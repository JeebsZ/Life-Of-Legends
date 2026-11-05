"""Personalize: Luma's first-run flow (and Settings -> "Redo personalize", which keeps progress).

One question per screen over the living mind-space: Luma intro -> hero name + sigil (live name
plate) -> focus areas (multi-select) -> three "Do you relate?" cards -> age band -> sex (optional,
stored in BodyProfile so Body never asks twice) -> daily time + best time + an explicit reminder
opt-in -> mind-space theme (live preview) -> Luma's staged analysis -> personal plan reveal ->
"Begin your legend". A top bar shows the % complete, a small changing encouragement, Back and
Skip (where sensible); the footer is Back / Continue (Continue waits for an answer).

Draw + wire only: the mapping rules live in lol.core.onboarding (build_plan / apply).
`on_done(started_side_quest)` mounts the app shell.
"""

from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import flet as ft

from lol.core import onboarding as ob
from lol.ui import ambient, avatars, notify, sfx
from lol.ui import components as ui
from lol.ui import theme as th
from lol.ui.screens import common
from lol.ui.theme import C, Motion, Radius, Size, Space, Type

if TYPE_CHECKING:
    from lol.ui.app import App

STEPS = ("hello", "name", "focus", "relate0", "relate1", "relate2", "age", "sex", "time",
         "theme", "plan")
SKIPPABLE = {"focus", "relate0", "relate1", "relate2", "age", "sex", "time", "theme"}
CHEERS = {
    "hello": "", "name": "Nice to meet you", "focus": "Honesty helps",
    "relate0": "No wrong answers", "relate1": "You're doing great",
    "relate2": "Almost halfway", "age": "Keeps your tips safe", "sex": "Just a few more",
    "time": "Small is powerful", "theme": "Make it yours", "plan": "Your plan is ready",
}
DEFAULT_NAME = "Legend"
TYPE_S = 0.034  # typewriter: a little slower than notices, it is the first hello
AUTO_NEXT_S = 0.32  # single-choice steps move on by themselves after this beat
MAX_W = 480

FOCUS_ICONS = {
    "mind": ft.Icons.PSYCHOLOGY, "habits": ft.Icons.REPEAT, "energy": ft.Icons.BOLT,
    "food": ft.Icons.RESTAURANT, "money": ft.Icons.ACCOUNT_BALANCE_WALLET,
    "home": ft.Icons.SPA, "creativity": ft.Icons.PALETTE, "outside": ft.Icons.PARK,
}
STATEMENT_ICONS = {
    "fade": ft.Icons.BATTERY_2_BAR, "phone": ft.Icons.PHONE_IPHONE,
    "stuck": ft.Icons.HOURGLASS_TOP,
}
BUDGET_TEXT = {5: ("A spark", "5 min"), 15: ("A steady habit", "15 min"),
               30: ("A real session", "30 min"), 60: ("Deep dive", "60 min")}
DAY_ICONS = {"morning": ft.Icons.WB_SUNNY, "midday": ft.Icons.LIGHT_MODE,
             "evening": ft.Icons.WB_TWILIGHT, "night": ft.Icons.NIGHTLIGHT_ROUND}
SEXES = (("female", "Female", ft.Icons.FEMALE), ("male", "Male", ft.Icons.MALE),
         ("unspecified", "Prefer not to say", ft.Icons.REMOVE_CIRCLE_OUTLINE))
ANALYSIS = ("READING YOUR ANSWERS…", "MAPPING PATHS…", "PLAN READY")


def _copy(a: ob.OnboardingAnswers) -> ob.OnboardingAnswers:
    return dataclasses.replace(a, focus=list(a.focus), relate=dict(a.relate),
                               paths=list(a.paths))


