"""Synthesize the app's UI sound effects (original sounds, PC-only tool, stdlib only).

    .venv/Scripts/python tools/sfx/make_sfx.py            # all sounds
    .venv/Scripts/python tools/sfx/make_sfx.py tab_open   # only names starting so

Style: airy, glassy, calm "Arcane system" - filtered-noise whooshes, inharmonic glass/bell
partials, soft FM pings, short Schroeder reverb tails, and (v1.3) a deep, gently saturated
low body under the reward sounds, modelled on skill_acquired. Everything is synthesized here; nothing
is sampled. Each sound has its own fixed random seed, so regenerating gives identical files.

Output: mono 16-bit WAV, 44.1 kHz, in src/assets/sfx/<name>.wav, peak-normalized per sound
(see PEAK_DB in SOUNDS). The sound recipes are the functions below `# --- sounds`.
"""

from __future__ import annotations

import math
import random
import struct
import sys
import wave
import zlib
from collections.abc import Callable, Sequence
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = ROOT / "src" / "assets" / "sfx"
# Sounds now made from the Sci-Fi pack (everything but SHIPPED) go here instead, for auditioning the
# old synth versions; they must never overwrite the shipped pack-based files.
SYNTH_OUT = HERE / "synth_out"
SHIPPED = frozenset({"level_up", "skill_acquired", "milestone", "lumen_hum"})
SR = 44100
TAU = 2.0 * math.pi

Sig = list[float]


# ============================================================== primitives
def n_samples(dur: float) -> int:
    return max(1, round(dur * SR))


def silence(dur: float) -> Sig:
    return [0.0] * n_samples(dur)


def add(dst: Sig, src: Sequence[float], at: float = 0.0, gain: float = 1.0) -> Sig:
    """Mix src into dst starting at `at` seconds (dst grows if needed)."""
    o = n_samples(at) if at > 0 else 0
    need = o + len(src)
    if need > len(dst):
        dst.extend([0.0] * (need - len(dst)))
    for i, s in enumerate(src):
        dst[o + i] += s * gain
    return dst


def mul(a: Sequence[float], b: Sequence[float]) -> Sig:
    return [x * y for x, y in zip(a, b, strict=False)]


def scale(a: Sequence[float], g: float) -> Sig:
    return [x * g for x in a]


def noise(dur: float, rng: random.Random) -> Sig:
    return [rng.uniform(-1.0, 1.0) for _ in range(n_samples(dur))]


def exp_glide(f0: float, f1: float, dur: float) -> Callable[[float], float]:
    """Exponential pitch sweep f0 -> f1 over dur seconds (holds f1 after)."""
    if f0 == f1 or dur <= 0:
        return lambda t: f0
    k = math.log(f1 / f0) / dur
    return lambda t: f0 * math.exp(k * min(t, dur))


def ease_glide(f0: float, f1: float, dur: float) -> Callable[[float], float]:
    """Smooth (ease-out) exponential glide - fast at first, settling into f1."""
    r = math.log(f1 / f0)

    def f(t: float) -> float:
        x = min(1.0, t / dur) if dur > 0 else 1.0
        return f0 * math.exp(r * (1.0 - (1.0 - x) ** 3))

    return f


# ---- envelopes
def env_ad(dur: float, attack: float, tau: float) -> Sig:
    """Smooth (sin^2) attack, then exponential decay with time constant tau."""
    out, na = [], max(1, n_samples(attack))
    for i in range(n_samples(dur)):
        if i < na:
            out.append(math.sin(0.5 * math.pi * i / na) ** 2)
        else:
            out.append(math.exp(-(i - na) / (tau * SR)))
    return out


def env_swell(dur: float, peak: float, rise_pow: float, tau: float) -> Sig:
    """Rise along x^rise_pow to 1.0 at fraction `peak` of dur, then exponential decay."""
    out, n = [], n_samples(dur)
    npk = max(1, int(n * peak))
    for i in range(n):
        if i < npk:
            out.append((i / npk) ** rise_pow)
        else:
            out.append(math.exp(-(i - npk) / (tau * SR)))
    return out


def env_adsr(dur: float, a: float, d: float, s: float, r: float) -> Sig:
    """Classic ADSR; release starts at dur - r."""
    out, n = [], n_samples(dur)
    na, nd, nr = n_samples(a), n_samples(d), n_samples(r)
    rel_at = n - nr
    for i in range(n):
        if i < na:
            v = math.sin(0.5 * math.pi * i / na) ** 2
        elif i < na + nd:
            v = 1.0 - (1.0 - s) * (i - na) / nd
        else:
            v = s
        if i >= rel_at:
            v *= math.exp(-5.0 * (i - rel_at) / max(1, nr))
        out.append(v)
    return out


# ---- oscillators
def osc(dur: float, freq: Callable[[float], float] | float, partials=((1.0, 1.0),),
        phase: float = 0.0) -> Sig:
    """Additive oscillator: sum of sine partials (ratio, gain) over a (possibly moving) pitch."""
    fn = freq if callable(freq) else (lambda t, f=freq: f)
    phases = [phase] * len(partials)
    out = []
    for i in range(n_samples(dur)):
        f = fn(i / SR)
        s = 0.0
        for k, (ratio, g) in enumerate(partials):
            fr = f * ratio
            if fr < SR * 0.45:
                s += g * math.sin(phases[k])
            phases[k] += TAU * fr / SR
        out.append(s)
    return out


