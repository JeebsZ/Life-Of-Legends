"""Small shared pieces for screens: sheets, confirm dialog, toast, pickers, labels.

Draw + wire only. No game rules here.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable, Sequence
from datetime import date, datetime, time, timedelta
from typing import Any

import flet as ft

from lol.ui import ambient, sfx
from lol.ui import theme as th
from lol.ui.theme import C, Motion, Radius, Size, Space, Type

LIST_PADDING = ft.Padding.only(left=Space.GUTTER, right=Space.GUTTER, top=Space.SM,
                               bottom=96)  # room so the FAB never covers the last row


def screen_list() -> ft.ListView:
    return ft.ListView(expand=True, spacing=Space.SM, padding=LIST_PADDING)


def card(content: ft.Control, *, padding: int = Space.LG, tint: str | None = None,
         **kw: Any) -> ft.Container:
    """Panel: frosted glass over the mind-space (flat when glass is capped to "flat").
    `tint`: a hex hue for the hairline + glow (e.g. a Path colour)."""
    return ambient.glass(content, "frost", radius=Radius.MD, padding=padding, tint=tint,
                         **kw)


def sheet_quality(page: ft.Page | None) -> str:
    """Real backdrop blur for sheets on the phone; frost on web (a large backdrop blur can
    crash the web renderer)."""
    try:
        return "frost" if page is not None and page.web else "blur"
    except Exception:  # noqa: BLE001
        return "frost"


def hint(text: str) -> ft.Text:
    return ft.Text(text, size=Type.CAPTION, color=C.TEXT_DIM)


def toast(page: ft.Page, text: str, *, icon: ft.IconData | None = None) -> None:
    row: list[ft.Control] = []
    if icon:
        row.append(ft.Icon(icon, color=C.PRIMARY, size=18))
    row.append(ft.Text(text, color=C.TEXT, size=Type.BODY - 1, expand=True))
    page.show_dialog(ft.SnackBar(ft.Row(row, spacing=Space.SM), bgcolor=C.SURFACE_HI,
                                 behavior=ft.SnackBarBehavior.FLOATING, duration=2200))


async def confirm(page: ft.Page, title: str, message: str, ok_text: str, *,
                  danger: bool = False) -> bool:
    """Modal yes/no. Resolves False on dismiss."""
    fut: asyncio.Future[bool] = asyncio.get_running_loop().create_future()

    def done(value: bool) -> None:
        if not fut.done():
            fut.set_result(value)
            close(dlg)

    def dismissed(_: Any) -> None:
        if not fut.done():
            fut.set_result(False)

    dlg = ft.AlertDialog(
        title=ft.Text(title, size=Type.TITLE + 1, weight=ft.FontWeight.BOLD, color=C.TEXT),
        content=ft.Text(message, size=Type.BODY, color=C.TEXT_DIM),
        bgcolor=C.SURFACE_HI,
        actions=[
            ft.TextButton("Not now", on_click=lambda e: done(False), height=Size.TAP,
                          style=ft.ButtonStyle(color=C.TEXT_DIM)),
            ft.FilledButton(ok_text, on_click=lambda e: done(True), height=Size.TAP,
                            style=ft.ButtonStyle(bgcolor=C.DANGER if danger else C.PRIMARY,
                                                 color=C.ON_DANGER if danger else C.ON_PRIMARY)),
        ],
        on_dismiss=dismissed,
    )
    sfx.play("sheet_open")
    page.show_dialog(dlg)
    return await fut


def close(dialog: ft.DialogControl) -> None:
    """Close this exact dialog. (page.pop_dialog() closes the topmost *open* one, which can be
    a lingering SnackBar toast instead of the sheet.)"""
    if dialog.open:
        dialog.open = False
        dialog.update()
        if isinstance(dialog, ft.BottomSheet):
            _sheet_closed(dialog)


_closed_sheets: set[int] = set()


def _sheet_closed(sheet: ft.BottomSheet) -> None:
    """sheet_close sound once per sheet (closing in code and on_dismiss both land here)."""
    if id(sheet) not in _closed_sheets:
        _closed_sheets.add(id(sheet))
        sfx.play("sheet_close")


def open_sheet(page: ft.Page, title: str, body: list[ft.Control], *,
               on_dismiss: Callable[[], Any] | None = None) -> ft.BottomSheet:
    def dismissed(_: Any) -> None:
        _sheet_closed(sheet)
        if on_dismiss:
            on_dismiss()

    panel = ambient.glass(
        ft.Column([ft.Container(width=36, height=4, border_radius=2,
                                bgcolor=C.a(C.TEXT, 0.3)),
                   ft.Text(title, size=Type.HEADLINE - 2, weight=ft.FontWeight.BOLD,
                           color=C.TEXT), *body],
                  spacing=Space.MD, tight=True, scroll=ft.ScrollMode.AUTO,
                  horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
        sheet_quality(page), radius=0, fill=1.6, glow=False,
        padding=ft.Padding.only(left=Space.LG, right=Space.LG, top=Space.MD,
                                bottom=Space.XL))
    panel.border_radius = ft.BorderRadius.only(top_left=Radius.LG, top_right=Radius.LG)
    sheet = ft.BottomSheet(
        panel, bgcolor=ft.Colors.TRANSPARENT, show_drag_handle=False, scrollable=True,
        on_dismiss=dismissed,
    )
    _closed_sheets.discard(id(sheet))
    sfx.play("sheet_open")
    page.show_dialog(sheet)
    return sheet


def reopen(page: ft.Page, sheet: ft.BottomSheet) -> None:
    """Show a sheet again (after stepping out of it, e.g. for a full-screen effect)."""
    _closed_sheets.discard(id(sheet))
    sfx.play("sheet_open")
    page.show_dialog(sheet)


def text_field(label: str, *, number: bool = False, prefix: str | None = None,
               autofocus: bool = False, on_submit: Callable | None = None) -> ft.TextField:
    return ft.TextField(
        label=label, autofocus=autofocus, on_submit=on_submit, filled=True,
        border_radius=Radius.SM, color=C.TEXT, fill_color=C.SURFACE_HI,
        keyboard_type=ft.KeyboardType.NUMBER if number else ft.KeyboardType.TEXT,
        prefix=prefix, capitalization=None if number else ft.TextCapitalization.SENTENCES,
    )


def with_sound(fn: Callable | None, name: str = "tap") -> Callable | None:
    """Wrap a click handler (sync or async, taking the event) so it plays a UI sound first."""
    if fn is None:
        return None

    async def handler(e: Any = None) -> None:
        sfx.play(name)
        res = fn(e)
        if inspect.isawaitable(res):
            await res

    return handler


def primary_button(text: str, on_click: Callable, *, icon: ft.IconData | None = None,
                   expand: bool = True) -> ft.FilledButton:
    return ft.FilledButton(text, icon=icon, on_click=with_sound(on_click), height=Size.TAP,
                           expand=expand,
                           style=ft.ButtonStyle(bgcolor=C.PRIMARY, color=C.ON_PRIMARY))


def secondary_button(text: str, on_click: Callable, *, icon: ft.IconData | None = None,
                     color: str = C.PRIMARY, expand: bool = True) -> ft.OutlinedButton:
    return ft.OutlinedButton(text, icon=icon, on_click=with_sound(on_click), height=Size.TAP,
                             expand=expand,
                             style=ft.ButtonStyle(color=color,
                                                  side=ft.BorderSide(1, C.a(color, 0.5))))


MenuItem = tuple  # (label, icon, action) or (label, icon, action, danger)


def menu_button(items: Sequence[MenuItem], *, tooltip: str = "Options") -> ft.PopupMenuButton:
    """A vertical-dots options menu. Each action may be sync or async (no arguments)."""
    def run(fn: Callable[[], Any]) -> Callable[[Any], Any]:
        async def go(_: Any) -> None:
            sfx.play("tap")
            res = fn()
            if inspect.isawaitable(res):
                await res
        return go

    entries = []
    for it in items:
        label, icon, fn = it[0], it[1], it[2]
        danger = len(it) > 3 and bool(it[3])
        col = C.DANGER if danger else C.PRIMARY
        entries.append(ft.PopupMenuItem(
            content=ft.Row([ft.Icon(icon, size=18, color=col),
                            ft.Text(label, color=C.DANGER if danger else C.TEXT,
                                    size=Type.BODY - 1)], spacing=Space.SM, tight=True),
            on_click=run(fn)))
    return ft.PopupMenuButton(
        icon=ft.Icons.MORE_VERT, icon_color=C.TEXT_DIM, icon_size=20, tooltip=tooltip,
        width=40, height=Size.TAP, padding=0, bgcolor=C.SURFACE_HI,
        on_open=lambda e: sfx.play("tap"), items=entries)


def back_bar(title: str, on_back: Callable[[], Any], *,
             trailing: ft.Control | None = None) -> ft.Container:
    """Sub-screen header: back arrow + title (+ an optional trailing action)."""
    row: list[ft.Control] = [
        ft.IconButton(ft.Icons.ARROW_BACK, icon_color=C.TEXT, tooltip="Back", width=Size.TAP,
                      height=Size.TAP, on_click=lambda e: on_back()),
        ft.Text(title, size=Type.HEADLINE - 2, weight=ft.FontWeight.BOLD, color=C.TEXT,
                expand=True, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
    ]
    if trailing is not None:
        row.append(trailing)
    return ft.Container(ft.Row(row, spacing=Space.XS,
                               vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        padding=ft.Padding.only(left=Space.XS, right=Space.SM, top=Space.XS))


def switch_row(title: str, sub: str, value: bool, on_change: Callable[[bool], Any], *,
               icon: ft.IconData | None = None) -> ft.Row:
    """Label + hint + Switch (plays the toggle sound)."""
    async def changed(e: Any) -> None:
        sfx.play("toggle")
        res = on_change(bool(e.control.value))
        if inspect.isawaitable(res):
            await res

    items: list[ft.Control] = []
    if icon:
        items.append(ft.Icon(icon, color=C.PRIMARY, size=22))
    items += [ft.Column([ft.Text(title, size=Type.BODY, weight=ft.FontWeight.W_600,
                                 color=C.TEXT), hint(sub)], spacing=0, expand=True, tight=True),
              ft.Switch(value=value, active_color=C.PRIMARY, on_change=changed)]
    return ft.Row(items, spacing=Space.MD, vertical_alignment=ft.CrossAxisAlignment.CENTER)


def date_row(page: ft.Page, label: str, value: date | None, today: date,
             on_pick: Callable[[date | None], Any], *, clearable: bool = False,
             help_text: str | None = None) -> ft.Container:
    """A tappable row that opens a DatePicker; on_pick(date) (or None when cleared)."""
    text = ft.Text(long_date(value) if value else "None", size=Type.BODY, color=C.TEXT,
                   weight=ft.FontWeight.W_600)
    clear_btn = ft.IconButton(ft.Icons.CLOSE, icon_size=18, icon_color=C.TEXT_DIM,
                              tooltip="Clear", width=40, height=40,
                              visible=clearable and value is not None)

    def picked(e: Any) -> None:
        v = e.control.value
        if v is not None:
            d = local_date(v)
            text.value = long_date(d)
            clear_btn.visible = clearable
            text.update()
            clear_btn.update()
            on_pick(d)

    def clear(_: Any) -> None:
        sfx.play("tap")
        text.value, clear_btn.visible = "None", False
        text.update()
        clear_btn.update()
        on_pick(None)

    def open_picker(_: Any) -> None:
        sfx.play("tap")
        page.show_dialog(picker)

    clear_btn.on_click = clear
    picker = ft.DatePicker(value=value or today, first_date=today - timedelta(days=365 * 2),
                           last_date=today + timedelta(days=365 * 3), on_change=picked,
                           help_text=help_text or label)
    return ft.Container(
        ft.Row([ft.Icon(ft.Icons.EVENT, color=C.PRIMARY), ft.Text(label, color=C.TEXT_DIM),
                ft.Container(expand=True), text, clear_btn,
                ft.Icon(ft.Icons.EDIT_CALENDAR, color=C.TEXT_DIM, size=18)],
               spacing=Space.SM, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        height=Size.TAP + 8, bgcolor=C.SURFACE_HI, border_radius=Radius.SM,
        padding=ft.Padding.only(left=Space.MD, right=Space.SM), ink=True, on_click=open_picker,
    )


def long_date(d: date) -> str:
    return f"{d:%a}, {d:%b} {d.day}, {d.year}"


class ToggleChips(ft.Row):
    """Multi-select filter chips (40 px tall). options: (value, label, icon or None, color)."""

    def __init__(self, options: Sequence[tuple[str, str, ft.IconData | None, str]],
                 selected: set[str], on_change: Callable[[set[str]], Any]) -> None:
        self.options, self.selected, self.on_change = list(options), set(selected), on_change
        self._chips: dict[str, ft.Container] = {}
        for val, label, icon, _ in self.options:
            items: list[ft.Control] = []
            if icon:
                items.append(ft.Icon(icon, size=15))
            items.append(ft.Text(label, size=Type.CAPTION, weight=ft.FontWeight.BOLD,
                                 no_wrap=True))
            self._chips[val] = ft.Container(
                ft.Row(items, spacing=4, tight=True), height=40,
                border_radius=Radius.PILL, alignment=ft.Alignment.CENTER,
                padding=ft.Padding.symmetric(horizontal=Space.MD - 2),
                on_click=lambda e, v=val: self._flip(v), animate=Motion.anim(Motion.FADE_MS))
        super().__init__(list(self._chips.values()), spacing=Space.XS + 2,
                         scroll=ft.ScrollMode.HIDDEN)
        self._paint()

    def _paint(self) -> None:
        for val, _label, _icon, color in self.options:
            chip = self._chips[val]
            on = val in self.selected
            chip.bgcolor = C.a(color, 0.18) if on else C.a(C.TEXT, 0.05)
            chip.border = ft.Border.all(1.2, C.a(color, 0.7) if on else C.a(C.TEXT, 0.08))
            for item in chip.content.controls:  # type: ignore[union-attr]
                item.color = color if on else C.TEXT_DIM

    def _flip(self, value: str) -> None:
        sfx.play("toggle")
        self.selected ^= {value}
        self._paint()
        self.update()
        self.on_change(set(self.selected))


def segmented(options: Sequence[tuple[str, str]], value: str,
              on_change: Callable[[str], None] | None = None) -> ft.SegmentedButton:
    def changed(e: Any) -> None:
        if on_change and e.control.selected:
            on_change(e.control.selected[0])

    return ft.SegmentedButton(
        segments=[ft.Segment(value=v, label=ft.Text(lbl, size=Type.LABEL)) for v, lbl in options],
        selected=[value], show_selected_icon=False, on_change=changed,
        style=ft.ButtonStyle(color=C.TEXT, padding=ft.Padding.symmetric(horizontal=6)),
    )


class ChoicePills(ft.Container):
    """Single-choice pills (Path picker, filters). Each pill is >= 48 px tall.

    options: (value, label, icon or None, color). grid_cols: pills per row (ResponsiveRow),
    or 0 for one horizontally scrolling row.
    """

    def __init__(self, options: Sequence[tuple[str, str, ft.IconData | None, str]],
                 value: str, *, on_change: Callable[[str], Any] | None = None,
                 grid_cols: int = 3) -> None:
        self.options, self.value, self.on_change = list(options), value, on_change
        self._pills: dict[str, ft.Container] = {}
        for val, label, icon, _ in self.options:
            items: list[ft.Control] = []
            if icon:
                items.append(ft.Icon(icon, size=16))
            items.append(ft.Text(label, size=Type.LABEL, weight=ft.FontWeight.BOLD,
                                 no_wrap=True))
            self._pills[val] = ft.Container(
                ft.Row(items, spacing=Space.XS, tight=True,
                       alignment=ft.MainAxisAlignment.CENTER),
                height=Size.TAP, border_radius=Radius.PILL, alignment=ft.Alignment.CENTER,
                padding=ft.Padding.symmetric(horizontal=Space.MD),
                on_click=lambda e, v=val: self._pick(v), data=val,
                animate=Motion.anim(Motion.FADE_MS), scale=1,
                animate_scale=Motion.anim(Motion.POP_MS, Motion.BACK),
                col=12 // grid_cols if grid_cols else None,
            )
        pills = list(self._pills.values())
        if grid_cols:
            body: ft.Control = ft.ResponsiveRow(pills, spacing=Space.SM, run_spacing=Space.SM)
        else:
            body = ft.Row(pills, spacing=Space.SM, scroll=ft.ScrollMode.HIDDEN)
        super().__init__(body)
        self._paint()

    def _paint(self) -> None:
        for val, _label, _icon, color in self.options:
            pill = self._pills[val]
            on = val == self.value
            fg = color if on else C.TEXT_DIM
            pill.bgcolor = C.a(color, 0.18) if on else C.a(C.TEXT, 0.05)
            pill.border = ft.Border.all(1.5, C.a(color, 0.7) if on else C.a(C.TEXT, 0.08))
            for item in pill.content.controls:  # type: ignore[union-attr]
                item.color = fg

    def _pick(self, value: str) -> None:
        from lol.ui.components import buzz, pop  # local: avoid cycles in type checkers

        self.value = value
        self._paint()
        if self.page:
            self.page.run_task(buzz, "select")
            self.page.run_task(pop, self._pills[value], 1.05)
        self.update()
        if self.on_change:
            self.on_change(value)


def path_options(include_all: bool = False) -> list[tuple[str, str, ft.IconData | None, str]]:
    opts: list[tuple[str, str, ft.IconData | None, str]] = []
    if include_all:
        opts.append(("all", "All", ft.Icons.APPS, C.PRIMARY))
    opts += [(pid, th.path_name(pid), th.path_icon(pid), th.path_color(pid))
             for pid in th.PATH_IDS]
    return opts


def local_date(value: date | datetime) -> date:
    """DatePicker values arrive as UTC datetimes (local midnight shifted, so east of UTC it
    reads as the previous day). Convert back to the local calendar date."""
    if isinstance(value, datetime):
        return (value.astimezone() if value.tzinfo else value).date()
    return value


def short_date(d: date) -> str:
    return f"{d:%b} {d.day}"


def due_label(status: str, due: date, today: date) -> str:
    days = (due - today).days
    if status == "paid":
        return "All paid"
    if days < 0:
        return f"Was due {short_date(due)}"
    if days == 0:
        return "Due today"
    if days == 1:
        return "Due tomorrow"
    return f"Due {short_date(due)}"


REPEAT_LABELS = {"none": None, "weekly": "Weekly", "monthly": "Monthly", "yearly": "Yearly"}


# --------------------------------------------------------------------------- v1.3 helpers
def hm(value: str) -> time:
    h, m = (value or "00:00").split(":")[:2]
    return time(int(h), int(m))


def time_row(page: ft.Page, label: str, value: str, on_pick: Callable[[str], Any], *,
             icon: ft.IconData = ft.Icons.SCHEDULE) -> ft.Container:
    """A tappable row that opens a TimePicker; on_pick("HH:MM")."""
    text = ft.Text(value, size=Type.BODY, color=C.TEXT, weight=ft.FontWeight.W_600)

    def picked(e: Any) -> None:
        v = e.control.value
        if v is not None:
            val = f"{v.hour:02d}:{v.minute:02d}"
            text.value = val
            text.update()
            on_pick(val)

    picker = ft.TimePicker(value=hm(value), on_change=picked, help_text=label)

    def open_picker(_: Any) -> None:
        sfx.play("tap")
        picker.value = hm(text.value or value)
        page.show_dialog(picker)

    return ft.Container(
        ft.Row([ft.Icon(icon, color=C.PRIMARY), ft.Text(label, color=C.TEXT_DIM, expand=True),
                text, ft.Icon(ft.Icons.EDIT, color=C.TEXT_DIM, size=16)],
               spacing=Space.SM, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        height=Size.TAP + 4, bgcolor=C.a(C.SURFACE_HI, 0.7), border_radius=Radius.SM,
        padding=ft.Padding.only(left=Space.MD, right=Space.MD), ink=True,
        on_click=open_picker,
    )


def stepper(value: int, on_change: Callable[[int], Any], *, lo: int = 0, hi: int = 999,
            step: int = 1, suffix: str = "", width: int = 64) -> ft.Row:
    """[-] value [+] for small numbers (minutes, days, reps) - big thumb targets."""
    st = {"v": value}
    txt = ft.Text(f"{value}{suffix}", size=Type.BODY, weight=ft.FontWeight.W_700, color=C.TEXT,
                  width=width, text_align=ft.TextAlign.CENTER)

    def bump(d: int) -> None:
        v = max(lo, min(hi, st["v"] + d))
        if v == st["v"]:
            sfx.play("error_soft")
            return
        sfx.play("tap")
        st["v"] = v
        txt.value = f"{v}{suffix}"
        txt.update()
        on_change(v)

    return ft.Row([
        ft.IconButton(ft.Icons.REMOVE, on_click=lambda e: bump(-step), width=Size.TAP,
                      height=Size.TAP, icon_color=C.PRIMARY, tooltip="Less"),
        txt,
        ft.IconButton(ft.Icons.ADD, on_click=lambda e: bump(step), width=Size.TAP,
                      height=Size.TAP, icon_color=C.PRIMARY, tooltip="More"),
    ], spacing=0, tight=True, vertical_alignment=ft.CrossAxisAlignment.CENTER)


def bar_chart(rows: Sequence[tuple[str, float, str]], *, height: int = 120,
              color: str = C.PRIMARY, goal: float | None = None,
              empty: str = "Nothing logged yet.") -> ft.Control:
    """Tiny bar chart from Containers (no chart dependency). rows: (label, value, value text).
    `goal`: a faint line at that value. Zero values draw a hairline stub."""
    if not rows or not any(v for _, v, _ in rows):
        return ft.Container(hint(empty), height=height // 2, alignment=ft.Alignment.CENTER)
    top = max([v for _, v, _ in rows] + [goal or 0]) or 1
    span = height - 34  # room for the value and label lines
    bars: list[ft.Control] = []
    for label, v, vt in rows:
        h = max(2, round(span * (v / top)))
        bars.append(ft.Column([
            ft.Text(vt, size=9, color=C.TEXT_DIM, no_wrap=True, max_lines=1,
                    text_align=ft.TextAlign.CENTER),
            ft.Container(height=h, border_radius=ft.BorderRadius.only(top_left=4, top_right=4),
                         bgcolor=color if v else C.a(C.TEXT, 0.15), tooltip=f"{label}: {vt}"),
            ft.Text(label, size=9, color=C.TEXT_DIM, no_wrap=True, max_lines=1,
                    text_align=ft.TextAlign.CENTER),
        ], spacing=2, expand=True, tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            alignment=ft.MainAxisAlignment.END))
    chart: list[ft.Control] = [ft.Row(bars, spacing=3, height=height,
                                      vertical_alignment=ft.CrossAxisAlignment.END)]
    if goal:
        gy = 15 + round(span * (goal / top))
        chart.append(ft.Container(height=1, bgcolor=C.a(C.ACCENT, 0.7), left=0, right=0,
                                  bottom=gy, tooltip="Goal"))
    return ft.Stack(chart, height=height)


def progress_ring(value: float, center: ft.Control, *, size: int = 132,
                  color: str = C.PRIMARY) -> ft.Stack:
    """A big round progress ring with content in the middle."""
    return ft.Stack([
        ft.ProgressRing(value=max(0.0, min(1.0, value)), width=size, height=size,
                        stroke_width=10, color=color, bgcolor=C.a(C.TEXT, 0.1)),
        ft.Container(center, width=size, height=size, alignment=ft.Alignment.CENTER),
    ], width=size, height=size)


def empty_card(title: str, text: str, icon: ft.IconData) -> ft.Container:
    return card(ft.Column([ft.Icon(icon, size=36, color=C.a(C.PRIMARY, 0.7)),
                           ft.Text(title, size=Type.TITLE, weight=ft.FontWeight.BOLD,
                                   color=C.TEXT, text_align=ft.TextAlign.CENTER),
                           ft.Text(text, size=Type.CAPTION, color=C.TEXT_DIM,
                                   text_align=ft.TextAlign.CENTER)],
                          spacing=Space.SM, tight=True,
                          horizontal_alignment=ft.CrossAxisAlignment.CENTER))


def section(title: str) -> ft.Container:
    return ft.Container(
        ft.Text(th.label(title), size=Type.CAPTION, weight=ft.FontWeight.BOLD,
                color=C.TEXT_DIM, style=ft.TextStyle(letter_spacing=th.label_spacing())),
        padding=ft.Padding.only(left=Space.XS, top=Space.SM))


def fmt_minutes(m: int | None) -> str:
    if m is None:
        return "-"
    h, mm = divmod(int(m), 60)
    return f"{h} h {mm:02d} m" if h else f"{mm} min"
