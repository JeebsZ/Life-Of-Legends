"""Local food table + fuzzy search. Pure data and functions (no Flet, no I/O).

Every value is per 100 g as eaten (cooked where it says so). `source`:
- "USDA": single ingredients, from USDA FoodData Central / SR Legacy (public domain), rounded.
- "estimate": dishes (most ulam, kakanin, street food), built from typical home recipes. These
  vary a lot by cook, so they carry a wider `uncertainty`.
`uncertainty` is the +-fraction on kcal per 100 g that the UI turns into a RANGE (never one
exact number). `portion_g` is a typical single serving, labelled `portion_label`.

Public API (also used by the on-device recognizer):
    search(query, limit=20, extra=(), brand=None) -> list[Food]  ranked, fuzzy; curated foods,
        restaurant items (core/restaurants.py) and an attached USDA databank (core/usda.py)
    match_food(name, extra=()) -> str | None          best curated id for a recognizer label
    food(food_id) / has(food_id)                       curated, restaurant or databank lookup
    brands() -> list[str]                              restaurant chains (filter for search)
    attach(source)                                     plug in the USDA databank (UI does it)
    suggestions_for(meal) -> list[str]                 time-of-day defaults (ids)

Curated "USDA" values are synced from FoodData Central by tools/foods/sync_curated.py (their
FDC ids are in foods_fdc.py).
"""

from __future__ import annotations

import dataclasses
import difflib
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from lol.core.foods_fdc import FDC_IDS

USDA = "USDA"
ESTIMATE = "estimate"
CUSTOM = "custom"
OFFICIAL = "official"  # a restaurant chain's own published numbers
SOURCE_LABELS = {USDA: "USDA FoodData Central", ESTIMATE: "estimate", CUSTOM: "my food",
                 OFFICIAL: "official"}
FDC_URL = "https://fdc.nal.usda.gov/food-details/{}/nutrients"
USDA_UNCERTAINTY = 0.08
DISH_UNCERTAINTY = 0.20
FRIED_UNCERTAINTY = 0.25
MATCH_MIN_SCORE = 62  # match_food needs at least this (0..100)


@dataclass(frozen=True)
class Food:
    id: str
    name: str
    kcal: float  # per 100 g
    protein: float  # g per 100 g
    carbs: float
    fat: float
    portion_g: float  # typical serving
    portion_label: str  # e.g. "1 cup", "1 piece"
    source: str = USDA  # "USDA" | "estimate" | "custom"
    uncertainty: float = USDA_UNCERTAINTY  # +- fraction on kcal per 100 g
    aliases: tuple[str, ...] = field(default=())
    category: str = "other"
    # optional extras (USDA databank / restaurant items)
    fiber: float | None = None
    sugar: float | None = None
    sodium_mg: float | None = None
    portions: tuple[tuple[str, float], ...] = field(default=())  # (label, grams)
    fdc_id: int | None = None
    brand: str = ""  # restaurant chain, e.g. "Jollibee"
    source_url: str = ""  # where the numbers come from (official page / FDC)


def _u(fid, name, kcal, p, c, f, g, label, cat, aliases=(), unc=USDA_UNCERTAINTY) -> Food:
    return Food(fid, name, kcal, p, c, f, g, label, USDA, unc, tuple(aliases), cat)


def _e(fid, name, kcal, p, c, f, g, label, cat, aliases=(), unc=DISH_UNCERTAINTY) -> Food:
    return Food(fid, name, kcal, p, c, f, g, label, ESTIMATE, unc, tuple(aliases), cat)


FR = FRIED_UNCERTAINTY

