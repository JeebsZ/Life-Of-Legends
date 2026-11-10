# Mind Grove: Flora Data, Alchemy Combinations & Economy Tuning Table

This databank document serves as the single source of truth for **Mind Grove (The Fitness Farm)** in LUMA. It documents all 22 plant species, their stats, all 18 alchemy cross-breeding recipes (including Tier 3 + Tier 1 elemental infusions), companion feeding parameters, and fitness habit sync rates.

Use this reference whenever adjusting numbers, balancing coin yields, tuning growth timers, or swapping in custom 2D art assets/icons.
Run `.venv\Scripts\python tools\sync_flora_databank.py` to synchronize any edits directly to game code!

---

## 1. Master Flora Catalog Table

| Seed ID              | Plant Name            | Tier |  Rarity  | Emoji | Icon Name               | Theme Color |  Growth Time  | Coin Yield | Mutation Chance | Description / Lore                                                                        |
| :------------------- | :-------------------- | :--: | :------: | :---: | :---------------------- | :---------- | :-----------: | :--------: | :-------------: | :---------------------------------------------------------------------------------------- |
| `seed_aqua`          | Aqua Spore            |  1   |  Common  |  💧   | `water_drop`            | `#00F5D4`   |  30m (1800s)  |     12     |       8%        | A bioluminescent water spore earned by staying hydrated.                                  |
| `seed_solar`         | Solar Fern Seed       |  1   |  Common  |  ☀️   | `wb_sunny`              | `#FFD166`   |  30m (1800s)  |     14     |       8%        | A radiant ember seed energized by outdoor walks and runs.                                 |
| `seed_terra`         | Terra Bulb            |  1   |  Common  |  🪨   | `fitness_center`        | `#06D6A0`   |  40m (2400s)  |     15     |       8%        | An iron-dense earthen bulb strengthened by gym and workout sessions.                      |
| `seed_spirit`        | Spirit Sprout         |  1   |  Common  |  🌙   | `self_improvement`      | `#C77DFF`   |  40m (2400s)  |     15     |       8%        | A tranquil twilight seed nurtured by mindful sleep and focus sessions.                    |
| `seed_mist`          | Vapor Orchid          |  2   | Uncommon |  🌸   | `local_florist`         | `#FF99C8`   |  60m (3600s)  |     35     |       8%        | A delicate blossom that shimmers with warm morning mist. (Aqua + Solar)                   |
| `seed_deep`          | Tide Root             |  2   | Uncommon |  🌿   | `waves`                 | `#48CAE4`   |  70m (4200s)  |     40     |       8%        | A glowing abyssal root rich in ocean minerals. (Aqua + Terra)                             |
| `seed_magma`         | Cinder Pepper         |  2   | Uncommon |  🌶️  | `whatshot`              | `#FF6B35`   |  70m (4200s)  |     40     |       8%        | A warm volcanic pepper pulsing with kinetic heat. (Solar + Terra)                         |
| `seed_dawn`          | Aurora Lily           |  2   | Uncommon |  🌻   | `flare`                 | `#FFB4D6`   |  80m (4800s)  |     45     |       8%        | A celestial flower that blooms with changing sunrise hues. (Solar + Spirit)               |
| `seed_frost`         | Frost Lotus           |  2   | Uncommon |  ❄️   | `ac_unit`               | `#A0C4FF`   |  80m (4800s)  |     45     |       8%        | A crystalline flower that radiates a soothing winter chill. (Aqua + Spirit)               |
| `seed_iron`          | Star-Iron Acorn       |  2   | Uncommon |  🌰   | `shield`                | `#BDB2FF`   |  90m (5400s)  |     50     |       8%        | A sturdy metallic acorn forged with earthen resilience. (Terra + Spirit)                  |
| `seed_abyssal`       | Abyssal Kelp          |  2   | Uncommon |  🌊   | `water`                 | `#0077B6`   |  85m (5100s)  |     48     |       8%        | Luminescent deep-sea kelp shimmering with oceanic tranquility. (Deep + Frost)             |
| `seed_solar_flare`   | Flare Peony           |  2   | Uncommon |  🌺   | `wb_iridescent`         | `#FF5400`   |  85m (5100s)  |     48     |       8%        | A radiant blossom bathed in intense morning dawn warmth. (Magma + Dawn)                   |
| `seed_volcanic`      | Volcanic Bloom        |  3   |   Rare   |   ⚡   | `local_fire_department` | `#EF476F`   | 120m (7200s)  |     90     |       12%       | A blazing floral wonder that blooms amid floating embers. (Mist + Magma)                  |
| `seed_celestial`     | Celestial Dahlia      |  3   |   Rare   |  🌌   | `stars`                 | `#7209B7`   | 140m (8400s)  |    100     |       15%       | Concentrated deep-space stardust and diamond petals. (Frost + Dawn)                       |
| `seed_chrono`        | Chrono Rose           |  3   |   Rare   |   ⏳   | `hourglass_bottom`      | `#FFD166`   | 160m (9600s)  |    110     |       15%       | An intricate golden rose whose petals turn in rhythmic motion. (Dawn + Deep)              |
| `seed_storm`         | Thunder Blossom       |  3   |   Rare   |  ⛈️   | `bolt`                  | `#3A86FF`   | 160m (9600s)  |    120     |       15%       | Crackles with electric violet lightning across its leaves. (Mist + Iron)                  |
| `seed_obsidian`      | Obsidian Lily         |  3   |   Rare   |  🖤   | `shield_moon`           | `#5A189A`   | 150m (9000s)  |    115     |       12%       | Glassy midnight lily created by rapidly cooling volcanic embers with sacred water. (Volcanic + Aqua) |
| `seed_supernova`     | Supernova Starflower  |  3   |   Rare   |  💥   | `flare`                 | `#FFBE0B`   | 150m (9000s)  |    120     |       14%       | Blinding stellar petals charged with pure solar kinetic radiance. (Celestial + Solar)     |
| `seed_crystal_bell`  | Crystal Campanula     |  3   |   Rare   |  🔔   | `notifications_active`  | `#90E0EF`   | 170m (10200s) |    125     |       14%       | Resonating crystal bells chiming with mindful cadence and focus. (Chrono + Spirit)        |
| `seed_magnetic`      | Lodestone Cactus      |  3   |   Rare   |  🧲   | `attractions`           | `#2B9348`   | 170m (10200s) |    125     |       14%       | A magnetic succulent crackling with iron filaments and earthen pull. (Storm + Terra)      |
| `seed_plasma`        | Plasma Lotus          |  3   |   Rare   |  🪷   | `electric_bolt`         | `#F72585`   | 200m (12000s) |    160     |       15%       | Superheated ionized petals dancing in a perpetual halo of neon plasma. (Volcanic + Storm) |
| `seed_astral`        | Astral Orchid         |  3   |   Rare   |  🌠   | `filter_vintage`        | `#4CC9F0`   | 220m (13200s) |    175     |       15%       | Translucent nebula flower showing miniature revolving celestial constellations. (Celestial + Chrono) |
| `seed_yggdrasil`     | World Tree Sapling    |  4   |  Mythic  |  🌳   | `park`                  | `#06D6A0`   | 240m (14400s) |    280     |       10%       | An ancient sprout pulsing with the primal life energy of the cosmos. (Deep + Iron)        |
| `seed_void`          | Void Dragonfruit      |  4   |  Mythic  |  🐉   | `auto_awesome`          | `#9D4EDD`   | 300m (18000s) |    350     |       10%       | A dark cosmic fruit enveloped in faint gravitational nebula rings. (Celestial + Volcanic) |
| `seed_phoenix`       | Phoenix Ash Willow    |  4   |  Mythic  |  🔥   | `whatshot`              | `#F3722C`   | 320m (19200s) |    380     |       10%       | Flaming golden boughs whose falling embers regenerate the soil. (Volcanic + Supernova)    |
| `seed_genesis`       | Genesis Bloom         |  4   |  Mythic  |  🌟   | `all_inclusive`         | `#4895EF`   | 360m (21600s) |    420     |       10%       | Primal botanical origin flower radiating kaleidoscopic universal auroras. (Astral + Plasma) |

