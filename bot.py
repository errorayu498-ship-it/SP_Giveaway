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

LOG_CHANNEL = config["log_channel_id"]
EMBED_COLOR = config["embed_color"]

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# ------------------------
# DATA FUNCTIONS
# ------------------------

def load_giveaways():
    if not os.path.exists("giveaways.json"):
        with open("giveaways.json","w") as f:
            json.dump({},f)

    with open("giveaways.json") as f:
        return json.load(f)

def save_giveaways(data):
    with open("giveaways.json","w") as f:
        json.dump(data,f,indent=4)

# ------------------------
# GIVEAWAY BUTTON VIEW
# ------------------------

class GiveawayView(discord.ui.View):

    def __init__(self, gw_id, ended=False):
        super().__init__(timeout=None)
        self.gw_id = gw_id

        if ended:
            for item in self.children:
                item.disabled = True

    @discord.ui.button(label="Enter Giveaway", style=discord.ButtonStyle.green, emoji="🎉", custom_id="enter_gw")
    async def enter(self, interaction: discord.Interaction, button: discord.ui.Button):

        data = load_giveaways()

        if self.gw_id not in data:
            await interaction.response.send_message(
                "❌ Giveaway not active.",
                ephemeral=True
            )
            return

        gw = data[self.gw_id]

        user = interaction.user

        if user.id in gw["entries"]:
            await interaction.response.send_message(
                "⚠️ You already joined this giveaway.",
                ephemeral=True
            )
            return

        # requirement check
        if gw["requirement"]:

            role_required = int(gw["requirement"])

            roles = [r.id for r in user.roles]

            if role_required not in roles:
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

        embed.set_field_at(
            2,
            name="Entries",
            value=str(len(gw["entries"]))
        )

        await msg.edit(embed=embed)

        await interaction.response.send_message(
            "🎉 YOU ARE ENTERED THE GIVEAWAY",
            ephemeral=True
        )

# ------------------------
# READY EVENT
# ------------------------

@bot.event
async def on_ready():

    await bot.tree.sync()

    data = load_giveaways()

    for gw_id in data:
        bot.add_view(GiveawayView(gw_id))

    check_giveaways.start()

    print(f"Bot Ready: {bot.user}")

# ------------------------
# CREATE GIVEAWAY
# ------------------------

@bot.tree.command(name="creategw")
async def creategw(
interaction: discord.Interaction,
prize:str,
winners:int,
duration:str,
requirement:str=None
):

    data = load_giveaways()

    gw_id = str(random.randint(10000,99999))

    end_time = datetime.strptime(duration,"%d/%m/%Y %I:%M:%S %p")

    embed = discord.Embed(
        title="🎉 NEW GIVEAWAY",
        color=EMBED_COLOR
    )

    embed.add_field(name="Prize",value=prize,inline=False)
    embed.add_field(name="Winners",value=winners)
    embed.add_field(name="Entries",value="0")
    embed.add_field(name="Ends",value=duration)
    embed.add_field(name="Requirement",value=requirement if requirement else "No Any Requirement")

    embed.set_footer(text=f"Giveaway ID: {gw_id}")

    msg = await interaction.channel.send(embed=embed)

    view = GiveawayView(gw_id)

    await msg.edit(view=view)

    data[gw_id] = {

        "message":msg.id,
        "channel":interaction.channel.id,
        "prize":prize,
        "winners":winners,
        "end":duration,
        "entries":[],
        "requirement":requirement,
        "type":"normal"
    }

    save_giveaways(data)

    await interaction.response.send_message(
        "✅ Giveaway Created",
        ephemeral=True
    )

# ------------------------
# QUICK GIVEAWAY
# ------------------------