FOODS: tuple[Food, ...] = (
    # --- rice, bread, noodles, starches ------------------------------------------------------
    _u("rice", "White rice, cooked", 130, 2.7, 28.2, 0.3, 160, "1 cup", "staple",
       ("kanin", "plain rice", "steamed rice", "rice")),
    _u("rice_brown", "Brown rice, cooked", 123, 2.7, 25.6, 1.0, 160, "1 cup", "staple"),
    _e("sinangag", "Sinangag (garlic fried rice)", 175, 3.2, 29, 5, 180, "1 cup", "staple",
       ("garlic rice", "fried rice garlic")),
    _e("fried_rice", "Fried rice (Chinese style)", 168, 4.6, 25, 5.3, 200, "1 plate", "staple",
       ("yang chow",)),
    _e("lugaw", "Lugaw (plain rice porridge)", 46, 0.9, 10, 0.1, 350, "1 bowl", "staple",
       ("congee", "rice porridge")),
    _e("arroz_caldo", "Arroz caldo (chicken rice porridge)", 75, 4, 10, 2, 350, "1 bowl",
       "dish", ("chicken congee", "pospas")),
    _e("champorado", "Champorado (chocolate rice porridge)", 130, 2.8, 25, 2.5, 250, "1 bowl",
       "dish", ("chocolate porridge",)),
    _e("pandesal", "Pandesal", 293, 8.5, 53, 5, 30, "1 piece", "bread",
       ("pan de sal", "bread roll")),
    _u("bread_white", "White bread", 266, 8.8, 49.4, 3.3, 28, "1 slice", "bread",
       ("loaf bread", "tasty")),
    _u("bread_wheat", "Whole wheat bread", 252, 12.4, 42.7, 3.5, 32, "1 slice", "bread"),
    _e("ensaymada", "Ensaymada", 400, 8, 48, 20, 70, "1 piece", "bread"),
    _e("spanish_bread", "Spanish bread", 330, 7, 52, 10, 50, "1 piece", "bread", ("monay",)),
    _e("hopia", "Hopia", 380, 6, 58, 14, 45, "1 piece", "bread"),
    _e("siopao", "Siopao asado", 250, 9, 38, 7, 120, "1 piece", "dish", ("steamed bun",)),
    _u("oats_dry", "Rolled oats, dry", 379, 13.2, 67.7, 6.5, 40, "1/2 cup", "staple",
       ("oatmeal dry",)),
    _u("oatmeal", "Oatmeal, cooked with water", 71, 2.5, 12, 1.5, 234, "1 cup", "staple"),
    _u("pasta", "Pasta, cooked", 158, 5.8, 30.9, 0.9, 140, "1 cup", "staple",
       ("spaghetti noodles", "macaroni")),
    _e("spaghetti_pinoy", "Filipino spaghetti (sweet, with hotdog)", 150, 5.5, 21, 4.8, 250,
       "1 plate", "dish", ("jollibee spaghetti", "sweet spaghetti")),
    _e("spaghetti_meat", "Spaghetti with meat sauce", 132, 6, 18, 4, 300, "1 plate", "dish",
       ("bolognese",)),
    _e("pancit_canton", "Pancit canton (home-cooked)", 150, 7, 20, 4.5, 220, "1 plate", "dish",
       ("canton", "stir fried noodles")),
    _e("pancit_canton_instant", "Instant pancit canton (dry weight)", 462, 9, 58, 21, 80,
       "1 pack", "dish", ("lucky me", "instant canton", "instant noodles")),
    _e("pancit_bihon", "Pancit bihon", 140, 6, 22, 3.5, 220, "1 plate", "dish",
       ("bihon", "rice noodles")),
    _e("pancit_palabok", "Pancit palabok", 160, 7, 22, 5, 250, "1 plate", "dish",
       ("palabok", "pancit malabon")),
    _e("lomi", "Lomi (thick noodle soup)", 85, 4.5, 11, 2.5, 400, "1 bowl", "dish"),
    _e("mami", "Mami (noodle soup)", 60, 4, 8, 1.5, 400, "1 bowl", "dish",
       ("noodle soup",)),
    _e("instant_ramen", "Instant noodles, prepared (1 pack + broth)", 94, 2.2, 12.8, 3.7, 400,
       "1 bowl", "dish", ("pancit noodle soup", "instant mami")),  # FDC 171177 dry, 85 g in 400 g
    _u("corn", "Sweet corn, boiled", 96, 3.4, 21, 1.5, 100, "1 ear", "staple", ("mais",)),
    _u("potato", "Potato, boiled", 87, 1.9, 20.1, 0.1, 150, "1 medium", "staple", ("patatas",)),
    _u("kamote", "Sweet potato, boiled", 76, 1.4, 17.7, 0.1, 150, "1 medium", "staple",
       ("kamote", "camote", "sweet potato")),
    _e("cassava", "Cassava, boiled", 150, 1.3, 36, 0.3, 150, "1 piece", "staple",
       ("kamoteng kahoy", "balinghoy")),
    _u("fries", "French fries", 323, 3.4, 42.6, 15.5, 117, "1 medium", "snack",
       ("fries", "potato fries")),
    _u("cornflakes", "Corn flakes", 384, 5.9, 88, 0.9, 30, "1 cup", "staple", ("cereal",)),
    _u("tortilla", "Flour tortilla", 306, 8.2, 49.4, 8, 45, "1 piece", "bread"),
    # --- eggs, meat, fish --------------------------------------------------------------------
    _u("egg_boiled", "Egg, boiled", 155, 12.6, 1.1, 10.6, 50, "1 large", "protein",
       ("itlog", "hard boiled egg", "nilagang itlog")),
    _u("egg_fried", "Egg, fried", 196, 13.6, 0.8, 14.8, 46, "1 large", "protein",
       ("pritong itlog", "sunny side up", "itlog")),
    _u("egg_scrambled", "Egg, scrambled", 149, 10, 1.6, 11, 61, "1 large", "protein",
       ("scrambled egg",)),
    _e("tortang_talong", "Tortang talong (eggplant omelette)", 140, 6, 6, 10, 120, "1 piece",
       "dish", ("eggplant omelet",), FR),
    _u("chicken_breast", "Chicken breast, roasted, no skin", 165, 31, 0, 3.6, 120,
       "1 palm-size", "protein", ("manok", "chicken")),
    _u("chicken_thigh", "Chicken thigh with skin, roasted", 232, 23.3, 0, 14.7, 100,
       "1 thigh", "protein", ("chicken leg",)),
    _e("fried_chicken", "Fried chicken (with skin, breaded)", 260, 24, 8, 14, 110,
       "1 piece", "protein", ("pritong manok",), FR),
    _e("chicken_inasal", "Chicken inasal", 200, 24, 2, 11, 180, "1 leg quarter", "protein",
       ("inasal", "grilled chicken")),
    _u("chicken_nuggets", "Chicken nuggets", 302, 15.8, 15.1, 19.8, 100, "6 pieces", "snack",
       ("nuggets",)),
    _u("pork_chop", "Pork chop, grilled", 209, 25.6, 0, 11.1, 120, "1 chop", "protein",
       ("porkchop", "baboy")),
    _u("ground_pork", "Ground pork, cooked", 297, 25.7, 0, 20.8, 85, "1/2 cup", "protein",
       ("giniling",)),
    _u("ground_beef", "Ground beef (80% lean), cooked", 270, 25.8, 0, 17.8, 85, "1/2 cup",
       "protein", ("beef giniling",)),
    _u("beef_steak", "Beef steak (sirloin), grilled", 257, 26.8, 0, 15.8, 150, "1 steak",
       "protein", ("steak", "baka")),
    _u("bacon", "Bacon, cooked", 548, 35.7, 1.4, 43.3, 16, "2 slices", "protein"),
    _u("hotdog", "Hotdog", 290, 10.3, 4.2, 25.8, 45, "1 piece", "protein",
       ("frankfurter", "red hotdog", "sausage")),
    _u("ham", "Ham, sliced", 164, 16.6, 3.6, 8.8, 28, "1 slice", "protein"),
    _u("luncheon_meat", "Luncheon meat (Spam-style)", 315, 13.4, 4.6, 26.6, 56, "1 slice",
       "protein", ("spam", "maling")),
    _u("corned_beef", "Corned beef, canned", 250, 27.1, 0, 14.9, 85, "1/3 can", "protein"),
    _u("tuna_water", "Tuna, canned in water", 116, 25.5, 0, 0.8, 85, "1/2 can", "protein",
       ("tuna",)),
    _u("tuna_oil", "Tuna, canned in oil", 198, 29.1, 0, 8.2, 85, "1/2 can", "protein"),
    _u("sardines", "Sardines in tomato sauce", 185, 20.9, 0.5, 10.4, 85, "1/2 can", "protein",
       ("sardinas", "ligo", "mega sardines")),
    _u("salmon", "Salmon, cooked", 206, 22.1, 0, 12.3, 120, "1 fillet", "protein"),
    _u("tilapia", "Tilapia, baked/steamed", 128, 26.1, 0, 2.6, 120, "1 small fish", "protein"),
    _e("tilapia_fried", "Tilapia, fried", 190, 24, 2, 10, 150, "1 fish", "protein",
       ("pritong tilapia",), FR),
    _u("bangus", "Bangus (milkfish), cooked", 190, 26.3, 0, 8.6, 150, "1/2 fish", "protein",
       ("milkfish", "boneless bangus", "inihaw na bangus")),
    _e("bangus_daing", "Daing na bangus (fried)", 240, 24, 2, 15, 150, "1/2 fish", "protein",
       ("daing na bangus", "bangsilog"), FR),
    _e("tuyo", "Tuyo / daing (dried fish), fried", 290, 45, 0, 12, 30, "3 small pieces",
       "protein", ("daing", "dried fish", "tuyo", "danggit"), FR),
    _u("shrimp", "Shrimp, cooked", 99, 24, 0.2, 0.3, 85, "8 pieces", "protein",
       ("hipon", "prawns")),
    _u("squid_fried", "Squid, fried (calamares)", 175, 17.9, 7.8, 7.5, 100, "1 serving",
       "protein", ("calamares", "pusit")),
    _u("tofu", "Tofu, firm", 144, 17.3, 2.8, 8.7, 100, "1/2 block", "protein", ("tokwa",)),
    _e("tokwa_fried", "Tokwa (fried tofu)", 271, 17, 10, 20, 100, "1 block", "protein",
       ("fried tofu",), FR),
    _e("longganisa", "Longganisa, fried", 330, 15, 12, 25, 80, "2 pieces", "protein",
       ("longanisa", "longsilog", "sausage"), FR),
    _e("tocino", "Tocino, fried", 300, 17, 20, 17, 90, "1 serving", "protein",
       ("tosilog", "sweet pork")),
    _e("tapa", "Beef tapa, fried", 240, 26, 6, 12, 90, "1 serving", "protein",
       ("tapsilog", "beef tapa")),
    _e("balut", "Balut", 190, 14, 2, 14, 65, "1 egg", "protein"),
    _e("kwek_kwek", "Kwek-kwek (battered quail eggs)", 230, 10, 18, 13, 60, "5 pieces",
       "snack", ("tokneneng",), FR),
    _e("fishball", "Fishballs, fried", 180, 8, 20, 7, 80, "10 pieces", "snack",
       ("fish ball", "squidball", "kikiam")),
    # --- ulam (Filipino dishes) ----------------------------------------------------------------
    _e("adobo_chicken", "Chicken adobo", 200, 18, 2, 13, 180, "1 serving", "dish",
       ("adobong manok", "adobo")),
    _e("adobo_pork", "Pork adobo", 290, 17, 3, 23, 150, "1 serving", "dish",
       ("adobong baboy", "adobo")),
    _e("adobong_kangkong", "Adobong kangkong", 70, 3, 5, 4.5, 120, "1 serving", "dish",
       ("kangkong",)),
    _e("sinigang_pork", "Sinigang na baboy", 75, 5.5, 3, 4.5, 350, "1 bowl", "dish",
       ("sinigang", "sour soup")),
    _e("sinigang_shrimp", "Sinigang na hipon", 45, 5, 3.5, 1, 350, "1 bowl", "dish",
       ("sinigang",)),
    _e("sinigang_fish", "Sinigang na isda", 50, 6, 3, 1.5, 350, "1 bowl", "dish",
       ("sinigang na bangus",)),
    _e("tinola", "Tinola (chicken ginger soup)", 60, 6, 2, 3, 350, "1 bowl", "dish",
       ("tinolang manok", "chicken soup")),
    _e("nilaga", "Nilagang baka (beef soup)", 70, 6, 4, 3.5, 350, "1 bowl", "dish",
       ("nilaga", "beef soup", "pochero")),
    _e("bulalo", "Bulalo", 95, 8, 3, 6, 400, "1 bowl", "dish", ("bone marrow soup",)),
    _e("kare_kare", "Kare-kare", 190, 12, 6, 13, 200, "1 serving", "dish",
       ("karekare", "oxtail peanut stew")),
    _e("bistek", "Bistek Tagalog", 190, 20, 4, 10, 150, "1 serving", "dish",
       ("beef steak filipino",)),
    _e("menudo", "Menudo", 160, 10, 7, 10, 180, "1 serving", "dish"),
    _e("caldereta", "Caldereta (beef)", 180, 13, 6, 12, 180, "1 serving", "dish",
       ("kaldereta",)),
    _e("afritada", "Chicken afritada", 140, 11, 6, 8, 180, "1 serving", "dish"),
    _e("mechado", "Mechado", 180, 13, 6, 12, 180, "1 serving", "dish"),
    _e("ginataang_manok", "Ginataang manok", 180, 14, 4, 12, 180, "1 serving", "dish",
       ("chicken in coconut milk",)),
    _e("lechon", "Lechon (roast pork with skin)", 380, 22, 0, 32, 100, "1 serving", "dish",
       ("litson", "roast pig")),
    _e("lechon_kawali", "Lechon kawali", 470, 18, 1, 44, 100, "1 serving", "dish",
       ("crispy pork belly", "lechon kawali"), FR),
    _e("crispy_pata", "Crispy pata", 450, 22, 1, 40, 150, "1 serving", "dish", (), FR),
    _e("sisig", "Pork sisig", 330, 16, 4, 28, 150, "1 serving", "dish", ("sizzling sisig",),
       FR),
    _e("dinuguan", "Dinuguan", 170, 14, 3, 11, 150, "1 serving", "dish", ("blood stew",)),
    _e("bbq_pork", "Pork barbecue skewer", 260, 20, 10, 16, 60, "1 stick", "dish",
       ("inihaw", "barbecue", "bbq")),
    _e("paksiw", "Paksiw na isda", 120, 18, 2, 4.5, 150, "1 serving", "dish", ("paksiw",)),
    _e("escabeche", "Escabeche (sweet and sour fish)", 170, 15, 10, 8, 150, "1 serving",
       "dish", ("sweet and sour fish",)),
    _e("tokwat_baboy", "Tokwa't baboy", 230, 15, 5, 17, 150, "1 serving", "dish"),
    _e("laing", "Laing", 160, 4, 8, 13, 120, "1 serving", "dish", ("taro leaves",)),
    _e("pinakbet", "Pinakbet", 80, 3.5, 6, 5, 150, "1 serving", "dish", ("pakbet",)),
    _e("chopsuey", "Chopsuey", 70, 4, 6, 3.5, 180, "1 serving", "dish",
       ("chop suey", "stir fried vegetables")),
    _e("ginisang_monggo", "Ginisang monggo", 110, 7, 13, 3.5, 250, "1 bowl", "dish",
       ("monggo", "mung bean stew", "munggo")),
    _e("ginataang_kalabasa", "Ginataang kalabasa at sitaw", 100, 2, 8, 7, 150, "1 serving",
       "dish", ("squash in coconut milk",)),
    _e("ampalaya_egg", "Ginisang ampalaya with egg", 80, 4, 4, 5.5, 150, "1 serving", "dish",
       ("ampalaya",)),
    _e("lumpia_shanghai", "Lumpiang shanghai (fried)", 280, 11, 20, 17, 100, "5 pieces",
       "dish", ("lumpia", "spring roll", "shanghai"), FR),
    _e("lumpia_sariwa", "Lumpiang sariwa (fresh)", 130, 4, 18, 5, 150, "1 roll", "dish",
       ("fresh lumpia",)),
    _e("lumpia_gulay", "Lumpiang gulay (fried)", 180, 4, 20, 9.5, 70, "1 piece", "dish",
       ("lumpia", "vegetable spring roll"), FR),
    _e("siomai", "Siomai (pork, steamed)", 210, 11, 14, 12, 100, "4 pieces", "dish",
       ("shumai", "dumplings")),
    _e("embutido", "Embutido", 250, 14, 9, 18, 80, "2 slices", "dish"),
    _e("relleno", "Rellenong bangus", 210, 18, 6, 12, 150, "1 slice", "dish"),
    _e("bicol_express", "Bicol express", 330, 12, 5, 30, 150, "1 serving", "dish", (), FR),
    _e("pork_steak", "Pork steak (Filipino)", 230, 20, 5, 14, 150, "1 serving", "dish"),
    _e("pancit_molo", "Pancit molo (wonton soup)", 65, 4, 7, 2.5, 350, "1 bowl", "dish",
       ("wonton soup", "molo")),
    _e("sopas", "Sopas (macaroni soup)", 80, 4, 9, 3, 350, "1 bowl", "dish",
       ("macaroni soup",)),
    _e("goto", "Goto (tripe porridge)", 80, 4.5, 10, 2.5, 350, "1 bowl", "dish"),
    # --- vegetables, legumes, nuts -----------------------------------------------------------
    _u("kangkong", "Kangkong (water spinach), boiled", 20, 2.1, 3.7, 0.2, 100, "1 cup", "veg",
       ("water spinach",)),
    _u("pechay", "Pechay / bok choy, boiled", 12, 1.6, 1.8, 0.2, 170, "1 cup", "veg",
       ("bok choy", "petsay")),
    _u("cabbage", "Cabbage, raw", 25, 1.3, 5.8, 0.1, 90, "1 cup", "veg", ("repolyo",)),
    _u("carrot", "Carrots, raw", 41, 0.9, 9.6, 0.2, 60, "1 medium", "veg"),
    _u("tomato", "Tomato, raw", 18, 0.9, 3.9, 0.2, 120, "1 medium", "veg", ("kamatis",)),
    _u("cucumber", "Cucumber", 13.9, 0.6, 3, 0.2, 100, "1/2 medium", "veg", ("pipino",)),
    _u("eggplant", "Eggplant, cooked", 35, 0.8, 8.7, 0.2, 100, "1 cup", "veg", ("talong",)),
    _u("ampalaya", "Bitter melon, cooked", 19, 0.8, 4.3, 0.2, 125, "1 cup", "veg",
       ("ampalaya", "bitter gourd")),
    _u("squash", "Squash (kalabasa), cooked", 40, 0.9, 10.5, 0.1, 205, "1 cup", "veg",
       ("kalabasa", "pumpkin")),
    _u("sitaw", "String beans, boiled", 35, 1.9, 7.9, 0.3, 125, "1 cup", "veg",
       ("sitaw", "green beans", "baguio beans")),
    _u("broccoli", "Broccoli, boiled", 35, 2.4, 7.2, 0.4, 156, "1 cup", "veg"),
    _u("lettuce", "Lettuce", 15, 1.4, 2.9, 0.1, 50, "1 cup", "veg"),
    _u("spinach", "Spinach, raw", 23, 2.9, 3.6, 0.4, 30, "1 cup", "veg"),
    _u("onion", "Onion, raw", 40, 1.1, 9.3, 0.1, 110, "1 medium", "veg", ("sibuyas",)),
    _u("malunggay", "Malunggay (moringa) leaves", 64, 9.4, 8.3, 1.4, 20, "1/2 cup", "veg",
       ("moringa",)),
    _u("monggo_beans", "Mung beans, boiled", 105, 7, 19.1, 0.4, 200, "1 cup", "veg",
       ("mung beans",)),
    _u("chickpeas", "Chickpeas, cooked", 164, 8.9, 27.4, 2.6, 165, "1 cup", "veg",
       ("garbanzos",)),
    _u("black_beans", "Black beans, cooked", 132, 8.9, 23.7, 0.5, 170, "1 cup", "veg"),
    _u("peanuts", "Peanuts, roasted", 587, 24.4, 21.3, 49.7, 30, "1 handful", "snack",
       ("mani", "adobong mani")),
    _u("peanut_butter", "Peanut butter", 598, 22.2, 22.3, 51.4, 32, "2 tbsp", "snack"),
    _u("almonds", "Almonds", 579, 21.1, 21.6, 49.9, 28, "1 handful", "snack"),
    _u("cashews", "Cashews", 574, 15.3, 32.7, 46.4, 28, "1 handful", "snack", ("kasoy",)),
    _e("salad", "Green salad with dressing", 90, 1.5, 5, 7, 150, "1 bowl", "veg"),
    # --- fruit ---------------------------------------------------------------------------------
    _u("banana", "Banana (lakatan/latundan)", 89, 1.1, 22.8, 0.3, 118, "1 medium", "fruit",
       ("saging", "lakatan", "latundan")),
    _u("saba", "Saba banana, boiled", 121, 1.1, 29.1, 0.1, 90, "1 piece", "fruit",
       ("nilagang saging", "plantain")),
    _u("mango", "Mango, ripe", 60, 0.8, 15, 0.4, 200, "1 mango", "fruit",
       ("mangga", "manga", "carabao mango")),
    _u("apple", "Apple", 52, 0.3, 13.8, 0.2, 182, "1 medium", "fruit", ("mansanas",)),
    _u("orange", "Orange", 47, 0.9, 11.8, 0.1, 131, "1 medium", "fruit", ("dalandan",)),
    _u("papaya", "Papaya", 43, 0.5, 10.8, 0.3, 145, "1 cup", "fruit"),
    _u("pineapple", "Pineapple", 50, 0.5, 13.1, 0.1, 165, "1 cup", "fruit", ("pinya",)),
    _u("watermelon", "Watermelon", 30, 0.6, 7.5, 0.1, 280, "1 wedge", "fruit", ("pakwan",)),
    _u("grapes", "Grapes", 69, 0.7, 18.1, 0.2, 150, "1 cup", "fruit", ("ubas",)),
    _u("avocado", "Avocado", 160, 2, 8.5, 14.7, 100, "1/2 fruit", "fruit"),
    _u("jackfruit", "Jackfruit (langka)", 95, 1.7, 23.2, 0.6, 100, "5 pods", "fruit",
       ("langka",)),
    _u("guava", "Guava (bayabas)", 68, 2.5, 14.3, 0.9, 100, "2 small", "fruit", ("bayabas",)),
    _e("lanzones", "Lanzones", 60, 1, 15, 0.2, 100, "1 cup", "fruit"),
    _u("strawberries", "Strawberries", 32.7, 0.6, 8, 0.2, 150, "1 cup", "fruit"),
    _u("blueberries", "Blueberries", 57.4, 0.7, 14.6, 0.3, 150, "1 cup", "fruit"),
    _u("coconut_water", "Buko juice (coconut water)", 19, 0.7, 3.7, 0.2, 240, "1 glass",
       "drink", ("buko", "coconut water")),
    # --- dairy, fats, condiments ---------------------------------------------------------------
    _u("milk_whole", "Milk, whole", 60, 3.3, 4.6, 3.2, 244, "1 cup", "dairy", ("gatas",)),
    _u("milk_skim", "Milk, skim", 34, 3.4, 4.9, 0.1, 245, "1 cup", "dairy"),
    _u("evap_milk", "Evaporated milk", 134, 6.8, 10, 7.6, 30, "2 tbsp", "dairy"),
    _u("condensed_milk", "Condensed milk, sweetened", 321, 7.9, 54.4, 8.7, 20, "1 tbsp",
       "dairy"),
    _u("cheddar", "Cheddar cheese", 408, 23.3, 2.4, 34, 28, "1 slice", "dairy",
       ("cheese",)),
    _e("cheese_processed", "Processed cheese (Eden-style)", 300, 13, 12, 23, 20, "1 slice",
       "dairy", ("eden", "quickmelt")),
    _u("yogurt", "Yogurt, plain", 77.3, 3.8, 5.6, 4.5, 170, "1 cup", "dairy"),
    _u("greek_yogurt", "Greek yogurt, nonfat", 61, 10.3, 3.6, 0.4, 170, "1 cup", "dairy"),
    _u("butter", "Butter", 717, 0.8, 0.1, 81.1, 14, "1 tbsp", "fat", ("mantikilya",)),
    _u("oil", "Cooking oil", 884, 0, 0, 100, 14, "1 tbsp", "fat", ("mantika", "oil")),
    _u("mayonnaise", "Mayonnaise", 680, 1, 0.6, 74.8, 14, "1 tbsp", "fat", ("mayo",)),
    _u("coconut_milk", "Coconut milk (gata)", 230, 2.3, 5.5, 23.8, 60, "1/4 cup", "fat",
       ("gata",)),
    _u("sugar", "Sugar", 385, 0, 99.6, 0.3, 4, "1 tsp", "condiment", ("asukal",)),
    _u("honey", "Honey", 304, 0.3, 82.4, 0, 21, "1 tbsp", "condiment"),
    _u("soy_sauce", "Soy sauce", 53, 8.1, 4.9, 0.6, 16, "1 tbsp", "condiment", ("toyo",)),
    _u("ketchup", "Ketchup / banana ketchup", 101, 1, 27.4, 0.1, 17, "1 tbsp", "condiment"),
    _u("ice_cream", "Ice cream, vanilla", 207, 3.5, 23.6, 11, 66, "1/2 cup", "dessert",
       ("sorbetes",)),
    # --- drinks ----------------------------------------------------------------------------------
    _u("coffee_black", "Coffee, black", 1, 0.1, 0, 0, 240, "1 cup", "drink", ("kape",)),
    _e("coffee_3in1", "3-in-1 coffee mix (powder)", 440, 3, 75, 14, 20, "1 sachet", "drink",
       ("kape", "coffee mix", "nescafe")),
    _u("tea", "Tea, unsweetened", 1, 0, 0.3, 0, 240, "1 cup", "drink"),
    _u("cola", "Soft drink (cola)", 42, 0, 10.4, 0.2, 330, "1 can", "drink",
       ("coke", "soda", "softdrinks")),
    _u("orange_juice", "Orange juice", 45, 0.7, 10.4, 0.2, 248, "1 cup", "drink"),
    _e("iced_tea", "Iced tea, sweetened", 35, 0, 8.6, 0, 350, "1 glass", "drink"),
    _e("milk_tea", "Milk tea with pearls", 80, 0.8, 15, 2, 500, "1 large cup", "drink",
       ("boba", "bubble tea"), 0.3),
    _u("beer", "Beer", 43, 0.5, 3.5, 0, 330, "1 bottle", "drink", ("serbesa",)),
    _e("choco_malt", "Chocolate malt drink powder", 410, 8, 72, 9, 22, "1 sachet", "drink",
       ("milo",)),
    _e("whey", "Whey protein powder", 380, 75, 10, 5, 30, "1 scoop", "drink",
       ("protein shake",)),
    _e("calamansi_juice", "Calamansi juice, sweetened", 45, 0.1, 11, 0, 250, "1 glass",
       "drink"),
    # --- snacks, kakanin, desserts --------------------------------------------------------------
    _e("halo_halo", "Halo-halo", 150, 2.5, 28, 3.5, 350, "1 glass", "dessert",
       ("halo halo",), 0.3),
    _e("turon", "Turon", 240, 1.5, 43, 7.5, 80, "1 piece", "snack",
       ("banana lumpia",), FR),
    _e("banana_cue", "Banana cue", 210, 1, 46, 3.5, 120, "1 stick", "snack",
       ("banana q", "bananacue")),
    _e("camote_cue", "Camote cue", 190, 1, 40, 3.5, 100, "1 stick", "snack",
       ("kamote cue",)),
    _e("maruya", "Maruya (banana fritter)", 230, 2.5, 38, 8, 80, "1 piece", "snack", (), FR),
    _e("leche_flan", "Leche flan", 220, 6, 33, 7, 80, "1 slice", "dessert", ("flan",)),
    _e("buko_pie", "Buko pie", 270, 3.5, 38, 12, 110, "1 slice", "dessert"),
    _e("taho", "Taho", 75, 3, 14, 1, 250, "1 cup", "snack"),
    _e("polvoron", "Polvoron", 520, 8, 60, 28, 15, "1 piece", "dessert"),
    _u("chicharon", "Chicharon (pork rinds)", 544, 61.3, 0, 31.3, 30, "1 small pack", "snack",
       ("chicharon", "pork rinds")),
    _u("chips", "Potato chips", 532, 6.4, 53.8, 34, 30, "1 small pack", "snack"),
    _u("chocolate", "Milk chocolate", 535, 7.7, 59.4, 29.7, 40, "1 bar", "snack"),
    _u("cookies", "Chocolate chip cookies", 492, 5.1, 65.4, 24.7, 30, "3 pieces", "snack"),
    _u("crackers", "Crackers (saltine)", 418, 9.5, 74, 8.6, 25, "1 pack", "snack",
       ("skyflakes", "biscuit")),
    _u("donut", "Glazed doughnut", 421, 6.1, 47.9, 22.7, 60, "1 piece", "snack", ("donut",)),
    _u("chocolate_cake", "Chocolate cake, frosted", 389, 3.5, 52.8, 20.1, 95, "1 slice",
       "dessert", ("cake",)),
    _e("puto", "Puto", 210, 3.5, 45, 2, 40, "1 piece", "snack"),
    _e("kutsinta", "Kutsinta", 200, 1.5, 47, 0.5, 40, "1 piece", "snack", ("cuchinta",)),
    _e("bibingka", "Bibingka", 260, 5, 40, 9, 120, "1 piece", "snack"),
    _e("suman", "Suman", 190, 2.5, 38, 3, 80, "1 piece", "snack"),
    _e("biko", "Biko", 280, 3, 52, 7, 80, "1 slice", "snack"),
    _e("sapin_sapin", "Sapin-sapin", 210, 2, 40, 5, 80, "1 slice", "snack"),
    _e("cassava_cake", "Cassava cake", 260, 2.5, 42, 10, 100, "1 slice", "dessert"),
    _e("ube_halaya", "Ube halaya", 220, 2, 40, 6, 60, "2 tbsp", "dessert", ("ube jam",)),
    _e("pastillas", "Pastillas", 380, 9, 60, 11, 15, "1 piece", "dessert"),
    # --- fast food and global basics ---------------------------------------------------------
    _e("burger", "Hamburger (single patty)", 260, 13, 29, 10, 110, "1 burger", "fastfood",
       ("burger", "yumburger")),
    _e("cheeseburger", "Cheeseburger", 263, 15, 25, 12, 120, "1 burger", "fastfood"),
    _u("pizza_cheese", "Pizza, cheese", 266, 11.4, 33.3, 9.7, 107, "1 slice", "fastfood",
       ("pizza",)),
    _u("pizza_pepperoni", "Pizza, pepperoni", 282, 11.7, 32, 11.9, 111, "1 slice", "fastfood"),
    _e("sandwich_ham_cheese", "Ham and cheese sandwich", 250, 14, 25, 10, 150, "1 sandwich",
       "fastfood", ("sandwich",)),
    _e("shawarma", "Chicken shawarma wrap", 200, 12, 20, 8, 250, "1 wrap", "fastfood",
       ("shawarma rice",)),
    _e("sushi_california", "California roll", 140, 4.5, 22, 4, 200, "8 pieces", "fastfood",
       ("sushi", "maki")),
    _e("ramen", "Ramen (restaurant)", 90, 4.5, 9, 4, 600, "1 bowl", "fastfood",
       ("tonkotsu",), 0.3),
    _e("burrito", "Burrito (beef and beans)", 200, 9, 25, 7, 250, "1 burrito", "fastfood"),
    _e("fried_chicken_meal", "Fried chicken with rice (fast food)", 210, 12, 22, 8, 300,
       "1 meal", "fastfood", ("1pc chicken meal",), FR),
)

