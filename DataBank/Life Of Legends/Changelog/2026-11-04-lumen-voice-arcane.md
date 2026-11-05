# 4 Nov 2026: Lumen voice + Arcane theme

Spec: [[luma-voice-spec]]

## What changed
- **Arcane theme** (navy, cyan, violet coins) is the default for new saves and is free. Ember is free too. Old saves keep their active theme, and Arcane is added to their owned themes when they load (`storage._profile`). Under Arcane, panels get a faint cyan border and glow (`theme.glow()`) and labels are uppercase and letter-spaced (`theme.label()`). Other themes keep their flat look.
- **Lumen** says every line from `ui/voice.py` through `say(kind, **values)`. Each kind has 2-3 variants that rotate.
- **LumenNotice** (in `components.py`) is a top panel that slides down and types its text out. It plays a light haptic, auto-hides after about 2.2 s, queues lines and never blocks taps. It replaces the toast for quest cleared, skill acquired, coin cap, bill paid, reward redeemed, theme bought and board accept.
- **Level-up banner** under Arcane is a navy card with a glowing frame and a CONFIRMED eyebrow. Its subtitle comes from Lumen.
- **Quest Board**: the button reads "Ask Lumen" and cards show a "Proposal:" header and an "Analysis:" line. The Today bills nudge reads "Advisory: …". The weekly review is now the **Lumen Report**.
- **Me → Skills** lists Quest Board quests completed at least once (`Game.skills()`, derived from data, so the save format is unchanged).

## Verified (web, 375 px, scratch save)
Fresh save starts in Arcane. Seen working: notice typing out, queueing and hiding; Arcane level-up banner; Ask Lumen and accept; Advisory nudge; paying a bill; buying a theme; Ember and Arcane switching; Skills; Lumen Report; all 5 theme swatches fit.

## Known
- Haptics are untested off-device.
- On web, Rewards "Use" buttons keep the old theme's color until you change tabs (seen after an Arcane → Ember switch).
