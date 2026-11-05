"""v1.3: locked-down editing, the Monk Path, and save schema 4."""

import json
from datetime import date, timedelta

import pytest

from lol.core import catalog, storage
from lol.core.game import (
    COINS_BY_DIFFICULTY,
    STEWARD_BILL_XP,
    XP_BY_DIFFICULTY,
    Game,
)
from lol.core.models import ExerciseEntry, SetEntry

D = date(2026, 11, 4)


# --- edit limits ---------------------------------------------------------------------------------
def test_rename_quest_only_changes_name_note_difficulty():
    g = Game()
    q = g.add_quest("Walk", "warrior", kind="daily", difficulty=1, today=D, coins=5, xp=10)
    g.complete_quest(q.id, D)
    earned = (g.profile.xp, g.profile.coins, dict(g.profile.path_xp))
    g.rename_quest(q.id, title="  Evening walk ", note="slow")
    assert (q.title, q.note, q.xp, q.coins, q.path_id, q.kind) == (
        "Evening walk", "slow", 10, 5, "warrior", "daily")  # same difficulty: rewards kept
    g.rename_quest(q.id, difficulty=3)
    assert (q.difficulty, q.xp, q.coins) == (3, XP_BY_DIFFICULTY[3], COINS_BY_DIFFICULTY[3])
    assert (g.profile.xp, g.profile.coins, g.profile.path_xp) == earned  # history untouched
    assert q.done_on == [D.isoformat()]
    c = g.complete_quest(q.id, D + timedelta(days=1))
    assert c.xp == XP_BY_DIFFICULTY[3]  # future completions use the new difficulty
    with pytest.raises(ValueError):
        g.rename_quest(q.id, title=" ")
    with pytest.raises(ValueError):
        g.rename_quest(q.id, difficulty=7)
    with pytest.raises(TypeError):
        g.rename_quest(q.id, path_id="chef")  # not exposed


def test_rename_reward_keeps_price_and_note_field():
    g = Game()
    r = g.add_reward("Movie", 100, note="with friends")
    assert r.note == "with friends"
    g.rename_reward(r.id, title="Cinema", note="")
    assert (r.title, r.note, r.cost) == ("Cinema", "", 100)
    with pytest.raises(ValueError):
        g.rename_reward(r.id, title="")
    with pytest.raises(TypeError):
        g.rename_reward(r.id, cost=5)


def test_update_bill_name_and_note_only():
    g = Game()
    b = g.add_bill("Rent", 8000, D, "monthly", note="landlord")
    assert b.note == "landlord"
    g.update_bill(b.id, name="House rent", note="pay by GCash")
    assert (b.name, b.note, b.amount, b.due, b.repeat) == (
        "House rent", "pay by GCash", 8000.0, D.isoformat(), "monthly")
    with pytest.raises(ValueError):
        g.update_bill(b.id, name=" ")
    with pytest.raises(TypeError):
        g.update_bill(b.id, amount=1)


def test_mark_paid_then_unpaid_undoes_cycle_and_keeps_xp():
    g = Game()
    b = g.add_bill("Phone", 500, D, "monthly")
    c = g.mark_bill_paid(b.id, D)
    assert c.xp == STEWARD_BILL_XP and g.next_due(b) == date(2026, 12, 4)
    xp, coins = g.profile.path_xp["steward"], g.profile.coins
    assert g.mark_bill_unpaid(b.id) is True
    assert (b.paid, b.paid_due, b.paid_amounts) == ([], [], [])
    assert g.next_due(b) == D and g.bill_status(b, D) == "due_soon"
    assert (g.profile.path_xp["steward"], g.profile.coins) == (xp, coins)  # never taken back
    again = g.mark_bill_paid(b.id, D)  # same day: no second reward (no pay/unpay farming)
    assert again.xp == 0 and again.coins == 0 and len(b.paid) == 1
    assert g.mark_bill_unpaid(b.id) and not g.mark_bill_unpaid(b.id)  # nothing left to undo
    later = g.mark_bill_paid(b.id, D + timedelta(days=1))
    assert later.xp == STEWARD_BILL_XP


def test_mark_unpaid_one_off_and_after_schedule_edit():
    g = Game()
    one = g.add_bill("Fee", 100, D)
    g.mark_bill_paid(one.id, D)
    assert g.bill_status(one, D) == "paid"
    g.mark_bill_unpaid(one.id)
    assert g.bill_status(one, D) == "due_soon" and one.due == D.isoformat()
    # a payment made before a schedule edit: undo brings that exact due date back
    b = g.add_bill("Gym", 300, date(2026, 11, 5), "monthly")
    g.pay_bill(b.id, D)
    g.edit_bill(b.id, due=date(2026, 12, 10))
    assert b.start_cycle == 1
    g.mark_bill_unpaid(b.id)
    assert g.next_due(b) == date(2026, 11, 5) and b.start_cycle == 0


