"""USDA FoodData Central databank: load the compact asset and search it fast. Pure: no Flet.

The asset (src/assets/data/usda_foods.json.gz) is built by tools/foods/build_usda.py from the
public-domain FDC bulk downloads (Foundation Foods + SR Legacy). The loader takes a path - the
UI passes the asset path - and `LazyUsda` defers reading it until the first lookup/search.

Ids are "u<fdc_id>". Search uses a 2-letter word-prefix index (thousands of foods stay snappy
on a phone) with a typo fallback over the word vocabulary.
"""

from __future__ import annotations

import difflib
import gzip
import json
import threading
from pathlib import Path
from typing import Any

from lol.core.foods import USDA, USDA_UNCERTAINTY, Food, normalize

PREFIX = "u"
SOURCE_NAME = "USDA FoodData Central"
CREDIT = ("U.S. Department of Agriculture, Agricultural Research Service. FoodData Central. "
          "fdc.nal.usda.gov (public domain, CC0 1.0).")
FDC_URL = "https://fdc.nal.usda.gov/food-details/{}/nutrients"
# USDA lab-analysed chain items (US menus): name prefix -> brand shown in the app
BRAND_PREFIXES: dict[str, str] = {
    "MCDONALD'S": "McDonald's (US)", "KFC": "KFC (US)", "BURGER KING": "Burger King (US)",
    "PIZZA HUT": "Pizza Hut (US)", "DOMINO'S": "Domino's (US)", "POPEYES": "Popeyes (US)",
    "WENDY'S": "Wendy's (US)", "SUBWAY": "Subway (US)", "TACO BELL": "Taco Bell (US)",
    "CHICK-FIL-A": "Chick-fil-A (US)",
}


PORTION_PREFERENCE = ("medium", "serving", "item", "piece", "sandwich", "slice", "large",
                      "small", "fillet", "breast", "thigh", "egg", "cup")


def default_portion(portions: tuple[tuple[str, float], ...]) -> tuple[float, str]:
    """(grams, label) of the most 'typical single serving' household measure, else 100 g."""
    if not portions:
        return 100.0, "100 g"
    for word in PORTION_PREFERENCE:
        for label, g in portions:
            if word in label.lower() and 5 <= g <= 600:
                return g, label
    return portions[0][1], portions[0][0]


def brand_of(name: str) -> str:
    up = name.upper()
    for prefix, brand in BRAND_PREFIXES.items():
        if up.startswith((prefix + ",", prefix + " ")):
            return brand
    return ""


