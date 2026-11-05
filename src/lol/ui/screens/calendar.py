"""More -> Calendar: month grid or week list of quests done, side-quest steps, logs, focus
sessions and bill dates (Game.calendar_entries), with filter chips. Blank days stay neutral:
no "missed" or broken-streak styling, ever. Tap a day for its entries."""

from __future__ import annotations

import calendar as cal
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

import flet as ft

from lol.core.game import add_months
from lol.core.models import Entry
from lol.ui import components as ui
from lol.ui import sfx
from lol.ui import theme as th
from lol.ui.screens import common, editors
from lol.ui.theme import C, Radius, Size, Space, Type

if TYPE_CHECKING:
    from lol.ui.app import App

BILL_DUE = "#FFB347"
# entry kind: (label, icon, fixed color or None = Path color)
KINDS: dict[str, tuple[str, ft.IconData, str | None]] = {
    "quest": ("Quest done", ft.Icons.TASK_ALT, None),
    "step": ("Side quest step", ft.Icons.ROUTE, None),
    "log": ("Log", ft.Icons.BOOK, "#F08CB4"),
    "focus": ("Focus", ft.Icons.TIMER, "#4FE3F0"),
    "bill_due": ("Bill due", ft.Icons.RECEIPT_LONG, BILL_DUE),
    "bill_paid": ("Bill paid", ft.Icons.PAID, "#5EEAB0"),
}
FILTERS = {  # chip -> entry kinds
    "quest": ("Quests", ft.Icons.TASK_ALT, "#7FB2FF", {"quest"}),
    "step": ("Steps", ft.Icons.ROUTE, "#A78BFA", {"step"}),
    "log": ("Logs", ft.Icons.BOOK, "#F08CB4", {"log"}),
    "focus": ("Focus", ft.Icons.TIMER, "#4FE3F0", {"focus"}),
    "bill": ("Bills", ft.Icons.RECEIPT_LONG, BILL_DUE, {"bill_due", "bill_paid"}),
}
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def entry_color(e: Entry) -> str:
    fixed = KINDS.get(e.kind, ("", None, None))[2]
    return fixed or (th.path_color(e.path_id) if e.path_id else C.PRIMARY)


