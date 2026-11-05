"""Regenerate Luma's voice clips from lines.json with Piper TTS (PC-only tool).

    tools/voice/.venv/Scripts/python tools/voice/make_voice.py            # all clips
    tools/voice/.venv/Scripts/python tools/voice/make_voice.py quest_done # only keys starting so

Stdlib only (wave/array/subprocess), so it runs on any Python. Needs the Piper Windows binary
in tools/voice/bin/piper/ and the voice model in tools/voice/models/ (see README.md).

Each clip: Piper at a calm pace (length_scale > 1, low noise) -> trim edge silence and
shorten long inner pauses -> loudness normalize (RMS target, peak-limited) -> 10 ms fades
-> short silence pad -> mono 16-bit WAV at the model rate (22.05 kHz) in src/assets/voice/<key>.wav. Stale clips are removed.
"""

from __future__ import annotations

import ast
import json
import math
import subprocess
import sys
import tempfile
import wave
from array import array
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PIPER = HERE / "bin" / "piper" / "piper.exe"
MODEL = HERE / "models" / "en_GB-alba-medium.onnx"
LINES = HERE / "lines.json"
OUT = ROOT / "src" / "assets" / "voice"
AUDIO_PY = ROOT / "src" / "lol" / "ui" / "audio.py"

# calm pacing
LENGTH_SCALE = 1.06   # >1 = slower
NOISE_SCALE = 0.5     # less expressive wobble than default 0.667
NOISE_W = 0.6
SENTENCE_SILENCE = 0.16
# loudness
TARGET_RMS_DB = -19.0
PEAK_DB = -1.5
# padding / fades (seconds)
LEAD_PAD = 0.04
TAIL_PAD = 0.10
FADE = 0.010
SILENCE_THRESH = 0.02  # of peak, for trimming
MAX_GAP = 0.22          # inner pauses longer than this are shortened to it


def synth(text: str, wav_path: Path) -> None:
    cmd = [str(PIPER), "-m", str(MODEL), "-f", str(wav_path), "-q",
           "--length_scale", str(LENGTH_SCALE), "--noise_scale", str(NOISE_SCALE),
           "--noise_w", str(NOISE_W), "--sentence_silence", str(SENTENCE_SILENCE)]
    subprocess.run(cmd, input=text.encode("utf-8"), check=True, capture_output=True)


def read_wav(path: Path) -> tuple[array, int]:
    with wave.open(str(path), "rb") as w:
        assert w.getnchannels() == 1 and w.getsampwidth() == 2, "expected mono 16-bit"
        rate = w.getframerate()
        data = array("h")
        data.frombytes(w.readframes(w.getnframes()))
    if sys.byteorder == "big":
        data.byteswap()
    return data, rate


def collapse_gaps(x: list[float], thresh: float, rate: int) -> list[float]:
    """Shorten silent stretches (10 ms windows under thresh) longer than MAX_GAP."""
    win, keep = int(0.01 * rate), int(MAX_GAP * rate)
    out: list[float] = []
    quiet: list[float] = []
    for i in range(0, len(x), win):
        chunk = x[i:i + win]
        if max(abs(s) for s in chunk) < thresh:
            quiet.extend(chunk)
            continue
        if len(quiet) > keep:  # keep the edges of the pause, drop its middle
            quiet = quiet[:keep // 2] + quiet[-(keep - keep // 2):]
        out.extend(quiet)
        out.extend(chunk)
        quiet = []
    return out + quiet


def process(data: array, rate: int) -> array:
    peak = max((abs(s) for s in data), default=0) or 1
    thresh = peak * SILENCE_THRESH
    first = next((i for i, s in enumerate(data) if abs(s) > thresh), 0)
    last = next((i for i in range(len(data) - 1, -1, -1) if abs(data[i]) > thresh), len(data) - 1)
    margin = int(0.02 * rate)
    x = collapse_gaps([float(s) for s in data[max(0, first - margin): last + margin]],
                      thresh, rate)
    rms = math.sqrt(sum(s * s for s in x) / max(1, len(x))) or 1.0
    gain = min(32767 * 10 ** (TARGET_RMS_DB / 20) / rms,
               32767 * 10 ** (PEAK_DB / 20) / (max(abs(s) for s in x) or 1.0))
    n_fade = int(FADE * rate)
    for i in range(min(n_fade, len(x) // 2)):
        f = i / n_fade
        x[i] *= f
        x[-1 - i] *= f
    out = array("h", [0] * int(LEAD_PAD * rate))
    out.extend(max(-32768, min(32767, round(s * gain))) for s in x)
    out.extend([0] * int(TAIL_PAD * rate))
    return out


def write_wav(path: Path, data: array, rate: int) -> None:
    if sys.byteorder == "big":
        data = array("h", data)
        data.byteswap()
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(data.tobytes())


def check_audio_py(keys: list[str]) -> None:
    """Warn if audio.CLIPS (variant counts the app plays) disagrees with lines.json."""
    counts = Counter(k.rsplit("_", 1)[0] for k in keys)
    try:
        tree = ast.parse(AUDIO_PY.read_text(encoding="utf-8"))
        clips = next(ast.literal_eval(n.value) for n in ast.walk(tree)
                     if isinstance(n, ast.AnnAssign | ast.Assign)
                     and "CLIPS" in ast.unparse(n.targets[0] if isinstance(n, ast.Assign)
                                                else n.target))
    except Exception as e:  # noqa: BLE001
        print(f"! could not read CLIPS from {AUDIO_PY}: {e}")
        return
    if dict(counts) != dict(clips):
        print(f"! update CLIPS in {AUDIO_PY} to: {dict(sorted(counts.items()))}")
    else:
        print("audio.CLIPS matches lines.json")


def main(argv: list[str]) -> None:
    lines: dict[str, str] = json.loads(LINES.read_text(encoding="utf-8"))
    only = argv[1:]
    OUT.mkdir(parents=True, exist_ok=True)
    if not only:  # full rebuild: drop clips no longer in lines.json
        for f in OUT.glob("*.wav"):
            if f.stem not in lines and not f.stem.startswith("cue_"):  # cues: make_cues.py
                f.unlink()
    total_bytes, total_s = 0, 0.0
    with tempfile.TemporaryDirectory() as tmp:
        for key, text in lines.items():
            if only and not any(key.startswith(p) for p in only):
                continue
            raw = Path(tmp) / f"{key}.wav"
            synth(text, raw)
            data, rate = read_wav(raw)
            clip = process(data, rate)
            dest = OUT / f"{key}.wav"
            write_wav(dest, clip, rate)
            secs = len(clip) / rate
            total_s += secs
            total_bytes += dest.stat().st_size
            print(f"{key:20s} {secs:5.2f}s {dest.stat().st_size / 1024:6.1f} KB  {text}")
    print(f"total: {total_s:.1f}s, {total_bytes / 1024 / 1024:.2f} MB -> {OUT}")
    check_audio_py(list(lines))


if __name__ == "__main__":
    main(sys.argv)