FOODS = tuple(dataclasses.replace(f, fdc_id=FDC_IDS[f.id],
                                  source_url=FDC_URL.format(FDC_IDS[f.id]))
              if f.id in FDC_IDS else f for f in FOODS)
_BY_ID: dict[str, Food] = {f.id: f for f in FOODS}
_sources: list[Any] = []  # attached databanks: has(id), food(id), search(q, n)->[(score, Food)]

# time-of-day quick picks (ids), shown when Luma couldn't identify a photo
SUGGESTIONS: dict[str, tuple[str, ...]] = {
    "breakfast": ("pandesal", "sinangag", "egg_fried", "tapa", "longganisa", "tocino",
                  "coffee_3in1", "champorado", "oatmeal", "banana"),
    "lunch": ("rice", "adobo_chicken", "sinigang_pork", "tinola", "fried_chicken",
              "pancit_canton", "tilapia_fried", "chopsuey", "ginisang_monggo", "bangus"),
    "dinner": ("rice", "adobo_pork", "sinigang_pork", "kare_kare", "tinola", "bistek",
               "lechon_kawali", "pinakbet", "bangus_daing", "chicken_inasal"),
    "snack": ("banana", "turon", "banana_cue", "taho", "halo_halo", "puto", "mango",
              "fishball", "crackers", "milk_tea"),
}


