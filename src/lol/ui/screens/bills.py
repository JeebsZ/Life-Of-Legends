"""Finance Hub (Bills, Expenses, Receipt Scanner & Splitwise-style Split Bills).

Empowered by the Steward Path (Financial Discipline & Resourcefulness).
Includes:
- Global Currency selector (₱, $, €, £, ¥, ₹, ₩, A$, C$, S$)
- Upcoming Recurring Bills (30-day forecast, one-tap pay)
- Variable Expense Tracker (Log manually or scan receipts)
- Splitwise-style Split Bill engine:
  - Smart Receipt OCR amount extraction (Free daily quota + rewarded ad gate)
  - Split evenly in the middle OR separate amounts per person / by item (with optional names)
  - Upload & display global payment QR code (PayPal, Venmo, Cash App, GCash, Maya, PayNow, Bank QR)
  - Member payment check-off with celebratory Steward XP & coin rewards
- Ceiling ceremonial animations, haptics, and sound effects!
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

import flet as ft

from lol.core import storage
from lol.core.finance import (
    DEFAULT_SAVINGS_APY,
    EXPENSE_CATEGORIES,
    ExpenseEntry,
    SavingsGoal,
    SplitBill,
    SplitMember,
    create_savings_goal,
    create_split_bill,
    extract_receipt_total,
)
from lol.core.models import Bill
from lol.ui import ads, ocr, sfx, voice
from lol.ui import components as ui
from lol.ui.screens import common, editors
from lol.ui.screens.meal import capture, pick_image
from lol.ui.theme import C, Radius, Size, Space, Type

if TYPE_CHECKING:
    from lol.ui.app import App


def _clean_amount(val: str | None) -> float:
    if not val:
        return 0.0
    cleaned = val
    for sym in ("₱", "$", "€", "£", "¥", "₹", "₩", "A$", "C$", "S$", ","):
        cleaned = cleaned.replace(sym, "")
    try:
        return float(cleaned.strip() or "0")
    except ValueError:
        return 0.0


class BillsScreen:
    title = "Finance & Bills"

    def __init__(self, app: App) -> None:
        self.app = app
        self.active_tab = "split"  # "split" | "bills" | "expenses"
        self.show_paid = False
        self.list = common.screen_list()
        self.view = ft.Container(self.list, expand=True, key="bills")
        self.fab = ft.FloatingActionButton(
            icon=ft.Icons.ADD,
            on_click=self._on_fab,
            bgcolor=C.PRIMARY,
            foreground_color=C.ON_PRIMARY,
            tooltip="Add",
        )

    def _on_fab(self, _: Any = None) -> None:
        if self.active_tab == "split":
            self._open_split_builder()
        elif self.active_tab == "expenses":
            self._open_add_expense()
        elif self.active_tab == "savings":
            self._open_add_savings_goal()
        else:
            self._open_add_bill()

    # ------------------------------------------------------------------ render
    def render(self) -> None:
        ui.set_currency(getattr(self.app.game.profile, "currency", "₱"))
        sym = ui.currency_symbol()

        # Mode Selector Pills: Split Bills | Regular Bills | Expenses | Savings + Currency chip
        tabs = [
            ("split", "Split Bills", ft.Icons.CALL_SPLIT),
            ("bills", "Fixed Bills", ft.Icons.RECEIPT_LONG),
            ("expenses", "Expenses", ft.Icons.SHOPPING_BAG),
            ("savings", "Savings Vault", ft.Icons.SAVINGS),
        ]
        pill_controls: list[ft.Control] = []
        for key, label, icon in tabs:
            on = key == self.active_tab
            pill = ft.Container(
                ft.Row(
                    [
                        ft.Icon(icon, size=15, color=C.PRIMARY if on else C.TEXT_DIM),
                        ft.Text(
                            label,
                            size=Type.CAPTION,
                            weight=ft.FontWeight.BOLD if on else ft.FontWeight.W_500,
                            color=C.PRIMARY if on else C.TEXT_DIM,
                        ),
                    ],
                    spacing=4,
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
                padding=ft.Padding.symmetric(horizontal=Space.SM + 2, vertical=Space.XS + 2),
                bgcolor=C.a(C.PRIMARY, 0.16) if on else C.a(C.SURFACE_HI, 0.6),
                border=ft.Border.all(1.5 if on else 1, C.PRIMARY if on else C.a(C.TEXT_DIM, 0.2)),
                border_radius=Radius.PILL,
                ink=True,
                on_click=lambda e, k=key: self._switch_tab(k),
            )
            pill_controls.append(pill)

        # Global Currency Selector Chip
        curr_chip = ft.Container(
            ft.Row(
                [
                    ft.Icon(ft.Icons.LANGUAGE, size=14, color=C.GOLD),
                    ft.Text(sym, size=Type.CAPTION, weight=ft.FontWeight.W_900, color=C.GOLD),
                ],
                spacing=3,
                tight=True,
            ),
            padding=ft.Padding.symmetric(horizontal=10, vertical=Space.XS + 2),
            bgcolor=C.a(C.GOLD, 0.14),
            border=ft.Border.all(1, C.a(C.GOLD, 0.45)),
            border_radius=Radius.PILL,
            ink=True,
            tooltip="Change currency symbol",
            on_click=self._open_currency_picker,
        )
        pill_controls.append(curr_chip)

        tab_row = ft.Row(
            pill_controls,
            spacing=Space.XS,
            alignment=ft.MainAxisAlignment.CENTER,
            scroll=ft.ScrollMode.HIDDEN,
        )

        items: list[ft.Control] = [tab_row]

        if self.active_tab == "split":
            items.extend(self._render_split_section())
        elif self.active_tab == "expenses":
            items.extend(self._render_expense_section())
        elif self.active_tab == "savings":
            items.extend(self._render_savings_section())
        else:
            items.extend(self._render_bills_section())

        self.list.controls = items

    def _switch_tab(self, key: str) -> None:
        self.active_tab = key
        sfx.play("tab_open")
        self.render()
        ui.refresh(self.list)

    def _open_currency_picker(self, _: Any = None) -> None:
        cur = getattr(self.app.game.profile, "currency", "₱")
        sheet_ref: list[ft.BottomSheet] = []

        def pick_cur(sym: str) -> None:
            self.app.game.profile.currency = sym
            ui.set_currency(sym)
            self.app.save()
            if sheet_ref:
                common.close(sheet_ref[0])
            sfx.play("toggle")
            self.app.toast(f"Currency set to {sym}", ft.Icons.CURRENCY_EXCHANGE)
            self.render()
            ui.refresh(self.list)

        chips = [
            ft.Container(
                ft.Text(
                    label,
                    size=Type.BODY,
                    weight=ft.FontWeight.BOLD,
                    color=C.ON_PRIMARY if sym == cur else C.TEXT,
                ),
                bgcolor=C.PRIMARY if sym == cur else C.SURFACE_HI,
                border_radius=Radius.PILL,
                padding=ft.Padding.symmetric(horizontal=14, vertical=8),
                ink=True,
                on_click=lambda e, s=sym: pick_cur(s),
            )
            for sym, label in ui.CURRENCIES
        ]
        sheet_ref.append(
            common.open_sheet(
                self.app.page,
                "Currency Symbol",
                [
                    common.hint("Choose your currency symbol for bills, splits, and expenses."),
                    ft.Row(chips, wrap=True, spacing=Space.XS, run_spacing=Space.XS),
                ],
            )
        )

    # =========================================================================
    # SECTION 1: SPLIT BILLS (Splitwise-style)
    # =========================================================================
    def _render_split_section(self) -> list[ft.Control]:
        g = self.app.game
        splits: list[SplitBill] = getattr(g.data, "split_bills", []) or []

        unsettled = [b for b in splits if not b.settled]
        settled = [b for b in splits if b.settled]

        total_due_to_me = sum(b.amount_remaining for b in unsettled)

        banner = common.card(
            ft.Row(
                [
                    ft.Container(
                        ft.Icon(ft.Icons.CALL_SPLIT, color=C.GOLD, size=28),
                        width=48,
                        height=48,
                        shape=ft.BoxShape.CIRCLE,
                        bgcolor=C.a(C.GOLD, 0.16),
                        alignment=ft.Alignment.CENTER,
                    ),
                    ft.Column(
                        [
                            ft.Text("To Collect", size=Type.CAPTION, color=C.TEXT_DIM),
                            ft.Text(ui.peso(total_due_to_me), size=Type.TITLE, weight=ft.FontWeight.W_900, color=C.TEXT),
                            ft.Text(f"{len(unsettled)} active split{'s' if len(unsettled) != 1 else ''}", size=Type.CAPTION, color=C.PRIMARY),
                        ],
                        spacing=1,
                        expand=True,
                        tight=True,
                    ),
                    common.primary_button(
                        "Split Bill",
                        lambda _: self._open_split_builder(),
                        icon=ft.Icons.RECEIPT,
                        expand=False,
                    ),
                ],
                spacing=Space.SM,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=Space.MD,
        )

        out: list[ft.Control] = [banner]

        # Global Payment QR code status/uploader
        saved_qr = getattr(g.data, "saved_qr_path", "")
        qr_exists = bool(saved_qr and Path(saved_qr).exists())
        qr_hint = "Payment QR ready to scan" if qr_exists else "PayPal, Venmo, Cash App, GCash, Bank QR"
        qr_row = common.card(
            ft.Row(
                [
                    ft.Icon(ft.Icons.QR_CODE_2, color=C.GOLD if qr_exists else C.TEXT_DIM, size=24),
                    ft.Column(
                        [
                            ft.Text("Your Payment QR", size=Type.BODY, weight=ft.FontWeight.BOLD, color=C.TEXT),
                            ft.Text(qr_hint, size=Type.CAPTION, color=C.TEXT_DIM),
                        ],
                        spacing=0,
                        expand=True,
                        tight=True,
                    ),
                    common.secondary_button(
                        "Change QR" if qr_exists else "Upload QR",
                        lambda _: self.app.page.run_task(self._upload_saved_qr),
                        icon=ft.Icons.UPLOAD,
                        expand=False,
                    ),
                ],
                spacing=Space.SM,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=Space.MD,
        )
        out.append(qr_row)

        out.append(ui.SectionHeader("Active Split Bills", count=len(unsettled)))
        if not unsettled:
            out.append(
                ui.EmptyState(
                    "No active split bills",
                    "Snap a receipt or split evenly / by item in seconds.",
                    icon=ft.Icons.CALL_SPLIT,
                    color=C.GOLD,
                    action_text="New Split Bill",
                    on_action=lambda e: self._open_split_builder(),
                )
            )
        else:
            out.extend([self._split_bill_card(b) for b in unsettled])

        if settled:
            out.append(ui.SectionHeader("Settled Split Bills", count=len(settled)))
            out.extend([self._split_bill_card(b) for b in settled])

        return out

    def _split_bill_card(self, b: SplitBill) -> ft.Control:
        paid_cnt = b.paid_count
        total_cnt = b.total_members
        pct = (paid_cnt / total_cnt) if total_cnt > 0 else 1.0

        bar = ft.ProgressBar(
            value=pct,
            color=C.SUCCESS if b.settled else C.GOLD,
            bgcolor=C.a(C.TEXT, 0.1),
            height=6,
            border_radius=Radius.PILL,
        )

        member_chips = []
        for m in b.members:
            m_col = C.SUCCESS if m.paid else C.GOLD
            m_icon = ft.Icons.CHECK_CIRCLE if m.paid else ft.Icons.PENDING
            chip = ft.Container(
                ft.Row(
                    [
                        ft.Icon(m_icon, size=14, color=m_col),
                        ft.Text(f"{m.name}: {ui.peso(m.amount)}", size=Type.CAPTION, weight=ft.FontWeight.W_600, color=C.TEXT),
                    ],
                    spacing=4,
                    tight=True,
                ),
                padding=ft.Padding.symmetric(horizontal=8, vertical=4),
                bgcolor=C.a(m_col, 0.12),
                border=ft.Border.all(1, C.a(m_col, 0.4)),
                border_radius=Radius.PILL,
                on_click=lambda e, bill=b, mem=m: self._toggle_member_paid(bill, mem),
                tooltip="Tap to toggle paid / unpaid",
            )
            member_chips.append(chip)

        status_text = "✓ FULLY SETTLED" if b.settled else f"Collected: {ui.peso(b.amount_collected)} · Left: {ui.peso(b.amount_remaining)}"
        mode_tag = "By Item" if b.split_mode == "custom" else "Even Split"

        card_content = ft.Column(
            [
                ft.Row(
                    [
                        ft.Icon(ft.Icons.RECEIPT, color=C.GOLD, size=24),
                        ft.Column(
                            [
                                ft.Text(b.title, size=Type.BODY, weight=ft.FontWeight.BOLD, color=C.TEXT),
                                ft.Text(
                                    f"{b.date} · {ui.peso(b.total_amount)} ({total_cnt} people · {mode_tag})",
                                    size=Type.CAPTION,
                                    color=C.TEXT_DIM,
                                ),
                            ],
                            spacing=0,
                            expand=True,
                            tight=True,
                        ),
                        common.secondary_button(
                            "QR",
                            lambda _, bill=b: self._show_qr_modal(bill),
                            icon=ft.Icons.QR_CODE,
                            expand=False,
                        ),
                    ],
                    spacing=Space.SM,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                bar,
                ft.Text(status_text, size=Type.CAPTION, color=C.SUCCESS if b.settled else C.GOLD, weight=ft.FontWeight.W_700),
                ft.Row(member_chips, wrap=True, spacing=Space.XS, run_spacing=Space.XS),
            ],
            spacing=Space.SM,
            tight=True,
        )

        return common.card(card_content, padding=Space.MD)

    def _toggle_member_paid(self, bill: SplitBill, member: SplitMember) -> None:
        member.paid = not member.paid
        member.paid_at = self.app.today().isoformat() if member.paid else ""

        all_done_before = bill.settled
        bill.settled = bill.is_all_paid

        if bill.settled and not bill.rewarded:
            bill.rewarded = True
            sfx.play("milestone")
            self.app.space.pulse(C.GOLD, 1.2)
            self.app.page.run_task(ui.buzz, "heavy")

            async def _reward_task() -> None:
                await self.app.award(
                    lambda: self.app.game.award_direct(
                        path_id="steward",
                        xp=60,
                        coins=15,
                        note=f"Split Bill Settled: {bill.title}",
                    ),
                    lambda c: f"Steward Mastery! {bill.title} settled! +{c.xp} XP +{c.coins} Coins",
                    stinger="chain_complete",
                )
                await self.app.fx_seal.show(
                    "TRANSACTION SETTLED",
                    f"{bill.title} · {ui.peso(bill.total_amount)} collected",
                    eyebrow="STEWARD TRIUMPH",
                    color=C.GOLD,
                )

            self.app.page.run_task(_reward_task)
        elif not all_done_before:
            sfx.play("coin")
            self.app.page.run_task(ui.buzz, "light")

        self.app.save()
        self.render()
        ui.refresh(self.list)

    def _show_qr_modal(self, bill: SplitBill) -> None:
        g = self.app.game
        qr_path = bill.qr_image_path or getattr(g.data, "saved_qr_path", "")
        qr_exists = bool(qr_path and Path(qr_path).exists())
        sheet_ref: list[ft.BottomSheet] = []

        if bill.split_mode == "custom":
            share_str = " · ".join(f"{m.name}: {ui.peso(m.amount)}" for m in bill.members)
            share_header = ft.Text(share_str, size=Type.BODY, weight=ft.FontWeight.BOLD, color=C.GOLD, text_align=ft.TextAlign.CENTER)
        else:
            per_person = bill.total_amount / max(1, bill.total_members)
            share_header = ft.Text(f"Share: {ui.peso(per_person)} each", size=Type.HEADLINE, weight=ft.FontWeight.BOLD, color=C.GOLD, text_align=ft.TextAlign.CENTER)

        async def upload_and_reopen(_: Any = None) -> None:
            if sheet_ref:
                common.close(sheet_ref[0])
            await self._upload_saved_qr()
            self._show_qr_modal(bill)

        img_box: ft.Control
        if qr_exists:
            img_box = ft.Container(
                ft.Image(src=qr_path, width=230, height=230, fit=ft.BoxFit.CONTAIN),
                alignment=ft.Alignment.CENTER,
                bgcolor=ft.Colors.WHITE,
                border_radius=Radius.MD,
                padding=Space.SM,
            )
        else:
            img_box = ft.Container(
                ft.Column(
                    [
                        ft.Icon(ft.Icons.QR_CODE_2, size=56, color=C.TEXT_DIM),
                        ft.Text("No payment QR uploaded yet.", size=Type.BODY, color=C.TEXT_DIM),
                        common.secondary_button(
                            "Upload Payment QR",
                            lambda _: self.app.page.run_task(upload_and_reopen),
                            icon=ft.Icons.UPLOAD,
                        ),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    alignment=ft.MainAxisAlignment.CENTER,
                    spacing=Space.SM,
                ),
                height=180,
                alignment=ft.Alignment.CENTER,
            )

        body = ft.Column(
            [
                share_header,
                img_box,
                ft.Text(
                    "Scan with PayPal, Venmo, Cash App, GCash, PayNow, or your banking app.",
                    size=Type.CAPTION,
                    color=C.TEXT_DIM,
                    text_align=ft.TextAlign.CENTER,
                ),
                common.primary_button(
                    "Done",
                    lambda _: common.close(sheet_ref[0]) if sheet_ref else None,
                    icon=ft.Icons.CHECK,
                ),
            ],
            spacing=Space.MD,
            tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )
        sheet_ref.append(common.open_sheet(self.app.page, f"Scan to Pay: {bill.title}", [body]))

    async def _upload_saved_qr(self, _: Any = None) -> None:
        raw = await pick_image(self.app)
        if not raw:
            return
        dest = storage.data_dir() / "saved_payment_qr.png"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(raw)
        self.app.game.data.saved_qr_path = str(dest)
        self.app.save()
        sfx.play("milestone")
        self.app.toast("Payment QR saved locally!", ft.Icons.QR_CODE)
        self.render()
        ui.refresh(self.list)

    async def _scan_receipt_bytes(self) -> tuple[float | None, str | None]:
        """Check free daily OCR quota / rewarded ad gate, and scan receipt via Camera or Photo Picker."""
        allowed = await ads.limit_gate(self.app, "note_scan")
        if not allowed:
            return None, None
        raw = await capture(self.app)
        if not raw:
            return None, None
        ads.spend(self.app, "note_scan")
        tmp_path = storage.data_dir() / "receipt_scan_tmp.jpg"
        tmp_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path.write_bytes(raw)
        rec = ocr.recognizer_for(self.app.page)
        text = await rec.recognize_async(str(tmp_path))
        return extract_receipt_total(text), str(tmp_path)

    def _open_split_builder(self) -> None:
        """Open the interactive split bill creator with Equal & By-Item/Person modes."""
        sym = ui.currency_symbol()
        state: dict[str, Any] = {
            "title": "",
            "total": 0.0,
            "people": 3,
            "mode": "equal",  # "equal" | "custom"
            "names": ["Me", "Person 2", "Person 3"],
            "custom_amounts": [0.0, 0.0, 0.0],
            "receipt_path": None,
        }
        sheet_ref: list[ft.BottomSheet] = []

        title_field = common.text_field("Bill title (e.g. Dinner, Groceries)", autofocus=True)
        total_field = common.text_field(f"Total Amount ({sym})", number=True, prefix=f"{sym} ")

        people_label = ft.Text("3 People", size=Type.BODY, weight=ft.FontWeight.BOLD, color=C.TEXT)
        share_label = ft.Text(f"Share: {ui.peso(0)} each", size=Type.TITLE, weight=ft.FontWeight.W_900, color=C.GOLD)

        members_container = ft.Column(spacing=Space.XS, tight=True)

        def sync_member_rows() -> None:
            members_container.controls.clear()
            cnt = state["people"]
            while len(state["names"]) < cnt:
                state["names"].append(f"Person {len(state['names']) + 1}")
            while len(state["custom_amounts"]) < cnt:
                state["custom_amounts"].append(0.0)

            is_custom = state["mode"] == "custom"
            for i in range(cnt):
                name_tf = common.text_field(f"Person {i + 1} name (optional)")
                name_tf.value = state["names"][i]

                def make_name_ch(idx: int, tf: ft.TextField):
                    def _nch(_: Any) -> None:
                        state["names"][idx] = (tf.value or "").strip() or f"Person {idx + 1}"
                    return _nch

                name_tf.on_change = make_name_ch(i, name_tf)

                row_children: list[ft.Control] = [
                    ft.Icon(ft.Icons.PERSON, size=18, color=C.PRIMARY if i == 0 else C.TEXT_DIM),
                    ft.Container(name_tf, expand=True),
                ]

                if is_custom:
                    cur_v = state["custom_amounts"][i]
                    val_field = common.text_field("Item/Share", number=True, prefix=f"{sym} ")
                    val_field.value = f"{cur_v:.2f}" if cur_v > 0 else ""

                    def make_amt_ch(idx: int, vf: ft.TextField):
                        def _ch(_: Any) -> None:
                            state["custom_amounts"][idx] = _clean_amount(vf.value)
                            total_sum = sum(state["custom_amounts"][: state["people"]])
                            share_label.value = f"Allocated: {ui.peso(total_sum)} / {ui.peso(state['total'])}"
                            ui.refresh(share_label)
                        return _ch

                    val_field.on_change = make_amt_ch(i, val_field)
                    row_children.append(ft.Container(val_field, width=125))

                members_container.controls.append(
                    ft.Row(
                        row_children,
                        spacing=Space.XS,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    )
                )

        equal_pill = ft.Container(
            ft.Text("Split Evenly", size=Type.CAPTION, weight=ft.FontWeight.BOLD, color=C.PRIMARY),
            padding=ft.Padding.symmetric(horizontal=12, vertical=6),
            border_radius=Radius.PILL,
            bgcolor=C.a(C.PRIMARY, 0.2),
            border=ft.Border.all(1.5, C.PRIMARY),
            ink=True,
            on_click=lambda _: set_mode("equal"),
        )
        custom_pill = ft.Container(
            ft.Text("Separate / By Item", size=Type.CAPTION, weight=ft.FontWeight.BOLD, color=C.TEXT_DIM),
            padding=ft.Padding.symmetric(horizontal=12, vertical=6),
            border_radius=Radius.PILL,
            bgcolor=C.a(C.SURFACE_HI, 0.5),
            border=ft.Border.all(1, C.OUTLINE),
            ink=True,
            on_click=lambda _: set_mode("custom"),
        )
        mode_selector = ft.Row(
            [equal_pill, custom_pill],
            spacing=Space.SM,
            alignment=ft.MainAxisAlignment.CENTER,
        )

        def set_mode(m: str) -> None:
            sfx.play("toggle")
            state["mode"] = m
            is_eq = m == "equal"
            equal_pill.bgcolor = C.a(C.PRIMARY, 0.2) if is_eq else C.a(C.SURFACE_HI, 0.5)
            equal_pill.border = ft.Border.all(1.5 if is_eq else 1, C.PRIMARY if is_eq else C.OUTLINE)
            equal_pill.content.color = C.PRIMARY if is_eq else C.TEXT_DIM

            custom_pill.bgcolor = C.a(C.PRIMARY, 0.2) if not is_eq else C.a(C.SURFACE_HI, 0.5)
            custom_pill.border = ft.Border.all(1.5 if not is_eq else 1, C.PRIMARY if not is_eq else C.OUTLINE)
            custom_pill.content.color = C.PRIMARY if not is_eq else C.TEXT_DIM

            sync_member_rows()
            recalc()
            ui.refresh(members_container, mode_selector)

        def recalc() -> None:
            amt = _clean_amount(total_field.value)
            state["total"] = amt
            cnt = state["people"]

            if state["mode"] == "custom":
                total_sum = sum(state["custom_amounts"][:cnt])
                share_label.value = f"Allocated: {ui.peso(total_sum)} / {ui.peso(amt)}"
            else:
                per = (amt / cnt) if cnt > 0 else 0.0
                share_label.value = f"Share: {ui.peso(per)} each"
            ui.refresh(share_label, people_label)

        total_field.on_change = lambda _: recalc()

        def change_people(delta: int) -> None:
            sfx.play("tap")
            new_cnt = max(2, min(20, state["people"] + delta))
            state["people"] = new_cnt
            people_label.value = f"{new_cnt} People"
            sync_member_rows()
            recalc()
            ui.refresh(members_container)

        btn_minus = ft.IconButton(ft.Icons.REMOVE_CIRCLE_OUTLINE, on_click=lambda _: change_people(-1), icon_color=C.PRIMARY)
        btn_plus = ft.IconButton(ft.Icons.ADD_CIRCLE_OUTLINE, on_click=lambda _: change_people(1), icon_color=C.PRIMARY)

        scan_status = ft.Text("", size=Type.CAPTION, color=C.PRIMARY)

        async def scan_receipt(_: Any = None) -> None:
            scan_status.value = "Starting scanner..."
            scan_status.color = C.PRIMARY
            ui.refresh(scan_status)
            try:
                total, f_path = await self._scan_receipt_bytes()
            except Exception as exc:  # noqa: BLE001
                scan_status.value = f"Scanner error: {exc}"
                scan_status.color = C.DANGER
                ui.refresh(scan_status)
                return

            if total is not None:
                total_field.value = f"{total:.2f}"
                state["receipt_path"] = f_path
                scan_status.value = f"✓ Scanned Total: {ui.peso(total)} (Confirm or edit below)"
                scan_status.color = C.SUCCESS
                sfx.play("milestone")
                recalc()
            elif f_path:
                state["receipt_path"] = f_path
                scan_status.value = "Receipt captured — please enter amount manually below."
                scan_status.color = C.ACCENT
            else:
                scan_status.value = ""
            ui.refresh(scan_status, total_field)

        scan_btn = common.secondary_button(
            "Scan Receipt",
            lambda _: self.app.page.run_task(scan_receipt),
            icon=ft.Icons.DOCUMENT_SCANNER,
            expand=False,
        )

        def save_split(_: Any = None) -> None:
            t = (title_field.value or "").strip() or "Group Split Bill"
            amt = _clean_amount(total_field.value)
            cnt = state["people"]
            custom_list = state["custom_amounts"][:cnt] if state["mode"] == "custom" else None
            final_total = sum(custom_list) if (custom_list and sum(custom_list) > 0) else amt

            if final_total <= 0:
                sfx.play("error_soft")
                total_field.error_text = "Enter a valid total amount"
                total_field.update()
                return

            split_id = f"sb_{self.app.game.data.next_id}"
            self.app.game.data.next_id += 1

            split_obj = create_split_bill(
                bill_id=split_id,
                title=t,
                total=final_total,
                num_people=cnt,
                names=state["names"][:cnt],
                qr_image_path=getattr(self.app.game.data, "saved_qr_path", None),
                custom_amounts=custom_list if (custom_list and sum(custom_list) > 0) else None,
                receipt_photo=state["receipt_path"],
                today_str=self.app.today().isoformat(),
            )

            if not hasattr(self.app.game.data, "split_bills"):
                self.app.game.data.split_bills = []
            self.app.game.data.split_bills.insert(0, split_obj)
            self.app.save()

            if sheet_ref:
                common.close(sheet_ref[0])
            sfx.play("coin_many")
            self.app.toast(f"Split created: {ui.peso(final_total)} ({cnt} people)", ft.Icons.CALL_SPLIT)
            self.render()
            ui.refresh(self.list)

        sync_member_rows()
        sheet_ref.append(
            common.open_sheet(
                self.app.page,
                "New Split Bill",
                [
                    common.hint("Split evenly in the middle or enter separate item amounts per person."),
                    title_field,
                    ft.Row([ft.Container(total_field, expand=True), scan_btn], spacing=Space.SM, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    scan_status,
                    mode_selector,
                    common.card(
                        ft.Column(
                            [
                                ft.Row(
                                    [
                                        ft.Text("People", size=Type.BODY, weight=ft.FontWeight.BOLD, color=C.TEXT),
                                        ft.Container(expand=True),
                                        btn_minus,
                                        people_label,
                                        btn_plus,
                                    ],
                                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                ),
                                share_label,
                                members_container,
                            ],
                            spacing=Space.SM,
                            tight=True,
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        padding=Space.MD,
                    ),
                    common.primary_button("Create Split Bill", save_split, icon=ft.Icons.CHECK),
                ],
            )
        )

    # =========================================================================
    # SECTION 2: EXPENSE TRACKER
    # =========================================================================
    def _render_expense_section(self) -> list[ft.Control]:
        g, today = self.app.game, self.app.today()
        expenses: list[ExpenseEntry] = getattr(g.data, "expenses", []) or []

        cur_month = f"{today.year}-{today.month:02d}"
        this_month_exp = [e for e in expenses if e.date.startswith(cur_month)]
        month_total = sum(e.amount for e in this_month_exp)

        summary = common.card(
            ft.Row(
                [
                    ft.Container(
                        ft.Icon(ft.Icons.SHOPPING_BAG, color=C.PRIMARY, size=28),
                        width=48,
                        height=48,
                        shape=ft.BoxShape.CIRCLE,
                        bgcolor=C.a(C.PRIMARY, 0.16),
                        alignment=ft.Alignment.CENTER,
                    ),
                    ft.Column(
                        [
                            ft.Text("Spent This Month", size=Type.CAPTION, color=C.TEXT_DIM),
                            ft.Text(ui.peso(month_total), size=Type.TITLE, weight=ft.FontWeight.W_900, color=C.TEXT),
                            ft.Text(f"{len(this_month_exp)} transaction{'s' if len(this_month_exp) != 1 else ''}", size=Type.CAPTION, color=C.TEXT_DIM),
                        ],
                        spacing=1,
                        expand=True,
                        tight=True,
                    ),
                    common.primary_button(
                        "Add Expense",
                        lambda _: self._open_add_expense(),
                        icon=ft.Icons.ADD,
                        expand=False,
                    ),
                ],
                spacing=Space.SM,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=Space.MD,
        )

        out: list[ft.Control] = [summary]
        out.append(ui.SectionHeader("Recent Expenses", count=len(expenses)))

        if not expenses:
            out.append(
                ui.EmptyState(
                    "No expenses logged",
                    "Scan a receipt or log your daily spending in a tap.",
                    icon=ft.Icons.SHOPPING_BAG,
                    color=C.PRIMARY,
                    action_text="Add Expense",
                    on_action=lambda e: self._open_add_expense(),
                )
            )
        else:
            for exp in expenses[:30]:
                out.append(self._expense_row(exp))

        return out

    def _expense_row(self, exp: ExpenseEntry) -> ft.Control:
        return common.card(
            ft.Row(
                [
                    ft.Container(
                        ft.Icon(ft.Icons.RECEIPT, size=20, color=C.PRIMARY),
                        width=38,
                        height=38,
                        shape=ft.BoxShape.CIRCLE,
                        bgcolor=C.a(C.PRIMARY, 0.12),
                        alignment=ft.Alignment.CENTER,
                    ),
                    ft.Column(
                        [
                            ft.Text(exp.title, size=Type.BODY, weight=ft.FontWeight.BOLD, color=C.TEXT),
                            ft.Text(f"{exp.date} · {exp.category}", size=Type.CAPTION, color=C.TEXT_DIM),
                        ],
                        spacing=0,
                        expand=True,
                        tight=True,
                    ),
                    ft.Text(ui.peso(exp.amount), size=Type.BODY, weight=ft.FontWeight.W_800, color=C.TEXT),
                ],
                spacing=Space.MD,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=Space.SM + 2,
        )

    def _open_add_expense(self) -> None:
        today = self.app.today()
        sym = ui.currency_symbol()
        sheet_ref: list[ft.BottomSheet] = []
        name_field = common.text_field("Expense Title (e.g. Coffee, Lunch)", autofocus=True)
        amt_field = common.text_field("Amount", number=True, prefix=f"{sym} ")
        cat_dropdown = ft.Dropdown(
            options=[ft.dropdown.Option(c) for c in EXPENSE_CATEGORIES],
            value="Food & Dining",
            border_color=C.a(C.TEXT_DIM, 0.3),
        )

        scan_status = ft.Text("", size=Type.CAPTION, color=C.PRIMARY)

        async def scan_receipt(_: Any = None) -> None:
            scan_status.value = "Starting scanner..."
            scan_status.color = C.PRIMARY
            ui.refresh(scan_status)
            try:
                total, f_path = await self._scan_receipt_bytes()
            except Exception as exc:  # noqa: BLE001
                scan_status.value = f"Scanner error: {exc}"
                scan_status.color = C.DANGER
                ui.refresh(scan_status)
                return

            if total is not None:
                amt_field.value = f"{total:.2f}"
                scan_status.value = f"✓ Found Total: {ui.peso(total)}"
                scan_status.color = C.SUCCESS
                sfx.play("milestone")
            elif f_path:
                scan_status.value = "Receipt captured — enter amount manually."
                scan_status.color = C.ACCENT
            else:
                scan_status.value = ""
            ui.refresh(scan_status, amt_field)

        scan_btn = common.secondary_button(
            "Scan Receipt",
            lambda _: self.app.page.run_task(scan_receipt),
            icon=ft.Icons.DOCUMENT_SCANNER,
            expand=False,
        )

        def save_exp(_: Any = None) -> None:
            t = (name_field.value or "").strip() or "General Expense"
            amt = _clean_amount(amt_field.value)

            if amt <= 0:
                sfx.play("error_soft")
                amt_field.error_text = "Enter a valid amount"
                amt_field.update()
                return

            exp_id = f"exp_{self.app.game.data.next_id}"
            self.app.game.data.next_id += 1

            new_exp = ExpenseEntry(
                id=exp_id,
                title=t,
                amount=amt,
                category=cat_dropdown.value or "Food & Dining",
                date=today.isoformat(),
            )
            if not hasattr(self.app.game.data, "expenses"):
                self.app.game.data.expenses = []
            self.app.game.data.expenses.insert(0, new_exp)
            self.app.save()

            if sheet_ref:
                common.close(sheet_ref[0])
            sfx.play("coin")
            self.app.toast(f"Logged: {t} · {ui.peso(amt)}", ft.Icons.SHOPPING_BAG)
            self.render()
            ui.refresh(self.list)

        sheet_ref.append(
            common.open_sheet(
                self.app.page,
                "Log Expense",
                [
                    name_field,
                    ft.Row([ft.Container(amt_field, expand=True), scan_btn], spacing=Space.SM, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    scan_status,
                    cat_dropdown,
                    common.primary_button("Save Expense", save_exp, icon=ft.Icons.CHECK),
                ],
            )
        )

    # =========================================================================
    # SECTION 3: RECURRING FIXED BILLS (Restored from stable engine)
    # =========================================================================
    def _render_bills_section(self) -> list[ft.Control]:
        g, today = self.app.game, self.app.today()
        rows = g.bills_status(today)
        overdue = sum(1 for _, s, _ in rows if s == "overdue")
        if overdue > getattr(self, "_overdue_heard", 0):
            sfx.play("low_health", 0.6)
        self._overdue_heard = overdue
        soon = sum(1 for _, s, _ in rows if s == "due_soon")
        total = g.upcoming_total(today, 30)

        status_bits: list[ft.Control] = []
        if overdue:
            status_bits.append(ui.chip(f"{overdue} overdue", icon=ft.Icons.ERROR_OUTLINE, color=C.DANGER))
        if soon:
            status_bits.append(ui.chip(f"{soon} due soon", icon=ft.Icons.SCHEDULE, color=C.ACCENT))
        if rows and not (overdue or soon):
            status_bits.append(ui.chip("All on track", icon=ft.Icons.TASK_ALT, color=C.SUCCESS))

        summary = common.card(
            ft.Column(
                [
                    ft.Text("Due in the next 30 days", size=Type.LABEL, color=C.TEXT_DIM),
                    ft.Text(ui.peso(total), size=Type.DISPLAY, weight=ft.FontWeight.W_900, color=C.TEXT),
                    ft.Row(status_bits, spacing=Space.SM, wrap=True, run_spacing=Space.XS),
                    common.hint("Paying a bill earns Steward XP."),
                ],
                spacing=Space.XS,
                tight=True,
            )
        )

        items: list[ft.Control] = [summary]
        active = [r for r in rows if r[1] != "paid"]
        paid = [r for r in rows if r[1] == "paid"]
        items.append(ui.SectionHeader("Recurring Bills", count=len(active)))
        if not rows:
            items.append(
                ui.EmptyState(
                    "No bills yet",
                    "Add one and we'll keep an eye on due dates for you.",
                    icon=ft.Icons.RECEIPT_LONG,
                    color=C.ACCENT,
                    action_text="Add a bill",
                    on_action=self._open_add_bill,
                )
            )
        elif not active:
            items.append(
                ui.EmptyState(
                    "All paid up!",
                    "Nice work, Steward. Nothing due.",
                    icon=ft.Icons.TASK_ALT,
                    color=C.SUCCESS,
                )
            )
        items += [self._row(b, s, d) for b, s, d in active]
        if paid:
            arrow = ft.Icons.EXPAND_LESS if self.show_paid else ft.Icons.EXPAND_MORE
            items.append(
                ui.SectionHeader(
                    "Paid",
                    count=len(paid),
                    trailing=ft.IconButton(
                        arrow,
                        on_click=self._toggle_paid,
                        icon_color=C.TEXT_DIM,
                        width=Size.TAP,
                        height=Size.TAP,
                        tooltip="Show paid bills",
                    ),
                )
            )
            if self.show_paid:
                items += [self._row(b, s, d) for b, s, d in paid]
        archived = g.archived_bills()
        if archived:
            items.append(ui.SectionHeader("Archived", count=len(archived)))
            items += [self._archived_row(b) for b in archived]
        if rows:
            items.append(
                ft.Container(
                    common.hint("Tap a bill to edit, archive or delete it."),
                    alignment=ft.Alignment.CENTER,
                    padding=Space.SM,
                )
            )
        return items

    def _archived_row(self, bill: Bill) -> ft.Control:
        def restore(_: Any = None) -> None:
            self.app.game.unarchive_bill(bill.id)
            self.app.save()
            self.app.update_badges()
            self._refresh()
            self.app.toast(f"{bill.name} is back on your list", ft.Icons.UNARCHIVE)

        paid = len(bill.paid)
        return ft.Container(
            ft.Row(
                [
                    ft.Icon(ft.Icons.ARCHIVE, color=C.TEXT_DIM, size=20),
                    ft.Column(
                        [
                            ft.Text(bill.name, size=Type.BODY, color=C.TEXT_DIM, weight=ft.FontWeight.W_600),
                            common.hint(f"{ui.peso(bill.amount)} · paid {paid}x · history kept"),
                        ],
                        spacing=0,
                        expand=True,
                        tight=True,
                    ),
                    ft.TextButton(
                        "Restore",
                        icon=ft.Icons.UNARCHIVE,
                        height=Size.TAP,
                        on_click=common.with_sound(restore),
                    ),
                ],
                spacing=Space.MD,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=C.SURFACE,
            border_radius=Radius.MD,
            padding=ft.Padding.symmetric(horizontal=Space.MD, vertical=Space.XS),
        )

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
        return ui.BillRow(
            bill.name,
            bill.amount,
            status=status,
            due_label=label,
            repeat_label=common.REPEAT_LABELS.get(bill.repeat),
            note=bill.note,
            on_pay=lambda row, bid=bill.id: self._pay(bid),
            on_click=lambda e, bid=bill.id: editors.edit_bill(self.app, bid, self._refresh),
            data=bill.id,
        )

    def _toggle_paid(self, _: Any = None) -> None:
        self.show_paid = not self.show_paid
        self.render()
        ui.refresh(self.list)

    async def _pay(self, bill_id: str) -> bool:
        g, today = self.app.game, self.app.today()
        bill = g.bill(bill_id)
        c = await self.app.award(
            lambda: g.mark_bill_paid(bill_id, today),
            line=lambda c: voice.say("bill_paid", bill=bill.name, xp=c.xp),
        )
        if not (c.xp or c.coins):
            self.app.lumen("bill_marked", ft.Icons.TASK_ALT, bill=bill.name)
        self.app.update_badges()
        await asyncio.sleep(0.5)
        self._refresh()
        return True

    def _open_add_bill(self, _: Any = None) -> None:
        app, today = self.app, self.app.today()
        sym = ui.currency_symbol()
        state: dict[str, Any] = {"due": today + timedelta(days=7), "repeat": "monthly"}
        name = common.text_field("Bill name (e.g. Electric, Internet)", autofocus=True)
        amount = common.text_field("Amount", number=True, prefix=f"{sym} ")
        note = common.text_field("Note (optional)")
        due_text = ft.Text(self._date_text(state["due"]), size=Type.BODY, color=C.TEXT, weight=ft.FontWeight.W_600)

        def picked(e: Any) -> None:
            v = e.control.value
            if v is not None:
                state["due"] = common.local_date(v)
                due_text.value = self._date_text(state["due"])
                due_text.update()

        picker = ft.DatePicker(
            value=state["due"],
            first_date=today - timedelta(days=365),
            last_date=today + timedelta(days=365 * 3),
            on_change=picked,
            help_text="Next due date",
        )
        due_btn = ft.Container(
            ft.Row(
                [
                    ft.Icon(ft.Icons.EVENT, color=C.PRIMARY),
                    ft.Text("Due", color=C.TEXT_DIM),
                    ft.Container(expand=True),
                    due_text,
                    ft.Icon(ft.Icons.EDIT_CALENDAR, color=C.TEXT_DIM, size=18),
                ],
                spacing=Space.SM,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            height=Size.TAP + 8,
            bgcolor=C.SURFACE_HI,
            border_radius=Radius.SM,
            padding=ft.Padding.symmetric(horizontal=Space.MD),
            ink=True,
            on_click=lambda e: app.page.show_dialog(picker),
        )
        repeat = common.segmented(
            [("none", "Once"), ("weekly", "Weekly"), ("monthly", "Monthly"), ("yearly", "Yearly")],
            "monthly",
            on_change=lambda v: state.update(repeat=v),
        )

        def add(_: Any = None) -> None:
            n = (name.value or "").strip()
            amt = _clean_amount(amount.value) if (amount.value or "").strip() else -1.0
            name.error_text = None if n else "Give it a name"
            amount.error_text = None if amt >= 0 else "Enter an amount, like 1500"
            if not n or amt < 0:
                sfx.play("error_soft")
                name.update()
                amount.update()
                return
            app.game.add_bill(n, amt, state["due"], state["repeat"], note=(note.value or "").strip())
            app.save()
            common.close(sheet)
            app.update_badges()
            self.render()
            ui.refresh(self.list)
            app.toast(f"Added {n} · {ui.peso(amt)}", ft.Icons.RECEIPT_LONG)

        sheet = common.open_sheet(
            app.page,
            "New bill",
            [
                name,
                amount,
                due_btn,
                common.hint("Repeats"),
                ft.Row([repeat], scroll=ft.ScrollMode.HIDDEN),
                note,
                common.hint("Amount, due date and repeat are fixed once the bill is added."),
                ft.Row([common.primary_button("Add bill", add, icon=ft.Icons.ADD)]),
            ],
        )

    @staticmethod
    def _date_text(d: date) -> str:
        return f"{d:%a}, {d:%b} {d.day}, {d.year}"

    # ------------------------------------------------------------------ Savings Section
    def _render_savings_section(self) -> list[ft.Control]:
        goals: list[SavingsGoal] = getattr(self.app.game.data, "savings_goals", [])
        total_saved = sum(g.current_amount for g in goals)
        total_daily_interest = sum(g.daily_interest for g in goals)
        total_monthly_interest = sum(g.monthly_interest for g in goals)
        avg_apy = (
            (sum(g.apy_percent * g.current_amount for g in goals) / total_saved)
            if total_saved > 0
            else DEFAULT_SAVINGS_APY
        )

        # Top Summary Vault Card
        summary_col = ft.Column(
            [
                ft.Row(
                    [
                        ft.Icon(ft.Icons.SAVINGS, color=C.GOLD, size=28),
                        ft.Column(
                            [
                                ft.Text("SAVINGS VAULT", size=Type.CAPTION, weight=ft.FontWeight.BOLD, color=C.GOLD),
                                ft.Text(ui.peso(total_saved), size=Type.HEADLINE + 2, weight=ft.FontWeight.W_900, color=C.TEXT),
                            ],
                            spacing=0,
                            tight=True,
                            expand=True,
                        ),
                        common.primary_button(
                            "New Goal",
                            lambda _: self._open_add_savings_goal(),
                            icon=ft.Icons.ADD,
                            expand=False,
                        ),
                    ],
                    spacing=Space.SM,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Divider(height=1, color=C.OUTLINE),
                ft.Row(
                    [
                        ft.Container(
                            ft.Row(
                                [
                                    ft.Icon(ft.Icons.TRENDING_UP, size=16, color=C.SUCCESS),
                                    ft.Text(f"+{ui.peso(total_daily_interest)} / day", size=Type.BODY, weight=ft.FontWeight.BOLD, color=C.SUCCESS),
                                ],
                                spacing=4,
                                tight=True,
                            ),
                            padding=ft.Padding.symmetric(horizontal=8, vertical=4),
                            bgcolor=C.a(C.SUCCESS, 0.12),
                            border=ft.Border.all(1, C.a(C.SUCCESS, 0.35)),
                            border_radius=Radius.PILL,
                        ),
                        ft.Text(f"~{ui.peso(total_monthly_interest)} / mo · {avg_apy:.1f}% APY", size=Type.CAPTION, color=C.TEXT_DIM),
                    ],
                    spacing=Space.SM,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    wrap=True,
                ),
                common.hint("Daily projected growth calculated automatically (MariBank & Maya high-yield savings model)."),
            ],
            spacing=Space.SM,
            tight=True,
        )
        out: list[ft.Control] = [common.card(summary_col, padding=Space.MD)]

        if not goals:
            empty = ft.Column(
                [
                    ft.Icon(ft.Icons.SAVINGS_OUTLINED, size=48, color=C.TEXT_DIM),
                    ft.Text("No Savings Goals Yet", size=Type.TITLE, weight=ft.FontWeight.BOLD, color=C.TEXT),
                    common.hint("Set up personal savings goals (e.g. Emergency Fund, Travel, Tech Upgrade) with real-time daily projected APY growth."),
                    common.primary_button("Create Savings Goal", lambda _: self._open_add_savings_goal(), icon=ft.Icons.ADD),
                ],
                spacing=Space.SM,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                tight=True,
            )
            out.append(common.card(empty, padding=Space.LG))
            return out

        out.append(ui.SectionHeader("Active Goals", count=len(goals)))
        for g in goals:
            out.append(self._savings_goal_card(g))

        return out

    def _savings_goal_card(self, g: SavingsGoal) -> ft.Control:
        pct = min(1.0, g.progress)
        is_reached = g.is_reached

        bar = ft.ProgressBar(
            value=pct,
            color=C.SUCCESS if is_reached else C.PRIMARY,
            bgcolor=C.a(C.TEXT, 0.1),
            height=7,
            border_radius=Radius.PILL,
        )

        card_content = ft.Column(
            [
                ft.Row(
                    [
                        ft.Icon(
                            ft.Icons.SAVINGS if g.icon == "savings" else ft.Icons.ACCOUNT_BALANCE_WALLET,
                            color=C.PRIMARY,
                            size=24,
                        ),
                        ft.Column(
                            [
                                ft.Text(g.name, size=Type.BODY, weight=ft.FontWeight.BOLD, color=C.TEXT),
                                ft.Text(
                                    f"Target: {ui.peso(g.target_amount)} · {g.apy_percent:.1f}% APY",
                                    size=Type.CAPTION,
                                    color=C.TEXT_DIM,
                                ),
                            ],
                            spacing=0,
                            expand=True,
                            tight=True,
                        ),
                        ft.Text(
                            ui.peso(g.current_amount),
                            size=Type.TITLE,
                            weight=ft.FontWeight.W_900,
                            color=C.SUCCESS if is_reached else C.TEXT,
                        ),
                    ],
                    spacing=Space.SM,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                bar,
                ft.Row(
                    [
                        ft.Text(
                            f"{pct * 100:.1f}% complete",
                            size=Type.CAPTION,
                            color=C.SUCCESS if is_reached else C.TEXT_DIM,
                            weight=ft.FontWeight.BOLD,
                        ),
                        ft.Container(expand=True),
                        ft.Text(f"+{ui.peso(g.daily_interest)} / day", size=Type.CAPTION, color=C.SUCCESS, weight=ft.FontWeight.W_700),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Row(
                    [
                        common.primary_button(
                            "+ Deposit",
                            lambda _, goal=g: self._open_deposit_modal(goal),
                            icon=ft.Icons.ARROW_DOWNWARD,
                            expand=True,
                        ),
                        common.secondary_button(
                            "- Withdraw",
                            lambda _, goal=g: self._open_withdraw_modal(goal),
                            icon=ft.Icons.ARROW_UPWARD,
                            expand=True,
                        ),
                        ft.IconButton(
                            ft.Icons.MORE_VERT,
                            tooltip="Manage Goal",
                            on_click=lambda _, goal=g: self._open_goal_options(goal),
                        ),
                    ],
                    spacing=Space.SM,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ],
            spacing=Space.SM,
            tight=True,
        )
        return common.card(card_content, padding=Space.MD)

    def _open_add_savings_goal(self) -> None:
        app = self.app
        name = common.text_field("Goal Name (e.g. Emergency Fund, Japan Trip)", autofocus=False)
        target = common.text_field("Target Amount (₱)", number=True)
        current = common.text_field("Starting Deposit (₱, optional)", number=True)
        apy = common.text_field("Interest APY % (MariBank/Maya standard: 4.5%)", number=True)
        apy.value = str(DEFAULT_SAVINGS_APY)
        notes = common.text_field("Notes (optional)")

        def save_goal(_: Any = None) -> None:
            n = (name.value or "").strip()
            t_val = _clean_amount(target.value)
            c_val = _clean_amount(current.value)
            try:
                apy_val = float(apy.value.strip()) if (apy.value or "").strip() else DEFAULT_SAVINGS_APY
            except ValueError:
                apy_val = DEFAULT_SAVINGS_APY

            name.error_text = None if n else "Name is required"
            target.error_text = None if t_val > 0 else "Enter a valid target amount"
            if not n or t_val <= 0:
                sfx.play("error_soft")
                name.update()
                target.update()
                return

            new_goal = create_savings_goal(
                goal_id=app.game._new_id("sg"),
                name=n,
                target_amount=t_val,
                current_amount=c_val,
                apy_percent=apy_val,
                notes=(notes.value or "").strip(),
            )
            app.game.data.savings_goals.append(new_goal)
            app.save()
            common.close(sheet)
            sfx.play("milestone")
            self.render()
            ui.refresh(self.list)
            app.toast(f"Goal '{n}' created!", ft.Icons.SAVINGS)

        sheet = common.open_sheet(
            app.page,
            "New Savings Goal",
            [
                name,
                target,
                current,
                apy,
                notes,
                common.hint("Calculates daily projected returns based on your chosen APY rate."),
                ft.Row([common.primary_button("Create Goal", save_goal, icon=ft.Icons.ADD)]),
            ],
        )

    def _open_deposit_modal(self, goal: SavingsGoal) -> None:
        app = self.app

        def confirm_deposit(_: Any = None) -> None:
            val = _clean_amount(amt_field.value)
            if val <= 0:
                sfx.play("error_soft")
                amt_field.error_text = "Enter a valid amount"
                amt_field.update()
                return
            goal.deposit(val)
            app.save()
            common.close(sheet)
            sfx.play("milestone")
            self.render()
            ui.refresh(self.list)
            app.toast(f"Deposited {ui.peso(val)} to {goal.name}!", ft.Icons.SAVINGS)

        amt_field = common.text_field("Deposit Amount (₱)", number=True, autofocus=False, on_submit=confirm_deposit)

        def set_preset(v: float) -> None:
            amt_field.value = str(int(v)) if v.is_integer() else str(v)
            amt_field.update()

        presets = ft.Row(
            [
                common.secondary_button("+₱500", lambda _: set_preset(500)),
                common.secondary_button("+₱1,000", lambda _: set_preset(1000)),
                common.secondary_button("+₱5,000", lambda _: set_preset(5000)),
            ],
            spacing=Space.XS,
            wrap=True,
        )

        sheet = common.open_sheet(
            app.page,
            f"Deposit: {goal.name}",
            [
                ft.Text(f"Current Balance: {ui.peso(goal.current_amount)}", size=Type.BODY, color=C.TEXT_DIM),
                amt_field,
                presets,
                common.hint(f"New balance will earn +{ui.peso((goal.current_amount + 1000) * (goal.apy_percent / 100) / 365)} daily interest."),
                ft.Row([common.primary_button("Confirm Deposit", confirm_deposit, icon=ft.Icons.ARROW_DOWNWARD)]),
            ],
        )

    def _open_withdraw_modal(self, goal: SavingsGoal) -> None:
        app = self.app

        def confirm_withdraw(_: Any = None) -> None:
            val = _clean_amount(amt_field.value)
            if val <= 0 or val > goal.current_amount:
                sfx.play("error_soft")
                amt_field.error_text = f"Enter an amount between ₱1 and {ui.peso(goal.current_amount)}"
                amt_field.update()
                return
            withdrawn = goal.withdraw(val)
            app.save()
            common.close(sheet)
            sfx.play("tap")
            self.render()
            ui.refresh(self.list)
            app.toast(f"Withdrew {ui.peso(withdrawn)} from {goal.name}", ft.Icons.ACCOUNT_BALANCE_WALLET)

        amt_field = common.text_field(
            f"Withdraw Amount (Max: {ui.peso(goal.current_amount)})", number=True, autofocus=False, on_submit=confirm_withdraw
        )

        sheet = common.open_sheet(
            app.page,
            f"Withdraw: {goal.name}",
            [
                ft.Text(f"Available Balance: {ui.peso(goal.current_amount)}", size=Type.BODY, color=C.TEXT_DIM),
                amt_field,
                ft.Row([common.primary_button("Confirm Withdrawal", confirm_withdraw, icon=ft.Icons.ARROW_UPWARD)]),
            ],
        )

    def _open_goal_options(self, goal: SavingsGoal) -> None:
        app = self.app

        def delete_goal(_: Any = None) -> None:
            if goal in app.game.data.savings_goals:
                app.game.data.savings_goals.remove(goal)
                app.save()
            common.close(sheet)
            sfx.play("tap")
            self.render()
            ui.refresh(self.list)
            app.toast(f"Goal '{goal.name}' removed", ft.Icons.DELETE)

        sheet = common.open_sheet(
            app.page,
            f"Goal: {goal.name}",
            [
                ft.Text(f"Current: {ui.peso(goal.current_amount)} / Target: {ui.peso(goal.target_amount)}", size=Type.BODY, color=C.TEXT),
                ft.Text(f"Daily Interest: +{ui.peso(goal.daily_interest)} ({goal.apy_percent:.1f}% APY)", size=Type.CAPTION, color=C.SUCCESS),
                common.secondary_button("Delete Savings Goal", delete_goal, icon=ft.Icons.DELETE, danger=True),
            ],
        )
