"""Save/load the game as human-readable JSON ("schema": 5), migrating schemas 4, 3, 2, 1 and the
v0 hero.json. Also full JSON backup/restore and CSV export of the tables.

Schema 1 -> 2 adds side_quests, skills and the profile fields avatar_id, onboarded, voice_on,
voice_volume. Every loaded save (schema 1, v0, or 2 without the key) counts as onboarded.

Schema 2 -> 3 (v1.2) adds, all with defaults so nothing is lost:
- templates, hidden_templates, focus_sessions (top level, empty lists);
- Quest.template_id; Reward.archived, Reward.redeemed_costs (filled with the current cost per
  past redemption); Bill.archived, Bill.start_cycle (0), Bill.paid_due (the due date each past
  payment covered, recomputed from the first due date exactly as before) and Bill.paid_amounts
  (the current amount per past payment); SideQuest.ordered/target_date/paused;
  Step.skipped_on.

Schema 3 -> 4 (v1.3) adds, all with defaults so nothing is lost:
- top level: workouts, workout_templates, sleep, water, energy (empty lists) and
  water_goal_days ({});
- Profile.modules (every module on), Profile.water (WaterSettings: no goal, ml), Profile.reminders
  (ReminderSettings defaults), and path_xp["monk"] = 0 (the new 7th Path);
- Bill.note, Bill.rewarded_on (every past payment day, so un-marking and re-paying on such a day
  gives no second reward); Reward.note.
Quests made from the old self-care templates keep their Path (history is not rewritten), and
old "workout"/"sleep" log entries stay as they are.

Schema 4 -> 5 (Body + Meals) adds, all with defaults so nothing is lost:
- top level: body (BodyProfile: nothing set, no plan), weights, meals, custom_foods,
  favorite_foods (empty lists);
- Profile.nutrition (NutritionSettings: calorie tracking off, Today chip off, photos discarded);
- Profile.modules gains "body" and "meals" (on, like every module).
Older schemas get the same defaults on the way up.

Additive inside schema 5 (no bump; a save without the keys loads with defaults):
- runs (RunEntry list, empty) and run_settings (RunSettings: run mode, keep screen awake);
- Profile.modules gains "run" (on, like every module).
- Profile.onboarding (OnboardingAnswers: everything empty = never personalized).
- decks (StudyDeck list with their StudyCards), study_sessions (StudySession list) and
  study_settings (StudySettings: 20 due reviews per deck per day).
- premium (PremiumState: no usage, dev switches off, no offers shown) and RunEntry.basic
  (False = a full-tracking run, as every run before it). PremiumState is never proof of
  purchase: see core/premium.py.

Uses Flet's per-app data dir on mobile, home dir on PC.
"""

import csv
import io
import json
import os
import re
from dataclasses import asdict, fields
from datetime import date
from pathlib import Path
from typing import Any

from lol.core import avatar_catalog
from lol.core.catalog import FREE_THEMES
from lol.core.finance import ExpenseEntry, SavingsGoal, SplitBill, SplitMember
from lol.core.models import (
    DEFAULT_NOTIFY_SOUND,
    MODULES,
    NOTIFY_SOUNDS,
    AvatarCustomization,
    Bill,
    BodyProfile,
    CustomFood,
    EnergyCheckin,
    ExerciseEntry,
    FocusSession,
    LogEntry,
    MealEntry,
    MealItem,
    NutritionPlan,
    NutritionSettings,
    OnboardingAnswers,
    PremiumState,
    Profile,
    Quest,
    QuestTemplate,
    ReminderSettings,
    Reward,
    RunEntry,
    RunSettings,
    SaveData,
    SetEntry,
    SideQuest,
    Skill,
    SleepEntry,
    Step,
    StudyCard,
    StudyDeck,
    StudySession,
    StudySettings,
    UsageCount,
    WaterEntry,
    WaterSettings,
    WeightEntry,
    WorkoutSession,
    WorkoutTemplate,
)

SCHEMA = 5
NEW_PATH = "monk"  # added in schema 4; existing saves get path_xp[NEW_PATH] = 0
SAVE_NAME = "save.json"
V0_NAME = "hero.json"  # the old v0 save; read and migrated if no save.json exists yet
V0_DEFAULT_PATH = "warrior"  # v0 quests whose stat has no matching Path land here
V0_STAT_TO_PATH = {"health": "warrior", "mind": "scholar", "wealth": "steward"}
LIST_KEYS = ("quests", "bills", "rewards", "logs", "side_quests", "skills", "templates",
             "hidden_templates", "focus_sessions", "workouts", "workout_templates", "sleep",
             "water", "energy", "weights", "meals", "custom_foods", "favorite_foods", "runs",
             "decks", "study_sessions", "expenses", "split_bills", "savings_goals")
