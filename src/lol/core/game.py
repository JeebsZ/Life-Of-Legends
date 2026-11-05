"""All game state and rules. Pure logic: dates come in as `datetime.date`, no flet, no clock.

Build with `Game.load(path)`, persist with `game.save(path)`.
"""

import calendar
import copy
import dataclasses
import itertools
import random
from collections.abc import Iterable
from datetime import date, datetime, time, timedelta
from pathlib import Path

from lol.core import catalog, storage
from lol.core.body import BodyMixin
from lol.core.models import (
    BILL_REPEATS,
    ENERGY_LEVELS,
    ENTRY_KINDS,
    FOCUS_MODES,
    LOG_KINDS,
    MAX_RANK,
    MODULES,
    QUEST_KINDS,
    WATER_UNITS,
    WEIGHT_UNITS,
    WORKOUT_TYPES,
    Bill,
    CatalogChain,
    CatalogQuest,
    CatalogStep,
    Completion,
    EnergyCheckin,
    Entry,
    ExerciseEntry,
    FocusSession,
    Insight,
    LogEntry,
    PathDef,
    PersonalRecord,
    Profile,
    Quest,
    QuestTemplate,
    Reminder,
    Reward,
    SaveData,
    SideQuest,
    Skill,
    SleepEntry,
    Step,
    ThemeDef,
    WaterEntry,
    WorkoutSession,
    WorkoutTemplate,
)
from lol.core.premium import PremiumMixin
from lol.core.progression import xp_for_level
from lol.core.runlog import RunMixin
from lol.core.study import StudyMixin

# --- Balance (working choices: tweak here) ---------------------------------------------------
XP_BY_DIFFICULTY = {1: 20, 2: 40, 3: 70}
COINS_BY_DIFFICULTY = {1: 10, 2: 20, 3: 35}
DAILY_COIN_CAP = 200  # coins earned per day from quests and bills; spending is not capped
STEWARD_BILL_XP = 15  # XP for paying a bill (goes to the Steward Path)
STEWARD_BILL_COINS = 5
STEWARD_PATH = "steward"
DUE_SOON_DAYS = 3  # a bill due within this many days is "due_soon"
STREAK_GRACE_DAYS = 1  # missed days allowed between done days before a streak resets
WEEK_DAYS = 7
# Side quests: each step pays XP_BY_DIFFICULTY / COINS_BY_DIFFICULTY for its difficulty.
SKILL_BONUS_MULT = 2  # unlock / rank-up bonus XP = this x the chain's average step XP
SIDE_QUEST_MIN_STEPS = 1  # custom chains
SIDE_QUEST_MAX_STEPS = 5
CUSTOM_STEP_DIFFICULTY = 1  # default difficulty for custom chain steps
GENERATED_CHAIN_STEPS = 4  # default length of a generated learning chain (3..5)
# Editing: custom XP/coins on quests/templates are clamped to 0..(this x the difficulty default).
CUSTOM_REWARD_MAX_MULT = 1.5
XP_MAX_BY_DIFFICULTY = {
    d: int(v * CUSTOM_REWARD_MAX_MULT + 0.5) for d, v in XP_BY_DIFFICULTY.items()
}  # {1: 30, 2: 60, 3: 105}
COINS_MAX_BY_DIFFICULTY = {
    d: int(v * CUSTOM_REWARD_MAX_MULT + 0.5) for d, v in COINS_BY_DIFFICULTY.items()
}  # {1: 15, 2: 30, 3: 53}
# Focus timer: Path XP per full block of minutes, capped per day; coins are a small trickle and
# also count toward DAILY_COIN_CAP. Short or interrupted (partial) sessions count the same way.
FOCUS_BLOCK_MINUTES = 5
FOCUS_XP_PER_BLOCK = 2  # 25 min = 10 XP, 60 min = 24 XP
FOCUS_DAILY_XP_CAP = 60  # reached after 2.5 h of focus in one day
FOCUS_COIN_MINUTES = 15  # 1 coin per full 15 minutes
FOCUS_DAILY_COIN_CAP = 10
FOCUS_MAX_MINUTES = 240  # one logged session is clamped to this
# --- Phase 2 (v1.3): health tracking. Small, capped rewards; logging is never required. ------
WARRIOR_PATH = "warrior"
MONK_PATH = "monk"
# Workouts: Warrior XP (or the linked quest's / chosen Path) per full block of minutes, nudged
# a little by perceived effort, capped per day. Coins are a small trickle like focus.
WORKOUT_BLOCK_MINUTES = 5
WORKOUT_XP_PER_BLOCK = 2  # 30 min at effort 5 = 12 XP
WORKOUT_EFFORT_STEP = 0.05  # x(1 + step*(effort-5)): effort 1 = x0.8, effort 10 = x1.25
WORKOUT_MIN_XP = 5  # a session logged with no duration (e.g. sets only)
WORKOUT_DAILY_XP_CAP = 80
WORKOUT_COIN_MINUTES = 15  # 1 coin per full 15 minutes
WORKOUT_DAILY_COIN_CAP = 10
WORKOUT_MAX_MINUTES = 300  # one logged session is clamped to this
REST_TIMER_PRESETS = (60, 90, 120, 180)  # seconds; the UI runs the timer
# Sleep: a small Monk XP for logging a night; never for hitting any duration.
SLEEP_LOG_XP = 5
SLEEP_DAILY_XP_CAP = 5  # per calendar day of logging, so back-filling can't farm
SLEEP_MAX_NAP_MINUTES = 600
# Water: Monk XP once per day when the user's own goal is reached (nothing without a goal).
WATER_GOAL_XP = 10
WATER_MAX_ENTRY_ML = 5000
WATER_DEFAULT_QUICK_ML = (250, 500)
# Reminders
COMEBACK_DAYS = 3  # gentle nudge this many days after the last activity (opt-in)
WATER_DAY_START = "08:00"  # water reminder window when no overnight quiet hours are set
WATER_DAY_END = "21:00"
# Units: stored values are never converted; these are for display and input only.
LB_PER_KG = 2.20462
ML_PER_OZ = 29.5735
# ----------------------------------------------------------------------------------------------

_UNSET = object()  # "argument not given" where None is a real value (e.g. clear a date)


def _iso(d: date) -> str:
    return d.isoformat()


def _day(s: str) -> date:
    return date.fromisoformat(s)


def add_months(d: date, months: int) -> date:
    """Shift by whole months, clamping to month end (Jan 31 + 1 month = Feb 28/29)."""
    total = d.year * 12 + (d.month - 1) + months
    year, month = divmod(total, 12)
    month += 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def _shift(anchor: date, repeat: str, k: int) -> date:
    if repeat == "weekly":
        return anchor + timedelta(weeks=k)
    if repeat == "monthly":
        return add_months(anchor, k)
    if repeat == "yearly":
        return add_months(anchor, 12 * k)
    return anchor


def bill_occurrence(bill: Bill, n: int) -> date:
    """The due date of cycle n (0 = first). Paid cycles from before a schedule edit keep the
    date they covered (bill.paid_due). Other cycles are computed from the anchor (bill.due is
    cycle bill.start_cycle), so Jan 31 monthly goes Feb 28 -> Mar 31, never drifting to the 28th."""
    if n < bill.start_cycle and n < len(bill.paid_due):
        return _day(bill.paid_due[n])
    return _shift(_day(bill.due), bill.repeat, n - bill.start_cycle)


# --- units and times ----------------------------------------------------------------------------
def kg_to_lb(kg: float) -> float:
    return kg * LB_PER_KG


def lb_to_kg(lb: float) -> float:
    return lb / LB_PER_KG


def convert_weight(value: float, from_unit: str, to_unit: str) -> float:
    """Display helper; stored set weights keep the unit they were entered in."""
    for u in (from_unit, to_unit):
        if u not in WEIGHT_UNITS:
            raise ValueError(f"weight unit must be one of {WEIGHT_UNITS}")
    if from_unit == to_unit:
        return float(value)
    return kg_to_lb(value) if to_unit == "lb" else lb_to_kg(value)


def ml_to_oz(ml: float) -> float:
    return ml / ML_PER_OZ


def oz_to_ml(oz: float) -> float:
    return oz * ML_PER_OZ


def water_in(ml: float, unit: str) -> float:
    """ml shown in the user's water unit (rounded to 1 decimal for oz)."""
    if unit not in WATER_UNITS:
        raise ValueError(f"water unit must be one of {WATER_UNITS}")
    return float(ml) if unit == "ml" else round(ml_to_oz(ml), 1)


def parse_hm(value: str) -> time:
    """'HH:MM' (24 h) -> time. ValueError if malformed."""
    try:
        hh, mm = str(value).strip().split(":")
        return time(int(hh), int(mm))
    except (ValueError, TypeError) as e:
        raise ValueError(f"time must be HH:MM, got {value!r}") from e


def _hm(value: str) -> str:
    """Normalize 'H:MM' -> 'HH:MM' (validates)."""
    return parse_hm(value).strftime("%H:%M")


def sleep_minutes(bedtime: str, wake: str) -> int:
    """Minutes from bedtime to wake. A wake time at or before bedtime crossed midnight
    (23:30 -> 07:00 = 450). Equal times are rejected by log_sleep."""
    b, w = parse_hm(bedtime), parse_hm(wake)
    mins = (w.hour * 60 + w.minute) - (b.hour * 60 + b.minute)
    return mins if mins > 0 else mins + 24 * 60


def reward_limits(difficulty: int) -> tuple[int, int]:
    """(max_xp, max_coins) a custom quest/template of this difficulty may set."""
    if difficulty not in XP_BY_DIFFICULTY:
        raise ValueError(f"difficulty must be one of {sorted(XP_BY_DIFFICULTY)}")
    return XP_MAX_BY_DIFFICULTY[difficulty], COINS_MAX_BY_DIFFICULTY[difficulty]


def clamp_rewards(difficulty: int, xp: int | None, coins: int | None) -> tuple[int, int]:
    """(xp, coins) for a difficulty: None = the default, else clamped to 0..reward_limits."""
    max_xp, max_coins = reward_limits(difficulty)
    xp = XP_BY_DIFFICULTY[difficulty] if xp is None else min(max(0, int(xp)), max_xp)
    coins = COINS_BY_DIFFICULTY[difficulty] if coins is None else min(max(0, int(coins)), max_coins)
    return xp, coins


def _gain(level: int, xp: int, amount: int) -> tuple[int, int, int]:
    """Apply `amount` XP inside-level. Returns (level, xp, levels_gained)."""
    xp += amount
    gained = 0
    while xp >= xp_for_level(level):
        xp -= xp_for_level(level)
        level += 1
        gained += 1
    return level, xp, gained


def level_from_total(total_xp: int) -> tuple[int, int, int]:
    """(level, xp_in_level, xp_to_next) for a running XP total."""
    level, xp, _ = _gain(1, 0, max(0, total_xp))
    return level, xp, xp_for_level(level)


