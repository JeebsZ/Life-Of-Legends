"""More -> Logbook: quick workout / sleep / note logs, newest first, grouped by day."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any

import flet as ft

from lol.core.models import LogEntry
from lol.ui import components as ui
from lol.ui import sfx
from lol.ui.screens import common
from lol.ui.theme import C, Radius, Size, Space, Type

if TYPE_CHECKING:
    from lol.ui.app import App

LOG_KINDS = {
    # kind: (label, icon, text hint)
    "workout": ("Workout", ft.Icons.FITNESS_CENTER, "What did you do? (e.g. 3 km walk)"),
    "sleep": ("Sleep", ft.Icons.BEDTIME, "How did you sleep?"),
    "note": ("Note", ft.Icons.EDIT_NOTE, "Anything on your mind"),
}
RECENT_LOGS = 40


class LogbookScreen:
    title = "Logbook"

    def __init__(self, app: App) -> None:
        self.app = app
        self.list = common.screen_list()
        self.view = ft.Container(self.list, expand=True, key="logbook")

    def render(self) -> None:
        g = self.app.game
        entries = g.logs()[:RECENT_LOGS]
        add_row = ft.Row([
            ft.Container(
                ft.Row([ft.Icon(icon, size=18, color=C.PRIMARY),
                        ft.Text(label, size=Type.LABEL, weight=ft.FontWeight.BOLD,
                                color=C.TEXT)], spacing=Space.XS, tight=True,
                       alignment=ft.MainAxisAlignment.CENTER),
                height=Size.TAP, expand=True, border_radius=Radius.PILL,
                bgcolor=C.a(C.PRIMARY, 0.12), alignment=ft.Alignment.CENTER, ink=True,
                on_click=lambda e, k=kind: self.open_log(k))
            for kind, (label, icon, _hint) in LOG_KINDS.items()
        ], spacing=Space.SM)
        items: list[ft.Control] = [ui.SectionHeader("Logbook", count=len(g.logs())), add_row]
        if not entries:
            items.append(common.hint("Log a workout, how you slept, or a quick note. "
                                     "Just for you."))
            self.list.controls = items
            return
        today = self.app.today()
        last_day = None
        rows: list[ft.Control] = []
        for e in entries:
            if e.day != last_day:
                last_day = e.day
                d = date.fromisoformat(e.day)
                label = "Today" if d == today else (
                    "Yesterday" if (today - d).days == 1 else f"{d:%a} {common.short_date(d)}")
                rows.append(ft.Text(label, size=Type.CAPTION, weight=ft.FontWeight.BOLD,
                                    color=C.TEXT_DIM))
            rows.append(log_row(e))
        items.append(common.card(ft.Column(rows, spacing=Space.SM, tight=True),
                                 padding=Space.MD))
        self.list.controls = items

    def restyle(self) -> None:
        self.render()
        ui.refresh(self.list)

    def open_log(self, kind: str) -> None:
        app = self.app
        sfx.play("tap")
        label, _icon, hint_text = LOG_KINDS[kind]
        text = common.text_field(hint_text, autofocus=True)
        minutes = common.text_field("Minutes (optional)", number=True)
        if kind == "sleep":
            minutes.label = "Minutes slept (optional, e.g. 420)"

        def add(_: Any = None) -> None:
            raw = (minutes.value or "").strip()
            mins: int | None = None
            if raw:
                try:
                    mins = int(raw)
                except ValueError:
                    sfx.play("error_soft")
                    minutes.error_text = "Whole minutes, like 30"
                    minutes.update()
                    return
            body = (text.value or "").strip()
            if not body and mins is None:
                sfx.play("error_soft")
                text.error_text = "Add a few words or the minutes"
                text.update()
                return
            app.game.add_log(kind, body, mins, today=app.today())
            app.save()
            common.close(sheet)
            self.render()
            ui.refresh(self.list)
            app.toast(f"{label} logged. Nice!", ft.Icons.BOOK)

        text.on_submit = add
        body: list[ft.Control] = [text]
        if kind != "note":
            body.append(minutes)
        body.append(ft.Row([common.primary_button(f"Log {label.lower()}", add,
                                                  icon=ft.Icons.CHECK)]))
        sheet = common.open_sheet(app.page, f"Log {label.lower()}", body)


def log_row(e: LogEntry) -> ft.Control:
    label, icon, _ = LOG_KINDS.get(e.kind, LOG_KINDS["note"])
    bits = [x for x in (e.text, f"{e.minutes} min" if e.minutes else "") if x]
    return ft.Row([
        ui.path_avatar(icon, C.PRIMARY, 32),
        ft.Column([
            ft.Text(label, size=Type.LABEL, weight=ft.FontWeight.BOLD, color=C.TEXT),
            ft.Text(" · ".join(bits) or "Logged", size=Type.LABEL, color=C.TEXT_DIM,
                    max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
        ], spacing=0, expand=True, tight=True),
    ], spacing=Space.MD, vertical_alignment=ft.CrossAxisAlignment.CENTER)