STR_LIST_KEYS = ("hidden_templates", "favorite_foods")
PHOTO_DIR = "meal_photos"


def data_dir() -> Path:
    # FLET_APP_STORAGE_DATA is set by Flet on packaged mobile/desktop builds.
    root = os.getenv("FLET_APP_STORAGE_DATA") or Path.home() / ".lifeoflegends"
    path = Path(root)
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_path() -> Path:
    return data_dir() / SAVE_NAME


# --- dict <-> dataclasses ------------------------------------------------------------------------
def to_dict(data: SaveData) -> dict[str, Any]:
    out = {"schema": SCHEMA, **asdict(data)}
    if out["legacy"] is None:
        del out["legacy"]
    return out


def _build(cls, raw: dict[str, Any]):
    """Build a dataclass, ignoring unknown keys (forward compat); missing keys use defaults."""
    names = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in raw.items() if k in names})


def _profile(raw: dict[str, Any], schema: int = SCHEMA) -> Profile:
    """Profile from a v1 save. Saves written before Arcane existed default to Ember (the old
    default) and get every free theme added to owned_themes; the active theme never changes.
    A loaded save is an existing player, so `onboarded` defaults to True when missing. Saves
    older than schema 4 get path_xp["monk"] = 0; nested settings and modules get defaults."""
    raw = {"theme_id": "ember", "owned_themes": ["ember"], "onboarded": True, **raw}
    profile = _build(Profile, raw)
    profile.owned_themes = list(profile.owned_themes)
    for theme_id in FREE_THEMES:
        if theme_id not in profile.owned_themes:
            profile.owned_themes.append(theme_id)
    profile.path_xp = dict(profile.path_xp)
    if profile.notify_sound not in NOTIFY_SOUNDS:  # additive (schema 5): missing/unknown
        profile.notify_sound = DEFAULT_NOTIFY_SOUND
    if schema < 4:  # migrating: the new Path starts at 0 XP
        profile.path_xp.setdefault(NEW_PATH, 0)
    profile.modules = {**{m: True for m in MODULES}, **dict(raw.get("modules") or {})}
    water = raw.get("water")
    profile.water = _build(WaterSettings, water) if isinstance(water, dict) else WaterSettings()
    profile.water.quick_amounts = list(profile.water.quick_amounts)
    rem = raw.get("reminders")
    profile.reminders = (_build(ReminderSettings, rem) if isinstance(rem, dict)
                         else ReminderSettings())
    profile.reminders.water_active_days = list(profile.reminders.water_active_days)
    nut = raw.get("nutrition")
    profile.nutrition = (_build(NutritionSettings, nut) if isinstance(nut, dict)
                         else NutritionSettings())
    ob = raw.get("onboarding")
    profile.onboarding = (_build(OnboardingAnswers, ob) if isinstance(ob, dict)
                          else OnboardingAnswers())
    profile.onboarding.focus = [str(x) for x in profile.onboarding.focus or []]
    profile.onboarding.relate = {str(k): bool(v) for k, v in
                                 dict(profile.onboarding.relate or {}).items()}
    profile.onboarding.paths = [str(x) for x in profile.onboarding.paths or []]
    pin = raw.get("center_pin")  # additive: missing / junk -> empty center slot
    profile.center_pin = pin if isinstance(pin, str) and pin else None
    from lol.core.i18n import LANGUAGES

    lang = raw.get("language")
    profile.language = lang if isinstance(lang, str) and lang in LANGUAGES else "en"
    av_raw = raw.get("avatar_customization")
    av_built = (
        _build(AvatarCustomization, av_raw)
        if isinstance(av_raw, dict)
        else AvatarCustomization()
    )
    profile.avatar_customization = avatar_catalog.sanitize(av_built)
    profile.avatar_configured = bool(raw.get("avatar_configured", False))
    profile.avatar_bonus_claimed = bool(raw.get("avatar_bonus_claimed", False))
    from lol.core import cosmetics as cos

    raw_owned_cos = raw.get("owned_cosmetics")
    profile.owned_cosmetics = (
        [str(x) for x in raw_owned_cos if isinstance(x, str)]
        if isinstance(raw_owned_cos, list)
        else []
    )
    for free_id in cos.FREE_COSMETICS:
        if free_id not in profile.owned_cosmetics:
            profile.owned_cosmetics.append(free_id)
    profile.particle_id = cos.get_cosmetic(raw.get("particle_id"), "particles").id
    profile.frame_id = cos.get_cosmetic(raw.get("frame_id"), "frame").id
    profile.title_id = cos.get_cosmetic(raw.get("title_id"), "title").id
    raw_equipped_titles = raw.get("equipped_titles")
    if isinstance(raw_equipped_titles, list):
        profile.equipped_titles = [
            str(x) for x in raw_equipped_titles
            if isinstance(x, str) and x in cos.COSMETIC_BY_ID and x != "title_none"
        ][:3]
    elif profile.title_id and profile.title_id != "title_none":
        profile.equipped_titles = [profile.title_id]
    else:
        profile.equipped_titles = []
    profile.pet_id = cos.get_cosmetic(raw.get("pet_id"), "pet").id
    profile.fx_style_id = cos.get_cosmetic(raw.get("fx_style_id"), "fx_style").id
    profile.daily_login_streak = int(raw.get("daily_login_streak", 0) or 0)
    profile.last_login_claim = str(raw.get("last_login_claim", "") or "")
    raw_claimed = raw.get("daily_login_claimed_days")
    profile.daily_login_claimed_days = (
        [int(x) for x in raw_claimed if isinstance(x, (int, str)) and str(x).isdigit()]
        if isinstance(raw_claimed, list)
        else []
    )
    cur = raw.get("currency")
    profile.currency = cur if isinstance(cur, str) and cur.strip() else "₱"
    profile.last_seen_changelog = str(raw.get("last_seen_changelog", "") or "")
    return profile


