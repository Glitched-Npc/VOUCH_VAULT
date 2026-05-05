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
# 🛠️ THE AUTO-SYNC ENGINE (SAVES AUTOMATICALLY)
# ============================================================================
def save_server_blueprint(guild):
    """Captures roles and channels and saves to PostgreSQL"""
    roles = []
    for role in guild.roles:
        if not role.is_default() and not role.managed:
            roles.append({"name": role.name, "color": role.color.value})

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
    print(f"✅ Auto-Synced: Server {guild.id}")

def is_authorized(user_id, server_id):
    if user_id in TESTER_IDS: return True
    cursor.execute('SELECT expiry_date FROM subscriptions WHERE server_id = %s', (server_id,))
    result = cursor.fetchone()
    if result and datetime.now() < result[0]: return True
    return False

# ============================================================================
# 🤖 BOT SETUP
# ============================================================================
intents = discord.Intents.default()
intents.message_content = True 
intents.guilds = True 
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f'🛡️ Vouch Vault + Auto-Sync is Online')

# ============================================================================
# 📡 AUTO-SYNC LISTENERS (WATCHING FOR CHANGES)
# ============================================================================

@bot.event
async def on_guild_channel_create(channel):
    # Only sync if the server has a subscription
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
# 🔄 COMMANDS
# ============================================================================

@bot.command()
async def restore(ctx, old_server_id: int):
    if ctx.author.id != ADMIN_USER_ID:
        await ctx.send("❌ Access Denied.")
        return

    cursor.execute('SELECT blueprint FROM server_backups WHERE server_id = %s', (old_server_id,))
    row = cursor.fetchone()
    if not row:
        await ctx.send("❓ No backup found.")
        return

    blueprint = row[0]
    if isinstance(blueprint, str): blueprint = json.loads(blueprint)

    await ctx.send("🚀 **Restoration Started!** Building structure...")

    try:
        for r in blueprint.get('roles', []):
            try: await ctx.guild.create_role(name=r['name'], color=discord.Color(r['color']))
            except: pass

        for cat in blueprint.get('categories', []):
            new_cat = await ctx.guild.create_category(cat['name'])
            for chan in cat['channels']:
                if chan['type'] == 'text': await ctx.guild.create_text_channel(chan['name'], category=new_cat)
                elif chan['type'] == 'voice': await ctx.guild.create_voice_channel(chan['name'], category=new_cat)
        
        await ctx.send("✅ **Restoration Complete!**")
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)}")

@bot.command()
async def backup(ctx):
    """Manual backup just in case"""
    if not is_authorized(ctx.author.id, ctx.guild.id):
        await ctx.send("🔒 Premium Required.")
        return
    save_server_blueprint(ctx.guild)
    await ctx.send("✅ **Manual Backup Saved!**")

# ... (Keep all your VOUCH and PROFILE commands below)
