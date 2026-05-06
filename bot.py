@bot.event
async def on_ready():
    # ENSURE ALL TABLES ARE CREATED CORRECTLY
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS vouches (id SERIAL PRIMARY KEY, seller_id BIGINT, customer_id BIGINT, customer_name TEXT, content TEXT, timestamp TEXT, origin_server_id BIGINT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS subscriptions (server_id BIGINT PRIMARY KEY, expiry_date TIMESTAMP)')
    # Using TEXT for blueprint to avoid JSON format errors during transfer
    cursor.execute('CREATE TABLE IF NOT EXISTS server_backups (server_id BIGINT PRIMARY KEY, blueprint TEXT, backup_date TIMESTAMP)')
    cursor.execute('CREATE TABLE IF NOT EXISTS global_blacklist (user_id BIGINT PRIMARY KEY, reason TEXT, date_flagged TIMESTAMP)')
    conn.commit()
    cursor.close()
    conn.close()
    print(f'✅ Vouch Vault PRO Online and Database Synced')

@bot.command()
async def backup(ctx):
    """Saves server roles and channels to the cloud."""
    # 1. Premium Check
    if not is_premium(ctx.guild.id) and ctx.author.id not in TESTER_IDS:
        await ctx.send("🔒 **Premium Required.** $6.99/mo required for Server Insurance.")
        return

    await ctx.send("⏳ **Scanning Server Structure...**")

    try:
        # 2. Capture Roles (Filter out bot roles and @everyone)
        roles = []
        for r in ctx.guild.roles:
            if not r.is_default() and not r.managed:
                roles.append({"name": r.name, "color": r.color.value})

        # 3. Capture Categories and Channels
        categories = []
        for cat in ctx.guild.categories:
            channels = []
            for chan in cat.channels:
                channels.append({"name": chan.name, "type": str(chan.type)})
            categories.append({"name": cat.name, "channels": channels})

        # 4. Convert to JSON string
        blueprint_data = json.dumps({"roles": roles, "categories": categories})

        # 5. Save to Postgres
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO server_backups (server_id, blueprint, backup_date) 
            VALUES (%s, %s, %s) 
            ON CONFLICT (server_id) DO UPDATE SET blueprint = EXCLUDED.blueprint, backup_date = EXCLUDED.backup_date
        ''', (ctx.guild.id, blueprint_data, datetime.now()))
        
        conn.commit()
        cursor.close()
        conn.close()

        # 6. Success Embed
        embed = discord.Embed(title="✅ BACKUP SUCCESSFUL", color=0x00FF00)
        embed.description = f"The structure of **{ctx.guild.name}** has been secured."
        embed.add_field(name="Roles Saved", value=f"`{len(roles)}`", inline=True)
        embed.add_field(name="Categories Saved", value=f"`{len(categories)}`", inline=True)
        embed.set_footer(text="Your blueprint is now safe in the Cloud Vault.")
        
        await ctx.send(embed=embed)

    except Exception as e:
        await ctx.send(f"❌ **Backup Failed:** `{str(e)}`")
        print(f"DEBUG ERROR: {e}")