def _body(raw: Any) -> BodyProfile:
    if not isinstance(raw, dict):
        return BodyProfile()
    body = _build(BodyProfile, raw)
    plan = raw.get("plan")
    body.plan = _plan(plan) if isinstance(plan, dict) else None
    return body


def _plan(raw: dict[str, Any]) -> NutritionPlan:
    p = _build(NutritionPlan, raw)
    p.protein_g, p.fat_g, p.carbs_g = list(p.protein_g), list(p.fat_g), list(p.carbs_g)
    p.water_ml, p.notes = list(p.water_ml), list(p.notes)
    return p


def _run(raw: dict[str, Any]) -> RunEntry:
    r = _build(RunEntry, raw)
    r.splits, r.cleared = [int(x) for x in r.splits], [str(x) for x in r.cleared]
    r.route = [[[float(p[0]), float(p[1])] for p in seg] for seg in r.route]
    r.bests = {str(k): int(v) for k, v in dict(r.bests).items()}
    return r


def _premium(raw: Any) -> PremiumState:
    """PremiumState (additive in schema 5); a missing or odd value loads as the default."""
    if not isinstance(raw, dict):
        return PremiumState()
    st = _build(PremiumState, raw)
    usage = raw.get("usage") if isinstance(raw.get("usage"), dict) else {}
    st.usage = {str(k): _build(UsageCount, v) for k, v in usage.items() if isinstance(v, dict)}
    st.offer_reasons = [str(x) for x in st.offer_reasons or []]
    return st


def _deck(raw: dict[str, Any]) -> StudyDeck:
    d = _build(StudyDeck, raw)
    d.cards = [_build(StudyCard, c) for c in raw.get("cards", []) if isinstance(c, dict)]
    for c in d.cards:
        c.tags = [str(t) for t in c.tags or []]
    return d


def _meal(raw: dict[str, Any]) -> MealEntry:
    m = _build(MealEntry, raw)
    m.items = [_build(MealItem, it) for it in raw.get("items", []) if isinstance(it, dict)]
    return m


def _exercises(items: list[dict[str, Any]]) -> list[ExerciseEntry]:
    out = []
    for ex in items or []:
        e = _build(ExerciseEntry, ex)
        e.sets = [_build(SetEntry, st) for st in ex.get("sets", [])]
        out.append(e)
    return out


def _workout(raw: dict[str, Any]) -> WorkoutSession:
    w = _build(WorkoutSession, raw)
    w.exercises = _exercises(raw.get("exercises", []))
    return w


def _workout_template(raw: dict[str, Any]) -> WorkoutTemplate:
    t = _build(WorkoutTemplate, raw)
    t.exercises = _exercises(raw.get("exercises", []))
    return t


def _side_quest(raw: dict[str, Any]) -> SideQuest:
    sq = _build(SideQuest, raw)
    sq.steps = [_build(Step, st) for st in raw.get("steps", [])]
    return sq


def _skill(raw: dict[str, Any]) -> Skill:
    skill = _build(Skill, raw)
    skill.chain_ids = list(skill.chain_ids)
    return skill


