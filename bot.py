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
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT expiry_date FROM subscriptions WHERE server_id = %s', (server_id,))
        result = cursor.fetchone()
        cursor.close()
        conn.close()
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
intents.members = True # REQUIRED for the new flag command

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS vouches (id SERIAL PRIMARY KEY, seller_id BIGINT, customer_id BIGINT, customer_name TEXT, content TEXT, timestamp TEXT, origin_server_id BIGINT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS subscriptions (server_id BIGINT PRIMARY KEY, expiry_date TIMESTAMP)')
    cursor.execute('CREATE TABLE IF NOT EXISTS server_backups (server_id BIGINT PRIMARY KEY, blueprint JSONB, backup_date TIMESTAMP)')
    cursor.execute('CREATE TABLE IF NOT EXISTS global_blacklist (user_id BIGINT PRIMARY KEY, reason TEXT, date_flagged TIMESTAMP)')
    conn.commit()
    cursor.close()
    conn.close()
    print(f'✅ Vouch Vault Security Engine Online')

# ============================================================================
# 🚨 GLOBAL SECURITY (ADMIN ONLY)
# ============================================================================

@bot.command()
async def flag(ctx, user: discord.User, *, reason: str = "No reason provided"):
    if ctx.author.id != ADMIN_USER_ID: return
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO global_blacklist (user_id, reason, date_flagged) 
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id) DO UPDATE SET reason = EXCLUDED.reason
    ''', (user.id, reason, datetime.now()))
    conn.commit()
    cursor.close()
    conn.close()

    embed = discord.Embed(title="🚨 GLOBAL BLACKLIST UPDATED", color=0xFF0000)
    embed.add_field(name="User", value=f"{user.name} (`{user.id}`)")
    embed.add_field(name="Reason", value=f"```{reason}```", inline=False)
    await ctx.send(embed=embed)

@bot.command()
async def unflag(ctx, user: discord.User):
    if ctx.author.id != ADMIN_USER_ID: return
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM global_blacklist WHERE user_id = %s', (user.id,))
    conn.commit()
    cursor.close()
    conn.close()
    await ctx.send(f"✅ User **{user.name}** cleared from blacklist.")

# ============================================================================
# 📊 PROFILE & AI INSIGHT
# ============================================================================

@bot.command()
async def profile(ctx, user: discord.Member = None):
    if not is_authorized(ctx.author.id, ctx.guild.id):
        await ctx.send("🔒 Subscription Required.")
        return
    user = user or ctx.author
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Blacklist Check
    cursor.execute('SELECT reason, date_flagged FROM global_blacklist WHERE user_id = %s', (user.id,))
    blacklisted = cursor.fetchone()
    if blacklisted:
        embed = discord.Embed(title="⚠️ GLOBAL SCAMMER ALERT ⚠️", description=f"**WARNING:** {user.mention} is flagged!", color=0xFF0000)
        embed.add_field(name="Reason", value=f"```{blacklisted[0]}```")
        await ctx.send(embed=embed)
        cursor.close(); conn.close()
        return

    # 2. Vouch Data
    cursor.execute('SELECT customer_name, content, timestamp FROM vouches WHERE seller_id = %s', (user.id,))
    all_vouches = cursor.fetchall()
    vouch_count = len(all_vouches)
    cursor.execute('SELECT COUNT(DISTINCT origin_server_id) FROM vouches WHERE seller_id = %s', (user.id,))
    unique_servers = cursor.fetchone()[0]
    cursor.close(); conn.close()

    if vouch_count == 0:
        await ctx.send("🛡️ No vouches found.")
        return

    async with ctx.typing():
        try:
            vouch_bundle = " ".join([v[1] for v in all_vouches])
            prompt = f"System: Analyst. Instruction: STRICT 2-sentence summary of seller reputation. Reviews: {vouch_bundle[:2000]}"
            chat = ai_client.chat.completions.create(messages=[{"role": "user", "content": prompt}], model="llama-3.1-8b-instant", temperature=0.1)
            ai_summary = chat.choices[0].message.content.strip()

            trust_score = min((unique_servers * 10) + vouch_count, 100)
            embed = discord.Embed(title=f"🛡️ Profile: {user.name}", description=f"**AI INSIGHT:**\n*{ai_summary}*", color=0x4fc3f7)
            embed.add_field(name="🛡️ Trust Score", value=f"**{trust_score}/100**", inline=True)
            embed.add_field(name="🌐 Global Reach", value=f"**{unique_servers}** Servers", inline=True)
            for name, msg, time in reversed(all_vouches[-5:]):
                embed.add_field(name=f"✅ {name} ({time})", value=msg, inline=False)
            await ctx.send(embed=embed)
        except Exception as e: await ctx.send(f"❌ AI Error: {str(e)}")

# ============================================================================
# ✍️ VOUCH & IMPORT
# ============================================================================

@bot.command()
async def vouch(ctx, seller: discord.Member, *, message: str):
    if not is_authorized(ctx.author.id, ctx.guild.id):
        await ctx.send("🔒 Subscription Required.")
        return
    if seller.id == ctx.author.id:
        await ctx.send("❌ Self-vouching disabled.")
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM global_blacklist WHERE user_id = %s', (seller.id,))
    if cursor.fetchone():
        await ctx.send("❌ **Blocked:** This user is blacklisted for scamming.")
        cursor.close(); conn.close()
        return

    cursor.execute('INSERT INTO vouches (seller_id, customer_id, customer_name, content, timestamp, origin_server_id) VALUES (%s, %s, %s, %s, %s, %s)', (seller.id, ctx.author.id, ctx.author.name, message, datetime.now().strftime("%Y-%m-%d %H:%M"), ctx.guild.id))
    conn.commit(); cursor.close(); conn.close()

    await ctx.send(embed=discord.Embed(title="✨ Vouch Recorded", description=f"```{message}```", color=0x81c784))
    try:
        thanks_prompt = f"Friendly AI one-sentence thank you to {ctx.author.name} for vouching for {seller.name}."
        chat = ai_client.chat.completions.create(messages=[{"role": "user", "content": thanks_prompt}], model="llama-3.1-8b-instant", temperature=0.7)
        await ctx.send(embed=discord.Embed(description=f"💬 **AI:** {chat.choices[0].message.content.strip()}", color=0x4fc3f7))
    except: pass

@bot.command()
async def import_vouches(ctx, channel: discord.TextChannel, seller: discord.Member):
    if ctx.author.id != ADMIN_USER_ID: return
    await ctx.send(f"⏳ Scanning {channel.mention}...")
    count = 0
    keywords = ["vouch", "legit", "fast", "+1", "delivered", "thanks", "✅"]
    conn = get_db_connection(); cursor = conn.cursor()
    async for message in channel.history(limit=100):
        if message.author.bot or message.author.id == seller.id: continue
        if any(key in message.content.lower() for key in keywords) or len(message.attachments) > 0:
            cursor.execute('INSERT INTO vouches (seller_id, customer_id, customer_name, content, timestamp, origin_server_id) VALUES (%s, %s, %s, %s, %s, %s)', (seller.id, message.author.id, message.author.name, message.content or "[Image]", message.created_at.strftime("%Y-%m-%d %H:%M"), ctx.guild.id))
            count += 1
    conn.commit(); cursor.close(); conn.close()
    await ctx.send(f"✅ Imported {count} vouches.")

# ============================================================================
# 🔄 BACKUP / RESTORE / AUTHORIZE
# ============================================================================

@bot.command()
async def backup(ctx):
    if not is_authorized(ctx.author.id, ctx.guild.id):
        await ctx.send("🔒 Premium Required.")
        return
    roles = [{"name": r.name, "color": r.color.value} for r in ctx.guild.roles if not r.is_default() and not r.managed]
    categories = []
    for category in ctx.guild.categories:
        cat_data = {"name": category.name, "channels": [{"name": c.name, "type": str(c.type)} for c in category.channels]}
        categories.append(cat_data)
    blueprint = json.dumps({"roles": roles, "categories": categories})
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute('INSERT INTO server_backups (server_id, blueprint, backup_date) VALUES (%s, %s, %s) ON CONFLICT (server_id) DO UPDATE SET blueprint = EXCLUDED.blueprint, backup_date = EXCLUDED.backup_date', (ctx.guild.id, blueprint, datetime.now()))
    conn.commit(); cursor.close(); conn.close()
    await ctx.send("✅ **Backup Saved to Cloud!**")

@bot.command()
async def restore(ctx, old_server_id: int):
    if ctx.author.id != ADMIN_USER_ID: return
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute('SELECT blueprint FROM server_backups WHERE server_id = %s', (old_server_id,))
    row = cursor.fetchone()
    cursor.close(); conn.close()
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
    await ctx.send("✅ **Restoration Complete.**")

@bot.command()
async def authorize(ctx, server_id: int, duration: str):
    if ctx.author.id != ADMIN_USER_ID: return 
    wait_time = parse_duration(duration)
    if not wait_time: return
    new_expiry = datetime.now() + wait_time
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute('INSERT INTO subscriptions (server_id, expiry_date) VALUES (%s, %s) ON CONFLICT (server_id) DO UPDATE SET expiry_date = EXCLUDED.expiry_date', (server_id, new_expiry))
    conn.commit(); cursor.close(); conn.close()
    await ctx.send(f"✅ Authorized {server_id} until {new_expiry.strftime('%Y-%m-%d')}")

bot.run(DISCORD_BOT_TOKEN)
