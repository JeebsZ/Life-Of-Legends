"""Tests for Character Creation & Customization core catalog, 3-slot makeup stacking,
randomizer, +200 coin bonus claim, and save/load persistence."""

from pathlib import Path

import flet as ft
import pytest

from lol.core import avatar_catalog, update_checker
from lol.core import cosmetics as cos
from lol.core.game import Game
from lol.core.models import AvatarCustomization
from lol.ui import ambient, avatars
from lol.ui import components as ui
from lol.ui import theme as th

ASSETS_DIR = Path(__file__).resolve().parent.parent / "src" / "assets"


@pytest.fixture(autouse=True)
def _isolated_storage(tmp_path, monkeypatch):
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path))


def test_all_catalog_assets_exist_on_disk():
    """Every catalog item ID resolves to an existing 256x256 PNG under src/assets/."""
    all_ids = (
        *avatar_catalog.BASE_BODIES,
        *avatar_catalog.CLOTHES,
        *avatar_catalog.EYES,
        *avatar_catalog.HAIRS,
        *avatar_catalog.MAKEUPS,
        *avatar_catalog.MOUTHS,
        *avatar_catalog.NOSES,
    )
    for item_id in all_ids:
        rel = avatar_catalog.asset_path(item_id)
        assert rel.startswith("CharacterCustomization/"), item_id
        full = ASSETS_DIR / rel
        assert full.is_file(), f"Missing asset file: {full}"


def test_layer_paths_order_and_hair_toggle():
    custom = AvatarCustomization(
        body="BaseBody",
        nose="Nose2",
        mouth="Mouth3",
        eyes="Eyes4",
        makeups=["Makeup1", "Makeup4"],
        clothes="Clothes5",
        hair="Hair7",
    )
    paths = avatar_catalog.layer_paths(custom)
    assert paths == [
        "CharacterCustomization/BaseBody.png",
        "CharacterCustomization/Nose/Nose2.png",
        "CharacterCustomization/Mouth/Mouth3.png",
        "CharacterCustomization/Eyes/Eyes4.png",
        "CharacterCustomization/Makeups/Makeup1.png",
        "CharacterCustomization/Makeups/Makeup4.png",
        "CharacterCustomization/Clothes/Clothes5.png",
        "CharacterCustomization/Hair/Hair7.png",
    ]

    # Bald / no hair option ("")
    bald = AvatarCustomization(hair="")
    bald_paths = avatar_catalog.layer_paths(bald)
    assert all("Hair" not in p for p in bald_paths)


def test_makeup_stacking_up_to_three():
    stack: list[str] = []
    # Add 1st
    stack, ok = avatar_catalog.toggle_makeup(stack, "Makeup1")
    assert ok and stack == ["Makeup1"]
    # Add 2nd
    stack, ok = avatar_catalog.toggle_makeup(stack, "Makeup3")
    assert ok and stack == ["Makeup1", "Makeup3"]
    # Add 3rd
    stack, ok = avatar_catalog.toggle_makeup(stack, "Makeup5")
    assert ok and stack == ["Makeup1", "Makeup3", "Makeup5"]
    # 4th is rejected (limit 3)
    stack, ok = avatar_catalog.toggle_makeup(stack, "Makeup2")
    assert not ok and stack == ["Makeup1", "Makeup3", "Makeup5"]
    # Toggling an active makeup removes it
    stack, ok = avatar_catalog.toggle_makeup(stack, "Makeup3")
    assert ok and stack == ["Makeup1", "Makeup5"]
    # Now adding another succeeds
    stack, ok = avatar_catalog.toggle_makeup(stack, "Makeup6")
    assert ok and stack == ["Makeup1", "Makeup5", "Makeup6"]
    # Clearing with "" empties the stack
    stack, ok = avatar_catalog.toggle_makeup(stack, "")
    assert ok and stack == []


def test_randomize_avatar_produces_valid_config():
    for seed in range(25):
        c = avatar_catalog.randomize_avatar(seed=seed)
        assert c.body in avatar_catalog.BASE_BODIES
        assert c.clothes in avatar_catalog.CLOTHES
        assert c.eyes in avatar_catalog.EYES
        assert c.hair in avatar_catalog.HAIRS
        assert c.mouth in avatar_catalog.MOUTHS
        assert c.nose in avatar_catalog.NOSES
        assert len(c.makeups) <= avatar_catalog.MAX_MAKEUPS
        assert len(set(c.makeups)) == len(c.makeups)
        for m in c.makeups:
            assert m in avatar_catalog.MAKEUPS


def test_claim_avatar_bonus_awards_200_coins_once(tmp_path):
    save_file = tmp_path / "save.json"
    g = Game()
    g.data.profile.coins = 50
    assert not g.profile.avatar_configured
    assert not g.profile.avatar_bonus_claimed

    awarded = g.claim_avatar_bonus()
    assert awarded == 200
    assert g.profile.coins == 250
    assert g.profile.avatar_configured is True
    assert g.profile.avatar_bonus_claimed is True

    # Second claim gives 0
    awarded_again = g.claim_avatar_bonus()
    assert awarded_again == 0
    assert g.profile.coins == 250

    # Round-trip save & load
    custom = AvatarCustomization(
        clothes="Clothe10",
        eyes="Eyes6",
        hair="Hair9",
        mouth="Mouth4",
        nose="Nose5",
        makeups=["Makeup2", "Makeup6"],
    )
    g.set_profile(avatar_customization=custom)
    g.save(save_file)

    loaded = Game.load(save_file)
    assert loaded.profile.avatar_configured is True
    assert loaded.profile.avatar_bonus_claimed is True
    assert loaded.profile.coins == 250
    assert loaded.profile.avatar_customization == custom