def bell(dur: float, f: float, partials: Sequence[tuple[float, float, float]],
         attack: float = 0.002, bend: float = 0.0, detune: float = 0.0) -> Sig:
    """Inharmonic bell/glass tone: partials (ratio, gain, decay_tau_s), each decaying on its own.
    bend: pitch starts this fraction sharp and settles within ~25 ms. detune: Hz of beating."""
    out = [0.0] * n_samples(dur)
    na = max(1, n_samples(attack))
    for ratio, g, tau in partials:
        for pair, dg in ((0.0, 1.0), (detune, 0.5)) if detune else ((0.0, 1.0),):
            ph, fr0 = 0.0, f * ratio + pair
            if fr0 >= SR * 0.45:
                continue
            for i in range(len(out)):
                t = i / SR
                a = math.exp(-t / tau) * (math.sin(0.5 * math.pi * i / na) ** 2 if i < na else 1)
                if a < 1e-5 and i > na:
                    break
                out[i] += g * dg * a * math.sin(ph)
                ph += TAU * fr0 * (1.0 + bend * math.exp(-t / 0.008)) / SR
    return out


def fm_ping(dur: float, fc: float, ratio: float, index: float, tau: float,
            index_tau: float | None = None, attack: float = 0.0015) -> Sig:
    """2-operator FM ping: bright metallic start (index decays fast) into a pure sine tail."""
    itau = index_tau if index_tau is not None else tau * 0.25
    fm = fc * ratio
    out, pc, pm = [], 0.0, 0.0
    na = max(1, n_samples(attack))
    for i in range(n_samples(dur)):
        t = i / SR
        a = math.exp(-t / tau) * (math.sin(0.5 * math.pi * i / na) ** 2 if i < na else 1.0)
        out.append(a * math.sin(pc + index * math.exp(-t / itau) * math.sin(pm)))
        pc += TAU * fc / SR
        pm += TAU * fm / SR
    return out


# ---- filters
def lowpass(x: Sequence[float], fc: float) -> Sig:
    """One-pole lowpass (6 dB/oct)."""
    a = 1.0 - math.exp(-TAU * fc / SR)
    y, out = 0.0, []
    for s in x:
        y += a * (s - y)
        out.append(y)
    return out


def highpass(x: Sequence[float], fc: float) -> Sig:
    """One-pole highpass (input minus its lowpass)."""
    return [s - lp for s, lp in zip(x, lowpass(x, fc), strict=True)]


def bandpass_sweep(x: Sequence[float], f: Callable[[float], float] | float, q: float) -> Sig:
    """RBJ biquad bandpass (0 dB peak) whose center frequency follows f(t); coefficients are
    recomputed every 16 samples."""
    fn = f if callable(f) else (lambda t, v=f: v)
    out = []
    x1 = x2 = y1 = y2 = 0.0
    b0 = b2 = a1 = a2 = 0.0
    for i, s in enumerate(x):
        if i % 16 == 0:
            fc = min(max(fn(i / SR), 20.0), SR * 0.45)
            w0 = TAU * fc / SR
            alpha = math.sin(w0) / (2.0 * q)
            a0 = 1.0 + alpha
            b0, b2 = alpha / a0, -alpha / a0
            a1, a2 = -2.0 * math.cos(w0) / a0, (1.0 - alpha) / a0
        y = b0 * s + b2 * x2 - a1 * y1 - a2 * y2
        x2, x1, y2, y1 = x1, s, y1, y
        out.append(y)
    return out


def tremolo(x: Sequence[float], rate: float, depth: float, phase: float = 0.0) -> Sig:
    return [s * (1.0 - depth * 0.5 * (1.0 + math.sin(TAU * rate * i / SR + phase)))
            for i, s in enumerate(x)]


def reverb(x: Sequence[float], size: float = 1.0, decay: float = 0.8, damp: float = 0.35,
           wet: float = 0.25, tail: float = 0.5) -> Sig:
    """Small mono Schroeder/Freeverb-style reverb: 6 damped feedback combs in parallel, then 3
    allpasses. Appends `tail` seconds so the decay is not cut off. Returns dry + wet."""
    src = list(x) + [0.0] * n_samples(tail)
    acc = [0.0] * len(src)
    for d in (1557, 1617, 1491, 1422, 1277, 1356):
        dl = max(8, int(d * size * SR / 44100))
        buf, idx, lp = [0.0] * dl, 0, 0.0
        for i, s in enumerate(src):
            y = buf[idx]
            lp = y * (1.0 - damp) + lp * damp
            buf[idx] = s + lp * decay
            idx = idx + 1 if idx + 1 < dl else 0
            acc[i] += y
    w = [v / 6.0 for v in acc]
    for d in (556, 441, 341):
        dl = max(4, int(d * size * SR / 44100))
        buf, idx, out = [0.0] * dl, 0, []
        for s in w:
            b = buf[idx]
            out.append(b - s)
            buf[idx] = s + b * 0.5
            idx = idx + 1 if idx + 1 < dl else 0
        w = out
    return [d + wet * v for d, v in zip(src, w, strict=True)]


def saw(dur: float, freq: Callable[[float], float] | float, phase: float = 0.0) -> Sig:
    """Plain sawtooth (-1..1). Only used under a steep lowpass, so aliasing stays inaudible."""
    fn = freq if callable(freq) else (lambda t, f=freq: f)
    ph, out = phase % 1.0, []
    for i in range(n_samples(dur)):
        out.append(2.0 * ph - 1.0)
        ph += fn(i / SR) / SR
        ph -= math.floor(ph)
    return out