class UsdaDB:
    """The parsed databank. Foods are built on demand and cached."""

    def __init__(self, doc: dict[str, Any]) -> None:
        self.meta = {k: doc.get(k) for k in ("v", "built", "sources", "credit")}
        self.cats: list[str] = list(doc.get("cats", []))
        self.rows: list[list[Any]] = list(doc.get("foods", []))
        self._by_fdc = {int(r[0]): i for i, r in enumerate(self.rows)}
        self._cache: dict[int, Food] = {}
        self._words: list[list[str]] = []
        self._norm: list[str] = []
        self._index: dict[str, list[int]] = {}
        self._brand: dict[int, str] = {}
        for i, r in enumerate(self.rows):
            n = normalize(r[1])
            words = n.split()
            self._norm.append(n)
            b = brand_of(r[1])
            if b:
                self._brand[i] = b
            self._words.append(words)
            for key in {w[:2] for w in words if w}:
                self._index.setdefault(key, []).append(i)
        self._vocab = sorted({w for ws in self._words for w in ws if len(w) >= 3})

    def __len__(self) -> int:
        return len(self.rows)

    def brands(self) -> list[str]:
        return [b for b in BRAND_PREFIXES.values() if b in set(self._brand.values())]

    def brand_items(self, brand: str) -> list[Food]:
        return [self._food(i) for i, b in self._brand.items() if b == brand]

    # --- lookups -----------------------------------------------------------------------------
    def has(self, food_id: str) -> bool:
        return self._row_index(food_id) is not None

    def food(self, food_id: str) -> Food:
        i = self._row_index(food_id)
        if i is None:
            raise KeyError(food_id)
        return self._food(i)

    def _row_index(self, food_id: str) -> int | None:
        if not food_id or not food_id.startswith(PREFIX) or not food_id[1:].isdigit():
            return None
        return self._by_fdc.get(int(food_id[1:]))

    def _food(self, i: int) -> Food:
        f = self._cache.get(i)
        if f is None:
            fdc, name, cat, kcal, p, c, fat, fiber, sugar, sodium, portions = self.rows[i]
            ps = tuple((str(lbl), float(g)) for lbl, g in portions)
            g0, lbl0 = default_portion(ps)
            f = Food(f"{PREFIX}{fdc}", name, float(kcal), float(p), float(c), float(fat), g0,
                     lbl0, USDA, USDA_UNCERTAINTY, (), self.cats[cat], fiber, sugar, sodium,
                     ps, int(fdc), self._brand.get(i, ""), FDC_URL.format(fdc))
            self._cache[i] = f
        return f

    # --- search ------------------------------------------------------------------------------
    def _match(self, tokens: list[str]) -> list[int]:
        if not tokens:
            return []
        pools = [self._index.get(t[:2], []) if len(t) >= 2 else
                 [i for k, v in self._index.items() if k.startswith(t) for i in v]
                 for t in tokens]
        base = min(pools, key=len)
        return [i for i in base
                if all(any(w.startswith(t) for w in self._words[i]) for t in tokens)]

    def search(self, query: str, limit: int = 20) -> list[tuple[float, Food]]:
        """(score 0..85, Food) best first. Every query word must start some word of the name;
        if nothing matches, close spellings from the vocabulary are tried."""
        q = normalize(query)
        tokens = q.split()
        hits = self._match(tokens)
        typo = False
        if not hits and tokens:
            fixed = []
            for t in tokens:
                if len(t) < 4:
                    fixed.append(t)
                    continue
                close = difflib.get_close_matches(t, self._vocab, n=1, cutoff=0.75)
                fixed.append(close[0] if close else t)
            if fixed != tokens:
                hits, tokens, typo = self._match(fixed), fixed, True
        scored = []
        for i in hits:
            words = self._words[i]
            s = 70.0
            if self._norm[i].startswith(" ".join(tokens)):
                s += 10
            elif words and words[0].startswith(tokens[0]):
                s += 6
            s -= min(10.0, len(words) * 0.6)  # shorter, plainer names first
            if typo:
                s -= 8
            scored.append((s, i))
        scored.sort(key=lambda t: (-t[0], len(self._norm[t[1]])))
        return [(s, self._food(i)) for s, i in scored[:limit]]


def load(path: str | Path) -> UsdaDB:
    """Read the gzip JSON asset."""
    with gzip.open(Path(path), "rt", encoding="utf-8") as fh:
        return UsdaDB(json.load(fh))


class LazyUsda:
    """Loads on first use (lookups, search). Missing/broken asset = an empty databank, so the
    app still runs with the curated foods."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._db: UsdaDB | None = None
        self._lock = threading.Lock()
        self.error: str = ""

    @property
    def db(self) -> UsdaDB:
        if self._db is None:
            with self._lock:
                if self._db is None:
                    try:
                        self._db = load(self.path)
                    except (OSError, ValueError, KeyError, IndexError, TypeError) as exc:
                        self.error = f"{exc.__class__.__name__}: {exc}"
                        self._db = UsdaDB({})
        return self._db

    @property
    def loaded(self) -> bool:
        return self._db is not None

    def has(self, food_id: str) -> bool:
        return bool(food_id) and food_id.startswith(PREFIX) and self.db.has(food_id)

    def food(self, food_id: str) -> Food:
        return self.db.food(food_id)

    def search(self, query: str, limit: int = 20) -> list[tuple[float, Food]]:
        return self.db.search(query, limit)

    def brands(self) -> list[str]:
        return self.db.brands()

    def brand_items(self, brand: str) -> list[Food]:
        return self.db.brand_items(brand)
