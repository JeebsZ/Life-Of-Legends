"""Phase 2 (v1.3): workouts, sleep, water, energy check-in, insights, modules."""

from datetime import date, timedelta

import pytest

from lol.core.game import (
    SLEEP_LOG_XP,
    WATER_GOAL_XP,
    WORKOUT_DAILY_COIN_CAP,
    WORKOUT_DAILY_XP_CAP,
    WORKOUT_MIN_XP,
    Game,
    convert_weight,
    kg_to_lb,
    lb_to_kg,
    ml_to_oz,
    oz_to_ml,
    sleep_minutes,
    water_in,
)
from lol.core.models import ExerciseEntry, SetEntry

D = date(2026, 11, 4)


def day(n: int) -> date:
    return D + timedelta(days=n)


# --- workouts ------------------------------------------------------------------------------------
def test_workout_xp_formula():
    assert Game.workout_xp(30) == 12
    assert Game.workout_xp(30, effort=10) == 15 and Game.workout_xp(30, effort=1) == 10
    assert Game.workout_xp(4) == 0 and Game.workout_xp(0) == WORKOUT_MIN_XP


def test_log_workout_quick_and_detailed():
    g = Game()
    c = g.log_workout(30, D)
    w = g.workout(c.ref_id)
    assert (c.xp, c.coins, c.path_id) == (12, 2, "warrior")
    assert (w.type, w.minutes, w.effort, w.xp, w.coins) == ("strength", 30, 5, 12, 2)
    assert g.profile.path_xp["warrior"] == 12
    sets = [SetEntry(8, 50, "kg"), SetEntry(6, 120, "lb")]
    ex = [ExerciseEntry(" Bench press ", sets)]
    c2 = g.log_workout(45, D, "strength", 8, "chest", exercises=ex, started="18:00")
    w2 = g.workout(c2.ref_id)
    assert w2.exercises[0].name == "Bench press" and w2.started == "18:00"
    assert w2.exercises[0].sets[1].unit == "lb" and w2.exercises[0].sets[1].weight == 120
    sets[0].reps = 99  # caller's objects are copied, not shared
    assert w2.exercises[0].sets[0].reps == 8


def test_workout_path_from_quest_or_choice_and_quest_not_completed():
    g = Game()
    q = g.add_quest("Yoga", "monk", today=D)
    c = g.log_workout(20, D, "mobility", quest_id=q.id)
    assert c.path_id == "monk" and not q.done_on
    assert g.log_workout(20, D, path_id="ranger").path_id == "ranger"
    with pytest.raises(ValueError):
        g.log_workout(20, D, path_id="nope")
    with pytest.raises(ValueError):
        g.log_workout(20, D, type="dance-off")
    with pytest.raises(ValueError):
        g.log_workout(20, D, effort=11)
    with pytest.raises(KeyError):
        g.log_workout(20, D, quest_id="q999")
    with pytest.raises(ValueError):
        g.log_workout(20, D, exercises=[ExerciseEntry("Squat", [SetEntry(5, -1)])])
    with pytest.raises(ValueError):
        g.log_workout(20, D, exercises=[ExerciseEntry("Squat", [SetEntry(5, 10, "stone")])])


def test_workout_daily_caps():
    g = Game()
    total_xp = total_coins = 0
    for _ in range(5):
        c = g.log_workout(300, D, effort=10)
        total_xp += c.xp
        total_coins += c.coins
    assert total_xp == WORKOUT_DAILY_XP_CAP and total_coins == WORKOUT_DAILY_COIN_CAP
    assert g.workout_stats(D)["xp_left"] == 0
    assert g.log_workout(30, day(1)).xp == 12  # a new day
    assert g.log_workout(9999, day(2)).ref_id and g.workouts(day(2), day(2))[0].minutes == 300


