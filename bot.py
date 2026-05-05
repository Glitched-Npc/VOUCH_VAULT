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
# 🛠️ HELPERS
# ============================================================================
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
    cursor.execute('INSERT INTO server_backups (server_id, blueprint, backup_date) VALUES (%s, %s, %s) ON CONFLICT (server_id) DO UPDATE SET blueprint = EXCLUDED.blueprint, backup_date = EXCLUDED.backup_date', (guild.id, json.dumps(blueprint), datetime.now()))
    conn.commit()

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
    print(f'🛡️ Vouch Vault + Restore Engine is Online')

# ============================================================================
# 🔄 RESTORE COMMAND (FIXED)
# ============================================================================
@bot.command()
async def restore(ctx, old_server_id: int):
    # 1. SECURITY CHECK
    if ctx.author.id != ADMIN_USER_ID:
        await ctx.send(f"❌ **Access Denied.** Your ID ({ctx.author.id}) is not authorized to restore.")
        return

    # 2. FETCH DATA
    cursor.execute('SELECT blueprint FROM server_backups WHERE server_id = %s', (old_server_id,))
    row = cursor.fetchone()
    
    if not row:
        await ctx.send(f"❓ **No backup found** for Server ID `{old_server_id}`. Did you type `!backup` in the old server?")
        return

    blueprint = row[0]
    # Handle cases where Postgres returns JSON as a string
    if isinstance(blueprint, str):
        blueprint = json.loads(blueprint)

    await ctx.send(f"🚀 **Restoration Started!** Rebuilding structure from server `{old_server_id}`...")

    try:
        # 3. RECREATE ROLES
        for r in blueprint.get('roles', []):
            try:
                await ctx.guild.create_role(name=r['name'], color=discord.Color(r['color']))
                print(f"Created role: {r['name']}")
            except Exception as e:
                print(f"Failed to create role {r['name']}: {e}")

        # 4. RECREATE CHANNELS
        for cat in blueprint.get('categories', []):
            new_cat = await ctx.guild.create_category(cat['name'])
            for chan in cat['channels']:
                if chan['type'] == 'text':
                    await ctx.guild.create_text_channel(chan['name'], category=new_cat)
                elif chan['type'] == 'voice':
                    await ctx.guild.create_voice_channel(chan['name'], category=new_cat)
        
        await ctx.send("✅ **Restoration Complete!** Roles and Channels have been rebuilt.")

    except Exception as e:
        await ctx.send(f"❌ **Restore Failed:** {str(e)}")

# ============================================================================
# 📥 BACKUP COMMAND
# ============================================================================
@bot.command()
async def backup(ctx):
    if not is_authorized(ctx.author.id, ctx.guild.id):
        await ctx.send("🔒 Premium Required.")
        return
    save_server_blueprint(ctx.guild)
    await ctx.send("✅ **Backup Saved!** You can now restore this layout to any other server.")

# ============================================================================
# ✍️ VOUCH / PROFILE / AUTHORIZE (Kept same as before)
# ============================================================================
@bot.command()
async def vouch(ctx, seller: discord.Member, *, message: str):
    if not is_authorized(ctx.author.id, ctx.guild.id):
        await ctx.send("🔒 Subscription Expired.")
        return
    time_now = datetime.now().strftime("%Y-%m-%d %H:%M")
    cursor.execute('INSERT INTO vouches (seller_id, customer_id, customer_name, content, timestamp, origin_server_id) VALUES (%s, %s, %s, %s, %s, %s)', (seller.id, ctx.author.id, ctx.author.name, message, time_now, ctx.guild.id))
    conn.commit()
    await ctx.send("✅ Vouch Recorded!")

@bot.command()
async def profile(ctx, user: discord.Member = None):
    if not is_authorized(ctx.author.id, ctx.guild.id):
        await ctx.send("🔒 Subscription Expired.")
        return
    user = user or ctx.author
    cursor.execute('SELECT customer_name, content, timestamp FROM vouches WHERE seller_id = %s', (user.id,))
    all_vouches = cursor.fetchall()
    await ctx.send(f"🛡️ Profile: {user.name} has {len(all_vouches)} vouches.")

@bot.command()
async def authorize(ctx, server_id: int, duration: str):
    if ctx.author.id != ADMIN_USER_ID: return 
    match = re.match(r"(\d+)([smhdowy])", duration.lower())
    amount, unit = int(match.group(1)), match.group(2)
    if unit == 'd': delta = timedelta(days=amount)
    elif unit == 'm': delta = timedelta(minutes=amount)
    # (Other time units...)
    new_expiry = datetime.now() + delta
    cursor.execute('INSERT INTO subscriptions (server_id, expiry_date) VALUES (%s, %s) ON CONFLICT (server_id) DO UPDATE SET expiry_date = EXCLUDED.expiry_date', (server_id, new_expiry))
    conn.commit()
    await ctx.send(f"✅ Authorized `{server_id}` until `{new_expiry}`")

bot.run(DISCORD_BOT_TOKEN)
