"""Character customization catalog, layer ordering, validation, and randomization.

All initial assets in `src/assets/CharacterCustomization/` are free and unlocked by default.
Future cosmetic packs can be gated by coins or premium (`unlocked` list on AvatarCustomization).
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from lol.core.models import AvatarCustomization

if TYPE_CHECKING:
    from lol.core.game import Game

MAX_MAKEUPS = 3
AVATAR_BONUS_COINS = 200

BASE_BODIES: tuple[str, ...] = ("BaseBody",)
CLOTHES: tuple[str, ...] = (
    "Clothes1",
    "Clothes2",
    "Clothes3",
    "Clothes4",
    "Clothes5",
    "Clothes6",
    "Clothes7",
    "Clothes8",
    "Clothe9",
    "Clothe10",
    "Clothe11",
    "Clothe12",
)
EYES: tuple[str, ...] = (
    "Eyes1",
    "Eyes2",
    "Eyes3",
    "Eyes4",
    "Eyes5",
    "Eyes6",
    "Eyes7",
    "Eyes8",
)
HAIRS: tuple[str, ...] = (
    "Hair1",
    "Hair2",
    "Hair3",
    "Hair4",
    "Hair5",
    "Hair6",
    "Hair7",
    "Hair8",
    "Hair9",
    "Hair10",
    "Hair11",
)
MAKEUPS: tuple[str, ...] = (
    "Makeup1",
    "Makeup2",
    "Makeup3",
    "Makeup4",
    "Makeup5",
    "Makeup6",
)
MOUTHS: tuple[str, ...] = (
    "Mouth1",
    "Mouth2",
    "Mouth3",
    "Mouth4",
    "Mouth5",
    "Mouth6",
)
NOSES: tuple[str, ...] = (
    "Nose1",
    "Nose2",
    "Nose3",
    "Nose4",
    "Nose5",
    "Nose6",
)

# Categories in editor tab order: (category_id, display_label, items_tuple, allow_none)
CATEGORIES: tuple[tuple[str, str, tuple[str, ...], bool], ...] = (
    ("base", "Base", BASE_BODIES, False),
    ("skin", "Skin Details", MAKEUPS, True),
    ("eyes", "Eyes", EYES, False),
    ("nose", "Nose", NOSES, False),
    ("mouth", "Mouth", MOUTHS, False),
    ("hair", "Hair", HAIRS, True),
    ("clothes", "Clothes", CLOTHES, False),
)

_FOLDER_FOR_ITEM: dict[str, str] = {
    **{x: "" for x in BASE_BODIES},
    **{x: "Clothes" for x in CLOTHES},
    **{x: "Eyes" for x in EYES},
    **{x: "Hair" for x in HAIRS},
    **{x: "Makeups" for x in MAKEUPS},
    **{x: "Mouth" for x in MOUTHS},
    **{x: "Nose" for x in NOSES},
}


def asset_path(item_id: str) -> str:
    """Return the Flet relative asset path for a given customization item ID."""
    if not item_id or item_id not in _FOLDER_FOR_ITEM:
        return ""
    folder = _FOLDER_FOR_ITEM[item_id]
    if not folder:
        return f"CharacterCustomization/{item_id}.png"
    return f"CharacterCustomization/{folder}/{item_id}.png"


def sanitize(custom: AvatarCustomization | None) -> AvatarCustomization:
    """Ensure all item IDs are valid and makeups has at most MAX_MAKEUPS unique items."""
    if custom is None:
        return AvatarCustomization()
    body = custom.body if custom.body in BASE_BODIES else BASE_BODIES[0]
    clothes = custom.clothes if custom.clothes in CLOTHES else CLOTHES[0]
    eyes = custom.eyes if custom.eyes in EYES else EYES[0]
    hair = custom.hair if (custom.hair == "" or custom.hair in HAIRS) else HAIRS[0]
    mouth = custom.mouth if custom.mouth in MOUTHS else MOUTHS[0]
    nose = custom.nose if custom.nose in NOSES else NOSES[0]

    clean_makeups: list[str] = []
    for m in custom.makeups or []:
        if m in MAKEUPS and m not in clean_makeups and len(clean_makeups) < MAX_MAKEUPS:
            clean_makeups.append(m)

    clean_unlocked = [str(u) for u in (custom.unlocked or []) if u]
    return AvatarCustomization(
        body=body,
        clothes=clothes,
        eyes=eyes,
        hair=hair,
        mouth=mouth,
        nose=nose,
        makeups=clean_makeups,
        unlocked=clean_unlocked,
    )


def layer_paths(custom: AvatarCustomization | None) -> list[str]:
    """Return ordered list of relative PNG asset paths from back to front."""
    c = sanitize(custom)
    ordered_ids: list[str] = [c.body, c.nose, c.mouth, c.eyes, *c.makeups, c.clothes]
    if c.hair:
        ordered_ids.append(c.hair)
    return [p for item_id in ordered_ids if (p := asset_path(item_id))]


def toggle_makeup(makeups: list[str], item_id: str | None) -> tuple[list[str], bool]:
    """Toggle a makeup item in the stack (up to MAX_MAKEUPS=3).

    - Passing "" or None clears all makeups and returns ([], True).
    - Passing an already-equipped item removes it and returns (updated, True).
    - Passing a new item when < 3 equipped adds it and returns (updated, True).
    - Passing a new item when already at 3 returns (unchanged, False).
    """
    current = [m for m in makeups if m in MAKEUPS][:MAX_MAKEUPS]
    if not item_id:
        return [], True
    if item_id not in MAKEUPS:
        return current, False
    if item_id in current:
        current.remove(item_id)
        return current, True
    if len(current) >= MAX_MAKEUPS:
        return current, False
    current.append(item_id)
    return current, True


def randomize_avatar(seed: int | None = None) -> AvatarCustomization:
    """Generate a random valid AvatarCustomization."""
    rng = random.Random(seed)
    num_makeups = rng.choices([0, 1, 2, 3], weights=[30, 40, 20, 10], k=1)[0]
    chosen_makeups = rng.sample(MAKEUPS, k=num_makeups)
    return AvatarCustomization(
        body=rng.choice(BASE_BODIES),
        clothes=rng.choice(CLOTHES),
        eyes=rng.choice(EYES),
        hair=rng.choice(HAIRS),
        mouth=rng.choice(MOUTHS),
        nose=rng.choice(NOSES),
        makeups=chosen_makeups,
    )


def claim_avatar_bonus(game: Game) -> int:
    """Mark avatar as configured and grant the one-time +200 coin bonus if unclaimed."""
    p = game.profile
    p.avatar_configured = True
    if not p.avatar_bonus_claimed:
        p.coins += AVATAR_BONUS_COINS
        p.avatar_bonus_claimed = True
        game.save()
        return AVATAR_BONUS_COINS
    game.save()
    return 0

