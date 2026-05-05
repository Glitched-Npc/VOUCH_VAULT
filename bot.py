# ============================================================================
# 🚨 GLOBAL SECURITY (FLAG: Server Admins | UNFLAG: Bot Owner Only)
# ============================================================================

@bot.command()
@commands.has_permissions(administrator=True)
async def flag(ctx, user: discord.User, *, reason: str = "No reason provided"):
    """
    Allows Server Admins to flag a scammer globally.
    Only works in authorized servers.
    """
    # 1. Check if the server has a subscription
    if not is_authorized(ctx.author.id, ctx.guild.id):
        await ctx.send("🔒 **Premium Required.** Your server must be authorized to use Global Security features.")
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 2. Add to Global Blacklist
    cursor.execute('''
        INSERT INTO global_blacklist (user_id, reason, date_flagged) 
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id) DO UPDATE SET reason = EXCLUDED.reason
    ''', (user.id, f"Flagged by {ctx.guild.name} Admin: {reason}", datetime.now()))
    
    conn.commit()
    cursor.close()
    conn.close()

    embed = discord.Embed(title="🚨 GLOBAL BLACKLIST UPDATED", color=0xFF0000)
    embed.add_field(name="User Flagged", value=f"{user.name} (`{user.id}`)")
    embed.add_field(name="Reason", value=f"```{reason}```", inline=False)
    embed.add_field(name="Reported By", value=f"{ctx.guild.name} Staff")
    embed.set_footer(text="Warning: This user is now blocked across the entire Silk Labz network.")
    
    await ctx.send(embed=embed)

@bot.command()
async def unflag(ctx, user: discord.User):
    """
    STRICTLY Bot Owner Only.
    """
    # LOCK: Only YOU (EXTEKK) can unflag
    if ctx.author.id != ADMIN_USER_ID:
        # Silent ignore for security
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM global_blacklist WHERE user_id = %s', (user.id,))
    conn.commit()
    cursor.close()
    conn.close()
    
    await ctx.send(f"✅ **Security Update:** User **{user.name}** has been cleared from the Global Blacklist by the System Administrator.")
