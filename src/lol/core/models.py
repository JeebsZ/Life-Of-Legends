"""Plain dataclasses for the save (schema 5). No rules here (see game.py), no I/O (see storage.py).

Dates are stored as ISO strings ("2026-11-04") so the save file stays human-readable JSON.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from lol.core.finance import SavingsGoal

QUEST_KINDS = ("once", "daily")
BILL_REPEATS = ("none", "weekly", "monthly", "yearly")
REWARD_KINDS = ("personal", "theme")
LOG_KINDS = ("workout", "sleep", "note")
BILL_STATUSES = ("overdue", "due_soon", "upcoming", "paid")
FOCUS_MODES = ("focus", "stopwatch")
ENTRY_KINDS = ("quest", "step", "log", "focus", "bill_due", "bill_paid")
RANK_NAMES = {1: "Novice", 2: "Apprentice", 3: "Adept"}
MAX_RANK = 3
WEIGHT_UNITS = ("kg", "lb")
WATER_UNITS = ("ml", "oz")
ENERGY_LEVELS = ("low", "okay", "high")
WORKOUT_TYPES = ("strength", "cardio", "mobility", "sport", "other")
MODULES = ("workout", "sleep", "water", "energy", "insights", "body", "meals", "run")
MEAL_TYPES = ("breakfast", "lunch", "dinner", "snack")
MEAL_ITEM_SOURCES = ("db", "custom", "manual", "scan")
REMINDER_CATEGORIES = ("bill", "daily", "water", "focus", "comeback")


def _default_modules() -> dict[str, bool]:
    return {m: True for m in MODULES}


@dataclass(frozen=True)
class PathDef:
    id: str
    name: str
    icon: str  # Material icon name, e.g. "restaurant"; the UI maps it to ft.Icons
    color: str  # hex, e.g. "#E76F51"


@dataclass(frozen=True)
class ThemeDef:
    id: str
    name: str
    price: int  # coins; 0 = free
    premium_only: bool = False  # buyable with coins only while premium (core/premium.py)


@dataclass(frozen=True)
class CatalogQuest:
    """A Quest Board suggestion. Becomes a real Quest via Game.suggest_quest + accept."""

    title: str
    path_id: str
    note: str
    difficulty: int  # 1..3
    minutes: int  # rough time estimate


@dataclass(frozen=True)
class CatalogStep:
    title: str
    note: str
    difficulty: int  # 1..3; XP and coins come from game.XP_BY_DIFFICULTY / COINS_BY_DIFFICULTY


@dataclass(frozen=True)
class CatalogChain:
    """A side quest template. rank 1 = the base chain that unlocks the skill; rank 2/3 =
    follow-up chains that rank the skill up (the player starts these by choice)."""

    id: str
    skill_name: str
    path_id: str
    rank: int  # rank this chain grants when finished (1..3)
    steps: tuple[CatalogStep, ...]
    blurb: str = ""


@dataclass
class Quest:
    id: str
    title: str
    path_id: str
    kind: str = "once"  # "once" | "daily"
    xp: int = 0
    coins: int = 0
    difficulty: int = 1
    note: str = ""
    created: str = ""  # ISO date
    done_on: list[str] = field(default_factory=list)  # ISO dates
    minutes: int | None = None  # estimate, set for Quest Board suggestions
    template_id: str | None = None  # QuestTemplate it was created from (info only)


@dataclass
class Bill:
    """A bill and its payment history.

    Cycles are numbered 0, 1, 2... `paid` has one entry per paid cycle, so cycle len(paid) is the
    next unpaid one. `due` is the due date of cycle `start_cycle` (0 for a never-edited bill = the
    first due date); later cycles are derived from `repeat`. Editing the schedule re-anchors:
    start_cycle = len(paid), due = the new next due date. Paid cycles keep the due date they
    covered in `paid_due` (and the amount in `paid_amounts`), so history never moves.
    """

    id: str
    name: str
    amount: float  # PHP
    due: str  # ISO due date of cycle `start_cycle`
    repeat: str = "none"  # "none" | "weekly" | "monthly" | "yearly"
    paid: list[str] = field(default_factory=list)  # ISO dates; one entry per cycle paid
    paid_due: list[str] = field(default_factory=list)  # due date each paid cycle covered
    paid_amounts: list[float] = field(default_factory=list)  # amount each paid cycle had
    start_cycle: int = 0  # cycle index `due` belongs to
    archived: bool = False  # hidden from status and totals; history kept
    note: str = ""
    rewarded_on: list[str] = field(default_factory=list)  # days a payment earned XP (no re-farm)


@dataclass
class Reward:
    id: str
    title: str
    cost: int
    kind: str = "personal"  # "personal" | "theme"
    theme_id: str | None = None
    redeemed: list[str] = field(default_factory=list)  # ISO dates
    redeemed_costs: list[int] = field(default_factory=list)  # price paid per redemption
    archived: bool = False  # hidden from the shop; deleting a redeemed reward archives it
    note: str = ""


@dataclass
class LogEntry:
    id: str
    day: str  # ISO date
    kind: str  # "workout" | "sleep" | "note"
    text: str = ""
    minutes: int | None = None


@dataclass
class Step:
    """One step of a side quest chain. Completed once ever (done_on = ISO date)."""

    title: str
    note: str = ""
    xp: int = 0
    coins: int = 0
    done_on: str | None = None
    skipped_on: str | None = None  # skipped = resolved (unlocks the next step), no XP

    @property
    def resolved(self) -> bool:
        return bool(self.done_on or self.skipped_on)


@dataclass
class SideQuest:
    """A chain of steps; finishing every step unlocks (rank 1) or ranks up its skill."""

    id: str
    skill_name: str
    path_id: str
    steps: list[Step] = field(default_factory=list)
    custom: bool = False
    rank_target: int = 1  # 1..3
    created: str = ""  # ISO date
    catalog_id: str | None = None  # CatalogChain id it was started from (None for custom)
    abandoned: bool = False  # abandoned chains keep earned XP but can't progress
    ordered: bool = False  # True = only the next unresolved step can be completed
    target_date: str | None = None  # ISO date; a soft goal, never a penalty
    paused: bool = False  # paused chains can't progress and are hidden from Today

    @property
    def done_count(self) -> int:
        return sum(1 for s in self.steps if s.done_on)

    @property
    def resolved_count(self) -> int:
        return sum(1 for s in self.steps if s.resolved)

    @property
    def finished(self) -> bool:
        """Every step done or skipped."""
        return bool(self.steps) and all(s.resolved for s in self.steps)

    @property
    def active(self) -> bool:
        return not self.abandoned and not self.finished


@dataclass
class Skill:
    """An unlocked skill. rank: 1 Novice, 2 Apprentice, 3 Adept."""

    name: str
    path_id: str
    rank: int = 1
    unlocked_on: str = ""  # ISO date rank 1 was earned
    chain_ids: list[str] = field(default_factory=list)  # SideQuest ids that earned each rank

    @property
    def rank_name(self) -> str:
        return RANK_NAMES.get(self.rank, "")


@dataclass
class QuestTemplate:
    """A reusable quest. Built-in ones live in catalog.TEMPLATES (builtin=True); editing one
    stores an override copy in the save, deleting one only hides it."""

    id: str
    title: str
    note: str = ""
    path_id: str = "warrior"
    difficulty: int = 1
    kind: str = "once"  # "once" | "daily"
    minutes: int | None = None
    coins: int = 0
    xp: int = 0
    builtin: bool = False


@dataclass
class FocusSession:
    id: str
    day: str  # ISO date
    started: str = ""  # free-form time stamp from the UI (e.g. "2026-11-04T09:30"), optional
    minutes: int = 0
    mode: str = "focus"  # "focus" | "stopwatch"
    quest_id: str | None = None
    path_id: str | None = None
    note: str = ""
    partial: bool = False  # stopped before the planned interval ended (still counts)
    xp: int = 0  # what it awarded (kept for history and the daily cap)
    coins: int = 0


@dataclass(frozen=True)
class Entry:
    """One calendar item. kind: quest | step | log | focus | bill_due | bill_paid."""

    kind: str
    title: str
    path_id: str = ""
    ref_id: str = ""  # quest / side quest / log / focus / bill id


@dataclass
class SetEntry:
    """One set. Every field is optional so bodyweight, weighted and cardio sets all fit.
    weight is stored in `unit` exactly as entered (never silently converted)."""

    reps: int | None = None
    weight: float | None = None
    unit: str = "kg"  # "kg" | "lb"
    distance_km: float | None = None
    seconds: int | None = None


@dataclass
class ExerciseEntry:
    name: str
    sets: list[SetEntry] = field(default_factory=list)


@dataclass
class WorkoutSession:
    id: str
    day: str  # ISO date
    started: str = ""  # free-form time from the UI, e.g. "18:30", optional
    type: str = "strength"  # see WORKOUT_TYPES
    minutes: int = 0
    effort: int = 5  # perceived effort 1..10
    notes: str = ""
    quest_id: str | None = None
    path_id: str = "warrior"
    exercises: list[ExerciseEntry] = field(default_factory=list)
    xp: int = 0  # what it awarded (history + daily cap); edits never change it
    coins: int = 0


@dataclass
class WorkoutTemplate:
    """A routine: a named list of exercises (sets are the planned ones, may be empty)."""

    id: str
    name: str
    type: str = "strength"
    minutes: int = 0
    exercises: list[ExerciseEntry] = field(default_factory=list)
    notes: str = ""


@dataclass
class SleepEntry:
    """One night. bedtime/wake are 'HH:MM'; wake <= bedtime means it crossed midnight."""

    id: str
    night_of: str  # ISO date of the evening the night started
    bedtime: str  # "HH:MM"
    wake: str  # "HH:MM"
    naps_min: int = 0
    restedness: int | None = None  # 1..5, optional
    note: str = ""
    logged_on: str = ""  # ISO date it was logged (for the daily XP cap)
    xp: int = 0


@dataclass
class WaterEntry:
    id: str
    day: str  # ISO date
    time: str = ""  # "HH:MM", optional
    amount_ml: int = 0


@dataclass
class EnergyCheckin:
    id: str
    day: str  # ISO date
    time: str = ""  # "HH:MM", optional
    level: str = "okay"  # "low" | "okay" | "high"
    note: str = ""


@dataclass
class JournalEntry:
    """A daily reflection or mindfulness entry (schema 5 additive)."""

    id: str
    day: str  # ISO date
    time: str = ""  # "HH:MM"
    mood: str = "good"  # "great" | "good" | "neutral" | "tired" | "stressed"
    gratitude: str = ""  # "One thing I am grateful for..."
    highlight: str = ""  # "Best moment of today..."
    notes: str = ""  # Free-form journaling / thoughts
    tags: list[str] = field(default_factory=list)
    xp: int = 20  # XP awarded to the Monk / Mind Path


@dataclass
class WaterSettings:
    daily_goal_ml: int | None = None  # None = no goal (no universal target)
    unit: str = "ml"  # display unit; amounts are always stored in ml
    quick_amounts: list[int] = field(default_factory=lambda: [250, 500])  # ml


@dataclass
class ReminderSettings:
    """What planned_reminders schedules. Times are 'HH:MM' local; active_days are weekday
    numbers 0=Mon..6=Sun (water reminders only)."""

    enabled: bool = True  # master switch
    quiet_start: str = "22:00"
    quiet_end: str = "07:00"  # quiet_start == quiet_end = no quiet hours
    bills_on: bool = True
    bill_days_before: int = 1
    bill_time: str = "09:00"
    daily_on: bool = True
    daily_time: str = "09:00"
    water_on: bool = False  # opt-in
    water_interval_min: int = 120
    water_active_days: list[int] = field(default_factory=lambda: list(range(7)))
    water_snooze_min: int = 15
    focus_on: bool = True
    comeback_on: bool = False  # gentle nudge after a few quiet days; off by default


@dataclass(frozen=True)
class Reminder:
    """A planned local notification. `id` is stable for the same event, so rescheduling
    replaces instead of duplicating."""

    id: str
    when: datetime
    title: str
    body: str
    category: str  # see REMINDER_CATEGORIES


@dataclass(frozen=True)
class PersonalRecord:
    """A descriptive best for one exercise (value in `unit`; "" for counts)."""

    kind: str  # "max_weight" | "max_reps" | "best_volume" | "longest_distance" | "longest_time"
    value: float
    unit: str
    day: str
    session_id: str


@dataclass(frozen=True)
class Insight:
    """A plain, ranged summary with the data behind it. No causal claims, no advice."""

    title: str
    text: str
    data: list[tuple[str, float]]
    kind: str  # "quests_by_path" | "workouts_per_week" | "sleep" | "water"


# --- Body + meals (schema 5) ---------------------------------------------------------------------
@dataclass
class WeightEntry:
    id: str
    day: str  # ISO date
    kg: float  # always stored in kg; BodyProfile.weight_unit is display only
    note: str = ""
    logged_on: str = ""  # ISO date it was logged (daily XP cap)
    xp: int = 0


@dataclass
class NutritionPlan:
    """An accepted Luma plan (a snapshot: it never changes by itself). Ranges are
    [low, target, high]. See core/nutrition.py for the formulas."""

    created: str  # ISO date
    goal: str = "maintain"  # lose | maintain | gain
    pace: str = "steady"  # gentle | steady | fast
    start_kg: float = 0.0
    goal_kg: float = 0.0
    bmr: int = 0
    tdee: int = 0
    floor: int = 0
    target_kcal: int = 0
    kcal_low: int = 0
    kcal_high: int = 0
    protein_g: list[int] = field(default_factory=lambda: [0, 0, 0])
    fat_g: list[int] = field(default_factory=lambda: [0, 0, 0])
    carbs_g: list[int] = field(default_factory=lambda: [0, 0, 0])
    fiber_g: int = 0
    water_ml: list[int] = field(default_factory=lambda: [0, 0])
    weekly_kg: float = 0.0  # negative = loss
    est_date: str = ""  # ISO date, "" = none (maintain / no change expected)
    floor_bound: bool = False
    sex_assumed: bool = False
    notes: list[str] = field(default_factory=list)


@dataclass
class BodyProfile:
    height_cm: float | None = None
    sex: str | None = None  # "female" | "male" | "unspecified" (prefer not to say); None = unset
    birth_year: int | None = None
    activity: str = "light"  # see nutrition.ACTIVITY_LEVELS
    weight_unit: str = "kg"  # display: "kg" | "lb"
    height_unit: str = "cm"  # display: "cm" | "ftin"
    goal_kg: float | None = None
    pace: str = "steady"
    plan: NutritionPlan | None = None


@dataclass
class NutritionSettings:
    calorie_tracking: bool = False  # opt-in: totals vs target, kcal on the log
    today_chip: bool = False  # kcal-left chip on Today (needs a plan + calorie tracking)
    keep_photos: bool = False  # scan photos are discarded unless this is on


@dataclass
class MealItem:
    """One food in a meal. Nutrients are for `grams` (already scaled). kcal_low/high is the
    honest range; grams typed from a scale (from_scale) narrow it."""

    name: str
    grams: float = 0.0
    kcal: float = 0.0
    protein: float = 0.0
    carbs: float = 0.0
    fat: float = 0.0
    food_id: str | None = None  # foods.py id or a CustomFood id
    from_scale: bool = False
    kcal_low: float = 0.0
    kcal_high: float = 0.0
    confidence: float | None = None  # recognizer confidence; None = picked by the user
    source: str = "db"  # see MEAL_ITEM_SOURCES


@dataclass
class MealEntry:
    id: str
    day: str  # ISO date
    meal: str = "snack"  # see MEAL_TYPES
    time: str = ""  # "HH:MM", optional
    items: list[MealItem] = field(default_factory=list)
    note: str = ""
    photo: str = ""  # file name in the data dir's meal_photos/ (kept only if the user chose)
    xp: int = 0


@dataclass
class CustomFood:
    """'My foods': the user's own entry, per 100 g, with a typical portion."""

    id: str
    name: str
    kcal: float
    protein: float = 0.0
    carbs: float = 0.0
    fat: float = 0.0
    portion_g: float = 100.0
    portion_label: str = "1 serving"


