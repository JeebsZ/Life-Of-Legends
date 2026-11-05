# UI sound effects (PC only)

The app's sound effects are the files in `src/assets/sfx/<name>.wav` (mono, 16-bit, 44.1 kHz).
They come from two sources:

- **Sci-Fi UI SFX pack** (`pack_sfx.py`): every UI, notice, timer and quest sound, plus the
  analysis and camera sounds.
- **Original synth** (`make_sfx.py`): `level_up`, `skill_acquired`, `milestone` and
  `lumen_hum`. The user loves `skill_acquired` and `lumen_hum`. The pack's `level_up` and
  `rank_up` were measured against ours and have less low end: 9-12% of their energy is below
  250 Hz, against 31% for our `level_up` and 55% for `milestone`. So all four stay synth, and
  they stay the same family as `skill_acquired`.

Nothing in `tools/` ships with the app. Only the WAVs in `src/assets/sfx` do.

## Sci-Fi UI SFX pack (`pack_sfx.py`)
Source: `src/assets/customsfx/scifi-ui-sfx/` (224 sounds, as WAV 48 kHz/24-bit and as OGG).
**License:** the sounds may be used in apps without attribution, but the pack itself must
**not** be redistributed. The pack folder stays excluded from the APK (`pyproject.toml`
`exclude`), and only the derived files below are copied into `src/assets/sfx`. Never copy the
pack, or files from it that the app doesn't use, into the app or a public repo.

```
.venv/Scripts/python tools/sfx/pack_sfx.py             # rebuild all mapped sounds (~3 s)
.venv/Scripts/python tools/sfx/pack_sfx.py scan        # only names starting with "scan"
.venv/Scripts/python tools/sfx/analyze_sfx.py --pack   # scan the whole pack (~5 s)
```
`pack_sfx.py` does the following, in order:
1. Mixes the layers.
2. Resamples from 48k to 44.1k (windowed sinc).
3. Trims the tail at -50 dB under the peak.
4. Sets the loudness (the RMS of the audible part) to the target.
5. Caps the peak at -1 dBFS.
6. Prints the `mixer.AUDIBLE` and `sfx.LENGTHS` tables.

We ship WAV instead of the pack's OGG for two reasons. WAV plays everywhere: on Android's
MediaPlayer, on iOS's AVPlayer (which has no Vorbis), and in Windows `flet run`. And the stdlib
can normalize a WAV's loudness.

The files were picked with `analyze_sfx.py --pack`, not by ear. For each role, the file with the
highest bass score wins, as long as it is the right gesture. The bass score is the share of
energy below 250 Hz minus the share above 4 kHz. Bright "digital" ticks, credit pings and hover
blips score between -0.2 and -0.45. They were avoided as chiptune-ish. The centroid trajectory
confirmed which sweeps rise and which fall.

