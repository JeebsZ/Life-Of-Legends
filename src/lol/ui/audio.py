"""Luma's voice clips: a tiny fire-and-forget player on top of flet_audio.

    audio.init(page, settings=lambda: app.game.profile)   # once, inside main
    audio.play("quest_done")              # random variant
    audio.play("quest_done", variant=1)   # the variant matching voice.LINES[kind][1]

Clips live in src/assets/voice/<kind>_<n>.wav (made by tools/voice/make_voice.py; Flet serves
src/assets as the assets dir, so the src is "/voice/<file>"; on Android the OGG copy
"/ogg/voice/<file>.ogg" from tools/sfx/encode_ogg.py). One shared player: clips never talk over
each other - a new clip waits for the current one, and is dropped if it would start
too late to match the screen. Nothing here blocks the UI or raises: on web without a user
gesture, with assets missing, or if flet_audio is unavailable, play() quietly does nothing.

Voice on/volume: `set_enabled` / `set_volume`, and - when `settings` is given - the profile's
`voice_on` / `voice_volume` (read defensively on every play, so a settings toggle applies at
once). The profile value wins over `set_volume` when present.

Sequencing (mixer.py): before a clip plays it waits mixer.voice_wait() - until the audible part
of a reward sound (quest chime, level-up, Luma hum ...) has ended + 0.15 s - and while it
speaks the mixer ducks sound effects to 35%.

Cut-off guards: the src is never swapped while a clip is still playing, and a 'completed' /
'stopped' event only ends a clip that was seen playing (stale events are ignored). Android
audio focus (an effect starting used to stop the voice) is fixed natively in
extensions/flet_lumen_notify (global audioplayers context without focus; see its README).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import random
import time
from collections.abc import Callable
from typing import Any

from lol.ui import mixer, sfx

# Variant counts per clip kind; keep in sync with tools/voice/lines.json (make_voice checks it).
CLIPS: dict[str, int] = {
    "analysis": 2,
    "bill_due": 2,
    "bill_paid": 3,
    "coin_cap": 2,
    "greeting": 2,
    "hello_again": 6,
    "level_up": 3,
    "path_level": 3,
    "proposal": 3,
    "quest_accepted": 3,
    "quest_done": 3,
    "reward_redeemed": 3,
    "skill_acquired": 3,
    "welcome_back": 3,
}
EXT = "wav"
DEFAULT_VOLUME = 0.8
STALE_S = 3.0      # drop a clip that waited longer than this for the previous one
MAX_CLIP_S = 6.0   # safety cap when waiting for a clip to finish
LOAD_S = 0.6       # wait for the new source to load before playing

log = logging.getLogger(__name__)

_page: Any = None
_player: Any = None
_settings: Callable[[], Any] | None = None
_enabled = True
_volume = DEFAULT_VOLUME
_lock: asyncio.Lock | None = None
_loaded = asyncio.Event()
_done = asyncio.Event()
_playing = asyncio.Event()
_src: str | None = None
_last: dict[str, int] = {}
_state = ""            # last state_change of the player ("playing", "completed", ...)
_clip_until = 0.0      # monotonic time the current clip is assumed over (safety cap)
_ogg = False           # Android: play the OGG copies


def src_for(kind: str, n: int, ogg: bool | None = None) -> str:
    """Asset path of variant n (1-based) of a clip kind: the OGG copy on Android (the APK only
    ships src/assets/ogg, see tools/sfx/encode_ogg.py), the WAV elsewhere."""
    if ogg if ogg is not None else _ogg:
        return f"/ogg/voice/{kind}_{n}.ogg"
    return f"/voice/{kind}_{n}.{EXT}"


def init(page: Any, settings: Callable[[], Any] | None = None) -> None:
    """Create the shared player (a flet_audio.Audio service) for this page. Call once in main.
    `settings()` returns the profile (or anything with voice_on / voice_volume)."""
    global _page, _player, _settings, _src, _state, _clip_until, _ogg
    _page, _settings, _player, _src = page, settings, None, None
    _ogg = sfx.is_android(page)
    _state, _clip_until = "", 0.0
    try:  # no audio extension / no page context: stay silent
        import flet_audio as fa

        # start with a real src: an Audio created with src=None ignores later src changes
        first = src_for("quest_done", 1)
        _player = fa.Audio(
            src=first,
            volume=_effective_volume(),
            release_mode=fa.ReleaseMode.STOP,
            on_loaded=lambda e: _loaded.set(),
            on_state_change=_on_state,
        )
        _src = first
        _init_cues(fa)
    except Exception:
        log.debug("voice player unavailable", exc_info=True)


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
    return bool(getattr(prof, "voice_on", True)) if prof is not None else True


def play(kind: str | None, variant: int | None = None) -> None:
    """Queue a clip of `kind` (variant index, 0-based, wraps; None = random). Sync, returns at
    once, never raises. Unknown kind, voice off, volume 0 or no player -> no-op."""
    try:
        n = CLIPS.get(kind or "", 0)
        if not n or _player is None or _page is None or not enabled():
            return
        if _effective_volume() <= 0:
            return
        if variant is None:
            choices = [i for i in range(n) if i != _last.get(kind)] or [0]
            i = random.choice(choices)
        else:
            i = int(variant) % n
        _last[kind] = i
        _page.run_task(_play, src_for(kind, i + 1), time.monotonic())
    except Exception:
        log.debug("voice play(%s) failed", kind, exc_info=True)


# ---------------------------------------------------------------------- internals
def _profile() -> Any:
    if _settings is None:
        return None
    with contextlib.suppress(Exception):
        return _settings()
    return None


def _effective_volume() -> float:
    prof = _profile()
    vol = getattr(prof, "voice_volume", None) if prof is not None else None
    if vol is None:
        return _volume
    try:
        return max(0.0, min(1.0, float(vol)))
    except (TypeError, ValueError):
        return _volume


def _on_state(e: Any) -> None:
    """Player state events. A 'completed'/'stopped' only ends the current clip once it was
    seen playing: a late event from the previous clip (or from a src swap) must not release
    the lock early, or the next clip would swap the src and cut this one off."""
    global _state
    state = getattr(getattr(e, "state", None), "value", getattr(e, "state", None))
    _state = str(state or "")
    if state == "playing":
        _playing.set()
    elif state == "disposed" or (state in ("completed", "stopped") and _playing.is_set()):
        _done.set()


async def _play(src: str, queued_at: float) -> None:
    global _lock, _src, _clip_until
    try:
        if _lock is None:
            _lock = asyncio.Lock()
        async with _lock:
            if time.monotonic() - queued_at > STALE_S or not enabled():
                return
            wait = mixer.voice_wait()  # let the reward chime finish first
            if wait > 0:
                await asyncio.sleep(wait)
            # a clip whose 'completed' never came (timeout) may still be speaking: changing
            # the src now would stop it mid-word, so give it until its safety cap
            rest = _clip_until - time.monotonic()
            if _state == "playing" and rest > 0:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(_done.wait(), rest)
            p = _player
            p.volume = _effective_volume()
            changed = src != _src
            if changed:
                _loaded.clear()
                p.src = _src = src
            p.update()
            if changed:
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(_loaded.wait(), LOAD_S)
            _done.clear()
            _playing.clear()
            _clip_until = time.monotonic() + MAX_CLIP_S
            await asyncio.wait_for(p.play(), 2.0)
            # let the clip finish before the next one; give up fast if it never started
            # (e.g. browser autoplay policy) so later clips are not held back
            await asyncio.wait_for(_playing.wait(), 1.0)
            mixer.voice_started(MAX_CLIP_S)
            await asyncio.wait_for(_done.wait(), MAX_CLIP_S)
    except TimeoutError:
        log.debug("voice %s: no playing/completed event in time", src)
    except Exception:
        log.debug("voice %s failed", src, exc_info=True)
    finally:
        mixer.voice_ended()


# ---------------------------------------------------------------------- stitched cues
# Run/walk coaching (core/run_cues.py): a cue is a list of tiny clips ("distance", "n5",
# "kilometres", ...) in src/assets/voice/cue_<key>.wav (OGG on Android). Two players
# ping-pong: while one speaks, the other already has the next clip loaded, so the words follow
# each other with only a short gap. A sequence holds the same lock as play(): cues and
# Luma's lines never talk over each other. Voice off / volume 0 -> silent.
SEQ_STALE_S = 8.0  # drop a cue that waited longer than this (it would be out of date)
SEQ_MAX_CLIPS = 40


class _CuePlayer:
    def __init__(self, player: Any) -> None:
        self.player = player
        self.src = ""
        self.loaded = asyncio.Event()
        self.playing = asyncio.Event()
        self.done = asyncio.Event()

    def on_state(self, e: Any) -> None:
        state = getattr(getattr(e, "state", None), "value", getattr(e, "state", None))
        if state == "playing":
            self.playing.set()
        elif state == "disposed" or (state in ("completed", "stopped")
                                     and self.playing.is_set()):
            self.done.set()


_cue_players: list[_CuePlayer] = []


def cue_src(key: str, ogg: bool | None = None) -> str:
    if ogg if ogg is not None else _ogg:
        return f"/ogg/voice/cue_{key}.ogg"
    return f"/voice/cue_{key}.{EXT}"


def _init_cues(fa: Any) -> None:
    _cue_players.clear()
    for _ in range(2):
        first = cue_src("distance")
        cp = _CuePlayer(None)
        cp.player = fa.Audio(src=first, volume=_effective_volume(),
                             release_mode=fa.ReleaseMode.STOP,
                             on_loaded=lambda e, c=cp: c.loaded.set(),
                             on_state_change=cp.on_state)
        cp.src = first
        _cue_players.append(cp)


def play_sequence(keys: list[str]) -> None:
    """Queue one stitched cue (clip keys in speaking order). Sync, never raises."""
    try:
        keys = [k for k in keys if k][:SEQ_MAX_CLIPS]
        if (not keys or len(_cue_players) < 2 or _page is None or not enabled()
                or _effective_volume() <= 0):
            return
        _page.run_task(_play_seq, keys, time.monotonic())
    except Exception:
        log.debug("voice play_sequence failed", exc_info=True)


async def _load(cp: _CuePlayer, key: str) -> None:
    src = cue_src(key)
    cp.player.volume = _effective_volume()
    if src != cp.src:
        cp.loaded.clear()
        cp.player.src = cp.src = src
        cp.player.update()
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(cp.loaded.wait(), LOAD_S)
    else:
        cp.player.update()


async def _play_seq(keys: list[str], queued_at: float) -> None:
    global _lock
    try:
        if _lock is None:
            _lock = asyncio.Lock()
        async with _lock:
            if time.monotonic() - queued_at > SEQ_STALE_S or not enabled():
                return
            wait = mixer.voice_wait()
            if wait > 0:
                await asyncio.sleep(wait)
            mixer.voice_started(MAX_CLIP_S * 2)
            await _load(_cue_players[0], keys[0])
            for i, key in enumerate(keys):
                if not enabled():
                    break
                cp = _cue_players[i % 2]
                cp.done.clear()
                cp.playing.clear()
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(cp.player.play(), 2.0)
                nxt = (asyncio.create_task(_load(_cue_players[(i + 1) % 2], keys[i + 1]))
                       if i + 1 < len(keys) else None)
                try:
                    await asyncio.wait_for(cp.playing.wait(), 1.0)
                    await asyncio.wait_for(cp.done.wait(), MAX_CLIP_S)
                except TimeoutError:
                    log.debug("cue clip %s: no playing/completed event in time", key)
                if nxt is not None:
                    with contextlib.suppress(Exception):
                        await nxt  # the next clip is loaded while this one speaks
    except Exception:
        log.debug("voice sequence failed", exc_info=True)
    finally:
        mixer.voice_ended()