# --- Monk ----------------------------------------------------------------------------------------
def test_monk_path_catalog():
    monk = next(p for p in catalog.PATHS if p.id == "monk")
    assert (monk.name, monk.icon) == ("Monk", "self_improvement") and monk.color.startswith("#")
    assert len(catalog.PATHS) == 7
    board = [c for c in catalog.QUEST_BOARD if c.path_id == "monk"]
    assert len(board) >= 5
    g = Game()
    base = g.side_quest_catalog("monk")
    assert len(base) >= 2
    for chain in base:
        ids = {c.id for c in catalog.SIDE_QUESTS if c.skill_name == chain.skill_name}
        assert ids == {chain.id, f"{chain.id}-r2", f"{chain.id}-r3"}
    assert g.suggest_quest("monk").path_id == "monk"
    assert "calm" in catalog.LEARNING_WHERE["monk"]


def test_self_care_templates_moved_to_monk():
    g = Game()
    for tid in catalog.SELF_CARE_TEMPLATE_IDS:
        assert g.template(tid).path_id == "monk", tid
    assert g.template("t-gym").path_id == "warrior"
    q = g.quest_from_template("t-skin-care", D)
    c = g.complete_quest(q.id, D)
    assert c.path_id == "monk" and g.profile.path_xp["monk"] == c.xp
    assert g.path_level("monk")[0] == 1


def test_monk_side_quest_unlocks_skill():
    g = Game()
    sq = g.start_side_quest("calm-breathing", D)
    for i in range(len(sq.steps)):
        c = g.complete_step(sq.id, i, D)
    assert c.skill_unlocked == "Calm Breathing" and c.path_id == "monk"
    assert g.followups_for("Calm Breathing")[0].id == "calm-breathing-r2"


# --- schema 4 ------------------------------------------------------------------------------------
SCHEMA3 = {
    "schema": 3,
    "profile": {"name": "Jarvin", "coins": 90, "path_xp": {"warrior": 60, "steward": 15},
                "theme_id": "arcane", "owned_themes": ["arcane", "ember"], "onboarded": True,
                "sfx_on": False},
    "quests": [
        {"id": "q1", "title": "Skin care routine", "path_id": "warrior", "kind": "daily",
         "xp": 20, "coins": 10, "difficulty": 1, "created": "2026-11-01",
         "done_on": ["2026-11-01", "2026-11-02"], "template_id": "t-skin-care"},
    ],
    "bills": [
        {"id": "b2", "name": "Rent", "amount": 100.0, "due": "2026-10-04", "repeat": "monthly",
         "paid": ["2026-10-03", "2026-10-03"], "paid_due": ["2026-10-04", "2026-11-04"],
         "paid_amounts": [100.0, 100.0], "start_cycle": 0, "archived": False},
    ],
    "rewards": [{"id": "r3", "title": "Snack", "cost": 30, "redeemed": ["2026-11-02"],
                 "redeemed_costs": [30], "archived": False}],
    "logs": [{"id": "l4", "day": "2026-11-02", "kind": "sleep", "text": "ok", "minutes": 420}],
    "side_quests": [],
    "skills": [],
    "templates": [{"id": "t-stretch", "title": "Stretch more", "path_id": "warrior",
                   "difficulty": 1, "kind": "daily", "builtin": True}],
    "hidden_templates": ["t-facial"],
    "focus_sessions": [{"id": "f5", "day": "2026-11-02", "minutes": 25, "xp": 10}],
    "next_id": 6,
}


def test_schema3_migrates_to_4_without_loss(tmp_path):
    raw = json.loads(json.dumps(SCHEMA3))
    data = storage.from_dict(raw)
    out = storage.to_dict(data)
    assert out["schema"] == storage.SCHEMA == 5
    for key in ("quests", "bills", "rewards", "logs", "templates", "focus_sessions"):
        for old, new in zip(SCHEMA3[key], out[key], strict=True):
            assert {k: new[k] for k in old} == old, key
    assert out["hidden_templates"] == ["t-facial"]
    p = data.profile
    assert p.path_xp == {"warrior": 60, "steward": 15, "monk": 0}
    assert p.sfx_on is False and p.name == "Jarvin" and p.coins == 90
    assert all(p.modules.values()) and set(p.modules) == {
        "workout", "sleep", "water", "energy", "insights", "body", "meals", "run"}
    assert p.water.daily_goal_ml is None and p.water.unit == "ml"
    assert p.reminders.enabled and not p.reminders.comeback_on
    # history kept: the old self-care quest stays on Warrior; the user's template edit too
    assert data.quests[0].path_id == "warrior"
    g = Game(data)
    assert g.template("t-stretch").path_id == "warrior"
    assert g.template("t-oral-care").path_id == "monk"
    # new tables empty; bill payment days count as already rewarded
    assert (data.workouts, data.sleep, data.water, data.energy) == ([], [], [], [])
    assert data.water_goal_days == {} and data.workout_templates == []
    assert data.bills[0].rewarded_on == ["2026-10-03"] and data.bills[0].note == ""
    assert data.rewards[0].note == ""
    # round trip as schema 4 is exact
    path = tmp_path / "save.json"
    storage.save(data, path)
    assert storage.load(path) == data


