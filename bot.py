import discord
from discord.ext import commands, tasks
from discord import app_commands
import json
import random
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("TOKEN")

with open("config.json") as f:
    config = json.load(f)

EMBED_COLOR = config["embed_color"]

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# -------------------------
# DATA SYSTEM
# -------------------------

def load_giveaways():
    if not os.path.exists("giveaways.json"):
        with open("giveaways.json","w") as f:
            json.dump({},f)

    with open("giveaways.json") as f:
        return json.load(f)

def save_giveaways(data):
    with open("giveaways.json","w") as f:
        json.dump(data,f,indent=4)

# -------------------------
# BUTTON VIEW
# -------------------------

class GiveawayView(discord.ui.View):

    def __init__(self, gw_id, ended=False):
        super().__init__(timeout=None)
        self.gw_id = gw_id

        if ended:
            for item in self.children:
                item.disabled = True

    @discord.ui.button(label="Enter Giveaway", style=discord.ButtonStyle.green, emoji="🎉")
    async def enter(self, interaction: discord.Interaction, button: discord.ui.Button):

        data = load_giveaways()

        if self.gw_id not in data:
            await interaction.response.send_message("❌ Giveaway not active.", ephemeral=True)
            return

        gw = data[self.gw_id]
        user = interaction.user

        if user.id in gw["entries"]:
            await interaction.response.send_message("⚠️ You already joined.", ephemeral=True)
            return

        if gw["requirement"]:
            role_ids = [r.id for r in user.roles]

            if gw["requirement"] not in role_ids:
                await interaction.response.send_message(
                    "❌ You don't meet giveaway requirements.",
                    ephemeral=True
                )
                return

        gw["entries"].append(user.id)
        save_giveaways(data)

        channel = interaction.channel
        msg = await channel.fetch_message(gw["message"])

        embed = msg.embeds[0]
        embed.set_field_at(3,name="Entries",value=str(len(gw["entries"])))

        await msg.edit(embed=embed)

        await interaction.response.send_message(
            "🎉 YOU ARE ENTERED THE GIVEAWAY",
            ephemeral=True
        )

# -------------------------
# READY EVENT
# -------------------------

@bot.event
async def on_ready():

    await bot.tree.sync()

    data = load_giveaways()

    for gid in data:
        bot.add_view(GiveawayView(gid))

    check_giveaways.start()

    print(f"Bot Ready: {bot.user}")

# -------------------------
# HELP COMMAND
# -------------------------

@bot.tree.command(name="help")
async def helpcmd(interaction: discord.Interaction):

    embed = discord.Embed(
        title="🎁 Giveaway Bot Commands",
        color=EMBED_COLOR
    )

    embed.add_field(
        name="Giveaway Commands",
        value="""
`/creategw` → Create timed giveaway  
`/cgw` → Quick giveaway  
`/endgw` → End giveaway  
`/reroll` → Reroll winners  
""",
        inline=False
    )

    embed.add_field(
        name="Manager Commands",
        value="""
`/glist` → List active giveaways  
`/ginfo` → Giveaway info  
`/gdelete` → Delete giveaway  
""",
        inline=False
    )

    await interaction.response.send_message(embed=embed, ephemeral=True)

# -------------------------
# QUICK GIVEAWAY
# -------------------------

@bot.tree.command(name="cgw")
async def cgw(
interaction: discord.Interaction,
prize:str,
winners:int,
requirement:discord.Role=None
):

    data = load_giveaways()

    gid = str(random.randint(10000,99999))

    embed = discord.Embed(
        title="🎉 QUICK GIVEAWAY",
        description="Click button below to join!",
        color=EMBED_COLOR
    )

    embed.add_field(name="Prize",value=prize,inline=False)
    embed.add_field(name="Host",value=interaction.user.mention)
    embed.add_field(name="Winners",value=winners)
    embed.add_field(name="Entries",value="0")

    if requirement:
        embed.add_field(name="Requirement",value=requirement.mention)
        req = requirement.id
    else:
        embed.add_field(name="Requirement",value="No Any Requirement")
        req = None

    embed.add_field(name="Giveaway Reactor",value="@everyone")

    embed.set_footer(text=f"Giveaway ID: {gid}")

    msg = await interaction.channel.send(embed=embed)

    view = GiveawayView(gid)
    await msg.edit(view=view)

    data[gid] = {
        "message":msg.id,
        "channel":interaction.channel.id,
        "prize":prize,
        "winners":winners,
        "entries":[],
        "host":interaction.user.id,
        "requirement":req,
        "end":None
    }

    save_giveaways(data)

    await interaction.response.send_message(
        f"✅ Giveaway Created | ID: `{gid}`",
        ephemeral=True
    )

