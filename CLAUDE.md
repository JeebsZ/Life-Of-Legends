# Life of Legends

Gamify-your-life app. **Python + Flet 1.x**, mobile-first (Android/iOS), also runs on PC.

## Layout
- `src/main.py` - entry point (`flet build` looks here).
- `src/lol/core/` - pure game logic (XP, quests, save/load). No Flet imports here, ever.
- `src/lol/ui/` - Flet screens. Draw and wire events only; call into `core`.
- `tests/` - pytest, covers `core`.
- `DataBank/Life Of Legends/` - Obsidian vault for design docs and build notes.

## Commands (run from repo root, venv at `.venv`)
- Run on PC: `.venv/Scripts/flet run src/main.py`
- Run on phone (live): `.venv/Scripts/flet run --android src/main.py` (scan QR with Flet app)
- Tests: `.venv/Scripts/python -m pytest -q`
- Lint: `.venv/Scripts/ruff check src tests`
- Android build: `.venv/Scripts/flet build apk` (needs Flutter SDK + Android SDK + JDK)

## Rules
- Mobile first: design for ~390px width, thumb reach, big tap targets (>=48px).
- Keep logic out of the UI so it is testable. New game rules land in `core` with a test.
- Save format is JSON; changing a dataclass field = handle old saves in `storage.load`.
- Done = a working, satisfying UX: tests/lint pass, runs in `flet run` at phone width, state survives restart, and every action has feedback (no dead taps, no jank). Plus a short note in the vault.

## Read first
`DataBank/Life Of Legends/Context/` — `vision.md`, `current-focus.md`, `work-preferences.md`.
Ask before: save-format changes, unrequested features/scope, installing packages/tools, git commits.
PERYA!/Roblox rules do not apply to this project.
