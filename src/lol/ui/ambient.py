"""Ambient "mind-space" layer for Life of Legends: the app should feel like light floating in
an inner space, not solid blocks on a black page.

- `MindSpace`      full-screen living background (sits *behind* the whole app in a Stack):
                   drifting/breathing nebula glows, a far starfield that twinkles, faint
                   constellation lines, near out-of-focus bokeh, floating light motes that rise,
                   a vignette. `pulse(color)` brightens it for a beat (rewards).
- `glass()` / `apply_glass()` / `glass_style()`
                   frosted translucent panels: semi-transparent navy, soft cyan hairline, faint
                   inner glow, optional *real* backdrop blur. Three quality levels (see below).
- `ParticleBurst`  tap-through overlay: soft glowing particles burst from a point and fade.

Performance budget (MindSpace, defaults): ~40 controls (5 nebula + 3 bokeh + 22 motes + 3 star
canvases + 1 line canvas + base/pulse/vignette). All motion is implicit animation (offset /
scale / opacity / position, 2-20 s each). One Python tick every `tick_s` (2.5 s, clamped 2-4)
re-targets whatever finished and sends ONE batched update - no per-frame loop. The tick parks
while the app is hidden (`page.wait_until_visible`) or `pause()`d. Reduce mode = static
gradient + still stars + dim still motes, no tick work at all.

Glass quality (`set_glass_cap()` lowers every glass panel live):
- "blur"  real backdrop blur (Container.blur -> Flutter BackdropFilter). Expensive on Android:
          each blurred panel re-samples what's behind it every frame anything behind it moves.
          Use for a few large, fixed surfaces only: header, bottom nav bar, bottom sheets/dialogs.
- "frost" fake frost: translucent gradient (no blur) + hairline + glow. Nearly free. Use for
          every card / row / tile in scrolling lists.
- "flat"  the old opaque panel (low-end phones or as a user choice).
"""

from __future__ import annotations

import asyncio
import contextlib
import math
import random
import time
import weakref
from dataclasses import dataclass
from typing import Any

import flet as ft
import flet.canvas as cv

from lol.ui import effects as fx
from lol.ui import theme as th
from lol.ui.theme import Radius, Space

a = fx.a
WHITE = "#FFFFFF"
INOUT = ft.AnimationCurve.EASE_IN_OUT_SINE
LINEAR = ft.AnimationCurve.LINEAR
SNAP = ft.Animation(1, LINEAR)  # instant jump; never None (see effects._SNAP)


def _anim(ms: float, curve: ft.AnimationCurve = INOUT) -> ft.Animation:
    return ft.Animation(int(max(1, ms)), curve)


