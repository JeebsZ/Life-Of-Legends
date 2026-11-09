"""More -> Workout: quick log (type, minutes, effort, notes, linked quest or Path), a strength
session builder (exercises with sets of reps x weight in kg or lb; add / remove / reorder),
routines (save / use), copy a past session as a draft, history with type filters, exercise
detail with personal records (descriptive only) and a rest timer.

Rules (XP per minutes and effort, daily caps, drafts) live in Game.log_workout & co."""

from __future__ import annotations

import asyncio
import time
from datetime import date
from typing import TYPE_CHECKING, Any

import flet as ft

from lol.core import exercise_catalog as ec
from lol.core.game import REST_TIMER_PRESETS
from lol.core.models import ExerciseEntry, SetEntry, WorkoutSession
from lol.core.workout_engine import (
    FORGE_RECIPES,
    GUARDIAN_TEMPLATES,
    REST_SAGE_LINES,
    spawn_guardian_for_target_volume,
)
from lol.ui import avatars, sfx
from lol.ui import components as ui
from lol.ui import theme as th
from lol.ui.screens import common
from lol.ui.theme import C, Motion, Radius, Size, Space, Type

if TYPE_CHECKING:
    from lol.ui.app import App

TYPES = {
    "strength": ("Strength", ft.Icons.FITNESS_CENTER),
    "cardio": ("Cardio", ft.Icons.DIRECTIONS_RUN),
    "mobility": ("Mobility", ft.Icons.SELF_IMPROVEMENT),
    "sport": ("Sport", ft.Icons.SPORTS_BASKETBALL),
    "other": ("Other", ft.Icons.BOLT),
}
EFFORT_WORDS = {1: "very easy", 3: "easy", 5: "moderate", 7: "hard", 9: "very hard",
                10: "all out"}
# Luma's short staged analysis the first time an exercise's records open (per visit)
RECORD_STAGES = ("READING YOUR SETS…", "RECORDS FOUND")
PR_LABELS = {"max_weight": "Heaviest set", "max_reps": "Most reps in a set",
             "best_volume": "Best session volume", "longest_distance": "Longest distance",
             "longest_time": "Longest set"}


def effort_word(v: int) -> str:
    return EFFORT_WORDS.get(v) or EFFORT_WORDS[max(k for k in EFFORT_WORDS if k <= v)]


def type_options() -> list[tuple[str, str, ft.IconData | None, str]]:
    return [(k, lbl, icon, C.PRIMARY) for k, (lbl, icon) in TYPES.items()]


def _num(text: str | None, kind: type = float) -> Any:
    t = (text or "").replace(",", ".").strip()
    if not t:
        return None
    try:
        v = kind(float(t))
    except ValueError:
        return None
    return v if v >= 0 else None


def set_text(st: SetEntry) -> str:
    bits = []
    if st.reps is not None:
        bits.append(f"{st.reps}")
    if st.weight is not None:
        bits.append(f"{st.weight:g} {st.unit}")
    if st.distance_km is not None:
        bits.append(f"{st.distance_km:g} km")
    if st.seconds is not None:
        bits.append(f"{st.seconds}s")
    return " × ".join(bits) or "-"


