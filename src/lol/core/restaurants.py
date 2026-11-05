"""Restaurant chain items (PH focus). Pure data + arithmetic, no I/O.

Two kinds, never mixed:
- source "official": numbers the chain itself publishes. Only McDonald's Philippines publishes
  per-item nutrition (kcal, fat, carbs, protein, sodium on mcdonalds.com.ph "Our Food" pages).
  The panels there are not labelled with item names; values were matched to items by page
  order, and serving weights (grams) are NOT published - they're estimated from the closest
  USDA McDonald's (US) entries, so kcal for the listed serving is exact, per-gram is not.
- source "estimate": the chain publishes nothing usable (Jollibee, Chowking, Mang Inasal,
  Greenwich, KFC PH, Max's, Shakey's; Starbucks PH lists Tall kcal only). These are BUILT from
  the closest USDA FoodData Central foods (`parts` below, each with its FDC id or a curated
  food that is itself synced to FDC) and carry a wide range (ESTIMATE_UNCERTAINTY).
Global chains (McDonald's US, KFC US, Burger King, Pizza Hut, Domino's, ...) come from USDA's
own lab analyses in the databank (core/usda.py tags them with a brand).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from lol.core import foods as F
from lol.core.foods import ESTIMATE, Food

OFFICIAL = "official"
OFFICIAL_UNCERTAINTY = 0.10  # published kcal, but serving grams are estimated
ESTIMATE_UNCERTAINTY = 0.30  # chain recipe unknown: built from USDA equivalents
SEP = " — "
MCD_PH = "https://www.mcdonalds.com.ph/our-food/{}"
FDC = "https://fdc.nal.usda.gov/food-details/{}/nutrients"

# FDC components used by estimates (per 100 g: kcal, protein, carbs, fat) - SR Legacy values
FDC_PARTS: dict[str, tuple[int, float, float, float, float]] = {
    "kfc_or_thigh": (170346, 269, 18.9, 8.5, 17.7),  # KFC, Original Recipe, thigh w/ skin
    "fried_chicken": (171449, 269, 28.6, 3.1, 14.9),  # broiler, meat+skin, fried, flour
    "gravy_chicken": (171566, 48, 0.7, 5.3, 2.6),
    "gravy_mushroom": (171170, 50, 1.3, 5.5, 2.7),
    "pie_fruit": (175011, 237, 1.9, 34, 11),  # pie, apple, commercially prepared
    "espresso": (171891, 9, 0.1, 1.7, 0.2),
    "cream_whipped": (170859, 340, 2.8, 2.8, 36.1),  # heavy whipping cream
    "choc_syrup": (168835, 350, 4.6, 62.9, 8.9),
    "mashed_potato": (168555, 113, 1.9, 16.8, 4.2),
    "lasagna": (172114, 135, 7.3, 15.4, 4.9),  # lasagna with meat sauce, prepared
    "pizza_supreme": (173281, 243, 10.9, 25.6, 10.7),  # Pizza Hut 12" Super Supreme
    "hamburger": (170717, 264, 12.9, 30.3, 10.1),  # McDonald's (US) hamburger
    "water": (0, 0, 0, 0, 0),  # ice / water: weight only
}


@dataclass(frozen=True)
class Item:
    brand: str
    name: str
    label: str  # serving label, e.g. "1 meal"
    parts: tuple[tuple[str, float], ...] = ()  # estimate: (curated food id | FDC_PARTS key, g)
    official: tuple[float, float, float, float, float] | None = None  # kcal, P, C, F, Na mg
    grams: float = 0  # official serving weight (estimated)
    url: str = ""
    aliases: tuple[str, ...] = ()


ITEMS: tuple[Item, ...] = (
    # --- McDonald's Philippines: OFFICIAL (mcdonalds.com.ph, values by page order) ----------
    Item("McDonald's PH", "Burger McDo", "1 burger", official=(354, 13, 43, 14, 858),
         grams=120, url=MCD_PH.format("burgers"), aliases=("burger mcdo", "mcdo burger")),
    Item("McDonald's PH", "Cheeseburger", "1 burger", official=(324, 16, 37, 12, 715),
         grams=119, url=MCD_PH.format("burgers")),
    Item("McDonald's PH", "Double Cheeseburger", "1 burger", official=(469, 27, 39, 22, 1087),
         grams=155, url=MCD_PH.format("burgers")),
    Item("McDonald's PH", "Quarter Pounder with Cheese", "1 burger",
         official=(521, 31, 41, 25, 1080), grams=199, url=MCD_PH.format("burgers"),
         aliases=("qpc",)),
    Item("McDonald's PH", "McChicken Sandwich", "1 sandwich", official=(358, 16, 40, 16, 644),
         grams=131, url=MCD_PH.format("burgers")),
    Item("McDonald's PH", "Crispy Chicken Sandwich", "1 sandwich",
         official=(387, 16, 42, 16, 1021), grams=150, url=MCD_PH.format("burgers")),
    Item("McDonald's PH", "Big Mac", "1 burger", official=(752, 29, 59, 43, 1452), grams=219,
         url=MCD_PH.format("burgers")),
    Item("McDonald's PH", "1pc Chicken McDo with Rice", "1 meal",
         official=(504, 26, 59, 18, 1130), grams=260, url=MCD_PH.format("chicken-platters"),
         aliases=("chicken mcdo",)),
    Item("McDonald's PH", "2pc Chicken McDo with Rice", "1 meal",
         official=(809, 47, 72, 36, 2260), grams=370, url=MCD_PH.format("chicken-platters")),
    Item("McDonald's PH", "1pc Chicken McDo with McSpaghetti", "1 meal",
         official=(679, 34, 73, 28, 1836), grams=350, url=MCD_PH.format("chicken-platters")),
    Item("McDonald's PH", "Crispy Chicken Fillet with Rice", "1 meal",
         official=(363, 14, 57, 8, 844), grams=230, url=MCD_PH.format("chicken-platters")),
    Item("McDonald's PH", "Cheesy Eggdesal", "1 sandwich", official=(248, 14, 31, 7, 402),
         grams=110, url=MCD_PH.format("breakfast")),
    Item("McDonald's PH", "Sausage McMuffin with Egg", "1 sandwich",
         official=(409, 24, 37, 18, 875), grams=165, url=MCD_PH.format("breakfast")),
    Item("McDonald's PH", "Hash Browns", "1 piece", official=(135, 1, 10, 8, 271), grams=53,
         url=MCD_PH.format("breakfast")),
    Item("McDonald's PH", "2pc Hotcakes", "2 hotcakes", official=(295, 7, 55, 5, 487),
         grams=100, url=MCD_PH.format("breakfast")),
    Item("McDonald's PH", "2pc Hotcakes with Sausage", "1 meal",
         official=(392, 15, 58, 11, 837), grams=140, url=MCD_PH.format("breakfast")),
    Item("McDonald's PH", "Sausage Platter with Rice", "1 meal",
         official=(520, 25, 55, 22, 796), grams=280, url=MCD_PH.format("breakfast")),
    # --- Jollibee: ESTIMATE (no published PH nutrition) ---------------------------------------
    Item("Jollibee", "Chickenjoy 1pc", "1 piece", (("kfc_or_thigh", 140),),
         aliases=("chickenjoy", "chicken joy")),
    Item("Jollibee", "Chickenjoy 1pc with rice", "1 meal",
         (("kfc_or_thigh", 140), ("rice", 150), ("gravy_chicken", 30)),
         aliases=("chickenjoy", "chicken joy")),
    Item("Jollibee", "Jolly Spaghetti (regular)", "1 plate", (("spaghetti_pinoy", 220),),
         aliases=("jolly spaghetti",)),
    Item("Jollibee", "Yumburger", "1 burger", (("hamburger", 100),)),
    Item("Jollibee", "Burger Steak 1pc with rice", "1 meal",
         (("ground_beef", 70), ("gravy_mushroom", 60), ("rice", 150))),
    Item("Jollibee", "Peach Mango Pie", "1 pie", (("pie_fruit", 85),)),
    Item("Jollibee", "Palabok Fiesta", "1 plate", (("pancit_palabok", 280),)),
    # --- Chowking ------------------------------------------------------------------------------
    Item("Chowking", "Chao Fan (pork)", "1 plate", (("fried_rice", 250),), aliases=("chaofan",)),
    Item("Chowking", "Siopao Asado", "1 piece", (("siopao", 120),)),
    Item("Chowking", "Pork Siomai 4pc", "4 pieces", (("siomai", 100),)),
    Item("Chowking", "Halo-Halo (regular)", "1 glass", (("halo_halo", 350),)),
    Item("Chowking", "Beef Mami", "1 bowl", (("mami", 450),)),
    # --- Mang Inasal ---------------------------------------------------------------------------
    Item("Mang Inasal", "Paa Large with rice", "1 meal",
         (("chicken_inasal", 200), ("rice", 160)), aliases=("paa", "inasal")),
    Item("Mang Inasal", "Pork BBQ 2 sticks with rice", "1 meal",
         (("bbq_pork", 120), ("rice", 160))),
    Item("Mang Inasal", "Extra rice", "1 cup", (("rice", 160),), aliases=("unli rice",)),
    # --- Greenwich -----------------------------------------------------------------------------
    Item("Greenwich", "Overload pizza slice (regular)", "1 slice", (("pizza_supreme", 110),)),
    Item("Greenwich", "Lasagna Supreme", "1 serving", (("lasagna", 280),)),
    # --- KFC Philippines -----------------------------------------------------------------------
    Item("KFC PH", "1pc Chicken with rice", "1 meal",
         (("kfc_or_thigh", 135), ("rice", 150), ("gravy_chicken", 30))),
    Item("KFC PH", "Mashed Potato with gravy (regular)", "1 cup",
         (("mashed_potato", 100), ("gravy_chicken", 20))),
    # --- Max's Restaurant ----------------------------------------------------------------------
    Item("Max's", "Fried Chicken (quarter)", "1/4 chicken", (("fried_chicken", 200),)),
    Item("Max's", "Kare-Kare", "1 serving", (("kare_kare", 250),)),
    Item("Max's", "Pancit Canton", "1 serving", (("pancit_canton", 250),)),
    # --- Shakey's ------------------------------------------------------------------------------
    Item("Shakey's", "Manager's Choice pizza slice", "1 slice", (("pizza_supreme", 120),)),
    Item("Shakey's", "Mojos (regular)", "1 serving", (("fries", 200),), aliases=("mojos",)),
    # --- Starbucks Philippines (site lists Tall kcal only - macros built from USDA) ----------
    Item("Starbucks PH", "Caffè Latte Tall (whole milk)", "1 tall (12 oz)",
         (("milk_whole", 300), ("espresso", 60)), aliases=("latte",)),
    Item("Starbucks PH", "Caramel Macchiato Tall", "1 tall (12 oz)",
         (("milk_whole", 290), ("espresso", 60), ("sugar", 20))),
    Item("Starbucks PH", "Caffè Americano Tall", "1 tall (12 oz)",
         (("espresso", 60), ("water", 290)), aliases=("americano",)),
    Item("Starbucks PH", "Java Chip Frappuccino Tall", "1 tall (12 oz)",
         (("milk_whole", 150), ("water", 120), ("sugar", 30), ("choc_syrup", 15),
          ("chocolate", 10), ("cream_whipped", 15)), aliases=("frappe", "frappuccino")),
)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", F.normalize(text)).strip("_")


def _part(key: str) -> tuple[float, float, float, float]:
    if key in FDC_PARTS:
        return FDC_PARTS[key][1:]
    f = F.food(key)  # curated (synced to FDC where it is a single ingredient)
    return f.kcal, f.protein, f.carbs, f.fat


def _build(it: Item) -> Food:
    fid = f"r_{_slug(it.brand)}_{_slug(it.name)}"
    name = f"{it.brand}{SEP}{it.name}"
    if it.official is not None:
        kcal, p, c, fat, na = it.official
        k = 100 / it.grams
        return Food(fid, name, round(kcal * k, 1), round(p * k, 1), round(c * k, 1),
                    round(fat * k, 1), it.grams, it.label, OFFICIAL, OFFICIAL_UNCERTAINTY,
                    it.aliases, "restaurant", None, None, round(na * k), (), None, it.brand,
                    it.url)
    grams = sum(g for _, g in it.parts)
    tot = [0.0, 0.0, 0.0, 0.0]
    for key, g in it.parts:
        for i, v in enumerate(_part(key)):
            tot[i] += v * g / 100
    k = 100 / grams
    basis = " + ".join(f"{key} {g:g} g" for key, g in it.parts)
    return Food(fid, name, round(tot[0] * k, 1), round(tot[1] * k, 1), round(tot[2] * k, 1),
                round(tot[3] * k, 1), grams, it.label, ESTIMATE, ESTIMATE_UNCERTAINTY,
                it.aliases, "restaurant", None, None, None, (), None, it.brand,
                f"estimate from USDA FoodData Central: {basis}")


FOODS: tuple[Food, ...] = tuple(_build(it) for it in ITEMS)
BY_ID: dict[str, Food] = {f.id: f for f in FOODS}
BRANDS: tuple[str, ...] = tuple(dict.fromkeys(f.brand for f in FOODS))


def items_for(brand: str) -> list[Food]:
    return [f for f in FOODS if f.brand == brand]