def _bill(raw: dict[str, Any]) -> Bill:
    """A bill; fills paid_due/paid_amounts for payments made before schema 3. Before schema 3 a
    bill was never re-anchored, so cycle n's due date is the first due date shifted n times."""
    from lol.core.game import bill_occurrence  # lazy: game imports storage

    bill = _build(Bill, raw)
    bill.paid, bill.paid_due = list(bill.paid), list(bill.paid_due)
    bill.paid_amounts = list(bill.paid_amounts)
    for n in range(len(bill.paid_due), len(bill.paid)):
        bill.paid_due.append(bill_occurrence(bill, n).isoformat())
    bill.paid_amounts += [bill.amount] * (len(bill.paid) - len(bill.paid_amounts))
    if "rewarded_on" not in raw:  # before schema 4: a payment day was a rewarded day
        bill.rewarded_on = sorted(set(bill.paid))
    bill.rewarded_on = list(bill.rewarded_on)
    return bill


def _reward(raw: dict[str, Any]) -> Reward:
    r = _build(Reward, raw)
    r.redeemed, r.redeemed_costs = list(r.redeemed), list(r.redeemed_costs)
    r.redeemed_costs += [r.cost] * (len(r.redeemed) - len(r.redeemed_costs))
    return r


_ID_NUM = re.compile(r"^[a-z]+(\d+)$")


def _split_bill(raw: dict[str, Any]) -> SplitBill:
    sb = _build(SplitBill, raw)
    sb.members = [_build(SplitMember, m) for m in raw.get("members", []) if isinstance(m, dict)]
    return sb


def _min_next_id(data: SaveData) -> int:
    """1 + the biggest numeric id suffix in use, so new ids never collide (built-in template
    ids like "t-skin-care" have no number and are ignored)."""
    ids = [x.id for group in (data.quests, data.bills, data.rewards, data.logs,
                              data.side_quests, data.templates, data.focus_sessions,
                              data.workouts, data.workout_templates, data.sleep, data.water,
                              data.energy, data.weights, data.meals, data.custom_foods, data.runs,
                              data.decks, data.study_sessions, data.expenses, data.split_bills,
                              data.savings_goals,
                              [c for d in data.decks for c in d.cards])
           for x in group]
    nums = [int(m.group(1)) for i in ids if (m := _ID_NUM.match(str(i)))]
    return max(nums, default=0) + 1


def from_dict(raw: dict[str, Any], today: date | None = None) -> SaveData:
    """Any supported save shape (v0, schema 1, 2, 3, 4, 5) -> SaveData. `today` stamps migrated
    v0 completions. Older schemas lack newer keys: defaults fill them (see module doc)."""
    if "schema" not in raw:
        return migrate_v0(raw, today or date.today())
    if raw["schema"] > SCHEMA:
        raise ValueError(f"save schema {raw['schema']} is newer than this app ({SCHEMA})")
    data = SaveData(
        profile=_profile(raw.get("profile", {}), raw["schema"]),
        quests=[_build(Quest, q) for q in raw.get("quests", [])],
        bills=[_bill(b) for b in raw.get("bills", [])],
        expenses=[_build(ExpenseEntry, e) for e in raw.get("expenses", []) if isinstance(e, dict)],
        split_bills=[_split_bill(sb) for sb in raw.get("split_bills", []) if isinstance(sb, dict)],
        savings_goals=[_build(SavingsGoal, sg) for sg in raw.get("savings_goals", []) if isinstance(sg, dict)],
        saved_qr_path=str(raw.get("saved_qr_path", "") or ""),
        rewards=[_reward(r) for r in raw.get("rewards", [])],
        logs=[_build(LogEntry, e) for e in raw.get("logs", [])],
        side_quests=[_side_quest(sq) for sq in raw.get("side_quests", [])],
        skills=[_skill(s) for s in raw.get("skills", [])],
        templates=[_build(QuestTemplate, t) for t in raw.get("templates", [])],
        hidden_templates=list(raw.get("hidden_templates", [])),
        focus_sessions=[_build(FocusSession, f) for f in raw.get("focus_sessions", [])],
        workouts=[_workout(w) for w in raw.get("workouts", [])],
        workout_templates=[_workout_template(t) for t in raw.get("workout_templates", [])],
        sleep=[_build(SleepEntry, e) for e in raw.get("sleep", [])],
        water=[_build(WaterEntry, e) for e in raw.get("water", [])],
        water_goal_days={str(k): int(v) for k, v in (raw.get("water_goal_days") or {}).items()},
        energy=[_build(EnergyCheckin, e) for e in raw.get("energy", [])],
        body=_body(raw.get("body")),
        weights=[_build(WeightEntry, e) for e in raw.get("weights", [])],
        meals=[_meal(m) for m in raw.get("meals", [])],
        custom_foods=[_build(CustomFood, f) for f in raw.get("custom_foods", [])],
        favorite_foods=[str(x) for x in raw.get("favorite_foods", [])],
        runs=[_run(r) for r in raw.get("runs", [])],
        run_settings=(_build(RunSettings, raw["run_settings"])
                      if isinstance(raw.get("run_settings"), dict) else RunSettings()),
        decks=[_deck(d) for d in raw.get("decks", [])],
        study_sessions=[_build(StudySession, x) for x in raw.get("study_sessions", [])],
        study_settings=(_build(StudySettings, raw["study_settings"])
                        if isinstance(raw.get("study_settings"), dict) else StudySettings()),
        premium=_premium(raw.get("premium")),
        star_iron=int(raw.get("star_iron", 0)),
        exercise_prs={str(k): float(v) for k, v in (raw.get("exercise_prs") or {}).items()},
        unlocked_workout_traits=[str(x) for x in raw.get("unlocked_workout_traits", [])],
        next_id=raw.get("next_id", 1),
        legacy=raw.get("legacy"),
    )
    data.next_id = max(data.next_id, _min_next_id(data))
    return data