---

## 2. Alchemical Synthesis Recipes (Cross-Breeding Combinations)

All combinations in LUMA are **deterministic formulas**. When a user combines these exact two seeds at the Botanical Altar, they obtain the target flora.

> **Lucky Tier Mutation**: Whenever fusing at the Altar, there is an automatic **10% lucky mutation chance** to jump an extra tier higher!

### Tier 1 + Tier 1 ➔ Tier 2 Elemental Hybrids
| Ingredient A | Ingredient B | Resulting Seed | Resulting Plant Name | Tier | Success |
| :--- | :--- | :--- | :--- | :---: | :---: |
| 💧 Aqua Spore (`seed_aqua`) | ☀️ Solar Fern (`seed_solar`) | `seed_mist` | 🌸 Vapor Orchid | 2 | 100% |
| 💧 Aqua Spore (`seed_aqua`) | 🪨 Terra Bulb (`seed_terra`) | `seed_deep` | 🌿 Tide Root | 2 | 100% |
| ☀️ Solar Fern (`seed_solar`) | 🪨 Terra Bulb (`seed_terra`) | `seed_magma` | 🌶️ Cinder Pepper | 2 | 100% |
| ☀️ Solar Fern (`seed_solar`) | 🌙 Spirit Sprout (`seed_spirit`) | `seed_dawn` | 🌻 Aurora Lily | 2 | 100% |
| 💧 Aqua Spore (`seed_aqua`) | 🌙 Spirit Sprout (`seed_spirit`) | `seed_frost` | ❄️ Frost Lotus | 2 | 100% |
| 🪨 Terra Bulb (`seed_terra`) | 🌙 Spirit Sprout (`seed_spirit`) | `seed_iron` | 🌰 Star-Iron Acorn | 2 | 100% |

