import discord
from discord.ext import commands
import psycopg2 
import os
import re # Added for time parsing
from datetime import datetime, timedelta

# ============================================================================
# 👑 ADMIN & TESTER PANEL
# ============================================================================
ADMIN_USER_ID = 882005122144669707 

# Any User ID in this list can use the bot for FREE in any server.
TESTER_IDS = [
    882005122144669707, # You
    # Add other tester Discord IDs here, separated by commas
]

# ============================================================================
# 🔑 CONFIG & DATABASE
# ============================================================================
DISCORD_BOT_TOKEN = os.getenv('DISCORD_TOKEN')
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
# 🛠️ TIME PARSER HELPER
# ============================================================================
def parse_duration(duration_str):
    """Converts strings like 10m, 2h, 30d, 1mo, 1y into a timedelta object"""
    match = re.match(r"(\d+)([smhdowy])", duration_str.lower())
    if not match:
        match = re.match(r"(\d+)(mo)", duration_str.lower())
        if not match: return None

    amount, unit = match.groups()
    amount = int(amount)

    if unit == 's': return timedelta(seconds=amount)
    if unit == 'm': return timedelta(minutes=amount)
    if unit == 'h': return timedelta(hours=amount)
    if unit == 'd': return timedelta(days=amount)
    if unit == 'w': return timedelta(weeks=amount)
    if unit == 'mo': return timedelta(days=amount * 30)
    if unit == 'y': return timedelta(days=amount * 365)
    return None

# ============================================================================
# 🤖 BOT SETUP & HELPERS
# ============================================================================
intents = discord.Intents.default()
intents.message_content = True 
bot = commands.Bot(command_prefix="!", intents=intents)

def is_authorized(user_id, server_id):
    """Checks if a user is a tester OR if the server has an active sub"""
    if user_id in TESTER_IDS:
        return True
    
    cursor.execute('SELECT expiry_date FROM subscriptions WHERE server_id = %s', (server_id,))
    result = cursor.fetchone()
    if result:
        expiry = result[0]
        if datetime.now() < expiry:
            return True
    return False

@bot.event
async def on_ready():
    print(f'🛡️ Vouch Vault (TIME-MASTER MODE) is Online')

# ============================================================================
# 👑 ADMIN COMMANDS
# ============================================================================

@bot.command()
async def authorize(ctx, server_id: int, duration: str):
    """Usage: !authorize [ID] 10m OR !authorize [ID] 30d"""
    if ctx.author.id != ADMIN_USER_ID:
        return 

    time_diff = parse_duration(duration)
    if time_diff is None:
        await ctx.send("❌ **Invalid Format!** Use `10m`, `2h`, `7d`, `1mo`, or `1y`.")
        return

    new_expiry = datetime.now() + time_diff
    
    cursor.execute('''
        INSERT INTO subscriptions (server_id, expiry_date)
        VALUES (%s, %s)
        ON CONFLICT (server_id) DO UPDATE SET expiry_date = EXCLUDED.expiry_date
    ''', (server_id, new_expiry))
    conn.commit()

    await ctx.send(f"✅ **Authorized!** Server `{server_id}` Premium until: `{new_expiry.strftime('%Y-%m-%d %H:%M:%S')}`")

@bot.command()
async def clearprofile(ctx, user_id: int):
    """Clears all vouches for a specific user ID"""
    if ctx.author.id != ADMIN_USER_ID:
        return 
    cursor.execute('DELETE FROM vouches WHERE seller_id = %s', (user_id,))
    conn.commit()
    await ctx.send(f"🧹 **Cleared!** All vouches for User ID `{user_id}` have been removed.")

# ============================================================================
# ✍️ MAIN COMMANDS
# ============================================================================

@bot.command()
async def vouch(ctx, seller: discord.Member, *, message: str):
    if not is_authorized(ctx.author.id, ctx.guild.id):
        await ctx.send("🔒 **Subscription Expired.** $6.99/mo required. Contact **The Silk Road**.")
        return

    if seller.id == ctx.author.id:
        await ctx.send("❌ Self-vouching is disabled.")
        return

    time_now = datetime.now().strftime("%Y-%m-%d %H:%M")
    cursor.execute('INSERT INTO vouches (seller_id, customer_id, customer_name, content, timestamp, origin_server_id) VALUES (%s, %s, %s, %s, %s, %s)', (seller.id, ctx.author.id, ctx.author.name, message, time_now, ctx.guild.id))
    conn.commit()

    await ctx.send(embed=discord.Embed(title="✨ Vouch Recorded", description=f"```{message}```", color=0x81c784))

@bot.command()
async def profile(ctx, user: discord.Member = None):
    if not is_authorized(ctx.author.id, ctx.guild.id):
        await ctx.send("🔒 **Subscription Expired.** $6.99/mo required. Contact **The Silk Road**.")
        return

    user = user or ctx.author
    cursor.execute('SELECT customer_name, content, timestamp FROM vouches WHERE seller_id = %s', (user.id,))
    all_vouches = cursor.fetchall()
    
    embed = discord.Embed(title=f"🛡️ Reputation Profile: {user.name}", description=f"Total Vouches: **{len(all_vouches)}**", color=0x4fc3f7)
    for name, msg, time in reversed(all_vouches[-5:]):
        embed.add_field(name=f"By {name} on {time}", value=msg, inline=False)
    await ctx.send(embed=embed)

bot.run(DISCORD_BOT_TOKEN)
