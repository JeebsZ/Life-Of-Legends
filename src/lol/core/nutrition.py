"""Body numbers and a calorie/macro plan. Pure functions: no Flet, no clock (dates come in).

Formulas (all screening estimates - NOT medical advice):
- BMR: Mifflin-St Jeor (1990): 10*kg + 6.25*cm - 5*age + s, s = +5 male, -161 female. With
  sex "unspecified" the two formulas are averaged (s = -78) and the plan says so.
- TDEE = BMR x activity factor (1.2 sedentary .. 1.9 very active).
- 1 kg of body weight ~ 7700 kcal. Loss pace: gentle 0.25 / steady 0.5 / fast 0.75 kg per
  week, capped at 1 % of current weight per week. Daily target = TDEE - pace*7700/7.
- Safety floor: max(BMR, 1200 female / 1500 male / 1350 unspecified). If the target would go
  below it, the target sits AT the floor and the timeline gets longer (the plan says so).
- Gain: surplus +250 / +375 / +500 kcal a day (gentle / steady / fast). Maintain: TDEE.
- BMI = kg / m^2 with WHO adult categories. A goal under BMI 18.5 is refused.
- Protein ~1.8 g/kg (range 1.6-2.2) of CURRENT weight, but above BMI 25 the reference weight is
  the weight at BMI 25 for the height (so the number stays sensible). Fat 25-30 % of kcal
  (at least 0.6 g/kg reference). Carbs = the rest. Fiber 14 g per 1000 kcal. Water 30-35 ml/kg.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta

KCAL_PER_KG = 7700
LB_PER_KG = 2.20462
CM_PER_IN = 2.54

SEXES = ("female", "male", "unspecified")
SEX_OFFSET = {"male": 5.0, "female": -161.0, "unspecified": -78.0}
SEX_FLOOR = {"female": 1200, "male": 1500, "unspecified": 1350}

ACTIVITY_LEVELS = ("sedentary", "light", "moderate", "active", "very_active")
ACTIVITY_FACTORS = {"sedentary": 1.2, "light": 1.375, "moderate": 1.55, "active": 1.725,
                    "very_active": 1.9}
ACTIVITY_LABELS = {
    "sedentary": ("Mostly sitting", "Desk work, little exercise"),
    "light": ("Lightly active", "Exercise 1-3 days a week"),
    "moderate": ("Moderately active", "Exercise 3-5 days a week"),
    "active": ("Very active", "Hard exercise 6-7 days a week"),
    "very_active": ("Athlete level", "Physical job plus training"),
}

GOALS = ("lose", "maintain", "gain")
PACES = ("gentle", "steady", "fast")
LOSS_KG_PER_WEEK = {"gentle": 0.25, "steady": 0.5, "fast": 0.75}
GAIN_SURPLUS = {"gentle": 250, "steady": 375, "fast": 500}
MAX_LOSS_FRACTION = 0.01  # per week, of current weight
MAINTAIN_BAND_KG = 0.5  # a goal this close to the current weight = maintain

BMI_HEALTHY_MIN = 18.5
BMI_REFERENCE = 25.0  # protein reference weight above this BMI
PROTEIN_G_PER_KG = (1.6, 1.8, 2.2)  # low, target, high
FAT_PCT = (0.25, 0.275, 0.30)
FAT_MIN_G_PER_KG = 0.6
FIBER_G_PER_1000 = 14
WATER_ML_PER_KG = (30, 35)
KCAL_RANGE = 100  # +- shown around the daily target
ADULT_AGE = 18
MIN_AGE, MAX_AGE = 13, 100
MIN_HEIGHT_CM, MAX_HEIGHT_CM = 100, 250
MIN_WEIGHT_KG, MAX_WEIGHT_KG = 25, 350

DISCLAIMER = ("Not medical advice. Talk to a doctor first if you are pregnant or "
              "breastfeeding, under 18, or have a medical condition.")
BMI_NOTE = "BMI is a rough screening number. It doesn't see muscle, frame or health."


class PlanRefused(ValueError):
    """The goal can't be planned safely; the message is shown to the user as-is."""


