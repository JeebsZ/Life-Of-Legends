"""Luma's voice player (src/lol/ui/audio.py) cut-off guards and the SFX name table, with
fake flet_audio players (no Flet session needed)."""

import asyncio
import itertools
import time
from pathlib import Path
from types import SimpleNamespace

from lol.core import models
from lol.ui import audio, mixer, sfx

ASSETS = Path(__file__).resolve().parents[1] / "src" / "assets"


class FakePlayer:
    def __init__(self) -> None:
        self.src = audio.src_for("quest_done", 1)
        self.volume = 1.0
        self.log: list[str] = []

    def update(self) -> None:
        self.log.append(f"src={self.src}")
        audio._loaded.set()  # on_loaded

    async def play(self) -> None:
        self.log.append(f"play {self.src}")
        audio._on_state(SimpleNamespace(state="playing"))


def _setup() -> FakePlayer:
    p = FakePlayer()
    audio._player, audio._page, audio._settings = p, object(), None
    audio._src, audio._lock, audio._state, audio._clip_until = p.src, None, "", 0.0
    # fresh events: asyncio.Event binds to the loop it is first awaited on (one per test)
    audio._done, audio._playing, audio._loaded = asyncio.Event(), asyncio.Event(), asyncio.Event()
    mixer.reset()
    return p


def _state(s: str) -> None:
    audio._on_state(SimpleNamespace(state=s))


def test_stale_completed_before_playing_is_ignored():
    _setup()
    _state("completed")  # late event from a previous clip / src swap
    assert not audio._done.is_set()
    _state("playing")
    _state("completed")
    assert audio._done.is_set()


def test_clip_finishes_on_completed():
    p = _setup()

    async def run() -> None:
        task = asyncio.create_task(audio._play(audio.src_for("greeting", 1), time.monotonic()))
        await asyncio.sleep(0.05)
        assert not task.done()  # still speaking: holds the lock
        _state("completed")
        await asyncio.wait_for(task, 1.0)

    asyncio.run(run())
    assert p.log[-1] == f"play {audio.src_for('greeting', 1)}"


def test_src_is_not_swapped_while_previous_clip_still_plays():
    p = _setup()
    audio._state = "playing"  # a clip whose completed event never arrived in time
    audio._playing.set()
    audio._clip_until = time.monotonic() + 0.5
    new = audio.src_for("level_up", 1)

    async def run() -> None:
        task = asyncio.create_task(audio._play(new, time.monotonic()))
        await asyncio.sleep(0.1)
        assert p.src != new  # waiting, not cutting the old clip off
        _state("completed")
        await asyncio.sleep(0.05)
        assert p.src == new
        _state("completed")
        await asyncio.wait_for(task, 1.0)

    asyncio.run(run())


def test_every_sound_has_wav_ogg_length_and_audible_entry():
    for sound in sfx.SOUNDS:
        for stem in sfx.files_of(sound):
            assert (ASSETS / sfx.src_of(stem, ogg=False).lstrip("/")).is_file(), stem
            assert (ASSETS / sfx.src_of(stem, ogg=True).lstrip("/")).is_file(), stem
        assert sound in sfx.LENGTHS and sound in mixer.AUDIBLE, sound
        assert mixer.AUDIBLE[sound] <= sfx.LENGTHS[sound] + 0.01, sound
    assert mixer.FOREGROUND <= set(sfx.SOUNDS)
    assert not {"distort", "scan_done", "scan_tick", "type"} & mixer.FOREGROUND
    assert "power_up" in mixer.FOREGROUND  # Luma's welcome back speaks after it
    for target in sfx.ALIASES.values():
        assert target in sfx.SOUNDS
    for parts in sfx.COMBOS.values():
        assert all(sfx.resolve(n) for n, _, _ in parts)
    assert set(sfx.NOTIFY) == set(models.NOTIFY_SOUNDS)
    assert sfx.DEFAULT_NOTIFY == models.DEFAULT_NOTIFY_SOUND


def test_voice_clips_have_ogg_copies():
    for kind, n in audio.CLIPS.items():
        for i in range(1, n + 1):
            assert (ASSETS / audio.src_for(kind, i, ogg=True).lstrip("/")).is_file(), kind


def test_variants_never_repeat_and_notice_follows_the_profile():
    picks = [sfx.pick_file("tap") for _ in range(50)]
    assert all(a != b for a, b in itertools.pairwise(picks))
    assert {p for p in picks} <= {f"tap_{i}" for i in range(1, 6)}
    prof = SimpleNamespace(notify_sound="notify_03")
    sfx._settings = lambda: prof
    assert sfx.resolve("notice") == "notify_03"
    prof.notify_sound = "bogus"
    assert sfx.resolve("notice") == sfx.DEFAULT_NOTIFY
    assert sfx.resolve("sheet_close") == "back" and sfx.resolve("nope") is None
    sfx._settings = None


class FakePage:
    platform = "android"

    def __init__(self) -> None:
        self.tasks: list[tuple] = []

    def run_task(self, fn, *args):
        self.tasks.append(args)


def test_combo_layers_and_typing_rate_limit():
    page = FakePage()
    sfx._page, sfx._settings, sfx._ogg = page, None, sfx.is_android(page)
    sfx._dedicated["x"] = object()  # pretend players exist
    sfx._last_play.clear()
    mixer.reset()
    try:
        sfx.play("skill_unlock")
        assert [t[0] for t in page.tasks] == ["skill_acquired", "unlock", "holo_flicker"]
        assert page.tasks[2][2] > 0  # the flicker is offset
        assert mixer.voice_wait() > 1.0  # skill_acquired holds the voice
        page.tasks.clear()
        for _ in range(20):  # a burst of typed characters
            sfx.play("type")
        assert len(page.tasks) == 1
        assert sfx.src_of("tap_1") == "/ogg/sfx/tap_1.ogg"
    finally:
        sfx._dedicated.clear()
        sfx._page, sfx._ogg = None, False
        mixer.reset()


def test_button_taps_and_toggles_are_silent_but_rewards_are_not():
    assert sfx.silent("tap") and sfx.silent("toggle") and sfx.silent("toggle_off")
    for name in ("quest_done", "quest_clear", "chain_step", "coin", "xp_fill", "level_up",
                 "purchase", "objective_new", "notice", "type", "loading", "power_up",
                 "tab_open", "tab_close", "back", "sheet_close", "low_energy"):
        assert not sfx.silent(name), name
    assert all(s not in sfx.SILENT for parts in sfx.COMBOS.values() for s, _, _ in parts)
    page = FakePage()
    sfx._page, sfx._settings, sfx._pool = page, None, [object()]
    sfx._last_play.clear()
    mixer.reset()
    try:
        sfx.play("tap")
        sfx.play("toggle")
        assert page.tasks == []  # nothing scheduled
        sfx.play("quest_done")
        assert [t[0] for t in page.tasks] == ["quest_done"]  # rewards still play
    finally:
        sfx._page, sfx._pool = None, []
        mixer.reset()
