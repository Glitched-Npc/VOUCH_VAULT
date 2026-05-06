import discord
from discord.ext import commands
import psycopg2 
import os
import re 
import json
from datetime import datetime, timedelta
from groq import Groq 

# ============================================================================
# 👑 CONFIG & ADMIN PANEL
# ============================================================================
ADMIN_USER_ID = 882005122144669707 
TESTER_IDS = [882005122144669707]

DISCORD_BOT_TOKEN = os.getenv('DISCORD_TOKEN')
GROQ_API_KEY = os.getenv('GROQ_KEY') 
DB_URL = os.getenv('DATABASE_URL')

ai_client = Groq(api_key=GROQ_API_KEY)

# ============================================================================
# 🛠️ DATABASE HELPERS
# ============================================================================
def get_db_connection():
    return psycopg2.connect(DB_URL)

def is_authorized(user_id, server_id):
    if user_id in TESTER_IDS: return True
    if not server_id: return False
    try:
        conn = get_db_connection(); cursor = conn.cursor()
        cursor.execute('SELECT expiry_date FROM subscriptions WHERE server_id = %s', (server_id,))
        result = cursor.fetchone()
        cursor.close(); conn.close()
        if result and datetime.now() < result[0]: return True
    except: pass
    return False

# ============================================================================
# 🤖 BOT SETUP
# ============================================================================
intents = discord.Intents.default()
intents.message_content = True 
intents.guilds = True 
intents.members = True 

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS vouches (id SERIAL PRIMARY KEY, seller_id BIGINT, customer_id BIGINT, customer_name TEXT, content TEXT, timestamp TEXT, origin_server_id BIGINT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS subscriptions (server_id BIGINT PRIMARY KEY, expiry_date TIMESTAMP)')
    cursor.execute('CREATE TABLE IF NOT EXISTS server_backups (server_id BIGINT PRIMARY KEY, blueprint JSONB, backup_date TIMESTAMP)')
    cursor.execute('CREATE TABLE IF NOT EXISTS global_blacklist (user_id BIGINT PRIMARY KEY, reason TEXT, date_flagged TIMESTAMP)')
    conn.commit(); cursor.close(); conn.close()
    print(f'✅ Vouch Vault (Member Protection Edition) Online')

# ============================================================================
# 🛡️ THE BUYER SHIELD (AUTO-PROTECTION FOR MEMBERS)
# ============================================================================
@bot.event
async def on_member_join(member):
    # Check if the member joining is a flagged scammer to warn the owner
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute('SELECT reason FROM global_blacklist WHERE user_id = %s', (member.id,))
    blacklisted = cursor.fetchone()
    cursor.close(); conn.close()

    if blacklisted:
        # Alert the server staff if they have a logs channel or just the first text channel
        try:
            embed = discord.Embed(title="🚨 SCAMMER ENTERED SERVER", color=0xFF0000)
            embed.description = f"**{member.name}** is on the Vouch Vault Global Blacklist.\n**Reason:** {blacklisted[0]}"
            await member.guild.system_channel.send(embed=embed)
        except: pass

# ============================================================================
# 📄 MEMBER COMMAND: !myvouches (PERSONAL RECEIPT BOOK)
# ============================================================================
@bot.command()
async def myvouches(ctx):
    """Sends a private DM to the user with their history of vouches given"""
    if not is_authorized(ctx.author.id, ctx.guild.id):
        await ctx.send("🔒 Subscription Required.")
        return

    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute('SELECT content, timestamp, seller_id FROM vouches WHERE customer_id = %s ORDER BY id DESC LIMIT 10', (ctx.author.id,))
    history = cursor.fetchall()
    cursor.close(); conn.close()

    if not history:
        await ctx.send("❓ You haven't left any vouches in the Global Vault yet.")
        return

    embed = discord.Embed(title="📄 Your Vouch History (Last 10)", color=0x4fc3f7)
    for msg, time, s_id in history:
        embed.add_field(name=f"To Seller ID: {s_id} ({time})", value=f"\"{msg}\"", inline=False)
    
    try:
        await ctx.author.send(embed=embed)
        await ctx.send(f"📬 {ctx.author.mention}, I've sent your transaction history to your DMs!")
    except:
        await ctx.send(f"❌ {ctx.author.mention}, I couldn't DM you. Please open your DMs.")

# ============================================================================
# 📊 DUAL-SIDED PROFILE (FOR STATUS)
# ============================================================================
@bot.command()
async def profile(ctx, user: discord.Member = None):
    if not is_authorized(ctx.author.id, ctx.guild.id):
        await ctx.send("🔒 Subscription Required.")
        return
    user = user or ctx.author
    
    conn = get_db_connection(); cursor = conn.cursor()
    
    # 1. Blacklist Check
    cursor.execute('SELECT reason FROM global_blacklist WHERE user_id = %s', (user.id,))
    blacklisted = cursor.fetchone()
    if blacklisted:
        embed = discord.Embed(title="⚠️ GLOBAL SCAMMER ALERT", color=0xFF0000)
        embed.description = f"**WARNING:** {user.mention} is a flagged scammer!\nReason: {blacklisted[0]}"
        await ctx.send(embed=embed)
        cursor.close(); conn.close(); return

    # 2. Seller/Buyer Data
    cursor.execute('SELECT content FROM vouches WHERE seller_id = %s', (user.id,))
    vouches_received = cursor.fetchall()
    cursor.execute('SELECT COUNT(*) FROM vouches WHERE customer_id = %s', (user.id,))
    vouches_given = cursor.fetchone()[0]
    cursor.close(); conn.close()

    # Ranking
    rank = "Newcomer"
    if vouches_given > 50: rank = "Legendary Supporter 💎"
    elif vouches_given > 20: rank = "Elite Supporter 🎖️"
    elif vouches_given > 5: rank = "Verified Supporter ✅"

    embed = discord.Embed(title=f"🛡️ Global Identity: {user.name}", color=0x4fc3f7)
    embed.add_field(name="🤝 COMMUNITY STATUS", value=f"**Rank:** {rank}\n**Vouches Given:** {vouches_given}", inline=True)
    embed.add_field(name="💰 SELLER STATUS", value=f"**Vouches Received:** {len(vouches_received)}", inline=True)

    if vouches_received:
        async with ctx.typing():
            vouch_bundle = " ".join([v[0] for v in vouches_received])
            prompt = f"System: Analyst. Instruction: STRICT 2-sentence summary of seller reputation. Reviews: {vouch_bundle[:2000]}"
            chat = ai_client.chat.completions.create(messages=[{"role": "user", "content": prompt}], model="llama-3.1-8b-instant", temperature=0.1)
            embed.description = f"**AI REPUTATION INSIGHT:**\n*{chat.choices[0].message.content.strip()}*"

    embed.set_thumbnail(url=user.avatar.url if user.avatar else None)
    await ctx.send(embed=embed)

# ============================================================================
# ✍️ ALL OTHER OWNER COMMANDS (VOUCH, FLAG, BACKUP, RESTORE, ETC.)
# ============================================================================
# [KEEP ALL YOUR PREVIOUS COMMANDS HERE]
