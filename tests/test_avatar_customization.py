"""Tests for Character Creation & Customization core catalog, 3-slot makeup stacking,
randomizer, +200 coin bonus claim, and save/load persistence."""

from pathlib import Path

from lol.core import avatar_catalog
from lol.core.game import Game
from lol.core.models import AvatarCustomization
from lol.ui import avatars

ASSETS_DIR = Path(__file__).resolve().parent.parent / "src" / "assets"


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
    assert isinstance(b.content, avatars.AvatarView)
    new_custom = AvatarCustomization(hair="", clothes="Clothes2", makeups=["Makeup2", "Makeup4"])
    avatars.restyle_bubble(b, "a3", custom=new_custom)
    assert b.content.custom == new_custom

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


