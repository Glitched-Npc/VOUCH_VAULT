import discord
from discord.ext import commands
import psycopg2 
import os
import re 
from datetime import datetime, timedelta
from groq import Groq 

# ============================================================================
# 👑 ADMIN & TESTER PANEL
# ============================================================================
ADMIN_USER_ID = 882005122144669707 
TESTER_IDS = [882005122144669707]

# ============================================================================
# 🔑 CONFIG & DATABASE
# ============================================================================
DISCORD_BOT_TOKEN = os.getenv('DISCORD_TOKEN')
GROQ_API_KEY = os.getenv('GROQ_KEY') 
DB_URL = os.getenv('DATABASE_URL')

conn = psycopg2.connect(DB_URL)
cursor = conn.cursor()
ai_client = Groq(api_key=GROQ_API_KEY)

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
cursor.execute('CREATE TABLE IF NOT EXISTS subscriptions (server_id BIGINT PRIMARY KEY, expiry_date TIMESTAMP)')
conn.commit()

# ============================================================================
# 🛠️ HELPERS
# ============================================================================
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
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f'🛡️ Vouch Vault (PRO MIGRATION) is Online')

# ============================================================================
# 📥 MIGRATION COMMAND: !import #channel @Seller
# ============================================================================
@bot.command(name="import_vouches", aliases=["import"])
async def import_vouches(ctx, channel: discord.TextChannel, seller: discord.Member):
    """Imports the last 100 messages from a channel as vouches for a seller"""
    
    # 1. Check if the person typing is the actual owner
    if ctx.author.id != ADMIN_USER_ID:
        await ctx.send(f"❌ **Unauthorized:** Your ID ({ctx.author.id}) does not match the Admin ID.")
        return

    await ctx.send(f"⏳ **Scanning {channel.mention}...** This reads the last 100 messages. Please wait.")
    
    count = 0
    keywords = ["vouch", "legit", "fast", "+1", "delivered", "received", "thanks", "bought", "🔥", "✅"]

    try:
        async for message in channel.history(limit=100):
            # Skip bot and skip the seller themselves
            if message.author.bot or message.author.id == seller.id:
                continue

            content_lower = message.content.lower()
            
            # Check if message is a vouch (has keywords, length, or an image)
            is_vouch = (
                any(key in content_lower for key in keywords) or 
                len(message.content) > 10 or 
                len(message.attachments) > 0
            )

            if is_vouch:
                time_str = message.created_at.strftime("%Y-%m-%d %H:%M")
                
                # Save to PostgreSQL
                cursor.execute('''
                    INSERT INTO vouches (seller_id, customer_id, customer_name, content, timestamp, origin_server_id) 
                    VALUES (%s, %s, %s, %s, %s, %s)
                ''', (seller.id, message.author.id, message.author.name, message.content or "[Image/No Text]", time_str, ctx.guild.id))
                count += 1

        conn.commit()
        await ctx.send(f"✅ **Migration Complete!** Added **{count}** vouches for {seller.mention} to the Vault.")
    
    except Exception as e:
        await ctx.send(f"❌ **Critical Error:** {str(e)}")

# ============================================================================
# 👑 ADMIN COMMANDS
# ============================================================================
@bot.command()
async def authorize(ctx, server_id: int, duration: str):
    if ctx.author.id != ADMIN_USER_ID: return 
    time_diff = parse_duration(duration)
    if time_diff is None:
        await ctx.send("❌ Use `10m`, `1h`, `30d`, etc.")
        return
    new_expiry = datetime.now() + time_diff
    cursor.execute('INSERT INTO subscriptions (server_id, expiry_date) VALUES (%s, %s) ON CONFLICT (server_id) DO UPDATE SET expiry_date = EXCLUDED.expiry_date', (server_id, new_expiry))
    conn.commit()
    await ctx.send(f"✅ **Authorized!** Server `{server_id}` until `{new_expiry}`")

