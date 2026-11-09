"""Labyrinth Workout Engine: Guardian boss HP, Set impact damage, Devour skills, PRs, and Star-Iron ore."""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from lol.core import exercise_catalog as ec


@dataclass
class WorkoutSet:
    set_num: int
    weight_kg: float
    reps: int
    rpe: float | None = None
    completed: bool = False

    @property
    def volume_kg(self) -> float:
        return round(self.weight_kg * self.reps, 1) if self.completed else 0.0


@dataclass
class ExerciseLog:
    exercise_id: str
    sets: list[WorkoutSet] = field(default_factory=list)
    notes: str = ""

    @property
    def total_volume_kg(self) -> float:
        return sum(s.volume_kg for s in self.sets if s.completed)

    @property
    def max_weight_kg(self) -> float:
        completed = [s.weight_kg for s in self.sets if s.completed]
        return max(completed) if completed else 0.0

    @property
    def exercise_name(self) -> str:
        ex = ec.get_exercise(self.exercise_id)
        return ex.name if ex else self.exercise_id


@dataclass
class LabyrinthGuardian:
    id: str
    name: str
    title: str
    affinity: str
    max_hp: int
    current_hp: int
    sprite: str = "creatures/KingSlime.png"

    @property
    def is_defeated(self) -> bool:
        return self.current_hp <= 0

    @property
    def hp_percent(self) -> float:
        return max(0.0, min(1.0, self.current_hp / self.max_hp)) if self.max_hp > 0 else 0.0


GUARDIAN_TEMPLATES = [
    ("g_golem", "Obsidian Colossus", "Chamber of Earth", "Earth", "creatures/HugeBoar.png"),
    ("g_chimera", "Infernal Overlord", "Hall of Cinders", "Flame", "creatures/Goblin General.png"),
    ("g_leviathan", "Sovereign Slime", "Sunken Depths", "Tide", "creatures/KingSlime.png"),
    ("g_tempest", "Nightwing Monarch", "Spire of Zephyrs", "Wind", "creatures/BatKing.png"),
    ("g_titan", "Adamantine Behemoth", "Vault of Primordials", "Physical", "creatures/BigSlime.png"),
]

# Tactical readouts from Great Sage / Luma during magicule rest recovery
REST_SAGE_LINES: tuple[str, ...] = (
    "[GREAT SAGE] Magicule density stabilizing. Muscular micro-tears analyzed — next strike will hit harder.",
    "[GREAT SAGE] Notice: Heart rate and ATP reserves recovering. Prepare Primordial Strike for the next set.",
    "[GREAT SAGE] Guardian armor fracture detected! Maintain form to maximize impact damage.",
    "[GREAT SAGE] Assimilating kinetic force into Star-Iron Ore. Optimal power output approaching.",
    "[GREAT SAGE] Breathing rhythm synchronized. Magicule barrier recharged to 100%.",
)


@dataclass(frozen=True)
class ForgeRecipe:
    id: str
    name: str
    desc: str
    cost_ore: int
    reward_coins: int
    reward_xp: int
    trait_id: str
    icon_name: str
    color: str


FORGE_RECIPES: tuple[ForgeRecipe, ...] = (
    ForgeRecipe(
        "forge_gauntlets",
        "Magisteel Gauntlets",
        "+100 Coins · [Adamantine Grip]",
        1500,
        100,
        150,
        "Relic: [Adamantine Grip]",
        "sports_mma",
        "#4FE3F0",
    ),
    ForgeRecipe(
        "forge_greaves",
        "Tempest Strider Greaves",
        "+220 Coins · [Titan's Momentum]",
        3000,
        220,
        300,
        "Relic: [Titan's Momentum]",
        "directions_run",
        "#5EEAB0",
    ),
    ForgeRecipe(
        "forge_aegis",
        "Obsidian Core Aegis",
        "+400 Coins · [Unbreakable Core]",
        5000,
        400,
        500,
        "Relic: [Unbreakable Core]",
        "shield",
        "#A78BFA",
    ),
    ForgeRecipe(
        "forge_blade",
        "Primordial Void Blade",
        "+900 Coins · [Sovereign's Edge]",
        10000,
        900,
        1000,
        "Relic: [Sovereign's Edge]",
        "auto_awesome",
        "#FFD36E",
    ),
)


def spawn_guardian_for_target_volume(target_volume_kg: float, index: int | None = None) -> LabyrinthGuardian:
    """Scale boss HP to the expected workout volume with an epic baseline."""
    base_hp = max(1200, int(target_volume_kg if target_volume_kg > 0 else 2500))
    idx = index if index is not None else (int(target_volume_kg) % len(GUARDIAN_TEMPLATES))
    template = GUARDIAN_TEMPLATES[idx % len(GUARDIAN_TEMPLATES)]
    return LabyrinthGuardian(
        id=template[0],
        name=template[1],
        title=template[2],
        affinity=template[3],
        max_hp=base_hp,
        current_hp=base_hp,
        sprite=template[4],
    )