# --- Run / walk tracker (additive in schema 5) ---------------------------------------------------
RUN_MODES = ("walk", "run")


@dataclass
class RunEntry:
    """One GPS-tracked walk or run. Numbers are computed once at finish (core/run.py) and
    stored; the route is simplified (~4 m) to keep the save small. Also logged as a cardio
    WorkoutSession (workout_id) so Insights and workout history count it."""

    id: str
    day: str  # ISO date
    started: str = ""  # "HH:MM"
    mode: str = "run"  # see RUN_MODES
    distance_m: float = 0.0
    moving_s: int = 0
    elapsed_s: int = 0
    elev_gain_m: float | None = None  # None = no altitude in the fixes
    kcal: int = 0  # gross estimate (MET x kg x h)
    rest_kcal: int = 0  # resting burn over the same moving time
    steps: int = 0  # estimated from distance / step length
    weight_kg: float = 0.0  # weight used for kcal
    weight_assumed: bool = False  # True = the default weight was used
    splits: list[int] = field(default_factory=list)  # moving seconds per full km
    route: list[list[list[float]]] = field(default_factory=list)  # segments of [lat, lon]
    bests: dict[str, int] = field(default_factory=dict)  # tier id -> fastest seconds inside
    cleared: list[str] = field(default_factory=list)  # tier ids first cleared by this run
    goal: str = ""  # tier id picked before the start ("" = free run)
    workout_id: str = ""
    xp: int = 0  # everything it awarded (workout XP + challenge bonus)
    coins: int = 0
    basic: bool = False  # free run without the stretch ad: shown as steps + time only


