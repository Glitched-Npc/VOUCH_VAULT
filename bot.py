import discord
from discord.ext import commands
import sqlite3
import os
from datetime import datetime

# ============================================================================
# 🟢 BUSINESS PANEL: AUTHORIZED SERVERS (THE PAYWALL)
# ============================================================================
AUTHORIZED_SERVERS = [
    1378864322687537262,  # Your Server ID
]

# ============================================================================
# 📂 DATABASE SYSTEM (THE VAULT)
# ============================================================================
# This creates/connects to a permanent database file
db = sqlite3.connect('vouch_vault.db')
cursor = db.cursor()

# Create a professional table to store vouches
cursor.execute('''
    CREATE TABLE IF NOT EXISTS vouches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        seller_id INTEGER,
        customer_id INTEGER,
        customer_name TEXT,
        content TEXT,
        timestamp TEXT,
        origin_server_id INTEGER
    )
''')
db.commit()

# ============================================================================
# 🤖 BOT SETUP
# ============================================================================
DISCORD_BOT_TOKEN = os.getenv('DISCORD_TOKEN')
intents = discord.Intents.default()
intents.message_content = True 
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f'🛡️ Vouch Vault is Online as {bot.user}')

# ============================================================================
# ✍️ COMMAND: !vouch @user <message>
# ============================================================================
@bot.command()
async def vouch(ctx, seller: discord.Member, *, message: str):
    if ctx.guild.id not in AUTHORIZED_SERVERS:
        await ctx.send("🔒 **Premium Required.** This server is not authorized to use Vouch Vault.")
        return

    if seller.id == ctx.author.id:
        await ctx.send("❌ You cannot vouch for yourself.")
        return

    # Record the vouch in the Global Vault
    time_now = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    cursor.execute('''
        INSERT INTO vouches (seller_id, customer_id, customer_name, content, timestamp, origin_server_id)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (seller.id, ctx.author.id, ctx.author.name, message, time_now, ctx.guild.id))
    db.commit()

    embed = discord.Embed(
        title="✨ Vouch Recorded in Vault",
        description=f"{ctx.author.mention} has vouched for {seller.mention}",
        color=0x81c784
    )
    embed.add_field(name="Feedback", value=f"```{message}```")
    embed.set_footer(text=f"ID: {seller.id} • Verified on {time_now}")
    await ctx.send(embed=embed)

# ============================================================================
# 📊 COMMAND: !profile @user (THE RESTORE FEATURE)
# ============================================================================
@bot.command()
async def profile(ctx, user: discord.Member = None):
    user = user or ctx.author
    
    # Search the database for ALL vouches across ALL servers for this User ID
    cursor.execute('SELECT customer_name, content, timestamp FROM vouches WHERE seller_id = ?', (user.id,))
    all_vouches = cursor.fetchall()
    
    vouch_count = len(all_vouches)

    embed = discord.Embed(
        title=f"🛡️ Reputation Profile: {user.name}",
        description=f"This user has **{vouch_count}** backed-up vouches.",
        color=0x4fc3f7
    )

    if vouch_count > 0:
        # Show the most recent 5 vouches
        recent = all_vouches[-5:]
        for name, msg, time in reversed(recent):
            embed.add_field(
                name=f"By {name} on {time}",
                value=msg,
                inline=False
            )
    else:
        embed.description = "No vouches found for this user in the Global Vault."

    embed.set_thumbnail(url=user.avatar.url if user.avatar else None)
    await ctx.send(embed=embed)

bot.run(DISCORD_BOT_TOKEN)
