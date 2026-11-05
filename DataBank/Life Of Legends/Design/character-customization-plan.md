# Character customization — art plan (not built)

**Idea:** a layered 2D avatar (bust/portrait) shown on Profile, the header orb, the onboarding reveal and level-ups. Parts unlock through Paths, levels and (later) premium.

## Use your 3D skills
Model one base bust in Blender. Render every part from the **same camera**, transparent PNG, with consistent lighting. Stylise it with a pixel-art or toon-shader pass if you want. One rig gives you endless parts that all line up.

## Layer stack (back → front)
1. hair_back
2. body (skin tone)
3. outfit
4. neck accessory
5. face base
6. eyes
7. brows
8. mouth
9. face accessory (glasses, marks)
10. hair_front
11. headwear (hood, headphones, hats)
12. aura/frame (Path-coloured glow, done in code)

## File spec
- 512×512 PNG with alpha, all on the same canvas and anchor point.
- Named `avatar/<layer>/<id>.png`, e.g. `avatar/hair_front/messy_01.png`.
- **Recolourable parts** (hair, outfit): paint them in **greyscale**. The app tints them, so one file covers every colour.
- Skin: 6–8 tones. Render the body/face per tone, or greyscale plus a tint (test which looks better).

## MVP part count (~40 files)
| Part | Count |
|---|---|
| Body | 2 builds |
| Hair | 6 (front + back each) |
| Eyes | 6 |
| Brows | 4 |
| Mouth | 6 |
| Outfit | 6, one per Path flavour (mage robe, chef apron, ranger cloak…) |
| Headwear | 4 |
| Face accessories | 4 |

## How it ties into the game
- **Free:** starter set.
- **Earned:** Path rank rewards. Warrior hits rank 3 → armour shoulder, and so on.
- **Coin shop:** a few items.
- **Premium:** exclusive cosmetics (see paywall-plan.md).
- **Unlocks:** each unlock plays the skill/unlock effect, and Luma comments on it.

## What the code side needs from you
A first batch of ~10 parts. I can build the layering, tint, picker UI (tabs: Base · Hair · Face · Outfit · Extras, random dice) and the save field around a placeholder set. Then swap in your art.
