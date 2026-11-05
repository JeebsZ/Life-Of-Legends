# 2026-11-04 - Lumen voice focus fix + Sci-Fi SFX pack

**Voice cut off on Android.** Every flet_audio player asked for AUDIOFOCUS_GAIN. So when a sound
effect started, the voice player lost focus and was stopped. Fix: the
`flet_lumen_notify` extension's `ensureInitialized()` now sets audioplayers' global context to
`mixWithOthers` (Android: no focus request) before any player exists. `audio.py` also
no longer swaps the src while a clip still plays, and it ignores stale completed/stopped events.
Not verified on the phone yet: rebuild the APK and complete a quest while Lumen speaks.
Side effect: app sounds now play over other apps' music instead of pausing it.

**SFX.** The UI sounds now come from the user's Sci-Fi UI SFX pack, picked by analysis to be
deep and not retro. Their loudness is matched to the synth sounds. `level_up`,
`skill_acquired`, `milestone` and `lumen_hum` stay synth. There are new event sounds for the
effects team: `distort`, `scan_tick`, `scan_done`, `shutter`, plus `toggle_on`/`toggle_off`
(`toggle` = on). Only the used files ship (about 1.29 MB). The pack must not be redistributed.
Mapping table and how to rebuild: `tools/sfx/README.md` (`pack_sfx.py`).

## Round 2 (2026-11-05)
Button/select sounds replaced by the user's picks: click_digital, holo open/close, back. The
heavy reward sounds stay and get pack sounds layered on top through `sfx.COMBOS`: chain_step,
chain_complete, skill_unlock, skill_rank_up and path_level_up. New event sounds: power_up,
objective_new, purchase, credits, low_energy, low_health, loading and Lumen typing.
Settings has a new notification sound picker (`profile.notify_sound`). It plays in the app and
through per-sound Android channels on the phone.
The APK now ships OGG only (`tools/sfx/encode_ogg.py`). Desktop runs keep the WAVs.
Mapping table: `tools/sfx/README.md`.
