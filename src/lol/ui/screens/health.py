"""More -> Body: height / weight / age / sex / activity, a weight log with a trend chart, BMI
(with WHO category and a one-line caveat) and Luma's plan: goal + pace -> daily kcal range,
macros, fiber and water hints, an estimated date.

Rules live in lol.core (nutrition.py formulas, body.py Game API). Logging weight gives a
little capped Monk XP; the number itself is never rewarded or judged."""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

import flet as ft

from lol.core import nutrition as nu
from lol.core.models import NutritionPlan
from lol.ui import components as ui
from lol.ui import sfx
from lol.ui.screens import common
from lol.ui.theme import C, Motion, Radius, Size, Space, Type

if TYPE_CHECKING:
    from lol.ui.app import App

BODY = "#6EE7B7"  # mint (same on every theme)
MACRO_COLORS = {"protein": "#FF8FA3", "carbs": "#FFC857", "fat": "#7FB2FF"}
SEX_OPTIONS = (("female", "Female"), ("male", "Male"), ("unspecified", "Prefer not to say"))
STAGES = {
    "lose": ("SCANNING BODY DATA…", "CALCULATING DEFICIT…", "PLAN READY"),
    "gain": ("SCANNING BODY DATA…", "CALCULATING SURPLUS…", "PLAN READY"),
    "maintain": ("SCANNING BODY DATA…", "BALANCING ENERGY…", "PLAN READY"),
}


# --- formatting ----------------------------------------------------------------------------------
def fmt_w(kg: float | None, unit: str, digits: int = 1) -> str:
    if kg is None:
        return "–"
    return f"{nu.from_kg(kg, unit):,.{digits}f} {unit}"


def fmt_h(cm: float | None, unit: str) -> str:
    if not cm:
        return "–"
    if unit == "ftin":
        ft_, in_ = nu.cm_to_ft_in(cm)
        return f"{ft_}′{in_}″"
    return f"{cm:g} cm"


def parse_num(text: str | None) -> float | None:
    t = (text or "").replace(",", ".").strip()
    try:
        return float(t) if t else None
    except ValueError:
        return None


def num_field(label: str, value: str = "", suffix: str | None = None,
              width: int | None = None) -> ft.TextField:
    """Numeric text field (number keyboard with a decimal point on phones)."""
    f = common.text_field(label, number=True)
    f.value = value
    f.suffix = suffix
    if width:
        f.width = width
    else:
        f.expand = True
    return f


def plan_dict(plan: nu.PlanResult | NutritionPlan) -> dict[str, Any]:
    """PlanResult (a proposal) or NutritionPlan (saved) -> one plain dict for the card."""
    if isinstance(plan, nu.PlanResult):
        m = plan.macros
        return {"goal": plan.goal, "pace": plan.pace, "start_kg": plan.start_kg,
                "goal_kg": plan.goal_kg, "bmr": plan.bmr, "tdee": plan.tdee,
                "floor": plan.floor, "target": plan.target_kcal, "low": plan.kcal_low,
                "high": plan.kcal_high, "protein": m.protein_g, "fat": m.fat_g,
                "carbs": m.carbs_g, "fiber": m.fiber_g, "water": m.water_ml,
                "weekly": plan.weekly_kg, "est": plan.est_date, "notes": list(plan.notes),
                "floor_bound": plan.floor_bound}
    return {"goal": plan.goal, "pace": plan.pace, "start_kg": plan.start_kg,
            "goal_kg": plan.goal_kg, "bmr": plan.bmr, "tdee": plan.tdee, "floor": plan.floor,
            "target": plan.target_kcal, "low": plan.kcal_low, "high": plan.kcal_high,
            "protein": plan.protein_g, "fat": plan.fat_g, "carbs": plan.carbs_g,
            "fiber": plan.fiber_g, "water": plan.water_ml, "weekly": plan.weekly_kg,
            "est": date.fromisoformat(plan.est_date) if plan.est_date else None,
            "notes": list(plan.notes), "floor_bound": plan.floor_bound,
            "created": plan.created}


