"""Adventure Run: a light auto-battler layered on a GPS walk/run. Pure logic, no flet.

Every SPAWN_INTERVAL_M of distance a pack spawns (2-3 NORMAL + 1 LEADER, and a BOSS_CHANCE
boss). Each tick, pace becomes DPS (see calculate_dps); the primary target (LOWEST_HP by
default) takes the full tick damage and up to CLEAVE_TARGETS other mobs take CLEAVE_RATIO
splash. Crossing a milestone (1K/3K/5K/10K) fires a Companion Shockwave split over the pack.
Defeats pay XP, coins and a chance at a cosmetic fragment (by tier).

The UI reads `AdventureEvent`s returned by update_tick() to drive sounds and animations.
Sprites live in src/assets/creatures/<sprite>; this module only knows the file names.
Defeated creatures drop trinket coins (1-5 for Normal/Leader, up to 10 for Boss) governed by a
separate daily adventure coin cap (`ADVENTURE_DAILY_COIN_CAP`).
"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

# --- Balance (tweak here) -------------------------------------------------------------------
SPAWN_INTERVAL_M = 350.0
MILESTONES_M: tuple[int, ...] = (1000, 3000, 5000, 10000)
BOSS_CHANCE = 0.20
NORMAL_COUNT = (2, 3)  # inclusive range of NORMAL mobs per pack
HP_SCALE_PER_KM = 0.15  # packs get +15% HP per km already covered
ADVENTURE_DAILY_COIN_CAP = 30  # separate daily cap for creature trinket coin drops

STILL_KMH = 2.5
WALK_MAX_KMH = 5.5
JOG_MAX_KMH = 8.5
WALK_DPS_PER_KMH = 4.5
JOG_DPS_PER_KMH = 6.5
SPRINT_DPS_PER_KMH = 9.0
JOG_CRIT = (0.25, 1.5)  # (chance, multiplier)
SPRINT_CRIT = (0.45, 2.0)

CLEAVE_RATIO = 0.45
CLEAVE_TARGETS = 2
SURGE_BASE = 250.0
SURGE_PER_KM = 50.0

FRAGMENT_CHANCE = {"normal": 0.05, "leader": 0.25, "boss": 0.80}


class CreatureTier(StrEnum):
    NORMAL = "normal"
    LEADER = "leader"
    BOSS = "boss"


class TargetMode(StrEnum):
    LOWEST_HP = "lowest_hp"
    STRONGEST = "strongest"
    MANUAL = "manual"


class EventType(StrEnum):
    SPAWN_CLUSTER = "spawn_cluster"
    DAMAGE_DEALT = "damage_dealt"
    MULTI_HIT = "multi_hit"
    CREATURE_DEFEATED = "creature_defeated"
    MILESTONE_SURGE = "milestone_surge"
    CLUSTER_CLEARED = "cluster_cleared"


@dataclass(frozen=True)
class CreatureDef:
    key: str
    name: str
    family: str
    tier: CreatureTier
    sprite: str  # file name under src/assets/creatures/
    hp: tuple[int, int]
    xp: tuple[int, int]
    coins: tuple[int, int]


def _d(name: str, family: str, tier: CreatureTier, hp: tuple[int, int], xp: tuple[int, int],
       coins: tuple[int, int]) -> CreatureDef:
    return CreatureDef(name, name, family, tier, f"{name}.png", hp, xp, coins)


_N, _L, _B = CreatureTier.NORMAL, CreatureTier.LEADER, CreatureTier.BOSS
CREATURES: dict[str, CreatureDef] = {c.key: c for c in (
    _d("Goblin Scout", "goblin", _N, (45, 65), (12, 18), (1, 3)),
    _d("Goblin Soldier", "goblin", _L, (130, 180), (40, 60), (3, 5)),
    _d("Goblin General", "goblin", _B, (380, 500), (160, 250), (8, 10)),
    _d("Slime", "slime", _N, (40, 55), (10, 16), (1, 2)),
    _d("BigSlime", "slime", _L, (120, 170), (38, 55), (3, 4)),
    _d("KingSlime", "slime", _B, (360, 480), (150, 230), (8, 10)),
    _d("Bat", "bat", _N, (35, 50), (11, 17), (1, 2)),
    _d("BatKing", "bat", _B, (340, 460), (150, 240), (8, 10)),
    _d("Boar", "boar", _N, (50, 70), (13, 19), (2, 3)),
    _d("WildBoar", "boar", _L, (140, 190), (42, 62), (4, 5)),
    _d("HugeBoar", "boar", _B, (400, 520), (170, 260), (9, 10)),
)}
FAMILIES: tuple[str, ...] = ("goblin", "slime", "bat", "boar")


def roster(tier: CreatureTier, family: str | None = None) -> list[CreatureDef]:
    return [c for c in CREATURES.values()
            if c.tier == tier and (family is None or c.family == family)]


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
    sprite: str = ""

    @property
    def is_alive(self) -> bool:
        return self.current_hp > 0.0

    @property
    def hp_percent(self) -> float:
        if self.max_hp <= 0:
            return 0.0
        return max(0.0, min(1.0, self.current_hp / self.max_hp))

    def take_damage(self, amount: float) -> float:
        """Applies damage and returns the damage actually dealt (never more than HP left)."""
        if not self.is_alive or amount <= 0:
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

    @property
    def has_boss(self) -> bool:
        return any(c.tier == CreatureTier.BOSS for c in self.creatures)

    def select_target(self, mode: TargetMode = TargetMode.LOWEST_HP,
                      manual_id: str | None = None) -> Creature | None:
        alive = self.alive_creatures
        if not alive:
            return None
        if mode == TargetMode.MANUAL and manual_id:
            for c in alive:
                if c.id == manual_id:
                    return c
            # locked target died: fall through to lowest HP so momentum never stalls
        if mode == TargetMode.STRONGEST:
            weight = {CreatureTier.BOSS: 3, CreatureTier.LEADER: 2, CreatureTier.NORMAL: 1}
            return max(alive, key=lambda c: (weight.get(c.tier, 1), c.current_hp))
        return min(alive, key=lambda c: c.current_hp)


class AdventureEngine:
    """Core adventure battle loop and encounter system."""

    DEFAULT_SPAWN_INTERVAL_M = SPAWN_INTERVAL_M
    MILESTONES_M = MILESTONES_M

    def __init__(self, target_mode: TargetMode = TargetMode.LOWEST_HP,
                 boss_encounter_chance: float = BOSS_CHANCE,
                 rng: random.Random | None = None) -> None:
        self.target_mode = target_mode
        self.boss_encounter_chance = boss_encounter_chance
        self.rng = rng or random.Random()
        self.active_cluster: EncounterCluster | None = None
        self.total_distance_m = 0.0
        self.next_spawn_distance_m = SPAWN_INTERVAL_M
        self.manual_target_id: str | None = None
        self.cleared_milestones: set[int] = set()
        self.total_xp_earned = 0
        self.total_coins_earned = 0
        self.creatures_defeated_count = 0
        self.cosmetic_fragments_count = 0

    # ------------------------------------------------------------------ spawning
    def _make(self, d: CreatureDef, cluster_id: str, slot: str, hp_scale: float) -> Creature:
        r = self.rng
        hp = round(r.randint(*d.hp) * hp_scale, 1)
        return Creature(
            id=f"{cluster_id}_{slot}", name=d.name, tier=d.tier, archetype=d.family,
            max_hp=hp, current_hp=hp, xp_reward=r.randint(*d.xp),
            coin_reward=r.randint(*d.coins),
            cosmetic_fragment_chance=FRAGMENT_CHANCE[d.tier.value], sprite=d.sprite)

    def generate_cluster(self, distance_m: float, force_boss: bool = False,
                         family: str | None = None) -> EncounterCluster:
        """A themed pack: 2-3 NORMAL + 1 LEADER of one family (Bat has no leader, so its
        packs borrow one), plus a random BOSS from any family on a BOSS_CHANCE roll."""
        r = self.rng
        cluster_id = f"cluster_{uuid.uuid4().hex[:8]}"
        fam = family or r.choice(FAMILIES)
        hp_scale = 1.0 + (distance_m / 1000.0) * HP_SCALE_PER_KM
        normal = roster(_N, fam)[0]
        creatures = [self._make(normal, cluster_id, f"m_{i}", hp_scale)
                     for i in range(r.randint(*NORMAL_COUNT))]
        leaders = roster(_L, fam) or roster(_L)
        creatures.append(self._make(r.choice(leaders), cluster_id, "leader", hp_scale))
        if force_boss or r.random() < self.boss_encounter_chance:
            creatures.append(self._make(r.choice(roster(_B)), cluster_id, "boss", hp_scale))
        return EncounterCluster(cluster_id, distance_m, creatures)

    # ------------------------------------------------------------------ combat math
    def calculate_dps(self, speed_kmh: float) -> tuple[float, bool]:
        """Pace -> (dps, is_crit). <2.5 km/h: 0. Walk: 4.5x. Jog (<=8.5): 6.5x, 25% crit
        x1.5. Sprint: 9.0x, 45% crit x2."""
        if speed_kmh < STILL_KMH:
            return 0.0, False
        if speed_kmh < WALK_MAX_KMH:
            return round(speed_kmh * WALK_DPS_PER_KMH, 1), False
        if speed_kmh <= JOG_MAX_KMH:
            base, (chance, mult) = speed_kmh * JOG_DPS_PER_KMH, JOG_CRIT
        else:
            base, (chance, mult) = speed_kmh * SPRINT_DPS_PER_KMH, SPRINT_CRIT
        crit = self.rng.random() < chance
        return round(base * mult if crit else base, 1), crit

    def base_dps(self, speed_kmh: float) -> float:
        """DPS without a crit roll (for the HUD counter; never consumes randomness)."""
        if speed_kmh < STILL_KMH:
            return 0.0
        k = (WALK_DPS_PER_KMH if speed_kmh < WALK_MAX_KMH else
             JOG_DPS_PER_KMH if speed_kmh <= JOG_MAX_KMH else SPRINT_DPS_PER_KMH)
        return round(speed_kmh * k, 1)

    def trigger_milestone_surge(self, milestone_m: int) -> list[AdventureEvent]:
        """Companion Shockwave: SURGE_BASE + SURGE_PER_KM x km, split over alive mobs."""
        events: list[AdventureEvent] = []
        cluster = self.active_cluster
        if not cluster or not cluster.has_alive:
            return events
        km = milestone_m // 1000
        burst = SURGE_BASE + (milestone_m / 1000.0) * SURGE_PER_KM
        alive = cluster.alive_creatures
        events.append(AdventureEvent(
            EventType.MILESTONE_SURGE,
            f"{km}K reached! Companion Shockwave: {burst:.0f} damage!",
            damage=burst, details={"milestone_m": milestone_m}))
        share = burst / len(alive)
        for c in alive:
            dealt = c.take_damage(share)
            events.append(AdventureEvent(EventType.MULTI_HIT, f"Shockwave hit {c.name}",
                                         target_id=c.id, target_name=c.name, damage=dealt,
                                         details={"source": "surge"}))
            if not c.is_alive:
                self._handle_creature_defeat(c, events)
        self._check_cleared(events, "by the Shockwave")
        return events

    def update_tick(self, delta_seconds: float, speed_kmh: float, distance_increment_m: float,
                    has_multi_hit: bool = True) -> list[AdventureEvent]:
        """One GPS/timer tick. Negative or bogus inputs are clamped (emulators, GPS jumps)."""
        events: list[AdventureEvent] = []
        delta_seconds = max(0.0, delta_seconds or 0.0)
        speed_kmh = max(0.0, speed_kmh or 0.0)
        self.total_distance_m += max(0.0, distance_increment_m or 0.0)

        for m in self.MILESTONES_M:
            if m not in self.cleared_milestones and self.total_distance_m >= m:
                self.cleared_milestones.add(m)
                events.extend(self.trigger_milestone_surge(m))

        cluster = self.active_cluster
        if (cluster is None or cluster.is_cleared) and \
                self.total_distance_m >= self.next_spawn_distance_m:
            cluster = self.active_cluster = self.generate_cluster(self.total_distance_m)
            self.manual_target_id = None
            if self.target_mode == TargetMode.MANUAL:
                self.target_mode = TargetMode.LOWEST_HP
            self.next_spawn_distance_m = self.total_distance_m + SPAWN_INTERVAL_M
            events.append(AdventureEvent(
                EventType.SPAWN_CLUSTER,
                ("A BOSS approaches!" if cluster.has_boss else "Encounter!")
                + f" {len(cluster.creatures)} creatures ahead.",
                details={"creature_count": len(cluster.creatures),
                         "cluster_id": cluster.cluster_id, "has_boss": cluster.has_boss}))

        if not cluster or not cluster.has_alive or delta_seconds <= 0:
            return events
        dps, crit = self.calculate_dps(speed_kmh)
        if dps <= 0:
            return events
        tick = dps * delta_seconds
        target = cluster.select_target(self.target_mode, self.manual_target_id)
        if target is None:
            return events
        dealt = target.take_damage(tick)
        events.append(AdventureEvent(
            EventType.DAMAGE_DEALT,
            f"{'CRIT! ' if crit else ''}Hit {target.name} for {dealt:.0f}",
            target_id=target.id, target_name=target.name, damage=dealt, is_crit=crit))
        if has_multi_hit:
            for other in [c for c in cluster.alive_creatures if c.id != target.id][
                    :CLEAVE_TARGETS]:
                s = other.take_damage(tick * CLEAVE_RATIO)
                events.append(AdventureEvent(
                    EventType.MULTI_HIT, f"Cleave hit {other.name} for {s:.0f}",
                    target_id=other.id, target_name=other.name, damage=s, is_crit=crit,
                    details={"source": "cleave"}))
                if not other.is_alive:
                    self._handle_creature_defeat(other, events)
        if not target.is_alive:
            self._handle_creature_defeat(target, events)
        self._check_cleared(events)
        return events

    # ------------------------------------------------------------------ helpers
    def _check_cleared(self, events: list[AdventureEvent], how: str = "") -> None:
        c = self.active_cluster
        if c and not c.is_cleared and not c.has_alive:
            c.is_cleared = True
            events.append(AdventureEvent(EventType.CLUSTER_CLEARED,
                                         f"Pack cleared{' ' + how if how else ''}!",
                                         details={"cluster_id": c.cluster_id}))

    def _handle_creature_defeat(self, creature: Creature, events: list[AdventureEvent]) -> None:
        self.creatures_defeated_count += 1
        self.total_xp_earned += creature.xp_reward
        self.total_coins_earned += creature.coin_reward
        frag = self.rng.random() < creature.cosmetic_fragment_chance
        if frag:
            self.cosmetic_fragments_count += 1
        events.append(AdventureEvent(
            EventType.CREATURE_DEFEATED,
            f"Defeated {creature.name}! +{creature.xp_reward} XP, +{creature.coin_reward} coins"
            + (" (+1 fragment)" if frag else ""),
            target_id=creature.id, target_name=creature.name, xp_gained=creature.xp_reward,
            coins_gained=creature.coin_reward,
            details={"fragment_gained": frag, "tier": creature.tier.value}))