def lowpass_sweep(x: Sequence[float], f: Callable[[float], float], q: float = 0.707) -> Sig:
    """RBJ biquad lowpass (12 dB/oct, resonance q) whose cutoff follows f(t); coefficients are
    recomputed every 16 samples (the 'slowly opening filter' of the Luma hum)."""
    out = []
    x1 = x2 = y1 = y2 = 0.0
    b0 = b1 = b2 = a1 = a2 = 0.0
    for i, s in enumerate(x):
        if i % 16 == 0:
            fc = min(max(f(i / SR), 20.0), SR * 0.45)
            w0 = TAU * fc / SR
            cw, alpha = math.cos(w0), math.sin(w0) / (2.0 * q)
            a0 = 1.0 + alpha
            b0 = b2 = (1.0 - cw) / 2.0 / a0
            b1 = (1.0 - cw) / a0
            a1, a2 = -2.0 * cw / a0, (1.0 - alpha) / a0
        y = b0 * s + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        x2, x1, y2, y1 = x1, s, y1, y
        out.append(y)
    return out


# ---- finishing
def soft_limit(x: Sequence[float], drive: float = 1.3) -> Sig:
    """Normalize to 1.0 then tanh-saturate gently, so peaks round off instead of clipping."""
    pk = max((abs(v) for v in x), default=0.0) or 1.0
    k = math.tanh(drive)
    return [math.tanh(drive * v / pk) / k for v in x]