@bot.tree.command(name="cgw")
async def cgw(
interaction: discord.Interaction,
prize:str,
winners:int
):

    data = load_giveaways()

    gw_id = str(random.randint(10000,99999))

    embed = discord.Embed(
        title="⚡ QUICK GIVEAWAY",
        color=EMBED_COLOR
    )

    embed.add_field(name="Prize",value=prize,inline=False)
    embed.add_field(name="Winners",value=winners)
    embed.add_field(name="Entries",value="0")

    embed.set_footer(text=f"Giveaway ID: {gw_id}")

    msg = await interaction.channel.send(embed=embed)

    view = GiveawayView(gw_id)

    await msg.edit(view=view)

    data[gw_id] = {

        "message":msg.id,
        "channel":interaction.channel.id,
        "prize":prize,
        "winners":winners,
        "entries":[],
        "requirement":None,
        "type":"quick"
    }

    save_giveaways(data)

    await interaction.response.send_message(
        "⚡ Quick Giveaway Created",
        ephemeral=True
    )

# ------------------------
# END GIVEAWAY
# ------------------------

@bot.tree.command(name="endgw")
async def endgw(interaction:discord.Interaction,giveaway_id:str):

    data = load_giveaways()

    if giveaway_id not in data:

        await interaction.response.send_message(
            "❌ Giveaway not found",
            ephemeral=True
        )
        return

    gw = data[giveaway_id]

    channel = bot.get_channel(gw["channel"])

    message = await channel.fetch_message(gw["message"])

    entries = gw["entries"]

    if len(entries) == 0:

        await channel.send("❌ No entries in giveaway.")

    else:

        winners = random.sample(entries, min(len(entries), gw["winners"]))

        mention = " ".join([f"<@{w}>" for w in winners])

        embed = discord.Embed(
            title="🎉 GIVEAWAY ENDED",
            description=f"Prize: **{gw['prize']}**\nWinner(s): {mention}",
            color=EMBED_COLOR
        )

        await channel.send(embed=embed)

    # disable button
    old_embed = message.embeds[0]

    view = GiveawayView(giveaway_id, ended=True)

    await message.edit(embed=old_embed, view=view)

    del data[giveaway_id]

    save_giveaways(data)

    await interaction.response.send_message(
        "✅ Giveaway Ended",
        ephemeral=True
    )

# ------------------------
# REROLL
# ------------------------

@bot.tree.command(name="reroll")
async def reroll(interaction:discord.Interaction,giveaway_id:str):

    data = load_giveaways()

    if giveaway_id not in data:

        await interaction.response.send_message(
            "❌ Giveaway not found.",
            ephemeral=True
        )
        return

    gw = data[giveaway_id]

    entries = gw["entries"]

    if len(entries) == 0:

        await interaction.response.send_message(
            "❌ No entries.",
            ephemeral=True
        )
        return

    winners = random.sample(entries, min(len(entries), gw["winners"]))

    mention = " ".join([f"<@{w}>" for w in winners])

    channel = bot.get_channel(gw["channel"])

    embed = discord.Embed(
        title="🔄 GIVEAWAY REROLLED",
        description=f"Prize: **{gw['prize']}**\nNew Winner(s): {mention}",
        color=EMBED_COLOR
    )

    await channel.send(embed=embed)

    await interaction.response.send_message(
        "✅ Giveaway rerolled.",
        ephemeral=True
    )

# ------------------------
# AUTO END SYSTEM
# ------------------------

@tasks.loop(seconds=30)
async def check_giveaways():

    data = load_giveaways()

    now = datetime.now()

    ended = []

    for gw_id,gw in data.items():

        if "end" not in gw:
            continue

        end = datetime.strptime(gw["end"],"%d/%m/%Y %I:%M:%S %p")

        if now >= end:

            channel = bot.get_channel(gw["channel"])

            message = await channel.fetch_message(gw["message"])

            entries = gw["entries"]

            if entries:

                winners = random.sample(entries, min(len(entries), gw["winners"]))

                mention = " ".join([f"<@{w}>" for w in winners])

                embed = discord.Embed(
                    title="🎉 GIVEAWAY ENDED",
                    description=f"Prize: **{gw['prize']}**\nWinner(s): {mention}",
                    color=EMBED_COLOR
                )

                await channel.send(embed=embed)

            view = GiveawayView(gw_id, ended=True)

            await message.edit(view=view)

            ended.append(gw_id)

    for gw_id in ended:
        del data[gw_id]

    save_giveaways(data)

# ------------------------

bot.run(TOKEN)
