# ============================================================================
# ✍️ VOUCH COMMAND
# ============================================================================
@bot.command()
async def vouch(ctx, seller: discord.Member, *, message: str):
    if not is_authorized(ctx.author.id, ctx.guild.id):
        await ctx.send("🔒 **Subscription Expired.** $6.99/mo required. Contact **The Silk Road**.")
        return

    if seller.id == ctx.author.id:
        await ctx.send("❌ You cannot vouch for yourself."); return

    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM global_blacklist WHERE user_id = %s', (seller.id,))
    if cursor.fetchone():
        await ctx.send("❌ **Blocked:** Seller is blacklisted."); cursor.close(); conn.close(); return

    # We save the IDs. Names will be looked up live to stay up-to-date.
    cursor.execute('''
        INSERT INTO vouches (seller_id, customer_id, customer_name, content, timestamp, origin_server_id) 
        VALUES (%s, %s, %s, %s, %s, %s)
    ''', (seller.id, ctx.author.id, ctx.author.name, message, datetime.now().strftime("%Y-%m-%d %H:%M"), ctx.guild.id))
    
    conn.commit(); cursor.close(); conn.close()
    await ctx.send(embed=discord.Embed(title="✨ Vouch Recorded", description=f"You vouched for **{seller.name}**", color=0x81c784))

# ============================================================================
# 📄 MEMBER COMMAND: !myvouches (NAMES INSTEAD OF IDs)
# ============================================================================
@bot.command()
async def myvouches(ctx):
    """Sends a DM with history using actual Names instead of numeric IDs"""
    if not is_authorized(ctx.author.id, ctx.guild.id):
        await ctx.send("🔒 Subscription Required."); return

    conn = get_db_connection(); cursor = conn.cursor()
    # We pull the content, time, seller_id, and origin_server_id
    cursor.execute('SELECT content, timestamp, seller_id, origin_server_id FROM vouches WHERE customer_id = %s ORDER BY id DESC LIMIT 10', (ctx.author.id,))
    history = cursor.fetchall()
    cursor.close(); conn.close()

    if not history:
        await ctx.send("❓ No history found."); return

    embed = discord.Embed(title="📄 Your Vouch History (Last 10)", color=0x4fc3f7)
    
    for msg, time, s_id, g_id in history:
        # 1. Try to find the Seller Name
        seller = bot.get_user(int(s_id))
        seller_display = seller.name if seller else f"User_{s_id}"
        
        # 2. Try to find the Server Name
        server = bot.get_guild(int(g_id))
        server_display = server.name if server else "Deleted/Private Server"
        
        embed.add_field(
            name=f"To {seller_display} in {server_display}", 
            value=f"*{time}*\n> {msg}", 
            inline=False
        )

    try:
        await ctx.author.send(embed=embed)
        await ctx.send(f"📬 {ctx.author.mention}, check your DMs for your named history!")
    except:
        await ctx.send("❌ I couldn't DM you. Please open your DMs in privacy settings.")