class Onboarding(ft.Container):
    def __init__(self, app: App, on_done: Callable[[bool], Any], *, redo: bool = False) -> None:
        self.app, self.on_done, self.redo = app, on_done, redo
        g = app.game
        self.step = 0
        self.name = "" if g.profile.name == DEFAULT_NAME else g.profile.name
        self.avatar_id = avatars.get(g.profile.avatar_id).id
        self.answers = _copy(g.profile.onboarding) if redo else ob.OnboardingAnswers()
        self.sex: str | None = g.body.sex
        self.plan: ob.Plan | None = None
        self.start_starter = True
        self._busy = False
        self._revealed = False

        # --- top bar: back · progress (+ % and a cheer) · skip
        self._back = ft.IconButton(ft.Icons.ARROW_BACK, icon_color=C.TEXT_DIM, tooltip="Back",
                                   on_click=self._go_back, width=Size.TAP, height=Size.TAP,
                                   opacity=0, disabled=True,
                                   animate_opacity=Motion.anim(Motion.FADE_MS))
        self._skip = ft.TextButton("Skip", on_click=self._skip_step, height=Size.TAP,
                                   opacity=0, disabled=True,
                                   style=ft.ButtonStyle(color=C.TEXT_DIM),
                                   animate_opacity=Motion.anim(Motion.FADE_MS))
        self._fill = ft.Container(width=0, height=6, border_radius=3, bgcolor=C.PRIMARY,
                                  shadow=ft.BoxShadow(blur_radius=10,
                                                      color=C.a(C.PRIMARY, 0.55)),
                                  animate=Motion.anim(Motion.FILL_MS, Motion.EASE_CUBIC))
        self._track = ft.Container(ft.Stack([self._fill]), height=6, border_radius=3,
                                   bgcolor=C.a(C.TEXT, 0.12))
        self._pct = ft.Text("", size=Type.CAPTION, weight=ft.FontWeight.BOLD, color=C.PRIMARY)
        self._cheer = ft.Text("", size=Type.CAPTION, color=C.TEXT_DIM, opacity=1, max_lines=1,
                              overflow=ft.TextOverflow.ELLIPSIS,
                              animate_opacity=Motion.anim(Motion.FADE_MS))
        self._progress = ft.Column([
            self._track,
            ft.Row([self._pct, ft.Container(self._cheer, expand=True,
                                            alignment=ft.Alignment.CENTER_RIGHT)],
                   spacing=Space.SM),
        ], spacing=6, expand=True, tight=True, opacity=0,
            animate_opacity=Motion.anim(Motion.FADE_MS))
        top = ft.Row([self._back, self._progress, ft.Container(self._skip, width=64)],
                     vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=Space.XS)

        self._stage = ft.Container(
            expand=True, offset=ft.Offset(0, 0), opacity=1,
            animate_offset=Motion.anim(Motion.SWAP_MS + 80, Motion.EASE_CUBIC),
            animate_opacity=Motion.anim(Motion.SWAP_MS + 80),
        )
        self._cta = ft.Column(spacing=Space.SM, tight=True,
                              horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
        body = ft.Container(
            ft.Column([top, self._stage, self._cta], spacing=Space.MD, expand=True),
            width=MAX_W, expand=True,
            padding=ft.Padding.only(left=Space.GUTTER, right=Space.GUTTER, top=Space.XS,
                                    bottom=Space.LG),
        )
        super().__init__(
            ft.Stack([app.space,
                      ft.SafeArea(ft.Container(body, alignment=ft.Alignment.TOP_CENTER,
                                               expand=True), expand=True)], expand=True),
            expand=True, bgcolor=C.BG, opacity=1,
            animate_opacity=Motion.anim(Motion.FADE_MS + 100),
        )
        self._render()

    # ------------------------------------------------------------------ flow
    @property
    def kind(self) -> str:
        return STEPS[self.step]

    def start(self) -> None:
        """Call once the flow is on the page: Luma's orb appears and types the greeting."""
        self.app.page.run_task(self._greet)

    async def _greet(self) -> None:
        await asyncio.sleep(0.35)
        if self.step != 0:
            return
        sfx.play("lumen_hum", 0.8)
        await ui.buzz("light")
        self._orb.opacity, self._orb.scale = 1, 1
        ui.refresh(self._orb)
        await asyncio.sleep(0.55)
        line = (f"Welcome back, {self.app.game.profile.name}. Let's tune your path."
                if self.redo else "I am Luma, your guide. Let's shape a legend that fits "
                "your real life.")
        for i in range(1, len(line) + 1):
            if self.step != 0:
                return
            self._typed.value = line[:i]
            ui.refresh(self._typed)
            if i % 3 == 1 and line[i - 1] != " ":
                sfx.play("type", 0.5)
            await asyncio.sleep(TYPE_S)
        self._orb.scale = 1.1
        ui.refresh(self._orb)
        await asyncio.sleep(0.25)
        self._orb.scale = 1
        self._sub.opacity = 1
        self._begin.opacity, self._begin.disabled = 1, False
        ui.refresh(self._orb, self._sub, self._begin)

    async def _move(self, delta: int) -> None:
        if self._busy:
            return
        self._busy = True
        try:
            await ui.buzz("select")
            d = 1 if delta > 0 else -1
            self._stage.offset, self._stage.opacity = ft.Offset(-0.18 * d, 0), 0
            ui.refresh(self._stage)
            await asyncio.sleep((Motion.SWAP_MS + 80) / 1000)
            self.step = max(0, min(len(STEPS) - 1, self.step + delta))
            self._render()
            anim = self._stage.animate_offset
            self._stage.animate_offset = ui.SNAP
            self._stage.offset = ft.Offset(0.18 * d, 0)
            ui.refresh(self)
            await asyncio.sleep(0.03)
            self._stage.animate_offset = anim
            self._stage.offset, self._stage.opacity = ft.Offset(0, 0), 1
            ui.refresh(self._stage)
        finally:
            self._busy = False
        if self.kind == "plan" and delta > 0:
            self.app.page.run_task(self._analyze)

    async def _go_back(self, _: Any = None) -> None:
        await self._move(-1)

    async def _next(self, _: Any = None) -> None:
        if self.kind == "name":
            self.name = (self._name_field.value or "").strip()[:24]
        await self._move(1)

    async def _skip_step(self, _: Any = None) -> None:
        a, k = self.answers, self.kind
        if k == "focus":
            a.focus = []
        elif k.startswith("relate"):
            a.relate.pop(ob.STATEMENT_IDS[int(k[-1])], None)
        elif k == "age":
            a.age_band = ""
        elif k == "time":
            a.minutes, a.day_time = 0, ""
        await self._move(1)

    async def _auto_next(self, step: int) -> None:
        await asyncio.sleep(AUTO_NEXT_S)
        if self.step == step:
            await self._move(1)

    # ------------------------------------------------------------------ chrome
    def _bar_width(self) -> float:
        w = self.app.page.width or 375
        return max(120.0, min(w, MAX_W) - 2 * Space.GUTTER - Size.TAP - 64 - 2 * Space.XS)

    def _render(self) -> None:
        k = self.kind
        last = len(STEPS) - 1
        pct = round(self.step / last * 100)
        first = self.step == 0
        self._progress.opacity = 0 if first else 1
        self._fill.width = self._bar_width() * self.step / last
        self._pct.value = f"{pct}% complete"
        self._cheer.value = CHEERS.get(k, "")
        self._back.opacity = 0 if first or k == "plan" and self._revealed else 1
        self._back.disabled = first
        show_skip = k in SKIPPABLE
        self._skip.opacity, self._skip.disabled = (1 if show_skip else 0), not show_skip
        stage_fn = getattr(self, "_step_" + (k[:-1] if k.startswith("relate") else k))
        self._stage.content, self._cta.controls = stage_fn()

    def _footer(self, ready: bool, label: str = "Continue",
                icon: ft.IconData = ft.Icons.ARROW_FORWARD) -> list[ft.Control]:
        self._go = common.primary_button(label, self._next, icon=icon)
        self._go.disabled, self._go.opacity = not ready, 1 if ready else 0.4
        self._go.animate_opacity = Motion.anim(Motion.FADE_MS)
        back = common.secondary_button("Back", self._go_back, color=C.TEXT_DIM)
        return [ft.Row([ft.Container(back, expand=2), ft.Container(self._go, expand=3)],
                       spacing=Space.SM)]

    def _set_ready(self, ready: bool) -> None:
        self._go.disabled, self._go.opacity = not ready, 1 if ready else 0.4
        ui.refresh(self._go)

    @staticmethod
    def _title(text: str, sub: str = "", eyebrow: str = "") -> list[ft.Control]:
        out: list[ft.Control] = []
        if eyebrow:
            out.append(ft.Text(th.label(eyebrow), size=Type.CAPTION, weight=ft.FontWeight.BOLD,
                               color=C.PRIMARY, text_align=ft.TextAlign.CENTER,
                               style=ft.TextStyle(letter_spacing=th.label_spacing())))
        out.append(ft.Text(text, size=Type.HEADLINE + 2, weight=ft.FontWeight.W_900,
                           color=C.TEXT, text_align=ft.TextAlign.CENTER))
        if sub:
            out.append(ft.Text(sub, size=Type.BODY, color=C.TEXT_DIM,
                               text_align=ft.TextAlign.CENTER))
        return out

    @staticmethod
    def _privacy(text: str = "Never shown on your profile. Change it anytime.") -> ft.Control:
        return ft.Row([ft.Icon(ft.Icons.LOCK_OUTLINE, size=14, color=C.TEXT_DIM),
                       ft.Text(text, size=Type.CAPTION, color=C.TEXT_DIM)],
                      spacing=6, alignment=ft.MainAxisAlignment.CENTER)

    # ------------------------------------------------------------------ option cards
    def _option(self, label: str, *, sub: str = "", icon: ft.IconData | None = None,
                color: str | None = None, on: bool = False, multi: bool = False,
                on_tap: Callable[[ft.Container], Any], height: int = 60,
                center: bool = False, show_mark: bool = True) -> ft.Container:
        col = color or C.PRIMARY
        mark = ft.Icon(ft.Icons.CHECK_CIRCLE if on else (
            ft.Icons.RADIO_BUTTON_UNCHECKED if multi else ft.Icons.CIRCLE_OUTLINED),
            size=22, color=col if on else C.a(C.TEXT, 0.3))
        texts: list[ft.Control] = [ft.Text(label, size=Type.BODY, weight=ft.FontWeight.BOLD,
                                           color=C.TEXT, max_lines=1,
                                           overflow=ft.TextOverflow.ELLIPSIS)]
        if sub:
            texts.append(ft.Text(sub, size=Type.CAPTION, color=C.TEXT_DIM, max_lines=1,
                                 overflow=ft.TextOverflow.ELLIPSIS))
        parts: list[ft.Control] = []
        if icon is not None:
            parts.append(ui.path_avatar(icon, col, 38))
        parts.append(ft.Column(texts, spacing=0, tight=True, expand=True,
                               horizontal_alignment=ft.CrossAxisAlignment.CENTER if center
                               else ft.CrossAxisAlignment.START))
        if not center and show_mark:
            parts.append(mark)
        card = ft.Container(
            ft.Row(parts, spacing=Space.MD, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            height=height, padding=ft.Padding.symmetric(horizontal=Space.MD),
            border_radius=Radius.MD, scale=1, data=(col, mark, multi),
            animate=Motion.anim(Motion.FADE_MS),
            animate_scale=Motion.anim(Motion.POP_MS, Motion.BACK),
        )
        card.on_click = lambda e, c=card: on_tap(c)
        self._paint_option(card, on)
        return card

    @staticmethod
    def _paint_option(card: ft.Container, on: bool) -> None:
        col, mark, multi = card.data
        card.bgcolor = C.a(col, 0.17) if on else C.a(C.SURFACE_HI, 0.62)
        card.border = ft.Border.all(1.5, col if on else C.a(C.TEXT, 0.08))
        card.shadow = (ft.BoxShadow(blur_radius=20, color=C.a(col, 0.32)) if on else None)
        mark.icon = (ft.Icons.CHECK_CIRCLE if on else
                     ft.Icons.RADIO_BUTTON_UNCHECKED if multi else ft.Icons.CIRCLE_OUTLINED)
        mark.color = col if on else C.a(C.TEXT, 0.3)

    def _feedback(self, card: ft.Container, on: bool) -> None:
        self.app.page.run_task(ui.pop, card, 1.04 if on else 0.97)
        self.app.page.run_task(ui.buzz, "select")
        if on:
            sfx.play("scan_tick", 0.5)

    # ------------------------------------------------------------------ 1 hello
    def _step_hello(self) -> tuple[ft.Control, list[ft.Control]]:
        self._orb = ft.Container(
            ft.Icon(ft.Icons.AUTO_AWESOME, size=48, color=C.PRIMARY),
            width=120, height=120, border_radius=60, alignment=ft.Alignment.CENTER,
            bgcolor=C.a(C.PRIMARY, 0.12), border=ft.Border.all(1.5, C.a(C.PRIMARY, 0.6)),
            shadow=[ft.BoxShadow(blur_radius=44, spread_radius=2, color=C.a(C.PRIMARY, 0.38)),
                    ft.BoxShadow(blur_radius=100, spread_radius=10,
                                 color=C.a(C.PRIMARY, 0.14))],
            opacity=0, scale=0.6, animate_opacity=Motion.anim(600),
            animate_scale=Motion.anim(Motion.POP_MS * 4, Motion.BACK),
        )
        self._typed = ft.Text("", size=Type.HEADLINE, weight=ft.FontWeight.W_600,
                              color=C.TEXT, text_align=ft.TextAlign.CENTER)
        sub = ("Your level, coins and quests stay exactly as they are." if self.redo else
               "Eight quick questions, about a minute. Then I'll build your personal plan.")
        self._sub = ft.Text(sub, size=Type.BODY, color=C.TEXT_DIM,
                            text_align=ft.TextAlign.CENTER, opacity=0,
                            animate_opacity=Motion.anim(500))
        stage = ft.Column([
            ft.Container(expand=1),
            self._orb,
            ft.Text("LUMA", size=Type.CAPTION, weight=ft.FontWeight.BOLD, color=C.PRIMARY,
                    style=ft.TextStyle(letter_spacing=3)),
            ft.Container(self._typed, height=96, alignment=ft.Alignment.CENTER),
            self._sub,
            ft.Container(expand=2),
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=Space.MD)
        self._begin = common.primary_button("Personalize" if self.redo else "Begin",
                                            self._next, icon=ft.Icons.AUTO_AWESOME,
                                            expand=False)
        self._begin.opacity, self._begin.disabled = 0, True
        self._begin.animate_opacity = Motion.anim(Motion.FADE_MS + 100)
        cta: list[ft.Control] = [self._begin]
        if not self.redo:
            cta.append(ft.Text("Saved on this device as a guest. Cloud backup comes later.",
                               size=Type.CAPTION, color=C.TEXT_DIM,
                               text_align=ft.TextAlign.CENTER))
        if self.step == 0 and self._typed.value == "" and getattr(self, "_greeted", False):
            self._orb.opacity, self._orb.scale = 1, 1  # came back with Back: no replay
            self._typed.value = "Ready when you are."
            self._sub.opacity, self._begin.opacity, self._begin.disabled = 1, 1, False
        self._greeted = True
        return stage, cta

    # ------------------------------------------------------------------ 2 name + sigil
    def _step_name(self) -> tuple[ft.Control, list[ft.Control]]:
        av = avatars.get(self.avatar_id)
        self._plate_bubble = avatars.bubble(self.avatar_id, 72)
        self._plate_name = ft.Text(self.name or DEFAULT_NAME, size=Type.DISPLAY,
                                   weight=ft.FontWeight.W_900, color=C.TEXT, max_lines=1,
                                   overflow=ft.TextOverflow.ELLIPSIS,
                                   text_align=ft.TextAlign.CENTER)
        self._plate_sigil = ft.Text(f"{av.name} sigil · Level 1", size=Type.LABEL,
                                    color=C.TEXT_DIM)
        self._plate = ambient.glass(ft.Column([
            ft.Text(th.label("Hero"), size=Type.CAPTION, weight=ft.FontWeight.BOLD,
                    color=av.color, style=ft.TextStyle(letter_spacing=3)),
            self._plate_bubble, self._plate_name, self._plate_sigil,
        ], spacing=Space.SM, tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            radius=Radius.LG, padding=Space.LG, tint=av.color, scale=1,
            animate_scale=Motion.anim(Motion.POP_MS, Motion.BACK))

        def typed(e: Any) -> None:
            self.name = (e.control.value or "").strip()[:24]
            self._plate_name.value = self.name or DEFAULT_NAME
            ui.refresh(self._plate_name)

        self._name_field = common.text_field("Hero name", on_submit=self._next)
        self._name_field.value = self.name
        self._name_field.hint_text = DEFAULT_NAME
        self._name_field.max_length = 24
        self._name_field.capitalization = ft.TextCapitalization.WORDS
        self._name_field.on_change = typed

        def picked(aid: str) -> None:
            self.avatar_id = aid
            a = avatars.get(aid)
            avatars.restyle_bubble(self._plate_bubble, aid)
            self._plate_sigil.value = f"{a.name} sigil · Level 1"
            ambient.set_glass_tint(self._plate, a.color)
            ui.refresh(self._plate)
            self.app.page.run_task(ui.pop, self._plate, 1.04)
            self.app.page.run_task(self.app.fx_burst.burst, None, None, color=a.color,
                                   count=16, ring=False)

        stage = ft.Column([
            *self._title("What shall I call you?",
                         "A name, a nickname or a title. You can change it later."),
            self._plate,
            self._name_field,
            avatars.AvatarPicker(self.avatar_id, size=42, on_change=picked),
        ], spacing=Space.MD, horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            scroll=ft.ScrollMode.AUTO)
        return stage, self._footer(True)

    # ------------------------------------------------------------------ 3 focus areas
    def _step_focus(self) -> tuple[ft.Control, list[ft.Control]]:
        a = self.answers

        def tap(fid: str, card: ft.Container) -> None:
            on = fid not in a.focus
            if on:
                a.focus.append(fid)
            else:
                a.focus.remove(fid)
            self._paint_option(card, on)
            ui.refresh(card)
            self._feedback(card, on)
            self._set_ready(bool(a.focus))

        cards = []
        for fid, (label, paths) in ob.FOCUS_AREAS.items():
            sub = " · ".join(th.path_name(p) for p in paths)
            cards.append(self._option(label, sub=sub, icon=FOCUS_ICONS[fid],
                                      color=th.path_color(paths[0]), on=fid in a.focus,
                                      multi=True, on_tap=lambda c, f=fid: tap(f, c)))
        stage = ft.Column([
            *self._title("Which parts of life feel out of control?",
                         "Choose all that apply. No judgment, just a starting point."),
            ft.Container(height=Space.XS),
            *cards,
        ], spacing=Space.SM, horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            scroll=ft.ScrollMode.AUTO)
        return stage, self._footer(bool(a.focus))

    # ------------------------------------------------------------------ 4 do you relate?
    def _step_relate(self) -> tuple[ft.Control, list[ft.Control]]:
        idx = int(self.kind[-1])
        sid, text = ob.STATEMENTS[idx]
        current = self.answers.relate.get(sid)
        pal = th.current()
        col = (pal.primary, pal.accent, pal.success)[idx]
        art = ft.Container(
            ft.Icon(STATEMENT_ICONS[sid], size=56, color=col),
            width=132, height=132, border_radius=66, alignment=ft.Alignment.CENTER,
            bgcolor=C.a(col, 0.12), border=ft.Border.all(1.5, C.a(col, 0.5)),
            shadow=[ft.BoxShadow(blur_radius=48, spread_radius=2, color=C.a(col, 0.32))],
        )
        quote = ambient.glass(ft.Column([
            ft.Icon(ft.Icons.FORMAT_QUOTE, color=C.a(col, 0.7), size=28),
            ft.Text(text, size=Type.HEADLINE, weight=ft.FontWeight.W_700, color=C.TEXT,
                    text_align=ft.TextAlign.CENTER),
        ], spacing=Space.XS, tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            radius=Radius.LG, padding=Space.XL, tint=col)
        stage = ft.Column([
            ft.Container(expand=1),
            *self._title("Do you relate to this?", eyebrow=f"Statement {idx + 1} of 3"),
            ft.Container(height=Space.SM),
            art,
            ft.Container(height=Space.SM),
            quote,
            ft.Container(expand=2),
        ], spacing=Space.SM, horizontal_alignment=ft.CrossAxisAlignment.CENTER)

        def answer(yes: bool, btn: ft.Container) -> None:
            self.answers.relate[sid] = yes
            for b, v in ((self._yes, True), (self._no, False)):
                self._paint_option(b, v == yes)
            ui.refresh(self._yes, self._no)
            self._feedback(btn, True)
            self.app.page.run_task(self._auto_next, self.step)

        self._no = self._option("No", icon=ft.Icons.THUMB_DOWN_ALT_OUTLINED,
                                color=C.TEXT_DIM, on=current is False, height=60,
                                on_tap=lambda c: answer(False, c), center=True)
        self._yes = self._option("Yes", icon=ft.Icons.THUMB_UP_ALT_OUTLINED, color=col,
                                 on=current is True, height=60,
                                 on_tap=lambda c: answer(True, c), center=True)
        return stage, [ft.Row([ft.Container(self._no, expand=1),
                               ft.Container(self._yes, expand=1)], spacing=Space.SM)]

    # ------------------------------------------------------------------ 5 age band
    def _single(self, options: list[tuple[str, str, ft.IconData | None]], current: str | None,
                pick: Callable[[str], Any], *, cols: int = 6) -> ft.ResponsiveRow:
        cards: dict[str, ft.Container] = {}

        def tap(key: str, card: ft.Container) -> None:
            pick(key)
            for k, c in cards.items():
                self._paint_option(c, k == key)
            ui.refresh(*cards.values())
            self._feedback(card, True)
            self._set_ready(True)
            self.app.page.run_task(self._auto_next, self.step)

        for key, label, icon in options:
            card = self._option(label, icon=icon, on=key == current, height=60,
                                on_tap=lambda c, k=key: tap(k, c), center=icon is None)
            card.col = cols
            cards[key] = card
        return ft.ResponsiveRow(list(cards.values()), spacing=Space.SM, run_spacing=Space.SM)

    def _step_age(self) -> tuple[ft.Control, list[ft.Control]]:
        a = self.answers

        def pick(band: str) -> None:
            a.age_band = band

        grid = self._single([(b, b, None) for b in ob.AGE_BANDS], a.age_band or None, pick)
        stage = ft.Column([
            ft.Container(height=Space.SM),
            *self._title("What's your age range?",
                         "Just a range. It keeps my health tips safe for you."),
            ft.Container(height=Space.SM),
            grid,
            ft.Container(height=Space.XS),
            self._privacy(),
        ], spacing=Space.SM, horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            scroll=ft.ScrollMode.AUTO)
        return stage, self._footer(bool(a.age_band))

    # ------------------------------------------------------------------ 6 sex (formulas)
    def _step_sex(self) -> tuple[ft.Control, list[ft.Control]]:
        def pick(value: str) -> None:
            self.sex = value

        grid = self._single([(k, label, icon) for k, label, icon in SEXES], self.sex, pick,
                            cols=12)
        stage = ft.Column([
            ft.Container(height=Space.SM),
            *self._title("Which formulas fit you?",
                         "Only used for calorie and pace estimates. Optional."),
            ft.Container(height=Space.SM),
            grid,
            ft.Container(height=Space.XS),
            self._privacy(),
        ], spacing=Space.SM, horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            scroll=ft.ScrollMode.AUTO)
        return stage, self._footer(self.sex is not None)

    # ------------------------------------------------------------------ 7 time + reminders
    def _step_time(self) -> tuple[ft.Control, list[ft.Control]]:
        a = self.answers
        budget: dict[int, ft.Container] = {}
        times: dict[str, ft.Container] = {}

        def pick_budget(m: int, card: ft.Container) -> None:
            a.minutes = m
            for k, c in budget.items():
                self._paint_option(c, k == m)
            ui.refresh(*budget.values())
            self._feedback(card, True)
            self._set_ready(True)

        def pick_time(t: str, card: ft.Container) -> None:
            a.day_time = t
            for k, c in times.items():
                self._paint_option(c, k == t)
            ui.refresh(*times.values())
            self._feedback(card, True)
            self._remind_sub.value = self._remind_text()
            ui.refresh(self._remind_sub)

        for m in ob.TIME_BUDGETS:
            title, mins = BUDGET_TEXT[m]
            card = self._option(mins, sub=title, on=a.minutes == m, height=64, center=True,
                                on_tap=lambda c, m=m: pick_budget(m, c))
            card.col = 6
            budget[m] = card
        for t, (label, _hm) in ob.DAY_TIMES.items():
            card = self._option(label, icon=DAY_ICONS[t], on=a.day_time == t, height=56,
                                on_tap=lambda c, t=t: pick_time(t, c), show_mark=False)
            card.col = 6
            times[t] = card

        self._remind_sub = ft.Text(self._remind_text(), size=Type.CAPTION, color=C.TEXT_DIM)
        self._remind_switch = ft.Switch(value=a.reminders == "on", active_color=C.PRIMARY,
                                        on_change=self._toggle_remind)
        remind = common.card(ft.Row([
            ft.Icon(ft.Icons.NOTIFICATIONS_ACTIVE_OUTLINED, color=C.PRIMARY),
            ft.Column([ft.Text("Gentle daily nudge", size=Type.BODY,
                               weight=ft.FontWeight.BOLD, color=C.TEXT),
                       self._remind_sub], spacing=2, tight=True, expand=True),
            self._remind_switch,
        ], spacing=Space.MD, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=Space.MD)
        stage = ft.Column([
            *self._title("How much time can you give each day?",
                         "Be kind to future you. Small and steady wins."),
            ft.ResponsiveRow(list(budget.values()), spacing=Space.SM, run_spacing=Space.SM),
            ft.Container(height=Space.XS),
            ft.Text("When do you have the most energy?", size=Type.TITLE,
                    weight=ft.FontWeight.BOLD, color=C.TEXT, text_align=ft.TextAlign.CENTER),
            ft.ResponsiveRow(list(times.values()), spacing=Space.SM, run_spacing=Space.SM),
            remind,
        ], spacing=Space.SM, horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            scroll=ft.ScrollMode.AUTO)
        return stage, self._footer(bool(a.minutes))

    def _remind_text(self) -> str:
        at = ob.reminder_time(self.answers.day_time) or self.app.game.profile.reminders.daily_time
        if self.answers.reminders == "on":
            return f"On · around {at}. Change it anytime in Settings."
        return f"Off until you say so · it would come around {at}."

    async def _toggle_remind(self, e: Any) -> None:
        a, app = self.answers, self.app
        if not e.control.value:
            a.reminders = "off"
        elif notify.available():
            ok = await common.confirm(
                app.page, "A gentle daily nudge?",
                "Luma can remind you once a day while a quest is open, plus bills and your "
                "focus timer. Your phone will ask once if Life of Legends may send "
                "notifications.", "Continue")
            granted = ok and await notify.ensure_permission()
            if not granted:
                if ok:
                    app.toast("Notifications are off. You can allow them in phone settings.",
                              ft.Icons.NOTIFICATIONS_OFF)
                self._remind_switch.value = False
                a.reminders = "off"
            else:
                a.reminders = "on"
        else:
            a.reminders = "on"
            app.toast("Saved. Reminders ring on the phone app.", ft.Icons.PHONE_ANDROID)
        if a.reminders == "on":
            sfx.play("granted", 0.6)
        await ui.buzz("select")
        self._remind_sub.value = self._remind_text()
        ui.refresh(self._remind_switch, self._remind_sub)

    # ------------------------------------------------------------------ 8 theme
    def _step_theme(self) -> tuple[ft.Control, list[ft.Control]]:
        g = self.app.game
        tiles: list[ft.Control] = []
        for t in g.themes():
            if t.id not in th.THEMES or t.id not in g.profile.owned_themes:
                continue
            pal = th.THEMES[t.id]
            on = t.id == g.profile.theme_id
            preview = ft.Container(
                ft.Stack([
                    ft.Container(width=46, height=46, border_radius=23, left=18, top=14,
                                 bgcolor=ft.Colors.with_opacity(0.85, pal.primary),
                                 shadow=ft.BoxShadow(blur_radius=26, color=pal.primary)),
                    ft.Container(width=14, height=14, border_radius=7, left=86, top=40,
                                 bgcolor=pal.accent),
                    ft.Container(width=10, height=10, border_radius=5, left=104, top=18,
                                 bgcolor=pal.success),
                ]),
                height=78, border_radius=Radius.SM,
                gradient=ft.LinearGradient(begin=ft.Alignment.TOP_LEFT,
                                           end=ft.Alignment.BOTTOM_RIGHT,
                                           colors=[pal.surface_hi, pal.bg]),
            )
            tile = ft.Container(
                ft.Column([
                    preview,
                    ft.Row([ft.Text(pal.name, size=Type.BODY, weight=ft.FontWeight.BOLD,
                                    color=C.TEXT, expand=True),
                            ft.Icon(ft.Icons.CHECK_CIRCLE if on else
                                    ft.Icons.CIRCLE_OUTLINED, size=20,
                                    color=pal.primary if on else C.a(C.TEXT, 0.3))]),
                ], spacing=Space.SM, tight=True),
                col=6, padding=Space.SM, border_radius=Radius.MD,
                bgcolor=C.a(pal.primary, 0.12) if on else C.a(C.SURFACE_HI, 0.62),
                border=ft.Border.all(2 if on else 1, pal.primary if on else
                                     C.a(C.TEXT, 0.08)),
                shadow=ft.BoxShadow(blur_radius=22, color=ft.Colors.with_opacity(
                    0.35, pal.primary)) if on else None,
                on_click=lambda e, tid=t.id: self._pick_theme(tid), scale=1,
                animate_scale=Motion.anim(Motion.POP_MS, Motion.BACK),
            )
            tiles.append(tile)
        stage = ft.Column([
            *self._title("Pick your mind-space", "Each one recolors the whole app. "
                         "More can be unlocked with coins later."),
            ft.Container(height=Space.XS),
            ft.ResponsiveRow(tiles, spacing=Space.SM, run_spacing=Space.SM),
        ], spacing=Space.SM, horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            scroll=ft.ScrollMode.AUTO)
        return stage, self._footer(True)

    def _pick_theme(self, theme_id: str) -> None:
        g, app = self.app.game, self.app
        if theme_id == g.profile.theme_id or not g.set_theme(theme_id):
            app.page.run_task(ui.buzz, "select")
            return
        sfx.play("holo_flicker", 0.6)
        app.page.run_task(ui.buzz, "select")
        th.apply_theme(app.page, theme_id, update=False)
        self.bgcolor = C.BG
        self._render()
        ui.refresh(self)
        app.space.pulse(th.current().primary, 0.8)

    # ------------------------------------------------------------------ 9 analysis + plan
    def _step_plan(self) -> tuple[ft.Control, list[ft.Control]]:
        self._reveal_items: list[ft.Control] = []
        name = self.name or DEFAULT_NAME
        head = ft.Column(self._title(f"{name}, here's your legend",
                                     "Built from your answers. Tweak anything later.",
                                     eyebrow="Personal plan"),
                         spacing=Space.XS, tight=True,
                         horizontal_alignment=ft.CrossAxisAlignment.CENTER)
        self._plan_body = ft.Column([], spacing=Space.MD, tight=True,
                                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
        if self.plan is not None:
            self._fill_plan()
        stage = ft.Column([head, self._plan_body], spacing=Space.MD,
                          horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                          scroll=ft.ScrollMode.AUTO)
        self._go = common.primary_button("Begin your legend", self._finish,
                                         icon=ft.Icons.AUTO_AWESOME)
        ready = self._revealed
        self._go.disabled, self._go.opacity = not ready, 1 if ready else 0
        self._go.animate_opacity = Motion.anim(Motion.FADE_MS + 150)
        self._go.height = 56
        self._go.scale = 1
        self._go.animate_scale = Motion.anim(Motion.POP_MS, Motion.BACK)
        return stage, [self._go]

    def _eyebrow(self, text: str, color: str | None = None) -> ft.Text:
        return ft.Text(th.label(text), size=Type.CAPTION, weight=ft.FontWeight.BOLD,
                       color=color or C.TEXT_DIM,
                       style=ft.TextStyle(letter_spacing=th.label_spacing()))

    def _hidden(self, ctrl: ft.Control) -> ft.Control:
        """Wrap for the staggered reveal (already shown once revealed)."""
        box = ft.Container(ctrl, opacity=1 if self._revealed else 0,
                           offset=ft.Offset(0, 0) if self._revealed else ft.Offset(0, 0.25),
                           animate_opacity=Motion.anim(420),
                           animate_offset=Motion.anim(420, Motion.EASE_CUBIC))
        self._reveal_items.append(box)
        return box

    def _fill_plan(self) -> None:
        plan = self.plan
        assert plan is not None
        cards: list[ft.Control] = []
        for i, pid in enumerate(plan.paths):
            pc = th.path_color(pid)
            cards.append(ft.Container(ambient.glass(ft.Column([
                ui.path_avatar(th.path_icon(pid), pc, 52),
                ft.Text(th.path_name(pid), size=Type.BODY, weight=ft.FontWeight.W_900,
                        color=C.TEXT),
                ft.Text("Main Path" if i == 0 else "Also for you", size=Type.CAPTION,
                        color=pc if i == 0 else C.TEXT_DIM),
            ], spacing=Space.XS, tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                radius=Radius.MD, padding=Space.MD, tint=pc), expand=1))
        paths = ft.Column([self._eyebrow("Your Paths"),
                           ft.Row(cards, spacing=Space.SM)], spacing=Space.SM, tight=True)

        rows: list[ft.Control] = []
        for q in plan.quests:
            pc = th.path_color(q.path_id)
            rows.append(ft.Container(ft.Row([
                ft.Container(width=4, height=40, border_radius=2, bgcolor=pc),
                ui.path_avatar(th.path_icon(q.path_id), pc, 34),
                ft.Column([ft.Text(q.title, size=Type.LABEL + 1, weight=ft.FontWeight.BOLD,
                                   color=C.TEXT, max_lines=2,
                                   overflow=ft.TextOverflow.ELLIPSIS),
                           ft.Text(f"{th.path_name(q.path_id)} · about {q.minutes} min",
                                   size=Type.CAPTION, color=C.TEXT_DIM)],
                          spacing=0, tight=True, expand=True),
                ui.xp_chip(self._xp(q.difficulty)),
            ], spacing=Space.SM, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                padding=ft.Padding.symmetric(vertical=Space.XS)))
        quests = common.card(ft.Column([self._eyebrow("Starter quests · added to Today"),
                                        *rows], spacing=Space.XS, tight=True),
                             padding=Space.MD)

        items: list[ft.Control] = [paths, quests]
        side = self._side_card()
        if side is not None:
            items.append(side)
        note = common.card(ft.Row([
            ft.Icon(ft.Icons.AUTO_AWESOME, color=C.PRIMARY, size=20),
            ft.Column([self._eyebrow("Luma", C.PRIMARY),
                       *[ft.Text(line, size=Type.LABEL + 1, color=C.TEXT)
                         for line in plan.lines]], spacing=Space.XS, tight=True,
                      expand=True),
        ], spacing=Space.MD, vertical_alignment=ft.CrossAxisAlignment.START),
            padding=Space.MD, tint=th.current().primary)
        items.append(note)
        self._plan_body.controls = [self._hidden(c) for c in items]

    @staticmethod
    def _xp(difficulty: int) -> int:
        from lol.core.game import XP_BY_DIFFICULTY

        return XP_BY_DIFFICULTY.get(difficulty, 0)

    def _side_card(self) -> ft.Control | None:
        plan = self.plan
        if plan is None or not plan.paths:
            return None
        c = ob.starter_chain(self.app.game, plan.paths[0])
        if c is None:
            return None
        pc = th.path_color(c.path_id)
        sw = ft.Switch(value=self.start_starter, active_color=pc,
                       on_change=lambda e: setattr(self, "start_starter", e.control.value))
        return common.card(ft.Column([
            self._eyebrow("First side quest", pc),
            ft.Row([ft.Column([ft.Text(c.skill_name, size=Type.TITLE,
                                       weight=ft.FontWeight.BOLD, color=C.TEXT),
                               common.hint(f"{c.blurb} {len(c.steps)} steps.")],
                              spacing=2, tight=True, expand=True), sw],
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
        ], spacing=Space.XS, tight=True), padding=Space.MD, tint=pc)

    async def _analyze(self) -> None:
        if self._revealed:
            return
        self._back.disabled = True
        ui.refresh(self._back)
        snapshot = ob.validate(_copy(self.answers))
        self.plan = await ui.lumen_analyze(self.app.page, ANALYSIS,
                                           lambda: ob.build_plan(snapshot), seconds=2.4)
        if self.kind != "plan":
            return
        self._fill_plan()
        ui.refresh(self._plan_body)
        await asyncio.sleep(0.05)
        top = th.path_color(self.plan.paths[0]) if self.plan.paths else C.PRIMARY
        sfx.play("objective_new", 0.8)
        self.app.space.pulse(top, 1.0)
        self.app.page.run_task(self.app.fx_burst.burst, None, None, color=top, count=30)
        await ui.buzz("medium")
        for box in self._reveal_items:
            box.opacity, box.offset = 1, ft.Offset(0, 0)
            ui.refresh(box)
            await asyncio.sleep(0.14)
        self._revealed = True
        self._back.disabled = False
        self._go.disabled, self._go.opacity = False, 1
        ui.refresh(self._go, self._back)
        await asyncio.sleep(0.3)
        await ui.pop(self._go, 1.05)

    async def _finish(self, _: Any = None) -> None:
        if self._busy or not self._revealed:
            return
        self._busy = True
        app, g, today = self.app, self.app.game, self.app.today()
        await ui.buzz("heavy")
        await ui.pop(self._go, 1.06)
        g.finish_onboarding(self.name or g.profile.name or DEFAULT_NAME, self.avatar_id)
        if self.sex is not None:
            g.set_body(sex=self.sex)
        plan, _added = ob.apply(g, self.answers, today, first_run=not self.redo)
        started = False
        starter = ob.starter_chain(g, plan.paths[0]) if plan.paths else None
        if self.start_starter and starter is not None and g.can_start(starter.id):
            g.start_side_quest(starter.id, today)
            started = True
        app.save()
        self.opacity = 0
        ui.refresh(self)
        await asyncio.sleep((Motion.FADE_MS + 100) / 1000)
        await ui.call(self.on_done, started)
