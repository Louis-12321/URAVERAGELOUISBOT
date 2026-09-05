import discord
import json
import os
import random
import time

DB_FILE = "levels.json"

# Level thresholds -> role name. Roles are given CUMULATIVELY,
# meaning a level 23 member gets "lvl 0+", "lvl 5+", "lvl 10+" and "lvl 20+".
# Make sure these role names exist in your server (or let setup_roles create them).
LEVEL_ROLES = {
    0: "lvl 0+",
    5: "lvl 5+",
    10: "lvl 10+",
    20: "lvl 20+",
    30: "lvl 30+",
    40: "lvl 40+",
    50: "lvl 50+",
    60: "lvl 60+",
    70: "lvl 70+",
    80: "lvl 80+",
    90: "lvl 90+",
    100: "lvl 100+",
}

XP_COOLDOWN = 1      # seconds a user must wait between XP gains
XP_MIN = 10           # min xp per message
XP_MAX = 20           # max xp per message

# in-memory cooldown tracker: (guild_id, user_id) -> last timestamp
_cooldowns = {}

# In-memory copy of the JSON data, loaded once and kept in sync on every write.
# Structure: { "guild_id": { "user_id": {"xp": int, "level": int} } }
# (JSON object keys are always strings, so ids are stored as strings and
# converted back to int wherever they're returned.)
_data = {}


def _load_data():
    global _data
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                _data = json.load(f)
        except (json.JSONDecodeError, OSError):
            _data = {}
    else:
        _data = {}


def _save_data():
    with open(DB_FILE, "w") as f:
        json.dump(_data, f, indent=4)


_load_data()


def xp_for_level(level: int) -> int:
    """XP required to go from `level` to `level + 1`."""
    return 5 * (level ** 2) + 50 * level + 100


def get_user(guild_id: int, user_id: int):
    """Returns (xp, level) for a user, defaulting to (0, 0)."""
    guild = _data.get(str(guild_id), {})
    entry = guild.get(str(user_id))
    if entry is None:
        return 0, 0
    return entry["xp"], entry["level"]


def set_user(guild_id: int, user_id: int, xp: int, level: int):
    guild = _data.setdefault(str(guild_id), {})
    guild[str(user_id)] = {"xp": xp, "level": level}
    _save_data()


def get_leaderboard(guild_id: int, limit: int = 10):
    """Returns top users as a list of (user_id, xp, level)."""
    guild = _data.get(str(guild_id), {})
    rows = [
        (int(user_id), entry["xp"], entry["level"])
        for user_id, entry in guild.items()
    ]
    rows.sort(key=lambda r: (r[2], r[1]), reverse=True)  # by level, then xp
    return rows[:limit]


def get_rank_text(user_id: int, guild_id: int, display_name: str) -> str:
    """Builds a short rank summary for a user, used by the !rank command."""
    xp, level = get_user(guild_id, user_id)
    needed = xp_for_level(level)
    return (
        f"**{display_name}**\n"
        f"Level: **{level}**\n"
        f"XP: **{xp} / {needed}**"
    )


MAX_XP_GAIN = 100000


def _xp_to_level(total_xp: int) -> tuple[int, int]:
    """Convert total XP to (level, remaining_xp) without looping."""
    level = 0
    while True:
        needed = xp_for_level(level)
        if total_xp < needed:
            break
        total_xp -= needed
        level += 1
    return level, total_xp


async def grant_xp(member: discord.Member, amount: int):
    """
    Adds `amount` xp to a member, handles any level-ups, and updates roles.
    Returns (new_xp, new_level, leveled_up). Used both by normal chat XP
    and by admin commands like !give.
    """
    if amount > MAX_XP_GAIN:
        amount = MAX_XP_GAIN

    guild_id = member.guild.id
    user_id = member.id
    xp, level = get_user(guild_id, user_id)

    total_xp = xp + amount
    new_level, remaining_xp = _xp_to_level(total_xp)
    leveled_up = new_level > level

    set_user(guild_id, user_id, remaining_xp, new_level)

    if leveled_up:
        await assign_roles(member, new_level)

    return remaining_xp, new_level, leveled_up


async def handle_message(message: discord.Message):
    """Call this from on_message for every message. Handles XP gain + leveling."""
    if message.author.bot:
        return
    if message.guild is None:  # ignore DMs
        return

    guild_id = message.guild.id
    user_id = message.author.id
    key = (guild_id, user_id)
    now = time.time()

    # cooldown check
    if now - _cooldowns.get(key, 0) < XP_COOLDOWN:
        remaining = round(XP_COOLDOWN - (now - _cooldowns.get(key, 0)), 1)
        print(f"[levels] {message.author} is on cooldown, {remaining}s left")
        return
    _cooldowns[key] = now

    gained = random.randint(XP_MIN, XP_MAX)
    xp, level, leveled_up = await grant_xp(message.author, gained)
    print(f"[levels] {message.author} gained {gained} xp (total {xp}, level {level})")

    if leveled_up:
        try:
            await message.channel.send(
                f"🎉 {message.author.mention} leveled up to **level {level}**!"
            )
        except discord.Forbidden:
            pass


# Cache of {guild_id: {threshold: discord.Role}} so we don't scan guild.roles
# (which can be a long list) on every single message.
_role_cache = {}


def _get_role_map(guild: discord.Guild):
    role_map = _role_cache.get(guild.id)
    if role_map is None:
        role_map = {}
        for threshold, role_name in LEVEL_ROLES.items():
            role = discord.utils.get(guild.roles, name=role_name)
            if role:
                role_map[threshold] = role
        _role_cache[guild.id] = role_map
    return role_map


def _invalidate_role_cache(guild: discord.Guild):
    _role_cache.pop(guild.id, None)


async def assign_roles(member: discord.Member, level: int):
    """
    Gives the member ONLY the highest level role they qualify for, swapping
    out any older one. E.g. reaching level 30 removes "lvl 20+" and adds
    "lvl 30+" instead of stacking every role.
    """
    guild = member.guild
    role_map = _get_role_map(guild)
    if not role_map:
        return

    # highest threshold this member currently qualifies for
    target_threshold = max((t for t in role_map if level >= t), default=None)
    if target_threshold is None:
        return
    target_role = role_map[target_threshold]

    all_level_roles = set(role_map.values())
    member_level_roles = set(member.roles) & all_level_roles

    # already exactly correct -> skip, no API calls needed (keeps it fast)
    if member_level_roles == {target_role}:
        return

    to_remove = member_level_roles - {target_role}
    to_add = set() if target_role in member_level_roles else {target_role}

    try:
        if to_remove:
            await member.remove_roles(*to_remove, reason="Level role update")
        if to_add:
            await member.add_roles(*to_add, reason="Level role reward")
    except discord.Forbidden:
        print(f"[levels] Missing permission to manage roles for {member} in {guild.name}")


async def setup_roles(guild: discord.Guild):
    """
    Optional helper: call once per guild (e.g. in on_ready) to auto-create
    any missing level roles so you don't have to make all 12 by hand.
    """
    created_any = False
    for threshold, role_name in LEVEL_ROLES.items():
        role = discord.utils.get(guild.roles, name=role_name)
        if role is None:
            try:
                await guild.create_role(name=role_name, reason="Auto-created level role")
                print(f"[levels] Created role '{role_name}' in {guild.name}")
                created_any = True
            except discord.Forbidden:
                print(f"[levels] Missing permission to create roles in {guild.name}")
    if created_any:
        _invalidate_role_cache(guild)