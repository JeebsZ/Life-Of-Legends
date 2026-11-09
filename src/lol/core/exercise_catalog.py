"""Offline exercise catalog for the Labyrinth Workout system.

Categories: Chest, Back, Legs, Shoulders, Arms, Core.
Equipment: Barbell, Dumbbell, Cable, Machine, Bodyweight.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Exercise:
    id: str
    name: str
    muscle: str  # "Chest" | "Back" | "Legs" | "Shoulders" | "Arms" | "Core"
    equipment: str  # "Barbell" | "Dumbbell" | "Cable" | "Machine" | "Bodyweight"
    instructions: tuple[str, ...]
    secondary_muscles: tuple[str, ...] = ()
    guardian_affinity: str = "Physical"  # "Earth", "Flame", "Tide", "Wind", "Physical"


EXERCISES: tuple[Exercise, ...] = (
    # --- Chest ---
    Exercise(
        id="bench_press_barbell",
        name="Bench Press (Barbell)",
        muscle="Chest",
        equipment="Barbell",
        instructions=(
            "Lie flat on the bench with your eyes under the bar.",
            "Grip the bar slightly wider than shoulder-width.",
            "Lower the bar under control until it gently touches mid-chest.",
            "Drive your feet into the floor and press the bar back up to lockout.",
        ),
        secondary_muscles=("Triceps", "Shoulders"),
        guardian_affinity="Flame",
    ),
    Exercise(
        id="incline_press_dumbbell",
        name="Incline Dumbbell Press",
        muscle="Chest",
        equipment="Dumbbell",
        instructions=(
            "Set the bench at a 30 to 45 degree angle.",
            "Hold dumbbells at shoulder level with wrists stacked over elbows.",
            "Press upward until arms are extended, squeezing upper chest.",
            "Lower slowly with a full stretch at the bottom.",
        ),
        secondary_muscles=("Shoulders", "Triceps"),
        guardian_affinity="Flame",
    ),
    Exercise(
        id="cable_chest_fly",
        name="Cable Chest Fly",
        muscle="Chest",
        equipment="Cable",
        instructions=(
            "Set pulleys at chest height. Take one step forward with a split stance.",
            "Maintain a slight bend in your elbows throughout.",
            "Bring your hands together in front of your chest in a hugging motion.",
            "Control the stretch on the way back.",
        ),
        secondary_muscles=("Shoulders",),
        guardian_affinity="Wind",
    ),
    Exercise(
        id="pushup_bodyweight",
        name="Push-Up",
        muscle="Chest",
        equipment="Bodyweight",
        instructions=(
            "Start in a high plank with hands slightly wider than shoulders.",
            "Brace core and lower chest until an inch above the floor.",
            "Push through your palms to return to starting position.",
        ),
        secondary_muscles=("Core", "Triceps"),
        guardian_affinity="Physical",
    ),
    # --- Back ---
    Exercise(
        id="lat_pulldown_cable",
        name="Lat Pulldown (Cable)",
        muscle="Back",
        equipment="Cable",
        instructions=(
            "Grip the wide bar with palms facing forward.",
            "Sit with thighs secured under pads and lean back slightly.",
            "Pull the bar down toward upper chest, driving elbows downward.",
            "Slowly let the bar return with a full lat stretch at the top.",
        ),
        secondary_muscles=("Biceps", "Forearms"),
        guardian_affinity="Tide",
    ),
    Exercise(
        id="barbell_bent_row",
        name="Bent-Over Row (Barbell)",
        muscle="Back",
        equipment="Barbell",
        instructions=(
            "Hinge at your hips with a flat back, torso around 45 degrees.",
            "Grip bar overhand, pull bar towards lower ribcage.",
            "Retract shoulder blades at the peak of the contraction.",
            "Lower the weight smoothly without rounding lower back.",
        ),
        secondary_muscles=("Biceps", "Core"),
        guardian_affinity="Earth",
    ),
    Exercise(
        id="seated_cable_row",
        name="Seated Cable Row (V-Grip)",
        muscle="Back",
        equipment="Cable",
        instructions=(
            "Sit with knees slightly bent and back straight.",
            "Pull the handle into your naval while pulling shoulders back.",
            "Squeeze middle back for a one-second pause.",
            "Extend arms forward under control without leaning too far.",
        ),
        secondary_muscles=("Biceps", "Shoulders"),
        guardian_affinity="Tide",
    ),
    Exercise(
        id="pullup_bodyweight",
        name="Pull-Up",
        muscle="Back",
        equipment="Bodyweight",
        instructions=(
            "Hang from bar with an overhand grip slightly wider than shoulders.",
            "Pull body up until chin clears the bar, leading with your chest.",
            "Lower with control until arms are fully extended.",
        ),
        secondary_muscles=("Biceps", "Core"),
        guardian_affinity="Wind",
    ),
    # --- Legs ---
    Exercise(
        id="squat_barbell",
        name="Squat (Barbell)",
        muscle="Legs",
        equipment="Barbell",
        instructions=(
            "Rest bar across upper traps. Feet shoulder-width apart, toes flared slightly.",
            "Break at hips and knees, sitting down until thighs are parallel to ground.",
            "Keep chest tall and knees tracking over toes.",
            "Drive through mid-foot to stand back up.",
        ),
        secondary_muscles=("Glutes", "Hamstrings", "Core"),
        guardian_affinity="Earth",
    ),
    Exercise(
        id="leg_press_machine",
        name="Leg Press (Machine)",
        muscle="Legs",
        equipment="Machine",
        instructions=(
            "Place feet shoulder-width on platform center.",
            "Release safety catches and lower sled until knees form 90 degrees.",
            "Do not let your lower back peel off the padded seat.",
            "Press the sled back up without locking knees aggressively.",
        ),
        secondary_muscles=("Glutes", "Calves"),
        guardian_affinity="Earth",
    ),
    Exercise(
        id="romanian_deadlift_barbell",
        name="Romanian Deadlift (Barbell)",
        muscle="Legs",
        equipment="Barbell",
        instructions=(
            "Stand holding bar at hip level with a slight bend in knees.",
            "Push hips backwards, lowering the bar along your shins.",
            "Stop when you feel a deep hamstring stretch with a neutral spine.",
            "Drive hips forward to return to standing lockout.",
        ),
        secondary_muscles=("Hamstrings", "Glutes", "Back"),
        guardian_affinity="Earth",
    ),
    Exercise(
        id="seated_leg_curl_machine",
        name="Seated Leg Curl (Machine)",
        muscle="Legs",
        equipment="Machine",
        instructions=(
            "Align knee joints with machine pivot point.",
            "Curl heels downward and under the seat as far as possible.",
            "Hold contraction briefly, then return slowly.",
        ),
        secondary_muscles=("Hamstrings", "Calves"),
        guardian_affinity="Tide",
    ),
    # --- Shoulders ---
    Exercise(
        id="overhead_press_barbell",
        name="Overhead Press (Barbell)",
        muscle="Shoulders",
        equipment="Barbell",
        instructions=(
            "Stand with feet hip-width. Rest bar on front delts.",
            "Brace core and glutes. Press bar straight up over head.",
            "Move head slightly forward once bar clears forehead.",
            "Lock out overhead, then lower bar back to collarbone.",
        ),
        secondary_muscles=("Triceps", "Upper Chest"),
        guardian_affinity="Flame",
    ),
    Exercise(
        id="lateral_raise_dumbbell",
        name="Dumbbell Lateral Raise",
        muscle="Shoulders",
        equipment="Dumbbell",
        instructions=(
            "Stand with dumbbells at your sides, palms facing inward.",
            "Raise arms out to sides with a slight elbow bend until parallel to floor.",
            "Pour out slightly as if holding water pitchers.",
            "Lower slowly under control without swinging body.",
        ),
        secondary_muscles=("Traps",),
        guardian_affinity="Wind",
    ),
    # --- Arms ---
    Exercise(
        id="bicep_curl_dumbbell",
        name="Dumbbell Bicep Curl",
        muscle="Arms",
        equipment="Dumbbell",
        instructions=(
            "Hold dumbbells by your sides with arms extended.",
            "Curl weights upward while rotating palms to face up.",
            "Squeeze biceps hard at top.",
            "Lower slowly all the way down for a full stretch.",
        ),
        secondary_muscles=("Forearms",),
        guardian_affinity="Physical",
    ),
    Exercise(
        id="tricep_rope_pushdown",
        name="Tricep Rope Pushdown",
        muscle="Arms",
        equipment="Cable",
        instructions=(
            "Grip rope attachment with elbows pinned to sides.",
            "Push rope downwards until arms lock out.",
            "Flare the ends of the rope apart at the bottom for peak contraction.",
            "Return slowly to 90 degrees elbow bend.",
        ),
        secondary_muscles=("Forearms",),
        guardian_affinity="Wind",
    ),
    # --- Core ---
    Exercise(
        id="hanging_leg_raise",
        name="Hanging Leg Raise",
        muscle="Core",
        equipment="Bodyweight",
        instructions=(
            "Hang from pull-up bar with arms straight.",
            "Raise legs smoothly until parallel to ground (or knees to chest).",
            "Avoid swinging or using momentum.",
            "Lower slowly and maintain control.",
        ),
        secondary_muscles=("Hip Flexors",),
        guardian_affinity="Wind",
    ),
    Exercise(
        id="plank_bodyweight",
        name="Core Plank",
        muscle="Core",
        equipment="Bodyweight",
        instructions=(
            "Rest on forearms and toes. Keep body in a straight line.",
            "Brace abs as if about to be punched.",
            "Hold position while breathing rhythmically.",
        ),
        secondary_muscles=("Glutes", "Shoulders"),
        guardian_affinity="Earth",
    ),
)

EXERCISE_BY_ID: dict[str, Exercise] = {e.id: e for e in EXERCISES}


def get_exercise(exercise_id: str) -> Exercise | None:
    return EXERCISE_BY_ID.get(exercise_id)


def filter_exercises(
    *,
    muscle: str | None = None,
    equipment: str | None = None,
    query: str | None = None,
) -> list[Exercise]:
    """Filter catalog by muscle group, equipment type, or search text."""
    results = list(EXERCISES)
    if muscle and muscle != "All":
        results = [e for e in results if e.muscle.lower() == muscle.lower()]
    if equipment and equipment != "All":
        results = [e for e in results if e.equipment.lower() == equipment.lower()]
    if query:
        q = query.strip().lower()
        results = [
            e
            for e in results
            if q in e.name.lower() or any(q in s.lower() for s in e.secondary_muscles)
        ]
    return results

