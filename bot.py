import discord
from discord.ext import commands
import psycopg2 
import os
import re 
import json
from datetime import datetime, timedelta
from groq import Groq 

# ============================================================================
# 👑 CONFIG
# ============================================================================
ADMIN_USER_ID = 882005122144669707 
TESTER_IDS = [882005122144669707]

DISCORD_BOT_TOKEN = os.getenv('DISCORD_TOKEN')
GROQ_API_KEY = os.getenv('GROQ_KEY') 
DB_URL = os.getenv('DATABASE_URL')

conn = psycopg2.connect(DB_URL)
cursor = conn.cursor()
ai_client = Groq(api_key=GROQ_API_KEY)

# ============================================================================
# 🛠️ DATABASE HELPER (THE AUTO-SYNC ENGINE)
# ============================================================================
def save_server_blueprint(guild):
    """Internal function to capture server state and save to Postgres"""
    roles = []
    for role in guild.roles:
        if not role.is_default() and not role.managed: # Skip @everyone and bot roles
            roles.append({"name": role.name, "color": role.color.value, "permissions": role.permissions.value})

    categories = []
    for category in guild.categories:
        cat_data = {"name": category.name, "channels": []}
        for channel in category.channels:
            cat_data["channels"].append({"name": channel.name, "type": str(channel.type)})
        categories.append(cat_data)

    blueprint = {"roles": roles, "categories": categories}
    
    cursor.execute('''
        INSERT INTO server_backups (server_id, blueprint, backup_date)
        VALUES (%s, %s, %s)
        ON CONFLICT (server_id) DO UPDATE SET blueprint = EXCLUDED.blueprint, backup_date = EXCLUDED.backup_date
    ''', (guild.id, json.dumps(blueprint), datetime.now()))
    conn.commit()
    print(f"☁️ Cloud Sync: Server {guild.id} layout updated.")

# ============================================================================
# 🤖 BOT SETUP
# ============================================================================
intents = discord.Intents.default()
intents.message_content = True 
intents.guilds = True # Required to see channels/roles
bot = commands.Bot(command_prefix="!", intents=intents)

def is_authorized(user_id, server_id):
    if user_id in TESTER_IDS: return True
    cursor.execute('SELECT expiry_date FROM subscriptions WHERE server_id = %s', (server_id,))
    result = cursor.fetchone()
    if result and datetime.now() < result[0]: return True
    return False

@bot.event
async def on_ready():
    print(f'🛡️ Vouch Vault + Auto-Sync Backup is Online')

# ============================================================================
# 📡 AUTO-SYNC LISTENERS (THE "BETTER THAN COMPETITION" PART)
# ============================================================================

@bot.event
async def on_guild_channel_create(channel):
    # If a channel is created, auto-update the backup if they have a sub
    cursor.execute('SELECT 1 FROM subscriptions WHERE server_id = %s', (channel.guild.id,))
    if cursor.fetchone():
        save_server_blueprint(channel.guild)

@bot.event
async def on_guild_channel_delete(channel):
    cursor.execute('SELECT 1 FROM subscriptions WHERE server_id = %s', (channel.guild.id,))
    if cursor.fetchone():
        save_server_blueprint(channel.guild)

@bot.event
async def on_guild_role_create(role):
    cursor.execute('SELECT 1 FROM subscriptions WHERE server_id = %s', (role.guild.id,))
    if cursor.fetchone():
        save_server_blueprint(role.guild)

# ============================================================================
# 📥 COMMANDS
# ============================================================================

@bot.command()
async def backup(ctx):
    """Manually force a cloud backup"""
    if not is_authorized(ctx.author.id, ctx.guild.id):
        await ctx.send("🔒 Premium Required.")
        return
    save_server_blueprint(ctx.guild)
    await ctx.send("✅ **Manual Sync Complete.** Server structure is saved in the Cloud Vault.")

@bot.command()
async def restore(ctx, old_server_id: int):
    if ctx.author.id != ADMIN_USER_ID: return
    
    cursor.execute('SELECT blueprint FROM server_backups WHERE server_id = %s', (old_server_id,))
    result = cursor.fetchone()
    if not result:
        await ctx.send("❓ No backup found.")
        return

    blueprint = result[0]
    await ctx.send("🚀 **Restoration Started!**")

    for r in blueprint['roles']:
        try: await ctx.guild.create_role(name=r['name'], color=discord.Color(r['color']))
        except: pass

    for cat in blueprint['categories']:
        new_cat = await ctx.guild.create_category(cat['name'])
        for chan in cat['channels']:
            if chan['type'] == 'text': await ctx.guild.create_text_channel(chan['name'], category=new_cat)
            elif chan['type'] == 'voice': await ctx.guild.create_voice_channel(chan['name'], category=new_cat)
    
    await ctx.send("✅ **Restoration Complete!**")

# ... (KEEP ALL OTHER VOUCH/PROFILE/AUTHORIZE COMMANDS BELOW)
