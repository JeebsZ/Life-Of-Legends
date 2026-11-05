"""Build the app's pack-based sound effects from the Sci-Fi UI SFX pack (stdlib only).

    .venv/Scripts/python tools/sfx/pack_sfx.py          # all mapped sounds
    .venv/Scripts/python tools/sfx/pack_sfx.py tab      # only names starting with "tab"

Reads src/assets/customsfx/scifi-ui-sfx/WAV/<folder>/<file>.wav (48 kHz / 24-bit mono; the pack
is excluded from the APK and must NOT be redistributed), mixes the layers listed in MAPPING,
resamples to 44.1 kHz (windowed-sinc, 147/160 polyphase), trims the silent tail (-50 dB under
the peak, 15 ms fade), matches LOUDNESS (RMS of the audible part, dBFS - see analyze_sfx), caps
the peak at -1 dBFS and writes 16-bit mono WAVs to src/assets/sfx/<name>.wav. Only these
derived files ship. It prints a ready-to-paste mixer.AUDIBLE / sfx.LENGTHS table.
Deterministic: the same pack gives byte-identical files.
"""
from __future__ import annotations

import math
import re
import struct
import sys
import wave
from pathlib import Path

from analyze_sfx import audible, load

ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "src" / "assets" / "customsfx" / "scifi-ui-sfx" / "WAV"
OUT = ROOT / "src" / "assets" / "sfx"
SR = 44100
PEAK_MAX_DB = -1.0
TAIL_DB = -50.0
FADE_S = 0.015

# file stem -> (layers [(pack file, gain dB, offset s)], target loudness dBFS).
# Targets follow the synth sounds (so the set sits with the kept skill_acquired / lumen_hum /
# level_up / milestone): reward stingers ~-16..-19, nav ~-21..-24, ticks and typing quieter.
# Stems ending in _<digit> are random variants of one sound (sfx.VARIANTS), e.g. tap_1..tap_5.
L = list[tuple[str, float, float]]


def _one(rel: str) -> L:
    return [(rel, 0, 0)]


MAPPING: dict[str, tuple[L, float]] = {
    # buttons / select: click_digital family (round 2: the user disliked the heavy click)
    **{f"tap_{i}": (_one(f"clicks/click_digital_0{i}"), -24.0) for i in range(1, 6)},
    "toggle_on": (_one("clicks/click_digital_06"), -23.0),
    # opening panels / screens, closing (back) screens, sheets and dialogs
    **{f"tab_open_{i}": (_one(f"panels/holo_open_0{i}"), -22.0) for i in range(1, 4)},
    **{f"tab_close_{i}": (_one(f"panels/holo_close_0{i}"), -22.0) for i in range(1, 4)},
    **{f"back_{i}": (_one(f"cancel/back_0{i}"), -22.0) for i in range(1, 5)},
    # notification sound picker (Settings; also the in-app 'notice' ping)
    **{f"notify_0{i}": (_one(f"notification/notify_0{i}"), -19.0) for i in range(1, 9)},
    "alert_soft": (_one("error/warning_01"), -16.5),
    "error_soft": (_one("error/error_01"), -19.5),
    "coin": (_one("reward/credits"), -21.0),
    "coin_many": (_one("reward/credits_many"), -19.5),
    "xp_fill": (_one("reward/xp_gain"), -21.0),
    "timer_tick": (_one("hud/countdown_tick"), -30.0),
    "timer_done": (_one("notification/alarm_03"), -18.0),
    # kept layered stingers (round 1)
    "quest_done": ([("confirm/access_granted_01", 0, 0), ("hud/shield_up", -6, 0)], -16.0),
    "quest_clear": ([("confirm/confirm_07", 0, 0), ("clicks/click_heavy_01", -4, 0)], -15.5),
    # layers played on top of the heavy moments (sfx.COMBOS)
    **{f"granted_{i}": (_one(f"confirm/access_granted_0{i}"), -19.0) for i in range(1, 4)},
    **{f"holo_flicker_{i}": (_one(f"panels/holo_flicker_0{i}"), -22.0) for i in range(1, 3)},
    "unlock": (_one("reward/unlock"), -19.0),
    "upgrade": (_one("reward/upgrade"), -19.0),
    "mission_complete": (_one("reward/mission_complete"), -18.0),
    "rank_up": (_one("reward/rank_up"), -18.0),
    # events
    "purchase": (_one("reward/purchase"), -19.0),
    "objective_new": (_one("hud/objective_new"), -19.5),
    "power_up": (_one("power/power_up_01"), -19.5),
    "low_energy": (_one("hud/low_energy"), -21.0),
    "low_health": (_one("hud/low_health"), -21.0),
    "loading": (_one("computer/loading_03"), -24.0),
    **{f"type_{i}": (_one(f"typing/type_0{i}"), -29.0) for i in range(1, 7)},
    # analysis / camera
    "distort": (_one("error/error_glitch_01"), -19.0),
    "scan_tick": (_one("typing/text_blip_01"), -26.0),
    "scan_done": (_one("confirm/confirm_05"), -19.5),
    "shutter": (_one("clicks/click_heavy_02"), -18.0),
}