@bot.command()
async def clearprofile(ctx, user_id: int):
    if ctx.author.id != ADMIN_USER_ID: return 
    cursor.execute('DELETE FROM vouches WHERE seller_id = %s', (user_id,))
    conn.commit()
    await ctx.send(f"🧹 Cleared all vouches for `{user_id}`.")

# ============================================================================
# ✍️ MAIN COMMANDS
# ============================================================================
@bot.command()
async def vouch(ctx, seller: discord.Member, *, message: str):
    if not is_authorized(ctx.author.id, ctx.guild.id):
        await ctx.send("🔒 **Subscription Expired.** $3.99/mo required. Contact **The Silk Road**.")
        return
    if seller.id == ctx.author.id:
        await ctx.send("❌ Self-vouching is disabled.")
        return

    time_now = datetime.now().strftime("%Y-%m-%d %H:%M")
    cursor.execute('INSERT INTO vouches (seller_id, customer_id, customer_name, content, timestamp, origin_server_id) VALUES (%s, %s, %s, %s, %s, %s)', (seller.id, ctx.author.id, ctx.author.name, message, time_now, ctx.guild.id))
    conn.commit()
    await ctx.send(embed=discord.Embed(title="✨ Vouch Recorded", description=f"```{message}```", color=0x81c784))

    # AI Thank You
    try:
        thanks_prompt = f"System: Friendly AI. Instruction: One-sentence thank you to {ctx.author.name} for vouching for {seller.name}."
        thanks_completion = ai_client.chat.completions.create(messages=[{"role": "user", "content": thanks_prompt}], model="llama-3.1-8b-instant", temperature=0.7)
        await ctx.send(embed=discord.Embed(description=f"💬 **AI:** {thanks_completion.choices[0].message.content.strip()}", color=0x4fc3f7))
    except: pass

@bot.command()
async def profile(ctx, user: discord.Member = None):
    if not is_authorized(ctx.author.id, ctx.guild.id):
        await ctx.send("🔒 **Subscription Expired.**")
        return
    user = user or ctx.author
    cursor.execute('SELECT customer_name, content, timestamp FROM vouches WHERE seller_id = %s', (user.id,))
    all_vouches = cursor.fetchall()
    vouch_count = len(all_vouches)
    if vouch_count == 0:
        await ctx.send("🛡️ No vouches found.")
        return

    cursor.execute('SELECT COUNT(DISTINCT origin_server_id) FROM vouches WHERE seller_id = %s', (user.id,))
    unique_servers = cursor.fetchone()[0]
    trust_score = min((unique_servers * 10) + vouch_count, 100)

    async with ctx.typing():
        try:
            vouch_bundle = " ".join([v[1] for v in all_vouches])
            prompt = f"System: Professional analyst. Instruction: STRICT 2-sentence summary of seller reputation. No intro. Reviews: {vouch_bundle[:2000]}"
            chat = ai_client.chat.completions.create(messages=[{"role": "user", "content": prompt}], model="llama-3.1-8b-instant", temperature=0.1)
            ai_summary = chat.choices[0].message.content.strip()

            embed = discord.Embed(title=f"🛡️ Profile: {user.name}", description=f"**AI INSIGHT:**\n*{ai_summary}*", color=0x4fc3f7)
            embed.add_field(name="🛡️ Trust Score", value=f"**{trust_score}/100**", inline=True)
            embed.add_field(name="🌐 Global Reach", value=f"**{unique_servers}** Servers", inline=True)
            embed.add_field(name="📈 Total", value=f"**{vouch_count}** Vouches", inline=True)
            for name, msg, time in reversed(all_vouches[-5:]):
                embed.add_field(name=f"✅ {name} ({time})", value=msg, inline=False)
            embed.set_footer(text="Verified & Analyzed by The Silk Road AI")
            await ctx.send(embed=embed)
        except Exception as e: await ctx.send(f"❌ Error: {str(e)}")

bot.run(DISCORD_BOT_TOKEN)