def test_v0_and_schema1_reach_schema4():
    v0 = {"name": "A", "level": 2, "xp": 5, "quests": [{"title": "Run", "xp": 30,
                                                          "stat": "health", "done": True}]}
    data = storage.from_dict(v0, D)
    assert data.profile.path_xp == {"monk": 0, "warrior": 30}
    assert storage.to_dict(data)["schema"] == 5
    s1 = {"schema": 1, "profile": {"name": "B", "path_xp": {"chef": 3}}, "next_id": 1}
    data = storage.from_dict(s1)
    assert data.profile.path_xp == {"chef": 3, "monk": 0} and data.profile.theme_id == "ember"


def _full_v13_game() -> Game:
    g = Game()
    g.set_water_settings(daily_goal_ml=1000, unit="oz", quick_amounts=[237, 355])
    g.set_reminders(water_on=True, quiet_start="23:00", water_active_days=[0, 2, 4])
    g.set_module("energy", False)
    g.log_workout(30, D, "strength", 7, "legs", exercises=[
        ExerciseEntry("Squat", [SetEntry(5, 60, "kg"), SetEntry(5, 135, "lb")]),
        ExerciseEntry("Run", [SetEntry(distance_km=2.5, seconds=900)]),
    ])
    g.add_workout_template("Push day", exercises=[ExerciseEntry("Push-up", [SetEntry(10)])])
    g.log_sleep(D - timedelta(days=1), "23:30", "07:00", D, naps_min=20, restedness=4,
                note="ok")
    g.add_water(600, D, "09:00")
    g.add_water(500, D)
    g.check_in("low", D, "08:00", "tired")
    b = g.add_bill("Rent", 100, D, "monthly", note="n")
    g.pay_bill(b.id, D)
    g.add_reward("Snack", 10, note="small")
    return g


def test_schema4_full_round_trip_and_backup(tmp_path):
    g = _full_v13_game()
    path = tmp_path / "save.json"
    g.save(path)
    loaded = Game.load(path)
    assert loaded.data == g.data
    assert isinstance(loaded.data.workouts[0].exercises[0].sets[0], SetEntry)
    assert loaded.profile.reminders.water_active_days == [0, 2, 4]
    assert loaded.profile.modules["energy"] is False
    restored = storage.import_json(storage.export_json(g.data))
    assert restored == g.data
    s = storage.summary(g.data)
    assert (s["workouts"], s["sleep_entries"], s["water_entries"], s["energy_checkins"],
            s["workout_templates"]) == (1, 1, 2, 1, 1)
    csvs = storage.export_csv(g.data)
    assert csvs["workout_sets.csv"].count("\n") == 1 + 3
    assert "Squat" in csvs["workout_sets.csv"] and ",lb," in csvs["workout_sets.csv"]
    assert "450" in csvs["sleep.csv"]  # 23:30 -> 07:00
    assert csvs["water.csv"].count("\n") == 3 and "low" in csvs["energy.csv"]
    assert "n" in csvs["bills.csv"].splitlines()[1].split(",")[-1]


def test_new_ids_never_collide_after_load():
    g = _full_v13_game()
    raw = storage.to_dict(g.data)
    raw["next_id"] = 1  # a damaged counter
    data = storage.from_dict(raw)
    assert data.next_id > max(int("".join(filter(str.isdigit, w.id))) for w in data.water)


@pytest.mark.parametrize("bad", [
    {"schema": 4, "workouts": {"a": 1}},
    {"schema": 4, "sleep": [{"id": "sl1", "night_of": "nope", "bedtime": "23:00",
                             "wake": "07:00"}]},
    {"schema": 4, "water": [{"id": "w1", "day": "2026-11-04"}, {"id": "w1", "day": "2026-11-04"}]},
    {"schema": 4, "water_goal_days": ["2026-11-04"]},
    {"schema": 4, "energy": [{"id": "e1", "day": "x"}]},
])
def test_import_rejects_bad_phase2_data(bad):
    with pytest.raises(ValueError):
        storage.import_json(json.dumps(bad))


def test_newer_schema_refused():
    with pytest.raises(ValueError):
        storage.from_dict({"schema": 6})