# --- units ---------------------------------------------------------------------------------------
def kg_to_lb(kg: float) -> float:
    return kg * LB_PER_KG


def lb_to_kg(lb: float) -> float:
    return lb / LB_PER_KG


def to_kg(value: float, unit: str) -> float:
    if unit not in ("kg", "lb"):
        raise ValueError("weight unit must be kg or lb")
    return value if unit == "kg" else lb_to_kg(value)


def from_kg(kg: float, unit: str) -> float:
    return kg if unit == "kg" else kg_to_lb(kg)


def ft_in_to_cm(feet: float, inches: float = 0) -> float:
    return (feet * 12 + inches) * CM_PER_IN


def cm_to_ft_in(cm: float) -> tuple[int, int]:
    total = round(cm / CM_PER_IN)
    return total // 12, total % 12


def age_from(value: int, today: date) -> tuple[int, int]:
    """'Age or birth year' input -> (age, birth_year). Values < 200 are ages."""
    v = int(value)
    if v < 200:
        return v, today.year - v
    return today.year - v, v


def age_on(birth_year: int, today: date) -> int:
    return today.year - int(birth_year)


# --- checks --------------------------------------------------------------------------------------
def check_body(weight_kg: float, height_cm: float, age: int, sex: str) -> None:
    if not MIN_WEIGHT_KG <= weight_kg <= MAX_WEIGHT_KG:
        raise ValueError(f"weight must be {MIN_WEIGHT_KG}-{MAX_WEIGHT_KG} kg")
    if not MIN_HEIGHT_CM <= height_cm <= MAX_HEIGHT_CM:
        raise ValueError(f"height must be {MIN_HEIGHT_CM}-{MAX_HEIGHT_CM} cm")
    if not MIN_AGE <= age <= MAX_AGE:
        raise ValueError(f"age must be {MIN_AGE}-{MAX_AGE}")
    if sex not in SEXES:
        raise ValueError(f"sex must be one of {SEXES}")


# --- BMI -----------------------------------------------------------------------------------------
def bmi(weight_kg: float, height_cm: float) -> float:
    m = height_cm / 100
    return weight_kg / (m * m)


def bmi_category(value: float) -> str:
    """WHO adult categories, in plain non-judging words."""
    if value < 18.5:
        return "Underweight range"
    if value < 25:
        return "Healthy range"
    if value < 30:
        return "Overweight range"
    if value < 35:
        return "Obesity class I range"
    if value < 40:
        return "Obesity class II range"
    return "Obesity class III range"


def weight_at_bmi(target_bmi: float, height_cm: float) -> float:
    m = height_cm / 100
    return target_bmi * m * m


def healthy_range_kg(height_cm: float) -> tuple[float, float]:
    """Weights for BMI 18.5..24.9 at this height."""
    return weight_at_bmi(18.5, height_cm), weight_at_bmi(24.9, height_cm)


# --- energy --------------------------------------------------------------------------------------
def bmr(weight_kg: float, height_cm: float, age: int, sex: str) -> float:
    """Mifflin-St Jeor resting energy, kcal/day."""
    if sex not in SEX_OFFSET:
        raise ValueError(f"sex must be one of {SEXES}")
    return 10 * weight_kg + 6.25 * height_cm - 5 * age + SEX_OFFSET[sex]


def tdee(bmr_kcal: float, activity: str) -> float:
    if activity not in ACTIVITY_FACTORS:
        raise ValueError(f"activity must be one of {ACTIVITY_LEVELS}")
    return bmr_kcal * ACTIVITY_FACTORS[activity]


def safety_floor(bmr_kcal: float, sex: str) -> float:
    return max(bmr_kcal, SEX_FLOOR.get(sex, SEX_FLOOR["unspecified"]))


def goal_kind(current_kg: float, goal_kg: float | None) -> str:
    if goal_kg is None or abs(goal_kg - current_kg) <= MAINTAIN_BAND_KG:
        return "maintain"
    return "lose" if goal_kg < current_kg else "gain"


