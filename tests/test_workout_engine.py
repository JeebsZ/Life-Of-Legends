"""Tests for the Labyrinth Workout RPG engine: Exercise catalog, Guardian combat math,
Set tonnage damage, PR awakenings, Devour traits, and Star-Iron ore conversion."""

from lol.core import exercise_catalog as ec
from lol.core.workout_engine import WorkoutSession, spawn_guardian_for_target_volume


def test_exercise_catalog_retrieval_and_filtering():
    bench = ec.get_exercise("bench_press_barbell")
    assert bench is not None
    assert bench.muscle == "Chest"
    assert bench.equipment == "Barbell"
    assert len(bench.instructions) >= 3

    chest_exercises = ec.filter_exercises(muscle="Chest")
    assert len(chest_exercises) >= 3
    assert all(e.muscle == "Chest" for e in chest_exercises)

    cable_exercises = ec.filter_exercises(equipment="Cable")
    assert len(cable_exercises) >= 2
    assert all(e.equipment == "Cable" for e in cable_exercises)

    squat_query = ec.filter_exercises(query="squat")
    assert any("Squat" in e.name for e in squat_query)


def test_guardian_hp_scaling_and_combat():
    guardian = spawn_guardian_for_target_volume(4500.0)
    assert guardian.max_hp == 4500
    assert guardian.current_hp == 4500
    assert not guardian.is_defeated
    assert guardian.hp_percent == 1.0


def test_workout_session_damage_pr_and_star_iron():
    session = WorkoutSession.start(
        routine_name="Push Day Raid",
        exercise_ids=["bench_press_barbell", "incline_press_dumbbell"],
        target_volume=2000.0,
    )
    prs: dict[str, float] = {"bench_press_barbell": 60.0}

    # Set 1: 60kg x 10 = 600 kg volume/damage -> matches PR, not broken
    dmg, is_pr, _trait = session.log_set_complete(
        exercise_idx=0,
        set_idx=0,
        weight_kg=60.0,
        reps=10,
        existing_prs=prs,
    )
    assert dmg == 600
    assert not is_pr
    assert session.guardian.current_hp == 1400

    # Set 2: 70kg x 8 = 560 kg volume/damage -> Breaks PR!
    dmg2, is_pr2, trait2 = session.log_set_complete(
        exercise_idx=0,
        set_idx=1,
        weight_kg=70.0,
        reps=8,
        existing_prs=prs,
    )
    assert dmg2 == 560
    assert is_pr2 is True
    assert trait2 == "Unique Trait: [Limit Breaker]"
    assert prs["bench_press_barbell"] == 70.0

    # Complete an exercise in second room
    session.log_set_complete(1, 0, 24.0, 10)

    summary = session.finish()
    assert summary["volume_kg"] == 600 + 560 + 240
    assert summary["star_iron"] == 1400
    assert "Trait: [Iron Bulwark]" in summary["skills_awakened"]
    assert "Unique Trait: [Limit Breaker]" in summary["skills_awakened"]
    assert summary["coins"] > 0
    assert summary["xp"] > 0
