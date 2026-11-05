"""Body + Meals game API, foods search, recognizer boundary and schema 5 migration."""

import copy
import json
from datetime import date, timedelta

import pytest

from lol.core import foods, nutrition, storage
from lol.core.body import MEAL_DAILY_XP_CAP, MEAL_LOG_XP, WEIGHT_LOG_XP, meal_for_hour
from lol.core.game import Game
from lol.core.models import MealItem
from lol.core.recognize import Candidate, ManualRecognizer, Recognizer, confidence_label

D = date(2026, 11, 4)


def _body_game() -> Game:
    g = Game()
    g.set_body(height_cm=175, sex="male", activity="moderate")
    g.set_age(30, D)
    g.log_weight(90, "kg", D)
    return g


# --- foods ---------------------------------------------------------------------------------------
def test_food_table_shape():
    assert 150 <= len(foods.FOODS) <= 250
    assert len({f.id for f in foods.FOODS}) == len(foods.FOODS)
    for f in foods.FOODS:
        assert f.source in (foods.USDA, foods.ESTIMATE)
        assert 0 <= f.kcal <= 900 and f.portion_g > 0 and 0 < f.uncertainty < 0.5
        if f.id == "beer":  # alcohol carries the kcal
            continue
        # macros roughly add up to the kcal (fibre aside)
        est = f.protein * 4 + f.carbs * 4 + f.fat * 9
        assert est == pytest.approx(f.kcal, rel=0.25, abs=25), f.id
    for meal_ids in foods.SUGGESTIONS.values():
        assert all(foods.has(i) for i in meal_ids)
    for must in ("rice", "sinangag", "adobo_chicken", "sinigang_pork", "tinola", "kare_kare",
                 "lechon_kawali", "pancit_canton", "pancit_bihon", "lumpia_shanghai", "tapa",
                 "longganisa", "tocino", "tuyo", "bangus", "tilapia", "pandesal",
                 "champorado", "arroz_caldo", "halo_halo", "turon", "banana", "mango"):
        assert foods.has(must), must


def test_search_fuzzy_aliases_accents():
    assert foods.search("adobo")[0].id.startswith("adobo")
    assert foods.search("kanin")[0].id == "rice"
    assert foods.search("sinigan")[0].id.startswith("sinigang")  # typo-ish prefix
    assert foods.search("KARE-KARE")[0].id == "kare_kare"
    assert foods.search("lechn kawali")[0].id == "lechon_kawali"  # typo
    assert foods.search("") == []
    assert foods.match_food("chicken adobo") == "adobo_chicken"
    assert foods.match_food("zzqqxx") is None


def test_recognizer_protocol():
    r = ManualRecognizer()
    assert isinstance(r, Recognizer) and r.recognize("x.jpg") == []
    assert confidence_label(0.9) == "high" and confidence_label(0.5) == "medium"
    assert confidence_label(0.1) == "low" and confidence_label(None) == "low"


def test_meal_for_hour():
    assert [meal_for_hour(h) for h in (7, 12, 16, 19, 23)] == [
        "breakfast", "lunch", "snack", "dinner", "snack"]


# --- body ----------------------------------------------------------------------------------------
def test_weight_log_xp_capped_per_day_and_same_day_updates():
    g = Game()
    c = g.log_weight(200, "lb", D)
    assert c.xp == WEIGHT_LOG_XP and c.path_id == "monk"
    w = g.latest_weight()
    assert w.kg == pytest.approx(90.72, abs=0.01)
    again = g.log_weight(198, "lb", D)  # same day -> updates, no XP
    assert again.xp == 0 and len(g.weights()) == 1 and again.ref_id == w.id
    back = g.log_weight(91, "kg", D, day=D - timedelta(days=3))  # back-fill: no 2nd XP today
    assert back.xp == 0 and len(g.weights()) == 2
    assert g.weights()[0].day == (D - timedelta(days=3)).isoformat()
    assert g.log_weight(90, "kg", D + timedelta(days=1)).xp == WEIGHT_LOG_XP
    with pytest.raises(ValueError):
        g.log_weight(5, "kg", D)
    g.delete_weight(w.id)
    assert len(g.weights()) == 2


def test_body_status_and_missing():
    g = Game()
    st = g.body_status(D)
    assert not st["ready"] and set(st["missing"]) == {"weight", "height", "age", "sex"}
    with pytest.raises(ValueError, match="needs"):
        g.propose_plan(D)
    g = _body_game()
    st = g.body_status(D)
    assert st["ready"] and st["bmi"] == pytest.approx(29.4) and st["age"] == 30
    assert st["bmi_category"] == "Overweight range"
    with pytest.raises(ValueError):
        g.set_body(height_cm=40)
    with pytest.raises(ValueError):
        g.set_body(sex="robot")
    g.set_body(sex="unspecified")
    assert g.body.sex == "unspecified"


