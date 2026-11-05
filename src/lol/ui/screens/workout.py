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

from lol.core.game import REST_TIMER_PRESETS
from lol.core.models import ExerciseEntry, SetEntry, WorkoutSession
from lol.ui import components as ui
from lol.ui import sfx
from lol.ui import theme as th
from lol.ui.screens import common
from lol.ui.theme import C, Radius, Size, Space, Type

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
                        stat(f"{stats['xp_left']}", "XP left today")]),
                ft.Row([common.primary_button("Quick log", self.open_quick,
                                              icon=ft.Icons.BOLT),
                        common.secondary_button("Strength", lambda e: self.open_builder(None),
                                                icon=ft.Icons.FITNESS_CENTER)],
                       spacing=Space.SM),
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
    def open_builder(self, draft: WorkoutSession | None, *, heading: str = "Strength session"
                     ) -> None:
        """Exercises + sets editor. `draft`: a copy / routine draft to start from."""
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
            # editable copy: [{"name": str, "sets": [[reps, weight], ...]}]
            "ex": [{"name": ex.name,
                    "sets": [[s.reps, s.weight] for s in ex.sets] or [[None, None]]}
                   for ex in (draft.exercises if draft else [])],
        }
        if not st["ex"]:
            st["ex"] = [{"name": "", "sets": [[None, None]]}]
        ex_col = ft.Column(spacing=Space.SM, tight=True)
        notes = common.text_field("Notes (optional)")
        notes.value = draft.notes if draft else ""
        routine_name = common.text_field("Routine name (to save as a routine)")

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
                for j, (reps, weight) in enumerate(ex["sets"]):
                    def set_val(e: Any, k: int = i, m: int = j, col: int = 0) -> None:
                        st["ex"][k]["sets"][m][col] = _num(e.control.value,
                                                           int if col == 0 else float)
                    rows.append(ft.Row([
                        ft.Text(f"Set {j + 1}", size=Type.CAPTION, color=C.TEXT_DIM, width=40),
                        num_field(reps, "reps", lambda e, k=i, m=j: set_val(e, k, m, 0)),
                        ft.Text("×", color=C.TEXT_DIM),
                        num_field(weight, st["unit"], lambda e, k=i, m=j: set_val(e, k, m, 1)),
                        ft.IconButton(ft.Icons.REMOVE_CIRCLE_OUTLINE, icon_size=18, width=36,
                                      height=40, icon_color=C.TEXT_DIM, tooltip="Remove set",
                                      disabled=len(ex["sets"]) == 1,
                                      on_click=lambda e, k=i, m=j: remove_set(k, m)),
                    ], spacing=Space.XS, vertical_alignment=ft.CrossAxisAlignment.CENTER))
                rows.append(ft.TextButton("Add set", icon=ft.Icons.ADD, height=40,
                                          on_click=lambda e, k=i: add_set(k)))
                blocks.append(ft.Container(ft.Column([head, *rows], spacing=Space.XS,
                                                     tight=True),
                                           bgcolor=C.a(C.SURFACE_HI, 0.6),
                                           border_radius=Radius.SM, padding=Space.SM))
            ex_col.controls = blocks

        def repaint() -> None:
            paint()
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
            st["ex"].append({"name": name, "sets": [[None, None]]})
            repaint()

        def add_set(i: int) -> None:
            sfx.play("tap")
            sets = st["ex"][i]["sets"]
            sets.append(list(sets[-1]) if sets else [None, None])  # repeat the last set
            repaint()

        def remove_set(i: int, j: int) -> None:
            sfx.play("tap")
            st["ex"][i]["sets"].pop(j)
            repaint()

        def set_unit(v: str) -> None:
            sfx.play("toggle")
            st["unit"] = v
            repaint()

        def exercises() -> list[ExerciseEntry]:
            out = []
            for ex in st["ex"]:
                name = (ex["name"] or "").strip()
                sets = [SetEntry(reps=r, weight=w, unit=st["unit"]) for r, w in ex["sets"]
                        if r is not None or w is not None]
                if name:
                    out.append(ExerciseEntry(name, sets))
            return out

        def log(_: Any = None) -> None:
            exs = exercises()
            if not exs and not st["minutes"]:
                app.error("Add an exercise or some minutes first")
                return
            qid, pid = self._link_args(st)
            common.close(sheet)
            label = f"{len(exs)} exercise{'s' if len(exs) != 1 else ''}"
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
        known = g.exercise_names()[:8]
        minutes = common.stepper(st["minutes"], lambda v: st.update(minutes=v), lo=0, hi=300,
                                 step=5, suffix=" min", width=72)
        body: list[ft.Control] = [
            ft.Row([common.hint("Weights in"), ft.Container(expand=True),
                    common.segmented([("kg", "kg"), ("lb", "lb")], st["unit"],
                                     on_change=set_unit)],
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ex_col,
            ft.Row([common.secondary_button("Add exercise", lambda e: add_ex(),
                                            icon=ft.Icons.ADD)]),
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
