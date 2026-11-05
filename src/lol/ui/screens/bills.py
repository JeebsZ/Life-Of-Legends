"""More -> Bills (also pinnable to the center nav slot): 30-day total, bills by urgency with one-tap pay, add-bill sheet."""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

import flet as ft

from lol.core.models import Bill
from lol.ui import components as ui
from lol.ui import sfx, voice
from lol.ui.screens import common, editors
from lol.ui.theme import C, Radius, Size, Space, Type

if TYPE_CHECKING:
    from lol.ui.app import App


class BillsScreen:
    title = "Bills"

    def __init__(self, app: App) -> None:
        self.app = app
        self.show_paid = False
        self.list = common.screen_list()
        self.view = ft.Container(self.list, expand=True, key="bills")
        self.fab = ft.FloatingActionButton(icon=ft.Icons.ADD, on_click=self._open_add,
                                           bgcolor=C.PRIMARY, foreground_color=C.ON_PRIMARY,
                                           tooltip="Add bill")

    # ------------------------------------------------------------------ render
    def render(self) -> None:
        g, today = self.app.game, self.app.today()
        rows = g.bills_status(today)
        overdue = sum(1 for _, s, _ in rows if s == "overdue")
        if overdue > getattr(self, "_overdue_heard", 0):  # low-health warning, once per new one
            sfx.play("low_health", 0.6)
        self._overdue_heard = overdue
        soon = sum(1 for _, s, _ in rows if s == "due_soon")
        total = g.upcoming_total(today, 30)

        status_bits: list[ft.Control] = []
        if overdue:
            status_bits.append(ui.chip(f"{overdue} overdue", icon=ft.Icons.ERROR_OUTLINE,
                                       color=C.DANGER))
        if soon:
            status_bits.append(ui.chip(f"{soon} due soon", icon=ft.Icons.SCHEDULE,
                                       color=C.ACCENT))
        if rows and not (overdue or soon):
            status_bits.append(ui.chip("All on track", icon=ft.Icons.TASK_ALT, color=C.SUCCESS))
        summary = common.card(ft.Column([
            ft.Text("Due in the next 30 days", size=Type.LABEL, color=C.TEXT_DIM),
            ft.Text(ui.peso(total), size=Type.DISPLAY, weight=ft.FontWeight.W_900,
                    color=C.TEXT),
            ft.Row(status_bits, spacing=Space.SM, wrap=True, run_spacing=Space.XS),
            common.hint("Paying a bill earns Steward XP."),
        ], spacing=Space.XS, tight=True))

        items: list[ft.Control] = [summary]
        active = [r for r in rows if r[1] != "paid"]
        paid = [r for r in rows if r[1] == "paid"]
        items.append(ui.SectionHeader("Bills", count=len(active)))
        if not rows:
            items.append(ui.EmptyState(
                "No bills yet", "Add one and we'll keep an eye on due dates for you.",
                icon=ft.Icons.RECEIPT_LONG, color=C.ACCENT, action_text="Add a bill",
                on_action=self._open_add))
        elif not active:
            items.append(ui.EmptyState("All paid up!", "Nice work, Steward. Nothing due.",
                                       icon=ft.Icons.TASK_ALT, color=C.SUCCESS))
        items += [self._row(b, s, d) for b, s, d in active]
        if paid:
            arrow = ft.Icons.EXPAND_LESS if self.show_paid else ft.Icons.EXPAND_MORE
            items.append(ui.SectionHeader(
                "Paid", count=len(paid),
                trailing=ft.IconButton(arrow, on_click=self._toggle_paid, icon_color=C.TEXT_DIM,
                                       width=Size.TAP, height=Size.TAP,
                                       tooltip="Show paid bills")))
            if self.show_paid:
                items += [self._row(b, s, d) for b, s, d in paid]
        archived = g.archived_bills()
        if archived:
            items.append(ui.SectionHeader("Archived", count=len(archived)))
            items += [self._archived_row(b) for b in archived]
        if rows:
            items.append(ft.Container(common.hint("Tap a bill to edit, archive or delete it."),
                                      alignment=ft.Alignment.CENTER, padding=Space.SM))
        self.list.controls = items

    def _archived_row(self, bill: Bill) -> ft.Control:
        def restore(_: Any = None) -> None:
            self.app.game.unarchive_bill(bill.id)
            self.app.save()
            self.app.update_badges()
            self._refresh()
            self.app.toast(f"{bill.name} is back on your list", ft.Icons.UNARCHIVE)

        paid = len(bill.paid)
        return ft.Container(ft.Row([
            ft.Icon(ft.Icons.ARCHIVE, color=C.TEXT_DIM, size=20),
            ft.Column([ft.Text(bill.name, size=Type.BODY, color=C.TEXT_DIM,
                               weight=ft.FontWeight.W_600),
                       common.hint(f"{ui.peso(bill.amount)} · paid {paid}x · history kept")],
                      spacing=0, expand=True, tight=True),
            ft.TextButton("Restore", icon=ft.Icons.UNARCHIVE, height=Size.TAP,
                          on_click=common.with_sound(restore)),
        ], spacing=Space.MD, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            bgcolor=C.SURFACE, border_radius=Radius.MD,
            padding=ft.Padding.symmetric(horizontal=Space.MD, vertical=Space.XS))

    def _refresh(self) -> None:
        if self.app.showing("bills"):
            self.render()
            ui.refresh(self.list)

    def _row(self, bill: Bill, status: str, due: date) -> ui.BillRow:
        today = self.app.today()
        if status == "paid" and bill.repeat != "none":
            label = f"Next {common.short_date(due)}"
        else:
            label = common.due_label(status, due, today)
        return ui.BillRow(bill.name, bill.amount, status=status, due_label=label,
                          repeat_label=common.REPEAT_LABELS.get(bill.repeat),
                          on_pay=lambda row, bid=bill.id: self._pay(bid),
                          on_click=lambda e, bid=bill.id: editors.edit_bill(
                              self.app, bid, self._refresh),
                          data=bill.id)

    def _toggle_paid(self, _: Any = None) -> None:
        self.show_paid = not self.show_paid
        self.render()
        ui.refresh(self.list)

    # ------------------------------------------------------------------ actions
    async def _pay(self, bill_id: str) -> bool:
        g, today = self.app.game, self.app.today()
        bill = g.bill(bill_id)
        c = await self.app.award(lambda: g.mark_bill_paid(bill_id, today),
                                 line=lambda c: voice.say("bill_paid", bill=bill.name, xp=c.xp))
        if not (c.xp or c.coins):  # award() announces paid bills that earned XP
            self.app.lumen("bill_marked", ft.Icons.TASK_ALT, bill=bill.name)
        self.app.update_badges()
        await asyncio.sleep(0.5)  # let the row show "Paid", then re-sort (repeats move on)
        if self.app.showing("bills"):
            self.render()
            ui.refresh(self.list)
        return True

    def _open_add(self, _: Any = None) -> None:
        app, today = self.app, self.app.today()
        state: dict[str, Any] = {"due": today + timedelta(days=7), "repeat": "monthly"}
        name = common.text_field("Bill name (e.g. Meralco)", autofocus=True)
        amount = common.text_field("Amount", number=True, prefix="₱ ")
        note = common.text_field("Note (optional)")
        due_text = ft.Text(self._date_text(state["due"]), size=Type.BODY, color=C.TEXT,
                           weight=ft.FontWeight.W_600)

        def picked(e: Any) -> None:
            v = e.control.value
            if v is not None:
                state["due"] = common.local_date(v)
                due_text.value = self._date_text(state["due"])
                due_text.update()

        picker = ft.DatePicker(value=state["due"], first_date=today - timedelta(days=365),
                               last_date=today + timedelta(days=365 * 3), on_change=picked,
                               help_text="Next due date")
        due_btn = ft.Container(
            ft.Row([ft.Icon(ft.Icons.EVENT, color=C.PRIMARY), ft.Text("Due", color=C.TEXT_DIM),
                    ft.Container(expand=True), due_text,
                    ft.Icon(ft.Icons.EDIT_CALENDAR, color=C.TEXT_DIM, size=18)],
                   spacing=Space.SM, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            height=Size.TAP + 8, bgcolor=C.SURFACE_HI, border_radius=Radius.SM,
            padding=ft.Padding.symmetric(horizontal=Space.MD), ink=True,
            on_click=lambda e: app.page.show_dialog(picker),
        )
        repeat = common.segmented([("none", "Once"), ("weekly", "Weekly"),
                                   ("monthly", "Monthly"), ("yearly", "Yearly")], "monthly",
                                  on_change=lambda v: state.update(repeat=v))

        def add(_: Any = None) -> None:
            n = (name.value or "").strip()
            try:
                amt = float((amount.value or "").replace(",", "").replace("₱", "").strip())
            except ValueError:
                amt = -1
            name.error_text = None if n else "Give it a name"
            amount.error_text = None if amt >= 0 else "Enter an amount, like 1500"
            if not n or amt < 0:
                sfx.play("error_soft")
                name.update()
                amount.update()
                return
            app.game.add_bill(n, amt, state["due"], state["repeat"],
                              note=(note.value or "").strip())
            app.save()
            common.close(sheet)
            app.update_badges()
            self.render()
            ui.refresh(self.list)
            app.toast(f"Added {n} · {ui.peso(amt)}", ft.Icons.RECEIPT_LONG)

        sheet = common.open_sheet(app.page, "New bill", [
            name, amount, due_btn, common.hint("Repeats"),
            ft.Row([repeat], scroll=ft.ScrollMode.HIDDEN), note,
            common.hint("Amount, due date and repeat are fixed once the bill is added."),
            ft.Row([common.primary_button("Add bill", add, icon=ft.Icons.ADD)]),
        ])

    @staticmethod
    def _date_text(d: date) -> str:
        return f"{d:%a}, {d:%b} {d.day}, {d.year}"
