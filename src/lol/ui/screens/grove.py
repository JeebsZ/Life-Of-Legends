"""Mind Grove: The Fitness Farm screen for LUMA.

Real-world health and workouts fuel crop growth, seed cross-breeding, and botanical rewards.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import flet as ft

from lol.core import cosmetics, grove
from lol.ui import components as ui
from lol.ui import sfx
from lol.ui.screens import common
from lol.ui.theme import C, Radius, Space, Type

if TYPE_CHECKING:
    from lol.ui.app import App


class GroveScreen:
    title = "Mind Grove"

    def __init__(self, app: App) -> None:
        self.app = app
        self.list = common.screen_list()
        self.view = ft.Container(self.list, expand=True, key="grove_screen")
        self.current_tab = "plots"  # "plots", "altar", "silo"
        self.selected_altar_a: str | None = None
        self.selected_altar_b: str | None = None

    def on_enter(self) -> None:
        # Sync real-world fitness habits whenever player visits Mind Grove
        res = grove.sync_fitness_to_grove(self.app.game)
        if res.get("awarded_seeds"):
            seeds_str = ", ".join(
                grove.get_seed(s).name if grove.get_seed(s) else s
                for s in res["awarded_seeds"]
            )
            self.app.toast(f"🌱 Fitness habits bloomed: +{seeds_str}!", ft.Icons.AUTO_AWESOME)
            sfx.play("reward_redeemed")
        self.render()

    def render(self) -> None:
        self.list.controls.clear()
        g = self.app.game
        state: grove.GroveState = getattr(g.data, "grove", None)
        if state is None:
            state = grove.GroveState()
            g.data.grove = state

        # Sync fitness status
        sync_info = grove.sync_fitness_to_grove(g)

        # 1. Header Banner & Habit Meters
        self.list.controls.append(self._header_card(sync_info, state))

        # 2. Tab Navigation Selector
        self.list.controls.append(self._tab_selector())

        # 3. Main Content by Tab
        if self.current_tab == "plots":
            self.list.controls.append(self._plots_view(state))
        elif self.current_tab == "altar":
            self.list.controls.append(self._altar_view(state))
        else:
            self.list.controls.append(self._silo_view(state))

        ui.refresh(self.list)

    # ------------------------------------------------------------------ Header & Meters
    def _header_card(self, sync_info: dict[str, Any], state: grove.GroveState) -> ft.Control:
        sunlight_s = sync_info.get("sunlight_boost_s", 0.0)
        sunlight_mins = int(sunlight_s // 60)

        # Count ready plots & seeds
        ready_count = sum(1 for p in state.plots if p.harvest_ready)
        seed_count = sum(state.seeds.values())

        return common.card(
            ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.PARK_ROUNDED, color="#06D6A0", size=26),
                            ft.Column(
                                [
                                    ft.Text(
                                        "MIND GROVE",
                                        size=Type.CAPTION,
                                        weight=ft.FontWeight.W_800,
                                        color="#06D6A0",
                                    ),
                                    ft.Text(
                                        f"The Fitness Farm ({ready_count} ready • {seed_count} seeds)",
                                        size=Type.TITLE,
                                        weight=ft.FontWeight.BOLD,
                                        color=C.TEXT,
                                    ),
                                ],
                                spacing=0,
                                expand=True,
                            ),
                            ft.Container(
                                ft.Row(
                                    [
                                        ft.Icon(
                                            ft.Icons.ENERGY_SAVINGS_LEAF_ROUNDED
                                            if ready_count > 0
                                            else ft.Icons.YARD_ROUNDED,
                                            size=15,
                                            color=C.GOLD if ready_count > 0 else "#06D6A0",
                                        ),
                                        ft.Text(
                                            f"{ready_count} Ready"
                                            if ready_count > 0
                                            else f"{state.total_harvests} Harvested",
                                            size=Type.CAPTION,
                                            weight=ft.FontWeight.BOLD,
                                            color=C.GOLD if ready_count > 0 else "#06D6A0",
                                        ),
                                    ],
                                    spacing=4,
                                    tight=True,
                                ),
                                padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                                bgcolor=C.a(C.GOLD if ready_count > 0 else "#06D6A0", 0.15),
                                border_radius=Radius.PILL,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Divider(height=1, color=C.a(C.OUTLINE, 0.4)),
                    # Real-world energy fuel indicators
                    ft.Row(
                        [
                            ft.Container(
                                ft.Row(
                                    [
                                        ft.Icon(ft.Icons.WB_SUNNY, size=16, color="#FFD166"),
                                        ft.Column(
                                            [
                                                ft.Text(
                                                    f"+{sunlight_mins}m Sunlight",
                                                    size=Type.CAPTION,
                                                    weight=ft.FontWeight.BOLD,
                                                    color=C.TEXT,
                                                ),
                                                ft.Text(
                                                    "Run/Walk speedup",
                                                    size=Type.CAPTION - 2,
                                                    color=C.TEXT_DIM,
                                                ),
                                            ],
                                            spacing=0,
                                        ),
                                    ],
                                    spacing=Space.SM,
                                ),
                                expand=True,
                            ),
                            ft.Container(
                                ft.Row(
                                    [
                                        ft.Icon(ft.Icons.WATER_DROP, size=16, color="#00F5D4"),
                                        ft.Column(
                                            [
                                                ft.Text(
                                                    "Hydrated" if state.last_awarded_habits.get("water") else "Needs Water",
                                                    size=Type.CAPTION,
                                                    weight=ft.FontWeight.BOLD,
                                                    color="#00F5D4" if state.last_awarded_habits.get("water") else C.TEXT_DIM,
                                                ),
                                                ft.Text(
                                                    "Daily water logged",
                                                    size=Type.CAPTION - 2,
                                                    color=C.TEXT_DIM,
                                                ),
                                            ],
                                            spacing=0,
                                        ),
                                    ],
                                    spacing=Space.SM,
                                ),
                                expand=True,
                            ),
                        ],
                        spacing=Space.MD,
                    ),
                ],
                spacing=Space.MD,
            ),
            tint="#06D6A0",
        )

    def _tab_selector(self) -> ft.Control:
        tabs = [
            ("plots", "Grove Plots", ft.Icons.YARD_ROUNDED),
            ("altar", "Botanical Altar", ft.Icons.AUTO_AWESOME_ROUNDED),
            ("silo", "Silo & Almanac", ft.Icons.INVENTORY_2_ROUNDED),
        ]

        chips: list[ft.Control] = []
        for key, label, icon in tabs:
            is_active = self.current_tab == key

            def make_click(k: str):
                def on_click(_):
                    if self.current_tab != k:
                        self.current_tab = k
                        sfx.play("tab_open")
                        self.render()
                return on_click

            chips.append(
                ft.Container(
                    ft.Row(
                        [
                            ft.Icon(
                                icon,
                                size=15,
                                color="#06D6A0" if is_active else C.TEXT_DIM,
                            ),
                            ft.Text(
                                label,
                                size=Type.CAPTION,
                                weight=ft.FontWeight.BOLD if is_active else ft.FontWeight.W_500,
                                color=C.TEXT if is_active else C.TEXT_DIM,
                            ),
                        ],
                        spacing=Space.XS,
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                    padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                    border_radius=Radius.PILL,
                    bgcolor=C.a("#06D6A0", 0.2) if is_active else C.a(C.SURFACE, 0.5),
                    border=ft.Border.all(1, "#06D6A0" if is_active else C.a(C.OUTLINE, 0.4)),
                    on_click=make_click(key),
                    expand=True,
                )
            )

        return ft.Row(chips, spacing=Space.SM)

    # ------------------------------------------------------------------ Plots Tab
    def _plots_view(self, state: grove.GroveState) -> ft.Control:
        plot_cards: list[ft.Control] = []
        now = datetime.now(UTC)

        for plot in state.plots:
            plot_cards.append(self._plot_card(plot, state, now))

        return ft.Column(
            [
                ft.Row(
                    [
                        ft.Text(
                            "SOIL PLOTS (6)",
                            size=Type.CAPTION,
                            weight=ft.FontWeight.BOLD,
                            color=C.TEXT_DIM,
                        ),
                        ft.Text(
                            "Tap ready plots to harvest coins & seeds",
                            size=Type.CAPTION - 1,
                            color=C.TEXT_DIM,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                *plot_cards,
            ],
            spacing=Space.MD,
        )

    def _plot_card(
        self, plot: grove.CropPlot, state: grove.GroveState, now: datetime
    ) -> ft.Control:
        if plot.is_empty():
            # Empty plot: Prompt planting
            def on_plant_click(_):
                self._open_plant_sheet(plot.plot_id, state)

            return common.card(
                ft.Row(
                    [
                        ft.Container(
                            ft.Icon(ft.Icons.GRASS_ROUNDED, color=C.a(C.TEXT_DIM, 0.5), size=28),
                            width=52,
                            height=52,
                            border_radius=Radius.MD,
                            bgcolor=C.a(C.SURFACE_HI, 0.6),
                            alignment=ft.Alignment(0, 0),
                        ),
                        ft.Column(
                            [
                                ft.Text(
                                    f"Plot #{plot.plot_id + 1} - Fertile Soil",
                                    size=Type.BODY,
                                    weight=ft.FontWeight.BOLD,
                                    color=C.TEXT,
                                ),
                                ft.Text(
                                    "Tap to sow a seed from your inventory",
                                    size=Type.CAPTION,
                                    color=C.TEXT_DIM,
                                ),
                            ],
                            spacing=2,
                            expand=True,
                        ),
                        ft.FilledButton(
                            "Plant",
                            icon=ft.Icons.ADD_ROUNDED,
                            style=ft.ButtonStyle(
                                bgcolor="#06D6A0",
                                color="#0D1F2D",
                                shape=ft.RoundedRectangleBorder(radius=Radius.PILL),
                            ),
                            on_click=on_plant_click,
                        ),
                    ],
                    spacing=Space.MD,
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
            )

        # Growing or Ready Plot
        seed = grove.get_seed(plot.seed_id)
        seed_name = seed.name if seed else "Sprout"
        seed_emoji = seed.emoji if seed else "🌱"
        seed_color = seed.color if seed else "#06D6A0"
        seed_yield = seed.coin_yield if seed else 50

        progress = grove.plot_progress(plot, now)
        rem_s = grove.plot_remaining_s(plot, now)
        is_ready = plot.harvest_ready or progress >= 1.0 or rem_s <= 0

        if is_ready:
            def on_harvest_click(_):
                plot.harvest_ready = True
                _coins, bonus = grove.harvest_crop(state, plot.plot_id)
                self.app.save()
                self.app.refresh_profile()
                sfx.play("harvest_burst")

                bonus_names = [grove.get_seed(b).name if grove.get_seed(b) else b for b in bonus]
                toast_msg = f"🌾 Harvested 1x {seed_name}! Stored in your Silo."
                if bonus_names:
                    toast_msg += f" (Bonus seed: {', '.join(bonus_names)})"
                self.app.toast(toast_msg, ft.Icons.ENERGY_SAVINGS_LEAF)
                self.render()

            return common.card(
                ft.Row(
                    [
                        ft.Container(
                            ft.Text(seed_emoji, size=28),
                            width=52,
                            height=52,
                            border_radius=Radius.MD,
                            bgcolor=C.a(seed_color, 0.25),
                            border=ft.Border.all(1.5, seed_color),
                            alignment=ft.Alignment(0, 0),
                        ),
                        ft.Column(
                            [
                                ft.Row(
                                    [
                                        ft.Text(
                                            seed_name,
                                            size=Type.BODY,
                                            weight=ft.FontWeight.BOLD,
                                            color=C.TEXT,
                                        ),
                                        ft.Container(
                                            ft.Text(
                                                "READY",
                                                size=Type.CAPTION - 2,
                                                weight=ft.FontWeight.BOLD,
                                                color="#0D1F2D",
                                            ),
                                            padding=ft.Padding.symmetric(horizontal=6, vertical=2),
                                            bgcolor=C.GOLD,
                                            border_radius=Radius.PILL,
                                        ),
                                    ],
                                    spacing=Space.SM,
                                ),
                                ft.Text(
                                    f"Yield: +{seed_yield} coins & bonus seed roll",
                                    size=Type.CAPTION,
                                    color=C.GOLD,
                                ),
                            ],
                            spacing=2,
                            expand=True,
                        ),
                        ft.FilledButton(
                            "Harvest",
                            icon=ft.Icons.ENERGY_SAVINGS_LEAF_ROUNDED,
                            style=ft.ButtonStyle(
                                bgcolor=C.GOLD,
                                color="#0D1F2D",
                                shape=ft.RoundedRectangleBorder(radius=Radius.PILL),
                            ),
                            on_click=on_harvest_click,
                        ),
                    ],
                    spacing=Space.MD,
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                tint=C.GOLD,
            )

        # Still Growing
        mins = int(rem_s // 60)
        secs = int(rem_s % 60)
        time_str = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"

        return common.card(
            ft.Column(
                [
                    ft.Row(
                        [
                            ft.Container(
                                ft.Text(seed_emoji, size=24),
                                width=46,
                                height=46,
                                border_radius=Radius.MD,
                                bgcolor=C.a(seed_color, 0.15),
                                alignment=ft.Alignment(0, 0),
                            ),
                            ft.Column(
                                [
                                    ft.Text(
                                        seed_name,
                                        size=Type.BODY,
                                        weight=ft.FontWeight.BOLD,
                                        color=C.TEXT,
                                    ),
                                    ft.Row(
                                        [
                                            ft.Text(
                                                f"Plot #{plot.plot_id + 1} • Tier {seed.tier if seed else 1}",
                                                size=Type.CAPTION,
                                                color=C.TEXT_DIM,
                                            ),
                                            *(
                                                [
                                                    ft.Container(
                                                        ft.Row(
                                                            [
                                                                ft.Icon(
                                                                    ft.Icons.WB_SUNNY,
                                                                    size=11,
                                                                    color="#FFD166",
                                                                ),
                                                                ft.Text(
                                                                    f"-{int(plot.boost_s // 60)}m run boost",
                                                                    size=Type.CAPTION - 3,
                                                                    color="#FFD166",
                                                                    weight=ft.FontWeight.BOLD,
                                                                ),
                                                            ],
                                                            spacing=2,
                                                            tight=True,
                                                        ),
                                                        padding=ft.Padding.symmetric(
                                                            horizontal=6, vertical=2
                                                        ),
                                                        bgcolor=C.a("#FFD166", 0.15),
                                                        border_radius=Radius.PILL,
                                                    )
                                                ]
                                                if plot.boost_s > 0
                                                else []
                                            ),
                                        ],
                                        spacing=Space.XS,
                                    ),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                            ft.Container(
                                ft.Row(
                                    [
                                        ft.Icon(ft.Icons.TIMER_OUTLINED, size=13, color=C.TEXT_DIM),
                                        ft.Text(time_str, size=Type.CAPTION, color=C.TEXT_DIM),
                                    ],
                                    spacing=4,
                                    tight=True,
                                ),
                                padding=ft.Padding.symmetric(horizontal=8, vertical=4),
                                bgcolor=C.a(C.SURFACE_HI, 0.5),
                                border_radius=Radius.PILL,
                            ),
                        ],
                        spacing=Space.MD,
                    ),
                    ft.ProgressBar(
                        value=progress,
                        color=seed_color,
                        bgcolor=C.a(C.SURFACE_HI, 0.5),
                        border_radius=Radius.PILL,
                    ),
                ],
                spacing=Space.SM,
            ),
            tint=seed_color,
        )

    # ------------------------------------------------------------------ Plant Sheet Modal
    def _open_plant_sheet(self, plot_id: int, state: grove.GroveState) -> None:
        sheet_items: list[ft.Control] = []

        if not state.seeds:
            sheet_items.append(
                ft.Container(
                    ft.Column(
                        [
                            ft.Icon(ft.Icons.INVENTORY_2_OUTLINED, size=36, color=C.TEXT_DIM),
                            ft.Text(
                                "No seeds in inventory",
                                size=Type.BODY,
                                weight=ft.FontWeight.BOLD,
                                color=C.TEXT,
                            ),
                            ft.Text(
                                "Log your daily water, runs, workouts, and sleep to earn spores!",
                                size=Type.CAPTION,
                                color=C.TEXT_DIM,
                                text_align=ft.TextAlign.CENTER,
                            ),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=Space.SM,
                    ),
                    padding=Space.LG,
                )
            )
        else:
            for s_id, count in sorted(state.seeds.items()):
                if count <= 0:
                    continue
                s_def = grove.get_seed(s_id)
                if not s_def:
                    continue

                def make_plant(target_sid: str, target_name: str):
                    def do_plant(_):
                        ok = grove.plant_crop(state, plot_id, target_sid)
                        if ok:
                            self.app.save()
                            sfx.play("coin")
                            self.app.toast(f"Planted {target_name} in Plot #{plot_id + 1}!")
                        common.close(bs)
                        self.render()
                    return do_plant

                mins = s_def.growth_time_s // 60
                sheet_items.append(
                    ft.Container(
                        ft.Row(
                            [
                                ft.Text(s_def.emoji, size=24),
                                ft.Column(
                                    [
                                        ft.Text(
                                            f"{s_def.name} (x{count})",
                                            size=Type.BODY,
                                            weight=ft.FontWeight.BOLD,
                                            color=C.TEXT,
                                        ),
                                        ft.Text(
                                            f"Grow time: {mins}m • Yield: +{s_def.coin_yield} coins",
                                            size=Type.CAPTION,
                                            color=C.TEXT_DIM,
                                        ),
                                    ],
                                    spacing=2,
                                    expand=True,
                                ),
                                ft.FilledButton(
                                    "Sow",
                                    style=ft.ButtonStyle(
                                        bgcolor="#06D6A0",
                                        color="#0D1F2D",
                                        shape=ft.RoundedRectangleBorder(radius=Radius.PILL),
                                    ),
                                    on_click=make_plant(s_id, s_def.name),
                                ),
                            ],
                            spacing=Space.MD,
                        ),
                        padding=Space.SM,
                        border_radius=Radius.MD,
                        bgcolor=C.a(C.SURFACE_HI, 0.3),
                    )
                )

        bs = ft.BottomSheet(
            ft.Container(
                ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Text(
                                    f"Sow Seed in Plot #{plot_id + 1}",
                                    size=Type.TITLE,
                                    weight=ft.FontWeight.BOLD,
                                    color=C.TEXT,
                                ),
                                ft.IconButton(
                                    ft.Icons.CLOSE,
                                    on_click=lambda _: common.close(bs),
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                        ft.Divider(height=1, color=C.a(C.OUTLINE, 0.4)),
                        *sheet_items,
                    ],
                    spacing=Space.SM,
                    tight=True,
                ),
                padding=Space.LG,
                bgcolor=C.SURFACE,
                border_radius=ft.BorderRadius(top_left=Radius.LG, top_right=Radius.LG, bottom_left=0, bottom_right=0),
            )
        )
        self.app.page.show_dialog(bs)

    # ------------------------------------------------------------------ Altar Tab (Fusion)
    def _altar_view(self, state: grove.GroveState) -> ft.Control:
        def slot_display(seed_id: str | None, label: str, on_clear: Any) -> ft.Control:
            if not seed_id:
                return ft.Container(
                    ft.Column(
                        [
                            ft.Icon(ft.Icons.ADD_CIRCLE_OUTLINE, size=28, color="#06D6A0"),
                            ft.Text(label, size=Type.CAPTION, color=C.TEXT_DIM),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=Space.XS,
                    ),
                    width=130,
                    height=110,
                    border_radius=Radius.MD,
                    bgcolor=C.a(C.SURFACE_HI, 0.4),
                    border=ft.Border.all(1, C.a(C.OUTLINE, 0.5)),
                    alignment=ft.Alignment(0, 0),
                    on_click=lambda _: self._open_altar_picker(label == "Seed Slot A", state),
                )
            s_def = grove.get_seed(seed_id)
            return ft.Container(
                ft.Column(
                    [
                        ft.Text(s_def.emoji if s_def else "🌱", size=30),
                        ft.Text(
                            s_def.name if s_def else seed_id,
                            size=Type.CAPTION,
                            weight=ft.FontWeight.BOLD,
                            color=C.TEXT,
                            no_wrap=True,
                        ),
                        ft.Text("Tap to change", size=Type.CAPTION - 3, color=C.TEXT_DIM),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=2,
                ),
                width=130,
                height=110,
                border_radius=Radius.MD,
                bgcolor=C.a(s_def.color if s_def else "#06D6A0", 0.2),
                border=ft.Border.all(1.5, s_def.color if s_def else "#06D6A0"),
                alignment=ft.Alignment(0, 0),
                on_click=lambda _: self._open_altar_picker(label == "Seed Slot A", state),
            )

        def clear_a():
            self.selected_altar_a = None
            self.render()

        def clear_b():
            self.selected_altar_b = None
            self.render()

        # Check recipe preview
        preview_match = None
        can_fuse = bool(self.selected_altar_a and self.selected_altar_b)
        if can_fuse:
            pair = frozenset({self.selected_altar_a, self.selected_altar_b})
            if pair in grove.FUSION_RECIPES:
                res_id = grove.FUSION_RECIPES[pair]
                preview_match = grove.get_seed(res_id)

        def on_fuse_click(_):
            if not self.selected_altar_a or not self.selected_altar_b:
                return
            self.app.page.run_task(self._run_transmutation_flow, state)

        # Preview Widget
        if not can_fuse:
            preview_widget = ft.Text(
                "Select 2 seeds to synthesize a rare botanical hybrid",
                size=Type.CAPTION,
                color=C.TEXT_DIM,
                text_align=ft.TextAlign.CENTER,
            )
        elif preview_match:
            preview_widget = ft.Container(
                ft.Row(
                    [
                        ft.Text(preview_match.emoji, size=20),
                        ft.Column(
                            [
                                ft.Row(
                                    [
                                        ft.Text(
                                            "100% ALCHEMY MATCH",
                                            size=Type.CAPTION - 3,
                                            weight=ft.FontWeight.W_800,
                                            color=C.GOLD,
                                        ),
                                        ft.Text(
                                            f"Tier {preview_match.tier} • {preview_match.rarity}",
                                            size=Type.CAPTION - 3,
                                            color=C.TEXT_DIM,
                                        ),
                                    ],
                                    spacing=4,
                                ),
                                ft.Text(
                                    f"Will synthesize: {preview_match.name}!",
                                    size=Type.CAPTION,
                                    weight=ft.FontWeight.BOLD,
                                    color=C.TEXT,
                                ),
                            ],
                            spacing=1,
                            expand=True,
                        ),
                        ft.Icon(ft.Icons.AUTO_AWESOME, size=18, color=C.GOLD),
                    ],
                    spacing=Space.SM,
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
                padding=ft.Padding.symmetric(horizontal=12, vertical=6),
                bgcolor=C.a(C.GOLD, 0.12),
                border=ft.Border.all(1, C.a(C.GOLD, 0.4)),
                border_radius=Radius.MD,
            )
        else:
            def_a = grove.get_seed(self.selected_altar_a) if self.selected_altar_a else None
            def_b = grove.get_seed(self.selected_altar_b) if self.selected_altar_b else None
            tier_a = def_a.tier if def_a else 1
            tier_b = def_b.tier if def_b else 1
            target_tier = min(4, max(tier_a, tier_b))
            preview_widget = ft.Container(
                ft.Row(
                    [
                        ft.Icon(ft.Icons.SHUFFLE, size=18, color="#9D4EDD"),
                        ft.Column(
                            [
                                ft.Text(
                                    "ESSENCE TRANSMUTATION",
                                    size=Type.CAPTION - 3,
                                    weight=ft.FontWeight.W_800,
                                    color="#9D4EDD",
                                ),
                                ft.Text(
                                    f"Combines life force into a random Tier {target_tier} Spore (+10% mutation chance)",
                                    size=Type.CAPTION - 1,
                                    color=C.TEXT,
                                ),
                            ],
                            spacing=1,
                            expand=True,
                        ),
                    ],
                    spacing=Space.SM,
                ),
                padding=ft.Padding.symmetric(horizontal=12, vertical=6),
                bgcolor=C.a("#9D4EDD", 0.12),
                border=ft.Border.all(1, C.a("#9D4EDD", 0.4)),
                border_radius=Radius.MD,
            )

        return common.card(
            ft.Column(
                [
                    ft.Row(
                        [
                            ft.Row(
                                [
                                    ft.Icon(ft.Icons.AUTO_AWESOME, color="#9D4EDD", size=22),
                                    ft.Text(
                                        "BOTANICAL TRANSMUTATION ALTAR",
                                        size=Type.CAPTION,
                                        weight=ft.FontWeight.BOLD,
                                        color="#9D4EDD",
                                    ),
                                ],
                                spacing=Space.SM,
                            ),
                            ft.Container(
                                ft.Row(
                                    [
                                        ft.Icon(
                                            ft.Icons.MENU_BOOK_ROUNDED, size=13, color="#9D4EDD"
                                        ),
                                        ft.Text(
                                            "Recipe Codex",
                                            size=Type.CAPTION - 2,
                                            color="#9D4EDD",
                                            weight=ft.FontWeight.BOLD,
                                        ),
                                    ],
                                    spacing=4,
                                    tight=True,
                                ),
                                padding=ft.Padding.symmetric(horizontal=8, vertical=4),
                                bgcolor=C.a("#9D4EDD", 0.15),
                                border_radius=Radius.PILL,
                                border=ft.Border.all(1, C.a("#9D4EDD", 0.3)),
                                on_click=lambda _: self._open_recipe_codex(state),
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Text(
                        "Cross-breed two seeds to create higher-tier flora, unlock species in your Almanac, and multiply harvest coins.",
                        size=Type.CAPTION,
                        color=C.TEXT_DIM,
                    ),
                    ft.Divider(height=1, color=C.a(C.OUTLINE, 0.4)),
                    ft.Row(
                        [
                            slot_display(self.selected_altar_a, "Seed Slot A", clear_a),
                            ft.Icon(ft.Icons.ADD, color="#06D6A0", size=20),
                            slot_display(self.selected_altar_b, "Seed Slot B", clear_b),
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                        spacing=Space.MD,
                    ),
                    preview_widget,
                    ft.FilledButton(
                        "Fuse & Transmute Seeds",
                        icon=ft.Icons.AUTO_FIX_HIGH,
                        style=ft.ButtonStyle(
                            bgcolor="#9D4EDD" if can_fuse else C.a(C.SURFACE_HI, 0.5),
                            color="#FFFFFF" if can_fuse else C.TEXT_DIM,
                            shape=ft.RoundedRectangleBorder(radius=Radius.PILL),
                        ),
                        disabled=not can_fuse,
                        on_click=on_fuse_click,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=Space.MD,
            ),
            tint="#9D4EDD",
        )

    async def _run_transmutation_flow(self, state: grove.GroveState) -> None:
        seed_a_id = self.selected_altar_a
        seed_b_id = self.selected_altar_b
        if not seed_a_id or not seed_b_id:
            return

        def_a = grove.get_seed(seed_a_id)
        def_b = grove.get_seed(seed_b_id)
        name_a = def_a.name if def_a else seed_a_id
        name_b = def_b.name if def_b else seed_b_id
        emoji_a = def_a.emoji if def_a else "🌱"
        emoji_b = def_b.emoji if def_b else "🌱"

        # Deduct & fuse
        res_id, is_mut = grove.fuse_seeds(state, seed_a_id, seed_b_id)
        self.selected_altar_a = None
        self.selected_altar_b = None
        self.app.save()

        res_def = grove.get_seed(res_id)
        res_name = res_def.name if res_def else res_id
        res_emoji = res_def.emoji if res_def else "🌱"
        res_color = res_def.color if res_def else "#9D4EDD"
        res_tier = res_def.tier if res_def else 2
        res_rarity = res_def.rarity if res_def else "Hybrid"
        res_yield = res_def.coin_yield if res_def else 100
        res_mins = (res_def.growth_time_s // 60) if res_def else 30

        # Stage 1: Channelling & Resonance Animation Container
        progress_bar = ft.ProgressBar(value=0.0, color="#9D4EDD", bgcolor=C.a(C.SURFACE_HI, 0.5))
        status_text = ft.Text(
            "Channelling elemental resonance...",
            size=Type.CAPTION,
            color=C.TEXT_DIM,
            text_align=ft.TextAlign.CENTER,
        )

        modal_col = ft.Column(
            [
                ft.Text(
                    "Botanical Transmutation",
                    size=Type.TITLE,
                    weight=ft.FontWeight.BOLD,
                    color=C.TEXT,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Text(
                    "Combining sacred botanical essences at the Altar",
                    size=Type.CAPTION - 1,
                    color=C.TEXT_DIM,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Container(height=Space.SM),
                ft.Row(
                    [
                        ft.Container(
                            ft.Column(
                                [
                                    ft.Text(emoji_a, size=32),
                                    ft.Text(
                                        name_a,
                                        size=Type.CAPTION - 2,
                                        weight=ft.FontWeight.BOLD,
                                        color=C.TEXT,
                                        text_align=ft.TextAlign.CENTER,
                                        no_wrap=True,
                                    ),
                                ],
                                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                spacing=2,
                            ),
                            width=95,
                            padding=Space.SM,
                            bgcolor=C.a(def_a.color if def_a else C.SURFACE_HI, 0.2),
                            border=ft.Border.all(1.5, def_a.color if def_a else C.OUTLINE),
                            border_radius=Radius.MD,
                        ),
                        ft.Column(
                            [
                                ft.Icon(ft.Icons.AUTO_AWESOME, color="#9D4EDD", size=24),
                                ft.Text(
                                    "FUSING",
                                    size=Type.CAPTION - 3,
                                    weight=ft.FontWeight.W_800,
                                    color="#9D4EDD",
                                ),
                            ],
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=2,
                        ),
                        ft.Container(
                            ft.Column(
                                [
                                    ft.Text(emoji_b, size=32),
                                    ft.Text(
                                        name_b,
                                        size=Type.CAPTION - 2,
                                        weight=ft.FontWeight.BOLD,
                                        color=C.TEXT,
                                        text_align=ft.TextAlign.CENTER,
                                        no_wrap=True,
                                    ),
                                ],
                                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                spacing=2,
                            ),
                            width=95,
                            padding=Space.SM,
                            bgcolor=C.a(def_b.color if def_b else C.SURFACE_HI, 0.2),
                            border=ft.Border.all(1.5, def_b.color if def_b else C.OUTLINE),
                            border_radius=Radius.MD,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                    spacing=Space.SM,
                ),
                ft.Container(height=Space.SM),
                progress_bar,
                status_text,
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=Space.SM,
            tight=True,
        )

        dialog_content = ft.Container(
            modal_col,
            width=320,
            padding=Space.MD,
        )

        dlg = ft.AlertDialog(content=dialog_content)
        self.app.page.show_dialog(dlg)

        # Start Transmutation SFX Combo
        sfx.play("botanical_transmute")

        # Step 1: Animate Progress
        for step in range(1, 11):
            await asyncio.sleep(0.1)
            progress_bar.value = step / 10.0
            if step == 4:
                status_text.value = "Harmonizing life force spores..."
            elif step == 8:
                status_text.value = "Catalyzing molecular bloom..."
            ui.refresh(dialog_content)

        await asyncio.sleep(0.2)

        # Stage 2: Radiant Reveal & Burst SFX
        sfx.play("milestone")

        def close_dialog(_):
            common.close(dlg)
            sfx.play("coin_many")
            self.render()

        recipe_tuple = grove.get_recipe_for_result(res_id)
        if recipe_tuple:
            recipe_note = (
                f"📖 Alchemy Formula Recorded: {emoji_a} + {emoji_b} ➔ {res_emoji} {res_name}"
            )
        else:
            recipe_note = (
                f"🌀 Essence Formula: {emoji_a} + {emoji_b} synthesized a rare Tier {res_tier} Spore!"
            )

        modal_col.controls = [
            ft.Container(
                ft.Text(
                    "🌟 LUCKY TIER MUTATION! 🌟" if is_mut else "✨ TRANSMUTATION SUCCESSFUL! ✨",
                    size=Type.CAPTION,
                    weight=ft.FontWeight.W_800,
                    color="#0D1F2D" if is_mut else "#FFFFFF",
                ),
                padding=ft.Padding.symmetric(horizontal=12, vertical=4),
                bgcolor=C.GOLD if is_mut else "#9D4EDD",
                border_radius=Radius.PILL,
            ),
            ft.Container(height=Space.XS),
            ft.Container(
                ft.Text(res_emoji, size=52),
                width=90,
                height=90,
                border_radius=Radius.LG,
                bgcolor=C.a(res_color, 0.25),
                border=ft.Border.all(2.5, res_color),
                alignment=ft.Alignment(0, 0),
            ),
            ft.Text(
                res_name,
                size=Type.TITLE,
                weight=ft.FontWeight.BOLD,
                color=C.TEXT,
                text_align=ft.TextAlign.CENTER,
            ),
            ft.Container(
                ft.Text(
                    f"Tier {res_tier} • {res_rarity}",
                    size=Type.CAPTION - 1,
                    weight=ft.FontWeight.BOLD,
                    color=res_color,
                ),
                padding=ft.Padding.symmetric(horizontal=10, vertical=3),
                bgcolor=C.a(res_color, 0.15),
                border_radius=Radius.PILL,
            ),
            ft.Container(
                ft.Text(
                    res_def.desc if res_def else "",
                    size=Type.CAPTION,
                    color=C.TEXT_DIM,
                    text_align=ft.TextAlign.CENTER,
                ),
                padding=ft.Padding.symmetric(horizontal=8),
            ),
            ft.Container(
                ft.Row(
                    [
                        ft.Row(
                            [
                                ft.Icon(ft.Icons.MONETIZATION_ON, size=14, color=C.GOLD),
                                ft.Text(
                                    f"+{res_yield} coins",
                                    size=Type.CAPTION,
                                    color=C.GOLD,
                                    weight=ft.FontWeight.BOLD,
                                ),
                            ],
                            spacing=4,
                        ),
                        ft.Row(
                            [
                                ft.Icon(ft.Icons.TIMER, size=14, color=C.TEXT_DIM),
                                ft.Text(
                                    f"{res_mins}m grow", size=Type.CAPTION, color=C.TEXT_DIM
                                ),
                            ],
                            spacing=4,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                    spacing=Space.MD,
                ),
                padding=ft.Padding.symmetric(horizontal=12, vertical=6),
                bgcolor=C.a(C.SURFACE_HI, 0.5),
                border_radius=Radius.MD,
            ),
            ft.Container(
                ft.Text(
                    recipe_note,
                    size=Type.CAPTION - 2,
                    color=C.GOLD,
                    text_align=ft.TextAlign.CENTER,
                ),
                padding=ft.Padding.symmetric(horizontal=4),
            ),
            ft.Container(height=Space.XS),
            ft.FilledButton(
                "Claim Flora Spore",
                icon=ft.Icons.CHECK_CIRCLE_ROUNDED,
                style=ft.ButtonStyle(
                    bgcolor="#06D6A0",
                    color="#0D1F2D",
                    shape=ft.RoundedRectangleBorder(radius=Radius.PILL),
                ),
                on_click=close_dialog,
            ),
        ]
        ui.refresh(dialog_content)


    def _open_altar_picker(self, is_slot_a: bool, state: grove.GroveState) -> None:
        items: list[ft.Control] = []
        for sid, count in sorted(state.seeds.items()):
            # If slot A already selected this seed, verify count >= 2
            available = count
            if not is_slot_a and self.selected_altar_a == sid:
                available -= 1
            if is_slot_a and self.selected_altar_b == sid:
                available -= 1
            if available <= 0:
                continue

            s_def = grove.get_seed(sid)
            if not s_def:
                continue

            def make_pick(target_sid: str):
                def do_pick(_):
                    if is_slot_a:
                        self.selected_altar_a = target_sid
                    else:
                        self.selected_altar_b = target_sid
                    common.close(bs)
                    self.render()
                return do_pick

            items.append(
                ft.Container(
                    ft.Row(
                        [
                            ft.Text(s_def.emoji, size=24),
                            ft.Column(
                                [
                                    ft.Text(
                                        f"{s_def.name} (x{available} avail)",
                                        size=Type.BODY,
                                        weight=ft.FontWeight.BOLD,
                                        color=C.TEXT,
                                    ),
                                    ft.Text(
                                        f"Tier {s_def.tier} • {s_def.rarity}",
                                        size=Type.CAPTION,
                                        color=C.TEXT_DIM,
                                    ),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                            ft.FilledButton(
                                "Select",
                                style=ft.ButtonStyle(
                                    bgcolor="#9D4EDD",
                                    color="#FFFFFF",
                                    shape=ft.RoundedRectangleBorder(radius=Radius.PILL),
                                ),
                                on_click=make_pick(sid),
                            ),
                        ],
                        spacing=Space.MD,
                    ),
                    padding=Space.SM,
                    border_radius=Radius.MD,
                    bgcolor=C.a(C.SURFACE_HI, 0.3),
                )
            )

        if not items:
            items.append(
                ft.Container(
                    ft.Text(
                        "No available seeds for fusion in inventory.",
                        size=Type.CAPTION,
                        color=C.TEXT_DIM,
                    ),
                    padding=Space.MD,
                )
            )

        bs = ft.BottomSheet(
            ft.Container(
                ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Text(
                                    f"Choose Seed for {'Slot A' if is_slot_a else 'Slot B'}",
                                    size=Type.TITLE,
                                    weight=ft.FontWeight.BOLD,
                                    color=C.TEXT,
                                ),
                                ft.IconButton(ft.Icons.CLOSE, on_click=lambda _: common.close(bs)),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                        ft.Divider(height=1, color=C.a(C.OUTLINE, 0.4)),
                        *items,
                    ],
                    spacing=Space.SM,
                    tight=True,
                ),
                padding=Space.LG,
                bgcolor=C.SURFACE,
                border_radius=ft.BorderRadius(top_left=Radius.LG, top_right=Radius.LG, bottom_left=0, bottom_right=0),
            )
        )
        self.app.page.show_dialog(bs)

    # ------------------------------------------------------------------ Silo & Almanac Tab
    def _silo_view(self, state: grove.GroveState) -> ft.Control:
        # Companion Level & Barter Mastery Card
        companion_id = getattr(self.app.game.profile, "equipped_companion", "")
        companion_name = "LUMA"
        if companion_id:
            c_item = cosmetics.get_cosmetic(companion_id, "companion")
            if c_item:
                companion_name = c_item.name

        luma_lvl = state.luma_level
        luma_xp = state.luma_xp
        needed_xp = grove.luma_xp_for_level(luma_lvl)
        xp_pct = min(1.0, max(0.0, luma_xp / max(1, needed_xp)))
        barter_mult = grove.luma_barter_multiplier(luma_lvl)
        barter_bonus_pct = round((barter_mult - 1.0) * 100)
        is_prem = bool(hasattr(self.app, "is_premium") and self.app.is_premium())

        if luma_lvl >= 10:
            perk_desc = "🌟 Max Barter (1.50x) • 8 Plots Active"
        elif luma_lvl >= 5:
            perk_desc = "🌱 7 Plots Active • Reach Lv 10 for Plot #8"
        else:
            perk_desc = "🌱 Reach Lv 5 to unlock Soil Plot #7"

        feed_card = common.card(
            ft.Column(
                [
                    ft.Row(
                        [
                            ft.Container(
                                ft.Icon(ft.Icons.PETS_ROUNDED, color=C.PRIMARY, size=24),
                                width=44,
                                height=44,
                                border_radius=Radius.MD,
                                bgcolor=C.a(C.PRIMARY, 0.2),
                                border=ft.Border.all(1.5, C.PRIMARY),
                                alignment=ft.Alignment(0, 0),
                            ),
                            ft.Column(
                                [
                                    ft.Row(
                                        [
                                            ft.Text(
                                                f"{companion_name} Companion",
                                                size=Type.BODY,
                                                weight=ft.FontWeight.BOLD,
                                                color=C.TEXT,
                                            ),
                                            ft.Container(
                                                ft.Text(
                                                    f"Lv {luma_lvl}",
                                                    size=Type.CAPTION - 2,
                                                    weight=ft.FontWeight.BOLD,
                                                    color=C.PRIMARY,
                                                ),
                                                padding=ft.Padding.symmetric(horizontal=6, vertical=1),
                                                bgcolor=C.a(C.PRIMARY, 0.2),
                                                border_radius=Radius.PILL,
                                            ),
                                            ft.Container(
                                                ft.Text(
                                                    f"+{barter_bonus_pct}% Barter",
                                                    size=Type.CAPTION - 2,
                                                    weight=ft.FontWeight.BOLD,
                                                    color=C.GOLD,
                                                ),
                                                padding=ft.Padding.symmetric(horizontal=6, vertical=1),
                                                bgcolor=C.a(C.GOLD, 0.2),
                                                border_radius=Radius.PILL,
                                            ),
                                        ],
                                        spacing=Space.XS,
                                    ),
                                    ft.Row(
                                        [
                                            ft.ProgressBar(
                                                value=xp_pct,
                                                color=C.PRIMARY,
                                                bgcolor=C.a(C.SURFACE_HI, 0.5),
                                                expand=True,
                                                height=6,
                                                border_radius=Radius.PILL,
                                            ),
                                            ft.Text(
                                                f"{luma_xp}/{needed_xp} XP",
                                                size=Type.CAPTION - 2,
                                                color=C.TEXT_DIM,
                                            ),
                                        ],
                                        spacing=Space.SM,
                                    ),
                                ],
                                spacing=4,
                                expand=True,
                            ),
                        ],
                        spacing=Space.SM,
                        alignment=ft.MainAxisAlignment.START,
                    ),
                    ft.Row(
                        [
                            ft.Text(
                                perk_desc + (" • ✨ Feast Active (+50% Feed XP)" if is_prem else ""),
                                size=Type.CAPTION - 1,
                                color=C.PRIMARY if is_prem else C.TEXT_DIM,
                                expand=True,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                ],
                spacing=Space.SM,
            ),
            tint=C.PRIMARY,
        )

        # Silo Inventory Cards
        almanac_rows: list[ft.Control] = []
        habit_origins = {
            "seed_aqua": "💧 Daily Water Log",
            "seed_solar": "☀️ Outdoor Runs & Walks",
            "seed_terra": "🪨 Gym Workouts",
            "seed_spirit": "🌙 Sleep & Focus",
        }

        for sid, sdef in sorted(grove.SEEDS.items(), key=lambda x: (x[1].tier, x[1].name)):
            in_seeds = state.seeds.get(sid, 0)
            in_harvest = state.harvested.get(sid, 0)
            discovered = (
                in_seeds > 0
                or in_harvest > 0
                or sid in state.discovered_fusions
                or sdef.tier == 1
            )

            rec_tuple = grove.get_recipe_for_result(sid)
            if discovered:
                if rec_tuple:
                    ing_a = grove.get_seed(rec_tuple[0])
                    ing_b = grove.get_seed(rec_tuple[1])
                    recipe_str = f"Formula: {ing_a.emoji if ing_a else ''} {ing_a.name if ing_a else rec_tuple[0]} + {ing_b.emoji if ing_b else ''} {ing_b.name if ing_b else rec_tuple[1]}"
                elif sid in habit_origins:
                    recipe_str = f"Origin: {habit_origins[sid]}"
                else:
                    recipe_str = "Origin: Botanical Altar Synthesis"
            else:
                recipe_str = (
                    f"Locked (Tier {sdef.tier}) • Tap for breeding hints"
                )

            def make_card_click(target_sdef: grove.SeedDef, is_disc: bool, s_cnt: int, h_cnt: int):
                return lambda _: self._open_flora_details(target_sdef, is_disc, s_cnt, h_cnt)

            actions_row = None
            if in_harvest > 0:
                sell_val = grove.sell_crop_value(sid, luma_lvl)
                feed_xp = grove.luma_crop_feed_xp(sid, is_prem)

                def make_sell_handler(crop_sid: str, s_val: int, c_name: str):
                    def handler(_):
                        earned = grove.sell_crop(state, crop_sid, 1)
                        self.app.game.profile.coins += earned
                        self.app.save()
                        self.app.refresh_profile()
                        sfx.play("reward_redeemed")
                        self.app.toast(
                            f"💰 Sold 1x {c_name} for {earned} coins! ({barter_mult:.2f}x barter rate)",
                            ft.Icons.MONETIZATION_ON,
                        )
                        self.render()
                    return handler

                def make_feed_handler(crop_sid: str, c_name: str):
                    def handler(_):
                        xp_gain, leveled = grove.feed_luma(state, crop_sid, is_premium=is_prem)
                        self.app.save()
                        self.app.refresh_profile()
                        if leveled:
                            sfx.play("level_up")
                            self.app.toast(
                                f"🎉 {companion_name} leveled up to Lv {state.luma_level}! Barter bonus increased to {grove.luma_barter_multiplier(state.luma_level):.2f}x!",
                                ft.Icons.AUTO_AWESOME,
                            )
                        else:
                            sfx.play("reward_redeemed")
                            self.app.toast(
                                f"✨ Fed 1x {c_name} to {companion_name}! +{xp_gain} Companion XP",
                                ft.Icons.PETS,
                            )
                        self.render()
                    return handler

                actions_row = ft.Row(
                    [
                        ft.Container(
                            ft.Row(
                                [
                                    ft.Icon(ft.Icons.MONETIZATION_ON, size=13, color=C.GOLD),
                                    ft.Text(f"Sell +{sell_val}", size=Type.CAPTION - 2, weight=ft.FontWeight.BOLD, color=C.GOLD),
                                ],
                                spacing=3,
                                tight=True,
                            ),
                            padding=ft.Padding.symmetric(horizontal=8, vertical=4),
                            bgcolor=C.a(C.GOLD, 0.15),
                            border_radius=Radius.PILL,
                            border=ft.Border.all(1, C.a(C.GOLD, 0.3)),
                            on_click=make_sell_handler(sid, sell_val, sdef.name),
                        ),
                        ft.Container(
                            ft.Row(
                                [
                                    ft.Icon(ft.Icons.RESTAURANT, size=13, color=C.PRIMARY),
                                    ft.Text(f"Feed +{feed_xp} XP", size=Type.CAPTION - 2, weight=ft.FontWeight.BOLD, color=C.PRIMARY),
                                ],
                                spacing=3,
                                tight=True,
                            ),
                            padding=ft.Padding.symmetric(horizontal=8, vertical=4),
                            bgcolor=C.a(C.PRIMARY, 0.15),
                            border_radius=Radius.PILL,
                            border=ft.Border.all(1, C.a(C.PRIMARY, 0.3)),
                            on_click=make_feed_handler(sid, sdef.name),
                        ),
                    ],
                    spacing=Space.XS,
                )

            card_content = ft.Column(
                [
                    ft.Row(
                        [
                            ft.Container(
                                ft.Text(sdef.emoji if discovered else "❓", size=22),
                                width=42,
                                height=42,
                                border_radius=Radius.SM,
                                bgcolor=C.a(sdef.color if discovered else C.TEXT_DIM, 0.2),
                                border=ft.Border.all(
                                    1, sdef.color if discovered else C.a(C.OUTLINE, 0.4)
                                ),
                                alignment=ft.Alignment(0, 0),
                            ),
                            ft.Column(
                                [
                                    ft.Row(
                                        [
                                            ft.Text(
                                                sdef.name if discovered else "Undiscovered Flora",
                                                size=Type.BODY,
                                                weight=ft.FontWeight.BOLD,
                                                color=C.TEXT if discovered else C.TEXT_DIM,
                                            ),
                                            ft.Container(
                                                ft.Text(
                                                    f"T{sdef.tier} • {sdef.rarity}",
                                                    size=Type.CAPTION - 3,
                                                    weight=ft.FontWeight.BOLD,
                                                    color=sdef.color if discovered else C.TEXT_DIM,
                                                ),
                                                padding=ft.Padding.symmetric(
                                                    horizontal=6, vertical=1
                                                ),
                                                bgcolor=C.a(
                                                    sdef.color if discovered else C.TEXT_DIM, 0.15
                                                ),
                                                border_radius=Radius.PILL,
                                            ),
                                        ],
                                        spacing=Space.XS,
                                    ),
                                    ft.Text(
                                        recipe_str,
                                        size=Type.CAPTION - 1,
                                        color=C.GOLD if discovered and rec_tuple else C.TEXT_DIM,
                                        no_wrap=True,
                                    ),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                            ft.Row(
                                [
                                    ft.Container(
                                        ft.Text(
                                            f"Seeds: {in_seeds}",
                                            size=Type.CAPTION - 1,
                                            color=C.TEXT,
                                        ),
                                        padding=ft.Padding.symmetric(horizontal=6, vertical=2),
                                        bgcolor=C.a(C.SURFACE_HI, 0.5),
                                        border_radius=Radius.PILL,
                                    ),
                                    ft.Container(
                                        ft.Text(
                                            f"Harvest: {in_harvest}",
                                            size=Type.CAPTION - 1,
                                            color=C.GOLD,
                                        ),
                                        padding=ft.Padding.symmetric(horizontal=6, vertical=2),
                                        bgcolor=C.a(C.GOLD, 0.15),
                                        border_radius=Radius.PILL,
                                    ),
                                    ft.Icon(ft.Icons.CHEVRON_RIGHT, size=16, color=C.TEXT_DIM),
                                ],
                                spacing=4,
                            ),
                        ],
                        spacing=Space.SM,
                    ),
                ],
                spacing=Space.XS,
            )
            if actions_row:
                card_content.controls.append(actions_row)

            almanac_rows.append(
                ft.Container(
                    card_content,
                    padding=Space.SM,
                    border_radius=Radius.MD,
                    bgcolor=C.a(C.SURFACE, 0.35),
                    border=ft.Border.all(1, C.a(C.OUTLINE, 0.2)),
                    on_click=make_card_click(sdef, discovered, in_seeds, in_harvest),
                )
            )

        recipes = grove.get_recipes_list()
        discovered_recipes = sum(
            1 for r in recipes if grove.is_recipe_discovered(state, r["result_id"])
        )

        almanac_card = common.card(
            ft.Column(
                [
                    ft.Row(
                        [
                            ft.Row(
                                [
                                    ft.Icon(
                                        ft.Icons.AUTO_STORIES_ROUNDED, color="#06D6A0", size=22
                                    ),
                                    ft.Column(
                                        [
                                            ft.Text(
                                                "BOTANICAL ALMANAC & SILO",
                                                size=Type.CAPTION,
                                                weight=ft.FontWeight.BOLD,
                                                color="#06D6A0",
                                            ),
                                            ft.Text(
                                                f"Species: {len([s for s in grove.SEEDS if state.seeds.get(s, 0) > 0 or state.harvested.get(s, 0) > 0 or s in state.discovered_fusions or grove.get_seed(s).tier == 1])}/16 Flora • {discovered_recipes}/12 Recipes",
                                                size=Type.CAPTION - 2,
                                                color=C.TEXT_DIM,
                                            ),
                                        ],
                                        spacing=0,
                                    ),
                                ],
                                spacing=Space.SM,
                            ),
                            ft.Container(
                                ft.Row(
                                    [
                                        ft.Icon(
                                            ft.Icons.MENU_BOOK_ROUNDED, size=13, color="#06D6A0"
                                        ),
                                        ft.Text(
                                            "Alchemy Codex",
                                            size=Type.CAPTION - 2,
                                            color="#06D6A0",
                                            weight=ft.FontWeight.BOLD,
                                        ),
                                    ],
                                    spacing=4,
                                    tight=True,
                                ),
                                padding=ft.Padding.symmetric(horizontal=8, vertical=4),
                                bgcolor=C.a("#06D6A0", 0.15),
                                border_radius=Radius.PILL,
                                border=ft.Border.all(1, C.a("#06D6A0", 0.3)),
                                on_click=lambda _: self._open_recipe_codex(state),
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Text(
                        "Tap any flora to view growth time, coin yield, and exact alchemy recipes.",
                        size=Type.CAPTION - 1,
                        color=C.TEXT_DIM,
                    ),
                    ft.Divider(height=1, color=C.a(C.OUTLINE, 0.4)),
                    *almanac_rows,
                ],
                spacing=Space.SM,
            ),
            tint="#06D6A0",
        )

        return ft.Column([feed_card, almanac_card], spacing=Space.MD)

    def _open_recipe_codex(self, state: grove.GroveState) -> None:
        recipes = grove.get_recipes_list()
        discovered_count = sum(
            1 for r in recipes if grove.is_recipe_discovered(state, r["result_id"])
        )

        # Group by tier
        tier_groups: dict[int, list[dict[str, Any]]] = {2: [], 3: [], 4: []}
        for r in recipes:
            t = r["tier"]
            if t in tier_groups:
                tier_groups[t].append(r)

        tier_titles = {
            2: "Tier 2: Elemental Hybrids (From 2 Base Spores)",
            3: "Tier 3: Mystical Flora (From 2 Tier 2 Hybrids)",
            4: "Tier 4: Mythic World Tree Flora (Ancient Cross-Breeds)",
        }

        codex_controls: list[ft.Control] = []

        for tier in (2, 3, 4):
            t_recipes = tier_groups.get(tier, [])
            if not t_recipes:
                continue
            codex_controls.append(
                ft.Container(
                    ft.Text(
                        tier_titles[tier],
                        size=Type.CAPTION,
                        weight=ft.FontWeight.BOLD,
                        color=C.GOLD,
                    ),
                    padding=ft.Padding.only(top=6, bottom=2),
                )
            )
            for r in t_recipes:
                is_disc = grove.is_recipe_discovered(state, r["result_id"])
                res = r["result_seed"]
                ing_a = r["ingredient_a"]
                ing_b = r["ingredient_b"]

                res_display_name = res.name if is_disc else f"??? (Tier {tier} Hybrid)"
                res_display_emoji = res.emoji if is_disc else "❓"
                res_color = res.color if is_disc else C.TEXT_DIM

                card_content = ft.Row(
                    [
                        # Ingredient A
                        ft.Container(
                            ft.Row(
                                [
                                    ft.Text(ing_a.emoji, size=15),
                                    ft.Text(
                                        ing_a.name,
                                        size=Type.CAPTION - 2,
                                        color=C.TEXT,
                                        weight=ft.FontWeight.BOLD,
                                    ),
                                ],
                                spacing=4,
                                tight=True,
                            ),
                            padding=ft.Padding.symmetric(horizontal=6, vertical=3),
                            bgcolor=C.a(ing_a.color, 0.15),
                            border_radius=Radius.PILL,
                        ),
                        ft.Text(
                            "+", size=Type.CAPTION, weight=ft.FontWeight.BOLD, color=C.TEXT_DIM
                        ),
                        # Ingredient B
                        ft.Container(
                            ft.Row(
                                [
                                    ft.Text(ing_b.emoji, size=15),
                                    ft.Text(
                                        ing_b.name,
                                        size=Type.CAPTION - 2,
                                        color=C.TEXT,
                                        weight=ft.FontWeight.BOLD,
                                    ),
                                ],
                                spacing=4,
                                tight=True,
                            ),
                            padding=ft.Padding.symmetric(horizontal=6, vertical=3),
                            bgcolor=C.a(ing_b.color, 0.15),
                            border_radius=Radius.PILL,
                        ),
                        ft.Icon(ft.Icons.ARROW_FORWARD, size=13, color=C.GOLD),
                        # Result
                        ft.Container(
                            ft.Row(
                                [
                                    ft.Text(res_display_emoji, size=15),
                                    ft.Text(
                                        res_display_name,
                                        size=Type.CAPTION - 2,
                                        color=res_color,
                                        weight=ft.FontWeight.BOLD,
                                    ),
                                    *(
                                        [ft.Icon(ft.Icons.CHECK_CIRCLE, size=12, color="#06D6A0")]
                                        if is_disc
                                        else []
                                    ),
                                ],
                                spacing=4,
                                tight=True,
                            ),
                            padding=ft.Padding.symmetric(horizontal=6, vertical=3),
                            bgcolor=C.a(res_color, 0.18),
                            border_radius=Radius.PILL,
                            border=ft.Border.all(
                                1, res_color if is_disc else C.a(C.OUTLINE, 0.4)
                            ),
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.START,
                    spacing=Space.XS,
                    wrap=True,
                )

                codex_controls.append(
                    ft.Container(
                        card_content,
                        padding=ft.Padding.symmetric(horizontal=8, vertical=6),
                        bgcolor=C.a(C.SURFACE_HI, 0.35) if is_disc else C.a(C.SURFACE, 0.4),
                        border_radius=Radius.MD,
                        border=ft.Border.all(
                            1, C.a(res_color, 0.3) if is_disc else C.a(C.OUTLINE, 0.3)
                        ),
                    )
                )

        bs = ft.BottomSheet(
            ft.Container(
                ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Row(
                                    [
                                        ft.Icon(
                                            ft.Icons.MENU_BOOK_ROUNDED, color="#9D4EDD", size=22
                                        ),
                                        ft.Column(
                                            [
                                                ft.Text(
                                                    "BOTANICAL ALCHEMY CODEX",
                                                    size=Type.BODY,
                                                    weight=ft.FontWeight.BOLD,
                                                    color=C.TEXT,
                                                ),
                                                ft.Text(
                                                    f"Discovered: {discovered_count} / {len(recipes)} Formulas",
                                                    size=Type.CAPTION - 1,
                                                    color="#9D4EDD",
                                                    weight=ft.FontWeight.BOLD,
                                                ),
                                            ],
                                            spacing=0,
                                        ),
                                    ],
                                    spacing=Space.SM,
                                ),
                                ft.IconButton(ft.Icons.CLOSE, on_click=lambda _: common.close(bs)),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                        ft.Text(
                            "Every cross-breeding combination in LUMA is a fixed alchemical formula. Fuse these exact pairs at the Altar to unlock each plant species!",
                            size=Type.CAPTION,
                            color=C.TEXT_DIM,
                        ),
                        ft.Divider(height=1, color=C.a(C.OUTLINE, 0.4)),
                        *codex_controls,
                    ],
                    spacing=Space.SM,
                    tight=True,
                    scroll=ft.ScrollMode.AUTO,
                ),
                padding=Space.LG,
                bgcolor=C.SURFACE,
                border_radius=ft.BorderRadius(
                    top_left=Radius.LG, top_right=Radius.LG, bottom_left=0, bottom_right=0
                ),
            ),
            scrollable=True,
        )
        self.app.page.show_dialog(bs)

    def _open_flora_details(
        self, sdef: grove.SeedDef, discovered: bool, in_seeds: int, in_harvest: int
    ) -> None:
        rec_tuple = grove.get_recipe_for_result(sdef.id)
        if rec_tuple:
            ing_a = grove.get_seed(rec_tuple[0])
            ing_b = grove.get_seed(rec_tuple[1])
            formula_text = f"{ing_a.emoji if ing_a else ''} {ing_a.name if ing_a else rec_tuple[0]}  +  {ing_b.emoji if ing_b else ''} {ing_b.name if ing_b else rec_tuple[1]}"
        elif sdef.tier == 1:
            origins = {
                "seed_aqua": "💧 Daily Water Log (Staying hydrated)",
                "seed_solar": "☀️ Outdoor Runs & Walks (GPS tracking)",
                "seed_terra": "🪨 Gym & Workout Sessions",
                "seed_spirit": "🌙 Mindful Sleep & Focus Sessions",
            }
            formula_text = origins.get(sdef.id, "Earned via real-world fitness habits")
        else:
            formula_text = "Synthesized at the Botanical Altar"

        mins = sdef.growth_time_s // 60
        state: grove.GroveState = getattr(self.app.game.data, "grove", None) or grove.GroveState()
        luma_lvl = state.luma_level
        barter_mult = grove.luma_barter_multiplier(luma_lvl)
        sell_val = grove.sell_crop_value(sdef.id, luma_lvl)
        is_prem = bool(hasattr(self.app, "is_premium") and self.app.is_premium())
        feed_xp = grove.luma_crop_feed_xp(sdef.id, is_prem)

        bs = ft.BottomSheet(
            ft.Container(
                ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Text(
                                    "Flora Dossier",
                                    size=Type.TITLE,
                                    weight=ft.FontWeight.BOLD,
                                    color=C.TEXT,
                                ),
                                ft.IconButton(ft.Icons.CLOSE, on_click=lambda _: common.close(bs)),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                        ft.Divider(height=1, color=C.a(C.OUTLINE, 0.4)),
                        ft.Row(
                            [
                                ft.Container(
                                    ft.Text(sdef.emoji if discovered else "❓", size=40),
                                    width=68,
                                    height=68,
                                    border_radius=Radius.MD,
                                    bgcolor=C.a(sdef.color if discovered else C.TEXT_DIM, 0.2),
                                    border=ft.Border.all(
                                        2, sdef.color if discovered else C.OUTLINE
                                    ),
                                    alignment=ft.Alignment(0, 0),
                                ),
                                ft.Column(
                                    [
                                        ft.Text(
                                            sdef.name if discovered else "Undiscovered Flora",
                                            size=Type.TITLE,
                                            weight=ft.FontWeight.BOLD,
                                            color=C.TEXT if discovered else C.TEXT_DIM,
                                        ),
                                        ft.Container(
                                            ft.Text(
                                                f"Tier {sdef.tier} • {sdef.rarity}",
                                                size=Type.CAPTION - 1,
                                                weight=ft.FontWeight.BOLD,
                                                color=sdef.color if discovered else C.TEXT_DIM,
                                            ),
                                            padding=ft.Padding.symmetric(horizontal=8, vertical=2),
                                            bgcolor=C.a(
                                                sdef.color if discovered else C.TEXT_DIM, 0.15
                                            ),
                                            border_radius=Radius.PILL,
                                        ),
                                    ],
                                    spacing=4,
                                    expand=True,
                                    alignment=ft.MainAxisAlignment.CENTER,
                                ),
                            ],
                            spacing=Space.MD,
                        ),
                        ft.Text(
                            sdef.desc
                            if discovered
                            else "Keep cross-breeding seeds at the Botanical Altar to unlock this mysterious flora and its alchemical entry in your Almanac.",
                            size=Type.BODY,
                            color=C.TEXT if discovered else C.TEXT_DIM,
                        ),
                        ft.Container(
                            ft.Column(
                                [
                                    ft.Text(
                                        "HOW TO OBTAIN / SYNTHESIS RECIPE",
                                        size=Type.CAPTION - 2,
                                        weight=ft.FontWeight.W_800,
                                        color=C.GOLD,
                                    ),
                                    ft.Text(
                                        formula_text,
                                        size=Type.BODY,
                                        weight=ft.FontWeight.BOLD,
                                        color=C.TEXT,
                                    ),
                                ],
                                spacing=4,
                            ),
                            padding=Space.SM,
                            bgcolor=C.a(C.SURFACE_HI, 0.5),
                            border_radius=Radius.MD,
                        ),
                        ft.Row(
                            [
                                ft.Container(
                                    ft.Column(
                                        [
                                            ft.Text(
                                                "GROW TIME", size=Type.CAPTION - 3, color=C.TEXT_DIM
                                            ),
                                            ft.Text(
                                                f"{mins} mins",
                                                size=Type.BODY,
                                                weight=ft.FontWeight.BOLD,
                                                color=C.TEXT,
                                            ),
                                        ],
                                        spacing=2,
                                    ),
                                    padding=Space.SM,
                                    bgcolor=C.a(C.SURFACE, 0.5),
                                    border_radius=Radius.MD,
                                    expand=True,
                                ),
                                ft.Container(
                                    ft.Column(
                                        [
                                            ft.Text(
                                                "MARKET VALUE", size=Type.CAPTION - 3, color=C.GOLD
                                            ),
                                            ft.Text(
                                                f"+{sell_val} coins",
                                                size=Type.BODY,
                                                weight=ft.FontWeight.BOLD,
                                                color=C.GOLD,
                                            ),
                                            ft.Text(
                                                f"x{barter_mult:.2f} barter",
                                                size=Type.CAPTION - 3,
                                                color=C.TEXT_DIM,
                                            ),
                                        ],
                                        spacing=1,
                                    ),
                                    padding=Space.SM,
                                    bgcolor=C.a(C.SURFACE, 0.5),
                                    border_radius=Radius.MD,
                                    expand=True,
                                ),
                                ft.Container(
                                    ft.Column(
                                        [
                                            ft.Text(
                                                "FEED XP", size=Type.CAPTION - 3, color=C.PRIMARY
                                            ),
                                            ft.Text(
                                                f"+{feed_xp} XP",
                                                size=Type.BODY,
                                                weight=ft.FontWeight.BOLD,
                                                color=C.PRIMARY,
                                            ),
                                            ft.Text(
                                                "Companion",
                                                size=Type.CAPTION - 3,
                                                color=C.TEXT_DIM,
                                            ),
                                        ],
                                        spacing=1,
                                    ),
                                    padding=Space.SM,
                                    bgcolor=C.a(C.SURFACE, 0.5),
                                    border_radius=Radius.MD,
                                    expand=True,
                                ),
                            ],
                            spacing=Space.SM,
                        ),
                    ],
                    spacing=Space.MD,
                    tight=True,
                ),
                padding=Space.LG,
                bgcolor=C.SURFACE,
                border_radius=ft.BorderRadius(
                    top_left=Radius.LG, top_right=Radius.LG, bottom_left=0, bottom_right=0
                ),
            ),
            scrollable=True,
        )

        if in_harvest > 0:
            def on_sell_dossier(_):
                common.close(bs)
                earned = grove.sell_crop(state, sdef.id, 1)
                self.app.game.profile.coins += earned
                self.app.save()
                self.app.refresh_profile()
                sfx.play("reward_redeemed")
                self.app.toast(
                    f"💰 Sold 1x {sdef.name} for {earned} coins! ({barter_mult:.2f}x barter rate)",
                    ft.Icons.MONETIZATION_ON,
                )
                self.render()

            def on_feed_dossier(_):
                common.close(bs)
                xp_gain, leveled = grove.feed_luma(state, sdef.id, is_premium=is_prem)
                self.app.save()
                self.app.refresh_profile()
                if leveled:
                    sfx.play("level_up")
                    self.app.toast(
                        f"🎉 LUMA leveled up to Lv {state.luma_level}! Barter bonus increased to {grove.luma_barter_multiplier(state.luma_level):.2f}x!",
                        ft.Icons.AUTO_AWESOME,
                    )
                else:
                    sfx.play("reward_redeemed")
                    self.app.toast(
                        f"✨ Fed 1x {sdef.name} to LUMA! +{xp_gain} Companion XP",
                        ft.Icons.PETS,
                    )
                self.render()

            bs.content.content.controls.append(
                ft.Row(
                    [
                        ft.FilledButton(
                            f"Sell 1x (+{sell_val})",
                            icon=ft.Icons.MONETIZATION_ON,
                            style=ft.ButtonStyle(
                                bgcolor=C.GOLD,
                                color=C.BG,
                                shape=ft.RoundedRectangleBorder(radius=Radius.PILL),
                            ),
                            on_click=on_sell_dossier,
                            expand=True,
                        ),
                        ft.FilledButton(
                            f"Feed (+{feed_xp} XP)",
                            icon=ft.Icons.RESTAURANT,
                            style=ft.ButtonStyle(
                                bgcolor=C.PRIMARY,
                                color=C.TEXT,
                                shape=ft.RoundedRectangleBorder(radius=Radius.PILL),
                            ),
                            on_click=on_feed_dossier,
                            expand=True,
                        ),
                    ],
                    spacing=Space.SM,
                )
            )

        self.app.page.show_dialog(bs)