def _restaurants() -> Any:
    from lol.core import restaurants  # lazy: restaurants builds its items from this module

    return restaurants


def attach(source: Any) -> None:
    """Plug in a databank (core/usda.LazyUsda). Idempotent."""
    if source not in _sources:
        _sources.append(source)


def detach_all() -> None:
    _sources.clear()


def food(food_id: str) -> Food:
    """Curated, restaurant or databank food by id (KeyError if unknown)."""
    if food_id in _BY_ID:
        return _BY_ID[food_id]
    r = _restaurants().BY_ID.get(food_id)
    if r is not None:
        return r
    for src in _sources:
        if src.has(food_id):
            return src.food(food_id)
    raise KeyError(food_id)


def has(food_id: str) -> bool:
    if not food_id:
        return False
    if food_id in _BY_ID or food_id in _restaurants().BY_ID:
        return True
    return any(src.has(food_id) for src in _sources)


def brands() -> list[str]:
    """Restaurant chains: PH chains first (curated), then databank brands (USDA, US menus)."""
    out = list(_restaurants().BRANDS)
    for src in _sources:
        for b in getattr(src, "brands", list)():
            if b not in out:
                out.append(b)
    return out


def suggestions_for(meal: str) -> list[str]:
    return list(SUGGESTIONS.get(meal, SUGGESTIONS["snack"]))


