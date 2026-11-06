"""Arcane overlay effects for Life of Legends (v1.2 spec, section A).

Original effects with the *feel* of the mood refs: cosmic light bursts, diamond emblems, rotating
rune rings, a wireframe orb, gear/clock rings and linked skill nodes. Glyphs are invented
(`ui.glyphs`); every label is English. Built only from Flet built-ins: Canvas shapes, gradients,
BoxShadow glows and implicit animations (rotate/scale/opacity/offset).

Overlays (add each once: `page.overlay.append(fx)`, then `await fx.show(...)`):
- `NoticeEmblem`   skill / notice acquired          `await show(title, eyebrow, subtitle, color)`
- `MilestoneSeal`  level-up, rank-up, achievement    `await show(title, subtitle)`
- `LumenThinking`  Luma "Analysis..."               `await play(0.9, "Analysis…")`,
                                                     `await play_staged(2.5)` (v1.3, staged) or
                                                     `async with thinking.session(): ...`;
                                                     `on_start=` hook fires as the orb appears
- `IdentifyReveal` theme bought, side quest, item    `await show(title, subtitle)`
- `QuestCleared`   every quest completion (v1.3)     `await show(quest_title, x=, y=)` ~1.25 s,
                                                     tap-through, restarts on a new call

v1.4 'impact' layer: every reward effect has an `Icosphere` (glowing geodesic wireframe) at its
heart and fires `distort()` at its impact frame - zoom punch + jitter on the app root, flash,
cyan/magenta fringes, glitch slices, scanline sweep, shockwave ring, chromatic title ghost and
sfx 'distort'. The app registers its root once: `install_distortion(page, root=shell)`.
Staged analysis for any action: `play_staged(2.4, stages=("SCANNING…", "CALCULATING…",
"PLAN READY"))` (scan_tick per stage, scan_done on the last) - or `components.lumen_analyze`.

In-screen controls: `SkillLinkTree` (+ `SkillNode`), `ClockSpiral` (focus timer background +
progress ring), and the helpers `Starfield`, `Flare`, `Sparks` (soft particle burst / rising
motes) and `soft_dot`. Optional backdrop blur behind big overlays: `set_backdrop_blur(8)`
(native only - see its docstring).

Rules every overlay follows:
- Tap anywhere skips to the exit. Input is never blocked for more than 2.5 s: a watchdog drops
  the tap layer and sets ignore_interactions after that, whatever is still playing.
- Reduce effects: `set_reduce(True)` (global) or `reduce=True` per control -> a simple fade card.
- Hidden (visible=False) when done; calls queue, so stacked effects play in turn.
- Performance: motion is implicit animation (one update starts a multi-second rotation). The
  Python frame loops are LumenThinking's orb (20 fps) and the Icosphere (24 fps, its own
  Canvas only, <= ~90 shapes) - both run only while their effect plays and stop by themselves -
  plus the NEXT-node pulse (about 1 update per second, only while mounted). Distortion is
  ~6 short updates over ~0.2 s.
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import itertools
import logging
import math
import os
import random
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from typing import Any, Self

import flet as ft
import flet.canvas as cv

from lol.ui import glyphs, sfx
from lol.ui import theme as th

# --------------------------------------------------------------------------- palette

NAVY = "#070B14"
CYAN = "#4FE3F0"
TEAL = "#1FA9B8"
VIOLET = "#A78BFA"
MINT = "#5EEAB0"
GOLD = "#F5C66B"
AMBER = "#FFB347"
BRONZE = "#B98A4B"
CREAM = "#FFF1D6"
WHITE = "#FFFFFF"
DIM = "#5C6B82"

TAU = math.tau
MAX_BLOCK_S = 2.5  # tap-to-skip layer never holds input longer than this

_reduce = [False]
# debug slow motion for screenshots (gallery only): LOL_FX_SLOWMO=5 makes every effect 5x slower
_slowmo = [max(0.1, float(os.environ.get("LOL_FX_SLOWMO") or 1))]
_backdrop = [0.0]  # overlay backdrop blur sigma (0 = off; opt-in, see set_backdrop_blur)
_tasks: set[asyncio.Task] = set()
_log = logging.getLogger(__name__)


def set_reduce(on: bool) -> None:
    """Global 'Reduce effects' switch (settings). Controls with reduce=None follow it."""
    _reduce[0] = bool(on)


def reduced() -> bool:
    return _reduce[0]


def set_backdrop_blur(sigma: float) -> None:
    """Blur the app behind the big overlays (Notice/Milestone/Luma/Identify). Default 0 = off.
    Opt-in only on native Android after testing (8 looks good): on Flutter *web* (skwasm) a
    full-screen backdrop blur under IdentifyReveal's rotating canvases crashed the renderer
    ("memory access out of bounds"). Applies to overlays created after the call."""
    _backdrop[0] = max(0.0, float(sigma))


def _backdrop_blur() -> ft.Blur | None:
    s = _backdrop[0]
    return ft.Blur(s, s, ft.BlurTileMode.CLAMP) if s > 0 else None


# --------------------------------------------------------------------------- small helpers


def a(color: str, opacity: float) -> str:
    return ft.Colors.with_opacity(max(0.0, min(1.0, opacity)), color)


def _anim(ms: int, curve: ft.AnimationCurve = ft.AnimationCurve.EASE_OUT) -> ft.Animation:
    return ft.Animation(int(ms * _slowmo[0]), curve)


async def _sleep(seconds: float) -> None:
    await asyncio.sleep(seconds * _slowmo[0])


LINEAR = ft.AnimationCurve.LINEAR
# "jump now" animation. Never reset animate_* to None between legs: Flet swaps the Flutter
# widget (Positioned <-> AnimatedPositioned, ...) and the next leg then snaps instead of moving.
_SNAP = ft.Animation(1, ft.AnimationCurve.LINEAR)
CUBIC = ft.AnimationCurve.EASE_OUT_CUBIC
BACK = ft.AnimationCurve.EASE_OUT_BACK


def _mounted(ctrl: ft.Control) -> bool:
    try:
        return ctrl.page is not None
    except Exception:  # noqa: BLE001 - unmounted controls raise in some Flet builds
        return False


def _refresh(*controls: ft.Control) -> None:
    for c in controls:
        with contextlib.suppress(Exception):
            if _mounted(c):
                c.update()


def _spawn(coro: Awaitable[Any]) -> None:
    task = asyncio.ensure_future(coro)
    _tasks.add(task)
    task.add_done_callback(_done)


def _done(task: asyncio.Task) -> None:
    _tasks.discard(task)
    if not task.cancelled() and task.exception() is not None:
        _log.warning("effect task failed", exc_info=task.exception())


def _buzz(kind: str) -> None:
    """Haptic via components.buzz if available (lazy import: no import cycle)."""
    with contextlib.suppress(Exception):
        from lol.ui import components
        _spawn(components.buzz(kind))


def _fire(hook: Callable[[], Any] | None) -> None:
    """Call a user hook (sync or async) without ever letting it break an effect."""
    if hook is None:
        return
    with contextlib.suppress(Exception):
        res = hook()
        if asyncio.iscoroutine(res):
            _spawn(res)


def _fill(ctrl: ft.Control) -> ft.Control:
    ctrl.left = ctrl.top = ctrl.right = ctrl.bottom = 0
    return ctrl


def _place(ctrl: ft.Control, cx: float, cy: float) -> ft.Control:
    """Position a fixed-size control centred on (cx, cy) inside a Stack."""
    ctrl.left = cx - ctrl.width / 2
    ctrl.top = cy - ctrl.height / 2
    return ctrl


def _stroke(color: str, width: float = 1.0, *, dash: list[float] | None = None,
            cap: ft.StrokeCap | None = None, gradient: Any = None) -> ft.Paint:
    p = ft.Paint(color=color, stroke_width=width, style=ft.PaintingStyle.STROKE)
    if dash:
        p.stroke_dash_pattern = dash
    if cap:
        p.stroke_cap = cap
    if gradient is not None:
        p.gradient = gradient
    return p


def _solid(color: str, gradient: Any = None) -> ft.Paint:
    p = ft.Paint(color=color, style=ft.PaintingStyle.FILL)
    if gradient is not None:
        p.gradient = gradient
    return p


def _ray(cx: float, cy: float, ang: float, r0: float, r1: float, color: str, op: float,
         width: float) -> cv.Line:
    """A light ray from radius r0 to r1 that fades out along its length."""
    x0, y0 = cx + r0 * math.cos(ang), cy + r0 * math.sin(ang)
    x1, y1 = cx + r1 * math.cos(ang), cy + r1 * math.sin(ang)
    grad = ft.PaintLinearGradient(begin=ft.Offset(x0, y0), end=ft.Offset(x1, y1),
                                  colors=[a(color, op), a(color, 0)])
    return cv.Line(x0, y0, x1, y1, paint=_stroke(color, width, gradient=grad))


def _blob(cx: float, cy: float, d: float, color: str, op: float) -> ft.Container:
    """Soft round nebula glow (radial gradient), positioned in a Stack."""
    return _place(ft.Container(
        width=d, height=d, shape=ft.BoxShape.CIRCLE,
        gradient=ft.RadialGradient(colors=[a(color, op), a(color, op * 0.45), a(color, 0)],
                                   stops=[0, 0.45, 1]),
        opacity=0, scale=0.85,
        animate_opacity=_anim(500), animate_scale=_anim(2600, LINEAR),
    ), cx, cy)


def _rays_canvas(size: int, count: int, *, seed: int, colors: Sequence[str],
                 r0: float = 20, up_bias: bool = False, op: tuple[float, float] = (.35, .75),
                 width: tuple[float, float] = (.6, 1.8)) -> ft.Container:
    """Radial light rays drawn once on a Canvas; animate the wrapper's rotate/opacity."""
    rnd = random.Random(seed)
    c = size / 2
    shapes = []
    for _ in range(count):
        ang = rnd.uniform(0, TAU)
        reach = c * rnd.uniform(0.45, 1.0)
        if up_bias and math.sin(ang) > 0:  # downward rays stay short
            reach *= 0.45
        shapes.append(_ray(c, c, ang, r0, reach, rnd.choice(colors), rnd.uniform(*op),
                           rnd.uniform(*width)))
    return ft.Container(cv.Canvas(shapes, width=size, height=size), width=size, height=size,
                        opacity=0, rotate=0, animate_opacity=_anim(400),
                        animate_rotation=_anim(2600, LINEAR))


def _gear_elements(cx: float, cy: float, r_out: float, r_in: float,
                   teeth: int) -> list[cv.Path.PathElement]:
    step = TAU / teeth
    els: list[cv.Path.PathElement] = []
    for i in range(teeth):
        a0 = i * step
        for k, (r, f) in enumerate(((r_in, 0.0), (r_out, 0.12), (r_out, 0.38), (r_in, 0.5))):
            x, y = cx + r * math.cos(a0 + f * step), cy + r * math.sin(a0 + f * step)
            els.append(cv.Path.MoveTo(x, y) if i == 0 and k == 0 else cv.Path.LineTo(x, y))
    els.append(cv.Path.Close())
    return els


def _ticks(cx: float, cy: float, r0: float, r1: float, count: int, *, major: int = 0,
           r_major: float | None = None) -> list[cv.Path.PathElement]:
    els: list[cv.Path.PathElement] = []
    for i in range(count):
        t = TAU * i / count
        rs = r_major if (major and i % major == 0 and r_major is not None) else r0
        els += [cv.Path.MoveTo(cx + rs * math.cos(t), cy + rs * math.sin(t)),
                cv.Path.LineTo(cx + r1 * math.cos(t), cy + r1 * math.sin(t))]
    return els


def _title_size(text: str, sizes: Sequence[tuple[int, int]]) -> int:
    n = len(text)
    for limit, size in sizes:
        if n <= limit:
            return size
    return sizes[-1][1]


# --------------------------------------------------------------------------- Starfield / Flare


class Starfield(ft.Container):
    """Cheap drifting starfield: one Canvas of dots + radial streaks, moved by animating the
    wrapper's scale (a warp outward from the centre) and opacity. ~2 shapes per star."""

    def __init__(self, width: int = 860, height: int = 860, *, count: int = 36,
                 streaks: int = 10, colors: Sequence[str] = (WHITE, CYAN), seed: int = 3,
                 hole: float = 40) -> None:
        rnd = random.Random(seed)
        cx, cy = width / 2, height / 2
        shapes: list[cv.Shape] = []
        for _ in range(count):
            while True:
                x, y = rnd.uniform(0, width), rnd.uniform(0, height)
                if math.hypot(x - cx, y - cy) > hole:
                    break
            r = rnd.choice((0.6, 0.8, 1.0, 1.0, 1.3, 1.7, 2.3))
            col = rnd.choice(colors)
            if r >= 1.7:  # a few soft halos
                shapes.append(cv.Circle(x, y, r * 3.2, paint=_solid(a(col, 0.13))))
            shapes.append(cv.Circle(x, y, r, paint=_solid(a(col, rnd.uniform(0.45, 0.95)))))
        for _ in range(streaks):
            ang = rnd.uniform(0, TAU)
            d = rnd.uniform(70, min(cx, cy) * 0.95)
            ln = rnd.uniform(10, 34)
            shapes.append(_ray(cx, cy, ang + math.pi, -(d + ln), -d, rnd.choice(colors),
                               rnd.uniform(0.5, 0.85), rnd.uniform(0.8, 1.4)))
        super().__init__(content=cv.Canvas(shapes, width=width, height=height),
                         width=width, height=height, opacity=0, scale=1,
                         animate_opacity=_anim(400), animate_scale=_anim(2400, LINEAR),
                         ignore_interactions=True)

    def prime(self) -> None:
        """Start state (set while the host is hidden)."""
        self.opacity, self.scale = 0, 1

    def warp(self, seconds: float = 2.4, scale: float = 1.3, opacity: float = 1.0) -> None:
        self.animate_scale = _anim(seconds * 1000, ft.AnimationCurve.EASE_IN)
        self.scale, self.opacity = scale, opacity


class Flare(ft.Container):
    """Lens-flare bloom: radial core + anamorphic streaks. Call prime() (hidden), then
    burst() -> settle() -> fade(), refreshing the host between steps."""

    def __init__(self, size: int = 200, color: str = CYAN, *, core: str = WHITE,
                 streak: float = 1.8) -> None:
        self._size = size
        self._glow = ft.Container(width=size, height=size, shape=ft.BoxShape.CIRCLE)
        self._h = ft.Container(width=size * streak, height=3, border_radius=2)
        self._v = ft.Container(width=2, height=size * 0.85, border_radius=2)
        self._h2 = ft.Container(width=size * streak * 0.55, height=1.5, border_radius=1,
                                rotate=0.5)
        w = size * max(streak, 1.0)
        super().__init__(
            content=ft.Stack([self._glow, self._h, self._v, self._h2], width=w, height=size,
                             alignment=ft.Alignment.CENTER),
            width=w, height=size, scale=0.1, opacity=0, ignore_interactions=True,
            animate_scale=_anim(300, BACK), animate_opacity=_anim(220),
        )
        self.set_color(color, core)

    def set_color(self, color: str, core: str = WHITE) -> None:
        self._glow.gradient = ft.RadialGradient(
            colors=[core, a(core, 0.92), a(color, 0.6), a(color, 0.18), a(color, 0)],
            stops=[0, 0.07, 0.2, 0.45, 1])
        lin = [a(color, 0), a(core, 0.95), a(color, 0)]
        self._h.gradient = ft.LinearGradient(colors=lin)
        self._h2.gradient = ft.LinearGradient(colors=[a(color, 0), a(core, 0.6), a(color, 0)])
        self._v.gradient = ft.LinearGradient(begin=ft.Alignment.TOP_CENTER,
                                             end=ft.Alignment.BOTTOM_CENTER, colors=lin)

    def prime(self) -> None:
        self.scale, self.opacity = 0.1, 0

    def burst(self, ms: int = 300, scale: float = 1.0) -> None:
        self.animate_scale = _anim(ms, BACK)
        self.scale, self.opacity = scale, 1

    def settle(self, scale: float = 0.6, opacity: float = 0.8, ms: int = 700) -> None:
        self.animate_scale = _anim(ms, CUBIC)
        self.scale, self.opacity = scale, opacity

    def fade(self) -> None:
        self.opacity = 0

    async def bloom(self, hold: float = 0.4) -> None:
        """Standalone one-shot: flare up, settle, fade (control must be mounted)."""
        if not _mounted(self):
            return
        self.animate_opacity, self.animate_scale = _SNAP, _SNAP
        self.prime()
        _refresh(self)
        await _sleep(0.03)
        self.animate_opacity = _anim(220)
        self.burst()
        _refresh(self)
        await _sleep(0.3)
        self.settle()
        _refresh(self)
        await _sleep(hold)
        self.fade()
        _refresh(self)


# --------------------------------------------------------------------------- soft particles


def soft_dot(d: float, color: str, *, core: str = WHITE, op: float = 1.0,
             glow: bool = False) -> ft.Container:
    """A soft, out-of-focus light point: radial gradient (white core -> color -> clear), so it
    reads as blurred light rather than a solid disc. glow=True adds a BoxShadow halo (only for
    a handful of bigger points - shadows cost more than gradients)."""
    return ft.Container(
        width=d, height=d, shape=ft.BoxShape.CIRCLE,
        gradient=ft.RadialGradient(colors=[a(core, op), a(color, op * 0.8), a(color, op * 0.25),
                                           a(color, 0)], stops=[0, 0.25, 0.6, 1]),
        shadow=ft.BoxShadow(blur_radius=d * 1.6, color=a(color, 0.35 * op)) if glow else None)