def migrate_v0(raw: dict[str, Any], today: date) -> SaveData:
    """v0 {name, level, xp, quests[{title, xp, stat, done}]} -> current schema.

    Hero level/XP become the overall profile. Old quests become `once` quests (Path from their
    stat, else V0_DEFAULT_PATH) keeping their XP; done ones are marked done on `today` and their
    XP is credited to that Path. The raw v0 dict is kept verbatim in `legacy`, so nothing is lost.
    """
    from lol.core.game import COINS_BY_DIFFICULTY  # lazy: game imports storage

    profile = Profile(
        name=raw.get("name", "Legend"), level=raw.get("level", 1), xp=raw.get("xp", 0),
        onboarded=True, path_xp={NEW_PATH: 0},
    )
    quests = []
    for i, old in enumerate(raw.get("quests", []), start=1):
        path_id = V0_STAT_TO_PATH.get(old.get("stat", ""), V0_DEFAULT_PATH)
        done = bool(old.get("done", False))
        quests.append(Quest(
            id=f"q{i}", title=old.get("title", "Quest"), path_id=path_id, kind="once",
            xp=int(old.get("xp", 0)), coins=COINS_BY_DIFFICULTY[1], difficulty=1,
            created=today.isoformat(), done_on=[today.isoformat()] if done else [],
        ))
        if done:
            profile.path_xp[path_id] = profile.path_xp.get(path_id, 0) + int(old.get("xp", 0))
    return SaveData(
        profile=profile, quests=quests, next_id=len(quests) + 1, legacy=json.loads(json.dumps(raw))
    )


# --- files ---------------------------------------------------------------------------------------
def save(data: SaveData, path: Path | None = None) -> Path:
    path = Path(path) if path else default_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(export_json(data), encoding="utf-8")
    tmp.replace(path)  # atomic swap so a crash never leaves a half-written save
    return path


def load(path: Path | None = None, today: date | None = None) -> SaveData:
    """Load a save. With no path: save.json, else migrate an old hero.json (left untouched as a
    backup), else a fresh game. A v0-shaped file at an explicit path is migrated too."""
    if path is None:
        path = default_path()
        if not path.exists() and (path.parent / V0_NAME).exists():
            path = path.parent / V0_NAME
    path = Path(path)
    if not path.exists():
        return SaveData()
    raw = json.loads(path.read_text(encoding="utf-8"))
    return from_dict(raw, today)


# --- backup and export ---------------------------------------------------------------------------
def export_json(data: SaveData) -> str:
    """The full backup: exactly the save file's JSON (schema 5, readable, UTF-8 text)."""
    return json.dumps(to_dict(data), indent=2, ensure_ascii=False)


