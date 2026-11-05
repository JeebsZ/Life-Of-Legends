"""USDA databank loader/search, curated-value sync, and restaurant (brand) items."""

import gzip
import json
from datetime import date
from pathlib import Path

import pytest

from lol.core import foods, restaurants, usda
from lol.core.foods_fdc import FDC_IDS
from lol.core.game import Game

ASSET = Path(__file__).resolve().parents[1] / "src/assets/data/usda_foods.json.gz"
D = date(2026, 11, 5)

MINI = {
    "v": 1, "built": "2026-11-05", "sources": [], "credit": "USDA FDC",
    "cats": ["Fast Foods", "Fruits", "Poultry"],
    "foods": [
        [173944, "Bananas, raw", 1, 89, 1.1, 22.8, 0.3, 2.6, 12.2, 1,
         [["1 medium (7\" to 7-7/8\" long)", 118], ["1 cup, sliced", 150]]],
        [171477, "Chicken, broilers or fryers, breast, meat only, cooked, roasted", 2, 165, 31,
         0, 3.6, 0, None, 74, [["1 cup, chopped", 140]]],
        [170720, "McDONALD'S, BIG MAC", 0, 257, 11.8, 20.1, 15, 1.6, 4, 460,
         [["1 item 7.6 oz", 219]]],
        [170346, "KFC, Fried Chicken, ORIGINAL RECIPE, Thigh, meat and skin with breading", 0,
         269, 18.9, 8.5, 17.7, None, None, None, []],
    ],
}


@pytest.fixture
def mini(tmp_path: Path) -> Path:
    path = tmp_path / "mini.json.gz"
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        json.dump(MINI, fh)
    return path


@pytest.fixture
def attached(mini: Path):
    src = usda.LazyUsda(mini)
    foods.detach_all()
    foods.attach(src)
    yield src
    foods.detach_all()


# --- loader --------------------------------------------------------------------------------------
def test_load_and_food_fields(mini: Path):
    db = usda.load(mini)
    assert len(db) == 4
    f = db.food("u173944")
    assert f.name == "Bananas, raw" and f.kcal == 89 and f.category == "Fruits"
    assert f.fiber == 2.6 and f.sugar == 12.2 and f.sodium_mg == 1
    assert f.portion_g == 118 and f.portions[1] == ("1 cup, sliced", 150.0)
    assert f.source == foods.USDA and f.fdc_id == 173944 and "173944" in f.source_url
    no_portion = db.food("u170346")
    assert no_portion.portion_g == 100 and no_portion.portion_label == "100 g"
    assert not db.has("u1") and not db.has("rice") and not db.has("ux")
    with pytest.raises(KeyError):
        db.food("u999")


def test_search_prefix_typo_and_ranking(mini: Path):
    db = usda.load(mini)
    assert [f.id for _, f in db.search("banana")] == ["u173944"]
    assert db.search("chick breast roast")[0][1].fdc_id == 171477  # word prefixes, any order
    assert db.search("bananna")[0][1].fdc_id == 173944  # typo -> vocabulary fallback
    assert db.search("zzzz") == []
    assert db.search("") == []


def test_brand_tagging(mini: Path):
    db = usda.load(mini)
    assert db.brands() == ["McDonald's (US)", "KFC (US)"]
    assert [f.fdc_id for f in db.brand_items("KFC (US)")] == [170346]
    assert db.food("u170720").brand == "McDonald's (US)"
    assert db.food("u173944").brand == ""


def test_lazy_loads_once_and_survives_missing_file(mini: Path, tmp_path: Path):
    lz = usda.LazyUsda(mini)
    assert not lz.loaded
    assert lz.has("u173944") and lz.loaded
    gone = usda.LazyUsda(tmp_path / "nope.json.gz")
    assert gone.search("banana") == [] and not gone.has("u173944") and gone.error


def test_foods_registry_game_items_and_brand_filter(attached):
    g = Game()
    assert foods.has("u173944") and foods.food("u173944").kcal == 89
    item = g.make_item("u173944")  # databank food -> a meal item with a range
    assert item.grams == 118 and item.kcal == pytest.approx(105.0, abs=0.1)
    assert item.kcal_low < item.kcal < item.kcal_high
    names = [f.name for f in g.search_foods("banana")]
    assert names[0].startswith("Banana")  # curated first, databank after
    assert "Bananas, raw" in names
    assert "KFC (US)" in foods.brands() and "Jollibee" in foods.brands()
    kfc = g.search_foods("", 50, brand="KFC (US)")
    assert [f.fdc_id for f in kfc] == [170346]
    g.add_meal(D, "lunch", [item], D)
    assert g.recent_food_ids() == ["u173944"]


