"""More -> Meals: a daily meal log (breakfast / lunch / dinner / snack) with kcal RANGES, totals
against the Body plan (opt-in calorie tracking), history by day, favorites / recents / my foods,
and the photo scan: capture -> Luma's staged analysis -> a confirm screen (MealReviewScreen)
where every item is editable and grams from a kitchen scale override any estimate.

The scan engine is chosen in ONE place: `get_recognizer(page)` (lol.ui.vision picks the
on-device model when it can run, else core's ManualRecognizer). Photos are discarded unless the
player turns "Keep meal photos" on. Nothing here rewards eating less."""

from __future__ import annotations

import asyncio
import contextlib
import inspect
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

import flet as ft

from lol.core import foods, nutrition, storage, usda
from lol.core.body import meal_for_hour
from lol.core.foods import Food
from lol.core.models import MEAL_TYPES, MealItem
from lol.core.recognize import Candidate, ManualRecognizer, Recognizer, confidence_label
from lol.ui import components as ui
from lol.ui import sfx
from lol.ui.screens import common
from lol.ui.screens.health import MACRO_COLORS, macro_row, num_field, parse_num
from lol.ui.theme import C, Radius, Size, Space, Type

if TYPE_CHECKING:
    from lol.ui.app import App

MEAL = "#FFB86B"  # warm orange (same on every theme)
SCALE = "#5EEAB0"
MEAL_LABELS = {"breakfast": "Breakfast", "lunch": "Lunch", "dinner": "Dinner",
               "snack": "Snack"}
MEAL_ICONS = {"breakfast": ft.Icons.FREE_BREAKFAST, "lunch": ft.Icons.LUNCH_DINING,
              "dinner": ft.Icons.DINNER_DINING, "snack": ft.Icons.COOKIE}
CONF_COLORS = {"high": "#5EEAB0", "medium": "#FFC857", "low": "#B9C3D6"}
SCAN_STAGES = ("SCANNING PLATE…", "IDENTIFYING FOODS…", "ESTIMATING PORTIONS…", "READY")
SCAN_MIN_S = 2.4
SCAN_TMP = "scan_tmp.jpg"
SEARCH_DEBOUNCE_S = 0.15

# USDA FoodData Central databank (src/assets/data, built by tools/foods/build_usda.py). Attached
# once; it is only read from disk on the first lookup/search (warm_databank does that off the UI).
DATABANK_PATH = Path(__file__).resolve().parents[3] / "assets" / "data" / "usda_foods.json.gz"
DATABANK = usda.LazyUsda(DATABANK_PATH)
foods.attach(DATABANK)


async def warm_databank() -> None:
    """Load the databank on a worker thread so the first search doesn't stall a tap."""
    if not DATABANK.loaded:
        with contextlib.suppress(Exception):
            await asyncio.to_thread(lambda: DATABANK.db)


# --- the scan engine (one swappable call) ---------------------------------------------------------
def get_recognizer(page: ft.Page) -> Recognizer:
    """THE place the photo engine is chosen: on-device vision when available, else manual."""
    try:
        from lol.ui import vision

        return vision.recognizer_for(page)
    except Exception:  # noqa: BLE001 - any engine trouble falls back to picking by hand
        return ManualRecognizer()


async def run_recognizer(rec: Recognizer, image_path: str) -> list[Candidate]:
    """Async engines are awaited; sync ones run on a worker thread. Errors -> no detections."""
    try:
        fn = getattr(rec, "recognize_async", None)
        if fn is not None and inspect.iscoroutinefunction(fn):
            return list(await fn(image_path))
        return list(await asyncio.to_thread(rec.recognize, image_path))
    except Exception:  # noqa: BLE001
        return []


# --- capture --------------------------------------------------------------------------------------
def _is_phone(page: ft.Page) -> bool:
    with contextlib.suppress(Exception):
        return not page.web and page.platform in (ft.PagePlatform.ANDROID, ft.PagePlatform.IOS)
    return False


_picker: ft.FilePicker | None = None


async def pick_image(app: App) -> bytes | None:
    """Gallery / file picker (web, desktop, or when the camera is unavailable)."""
    global _picker
    if _picker is None:
        _picker = ft.FilePicker()  # a service: registers itself with the page
    try:
        files = await _picker.pick_files(dialog_title="Choose a meal photo",
                                         file_type=ft.FilePickerFileType.IMAGE, with_data=True)
    except Exception as exc:  # noqa: BLE001
        app.error(f"Couldn't open the photo picker ({exc.__class__.__name__}).")
        return None
    if not files:
        return None
    f = files[0]
    if f.bytes:
        return bytes(f.bytes)
    if f.path:
        with contextlib.suppress(OSError):
            return await asyncio.to_thread(Path(f.path).read_bytes)
    app.error("Couldn't read that photo.")
    return None


async def _camera_allowed() -> bool | None:
    """True/False from the permission handler; None if it can't tell (let the camera try)."""
    try:
        from flet_permission_handler import Permission, PermissionHandler, PermissionStatus

        ph = PermissionHandler()
        status = await ph.get_status(Permission.CAMERA)
        if status == PermissionStatus.GRANTED:
            return True
        if status in (PermissionStatus.PERMANENTLY_DENIED, PermissionStatus.RESTRICTED):
            return False
        return await ph.request(Permission.CAMERA) == PermissionStatus.GRANTED
    except Exception:  # noqa: BLE001
        return None