def import_json(text: str, today: date | None = None) -> SaveData:
    """Restore a backup (any supported schema, migrated). Raises ValueError with a readable
    message if the text is not a valid Life of Legends backup; nothing is changed then. The
    caller confirms with the player and then replaces Game.data (and saves)."""
    try:
        raw = json.loads(text)
    except (json.JSONDecodeError, TypeError) as e:
        raise ValueError(f"not a JSON backup: {e}") from e
    if not isinstance(raw, dict):
        raise ValueError("backup must be a JSON object")  # noqa: TRY004 - one error type
    if "schema" in raw:
        schema = raw["schema"]
        if not isinstance(schema, int) or isinstance(schema, bool) or schema < 1:
            raise ValueError(f"bad schema value: {schema!r}")
        if not isinstance(raw.get("profile", {}), dict):
            raise ValueError("profile must be an object")
        if not isinstance(raw.get("water_goal_days", {}), dict):
            raise ValueError("water_goal_days must be an object")
        if raw.get("body") is not None and not isinstance(raw["body"], dict):
            raise ValueError("body must be an object")
        if raw.get("run_settings") is not None and not isinstance(raw["run_settings"], dict):
            raise ValueError("run_settings must be an object")
        if raw.get("study_settings") is not None and not isinstance(raw["study_settings"], dict):
            raise ValueError("study_settings must be an object")
        for key in LIST_KEYS:
            items = raw.get(key, [])
            want = str if key in STR_LIST_KEYS else dict
            if not isinstance(items, list) or not all(isinstance(x, want) for x in items):
                raise ValueError(f"{key} must be a list of {want.__name__}")
    elif not isinstance(raw.get("quests", []), list):
        raise ValueError("v0 quests must be a list")
    try:
        data = from_dict(raw, today)
    except (TypeError, KeyError, AttributeError) as e:
        raise ValueError(f"backup is missing or has bad fields: {e}") from e
    _validate(data)
    return data


def _validate(data: SaveData) -> None:
    """Dates must parse and ids must be unique per table."""
    def check_day(value: Any, where: str) -> None:
        try:
            date.fromisoformat(value)
        except (TypeError, ValueError) as e:
            raise ValueError(f"bad date {value!r} in {where}") from e

    for q in data.quests:
        for d in q.done_on:
            check_day(d, f"quest {q.id}")
    for b in data.bills:
        check_day(b.due, f"bill {b.id}")
        for d in (*b.paid, *b.paid_due):
            check_day(d, f"bill {b.id}")
    for r in data.rewards:
        for d in r.redeemed:
            check_day(d, f"reward {r.id}")
    for e in data.logs:
        check_day(e.day, f"log {e.id}")
    for f in data.focus_sessions:
        check_day(f.day, f"focus session {f.id}")
    for w in data.workouts:
        check_day(w.day, f"workout {w.id}")
    for e in data.sleep:
        check_day(e.night_of, f"sleep {e.id}")
    for group, label in ((data.water, "water"), (data.energy, "energy check-in")):
        for x in group:
            check_day(x.day, f"{label} {x.id}")
    for w in data.weights:
        check_day(w.day, f"weight {w.id}")
    for m in data.meals:
        check_day(m.day, f"meal {m.id}")
    for r in data.runs:
        check_day(r.day, f"run {r.id}")
    for s in data.study_sessions:
        check_day(s.day, f"study session {s.id}")
    for d in data.water_goal_days:
        check_day(d, "water_goal_days")
    for sq in data.side_quests:
        for st in sq.steps:
            for d in (st.done_on, st.skipped_on):
                if d:
                    check_day(d, f"side quest {sq.id}")
    for name in ("quests", "bills", "rewards", "logs", "side_quests", "templates",
                 "focus_sessions", "workouts", "workout_templates", "sleep", "water", "energy",
                 "weights", "meals", "custom_foods", "runs", "decks", "study_sessions",
                 "savings_goals"):
        ids = [x.id for x in getattr(data, name)]
        if len(ids) != len(set(ids)):
            raise ValueError(f"duplicate ids in {name}")


def summary(data: SaveData) -> dict[str, int]:
    """What a backup contains, for the "what's included" line."""
    return {
        "quests": len(data.quests),
        "quest_completions": sum(len(q.done_on) for q in data.quests),
        "side_quests": len(data.side_quests),
        "skills": len(data.skills),
        "bills": len(data.bills),
        "bill_payments": sum(len(b.paid) for b in data.bills),
        "rewards": len(data.rewards),
        "redemptions": sum(len(r.redeemed) for r in data.rewards),
        "logs": len(data.logs),
        "focus_sessions": len(data.focus_sessions),
        "templates": len(data.templates),
        "workouts": len(data.workouts),
        "workout_templates": len(data.workout_templates),
        "sleep_entries": len(data.sleep),
        "water_entries": len(data.water),
        "energy_checkins": len(data.energy),
        "weight_entries": len(data.weights),
        "meals": len(data.meals),
        "custom_foods": len(data.custom_foods),
        "runs": len(data.runs),
        "study_decks": len(data.decks),
        "study_cards": sum(len(d.cards) for d in data.decks),
        "study_sessions": len(data.study_sessions),
        "savings_goals": len(data.savings_goals),
    }


