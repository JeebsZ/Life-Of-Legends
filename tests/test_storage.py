import json
from datetime import date

import pytest

from lol.core import storage
from lol.core.game import COINS_BY_DIFFICULTY, Game
from lol.core.models import SaveData

D = date(2026, 11, 4)

V0 = {
    "name": "Jarvin",
    "level": 3,
    "xp": 42,
    "quests": [
        {"title": "Walk 5k", "xp": 40, "stat": "health", "done": True},
        {"title": "Read", "xp": 10, "stat": "mind", "done": False},
        {"title": "Call mom", "xp": 15, "stat": "social", "done": True},
        {"title": "Budget", "xp": 20, "stat": "wealth", "done": False},
    ],
}


def _full_game() -> Game:
    g = Game()
    g.profile.name = "Jarvin"
    q = g.add_quest("Stretch", "warrior", kind="daily", note="gentle", today=D)
    g.complete_quest(q.id, D)
    g.add_quest("Cook", "chef", difficulty=2, today=D, minutes=30)
    g.pay_bill(g.add_bill("Rent", 8000.5, D, repeat="monthly").id, D)
    g.profile.coins += 500
    g.buy_theme("royal")
    g.set_theme("royal")
    g.redeem(g.add_reward("Jollibee meal", 50).id, D)
    g.add_log("sleep", "ok", 420, today=D)
    return g


def test_save_load_roundtrip(tmp_path):
    g = _full_game()
    path = g.save(tmp_path / "save.json")
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["schema"] == storage.SCHEMA == 5 and "legacy" not in raw
    assert raw["quests"][0]["done_on"] == ["2026-11-04"]
    assert Game.load(path).data == g.data


def test_atomic_save_leaves_no_tmp(tmp_path):
    path = tmp_path / "save.json"
    Game().save(path)
    _full_game().save(path)
    assert [p.name for p in tmp_path.iterdir()] == ["save.json"]


def test_load_missing_file_gives_fresh_game(tmp_path):
    assert storage.load(tmp_path / "nope.json") == SaveData()


def test_load_ignores_unknown_and_fills_missing_fields(tmp_path):
    path = tmp_path / "save.json"
    path.write_text(json.dumps({
        "schema": 1,
        "profile": {"name": "A", "coins": 7, "future_field": 1},
        "quests": [{"id": "q1", "title": "T", "path_id": "chef", "extra": True}],
    }), encoding="utf-8")
    data = storage.load(path)
    assert data.profile.name == "A" and data.profile.coins == 7
    assert data.profile.theme_id == "ember" and data.quests[0].done_on == []  # pre-Arcane save


def test_old_save_keeps_its_theme_and_gains_arcane(tmp_path):
    path = tmp_path / "save.json"
    for active, owned in (("ember", ["ember"]), ("royal", ["ember", "royal"])):
        path.write_text(json.dumps({
            "schema": 1, "profile": {"theme_id": active, "owned_themes": owned},
        }), encoding="utf-8")
        p = Game.load(path).profile
        assert p.theme_id == active  # active theme unchanged
        assert p.owned_themes == [*owned, "arcane", "rose"]  # free themes added


def test_new_save_starts_in_arcane_owning_ember(tmp_path):
    g = Game.load(tmp_path / "missing.json")
    assert g.profile.theme_id == "arcane"
    assert g.profile.owned_themes == ["arcane", "ember", "rose"]
    path = g.save(tmp_path / "save.json")
    assert Game.load(path).profile.owned_themes == ["arcane", "ember", "rose"]  # no duplicates


def test_newer_schema_is_refused():
    with pytest.raises(ValueError):
        storage.from_dict({"schema": 99})


def test_v0_migration_keeps_everything():
    data = storage.from_dict(V0, today=D)
    p = data.profile
    assert (p.name, p.level, p.xp, p.coins) == ("Jarvin", 3, 42, 0)
    assert [q.title for q in data.quests] == ["Walk 5k", "Read", "Call mom", "Budget"]
    assert [q.path_id for q in data.quests] == [
        "warrior", "scholar", storage.V0_DEFAULT_PATH, "steward"
    ]
    assert [q.xp for q in data.quests] == [40, 10, 15, 20]
    assert all(q.kind == "once" for q in data.quests)
    assert [bool(q.done_on) for q in data.quests] == [True, False, True, False]
    assert len({q.id for q in data.quests}) == 4
    assert data.legacy == V0  # raw v0 kept verbatim
    assert p.path_xp == {"warrior": 40 + 15, "monk": 0}  # done XP credited to its Path


def test_v0_migrated_game_plays(tmp_path):
    g = Game(storage.from_dict(V0, today=D))
    read = next(q for q in g.quests if q.title == "Read")
    walk = next(q for q in g.quests if q.title == "Walk 5k")
    assert g.complete_quest(walk.id, D).xp == 0  # already done in v0: no double XP
    c = g.complete_quest(read.id, D)
    assert c.xp == 10 and c.coins == COINS_BY_DIFFICULTY[1]
    new = g.add_quest("New", "chef", today=D)
    assert new.id not in {q.id for q in g.quests if q is not new}


