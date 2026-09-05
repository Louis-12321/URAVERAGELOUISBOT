import levels  # reuse the same xp formula and file path so numbers always match the bot


def main():
    if not levels._data:
        print("No data yet — no one has earned XP.")
        return

    for guild_id, members in levels._data.items():
        rows = [(int(uid), e["xp"], e["level"]) for uid, e in members.items()]
        rows.sort(key=lambda r: (r[2], r[1]), reverse=True)  # by level, then xp

        print(f"\n=== Guild {guild_id} ({len(rows)} tracked members) ===")
        print(f"{'Rank':<6}{'User ID':<22}{'Level':<8}{'XP':<12}{'Next lvl at':<12}")
        for i, (user_id, xp, level) in enumerate(rows, start=1):
            needed = levels.xp_for_level(level)
            print(f"{i:<6}{user_id:<22}{level:<8}{xp:<12}{needed:<12}")


if __name__ == "__main__":
    main()