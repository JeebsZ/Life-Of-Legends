"""Run / walk log, the distance ladder and safe-progression advice, mixed into Game.
Pure logic: dates come in, no Flet. Tracking math lives in core/run.py.

Ladder: ONE set of distance tiers (1K .. Marathon) with a separate progress track per mode.
A 10K walk and a 10K run are different achievements (and different loads), so each mode
climbs on its own, but the tiers, rewards and safety rules are shared - one thing to learn.

- Clearing a tier = covering its distance in ONE session of that mode.
- The next tier then becomes AVAILABLE as a Challenge, from the next day (never the same
  day). Clearing a tier for the first time pays like a hard quest (CHALLENGE_XP/COINS) on
  top of the normal workout XP; one bonus per run even if it clears several tiers.
- Advice (run_advice) only ever suggests the Challenge when it is safe: not the unlock day,
  not after a session today, not with a rest nudge pending, not for an under-18 or a "low"
  energy check-in, and only if it fits a +10% weekly-volume ramp. Otherwise it suggests an
  easy session or rest. Nothing here sends reminders: an available tier never nags.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

from lol.core import nutrition
from lol.core.models import RUN_MODES, Completion, RunEntry
from lol.core.run import RunStats, fmt_duration, fmt_pace, met_for
from lol.core.run_cues import CUE_EVERY

if TYPE_CHECKING:
    from lol.core.models import EnergyCheckin, SaveData, WeightEntry


@dataclass(frozen=True)
class Tier:
    id: str
    label: str
    meters: float


TIERS: tuple[Tier, ...] = (
    Tier("1k", "1K", 1000), Tier("3k", "3K", 3000), Tier("5k", "5K", 5000),
    Tier("10k", "10K", 10000), Tier("15k", "15K", 15000),
    Tier("half", "Half marathon", 21097.5), Tier("30k", "30K", 30000),
    Tier("marathon", "Marathon", 42195),
)
TIER_BY_ID = {t.id: t for t in TIERS}
CHALLENGE_XP = 70  # = a hard quest (game.XP_BY_DIFFICULTY[3])
CHALLENGE_COINS = 35  # = game.COINS_BY_DIFFICULTY[3]
RUN_PATH = "warrior"
MIN_LOG_M = 50  # shorter sessions are not worth saving (the UI offers to discard)

RAMP = 1.10  # suggest at most +10% weekly volume
BASE_WEEKS = 4  # the ramp base = max(last week, average of the last 4 weeks)
START_WEEK_M = {"run": 6000.0, "walk": 10000.0}  # weekly room for someone with no history
REST_AFTER_DAYS = {"run": 3, "walk": 6}  # this many days in a row -> rest nudge
BIG_DAY_M = {"run": 15000.0, "walk": 21097.5}  # a session this long yesterday -> rest nudge
ADULT_AGE = 18

# pace badges: (label, slowest s/km that earns it), fastest first
PACE_BADGES = {
    "run": (("Blaze", 270), ("Swift", 330), ("Steady", 420), ("Finisher", 10 ** 9)),
    "walk": (("Power", 540), ("Brisk", 660), ("Steady", 840), ("Finisher", 10 ** 9)),
}

HEAT_NOTE = ("Hot or humid out? Go early or late, drink water before and after, and slow "
             "down in the heat. Pace matters less than coming home well.")
PAIN_NOTE = ("Stop if you feel pain, dizziness, chest tightness or unusual breathlessness. "
             "Walk it home and rest.")
YOUTH_NOTE = ("Under 18: keep it short, fun and easy. Bigger tiers aren't suggested - "
              "check with a coach or parent before longer distances.")
LOW_ENERGY_NOTE = "Low energy today: an easy walk or a rest day is the strong move."
TODAY_NOTE = "You've already moved today. Anything more is a bonus - keep it easy."


def pace_badge(mode: str, seconds: float, meters: float) -> str:
    pace = seconds / (meters / 1000)
    for label, limit in PACE_BADGES[mode]:
        if pace <= limit:
            return label
    return PACE_BADGES[mode][-1][0]


def effort_for(stats: RunStats) -> int:
    """Workout effort 1..10 from the average MET (run 10 km/h ~ 8, brisk walk ~ 3)."""
    if stats.moving_s <= 0 or stats.distance_m <= 0:
        return 3
    met = met_for(stats.distance_m / stats.moving_s * 3.6, stats.mode)
    return max(1, min(10, round(met * 0.8)))


@dataclass
class TierState:
    tier: Tier
    state: str  # "cleared" | "open" (the Challenge) | "locked"
    cleared_on: str | None = None  # ISO date of the first clear
    best_s: int | None = None  # fastest time for this distance (any run of the mode)
    badge: str | None = None  # pace badge of best_s
    available_from: date | None = None  # for "open": first day it is offered


@dataclass
class RunAdvice:
    mode: str
    suggest_challenge: bool  # True only when every safety rule allows it
    challenge: TierState | None  # the open tier (always shown as available/upcoming)
    headline: str  # Luma's one-line suggestion
    reason: str = ""  # why the Challenge isn't suggested today ("" when it is)
    easy_km: float = 0.0  # a suggested easy distance (0 = rest)
    week_km: float = 0.0  # this mode, last 7 days incl. today
    cap_km: float = 0.0  # +10% weekly room
    rest_nudge: str | None = None
    notes: list[str] = field(default_factory=list)  # safety notes (always shown)


class RunMixin:
    """Game methods for GPS runs. Relies on Game's data/_new_id/_award/_find/log_workout,
    BodyMixin.latest_weight/age and energy_today."""

    data: SaveData

    if TYPE_CHECKING:  # provided by Game / BodyMixin
        def _new_id(self, prefix: str) -> str: ...
        def _award(self, xp: int, coins: int, path_id: str, today: date) -> Completion: ...
        def _find(self, items: list, item_id: str) -> Any: ...
        def log_workout(self, minutes: int, today: date, type: str = ..., effort: int = ...,
                        notes: str = ..., quest_id: str | None = ..., path_id: str | None = ...,
                        exercises: Any = ..., *, started: str = ...) -> Completion: ...
        def delete_workout(self, session_id: str) -> None: ...
        def latest_weight(self) -> WeightEntry | None: ...
        def age(self, today: date) -> int | None: ...
        def is_minor(self, today: date) -> bool: ...
        def energy_today(self, today: date) -> EnergyCheckin | None: ...

    # ------------------------------------------------------------------ queries
    def runs(self, mode: str | None = None) -> list[RunEntry]:
        """Newest first."""
        rows = [r for r in self.data.runs if mode in (None, r.mode)]
        return sorted(rows, key=lambda r: (r.day, r.started), reverse=True)

    def run(self, run_id: str) -> RunEntry:
        return self._find(self.data.runs, run_id)

    def delete_run(self, run_id: str) -> None:
        """Remove a run and its workout entry. XP it earned stays."""
        r = self.run(run_id)
        self.data.runs.remove(r)
        if r.workout_id and any(w.id == r.workout_id for w in self.data.workouts):
            self.delete_workout(r.workout_id)

    def set_run_settings(self, *, mode: str | None = None, keep_awake: bool | None = None,
                         voice_cues: bool | None = None, cue_every: str | None = None) -> None:
        s = self.data.run_settings
        if cue_every is not None:
            if cue_every not in CUE_EVERY:
                raise ValueError(f"cue interval must be one of {CUE_EVERY}")
            s.cue_every = cue_every
        if voice_cues is not None:
            s.voice_cues = bool(voice_cues)
        if mode is not None:
            if mode not in RUN_MODES:
                raise ValueError(f"mode must be one of {RUN_MODES}")
            s.mode = mode
        if keep_awake is not None:
            s.keep_awake = bool(keep_awake)

    def run_body(self, today: date) -> dict:
        """What the kcal/steps math can use. Keys: weight_kg (None = not logged), height_cm,
        bmr (kcal/day or None if height/age/sex are missing)."""
        w = self.latest_weight()
        b = self.data.body
        age = self.age(today)
        bmr = None
        if w and b.height_cm and age is not None and b.sex:
            bmr = nutrition.bmr(w.kg, b.height_cm, age, b.sex)
        return {"weight_kg": w.kg if w else None, "height_cm": b.height_cm, "bmr": bmr}

    # ------------------------------------------------------------------ ladder
    def ladder(self, mode: str) -> list[TierState]:
        if mode not in RUN_MODES:
            raise ValueError(f"mode must be one of {RUN_MODES}")
        runs = sorted(self.runs(mode), key=lambda r: (r.day, r.started))
        out: list[TierState] = []
        prev_cleared: str | None = None
        opened = False
        for i, t in enumerate(TIERS):
            first = next((r for r in runs if r.distance_m >= t.meters
                          or t.id in r.cleared), None)
            times = [r.bests[t.id] for r in runs if t.id in r.bests]
            best = min(times) if times else None
            badge = pace_badge(mode, best, t.meters) if best else None
            if first is not None:
                out.append(TierState(t, "cleared", first.day, best, badge))
                prev_cleared = first.day
            elif not opened:
                opened = True
                avail = (date.fromisoformat(prev_cleared) + timedelta(days=1)
                         if i and prev_cleared else None)
                out.append(TierState(t, "open", None, best, badge, avail))
            else:
                out.append(TierState(t, "locked", None, best, badge))
        return out

    def personal_bests(self, mode: str) -> list[TierState]:
        return [s for s in self.ladder(mode) if s.best_s is not None]

    # ------------------------------------------------------------------ advice
    def _distance_between(self, mode: str, start: date, end: date) -> float:
        return sum(r.distance_m for r in self.data.runs
                   if r.mode == mode and start.isoformat() <= r.day <= end.isoformat())

    def weekly_volume(self, mode: str, today: date) -> tuple[float, float, float]:
        """(this week, ramp base, +10% cap) in metres. Week = the last 7 days incl. today;
        base = max(the 7 days before, the average of the 4 weeks before)."""
        week = self._distance_between(mode, today - timedelta(days=6), today)
        weeks = [self._distance_between(mode, today - timedelta(days=7 * k + 6),
                                        today - timedelta(days=7 * k))
                 for k in range(1, BASE_WEEKS + 1)]
        base = max(weeks[0], sum(weeks) / BASE_WEEKS)
        return week, base, max(base * RAMP, START_WEEK_M[mode])

    def _streak_days(self, mode: str, today: date) -> int:
        days = {r.day for r in self.data.runs if r.mode == mode}
        d = today if today.isoformat() in days else today - timedelta(days=1)
        n = 0
        while d.isoformat() in days:
            n += 1
            d -= timedelta(days=1)
        return n

    def run_advice(self, mode: str, today: date) -> RunAdvice:
        """Safe suggestion for today (see module doc). Never raises the stakes on its own:
        the Challenge is offered, never pushed."""
        lad = self.ladder(mode)
        challenge = next((s for s in lad if s.state == "open"), None)
        cleared = [s for s in lad if s.state == "cleared"]
        week, base, cap = self.weekly_volume(mode, today)
        room = max(0.0, cap - week)
        ran_today = any(r.mode == mode and r.day == today.isoformat() for r in self.data.runs)
        energy = self.energy_today(today)
        low = energy is not None and energy.level == "low"
        youth = self.is_minor(today)  # Body age or the onboarding age band

        rest = None
        yday = today - timedelta(days=1)
        streak = self._streak_days(mode, today)
        if streak >= REST_AFTER_DAYS[mode]:
            rest = (f"{streak} days in a row. A rest day lets your body adapt - "
                    "the ladder will wait.")
        elif self._distance_between(mode, yday, yday) >= BIG_DAY_M[mode]:
            rest = "Big effort yesterday. Rest or an easy walk today."

        notes = [HEAT_NOTE, PAIN_NOTE]
        if youth:
            notes.insert(0, YOUTH_NOTE)

        reason = ""
        if challenge is None:
            reason = "Every tier is cleared. Keep it fun and easy - recovery is training too."
        elif challenge.available_from and challenge.available_from > today:
            reason = (f"{challenge.tier.label} unlocked today. It opens tomorrow - "
                      "rest first.")
        elif ran_today:
            reason = TODAY_NOTE
        elif youth:
            reason = YOUTH_NOTE
        elif low:
            reason = LOW_ENERGY_NOTE
        elif rest:
            reason = rest
        elif room < challenge.tier.meters:
            reason = self._ramp_reason(challenge.tier, week, base, cap)
        ok = challenge is not None and not reason

        easy = 0.0
        if not (ok or ran_today or rest or room < 1000):
            top = cleared[-1].tier.meters if cleared else TIERS[0].meters
            easy = max(1.0, math.floor(min(top, room) / 500) * 0.5)
            if low or youth:
                easy = min(easy, 3.0)
        if ok and challenge is not None:
            headline = f"Challenge ready: {challenge.tier.label}. Go steady, finish strong."
        elif easy:
            headline = f"Suggested: an easy {easy:g} km {'walk' if mode == 'walk' else 'run'}."
        else:
            headline = "Suggested: rest or a gentle stroll today."
        return RunAdvice(mode, ok, challenge, headline, reason, easy, round(week / 1000, 2),
                         round(cap / 1000, 1), rest, notes)

    @staticmethod
    def _ramp_reason(tier: Tier, week: float, base: float, cap: float) -> str:
        """Why the Challenge doesn't fit this week's +10% room."""
        km = f"{week / 1000:.1f} of {cap / 1000:.1f} km"
        if cap >= tier.meters:
            return (f"This week's safe volume is nearly used ({km}). "
                    f"{tier.label} fits better after a few rest days.")
        if base <= 0:
            return f"Build a few easy weeks first ({km} this week)."
        weeks = max(1, math.ceil(math.log(tier.meters / base) / math.log(RAMP)))
        return (f"Build your weekly base first ({km} this week). At +10% a week, "
                f"{tier.label} fits in about {weeks} week{'s' if weeks > 1 else ''}.")

    # ------------------------------------------------------------------ logging
    def log_run(self, stats: RunStats, today: date, *, started: str = "",
                goal: str = "", basic: bool = False) -> Completion:
        """Save a finished session: a RunEntry plus a cardio WorkoutSession (normal workout
        XP and caps; Warrior Path). First clears of ladder tiers in this mode add one
        Challenge bonus (CHALLENGE_XP / CHALLENGE_COINS). Completion.ref_id = run id.
        basic = a free run started without the stretch ad (shown as steps + time only)."""
        if stats.mode not in RUN_MODES:
            raise ValueError(f"mode must be one of {RUN_MODES}")
        if goal and goal not in TIER_BY_ID:
            raise ValueError(f"unknown tier: {goal}")
        if stats.distance_m < 0 or stats.moving_s < 0:
            raise ValueError("distance and time cannot be negative")
        done = {s.tier.id for s in self.ladder(stats.mode) if s.state == "cleared"}
        newly = [t.id for t in TIERS
                 if stats.distance_m >= t.meters and t.id not in done]
        km = stats.distance_m / 1000
        notes = (f"{'Walk' if stats.mode == 'walk' else 'Run'} {km:.2f} km · "
                 f"{fmt_duration(stats.moving_s)} · {fmt_pace(stats.avg_pace)} /km (GPS)")
        c = self.log_workout(round(stats.moving_s / 60), today, "cardio", effort_for(stats),
                             notes, None, RUN_PATH, started=started)
        workout_id = c.ref_id
        if newly:
            bonus = self._award(CHALLENGE_XP, CHALLENGE_COINS, RUN_PATH, today)
            c = Completion(c.xp + bonus.xp, c.coins + bonus.coins,
                           c.levels_gained + bonus.levels_gained, RUN_PATH,
                           c.path_levels_gained + bonus.path_levels_gained,
                           c.capped or bonus.capped)
        entry = RunEntry(
            self._new_id("r"), today.isoformat(), started, stats.mode,
            round(stats.distance_m, 1), round(stats.moving_s), round(stats.elapsed_s),
            stats.elev_gain_m, round(stats.kcal), round(stats.rest_kcal), stats.steps,
            round(stats.weight_kg, 1), stats.weight_assumed,
            [round(s) for s in stats.splits],
            [[[round(la, 6), round(lo, 6)] for la, lo in seg] for seg in stats.route if seg],
            {k: round(v) for k, v in stats.bests.items()}, newly, goal, workout_id,
            c.xp, c.coins, basic)
        self.data.runs.append(entry)
        c.ref_id = entry.id
        return c