def test_v0_hero_json_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path))
    hero = tmp_path / "hero.json"
    hero.write_text(json.dumps(V0), encoding="utf-8")

    g = Game.load(today=D)  # no save.json yet: finds and migrates hero.json
    assert g.profile.name == "Jarvin" and len(g.quests) == 4
    saved = g.save()
    assert saved == tmp_path / "save.json"
    assert json.loads(hero.read_text(encoding="utf-8")) == V0  # old file untouched (backup)

    again = Game.load(today=date(2030, 1, 1))  # now reads save.json, not hero.json
    assert again.data == g.data
    assert again.data.legacy == V0


def test_v0_at_explicit_path_is_migrated(tmp_path):
    path = tmp_path / "hero.json"
    path.write_text(json.dumps(V0), encoding="utf-8")
    g = Game.load(path, today=D)
    assert g.profile.level == 3 and g.quests[0].done_on == [D.isoformat()]


def test_empty_v0_hero():
    data = storage.from_dict({"name": "Legend", "level": 1, "xp": 0, "quests": []}, today=D)
    assert data.quests == [] and data.profile.level == 1 and data.next_id == 1


def test_data_dir_env(tmp_path, monkeypatch):
    target = tmp_path / "flet"
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(target))
    assert storage.data_dir() == target and target.is_dir()


# --- schema 2 (v1.1) ----------------------------------------------------------------------------
SCHEMA1 = {
    "schema": 1,
    "profile": {
        "name": "Jarvin", "level": 4, "xp": 30, "coins": 120,
        "path_xp": {"chef": 300, "steward": 45}, "theme_id": "royal",
        "owned_themes": ["arcane", "ember", "royal"], "coins_today": 20,
        "coins_day": "2026-11-03",
    },
    "quests": [{"id": "q1", "title": "Stretch", "path_id": "warrior", "kind": "daily",
                "xp": 20, "coins": 10, "difficulty": 1, "note": "gentle",
                "created": "2026-11-01", "done_on": ["2026-11-02", "2026-11-03"],
                "minutes": None}],
    "bills": [{"id": "b2", "name": "Rent", "amount": 8000.5, "due": "2026-11-04",
               "repeat": "monthly", "paid": ["2026-11-04"]}],
    "rewards": [{"id": "r3", "title": "Movie", "cost": 50, "kind": "personal",
                 "theme_id": None, "redeemed": ["2026-11-02"]}],
    "logs": [{"id": "l4", "day": "2026-11-02", "kind": "sleep", "text": "ok", "minutes": 420}],
    "next_id": 5,
}


def test_schema1_migrates_to_2_without_loss(tmp_path):
    path = tmp_path / "save.json"
    path.write_text(json.dumps(SCHEMA1), encoding="utf-8")
    g = Game.load(path)
    p = g.profile
    assert (p.name, p.level, p.xp, p.coins, p.path_xp) == (
        "Jarvin", 4, 30, 120, {"chef": 300, "steward": 45, "monk": 0})
    assert (p.theme_id, p.owned_themes, p.coins_today, p.coins_day) == (
        "royal", ["arcane", "ember", "royal", "rose"], 20, "2026-11-03")
    assert (p.avatar_id, p.onboarded, p.voice_on, p.voice_volume) == ("a1", True, True, 0.8)
    assert g.data.side_quests == [] and g.data.skills == [] and g.data.next_id == 5
    # every v1 record survives: compare against the original dicts
    out = storage.to_dict(g.data)
    assert out["schema"] == storage.SCHEMA
    for key in ("quests", "bills", "rewards", "logs"):  # every old field kept, new ones added
        for old, new in zip(SCHEMA1[key], out[key], strict=True):
            assert {k: new[k] for k in old} == old, key
    for key, value in SCHEMA1["profile"].items():
        if key == "path_xp":  # schema 4 adds the Monk Path at 0
            value = {**value, "monk": 0}
        if key == "owned_themes":  # free themes (Rose Arcana) are added on load
            value = [*value, "rose"]
        assert out["profile"][key] == value, key
    # and it round-trips as schema 3
    g.save(path)
    assert Game.load(path).data == g.data


def test_existing_schema1_player_is_onboarded_even_if_minimal():
    data = storage.from_dict({"schema": 1})
    assert data.profile.onboarded is True


def test_v0_migrates_to_schema2_onboarded(tmp_path):
    data = storage.from_dict(V0, today=D)
    assert data.profile.onboarded is True and data.side_quests == [] and data.skills == []
    path = storage.save(data, tmp_path / "save.json")
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["schema"] == storage.SCHEMA and raw["legacy"] == V0 and raw["profile"]["onboarded"] is True
    again = storage.load(path)
    assert again == data and again.profile.onboarded is True


