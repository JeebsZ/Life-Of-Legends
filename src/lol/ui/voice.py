"""Luma's voice: every line the in-app assistant says, in one place.

Luma is calm, precise and kind - a slightly formal inner assistant that reports what
happened ("Notice:", "Confirmed:"), proposes ("Proposal:"), warns gently ("Advisory:") and
reads the numbers ("Analysis:"). It never guilts, scolds or counts what you missed against you.

Use `say(kind, **values)`. Each kind has 2-3 variants that rotate in turn (not randomly), so
the same moment twice in a row reads differently. Tune wording here only. No Flet imports.
"""

from __future__ import annotations

from collections import defaultdict

NAME = "Luma"

LINES: dict[str, tuple[str, ...]] = {
    # --- rewards ----------------------------------------------------------------------------
    "quest_done": (
        "Notice: Quest cleared. +{xp} XP to {path} Path.",
        "Notice: Objective complete. {path} Path gains {xp} XP.",
        "Confirmed: Quest cleared. +{xp} XP recorded for {path} Path.",
    ),
    "coin_cap": (
        "Notice: Today's coin limit reached. Experience still counts.",
        "Notice: Coin reserve full for today. XP continues to accumulate.",
        "Notice: Daily coin limit reached. Coins refill tomorrow; XP still counts.",
    ),
    "path_level": (
        "Confirmed: {path} Path has reached Lv {level}.",
        "Confirmed: {path} Path advanced to Lv {level}.",
        "Confirmed: Growth detected. {path} Path is now Lv {level}.",
    ),
    "level_up": (
        "Notice: Individual level increased → Lv {level}.",
        "Confirmed: Overall level raised to Lv {level}.",
        "Notice: Level threshold crossed. You are now Lv {level}.",
    ),
    "skill_acquired": (
        "Skill acquired: {skill}.",
        "Notice: New skill acquired: {skill}.",
        "Confirmed: Skill acquired: {skill}. Well done.",
    ),
    "quest_accepted": (
        "Confirmed: \"{title}\" added to Today.",
        "Confirmed: Proposal accepted. \"{title}\" is on your list.",
        "Notice: \"{title}\" registered for today.",
    ),
    # --- quest board ------------------------------------------------------------------------
    "board_header": (
        "Proposal:",
        "Proposal: suited to now",
        "Proposal: worth a try",
    ),
    "board_analysis": (
        "Analysis: {minutes}, {difficulty}.",
        "Analysis: about {minutes}; {difficulty}.",
        "Analysis: {minutes} estimated, {difficulty}.",
    ),
    # --- bills ------------------------------------------------------------------------------
    "bill_due": (
        "Advisory: {bill} {when}.",
        "Advisory: {bill} {when}. A quick look keeps things calm.",
        "Advisory: {bill} {when}. Tap to review.",
    ),
    "bill_paid": (
        "Confirmed: Payment recorded. Steward Path +{xp} XP.",
        "Confirmed: {bill} paid. Steward Path +{xp} XP.",
        "Confirmed: Payment logged. +{xp} XP to Steward Path.",
    ),
    "bill_marked": (
        "Confirmed: {bill} marked paid.",
        "Confirmed: Payment for {bill} recorded.",
    ),
    # --- shop -------------------------------------------------------------------------------
    "reward_redeemed": (
        "Confirmed: Reward granted. Enjoy it, you earned it.",
        "Confirmed: {reward} granted. Enjoy it, you earned it.",
        "Confirmed: Reward released. {reward} is yours. Enjoy.",
    ),
    "theme_bought": (
        "Confirmed: {theme} theme unlocked. Tap Use to apply it.",
        "Confirmed: {theme} theme acquired. Apply it whenever you like.",
        "Notice: {theme} theme added to your collection.",
    ),
    # --- gentle moments ---------------------------------------------------------------------
    "comeback": (
        "Resuming is also a skill. Shall we continue?",
        "Picking up again counts. Shall we continue?",
        "No catching up needed. Shall we continue from here?",
    ),
    # app open / resume (core/welcome.py picks the variant: index i fits welcome.SLOTS[i])
    "hello_again": (
        "Good morning. Luma online. Your quests are ready when you are.",
        "Welcome back. Luma online. Your quests are waiting.",
        "Systems restored. Welcome back. Shall we continue?",
        "Good evening. Welcome back. One small step is plenty tonight.",
        "Welcome back. The hour is late. Rest counts as progress too.",
        "Welcome back. It has been a few days. We begin again from here.",
    ),
    "empty_today": (
        "No active quests. Proposal: Ask Luma for one.",
        "No active quests. Proposal: add one, or Ask Luma.",
        "Nothing scheduled yet. Proposal: Ask Luma for a quest.",
    ),
    "skills_empty": (
        "No skills recorded yet. Proposal: finish a side quest to acquire your first.",
        "Analysis: no skills yet. A side quest of three small steps is a fine start.",
    ),
    # --- side quests and skills -------------------------------------------------------------
    "practiced": (
        "Notice: New practice recorded: {title}.",
        "Notice: Practice logged: {title}.",
    ),
    "side_quest_started": (
        "Confirmed: Side quest begun: {skill}.",
        "Confirmed: {skill} chain started. One step at a time.",
        "Notice: Side quest registered: {skill}.",
    ),
    "side_quest_made": (
        "Confirmed: Your side quest is ready: {skill}.",
        "Confirmed: Custom chain registered: {skill}.",
    ),
    "side_quest_set_aside": (
        "Notice: {skill} set aside. You can pick it up again anytime.",
        "Notice: Side quest paused. Earned XP stays yours.",
    ),
    "rank_up_started": (
        "Confirmed: Rank-up chain begun: {skill}.",
        "Confirmed: {skill} training continues.",
    ),
    "skill_ranked": (
        "Confirmed: {skill} ranked up.",
        "Notice: Skill rank increased: {skill}.",
    ),
    # --- onboarding / profile ---------------------------------------------------------------
    "greeting": (
        "Hello. I am Luma. I will guide your progress.",
        "Hello. I am Luma. Shall we begin?",
    ),
    "welcome": (
        "Confirmed: Profile registered. Your legend begins.",
        "Confirmed: Welcome aboard. Shall we begin?",
    ),
    "profile_saved": (
        "Confirmed: Profile updated.",
        "Confirmed: Changes recorded.",
    ),
    "report_title": (
        "Luma Report",
        "Luma Report · this week",
        "Luma Report · 7-day analysis",
    ),
}

DIFFICULTY_WORDS = {1: "beginner-friendly", 2: "a steady challenge", 3: "a real stretch"}

_turn: defaultdict[str, int] = defaultdict(int)


def say(kind: str, **values: object) -> str:
    """Next variant of a Luma line, filled with values. Unknown kind -> KeyError."""
    variants = LINES[kind]
    i = _turn[kind] % len(variants)
    _turn[kind] += 1
    return variants[i].format(**values)


def minutes_text(minutes: int | None) -> str:
    """'10 min', '1 h 30 min', or 'a short while' when unknown."""
    if not minutes:
        return "a short while"
    h, m = divmod(int(minutes), 60)
    if not h:
        return f"{m} min"
    return f"{h} h" + (f" {m} min" if m else "")


def difficulty_text(difficulty: int) -> str:
    return DIFFICULTY_WORDS.get(max(1, min(3, int(difficulty))), DIFFICULTY_WORDS[1])
