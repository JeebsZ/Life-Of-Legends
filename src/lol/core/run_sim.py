"""A recorded-style loop for testing without real GPS (debug only; the UI enables it with the
LOL_FAKE_GPS=1 env var). Deterministic: the same seed gives the same fixes.

The loop runs around Rizal Park (Luneta), Manila: Roxas Blvd side -> along T.M. Kalaw ->
past the Rizal Monument -> back along the south promenade. About 2.4 km per lap.
The replay adds the things real GPS does: a few low-accuracy fixes, one teleport
glitch, slowly drifting ~3 m error, a 25 s stop at a crossing (auto-pause) and some altitude wobble.
"""

from __future__ import annotations

import itertools
import math
import random
from collections.abc import Iterator

from lol.core.run import Fix, haversine_m

# (lat, lon) waypoints, clockwise from the Roxas Blvd / Kalaw corner
RIZAL_PARK_LOOP: tuple[tuple[float, float], ...] = (
    (14.58405, 120.97655),
    (14.58330, 120.97905),
    (14.58255, 120.98150),
    (14.58180, 120.98400),
    (14.58120, 120.98545),
    (14.58010, 120.98520),
    (14.57905, 120.98490),
    (14.57960, 120.98270),
    (14.58030, 120.98020),
    (14.58100, 120.97780),
    (14.58020, 120.97640),
    (14.58200, 120.97640),
    (14.58405, 120.97655),
)
SIM_PACE_S_PER_KM = {"run": 360.0, "walk": 660.0}  # 6:00 /km run, 11:00 /km walk
STOP_AT_S = 150.0  # a stop at a crossing, this many seconds in
STOP_FOR_S = 25.0
GLITCH_AT_S = 300.0  # one 300 m teleport fix
ERROR_KEEP = 0.9  # error memory per fix
ERROR_STEP_M = 1.2  # -> about 2.8 m standard error at rest
BAD_EVERY = 47  # every Nth fix has 40 m accuracy (dropped by the filter)


def loop_length_m(loop: tuple[tuple[float, float], ...] = RIZAL_PARK_LOOP) -> float:
    return sum(haversine_m(*a, *b) for a, b in itertools.pairwise(loop))


def _position(loop: tuple[tuple[float, float], ...], dist: float) -> tuple[float, float]:
    total = loop_length_m(loop)
    dist %= total
    for a, b in itertools.pairwise(loop):
        leg = haversine_m(*a, *b)
        if dist <= leg:
            f = dist / leg if leg else 0.0
            return a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f
        dist -= leg
    return loop[-1]


def simulate(mode: str = "run", start_t: float = 0.0, seconds: float | None = None,
             seed: int = 7, interval_s: float = 1.0) -> Iterator[Fix]:
    """Fixes every interval_s at the mode's sim pace. Endless if seconds is None."""
    rng = random.Random(seed)
    speed = 1000.0 / SIM_PACE_S_PER_KM[mode]
    m_per_deg = math.pi / 180 * 6_371_008.8
    t = 0.0
    dist = 0.0
    n = 0
    en = ee = 0.0  # GPS error drifts slowly (AR(1)), like a real receiver, not white noise
    while seconds is None or t <= seconds:
        stopped = STOP_AT_S <= t < STOP_AT_S + STOP_FOR_S
        lat, lon = _position(RIZAL_PARK_LOOP, dist)
        en = ERROR_KEEP * en + rng.gauss(0, ERROR_STEP_M)
        ee = ERROR_KEEP * ee + rng.gauss(0, ERROR_STEP_M)
        north, east = en, ee
        acc = rng.uniform(4.0, 9.0)
        if n and n % BAD_EVERY == 0:
            acc = 40.0
            north, east = north + rng.gauss(0, 30), east + rng.gauss(0, 30)
        lat += north / m_per_deg
        lon += east / (m_per_deg * math.cos(math.radians(lat)))
        if abs(t - GLITCH_AT_S) < interval_s / 2:
            lat += 300 / m_per_deg  # a teleport the filter must drop
        alt = 8.0 + 4.0 * math.sin(dist / 400.0) + rng.gauss(0, 0.6)
        yield Fix(lat, lon, round(acc, 1), start_t + t, round(alt, 1))
        n += 1
        t += interval_s
        if not stopped:
            dist += speed * interval_s
