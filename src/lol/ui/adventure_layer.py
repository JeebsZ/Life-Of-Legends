from __future__ import annotations

import contextlib
from collections.abc import Callable

import flet as ft

from lol.core.adventure import (
    AdventureEngine,
    Creature,
    CreatureTier,
    EventType,
    TargetMode,
)


class AdventureRunCard(ft.Container):
    """Mobile-optimized Flet card that overlays creature clusters,

    target status, and combat events directly onto the Run screen.
    """

    def __init__(
        self,
        engine: AdventureEngine,
        on_play_sound: Callable[[str], None] | None = None,
        on_target_changed: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__()
        self.engine = engine
        self.on_play_sound = on_play_sound
        self.on_target_changed = on_target_changed

        self.padding = 14
        self.border_radius = 16
        self.bgcolor = "#161D2B"  # Matching dark palette from user screenshot
        self.border = ft.border.all(1, "#263248")

        self.status_title = ft.Text(
            "Scouting Path...",
            size=14,
            weight=ft.FontWeight.W_600,
            color="#94A3B8",
        )
        self.dps_badge = ft.Container(
            content=ft.Text(
                "0 DPS", size=12, weight=ft.FontWeight.BOLD, color="#38BDF8"
            ),
            padding=ft.padding.symmetric(horizontal=8, vertical=4),
            border_radius=8,
            bgcolor="#0F243A",
        )
        self.combat_ticker = ft.Text(
            "Maintain jogging pace to deal damage.",
            size=12,
            color="#64748B",
            italic=True,
            no_wrap=True,
        )

        self.creatures_row = ft.Row(
            spacing=8,
            scroll=ft.ScrollMode.ADAPTIVE,
            alignment=ft.MainAxisAlignment.START,
        )

        self.content = ft.Column(
            spacing=10,
            controls=[
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    controls=[self.status_title, self.dps_badge],
                ),
                self.creatures_row,
                ft.Divider(height=1, color="#1E293B"),
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    controls=[
                        ft.Row(
                            spacing=6,
                            controls=[
                                ft.Icon(
                                    ft.Icons.FLASH_ON_ROUNDED,
                                    size=16,
                                    color="#F59E0B",
                                ),
                                self.combat_ticker,
                            ],
                        ),
                        ft.IconButton(
                            icon=ft.Icons.CENTER_FOCUS_STRONG_ROUNDED,
                            tooltip="Auto-Target: Lowest HP",
                            icon_size=18,
                            icon_color="#38BDF8",
                            on_click=self._toggle_target_mode,
                        ),
                    ],
                ),
            ],
        )

    def _safe_update(self) -> None:
        if getattr(self, "page", None):
            with contextlib.suppress(Exception):
                self.update()

    def _toggle_target_mode(self, e: ft.ControlEvent) -> None:
        if self.engine.target_mode == TargetMode.LOWEST_HP:
            self.engine.target_mode = TargetMode.STRONGEST
            e.control.tooltip = "Auto-Target: Strongest"
            e.control.icon_color = "#EC4899"
        else:
            self.engine.target_mode = TargetMode.LOWEST_HP
            e.control.tooltip = "Auto-Target: Lowest HP"
            e.control.icon_color = "#38BDF8"
        self._safe_update()

    def _build_creature_badge(
        self, creature: Creature, is_target: bool
    ) -> ft.Container:
        tier_colors = {
            CreatureTier.NORMAL: "#38BDF8",
            CreatureTier.LEADER: "#F59E0B",
            CreatureTier.BOSS: "#A855F7",
        }
        accent = tier_colors.get(creature.tier, "#38BDF8")

        # Color-code HP bar
        hp_ratio = creature.hp_percent
        hp_color = (
            "#10B981"
            if hp_ratio > 0.5
            else "#F59E0B" if hp_ratio > 0.25 else "#EF4444"
        )

        return ft.Container(
            width=100,
            padding=8,
            border_radius=12,
            bgcolor="#0B1320" if is_target else "#111827",
            border=ft.border.all(
                2 if is_target else 1, accent if is_target else "#1F2937"
            ),
            content=ft.Column(
                spacing=4,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Text(
                        creature.name,
                        size=11,
                        weight=ft.FontWeight.BOLD,
                        color="#F8FAFC",
                        no_wrap=True,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    ft.ProgressBar(
                        value=hp_ratio,
                        color=hp_color,
                        bgcolor="#1E293B",
                        height=6,
                        border_radius=4,
                    ),
                    ft.Text(
                        f"{int(creature.current_hp)}/{int(creature.max_hp)}",
                        size=10,
                        color="#94A3B8",
                    ),
                ],
            ),
            on_click=lambda _: self._on_select_manual(creature.id),
        )

    def _on_select_manual(self, creature_id: str) -> None:
        self.engine.manual_target_id = creature_id
        self.engine.target_mode = TargetMode.MANUAL
        if self.on_target_changed:
            self.on_target_changed(creature_id)
        self.refresh_display(current_speed_kmh=0.0)

    def refresh_display(self, current_speed_kmh: float = 0.0) -> None:
        """Refreshes the HUD controls with latest engine state."""
        dps, _ = self.engine.calculate_dps(current_speed_kmh)
        self.dps_badge.content.value = f"{int(dps)} DPS"

        cluster = self.engine.active_cluster
        if not cluster or not cluster.has_alive:
            self.status_title.value = "Peaceful Stride · Scouting Ahead"
            self.creatures_row.controls = [
                ft.Text(
                    "No active creatures. Next pack in ~350m.",
                    size=12,
                    color="#64748B",
                )
            ]
        else:
            alive_count = len(cluster.alive_creatures)
            has_boss = any(
                c.tier == CreatureTier.BOSS for c in cluster.alive_creatures
            )
            self.status_title.value = (
                f"BOSS ENCOUNTER ({alive_count} left)"
                if has_boss
                else f"Pack Encounter ({alive_count} mobs)"
            )

            current_target = cluster.select_target(
                mode=self.engine.target_mode,
                manual_id=self.engine.manual_target_id,
            )
            target_id = current_target.id if current_target else None

            self.creatures_row.controls = [
                self._build_creature_badge(
                    creature=c, is_target=(c.id == target_id)
                )
                for c in cluster.alive_creatures
            ]

        self._safe_update()

    def process_tick_events(self, events: list) -> None:
        """Processes events from update_tick to trigger audio cues and banner messages."""
        for event in events:
            if event.event_type == EventType.CREATURE_DEFEATED:
                self.combat_ticker.value = f"Defeated {event.target_name}! +{event.xp_gained} XP, +${event.coins_gained}"
                if self.on_play_sound:
                    self.on_play_sound("slime_defeat.ogg")
            elif event.event_type == EventType.MILESTONE_SURGE:
                self.combat_ticker.value = event.message
                if self.on_play_sound:
                    self.on_play_sound("milestone_surge.ogg")
            elif event.event_type == EventType.SPAWN_CLUSTER:
                self.combat_ticker.value = "New creature pack engaged!"
                if self.on_play_sound:
                    self.on_play_sound("cluster_spawn.ogg")
            elif event.event_type == EventType.DAMAGE_DEALT and event.is_crit:
                if self.on_play_sound:
                    self.on_play_sound("crit_hit.ogg")
        self._safe_update()