### Tier 2 + Tier 2 ➔ Tier 2 Extended Hybrids & Tier 3 Mystical Flora
| Ingredient A | Ingredient B | Resulting Seed | Resulting Plant Name | Tier | Success |
| :--- | :--- | :--- | :--- | :---: | :---: |
| 🌿 Tide Root (`seed_deep`) | ❄️ Frost Lotus (`seed_frost`) | `seed_abyssal` | 🌊 Abyssal Kelp | 2 | 100% |
| 🌶️ Cinder Pepper (`seed_magma`) | 🌻 Aurora Lily (`seed_dawn`) | `seed_solar_flare` | 🌺 Flare Peony | 2 | 100% |
| 🌸 Vapor Orchid (`seed_mist`) | 🌶️ Cinder Pepper (`seed_magma`) | `seed_volcanic` | ⚡ Volcanic Bloom | 3 | 100% |
| ❄️ Frost Lotus (`seed_frost`) | 🌻 Aurora Lily (`seed_dawn`) | `seed_celestial` | 🌌 Celestial Dahlia | 3 | 100% |
| 🌻 Aurora Lily (`seed_dawn`) | 🌿 Tide Root (`seed_deep`) | `seed_chrono` | ⏳ Chrono Rose | 3 | 100% |
| 🌸 Vapor Orchid (`seed_mist`) | 🌰 Star-Iron Acorn (`seed_iron`) | `seed_storm` | ⛈️ Thunder Blossom | 3 | 100% |

### Tier 3 + Tier 1 ➔ Elemental Infusions (Cross-Tier Mastery)
| Ingredient A | Ingredient B | Resulting Seed | Resulting Plant Name | Tier | Success |
| :--- | :--- | :--- | :--- | :---: | :---: |
| ⚡ Volcanic Bloom (`seed_volcanic`) | 💧 Aqua Spore (`seed_aqua`) | `seed_obsidian` | 🖤 Obsidian Lily | 3 | 100% |
| 🌌 Celestial Dahlia (`seed_celestial`) | ☀️ Solar Fern (`seed_solar`) | `seed_supernova` | 💥 Supernova Starflower | 3 | 100% |
| ⏳ Chrono Rose (`seed_chrono`) | 🌙 Spirit Sprout (`seed_spirit`) | `seed_crystal_bell` | 🔔 Crystal Campanula | 3 | 100% |
| ⛈️ Thunder Blossom (`seed_storm`) | 🪨 Terra Bulb (`seed_terra`) | `seed_magnetic` | 🧲 Lodestone Cactus | 3 | 100% |

### Tier 3 + Tier 3 ➔ Transcendent Astral Flora
| Ingredient A | Ingredient B | Resulting Seed | Resulting Plant Name | Tier | Success |
| :--- | :--- | :--- | :--- | :---: | :---: |
| ⚡ Volcanic Bloom (`seed_volcanic`) | ⛈️ Thunder Blossom (`seed_storm`) | `seed_plasma` | 🪷 Plasma Lotus | 3 | 100% |
| 🌌 Celestial Dahlia (`seed_celestial`) | ⏳ Chrono Rose (`seed_chrono`) | `seed_astral` | 🌠 Astral Orchid | 3 | 100% |

