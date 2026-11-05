"""Personalize ("onboarding"): the answers -> a starter plan. Pure logic, no Flet.

Flow (the UI asks, this decides): focus areas (multi-select) -> "Do you relate?" statements ->
age band -> sex (BodyProfile.sex, optional) -> daily time budget + best time of day (+ an
explicit reminder opt-in) -> theme -> plan.

Rules (all numbers are the constants below):
- Paths: each picked focus area gives PRIMARY_W to its first Path and SECONDARY_W to the
  rest; "My phone eats my evenings" adds PHONE_BOOST to Monk. Ties keep PATH_ORDER. The top
  MAX_PATHS Paths with a score are recommended; fewer than MIN_PATHS are filled from
  DEFAULT_PATHS.
- Difficulty cap for the starter quests: 1 if the budget is <= EASY_BUDGET or the player said
  yes to "lose steam" / "never start"; else 2. Never 3 on day one.
- Minutes per starter quest: the budget (unknown = DEFAULT_MINUTES), at least MIN_QUEST_MIN;
  "never start" caps it at TINY_MIN so the first step is small.
- Starter quests: STARTER_COUNT from the base Quest Board, round-robin over the recommended
  Paths, easiest/shortest first that fit the caps; a Path with nothing that fits gives its
  gentlest quest. "Phone" prefers PHONE_PICKS when they fit.
- Reminder default: DAY_TIMES[day_time] becomes the daily reminder time. Reminders are only
  switched on by an explicit "on"; a first run without an answer leaves them off.
- Safety: the age band "13-17" marks a minor (Game.is_minor): no weight-loss plans and no
  run-ladder challenges, exactly like an under-18 Body age. The band is never an exact age.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING

from lol.core import catalog
from lol.core.models import CatalogChain, CatalogQuest, OnboardingAnswers, Quest

if TYPE_CHECKING:
    from lol.core.game import Game

# --- answers ---------------------------------------------------------------------------------
# id -> (label, Paths it feeds, first = main)
FOCUS_AREAS: dict[str, tuple[str, tuple[str, ...]]] = {
    "mind": ("Mind & focus", ("scholar", "monk")),
    "habits": ("Daily habits", ("monk", "steward")),
    "energy": ("Energy & fitness", ("warrior", "ranger")),
    "food": ("Food & cooking", ("chef", "warrior")),
    "money": ("Money", ("steward",)),
    "home": ("Home & self-care", ("steward", "monk")),
    "creativity": ("Creativity", ("artisan",)),
    "outside": ("Outdoors & people", ("ranger", "artisan")),
}
STATEMENTS: tuple[tuple[str, str], ...] = (
    ("fade", "I start strong, then lose steam by day three."),
    ("phone", "My phone quietly eats my evenings."),
    ("stuck", "I know what to do. Starting is the hard part."),
)
STATEMENT_IDS: tuple[str, ...] = tuple(s[0] for s in STATEMENTS)
AGE_BANDS: tuple[str, ...] = ("13-17", "18-24", "25-34", "35-44", "45-54", "55+")
MINOR_BANDS: frozenset[str] = frozenset({"13-17"})
TIME_BUDGETS: tuple[int, ...] = (5, 15, 30, 60)  # minutes a day
DAY_TIMES: dict[str, tuple[str, str]] = {  # id -> (label, daily reminder "HH:MM")
    "morning": ("Morning", "08:00"),
    "midday": ("Midday", "12:30"),
    "evening": ("Evening", "19:00"),
    "night": ("Late evening", "21:00"),
}
REMINDER_CHOICES = ("on", "off", "")

# --- balance ---------------------------------------------------------------------------------
PATH_ORDER: tuple[str, ...] = catalog.PATH_IDS
PRIMARY_W, SECONDARY_W, PHONE_BOOST = 2, 1, 1
MAX_PATHS, MIN_PATHS = 3, 2
DEFAULT_PATHS: tuple[str, ...] = ("monk", "scholar", "warrior")
STARTER_COUNT = 3
EASY_BUDGET = 15  # minutes; at or below this the starters stay difficulty 1
DEFAULT_MINUTES = 15
MIN_QUEST_MIN = 5
TINY_MIN = 10
MAX_STARTER_DIFFICULTY = 2
PHONE_PICKS: tuple[str, ...] = ("Make a calm evening wind-down", "Take three slow breaths")


@dataclass(frozen=True)
class Plan:
    paths: tuple[str, ...]  # recommended, best first (2-3)
    quests: tuple[CatalogQuest, ...]  # starter quests (STARTER_COUNT)
    difficulty: int  # cap used for the starters (1-2)
    max_minutes: int  # per-quest cap used
    reminder_time: str  # "HH:MM", "" = keep the current daily reminder time
    minor: bool  # age band says under 18
    lines: tuple[str, ...] = field(default_factory=tuple)  # Luma's notes for the reveal


# --- pure rules ------------------------------------------------------------------------------
def is_minor(age_band: str | None) -> bool:
    return (age_band or "") in MINOR_BANDS


def path_scores(focus: Iterable[str], relate: dict[str, bool] | None = None) -> dict[str, int]:
    scores = {p: 0 for p in PATH_ORDER}
    for fid in dict.fromkeys(focus):  # unique, order kept
        paths = FOCUS_AREAS.get(fid, ("", ()))[1]
        for i, pid in enumerate(paths):
            scores[pid] += PRIMARY_W if i == 0 else SECONDARY_W
    if (relate or {}).get("phone"):
        scores["monk"] += PHONE_BOOST
    return scores


def rank_paths(focus: Iterable[str], relate: dict[str, bool] | None = None) -> tuple[str, ...]:
    scores = path_scores(focus, relate)
    ranked = sorted((p for p in PATH_ORDER if scores[p] > 0),
                    key=lambda p: (-scores[p], PATH_ORDER.index(p)))[:MAX_PATHS]
    for pid in DEFAULT_PATHS:
        if len(ranked) >= MIN_PATHS:
            break
        if pid not in ranked:
            ranked.append(pid)
    return tuple(ranked)


def difficulty_for(minutes: int, relate: dict[str, bool] | None = None) -> int:
    r = relate or {}
    if r.get("fade") or r.get("stuck") or (minutes or DEFAULT_MINUTES) <= EASY_BUDGET:
        return 1
    return MAX_STARTER_DIFFICULTY


def minutes_cap(minutes: int, relate: dict[str, bool] | None = None) -> int:
    cap = max(MIN_QUEST_MIN, minutes or DEFAULT_MINUTES)
    if (relate or {}).get("stuck"):
        cap = min(cap, TINY_MIN)
    return cap


def reminder_time(day_time: str) -> str:
    return DAY_TIMES.get(day_time, ("", ""))[1]


def _gentlest(pool: Sequence[CatalogQuest]) -> CatalogQuest | None:
    return min(pool, key=lambda q: (q.difficulty, q.minutes), default=None)


def pick_quests(paths: Sequence[str], difficulty: int, cap: int, *, phone: bool = False,
                pool: Sequence[CatalogQuest] = catalog.BASE_QUEST_BOARD,
                count: int = STARTER_COUNT) -> tuple[CatalogQuest, ...]:
    """Round-robin over `paths`, easiest/shortest first within the caps (see module doc)."""
    out: list[CatalogQuest] = []
    if not paths:
        return ()
    rounds = 0
    while len(out) < count and rounds < count:
        added = False
        for pid in paths:
            if len(out) >= count:
                break
            taken = {q.title for q in out}
            mine = [q for q in pool if q.path_id == pid and q.title not in taken]
            fits = sorted((q for q in mine if q.difficulty <= difficulty and q.minutes <= cap),
                          key=lambda q: (q.difficulty, q.minutes, q.title))
            if phone and pid == "monk":
                preferred = sorted((q for q in fits if q.title in PHONE_PICKS),
                                   key=lambda q: PHONE_PICKS.index(q.title))
                fits = preferred + [q for q in fits if q not in preferred]
            pick = fits[0] if fits else (_gentlest(mine) if rounds == 0 else None)
            if pick is not None:
                out.append(pick)
                added = True
        rounds += 1
        if not added:
            break
    return tuple(out)


def luma_lines(answers: OnboardingAnswers, plan_paths: Sequence[str]) -> tuple[str, ...]:
    """Short, warm notes for the reveal. Never shaming."""
    r = answers.relate
    out: list[str] = []
    if r.get("fade"):
        out.append("Steady beats intense. I kept your first quests light, so day three "
                   "still feels easy.")
    if r.get("stuck"):
        out.append("Every first step is ten minutes or less. Starting is the whole win.")
    if r.get("phone"):
        out.append("I added a calm evening touch for the hours your phone likes to take.")
    if is_minor(answers.age_band):
        out.append("Some health tools stay in their gentlest mode for you. That's on "
                   "purpose.")
    if not out:
        out.append("Small wins, every day. Your Paths grow as you do.")
    return tuple(out[:3])


def build_plan(answers: OnboardingAnswers) -> Plan:
    paths = rank_paths(answers.focus, answers.relate)
    diff = difficulty_for(answers.minutes, answers.relate)
    cap = minutes_cap(answers.minutes, answers.relate)
    quests = pick_quests(paths, diff, cap, phone=bool(answers.relate.get("phone")))
    return Plan(paths, quests, diff, cap, reminder_time(answers.day_time),
                is_minor(answers.age_band), luma_lines(answers, paths))


def validate(answers: OnboardingAnswers) -> OnboardingAnswers:
    """Drop unknown values (an old or hand-edited save never breaks the plan)."""
    a = answers
    a.focus = [f for f in dict.fromkeys(a.focus) if f in FOCUS_AREAS]
    a.relate = {k: bool(v) for k, v in a.relate.items() if k in STATEMENT_IDS}
    if a.age_band not in AGE_BANDS:
        a.age_band = ""
    if a.minutes not in TIME_BUDGETS:
        a.minutes = 0
    if a.day_time not in DAY_TIMES:
        a.day_time = ""
    if a.reminders not in REMINDER_CHOICES:
        a.reminders = ""
    return a


def starter_chain(game: Game, path_id: str) -> CatalogChain | None:
    """First side quest to suggest: the Path's first hand-written rank-1 chain that can start
    now (beginner-friendly), else the game's usual pick."""
    for c in catalog.BASE_SIDE_QUESTS:
        if c.path_id == path_id and c.rank == 1 and game.can_start(c.id):
            return c
    return game.starter_side_quest(path_id)


