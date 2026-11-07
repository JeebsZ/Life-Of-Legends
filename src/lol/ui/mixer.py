"""A tiny audio "bus" shared by sfx.py (effects) and audio.py (Luma's voice).

Both players stay fire-and-forget; this module only keeps two clocks and answers two questions:

- **Voice waits for reward sounds.** When an effect in FOREGROUND starts (the quest chime, the
  level-up strum, the Luma hum ...), `sfx_started` records when its *audible* part ends
  (AUDIBLE, measured by tools/sfx/pack_sfx.py / make_sfx.py: the time until the sound's
  short-term RMS last sits within 20 dB of its loudest moment; the reverb tail after that is quiet enough to talk
  over). `voice_wait()` is how long a voice clip should still wait: until that end + GAP_S,
  capped at MAX_WAIT_S. audio.py applies it before every clip; `cue()` lets the Luma notice
  delay its 'notice' ping + voice together, so the ping lands right before Luma speaks.
- **Effects duck under the voice.** While a clip is speaking (`voice_started` ..
  `voice_ended`), `duck()` is DUCK (35%) and sfx.py scales every new effect by it; effects
  still sounding when the voice starts are turned down too (via the hook sfx.py registers).

Light UI sounds (taps, typing, tab sweeps, xp_fill, coin, notice), the analysis / camera
sounds (distort, scan_*, shutter, loading) and the low_* alerts are not in FOREGROUND: the voice
never waits for them. power_up is (Luma's welcome back on open / resume speaks after it).
Nothing here blocks or raises.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from typing import Any

# Audible length (s) of each sound (longest variant), as printed by tools/sfx/pack_sfx.py
# (pack sounds) and tools/sfx/make_sfx.py (level_up, skill_acquired, milestone, lumen_hum).
# Keyed by sound (sfx.SOUNDS); aliases / "notice" / combos resolve to these. Keep in sync.
AUDIBLE: dict[str, float] = {
    "tap": 0.04, "toggle_on": 0.04, "tab_open": 0.54, "tab_close": 0.32, "back": 0.12,
    "notify_01": 0.48, "notify_02": 0.40, "notify_03": 0.56, "notify_04": 0.46,
    "notify_05": 0.54, "notify_06": 0.42, "notify_07": 0.56, "notify_08": 0.42,
    "alert_soft": 0.36, "error_soft": 0.26, "coin": 0.22, "coin_many": 0.48, "xp_fill": 0.14,
    "timer_tick": 0.06, "timer_done": 1.30, "quest_done": 0.68, "quest_clear": 0.38,
    "granted": 0.50, "holo_flicker": 0.54, "unlock": 0.50, "upgrade": 0.84,
    "mission_complete": 1.38, "rank_up": 0.70, "purchase": 0.38, "objective_new": 0.66,
    "power_up": 1.06, "low_energy": 0.46, "low_health": 1.22, "loading": 0.98, "type": 0.02,
    "distort": 0.22, "scan_tick": 0.04, "scan_done": 0.30, "shutter": 0.06,
    "level_up": 1.48, "skill_acquired": 1.22, "milestone": 2.50, "lumen_hum": 2.08,
    "text_blip_01": 0.08, "download_complete": 0.95,
}
# Sounds Luma's voice must not talk over (it waits until their audible part ends). Combo
# layers count on their own: chain_complete holds the voice through mission_complete.
FOREGROUND = frozenset({"quest_done", "quest_clear", "level_up", "skill_acquired", "milestone",
                        "lumen_hum", "alert_soft", "timer_done", "mission_complete", "rank_up",
                        "purchase", "power_up", "download_complete"})
GAP_S = 0.15        # breath between the end of a reward sound and the voice
MAX_WAIT_S = 2.2    # never hold the voice longer than this (it must still match the screen)
DUCK = 0.35         # effects play at 35% while Luma speaks
DUCK_BIG = 0.6      # ... but a big moment (level / skill / milestone) only drops to 60%
BIG = frozenset({"level_up", "skill_acquired", "milestone"})
CUE_MAX_S = 3.0     # cue(): total wait cap when reward sounds keep arriving
SPEAK_MAX_S = 6.5   # safety: a 'speaking' flag never outlives this

log = logging.getLogger(__name__)

_fg_end = 0.0        # monotonic time the latest foreground effect stops being audible
_voice_until = 0.0   # monotonic time the current clip is assumed done (0 = silent)
_duck_hooks: list[Callable[[], None]] = []


def reset() -> None:
    """Forget all timing (tests / a fresh page)."""
    global _fg_end, _voice_until
    _fg_end = _voice_until = 0.0


def sfx_started(name: str, scale: float = 1.0, now: float | None = None) -> None:
    """An effect just started. Foreground effects push back the voice. A quiet play (scale
    under 0.3, e.g. ducked) does not hold the voice."""
    global _fg_end
    if name not in FOREGROUND or scale < 0.3:
        return
    t = time.monotonic() if now is None else now
    _fg_end = max(_fg_end, t + AUDIBLE.get(name, 0.5))


def voice_wait(now: float | None = None) -> float:
    """Seconds a voice clip should still wait so it starts GAP_S after the audible part of
    the current reward sound (0 when the coast is clear)."""
    t = time.monotonic() if now is None else now
    return max(0.0, min(MAX_WAIT_S, _fg_end + GAP_S - t))


def speaking(now: float | None = None) -> bool:
    t = time.monotonic() if now is None else now
    return _voice_until > t


def duck(name: str = "", now: float | None = None) -> float:
    """Volume factor for an effect starting now: DUCK (DUCK_BIG for a big moment) while Luma
    speaks, else 1."""
    if not speaking(now):
        return 1.0
    return DUCK_BIG if name in BIG else DUCK


def voice_started(max_s: float = SPEAK_MAX_S) -> None:
    """audio.py: a clip started playing. Ducks the effects that are still sounding."""
    global _voice_until
    _voice_until = time.monotonic() + max_s
    for hook in _duck_hooks:
        with contextlib.suppress(Exception):
            hook()


def voice_ended() -> None:
    global _voice_until
    _voice_until = 0.0


def on_voice_start(hook: Callable[[], None]) -> None:
    """Register a callback run when a clip starts (sfx.py turns sounding effects down)."""
    if hook not in _duck_hooks:
        _duck_hooks.append(hook)


def cue(page: Any, fn: Callable[[], Any]) -> float:
    """Run fn now, or once voice_wait() is clear, on the page's loop (for the 'notice' ping +
    voice pair, so both land after the reward chime). Re-checks after each wait, so a reward
    sound that starts meanwhile (a level-up seal) also gets its room; gives up waiting after
    CUE_MAX_S. Returns the first delay; never raises."""
    try:
        wait = voice_wait()
        if wait <= 0 or page is None:
            fn()
            return 0.0

        async def later() -> None:
            deadline = time.monotonic() + CUE_MAX_S
            w = wait
            while w > 0 and time.monotonic() < deadline:
                await asyncio.sleep(min(w, max(0.0, deadline - time.monotonic())))
                w = voice_wait()
            with contextlib.suppress(Exception):
                fn()

        page.run_task(later)
        return wait
    except Exception:
        log.debug("mixer cue failed", exc_info=True)
        return 0.0