# --- the real asset ------------------------------------------------------------------------------
@pytest.mark.skipif(not ASSET.exists(), reason="databank asset not built")
def test_real_asset_size_count_and_speed():
    import time

    assert ASSET.stat().st_size <= 1_500_000
    db = usda.load(ASSET)
    assert len(db) > 7000
    assert db.meta["sources"][0]["release"] == "2026-10-29"
    t = time.perf_counter()
    for q in ("chicken breast", "rice", "brocoli", "milk whole", "egg"):
        assert db.search(q, 20)
    assert (time.perf_counter() - t) / 5 < 0.1  # well under 100 ms per search on a PC


@pytest.mark.skipif(not ASSET.exists(), reason="databank asset not built")
def test_curated_usda_values_match_the_asset():
    db = usda.load(ASSET)
    curated = [f for f in foods.FOODS if f.source == foods.USDA]
    assert len(curated) == len(FDC_IDS) >= 100
    for f in curated:
        row = db.food(f"u{FDC_IDS[f.id]}")
        assert (f.kcal, f.protein, f.carbs, f.fat) == pytest.approx(
            (row.kcal, row.protein, row.carbs, row.fat), abs=0.051), f.id
        assert f.fdc_id == FDC_IDS[f.id] and "fdc.nal.usda.gov" in f.source_url


# --- restaurants ---------------------------------------------------------------------------------
def test_restaurant_items_are_labelled_and_unique():
    ids = [f.id for f in restaurants.FOODS]
    assert len(ids) == len(set(ids)) >= 40
    for want in ("Jollibee", "McDonald's PH", "Chowking", "Mang Inasal", "Greenwich", "KFC PH",
                 "Max's", "Shakey's", "Starbucks PH"):
        assert want in restaurants.BRANDS
    for f in restaurants.FOODS:
        assert f.name.startswith(f.brand + restaurants.SEP)
        assert f.source in (restaurants.OFFICIAL, foods.ESTIMATE)
        assert f.source_url
        if f.source == foods.ESTIMATE:
            assert f.uncertainty >= 0.3 and "USDA" in f.source_url
        else:  # only chains that publish numbers may be "official"
            assert f.brand == "McDonald's PH" and f.source_url.startswith(
                "https://www.mcdonalds.com.ph/")


def test_official_items_keep_published_kcal_per_serving():
    by_name = {f.name: f for f in restaurants.FOODS}
    big_mac = by_name["McDonald's PH — Big Mac"]
    assert big_mac.kcal * big_mac.portion_g / 100 == pytest.approx(752, abs=0.2)
    one_pc = by_name["McDonald's PH — 1pc Chicken McDo with Rice"]
    assert one_pc.kcal * one_pc.portion_g / 100 == pytest.approx(504, abs=0.2)
    assert one_pc.sodium_mg == round(1130 * 100 / one_pc.portion_g)


def test_estimates_are_sums_of_their_usda_parts():
    joy = next(f for f in restaurants.FOODS if f.name == "Jollibee — Chickenjoy 1pc with rice")
    thigh = restaurants.FDC_PARTS["kfc_or_thigh"][1]
    gravy = restaurants.FDC_PARTS["gravy_chicken"][1]
    want = thigh * 1.4 + foods.food("rice").kcal * 1.5 + gravy * 0.3
    assert joy.kcal * joy.portion_g / 100 == pytest.approx(want, abs=0.5)


def test_brand_search_and_game_items():
    g = Game()
    assert foods.search("chickenjoy")[0].brand == "Jollibee"
    jb = foods.search("", 0, brand="Jollibee")
    assert jb and all(f.brand == "Jollibee" for f in jb)
    assert [f.name for f in foods.search("rice", 10, brand="Mang Inasal")]
    it = g.make_item(jb[0].id)
    assert it.source == "db" and it.kcal_high - it.kcal_low > it.kcal * 0.5  # wide range
    assert foods.has(jb[0].id) and foods.food(jb[0].id).brand == "Jollibee"
    assert foods.match_food("chickenjoy") != jb[0].id  # recognizer matching stays curated
