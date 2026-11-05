"""More -> Water: today's total and (optional) goal ring, quick-add buttons, a custom amount,
undo, the last 7 days and the water settings (goal, unit, quick amounts).

The goal is the player's own (there's no universal target). Reaching it gives a little Monk
XP once per day (Game.add_water). Today shows a compact version (`mini_card`)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

import flet as ft

from lol.core.game import oz_to_ml, water_in
from lol.ui import ambient, sfx
from lol.ui import components as ui
from lol.ui import theme as th
from lol.ui.screens import common
from lol.ui.theme import C, Radius, Size, Space, Type

if TYPE_CHECKING:
    from lol.ui.app import App

WATER = "#5EC8F2"  # water blue (same on every theme)


def fmt(ml: float, unit: str) -> str:
    v = water_in(ml, unit)
    return f"{v:,.0f} ml" if unit == "ml" else f"{v:,.1f} oz"


async def add(app: App, ml: float, at: tuple[float | None, float | None] | None = None,
              on_done: Any = None) -> None:
    """Add a drink with feedback; the first time today's goal is reached it's a reward beat."""
    g, today = app.game, app.today()
    try:
        before = g.water_today(today)["reached"]
        c = await app.award(
            lambda: g.add_water(ml, today),
            line=lambda c: f"Notice: Daily water goal reached. +{c.xp} XP to Monk Path.",
            at=at)
    except ValueError as exc:
        app.error(str(exc))
        return
    app.save()
    unit = g.profile.water.unit
    if not (c.xp or c.coins):
        sfx.play("tap")
        now = g.water_today(today)
        if now["reached"] and not before:
            app.juice(WATER, at)
            app.toast(f"Goal reached: {fmt(now['ml'], unit)} today", ft.Icons.WATER_DROP)
        else:
            app.toast(f"+{fmt(ml, unit)} · {fmt(now['ml'], unit)} today", ft.Icons.WATER_DROP)
    if on_done:
        on_done()


def undo(app: App, on_done: Any = None) -> None:
    g = app.game
    e = g.undo_water(app.today())
    if e is None:
        app.error("Nothing to undo today")
        return
    app.save()
    sfx.play("tap")
    app.toast(f"Removed {fmt(e.amount_ml, g.profile.water.unit)}. XP stays.", ft.Icons.UNDO)
    if on_done:
        on_done()


def quick_buttons(app: App, on_done: Any, limit: int = 6, *, expand: bool = False
                  ) -> list[ft.Control]:
    w = app.game.profile.water
    out: list[ft.Control] = []
    for ml in w.quick_amounts[:limit]:
        pos: dict[str, Any] = {}
        btn = ft.Container(
            ft.Row([ft.Icon(ft.Icons.WATER_DROP, size=16, color=WATER),
                    ft.Text(f"+{fmt(ml, w.unit)}", size=Type.LABEL, weight=ft.FontWeight.BOLD,
                            color=C.TEXT)], spacing=4, tight=True,
                   alignment=ft.MainAxisAlignment.CENTER),
            height=Size.TAP, border_radius=Radius.PILL, expand=expand,
            alignment=ft.Alignment.CENTER,
            padding=ft.Padding.symmetric(horizontal=Space.MD),
            bgcolor=C.a(WATER, 0.14),
            border=ft.Border.all(1, C.a(WATER, 0.45)), scale=1,
            animate_scale=th.Motion.anim(th.Motion.POP_MS, th.Motion.BACK))

        async def tap(_: Any, ml: int = ml, btn: ft.Container = btn,
                      pos: dict[str, Any] = pos) -> None:
            await ui.pop(btn, 1.08)
            await add(app, ml, pos.get("at"), on_done)

        btn.on_click = tap
        btn.on_tap_down = lambda e, pos=pos: pos.update(at=ambient.card_center(e))
        out.append(btn)
    return out


def mini_card(app: App, on_done: Any) -> ft.Control:
    """Today: a slim progress bar + two quick-add buttons + open the Water screen."""
    g = app.game
    t = g.water_today(app.today())
    unit = g.profile.water.unit
    label = (f"{fmt(t['ml'], unit)} of {fmt(t['goal_ml'], unit)}" if t["goal_ml"]
             else f"{fmt(t['ml'], unit)} today")
    bar = ft.ProgressBar(value=t["progress"] or 0, color=WATER, bgcolor=C.a(C.TEXT, 0.1),
                         height=6, border_radius=3, visible=t["goal_ml"] is not None)
    head = ft.Row([
        ft.Icon(ft.Icons.CHECK_CIRCLE if t["reached"] else ft.Icons.WATER_DROP,
                color=C.SUCCESS if t["reached"] else WATER, size=20),
        ft.Text("Water", size=Type.BODY, weight=ft.FontWeight.W_700, color=C.TEXT),
        ft.Text(label, size=Type.CAPTION, color=C.TEXT_DIM, expand=True,
                text_align=ft.TextAlign.RIGHT),
        ft.IconButton(ft.Icons.CHEVRON_RIGHT, icon_color=C.TEXT_DIM, width=40, height=40,
                      tooltip="Open Water", on_click=lambda e: app.open_sub("water")),
    ], spacing=Space.SM, vertical_alignment=ft.CrossAxisAlignment.CENTER)
    return common.card(ft.Column([
        head, bar, ft.Row(quick_buttons(app, on_done, limit=3, expand=True), spacing=Space.SM),
    ], spacing=Space.SM, tight=True), padding=Space.MD, tint=WATER)


class WaterScreen:
    title = "Water"

    def __init__(self, app: App) -> None:
        self.app = app
        self.list = common.screen_list()
        self.view = ft.Container(self.list, expand=True, key="water")

    def _refresh(self) -> None:
        self.render()
        ui.refresh(self.list)

    def restyle(self) -> None:
        self._refresh()

    def render(self) -> None:
        g, today = self.app.game, self.app.today()
        w = g.profile.water
        t = g.water_today(today)
        unit = w.unit
        if t["goal_ml"]:
            center = ft.Column([
                ft.Text(fmt(t["ml"], unit), size=Type.HEADLINE, weight=ft.FontWeight.W_900,
                        color=C.TEXT),
                common.hint(f"of {fmt(t['goal_ml'], unit)}"),
                ft.Icon(ft.Icons.CHECK_CIRCLE, color=C.SUCCESS, size=20,
                        visible=t["reached"]),
            ], spacing=0, tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
            ring: ft.Control = common.progress_ring(t["progress"] or 0, center,
                                                    color=C.SUCCESS if t["reached"] else WATER)
        else:
            ring = ft.Column([
                ft.Icon(ft.Icons.WATER_DROP, color=WATER, size=40),
                ft.Text(fmt(t["ml"], unit), size=Type.HEADLINE, weight=ft.FontWeight.W_900,
                        color=C.TEXT),
                common.hint("today · no daily goal set"),
            ], spacing=2, tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER)

        custom = common.text_field(f"Custom amount ({unit})", number=True)

        async def add_custom(_: Any = None) -> None:
            try:
                v = float((custom.value or "").replace(",", "").strip())
            except ValueError:
                v = 0
            if v <= 0:
                custom.error_text = "Enter an amount, like 300"
                sfx.play("error_soft")
                custom.update()
                return
            ml = v if unit == "ml" else oz_to_ml(v)
            await add(self.app, ml, None, self._refresh)

        custom.on_submit = add_custom
        entries = g.water_entries(today)
        btns = quick_buttons(self.app, self._refresh, expand=True)
        top = common.card(ft.Column([
            ft.Container(ring, alignment=ft.Alignment.CENTER, padding=Space.SM),
            *[ft.Row(btns[i:i + 3], spacing=Space.SM) for i in range(0, len(btns), 3)],
            ft.Row([ft.Container(custom, expand=True),
                    ft.IconButton(ft.Icons.ADD, icon_color=C.ON_PRIMARY, bgcolor=C.PRIMARY,
                                  width=Size.TAP, height=Size.TAP, tooltip="Add",
                                  on_click=add_custom)],
                   spacing=Space.SM, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Row([common.hint(f"{len(entries)} drink{'s' if len(entries) != 1 else ''} "
                                "today"),
                    ft.Container(expand=True),
                    ft.TextButton("Undo last", icon=ft.Icons.UNDO, height=Size.TAP,
                                  disabled=not entries,
                                  on_click=lambda e: undo(self.app, self._refresh))],
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
        ], spacing=Space.MD, tight=True), tint=WATER)

        hist = g.water_history(today - timedelta(days=6), today)
        rows = [(f"{date.fromisoformat(d):%a}"[:2], float(water_in(ml, unit)),
                 f"{water_in(ml, unit):,.0f}" if unit == "ml" else f"{water_in(ml, unit):.0f}")
                for d, ml, _ in hist]
        goal = water_in(w.daily_goal_ml, unit) if w.daily_goal_ml else None
        reached = sum(1 for *_, ok in hist if ok)
        hist_card = common.card(ft.Column([
            ft.Row([ft.Text("Last 7 days", size=Type.BODY, weight=ft.FontWeight.W_700,
                            color=C.TEXT, expand=True),
                    common.hint(f"goal met {reached}/7" if goal else unit)]),
            common.bar_chart(rows, color=WATER, goal=goal, empty="No water logged this week."),
        ], spacing=Space.SM, tight=True))

        self.list.controls = [top, common.section("History"), hist_card,
                              common.section("Settings"), self._settings()]

    def _settings(self) -> ft.Control:
        g, app = self.app.game, self.app
        w = g.profile.water
        unit = w.unit
        goal = common.text_field(f"Daily goal ({unit})", number=True)
        goal.value = (f"{water_in(w.daily_goal_ml, unit):g}" if w.daily_goal_ml else "")
        quick = common.text_field(f"Quick-add buttons ({unit}, comma separated)")
        quick.value = ", ".join(f"{water_in(a, unit):g}" for a in w.quick_amounts)

        def to_ml(v: float) -> float:
            return v if w.unit == "ml" else oz_to_ml(v)

        def save(_: Any = None) -> None:
            text = (goal.value or "").replace(",", "").strip()
            try:
                goal_ml = round(to_ml(float(text))) if text else None
                amounts = [round(to_ml(float(x))) for x in (quick.value or "").split(",")
                           if x.strip()]
                g.set_water_settings(daily_goal_ml=goal_ml, quick_amounts=amounts)
            except ValueError as exc:
                app.error(f"Couldn't save: {exc}")
                return
            app.save()
            sfx.play("toggle")
            app.toast("Water settings saved", ft.Icons.WATER_DROP)
            self._refresh()

        def set_unit(v: str) -> None:
            sfx.play("toggle")
            g.set_water_settings(unit=v)
            app.save()
            self._refresh()

        return common.card(ft.Column([
            common.hint("Your goal is yours to pick - leave it empty for no goal. Reaching it "
                        "gives a little Monk XP once a day."),
            goal, quick,
            ft.Row([common.hint("Unit"), ft.Container(expand=True),
                    common.segmented([("ml", "ml"), ("oz", "oz")], unit, on_change=set_unit)],
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Row([common.primary_button("Save", save, icon=ft.Icons.CHECK)]),
            ft.TextButton("Water reminders: Settings > Notifications",
                          icon=ft.Icons.NOTIFICATIONS, height=Size.TAP,
                          on_click=lambda e: app.more.open("settings")),
        ], spacing=Space.MD, tight=True))
