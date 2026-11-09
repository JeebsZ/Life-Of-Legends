# Changelog — Nov 7, 2026: Character Creation, Slime GPS Run, 8 New Themes, Background FX & Cosmetics Shop

## 1. Modular Chibi Character Customization
- **Layered 256x256 pixel art chibis**: 7 modular layer slots (Base Body, Clothes, Eyes, Hair, Mouth, Nose, and up to 3 stacked Makeups/blush/eyeshadow/markings).
- **Interactive Character Creator**: Live canvas preview with layer selectors, randomizer, and one-time +200 free coin claim.
- **Universal Chibi Avatar Integration**: Replaced legacy static sigil picker in Profile, Onboarding, Header, Rewards, and Map markers.
- **Avatar Bubble clipping fix**: Solved avatar head/shoulder overflow with circular inner clipping (`ft.ClipBehavior.HARD_EDGE`), auto-syncing ring tint with active theme.

## 2. Slime Adventure GPS Run Tracker
- **Slime Core & Radar**: Live GPS route tracking with Great Sage / Field radar map styles.
- **ARPG Mob Encounters**: Spatial Rifts, auto-spawning monster packs (Slimes, Goblins, Wolves, Bosses), combat DPS scaling with real walking/running pace.
- **Simulated GPS Route Mode**: Dedicated dev-only route simulator gated by `g.dev_allowed()`, awarding 0 XP and 0 coins to preserve economy integrity. Auto-whitelisted for developer account (`jarvin.eslao.work@gmail.com`).

## 3. Store Update Checker & First-Open Google Sign-In
- **Store Version Check**: Added `update_checker.py` to compare running SemVer against Google Play Store HTML/JSON endpoints. Prompts with a non-blocking modal linking directly to Play Store when an update is live.
- **First-Open Auth Prompt**: Prompts Google Cloud Sync sign-in on first app open, with "Sign in with Google" integrated into Onboarding.
- **Fixed Android Bottom Navigation Crash**: Removed conflicting `LayoutControl` coordinates from `ArcaneNavBar` on `SafeArea`, fixing the release build crash.

## 4. 8 New Themes (14 Themes Total)
- Added 8 themes passing WCAG contrast (>= 4.5:1) and Delta E color isolation checks:
  1. `matcha` (250 coins) — Sage-leaf greens & forest-tea darks.
  2. `lavender` (250 coins) — Pastel lilac & twilight periwinkle.
  3. `sakura` (300 coins, glow) — Petal pink & plum night.
  4. `cyber` (350 coins, glow) — Electric cyan & hot magenta synthwave.
  5. `solar` (400 coins, glow) — Sun-forged radiant gold & warm obsidian.
  6. `crimson` (450 coins, glow) — Bloodmoon ruby & obsidian shadow.
  7. `aurora` (500 coins, glow) — Polar mint-cyan & deep arctic violet.
  8. `abyss` (600 coins, glow) — True-black OLED starfield with astral violet.

## 5. Living MindSpace Background Particle FX
- Upgraded `MindSpace` ambience with 7 distinct particle modes:
  - `auto`: Automatically reflects active theme's signature atmosphere.
  - `sakura`: Falling cherry blossom petals with gentle angle drift.
  - `fireflies`: Wandering 2D glowing orbs that twinkle.
  - `embers`: Fast-rising fiery sparks.
  - `snow`: Gracefully descending soft snowflakes.
  - `cyber`: High-tech vertical neon matrix streaks.
  - `stardust`: Rotating 4-point celestial diamond stars.

## 6. Personalization Coin Shop
- Added multi-category coin shop in Rewards tab:
  - **Background FX**: Unlock and pin distinct particle styles independently from themes.
  - **Avatar Frames**: Golden Halo, Sakura Wreath, Cyber Glitch Ring, Flame Aura, Frost Crystal, Void Singularity with dual-glow shadows.
  - **Hero Titles**: Early Bird, Night Owl, Iron Sprinter, Hydro Homie, Zen Monk, Shadow Monarch, Arcane Sovereign (displayed in header & profile).
  - **Companions / Pets**: Starlight Slime (💧), Ember Kitsune (🦊), Moss Sprite (🌿), Cyber Neko (🐱), Astral Owl (🦉), Golden Dragonet (🐉) perched on avatar bubbles.
  - **XP & Trail FX**: Custom gradient XP bars and matching GPS map route polyline trail colors.