@dataclass
class RunSettings:
    mode: str = "run"  # last picked mode
    keep_awake: bool = True  # keep the screen on while tracking
    voice_cues: bool = True  # spoken coaching cues (needs the voice on)
    cue_every: str = "1km"  # "1km" | "0.5km" | "5min" (see core/run_cues.CUE_EVERY)


@dataclass
class OnboardingAnswers:
    """'Personalize' answers (core/onboarding.py). Empty = skipped / never asked (old saves).
    Sex is not here: it lives in BodyProfile.sex so Body never asks twice."""

    focus: list[str] = field(default_factory=list)  # FOCUS_AREAS ids
    relate: dict[str, bool] = field(default_factory=dict)  # STATEMENTS id -> yes / no
    age_band: str = ""  # AGE_BANDS id (a band, never an exact age); "" = not given
    minutes: int = 0  # daily time budget (TIME_BUDGETS); 0 = not given
    day_time: str = ""  # DAY_TIMES id; "" = not given
    reminders: str = ""  # "on" | "off" | "" (not answered)
    paths: list[str] = field(default_factory=list)  # recommended Paths, best first
    difficulty: int = 0  # starter difficulty cap that was used; 0 = never applied
    done_on: str = ""  # ISO date the answers were last applied


@dataclass
class AvatarCustomization:
    """Modular layered character avatar (256x256 transparent PNG layers)."""

    body: str = "BaseBody"
    clothes: str = "Clothes1"
    eyes: str = "Eyes1"
    hair: str = "Hair1"
    mouth: str = "Mouth1"
    nose: str = "Nose1"
    makeups: list[str] = field(default_factory=list)  # up to 3 stacked makeups
    unlocked: list[str] = field(default_factory=list)  # unlocked cosmetic IDs