def test_brand_new_save_is_not_onboarded_and_stays_so_until_finished(tmp_path):
    g = Game.load(tmp_path / "missing.json")
    assert g.profile.onboarded is False
    path = g.save(tmp_path / "save.json")
    assert Game.load(path).profile.onboarded is False  # app closed mid-onboarding
    g.finish_onboarding("Jarvin", "a3")
    g.save(path)
    assert Game.load(path).profile.onboarded is True


def _schema2_game() -> Game:
    g = _full_game()
    g.set_profile(avatar_id="a7", voice_on=False, voice_volume=0.35)
    g.profile.onboarded = True
    done = g.start_side_quest("knife-skills", D)
    for i in range(3):
        g.complete_step(done.id, i, D)
    g.start_side_quest(g.followups_for("Knife Skills")[0].id, D)
    half = g.add_side_quest("Juggling", "artisan", ["a", "b"], difficulty=2, today=D)
    g.complete_step(half.id, 0, D)
    gone = g.start_side_quest("budgeting", D)
    g.complete_step(gone.id, 1, D)
    g.abandon_side_quest(gone.id)
    return g


def test_schema2_round_trip(tmp_path):
    g = _schema2_game()
    path = g.save(tmp_path / "save.json")
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["schema"] == storage.SCHEMA
    assert raw["profile"]["avatar_id"] == "a7" and raw["profile"]["voice_volume"] == 0.35
    assert [sq["catalog_id"] for sq in raw["side_quests"]] == [
        "knife-skills", "knife-skills-r2", None, "budgeting"]
    assert raw["side_quests"][3]["abandoned"] is True
    assert raw["side_quests"][0]["steps"][0]["done_on"] == D.isoformat()
    assert raw["skills"] == [{"name": "Knife Skills", "path_id": "chef", "rank": 1,
                              "unlocked_on": D.isoformat(),
                              "chain_ids": [raw["side_quests"][0]["id"]]}]
    loaded = Game.load(path)
    assert loaded.data == g.data
    # the loaded game keeps playing correctly
    r2 = loaded.side_quests(active_only=True)[0]
    *_, last = [loaded.complete_step(r2.id, i, D) for i in range(3)]
    assert (last.skill_unlocked, last.skill_rank) == ("Knife Skills", 2)


def test_schema2_ignores_unknown_side_quest_fields(tmp_path):
    path = tmp_path / "save.json"
    path.write_text(json.dumps({
        "schema": 2,
        "profile": {"onboarded": False},
        "side_quests": [{"id": "s1", "skill_name": "X", "path_id": "chef", "future": 1,
                         "steps": [{"title": "a", "xp": 20, "coins": 10, "extra": True}]}],
        "skills": [{"name": "Y", "path_id": "chef", "rank": 2, "mystery": "?"}],
    }), encoding="utf-8")
    data = storage.load(path)
    assert data.profile.onboarded is False  # schema 2 value kept
    [sq] = data.side_quests
    assert sq.steps[0].title == "a" and sq.steps[0].done_on is None and sq.rank_target == 1
    assert data.skills[0].rank == 2 and data.skills[0].chain_ids == []


def test_sfx_and_effects_settings_default_and_round_trip(tmp_path):
    # an older save without the v1.2 settings keys loads with the defaults
    old = {"schema": 3, "profile": {"name": "A", "voice_on": False}}
    p = storage.from_dict(old, D).profile
    assert (p.sfx_on, p.sfx_volume, p.reduce_effects) == (True, 0.6, False)
    g = Game()
    g.set_profile(sfx_on=False, sfx_volume=1.7, reduce_effects=True)
    assert g.profile.sfx_volume == 1.0  # clamped
    g.set_profile(sfx_volume=-1)
    assert g.profile.sfx_volume == 0.0
    path = g.save(tmp_path / "save.json")
    back = Game.load(path).profile
    assert (back.sfx_on, back.sfx_volume, back.reduce_effects) == (False, 0.0, True)
    g.set_profile(name="B")  # None leaves the settings alone
    assert (g.profile.sfx_on, g.profile.reduce_effects) == (False, True)


def test_notify_sound_default_validation_and_old_saves(tmp_path):
    from lol.core.models import DEFAULT_NOTIFY_SOUND, NOTIFY_SOUNDS

    g = Game()
    assert g.profile.notify_sound == DEFAULT_NOTIFY_SOUND in NOTIFY_SOUNDS
    g.set_profile(notify_sound="notify_03")
    with pytest.raises(ValueError):
        g.set_profile(notify_sound="beep")
    assert g.profile.notify_sound == "notify_03"
    back = storage.import_json(storage.export_json(g.data))
    assert back.profile.notify_sound == "notify_03"
    raw = json.loads(storage.export_json(g.data))
    del raw["profile"]["notify_sound"]  # a schema-5 save from before the field
    assert storage.import_json(json.dumps(raw)).profile.notify_sound == DEFAULT_NOTIFY_SOUND
    raw["profile"]["notify_sound"] = "gone"
    assert storage.import_json(json.dumps(raw)).profile.notify_sound == DEFAULT_NOTIFY_SOUND