# --- apply to a game -------------------------------------------------------------------------
def _open_titles(game: Game, today: date) -> set[str]:
    return {q.title.casefold() for q in game.quests
            if q.kind == "daily" or not game.is_done(q, today)}


def apply(game: Game, answers: OnboardingAnswers, today: date, *,
          first_run: bool) -> tuple[Plan, list[Quest]]:
    """Store the answers, set reminder defaults and add the starter quests (skipping any that
    are already open, so a redo never duplicates). Progress is never touched. Returns the plan
    and the quests actually added. Marks the profile onboarded."""
    a = validate(answers)
    plan = build_plan(a)
    a.paths, a.difficulty, a.done_on = list(plan.paths), plan.difficulty, today.isoformat()
    game.profile.onboarding = a
    if plan.reminder_time:
        game.set_reminders(daily_time=plan.reminder_time)
    if a.reminders == "on":
        game.set_reminders(enabled=True, daily_on=True)
    elif a.reminders == "off" or first_run:
        game.set_reminders(enabled=False)
    have = _open_titles(game, today)
    added: list[Quest] = []
    for c in plan.quests:
        if c.title.casefold() in have:
            continue
        q = game.add_quest(c.title, c.path_id, "once", c.difficulty, c.note, today, c.minutes)
        added.append(q)
    game.profile.onboarded = True
    return plan, added
