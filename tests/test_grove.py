import random
from datetime import UTC, date, datetime, timedelta

from lol.core.game import Game
from lol.core.grove import (
    FUSION_RECIPES,
    SEEDS,
    CropPlot,
    GroveState,
    fuse_seeds,
    get_seed,
    harvest_crop,
    plant_crop,
    plot_progress,
    plot_remaining_s,
    sync_fitness_to_grove,
)
from lol.core.models import RunEntry, SleepEntry, WaterEntry, WorkoutSession


def test_seed_catalog():
    assert len(SEEDS) == 16
    aqua = get_seed("seed_aqua")
    assert aqua is not None
    assert aqua.tier == 1
    assert aqua.coin_yield == 60
    assert aqua.emoji == "💧"

    ygg = get_seed("seed_yggdrasil")
    assert ygg is not None
    assert ygg.tier == 4
    assert ygg.coin_yield == 2200


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
    assert coins == 65
    assert len(bonus) >= 1
    assert grove.plots[1].is_empty()
    assert grove.harvested["seed_solar"] == 1
    assert grove.total_harvests == 1


def test_altar_fusion():
    grove = GroveState()
    grove.seeds["seed_aqua"] = 2
    grove.seeds["seed_solar"] = 1

    # Fuse Aqua + Solar -> Mist (Vapor Orchid)
    res, is_mut = fuse_seeds(grove, "seed_aqua", "seed_solar", rng=random.Random(1))
    assert res == "seed_mist"
    assert grove.seeds["seed_aqua"] == 1
    assert "seed_solar" not in grove.seeds
    assert grove.seeds["seed_mist"] == 1
    assert "seed_mist" in grove.discovered_fusions

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

    # Plant a crop to receive sunlight & water
    g.data.grove = GroveState()
    g.data.grove.seeds.clear()
    g.data.grove.seeds["seed_terra"] = 1
    now = datetime.now(UTC)
    plant_crop(g.data.grove, 0, "seed_terra", now=now)

    sync_result = sync_fitness_to_grove(g, now=now)
    grove = g.data.grove

    assert "seed_aqua" in sync_result["awarded_seeds"]
    assert "seed_solar" in sync_result["awarded_seeds"]
    assert "seed_terra" in sync_result["awarded_seeds"]
    assert "seed_spirit" in sync_result["awarded_seeds"]

    # Seeds awarded in inventory
    assert grove.seeds.get("seed_aqua") == 1
    assert grove.seeds.get("seed_solar") == 1
    assert grove.seeds.get("seed_terra") == 1  # 1 was planted, 1 newly awarded
    assert grove.seeds.get("seed_spirit") == 1

    # Sunlight boost calculated: 2500m -> 25 * 60 = 1500s boost
    assert sync_result["sunlight_boost_s"] == 1500.0
    assert grove.plots[0].boost_s == 1500.0


def test_grove_storage_save_load(tmp_path):
    g = Game()
    g.data.grove = GroveState()
    g.data.grove.seeds["seed_celestial"] = 3
    g.data.grove.harvested["seed_aqua"] = 5
    g.data.grove.total_harvests = 5
    g.data.grove.discovered_fusions = ["seed_mist", "seed_celestial"]
    g.data.grove.plots[0] = CropPlot(
        plot_id=0,
        seed_id="seed_celestial",
        planted_at="2026-11-10T10:00:00+00:00",
        watered_at="2026-11-10T10:00:00+00:00",
        boost_s=360.0,
        harvest_ready=False,
    )

    path = g.save(tmp_path / "save.json")
    loaded = Game.load(path)

    assert loaded.data.grove is not None
    loaded_grove: GroveState = loaded.data.grove
    assert loaded_grove.seeds["seed_celestial"] == 3
    assert loaded_grove.harvested["seed_aqua"] == 5
    assert loaded_grove.total_harvests == 5
    assert loaded_grove.discovered_fusions == ["seed_mist", "seed_celestial"]
    assert loaded_grove.plots[0].seed_id == "seed_celestial"
    assert loaded_grove.plots[0].boost_s == 360.0