def test_propose_accept_clear_plan():
    g = _body_game()
    p = g.propose_plan(D, goal_kg=80, pace="steady")
    assert g.body.plan is None  # a proposal is not saved
    saved = g.accept_plan(p, D)
    assert g.body.plan is saved and saved.target_kcal == p.target_kcal
    assert saved.est_date == p.est_date.isoformat() and g.body.goal_kg == 80
    assert saved.protein_g == list(p.macros.protein_g)
    with pytest.raises(nutrition.PlanRefused):
        g.propose_plan(D, goal_kg=50)
    g.clear_plan()
    assert g.body.plan is None and g.body.goal_kg is None


# --- meals ---------------------------------------------------------------------------------------
def test_make_item_and_regram_with_scale():
    g = Game()
    it = g.make_item("rice")  # typical portion, 160 g
    assert it.grams == 160 and it.kcal == pytest.approx(208)
    assert it.kcal_low < it.kcal < it.kcal_high
    scaled = g.regram(it, 200, from_scale=True)
    assert scaled.kcal == pytest.approx(260) and scaled.from_scale
    assert (scaled.kcal_high - scaled.kcal_low) / scaled.kcal < (
        (it.kcal_high - it.kcal_low) / it.kcal)  # scale grams -> narrower range
    m = g.manual_item("Lola's cake", 120, 400, 5, 50, 18)
    m2 = g.regram(m, 60, from_scale=False)
    assert m2.kcal == pytest.approx(200) and m2.protein == pytest.approx(2.5)
    with pytest.raises(ValueError):
        g.make_item("rice", 0)
    with pytest.raises(KeyError):
        g.make_item("unicorn")


def test_add_meal_xp_cap_totals_history():
    g = Game()
    items = [g.make_item("rice"), g.make_item("adobo_chicken")]
    total_xp = 0
    for meal in ("breakfast", "lunch", "dinner", "snack"):
        total_xp += g.add_meal(D, meal, items, D).xp
    assert total_xp == MEAL_DAILY_XP_CAP and MEAL_LOG_XP <= MEAL_DAILY_XP_CAP
    t = g.day_totals(D)
    assert t["count"] == 8 and t["kcal_low"] < t["kcal"] < t["kcal_high"]
    assert [m.meal for m in g.meals_on(D)] == ["breakfast", "lunch", "dinner", "snack"]
    hist = g.meal_history(D - timedelta(days=2), D)
    assert len(hist) == 3 and hist[0][1] == 0 and hist[-1][4] == 4
    with pytest.raises(ValueError):
        g.add_meal(D, "brunch", items, D)
    with pytest.raises(ValueError):
        g.add_meal(D, "lunch", [], D)
    m = g.meals_on(D)[0]
    g.edit_meal(m.id, meal="snack", items=[g.make_item("banana")])
    assert g.meal(m.id).items[0].food_id == "banana"
    gone = g.delete_meal(m.id)
    assert gone.id == m.id and len(g.meals_on(D)) == 3


def test_meal_items_are_copied_not_shared():
    g = Game()
    it = g.make_item("rice")
    g.add_meal(D, "lunch", [it], D)
    it.grams = 999
    assert g.meals_on(D)[0].items[0].grams == 160


def test_custom_foods_favorites_recents_suggestions():
    g = Game()
    cf = g.add_custom_food("Mama's adobo", 210, 17, 3, 14, 200, "1 bowl")
    assert g.search_foods("mama")[0].id == cf.id
    item = g.make_item(cf.id)
    assert item.source == "custom" and item.kcal == pytest.approx(420)
    assert g.toggle_favorite(cf.id) and g.is_favorite(cf.id)
    assert g.favorite_foods()[0].id == cf.id
    g.add_meal(D, "dinner", [g.make_item("bangus")], D)
    assert g.recent_food_ids() == ["bangus"]
    sug = [f.id for f in g.food_suggestions("breakfast")]
    assert sug[:2] == [cf.id, "bangus"] and "pandesal" in sug
    g.delete_custom_food(cf.id)
    assert not g.is_favorite(cf.id)
    with pytest.raises(ValueError):
        g.add_custom_food("", 100)
    with pytest.raises(KeyError):
        g.toggle_favorite("nope")


def test_items_from_candidates():
    g = Game()
    items = g.items_from_candidates([
        Candidate("chicken adobo", 0.8, None, 200),
        Candidate("rice", 0.9, "rice", None),
        Candidate("mystery stew", 0.3),
    ])
    assert items[0].food_id == "adobo_chicken" and items[0].grams == 200
    assert items[0].source == "scan" and items[0].confidence == 0.8
    assert items[1].grams == 160
    assert items[2].food_id is None and items[2].kcal == 0
    assert g.items_from_candidates(ManualRecognizer().recognize("p.jpg")) == []