def _repaint_dot(dot: ft.Container, color: str, core: str = WHITE, op: float = 1.0) -> None:
    dot.gradient = ft.RadialGradient(colors=[a(core, op), a(color, op * 0.8), a(color, op * 0.25),
                                             a(color, 0)], stops=[0, 0.25, 0.6, 1])
    if dot.shadow is not None:
        dot.shadow = ft.BoxShadow(blur_radius=(dot.width or 6) * 1.6, color=a(color, 0.35 * op))


class Sparks(ft.Container):
    """Soft glowing particles in a size x size box (children may overflow).

    mode="burst": they fly out from the centre (with a slight upward drift), shrink and fade.
    mode="rise":  they start spread over the lower part and float upward slowly (embers/motes).
    Use like Flare: prime() while the host is hidden (or refresh between), then burst()/rise(),
    later fade(). Every move is one implicit animation per particle - no frame loop."""

    def __init__(self, size: int = 360, count: int = 24, colors: Sequence[str] = (WHITE, CYAN),
                 *, seed: int = 1, mode: str = "burst", reach: tuple[float, float] = (60, 170),
                 dot: tuple[float, float] = (3, 12), lift: float = 30,
                 ms: tuple[int, int] = (700, 1250), core: str = WHITE) -> None:
        self._size, self._mid = size, size / 2
        self._mode, self._reach, self._lift, self._ms = mode, reach, lift, ms
        self._rnd = random.Random(seed)
        self._dots: list[tuple[ft.Container, float, float]] = []  # (ctrl, diameter, peak op)
        for i in range(count):
            r = self._rnd.random()
            d = dot[0] + (dot[1] - dot[0]) * r * r  # mostly small, a few big soft ones
            op = 1.0 if d < (dot[0] + dot[1]) / 2 else self._rnd.uniform(0.55, 0.85)
            ctrl = soft_dot(d, colors[i % len(colors)], core=core, op=1.0,
                            glow=(i % 4 == 0 and d >= 5))
            self._dots.append((ctrl, d, op))
        super().__init__(content=ft.Stack([c for c, _, _ in self._dots], width=size, height=size,
                                          clip_behavior=ft.ClipBehavior.NONE),
                         width=size, height=size, ignore_interactions=True)
        self.prime()

    def set_colors(self, colors: Sequence[str], core: str = WHITE) -> None:
        for i, (ctrl, _, _) in enumerate(self._dots):
            _repaint_dot(ctrl, colors[i % len(colors)], core)

    def prime(self) -> None:
        """Snap every particle back to its start (no animation) and hide it."""
        c, rnd = self._mid, self._rnd
        for ctrl, d, _ in self._dots:
            ctrl.animate_position = ctrl.animate_opacity = ctrl.animate_scale = _SNAP
            if self._mode == "rise":
                x, y = rnd.uniform(0, self._size), rnd.uniform(c * 0.9, self._size)
            else:
                x, y = c + rnd.uniform(-6, 6), c + rnd.uniform(-6, 6)
            ctrl.left, ctrl.top = x - d / 2, y - d / 2
            ctrl.opacity, ctrl.scale = 0, 1

    def burst(self, speed: float = 1.0) -> None:
        """Start the motion (burst outward, or float up in rise mode)."""
        rnd = self._rnd
        for ctrl, d, op in self._dots:
            lo, hi = self._ms
            ms = rnd.uniform(lo, hi) / max(0.1, speed)
            if self._mode == "rise":
                dx, dy = rnd.uniform(-24, 24), -rnd.uniform(*self._reach)
                curve = ft.AnimationCurve.EASE_OUT_SINE
            else:
                ang = rnd.uniform(0, TAU)
                dist = rnd.uniform(*self._reach) * (0.55 + 0.45 * rnd.random())
                dx, dy = dist * math.cos(ang), dist * math.sin(ang) - self._lift
                curve = ft.AnimationCurve.EASE_OUT_CUBIC
            ctrl.animate_position = _anim(ms, curve)
            ctrl.animate_opacity = _anim(160 if self._mode == "burst" else 700)
            ctrl.animate_scale = _anim(ms, curve)
            ctrl.left = (ctrl.left or 0) + dx
            ctrl.top = (ctrl.top or 0) + dy
            ctrl.opacity = op * rnd.uniform(0.75, 1.0)
            ctrl.scale = rnd.uniform(0.6, 1.0) if self._mode == "burst" else rnd.uniform(0.8, 1.3)

    rise = burst

    def fade(self, ms: tuple[int, int] = (450, 900)) -> None:
        for ctrl, _, _ in self._dots:
            ctrl.animate_opacity = _anim(self._rnd.uniform(*ms), ft.AnimationCurve.EASE_IN)
            ctrl.opacity = 0


def _bloom(side: float, *, diamond: bool = False) -> ft.Container:
    """Big soft light behind a frame (painted per show with _paint_bloom). Breathes via scale."""
    return ft.Container(width=side, height=side, opacity=0, scale=0.6,
                        shape=None if diamond else ft.BoxShape.CIRCLE,
                        border_radius=side * 0.18 if diamond else None,
                        rotate=math.pi / 4 if diamond else 0,
                        animate_opacity=_anim(520), animate_scale=_anim(1600, CUBIC))


def _paint_bloom(ctrl: ft.Container, color: str, op: float = 0.4) -> None:
    ctrl.gradient = ft.RadialGradient(colors=[a(color, op), a(color, op * 0.4), a(color, 0)],
                                      stops=[0, 0.5, 1])
    ctrl.shadow = ft.BoxShadow(blur_radius=(ctrl.width or 100) * 0.35,
                               color=a(color, op * 0.35))


# --------------------------------------------------------------------------- overlay base