class WorkoutScreen:
    title = "Workout"

    def __init__(self, app: App) -> None:
        self.app = app
        self.filter = "all"
        self._scanned: set[str] = set()  # exercises whose records Luma scanned this visit
        self.list = common.screen_list()
        self.view = ft.Container(self.list, expand=True, key="workout")
        self.fab = ft.FloatingActionButton(icon=ft.Icons.ADD, on_click=self.open_quick,
                                           bgcolor=C.PRIMARY, foreground_color=C.ON_PRIMARY,
                                           tooltip="Log a workout")
        # rest timer (lives across renders; the loop runs only while it's counting)
        self.rest_end = 0.0
        self.rest_total = 0
        self.rest_gen = 0
        self.rest_text = ft.Text("Rest timer", size=Type.TITLE, weight=ft.FontWeight.W_800,
                                 color=C.TEXT)
        self.rest_bar = ft.ProgressBar(value=0, color=C.PRIMARY, bgcolor=C.a(C.TEXT, 0.1),
                                       height=6, border_radius=3)

    def _refresh(self) -> None:
        self.render()
        ui.refresh(self.list)

    def restyle(self) -> None:
        self._refresh()

    def on_leave(self) -> None:
        pass  # the rest timer keeps counting by timestamp; its loop parks when unmounted

    def on_enter(self) -> None:
        self._scanned.clear()

    # ------------------------------------------------------------------ render
    def render(self) -> None:
        g, today = self.app.game, self.app.today()
        stats = g.workout_stats(today)

        def stat(value: str, label: str) -> ft.Control:
            return ft.Column([ft.Text(value, size=Type.TITLE, weight=ft.FontWeight.W_800,
                                      color=C.TEXT), common.hint(label)],
                             spacing=0, tight=True, expand=True,
                             horizontal_alignment=ft.CrossAxisAlignment.CENTER)

        items: list[ft.Control] = [
            common.card(ft.Column([
                ft.Row([stat(str(stats["sessions"]), "sessions today"),
                        stat(f"{stats['minutes']}", "minutes"),
                        stat(f"{g.data.star_iron:,}", "Star-Iron Ore")]),
                ft.Row([common.primary_button("Start workout", lambda e: self.open_builder(None),
                                              icon=ft.Icons.FITNESS_CENTER),
                        common.secondary_button("Quick log", self.open_quick,
                                                icon=ft.Icons.BOLT)],
                       spacing=Space.SM),
                ft.Row([
                    common.secondary_button("Star-Iron Forge", self._open_forge,
                                            icon=ft.Icons.HARDWARE),
                ]),
            ], spacing=Space.MD, tight=True)),
            self._rest_card(),
        ]
        routines = g.workout_templates()
        items.append(common.section("Routines"))
        if not routines:
            items.append(common.hint("  Save a session as a routine to reuse it in one tap."))
        for t in routines:
            items.append(common.card(ft.Row([
                ft.Icon(TYPES.get(t.type, TYPES["other"])[1], color=C.PRIMARY, size=22),
                ft.Column([ft.Text(t.name, size=Type.BODY, weight=ft.FontWeight.W_600,
                                   color=C.TEXT),
                           common.hint(f"{len(t.exercises)} exercise"
                                       f"{'s' if len(t.exercises) != 1 else ''}"
                                       + (f" · {t.minutes} min" if t.minutes else ""))],
                          spacing=0, expand=True, tight=True),
                ft.TextButton("Use", icon=ft.Icons.PLAY_ARROW, height=Size.TAP,
                              on_click=lambda e, tid=t.id: self._use_routine(tid)),
                common.menu_button([("Delete routine", ft.Icons.DELETE_OUTLINE,
                                     lambda tid=t.id: self._delete_routine(tid), True)]),
            ], spacing=Space.SM, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                padding=ft.Padding.only(left=Space.MD, top=Space.XS, bottom=Space.XS)))

        names = g.exercise_names()
        if names:
            items.append(common.section("Exercises & records"))
            items.append(ft.Row([
                ft.OutlinedButton(n, height=40,
                                  on_click=lambda e, n=n: self.app.page.run_task(
                                      self._exercise, n))
                for n in names], wrap=True, spacing=Space.XS, run_spacing=Space.XS))

        items.append(common.section("History"))
        items.append(common.ChoicePills(
            [("all", "All", ft.Icons.APPS, C.PRIMARY), *type_options()], self.filter,
            on_change=self._set_filter, grid_cols=0))
        sessions = g.workouts(type=None if self.filter == "all" else self.filter)[:40]
        if not sessions:
            items.append(common.empty_card("No workouts yet",
                                           "Any movement counts. Log one in a tap.",
                                           ft.Icons.FITNESS_CENTER))
        items += [self._session_row(w) for w in sessions]
        self.list.controls = items

    def _set_filter(self, v: str) -> None:
        self.filter = v
        self._refresh()

    def _session_row(self, w: WorkoutSession) -> ft.Control:
        label, icon = TYPES.get(w.type, TYPES["other"])
        d = date.fromisoformat(w.day)
        sub = [f"{w.minutes} min" if w.minutes else "no time logged",
               f"effort {w.effort}/10"]
        if w.exercises:
            sub.append(f"{len(w.exercises)} exercise{'s' if len(w.exercises) != 1 else ''}")
        detail = [common.hint(" · ".join(sub))]
        for ex in w.exercises[:4]:
            detail.append(ft.Text(f"{ex.name}: " + (", ".join(set_text(s) for s in ex.sets)
                                                    or "no sets"),
                                  size=Type.CAPTION, color=C.TEXT_DIM, max_lines=1,
                                  overflow=ft.TextOverflow.ELLIPSIS))
        if w.notes:
            detail.append(common.hint(w.notes))
        pc = th.path_color(w.path_id)
        return common.card(ft.Row([
            ui.path_avatar(icon, pc, 38),
            ft.Column([ft.Text(f"{label} · {d:%a} {common.short_date(d)}", size=Type.BODY,
                               weight=ft.FontWeight.W_600, color=C.TEXT), *detail],
                      spacing=1, expand=True, tight=True),
            common.menu_button([
                ("Copy as new", ft.Icons.CONTENT_COPY, lambda sid=w.id: self._copy(sid)),
                ("Save as routine", ft.Icons.BOOKMARK_ADD, lambda sid=w.id: self._to_routine(sid)),
                ("Delete", ft.Icons.DELETE_OUTLINE, lambda sid=w.id: self._delete(sid), True),
            ], tooltip="Session options"),
        ], spacing=Space.MD, vertical_alignment=ft.CrossAxisAlignment.START),
            padding=ft.Padding.only(left=Space.MD, top=Space.SM, bottom=Space.SM),
            tint=pc)

    # ------------------------------------------------------------------ rest timer
    def _rest_card(self) -> ft.Control:
        btns = [ft.OutlinedButton(f"{s // 60}:{s % 60:02d}", height=40,
                                  on_click=lambda e, s=s: self._rest_start(s))
                for s in REST_TIMER_PRESETS]
        stop = ft.IconButton(ft.Icons.STOP, icon_color=C.TEXT_DIM, tooltip="Stop rest",
                             width=40, height=40, on_click=lambda e: self._rest_stop())
        return common.card(ft.Column([
            ft.Row([ft.Icon(ft.Icons.HOURGLASS_BOTTOM, color=C.PRIMARY), self.rest_text,
                    ft.Container(expand=True), stop],
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
            self.rest_bar,
            ft.Row(btns, spacing=Space.XS, wrap=True),
        ], spacing=Space.SM, tight=True), padding=Space.MD)

    def _rest_start(self, seconds: int) -> None:
        sfx.play("tap")
        self.rest_total = seconds
        self.rest_end = time.time() + seconds
        self.rest_gen += 1
        self.app.page.run_task(self._rest_loop, self.rest_gen)

    def _rest_stop(self) -> None:
        sfx.play("tap")
        self.rest_gen += 1
        self.rest_end = 0
        self.rest_text.value, self.rest_bar.value = "Rest timer", 0
        ui.refresh(self.rest_text, self.rest_bar)

    async def _rest_loop(self, gen: int) -> None:
        while gen == self.rest_gen:
            left = self.rest_end - time.time()
            if left <= 0:
                self.rest_text.value, self.rest_bar.value = "Rest done - next set!", 1
                ui.refresh(self.rest_text, self.rest_bar)
                sfx.play("timer_done", 0.8)
                await ui.buzz("heavy")
                return
            s = int(left + 0.99)
            self.rest_text.value = f"Rest {s // 60}:{s % 60:02d}"
            self.rest_bar.value = 1 - left / max(1, self.rest_total)
            ui.refresh(self.rest_text, self.rest_bar)
            await asyncio.sleep(0.5)

    # ------------------------------------------------------------------ link picker
    def _link_dropdown(self, st: dict) -> ft.Dropdown:
        g, today = self.app.game, self.app.today()
        opts = [ft.DropdownOption(key="none", text="Warrior Path (default)")]
        opts += [ft.DropdownOption(key=f"p:{pid}", text=f"Path · {th.path_name(pid)}")
                 for pid in th.PATH_IDS if pid != "warrior"]
        opts += [ft.DropdownOption(key=f"q:{q.id}", text=f"Quest · {q.title}")
                 for q in g.quests if not g.is_done(q, today)]

        def picked(e: Any) -> None:
            sfx.play("tap")
            st["link"] = e.control.value or "none"

        return ft.Dropdown(label="XP goes to", value=st.get("link", "none"), options=opts,
                           on_select=picked, expand=True, filled=True, menu_height=360,
                           border_radius=Radius.SM, fill_color=C.SURFACE_HI)

    @staticmethod
    def _link_args(st: dict) -> tuple[str | None, str | None]:
        link = st.get("link", "none")
        return (link[2:] if link.startswith("q:") else None,
                link[2:] if link.startswith("p:") else None)

    def _effort_row(self, st: dict) -> ft.Control:
        label = ft.Text(f"Effort {st['effort']}/10 · {effort_word(st['effort'])}",
                        size=Type.LABEL, color=C.TEXT)

        def slide(e: Any) -> None:
            st["effort"] = round(float(e.control.value))
            label.value = f"Effort {st['effort']}/10 · {effort_word(st['effort'])}"
            ui.refresh(label)

        return ft.Column([label, ft.Slider(min=1, max=10, divisions=9, value=st["effort"],
                                           active_color=C.PRIMARY,
                                           inactive_color=C.a(C.TEXT, 0.12),
                                           on_change=slide)], spacing=0, tight=True)

    async def _log(self, mutate: Any, title: str) -> None:
        app = self.app

        def line(c: Any) -> str:
            return (f"Notice: Workout logged: {title}. +{c.xp} XP to "
                    f"{th.path_name(c.path_id)} Path.")

        try:
            c = await app.award(mutate, line=line)
        except ValueError as exc:
            app.error(f"Couldn't log it: {exc}")
            return
        if not (c.xp or c.coins):
            sfx.play("tap")
            app.toast("Logged. Today's workout XP cap is reached - rest counts too.",
                      ft.Icons.FITNESS_CENTER)
        self._refresh()

    # ------------------------------------------------------------------ quick log
    def open_quick(self, _: Any = None) -> None:
        app, g = self.app, self.app.game
        st: dict[str, Any] = {"type": "cardio", "minutes": 30, "effort": 5, "link": "none"}
        notes = common.text_field("Notes (optional)")
        minutes = common.stepper(st["minutes"], lambda v: st.update(minutes=v), lo=0, hi=300,
                                 step=5, suffix=" min", width=72)

        def log(_: Any = None) -> None:
            qid, pid = self._link_args(st)
            common.close(sheet)
            label = TYPES[st["type"]][0]
            app.page.run_task(self._log, lambda: g.log_workout(
                st["minutes"], app.today(), st["type"], st["effort"],
                (notes.value or "").strip(), qid, pid), f"{label}, {st['minutes']} min")

        sheet = common.open_sheet(app.page, "Quick log", [
            common.ChoicePills(type_options(), st["type"],
                               on_change=lambda v: st.update(type=v)),
            ft.Row([ft.Icon(ft.Icons.TIMER, color=C.TEXT_DIM, size=20),
                    ft.Text("Minutes", color=C.TEXT_DIM, expand=True), minutes],
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
            self._effort_row(st),
            ft.Row([self._link_dropdown(st)]),
            notes,
            common.hint("XP grows with minutes and effort, up to a daily cap. A linked quest "
                        "isn't completed - tick it yourself when it's done."),
            ft.Row([common.primary_button("Log workout", log, icon=ft.Icons.CHECK)]),
        ])

    # ------------------------------------------------------------------ session builder
    def _open_exercise_picker(self, on_select: Any) -> None:
        """Hevy-style exercise catalog with muscle filters, search, and (i) tutorials."""
        app = self.app
        search_field = common.text_field("Search exercises (e.g. Bench, Squat)")
        active_muscle = ["All"]
        active_equip = ["All"]
        results_col = ft.Column(spacing=Space.XS, tight=True, scroll=ft.ScrollMode.ADAPTIVE)

        muscles = ["All", "Chest", "Back", "Legs", "Shoulders", "Arms", "Core"]

        def show_tutorial(ex: ec.Exercise) -> None:
            tut_items: list[ft.Control] = [
                ft.Row([
                    ft.Icon(ft.Icons.FITNESS_CENTER, color=C.PRIMARY, size=24),
                    ft.Column([
                        ft.Text(ex.name, size=Type.TITLE, weight=ft.FontWeight.W_900, color=C.TEXT),
                        common.hint(f"Muscle: {ex.muscle} · Equipment: {ex.equipment}"),
                    ], spacing=2, expand=True, tight=True),
                ], spacing=Space.SM),
                ft.Divider(height=1, color=C.OUTLINE),
                ft.Text("Step-by-Step Instructions", size=Type.BODY, weight=ft.FontWeight.BOLD, color=C.PRIMARY),
            ]
            for step_idx, step_txt in enumerate(ex.instructions, 1):
                tut_items.append(
                    ft.Row([
                        ft.Container(
                            ft.Text(str(step_idx), size=11, weight=ft.FontWeight.BOLD, color=C.ON_PRIMARY),
                            width=22, height=22, border_radius=11, bgcolor=C.PRIMARY,
                            alignment=ft.Alignment.CENTER,
                        ),
                        ft.Text(step_txt, size=Type.BODY, color=C.TEXT, expand=True),
                    ], spacing=Space.SM, vertical_alignment=ft.CrossAxisAlignment.START)
                )
            if ex.secondary_muscles:
                tut_items.append(
                    common.hint(f"Secondary muscles: {', '.join(ex.secondary_muscles)}")
                )
            common.open_sheet(app.page, "Exercise Guide", tut_items)

        def refresh_list() -> None:
            m = active_muscle[0] if active_muscle[0] != "All" else None
            eq = active_equip[0] if active_equip[0] != "All" else None
            q = (search_field.value or "").strip()
            items = ec.filter_exercises(muscle=m, equipment=eq, query=q)
            rows: list[ft.Control] = []
            if not items:
                rows.append(ft.Container(common.hint("No matching exercises found"), alignment=ft.Alignment.CENTER))
            for ex in items:
                def pick(_: Any, name=ex.name) -> None:
                    common.close(sheet)
                    on_select(name)

                rows.append(
                    common.card(
                        ft.Row([
                            ft.Icon(ft.Icons.FITNESS_CENTER, color=C.PRIMARY, size=22),
                            ft.Column([
                                ft.Text(ex.name, size=Type.BODY, weight=ft.FontWeight.W_700, color=C.TEXT),
                                common.hint(f"{ex.muscle} · {ex.equipment}"),
                            ], spacing=0, expand=True, tight=True),
                            ft.IconButton(
                                ft.Icons.INFO_OUTLINE,
                                icon_color=C.PRIMARY,
                                tooltip="How to do this exercise",
                                on_click=lambda e, ex=ex: show_tutorial(ex),
                            ),
                            ft.IconButton(
                                ft.Icons.ADD_CIRCLE_OUTLINE,
                                icon_color=C.ACCENT,
                                tooltip="Add to workout",
                                on_click=pick,
                            ),
                        ], spacing=Space.SM, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        padding=ft.Padding.symmetric(horizontal=Space.MD, vertical=Space.XS),
                    )
                )
            results_col.controls = rows
            ui.refresh(results_col)

        search_field.on_change = lambda e: refresh_list()

        muscle_pills = ft.Row([
            ft.Container(
                ft.Text(m, size=Type.CAPTION, weight=ft.FontWeight.BOLD,
                        color=C.ON_PRIMARY if m == active_muscle[0] else C.TEXT),
                bgcolor=C.PRIMARY if m == active_muscle[0] else C.SURFACE_HI,
                border_radius=Radius.PILL,
                padding=ft.Padding.symmetric(horizontal=10, vertical=5),
                on_click=lambda e, m=m: set_muscle(m),
                ink=True,
            )
            for m in muscles
        ], scroll=ft.ScrollMode.ADAPTIVE, spacing=Space.XS)

        def set_muscle(m: str) -> None:
            sfx.play("toggle")
            active_muscle[0] = m
            for pill, target_m in zip(muscle_pills.controls, muscles):
                active = target_m == m
                pill.bgcolor = C.PRIMARY if active else C.SURFACE_HI
                pill.content.color = C.ON_PRIMARY if active else C.TEXT
            ui.refresh(muscle_pills)
            refresh_list()

        refresh_list()
        sheet = common.open_sheet(app.page, "Select Exercise", [
            search_field,
            muscle_pills,
            ft.Container(results_col, height=360),
        ])

    def _open_forge(self, _: Any = None) -> None:
        """Tempest Star-Iron Forge: spend lifted volume ore to forge relics, coins & traits."""
        app, g = self.app, self.app.game
        ore_text = ft.Text(
            f"⛏️ {g.data.star_iron:,} Star-Iron Ore",
            size=Type.TITLE,
            weight=ft.FontWeight.W_900,
            color="#4FE3F0",
        )
        recipe_col = ft.Column(spacing=Space.SM, tight=True)

        def paint_recipes() -> None:
            ore_text.value = f"⛏️ {g.data.star_iron:,} Star-Iron Ore"
            cards: list[ft.Control] = []
            for r in FORGE_RECIPES:
                forged = r.trait_id in g.data.unlocked_workout_traits
                can_afford = g.data.star_iron >= r.cost_ore and not forged

                def craft(_: Any, rec=r) -> None:
                    if g.data.star_iron < rec.cost_ore or rec.trait_id in g.data.unlocked_workout_traits:
                        sfx.play("error_soft")
                        return
                    g.data.star_iron -= rec.cost_ore
                    g.data.unlocked_workout_traits.append(rec.trait_id)
                    g.profile.coins += rec.reward_coins
                    g.profile.xp += rec.reward_xp
                    app.save()
                    sfx.play("skill_acquired", 0.85)
                    app.juice(rec.color, strength=1.0)
                    if app.page:
                        app.page.run_task(app.coins_changed)
                        app.page.run_task(app.reveal, rec.name, f"{rec.trait_id} Forged! +{rec.reward_coins} Coins")
                    paint_recipes()
                    ui.refresh(ore_text, recipe_col)
                    self._refresh()

                btn_label = "Forged ✓" if forged else f"Forge ({r.cost_ore:,} Ore)"
                btn = ft.Container(
                    ft.Text(
                        btn_label,
                        size=Type.CAPTION,
                        weight=ft.FontWeight.W_800,
                        color=C.SUCCESS if forged else (C.ON_PRIMARY if can_afford else C.TEXT_DIM),
                    ),
                    bgcolor=C.a(C.SUCCESS, 0.16) if forged else (r.color if can_afford else C.SURFACE_HI),
                    border_radius=Radius.PILL,
                    padding=ft.Padding.symmetric(horizontal=12, vertical=6),
                    on_click=craft if can_afford else None,
                    ink=can_afford,
                )
                cards.append(
                    common.card(
                        ft.Row(
                            [
                                ft.Container(
                                    ft.Icon(ft.Icons.SHIELD_MOON, color=r.color, size=24),
                                    width=44,
                                    height=44,
                                    border_radius=22,
                                    bgcolor=C.a(r.color, 0.16),
                                    alignment=ft.Alignment.CENTER,
                                ),
                                ft.Column(
                                    [
                                        ft.Text(r.name, size=Type.BODY, weight=ft.FontWeight.W_800, color=C.TEXT),
                                        ft.Text(r.desc, size=Type.CAPTION, color=C.TEXT_DIM),
                                    ],
                                    spacing=2,
                                    expand=True,
                                    tight=True,
                                ),
                                btn,
                            ],
                            spacing=Space.SM,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        padding=Space.SM,
                    )
                )
            recipe_col.controls = cards

        paint_recipes()
        common.open_sheet(
            app.page,
            "Star-Iron Forge",
            [
                common.card(
                    ft.Column(
                        [
                            ore_text,
                            common.hint("1 kg lifted = 1 Ore. Craft relics for permanent traits & coins."),
                        ],
                        spacing=4,
                        tight=True,
                    ),
                    padding=Space.MD,
                ),
                recipe_col,
            ],
        )

    def open_builder(self, draft: WorkoutSession | None, *, heading: str = "Labyrinth Raid Session"
                     ) -> None:
        """Interactive Labyrinth Boss Raid + Exercise/Set Logger with Strike buttons & Rest Recovery."""
        app, g = self.app, self.app.game
        unit = "kg"
        if draft and draft.exercises and draft.exercises[0].sets:
            unit = draft.exercises[0].sets[0].unit
        st: dict[str, Any] = {
            "type": draft.type if draft else "strength",
            "minutes": draft.minutes if draft else 45,
            "effort": draft.effort if draft else 6,
            "link": f"p:{draft.path_id}" if draft and draft.path_id != "warrior" else "none",
            "unit": unit,
            "rest_preset": 60,
            "boss_idx": 0,
            # editable copy: [{"name": str, "sets": [[reps, weight, done], ...]}]
            "ex": [
                {
                    "name": ex.name,
                    "sets": [[s.reps or 10, s.weight or 20.0, False] for s in ex.sets]
                    or [[10, 20.0, False]],
                }
                for ex in (draft.exercises if draft else [])
            ],
        }
        if not st["ex"]:
            st["ex"] = [{"name": "Bench Press (Barbell)", "sets": [[10, 40.0, False], [10, 40.0, False], [10, 40.0, False]]}]
        ex_col = ft.Column(spacing=Space.SM, tight=True)
        notes = common.text_field("Notes (optional)")
        notes.value = draft.notes if draft else ""
        routine_name = common.text_field("Routine name (to save as a routine)")

        # --- Interactive Labyrinth Combat Arena ---
        target_vol = sum((s[0] or 10) * (s[1] or 20) for ex in st["ex"] for s in ex["sets"])
        guardian = spawn_guardian_for_target_volume(max(1500, target_vol), index=st["boss_idx"])

        player_avatar = avatars.bubble(
            g.profile.avatar_id,
            56,
            custom=g.profile.avatar_customization,
            frame_id=g.profile.frame_id,
            pet_id=g.profile.pet_id,
        )
        player_box = ft.Container(
            player_avatar,
            offset=ft.Offset(0, 0),
            scale=1.0,
            animate_offset=Motion.anim(180, Motion.BACK),
            animate_scale=Motion.anim(180, Motion.BACK),
        )
        boss_img = ft.Image(
            src=guardian.sprite,
            width=68,
            height=68,
            fit=ft.BoxFit.CONTAIN,
            filter_quality=ft.FilterQuality.NONE,
        )
        boss_sprite_box = ft.Container(
            boss_img,
            width=72,
            height=72,
            alignment=ft.Alignment.CENTER,
            scale=1.0,
            offset=ft.Offset(0, 0),
            animate_scale=Motion.anim(180, Motion.BACK),
            animate_offset=Motion.anim(140, Motion.EASE_CUBIC),
        )
        dmg_popup_text = ft.Text(
            "",
            size=16,
            weight=ft.FontWeight.W_900,
            color="#FFD36E",
        )
        dmg_popup = ft.Container(
            dmg_popup_text,
            bgcolor=C.a("#000000", 0.78),
            border=ft.Border.all(1.5, "#FFD36E"),
            border_radius=Radius.PILL,
            padding=ft.Padding.symmetric(horizontal=10, vertical=3),
            opacity=0,
            offset=ft.Offset(0, 0),
            animate_opacity=Motion.anim(220),
            animate_offset=Motion.anim(320, Motion.EASE_CUBIC),
        )
        boss_name_text = ft.Text(
            f"⚔️ {guardian.name}",
            size=Type.BODY + 1,
            weight=ft.FontWeight.W_900,
            color="#FFFFFF",
        )
        boss_aff_text = ft.Text(
            f"{guardian.affinity} · {guardian.title}",
            size=10,
            weight=ft.FontWeight.BOLD,
            color="#4FE3F0",
        )
        boss_hp_bar = ft.ProgressBar(
            value=1.0,
            color="#FF4D6D",
            bgcolor=C.a("#FFFFFF", 0.14),
            height=10,
            border_radius=5,
        )
        boss_hp_text = ft.Text(
            f"{guardian.current_hp:,} / {guardian.max_hp:,} HP",
            size=11,
            weight=ft.FontWeight.W_800,
            color="#FFD36E",
        )
        combat_log_text = ft.Text(
            "Tap ⚡ STRIKE on each set as you finish lifting to unleash Slime attacks!",
            size=11,
            color="#94A3B8",
            max_lines=2,
        )
        ore_counter_text = ft.Text(
            "⛏️ +0 Star-Iron",
            size=11,
            weight=ft.FontWeight.W_800,
            color="#4FE3F0",
        )

        # In-sheet Magicule Rest Recovery Overlay Banner
        rest_banner_timer = ft.Text("1:00", size=Type.TITLE, weight=ft.FontWeight.W_900, color="#4FE3F0")
        rest_banner_bar = ft.ProgressBar(value=0.0, color="#4FE3F0", bgcolor=C.a("#FFFFFF", 0.12), height=6, border_radius=3)
        rest_sage_msg = ft.Text(REST_SAGE_LINES[0], size=11, color="#E2E8F0")
        rest_sheet_gen = [0]

        def stop_sheet_rest(_: Any = None) -> None:
            sfx.play("tap")
            rest_sheet_gen[0] += 1
            rest_banner.visible = False
            self._rest_stop()
            ui.refresh(rest_banner)

        rest_banner = ft.Container(
            ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.AUTO_AWESOME, color="#4FE3F0", size=18),
                            ft.Text(
                                "MAGICULE RECOVERY (REST)",
                                size=11,
                                weight=ft.FontWeight.W_900,
                                color="#4FE3F0",
                                expand=True,
                            ),
                            rest_banner_timer,
                            ft.TextButton(
                                "Skip Rest",
                                on_click=stop_sheet_rest,
                                style=ft.ButtonStyle(color="#94A3B8", padding=4),
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    rest_banner_bar,
                    rest_sage_msg,
                ],
                spacing=4,
                tight=True,
            ),
            bgcolor="#0F1E36",
            border=ft.Border.all(1.5, C.a("#4FE3F0", 0.65)),
            border_radius=Radius.MD,
            padding=Space.SM,
            visible=False,
        )

        async def run_sheet_rest(seconds: int, dmg: int, is_pr: bool) -> None:
            rest_sheet_gen[0] += 1
            my_gen = rest_sheet_gen[0]
            self._rest_start(seconds)
            line_idx = (dmg + seconds) % len(REST_SAGE_LINES)
            prefix = f"💥 Dealt {dmg:,} DMG! " + ("🏆 NEW PR [Limit Breaker]! " if is_pr else "")
            rest_sage_msg.value = prefix + REST_SAGE_LINES[line_idx]
            rest_banner.visible = True
            ui.refresh(rest_banner)
            end_t = time.time() + seconds
            while my_gen == rest_sheet_gen[0]:
                left = end_t - time.time()
                if left <= 0:
                    rest_banner_timer.value = "READY!"
                    rest_banner_bar.value = 1.0
                    rest_sage_msg.value = "⚡ [GREAT SAGE] Magicules at 100%! Begin your next set!"
                    ui.refresh(rest_banner)
                    await asyncio.sleep(2.5)
                    if my_gen == rest_sheet_gen[0]:
                        rest_banner.visible = False
                        ui.refresh(rest_banner)
                    return
                s = int(left + 0.99)
                rest_banner_timer.value = f"{s // 60}:{s % 60:02d}"
                rest_banner_bar.value = max(0.0, min(1.0, 1.0 - left / max(1, seconds)))
                ui.refresh(rest_banner_timer, rest_banner_bar)
                await asyncio.sleep(0.4)

        def cycle_boss(_: Any = None) -> None:
            sfx.play("tap")
            st["boss_idx"] = (st["boss_idx"] + 1) % len(GUARDIAN_TEMPLATES)
            t = GUARDIAN_TEMPLATES[st["boss_idx"]]
            guardian.id, guardian.name, guardian.title, guardian.affinity, guardian.sprite = (
                t[0], t[1], t[2], t[3], t[4]
            )
            boss_img.src = guardian.sprite
            boss_name_text.value = f"⚔️ {guardian.name}"
            boss_aff_text.value = f"{guardian.affinity} · {guardian.title}"
            update_boss_damage()
            ui.refresh(boss_img, boss_name_text, boss_aff_text)

        boss_card = ft.Container(
            ft.Column(
                [
                    ft.Row(
                        [
                            ft.Column([boss_name_text, boss_aff_text], spacing=1, expand=True, tight=True),
                            ore_counter_text,
                            ft.IconButton(
                                ft.Icons.SWAP_HORIZ,
                                icon_color="#4FE3F0",
                                icon_size=18,
                                tooltip="Switch Labyrinth Guardian",
                                on_click=cycle_boss,
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Container(
                        ft.Stack(
                            [
                                ft.Row(
                                    [
                                        ft.Column(
                                            [
                                                player_box,
                                                ft.Text(g.profile.name, size=10, weight=ft.FontWeight.BOLD, color="#E2E8F0"),
                                            ],
                                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                            spacing=2,
                                            tight=True,
                                        ),
                                        ft.Column(
                                            [
                                                ft.Icon(ft.Icons.BOLT, color="#FFD36E", size=24),
                                                ft.Text("VS", size=11, weight=ft.FontWeight.W_900, color="#FFD36E"),
                                            ],
                                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                            spacing=0,
                                            tight=True,
                                        ),
                                        ft.Column(
                                            [
                                                boss_sprite_box,
                                                ft.Text("Guardian", size=10, weight=ft.FontWeight.BOLD, color="#FF6F91"),
                                            ],
                                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                            spacing=2,
                                            tight=True,
                                        ),
                                    ],
                                    alignment=ft.MainAxisAlignment.SPACE_AROUND,
                                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                ),
                                ft.Container(dmg_popup, alignment=ft.Alignment.TOP_CENTER, top=2),
                            ],
                        ),
                        bgcolor="#09111E",
                        border_radius=Radius.MD,
                        padding=ft.Padding.symmetric(horizontal=Space.MD, vertical=Space.SM),
                        border=ft.Border.all(1, "#1E293B"),
                    ),
                    boss_hp_bar,
                    ft.Row(
                        [
                            combat_log_text,
                            boss_hp_text,
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                ],
                spacing=6,
                tight=True,
            ),
            bgcolor="#0D1729",
            border=ft.Border.all(1.5, C.a("#4FE3F0", 0.45)),
            border_radius=Radius.LG,
            padding=Space.MD,
        )

        def update_boss_damage() -> tuple[int, int]:
            """Recalculate total struck damage (from completed sets) and update boss HP bar."""
            total_target = max(
                1200,
                int(sum((s[0] or 10) * (s[1] or 20) for ex in st["ex"] for s in ex["sets"])),
            )
            guardian.max_hp = total_target
            struck_dmg = int(
                sum((s[0] or 0) * (s[1] or 0) for ex in st["ex"] for s in ex["sets"] if len(s) > 2 and s[2])
            )
            rem_hp = max(0, guardian.max_hp - struck_dmg)
            guardian.current_hp = rem_hp
            boss_hp_bar.value = max(0.0, rem_hp / max(1, guardian.max_hp))
            ore_counter_text.value = f"⛏️ +{struck_dmg:,} Star-Iron"
            if rem_hp == 0 and struck_dmg > 0:
                boss_hp_text.value = "🏆 BOSS SLAIN! (+60 Bonus XP)"
                boss_hp_text.color = "#5EEAB0"
                boss_hp_bar.color = "#5EEAB0"
            else:
                boss_hp_text.value = f"{rem_hp:,} / {guardian.max_hp:,} HP"
                boss_hp_text.color = "#FFD36E"
                boss_hp_bar.color = "#FF4D6D"
            ui.refresh(boss_hp_bar, boss_hp_text, ore_counter_text)
            return struck_dmg, rem_hp

        async def play_strike_anim(ex_idx: int, set_idx: int) -> None:
            s = st["ex"][ex_idx]["sets"][set_idx]
            reps = int(s[0] or 0)
            weight = float(s[1] or 0.0)
            if reps <= 0 and weight <= 0:
                reps, weight = 10, 20.0
                s[0], s[1] = reps, weight
            dmg = max(10, round(reps * (weight if weight > 0 else 10.0)))
            ex_name = (st["ex"][ex_idx]["name"] or "Exercise").strip()

            # Check PR against saved exercise_prs
            prev_pr = g.data.exercise_prs.get(ex_name, 0.0)
            is_pr = weight > prev_pr and weight > 0
            if is_pr:
                g.data.exercise_prs[ex_name] = weight
                if "Unique Trait: [Limit Breaker]" not in g.data.unlocked_workout_traits:
                    g.data.unlocked_workout_traits.append("Unique Trait: [Limit Breaker]")

            # 1. Player lunges right, SFX + Haptic
            sfx.play("milestone" if is_pr else "quest_clear", 0.85)
            await ui.buzz("heavy" if is_pr else "medium")
            player_box.offset = ft.Offset(0.35, 0)
            player_box.scale = 1.18
            dmg_popup_text.value = f"💥 -{dmg:,} HP!" + (" 🏆 PR!" if is_pr else "")
            dmg_popup_text.color = "#5EEAB0" if is_pr else "#FFD36E"
            dmg_popup.opacity = 1
            dmg_popup.offset = ft.Offset(0, -0.15)
            ui.refresh(player_box, dmg_popup)

            await asyncio.sleep(0.16)
            # 2. Boss recoils & flashes
            boss_sprite_box.offset = ft.Offset(0.22, -0.08)
            boss_sprite_box.scale = 0.84
            player_box.offset = ft.Offset(0, 0)
            player_box.scale = 1.0
            combat_log_text.value = (
                f"⚡ {ex_name} Set {set_idx + 1}: Dealt {dmg:,} DMG!"
                + (" 🏆 NEW PR [Limit Breaker]!" if is_pr else "")
            )
            combat_log_text.color = "#5EEAB0" if is_pr else "#FFD36E"
            _, rem_hp = update_boss_damage()
            ui.refresh(boss_sprite_box, player_box, combat_log_text)

            await asyncio.sleep(0.22)
            boss_sprite_box.offset = ft.Offset(0, 0)
            boss_sprite_box.scale = 0.65 if rem_hp == 0 else 1.0
            ui.refresh(boss_sprite_box)

            # Start automatic Magicule Rest Timer
            if st["rest_preset"] > 0:
                app.page.run_task(run_sheet_rest, st["rest_preset"], dmg, is_pr)

            await asyncio.sleep(0.9)
            dmg_popup.opacity = 0
            dmg_popup.offset = ft.Offset(0, 0)
            ui.refresh(dmg_popup)

        def num_field(value: Any, hint_text: str, on_change: Any) -> ft.TextField:
            f = ft.TextField(value="" if value is None else f"{value:g}", hint_text=hint_text,
                             keyboard_type=ft.KeyboardType.NUMBER, dense=True, filled=True,
                             fill_color=C.SURFACE_HI, border_radius=Radius.SM, expand=True,
                             text_align=ft.TextAlign.CENTER, color=C.TEXT,
                             on_change=on_change)
            return f

        def paint() -> None:
            blocks: list[ft.Control] = []
            n = len(st["ex"])
            for i, ex in enumerate(st["ex"]):
                name = ft.TextField(value=ex["name"], hint_text="Exercise (e.g. Squat)",
                                    dense=True, filled=True, fill_color=C.SURFACE_HI,
                                    border_radius=Radius.SM, expand=True, color=C.TEXT,
                                    capitalization=ft.TextCapitalization.WORDS,
                                    on_change=lambda e, k=i: st["ex"][k].update(
                                        name=e.control.value or ""))
                head = ft.Row([
                    name,
                    ft.IconButton(ft.Icons.ARROW_UPWARD, icon_size=18, width=36, height=40,
                                  disabled=i == 0, tooltip="Move up",
                                  on_click=lambda e, k=i: move(k, -1)),
                    ft.IconButton(ft.Icons.ARROW_DOWNWARD, icon_size=18, width=36, height=40,
                                  disabled=i == n - 1, tooltip="Move down",
                                  on_click=lambda e, k=i: move(k, 1)),
                    ft.IconButton(ft.Icons.CLOSE, icon_size=18, width=36, height=40,
                                  icon_color=C.DANGER, tooltip="Remove exercise",
                                  on_click=lambda e, k=i: remove_ex(k)),
                ], spacing=0, vertical_alignment=ft.CrossAxisAlignment.CENTER)
                rows: list[ft.Control] = []
                for j, s_item in enumerate(ex["sets"]):
                    while len(s_item) < 3:
                        s_item.append(False)
                    reps, weight, done = s_item[0], s_item[1], bool(s_item[2])

                    def set_val(e: Any, k: int = i, m: int = j, col: int = 0) -> None:
                        st["ex"][k]["sets"][m][col] = _num(e.control.value,
                                                           int if col == 0 else float)
                        update_boss_damage()

                    def toggle_strike(_: Any, k: int = i, m: int = j) -> None:
                        cur = bool(st["ex"][k]["sets"][m][2])
                        st["ex"][k]["sets"][m][2] = not cur
                        repaint()
                        if not cur:
                            app.page.run_task(play_strike_anim, k, m)
                        else:
                            sfx.play("tap")
                            update_boss_damage()

                    set_dmg = int((reps or 0) * (weight or 0))
                    strike_btn = ft.Container(
                        ft.Row(
                            [
                                ft.Icon(
                                    ft.Icons.CHECK_CIRCLE if done else ft.Icons.BOLT,
                                    size=15,
                                    color="#09111E" if done else "#FFD36E",
                                ),
                                ft.Text(
                                    f"{set_dmg} DMG" if done else "STRIKE",
                                    size=10,
                                    weight=ft.FontWeight.W_900,
                                    color="#09111E" if done else "#FFD36E",
                                ),
                            ],
                            spacing=3,
                            tight=True,
                        ),
                        bgcolor="#5EEAB0" if done else C.a("#FFD36E", 0.16),
                        border=ft.Border.all(1.2, "#5EEAB0" if done else "#FFD36E"),
                        border_radius=Radius.PILL,
                        padding=ft.Padding.symmetric(horizontal=10, vertical=7),
                        on_click=toggle_strike,
                        ink=True,
                        tooltip="Complete Set & Strike Guardian!",
                    )
                    rows.append(ft.Row([
                        ft.Text(f"S{j + 1}", size=Type.CAPTION, weight=ft.FontWeight.BOLD,
                                color="#5EEAB0" if done else C.TEXT_DIM, width=26),
                        num_field(reps, "reps", lambda e, k=i, m=j: set_val(e, k, m, 0)),
                        ft.Text("×", color=C.TEXT_DIM),
                        num_field(weight, st["unit"], lambda e, k=i, m=j: set_val(e, k, m, 1)),
                        strike_btn,
                        ft.IconButton(ft.Icons.REMOVE_CIRCLE_OUTLINE, icon_size=16, width=30,
                                      height=36, icon_color=C.TEXT_DIM, tooltip="Remove set",
                                      disabled=len(ex["sets"]) == 1,
                                      on_click=lambda e, k=i, m=j: remove_set(k, m)),
                    ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER))
                rows.append(ft.TextButton("Add set", icon=ft.Icons.ADD, height=36,
                                          on_click=lambda e, k=i: add_set(k)))
                blocks.append(ft.Container(ft.Column([head, *rows], spacing=Space.XS,
                                                     tight=True),
                                           bgcolor=C.a(C.SURFACE_HI, 0.6),
                                           border_radius=Radius.SM, padding=Space.SM))
            ex_col.controls = blocks

        def repaint() -> None:
            paint()
            update_boss_damage()
            ui.refresh(ex_col)

        def move(i: int, d: int) -> None:
            sfx.play("tap")
            exs = st["ex"]
            exs[i], exs[i + d] = exs[i + d], exs[i]
            repaint()

        def remove_ex(i: int) -> None:
            sfx.play("tap")
            st["ex"].pop(i)
            repaint()

        def add_ex(name: str = "") -> None:
            sfx.play("tap")
            st["ex"].append({"name": name, "sets": [[10, 20.0, False], [10, 20.0, False], [10, 20.0, False]]})
            repaint()

        def add_set(i: int) -> None:
            sfx.play("tap")
            sets = st["ex"][i]["sets"]
            last = sets[-1] if sets else [10, 20.0, False]
            sets.append([last[0], last[1], False])
            repaint()

        def remove_set(i: int, j: int) -> None:
            sfx.play("tap")
            st["ex"][i]["sets"].pop(j)
            repaint()

        def set_unit(v: str) -> None:
            sfx.play("toggle")
            st["unit"] = v
            repaint()

        def set_rest_preset(v: str) -> None:
            sfx.play("toggle")
            st["rest_preset"] = int(v)

        def exercises() -> list[ExerciseEntry]:
            out = []
            for ex in st["ex"]:
                name = (ex["name"] or "").strip()
                sets = [SetEntry(reps=s[0], weight=s[1], unit=st["unit"]) for s in ex["sets"]
                        if s[0] is not None or s[1] is not None]
                if name:
                    out.append(ExerciseEntry(name, sets))
            return out

        def log(_: Any = None) -> None:
            exs = exercises()
            if not exs and not st["minutes"]:
                app.error("Add an exercise or some minutes first")
                return
            # Calculate total Star-Iron Ore earned from all sets with reps & weight
            total_ore = int(
                sum((s[0] or 0) * (s[1] or 0) for ex in st["ex"] for s in ex["sets"] if (s[0] or 0) > 0 and (s[1] or 0) > 0)
            )
            g.data.star_iron += total_ore
            qid, pid = self._link_args(st)
            common.close(sheet)
            label = f"{len(exs)} exercise{'s' if len(exs) != 1 else ''}"
            if total_ore > 0:
                label += f" (+{total_ore:,} Star-Iron Ore)"
            app.page.run_task(self._log, lambda: g.log_workout(
                st["minutes"], app.today(), st["type"], st["effort"],
                (notes.value or "").strip(), qid, pid, exs), label)

        def save_routine(_: Any = None) -> None:
            name = (routine_name.value or "").strip()
            if not name:
                routine_name.error_text = "Name the routine"
                sfx.play("error_soft")
                routine_name.update()
                return
            try:
                g.add_workout_template(name, st["type"], st["minutes"], exercises(),
                                       (notes.value or "").strip())
            except ValueError as exc:
                app.error(f"Couldn't save: {exc}")
                return
            app.save()
            sfx.play("toggle")
            routine_name.error_text = None
            routine_name.value = ""
            ui.refresh(routine_name)
            app.toast(f"Routine saved: {name}", ft.Icons.BOOKMARK_ADD)
            self._refresh()

        paint()
        update_boss_damage()
        known = g.exercise_names()[:8]
        minutes = common.stepper(st["minutes"], lambda v: st.update(minutes=v), lo=0, hi=300,
                                 step=5, suffix=" min", width=72)

        body: list[ft.Control] = [
            boss_card,
            rest_banner,
            ft.Row([
                common.hint("Auto-Rest after Strike"),
                ft.Container(expand=True),
                common.segmented(
                    [("0", "Off"), ("60", "60s"), ("90", "90s"), ("120", "2m")],
                    str(st["rest_preset"]),
                    on_change=set_rest_preset,
                ),
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Row([common.hint("Weights in"), ft.Container(expand=True),
                    common.segmented([("kg", "kg"), ("lb", "lb")], st["unit"],
                                     on_change=set_unit)],
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ex_col,
            ft.Row([
                common.primary_button("Browse Exercises", lambda e: self._open_exercise_picker(add_ex),
                                      icon=ft.Icons.SEARCH),
                common.secondary_button("Custom Exercise", lambda e: add_ex(),
                                        icon=ft.Icons.ADD),
            ], spacing=Space.SM),
        ]
        if known:
            body.append(ft.Row([ft.TextButton(n, height=36, on_click=lambda e, n=n: add_ex(n))
                                for n in known], wrap=True, spacing=0))
        body += [
            ft.Row([ft.Icon(ft.Icons.TIMER, color=C.TEXT_DIM, size=20),
                    ft.Text("Minutes", color=C.TEXT_DIM, expand=True), minutes],
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
            self._effort_row(st),
            ft.Row([self._link_dropdown(st)]),
            notes,
            ft.Row([common.primary_button("Log session", log, icon=ft.Icons.CHECK)]),
            ft.Row([ft.Container(routine_name, expand=True),
                    ft.IconButton(ft.Icons.BOOKMARK_ADD, icon_color=C.PRIMARY,
                                  tooltip="Save as routine", width=Size.TAP, height=Size.TAP,
                                  on_click=save_routine)],
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
        ]
        sheet = common.open_sheet(app.page, heading, body)

    # ------------------------------------------------------------------ actions
    def _copy(self, session_id: str) -> None:
        draft = self.app.game.copy_workout(session_id, self.app.today())
        if draft.exercises:
            self.open_builder(draft, heading="Copy of a session")
            return
        # no exercises: a quick re-log of the same type/minutes/effort
        g, app = self.app.game, self.app
        app.page.run_task(self._log, lambda: g.log_workout_draft(draft, app.today()),
                          f"{TYPES.get(draft.type, TYPES['other'])[0]}, {draft.minutes} min")

    def _use_routine(self, template_id: str) -> None:
        sfx.play("tap")
        draft = self.app.game.workout_from_template(template_id, self.app.today())
        self.open_builder(draft, heading=self.app.game.workout_template(template_id).name)

    def _to_routine(self, session_id: str) -> None:
        t = self.app.game.template_from_workout(session_id)
        self.app.save()
        sfx.play("toggle")
        self.app.toast(f"Saved as routine: {t.name}", ft.Icons.BOOKMARK_ADD)
        self._refresh()

    async def _delete(self, session_id: str) -> None:
        if not await common.confirm(self.app.page, "Delete this workout?",
                                    "It leaves your log. XP you earned stays.", "Delete",
                                    danger=True):
            return
        self.app.game.delete_workout(session_id)
        self.app.save()
        self.app.toast("Workout deleted", ft.Icons.DELETE_OUTLINE)
        self._refresh()

    async def _delete_routine(self, template_id: str) -> None:
        name = self.app.game.workout_template(template_id).name
        if not await common.confirm(self.app.page, f"Delete {name}?",
                                    "The routine goes away. Logged sessions stay.", "Delete",
                                    danger=True):
            return
        self.app.game.delete_workout_template(template_id)
        self.app.save()
        self.app.toast("Routine deleted", ft.Icons.DELETE_OUTLINE)
        self._refresh()

    async def _exercise(self, name: str) -> None:
        """Records sheet; the first open of each exercise per visit plays a short scan."""
        if name not in self._scanned:
            self._scanned.add(name)
            sfx.play("tap")
            await ui.lumen_analyze(self.app.page, RECORD_STAGES, seconds=1.4)
        self.open_exercise(name)

    def open_exercise(self, name: str) -> None:
        g = self.app.game
        st = {"unit": "kg"}
        body_col = ft.Column(spacing=Space.SM, tight=True)

        def paint() -> None:
            prs = g.personal_records(name, st["unit"])
            rows: list[ft.Control] = []
            for kind, label in PR_LABELS.items():
                pr = prs.get(kind)
                if pr is None:
                    continue
                d = date.fromisoformat(pr.day)
                val = (f"{pr.value:g} {pr.unit}" if kind != "longest_time"
                       else f"{int(pr.value)} s")
                if kind == "max_reps":
                    val = f"{int(pr.value)} reps"
                rows.append(ft.Row([
                    ft.Icon(ft.Icons.EMOJI_EVENTS, color=C.ACCENT, size=18),
                    ft.Text(label, size=Type.BODY - 1, color=C.TEXT, expand=True),
                    ft.Text(val, size=Type.BODY - 1, weight=ft.FontWeight.W_700, color=C.TEXT),
                    common.hint(common.short_date(d)),
                ], spacing=Space.SM))
            if not rows:
                rows.append(common.hint("No sets with numbers logged yet."))
            hist = g.exercise_history(name)[:12]
            rows.append(ft.Divider(height=1, color=C.OUTLINE))
            rows.append(common.hint("Your past sessions (newest first)"))
            for w, ex in hist:
                d = date.fromisoformat(w.day)
                rows.append(ft.Row([
                    ft.Text(f"{d:%a} {common.short_date(d)}", size=Type.CAPTION,
                            color=C.TEXT_DIM, width=72),
                    ft.Text(", ".join(set_text(s) for s in ex.sets) or "-", size=Type.CAPTION,
                            color=C.TEXT, expand=True),
                ], vertical_alignment=ft.CrossAxisAlignment.START))
            body_col.controls = rows

        def set_unit(v: str) -> None:
            sfx.play("toggle")
            st["unit"] = v
            paint()
            ui.refresh(body_col)

        paint()
        common.open_sheet(self.app.page, name, [
            ft.Row([ft.Container(common.hint("Your own bests, for reference."), expand=True),
                    common.segmented([("kg", "kg"), ("lb", "lb")], "kg", on_change=set_unit)],
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
            body_col,
        ])
