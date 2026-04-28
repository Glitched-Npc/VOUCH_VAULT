import discord
from discord.ext import commands
import psycopg2 
import os
from datetime import datetime

# ============================================================================
# 🟢 BUSINESS PANEL (AUTHORIZED SERVERS)
# ============================================================================
# Add every Server ID that pays you to this list.
AUTHORIZED_SERVERS = [
    1378864322687537262,  # Your Server ID
    1498666045500821504,  # Testing server
]

# ============================================================================
# 📂 PERMANENT DATABASE SYSTEM (POSTGRESQL)
# ============================================================================
DB_URL = os.getenv('DATABASE_URL')
conn = psycopg2.connect(DB_URL)
cursor = conn.cursor()

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
conn.commit()

# ============================================================================
# 🤖 BOT SETUP
# ============================================================================
DISCORD_BOT_TOKEN = os.getenv('DISCORD_TOKEN')
intents = discord.Intents.default()
intents.message_content = True 
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f'🛡️ Vouch Vault (FULLY SECURED) is Online as {bot.user}')

# ============================================================================
# ✍️ COMMAND: !vouch @user <message>
# ============================================================================
@bot.command()
async def vouch(ctx, seller: discord.Member, *, message: str):
    # THE LOCK
    if ctx.guild.id not in AUTHORIZED_SERVERS:
        await ctx.send("🔒 **Premium Required.** This server is not authorized. Contact **The Silk Road**.")
        return

    if seller.id == ctx.author.id:
        await ctx.send("❌ You cannot vouch for yourself.")
        return

    time_now = datetime.now().strftime("%Y-%m-%d %H:%M")
    cursor.execute('''
        INSERT INTO vouches (seller_id, customer_id, customer_name, content, timestamp, origin_server_id)
        VALUES (%s, %s, %s, %s, %s, %s)
    ''', (seller.id, ctx.author.id, ctx.author.name, message, time_now, ctx.guild.id))
    conn.commit()

    embed = discord.Embed(title="✨ Vouch Recorded", color=0x81c784)
    embed.add_field(name="Feedback", value=f"```{message}```")
    embed.set_footer(text=f"ID: {seller.id} • Verified on {time_now}")
    await ctx.send(embed=embed)

# ============================================================================
# 📊 COMMAND: !profile @user
# ============================================================================
@bot.command()
async def profile(ctx, user: discord.Member = None):
    # THE LOCK (Adding this makes the whole bot private)
    if ctx.guild.id not in AUTHORIZED_SERVERS:
        await ctx.send("🔒 **Premium Required.** This server is not authorized. Contact **The Silk Road**.")
        return

    user = user or ctx.author
    cursor.execute('SELECT customer_name, content, timestamp FROM vouches WHERE seller_id = %s', (user.id,))
    all_vouches = cursor.fetchall()
    vouch_count = len(all_vouches)

    embed = discord.Embed(
        title=f"🛡️ Reputation Profile: {user.name}",
        description=f"This user has **{vouch_count}** backed-up vouches.",
        color=0x4fc3f7
    )

    if vouch_count > 0:
        recent = all_vouches[-5:]
        for name, msg, time in reversed(recent):
            embed.add_field(name=f"By {name} on {time}", value=msg, inline=False)
    else:
        embed.description = "No vouches found in the Global Vault."

    await ctx.send(embed=embed)

bot.run(DISCORD_BOT_TOKEN)