def macro_row(name: str, grams: list[int] | tuple[int, ...], kcal_per_g: int, total: int,
              color: str, eaten: float | None = None) -> ft.Control:
    """Protein 126 g (112–154) · 504 kcal · 27 %  [bar]. With `eaten`: progress toward it."""
    lo, mid, hi = grams
    kcal = mid * kcal_per_g
    pct = round(kcal * 100 / total) if total else 0
    if eaten is None:
        value = pct / 100
        right = f"{mid} g · {kcal:,} kcal · {pct}%"
        sub = f"range {lo}–{hi} g"
    else:
        value = min(1.0, eaten / mid) if mid else 0
        right = f"{eaten:.0f} / {mid} g"
        sub = f"range {lo}–{hi} g"
    return ft.Column([
        ft.Row([ft.Container(width=10, height=10, border_radius=5, bgcolor=color),
                ft.Text(name, size=Type.LABEL, weight=ft.FontWeight.W_700, color=C.TEXT),
                ft.Text(sub, size=Type.CAPTION, color=C.TEXT_DIM, expand=True),
                ft.Text(right, size=Type.LABEL, weight=ft.FontWeight.W_600, color=C.TEXT)],
               spacing=Space.SM, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        ft.ProgressBar(value=value, color=color, bgcolor=C.a(C.TEXT, 0.08), height=6,
                       border_radius=3),
    ], spacing=4, tight=True)


def plan_card(plan: nu.PlanResult | NutritionPlan, unit: str, *, title: str = "Your plan",
              actions: list[ft.Control] | None = None) -> ft.Container:
    p = plan_dict(plan)
    goal_words = {"lose": "Lose", "gain": "Gain", "maintain": "Maintain"}[p["goal"]]
    if p["goal"] == "maintain":
        goal_line = f"Maintain around {fmt_w(p['start_kg'], unit)}"
    else:
        rate = abs(p["weekly"])
        when = (f" · around {p['est']:%b %d, %Y}" if p["est"] else "")
        goal_line = (f"{goal_words} to {fmt_w(p['goal_kg'], unit)} · "
                     f"~{nu.from_kg(rate, unit):.2f} {unit}/week{when}")
    total = p["target"]
    rows: list[ft.Control] = [
        ft.Row([ft.Icon(ft.Icons.AUTO_AWESOME, color=BODY, size=18),
                ft.Text(title.upper(), size=Type.CAPTION, weight=ft.FontWeight.BOLD,
                        color=BODY, style=ft.TextStyle(letter_spacing=1.5), expand=True)],
               spacing=Space.SM),
        ft.Row([ft.Text(f"{total:,}", size=Type.HERO, weight=ft.FontWeight.W_900,
                        color=C.TEXT),
                ft.Column([ft.Text("kcal a day", size=Type.LABEL, color=C.TEXT),
                           common.hint(f"aim for {p['low']:,}–{p['high']:,}")],
                          spacing=0, tight=True)],
               spacing=Space.SM, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        ft.Text(goal_line, size=Type.BODY - 1, color=C.TEXT),
        ft.Divider(height=1, color=C.OUTLINE),
        macro_row("Protein", p["protein"], 4, total, MACRO_COLORS["protein"]),
        macro_row("Carbs", p["carbs"], 4, total, MACRO_COLORS["carbs"]),
        macro_row("Fat", p["fat"], 9, total, MACRO_COLORS["fat"]),
        ft.Row([ft.Icon(ft.Icons.GRASS, size=16, color=C.TEXT_DIM),
                common.hint(f"Fiber ~{p['fiber']} g"),
                ft.Icon(ft.Icons.WATER_DROP, size=16, color=C.TEXT_DIM),
                common.hint(f"Water ~{p['water'][0] / 1000:.1f}–{p['water'][1] / 1000:.1f} L "
                            "(food counts too)")], spacing=Space.XS, wrap=True),
    ]
    for note in p["notes"]:
        rows.append(ft.Row([ft.Icon(ft.Icons.INFO_OUTLINE, size=16, color=C.ACCENT),
                            ft.Text(note, size=Type.CAPTION, color=C.TEXT, expand=True)],
                           spacing=Space.SM, vertical_alignment=ft.CrossAxisAlignment.START))
    rows.append(common.hint(f"Resting burn ~{p['bmr']:,} kcal · daily burn ~{p['tdee']:,} "
                            f"kcal (estimates) · safe minimum {p['floor']:,} kcal"))
    rows.append(common.hint(nu.DISCLAIMER))
    if actions:
        rows.append(ft.Row(actions, spacing=Space.SM))
    return common.card(ft.Column(rows, spacing=Space.SM, tight=True), tint=BODY)


class _Pills:
    """Small single-choice pills with a subtitle (activity levels, goals, paces)."""

    def __init__(self, options: list[tuple[str, str, str]], value: str, on_change: Any,
                 cols: int = 1) -> None:
        self.value, self.on_change = value, on_change
        self.boxes: dict[str, ft.Container] = {}
        for val, label, sub in options:
            self.boxes[val] = ft.Container(
                ft.Column([ft.Text(label, size=Type.LABEL, weight=ft.FontWeight.W_700),
                           *([ft.Text(sub, size=Type.CAPTION)] if sub else [])],
                          spacing=0, tight=True,
                          horizontal_alignment=ft.CrossAxisAlignment.CENTER if cols > 1
                          else ft.CrossAxisAlignment.START),
                col=12 // cols, padding=ft.Padding.symmetric(horizontal=Space.MD, vertical=6),
                border_radius=Radius.SM, alignment=ft.Alignment.CENTER_LEFT if cols == 1
                else ft.Alignment.CENTER, height=Size.TAP + (8 if sub else 0),
                animate=Motion.anim(Motion.FADE_MS), scale=1,
                animate_scale=Motion.anim(Motion.POP_MS, Motion.BACK),
                on_click=lambda e, v=val: self.pick(v))
        self.control = ft.ResponsiveRow(list(self.boxes.values()), spacing=Space.SM,
                                        run_spacing=Space.SM)
        self.paint()

    def paint(self) -> None:
        for val, box in self.boxes.items():
            on = val == self.value
            box.bgcolor = C.a(BODY, 0.18) if on else C.a(C.TEXT, 0.05)
            box.border = ft.Border.all(1.5, C.a(BODY, 0.8) if on else C.a(C.TEXT, 0.08))
            col = box.content
            for i, t in enumerate(col.controls):  # type: ignore[union-attr]
                t.color = (BODY if on else C.TEXT) if i == 0 else C.TEXT_DIM

    def pick(self, value: str) -> None:
        sfx.play("toggle")
        self.value = value
        self.paint()
        ui.refresh(self.control)
        if self.control.page:
            self.control.page.run_task(ui.pop, self.boxes[value], 1.04)
        if self.on_change:
            self.on_change(value)


class BodyScreen:
    title = "Body"

    def __init__(self, app: App) -> None:
        self.app = app
        self.list = common.screen_list()
        self.view = ft.Container(self.list, expand=True, key="body")
        self.fab = ft.FloatingActionButton(icon=ft.Icons.MONITOR_WEIGHT, on_click=self.open_log,
                                           bgcolor=C.PRIMARY, foreground_color=C.ON_PRIMARY,
                                           tooltip="Log weight")

    def _refresh(self) -> None:
        self.render()
        ui.refresh(self.list)

    def restyle(self) -> None:
        self._refresh()

    # ------------------------------------------------------------------ render
    def render(self) -> None:
        g, today = self.app.game, self.app.today()
        b = g.body
        unit = b.weight_unit
        st = g.body_status(today)
        items: list[ft.Control] = [self._top(st, unit), self._trend(unit),
                                   common.section("Your stats"), self._stats(st),
                                   common.section("Goal & plan")]
        if b.plan is not None:
            items.append(plan_card(b.plan, unit, actions=[
                common.secondary_button("New plan", self.open_goal, icon=ft.Icons.TUNE),
                common.secondary_button("Clear", self._clear_plan, icon=ft.Icons.CLOSE,
                                        color=C.TEXT_DIM),
            ]))
            items.append(common.hint(f"Plan made {common.long_date(date.fromisoformat(b.plan.created))}"
                                     f" from {fmt_w(b.plan.start_kg, unit)}. Weight changes "
                                     "over time - make a new plan whenever you like."))
        else:
            items.append(self._goal_cta(st))
        items.append(common.section("Weigh-ins"))
        rows = list(reversed(g.weights()))[:30]
        if not rows:
            items.append(common.empty_card("No weigh-ins yet",
                                           "Log your weight whenever you like. Any day counts.",
                                           ft.Icons.MONITOR_WEIGHT))
        for w in rows:
            items.append(self._weight_row(w.id, w.day, w.kg, w.note, unit))
        items.append(ft.Container(common.hint(nu.DISCLAIMER), padding=Space.SM))
        self.list.controls = items

    def _top(self, st: dict, unit: str) -> ft.Control:
        w = st["weight_kg"]
        bmi_bits: list[ft.Control] = []
        if st["bmi"] is not None:
            lo, hi = st["healthy_kg"]
            bmi_bits = [
                ft.Row([ui.chip(f"BMI {st['bmi']:.1f}", icon=ft.Icons.STRAIGHTEN, color=BODY),
                        ft.Text(st["bmi_category"], size=Type.LABEL, color=C.TEXT,
                                weight=ft.FontWeight.W_600)], spacing=Space.SM, wrap=True),
                common.hint(f"{nu.BMI_NOTE} Healthy range for your height: "
                            f"{fmt_w(lo, unit)}–{fmt_w(hi, unit)}."),
            ]
        elif w is not None:
            bmi_bits = [common.hint("Add your height to see BMI.")]
        return common.card(ft.Column([
            ft.Row([
                ft.Column([common.hint("Latest weight"),
                           ft.Text(fmt_w(w, unit), size=Type.DISPLAY,
                                   weight=ft.FontWeight.W_900, color=C.TEXT)],
                          spacing=0, tight=True, expand=True),
                common.segmented([("kg", "kg"), ("lb", "lb")], unit, on_change=self._set_unit),
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
            *bmi_bits,
            ft.Row([common.primary_button("Log weight", self.open_log,
                                          icon=ft.Icons.MONITOR_WEIGHT)]),
        ], spacing=Space.SM, tight=True), tint=BODY)

    def _trend(self, unit: str) -> ft.Control:
        g, today = self.app.game, self.app.today()
        rows = g.weights(today - timedelta(days=90), today)[-14:]
        if len(rows) < 2:
            chart: ft.Control = ft.Container(
                common.hint("Two or more weigh-ins draw a trend here."), height=48,
                alignment=ft.Alignment.CENTER)
        else:
            vals = [nu.from_kg(w.kg, unit) for w in rows]
            base = min(vals) - max(1.0, (max(vals) - min(vals)) * 0.6)  # zoom on the change
            chart = common.bar_chart(
                [(f"{date.fromisoformat(w.day):%d}", v - base, f"{v:.1f}")
                 for w, v in zip(rows, vals, strict=True)], color=BODY, height=130)
        first_last = ""
        if len(rows) >= 2:
            d = nu.from_kg(rows[-1].kg - rows[0].kg, unit)
            first_last = f"{'+' if d > 0 else ''}{d:.1f} {unit} since {common.short_date(date.fromisoformat(rows[0].day))}"
        return common.card(ft.Column([
            ft.Row([ft.Text("Trend", size=Type.BODY, weight=ft.FontWeight.W_700, color=C.TEXT,
                            expand=True), common.hint(first_last or f"last {len(rows)}")]),
            chart,
            common.hint("Your own numbers. Day-to-day ups and downs are normal (water, food)."),
        ], spacing=Space.SM, tight=True))

    def _stats(self, st: dict) -> ft.Control:
        b = self.app.game.body
        sex = dict(SEX_OPTIONS).get(b.sex or "", "–")
        act = nu.ACTIVITY_LABELS.get(b.activity, ("–", ""))[0]

        def cell(label: str, value: str) -> ft.Control:
            return ft.Column([common.hint(label),
                              ft.Text(value, size=Type.BODY, weight=ft.FontWeight.W_700,
                                      color=C.TEXT, max_lines=1,
                                      overflow=ft.TextOverflow.ELLIPSIS)],
                             spacing=0, tight=True, col=6)

        missing = st["missing"]
        return common.card(ft.Column([
            ft.ResponsiveRow([cell("Height", fmt_h(b.height_cm, b.height_unit)),
                              cell("Age", str(st["age"]) if st["age"] is not None else "–"),
                              cell("Sex (for the formula)", sex), cell("Activity", act)],
                             run_spacing=Space.SM),
            *([common.hint("Luma still needs: " + ", ".join(missing))] if missing else []),
            ft.Row([common.secondary_button("Edit stats", self.open_stats, icon=ft.Icons.EDIT)]),
        ], spacing=Space.MD, tight=True), on_click=self.open_stats)

    def _goal_cta(self, st: dict) -> ft.Control:
        return common.card(ft.Column([
            ft.Row([ft.Icon(ft.Icons.AUTO_AWESOME, color=BODY),
                    ft.Text("Ask Luma for a plan", size=Type.TITLE,
                            weight=ft.FontWeight.W_800, color=C.TEXT)], spacing=Space.SM),
            common.hint("Pick a goal (lose, keep or gain) and a gentle pace. Luma works out a "
                        "daily calorie range and macros. Optional - your log works without it."),
            ft.Row([common.primary_button("Set a goal", self.open_goal, icon=ft.Icons.FLAG)]),
        ], spacing=Space.SM, tight=True), tint=BODY)

    def _weight_row(self, wid: str, day: str, kg: float, note: str, unit: str) -> ft.Control:
        d = date.fromisoformat(day)
        return common.card(ft.Row([
            ft.Icon(ft.Icons.MONITOR_WEIGHT, color=BODY, size=20),
            ft.Column([ft.Text(fmt_w(kg, unit), size=Type.BODY, weight=ft.FontWeight.W_700,
                               color=C.TEXT),
                       common.hint(f"{d:%a} {common.short_date(d)}" + (f" · {note}" if note
                                                                        else ""))],
                      spacing=0, tight=True, expand=True),
            common.menu_button([("Delete", ft.Icons.DELETE_OUTLINE,
                                 lambda: self._delete_weight(wid), True)],
                               tooltip="Weigh-in options"),
        ], spacing=Space.MD, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.Padding.only(left=Space.MD, top=Space.XS, bottom=Space.XS))

    # ------------------------------------------------------------------ actions
    def _set_unit(self, unit: str) -> None:
        sfx.play("toggle")
        self.app.game.set_body(weight_unit=unit)
        self.app.save()
        self._refresh()

    def open_log(self, _: Any = None) -> None:
        app, g = self.app, self.app.game
        unit = g.body.weight_unit
        last = g.latest_weight()
        field = num_field(f"Weight ({unit})", suffix=unit)
        field.autofocus = True
        if last:
            field.hint_text = f"{nu.from_kg(last.kg, unit):.1f}"
        note = common.text_field("Note (optional)")
        st = {"day": app.today()}

        def save(_: Any = None) -> None:
            v = parse_num(field.value)
            if v is None or v <= 0:
                field.error_text = "Enter your weight, like 72.5"
                sfx.play("error_soft")
                field.update()
                return
            try:
                kg = nu.to_kg(v, unit)
                if not nu.MIN_WEIGHT_KG <= kg <= nu.MAX_WEIGHT_KG:
                    raise ValueError(f"Weight must be {fmt_w(nu.MIN_WEIGHT_KG, unit, 0)}–"
                                     f"{fmt_w(nu.MAX_WEIGHT_KG, unit, 0)}")
            except ValueError as exc:
                field.error_text = str(exc)
                sfx.play("error_soft")
                field.update()
                return
            common.close(sheet)

            async def go() -> None:
                c = await app.award(
                    lambda: g.log_weight(v, unit, app.today(), st["day"],
                                         (note.value or "").strip()),
                    line=lambda c: f"Notice: Weigh-in logged. +{c.xp} XP to Monk Path.")
                if not c.xp:
                    sfx.play("tap")
                    app.toast(f"Logged {v:g} {unit}", ft.Icons.MONITOR_WEIGHT)
                self._refresh()

            app.page.run_task(go)

        field.on_submit = save
        sheet = common.open_sheet(app.page, "Log weight", [
            field,
            common.date_row(app.page, "Day", st["day"], app.today(),
                            lambda d: st.update(day=d or st["day"])),
            note,
            common.hint("Same day again? It updates that day's entry."),
            ft.Row([common.primary_button("Save", save, icon=ft.Icons.CHECK)]),
        ])

    def open_stats(self, _: Any = None) -> None:
        app, g = self.app, self.app.game
        b, today = g.body, app.today()
        hunit = {"v": b.height_unit}
        cm = num_field("Height", f"{b.height_cm:g}" if b.height_cm else "", "cm")
        ft_v, in_v = nu.cm_to_ft_in(b.height_cm) if b.height_cm else (None, None)
        feet = num_field("Feet", "" if ft_v is None else str(ft_v), "ft")
        inch = num_field("Inches", "" if in_v is None else str(in_v), "in")
        imperial = ft.Row([feet, inch], spacing=Space.SM, visible=hunit["v"] == "ftin")
        cm.visible = hunit["v"] == "cm"
        age_now = g.age(today)
        age = num_field("Age or birth year", "" if age_now is None else str(age_now))
        st = {"sex": b.sex or "", "activity": b.activity}

        def set_hunit(v: str) -> None:
            sfx.play("toggle")
            hunit["v"] = v
            cm.visible, imperial.visible = v == "cm", v == "ftin"
            ui.refresh(cm, imperial)

        sex_pills = _Pills([(v, lbl, "") for v, lbl in SEX_OPTIONS], st["sex"],
                           lambda v: st.update(sex=v), cols=3)
        act_pills = _Pills([(v, *nu.ACTIVITY_LABELS[v]) for v in nu.ACTIVITY_LEVELS],
                           st["activity"], lambda v: st.update(activity=v), cols=1)

        def save(_: Any = None) -> None:
            try:
                if hunit["v"] == "cm":
                    h = parse_num(cm.value)
                else:
                    f_, i_ = parse_num(feet.value), parse_num(inch.value) or 0
                    h = nu.ft_in_to_cm(f_, i_) if f_ else None
                a = parse_num(age.value)
                g.set_body(height_cm=h if h else None, sex=st["sex"] or None,
                           activity=st["activity"], height_unit=hunit["v"])
                if a is not None:
                    g.set_age(int(a), today)
            except ValueError as exc:
                app.error(f"Check that: {exc}")
                return
            app.save()
            sfx.play("toggle")
            app.toast("Stats saved", ft.Icons.CHECK)
            common.close(sheet)
            self._refresh()

        sheet = common.open_sheet(app.page, "Your stats", [
            ft.Row([common.hint("Height unit"), ft.Container(expand=True),
                    common.segmented([("cm", "cm"), ("ftin", "ft / in")], hunit["v"],
                                     on_change=set_hunit)],
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
            cm, imperial, age,
            common.hint("Sex is only used to pick the calorie formula. 'Prefer not to say' "
                        "averages the two."),
            sex_pills.control,
            common.hint("Activity level"),
            act_pills.control,
            ft.Row([common.primary_button("Save", save, icon=ft.Icons.CHECK)]),
        ])

    def open_goal(self, _: Any = None) -> None:
        app, g = self.app, self.app.game
        today = app.today()
        st0 = g.body_status(today)
        if not st0["ready"]:
            app.error("Luma needs your " + ", ".join(st0["missing"]) + " first")
            if "weight" in st0["missing"]:
                self.open_log()
            else:
                self.open_stats()
            return
        unit = g.body.weight_unit
        cur = st0["weight_kg"]
        b = g.body
        kind0 = nu.goal_kind(cur, b.goal_kg)
        st = {"kind": kind0, "pace": b.pace}
        target = num_field(f"Target weight ({unit})",
                           f"{nu.from_kg(b.goal_kg, unit):.1f}" if b.goal_kg else "", unit)
        target.visible = kind0 != "maintain"
        lo, _hi = st0["healthy_kg"]
        safe_hint = common.hint(f"Now {fmt_w(cur, unit)}. Luma won't plan below "
                                f"{fmt_w(lo, unit)} (BMI 18.5) for your height.")

        def pace_opts(kind: str) -> list[tuple[str, str, str]]:
            if kind == "gain":
                return [(p, p.title(), f"+{nu.GAIN_SURPLUS[p]} kcal") for p in nu.PACES]
            return [(p, p.title(), f"{nu.from_kg(nu.LOSS_KG_PER_WEEK[p], unit):.2f} {unit}/wk")
                    for p in nu.PACES]

        pace_host = ft.Container()

        def build_pace() -> None:
            pace_host.content = _Pills(pace_opts(st["kind"]), st["pace"],
                                       lambda v: st.update(pace=v), cols=3).control
            pace_host.visible = st["kind"] != "maintain"

        def set_kind(v: str) -> None:
            st["kind"] = v
            target.visible = v != "maintain"
            build_pace()
            ui.refresh(target, pace_host)

        build_pace()
        kinds = _Pills([("lose", "Lose", ""), ("maintain", "Keep", ""), ("gain", "Gain", "")],
                       kind0, set_kind, cols=3)

        def generate(_: Any = None) -> None:
            goal_kg = None
            if st["kind"] != "maintain":
                v = parse_num(target.value)
                if v is None:
                    target.error_text = "Enter a target weight"
                    sfx.play("error_soft")
                    target.update()
                    return
                goal_kg = nu.to_kg(v, unit)
                if nu.goal_kind(cur, goal_kg) != st["kind"]:
                    target.error_text = (f"That's not a {'loss' if st['kind'] == 'lose' else 'gain'}"
                                         f" from {fmt_w(cur, unit)}")
                    sfx.play("error_soft")
                    target.update()
                    return
            try:
                plan = g.propose_plan(today, goal_kg, st["pace"])
            except nu.PlanRefused as exc:
                sfx.play("error_soft")
                target.error_text = None
                refusal.content = ft.Row([ft.Icon(ft.Icons.SHIELD_OUTLINED, color=C.ACCENT),
                                          ft.Text(str(exc), size=Type.CAPTION, color=C.TEXT,
                                                  expand=True)], spacing=Space.SM)
                refusal.visible = True
                ui.refresh(refusal, target)
                return
            except ValueError as exc:
                app.error(str(exc))
                return
            common.close(sheet)
            app.page.run_task(self._reveal, plan)

        refusal = ft.Container(visible=False, padding=Space.MD, border_radius=Radius.SM,
                               bgcolor=C.a(C.ACCENT, 0.12))
        sheet = common.open_sheet(app.page, "Your goal", [
            kinds.control, target, safe_hint,
            pace_host, refusal,
            common.hint("Gentle paces are easier to keep. You can change the plan any time."),
            ft.Row([common.primary_button("Generate plan", generate,
                                          icon=ft.Icons.AUTO_AWESOME)]),
        ])

    async def _reveal(self, plan: nu.PlanResult) -> None:
        """Luma's staged analysis, then the proposal card (Accept / Not now)."""
        app, g = self.app, self.app.game
        await asyncio.sleep(0.25)  # let the goal sheet slide away first
        await app.fx_think.play_staged(2.6, stages=STAGES[plan.goal])
        sfx.play("notice")
        app.notice.say("Proposal: a daily plan is ready for your review.",
                       ft.Icons.AUTO_AWESOME, "proposal")
        unit = g.body.weight_unit

        def accept(_: Any = None) -> None:
            g.accept_plan(plan, app.today())
            app.save()
            common.close(sheet)
            app.juice(BODY)
            sfx.play("quest_done", 0.5)
            app.toast("Plan saved. Meals can now compare to it.", ft.Icons.AUTO_AWESOME)
            self._refresh()

        def later(_: Any = None) -> None:
            common.close(sheet)
            app.toast("Plan not saved. Ask again any time.", ft.Icons.INFO_OUTLINE)

        sheet = common.open_sheet(app.page, "Luma's proposal", [
            plan_card(plan, unit, title="Proposal"),
            ft.Row([common.secondary_button("Not now", later),
                    common.primary_button("Accept plan", accept, icon=ft.Icons.CHECK)],
                   spacing=Space.SM),
        ])

    async def _clear_plan(self, _: Any = None) -> None:
        if not await common.confirm(self.app.page, "Clear your plan?",
                                    "Meals keep logging; they just won't compare to a target.",
                                    "Clear"):
            return
        self.app.game.clear_plan()
        self.app.save()
        self.app.toast("Plan cleared", ft.Icons.CLOSE)
        self._refresh()

    async def _delete_weight(self, wid: str) -> None:
        if not await common.confirm(self.app.page, "Delete this weigh-in?",
                                    "XP you earned stays.", "Delete", danger=True):
            return
        self.app.game.delete_weight(wid)
        self.app.save()
        self.app.toast("Weigh-in deleted", ft.Icons.DELETE_OUTLINE)
        self._refresh()