async def capture_camera(app: App) -> bytes | None:
    """Live camera in a sheet with a big shutter button. Falls back to the picker."""
    allowed = await _camera_allowed()
    if allowed is False:
        app.error("Camera access is off. Pick a photo instead (or allow it in Settings).")
        return await pick_image(app)
    try:
        import flet_camera as fc
    except Exception:  # noqa: BLE001
        return await pick_image(app)
    loop = asyncio.get_running_loop()
    result: asyncio.Future[bytes | None | str] = loop.create_future()
    cam = fc.Camera(expand=True, preview_enabled=True)
    status = common.hint("Starting camera…")

    def finish(value: bytes | None | str) -> None:
        if not result.done():
            result.set_result(value)

    async def shoot(_: Any = None) -> None:
        sfx.play("shutter")
        await ui.buzz("medium")
        try:
            data = await cam.take_picture()
        except Exception:  # noqa: BLE001
            app.error("Couldn't take the photo. Try again or pick one.")
            return
        common.close(sheet)
        finish(bytes(data) if data else None)

    def gallery(_: Any = None) -> None:
        common.close(sheet)
        finish("gallery")

    shutter = ft.Container(
        ft.Container(width=56, height=56, border_radius=28, bgcolor=ft.Colors.WHITE),
        width=72, height=72, border_radius=36, alignment=ft.Alignment.CENTER,
        border=ft.Border.all(4, C.a(ft.Colors.WHITE, 0.8)), on_click=shoot, tooltip="Take photo")
    sheet = common.open_sheet(app.page, "Scan your meal", [
        ft.Container(cam, height=380, border_radius=Radius.MD, bgcolor="#000000",
                     clip_behavior=ft.ClipBehavior.ANTI_ALIAS),
        status,
        ft.Row([ft.TextButton("Gallery", icon=ft.Icons.PHOTO_LIBRARY, height=Size.TAP,
                              on_click=gallery),
                shutter, ft.Container(width=96)],
               alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
               vertical_alignment=ft.CrossAxisAlignment.CENTER),
    ], on_dismiss=lambda: finish(None))
    try:
        await asyncio.sleep(0.3)  # let the Camera control mount
        cams = await cam.get_available_cameras()
        if not cams:
            raise RuntimeError("no camera")
        back = next((c for c in cams if c.lens_direction == fc.CameraLensDirection.BACK),
                    cams[0])
        await cam.initialize(back, fc.ResolutionPreset.MEDIUM, enable_audio=False)
        status.value = "Fit the whole plate in the frame."
        ui.refresh(status)
    except Exception:  # noqa: BLE001
        common.close(sheet)
        finish("gallery")
        app.toast("Camera isn't available here. Pick a photo instead.", ft.Icons.PHOTO_LIBRARY)
    got = await result
    if got == "gallery":
        return await pick_image(app)
    return got if isinstance(got, bytes) else None


async def capture(app: App) -> bytes | None:
    if _is_phone(app.page):
        return await capture_camera(app)
    return await pick_image(app)


# --- small pieces ---------------------------------------------------------------------------------
def kcal_text(lo: float, hi: float) -> str:
    if round(lo) == round(hi):
        return f"~{lo:,.0f} kcal"
    return f"~{lo:,.0f}–{hi:,.0f} kcal"


BADGES = {foods.USDA: ("USDA", C.TEXT_DIM), foods.ESTIMATE: ("est.", C.ACCENT),
          foods.OFFICIAL: ("official", SCALE), foods.CUSTOM: ("mine", MEAL)}


def source_badge(f: Food) -> ft.Control:
    label, color = BADGES.get(f.source, (f.source, C.TEXT_DIM))
    return ui.chip(label, color=color, dim=False)


def source_line(f: Food) -> str:
    """Where an item's numbers come from, in words."""
    if f.source == foods.USDA:
        return "USDA FoodData Central" + (f" · FDC {f.fdc_id}" if f.fdc_id else "")
    if f.source == foods.OFFICIAL:
        return f"{f.brand} published values (serving weight estimated)"
    if f.source == foods.ESTIMATE and f.brand:
        return f"Estimate - {f.brand} publishes no nutrition; built from USDA foods"
    if f.source == foods.ESTIMATE:
        return "Estimate - typical recipe, varies by cook"
    return "Your own food"


