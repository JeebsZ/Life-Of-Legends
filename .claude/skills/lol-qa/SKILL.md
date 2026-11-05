---
name: lol-qa
description: Use when testing, reviewing or verifying Life of Legends changes, or when something misbehaves (wrong XP, lost save, UI not updating). Gives the QA checklist and triage order.
---
# Life of Legends - QA

Triage order when something is wrong:
1. Reproduce in a pytest against `lol.core` (fast, no UI).
2. Save/load: inspect `hero.json` - under `src/.flet/storage/data/` with `flet run`, `~/.lifeoflegends/` with plain `python` - is state persisted? Did a field change shape?
3. UI: was `page.update()` / `refresh()` called after the state change?

Release checklist:
- [ ] `python -m pytest -q` green, `ruff check src tests` clean
- [ ] `flet run src/main.py` launches; add quest, complete it, restart app -> state kept
- [ ] Narrow window (~390px) has no overflow; tap targets usable
- [ ] Old save file still loads
- [ ] Feels good: every tap gives visible feedback, reward moments (quest done, level up) are animated, no lag or dead taps
Report failures with the exact command and output, never "seems fine".