### Tier 3 & Tier 4 Fusions ➔ Mythic World Tree & Cosmic Flora
| Ingredient A | Ingredient B | Resulting Seed | Resulting Plant Name | Tier | Success |
| :--- | :--- | :--- | :--- | :---: | :---: |
| 🌿 Tide Root (`seed_deep`) | 🌰 Star-Iron Acorn (`seed_iron`) | `seed_yggdrasil` | 🌳 World Tree Sapling | 4 | 100% |
| 🌌 Celestial Dahlia (`seed_celestial`) | ⚡ Volcanic Bloom (`seed_volcanic`) | `seed_void` | 🐉 Void Dragonfruit | 4 | 100% |
| ⚡ Volcanic Bloom (`seed_volcanic`) | 💥 Supernova Starflower (`seed_supernova`) | `seed_phoenix` | 🔥 Phoenix Ash Willow | 4 | 100% |
| 🌠 Astral Orchid (`seed_astral`) | 🪷 Plasma Lotus (`seed_plasma`) | `seed_genesis` | 🌟 Genesis Bloom | 4 | 100% |

### Non-Recipe Essence Transmutation
- When 2 seeds that do **not** form a direct formula are fused:
  - LUMA combines their life essences to yield a random seed of the higher tier: `target_tier = min(4, max(tier_a, tier_b))`.
  - Still rolls the 10% lucky mutation chance to jump one tier higher!

---

## 3. Real-World Fitness & Habit Sync Parameters

| Real-World Habit | Trigger Requirement | Reward | In-Game Effect |
| :--- | :--- | :--- | :--- |
| **Hydration** | Log daily water intake (any amount $\ge 250\text{ mL}$) | +1 Aqua Spore (`seed_aqua`) | Hydrates soil, awards base water spore once daily. |
| **Outdoor Runs / Walks** | Total GPS run/walk distance logged today | +1 Solar Fern (`seed_solar`) | **Sunlight Speedup**: Every $100\text{ m}$ walked or run shaves **$60\text{ s}$ off all growing plots**! (e.g. a $2.5\text{ km}$ run speeds up crops by $25\text{ mins}$). |
| **Gym & Workouts** | Log at least 1 workout session | +1 Terra Bulb (`seed_terra`) | Strengthens roots, awards base earth bulb once daily. |
| **Mindful Sleep / Focus** | Log sleep entry or complete a focus session | +1 Spirit Sprout (`seed_spirit`) | Calms grove, awards base spirit sprout once daily. |

---

## 4. Companion Feeding & Silo Economy (Sell vs Feed)

| Parameter | Current Value | Tuning Notes |
| :--- | :---: | :--- |
| **Harvest Direct Coins** | **0 coins** | Crops go directly to Silo inventory; player chooses between selling or feeding. |
| **Sell Crop Value** | `base_yield * luma_barter_mult` | Tier 1: 12–15 coins, Tier 2: 35–50, Tier 3: 90–175, Tier 4: 280–420. |
| **LUMA Barter Multiplier** | `1.0x` (Lv 1) ➔ `1.50x` (Lv 10) | Leveling up LUMA companion increases market crop barter value. |
| **Feed Companion XP** | Tier 1: 20 XP<br>Tier 2: 60 XP<br>Tier 3: 180 XP<br>Tier 4: 500 XP | Upgrades companion level and unlocks grove plot perks. |
| **Premium Feast Perk** | **+50% Feed XP** | Legends+ active subscriber perk: 1.5x Companion XP gain when feeding. |
| **Coin Boost on Feed** | **+10% Daily Coin Boost** | Active for 24 hours after feeding companion. |
| **Grove Plot Unlocks** | 6 Plots (Base)<br>7 Plots (Lv 5 LUMA)<br>8 Plots (Lv 10 LUMA) | Rewarding long-term farming progression. |
| **Initial Starter Spores** | 2 Aqua, 2 Solar, 1 Terra, 1 Spirit | Brand new players start with 6 seeds to immediately plant and experiment with. |

---

## 5. Developer Guide: How to Read & Adjust

When you want to tweak values:
1. Edit the markdown tables above (coin yields, growth times, emojis, names, recipes).
2. Run `.venv\Scripts\python tools\sync_flora_databank.py`.
3. The script will automatically update `SEEDS` and `FUSION_RECIPES` in `src/lol/core/grove.py`.
