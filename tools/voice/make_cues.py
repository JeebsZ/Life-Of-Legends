"""Make the run/walk coaching cue clips (PC-only tool), from cues.json with Piper.

    tools/voice/.venv/Scripts/python tools/voice/make_cues.py      # or any Python 3

Same engine, voice and loudness as make_voice.py (it reuses its synth/process), but tuned for
stitching: very short lead/tail silence (cues play back to back) and resampled to 16 kHz to
keep the pack small. Output: src/assets/voice/cue_<key>.wav. Keys must match
lol.core.run_cues.ALL_KEYS. Lines are name-free on purpose (the assistant may be renamed).
make_voice.py leaves cue_* files alone. Then run tools/sfx/encode_ogg.py for the Android OGGs.
"""

from __future__ import annotations

import json
import sys
import tempfile
from array import array
from pathlib import Path

import make_voice as mv

CUES = mv.HERE / "cues.json"
PREFIX = "cue_"
RATE = 16000
LEAD_PAD = 0.01
TAIL_PAD = 0.05


def resample(data: array, src_rate: int, dst_rate: int = RATE) -> array:
    """Light 3-tap low-pass, then linear interpolation (fine for speech)."""
    x = [float(s) for s in data]
    sm = [x[0]] + [(x[i - 1] + 2 * x[i] + x[i + 1]) / 4 for i in range(1, len(x) - 1)] + [x[-1]]
    n = int(len(sm) * dst_rate / src_rate)
    out = array("h")
    for i in range(n):
        pos = i * src_rate / dst_rate
        j = int(pos)
        f = pos - j
        a = sm[j]
        b = sm[j + 1] if j + 1 < len(sm) else a
        out.append(max(-32768, min(32767, round(a + (b - a) * f))))
    return out


def main(argv: list[str]) -> None:
    lines: dict[str, str] = json.loads(CUES.read_text(encoding="utf-8"))
    only = argv[1:]
    mv.LEAD_PAD, mv.TAIL_PAD = LEAD_PAD, TAIL_PAD
    mv.OUT.mkdir(parents=True, exist_ok=True)
    if not only:
        for f in mv.OUT.glob(f"{PREFIX}*.wav"):
            if f.stem[len(PREFIX):] not in lines:
                f.unlink()
    total_b, total_s = 0, 0.0
    with tempfile.TemporaryDirectory() as tmp:
        for key, text in lines.items():
            if only and key not in only:
                continue
            raw = Path(tmp) / f"{key}.wav"
            mv.synth(text, raw)
            data, rate = mv.read_wav(raw)
            clip = resample(mv.process(data, rate), rate)
            dest = mv.OUT / f"{PREFIX}{key}.wav"
            mv.write_wav(dest, clip, RATE)
            secs = len(clip) / RATE
            total_s += secs
            total_b += dest.stat().st_size
            print(f"{key:16s} {secs:4.2f}s {dest.stat().st_size / 1024:5.1f} KB  {text}")
    print(f"total: {len(lines)} clips, {total_s:.1f}s, {total_b / 1024 / 1024:.2f} MB")


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    main(sys.argv)
