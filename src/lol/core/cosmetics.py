"""Coin-purchasable personalization cosmetics: Background Particles, Avatar Frames,
Hero Titles, Companion Pets, and XP Bar / GPS Trail Styles."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CosmeticItem:
    id: str
    category: str  # "particles" | "frame" | "title" | "pet" | "fx_style"
    name: str
    price: int
    desc: str
    color: str
    secondary_color: str = ""
    icon_name: str = "auto_awesome"
    badge_text: str = ""
    particle_mode: str = ""
    premium_only: bool = False

    @property
    def subtitle(self) -> str:
        return self.desc


CATEGORIES: dict[str, str] = {
    "particles": "Background FX",
    "frame": "Avatar Frames",
    "title": "Hero Titles",
    "pet": "Companions",
    "fx_style": "XP & Trail FX",
}

DEFAULT_BY_CATEGORY: dict[str, str] = {
    "particles": "particles_auto",
    "frame": "frame_default",
    "title": "title_none",
    "pet": "pet_none",
    "fx_style": "fx_default",
}

COSMETICS: tuple[CosmeticItem, ...] = (
    # --- 1. Background Particle Effects ---
    CosmeticItem(
        "particles_auto",
        "particles",
        "Theme Default FX",
        0,
        "Automatically matches your active theme's signature atmosphere",
        "#4FE3F0",
        "#A78BFA",
        icon_name="auto_awesome",
        particle_mode="auto",
    ),
    CosmeticItem(
        "particles_sakura",
        "particles",
        "Sakura Blossom Petals",
        300,
        "Softly falling cherry-blossom petals drifting across your mind-space",
        "#FFB7C5",
        "#FF6FB1",
        icon_name="local_florist",
        particle_mode="sakura",
    ),
    CosmeticItem(
        "particles_fireflies",
        "particles",
        "Fireflies",
        250,
        "Warm golden-green fireflies wandering and pulsing in the dark",
        "#9BD46A",
        "#FFD166",
        icon_name="flare",
        particle_mode="fireflies",
    ),
    CosmeticItem(
        "particles_embers",
        "particles",
        "Hearts",
        300,
        "Bubbly floating hearts drifting upward with warm affection",
        "#FF4D6D",
        "#FF8FA3",
        icon_name="favorite",
        particle_mode="hearts",
    ),
    CosmeticItem(
        "particles_snow",
        "particles",
        "Snowfall",
        250,
        "Gentle crystalline snowflakes drifting down with a soft winter sway",
        "#80FFDB",
        "#64DFDF",
        icon_name="ac_unit",
        particle_mode="snow",
    ),
    CosmeticItem(
        "particles_cyber",
        "particles",
        "Cyber Rain",
        350,
        "Vertical synthwave neon streaks gliding through the digital grid",
        "#00F5D4",
        "#FF2A85",
        icon_name="bolt",
        particle_mode="cyber",
        premium_only=True,
    ),
    CosmeticItem(
        "particles_stardust",
        "particles",
        "Cosmic",
        400,
        "Twinkling 4-point celestial diamond stars floating in deep space",
        "#C77DFF",
        "#FFD166",
        icon_name="stars",
        particle_mode="cosmic",
    ),
    # --- 2. Avatar Ring Frames & Auras ---
    CosmeticItem(
        "frame_default",
        "frame",
        "Theme Ring",
        0,
        "Clean circular ring that matches your active theme color",
        "#4FE3F0",
        icon_name="radio_button_unchecked",
    ),
    CosmeticItem(
        "frame_gold",
        "frame",
        "Solar Halo",
        250,
        "Radiant sunburst gold ring with a warm celestial double glow",
        "#FFD166",
        "#FF9F1C",
        icon_name="wb_sunny",
    ),
    CosmeticItem(
        "frame_sakura",
        "frame",
        "Sakura Garland",
        300,
        "Soft cherry-blossom pink ring with a dreamy petal halo",
        "#FFB7C5",
        "#FF6FB1",
        icon_name="filter_vintage",
    ),
    CosmeticItem(
        "frame_cyber",
        "frame",
        "Neon Glitch Ring",
        350,
        "High-voltage electric cyan and magenta synthwave aura",
        "#00F5D4",
        "#FF2A85",
        icon_name="Offline_bolt",
    ),
    CosmeticItem(
        "frame_emerald",
        "frame",
        "Elderwood Vine",
        250,
        "Lush forest emerald ring with a tranquil nature aura",
        "#5EEAB0",
        "#7CE395",
        icon_name="spa",
    ),
    CosmeticItem(
        "frame_crimson",
        "frame",
        "Bloodmoon Flame",
        400,
        "Fierce warrior ruby ring with a blazing crimson aura",
        "#FF4D6D",
        "#FFB703",
        icon_name="whatshot",
    ),
    CosmeticItem(
        "frame_void",
        "frame",
        "Abyssal Orbit",
        500,
        "Deep nebula violet ring with a starlight event-horizon glow",
        "#C77DFF",
        "#72EFDD",
        icon_name="blur_circular",
    ),
    # --- 3. Hero Titles ---
    CosmeticItem(
        "title_none",
        "title",
        "No Title",
        0,
        "Show only your hero name in the header and profile",
        "#8FA4C2",
        icon_name="remove_circle_outline",
        badge_text="",
    ),
    CosmeticItem(
        "title_dawn",
        "title",
        "Dawn Runner",
        0,
        "Unlocked: Complete a run or walk between 5:00 AM - 6:00 AM",
        "#4FE3F0",
        icon_name="directions_run",
        badge_text="Dawn Runner",
    ),
    CosmeticItem(
        "title_dusk",
        "title",
        "Dusk Runner",
        0,
        "Unlocked: Complete a run or walk between 5:00 PM - 6:00 PM",
        "#FF758F",
        icon_name="directions_run",
        badge_text="Dusk Runner",
    ),
    CosmeticItem(
        "title_alchemist",
        "title",
        "Cozy Alchemist",
        0,
        "Unlocked: Complete 7 days of meal & water hydration care",
        "#FFA071",
        icon_name="coffee",
        badge_text="Cozy Alchemist",
    ),
    CosmeticItem(
        "title_scholar",
        "title",
        "Night Owl Scholar",
        0,
        "Unlocked: Score 100% on a study quiz exam",
        "#B8A9FF",
        icon_name="menu_book",
        badge_text="Night Owl Scholar",
    ),
    CosmeticItem(
        "title_monk",
        "title",
        "Matcha Monk",
        0,
        "Unlocked: Reach a 10x consecutive self-care habit",
        "#7CE395",
        icon_name="self_improvement",
        badge_text="Matcha Monk",
    ),
    CosmeticItem(
        "title_vanguard",
        "title",
        "Iron Vanguard",
        0,
        "Unlocked: Complete 10 gym or strength workouts",
        "#FF4D6D",
        icon_name="fitness_center",
        badge_text="Iron Vanguard",
    ),
    CosmeticItem(
        "title_ranger",
        "title",
        "Shadow Ranger",
        0,
        "Unlocked: Clear 5 outdoor GPS adventure quests",
        "#5EEAB0",
        icon_name="forest",
        badge_text="Shadow Ranger",
    ),
    CosmeticItem(
        "title_ronin",
        "title",
        "Cyber Ronin",
        0,
        "Unlocked: Finish a 60-minute deep focus session",
        "#00F5D4",
        icon_name="bolt",
        badge_text="Cyber Ronin",
    ),
    CosmeticItem(
        "title_sovereign",
        "title",
        "Grand Sovereign",
        0,
        "Unlocked: Track ₱50,000+ across expense & savings vaults",
        "#FFD166",
        icon_name="workspace_premium",
        badge_text="Grand Sovereign",
    ),
    CosmeticItem(
        "title_sprinter",
        "title",
        "Streak Sprinter",
        0,
        "Unlocked: Maintain an unbroken 7-day adventure streak",
        "#FFD166",
        icon_name="bolt",
        badge_text="Streak Sprinter",
    ),
    CosmeticItem(
        "title_early",
        "title",
        "Early Bird",
        0,
        "Unlocked: Wake up and log in before 6:30 AM for 5 days",
        "#4FE3F0",
        icon_name="wb_twilight",
        badge_text="Early Bird",
    ),
    CosmeticItem(
        "title_beta",
        "title",
        "Beta Tester",
        0,
        "Pioneering adventurer of LUMA - dynamic prismatic badge",
        "#00F5D4",
        secondary_color="#FF2A85",
        icon_name="verified",
        badge_text="Beta Tester",
    ),
    # --- 4. Companion Pets ---
    CosmeticItem(
        "pet_none",
        "pet",
        "No Companion",
        0,
        "Travel solo without a companion badge",
        "#8FA4C2",
        icon_name="remove_circle_outline",
        badge_text="",
    ),
    CosmeticItem(
        "pet_slime",
        "pet",
        "Slime",
        400,
        "A friendly bouncing mana slime that cheers on your daily quests",
        "#4FE3F0",
        "#A78BFA",
        icon_name="water_drop",
        badge_text="💧",
    ),
    CosmeticItem(
        "pet_sprout",
        "pet",
        "Sprout Spirit",
        400,
        "A tiny leaf spirit that loves sunshine, walks, and hydration",
        "#7CE395",
        "#5EEAB0",
        icon_name="eco",
        badge_text="🌱",
    ),
    CosmeticItem(
        "pet_kitsune",
        "pet",
        "Kitsune",
        500,
        "A nine-tailed flame fox spirit that runs beside you on GPS quests",
        "#FFA53A",
        "#FF4D6D",
        icon_name="pets",
        badge_text="🦊",
    ),
    CosmeticItem(
        "pet_shiba",
        "pet",
        "Shiba",
        550,
        "Loyal adventure pup always ready for the next 1 km surge",
        "#FFD166",
        "#FFA071",
        icon_name="pets",
        badge_text="🐕",
    ),
    CosmeticItem(
        "pet_cat",
        "pet",
        "Neko",
        600,
        "A mysterious cosmic cat with starry eyes and quiet purrs",
        "#C77DFF",
        "#FFB7C5",
        icon_name="nights_stay",
        badge_text="🐈‍⬛",
    ),
    CosmeticItem(
        "pet_dragon",
        "pet",
        "Dragonling",
        800,
        "A mythic pocket dragon that guards your streak and coin hoard",
        "#FFD166",
        "#FF4D6D",
        icon_name="Auto_awesome",
        badge_text="🐉",
    ),
    # --- 5. XP Bar & GPS Trail FX ---
    CosmeticItem(
        "fx_default",
        "fx_style",
        "Theme Default",
        0,
        "Uses your active theme's primary color for the XP bar and GPS trail",
        "#4FE3F0",
        icon_name="linear_scale",
    ),
    CosmeticItem(
        "fx_gold",
        "fx_style",
        "Liquid Gold",
        250,
        "Gleaming golden XP bar and sunlit golden GPS run trail",
        "#FFD166",
        "#FF9F1C",
        icon_name="wb_sunny",
    ),
    CosmeticItem(
        "fx_sakura",
        "fx_style",
        "Sakura Blossom",
        250,
        "Rose-blossom pink XP bar and petal-tinted GPS run trail",
        "#FFB7C5",
        "#FF6FB1",
        icon_name="local_florist",
    ),
    CosmeticItem(
        "fx_cyber",
        "fx_style",
        "Synthwave Neon",
        300,
        "Electric neon magenta-cyan XP bar and laser GPS run trail",
        "#FF2A85",
        "#00F5D4",
        icon_name="bolt",
    ),
    CosmeticItem(
        "fx_emerald",
        "fx_style",
        "Emerald Surge",
        250,
        "Vibrant wind-runner emerald XP bar and forest GPS trail",
        "#5EEAB0",
        "#7CE395",
        icon_name="bolt",
    ),
    CosmeticItem(
        "fx_crimson",
        "fx_style",
        "Crimson Overdrive",
        350,
        "Blazing bloodmoon ruby XP bar and flame GPS run trail",
        "#FF4D6D",
        "#FFB703",
        icon_name="whatshot",
    ),
)

COSMETIC_BY_ID: dict[str, CosmeticItem] = {c.id: c for c in COSMETICS}
FREE_COSMETICS: tuple[str, ...] = tuple(DEFAULT_BY_CATEGORY.values())


def get_cosmetic(item_id: str | None, category: str | None = None) -> CosmeticItem:
    """Return a CosmeticItem by id, falling back to the category default."""
    if item_id and item_id in COSMETIC_BY_ID:
        item = COSMETIC_BY_ID[item_id]
        if category is None or item.category == category:
            return item
    default_id = DEFAULT_BY_CATEGORY.get(category or "particles", "particles_auto")
    return COSMETIC_BY_ID[default_id]


def items_for_category(category: str) -> list[CosmeticItem]:
    return [c for c in COSMETICS if c.category == category]


def theme_default_particle_mode(theme_id: str) -> str:
    """Signature particle effect for each theme when 'particles_auto' is selected."""
    mapping = {
        "sakura": "sakura",
        "rose": "sakura",
        "forest": "fireflies",
        "matcha": "fireflies",
        "ember": "hearts",
        "crimson": "hearts",
        "solar": "hearts",
        "aurora": "snow",
        "ocean": "motes",
        "cyber": "cyber",
        "abyss": "cosmic",
        "royal": "cosmic",
        "lavender": "cosmic",
        "arcane": "motes",
    }
    return mapping.get(theme_id, "motes")


KNOWN_PARTICLE_SPRITES: set[str] = {
    "sakura", "fireflies", "hearts", "snow", "cyber", "cosmic"
}


def particle_asset_variants(mode: str) -> list[str]:
    """Return list of asset paths for 4-quadrant sprite variants (particles/<mode>_<i>.png)."""
    if not mode or mode in ("auto", "motes"):
        return []
    mode_map = {
        "embers": "hearts",
        "stardust": "cosmic",
    }
    target_mode = mode_map.get(mode, mode)
    if target_mode in KNOWN_PARTICLE_SPRITES:
        return [f"particles/{target_mode}_{i}.png" for i in range(4)]
    return []


def particle_asset_path(mode: str) -> str | None:
    """Return relative Flet asset path if an image asset exists in assets/particles/."""
    variants = particle_asset_variants(mode)
    if variants:
        return variants[0]
    return None


def is_title_unlocked(game: Any, title_id: str) -> bool:
    """Check if a Hero Title is unlocked via in-game achievement or owned."""
    if title_id in ("title_none", "title_beta"):
        return True
    p = getattr(game, "profile", None)
    if p and title_id in getattr(p, "owned_cosmetics", []):
        return True
    data = getattr(game, "data", None)
    if data is None or p is None:
        return True

    unlocked = False
    if title_id == "title_dawn":
        unlocked = any(
            (getattr(r, "started", "") and "05:00" <= r.started <= "06:00")
            for r in getattr(data, "runs", [])
        ) or any(
            (getattr(w, "started", "") and "05:00" <= w.started <= "06:00")
            for w in getattr(data, "workouts", [])
        )
    elif title_id == "title_dusk":
        unlocked = any(
            (getattr(r, "started", "") and "17:00" <= r.started <= "18:00")
            for r in getattr(data, "runs", [])
        ) or any(
            (getattr(w, "started", "") and "17:00" <= w.started <= "18:00")
            for w in getattr(data, "workouts", [])
        )
    elif title_id == "title_alchemist":
        unlocked = len(getattr(data, "meals", [])) >= 7 or len(getattr(data, "water", [])) >= 7
    elif title_id == "title_scholar":
        unlocked = any(
            getattr(s, "mode", "") == "exam" and s.total > 0 and s.right == s.total
            for s in getattr(data, "study_sessions", [])
        )
    elif title_id == "title_monk":
        unlocked = len(getattr(data, "energy", [])) >= 10 or len(getattr(data, "logs", [])) >= 10
    elif title_id == "title_vanguard":
        unlocked = len(getattr(data, "workouts", [])) >= 10
    elif title_id == "title_ranger":
        unlocked = len(getattr(data, "runs", [])) >= 5
    elif title_id == "title_ronin":
        unlocked = any(getattr(f, "minutes", 0) >= 60 for f in getattr(data, "focus_sessions", []))
    elif title_id == "title_sovereign":
        total_tracked = (
            sum(getattr(e, "amount", 0.0) for e in getattr(data, "expenses", []))
            + sum(getattr(sg, "current_amount", 0.0) for sg in getattr(data, "savings_goals", []))
            + sum(getattr(b, "amount", 0.0) for b in getattr(data, "bills", []))
        )
        unlocked = total_tracked >= 50000.0
    elif title_id == "title_sprinter":
        unlocked = getattr(p, "daily_login_streak", 0) >= 7
    elif title_id == "title_early":
        unlocked = (
            any(getattr(s, "wake", "") and s.wake <= "06:30" for s in getattr(data, "sleep", []))
            or getattr(p, "daily_login_streak", 0) >= 5
        )

    if unlocked and p and hasattr(p, "owned_cosmetics") and title_id not in p.owned_cosmetics:
        p.owned_cosmetics.append(title_id)
    return unlocked

