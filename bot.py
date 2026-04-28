import discord
from discord.ext import commands
import psycopg2 
import os
import re 
from datetime import datetime, timedelta
from groq import Groq # Added for AI Insight

# ============================================================================
# 👑 ADMIN & TESTER PANEL
# ============================================================================
ADMIN_USER_ID = 882005122144669707 

TESTER_IDS = [
    882005122144669707, # You
]

# ============================================================================
# 🔑 CONFIG & DATABASE
# ============================================================================
DISCORD_BOT_TOKEN = os.getenv('DISCORD_TOKEN')
GROQ_API_KEY = os.getenv('GROQ_KEY') # Added for AI
DB_URL = os.getenv('DATABASE_URL')

conn = psycopg2.connect(DB_URL)
cursor = conn.cursor()

# Initialize Groq Client
ai_client = Groq(api_key=GROQ_API_KEY)

# Create tables
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
    print(f'🛡️ Vouch Vault (AI-INSIGHT MODE) is Online')

# ============================================================================
# 👑 ADMIN COMMANDS
# ============================================================================

@bot.command()
async def authorize(ctx, server_id: int, duration: str):
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
    
    # 1. Fetch ALL vouches for the AI to analyze
    cursor.execute('SELECT customer_name, content, timestamp FROM vouches WHERE seller_id = %s', (user.id,))
    all_vouches = cursor.fetchall()
    vouch_count = len(all_vouches)

    if vouch_count == 0:
        await ctx.send(f"🛡️ {user.name} has no vouches in the Vault yet.")
        return

    async with ctx.typing():
        try:
            # 2. Prepare the text for Groq AI
            vouch_bundle = " ".join([v[1] for v in all_vouches])
            
            prompt = f"""
            Based on these customer reviews, write a 2-sentence professional summary 
            of this seller's reputation. Focus on their strengths (speed, quality, etc).
            Reviews: {vouch_bundle[:2000]} 
            """
            
            chat_completion = ai_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="llama-3.1-8b-instant",
                temperature=0.3,
            )
            ai_summary = chat_completion.choices[0].message.content.strip()

            # 3. Create the Embed with AI Insight
            embed = discord.Embed(
                title=f"🛡️ Reputation Profile: {user.name}", 
                description=f"**AI INSIGHT:**\n*{ai_summary}*",
                color=0x4fc3f7
            )
            
            embed.add_field(name="📈 Total Reputation", value=f"**{vouch_count} Verified Vouches**", inline=False)

            # Show the 5 most recent vouches
            recent = all_vouches[-5:]
            for name, msg, time in reversed(recent):
                embed.add_field(name=f"By {name} on {time}", value=msg, inline=False)

            embed.set_thumbnail(url=user.avatar.url if user.avatar else None)
            embed.set_footer(text="Reputation Analyzed by The Silk Labz AI Engine")
            
            await ctx.send(embed=embed)

        except Exception as e:
            await ctx.send(f"❌ **Error generating AI profile:** {str(e)}")

bot.run(DISCORD_BOT_TOKEN)