# -------------------------
# END GIVEAWAY
# -------------------------

@bot.tree.command(name="endgw")
async def endgw(interaction:discord.Interaction,giveaway_id:str):

    data = load_giveaways()

    if giveaway_id not in data:
        await interaction.response.send_message("❌ Giveaway not found.",ephemeral=True)
        return

    gw = data[giveaway_id]

    channel = bot.get_channel(gw["channel"])
    message = await channel.fetch_message(gw["message"])

    entries = gw["entries"]

    if entries:
        winners = random.sample(entries,min(len(entries),gw["winners"]))
        mention = " ".join([f"<@{w}>" for w in winners])

        embed = discord.Embed(
            title="🎉 GIVEAWAY ENDED",
            description=f"Prize: **{gw['prize']}**\nWinner(s): {mention}",
            color=EMBED_COLOR
        )

        await channel.send(embed=embed)

    view = GiveawayView(giveaway_id,ended=True)
    await message.edit(view=view)

    del data[giveaway_id]
    save_giveaways(data)

    await interaction.response.send_message("✅ Giveaway Ended",ephemeral=True)

# -------------------------
# REROLL
# -------------------------

@bot.tree.command(name="reroll")
async def reroll(interaction:discord.Interaction,giveaway_id:str):

    data = load_giveaways()

    if giveaway_id not in data:
        await interaction.response.send_message("❌ Giveaway not found.",ephemeral=True)
        return

    gw = data[giveaway_id]

    entries = gw["entries"]

    if not entries:
        await interaction.response.send_message("❌ No entries.",ephemeral=True)
        return

    winners = random.sample(entries,min(len(entries),gw["winners"]))
    mention = " ".join([f"<@{w}>" for w in winners])

    channel = bot.get_channel(gw["channel"])

    embed = discord.Embed(
        title="🔄 GIVEAWAY REROLLED",
        description=f"New Winner(s): {mention}",
        color=EMBED_COLOR
    )

    await channel.send(embed=embed)

    await interaction.response.send_message("✅ Rerolled",ephemeral=True)

# -------------------------
# LIST GIVEAWAYS
# -------------------------

@bot.tree.command(name="glist")
async def glist(interaction:discord.Interaction):

    data = load_giveaways()

    if not data:
        await interaction.response.send_message("❌ No active giveaways.",ephemeral=True)
        return

    embed = discord.Embed(title="🎁 Active Giveaways",color=EMBED_COLOR)

    for gid,gw in data.items():

        embed.add_field(
            name=f"ID: {gid}",
            value=f"Prize: {gw['prize']}\nEntries: {len(gw['entries'])}",
            inline=False
        )

    await interaction.response.send_message(embed=embed)

# -------------------------
# GIVEAWAY INFO
# -------------------------

@bot.tree.command(name="ginfo")
async def ginfo(interaction:discord.Interaction,giveaway_id:str):

    data = load_giveaways()

    if giveaway_id not in data:
        await interaction.response.send_message("❌ Giveaway not found.",ephemeral=True)
        return

    gw = data[giveaway_id]

    embed = discord.Embed(title="🎉 Giveaway Info",color=EMBED_COLOR)

    embed.add_field(name="Prize",value=gw["prize"])
    embed.add_field(name="Entries",value=len(gw["entries"]))
    embed.add_field(name="Winners",value=gw["winners"])

    embed.set_footer(text=f"Giveaway ID: {giveaway_id}")

    await interaction.response.send_message(embed=embed)

# -------------------------
# DELETE GIVEAWAY
# -------------------------

@bot.tree.command(name="gdelete")
async def gdelete(interaction:discord.Interaction,giveaway_id:str):

    data = load_giveaways()

    if giveaway_id not in data:
        await interaction.response.send_message("❌ Giveaway not found.",ephemeral=True)
        return

    gw = data[giveaway_id]

    channel = bot.get_channel(gw["channel"])

    try:
        msg = await channel.fetch_message(gw["message"])
        await msg.delete()
    except:
        pass

    del data[giveaway_id]
    save_giveaways(data)

    await interaction.response.send_message("🗑 Giveaway deleted.",ephemeral=True)

# -------------------------
# AUTO END SYSTEM
# -------------------------

@tasks.loop(seconds=30)
async def check_giveaways():
    pass

# -------------------------

bot.run(TOKEN)
