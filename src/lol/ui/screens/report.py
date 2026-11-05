"""More -> Luma Report: the weekly review. Opening it plays Luma's staged analysis."""

from __future__ import annotations

import time
from datetime import date
from typing import TYPE_CHECKING

import flet as ft

from lol.ui import components as ui
from lol.ui import theme as th
from lol.ui import voice
from lol.ui.screens import common
from lol.ui.theme import C, Radius, Size, Space, Type

if TYPE_CHECKING:
    from lol.ui.app import App

# Luma's staged analysis as the report opens (hum, scan, staged text; tap to skip)
REPORT_STAGES = ("READING YOUR WEEK…", "WEIGHING PATHS…", "REPORT READY")


class ReportScreen:
    title = "Luma Report"

    def __init__(self, app: App) -> None:
        self.app = app
        self._analyzed = -1e9  # monotonic time of the last staged scan
        self.list = common.screen_list()
        self.view = ft.Container(self.list, expand=True, key="report")

    def on_enter(self) -> None:
        if time.monotonic() - self._analyzed < 45:  # back from another tab: no re-scan
            return
        self._analyzed = time.monotonic()
        self.app.page.run_task(ui.lumen_analyze, self.app.page, REPORT_STAGES, None,
                               seconds=2.2)

    def render(self) -> None:
        today = self.app.today()
        self.list.controls = [ui.SectionHeader(voice.say("report_title")), self._weekly(today),
                              *self._focus(today)]

    def restyle(self) -> None:
        self.render()
        ui.refresh(self.list)

    def _focus(self, today: date) -> list[ft.Control]:
        sessions = [s for s in self.app.game.focus_sessions()
                    if 0 <= (today - date.fromisoformat(s.day)).days < 7]
        if not sessions:
            return []
        mins = sum(s.minutes for s in sessions)
        return [ui.SectionHeader("Focus this week"), common.card(ft.Row([
            self._stat(str(len(sessions)), "sessions", C.PRIMARY),
            self._stat(f"{mins // 60}h {mins % 60}m" if mins >= 60 else f"{mins}m", "focused",
                       C.SUCCESS),
            self._stat(str(sum(s.xp for s in sessions)), "XP", C.ACCENT),
        ], spacing=Space.SM))]

    def _weekly(self, today: date) -> ft.Control:
        r = self.app.game.weekly_review(today)
        xp_by = r["xp_by_path"]
        top = max(xp_by.values()) if xp_by else 0
        stats = ft.Row([
            self._stat(str(r["done"]), "quests done", C.SUCCESS),
            self._stat(f"{r['xp_total']:,}", "XP earned", C.PRIMARY),
            self._stat(str(r["best_streak"]), "best streak", ui.FIRE),
        ], spacing=Space.SM)
        bars: list[ft.Control] = []
        for pid in th.PATH_IDS:
            xp = xp_by.get(pid, 0)
            bars.append(ft.Row([
                ft.Icon(th.path_icon(pid), color=th.path_color(pid), size=16),
                ft.Text(th.path_name(pid), size=Type.CAPTION, color=C.TEXT_DIM, width=58),
                ft.Container(ui.XpBar(xp / top if top else 0, height=Size.BAR_MINI,
                                      color=th.path_color(pid), show_level=False),
                             expand=True),
                ft.Text(str(xp), size=Type.CAPTION, color=C.TEXT, width=36,
                        text_align=ft.TextAlign.RIGHT),
            ], spacing=Space.SM, vertical_alignment=ft.CrossAxisAlignment.CENTER))
        lines: list[ft.Control] = []
        if r["best_streak"] and r["best_streak_quest"]:
            lines.append(common.hint(f"Longest streak: {r['best_streak_quest']} "
                                     f"({r['best_streak']} days)"))
        if r["skipped"]:
            lines.append(common.hint(f"{r['skipped']} daily check-ins open. "
                                     + voice.say("comeback")))
        elif r["done"]:
            lines.append(common.hint("Every daily kept this week. Lovely rhythm!"))
        else:
            lines.append(common.hint("A fresh week. One small quest is a great start."))
        if r["bills_paid"] or r["logs"]:
            bills = f"{r['bills_paid']} bill{'' if r['bills_paid'] == 1 else 's'} paid"
            logs = f"{r['logs']} log entr{'y' if r['logs'] == 1 else 'ies'}"
            lines.append(common.hint(f"{bills} · {logs}"))
        return common.card(ft.Column([
            common.hint(f"{common.short_date(date.fromisoformat(r['start']))} – "
                        f"{common.short_date(today)}"),
            stats, ft.Column(bars, spacing=Space.XS + 2, tight=True), *lines,
        ], spacing=Space.MD, tight=True))

    @staticmethod
    def _stat(value: str, label: str, color: str) -> ft.Control:
        return ft.Container(ft.Column([
            ft.Text(value, size=Type.HEADLINE, weight=ft.FontWeight.W_900, color=color),
            ft.Text(label, size=Type.CAPTION, color=C.TEXT_DIM),
        ], spacing=0, tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            expand=True, bgcolor=C.SURFACE_HI, border_radius=Radius.SM,
            padding=ft.Padding.symmetric(vertical=Space.SM), alignment=ft.Alignment.CENTER)