def _rgb(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")[-6:]
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def mix(c1: str, c2: str, t: float) -> str:
    """Blend two #RRGGBB colours (t=0 -> c1, t=1 -> c2)."""
    r1, g1, b1 = _rgb(c1)
    r2, g2, b2 = _rgb(c2)
    t = max(0.0, min(1.0, t))
    r, g, b = (round(p + (q - p) * t) for p, q in ((r1, r2), (g1, g2), (b1, b2)))
    return f"#{r:02X}{g:02X}{b:02X}"


def _mounted(ctrl: ft.Control) -> bool:
    try:
        return ctrl.page is not None
    except Exception:  # noqa: BLE001
        return False


def _page_size(ctrl: ft.Control, fallback: tuple[float, float] = (375, 812)) -> tuple[float, float]:
    with contextlib.suppress(Exception):
        p = ctrl.page
        if p is not None and p.width and p.height:
            return float(p.width), float(p.height)
    return fallback


# --------------------------------------------------------------------------- tones


@dataclass(frozen=True)
class Tones:
    """Concrete colours MindSpace paints with, derived from the active palette."""

    base: tuple[str, str, str]  # top, middle, bottom of the backdrop gradient
    nebula: tuple[tuple[str, float], ...]  # (colour, peak opacity) per blob
    bokeh: tuple[str, ...]
    motes: tuple[str, ...]
    stars: tuple[str, ...]
    lines: str
    vignette: str
    strength: float  # 1 on Arcane, lower on the flat themes


def tones(pal: th.Palette | None = None) -> Tones:
    pal = pal or th.current()
    if pal.id == "rose":  # Rose Arcana: the full mind-space in plum / rose / lilac / peach
        return Tones(
            base=("#1F0A26", pal.bg, "#070209"),
            nebula=(("#A8327E", 0.50), ("#B79BFF", 0.34), (pal.primary, 0.26),
                    ("#4A1F7A", 0.58), ("#FFB49A", 0.14)),
            bokeh=(pal.primary, "#C9A7FF", "#FFC4A8"),
            motes=(pal.primary, "#FFD3E8", WHITE, "#FFC4A8", "#D8C2FF"),
            stars=(WHITE, "#FFE3F1", "#E4D3FF"),
            lines=pal.primary, vignette="#050106", strength=1.0)
    if pal.glow:  # Arcane: the full cyan / teal / violet / mint mind-space
        return Tones(
            base=("#0A1428", pal.bg, "#04060C"),
            nebula=(("#1FA9B8", 0.52), ("#A78BFA", 0.40), (pal.primary, 0.28),
                    ("#2456A8", 0.60), (pal.success, 0.20)),
            bokeh=(pal.primary, "#A78BFA", pal.success),
            motes=(pal.primary, "#CFF8FF", WHITE, "#F5C66B", "#B9A6FF", "#4FE3F0"),
            stars=(WHITE, "#CFF8FF", "#9FD8FF"),
            lines=pal.primary, vignette="#020409", strength=1.0)
    deep = mix(pal.bg, pal.primary, 0.35)
    return Tones(  # other themes: same space, quieter and in their own hues
        base=(mix(pal.bg, pal.primary, 0.06), pal.bg, mix(pal.bg, "#000000", 0.35)),
        nebula=((pal.primary, 0.26), (pal.accent, 0.17), (deep, 0.36),
                (mix(pal.bg, pal.accent, 0.4), 0.26), (pal.success, 0.09)),
        bokeh=(pal.primary, pal.accent, pal.success),
        motes=(pal.primary, mix(pal.primary, WHITE, 0.6), pal.accent),
        stars=(WHITE, mix(pal.primary, WHITE, 0.7)),
        lines=pal.primary, vignette=mix(pal.bg, "#000000", 0.6), strength=0.65)


# --------------------------------------------------------------------------- MindSpace parts

# nebula layout: (centre x, centre y) as a fraction of the screen, diameter as width multiple
_NEBULA = ((0.02, 0.16, 1.40), (0.98, 0.44, 1.25), (0.22, 0.74, 1.10), (0.62, 0.02, 1.55),
           (0.86, 0.94, 1.00))
_BOKEH = ((0.80, 0.22, 96), (0.14, 0.52, 70), (0.66, 0.80, 120))


class _Drifter:
    """A big soft glow that drifts (offset), breathes (scale) and dims (opacity) toward a new
    random target every `dur` seconds - one implicit animation per leg."""

    def __init__(self, ctrl: ft.Container, base_op: float, *, reach: float, dur: tuple[float, float],
                 scale: tuple[float, float], rnd: random.Random) -> None:
        self.ctrl, self.base_op, self.reach, self.dur, self.scale = ctrl, base_op, reach, dur, scale
        self.due = 0.0
        self.rnd = rnd

    def retarget(self, now: float, k: float = 1.0) -> None:
        r = self.rnd
        secs = r.uniform(*self.dur)
        anim = _anim(secs * 1000)
        c = self.ctrl
        c.animate_offset = c.animate_scale = c.animate_opacity = anim
        c.offset = ft.Offset(r.uniform(-self.reach, self.reach), r.uniform(-self.reach, self.reach) * 0.8)
        c.scale = r.uniform(*self.scale)
        c.opacity = min(1.0, self.base_op * r.uniform(0.6, 1.0) * k)
        self.due = now + secs * r.uniform(0.85, 1.0)

    def rest(self) -> None:
        c = self.ctrl
        c.animate_offset = c.animate_scale = c.animate_opacity = SNAP
        c.offset, c.scale, c.opacity = ft.Offset(0, 0), 1.0, self.base_op * 0.85


class _Mote:
    """A floating light point. Lives in ticks: spawn (hidden, snapped) -> rise (slow upward
    drift + fade in) -> twinkle -> fade -> spawn again somewhere else."""

    def __init__(self, ctrl: ft.Container, d: float, peak: float, rnd: random.Random) -> None:
        self.ctrl, self.d, self.peak, self.rnd = ctrl, d, peak, rnd
        ctrl.animate_position = ctrl.animate_opacity = SNAP  # animated from the start
        self.state = "spawn"
        self.left = 0

    def spawn(self, w: float, h: float, *, y_range: tuple[float, float] = (0.3, 1.02)) -> None:
        c, r = self.ctrl, self.rnd
        c.animate_position = c.animate_opacity = SNAP
        c.left = r.uniform(-4, w - self.d + 4)
        c.top = r.uniform(h * y_range[0], h * y_range[1])
        c.opacity = 0
        self.state = "rise"

    def rise(self, tick: float, h: float, ticks: int | None = None) -> None:
        c, r = self.ctrl, self.rnd
        self.left = ticks if ticks is not None else r.randint(4, 8)
        secs = self.left * tick + 2.0
        speed = r.uniform(5, 13) * (1.25 if self.d < 5 else 0.85)  # small ones are 'nearer'
        c.animate_position = _anim(secs * 1000, LINEAR)
        c.animate_opacity = _anim(2200)
        c.top = (c.top or 0) - speed * secs
        c.left = (c.left or 0) + r.uniform(-26, 26)
        c.opacity = self.peak
        self.state = "twinkle"

    def step(self, tick: float, w: float, h: float) -> None:
        if self.state == "spawn":
            self.spawn(w, h)
        elif self.state == "rise":
            self.rise(tick, h)
        elif self.state == "twinkle":
            self.left -= 1
            if self.left <= 0:
                self.ctrl.animate_opacity = _anim(1800)
                self.ctrl.opacity = 0
                self.state = "spawn"
            elif self.rnd.random() < 0.6:
                self.ctrl.animate_opacity = _anim(self.rnd.uniform(900, 2200))
                self.ctrl.opacity = self.peak * self.rnd.uniform(0.3, 1.0)

    def rest(self, w: float, h: float) -> None:
        c, r = self.ctrl, self.rnd
        c.animate_position = c.animate_opacity = SNAP
        if c.top is None or c.top < -20 or c.top > h:
            c.left, c.top = r.uniform(0, w - self.d), r.uniform(h * 0.1, h * 0.95)
        c.opacity = self.peak * 0.45
        self.state = "rise"


def _mote_dot(d: float, color: str, peak: float, glow: bool) -> ft.Container:
    dot = fx.soft_dot(d, color, op=1.0, glow=glow)
    dot.opacity = 0
    return dot


def _bokeh_disc(d: float, color: str, op: float) -> ft.Container:
    """Out-of-focus disc: flat-ish centre with a soft edge (looks like near, blurred light)."""
    return ft.Container(width=d, height=d, shape=ft.BoxShape.CIRCLE, opacity=op,
                        gradient=ft.RadialGradient(colors=[a(color, 0.55), a(color, 0.42),
                                                           a(color, 0.16), a(color, 0)],
                                                   stops=[0, 0.62, 0.86, 1]))


class MindSpace(ft.Container):
    """Living background - put it first in a Stack behind the app:

        space = MindSpace()
        page.add(ft.Stack([space, ft.SafeArea(shell, expand=True)], expand=True))

    It never takes input (ignore_interactions). Size comes from the page on mount; call
    `resize(w, h)` from page.on_resize. `pause()` / `resume()` for app hide/show (the tick also
    parks by itself while `page.app_visible` is False). Follows `effects.reduced()` unless
    `reduce=` is given; flip with `set_reduce()`. Theme switches recolour it live."""

    def __init__(self, *, motes: int = 22, stars: int = 72, lines: bool = True,
                 bokeh: bool = True, reduce: bool | None = None, tick_s: float = 2.5,
                 seed: int = 7) -> None:
        self.reduce = reduce
        self.tick_s = max(2.0, min(4.0, tick_s))
        self._rnd = random.Random(seed)
        self._seed = seed
        self._w, self._h = 375.0, 812.0
        self._n_stars, self._lines_on = stars, lines
        self._alive = False
        self._paused = False
        self._static = False
        self._wake = asyncio.Event()
        self._loop_gen = 0
        self._tick_n = 0
        self._tones = tones()

        self._base = ft.Container(left=0, top=0, right=0, bottom=0)
        self._star_layers = [ft.Container(cv.Canvas([], width=375, height=812), left=0, top=0, right=0,
                                          bottom=0, opacity=0.9, offset=ft.Offset(0, 0),
                                          animate_opacity=SNAP, animate_offset=SNAP)
                             for _ in range(3)]
        self._lines = ft.Container(cv.Canvas([], width=375, height=812), left=0, top=0, right=0, bottom=0,
                                   opacity=0.8, visible=lines, animate_opacity=SNAP)
        self._blobs = [ft.Container(shape=ft.BoxShape.CIRCLE) for _ in _NEBULA]
        self._bokeh = [ft.Container(shape=ft.BoxShape.CIRCLE) for _ in _BOKEH] if bokeh else []
        self._drift = [_Drifter(b, op, reach=0.13, dur=(10, 18), scale=(0.88, 1.18),
                                rnd=self._rnd)
                       for b, (_, op) in zip(self._blobs, self._tones.nebula, strict=False)]
        self._drift += [_Drifter(b, 1.0, reach=0.9, dur=(8, 13), scale=(0.8, 1.25),
                                 rnd=self._rnd) for b in self._bokeh]
        rnd = self._rnd
        self._motes: list[_Mote] = []
        for i in range(max(0, min(30, motes))):
            r = rnd.random()
            d = 3.6 + 9.0 * r * r  # mostly small, a few bigger soft ones
            peak = rnd.uniform(0.7, 1.0) if d < 6 else rnd.uniform(0.45, 0.7)
            ctrl = _mote_dot(d, self._tones.motes[i % len(self._tones.motes)], peak,
                             glow=d >= 8)
            self._motes.append(_Mote(ctrl, d, peak, rnd))
        self._pulse = ft.Container(left=0, top=0, right=0, bottom=0, opacity=0,
                                   animate_opacity=_anim(300, ft.AnimationCurve.EASE_OUT))
        self._vignette = ft.Container(left=0, top=0, right=0, bottom=0)
        self._stack = ft.Stack(
            [self._base, *self._star_layers[:2], *self._blobs, self._star_layers[2], self._lines,
             *(m.ctrl for m in self._motes), *self._bokeh, self._pulse, self._vignette],
            expand=True, clip_behavior=ft.ClipBehavior.HARD_EDGE)
        super().__init__(content=self._stack, expand=True, ignore_interactions=True,
                         bgcolor=th.current().bg)
        self._paint()
        self._layout()
        for d in self._drift:  # start at rest (soft, dim) - the first tick sets them drifting
            d.rest()
        th.on_theme_change(self)

    # ---------------------------------------------------------------- painting / layout
    def _paint(self) -> None:
        t = self._tones = tones()
        self.bgcolor = t.base[1]
        self._base.gradient = ft.LinearGradient(begin=ft.Alignment.TOP_CENTER,
                                                end=ft.Alignment.BOTTOM_CENTER,
                                                colors=list(t.base), stops=[0, 0.45, 1])
        for b, (col, _) in zip(self._blobs, t.nebula, strict=False):
            b.gradient = ft.RadialGradient(colors=[a(col, 1), a(col, 0.45), a(col, 0.12),
                                                   a(col, 0)], stops=[0, 0.35, 0.65, 1])
        for drifter, (_, op) in zip(self._drift, t.nebula, strict=False):
            drifter.base_op = op
        for i, (b, (_, _, d)) in enumerate(zip(self._bokeh, _BOKEH, strict=False)):
            col = t.bokeh[i % len(t.bokeh)]
            disc = _bokeh_disc(d, col, 1)
            b.gradient = disc.gradient
        for i, d in enumerate(self._drift[len(self._blobs):]):
            d.base_op = (0.22, 0.16, 0.13)[i % 3] * t.strength
        for i, m in enumerate(self._motes):
            fx._repaint_dot(m.ctrl, t.motes[i % len(t.motes)])
        self._vignette.gradient = ft.RadialGradient(
            center=ft.Alignment(0, -0.15), radius=1.05,
            colors=[a(t.vignette, 0), a(t.vignette, 0), a(t.vignette, 0.3),
                    a(t.vignette, 0.7)], stops=[0, 0.55, 0.85, 1])

    def _layout(self) -> None:
        """Place the size-dependent parts for the current width/height."""
        w, h = self._w, self._h
        for b, (fx_, fy, k) in zip(self._blobs, _NEBULA, strict=False):
            d = k * w
            b.width = b.height = d
            b.left, b.top = fx_ * w - d / 2, fy * h - d / 2
        for b, (fx_, fy, d) in zip(self._bokeh, _BOKEH, strict=False):
            b.width = b.height = d
            b.left, b.top = fx_ * w - d / 2, fy * h - d / 2
        self._draw_stars()
        self._draw_lines()
        for m in self._motes:
            if m.ctrl.top is None:
                m.ctrl.left = self._rnd.uniform(0, w - m.d)
                m.ctrl.top = self._rnd.uniform(h * 0.05, h * 0.98)

    def _draw_stars(self) -> None:
        t, w, h = self._tones, self._w, self._h
        rnd = random.Random(self._seed * 31 + int(w))
        per = max(8, self._n_stars // 3)
        for layer in self._star_layers:
            shapes: list[cv.Shape] = []
            for _ in range(per):
                x, y = rnd.uniform(0, w), rnd.uniform(0, h)
                r = rnd.choice((0.45, 0.6, 0.7, 0.8, 0.9, 1.0, 1.2, 1.5))
                col = rnd.choice(t.stars)
                if r >= 1.2 and rnd.random() < 0.6:  # a few with a soft halo
                    shapes.append(cv.Circle(x, y, r * 3.6, paint=fx._solid(a(col, 0.07))))
                shapes.append(cv.Circle(x, y, r, paint=fx._solid(
                    a(col, rnd.uniform(0.25, 0.75) * (0.7 + 0.3 * t.strength)))))
            canvas = layer.content
            canvas.shapes, canvas.width, canvas.height = shapes, w, h  # type: ignore[union-attr]

    def _draw_lines(self) -> None:
        """Faint constellations + one huge thought-halo arc - original, abstract."""
        t, w, h = self._tones, self._w, self._h
        rnd = random.Random(self._seed * 7 + 3)
        col = t.lines
        line_paint = fx._stroke(a(col, 0.11 * (0.6 + 0.4 * t.strength)), 0.7)
        node_paint = fx._solid(a(col, 0.32 * (0.6 + 0.4 * t.strength)))
        halo_paint = fx._solid(a(col, 0.07))
        shapes: list[cv.Shape] = []
        anchors = ((0.18, 0.12), (0.78, 0.30), (0.30, 0.58), (0.82, 0.74), (0.12, 0.90))
        for ax, ay in anchors:
            x, y = ax * w, ay * h
            pts = [(x, y)]
            ang = rnd.uniform(0, math.tau)
            for _ in range(rnd.randint(2, 4)):
                ang += rnd.uniform(-1.1, 1.1)
                step = rnd.uniform(26, 58)
                x, y = x + step * math.cos(ang), y + step * math.sin(ang)
                pts.append((x, y))
            els = [cv.Path.MoveTo(*pts[0])] + [cv.Path.LineTo(px, py) for px, py in pts[1:]]
            shapes.append(cv.Path(els, paint=line_paint))
            for px, py in pts:
                shapes.append(cv.Circle(px, py, 3.6, paint=halo_paint))
                shapes.append(cv.Circle(px, py, 1.3, paint=node_paint))
        # a vast, barely-there halo ring (the 'edge' of the mind) + a dashed inner orbit
        cx, cy, rr = w * 1.05, h * 0.06, w * 0.95
        shapes.append(cv.Circle(cx, cy, rr, paint=fx._stroke(a(col, 0.06), 1)))
        shapes.append(cv.Circle(cx, cy, rr * 0.82, paint=fx._stroke(a(col, 0.05), 1,
                                                                    dash=[2, 7])))
        canvas = self._lines.content
        canvas.shapes, canvas.width, canvas.height = shapes, w, h  # type: ignore[union-attr]

    def restyle(self) -> None:
        """Theme switched (called by theme.apply_theme before its page.update)."""
        self._paint()
        self._draw_stars()
        self._draw_lines()
        if self._static or self._reduced():
            self._settle_static()

    def resize(self, width: float, height: float, *, update: bool = True) -> None:
        if not width or not height:
            return
        if abs(width - self._w) < 1 and abs(height - self._h) < 1:
            return
        self._w, self._h = float(width), float(height)
        self._layout()
        if update and _mounted(self):
            self.update()

    # ---------------------------------------------------------------- reduce / pause
    def _reduced(self) -> bool:
        return fx.reduced() if self.reduce is None else bool(self.reduce)

    def set_reduce(self, on: bool | None) -> None:
        """True/False pins reduce mode for this control; None follows effects.reduced()."""
        self.reduce = on
        self._wake.set()

    def pause(self) -> None:
        """Stop re-targeting (in-flight glides finish, then everything rests). Cheap."""
        self._paused = True

    def resume(self) -> None:
        self._paused = False
        self._wake.set()

    @property
    def paused(self) -> bool:
        return self._paused

    def _settle_static(self) -> None:
        for d in self._drift:
            d.rest()
        for m in self._motes:
            m.rest(self._w, self._h)
        for layer in self._star_layers:
            layer.animate_opacity = layer.animate_offset = SNAP
            layer.opacity, layer.offset = 0.85, ft.Offset(0, 0)
        self._lines.animate_opacity = SNAP
        self._lines.opacity = 0.75
        self._static = True

    # ---------------------------------------------------------------- tick
    def did_mount(self) -> None:
        super().did_mount()
        self._w, self._h = _page_size(self, (self._w, self._h))
        self._layout()
        self._alive = True
        self._loop_gen += 1
        with contextlib.suppress(Exception):
            self.page.run_task(self._loop, self._loop_gen)  # type: ignore[union-attr]

    def will_unmount(self) -> None:
        self._alive = False
        self._wake.set()
        super().will_unmount()

    async def _sleep(self, seconds: float) -> None:
        self._wake.clear()
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(self._wake.wait(), seconds)

    async def _loop(self, gen: int) -> None:
        await asyncio.sleep(0.15)
        first = True
        while self._alive and gen == self._loop_gen:
            with contextlib.suppress(Exception):
                page = self.page
                if page is not None and not page.app_visible:
                    await page.wait_until_visible()
            if not self._alive or gen != self._loop_gen:
                return
            if self._reduced():
                if not self._static:
                    self._settle_static()
                    self._push()
                await self._sleep(self.tick_s)
                continue
            if self._paused:
                await self._sleep(30)
                continue
            if self._static:  # coming back from reduce mode
                self._static = False
                first = True
            self._tick(first)
            self._push()
            first = False
            await self._sleep(self.tick_s)

    def _push(self) -> None:
        with contextlib.suppress(Exception):
            if _mounted(self):
                self.update()

    def _tick(self, first: bool) -> None:
        now = time.monotonic()
        self._tick_n += 1
        for d in self._drift:
            if first or now >= d.due:
                d.retarget(now)
        w, h = self._w, self._h
        if first:  # start everyone at a different point of their life: no synced waves
            for m in self._motes:
                c = m.ctrl
                if c.top is None or c.top < -10 or c.top > h:
                    c.left, c.top = self._rnd.uniform(0, w - m.d), self._rnd.uniform(0, h)
                m.rise(self.tick_s, h, ticks=self._rnd.randint(1, 7))
        else:
            for m in self._motes:
                m.step(self.tick_s, w, h)
        # far stars: one layer re-twinkles per tick; slow parallax drift every few ticks
        layer = self._star_layers[self._tick_n % len(self._star_layers)]
        layer.animate_opacity = _anim(self.tick_s * 1000 * 1.6)
        layer.opacity = self._rnd.uniform(0.35, 1.0)
        if first or self._tick_n % 6 == 0:
            for k, sl in enumerate(self._star_layers):
                sl.animate_offset = _anim(self.tick_s * 6000 + 500)
                amp = 0.006 * (k + 1)
                sl.offset = ft.Offset(self._rnd.uniform(-amp, amp), self._rnd.uniform(-amp, amp))
        if self._lines_on and (first or self._tick_n % 3 == 0):
            self._lines.animate_opacity = _anim(self.tick_s * 3000)
            self._lines.opacity = self._rnd.uniform(0.45, 1.0)

    # ---------------------------------------------------------------- pulse
    def pulse(self, color: str | None = None, strength: float = 1.0) -> None:
        """Briefly brighten the space (reward moments). Fire-and-forget; safe anywhere."""
        if not _mounted(self):
            return
        with contextlib.suppress(Exception):
            self.page.run_task(self._pulse_run, color, strength)  # type: ignore[union-attr]

    async def _pulse_run(self, color: str | None, strength: float) -> None:
        col = color or th.current().primary
        k = max(0.2, min(1.5, strength)) * (0.75 + 0.25 * self._tones.strength)
        self._pulse.gradient = ft.RadialGradient(
            center=ft.Alignment(0, -0.2), radius=0.95,
            colors=[a(col, 0.34 * k), a(col, 0.14 * k), a(col, 0.04 * k), a(col, 0)],
            stops=[0, 0.4, 0.75, 1])
        self._pulse.animate_opacity = _anim(260, ft.AnimationCurve.EASE_OUT)
        self._pulse.opacity = 1
        lively = not self._reduced()
        if lively:  # motes flare up with it
            for m in self._motes:
                if m.state == "twinkle":
                    m.ctrl.animate_opacity = _anim(260)
                    m.ctrl.opacity = min(1.0, m.peak * 1.25)
        self._push()
        await asyncio.sleep(0.42)
        self._pulse.animate_opacity = _anim(1700, ft.AnimationCurve.EASE_IN_OUT)
        self._pulse.opacity = 0
        if lively:
            for m in self._motes:
                if m.state == "twinkle":
                    m.ctrl.animate_opacity = _anim(1600)
                    m.ctrl.opacity = m.peak * self._rnd.uniform(0.4, 0.9)
        self._push()


# --------------------------------------------------------------------------- glass

QUALITIES = ("flat", "frost", "blur")
_cap = ["blur"]
_glass: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()  # ctrl -> spec dict
_hooked = [False]


def set_glass_cap(quality: str, page: ft.Page | None = None) -> None:
    """Highest glass quality allowed app-wide ("blur" | "frost" | "flat"). Every panel made
    with glass()/apply_glass() restyles live; pass `page` to push it now."""
    if quality not in QUALITIES:
        return
    _cap[0] = quality
    _restyle_all()
    if page is not None:
        with contextlib.suppress(Exception):
            page.update()


def glass_cap() -> str:
    return _cap[0]


def effective_quality(requested: str) -> str:
    req = requested if requested in QUALITIES else "frost"
    return QUALITIES[min(QUALITIES.index(req), QUALITIES.index(_cap[0]))]


def glass_style(quality: str = "frost", *, tint: str | None = None, sigma: float = 14,
                fill: float = 1.0, glow: bool = True) -> dict[str, Any]:
    """Container kwargs for a glass panel in the current theme (bgcolor, gradient, blur,
    border, shadow). `tint`: hue of the hairline + glow (e.g. a Path colour). `fill` scales the
    panel's opacity (1 = default; 1.15 for denser text-heavy panels)."""
    pal = th.current()
    q = effective_quality(quality)
    hue = tint or pal.primary
    if q == "flat":
        return {"bgcolor": pal.surface_hi, "gradient": None, "blur": None,
                "border": th.panel_border(tint), "shadow": th.panel_shadow(tint)}
    sheen = mix(pal.surface_hi, hue, 0.08 if pal.glow else 0.04)
    if q == "blur":
        ops = (0.52, 0.40, 0.36)
    else:  # frost: no real blur, so a touch denser to keep text crisp over moving light
        ops = (0.66, 0.54, 0.48)
    ops = tuple(min(0.97, o * fill) for o in ops)
    grad = ft.LinearGradient(begin=ft.Alignment.TOP_LEFT, end=ft.Alignment.BOTTOM_RIGHT,
                             colors=[a(sheen, ops[0]), a(pal.surface, ops[1]),
                                     a(pal.bg, ops[2])], stops=[0, 0.55, 1])
    if pal.glow:
        border = ft.Border.all(1.2, a(hue, 0.28))
        shadow = [ft.BoxShadow(blur_radius=22, color=a(hue, 0.12) if glow else a(hue, 0)),
                  ft.BoxShadow(blur_radius=18, offset=ft.Offset(0, 8),
                               color=a("#000000", 0.32))]
    else:
        border = ft.Border.all(1, a(pal.text, 0.09))
        shadow = [ft.BoxShadow(blur_radius=16, offset=ft.Offset(0, 6), color=a("#000000", 0.25))]
    return {"bgcolor": None, "gradient": grad,
            "blur": ft.Blur(sigma, sigma, ft.BlurTileMode.CLAMP) if q == "blur" else None,
            "border": border, "shadow": shadow}


def _apply(ctrl: ft.Container, spec: dict[str, Any]) -> None:
    for k, v in glass_style(**spec).items():
        setattr(ctrl, k, v)


def _restyle_all(_: Any = None) -> None:
    for ctrl, spec in list(_glass.items()):
        with contextlib.suppress(Exception):
            _apply(ctrl, spec)


def apply_glass(ctrl: ft.Container, quality: str = "frost", *, tint: str | None = None,
                sigma: float = 14, fill: float = 1.0, glow: bool = True) -> ft.Container:
    """Turn an existing panel Container into glass, live across theme switches and
    set_glass_cap(). Replaces theme.glow() for that control (it stops managing it)."""
    with contextlib.suppress(Exception):
        th._glowing.pop(ctrl, None)  # glass owns border + shadow now
    spec = {"quality": quality, "tint": tint, "sigma": sigma, "fill": fill, "glow": glow}
    _glass[ctrl] = spec
    _apply(ctrl, spec)
    if not _hooked[0]:
        _hooked[0] = True
        th.on_theme_change(callback=_restyle_all)
    return ctrl


def set_glass_tint(ctrl: ft.Container, tint: str | None) -> None:
    """Change a glass panel's hue (e.g. a card switching Path)."""
    spec = _glass.get(ctrl)
    if spec is not None:
        spec["tint"] = tint
        _apply(ctrl, spec)


def glass(content: ft.Control | None = None, quality: str = "frost", *,
          radius: float = Radius.MD, padding: Any = Space.MD, tint: str | None = None,
          sigma: float = 14, fill: float = 1.0, glow: bool = True, **kw: Any) -> ft.Container:
    """A frosted translucent panel - light in space instead of a solid chunk.

    quality: "blur" (real backdrop blur: header, nav bar, sheets), "frost" (cards, rows - the
    default), "flat" (opaque). Extra kwargs go to ft.Container (width, on_click, ...)."""
    kw.setdefault("clip_behavior", ft.ClipBehavior.ANTI_ALIAS)
    ctrl = ft.Container(content, border_radius=radius, padding=padding, **kw)
    return apply_glass(ctrl, quality, tint=tint, sigma=sigma, fill=fill, glow=glow)


# --------------------------------------------------------------------------- ParticleBurst


class ParticleBurst(ft.Container):
    """Tap-through overlay of soft glowing particles. `page.overlay.append(burst)`, then
    `await burst.burst(x, y, color=...)` (page coordinates; None = screen centre). Each burst
    is ~1.4 s: a bloom flash + shockwave ring + 20-40 particles flying out with a gentle lift,
    shrinking and fading; then its controls are removed. At most `max_live` run at once (the
    oldest is dropped). Reduce mode: just the soft bloom."""

    S = 360

    def __init__(self, *, reduce: bool | None = None, max_live: int = 3) -> None:
        self.reduce = reduce
        self.max_live = max_live
        self._stack = ft.Stack([], expand=True, clip_behavior=ft.ClipBehavior.NONE)
        self._live: list[ft.Container] = []
        self._seed = 100
        super().__init__(content=self._stack, expand=True, ignore_interactions=True)

    def _reduced(self) -> bool:
        return fx.reduced() if self.reduce is None else bool(self.reduce)

    def _push(self) -> None:
        with contextlib.suppress(Exception):
            if _mounted(self):
                self._stack.update()

    async def burst(self, x: float | None = None, y: float | None = None, *,
                    color: str | None = None, count: int = 34, spread: float = 1.0,
                    ring: bool = True) -> None:
        if not _mounted(self):
            return
        w, h = _page_size(self)
        x = w / 2 if x is None else x
        y = h * 0.45 if y is None else y
        col = color or th.current().primary
        s, c = self.S, self.S / 2
        self._seed += 1
        simple = self._reduced()
        flash = fx._place(fx._bloom(190), c, c)
        fx._paint_bloom(flash, col, 0.62)
        parts: list[ft.Control] = [flash]
        shock = sparks = None
        if not simple:
            if ring:
                shock = fx._place(ft.Container(
                    width=70, height=70, shape=ft.BoxShape.CIRCLE, scale=0.3, opacity=0.9,
                    animate_scale=fx._anim(700, fx.CUBIC),
                    animate_opacity=fx._anim(700, ft.AnimationCurve.EASE_IN),
                    border=ft.Border.all(1.3, a(col, 0.75)),
                    shadow=ft.BoxShadow(blur_radius=12, color=a(col, 0.4))), c, c)
                parts.append(shock)
            sparks = fx._place(fx.Sparks(s, max(20, min(40, count)),
                                         (WHITE, col, mix(col, WHITE, 0.55)), seed=self._seed,
                                         reach=(55 * spread, 165 * spread), dot=(3.5, 14),
                                         lift=36, ms=(750, 1300)), c, c)
            parts.append(sparks)
        holder = ft.Container(ft.Stack(parts, width=s, height=s,
                                       clip_behavior=ft.ClipBehavior.NONE),
                              left=x - c, top=y - c, width=s, height=s)
        while len(self._live) >= self.max_live:
            old = self._live.pop(0)
            with contextlib.suppress(ValueError):
                self._stack.controls.remove(old)
        self._live.append(holder)
        self._stack.controls.append(holder)
        self._push()
        await asyncio.sleep(0.03)
        flash.opacity, flash.scale = 1, 1.15
        if shock is not None:
            shock.scale, shock.opacity = 2.6, 0
        if sparks is not None:
            sparks.burst()
        self._push()
        await asyncio.sleep(0.35)
        flash.animate_opacity = fx._anim(700, ft.AnimationCurve.EASE_IN_OUT)
        flash.opacity, flash.scale = 0, 0.9
        if sparks is not None:
            sparks.fade((500, 950))
        self._push()
        await asyncio.sleep(1.05)
        if holder in self._live:
            self._live.remove(holder)
            with contextlib.suppress(ValueError):
                self._stack.controls.remove(holder)
            self._push()


def card_center(e: Any) -> tuple[float | None, float | None]:
    """(x, y) page coordinates from a TapEvent (`on_tap_down`), for burst()/QuestCleared."""
    with contextlib.suppress(Exception):
        p = e.global_position
        return float(p.x), float(p.y)
    return None, None


__all__ = ["QUALITIES", "MindSpace", "ParticleBurst", "Tones", "apply_glass", "card_center",
           "effective_quality", "glass", "glass_cap", "glass_style", "mix", "set_glass_cap",
           "set_glass_tint", "tones"]
