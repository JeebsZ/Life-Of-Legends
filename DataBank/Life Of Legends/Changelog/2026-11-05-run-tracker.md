# 2026-11-05 - Run & walk tracker (GPS, ladder, voice cues)

More -> Track -> **Run** (module "run", Settings -> Tracking).

- **Tracking** (`core/run.py`, pure): drops fixes worse than 25 m, drops teleports (>12 m/s run, >6 m/s walk; 3 agreeing jumps = GPS re-lock, new segment), light EMA smoothing, a 5 m jitter gate, auto-pause (slower than 0.5 m/s adds no moving time). Moving vs elapsed time, current (30 s) and average pace, 1 km splits, best effort per distance, elevation gain with 3 m hysteresis, Douglas-Peucker route (~4 m) for the save.
- **Energy**: MET from the 2011 Compendium (walking 17152-17231, running 12029-12135) x kg x moving hours, per ~60 s chunk. Net kcal = gross minus BMR/24 h over the same time (Mifflin-St Jeor; 1 MET if the body profile is incomplete). No weight -> 70 kg, labelled.
- **Steps (estimated)**: distance / step length; walk 0.415 x height, run 0.55 x height at 10 km/h, +0.12 per m/s, clamped 0.45-0.95.
- **Ladder** (`core/runlog.py`): 1K, 3K, 5K, 10K, 15K, Half, 30K, Marathon; one ladder, a separate track per mode. A first clear pays like a hard quest (+70 XP, +35 coins) once per run, plus a pace badge. The next tier opens the next day.
- **Safety**: the next tier is suggested only when it fits +10% weekly volume (base = max(last week, 4-week average); 6 km run / 10 km walk room with no history), not on the unlock day, not after a session today, not for an under-18 or a "low" energy check-in, and not with a rest nudge (3 run days in a row, or a big day yesterday). Heat/hydration and "stop if pain/dizziness" notes always show. Nothing nags.
- **Save**: additive in schema 5. `runs`, `run_settings` (mode, keep awake, voice cues, cue interval), modules["run"]. Each run is also a cardio WorkoutSession, so Insights counts it. CSV adds runs.csv.
- **Voice cues** (`core/run_cues.py`): stitched clips (`cue_*.wav/.ogg`, made by `tools/voice/make_cues.py` from `cues.json`; name-free). Every 1 km / 0.5 km / 5 min: distance, time, pace, steps. Also halfway, goal reached, tier cleared, water every 20 min (run) or 30 min (walk), and an "ease off" nudge if a km is 15% faster than the earlier average early in a goal of 5K or more. `audio.play_sequence` uses two ping-pong players under the voice lock. 89 clips: 2.1 MB WAV, 0.77 MB OGG.
- **Map**: flet_map with OSM tiles, "© OpenStreetMap contributors" always visible, UA "LifeOfLegends/0.1 (com.jarvin.lifeoflegends)". A public release needs a keyed tile provider.
- **Debug**: `LOL_FAKE_GPS=1` (optional `LOL_FAKE_GPS_SPEED=12`) replays a loop around Rizal Park.
- **Limits**: tracking only works while the app is open on screen. No background or locked-screen tracking.
- Tests: tests/test_run.py (41). Total 369 pass; ruff is clean.