Round 3 (user's call): plain button taps and toggle/select clicks are **silent**. `sfx.SILENT`
(`tap`, `toggle_on`) makes `play()` drop them; the files and call sites stay, so taking a name
out of `SILENT` brings the click back. Haptics and visuals still answer every tap. Everything
that marks progress keeps its sound (quest/chain/skill/level/milestone, coins, xp, purchase,
objective_new, notices, typing, loading, power_up, low_*), and so does navigation
(`tab_open`/`tab_close` holo sweeps, `back`/`sheet_close`), which reads as a screen change
rather than a click. The SFX gallery labels muted sounds "muted".

Round 2 (user's picks): button/select sounds replaced; the heavy reward sounds kept and pack
sounds **layered on top** of them (sfx.COMBOS), never swapped. `_N` = random variant per play.

| event (play name) | sound / pack file(s) | where it plays |
|---|---|---|
| `tap` | click_digital_01-05 (random, `tap_1..5`) | **muted** (`sfx.SILENT`): button taps are silent |
| `toggle` / `toggle_on` / `toggle_off` | click_digital_06 | **muted** (`sfx.SILENT`): selects, switches |
| `tab_open` / `sheet_open` | holo_open_01-03 | tabs, sub-screens, sheets open |
| `tab_close` | holo_close_01-03 | leaving the More tab |
| `back` / `sheet_close` | back_01-04 | back from a sub-screen, closing sheets/dialogs |
| `notice` | the profile's `notify_sound` (notify_01-08) | Luma notice ping; phone notifications |
| `chain_step` | quest_clear + access_granted_01-03 (+0.06 s, 70%) | side-quest chain step |
| `chain_complete` | quest_done + mission_complete (+0.1 s, 60%) | last chain step (skill unlocked) |
| `skill_unlock` | skill_acquired + unlock (55%) + holo_flicker_01/02 (+0.12 s, 60%) | SKILL ACQUIRED emblem |
| `skill_rank_up` | skill_acquired + upgrade (55%) + holo_flicker | SKILL RANK UP emblem |
| `path_level_up` | level_up + rank_up (50%) | Path level-up banner |
| `quest_done` / `quest_clear` | kept round-1 layers (access_granted_01+shield_up / confirm_07+click_heavy_01) | quest rewards |
| `coin` / `coin_many` | credits / credits_many | coin payout (hard quest = many) |
| `xp_fill` | xp_gain | XP bar fill |
| `purchase` | purchase | reward redeemed |
| `objective_new` | objective_new | quest added |
| `power_up` | power_up_01 | app open / resume (greeting layers over it) |
| `low_energy` / `low_health` | low_energy / low_health | "Low" energy check-in / a new overdue bill |
| `loading` | loading_03 | staged analysis start (under the hum) |
| `type` | type_01-06 (random, rate-limited 85-150 ms) | Luma notice typewriter, staged labels |
| `timer_tick` / `timer_done` | countdown_tick / alarm_03 | focus timer (tick at 50%, per second) |
| `alert_soft` / `error_soft` | warning_01 / error_01 | alerts, validation |
| `distort` / `scan_tick` / `scan_done` / `shutter` | error_glitch_01 / text_blip_01 / confirm_05 / click_heavy_02 | effects, analysis, camera |
| `level_up` / `skill_acquired` / `milestone` / `lumen_hum` | synth (make_sfx.py) | kept |

Loudness targets (RMS of the audible part): stingers -15.5..-19, nav -22..-24, typing -29,
ticks -26..-30; the synth set sits at -12..-18.

## APK: OGG
The APK ships OGG Vorbis only: `tools/sfx/encode_ogg.py` encodes `src/assets/sfx/*.wav` and
`src/assets/voice/*.wav` to `src/assets/ogg/{sfx,voice}` (q4 mono, ~1.4 MB total vs ~7.8 MB
WAV) and copies notify_0*.ogg to the flet_lumen_notify Android res/raw. On Android
`sfx.py` / `audio.py` load `/ogg/...`; desktop / web keep the WAVs. pyproject excludes
`assets\sfx` and `assets\voice` for Android and `assets\ogg` elsewhere (flet's exclude is
an exact relative path, no globs). No encoder is installed: the script uses $LOL_FFMPEG, PATH
or an ffmpeg with libvorbis already on this PC (KNOWN). Re-run it after any WAV change.

To add a new sound:
1. Add a `MAPPING` entry in `pack_sfx.py` (stem `name` or `name_1..n` for variants), run it,
   then `encode_ogg.py`.
2. Add it to `SINGLE` or `VARIANTS` and `LENGTHS` in `src/lol/ui/sfx.py`, and to `AUDIBLE` in
   `src/lol/ui/mixer.py` (both printed). FOREGROUND only if Luma must not talk over it.

`tests/test_audio_player.py` checks every sound has WAV + OGG + table entries.


## Synth sounds (`make_sfx.py`)
The synth sounds are **original**. The style takes after the "airy, glassy" feel of Opera GX's
tab sounds, but nothing is sampled from them or copied note for note. The building blocks are
filtered-noise whooshes, inharmonic glass and bell partials, soft FM pings, shimmer clouds and
a small Schroeder reverb. The script uses only the Python standard library.

`make_sfx.py` writes the names that now come from the pack (`pack_sfx.MAPPING`, plus `toggle`)
to `tools/sfx/synth_out/` instead. The old synth versions can still be auditioned there, and
they never overwrite the shipped files. Only `level_up`, `skill_acquired`, `milestone` and
`lumen_hum` land in `src/assets/sfx`.

**v1.3 (phone feedback): more body, less retro.** `skill_acquired` is the reference sound.
Every reward sound now carries its low end: `impact()` (a gently tanh-saturated sine that
glides down onto the root, plus a lowpassed noise thump) and `hum()` (a sustained, saturated
low "hmm" with optional fifth). The saturation adds 2nd/3rd harmonics around 120-250 Hz, so
the bass still reads on a phone speaker that cannot play 55 Hz. Chimes are strummed with soft
4-12 ms attacks and gentle detune instead of hard-stepped blips, shimmer tremolo is slower and
shallower, and the reverb matches `skill_acquired`'s big soft room. Navigation sounds stay
light (`tab_open` / `tab_close` only gained a faint low "whoomp").

### Regenerate the synth sounds
```
.venv/Scripts/python tools/sfx/make_sfx.py            # all 19 recipes (~10 s)
.venv/Scripts/python tools/sfx/make_sfx.py tab        # only names starting with "tab"
.venv/Scripts/flet run src/lol/ui/sfx_gallery.py      # listen: one button per sound,
                                                      # + "Quest complete sequence" (with voice)
```
The output is deterministic. Each sound uses its own fixed seed (a CRC of its name), so
regenerating gives byte-identical files.
Format: mono, 16-bit, 44.1 kHz WAV.
The run also prints each sound's **audible** length (`audible()`: until its short-term RMS
last sits within 20 dB of its loudest moment) as a ready-to-paste `mixer.AUDIBLE` table.

### Synth recipes (only level_up, skill_acquired, milestone, lumen_hum ship; the rest land in synth_out/)
| name | length | peak | what it is |
|---|---|---|---|
| `tab_open` | ~0.42 s | -9 dBFS | Bandpassed noise sweeping 650 Hz to 5.2 kHz, a faint sine glide, a glassy click (2.96 kHz), and a faint 62 to 82 Hz whoomp under it |
| `tab_close` | ~0.36 s | -9.5 | Mirror of `tab_open`: a darker click (2.35 kHz) first, then noise falling 4.2 kHz to 520 Hz and a faint 90 to 62 Hz whoomp, lowpassed |
| `tap` | 44 ms | -14 | Tiny 1.9 kHz glass tick + 4 ms air transient |
| `toggle` | 0.16 s | -12 | Two soft detuned glass taps, 1050 Hz then 1575 Hz (up a fifth), tiny room |
| `sheet_open` / `sheet_close` | ~0.4 s | -12 / -13 | Low-Q noise whoosh up / down (340 Hz to 2.5 kHz) with a soft low body, lowpassed (no click) |
| `quest_done` | ~1.6 s | -3 | Deep E impact (130 to 82 Hz + thump) and E hum, then a soft crystal strum E6, B6, E7 (60 ms apart), a few high twinkles |
| `coin` | ~0.7 s | -7 | Two detuned crystal-bell pings (D7, A7) with a light FM edge, airy twinkles, a faint low tick; stays soft |
| `xp_fill` | ~0.9 s | -9 | Smooth shimmer cloud rising 700 Hz to 1.45 kHz (slow, shallow tremolo) + rising air + a quiet 110 to 165 Hz hum |
| `level_up` | ~2.0 s | -3 | Deep C impact and C/G hum, then a soft C-major strum C5 E5 G5 C6 E6 (12 ms attacks, swelling in), shimmer bloom |
| `skill_acquired` | ~2.3 s | -4 | **The reference.** Deep soft impact (110 Hz falling to 44 Hz + lowpassed thump), a sustained A hum, then an A6/E7/A7 crystal chord and sparkles in a large reverb |
| `milestone` | ~3.5 s | -3 | Four tones gliding up a fourth into an A-major chord over a swelling A1 hum, a deep impact as they land, a crystal chord, then a rune-like twinkle of A-pentatonic glass grains |
| `notice` | ~0.86 s | -8 | A soft air breath and a low G2 "hmm", then a detuned G6 glass ping (plays right before Luma speaks) |
| `alert_soft` | ~1.1 s | -6 | Polite "ding-dong", A5 then F5, mellow bell, each over a soft low hum |
| `error_soft` | ~0.29 s | -10 | Two low muted thuds (260 Hz, then 228 Hz), heavily lowpassed |
| `timer_tick` | 25 ms | -22 | Very soft 2.2 kHz tick |
| `timer_done` | ~2.8 s | -4 | Risset-style inharmonic bell on E5 with a faint B5 echo over a warm E2 hum, long tail |
| `quest_clear` | ~1.0 s (audible 0.54) | -4.5 | Stinger for the QuestCleared flash: an airy upward flick, a soft E bass thump, a detuned B6/E7 glass pair and sparks |
| `lumen_hum` | ~2.6 s (audible 2.1) | -3.5 | Luma's thinking intro (original): detuned saws on D2 + an A2 fifth through a resonant lowpass that opens from 110 Hz to ~1.5 kHz while the pitch settles up into D, a D1 sub swell, an airy whoosh building under it, then at 1.2 s a crystalline bloom (D6 A6 D7 E7 + shimmer + sparkles) as the orb appears |

### Tweaking the synth
- Each sound is one `s_<name>(rng)` function in `make_sfx.py`. Its docstring describes the
  recipe, and the numbers in it are the knobs: sweep start and end Hz, durations, gains and
  decay times.
- Loudness: `SOUNDS` maps each name to `(recipe, peak dBFS)`. Every sound passes through
  `finish()`, which soft-limits it (tanh), trims the tail below -46 dB (quiet UI sounds) or
  -54 dB (louder ones) relative to the peak, applies a 25 ms fade-out, and normalizes the peak.
- Brightness: lower the `glass_click` frequency or add a `lowpass(x, Hz)` to make a sound
  darker. Raise `bright` or the FM `index` to make it glassier.
- Space: use the `reverb(..., size, decay, damp, wet, tail)` call at the end of each recipe.
  `decay` controls tail length (0.6 to 0.9), `damp` makes the tail darker, and `wet` sets the
  reverb level.
- Change a seed: edit `seed_for()` (this changes the noise and sparkle placement of every sound).
- Body: `impact(out, at, f, rng, gain, glide_from)` and `hum(dur, f, attack, tau)` are the
  low-end layers. Raise their gain for more weight; `drive` sets how much harmonic "phone
  bass" the saturation adds.
- New sound: add a recipe, add an entry to `SOUNDS`, then add the name to `NAMES` and
  `LENGTHS` in `src/lol/ui/sfx.py` (the file's duration) and to `AUDIBLE` in
  `src/lol/ui/mixer.py` (the printed audible length). If Luma's voice must not talk over
  it, add it to `mixer.FOREGROUND`.

## Checking without ears
`.venv/Scripts/python tools/sfx/analyze_sfx.py` (about 20 s) prints each file's duration,
peak, RMS and loudness (the audible part) in dBFS, clipped-sample count and a spectral-centroid
trajectory (reads 16- and 24-bit WAV), so you can confirm sweep directions and that nothing
clips. `--pack [DIR]` is the fast recursive scan used to pick the pack sounds: audible length,
loudness, low / high energy shares and the bass score.

## Voice sequencing (`src/lol/ui/mixer.py`)
A tiny bus shared by `sfx.py` and `audio.py` (Luma's voice), so the two never talk over
each other:
- When a sound in `FOREGROUND` starts (`quest_done`, `quest_clear`, `level_up`,
  `skill_acquired`, `milestone`, `lumen_hum`, `alert_soft`, `timer_done`), a voice clip waits
  until its audible part ends + 0.15 s (capped at 2.2 s). `audio.py` applies the wait before
  every clip; `LumenNotice` uses `mixer.cue()` so its `notice` ping and the voice land together
  after the chime.
- While Luma speaks, every new effect plays at 35% (a level / skill / milestone moment at
  60%), and effects still sounding when the voice starts are turned down the same way.
- Quest complete: `quest_done` chime + `xp_fill` at 35% at 0 s, `coin` at 55% at 0.35 s, then
  the `notice` ping + Luma's line at ~0.85 s (the pack `quest_done` is audible for 0.68 s).
  Audition it with the gallery's "Quest complete sequence" button.
- `distort`, `scan_tick`, `scan_done` and `shutter` are not in `FOREGROUND`, so the voice never
  waits for them.
- On Android, the voice and the effects mix instead of stealing audio focus from each other.
  This used to cut Luma off mid-line. See `extensions/flet_lumen_notify/README.md`
  "Audio focus".

## Player
`src/lol/ui/sfx.py` covers `init(page, settings)`, `play(name, volume=None)`,
`set_enabled` and `set_volume`. It reads `sfx_on`, `sfx_volume` and `reduce_effects` from the
profile. See its module docstring for details.
