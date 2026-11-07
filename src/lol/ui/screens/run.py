"""More -> Run: a GPS walk/run tracker with a live route map, the distance ladder and spoken
coaching cues.

Phases: pre (mode, goal, Challenge card, safety advice, GPS status, options, bests, history)
-> live (map + big numbers, pause / resume / finish) -> summary (route, splits, kcal, steps,
tier badges). A past run opens the same summary.

Honest limits, said on screen: tracking continues in the background and while the screen is
off or tabbed out. Steps and kcal are estimates. Map tiles come from OpenStreetMap (attribution
always visible); a public release should switch to a keyed tile provider. Rules and math live in
core (run.py, runlog.py, run_cues.py)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import math
import time
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

import flet as ft
import flet.canvas as cv

from lol.core import premium
from lol.core import run as rcore
from lol.core.adventure import (
    AdventureEngine,
    EventType,
    TargetMode,
    creature_latlon,
    is_km_milestone,
)
from lol.core.models import AvatarCustomization, RunEntry
from lol.core.run_cues import CUE_EVERY, CueCoach
from lol.core.runlog import CHALLENGE_COINS, CHALLENGE_XP, MIN_LOG_M, PACE_BADGES, TIER_BY_ID
from lol.ui import ads, audio, avatars, gps, notify, sfx
from lol.ui import components as ui
from lol.ui import theme as th
from lol.ui.adventure_layer import (
    MAGIC_SENSE_ICON,
    SPAWN_RIFT_ICON,
    AdventureRunCard,
    build_map_creature_marker,
)
from lol.ui.screens import common
from lol.ui.theme import C, Radius, Size, Space, Type

if TYPE_CHECKING:
    from lol.ui.app import App

log = logging.getLogger(__name__)

OSM_TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
OSM_URL = OSM_TILE_URL
FIELD_TILE_URL = OSM_TILE_URL
ARCANE_TILE_URL = OSM_TILE_URL
OSM_ATTRIBUTION = "OpenStreetMap contributors"  # the attribution layer adds the ©
# identifies the app to the tile server (OSM policy: a clear app name, not a library default)
TILE_UA = "LUMA/0.1 (com.companions.LUMA)"
LIVE_MAP_H = 340
HUD_GLASS_BG = "#D8070B14"
HUD_GLASS_BORDER = "#444FE3F0"
ARCANE_CYAN = "#4FE3F0"
ARCANE_VEIL_COLOR = "#B0050914"
MANILA = (14.5826, 120.9787)
STAGES = ("TRACING ROUTE…", "MEASURING EFFORT…", "RUN LOGGED")
MODE_INFO = {"run": ("Run", ft.Icons.DIRECTIONS_RUN), "walk": ("Walk", ft.Icons.DIRECTIONS_WALK)}
CUE_LABELS = {"1km": "Every 1 km", "0.5km": "Every 0.5 km", "5min": "Every 5 min"}
ROUTE_COLOR = "#FF8A5B"
LIVE_MAP_POINTS = 400  # the live polyline is thinned to this many points
TICK_S = 1.0
ADV_MAX_TICK_S = 3.0  # adventure: longest slice per step (background gaps are stepped in slices)
ADV_MAX_BG_GAP_S = 300.0  # adventure: max background gap replayed in slices
WAKE_TIMEOUT_S = 1.5  # keep-awake enable/disable; web never answers
MAP_EVERY_S = 2.0  # wall seconds between polyline redraws (keeps the web client snappy)
FOLLOW_EVERY_S = 3.0
GOOD_ACC, OK_ACC = 10.0, rcore.MAX_ACCURACY_M
HONEST_NOTE = ("Tracking continues in the background even if your screen is turned off or you "
               "tab out to another app.")
# Adventure card sound names -> (sfx name, volume scale). Swap in real files later by adding
# them to sfx.py and pointing these entries at them.
ADVENTURE_SOUNDS: dict[str, tuple[str, float | None]] = {
    "hit.ogg": ("scan_tick", 0.35),
    "crit_hit.ogg": ("xp_fill", 0.7),
    "slime_defeat.ogg": ("quest_clear", 0.8),
    "cluster_spawn.ogg": ("objective_new", 0.7),
    "boss_spawn.ogg": ("alert_soft", None),
    "milestone_surge.ogg": ("milestone", None),
}


class _AdvStateProxy(dict):
    """Dict for step timing (`dist`, `t`, `last_step`) that also proxies attribute lookups
    (like `.active_cluster`, `.total_distance_m`, `.next_spawn_distance_m`) to `AdventureEngine`."""

    def __init__(self, engine: AdventureEngine, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        object.__setattr__(self, "_engine", engine)

    def __getattr__(self, name: str) -> Any:
        eng = object.__getattribute__(self, "_engine")
        return getattr(eng, name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "_engine":
            object.__setattr__(self, name, value)
            return
        eng = object.__getattribute__(self, "_engine")
        if hasattr(eng, name):
            setattr(eng, name, value)
        else:
            object.__setattr__(self, name, value)


def _is_mounted(ctrl: ft.Control | None) -> bool:
    if ctrl is None:
        return False
    try:
        return ctrl.page is not None
    except Exception:  # noqa: BLE001
        return False


def _player_slime_beacon(custom: AvatarCustomization | None = None) -> ft.Container:
    """Player chibi avatar / Great Sage presence beacon marker (44x44) for the live map."""
    return ft.Container(
        avatars.AvatarView(custom, size=38),
        width=44,
        height=44,
        border_radius=22,
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        bgcolor="#D9070B14",
        border=ft.Border.all(2, ARCANE_CYAN),
        shadow=ft.BoxShadow(blur_radius=12, color="#884FE3F0"),
        alignment=ft.Alignment.CENTER,
    )


def km(meters: float) -> str:
    return f"{meters / 1000:.2f}"


def _acc_color(acc: float | None) -> str:
    if acc is None:
        return C.TEXT_DIM
    return "#5EEAB0" if acc <= GOOD_ACC else "#F5C66B" if acc <= OK_ACC else C.DANGER


def route_thumb(route: list, size: int = 56, color: str = ROUTE_COLOR) -> ft.Control:
    """A tiny polyline of the route (no map tiles), for the history list."""
    pts = [p for seg in route for p in seg]
    box = {"width": size, "height": size, "border_radius": Radius.SM,
               "bgcolor": C.a(color, 0.08), "border": ft.Border.all(1, C.a(color, 0.3))}
    if len(pts) < 2:
        return ft.Container(ft.Icon(ft.Icons.ROUTE, color=color, size=22),
                            alignment=ft.Alignment.CENTER, **box)
    k = math.cos(math.radians(pts[0][0]))
    xs = [p[1] * k for p in pts]
    ys = [p[0] for p in pts]
    span = max(max(xs) - min(xs), max(ys) - min(ys)) or 1e-9
    pad = 6
    scale = (size - 2 * pad) / span
    ox = pad + ((size - 2 * pad) - (max(xs) - min(xs)) * scale) / 2
    oy = pad + ((size - 2 * pad) - (max(ys) - min(ys)) * scale) / 2
    paint = ft.Paint(color=color, stroke_width=2, style=ft.PaintingStyle.STROKE,
                     stroke_cap=ft.StrokeCap.ROUND, stroke_join=ft.StrokeJoin.ROUND)
    shapes = []
    for seg in route:
        if len(seg) < 2:
            continue
        xy = [(ox + (p[1] * k - min(xs)) * scale, size - oy - (p[0] - min(ys)) * scale)
              for p in seg]
        els = [cv.Path.MoveTo(*xy[0])] + [cv.Path.LineTo(x, y) for x, y in xy[1:]]
        shapes.append(cv.Path(els, paint=paint))
    return ft.Container(cv.Canvas(shapes, width=size, height=size), **box)


def _dot(color: str, size: int = 18) -> ft.Container:
    return ft.Container(width=size, height=size, border_radius=size, bgcolor=color,
                        border=ft.Border.all(3, "#FFFFFF"),
                        shadow=ft.BoxShadow(blur_radius=6, color=C.a("#000000", 0.4)))


class RunScreen:
    title = "Run"

    def __init__(self, app: App) -> None:
        self.app = app
        self.gps = gps.make(app.page)
        self.wake: Any = None
        with contextlib.suppress(Exception):
            self.wake = ft.Wakelock()
        self.phase = "pre"  # pre | live | summary
        self.perm = "checking"
        self.acc: float | None = None
        self.pos: tuple[float, float] | None = None
        self.tracker: rcore.Tracker | None = None
        self.coach: CueCoach | None = None
        self.goal = ""
        self.started = ""
        self.gen = 0
        self.result: RunEntry | None = None
        self.result_new = False  # the summary is of a run just finished
        self.tracking = "full"  # "full" | "basic" (free run without the stretch ad)
        self.list = common.screen_list()
        self.view = ft.Container(self.list, expand=True, key="run")
        self._last_follow = 0.0
        self._list_phase = "pre"
        self._last_map = 0.0
        self._map_points = -1
        self._finish_open = False
        self._map_style: str = "arcane"  # "arcane" (Great Sage dark) | "field" (daylight)
        self._rift_alert_until = 0.0
        self._rift_alert_msg = "[GREAT SAGE] Spatial Rift detected!"
        self.live_map: Any = None
        self.live_poly: Any = None
        self.live_circles: Any = None
        self.live_marks: Any = None
        self._map: Any = None
        self._tile_layer: Any = None
        self._veil_layer: Any = None
        self._polyline_layer: Any = None
        self._circle_layer: Any = None
        self._marker_layer: Any = None
        self._hud_dock_collapsed: bool = True
        self._hud_layout: str = "dock"  # "dock" (Option A) | "go" (Option B Pokémon GO)
        self.adventure_engine = AdventureEngine()
        self.adventure_card: AdventureRunCard | None = None
        self._adv_state: _AdvStateProxy = _AdvStateProxy(
            self.adventure_engine, {"dist": 0.0, "t": 0.0, "last_step": 0.0}
        )
        self._build_live()

    @property
    def PocketMode(self) -> bool:
        return bool(self.adventure_card and self.adventure_card.pocket_mode)

    @PocketMode.setter
    def PocketMode(self, value: bool) -> None:
        if self.adventure_card is not None:
            self.adventure_card.pocket_mode = bool(value)
            self.adventure_card._apply_pocket()
            self.adventure_card._sync()

    @property
    def fullscreen(self) -> bool:
        """When a run is live, take 100% of the screen like Pokémon GO."""
        return self.phase == "live"

    def _tile_url_for_style(self, style: str | None = None) -> str:
        st = style or self._map_style
        return ARCANE_TILE_URL if st == "arcane" else FIELD_TILE_URL

    def _toggle_map_style(self, _: Any = None) -> None:
        sfx.play("toggle")
        self._map_style = "field" if self._map_style == "arcane" else "arcane"
        is_arcane = self._map_style == "arcane"
        if hasattr(self, "map_style_text"):
            self.map_style_text.value = "SAGE" if is_arcane else "FIELD"
            self.map_style_text.color = ARCANE_CYAN if is_arcane else "#F5C66B"
        if hasattr(self, "map_style_pill"):
            self.map_style_pill.border = ft.Border.all(
                1, C.a(ARCANE_CYAN if is_arcane else "#F5C66B", 0.55)
            )
            self.map_style_pill.bgcolor = C.a(ARCANE_CYAN if is_arcane else "#F5C66B", 0.16)
        if self._tile_layer is not None:
            self._tile_layer.url_template = self._tile_url_for_style()
        self._update_map()
        if _is_mounted(self.live_view):
            ui.refresh(self.live_view)

    def _toggle_hud_dock(self, _: Any = None) -> None:
        """Collapse or expand the floating Great Sage combat card on the full-screen map."""
        sfx.play("tap")
        self._hud_dock_collapsed = not self._hud_dock_collapsed
        self._sync_hud_layout()
        if _is_mounted(self.live_view):
            ui.refresh(self.live_view)

    def _toggle_hud_layout(self, _: Any = None) -> None:
        """Toggle between Option A ('dock' Compact Strip) and Option B ('go' Pokémon GO Orbs)."""
        sfx.play("toggle")
        self._hud_layout = "go" if self._hud_layout == "dock" else "dock"
        self._sync_hud_layout()
        self._paint_live()
        if _is_mounted(self.live_view):
            ui.refresh(self.live_view)

    def _cycle_target_mode(self, _: Any = None) -> None:
        """Cycle between Lowest HP and Strongest target mode from the Option B Target Orb."""
        sfx.play("tap")
        eng = self.adventure_engine
        new_mode = (
            TargetMode.STRONGEST
            if eng.target_mode == TargetMode.LOWEST_HP
            else TargetMode.LOWEST_HP
        )
        eng.target_mode, eng.manual_target_id = new_mode, None
        if self.adventure_card is not None and hasattr(self.adventure_card, "_on_select_mode"):
            self.adventure_card._on_select_mode(new_mode)
        self._paint_live()
        self._update_map()
        if _is_mounted(self.live_view):
            ui.refresh(self.live_view)

    def _sync_hud_layout(self) -> None:
        is_go = self._hud_layout == "go"
        basic = self.tracking == "basic"
        if hasattr(self, "hud_layout_text"):
            self.hud_layout_text.value = "HUD: GO" if is_go else "HUD: DOCK"
        if hasattr(self, "hud_top_dock_row"):
            self.hud_top_dock_row.visible = not is_go
        if hasattr(self, "hud_top_go_col"):
            self.hud_top_go_col.visible = is_go
        if hasattr(self, "hud_dock_strip"):
            self.hud_dock_strip.visible = (not basic) and (not is_go)
        if hasattr(self, "adventure_wrap"):
            self.adventure_wrap.visible = (
                (not basic) and (not is_go) and (not self._hud_dock_collapsed)
            )
        if hasattr(self, "hud_go_left_pill"):
            self.hud_go_left_pill.visible = (not basic) and is_go
        if hasattr(self, "hud_go_target_orb"):
            self.hud_go_target_orb.visible = (not basic) and is_go
        if hasattr(self, "hud_dock_toggle_icon"):
            self.hud_dock_toggle_icon.icon = (
                ft.Icons.KEYBOARD_ARROW_UP
                if self._hud_dock_collapsed
                else ft.Icons.KEYBOARD_ARROW_DOWN
            )

    def _recenter_map(self, _: Any = None) -> None:
        sfx.play("tap")
        pts = [p for seg in (self.tracker.route() if self.tracker else []) for p in seg]
        here = (pts[-1] if pts else None) or self.pos or MANILA
        if self.live_map is not None:
            self.app.page.run_task(self._follow, here)

    def _on_target_creature(self, creature_id: str) -> None:
        sfx.play("tap")
        if self.adventure_card is not None:
            self.adventure_card._on_select_manual(creature_id)
        else:
            eng = self.adventure_engine
            if eng.target_mode == TargetMode.MANUAL and eng.manual_target_id == creature_id:
                eng.target_mode, eng.manual_target_id = TargetMode.LOWEST_HP, None
            else:
                eng.target_mode, eng.manual_target_id = TargetMode.MANUAL, creature_id
        self._update_map()
        if _is_mounted(self.live_view):
            ui.refresh(self.live_view)

    def _on_card_target_changed(self, _creature_id: str) -> None:
        self._update_map()
        if _is_mounted(self.live_view):
            ui.refresh(self.live_view)

    def _play_adventure_sound(self, sound_name: str) -> None:
        """Adventure card sound hook -> existing sfx (unknown names are ignored, so missing
        .ogg files never break a run). Frequent sounds stay light and quiet; only the big
        moments use FOREGROUND sounds that hold Luma's voice."""
        stem, volume = ADVENTURE_SOUNDS.get(
            sound_name, (sound_name.removesuffix(".ogg").removesuffix(".wav"), None))
        if stem in sfx.NAMES:
            sfx.play(stem, volume=volume)

    # ------------------------------------------------------------------ lifecycle
    def restyle(self) -> None:
        self._refresh()

    def _refresh(self) -> None:
        self.render()
        ui.refresh(self.view)

    def _refresh_hud_avatars(self) -> None:
        custom = self.app.game.profile.avatar_customization
        for attr in ("hud_slime_avatar", "hud_go_avatar"):
            ctrl = getattr(self, attr, None)
            if ctrl is not None and isinstance(ctrl.content, avatars.AvatarView):
                ctrl.content.set_custom(custom)

    def on_enter(self) -> None:
        self._refresh_hud_avatars()
        if self.phase == "pre":
            self.app.page.run_task(self._check_gps)

    def on_leave(self) -> None:
        if self.phase != "live":
            self.gps.stop()

    @property
    def settings(self):
        return self.app.game.data.run_settings

    def render(self) -> None:
        self._refresh_hud_avatars()
        with contextlib.suppress(Exception):
            self.app.set_fullscreen(self.phase == "live")
        if self.phase == "live":
            self.view.content = self.live_view
            self._paint_live()
            return
        # a fresh list per phase: back from live (a control that left the tree isn't re-sent
        # by the diff), and pre <-> summary starts at the top
        if self.view.content is not self.list or self._list_phase != self.phase:
            self.list = common.screen_list()
            self._list_phase = self.phase
        self.view.content = self.list
        self.list.controls = (self._summary(self.result) if self.phase == "summary"
                              and self.result else self._pre())

    # ------------------------------------------------------------------ GPS
    def _on_fix(self, fix: rcore.Fix) -> None:
        self.acc = fix.accuracy
        if fix.accuracy <= rcore.MAX_ACCURACY_M:
            self.pos = (fix.lat, fix.lon)
        if self.phase == "live" and self.tracker is not None:
            self.tracker.add(fix)
            now = self.gps.now()
            if now - self._adv_state.get("last_step", 0.0) >= TICK_S:
                self._step_live(now)
        elif self.phase == "pre":
            self._paint_gps()

    async def _check_gps(self) -> None:
        self.perm = await self.gps.status()
        if self.perm == gps.GRANTED:
            self.gps.start(self._on_fix, self.settings.mode)  # warm up for a quicker lock
        if self.phase == "pre":
            self._paint_gps()

    async def _ask_permission(self, _: Any = None) -> None:
        sfx.play("tap")
        self.perm = await self.gps.request()
        if self.perm == gps.GRANTED:
            sfx.play("granted")
            self.app.toast("Location on. Waiting for a GPS fix…", ft.Icons.GPS_FIXED)
            self.gps.start(self._on_fix, self.settings.mode)
        else:
            sfx.play("error_soft")
        self._paint_gps()

    async def _open_settings(self, location: bool = False) -> None:
        ok = await self.gps.open_settings(location) if not self.gps.fake else False
        if not ok:
            self.app.error("Open your phone's Settings -> Apps -> Life of Legends -> "
                           "Location yourself, then come back.")

    # ------------------------------------------------------------------ pre-run
    def _pre(self) -> list[ft.Control]:
        g, today, s = self.app.game, self.app.today(), self.settings
        mode = s.mode
        adv = g.run_advice(mode, today)
        lad = g.ladder(mode)
        items: list[ft.Control] = [
            common.ChoicePills([(k, lbl, icon, ROUTE_COLOR) for k, (lbl, icon)
                                in MODE_INFO.items()], mode, on_change=self._set_mode,
                               grid_cols=2),
            self._advice_card(adv),
        ]
        if adv.challenge is not None:
            items.append(self._challenge_card(adv.challenge, adv.suggest_challenge, today))
        items.append(self._goal_picker(lad, today))
        self.gps_box = ft.Container()
        self._paint_gps(update=False)
        items.append(self.gps_box)
        items.append(ft.Container(
            common.primary_button("Start " + MODE_INFO[mode][0].lower(), self._start,
                                  icon=ft.Icons.PLAY_ARROW), height=56))
        if g.is_premium(today):  # free runs get the stretch guide on the Start sheet
            items.append(ft.Row([common.secondary_button(
                "Stretch first (optional)", self._stretch_only,
                icon=ft.Icons.SPORTS_GYMNASTICS, color=ROUTE_COLOR)]))
        else:
            items.append(ft.Container(common.hint(
                "Free runs start with an optional stretch + short ad for full tracking."),
                alignment=ft.Alignment.CENTER))
        items.append(self._options_card())
        items.append(self._body_card())
        items += self._bests(lad)
        items += self._history()
        return items

    def _set_mode(self, mode: str) -> None:
        self.app.game.set_run_settings(mode=mode)
        self.app.save()
        if self.goal and self.goal not in {t.tier.id for t in self.app.game.ladder(mode)
                                           if t.state == "cleared"}:
            self.goal = ""
        self._refresh()

    def _advice_card(self, adv: Any) -> ft.Control:
        rows: list[ft.Control] = [
            ft.Row([ft.Icon(ft.Icons.AUTO_AWESOME, color=C.PRIMARY, size=18),
                    ft.Text(adv.headline, size=Type.BODY, weight=ft.FontWeight.W_700,
                            color=C.TEXT, expand=True)], spacing=Space.SM),
        ]
        if adv.reason:
            rows.append(common.hint(adv.reason))
        if adv.rest_nudge and adv.rest_nudge != adv.reason:
            rows.append(ft.Row([ft.Icon(ft.Icons.BEDTIME, color="#A78BFA", size=16),
                                ft.Text(adv.rest_nudge, size=Type.CAPTION, color=C.TEXT,
                                        expand=True)], spacing=Space.SM))
        frac = min(1.0, adv.week_km / adv.cap_km) if adv.cap_km else 0
        rows += [
            ft.Row([common.hint(f"This week {adv.week_km:.1f} km"),
                    ft.Container(expand=True),
                    common.hint(f"safe room {adv.cap_km:.1f} km (+10%/week)")]),
            ft.ProgressBar(value=frac, color=ROUTE_COLOR, bgcolor=C.a(C.TEXT, 0.1), height=6,
                           border_radius=3),
        ]
        for note in adv.notes:
            icon = (ft.Icons.WB_SUNNY if note.startswith("Hot") else ft.Icons.HEALTH_AND_SAFETY
                    if note.startswith("Stop") else ft.Icons.CHILD_CARE)
            rows.append(ft.Row([ft.Icon(icon, color=C.TEXT_DIM, size=16),
                                ft.Text(note, size=Type.CAPTION, color=C.TEXT_DIM,
                                        expand=True)], spacing=Space.SM,
                               vertical_alignment=ft.CrossAxisAlignment.START))
        return common.card(ft.Column(rows, spacing=Space.SM, tight=True))

    def _challenge_card(self, st: Any, ready: bool, today: date) -> ft.Control:
        t = st.tier
        if st.available_from and st.available_from > today:
            status, col = "Opens tomorrow - rest first", C.TEXT_DIM
        elif ready:
            status, col = "Available now", "#5EEAB0"
        else:
            status, col = "Available - build up first", "#F5C66B"
        mode = self.settings.mode
        badges = " · ".join(f"{lbl} ≤{rcore.fmt_pace(lim)}" for lbl, lim
                            in PACE_BADGES[mode][:3])
        open_now = not (st.available_from and st.available_from > today)
        chosen = self.goal == t.id

        def pick(_: Any = None) -> None:
            if not open_now:
                sfx.play("error_soft")
                self.app.toast("It opens tomorrow. Rest is part of the climb.",
                               ft.Icons.BEDTIME)
                return
            sfx.play("toggle")
            self.goal = "" if chosen else t.id
            self._refresh()

        return common.card(ft.Column([
            ft.Row([ft.Icon(ft.Icons.EMOJI_EVENTS, color=C.ACCENT, size=22),
                    ft.Text(f"Challenge · {t.label}", size=Type.TITLE,
                            weight=ft.FontWeight.W_800, color=C.TEXT, expand=True),
                    ui.xp_chip(CHALLENGE_XP), ui.coin_chip(CHALLENGE_COINS)],
                   spacing=Space.SM),
            ft.Text(status, size=Type.CAPTION, color=col, weight=ft.FontWeight.W_600),
            common.hint(f"Cover {t.meters / 1000:g} km in one {mode}. Pace badges: {badges}."),
            ft.Row([common.secondary_button("Clear goal" if chosen else "Set as goal", pick,
                                            icon=ft.Icons.FLAG, color=ROUTE_COLOR)]),
        ], spacing=Space.SM, tight=True), tint="#F5C66B")

    def _goal_picker(self, lad: list, today: date) -> ft.Control:
        opts = [("", "Free", ft.Icons.ALL_INCLUSIVE, ROUTE_COLOR)]
        for st in lad:
            if st.state == "cleared" or (st.state == "open" and not (
                    st.available_from and st.available_from > today)):
                opts.append((st.tier.id, st.tier.label.replace(" marathon", ""), None,
                             C.ACCENT if st.state == "open" else ROUTE_COLOR))
        if self.goal not in {o[0] for o in opts}:
            self.goal = ""

        def pick(v: str) -> None:
            self.goal = v

        return ft.Column([common.section("Goal"),
                          common.ChoicePills(opts, self.goal, on_change=pick, grid_cols=0)],
                         spacing=Space.XS, tight=True)

    def _paint_gps(self, update: bool = True) -> None:
        box = getattr(self, "gps_box", None)
        if box is None:
            return
        rows: list[ft.Control] = []
        st = self.perm
        if self.gps.fake:
            rows.append(common.hint("Debug: simulated route (LOL_FAKE_GPS)."))
        if st == gps.GRANTED:
            acc = self.acc
            col = _acc_color(acc)
            label = ("Waiting for a GPS fix…" if acc is None
                     else f"GPS ready · ±{acc:.0f} m" if acc <= GOOD_ACC
                     else f"GPS weak · ±{acc:.0f} m (step outside, away from buildings)")
            rows.insert(0, ft.Row([ft.Container(width=12, height=12, border_radius=6,
                                                bgcolor=col),
                                   ft.Text(label, size=Type.BODY, color=C.TEXT,
                                           expand=True)], spacing=Space.SM))
        elif st == "checking":
            rows.insert(0, common.hint("Checking location permission…"))
        elif st == "denied":
            rows[:0] = [
                ft.Text("Location is needed to draw your route", size=Type.BODY,
                        weight=ft.FontWeight.W_700, color=C.TEXT),
                common.hint("Used only while you track, to measure distance and pace. "
                            "Nothing leaves your phone."),
                ft.Row([common.primary_button("Allow location", self._ask_permission,
                                              icon=ft.Icons.GPS_FIXED)]),
            ]
        elif st == "denied_forever":
            rows[:0] = [
                ft.Text("Location is turned off for this app", size=Type.BODY,
                        weight=ft.FontWeight.W_700, color=C.TEXT),
                common.hint("Turn it on in your phone's settings, or log the session by hand "
                            "in Workout."),
                ft.Row([common.secondary_button("Open settings",
                                                lambda e: self._open_settings(),
                                                icon=ft.Icons.SETTINGS),
                        common.secondary_button("Log by hand", self._manual,
                                                icon=ft.Icons.EDIT_NOTE)], spacing=Space.SM),
            ]
        elif st == "service_off":
            rows[:0] = [
                ft.Text("Your phone's location is off", size=Type.BODY,
                        weight=ft.FontWeight.W_700, color=C.TEXT),
                ft.Row([common.secondary_button("Turn on location",
                                                lambda e: self._open_settings(True),
                                                icon=ft.Icons.LOCATION_ON),
                        common.secondary_button("Check again",
                                                lambda e: self._check_gps(),
                                                icon=ft.Icons.REFRESH)], spacing=Space.SM),
            ]
        else:
            rows[:0] = [
                ft.Text("GPS isn't available here", size=Type.BODY,
                        weight=ft.FontWeight.W_700, color=C.TEXT),
                common.hint("Route tracking needs the phone app. You can still log a walk or "
                            "run by hand."),
                ft.Row([common.secondary_button("Log by hand in Workout", self._manual,
                                                icon=ft.Icons.EDIT_NOTE)]),
            ]
        rows.append(ft.Row([ft.Icon(ft.Icons.INFO_OUTLINE, size=14, color=C.TEXT_DIM),
                            ft.Text(HONEST_NOTE, size=Type.CAPTION, color=C.TEXT_DIM,
                                    expand=True)], spacing=Space.SM,
                           vertical_alignment=ft.CrossAxisAlignment.START))
        box.content = common.card(ft.Column(rows, spacing=Space.SM, tight=True))
        if update:
            ui.refresh(box)

    def _manual(self, _: Any = None) -> None:
        self.app.more.open("workout")

    def _options_card(self) -> ft.Control:
        g, s = self.app.game, self.settings

        def awake(on: bool) -> None:
            g.set_run_settings(keep_awake=on)
            self.app.save()

        def cues(on: bool) -> None:
            g.set_run_settings(voice_cues=on)
            self.app.save()
            if on and not audio.enabled():
                self.app.toast("Voice is off in Settings - turn it on to hear the cues.",
                               ft.Icons.VOLUME_OFF)

        def every(v: str) -> None:
            g.set_run_settings(cue_every=v)
            self.app.save()

        def toggle_sim_gps(on: bool) -> None:
            self.gps.stop()
            if on:
                self.gps = gps.FakeGps(self.app.page, speed=4.0)
                self.perm = gps.GRANTED
                self.app.toast("Demo GPS enabled (Rizal Park loop · 4× speed).",
                               ft.Icons.EXPLORE)
            else:
                self.gps = gps.PhoneGps(self.app.page)
                self.app.page.run_task(self._check_gps)
            self._refresh()

        return common.card(ft.Column([
            common.switch_row("Keep screen awake", "Keep display on while viewing Run (tracking "
                              "also continues with screen off or in background)", s.keep_awake,
                              awake, icon=ft.Icons.SCREEN_LOCK_PORTRAIT),
            common.switch_row("Voice cues", "Distance, time, pace and steps, halfway, goal, "
                              "water and pacing nudges", s.voice_cues, cues,
                              icon=ft.Icons.RECORD_VOICE_OVER),
            common.segmented([(k, CUE_LABELS[k]) for k in CUE_EVERY], s.cue_every,
                             on_change=every),
            common.switch_row("Simulate GPS route (BlueStacks / Demo)",
                              "Replay a simulated outdoor loop to test map & wild mob spawns on "
                              "emulators or indoors",
                              bool(getattr(self.gps, "fake", False)), toggle_sim_gps,
                              icon=ft.Icons.EXPLORE),
        ], spacing=Space.SM, tight=True))

    def _body_card(self) -> ft.Control:
        body = self.app.game.run_body(self.app.today())
        if body["weight_kg"] is not None:
            txt = (f"kcal uses your weight {body['weight_kg']:g} kg"
                   + ("" if body["bmr"] else " · add height, age and sex in Body for "
                      "a better resting burn"))
            return ft.Container(common.hint(txt), padding=ft.Padding.symmetric(horizontal=4))
        return common.card(ft.Row([
            ft.Icon(ft.Icons.MONITOR_WEIGHT, color=C.TEXT_DIM, size=20),
            ft.Column([ft.Text("Weight not set", size=Type.BODY, color=C.TEXT,
                               weight=ft.FontWeight.W_600),
                       common.hint(f"kcal will use {rcore.DEFAULT_WEIGHT_KG:g} kg "
                                   "(an estimate)")], spacing=0, tight=True, expand=True),
            ft.TextButton("Add weight", on_click=common.with_sound(self._add_weight),
                          height=Size.TAP, style=ft.ButtonStyle(color=C.PRIMARY)),
        ], vertical_alignment=ft.CrossAxisAlignment.CENTER), padding=Space.MD)

    def _add_weight(self, _: Any = None) -> None:
        g, app = self.app.game, self.app
        unit = g.data.body.weight_unit
        field = common.text_field(f"Weight ({unit})", number=True, autofocus=True)

        def save(_: Any = None) -> None:
            try:
                v = float((field.value or "").replace(",", "."))
            except ValueError:
                app.error("Type a number, e.g. 68.5")
                return
            common.close(sheet)

            async def go() -> None:
                try:
                    await app.award(lambda: g.log_weight(v, unit, app.today()),
                                    line=lambda c: f"Notice: Weight logged. +{c.xp} XP.")
                except ValueError as exc:
                    app.error(str(exc))
                self._refresh()

            app.page.run_task(go)

        field.on_submit = save
        sheet = common.open_sheet(app.page, "Your weight", [
            common.hint("Used for the kcal estimate. Also saved to your Body log."),
            field, ft.Row([common.primary_button("Save", save, icon=ft.Icons.CHECK)])])

    def _bests(self, lad: list) -> list[ft.Control]:
        out: list[ft.Control] = [common.section("Ladder & personal bests")]
        chips = []
        for st in lad:
            col = (ROUTE_COLOR if st.state == "cleared" else C.ACCENT if st.state == "open"
                   else C.TEXT_DIM)
            icon = (ft.Icons.CHECK_CIRCLE if st.state == "cleared" else ft.Icons.FLAG
                    if st.state == "open" else ft.Icons.LOCK)
            chips.append(ui.chip(st.tier.label.replace(" marathon", ""), icon=icon, color=col,
                                 dim=st.state == "locked"))
        rows: list[ft.Control] = [ft.Row(chips, wrap=True, spacing=Space.XS,
                                         run_spacing=Space.XS)]
        for st in lad:
            if st.best_s is None:
                continue
            pace = rcore.fmt_pace(st.best_s / (st.tier.meters / 1000))
            rows.append(ft.Row([
                ft.Icon(ft.Icons.EMOJI_EVENTS, color=C.ACCENT, size=18),
                ft.Text(st.tier.label, size=Type.BODY, color=C.TEXT, expand=True),
                ft.Text(rcore.fmt_duration(st.best_s), size=Type.BODY,
                        weight=ft.FontWeight.W_700, color=C.TEXT),
                common.hint(f"{pace} /km"),
                ui.chip(st.badge or "", color=ROUTE_COLOR),
            ], spacing=Space.SM))
        if len(rows) == 1:
            rows.append(common.hint("Finish a 1K to set your first best."))
        out.append(common.card(ft.Column(rows, spacing=Space.SM, tight=True)))
        return out

    def _history(self) -> list[ft.Control]:
        g, today = self.app.game, self.app.today()
        cutoff = g.history_cutoff("run_history", today)
        every = g.runs()
        runs = [r for r in every if cutoff is None or r.day >= cutoff.isoformat()]
        out: list[ft.Control] = [common.section("History")]
        if not runs:
            out.append(common.hint("  Your tracked walks and runs show up here."))
        hide = self._hidden_stats
        for r in runs:
            d = date.fromisoformat(r.day)
            pace = rcore.fmt_pace(rcore.pace_s_per_km(r.distance_m, r.moving_s))
            if hide(r):  # basic run: steps + time only
                line = f"{d:%a} {common.short_date(d)} · {rcore.fmt_duration(r.moving_s)}"
                head = f"{r.steps:,} steps (est.) · basic"
            else:
                line = (f"{d:%a} {common.short_date(d)} · "
                        f"{rcore.fmt_duration(r.moving_s)} · {pace} /km")
                head = f"{km(r.distance_m)} km {MODE_INFO[r.mode][0].lower()}"
            out.append(common.card(ft.Row([
                route_thumb(r.route),
                ft.Column([
                    ft.Text(head, size=Type.BODY, weight=ft.FontWeight.W_700, color=C.TEXT),
                    common.hint(line),
                ], spacing=2, tight=True, expand=True),
                ft.Icon(ft.Icons.EMOJI_EVENTS, color=C.ACCENT, size=18, visible=bool(r.cleared)),
                ft.Icon(ft.Icons.CHEVRON_RIGHT, color=C.TEXT_DIM),
            ], spacing=Space.MD, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                padding=Space.SM, on_click=lambda e, rid=r.id: self._open_run(rid), ink=True))
        older = len(every) - len(runs)
        if older:
            out.append(ft.Row([ft.TextButton(
                f"{older} older session{'s' if older != 1 else ''} kept · see all with "
                f"{premium.PREMIUM_NAME}", icon=ft.Icons.WORKSPACE_PREMIUM,
                on_click=lambda e: self.app.open_sub("premium"),
                style=ft.ButtonStyle(color="#F5C66B"))],
                alignment=ft.MainAxisAlignment.CENTER))
        return out

    def _hidden_stats(self, r: RunEntry) -> bool:
        """A basic run shows steps + time only, until premium."""
        return r.basic and not self.app.game.is_premium(self.app.today())

    def _open_run(self, run_id: str) -> None:
        sfx.play("tab_open")
        self.result, self.result_new, self.phase = self.app.game.run(run_id), False, "summary"
        self._refresh()

    # ------------------------------------------------------------------ live
    def _build_live(self) -> None:
        big = {"weight": ft.FontWeight.W_900, "color": C.TEXT}
        self.l_dist = ft.Text("0.00", size=28, **big)
        self.l_steps = ft.Text("0", size=44, **big)  # basic tracking: steps + time
        self.l_btime = ft.Text("0:00", size=Type.HEADLINE + 2, **big)
        self.l_time = ft.Text("0:00", size=14, weight=ft.FontWeight.W_800, color="#CBD5E1")
        self.l_pace = ft.Text("-:--", size=14, weight=ft.FontWeight.W_800, color=ARCANE_CYAN)
        self.l_avg = ft.Text("-:--", size=13, weight=ft.FontWeight.W_700, color=C.TEXT_DIM)
        self.l_status = ft.Text("", size=10, color=C.TEXT_DIM)
        self.l_dot = ft.Container(width=9, height=9, border_radius=5, bgcolor=C.TEXT_DIM)
        self.l_goal = ft.ProgressBar(value=0, color=ROUTE_COLOR, bgcolor=C.a(C.TEXT, 0.14),
                                     height=5, border_radius=3)
        self.l_goal_txt = ft.Text("", size=10, color="#F8FAFC", weight=ft.FontWeight.W_600)
        self.l_banner = ft.Container(
            ft.Text("AUTO-PAUSED", size=9, weight=ft.FontWeight.BOLD,
                    color=C.BG), bgcolor="#F5C66B", border_radius=Radius.PILL,
            padding=ft.Padding.symmetric(horizontal=8, vertical=2), visible=False)
        self.b_pause = ft.Container(
            ft.Icon(ft.Icons.PAUSE, size=30, color="#070B14"), width=62, height=62,
            border_radius=31, bgcolor=ARCANE_CYAN, alignment=ft.Alignment.CENTER,
            border=ft.Border.all(2, "#FFFFFF"),
            shadow=ft.BoxShadow(blur_radius=12, color=C.a(ARCANE_CYAN, 0.55)),
            on_click=self._toggle_pause, tooltip="Pause", scale=1,
            animate_scale=th.Motion.anim(th.Motion.POP_MS, th.Motion.BACK))
        self.b_finish = ft.Container(
            ft.Icon(ft.Icons.STOP, size=28, color="#FFFFFF"), width=62, height=62,
            border_radius=31, bgcolor="#E5484D", alignment=ft.Alignment.CENTER,
            border=ft.Border.all(2, "#FCA5A5"),
            shadow=ft.BoxShadow(blur_radius=12, color=C.a("#E5484D", 0.55)),
            on_click=self._finish_tap, tooltip="Finish", scale=1,
            animate_scale=th.Motion.anim(th.Motion.POP_MS, th.Motion.BACK))
        # Backwards-compatible attribute aliases
        self.distance_text = self.l_dist
        self.time_text = self.l_time
        self.pace_text = self.l_pace
        self.avg_pace_text = self.l_avg
        self.gps_chip = self.l_status
        self.pause_btn = self.b_pause
        self.finish_btn = self.b_finish
        self.splits_column = ft.Column(spacing=Space.XS, tight=True)

        # Full-bleed Map Canvas inside the body frame
        self.map_host = ft.Container(
            expand=True,
            top=0,
            bottom=0,
            left=0,
            right=0,
            border_radius=Radius.LG,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            bgcolor="#070B14",
        )

        # --- Pokémon GO / Great Sage Floating HUD Overlays on Top of the Map ---
        is_arcane = self._map_style == "arcane"
        is_go = self._hud_layout == "go"
        self.hud_compass_icon = ft.Container(
            ft.Image(
                src=MAGIC_SENSE_ICON,
                width=28,
                height=28,
                fit=ft.BoxFit.COVER,
                error_content=ft.Icon(ft.Icons.EXPLORE, size=18, color=ARCANE_CYAN),
            ),
            width=28,
            height=28,
            border_radius=14,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            border=ft.Border.all(1, C.a(ARCANE_CYAN, 0.65)),
            on_click=self._recenter_map,
            tooltip="Re-center Map on Slime Core",
        )
        self.hud_dist_text = ft.Text(
            "0.00 km", size=22, weight=ft.FontWeight.W_900, color="#F8FAFC"
        )
        self.hud_time_text = ft.Text(
            "0:00", size=12, weight=ft.FontWeight.W_700, color="#CBD5E1"
        )
        self.hud_pace_text = ft.Text(
            "-:-- /km", size=12, weight=ft.FontWeight.W_800, color=ARCANE_CYAN
        )
        # Option B ('GO') top header labels
        self.hud_go_time = ft.Text(
            "0:00", size=15, weight=ft.FontWeight.W_800, color="#E2E8F0"
        )
        self.hud_go_dist = ft.Text(
            "0.00 km", size=24, weight=ft.FontWeight.W_900, color="#FFFFFF"
        )
        self.hud_go_pace = ft.Text(
            "-:-- /km", size=15, weight=ft.FontWeight.W_800, color=ARCANE_CYAN
        )

        self.map_style_text = ft.Text(
            "SAGE" if is_arcane else "FIELD",
            size=10,
            weight=ft.FontWeight.W_900,
            color=ARCANE_CYAN if is_arcane else "#F5C66B",
        )
        self.map_style_pill = ft.Container(
            self.map_style_text,
            bgcolor=C.a(ARCANE_CYAN if is_arcane else "#F5C66B", 0.16),
            border=ft.Border.all(1, C.a(ARCANE_CYAN if is_arcane else "#F5C66B", 0.55)),
            border_radius=Radius.PILL,
            padding=ft.Padding.symmetric(horizontal=8, vertical=2),
            on_click=self._toggle_map_style,
            ink=True,
            tooltip="Toggle Great Sage Radar / Daylight Field Map",
        )
        self.hud_layout_text = ft.Text(
            "HUD: GO" if is_go else "HUD: DOCK",
            size=10,
            weight=ft.FontWeight.W_900,
            color="#C4B5FD",
        )
        self.hud_layout_pill = ft.Container(
            self.hud_layout_text,
            bgcolor=C.a("#8B5CF6", 0.20),
            border=ft.Border.all(1, C.a("#A78BFA", 0.65)),
            border_radius=Radius.PILL,
            padding=ft.Padding.symmetric(horizontal=8, vertical=2),
            on_click=self._toggle_hud_layout,
            ink=True,
            tooltip="Switch between Option A (Compact Dock) and Option B (Pokémon GO Orbs)",
        )
        self.hud_gps_dot = ft.Container(
            width=9, height=9, border_radius=5, bgcolor=C.TEXT_DIM
        )
        back_btn = ft.Container(
            ft.Icon(ft.Icons.ARROW_BACK, size=18, color="#E2E8F0"),
            width=30,
            height=30,
            border_radius=15,
            bgcolor=C.a("#FFFFFF", 0.08),
            alignment=ft.Alignment.CENTER,
            on_click=lambda _: self.app.more.back(),
            ink=True,
            tooltip="Back (Run continues in background)",
        )

        # Option A ('DOCK') Top Row
        self.hud_top_dock_row = ft.Row(
            [
                back_btn,
                self.hud_compass_icon,
                ft.Column(
                    [
                        self.hud_dist_text,
                        ft.Row(
                            [self.hud_time_text, self.hud_pace_text],
                            spacing=8,
                            tight=True,
                        ),
                    ],
                    spacing=0,
                    tight=True,
                    expand=True,
                ),
                ft.Column(
                    [
                        ft.Row(
                            [self.hud_layout_pill, self.map_style_pill],
                            spacing=4,
                            tight=True,
                        ),
                        ft.Row(
                            [self.l_banner, self.l_status, self.hud_gps_dot],
                            spacing=4,
                            tight=True,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                    ],
                    spacing=3,
                    tight=True,
                    horizontal_alignment=ft.CrossAxisAlignment.END,
                ),
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            visible=not is_go,
        )

        # Option B ('GO') Top Column
        back_btn_go = ft.Container(
            ft.Icon(ft.Icons.ARROW_BACK, size=18, color="#E2E8F0"),
            width=30,
            height=30,
            border_radius=15,
            bgcolor=C.a("#FFFFFF", 0.08),
            alignment=ft.Alignment.CENTER,
            on_click=lambda _: self.app.more.back(),
            ink=True,
            tooltip="Back (Run continues in background)",
        )
        self.hud_top_go_col = ft.Column(
            [
                ft.Row(
                    [
                        back_btn_go,
                        self.hud_go_time,
                        ft.Container(
                            self.hud_go_dist,
                            expand=True,
                            alignment=ft.Alignment.CENTER,
                        ),
                        self.hud_go_pace,
                    ],
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Row(
                    [
                        self.hud_layout_pill,
                        self.map_style_pill,
                        self.l_banner,
                        ft.Row(
                            [self.l_dot, self.l_status],
                            spacing=4,
                            tight=True,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                    ],
                    spacing=6,
                    alignment=ft.MainAxisAlignment.CENTER,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ],
            spacing=4,
            tight=True,
            visible=is_go,
        )

        self.hud_top_bar = ft.Container(
            ft.Column(
                [
                    self.hud_top_dock_row,
                    self.hud_top_go_col,
                    self.l_goal,
                    self.l_goal_txt,
                ],
                spacing=4,
                tight=True,
            ),
            top=10,
            left=10,
            right=10,
            bgcolor=HUD_GLASS_BG,
            border=ft.Border.all(1, HUD_GLASS_BORDER),
            border_radius=Radius.LG,
            padding=ft.Padding.symmetric(horizontal=12, vertical=8),
        )

        # Slime Core / Great Sage Level & Nearby Mobs Counter pill
        custom = self.app.game.profile.avatar_customization
        self.hud_slime_avatar = ft.Container(
            avatars.AvatarView(custom, size=22),
            width=22,
            height=22,
            border_radius=11,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        )
        self.hud_slime_text = ft.Text(
            "[MAGIC SENSE] Scouting · 0 DPS",
            size=11,
            weight=ft.FontWeight.W_800,
            color="#E2E8F0",
            expand=True,
        )
        self.hud_dock_toggle_icon = ft.Icon(
            ft.Icons.KEYBOARD_ARROW_UP
            if self._hud_dock_collapsed
            else ft.Icons.KEYBOARD_ARROW_DOWN,
            size=18,
            color=ARCANE_CYAN,
        )
        # Option A ('DOCK') Compact Encounter Strip (tappable to expand/collapse full AdventureRunCard)
        self.hud_dock_strip = ft.Container(
            ft.Row(
                [
                    self.hud_slime_avatar,
                    self.hud_slime_text,
                    self.hud_dock_toggle_icon,
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=HUD_GLASS_BG,
            border=ft.Border.all(1, HUD_GLASS_BORDER),
            border_radius=Radius.PILL,
            padding=ft.Padding.symmetric(horizontal=12, vertical=7),
            on_click=self._toggle_hud_dock,
            ink=True,
            tooltip="Tap to expand / collapse full Great Sage combat panel",
            visible=not is_go,
        )
        self.hud_slime_pill = self.hud_dock_strip

        # Option B ('GO') Bottom-Left Great Sage Status Pill & Bottom-Right Target Mode Orb
        self.hud_go_left_text = ft.Text(
            "GREAT SAGE · Scouting",
            size=11,
            weight=ft.FontWeight.W_800,
            color="#E2E8F0",
        )
        self.hud_go_avatar = ft.Container(
            avatars.AvatarView(custom, size=26),
            width=26,
            height=26,
            border_radius=13,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        )
        self.hud_go_left_pill = ft.Container(
            ft.Row(
                [
                    self.hud_go_avatar,
                    self.hud_go_left_text,
                ],
                spacing=6,
                tight=True,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=HUD_GLASS_BG,
            border=ft.Border.all(1, HUD_GLASS_BORDER),
            border_radius=Radius.PILL,
            padding=ft.Padding.symmetric(horizontal=10, vertical=6),
            on_click=self._recenter_map,
            ink=True,
            visible=is_go,
        )
        self.hud_go_target_label = ft.Text(
            "Lowest\nHP",
            size=9,
            weight=ft.FontWeight.W_800,
            color="#E2E8F0",
            text_align=ft.TextAlign.CENTER,
        )
        self.hud_go_target_orb = ft.Container(
            ft.Column(
                [
                    ft.Icon(ft.Icons.GPS_FIXED, size=16, color="#FACC15"),
                    self.hud_go_target_label,
                ],
                spacing=1,
                tight=True,
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            width=58,
            height=58,
            border_radius=29,
            bgcolor=HUD_GLASS_BG,
            border=ft.Border.all(1.5, C.a("#FACC15", 0.7)),
            alignment=ft.Alignment.CENTER,
            on_click=self._cycle_target_mode,
            ink=True,
            tooltip="Switch Target Mode (Lowest HP / Strongest)",
            visible=is_go,
        )

        # 1 km Surge / Encounter Alert banner
        self.hud_rift_icon = ft.Image(
            src=SPAWN_RIFT_ICON,
            width=18,
            height=18,
            fit=ft.BoxFit.CONTAIN,
            error_content=ft.Icon(ft.Icons.BOLT, size=14, color="#FACC15"),
        )
        self.hud_rift_text = ft.Text(
            "[GREAT SAGE] Spatial Rift detected!",
            size=10,
            weight=ft.FontWeight.W_800,
            color="#FACC15",
        )
        self.hud_rift_banner = ft.Container(
            ft.Row(
                [self.hud_rift_icon, self.hud_rift_text],
                spacing=4,
                tight=True,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=HUD_GLASS_BG,
            border=ft.Border.all(1, C.a("#FACC15", 0.55)),
            border_radius=Radius.PILL,
            padding=ft.Padding.symmetric(horizontal=9, vertical=4),
            visible=False,
        )

        def stat(ctrl: ft.Control, label: str) -> ft.Control:
            return ft.Column([ctrl, common.hint(label)], spacing=0, tight=True, expand=True,
                             horizontal_alignment=ft.CrossAxisAlignment.CENTER)

        self.full_stats = ft.Column([
            ft.Row([self.l_dist, ft.Text("km", size=Type.TITLE, color=C.TEXT_DIM)],
                   spacing=Space.SM, alignment=ft.MainAxisAlignment.CENTER,
                   vertical_alignment=ft.CrossAxisAlignment.END),
            ft.Row([stat(self.l_time, "moving time"), stat(self.l_pace, "pace /km"),
                    stat(self.l_avg, "avg /km")]),
        ], spacing=Space.SM, tight=True)
        self.basic_stats = ft.Container(
            common.card(ft.Column([
                ft.Row([self.l_steps, ft.Text("steps (est.)", size=Type.TITLE,
                                              color=C.TEXT_DIM)],
                       spacing=Space.SM, alignment=ft.MainAxisAlignment.CENTER,
                       vertical_alignment=ft.CrossAxisAlignment.END),
                ft.Row([stat(self.l_btime, "moving time")]),
                ft.Row([
                    ft.Icon(ft.Icons.LOCK_OPEN, size=18, color="#F5C66B"),
                    ft.Text("Basic tracking: steps and time. Unlock full tracking: watch the "
                            f"stretch ad next run or go {premium.PREMIUM_NAME}.",
                            size=Type.CAPTION, color=C.TEXT_DIM, expand=True)],
                    spacing=Space.SM),
            ], spacing=Space.SM, tight=True)),
            top=90,
            left=12,
            right=12,
            visible=False,
        )
        self.adventure_card = AdventureRunCard(
            self.adventure_engine,
            on_play_sound=self._play_adventure_sound,
            on_target_changed=self._on_card_target_changed,
        )
        self.adventure_wrap = ft.Container(
            self.adventure_card,
            visible=(not is_go) and (not self._hud_dock_collapsed),
        )
        self.bottom_hud_dock = ft.Container(
            ft.Column(
                [
                    ft.Row(
                        [self.hud_go_left_pill, ft.Container(expand=True), self.hud_rift_banner],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    self.adventure_wrap,
                    self.hud_dock_strip,
                    ft.Row(
                        [
                            ft.Container(width=58, visible=is_go),
                            ft.Row(
                                [self.b_pause, self.b_finish],
                                spacing=Space.XL,
                                alignment=ft.MainAxisAlignment.CENTER,
                            ),
                            self.hud_go_target_orb,
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                        if is_go
                        else ft.MainAxisAlignment.CENTER,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                ],
                spacing=8,
                tight=True,
            ),
            bottom=10,
            left=10,
            right=10,
        )
        self.map_stack = ft.Stack(
            [
                self.map_host,
                self.hud_top_bar,
                self.basic_stats,
                self.bottom_hud_dock,
            ],
            expand=True,
        )
        self.map_wrap = ft.Container(
            self.map_stack,
            expand=True,
        )
        # Single full-height map frame inside the body area, with slim margins so the
        # flowing MindSpace background remains visible around the rounded border!
        self.live_view = ft.Container(
            self.map_wrap,
            expand=True,
            padding=ft.Padding.only(left=10, right=10, top=6, bottom=10),
        )

    def _make_map(self, center: tuple[float, float], route: list, *, live: bool,
                  height: int = LIVE_MAP_H) -> tuple[Any, Any, Any]:
        """(map, polyline layer, marker layer). Returns (None, ...) if flet_map is missing."""
        try:
            import flet_map as fm
        except ImportError:
            return None, None, None
        tile_url = self._tile_url_for_style() if live else OSM_TILE_URL
        tile_layer = fm.TileLayer(url_template=tile_url, user_agent_package_name=TILE_UA)
        veil = fm.CircleLayer(
            circles=[
                fm.CircleMarker(
                    radius=50000,
                    coordinates=fm.MapLatitudeLongitude(*center),
                    color=ARCANE_VEIL_COLOR,
                    use_radius_in_meter=True,
                )
            ]
            if (live and self._map_style == "arcane")
            else []
        )
        poly = fm.PolylineLayer(polylines=[
            fm.PolylineMarker(coordinates=[fm.MapLatitudeLongitude(*p) for p in seg],
                              color=ROUTE_COLOR, stroke_width=5, border_color=C.a("#000000",
                                                                                  0.35),
                              border_stroke_width=1.5)
            for seg in route if seg] or [fm.PolylineMarker(coordinates=[], stroke_width=5,
                                                           color=ROUTE_COLOR)])
        circles = fm.CircleLayer(circles=[])
        markers = fm.MarkerLayer(markers=[])
        pts = [p for seg in route for p in seg]
        fit = (fm.CameraFit(coordinates=[fm.MapLatitudeLongitude(*p) for p in pts],
                            padding=ft.Padding.all(36), max_zoom=17)
               if not live and len(pts) > 1 else None)
        flags = (fm.InteractionFlag.PINCH_ZOOM | fm.InteractionFlag.DOUBLE_TAP_ZOOM
                 | fm.InteractionFlag.SCROLL_WHEEL_ZOOM) if live else fm.InteractionFlag.ALL
        m = fm.Map(
            layers=[
                tile_layer,
                veil,
                poly,
                circles,
                markers,
                fm.SimpleAttribution(text=OSM_ATTRIBUTION,
                                     text_style=ft.TextStyle(size=9, color="#94A3B8"),
                                     bgcolor=C.a("#070B14", 0.65),
                                     alignment=ft.Alignment.TOP_RIGHT),
            ],
            initial_center=fm.MapLatitudeLongitude(*center),
            initial_zoom=17 if live else 16,
            initial_camera_fit=fit,
            height=None if live else height,
            expand=live,
            keep_alive=True,
            bgcolor="#070B14",
            interaction_configuration=fm.InteractionConfiguration(flags=flags),
        )
        if live:
            self._map = m
            self._tile_layer = tile_layer
            self._veil_layer = veil
            self._polyline_layer = poly
            self._circle_layer = circles
            self._marker_layer = markers
            self.live_circles = circles
        return m, poly, markers

    def _active_cluster(self) -> Any:
        cluster = getattr(self._adv_state, "active_cluster", None)
        if cluster is not None:
            return cluster
        return getattr(self.adventure_engine, "active_cluster", None)

    def _paint_live(self) -> None:
        tr = self.tracker
        if tr is None:
            return
        now = self.gps.now()
        basic = self.tracking == "basic"
        self.full_stats.visible = not basic
        self.basic_stats.visible = basic
        self._sync_hud_layout()
        if basic:
            self.l_steps.value = f"{self._steps_now():,}"
            self.l_btime.value = rcore.fmt_duration(tr.moving_s)
        dist_str = km(tr.distance_m)
        time_str = rcore.fmt_duration(tr.moving_s)
        pace_val = tr.current_pace(now)
        pace_str = rcore.fmt_pace(pace_val)
        self.l_dist.value = dist_str
        self.l_time.value = time_str
        self.l_pace.value = pace_str
        self.l_avg.value = rcore.fmt_pace(rcore.pace_s_per_km(tr.distance_m, tr.moving_s))
        acc = self.acc
        dot_col = _acc_color(acc)
        self.l_dot.bgcolor = dot_col

        # Update floating Pokémon GO / Great Sage map HUD controls (both Option A & Option B)
        if hasattr(self, "hud_dist_text"):
            self.hud_dist_text.value = f"{dist_str} km"
            self.hud_time_text.value = time_str
            self.hud_pace_text.value = f"{pace_str} /km"
            self.hud_gps_dot.bgcolor = dot_col
        if hasattr(self, "hud_go_dist"):
            self.hud_go_dist.value = f"{dist_str} km"
            self.hud_go_time.value = time_str
            self.hud_go_pace.value = f"{pace_str} /km"
        if hasattr(self, "hud_go_target_label"):
            tmode = self.adventure_engine.target_mode
            self.hud_go_target_label.value = (
                "Strongest" if tmode == TargetMode.STRONGEST
                else "Manual" if tmode == TargetMode.MANUAL
                else "Lowest\nHP"
            )
        speed_kmh = 3600.0 / pace_val if (pace_val and pace_val > 0 and not tr.paused) else 0.0
        dps_now = self.adventure_engine.base_dps(speed_kmh)
        cluster = self._active_cluster()
        if hasattr(self, "hud_slime_text"):
            if cluster is not None and cluster.has_alive:
                alive_n = len(cluster.alive_creatures)
                self.hud_slime_text.value = (
                    f"[MAGIC SENSE] {alive_n} mob{'s' if alive_n != 1 else ''} nearby · "
                    f"{dps_now:.0f} DPS"
                )
                if hasattr(self, "hud_go_left_text"):
                    self.hud_go_left_text.value = (
                        f"GREAT SAGE · {alive_n} mobs · {dps_now:.0f} DPS"
                    )
            else:
                left_m = max(
                    0.0,
                    self.adventure_engine.next_spawn_distance_m
                    - self.adventure_engine.total_distance_m,
                )
                self.hud_slime_text.value = (
                    f"[MAGIC SENSE] Rift ~{left_m:.0f}m · {dps_now:.0f} DPS"
                )
                if hasattr(self, "hud_go_left_text"):
                    self.hud_go_left_text.value = (
                        f"GREAT SAGE · Rift ~{left_m:.0f}m · {dps_now:.0f} DPS"
                    )
        if hasattr(self, "hud_rift_banner"):
            active_rift = (cluster is not None and cluster.has_alive) or (
                now < self._rift_alert_until
            )
            self.hud_rift_banner.visible = active_rift
            if now < self._rift_alert_until:
                self.hud_rift_text.value = self._rift_alert_msg
            elif cluster is not None and cluster.has_alive:
                self.hud_rift_text.value = (
                    "[GREAT SAGE] Boss Rift!" if cluster.has_boss
                    else "[GREAT SAGE] Spatial Rift detected!"
                )

        state = ("Paused" if tr.paused else "Waiting for GPS…" if not tr.points
                 else f"GPS ±{acc:.0f} m" if acc is not None else "GPS")
        self.l_status.value = state
        self.l_banner.visible = tr.auto_paused(now)
        if self.goal:
            t = TIER_BY_ID[self.goal]
            self.l_goal.visible = self.l_goal_txt.visible = True
            self.l_goal.value = min(1.0, tr.distance_m / t.meters)
            left = t.meters - tr.distance_m
            self.l_goal_txt.value = (f"Goal {t.label} reached!" if left <= 0
                                     else f"Goal {t.label}" if basic
                                     else f"Goal {t.label}: {left / 1000:.2f} km to go")
        else:
            self.l_goal.visible = self.l_goal_txt.visible = False
        self.b_pause.content.icon = ft.Icons.PLAY_ARROW if tr.paused else ft.Icons.PAUSE
        self.b_pause.tooltip = "Resume" if tr.paused else "Pause"

    def _update_map(self, now: float | None = None) -> None:
        tr = self.tracker
        m = self.live_map or self._map
        if tr is None or m is None:
            return
        try:
            import flet_map as fm
        except ImportError:
            return
        if now is None:
            now = self.gps.now()

        segs = tr.route()
        total = sum(len(s) for s in segs)
        step = max(1, math.ceil(total / LIVE_MAP_POINTS))
        lines = []
        for seg in segs:
            pts = seg[::step] + ([seg[-1]] if (len(seg) - 1) % step else [])
            lines.append(fm.PolylineMarker(
                coordinates=[fm.MapLatitudeLongitude(*p) for p in pts], color=ROUTE_COLOR,
                stroke_width=5, border_color=C.a("#000000", 0.35), border_stroke_width=1.5))
        poly_layer = self.live_poly or self._polyline_layer
        if poly_layer is not None:
            poly_layer.polylines = lines or poly_layer.polylines

        pts_all = [p for seg in segs for p in seg]
        here = (pts_all[-1] if pts_all else None) or self.pos or MANILA
        if self._veil_layer is not None:
            self._veil_layer.circles = (
                [
                    fm.CircleMarker(
                        radius=50000,
                        coordinates=fm.MapLatitudeLongitude(here[0], here[1]),
                        color=ARCANE_VEIL_COLOR,
                        use_radius_in_meter=True,
                    )
                ]
                if self._map_style == "arcane"
                else []
            )
        circle_layer = self._circle_layer or self.live_circles
        marks: list[Any] = []
        if segs and segs[0]:
            marks.append(
                fm.Marker(
                    content=_dot("#5EEAB0", 20),
                    coordinates=fm.MapLatitudeLongitude(*segs[0][0]),
                    width=20,
                    height=20,
                )
            )
        if here:
            if circle_layer is not None:
                circle_layer.circles = [
                    fm.CircleMarker(
                        radius=38,
                        coordinates=fm.MapLatitudeLongitude(here[0], here[1]),
                        color="#144FE3F0",
                        border_color="#884FE3F0",
                        border_stroke_width=2,
                        use_radius_in_meter=True,
                    ),
                    fm.CircleMarker(
                        radius=14,
                        coordinates=fm.MapLatitudeLongitude(here[0], here[1]),
                        color="#247A5CFF",
                        border_color="#AA4FE3F0",
                        border_stroke_width=1.5,
                        use_radius_in_meter=True,
                    ),
                ]
            cluster = self._active_cluster()
            if cluster is not None and getattr(cluster, "creatures", None):
                eng = self.adventure_engine
                target = cluster.select_target(eng.target_mode, eng.manual_target_id)
                last_hit = self.adventure_card.last_hit if self.adventure_card else None
                for c in cluster.creatures:
                    c_lat, c_lon = creature_latlon(here, c)
                    is_targeted = target is not None and c.id == target.id
                    marker_ctrl = build_map_creature_marker(
                        c,
                        is_targeted=is_targeted,
                        last_hit=last_hit,
                        on_tap=self._on_target_creature,
                    )
                    mw = 52 if c.is_alive else 36
                    mh = 60 if c.is_alive else 36
                    marks.append(
                        fm.Marker(
                            content=marker_ctrl,
                            coordinates=fm.MapLatitudeLongitude(c_lat, c_lon),
                            width=mw,
                            height=mh,
                        )
                    )
            marks.append(
                fm.Marker(
                    content=_player_slime_beacon(self.app.game.profile.avatar_customization),
                    coordinates=fm.MapLatitudeLongitude(here[0], here[1]),
                    width=44,
                    height=44,
                )
            )
        elif circle_layer is not None:
            circle_layer.circles = []

        marker_layer = self.live_marks or self._marker_layer
        if marker_layer is not None:
            marker_layer.markers = marks

        if _is_mounted(m):
            ui.refresh(m)
            if here and now - self._last_follow >= FOLLOW_EVERY_S:
                self._last_follow = now
                self.app.page.run_task(self._follow, here)

    async def _follow(self, here: tuple[float, float]) -> None:
        with contextlib.suppress(Exception):
            import flet_map as fm

            await self.live_map.move_to(destination=fm.MapLatitudeLongitude(*here))

    def _steps_now(self) -> int:
        tr = self.tracker
        if tr is None:
            return 0
        return rcore.steps_for(rcore.chunks(tr.points),
                               self.app.game.data.body.height_cm or rcore.DEFAULT_HEIGHT_CM,
                               tr.mode)

    def _stretch_only(self, _: Any = None) -> None:
        from lol.ui.screens.stretch import open_stretch_sheet

        g, today = self.app.game, self.app.today()
        open_stretch_sheet(self.app, with_ad=False,
                           notes=g.run_advice(self.settings.mode, today).notes,
                           on_start=lambda res: self.app.page.run_task(self._start))

    async def _start(self, _: Any = None) -> None:
        """Premium (or no ad to show): straight to full tracking. Free: the stretch sheet
        with the optional ad; watched -> full, skipped/declined -> basic."""
        if self.perm != gps.GRANTED:
            sfx.play("error_soft")
            self.app.toast("Allow location first, or log the session by hand.",
                           ft.Icons.GPS_OFF)
            return
        g, today = self.app.game, self.app.today()
        if g.is_premium(today) or not ads.can_show(self.app):
            await self._begin(premium.run_tracking(g.is_premium(today), "unavailable"))
            return
        from lol.ui.screens.stretch import open_stretch_sheet

        def go(res: str | None) -> None:
            async def later() -> None:
                await asyncio.sleep(0.35)  # let the sheet close first
                await self._begin(premium.run_tracking(False, res))
            self.app.page.run_task(later)

        open_stretch_sheet(self.app, with_ad=True,
                           notes=g.run_advice(self.settings.mode, today).notes, on_start=go)

    async def _begin(self, tracking: str) -> None:
        if self.phase == "live":
            return
        self.tracking = tracking
        g, s = self.app.game, self.settings
        now = self.gps.now()
        self.tracker = rcore.Tracker(s.mode, now)
        uncleared = [(st.tier.id, st.tier.meters) for st in g.ladder(s.mode)
                     if st.state != "cleared"]
        goal_m = TIER_BY_ID[self.goal].meters if self.goal else None
        self.coach = CueCoach(s.mode, s.cue_every, goal_m, uncleared)
        self.adventure_engine = AdventureEngine()
        self._adv_state = _AdvStateProxy(
            self.adventure_engine, {"dist": 0.0, "t": now, "last_step": now}
        )
        self.started = datetime.now().strftime("%H:%M")
        self.phase = "live"
        self.gen += 1
        center = self.pos or MANILA
        self._build_live()  # fresh controls each session (see render)
        self.live_map, self.live_poly, self.live_marks = self._make_map(
            center, [], live=True, height=LIVE_MAP_H)
        self.map_host.content = self.live_map or ft.Container(
            common.hint("Map unavailable"), alignment=ft.Alignment.CENTER)
        self._refresh()  # mount live_view & map into page first so they are mounted!
        self._update_map(now)  # safe to update now that map is mounted
        self.gps.start(self._on_fix, s.mode)
        sfx.play("objective_new")
        self.app.page.run_task(self._tick, self.gen)
        if s.keep_awake and self.wake is not None:
            # web has no wakelock and never answers; never let it hold up the run
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self.wake.enable(), WAKE_TIMEOUT_S)
        await ui.buzz("medium")

    async def _tick(self, gen: int) -> None:
        while self.gen == gen and self.phase == "live":
            await asyncio.sleep(TICK_S)
            if self.gen != gen or self.phase != "live" or self.tracker is None:
                return
            now = self.gps.now()
            last_step = (
                self._adv_state.get("last_step", 0.0)
                if isinstance(self._adv_state, dict)
                else getattr(self._adv_state, "last_step", 0.0)
            )
            if now - last_step >= TICK_S * 0.5:
                self._step_live(now)

    def _step_live(self, now: float) -> None:
        """Advance live stats, map, Adventure Run combat and voice cues. Called by both the 1s
        timer loop and incoming GPS fixes so background / screen-off runs never stall."""
        if self.phase != "live" or self.tracker is None:
            return
        if isinstance(self._adv_state, dict):
            self._adv_state["last_step"] = now
        # Only touch UI controls if live_view is currently mounted on screen
        is_mounted = _is_mounted(self.live_view)
        with contextlib.suppress(Exception):  # the adventure must never break a run
            self._adventure_tick(now, self._adv_state)
        if is_mounted:
            self._paint_live()
            wall = time.monotonic()
            n = len(self.tracker.points)
            if wall - self._last_map >= MAP_EVERY_S and n != self._map_points:
                self._last_map, self._map_points = wall, n
                self._update_map(now)  # the polyline is the heavy part: every 2 s at most
            ui.refresh(self.live_view)
        self._cues(now)

    def _adventure_tick(self, now: float, adv: dict[str, float]) -> None:
        """Feed the Adventure engine from the tracker. No GPS permission, no fix yet
        (emulator / Bluestacks / PC), paused or auto-paused -> 0 km/h: the pack waits and
        nothing crashes. Background gaps are stepped in slices up to ADV_MAX_TICK_S so
        combat progress, spawns, and trinket coin drops continue while tabbed out or locked."""
        tr, card = self.tracker, self.adventure_card
        if tr is None:
            return
        prev_t = adv["t"] if isinstance(adv, dict) else getattr(adv, "t", now)
        prev_dist = adv["dist"] if isinstance(adv, dict) else getattr(adv, "dist", 0.0)
        raw_delta = min(ADV_MAX_BG_GAP_S, max(0.0, now - prev_t))
        total_dist_inc = max(0.0, tr.distance_m - prev_dist)
        crossed_km = is_km_milestone(prev_dist, tr.distance_m)
        if isinstance(adv, dict):
            adv["t"], adv["dist"] = now, tr.distance_m
        speed_kmh = 0.0
        if not (tr.paused or tr.auto_paused(now) or self.perm != gps.GRANTED or not tr.points):
            pace = tr.current_pace(now)
            if pace and pace > 0:
                speed_kmh = 3600.0 / pace
            elif raw_delta > 0 and total_dist_inc > 0:
                speed_kmh = total_dist_inc / raw_delta * 3.6
        steps = max(1, math.ceil(raw_delta / ADV_MAX_TICK_S)) if raw_delta > 0 else 1
        step_dt = raw_delta / steps if raw_delta > 0 else 0.0
        step_dist = total_dist_inc / steps
        all_events = []
        coins_granted_total = 0
        today = self.app.today()
        for _ in range(steps):
            evs = self.adventure_engine.update_tick(step_dt, speed_kmh, step_dist)
            for ev in evs:
                if ev.event_type == EventType.CREATURE_DEFEATED and ev.coins_gained > 0:
                    granted = self.app.game.award_adventure_coins(ev.coins_gained, today)
                    ev.coins_gained = granted
                    coins_granted_total += granted
            all_events.extend(evs)
        bg_alert_msg: str | None = None
        if crossed_km or any(ev.event_type == EventType.MILESTONE_SURGE for ev in all_events):
            self._rift_alert_until = now + 6.0
            self._rift_alert_msg = "⚡ [GREAT SAGE] 1 KM SURGE!"
            bg_alert_msg = f"⚡ 1 KM Surge! ({km(tr.distance_m)} km covered)"
            if card is not None:
                card.show_km_surge_callout("⚡ GREAT SAGE · 1 KM SURGE")
        elif any(ev.event_type == EventType.SPAWN_CLUSTER for ev in all_events):
            self._rift_alert_until = now + 6.0
            self._rift_alert_msg = "[GREAT SAGE] Spatial Rift detected!"
            spawn_ev = next(ev for ev in all_events if ev.event_type == EventType.SPAWN_CLUSTER)
            bg_alert_msg = f"Spatial Rift detected! {spawn_ev.message}"
        elif any(ev.event_type == EventType.CLUSTER_CLEARED for ev in all_events):
            bg_alert_msg = (
                f"Pack cleared at {km(tr.distance_m)} km! "
                f"Total: +{self.adventure_engine.total_xp_earned} XP, "
                f"+{self.adventure_engine.total_coins_earned} coins."
            )
        is_mounted = _is_mounted(self.live_view)
        if bg_alert_msg and (not is_mounted or notify.available()):
            with contextlib.suppress(Exception):
                self.app.page.run_task(
                    notify.post_run_alert, "LUMA · Great Sage", bg_alert_msg
                )
        if coins_granted_total > 0:
            self.app.save()
            with contextlib.suppress(Exception):
                self.app.page.run_task(self.app.coins_changed)
        if card is not None:
            card.process_tick_events(all_events)
            card.refresh_display(current_speed_kmh=speed_kmh)
        if all_events and is_mounted:
            self._update_map(now)

    def _cues(self, now: float) -> None:
        tr, coach = self.tracker, self.coach
        if tr is None or coach is None or tr.paused or self.tracking == "basic":
            return  # voice cues are part of full tracking
        steps = rcore.steps_for(rcore.chunks(tr.points),
                                self.app.game.data.body.height_cm or rcore.DEFAULT_HEIGHT_CM,
                                tr.mode)
        pace = tr.current_pace(now) or rcore.pace_s_per_km(tr.distance_m, tr.moving_s)
        due = coach.update(tr.distance_m, tr.moving_s, pace, steps, rcore.splits(tr.points))
        if due and self.settings.voice_cues:
            for keys in due:
                audio.play_sequence(keys)

    async def _toggle_pause(self, _: Any = None) -> None:
        tr = self.tracker
        if tr is None:
            return
        await ui.pop(self.b_pause)
        now = self.gps.now()
        if tr.paused:
            tr.resume(now)
            sfx.play("toggle")
        else:
            tr.pause(now)
            sfx.play("tap")
        await ui.buzz("select")
        self._paint_live()
        ui.refresh(self.live_view)

    async def _finish_tap(self, _: Any = None) -> None:
        tr = self.tracker
        if tr is None:
            return
        if self._finish_open:
            return
        self._finish_open = True
        await ui.pop(self.b_finish)
        short = tr.distance_m < MIN_LOG_M
        shown = (f"{self._steps_now():,} steps (est.)" if self.tracking == "basic"
                 else f"{km(tr.distance_m)} km")
        body = [common.hint(f"{shown} · {rcore.fmt_duration(tr.moving_s)} "
                            "moving" + (" - too short to save." if short else "."))]
        if not short:
            body.append(ft.Row([common.primary_button(
                "Finish & save", lambda e: self._close_then(sheet, self._save),
                icon=ft.Icons.CHECK)]))
        body.append(ft.Row([common.secondary_button(
            "Keep going", lambda e: self._close_then(sheet, self._noop),
            icon=ft.Icons.PLAY_ARROW),
            common.secondary_button("Discard", lambda e: self._close_then(sheet,
                                                                          self._discard),
                                    icon=ft.Icons.DELETE_OUTLINE, color=C.DANGER)],
            spacing=Space.SM))
        sheet = common.open_sheet(self.app.page, "Finish?", body,
                                  on_dismiss=lambda: setattr(self, "_finish_open", False))

    def _close_then(self, sheet: Any, fn: Any) -> None:
        """Close the Finish sheet, then run fn once it is gone (a dialog opened while the
        sheet is still closing ends up underneath it)."""
        self._finish_open = False
        common.close(sheet)

        async def later() -> None:
            await asyncio.sleep(0.35)
            await fn()

        self.app.page.run_task(later)

    async def _noop(self) -> None:
        return None

    async def _stop_tracking(self) -> None:
        self.gen += 1
        self.gps.stop()
        if self.wake is not None:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self.wake.disable(), WAKE_TIMEOUT_S)

    async def _discard(self) -> None:
        self._finish_open = True  # no second Finish sheet over the confirm dialog
        try:
            if self.tracker and self.tracker.distance_m >= MIN_LOG_M and not await                     common.confirm(self.app.page, "Discard this session?",
                                   "The route and numbers are not saved.", "Discard",
                                   danger=True):
                return
        finally:
            self._finish_open = False
        await self._stop_tracking()
        self.tracker, self.phase = None, "pre"
        sfx.play("tab_close")
        self._refresh()
        self.app.page.run_task(self._check_gps)

    async def _save(self) -> None:
        app, g, tr = self.app, self.app.game, self.tracker
        if tr is None:
            return
        await self._stop_tracking()
        now = self.gps.now()
        today = app.today()
        body = g.run_body(today)
        tiers = [(t.id, t.meters) for t in TIER_BY_ID.values()]

        def work() -> rcore.RunStats:
            return rcore.summarize(tr, now, weight_kg=body["weight_kg"],
                                   height_cm=body["height_cm"], bmr_kcal_day=body["bmr"],
                                   tiers=tiers)

        stats = await ui.lumen_analyze(app.page, STAGES, work=work)
        goal = self.goal

        def line(c: Any) -> str:
            return (f"Notice: {MODE_INFO[stats.mode][0]} logged: {km(stats.distance_m)} km. "
                    f"+{c.xp} XP to Warrior Path.")

        try:
            c = await app.award(lambda: g.log_run(stats, today, started=self.started,
                                                  goal=goal, basic=self.tracking == "basic"),
                                line=line)
        except ValueError as exc:
            app.error(f"Couldn't save it: {exc}")
            return
        if not (c.xp or c.coins):
            sfx.play("tap")
            app.toast("Logged. Short sessions (or today's workout XP cap) give no XP - "
                      "it still counts.", ft.Icons.DIRECTIONS_RUN)
        self.result, self.result_new = g.run(c.ref_id), True
        self.tracker, self.phase = None, "summary"
        if self.result.cleared:
            sfx.play("rank_up")
        self._refresh()

    # ------------------------------------------------------------------ summary
    def _summary(self, r: RunEntry) -> list[ft.Control]:
        if self._hidden_stats(r):
            return self._basic_summary(r)
        route = [[tuple(p) for p in seg] for seg in r.route]
        pts = [p for seg in route for p in seg]
        m, _, marks = self._make_map(pts[0] if pts else MANILA, route, live=False,
                                     height=260)
        if m is not None and pts:
            import flet_map as fm

            marks.markers = [
                fm.Marker(content=_dot("#5EEAB0", 16),
                          coordinates=fm.MapLatitudeLongitude(*pts[0]), width=16, height=16),
                fm.Marker(content=ft.Container(ft.Icon(ft.Icons.SPORTS_SCORE, size=16,
                                                       color="#FFFFFF"),
                                               width=24, height=24, border_radius=12,
                                               bgcolor="#E5484D",
                                               alignment=ft.Alignment.CENTER),
                          coordinates=fm.MapLatitudeLongitude(*pts[-1]), width=24, height=24),
            ]
        d = date.fromisoformat(r.day)
        pace = rcore.pace_s_per_km(r.distance_m, r.moving_s)

        def stat(value: str, label: str) -> ft.Control:
            return ft.Column([ft.Text(value, size=Type.HEADLINE, weight=ft.FontWeight.W_800,
                                      color=C.TEXT), common.hint(label)],
                             spacing=0, tight=True, col=4,
                             horizontal_alignment=ft.CrossAxisAlignment.CENTER)

        items: list[ft.Control] = [
            ft.Text(f"{MODE_INFO[r.mode][0]} · {d:%A} {common.short_date(d)}"
                    + (f" · {r.started}" if r.started else ""), size=Type.TITLE,
                    weight=ft.FontWeight.W_800, color=C.TEXT),
            ft.Container(m or common.hint("Map unavailable"), height=260,
                         border_radius=Radius.MD, clip_behavior=ft.ClipBehavior.ANTI_ALIAS),
        ]
        if r.cleared:
            labels = ", ".join(TIER_BY_ID[t].label for t in r.cleared if t in TIER_BY_ID)
            top = r.cleared[-1]
            badge = next((s.badge for s in self.app.game.ladder(r.mode)
                          if s.tier.id == top), None)
            items.append(common.card(ft.Row([
                ft.Icon(ft.Icons.EMOJI_EVENTS, color=C.ACCENT, size=30),
                ft.Column([ft.Text(f"Tier cleared: {labels}", size=Type.BODY,
                                   weight=ft.FontWeight.W_800, color=C.TEXT),
                           common.hint("The next tier is available from tomorrow. "
                                       "No rush - it waits for you.")],
                          spacing=2, tight=True, expand=True),
                ui.chip(badge or "Finisher", icon=ft.Icons.SPEED, color=ROUTE_COLOR),
            ], spacing=Space.MD), tint="#F5C66B"))
        items.append(common.card(ft.ResponsiveRow([
            stat(km(r.distance_m), "km"),
            stat(rcore.fmt_duration(r.moving_s), "moving"),
            stat(rcore.fmt_pace(pace), "avg /km"),
            stat(rcore.fmt_duration(r.elapsed_s), "elapsed"),
            stat(f"{r.elev_gain_m:.0f} m" if r.elev_gain_m is not None else "-", "climb"),
            stat(f"{r.steps:,}", "steps (est.)"),
        ], run_spacing=Space.MD)))
        net = max(0, r.kcal - r.rest_kcal)
        w_note = (f"{rcore.DEFAULT_WEIGHT_KG:g} kg estimate - add your weight for better "
                  "numbers" if r.weight_assumed else f"at {r.weight_kg:g} kg")
        items.append(common.card(ft.Column([
            ft.Row([ft.Icon(ft.Icons.LOCAL_FIRE_DEPARTMENT, color="#FF8A5B", size=22),
                    ft.Text(f"{r.kcal} kcal", size=Type.HEADLINE, weight=ft.FontWeight.W_800,
                            color=C.TEXT),
                    ft.Container(expand=True),
                    ft.Text(f"{net} net", size=Type.TITLE, weight=ft.FontWeight.W_700,
                            color=C.TEXT)]),
            common.hint(f"Total burn (estimate, {w_note}). Net = above the {r.rest_kcal} kcal "
                        "your body would burn resting in the same time."),
        ], spacing=Space.XS, tight=True)))
        if r.splits:
            rows = [(str(i + 1), float(s), rcore.fmt_pace(s)) for i, s in enumerate(r.splits)]
            items.append(common.section("Splits (per km)"))
            items.append(common.card(common.bar_chart(rows, height=120, color=ROUTE_COLOR)))
        if r.xp or r.coins:
            items.append(ft.Row([ui.xp_chip(r.xp), ui.coin_chip(r.coins)], spacing=Space.SM,
                                alignment=ft.MainAxisAlignment.CENTER))
        items.append(ft.Row([common.primary_button("Done", self._back_to_pre,
                                                   icon=ft.Icons.CHECK)]))
        if not self.result_new:
            items.append(ft.Row([common.secondary_button(
                "Delete this session", lambda e: self._delete(r.id),
                icon=ft.Icons.DELETE_OUTLINE, color=C.DANGER)]))
        return items

    def _basic_summary(self, r: RunEntry) -> list[ft.Control]:
        """Basic tracking (free, stretch ad skipped): steps + time only. Map, pace, splits
        and kcal stay hidden; going premium reveals them (the data is the user's anyway and
        is in every export)."""
        d = date.fromisoformat(r.day)

        def stat(value: str, label: str) -> ft.Control:
            return ft.Column([ft.Text(value, size=Type.HEADLINE + 4, weight=ft.FontWeight.W_800,
                                      color=C.TEXT), common.hint(label)],
                             spacing=0, tight=True, col=6,
                             horizontal_alignment=ft.CrossAxisAlignment.CENTER)

        items: list[ft.Control] = [
            ft.Text(f"{MODE_INFO[r.mode][0]} · {d:%A} {common.short_date(d)}"
                    + (f" · {r.started}" if r.started else ""), size=Type.TITLE,
                    weight=ft.FontWeight.W_800, color=C.TEXT),
            common.card(ft.ResponsiveRow([
                stat(f"{r.steps:,}", "steps (est.)"),
                stat(rcore.fmt_duration(r.moving_s), "moving time"),
            ], run_spacing=Space.MD)),
            common.card(ft.Column([
                ft.Row([ft.Icon(ft.Icons.LOCK, color="#F5C66B", size=18),
                        ft.Text("Basic tracking", size=Type.BODY, weight=ft.FontWeight.W_700,
                                color=C.TEXT)], spacing=Space.SM),
                common.hint("Map, pace, splits and kcal are hidden for this run. Unlock full "
                            "tracking: watch the stretch ad next run or go "
                            f"{premium.PREMIUM_NAME}."),
                ft.Row([common.secondary_button(f"See {premium.PREMIUM_NAME}",
                                                lambda e: self.app.open_sub("premium"),
                                                icon=ft.Icons.WORKSPACE_PREMIUM,
                                                color="#F5C66B")]),
            ], spacing=Space.SM, tight=True), padding=Space.MD),
        ]
        if r.cleared:
            labels = ", ".join(TIER_BY_ID[t].label for t in r.cleared if t in TIER_BY_ID)
            items.append(common.card(ft.Row([
                ft.Icon(ft.Icons.EMOJI_EVENTS, color=C.ACCENT, size=26),
                ft.Text(f"Tier cleared: {labels}", size=Type.BODY, weight=ft.FontWeight.W_800,
                        color=C.TEXT, expand=True)], spacing=Space.MD), tint="#F5C66B"))
        if r.xp or r.coins:
            items.append(ft.Row([ui.xp_chip(r.xp), ui.coin_chip(r.coins)], spacing=Space.SM,
                                alignment=ft.MainAxisAlignment.CENTER))
        items.append(ft.Row([common.primary_button("Done", self._back_to_pre,
                                                   icon=ft.Icons.CHECK)]))
        if not self.result_new:
            items.append(ft.Row([common.secondary_button(
                "Delete this session", lambda e: self._delete(r.id),
                icon=ft.Icons.DELETE_OUTLINE, color=C.DANGER)]))
        return items

    def _back_to_pre(self, _: Any = None) -> None:
        self.phase, self.result = "pre", None
        self._refresh()
        self.app.page.run_task(self._check_gps)

    async def _delete(self, run_id: str) -> None:
        if not await common.confirm(self.app.page, "Delete this session?",
                                    "The route and its workout entry are removed. XP you "
                                    "earned stays.", "Delete", danger=True):
            return
        self.app.game.delete_run(run_id)
        self.app.save()
        sfx.play("tab_close")
        self._back_to_pre()

