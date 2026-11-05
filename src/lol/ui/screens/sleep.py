"""More -> Sleep: log a night (bedtime and wake time, which can cross midnight), naps, a 1-5
restedness rating and a note; edit or delete later; the weekly average and a simple bar chart
of the last 14 nights.

Plain numbers only - no scores, targets or health claims. Logging gives a little Monk XP
(Game.log_sleep caps it per day); how long you slept is never rewarded."""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

import flet as ft

from lol.core.game import sleep_minutes
from lol.core.models import SleepEntry
from lol.ui import components as ui
from lol.ui import sfx
from lol.ui.screens import common
from lol.ui.theme import C, Motion, Radius, Size, Space, Type

if TYPE_CHECKING:
    from lol.ui.app import App

SLEEP = "#A78BFA"
REST_LABELS = {1: "Drained", 2: "Tired", 3: "Okay", 4: "Good", 5: "Fresh"}


def rest_pills(value: int | None, on_change: Any) -> ft.Row:
    """1..5 restedness (optional: tap the selected one again to clear)."""
    st = {"v": value}
    row = ft.Row(spacing=Space.XS)

    def paint() -> None:
        row.controls = []
        for n in range(1, 6):
            on = st["v"] == n
            row.controls.append(ft.Container(
                ft.Column([ft.Text(str(n), size=Type.BODY, weight=ft.FontWeight.W_900,
                                   color=SLEEP if on else C.TEXT),
                           ft.Text(REST_LABELS[n], size=9, color=C.TEXT_DIM, no_wrap=True)],
                          spacing=0, tight=True,
                          horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                height=Size.TAP + 4, expand=True, border_radius=Radius.SM,
                alignment=ft.Alignment.CENTER, bgcolor=C.a(SLEEP, 0.2 if on else 0.06),
                border=ft.Border.all(1.2, C.a(SLEEP, 0.75 if on else 0.2)),
                animate=Motion.anim(Motion.FADE_MS),
                on_click=lambda e, k=n: pick(k)))

    def pick(n: int) -> None:
        sfx.play("toggle")
        st["v"] = None if st["v"] == n else n
        paint()
        row.update()
        on_change(st["v"])

    paint()
    return row


def sleep_form(app: App, title: str, initial: SleepEntry | None, on_save: Any,
               extra: list[ft.Control] | None = None) -> ft.BottomSheet:
    """Bottom sheet to log or edit one night. on_save(values) returns False to stay open."""
    today = app.today()
    if initial is None:  # last night, or the most recent night not logged yet (2 weeks back)
        logged = {e.night_of for e in app.game.sleep_entries(today - timedelta(days=15))}
        night = next((today - timedelta(days=i) for i in range(1, 15)
                      if (today - timedelta(days=i)).isoformat() not in logged),
                     today - timedelta(days=1))
    else:
        night = date.fromisoformat(initial.night_of)
    st: dict[str, Any] = {
        "night": night,
        "bed": initial.bedtime if initial else "23:00",
        "wake": initial.wake if initial else "07:00",
        "naps": initial.naps_min if initial else 0,
        "rest": initial.restedness if initial else None,
    }
    duration = ft.Text("", size=Type.TITLE, weight=ft.FontWeight.W_800, color=SLEEP)

    def paint_duration() -> None:
        if st["bed"] == st["wake"]:
            duration.value = "Bedtime and wake time are the same"
            return
        m = sleep_minutes(st["bed"], st["wake"])
        crosses = st["wake"] <= st["bed"]
        duration.value = f"{common.fmt_minutes(m)} night sleep" + (
            " (past midnight)" if crosses else "")

    def set_time(key: str, v: str) -> None:
        st[key] = v
        paint_duration()
        ui.refresh(duration)

    paint_duration()
    note = common.text_field("Note (optional)")
    note.value = initial.note if initial else ""

    def save(_: Any = None) -> None:
        values = {"night_of": st["night"], "bedtime": st["bed"], "wake": st["wake"],
                  "naps_min": st["naps"], "restedness": st["rest"],
                  "note": (note.value or "").strip()}
        if on_save(values) is False:
            return
        common.close(sheet)

    body: list[ft.Control] = [
        common.date_row(app.page, "Night of", st["night"], today,
                        lambda d: st.update(night=d or st["night"]),
                        help_text="The evening the night started"),
        common.time_row(app.page, "Bedtime", st["bed"], lambda v: set_time("bed", v),
                        icon=ft.Icons.BEDTIME),
        common.time_row(app.page, "Woke up", st["wake"], lambda v: set_time("wake", v),
                        icon=ft.Icons.WB_SUNNY),
        duration,
        ft.Row([ft.Icon(ft.Icons.AIRLINE_SEAT_FLAT, color=C.TEXT_DIM, size=20),
                ft.Text("Naps", color=C.TEXT_DIM, expand=True),
                common.stepper(st["naps"], lambda v: st.update(naps=v), lo=0, hi=600, step=10,
                               suffix=" min", width=72)],
               vertical_alignment=ft.CrossAxisAlignment.CENTER),
        common.hint("How rested do you feel? (optional)"),
        rest_pills(st["rest"], lambda v: st.update(rest=v)),
        note,
        ft.Row([common.primary_button("Save night", save, icon=ft.Icons.CHECK)]),
    ]
    if extra:
        body += extra
    sheet = common.open_sheet(app.page, title, body)
    return sheet


class SleepScreen:
    title = "Sleep"

    def __init__(self, app: App) -> None:
        self.app = app
        self.list = common.screen_list()
        self.view = ft.Container(self.list, expand=True, key="sleep")
        self.fab = ft.FloatingActionButton(icon=ft.Icons.BEDTIME, on_click=self.open_log,
                                           bgcolor=C.PRIMARY, foreground_color=C.ON_PRIMARY,
                                           tooltip="Log a night")

    def _refresh(self) -> None:
        self.render()
        ui.refresh(self.list)

    def restyle(self) -> None:
        self._refresh()

    def render(self) -> None:
        g, today = self.app.game, self.app.today()
        week = g.sleep_stats(today - timedelta(days=7), today)
        two = g.sleep_stats(today - timedelta(days=14), today)
        by_night = {n: m for n, m, _, _ in two["per_night"]}
        rows = []
        for i in range(14, 0, -1):
            d = today - timedelta(days=i)
            m = by_night.get(d.isoformat())
            rows.append((f"{d.day}", (m or 0) / 60, f"{m / 60:.1f}" if m else "–"))

        def stat(value: str, label: str) -> ft.Control:
            return ft.Column([ft.Text(value, size=Type.TITLE, weight=ft.FontWeight.W_800,
                                      color=C.TEXT),
                              common.hint(label)], spacing=0, tight=True, expand=True,
                             horizontal_alignment=ft.CrossAxisAlignment.CENTER)

        rest = week["avg_restedness"]
        summary = common.card(ft.Column([
            ft.Row([stat(common.fmt_minutes(week["avg_minutes"]), "avg night (7 d)"),
                    stat(f"{week['nights']}", "nights logged"),
                    stat(f"{rest:g}/5" if rest is not None else "-", "avg rested")]),
            ft.Divider(height=1, color=C.OUTLINE),
            ft.Text("Last 14 nights (hours)", size=Type.LABEL, weight=ft.FontWeight.W_700,
                    color=C.TEXT),
            common.bar_chart(rows, color=SLEEP, height=130,
                             empty="No nights logged yet. Tap the moon to add one."),
            common.hint("Just your own numbers - missing nights stay blank."),
        ], spacing=Space.SM, tight=True), tint=SLEEP)
        items: list[ft.Control] = [
            summary,
            ft.Row([common.primary_button("Log a night", self.open_log, icon=ft.Icons.BEDTIME)]),
            common.section("Nights"),
        ]
        entries = g.sleep_entries()[:30]
        if not entries:
            items.append(common.empty_card("No nights yet",
                                           "Log last night when you have a moment.",
                                           ft.Icons.NIGHTLIGHT))
        for e in entries:
            items.append(self._row(e))
        self.list.controls = items

    def _row(self, e: SleepEntry) -> ft.Control:
        g = self.app.game
        d = date.fromisoformat(e.night_of)
        bits = [f"{e.bedtime} → {e.wake}"]
        if e.naps_min:
            bits.append(f"naps {e.naps_min} min")
        if e.restedness:
            bits.append(f"rested {e.restedness}/5")
        return common.card(ft.Row([
            ft.Icon(ft.Icons.NIGHTLIGHT, color=SLEEP, size=22),
            ft.Column([
                ft.Text(f"{d:%a} {common.short_date(d)} · "
                        f"{common.fmt_minutes(g.sleep_duration(e))}", size=Type.BODY,
                        weight=ft.FontWeight.W_600, color=C.TEXT),
                common.hint(" · ".join(bits)),
                *([common.hint(e.note)] if e.note else []),
            ], spacing=0, expand=True, tight=True),
            common.menu_button([
                ("Edit", ft.Icons.EDIT, lambda eid=e.id: self.open_edit(eid)),
                ("Delete", ft.Icons.DELETE_OUTLINE, lambda eid=e.id: self._delete(eid), True),
            ], tooltip="Night options"),
        ], spacing=Space.MD, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.Padding.only(left=Space.MD, top=Space.XS, bottom=Space.XS),
            on_click=lambda ev, eid=e.id: self.open_edit(eid))

    def open_log(self, _: Any = None) -> None:
        app, g = self.app, self.app.game

        def save(v: dict) -> bool:
            async def go() -> None:
                c = await app.award(
                    lambda: g.log_sleep(v["night_of"], v["bedtime"], v["wake"], app.today(),
                                        v["naps_min"], v["restedness"], v["note"]),
                    line=lambda c: f"Notice: Night logged. +{c.xp} XP to Monk Path.")
                if not c.xp:
                    sfx.play("tap")
                    app.toast("Night logged", ft.Icons.NIGHTLIGHT)
                self._refresh()

            try:  # validate first so the sheet can stay open on a mistake
                g._check_sleep(v["bedtime"], v["wake"], v["naps_min"], v["restedness"])
                if any(e.night_of == v["night_of"].isoformat() for e in g.sleep_entries()):
                    raise ValueError("That night is already logged. Edit it instead.")
            except ValueError as exc:
                app.error(str(exc))
                return False
            app.page.run_task(go)
            return True

        sleep_form(app, "Log a night", None, save)

    def open_edit(self, entry_id: str) -> None:
        app, g = self.app, self.app.game
        e = g.sleep_entry(entry_id)

        def save(v: dict) -> bool:
            try:
                g.edit_sleep(entry_id, night_of=v["night_of"], bedtime=v["bedtime"],
                             wake=v["wake"], naps_min=v["naps_min"],
                             restedness=v["restedness"], note=v["note"])
            except ValueError as exc:
                app.error(str(exc))
                return False
            app.save()
            sfx.play("toggle")
            app.toast("Night updated", ft.Icons.EDIT)
            self._refresh()
            return True

        sleep_form(app, "Edit night", e, save)

    async def _delete(self, entry_id: str) -> None:
        if not await common.confirm(self.app.page, "Delete this night?",
                                    "It leaves your sleep log. XP you earned stays.", "Delete",
                                    danger=True):
            return
        self.app.game.delete_sleep(entry_id)
        self.app.save()
        self.app.toast("Night deleted", ft.Icons.DELETE_OUTLINE)
        self._refresh()