# --- search --------------------------------------------------------------------------------------
_PUNCT = re.compile(r"[^a-z0-9 ]+")


def normalize(text: str) -> str:
    """Lowercase, no accents, punctuation -> spaces, single spaces ('Kare-kare' -> 'kare kare')."""
    t = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    return " ".join(_PUNCT.sub(" ", t.lower()).split())


def _score_text(q: str, text: str) -> float:
    """0..100 for one candidate string (already normalized)."""
    if not q or not text:
        return 0.0
    if text == q:
        return 100.0
    if text.startswith(q):
        return 92.0
    words = text.split()
    q_words = q.split()
    if all(any(w.startswith(qw) for w in words) for qw in q_words):
        return 85.0 if words[0].startswith(q_words[0]) else 80.0
    if q in text:
        return 72.0
    # typos: compare against each word and against the whole text
    best = difflib.SequenceMatcher(None, q, text).ratio()
    for w in words:
        best = max(best, difflib.SequenceMatcher(None, q, w).ratio() - 0.05)
    return best * 75.0 if best >= 0.72 else 0.0


def score(query: str, f: Food) -> float:
    q = normalize(query)
    best = _score_text(q, normalize(f.name))
    for a in f.aliases:
        best = max(best, _score_text(q, normalize(a)) - 1)  # names win ties over aliases
    return best


