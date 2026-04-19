import discord
from discord.ext import commands, tasks
from discord import app_commands
import sqlite3
import random
import json
import string
import asyncio
from datetime import datetime, timedelta

TOKEN = "YOUR_BOT_TOKEN"

XP_CHANNEL_ID = 123456789
LOG_CHANNEL_ID = 123456789

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# DATABASE
db = sqlite3.connect("database.db")
cursor = db.cursor()

cursor.execute("""CREATE TABLE IF NOT EXISTS xp(
user_id INTEGER PRIMARY KEY,
xp INTEGER DEFAULT 0,
level INTEGER DEFAULT 0
)""")

cursor.execute("""CREATE TABLE IF NOT EXISTS invites(
user_id INTEGER PRIMARY KEY,
invites INTEGER DEFAULT 0
)""")

cursor.execute("""CREATE TABLE IF NOT EXISTS giveaways(
gw_id TEXT,
message_id INTEGER,
channel_id INTEGER,
ended INTEGER DEFAULT 0
)""")

db.commit()

# LOAD ACTIVITY
with open("activity.json") as f:
    activity_data = json.load(f)["activities"]

# MULTI ACTIVITY
@tasks.loop(seconds=15)
async def change_activity():
    activity = random.choice(activity_data)
    await bot.change_presence(
        status=discord.Status.dnd,
        activity=discord.Game(activity)
    )

# LEVEL SYSTEM
def level_formula(xp):
    return int((xp / 100) ** 0.5)

# BOT READY
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    change_activity.start()
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands")
    except:
        pass

# MESSAGE XP SYSTEM
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if message.channel.id == XP_CHANNEL_ID:
        user = message.author.id

        cursor.execute("SELECT xp, level FROM xp WHERE user_id=?", (user,))
        data = cursor.fetchone()

        if data is None:
            xp = 10
            level = 0
            cursor.execute("INSERT INTO xp VALUES (?,?,?)",(user,xp,level))
        else:
            xp = data[0] + 10
            level = data[1]

            new_level = level_formula(xp)

            cursor.execute("UPDATE xp SET xp=? WHERE user_id=?",(xp,user))

            if new_level > level:
                cursor.execute("UPDATE xp SET level=? WHERE user_id=?",(new_level,user))
                await message.channel.send(f"{message.author.mention} 🎉 Level Up! **Level {new_level}**")

        db.commit()

        await message.channel.send(f"{message.author.mention} gained **10 XP**")

    await bot.process_commands(message)

# XP COMMAND
@bot.tree.command(name="xp")
async def xp(interaction: discord.Interaction, member: discord.Member=None):
    if member is None:
        member = interaction.user

    cursor.execute("SELECT xp, level FROM xp WHERE user_id=?", (member.id,))
    data = cursor.fetchone()

    if data is None:
        await interaction.response.send_message("No XP yet.")
    else:
        await interaction.response.send_message(
            f"{member.mention}\nXP: {data[0]}\nLevel: {data[1]}"
        )

# INVITE COMMAND
@bot.tree.command(name="invite")
async def invite(interaction: discord.Interaction, member: discord.Member=None):

    if member is None:
        member = interaction.user

    cursor.execute("SELECT invites FROM invites WHERE user_id=?", (member.id,))
    data = cursor.fetchone()

    if data is None:
        await interaction.response.send_message("Invites: 0")
    else:
        await interaction.response.send_message(f"Invites: {data[0]}")

# HELP COMMAND
@bot.tree.command(name="help")
async def help_cmd(interaction: discord.Interaction):

    embed = discord.Embed(
        title="Bot Commands",
        color=0x00ff00
    )

    embed.add_field(name="/xp", value="Check XP", inline=False)
    embed.add_field(name="/invite", value="Check invites", inline=False)
    embed.add_field(name="/giveaway", value="Create giveaway (Admin)", inline=False)
    embed.add_field(name="/endgw", value="End giveaway (Admin)", inline=False)
    embed.add_field(name="/deletegw", value="Delete giveaway (Admin)", inline=False)
    embed.add_field(name="/adminpanel", value="Admin control panel", inline=False)

    await interaction.response.send_message(embed=embed)

# GIVEAWAY BUTTON
class GiveawayView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Enter Giveaway", style=discord.ButtonStyle.green)
    async def enter(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("You joined giveaway!", ephemeral=True)

# GENERATE ID
def generate_id():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

# CREATE GIVEAWAY
@bot.tree.command(name="giveaway")
@app_commands.checks.has_permissions(administrator=True)
async def giveaway(interaction: discord.Interaction, duration:int, prize:str):

    gw_id = generate_id()
    end = datetime.utcnow() + timedelta(minutes=duration)

    embed = discord.Embed(
        title="🎉 GIVEAWAY",
        description=f"Prize: **{prize}**\nEnds: <t:{int(end.timestamp())}:R>",
        color=0xff0000
    )

    embed.set_footer(text=f"Giveaway ID: {gw_id}")

    view = GiveawayView()

    msg = await interaction.channel.send(embed=embed, view=view)

    cursor.execute(
        "INSERT INTO giveaways VALUES (?,?,?,0)",
        (gw_id,msg.id,interaction.channel.id)
    )

    db.commit()

    await interaction.response.send_message("Giveaway created.", ephemeral=True)

# END GIVEAWAY
@bot.tree.command(name="endgw")
@app_commands.checks.has_permissions(administrator=True)
async def endgw(interaction: discord.Interaction, gw_id:str):

    cursor.execute("SELECT message_id, channel_id FROM giveaways WHERE gw_id=?",(gw_id,))
    data = cursor.fetchone()

    if data is None:
        await interaction.response.send_message("Invalid ID")
        return

    channel = bot.get_channel(data[1])
    msg = await channel.fetch_message(data[0])

    embed = msg.embeds[0]
    embed.title = "Giveaway Ended"

    await msg.edit(embed=embed, view=None)

    await interaction.response.send_message("Giveaway ended")

# DELETE GIVEAWAY
@bot.tree.command(name="deletegw")
@app_commands.checks.has_permissions(administrator=True)
async def deletegw(interaction: discord.Interaction, gw_id:str):

    cursor.execute("SELECT message_id, channel_id FROM giveaways WHERE gw_id=?",(gw_id,))
    data = cursor.fetchone()

    if data is None:
        await interaction.response.send_message("Invalid ID")
        return

    channel = bot.get_channel(data[1])
    msg = await channel.fetch_message(data[0])

    await msg.delete()

    cursor.execute("DELETE FROM giveaways WHERE gw_id=?",(gw_id,))
    db.commit()

    await interaction.response.send_message("Giveaway deleted")

# ADMIN PANEL
@bot.tree.command(name="adminpanel")
@app_commands.checks.has_permissions(administrator=True)
async def adminpanel(interaction: discord.Interaction):

    embed = discord.Embed(
        title="Admin Panel",
        description="""
Admin commands

Edit XP
Edit Invites
Manage Giveaways
Bot Logs
""",
        color=0x0099ff
    )

    await interaction.response.send_message(embed=embed)

bot.run(TOKEN)
