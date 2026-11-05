from __future__ import annotations

import unittest
from datetime import date

from src.lol.core.adventure import (
    ADVENTURE_DAILY_COIN_CAP,
    CREATURES,
    FRAGMENT_CHANCE,
    AdventureEngine,
    Creature,
    CreatureTier,
    EventType,
    TargetMode,
)
from src.lol.core.game import DAILY_COIN_CAP, Game


class TestAdventure(unittest.TestCase):
    def test_creature_hp_and_damage(self):
        slime = Creature(
            id="c1",
            name="Lil Slime",
            tier=CreatureTier.NORMAL,
            archetype="slime",
            max_hp=50.0,
            current_hp=50.0,
            xp_reward=15,
            coin_reward=5,
        )
        self.assertTrue(slime.is_alive)
        self.assertEqual(slime.hp_percent, 1.0)

        dealt = slime.take_damage(20.0)
        self.assertEqual(dealt, 20.0)
        self.assertEqual(slime.current_hp, 30.0)
        self.assertTrue(slime.is_alive)

        overkill = slime.take_damage(40.0)
        self.assertEqual(overkill, 30.0)
        self.assertEqual(slime.current_hp, 0.0)
        self.assertFalse(slime.is_alive)

    def test_dps_pace_scaling(self):
        engine = AdventureEngine()

        # Stationary / < 2.5 km/h
        dps_idle, _ = engine.calculate_dps(1.5)
        self.assertEqual(dps_idle, 0.0)

        # Walking (4.0 km/h)
        dps_walk, crit_walk = engine.calculate_dps(4.0)
        self.assertTrue(15.0 <= dps_walk <= 25.0)
        self.assertFalse(crit_walk)

        # Jogging (7.0 km/h)
        dps_jog, _ = engine.calculate_dps(7.0)
        self.assertGreaterEqual(dps_jog, 40.0)

        # Sprinting (10.0 km/h)
        dps_sprint, _ = engine.calculate_dps(10.0)
        self.assertGreaterEqual(dps_sprint, 80.0)

    def test_cluster_lowest_hp_targeting(self):
        engine = AdventureEngine(target_mode=TargetMode.LOWEST_HP)
        cluster = engine.generate_cluster(distance_m=0.0, force_boss=True)

        target_creature = cluster.creatures[0]
        target_creature.current_hp = 5.0

        selected = cluster.select_target(mode=TargetMode.LOWEST_HP)
        self.assertIsNotNone(selected)
        self.assertEqual(selected.current_hp, 5.0)

    def test_multi_hit_cleave(self):
        engine = AdventureEngine()
        cluster = engine.generate_cluster(distance_m=0.0, force_boss=False)
        engine.active_cluster = cluster

        events = engine.update_tick(
            delta_seconds=1.0,
            speed_kmh=7.0,
            distance_increment_m=2.0,
            has_multi_hit=True,
        )

        damage_events = [
            e for e in events if e.event_type == EventType.DAMAGE_DEALT
        ]
        multi_hit_events = [
            e for e in events if e.event_type == EventType.MULTI_HIT
        ]

        self.assertEqual(len(damage_events), 1)
        self.assertGreaterEqual(len(multi_hit_events), 1)

    def test_milestone_surge_clears_mobs(self):
        engine = AdventureEngine()
        cluster = engine.generate_cluster(distance_m=950.0, force_boss=False)
        engine.active_cluster = cluster

        engine.total_distance_m = 990.0
        events = engine.update_tick(
            delta_seconds=1.0,
            speed_kmh=6.0,
            distance_increment_m=20.0,
            has_multi_hit=True,
        )

        milestone_events = [
            e for e in events if e.event_type == EventType.MILESTONE_SURGE
        ]
        self.assertEqual(len(milestone_events), 1)
        self.assertIn(1000, engine.cleared_milestones)

    def test_defeat_rewards_accumulation(self):
        engine = AdventureEngine()
        slime = Creature(
            id="test_slime",
            name="Test Slime",
            tier=CreatureTier.NORMAL,
            archetype="slime",
            max_hp=10.0,
            current_hp=10.0,
            xp_reward=20,
            coin_reward=10,
            cosmetic_fragment_chance=1.0,
        )
        events = []
        slime.take_damage(10.0)
        engine._handle_creature_defeat(slime, events)

        self.assertEqual(engine.creatures_defeated_count, 1)
        self.assertEqual(engine.total_xp_earned, 20)
        self.assertEqual(engine.total_coins_earned, 10)
        self.assertEqual(engine.cosmetic_fragments_count, 1)
        self.assertEqual(events[0].event_type, EventType.CREATURE_DEFEATED)

    def test_rapid_speed_shifts(self):
        """Edge case: rapid shifts between sprint, abrupt stop, walking, and jogging."""
        engine = AdventureEngine()
        cluster = engine.generate_cluster(distance_m=0.0, force_boss=False)
        engine.active_cluster = cluster
        for c in cluster.creatures:
            c.current_hp = 250.0
            c.max_hp = 250.0

        # 1. High speed sprint (12 km/h) -> high DPS & damage dealt
        sprint_events = engine.update_tick(
            delta_seconds=1.0,
            speed_kmh=12.0,
            distance_increment_m=3.3,
        )
        sprint_dmg = [e for e in sprint_events if e.event_type == EventType.DAMAGE_DEALT]
        self.assertEqual(len(sprint_dmg), 1)
        self.assertGreater(sprint_dmg[0].damage, 70.0)

        # 2. Sudden stop (< 2.5 km/h, e.g. red light or pause) -> 0 DPS, no damage events
        stop_events = engine.update_tick(
            delta_seconds=1.0,
            speed_kmh=1.2,
            distance_increment_m=0.0,
        )
        stop_dmg = [e for e in stop_events if e.event_type in (EventType.DAMAGE_DEALT, EventType.MULTI_HIT)]
        self.assertEqual(len(stop_dmg), 0)

        # 3. Resume at light walk (3.5 km/h) -> modest DPS
        walk_events = engine.update_tick(
            delta_seconds=1.0,
            speed_kmh=3.5,
            distance_increment_m=1.0,
        )
        walk_dmg = [e for e in walk_events if e.event_type == EventType.DAMAGE_DEALT]
        self.assertEqual(len(walk_dmg), 1)
        self.assertLess(walk_dmg[0].damage, 30.0)

    def test_full_cluster_clear_and_respawn(self):
        """Edge case: ticking combat until an entire cluster is eliminated."""
        engine = AdventureEngine()
        cluster = engine.generate_cluster(distance_m=0.0, force_boss=False)
        engine.active_cluster = cluster

        # Set all creatures to 1 HP
        for c in cluster.creatures:
            c.current_hp = 1.0

        # Execute a strong tick that kills primary and splashes others
        cleared = False
        for _ in range(5):
            events = engine.update_tick(
                delta_seconds=1.0,
                speed_kmh=9.0,
                distance_increment_m=2.5,
                has_multi_hit=True,
            )
            if any(e.event_type == EventType.CLUSTER_CLEARED for e in events):
                cleared = True
                break

        self.assertTrue(cleared)
        self.assertTrue(engine.active_cluster.is_cleared)
        self.assertFalse(engine.active_cluster.has_alive)

        # Advance distance past next_spawn_distance_m to trigger fresh encounter
        engine.total_distance_m = engine.next_spawn_distance_m + 10.0
        respawn_events = engine.update_tick(
            delta_seconds=1.0,
            speed_kmh=6.0,
            distance_increment_m=10.0,
        )
        spawn_events = [e for e in respawn_events if e.event_type == EventType.SPAWN_CLUSTER]
        self.assertEqual(len(spawn_events), 1)
        self.assertTrue(engine.active_cluster.has_alive)

    def test_manual_and_strongest_target_mode(self):
        """Edge case: testing manual override and strongest enemy targeting."""
        engine = AdventureEngine(target_mode=TargetMode.STRONGEST)
        cluster = engine.generate_cluster(distance_m=0.0, force_boss=True)

        # Strongest mode should target Boss even if mob has lower HP
        selected = cluster.select_target(mode=TargetMode.STRONGEST)
        self.assertIsNotNone(selected)
        self.assertEqual(selected.tier, CreatureTier.BOSS)

        # Manual selection override
        normal_mob = next(c for c in cluster.creatures if c.tier == CreatureTier.NORMAL)
        manual_selected = cluster.select_target(mode=TargetMode.MANUAL, manual_id=normal_mob.id)
        self.assertEqual(manual_selected.id, normal_mob.id)

    def test_all_11_creature_definitions_and_fragment_chances(self):
        """Verify all 11 creature sprites and cosmetic fragment drop chances."""
        expected_sprites = {
            "Goblin Scout.png",
            "Goblin Soldier.png",
            "Goblin General.png",
            "Slime.png",
            "BigSlime.png",
            "KingSlime.png",
            "Bat.png",
            "BatKing.png",
            "Boar.png",
            "WildBoar.png",
            "HugeBoar.png",
        }
        self.assertEqual(len(CREATURES), 11)
        self.assertEqual({c.sprite for c in CREATURES.values()}, expected_sprites)
        self.assertEqual(FRAGMENT_CHANCE[CreatureTier.NORMAL], 0.05)
        self.assertEqual(FRAGMENT_CHANCE[CreatureTier.LEADER], 0.25)
        self.assertEqual(FRAGMENT_CHANCE[CreatureTier.BOSS], 0.80)

        # Verify trinket coin drop ranges: 1..5 for Normal/Leader, <= 10 (around 8..10) for Boss
        for c in CREATURES.values():
            lo, hi = c.coins
            self.assertLessEqual(lo, hi)
            if c.tier in (CreatureTier.NORMAL, CreatureTier.LEADER):
                self.assertGreaterEqual(lo, 1)
                self.assertLessEqual(hi, 5)
            else:
                self.assertGreaterEqual(lo, 8)
                self.assertLessEqual(hi, 10)

    def test_adventure_coin_cap_is_separate_from_daily_quest_coin_cap(self):
        """Creature trinket coins have their own daily cap and do not consume DAILY_COIN_CAP."""
        g = Game()
        today = date(2026, 11, 5)

        # Max out the main quest/bill daily coin cap
        g._award(xp=0, coins=DAILY_COIN_CAP, path_id="warrior", today=today)
        self.assertEqual(g.profile.coins, DAILY_COIN_CAP)
        self.assertEqual(g.profile.coins_today, DAILY_COIN_CAP)

        # Defeating creatures still grants trinket coins up to ADVENTURE_DAILY_COIN_CAP
        granted_1 = g.award_adventure_coins(10, today)
        self.assertEqual(granted_1, 10)
        self.assertEqual(g.profile.coins, DAILY_COIN_CAP + 10)
        self.assertEqual(g.adventure_coins_remaining(today), ADVENTURE_DAILY_COIN_CAP - 10)

        # Exceeding ADVENTURE_DAILY_COIN_CAP clamps to remaining adventure cap
        granted_2 = g.award_adventure_coins(50, today)
        self.assertEqual(granted_2, ADVENTURE_DAILY_COIN_CAP - 10)
        self.assertEqual(g.adventure_coins_remaining(today), 0)
        self.assertEqual(g.profile.coins, DAILY_COIN_CAP + ADVENTURE_DAILY_COIN_CAP)


if __name__ == "__main__":
    unittest.main()