@dataclass
class Profile:
    name: str = "Legend"
    level: int = 1
    xp: int = 0  # XP inside the current overall level
    coins: int = 0
    path_xp: dict[str, int] = field(default_factory=dict)  # total XP per Path id
    theme_id: str = "arcane"
    owned_themes: list[str] = field(default_factory=lambda: ["arcane", "ember", "rose"])
    coins_today: int = 0  # coins earned on `coins_day` (for the daily cap)
    coins_day: str = ""  # ISO date
    avatar_id: str = "a1"
    onboarded: bool = False  # brand-new saves only; storage.load sets True for existing saves
    voice_on: bool = True
    voice_volume: float = 0.8  # 0.0..1.0
    sfx_on: bool = True  # UI sound effects (separate from the voice)
    sfx_volume: float = 0.6  # 0.0..1.0
    reduce_effects: bool = False  # simple fades instead of full overlay effects
    notify_sound: str = "notify_08"  # one of NOTIFY_SOUNDS: in-app notice ping + phone alerts
    modules: dict[str, bool] = field(default_factory=_default_modules)  # MODULES on/off
    water: WaterSettings = field(default_factory=WaterSettings)
    reminders: ReminderSettings = field(default_factory=ReminderSettings)
    nutrition: NutritionSettings = field(default_factory=NutritionSettings)
    onboarding: OnboardingAnswers = field(default_factory=OnboardingAnswers)
    center_pin: str | None = None  # More feature pinned to the nav's center slot (core/pins.py)
    language: str = "en"  # active UI language code (core/i18n.py)
    adventure_coins_today: int = 0  # creature trinket coins earned on `adventure_coins_day`
    adventure_coins_day: str = ""  # ISO date for separate adventure coin cap
    avatar_customization: AvatarCustomization = field(default_factory=AvatarCustomization)
    avatar_configured: bool = False  # True once the player saves their custom chibi avatar
    avatar_bonus_claimed: bool = False  # True once the +200 coin avatar bonus is claimed
    owned_cosmetics: list[str] = field(
        default_factory=lambda: [
            "particles_auto",
            "frame_default",
            "title_none",
            "pet_none",
            "fx_default",
        ]
    )
    particle_id: str = "particles_auto"
    frame_id: str = "frame_default"
    title_id: str = "title_none"
    equipped_titles: list[str] = field(default_factory=list)  # up to 3 simultaneously equipped titles
    pet_id: str = "pet_none"
    fx_style_id: str = "fx_default"
    daily_login_streak: int = 0
    last_login_claim: str = ""  # ISO date string ("YYYY-MM-DD")
    daily_login_claimed_days: list[int] = field(default_factory=list)
    currency: str = "₱"  # active currency symbol ("₱", "$", "€", "£", "¥", "₹", "₩", "A$", "C$", "S$")
    last_seen_changelog: str = ""  # date string "YYYY-MM-DD" when user last saw or dismissed "What's New"