class _Overlay(ft.Container):
    """Full-screen overlay host: background layer + centred stage (fixed size, children may
    overflow) + reduce-mode card + tap-to-skip layer."""

    STAGE_W = 340
    STAGE_H = 340

    def __init__(self, *, reduce: bool | None = None) -> None:
        self.reduce = reduce
        self._lock = asyncio.Lock()
        self._skip = asyncio.Event()
        # soft backdrop: the app (and the MindSpace behind it) blurs and dims instead of being
        # covered by a solid sheet - the effect feels like it happens *in* the space
        self._bg = _fill(ft.Container(opacity=0, animate_opacity=_anim(280),
                                      blur=_backdrop_blur()))
        self._stage = ft.Stack([], width=self.STAGE_W, height=self.STAGE_H,
                               clip_behavior=ft.ClipBehavior.NONE)
        self._stage_box = _fill(ft.Container(self._stage, alignment=ft.Alignment.CENTER,
                                             scale=1, animate_scale=_anim(380, CUBIC),
                                             offset=ft.Offset(0, 0), animate_offset=_SNAP))
        self._fx = _fill(ft.Container(
            ft.Stack([self._bg, self._stage_box], expand=True),
            ignore_interactions=True, opacity=1, animate_opacity=_anim(320)))
        # reduce-mode card
        self._s_eyebrow = ft.Text("", size=10, weight=ft.FontWeight.BOLD,
                                  style=ft.TextStyle(letter_spacing=3))
        self._s_title = ft.Text("", size=22, weight=ft.FontWeight.W_800, color="#E4F0FF",
                                text_align=ft.TextAlign.CENTER)
        self._s_sub = ft.Text("", size=12, color="#8FA4C2", text_align=ft.TextAlign.CENTER)
        self._s_card = ft.Container(
            ft.Column([self._s_eyebrow, self._s_title, self._s_sub], tight=True, spacing=4,
                      horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            bgcolor=a("#0D1524", 0.97), border_radius=16, width=300,
            padding=ft.Padding.symmetric(vertical=20, horizontal=24),
            opacity=0, animate_opacity=_anim(220))
        self._simple = _fill(ft.Container(self._s_card, alignment=ft.Alignment.CENTER,
                                          visible=False, ignore_interactions=True))
        self._tap = _fill(ft.Container(bgcolor=a("#000000", 0.01), on_click=self._on_tap))
        super().__init__(content=ft.Stack([self._fx, self._simple, self._tap], expand=True),
                         expand=True, visible=False)

    # ---------------------------------------------------------------- plumbing
    def _reduced(self) -> bool:
        return reduced() if self.reduce is None else bool(self.reduce)

    def _on_tap(self, _: Any = None) -> None:
        self._skip.set()

    def skip(self) -> None:
        self._skip.set()

    def _impact(self, strength: float, color: str, *, y: float | None = None) -> None:
        """Screen distortion at the effect's impact frame: the app root and this overlay's
        stage both punch + jitter (the stage is what the eye is on - the root sits under the
        dimmed backdrop)."""
        distort(self, strength, y=y, color=color, also=(self._stage_box,))

    async def _wait(self, seconds: float) -> bool:
        """Sleep, waking early on tap. True if skipped."""
        if self._skip.is_set():
            return True
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(self._skip.wait(), seconds * _slowmo[0])
        return self._skip.is_set()

    async def _watchdog(self) -> None:
        await _sleep(MAX_BLOCK_S)
        self._tap.visible = False
        self.ignore_interactions = True
        _refresh(self)

    async def _play(self, run: Callable[[], Awaitable[None]], *, title: str, eyebrow: str,
                    subtitle: str | None, color: str, hold: float = 1.2,
                    stop: asyncio.Event | None = None,
                    on_start: Callable[[], Any] | None = None) -> None:
        if not _mounted(self):
            return
        async with self._lock:
            self._skip.clear()
            self._tap.visible = True
            self.ignore_interactions = False
            dog = asyncio.ensure_future(self._watchdog())
            try:
                if self._reduced():
                    _fire(on_start)  # the simple card appears right away
                    await self._play_simple(title, eyebrow, subtitle, color, hold, stop)
                else:
                    await run()
            finally:
                dog.cancel()
                self.visible = False
                self.ignore_interactions = False
                self._tap.visible = True
                _refresh(self)

    async def _play_simple(self, title: str, eyebrow: str, subtitle: str | None, color: str,
                           hold: float, stop: asyncio.Event | None) -> None:
        self._s_eyebrow.value, self._s_eyebrow.color = eyebrow.upper(), color
        self._s_title.value = title
        self._s_sub.value, self._s_sub.visible = subtitle or "", bool(subtitle)
        self._s_card.border = ft.Border.all(1, a(color, 0.55))
        self._s_card.shadow = ft.BoxShadow(blur_radius=24, color=a(color, 0.22))
        self._s_card.opacity = 0
        self._fx.visible, self._simple.visible = False, True
        self.visible = True
        _refresh(self)
        await _sleep(0.04)
        self._s_card.opacity = 1
        _refresh(self)
        t0 = time.perf_counter()
        await self._wait(hold)
        while stop is not None and not stop.is_set() and not self._skip.is_set() \
                and time.perf_counter() - t0 < 12:
            await _sleep(0.05)
        self._s_card.opacity = 0
        _refresh(self)
        await _sleep(0.23)

    async def _open(self) -> None:
        """Show the (already primed) full effect; next refresh starts its animations."""
        self._fx.animate_opacity = _anim(320)
        self._fx.opacity = 1
        self._stage_box.scale = 1
        self._fx.visible, self._simple.visible = True, False
        self.visible = True
        _refresh(self)
        await _sleep(0.04)

    async def _close(self, ms: int = 340, scale: float = 1.05) -> None:
        if self._skip.is_set():
            ms = 170
        self._fx.animate_opacity = _anim(ms)
        self._fx.opacity = 0
        self._stage_box.scale = scale
        _refresh(self)
        await _sleep(ms / 1000 + 0.02)
        self._stage_box.offset = ft.Offset(0, 0)


# --------------------------------------------------------------------------- 1 NoticeEmblem


class NoticeEmblem(_Overlay):
    """Skill / notice acquired: diamond double-frame emblem, stacked title, top light burst,
    warp starfield, cyan-teal nebula. ~2.2 s.

    `await notice.show("Onion Dicing", "SKILL ACQUIRED", subtitle="Chef Path")`
    """

    STAGE_W, STAGE_H = 340, 400
    D = 196  # diamond side; half-diagonal = D / sqrt(2) ~ 139
    ICO = 150

    def __init__(self, *, reduce: bool | None = None) -> None:
        super().__init__(reduce=reduce)
        cx, cy = 170, 205
        hd = self.D / math.sqrt(2)
        top_y = cy - hd
        self._stars = _place(Starfield(860, 860, count=40, streaks=12,
                                       colors=(WHITE, CYAN, "#9FF6FF"), seed=11), cx, cy)
        self._blobs = [_blob(cx + dx, cy + dy, d, col, op) for dx, dy, d, col, op in (
            (-150, 40, 380, TEAL, 0.42), (130, -90, 300, CYAN, 0.24),
            (150, 120, 260, VIOLET, 0.20), (-90, -170, 260, "#1E6F8A", 0.40),
            (0, 170, 420, "#0F4C5C", 0.34), (-40, -60, 220, "#2FD6C9", 0.16))]
        self._rays = _place(_rays_canvas(640, 26, seed=4, colors=(WHITE, CYAN, "#BFFAFF"),
                                         r0=10, up_bias=True), cx, top_y)
        self._halo = self._frame(self.D + 24)
        self._outer = self._frame(self.D)
        self._inner = self._frame(self.D - 18)
        for f in (self._halo, self._outer, self._inner):
            _place(f, cx, cy)
        self._marks = [_place(ft.Container(width=7, height=7, rotate=math.pi / 4, opacity=0,
                                           animate_opacity=_anim(400)), cx + dx, cy)
                       for dx in (-hd - 12, hd + 12)]
        self._line = ft.Container(width=1.4, height=190, left=cx - 0.7, top=cy + hd + 2,
                                  opacity=0, animate_opacity=_anim(500))
        self._line_up = ft.Container(width=1.2, height=60, left=cx - 0.6, top=top_y - 64,
                                     opacity=0, animate_opacity=_anim(500))
        self._flare = _place(Flare(210), cx, top_y)
        self._eyebrow = ft.Text("", size=9.5, weight=ft.FontWeight.BOLD,
                                style=ft.TextStyle(letter_spacing=3.2))
        self._title = ft.Text("", weight=ft.FontWeight.W_900, color=WHITE, width=146,
                              text_align=ft.TextAlign.CENTER, max_lines=3)
        self._stars_row = ft.Row(
            [ft.Icon(ft.Icons.STAR, size=13, color="#F5C66B") for _ in range(3)],
            spacing=2, tight=True, alignment=ft.MainAxisAlignment.CENTER,
        )
        self._sub = ft.Text("", size=10.5, color="#B9D8E6", text_align=ft.TextAlign.CENTER,
                            width=150, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)
        self._rule = ft.Container(width=46, height=1)
        self._chroma = _Chroma(self._title)
        self._claim_btn = ft.Container(
            ft.Row([
                ft.Icon(ft.Icons.CHECK, size=11, color="#070B14"),
                ft.Text("EQUIP", size=8.5, weight=ft.FontWeight.W_900, color="#070B14"),
            ], spacing=3, tight=True, alignment=ft.MainAxisAlignment.CENTER),
            bgcolor=CYAN, border_radius=999,
            padding=ft.Padding.symmetric(horizontal=10, vertical=3),
            border=ft.Border.all(1, WHITE),
            shadow=ft.BoxShadow(blur_radius=8, color=a(CYAN, 0.6)),
            on_click=lambda _: self._skip.set(),
        )
        self._content = _place(ft.Container(
            ft.Column([self._eyebrow, self._rule, self._chroma.wrap, self._stars_row, self._sub, self._claim_btn],
                      tight=True, spacing=3, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            width=200, height=200, alignment=ft.Alignment.CENTER, opacity=0,
            offset=ft.Offset(0, 0.1), animate_opacity=_anim(420),
            animate_offset=_anim(500, CUBIC)), cx, cy + 4)
        self._side = ft.Text("", size=7.5, weight=ft.FontWeight.BOLD, no_wrap=True,
                             style=ft.TextStyle(letter_spacing=1.8))
        self._side_box = _place(ft.Container(self._side, width=88, height=12,
                                             alignment=ft.Alignment.CENTER, rotate=math.pi / 2,
                                             opacity=0, animate_opacity=_anim(500)),
                                cx + 76, cy - 6)
        self._bloom = _place(_bloom(self.D * 1.55, diamond=True), cx, cy)
        self._bloom_top = _place(_bloom(300), cx, top_y)
        self._sparks = _place(Sparks(420, 30, (WHITE, CYAN, "#9FF6FF"), seed=5,
                                     reach=(70, 210), dot=(2.5, 11), lift=10), cx, top_y)
        self._motes = _place(Sparks(380, 22, (CYAN, "#9FF6FF", MINT, "#F5C66B"), seed=8, mode="rise",
                                    reach=(90, 220), dot=(3, 14), ms=(2200, 3200)), cx, cy + 30)
        self._magic_circle = _place(self._make_magic_circle(280, CYAN), cx, cy)
        # the crystal: charges at the centre, then rises to crown the emblem on impact
        self._ico = _place(Icosphere(self.ICO, freq=2, facets=True, seed=3), cx, cy)
        self._ico.animate_position = _anim(460, CUBIC)  # positioned in the stage Stack
        self._ico_home = (self._ico.left, self._ico.top)
        self._ico_crown = (cx - self.ICO / 2, top_y - self.ICO / 2)
        self._stage.controls = [self._stars, *self._blobs, self._magic_circle, self._bloom_top, self._rays,
                                self._motes, self._bloom, self._line, self._line_up, self._halo,
                                self._outer, self._inner, *self._marks, self._side_box,
                                self._content, self._ico, self._sparks, self._flare]
        self._bg.gradient = ft.RadialGradient(
            center=ft.Alignment(0, -0.2), radius=1.1,
            colors=[a("#0C2A38", 0.86), a(NAVY, 0.9), a("#03050A", 0.95)], stops=[0, 0.5, 1])

    @staticmethod
    def _frame(side: float) -> ft.Container:
        return ft.Container(width=side, height=side, rotate=math.pi / 4, scale=0.55, opacity=0,
                            animate_rotation=_anim(720, CUBIC), animate_scale=_anim(620, BACK),
                            animate_opacity=_anim(300))

    @staticmethod
    def _make_magic_circle(size: float, col: str) -> ft.Container:
        s = int(size)
        c = s / 2
        shapes: list[cv.Shape] = [
            cv.Circle(c, c, c - 2, paint=_stroke(a(col, 0.45), 1.2)),
            cv.Circle(c, c, c - 14, paint=_stroke(a(col, 0.25), 0.8)),
            cv.Path(_ticks(c, c, c - 13, c - 3, 24), paint=_stroke(a(col, 0.5), 1)),
            cv.Circle(c, c, c - 28, paint=_stroke(a(col, 0.2), 0.8, dash=[4, 4])),
        ]
        return ft.Container(
            cv.Canvas(shapes, width=s, height=s), width=s, height=s,
            opacity=0, rotate=0, animate_opacity=_anim(400),
            animate_rotation=_anim(2800, LINEAR),
        )

    def _paint(self, col: str) -> None:
        self._outer.border = ft.Border.all(1.6, a(col, 0.95))
        self._outer.gradient = ft.LinearGradient(begin=ft.Alignment.TOP_LEFT,
                                                 end=ft.Alignment.BOTTOM_RIGHT,
                                                 colors=[a("#0C2738", 0.94), a("#040A14", 0.96)])
        self._outer.shadow = [ft.BoxShadow(blur_radius=26, color=a(col, 0.5)),
                              ft.BoxShadow(blur_radius=80, spread_radius=6, color=a(TEAL, 0.25))]
        self._inner.border = ft.Border.all(1, a(col, 0.6))
        self._halo.border = ft.Border.all(0.8, a(col, 0.3))
        for m in self._marks:
            m.bgcolor = col
            m.shadow = ft.BoxShadow(blur_radius=8, color=a(col, 0.9))
        down = [a(col, 0.9), a(col, 0)]
        self._line.gradient = ft.LinearGradient(begin=ft.Alignment.TOP_CENTER,
                                                end=ft.Alignment.BOTTOM_CENTER, colors=down)
        self._line_up.gradient = ft.LinearGradient(begin=ft.Alignment.BOTTOM_CENTER,
                                                   end=ft.Alignment.TOP_CENTER, colors=down)
        self._flare.set_color(col)
        _paint_bloom(self._bloom, col, 0.32)
        _paint_bloom(self._bloom_top, col, 0.45)
        self._sparks.set_colors((WHITE, col, "#9FF6FF", "#F5C66B"))
        self._motes.set_colors((col, "#4FE3F0", "#A78BFA", "#F5C66B"))
        self._ico.set_color(col)
        self._claim_btn.bgcolor = col
        self._eyebrow.color = col
        self._side.color = a(col, 0.85)
        self._rule.bgcolor = a(col, 0.7)
        self._title.style = ft.TextStyle(letter_spacing=1, height=1.05, shadow=[
            ft.BoxShadow(blur_radius=14, color=a(col, 0.85)),
            ft.BoxShadow(blur_radius=3, color=a("#000000", 0.6))])

    async def show(self, title: str, eyebrow: str = "SKILL ACQUIRED",
                   subtitle: str | None = None, color: str | None = None, *,
                   side: str = "LUMA · NOTICE") -> None:
        col = color or CYAN

        async def run() -> None:
            self._paint(col)
            self._eyebrow.value = eyebrow.upper()
            self._title.value = title
            self._title.size = _title_size(title, ((7, 36), (10, 31), (13, 27), (18, 23),
                                                   (99, 19)))
            self._sub.value, self._sub.visible = subtitle or "", bool(subtitle)
            self._side.value = side.upper()
            # prime (hidden)
            self._bg.opacity = 0
            self._stars.prime()
            for b in self._blobs:
                b.opacity, b.scale = 0, 0.85
            self._rays.opacity, self._rays.rotate = 0, -0.05
            for f, r0 in ((self._halo, 0.0), (self._outer, math.pi / 2),
                          (self._inner, -math.pi / 2)):
                f.rotate, f.scale, f.opacity = math.pi / 4 + r0, 0.55, 0
            for m in (*self._marks, self._line, self._line_up, self._side_box):
                m.opacity = 0
            self._content.opacity, self._content.offset = 0, ft.Offset(0, 0.1)
            self._flare.prime()
            self._magic_circle.opacity, self._magic_circle.rotate = 0, 0
            for bl in (self._bloom, self._bloom_top):
                bl.opacity, bl.scale = 0, 0.6
            self._sparks.prime()
            self._motes.prime()
            self._chroma.prime()
            self._ico.prime(0.2)
            self._ico.animate_position = _SNAP
            self._ico.left, self._ico.top = self._ico_home
            await self._open()
            # charge: the crystal spins up in the middle of the space
            _buzz("light")
            self._bg.opacity = 1
            self._stars.warp(2.8, 1.35)
            for b in self._blobs:
                b.opacity, b.scale = 0.7, 1.0
            self._bloom.opacity, self._bloom.scale = 0.55, 0.8
            self._magic_circle.opacity, self._magic_circle.rotate = 0.55, math.pi / 2
            self._ico.appear(380, 1.0, energy=0.9)
            self._ico.start(5.0)
            _refresh(self)
            await self._wait(0.24)
            self._ico.flare(5)
            await self._wait(0.18)
            # impact: the crystal kicks and rises to the crown, the emblem slams in
            _buzz("medium")
            self._ico.animate_position = _anim(460, CUBIC)
            self._ico.left, self._ico.top = self._ico_crown
            self._ico.punch(1.3, 1.0, settle=0.62)
            for b in self._blobs:
                b.opacity, b.scale = 1, 1.1
            self._rays.opacity, self._rays.rotate = 0.95, 0.07
            self._flare.burst(300, 1.15)
            self._bloom_top.opacity, self._bloom_top.scale = 1, 1.15
            self._magic_circle.opacity, self._magic_circle.rotate = 0.9, math.pi
            self._sparks.burst()
            self._motes.rise()
            self._impact(0.85, col)
            _refresh(self)
            await self._wait(0.12)
            for f in (self._halo, self._outer, self._inner):
                f.rotate, f.scale, f.opacity = math.pi / 4, 1, 1
            for m in (*self._marks, self._line, self._line_up):
                m.opacity = 1
            self._bloom.opacity, self._bloom.scale = 1, 1.05
            _refresh(self)
            await self._wait(0.26)
            self._content.opacity, self._content.offset = 1, ft.Offset(0, 0)
            self._side_box.opacity = 1
            self._flare.settle(0.6, 0.85)
            self._sparks.fade((600, 1100))
            self._bloom_top.opacity, self._bloom_top.scale = 0.55, 0.9
            _refresh(self)
            _spawn(self._chroma.hit(0.8))
            await self._wait(0.9)
            self._bloom.scale = 0.92  # slow breath out before leaving
            self._ico.flare(3)
            _refresh(self)
            await self._wait(0.55)
            self._flare.fade()
            self._motes.fade((250, 400))
            self._magic_circle.opacity = 0
            self._ico.vanish(300, 1.2)
            await self._close()
            self._ico.stop()

        await self._play(run, title=title, eyebrow=eyebrow, subtitle=subtitle, color=col)


# --------------------------------------------------------------------------- 2 MilestoneSeal


class MilestoneSeal(_Overlay):
    """Level-up / rank-up / achievement: concentric gold rings of invented glyphs rotating in
    opposite directions, a diamond seal with circuit traces, bright core flare and light rays.
    ~2.4 s. `await seal.show("LEVEL 5", "Individual level increased")`"""

    STAGE_W, STAGE_H = 340, 470
    CX, CY = 170, 185

    def __init__(self, *, reduce: bool | None = None) -> None:
        super().__init__(reduce=reduce)
        cx, cy = self.CX, self.CY
        self._bg.gradient = ft.RadialGradient(
            center=ft.Alignment(0, -0.22), radius=1.0,
            colors=[a("#4A3412", 0.88), a("#170F06", 0.92), a("#04060B", 0.96)],
            stops=[0, 0.45, 1])
        self._blobs = [_blob(cx + dx, cy + dy, d, col, op) for dx, dy, d, col, op in (
            (-130, -60, 300, AMBER, 0.30), (130, 80, 320, "#E0A040", 0.26),
            (0, 0, 380, GOLD, 0.24), (140, -130, 220, "#7FD6C8", 0.14),
            (-140, 150, 240, VIOLET, 0.14))]
        self._rays = _place(_rays_canvas(900, 40, seed=9, colors=(CREAM, GOLD, WHITE), r0=40,
                                         op=(.3, .7), width=(.7, 2.6)), cx, cy)
        self._stars = _place(Starfield(860, 860, count=42, streaks=16,
                                       colors=(GOLD, CREAM, AMBER), seed=21, hole=90), cx, cy)
        self._ring_a = _place(self._ring(340, (166, 162, 136, 132), 149, 30, 13, seed=2), cx, cy)
        self._ring_b = _place(self._ring(270, (126, 100), 113, 24, 10, seed=5, dashed=92),
                              cx, cy)
        self._seal = _place(self._seal_canvas(), cx, cy)
        self._flare = _place(Flare(160, GOLD, core=WHITE, streak=2.2), cx, cy)
        self._eyebrow = ft.Text("", size=10, weight=ft.FontWeight.BOLD, color=GOLD,
                                style=ft.TextStyle(letter_spacing=3.6))
        self._title = ft.Text("", weight=ft.FontWeight.W_900, color=CREAM, max_lines=2,
                              text_align=ft.TextAlign.CENTER, width=320,
                              style=ft.TextStyle(letter_spacing=1.5, shadow=[
                                  ft.BoxShadow(blur_radius=18, color=a(AMBER, 0.85)),
                                  ft.BoxShadow(blur_radius=3, color=a("#000000", 0.7))]))
        self._sub = ft.Text("", size=12.5, color=a(GOLD, 0.9), text_align=ft.TextAlign.CENTER,
                            width=300)
        self._chroma = _Chroma(self._title)
        self._text = ft.Container(
            ft.Column([self._eyebrow, self._chroma.wrap, self._sub], tight=True, spacing=4,
                      horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            left=0, width=340, top=cy + 182, alignment=ft.Alignment.TOP_CENTER,
            opacity=0, offset=ft.Offset(0, 0.3), animate_opacity=_anim(400),
            animate_offset=_anim(520, CUBIC))
        self._bloom = _place(_bloom(420), cx, cy)
        _paint_bloom(self._bloom, AMBER, 0.42)
        self._sparks = _place(Sparks(460, 34, (CREAM, GOLD, AMBER, WHITE), seed=12,
                                     reach=(110, 240), dot=(2.5, 12), lift=20, core=CREAM),
                              cx, cy)
        self._motes = _place(Sparks(420, 18, (GOLD, CREAM, AMBER), seed=14, mode="rise",
                                    reach=(120, 260), dot=(3, 15), ms=(2200, 3300),
                                    core=CREAM), cx, cy + 60)
        self._ico = _place(Icosphere(230, freq=2, color=GOLD, core=CREAM, facets=True, seed=9,
                                     tilt=0.5), cx, cy)
        self._stage.controls = [*self._blobs, self._bloom, self._rays, self._stars, self._motes,
                                self._ico, self._ring_a, self._ring_b, self._seal, self._sparks,
                                self._flare, self._text]

    @staticmethod
    def _ring(size: int, circles: Sequence[float], glyph_r: float, count: int, gsize: float,
              *, seed: int, dashed: float | None = None) -> ft.Container:
        c = size / 2
        shapes: list[cv.Shape] = []
        for i, r in enumerate(circles):
            shapes.append(cv.Circle(c, c, r, paint=_stroke(a(GOLD, 0.85 if i % 2 == 0 else 0.35),
                                                           1.3 if i % 2 == 0 else 0.6)))
        els = glyphs.ring_elements(c, c, glyph_r, count, gsize, seed=seed)
        shapes.append(cv.Path(els, paint=_stroke(a(AMBER, 0.22), 4.5)))  # glow pass
        shapes.append(cv.Path(els, paint=_stroke("#FFD98A", 1.5)))
        if dashed:
            shapes.append(cv.Circle(c, c, dashed, paint=_stroke(a(GOLD, 0.5), 2.2,
                                                                dash=[2, 5])))
        return ft.Container(cv.Canvas(shapes, width=size, height=size), width=size,
                            height=size, opacity=0, scale=1.5, rotate=0,
                            animate_opacity=_anim(450), animate_scale=_anim(650, CUBIC),
                            animate_rotation=_anim(2800, LINEAR))

    @staticmethod
    def _seal_canvas() -> ft.Container:
        s, c = 210, 105
        hd, hd2, sq = 96, 85, 30

        def diamond(h: float) -> list[cv.Path.PathElement]:
            return [cv.Path.MoveTo(c, c - h), cv.Path.LineTo(c + h, c), cv.Path.LineTo(c, c + h),
                    cv.Path.LineTo(c - h, c), cv.Path.Close()]

        def square(h: float) -> list[cv.Path.PathElement]:
            return [cv.Path.MoveTo(c - h, c - h), cv.Path.LineTo(c + h, c - h),
                    cv.Path.LineTo(c + h, c + h), cv.Path.LineTo(c - h, c + h), cv.Path.Close()]

        fill = ft.PaintRadialGradient(center=ft.Offset(c, c), radius=hd,
                                      colors=["#4A3511", "#1A1207", "#0C0804"],
                                      color_stops=[0, 0.6, 1])
        circ, ends = glyphs.circuit_elements(c, c, sq + 4, hd2, seed=7)
        ticks: list[cv.Path.PathElement] = []
        for k in range(4):  # little ticks outside each diamond edge
            ax, ay = math.cos(k * math.pi / 2), math.sin(k * math.pi / 2)
            bx, by = math.cos((k + 1) * math.pi / 2), math.sin((k + 1) * math.pi / 2)
            for j in range(1, 8):
                t = j / 8
                px, py = c + hd * (ax + (bx - ax) * t), c + hd * (ay + (by - ay) * t)
                nx, ny = (ax + bx) / math.sqrt(2), (ay + by) / math.sqrt(2)
                ticks += [cv.Path.MoveTo(px + nx * 2, py + ny * 2),
                          cv.Path.LineTo(px + nx * 6, py + ny * 6)]
        marks: list[cv.Path.PathElement] = []
        for k in range(4):  # one glyph on each axis, between the circuit lanes
            th_ = k * math.pi / 2 - math.pi / 2
            marks += glyphs.glyph_elements(k * 3 + 1, c + 60 * math.cos(th_),
                                           c + 60 * math.sin(th_), 11, th_ + math.pi / 2)
        core = ft.PaintRadialGradient(center=ft.Offset(c, c), radius=24,
                                      colors=[WHITE, "#FFE6A8", a(GOLD, 0.2)],
                                      color_stops=[0, 0.5, 1])
        shapes: list[cv.Shape] = [
            cv.Path(diamond(hd), paint=_solid("#140E06", fill)),
            cv.Path(diamond(hd), paint=_stroke(a(AMBER, 0.3), 5)),
            cv.Path(diamond(hd), paint=_stroke(GOLD, 1.7)),
            cv.Path(diamond(hd2), paint=_stroke(a(GOLD, 0.6), 1)),
            cv.Path(ticks, paint=_stroke(a(GOLD, 0.75), 1)),
            cv.Path(circ, paint=_stroke(a(GOLD, 0.85), 1.1)),
            cv.Path(marks, paint=_stroke(a("#FFE2A0", 0.95), 1.3)),
            cv.Path(square(sq + 4), paint=_stroke(a(GOLD, 0.45), 0.7)),
            cv.Path(square(sq), paint=_stroke(GOLD, 1.4)),
            cv.Rect(c - 17, c - 17, 20, 20, paint=_solid(WHITE, core)),
            cv.Rect(c - 3, c - 3, 20, 20, paint=_solid(WHITE, core)),
            cv.Rect(c - 17, c - 17, 20, 20, paint=_stroke(a(CREAM, 0.9), 1)),
            cv.Rect(c - 3, c - 3, 20, 20, paint=_stroke(a(CREAM, 0.9), 1)),
        ]
        shapes += [cv.Circle(x, y, 1.9, paint=_solid(GOLD)) for x, y in ends]
        for k in range(4):  # vertex studs
            th_ = k * math.pi / 2
            shapes.append(cv.Circle(c + (hd + 1) * math.cos(th_), c + (hd + 1) * math.sin(th_),
                                    3.2, paint=_solid(CREAM)))
        return ft.Container(cv.Canvas(shapes, width=s, height=s), width=s, height=s,
                            opacity=0, scale=0.2, rotate=-math.pi / 2,
                            shadow=None, animate_opacity=_anim(250),
                            animate_scale=_anim(640, BACK), animate_rotation=_anim(700, CUBIC))

    async def show(self, title: str, subtitle: str | None = None, *,
                   eyebrow: str = "MILESTONE") -> None:
        async def run() -> None:
            self._eyebrow.value = eyebrow.upper()
            self._title.value = title
            self._title.size = _title_size(title, ((10, 32), (16, 26), (99, 21)))
            self._sub.value, self._sub.visible = subtitle or "", bool(subtitle)
            # prime
            self._bg.opacity = 0
            for b in self._blobs:
                b.opacity, b.scale = 0, 0.85
            self._rays.opacity, self._rays.rotate = 0, 0
            self._stars.prime()
            for r, s0 in ((self._ring_a, 1.5), (self._ring_b, 1.7)):
                r.opacity, r.scale, r.rotate = 0, s0, 0
            self._seal.opacity, self._seal.scale, self._seal.rotate = 0, 0.2, -math.pi / 2
            self._flare.prime()
            self._text.opacity, self._text.offset = 0, ft.Offset(0, 0.3)
            self._bloom.opacity, self._bloom.scale = 0, 0.6
            self._sparks.prime()
            self._motes.prime()
            self._chroma.prime()
            self._ico.prime(0.25)
            await self._open()
            # charge: a golden crystal spins up while the glyph rings close in
            _buzz("light")
            self._bg.opacity = 1
            for b in self._blobs:
                b.opacity, b.scale = 0.75, 1.0
            self._stars.warp(2.9, 1.3)
            self._ring_a.opacity, self._ring_a.scale, self._ring_a.rotate = 0.8, 1.04, 0.3
            self._ring_b.opacity, self._ring_b.scale, self._ring_b.rotate = 0.8, 1.06, -0.4
            self._bloom.opacity, self._bloom.scale = 0.5, 0.8
            self._ico.appear(420, 0.78, energy=1.0)
            self._ico.start(5.5)
            _refresh(self)
            await self._wait(0.22)
            self._ico.flare(6)
            await self._wait(0.24)
            # impact: the seal slams in front of the crystal, which bursts outward behind it
            _buzz("heavy")
            for b in self._blobs:
                b.opacity, b.scale = 1, 1.1
            self._rays.opacity, self._rays.rotate = 0.9, 0.14
            self._ring_a.opacity, self._ring_a.scale, self._ring_a.rotate = 1, 1, 0.55
            self._ring_b.opacity, self._ring_b.scale, self._ring_b.rotate = 1, 1, -0.75
            self._seal.opacity, self._seal.scale, self._seal.rotate = 1, 1, 0
            self._ico.punch(1.75, 1.0, settle=1.5, facets=10)
            self._ico.animate_opacity = _anim(900, ft.AnimationCurve.EASE_OUT)
            self._ico.opacity = 0.55
            self._flare.burst(280, 1.25)
            self._sparks.burst()
            self._motes.rise()
            self._bloom.opacity, self._bloom.scale = 1, 1.15
            self._impact(1.0, GOLD)
            _refresh(self)
            await self._wait(0.3)
            self._flare.settle(0.55, 0.9)
            self._text.opacity, self._text.offset = 1, ft.Offset(0, 0)
            self._sparks.fade((700, 1200))
            _refresh(self)
            _spawn(self._chroma.hit(1.0))
            await self._wait(0.8)
            self._ico.flare(4)
            await self._wait(0.7)
            self._flare.fade()
            self._motes.fade((250, 400))
            self._ico.vanish(360, 1.9)
            await self._close(360, 1.08)
            self._ico.stop()

        await self._play(run, title=title, eyebrow=eyebrow, subtitle=subtitle, color=GOLD)


# --------------------------------------------------------------------------- 3 LumenThinking

_PHI = (1 + math.sqrt(5)) / 2
_ICO = [(-1, _PHI, 0), (1, _PHI, 0), (-1, -_PHI, 0), (1, -_PHI, 0), (0, -1, _PHI),
        (0, 1, _PHI), (0, -1, -_PHI), (0, 1, -_PHI), (_PHI, 0, -1), (_PHI, 0, 1),
        (-_PHI, 0, -1), (-_PHI, 0, 1)]
_ICO = [(x / math.hypot(1, _PHI), y / math.hypot(1, _PHI), z / math.hypot(1, _PHI))
        for x, y, z in _ICO]
_ICO_EDGES = [(i, j) for i in range(12) for j in range(i + 1, 12)
              if math.dist(_ICO[i], _ICO[j]) < 1.06 * 1.0515]  # edge = 1.0515 on unit sphere
_RING = [(math.cos(TAU * k / 28), math.sin(TAU * k / 28), 0.0) for k in range(29)]


def _rot(p: tuple[float, float, float], ay: float, ax: float) -> tuple[float, float, float]:
    x, y, z = p
    x, z = x * math.cos(ay) + z * math.sin(ay), -x * math.sin(ay) + z * math.cos(ay)
    y, z = y * math.cos(ax) - z * math.sin(ax), y * math.sin(ax) + z * math.cos(ax)
    return x, y, z


# --------------------------------------------------------------------------- pure helpers (tested)

V3 = tuple[float, float, float]


@functools.lru_cache(maxsize=4)
def icosphere_mesh(freq: int = 1) -> tuple[tuple[V3, ...], tuple[tuple[int, int], ...],
                                          tuple[tuple[int, int, int], ...]]:
    """Geodesic icosphere on the unit sphere: an icosahedron whose 20 faces are each split into
    freq² triangles, new vertices pushed out to radius 1. Returns (vertices, edges, faces).
    freq 1 -> 12 / 30 / 20, freq 2 -> 42 / 120 / 80 (V = 10f² + 2, E = 30f², F = 20f²)."""
    freq = max(1, int(freq))
    base_faces = [(i, j, k) for i, j, k in itertools.combinations(range(12), 3)
                  if {(i, j), (i, k), (j, k)} <= set(_ICO_EDGES)]
    verts: list[V3] = []
    index: dict[tuple[int, int, int], int] = {}

    def vid(p: V3) -> int:
        n = math.sqrt(p[0] ** 2 + p[1] ** 2 + p[2] ** 2)
        q = (p[0] / n, p[1] / n, p[2] / n)
        key = (round(q[0] * 1e5), round(q[1] * 1e5), round(q[2] * 1e5))
        if key not in index:
            index[key] = len(verts)
            verts.append(q)
        return index[key]

    faces: list[tuple[int, int, int]] = []
    for fa, fb, fc in base_faces:
        pa, pb, pc = _ICO[fa], _ICO[fb], _ICO[fc]

        def at(i: int, j: int, pa: V3 = pa, pb: V3 = pb, pc: V3 = pc) -> int:
            return vid(tuple(pa[d] + (pb[d] - pa[d]) * i / freq + (pc[d] - pa[d]) * j / freq
                             for d in range(3)))  # type: ignore[arg-type]

        for i in range(freq):
            for j in range(freq - i):
                faces.append((at(i, j), at(i + 1, j), at(i, j + 1)))
                if i + j < freq - 1:
                    faces.append((at(i + 1, j), at(i + 1, j + 1), at(i, j + 1)))
    edges = sorted({(min(a_, b_), max(a_, b_)) for f in faces
                    for a_, b_ in ((f[0], f[1]), (f[1], f[2]), (f[0], f[2]))})
    return tuple(verts), tuple(edges), tuple(faces)


def stage_labels(stages: Sequence[str]) -> tuple[list[str], list[bool]]:
    """Stage texts -> (upper-case names without trailing dots, animate-dots flags). The final
    stage of a multi-stage run stands still ('PROPOSAL READY' has no ticking dots)."""
    names = [s.rstrip().rstrip(".…").upper() for s in stages]
    dots = [s.rstrip().endswith(("…", ".")) for s in stages]
    if len(stages) >= 2:
        dots[-1] = False
    return names, dots


def stage_at(t: float, run_until: float, working: int) -> int:
    """Which working stage (0 .. working-1) shows at time t: the working stages share the time
    before `run_until` evenly; the final (ready) stage is decided by the caller."""
    if working <= 1 or run_until <= 0:
        return 0
    return max(0, min(working - 1, int(t / (run_until / working))))


def _mix(c1: str, c2: str, t: float) -> str:
    """Blend two #RRGGBB colors (t=0 -> c1, 1 -> c2)."""
    def rgb(c: str) -> tuple[int, int, int]:
        c = c.lstrip("#")[-6:]
        return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    try:
        r1, r2 = rgb(c1), rgb(c2)
    except ValueError:
        return c1
    t = max(0.0, min(1.0, t))
    return "#" + "".join(f"{round(x + (y - x) * t):02X}" for x, y in zip(r1, r2, strict=True))


# --------------------------------------------------------------------------- Icosphere


class Icosphere(ft.Container):
    """Glowing geodesic wireframe (subdivided icosahedron), rotating in 3D: edges fade with
    depth (4 depth bands, front band gets a soft glow pass), vertices twinkle as sparks, and
    `facets=True` flashes a few front triangles on every punch.

    Choreography (set props, then refresh the host - like Flare):
        ico.prime()                 hidden, small, loop stopped
        ico.appear(); ico.start()   scale-in (back curve) + the frame loop (<= fps, bounded)
        ico.punch(1.3)              impact: quick scale kick, spin whirl, facets flash
        ico.vanish()                scale out + fade, loop stops when it is gone
    The frame loop redraws only its own Canvas, at `fps` (default 24), and always stops by
    itself after `max_s`. ~50-90 shapes per frame at freq 2."""

    def __init__(self, size: int = 180, *, freq: int = 2, color: str = CYAN, core: str = WHITE,
                 fps: int = 24, spin: float = 1.0, facets: bool = False, seed: int = 7,
                 tilt: float = 0.42) -> None:
        self._size = size
        self._verts, self._edges, self._faces = icosphere_mesh(freq)
        self._fps = max(6, min(30, fps))
        self._spin = spin
        self._facets = facets
        self._tilt = tilt
        self._rnd = random.Random(seed)
        self._phase = [self._rnd.uniform(0, TAU) for _ in self._verts]
        self._ay = self._rnd.uniform(0, TAU)
        self._energy = 0.0
        self._flashes: list[list[float]] = []  # [face index, life 0..1]
        self._gen = 0
        self._last = 0.0
        self._canvas = cv.Canvas([], width=size, height=size)
        self._halo = ft.Container(width=size * 0.95, height=size * 0.95, shape=ft.BoxShape.CIRCLE,
                                  left=size * 0.025, top=size * 0.025)
        super().__init__(
            content=ft.Stack([self._halo, self._canvas], width=size, height=size,
                             clip_behavior=ft.ClipBehavior.NONE),
            width=size, height=size, scale=0.3, opacity=0, offset=ft.Offset(0, 0),
            animate_scale=_anim(420, BACK), animate_opacity=_anim(220),
            ignore_interactions=True)
        self.set_color(color, core)
        self._draw(0.0)

    # ---------------------------------------------------------------- look
    def set_color(self, color: str, core: str = WHITE) -> None:
        self._col, self._core = color, core
        self._hot = _mix(color, core, 0.55)  # front edges: color lifted toward white
        self._halo.gradient = ft.RadialGradient(
            colors=[a(core, 0.30), a(color, 0.20), a(color, 0.06), a(color, 0)],
            stops=[0, 0.25, 0.6, 1])

    def _draw(self, dt: float) -> None:
        s = self._size
        c, rr, f = s / 2, s * 0.40, 3.3
        e = self._energy
        self._ay += dt * (0.9 + 7.5 * e) * self._spin
        ax = self._tilt + 0.18 * math.sin(self._ay * 0.37)
        self._energy = e * math.exp(-dt * 2.6)
        pts = []
        for v in self._verts:
            x, y, z = _rot(v, self._ay, ax)
            k = rr * f / (f - z)
            pts.append((c + x * k, c + y * k, z))
        bands: list[list[cv.Path.PathElement]] = [[], [], [], []]
        for i, j in self._edges:
            z = (pts[i][2] + pts[j][2]) / 2
            b = min(3, max(0, int((z + 1) / 2 * 4)))
            bands[b] += [cv.Path.MoveTo(pts[i][0], pts[i][1]), cv.Path.LineTo(pts[j][0], pts[j][1])]
        lift = 0.82 + 0.18 * min(1.0, e * 1.5)
        shapes: list[cv.Shape] = []
        # facet flashes (front faces only), under the wires
        live = []
        for fl in self._flashes:
            fi, life = int(fl[0]), fl[1]
            ia, ib, ic = self._faces[fi]
            if (pts[ia][2] + pts[ib][2] + pts[ic][2]) / 3 > -0.1 and life > 0.02:
                shapes.append(cv.Path([cv.Path.MoveTo(pts[ia][0], pts[ia][1]),
                                       cv.Path.LineTo(pts[ib][0], pts[ib][1]),
                                       cv.Path.LineTo(pts[ic][0], pts[ic][1]), cv.Path.Close()],
                                      paint=_solid(a(self._hot, 0.55 * life))))
            fl[1] = life * math.exp(-dt * 3.2)
            if fl[1] > 0.02:
                live.append(fl)
        self._flashes = live
        for b, (op, w) in enumerate(((0.10, 0.6), (0.22, 0.8), (0.5, 1.0), (0.92, 1.3))):
            if not bands[b]:
                continue
            col = self._col if b < 2 else self._hot
            if b == 3:  # two glow passes on the front band: wide bloom + tight halo
                shapes.append(cv.Path(bands[b], paint=_stroke(a(self._col, 0.07 + 0.08 * e),
                                                              11 + 6 * e)))
                shapes.append(cv.Path(bands[b], paint=_stroke(a(self._col, 0.26 * lift),
                                                              4.4 + 2.5 * e)))
            shapes.append(cv.Path(bands[b], paint=_stroke(a(col, op * lift), w + 0.5 * e)))
        t = self._ay
        for (x, y, z), ph in zip(pts, self._phase, strict=True):
            tw = 0.6 + 0.4 * math.sin(t * 2.3 + ph)
            if z > 0.15:
                r = 1.3 + 1.6 * z + 0.9 * e
                if z > 0.55 and tw > 0.7:  # the sparkiest front points get a halo
                    shapes.append(cv.Circle(x, y, r * 3.2, paint=_solid(a(self._col, 0.16 * tw))))
                shapes.append(cv.Circle(x, y, r, paint=_solid(a(self._core, 0.95 * tw))))
            elif z > -0.4:
                shapes.append(cv.Circle(x, y, 1.0, paint=_solid(a(self._col, 0.45 * tw))))
        self._canvas.shapes = shapes

    # ---------------------------------------------------------------- loop
    def start(self, max_s: float = 6.0) -> None:
        """Run the frame loop (stops on stop()/prime()/vanish(), unmount, or after max_s)."""
        self._gen += 1
        _spawn(self._loop(self._gen, max_s))

    def stop(self) -> None:
        self._gen += 1

    async def _loop(self, gen: int, max_s: float) -> None:
        t0 = last = time.perf_counter()
        step = 1 / self._fps
        while gen == self._gen and _mounted(self):
            now = time.perf_counter()
            if now - t0 > max_s:
                break
            self._draw(min(0.1, now - last))
            last = now
            _refresh(self._canvas)
            await _sleep(max(0.0, step - (time.perf_counter() - now)))

    # ---------------------------------------------------------------- choreography
    def prime(self, scale: float = 0.3) -> None:
        self.stop()
        self.animate_scale = self.animate_opacity = _SNAP
        self.scale, self.opacity = scale, 0
        self._energy, self._flashes = 0.0, []
        self._draw(0.0)

    def appear(self, ms: int = 420, scale: float = 1.0, opacity: float = 1.0,
               energy: float = 0.6) -> None:
        self.animate_scale = _anim(ms, BACK)
        self.animate_opacity = _anim(min(ms, 260))
        self.scale, self.opacity = scale, opacity
        self._energy = max(self._energy, energy)

    def punch(self, scale: float = 1.3, energy: float = 1.0, settle: float = 1.0,
              facets: int | None = None) -> None:
        """Impact: a fast scale kick (then settles back to `settle` by itself), a whirl of spin
        and - with facets - a handful of triangles flashing."""
        self.animate_scale = _anim(110, ft.AnimationCurve.EASE_OUT)
        self.scale = scale
        self._energy = max(self._energy, energy)
        n = (6 if self._facets else 0) if facets is None else facets
        for fi in self._rnd.sample(range(len(self._faces)), min(n, len(self._faces))):
            self._flashes.append([fi, 1.0])
        gen = self._gen

        async def back() -> None:
            await _sleep(0.12)
            if gen == self._gen:
                self.animate_scale = _anim(520, BACK)
                self.scale = settle
                _refresh(self)

        _spawn(back())

    def flare(self, n: int = 4) -> None:
        """Flash a few facets without a scale kick (charging shimmer)."""
        for fi in self._rnd.sample(range(len(self._faces)), min(n, len(self._faces))):
            self._flashes.append([fi, 0.8])
        self._energy = max(self._energy, 0.35)

    def vanish(self, ms: int = 380, scale: float = 1.6) -> None:
        self.animate_scale = _anim(ms, ft.AnimationCurve.EASE_IN_CUBIC)
        self.animate_opacity = _anim(ms, ft.AnimationCurve.EASE_IN)
        self.scale, self.opacity = scale, 0
        gen = self._gen

        async def later() -> None:
            await _sleep(ms / 1000 + 0.05)
            if gen == self._gen:
                self.stop()

        _spawn(later())

    def will_unmount(self) -> None:
        self.stop()


# --------------------------------------------------------------------------- chroma ghost

MAGENTA = "#FF4FD8"


class _Chroma:
    """Chromatic-aberration ghost for a Text: a cyan and a magenta copy under it that jump
    apart on impact and slide back together. `wrap` replaces the Text in its parent."""

    def __init__(self, text: ft.Text) -> None:
        self.text = text
        self._ghosts = [ft.Text("", color=a(col, 0.8)) for col in (CYAN, MAGENTA)]
        self._boxes = [ft.Container(g, opacity=0, offset=ft.Offset(0, 0),
                                    animate_offset=_SNAP, animate_opacity=_SNAP)
                       for g in self._ghosts]
        self.wrap = ft.Stack([*self._boxes, text], alignment=ft.Alignment.CENTER)
        self._gen = 0

    def _sync(self) -> None:
        t = self.text
        st = t.style
        for g in self._ghosts:
            g.value, g.size, g.weight, g.width = t.value, t.size, t.weight, t.width
            g.text_align, g.max_lines, g.no_wrap = t.text_align, t.max_lines, t.no_wrap
            g.style = ft.TextStyle(letter_spacing=getattr(st, "letter_spacing", None),
                                   height=getattr(st, "height", None))

    def prime(self) -> None:
        self._gen += 1
        for b in self._boxes:
            b.animate_offset = b.animate_opacity = _SNAP
            b.opacity, b.offset = 0, ft.Offset(0, 0)

    async def hit(self, strength: float = 1.0) -> None:
        """Split (3-6 px), flicker once, then converge and fade (~0.35 s)."""
        if reduced() or not _mounted(self.text):
            return
        self._gen += 1
        gen = self._gen
        self._sync()
        w = float(self.text.width or max(60, len(self.text.value or "") * (self.text.size or 14)
                                         * 0.62))
        px = 3 + 3 * strength
        for b, sgn in zip(self._boxes, (-1, 1), strict=True):
            b.animate_offset = b.animate_opacity = _SNAP
            b.offset, b.opacity = ft.Offset(sgn * px / w, sgn * -0.02), 0.9
        _refresh(*self._boxes)
        for k, (fx_, op) in enumerate(((-0.55, 0.6), (0.8, 0.75))):
            await _sleep(0.05)
            if gen != self._gen:
                return
            for b, sgn in zip(self._boxes, (-1, 1), strict=True):
                b.offset = ft.Offset(sgn * fx_ * px / w, sgn * 0.015 * (1 - k))
                b.opacity = op
            _refresh(*self._boxes)
        await _sleep(0.05)
        if gen != self._gen:
            return
        for b in self._boxes:
            b.animate_offset = _anim(260, CUBIC)
            b.animate_opacity = _anim(300, ft.AnimationCurve.EASE_IN)
            b.offset, b.opacity = ft.Offset(0, 0), 0
        _refresh(*self._boxes)


# --------------------------------------------------------------------------- screen distortion


class Distortion(ft.Container):
    """Full-screen, tap-through 'impact' layer used by `distort()`: a soft flash, cyan/magenta
    edge fringes (chromatic aberration), horizontal glitch slices, a scanline band sweeping
    down, and an expanding double shockwave ring. Hidden except while it plays (~0.7 s).
    Pair it with a root content control (zoom punch + 2-4 frames of jitter) - see
    `install_distortion` / `distort`."""

    SLICES = 7

    def __init__(self) -> None:
        self._flash = _fill(ft.Container(opacity=0, animate_opacity=_SNAP))
        self._edge_l = ft.Container(left=0, top=0, bottom=0, width=80, opacity=0,
                                    animate_opacity=_SNAP)
        self._edge_r = ft.Container(right=0, top=0, bottom=0, width=80, opacity=0,
                                    animate_opacity=_SNAP)
        self._band = ft.Container(left=0, right=0, top=-120, height=96, opacity=0,
                                  animate_position=_SNAP, animate_opacity=_SNAP)
        self._line = ft.Container(left=0, right=0, top=-40, height=1.5, opacity=0,
                                  animate_position=_SNAP, animate_opacity=_SNAP)
        self._slices = [ft.Container(left=0, top=-20, width=400, height=4, opacity=0)
                        for _ in range(self.SLICES)]
        self._rings = [ft.Container(width=100, height=100, left=0, top=0,
                                    shape=ft.BoxShape.CIRCLE, scale=0.05, opacity=0,
                                    animate_scale=_SNAP, animate_opacity=_SNAP)
                       for _ in range(3)]  # soft glow band, crisp ring, late echo
        self._gen = 0
        self._rnd = random.Random(41)
        super().__init__(
            content=ft.Stack([self._flash, *self._rings, self._band, self._line,
                              *self._slices, self._edge_l, self._edge_r], expand=True,
                             clip_behavior=ft.ClipBehavior.HARD_EDGE),
            expand=True, visible=False, ignore_interactions=True)

    def _paint(self, col: str) -> None:
        self._flash.bgcolor = a(_mix(col, WHITE, 0.6), 1)
        self._edge_l.gradient = ft.LinearGradient(colors=[a(CYAN, 0.42), a(CYAN, 0)])
        self._edge_r.gradient = ft.LinearGradient(begin=ft.Alignment.CENTER_RIGHT,
                                                  end=ft.Alignment.CENTER_LEFT,
                                                  colors=[a(MAGENTA, 0.38), a(MAGENTA, 0)])
        self._band.gradient = ft.LinearGradient(
            begin=ft.Alignment.TOP_CENTER, end=ft.Alignment.BOTTOM_CENTER,
            colors=[a(col, 0), a(col, 0.10), a(col, 0.22), a(col, 0)], stops=[0, 0.6, 0.9, 1])
        self._line.bgcolor = a(_mix(col, WHITE, 0.5), 0.85)
        self._line.shadow = ft.BoxShadow(blur_radius=10, color=a(col, 0.9))
        # no BoxShadow here: on a borderless-fill circle it paints a filled disc
        glow, crisp, echo = self._rings
        glow.border = ft.Border.all(10, a(col, 0.16))
        crisp.border = ft.Border.all(2, a(_mix(col, WHITE, 0.45), 0.95))
        echo.border = ft.Border.all(1.2, a(col, 0.6))

    def _shuffle_slices(self, w: float, h: float, strength: float, cy: float) -> None:
        rnd = self._rnd
        for sl in self._slices:
            if rnd.random() < 0.25:
                sl.opacity = 0
                continue
            y = cy + rnd.gauss(0, h * 0.22)
            hh = rnd.choice((1.5, 2, 3, 4, 6, 9, 14))
            dx = rnd.uniform(-34, 34) * strength
            col = rnd.choice((CYAN, MAGENTA, WHITE, CYAN))
            sl.top, sl.height, sl.left, sl.width = y, hh, dx - 20, w + 40
            mid = rnd.uniform(0.25, 0.75)
            sl.gradient = ft.LinearGradient(
                colors=[a(col, 0), a(col, 0.10 + 0.25 * strength), a(WHITE, 0.30 * strength),
                        a(col, 0.10 + 0.2 * strength), a(col, 0)],
                stops=[0, max(0.05, mid - 0.3), mid, min(0.95, mid + 0.25), 1])
            sl.opacity = 1

    async def play(self, strength: float, x: float | None, y: float | None, color: str,
                   targets: Sequence[ft.Control] = ()) -> None:
        if not _mounted(self):
            return
        self._gen += 1
        gen = self._gen
        s = max(0.1, min(1.0, strength))
        pw = ph = None
        with contextlib.suppress(Exception):
            pw, ph = self.page.width, self.page.height  # type: ignore[union-attr]
        w, h = float(pw or 375), float(ph or 812)
        cx = w / 2 if x is None else x
        cy = h * 0.45 if y is None else y
        self._paint(color)
        soft = reduced()
        # ---- prime (snap)
        for ctrl in (self._flash, self._edge_l, self._edge_r, self._band, self._line,
                     *self._rings):
            ctrl.animate_opacity = _SNAP
            ctrl.opacity = 0
        self._band.animate_position = self._line.animate_position = _SNAP
        self._band.top, self._line.top = -110, -40
        reach = 2 * max(math.hypot(cx - px, cy - py) for px in (0, w) for py in (0, h))
        reach = min(1900.0, reach)
        for r in self._rings:
            r.animate_scale = _SNAP
            r.width = r.height = reach
            r.left, r.top = cx - reach / 2, cy - reach / 2
            r.scale = 0.03
        for sl in self._slices:
            sl.opacity = 0
        self.visible = True
        _refresh(self)
        await _sleep(0.02)
        if gen != self._gen:
            return
        sfx.play("distort", 0.45 + 0.55 * s)
        if soft:  # reduce effects: one soft flash, nothing moves
            self._flash.opacity = 0.10 * s + 0.04
            _refresh(self._flash)
            await _sleep(0.05)
            self._flash.animate_opacity = _anim(320, ft.AnimationCurve.EASE_OUT)
            self._flash.opacity = 0
            _refresh(self._flash)
            await _sleep(0.34)
            if gen == self._gen:
                self.visible = False
                _refresh(self)
            return
        # ---- impact frame
        self._flash.opacity = 0.18 * s
        self._edge_l.opacity = self._edge_r.opacity = 0.75 * s
        for i, r in enumerate(self._rings):  # grow now; visible at once, fade from next frame
            r.animate_scale = _anim(640 if i < 2 else 860, CUBIC)
            r.animate_opacity = _SNAP
            r.scale, r.opacity = (1.0 if i < 2 else 0.8), 1.0
        self._band.animate_position = _anim(460, ft.AnimationCurve.EASE_IN_OUT)
        self._line.animate_position = _anim(460, ft.AnimationCurve.EASE_IN_OUT)
        self._band.top, self._line.top = h + 10, h + 80
        self._band.opacity = self._line.opacity = 1
        self._shuffle_slices(w, h, s, cy)
        punch = _Punch.start(targets, s)
        _refresh(self)
        frames = 2 + round(2 * s)
        for k in range(frames):
            await _sleep(0.04)
            if gen != self._gen:
                punch.finish()
                return
            if k == 0:
                for i, r in enumerate(self._rings):
                    r.animate_opacity = _anim(600 if i < 2 else 820, ft.AnimationCurve.EASE_IN)
                    r.opacity = 0
                self._flash.animate_opacity = _anim(300)
                self._flash.opacity = 0
                for e in (self._edge_l, self._edge_r):
                    e.animate_opacity = _anim(320, ft.AnimationCurve.EASE_OUT)
                    e.opacity = 0
            if k < frames - 1:
                self._shuffle_slices(w, h, s * (1 - k / frames), cy)
            else:
                for sl in self._slices:
                    sl.opacity = 0
            punch.frame(k, frames)
            _refresh(self)
        punch.finish()
        await _sleep(0.45)
        if gen == self._gen:
            self._band.opacity = self._line.opacity = 0
            self.visible = False
            _refresh(self)


class _Punch:
    """Zoom punch + jitter on content controls (the app root, an overlay's stage). Each target
    must already carry animate_scale / animate_offset (set at build time) so changing them
    never swaps its Flutter widget (which would rebuild the subtree)."""

    def __init__(self, targets: Sequence[ft.Control], s: float) -> None:
        self.targets = [t for t in targets if t is not None and _mounted(t)]
        self.s = s
        self._saved = [(getattr(t, "animate_scale", None), getattr(t, "animate_offset", None))
                       for t in self.targets]
        self._rnd = random.Random()

    @classmethod
    def start(cls, targets: Sequence[ft.Control], s: float) -> _Punch:
        p = cls(targets, s)
        for t in p.targets:
            t.animate_scale = _anim(70, ft.AnimationCurve.EASE_OUT)
            t.scale = 1 + 0.035 * s
            t.animate_offset = _SNAP
            t.offset = ft.Offset(0.012 * s, -0.004 * s)
        _refresh(*p.targets)
        return p

    def frame(self, k: int, frames: int) -> None:
        fade = 1 - (k + 1) / frames
        for t in self.targets:
            if k == 0:
                t.animate_scale = _anim(300, CUBIC)
                t.scale = 1
            sgn = -1 if k % 2 == 0 else 1
            t.offset = ft.Offset(sgn * 0.010 * self.s * fade,
                                 self._rnd.uniform(-0.004, 0.004) * self.s * fade)
        _refresh(*self.targets)

    def finish(self) -> None:
        for t, (sc, of) in zip(self.targets, self._saved, strict=True):
            t.scale = 1
            t.offset = ft.Offset(0, 0)
            t.animate_offset = _SNAP
            if sc is not None:
                t.animate_scale = _anim(260, CUBIC)
            _refresh(t)
            if of is not None:  # restore the owner's offset animation for later moves
                t.animate_offset = of


_distort_hosts: dict[int, tuple[Distortion, Any]] = {}


def _ensure_animatable(ctrl: ft.Control) -> None:
    """Give a root control scale/offset animations up front (before it is first rendered)."""
    if getattr(ctrl, "animate_scale", None) is None:
        ctrl.animate_scale = _SNAP
    if getattr(ctrl, "animate_offset", None) is None:
        ctrl.animate_offset = _SNAP
    if getattr(ctrl, "scale", None) is None:
        ctrl.scale = 1
    if getattr(ctrl, "offset", None) is None:
        ctrl.offset = ft.Offset(0, 0)


def install_distortion(page: ft.Page, root: ft.Control | None = None) -> Distortion:
    """Add the distortion layer to `page.overlay` (once) and register `root` - the app's main
    content control - for the zoom punch + jitter. Call before the root is first shown (it
    gives the root scale/offset animations so later changes never rebuild it). Idempotent."""
    layer, old_root = _distort_hosts.get(id(page), (None, None))
    if layer is None or layer not in page.overlay:
        layer = Distortion()
        page.overlay.append(layer)
    if root is not None:
        _ensure_animatable(root)
    _distort_hosts[id(page)] = (layer, root if root is not None else old_root)
    return layer


def distort(target: Any = None, strength: float = 1.0, *, x: float | None = None,
            y: float | None = None, color: str | None = None,
            also: Sequence[ft.Control] = ()) -> None:
    """Screen 'impact' (fire-and-forget): zoom punch 1.0 -> 1.035 -> 1.0 and 2-4 frames of
    jitter on the registered root (+ `also`, e.g. an overlay's stage), a flash, cyan/magenta
    edge fringes, glitch slices, a scanline sweep and a shockwave ring from (x, y) (page
    coords; default screen centre), plus sfx 'distort'. Reduce effects -> a soft flash only.
    `target`: the Page, or any mounted control on it (its page is used)."""
    page = target if isinstance(target, ft.Page) else None
    if page is None and target is not None:
        with contextlib.suppress(Exception):
            page = target.page
    if page is None:
        return
    layer, root = _distort_hosts.get(id(page), (None, None))
    if layer is None or not _mounted(layer):
        with contextlib.suppress(Exception):
            layer = install_distortion(page)
            page.update()
    if layer is None:
        return
    targets = [t for t in ((root,) if root is not None else ()) + tuple(also) if t is not None]
    _spawn(layer.play(strength, x, y, color or CYAN, targets))


# --------------------------------------------------------------------------- Luma lookup


def thinking_for(page: ft.Page) -> LumenThinking:
    """The page's LumenThinking overlay (the app's, with its hum hook), or a new one."""
    for ctrl in reversed(list(page.overlay)):
        if isinstance(ctrl, LumenThinking):
            return ctrl
    think = LumenThinking()
    page.overlay.append(think)
    with contextlib.suppress(Exception):
        page.update()
    return think


class LumenThinking(_Overlay):
    """Luma 'Analysis…': wireframe icosahedron + ring orbiting a bright core, radial light
    lines, square data particles swirling outward, nebula halo.

    `await thinking.play(0.9, "Analysis…")` - fixed length (0.3-2.1 s), or
    `await thinking.play_staged(2.5)` - v1.3 long version (2.2-2.8 s): "ANALYSIS…" ->
    "MATCHING PATHS…" -> "PROPOSAL READY", slow scan bar, or
    `async with thinking.session("Analysis…", stages=STAGES): result = await compute()` -
    plays while the block runs (at least `min_s`). The orb redraws at 20 fps only while playing.

    `on_start`: called (sync or async, no args) at the exact moment the orb appears - hook the
    'lumen_hum' SFX there: `LumenThinking(on_start=lambda: sfx.play("lumen_hum"))`, or set
    `thinking.on_start = ...`, or pass `on_start=` per call (overrides). In reduce mode it fires
    when the simple card appears. Tap still skips; input is released after 2.5 s regardless."""

    STAGE_W, STAGE_H = 300, 360
    CX, CY = 150, 150
    FPS = 20
    WIRE = 250
    BAR_W = 168
    STAGES = ("ANALYSIS…", "MATCHING PATHS…", "PROPOSAL READY")
    MAX_STAGED_S = 2.8
    MIN_STAGED_S = 1.4
    READY_HOLD_S = 0.45  # the final stage stays this long before the exit

    def __init__(self, *, reduce: bool | None = None,
                 on_start: Callable[[], Any] | None = None) -> None:
        super().__init__(reduce=reduce)
        self.on_start = on_start
        cx, cy = self.CX, self.CY
        self._bg.gradient = ft.RadialGradient(
            center=ft.Alignment(0, -0.1), radius=1.0,
            colors=[a("#0B1D2C", 0.84), a(NAVY, 0.9), a("#03050A", 0.95)], stops=[0, 0.5, 1])
        self._blobs = [_blob(cx + dx, cy + dy, d, col, op) for dx, dy, d, col, op in (
            (-85, 10, 250, MINT, 0.45), (95, 15, 240, VIOLET, 0.42), (0, -85, 210, CYAN, 0.30),
            (-30, 90, 230, "#9BE86A", 0.26), (65, 75, 180, "#6BB8FF", 0.32))]
        self._rays = _place(_rays_canvas(760, 46, seed=13, colors=(WHITE, "#CFF8FF", CYAN),
                                         r0=46, op=(.25, .6), width=(.5, 1.3)), cx, cy)
        self._rays.animate_rotation = _anim(6000, LINEAR)
        rnd = random.Random(17)
        squares = []
        for _ in range(26):
            ang, r = rnd.uniform(0, TAU), rnd.uniform(40, 150)
            sz = rnd.choice((3, 4, 5, 6, 8, 10))
            outlined = sz >= 6 and rnd.random() < 0.6
            squares.append(_place(ft.Container(
                width=sz, height=sz * rnd.uniform(0.6, 1.0), rotate=rnd.uniform(0, 1.5),
                bgcolor=None if outlined else a(WHITE, rnd.uniform(0.5, 0.9)),
                border=ft.Border.all(1, a("#CFF8FF", 0.7)) if outlined else None),
                150 + r * math.cos(ang), 150 + r * math.sin(ang)))
        self._squares = _place(ft.Container(
            ft.Stack(squares, width=300, height=300), width=300, height=300, opacity=0, scale=0.6,
            rotate=0, animate_opacity=_anim(300), animate_scale=_anim(6000, LINEAR),
            animate_rotation=_anim(6000, LINEAR)), cx, cy)
        self._wire = cv.Canvas([], width=self.WIRE, height=self.WIRE)
        self._wire_box = _place(ft.Container(self._wire, width=self.WIRE, height=self.WIRE,
                                             opacity=0, scale=0.7, animate_opacity=_anim(250),
                                             animate_scale=_anim(450, BACK)), cx, cy)
        self._core = _place(Flare(170, CYAN, streak=1.7), cx, cy)
        self._label = ft.Text("", size=12, weight=ft.FontWeight.BOLD, color=CYAN,
                              style=ft.TextStyle(letter_spacing=3.4, shadow=[
                                  ft.BoxShadow(blur_radius=10, color=a(CYAN, 0.7))]))
        self._bar = ft.Container(width=0, height=2, bgcolor=CYAN, border_radius=1,
                                 animate=_SNAP,  # AnimatedContainer: animates the width
                                 shadow=ft.BoxShadow(blur_radius=6, color=a(CYAN, 0.9)))
        self._label_box = ft.Container(
            ft.Column([self._label, ft.Container(self._bar, width=self.BAR_W, height=2,
                                                 bgcolor=a(CYAN, 0.15),
                                                 alignment=ft.Alignment.CENTER_LEFT)],
                      tight=True, spacing=7, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            left=0, width=300, top=cy + 158, alignment=ft.Alignment.TOP_CENTER,
            opacity=0, animate_opacity=_anim(300))
        self._bloom = _place(_bloom(330), cx, cy)
        _paint_bloom(self._bloom, "#7FF3FF", 0.36)
        self._motes = _place(Sparks(360, 20, (CYAN, MINT, VIOLET, "#CFF8FF"), seed=19,
                                    mode="rise", reach=(110, 240), dot=(3, 16),
                                    ms=(2400, 3400)), cx, cy + 40)
        self._stage.controls = [*self._blobs, self._bloom, self._rays, self._motes,
                                self._squares, self._wire_box, self._core, self._label_box]
        self._draw(0.0)

    # ---------------------------------------------------------------- drawing
    def _draw(self, t: float) -> None:
        c, rr, f = self.WIRE / 2, 104, 3.4
        ay, ax = t * 1.9, 0.45 + 0.28 * math.sin(t * 1.3)

        def proj(p: tuple[float, float, float], r: float = rr) -> tuple[float, float, float]:
            x, y, z = p
            s = r * f / (f - z)
            return c + x * s, c + y * s, z

        pts = [proj(_rot(v, ay, ax)) for v in _ICO]
        front: list[cv.Path.PathElement] = []
        back: list[cv.Path.PathElement] = []
        for i, j in _ICO_EDGES:
            seg = [cv.Path.MoveTo(pts[i][0], pts[i][1]), cv.Path.LineTo(pts[j][0], pts[j][1])]
            (front if pts[i][2] + pts[j][2] > -0.2 else back).extend(seg)

        def ring(ay2: float, ax2: float, r: float) -> list[cv.Path.PathElement]:
            out = []
            for k, p in enumerate(_RING):
                x, y, _ = proj(_rot(p, ay2, ax2), r)
                out.append(cv.Path.MoveTo(x, y) if k == 0 else cv.Path.LineTo(x, y))
            return out

        ring1 = ring(1.25 + t * 2.6, 0.35, 74)
        ring2 = ring(-0.4 - t * 1.5, 1.2 + 0.2 * math.sin(t), 58)
        shapes: list[cv.Shape] = [
            cv.Path(back, paint=_stroke(a(WHITE, 0.28), 0.8)),
            cv.Path(ring2, paint=_stroke(a("#CFF8FF", 0.55), 1.2)),
            cv.Path(ring1, paint=_stroke(a(CYAN, 0.28), 7)),
            cv.Path(ring1, paint=_stroke(a(WHITE, 0.92), 2.4)),
            cv.Path(front, paint=_stroke(a(WHITE, 0.85), 1.1)),
        ]
        for x, y, z in pts:
            shapes.append(cv.Circle(x, y, 2.6 if z > 0 else 1.6,
                                    paint=_solid(a(WHITE, 0.95 if z > 0 else 0.45))))
        self._wire.shapes = shapes

    # ---------------------------------------------------------------- playback
    def _set_tone(self, col: str) -> None:
        self._label.color = col
        self._label.style = ft.TextStyle(letter_spacing=3.4, shadow=[
            ft.BoxShadow(blur_radius=10, color=a(col, 0.7))])
        self._bar.bgcolor = col
        self._bar.shadow = ft.BoxShadow(blur_radius=6, color=a(col, 0.9))

    async def _run(self, label: str, min_s: float, stop: asyncio.Event | None,
                   stages: Sequence[str] | None = None,
                   on_start: Callable[[], Any] | None = None) -> None:
        staged = bool(stages) and len(stages or ()) >= 2
        names, dots = stage_labels(list(stages) if staged and stages else [label])
        hold = self.READY_HOLD_S if staged else 0.0
        run_until = max(0.2, min_s - hold)
        self._label.value = names[0]
        self._set_tone(CYAN)
        self._bg.opacity = 0
        for b in self._blobs:
            b.opacity, b.scale = 0, 0.85
        self._rays.opacity, self._rays.rotate = 0, 0
        self._squares.opacity, self._squares.scale, self._squares.rotate = 0, 0.6, 0
        self._wire_box.opacity, self._wire_box.scale = 0, 0.7
        self._core.prime()
        self._bloom.opacity, self._bloom.scale = 0, 0.6
        self._motes.prime()
        self._label_box.opacity = 0
        self._bar.animate = _SNAP
        self._bar.width = 0
        self._draw(0.0)
        await self._open()
        _fire(on_start)  # the orb appears with this update - 'lumen_hum' goes here
        if staged:
            sfx.play("loading", 0.5)  # data churn under the hum while the stages run
            sfx.play("type", 0.5)  # the first label types in
        _buzz("light")
        self._bg.opacity = 1
        for b in self._blobs:
            b.opacity, b.scale = 1, 1.12
        self._rays.opacity, self._rays.rotate = 0.9, 0.5 if not staged else 0.8
        self._squares.opacity, self._squares.scale, self._squares.rotate = 1, 2.2, 1.6
        self._wire_box.opacity, self._wire_box.scale = 1, 1
        self._core.burst(260, 1.0)
        self._bloom.opacity, self._bloom.scale = 1, 1.1
        self._motes.rise(0.9 if staged else 1.3)
        self._label_box.opacity = 1
        if staged:  # slow, even scan that reaches ~92% when the last working stage ends
            self._bar.animate = _anim(run_until * 1000, ft.AnimationCurve.EASE_IN_OUT_SINE)
            self._bar.width = self.BAR_W * 0.92
        else:
            self._bar.animate = _anim(max(300, min_s * 1000), CUBIC)
            self._bar.width = self.BAR_W
        _refresh(self)
        t0 = time.perf_counter()
        frame = 0
        work = len(names) - 1 if staged else 1  # stages shown while 'working'
        ready_at: float | None = None
        shown = 0
        while not self._skip.is_set():
            t = time.perf_counter() - t0
            if t > 12:  # safety: never spin forever
                break
            done_ok = t >= run_until and (stop is None or stop.is_set())
            if not staged:
                if done_ok:
                    break
                idx = 0
            elif ready_at is None and done_ok:
                ready_at = t
                idx = len(names) - 1
                self._set_tone(MINT)
                self._bar.animate = _anim(220, CUBIC)
                self._bar.width = self.BAR_W
                self._core.burst(200, 1.18)
                sfx.play("scan_done", 0.8)
                _refresh(self._bar)
            elif ready_at is not None:
                if t - ready_at >= hold:
                    break
                idx = len(names) - 1
            else:
                idx = stage_at(t, run_until, work)
            if idx != shown:
                shown = idx
                _buzz("select")
                if idx < len(names) - 1:
                    sfx.play("scan_tick", 0.6)
                    sfx.play("type", 0.5)  # the new stage label types in
            self._draw(t)
            self._label.value = names[idx] + ("." * (1 + (frame // 5) % 3) if dots[idx] else "")
            if frame % 8 == 0 and ready_at is None:
                self._core.settle(0.85 if (frame // 8) % 2 else 1.0, 1, 380)
            _refresh(self._wire, self._label_box, self._core)
            frame += 1
            await _sleep(1 / self.FPS)
        self._core.burst(160, 1.3)
        _refresh(self._core)
        await _sleep(0.12)
        self._core.fade()
        self._motes.fade((200, 320))
        await self._close(260, 1.1)

    async def play(self, duration: float = 0.9, label: str = "Analysis…", *,
                   stages: Sequence[str] | None = None,
                   on_start: Callable[[], Any] | None = None) -> None:
        """Fixed-length play. With `stages` the length may run to 2.8 s (v1.3 long analysis);
        without, it stays within 0.3-2.1 s."""
        hi = self.MAX_STAGED_S if stages else MAX_BLOCK_S - 0.4
        duration = max(0.3, min(hi, duration))
        hook = on_start if on_start is not None else self.on_start
        title = (stages[0] if stages else label)
        await self._play(lambda: self._run(label, duration, None, stages, hook), title=title,
                         eyebrow="LUMA", subtitle=None, color=CYAN, hold=duration,
                         on_start=hook)

    async def play_staged(self, duration: float = 2.5, stages: Sequence[str] | None = None, *,
                          on_start: Callable[[], Any] | None = None) -> None:
        """Staged analysis (hum, slow scan bar, staged text; tap to skip). Default stages:
        ANALYSIS… -> MATCHING PATHS… -> PROPOSAL READY. Any action can pass its own (2+; the
        last is the 'ready' line, shown in mint with sfx 'scan_done'; every earlier stage change
        ticks 'scan_tick'). `duration` 1.4-2.8 s (Ask Luma uses 2.5)."""
        await self.play(max(self.MIN_STAGED_S, duration), stages=stages or self.STAGES,
                        on_start=on_start)

    @contextlib.asynccontextmanager
    async def session(self, label: str = "Analysis…", min_s: float = 0.6, *,
                      stages: Sequence[str] | None = None,
                      on_start: Callable[[], Any] | None = None) -> AsyncIterator[None]:
        """Play while the block runs (stages advance over `min_s`; the final one shows once
        the block is done). Input is released after 2.5 s even if it is still going."""
        if not _mounted(self):
            yield
            return
        stop = asyncio.Event()
        hook = on_start if on_start is not None else self.on_start
        title = stages[0] if stages else label
        task = asyncio.ensure_future(self._play(
            lambda: self._run(label, min_s, stop, stages, hook), title=title, eyebrow="LUMA",
            subtitle=None, color=CYAN, hold=min_s, stop=stop, on_start=hook))
        try:
            yield
        finally:
            stop.set()
            with contextlib.suppress(Exception):
                await task

    async def __aenter__(self) -> Self:
        self._cm = self.session()
        await self._cm.__aenter__()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._cm.__aexit__(*exc)


# --------------------------------------------------------------------------- 4 IdentifyReveal


def _chain_half(length: float, links: int) -> ft.Container:
    h = 40
    cy = h / 2
    pitch = (length - 16) / (links - 1)
    ovals: list[cv.Path.PathElement] = []
    bars: list[cv.Path.PathElement] = []
    for i in range(links):
        x = 8 + i * pitch
        if i % 2 == 0:
            w = pitch * 1.6
            ovals.append(cv.Path.Oval(x - w / 2, cy - 6.5, w, 13))
        else:
            w = pitch * 1.45
            bars.append(cv.Path.Rect(x - w / 2, cy - 2.4, w, 4.8, border_radius=2.4))
    metal = ft.PaintLinearGradient(begin=ft.Offset(0, cy - 7), end=ft.Offset(0, cy + 7),
                                   colors=[CREAM, GOLD, "#8A6430"], color_stops=[0, 0.45, 1])
    shapes: list[cv.Shape] = [
        cv.Path(ovals, paint=_stroke(a("#000000", 0.55), 5.2)),
        cv.Path(bars, paint=_stroke(a("#000000", 0.55), 2.6)),
        cv.Path(ovals, paint=_stroke(GOLD, 2.6, gradient=metal)),
        cv.Path(bars, paint=_solid(GOLD, metal)),
    ]
    return ft.Container(cv.Canvas(shapes, width=length, height=h), width=length, height=h,
                        opacity=0, offset=ft.Offset(0, 0), rotate=0,
                        animate_opacity=_anim(300), animate_offset=_anim(480, CUBIC),
                        animate_rotation=_anim(480, CUBIC))


def _lock_icon() -> ft.Container:
    w, h = 36, 46
    body = ft.PaintLinearGradient(begin=ft.Offset(0, 20), end=ft.Offset(0, 44),
                                  colors=[CREAM, GOLD, "#8A6430"])
    shapes: list[cv.Shape] = [
        cv.Path([cv.Path.MoveTo(9, 22), cv.Path.LineTo(9, 13),
                 cv.Path.Arc(9, 4, 18, 18, math.pi, math.pi),
                 cv.Path.LineTo(27, 22)], paint=_stroke(GOLD, 3.6)),
        cv.Rect(4, 20, 28, 23, border_radius=4, paint=_solid(GOLD, body)),
        cv.Rect(4, 20, 28, 23, border_radius=4, paint=_stroke(a("#5A3E18", 0.9), 1)),
        cv.Circle(18, 29, 3.2, paint=_solid("#2A1C0A")),
        cv.Rect(16.8, 30, 2.4, 7, paint=_solid("#2A1C0A")),
    ]
    return ft.Container(cv.Canvas(shapes, width=w, height=h), width=w, height=h, opacity=0,
                        scale=0.4, rotate=0, offset=ft.Offset(0, 0),
                        shadow=None, animate_opacity=_anim(260), animate_scale=_anim(300, BACK),
                        animate_rotation=_anim(80), animate_offset=_anim(420, CUBIC))


class IdentifyReveal(_Overlay):
    """Unlock / identify (theme bought, side quest started, item obtained): rotating gear and
    clock-face rings behind a big bold title, chains crossing it that rattle and snap apart.
    ~2.3 s. `await reveal.show("EMBER THEME", "Unlocked")`"""

    STAGE_W, STAGE_H = 340, 340
    CX, CY = 170, 170
    CHAIN_L = 176

    def __init__(self, *, reduce: bool | None = None) -> None:
        super().__init__(reduce=reduce)
        cx, cy = self.CX, self.CY
        self._bg.gradient = ft.RadialGradient(
            center=ft.Alignment(0, -0.05), radius=0.9,
            colors=[a("#22344F", 0.88), a("#17120A", 0.92), a("#050608", 0.96)],
            stops=[0, 0.5, 1])
        self._texture = _place(self._texture_ring(), cx, cy)
        self._gear = _place(self._gear_ring(), cx, cy)
        self._clock = _place(self._clock_ring(), cx, cy)
        self._glow = _blob(cx, cy, 300, "#5B8FD6", 0.38)
        self._sparks = _place(Starfield(700, 700, count=34, streaks=14,
                                        colors=(GOLD, CREAM, WHITE), seed=31, hole=60), cx, cy)
        self._title = ft.Text("", weight=ft.FontWeight.W_900, color=CREAM, width=330,
                              text_align=ft.TextAlign.CENTER, max_lines=2,
                              style=ft.TextStyle(letter_spacing=1.5, height=1.0, shadow=[
                                  ft.BoxShadow(blur_radius=4, offset=ft.Offset(0, 2),
                                               color=a("#000000", 0.85)),
                                  ft.BoxShadow(blur_radius=20, color=a(GOLD, 0.55))]))
        self._chroma = _Chroma(self._title)
        self._title_box = _place(ft.Container(self._chroma.wrap, width=340, height=120,
                                              alignment=ft.Alignment.CENTER, opacity=0,
                                              scale=0.92, animate_opacity=_anim(260),
                                              animate_scale=_anim(260, BACK)), cx, cy)
        self._sub = ft.Text("", size=11, weight=ft.FontWeight.BOLD, color=GOLD,
                            style=ft.TextStyle(letter_spacing=3.4))
        self._sub_box = ft.Container(self._sub, left=0, width=340, top=cy + 62,
                                     alignment=ft.Alignment.TOP_CENTER, opacity=0,
                                     animate_opacity=_anim(400))
        # two chains crossing the title (an X), each split in halves around the lock
        self._halves: list[tuple[ft.Container, float, int]] = []
        for theta in (-0.21, 0.19):
            for side in (-1, 1):
                half = _chain_half(self.CHAIN_L, 11)
                d = self.CHAIN_L / 2 + 8
                _place(half, cx + side * d * math.cos(theta), cy + side * d * math.sin(theta))
                self._halves.append((half, theta, side))
        self._padlock = _place(_lock_icon(), cx, cy)
        self._flash = _place(Flare(280, GOLD, core=WHITE, streak=1.5), cx, cy)
        self._snap = _place(Sparks(440, 32, (CREAM, GOLD, WHITE, "#9CC4FF"), seed=33,
                                   reach=(100, 230), dot=(2.5, 11), lift=0, core=CREAM), cx, cy)
        self._bloom = _place(_bloom(380), cx, cy)
        _paint_bloom(self._bloom, "#7FA8E8", 0.34)
        self._ico = _place(Icosphere(210, freq=2, color="#9CC4FF", core=CREAM, facets=True,
                                     seed=5), cx, cy)
        self._stage.controls = [self._texture, self._gear, self._glow, self._bloom, self._clock,
                                self._sparks, self._ico, self._flash, self._title_box,
                                self._sub_box,
                                *(h for h, _, _ in self._halves), self._padlock, self._snap]

    @staticmethod
    def _spin_box(canvas: cv.Canvas, size: float) -> ft.Container:
        return ft.Container(canvas, width=size, height=size, opacity=0, scale=1.2, rotate=0,
                            animate_opacity=_anim(450), animate_scale=_anim(600, CUBIC),
                            animate_rotation=_anim(3000, LINEAR))

    def _texture_ring(self) -> ft.Container:
        s = 580
        c = s / 2
        rnd = random.Random(23)
        els: list[cv.Path.PathElement] = []
        for i in range(150):  # dense 'data' texture band
            t = TAU * i / 150
            r0 = 212 + rnd.uniform(0, 14)
            r1 = r0 + rnd.uniform(8, 44)
            els += [cv.Path.MoveTo(c + r0 * math.cos(t), c + r0 * math.sin(t)),
                    cv.Path.LineTo(c + r1 * math.cos(t), c + r1 * math.sin(t))]
        shapes: list[cv.Shape] = [
            cv.Circle(c, c, 240, paint=_stroke(a(BRONZE, 0.28), 26, dash=[5, 3])),
            cv.Path(els, paint=_stroke(a(GOLD, 0.42), 1.1)),
            cv.Circle(c, c, 206, paint=_stroke(a(BRONZE, 0.6), 1.4)),
            cv.Circle(c, c, 278, paint=_stroke(a(BRONZE, 0.45), 1.2)),
        ]
        return self._spin_box(cv.Canvas(shapes, width=s, height=s), s)

    def _gear_ring(self) -> ft.Container:
        s = 340
        c = s / 2
        gear = _gear_elements(c, c, 166, 154, 44)
        fill = ft.PaintRadialGradient(center=ft.Offset(c, c), radius=166,
                                      colors=["#1C2638", "#1B150C", "#2A2012"],
                                      color_stops=[0, 0.75, 1])
        shapes: list[cv.Shape] = [
            cv.Path(gear, paint=_solid("#1B150C", fill)),
            cv.Path(gear, paint=_stroke(a(BRONZE, 0.95), 1.6)),
            cv.Circle(c, c, 134, paint=_stroke(a(GOLD, 0.55), 1.2)),
        ]
        for k in range(10):  # lightening holes
            t = TAU * k / 10
            shapes.append(cv.Circle(c + 144 * math.cos(t), c + 144 * math.sin(t), 4.5,
                                    paint=_stroke(a(BRONZE, 0.8), 1.2)))
        return self._spin_box(cv.Canvas(shapes, width=s, height=s), s)

    def _clock_ring(self) -> ft.Container:
        s = 260
        c = s / 2
        shapes: list[cv.Shape] = [
            cv.Circle(c, c, 124, paint=_stroke(a(GOLD, 0.75), 1.3)),
            cv.Path(_ticks(c, c, 112, 121, 60, major=5, r_major=103),
                    paint=_stroke(a(GOLD, 0.7), 1.2)),
            cv.Path(_gear_elements(c, c, 92, 86, 30), paint=_stroke(a(BRONZE, 0.75), 1.3)),
            cv.Circle(c, c, 70, paint=_stroke(a(GOLD, 0.35), 1, dash=[3, 4])),
        ]
        return self._spin_box(cv.Canvas(shapes, width=s, height=s), s)

    async def show(self, title: str, subtitle: str | None = None, *,
                   eyebrow: str = "UNLOCKED") -> None:
        async def run() -> None:
            self._title.value = title.upper()
            self._title.size = _title_size(title, ((6, 50), (9, 44), (12, 38), (16, 30),
                                                   (99, 23)))
            self._sub.value = (subtitle or eyebrow).upper()
            # prime
            self._bg.opacity = 0
            for r in (self._texture, self._gear, self._clock):
                r.opacity, r.scale, r.rotate = 0, 1.2, 0
            self._glow.opacity, self._glow.scale = 0, 0.85
            self._sparks.prime()
            self._title_box.opacity, self._title_box.scale = 0, 0.92
            self._sub_box.opacity = 0
            for h, theta, side in self._halves:
                h.opacity, h.rotate = 0, theta
                h.offset = ft.Offset(side * 0.7 * math.cos(theta), side * 0.7 * math.sin(theta))
            self._padlock.opacity, self._padlock.scale, self._padlock.rotate = 0, 0.4, 0
            self._padlock.offset = ft.Offset(0, 0)
            self._flash.prime()
            self._snap.prime()
            self._bloom.opacity, self._bloom.scale = 0, 0.6
            self._chroma.prime()
            self._ico.prime(0.3)
            await self._open()
            self._bg.opacity = 1
            self._ico.appear(460, 0.9, 0.9, energy=0.8)
            self._ico.start(5.0)
            self._texture.opacity, self._texture.scale, self._texture.rotate = 1, 1, 0.22
            self._gear.opacity, self._gear.scale, self._gear.rotate = 1, 1, -0.35
            self._clock.opacity, self._clock.scale, self._clock.rotate = 1, 1, 0.6
            self._glow.opacity, self._glow.scale = 1, 1.1
            self._title_box.opacity, self._title_box.scale = 0.5, 0.96
            for h, _, _ in self._halves:
                h.opacity, h.offset = 1, ft.Offset(0, 0)
            self._padlock.opacity, self._padlock.scale = 1, 1
            _refresh(self)
            await self._wait(0.38)
            for ang in (0.24, -0.24, 0.16, 0):  # rattle
                if self._skip.is_set():
                    break
                self._padlock.rotate = ang
                self._ico.flare(2)
                _refresh(self._padlock)
                await _sleep(0.085)
            await self._wait(0.1)
            # snap!
            _buzz("heavy")
            for h, theta, side in self._halves:
                h.offset = ft.Offset(side * 1.05 * math.cos(theta), 1.6 + side * 0.4)
                h.rotate = theta + side * 0.55
                h.opacity = 0
            self._padlock.animate_rotation = _anim(420, CUBIC)
            self._padlock.offset = ft.Offset(0, 1.3)
            self._padlock.rotate, self._padlock.opacity = 0.9, 0
            self._flash.burst(220, 1.2)
            self._sparks.warp(1.6, 1.45)
            self._snap.burst()
            self._bloom.opacity, self._bloom.scale = 1, 1.15
            self._title_box.opacity, self._title_box.scale = 1, 1.08
            self._sub_box.opacity = 1
            self._ico.punch(1.5, 1.0, settle=1.25, facets=10)
            self._ico.animate_opacity = _anim(700, ft.AnimationCurve.EASE_OUT)
            self._ico.opacity = 0.5
            self._impact(0.9, GOLD)
            _refresh(self)
            _spawn(self._chroma.hit(0.9))
            await self._wait(0.2)
            self._flash.settle(0.35, 0.55, 500)
            self._title_box.scale = 1
            self._snap.fade((650, 1100))
            self._bloom.opacity, self._bloom.scale = 0.6, 1.0
            _refresh(self)
            await self._wait(0.95)
            self._padlock.animate_rotation = _anim(80)
            self._flash.fade()
            self._ico.vanish(300, 1.7)
            await self._close(320, 1.06)
            self._ico.stop()

        await self._play(run, title=title, eyebrow=eyebrow, subtitle=subtitle, color=GOLD)


# --------------------------------------------------------------------------- QuestCleared


class QuestCleared(ft.Container):
    """Every quest completion (v1.3 fix 2, v1.4 impact): ~1.25 s, fully tap-through (never
    blocks input). A small Icosphere spins in, kicks on impact (shockwave ring, flare, sparks,
    a light screen distortion), then implodes as "QUEST CLEARED" slides up under it with a
    chromatic ghost. A new call restarts it (rapid completions never queue).

    `page.overlay.append(cleared)`; `await cleared.show("Drink water", x=..., y=...)`
    x/y: page coordinates to centre on (e.g. the tapped card's `global_position` from
    `on_tap_down`); omitted -> centre of the screen, a bit above middle. Reduce mode: the label
    alone fades in and out."""

    S = 300  # stage box
    C_ = 150
    ICO = 112  # the little crystal at the heart of the flash

    def __init__(self, *, reduce: bool | None = None, color: str | None = None) -> None:
        self.reduce = reduce
        self._color = color
        self._gen = 0
        c = self.C_
        self._glow = _place(_bloom(230), c, c)
        self._ring = _place(ft.Container(width=90, height=90, shape=ft.BoxShape.CIRCLE,
                                         scale=0.3, opacity=0, animate_scale=_anim(620, CUBIC),
                                         animate_opacity=_anim(620, ft.AnimationCurve.EASE_IN)),
                            c, c)
        self._ico = _place(Icosphere(self.ICO, freq=2, seed=27, tilt=0.5), c, c)
        self._flare = _place(Flare(130, CYAN, streak=2.4), c, c)
        self._sparks = _place(Sparks(self.S, 26, (WHITE, CYAN, MINT), seed=27,
                                     reach=(55, 135), dot=(2.5, 9), lift=24, ms=(650, 1000)),
                              c, c)
        self._label = ft.Text("QUEST CLEARED", size=15, weight=ft.FontWeight.W_900,
                              no_wrap=True)
        self._chroma = _Chroma(self._label)
        self._sub = ft.Text("", size=11.5, color="#B9D8E6", max_lines=1, width=250,
                            text_align=ft.TextAlign.CENTER, overflow=ft.TextOverflow.ELLIPSIS)
        self._rule_l = ft.Container(width=0, height=1, animate=_anim(420, CUBIC))
        self._rule_r = ft.Container(width=0, height=1, animate=_anim(420, CUBIC))
        # soft night backing (theme bg; navy on Arcane) that fades out at the sides: the label
        # stays readable over cards. Tinted per theme in _paint.
        backing = self._backing = ft.Container(
            ft.Column([
                ft.Row([ft.Container(self._rule_l, width=34, alignment=ft.Alignment.CENTER_RIGHT),
                        self._chroma.wrap,
                        ft.Container(self._rule_r, width=34, alignment=ft.Alignment.CENTER_LEFT)],
                       spacing=8, tight=True, alignment=ft.MainAxisAlignment.CENTER,
                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
                self._sub], spacing=2, tight=True,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.Padding.symmetric(horizontal=22, vertical=7), border_radius=18,
            gradient=ft.LinearGradient(colors=[a(NAVY, 0), a(NAVY, 0.82), a(NAVY, 0.82),
                                               a(NAVY, 0)], stops=[0, 0.18, 0.82, 1]),
            shadow=ft.BoxShadow(blur_radius=16, color=a(NAVY, 0.55)))
        self._text = ft.Container(
            backing,
            left=0, width=self.S, top=c + 30, alignment=ft.Alignment.TOP_CENTER, opacity=0,
            offset=ft.Offset(0, 0.4), animate_opacity=_anim(220),
            animate_offset=_anim(380, CUBIC))
        self._stage = ft.Stack([self._glow, self._ring, self._sparks, self._ico,
                                self._flare, self._text], width=self.S, height=self.S,
                               clip_behavior=ft.ClipBehavior.NONE)
        self._box = ft.Container(self._stage, width=self.S, height=self.S, left=0, top=0,
                                 opacity=1, animate_opacity=_anim(280))
        super().__init__(content=ft.Stack([self._box], expand=True), expand=True,
                         visible=False, ignore_interactions=True)

    def _reduced(self) -> bool:
        return reduced() if self.reduce is None else bool(self.reduce)

    def _paint(self, col: str) -> None:
        _paint_bloom(self._glow, col, 0.42)
        self._ring.border = ft.Border.all(1.4, a(col, 0.8))
        self._ring.shadow = ft.BoxShadow(blur_radius=14, color=a(col, 0.45))
        self._ico.set_color(col)
        self._flare.set_color(col)
        pal = th.current()
        self._sparks.set_colors((WHITE, col, pal.success))  # MINT on Arcane
        self._backing.gradient = ft.LinearGradient(
            colors=[a(pal.bg, 0), a(pal.bg, 0.82), a(pal.bg, 0.82), a(pal.bg, 0)],
            stops=[0, 0.18, 0.82, 1])
        self._backing.shadow = ft.BoxShadow(blur_radius=16, color=a(pal.bg, 0.55))
        self._sub.color = _mix(pal.text, pal.text_dim, 0.4)
        self._label.color = col
        self._label.style = ft.TextStyle(letter_spacing=4, shadow=[
            ft.BoxShadow(blur_radius=12, color=a(col, 0.8)),
            ft.BoxShadow(blur_radius=3, color=a("#000000", 0.7))])
        for r in (self._rule_l, self._rule_r):
            r.bgcolor = a(col, 0.7)

    def _locate(self, x: float | None, y: float | None) -> None:
        pw = ph = None
        with contextlib.suppress(Exception):
            pw, ph = self.page.width, self.page.height  # type: ignore[union-attr]
        pw, ph = float(pw or 375), float(ph or 812)
        cx = pw / 2 if x is None else x
        cy = ph * 0.42 if y is None else y
        cx = max(self.C_, min(pw - self.C_, cx))  # keep the label on screen
        cy = max(110.0, min(ph - 150.0, cy))
        self._box.left, self._box.top = cx - self.C_, cy - self.C_

    async def show(self, subtitle: str | None = None, *, x: float | None = None,
                   y: float | None = None, color: str | None = None,
                   title: str = "QUEST CLEARED") -> None:
        if not _mounted(self):
            return
        self._gen += 1
        gen = self._gen
        col = color or self._color or CYAN

        def live() -> bool:
            return gen == self._gen

        self._paint(col)
        self._label.value = title.upper()
        self._sub.value, self._sub.visible = subtitle or "", bool(subtitle)
        self._locate(x, y)
        simple = self._reduced()
        # prime (snap, no animation): hidden first so a restart never shows a jump
        self.visible = False
        self._box.opacity = 1
        for ctrl in (self._glow, self._ring):
            ctrl.opacity = 0
        self._ring.scale = 0.3
        self._glow.scale = 0.6
        self._ico.prime(0.25)
        self._chroma.prime()
        self._flare.prime()
        self._sparks.prime()
        self._text.opacity, self._text.offset = 0, ft.Offset(0, 0.4)
        self._rule_l.width = self._rule_r.width = 0
        _refresh(self)
        await _sleep(0.03)
        if not live():
            return
        self.visible = True
        _refresh(self)
        await _sleep(0.03)
        if not live():
            return
        if simple:
            self._text.opacity, self._text.offset = 1, ft.Offset(0, 0)
            _refresh(self)
            await _sleep(0.75)
        else:
            _buzz("light")
            self._ico.appear(260, 1.0, energy=1.0)
            self._ico.start(2.2)
            self._glow.opacity, self._glow.scale = 0.8, 0.9
            self._flare.burst(240, 0.8)
            _refresh(self)
            await _sleep(0.11)
            if not live():
                return
            # impact: crystal kick + shockwave + sparks + a light screen distortion
            cx, cy = (self._box.left or 0) + self.C_, (self._box.top or 0) + self.C_
            self._ico.punch(1.32, 1.0, settle=1.0, facets=5)
            self._glow.opacity, self._glow.scale = 1, 1.15
            self._ring.opacity, self._ring.scale = 1, 2.4
            self._flare.burst(160, 1.05)
            self._sparks.burst()
            distort(self, 0.42, x=cx, y=cy, color=col)
            _refresh(self)
            await _sleep(0.1)
            if not live():
                return
            self._ring.opacity = 0
            self._text.opacity, self._text.offset = 1, ft.Offset(0, 0)
            self._rule_l.width = self._rule_r.width = 34
            self._flare.settle(0.45, 0.7, 420)
            _refresh(self)
            _spawn(self._chroma.hit(0.5))
            await _sleep(0.36)
            if not live():
                return
            self._sparks.fade((350, 650))
            self._glow.opacity, self._glow.scale = 0.6, 0.95
            _refresh(self)
            await _sleep(0.22)
            if not live():
                return
            self._ico.vanish(320, 0.35)  # implodes into the label
            _refresh(self)
            await _sleep(0.12)
        if not live():
            return
        self._flare.fade()
        self._box.opacity = 0
        _refresh(self)
        await _sleep(0.3)
        if live():
            self._ico.stop()
            self.visible = False
            _refresh(self)


# --------------------------------------------------------------------------- 5 Skill links

_TAGS = {"acquired": "ACQUIRED", "next": "NEXT", "locked": "LOCKED"}


class SkillNode(ft.Container):
    """Framed skill node: thin double border, small centre tag (ACQUIRED / NEXT / LOCKED or
    any state string), English name, a tiny glyph caption. NEXT nodes pulse a soft glow."""

    def __init__(self, node_id: str, label: str, state: str = "locked", *,
                 path_color: str | None = None, on_tap: Callable[[str], Any] | None = None,
                 width: float = 104, height: float = 82, reduce: bool | None = None,
                 tooltip: str | None = None) -> None:
        self.node_id = node_id
        self.state = state
        self._on_tap_cb = on_tap
        self._reduce = reduce
        self._alive = False
        self._accent = self.accent_for(state, path_color)
        locked = state == "locked"
        acc = self._accent
        tip = tooltip or label
        tag = ft.Container(
            ft.Text(_TAGS.get(state, state.upper()), size=7.5, weight=ft.FontWeight.BOLD,
                    color=acc, style=ft.TextStyle(letter_spacing=1.6)),
            border=ft.Border.all(0.8, a(acc, 0.9)), bgcolor=a(acc, 0.10),
            padding=ft.Padding.symmetric(horizontal=5, vertical=1))
        name = ft.Text(label, size=12, weight=ft.FontWeight.W_700, max_lines=2,
                       overflow=ft.TextOverflow.ELLIPSIS, text_align=ft.TextAlign.CENTER,
                       color=a("#E4F0FF", 0.45) if locked else "#E4F0FF",
                       style=ft.TextStyle(height=1.1), tooltip=tip)
        seed = sum(map(ord, node_id))
        caption = cv.Canvas([cv.Path(glyphs.word_elements(2, 4, 6, 5.5, seed=seed),
                                     paint=_stroke(a(acc, 0.55), 0.8))], width=50, height=8)
        inner = ft.Container(
            ft.Column([tag, name, caption], spacing=3, tight=True,
                      alignment=ft.MainAxisAlignment.CENTER,
                      horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            border=ft.Border.all(0.8, a(acc, 0.4)),
            padding=ft.Padding.symmetric(horizontal=6, vertical=4),
            alignment=ft.Alignment.CENTER)
        self._halo = ft.Container(
            width=width, height=height, opacity=0, animate_opacity=_anim(900, ft.AnimationCurve.EASE_IN_OUT),
            shadow=[ft.BoxShadow(blur_radius=22, spread_radius=1, color=a(acc, 0.65))],
            bgcolor=a(acc, 0.04))
        frame = ft.Container(
            inner, width=width, height=height, padding=3,
            border=ft.Border.all(1.1, a(acc, 0.35 if locked else 0.95)),
            bgcolor=a("#0A1220", 0.92),
            shadow=None if locked else ft.BoxShadow(blur_radius=12, color=a(acc, 0.18)))
        super().__init__(content=ft.Stack([self._halo, frame], width=width, height=height),
                         width=width, height=height, on_click=self._tap,
                         scale=1, animate_scale=_anim(140, BACK), tooltip=tip)
        if state == "next":
            self._halo.opacity = 0.9

    @staticmethod
    def accent_for(state: str, path_color: str | None) -> str:
        if state == "locked":
            return DIM
        if state == "next":
            return th.current().primary
        return path_color or th.current().primary

    def did_mount(self) -> None:
        super().did_mount()
        r = reduced() if self._reduce is None else self._reduce
        if self.state == "next" and not r:
            self._alive = True
            with contextlib.suppress(Exception):
                self.page.run_task(self._pulse)

    def will_unmount(self) -> None:
        self._alive = False
        super().will_unmount()

    async def _pulse(self) -> None:
        on = False
        while self._alive:
            self._halo.opacity = 0.95 if on else 0.3
            on = not on
            _refresh(self._halo)
            await _sleep(0.95)

    async def _tap(self, _: Any = None) -> None:
        self.scale = 1.06
        _refresh(self)
        _buzz("light")
        await _sleep(0.14)
        self.scale = 1
        _refresh(self)
        if self._on_tap_cb is not None:
            res = self._on_tap_cb(self.node_id)
            if asyncio.iscoroutine(res):
                await res


class SkillLinkTree(ft.Container):
    """Static skill / side-quest link tree: root on top, children below, sibling links.

    nodes: [{"id", "label", "state": acquired|next|locked, "path_color": hex|None,
             "parent": id|None}, ...]   on_tap(node_id) -> sync or async.
    Fits 375 px (3 nodes per row at the default width); wider trees scroll horizontally."""

    def __init__(self, nodes: Sequence[dict], on_tap: Callable[[str], Any] | None = None, *,
                 node_width: float = 104, node_height: float = 82, h_gap: float = 12,
                 v_gap: float = 40, reduce: bool | None = None) -> None:
        self._on_tap = on_tap
        self._nw, self._nh, self._hg, self._vg = node_width, node_height, h_gap, v_gap
        self._reduce = reduce
        self._row = ft.Row([], scroll=ft.ScrollMode.AUTO, alignment=ft.MainAxisAlignment.CENTER)
        super().__init__(content=self._row, padding=ft.Padding.symmetric(vertical=4))
        self.set_nodes(nodes, update=False)

    def set_nodes(self, nodes: Sequence[dict], *, update: bool = True) -> None:
        self._row.controls = [self._build(list(nodes))]
        if update:
            _refresh(self)

    def _build(self, nodes: list[dict]) -> ft.Control:
        by_id = {n["id"]: n for n in nodes}
        kids: dict[str | None, list[str]] = {}
        for n in nodes:
            p = n.get("parent")
            kids.setdefault(p if p in by_id else None, []).append(n["id"])
        slot: dict[str, float] = {}
        depth: dict[str, int] = {}
        counter = [0]

        def place(nid: str, d: int, seen: frozenset) -> None:
            depth[nid] = d
            ch = [c for c in kids.get(nid, []) if c not in seen]
            if not ch:
                slot[nid] = counter[0]
                counter[0] += 1
                return
            for c in ch:
                place(c, d + 1, seen | {c})
            slot[nid] = (slot[ch[0]] + slot[ch[-1]]) / 2

        for root in kids.get(None, []):
            place(root, 0, frozenset({root}))
        nw, nh, hg, vg = self._nw, self._nh, self._hg, self._vg
        cols = max(1, counter[0])
        rows = max(depth.values(), default=0) + 1
        w = cols * nw + (cols - 1) * hg + 8
        h = rows * nh + (rows - 1) * vg + 8

        def xy(nid: str) -> tuple[float, float]:
            return 4 + slot[nid] * (nw + hg), 4 + depth[nid] * (nh + vg)

        lines: list[cv.Shape] = []
        for pid, ch in kids.items():
            if pid is None:
                continue
            px, py = xy(pid)
            for cid in ch:
                if cid not in slot:
                    continue
                cx, cy = xy(cid)
                n = by_id[cid]
                acc = SkillNode.accent_for(n.get("state", "locked"), n.get("path_color"))
                locked = n.get("state", "locked") == "locked"
                paint = _stroke(a(acc, 0.45 if locked else 0.9), 1.4,
                                dash=[4, 4] if locked else None)
                x0, y0 = px + nw / 2, py + nh + 5
                x1, y1 = cx + nw / 2, cy - 5
                if abs(x1 - x0) > 1:  # shorten diagonals toward the node corners like a fan
                    x0 += (x1 - x0) * 0.08
                lines.append(cv.Line(x0, y0, x1, y1, paint=paint))
                lines.append(cv.Circle(x1, y1, 2.2, paint=_solid(a(acc, 0.9))))
            ordered = sorted((c for c in ch if c in slot), key=lambda c: slot[c])
            for l_id, r_id in itertools.pairwise(ordered):  # sibling links
                if slot[r_id] - slot[l_id] > 1.01:
                    continue
                lx, ly = xy(l_id)
                rx, _ = xy(r_id)
                both_locked = all(by_id[i].get("state") == "locked" for i in (l_id, r_id))
                col = DIM if both_locked else th.current().primary
                lines.append(cv.Line(lx + nw + 2, ly + nh / 2, rx - 2, ly + nh / 2,
                                     paint=_stroke(a(col, 0.4 if both_locked else 0.8), 1.4,
                                                   dash=[3, 3] if both_locked else None)))
        children: list[ft.Control] = [ft.Container(cv.Canvas(lines, width=w, height=h),
                                                   left=0, top=0, width=w, height=h)]
        for nid in slot:
            n = by_id[nid]
            x, y = xy(nid)
            node = SkillNode(nid, n.get("label", nid), n.get("state", "locked"),
                             path_color=n.get("path_color"), on_tap=self._on_tap,
                             width=nw, height=nh, reduce=self._reduce,
                             tooltip=n.get("tooltip"))
            node.left, node.top = x, y
            children.append(node)
        return ft.Stack(children, width=w, height=h)


# --------------------------------------------------------------------------- 6 ClockSpiral

_ROMAN = ("XII", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI")


class ClockSpiral(ft.Container):
    """Focus-timer background: concentric clock rings with roman numerals receding into a bright
    centre (slightly off-axis, like a tunnel), each ring slowly rotating; progress ring on top.

    `spiral = ClockSpiral(300, content=timer_text)`; `spiral.start()` / `spiral.stop()`;
    `spiral.set_progress(0.42)` (None hides the arc). Rotation is one long implicit animation
    per ring (no Python loop); stop() freezes rings where they are."""

    SPAN_S = 2 * 3600  # one start() keeps rings turning for two hours

    def __init__(self, size: int = 300, *, color: str | None = None,
                 ring_color: str = "#CFC8FF", content: ft.Control | None = None,
                 rings: int = 5, reduce: bool | None = None) -> None:
        self._size = size
        self._color = color or CYAN
        self._reduce = reduce
        self._running = False
        self._want = False
        c = size / 2
        r0 = c * 0.98
        vx, vy = size * 0.07, -size * 0.045  # vanishing point offset
        self._rings: list[tuple[ft.Container, float, float]] = []  # (ctrl, turns/s, base)
        layers: list[ft.Control] = []
        bg = ft.Container(width=size, height=size, left=0, top=0, gradient=ft.RadialGradient(
            center=ft.Alignment(vx / c, vy / c), radius=0.62,
            colors=[a("#6A5CE0", 0.6), a("#3A3794", 0.38), a("#141A44", 0.18), a("#0B0F25", 0)],
            stops=[0, 0.35, 0.7, 1]))
        layers.append(bg)
        layers.append(ft.Container(Starfield(size, size, count=28, streaks=0,
                                             colors=(WHITE, "#D9D2FF", "#9FB4FF"), seed=41,
                                             hole=10).content, left=0, top=0, width=size,
                                   height=size, opacity=0.8))
        for k in range(rings):
            r = r0 * 0.7 ** k
            f = k / max(1, rings - 1)
            ring = self._ring(r, ring_color)
            _place(ring, c + vx * f, c + vy * f)
            direction = -1 if k % 2 else 1
            turns_per_s = direction / (70 - k * 11)
            self._rings.append((ring, turns_per_s, 0.0))
            layers.append(ring)
        core = _place(ft.Container(width=size * 0.42, height=size * 0.42,
                                   shape=ft.BoxShape.CIRCLE, gradient=ft.RadialGradient(
                                       colors=[WHITE, a(WHITE, 0.9), a("#C9BCFF", 0.55),
                                               a(VIOLET, 0.15), a(VIOLET, 0)],
                                       stops=[0, 0.07, 0.22, 0.5, 1])), c + vx, c + vy)
        layers.append(core)
        self._arc_r = c - 8
        self._progress: float | None = 0.0
        self._prog = cv.Canvas([], width=size, height=size)
        layers.append(ft.Container(self._prog, left=0, top=0, width=size, height=size))
        if content is not None:
            layers.append(ft.Container(content, left=0, top=0, width=size, height=size,
                                       alignment=ft.Alignment.CENTER))
        self._paint_progress()
        self._t0 = 0.0
        super().__init__(content=ft.Stack(layers, width=size, height=size), width=size,
                         height=size, ignore_interactions=content is None)

    def _ring(self, r: float, col: str) -> ft.Container:
        s = 2 * r + 4
        c = s / 2
        shapes: list[cv.Shape] = [
            cv.Circle(c, c, r, paint=_stroke(a(col, 0.8), 1.3)),
            cv.Circle(c, c, r * 0.86, paint=_stroke(a(col, 0.6), 1)),
            cv.Path(_ticks(c, c, r * 0.87, r * 0.99, 60 if r > 60 else 36),
                    paint=_stroke(a(col, 0.5), 0.9)),
        ]
        if r >= 36:
            fs = max(6.5, r * 0.12)
            for i, num in enumerate(_ROMAN):
                t = TAU * i / 12 - math.pi / 2
                shapes.append(cv.Text(c + r * 0.72 * math.cos(t), c + r * 0.72 * math.sin(t),
                                      num, style=ft.TextStyle(size=fs, color=a(WHITE, 0.85),
                                                              weight=ft.FontWeight.W_500),
                                      alignment=ft.Alignment.CENTER, rotate=t + math.pi / 2))
            shapes.append(cv.Circle(c, c, r * 0.56, paint=_stroke(a(col, 0.32), 0.8)))
        return ft.Container(cv.Canvas(shapes, width=s, height=s), width=s, height=s, rotate=0,
                            animate_rotation=_anim(1, LINEAR))

    # ---------------------------------------------------------------- progress
    def _paint_progress(self) -> None:
        c, r = self._size / 2, self._arc_r
        shapes: list[cv.Shape] = [cv.Circle(c, c, r, paint=_stroke(a(WHITE, 0.10), 3))]
        p = self._progress
        if p is not None and p > 0:
            sweep = TAU * min(1.0, p)
            for w, op in ((12, 0.22), (4.5, 1.0)):
                shapes.append(cv.Arc(c - r, c - r, 2 * r, 2 * r, -math.pi / 2, sweep,
                                     paint=_stroke(a(self._color, op), w,
                                                   cap=ft.StrokeCap.ROUND)))
            hx = c + r * math.cos(-math.pi / 2 + sweep)
            hy = c + r * math.sin(-math.pi / 2 + sweep)
            shapes += [cv.Circle(hx, hy, 9, paint=_solid(a(self._color, 0.35))),
                       cv.Circle(hx, hy, 4.2, paint=_solid(WHITE))]
        self._prog.shapes = shapes

    def set_progress(self, value: float | None) -> None:
        """0..1 fills the ring clockwise from 12 o'clock; None hides the arc."""
        self._progress = None if value is None else max(0.0, min(1.0, float(value)))
        self._paint_progress()
        _refresh(self._prog)

    # ---------------------------------------------------------------- rotation
    def _reduced(self) -> bool:
        return reduced() if self._reduce is None else bool(self._reduce)

    def start(self) -> None:
        """Begin slow rotation (no-op in reduce mode). Safe before mount."""
        self._want = True
        if self._running or self._reduced() or not _mounted(self):
            return
        self._running = True
        self._t0 = time.perf_counter()
        for i, (ring, tps, _) in enumerate(self._rings):
            base = float(ring.rotate or 0)
            self._rings[i] = (ring, tps, base)
            ring.animate_rotation = _anim(self.SPAN_S * 1000, LINEAR)
            ring.rotate = base + TAU * tps * self.SPAN_S
        _refresh(self)

    def advance(self, seconds: float = 1.0) -> None:
        """Turn the rings by `seconds` of rotation with a short linear animation. A per-tick
        alternative to start() for callers that already update once a second (the focus
        timer): on Flutter web, a 2-hour implicit rotation re-mounted after a tab switch
        crashed the skwasm renderer. No-op in reduce mode or when not mounted."""
        if self._reduced() or not _mounted(self):
            return
        ms = max(1, int(seconds * 1000))
        for ring, tps, _ in self._rings:
            ring.animate_rotation = _anim(ms, LINEAR)
            ring.rotate = float(ring.rotate or 0) + TAU * tps * seconds
        _refresh(self)

    def stop(self) -> None:
        """Freeze rings at their current angle."""
        self._want = False
        if not self._running:
            return
        self._running = False
        el = min(time.perf_counter() - self._t0, self.SPAN_S)
        for ring, tps, base in self._rings:
            ring.animate_rotation = _anim(1, LINEAR)
            ring.rotate = (base + TAU * tps * el) % TAU
        _refresh(self)

    def did_mount(self) -> None:
        super().did_mount()
        if self._want:
            self._want = False
            self.start()

    def will_unmount(self) -> None:
        self._running = False
        super().will_unmount()
