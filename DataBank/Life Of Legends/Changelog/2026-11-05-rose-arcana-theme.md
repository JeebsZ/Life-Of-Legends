# Rose Arcana theme (free)

A second glowing mind-space theme in pink, free for every player (`catalog.FREE_THEMES`; old saves gain it on load like Arcane did).

- Palette (`theme.py`, id `rose`): bg #120814, surface #1C0D21, surface_hi #27142E, primary #FF6FB1 (on_primary #2B0418), coins #FFC08A, success mint #6EE7BF, danger #FF8063, text #FCEAF3, dim #C7A6BC. Paths: chef #FFA066, warrior #FF5E68, scholar #7DB6FF, artisan #C29BFF, ranger #5FE0B0, steward #FFD66E, monk #B3D99A.
- Contrast: text 16.1:1 / 14.9:1 on panels, dim text 8.5:1 / 7.8:1, dark-on-rose buttons 7.2:1. Closest Path pair ΔE 27 (ranger/monk).
- Mind-space (`ambient.tones`): plum/magenta/lilac/peach nebula, rose and lilac motes.
- Theme picker: swatches are now little preview orbs (theme light blooming out of its night, coin-coloured star, glow on glowing themes) in a 3-wide grid.
- QuestCleared: the label backing and subtitle now follow the theme bg/text (unchanged on Arcane), and the third spark colour is the theme's success colour.
- Tests: `tests/test_themes.py`.