# Notification sounds the user can pick (Settings): Sci-Fi pack notify_01..08.
NOTIFY_SOUNDS: tuple[str, ...] = tuple(f"notify_{i:02d}" for i in range(1, 9))
DEFAULT_NOTIFY_SOUND = "notify_08"


@dataclass
class Completion:
    """What a completion (quest or bill payment) awarded. All zeros = nothing happened."""

    xp: int = 0
    coins: int = 0
    levels_gained: int = 0
    path_id: str = ""
    path_levels_gained: int = 0
    capped: bool = False  # True if the daily coin cap cut the coin reward
    skill_unlocked: str | None = None  # skill name, when a side quest unlocked/ranked it up
    skill_rank: int | None = None  # the skill's new rank (1..3)
    ref_id: str = ""  # id of what was created, e.g. the FocusSession from log_focus


@dataclass
class StudyCard:
    """A flashcard. box/due/seen/right are spaced-repetition state (core/study.py)."""

    id: str
    term: str
    definition: str
    hint: str = ""
    example: str = ""
    tags: list[str] = field(default_factory=list)
    image: str = ""  # reserved: a photo file name (not used yet)
    box: int = 0  # Leitner box 0..5
    due: str = ""  # ISO date it is due again; "" = new
    seen: int = 0  # times answered (first try per session)
    right: int = 0  # of those, answered right
    last_seen: str = ""  # ISO date


