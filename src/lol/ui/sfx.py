"""UI sound effects: a small fire-and-forget player on top of flet_audio.

    sfx.init(page, settings=lambda: app.game.profile)   # once, inside main
    sfx.play("tab_open")
    sfx.play("quest_done", volume=0.5)                  # half of the user's SFX volume
    sfx.play("skill_unlock")                            # a COMBO: layered sounds

Files: src/assets/sfx/<stem>.wav (pack sounds: tools/sfx/pack_sfx.py from the Sci-Fi UI SFX
pack; level_up / skill_acquired / milestone / lumen_hum: tools/sfx/make_sfx.py), plus OGG
copies in src/assets/ogg/sfx (tools/sfx/encode_ogg.py). On Android the OGGs play (the APK ships
only those); everywhere else the WAVs. Flet serves src/assets, so the src is "/sfx/x.wav" or
"/ogg/sfx/x.ogg". A play name resolves to a file stem like this:

- VARIANTS: a random file of the set each time (never the same one twice in a row), e.g.
  "tap" -> tap_1..tap_5 (click_digital_01..05).
- ALIASES: another sound's file ("toggle" -> toggle_on, "sheet_close" -> back).
- SILENT: sounds muted app-wide (plain button taps and toggle/select clicks: "tap",
  "toggle"). Call sites keep calling them; play() just drops them, so taking a name out of
  SILENT brings the click back. Reward / progress / navigation sounds are never in it.
- "notice": the profile's `notify_sound` (Settings picker, notify_01..08).
- COMBOS: several sounds layered with offsets and volumes (the heavy moments keep their synth
  sound and get pack sounds on top, e.g. skill_unlock = skill_acquired + unlock + holo_flicker).

Players: the most frequent files get their own flet_audio.Audio (DEDICATED, never reload);
everything else shares a POOL (a slot already holding the file is reused, else the least
recently used idle slot swaps its src and waits briefly for on_loaded). Every Audio is created
with a real src (one created with src=None ignores later src changes).

Settings, read defensively on every play: the profile's `sfx_on`, `sfx_volume` (default 0.6;
wins over `set_volume`), `reduce_effects` (True plays 40% quieter) and `notify_sound`. Nothing
here blocks the UI or raises. Rate limits: a repeat of the same name within MIN_GAP_S is
dropped; "type" (Luma's typing) uses a longer, jittered gap so it never machine-guns.

Voice sequencing (mixer.py): every play (each combo layer at its offset) is reported to the
mixer, so Luma's voice waits for the audible part of a FOREGROUND sound; while Luma speaks,
new effects play at mixer.duck() and effects still sounding are turned down the same way.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from lol.ui import mixer

# Random-variant sounds: name -> number of files (<name>_1 .. <name>_n).
VARIANTS: dict[str, int] = {"tap": 5, "tab_open": 3, "tab_close": 3, "back": 4, "granted": 3,
                            "holo_flicker": 2, "type": 6}
NOTIFY: tuple[str, ...] = tuple(f"notify_{i:02d}" for i in range(1, 9))  # = models.NOTIFY_SOUNDS
DEFAULT_NOTIFY = "notify_08"
# Single-file sounds (file stem = name).
SINGLE: tuple[str, ...] = (
    "toggle_on", "quest_done", "quest_clear", "coin", "coin_many", "xp_fill", "level_up",
    "skill_acquired", "milestone", "alert_soft", "error_soft", "timer_tick", "timer_done",
    "lumen_hum", "distort", "scan_tick", "scan_done", "shutter", "unlock", "upgrade",
    "mission_complete", "rank_up", "purchase", "objective_new", "power_up", "low_energy",
    "low_health", "loading", *NOTIFY,
)
# Muted app-wide (resolved sound names): plain button taps and toggle/select clicks. Feedback
# for those comes from haptics + visuals; completion/reward sounds stay. Remove a name to
# bring its click back (the files and call sites are kept).
SILENT: frozenset[str] = frozenset({"tap", "toggle_on"})
# Names that play another sound (no files of their own).
ALIASES: dict[str, str] = {"toggle": "toggle_on", "toggle_off": "toggle_on",
                           "sheet_open": "tab_open", "sheet_close": "back"}
# Layered moments: name -> ((sound, offset s, volume scale), ...). The first layer is the
# heavy one we keep; pack sounds go on top of it, never instead of it.
COMBOS: dict[str, tuple[tuple[str, float, float], ...]] = {
    # side-quest chain step: the quest_clear stinger + an access-granted chime
    "chain_step": (("quest_clear", 0.0, 1.0), ("granted", 0.06, 0.7)),
    # the last step of a chain (skill unlocked): quest_done + mission_complete
    "chain_complete": (("quest_done", 0.0, 1.0), ("mission_complete", 0.1, 0.6)),
    # skill emblem: new skill / rank up, with a holo flicker as the emblem appears
    "skill_unlock": (("skill_acquired", 0.0, 1.0), ("unlock", 0.0, 0.55),
                     ("holo_flicker", 0.12, 0.6)),
    "skill_rank_up": (("skill_acquired", 0.0, 1.0), ("upgrade", 0.0, 0.55),
                      ("holo_flicker", 0.12, 0.6)),
    # Path level-up banner: level_up with rank_up under it
    "path_level_up": (("level_up", 0.0, 1.0), ("rank_up", 0.0, 0.5)),
}
# Own players (no src swaps): every file of these. Keep short: each Audio is a native player.
DEDICATED: tuple[str, ...] = ("tap", "type", "toggle_on", "quest_clear", "quest_done")
POOL_SIZE = 6
# File lengths (s, longest variant) so the pool knows when a slot is free again; the audible
# part (voice sequencing) is mixer.AUDIBLE. Printed by tools/sfx/pack_sfx.py / make_sfx.py.
LENGTHS: dict[str, float] = {
    "tap": 0.30, "toggle_on": 0.27, "tab_open": 0.89, "tab_close": 0.70, "back": 0.52,
    "notify_01": 0.61, "notify_02": 0.64, "notify_03": 0.79, "notify_04": 0.72,
    "notify_05": 0.70, "notify_06": 0.62, "notify_07": 0.78, "notify_08": 0.73,
    "alert_soft": 0.82, "error_soft": 0.71, "coin": 0.51, "coin_many": 0.79, "xp_fill": 0.57,
    "timer_tick": 0.40, "timer_done": 2.10, "quest_done": 1.06, "quest_clear": 0.68,
    "granted": 0.86, "holo_flicker": 0.88, "unlock": 0.70, "upgrade": 1.03,
    "mission_complete": 1.86, "rank_up": 1.52, "purchase": 0.54, "objective_new": 0.83,
    "power_up": 1.26, "low_energy": 0.88, "low_health": 1.67, "loading": 1.33, "type": 0.24,
    "distort": 0.66, "scan_tick": 0.32, "scan_done": 0.65, "shutter": 0.41,
    "level_up": 2.03, "skill_acquired": 2.27, "milestone": 3.5, "lumen_hum": 2.6,
}
SOUNDS: tuple[str, ...] = (*VARIANTS, *SINGLE)        # names with files
NAMES: tuple[str, ...] = (*SOUNDS, *ALIASES, "notice", *COMBOS)  # everything play() accepts
DEFAULT_VOLUME = 0.6
REDUCED = 0.6        # reduce_effects multiplier (40% quieter)
LOAD_S = 0.5         # wait this long for a swapped src to load
MIN_GAP_S = 0.035    # ignore a repeat of the same sound faster than this (stacked taps)
TYPE_GAP_S = (0.085, 0.15)  # Luma typing: random gap between ticks (light, never a buzz)

log = logging.getLogger(__name__)


@dataclass
class _Slot:
    player: Any
    src: str
    loaded: asyncio.Event = field(default_factory=asyncio.Event)
    busy_until: float = 0.0
    used: float = 0.0
    name: str = ""
    vol: float = 0.0
    lock: asyncio.Lock | None = None


_page: Any = None
_settings: Callable[[], Any] | None = None
_enabled = True
_volume = DEFAULT_VOLUME
_ogg = False
_dedicated: dict[str, _Slot] = {}
_pool: list[_Slot] = []
_last_play: dict[str, float] = {}
_last_variant: dict[str, int] = {}
_type_gap = TYPE_GAP_S[0]


def files_of(sound: str) -> list[str]:
    """File stems of a sound with files (variants: all of them)."""
    n = VARIANTS.get(sound)
    return [f"{sound}_{i}" for i in range(1, n + 1)] if n else [sound]


def resolve(name: str) -> str | None:
    """Play name -> sound with files (alias / notice resolved), or None if unknown."""
    if name == "notice":
        prof = _profile()
        pick = getattr(prof, "notify_sound", None) if prof is not None else None
        return pick if pick in NOTIFY else DEFAULT_NOTIFY
    name = ALIASES.get(name, name)
    return name if name in LENGTHS else None


def pick_file(sound: str) -> str:
    """A file stem for one play: variants pick at random, never the same twice in a row."""
    n = VARIANTS.get(sound)
    if not n:
        return sound
    choices = [i for i in range(1, n + 1) if i != _last_variant.get(sound)] or [1]
    i = random.choice(choices)
    _last_variant[sound] = i
    return f"{sound}_{i}"


def src_of(stem: str, ogg: bool | None = None) -> str:
    """Asset path of a file stem (OGG on Android, WAV elsewhere)."""
    if ogg if ogg is not None else _ogg:
        return f"/ogg/sfx/{stem}.ogg"
    return f"/sfx/{stem}.wav"


def src_for(name: str) -> str:
    """Asset path of a play name (a random variant / the alias target / the picked notice)."""
    sound = resolve(name) or name
    return src_of(pick_file(sound))


def is_android(page: Any) -> bool:
    plat = getattr(page, "platform", None)
    return str(getattr(plat, "value", plat) or "").lower() == "android"


def init(page: Any, settings: Callable[[], Any] | None = None) -> None:
    """Create the players (flet_audio.Audio services) for this page. Call once in main.
    `settings()` returns the profile (or anything with sfx_on / sfx_volume / reduce_effects /
    notify_sound)."""
    global _page, _settings, _ogg
    _page, _settings = page, settings
    _ogg = is_android(page)
    _dedicated.clear()
    _pool.clear()
    _last_play.clear()
    try:  # no audio extension / no page context: stay silent
        import flet_audio as fa
    except Exception:
        log.debug("sfx player unavailable", exc_info=True)
        return
    for sound in DEDICATED:
        if sound in SILENT:
            continue  # never plays: no native player for it
        for stem in files_of(sound):
            slot = _make(fa, src_of(stem))
            if slot is not None:
                _dedicated[stem] = slot
    pooled = [s for s in SOUNDS if s not in DEDICATED and s not in SILENT]
    for i in range(POOL_SIZE):
        slot = _make(fa, src_of(files_of(pooled[i % len(pooled)])[0]))
        if slot is not None:
            _pool.append(slot)
    mixer.on_voice_start(_duck_sounding)


def set_enabled(on: bool) -> None:
    global _enabled
    _enabled = bool(on)


def set_volume(volume: float) -> None:
    global _volume
    with contextlib.suppress(TypeError, ValueError):
        _volume = max(0.0, min(1.0, float(volume)))


def enabled() -> bool:
    if not _enabled:
        return False
    prof = _profile()
    return bool(getattr(prof, "sfx_on", True)) if prof is not None else True


def effective_volume(volume: float | None = None) -> float:
    """Final 0..1 volume: setting x reduce_effects x the optional per-call scale."""
    prof = _profile()
    base = _volume
    if prof is not None:
        v = getattr(prof, "sfx_volume", None)
        if v is not None:
            with contextlib.suppress(TypeError, ValueError):
                base = float(v)
        if getattr(prof, "reduce_effects", False):
            base *= REDUCED
    if volume is not None:
        with contextlib.suppress(TypeError, ValueError):
            base *= float(volume)
    return max(0.0, min(1.0, base))


def silent(name: str | None) -> bool:
    """True for a play name muted app-wide (SILENT, alias resolved)."""
    return bool(name) and ALIASES.get(name, name) in SILENT


def play(name: str | None, volume: float | None = None) -> None:
    """Play a sound or combo (`volume`: optional 0..1 scale on top of the user's SFX volume).
    Sync, returns at once, never raises. Unknown name, SILENT name, SFX off, volume 0 or no
    player -> no-op."""
    try:
        if not name or silent(name) or _page is None or not enabled():
            return
        if not _dedicated and not _pool:
            return
        now = time.monotonic()
        if not _gap_ok(name, now):
            return
        scale = 1.0 if volume is None else float(volume)
        for sound, offset, vol in COMBOS.get(name, ((name, 0.0, 1.0),)):
            _start(sound, scale * vol, offset, now)
    except Exception:
        log.debug("sfx play(%s) failed", name, exc_info=True)


# ---------------------------------------------------------------------- internals
def _gap_ok(name: str, now: float) -> bool:
    """Rate limit per play name (typing gets a longer, jittered gap)."""
    global _type_gap
    gap = _type_gap if name == "type" else MIN_GAP_S
    if now - _last_play.get(name, -1.0) < gap:
        return False
    _last_play[name] = now
    if name == "type":
        _type_gap = random.uniform(*TYPE_GAP_S)
    return True


def _start(name: str, scale: float, offset: float, now: float) -> None:
    sound = resolve(name)
    if sound is None or sound in SILENT:
        return
    vol = effective_volume(scale) * mixer.duck(sound)
    if vol <= 0:
        return
    mixer.sfx_started(sound, scale, now + offset)
    _page.run_task(_play, sound, vol, offset)


def _make(fa: Any, src: str) -> _Slot | None:
    try:
        slot = _Slot(player=None, src=src)
        slot.player = fa.Audio(
            src=src,
            volume=effective_volume(),
            release_mode=fa.ReleaseMode.STOP,
            on_loaded=lambda e, s=slot: s.loaded.set(),
        )
        return slot
    except Exception:
        log.debug("sfx Audio(%s) failed", src, exc_info=True)
        return None


def _profile() -> Any:
    if _settings is None:
        return None
    with contextlib.suppress(Exception):
        return _settings()
    return None


def _pick(src: str, now: float) -> _Slot | None:
    """Pool slot for src: one already holding it (idle preferred), else the LRU idle slot,
    else the slot that frees up soonest."""
    if not _pool:
        return None
    same = [s for s in _pool if s.src == src]
    idle_same = [s for s in same if s.busy_until <= now]
    if idle_same:
        return idle_same[0]
    idle = [s for s in _pool if s.busy_until <= now]
    if idle:
        return min(idle, key=lambda s: s.used)
    if same:  # everything busy: restart the same sound rather than cut a different one
        return same[0]
    return min(_pool, key=lambda s: s.busy_until)


def _duck_sounding() -> None:
    """mixer hook (a voice clip just started): turn down effects that are still sounding."""
    now = time.monotonic()
    for slot in (*_dedicated.values(), *_pool):
        if slot.busy_until <= now or not slot.vol:
            continue
        with contextlib.suppress(Exception):
            slot.player.volume = slot.vol * mixer.duck(slot.name, now)
            slot.player.update()


async def _play(sound: str, vol: float, delay: float = 0.0) -> None:
    try:
        if delay > 0:
            await asyncio.sleep(delay)
        stem = pick_file(sound)
        src = src_of(stem)
        now = time.monotonic()
        slot = _dedicated.get(stem) or _pick(src, now)
        if slot is None:
            return
        if slot.lock is None:
            slot.lock = asyncio.Lock()
        slot.busy_until = now + LENGTHS.get(sound, 1.0)
        slot.used = now
        slot.name, slot.vol = sound, vol
        async with slot.lock:
            p = slot.player
            p.volume = vol
            changed = slot.src != src
            if changed:
                slot.loaded.clear()
                p.src = slot.src = src
            p.update()
            if changed:
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(slot.loaded.wait(), LOAD_S)
            await asyncio.wait_for(p.play(), 2.0)
    except TimeoutError:
        log.debug("sfx %s: play timed out", sound)
    except Exception:
        log.debug("sfx %s failed", sound, exc_info=True)
