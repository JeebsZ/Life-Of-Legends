---
name: lol-python
description: Use when writing or editing Python game logic for Life of Legends (XP, levels, quests, stats, streaks, rewards, saving). Covers the core/ui split, save-format safety and the test-first rule.
---
# Life of Legends - core logic

1. Game rules live in `src/lol/core/`, as plain dataclasses + functions. No `flet` import in core.
2. Every new rule gets a pytest in `tests/` before it is wired into UI.
3. Balance numbers (XP base, growth, rewards) are module-level constants at the top of the file - tweak there, not inline.
4. Saves: `storage.save/load` (JSON, atomic write). Adding a field -> give it a default. Renaming/removing a field -> migrate in `load`, and add a test that loads an old-shape dict.
5. Never award XP twice: completion must be idempotent (see `Hero.complete`).
6. Verify: `.venv/Scripts/python -m pytest -q` and `.venv/Scripts/ruff check src tests`.
