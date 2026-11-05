"""On-device food classifier labels -> meal candidates. Pure: no Flet, no I/O.

The classifier (Google AIY food_V1, see extensions/flet_lumen_vision) names ~2,000 dishes
in English ("Philippine adobo", "White rice", ...) plus `__background__` and ~20 untranslated
knowledge-graph ids ("/g/11b8_rxx4d"). This module:

- drops non-food / unreadable labels and weak scores,
- maps each label to a foods.py id: first through the hand-curated ALIASES table (exact model
  label -> id), then foods.match_food (fuzzy), else a name-only candidate (food_id None),
- merges labels that land on the same food (their probabilities add up),

and returns at most a few `Candidate`s, best first. Thresholds are constants so they can be
tuned after testing real meals on the phone.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable

from lol.core import foods
from lol.core.recognize import Candidate

BACKGROUND = "__background__"

# A softmax over 2,024 classes: a clear single dish usually scores 0.3-0.9 for its top
# label, a mixed or badly framed plate spreads out to <0.1 per label. Below MIN_CONFIDENCE a
# label is mostly noise; alternatives must also reach RELATIVE_FLOOR x the best score so one
# strong guess is not padded with junk.
MIN_CONFIDENCE = 0.10
RELATIVE_FLOOR = 0.25
MAX_CANDIDATES = 3
TOP_K = 10  # how many labels to ask the model for (merging needs more than MAX_CANDIDATES)

# Model labels (exact spelling, see assets/food_v1_labels.txt) that are Filipino dishes.
# Menudo is ambiguous: the model most likely learned the Mexican tripe soup.
FILIPINO_LABELS: tuple[str, ...] = (
    "Philippine adobo",
    "Sinigang",
    "Kare-kare",
    "Bistek",
    "Kaldereta",
    "Menudo",
    "Halo-halo",
    "Champorado",
    "Bibingka",
    "Puto",
    "Kutsinta",
    "Suman",
    "Sapin-sapin",
    "Palitaw",
    "Sorbetes",
)

# Exact model label -> foods.py id. Only where the fuzzy matcher would miss or pick wrong
# (different name, regional dish that looks the same on a Filipino plate). Labels with no
# sensible food (e.g. "Palitaw") are left out on purpose: they become name-only candidates.
ALIASES: dict[str, str] = {
    # Filipino dishes the model knows
    "Philippine adobo": "adobo_chicken",  # pork or chicken can't be told apart; user can switch
    "Sinigang": "sinigang_pork",
    "Kare-kare": "kare_kare",
    "Bistek": "bistek",
    "Kaldereta": "caldereta",
    "Menudo": "menudo",
    "Halo-halo": "halo_halo",
    "Champorado": "champorado",
    "Bibingka": "bibingka",
    "Puto": "puto",
    "Kutsinta": "kutsinta",
    "Suman": "suman",
    "Sapin-sapin": "sapin_sapin",
    "Sorbetes": "ice_cream",
    # Look-alikes on a Filipino plate
    "White rice": "rice",
    "Fried rice": "fried_rice",
    "Yangzhou fried rice": "fried_rice",
    "Hokkien fried rice": "fried_rice",
    "American fried rice": "fried_rice",
    "Thai fried rice": "fried_rice",
    "Kimchi fried rice": "fried_rice",
    "Arroz chaufa": "fried_rice",
    "Congee": "lugaw",
    "Chow mein": "pancit_canton",
    "Lo mein": "pancit_canton",
    "Shanghai fried noodles": "pancit_canton",
    "Beef noodle soup": "mami",
    "Wonton noodles": "mami",
    "Macaroni soup": "sopas",
    "Shumai": "siomai",
    "Baozi": "siopao",
    "Suckling pig": "lechon",
    "Siu yuk": "lechon_kawali",
    "Satay": "bbq_pork",
    "Char siu": "bbq_pork",
    "Fried fish": "tilapia_fried",
    "Fish ball": "fishball",
    "Crème caramel": "leche_flan",
    "Flan": "leche_flan",
    # Fast food and basics
    "Fried chicken": "fried_chicken",
    "Chicken nugget": "chicken_nuggets",
    "Hot dog": "hotdog",
    "Hamburger": "burger",
    "Cheeseburger": "cheeseburger",
    "Spaghetti": "spaghetti_meat",
    "Ramen": "ramen",
    "Shawarma": "shawarma",
    "Sushi": "sushi_california",
    "Burrito": "burrito",
    "Doughnut": "donut",
    "Bacon": "bacon",
    "Peanut butter": "peanut_butter",
    "Garden salad": "salad",
    "Ham and cheese sandwich": "sandwich_ham_cheese",
    "New York-style pizza": "pizza_cheese",
    "Neapolitan pizza": "pizza_cheese",
    "Chicago-style pizza": "pizza_cheese",
    "California-style pizza": "pizza_cheese",
    "Detroit-style pizza": "pizza_cheese",
}

Matcher = Callable[[str], str | None]


def is_food_label(label: str) -> bool:
    """False for the background class, untranslated ids ('/g/...') and blanks."""
    t = (label or "").strip()
    return bool(t) and t != BACKGROUND and not t.startswith("/")


def food_id_for_label(label: str, matcher: Matcher | None = None) -> str | None:
    """foods.py id for a model label: alias table first, then the fuzzy matcher
    (default foods.match_food), else None."""
    if not is_food_label(label):
        return None
    fid = ALIASES.get(label.strip())
    if fid is not None:
        return fid
    match = matcher if matcher is not None else foods.match_food
    return match(label.strip())


def candidates_from_predictions(
    predictions: Iterable[tuple[str, float]],
    matcher: Matcher | None = None,
    min_confidence: float = MIN_CONFIDENCE,
    relative_floor: float = RELATIVE_FLOOR,
    limit: int = MAX_CANDIDATES,
) -> list[Candidate]:
    """Model (label, probability) pairs -> at most `limit` Candidates, best first.

    Labels mapping to the same food are merged (probabilities summed, capped at 1) so
    "Fried rice" + "Yangzhou fried rice" count as one stronger "fried_rice". Unmapped labels
    stay as name-only candidates (food_id None) so the user still sees what the camera saw.
    """
    merged: dict[str, Candidate] = {}
    order: list[str] = []
    for label, prob in predictions:
        try:
            p = float(prob)
        except (TypeError, ValueError):
            continue
        if not is_food_label(label) or math.isnan(p) or p <= 0:
            continue
        name = label.strip()
        fid = food_id_for_label(name, matcher)
        key = fid if fid is not None else "name:" + name.casefold()
        prev = merged.get(key)
        if prev is None:
            display = foods.food(fid).name if fid is not None and foods.has(fid) else name
            merged[key] = Candidate(name=display, confidence=min(p, 1.0), food_id=fid)
            order.append(key)
        else:
            merged[key] = Candidate(
                name=prev.name, confidence=min(prev.confidence + p, 1.0), food_id=prev.food_id
            )
    ranked = sorted(merged.values(), key=lambda c: (-c.confidence, order.index(_key(c))))
    if not ranked:
        return []
    best = ranked[0].confidence
    floor = max(min_confidence, best * relative_floor)
    return [c for c in ranked if c.confidence >= floor][: max(0, limit)]


def _key(c: Candidate) -> str:
    return c.food_id if c.food_id is not None else "name:" + c.name.casefold()
