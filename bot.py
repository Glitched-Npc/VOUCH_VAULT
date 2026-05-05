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

ai_client = Groq(api_key=GROQ_API_KEY)

# ============================================================================
# 🛠️ DATABASE HELPER (RE-CONNECTS IF NEEDED)
# ============================================================================
def get_db_connection():
    return psycopg2.connect(DB_URL)

def save_server_blueprint(guild):
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
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO server_backups (server_id, blueprint, backup_date) 
        VALUES (%s, %s, %s) 
        ON CONFLICT (server_id) DO UPDATE SET blueprint = EXCLUDED.blueprint, backup_date = EXCLUDED.backup_date
    ''', (guild.id, json.dumps(blueprint), datetime.now()))
    conn.commit()
    cursor.close()
    conn.close()

# ============================================================================
# 🤖 BOT SETUP
# ============================================================================
intents = discord.Intents.default()
intents.message_content = True 
intents.guilds = True # CRUCIAL: Must be on to see channels
bot = commands.Bot(command_prefix="!", intents=intents)

def is_authorized(user_id, server_id):
    if user_id in TESTER_IDS: return True
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT expiry_date FROM subscriptions WHERE server_id = %s', (server_id,))
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    if result and datetime.now() < result[0]: return True
    return False

@bot.event
async def on_ready():
    # Create tables if they don't exist
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS vouches (id SERIAL PRIMARY KEY, seller_id BIGINT, customer_id BIGINT, customer_name TEXT, content TEXT, timestamp TEXT, origin_server_id BIGINT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS subscriptions (server_id BIGINT PRIMARY KEY, expiry_date TIMESTAMP)')
    cursor.execute('CREATE TABLE IF NOT EXISTS server_backups (server_id BIGINT PRIMARY KEY, blueprint JSONB, backup_date TIMESTAMP)')
    conn.commit()
    cursor.close()
    conn.close()
    print(f'✅ Vouch Vault PRO Online')

# ============================================================================
# 📡 AUTO-SYNC
# ============================================================================
@bot.event
async def on_guild_channel_create(channel):
    if is_authorized(ADMIN_USER_ID, channel.guild.id):
        save_server_blueprint(channel.guild)

# ============================================================================
# 🔄 COMMANDS
# ============================================================================

@bot.command()
async def debug(ctx):
    """Tells you if the bot can see you and the server"""
    authorized = is_authorized(ctx.author.id, ctx.guild.id)
    await ctx.send(f"🤖 **Debug Info:**\n- Your ID: `{ctx.author.id}`\n- Server ID: `{ctx.guild.id}`\n- Authorized: `{authorized}`")

@bot.command()
async def restore(ctx, old_server_id: int):
    if ctx.author.id != ADMIN_USER_ID:
        await ctx.send("❌ Admin Only.")
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT blueprint FROM server_backups WHERE server_id = %s', (old_server_id,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()

    if not row:
        await ctx.send("❓ No backup found.")
        return

    blueprint = row[0]
    if isinstance(blueprint, str): blueprint = json.loads(blueprint)

    await ctx.send("🚀 **Restoring...**")
    for r in blueprint.get('roles', []):
        try: await ctx.guild.create_role(name=r['name'], color=discord.Color(r['color']))
        except: pass
    for cat in blueprint.get('categories', []):
        new_cat = await ctx.guild.create_category(cat['name'])
        for chan in cat['channels']:
            if chan['type'] == 'text': await ctx.guild.create_text_channel(chan['name'], category=new_cat)
    await ctx.send("✅ Done.")

@bot.command()
async def backup(ctx):
    if not is_authorized(ctx.author.id, ctx.guild.id):
        await ctx.send("🔒 Locked.")
        return
    save_server_blueprint(ctx.guild)
    await ctx.send("✅ Manual Backup Saved.")

@bot.command()
async def authorize(ctx, server_id: int, duration: str):
    if ctx.author.id != ADMIN_USER_ID: return 
    # (Simple duration parser for days)
    days = int(re.search(r'\d+', duration).group())
    new_expiry = datetime.now() + timedelta(days=days)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO subscriptions (server_id, expiry_date) VALUES (%s, %s) ON CONFLICT (server_id) DO UPDATE SET expiry_date = EXCLUDED.expiry_date', (server_id, new_expiry))
    conn.commit()
    cursor.close()
    conn.close()
    await ctx.send(f"✅ Authorized {server_id}")

bot.run(DISCORD_BOT_TOKEN)
