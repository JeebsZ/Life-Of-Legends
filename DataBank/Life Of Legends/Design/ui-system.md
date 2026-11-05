# UI system — Life of Legends

Code: `src/lol/ui/theme.py` (tokens, themes), `src/lol/ui/components.py` (controls), `src/lol/ui/gallery.py` (every component in every state, live theme switch).
Gallery: `.venv/Scripts/flet run src/lol/ui/gallery.py`

## Principles
1. **Juice over size.** Every reward moment moves: pop, fill, float, banner, haptic. Feel is the product.
2. **No dead taps.** The tap answers at once (pop + haptic) *before* any logic runs. Taps on done or locked things get a soft nudge.
3. **Never guilt.** No "failed", no red for missed habits. A streak that broke shows nothing, and the copy says "resume". Red is only for money that is overdue.
4. **Thumb first.** 375–390 px wide, tap targets ≥ 48 px, primary action at the bottom or right edge.
5. **UI draws, core decides.** Components take plain values and callbacks. They never import `lol.core`. A callback that returns `False` means "rejected", and the component reverts its optimistic animation.

## Tokens (`theme.py`)
| Group | Values |
|---|---|
| `Space` | XS 4 · SM 8 · MD 12 · LG 16 · XL 24 · XXL 32 · GUTTER 16 |
| `Radius` | SM 8 · MD 14 (cards) · LG 20 (sheets/banners) · PILL |
| `Type` | CAPTION 12 · LABEL 13 · BODY 15 · TITLE 17 · HEADLINE 22 · DISPLAY 28 · HERO 34 |
| `Size` | TAP 48 · BAR 14 · BAR_MINI 6 · STRIPE 4 |
| `Motion` | FILL 450 · POP 140 (scale 1.06) · FLOAT 700 · BANNER 450 + hold 1.3 s · FADE 250 · DONE_FADE 400 · COUNT 600 · SWAP 220 |
| Curves | EASE_OUT (default) · EASE_OUT_CUBIC (fills, slides) · EASE_OUT_BACK (pops, chips) · ELASTIC_OUT (banners only) |

**Color roles (`C.*`)** map to Material ColorScheme slots, so they recolor live:
BG→surface · SURFACE→surface_container · SURFACE_HI→surface_container_highest · PRIMARY · ON_PRIMARY · ACCENT (coins)→tertiary · SUCCESS→secondary · DANGER→error · TEXT→on_surface · TEXT_DIM→on_surface_variant · OUTLINE→outline_variant. Use `C.a(color, opacity)` for tints.

**Themes**: `arcane` (default, glowing cyan mind-space), `rose` (Rose Arcana, glowing plum/rose mind-space, **free for everyone**), `ember` (free), `ocean`, `forest`, `royal`. All are dark. Each `Palette` has bg, surface, surface_hi, primary, on_primary, accent, success, danger, text, text_dim, plus `paths{chef, warrior, scholar, artisan, ranger, steward, monk}` and `glow`. `tests/test_themes.py` checks every theme: all tokens, WCAG ≥4.5:1 for text/dim text on panels and on_primary on primary, Path colours ≥20 ΔE apart. Effect colours: QuestCleared/burst/distort follow `primary`; Luma's own effects stay cyan (Luma's signature), reward ceremonies (seal, reveal) stay gold, and the impact fringes stay cyan/magenta (chromatic aberration).
Path icons: chef RESTAURANT · warrior FITNESS_CENTER · scholar MENU_BOOK · artisan PALETTE · ranger HIKING · steward ACCOUNT_BALANCE_WALLET.

**Live switching**: `theme.apply_theme(page, id)`. It sets page.theme and dark_theme, calls `restyle()` on every registered Path-colored component (held in a weakref set), runs `on_theme_change(callback=...)` callbacks, then does one `page.update()`. No restart needed.

