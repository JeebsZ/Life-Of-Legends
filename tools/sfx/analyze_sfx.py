"""No-ears check of sound effects (stdlib only).

    .venv/Scripts/python tools/sfx/analyze_sfx.py               # src/assets/sfx: full report
    .venv/Scripts/python tools/sfx/analyze_sfx.py DIR           # another folder of WAVs
    .venv/Scripts/python tools/sfx/analyze_sfx.py --pack [DIR]  # fast scan, recursive (default:
                                                                # the Sci-Fi pack's WAV folder)

Full report: duration, active length, peak / RMS dBFS, clipped samples, spectral-centroid
trajectory. Pack scan (sorted by folder): duration, audible length (mixer.AUDIBLE rule), peak,
"loud" (RMS of the audible part, dBFS - what the normalizer matches), low = share of energy
below 250 Hz, high = share above 4 kHz, and a 'bass' score (low - high) used to pick the
deep, least chiptune-y candidates. Reads 16- and 24-bit PCM.
"""
import cmath
import math
import struct
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SFX = ROOT / "src" / "assets" / "sfx"
PACK = ROOT / "src" / "assets" / "customsfx" / "scifi-ui-sfx" / "WAV"
WIN = 512


def load(p):
    """(sample rate, mono floats -1..1) of a 16/24-bit PCM WAV."""
    with wave.open(str(p)) as w:
        sr, n, ch, sw = w.getframerate(), w.getnframes(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(n)
    if sw == 2:
        x = [v / 32768 for v in struct.unpack(f"<{n * ch}h", raw)]
    elif sw == 3:
        x = [int.from_bytes(raw[i:i + 3], "little", signed=True) / 8388608
             for i in range(0, len(raw), 3)]
    else:
        raise ValueError(f"{p.name}: {sw * 8}-bit PCM not supported")
    if ch > 1:
        x = [sum(x[i:i + ch]) / ch for i in range(0, len(x), ch)]
    return sr, x


def centroid(seg, sr):
    n = len(seg)
    hann = [0.5 - 0.5 * math.cos(2 * math.pi * i / (n - 1)) for i in range(n)]
    s = [a * b for a, b in zip(seg, hann)]
    num = den = 0.0
    for k in range(1, n // 2, 2):  # every 2nd bin is plenty for a rough centroid
        w = cmath.exp(-2j * math.pi * k / n)
        acc, z = 0j, 1 + 0j
        for v in s:
            acc += v * z
            z *= w
        m = abs(acc)
        num += m * k * sr / n
        den += m
    return num / den if den else 0.0


def db(v):
    return 20 * math.log10(v) if v > 0 else -120


def audible(x, sr, below_db=-20.0, win=0.02):
    """Seconds until the short-term RMS last sits within below_db of its loudest window (same
    rule as make_sfx.audible -> mixer.AUDIBLE)."""
    n = max(1, int(sr * win))
    rms = [math.sqrt(sum(v * v for v in x[i:i + n]) / n) for i in range(0, len(x), n)]
    top = max(rms, default=0.0)
    if top <= 0:
        return 0.0, 0.0
    thr = top * 10 ** (below_db / 20.0)
    last = max(i for i, v in enumerate(rms) if v >= thr)
    return (last + 1) * n / sr, top


def band_shares(x, sr, lo=250.0, hi=4000.0):
    """(share of energy below lo Hz, share above hi Hz), via one-pole filters."""
    a_lo = math.exp(-2 * math.pi * lo / sr)
    a_hi = math.exp(-2 * math.pi * hi / sr)
    y_lo = y_hi = 0.0
    e_lo = e_hi = e = 0.0
    for v in x:
        y_lo = (1 - a_lo) * v + a_lo * y_lo
        y_hi = (1 - a_hi) * v + a_hi * y_hi
        h = v - y_hi
        e += v * v
        e_lo += y_lo * y_lo
        e_hi += h * h
    return (e_lo / e, e_hi / e) if e else (0.0, 0.0)


def loudness(x, sr):
    """RMS dBFS over the audible part (what normalize matches between sounds)."""
    aud, _ = audible(x, sr)
    seg = x[: max(1, int(aud * sr))]
    return db(math.sqrt(sum(v * v for v in seg) / len(seg)))


def pack_scan(root):
    rows = []
    for p in sorted(root.rglob("*.wav")):
        sr, x = load(p)
        aud, _ = audible(x, sr)
        lo, hi = band_shares(x, sr)
        rows.append((p.parent.name, p.stem, len(x) / sr, aud, db(max(abs(v) for v in x)),
                     loudness(x, sr), lo, hi))
    print(f"{'folder':12s} {'name':22s} {'len':>5s} {'aud':>5s} {'peak':>6s} {'loud':>6s} "
          f"{'low':>5s} {'high':>5s} {'bass':>6s}")
    for f, n, d, a, pk, ld, lo, hi in rows:
        print(f"{f:12s} {n:22s} {d:5.2f} {a:5.2f} {pk:6.1f} {ld:6.1f} {lo:5.2f} {hi:5.2f} "
              f"{lo - hi:+6.2f}")
    print(f"{len(rows)} files")


def full_report(folder):
    total = 0
    for p in sorted(folder.glob("*.wav")):
        sr, x = load(p)
        total += p.stat().st_size
        pk = max(abs(v) for v in x)
        rms = math.sqrt(sum(v * v for v in x) / len(x))
        clip = sum(1 for v in x if abs(v) > 0.999)
        # active region: until the envelope falls 30 dB below peak
        thr = pk * 10 ** (-30 / 20)
        last = max(i for i, v in enumerate(x) if abs(v) > thr)
        pts = []
        for frac in (0.08, 0.3, 0.55, 0.85):
            c = int(last * frac)
            seg = x[max(0, c - WIN // 2): max(0, c - WIN // 2) + WIN]
            if len(seg) < WIN:
                seg = seg + [0.0] * (WIN - len(seg))
            e = math.sqrt(sum(v * v for v in seg) / WIN)
            pts.append(f"{centroid(seg, sr):5.0f}" if e > pk * 0.01 else "   --")
        print(f"{p.stem:15s} {len(x)/sr*1000:6.0f} ms (active {last/sr*1000:5.0f})  "
              f"peak {db(pk):6.1f}  rms {db(rms):6.1f}  loud {loudness(x, sr):6.1f}  "
              f"clip {clip}  centroid Hz: {' '.join(pts)}")
    print(f"total {total/1024:.0f} KB")


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--pack":
        pack_scan(Path(args[1]) if len(args) > 1 else PACK)
    else:
        full_report(Path(args[0]) if args else SFX)