# ------------------------------------------------------------------- resampling 48k -> 44.1k
def _taps(up: int = 147, down: int = 160, half: int = 16) -> list[list[float]]:
    """Polyphase windowed-sinc (Blackman) tables, one per output phase."""
    fc = 0.5 * up / down * 0.94  # cutoff, cycles per input sample (just under 22.05 kHz)
    tables = []
    for ph in range(up):
        frac = (ph * down % up) / up
        row = []
        for k in range(-half + 1, half + 1):
            d = k - frac
            s = 2 * fc * (math.sin(2 * math.pi * fc * d) / (2 * math.pi * fc * d) if d else 1.0)
            w = 0.42 + 0.5 * math.cos(math.pi * d / half) + 0.08 * math.cos(2 * math.pi * d / half)
            row.append(s * w if abs(d) < half else 0.0)
        tables.append(row)
    return tables


def resample(x: list[float], sr_in: int) -> list[float]:
    if sr_in == SR:
        return list(x)
    if sr_in != 48000:
        raise ValueError(f"unsupported rate {sr_in}")
    up, down, half = 147, 160, 16
    tabs = _taps(up, down, half)
    pad = [0.0] * half
    xp = pad + x + pad
    n_out = len(x) * up // down
    out = []
    for m in range(n_out):
        base = m * down // up  # integer input index
        row = tabs[m % up]
        i0 = base + half - half + 1  # xp index of input sample base - half + 1
        out.append(sum(c * v for c, v in zip(row, xp[i0:i0 + 2 * half])))
    return out


# ------------------------------------------------------------------- processing
def build(name: str) -> list[float]:
    layers, target = MAPPING[name]
    mix: list[float] = []
    for rel, gain_db, offset in layers:
        sr, x = load(PACK / f"{rel}.wav")
        x = resample(x, sr)
        g = 10 ** (gain_db / 20)
        start = int(offset * SR)
        need = start + len(x)
        if len(mix) < need:
            mix.extend([0.0] * (need - len(mix)))
        for i, v in enumerate(x):
            mix[start + i] += v * g
    mix = trim(mix)
    return normalize(mix, target)


def trim(x: list[float]) -> list[float]:
    pk = max(abs(v) for v in x) or 1.0
    thr = pk * 10 ** (TAIL_DB / 20)
    last = max(i for i, v in enumerate(x) if abs(v) > thr)
    n_fade = int(FADE_S * SR)
    end = min(len(x), last + n_fade)
    y = x[:end]
    for i in range(min(n_fade, len(y))):
        y[end - 1 - i] *= i / n_fade
    return y


def loud_db(x: list[float]) -> float:
    aud, _ = audible(x, SR)
    seg = x[: max(1, int(aud * SR))]
    return 20 * math.log10(math.sqrt(sum(v * v for v in seg) / len(seg)) or 1e-9)


def normalize(x: list[float], target_db: float) -> list[float]:
    g = 10 ** ((target_db - loud_db(x)) / 20)
    pk = max(abs(v) for v in x) * g
    cap = 10 ** (PEAK_MAX_DB / 20)
    if pk > cap:
        g *= cap / pk
    return [v * g for v in x]


def write_wav(path: Path, x: list[float]) -> None:
    data = struct.pack(f"<{len(x)}h", *(max(-32767, min(32767, round(v * 32767))) for v in x))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(data)


def base(stem: str) -> str:
    """Variant files share one name: tap_3 -> tap (notify_03 keeps its two-digit suffix)."""
    return re.sub(r"_\d$", "", stem)


def main(argv: list[str]) -> int:
    names = [n for n in MAPPING if not argv or any(n.startswith(a) for a in argv)]
    if not names:
        print(f"no sound matches {argv}; known: {', '.join(MAPPING)}")
        return 1
    if not PACK.is_dir():
        print(f"pack not found: {PACK}")
        return 1
    total = 0
    aud: dict[str, float] = {}
    lens: dict[str, float] = {}
    for name in names:
        x = build(name)
        path = OUT / f"{name}.wav"
        write_wav(path, x)
        size = path.stat().st_size
        total += size
        aud[name] = audible(x, SR)[0]
        lens[name] = len(x) / SR
        pk = 20 * math.log10(max(abs(v) for v in x))
        print(f"{name:12s} {lens[name]:5.2f} s  audible {aud[name]:4.2f} s  peak {pk:6.1f}  "
              f"loud {loud_db(x):6.1f} dBFS  {size / 1024:6.1f} KB")
    print(f"{len(names)} file(s), {total / 1024:.0f} KB -> {OUT}")
    def per_base(d: dict[str, float]) -> dict[str, float]:
        out: dict[str, float] = {}
        for n, v in d.items():
            b = base(n)
            out[b] = max(out.get(b, 0.0), v)
        return out

    print("mixer.AUDIBLE:", ", ".join(f'"{n}": {v:.2f}' for n, v in per_base(aud).items()))
    print("sfx.LENGTHS: ", ", ".join(f'"{n}": {v:.2f}' for n, v in per_base(lens).items()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
