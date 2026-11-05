"""More -> Energy: a quick low / okay / high check-in with an optional note, and the history.

A check-in only re-sorts Today's quests (Game.suggest_order: low -> easiest first, high ->
hardest first). It never hides or blocks anything, gives no XP, and can be skipped or turned
off in Settings. Today shows the one-tap chip row (`chip_row`)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any

import flet as ft

from lol.core.models import ENERGY_LEVELS
from lol.ui import components as ui
from lol.ui import sfx
from lol.ui.screens import common
from lol.ui.theme import C, Motion, Radius, Size, Space, Type

if TYPE_CHECKING:
    from lol.ui.app import App

LEVELS = {
    # level: (label, icon, color, what it does on Today)
    "low": ("Low", ft.Icons.BATTERY_2_BAR, "#7FB2FF", "Easiest quests first today."),
    "okay": ("Okay", ft.Icons.BATTERY_5_BAR, "#5EEAB0", "Your usual order."),
    "high": ("High", ft.Icons.BATTERY_FULL, "#FFB347", "Bigger quests first today."),
}


def check_in(app: App, level: str, note: str = "", on_done: Any = None) -> None:
    now = datetime.now()
    app.game.check_in(level, app.today(), time=f"{now:%H:%M}", note=note)
    app.save()
    sfx.play("low_energy" if level == "low" else "toggle")
    label, icon, _color, effect = LEVELS[level]
    app.toast(f"Energy: {label}. {effect}", icon)
    if on_done:
        on_done()


def level_chip(level: str, *, selected: bool = False, on_click: Any = None,
               height: int = Size.TAP) -> ft.Container:
    label, icon, color, _ = LEVELS[level]
    chip = ft.Container(
        ft.Row([ft.Icon(icon, size=18, color=color),
                ft.Text(label, size=Type.LABEL, weight=ft.FontWeight.BOLD,
                        color=color if selected else C.TEXT)],
               spacing=4, tight=True, alignment=ft.MainAxisAlignment.CENTER),
        height=height, expand=True, border_radius=Radius.PILL, alignment=ft.Alignment.CENTER,
        bgcolor=C.a(color, 0.22 if selected else 0.08),
        border=ft.Border.all(1.5 if selected else 1, C.a(color, 0.8 if selected else 0.35)),
        scale=1, animate_scale=Motion.anim(Motion.POP_MS, Motion.BACK))

    async def tap(_: Any) -> None:
        await ui.pop(chip, 1.08)
        if on_click:
            on_click(level)

    chip.on_click = tap
    return chip


def chip_row(app: App, on_done: Any, on_skip: Any) -> ft.Control:
    """Today: 'How's your energy?' with three one-tap chips (skippable), or today's level."""
    current = app.game.energy_today(app.today())
    if current is not None:
        label, icon, color, effect = LEVELS[current.level]
        return common.card(ft.Row([
            ft.Icon(icon, color=color, size=20),
            ft.Column([ft.Text(f"Energy: {label}", size=Type.BODY, weight=ft.FontWeight.W_700,
                               color=C.TEXT),
                       common.hint(effect + " Nothing is hidden.")],
                      spacing=0, expand=True, tight=True),
            ft.TextButton("Change", height=40, on_click=lambda e: app.open_sub("energy")),
        ], spacing=Space.SM, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.Padding.symmetric(horizontal=Space.MD, vertical=Space.XS))
    chips = [level_chip(lv, on_click=lambda v: check_in(app, v, on_done=on_done), height=44)
             for lv in ENERGY_LEVELS]
    return common.card(ft.Column([
        ft.Row([ft.Text("How's your energy?", size=Type.BODY, weight=ft.FontWeight.W_700,
                        color=C.TEXT, expand=True),
                ft.IconButton(ft.Icons.CLOSE, icon_size=18, icon_color=C.TEXT_DIM, width=40,
                              height=40, tooltip="Skip for today",
                              on_click=lambda e: (sfx.play("tap"), on_skip()))],
               vertical_alignment=ft.CrossAxisAlignment.CENTER),
        ft.Row(chips, spacing=Space.SM),
    ], spacing=Space.XS, tight=True), padding=ft.Padding.only(left=Space.MD, right=Space.XS,
                                                             top=Space.XS, bottom=Space.MD))


class EnergyScreen:
    title = "Energy"

    def __init__(self, app: App) -> None:
        self.app = app
        self.list = common.screen_list()
        self.view = ft.Container(self.list, expand=True, key="energy")
        self.picked: str | None = None

    def _refresh(self) -> None:
        self.render()
        ui.refresh(self.list)

    def restyle(self) -> None:
        self._refresh()

    def render(self) -> None:
        g, today = self.app.game, self.app.today()
        current = g.energy_today(today)
        note = common.text_field("Note (optional)")
        chips_row = ft.Row(spacing=Space.SM)

        def paint() -> None:
            chips_row.controls = [level_chip(lv, selected=lv == self.picked, on_click=pick)
                                  for lv in ENERGY_LEVELS]

        def pick(level: str) -> None:
            self.picked = level
            paint()
            ui.refresh(chips_row)

        def save(_: Any = None) -> None:
            if self.picked is None:
                self.app.error("Pick low, okay or high first")
                return
            level, self.picked = self.picked, None
            check_in(self.app, level, (note.value or "").strip(), self._refresh)

        paint()
        status = (f"Today: {LEVELS[current.level][0]}"
                  f"{' at ' + current.time if current.time else ''}. "
                  f"{LEVELS[current.level][3]}" if current else "No check-in today yet.")
        items: list[ft.Control] = [
            common.card(ft.Column([
                ft.Text("How's your energy right now?", size=Type.TITLE,
                        weight=ft.FontWeight.BOLD, color=C.TEXT),
                common.hint(status),
                chips_row, note,
                ft.Row([common.primary_button("Check in", save, icon=ft.Icons.BOLT)]),
                common.hint("It only sorts Today's list (never hides a quest). Check in as "
                            "often as you like, or skip it."),
            ], spacing=Space.MD, tight=True)),
            common.section("Last 30 days"),
        ]
        rows = g.energy_checkins(today - timedelta(days=29), today)
        if not rows:
            items.append(common.empty_card("No check-ins yet",
                                           "Tap a level when you feel like it.",
                                           ft.Icons.BOLT))
        for c in rows:
            label, icon, color, _ = LEVELS.get(c.level, LEVELS["okay"])
            d = date.fromisoformat(c.day)
            when = "Today" if d == today else common.short_date(d)
            items.append(common.card(ft.Row([
                ft.Icon(icon, color=color, size=22),
                ft.Column([ft.Text(f"{label} · {when}{' ' + c.time if c.time else ''}",
                                   size=Type.BODY, weight=ft.FontWeight.W_600, color=C.TEXT),
                           *([common.hint(c.note)] if c.note else [])],
                          spacing=0, expand=True, tight=True),
                ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_color=C.TEXT_DIM, icon_size=20,
                              width=Size.TAP, height=Size.TAP, tooltip="Delete",
                              on_click=lambda e, cid=c.id: self._delete(cid)),
            ], spacing=Space.MD, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                padding=ft.Padding.symmetric(horizontal=Space.MD, vertical=Space.XS)))
        self.list.controls = items

    def _delete(self, checkin_id: str) -> None:
        self.app.game.delete_checkin(checkin_id)
        self.app.save()
        sfx.play("tap")
        self.app.toast("Check-in deleted", ft.Icons.DELETE_OUTLINE)
        self._refresh()
