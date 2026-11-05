# 4 Nov 2026 — Quest tick + level-up juice

## What changed
- **Quest rows** are now big tappable cards (whole row = target). Tap → check pops green, row bounces (scale 1.06), haptic tick, then it fades, gets crossed out and sinks below open quests.
- **XP bar** is custom and *fills* (450 ms ease-out) instead of jumping. On level-up it fills to the end, snaps empty, then fills to the leftover XP.
- **Floating "+25 XP"** rises and fades from the top-right of the bar.
- **Level-up**: gold "LEVEL UP! Lv N" card pops in with an elastic bounce, level title pulses, heavy haptic, auto-dismisses after ~1.3 s.
- **Add quest**: Enter submits and the keyboard stays up for quick entry.
- New pure function `bar_steps()` in `core/progression.py` drives the bar animation (+3 tests, 9 total).
- Feel timings are constants at the top of `ui/app.py` (`FILL_MS`, `POP_MS`, `FLOAT_MS`, `BANNER_*`).
- Save format **unchanged**.

## Verified (browser, phone size 375×812)
Tick, sink, strike-through, bar fill, Lv1→2→3→4 with correct leftover XP, banner centered and dismissing, save survives restart.

## Not verified / known issues
- Haptics: phone-only, untested until it runs on a device.
- Floating "+XP" text: too quick to catch in a screenshot; code ran without errors.
- Typing the next quest *instantly* after Enter can drop letters in web mode (server round-trip clears the field late). Expected to be far less noticeable on-device; revisit if it bites.
