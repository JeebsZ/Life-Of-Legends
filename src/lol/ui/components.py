"""Reusable, juicy Flet controls for LUMA: Your Lifestyle QoL.

Rules
- Draw + animate only. No game rules, no lol.core imports: every component takes plain
  values and callbacks. The screen decides what a tap *means*; the component makes it *feel*.
- Every tap answers at once (pop + haptic) before the callback runs - never a dead tap.
- Callbacks may be sync or async. A callback returning `False` means "rejected" and the
  component reverts its optimistic animation (e.g. not enough coins).
- Animation methods (`play`, `show`, `count_to`, ...) are coroutines; call them from async
  handlers or `page.run_task(...)`. They no-op safely if the control is not on a page yet.

Haptics: call `use_haptics(ft.HapticFeedback())` once inside `main`.
Theme: colors are roles from `theme.C` (live); Path colors re-apply via `restyle()`.
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import inspect
import math
from collections.abc import Callable, Sequence
from typing import Any

import flet as ft

from lol.ui import ambient, audio, mixer, sfx
from lol.ui import effects as fx
from lol.ui import theme as th
from lol.ui.theme import C, Motion, Radius, Size, Space, Type

SNAP = ft.Animation(1, ft.AnimationCurve.LINEAR)  # instant jump (never reset animate_* to None)

FIRE = "#FF7B3A"  # streak flame - same in every theme
XP_ICON = ft.Icons.BOLT
COIN_ICON = ft.Icons.MONETIZATION_ON

Callback = Callable[..., Any] | None
Clip = str | tuple[str, int] | None  # voice clip kind, or (kind, variant index); see ui.audio

# --------------------------------------------------------------------------- helpers

_haptics: list[Any] = [None]


def voice(clip: Clip) -> None:
    """Play a Luma voice clip (fire-and-forget, silent on failure)."""
    if not clip:
        return
    kind, variant = (clip, None) if isinstance(clip, str) else clip
    audio.play(kind, variant)


def use_haptics(haptics: Any) -> None:
    """Register the page's ft.HapticFeedback() so components can buzz."""
    _haptics[0] = haptics


async def buzz(kind: str = "light") -> None:
    """kind: light | medium | heavy | select. Fire-and-forget: never delays the visual beat,
    silently skipped where unsupported (desktop/web)."""
    h = _haptics[0]
    if h is None:
        return
    fn = {"light": "light_impact", "medium": "medium_impact", "heavy": "heavy_impact",
          "select": "selection_click"}.get(kind, "light_impact")

    async def _go() -> None:
        with contextlib.suppress(Exception):
            await asyncio.wait_for(getattr(h, fn)(), 1.0)

    task = asyncio.get_running_loop().create_task(_go())
    _pending.add(task)
    task.add_done_callback(_pending.discard)


_pending: set[asyncio.Task] = set()


async def call(fn: Callback, *args: Any) -> Any:
    """Run a sync or async callback; returns its result (None if no callback)."""
    if fn is None:
        return None
    result = fn(*args)
    if inspect.isawaitable(result):
        result = await result
    return result


async def lumen_analyze(page: ft.Page, stages: Sequence[str] | None = None,
                        work: Callback = None, *, seconds: float = 2.4) -> Any:
    """Luma's staged analysis for any 'Luma thinks' moment: hum, orb, slow scan bar and
    staged text with a scan_tick per stage and scan_done on the last (mint 'ready' line).
    Tap skips; input is never held longer than 2.5 s.

    stages:  2+ texts, last one is the result line, e.g.
             ("SCANNING BODY DATA…", "CALCULATING…", "PLAN READY"). None -> the default
             ("ANALYSIS…", "MATCHING PATHS…", "PROPOSAL READY").
    work:    optional sync/async callable run WHILE the orb plays; its result is returned
             (exceptions propagate after the effect closes). The stages advance over
             `seconds`; the ready line shows once the work is done.
    seconds: 1.4-2.8 (2.4 is the house default; ~1.6-1.8 for lighter moments).

    Uses the page's LumenThinking overlay (the app's, with its hum) or adds one. Close any
    open sheet/dialog first - overlays draw under dialogs."""
    stages = tuple(stages) if stages else fx.LumenThinking.STAGES
    seconds = max(fx.LumenThinking.MIN_STAGED_S, min(fx.LumenThinking.MAX_STAGED_S, seconds))
    think = fx.thinking_for(page)
    if work is None:
        await think.play_staged(seconds, stages)
        return None
    async with think.session(stages[0], min_s=seconds, stages=stages):
        result = await call(work)
    return result


def refresh(*controls: ft.Control) -> None:
    """update() only the controls that are mounted."""
    for c in controls:
        with contextlib.suppress(RuntimeError):  # unmounted/frozen: nothing to repaint
            if c.page:
                c.update()


async def pop(ctrl: ft.Control, scale: float = Motion.POP_SCALE, ms: int = Motion.POP_MS) -> None:
    """Scale up then settle - the universal 'yes, that registered' beat."""
    if ctrl.animate_scale is None:
        ctrl.animate_scale = Motion.anim(ms, Motion.BACK)
    ctrl.scale = scale
    refresh(ctrl)
    await asyncio.sleep(ms / 1000)
    ctrl.scale = 1
    refresh(ctrl)


async def nudge(ctrl: ft.Control) -> None:
    """Small press-in for taps that do nothing new (e.g. an already-done quest)."""
    await pop(ctrl, Motion.PRESS_SCALE, 90)


CURRENCIES: tuple[tuple[str, str], ...] = (
    ("₱", "PHP (₱)"),
    ("$", "USD ($)"),
    ("€", "EUR (€)"),
    ("£", "GBP (£)"),
    ("¥", "JPY/CNY (¥)"),
    ("₹", "INR (₹)"),
    ("₩", "KRW (₩)"),
    ("A$", "AUD (A$)"),
    ("C$", "CAD (C$)"),
    ("S$", "SGD (S$)"),
)
_active_currency: str = "₱"


def set_currency(symbol: str) -> None:
    """Set the active display currency symbol for the session."""
    global _active_currency
    if symbol and symbol.strip():
        _active_currency = symbol.strip()


def currency_symbol() -> str:
    """Return the active display currency symbol."""
    return _active_currency


def peso(amount: float) -> str:
    """Format currency amount with the active currency symbol (e.g. $1,250 or ₱1,250.50)."""
    sym = _active_currency
    return f"{sym}{amount:,.0f}" if float(amount).is_integer() else f"{sym}{amount:,.2f}"


def chip(text: str, *, icon: ft.IconData | None = None, color: str = C.PRIMARY,
         dim: bool = False, solid: bool = False) -> ft.Container:
    """Small pill: '+25 XP', '+5', 'Daily', status labels."""
    fg = C.a(C.TEXT, 0.38) if dim else (C.BG if solid else color)
    bg = C.a(C.TEXT, 0.06) if dim else (color if solid else C.a(color, 0.16))
    items: list[ft.Control] = []
    if icon:
        items.append(ft.Icon(icon, size=14, color=fg))
    items.append(ft.Text(text, size=Type.CAPTION, weight=ft.FontWeight.BOLD, color=fg))
    return ft.Container(
        content=ft.Row(items, spacing=3, tight=True),
        bgcolor=bg, border_radius=Radius.PILL,
        padding=ft.Padding.symmetric(vertical=3, horizontal=8),
        animate=Motion.anim(Motion.FADE_MS),
    )


def xp_chip(xp: int, dim: bool = False) -> ft.Container:
    return chip(f"+{xp} XP", icon=XP_ICON, color=C.PRIMARY, dim=dim)


def coin_chip(coins: int, dim: bool = False) -> ft.Container:
    return chip(f"+{coins}", icon=COIN_ICON, color=C.GOLD, dim=dim)


def streak_badge(days: int) -> ft.Container:
    return chip(str(days), icon=ft.Icons.LOCAL_FIRE_DEPARTMENT, color=FIRE)


def path_avatar(icon: ft.IconData, color: str, size: int = 40) -> ft.Container:
    """Soft tinted circle with the Path icon."""
    return ft.Container(
        content=ft.Icon(icon, color=color, size=size * 0.5),
        width=size, height=size, border_radius=size / 2,
        bgcolor=C.a(color, 0.18), alignment=ft.Alignment.CENTER,
        animate=Motion.anim(Motion.FADE_MS),
    )


def _set_chip(c: ft.Container, text: str, color: str, *, dim: bool = False) -> None:
    """Recolor/relabel a chip built by chip() in place (keeps its animation)."""
    fg = C.a(C.TEXT, 0.38) if dim else color
    c.bgcolor = C.a(C.TEXT, 0.06) if dim else C.a(color, 0.16)
    row: ft.Row = c.content  # type: ignore[assignment]
    for item in row.controls:
        if isinstance(item, ft.Icon):
            item.color = fg
        elif isinstance(item, ft.Text):
            item.value, item.color = text, fg


def split_lead(text: str) -> tuple[str, str]:
    """'Notice: Quest cleared.' -> ('Notice:', ' Quest cleared.'). No short lead -> ('', text)."""
    i = text.find(":")
    if 0 < i <= 16 and " " not in text[:i].strip():
        return text[:i + 1], text[i + 1:]
    if text.startswith("Skill acquired:"):
        return "Skill acquired:", text[len("Skill acquired:"):]
    return "", text


def lead_spans(text: str, *, color: str = C.PRIMARY) -> list[ft.TextSpan]:
    """Text as spans with its lead word ('Analysis:') tinted and bold."""
    lead, rest = split_lead(text)
    spans: list[ft.TextSpan] = []
    if lead:
        spans.append(ft.TextSpan(text=lead,
                                 style=ft.TextStyle(color=color, weight=ft.FontWeight.BOLD)))
    spans.append(ft.TextSpan(text=rest))
    return spans


# --------------------------------------------------------------------------- XpBar


