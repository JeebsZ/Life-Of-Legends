# Life of Legends — setup memo
**4 Nov 2026** · Python 3.15.2 · Flet 1.0.5 · mobile-first, runs on PC too

## Stack and why
**Flet** (Python → Flutter). One codebase → Android, iOS, Windows. `flet build apk` works from Windows; Kivy/Buildozer would need WSL.

## What's in place
| Piece | Where |
|---|---|
| Game logic (XP curve, level-up, quests, JSON save) | `src/lol/core/` — no UI imports |
| Starter screen (level, XP bar, add/complete quests) | `src/lol/ui/app.py` |
| Tests (6) + lint | `tests/`, ruff |
| Project rules for Claude | `CLAUDE.md` |
| Skills | `lol-python` (logic), `lol-mobile-ui` (Flet/mobile), `lol-qa` (triage + checklist) |
| Subagents | `qa-tester` (tests/edge cases, no edits to `src/`), `mobile-build` (APK/desktop packaging) |

**Verified:** 6/6 tests pass, ruff clean, `flet run src/main.py` opens the window on PC.
**Not verified:** on a phone; APK build (needs Android SDK + JDK — neither installed).

## Run it
`.venv/Scripts/flet run src/main.py` · phone: `flet run --android src/main.py` (Flet app + QR)

## Gotcha
PyYAML has no wheel for Python 3.15 → Flet CLI failed. Fixed by building it pure-Python. A fresh venv hits this again — use Python 3.13 or repeat `PYYAML_FORCE_LIBYAML=0 pip install --no-binary pyyaml pyyaml`.

## Disagreements — flagged, not resolved
- ~~**Subagents vs skills.**~~ **Decided 4 Nov:** keep both (3 skills + 2 narrow subagents).
- **Focus.** `current-focus.md` (22 Oct) puts PERYA! as the focus and treats scope creep as the main risk. Life of Legends isn't mentioned there. Also, `About-me.md` says the goal is to make Roblox the main thing.
- ~~**"Done" and file rules are Roblox-only.**~~ **Decided 4 Nov:** this project has its own rules in `Context/work-preferences.md`. Done = a working, satisfying UX.
