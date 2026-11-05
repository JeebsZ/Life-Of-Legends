# v1 build spec — shared contract for all builders

Source: the user's ChatGPT design chat ("LifeQuest"), adapted to this repo. Working choices marked **(WC)** are open questions for the user and must stay easy to change, so keep them in config or constants.

## Scope for this build
| In | Out (later or flagged) |
|---|---|
| Today screen: today's quests, one-tap complete, XP and coins | Meal photo scan (plan only) |
| Paths: Chef, Warrior, Scholar, Artisan, Ranger, Steward. Each has its own XP and level | Selfie/face scan (flagged, not built) |
| Quest kinds: `once`, `daily` (resets each day), with optional note | Push reminders and notifications |
| Quest Board: "Give me a quest" picks from a built-in catalog by Path and difficulty. Accept / reroll / skip | Bank links, accounts, cloud sync |
| Coins: earned per quest, **daily cap (WC: 200)**. Never removed | Real coupons |
| Rewards Shop: user-made personal rewards (e.g. "Jollibee meal") with a coin price, plus cosmetic **themes** bought with coins | |
| Bills: name, amount (PHP), due date, repeat (none/weekly/monthly/yearly), mark paid, due-soon/overdue, upcoming total. Paying a bill = small Steward XP | |
| Logbook: workout, sleep, note entries | |
| Weekly review: done vs skipped, XP per Path, best streak | |
| Streaks with grace: a miss never removes XP or coins. Show "resume", not "failed" | |
| Export: save file is human-readable JSON | |

## Core API (in `src/lol/core`, pure Python, no flet import)
- `models.py` dataclasses: `PathDef(id, name, icon, color)`, `Quest(id, title, path_id, kind, xp, coins, difficulty, note, created, done_on: list[str ISO dates])`, `Bill(id, name, amount, due: date ISO, repeat, paid: list[ISO dates])`, `Reward(id, title, cost, kind: "personal"|"theme", theme_id|None, redeemed: list[ISO])`, `LogEntry(id, day, kind: "workout"|"sleep"|"note", text, minutes|None)`, `Profile(name, level, xp, coins, path_xp: dict[str,int], theme_id, owned_themes: list[str], coins_today: int, coins_day: str)`.
- `game.py` → `class Game` (all state + rules), built from `Game.load(path)` / `game.save(path)`.
  - `paths() -> list[PathDef]`, `path_level(path_id) -> (level, xp_in_level, xp_to_next)`
  - `today_quests(today) -> list[Quest]` (daily not done today + once not done + done today)
  - `is_done(quest, today) -> bool`, `streak(quest, today) -> int`
  - `add_quest(title, path_id, kind="once", difficulty=1, note="") -> Quest`
  - `complete_quest(quest_id, today) -> Completion(xp, coins, levels_gained, path_id, path_levels_gained, capped: bool)`: idempotent per day
  - `suggest_quest(path_id|None, difficulty|None, rng) -> Quest` (not yet added), `accept(quest)`
  - `add_bill(...)`, `pay_bill(bill_id, today) -> Completion`, `bills_status(today) -> list[(Bill, status: "overdue"|"due_soon"|"upcoming"|"paid", next_due)]`, `upcoming_total(today, days=30)`
  - `add_reward(title, cost)`, `redeem(reward_id, today) -> bool` (fails if not enough coins), `buy_theme(theme_id) -> bool`, `set_theme(theme_id)`
  - `add_log(kind, text, minutes=None, today)`, `logs(day|None)`
  - `weekly_review(today) -> dict`
- Balance constants at the top of `game.py`: XP and coins per difficulty, daily coin cap, Steward XP per bill.
- `storage.py`: JSON with `"schema": 1`. **Must migrate the old v0 `hero.json`** (`name, level, xp, quests[{title,xp,stat,done}]`) with no data loss: hero XP/level becomes the overall profile, and old quests become `once` quests on a default Path.
- Keep `progression.xp_for_level` and `bar_steps` (the UI uses them for the overall level and per-Path levels).

## UI (in `src/lol/ui`, Flet 1.0.5)
- Bottom `NavigationBar`: **Today · Quests · Bills · Rewards · Me** (Me = profile, Paths, Logbook, Weekly review, theme picker).
- Mobile first: 375–390px wide, tap targets 48px or more, primary actions in thumb reach.
- Theme tokens in one place. Themes are the customization the player buys with coins (3 or more themes, 1 free).
- Keep and reuse the existing juice: XP bar fill, row pop, "+XP" floater, level-up banner, haptics. Add a coin "+N" too.
- No new dependencies. No git commands.
