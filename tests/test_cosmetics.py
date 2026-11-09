"""Unit tests for Personalization Shop, Hero Titles, and Cosmetics."""


from lol.core import cosmetics as cos
from lol.core.game import Game
from lol.core.models import RunEntry


def test_companion_renames():
    slime = cos.get_cosmetic("pet_slime")
    assert slime.name == "Slime"

    kitsune = cos.get_cosmetic("pet_kitsune")
    assert kitsune.name == "Kitsune"

    shiba = cos.get_cosmetic("pet_shiba")
    assert shiba.name == "Shiba"

    neko = cos.get_cosmetic("pet_cat")
    assert neko.name == "Neko"

    dragon = cos.get_cosmetic("pet_dragon")
    assert dragon.name == "Dragonling"


def test_background_vfx_modes():
    fireflies = cos.get_cosmetic("particles_fireflies")
    assert fireflies.name == "Fireflies"
    assert fireflies.particle_mode == "fireflies"

    hearts = cos.get_cosmetic("particles_embers")
    assert hearts.name == "Hearts"
    assert hearts.particle_mode == "hearts"

    snow = cos.get_cosmetic("particles_snow")
    assert snow.name == "Snowfall"
    assert snow.particle_mode == "snow"

    cyber = cos.get_cosmetic("particles_cyber")
    assert cyber.name == "Cyber Rain"
    assert cyber.particle_mode == "cyber"

    cosmic = cos.get_cosmetic("particles_stardust")
    assert cosmic.name == "Cosmic"
    assert cosmic.particle_mode == "cosmic"


def test_theme_particle_mode_mapping():
    assert cos.theme_default_particle_mode("sakura") == "sakura"
    assert cos.theme_default_particle_mode("forest") == "fireflies"
    assert cos.theme_default_particle_mode("ember") == "hearts"
    assert cos.theme_default_particle_mode("cyber") == "cyber"
    assert cos.theme_default_particle_mode("royal") == "cosmic"
    assert cos.theme_default_particle_mode("ocean") == "motes"


def test_title_achievement_unlocks():
    g = Game()
    # Beta tester and No Title are always unlocked
    assert cos.is_title_unlocked(g, "title_none") is True
    assert cos.is_title_unlocked(g, "title_beta") is True

    # Dawn runner locked before 5-6 AM run
    assert cos.is_title_unlocked(g, "title_dawn") is False
    g.data.runs.append(RunEntry(id="r1", day="2026-11-09", started="05:30", distance_m=3000))
    assert cos.is_title_unlocked(g, "title_dawn") is True

    # Dusk runner
    assert cos.is_title_unlocked(g, "title_dusk") is False
    g.data.runs.append(RunEntry(id="r2", day="2026-11-09", started="17:45", distance_m=3000))
    assert cos.is_title_unlocked(g, "title_dusk") is True


def test_multi_title_equipping():
    g = Game()
    # Unlock dawn, dusk, beta
    g.profile.owned_cosmetics.extend(["title_dawn", "title_dusk", "title_beta", "title_monk"])

    # Equip first title
    assert g.equip_cosmetic("title_dawn") is True
    assert g.profile.equipped_titles == ["title_dawn"]
    assert g.is_title_equipped("title_dawn") is True

    # Equip second title
    assert g.equip_cosmetic("title_dusk") is True
    assert g.profile.equipped_titles == ["title_dawn", "title_dusk"]

    # Equip third title
    assert g.equip_cosmetic("title_beta") is True
    assert g.profile.equipped_titles == ["title_dawn", "title_dusk", "title_beta"]

    # Equip fourth title (should pop oldest and keep max 3)
    assert g.equip_cosmetic("title_monk") is True
    assert len(g.profile.equipped_titles) == 3
    assert g.profile.equipped_titles == ["title_dusk", "title_beta", "title_monk"]
    assert not g.is_title_equipped("title_dawn")

    # Toggle off / unequip a title
    assert g.equip_cosmetic("title_beta") is True
    assert g.profile.equipped_titles == ["title_dusk", "title_monk"]
    assert not g.is_title_equipped("title_beta")

    # Equipping title_none clears all equipped titles
    assert g.equip_cosmetic("title_none") is True
    assert g.profile.equipped_titles == []
    assert g.profile.title_id == "title_none"
    assert g.is_title_equipped("title_none") is True


def test_achievements_screen_render():
    from unittest.mock import MagicMock

    from lol.ui.screens.achievements import AchievementsScreen

    app = MagicMock()
    app.game = Game()
    screen = AchievementsScreen(app)
    screen.render()
    assert len(screen.list.controls) > 2


def test_particle_variants_and_ambient():
    from lol.ui.ambient import MindSpace

    modes = ["sakura", "fireflies", "hearts", "snow", "cyber", "cosmic"]
    for m in modes:
        vars_ = cos.particle_asset_variants(m)
        assert len(vars_) == 4, f"Expected 4 sprite variants for {m}, got {vars_}"
        for v in vars_:
            assert v.endswith(".png")

    # Test MindSpace initialization & particle modes
    ms = MindSpace(motes=10)
    for m in modes:
        ms.set_particle_style(m)
        assert ms._effective_particle_mode() == m
        # Test step logic for each particle mode
        for mote in ms._motes:
            mote.step(2.5, 375.0, 812.0)


def test_cyber_rain_premium():
    from datetime import date
    g = Game()
    g.profile.coins = 1000
    cyber = cos.get_cosmetic("particles_cyber")
    assert cyber.premium_only is True

    # Free user cannot buy premium-only cosmetic
    assert g.is_premium(date.today()) is False
    assert g.buy_cosmetic("particles_cyber", today=date.today()) is False
    assert "particles_cyber" not in g.profile.owned_cosmetics

    # Premium user can buy with coins
    g.unlock_dev()
    g.set_dev_premium(True)
    assert g.is_premium(date.today()) is True
    assert g.buy_cosmetic("particles_cyber", today=date.today()) is True
    assert "particles_cyber" in g.profile.owned_cosmetics


