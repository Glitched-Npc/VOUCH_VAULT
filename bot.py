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
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT expiry_date FROM subscriptions WHERE server_id = %s', (server_id,))
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    if result and datetime.now() < result[0]: return True
    return False

def parse_duration(duration_str):
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
# 🤖 BOT SETUP
# ============================================================================
intents = discord.Intents.default()
intents.message_content = True 
intents.guilds = True 
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS vouches (id SERIAL PRIMARY KEY, seller_id BIGINT, customer_id BIGINT, customer_name TEXT, content TEXT, timestamp TEXT, origin_server_id BIGINT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS subscriptions (server_id BIGINT PRIMARY KEY, expiry_date TIMESTAMP)')
    cursor.execute('CREATE TABLE IF NOT EXISTS server_backups (server_id BIGINT PRIMARY KEY, blueprint JSONB, backup_date TIMESTAMP)')
    # NEW: Global Blacklist Table
    cursor.execute('CREATE TABLE IF NOT EXISTS global_blacklist (user_id BIGINT PRIMARY KEY, reason TEXT, date_flagged TIMESTAMP)')
    conn.commit()
    cursor.close()
    conn.close()
    print(f'✅ Vouch Vault Security Engine Online')

# ============================================================================
# 🚨 GLOBAL SECURITY COMMANDS (ADMIN ONLY)
# ============================================================================

@bot.command()
async def flag(ctx, user_id: int, *, reason: str):
    """Adds a user to the Global Blacklist"""
    if ctx.author.id != ADMIN_USER_ID: return

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO global_blacklist (user_id, reason, date_flagged) 
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id) DO UPDATE SET reason = EXCLUDED.reason
    ''', (user_id, reason, datetime.now()))
    conn.commit()
    cursor.close()
    conn.close()

    await ctx.send(f"🚨 **GLOBAL ALERT:** User `{user_id}` has been flagged as a scammer across the entire Silk Labz network.")

@bot.command()
async def unflag(ctx, user_id: int):
    """Removes a user from the Global Blacklist"""
    if ctx.author.id != ADMIN_USER_ID: return

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM global_blacklist WHERE user_id = %s', (user_id,))
    conn.commit()
    cursor.close()
    conn.close()

    await ctx.send(f"✅ User `{user_id}` has been removed from the Global Blacklist.")

# ============================================================================
# 📊 UPDATED PROFILE COMMAND (WITH SECURITY CHECK)
# ============================================================================
@bot.command()
async def profile(ctx, user: discord.Member = None):
    if not is_authorized(ctx.author.id, ctx.guild.id):
        await ctx.send("🔒 Subscription Required.")
        return

    user = user or ctx.author
    
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Check if user is BLACKLISTED
    cursor.execute('SELECT reason, date_flagged FROM global_blacklist WHERE user_id = %s', (user.id,))
    blacklist_entry = cursor.fetchone()

    # 2. Fetch Vouch Data
    cursor.execute('SELECT customer_name, content, timestamp FROM vouches WHERE seller_id = %s', (user.id,))
    all_vouches = cursor.fetchall()
    vouch_count = len(all_vouches)

    cursor.execute('SELECT COUNT(DISTINCT origin_server_id) FROM vouches WHERE seller_id = %s', (user.id,))
    unique_servers = cursor.fetchone()[0]
    cursor.close()
    conn.close()

    trust_score = min((unique_servers * 10) + vouch_count, 100)

    # --- IF BLACKLISTED: SHOW MASSIVE WARNING ---
    if blacklist_entry:
        embed = discord.Embed(
            title="⚠️ SCAMMER ALERT - GLOBAL BLACKLIST ⚠️",
            description=f"**WARNING:** {user.mention} is a flagged scammer!",
            color=0xFF0000 # Solid Red
        )
        embed.add_field(name="Reason", value=f"```{blacklist_entry[0]}```", inline=False)
        embed.add_field(name="Date Flagged", value=blacklist_entry[1].strftime("%Y-%m-%d"), inline=False)
        embed.set_thumbnail(url="https://cdn-icons-png.flaticon.com/512/595/595067.png") # Red Warning Icon
        await ctx.send(embed=embed)
        return

    # --- IF NOT BLACKLISTED: SHOW PROFESSIONAL PROFILE ---
    if vouch_count == 0:
        await ctx.send("🛡️ No vouches found in the Vault.")
        return

    async with ctx.typing():
        try:
            vouch_bundle = " ".join([v[1] for v in all_vouches])
            prompt = f"System: Analyst. Instruction: STRICT 2-sentence summary of seller reputation. Reviews: {vouch_bundle[:2000]}"
            chat = ai_client.chat.completions.create(messages=[{"role": "user", "content": prompt}], model="llama-3.1-8b-instant", temperature=0.1)
            ai_summary = chat.choices[0].message.content.strip()

            embed = discord.Embed(title=f"🛡️ Profile: {user.name}", description=f"**AI INSIGHT:**\n*{ai_summary}*", color=0x4fc3f7)
            embed.add_field(name="🛡️ Trust Score", value=f"**{trust_score}/100**", inline=True)
            embed.add_field(name="🌐 Global Reach", value=f"**{unique_servers}** Servers", inline=True)
            embed.add_field(name="📈 Total", value=f"**{vouch_count}** Vouches", inline=True)
            
            for name, msg, time in reversed(all_vouches[-5:]):
                embed.add_field(name=f"✅ {name} ({time})", value=msg, inline=False)
            
            embed.set_footer(text="The Silk Labz: Security & Reputation Engine")
            await ctx.send(embed=embed)
        except Exception as e: await ctx.send(f"❌ AI Error: {str(e)}")

# ============================================================================
# ✍️ ALL OTHER COMMANDS (VOUCH, IMPORT, BACKUP, AUTHORIZE)
# ============================================================================
@bot.command()
async def vouch(ctx, seller: discord.Member, *, message: str):
    if not is_authorized(ctx.author.id, ctx.guild.id):
        await ctx.send("🔒 **Subscription Expired.** $6.99/mo required.")
        return
    if seller.id == ctx.author.id:
        await ctx.send("❌ Self-vouching is disabled.")
        return
    
    # Check if seller is blacklisted before allowing a vouch
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM global_blacklist WHERE user_id = %s', (seller.id,))
    if cursor.fetchone():
        await ctx.send("❌ **Cannot Vouch:** This user is on the Global Blacklist for scamming.")
        cursor.close()
        conn.close()
        return

    time_now = datetime.now().strftime("%Y-%m-%d %H:%M")
    cursor.execute('INSERT INTO vouches (seller_id, customer_id, customer_name, content, timestamp, origin_server_id) VALUES (%s, %s, %s, %s, %s, %s)', (seller.id, ctx.author.id, ctx.author.name, message, time_now, ctx.guild.id))
    conn.commit()
    cursor.close()
    conn.close()

    await ctx.send(embed=discord.Embed(title="✨ Vouch Recorded", description=f"```{message}```", color=0x81c784))
    try:
        thanks_prompt = f"Friendly AI one-sentence thank you to {ctx.author.name} for vouching for {seller.name}."
        chat = ai_client.chat.completions.create(messages=[{"role": "user", "content": thanks_prompt}], model="llama-3.1-8b-instant", temperature=0.7)
        await ctx.send(embed=discord.Embed(description=f"💬 **AI:** {chat.choices[0].message.content.strip()}", color=0x4fc3f7))
    except: pass

# ... (Include !backup, !restore, !authorize, !import_vouches as they were)
# [I have left these out for brevity, but keep them in your actual file!]
bot.run(DISCORD_BOT_TOKEN)