## Components (`components.py`)
| Component | Purpose · states |
|---|---|
| `XpBar` | Overall or Path XP. Measures its own width. `play(bar_steps)`: each 1.0 fills, snaps to empty, pops "Lv N" and fires `on_rollover(level)`. Gains queue. `set()` jumps to a value. |
| `QuestCard` | Path stripe and avatar, title, note, XP/coin chips, flame streak, daily icon. States: open · completing (pop, check, green flash) · done (strikethrough, dim, 0.6 opacity) · rejected (reverts). |
| `FloatingGain` | `+25 XP` / `+5 coins` rises and fades. Place it in a Stack. |
| `LevelUpBanner` | Overlay with a scrim and an elastic pop plus slight rotation; dismisses itself. Path variant takes a path color, icon and title. Calls queue. |
| `CoinCounter` | Coin pill. `count_to(n)` ticks up, then the coin pops. |
| `SectionHeader` | Title, count chip, optional action or trailing text. |
| `EmptyState` | Icon bubble, title, kind message, optional CTA. |
| `BillRow` | Status chip: overdue (red, outlined) · due_soon (gold) · upcoming (dim) · paid (green, dimmed). Amount in ₱. Pay button pops, flips the row to Paid, then calls `on_pay`. |
| `RewardTile` | Personal or theme reward. States: affordable (Redeem/Buy) · locked (lock, progress toward cost, "N more to go") · theme owned (Use) · equipped. A redeem flashes "Enjoy!". |
| `PathBadge` / `PathProgress` | Path pill · Path row with a mini bar. `play(steps)` pops the level and calls `on_level_up`. |
| `ArcaneNavBar` | `page.bottom_appbar`: Today · Quests · **center slot** · Rewards · More. Plain tabs = icon in a primary pill + label. `select(i)` moves the highlight (center lights the slot), `set_badge(i, True/"3"/None)` = red dot / count / clear. `build_bottom_nav` is the gallery shortcut. |
| `ArcaneSlot` | The raised center button (64 px orb, rises 28 px above the bar): glowing halo ring, 16-tick rune ring turned by ONE `rotate` animation per 28 s (`spin(reduced)`; still while Reduce effects), core disc. Empty: `+` / "Pin". Pinned: feature icon + color + short label. Active: brighter glow, bold label in the feature color. `pulse()` pops it. |
| `QuestSuggestionCard` | Quest Board card: Path badge, difficulty stars, title, note, chips; Skip · 🎲 Reroll (dice spins, card slides) · Accept (flashes "Added!"). |
| `ThemeSwatch` | Theme picker dot: split color, selection ring, lock and price if not owned. |
| helpers | `chip`, `xp_chip`, `coin_chip`, `streak_badge`, `path_avatar`, `peso`, `pop`, `nudge`, `buzz`, `use_haptics`, `refresh` |

## Motion rules
- Pop = scale 1.06 for 140 ms with an EASE_OUT_BACK curve. It is the universal "registered" beat. A press-in (0.97) is for no-op taps.
- Fill bars always go *up*. A level crossing snaps to empty without animating, then fills again.
- Elastic is reserved for level-ups. Nothing else bounces that hard.
- Haptics are fire-and-forget: medium for complete or pay, heavy for a level-up, select for no-ops and nav.
- Save before animating: the screen saves state in the callback, so an interrupted animation never loses XP.
- Stagger: floaters and the coin count run in parallel (`page.run_task`). The XP bar awaits, and the banner runs in the background.

## Screens (wireframes)

**Today**
```
Jarvin                    (🪙 135)
Lv 4 [██████████░░░░░░]  +25 XP↑
     60 / 195 XP
Today's quests (5)            Add
▌🍴 Cook adobo   +25⚡ +5🪙      ○
▌🏋 Stretch  🔥6 ↻ +15⚡         ○
▌📖 Read 10 pages (done, dim)    ✓
[ empty: "All quests done! Rest counts too." → Give me a quest ]
[Today][Quests]( ◎ Pin )[Rewards][More•]
```
**Quests**: segmented Active | Daily | Done. The **Quest Board** card sits on top (Path filter chips and difficulty stars, then the suggestion card with Skip / 🎲 / Accept). Below it is the full quest list, where long-press edits. A FAB "+" adds a quest through a bottom sheet (title, Path, kind, difficulty, note).

**Bills**: summary card "₱23,198 due in 30 days" (overdue count in danger). Rows sorted overdue → due soon → upcoming → paid (collapsed). FAB "+" opens a sheet (name, amount, due date, repeat). Paying shows a Steward XP floater.

**Rewards**: CoinCounter header. Personal rewards in a 2-column grid of RewardTiles, then a "Themes" section of theme tiles with swatches. "+ New reward" sheet (title, cost).

**Me**:
```
Avatar  Jarvin · Lv 4 · 🪙 135
Paths     PathProgress ×6 (tap → Path detail)
Weekly    done vs skipped · XP per Path (mini bars) · best streak 🔥
Logbook   + workout / sleep / note → list by day
Theme     ThemeSwatch ×4 (locked show price → Rewards)
Export    "Save file (JSON)"
```

## Bottom nav + center slot (v1.5)
- Bar: Today · Quests · [center] · Rewards · More. Bills moved into More (Plan & focus); overdue bills show a red dot on More, the count on the Bills tile, and the dot moves to the center orb when Bills is pinned.
- Center slot = any More feature (`more.pinnable_keys`: built from `SECTIONS`, minus coming-soon tiles and modules switched off in Settings; new tiles appear automatically). Saved as `Profile.center_pin` (None = empty; a switched-off module reads empty but keeps the pin). Rules: `core/pins.py`.
- Tap empty -> picker sheet. Tap pinned -> opens the feature on the center's own stack (`CenterScreen`, shares sub-screen instances with More), center highlighted; back at its root returns to the previous tab. Hold -> unpin + "Unpinned X" toast with Undo (heavy buzz). Pinning: `unlock` sound + medium buzz + orb pop + toast. Settings -> Middle button: Change (same picker) / Unpin.
- `app.open_sub(key)` for the pinned key from another tab opens it under the center; `app.more` is the visible stack (center or More); `app.showing(key)` replaces hard-coded tab checks.