class XpBar(ft.Column):
    """Animated XP bar. Fill width is measured from the track, so it fits any screen.

    `play(steps)` takes progression.bar_steps() output: each 1.0 fills, snaps empty and
    rolls the level over (level label pops, `on_rollover(new_level)` fires in background).
    Gains queue up: a second play() waits for the first.
    """

    def __init__(self, value: float = 0.0, *, level: int | None = None,
                 caption: str | None = None, color: str | None = None,
                 height: int = Size.BAR, width: float | None = None,
                 show_level: bool = True, on_rollover: Callback = None) -> None:
        self.value = max(0.0, min(1.0, value))
        self.level = level
        self.on_rollover = on_rollover
        self._width = width or 0.0
        self._lock = asyncio.Lock()
        self._fill = ft.Container(
            height=height, border_radius=height / 2, bgcolor=color or C.PRIMARY, width=0,
            animate=Motion.anim(Motion.FILL_MS, Motion.EASE_CUBIC),
        )
        # Sparkle shimmer glow that sweeps across the leading edge of the XP bar
        self._sparkle = ft.Container(
            width=height * 1.5,
            height=height,
            border_radius=height / 2,
            bgcolor=ft.Colors.WHITE,
            opacity=0.0,
            scale=1.0,
            animate_opacity=Motion.anim(200),
            animate_scale=Motion.anim(200),
        )
        self._track = ft.Container(
            height=height, border_radius=height / 2, bgcolor=C.a(C.TEXT, 0.10),
            content=ft.Stack([self._fill, self._sparkle]), width=width, expand=width is None,
            on_size_change=self._on_size, clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        )
        self._level_text = ft.Text(
            f"Lv {level}" if level is not None else "", size=Type.LABEL,
            weight=ft.FontWeight.W_900, color=color or C.PRIMARY,
            visible=show_level and level is not None, scale=1,
            animate_scale=Motion.anim(Motion.POP_MS * 2, Motion.BACK),
        )
        self._caption = ft.Text(caption or "", size=Type.CAPTION, color=C.TEXT_DIM,
                                visible=caption is not None)
        super().__init__(
            controls=[
                ft.Row([self._level_text, self._track], spacing=Space.SM,
                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
                self._caption,
            ],
            spacing=Space.XS, tight=True,
        )
        if width:
            self._fill.width = width * self.value

    def _on_size(self, e: Any) -> None:
        w = getattr(e, "width", 0) or 0
        if w and abs(w - self._width) > 0.5:
            self._width = w
            if not self._lock.locked():
                self._fill.width = w * self.value
                refresh(self._fill)

    def set(self, value: float, *, caption: str | None = None, level: int | None = None) -> None:
        """Jump (with a short fill animation) to a value - no rollover juice."""
        self.value = max(0.0, min(1.0, value))
        self._fill.width = self._width * self.value
        if caption is not None:
            self._caption.value, self._caption.visible = caption, True
        if level is not None:
            self.level = level
            self._level_text.value = f"Lv {level}"
        refresh(self)

    def set_color(self, color: str, secondary_color: str | None = None) -> None:
        self._fill.bgcolor = color
        if secondary_color and secondary_color != color:
            self._fill.gradient = ft.LinearGradient(
                begin=ft.Alignment.CENTER_LEFT,
                end=ft.Alignment.CENTER_RIGHT,
                colors=[color, secondary_color],
            )
            self._fill.shadow = ft.BoxShadow(blur_radius=8, color=C.a(color, 0.45))
        else:
            self._fill.gradient = None
            self._fill.shadow = None
        self._level_text.color = color

    async def play(self, steps: Sequence[float], *, caption: str | None = None,
                   on_rollover: Callback = None) -> int:
        """Animate through bar_steps. Returns number of level-ups played."""
        on_rollover = on_rollover or self.on_rollover
        rolled = 0
        async with self._lock:
            reduce = False
            if self.page:
                reduce = getattr(getattr(self.page, "_app_profile", None), "reduce_effects", False)
            for target in steps:
                self.value = max(0.0, min(1.0, target))
                target_w = self._width * self.value
                self._fill.width = target_w
                if not reduce and target_w > 8:
                    self._sparkle.left = max(0.0, target_w - self._fill.height)
                    self._sparkle.opacity = 0.85
                    self._sparkle.scale = 1.3
                refresh(self._fill, self._sparkle)
                await asyncio.sleep(Motion.FILL_MS / 1000)
                if not reduce:
                    self._sparkle.opacity = 0.0
                    self._sparkle.scale = 1.0
                    refresh(self._sparkle)
                if target >= 1.0:  # crossed a level: snap empty, pop the label
                    rolled += 1
                    anim = self._fill.animate
                    self._fill.animate, self._fill.width = None, 0
                    if self.level is not None:
                        self.level += 1
                        self._level_text.value = f"Lv {self.level}"
                        self._level_text.scale = 1.45 if not reduce else 1.15
                    refresh(self)
                    self._fill.animate = anim
                    self.value = 0.0
                    if on_rollover is not None:
                        lvl = self.level if self.level is not None else rolled
                        if self.page:
                            self.page.run_task(call, on_rollover, lvl)
                    await asyncio.sleep(Motion.POP_MS * 2 / 1000)
                    self._level_text.scale = 1
                    refresh(self._level_text)
            if caption is not None:
                self._caption.value, self._caption.visible = caption, True
                refresh(self._caption)
        return rolled


# --------------------------------------------------------------------------- FloatingGain


class FloatingGain(ft.Container):
    """'+25 XP' / '+5 coins' text that rises and fades. Put it in a Stack (e.g. top-right
    of the header) and call `await g.xp(25)` / `await g.coins(5)` / `await g.play(...)`.
    """

    def __init__(self, *, size: int = 18, **kwargs: Any) -> None:
        self._icon = ft.Icon(XP_ICON, size=size, color=C.PRIMARY)
        self._text = ft.Text("", size=size, weight=ft.FontWeight.W_900, color=C.PRIMARY)
        super().__init__(
            content=ft.Row([self._icon, self._text], spacing=2, tight=True),
            opacity=0, offset=ft.Offset(0, 0.5), scale=0.6, ignore_interactions=True,
            **kwargs,
        )

    async def play(self, text: str, *, icon: ft.IconData | None = None,
                   color: str = C.PRIMARY) -> None:
        self._text.value, self._text.color = text, color
        self._icon.icon, self._icon.color, self._icon.visible = icon, color, icon is not None
        # reset instantly
        self.animate_offset = self.animate_opacity = self.animate_scale = SNAP
        self.offset, self.opacity, self.scale = ft.Offset(0, 0.5), 0, 0.6
        refresh(self)
        await asyncio.sleep(0.03)
        # rise: quick appear + overshoot, then drift up and fade
        self.animate_offset = Motion.anim(Motion.FLOAT_MS, Motion.EASE_CUBIC)
        self.animate_opacity = Motion.anim(120)
        self.animate_scale = Motion.anim(220, Motion.BACK)
        self.offset, self.opacity, self.scale = ft.Offset(0, -1.4), 1, 1
        refresh(self)
        await asyncio.sleep(Motion.FLOAT_MS * 0.55 / 1000)
        self.animate_opacity = Motion.anim(int(Motion.FLOAT_MS * 0.45), Motion.EASE)
        self.opacity = 0
        refresh(self)
        await asyncio.sleep(Motion.FLOAT_MS * 0.45 / 1000)

    async def xp(self, amount: int) -> None:
        await self.play(f"+{amount} XP", icon=XP_ICON, color=C.PRIMARY)

    async def coins(self, amount: int) -> None:
        await self.play(f"+{amount}", icon=COIN_ICON, color=C.ACCENT)


# --------------------------------------------------------------------------- LevelUpBanner


class LevelUpBanner(ft.Container):
    """Full-screen overlay host; add once: `page.overlay.append(banner)`.

    `await banner.show(5)` -> big LEVEL UP card with elastic pop, auto-dismiss.
    Path level-up: `await banner.show(3, title="CHEF LEVEL UP", subtitle="Chef",
    color=path_color, icon=path_icon)`. Calls queue, so stacked level-ups play in turn.
    Never blocks taps (ignore_interactions).
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._eyebrow = ft.Text("CONFIRMED", size=Type.CAPTION, weight=ft.FontWeight.BOLD,
                                style=ft.TextStyle(letter_spacing=3), visible=False)
        self._icon = ft.Icon(ft.Icons.EMOJI_EVENTS, size=36, color=C.ON_PRIMARY)
        self._title = ft.Text("LEVEL UP!", size=Type.TITLE - 1, weight=ft.FontWeight.BOLD,
                              color=C.ON_PRIMARY)
        self._level = ft.Text("", size=Type.HERO + 6, weight=ft.FontWeight.W_900,
                              color=C.ON_PRIMARY)
        self._sub = ft.Text("", size=Type.LABEL, weight=ft.FontWeight.W_600,
                            color=C.ON_PRIMARY, visible=False, text_align=ft.TextAlign.CENTER)
        self._card = ft.Container(
            content=ft.Column([self._eyebrow, self._icon, self._title, self._level, self._sub],
                              horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                              spacing=0, tight=True),
            bgcolor=C.PRIMARY, border_radius=Radius.LG + 4,
            padding=ft.Padding.symmetric(vertical=Space.XL, horizontal=Space.XXL + 8),
            shadow=ft.BoxShadow(blur_radius=40, spread_radius=2, color=C.a(C.PRIMARY, 0.45)),
            scale=0.4, opacity=0, rotate=-0.12,
            animate_scale=Motion.anim(Motion.BANNER_MS, Motion.ELASTIC),
            animate_opacity=Motion.anim(Motion.BANNER_MS // 2, Motion.EASE),
            animate_rotation=Motion.anim(Motion.BANNER_MS, Motion.ELASTIC),
        )
        self._scrim = ft.Container(expand=True, bgcolor=C.a(C.SCRIM, 0.35), opacity=0,
                                   animate_opacity=Motion.anim(Motion.BANNER_MS // 2))
        self._ico = fx.Icosphere(300, freq=2, facets=True, seed=12)  # crystal behind the card
        super().__init__(
            content=ft.Stack([self._scrim,
                              ft.Container(self._ico, alignment=ft.Alignment.CENTER, expand=True),
                              ft.Container(self._card, alignment=ft.Alignment.CENTER,
                                           expand=True)], expand=True),
            expand=True, ignore_interactions=True, visible=False,
        )

    async def show(self, level: int | str, *, title: str = "LEVEL UP!",
                   subtitle: str | None = None, color: str | None = None,
                   icon: ft.IconData | None = None, hold_s: float = Motion.BANNER_HOLD_S,
                   clip: Clip = None) -> None:
        """`clip`: Luma voice clip played as the card pops (see ui.audio)."""
        async with self._lock:
            if th.glowing():  # Arcane: navy panel, glowing frame, CONFIRMED eyebrow
                glow = color or th.current().primary
                self._card.bgcolor = C.a(th.current().surface, 0.94)
                self._card.border = ft.Border.all(2, glow)
                self._card.shadow = [
                    ft.BoxShadow(blur_radius=36, spread_radius=1, color=C.a(glow, 0.55)),
                    ft.BoxShadow(blur_radius=90, spread_radius=6, color=C.a(glow, 0.18)),
                ]
                self._eyebrow.visible, self._eyebrow.color = True, glow
                self._icon.color = self._level.color = glow
                self._title.color, self._sub.color = C.TEXT, C.TEXT_DIM
                self._title.style = ft.TextStyle(letter_spacing=2)
            else:
                ink = C.ON_PRIMARY if color is None else ft.Colors.with_opacity(0.88, "#000000")
                bg = color or C.PRIMARY
                self._card.bgcolor, self._card.border = bg, None
                self._card.shadow = ft.BoxShadow(blur_radius=40, spread_radius=2,
                                                 color=C.a(bg, 0.45))
                self._eyebrow.visible = False
                self._title.style = None
                for t in (self._icon, self._title, self._level, self._sub):
                    t.color = ink
            self._icon.icon = icon or ft.Icons.EMOJI_EVENTS
            self._title.value = title
            self._level.value = f"Lv {level}" if isinstance(level, int) else level
            self._sub.value, self._sub.visible = subtitle or "", bool(subtitle)
            self._ico.set_color(color or th.current().primary)
            self._ico.prime(0.3)
            self.visible = True
            refresh(self)
            await asyncio.sleep(0.02)
            await buzz("heavy")
            voice(clip)
            self._card.scale, self._card.opacity, self._card.rotate = 1, 1, 0
            self._scrim.opacity = 1
            if not fx.reduced():
                self._ico.appear(380, 1.0, 0.85, energy=1.0)
                self._ico.start(hold_s + 1.6)
            refresh(self)
            await asyncio.sleep(0.16)
            self._ico.punch(1.3, 1.0, settle=1.0, facets=8)
            fx.distort(self, 0.7, color=color or th.current().primary)
            refresh(self)
            await asyncio.sleep(max(0.1, hold_s + Motion.BANNER_MS / 1000 - 0.16))
            self._card.scale, self._card.opacity, self._card.rotate = 0.4, 0, -0.12
            self._scrim.opacity = 0
            self._ico.vanish(320, 1.6)
            refresh(self)
            await asyncio.sleep(Motion.BANNER_MS / 1000)
            self.visible = False
            refresh(self)


# --------------------------------------------------------------------------- LumenNotice


class LumenNotice(ft.Container):
    """Luma's top-anchored announcement panel; add once: `page.overlay.append(notice)`.

    `notice.say("Notice: Quest cleared. +40 XP to Warrior Path.")` queues a line (sync, safe from
    any handler). Each line: panel slides down, soft haptic, text types out (~25 ms/char, the
    lead word like 'Notice:' tinted), holds ~2.2 s, slides up. Lines queue and play in turn; a
    waiting queue shortens the hold so nothing lags far behind the action. `skip()` finishes the
    current line at once (cancellable). Never blocks taps (ignore_interactions).
    """

    CHAR_S = 0.025
    HOLD_S = 2.2
    HOLD_BUSY_S = 1.0  # hold when more lines are waiting
    SLIDE_MS = 320

    def __init__(self, top: float = Space.SM) -> None:
        """`top`: gap from the safe-area top; pass the header height so the XP bar stays in view."""
        self._queue: list[tuple[str, ft.IconData | None, Clip]] = []
        self._running = False
        self._skip = asyncio.Event()
        self._dot = ft.Container(width=7, height=7, border_radius=4, bgcolor=C.PRIMARY,
                                 shadow=ft.BoxShadow(blur_radius=8, spread_radius=1,
                                                     color=C.a(C.PRIMARY, 0.8)),
                                 opacity=1, animate_opacity=Motion.anim(300, Motion.EASE))
        self._icon = ft.Icon(ft.Icons.AUTO_AWESOME, size=14, color=C.a(C.PRIMARY, 0.7),
                             visible=False)
        eyebrow = ft.Row([
            self._dot,
            ft.Text("LUMA", size=11, weight=ft.FontWeight.BOLD, color=C.PRIMARY,
                    style=ft.TextStyle(letter_spacing=2.6)),
            ft.Container(expand=True), self._icon,
        ], spacing=Space.SM - 1, vertical_alignment=ft.CrossAxisAlignment.CENTER)
        # sizer: the full line, invisible, so the panel never grows while text types out
        self._sizer = ft.Text("", size=Type.BODY, opacity=0)
        self._typed = ft.Text("", size=Type.BODY, color=C.TEXT)
        self._panel = ft.Container(
            content=ft.Column([eyebrow, ft.Stack([self._sizer, self._typed])],
                              spacing=Space.XS + 2, tight=True),
            border_radius=Radius.MD + 2,
            padding=ft.Padding.only(left=Space.LG, right=Space.LG, top=Space.MD - 2,
                                    bottom=Space.MD),
            width=420, offset=ft.Offset(0, -1.6), opacity=0,
            animate_offset=Motion.anim(self.SLIDE_MS, Motion.EASE_CUBIC),
            animate_opacity=Motion.anim(self.SLIDE_MS // 2),
        )
        # Text floats over cards: real blur + near-opaque fill so nothing reads through.
        ambient.apply_glass(self._panel, "blur", fill=2.2)
        super().__init__(
            content=ft.SafeArea(ft.Container(
                self._panel, alignment=ft.Alignment.TOP_CENTER,
                padding=ft.Padding.only(left=Space.MD, right=Space.MD, top=top))),
            expand=True, ignore_interactions=True, visible=False,
            alignment=ft.Alignment.TOP_CENTER,
        )

    # -------------------------------------------------------------- public
    def say(self, text: str, icon: ft.IconData | None = None, clip: Clip = None) -> None:
        """Queue a line. Starts the player if idle (needs the notice on a page). `clip`: Luma
        voice clip (kind or (kind, variant)) spoken when this line starts showing."""
        if not text:
            return
        self._queue.append((text, icon, clip))
        if not self._running and self.page:
            self._running = True
            self.page.run_task(self._run)

    def skip(self) -> None:
        """Finish the current line now and move on (cancellable typewriter + hold)."""
        self._skip.set()

    # -------------------------------------------------------------- player
    async def _run(self) -> None:
        try:
            while self._queue:
                text, icon, clip = self._queue.pop(0)
                await self._play(text, icon, clip)
        finally:
            self._running = False
            self.visible = False
            refresh(self)

    async def _play(self, text: str, icon: ft.IconData | None, clip: Clip = None) -> None:
        self._skip.clear()
        lead, rest = split_lead(text)
        lead_style = ft.TextStyle(color=C.PRIMARY, weight=ft.FontWeight.BOLD)
        self._sizer.spans = lead_spans(text)
        self._typed.spans = []
        self._icon.icon, self._icon.visible = icon, icon is not None
        # slide in from above
        self.visible = True
        self._panel.animate_offset = SNAP
        self._panel.offset, self._panel.opacity = ft.Offset(0, -1.6), 0
        refresh(self)
        await asyncio.sleep(0.02)
        self._panel.animate_offset = Motion.anim(self.SLIDE_MS, Motion.EASE_CUBIC)
        self._panel.offset, self._panel.opacity = ft.Offset(0, 0), 1
        refresh(self._panel)
        await buzz("light")
        # soft ping just before Luma speaks; both wait for a reward chime to finish (mixer)
        mixer.cue(self.page, lambda: (sfx.play("notice", 0.7), voice(clip)))
        await self._wait(self.SLIDE_MS / 1000 * 0.6)
        # typewriter: a couple of chars per frame on long lines keeps ~25 ms/char overall
        total = len(lead) + len(rest)
        step = 1 if total <= 80 else 2
        shown = 0
        while shown < total and not self._skip.is_set():
            shown = min(total, shown + step)
            self._typed.spans = self._cut(lead, rest, shown, lead_style)
            self._dot.opacity = 0.35 if (shown // 6) % 2 else 1  # dot flickers while 'speaking'
            sfx.play("type", 0.4)  # light key ticks; sfx rate-limits them (~8/s, jittered)
            refresh(self._panel)
            await self._wait(self.CHAR_S * step)
        self._typed.spans = self._cut(lead, rest, total, lead_style)
        self._dot.opacity = 1
        refresh(self._panel)
        await self._wait(self.HOLD_BUSY_S if self._queue else self.HOLD_S)
        # slide away
        self._panel.offset, self._panel.opacity = ft.Offset(0, -1.6), 0
        refresh(self._panel)
        await asyncio.sleep(self.SLIDE_MS / 1000)

    @staticmethod
    def _cut(lead: str, rest: str, n: int, lead_style: ft.TextStyle) -> list[ft.TextSpan]:
        spans = []
        if lead:
            spans.append(ft.TextSpan(text=lead[:n], style=lead_style))
        if n > len(lead):
            spans.append(ft.TextSpan(text=rest[:n - len(lead)]))
        return spans

    async def _wait(self, seconds: float) -> None:
        """Sleep, but wake early if skip() was called."""
        if self._skip.is_set():
            return
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(self._skip.wait(), seconds)


# --------------------------------------------------------------------------- CoinCounter


class CoinCounter(ft.Container):
    """Coin balance pill. `await counter.count_to(n)` ticks the number up and pops."""

    def __init__(self, value: int = 0, *, size: int = Type.TITLE,
                 on_click: Callback = None) -> None:
        self.value = value
        self._text = ft.Text(f"{value:,}", size=size, weight=ft.FontWeight.W_900, color=C.TEXT)
        self._coin = ft.Icon(COIN_ICON, size=size + 4, color=C.GOLD, scale=1,
                             animate_scale=Motion.anim(Motion.POP_MS * 2, Motion.BACK))
        super().__init__(
            content=ft.Row([self._coin, self._text], spacing=Space.XS + 2, tight=True),
            bgcolor=C.a(C.GOLD, 0.14), border_radius=Radius.PILL,
            padding=ft.Padding.symmetric(vertical=Space.XS + 2, horizontal=Space.MD),
            scale=1, animate_scale=Motion.anim(Motion.POP_MS, Motion.BACK),
            on_click=on_click,
        )

    def set(self, value: int) -> None:
        self.value = value
        self._text.value = f"{value:,}"
        refresh(self._text)

    async def count_to(self, value: int) -> None:
        start, diff = self.value, value - self.value
        frames = max(1, min(abs(diff), 15))
        for i in range(1, frames + 1):
            self._text.value = f"{round(start + diff * i / frames):,}"
            refresh(self._text)
            await asyncio.sleep(Motion.COUNT_MS / 1000 / frames)
        self.value = value
        self._coin.scale = 1.35
        refresh(self._coin)
        await pop(self, 1.08)
        self._coin.scale = 1
        refresh(self._coin)


# --------------------------------------------------------------------------- simple bits


class SectionHeader(ft.Container):
    """'Today's quests  3        See all' row."""

    def __init__(self, title: str, *, count: int | None = None, action_text: str | None = None,
                 on_action: Callback = None, trailing: ft.Control | None = None) -> None:
        self._raw_title = title
        self._title = ft.Text(th.label(title), size=Type.TITLE, weight=ft.FontWeight.BOLD,
                              color=C.TEXT, style=ft.TextStyle(letter_spacing=th.label_spacing()))
        left: list[ft.Control] = [self._title]
        if count is not None:
            left.append(chip(str(count), color=C.TEXT_DIM))
        right: list[ft.Control] = []
        if trailing is not None:
            right.append(trailing)
        if action_text:
            right.append(ft.TextButton(action_text, on_click=on_action,
                                       style=ft.ButtonStyle(color=C.PRIMARY)))
        super().__init__(
            content=ft.Row([ft.Row(left, spacing=Space.SM, tight=True), *right],
                           alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                           vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.Padding.only(top=Space.SM, bottom=Space.XS),
        )
        th.on_theme_change(self)

    def restyle(self) -> None:
        self._title.value = th.label(self._raw_title)
        self._title.style = ft.TextStyle(letter_spacing=th.label_spacing())


class EmptyState(ft.Container):
    """Friendly empty view. Copy should invite, never scold."""

    def __init__(self, title: str = "All clear!", message: str = "Nothing here yet.", *,
                 icon: ft.IconData = ft.Icons.AUTO_AWESOME, action_text: str | None = None,
                 on_action: Callback = None, color: str = C.PRIMARY) -> None:
        items: list[ft.Control] = [
            ft.Container(ft.Icon(icon, size=34, color=color), width=72, height=72,
                         border_radius=36, bgcolor=C.a(color, 0.14),
                         alignment=ft.Alignment.CENTER),
            ft.Text(title, size=Type.TITLE, weight=ft.FontWeight.BOLD, color=C.TEXT,
                    text_align=ft.TextAlign.CENTER),
            ft.Text(message, size=Type.BODY - 1, color=C.TEXT_DIM,
                    text_align=ft.TextAlign.CENTER),
        ]
        if action_text:
            items.append(ft.Container(height=Space.XS))
            items.append(ft.FilledButton(action_text, on_click=on_action, height=Size.TAP,
                                         style=ft.ButtonStyle(bgcolor=color,
                                                              color=C.ON_PRIMARY)))
        super().__init__(
            content=ft.Column(items, horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                              spacing=Space.SM, tight=True),
            padding=ft.Padding.symmetric(vertical=Space.XXL, horizontal=Space.XL),
            alignment=ft.Alignment.CENTER,
        )


# --------------------------------------------------------------------------- QuestCard


class QuestCard(ft.Container):
    """One quest row. Tap = complete: pop + check + haptic now, then `on_complete(card)`,
    then fade to done. `on_complete` returning False reverts. Tapping a done card nudges.

    kind: "once" | "daily". streak > 0 shows a flame badge (never a 'failed' state).
    """

    def __init__(self, title: str, *, path_id: str | None = None, xp: int = 0, coins: int = 0,
                 done: bool = False, streak: int = 0, kind: str = "once", note: str = "",
                 icon: ft.IconData | None = None, color: str | None = None,
                 on_complete: Callback = None, on_long_press: Callback = None,
                 menu: ft.Control | None = None, data: Any = None) -> None:
        self.path_id, self.done, self.on_complete = path_id, done, on_complete
        self.xp, self.coins = xp, coins
        self._color_override = color
        self._busy = False
        self.tap_pos: tuple[float | None, float | None] = (None, None)  # page coords of a tap
        pc = color or th.path_color(path_id)
        self._flash = ft.Container(left=0, top=0, right=0, bottom=0, opacity=0,
                                   bgcolor=C.a(C.SUCCESS, 0.25),
                                   animate_opacity=Motion.anim(Motion.POP_MS * 2))
        self._avatar = path_avatar(icon or th.path_icon(path_id), pc)
        self._stripe = ft.Container(width=Size.STRIPE, bgcolor=pc, left=0, top=0, bottom=0,
                                    animate=Motion.anim(Motion.FADE_MS))
        self._title = ft.Text(title, size=Type.BODY + 1, weight=ft.FontWeight.W_600,
                              color=C.TEXT, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS,
                              tooltip=title)
        self._xp_chip = xp_chip(xp)
        self._coin_chip = coin_chip(coins)
        meta: list[ft.Control] = [self._xp_chip]
        if coins:
            meta.append(self._coin_chip)
        if streak > 0:
            meta.append(streak_badge(streak))
        if kind == "daily":
            meta.append(ft.Icon(ft.Icons.EVENT_REPEAT, size=16, color=C.TEXT_DIM,
                                tooltip="Daily"))
        self._note = ft.Text(note, size=Type.CAPTION, color=C.TEXT_DIM, max_lines=2,
                             overflow=ft.TextOverflow.ELLIPSIS, visible=bool(note),
                             tooltip=note if note else None)
        self._check_icon = ft.Icon(ft.Icons.RADIO_BUTTON_UNCHECKED, size=Size.ICON_LG,
                                   color=C.a(C.TEXT, 0.4))
        self._check = ft.Container(self._check_icon, width=Size.TAP, height=Size.TAP,
                                   alignment=ft.Alignment.CENTER, scale=1,
                                   animate_scale=Motion.anim(Motion.POP_MS * 2, Motion.BACK))
        full_tip = f"{title}\n{note}" if note else title
        body = ft.Row(
            [
                self._avatar,
                ft.Column([self._title, self._note,
                           ft.Row(meta, spacing=Space.XS + 2, wrap=True)],
                          spacing=Space.XS, expand=True, tight=True, tooltip=full_tip),
                self._check,
                *([menu] if menu is not None else []),
            ],
            spacing=Space.MD, vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        super().__init__(
            content=ft.Stack([
                self._flash,
                ft.Container(body, padding=ft.Padding.only(left=Space.MD + Size.STRIPE,
                                                           right=Space.XS, top=Space.MD,
                                                           bottom=Space.MD)),
                self._stripe,
            ]),
            border_radius=Radius.MD, clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            scale=1, opacity=1, data=data, tooltip=full_tip,
            animate=Motion.anim(Motion.FADE_MS),
            animate_opacity=Motion.anim(Motion.DONE_FADE_MS),
            animate_scale=Motion.anim(Motion.POP_MS, Motion.BACK),
            on_click=self._tap, on_long_press=on_long_press, ink=False,
            on_tap_down=self._tap_down,
        )
        ambient.apply_glass(self, "frost", tint=pc)
        self._apply_done(done)
        th.on_theme_change(self)

    def _tap_down(self, e: Any) -> None:
        self.tap_pos = ambient.card_center(e)

    def restyle(self) -> None:
        pc = self._color_override or th.path_color(self.path_id)
        ambient.set_glass_tint(self, pc)
        self._stripe.bgcolor = pc if not self.done else C.a(C.TEXT, 0.2)
        self._avatar.bgcolor = C.a(pc, 0.18)
        self._avatar.content.color = pc  # type: ignore[union-attr]

    def _apply_done(self, done: bool) -> None:
        self.done = done
        pc = self._color_override or th.path_color(self.path_id)
        self._check_icon.icon = ft.Icons.CHECK_CIRCLE if done else ft.Icons.RADIO_BUTTON_UNCHECKED
        self._check_icon.color = C.SUCCESS if done else C.a(C.TEXT, 0.4)
        self._title.style = (ft.TextStyle(decoration=ft.TextDecoration.LINE_THROUGH)
                             if done else None)
        self._title.color = C.TEXT_DIM if done else C.TEXT
        _set_chip(self._xp_chip, f"+{self.xp} XP", C.PRIMARY, dim=done)
        _set_chip(self._coin_chip, f"+{self.coins}", C.ACCENT, dim=done)
        self._stripe.bgcolor = C.a(C.TEXT, 0.2) if done else pc
        self._flash.opacity = 0
        self.opacity = 0.6 if done else 1

    def set_done(self, done: bool) -> None:
        self._apply_done(done)
        refresh(self)

    async def _tap(self, _: Any = None) -> None:
        if self._busy:
            return
        if self.done:
            await buzz("select")
            await nudge(self)
            return
        self._busy = True
        try:
            await buzz("medium")
            self._check_icon.icon, self._check_icon.color = ft.Icons.CHECK_CIRCLE, C.SUCCESS
            self._check.scale = 1.35
            self.scale, self._flash.opacity = Motion.POP_SCALE, 1
            refresh(self)
            await asyncio.sleep(Motion.POP_MS / 1000)
            self.scale, self._check.scale = 1, 1
            refresh(self)
            ok = await call(self.on_complete, self)
            if ok is False:
                self._apply_done(False)
                refresh(self)
                return
            await asyncio.sleep(0.15)
            self.set_done(True)
        finally:
            self._busy = False


# --------------------------------------------------------------------------- BillRow

BILL_STATUS = {
    # status: (label, color role, icon)
    "overdue": ("Overdue", C.DANGER, ft.Icons.ERROR_OUTLINE),
    "due_soon": ("Due soon", C.ACCENT, ft.Icons.SCHEDULE),
    "upcoming": ("Upcoming", C.TEXT_DIM, ft.Icons.EVENT),
    "paid": ("Paid", C.SUCCESS, ft.Icons.TASK_ALT),
}


class BillRow(ft.Container):
    """Bill line: status icon, name, due label, ₱ amount, Pay button.

    Pay = pop + haptic, flips to 'Paid', then `on_pay(row)` (False reverts).
    """

    def __init__(self, name: str, amount: float, *, status: str = "upcoming",
                 due_label: str = "", repeat_label: str | None = None, note: str = "",
                 on_pay: Callback = None, on_click: Callback = None, data: Any = None) -> None:
        self.status, self.on_pay = status, on_pay
        self._busy = False
        self._icon = ft.Icon(ft.Icons.EVENT, size=22)
        self._icon_box = ft.Container(self._icon, width=40, height=40, border_radius=20,
                                      alignment=ft.Alignment.CENTER,
                                      animate=Motion.anim(Motion.FADE_MS))
        self._chip = chip("", color=C.TEXT_DIM)
        sub = [self._chip]
        due = " · ".join(x for x in (due_label, repeat_label or "") if x)
        if due:
            sub.append(ft.Text(due, size=Type.CAPTION, color=C.TEXT_DIM))
        self._amount = ft.Text(peso(amount), size=Type.TITLE, weight=ft.FontWeight.W_800,
                               color=C.TEXT)
        self._pay = ft.IconButton(ft.Icons.CHECK, icon_color=C.ON_PRIMARY, bgcolor=C.PRIMARY,
                                  tooltip="Mark paid", on_click=self._tap_pay,
                                  width=Size.TAP, height=Size.TAP)
        self._pay_box = ft.Container(self._pay, scale=1,
                                     animate_scale=Motion.anim(Motion.POP_MS, Motion.BACK),
                                     animate_opacity=Motion.anim(Motion.FADE_MS))
        full_tip = f"{name}\n{note}" if note else name
        col_items: list[ft.Control] = [
            ft.Text(name, size=Type.BODY + 1, weight=ft.FontWeight.W_600,
                    color=C.TEXT, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS,
                    tooltip=full_tip),
        ]
        if note:
            col_items.append(ft.Text(note, size=Type.CAPTION, color=C.TEXT_DIM, max_lines=2,
                                     overflow=ft.TextOverflow.ELLIPSIS, tooltip=note))
        col_items.append(ft.Row(sub, spacing=Space.SM, wrap=True))
        super().__init__(
            content=ft.Row([
                self._icon_box,
                ft.Column(col_items, spacing=Space.XS, expand=True, tight=True),
                self._amount,
                self._pay_box,
            ], spacing=Space.MD, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            border_radius=Radius.MD,
            padding=ft.Padding.only(left=Space.MD, right=Space.SM, top=Space.SM + 2,
                                    bottom=Space.SM + 2),
            scale=1, animate=Motion.anim(Motion.FADE_MS),
            animate_scale=Motion.anim(Motion.POP_MS, Motion.BACK),
            animate_opacity=Motion.anim(Motion.DONE_FADE_MS),
            on_click=on_click, data=data, tooltip=full_tip,
        )
        ambient.apply_glass(self, "frost")
        self._apply(status)

    def _apply(self, status: str) -> None:
        self.status = status
        label, color, icon = BILL_STATUS.get(status, BILL_STATUS["upcoming"])
        self._icon.icon, self._icon.color = icon, color
        self._icon_box.bgcolor = C.a(color, 0.16)
        _set_chip(self._chip, label, color)
        paid = status == "paid"
        self._pay_box.visible = not paid
        self._amount.color = C.TEXT_DIM if paid else (C.DANGER if status == "overdue" else C.TEXT)
        self.opacity = 0.7 if paid else 1
        ambient.set_glass_tint(self, th.current().danger if status == "overdue" else None)
        if status == "overdue":  # keep a visible red hairline on every theme
            self.border = ft.Border.all(1, C.a(C.DANGER, 0.45))

    def set_status(self, status: str) -> None:
        self._apply(status)
        refresh(self)

    async def _tap_pay(self, _: Any = None) -> None:
        if self._busy or self.status == "paid":
            return
        self._busy = True
        prev = self.status
        try:
            await buzz("medium")
            self._pay_box.scale = 1.25
            refresh(self._pay_box)
            await asyncio.sleep(Motion.POP_MS / 1000)
            self._apply("paid")
            self.scale = Motion.POP_SCALE
            refresh(self)
            await asyncio.sleep(Motion.POP_MS / 1000)
            self.scale = 1
            self._pay_box.scale = 1
            refresh(self)
            if await call(self.on_pay, self) is False:
                self.set_status(prev)
        finally:
            self._busy = False


# --------------------------------------------------------------------------- RewardTile


class RewardTile(ft.Container):
    """Shop tile. kind "personal" (redeem for real life) or "theme" (cosmetic).

    States: affordable (Redeem/Buy), locked (lock + 'N more' + progress toward cost),
    owned theme ('Use'), active theme ('Equipped'). `set_coins(n)` re-evaluates.
    on_redeem(tile) for redeem/buy (False reverts), on_use(tile) for an owned theme.
    """

    def __init__(self, title: str, cost: int, *, coins: int = 0, kind: str = "personal",
                 icon: ft.IconData | None = None, swatch: Sequence[str] | None = None,
                 owned: bool = False, active: bool = False, on_redeem: Callback = None,
                 on_use: Callback = None, width: float | None = None, data: Any = None,
                 crown: bool = False, premium_locked: bool = False,
                 on_premium: Callback = None, note: str = "") -> None:
        self.title, self.cost, self.coins, self.kind = title, cost, coins, kind
        self.owned, self.active = owned, active
        self.on_redeem, self.on_use = on_redeem, on_use
        # crown: a premium-only item (badge); premium_locked: buyable only with premium, so
        # the button opens the premium offer (on_premium) instead of buying
        self.premium_locked, self.on_premium = premium_locked, on_premium
        self._busy = False
        if swatch:
            art: ft.Control = ft.Container(
                width=56, height=56, border_radius=28,
                gradient=ft.LinearGradient(colors=list(swatch), begin=ft.Alignment.TOP_LEFT,
                                           end=ft.Alignment.BOTTOM_RIGHT),
                border=ft.Border.all(2, C.a(C.TEXT, 0.15)),
            )
        else:
            art = ft.Container(ft.Icon(icon or ft.Icons.CARD_GIFTCARD, size=28, color=C.ACCENT),
                               width=56, height=56, border_radius=28,
                               bgcolor=C.a(C.ACCENT, 0.14), alignment=ft.Alignment.CENTER)
        self._cost = chip(f"{cost:,}", icon=COIN_ICON, color=C.ACCENT)
        self._progress = XpBar(min(1.0, coins / cost) if cost else 1.0, height=Size.BAR_MINI,
                               color=C.ACCENT, show_level=False)
        self._hint = ft.Text("", size=Type.CAPTION, color=C.TEXT_DIM)
        self._btn_text = ft.Text("", size=Type.LABEL, weight=ft.FontWeight.BOLD)
        self._btn_icon = ft.Icon(ft.Icons.LOCK, size=16)
        self._btn = ft.Container(
            content=ft.Row([self._btn_icon, self._btn_text], spacing=Space.XS, tight=True,
                           alignment=ft.MainAxisAlignment.CENTER),
            height=40, border_radius=Radius.PILL, alignment=ft.Alignment.CENTER,
            on_click=self._tap, scale=1,
            animate=Motion.anim(Motion.FADE_MS),
            animate_scale=Motion.anim(Motion.POP_MS, Motion.BACK),
        )
        if crown:
            art = ft.Stack([art, ft.Container(
                ft.Icon(ft.Icons.WORKSPACE_PREMIUM, size=14, color=C.BG), width=22, height=22,
                border_radius=11, bgcolor="#F5C66B", alignment=ft.Alignment.CENTER, right=0,
                top=0, tooltip="Premium item")], width=60, height=58)
        full_tip = f"{title}\n{note}" if note else title
        super().__init__(
            content=ft.Column([
                art,
                ft.Text(title, size=Type.BODY, weight=ft.FontWeight.W_600, color=C.TEXT,
                        max_lines=2, overflow=ft.TextOverflow.ELLIPSIS,
                        text_align=ft.TextAlign.CENTER, height=40, tooltip=full_tip),
                self._cost, self._progress, self._hint, self._btn,
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=Space.SM, tight=True),
            border_radius=Radius.MD, width=width, data=data, tooltip=full_tip,
            padding=Space.MD, scale=1,
            animate=Motion.anim(Motion.FADE_MS),
            animate_scale=Motion.anim(Motion.POP_MS, Motion.BACK),
        )
        self._apply()
        ambient.apply_glass(self, "frost")

    @property
    def affordable(self) -> bool:
        return self.coins >= self.cost

    def _apply(self) -> None:
        owned_theme = self.kind == "theme" and self.owned
        locked = not owned_theme and not self.affordable and not self.premium_locked
        self._cost.visible = not owned_theme
        self._progress.visible = locked
        self._progress.set(min(1.0, self.coins / self.cost) if self.cost else 1.0)
        self._hint.visible = locked
        self._hint.value = f"{self.cost - self.coins:,} more to go"
        if owned_theme and self.active:
            label, icon, fg, bg = "Equipped", ft.Icons.CHECK, C.SUCCESS, C.a(C.SUCCESS, 0.16)
        elif owned_theme:
            label, icon, fg, bg = "Use", ft.Icons.BRUSH, C.ON_PRIMARY, C.PRIMARY
        elif self.premium_locked:
            label, icon, fg, bg = "Premium", ft.Icons.WORKSPACE_PREMIUM, "#F5C66B",                 C.a("#F5C66B", 0.14)
        elif locked:
            label, icon, fg, bg = "Locked", ft.Icons.LOCK, C.TEXT_DIM, C.a(C.TEXT, 0.08)
        else:
            label = "Buy" if self.kind == "theme" else "Redeem"
            icon, fg, bg = COIN_ICON, C.ON_PRIMARY, C.PRIMARY
        self._btn_text.value, self._btn_text.color = label, fg
        self._btn_icon.icon, self._btn_icon.color = icon, fg
        self._btn.bgcolor = bg
        self.opacity = 0.85 if locked else 1

    def set_coins(self, coins: int) -> None:
        self.coins = coins
        self._apply()
        refresh(self)

    def set_owned(self, owned: bool, active: bool = False) -> None:
        self.owned, self.active = owned, active
        self._apply()
        refresh(self)

    async def _tap(self, _: Any = None) -> None:
        if self._busy:
            return
        owned_theme = self.kind == "theme" and self.owned
        if self.premium_locked and not owned_theme:
            await buzz("select")
            await call(self.on_premium, self)
            return
        if (owned_theme and self.active) or (not owned_theme and not self.affordable):
            await buzz("select")
            await nudge(self._btn)  # locked: soft nudge, no scolding
            return
        self._busy = True
        try:
            await buzz("medium")
            await pop(self, 1.05)
            if owned_theme:
                await call(self.on_use, self)
                return
            if await call(self.on_redeem, self) is False:
                return
            # celebrate briefly, then settle into the new state
            label = "Yours!" if self.kind == "theme" else "Enjoy!"
            self._btn_text.value, self._btn_icon.icon = label, ft.Icons.CELEBRATION
            self._btn.bgcolor = C.SUCCESS
            self._btn_text.color = self._btn_icon.color = C.ON_SUCCESS
            refresh(self._btn)
            await pop(self._btn, 1.12)
            await asyncio.sleep(0.9)
            if self.kind == "theme":
                self.owned = True
            self._apply()
            refresh(self)
        finally:
            self._busy = False


# --------------------------------------------------------------------------- Paths


class PathBadge(ft.Container):
    """Compact pill: [icon] Chef  Lv 3."""

    def __init__(self, path_id: str, *, name: str | None = None, level: int | None = None,
                 icon: ft.IconData | None = None, color: str | None = None,
                 on_click: Callback = None) -> None:
        self.path_id, self._color_override = path_id, color
        pc = color or th.path_color(path_id)
        self._icon = ft.Icon(icon or th.path_icon(path_id), size=16, color=pc)
        self._name = ft.Text(name or th.path_name(path_id), size=Type.LABEL,
                             weight=ft.FontWeight.BOLD, color=pc)
        items: list[ft.Control] = [self._icon, self._name]
        if level is not None:
            items.append(ft.Text(f"Lv {level}", size=Type.CAPTION, weight=ft.FontWeight.W_900,
                                 color=C.TEXT))
        super().__init__(
            content=ft.Row(items, spacing=Space.XS + 2, tight=True),
            bgcolor=C.a(pc, 0.15), border_radius=Radius.PILL,
            padding=ft.Padding.symmetric(vertical=Space.XS + 1, horizontal=Space.MD - 2),
            on_click=on_click, animate=Motion.anim(Motion.FADE_MS),
        )
        th.on_theme_change(self)

    def restyle(self) -> None:
        pc = self._color_override or th.path_color(self.path_id)
        self._icon.color = self._name.color = pc
        self.bgcolor = C.a(pc, 0.15)


class PathProgress(ft.Container):
    """Path row: icon, name, level, mini XP bar, caption. `await pp.play(steps)` animates
    a gain; each rollover pops the level and calls on_level_up(new_level).
    """

    def __init__(self, path_id: str, *, level: int = 1, value: float = 0.0,
                 caption: str | None = None, name: str | None = None,
                 icon: ft.IconData | None = None, color: str | None = None,
                 on_click: Callback = None, on_level_up: Callback = None) -> None:
        self.path_id, self._color_override = path_id, color
        self.on_level_up = on_level_up
        pc = color or th.path_color(path_id)
        self._avatar = path_avatar(icon or th.path_icon(path_id), pc, 44)
        self._level = ft.Text(f"Lv {level}", size=Type.LABEL, weight=ft.FontWeight.W_900,
                              color=pc, scale=1,
                              animate_scale=Motion.anim(Motion.POP_MS * 2, Motion.BACK))
        self.bar = XpBar(value, level=level, caption=caption, color=pc,
                         height=Size.BAR_MINI + 2, show_level=False)
        super().__init__(
            content=ft.Row([
                self._avatar,
                ft.Column([
                    ft.Row([ft.Text(name or th.path_name(path_id), size=Type.BODY + 1,
                                    weight=ft.FontWeight.W_600, color=C.TEXT),
                            self._level], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    self.bar,
                ], spacing=Space.XS + 2, expand=True, tight=True),
            ], spacing=Space.MD, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            border_radius=Radius.MD,
            padding=ft.Padding.symmetric(vertical=Space.MD, horizontal=Space.MD),
            on_click=on_click, scale=1,
            animate_scale=Motion.anim(Motion.POP_MS, Motion.BACK),
        )
        ambient.apply_glass(self, "frost", tint=pc)
        th.on_theme_change(self)

    def restyle(self) -> None:
        pc = self._color_override or th.path_color(self.path_id)
        ambient.set_glass_tint(self, pc)
        self._avatar.bgcolor = C.a(pc, 0.18)
        self._avatar.content.color = pc  # type: ignore[union-attr]
        self._level.color = pc
        self.bar.set_color(pc)

    def set(self, level: int, value: float, caption: str | None = None) -> None:
        self._level.value = f"Lv {level}"
        self.bar.set(value, caption=caption, level=level)

    async def play(self, steps: Sequence[float], *, caption: str | None = None) -> int:
        async def rolled(level: int) -> None:
            self._level.value, self._level.scale = f"Lv {level}", 1.5
            refresh(self._level)
            await asyncio.sleep(Motion.POP_MS * 2 / 1000)
            self._level.scale = 1
            refresh(self._level)
            await call(self.on_level_up, level)

        return await self.bar.play(steps, caption=caption, on_rollover=rolled)


# --------------------------------------------------------------------------- BottomNav

NAV_TABS: tuple[tuple[str, ft.IconData, ft.IconData] | None, ...] = (
    # label, icon, selected icon; None = the center slot (ArcaneSlot)
    ("Today", ft.Icons.CALENDAR_TODAY_OUTLINED, ft.Icons.CALENDAR_TODAY),
    ("Quests", ft.Icons.ASSIGNMENT_OUTLINED, ft.Icons.ASSIGNMENT),
    None,
    ("Rewards", ft.Icons.WORKSPACE_PREMIUM_OUTLINED, ft.Icons.WORKSPACE_PREMIUM),
    ("More", ft.Icons.MORE_HORIZ_ROUNDED, ft.Icons.MORE_HORIZ_ROUNDED),
)
NAV_CENTER = 2
NAV_H = 68  # bar height
SLOT_SIZE = 48
SLOT_SPIN_S = 28  # one slow turn of the rune ring (one rotate update per turn: cheap)


def _dot(badge: str | bool | None) -> ft.Badge | str | None:
    """True -> a small red dot; a string -> a count; None/False -> nothing."""
    if badge is True:
        return ft.Badge(small_size=9, bgcolor=C.DANGER)  # no label = dot
    return badge or None


class NavTab(ft.Container):
    """One bottom-nav tab: active cyan indicator line at the top, modern outline icon, caption."""

    def __init__(self, label: str, icon: ft.IconData, selected_icon: ft.IconData, *,
                 on_click: Callback = None) -> None:
        self._raw_label = label
        self.glyphs = (icon, selected_icon)
        self.indicator = ft.Container(
            width=38, height=3, border_radius=1.5, bgcolor=C.PRIMARY,
            shadow=ft.BoxShadow(blur_radius=8, spread_radius=1, color=C.a(C.PRIMARY, 0.8)),
            opacity=0, animate_opacity=Motion.anim(Motion.FADE_MS))
        self.glyph = ft.Icon(icon, size=23, color=C.TEXT_DIM)
        self.caption = ft.Text(th.tr(label), size=Type.CAPTION - 0.5, color=C.TEXT_DIM,
                               weight=ft.FontWeight.W_500, max_lines=1)
        super().__init__(
            content=ft.Column([
                self.indicator,
                ft.Container(height=4),
                self.glyph,
                ft.Container(height=2),
                self.caption,
            ], spacing=0, tight=True, alignment=ft.MainAxisAlignment.START,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            expand=1, height=NAV_H, alignment=ft.Alignment.TOP_CENTER, on_click=on_click,
            ink=True,
        )

    def refresh_label(self) -> None:
        self.caption.value = th.tr(self._raw_label)

    def set_selected(self, on: bool) -> None:
        self.indicator.opacity = 1 if on else 0
        self.glyph.icon = self.glyphs[1] if on else self.glyphs[0]
        self.glyph.color = C.PRIMARY if on else C.TEXT_DIM
        self.caption.color = C.PRIMARY if on else C.TEXT_DIM
        self.caption.weight = ft.FontWeight.W_700 if on else ft.FontWeight.W_500

    def set_badge(self, badge: str | bool | None) -> None:
        self.glyph.badge = _dot(badge)


def _rune_ticks(size: float = 48) -> list[ft.Control]:
    """16 static rune ticks around the ring; every 4th is a small diamond."""
    out: list[ft.Control] = []
    r, mid = size / 2 - 2, size / 2
    for n in range(16):
        a = 2 * math.pi * n / 16
        big = n % 4 == 0
        w, h = (3.5, 3.5) if big else (1.8, 3.5)
        out.append(ft.Container(
            width=w, height=h, left=mid + r * math.sin(a) - w / 2,
            top=mid - r * math.cos(a) - h / 2, rotate=a + (math.pi / 4 if big else 0),
            bgcolor=C.a(C.PRIMARY, 0.85 if big else 0.4), border_radius=1))
    return out


class ArcaneSlot(ft.Container):
    """The big center nav button: a glowing 3D spherical cyan orb with ambient radial backlight glow.
    Empty: crisp white '+' glyph. Pinned: the feature's icon + color and a short label.
    Active (its feature is on screen): brighter glow, bold label."""

    def __init__(self, *, on_click: Callback = None, on_long_press: Callback = None) -> None:
        self.color = C.PRIMARY
        self.active = False
        self.pinned = False
        self.angle = 0.0
        self.spinning = False
        self.glyph = ft.Icon(ft.Icons.ADD, size=24, color="#FFFFFF")
        self.core = ft.Container(self.glyph, width=42, height=42,
                                 shape=ft.BoxShape.CIRCLE, alignment=ft.Alignment.CENTER)
        self.halo = ft.Container(width=48, height=48, shape=ft.BoxShape.CIRCLE,
                                 animate=Motion.anim(Motion.FADE_MS))
        self.ring = ft.Container(ft.Stack(_rune_ticks(48), width=48, height=48),
                                 width=48, height=48, rotate=0,
                                 animate_rotation=ft.Animation(SLOT_SPIN_S * 1000,
                                                               ft.AnimationCurve.LINEAR),
                                 animate_opacity=Motion.anim(Motion.FADE_MS))
        self.orb = ft.Container(
            ft.Stack([self.halo, self.ring,
                      ft.Container(self.core, width=48, height=48,
                                   alignment=ft.Alignment.CENTER)],
                     width=48, height=48),
            scale=1, animate_scale=Motion.anim(Motion.POP_MS, Motion.BACK))
        self.caption = ft.Text("", size=Type.CAPTION - 2.5, color=C.TEXT_DIM, max_lines=1,
                               weight=ft.FontWeight.W_700, overflow=ft.TextOverflow.ELLIPSIS,
                               text_align=ft.TextAlign.CENTER, visible=False)
        self.layout = ft.Column(
            [self.orb, self.caption],
            spacing=1,
            tight=True,
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )
        super().__init__(
            content=self.layout,
            expand=1, height=NAV_H, alignment=ft.Alignment.CENTER,
            on_click=on_click, on_long_press=on_long_press,
        )
        self._paint()

    def _paint(self) -> None:
        col, on = self.color, self.active
        hex_col = col if isinstance(col, str) and col.startswith("#") else th.current().primary
        self.halo.shadow = [
            ft.BoxShadow(blur_radius=18, spread_radius=1, color=C.a(col, 0.85 if on else 0.65)),
            ft.BoxShadow(blur_radius=36, spread_radius=3, color=C.a(col, 0.40 if on else 0.22)),
        ]
        self.halo.bgcolor = ft.Colors.TRANSPARENT
        # 3D spherical gradient with specular highlight on top-left
        self.core.gradient = ft.RadialGradient(
            center=ft.Alignment(-0.35, -0.45), radius=0.9,
            colors=[C.a("#FFFFFF", 0.95), C.a(col, 0.95), ambient.mix(hex_col, "#0284C7", 0.6), "#0369A1"],
            stops=[0, 0.35, 0.75, 1],
        )
        self.core.border = ft.Border.all(1.5, C.a("#FFFFFF", 0.75 if on else 0.55))
        self.glyph.color = "#FFFFFF"
        self.caption.color = col if on else (C.TEXT if self.pinned else C.TEXT_DIM)
        self.caption.weight = ft.FontWeight.W_800 if on else ft.FontWeight.W_600
        self.caption.visible = self.pinned
        self.ring.opacity = 0.8 if on else (0.6 if self.pinned else 0.35)

    def set_pin(self, label: str | None, icon: ft.IconData | None = None,
                color: str | None = None) -> None:
        """label None -> empty slot ('+', no clutter)."""
        self.pinned = label is not None
        self.glyph.icon = icon if self.pinned and icon else ft.Icons.ADD
        self.glyph.size = 20 if self.pinned else 24
        self.color = color if self.pinned and color else C.PRIMARY
        self.caption.value = th.tr(label) if self.pinned and label else ""
        self.caption.visible = self.pinned
        self._paint()
        refresh(self)

    def set_active(self, on: bool) -> None:
        self.active = on
        self._paint()

    async def pulse(self, scale: float = 1.14) -> None:
        await pop(self.orb, scale, Motion.POP_MS + 40)

    async def spin(self, reduced: Callable[[], bool] = lambda: False) -> None:
        """Slow endless turn of the rune ring (one rotate update per turn). A single loop;
        it ends when the slot leaves the page."""
        if self.spinning:
            return
        self.spinning = True
        try:
            await asyncio.sleep(0.3)
            while True:
                try:
                    mounted = self.page is not None
                except RuntimeError:
                    mounted = False
                if not mounted:
                    return
                still = reduced()
                if not still:
                    self.angle += 2 * math.pi
                    self.ring.rotate = self.angle
                    refresh(self.ring)
                await asyncio.sleep(2 if still else SLOT_SPIN_S)
        finally:
            self.spinning = False


class ArcaneNavBar(ft.BottomAppBar):
    """Today · Quests · [center ArcaneSlot] · Rewards · More. Set as page.bottom_appbar.

    on_select(index) for a plain tab; on_center(e) / on_center_hold(e) for the center slot.
    `select(i)` moves the highlight (i == NAV_CENTER lights the slot); `set_badge(i, b)`:
    True = red dot, "3" = count, None = clear."""

    def __init__(self, selected: int = 0, *, on_select: Callback = None,
                 on_center: Callback = None, on_center_hold: Callback = None,
                 badges: dict[int, str | bool] | None = None) -> None:
        self.on_select = on_select
        self.items: dict[int, NavTab] = {}
        row: list[ft.Control] = []
        for n, spec in enumerate(NAV_TABS):
            if spec is None:
                self.slot = ArcaneSlot(on_click=on_center, on_long_press=on_center_hold)
                row.append(self.slot)
                continue
            label, icon, sel = spec
            tab = NavTab(label, icon, sel, on_click=lambda e, n=n: self._tap(n))
            self.items[n] = tab
            row.append(tab)
        self.selected_index = selected
        self.nav_row = ft.Row(row, spacing=0, vertical_alignment=ft.CrossAxisAlignment.CENTER)
        self.nav_container = ft.Container(
            content=self.nav_row,
            border=ft.Border(top=ft.BorderSide(1, C.a(C.PRIMARY, 0.22))),
            height=NAV_H,
        )
        super().__init__(
            content=self.nav_container,
            bgcolor=C.a(C.SURFACE, 0.94),
            padding=ft.Padding.only(left=4, right=4, top=0, bottom=6),
            height=NAV_H + 6,
            elevation=0,
            clip_behavior=ft.ClipBehavior.NONE,
            border_radius=ft.BorderRadius(top_left=22, top_right=22, bottom_left=0, bottom_right=0),
        )
        for n, b in (badges or {}).items():
            self.set_badge(n, b)
        self.select(selected)

    def _tap(self, index: int) -> None:
        if self.on_select:
            self.on_select(index)

    def select(self, index: int) -> None:
        self.selected_index = index
        for n, tab in self.items.items():
            tab.set_selected(n == index)
        self.slot.set_active(index == NAV_CENTER)
        refresh(self)

    def set_badge(self, index: int, badge: str | bool | None) -> None:
        if index in self.items:
            self.items[index].set_badge(badge)
        elif index == NAV_CENTER:
            self.slot.glyph.badge = _dot(badge)

    def refresh_labels(self) -> None:
        for tab in self.items.values():
            tab.refresh_label()
        refresh(self)


def build_bottom_nav(selected_index: int = 0, on_change: Callback = None,
                     badges: dict[int, str | bool] | None = None) -> ArcaneNavBar:
    """Gallery shortcut: an ArcaneNavBar whose plain tabs call on_change(index)."""
    return ArcaneNavBar(selected_index, on_select=on_change, badges=badges)


# --------------------------------------------------------------------------- Quest Board


class QuestSuggestionCard(ft.Container):
    """Quest Board card: 'Give me a quest' result with Skip / Reroll / Accept.

    - on_accept(card): pop + 'Added!' flash. Return False to revert.
    - on_reroll(card) / on_skip(card): may return a dict of show() kwargs (title, path_id,
      xp, coins, difficulty, note, header, analysis) - the card slides the new quest in.
      Or call show() yourself. header: small line above ("Proposal:"); analysis: a line under
      the note ("Analysis: 10 min, ..."). The text before the first ':' is tinted primary.
    """

    def __init__(self, title: str = "", *, path_id: str | None = None, xp: int = 0,
                 coins: int = 0, difficulty: int = 1, note: str = "",
                 on_accept: Callback = None, on_reroll: Callback = None,
                 on_skip: Callback = None) -> None:
        self.on_accept, self.on_reroll, self.on_skip = on_accept, on_reroll, on_skip
        self.path_id = path_id
        self._busy = False
        self._badge_slot = ft.Container()
        self._header = ft.Text("", size=Type.LABEL, weight=ft.FontWeight.BOLD, color=C.PRIMARY,
                               visible=False)
        self._analysis = ft.Text("", size=Type.LABEL, color=C.TEXT_DIM, visible=False)
        self._pips = ft.Row(spacing=2, tight=True)
        self._title = ft.Text("", size=Type.HEADLINE - 2, weight=ft.FontWeight.BOLD,
                              color=C.TEXT)
        self._note = ft.Text("", size=Type.LABEL + 1, color=C.TEXT_DIM)
        self._chips = ft.Row(spacing=Space.XS + 2)
        self._body = ft.Container(
            content=ft.Column([
                self._header,
                ft.Row([self._badge_slot, self._pips],
                       alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                self._title, self._note, self._analysis, self._chips,
            ], spacing=Space.SM, tight=True),
            offset=ft.Offset(0, 0), opacity=1,
            animate_offset=Motion.anim(Motion.SWAP_MS, Motion.EASE_CUBIC),
            animate_opacity=Motion.anim(Motion.SWAP_MS),
        )
        self._accept_text = ft.Text("Accept", size=Type.BODY, weight=ft.FontWeight.BOLD,
                                    color=C.ON_PRIMARY)
        self._accept_icon = ft.Icon(ft.Icons.ADD_TASK, size=20, color=C.ON_PRIMARY)
        self._accept = ft.Container(
            content=ft.Row([self._accept_icon, self._accept_text], spacing=Space.SM - 2,
                           tight=True, alignment=ft.MainAxisAlignment.CENTER),
            bgcolor=C.PRIMARY, border_radius=Radius.PILL, height=Size.TAP, expand=True,
            alignment=ft.Alignment.CENTER, on_click=self._tap_accept, scale=1,
            animate=Motion.anim(Motion.FADE_MS),
            animate_scale=Motion.anim(Motion.POP_MS, Motion.BACK),
        )
        self._dice = ft.Container(
            ft.Icon(ft.Icons.CASINO, color=C.PRIMARY, size=22), width=Size.TAP,
            height=Size.TAP, border_radius=Size.TAP / 2, alignment=ft.Alignment.CENTER,
            border=ft.Border.all(1.5, C.a(C.PRIMARY, 0.5)), on_click=self._tap_reroll,
            tooltip="Reroll", rotate=0,
            animate_rotation=Motion.anim(Motion.SWAP_MS * 2, Motion.BACK),
        )
        self._skip = ft.TextButton("Skip", on_click=self._tap_skip, height=Size.TAP,
                                   style=ft.ButtonStyle(color=C.TEXT_DIM))
        super().__init__(
            content=ft.Column([self._body,
                               ft.Row([self._skip, self._dice, self._accept],
                                      spacing=Space.SM,
                                      vertical_alignment=ft.CrossAxisAlignment.CENTER)],
                              spacing=Space.LG, tight=True),
            border_radius=Radius.LG, padding=Space.LG,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS, scale=1,
            animate_scale=Motion.anim(Motion.POP_MS, Motion.BACK),
        )
        ambient.apply_glass(self, "frost", tint=th.path_color(path_id), fill=1.1)
        self._fill(title, path_id, xp, coins, difficulty, note)
        th.on_theme_change(self)

    def _fill(self, title: str, path_id: str | None, xp: int, coins: int, difficulty: int,
              note: str, header: str = "", analysis: str = "") -> None:
        self.path_id = path_id
        self._header.value = th.label(header)
        self._header.style = ft.TextStyle(letter_spacing=th.label_spacing())
        self._header.visible = bool(header)
        self._analysis.spans = lead_spans(analysis)
        self._analysis.visible = bool(analysis)
        ambient.set_glass_tint(self, th.path_color(path_id))
        self.border = ft.Border.all(1, C.a(th.path_color(path_id), 0.35))
        self._badge_slot.content = PathBadge(path_id) if path_id else None
        d = max(1, min(3, difficulty))
        self._pips.controls = [
            ft.Icon(ft.Icons.STAR if i < d else ft.Icons.STAR_BORDER, size=16,
                    color=C.ACCENT if i < d else C.a(C.TEXT, 0.3))
            for i in range(3)
        ]
        self._title.value = title
        self._title.tooltip = title
        self._note.value, self._note.visible = note, bool(note)
        self._note.tooltip = note if note else None
        self._chips.controls = [xp_chip(xp), *([coin_chip(coins)] if coins else [])]

    def restyle(self) -> None:
        ambient.set_glass_tint(self, th.path_color(self.path_id))
        self.border = ft.Border.all(1, C.a(th.path_color(self.path_id), 0.35))

    async def show(self, title: str, path_id: str | None = None, xp: int = 0, coins: int = 0,
                   difficulty: int = 1, note: str = "", header: str = "", analysis: str = "",
                   *, direction: int = 1) -> None:
        """Slide the current quest out and the new one in. direction 1 = from right."""
        self._body.offset, self._body.opacity = ft.Offset(-0.25 * direction, 0), 0
        refresh(self._body)
        await asyncio.sleep(Motion.SWAP_MS / 1000)
        self._fill(title, path_id, xp, coins, difficulty, note, header, analysis)
        self._body.animate_offset = SNAP
        self._body.offset = ft.Offset(0.25 * direction, 0)
        refresh(self)
        await asyncio.sleep(0.02)
        self._body.animate_offset = Motion.anim(Motion.SWAP_MS, Motion.EASE_CUBIC)
        self._body.offset, self._body.opacity = ft.Offset(0, 0), 1
        refresh(self._body)
        await asyncio.sleep(Motion.SWAP_MS / 1000)

    async def _maybe_show(self, result: Any) -> None:
        if isinstance(result, dict):
            await self.show(**result)

    async def _tap_reroll(self, _: Any = None) -> None:
        if self._busy:
            return
        self._busy = True
        try:
            await buzz("light")
            self._dice.rotate = (self._dice.rotate or 0) + 3.1416
            refresh(self._dice)
            await self._maybe_show(await call(self.on_reroll, self))
        finally:
            self._busy = False

    async def _tap_skip(self, _: Any = None) -> None:
        if self._busy:
            return
        self._busy = True
        try:
            await buzz("select")
            await self._maybe_show(await call(self.on_skip, self))
        finally:
            self._busy = False

    async def _tap_accept(self, _: Any = None) -> None:
        if self._busy:
            return
        self._busy = True
        try:
            await buzz("medium")
            self._accept_icon.icon, self._accept_text.value = ft.Icons.CHECK, "Added!"
            self._accept.bgcolor = C.SUCCESS
            self._accept_icon.color = self._accept_text.color = C.ON_SUCCESS
            refresh(self._accept)
            await pop(self, 1.04)
            result = await call(self.on_accept, self)
            await asyncio.sleep(0.6)
            self._accept_icon.icon, self._accept_text.value = ft.Icons.ADD_TASK, "Accept"
            self._accept.bgcolor = C.PRIMARY
            self._accept_icon.color = self._accept_text.color = C.ON_PRIMARY
            refresh(self._accept)
            if result is not False:
                await self._maybe_show(result)
        finally:
            self._busy = False


# --------------------------------------------------------------------------- ThemeSwatch


class ThemeSwatch(ft.Container):
    """Theme picker orb for Me > Theme: a tiny preview of that theme's space (its light
    blooming out of its night, a coin-coloured star, a glow on glowing themes) + name; lock and
    price if not owned. Fixed width, so a wrapping Row lines swatches up as a grid."""

    WIDTH = 92

    def __init__(self, theme_id: str, *, selected: bool = False, owned: bool = True,
                 price: int | None = None, on_select: Callback = None) -> None:
        pal = th.THEMES[theme_id]
        self.theme_id, self.on_select, self.owned = theme_id, on_select, owned
        star = ft.Container(width=6, height=6, border_radius=3, bgcolor=pal.accent, left=29,
                            top=27, shadow=ft.BoxShadow(blur_radius=6,
                                                        color=C.a(pal.accent, 0.8)))
        lock = ft.Container(ft.Icon(ft.Icons.LOCK, size=16, color=pal.text), width=44,
                            height=44, alignment=ft.Alignment.CENTER,
                            bgcolor=C.a(pal.bg, 0.45), border_radius=22)
        self._ring = ft.Container(
            content=ft.Container(
                width=44, height=44, border_radius=22,
                gradient=ft.RadialGradient(center=ft.Alignment(-0.45, -0.5), radius=1.15,
                                           colors=[pal.primary, C.a(pal.primary, 0.35),
                                                   pal.surface_hi, pal.bg],
                                           stops=[0, 0.32, 0.62, 1]),
                border=ft.Border.all(1, C.a(pal.primary, 0.45)),
                shadow=ft.BoxShadow(blur_radius=14, color=C.a(pal.primary, 0.45))
                if pal.glow else None,
                content=ft.Stack([star] if owned else [star, lock], width=44, height=44),
            ),
            padding=3, border_radius=Radius.PILL,
            border=ft.Border.all(2.5, pal.primary if selected else "#00000000"),
            animate=Motion.anim(Motion.FADE_MS), scale=1,
            animate_scale=Motion.anim(Motion.POP_MS, Motion.BACK),
        )
        label = pal.name if owned or price is None else f"{price:,}"
        super().__init__(
            content=ft.Column([self._ring,
                               ft.Text(label, size=Type.CAPTION,
                                       weight=ft.FontWeight.BOLD if selected else None,
                                       color=C.TEXT if selected else C.TEXT_DIM)],
                              horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                              spacing=Space.XS, tight=True),
            on_click=self._tap, padding=Space.XS, width=self.WIDTH,
        )

    async def _tap(self, _: Any = None) -> None:
        await buzz("select")
        if self.page:
            self.page.run_task(pop, self._ring, 1.12)
        await call(self.on_select, self.theme_id)


# --------------------------------------------------------------------------- SideQuestCard


class ProgressRingBadge(ft.Stack):
    """Small progress ring with 'n/m' in the middle. `await ring.play(done)` fills smoothly."""

    def __init__(self, done: int, total: int, *, color: str = C.PRIMARY, size: int = 46) -> None:
        self.done, self.total = done, max(1, total)
        self._ring = ft.ProgressRing(value=done / self.total, stroke_width=4, color=color,
                                     bgcolor=C.a(C.TEXT, 0.10), width=size, height=size,
                                     stroke_cap=ft.StrokeCap.ROUND)
        self._label = ft.Text(f"{done}/{self.total}", size=Type.CAPTION,
                              weight=ft.FontWeight.W_900, color=C.TEXT)
        super().__init__([
            self._ring,
            ft.Container(self._label, width=size, height=size, alignment=ft.Alignment.CENTER),
        ], width=size, height=size, scale=1,
            animate_scale=Motion.anim(Motion.POP_MS * 2, Motion.BACK))

    def set_color(self, color: str) -> None:
        self._ring.color = color

    async def play(self, done: int) -> None:
        start, end = self.done / self.total, done / self.total
        self.done = done
        self._label.value = f"{done}/{self.total}"
        frames = 12
        for i in range(1, frames + 1):
            t = i / frames
            ease = 1 - (1 - t) ** 3  # ease-out cubic, like the XP bar
            self._ring.value = start + (end - start) * ease
            refresh(self)
            await asyncio.sleep(Motion.FILL_MS / 1000 / frames)


class SideQuestCard(ft.Container):
    """A side quest chain: Path avatar, skill name, rank eyebrow, progress ring and a step
    checklist. Tap an open step = complete it (pop + check + haptic now, then
    `on_step(card, index)`; False reverts). Done steps nudge. Finishing the last step plays
    a short celebration (`finished` turns True). `on_menu(card)` (the options button or a
    long-press) is for set-aside/abandon.

    steps: (title, note, xp, coins, done) tuples.
    """

    def __init__(self, skill_name: str, *, path_id: str | None,
                 steps: Sequence[tuple[str, str, int, int, bool]], eyebrow: str = "",
                 footer: str = "", on_step: Callback = None, on_menu: Callback = None,
                 data: Any = None) -> None:
        self.path_id, self.on_step, self.on_menu = path_id, on_step, on_menu
        self.skill_name = skill_name
        self.steps = [list(s) for s in steps]
        self._busy = False
        self.tap_pos: tuple[float | None, float | None] = (None, None)
        pc = th.path_color(path_id)
        done = sum(1 for s in self.steps if s[4])
        self._avatar = path_avatar(th.path_icon(path_id), pc, 42)
        self._eyebrow_raw = eyebrow
        self._eyebrow = ft.Text(th.label(eyebrow), size=Type.CAPTION, color=pc,
                                weight=ft.FontWeight.BOLD,
                                style=ft.TextStyle(letter_spacing=th.label_spacing()),
                                visible=bool(eyebrow))
        self.ring = ProgressRingBadge(done, len(self.steps), color=pc)
        menu = ft.IconButton(ft.Icons.MORE_VERT, icon_color=C.TEXT_DIM, icon_size=20,
                             tooltip="Options", width=40, height=Size.TAP,
                             on_click=self._menu, visible=on_menu is not None)
        header = ft.Row([
            self._avatar,
            ft.Column([self._eyebrow,
                       ft.Text(skill_name, size=Type.TITLE, weight=ft.FontWeight.BOLD,
                               color=C.TEXT, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS,
                               tooltip=skill_name)],
                      spacing=1, expand=True, tight=True),
            self.ring, menu,
        ], spacing=Space.MD - 2, vertical_alignment=ft.CrossAxisAlignment.CENTER)
        self._rows: list[ft.Container] = []
        self._checks: list[ft.Icon] = []
        self._titles: list[ft.Text] = []
        self._chips: list[ft.Container] = []
        for i, (title, note, xp, _coins, _done) in enumerate(self.steps):
            check = ft.Icon(ft.Icons.RADIO_BUTTON_UNCHECKED, size=Size.ICON, scale=1,
                            animate_scale=Motion.anim(Motion.POP_MS * 2, Motion.BACK))
            step_tip = f"{title}\n{note}" if note else title
            text = ft.Text(title, size=Type.BODY, weight=ft.FontWeight.W_600, max_lines=2,
                           overflow=ft.TextOverflow.ELLIPSIS, tooltip=step_tip)
            xpc = xp_chip(xp)
            col: list[ft.Control] = [text]
            if note:
                col.append(ft.Text(note, size=Type.CAPTION, color=C.TEXT_DIM, max_lines=3,
                                   overflow=ft.TextOverflow.ELLIPSIS, tooltip=note))
            row = ft.Container(
                ft.Row([check, ft.Column(col, spacing=1, expand=True, tight=True), xpc],
                       spacing=Space.MD - 2, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                padding=ft.Padding.symmetric(vertical=Space.SM + 2, horizontal=Space.SM),
                border_radius=Radius.SM, scale=1,
                animate=Motion.anim(Motion.FADE_MS),
                animate_scale=Motion.anim(Motion.POP_MS, Motion.BACK),
                on_click=functools.partial(self._tap_step, i),
                on_tap_down=self._tap_down,
                tooltip=step_tip,
            )
            self._rows.append(row)
            self._checks.append(check)
            self._titles.append(text)
            self._chips.append(xpc)
        self._repaint_all()
        self._footer = ft.Text(footer, size=Type.CAPTION, color=C.TEXT_DIM,
                               visible=bool(footer))
        super().__init__(
            content=ft.Column([header, ft.Column(self._rows, spacing=2, tight=True),
                               self._footer], spacing=Space.SM, tight=True),
            border_radius=Radius.MD, padding=Space.MD, data=data, scale=1, opacity=1,
            animate=Motion.anim(Motion.FADE_MS),
            animate_scale=Motion.anim(Motion.POP_MS, Motion.BACK),
            animate_opacity=Motion.anim(Motion.DONE_FADE_MS),
            on_long_press=self._menu if on_menu is not None else None,
        )
        ambient.apply_glass(self, "frost", tint=pc)
        self.border = ft.Border.all(1, C.a(pc, 0.35))  # the hairline is the Path color
        th.on_theme_change(self)

    def _tap_down(self, e: Any) -> None:
        self.tap_pos = ambient.card_center(e)

    @property
    def finished(self) -> bool:
        return all(s[4] for s in self.steps)

    def restyle(self) -> None:
        pc = th.path_color(self.path_id)
        ambient.set_glass_tint(self, pc)
        self.border = ft.Border.all(1, C.a(pc, 0.35))
        self._avatar.bgcolor = C.a(pc, 0.18)
        self._avatar.content.color = pc  # type: ignore[union-attr]
        self._eyebrow.color = pc
        self._eyebrow.value = th.label(self._eyebrow_raw)
        self._eyebrow.style = ft.TextStyle(letter_spacing=th.label_spacing())
        self.ring.set_color(pc)
        self._repaint_all()

    def _next_open(self) -> int | None:
        return next((i for i, s in enumerate(self.steps) if not s[4]), None)

    def _repaint_all(self) -> None:
        """Checks, strikethrough and the soft highlight on the next open step."""
        pc = th.path_color(self.path_id)
        nxt = self._next_open()
        for i, s in enumerate(self.steps):
            done = bool(s[4])
            check = self._checks[i]
            check.icon = ft.Icons.CHECK_CIRCLE if done else ft.Icons.RADIO_BUTTON_UNCHECKED
            check.color = C.SUCCESS if done else (pc if i == nxt else C.a(C.TEXT, 0.4))
            self._titles[i].color = C.TEXT_DIM if done else C.TEXT
            self._titles[i].style = (ft.TextStyle(decoration=ft.TextDecoration.LINE_THROUGH)
                                     if done else None)
            _set_chip(self._chips[i], f"+{s[2]} XP", C.PRIMARY, dim=done)
            self._rows[i].bgcolor = C.a(pc, 0.10) if i == nxt else None

    async def _menu(self, _: Any = None) -> None:
        if self._busy or self.on_menu is None:
            return
        await buzz("medium")
        await call(self.on_menu, self)

    async def _tap_step(self, i: int, _: Any = None) -> None:
        if self._busy:
            return
        row, check = self._rows[i], self._checks[i]
        if self.steps[i][4]:
            await buzz("select")
            await nudge(row)
            return
        self._busy = True
        try:
            await buzz("medium")
            check.icon, check.color, check.scale = ft.Icons.CHECK_CIRCLE, C.SUCCESS, 1.4
            row.scale, row.bgcolor = Motion.POP_SCALE, C.a(C.SUCCESS, 0.22)
            refresh(row)
            await asyncio.sleep(Motion.POP_MS / 1000)
            row.scale, check.scale = 1, 1
            refresh(row)
            if await call(self.on_step, self, i) is False:
                self._repaint_all()
                refresh(self)
                return
            self.steps[i][4] = True
            self._repaint_all()  # moves the "next step" highlight
            refresh(self)
            await self.ring.play(sum(1 for s in self.steps if s[4]))
            if self.finished:
                await self.celebrate()
        finally:
            self._busy = False

    async def celebrate(self) -> None:
        """All steps done: green flash + pop. The screen swaps the card out afterwards."""
        self.bgcolor = C.a(C.SUCCESS, 0.16)
        self.border = ft.Border.all(2, C.SUCCESS)
        refresh(self)
        await pop(self, 1.04, Motion.POP_MS * 2)
        await pop(self.ring, 1.3, Motion.POP_MS * 2)