@dataclass
class WorkoutSession:
    id: str
    routine_name: str
    exercises: list[ExerciseLog]
    guardian: LabyrinthGuardian
    started_at: str
    ended_at: str = ""
    is_completed: bool = False
    star_iron_earned: int = 0
    prs_broken: list[str] = field(default_factory=list)
    skills_awakened: list[str] = field(default_factory=list)

    @classmethod
    def start(cls, routine_name: str, exercise_ids: list[str], target_volume: float = 3000.0) -> WorkoutSession:
        guardian = spawn_guardian_for_target_volume(target_volume)
        logs = [
            ExerciseLog(
                exercise_id=eid,
                sets=[WorkoutSet(set_num=i + 1, weight_kg=0.0, reps=10) for i in range(3)],
            )
            for eid in exercise_ids
        ]
        return cls(
            id=str(uuid.uuid4())[:8],
            routine_name=routine_name or "Custom Raid",
            exercises=logs,
            guardian=guardian,
            started_at=datetime.now().isoformat(),
        )

    def log_set_complete(
        self,
        exercise_idx: int,
        set_idx: int,
        weight_kg: float,
        reps: int,
        existing_prs: dict[str, float] | None = None,
    ) -> tuple[int, bool, str | None]:
        """Record a completed set, deal damage to Guardian, and check for PR awakenings.

        Returns (damage_dealt, is_pr, awakened_skill_name).
        """
        if exercise_idx >= len(self.exercises):
            return 0, False, None
        ex_log = self.exercises[exercise_idx]
        if set_idx >= len(ex_log.sets):
            return 0, False, None

        w_set = ex_log.sets[set_idx]
        w_set.weight_kg = max(0.0, float(weight_kg))
        w_set.reps = max(0, int(reps))
        w_set.completed = True

        damage = int(w_set.volume_kg)
        self.guardian.current_hp = max(0, self.guardian.current_hp - damage)

        # Check PR
        is_pr = False
        awakened_skill = None
        ex_id = ex_log.exercise_id
        if existing_prs is not None:
            prev_max = existing_prs.get(ex_id, 0.0)
            if w_set.weight_kg > prev_max and w_set.weight_kg > 0:
                is_pr = True
                existing_prs[ex_id] = w_set.weight_kg
                pr_tag = f"{ex_log.exercise_name} ({w_set.weight_kg:.1f}kg)"
                if pr_tag not in self.prs_broken:
                    self.prs_broken.append(pr_tag)
                awakened_skill = "Unique Trait: [Limit Breaker]"
                if awakened_skill not in self.skills_awakened:
                    self.skills_awakened.append(awakened_skill)

        return damage, is_pr, awakened_skill

    def finish(self) -> dict[str, int | str | list[str]]:
        """Finalize workout session, calculate Star-Iron Ore and rewards."""
        self.ended_at = datetime.now().isoformat()
        self.is_completed = True
        total_volume = sum(ex.total_volume_kg for ex in self.exercises)
        # 1 kg volume = 1 Star-Iron Ore
        self.star_iron_earned = int(total_volume)

        # Muscle Group Traits
        for ex in self.exercises:
            item = ec.get_exercise(ex.exercise_id)
            if item and ex.total_volume_kg > 0:
                trait_map = {
                    "Chest": "Trait: [Iron Bulwark]",
                    "Back": "Trait: [Grip of the Depths]",
                    "Legs": "Trait: [Titan's Stride]",
                    "Shoulders": "Trait: [Gale Surge]",
                    "Arms": "Trait: [Adamantine Fist]",
                    "Core": "Trait: [Unshakable Core]",
                }
                trait = trait_map.get(item.muscle)
                if trait and trait not in self.skills_awakened:
                    self.skills_awakened.append(trait)

        # Coins & XP calculation: volume-based with caps to prevent inflation
        coins = min(80, max(15, math.ceil(total_volume / 120)))
        xp = min(250, max(40, math.ceil(total_volume / 25)))
        if self.guardian.is_defeated:
            coins += 25
            xp += 60

        return {
            "volume_kg": total_volume,
            "star_iron": self.star_iron_earned,
            "coins": coins,
            "xp": xp,
            "boss_defeated": self.guardian.is_defeated,
            "prs_broken": list(self.prs_broken),
            "skills_awakened": list(self.skills_awakened),
        }

