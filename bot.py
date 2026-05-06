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
    try:
        conn = get_db_connection(); cursor = conn.cursor()
        
        # --- THE AUTO-FIX LINE: This deletes the old broken table format ---
        cursor.execute('DROP TABLE IF EXISTS server_backups') 
        
        # Now we rebuild all tables correctly
        cursor.execute('CREATE TABLE IF NOT EXISTS vouches (id SERIAL PRIMARY KEY, seller_id BIGINT, customer_id BIGINT, customer_name TEXT, content TEXT, timestamp TEXT, origin_server_id BIGINT)')
        cursor.execute('CREATE TABLE IF NOT EXISTS subscriptions (server_id BIGINT PRIMARY KEY, expiry_date TIMESTAMP)')
        cursor.execute('CREATE TABLE IF NOT EXISTS server_backups (server_id BIGINT PRIMARY KEY, blueprint TEXT, backup_date TIMESTAMP)')
        cursor.execute('CREATE TABLE IF NOT EXISTS global_blacklist (user_id BIGINT PRIMARY KEY, reason TEXT, date_flagged TIMESTAMP)')
        
        conn.commit(); cursor.close(); conn.close()
        print(f'✅ Vouch Vault PRO Online and Database Reset Successful')
    except Exception as e:
        print(f"❌ Startup Database Error: {e}")

# ============================================================================
# 🛠️ ADMIN TOOLS (EXTEKK ONLY)
# ============================================================================

@bot.command()
async def botstatus(ctx):
    if ctx.author.id != ADMIN_USER_ID: return
    try:
        conn = get_db_connection(); cursor = conn.cursor()
        cursor.execute('SELECT 1'); cursor.close(); conn.close()
        db_s = "✅ Connected"
    except: db_s = "❌ Failed"
    embed = discord.Embed(title="⚙️ SYSTEM STATUS", color=0x4fc3f7)
    embed.add_field(name="Database", value=db_s); embed.add_field(name="Servers", value=len(bot.guilds))
    await ctx.send(embed=embed)

@bot.command()
async def simulate(ctx, state: str):
    if ctx.author.id != ADMIN_USER_ID: return
    conn = get_db_connection(); cursor = conn.cursor()
    new_expiry = datetime.now() + timedelta(minutes=10) if state.lower() == "premium" else datetime.now() - timedelta(days=1)
    cursor.execute('INSERT INTO subscriptions (server_id, expiry_date) VALUES (%s, %s) ON CONFLICT (server_id) DO UPDATE SET expiry_date = EXCLUDED.expiry_date', (ctx.guild.id, new_expiry))
    conn.commit(); cursor.close(); conn.close()
    await ctx.send(f"🔄 Mode set to: **{state.upper()}**")

# ============================================================================
# 🚨 SECURITY (FLAG/UNFLAG)
# ============================================================================

@bot.command()
async def flag(ctx, user: discord.User, *, reason: str = "No reason provided"):
    is_adm = ctx.author.guild_permissions.administrator if ctx.guild else False
    if ctx.author.id != ADMIN_USER_ID and ctx.author.id not in TESTER_IDS and not is_adm:
        await ctx.send("❌ Access Denied."); return
    if not is_premium(ctx.guild.id) and ctx.author.id not in TESTER_IDS:
        await ctx.send("🔒 Premium Required."); return

    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute('INSERT INTO global_blacklist (user_id, reason, date_flagged) VALUES (%s, %s, %s) ON CONFLICT (user_id) DO UPDATE SET reason = EXCLUDED.reason', (user.id, f"Flagged by {ctx.guild.name}: {reason}", datetime.now()))
    conn.commit(); cursor.close(); conn.close()

    embed = discord.Embed(title="🚨 GLOBAL BLACKLIST UPDATED", color=0xFF0000)
    embed.add_field(name="User", value=f"{user.name} (`{user.id}`)").add_field(name="Reason", value=f"```{reason}```", inline=False)
    await ctx.send(embed=embed)