def test_edit_delete_workout_keeps_rewards():
    g = Game()
    c = g.log_workout(30, D)
    xp = g.profile.xp
    w = g.edit_workout(c.ref_id, minutes=90, effort=9, notes="longer", type="cardio",
                       day=day(-1), exercises=[ExerciseEntry("Row", [SetEntry(seconds=600)])])
    assert (w.minutes, w.effort, w.notes, w.type, w.day, w.xp) == (
        90, 9, "longer", "cardio", day(-1).isoformat(), 12)
    assert w.exercises[0].name == "Row" and g.profile.xp == xp
    with pytest.raises(ValueError):
        g.edit_workout(c.ref_id, effort=0)
    g.delete_workout(c.ref_id)
    assert g.workouts() == [] and g.profile.xp == xp


def test_copy_workout_is_a_draft():
    g = Game()
    c = g.log_workout(40, D, "strength", 6, "legs", path_id="warrior",
                      exercises=[ExerciseEntry("Squat", [SetEntry(5, 60)])])
    draft = g.copy_workout(c.ref_id, day(2))
    assert draft.id == "" and draft.day == day(2).isoformat() and draft.xp == 0
    assert len(g.workouts()) == 1  # nothing saved yet
    draft.exercises[0].sets[0].weight = 65
    assert g.workout(c.ref_id).exercises[0].sets[0].weight == 60  # deep copy
    c2 = g.log_workout_draft(draft, day(2))
    w2 = g.workout(c2.ref_id)
    assert (w2.minutes, w2.effort, w2.notes, w2.exercises[0].sets[0].weight) == (40, 6, "legs", 65)


def test_workout_templates_routines():
    g = Game()
    t = g.add_workout_template("Leg day", "strength", 45,
                               [ExerciseEntry("Squat", [SetEntry(5, 60)]),
                                ExerciseEntry("Lunge")], "warm up")
    assert g.workout_templates() == [t] and t.id.startswith("wt")
    g.edit_workout_template(t.id, name="Legs", minutes=50,
                            exercises=[ExerciseEntry("Squat", [SetEntry(5, 70)])])
    assert (t.name, t.minutes, len(t.exercises)) == ("Legs", 50, 1)
    draft = g.workout_from_template(t.id, D)
    assert draft.id == "" and draft.exercises[0].sets[0].weight == 70
    c = g.log_workout_draft(draft, D)
    t2 = g.template_from_workout(c.ref_id, "Copy")
    assert t2.name == "Copy" and t2.exercises[0].name == "Squat"
    with pytest.raises(ValueError):
        g.add_workout_template(" ")
    g.delete_workout_template(t.id)
    assert g.workout_templates() == [t2]


def test_exercise_history_and_personal_records():
    g = Game()
    g.log_workout(30, day(0), exercises=[ExerciseEntry("Squat", [SetEntry(5, 60), SetEntry(8, 50)])])
    g.log_workout(30, day(1), exercises=[ExerciseEntry("squat", [SetEntry(3, 154, "lb")])])
    g.log_workout(30, day(2), exercises=[ExerciseEntry("Run", [SetEntry(distance_km=5,
                                                                      seconds=1800)])])
    g.log_workout(30, day(3), exercises=[ExerciseEntry("SQUAT", [SetEntry(5, 60)])])
    hist = g.exercise_history(" Squat")
    assert [w.day for w, _ in hist] == [day(3).isoformat(), day(1).isoformat(), D.isoformat()]
    pr = g.personal_records("Squat")
    assert pr["max_weight"].value == pytest.approx(69.85, abs=0.01)  # 154 lb in kg
    assert pr["max_weight"].day == day(1).isoformat() and pr["max_weight"].unit == "kg"
    assert pr["max_reps"].value == 8 and pr["max_reps"].day == D.isoformat()
    assert pr["best_volume"].value == 700  # 5*60 + 8*50; day 3 ties at 300 only
    assert "longest_distance" not in pr
    assert g.personal_records("Squat", "lb")["max_weight"].value == pytest.approx(154, abs=0.01)
    stored = g.workouts(day(1), day(1))[0].exercises[0].sets[0]
    assert (stored.weight, stored.unit) == (154, "lb")  # never silently converted
    run = g.personal_records("run")
    assert run["longest_distance"].value == 5 and run["longest_time"].value == 1800
    assert g.personal_records("Deadlift") == {}
    assert g.exercise_names() == ["Run", "Squat"]
    with pytest.raises(ValueError):
        g.personal_records("Squat", "stone")


