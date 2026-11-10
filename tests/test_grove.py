import random
from datetime import UTC, date, datetime, timedelta

from lol.core.game import Game
from lol.core.grove import (
    FUSION_RECIPES,
    SEEDS,
    GroveState,
    ensure_grove_plots,
    feed_luma,
    fuse_seeds,
    get_seed,
    harvest_crop,
    luma_barter_multiplier,
    plant_crop,
    plot_progress,
    plot_remaining_s,
    sell_crop,
    sell_crop_value,
    sync_fitness_to_grove,
)
from lol.core.models import RunEntry, SleepEntry, WaterEntry, WorkoutSession


def test_seed_catalog():
    assert len(SEEDS) == 26
    aqua = get_seed("seed_aqua")
    assert aqua is not None
    assert aqua.tier == 1
    assert aqua.coin_yield == 12
    assert aqua.emoji == "💧"

    ygg = get_seed("seed_yggdrasil")
    assert ygg is not None
    assert ygg.tier == 4
    assert ygg.coin_yield == 280

    obsidian = get_seed("seed_obsidian")
    assert obsidian is not None
    assert obsidian.tier == 3
    assert obsidian.coin_yield == 115


def test_planting_and_growth_calc():
    grove = GroveState()
    grove.seeds["seed_aqua"] = 2

    now = datetime(2026, 11, 10, 10, 0, 0, tzinfo=UTC)
    ok = plant_crop(grove, 0, "seed_aqua", now=now)
    assert ok is True
    assert grove.seeds["seed_aqua"] == 1
    assert grove.plots[0].seed_id == "seed_aqua"
    assert not grove.plots[0].is_empty()

    # Double plant on same plot should fail
    fail = plant_crop(grove, 0, "seed_aqua", now=now)
    assert fail is False

    # Immediate progress is 0.0
    assert plot_progress(grove.plots[0], now=now) == 0.0
    assert plot_remaining_s(grove.plots[0], now=now) == 1800.0

    # 15 mins later (900s / 1800s = 0.5)
    later_15m = now + timedelta(seconds=900)
    assert abs(plot_progress(grove.plots[0], now=later_15m) - 0.5) < 0.01
    assert plot_remaining_s(grove.plots[0], now=later_15m) == 900.0

    # Boost by 900s
    grove.plots[0].boost_s = 900.0
    assert plot_progress(grove.plots[0], now=later_15m) == 1.0
    assert plot_remaining_s(grove.plots[0], now=later_15m) == 0.0


def test_harvest_crop():
    grove = GroveState()
    grove.seeds["seed_solar"] = 1
    now = datetime(2026, 11, 10, 10, 0, 0, tzinfo=UTC)
    plant_crop(grove, 1, "seed_solar", now=now)

    # Not ready yet
    coins, bonus = harvest_crop(grove, 1)
    assert coins == 0
    assert bonus == []

    # Mark ready
    grove.plots[1].harvest_ready = True
    rng = random.Random(42)  # deterministic
    coins, bonus = harvest_crop(grove, 1, rng=rng)
    # Harvesting awards 0 direct coins; crops go to Silo for player choice (Sell vs Feed)
    assert coins == 0
    assert len(bonus) >= 1
    assert grove.plots[1].is_empty()
    assert grove.harvested["seed_solar"] == 1
    assert grove.total_harvests == 1


def test_sell_crop_and_barter_rates():
    grove = GroveState()
    grove.harvested["seed_aqua"] = 5
    grove.luma_level = 1

    # Base price at Lv 1 (1.0x): 12 coins
    assert sell_crop_value("seed_aqua", grove.luma_level) == 12
    coins_earned = sell_crop(grove, "seed_aqua", 2)
    assert coins_earned == 24
    assert grove.harvested["seed_aqua"] == 3

    # Upgrade LUMA to Level 10 (1.50x barter rate)
    grove.luma_level = 10
    assert luma_barter_multiplier(10) == 1.50
    # 12 * 1.50 = 18 coins per crop
    assert sell_crop_value("seed_aqua", 10) == 18
    coins_earned_lv10 = sell_crop(grove, "seed_aqua", 3)
    assert coins_earned_lv10 == 54
    assert "seed_aqua" not in grove.harvested


