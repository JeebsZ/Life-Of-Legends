"""Adventure Run HUD: the creature pack, HP bars, DPS counter and combat juice on the Run screen.

Draws engine state and reacts to the AdventureEvents from AdventureEngine.update_tick(); no
game rules here. Badges are kept per creature id (not rebuilt each tick) so implicit
animations - HP bar fill + trailing damage-lag bar, hit squish, crit pop, defeat burst - can
play. Pocket Mode skips every animation and collapses the pack to one line; the combat loop
and sound callbacks keep running.

Sound callbacks get file-style names ("hit.ogg", "crit_hit.ogg", "slime_defeat.ogg",
"boss_spawn.ogg", "cluster_spawn.ogg", "milestone_surge.ogg"); the screen maps them to real
sounds and ignores unknown ones, so missing files never break anything.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Callable
from typing import Any

import flet as ft

from lol.core.adventure import (
    AdventureEngine,
    AdventureEvent,
    Creature,
    CreatureTier,
    EventType,
    TargetMode,
)
from lol.ui.theme import C

CREATURE_DIR = "/creatures/"  # src/assets/creatures/<sprite>
SPRITE = 64
BOSS_SPRITE = 88
BAR_H = 6
FILL_MS = 90  # main HP fill: snappy
LAG_MS = 250  # trailing white damage bar: catches up after the fill
HIT_MS = 140
BURST_MS = 200
FLOAT_MS = 450
BANNER_S = 1.4
HIT_SOUND_GAP_S = 2.0  # plain hits land every tick; keep their sound occasional

BG = "#161D2B"
BORDER = "#263248"
BADGE_BG = "#111827"
TARGET_BG = "#0B1320"
GOLD = "#FACC15"
CYAN = "#22D3EE"
TIER_COLOR = {CreatureTier.NORMAL: "#38BDF8", CreatureTier.LEADER: "#F59E0B",
              CreatureTier.BOSS: "#A855F7"}
MODE_INFO = {TargetMode.LOWEST_HP: ("Lowest HP", ft.Icons.CENTER_FOCUS_STRONG_ROUNDED, "#38BDF8"),
             TargetMode.STRONGEST: ("Strongest", ft.Icons.WHATSHOT_ROUNDED, "#EC4899"),
             TargetMode.MANUAL: ("Locked", ft.Icons.LOCK_ROUNDED, GOLD)}


def hp_color(ratio: float) -> str:
    return "#10B981" if ratio > 0.5 else "#F59E0B" if ratio > 0.25 else "#EF4444"


def _anim(ms: int, curve: ft.AnimationCurve = ft.AnimationCurve.EASE_OUT) -> ft.Animation:
    return ft.Animation(ms, curve)


def _upd(*controls: ft.Control) -> None:
    """update() only mounted controls; never raise from an animation task."""
    for c in controls:
        with contextlib.suppress(Exception):
            if c.page:
                c.update()


def _pill(text: str, color: str) -> ft.Container:
    return ft.Container(ft.Text(text, size=11, weight=ft.FontWeight.W_800, color=color),
                        bgcolor=C.a(color, 0.16), border=ft.Border.all(1, C.a(color, 0.5)),
                        border_radius=10, padding=ft.Padding.symmetric(horizontal=6, vertical=1))


async def _float_up(stack: ft.Stack, chip: ft.Control, top: float, rise: float = -1.4) -> None:
    """A fresh chip appears in `stack`, drifts up and fades out, then is removed."""
    host = ft.Container(chip, top=top, left=0, right=0, alignment=ft.Alignment.CENTER,
                        offset=ft.Offset(0, 0), opacity=1.0,
                        animate_offset=_anim(FLOAT_MS), animate_opacity=_anim(FLOAT_MS))
    stack.controls.append(host)
    _upd(stack)
    await asyncio.sleep(0.03)
    host.offset, host.opacity = ft.Offset(0, rise), 0.0
    _upd(host)
    await asyncio.sleep(FLOAT_MS / 1000 + 0.05)
    with contextlib.suppress(ValueError):
        stack.controls.remove(host)
    _upd(stack)


class _Badge:
    """One creature: sprite, name, layered HP bar, HP text, floating damage numbers."""

    def __init__(self, c: Creature, on_tap: Callable[[str], None]) -> None:
        self.id, self.tier = c.id, c.tier
        self.boss = c.tier == CreatureTier.BOSS
        self.size = BOSS_SPRITE if self.boss else SPRITE
        self.accent = TIER_COLOR.get(c.tier, "#38BDF8")
        self.is_target = False
        self.dying = False
        s = self.size
        self.sprite_box = ft.Container(
            ft.Image(src=CREATURE_DIR + c.sprite, width=s, height=s, fit=ft.BoxFit.CONTAIN,
                     error_content=ft.Icon(ft.Icons.PEST_CONTROL, color=self.accent,
                                           size=s * 0.6)),
            width=s, height=s, border_radius=12, alignment=ft.Alignment.CENTER,
            bgcolor=C.a("#FFFFFF", 0.0), animate=_anim(HIT_MS))
        r = c.hp_percent
        self.lag = ft.Container(width=s * r, height=BAR_H, bgcolor="#F8FAFC", opacity=0.85,
                                border_radius=3, animate=_anim(LAG_MS))
        self.fill = ft.Container(width=s * r, height=BAR_H, bgcolor=hp_color(r),
                                 border_radius=3, animate=_anim(FILL_MS))
        track = ft.Container(ft.Stack([self.lag, self.fill]), width=s, height=BAR_H,
                             bgcolor="#1E293B", border_radius=3)
        self.hp_text = ft.Text(self._hp_label(c), size=10, color="#94A3B8")
        body = ft.Column([
            self.sprite_box,
            ft.Text(c.name, size=11, weight=ft.FontWeight.BOLD, color="#F8FAFC", no_wrap=True,
                    width=s + 8, text_align=ft.TextAlign.CENTER,
                    overflow=ft.TextOverflow.ELLIPSIS),
            track, self.hp_text,
        ], spacing=4, tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
        self.stack = ft.Stack([body], clip_behavior=ft.ClipBehavior.NONE)
        self.root = ft.Container(
            self.stack, padding=6, border_radius=14, bgcolor=BADGE_BG,
            border=self._border(), shadow=self._shadow(),
            scale=1.0, animate_scale=_anim(HIT_MS, ft.AnimationCurve.EASE_OUT_BACK),
            opacity=1.0, animate_opacity=_anim(BURST_MS), animate=_anim(160),
            on_click=lambda _: on_tap(self.id), ink=True,
            tooltip=f"{c.name} ({c.tier.value}) - tap to lock target")

    @staticmethod
    def _hp_label(c: Creature) -> str:
        return f"{round(c.current_hp)}/{round(c.max_hp)}"

    def _border(self, color: str | None = None) -> ft.Border:
        if color:
            return ft.Border.all(2, color)
        if self.boss:
            return ft.Border.all(2, GOLD if self.is_target else self.accent)
        return ft.Border.all(2 if self.is_target else 1,
                             self.accent if self.is_target else "#1F2937")

    def _shadow(self) -> ft.BoxShadow | None:
        if not self.boss:
            return None
        return ft.BoxShadow(blur_radius=14, spread_radius=1,
                            color=C.a(GOLD if self.is_target else self.accent, 0.45))

    def set_hp(self, c: Creature) -> None:
        r = c.hp_percent
        self.fill.width = self.size * r
        self.fill.bgcolor = hp_color(r)
        self.lag.width = self.size * r
        self.hp_text.value = self._hp_label(c)

    def set_target(self, on: bool) -> None:
        self.is_target = on
        self.root.bgcolor = TARGET_BG if on else BADGE_BG
        self.root.border = self._border()
        self.root.shadow = self._shadow()

    async def hit(self, dmg: float, crit: bool, cleave: bool) -> None:
        """Squish + tint on a hit; gold pop and a floating number on a crit or cleave."""
        pop = crit or cleave
        self.root.scale = 1.12 if crit else 0.88
        self.sprite_box.bgcolor = C.a("#EF4444" if crit else "#FFFFFF", 0.45)
        if pop:
            self.root.border = self._border(GOLD)
        _upd(self.root)
        if crit:
            asyncio.ensure_future(_float_up(self.stack, _pill(f"CRIT! -{dmg:.0f}", GOLD),
                                            top=self.size * 0.3))
        elif cleave:
            asyncio.ensure_future(_float_up(self.stack, _pill(f"-{dmg:.0f}", "#FDE68A"),
                                            top=self.size * 0.4))
        await asyncio.sleep(HIT_MS / 1000)
        if self.dying:
            return
        self.root.scale = 1.0
        self.sprite_box.bgcolor = C.a("#FFFFFF", 0.0)
        _upd(self.root)
        if pop:
            await asyncio.sleep(0.18)
            if not self.dying:
                self.root.border = self._border()
                _upd(self.root)

    async def burst(self) -> None:
        """Pop then shrink away."""
        self.dying = True
        self.root.scale = 1.2
        _upd(self.root)
        await asyncio.sleep(0.08)
        self.root.animate_scale = _anim(BURST_MS, ft.AnimationCurve.EASE_IN)
        self.root.scale, self.root.opacity = 0.0, 0.0
        _upd(self.root)
        await asyncio.sleep(BURST_MS / 1000 + 0.02)


class AdventureRunCard(ft.Container):
    """Mobile card (fits a ~390 px phone) under the Run map: pack, target, DPS and loot."""

    def __init__(self, engine: AdventureEngine,
                 on_play_sound: Callable[[str], None] | None = None,
                 on_target_changed: Callable[[str], None] | None = None,
                 pocket_mode: bool = False) -> None:
        super().__init__()
        self.engine = engine
        self.on_play_sound = on_play_sound
        self.on_target_changed = on_target_changed
        self.pocket_mode = pocket_mode
        self._badges: dict[str, _Badge] = {}
        self._cluster_id: str | None = None
        self._last_hit_sound = 0.0
        self._speed = 0.0

        self.padding = 14
        self.border_radius = 16
        self.bgcolor = BG
        self.border = ft.Border.all(1, BORDER)

        self.status_title = ft.Text("Scouting ahead…", size=14, weight=ft.FontWeight.W_700,
                                    color="#94A3B8", expand=True, no_wrap=True,
                                    overflow=ft.TextOverflow.ELLIPSIS)
        self.dps_text = ft.Text("0 DPS", size=12, weight=ft.FontWeight.BOLD, color="#38BDF8")
        self.dps_badge = ft.Container(self.dps_text, bgcolor="#0F243A", border_radius=8,
                                      padding=ft.Padding.symmetric(horizontal=8, vertical=4))
        self.loot_text = ft.Text("", size=11, color="#CBD5E1")
        self.loot_stack = ft.Stack([ft.Container(self.loot_text, height=18)], width=140,
                                   height=18, clip_behavior=ft.ClipBehavior.NONE)
        self.banner_text = ft.Text("", size=13, weight=ft.FontWeight.W_900, color="#0B1320",
                                   text_align=ft.TextAlign.CENTER)
        self.banner = ft.Container(
            self.banner_text, alignment=ft.Alignment.CENTER, border_radius=10,
            padding=ft.Padding.symmetric(horizontal=10, vertical=6), visible=False, opacity=0.0,
            animate_opacity=_anim(220), scale=0.9, animate_scale=_anim(
                220, ft.AnimationCurve.EASE_OUT_BACK),
            gradient=ft.LinearGradient(colors=[CYAN, GOLD], begin=ft.Alignment.CENTER_LEFT,
                                       end=ft.Alignment.CENTER_RIGHT))
        self.creatures_row = ft.Row(spacing=8, scroll=ft.ScrollMode.AUTO,
                                    vertical_alignment=ft.CrossAxisAlignment.END)
        self.pocket_line = ft.Text("", size=12, color="#CBD5E1", visible=False, no_wrap=True,
                                   overflow=ft.TextOverflow.ELLIPSIS)
        self.combat_ticker = ft.Text("Walk 2.5+ km/h to attack. Faster pace, harder hits.",
                                     size=12, color="#64748B", italic=True, no_wrap=True,
                                     overflow=ft.TextOverflow.ELLIPSIS, expand=True)
        self.mode_btn = self._icon_btn(ft.Icons.CENTER_FOCUS_STRONG_ROUNDED, "#38BDF8",
                                       "Target: Lowest HP (tap for Strongest)",
                                       self._toggle_target_mode)
        self.pocket_btn = self._icon_btn(ft.Icons.PHONE_ANDROID_ROUNDED, "#94A3B8",
                                         "Pocket Mode: off", self._toggle_pocket)
        self.content = ft.Column(spacing=10, tight=True, controls=[
            ft.Row([self.status_title, self.dps_badge], spacing=8),
            self.banner,
            self.creatures_row,
            self.pocket_line,
            ft.Row([self.loot_stack, ft.Container(expand=True), self.mode_btn,
                    self.pocket_btn], spacing=4,
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Divider(height=1, color="#1E293B"),
            ft.Row([ft.Icon(ft.Icons.FLASH_ON_ROUNDED, size=16, color="#F59E0B"),
                    self.combat_ticker], spacing=6),
        ])
        self._apply_pocket()
        self._sync()

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _icon_btn(icon: str, color: str, tip: str, handler: Callable) -> ft.Container:
        return ft.Container(ft.Icon(icon, size=20, color=color), width=48, height=48,
                            border_radius=24, alignment=ft.Alignment.CENTER, tooltip=tip,
                            on_click=handler, ink=True, bgcolor=C.a(color, 0.08))

    def _page(self) -> Any:
        with contextlib.suppress(Exception):
            return self.page
        return None

    def _animate(self, coro_fn: Callable, *args: Any) -> None:
        """Run an animation task unless in Pocket Mode or not on screen."""
        page = self._page()
        if self.pocket_mode or page is None:
            return
        with contextlib.suppress(Exception):
            page.run_task(coro_fn, *args)

    def _sound(self, name: str) -> None:
        if self.on_play_sound:
            with contextlib.suppress(Exception):
                self.on_play_sound(name)

    def _safe_update(self) -> None:
        _upd(self)

    # ------------------------------------------------------------------ controls
    def _toggle_target_mode(self, _: Any = None) -> None:
        eng = self.engine
        eng.target_mode = (TargetMode.STRONGEST if eng.target_mode == TargetMode.LOWEST_HP
                           else TargetMode.LOWEST_HP)
        eng.manual_target_id = None
        self._sync()
        self._safe_update()

    def _on_select_manual(self, creature_id: str) -> None:
        eng = self.engine
        if eng.target_mode == TargetMode.MANUAL and eng.manual_target_id == creature_id:
            eng.target_mode, eng.manual_target_id = TargetMode.LOWEST_HP, None  # unlock
        else:
            eng.target_mode, eng.manual_target_id = TargetMode.MANUAL, creature_id
            if self.on_target_changed:
                self.on_target_changed(creature_id)
        self._sync()
        self._safe_update()

    def _toggle_pocket(self, _: Any = None) -> None:
        self.pocket_mode = not self.pocket_mode
        self._apply_pocket()
        self._sync()
        self._safe_update()

    def _apply_pocket(self) -> None:
        on = self.pocket_mode
        self.creatures_row.visible = not on
        self.pocket_line.visible = on
        if on:
            self.banner.visible = False
        icon = self.pocket_btn.content
        icon.name = ft.Icons.BATTERY_SAVER_ROUNDED if on else ft.Icons.PHONE_ANDROID_ROUNDED
        icon.color = "#5EEAB0" if on else "#94A3B8"
        self.pocket_btn.tooltip = (f"Pocket Mode: {'on' if on else 'off'} (animations "
                                   f"{'paused' if on else 'on'}; combat and sounds keep going)")

    # ------------------------------------------------------------------ state -> controls
    def _sync(self) -> None:
        """Bring every control in line with the engine (no animation here)."""
        eng = self.engine
        self.dps_text.value = f"{int(eng.base_dps(self._speed))} DPS"
        label, icon, color = MODE_INFO[eng.target_mode]
        self.mode_btn.content.name, self.mode_btn.content.color = icon, color
        self.mode_btn.tooltip = f"Target: {label} (tap to switch)"
        self.mode_btn.bgcolor = C.a(color, 0.1)
        self.loot_text.value = (f"+{eng.total_xp_earned} XP · +{eng.total_coins_earned} coins"
                                + (f" · {eng.cosmetic_fragments_count}✦"
                                   if eng.cosmetic_fragments_count else "")
                                if eng.creatures_defeated_count else "")
        cluster = eng.active_cluster
        if cluster is None or not cluster.has_alive:
            left = max(0.0, eng.next_spawn_distance_m - eng.total_distance_m)
            self.status_title.value = "Peaceful stride · scouting ahead"
            self.status_title.color = "#94A3B8"
            self.pocket_line.value = f"Next pack in ~{left:.0f} m"
            if not any(b.dying for b in self._badges.values()):
                self._badges.clear()
                self._cluster_id = None
                self.creatures_row.controls = [ft.Text(f"Next pack in ~{left:.0f} m",
                                                       size=12, color="#64748B")]
            return
        alive = cluster.alive_creatures
        boss = any(c.tier == CreatureTier.BOSS for c in alive)
        self.status_title.value = (f"BOSS ENCOUNTER · {len(alive)} left" if boss
                                   else f"Pack encounter · {len(alive)} left")
        self.status_title.color = "#E9D5FF" if boss else "#F8FAFC"
        if cluster.cluster_id != self._cluster_id:
            self._cluster_id = cluster.cluster_id
            self._badges = {c.id: _Badge(c, self._on_select_manual) for c in alive}
            self.creatures_row.controls = [b.root for b in self._badges.values()]
        target = cluster.select_target(eng.target_mode, eng.manual_target_id)
        by_id = {c.id: c for c in cluster.creatures}
        for cid, b in self._badges.items():
            c = by_id.get(cid)
            if c is None or b.dying:
                continue
            b.set_hp(c)
            b.set_target(target is not None and c.id == target.id)
        if target is not None:
            self.pocket_line.value = (f"{len(alive)} left · ⌖ {target.name} "
                                      f"{int(target.current_hp)}/{int(target.max_hp)} HP")

    def refresh_display(self, current_speed_kmh: float = 0.0) -> None:
        """Repaint from engine state (call once per tick, after process_tick_events)."""
        self._speed = max(0.0, current_speed_kmh or 0.0)
        self._sync()
        self._safe_update()

    # ------------------------------------------------------------------ events -> juice
    def process_tick_events(self, events: list[AdventureEvent]) -> None:
        """Sounds always; animations unless Pocket Mode. Never raises."""
        for ev in events:
            with contextlib.suppress(Exception):
                self._handle(ev)

    def _handle(self, ev: AdventureEvent) -> None:
        t = ev.event_type
        if t == EventType.SPAWN_CLUSTER:
            boss = bool(ev.details.get("has_boss"))
            self.combat_ticker.value = ev.message
            self._sound("boss_spawn.ogg" if boss else "cluster_spawn.ogg")
            self._sync()  # build the new badges now so their hits can animate
        elif t in (EventType.DAMAGE_DEALT, EventType.MULTI_HIT):
            b = self._badges.get(ev.target_id or "")
            cleave = t == EventType.MULTI_HIT
            if t == EventType.DAMAGE_DEALT:
                if ev.is_crit:
                    self.combat_ticker.value = f"CRIT! {ev.target_name} -{ev.damage:.0f}"
                    self._sound("crit_hit.ogg")
                else:
                    now = time.monotonic()
                    if now - self._last_hit_sound >= HIT_SOUND_GAP_S:
                        self._last_hit_sound = now
                        self._sound("hit.ogg")
            if b is not None and not b.dying and ev.damage > 0:
                self._animate(b.hit, ev.damage, ev.is_crit and not cleave, cleave)
        elif t == EventType.CREATURE_DEFEATED:
            self.combat_ticker.value = ev.message
            self._sound("slime_defeat.ogg")
            b = self._badges.get(ev.target_id or "")
            if b is not None:
                b.dying = True
                if self._page() is None or self.pocket_mode:
                    self._remove_badge(b)
                else:
                    self._animate(self._defeat, b)
            self._animate(self._loot, ev.xp_gained, ev.coins_gained,
                          bool(ev.details.get("fragment_gained")))
        elif t == EventType.MILESTONE_SURGE:
            self.combat_ticker.value = ev.message
            self._sound("milestone_surge.ogg")
            km = int(ev.details.get("milestone_m", 0)) // 1000
            self._animate(self._shockwave, f"⚡ {km}K SHOCKWAVE · -{ev.damage:.0f} AoE ⚡")
        elif t == EventType.CLUSTER_CLEARED:
            self.combat_ticker.value = "Pack cleared! Keep moving to find the next one."

    def _remove_badge(self, b: _Badge) -> None:
        self._badges.pop(b.id, None)
        with contextlib.suppress(ValueError):
            self.creatures_row.controls.remove(b.root)

    async def _defeat(self, b: _Badge) -> None:
        await b.burst()
        self._remove_badge(b)
        self._sync()
        self._safe_update()

    async def _loot(self, xp: int, coins: int, frag: bool) -> None:
        asyncio.ensure_future(_float_up(self.loot_stack, _pill(f"+{xp} XP", "#A78BFA"),
                                        top=-2, rise=-1.6))
        await asyncio.sleep(0.12)
        asyncio.ensure_future(_float_up(self.loot_stack, _pill(f"+{coins} coins", GOLD),
                                        top=-2, rise=-1.6))
        if frag:
            await asyncio.sleep(0.12)
            await _float_up(self.loot_stack, _pill("+1 fragment ✦", CYAN), top=-2, rise=-1.6)

    async def _shockwave(self, text: str) -> None:
        self.banner_text.value = text
        self.banner.visible, self.banner.opacity, self.banner.scale = True, 0.0, 0.9
        _upd(self)
        await asyncio.sleep(0.02)
        self.banner.opacity, self.banner.scale = 1.0, 1.0
        _upd(self.banner)
        for b in list(self._badges.values()):
            if not b.dying:
                asyncio.ensure_future(b.hit(0, False, False))
        await asyncio.sleep(BANNER_S)
        self.banner.opacity = 0.0
        _upd(self.banner)
        await asyncio.sleep(0.25)
        self.banner.visible = False
        _upd(self)
