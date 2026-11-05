# Icosphere, screen impact and staged Lumen everywhere (2026-11-04)

Feedback: "not just a burst of glow - add the animated icosphere and some screen distortion" and
"the analyze is perfect, I want it the same with other stuff".

## Icosphere (`effects.Icosphere`)
Geodesic wireframe (icosahedron, freq 1-2), depth-faded edges in 4 bands with a glow pass on the
front band, twinkling vertex sparks, facet flashes. Choreography: `prime / appear / start /
punch / flare / vanish`. Its own Canvas redraws at 24 fps only while the effect plays (<= ~90
shapes) and stops itself. Geometry helper `icosphere_mesh(freq)` is tested (12/30/20, 42/120/80).

## Impact (`effects.distort(page_or_control, strength)`)
Zoom punch 1.0 -> 1.035 -> 1.0 + 2-4 frames of jitter on the app root (registered by
`install_distortion(page, root=shell)` in `app.mount_shell`) and the overlay stage, a flash,
cyan/magenta edge fringes, glitch slices, a scanline sweep, a 3-ring shockwave, sfx `distort`.
Titles get a chromatic ghost (cyan/magenta copies split and converge). Reduce effects: one soft
flash only.

| Effect | Now | Length |
|---|---|---|
| QuestCleared | small crystal spins in, kicks (shockwave, distort 0.42), implodes into the label | ~1.25 s, tap-through |
| NoticeEmblem (skill) | crystal charges centre 0.4 s, impact (distort 0.85) lifts it to crown the diamond | ~2.6 s |
| MilestoneSeal (level) | golden crystal charges inside the glyph rings, seal slams in front, crystal bursts behind (distort 1.0) | ~2.8 s |
| IdentifyReveal | crystal behind the title shimmers with each chain rattle, snap = punch + distort 0.9 | ~2.3 s |
| LevelUpBanner (Path) | crystal behind the card + distort 0.7 | unchanged |

## Staged analysis for any action
`LumenThinking.play_staged(seconds, stages)` takes any stages (last = mint "ready" line), ticks
`scan_tick` per stage, `scan_done` on ready. Helper:
`await components.lumen_analyze(page, stages=None, work=None, *, seconds=2.4)` - runs `work`
while the orb plays and returns its result. Wired: Lumen Report open, Insights open (once per
45 s), side-quest chain start + "Generate steps", skill rank-up, Quest Board "Give me a quest",
backup restore (after confirm), first open of an exercise's records (1.4 s).

Debug: `LOL_FX_SLOWMO=4` slows every effect for screenshots (gallery only).
Not verified: real-device performance and feel; the Path level-up banner's new crystal.