CSV_TABLES: dict[str, tuple[str, ...]] = {
    "quests.csv": ("id", "title", "path_id", "kind", "difficulty", "xp", "coins", "note",
                   "minutes", "created", "times_done", "template_id"),
    "quest_completions.csv": ("quest_id", "title", "path_id", "day"),
    "side_quest_steps.csv": ("side_quest_id", "skill_name", "path_id", "rank_target", "ordered",
                             "paused", "abandoned", "target_date", "step_index", "step_title",
                             "step_note", "xp", "coins", "done_on", "skipped_on"),
    "bills.csv": ("id", "name", "amount", "repeat", "due", "start_cycle", "archived",
                  "times_paid", "note"),
    "bill_payments.csv": ("bill_id", "name", "paid_on", "cycle_due", "amount"),
    "rewards.csv": ("id", "title", "cost", "kind", "archived", "times_redeemed", "note"),
    "reward_redemptions.csv": ("reward_id", "title", "day", "cost"),
    "logs.csv": ("id", "day", "kind", "minutes", "text"),
    "focus_sessions.csv": ("id", "day", "started", "minutes", "mode", "quest_id", "path_id",
                           "note", "partial", "xp", "coins"),
    "workouts.csv": ("id", "day", "started", "type", "minutes", "effort", "path_id", "quest_id",
                     "notes", "exercises", "xp", "coins"),
    "workout_sets.csv": ("workout_id", "day", "exercise_index", "exercise", "set_index", "reps",
                         "weight", "unit", "distance_km", "seconds"),
    "sleep.csv": ("id", "night_of", "bedtime", "wake", "minutes", "naps_min", "restedness",
                  "note", "xp"),
    "water.csv": ("id", "day", "time", "amount_ml"),
    "energy.csv": ("id", "day", "time", "level", "note"),
    "weights.csv": ("id", "day", "kg", "note"),
    "meal_items.csv": ("meal_id", "day", "meal", "time", "item_index", "name", "grams", "kcal",
                       "kcal_low", "kcal_high", "protein", "carbs", "fat", "food_id",
                       "from_scale", "source"),
    "custom_foods.csv": ("id", "name", "kcal_per_100g", "protein", "carbs", "fat", "portion_g",
                         "portion_label"),
    "runs.csv": ("id", "day", "started", "mode", "distance_km", "moving_s", "elapsed_s",
                 "pace_s_per_km", "elev_gain_m", "kcal", "rest_kcal", "steps", "splits",
                 "cleared", "xp", "coins"),
    "study_cards.csv": ("deck_id", "deck", "subject", "card_id", "term", "definition", "hint",
                        "example", "tags", "box", "due", "seen", "right"),
    "study_sessions.csv": ("id", "deck_id", "day", "mode", "total", "right", "seconds", "xp",
                           "coins"),
}
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def _cell(value: Any) -> Any:
    """CSV-safe cell: None -> "", and text that a spreadsheet would run as a formula gets a
    leading apostrophe (numbers are left alone)."""
    if value is None:
        return ""
    if isinstance(value, str) and value.startswith(_FORMULA_START):
        return "'" + value
    return value