def test_unit_helpers():
    assert kg_to_lb(100) == pytest.approx(220.462)
    assert lb_to_kg(kg_to_lb(42)) == pytest.approx(42)
    assert convert_weight(10, "kg", "kg") == 10
    assert ml_to_oz(oz_to_ml(8)) == pytest.approx(8)
    assert water_in(500, "ml") == 500 and water_in(500, "oz") == 16.9
    with pytest.raises(ValueError):
        convert_weight(1, "kg", "st")
    with pytest.raises(ValueError):
        water_in(1, "cups")


# --- sleep ---------------------------------------------------------------------------------------
def test_sleep_duration_crossing_midnight():
    assert sleep_minutes("23:30", "07:00") == 450
    assert sleep_minutes("01:15", "08:45") == 450
    assert sleep_minutes("22:00", "22:30") == 30
    assert sleep_minutes("13:00", "12:00") == 23 * 60


def test_log_sleep_xp_cap_and_validation():
    g = Game()
    c = g.log_sleep(day(-1), "23:30", "7:00", D, naps_min=20, restedness=4, note="ok")
    e = g.sleep_entry(c.ref_id)
    assert (c.xp, c.path_id, e.wake, e.logged_on) == (SLEEP_LOG_XP, "monk", "07:00", D.isoformat())
    assert g.profile.path_xp["monk"] == SLEEP_LOG_XP
    c2 = g.log_sleep(day(-2), "00:30", "06:00", D)  # back-filling the same day: capped
    assert c2.xp == 0 and g.sleep_entry(c2.ref_id).restedness is None
    assert g.log_sleep(D, "23:00", "06:30", day(1)).xp == SLEEP_LOG_XP
    with pytest.raises(ValueError):
        g.log_sleep(day(-1), "22:00", "06:00", day(1))  # night already logged
    with pytest.raises(ValueError):
        g.log_sleep(day(5), "22:00", "22:00", day(5))
    with pytest.raises(ValueError):
        g.log_sleep(day(5), "25:00", "06:00", day(5))
    with pytest.raises(ValueError):
        g.log_sleep(day(5), "22:00", "06:00", day(5), restedness=6)
    with pytest.raises(ValueError):
        g.log_sleep(day(5), "22:00", "06:00", day(5), naps_min=-5)


def test_edit_delete_sleep():
    g = Game()
    c = g.log_sleep(day(-1), "23:30", "07:00", D, restedness=3)
    xp = g.profile.xp
    e = g.edit_sleep(c.ref_id, wake="08:00", restedness=None, note="slept in", night_of=day(-3))
    assert (e.wake, e.restedness, e.note, e.night_of) == ("08:00", None, "slept in",
                                                          day(-3).isoformat())
    assert g.sleep_duration(e) == 510 and g.profile.xp == xp
    g.log_sleep(day(-1), "23:00", "07:00", D)
    with pytest.raises(ValueError):
        g.edit_sleep(c.ref_id, night_of=day(-1))
    g.delete_sleep(c.ref_id)
    assert len(g.sleep_entries()) == 1 and g.profile.xp == xp


def test_sleep_stats():
    g = Game()
    empty = g.sleep_stats(D, day(6))
    assert empty == {"nights": 0, "avg_minutes": None, "avg_nap_minutes": None,
                     "avg_restedness": None, "per_night": []}
    g.log_sleep(day(2), "23:00", "07:00", day(3), restedness=4)  # 480
    g.log_sleep(day(0), "00:00", "07:00", day(1), naps_min=30, restedness=2)  # 420
    g.log_sleep(day(9), "22:00", "06:00", day(10))  # outside the range
    s = g.sleep_stats(D, day(6))
    assert (s["nights"], s["avg_minutes"], s["avg_nap_minutes"], s["avg_restedness"]) == (
        2, 450, 15, 3.0)
    assert s["per_night"] == [(D.isoformat(), 420, 30, 2), (day(2).isoformat(), 480, 0, 4)]


