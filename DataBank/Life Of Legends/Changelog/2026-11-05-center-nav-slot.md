# Bottom nav: center "Middle button" slot

The bar is now Today · Quests · [center slot] · Rewards · More (custom `ArcaneNavBar` as `page.bottom_appbar`, replacing the Material NavigationBar).

- Center slot: a raised glowing orb (halo ring, slowly turning rune ring: one rotate animation per 28 s, still when Reduce effects is on). Empty: `+` / "Pin". Tap empty -> picker sheet of every More feature (built from the More registry, so new tiles like Study appear on their own; coming-soon tiles and modules switched off in Settings are hidden). Tap pinned -> opens that feature with the center highlighted; back returns to the previous tab. Hold -> unpin, toast with Undo.
- Feedback: pin = `unlock` + medium buzz + orb pop + toast; unpin = `back` + heavy buzz + orb shrink-pop; nav taps = select buzz.
- Bills left the bar: it is a More tile (Plan & focus) with an overdue count; More (or the orb, when Bills is pinned) shows a red dot. Today's bill advisory opens it.
- Settings -> Middle button: Change (same picker) / Unpin.
- Save: `Profile.center_pin` (additive, default None; junk/missing -> None in `storage._profile`). Rules: `core/pins.py`. Tests: `tests/test_pins.py`.
- Tab state: the highlight is set in `App._show`, so it always follows the visible screen (fixes Today staying lit while More shows). `app.more` is the visible stack (center or More); `app.showing(key)` replaces hard-coded tab indices.