@bot.command()
async def unflag(ctx, user: discord.User):
    if ctx.author.id != ADMIN_USER_ID: return
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute('DELETE FROM global_blacklist WHERE user_id = %s', (user.id,))
    conn.commit(); cursor.close(); conn.close()
    await ctx.send(embed=discord.Embed(title="✅ UNFLAGGED", description=f"{user.name} removed from blacklist.", color=0x00FF00))

# ============================================================================
# 📊 USER COMMANDS (PROFILE/VOUCH/HISTORY)
# ============================================================================

@bot.command()
async def profile(ctx, user: discord.Member = None):
    if not is_premium(ctx.guild.id) and ctx.author.id not in TESTER_IDS:
        await ctx.send("🔒 Premium Required."); return
    user = user or ctx.author
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute('SELECT reason FROM global_blacklist WHERE user_id = %s', (user.id,))
    bad = cursor.fetchone()
    if bad:
        await ctx.send(embed=discord.Embed(title="⚠️ BLACKLISTED", description=f"WARNING: {user.name} is a flagged scammer!\nReason: {bad[0]}", color=0xFF0000))
        cursor.close(); conn.close(); return

    cursor.execute('SELECT content FROM vouches WHERE seller_id = %s', (user.id,))
    recv = cursor.fetchall()
    cursor.execute('SELECT COUNT(*) FROM vouches WHERE customer_id = %s', (user.id,))
    given = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(DISTINCT origin_server_id) FROM vouches WHERE seller_id = %s', (user.id,))
    reach = cursor.fetchone()[0]
    cursor.close(); conn.close()

    rank = "Legendary 💎" if given > 50 else "Elite 🎖️" if given > 20 else "Verified ✅" if given > 5 else "Newcomer"
    embed = discord.Embed(title=f"🛡️ Profile: {user.name}", color=0x4fc3f7)
    embed.add_field(name="🤝 STATUS", value=f"{rank} ({given} given)").add_field(name="💰 SELLER", value=f"{len(recv)} vouches ({reach} servers)")

    if recv:
        async with ctx.typing():
            try:
                p = f"Professional 2-sentence summary of reputation: {' '.join([v[0] for v in recv])[:2000]}"
                c = ai_client.chat.completions.create(messages=[{"role":"user","content":p}], model="llama-3.1-8b-instant", temperature=0.1)
                embed.description = f"**AI INSIGHT:**\n*{c.choices[0].message.content.strip()}*"
            except: pass
    await ctx.send(embed=embed)

@bot.command()
async def vouch(ctx, seller: discord.Member, *, message: str):
    if seller.id == ctx.author.id:
        await ctx.send("❌ Cannot vouch for yourself."); return
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM global_blacklist WHERE user_id = %s', (seller.id,))
    if cursor.fetchone():
        await ctx.send("❌ Blocked: Seller is blacklisted."); cursor.close(); conn.close(); return
    cursor.execute('INSERT INTO vouches (seller_id, customer_id, customer_name, content, timestamp, origin_server_id) VALUES (%s, %s, %s, %s, %s, %s)', (seller.id, ctx.author.id, ctx.author.name, message, datetime.now().strftime("%Y-%m-%d %H:%M"), ctx.guild.id))
    conn.commit(); cursor.close(); conn.close()
    await ctx.send(embed=discord.Embed(title="✨ Vouch Recorded", color=0x81c784))

@bot.command()
async def myvouches(ctx):
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute('SELECT content, timestamp, seller_id FROM vouches WHERE customer_id = %s ORDER BY id DESC LIMIT 10', (ctx.author.id,))
    history = cursor.fetchall(); cursor.close(); conn.close()
    if not history:
        await ctx.send("❓ No history found."); return
    embed = discord.Embed(title="📄 Your Vouch History", color=0x4fc3f7)
    for m, t, s in history: embed.add_field(name=f"To User ID: {s} ({t})", value=m, inline=False)
    try: await ctx.author.send(embed=embed); await ctx.send("📬 Check DMs!")
    except: await ctx.send("❌ DMs closed.")

