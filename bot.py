import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv
import json
import random
import os
import time
from datetime import datetime

load_dotenv()

TOKEN = os.getenv("TOKEN")

with open("config.json") as f:
    config = json.load(f)

EMBED_COLOR = config["embed_color"]
LOG_CHANNEL = config["log_channel_id"]
XP_CHANNEL = config["xp_channel_id"]

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

cooldowns = {}

# ---------------- DATABASE ----------------

def load_db():
    if not os.path.exists("database.json"):
        return {"users": {}, "giveaways": {}}

    with open("database.json") as f:
        return json.load(f)

def save_db(data):
    with open("database.json","w") as f:
        json.dump(data,f,indent=4)

# ---------------- XP SYSTEM ----------------

@bot.event
async def on_message(message):

    if message.author.bot:
        return

    if message.channel.id != XP_CHANNEL:
        return

    db = load_db()
    uid = str(message.author.id)

    if uid not in db["users"]:
        db["users"][uid] = {"xp":0,"level":1,"invites":0}

    # anti spam cooldown
    now = time.time()
    if uid in cooldowns and now - cooldowns[uid] < 5:
        return

    cooldowns[uid] = now

    db["users"][uid]["xp"] += 10

    xp = db["users"][uid]["xp"]
    level = db["users"][uid]["level"]

    if xp >= level * 100:
        db["users"][uid]["level"] += 1

        await message.channel.send(
            f"🎉 {message.author.mention} leveled up to **Level {level+1}**!"
        )

    else:
        await message.channel.send(
            f"📈 {message.author.mention} +10 XP"
        )

    save_db(db)

    await bot.process_commands(message)

# ---------------- GIVEAWAY VIEW ----------------

class GiveawayView(discord.ui.View):

    def __init__(self, gw_id, ended=False):
        super().__init__(timeout=None)
        self.gw_id = gw_id

        if ended:
            for item in self.children:
                item.disabled = True

    @discord.ui.button(label="Enter Giveaway", style=discord.ButtonStyle.green, emoji="🎉")
    async def enter(self, interaction: discord.Interaction, button: discord.ui.Button):

        db = load_db()
        gw = db["giveaways"][self.gw_id]
        user = interaction.user

        uid = str(user.id)

        if uid in gw["entries"]:
            await interaction.response.send_message("Already joined.", ephemeral=True)
            return

        # ROLE CHECK
        if gw.get("role_req"):
            if gw["role_req"] not in [r.id for r in user.roles]:
                await interaction.response.send_message("❌ Role required.", ephemeral=True)
                return

        # LEVEL CHECK
        if gw.get("level_req"):
            level = db["users"].get(uid, {}).get("level", 1)
            if level < gw["level_req"]:
                await interaction.response.send_message("❌ Level required.", ephemeral=True)
                return

        # INVITE CHECK
        if gw.get("invite_req"):
            invites = db["users"].get(uid, {}).get("invites", 0)
            if invites < gw["invite_req"]:
                await interaction.response.send_message("❌ Invite requirement not met.", ephemeral=True)
                return

        gw["entries"].append(uid)
        save_db(db)

        msg = await interaction.channel.fetch_message(gw["message"])

        embed = msg.embeds[0]
        embed.set_field_at(3, name="Entries", value=str(len(gw["entries"])))

        await msg.edit(embed=embed)

        await interaction.response.send_message("🎉 Entered giveaway!", ephemeral=True)

# ---------------- CREATE GIVEAWAY ----------------

@bot.tree.command(name="cgw")
async def cgw(interaction: discord.Interaction,
              prize:str,
              winners:int,
              role:discord.Role=None,
              level:int=0,
              invites:int=0):

    db = load_db()

    gid = str(random.randint(10000,99999))

    embed = discord.Embed(
        title="🎉 PREMIUM GIVEAWAY",
        description="Click button to enter",
        color=EMBED_COLOR
    )

    embed.add_field(name="Prize", value=prize)
    embed.add_field(name="Winners", value=winners)
    embed.add_field(name="Host", value=interaction.user.mention)
    embed.add_field(name="Entries", value="0")

    embed.add_field(name="Requirements",
        value=f"Role: {role.mention if role else 'None'}\nLevel: {level}\nInvites: {invites}"
    )

    msg = await interaction.channel.send(embed=embed)

    view = GiveawayView(gid)
    await msg.edit(view=view)

    db["giveaways"][gid] = {
        "message": msg.id,
        "channel": interaction.channel.id,
        "prize": prize,
        "winners": winners,
        "entries": [],
        "host": interaction.user.id,
        "role_req": role.id if role else None,
        "level_req": level,
        "invite_req": invites
    }

    save_db(db)

    await interaction.response.send_message(f"Created Giveaway ID: {gid}", ephemeral=True)

# ---------------- INVITE TRACKING ----------------

@bot.event
async def on_member_join(member):

    db = load_db()

    inviter = None

    invites = await member.guild.invites()

    for i in invites:
        if i.uses > 0:
            inviter = i.inviter
            break

    if inviter:
        uid = str(inviter.id)

        if uid not in db["users"]:
            db["users"][uid] = {"xp":0,"level":1,"invites":0}

        db["users"][uid]["invites"] += 1

        save_db(db)

        log = bot.get_channel(LOG_CHANNEL)

        await log.send(
            f"📨 Invite Update\n{inviter.mention} now has {db['users'][uid]['invites']} invites"
        )

# ---------------- REROLL ----------------

@bot.tree.command(name="reroll")
async def reroll(interaction: discord.Interaction, gid:str):

    db = load_db()

    gw = db["giveaways"][gid]

    winners = random.sample(gw["entries"], min(len(gw["entries"]), gw["winners"]))

    await interaction.channel.send(
        f"🔄 New Winner(s): " + " ".join([f"<@{w}>" for w in winners])
    )

    await interaction.response.send_message("Rerolled!", ephemeral=True)

# ---------------- END GIVEAWAY ----------------

@bot.tree.command(name="endgw")
async def endgw(interaction: discord.Interaction, gid:str):

    db = load_db()

    gw = db["giveaways"][gid]

    channel = bot.get_channel(gw["channel"])

    msg = await channel.fetch_message(gw["message"])

    view = GiveawayView(gid, ended=True)

    await msg.edit(view=view)

    if gw["entries"]:
        winner = random.sample(gw["entries"],1)[0]

        await channel.send(f"🎉 Winner: <@{winner}>")

    del db["giveaways"][gid]

    save_db(db)

    await interaction.response.send_message("Ended", ephemeral=True)

# ---------------- HELP ----------------

@bot.tree.command(name="help")
async def helpcmd(interaction: discord.Interaction):

    embed = discord.Embed(
        title="🎁 Bot Help",
        description="""
/cgw - create giveaway  
/endgw - end giveaway  
/reroll - reroll winner  
stats system included  
XP + Invite system active  
""",
        color=EMBED_COLOR
    )

    await interaction.response.send_message(embed=embed, ephemeral=True)

# ---------------- RUN BOT ----------------

bot.run(TOKEN)
