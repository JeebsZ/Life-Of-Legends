"""Mind Grove: The Fitness Farm Core Engine for LUMA.

Real-world health and fitness actions (water, walks/runs, workouts, sleep/focus)
fuel crop growth, seed cross-breeding, and botanical rewards.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from lol.core.game import Game


@dataclass(frozen=True)
class SeedDef:
    id: str
    name: str
    tier: int  # 1: Base Spore, 2: Hybrid, 3: Mystic, 4: Mythic
    rarity: str  # "Common", "Uncommon", "Rare", "Mythic"
    desc: str
    growth_time_s: int  # Base growth time in seconds
    coin_yield: int
    color: str
    icon_name: str
    emoji: str
    mutation_chance: float = 0.08


# --- Catalog of all 16 Flora Seeds ---
SEEDS: dict[str, SeedDef] = {
    # Tier 1: Base Spores (Earned exclusively via daily health habits)
    "seed_aqua": SeedDef(
        "seed_aqua",
        "Aqua Spore",
        1,
        "Common",
        "A bioluminescent water spore earned by staying hydrated.",
        growth_time_s=1800,  # 30 mins base (or ~5 mins with a walk)
        coin_yield=60,
        color="#00F5D4",
        icon_name="water_drop",
        emoji="💧",
    ),
    "seed_solar": SeedDef(
        "seed_solar",
        "Solar Fern Seed",
        1,
        "Common",
        "A radiant ember seed energized by outdoor walks and runs.",
        growth_time_s=1800,
        coin_yield=65,
        color="#FFD166",
        icon_name="wb_sunny",
        emoji="☀️",
    ),
    "seed_terra": SeedDef(
        "seed_terra",
        "Terra Bulb",
        1,
        "Common",
        "An iron-dense earthen bulb strengthened by gym and workout sessions.",
        growth_time_s=2400,
        coin_yield=75,
        color="#06D6A0",
        icon_name="fitness_center",
        emoji="🪨",
    ),
    "seed_spirit": SeedDef(
        "seed_spirit",
        "Spirit Sprout",
        1,
        "Common",
        "A tranquil twilight seed nurtured by mindful sleep and focus sessions.",
        growth_time_s=2400,
        coin_yield=75,
        color="#C77DFF",
        icon_name="self_improvement",
        emoji="🌙",
    ),
    # Tier 2: Elemental Hybrids (Synthesized at the Altar from 2 Tier 1 seeds)
    "seed_mist": SeedDef(
        "seed_mist",
        "Vapor Orchid",
        2,
        "Uncommon",
        "A delicate blossom that shimmers with warm morning mist. (Aqua + Solar)",
        growth_time_s=3600,  # 1 hour
        coin_yield=180,
        color="#FF99C8",
        icon_name="local_florist",
        emoji="🌸",
    ),
    "seed_deep": SeedDef(
        "seed_deep",
        "Tide Root",
        2,
        "Uncommon",
        "A glowing abyssal root rich in ocean minerals. (Aqua + Terra)",
        growth_time_s=4200,
        coin_yield=200,
        color="#48CAE4",
        icon_name="waves",
        emoji="🌿",
    ),
    "seed_magma": SeedDef(
        "seed_magma",
        "Cinder Pepper",
        2,
        "Uncommon",
        "A warm volcanic pepper pulsing with kinetic heat. (Solar + Terra)",
        growth_time_s=4200,
        coin_yield=220,
        color="#FF6B35",
        icon_name="whatshot",
        emoji="🌶️",
    ),
    "seed_dawn": SeedDef(
        "seed_dawn",
        "Aurora Lily",
        2,
        "Uncommon",
        "A celestial flower that blooms with changing sunrise hues. (Solar + Spirit)",
        growth_time_s=4800,
        coin_yield=240,
        color="#FFB4D6",
        icon_name="flare",
        emoji="🌻",
    ),
    "seed_frost": SeedDef(
        "seed_frost",
        "Frost Lotus",
        2,
        "Uncommon",
        "A crystalline flower that radiates a soothing winter chill. (Aqua + Spirit)",
        growth_time_s=4800,
        coin_yield=250,
        color="#A0C4FF",
        icon_name="ac_unit",
        emoji="❄️",
    ),
    "seed_iron": SeedDef(
        "seed_iron",
        "Star-Iron Acorn",
        2,
        "Uncommon",
        "A sturdy metallic acorn forged with earthen resilience. (Terra + Spirit)",
        growth_time_s=5400,
        coin_yield=270,
        color="#BDB2FF",
        icon_name="shield",
        emoji="🌰",
    ),
    # Tier 3: Mystical Flora (Synthesized from Tier 2 Hybrids)
    "seed_volcanic": SeedDef(
        "seed_volcanic",
        "Volcanic Bloom",
        3,
        "Rare",
        "A blazing floral wonder that blooms amid floating embers. (Mist + Magma)",
        growth_time_s=7200,  # 2 hours
        coin_yield=600,
        color="#EF476F",
        icon_name="local_fire_department",
        emoji="⚡",
        mutation_chance=0.12,
    ),
    "seed_celestial": SeedDef(
        "seed_celestial",
        "Celestial Dahlia",
        3,
        "Rare",
        "Shimmers with concentrated deep-space stardust and diamond petals. (Frost + Dawn)",
        growth_time_s=8400,
        coin_yield=750,
        color="#7209B7",
        icon_name="stars",
        emoji="🌌",
        mutation_chance=0.15,
    ),
    "seed_chrono": SeedDef(
        "seed_chrono",
        "Chrono Rose",
        3,
        "Rare",
        "An intricate golden rose whose petals turn in rhythmic motion. (Dawn + Deep)",
        growth_time_s=9600,
        coin_yield=850,
        color="#FFD166",
        icon_name="hourglass_bottom",
        emoji="⏳",
        mutation_chance=0.15,
    ),
    "seed_storm": SeedDef(
        "seed_storm",
        "Thunder Blossom",
        3,
        "Rare",
        "Crackles with electric violet lightning across its leaves. (Mist + Iron)",
        growth_time_s=9600,
        coin_yield=900,
        color="#3A86FF",
        icon_name="bolt",
        emoji="⛈️",
        mutation_chance=0.15,
    ),
    # Tier 4: Mythic World Tree Flora
    "seed_yggdrasil": SeedDef(
        "seed_yggdrasil",
        "World Tree Sapling",
        4,
        "Mythic",
        "An ancient sprout pulsing with the primal life energy of the cosmos. (Deep + Iron)",
        growth_time_s=14400,  # 4 hours
        coin_yield=2200,
        color="#06D6A0",
        icon_name="park",
        emoji="🌳",
    ),
    "seed_void": SeedDef(
        "seed_void",
        "Void Dragonfruit",
        4,
        "Mythic",
        "A dark cosmic fruit enveloped in faint gravitational nebula rings. (Celestial + Volcanic)",
        growth_time_s=18000,  # 5 hours
        coin_yield=2800,
        color="#9D4EDD",
        icon_name="auto_awesome",
        emoji="🐉",
    ),
}

# --- Altar Fusion Recipes Matrix ---
FUSION_RECIPES: dict[frozenset[str], str] = {
    # Tier 1 + Tier 1 -> Tier 2
    frozenset({"seed_aqua", "seed_solar"}): "seed_mist",
    frozenset({"seed_aqua", "seed_terra"}): "seed_deep",
    frozenset({"seed_solar", "seed_terra"}): "seed_magma",
    frozenset({"seed_solar", "seed_spirit"}): "seed_dawn",
    frozenset({"seed_aqua", "seed_spirit"}): "seed_frost",
    frozenset({"seed_terra", "seed_spirit"}): "seed_iron",
    # Tier 2 + Tier 2 -> Tier 3
    frozenset({"seed_mist", "seed_magma"}): "seed_volcanic",
    frozenset({"seed_frost", "seed_dawn"}): "seed_celestial",
    frozenset({"seed_dawn", "seed_deep"}): "seed_chrono",
    frozenset({"seed_mist", "seed_iron"}): "seed_storm",
    # Tier 3 Cross-Breeding -> Tier 4 Mythics
    frozenset({"seed_deep", "seed_iron"}): "seed_yggdrasil",
    frozenset({"seed_celestial", "seed_volcanic"}): "seed_void",
}


@dataclass
class CropPlot:
    plot_id: int
    seed_id: str = ""
    planted_at: str = ""  # ISO datetime string
    watered_at: str = ""  # ISO datetime string
    boost_s: float = 0.0  # Seconds shaved off by sunlight/fitness
    harvest_ready: bool = False

    def is_empty(self) -> bool:
        return not self.seed_id


@dataclass
class GroveState:
    plots: list[CropPlot] = field(default_factory=list)
    seeds: dict[str, int] = field(default_factory=dict)  # seed_id -> count
    harvested: dict[str, int] = field(default_factory=dict)  # seed_id -> count
    total_harvests: int = 0
    discovered_fusions: list[str] = field(default_factory=list)
    last_awarded_habits: dict[str, str] = field(default_factory=dict)  # habit_name -> ISO day

    def __post_init__(self) -> None:
        if not self.plots:
            # Initialize default 6 plots
            self.plots = [CropPlot(plot_id=i) for i in range(6)]
        # Default starter gift if brand new
        if not self.seeds and self.total_harvests == 0:
            self.seeds = {
                "seed_aqua": 2,
                "seed_solar": 2,
                "seed_terra": 1,
                "seed_spirit": 1,
            }


def get_seed(seed_id: str) -> SeedDef | None:
    return SEEDS.get(seed_id)


def plot_progress(plot: CropPlot, now: datetime | None = None) -> float:
    """Return 0.0 to 1.0 progress of the plot."""
    if plot.is_empty():
        return 0.0
    if plot.harvest_ready:
        return 1.0
    seed = get_seed(plot.seed_id)
    if not seed:
        return 0.0
    now_dt = now or datetime.now(UTC)
    try:
        planted = datetime.fromisoformat(plot.planted_at)
        elapsed = (now_dt - planted).total_seconds() + plot.boost_s
        required = float(seed.growth_time_s)
        return min(1.0, max(0.0, elapsed / required))
    except (ValueError, TypeError, KeyError):
        return 0.0


def plot_remaining_s(plot: CropPlot, now: datetime | None = None) -> float:
    """Return seconds remaining until harvest is ready."""
    if plot.is_empty() or plot.harvest_ready:
        return 0.0
    seed = get_seed(plot.seed_id)
    if not seed:
        return 0.0
    now_dt = now or datetime.now(UTC)
    try:
        planted = datetime.fromisoformat(plot.planted_at)
        elapsed = (now_dt - planted).total_seconds() + plot.boost_s
        required = float(seed.growth_time_s)
        return max(0.0, required - elapsed)
    except (ValueError, TypeError, KeyError):
        return 0.0


def plant_crop(grove: GroveState, plot_id: int, seed_id: str, now: datetime | None = None) -> bool:
    """Plant a seed from inventory into a plot."""
    if plot_id < 0 or plot_id >= len(grove.plots):
        return False
    plot = grove.plots[plot_id]
    if not plot.is_empty():
        return False
    if grove.seeds.get(seed_id, 0) <= 0:
        return False

    now_dt = now or datetime.now(UTC)
    grove.seeds[seed_id] -= 1
    if grove.seeds[seed_id] <= 0:
        del grove.seeds[seed_id]

    plot.seed_id = seed_id
    plot.planted_at = now_dt.isoformat()
    plot.watered_at = now_dt.isoformat()
    plot.boost_s = 0.0
    plot.harvest_ready = False
    return True


def harvest_crop(
    grove: GroveState, plot_id: int, rng: random.Random | None = None
) -> tuple[int, list[str]]:
    """Harvest ready crop. Returns (coins_earned, bonus_seeds)."""
    if plot_id < 0 or plot_id >= len(grove.plots):
        return 0, []
    plot = grove.plots[plot_id]
    if plot.is_empty() or not plot.harvest_ready:
        return 0, []

    seed = get_seed(plot.seed_id)
    r = rng or random.Random()
    coins = seed.coin_yield if seed else 50

    # Record harvest in silo
    grove.harvested[plot.seed_id] = grove.harvested.get(plot.seed_id, 0) + 1
    grove.total_harvests += 1

    # Bonus seeds roll
    bonus: list[str] = []
    # Always yield at least 1 returned seed or mutation
    if r.random() < (seed.mutation_chance if seed else 0.08):
        # Lucky Starlight Mutation! Yield a random Tier 2 or Tier 3 seed!
        mutated = r.choice(list(SEEDS.keys()))
        bonus.append(mutated)
        grove.seeds[mutated] = grove.seeds.get(mutated, 0) + 1
    else:
        # Standard seed drop
        bonus.append(plot.seed_id)
        grove.seeds[plot.seed_id] = grove.seeds.get(plot.seed_id, 0) + 1

    # Reset plot
    plot.seed_id = ""
    plot.planted_at = ""
    plot.watered_at = ""
    plot.boost_s = 0.0
    plot.harvest_ready = False

    return coins, bonus


def fuse_seeds(
    grove: GroveState, seed_a: str, seed_b: str, rng: random.Random | None = None
) -> tuple[str, bool]:
    """Combine 2 seeds at the Botanical Altar. Returns (result_seed_id, is_mutation)."""
    if grove.seeds.get(seed_a, 0) <= 0 or grove.seeds.get(seed_b, 0) <= 0:
        return "", False
    # If same seed, make sure we have at least 2
    if seed_a == seed_b and grove.seeds.get(seed_a, 0) < 2:
        return "", False

    r = rng or random.Random()

    # Deduct ingredients
    grove.seeds[seed_a] -= 1
    if grove.seeds[seed_a] <= 0:
        del grove.seeds[seed_a]
    grove.seeds[seed_b] -= 1
    if grove.seeds[seed_b] <= 0:
        del grove.seeds[seed_b]

    pair = frozenset({seed_a, seed_b})
    is_mutation = False
    result_seed = ""

    if pair in FUSION_RECIPES:
        result_seed = FUSION_RECIPES[pair]
        # Lucky 10% chance to jump a tier higher
        target_def = get_seed(result_seed)
        if target_def and r.random() < 0.10:
            higher_tier_candidates = [
                s.id for s in SEEDS.values() if s.tier == min(4, target_def.tier + 1)
            ]
            if higher_tier_candidates:
                result_seed = r.choice(higher_tier_candidates)
                is_mutation = True
    else:
        # No direct recipe: combine essences and synthesize a random seed of the higher tier!
        tier_a = get_seed(seed_a).tier if get_seed(seed_a) else 1
        tier_b = get_seed(seed_b).tier if get_seed(seed_b) else 1
        target_tier = min(4, max(tier_a, tier_b))
        candidates = [s.id for s in SEEDS.values() if s.tier == target_tier]
        result_seed = r.choice(candidates)
        is_mutation = False

    # Award the synthesized seed
    grove.seeds[result_seed] = grove.seeds.get(result_seed, 0) + 1
    if result_seed not in grove.discovered_fusions:
        grove.discovered_fusions.append(result_seed)

    return result_seed, is_mutation


def sync_fitness_to_grove(
    game: Game, now: datetime | None = None
) -> dict[str, Any]:
    """Connect real-world LUMA habit and fitness data to Mind Grove.

    - Water logged today -> Waters all active plots.
    - Walk/Run distance today -> Grants sunlight seconds off plot countdowns.
    - Daily milestones -> Awards base seeds (Aqua, Solar, Terra, Spirit).
    """
    now_dt = now or datetime.now(UTC)
    today_iso = (game.today() if hasattr(game, "today") else date.today()).isoformat()

    grove: GroveState = getattr(game.data, "grove", None)
    if grove is None:
        grove = GroveState()
        game.data.grove = grove

    awarded_seeds: list[str] = []

    # 1. Water Tracker Hook -> Aqua Spore award (if water >= 1500 mL)
    total_water_ml = sum(
        getattr(w, "amount_ml", 0)
        for w in getattr(game.data, "water", [])
        if getattr(w, "day", "") == today_iso
    )
    if total_water_ml >= 1500 and grove.last_awarded_habits.get("water") != today_iso:
        grove.seeds["seed_aqua"] = grove.seeds.get("seed_aqua", 0) + 1
        grove.last_awarded_habits["water"] = today_iso
        awarded_seeds.append("seed_aqua")

    # Water all plots if any water was drank today
    if total_water_ml > 0:
        for p in grove.plots:
            if not p.is_empty():
                p.watered_at = now_dt.isoformat()

    # 2. GPS Walk/Run Hook -> Solar Fern award & Sunlight speed-up
    total_run_dist_m = sum(
        getattr(r, "distance_m", 0.0)
        for r in getattr(game.data, "runs", [])
        if getattr(r, "day", "") == today_iso
    )
    if total_run_dist_m >= 2000 and grove.last_awarded_habits.get("run") != today_iso:
        grove.seeds["seed_solar"] = grove.seeds.get("seed_solar", 0) + 1
        grove.last_awarded_habits["run"] = today_iso
        awarded_seeds.append("seed_solar")

    # Every 100 meters = 60s boost to all growing plots
    sunlight_boost_s = math.floor(total_run_dist_m / 100.0) * 60.0

    # 3. Workout Hook -> Terra Bulb award
    today_workouts = [
        w
        for w in getattr(game.data, "workouts", [])
        if getattr(w, "day", "") == today_iso
    ]
    if len(today_workouts) >= 1 and grove.last_awarded_habits.get("workout") != today_iso:
        grove.seeds["seed_terra"] = grove.seeds.get("seed_terra", 0) + 1
        grove.last_awarded_habits["workout"] = today_iso
        awarded_seeds.append("seed_terra")

    # 4. Sleep & Focus Hook -> Spirit Sprout award
    today_sleep = any(
        getattr(s, "night_of", getattr(s, "day", "")) == today_iso
        or getattr(s, "logged_on", "") == today_iso
        for s in getattr(game.data, "sleep", [])
    )
    today_focus = any(
        getattr(f, "day", "") == today_iso for f in getattr(game.data, "focus_sessions", [])
    )
    if (today_sleep or today_focus) and grove.last_awarded_habits.get("spirit") != today_iso:
        grove.seeds["seed_spirit"] = grove.seeds.get("seed_spirit", 0) + 1
        grove.last_awarded_habits["spirit"] = today_iso
        awarded_seeds.append("seed_spirit")

    # Update plot readiness
    plots_ready_count = 0
    for p in grove.plots:
        if not p.is_empty() and not p.harvest_ready:
            p.boost_s = sunlight_boost_s
            if plot_remaining_s(p, now_dt) <= 0:
                p.harvest_ready = True
                plots_ready_count += 1

    return {
        "awarded_seeds": awarded_seeds,
        "plots_ready": plots_ready_count,
        "sunlight_boost_s": sunlight_boost_s,
    }