@dataclass
class StudyDeck:
    id: str
    title: str
    subject: str = ""
    path_id: str = "scholar"  # the Path its XP goes to
    color: str = "#7FB2FF"
    created: str = ""  # ISO date
    cards: list[StudyCard] = field(default_factory=list)
    category: str = "course"  # see study.DECK_CATEGORIES (course / project / skill / path)
    daily_limit: int = 0  # due reviews per day for this deck; 0 = the global StudySettings one
    exam_date: str = ""  # ISO date of the exam, "" = none (shows a countdown)
    quest_id: str = ""  # linked quest, completed when a session on this deck finishes


@dataclass
class StudySettings:
    daily_limit: int = 20  # due reviews per deck per day (0 = no limit)


@dataclass
class StudySession:
    """One finished study run (exam / learn / flip)."""

    id: str
    deck_id: str
    day: str  # ISO date
    mode: str = "exam"  # see study.STUDY_MODES
    total: int = 0  # cards answered (first try)
    right: int = 0
    seconds: int = 0
    xp: int = 0
    coins: int = 0


# --- Premium foundation (additive in schema 5; rules in core/premium.py) -------------------------
@dataclass
class UsageCount:
    """Uses of one limited feature in one period (free: a day, premium: a Monday week)."""

    period: str = ""  # "D2026-11-05" (free day) or "W2026-11-02" (premium week, its Monday)
    used: int = 0
    bonus: int = 0  # extra uses granted by rewarded ads in this period


