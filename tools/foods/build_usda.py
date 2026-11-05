"""Build the compact USDA databank asset (src/assets/data/usda_foods.json.gz).

Source: USDA FoodData Central bulk downloads (public domain / CC0), no API key:
    https://fdc.nal.usda.gov/download-datasets/
    - SR Legacy, CSV, April 2018:      FoodData_Central_sr_legacy_food_csv_2018-04.zip
    - Foundation Foods, JSON, 2026-10-29: FoodData_Central_foundation_food_json_2026-10-29.zip
      (the 2026-10-29 Foundation CSV bundle ships without food/food_nutrient/food_portion,
      so the JSON bundle is used for Foundation)

Usage (unzip both first; run with an isolated interpreter):
    python -I tools/foods/build_usda.py --sr <unzipped SR csv folder>
        --foundation <Foundation .json file> [--out src/assets/data/usda_foods.json.gz]

Output (gzip JSON, columnar to stay small):
    {"v": 1, "built": "...", "sources": [...], "cats": [category names],
     "cols": ["fdc", "name", "cat", "kcal", "protein", "carbs", "fat", "fiber", "sugar",
              "sodium_mg", "portions"],
     "foods": [[fdc_id, name, cat_index, kcal, p, c, f, fiber|null, sugar|null, sodium|null,
                [[label, grams], ...]], ...]}
All nutrients are per 100 g. Foundation entries win over SR Legacy when both have a food with
the same description. Foods without kcal, protein, carbs and fat are dropped.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import json
from pathlib import Path

# FDC nutrient *numbers* (stable across datasets)
N_KCAL = ("208", "958", "957")  # Energy kcal, then Atwater specific, then general
N_PROTEIN, N_FAT, N_FIBER, N_SODIUM = "203", "204", "291", "307"
N_CARBS = ("205", "205.2")  # by difference, then by summation
N_SUGAR = ("269", "269.3")  # total sugars, then "sugars, total NLEA"
MAX_PORTIONS = 6
UNKNOWN_UNIT = "undetermined"


def r1(x: float | None) -> float | None:
    if x is None:
        return None
    v = round(float(x), 1)
    return int(v) if v.is_integer() else v


def first(d: dict[str, float], keys: tuple[str, ...]) -> float | None:
    for k in keys:
        if k in d:
            return d[k]
    return None


def portion_label(amount: float | None, unit: str, desc: str, modifier: str) -> str:
    amt = "" if amount in (None, "") else f"{float(amount):g} "
    unit = (unit or "").strip()
    extra = (desc or modifier or "").strip()
    if not unit or unit in (UNKNOWN_UNIT, "RACC"):
        text = f"{amt}{extra}".strip() or "serving"
    else:
        text = f"{amt}{unit}" + (f" {modifier.strip()}" if modifier and modifier.strip() else "")
    return " ".join(text.split())[:40]


def build_row(fdc: int, name: str, cat: str, nut: dict[str, float],
              portions: list[tuple[str, float]]) -> tuple | None:
    kcal = first(nut, N_KCAL)
    p, f, c = nut.get(N_PROTEIN), nut.get(N_FAT), first(nut, N_CARBS)
    if kcal is None or p is None or f is None or c is None:
        return None
    seen, ps = set(), []
    for label, g in portions:
        if g and g > 0 and label not in seen:
            seen.add(label)
            ps.append([label, r1(g)])
        if len(ps) >= MAX_PORTIONS:
            break
    return (fdc, name.strip(), cat, r1(kcal), r1(p), r1(c), r1(f), r1(nut.get(N_FIBER)),
            r1(first(nut, N_SUGAR)), r1(nut.get(N_SODIUM)), ps)


def read_sr(folder: Path) -> list[tuple]:
    def rows(name: str):
        with open(folder / name, encoding="utf-8", newline="") as fh:
            yield from csv.DictReader(fh)

    num_of = {r["id"]: r["nutrient_nbr"] for r in rows("nutrient.csv")}
    want = {N_PROTEIN, N_FAT, N_FIBER, N_SODIUM, *N_KCAL, *N_CARBS, *N_SUGAR}
    cats = {r["id"]: r["description"] for r in rows("food_category.csv")}
    units = {r["id"]: r["name"] for r in rows("measure_unit.csv")}
    nut: dict[str, dict[str, float]] = {}
    for r in rows("food_nutrient.csv"):
        n = num_of.get(r["nutrient_id"])
        if n in want and r["amount"] != "":
            nut.setdefault(r["fdc_id"], {})[n] = float(r["amount"])
    por: dict[str, list[tuple[int, str, float]]] = {}
    for r in rows("food_portion.csv"):
        label = portion_label(r["amount"] or None, units.get(r["measure_unit_id"], ""),
                              r["portion_description"], r["modifier"])
        por.setdefault(r["fdc_id"], []).append(
            (int(r["seq_num"] or 0), label, float(r["gram_weight"] or 0)))
    out = []
    for r in rows("food.csv"):
        fid = r["fdc_id"]
        ps = [(lbl, g) for _, lbl, g in sorted(por.get(fid, []))]
        row = build_row(int(fid), r["description"], cats.get(r["food_category_id"], "Other"),
                        nut.get(fid, {}), ps)
        if row:
            out.append(row)
    return out


def read_foundation(path: Path) -> list[tuple]:
    data = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for f in data["FoundationFoods"]:
        nut: dict[str, float] = {}
        for n in f.get("foodNutrients", []):
            num = (n.get("nutrient") or {}).get("number")
            if num and n.get("amount") is not None:
                nut.setdefault(num, float(n["amount"]))
        ps = []
        for p in sorted(f.get("foodPortions", []), key=lambda p: p.get("sequenceNumber") or 0):
            unit = (p.get("measureUnit") or {}).get("name", "")
            ps.append((portion_label(p.get("amount") or p.get("value"), unit,
                                     p.get("portionDescription", ""), p.get("modifier", "")),
                       float(p.get("gramWeight") or 0)))
        row = build_row(int(f["fdcId"]), f["description"],
                        (f.get("foodCategory") or {}).get("description", "Other"), nut, ps)
        if row:
            out.append(row)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sr", required=True, type=Path)
    ap.add_argument("--foundation", required=True, type=Path)
    ap.add_argument("--out", type=Path, default=Path("src/assets/data/usda_foods.json.gz"))
    a = ap.parse_args()
    found = read_foundation(a.foundation)
    sr = read_sr(a.sr)
    names = {r[1].lower() for r in found}
    rows = found + [r for r in sr if r[1].lower() not in names]
    rows.sort(key=lambda r: r[1].lower())
    cats = sorted({r[2] for r in rows})
    ci = {c: i for i, c in enumerate(cats)}
    doc = {
        "v": 1,
        "built": dt.date.today().isoformat(),
        "sources": [
            {"name": "USDA FoodData Central, Foundation Foods", "release": "2026-10-29",
             "count": len(found)},
            {"name": "USDA FoodData Central, SR Legacy", "release": "2018-04",
             "count": len(rows) - len(found)},
        ],
        "credit": "U.S. Department of Agriculture, Agricultural Research Service. FoodData "
                  "Central. fdc.nal.usda.gov (public domain, CC0 1.0).",
        "cats": cats,
        "cols": ["fdc", "name", "cat", "kcal", "protein", "carbs", "fat", "fiber", "sugar",
                 "sodium_mg", "portions"],
        "foods": [[r[0], r[1], ci[r[2]], *r[3:]] for r in rows],
    }
    a.out.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(doc, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    with gzip.GzipFile(a.out, "wb", compresslevel=9, mtime=0) as fh:
        fh.write(raw)
    print(f"{len(rows)} foods ({len(found)} Foundation + {len(rows) - len(found)} SR Legacy), "
          f"{len(raw) / 1e6:.2f} MB json -> {a.out.stat().st_size / 1e6:.2f} MB gz at {a.out}")


if __name__ == "__main__":
    main()
