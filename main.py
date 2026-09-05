import discord
import levels
import json
import os

key = open("BOT_KEY.KEY", "r")
DISCORD_KEY = key.readline()

TARGET_GUILD_ID = 1545389814679863388
OWNER_ID = 1534437987251781722
WARNINGS_FILE = "warnings.json"

def load_warnings():
    if os.path.exists(WARNINGS_FILE):
        try:
            with open(WARNINGS_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}

def save_warnings(data):
    with open(WARNINGS_FILE, "w") as f:
        json.dump(data, f, indent=4)

def add_warning(guild_id: int, user_id: int, reason: str, moderator_id: int):
    data = load_warnings()
    guild_key = str(guild_id)
    user_key = str(user_id)
    if guild_key not in data:
        data[guild_key] = {}
    if user_key not in data[guild_key]:
        data[guild_key][user_key] = {"count": 0, "history": []}
    data[guild_key][user_key]["count"] += 1
    data[guild_key][user_key]["history"].append({
        "reason": reason,
        "moderator": moderator_id,
        "count": data[guild_key][user_key]["count"]
    })
    save_warnings(data)
    return data[guild_key][user_key]["count"]

def get_warnings(guild_id: int, user_id: int):
    data = load_warnings()
    return data.get(str(guild_id), {}).get(str(user_id), {"count": 0, "history": []})

class Client(discord.Client):
    async def on_ready(self):
        print(f'Logged on as {self.user}')
        guild = self.get_guild(TARGET_GUILD_ID)
        if guild:
            await levels.setup_roles(guild)
        else:
            print(f"[main] Warning: bot is not in target guild {TARGET_GUILD_ID}")

    async def on_message(self, message):
        if message.author.bot:
            return
        if message.guild is None or message.guild.id != TARGET_GUILD_ID:
            return

        if message.content == "?louis":
            await message.reply('Truly a peak moment')

        if message.content == "?IQ":
            await message.reply('Big Brain IQ 🧠')
        
        if message.content == "?unc":
            await message.reply('so tuff🥶')

        if message.content == "!level":
            target = message.mentions[0] if message.mentions else message.author
            text = levels.get_rank_text(target.id, message.guild.id, target.display_name)
            await message.reply(text)

        if message.content == "!top":
            top = levels.get_leaderboard(message.guild.id, limit=10)
            if not top:
                await message.reply("No one has earned XP yet.")
            else:
                lines = []
                for i, (user_id, xp, level) in enumerate(top, start=1):
                    member = message.guild.get_member(user_id)
                    name = member.display_name if member else f"User {user_id}"
                    lines.append(f"**#{i}** {name} — Level {level} ({xp} XP)")
                await message.reply("**🏆 Leaderboard**\n" + "\n".join(lines))


        if message.content.startswith("!give"):
            if message.author.id != OWNER_ID:
                await message.reply("You don't have permission to use this command.")
            elif not message.mentions:
                await message.reply("Usage: `!give @user <amount>`")
            else:
                parts = message.content.split()
                try:
                    amount = int(parts[-1])
                except ValueError:
                    await message.reply("Usage: `!give @user <amount>` — amount must be a number.")
                else:
                    target = message.mentions[0]
                    xp, level, leveled_up = await levels.grant_xp(target, amount)
                    await message.reply(
                        f"Gave **{amount} XP** to {target.mention}. "
                        f"They're now **level {level}** ({xp} XP)."
                    )
                    if leveled_up:
                        await message.channel.send(
                            f"🎉 {target.mention} leveled up to **level {level}**!"
                        )

        await levels.handle_message(message)

        if message.content.startswith("!warning"):
            if message.guild is None or message.guild.id != TARGET_GUILD_ID:
                return
            if not message.mentions:
                await message.reply("Usage: `!warning @user <reason>`")
                return
            parts = message.content.split(maxsplit=2)
            if len(parts) < 3:
                await message.reply("Usage: `!warning @user <reason>`")
                return
            target = message.mentions[0]
            if target.id == self.user.id:
                await message.reply("I can't warn myself.")
                return
            if target.bot:
                await message.reply("I can't warn other bots.")
                return
            reason = parts[2]

            count = add_warning(message.guild.id, target.id, reason, message.author.id)

            try:
                await target.send(f"You have been warned in {message.guild.name}\nReason: {reason}\nTotal warnings: {count}")
                await message.reply(f"Warned {target.mention} via DM.\nReason: {reason}\nTotal warnings: {count}")
            except discord.Forbidden:
                await message.reply(f"Could not DM {target.mention} (DMs disabled). Warned here.\nReason: {reason}\nTotal warnings: {count}")
                await message.channel.send(f"{target.mention} **Warning:** {reason}\nTotal warnings: {count}")

        if message.content.startswith("!warnings"):
            if message.guild is None or message.guild.id != TARGET_GUILD_ID:
                return
            target = message.mentions[0] if message.mentions else message.author
            data = get_warnings(message.guild.id, target.id)
            count = data["count"]
            history = data["history"]
            if count == 0:
                await message.reply(f"{target.display_name} has no warnings.")
            else:
                lines = [f"**{target.display_name}** has **{count}** warning(s):"]
                for h in history:
                    mod = message.guild.get_member(h["moderator"])
                    mod_name = mod.display_name if mod else f"User {h['moderator']}"
                    lines.append(f"  #{h['count']}: {h['reason']} (by {mod_name})")
                await message.reply("\n".join(lines))

        if message.content == "!shutdown":
            if message.author.id == OWNER_ID:
                await message.reply("Shutting down...")
                await self.close()
            else:
                await message.reply("You do not have permission to shut down this bot.")


intents = discord.Intents.default()
intents.message_content = True
intents.members = True

client = Client(intents=intents)
client.run(DISCORD_KEY)