# ============================================================================
# 🏗️ BACKUP & RESTORE
# ============================================================================

@bot.command()
async def backup(ctx):
    if not is_premium(ctx.guild.id) and ctx.author.id not in TESTER_IDS:
        await ctx.send("🔒 Premium Required."); return
    try:
        roles = [{"name": r.name, "color": r.color.value} for r in ctx.guild.roles if not r.is_default() and not r.managed]
        cats = []
        for c in ctx.guild.categories:
            cats.append({"name": c.name, "channels": [{"name": ch.name, "type": str(ch.type)} for ch in ch.channels]})
        blueprint = json.dumps({"roles": roles, "categories": cats})
        conn = get_db_connection(); cursor = conn.cursor()
        cursor.execute('INSERT INTO server_backups (server_id, blueprint, backup_date) VALUES (%s, %s, %s) ON CONFLICT (server_id) DO UPDATE SET blueprint = EXCLUDED.blueprint', (ctx.guild.id, blueprint, datetime.now()))
        conn.commit(); cursor.close(); conn.close()
        await ctx.send("✅ Server structure backed up!")
    except Exception as e: await ctx.send(f"❌ Error: {e}")

@bot.command()
async def restore(ctx, old_id: int):
    if ctx.author.id != ADMIN_USER_ID: return
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute('SELECT blueprint FROM server_backups WHERE server_id = %s', (old_id,))
    row = cursor.fetchone(); cursor.close(); conn.close()
    if not row:
        await ctx.send("❓ Backup not found."); return
    data = json.loads(row[0])
    await ctx.send("🚀 Restoring...")
    for r in data['roles']:
        try: await ctx.guild.create_role(name=r['name'], color=discord.Color(r['color']))
        except: pass
    for c in data['categories']:
        nc = await ctx.guild.create_category(c['name'])
        for ch in c['channels']:
            if ch['type'] == 'text': await ctx.guild.create_text_channel(ch['name'], category=nc)
    await ctx.send("✅ Restore complete.")

# ============================================================================
# 👑 SYSTEM ADMIN
# ============================================================================
@bot.command()
async def authorize(ctx, server_id: int, duration: str):
    if ctx.author.id != ADMIN_USER_ID: return 
    wait = parse_duration(duration)
    if not wait: return
    exp = datetime.now() + wait
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute('INSERT INTO subscriptions (server_id, expiry_date) VALUES (%s, %s) ON CONFLICT (server_id) DO UPDATE SET expiry_date = EXCLUDED.expiry_date', (server_id, exp))
    conn.commit(); cursor.close(); conn.close()
    await ctx.send(f"✅ Authorized {server_id}")

@bot.command()
async def import_vouches(ctx, channel: discord.TextChannel, seller: discord.Member):
    if not is_premium(ctx.guild.id): return
    if ctx.author.id != ADMIN_USER_ID: return
    count = 0
    conn = get_db_connection(); cursor = conn.cursor()
    async for m in channel.history(limit=100):
        if m.author.bot or m.author.id == seller.id: continue
        if "vouch" in m.content.lower() or len(m.attachments) > 0:
            cursor.execute('INSERT INTO vouches (seller_id, customer_id, customer_name, content, timestamp, origin_server_id) VALUES (%s, %s, %s, %s, %s, %s)', (seller.id, m.author.id, m.author.name, m.content or "[Image]", m.created_at.strftime("%Y-%m-%d"), ctx.guild.id))
            count += 1
    conn.commit(); cursor.close(); conn.close()
    await ctx.send(f"✅ Imported {count} vouches.")

@bot.command()
async def clearprofile(ctx, user_id: int):
    if ctx.author.id != ADMIN_USER_ID: return 
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute('DELETE FROM vouches WHERE seller_id = %s', (user_id,))
    conn.commit(); cursor.close(); conn.close()
    await ctx.send(f"🧹 Profile `{user_id}` Cleared.")

bot.run(DISCORD_BOT_TOKEN)