def finish(x: Sequence[float], peak_db: float, fade_ms: float = 25.0,
           floor_db: float = -54.0) -> Sig:
    """Soft-limit, trim the tail where it falls below floor_db (relative to the peak), fade
    in/out, normalize the peak to peak_db dBFS."""
    y = soft_limit(x)
    floor = 10 ** (floor_db / 20.0)
    end = len(y)
    while end > 1 and abs(y[end - 1]) < floor:
        end -= 1
    y = y[: end + n_samples(0.005)]
    nf = min(len(y) // 3, n_samples(fade_ms / 1000.0))
    for i in range(nf):  # cosine fade-out
        y[len(y) - nf + i] *= 0.5 * (1.0 + math.cos(math.pi * (i + 1) / nf))
    ni = min(len(y), n_samples(0.0008))
    for i in range(ni):
        y[i] *= i / ni
    pk = max((abs(v) for v in y), default=0.0) or 1.0
    g = 10 ** (peak_db / 20.0) / pk
    return [v * g for v in y]


def write_wav(path: Path, x: Sequence[float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = b"".join(struct.pack("<h", max(-32767, min(32767, round(v * 32767)))) for v in x)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(data)


# ============================================================== building blocks
GLASS = ((1.0, 1.0, 0.030), (2.32, 0.45, 0.014), (4.25, 0.22, 0.007), (6.73, 0.10, 0.004))
CRYSTAL = ((1.0, 1.0, 0.42), (2.76, 0.28, 0.16), (5.40, 0.11, 0.07), (8.93, 0.05, 0.03))
SOFT_BELL = ((1.0, 1.0, 0.22), (2.0, 0.18, 0.12), (3.0, 0.06, 0.06))
RISSET = ((0.56, 0.55, 0.95), (0.92, 0.40, 0.60), (1.0, 1.0, 0.62), (1.19, 0.45, 0.42),
          (1.56, 0.30, 0.32), (2.0, 0.35, 0.28), (2.74, 0.18, 0.18), (3.0, 0.14, 0.14),
          (4.07, 0.08, 0.09))


def glass_click(f: float, rng: random.Random, dur: float = 0.09, bright: float = 1.0) -> Sig:
    """Glassy click: inharmonic glass partials + a short FM tick + a 2 ms air transient."""
    body = bell(dur, f, GLASS, attack=0.0006, bend=0.015)
    add(body, fm_ping(dur, f * 1.5, 3.5, 1.6 * bright, 0.006), 0, 0.35)
    trans = highpass(noise(0.003, rng), 3500)
    add(body, mul(trans, env_ad(0.003, 0.0003, 0.0008)), 0, 0.5 * bright)
    return body


def crystal(f: float, dur: float, tau_scale: float = 1.0, fm: float = 0.35,
            attack: float = 0.0015) -> Sig:
    """Crystal chime note: CRYSTAL bell partials plus a soft FM sparkle on the attack.
    A longer `attack` (4-12 ms) rounds the strike off (less 'chip', more glass)."""
    parts = [(r, g, t * tau_scale) for r, g, t in CRYSTAL]
    x = bell(dur, f, parts, attack=attack, bend=0.004, detune=1.3)
    add(x, fm_ping(dur, f, 3.0, 1.3, 0.05 * tau_scale, 0.012), 0, fm)
    return x


def whoosh(dur: float, f0: float, f1: float, q: float, peak: float, rise_pow: float,
           tau: float, rng: random.Random) -> Sig:
    """Airy whoosh: white noise through a sweeping bandpass, shaped by a swell envelope."""
    sweep = exp_glide(f0, f1, dur * peak + tau * 2)
    x = bandpass_sweep(noise(dur, rng), sweep, q)
    return mul(x, env_swell(dur, peak, rise_pow, tau))


def shimmer(dur: float, center: Callable[[float], float], rng: random.Random, voices: int = 10,
            spread: Sequence[float] = (1.0, 1.5, 2.0, 2.5, 3.0, 4.0), depth: float = 0.85,
            rates: tuple[float, float] = (7.0, 21.0)) -> Sig:
    """Shimmer: a cloud of detuned sines around a (moving) center, each with its own
    tremolo, so it sparkles instead of droning. Lower depth/rates = smoother, less 'chip'."""
    out = [0.0] * n_samples(dur)
    for _ in range(voices):
        ratio = rng.choice(spread) * (1.0 + rng.uniform(-0.012, 0.012))
        rate, ph0 = rng.uniform(*rates), rng.uniform(0, TAU)
        tone = osc(dur, lambda t, r=ratio: center(t) * r, phase=rng.uniform(0, TAU))
        add(out, tremolo(tone, rate, depth, ph0), 0, 1.0 / voices)
    return out


def sparkle_grains(span: tuple[float, float], count: int, freqs: Sequence[float],
                   rng: random.Random, gain: float = 1.0, tau: float = 0.08,
                   fade: bool = True) -> Sig:
    """Scattered tiny glass pings (the 'rune' twinkle) at random times inside span."""
    out = silence(span[1])
    t0, t1 = span
    for _ in range(count):
        at = rng.uniform(t0, t1)
        f = rng.choice(freqs) * (1.0 + rng.uniform(-0.003, 0.003))
        g = gain * rng.uniform(0.45, 1.0)
        if fade:
            g *= 1.0 - 0.6 * (at - t0) / max(1e-6, t1 - t0)
        ping = fm_ping(tau * 5, f, rng.choice((2.0, 3.0, 3.5)), rng.uniform(0.6, 1.4), tau)
        add(out, ping, at, g)
    return out


# ---- low end ("body"): the skill_acquired recipe, shared by every reward sound
def low_body(dur: float, f: float, attack: float, tau: float, glide_from: float | None = None,
             glide_to: float | None = None, drive: float = 1.8, fifth: bool = False) -> Sig:
    """Deep, warm tone: a sine with soft 2nd/3rd harmonics (+ optional fifth), gently tanh-
    saturated so its harmonics (~120-250 Hz) still read on phone speakers, lowpassed, with a
    soft attack and exponential decay. glide_from: starts there and settles on f (a 'boom');
    glide_to: drifts from f to it over dur."""
    if glide_from:
        fr = exp_glide(glide_from, f, 0.3)
    elif glide_to:
        fr = exp_glide(f, glide_to, dur)
    else:
        fr = exp_glide(f, f, dur)
    parts = ((1, 1), (2, 0.3), (3, 0.1), (1.5, 0.22)) if fifth else ((1, 1), (2, 0.3), (3, 0.1))
    x = osc(dur, fr, parts)
    k = math.tanh(drive)
    x = lowpass([math.tanh(drive * v / 1.4) / k for v in x], 700)
    return mul(x, env_ad(dur, attack, tau))


def hum(dur: float, f: float, attack: float, tau: float, drive: float = 1.8,
        fifth: bool = False, glide_to: float | None = None) -> Sig:
    """Sustained 'hmm' body under a sound (a low_body with a slower attack/decay)."""
    return low_body(dur, f, attack, tau, glide_to=glide_to, drive=drive, fifth=fifth)


def impact(dst: Sig, at: float, f: float, rng: random.Random, gain: float,
           glide_from: float, tau: float = 0.22) -> Sig:
    """skill_acquired's soft impact: a saturated downward boom settling on f + a lowpassed
    noise thump, mixed into dst at `at` seconds."""
    add(dst, low_body(tau * 3.2, f, 0.004, tau, glide_from=glide_from, drive=1.5), at, gain)
    thump = mul(lowpass(lowpass(noise(0.2, rng), 380), 380), env_ad(0.2, 0.002, 0.045))
    return add(dst, thump, at, gain * 1.85)


def note(name: str) -> float:
    """'A4' / 'C#6' -> Hz (equal temperament, A4 = 440)."""
    names = {"C": -9, "D": -7, "E": -5, "F": -4, "G": -2, "A": 0, "B": 2}
    semis = names[name[0]]
    rest = name[1:]
    if rest.startswith("#"):
        semis, rest = semis + 1, rest[1:]
    elif rest.startswith("b"):
        semis, rest = semis - 1, rest[1:]
    return 440.0 * 2 ** ((semis + 12 * (int(rest) - 4)) / 12)


# ============================================================== sounds
# Each recipe gets its own seeded Random and returns the raw (un-normalized) signal.
# v1.3: every reward sound carries the same deep body as skill_acquired (a gently saturated
# low sine that glides down + a lowpassed noise thump + a soft sustained hum) and the same
# big-room reverb. Tones avoid bare blips and hard-stepped arpeggios: notes are strummed with
# soft attacks and gentle detune, so nothing reads as chiptune.

def s_tab_open(r: random.Random) -> Sig:
    """Rising airy sweep that lands on a glassy click, with a faint low 'whoomp' under it."""
    out = whoosh(0.30, 650, 5200, 1.3, peak=0.62, rise_pow=1.8, tau=0.045, rng=r)
    glide = osc(0.30, exp_glide(900, 1900, 0.19), ((1, 1), (2, 0.25)))
    add(out, mul(glide, env_swell(0.30, 0.62, 2.2, 0.03)), 0, 0.10)
    add(out, glass_click(2960, r), 0.178, 0.55)
    add(out, low_body(0.28, 82, attack=0.06, tau=0.07, glide_from=62, drive=1.6), 0.09, 0.18)
    return reverb(out, size=0.55, decay=0.70, damp=0.45, wet=0.20, tail=0.12)


def s_tab_close(r: random.Random) -> Sig:
    """Mirror of tab_open: a slightly darker click first, then a falling sweep and whoomp."""
    out = silence(0.30)
    add(out, glass_click(2350, r, bright=0.7), 0.004, 0.55)
    air = whoosh(0.28, 4200, 520, 1.2, peak=0.12, rise_pow=1.2, tau=0.075, rng=r)
    add(out, air, 0.012, 1.0)
    glide = osc(0.26, exp_glide(1700, 760, 0.18), ((1, 1), (2, 0.2)))
    add(out, mul(glide, env_ad(0.26, 0.02, 0.06)), 0.012, 0.09)
    add(out, low_body(0.26, 62, attack=0.02, tau=0.07, glide_from=90, drive=1.6), 0.01, 0.16)
    out = lowpass(out, 7000)
    return reverb(out, size=0.55, decay=0.68, damp=0.55, wet=0.18, tail=0.12)


def s_tap(r: random.Random) -> Sig:
    """Tiny soft tick."""
    x = bell(0.045, 1900, ((1.0, 1.0, 0.007), (2.7, 0.3, 0.003)), attack=0.0005)
    t = mul(highpass(noise(0.004, r), 3000), env_ad(0.004, 0.0002, 0.0009))
    return add(x, t, 0, 0.3)


def s_toggle(r: random.Random) -> Sig:
    """Two soft glassy taps up a fifth (rounded attacks, slight detune - no bare blips)."""
    def blip(f: float, d: float) -> Sig:
        x = bell(d, f, ((1.0, 1.0, 0.016), (2.0, 0.12, 0.008)), attack=0.003, detune=1.5)
        return lowpass(x, 5000)
    out = blip(1050, 0.06)
    add(out, blip(1575, 0.07), 0.052, 0.9)
    add(out, mul(highpass(noise(0.003, r), 4000), env_ad(0.003, 0.0002, 0.0008)), 0, 0.10)
    return reverb(out, size=0.4, decay=0.6, damp=0.5, wet=0.1, tail=0.04)


def s_sheet_open(r: random.Random) -> Sig:
    """Soft upward whoosh, no click."""
    out = whoosh(0.34, 340, 2500, 0.8, peak=0.70, rise_pow=1.6, tau=0.05, rng=r)
    body = osc(0.34, exp_glide(170, 260, 0.24))
    add(out, mul(body, env_swell(0.34, 0.7, 1.8, 0.04)), 0, 0.14)
    out = lowpass(lowpass(out, 4200), 6000)  # softer, less hiss than the tab sweeps
    return reverb(out, size=0.6, decay=0.66, damp=0.6, wet=0.14, tail=0.1)


def s_sheet_close(r: random.Random) -> Sig:
    """Soft downward whoosh, a touch shorter."""
    out = whoosh(0.30, 2500, 340, 0.8, peak=0.22, rise_pow=1.3, tau=0.07, rng=r)
    body = osc(0.30, exp_glide(260, 165, 0.2))
    add(out, mul(body, env_swell(0.30, 0.22, 1.3, 0.06)), 0, 0.12)
    out = lowpass(lowpass(out, 4200), 6000)
    return reverb(out, size=0.6, decay=0.64, damp=0.65, wet=0.12, tail=0.1)


def s_quest_done(r: random.Random) -> Sig:
    """Crystal chime E6 B6 E7 strummed softly over a deep E body (skill_acquired-style)."""
    out = silence(1.0)
    impact(out, 0.0, 82.4, r, gain=0.95, glide_from=130, tau=0.24)
    add(out, hum(0.95, 82.4, attack=0.09, tau=0.42), 0.0, 0.38)
    for i, (n, g) in enumerate((("E6", 0.75), ("B6", 0.7), ("E7", 0.62))):
        add(out, crystal(note(n), 0.9, tau_scale=0.75 + 0.3 * i, fm=0.18, attack=0.004),
            0.02 + 0.06 * i, g)
    add(out, sparkle_grains((0.16, 0.5), 5, [note(n) for n in ("B7", "E8", "G#7")], r,
                            gain=0.08, tau=0.03), 0, 1.0)
    return reverb(out, size=1.0, decay=0.82, damp=0.42, wet=0.32, tail=0.55)


def s_coin(r: random.Random) -> Sig:
    """Soft glassy coin sparkle: two detuned bell pings + a few airy twinkles, faint low tick."""
    out = silence(0.42)
    add(out, bell(0.32, note("D7"), CRYSTAL, attack=0.002, detune=2.0), 0, 0.5)
    add(out, fm_ping(0.3, note("D7"), 2.0, 0.7, 0.05, 0.012, attack=0.002), 0, 0.15)
    add(out, bell(0.4, note("A7"), CRYSTAL, attack=0.002, detune=2.4), 0.06, 0.55)
    add(out, sparkle_grains((0.07, 0.26), 5, [4200, 5200, 6100], r, gain=0.09,
                            tau=0.02), 0, 1.0)
    add(out, low_body(0.18, 147, attack=0.004, tau=0.05, glide_from=220, drive=1.5), 0, 0.28)
    out = lowpass(out, 9000)
    return reverb(out, size=0.75, decay=0.76, damp=0.4, wet=0.2, tail=0.25)


def s_xp_fill(r: random.Random) -> Sig:
    """Soft rising shimmer, ~0.6 s, over a quiet rising hum (sits under Luma's voice)."""
    d = 0.6
    sh = shimmer(d, exp_glide(700, 1450, d), r, voices=12, depth=0.45, rates=(4.0, 9.0))
    out = mul(sh, env_swell(d, 0.86, 1.5, 0.05))
    air = whoosh(d, 2200, 6500, 1.6, peak=0.86, rise_pow=2.0, tau=0.05, rng=r)
    add(out, air, 0, 0.32)
    rise = mul(hum(d, 110, attack=0.02, tau=9.0, glide_to=165), env_swell(d, 0.8, 1.6, 0.06))
    add(out, rise, 0, 0.3)
    out = lowpass(out, 9000)
    return reverb(out, size=0.85, decay=0.78, damp=0.45, wet=0.26, tail=0.3)


def s_level_up(r: random.Random) -> Sig:
    """Soft rising C-major strum (C5 E5 G5 C6 E6 swelling in, not stepped) over a deep C body,
    blooming into a shimmer."""
    out = silence(1.3)
    impact(out, 0.0, 65.4, r, gain=0.75, glide_from=110, tau=0.28)
    add(out, hum(1.25, 65.4, attack=0.12, tau=0.6, fifth=True), 0, 0.32)
    arp = ("C5", "E5", "G5", "C6", "E6")
    for i, n in enumerate(arp):
        last = i == len(arp) - 1
        add(out, crystal(note(n), 1.15 if last else 0.75, tau_scale=1.3 if last else 0.75,
                         fm=0.15, attack=0.012), 0.02 + 0.065 * i, 0.42 + 0.06 * i)
    sh = mul(shimmer(0.9, exp_glide(1800, 2600, 0.9), r, voices=10, depth=0.55),
             env_swell(0.9, 0.45, 1.4, 0.2))
    add(out, sh, 0.25, 0.24)
    add(out, sparkle_grains((0.4, 1.0), 8, [note(n) for n in ("C8", "G7", "E8", "D8")], r,
                            gain=0.07, tau=0.035), 0, 1.0)
    return reverb(out, size=1.1, decay=0.85, damp=0.42, wet=0.34, tail=0.6)


def s_skill_acquired(r: random.Random) -> Sig:
    """The reference: deep soft impact, then a bright crystal sparkle in a big (quiet) reverb.
    v1.3 adds a gently saturated sustained A hum under it ('hmm' body on phone speakers)."""
    out = silence(1.5)
    boom = mul(osc(0.7, exp_glide(110, 44, 0.3), ((1, 1), (2, 0.3), (3, 0.08))),
               env_ad(0.7, 0.004, 0.22))
    add(out, boom, 0, 0.75)
    thump = mul(lowpass(lowpass(noise(0.2, r), 380), 380), env_ad(0.2, 0.002, 0.045))
    add(out, thump, 0, 1.4)
    add(out, hum(1.3, 55.0, attack=0.1, tau=0.55, fifth=True), 0.02, 0.24)
    for i, n in enumerate(("A6", "E7", "A7")):
        add(out, crystal(note(n), 1.2, tau_scale=1.1), 0.09 + 0.03 * i, 0.32)
    sh = mul(shimmer(1.0, exp_glide(2200, 3000, 1.0), r, voices=10),
             env_swell(1.0, 0.25, 1.2, 0.3))
    add(out, sh, 0.1, 0.2)
    add(out, sparkle_grains((0.15, 0.95), 12, [note(n) for n in ("A7", "B7", "C#8", "E8")],
                            r, gain=0.09, tau=0.04), 0, 1.0)
    return reverb(out, size=1.1, decay=0.87, damp=0.42, wet=0.38, tail=0.8)


def s_milestone(r: random.Random) -> Sig:
    """The big one: four tones gliding up into an A-major chord over a swelling A sub hum, a
    deep impact as they land, a crystal chord, and a long rune-like twinkle of glass grains."""
    out = silence(2.5)
    chord = ("A3", "E4", "A4", "C#5")
    for i, n in enumerate(chord):
        f = note(n)
        d = 2.0 - 0.1 * i
        tone = osc(d, ease_glide(f * 0.75, f, 0.85 - 0.08 * i),
                   ((1, 1), (2, 0.22), (3, 0.06)), phase=0.7 * i)
        tone = lowpass(tone, 2400)
        add(out, mul(tone, env_adsr(d, 0.55, 0.4, 0.55, 0.7)), 0.12 * i, 0.15)
    swell = mul(hum(2.4, 55.0, attack=0.02, tau=9.0, fifth=True),
                env_swell(2.4, 0.4, 1.6, 0.7))
    add(out, swell, 0.0, 0.3)
    land = 0.9
    impact(out, land, 55.0, r, gain=0.75, glide_from=110, tau=0.3)
    for i, n in enumerate(("A6", "C#7", "E7", "A7")):
        add(out, crystal(note(n), 1.4, tau_scale=1.4, fm=0.2), land + 0.025 * i, 0.22)
    sh = mul(shimmer(1.4, exp_glide(1760, 2640, 1.4), r, voices=14),
             env_swell(1.4, 0.35, 1.3, 0.35))
    add(out, sh, land - 0.25, 0.22)
    runes = [note(n) for n in ("A6", "B6", "C#7", "E7", "F#7", "A7", "B7", "C#8")]
    add(out, sparkle_grains((land + 0.05, 2.2), 26, runes, r, gain=0.1, tau=0.06), 0, 1.0)
    return reverb(out, size=1.25, decay=0.88, damp=0.42, wet=0.4, tail=1.0)


def s_notice(r: random.Random) -> Sig:
    """Gentle 'hmm' ping before Luma speaks: a soft air breath and low G hum, then a soft,
    detuned G6 glass ping (no pre-blip)."""
    out = mul(bandpass_sweep(noise(0.12, r), exp_glide(900, 2600, 0.1), 1.2),
              env_swell(0.12, 0.75, 1.6, 0.02))
    out = scale(out, 0.22)
    add(out, hum(0.5, 98.0, attack=0.035, tau=0.2), 0.0, 0.42)
    add(out, bell(0.5, note("G6"), ((1.0, 1.0, 0.16), (2.0, 0.12, 0.06), (3.01, 0.04, 0.03)),
                  attack=0.004, detune=1.6), 0.06, 0.8)
    add(out, fm_ping(0.3, note("G6"), 2.0, 0.6, 0.06, 0.015, attack=0.004), 0.06, 0.18)
    return reverb(out, size=0.85, decay=0.76, damp=0.48, wet=0.24, tail=0.3)


def s_alert_soft(r: random.Random) -> Sig:
    """Polite two-note 'ding-dong' (A5 -> F5), mellow bell partials over a soft low body."""
    out = silence(0.8)
    add(out, bell(0.6, note("A5"), SOFT_BELL, attack=0.008, detune=0.8), 0, 0.8)
    add(out, hum(0.4, note("A2"), attack=0.012, tau=0.12), 0, 0.5)
    add(out, bell(0.7, note("F5"), SOFT_BELL, attack=0.008, detune=0.8), 0.2, 0.85)
    add(out, hum(0.55, note("F2"), attack=0.012, tau=0.18), 0.2, 0.55)
    del r
    out = lowpass(out, 7000)
    return reverb(out, size=0.9, decay=0.78, damp=0.5, wet=0.24, tail=0.35)


def s_error_soft(r: random.Random) -> Sig:
    """Low muted double tap; lowpassed, nothing sharp."""
    def thud(f0: float, f1: float) -> Sig:
        x = mul(osc(0.12, exp_glide(f0, f1, 0.05), ((1, 1), (2, 0.3))),
                env_ad(0.12, 0.003, 0.03))
        add(x, mul(lowpass(noise(0.03, r), 600), env_ad(0.03, 0.001, 0.008)), 0, 0.25)
        return x
    out = thud(260, 225)
    add(out, thud(228, 196), 0.115, 0.85)
    out = lowpass(lowpass(out, 1600), 2400)
    return reverb(out, size=0.5, decay=0.6, damp=0.7, wet=0.1, tail=0.08)


def s_timer_tick(r: random.Random) -> Sig:
    """Very soft tick for a running timer."""
    x = mul(osc(0.025, 2200), env_ad(0.025, 0.0004, 0.004))
    nb = bandpass_sweep(noise(0.01, r), 5000, 2.0)
    return add(x, mul(nb, env_ad(0.01, 0.0002, 0.0018)), 0, 0.4)


def s_timer_done(r: random.Random) -> Sig:
    """Gentle Risset-style bell with a long soft tail, over a warm low E hum."""
    out = bell(2.2, note("E5"), RISSET, attack=0.006, detune=1.1)
    add(out, bell(1.6, note("B5"), RISSET[2:6], attack=0.008), 0.42, 0.18)
    add(out, hum(1.8, note("E2"), attack=0.06, tau=0.7, fifth=True), 0, 0.5)
    del r
    out = lowpass(out, 7500)
    return reverb(out, size=1.1, decay=0.86, damp=0.45, wet=0.3, tail=1.0)


def s_quest_clear(r: random.Random) -> Sig:
    """Short bright stinger for the QuestCleared flash: an airy upward flick, a soft bass
    thump, then a detuned B6/E7 glass pair and a few sparks."""
    out = mul(bandpass_sweep(noise(0.14, r), exp_glide(1200, 7000, 0.12), 1.4),
              env_swell(0.14, 0.85, 1.8, 0.02))
    out = scale(out, 0.35)
    impact(out, 0.1, 82.4, r, gain=0.9, glide_from=150, tau=0.13)
    add(out, crystal(note("B6"), 0.55, tau_scale=0.55, fm=0.2, attack=0.003), 0.105, 0.6)
    add(out, crystal(note("E7"), 0.6, tau_scale=0.65, fm=0.2, attack=0.003), 0.135, 0.6)
    add(out, sparkle_grains((0.15, 0.4), 6, [note(n) for n in ("E8", "B7", "G#7")], r,
                            gain=0.08, tau=0.025), 0, 1.0)
    return reverb(out, size=0.85, decay=0.76, damp=0.42, wet=0.26, tail=0.3)


def s_lumen_hum(r: random.Random) -> Sig:
    """Luma's thinking intro (original): a deep layered drone (detuned saws on D2 + a D1 sub
    + a soft A2 fifth) rising into pitch through a resonant lowpass that slowly opens, an airy
    whoosh building under it, then at ~1.2 s a crystalline shimmer bloom as the orb appears."""
    d = 2.05
    out = silence(d)
    root = note("D2")
    pitch = ease_glide(root * 0.94, root, 0.7)
    drone = silence(d)
    for k, (det, g) in enumerate(((1.0, 1.0), (1.0045, 0.85), (0.9958, 0.85), (2.003, 0.3))):
        add(drone, saw(d, lambda t, m=det: pitch(t) * m, phase=0.21 * k), 0, g)
    add(drone, saw(d, lambda t: pitch(t) * 1.4983, phase=0.5), 0, 0.28)  # the fifth (A2)

    def cutoff(t: float) -> float:  # opens 110 Hz -> ~1.5 kHz by 1.35 s, then eases back
        return (110.0 * 14.0 ** (min(1.0, t / 1.35) ** 1.6)
                * (1.0 - 0.45 * max(0.0, t - 1.35) / 0.7))
    drone = lowpass_sweep(drone, cutoff, q=1.6)
    drone = tremolo(drone, 0.55, 0.18)
    add(out, mul(drone, env_adsr(d, 0.55, 0.3, 0.8, 0.6)), 0, 0.42)
    sub = mul(hum(d, root / 2, attack=0.02, tau=9.0, drive=1.4),
              env_adsr(d, 0.7, 0.2, 0.9, 0.7))
    add(out, sub, 0, 0.55)
    air = whoosh(1.5, 260, 3200, 0.9, peak=0.78, rise_pow=2.0, tau=0.18, rng=r)
    add(out, lowpass(air, 5000), 0.0, 0.32)
    bloom = 1.2
    for i, n in enumerate(("D6", "A6", "D7", "E7")):
        add(out, crystal(note(n), 0.85, tau_scale=1.2, fm=0.15, attack=0.01),
            bloom + 0.03 * i, 0.16)
    sh = mul(shimmer(0.85, exp_glide(1760, 2350, 0.85), r, voices=12, depth=0.6),
             env_swell(0.85, 0.3, 1.4, 0.25))
    add(out, sh, bloom - 0.08, 0.18)
    add(out, sparkle_grains((bloom + 0.05, 1.95), 10, [note(n) for n in ("D8", "A7", "E8")],
                            r, gain=0.06, tau=0.04), 0, 1.0)
    return reverb(out, size=1.25, decay=0.86, damp=0.45, wet=0.36, tail=0.45)


# name -> (recipe, peak dBFS). UI clicks sit far below the reward sounds.
SOUNDS: dict[str, tuple[Callable[[random.Random], Sig], float]] = {
    "tab_open": (s_tab_open, -9.0),
    "tab_close": (s_tab_close, -9.5),
    "tap": (s_tap, -14.0),
    "toggle": (s_toggle, -12.0),
    "sheet_open": (s_sheet_open, -12.0),
    "sheet_close": (s_sheet_close, -13.0),
    "quest_done": (s_quest_done, -3.0),
    "coin": (s_coin, -7.0),
    "xp_fill": (s_xp_fill, -9.0),
    "level_up": (s_level_up, -3.0),
    "skill_acquired": (s_skill_acquired, -4.0),
    "milestone": (s_milestone, -3.0),
    "notice": (s_notice, -8.0),
    "alert_soft": (s_alert_soft, -6.0),
    "error_soft": (s_error_soft, -10.0),
    "timer_tick": (s_timer_tick, -22.0),
    "timer_done": (s_timer_done, -4.0),
    "quest_clear": (s_quest_clear, -4.5),
    "lumen_hum": (s_lumen_hum, -3.5),
}


def audible(x: Sequence[float], below_db: float = -20.0, win: float = 0.02) -> float:
    """Seconds until the sound's short-term RMS last sits within below_db of its loudest window
    (the part a voice would collide with; the reverb tail after it is quiet enough to talk
    over). This is the AUDIBLE table in src/lol/ui/mixer.py."""
    n = n_samples(win)
    rms = [math.sqrt(sum(v * v for v in x[i:i + n]) / n) for i in range(0, len(x), n)]
    top = max(rms, default=0.0)
    if top <= 0:
        return 0.0
    thr = top * 10 ** (below_db / 20.0)
    last = max(i for i, v in enumerate(rms) if v >= thr)
    return (last + 1) * n / SR


def seed_for(name: str) -> int:
    return zlib.crc32(name.encode()) ^ 0x1E6E7D


def render(name: str) -> Sig:
    fn, peak_db = SOUNDS[name]
    # quiet UI sounds can trim earlier: their tail is inaudible sooner
    floor_db = -46.0 if peak_db <= -9.0 else -54.0
    return finish(fn(random.Random(seed_for(name))), peak_db, floor_db=floor_db)


def main(argv: list[str]) -> int:
    names = [n for n in SOUNDS if not argv or any(n.startswith(a) for a in argv)]
    if not names:
        print(f"no sound matches {argv}; known: {', '.join(SOUNDS)}")
        return 1
    # only these synth sounds ship; the rest are now pack-based (pack_sfx.py)
    packed = set(SOUNDS) - SHIPPED
    total = 0
    aud: dict[str, float] = {}
    for name in names:
        x = render(name)
        out = SYNTH_OUT if name in packed else OUT
        out.mkdir(parents=True, exist_ok=True)
        path = out / f"{name}.wav"
        write_wav(path, x)
        size = path.stat().st_size
        total += size
        pk = max(abs(v) for v in x)
        aud[name] = audible(x)
        print(f"{name:15s} {len(x) / SR:5.2f} s  audible {aud[name]:4.2f} s  "
              f"peak {20 * math.log10(pk):6.1f} dBFS  {size / 1024:6.1f} KB")
    print(f"{len(names)} file(s), {total / 1024:.0f} KB -> {OUT} (pack-mapped names -> {SYNTH_OUT})")
    print("mixer.AUDIBLE (src/lol/ui/mixer.py):")
    print("    " + ", ".join(f'"{n}": {v:.2f}' for n, v in aud.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
