import discord
from discord.ext import commands
import psycopg2 
import os
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
import threading

# ============================================================================
# 🔑 CONFIG & DATABASE
# ============================================================================
DISCORD_BOT_TOKEN = os.getenv('DISCORD_TOKEN')
ADMIN_USER_ID = 1378864322687537262  # <--- YOUR DISCORD USER ID
WEBHOOK_SECRET = "MY_SUPER_SECRET_KEY_123" 

DB_URL = os.getenv('DATABASE_URL')
conn = psycopg2.connect(DB_URL)
cursor = conn.cursor()

# Create tables
cursor.execute('CREATE TABLE IF NOT EXISTS vouches (id SERIAL PRIMARY KEY, seller_id BIGINT, customer_id BIGINT, customer_name TEXT, content TEXT, timestamp TEXT, origin_server_id BIGINT)')
cursor.execute('CREATE TABLE IF NOT EXISTS subscriptions (server_id BIGINT PRIMARY KEY, expiry_date TIMESTAMP)')
conn.commit()

# ============================================================================
# 🌐 WEBHOOK SERVER (FOR WEBSITE AUTOMATION)
# ============================================================================
app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    if data.get("secret") != WEBHOOK_SECRET:
        return jsonify({"status": "unauthorized"}), 403

    server_id = data.get("server_id")
    # CHANGED TO MINUTES FOR TESTING
    minutes = data.get("minutes", 5) 

    new_expiry = datetime.now() + timedelta(minutes=minutes)
    cursor.execute('''
        INSERT INTO subscriptions (server_id, expiry_date)
        VALUES (%s, %s)
        ON CONFLICT (server_id) DO UPDATE SET expiry_date = EXCLUDED.expiry_date
    ''', (server_id, new_expiry))
    conn.commit()

    return jsonify({"status": "success", "expiry": str(new_expiry)}), 200

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

# ============================================================================
# 🤖 DISCORD BOT
# ============================================================================
intents = discord.Intents.default()
intents.message_content = True 
bot = commands.Bot(command_prefix="!", intents=intents)

def check_subscription(server_id):
    cursor.execute('SELECT expiry_date FROM subscriptions WHERE server_id = %s', (server_id,))
    result = cursor.fetchone()
    if result:
        expiry = result[0]
        # Compare current time to expiry time
        if datetime.now() < expiry:
            return True
    return False

@bot.event
async def on_ready():
    print(f'🛡️ Vouch Vault (5-MIN TEST MODE) is Online')

# --- QUICK TEST COMMAND: !test5 ---
@bot.command()
async def test5(ctx):
    if ctx.author.id != ADMIN_USER_ID:
        return

    # Adds exactly 5 minutes of premium to the current server
    new_expiry = datetime.now() + timedelta(minutes=5)
    cursor.execute('''
        INSERT INTO subscriptions (server_id, expiry_date)
        VALUES (%s, %s)
        ON CONFLICT (server_id) DO UPDATE SET expiry_date = EXCLUDED.expiry_date
    ''', (ctx.guild.id, new_expiry))
    conn.commit()

    await ctx.send(f"🕒 **Test Activated!** This server has Premium for **5 minutes**.\nExpires at: `{new_expiry.strftime('%H:%M:%S')}`")

# --- VOUCH COMMAND ---
@bot.command()
async def vouch(ctx, seller: discord.Member, *, message: str):
    if not check_subscription(ctx.guild.id):
        await ctx.send("🔒 **Subscription Expired.** $4.99/mo required. Buy here: `[Your Website]`")
        return
    
    # (Original vouch logic)
    time_now = datetime.now().strftime("%Y-%m-%d %H:%M")
    cursor.execute('INSERT INTO vouches (seller_id, customer_id, customer_name, content, timestamp, origin_server_id) VALUES (%s, %s, %s, %s, %s, %s)', (seller.id, ctx.author.id, ctx.author.name, message, time_now, ctx.guild.id))
    conn.commit()
    await ctx.send("✨ Vouch Recorded!")

# --- PROFILE COMMAND ---
@bot.command()
async def profile(ctx, user: discord.Member = None):
    if not check_subscription(ctx.guild.id):
        await ctx.send("🔒 **Subscription Expired.** $4.99/mo required. Buy here: `[Your Website]`")
        return
    
    user = user or ctx.author
    cursor.execute('SELECT customer_name, content, timestamp FROM vouches WHERE seller_id = %s', (user.id,))
    all_vouches = cursor.fetchall()
    await ctx.send(f"🛡️ Profile: {user.name} has {len(all_vouches)} vouches.")

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    bot.run(DISCORD_BOT_TOKEN)
