from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CreatureTier(str, Enum):
    NORMAL = "normal"
    LEADER = "leader"
    BOSS = "boss"


class TargetMode(str, Enum):
    LOWEST_HP = "lowest_hp"
    STRONGEST = "strongest"
    MANUAL = "manual"


class EventType(str, Enum):
    SPAWN_CLUSTER = "spawn_cluster"
    DAMAGE_DEALT = "damage_dealt"
    MULTI_HIT = "multi_hit"
    CREATURE_DEFEATED = "creature_defeated"
    MILESTONE_SURGE = "milestone_surge"
    CLUSTER_CLEARED = "cluster_cleared"


@dataclass
class AdventureEvent:
    event_type: EventType
    message: str
    target_id: str | None = None
    target_name: str | None = None
    damage: float = 0.0
    xp_gained: int = 0
    coins_gained: int = 0
    is_crit: bool = False
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class Creature:
    id: str
    name: str
    tier: CreatureTier
    archetype: str
    max_hp: float
    current_hp: float
    xp_reward: int
    coin_reward: int
    cosmetic_fragment_chance: float = 0.0

    @property
    def is_alive(self) -> bool:
        return self.current_hp > 0.0

    @property
    def hp_percent(self) -> float:
        if self.max_hp <= 0:
            return 0.0
        return max(0.0, min(1.0, self.current_hp / self.max_hp))

    def take_damage(self, amount: float) -> float:
        """Applies damage and returns actual damage dealt."""
        if not self.is_alive:
            return 0.0
        actual = min(self.current_hp, amount)
        self.current_hp = max(0.0, self.current_hp - amount)
        return actual


@dataclass
class EncounterCluster:
    cluster_id: str
    spawn_distance_m: float
    creatures: list[Creature]
    is_cleared: bool = False

    @property
    def alive_creatures(self) -> list[Creature]:
        return [c for c in self.creatures if c.is_alive]

    @property
    def has_alive(self) -> bool:
        return any(c.is_alive for c in self.creatures)

    def select_target(
        self,
        mode: TargetMode = TargetMode.LOWEST_HP,
        manual_id: str | None = None,
    ) -> Creature | None:
        alive = self.alive_creatures
        if not alive:
            return None

        if mode == TargetMode.MANUAL and manual_id:
            for c in alive:
                if c.id == manual_id:
                    return c

        if mode == TargetMode.STRONGEST:
            # Boss > Leader > Normal, then highest HP
            tier_weights = {
                CreatureTier.BOSS: 3,
                CreatureTier.LEADER: 2,
                CreatureTier.NORMAL: 1,
            }
            return max(
                alive,
                key=lambda c: (tier_weights.get(c.tier, 1), c.current_hp),
            )

        # Default: Lowest HP first for satisfying fast clearing
        return min(alive, key=lambda c: c.current_hp)