def search(query: str, limit: int = 20, extra: Iterable[Food] = (),
           brand: str | None = None) -> list[Food]:
    """Foods matching `query`, best first. `extra`: the user's own foods (searched too, and
    ranked first on ties). Curated foods and restaurant items come before databank hits of
    the same score. `brand`: only that chain's items (an empty query then lists them all).
    Empty query without a brand -> []."""
    q = normalize(query)
    if brand:
        pool = [f for f in _restaurants().FOODS if f.brand == brand]
        for src in _sources:
            pool += list(getattr(src, "brand_items", lambda b: [])(brand))
        if not q:
            return pool[:limit] if limit else pool
        hits = [(score(query, f), i, f) for i, f in enumerate(pool)]
        hits = [h for h in hits if h[0] > 0]
        hits.sort(key=lambda t: (-t[0], t[1]))
        return [f for _, _, f in hits[:limit]]
    if not q:
        return []
    pool = [*extra, *FOODS, *_restaurants().FOODS]
    scored = [(score(query, f) + 0.5, i, f) for i, f in enumerate(pool)]
    hits = [(s, i, f) for s, i, f in scored if s > 0.5]
    n = len(pool)
    for src in _sources:
        for j, (s, f) in enumerate(src.search(query, limit)):
            hits.append((s, n + j, f))
        n += limit
    hits.sort(key=lambda t: (-t[0], t[1]))
    out, seen = [], set()
    for _, _, f in hits:
        if f.id not in seen:
            seen.add(f.id)
            out.append(f)
        if len(out) >= limit:
            break
    return out


def match_food(name: str, extra: Iterable[Food] = ()) -> str | None:
    """The best food id for a free-text label (e.g. a recognizer's 'chicken adobo'), or None
    if nothing is a confident match."""
    extra = list(extra)
    pool = [*extra, *FOODS]
    best = max(((score(name, f), -i, f) for i, f in enumerate(pool)),
               key=lambda t: (t[0], t[1]), default=None)
    if best is None or best[0] < MATCH_MIN_SCORE:
        return None
    return best[2].id