# --- water ---------------------------------------------------------------------------------------
def test_water_without_goal_gives_no_xp():
    g = Game()
    assert g.profile.water.daily_goal_ml is None
    c = g.add_water(3000, D)
    assert c.xp == 0 and g.water_day(D) == 3000
    t = g.water_today(D)
    assert t == {"ml": 3000, "goal_ml": None, "progress": None, "reached": False}


def test_water_goal_xp_once_per_day():
    g = Game()
    g.set_water_settings(daily_goal_ml=1000)
    assert g.add_water(600, D, "9:05").xp == 0
    assert g.water_entries(D)[0].time == "09:05"
    c = g.add_water(500, D)
    assert (c.xp, c.coins, c.path_id) == (WATER_GOAL_XP, 0, "monk")
    assert g.water_today(D)["reached"] and g.water_today(D)["progress"] == 1.0
    assert g.add_water(500, D).xp == 0  # once per day
    g.undo_water(D)
    g.undo_water(D)
    assert g.water_day(D) == 600 and g.profile.path_xp["monk"] == WATER_GOAL_XP  # XP stays
    assert g.add_water(500, D).xp == 0  # re-reaching the goal never pays twice
    assert g.add_water(1000, day(1)).xp == WATER_GOAL_XP


def test_water_undo_delete_history_and_settings():
    g = Game()
    assert g.undo_water(D) is None
    a = g.add_water(250, D)
    g.add_water(oz_to_ml(8), D)
    assert g.water_entries(D)[-1].amount_ml == 237
    removed = g.undo_water(D)
    assert removed.amount_ml == 237 and g.water_day(D) == 250
    g.delete_water(a.ref_id)
    assert g.water_day(D) == 0
    g.add_water(800, day(1))
    g.set_water_settings(daily_goal_ml=700)
    hist = g.water_history(D, day(2))
    assert hist == [(D.isoformat(), 0, False), (day(1).isoformat(), 800, True),
                    (day(2).isoformat(), 0, False)]
    g.set_water_settings(unit="oz", quick_amounts=[236.6, 500])
    assert g.profile.water.unit == "oz" and g.profile.water.quick_amounts == [237, 500]
    g.set_water_settings(daily_goal_ml=None)
    assert g.profile.water.daily_goal_ml is None and g.profile.water.unit == "oz"
    for bad in ({"daily_goal_ml": 0}, {"unit": "cup"}, {"quick_amounts": []},
                {"quick_amounts": [0]}):
        with pytest.raises(ValueError):
            g.set_water_settings(**bad)
    for amount in (0, -5, 99999):
        with pytest.raises(ValueError):
            g.add_water(amount, D)


# --- energy --------------------------------------------------------------------------------------
def test_energy_checkins():
    g = Game()
    assert g.energy_today(D) is None
    a = g.check_in("okay", D, "08:00")
    b = g.check_in("low", D, "13:30", note="after lunch")
    g.check_in("high", day(-1), "20:00")
    assert g.energy_today(D) is b and b.note == "after lunch"
    g.check_in("high", D, "07:00")  # an earlier time added later is not the latest
    assert g.energy_today(D) is b
    assert [c.level for c in g.energy_checkins(D, D)] == ["low", "okay", "high"]
    g.delete_checkin(b.id)
    assert g.energy_today(D) is a
    assert g.profile.xp == 0  # check-ins are never rewarded
    with pytest.raises(ValueError):
        g.check_in("meh", D)


