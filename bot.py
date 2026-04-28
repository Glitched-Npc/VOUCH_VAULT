import discord
from discord.ext import commands
import psycopg2 
import os
from datetime import datetime, timedelta

# ============================================================================
# 🔑 CONFIG
# ============================================================================
DISCORD_BOT_TOKEN = os.getenv('DISCORD_TOKEN')
ADMIN_USER_ID = 882005122144669707 # <--- YOUR PERSONAL DISCORD USER ID

DB_URL = os.getenv('DATABASE_URL')
conn = psycopg2.connect(DB_URL)
cursor = conn.cursor()

# Create tables: One for vouches, one for subscriptions
cursor.execute('''
    CREATE TABLE IF NOT EXISTS vouches (
        id SERIAL PRIMARY KEY,
        seller_id BIGINT,
        customer_id BIGINT,
        customer_name TEXT,
        content TEXT,
        timestamp TEXT,
        origin_server_id BIGINT
    )
''')
cursor.execute('''
    CREATE TABLE IF NOT EXISTS subscriptions (
        server_id BIGINT PRIMARY KEY,
        expiry_date TIMESTAMP
    )
''')
conn.commit()

# ============================================================================
# 🤖 BOT SETUP & HELPER
# ============================================================================
intents = discord.Intents.default()
intents.message_content = True 
bot = commands.Bot(command_prefix="!", intents=intents)

def check_subscription(server_id):
    """Returns True if the server has an active subscription"""
    cursor.execute('SELECT expiry_date FROM subscriptions WHERE server_id = %s', (server_id,))
    result = cursor.fetchone()
    if result:
        expiry = result[0]
        if datetime.now() < expiry:
            return True
    return False

@bot.event
async def on_ready():
    print(f'🛡️ Vouch Vault (SUBSCRIPTION MODE) is Online')

# ============================================================================
# 👑 ADMIN COMMAND: !authorize <server_id> <days>
# ============================================================================
@bot.command()
async def authorize(ctx, server_id: int, days: int):
    if ctx.author.id != ADMIN_USER_ID:
        return # Only you can use this

    new_expiry = datetime.now() + timedelta(days=days)
    
    cursor.execute('''
        INSERT INTO subscriptions (server_id, expiry_date)
        VALUES (%s, %s)
        ON CONFLICT (server_id) DO UPDATE SET expiry_date = EXCLUDED.expiry_date
    ''', (server_id, new_expiry))
    conn.commit()

    await ctx.send(f"✅ **Authorized!** Server `{server_id}` now has `{days}` days of Premium.")

# ============================================================================
# ✍️ COMMAND: !vouch
# ============================================================================
@bot.command()
async def vouch(ctx, seller: discord.Member, *, message: str):
    if not check_subscription(ctx.guild.id):
        await ctx.send("🔒 **Subscription Expired.** $4.99/mo required. Contact **EXTEKK**.")
        return

    if seller.id == ctx.author.id:
        await ctx.send("❌ Self-vouching is disabled.")
        return

    time_now = datetime.now().strftime("%Y-%m-%d %H:%M")
    cursor.execute('INSERT INTO vouches (seller_id, customer_id, customer_name, content, timestamp, origin_server_id) VALUES (%s, %s, %s, %s, %s, %s)', (seller.id, ctx.author.id, ctx.author.name, message, time_now, ctx.guild.id))
    conn.commit()

    await ctx.send(embed=discord.Embed(title="✨ Vouch Recorded", description=f"```{message}```", color=0x81c784))

# ============================================================================
# 📊 COMMAND: !profile
# ============================================================================
@bot.command()
async def profile(ctx, user: discord.Member = None):
    if not check_subscription(ctx.guild.id):
        await ctx.send("🔒 **Subscription Expired.** $4.99/mo required. Contact **EXTEKK**.")
        return

    user = user or ctx.author
    cursor.execute('SELECT customer_name, content, timestamp FROM vouches WHERE seller_id = %s', (user.id,))
    all_vouches = cursor.fetchall()
    
    embed = discord.Embed(title=f"🛡️ Reputation Profile: {user.name}", description=f"Total Vouches: **{len(all_vouches)}**", color=0x4fc3f7)
    for name, msg, time in reversed(all_vouches[-5:]):
        embed.add_field(name=f"By {name} on {time}", value=msg, inline=False)
    await ctx.send(embed=embed)

bot.run(DISCORD_BOT_TOKEN)
