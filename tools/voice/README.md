# Luma voicepack tools (PC only)

Makes Luma's spoken clips in `src/assets/voice/<kind>_<n>.wav` from `lines.json`.
Nothing here ships with the app; only the generated WAVs do.

## Engine
- **Piper TTS**, standalone Windows binary `piper_windows_amd64.zip`, release `2023.11.14-2`,
  from https://github.com/rhasspy/piper/releases, unzipped to `bin/piper/` (MIT license).
- The `piper-tts` pip package could not be used: it needs `onnxruntime` and
  `piper-phonemize`, which have no Python 3.15 wheels. `.venv` (stdlib-only) just runs the
  script; `make_voice.py` uses only the standard library.

## Voice
- **en_GB-alba-medium** (female, Scottish English, calm), from
  https://huggingface.co/rhasspy/piper-voices/tree/main/en/en_GB/alba/medium, saved in `models/`
  (model `.onnx`, its `.onnx.json`, and `MODEL_CARD`).
- **License** (from MODEL_CARD): dataset https://datashare.ed.ac.uk/handle/10283/3270,
  **CC BY 4.0** (https://creativecommons.org/licenses/by/4.0/). Commercial use is allowed
  **with attribution**. Credit it in the app's About/credits, for example:
  "Luma voice: Piper TTS, alba voice (University of Edinburgh, CC BY 4.0)."
- Why alba: the other calm female candidates have licenses that are unclear or restrictive
  for shipping. hfc_female is CC BY-NC-SA (non-commercial), lessac uses the Blizzard 2013
  research license, and amy only says "see URL".

## Regenerate
```
tools/voice/.venv/Scripts/python tools/voice/make_voice.py              # all clips
tools/voice/.venv/Scripts/python tools/voice/make_voice.py quest_done   # one kind
```
Settings live at the top of `make_voice.py`. Pace: `length_scale` 1.06, `noise_scale` 0.5,
inner pauses capped at 0.22 s. Loudness: RMS normalized to -19 dBFS with a -1.5 dBFS peak cap.
Output: mono 16-bit WAV at 22.05 kHz, with 40 ms of lead silence and 100 ms of tail silence.
OGG/Opus would be smaller, but no encoder is available without new installs. Piper output
varies slightly from run to run, so durations and sizes shift a little each time.

Keys in `lines.json` are `<kind>_<n>`, and the lines are generic (no numbers or names).
Variant n mirrors the matching `voice.LINES` variant where one exists, so the spoken clip
fits the line on screen. If you add or remove variants, update `CLIPS` in
`src/lol/ui/audio.py`. The script checks it and prints a warning if they differ.

## Name and welcome back
The assistant is **Luma** (eSpeak/Piper reads it `lˈuːmɐ`, "LOO-mah", spelled plainly).
`hello_again_1..6` are Luma's welcome back on app open / resume: variant i fits
`lol.core.welcome.SLOTS[i]` (morning, day, day, evening, night, away) and mirrors
`voice.LINES["hello_again"][i]`. Regenerate with `make_voice.py hello_again`, then
`tools/sfx/encode_ogg.py` for the Android OGGs.