def test_suggest_order_never_hides():
    g = Game()
    hard = g.add_quest("Hard", "warrior", difficulty=3, today=D, minutes=60)
    easy_long = g.add_quest("Easy long", "chef", difficulty=1, today=D, minutes=30)
    mid = g.add_quest("Mid", "scholar", difficulty=2, today=D)
    easy_short = g.add_quest("Easy short", "monk", difficulty=1, today=D, minutes=5)
    qs = g.quests
    low = g.suggest_order(qs, "low")
    assert low == [easy_short, easy_long, mid, hard]
    assert g.suggest_order(qs, "high")[0] is hard
    assert g.suggest_order(qs, "okay") == qs and g.suggest_order(qs, None) == qs
    assert g.suggest_order(qs, g.check_in("low", D)) == low
    for level in ("low", "okay", "high"):
        assert sorted(q.id for q in g.suggest_order(qs, level)) == sorted(q.id for q in qs)


# --- modules + insights --------------------------------------------------------------------------
def test_modules_toggle():
    g = Game()
    assert all(g.module_on(m) for m in ("workout", "sleep", "water", "energy", "insights"))
    g.set_module("energy", False)
    assert not g.module_on("energy")
    with pytest.raises(ValueError):
        g.set_module("tarot", True)
    with pytest.raises(ValueError):
        g.module_on("tarot")


def test_insights_empty_safe():
    g = Game()
    ins = g.insights(D, day(13))
    assert [i.kind for i in ins] == ["quests_by_path", "workouts_per_week", "sleep", "water"]
    assert all(i.text for i in ins)
    assert ins[0].data[-1] == ("Monk", 0.0) and len(ins[0].data) == 7
    assert ins[1].data == [("Nov 4", 0.0), ("Nov 11", 0.0)]
    assert ins[2].data == [] and len(ins[3].data) == 14
    with pytest.raises(ValueError):
        g.insights(day(1), D)


def test_insights_with_data_plain_wording():
    g = Game()
    q = g.add_quest("Stretch", "monk", kind="daily", today=D)
    for i in range(3):
        g.complete_quest(q.id, day(i))
    g.complete_quest(g.add_quest("Cook", "chef", today=D).id, D)
    sq = g.start_side_quest("calm-breathing", D)
    g.complete_step(sq.id, 0, day(1))
    g.log_workout(30, D)
    g.log_workout(20, day(8))
    g.log_sleep(D, "23:00", "07:00", day(1), restedness=4)
    g.log_sleep(day(1), "23:00", "06:00", day(2))
    g.set_water_settings(daily_goal_ml=1000)
    g.add_water(1200, D)
    g.add_water(300, day(1))
    ins = {i.kind: i for i in g.insights(D, day(13))}
    qb = ins["quests_by_path"]
    assert dict(qb.data)["Monk"] == 4 and dict(qb.data)["Chef"] == 1
    assert "5 quests and steps" in qb.text and "Monk Path" in qb.text
    assert ins["workouts_per_week"].data == [("Nov 4", 1.0), ("Nov 11", 1.0)]
    assert "2 workouts" in ins["workouts_per_week"].text and "1.0 per week" in ins[
        "workouts_per_week"].text
    assert ins["sleep"].data == [(D.isoformat(), 8.0), (day(1).isoformat(), 7.0)]
    assert "7 h 30 min" in ins["sleep"].text and "4.0 of 5" in ins["sleep"].text
    assert "1 of 14 days" in ins["water"].text
    for i in ins.values():  # descriptive only
        low = i.text.lower()
        assert not any(w in low for w in ("because", "caused", "should", "improve"))
    g.set_module("sleep", False)
    g.set_module("water", False)
    assert [i.kind for i in g.insights(D, day(13))] == ["quests_by_path", "workouts_per_week"]


def test_weekly_review_counts_phase2_xp():
    g = Game()
    g.log_workout(30, D)
    g.log_sleep(day(-1), "23:00", "07:00", D)
    g.set_water_settings(daily_goal_ml=500)
    g.add_water(500, D)
    r = g.weekly_review(D)
    assert r["workouts"] == 1 and r["workout_minutes"] == 30
    assert r["xp_by_path"]["warrior"] == 12
    assert r["xp_by_path"]["monk"] == SLEEP_LOG_XP + WATER_GOAL_XP
    assert r["xp_total"] == 12 + SLEEP_LOG_XP + WATER_GOAL_XP == g.profile.xp