def today_chip(app: App) -> ft.Control | None:
    """Today: a small 'kcal left' chip (opt-in; needs a plan + calorie tracking)."""
    g = app.game
    if not (g.module_on("meals") and g.profile.nutrition.today_chip):
        return None
    left = g.kcal_left(app.today())
    if left is None:
        return None
    lo, hi = left["left_low"], left["left_high"]
    if hi <= 0:
        text = f"Plan reached today ({left['target']:,} kcal)"
    elif lo <= 0:
        text = f"Up to ~{hi:,} kcal left today"
    else:
        text = f"{kcal_text(lo, hi)} left today"
    return ft.Container(
        ft.Row([ft.Icon(ft.Icons.RESTAURANT, size=18, color=MEAL),
                ft.Text(text, size=Type.LABEL, weight=ft.FontWeight.W_600, color=C.TEXT,
                        expand=True),
                ft.Icon(ft.Icons.CHEVRON_RIGHT, size=18, color=C.TEXT_DIM)],
               spacing=Space.SM, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        height=Size.TAP, border_radius=Radius.PILL, bgcolor=C.a(MEAL, 0.12),
        border=ft.Border.all(1, C.a(MEAL, 0.4)),
        padding=ft.Padding.symmetric(horizontal=Space.MD), ink=True,
        on_click=lambda e: app.open_sub("meals"))


def food_row(app: App, f: Food, on_pick: Any, on_star: Any | None = None) -> ft.Control:
    g = app.game
    star = g.is_favorite(f.id)
    lo, hi = nutrition.kcal_range(nutrition.scaled(f.kcal, f.portion_g), f.uncertainty, False)
    sub = f"{f.portion_label} ({f.portion_g:g} g) · {kcal_text(lo, hi)}"
    star_btn = ft.IconButton(ft.Icons.STAR if star else ft.Icons.STAR_BORDER,
                             icon_color=C.ACCENT if star else C.TEXT_DIM, width=Size.TAP,
                             height=Size.TAP, tooltip="Favorite")

    def toggle(_: Any) -> None:
        now = g.toggle_favorite(f.id)
        app.save()
        sfx.play("toggle")
        star_btn.icon = ft.Icons.STAR if now else ft.Icons.STAR_BORDER
        star_btn.icon_color = C.ACCENT if now else C.TEXT_DIM
        ui.refresh(star_btn)
        if on_star:
            on_star()

    star_btn.on_click = toggle
    return ft.Container(
        ft.Row([ft.Column([ft.Text(f.name, size=Type.BODY, weight=ft.FontWeight.W_600,
                                   color=C.TEXT, max_lines=2,
                                   overflow=ft.TextOverflow.ELLIPSIS),
                           ft.Row([source_badge(f),
                                   ft.Text(sub, size=Type.CAPTION, color=C.TEXT_DIM,
                                           expand=True, max_lines=1,
                                           overflow=ft.TextOverflow.ELLIPSIS)],
                                  spacing=Space.XS)],
                          spacing=2, expand=True, tight=True),
                star_btn], spacing=Space.XS, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        padding=ft.Padding.only(left=Space.MD, top=Space.XS, bottom=Space.XS),
        border_radius=Radius.SM, bgcolor=C.a(C.SURFACE_HI, 0.6), ink=True,
        on_click=lambda e: on_pick(f.id))


def food_picker(app: App, on_pick: Any, meal: str = "snack", title: str = "Add food") -> None:
    """Search sheet: fuzzy search, favorites, recents, suggestions, and 'create my food'."""
    g = app.game
    app.page.run_task(warm_databank)
    results = ft.Column(spacing=Space.XS, tight=True)
    search = common.text_field("Search foods (e.g. adobo, kanin, Chickenjoy)", autofocus=True)
    search.prefix_icon = ft.Icons.SEARCH
    st: dict[str, Any] = {"brand": "", "gen": 0}

    def pick(fid: str) -> None:
        sfx.play("tap")
        common.close(sheet)
        on_pick(fid)

    def group(title_: str, rows: list[Food]) -> list[ft.Control]:
        if not rows:
            return []
        return [common.section(title_), *[food_row(app, f, pick) for f in rows]]

    def paint(_: Any = None) -> None:
        q = (search.value or "").strip()
        brand = st["brand"]
        if brand:
            hits = g.search_foods(q, 60, brand=brand)
            note = next((source_line(f) for f in hits if f.source == foods.ESTIMATE), "")
            results.controls = ([common.hint(note)] if note else []) + (
                [food_row(app, f, pick) for f in hits] if hits else
                [common.hint(f"No {brand} item matches '{q}'.")])
        elif q:
            hits = g.search_foods(q, 25)
            results.controls = ([food_row(app, f, pick) for f in hits] if hits else [
                common.hint(f"No match for '{q}'. Create it as your own food below.")])
        else:
            fav = g.favorite_foods()
            recent = [g.food_info(i) for i in g.recent_food_ids(8) if g.has_food(i)]
            seen = {f.id for f in fav} | {f.id for f in recent}
            sug = [f for f in (g.food_info(i) for i in foods.suggestions_for(meal))
                   if f.id not in seen]
            results.controls = (group("Favorites", fav) + group("Recent", recent)
                                + group(f"Ideas for {MEAL_LABELS[meal].lower()}", sug))
        ui.refresh(results)

    async def typed(_: Any = None) -> None:  # debounce: search once typing pauses
        st["gen"] += 1
        gen = st["gen"]
        await asyncio.sleep(SEARCH_DEBOUNCE_S)
        if gen == st["gen"]:
            paint()

    search.on_change = typed

    def set_brand(value: str) -> None:
        st["brand"] = value
        paint()

    brand_pills = common.ChoicePills(
        [("", "All foods", ft.Icons.SEARCH, MEAL)]
        + [(b, b, ft.Icons.STOREFRONT, MEAL) for b in foods.brands()],
        "", on_change=set_brand, grid_cols=0)

    def create(_: Any = None) -> None:
        common.close(sheet)
        custom_food_sheet(app, on_pick, (search.value or "").strip())

    paint()
    sheet = common.open_sheet(app.page, title, [
        search, common.hint("Restaurants"), brand_pills, results,
        ft.Row([common.secondary_button("Create my own food", create, icon=ft.Icons.ADD)]),
        common.hint("USDA = USDA FoodData Central values. official = the chain's own published "
                    "numbers. est. = estimate (home recipe, or a chain that publishes nothing), "
                    "so its range is wider."),
    ])


def custom_food_sheet(app: App, on_created: Any | None, name: str = "") -> None:
    g = app.game
    nm = common.text_field("Name")
    nm.value = name
    kcal = num_field("kcal per 100 g")
    pro = num_field("Protein g", width=None)
    carb = num_field("Carbs g")
    fat = num_field("Fat g")
    portion = num_field("Usual portion", "100", "g")
    label = common.text_field("Portion name (e.g. 1 bowl)")

    def save(_: Any = None) -> None:
        try:
            cf = g.add_custom_food(nm.value or "", parse_num(kcal.value) or 0,
                                   parse_num(pro.value) or 0, parse_num(carb.value) or 0,
                                   parse_num(fat.value) or 0, parse_num(portion.value) or 100,
                                   label.value or "1 serving")
        except ValueError as exc:
            app.error(str(exc).capitalize())
            return
        app.save()
        sfx.play("toggle")
        app.toast(f"Saved to My foods: {cf.name}", ft.Icons.BOOKMARK_ADDED)
        common.close(sheet)
        if on_created:
            on_created(cf.id)

    sheet = common.open_sheet(app.page, "My food", [
        nm, kcal, ft.Row([pro, carb, fat], spacing=Space.SM), ft.Row([portion]), label,
        common.hint("Use the label on the pack, or your own recipe. Values are per 100 g."),
        ft.Row([common.primary_button("Save food", save, icon=ft.Icons.CHECK)]),
    ])


# --- the meal log ----------------------------------------------------------------------------------
class MealScreen:
    title = "Meals"

    def __init__(self, app: App) -> None:
        self.app = app
        self.day = app.today()
        self.list = common.screen_list()
        self.view = ft.Container(self.list, expand=True, key="meals")
        self.fab = ft.FloatingActionButton(icon=ft.Icons.PHOTO_CAMERA, on_click=self.scan,
                                           bgcolor=C.PRIMARY, foreground_color=C.ON_PRIMARY,
                                           tooltip="Scan a meal")
        self._busy = False

    def prepare(self, day: date | None = None, **_: object) -> None:
        if day is not None:
            self.day = day

    def on_enter(self) -> None:
        self.day = min(self.day, self.app.today())
        self.app.page.run_task(warm_databank)

    def _refresh(self) -> None:
        self.render()
        ui.refresh(self.list)

    def restyle(self) -> None:
        self._refresh()

    def _shift(self, days: int) -> None:
        new = self.day + timedelta(days=days)
        if new > self.app.today():
            sfx.play("error_soft")
            return
        sfx.play("tap")
        self.day = new
        self._refresh()

    # ------------------------------------------------------------------ render
    def render(self) -> None:
        g = self.app.game
        tracking = g.profile.nutrition.calorie_tracking
        items: list[ft.Control] = [self._day_nav(), self._summary(tracking),
                                   ft.Row([
                                       common.primary_button("Scan meal", self.scan,
                                                             icon=ft.Icons.PHOTO_CAMERA),
                                       common.secondary_button("Add food", self._add_quick,
                                                               icon=ft.Icons.ADD)],
                                       spacing=Space.SM)]
        meals = g.meals_on(self.day)
        for mt in MEAL_TYPES:
            rows = [m for m in meals if m.meal == mt]
            items.append(self._meal_header(mt, rows, tracking))
            items += [self._meal_card(m.id, tracking) for m in rows]
        items += [common.section("Last 7 days"), self._history(tracking),
                  common.section("Settings"), self._settings(), common.section("My foods"),
                  self._my_foods()]
        self.list.controls = items

    def _day_nav(self) -> ft.Control:
        today = self.app.today()
        label = ("Today" if self.day == today else
                 "Yesterday" if self.day == today - timedelta(days=1) else
                 f"{self.day:%a}")
        return ft.Row([
            ft.IconButton(ft.Icons.CHEVRON_LEFT, width=Size.TAP, height=Size.TAP,
                          icon_color=C.TEXT, tooltip="Previous day",
                          on_click=lambda e: self._shift(-1)),
            ft.Column([ft.Text(label, size=Type.TITLE, weight=ft.FontWeight.W_800,
                               color=C.TEXT),
                       common.hint(common.long_date(self.day))], spacing=0, tight=True,
                      expand=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            ft.IconButton(ft.Icons.CHEVRON_RIGHT, width=Size.TAP, height=Size.TAP,
                          icon_color=C.TEXT if self.day < today else C.a(C.TEXT, 0.2),
                          tooltip="Next day", on_click=lambda e: self._shift(1)),
        ], vertical_alignment=ft.CrossAxisAlignment.CENTER)

    def _summary(self, tracking: bool) -> ft.Control:
        g = self.app.game
        t = g.day_totals(self.day)
        n_meals = len(g.meals_on(self.day))
        if not tracking:
            return common.card(ft.Column([
                ft.Row([ft.Icon(ft.Icons.RESTAURANT, color=MEAL),
                        ft.Text(f"{n_meals} meal{'s' if n_meals != 1 else ''} · "
                                f"{int(t['count'])} food{'s' if t['count'] != 1 else ''}",
                                size=Type.TITLE, weight=ft.FontWeight.W_800, color=C.TEXT)],
                       spacing=Space.SM),
                common.hint("A plain meal log. Calorie tracking is optional - turn it on to "
                            "see daily kcal ranges and macros."),
                common.switch_row("Calorie tracking", "Daily ranges vs your plan", False,
                                  self._set_tracking, icon=ft.Icons.LOCAL_FIRE_DEPARTMENT),
            ], spacing=Space.SM, tight=True), tint=MEAL)
        plan = g.body.plan
        rng = kcal_text(t["kcal_low"], t["kcal_high"]) if t["count"] else "nothing logged yet"
        if plan is None:
            return common.card(ft.Column([
                ft.Row([ft.Text(f"{t['kcal']:,.0f}", size=Type.DISPLAY,
                                weight=ft.FontWeight.W_900, color=C.TEXT),
                        ft.Column([ft.Text("kcal (mid)", color=C.TEXT, size=Type.LABEL),
                                   common.hint(rng)], spacing=0, tight=True)],
                       spacing=Space.SM),
                common.hint(f"Protein {t['protein']:.0f} g · Carbs {t['carbs']:.0f} g · "
                            f"Fat {t['fat']:.0f} g"),
                ft.Row([common.secondary_button("Get a plan in Body", lambda e:
                                                self.app.more.open("body"),
                                                icon=ft.Icons.AUTO_AWESOME)]),
            ], spacing=Space.SM, tight=True), tint=MEAL)
        target = plan.target_kcal
        prog = t["kcal"] / target if target else 0
        center = ft.Column([
            ft.Text(f"{t['kcal']:,.0f}", size=Type.HEADLINE, weight=ft.FontWeight.W_900,
                    color=C.TEXT),
            common.hint(f"of {target:,} kcal"),
        ], spacing=0, tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
        left_lo, left_hi = target - t["kcal_high"], target - t["kcal_low"]
        left = ("Plan reached for today" if left_hi <= 0 else
                f"{kcal_text(max(0, left_lo), left_hi)} left")
        return common.card(ft.Column([
            ft.Row([common.progress_ring(min(1.0, prog), center, size=118, color=MEAL),
                    ft.Column([ft.Text(left, size=Type.BODY, weight=ft.FontWeight.W_700,
                                       color=C.TEXT),
                               common.hint(f"Eaten {rng}"),
                               common.hint(f"Plan {plan.kcal_low:,}–{plan.kcal_high:,}")],
                              spacing=2, tight=True, expand=True)],
                   spacing=Space.LG, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            macro_row("Protein", plan.protein_g, 4, target, MACRO_COLORS["protein"],
                      t["protein"]),
            macro_row("Carbs", plan.carbs_g, 4, target, MACRO_COLORS["carbs"], t["carbs"]),
            macro_row("Fat", plan.fat_g, 9, target, MACRO_COLORS["fat"], t["fat"]),
        ], spacing=Space.SM, tight=True), tint=MEAL)

    def _meal_header(self, mt: str, rows: list, tracking: bool) -> ft.Control:
        g = self.app.game
        t = g.totals(it for m in rows for it in m.items)
        extra = (kcal_text(t["kcal_low"], t["kcal_high"]) if tracking and t["count"] else
                 f"{int(t['count'])} item{'s' if t['count'] != 1 else ''}" if t["count"] else "")
        return ft.Row([
            ft.Icon(MEAL_ICONS[mt], color=MEAL, size=20),
            ft.Text(MEAL_LABELS[mt], size=Type.BODY, weight=ft.FontWeight.W_700, color=C.TEXT),
            ft.Text(extra, size=Type.CAPTION, color=C.TEXT_DIM, expand=True),
            ft.IconButton(ft.Icons.ADD_CIRCLE_OUTLINE, icon_color=MEAL, width=Size.TAP,
                          height=Size.TAP, tooltip=f"Add to {MEAL_LABELS[mt].lower()}",
                          on_click=lambda e, m=mt: self._open_review(meal=m, search=True)),
        ], spacing=Space.SM, vertical_alignment=ft.CrossAxisAlignment.CENTER)

    def _meal_card(self, meal_id: str, tracking: bool) -> ft.Control:
        g = self.app.game
        m = g.meal(meal_id)
        lines: list[ft.Control] = []
        for it in m.items:
            right = kcal_text(it.kcal_low, it.kcal_high) if tracking else ""
            lines.append(ft.Row([
                ft.Text(it.name, size=Type.LABEL, color=C.TEXT, expand=True, max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS),
                *([ft.Icon(ft.Icons.SCALE, size=14, color=SCALE, tooltip="From scale")]
                  if it.from_scale else []),
                ft.Text(f"{it.grams:g} g", size=Type.CAPTION, color=C.TEXT_DIM),
                *([ft.Text(right, size=Type.CAPTION, color=C.TEXT_DIM)] if right else []),
            ], spacing=Space.SM, vertical_alignment=ft.CrossAxisAlignment.CENTER))
        head = ft.Row([
            common.hint(" · ".join(x for x in (m.time, m.note) if x)),
            ft.Container(expand=True),
            *([ft.Icon(ft.Icons.PHOTO, size=16, color=C.TEXT_DIM)] if m.photo else []),
            common.menu_button([
                ("Edit", ft.Icons.EDIT, lambda: self._open_review(meal_id=meal_id)),
                ("Delete", ft.Icons.DELETE_OUTLINE, lambda: self._delete(meal_id), True),
            ], tooltip="Meal options"),
        ], vertical_alignment=ft.CrossAxisAlignment.CENTER, height=Size.TAP)
        body = ft.Container(ft.Column(lines, spacing=4, tight=True),
                            padding=ft.Padding.only(right=Space.MD))
        return common.card(ft.Column([head, body], spacing=4, tight=True),
                           padding=ft.Padding.only(left=Space.MD, right=Space.XS,
                                                   bottom=Space.MD),
                           on_click=lambda e: self._open_review(meal_id=meal_id))

    def _history(self, tracking: bool) -> ft.Control:
        g, today = self.app.game, self.app.today()
        hist = g.meal_history(today - timedelta(days=6), today)
        if tracking:
            rows = [(f"{date.fromisoformat(d):%a}"[:2], float(k), f"{k:,}" if k else "–")
                    for d, k, _lo, _hi, _n in hist]
            goal = g.body.plan.target_kcal if g.body.plan else None
            chart = common.bar_chart(rows, color=MEAL, goal=goal,
                                     empty="No meals logged this week.")
            note = "kcal per day (mid of each range)" + (" · line = plan" if goal else "")
        else:
            rows = [(f"{date.fromisoformat(d):%a}"[:2], float(n), str(n) if n else "–")
                    for d, _k, _lo, _hi, n in hist]
            chart = common.bar_chart(rows, color=MEAL, empty="No meals logged this week.")
            note = "meals logged per day"
        return common.card(ft.Column([chart, common.hint(note + ". Just a record - no streaks,"
                                                         " no targets to beat.")],
                                     spacing=Space.SM, tight=True))

    def _settings(self) -> ft.Control:
        g = self.app.game
        n = g.profile.nutrition
        return common.card(ft.Column([
            common.switch_row("Calorie tracking", "Daily kcal ranges and macros (opt-in)",
                              n.calorie_tracking, self._set_tracking,
                              icon=ft.Icons.LOCAL_FIRE_DEPARTMENT),
            common.switch_row("Kcal left on Today", "Needs a plan and calorie tracking",
                              n.today_chip, self._set_chip, icon=ft.Icons.TODAY),
            common.switch_row("Keep meal photos", "Off: photos are discarded after a scan",
                              n.keep_photos, self._set_photos, icon=ft.Icons.PHOTO),
        ], spacing=Space.SM, tight=True))

    def _my_foods(self) -> ft.Control:
        g = self.app.game
        mine = g.my_foods()
        rows: list[ft.Control] = []
        for f in mine:
            rows.append(ft.Row([
                ft.Column([ft.Text(f.name, size=Type.BODY, color=C.TEXT,
                                   weight=ft.FontWeight.W_600),
                           common.hint(f"{f.kcal:g} kcal / 100 g · {f.portion_label} "
                                       f"({f.portion_g:g} g)")],
                          spacing=0, tight=True, expand=True),
                common.menu_button([("Delete", ft.Icons.DELETE_OUTLINE,
                                     lambda fid=f.id: self._delete_food(fid), True)],
                                   tooltip="Food options"),
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER))
        if not rows:
            rows.append(common.hint("Your own recipes and packaged foods live here."))
        rows.append(ft.Row([common.secondary_button(
            "New food", lambda e: custom_food_sheet(self.app, lambda fid: self._refresh()),
            icon=ft.Icons.ADD)]))
        return common.card(ft.Column(rows, spacing=Space.SM, tight=True))

    # ------------------------------------------------------------------ actions
    def _set_tracking(self, on: bool) -> None:
        self.app.game.set_nutrition(calorie_tracking=on)
        self.app.save()
        self.app.toast("Calorie tracking on" if on else "Calorie tracking off. Your log stays.",
                       ft.Icons.LOCAL_FIRE_DEPARTMENT)
        self._refresh()

    def _set_chip(self, on: bool) -> None:
        g = self.app.game
        g.set_nutrition(today_chip=on)
        self.app.save()
        if on and (g.body.plan is None or not g.profile.nutrition.calorie_tracking):
            self.app.toast("Shows once you have a plan and calorie tracking is on",
                           ft.Icons.INFO_OUTLINE)

    def _set_photos(self, on: bool) -> None:
        self.app.game.set_nutrition(keep_photos=on)
        self.app.save()

    def _add_quick(self, _: Any = None) -> None:
        self._open_review(meal=meal_for_hour(datetime.now().hour), search=True)

    def _open_review(self, *, meal: str | None = None, meal_id: str | None = None,
                     search: bool = False, items: list[MealItem] | None = None,
                     photo: bytes | None = None, scanned: bool = False,
                     engine: str = "") -> None:
        self.app.more.open("meal_review", day=self.day, meal=meal, meal_id=meal_id,
                           search=search, items=items, photo=photo, scanned=scanned,
                           engine=engine, on_saved=self._refresh)

    async def scan(self, _: Any = None) -> None:
        if self._busy:
            return
        self._busy = True
        try:
            app = self.app
            data = await capture(app)
            if not data:
                return
            sfx.play("shutter")
            rec = get_recognizer(app.page)
            path = str(storage.data_dir() / SCAN_TMP)
            await asyncio.to_thread(Path(path).write_bytes, data)
            cands: list[Candidate] = []
            ticker = app.page.run_task(self._ticks)
            try:
                async with app.fx_think.session(SCAN_STAGES[0], min_s=SCAN_MIN_S,
                                                stages=SCAN_STAGES):
                    cands = await run_recognizer(rec, path)
            finally:
                with contextlib.suppress(Exception):
                    ticker.cancel()
                with contextlib.suppress(OSError):
                    storage.data_dir().joinpath(SCAN_TMP).unlink()
            sfx.play("scan_done")
            items = app.game.items_from_candidates(cands)
            self._open_review(meal=meal_for_hour(datetime.now().hour), items=items,
                              photo=data, scanned=True, engine=rec.name)
        finally:
            self._busy = False

    async def _ticks(self) -> None:
        """scan_tick on each analysis stage (the overlay advances over SCAN_MIN_S)."""
        step = SCAN_MIN_S / (len(SCAN_STAGES) - 1)
        for _ in SCAN_STAGES[:-1]:
            sfx.play("scan_tick")
            await asyncio.sleep(step)

    async def _delete(self, meal_id: str) -> None:
        if not await common.confirm(self.app.page, "Delete this meal?",
                                    "It leaves your log. XP you earned stays.", "Delete",
                                    danger=True):
            return
        m = self.app.game.delete_meal(meal_id)
        if m.photo:
            with contextlib.suppress(OSError):
                storage.delete_photo(m.photo)
        self.app.save()
        self.app.toast("Meal deleted", ft.Icons.DELETE_OUTLINE)
        self._refresh()

    async def _delete_food(self, food_id: str) -> None:
        if not await common.confirm(self.app.page, "Delete this food?",
                                    "Meals that used it keep their numbers.", "Delete",
                                    danger=True):
            return
        self.app.game.delete_custom_food(food_id)
        self.app.save()
        self._refresh()


# --- confirm / edit a meal ------------------------------------------------------------------------
class MealReviewScreen:
    """The confirm card: every item editable (food, grams, scale badge, portion presets,
    delete), add more, then Save. Opened by a scan, 'Add food' or editing a meal."""

    title = "Review meal"

    def __init__(self, app: App) -> None:
        self.app = app
        self.list = common.screen_list()
        self.view = ft.Container(self.list, expand=True, key="meal_review")
        self.items: list[MealItem] = []
        self.meal = "lunch"
        self.day = app.today()
        self.meal_id: str | None = None
        self.photo: bytes | None = None
        self.scanned = False
        self.engine = ""
        self.detected = 0  # items the recognizer found (the rest the player added)
        self.on_saved: Any = None
        self._search = False
        self.trailing = ft.TextButton("Save", icon=ft.Icons.CHECK, height=Size.TAP,
                                      on_click=self.save)

    def prepare(self, *, day: date | None = None, meal: str | None = None,
                meal_id: str | None = None, search: bool = False,
                items: list[MealItem] | None = None, photo: bytes | None = None,
                scanned: bool = False, engine: str = "", on_saved: Any = None,
                **_: object) -> None:
        g = self.app.game
        self.meal_id, self.photo, self.scanned, self.engine = meal_id, photo, scanned, engine
        self.detected = len(items or []) if scanned else 0
        self.on_saved = on_saved
        self.day = day or self.app.today()
        if meal_id:
            m = g.meal(meal_id)
            self.items = [MealItem(**vars(i)) for i in m.items]
            self.meal, self.day = m.meal, date.fromisoformat(m.day)
            self.title = "Edit meal"
        else:
            self.items = list(items or [])
            self.meal = meal or meal_for_hour(datetime.now().hour)
            self.title = "Confirm meal" if scanned else "Add meal"
        self._search = search

    def on_enter(self) -> None:
        if self._search:
            self._search = False
            self.add_food()

    def _refresh(self) -> None:
        self.render()
        ui.refresh(self.list)

    def restyle(self) -> None:
        self._refresh()

    def render(self) -> None:
        g = self.app.game
        items: list[ft.Control] = []
        if self.photo:
            with contextlib.suppress(Exception):
                items.append(ft.Container(
                    ft.Image(src=self.photo, fit=ft.BoxFit.COVER, height=170),
                    height=170, border_radius=Radius.MD,
                    clip_behavior=ft.ClipBehavior.ANTI_ALIAS))
        pills = common.ChoicePills(
            [(m, MEAL_LABELS[m], MEAL_ICONS[m], MEAL) for m in MEAL_TYPES], self.meal,
            on_change=lambda v: setattr(self, "meal", v), grid_cols=2)
        items.append(pills)
        if self.scanned and not self.items:
            items.append(self._no_detection())
        elif self.scanned and self.detected:
            items.append(common.hint(
                f"Luma ({self.engine or 'scan'}) found {self.detected} item"
                f"{'s' if self.detected != 1 else ''}. Check each one - grams from your "
                "scale beat any guess."))
        elif self.scanned:
            items.append(common.hint("Luma couldn't identify this photo, so you picked the "
                                     "foods. Grams from a scale give the tightest range."))
        elif not self.items:
            items.append(self._suggestions("Quick picks"))
        for i, it in enumerate(self.items):
            items.append(self._item_card(i, it))
        t = g.totals(self.items)
        items.append(ft.Row([common.secondary_button("Add food", self.add_food,
                                                     icon=ft.Icons.ADD)]))
        if self.items:
            items.append(common.card(ft.Column([
                ft.Row([ft.Text("Meal total", size=Type.BODY, weight=ft.FontWeight.W_700,
                                color=C.TEXT, expand=True),
                        ft.Text(kcal_text(t["kcal_low"], t["kcal_high"]), size=Type.BODY,
                                weight=ft.FontWeight.W_700, color=MEAL)]),
                common.hint(f"Protein {t['protein']:.0f} g · Carbs {t['carbs']:.0f} g · "
                            f"Fat {t['fat']:.0f} g"),
            ], spacing=2, tight=True), tint=MEAL))
        if self.photo and not self.meal_id:
            keep = g.profile.nutrition.keep_photos
            items.append(common.hint("The photo will be kept with this meal." if keep else
                                     "The photo is discarded when you save (Settings in "
                                     "Meals can keep it)."))
        items.append(ft.Row([common.primary_button("Save meal", self.save,
                                                   icon=ft.Icons.CHECK)]))
        self.list.controls = items

    def _no_detection(self) -> ft.Control:
        return common.card(ft.Column([
            ft.Row([ft.Icon(ft.Icons.AUTO_AWESOME, color=MEAL),
                    ft.Text("Luma couldn't identify this - pick foods", size=Type.BODY,
                            weight=ft.FontWeight.W_700, color=C.TEXT, expand=True)],
                   spacing=Space.SM),
            common.hint("Tap a quick pick or search. Weigh it on a scale for the best range."),
            self._suggestions(None),
        ], spacing=Space.SM, tight=True), tint=MEAL)

    def _suggestions(self, title: str | None) -> ft.Control:
        g = self.app.game
        chips: list[ft.Control] = []
        for f in g.food_suggestions(self.meal, 8):
            chips.append(ft.Container(
                ft.Text(f.name.split(" (")[0], size=Type.LABEL, color=C.TEXT,
                        weight=ft.FontWeight.W_600, max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS),
                border_radius=Radius.PILL, bgcolor=C.a(MEAL, 0.12),
                border=ft.Border.all(1, C.a(MEAL, 0.4)),
                padding=ft.Padding.symmetric(horizontal=Space.MD, vertical=14), ink=True,
                on_click=lambda e, fid=f.id: self._add(fid)))
        body: list[ft.Control] = [ft.Row(chips, wrap=True, spacing=Space.SM,
                                         run_spacing=Space.SM)]
        if title:
            body.insert(0, common.hint(title))
        return ft.Column(body, spacing=Space.SM, tight=True)

    def _item_card(self, i: int, it: MealItem) -> ft.Control:
        g = self.app.game
        unknown = it.food_id is None and it.source == "scan"
        f = g.food_info(it.food_id) if it.food_id and g.has_food(it.food_id) else None
        chips: list[ft.Control] = []
        if not unknown:
            chips.append(ui.chip(kcal_text(it.kcal_low, it.kcal_high), color=MEAL))
        if it.confidence is not None:
            lbl = confidence_label(it.confidence)
            chips.append(ui.chip(f"{lbl} confidence", color=CONF_COLORS[lbl]))
        if it.from_scale:
            chips.append(ui.chip("from scale", icon=ft.Icons.SCALE, color=SCALE))
        grams = num_field("Grams", f"{it.grams:g}", "g", width=120)
        grams.on_submit = grams.on_blur = lambda e, k=i: self._set_grams(k, e.control.value)
        scale_btn = ft.Container(
            ft.Row([ft.Icon(ft.Icons.SCALE, size=18,
                            color=SCALE if it.from_scale else C.TEXT_DIM),
                    ft.Text("Scale", size=Type.LABEL, weight=ft.FontWeight.W_600,
                            color=SCALE if it.from_scale else C.TEXT_DIM)],
                   spacing=4, tight=True, alignment=ft.MainAxisAlignment.CENTER),
            height=Size.TAP, border_radius=Radius.PILL, alignment=ft.Alignment.CENTER,
            padding=ft.Padding.symmetric(horizontal=Space.MD),
            bgcolor=C.a(SCALE, 0.14) if it.from_scale else C.a(C.TEXT, 0.05),
            border=ft.Border.all(1, C.a(SCALE, 0.5) if it.from_scale else C.a(C.TEXT, 0.1)),
            tooltip="Weighed on a kitchen scale", on_click=lambda e, k=i: self._toggle_scale(k))
        presets: list[ft.Control] = []
        if f is not None:
            for name, mult in nutrition.PORTION_PRESETS:
                g_ = round(f.portion_g * mult)
                on = abs(it.grams - g_) < 0.5 and not it.from_scale
                presets.append(ft.Container(
                    ft.Column([ft.Text(name[0].upper(), size=Type.LABEL,
                                       weight=ft.FontWeight.W_800,
                                       color=MEAL if on else C.TEXT),
                               ft.Text(f"{g_} g", size=9, color=C.TEXT_DIM)],
                              spacing=0, tight=True,
                              horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    width=Size.TAP, height=Size.TAP, border_radius=Radius.SM,
                    alignment=ft.Alignment.CENTER, tooltip=f"{name} ({g_} g)",
                    bgcolor=C.a(MEAL, 0.18) if on else C.a(C.TEXT, 0.05),
                    on_click=lambda e, k=i, gg=g_: self._preset(k, gg)))
        name_row = ft.Row([
            ft.Container(
                ft.Column([
                    ft.Text(it.name, size=Type.BODY, weight=ft.FontWeight.W_700,
                            color=C.ACCENT if unknown else C.TEXT, max_lines=2,
                            overflow=ft.TextOverflow.ELLIPSIS),
                    common.hint("Tap to pick the matching food" if unknown else
                                (f"{f.portion_label} = {f.portion_g:g} g · tap to change"
                                 if f else "Your own item")),
                    *([common.hint(source_line(f))] if f and not unknown else []),
                ], spacing=0, tight=True),
                expand=True, on_click=lambda e, k=i: self._replace(k), ink=True,
                padding=ft.Padding.symmetric(vertical=4), border_radius=Radius.SM),
            ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_color=C.TEXT_DIM, width=Size.TAP,
                          height=Size.TAP, tooltip="Remove item",
                          on_click=lambda e, k=i: self._remove(k)),
        ], vertical_alignment=ft.CrossAxisAlignment.START)
        body: list[ft.Control] = [name_row]
        if chips:
            body.append(ft.Row(chips, wrap=True, spacing=Space.XS, run_spacing=Space.XS))
        if not unknown:
            body.append(ft.Row([grams, scale_btn], spacing=Space.SM,
                               vertical_alignment=ft.CrossAxisAlignment.CENTER))
            if presets:
                body.append(ft.Row([common.hint("Portion"), *presets], spacing=Space.XS,
                                   vertical_alignment=ft.CrossAxisAlignment.CENTER))
            if f is not None and len(f.portions) > 1:  # USDA household measures
                body.append(ft.Row([self._measure(i, lbl, gg) for lbl, gg in f.portions[:4]],
                                   wrap=True, spacing=Space.XS, run_spacing=Space.XS))
            body.append(common.hint(f"P {it.protein:.0f} g · C {it.carbs:.0f} g · "
                                    f"F {it.fat:.0f} g"))
        return common.card(ft.Column(body, spacing=Space.SM, tight=True),
                           padding=ft.Padding.only(left=Space.MD, right=Space.XS,
                                                   top=Space.SM, bottom=Space.MD),
                           tint=C.ACCENT if unknown else None)

    # ------------------------------------------------------------------ item edits
    def _regram(self, i: int, grams: float, from_scale: bool) -> bool:
        try:
            self.items[i] = self.app.game.regram(self.items[i], grams, from_scale)
        except ValueError as exc:
            self.app.error(str(exc).capitalize())
            return False
        return True

    def _set_grams(self, i: int, text: str | None) -> None:
        if i >= len(self.items):
            return
        v = parse_num(text)
        it = self.items[i]
        if v is None or abs(v - it.grams) < 0.05:
            return
        # typed grams are treated as weighed (they override any estimate)
        if self._regram(i, v, True):
            sfx.play("tap")
            self._refresh()

    def _toggle_scale(self, i: int) -> None:
        it = self.items[i]
        if self._regram(i, it.grams, not it.from_scale):
            sfx.play("toggle")
            self._refresh()

    def _measure(self, i: int, label: str, grams: float) -> ft.Control:
        on = abs(self.items[i].grams - grams) < 0.5 and not self.items[i].from_scale
        return ft.Container(
            ft.Text(f"{label} · {grams:g} g", size=Type.CAPTION, weight=ft.FontWeight.W_600,
                    color=MEAL if on else C.TEXT, max_lines=1,
                    overflow=ft.TextOverflow.ELLIPSIS),
            padding=ft.Padding.symmetric(horizontal=Space.MD, vertical=14),
            border_radius=Radius.PILL, bgcolor=C.a(MEAL, 0.18) if on else C.a(C.TEXT, 0.05),
            on_click=lambda e, k=i, gg=grams: self._preset(k, gg))

    def _preset(self, i: int, grams: float) -> None:
        if self._regram(i, grams, False):
            sfx.play("tap")
            self._refresh()

    def _remove(self, i: int) -> None:
        sfx.play("tap")
        removed = self.items.pop(i)
        self.app.toast(f"Removed {removed.name}", ft.Icons.DELETE_OUTLINE)
        self._refresh()

    def _add(self, food_id: str) -> None:
        try:
            self.items.append(self.app.game.make_item(food_id))
        except (KeyError, ValueError):
            self.app.error("Couldn't add that food")
            return
        sfx.play("tap")
        self._refresh()

    def _replace(self, i: int) -> None:
        old = self.items[i]

        def picked(fid: str) -> None:
            g = self.app.game
            grams = old.grams if old.grams else None
            try:
                new = g.make_item(fid, grams, from_scale=old.from_scale,
                                  confidence=old.confidence,
                                  source="scan" if old.source == "scan" else None)
            except (KeyError, ValueError):
                self.app.error("Couldn't use that food")
                return
            if old.food_id is None and old.source == "scan" and not old.kcal:
                new = g.make_item(fid, None, confidence=old.confidence, source="scan")
            self.items[i] = new
            self._refresh()

        food_picker(self.app, picked, self.meal, title="Pick the food")

    def add_food(self, _: Any = None) -> None:
        food_picker(self.app, self._add, self.meal)

    async def save(self, _: Any = None) -> None:
        app, g = self.app, self.app.game
        unknown = [it.name for it in self.items if it.food_id is None and it.source == "scan"]
        if unknown:
            app.error(f"Pick a food for '{unknown[0]}' or remove it")
            return
        if not self.items:
            app.error("Add at least one food")
            return
        if self.meal_id:
            try:
                g.edit_meal(self.meal_id, meal=self.meal, items=self.items)
            except ValueError as exc:
                app.error(str(exc).capitalize())
                return
            app.save()
            sfx.play("toggle")
            app.toast("Meal updated", ft.Icons.EDIT)
        else:
            now = datetime.now()
            when = f"{now:%H:%M}" if self.day == app.today() else ""
            try:
                g._check_meal(self.meal, self.items)
            except ValueError as exc:
                app.error(str(exc).capitalize())
                return
            label = MEAL_LABELS[self.meal]
            c = await app.award(
                lambda: g.add_meal(self.day, self.meal, self.items, app.today(), when),
                line=lambda c: f"Notice: {label} logged. +{c.xp} XP to Monk Path.")
            if self.photo and g.profile.nutrition.keep_photos and c.ref_id:
                with contextlib.suppress(OSError):
                    g.meal(c.ref_id).photo = storage.save_photo(f"{c.ref_id}.jpg", self.photo)
                    app.save()
            if not c.xp:
                sfx.play("tap")
                app.toast(f"{label} logged", MEAL_ICONS[self.meal])
        self.photo = None  # discarded unless kept above
        cb = self.on_saved
        app.more.back()
        if cb:
            cb()
