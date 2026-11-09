"""Mind Grove: The Fitness Farm screen for LUMA.

Real-world health and workouts fuel crop growth, seed cross-breeding, and botanical rewards.
"""

from __future__ import annotations

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
                                        ft.Icon(ft.Icons.MONETIZATION_ON, size=15, color=C.GOLD),
                                        ft.Text(
                                            f"{self.app.game.profile.coins}",
                                            size=Type.CAPTION,
                                            weight=ft.FontWeight.BOLD,
                                            color=C.GOLD,
                                        ),
                                    ],
                                    spacing=4,
                                    tight=True,
                                ),
                                padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                                bgcolor=C.a(C.GOLD, 0.15),
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
                coins, bonus = grove.harvest_crop(state, plot.plot_id)
                self.app.game.profile.coins += coins
                self.app.save()
                sfx.play("coin")
                sfx.play("quest_done")

                bonus_names = [grove.get_seed(b).name if grove.get_seed(b) else b for b in bonus]
                toast_msg = f"🌾 Harvested {seed_name}! +{coins} coins"
                if bonus_names:
                    toast_msg += f" & found {', '.join(bonus_names)}!"
                self.app.toast(toast_msg, ft.Icons.AUTO_AWESOME)
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
                                    ft.Text(
                                        f"Plot #{plot.plot_id + 1} • Tier {seed.tier if seed else 1}",
                                        size=Type.CAPTION,
                                        color=C.TEXT_DIM,
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
        preview_text = "Select 2 seeds to synthesize a rare botanical hybrid"
        can_fuse = bool(self.selected_altar_a and self.selected_altar_b)
        if can_fuse:
            pair = frozenset({self.selected_altar_a, self.selected_altar_b})
            if pair in grove.FUSION_RECIPES:
                res_id = grove.FUSION_RECIPES[pair]
                res_def = grove.get_seed(res_id)
                preview_text = f"✨ Synthesis Match: {res_def.name if res_def else res_id} ({res_def.rarity if res_def else ''})!"
            else:
                preview_text = "🌀 Essence Fusion: Will synthesize a hybrid seed!"

        def on_fuse_click(_):
            if not self.selected_altar_a or not self.selected_altar_b:
                return
            res_id, is_mut = grove.fuse_seeds(
                state, self.selected_altar_a, self.selected_altar_b
            )
            self.selected_altar_a = None
            self.selected_altar_b = None
            self.app.save()

            res_def = grove.get_seed(res_id)
            name = res_def.name if res_def else res_id
            emoji = res_def.emoji if res_def else "🌱"

            sfx.play("level_up")
            mut_text = " 🌟 LUCKY TIER MUTATION!" if is_mut else ""
            self.app.toast(f"Synthesized {emoji} {name}!{mut_text}", ft.Icons.AUTO_AWESOME)
            self.render()

        return common.card(
            ft.Column(
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
                    ft.Text(
                        "Cross-breed two seeds to create higher-tier flora, unlock new species in your Almanac, and multiply harvest coins.",
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
                    ft.Text(
                        preview_text,
                        size=Type.CAPTION,
                        color=C.GOLD if can_fuse else C.TEXT_DIM,
                        text_align=ft.TextAlign.CENTER,
                    ),
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
        # Feed Companion section
        companion_id = getattr(self.app.game.profile, "equipped_companion", "")
        companion_name = "LUMA"
        if companion_id:
            c_item = cosmetics.get_cosmetic(companion_id, "companion")
            if c_item:
                companion_name = c_item.name

        def on_feed_companion(_):
            # Consume 1 harvested crop if available
            available_crops = [k for k, v in state.harvested.items() if v > 0]
            if not available_crops:
                self.app.toast("Harvest some crops first to feed your companion!", ft.Icons.INFO_OUTLINE)
                return
            chosen_crop = available_crops[0]
            state.harvested[chosen_crop] -= 1
            if state.harvested[chosen_crop] <= 0:
                del state.harvested[chosen_crop]
            self.app.save()

            crop_def = grove.get_seed(chosen_crop)
            c_name = crop_def.name if crop_def else "Harvest"
            sfx.play("reward_redeemed")
            self.app.toast(f"✨ Fed {c_name} to {companion_name}! +10% daily coin boost active!", ft.Icons.PETS)
            self.render()

        feed_card = common.card(
            ft.Row(
                [
                    ft.Icon(ft.Icons.PETS_ROUNDED, color=C.PRIMARY, size=28),
                    ft.Column(
                        [
                            ft.Text(
                                f"Feed {companion_name}",
                                size=Type.BODY,
                                weight=ft.FontWeight.BOLD,
                                color=C.TEXT,
                            ),
                            ft.Text(
                                "Offer harvested crops for companion affection & +10% coin boost.",
                                size=Type.CAPTION,
                                color=C.TEXT_DIM,
                            ),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    ft.FilledButton(
                        "Feed",
                        icon=ft.Icons.RESTAURANT,
                        style=ft.ButtonStyle(
                            bgcolor=C.PRIMARY,
                            color=C.TEXT,
                            shape=ft.RoundedRectangleBorder(radius=Radius.PILL),
                        ),
                        on_click=on_feed_companion,
                    ),
                ],
                spacing=Space.MD,
            ),
            tint="#06D6A0",
        )

        # Silo Inventory Cards
        almanac_rows: list[ft.Control] = []
        for sid, sdef in sorted(grove.SEEDS.items(), key=lambda x: (x[1].tier, x[1].name)):
            in_seeds = state.seeds.get(sid, 0)
            in_harvest = state.harvested.get(sid, 0)
            discovered = in_seeds > 0 or in_harvest > 0 or sid in state.discovered_fusions or sdef.tier == 1

            almanac_rows.append(
                ft.Container(
                    ft.Row(
                        [
                            ft.Container(
                                ft.Text(sdef.emoji if discovered else "❓", size=22),
                                width=40,
                                height=40,
                                border_radius=Radius.SM,
                                bgcolor=C.a(sdef.color if discovered else C.TEXT_DIM, 0.2),
                                alignment=ft.Alignment(0, 0),
                            ),
                            ft.Column(
                                [
                                    ft.Text(
                                        sdef.name if discovered else "Undiscovered Flora",
                                        size=Type.BODY,
                                        weight=ft.FontWeight.BOLD,
                                        color=C.TEXT if discovered else C.TEXT_DIM,
                                    ),
                                    ft.Text(
                                        f"Tier {sdef.tier} • {sdef.rarity}" if discovered else "Synthesize at the Botanical Altar",
                                        size=Type.CAPTION,
                                        color=C.TEXT_DIM,
                                    ),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                            ft.Row(
                                [
                                    ft.Container(
                                        ft.Text(f"Seeds: {in_seeds}", size=Type.CAPTION - 1, color=C.TEXT),
                                        padding=ft.Padding.symmetric(horizontal=6, vertical=2),
                                        bgcolor=C.a(C.SURFACE_HI, 0.5),
                                        border_radius=Radius.PILL,
                                    ),
                                    ft.Container(
                                        ft.Text(f"Harvested: {in_harvest}", size=Type.CAPTION - 1, color=C.GOLD),
                                        padding=ft.Padding.symmetric(horizontal=6, vertical=2),
                                        bgcolor=C.a(C.GOLD, 0.15),
                                        border_radius=Radius.PILL,
                                    ),
                                ],
                                spacing=4,
                            ),
                        ],
                        spacing=Space.MD,
                    ),
                    padding=Space.SM,
                    border_radius=Radius.MD,
                    bgcolor=C.a(C.SURFACE, 0.3),
                )
            )

        almanac_card = common.card(
            ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.AUTO_STORIES_ROUNDED, color="#06D6A0", size=22),
                            ft.Text(
                                "BOTANICAL ALMANAC & SILO",
                                size=Type.CAPTION,
                                weight=ft.FontWeight.BOLD,
                                color="#06D6A0",
                            ),
                        ],
                        spacing=Space.SM,
                    ),
                    ft.Text(
                        f"Discovered species: {len([s for s in grove.SEEDS if state.seeds.get(s, 0) > 0 or state.harvested.get(s, 0) > 0 or s in state.discovered_fusions or grove.get_seed(s).tier == 1])}/16 Flora",
                        size=Type.CAPTION,
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