def loss_rate(weight_kg: float, pace: str) -> float:
    """kg/week for a loss pace, capped at 1 % of the current weight."""
    if pace not in LOSS_KG_PER_WEEK:
        raise ValueError(f"pace must be one of {PACES}")
    return min(LOSS_KG_PER_WEEK[pace], MAX_LOSS_FRACTION * weight_kg)


# --- macros --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Macros:
    kcal: int
    protein_g: tuple[int, int, int]  # low, target, high
    fat_g: tuple[int, int, int]
    carbs_g: tuple[int, int, int]
    ref_weight_kg: float  # weight the g/kg numbers use
    fiber_g: int
    water_ml: tuple[int, int]

    def pct(self) -> dict[str, int]:
        """Share of kcal for the target grams (rounded, sums to ~100)."""
        k = max(1, self.kcal)
        return {"protein": round(self.protein_g[1] * 4 * 100 / k),
                "fat": round(self.fat_g[1] * 9 * 100 / k),
                "carbs": round(self.carbs_g[1] * 4 * 100 / k)}


def protein_reference_kg(weight_kg: float, height_cm: float) -> float:
    """Current weight, or the weight at BMI 25 when above it."""
    return min(weight_kg, weight_at_bmi(BMI_REFERENCE, height_cm))


def macros(kcal: float, weight_kg: float, height_cm: float) -> Macros:
    ref = protein_reference_kg(weight_kg, height_cm)
    p = [g * ref for g in PROTEIN_G_PER_KG]
    fat_min = FAT_MIN_G_PER_KG * ref
    f = [max(fat_min, kcal * pct / 9) for pct in FAT_PCT]
    carbs_mid = (kcal - p[1] * 4 - f[1] * 9) / 4
    carbs_hi = (kcal - p[0] * 4 - f[0] * 9) / 4
    carbs_lo = (kcal - p[2] * 4 - f[2] * 9) / 4
    c = [max(0.0, carbs_lo), max(0.0, carbs_mid), max(0.0, carbs_hi)]
    return Macros(
        kcal=round(kcal),
        protein_g=tuple(round(x) for x in p),  # type: ignore[arg-type]
        fat_g=tuple(round(x) for x in f),  # type: ignore[arg-type]
        carbs_g=tuple(round(x) for x in c),  # type: ignore[arg-type]
        ref_weight_kg=round(ref, 1),
        fiber_g=round(FIBER_G_PER_1000 * kcal / 1000),
        water_ml=(round(WATER_ML_PER_KG[0] * weight_kg, -2),
                  round(WATER_ML_PER_KG[1] * weight_kg, -2)),
    )


# --- plan ----------------------------------------------------------------------------------------
@dataclass(frozen=True)
class PlanResult:
    goal: str  # lose | maintain | gain
    pace: str
    start_kg: float
    goal_kg: float
    bmr: int
    tdee: int
    floor: int
    target_kcal: int
    kcal_low: int
    kcal_high: int
    weekly_kg: float  # expected change per week (negative = loss); 0 for maintain
    est_date: date | None  # None = maintain, or no change expected
    weeks: float | None
    floor_bound: bool
    sex_assumed: bool  # sex unspecified: formulas averaged
    macros: Macros
    notes: tuple[str, ...] = field(default=())