def test_kcal_left_needs_plan_and_opt_in():
    g = _body_game()
    assert g.kcal_left(D) is None
    g.accept_plan(g.propose_plan(D, 80), D)
    assert g.kcal_left(D) is None  # tracking is opt-in (off by default)
    g.set_nutrition(calorie_tracking=True)
    g.add_meal(D, "lunch", [g.make_item("rice")], D)
    left = g.kcal_left(D)
    assert left["left_low"] < left["left_high"] < left["target"]


# --- schema 5 ------------------------------------------------------------------------------------
def _schema4_raw() -> dict:
    """A schema 4 save as v1.3 wrote it (no schema-5 keys at all)."""
    g = Game()
    g.add_water(250, D)
    g.log_sleep(D - timedelta(days=1), "23:00", "07:00", D)
    g.set_module("energy", False)
    raw = storage.to_dict(g.data)
    raw["schema"] = 4
    for key in ("body", "weights", "meals", "custom_foods", "favorite_foods"):
        raw.pop(key)
    raw["profile"].pop("nutrition")
    raw["profile"]["modules"] = {k: v for k, v in raw["profile"]["modules"].items()
                                 if k not in ("body", "meals")}
    return raw


def test_schema4_migrates_to_5_with_defaults(tmp_path):
    raw = _schema4_raw()
    before = copy.deepcopy(raw)
    data = storage.from_dict(raw)
    out = storage.to_dict(data)
    assert out["schema"] == 5
    for key in ("water", "sleep", "quests", "bills"):
        assert out[key] == before[key]
    assert data.profile.modules["energy"] is False  # kept
    assert data.profile.modules["body"] and data.profile.modules["meals"]
    n = data.profile.nutrition
    assert (n.calorie_tracking, n.today_chip, n.keep_photos) == (False, False, False)
    assert data.body.plan is None and data.body.height_cm is None
    assert (data.weights, data.meals, data.custom_foods, data.favorite_foods) == ([], [], [], [])
    path = tmp_path / "save.json"
    storage.save(data, path)
    assert storage.load(path) == data


@pytest.mark.parametrize("raw", [
    {"name": "A", "level": 2, "xp": 5, "quests": [{"title": "Run", "xp": 30, "done": True}]},
    {"schema": 1, "profile": {"name": "B"}},
    {"schema": 2, "profile": {"name": "C"}, "side_quests": []},
    {"schema": 3, "profile": {"name": "D"}},
])
def test_older_saves_reach_schema5(raw):
    data = storage.from_dict(raw, D)
    assert storage.to_dict(data)["schema"] == 5
    assert data.profile.nutrition.calorie_tracking is False and data.meals == []


def test_schema5_round_trip_backup_csv(tmp_path):
    g = _body_game()
    g.accept_plan(g.propose_plan(D, 80), D)
    g.set_nutrition(calorie_tracking=True, keep_photos=True)
    cf = g.add_custom_food("Mama's adobo", 210, 17, 3, 14)
    g.toggle_favorite(cf.id)
    g.toggle_favorite("rice")
    g.add_meal(D, "lunch", [g.make_item("rice", 180, from_scale=True), g.make_item(cf.id),
                            g.manual_item("Soup", 300, 90)], D, time="12:30", photo="ml9.jpg")
    path = tmp_path / "save.json"
    g.save(path)
    loaded = Game.load(path)
    assert loaded.data == g.data
    assert isinstance(loaded.data.meals[0].items[0], MealItem)
    assert loaded.body.plan.protein_g == g.body.plan.protein_g
    assert storage.import_json(storage.export_json(g.data)) == g.data
    s = storage.summary(g.data)
    assert (s["weight_entries"], s["meals"], s["custom_foods"]) == (1, 1, 1)
    csvs = storage.export_csv(g.data)
    assert csvs["meal_items.csv"].count("\n") == 1 + 3
    assert "Mama's adobo" in csvs["custom_foods.csv"] and "90.0" in csvs["weights.csv"]
    # new ids never collide with loaded ones
    assert loaded._new_id("x") not in {m.id for m in loaded.data.meals}


@pytest.mark.parametrize("bad", [
    {"schema": 5, "meals": {"a": 1}},
    {"schema": 5, "favorite_foods": [{"x": 1}]},
    {"schema": 5, "body": []},
    {"schema": 5, "weights": [{"id": "wt1", "day": "nope", "kg": 80}]},
    {"schema": 5, "meals": [{"id": "m1", "day": "2026-11-04"}, {"id": "m1", "day": "2026-11-04"}]},
])
def test_import_rejects_bad_schema5_data(bad):
    with pytest.raises(ValueError):
        storage.import_json(json.dumps(bad))


def test_photo_helpers(tmp_path, monkeypatch):
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path))
    name = storage.save_photo("ml1/../x.jpg", b"jpeg")
    assert "/" not in name and storage.photo_path(name).read_bytes() == b"jpeg"
    storage.delete_photo(name)
    assert storage.photo_path(name) is None