class AdventureEngine:
    """Core adventure battle loop and encounter system."""

    DEFAULT_SPAWN_INTERVAL_M = 350.0  # Encounter cluster every 350 meters
    MILESTONES_M: tuple[int, ...] = (1000, 3000, 5000, 10000)

    SLIME_NAMES: tuple[str, ...] = (
        "Lil' Cyan Slime",
        "Batwing Slime",
        "Honey Bear Slime",
        "Berry Slime",
        "Melon Slime",
    )

    def __init__(
        self,
        target_mode: TargetMode = TargetMode.LOWEST_HP,
        boss_encounter_chance: float = 0.20,
    ) -> None:
        self.target_mode = target_mode
        self.boss_encounter_chance = boss_encounter_chance
        self.active_cluster: EncounterCluster | None = None
        self.total_distance_m: float = 0.0
        self.next_spawn_distance_m: float = self.DEFAULT_SPAWN_INTERVAL_M
        self.manual_target_id: str | None = None

        self.cleared_milestones: set[int] = set()
        self.total_xp_earned: int = 0
        self.total_coins_earned: int = 0
        self.creatures_defeated_count: int = 0
        self.cosmetic_fragments_count: int = 0

    def generate_cluster(
        self, distance_m: float, force_boss: bool = False
    ) -> EncounterCluster:
        """Generates a pack of slimes with randomized attributes and a potential boss."""
        cluster_id = f"cluster_{uuid.uuid4().hex[:8]}"
        creatures: list[Creature] = []

        is_boss_pack = force_boss or (
            random.random() < self.boss_encounter_chance
        )

        # Base pack scaling with distance (slight level scaling per km)
        km = distance_m / 1000.0
        hp_scale = 1.0 + (km * 0.15)

        # 2-4 Normal Slimes
        normal_count = random.randint(2, 3)
        for i in range(normal_count):
            name = random.choice(self.SLIME_NAMES)
            base_hp = random.randint(40, 65) * hp_scale
            creatures.append(
                Creature(
                    id=f"{cluster_id}_m_{i}",
                    name=name,
                    tier=CreatureTier.NORMAL,
                    archetype="slime",
                    max_hp=round(base_hp, 1),
                    current_hp=round(base_hp, 1),
                    xp_reward=random.randint(12, 18),
                    coin_reward=random.randint(5, 10),
                    cosmetic_fragment_chance=0.05,
                )
            )

        # 1 Slime Leader
        leader_hp = random.randint(120, 180) * hp_scale
        creatures.append(
            Creature(
                id=f"{cluster_id}_leader",
                name="Slime Commander",
                tier=CreatureTier.LEADER,
                archetype="slime_leader",
                max_hp=round(leader_hp, 1),
                current_hp=round(leader_hp, 1),
                xp_reward=random.randint(40, 60),
                coin_reward=random.randint(25, 40),
                cosmetic_fragment_chance=0.25,
            )
        )

        # Optional Random Boss Encounter
        if is_boss_pack:
            boss_hp = random.randint(350, 500) * hp_scale
            creatures.append(
                Creature(
                    id=f"{cluster_id}_boss",
                    name="Emperor Slime King",
                    tier=CreatureTier.BOSS,
                    archetype="slime_boss",
                    max_hp=round(boss_hp, 1),
                    current_hp=round(boss_hp, 1),
                    xp_reward=random.randint(150, 250),
                    coin_reward=random.randint(80, 150),
                    cosmetic_fragment_chance=0.75,
                )
            )

        return EncounterCluster(
            cluster_id=cluster_id,
            spawn_distance_m=distance_m,
            creatures=creatures,
        )

    def calculate_dps(self, speed_kmh: float) -> tuple[float, bool]:
        """Calculates DPS and critical strike based on pace.

        Speed bands:
        - < 2.5 km/h: 0 DPS (stationary/paused)
        - 2.5 - 5.5 km/h (Walking): 15-25 base DPS
        - 5.5 - 8.5 km/h (Jogging): 35-55 DPS + 25% crit chance (1.5x)
        - > 8.5 km/h (Sprinting): 70-110 DPS + 45% crit chance (2.0x)
        """
        if speed_kmh < 2.5:
            return 0.0, False

        is_crit = False
        if speed_kmh < 5.5:
            base_dps = speed_kmh * 4.5
        elif speed_kmh <= 8.5:
            base_dps = speed_kmh * 6.5
            if random.random() < 0.25:
                base_dps *= 1.5
                is_crit = True
        else:
            base_dps = speed_kmh * 9.0
            if random.random() < 0.45:
                base_dps *= 2.0
                is_crit = True

        return round(base_dps, 1), is_crit

    def trigger_milestone_surge(
        self, milestone_m: int
    ) -> list[AdventureEvent]:
        """Unleashes a massive companion shockwave when passing a 1K/3K/5K distance tier."""
        events: list[AdventureEvent] = []
        if not self.active_cluster or not self.active_cluster.has_alive:
            return events

        # Massive burst damage: 250 base + 50 per km
        burst_dmg = 250.0 + ((milestone_m / 1000.0) * 50.0)
        alive = self.active_cluster.alive_creatures

        events.append(
            AdventureEvent(
                event_type=EventType.MILESTONE_SURGE,
                message=f"Milestone {milestone_m // 1000}K reached! Companion unleashes Milestone Shockwave ({burst_dmg:.0f} AoE damage)!",
                damage=burst_dmg,
            )
        )

        # Distribute burst damage across all alive creatures in the cluster
        damage_per_creature = burst_dmg / len(alive)
        for creature in alive:
            creature.take_damage(damage_per_creature)
            if not creature.is_alive:
                self._handle_creature_defeat(creature, events)

        if not self.active_cluster.has_alive:
            self.active_cluster.is_cleared = True
            events.append(
                AdventureEvent(
                    event_type=EventType.CLUSTER_CLEARED,
                    message=f"Cluster {self.active_cluster.cluster_id} cleared by Milestone Surge!",
                )
            )

        return events

    def update_tick(
        self,
        delta_seconds: float,
        speed_kmh: float,
        distance_increment_m: float,
        has_multi_hit: bool = True,
    ) -> list[AdventureEvent]:
        """Main periodic update loop called by the GPS tracking tick."""
        events: list[AdventureEvent] = []
        self.total_distance_m += distance_increment_m

        # 1. Check Distance Milestones
        for m in self.MILESTONES_M:
            if m not in self.cleared_milestones and self.total_distance_m >= m:
                self.cleared_milestones.add(m)
                milestone_events = self.trigger_milestone_surge(m)
                events.extend(milestone_events)

        # 2. Spawn Cluster if distance reached and no active cluster
        if (
            self.active_cluster is None or self.active_cluster.is_cleared
        ) and self.total_distance_m >= self.next_spawn_distance_m:
            self.active_cluster = self.generate_cluster(self.total_distance_m)
            self.next_spawn_distance_m = (
                self.total_distance_m + self.DEFAULT_SPAWN_INTERVAL_M
            )
            events.append(
                AdventureEvent(
                    event_type=EventType.SPAWN_CLUSTER,
                    message=f"Encounter! Encountered a pack of {len(self.active_cluster.creatures)} creatures!",
                    details={
                        "creature_count": len(self.active_cluster.creatures),
                        "cluster_id": self.active_cluster.cluster_id,
                    },
                )
            )

        # 3. Combat Execution
        if (
            self.active_cluster
            and self.active_cluster.has_alive
            and delta_seconds > 0
        ):
            dps, is_crit = self.calculate_dps(speed_kmh)
            if dps > 0:
                tick_damage = dps * delta_seconds

                target = self.active_cluster.select_target(
                    mode=self.target_mode,
                    manual_id=self.manual_target_id,
                )

                if target:
                    dealt = target.take_damage(tick_damage)
                    events.append(
                        AdventureEvent(
                            event_type=EventType.DAMAGE_DEALT,
                            target_id=target.id,
                            target_name=target.name,
                            damage=dealt,
                            is_crit=is_crit,
                            message=f"{'CRIT! ' if is_crit else ''}Hit {target.name} for {dealt:.1f} dmg ({target.current_hp:.1f}/{target.max_hp:.1f} HP)",
                        )
                    )

                    # Multi-Hit Cleave (hits up to 2 other alive targets for 45% splash)
                    alive_others = [
                        c
                        for c in self.active_cluster.alive_creatures
                        if c.id != target.id
                    ]
                    if has_multi_hit and alive_others:
                        splash_dmg = tick_damage * 0.45
                        for splash_target in alive_others[:2]:
                            s_dealt = splash_target.take_damage(splash_dmg)
                            events.append(
                                AdventureEvent(
                                    event_type=EventType.MULTI_HIT,
                                    target_id=splash_target.id,
                                    target_name=splash_target.name,
                                    damage=s_dealt,
                                    message=f"Multi-Hit cleaved {splash_target.name} for {s_dealt:.1f} dmg",
                                )
                            )
                            if not splash_target.is_alive:
                                self._handle_creature_defeat(
                                    splash_target, events
                                )

                    # Check Primary Target Defeat
                    if not target.is_alive:
                        self._handle_creature_defeat(target, events)

                    # Check if entire cluster cleared
                    if not self.active_cluster.has_alive:
                        self.active_cluster.is_cleared = True
                        events.append(
                            AdventureEvent(
                                event_type=EventType.CLUSTER_CLEARED,
                                message=f"Cluster {self.active_cluster.cluster_id} cleared!",
                            )
                        )

        return events

    def _handle_creature_defeat(
        self, creature: Creature, events: list[AdventureEvent]
    ) -> None:
        """Handles rewards, stat tracking, and defeat event emission."""
        self.creatures_defeated_count += 1
        self.total_xp_earned += creature.xp_reward
        self.total_coins_earned += creature.coin_reward

        frag_gained = False
        if random.random() < creature.cosmetic_fragment_chance:
            self.cosmetic_fragments_count += 1
            frag_gained = True

        events.append(
            AdventureEvent(
                event_type=EventType.CREATURE_DEFEATED,
                target_id=creature.id,
                target_name=creature.name,
                xp_gained=creature.xp_reward,
                coins_gained=creature.coin_reward,
                details={"fragment_gained": frag_gained},
                message=f"Defeated {creature.name}! +{creature.xp_reward} XP, +${creature.coin_reward} Coins{' (+1 Cosmetic Frag!)' if frag_gained else ''}",
            )
        )