def make_plan(weight_kg: float, height_cm: float, age: int, sex: str, activity: str,
              goal_kg: float | None, pace: str, today: date) -> PlanResult:
    """A daily kcal target + macros for a goal. Raises PlanRefused (a friendly message) when
    the goal is not safe to plan, ValueError on bad inputs."""
    check_body(weight_kg, height_cm, age, sex)
    if pace not in PACES:
        raise ValueError(f"pace must be one of {PACES}")
    goal = goal_kind(weight_kg, goal_kg)
    goal_kg = weight_kg if goal_kg is None else float(goal_kg)
    lo_ok = weight_at_bmi(BMI_HEALTHY_MIN, height_cm)
    notes: list[str] = []
    if goal == "lose":
        if bmi(goal_kg, height_cm) < BMI_HEALTHY_MIN:
            raise PlanRefused(
                f"That target is below the healthy range for your height (about "
                f"{lo_ok:.1f} kg or more). Luma won't plan for it - a doctor or dietitian "
                "can help you pick a safe goal.")
        if age < ADULT_AGE:
            raise PlanRefused("Weight-loss plans here are for adults. Please talk to a doctor "
                              "or your parents first - Luma can still help you track meals.")
    b = bmr(weight_kg, height_cm, age, sex)
    t = tdee(b, activity)
    floor = safety_floor(b, sex)
    floor_bound = False
    if goal == "lose":
        rate = loss_rate(weight_kg, pace)
        if rate < LOSS_KG_PER_WEEK[pace]:
            notes.append(f"Pace capped at 1% of your weight: {rate:.2f} kg a week.")
        target = t - rate * KCAL_PER_KG / 7
        if target < floor:
            floor_bound = True
            target = floor
            rate = max(0.0, (t - floor) * 7 / KCAL_PER_KG)
            if rate <= 0:
                notes.append("Your safety floor is at your maintenance level, so food alone "
                             "won't move the scale. More daily movement would.")
            else:
                notes.append("Your target is held at a safe minimum, so this takes a bit "
                             f"longer: about {rate:.2f} kg a week.")
        weekly = -rate
    elif goal == "gain":
        target = t + GAIN_SURPLUS[pace]
        weekly = GAIN_SURPLUS[pace] * 7 / KCAL_PER_KG
    else:
        target, weekly = t, 0.0
    if sex == "unspecified":
        notes.append("Sex not given: Luma averaged the male and female formulas.")
    if age < ADULT_AGE:
        notes.append("These formulas are made for adults - treat the numbers as rough.")
    if goal == "gain" and bmi(goal_kg, height_cm) >= 30:
        notes.append("That goal is above the healthy BMI range - worth a chat with a doctor.")
    weeks = abs(goal_kg - weight_kg) / abs(weekly) if weekly else None
    est = today + timedelta(days=math.ceil(weeks * 7)) if weeks else None
    target_r = round(target / 10) * 10
    if goal == "lose" and target_r < floor:  # rounding never dips under the floor
        target_r = math.ceil(floor / 10) * 10
    return PlanResult(
        goal=goal, pace=pace, start_kg=round(weight_kg, 1), goal_kg=round(goal_kg, 1),
        bmr=round(b), tdee=round(t), floor=round(floor), target_kcal=target_r,
        kcal_low=max(round(floor), target_r - KCAL_RANGE) if goal == "lose"
        else target_r - KCAL_RANGE,
        kcal_high=target_r + KCAL_RANGE, weekly_kg=round(weekly, 3), est_date=est,
        weeks=round(weeks, 1) if weeks else None, floor_bound=floor_bound,
        sex_assumed=sex == "unspecified", macros=macros(target_r, weight_kg, height_cm),
        notes=tuple(notes))


# --- food amounts and ranges ---------------------------------------------------------------------
PORTION_PRESETS = (("small", 0.6), ("medium", 1.0), ("large", 1.5))
PORTION_GUESS_UNCERTAINTY = 0.25  # grams eyeballed / guessed from a photo
SCALE_UNCERTAINTY = 0.02  # grams from a kitchen scale


def scaled(per100: float, grams: float) -> float:
    return per100 * grams / 100


def kcal_range(kcal: float, food_uncertainty: float, from_scale: bool) -> tuple[int, int]:
    """Low/high kcal for an item: the food's own spread combined with the portion spread
    (tiny for scale grams, wide for guesses). Rounded to 5 kcal."""
    portion_u = SCALE_UNCERTAINTY if from_scale else PORTION_GUESS_UNCERTAINTY
    u = math.hypot(food_uncertainty, portion_u)
    lo, hi = kcal * (1 - u), kcal * (1 + u)
    return int(5 * math.floor(lo / 5)), int(5 * math.ceil(hi / 5))


def round_range(lo: float, hi: float, step: int = 10) -> tuple[int, int]:
    return int(step * math.floor(lo / step)), int(step * math.ceil(hi / step))