class CalendarScreen:
    title = "Calendar"

    def __init__(self, app: App) -> None:
        self.app = app
        self.view_mode = "month"
        self.cursor = app.today()  # any day in the shown month / week
        self.filters: set[str] = set(FILTERS)
        self.list = common.screen_list()
        self.view = ft.Container(self.list, expand=True, key="calendar")

    def _kinds(self) -> set[str]:
        out: set[str] = set()
        for f in self.filters:
            out |= FILTERS[f][3]
        return out

    # ------------------------------------------------------------------ render
    def render(self) -> None:
        mode = common.segmented([("month", "Month"), ("week", "Week")], self.view_mode,
                                on_change=self._set_mode)
        chips = common.ToggleChips([(k, lbl, icon, col) for k, (lbl, icon, col, _)
                                    in FILTERS.items()], self.filters, self._set_filters)
        if self.view_mode == "month":
            first = self.cursor.replace(day=1)
            title = f"{first:%B} {first.year}"
        else:
            start = self.cursor - timedelta(days=self.cursor.weekday())
            end = start + timedelta(days=6)
            title = f"{common.short_date(start)} – {common.short_date(end)}"
        nav = ft.Row([
            ft.IconButton(ft.Icons.CHEVRON_LEFT, icon_color=C.TEXT, width=Size.TAP,
                          height=Size.TAP, tooltip="Previous", on_click=lambda e: self._shift(-1)),
            ft.Text(title, size=Type.TITLE, weight=ft.FontWeight.BOLD, color=C.TEXT,
                    expand=True, text_align=ft.TextAlign.CENTER),
            ft.IconButton(ft.Icons.CHEVRON_RIGHT, icon_color=C.TEXT, width=Size.TAP,
                          height=Size.TAP, tooltip="Next", on_click=lambda e: self._shift(1)),
            ft.TextButton("Today", on_click=common.with_sound(self._to_today), height=40),
        ], spacing=0, vertical_alignment=ft.CrossAxisAlignment.CENTER)
        items: list[ft.Control] = [ft.Row([mode], alignment=ft.MainAxisAlignment.CENTER),
                                   chips, nav]
        items.append(self._month() if self.view_mode == "month" else self._week())
        items.append(ft.Container(common.hint(
            "Days without entries stay plain: rest days count too. Tap a day for details."),
            alignment=ft.Alignment.CENTER, padding=Space.SM))
        self.list.controls = items

    def restyle(self) -> None:
        self.render()
        ui.refresh(self.list)

    def _refresh(self) -> None:
        self.render()
        ui.refresh(self.list)

    # ------------------------------------------------------------------ month
    def _month(self) -> ft.Control:
        today = self.app.today()
        first = self.cursor.replace(day=1)
        start = first - timedelta(days=first.weekday())
        days_in = cal.monthrange(first.year, first.month)[1]
        last = first.replace(day=days_in)
        end = last + timedelta(days=6 - last.weekday())
        entries = self.app.game.calendar_entries(start, end, self._kinds())
        header = ft.Row([ft.Container(ft.Text(w[0:2], size=Type.CAPTION, color=C.TEXT_DIM,
                                              weight=ft.FontWeight.BOLD),
                                      expand=True, alignment=ft.Alignment.CENTER)
                         for w in WEEKDAYS], spacing=2)
        weeks: list[ft.Control] = [header]
        d = start
        while d <= end:
            row = []
            for _ in range(7):
                row.append(self._cell(d, entries.get(d, []), d.month == first.month,
                                      d == today))
                d += timedelta(days=1)
            weeks.append(ft.Row(row, spacing=2))
        return common.card(ft.Column(weeks, spacing=2, tight=True), padding=Space.SM)

    def _cell(self, d: date, entries: list[Entry], in_month: bool, is_today: bool) -> ft.Control:
        kinds_seen: list[str] = []
        for e in entries:
            if e.kind not in kinds_seen and e.kind != "bill_due":
                kinds_seen.append(e.kind)
        due = any(e.kind == "bill_due" for e in entries)
        dots = [ft.Container(width=6, height=6, border_radius=3,
                             bgcolor=entry_color(next(e for e in entries if e.kind == k)))
                for k in kinds_seen[:4]]
        num = ft.Text(str(d.day), size=Type.LABEL,
                      weight=ft.FontWeight.BOLD if is_today else ft.FontWeight.W_500,
                      color=(C.PRIMARY if is_today else C.TEXT) if in_month
                      else C.a(C.TEXT, 0.3))
        marker = ft.Container(ft.Icon(ft.Icons.RECEIPT_LONG, size=10, color=BILL_DUE),
                              right=1, top=1, visible=due)
        count = len(entries)
        body = ft.Column([num, ft.Row(dots, spacing=2, alignment=ft.MainAxisAlignment.CENTER,
                                      tight=True)],
                         spacing=3, tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                         alignment=ft.MainAxisAlignment.CENTER)
        return ft.Container(
            ft.Stack([ft.Container(body, alignment=ft.Alignment.CENTER, expand=True), marker],
                     expand=True),
            expand=True, height=50, border_radius=Radius.SM,
            bgcolor=C.a(C.PRIMARY, 0.06) if count and in_month else None,
            border=ft.Border.all(1.4, C.PRIMARY) if is_today else None,
            on_click=lambda e, dd=d: self._open_day(dd), ink=True,
            opacity=1 if in_month else 0.7,
            tooltip=f"{count} entr{'y' if count == 1 else 'ies'}" if count else None)

    # ------------------------------------------------------------------ week
    def _week(self) -> ft.Control:
        today = self.app.today()
        start = self.cursor - timedelta(days=self.cursor.weekday())
        entries = self.app.game.calendar_entries(start, start + timedelta(days=6),
                                                 self._kinds())
        rows: list[ft.Control] = []
        for i in range(7):
            d = start + timedelta(days=i)
            day_entries = entries.get(d, [])
            head = ft.Row([
                ft.Text(f"{WEEKDAYS[i]} {common.short_date(d)}", size=Type.LABEL,
                        weight=ft.FontWeight.BOLD,
                        color=C.PRIMARY if d == today else C.TEXT),
                ft.Container(expand=True),
                common.hint(f"{len(day_entries)}" if day_entries else ""),
            ])
            body: list[ft.Control] = [head]
            body += [self._entry_row(e, compact=True) for e in day_entries[:6]]
            if len(day_entries) > 6:
                body.append(common.hint(f"+{len(day_entries) - 6} more"))
            rows.append(ft.Container(ft.Column(body, spacing=Space.XS, tight=True),
                                     bgcolor=C.SURFACE_HI if day_entries else C.SURFACE,
                                     border_radius=Radius.MD, padding=Space.MD,
                                     border=ft.Border.all(1.2, C.a(C.PRIMARY, 0.6))
                                     if d == today else None,
                                     on_click=lambda e, dd=d: self._open_day(dd), ink=True))
        return ft.Column(rows, spacing=Space.SM, tight=True)

    # ------------------------------------------------------------------ day sheet
    def _entry_row(self, e: Entry, *, compact: bool = False) -> ft.Control:
        label, icon, _ = KINDS.get(e.kind, ("", ft.Icons.CIRCLE, None))
        col = entry_color(e)
        texts: list[ft.Control] = [ft.Text(e.title, size=Type.LABEL if compact else Type.BODY,
                                           color=C.TEXT, max_lines=2,
                                           overflow=ft.TextOverflow.ELLIPSIS)]
        if not compact:
            texts.append(common.hint(label + (f" · {th.path_name(e.path_id)}"
                                              if e.path_id and e.kind in ("quest", "step",
                                                                          "focus") else "")))
        return ft.Row([ft.Icon(icon, size=16 if compact else 20, color=col),
                       ft.Column(texts, spacing=0, expand=True, tight=True)],
                      spacing=Space.SM, vertical_alignment=ft.CrossAxisAlignment.CENTER)

    def _open_day(self, d: date) -> None:
        sfx.play("tap")
        entries = self.app.game.calendar_entries(d, d, self._kinds()).get(d, [])
        body: list[ft.Control] = []
        if not entries:
            body.append(common.hint("Nothing logged. Rest days are part of the journey."))
        sheet_ref: list[ft.BottomSheet] = []
        for e in entries:
            row = self._entry_row(e)
            edit = self._editor_for(e, sheet_ref)
            if edit is not None:
                row.controls.append(ft.IconButton(ft.Icons.EDIT, icon_size=18,
                                                  icon_color=C.TEXT_DIM, tooltip="Edit",
                                                  width=40, height=40, on_click=edit))
            body.append(ft.Container(row, bgcolor=C.SURFACE_HI, border_radius=Radius.SM,
                                     padding=ft.Padding.only(left=Space.MD, right=Space.XS,
                                                             top=Space.SM, bottom=Space.SM)))
        title = "Today" if d == self.app.today() else f"{d:%A}, {common.short_date(d)}"
        sheet_ref.append(common.open_sheet(self.app.page, title, body))

    def _editor_for(self, e: Entry, sheet_ref: list) -> Any:
        app = self.app

        def close() -> None:
            if sheet_ref:
                common.close(sheet_ref[0])

        if e.kind == "quest" and any(q.id == e.ref_id for q in app.game.quests):
            return lambda ev: (close(), editors.edit_quest(app, e.ref_id, self._refresh))
        if e.kind in ("bill_due", "bill_paid") and any(b.id == e.ref_id
                                                       for b in app.game.data.bills):
            if app.game.bill(e.ref_id).archived:
                return None
            return lambda ev: (close(), editors.edit_bill(app, e.ref_id, self._refresh))
        return None

    # ------------------------------------------------------------------ actions
    def _set_mode(self, v: str) -> None:
        sfx.play("toggle")
        self.view_mode = v
        self._refresh()

    def _set_filters(self, selected: set[str]) -> None:
        self.filters = selected
        self._refresh()

    def _shift(self, n: int) -> None:
        sfx.play("tap")
        if self.view_mode == "month":
            self.cursor = add_months(self.cursor.replace(day=1), n)
        else:
            self.cursor += timedelta(days=7 * n)
        self._refresh()

    def _to_today(self, _: Any = None) -> None:
        self.cursor = self.app.today()
        self._refresh()
