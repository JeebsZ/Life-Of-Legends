---
name: lol-mobile-ui
description: Use when building or restyling Life of Legends screens, HUD, level-up feedback or navigation in Flet. Covers mobile-first sizing, Flet 1.x API gotchas and the juice rule.
---
# Life of Legends - mobile UI (Flet 1.x)

- Target a phone first: ~390x844, wrap screens in `ft.SafeArea`, tap targets >= 48px, primary actions in bottom thumb zone (`NavigationBar`, FAB).
- Flet 1.x API: start with `ft.run(main)`; dialogs/snackbars via `page.show_dialog(...)` (not `page.open`); icons `ft.Icons.X`, colors `ft.Colors.X`. If unsure, check with `inspect.signature` in the venv before writing.
- UI only draws and wires events. Any rule or number -> `lol.core`.
- Juice: every reward moment (quest done, level up) needs feedback - animate (`animate_*`, `AnimatedSwitcher`), not just text.
- Check on PC with `flet run src/main.py`, resize window narrow; then on phone with `flet run --android`.