def _rows(data: SaveData) -> dict[str, list[tuple]]:
    t: dict[str, list[tuple]] = {name: [] for name in CSV_TABLES}
    for q in data.quests:
        t["quests.csv"].append((q.id, q.title, q.path_id, q.kind, q.difficulty, q.xp, q.coins,
                                q.note, q.minutes, q.created, len(q.done_on), q.template_id))
        t["quest_completions.csv"] += [(q.id, q.title, q.path_id, d) for d in q.done_on]
    for sq in data.side_quests:
        for i, st in enumerate(sq.steps):
            t["side_quest_steps.csv"].append((
                sq.id, sq.skill_name, sq.path_id, sq.rank_target, sq.ordered, sq.paused,
                sq.abandoned, sq.target_date, i, st.title, st.note, st.xp, st.coins,
                st.done_on, st.skipped_on))
    for b in data.bills:
        t["bills.csv"].append((b.id, b.name, b.amount, b.repeat, b.due, b.start_cycle,
                               b.archived, len(b.paid), b.note))
        for i, paid_on in enumerate(b.paid):
            due = b.paid_due[i] if i < len(b.paid_due) else None
            amount = b.paid_amounts[i] if i < len(b.paid_amounts) else b.amount
            t["bill_payments.csv"].append((b.id, b.name, paid_on, due, amount))
    for r in data.rewards:
        t["rewards.csv"].append((r.id, r.title, r.cost, r.kind, r.archived, len(r.redeemed),
                                 r.note))
        for i, d in enumerate(r.redeemed):
            cost = r.redeemed_costs[i] if i < len(r.redeemed_costs) else r.cost
            t["reward_redemptions.csv"].append((r.id, r.title, d, cost))
    for e in data.logs:
        t["logs.csv"].append((e.id, e.day, e.kind, e.minutes, e.text))
    for f in data.focus_sessions:
        t["focus_sessions.csv"].append((f.id, f.day, f.started, f.minutes, f.mode, f.quest_id,
                                        f.path_id, f.note, f.partial, f.xp, f.coins))
    from lol.core.game import sleep_minutes  # lazy: game imports storage

    for w in data.workouts:
        t["workouts.csv"].append((w.id, w.day, w.started, w.type, w.minutes, w.effort, w.path_id,
                                  w.quest_id, w.notes, len(w.exercises), w.xp, w.coins))
        for i, ex in enumerate(w.exercises):
            for j, st in enumerate(ex.sets):
                t["workout_sets.csv"].append((w.id, w.day, i, ex.name, j, st.reps, st.weight,
                                              st.unit, st.distance_km, st.seconds))
    for e in data.sleep:
        t["sleep.csv"].append((e.id, e.night_of, e.bedtime, e.wake,
                               sleep_minutes(e.bedtime, e.wake), e.naps_min, e.restedness,
                               e.note, e.xp))
    for e in data.water:
        t["water.csv"].append((e.id, e.day, e.time, e.amount_ml))
    for e in data.energy:
        t["energy.csv"].append((e.id, e.day, e.time, e.level, e.note))
    for w in data.weights:
        t["weights.csv"].append((w.id, w.day, w.kg, w.note))
    for m in data.meals:
        for i, it in enumerate(m.items):
            t["meal_items.csv"].append((m.id, m.day, m.meal, m.time, i, it.name, it.grams,
                                        round(it.kcal), round(it.kcal_low),
                                        round(it.kcal_high), round(it.protein, 1),
                                        round(it.carbs, 1), round(it.fat, 1), it.food_id,
                                        it.from_scale, it.source))
    for f in data.custom_foods:
        t["custom_foods.csv"].append((f.id, f.name, f.kcal, f.protein, f.carbs, f.fat,
                                      f.portion_g, f.portion_label))
    for r in data.runs:
        pace = round(r.moving_s / (r.distance_m / 1000)) if r.distance_m >= 10 else None
        t["runs.csv"].append((r.id, r.day, r.started, r.mode, round(r.distance_m / 1000, 3),
                              r.moving_s, r.elapsed_s, pace, r.elev_gain_m, r.kcal,
                              r.rest_kcal, r.steps, " ".join(map(str, r.splits)),
                              " ".join(r.cleared), r.xp, r.coins))
    for d in data.decks:
        for c in d.cards:
            t["study_cards.csv"].append((d.id, d.title, d.subject, c.id, c.term, c.definition,
                                         c.hint, c.example, " ".join(c.tags), c.box, c.due,
                                         c.seen, c.right))
    for x in data.study_sessions:
        t["study_sessions.csv"].append((x.id, x.deck_id, x.day, x.mode, x.total, x.right,
                                        x.seconds, x.xp, x.coins))
    return t


def export_csv(data: SaveData) -> dict[str, str]:
    """Readable tables, {file name: CSV text with a header row}. Lists (completions, payments,
    redemptions) get their own tables, one row per entry. Export only: restore uses JSON."""
    out = {}
    for name, rows in _rows(data).items():
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(CSV_TABLES[name])
        w.writerows([_cell(v) for v in row] for row in rows)
        out[name] = buf.getvalue()
    return out


# --- meal photos (kept only when the user opts in) -----------------------------------------------
def save_photo(name: str, data: bytes) -> str:
    """Write a kept meal photo into the data dir; returns the file name stored on the meal."""
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", name)
    folder = data_dir() / PHOTO_DIR
    folder.mkdir(parents=True, exist_ok=True)
    (folder / safe).write_bytes(data)
    return safe


def photo_path(name: str) -> Path | None:
    if not name:
        return None
    p = data_dir() / PHOTO_DIR / Path(name).name
    return p if p.exists() else None


def delete_photo(name: str) -> None:
    p = photo_path(name)
    if p is not None:
        p.unlink(missing_ok=True)
