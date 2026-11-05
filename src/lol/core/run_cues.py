"""Spoken coaching cues for a walk/run, built from short stitched clips. Pure: totals come in,
lists of clip keys come out; the UI plays each list with audio.play_sequence.

Numbers make whole sentences combinatorial, so a cue is a sequence of tiny clips:
    ["distance", "n5", "kilometres", "time", "n28", "minutes", "pace", "n5", "n38",
     "per_kilometre", "steps", "about", "n5", "thousand", "n2", "hundred"]
Clip files: src/assets/voice/cue_<key>.wav (tools/voice/make_cues.py from cues.json; OGG copies
for Android via tools/sfx/encode_ogg.py). The lines are name-free on purpose.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

CUE_EVERY = ("1km", "0.5km", "5min")
NUMBER_KEYS = tuple(f"n{i}" for i in range(60)) + ("n60", "n70", "n80", "n90")
WORD_KEYS = ("distance", "time", "pace", "steps", "about", "point", "oh", "kilometre",
             "kilometres", "per_kilometre", "hour", "hours", "minute", "minutes", "seconds",
             "hundred", "thousand", "k", "half_marathon", "marathon")
PHRASE_KEYS = ("halfway", "goal_reached", "tier_cleared", "water", "ease_off")
ALL_KEYS = NUMBER_KEYS + WORD_KEYS + PHRASE_KEYS

WATER_EVERY_S = {"run": 20 * 60, "walk": 30 * 60}  # moving time between water nudges
EASE_OFF_RATIO = 0.85  # a km split this much faster than the earlier average = going out hot
EASE_OFF_BEFORE = 0.6  # ... only in the first 60% of a goal distance
EASE_OFF_GAP_KM = 3  # at most one ease-off nudge per 3 km


def number_keys(n: int) -> list[str]:
    """0..9999 as clip keys: 0-59 direct, 60-99 tens + unit, then hundreds/thousands."""
    n = int(n)
    if n < 0:
        raise ValueError("negative number")
    if n < 60:
        return [f"n{n}"]
    if n < 100:
        tens, unit = divmod(n, 10)
        return [f"n{tens * 10}"] + ([f"n{unit}"] if unit else [])
    if n < 1000:
        h, rest = divmod(n, 100)
        return [f"n{h}", "hundred"] + (number_keys(rest) if rest else [])
    if n < 10000:
        th, rest = divmod(n, 1000)
        return [f"n{th}", "thousand"] + (number_keys(rest) if rest else [])
    raise ValueError("number too large for cues")


def distance_keys(meters: float) -> list[str]:
    """'Distance five point two kilometres' (one decimal; '.0' is dropped)."""
    tenths = round(meters / 100)
    whole, tenth = divmod(tenths, 10)
    out = ["distance", *number_keys(whole)]
    if tenth:
        out += ["point", f"n{tenth}"]
    return [*out, "kilometre" if tenths == 10 else "kilometres"]


def time_keys(seconds: float) -> list[str]:
    """'Time twenty-eight minutes' / 'Time one hour five minutes' / under a minute: seconds."""
    s = max(0, int(seconds))
    h, m = divmod(s // 60, 60)
    out = ["time"]
    if h:
        out += [*number_keys(h), "hour" if h == 1 else "hours"]
    if m or not h:
        if not h and not m:
            return [*out, *number_keys(s % 60), "seconds"]
        out += [*number_keys(m), "minute" if m == 1 else "minutes"]
    return out


def pace_keys(s_per_km: float | None) -> list[str]:
    """'Pace five thirty-eight per kilometre'; 5:05 -> 'five oh five'; 6:00 -> 'six minutes'."""
    if s_per_km is None or s_per_km <= 0 or s_per_km >= 60 * 60:
        return []
    m, s = divmod(round(s_per_km), 60)
    out = ["pace", *number_keys(m)]
    if s == 0:
        out.append("minutes")
    elif s < 10:
        out += ["oh", f"n{s}"]
    else:
        out += number_keys(s)
    return [*out, "per_kilometre"]


def steps_keys(steps: int) -> list[str]:
    """'Steps about five thousand two hundred' (rounded to 100; nothing under 100)."""
    hundreds = round(steps / 100)
    if hundreds <= 0:
        return []
    th, hu = divmod(hundreds, 10)
    out = ["steps", "about"]
    if th:
        out += [*number_keys(th), "thousand"]
    if hu:
        out += [f"n{hu}", "hundred"]
    return out


def update_keys(meters: float, moving_s: float, pace: float | None, steps: int) -> list[str]:
    """The regular update: distance, time, pace, steps."""
    return [*distance_keys(meters), *time_keys(moving_s), *pace_keys(pace), *steps_keys(steps)]


def tier_keys(tier_id: str) -> list[str]:
    """'five K', 'half marathon', 'marathon'."""
    if tier_id == "half":
        return ["half_marathon"]
    if tier_id == "marathon":
        return ["marathon"]
    km = int(tier_id.rstrip("k"))
    return [*number_keys(km), "k"]


@dataclass
class CueCoach:
    """Decides which cues are due as a session goes on. Feed it totals with update().

    every:  "1km" | "0.5km" | "5min" (regular update interval)
    goal_m: the picked goal distance (halfway + goal reached), None = free run
    tiers:  (tier id, metres) not yet cleared in this mode -> "Tier cleared" on crossing
    """

    mode: str = "run"
    every: str = "1km"
    goal_m: float | None = None
    tiers: Sequence[tuple[str, float]] = ()
    _last_bucket: int = 0
    _halfway: bool = False
    _goal: bool = False
    _tiers_done: set[str] = field(default_factory=set)
    _next_water: float = 0.0
    _splits_seen: int = 0
    _last_ease_km: int = -EASE_OFF_GAP_KM

    def __post_init__(self) -> None:
        if self.every not in CUE_EVERY:
            raise ValueError(f"cue interval must be one of {CUE_EVERY}")
        self._next_water = WATER_EVERY_S.get(self.mode, WATER_EVERY_S["run"])

    def _bucket(self, meters: float, moving_s: float) -> int:
        if self.every == "5min":
            return int(moving_s // 300)
        step = 500.0 if self.every == "0.5km" else 1000.0
        return int(meters // step)

    def update(self, meters: float, moving_s: float, pace: float | None, steps: int,
               splits: Iterable[float] = ()) -> list[list[str]]:
        """Cues due now, in speaking order (each one a list of clip keys)."""
        out: list[list[str]] = []
        b = self._bucket(meters, moving_s)
        if b > self._last_bucket:
            self._last_bucket = b
            out.append(update_keys(meters, moving_s, pace, steps))
        if self.goal_m:
            if not self._halfway and meters >= self.goal_m / 2 and self.goal_m >= 1000:
                self._halfway = True
                out.append(["halfway"])
            if not self._goal and meters >= self.goal_m:
                self._goal = self._halfway = True
                out.append(["goal_reached"])
        for tid, tm in self.tiers:
            if tid not in self._tiers_done and meters >= tm:
                self._tiers_done.add(tid)
                out.append(["tier_cleared", *tier_keys(tid)])
        sp = list(splits)
        if len(sp) > self._splits_seen:
            self._splits_seen = len(sp)
            if self._going_out_hot(sp, meters):
                self._last_ease_km = len(sp)
                out.append(["ease_off"])
        if moving_s >= self._next_water:
            self._next_water += WATER_EVERY_S.get(self.mode, WATER_EVERY_S["run"])
            out.append(["water"])
        return out

    def _going_out_hot(self, sp: list[float], meters: float) -> bool:
        """The latest km was much faster than the ones before, early in a long goal."""
        if len(sp) < 3 or not self.goal_m or self.goal_m < 5000:
            return False
        if meters > self.goal_m * EASE_OFF_BEFORE:
            return False
        if len(sp) - self._last_ease_km < EASE_OFF_GAP_KM:
            return False
        earlier = sp[:-1]
        return sp[-1] < EASE_OFF_RATIO * (sum(earlier) / len(earlier))


def keys_used(cues: Iterable[Sequence[str]]) -> set[str]:
    return {k for cue in cues for k in cue}

