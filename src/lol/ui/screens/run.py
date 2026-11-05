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
from lol.core.adventure import AdventureEngine, EventType
from lol.core.models import RunEntry
from lol.core.run_cues import CUE_EVERY, CueCoach
from lol.core.runlog import CHALLENGE_COINS, CHALLENGE_XP, MIN_LOG_M, PACE_BADGES, TIER_BY_ID
from lol.ui import ads, audio, gps, sfx
from lol.ui import components as ui
from lol.ui import theme as th
from lol.ui.adventure_layer import AdventureRunCard
from lol.ui.screens import common
from lol.ui.theme import C, Radius, Size, Space, Type

if TYPE_CHECKING:
    from lol.ui.app import App

log = logging.getLogger(__name__)

OSM_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
OSM_ATTRIBUTION = "OpenStreetMap contributors"  # the attribution layer adds the ©
# identifies the app to the tile server (OSM policy: a clear app name, not a library default)
TILE_UA = "LifeOfLegends/0.1 (com.jarvin.lifeoflegends)"
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
        self.live_map: Any = None
        self.live_poly: Any = None
        self.live_marks: Any = None
        self.adventure_engine = AdventureEngine()
        self.adventure_card: AdventureRunCard | None = None
        self._adv_state: dict[str, float] = {"dist": 0.0, "t": 0.0, "last_step": 0.0}
        self._build_live()

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

    def on_enter(self) -> None:
        if self.phase == "pre":
            self.app.page.run_task(self._check_gps)

    def on_leave(self) -> None:
        if self.phase != "live":
            self.gps.stop()

    @property
    def settings(self):
        return self.app.game.data.run_settings

    def render(self) -> None:
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

        return common.card(ft.Column([
            common.switch_row("Keep screen awake", "Keep display on while viewing Run (tracking "
                              "also continues with screen off or in background)", s.keep_awake,
                              awake, icon=ft.Icons.SCREEN_LOCK_PORTRAIT),
            common.switch_row("Voice cues", "Distance, time, pace and steps, halfway, goal, "
                              "water and pacing nudges", s.voice_cues, cues,
                              icon=ft.Icons.RECORD_VOICE_OVER),
            common.segmented([(k, CUE_LABELS[k]) for k in CUE_EVERY], s.cue_every,
                             on_change=every),
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
        self.l_dist = ft.Text("0.00", size=56, **big)
        self.l_steps = ft.Text("0", size=56, **big)  # basic tracking: steps + time
        self.l_btime = ft.Text("0:00", size=Type.HEADLINE + 4, **big)
        self.l_time = ft.Text("0:00", size=Type.HEADLINE + 4, **big)
        self.l_pace = ft.Text("-:--", size=Type.HEADLINE + 4, **big)
        self.l_avg = ft.Text("-:--", size=Type.HEADLINE + 4, **big)
        self.l_status = ft.Text("", size=Type.CAPTION, color=C.TEXT_DIM)
        self.l_dot = ft.Container(width=10, height=10, border_radius=5, bgcolor=C.TEXT_DIM)
        self.l_goal = ft.ProgressBar(value=0, color=ROUTE_COLOR, bgcolor=C.a(C.TEXT, 0.1),
                                     height=8, border_radius=4)
        self.l_goal_txt = common.hint("")
        self.l_banner = ft.Container(
            ft.Text("AUTO-PAUSED", size=Type.CAPTION, weight=ft.FontWeight.BOLD,
                    color=C.BG), bgcolor="#F5C66B", border_radius=Radius.PILL,
            padding=ft.Padding.symmetric(horizontal=10, vertical=3), visible=False)
        self.b_pause = ft.Container(
            ft.Icon(ft.Icons.PAUSE, size=36, color=C.ON_PRIMARY), width=76, height=76,
            border_radius=38, bgcolor=C.PRIMARY, alignment=ft.Alignment.CENTER,
            on_click=self._toggle_pause, tooltip="Pause", scale=1,
            animate_scale=th.Motion.anim(th.Motion.POP_MS, th.Motion.BACK))
        self.b_finish = ft.Container(
            ft.Icon(ft.Icons.STOP, size=34, color="#FFFFFF"), width=76, height=76,
            border_radius=38, bgcolor="#E5484D", alignment=ft.Alignment.CENTER,
            on_click=self._finish_tap, tooltip="Finish", scale=1,
            animate_scale=th.Motion.anim(th.Motion.POP_MS, th.Motion.BACK))
        self.map_host = ft.Container(height=250, border_radius=Radius.MD,
                                     clip_behavior=ft.ClipBehavior.ANTI_ALIAS)

        def stat(ctrl: ft.Control, label: str) -> ft.Control:
            return ft.Column([ctrl, common.hint(label)], spacing=0, tight=True, expand=True,
                             horizontal_alignment=ft.CrossAxisAlignment.CENTER)

        self.map_wrap = ft.Container(self.map_host,
                                     padding=ft.Padding.symmetric(horizontal=Space.GUTTER))
        self.full_stats = ft.Column([
            ft.Row([self.l_dist, ft.Text("km", size=Type.TITLE, color=C.TEXT_DIM)],
                   spacing=Space.SM, alignment=ft.MainAxisAlignment.CENTER,
                   vertical_alignment=ft.CrossAxisAlignment.END),
            ft.Row([stat(self.l_time, "moving time"), stat(self.l_pace, "pace /km"),
                    stat(self.l_avg, "avg /km")]),
        ], spacing=Space.SM, tight=True)
        self.basic_stats = ft.Column([
            ft.Row([self.l_steps, ft.Text("steps (est.)", size=Type.TITLE,
                                          color=C.TEXT_DIM)],
                   spacing=Space.SM, alignment=ft.MainAxisAlignment.CENTER,
                   vertical_alignment=ft.CrossAxisAlignment.END),
            ft.Row([stat(self.l_btime, "moving time")]),
            common.card(ft.Row([
                ft.Icon(ft.Icons.LOCK_OPEN, size=18, color="#F5C66B"),
                ft.Text("Basic tracking: steps and time. Unlock full tracking: watch the "
                        f"stretch ad next run or go {premium.PREMIUM_NAME}.",
                        size=Type.CAPTION, color=C.TEXT_DIM, expand=True)],
                spacing=Space.SM), padding=Space.SM),
        ], spacing=Space.SM, tight=True, visible=False)
        self.adventure_card = AdventureRunCard(
            self.adventure_engine,
            on_play_sound=self._play_adventure_sound,
        )
        self.adventure_wrap = ft.Container(
            self.adventure_card,
            padding=ft.Padding.symmetric(horizontal=Space.GUTTER),
        )
        self.live_view = ft.Column([
            self.map_wrap,
            self.adventure_wrap,
            ft.Container(ft.Column([
                ft.Row([self.l_dot, self.l_status, ft.Container(expand=True), self.l_banner],
                       spacing=Space.SM),
                self.full_stats, self.basic_stats,
                self.l_goal, self.l_goal_txt,
            ], spacing=Space.SM, tight=True),
                padding=ft.Padding.symmetric(horizontal=Space.GUTTER)),
            ft.Container(ft.Row([self.b_pause, self.b_finish], spacing=Space.XXL,
                                alignment=ft.MainAxisAlignment.CENTER),
                         padding=ft.Padding.only(top=Space.SM, bottom=96)),
        ], spacing=Space.MD, expand=True, scroll=ft.ScrollMode.AUTO)

    def _make_map(self, center: tuple[float, float], route: list, *, live: bool,
                  height: int) -> tuple[Any, Any, Any]:
        """(map, polyline layer, marker layer). Returns (None, ...) if flet_map is missing."""
        try:
            import flet_map as fm
        except ImportError:
            return None, None, None
        poly = fm.PolylineLayer(polylines=[
            fm.PolylineMarker(coordinates=[fm.MapLatitudeLongitude(*p) for p in seg],
                              color=ROUTE_COLOR, stroke_width=5, border_color=C.a("#000000",
                                                                                  0.35),
                              border_stroke_width=1.5)
            for seg in route if seg] or [fm.PolylineMarker(coordinates=[], stroke_width=5,
                                                           color=ROUTE_COLOR)])
        markers = fm.MarkerLayer(markers=[])
        pts = [p for seg in route for p in seg]
        fit = (fm.CameraFit(coordinates=[fm.MapLatitudeLongitude(*p) for p in pts],
                            padding=ft.Padding.all(36), max_zoom=17)
               if not live and len(pts) > 1 else None)
        flags = (fm.InteractionFlag.PINCH_ZOOM | fm.InteractionFlag.DOUBLE_TAP_ZOOM
                 | fm.InteractionFlag.SCROLL_WHEEL_ZOOM) if live else fm.InteractionFlag.ALL
        m = fm.Map(
            layers=[
                fm.TileLayer(url_template=OSM_URL, user_agent_package_name=TILE_UA),
                poly, markers,
                fm.SimpleAttribution(text=OSM_ATTRIBUTION,
                                     text_style=ft.TextStyle(size=10, color="#222222"),
                                     bgcolor=C.a("#FFFFFF", 0.8),
                                     alignment=ft.Alignment.BOTTOM_RIGHT),
            ],
            initial_center=fm.MapLatitudeLongitude(*center), initial_zoom=16,
            initial_camera_fit=fit, height=height, keep_alive=True, bgcolor="#1B1F2A",
            interaction_configuration=fm.InteractionConfiguration(flags=flags),
        )
        return m, poly, markers

    def _paint_live(self) -> None:
        tr = self.tracker
        if tr is None:
            return
        now = self.gps.now()
        basic = self.tracking == "basic"
        self.map_wrap.visible = self.full_stats.visible = not basic
        if hasattr(self, "adventure_wrap"):
            self.adventure_wrap.visible = not basic
        self.basic_stats.visible = basic
        if basic:
            self.l_steps.value = f"{self._steps_now():,}"
            self.l_btime.value = rcore.fmt_duration(tr.moving_s)
        self.l_dist.value = km(tr.distance_m)
        self.l_time.value = rcore.fmt_duration(tr.moving_s)
        self.l_pace.value = rcore.fmt_pace(tr.current_pace(now))
        self.l_avg.value = rcore.fmt_pace(rcore.pace_s_per_km(tr.distance_m, tr.moving_s))
        acc = self.acc
        self.l_dot.bgcolor = _acc_color(acc)
        state = ("Paused" if tr.paused else "Waiting for GPS…" if not tr.points
                 else f"GPS ±{acc:.0f} m" if acc is not None else "GPS")
        self.l_status.value = (f"{state} · {rcore.fmt_duration(tr.elapsed_s(now))} total"
                               if tr.points else state)
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

    def _update_map(self, now: float) -> None:
        tr = self.tracker
        if tr is None or self.live_map is None or not getattr(self.live_map, "page", None):
            return
        import flet_map as fm

        segs = tr.route()
        total = sum(len(s) for s in segs)
        step = max(1, math.ceil(total / LIVE_MAP_POINTS))
        lines = []
        for seg in segs:
            pts = seg[::step] + ([seg[-1]] if (len(seg) - 1) % step else [])
            lines.append(fm.PolylineMarker(
                coordinates=[fm.MapLatitudeLongitude(*p) for p in pts], color=ROUTE_COLOR,
                stroke_width=5, border_color=C.a("#000000", 0.35), border_stroke_width=1.5))
        self.live_poly.polylines = lines or self.live_poly.polylines
        here = self.pos or (segs[-1][-1] if segs and segs[-1] else None)
        marks = []
        if segs and segs[0]:
            marks.append(fm.Marker(content=_dot("#5EEAB0", 14),
                                   coordinates=fm.MapLatitudeLongitude(*segs[0][0]),
                                   width=14, height=14))
        if here:
            marks.append(fm.Marker(content=_dot("#4FA3FF", 20),
                                   coordinates=fm.MapLatitudeLongitude(*here),
                                   width=20, height=20))
        self.live_marks.markers = marks
        ui.refresh(self.live_map)
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
        self._adv_state = {"dist": 0.0, "t": now, "last_step": now}
        self.started = datetime.now().strftime("%H:%M")
        self.phase = "live"
        self.gen += 1
        center = self.pos or MANILA
        self._build_live()  # fresh controls each session (see render)
        self.live_map, self.live_poly, self.live_marks = self._make_map(
            center, [], live=True, height=250)
        self.map_host.content = self.live_map or ft.Container(
            common.hint("Map unavailable"), alignment=ft.Alignment.CENTER)
        self.gps.start(self._on_fix, s.mode)
        sfx.play("objective_new")
        self._refresh()  # show the live screen first: the calls below may answer slowly
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
            if now - self._adv_state.get("last_step", 0.0) >= TICK_S * 0.5:
                self._step_live(now)

    def _step_live(self, now: float) -> None:
        """Advance live stats, map, Adventure Run combat and voice cues. Called by both the 1s
        timer loop and incoming GPS fixes so background / screen-off runs never stall."""
        if self.phase != "live" or self.tracker is None:
            return
        self._adv_state["last_step"] = now
        self._paint_live()
        wall = time.monotonic()
        n = len(self.tracker.points)
        if wall - self._last_map >= MAP_EVERY_S and n != self._map_points:
            self._last_map, self._map_points = wall, n
            self._update_map(now)  # the polyline is the heavy part: every 2 s at most
        with contextlib.suppress(Exception):  # the adventure must never break a run
            self._adventure_tick(now, self._adv_state)
        if getattr(self.live_view, "page", None):
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
        raw_delta = min(ADV_MAX_BG_GAP_S, max(0.0, now - adv["t"]))
        total_dist_inc = max(0.0, tr.distance_m - adv["dist"])
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
        if coins_granted_total > 0:
            self.app.save()
            with contextlib.suppress(Exception):
                self.app.page.run_task(self.app.coins_changed)
        if card is not None:
            card.process_tick_events(all_events)
            card.refresh_display(current_speed_kmh=speed_kmh)

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