def test_feed_luma_progression_and_plot_unlocks():
    grove = GroveState()
    grove.harvested["seed_aqua"] = 10  # Tier 1: 20 XP each
    assert grove.luma_level == 1
    assert grove.luma_xp == 0
    assert len(grove.plots) == 6

    # Feed 1 crop -> 20 XP
    xp, leveled = feed_luma(grove, "seed_aqua", is_premium=False)
    assert xp == 20
    assert leveled is False
    assert grove.luma_xp == 20
    assert grove.harvested["seed_aqua"] == 9

    # Feed with premium: +50% XP = 30 XP
    xp_prem, _ = feed_luma(grove, "seed_aqua", is_premium=True)
    assert xp_prem == 30
    assert grove.luma_xp == 50

    # Level 1 requires 100 XP to level up. Add a Tier 2 crop (60 XP)
    grove.harvested["seed_mist"] = 1
    xp, leveled = feed_luma(grove, "seed_mist")
    assert xp == 60
    assert leveled is True
    assert grove.luma_level == 2
    assert grove.luma_xp == 10  # 50 + 60 = 110, 110 - 100 = 10

    # Fast forward to Level 5 -> Unlocks Plot #7
    grove.luma_level = 5
    ensure_grove_plots(grove)
    assert len(grove.plots) == 7

    # Fast forward to Level 10 -> Unlocks Plot #8
    grove.luma_level = 10
    ensure_grove_plots(grove)
    assert len(grove.plots) == 8


def test_altar_fusion_and_infusions():
    grove = GroveState()
    grove.seeds["seed_aqua"] = 2
    grove.seeds["seed_solar"] = 1

    # Fuse Aqua + Solar -> Mist (Vapor Orchid)
    res, _is_mut = fuse_seeds(grove, "seed_aqua", "seed_solar", rng=random.Random(1))
    assert res == "seed_mist"
    assert grove.seeds["seed_aqua"] == 1
    assert "seed_solar" not in grove.seeds
    assert grove.seeds["seed_mist"] == 1
    assert "seed_mist" in grove.discovered_fusions

    # Test Tier 3 + Tier 1 Cross-Infusion: Volcanic Bloom + Aqua Spore -> Obsidian Lily
    grove.seeds["seed_volcanic"] = 1
    grove.seeds["seed_aqua"] = 1
    inf_res, _ = fuse_seeds(grove, "seed_volcanic", "seed_aqua", rng=random.Random(1))
    assert inf_res == "seed_obsidian"
    assert grove.seeds["seed_obsidian"] == 1

    # Test all predefined recipe keys exist
    for pair, output in FUSION_RECIPES.items():
        assert len(pair) == 2
        for s in pair:
            assert s in SEEDS
        assert output in SEEDS


def test_sync_fitness_to_grove():
    g = Game()
    today_iso = date.today().isoformat()

    # 1. Log 1600 mL water
    g.data.water.append(WaterEntry(id="w1", day=today_iso, time="09:00", amount_ml=1600))
    # 2. Log 2500 m run
    g.data.runs.append(RunEntry(id="r1", day=today_iso, started="10:00", distance_m=2500.0))
    # 3. Log a workout
    g.data.workouts.append(WorkoutSession(id="wo1", day=today_iso, started="11:00"))
    # 4. Log sleep
    g.data.sleep.append(SleepEntry(id="s1", night_of=today_iso, bedtime="23:00", wake="07:00", logged_on=today_iso))

    res = sync_fitness_to_grove(g)
    grove: GroveState = g.data.grove

    assert "seed_aqua" in res["awarded_seeds"]
    assert "seed_solar" in res["awarded_seeds"]
    assert "seed_terra" in res["awarded_seeds"]
    assert "seed_spirit" in res["awarded_seeds"]

    # Starter 2 aqua + 1 habit = 3
    assert grove.seeds["seed_aqua"] == 3
    assert grove.seeds["seed_solar"] == 3
    assert grove.seeds["seed_terra"] == 2
    assert grove.seeds["seed_spirit"] == 2

    # Sunlight boost for 2500m (25 * 60 = 1500s)
    assert res["sunlight_boost_s"] == 1500.0
