"""Sync tool to parse DataBank/Life Of Legends/Design/flora-combinations-and-tuning.md
and update the SEEDS dictionary and FUSION_RECIPES in src/lol/core/grove.py.

Usage:
    .venv\\Scripts\\python tools\\sync_flora_databank.py
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATABANK_MD = ROOT / "DataBank" / "Life Of Legends" / "Design" / "flora-combinations-and-tuning.md"
GROVE_PY = ROOT / "src" / "lol" / "core" / "grove.py"


def sync_databank() -> bool:
    if not DATABANK_MD.exists():
        print(f"Error: {DATABANK_MD} does not exist.")
        return False

    content = DATABANK_MD.read_text(encoding="utf-8")

    # 1. Parse Seeds Table
    seed_pattern = re.compile(
        r"\|\s*`(?P<id>seed_[^`]+)`\s*\|\s*(?P<name>[^|]+?)\s*\|\s*(?P<tier>\d+)\s*\|\s*(?P<rarity>[^|]+?)\s*\|\s*(?P<emoji>[^|]+?)\s*\|\s*`?(?P<icon>[^`|]+?)`?\s*\|\s*(?P<color>[^|]+?)\s*\|\s*(?P<growth>[^|]+?)\s*\|\s*(?P<coins>[0-9,]+)\s*\|\s*(?P<mut>[0-9.]+)%?\s*\|\s*(?P<desc>[^|]+?)\s*\|"
    )

    seeds_entries: list[str] = []
    found_seeds = 0

    for match in seed_pattern.finditer(content):
        d = match.groupdict()
        sid = d["id"].strip()
        name = d["name"].strip()
        tier = int(d["tier"].strip())
        rarity = d["rarity"].strip()
        emoji = d["emoji"].strip()
        icon = d["icon"].strip()
        color = d["color"].strip()

        growth_raw = d["growth"].strip()
        s_match = re.search(r"(\d+)\s*s", growth_raw)
        m_match = re.search(r"(\d+)\s*m", growth_raw)
        if s_match:
            growth_s = int(s_match.group(1))
        elif m_match:
            growth_s = int(m_match.group(1)) * 60
        else:
            growth_s = 1800

        coins = int(d["coins"].replace(",", "").strip())
        mut_chance = round(float(d["mut"].strip()) / 100.0, 3)
        desc = d["desc"].strip().replace('"', '\\"')

        entry = f"""    "{sid}": SeedDef(
        "{sid}",
        "{name}",
        {tier},
        "{rarity}",
        "{desc}",
        growth_time_s={growth_s},
        coin_yield={coins},
        color="{color}",
        icon_name="{icon}",
        emoji="{emoji}",
        mutation_chance={mut_chance},
    ),"""
        seeds_entries.append(entry)
        found_seeds += 1

    if found_seeds == 0:
        print("No seed table entries found in databank markdown.")
        return False

    print(f"Parsed {found_seeds} flora seeds from databank.")

    # 2. Parse Recipe Tables
    recipe_pattern = re.compile(
        r"\|\s*.*?`?(seed_[a-z0-9_]+)`?.*?\s*\|\s*.*?`?(seed_[a-z0-9_]+)`?.*?\s*\|\s*`?(seed_[a-z0-9_]+)`?\s*\|"
    )

    recipes_entries: list[str] = []
    seen_pairs: set[frozenset[str]] = set()

    # Find section 2 onwards
    sec2_idx = content.find("## 2. Alchemical Synthesis Recipes")
    if sec2_idx != -1:
        sec3_idx = content.find("## 3. Real-World Fitness", sec2_idx)
        recipe_text = content[sec2_idx:sec3_idx] if sec3_idx != -1 else content[sec2_idx:]
        for rmatch in recipe_pattern.finditer(recipe_text):
            ing_a = rmatch.group(1)
            ing_b = rmatch.group(2)
            res = rmatch.group(3)
            pair = frozenset({ing_a, ing_b})
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            recipes_entries.append(
                f'    frozenset({{"{ing_a}", "{ing_b}"}}): "{res}",'
            )

    print(f"Parsed {len(recipes_entries)} alchemy fusion recipes from databank.")

    grove_code = GROVE_PY.read_text(encoding="utf-8")

    # Update SEEDS dict
    new_seeds_block = "SEEDS: dict[str, SeedDef] = {\n" + "\n".join(seeds_entries) + "\n}"
    pattern_seeds = re.compile(r"SEEDS:\s*dict\[str,\s*SeedDef\]\s*=\s*\{.*?\n\}", re.DOTALL)
    if not pattern_seeds.search(grove_code):
        print("Could not find SEEDS dictionary block in grove.py")
        return False
    updated_code = pattern_seeds.sub(new_seeds_block, grove_code)

    # Update FUSION_RECIPES dict if we found recipes
    if recipes_entries:
        new_recipes_block = "FUSION_RECIPES: dict[frozenset[str], str] = {\n" + "\n".join(recipes_entries) + "\n}"
        pattern_recipes = re.compile(
            r"FUSION_RECIPES:\s*dict\[frozenset\[str\],\s*str\]\s*=\s*\{.*?\n\}", re.DOTALL
        )
        if pattern_recipes.search(updated_code):
            updated_code = pattern_recipes.sub(new_recipes_block, updated_code)

    GROVE_PY.write_text(updated_code, encoding="utf-8")
    print(f"Successfully updated {GROVE_PY} with {found_seeds} flora definitions and {len(recipes_entries)} recipes!")
    return True


if __name__ == "__main__":
    sync_databank()
