"""More -> Insights: plain trends over 7 / 30 / 90 days from Game.insights(), each with a
"Show the data" expander (a small bar chart + the numbers behind the sentence).

Descriptive only: no claims that one thing causes another and no health advice."""

from __future__ import annotations

import time
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

import flet as ft

from lol.core.models import Insight
from lol.core.premium import PREMIUM_NAME
from lol.ui import components as ui
from lol.ui import sfx
from lol.ui.screens import common
from lol.ui.theme import C, Size, Space, Type

if TYPE_CHECKING:
    from lol.ui.app import App

RANGES = [("7", "7 days"), ("30", "30 days"), ("90", "90 days")]
# Luma's staged analysis when Insights opens (switching the range stays instant)
INSIGHT_STAGES = ("SCANNING LOGS…", "FINDING TRENDS…", "INSIGHTS READY")
KIND = {
    # kind: (icon, color, unit for the data rows)
    "quests_by_path": (ft.Icons.FLAG, "#4FE3F0", "done"),
    "workouts_per_week": (ft.Icons.FITNESS_CENTER, "#FF6F91", "sessions"),
    "sleep": (ft.Icons.NIGHTLIGHT, "#A78BFA", "h"),
    "water": (ft.Icons.WATER_DROP, "#5EC8F2", "ml"),
}


def _short(label: str) -> str:
    """Chart label: ISO dates -> day of month; long names -> 3 letters."""
    try:
        return str(date.fromisoformat(label).day)
    except ValueError:
        return label if len(label) <= 6 else label[:3]


def _num(v: float, unit: str) -> str:
    if unit == "h":
        return f"{v:.1f} h"
    return f"{v:,.0f} {unit}" if unit != "done" else f"{v:,.0f}"


class InsightsScreen:
    title = "Insights"

    def __init__(self, app: App) -> None:
        self.app = app
        self._analyzed = -1e9  # monotonic time of the last staged scan
        self.days = 7
        self.open: set[str] = set()
        self.list = common.screen_list()
        self.view = ft.Container(self.list, expand=True, key="insights")

    def _refresh(self) -> None:
        self.render()
        ui.refresh(self.list)

    def on_enter(self) -> None:
        if time.monotonic() - self._analyzed < 45:  # back from another tab: no re-scan
            return
        self._analyzed = time.monotonic()
        self.app.page.run_task(ui.lumen_analyze, self.app.page, INSIGHT_STAGES, None,
                               seconds=1.8)

    def restyle(self) -> None:
        self._refresh()

    def _set_range(self, v: str) -> None:
        app = self.app
        cutoff = app.game.history_cutoff("insights", app.today())
        if cutoff is not None and int(v) > (app.today() - cutoff).days + 1:
            sfx.play("error_soft")
            app.offer_premium("limit")
            app.toast(f"30 and 90 days come with {PREMIUM_NAME}. The last 7 days stay free.",
                      ft.Icons.WORKSPACE_PREMIUM)
            self._refresh()  # the segment snaps back
            return
        sfx.play("toggle")
        self.days = int(v)
        self._refresh()

    def render(self) -> None:
        today = self.app.today()
        if self.app.game.history_cutoff("insights", today) is not None:
            self.days = 7  # premium ended: back to the free window
        start = today - timedelta(days=self.days - 1)
        items: list[ft.Control] = [
            ft.Row([common.segmented(RANGES, str(self.days), on_change=self._set_range)],
                   alignment=ft.MainAxisAlignment.CENTER),
            common.hint("Plain summaries of what you logged. They describe, they don't "
                        "explain - no advice here."),
        ]
        items += [self._card(i) for i in self.app.game.insights(start, today)]
        self.list.controls = items

    def _card(self, ins: Insight) -> ft.Control:
        icon, color, unit = KIND.get(ins.kind, (ft.Icons.INSIGHTS, C.PRIMARY, ""))
        shown = ins.kind in self.open
        data = ins.data
        # long ranges: chart up to ~16 bars (most recent), the table lists everything
        chart_rows = [(_short(lb), v, "" if len(data) > 10 else _num(v, unit).split(" ")[0])
                      for lb, v in data[-16:]]
        table = ft.Column([
            ft.Row([ft.Text(lb, size=Type.CAPTION, color=C.TEXT_DIM, expand=True),
                    ft.Text(_num(v, unit), size=Type.CAPTION, color=C.TEXT,
                            weight=ft.FontWeight.W_600)])
            for lb, v in data
        ], spacing=2, tight=True)
        detail = ft.Column([
            common.bar_chart(chart_rows, color=color, height=110, empty="No data in range."),
            ft.Divider(height=1, color=C.OUTLINE),
            table,
        ], spacing=Space.SM, tight=True, visible=shown)
        toggle = ft.TextButton("Hide the data" if shown else "Show the data",
                               icon=ft.Icons.EXPAND_LESS if shown else ft.Icons.EXPAND_MORE,
                               height=Size.TAP)

        def flip(_: Any) -> None:
            sfx.play("tap")
            self.open ^= {ins.kind}
            on = ins.kind in self.open
            detail.visible = on
            toggle.content = "Hide the data" if on else "Show the data"
            toggle.icon = ft.Icons.EXPAND_LESS if on else ft.Icons.EXPAND_MORE
            ui.refresh(detail, toggle)

        toggle.on_click = flip
        return common.card(ft.Column([
            ft.Row([ft.Icon(icon, color=color, size=22),
                    ft.Text(ins.title, size=Type.TITLE, weight=ft.FontWeight.BOLD,
                            color=C.TEXT)], spacing=Space.SM),
            ft.Text(ins.text, size=Type.BODY, color=C.TEXT),
            toggle, detail,
        ], spacing=Space.SM, tight=True), tint=color)
