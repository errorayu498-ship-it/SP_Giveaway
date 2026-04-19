import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv
import json
import random
import os
import time

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

def get_user(db, uid):
    if uid not in db["users"]:
        db["users"][uid] = {"xp":0,"level":1,"invites":0}
    return db["users"][uid]

# ---------------- XP SYSTEM ----------------

@bot.event
async def on_message(message):

    if message.author.bot:
        return

    if message.channel.id != XP_CHANNEL:
        return

    db = load_db()
    uid = str(message.author.id)

    user = get_user(db, uid)

    now = time.time()
    if uid in cooldowns and now - cooldowns[uid] < 5:
        return

    cooldowns[uid] = now

    old = user["xp"]

    user["xp"] += 10

    new = user["xp"]

    # LEVEL UP
    if new >= user["level"] * 100:
        user["level"] += 1
        await message.channel.send(f"🎉 {message.author.mention} reached Level {user['level']}!")

    # ONLY 100 XP MILESTONE MESSAGE
    if new % 100 == 0 and new != old:
        await message.channel.send(f"📈 {message.author.mention} reached {new} XP!")

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

        uid = str(interaction.user.id)
        user = get_user(db, uid)

        if uid in gw["entries"]:
            return await interaction.response.send_message("Already joined.", ephemeral=True)

        # ROLE
        if gw.get("role_req"):
            if gw["role_req"] not in [r.id for r in interaction.user.roles]:
                return await interaction.response.send_message("❌ Role required", ephemeral=True)

        # XP
        if gw.get("xp_req",0) > 0:
            if user["xp"] < gw["xp_req"]:
                return await interaction.response.send_message("❌ XP required", ephemeral=True)

        # INVITES
        if gw.get("invite_req",0) > 0:
            if user["invites"] < gw["invite_req"]:
                return await interaction.response.send_message("❌ Invites required", ephemeral=True)

        gw["entries"].append(uid)
        save_db(db)

        msg = await interaction.channel.fetch_message(gw["message"])

        embed = msg.embeds[0]
        embed.set_field_at(3, name="Entries", value=str(len(gw["entries"])))

        await msg.edit(embed=embed)

        await interaction.response.send_message("🎉 Entered giveaway!", ephemeral=True)

# ---------------- ADMIN CHECK ----------------

def admin_only(interaction: discord.Interaction):
    return interaction.user.guild_permissions.administrator

# ---------------- MULTI ACTIVITY ----------------

@tasks.loop(seconds=15)
async def change_activity():

    with open("activity.json") as f:
        data = json.load(f)

    act = random.choice(data["activities"])

    await bot.change_presence(
        status=discord.Status.dnd,
        activity=discord.Game(name=act)
    )

# ---------------- READY ----------------

@bot.event
async def on_ready():

    await bot.tree.sync()

    change_activity.start()

    print(f"BOT ONLINE: {bot.user}")

# ---------------- XP COMMAND ----------------

@bot.tree.command(name="xp")
async def xp(interaction: discord.Interaction, member: discord.Member=None):

    member = member or interaction.user
    db = load_db()

    user = db["users"].get(str(member.id), {"xp":0,"level":1})

    embed = discord.Embed(title="📊 XP PROFILE", color=EMBED_COLOR)
    embed.add_field(name="XP", value=user["xp"])
    embed.add_field(name="Level", value=user["level"])

    await interaction.response.send_message(embed=embed)

# ---------------- INVITE COMMAND ----------------

@bot.tree.command(name="invite")
async def invite(interaction: discord.Interaction, member: discord.Member=None):

    member = member or interaction.user
    db = load_db()

    user = db["users"].get(str(member.id), {"invites":0})

    embed = discord.Embed(title="📨 INVITES", color=EMBED_COLOR)
    embed.add_field(name="Invites", value=user["invites"])

    await interaction.response.send_message(embed=embed)

# ---------------- ADMIN GIVEAWAY ----------------

@bot.tree.command(name="cgw")
async def cgw(interaction: discord.Interaction, prize:str, winners:int,
              role:discord.Role=None, xp:int=0, invites:int=0):

    if not admin_only(interaction):
        return await interaction.response.send_message("Admin only.", ephemeral=True)

    db = load_db()
    gid = str(random.randint(10000,99999))

    embed = discord.Embed(title="🎉 SP GIVEAWAY", color=EMBED_COLOR)
    embed.add_field(name="Prize", value=prize)
    embed.add_field(name="Winners", value=winners)
    embed.add_field(name="Host", value=interaction.user.mention)
    embed.add_field(name="Entries", value="0")

    embed.add_field(
        name="Requirements",
        value=f"Role: {role.mention if role else 'None'}\nXP: {xp}\nInvites: {invites}"
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
        "xp_req": xp,
        "invite_req": invites
    }

    save_db(db)

    await interaction.response.send_message(f"Created {gid}", ephemeral=True)

# ---------------- REROLL ----------------

@bot.tree.command(name="reroll")
async def reroll(interaction: discord.Interaction, gid:str):

    if not admin_only(interaction):
        return

    db = load_db()
    gw = db["giveaways"][gid]

    winners = random.sample(gw["entries"], min(len(gw["entries"]), gw["winners"]))

    await interaction.channel.send("🎉 Winner: " + " ".join([f"<@{w}>" for w in winners]))

# ---------------- RUN ----------------

bot.run(TOKEN)
