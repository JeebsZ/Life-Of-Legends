"""Walk/run tracking math. Pure: fixes (with their own timestamps) come in, numbers come out.

Pipeline for each GPS fix (see Tracker.add):
1. Drop fixes whose accuracy radius is worse than MAX_ACCURACY_M.
2. Drop "teleports": an implied speed above MAX_SPEED[mode] from the last kept point, after
   giving the fix its accuracy radius as slack. If JUMP_RESET_AFTER jumps in a row agree with
   each other, the GPS has re-locked somewhere else: start a new segment there (the gap is
   not counted as distance).
3. Light smoothing: an exponential moving average; a new fix weighs 0.45 at <= 11 m accuracy,
   down to 0.3 for poorer fixes (about 1 s of lag at 1 fix/s).
4. Jitter gate: the anchor only moves once the smoothed position is MIN_MOVE_M (or half the
   accuracy, at most 8 m) away, so standing still does not add distance.
5. Auto-pause: a stretch slower than STILL_SPEED_MS adds no moving time, and one stretch never
   adds more than AUTOPAUSE_S. After AUTOPAUSE_S with no progress the tracker reports
   auto_paused. Manual pause starts a new segment on resume.

Energy: MET x kg x moving hours, MET interpolated by speed from the 2011 Compendium of
Physical Activities (Ainsworth et al.). Walking codes 17152-17231, running codes 12029-12135
(see WALK_MET / RUN_MET). Moving time is cut into ~60 s chunks, each with its own speed. Net
kcal = gross minus resting burn over the same moving time (BMR / 24 h, Mifflin-St Jeor from
core.nutrition; 1 MET if the body profile is incomplete).

Steps are ESTIMATED: distance / step length. Walking step = 0.415 x height; running step grows
with speed (RUN_STEP_*). Not a pedometer.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

EARTH_RADIUS_M = 6_371_008.8
MODES = ("walk", "run")

# --- filter tuning ---------------------------------------------------------------------------
MAX_ACCURACY_M = 25.0
MAX_SPEED = {"run": 12.0, "walk": 6.0}  # m/s; faster than this between fixes = a GPS jump
JUMP_RESET_AFTER = 3
MIN_MOVE_M = 5.0
MAX_GATE_M = 8.0
AUTOPAUSE_S = 10.0
SMOOTH_ALPHA = (0.3, 0.45)  # EMA weight of a new fix: min (poor accuracy) .. max (good)
SMOOTH_REF_ACC = 5.0  # alpha = SMOOTH_REF_ACC / accuracy, clamped to SMOOTH_ALPHA
STILL_SPEED_MS = 0.5  # slower than this between kept points = standing (no moving time)
ELEV_HYSTERESIS_M = 3.0  # altitude must move this much before gain counts (GPS altitude is noisy)
PACE_WINDOW_S = 30.0  # current pace looks back this many moving seconds
SPLIT_M = 1000.0
CHUNK_S = 60.0  # energy/steps are computed per ~60 s of moving time

# --- body defaults (labelled "estimate" in the UI when used) ---------------------------------
DEFAULT_WEIGHT_KG = 70.0
DEFAULT_HEIGHT_CM = 170.0

# --- METs: (km/h, MET), 2011 Compendium of Physical Activities -------------------------------
WALK_MET = (
    (1.6, 2.0),  # 17150 walking, household / very slow
    (3.2, 2.8),  # 17152 2.0 mph, level, slow
    (4.0, 3.0),  # 17170 2.5 mph
    (4.8, 3.5),  # 17190 2.8-3.2 mph, level, moderate
    (5.6, 4.3),  # 17200 3.5 mph, level, brisk
    (6.4, 5.0),  # 17220 4.0 mph, level, very brisk
    (7.2, 7.0),  # 17230 4.5 mph, very, very brisk
    (8.0, 8.3),  # 17231 5.0 mph
)
RUN_MET = (
    (6.4, 6.0),  # 12029 4 mph (15 min/mile)
    (8.0, 8.3),  # 12030 5 mph
    (8.4, 9.0),  # 12040 5.2 mph
    (9.7, 9.8),  # 12050 6 mph
    (10.8, 10.5),  # 12060 6.7 mph
    (11.3, 11.0),  # 12070 7 mph
    (12.1, 11.5),  # 12080 7.5 mph
    (12.9, 11.8),  # 12090 8 mph
    (13.8, 12.3),  # 12100 8.6 mph
    (14.5, 12.8),  # 12110 9 mph
    (16.1, 14.5),  # 12120 10 mph
    (17.7, 16.0),  # 12130 11 mph
    (19.3, 19.0),  # 12132 12 mph
    (20.9, 19.8),  # 12134 13 mph
    (22.5, 23.0),  # 12135 14 mph
)
RUN_FROM_KMH = {"run": 6.4, "walk": 8.0}  # below this speed the walking table applies

WALK_STEP_RATIO = 0.415  # step length / height
RUN_STEP_BASE = 0.55  # step length / height at RUN_STEP_REF_MS
RUN_STEP_REF_MS = 2.78  # 10 km/h
RUN_STEP_SLOPE = 0.12  # extra ratio per m/s faster
RUN_STEP_RANGE = (0.45, 0.95)


# --- geometry --------------------------------------------------------------------------------
def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def _xy(lat: float, lon: float, lat0: float) -> tuple[float, float]:
    """Local equirectangular metres (fine for a run-sized area)."""
    k = math.pi / 180 * EARTH_RADIUS_M
    return lon * k * math.cos(math.radians(lat0)), lat * k


def simplify(points: Sequence[tuple[float, float]], tolerance_m: float = 4.0
             ) -> list[tuple[float, float]]:
    """Douglas-Peucker on (lat, lon); keeps the first and last point."""
    n = len(points)
    if n <= 2:
        return list(points)
    lat0 = points[0][0]
    xy = [_xy(la, lo, lat0) for la, lo in points]
    keep = [False] * n
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        i, j = stack.pop()
        (ax, ay), (bx, by) = xy[i], xy[j]
        dx, dy = bx - ax, by - ay
        seg2 = dx * dx + dy * dy
        best, idx = -1.0, -1
        for k in range(i + 1, j):
            px, py = xy[k]
            if seg2 == 0:
                d = math.hypot(px - ax, py - ay)
            else:
                t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg2))
                d = math.hypot(px - (ax + t * dx), py - (ay + t * dy))
            if d > best:
                best, idx = d, k
        if idx >= 0 and best > tolerance_m:
            keep[idx] = True
            stack += [(i, idx), (idx, j)]
    return [p for p, k in zip(points, keep, strict=True) if k]


# --- track model -----------------------------------------------------------------------------
@dataclass(frozen=True)
class Fix:
    """One GPS reading. t = seconds (any epoch, but monotonic within a run)."""

    lat: float
    lon: float
    accuracy: float
    t: float
    alt: float | None = None


@dataclass(frozen=True)
class TrackPoint:
    """A kept (filtered, smoothed) point with running totals at that point."""

    lat: float
    lon: float
    t: float
    seg: int
    dist: float  # cumulative metres
    moving: float  # cumulative moving seconds
    alt: float | None = None


class Tracker:
    """Incremental track for one session. Feed fixes with add(); read totals any time."""

    def __init__(self, mode: str = "run", start_t: float = 0.0) -> None:
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        self.mode = mode
        self.start_t = start_t
        self.points: list[TrackPoint] = []
        self.seg = 0
        self.paused = False
        self.dropped = 0  # fixes thrown away (inaccurate or jumps)
        self.last_fix: Fix | None = None  # latest fix seen (for the accuracy indicator)
        self.elev_gain = 0.0
        self.has_alt = False
        self._ema: tuple[float, float] | None = None
        self._jumps: list[Fix] = []
        self._seg_open = False  # current segment has its first point
        self._elev_base: float | None = None
        self._paused_s = 0.0
        self._paused_at: float | None = None

    # ---- totals
    @property
    def distance_m(self) -> float:
        return self.points[-1].dist if self.points else 0.0

    @property
    def moving_s(self) -> float:
        return self.points[-1].moving if self.points else 0.0

    def elapsed_s(self, now: float) -> float:
        return max(0.0, now - self.start_t)

    def auto_paused(self, now: float) -> bool:
        """No forward progress for AUTOPAUSE_S (and not paused by hand)."""
        if self.paused or not self._seg_open or not self.points:
            return False
        return now - self.points[-1].t > AUTOPAUSE_S

    def current_pace(self, now: float) -> float | None:
        """Seconds per km over the last PACE_WINDOW_S of moving time; None while still."""
        if not self.points or self.auto_paused(now) or self.paused:
            return None
        last = self.points[-1]
        ref = None
        for p in reversed(self.points):
            if p.seg != last.seg:
                break
            ref = p
            if last.moving - p.moving >= PACE_WINDOW_S:
                break
        if ref is None or last.dist - ref.dist < 10 or last.moving <= ref.moving:
            return None
        return (last.moving - ref.moving) / ((last.dist - ref.dist) / 1000)

    # ---- control
    def pause(self, now: float) -> None:
        if not self.paused:
            self.paused, self._paused_at = True, now

    def resume(self, now: float) -> None:
        if self.paused:
            self._paused_s += max(0.0, now - (self._paused_at or now))
            self.paused, self._paused_at = False, None
            self._new_segment()

    def _new_segment(self) -> None:
        self.seg += 1
        self._seg_open = False
        self._ema = None
        self._jumps = []
        self._elev_base = None

    # ---- input
    def add(self, fix: Fix) -> str:
        """Feed one fix. Returns what happened: ok | first | still | inaccurate | jump |
        paused | stale."""
        self.last_fix = fix
        if self.paused:
            return "paused"
        if fix.accuracy is None or fix.accuracy > MAX_ACCURACY_M:
            self.dropped += 1
            return "inaccurate"
        if not self._seg_open:
            self._open(fix)
            return "first"
        anchor = self.points[-1]
        dt = fix.t - anchor.t
        if dt <= 0:
            return "stale"
        # teleport check against the raw fix, with the accuracy radius as slack
        raw = haversine_m(anchor.lat, anchor.lon, fix.lat, fix.lon)
        if max(0.0, raw - fix.accuracy) / dt > MAX_SPEED[self.mode]:
            return self._jump(fix)
        self._jumps = []
        lat, lon = self._smooth(fix)
        d = haversine_m(anchor.lat, anchor.lon, lat, lon)
        gate = max(MIN_MOVE_M, min(MAX_GATE_M, fix.accuracy / 2))
        if d < gate:
            self._elev(fix)
            return "still"
        moving = min(dt, AUTOPAUSE_S) if d / dt >= STILL_SPEED_MS else 0.0
        self._elev(fix)
        self.points.append(TrackPoint(lat, lon, fix.t, self.seg, anchor.dist + d,
                                      anchor.moving + moving, fix.alt))
        return "ok"

    def _open(self, fix: Fix) -> None:
        dist, moving = (self.points[-1].dist, self.points[-1].moving) if self.points else (0, 0)
        self._ema = (fix.lat, fix.lon)
        self._seg_open = True
        self._elev(fix)
        self.points.append(TrackPoint(fix.lat, fix.lon, fix.t, self.seg, dist, moving,
                                      fix.alt))

    def _jump(self, fix: Fix) -> str:
        self.dropped += 1
        if self._jumps:
            prev = self._jumps[-1]
            dt = fix.t - prev.t
            ok = dt > 0 and haversine_m(prev.lat, prev.lon, fix.lat, fix.lon) / dt \
                <= MAX_SPEED[self.mode]
            self._jumps = [*self._jumps, fix] if ok else [fix]
        else:
            self._jumps = [fix]
        if len(self._jumps) >= JUMP_RESET_AFTER:  # the GPS re-locked elsewhere: trust it
            self._new_segment()
            self._open(fix)
            self.dropped -= 1
            return "relock"
        return "jump"

    def _smooth(self, fix: Fix) -> tuple[float, float]:
        lo, hi = SMOOTH_ALPHA
        alpha = max(lo, min(hi, SMOOTH_REF_ACC / max(fix.accuracy, 0.1)))
        if self._ema is None:
            self._ema = (fix.lat, fix.lon)
        else:
            la, lo = self._ema
            self._ema = (la + alpha * (fix.lat - la), lo + alpha * (fix.lon - lo))
        return self._ema

    def _elev(self, fix: Fix) -> None:
        if fix.alt is None:
            return
        self.has_alt = True
        if self._elev_base is None:
            self._elev_base = fix.alt
            return
        diff = fix.alt - self._elev_base
        if diff >= ELEV_HYSTERESIS_M:
            self.elev_gain += diff
            self._elev_base = fix.alt
        elif diff <= -ELEV_HYSTERESIS_M:
            self._elev_base = fix.alt

    # ---- derived
    def route(self) -> list[list[tuple[float, float]]]:
        """Kept points as one (lat, lon) list per segment."""
        out: list[list[tuple[float, float]]] = []
        seg = None
        for p in self.points:
            if p.seg != seg:
                out.append([])
                seg = p.seg
            out[-1].append((p.lat, p.lon))
        return out


# --- splits and bests ------------------------------------------------------------------------
def _moving_at(points: Sequence[TrackPoint], dist: float) -> float:
    """Cumulative moving seconds when the track reached `dist` metres (interpolated)."""
    lo, hi = 0, len(points) - 1
    if dist <= points[0].dist:
        return points[0].moving
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if points[mid].dist < dist:
            lo = mid
        else:
            hi = mid
    a, b = points[lo], points[hi]
    if b.dist <= a.dist:
        return b.moving
    return a.moving + (b.moving - a.moving) * (dist - a.dist) / (b.dist - a.dist)


def splits(points: Sequence[TrackPoint], every_m: float = SPLIT_M) -> list[float]:
    """Moving seconds for each full `every_m` (1 km); the remainder is not a split."""
    if not points:
        return []
    total = points[-1].dist
    out, prev = [], points[0].moving
    k = 1
    while k * every_m <= total + 1e-6:
        t = _moving_at(points, k * every_m)
        out.append(t - prev)
        prev = t
        k += 1
    return out


def best_effort(points: Sequence[TrackPoint], dist_m: float) -> float | None:
    """Fastest moving time to cover dist_m anywhere inside this track (None if too short)."""
    if not points or points[-1].dist + 1e-6 < dist_m:
        return None
    best = None
    for p in points:
        if p.dist + 1e-6 < dist_m:
            continue
        t = p.moving - _moving_at(points, p.dist - dist_m)
        if best is None or t < best:
            best = t
    return best


# --- energy and steps ------------------------------------------------------------------------
def _interp(table: Sequence[tuple[float, float]], x: float) -> float:
    if x <= table[0][0]:
        return table[0][1]
    for (x0, y0), (x1, y1) in itertools.pairwise(table):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return table[-1][1]


def met_for(speed_kmh: float, mode: str = "run") -> float:
    """Compendium MET at this speed. Run mode uses the walking table below 6.4 km/h; walk
    mode switches to the running table above 8 km/h (a walk that became a jog)."""
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    if speed_kmh <= 0:
        return 1.0
    return _interp(WALK_MET if speed_kmh < RUN_FROM_KMH[mode] else RUN_MET, speed_kmh)


def step_length_m(speed_ms: float, height_cm: float, mode: str = "run") -> float:
    """Estimated step length. Walking pace (or walk mode below 8 km/h): 0.415 x height.
    Running: RUN_STEP_BASE x height at 10 km/h, longer when faster, within RUN_STEP_RANGE."""
    h = height_cm / 100
    if speed_ms * 3.6 < RUN_FROM_KMH[mode]:
        return WALK_STEP_RATIO * h
    lo, hi = RUN_STEP_RANGE
    ratio = RUN_STEP_BASE + RUN_STEP_SLOPE * (speed_ms - RUN_STEP_REF_MS)
    return max(lo, min(hi, ratio)) * h


def chunks(points: Sequence[TrackPoint], every_s: float = CHUNK_S
           ) -> list[tuple[float, float]]:
    """(metres, moving seconds) per ~every_s of moving time."""
    out: list[tuple[float, float]] = []
    d_acc = t_acc = 0.0
    for a, b in itertools.pairwise(points):
        if b.seg != a.seg:
            continue
        d_acc += b.dist - a.dist
        t_acc += b.moving - a.moving
        if t_acc >= every_s:
            out.append((d_acc, t_acc))
            d_acc = t_acc = 0.0
    if t_acc > 0:
        out.append((d_acc, t_acc))
    return out


def kcal_gross(parts: Iterable[tuple[float, float]], weight_kg: float, mode: str) -> float:
    """Sum of MET(speed) x kg x hours over (metres, seconds) chunks."""
    total = 0.0
    for d, t in parts:
        if t <= 0:
            continue
        total += met_for(d / t * 3.6, mode) * weight_kg * t / 3600
    return total


def rest_kcal(moving_s: float, weight_kg: float, bmr_kcal_day: float | None) -> float:
    """Resting burn over the same time: BMR/24 h, else 1 MET (1 kcal/kg/h)."""
    if bmr_kcal_day:
        return bmr_kcal_day * moving_s / 86400
    return weight_kg * moving_s / 3600


def steps_for(parts: Iterable[tuple[float, float]], height_cm: float, mode: str) -> int:
    total = 0.0
    for d, t in parts:
        if t <= 0 or d <= 0:
            continue
        total += d / step_length_m(d / t, height_cm, mode)
    return round(total)


def pace_s_per_km(dist_m: float, seconds: float) -> float | None:
    return seconds / (dist_m / 1000) if dist_m >= 10 and seconds > 0 else None


def fmt_pace(s_per_km: float | None) -> str:
    """'5:42' (per km) or '-:--'."""
    if s_per_km is None or s_per_km <= 0 or s_per_km > 3600:
        return "-:--"
    m, s = divmod(round(s_per_km), 60)
    return f"{m}:{s:02d}"


def fmt_duration(seconds: float) -> str:
    """'42:07' or '1:05:12'."""
    s = max(0, round(seconds))
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


@dataclass
class RunStats:
    """Everything the summary shows. Estimates are labelled by the *_assumed flags."""

    mode: str
    distance_m: float
    moving_s: float
    elapsed_s: float
    avg_pace: float | None  # s per km over moving time
    splits: list[float] = field(default_factory=list)
    elev_gain_m: float | None = None  # None = the fixes had no altitude
    kcal: float = 0.0
    rest_kcal: float = 0.0
    steps: int = 0
    weight_kg: float = DEFAULT_WEIGHT_KG
    weight_assumed: bool = True
    height_assumed: bool = True
    rest_from_bmr: bool = False
    bests: dict[str, float] = field(default_factory=dict)  # tier id -> fastest seconds
    route: list[list[tuple[float, float]]] = field(default_factory=list)  # per segment

    @property
    def net_kcal(self) -> float:
        return max(0.0, self.kcal - self.rest_kcal)


def summarize(tracker: Tracker, now: float, *, weight_kg: float | None = None,
              height_cm: float | None = None, bmr_kcal_day: float | None = None,
              tiers: Iterable[tuple[str, float]] = (), simplify_m: float = 4.0) -> RunStats:
    """Final numbers for a finished session. Missing weight/height use the labelled
    defaults. `tiers`: (id, metres) whose best effort inside this run should be measured."""
    pts = tracker.points
    kg = weight_kg or DEFAULT_WEIGHT_KG
    cm = height_cm or DEFAULT_HEIGHT_CM
    parts = chunks(pts)
    moving = tracker.moving_s
    bests = {}
    for tid, dist in tiers:
        b = best_effort(pts, dist)
        if b is not None:
            bests[tid] = b
    return RunStats(
        mode=tracker.mode,
        distance_m=tracker.distance_m,
        moving_s=moving,
        elapsed_s=tracker.elapsed_s(now),
        avg_pace=pace_s_per_km(tracker.distance_m, moving),
        splits=splits(pts),
        elev_gain_m=round(tracker.elev_gain, 1) if tracker.has_alt else None,
        kcal=kcal_gross(parts, kg, tracker.mode),
        rest_kcal=rest_kcal(moving, kg, bmr_kcal_day),
        steps=steps_for(parts, cm, tracker.mode),
        weight_kg=kg,
        weight_assumed=weight_kg is None,
        height_assumed=height_cm is None,
        rest_from_bmr=bool(bmr_kcal_day),
        bests=bests,
        route=[simplify(seg, simplify_m) for seg in tracker.route()],
    )
