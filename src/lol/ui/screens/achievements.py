"""More -> Achievements: Complete list of in-game achievements that unlock equippable Hero Titles.

Supports tracking progress, displaying unlocked titles, and equipping up to 3 titles simultaneously.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import flet as ft

from lol.core import cosmetics as cos
from lol.ui import components as ui
from lol.ui import sfx
from lol.ui.screens import common
from lol.ui.theme import C, Radius, Space, Type

if TYPE_CHECKING:
    from lol.ui.app import App


class AchievementsScreen:
    title = "Achievements"

    def __init__(self, app: App) -> None:
        self.app = app
        self.list = common.screen_list()
        self.view = ft.Container(self.list, expand=True, key="achievements")

    def render(self) -> None:
        g = self.app.game
        p = g.profile
        titles = [c for c in cos.items_for_category("title") if c.id != "title_none"]
        unlocked_titles = [c for c in titles if cos.is_title_unlocked(g, c.id)]
        equipped_tids = getattr(p, "equipped_titles", []) or []

        # --- Top Overview Card ---
        pct = len(unlocked_titles) / len(titles) if titles else 0.0

        # Currently equipped title chips
        eq_chips: list[ft.Control] = []
        if equipped_tids:
            for tid in equipped_tids[:3]:
                t_item = cos.get_cosmetic(tid, "title")
                chip = ft.Container(
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.MILITARY_TECH, size=14, color=t_item.color),
                            ft.Text(
                                t_item.badge_text.upper() if t_item.badge_text else t_item.name.upper(),
                                size=Type.CAPTION,
                                weight=ft.FontWeight.W_800,
                                color=C.TEXT,
                            ),
                            ft.Icon(ft.Icons.CLOSE, size=13, color=C.TEXT_DIM),
                        ],
                        spacing=4,
                        tight=True,
                    ),
                    padding=ft.Padding.symmetric(horizontal=8, vertical=4),
                    bgcolor=C.a(t_item.color, 0.16),
                    border=ft.Border.all(1, C.a(t_item.color, 0.45)),
                    border_radius=Radius.PILL,
                    ink=True,
                    tooltip=f"Tap to unequip {t_item.name}",
                    on_click=lambda e, cid=tid: self._toggle_equip(cid),
                )
                eq_chips.append(chip)
        else:
            eq_chips.append(
                ft.Text("No titles equipped (you can equip up to 3)", size=Type.CAPTION, color=C.TEXT_DIM)
            )

        header_content = ft.Column(
            [
                ft.Row(
                    [
                        ft.Icon(ft.Icons.EMOJI_EVENTS, color=C.GOLD, size=28),
                        ft.Column(
                            [
                                ft.Text("HERO ACHIEVEMENTS & TITLES", size=Type.CAPTION, weight=ft.FontWeight.BOLD, color=C.GOLD),
                                ft.Text(f"{len(unlocked_titles)} / {len(titles)} Unlocked", size=Type.HEADLINE, weight=ft.FontWeight.W_900, color=C.TEXT),
                            ],
                            spacing=0,
                            tight=True,
                            expand=True,
                        ),
                        ft.Container(
                            ft.Text(f"Equipped: {len(equipped_tids)}/3", size=Type.CAPTION, weight=ft.FontWeight.BOLD, color=C.PRIMARY),
                            padding=ft.Padding.symmetric(horizontal=8, vertical=4),
                            bgcolor=C.a(C.PRIMARY, 0.14),
                            border=ft.Border.all(1, C.a(C.PRIMARY, 0.4)),
                            border_radius=Radius.PILL,
                        ),
                    ],
                    spacing=Space.SM,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.ProgressBar(
                    value=pct,
                    color=C.GOLD,
                    bgcolor=C.a(C.TEXT, 0.1),
                    height=6,
                    border_radius=Radius.PILL,
                ),
                ft.Row(eq_chips, wrap=True, spacing=Space.XS, run_spacing=Space.XS),
                common.hint("Achievements reward permanent Equippable Titles. You can display up to 3 simultaneously on your hero!"),
            ],
            spacing=Space.SM,
            tight=True,
        )

        items: list[ft.Control] = [common.card(header_content, padding=Space.MD)]
        items.append(ui.SectionHeader("Titles & Badges", count=len(titles)))

        # List of Title Achievement Cards
        for c_item in titles:
            items.append(self._achievement_card(c_item))

        self.list.controls = items

    def _achievement_card(self, c_item: cos.CosmeticItem) -> ft.Control:
        g = self.app.game
        p = g.profile
        unlocked = cos.is_title_unlocked(g, c_item.id)
        equipped = g.is_title_equipped(c_item.id)
        eq_cnt = len(getattr(p, "equipped_titles", []))

        # Rainbow styling for beta badge
        if c_item.id == "title_beta":
            rainbow_palette = [
                "#FF595E", "#FF924C", "#FFCA3A", "#8AC926",
                "#1982C4", "#6A4C93", "#FF595E", "#FF924C",
                "#FFCA3A", "#8AC926", "#1982C4",
            ]
            spans = []
            txt = c_item.name.upper()
            for idx, ch in enumerate(txt):
                spans.append(
                    ft.TextSpan(ch, style=ft.TextStyle(color=rainbow_palette[idx % len(rainbow_palette)], weight=ft.FontWeight.W_900, size=14))
                )
            title_widget = ft.Text(spans=spans)
        else:
            title_widget = ft.Text(c_item.name, size=Type.TITLE, weight=ft.FontWeight.W_800, color=C.TEXT if unlocked else C.TEXT_DIM)

        # Status badge & action button
        if equipped:
            status_badge = ft.Container(
                ft.Row(
                    [
                        ft.Icon(ft.Icons.CHECK_CIRCLE, size=14, color=C.SUCCESS),
                        ft.Text("EQUIPPED", size=Type.CAPTION, weight=ft.FontWeight.W_900, color=C.SUCCESS),
                    ],
                    spacing=4,
                    tight=True,
                ),
                padding=ft.Padding.symmetric(horizontal=8, vertical=4),
                bgcolor=C.a(C.SUCCESS, 0.15),
                border=ft.Border.all(1, C.a(C.SUCCESS, 0.45)),
                border_radius=Radius.PILL,
            )
            action_btn = common.secondary_button("Unequip", lambda _, cid=c_item.id: self._toggle_equip(cid), icon=ft.Icons.REMOVE_CIRCLE_OUTLINE, expand=False)
        elif unlocked:
            status_badge = ft.Container(
                ft.Row(
                    [
                        ft.Icon(ft.Icons.VERIFIED, size=14, color=C.GOLD),
                        ft.Text("UNLOCKED", size=Type.CAPTION, weight=ft.FontWeight.W_900, color=C.GOLD),
                    ],
                    spacing=4,
                    tight=True,
                ),
                padding=ft.Padding.symmetric(horizontal=8, vertical=4),
                bgcolor=C.a(C.GOLD, 0.15),
                border=ft.Border.all(1, C.a(C.GOLD, 0.45)),
                border_radius=Radius.PILL,
            )
            action_btn = common.primary_button(
                f"Equip ({eq_cnt}/3)",
                lambda _, cid=c_item.id: self._toggle_equip(cid),
                icon=ft.Icons.ADD_CIRCLE_OUTLINE,
                expand=False,
            )
        else:
            status_badge = ft.Container(
                ft.Row(
                    [
                        ft.Icon(ft.Icons.LOCK, size=14, color=C.TEXT_DIM),
                        ft.Text("LOCKED", size=Type.CAPTION, weight=ft.FontWeight.W_700, color=C.TEXT_DIM),
                    ],
                    spacing=4,
                    tight=True,
                ),
                padding=ft.Padding.symmetric(horizontal=8, vertical=4),
                bgcolor=C.a(C.SURFACE_HI, 0.5),
                border=ft.Border.all(1, C.a(C.TEXT_DIM, 0.25)),
                border_radius=Radius.PILL,
            )
            action_btn = ft.Container()

        icon_box = ft.Container(
            ft.Icon(
                getattr(ft.Icons, c_item.icon_name.upper(), ft.Icons.MILITARY_TECH),
                color=c_item.color if unlocked else C.TEXT_DIM,
                size=24,
            ),
            width=44,
            height=44,
            bgcolor=C.a(c_item.color, 0.15) if unlocked else C.a(C.SURFACE_HI, 0.6),
            border=ft.Border.all(1.2, C.a(c_item.color, 0.4) if unlocked else C.a(C.TEXT_DIM, 0.2)),
            border_radius=Radius.MD,
            alignment=ft.Alignment(0, 0),
        )

        card_content = ft.Column(
            [
                ft.Row(
                    [
                        icon_box,
                        ft.Column(
                            [
                                title_widget,
                                ft.Text(c_item.subtitle, size=Type.CAPTION, color=C.TEXT if unlocked else C.TEXT_DIM),
                            ],
                            spacing=2,
                            expand=True,
                            tight=True,
                        ),
                        status_badge,
                    ],
                    spacing=Space.SM,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Row(
                    [
                        ft.Container(expand=True),
                        action_btn,
                    ],
                    alignment=ft.MainAxisAlignment.END,
                ) if unlocked else ft.Container(),
            ],
            spacing=Space.SM,
            tight=True,
        )

        return common.card(
            card_content,
            padding=Space.MD,
            border=ft.Border.all(1.2, C.a(c_item.color, 0.5)) if equipped else None,
        )

    def _toggle_equip(self, title_id: str) -> None:
        g = self.app.game
        was_equipped = g.is_title_equipped(title_id)
        if not g.equip_cosmetic(title_id):
            sfx.play("error_soft")
            return
        self.app.save()
        if was_equipped:
            sfx.play("tap")
            self.app.toast("Title unequipped", ft.Icons.REMOVE_CIRCLE_OUTLINE)
        else:
            sfx.play("milestone")
            t_item = cos.get_cosmetic(title_id, "title")
            self.app.toast(f"Equipped '{t_item.name}'!", ft.Icons.CHECK_CIRCLE)

        self.app.refresh_profile()
        self.render()
        ui.refresh(self.list)
