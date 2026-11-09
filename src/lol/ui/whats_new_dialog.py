"""What's New / In-App TL;DR Patch Notes Dialog for LUMA v0.2.1."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import flet as ft

from lol.core import cloud_config
from lol.ui import components as ui
from lol.ui import sfx
from lol.ui.screens import common
from lol.ui.theme import C, Radius, Space, Type

if TYPE_CHECKING:
    from lol.ui.app import App

CHANGELOG_ITEMS = (
    (
        ft.Icons.CALL_SPLIT,
        C.GOLD,
        "Split Bills & Receipt OCR",
        "Split expenses evenly in the middle or per dish/item with your friends. Upload your QR code (PayPal, Venmo, GCash, Bank) so friends can pay in a tap!",
    ),
    (
        ft.Icons.LANGUAGE,
        C.PRIMARY,
        "Global Currency Switcher",
        "Switch currency symbols anytime (₱, $, €, £, ¥, ₹, ₩, A$, C$, S$) across your bills and tracking.",
    ),
    (
        ft.Icons.PALETTE,
        "#A78BFA",
        "Unified Personalization Shop",
        "Themes, background particle FX, avatar frames, titles, companions, and XP trail glows are now unified in one shop under Rewards.",
    ),
    (
        ft.Icons.AUTO_AWESOME,
        "#FF8FA3",
        "Realistic Sakura & Particle FX",
        "Background atmospheric particles now feature authentic fluttering sakura petals, soft fireflies, embers, and snowfall.",
    ),
    (
        ft.Icons.FITNESS_CENTER,
        "#4FE3F0",
        "Clean Workout Hub & Star-Iron Forge",
        "Streamlined 'Start workout' button and concise relic forging recipes to power up your hero.",
    ),
)


def prompt_whats_new(app: App, on_done: Any = None) -> None:
    """Show the v0.2.1 What's New modal once per day or update cycle."""
    today_str = app.today().isoformat()
    last_seen = getattr(app.game.profile, "last_seen_changelog", "")
    if last_seen == today_str:
        if callable(on_done):
            on_done()
        return

    sheet_ref: list[ft.BottomSheet] = []

    def close_and_dismiss(for_today: bool = True) -> None:
        if for_today:
            app.game.profile.last_seen_changelog = today_str
            app.save()
        if sheet_ref:
            common.close(sheet_ref[0])
        sfx.play("tap")
        if callable(on_done):
            on_done()

    rows: list[ft.Control] = []
    for icon, color, title, desc in CHANGELOG_ITEMS:
        rows.append(
            common.card(
                ft.Row(
                    [
                        ft.Container(
                            ft.Icon(icon, color=color, size=24),
                            width=42,
                            height=42,
                            border_radius=Radius.SM,
                            bgcolor=C.a(color, 0.16),
                            alignment=ft.Alignment.CENTER,
                        ),
                        ft.Column(
                            [
                                ft.Text(title, size=Type.BODY, weight=ft.FontWeight.W_800, color=C.TEXT),
                                ft.Text(desc, size=Type.CAPTION, color=C.TEXT_DIM),
                            ],
                            spacing=2,
                            expand=True,
                            tight=True,
                        ),
                    ],
                    spacing=Space.SM,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                ),
                padding=Space.SM + 2,
            )
        )

    header = ft.Column(
        [
            ft.Row(
                [
                    ui.chip(f"v{cloud_config.APP_VERSION}", color=C.PRIMARY, solid=True),
                    ft.Text("What's New in LUMA", size=Type.TITLE, weight=ft.FontWeight.W_900, color=C.TEXT),
                ],
                spacing=Space.SM,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            common.hint("Here is a quick look at the latest features and quality-of-life updates:"),
        ],
        spacing=4,
        tight=True,
    )

    actions = ft.Row(
        [
            common.secondary_button("Got it", lambda _: close_and_dismiss(for_today=True), expand=True),
        ],
        spacing=Space.SM,
    )

    body = ft.Column(
        [
            header,
            *rows,
            ft.Container(height=Space.XS),
            actions,
        ],
        spacing=Space.SM,
        tight=True,
        scroll=ft.ScrollMode.AUTO,
    )

    sheet_ref.append(
        common.open_sheet(
            app.page,
            f"What's New (v{cloud_config.APP_VERSION})",
            [body],
            on_dismiss=lambda: close_and_dismiss(for_today=True),
        )
    )

