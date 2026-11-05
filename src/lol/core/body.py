"""Body + Meals rules, mixed into Game (schema 5). Pure logic: dates come in, no Flet.

Body: height/sex/age/activity, a weight log (small capped Monk XP for logging, never for the
number going down), BMI, and a Luma plan (core/nutrition.py) that the user accepts.
Meals: a daily log of food items with kcal RANGES, the food table (core/foods.py) plus the
user's own foods, favorites and recents, and photo-scan candidates -> editable items.
Calorie tracking is opt-in (Profile.nutrition). Nothing here rewards eating less.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

from lol.core import foods, nutrition, onboarding
from lol.core.foods import Food
from lol.core.models import (
    MEAL_ITEM_SOURCES,
    MEAL_TYPES,
    BodyProfile,
    Completion,
    CustomFood,
    MealEntry,
    MealItem,
    NutritionPlan,
    WeightEntry,
)
from lol.core.recognize import Candidate

if TYPE_CHECKING:
    from lol.core.models import SaveData

MONK = "monk"
WEIGHT_LOG_XP = 5  # once per day of logging
MEAL_LOG_XP = 3  # per meal logged
MEAL_DAILY_XP_CAP = 9  # per day of logging (3 meals' worth); snacks beyond that log freely
MAX_ITEM_GRAMS = 3000
MAX_ITEMS = 30
CUSTOM_UNCERTAINTY = 0.10
MANUAL_UNCERTAINTY = 0.15
UNSET: Any = object()
HEIGHT_UNITS = ("cm", "ftin")


def _iso(d: date) -> str:
    return d.isoformat()


def meal_for_hour(hour: int) -> str:
    """Default meal type for the time of day."""
    if 4 <= hour < 10:
        return "breakfast"
    if 10 <= hour < 15:
        return "lunch"
    if 15 <= hour < 18:
        return "snack"
    if 18 <= hour < 22:
        return "dinner"
    return "snack"


def custom_as_food(cf: CustomFood) -> Food:
    return Food(cf.id, cf.name, cf.kcal, cf.protein, cf.carbs, cf.fat, cf.portion_g,
                cf.portion_label, foods.CUSTOM, CUSTOM_UNCERTAINTY, (), "mine")


class BodyMixin:
    """Game methods for Body + Meals. Relies on Game's data/_new_id/_award/_find/profile."""

    data: SaveData

    if TYPE_CHECKING:  # provided by Game
        def _new_id(self, prefix: str) -> str: ...
        def _award(self, xp: int, coins: int, path_id: str, today: date) -> Completion: ...
        def _find(self, items: list, item_id: str) -> Any: ...

    # ============================================================== body
    @property
    def body(self) -> BodyProfile:
        return self.data.body

    def set_body(self, *, height_cm: Any = UNSET, sex: Any = UNSET, birth_year: Any = UNSET,
                 activity: str | None = None, weight_unit: str | None = None,
                 height_unit: str | None = None) -> BodyProfile:
        """Omit = unchanged; height/sex/birth_year accept None to clear."""
        b = self.body
        if height_cm is not UNSET:
            if height_cm is not None and not (nutrition.MIN_HEIGHT_CM <= float(height_cm)
                                              <= nutrition.MAX_HEIGHT_CM):
                raise ValueError(f"height must be {nutrition.MIN_HEIGHT_CM}-"
                                 f"{nutrition.MAX_HEIGHT_CM} cm")
            b.height_cm = None if height_cm is None else round(float(height_cm), 1)
        if sex is not UNSET:
            if sex is not None and sex not in nutrition.SEXES:
                raise ValueError(f"sex must be one of {nutrition.SEXES}")
            b.sex = sex
        if birth_year is not UNSET:
            b.birth_year = None if birth_year is None else int(birth_year)
        if activity is not None:
            if activity not in nutrition.ACTIVITY_FACTORS:
                raise ValueError(f"activity must be one of {nutrition.ACTIVITY_LEVELS}")
            b.activity = activity
        if weight_unit is not None:
            if weight_unit not in ("kg", "lb"):
                raise ValueError("weight unit must be kg or lb")
            b.weight_unit = weight_unit
        if height_unit is not None:
            if height_unit not in HEIGHT_UNITS:
                raise ValueError(f"height unit must be one of {HEIGHT_UNITS}")
            b.height_unit = height_unit
        return b

    def set_age(self, value: int, today: date) -> int:
        """'Age or birth year' -> stores birth_year; returns the age."""
        age, year = nutrition.age_from(value, today)
        if not nutrition.MIN_AGE <= age <= nutrition.MAX_AGE:
            raise ValueError(f"age must be {nutrition.MIN_AGE}-{nutrition.MAX_AGE}")
        self.body.birth_year = year
        return age

    def age(self, today: date) -> int | None:
        y = self.body.birth_year
        return None if y is None else nutrition.age_on(y, today)

    def is_minor(self, today: date) -> bool:
        """Under 18 by the Body age OR the onboarding age band - either is enough (safety
        first). Drives the no-weight-loss rule and the gentle run ladder."""
        age = self.age(today)
        return ((age is not None and age < nutrition.ADULT_AGE)
                or onboarding.is_minor(self.data.profile.onboarding.age_band))

    # --- weight log ---------------------------------------------------------------------------
    def log_weight(self, value: float, unit: str, today: date, day: date | None = None,
                   note: str = "") -> Completion:
        """Log a weigh-in (one per day: logging the same day again updates it). Gives
        WEIGHT_LOG_XP Monk XP once per day of logging - for logging, never for the number.
        Completion.ref_id = entry id."""
        kg = round(nutrition.to_kg(float(value), unit), 2)
        if not nutrition.MIN_WEIGHT_KG <= kg <= nutrition.MAX_WEIGHT_KG:
            raise ValueError(f"weight must be {nutrition.MIN_WEIGHT_KG}-"
                             f"{nutrition.MAX_WEIGHT_KG} kg")
        d = _iso(day or today)
        existing = next((w for w in self.data.weights if w.day == d), None)
        if existing is not None:
            existing.kg = kg
            if note:
                existing.note = note
            return Completion(path_id=MONK, ref_id=existing.id)
        earned = any(w.logged_on == _iso(today) and w.xp for w in self.data.weights)
        c = (Completion(path_id=MONK) if earned
             else self._award(WEIGHT_LOG_XP, 0, MONK, today))
        entry = WeightEntry(self._new_id("wt"), d, kg, note, _iso(today), c.xp)
        self.data.weights.append(entry)
        c.ref_id = entry.id
        return c

    def weights(self, start: date | None = None, end: date | None = None) -> list[WeightEntry]:
        """Weigh-ins in start..end, oldest first."""
        rows = [w for w in self.data.weights
                if (start is None or w.day >= _iso(start)) and (end is None or w.day <= _iso(end))]
        return sorted(rows, key=lambda w: w.day)

    def latest_weight(self) -> WeightEntry | None:
        rows = self.weights()
        return rows[-1] if rows else None

    def delete_weight(self, entry_id: str) -> None:
        """Remove a weigh-in. XP it earned stays."""
        self.data.weights.remove(self._find(self.data.weights, entry_id))

    def body_status(self, today: date) -> dict:
        """Keys: weight_kg, height_cm, age, sex, bmi, bmi_category, healthy_kg (lo, hi),
        missing (list of field names still needed for a plan), ready (bool)."""
        b = self.body
        w = self.latest_weight()
        age = self.age(today)
        missing = [name for name, v in (("weight", w), ("height", b.height_cm), ("age", age),
                                         ("sex", b.sex)) if v is None]
        out: dict[str, Any] = {"weight_kg": w.kg if w else None, "height_cm": b.height_cm,
                               "age": age, "sex": b.sex, "bmi": None, "bmi_category": None,
                               "healthy_kg": None, "missing": missing, "ready": not missing}
        if w and b.height_cm:
            v = nutrition.bmi(w.kg, b.height_cm)
            out.update(bmi=round(v, 1), bmi_category=nutrition.bmi_category(v),
                       healthy_kg=nutrition.healthy_range_kg(b.height_cm))
        return out

    # --- plan ---------------------------------------------------------------------------------
    def propose_plan(self, today: date, goal_kg: float | None = None,
                     pace: str | None = None) -> nutrition.PlanResult:
        """Luma's proposal from the saved body data + latest weigh-in (not saved). Raises
        ValueError if data is missing, nutrition.PlanRefused if the goal isn't safe."""
        st = self.body_status(today)
        if not st["ready"]:
            raise ValueError("Luma needs your " + ", ".join(st["missing"]) + " first")
        b = self.body
        age = st["age"]
        if self.is_minor(today):  # an under-18 age band counts even if Body says adult
            age = min(age, nutrition.ADULT_AGE - 1)
        return nutrition.make_plan(st["weight_kg"], b.height_cm, age, b.sex, b.activity,
                                   goal_kg, pace or b.pace, today)

    def accept_plan(self, plan: nutrition.PlanResult, today: date) -> NutritionPlan:
        m = plan.macros
        saved = NutritionPlan(
            created=_iso(today), goal=plan.goal, pace=plan.pace, start_kg=plan.start_kg,
            goal_kg=plan.goal_kg, bmr=plan.bmr, tdee=plan.tdee, floor=plan.floor,
            target_kcal=plan.target_kcal, kcal_low=plan.kcal_low, kcal_high=plan.kcal_high,
            protein_g=list(m.protein_g), fat_g=list(m.fat_g), carbs_g=list(m.carbs_g),
            fiber_g=m.fiber_g, water_ml=list(m.water_ml), weekly_kg=plan.weekly_kg,
            est_date=plan.est_date.isoformat() if plan.est_date else "",
            floor_bound=plan.floor_bound, sex_assumed=plan.sex_assumed, notes=list(plan.notes))
        self.body.plan = saved
        self.body.goal_kg = plan.goal_kg if plan.goal != "maintain" else None
        self.body.pace = plan.pace
        return saved

    def clear_plan(self) -> None:
        self.body.plan = None
        self.body.goal_kg = None

    def set_nutrition(self, *, calorie_tracking: bool | None = None,
                      today_chip: bool | None = None, keep_photos: bool | None = None) -> None:
        n = self.data.profile.nutrition
        if calorie_tracking is not None:
            n.calorie_tracking = bool(calorie_tracking)
        if today_chip is not None:
            n.today_chip = bool(today_chip)
        if keep_photos is not None:
            n.keep_photos = bool(keep_photos)

    # ============================================================== foods
    def food_info(self, food_id: str) -> Food:
        """Built-in or custom food by id (KeyError if unknown)."""
        if foods.has(food_id):
            return foods.food(food_id)
        return custom_as_food(self._find(self.data.custom_foods, food_id))

    def has_food(self, food_id: str | None) -> bool:
        if not food_id:
            return False
        return foods.has(food_id) or any(f.id == food_id for f in self.data.custom_foods)

    def my_foods(self) -> list[Food]:
        return [custom_as_food(cf) for cf in self.data.custom_foods]

    def search_foods(self, query: str, limit: int = 20, brand: str | None = None) -> list[Food]:
        """Curated + restaurant + databank foods (and 'my foods'); `brand` = one chain only."""
        return foods.search(query, limit, extra=self.my_foods(), brand=brand)

    def add_custom_food(self, name: str, kcal: float, protein: float = 0, carbs: float = 0,
                        fat: float = 0, portion_g: float = 100,
                        portion_label: str = "1 serving") -> CustomFood:
        """A 'my foods' entry; nutrients are per 100 g."""
        name = (name or "").strip()
        if not name:
            raise ValueError("give the food a name")
        vals = [float(kcal), float(protein), float(carbs), float(fat)]
        if not 0 <= vals[0] <= 900 or any(not 0 <= v <= 100 for v in vals[1:]):
            raise ValueError("per 100 g: kcal 0-900, protein/carbs/fat 0-100 g")
        if not 0 < float(portion_g) <= MAX_ITEM_GRAMS:
            raise ValueError(f"portion must be 1-{MAX_ITEM_GRAMS} g")
        cf = CustomFood(self._new_id("cf"), name, *vals, float(portion_g),
                        portion_label.strip() or "1 serving")
        self.data.custom_foods.append(cf)
        return cf

    def delete_custom_food(self, food_id: str) -> None:
        """Remove from 'my foods'. Meals that used it keep their numbers."""
        self.data.custom_foods.remove(self._find(self.data.custom_foods, food_id))
        if food_id in self.data.favorite_foods:
            self.data.favorite_foods.remove(food_id)

    def is_favorite(self, food_id: str) -> bool:
        return food_id in self.data.favorite_foods

    def toggle_favorite(self, food_id: str) -> bool:
        """Star/unstar a food; returns whether it is now a favorite."""
        if food_id in self.data.favorite_foods:
            self.data.favorite_foods.remove(food_id)
            return False
        if not self.has_food(food_id):
            raise KeyError(food_id)
        self.data.favorite_foods.append(food_id)
        return True

    def favorite_foods(self) -> list[Food]:
        return [self.food_info(i) for i in self.data.favorite_foods if self.has_food(i)]

    def recent_food_ids(self, limit: int = 10) -> list[str]:
        """Most recently logged foods first (no repeats)."""
        out: list[str] = []
        for m in sorted(self.data.meals, key=lambda m: (m.day, m.time, m.id), reverse=True):
            for it in reversed(m.items):
                if it.food_id and it.food_id not in out and self.has_food(it.food_id):
                    out.append(it.food_id)
                    if len(out) >= limit:
                        return out
        return out

    def food_suggestions(self, meal: str, limit: int = 8) -> list[Food]:
        """Quick picks when a scan finds nothing: favorites, recents, then time-of-day
        defaults for `meal`."""
        ids: list[str] = []
        for fid in (*self.data.favorite_foods, *self.recent_food_ids(6),
                    *foods.suggestions_for(meal)):
            if fid not in ids and self.has_food(fid):
                ids.append(fid)
        return [self.food_info(i) for i in ids[:limit]]

    # ============================================================== items
    @staticmethod
    def _check_grams(grams: float) -> float:
        g = float(grams)
        if not 0 < g <= MAX_ITEM_GRAMS:
            raise ValueError(f"grams must be 1-{MAX_ITEM_GRAMS}")
        return round(g, 1)

    def make_item(self, food_id: str, grams: float | None = None, *, from_scale: bool = False,
                  confidence: float | None = None, source: str | None = None) -> MealItem:
        """An item for `grams` of a food (None = its typical portion)."""
        f = self.food_info(food_id)
        g = self._check_grams(f.portion_g if grams is None else grams)
        kcal = nutrition.scaled(f.kcal, g)
        lo, hi = nutrition.kcal_range(kcal, f.uncertainty, from_scale)
        src = source or ("custom" if f.source == foods.CUSTOM else "db")
        return MealItem(f.name, g, round(kcal, 1), round(nutrition.scaled(f.protein, g), 1),
                        round(nutrition.scaled(f.carbs, g), 1),
                        round(nutrition.scaled(f.fat, g), 1), f.id, bool(from_scale), lo, hi,
                        confidence, src)

    @staticmethod
    def manual_item(name: str, grams: float, kcal: float, protein: float = 0,
                    carbs: float = 0, fat: float = 0, *, from_scale: bool = False) -> MealItem:
        """A one-off item typed in by hand (totals for the portion, not per 100 g)."""
        name = (name or "").strip()
        if not name:
            raise ValueError("give the item a name")
        g = BodyMixin._check_grams(grams)
        if not 0 <= float(kcal) <= 5000:
            raise ValueError("kcal must be 0-5000")
        lo, hi = nutrition.kcal_range(float(kcal), MANUAL_UNCERTAINTY, from_scale)
        return MealItem(name, g, float(kcal), float(protein), float(carbs), float(fat), None,
                        from_scale, lo, hi, None, "manual")

    def regram(self, item: MealItem, grams: float, from_scale: bool) -> MealItem:
        """The same food at new grams (scale grams override any estimate)."""
        g = self._check_grams(grams)
        if item.food_id and self.has_food(item.food_id):
            src = item.source if item.source in MEAL_ITEM_SOURCES else "db"
            return self.make_item(item.food_id, g, from_scale=from_scale,
                                  confidence=item.confidence, source=src)
        k = g / item.grams if item.grams else 0.0
        kcal = item.kcal * k
        u = MANUAL_UNCERTAINTY
        lo, hi = nutrition.kcal_range(kcal, u, from_scale)
        return dataclasses.replace(item, grams=g, kcal=round(kcal, 1),
                                   protein=round(item.protein * k, 1),
                                   carbs=round(item.carbs * k, 1), fat=round(item.fat * k, 1),
                                   from_scale=from_scale, kcal_low=lo, kcal_high=hi)

    def items_from_candidates(self, candidates: Iterable[Candidate]) -> list[MealItem]:
        """Recognizer output -> draft items. Candidates that match a food get its numbers;
        unmatched ones stay as named placeholders (food_id None, 0 kcal) for the user to pick."""
        out: list[MealItem] = []
        mine = self.my_foods()
        for c in candidates:
            fid = c.food_id if self.has_food(c.food_id) else foods.match_food(c.name, mine)
            grams = c.portion_g_guess if c.portion_g_guess and c.portion_g_guess > 0 else None
            if fid:
                out.append(self.make_item(fid, grams, confidence=c.confidence, source="scan"))
            else:
                out.append(MealItem(c.name or "Unknown food", grams or 100, 0, 0, 0, 0, None,
                                    False, 0, 0, c.confidence, "scan"))
        return out[:MAX_ITEMS]

    # ============================================================== meals
    def _check_meal(self, meal: str, items: list[MealItem]) -> None:
        if meal not in MEAL_TYPES:
            raise ValueError(f"meal must be one of {MEAL_TYPES}")
        if not items:
            raise ValueError("add at least one food")
        if len(items) > MAX_ITEMS:
            raise ValueError(f"at most {MAX_ITEMS} items in one meal")
        for it in items:
            self._check_grams(it.grams)

    def add_meal(self, day: date, meal: str, items: Iterable[MealItem], today: date,
                 time: str = "", note: str = "", photo: str = "") -> Completion:
        """Log a meal. Gives MEAL_LOG_XP Monk XP per meal, up to MEAL_DAILY_XP_CAP per day of
        logging. XP is for logging only - never for eating more or less.
        Completion.ref_id = meal id."""
        rows = [dataclasses.replace(it) for it in items]
        self._check_meal(meal, rows)
        earned = sum(m.xp for m in self.data.meals if m.day == _iso(today))
        xp = min(MEAL_LOG_XP, max(0, MEAL_DAILY_XP_CAP - earned))
        c = self._award(xp, 0, MONK, today) if xp else Completion(path_id=MONK)
        entry = MealEntry(self._new_id("ml"), _iso(day), meal, time, rows, note, photo, c.xp)
        self.data.meals.append(entry)
        c.ref_id = entry.id
        return c

    def meal(self, meal_id: str) -> MealEntry:
        return self._find(self.data.meals, meal_id)

    def edit_meal(self, meal_id: str, *, meal: str | None = None,
                  items: Iterable[MealItem] | None = None, note: str | None = None,
                  day: date | None = None) -> MealEntry:
        m = self.meal(meal_id)
        new_items = m.items if items is None else [dataclasses.replace(i) for i in items]
        self._check_meal(meal or m.meal, new_items)
        m.meal, m.items = meal or m.meal, new_items
        if note is not None:
            m.note = note
        if day is not None:
            m.day = _iso(day)
        return m

    def delete_meal(self, meal_id: str) -> MealEntry:
        """Remove a meal (returned, so the UI can drop a kept photo). XP stays."""
        m = self.meal(meal_id)
        self.data.meals.remove(m)
        return m

    def meals_on(self, day: date) -> list[MealEntry]:
        order = {t: i for i, t in enumerate(MEAL_TYPES)}
        rows = [m for m in self.data.meals if m.day == _iso(day)]
        return sorted(rows, key=lambda m: (order.get(m.meal, 9), m.time, m.id))

    @staticmethod
    def totals(items: Iterable[MealItem]) -> dict[str, float]:
        """kcal (mid), kcal_low, kcal_high, protein, carbs, fat, count."""
        rows = list(items)
        return {"kcal": round(sum(i.kcal for i in rows)),
                "kcal_low": round(sum(i.kcal_low for i in rows)),
                "kcal_high": round(sum(i.kcal_high for i in rows)),
                "protein": round(sum(i.protein for i in rows), 1),
                "carbs": round(sum(i.carbs for i in rows), 1),
                "fat": round(sum(i.fat for i in rows), 1),
                "count": len(rows)}

    def day_totals(self, day: date) -> dict[str, float]:
        return self.totals(it for m in self.meals_on(day) for it in m.items)

    def meal_history(self, start: date, end: date) -> list[tuple[str, int, int, int, int]]:
        """(ISO day, kcal, kcal_low, kcal_high, meals) for every day in start..end, oldest
        first (empty days included as zeros so a chart has every day)."""
        out = []
        for i in range((end - start).days + 1):
            d = start + timedelta(days=i)
            t = self.day_totals(d)
            out.append((_iso(d), int(t["kcal"]), int(t["kcal_low"]), int(t["kcal_high"]),
                        len(self.meals_on(d))))
        return out

    def kcal_left(self, today: date) -> dict | None:
        """For the Today chip: None unless calorie tracking is on and a plan exists. Keys:
        target, eaten_low, eaten_high, left_low, left_high (left can go below 0; the UI words
        that neutrally)."""
        plan = self.body.plan
        if plan is None or not self.data.profile.nutrition.calorie_tracking:
            return None
        t = self.day_totals(today)
        return {"target": plan.target_kcal, "eaten_low": int(t["kcal_low"]),
                "eaten_high": int(t["kcal_high"]),
                "left_low": plan.target_kcal - int(t["kcal_high"]),
                "left_high": plan.target_kcal - int(t["kcal_low"])}
