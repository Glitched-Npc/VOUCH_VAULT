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

def is_premium(server_id):
    if not server_id: return False
    try:
        conn = get_db_connection(); cursor = conn.cursor()
        cursor.execute('SELECT expiry_date FROM subscriptions WHERE server_id = %s', (server_id,))
        result = cursor.fetchone()
        cursor.close(); conn.close()
        if result and datetime.now() < result[0]: return True
    except: pass
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
    print(f'✅ Vouch Vault Security Hub Online')

# ============================================================================
# 🚨 GLOBAL SECURITY (FLAG: Admins | UNFLAG: Owner Only)
# ============================================================================

@bot.command()
async def flag(ctx, user: discord.User, *, reason: str = "No reason provided"):
    """Flag a scammer globally. Tidy Embed output."""
    # 1. Permission Check
    is_admin = ctx.author.guild_permissions.administrator if ctx.guild else False
    if ctx.author.id != ADMIN_USER_ID and ctx.author.id not in TESTER_IDS and not is_admin:
        await ctx.send("❌ **Access Denied.** Administrator permissions required."); return

    # 2. Premium Check
    if not is_premium(ctx.guild.id) and ctx.author.id not in TESTER_IDS:
        await ctx.send("🔒 **Premium Required.** $6.99/mo for Global Security."); return

    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO global_blacklist (user_id, reason, date_flagged) 
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id) DO UPDATE SET reason = EXCLUDED.reason
    ''', (user.id, f"Flagged by {ctx.guild.name}: {reason}", datetime.now()))
    conn.commit(); cursor.close(); conn.close()

    # THE TIDY BOX (Embed)
    embed = discord.Embed(title="🚨 GLOBAL BLACKLIST UPDATED", color=0xFF0000)
    embed.add_field(name="Target User", value=f"**{user.name}**", inline=True)
    embed.add_field(name="User ID", value=f"`{user.id}`", inline=True)
    embed.add_field(name="Reason", value=f"```{reason}```", inline=False)
    embed.set_footer(text=f"Reported via {ctx.guild.name} • Status: Globally Blocked")
    embed.set_thumbnail(url="https://cdn-icons-png.flaticon.com/512/595/595067.png")
    
    await ctx.send(embed=embed)

@bot.command()
async def unflag(ctx, user: discord.User):
    """EXCLUSIVE: Only the System Admin can unflag users."""
    if ctx.author.id != ADMIN_USER_ID:
        return # Silent ignore for security

    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute('DELETE FROM global_blacklist WHERE user_id = %s', (user.id,))
    conn.commit(); cursor.close(); conn.close()

    embed = discord.Embed(title="✅ SECURITY UPDATE", color=0x00FF00)
    embed.description = f"User **{user.name}** has been successfully removed from the Global Blacklist."
    embed.set_footer(text="Authorized by System Administrator")
    
    await ctx.send(embed=embed)

# ============================================================================
# 📊 PROFILE & AI INSIGHT
# ============================================================================
@bot.command()
async def profile(ctx, user: discord.Member = None):
    user = user or ctx.author
    premium = is_premium(ctx.guild.id) or ctx.author.id in TESTER_IDS
    
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute('SELECT reason FROM global_blacklist WHERE user_id = %s', (user.id,))
    blacklisted = cursor.fetchone()
    if blacklisted:
        embed = discord.Embed(title="⚠️ GLOBAL SCAMMER ALERT", color=0xFF0000)
        embed.description = f"**WARNING:** {user.mention} is flagged for: {blacklisted[0]}"
        await ctx.send(embed=embed)
        cursor.close(); conn.close(); return

    cursor.execute('SELECT content FROM vouches WHERE seller_id = %s', (user.id,))
    received = cursor.fetchall()
    cursor.execute('SELECT COUNT(*) FROM vouches WHERE customer_id = %s', (user.id,))
    given = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(DISTINCT origin_server_id) FROM vouches WHERE seller_id = %s', (user.id,))
    reach = cursor.fetchone()[0]
    cursor.close(); conn.close()

    rank = "Newcomer"
    if given > 50: rank = "Legendary Supporter 💎"
    elif given > 20: rank = "Elite Supporter 🎖️"
    elif given > 5: rank = "Verified Supporter ✅"

    embed = discord.Embed(title=f"🛡️ Global Profile: {user.name}", color=0x4fc3f7)
    embed.add_field(name="🤝 STATUS", value=f"**Rank:** {rank}\n**Vouches Given:** {given}", inline=True)
    embed.add_field(name="💰 SELLER", value=f"**Vouches:** {len(received)}\n**Reach:** {reach} Servers", inline=True)

    if premium and received:
        async with ctx.typing():
            try:
                bundle = " ".join([v[0] for v in received])
                p = f"System: Analyst. Instruction: STRICT 2-sentence summary. Reviews: {bundle[:2000]}"
                c = ai_client.chat.completions.create(messages=[{"role":"user","content":p}], model="llama-3.1-8b-instant", temperature=0.1)
                embed.description = f"**AI INSIGHT:**\n*{c.choices[0].message.content.strip()}*"
                for msg in received[-3:]:
                    embed.add_field(name="✅ Verified Vouch", value=msg[0], inline=False)
            except: pass
    elif received:
        embed.description = "💡 *[PREMIUM] AI Reputation Insights are hidden.*"

    embed.set_thumbnail(url=user.avatar.url if user.avatar else None)
    await ctx.send(embed=embed)

# ============================================================================
# 📄 MEMBER COMMAND: !myvouches
# ============================================================================
@bot.command()
async def myvouches(ctx):
    await ctx.send("⏳ **Checking your history...**")
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute('SELECT content, timestamp, seller_id, origin_server_id FROM vouches WHERE customer_id = %s ORDER BY id DESC LIMIT 10', (ctx.author.id,))
    history = cursor.fetchall()
    cursor.close(); conn.close()
    if not history:
        await ctx.send("❓ No history found."); return

    embed = discord.Embed(title="📄 Your Vouch History", color=0x4fc3f7)
    for msg, time, s_id, g_id in history:
        try: u = await bot.fetch_user(s_id); s_name = u.name
        except: s_name = f"User({s_id})"
        g = bot.get_guild(g_id); g_name = g.name if g else "Private Server"
        embed.add_field(name=f"To {s_name} in {g_name}", value=f"*{time}*\n> {msg}", inline=False)
    try: await ctx.author.send(embed=embed); await ctx.send("📬 Sent to DMs!")
    except: await ctx.send("❌ Please open your DMs.")

# ============================================================================
# ✍️ MAIN COMMANDS & ADMIN
# ============================================================================
@bot.command()
async def vouch(ctx, seller: discord.Member, *, message: str):
    if seller.id == ctx.author.id:
        await ctx.send("❌ Self-vouching disabled."); return
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM global_blacklist WHERE user_id = %s', (seller.id,))
    if cursor.fetchone():
        await ctx.send("❌ Blocked: Seller is blacklisted."); cursor.close(); conn.close(); return
    cursor.execute('INSERT INTO vouches (seller_id, customer_id, customer_name, content, timestamp, origin_server_id) VALUES (%s, %s, %s, %s, %s, %s)', (seller.id, ctx.author.id, ctx.author.name, message, datetime.now().strftime("%Y-%m-%d %H:%M"), ctx.guild.id))
    conn.commit(); cursor.close(); conn.close()
    await ctx.send(embed=discord.Embed(title="✨ Vouch Recorded", color=0x81c784))

@bot.command()
async def authorize(ctx, server_id: int, duration: str):
    if ctx.author.id != ADMIN_USER_ID: return 
    wait_time = parse_duration(duration)
    if not wait_time: return
    new_expiry = datetime.now() + wait_time
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute('INSERT INTO subscriptions (server_id, expiry_date) VALUES (%s, %s) ON CONFLICT (server_id) DO UPDATE SET expiry_date = EXCLUDED.expiry_date', (server_id, new_expiry))
    conn.commit(); cursor.close(); conn.close()
    await ctx.send(f"✅ Authorized {server_id} until {new_expiry.strftime('%Y-%m-%d %H:%M:%S')}")

# [KEEP OTHER COMMANDS: backup, restore, import_vouches, clearprofile]
# Note: Ensure they use get_db_connection() style!

bot.run(DISCORD_BOT_TOKEN)
