"""The pre-run stretch sheet: "Stretch while a short ad plays" (free, opt-in ad) or a plain
stretch guide (premium, or anyone who taps "Stretch first"). Four gentle holds, each with a
tap-to-start timer. Run safety notes are always shown here, ad or not.

on_start(ad_result) runs when the user taps Start: ad_result is the AdCard result ("watched" /
"skipped") or None (no ad on this sheet, or the user started before it finished)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import flet as ft

from lol.core import stretch
from lol.core.premium import PREMIUM_NAME
from lol.ui import ads, sfx
from lol.ui import components as ui
from lol.ui.screens import common
from lol.ui.theme import C, Radius, Space, Type

if TYPE_CHECKING:
    from lol.ui.app import App

ACCENT = "#FF8A5B"


class StretchRow(ft.Container):
    """One stretch: tap to time it (switch legs at half time), check when done."""

    def __init__(self, page: ft.Page, s: stretch.Stretch, alive: Callable[[], bool]) -> None:
        self.page_ref, self.s, self.alive = page, s, alive
        self.running = False
        self.done = False
        self.ring = ft.ProgressRing(value=0, width=36, height=36, stroke_width=4,
                                    color=ACCENT, bgcolor=C.a(C.TEXT, 0.1))
        self.icon = ft.Icon(getattr(ft.Icons, s.icon.upper(), ft.Icons.ACCESSIBILITY_NEW),
                            size=18, color=ACCENT)
        self.time = ft.Text(f"{s.seconds} s" + (" each leg" if s.sides else ""),
                            size=Type.CAPTION, color=C.TEXT_DIM)
        super().__init__(
            ft.Row([
                ft.Stack([self.ring, ft.Container(self.icon, width=36, height=36,
                                                  alignment=ft.Alignment.CENTER)],
                         width=36, height=36),
                ft.Column([ft.Text(s.name, size=Type.BODY, weight=ft.FontWeight.W_700,
                                   color=C.TEXT),
                           common.hint(s.how), self.time], spacing=0, tight=True,
                          expand=True),
            ], spacing=Space.MD, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=Space.SM, border_radius=Radius.MD, bgcolor=C.SURFACE, ink=True,
            border=ft.Border.all(1, C.OUTLINE), on_click=self._tap, key=f"stretch:{s.id}")

    def _tap(self, _: Any = None) -> None:
        if self.running:
            return
        sfx.play("tap")
        self.running = True
        self.border = ft.Border.all(2, ACCENT)
        ui.refresh(self)
        self.page_ref.run_task(self._run)

    async def _run(self) -> None:
        s = self.s
        sides = 2 if s.sides else 1
        total = s.seconds * sides
        for t in range(total):
            if not self.alive():
                return
            left = s.seconds - (t % s.seconds)
            leg = "" if not s.sides else (" · left leg" if t < s.seconds else " · right leg")
            self.time.value = f"{left} s{leg}"
            self.ring.value = t / total
            ui.refresh(self.time, self.ring)
            if s.sides and t == s.seconds:
                sfx.play("notice")  # switch legs
            await asyncio.sleep(1)
        self.running, self.done = False, True
        self.ring.value = 1
        self.icon.icon, self.icon.color = ft.Icons.CHECK, C.SUCCESS
        self.time.value = "Done"
        self.border = ft.Border.all(1, C.a(C.SUCCESS, 0.6))
        sfx.play("toggle")
        ui.refresh(self)


def open_stretch_sheet(app: App, *, with_ad: bool, notes: list[str],
                       on_start: Callable[[str | None], Any]) -> None:
    state = {"open": True, "started": False}
    alive = lambda: state["open"]
    card: ads.AdCard | None = None
    mode_hint = common.hint("")
    start_btn = common.primary_button("Start run", lambda e: start(), icon=ft.Icons.PLAY_ARROW)

    def paint() -> None:
        res = card.result if card else None
        if card is None:
            mode_hint.value = "Full tracking: map, pace, splits, kcal and voice cues."
        elif res == "watched":
            mode_hint.value = "Full tracking unlocked: map, pace, splits, kcal and cues."
        elif res == "skipped":
            mode_hint.value = ("Basic tracking: steps (estimated) and time. Map, pace, "
                               "splits and kcal stay hidden.")
        else:
            mode_hint.value = ("Full tracking unlocks when the ad ends. Starting now uses "
                               "basic tracking (steps + time).")
        mode_hint.color = C.SUCCESS if res == "watched" or card is None else C.TEXT_DIM
        ui.refresh(mode_hint)

    def ad_done(_: str) -> None:
        paint()

    def start() -> None:
        if state["started"]:
            return
        state["started"] = True
        res = card.result if card else None
        close()
        on_start(res)

    def close() -> None:
        state["open"] = False
        if card is not None and card.result is None:
            card.result = "skipped"  # stops its timer silently
        common.close(sheet)

    def to_premium(_: Any = None) -> None:
        close()
        app.open_sub("premium")

    body: list[ft.Control] = []
    if with_ad:
        card = ads.AdCard(app.page, "pre_run_stretch", ad_done)
        body += [common.hint("Optional: watching unlocks full tracking for this run. Skip "
                             "any time and you still get steps and time."), card]
    body.append(common.hint("Tap a stretch to time it. " + stretch.SAFETY))
    body += [StretchRow(app.page, s, alive) for s in stretch.STRETCHES]
    if notes:
        body.append(common.card(ft.Column([
            ft.Row([ft.Icon(ft.Icons.HEALTH_AND_SAFETY, size=16, color=C.TEXT_DIM),
                    ft.Text(n, size=Type.CAPTION, color=C.TEXT_DIM, expand=True)],
                   spacing=Space.SM, vertical_alignment=ft.CrossAxisAlignment.START)
            for n in notes], spacing=Space.XS, tight=True), padding=Space.SM))
    body += [mode_hint, ft.Row([start_btn])]
    if with_ad:
        body.append(ft.Row([ft.TextButton(f"Or {PREMIUM_NAME}: no ads, full tracking always",
                                          icon=ft.Icons.WORKSPACE_PREMIUM, on_click=to_premium,
                                          style=ft.ButtonStyle(color="#F5C66B"))],
                           alignment=ft.MainAxisAlignment.CENTER))
    def dismissed() -> None:  # swiped away: stop the timers, start nothing
        state["open"] = False
        if card is not None and card.result is None:
            card.result = "skipped"

    paint()
    sheet = common.open_sheet(app.page, "Stretch while a short ad plays" if with_ad
                              else "Stretch first", body, on_dismiss=dismissed)
    if card is not None:
        card.start()