class Game(BodyMixin, RunMixin, StudyMixin, PremiumMixin):
    def __init__(self, data: SaveData | None = None) -> None:
        self.data = data or SaveData()

    # --- persistence ---------------------------------------------------------------------------
    @classmethod
    def load(cls, path: Path | None = None, today: date | None = None) -> "Game":
        return cls(storage.load(path, today))

    def save(self, path: Path | None = None) -> Path:
        return storage.save(self.data, path)

    # --- state shortcuts -----------------------------------------------------------------------
    @property
    def profile(self) -> Profile:
        return self.data.profile

    @property
    def quests(self) -> list[Quest]:
        return self.data.quests

    @property
    def bills(self) -> list[Bill]:
        """Bills that are not archived (a new list). data.bills holds all of them."""
        return [b for b in self.data.bills if not b.archived]

    @property
    def rewards(self) -> list[Reward]:
        """Rewards in the shop, i.e. not archived (a new list). data.rewards holds all."""
        return [r for r in self.data.rewards if not r.archived]

    def _new_id(self, prefix: str) -> str:
        n = self.data.next_id
        self.data.next_id += 1
        return f"{prefix}{n}"

    def _find(self, items: list, item_id: str):
        for item in items:
            if item.id == item_id:
                return item
        raise KeyError(item_id)

    def quest(self, quest_id: str) -> Quest:
        return self._find(self.quests, quest_id)

    def bill(self, bill_id: str) -> Bill:
        """Any bill by id, archived included."""
        return self._find(self.data.bills, bill_id)

    def reward(self, reward_id: str) -> Reward:
        """Any reward by id, archived included."""
        return self._find(self.data.rewards, reward_id)

    # --- paths and levels ----------------------------------------------------------------------
    def paths(self) -> list[PathDef]:
        return list(catalog.PATHS)

    def path_level(self, path_id: str) -> tuple[int, int, int]:
        """(level, xp_in_level, xp_to_next) for one Path."""
        return level_from_total(self.profile.path_xp.get(path_id, 0))

    def _award(self, xp: int, coins: int, path_id: str, today: date) -> Completion:
        """Give XP (overall + Path; path_id "" = overall only) and coins under the daily cap."""
        p = self.profile
        p.level, p.xp, levels = _gain(p.level, p.xp, xp)

        path_levels = 0
        if path_id:
            before = self.path_level(path_id)[0]
            p.path_xp[path_id] = p.path_xp.get(path_id, 0) + xp
            path_levels = self.path_level(path_id)[0] - before

        if p.coins_day != _iso(today):
            p.coins_day, p.coins_today = _iso(today), 0
        granted = max(0, min(coins, DAILY_COIN_CAP - p.coins_today))
        p.coins_today += granted
        p.coins += granted
        return Completion(xp, granted, levels, path_id, path_levels, capped=granted < coins)

    # --- quests --------------------------------------------------------------------------------
    def is_done(self, quest: Quest, today: date) -> bool:
        if quest.kind == "daily":
            return _iso(today) in quest.done_on
        return any(_day(d) <= today for d in quest.done_on)

    def today_quests(self, today: date) -> list[Quest]:
        """Open quests first (daily not done today, once never done), then done today."""
        t = _iso(today)
        open_ = [q for q in self.quests if not self.is_done(q, today)]
        done = [q for q in self.quests if t in q.done_on]
        return open_ + done

    def streak(self, quest: Quest, today: date) -> int:
        """Done-days in a row for a daily quest. Today not done yet does not break it, and up to
        STREAK_GRACE_DAYS missed days in a gap are forgiven. A miss never costs XP or coins."""
        if quest.kind != "daily":
            return 0
        days = sorted({_day(d) for d in quest.done_on if _day(d) <= today}, reverse=True)
        max_gap = 1 + STREAK_GRACE_DAYS
        if not days or (today - days[0]).days > max_gap:
            return 0
        count = 1
        for newer, older in itertools.pairwise(days):
            if (newer - older).days > max_gap:
                break
            count += 1
        return count

    def add_quest(
        self,
        title: str,
        path_id: str,
        kind: str = "once",
        difficulty: int = 1,
        note: str = "",
        today: date | None = None,
        minutes: int | None = None,
        *,
        coins: int | None = None,
        xp: int | None = None,
    ) -> Quest:
        """Add a custom quest. coins/xp default to the difficulty's reward; given values are
        clamped to reward_limits(difficulty) so a custom quest can't be over-priced."""
        quest = self._make_quest(title, path_id, kind, difficulty, note, minutes)
        quest.xp, quest.coins = clamp_rewards(difficulty, xp, coins)
        return self.accept(quest, today)

    @staticmethod
    def _check_quest_fields(path_id: str, kind: str, difficulty: int) -> None:
        if path_id not in catalog.PATH_IDS:
            raise ValueError(f"unknown path: {path_id}")
        if kind not in QUEST_KINDS:
            raise ValueError(f"unknown quest kind: {kind}")
        if difficulty not in XP_BY_DIFFICULTY:
            raise ValueError(f"difficulty must be one of {sorted(XP_BY_DIFFICULTY)}")

    def _make_quest(
        self, title: str, path_id: str, kind: str, difficulty: int, note: str,
        minutes: int | None,
    ) -> Quest:
        self._check_quest_fields(path_id, kind, difficulty)
        title = title.strip()
        if not title:
            raise ValueError("quest title is empty")
        return Quest(
            id="", title=title, path_id=path_id, kind=kind,
            xp=XP_BY_DIFFICULTY[difficulty], coins=COINS_BY_DIFFICULTY[difficulty],
            difficulty=difficulty, note=note, minutes=minutes,
        )

    def edit_quest(
        self,
        quest_id: str,
        *,
        title: str | None = None,
        path_id: str | None = None,
        difficulty: int | None = None,
        kind: str | None = None,
        note: str | None = None,
        coins: int | None = None,
        xp: int | None = None,
        minutes=_UNSET,
    ) -> Quest:
        """Edit a quest in place; None = unchanged (minutes: omit = unchanged, None = clear).

        Completion history (done_on) is kept and XP/coins already earned never change; new
        values apply to future completions. Changing difficulty resets xp/coins to the new
        difficulty's defaults unless given. Given values are clamped to reward_limits."""
        q = self.quest(quest_id)
        new_title = q.title if title is None else title.strip()
        if not new_title:
            raise ValueError("quest title is empty")
        new_path = q.path_id if path_id is None else path_id
        new_kind = q.kind if kind is None else kind
        new_diff = q.difficulty if difficulty is None else difficulty
        self._check_quest_fields(new_path, new_kind, new_diff)
        if new_diff != q.difficulty:
            q.xp, q.coins = clamp_rewards(new_diff, xp, coins)
        else:
            max_xp, max_coins = reward_limits(new_diff)
            if xp is not None:
                q.xp = min(max(0, int(xp)), max_xp)
            if coins is not None:
                q.coins = min(max(0, int(coins)), max_coins)
        q.title, q.path_id, q.kind, q.difficulty = new_title, new_path, new_kind, new_diff
        if note is not None:
            q.note = note
        if minutes is not _UNSET:
            q.minutes = minutes
        return q

    def complete_quest(self, quest_id: str, today: date) -> Completion:
        """Award a quest once per day (daily) or once ever (once). Repeats return all zeros."""
        quest = self.quest(quest_id)
        if self.is_done(quest, today) or (quest.kind == "once" and quest.done_on):
            return Completion(path_id=quest.path_id)
        quest.done_on.append(_iso(today))
        return self._award(quest.xp, quest.coins, quest.path_id, today)

    def rename_quest(
        self, quest_id: str, title: str | None = None, note: str | None = None,
        difficulty: int | None = None,
    ) -> Quest:
        """The player-facing quest edit (v1.3): name, note and difficulty only; None =
        unchanged. A difficulty change resets xp/coins to the new difficulty's defaults for
        FUTURE completions; earned XP/coins and done_on never change. Path, kind and rewards
        can't be set here (edit_quest stays for internal use)."""
        return self.edit_quest(quest_id, title=title, note=note, difficulty=difficulty)

    def delete_quest(self, quest_id: str) -> None:
        """Remove a quest. Already earned XP and coins stay."""
        self.data.quests.remove(self.quest(quest_id))

    # --- Quest Board ---------------------------------------------------------------------------
    def suggest_quest(
        self,
        path_id: str | None = None,
        difficulty: int | None = None,
        rng: random.Random | None = None,
        exclude: Iterable[str] = (),
    ) -> Quest:
        """A fresh catalog quest (NOT added yet; call accept). `exclude` = titles to skip, for
        reroll. Falls back to ignoring `exclude`, then `difficulty`, if nothing matches."""
        if path_id is not None and path_id not in catalog.PATH_IDS:
            raise ValueError(f"unknown path: {path_id}")
        rng = rng or random.Random()
        skip = set(exclude)
        pool = [c for c in catalog.QUEST_BOARD if path_id in (None, c.path_id)]
        by_diff = [c for c in pool if difficulty in (None, c.difficulty)]
        for candidates in ([c for c in by_diff if c.title not in skip], by_diff, pool):
            if candidates:
                pick = rng.choice(candidates)
                return self._make_quest(
                    pick.title, pick.path_id, "once", pick.difficulty, pick.note, pick.minutes
                )
        raise ValueError("quest catalog is empty")

    def accept(self, quest: Quest, today: date | None = None) -> Quest:
        """Add a (suggested) quest to the player's list. Returns it with an id."""
        quest.id = quest.id or self._new_id("q")
        quest.created = quest.created or _iso(today or date.today())
        self.data.quests.append(quest)
        return quest

    def practiced(self) -> list[CatalogQuest]:
        """Quest Board quests completed at least once (by title), oldest first completion first.
        Derived from quests' done_on, so no extra save data. (Was `skills()` before v1.1.)"""
        first: dict[str, str] = {}
        for q in self.quests:
            if q.done_on:
                day = min(q.done_on)
                first[q.title] = min(day, first.get(q.title, day))
        acquired = [c for c in catalog.QUEST_BOARD if c.title in first]
        return sorted(acquired, key=lambda c: first[c.title])

    # --- quest templates -----------------------------------------------------------------------
    def templates(self, include_hidden: bool = False) -> list[QuestTemplate]:
        """Built-in templates (edited copies replace the originals, hidden ones skipped unless
        include_hidden), then the player's own templates in creation order."""
        overrides = {t.id: t for t in self.data.templates}
        hidden = set(self.data.hidden_templates)
        out = [overrides.get(t.id, t) for t in catalog.builtin_templates()
               if include_hidden or t.id not in hidden]
        out += [t for t in self.data.templates if t.id not in catalog.TEMPLATE_IDS]
        return out

    def template(self, template_id: str) -> QuestTemplate:
        """A template by id (hidden built-ins included). KeyError if unknown."""
        return self._find(self.templates(include_hidden=True), template_id)

    def add_template(
        self,
        title: str,
        path_id: str,
        difficulty: int = 1,
        kind: str = "once",
        note: str = "",
        minutes: int | None = None,
        *,
        coins: int | None = None,
        xp: int | None = None,
    ) -> QuestTemplate:
        """A new player template; rewards default/clamp like add_quest."""
        self._check_quest_fields(path_id, kind, difficulty)
        title = title.strip()
        if not title:
            raise ValueError("template title is empty")
        xp, coins = clamp_rewards(difficulty, xp, coins)
        t = QuestTemplate(self._new_id("t"), title, note, path_id, difficulty, kind, minutes,
                          coins, xp, builtin=False)
        self.data.templates.append(t)
        return t

    def template_from_quest(self, quest_id: str) -> QuestTemplate:
        """Save a quest as a new player template (the quest is untouched)."""
        q = self.quest(quest_id)
        return self.add_template(q.title, q.path_id, q.difficulty, q.kind, q.note, q.minutes,
                                 coins=q.coins, xp=q.xp)

    def edit_template(
        self,
        template_id: str,
        *,
        title: str | None = None,
        note: str | None = None,
        path_id: str | None = None,
        difficulty: int | None = None,
        kind: str | None = None,
        minutes=_UNSET,
        coins: int | None = None,
        xp: int | None = None,
    ) -> QuestTemplate:
        """Edit a template; None = unchanged. Editing a built-in saves an edited copy (same id)
        in the save; restore_template brings back the original. Rewards follow edit_quest."""
        current = self.template(template_id)
        new_title = current.title if title is None else title.strip()
        if not new_title:
            raise ValueError("template title is empty")
        new_path = current.path_id if path_id is None else path_id
        new_kind = current.kind if kind is None else kind
        new_diff = current.difficulty if difficulty is None else difficulty
        self._check_quest_fields(new_path, new_kind, new_diff)
        if new_diff != current.difficulty:
            new_xp, new_coins = clamp_rewards(new_diff, xp, coins)
        else:
            new_xp, new_coins = clamp_rewards(
                new_diff, current.xp if xp is None else xp,
                current.coins if coins is None else coins)
        t = current
        if t.builtin and not any(x is t for x in self.data.templates):
            t = dataclasses.replace(current)
            self.data.templates.append(t)
        t.title, t.path_id, t.kind, t.difficulty = new_title, new_path, new_kind, new_diff
        t.xp, t.coins = new_xp, new_coins
        if note is not None:
            t.note = note
        if minutes is not _UNSET:
            t.minutes = minutes
        return t

    def delete_template(self, template_id: str) -> None:
        """Player templates are removed; built-ins are only hidden (restore_template undoes)."""
        t = self.template(template_id)
        if t.id in catalog.TEMPLATE_IDS:
            if t.id not in self.data.hidden_templates:
                self.data.hidden_templates.append(t.id)
        else:
            self.data.templates.remove(t)

    def restore_template(self, template_id: str) -> QuestTemplate:
        """Un-hide a built-in template and drop any edits to it."""
        if template_id not in catalog.TEMPLATE_IDS:
            raise KeyError(template_id)
        self.data.templates = [t for t in self.data.templates if t.id != template_id]
        self.data.hidden_templates = [i for i in self.data.hidden_templates if i != template_id]
        return self.template(template_id)

    def quest_from_template(self, template_id: str, today: date) -> Quest:
        """Add a new quest copied from a template. The template is not changed."""
        t = self.template(template_id)
        q = self.add_quest(t.title, t.path_id, t.kind, t.difficulty, t.note, today, t.minutes,
                           coins=t.coins, xp=t.xp)
        q.template_id = t.id
        return q

    # --- side quests and skills ----------------------------------------------------------------
    def side_quests(self, active_only: bool = False) -> list[SideQuest]:
        """All side quests in start order; active_only = not finished and not abandoned
        (paused chains are still active)."""
        return [sq for sq in self.data.side_quests if sq.active or not active_only]

    def side_quest(self, sq_id: str) -> SideQuest:
        return self._find(self.data.side_quests, sq_id)

    def side_quest_catalog(self, path_id: str | None = None) -> list[CatalogChain]:
        """Rank-1 preset chains (what "Start a side quest" lists), optionally for one Path.
        Follow-ups come from followups_for(skill)."""
        if path_id is not None and path_id not in catalog.PATH_IDS:
            raise ValueError(f"unknown path: {path_id}")
        return [c for c in catalog.SIDE_QUESTS if c.rank == 1 and path_id in (None, c.path_id)]

    def chain(self, catalog_id: str) -> CatalogChain:
        """A catalog chain by id, including generated follow-ups for custom skills."""
        if catalog_id in catalog.SIDE_QUEST_BY_ID:
            return catalog.SIDE_QUEST_BY_ID[catalog_id]
        prefix = catalog.CUSTOM_FOLLOWUP_PREFIX
        if catalog_id.startswith(prefix) and ":" in catalog_id:
            rank_s, name = catalog_id[len(prefix):].split(":", 1)
            skill = self.skill(name)
            if skill and rank_s.isdigit() and 2 <= int(rank_s) <= MAX_RANK:
                return catalog.generic_followup(skill.name, skill.path_id, int(rank_s))
        raise KeyError(catalog_id)

    def can_start(self, catalog_id: str) -> bool:
        """True if the chain is the skill's next rank and isn't already running."""
        try:
            c = self.chain(catalog_id)
        except KeyError:
            return False
        if any(sq.active and sq.catalog_id == c.id for sq in self.data.side_quests):
            return False
        skill = self.skill(c.skill_name)
        return c.rank == (skill.rank if skill else 0) + 1

    def start_side_quest(
        self, catalog_id: str, today: date, *, ordered: bool = False,
        target_date: date | None = None,
    ) -> SideQuest:
        """Start a preset chain (rank 1) or a follow-up the player chose (rank 2/3).
        Raises KeyError for an unknown id, ValueError if it can't be started now."""
        c = self.chain(catalog_id)
        if not self.can_start(c.id):
            raise ValueError(f"side quest {c.id} can't be started now")
        steps = [self._make_step(s.title, s.note, s.difficulty) for s in c.steps]
        sq = SideQuest(self._new_id("s"), c.skill_name, c.path_id, steps, custom=False,
                       rank_target=c.rank, created=_iso(today), catalog_id=c.id,
                       ordered=ordered, target_date=_iso(target_date) if target_date else None)
        self.data.side_quests.append(sq)
        return sq

    def add_side_quest(
        self,
        skill_name: str,
        path_id: str,
        steps: list[str | CatalogStep],
        difficulty: int = CUSTOM_STEP_DIFFICULTY,
        today: date | None = None,
        *,
        ordered: bool = False,
        target_date: date | None = None,
    ) -> SideQuest:
        """A custom chain of 1-5 steps; finishing it unlocks `skill_name` at rank 1.
        A step is a title (uses `difficulty`) or a CatalogStep (e.g. from generate_chain)."""
        if path_id not in catalog.PATH_IDS:
            raise ValueError(f"unknown path: {path_id}")
        if difficulty not in XP_BY_DIFFICULTY:
            raise ValueError(f"difficulty must be one of {sorted(XP_BY_DIFFICULTY)}")
        skill_name = skill_name.strip()
        if not skill_name:
            raise ValueError("skill name is empty")
        specs = [CatalogStep(s.strip(), "", difficulty) if isinstance(s, str)
                 else CatalogStep(s.title.strip(), s.note, s.difficulty) for s in steps]
        if not SIDE_QUEST_MIN_STEPS <= len(specs) <= SIDE_QUEST_MAX_STEPS:
            raise ValueError(
                f"a side quest needs {SIDE_QUEST_MIN_STEPS}-{SIDE_QUEST_MAX_STEPS} steps")
        if not all(s.title for s in specs):
            raise ValueError("a step title is empty")
        if any(s.difficulty not in XP_BY_DIFFICULTY for s in specs):
            raise ValueError(f"difficulty must be one of {sorted(XP_BY_DIFFICULTY)}")
        sq = SideQuest(self._new_id("s"), skill_name, path_id,
                       [self._make_step(s.title, s.note, s.difficulty) for s in specs],
                       custom=True, rank_target=1, created=_iso(today or date.today()),
                       ordered=ordered, target_date=_iso(target_date) if target_date else None)
        self.data.side_quests.append(sq)
        return sq

    @staticmethod
    def generate_chain(
        skill_name: str, path_id: str, steps: int = GENERATED_CHAIN_STEPS
    ) -> list[CatalogStep]:
        """A learning chain for any skill name (template-based, deterministic, 3-5 steps):
        learn basics -> guided practice -> (solo practice) -> apply in real life -> reflect.
        Nothing is added: preview it, then pass it to add_side_quest(..., ordered=True)."""
        if path_id not in catalog.PATH_IDS:
            raise ValueError(f"unknown path: {path_id}")
        skill_name = skill_name.strip()
        if not skill_name:
            raise ValueError("skill name is empty")
        return catalog.learning_chain(skill_name, path_id, steps)

    @staticmethod
    def _make_step(title: str, note: str, difficulty: int) -> Step:
        return Step(title, note, XP_BY_DIFFICULTY[difficulty], COINS_BY_DIFFICULTY[difficulty])

    @staticmethod
    def next_step(sq: SideQuest) -> int | None:
        """Index of the first unresolved (not done, not skipped) step; None if none left."""
        return next((i for i, s in enumerate(sq.steps) if not s.resolved), None)

    def can_complete_step(self, sq_id: str, step_index: int) -> bool:
        """False for abandoned/paused chains, resolved steps, and (ordered chains) any step
        but the next one."""
        sq = self.side_quest(sq_id)
        if not 0 <= step_index < len(sq.steps):
            raise IndexError(step_index)
        if sq.abandoned or sq.paused or sq.steps[step_index].resolved:
            return False
        return not sq.ordered or step_index == self.next_step(sq)

    def complete_step(self, sq_id: str, step_index: int, today: date) -> Completion:
        """Award a step once ever. Repeats, abandoned/paused chains and locked steps (ordered
        chains) return all zeros. Resolving the last open step unlocks the skill (rank 1) or
        ranks it up, with a bonus XP award."""
        sq = self.side_quest(sq_id)
        if not self.can_complete_step(sq_id, step_index):
            return Completion(path_id=sq.path_id)
        step = sq.steps[step_index]
        step.done_on = _iso(today)
        return self._resolve(sq, step.xp, step.coins, today)

    def skip_step(self, sq_id: str, step_index: int, today: date | None = None) -> Completion:
        """Skip a step: it counts as resolved (unlocks the next step, can finish the chain) but
        gives no XP or coins. Any unresolved step can be skipped. If this finishes the chain
        the skill still unlocks, as long as at least one step was actually done."""
        sq = self.side_quest(sq_id)
        if not 0 <= step_index < len(sq.steps):
            raise IndexError(step_index)
        step = sq.steps[step_index]
        if sq.abandoned or sq.paused or step.resolved:
            return Completion(path_id=sq.path_id)
        step.skipped_on = _iso(today or date.today())
        return self._resolve(sq, 0, 0, today or date.today())

    def unskip_step(self, sq_id: str, step_index: int) -> bool:
        """Undo a skip while the chain is unfinished. True if it was un-skipped."""
        sq = self.side_quest(sq_id)
        step = sq.steps[step_index]
        if sq.finished or not step.skipped_on:
            return False
        step.skipped_on = None
        return True

    def _resolve(self, sq: SideQuest, xp: int, coins: int, today: date) -> Completion:
        bonus, skill = 0, None
        if sq.finished and sq.done_count > 0:
            skill = self._advance_skill(sq, today)
            if skill:
                bonus = self.skill_bonus(sq)
        if xp == coins == bonus == 0:
            c = Completion(path_id=sq.path_id)
        else:
            c = self._award(xp + bonus, coins, sq.path_id, today)
        if skill:
            c.skill_unlocked, c.skill_rank = skill.name, skill.rank
        return c

    @staticmethod
    def skill_bonus(sq: SideQuest) -> int:
        """Bonus XP for unlocking / ranking up via this chain: about 2x an average step,
        scaled down by the share of skipped steps (so skipping isn't rewarded at full value)."""
        if not sq.steps:
            return 0
        full = SKILL_BONUS_MULT * round(sum(s.xp for s in sq.steps) / len(sq.steps))
        kept = sum(1 for s in sq.steps if not s.skipped_on)
        return round(full * kept / len(sq.steps))

    def reorder_steps(self, sq_id: str, new_order: list[int]) -> None:
        """Reorder steps: new_order lists the current indices in their new order (a permutation).
        Done/skipped state moves with each step."""
        sq = self.side_quest(sq_id)
        if sorted(new_order) != list(range(len(sq.steps))):
            raise ValueError("new_order must be a permutation of the step indices")
        sq.steps = [sq.steps[i] for i in new_order]

    def edit_step(
        self, sq_id: str, step_index: int, title: str | None = None, note: str | None = None
    ) -> Step:
        """Rename a step or change its note (rewards and done state unchanged)."""
        step = self.side_quest(sq_id).steps[step_index]
        if title is not None:
            if not title.strip():
                raise ValueError("a step title is empty")
            step.title = title.strip()
        if note is not None:
            step.note = note
        return step

    def edit_side_quest(self, sq_id: str, *, ordered: bool | None = None,
                        target_date=_UNSET) -> SideQuest:
        """Switch ordered/any-order or set the target date (a date, or None to clear)."""
        sq = self.side_quest(sq_id)
        if ordered is not None:
            sq.ordered = bool(ordered)
        if target_date is not _UNSET:
            sq.target_date = _iso(target_date) if target_date else None
        return sq

    def pause_side_quest(self, sq_id: str) -> None:
        """Pause an unfinished chain: no progress, hidden from Today. Earned XP stays."""
        sq = self.side_quest(sq_id)
        if sq.active:
            sq.paused = True

    def resume_side_quest(self, sq_id: str) -> None:
        self.side_quest(sq_id).paused = False

    def today_next_steps(self, today: date) -> list[tuple[SideQuest, int, Step]]:
        """(chain, step index, step) for the next step of every active, unpaused chain.
        Chains with the nearest target date come first, then the rest in start order.
        Target dates are only for sorting: a passed date is never flagged."""
        rows = []
        for sq in self.data.side_quests:
            i = self.next_step(sq)
            if sq.active and not sq.paused and i is not None:
                rows.append((sq, i, sq.steps[i]))
        return sorted(rows, key=lambda r: (r[0].target_date is None, r[0].target_date or ""))

    def _advance_skill(self, sq: SideQuest, today: date) -> Skill | None:
        """Unlock (rank 1) or rank up the chain's skill. None if this chain doesn't change it
        (e.g. a repeat rank-1 chain for a skill already unlocked)."""
        skill = self.skill(sq.skill_name)
        if skill is None:
            if sq.rank_target != 1:
                return None
            skill = Skill(sq.skill_name, sq.path_id, 1, _iso(today), [sq.id])
            self.data.skills.append(skill)
            return skill
        if sq.rank_target == skill.rank + 1 <= MAX_RANK:
            skill.rank += 1
            skill.chain_ids.append(sq.id)
            return skill
        return None

    def abandon_side_quest(self, sq_id: str) -> None:
        """Stop a chain. XP and coins from finished steps stay; it can be started again fresh.
        Finished chains can't be abandoned (no-op)."""
        sq = self.side_quest(sq_id)
        if not sq.finished:
            sq.abandoned = True

    def skills(self) -> list[Skill]:
        """Unlocked skills, in unlock order."""
        return list(self.data.skills)

    def skill(self, name: str) -> Skill | None:
        key = name.strip().casefold()
        return next((s for s in self.data.skills if s.name.casefold() == key), None)

    def followups_for(self, skill_name: str) -> list[CatalogChain]:
        """The next-rank follow-up chain for an unlocked skill ([] if locked or Adept). Catalog
        skills use their preset follow-up; custom skills get a generated one. The player starts
        it with start_side_quest(chain.id); check can_start (False while it is already running)."""
        skill = self.skill(skill_name)
        if skill is None or skill.rank >= MAX_RANK:
            return []
        rank = skill.rank + 1
        key = skill.name.casefold()
        for c in catalog.SIDE_QUESTS:
            if c.rank == rank and c.skill_name.casefold() == key:
                return [c]
        return [catalog.generic_followup(skill.name, skill.path_id, rank)]

    def starter_side_quest(self, path_id: str) -> CatalogChain | None:
        """First preset chain for a Path that can be started now (onboarding suggestion)."""
        return next((c for c in self.side_quest_catalog(path_id) if self.can_start(c.id)), None)

    # --- focus timer ---------------------------------------------------------------------------
    def log_focus(
        self,
        minutes: int,
        today: date,
        quest_id: str | None = None,
        path_id: str | None = None,
        note: str = "",
        partial: bool = False,
        *,
        mode: str = "focus",
        started: str = "",
    ) -> Completion:
        """Log a finished or partial focus/stopwatch session (minutes >= 1, clamped to
        FOCUS_MAX_MINUTES). XP = FOCUS_XP_PER_BLOCK per full FOCUS_BLOCK_MINUTES, up to
        FOCUS_DAILY_XP_CAP per day; coins = 1 per FOCUS_COIN_MINUTES, up to FOCUS_DAILY_COIN_CAP
        per day and the normal DAILY_COIN_CAP. XP goes to path_id, else the linked quest's Path,
        else overall XP only. A linked quest is NOT completed. Completion.ref_id = session id."""
        if mode not in FOCUS_MODES:
            raise ValueError(f"focus mode must be one of {FOCUS_MODES}")
        minutes = int(minutes)
        if minutes < 1:
            raise ValueError("a focus session needs at least 1 minute")
        minutes = min(minutes, FOCUS_MAX_MINUTES)
        if quest_id is not None:
            quest = self.quest(quest_id)  # KeyError if unknown
            path_id = path_id or quest.path_id
        if path_id is not None and path_id not in catalog.PATH_IDS:
            raise ValueError(f"unknown path: {path_id}")
        stats = self.focus_stats(today)
        xp = min(minutes // FOCUS_BLOCK_MINUTES * FOCUS_XP_PER_BLOCK,
                 max(0, FOCUS_DAILY_XP_CAP - stats["xp"]))
        coins = min(minutes // FOCUS_COIN_MINUTES, max(0, FOCUS_DAILY_COIN_CAP - stats["coins"]))
        c = self._award(xp, coins, path_id or "", today)
        session = FocusSession(self._new_id("f"), _iso(today), started, minutes, mode, quest_id,
                               path_id, note, bool(partial), c.xp, c.coins)
        self.data.focus_sessions.append(session)
        c.ref_id = session.id
        return c

    def focus_sessions(self, day: date | None = None) -> list[FocusSession]:
        """Sessions for one day, or all; newest first."""
        rows = list(reversed(self.data.focus_sessions))
        if day is not None:
            rows = [s for s in rows if s.day == _iso(day)]
        return sorted(rows, key=lambda s: s.day, reverse=True)

    def focus_stats(self, day: date) -> dict:
        """Keys: sessions, minutes, xp, coins (earned that day), xp_left (before the cap)."""
        rows = [s for s in self.data.focus_sessions if s.day == _iso(day)]
        xp = sum(s.xp for s in rows)
        return {
            "sessions": len(rows),
            "minutes": sum(s.minutes for s in rows),
            "xp": xp,
            "coins": sum(s.coins for s in rows),
            "xp_left": max(0, FOCUS_DAILY_XP_CAP - xp),
        }

    def delete_focus_session(self, session_id: str) -> None:
        """Remove a session from the log. XP and coins it earned stay."""
        self.data.focus_sessions.remove(self._find(self.data.focus_sessions, session_id))

    # --- profile -------------------------------------------------------------------------------
    def set_profile(
        self,
        *,
        name: str | None = None,
        avatar_id: str | None = None,
        voice_on: bool | None = None,
        voice_volume: float | None = None,
        sfx_on: bool | None = None,
        sfx_volume: float | None = None,
        reduce_effects: bool | None = None,
        notify_sound: str | None = None,
    ) -> None:
        """Edit profile settings; None = unchanged. Volumes are clamped to 0..1. notify_sound
        must be one of models.NOTIFY_SOUNDS (ValueError otherwise)."""
        p = self.profile
        if name is not None:
            name = name.strip()
            if not name:
                raise ValueError("name is empty")
            p.name = name
        if avatar_id is not None:
            if not avatar_id.strip():
                raise ValueError("avatar id is empty")
            p.avatar_id = avatar_id.strip()
        if voice_on is not None:
            p.voice_on = bool(voice_on)
        if voice_volume is not None:
            p.voice_volume = min(1.0, max(0.0, float(voice_volume)))
        if sfx_on is not None:
            p.sfx_on = bool(sfx_on)
        if sfx_volume is not None:
            p.sfx_volume = min(1.0, max(0.0, float(sfx_volume)))
        if reduce_effects is not None:
            p.reduce_effects = bool(reduce_effects)
        if notify_sound is not None:
            from lol.core.models import NOTIFY_SOUNDS

            if notify_sound not in NOTIFY_SOUNDS:
                raise ValueError(f"unknown notification sound {notify_sound!r}")
            p.notify_sound = notify_sound

    def finish_onboarding(self, name: str, avatar_id: str) -> None:
        """Guest onboarding done: set name and avatar, never show onboarding again."""
        self.set_profile(name=name, avatar_id=avatar_id)
        self.profile.onboarded = True

    # --- bills ---------------------------------------------------------------------------------
    def add_bill(
        self, name: str, amount: float, due: date, repeat: str = "none", note: str = ""
    ) -> Bill:
        if repeat not in BILL_REPEATS:
            raise ValueError(f"repeat must be one of {BILL_REPEATS}")
        if amount < 0:
            raise ValueError("amount cannot be negative")
        name = name.strip()
        if not name:
            raise ValueError("bill name is empty")
        bill = Bill(self._new_id("b"), name, float(amount), _iso(due), repeat, note=note)
        self.data.bills.append(bill)
        return bill

    @staticmethod
    def _oneoff_paid(bill: Bill) -> bool:
        return bill.repeat == "none" and len(bill.paid) > bill.start_cycle

    def next_due(self, bill: Bill) -> date:
        """Due date of the oldest unpaid cycle (for a one-off bill: its due date)."""
        if bill.repeat == "none":
            return _day(bill.due)
        return bill_occurrence(bill, len(bill.paid))

    def bill_status(self, bill: Bill, today: date) -> str:
        if bill.repeat == "none":
            if self._oneoff_paid(bill):
                return "paid"
        elif bill.paid and today <= bill_occurrence(bill, len(bill.paid) - 1):
            return "paid"  # the current cycle is paid and its due date has not passed yet
        days = (self.next_due(bill) - today).days
        if days < 0:
            return "overdue"
        if days <= DUE_SOON_DAYS:
            return "due_soon"
        return "upcoming"

    def bills_status(self, today: date) -> list[tuple[Bill, str, date]]:
        """(bill, status, next_due) for non-archived bills, most urgent first."""
        order = {"overdue": 0, "due_soon": 1, "upcoming": 2, "paid": 3}
        rows = [(b, self.bill_status(b, today), self.next_due(b)) for b in self.bills]
        return sorted(rows, key=lambda r: (order[r[1]], r[2]))

    def pay_bill(self, bill_id: str, today: date) -> Completion:
        """Pay the oldest unpaid cycle. A repeating bill moves on to its next due date.
        Paying an already-paid one-off bill or an archived bill does nothing; rewards are once
        per bill per day. Records the cycle's due date and amount with the payment."""
        bill = self.bill(bill_id)
        if bill.archived or self._oneoff_paid(bill):
            return Completion(path_id=STEWARD_PATH)
        t = _iso(today)
        rewarded_today = t in bill.paid or t in bill.rewarded_on
        due = self.next_due(bill)
        bill.paid_due.append(_iso(due))
        bill.paid_amounts.append(bill.amount)
        bill.paid.append(t)
        if rewarded_today:
            return Completion(path_id=STEWARD_PATH)
        bill.rewarded_on.append(t)
        return self._award(STEWARD_BILL_XP, STEWARD_BILL_COINS, STEWARD_PATH, today)

    def mark_bill_paid(self, bill_id: str, today: date) -> Completion:
        """Player-facing "paid" toggle (v1.3): pays the oldest unpaid cycle (see pay_bill)."""
        return self.pay_bill(bill_id, today)

    def mark_bill_unpaid(self, bill_id: str) -> bool:
        """Undo the most recent payment: its paid / paid_due / paid_amounts record is removed,
        so that cycle is unpaid again and next_due goes back to it. False if nothing was paid.

        Earned XP and coins are NEVER taken back. The payment day stays in rewarded_on, so
        paying again that same day gives no second reward (no pay/unpay farming). If the payment
        predates a schedule edit (old saves), the bill is re-anchored on the cycle it covered,
        so that exact due date comes back as the next due date."""
        bill = self.bill(bill_id)
        if not bill.paid:
            return False
        i = len(bill.paid) - 1
        bill.paid.pop()
        covered = bill.paid_due.pop() if len(bill.paid_due) > i else None
        if len(bill.paid_amounts) > i:
            bill.paid_amounts.pop()
        if bill.repeat != "none" and i < bill.start_cycle and covered:
            bill.start_cycle, bill.due = i, covered
        return True

    def update_bill(self, bill_id: str, name: str | None = None,
                    note: str | None = None) -> Bill:
        """The player-facing bill edit (v1.3): name and note only (paid status via
        mark_bill_paid / mark_bill_unpaid). Amount, due date and repeat are fixed."""
        bill = self.bill(bill_id)
        if name is not None:
            if not name.strip():
                raise ValueError("bill name is empty")
            bill.name = name.strip()
        if note is not None:
            bill.note = note
        return bill

    def edit_bill(
        self,
        bill_id: str,
        *,
        name: str | None = None,
        amount: float | None = None,
        due: date | None = None,
        repeat: str | None = None,
    ) -> Bill:
        """Edit a bill (the whole series); None = unchanged. Payment history never changes.

        `due` means the NEXT unpaid due date (what the Bills screen shows), not the original
        first due date. Rule for a schedule change (new due date or repeat): the bill is
        re-anchored at its current paid count, start_cycle = len(paid) and due = the new date,
        so paid cycles are neither lost nor counted twice and the next unpaid cycle falls on
        exactly the new date (later ones follow the new repeat). Past paid cycles keep the due
        date and amount they had (paid_due / paid_amounts). If only repeat changes, the next due
        date stays where it is. Special case: a paid one-off bill that stays one-off keeps its
        paid state and just moves its date; switching it to repeating starts the series one
        repeat after its old date unless `due` is given. Amount changes apply to unpaid cycles.
        """
        bill = self.bill(bill_id)
        new_repeat = bill.repeat if repeat is None else repeat
        if new_repeat not in BILL_REPEATS:
            raise ValueError(f"repeat must be one of {BILL_REPEATS}")
        if amount is not None and amount < 0:
            raise ValueError("amount cannot be negative")
        if name is not None and not name.strip():
            raise ValueError("bill name is empty")
        current_next = self.next_due(bill)
        if self._oneoff_paid(bill) and new_repeat == "none":
            if due is not None:
                bill.due = _iso(due)
        elif (due is not None and due != current_next) or new_repeat != bill.repeat:
            if due is None:
                due = (_shift(current_next, new_repeat, 1) if self._oneoff_paid(bill)
                       else current_next)
            bill.start_cycle, bill.due, bill.repeat = len(bill.paid), _iso(due), new_repeat
        if name is not None:
            bill.name = name.strip()
        if amount is not None:
            bill.amount = float(amount)
        return bill

    def archive_bill(self, bill_id: str) -> None:
        """Hide a bill from status, totals and the calendar's due dates. History stays."""
        self.bill(bill_id).archived = True

    def unarchive_bill(self, bill_id: str) -> None:
        self.bill(bill_id).archived = False

    def archived_bills(self) -> list[Bill]:
        return [b for b in self.data.bills if b.archived]

    def delete_bill(self, bill_id: str) -> None:
        """Remove a bill and its history for good (archive_bill keeps it). XP stays."""
        self.data.bills.remove(self.bill(bill_id))

    def upcoming_total(self, today: date, days: int = 30) -> float:
        """PHP owed for every unpaid cycle due on or before today + days (overdue included).
        Archived bills are left out."""
        horizon = today + timedelta(days=days)
        total = 0.0
        for bill in self.bills:
            if bill.repeat == "none":
                if not self._oneoff_paid(bill) and _day(bill.due) <= horizon:
                    total += bill.amount
                continue
            n = len(bill.paid)
            while bill_occurrence(bill, n) <= horizon:
                total += bill.amount
                n += 1
        return round(total, 2)

    # --- rewards and themes --------------------------------------------------------------------
    def add_reward(self, title: str, cost: int, note: str = "") -> Reward:
        if cost < 0:
            raise ValueError("cost cannot be negative")
        title = title.strip()
        if not title:
            raise ValueError("reward title is empty")
        reward = Reward(self._new_id("r"), title, int(cost), note=note)
        self.data.rewards.append(reward)
        return reward

    def edit_reward(self, reward_id: str, title: str | None = None,
                    cost: int | None = None) -> Reward:
        """Rename or re-price a reward; None = unchanged. Past redemptions keep their date and
        the price paid (redeemed_costs); coins already spent never change."""
        reward = self.reward(reward_id)
        if title is not None:
            if not title.strip():
                raise ValueError("reward title is empty")
            reward.title = title.strip()
        if cost is not None:
            if cost < 0:
                raise ValueError("cost cannot be negative")
            reward.cost = int(cost)
        return reward

    def rename_reward(self, reward_id: str, title: str | None = None,
                      note: str | None = None) -> Reward:
        """The player-facing reward edit (v1.3): name and note only; the price is fixed."""
        reward = self.reward(reward_id)
        if title is not None:
            if not title.strip():
                raise ValueError("reward title is empty")
            reward.title = title.strip()
        if note is not None:
            reward.note = note
        return reward

    def redeem(self, reward_id: str, today: date) -> bool:
        """Spend coins on a personal reward. False (and nothing spent) if coins are short or
        the reward is archived."""
        reward = self.reward(reward_id)
        if reward.archived or self.profile.coins < reward.cost:
            return False
        self.profile.coins -= reward.cost
        reward.redeemed.append(_iso(today))
        reward.redeemed_costs.append(reward.cost)
        return True

    def delete_reward(self, reward_id: str) -> None:
        """Remove a reward. One that was ever redeemed is archived instead, so its redemption
        history stays (shown with an "archived" label)."""
        reward = self.reward(reward_id)
        if reward.redeemed:
            reward.archived = True
        else:
            self.data.rewards.remove(reward)

    def archive_reward(self, reward_id: str) -> None:
        self.reward(reward_id).archived = True

    def unarchive_reward(self, reward_id: str) -> None:
        self.reward(reward_id).archived = False

    def archived_rewards(self) -> list[Reward]:
        return [r for r in self.data.rewards if r.archived]

    def themes(self) -> list[ThemeDef]:
        return list(catalog.THEMES)

    def buy_theme(self, theme_id: str, today: date | None = None) -> bool:
        """Buy a theme with coins. True if owned afterwards (already owned costs nothing).
        A premium-only theme can be bought only while premium (premium never grants it)."""
        if theme_id not in catalog.THEME_PRICES:
            raise ValueError(f"unknown theme: {theme_id}")
        p = self.profile
        if theme_id in p.owned_themes:
            return True
        if catalog.THEME_BY_ID[theme_id].premium_only and not self.is_premium(today):
            return False
        price = catalog.THEME_PRICES[theme_id]
        if p.coins < price:
            return False
        p.coins -= price
        p.owned_themes.append(theme_id)
        return True

    def set_theme(self, theme_id: str) -> bool:
        """Switch to an owned theme. False if not owned."""
        if theme_id not in self.profile.owned_themes:
            return False
        self.profile.theme_id = theme_id
        return True

    # --- logbook -------------------------------------------------------------------------------
    def add_log(
        self, kind: str, text: str = "", minutes: int | None = None, today: date | None = None
    ) -> LogEntry:
        if kind not in LOG_KINDS:
            raise ValueError(f"log kind must be one of {LOG_KINDS}")
        entry = LogEntry(self._new_id("l"), _iso(today or date.today()), kind, text, minutes)
        self.data.logs.append(entry)
        return entry

    def logs(self, day: date | None = None) -> list[LogEntry]:
        """Entries for one day, or all; newest first."""
        entries = self.data.logs
        if day is not None:
            entries = [e for e in entries if e.day == _iso(day)]
        return sorted(entries, key=lambda e: e.day, reverse=True)

    # --- calendar ------------------------------------------------------------------------------
    def calendar_entries(
        self, start: date, end: date, kinds: set[str] | None = None
    ) -> dict[date, list[Entry]]:
        """Entries per day for start..end (inclusive). Only days with entries are present, so a
        blank day is simply absent (neutral). kinds filters (None = all of ENTRY_KINDS).

        quest: each completion day. step: side quest steps done (skips are not shown). log,
        focus: by day. bill_paid: each payment day (archived bills too: it is history).
        bill_due: every cycle's due date in range, including future ones, for non-archived
        bills; paid cycles use the date they covered. Nothing is ever marked missed/overdue.
        """
        kinds = set(ENTRY_KINDS) if kinds is None else set(kinds)
        unknown = kinds - set(ENTRY_KINDS)
        if unknown:
            raise ValueError(f"unknown calendar kinds: {sorted(unknown)}")
        out: dict[date, list[Entry]] = {}

        def put(day_s: str | date, entry: Entry) -> None:
            d = _day(day_s) if isinstance(day_s, str) else day_s
            if start <= d <= end:
                out.setdefault(d, []).append(entry)

        if "quest" in kinds:
            for q in self.quests:
                for d in sorted(set(q.done_on)):
                    put(d, Entry("quest", q.title, q.path_id, q.id))
        if "step" in kinds:
            for sq in self.data.side_quests:
                for st in sq.steps:
                    if st.done_on:
                        put(st.done_on, Entry("step", f"{sq.skill_name}: {st.title}",
                                              sq.path_id, sq.id))
        if "log" in kinds:
            for e in self.data.logs:
                put(e.day, Entry("log", e.text or e.kind.capitalize(), "", e.id))
        if "focus" in kinds:
            for s in self.data.focus_sessions:
                label = s.note or ("Focus" if s.mode == "focus" else "Stopwatch")
                put(s.day, Entry("focus", f"{label} ({s.minutes} min)", s.path_id or "", s.id))
        for bill in self.data.bills:
            if "bill_paid" in kinds:
                for d in bill.paid:
                    put(d, Entry("bill_paid", bill.name, STEWARD_PATH, bill.id))
            if "bill_due" in kinds and not bill.archived:
                for d in self._bill_due_dates(bill, end):
                    put(d, Entry("bill_due", bill.name, STEWARD_PATH, bill.id))
        order = {k: i for i, k in enumerate(ENTRY_KINDS)}
        for entries in out.values():
            entries.sort(key=lambda e: order[e.kind])
        return dict(sorted(out.items()))

    def _bill_due_dates(self, bill: Bill, end: date) -> list[date]:
        """Due dates of every cycle up to `end`: paid ones as covered, then unpaid ones."""
        dates = [_day(d) for d in bill.paid_due]
        if bill.repeat == "none":
            if not self._oneoff_paid(bill):
                dates.append(_day(bill.due))
            return dates
        n = len(bill.paid)
        while (d := bill_occurrence(bill, n)) <= end:
            dates.append(d)
            n += 1
        return dates

    # --- weekly review -------------------------------------------------------------------------
    def weekly_review(self, today: date) -> dict:
        """Last 7 days ending today.

        Keys: start, end (ISO), done (quest and side quest step completions), skipped (daily
        quest-days missed, today not counted), xp_by_path {path_id: xp}, xp_total, bills_paid, logs,
        focus_minutes, workouts, workout_minutes, best_streak, best_streak_quest (title or None).
        Focus XP counts toward its Path (unlinked focus XP only toward xp_total); workout XP
        toward its Path; sleep-log and water-goal XP toward Monk.
        """
        start = today - timedelta(days=WEEK_DAYS - 1)
        window = {_iso(start + timedelta(days=i)) for i in range(WEEK_DAYS)}
        xp_by_path = {p.id: 0 for p in catalog.PATHS}
        done = skipped = 0
        for q in self.quests:
            hits = [d for d in q.done_on if d in window]
            done += len(hits)
            xp_by_path[q.path_id] = xp_by_path.get(q.path_id, 0) + q.xp * len(hits)
            if q.kind == "daily":
                created = _day(q.created) if q.created else start
                for i in range(WEEK_DAYS - 1):  # today is still in progress
                    d = start + timedelta(days=i)
                    if d >= created and _iso(d) not in q.done_on:
                        skipped += 1
        for sq in self.data.side_quests:  # side quest steps count as completions too
            for st in sq.steps:
                if st.done_on in window:
                    done += 1
                    xp_by_path[sq.path_id] = xp_by_path.get(sq.path_id, 0) + st.xp
        bills_paid = sum(1 for b in self.data.bills for d in b.paid if d in window)
        xp_by_path[STEWARD_PATH] += STEWARD_BILL_XP * bills_paid
        focus = [s for s in self.data.focus_sessions if s.day in window]
        unlinked_focus_xp = 0
        for s in focus:
            if s.path_id:
                xp_by_path[s.path_id] = xp_by_path.get(s.path_id, 0) + s.xp
            else:
                unlinked_focus_xp += s.xp
        workouts = [w for w in self.data.workouts if w.day in window]
        for w in workouts:
            xp_by_path[w.path_id] = xp_by_path.get(w.path_id, 0) + w.xp
        xp_by_path[MONK_PATH] += sum(e.xp for e in self.data.sleep if e.logged_on in window)
        xp_by_path[MONK_PATH] += sum(xp for d, xp in self.data.water_goal_days.items()
                                     if d in window)
        best, best_title = 0, None
        for q in self.quests:
            s = self.streak(q, today)
            if s > best:
                best, best_title = s, q.title
        return {
            "start": _iso(start),
            "end": _iso(today),
            "done": done,
            "skipped": skipped,
            "xp_by_path": xp_by_path,
            "xp_total": sum(xp_by_path.values()) + unlinked_focus_xp,
            "bills_paid": bills_paid,
            "logs": sum(1 for e in self.data.logs if e.day in window),
            "focus_minutes": sum(s.minutes for s in focus),
            "workouts": len(workouts),
            "workout_minutes": sum(w.minutes for w in workouts),
            "best_streak": best,
            "best_streak_quest": best_title,
        }

    # --- modules (Phase 2) ---------------------------------------------------------------------
    def module_on(self, name: str) -> bool:
        if name not in MODULES:
            raise ValueError(f"module must be one of {MODULES}")
        return self.profile.modules.get(name, True)

    def set_module(self, name: str, on: bool) -> None:
        """Show/hide a tracking module. Turning one off never deletes its data."""
        if name not in MODULES:
            raise ValueError(f"module must be one of {MODULES}")
        self.profile.modules[name] = bool(on)

    # --- workouts ------------------------------------------------------------------------------
    @staticmethod
    def _clean_exercises(exercises: Iterable[ExerciseEntry] | None) -> list[ExerciseEntry]:
        """Validated deep copies (so a draft or routine is never shared with a session)."""
        out = []
        for ex in exercises or ():
            name = ex.name.strip()
            if not name:
                raise ValueError("exercise name is empty")
            sets = []
            for st in ex.sets:
                if st.unit not in WEIGHT_UNITS:
                    raise ValueError(f"weight unit must be one of {WEIGHT_UNITS}")
                for v in (st.reps, st.weight, st.distance_km, st.seconds):
                    if v is not None and v < 0:
                        raise ValueError("set values cannot be negative")
                sets.append(dataclasses.replace(st))
            out.append(ExerciseEntry(name, sets))
        return out

    @staticmethod
    def _check_workout(type_: str, effort: int) -> None:
        if type_ not in WORKOUT_TYPES:
            raise ValueError(f"workout type must be one of {WORKOUT_TYPES}")
        if not 1 <= int(effort) <= 10:
            raise ValueError("effort must be 1..10")

    @staticmethod
    def workout_xp(minutes: int, effort: int = 5) -> int:
        """Uncapped XP for one session: WORKOUT_XP_PER_BLOCK per full WORKOUT_BLOCK_MINUTES,
        x(1 + WORKOUT_EFFORT_STEP*(effort-5)); WORKOUT_MIN_XP when no duration was logged."""
        if minutes <= 0:
            return WORKOUT_MIN_XP
        base = minutes // WORKOUT_BLOCK_MINUTES * WORKOUT_XP_PER_BLOCK
        return round(base * (1 + WORKOUT_EFFORT_STEP * (int(effort) - 5)))

    def log_workout(
        self,
        minutes: int,
        today: date,
        type: str = "strength",
        effort: int = 5,
        notes: str = "",
        quest_id: str | None = None,
        path_id: str | None = None,
        exercises: Iterable[ExerciseEntry] | None = None,
        *,
        started: str = "",
    ) -> Completion:
        """Log a workout session (quick log = minutes only; or with exercises/sets). minutes
        is clamped to 0..WORKOUT_MAX_MINUTES. XP = workout_xp, up to WORKOUT_DAILY_XP_CAP per
        day; coins 1 per WORKOUT_COIN_MINUTES up to WORKOUT_DAILY_COIN_CAP (and DAILY_COIN_CAP).
        XP goes to path_id, else the linked quest's Path, else Warrior. A linked quest is NOT
        completed. Completion.ref_id = the session id."""
        self._check_workout(type, effort)
        minutes = min(max(0, int(minutes)), WORKOUT_MAX_MINUTES)
        if quest_id is not None:
            path_id = path_id or self.quest(quest_id).path_id
        path_id = path_id or WARRIOR_PATH
        if path_id not in catalog.PATH_IDS:
            raise ValueError(f"unknown path: {path_id}")
        clean = self._clean_exercises(exercises)
        stats = self.workout_stats(today)
        xp = min(self.workout_xp(minutes, effort), stats["xp_left"])
        coins = min(minutes // WORKOUT_COIN_MINUTES,
                    max(0, WORKOUT_DAILY_COIN_CAP - stats["coins"]))
        c = self._award(xp, coins, path_id, today)
        session = WorkoutSession(self._new_id("w"), _iso(today), started, type, minutes,
                                 int(effort), notes, quest_id, path_id, clean, c.xp, c.coins)
        self.data.workouts.append(session)
        c.ref_id = session.id
        return c

    def log_workout_draft(self, draft: WorkoutSession, today: date) -> Completion:
        """Log a draft from copy_workout / workout_from_template (after the player edits it)."""
        return self.log_workout(draft.minutes, today, draft.type, draft.effort, draft.notes,
                                draft.quest_id, draft.path_id, draft.exercises,
                                started=draft.started)

    def workout(self, session_id: str) -> WorkoutSession:
        return self._find(self.data.workouts, session_id)

    def workouts(self, start: date | None = None, end: date | None = None,
                 type: str | None = None) -> list[WorkoutSession]:
        """Sessions in start..end (inclusive, either open), optionally one type; newest first."""
        rows = [w for w in reversed(self.data.workouts)
                if (start is None or _day(w.day) >= start)
                and (end is None or _day(w.day) <= end)
                and type in (None, w.type)]
        return sorted(rows, key=lambda w: w.day, reverse=True)

    def workout_stats(self, day: date) -> dict:
        """Keys: sessions, minutes, xp, coins (earned that day), xp_left (before the cap)."""
        rows = [w for w in self.data.workouts if w.day == _iso(day)]
        xp = sum(w.xp for w in rows)
        return {
            "sessions": len(rows),
            "minutes": sum(w.minutes for w in rows),
            "xp": xp,
            "coins": sum(w.coins for w in rows),
            "xp_left": max(0, WORKOUT_DAILY_XP_CAP - xp),
        }

    def edit_workout(
        self,
        session_id: str,
        *,
        day: date | None = None,
        started: str | None = None,
        type: str | None = None,
        minutes: int | None = None,
        effort: int | None = None,
        notes: str | None = None,
        exercises: Iterable[ExerciseEntry] | None = None,
    ) -> WorkoutSession:
        """Correct a saved session; None = unchanged. The XP/coins it awarded never change
        (no re-farming by editing minutes up, no clawback by editing down)."""
        w = self.workout(session_id)
        new_type = w.type if type is None else type
        new_effort = w.effort if effort is None else int(effort)
        self._check_workout(new_type, new_effort)
        if exercises is not None:
            w.exercises = self._clean_exercises(exercises)
        w.type, w.effort = new_type, new_effort
        if minutes is not None:
            w.minutes = min(max(0, int(minutes)), WORKOUT_MAX_MINUTES)
        if day is not None:
            w.day = _iso(day)
        if started is not None:
            w.started = started
        if notes is not None:
            w.notes = notes
        return w

    def delete_workout(self, session_id: str) -> None:
        """Remove a session from the log. XP and coins it earned stay."""
        self.data.workouts.remove(self.workout(session_id))

    def copy_workout(self, session_id: str, today: date) -> WorkoutSession:
        """A DRAFT copy of a past session dated today (id "", nothing awarded or saved): same
        type, minutes, effort, notes, Path and exercises/sets (deep copy), no quest link. Let
        the player adjust it, then log it with log_workout_draft."""
        w = self.workout(session_id)
        return WorkoutSession("", _iso(today), "", w.type, w.minutes, w.effort, w.notes, None,
                              w.path_id, copy.deepcopy(w.exercises))

    def exercise_names(self) -> list[str]:
        """Every exercise name used in sessions or routines (case-insensitive unique, sorted)."""
        names: dict[str, str] = {}
        for group in (self.data.workouts, self.data.workout_templates):
            for item in group:
                for ex in item.exercises:
                    names.setdefault(ex.name.casefold(), ex.name)
        return sorted(names.values(), key=str.casefold)

    def exercise_history(self, name: str) -> list[tuple[WorkoutSession, ExerciseEntry]]:
        """(session, exercise) for every logged session with this exercise (name matched
        case-insensitively), newest first. For "compare with my prior sessions"."""
        key = name.strip().casefold()
        return [(w, ex) for w in self.workouts() for ex in w.exercises
                if ex.name.casefold() == key]

    def personal_records(self, name: str, unit: str = "kg") -> dict[str, PersonalRecord]:
        """Descriptive bests for one exercise; only kinds with data are present.

        max_weight: heaviest single set; max_reps: most reps in one set; best_volume: biggest
        session total of reps x weight; longest_distance (km) and longest_time (seconds): best
        single set. Weights are shown in `unit` (converted for display only; stored sets keep
        their own unit). Ties keep the earliest session."""
        if unit not in WEIGHT_UNITS:
            raise ValueError(f"weight unit must be one of {WEIGHT_UNITS}")
        best: dict[str, PersonalRecord] = {}

        def offer(kind: str, value: float, u: str, w: WorkoutSession) -> None:
            if value > 0 and (kind not in best or value > best[kind].value):
                best[kind] = PersonalRecord(kind, round(value, 2), u, w.day, w.id)

        for w, ex in sorted(self.exercise_history(name), key=lambda r: r[0].day):
            volume = 0.0
            for st in ex.sets:
                weight = (convert_weight(st.weight, st.unit, unit)
                          if st.weight is not None else None)
                if weight is not None:
                    offer("max_weight", weight, unit, w)
                if st.reps is not None:
                    offer("max_reps", st.reps, "", w)
                    if weight is not None:
                        volume += st.reps * weight
                if st.distance_km is not None:
                    offer("longest_distance", st.distance_km, "km", w)
                if st.seconds is not None:
                    offer("longest_time", st.seconds, "s", w)
            offer("best_volume", volume, unit, w)
        return best

    # routines / templates
    def workout_templates(self) -> list[WorkoutTemplate]:
        return list(self.data.workout_templates)

    def workout_template(self, template_id: str) -> WorkoutTemplate:
        return self._find(self.data.workout_templates, template_id)

    def add_workout_template(
        self, name: str, type: str = "strength", minutes: int = 0,
        exercises: Iterable[ExerciseEntry] | None = None, notes: str = "",
    ) -> WorkoutTemplate:
        name = name.strip()
        if not name:
            raise ValueError("routine name is empty")
        self._check_workout(type, 5)
        t = WorkoutTemplate(self._new_id("wt"), name, type,
                            min(max(0, int(minutes)), WORKOUT_MAX_MINUTES),
                            self._clean_exercises(exercises), notes)
        self.data.workout_templates.append(t)
        return t

    def template_from_workout(self, session_id: str, name: str = "") -> WorkoutTemplate:
        """Save a past session as a routine (the session is untouched)."""
        w = self.workout(session_id)
        return self.add_workout_template(name or w.type.capitalize(), w.type, w.minutes,
                                         w.exercises, w.notes)

    def edit_workout_template(
        self, template_id: str, *, name: str | None = None,
        type: str | None = None, minutes: int | None = None,
        exercises: Iterable[ExerciseEntry] | None = None, notes: str | None = None,
    ) -> WorkoutTemplate:
        t = self.workout_template(template_id)
        if name is not None:
            if not name.strip():
                raise ValueError("routine name is empty")
            t.name = name.strip()
        if type is not None:
            self._check_workout(type, 5)
            t.type = type
        if minutes is not None:
            t.minutes = min(max(0, int(minutes)), WORKOUT_MAX_MINUTES)
        if exercises is not None:
            t.exercises = self._clean_exercises(exercises)
        if notes is not None:
            t.notes = notes
        return t

    def delete_workout_template(self, template_id: str) -> None:
        self.data.workout_templates.remove(self.workout_template(template_id))

    def workout_from_template(self, template_id: str, today: date) -> WorkoutSession:
        """A DRAFT session (id "", not saved) from a routine; log it with log_workout_draft."""
        t = self.workout_template(template_id)
        return WorkoutSession("", _iso(today), "", t.type, t.minutes, 5, t.notes, None,
                              WARRIOR_PATH, copy.deepcopy(t.exercises))

    # --- sleep ---------------------------------------------------------------------------------
    @staticmethod
    def _check_sleep(bedtime: str, wake: str, naps_min: int, restedness: int | None) -> None:
        if parse_hm(bedtime) == parse_hm(wake):
            raise ValueError("bedtime and wake time are the same")
        if not 0 <= int(naps_min) <= SLEEP_MAX_NAP_MINUTES:
            raise ValueError(f"naps must be 0..{SLEEP_MAX_NAP_MINUTES} minutes")
        if restedness is not None and not 1 <= int(restedness) <= 5:
            raise ValueError("restedness must be 1..5")

    def log_sleep(
        self, night_of: date, bedtime: str, wake: str, today: date, naps_min: int = 0,
        restedness: int | None = None, note: str = "",
    ) -> Completion:
        """Log one night (night_of = the evening it started; can be entered after waking or
        later). One entry per night: a second one raises ValueError (edit it instead). Gives
        SLEEP_LOG_XP Monk XP for logging, up to SLEEP_DAILY_XP_CAP per day of logging; never
        anything for how long you slept. Completion.ref_id = entry id."""
        self._check_sleep(bedtime, wake, naps_min, restedness)
        if any(e.night_of == _iso(night_of) for e in self.data.sleep):
            raise ValueError("that night is already logged; edit it instead")
        earned = sum(e.xp for e in self.data.sleep if e.logged_on == _iso(today))
        xp = min(SLEEP_LOG_XP, max(0, SLEEP_DAILY_XP_CAP - earned))
        c = self._award(xp, 0, MONK_PATH, today) if xp else Completion(path_id=MONK_PATH)
        entry = SleepEntry(self._new_id("sl"), _iso(night_of), _hm(bedtime), _hm(wake),
                           int(naps_min), None if restedness is None else int(restedness),
                           note, _iso(today), c.xp)
        self.data.sleep.append(entry)
        c.ref_id = entry.id
        return c

    def sleep_entry(self, entry_id: str) -> SleepEntry:
        return self._find(self.data.sleep, entry_id)

    def sleep_entries(self, start: date | None = None,
                      end: date | None = None) -> list[SleepEntry]:
        """Nights in start..end (by night_of, inclusive), newest first."""
        rows = [e for e in self.data.sleep
                if (start is None or _day(e.night_of) >= start)
                and (end is None or _day(e.night_of) <= end)]
        return sorted(rows, key=lambda e: e.night_of, reverse=True)

    def edit_sleep(
        self, entry_id: str, *, night_of: date | None = None, bedtime: str | None = None,
        wake: str | None = None, naps_min: int | None = None, restedness=_UNSET,
        note: str | None = None,
    ) -> SleepEntry:
        """Correct an entry; None = unchanged (restedness: omit = unchanged, None = clear).
        XP already given never changes."""
        e = self.sleep_entry(entry_id)
        new_bed = e.bedtime if bedtime is None else bedtime
        new_wake = e.wake if wake is None else wake
        new_naps = e.naps_min if naps_min is None else naps_min
        new_rest = e.restedness if restedness is _UNSET else restedness
        self._check_sleep(new_bed, new_wake, new_naps, new_rest)
        if night_of is not None and _iso(night_of) != e.night_of:
            if any(x.night_of == _iso(night_of) for x in self.data.sleep):
                raise ValueError("that night is already logged")
            e.night_of = _iso(night_of)
        e.bedtime, e.wake, e.naps_min = _hm(new_bed), _hm(new_wake), int(new_naps)
        e.restedness = None if new_rest is None else int(new_rest)
        if note is not None:
            e.note = note
        return e

    def delete_sleep(self, entry_id: str) -> None:
        """Remove an entry. XP it earned stays."""
        self.data.sleep.remove(self.sleep_entry(entry_id))

    @staticmethod
    def sleep_duration(entry: SleepEntry) -> int:
        """Night-time minutes (bedtime -> wake, crossing midnight), naps not included."""
        return sleep_minutes(entry.bedtime, entry.wake)

    def sleep_stats(self, start: date, end: date) -> dict:
        """Plain numbers for start..end. Missing nights are simply absent (never zeros).

        Keys: nights (count), avg_minutes (night sleep, None if no nights), avg_nap_minutes,
        avg_restedness (rated nights only, None if none), per_night: [(night_of ISO, minutes,
        naps_min, restedness or None)] oldest first, for a chart."""
        rows = sorted(self.sleep_entries(start, end), key=lambda e: e.night_of)
        mins = [self.sleep_duration(e) for e in rows]
        rated = [e.restedness for e in rows if e.restedness is not None]
        return {
            "nights": len(rows),
            "avg_minutes": round(sum(mins) / len(mins)) if mins else None,
            "avg_nap_minutes": round(sum(e.naps_min for e in rows) / len(rows)) if rows else None,
            "avg_restedness": round(sum(rated) / len(rated), 1) if rated else None,
            "per_night": [(e.night_of, m, e.naps_min, e.restedness)
                          for e, m in zip(rows, mins, strict=True)],
        }

    # --- water ---------------------------------------------------------------------------------
    def set_water_settings(self, *, daily_goal_ml=_UNSET, unit: str | None = None,
                           quick_amounts: Iterable[float] | None = None) -> None:
        """daily_goal_ml: omit = unchanged, None = no goal, else 1..20000 ml. unit: "ml" | "oz"
        (display only). quick_amounts: ml values for the quick-add buttons (1..6 of them)."""
        w = self.profile.water
        if daily_goal_ml is not _UNSET:
            if daily_goal_ml is not None and not 0 < int(daily_goal_ml) <= 20000:
                raise ValueError("daily goal must be 1..20000 ml, or None for no goal")
            w.daily_goal_ml = None if daily_goal_ml is None else int(daily_goal_ml)
        if unit is not None:
            if unit not in WATER_UNITS:
                raise ValueError(f"water unit must be one of {WATER_UNITS}")
            w.unit = unit
        if quick_amounts is not None:
            amounts = [round(a) for a in quick_amounts]
            if not 1 <= len(amounts) <= 6 or not all(0 < a <= WATER_MAX_ENTRY_ML
                                                     for a in amounts):
                raise ValueError(f"1..6 quick amounts, each 1..{WATER_MAX_ENTRY_ML} ml")
            w.quick_amounts = amounts

    def add_water(self, amount_ml: float, today: date, time: str = "") -> Completion:
        """Add a drink (ml; convert oz with oz_to_ml first). The first time the day's total
        reaches the user's goal, gives WATER_GOAL_XP Monk XP, once per day (undo and re-add
        never pays twice). No goal = no XP. Completion.ref_id = entry id."""
        amount = round(amount_ml)
        if not 0 < amount <= WATER_MAX_ENTRY_ML:
            raise ValueError(f"amount must be 1..{WATER_MAX_ENTRY_ML} ml")
        entry = WaterEntry(self._new_id("wa"), _iso(today), _hm(time) if time else "", amount)
        self.data.water.append(entry)
        goal = self.profile.water.daily_goal_ml
        t = _iso(today)
        if goal and t not in self.data.water_goal_days and self.water_day(today) >= goal:
            c = self._award(WATER_GOAL_XP, 0, MONK_PATH, today)
            self.data.water_goal_days[t] = c.xp
        else:
            c = Completion(path_id=MONK_PATH)
        c.ref_id = entry.id
        return c

    def water_entries(self, day: date) -> list[WaterEntry]:
        """That day's drinks in the order added."""
        return [e for e in self.data.water if e.day == _iso(day)]

    def undo_water(self, today: date) -> WaterEntry | None:
        """Remove the most recent drink added today; None if there is none. XP stays."""
        rows = self.water_entries(today)
        if not rows:
            return None
        self.data.water.remove(rows[-1])
        return rows[-1]

    def delete_water(self, entry_id: str) -> None:
        """Remove one drink (any day). XP stays."""
        self.data.water.remove(self._find(self.data.water, entry_id))

    def water_day(self, day: date) -> int:
        """Total ml for a day."""
        return sum(e.amount_ml for e in self.water_entries(day))

    def water_today(self, today: date) -> dict:
        """Keys: ml, goal_ml (None = no goal), progress (0..1, None without a goal), reached."""
        ml = self.water_day(today)
        goal = self.profile.water.daily_goal_ml
        return {"ml": ml, "goal_ml": goal,
                "progress": min(1.0, ml / goal) if goal else None,
                "reached": bool(goal) and ml >= goal}

    def water_history(self, start: date, end: date) -> list[tuple[str, int, bool]]:
        """(ISO day, ml, reached the CURRENT goal) for every day in start..end, oldest first
        (zero-ml days included so a chart has every day)."""
        goal = self.profile.water.daily_goal_ml
        totals: dict[str, int] = {}
        for e in self.data.water:
            totals[e.day] = totals.get(e.day, 0) + e.amount_ml
        out = []
        for i in range((end - start).days + 1):
            d = _iso(start + timedelta(days=i))
            ml = totals.get(d, 0)
            out.append((d, ml, bool(goal) and ml >= goal))
        return out

    # --- energy check-in -----------------------------------------------------------------------
    def check_in(self, level: str, today: date, time: str = "", note: str = "") -> EnergyCheckin:
        """Record low / okay / high (optional note). Several per day are fine; no XP."""
        if level not in ENERGY_LEVELS:
            raise ValueError(f"energy level must be one of {ENERGY_LEVELS}")
        c = EnergyCheckin(self._new_id("e"), _iso(today), _hm(time) if time else "", level,
                          note)
        self.data.energy.append(c)
        return c

    def energy_today(self, today: date) -> EnergyCheckin | None:
        """The latest check-in of the day (by time, then order added), or None."""
        rows = [(c.time, i, c) for i, c in enumerate(self.data.energy) if c.day == _iso(today)]
        return max(rows, key=lambda r: r[:2])[2] if rows else None

    def energy_checkins(self, start: date | None = None,
                        end: date | None = None) -> list[EnergyCheckin]:
        """Check-ins in start..end (inclusive), newest first."""
        rows = [c for c in self.data.energy
                if (start is None or _day(c.day) >= start)
                and (end is None or _day(c.day) <= end)]
        return sorted(rows, key=lambda c: (c.day, c.time), reverse=True)

    def delete_checkin(self, checkin_id: str) -> None:
        self.data.energy.remove(self._find(self.data.energy, checkin_id))

    @staticmethod
    def suggest_order(quests: Iterable[Quest],
                      energy: str | EnergyCheckin | None) -> list[Quest]:
        """The same quests, re-sorted for the energy level (never filtered, nothing hidden).
        low: easiest and shortest first; high: hardest first; okay / None: unchanged order.
        The sort is stable, so equal quests keep their order."""
        rows = list(quests)
        level = energy.level if isinstance(energy, EnergyCheckin) else energy
        if level == "low":
            return sorted(rows, key=lambda q: (q.difficulty, q.minutes or 0))
        if level == "high":
            return sorted(rows, key=lambda q: -q.difficulty)
        return rows

    # --- insights ------------------------------------------------------------------------------
    def insights(self, start: date, end: date) -> list[Insight]:
        """Plain summaries for start..end (inclusive) with the data behind each. Workout, sleep
        and water insights appear only while their module is on. Descriptive only: no claims
        that one thing causes another and no advice. Empty ranges give a neutral line."""
        if end < start:
            raise ValueError("end is before start")
        rng = f"from {start:%b} {start.day} to {end:%b} {end.day}"
        out = [self._insight_quests(start, end, rng)]
        if self.module_on("workout"):
            out.append(self._insight_workouts(start, end, rng))
        if self.module_on("sleep"):
            out.append(self._insight_sleep(start, end, rng))
        if self.module_on("water"):
            out.append(self._insight_water(start, end, rng))
        return out

    def _insight_quests(self, start: date, end: date, rng: str) -> Insight:
        counts = {p.id: 0 for p in catalog.PATHS}

        def inside(d: str | None) -> bool:
            return bool(d) and start <= _day(d) <= end

        for q in self.quests:
            counts[q.path_id] = counts.get(q.path_id, 0) + sum(1 for d in q.done_on if inside(d))
        for sq in self.data.side_quests:
            counts[sq.path_id] = counts.get(sq.path_id, 0) + sum(
                1 for st in sq.steps if inside(st.done_on))
        names = {p.id: p.name for p in catalog.PATHS}
        data = [(names.get(pid, pid), float(n)) for pid, n in counts.items()]
        total = sum(counts.values())
        if not total:
            text = f"No quests or steps completed {rng}."
        else:
            top = max(data, key=lambda r: r[1])[0]
            text = (f"{total} quests and steps completed {rng}. "
                    f"The most were on the {top} Path.")
        return Insight("Quests by Path", text, data, "quests_by_path")

    def _insight_workouts(self, start: date, end: date, rng: str) -> Insight:
        sessions = self.workouts(start, end)
        data = []
        week = start
        while week <= end:
            week_end = min(end, week + timedelta(days=WEEK_DAYS - 1))
            n = sum(1 for w in sessions if week <= _day(w.day) <= week_end)
            data.append((f"{week:%b} {week.day}", float(n)))
            week = week_end + timedelta(days=1)
        if not sessions:
            text = f"No workouts logged {rng}."
        else:
            per_week = len(sessions) / (((end - start).days + 1) / WEEK_DAYS)
            mins = sum(w.minutes for w in sessions)
            text = (f"{len(sessions)} workouts logged {rng} ({mins} min), "
                    f"about {per_week:.1f} per week.")
        return Insight("Workouts per week", text, data, "workouts_per_week")

    def _insight_sleep(self, start: date, end: date, rng: str) -> Insight:
        stats = self.sleep_stats(start, end)
        data = [(night, round(m / 60, 2)) for night, m, _, _ in stats["per_night"]]
        if not stats["nights"]:
            text = f"No nights logged {rng}."
        else:
            h, m = divmod(stats["avg_minutes"], 60)
            text = (f"Average logged sleep was {h} h {m} min over {stats['nights']} "
                    f"nights {rng}.")
            if stats["avg_restedness"] is not None:
                text += f" Average restedness: {stats['avg_restedness']} of 5."
        return Insight("Sleep", text, data, "sleep")

    def _insight_water(self, start: date, end: date, rng: str) -> Insight:
        hist = self.water_history(start, end)
        data = [(d, float(ml)) for d, ml, _ in hist]
        logged = sum(1 for _, ml, _ in hist if ml)
        if not logged:
            text = f"No water logged {rng}."
        elif self.profile.water.daily_goal_ml:
            reached = sum(1 for *_, ok in hist if ok)
            text = (f"Your daily goal was reached on {reached} of {len(hist)} days {rng} "
                    f"(water logged on {logged}).")
        else:
            text = f"Water logged on {logged} of {len(hist)} days {rng}. No daily goal is set."
        return Insight("Water", text, data, "water")

    # --- reminders (planned here, scheduled by the UI's notification extension) ----------------
    _REMINDER_TIMES = ("quiet_start", "quiet_end", "bill_time", "daily_time")

    def set_reminders(self, **changes) -> None:
        """Change ReminderSettings fields by name (validated). Unknown names raise ValueError."""
        r = self.profile.reminders
        names = {f.name for f in dataclasses.fields(r)}
        for key, value in changes.items():
            if key not in names:
                raise ValueError(f"unknown reminder setting: {key}")
            if key in self._REMINDER_TIMES:
                value = _hm(value)
            elif key == "bill_days_before":
                if not 0 <= int(value) <= 30:
                    raise ValueError("bill_days_before must be 0..30")
                value = int(value)
            elif key == "water_interval_min":
                if not 15 <= int(value) <= 720:
                    raise ValueError("water interval must be 15..720 minutes")
                value = int(value)
            elif key == "water_snooze_min":
                if not 1 <= int(value) <= 240:
                    raise ValueError("snooze must be 1..240 minutes")
                value = int(value)
            elif key == "water_active_days":
                value = sorted({int(d) for d in value})
                if any(not 0 <= d <= 6 for d in value):
                    raise ValueError("active days are 0 (Mon) .. 6 (Sun)")
            else:
                value = bool(value)
            setattr(r, key, value)

    def in_quiet_hours(self, when: datetime) -> bool:
        r = self.profile.reminders
        qs, qe, t = parse_hm(r.quiet_start), parse_hm(r.quiet_end), when.time()
        if qs == qe:
            return False
        return qs <= t < qe if qs < qe else (t >= qs or t < qe)

    def _after_quiet(self, when: datetime) -> datetime:
        """`when`, or the end of the quiet hours it falls in."""
        if not self.in_quiet_hours(when):
            return when
        qe = parse_hm(self.profile.reminders.quiet_end)
        shifted = datetime.combine(when.date(), qe)
        return shifted if shifted > when else shifted + timedelta(days=1)

    def planned_reminders(self, now: datetime, horizon_days: int = 7) -> list[Reminder]:
        """Every reminder due in (now, now + horizon_days], sorted by time.

        Ids are stable per event (bill:<id>:<due>, daily:<day>, water:<day>T<HH:MM>,
        comeback:<day>), so the scheduler can cancel ids that disappeared and replace the rest:
        call it again after any change (paying a bill, adding water, editing settings).
        - Master switch off: nothing.
        - Quiet hours: bill, daily and comeback reminders move to the end of quiet hours; water
          reminders inside quiet hours are dropped (they would pile up otherwise).
        - Bills: each unpaid cycle of a non-archived bill, bill_days_before days before its due
          date at bill_time. Paid cycles and past reminder times are skipped.
        - Daily: at daily_time on each day that still has an open quest.
        - Water: every water_interval_min inside the waking window (end of overnight quiet hours
          to their start; WATER_DAY_START..WATER_DAY_END without them), active days only, and
          none for the rest of today once today's goal is reached.
        - Comeback (opt-in): one gentle nudge COMEBACK_DAYS after the last activity."""
        r = self.profile.reminders
        if not r.enabled:
            return []
        until = now + timedelta(days=horizon_days)
        out: dict[str, Reminder] = {}

        def put(rid: str, when: datetime, title: str, body: str, cat: str,
                shift: bool = True) -> None:
            if shift:
                when = self._after_quiet(when)
            if now < when <= until:
                out[rid] = Reminder(rid, when, title, body, cat)

        days = [now.date() + timedelta(days=i) for i in range(horizon_days + 1)]
        if r.bills_on:
            bill_t = parse_hm(r.bill_time)
            last_due = until.date() + timedelta(days=r.bill_days_before)
            for bill in self.bills:
                for due in self._unpaid_due_dates(bill, last_due):
                    when = datetime.combine(due - timedelta(days=r.bill_days_before), bill_t)
                    body = f"PHP {bill.amount:,.2f} due {due:%a %b} {due.day}."
                    put(f"bill:{bill.id}:{_iso(due)}", when, f"Bill coming up: {bill.name}",
                        body, "bill")
        if r.daily_on:
            daily_t = parse_hm(r.daily_time)
            for d in days:
                if any(not self.is_done(q, d) for q in self.quests):
                    put(f"daily:{_iso(d)}", datetime.combine(d, daily_t),
                        "Your quests are ready", "Pick one small quest for today.", "daily")
        if r.water_on:
            self._plan_water(days, now, put)
        if r.comeback_on:
            last = self.last_active_day()
            if last is not None:
                d = last + timedelta(days=COMEBACK_DAYS)
                put(f"comeback:{_iso(d)}", datetime.combine(d, parse_hm(r.daily_time)),
                    "Your quests will wait for you",
                    "Whenever you're ready, one small quest is plenty.", "comeback")
        return sorted(out.values(), key=lambda x: (x.when, x.id))

    def _unpaid_due_dates(self, bill: Bill, until: date) -> list[date]:
        if bill.repeat == "none":
            return [] if self._oneoff_paid(bill) else [_day(bill.due)]
        dates, n = [], len(bill.paid)
        while (d := bill_occurrence(bill, n)) <= until:
            dates.append(d)
            n += 1
        return dates

    def _plan_water(self, days: list[date], now: datetime, put) -> None:
        r = self.profile.reminders
        qs, qe = parse_hm(r.quiet_start), parse_hm(r.quiet_end)
        if qs > qe:  # overnight quiet hours: the waking window sits between them
            win_start, win_end = qe, qs
        else:
            win_start, win_end = parse_hm(WATER_DAY_START), parse_hm(WATER_DAY_END)
        goal = self.profile.water.daily_goal_ml
        step = timedelta(minutes=r.water_interval_min)
        for d in days:
            if d.weekday() not in r.water_active_days:
                continue
            if d == now.date() and goal and self.water_day(d) >= goal:
                continue  # goal reached: no nagging for the rest of today
            t = datetime.combine(d, win_start) + step
            end = datetime.combine(d, win_end)
            while t <= end:
                if not self.in_quiet_hours(t):
                    put(f"water:{_iso(d)}T{t:%H:%M}", t, "Water break",
                        "A few sips whenever it suits you.", "water", shift=False)
                t += step

    def snooze_reminder(self, reminder: Reminder, now: datetime) -> Reminder:
        """The same reminder again in water_snooze_min minutes (after quiet hours), with id
        "<id>:snooze" so a new snooze replaces the previous one."""
        when = self._after_quiet(now + timedelta(minutes=self.profile.reminders.water_snooze_min))
        rid = reminder.id if reminder.id.endswith(":snooze") else f"{reminder.id}:snooze"
        return Reminder(rid, when, reminder.title, reminder.body, reminder.category)

    def focus_reminder(self, ends_at: datetime, label: str = "Focus") -> Reminder | None:
        """'Timer finished' notification for a running focus timer (None if switched off).
        Not moved by quiet hours: the player started the timer. Stable id "focus:timer"."""
        r = self.profile.reminders
        if not (r.enabled and r.focus_on):
            return None
        return Reminder("focus:timer", ends_at, f"{label} finished",
                        "Nice work. Log it when you're ready.", "focus")

    def last_active_day(self) -> date | None:
        """The latest day anything was completed or logged (None for a brand-new save)."""
        days = [d for q in self.quests for d in q.done_on]
        days += [st.done_on for sq in self.data.side_quests for st in sq.steps if st.done_on]
        for group in (self.data.logs, self.data.focus_sessions, self.data.workouts,
                      self.data.water, self.data.energy):
            days += [x.day for x in group]
        days += [e.logged_on or e.night_of for e in self.data.sleep]
        days += [d for b in self.data.bills for d in b.paid]
        return max((_day(d) for d in days), default=None)