def test_sanitize_handles_invalid_or_excess_items():
    dirty = AvatarCustomization(
        body="InvalidBody",
        clothes="InvalidClothes",
        eyes="InvalidEyes",
        hair="InvalidHair",
        mouth="InvalidMouth",
        nose="InvalidNose",
        makeups=["Makeup1", "Makeup1", "BadMakeup", "Makeup2", "Makeup3", "Makeup4"],
    )
    clean = avatar_catalog.sanitize(dirty)
    assert clean.body == "BaseBody"
    assert clean.clothes == "Clothes1"
    assert clean.eyes == "Eyes1"
    assert clean.hair == "Hair1"
    assert clean.mouth == "Mouth1"
    assert clean.nose == "Nose1"
    assert clean.makeups == ["Makeup1", "Makeup2", "Makeup3"]


def test_avatar_view_and_character_customizer_ui():
    custom = AvatarCustomization(hair="Hair3", clothes="Clothes4", makeups=["Makeup1"])
    view = avatars.AvatarView(custom, size=64)
    assert len(view._stack.controls) == len(avatar_catalog.layer_paths(custom))

    b = avatars.bubble("a2", 48, custom=custom)
    assert isinstance(b.content, ft.Container)
    assert b.content.clip_behavior == ft.ClipBehavior.HARD_EDGE
    assert isinstance(b.content.content, avatars.AvatarView)
    new_custom = AvatarCustomization(hair="", clothes="Clothes2", makeups=["Makeup2", "Makeup4"])
    avatars.restyle_bubble(b, "a3", custom=new_custom)
    assert b.content.content.custom == new_custom

    changes: list[AvatarCustomization] = []
    limit_msgs: list[str] = []
    editor = avatars.CharacterCustomizer(
        custom=custom,
        hero_name="Hero",
        on_change=changes.append,
        on_limit_toast=limit_msgs.append,
    )
    editor._select_cat("skin")
    editor._select_item("skin", "Makeup2")
    editor._select_item("skin", "Makeup3")
    assert len(editor.custom.makeups) == 3
    # 4th makeup triggers limit toast
    editor._select_item("skin", "Makeup4")
    assert len(limit_msgs) == 1
    # Randomize updates custom and triggers on_change
    editor._on_randomize()
    assert len(changes) >= 3


def test_avatar_bubble_follows_theme_color():
    prev_id = th.current().id
    try:
        for tid, pal in th.THEMES.items():
            th._current[0] = tid
            b = avatars.bubble("a1", 40)
            assert pal.primary.lstrip("#").lower() in (b.bgcolor or "").lower()
    finally:
        th._current[0] = prev_id


def test_arcane_nav_bar_has_valid_height_and_no_positioned_crash():
    nav = ui.ArcaneNavBar(0)
    assert nav.height is not None and nav.height >= ui.NAV_H
    assert nav.content is not None
    assert getattr(nav.content, "top", None) is None
    assert getattr(nav.content, "bottom", None) is None


def test_store_update_checker_version_parsing_and_extraction():
    assert update_checker.is_newer_version("0.1.3", "0.1.4")
    assert update_checker.is_newer_version("0.1.3", "0.2.0")
    assert update_checker.is_newer_version("0.1.3", "1.0.0")
    assert not update_checker.is_newer_version("0.1.3", "0.1.3")
    assert not update_checker.is_newer_version("0.1.3", "0.1.2")

    html_sample = 'AF_initDataCallback({key: "ds:5", data: [[["0.1.5"]]]});'
    assert update_checker.extract_play_store_version(html_sample) == "0.1.5"
    json_sample = '{"latest_version": "0.2.1"}'
    assert update_checker.extract_play_store_version(json_sample) == "0.2.1"


def test_cosmetics_shop_buy_equip_and_persistence(tmp_path: Path):
    save_file = tmp_path / "save_cosmetics.json"
    g = Game.load(save_file)
    g.profile.coins = 5000

    for cat in ("particles", "frame", "pet", "fx_style"):
        items = cos.items_for_category(cat)
        assert len(items) >= 6
        paid = next(i for i in items if i.price > 0)
        assert not g.equip_cosmetic(paid.id)
        assert g.buy_cosmetic(paid.id)
        assert paid.id in g.profile.owned_cosmetics
        assert g.equip_cosmetic(paid.id)
        assert g.equipped_cosmetic_id(cat) == paid.id

    # Title category is achievement-unlocked
    title_items = cos.items_for_category("title")
    assert len(title_items) >= 6
    g.profile.owned_cosmetics.append("title_beta")
    assert g.equip_cosmetic("title_beta")
    assert "title_beta" in g.profile.equipped_titles

    g.save(save_file)
    g2 = Game.load(save_file)
    for cat in cos.CATEGORIES:
        assert g2.equipped_cosmetic_id(cat) == g.equipped_cosmetic_id(cat)


def test_mindspace_particle_modes_and_bubble_frames_pets():
    space = ambient.MindSpace()
    for p_item in cos.items_for_category("particles"):
        space.set_particle_style(p_item.id)
        for m in space._motes[:3]:
            m.step(2.5, 375.0, 812.0)
        assert len(space._motes) > 0

    b = avatars.bubble(
        "a1",
        52,
        custom=AvatarCustomization(),
        frame_id="frame_gold",
        pet_id="pet_slime",
    )
    assert isinstance(b.shadow, list)
    av_view = b.content.content
    assert isinstance(av_view, avatars.AvatarView)
    assert len(av_view._stack.controls) == len(avatar_catalog.layer_paths(av_view.custom)) + 1