@dataclass
class PremiumState:
    """Usage counters, soft-offer timing and dev switches. NOT proof of purchase: the
    entitlement comes from the store (Part 2); dev_premium only counts in dev builds."""

    dev_premium: bool = False  # Settings -> Developer toggle (ignored in store builds)
    dev_unlocked: bool = False  # the Developer section was revealed (version tapped 7 times)
    usage: dict[str, UsageCount] = field(default_factory=dict)  # feature id -> counter
    ads_non_personalized: bool = False  # 13-17 band: Part 2 sends this flag to AdMob
    first_seen: str = ""  # ISO day the app first ran with this state (day-3 soft offer)
    offer_last: str = ""  # ISO day of the last soft offer notice
    offer_reasons: list[str] = field(default_factory=list)  # soft-offer reasons already used


@dataclass
class SaveData:
    """Everything that goes into the save file."""

    profile: Profile = field(default_factory=Profile)
    quests: list[Quest] = field(default_factory=list)
    bills: list[Bill] = field(default_factory=list)
    expenses: list[Any] = field(default_factory=list)  # ExpenseEntry list (schema 5 additive)
    split_bills: list[Any] = field(default_factory=list)  # SplitBill list (schema 5 additive)
    savings_goals: list[SavingsGoal] = field(default_factory=list)
    saved_qr_path: str = ""  # Digital bank QR code image path for quick payments
    rewards: list[Reward] = field(default_factory=list)
    logs: list[LogEntry] = field(default_factory=list)
    side_quests: list[SideQuest] = field(default_factory=list)
    skills: list[Skill] = field(default_factory=list)
    templates: list[QuestTemplate] = field(default_factory=list)  # user + edited built-ins
    hidden_templates: list[str] = field(default_factory=list)  # built-in ids the user hid
    focus_sessions: list[FocusSession] = field(default_factory=list)
    workouts: list[WorkoutSession] = field(default_factory=list)
    workout_templates: list[WorkoutTemplate] = field(default_factory=list)
    sleep: list[SleepEntry] = field(default_factory=list)
    water: list[WaterEntry] = field(default_factory=list)
    water_goal_days: dict[str, int] = field(default_factory=dict)  # ISO day -> XP awarded
    energy: list[EnergyCheckin] = field(default_factory=list)
    body: BodyProfile = field(default_factory=BodyProfile)
    weights: list[WeightEntry] = field(default_factory=list)
    meals: list[MealEntry] = field(default_factory=list)
    custom_foods: list[CustomFood] = field(default_factory=list)
    favorite_foods: list[str] = field(default_factory=list)  # food ids (built-in or custom)
    runs: list[RunEntry] = field(default_factory=list)  # GPS walks/runs (additive, schema 5)
    run_settings: RunSettings = field(default_factory=RunSettings)
    decks: list[StudyDeck] = field(default_factory=list)  # Study flashcards (additive, schema 5)
    study_sessions: list[StudySession] = field(default_factory=list)
    study_settings: StudySettings = field(default_factory=StudySettings)
    premium: PremiumState = field(default_factory=PremiumState)  # additive, schema 5
    star_iron: int = 0  # Star-Iron Ore earned from lifting tonnage (1 kg = 1 ore)
    exercise_prs: dict[str, float] = field(default_factory=dict)  # exercise_id -> max_weight_kg
    unlocked_workout_traits: list[str] = field(default_factory=list)  # awakened traits
    grove: Any = None  # GroveState (Mind Grove fitness farm, schema 5 additive)
    journals: list[JournalEntry] = field(default_factory=list)  # Daily journal reflections (schema 5 additive)
    next_id: int = 1
    legacy: dict[str, Any] | None = None  # raw v0 hero.json, kept verbatim after migration
