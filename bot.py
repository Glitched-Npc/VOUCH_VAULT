# ============================================================================
# 🚨 GLOBAL SECURITY COMMANDS (ADMIN ONLY)
# ============================================================================

@bot.command()
async def flag(ctx, user: discord.User, *, reason: str = "No reason provided"):
    """Adds a user to the Global Blacklist. Usage: !flag @User Reason or !flag ID Reason"""
    if ctx.author.id != ADMIN_USER_ID: 
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Store the ID as a string to ensure no errors with large numbers
    user_id = str(user.id)
    
    cursor.execute('''
        INSERT INTO global_blacklist (user_id, reason, date_flagged) 
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id) DO UPDATE SET reason = EXCLUDED.reason
    ''', (user_id, reason, datetime.now()))
    
    conn.commit()
    cursor.close()
    conn.close()

    embed = discord.Embed(
        title="🚨 GLOBAL BLACKLIST UPDATED",
        description=f"User **{user.name}** (`{user.id}`) has been flagged.",
        color=0xFF0000
    )
    embed.add_field(name="Reason Stored", value=f"```{reason}```")
    embed.set_footer(text="This user is now blocked across the entire network.")
    
    await ctx.send(embed=embed)

@bot.command()
async def unflag(ctx, user: discord.User):
    """Removes a user from the Global Blacklist. Usage: !unflag @User or !unflag ID"""
    if ctx.author.id != ADMIN_USER_ID: 
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM global_blacklist WHERE user_id = %s', (str(user.id),))
    conn.commit()
    cursor.close()
    conn.close()

    await ctx.send(f"✅ **Security Update:** User **{user.name}** has been cleared from the Global Blacklist.")
