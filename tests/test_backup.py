import csv
import io
import json
from datetime import date, timedelta

import pytest

from lol.core import storage
from lol.core.game import Game
from lol.core.models import SaveData

D = date(2026, 11, 4)


def day(n: int) -> date:
    return D + timedelta(days=n)


def _v12_game() -> Game:
    g = Game()
    g.profile.name = "Jarvin"
    q = g.add_quest("Stretch, gently", "warrior", kind="daily", note='say "hi"', today=D)
    g.complete_quest(q.id, D)
    g.complete_quest(q.id, day(1))
    g.quest_from_template("t-oral-care", D)
    g.edit_template("t-gym", title="Leg day")
    g.delete_template("t-facial")
    g.template_from_quest(q.id)
    rent = g.add_bill("Rent", 8000.5, D, "monthly")
    g.pay_bill(rent.id, D)
    g.edit_bill(rent.id, due=date(2026, 12, 20), amount=9000)
    old = g.add_bill("Old gym", 30, D)
    g.pay_bill(old.id, D)
    g.archive_bill(old.id)
    g.profile.coins += 200
    r = g.add_reward("Movie", 50)
    g.redeem(r.id, D)
    g.edit_reward(r.id, cost=70)
    g.delete_reward(r.id)  # archived, history kept
    g.add_log("note", "=SUM(A1)", today=D)  # formula-looking text
    sq = g.add_side_quest("Guitar", "artisan", g.generate_chain("Guitar", "artisan"), today=D,
                          ordered=True, target_date=day(20))
    g.complete_step(sq.id, 0, D)
    g.skip_step(sq.id, 1, D)
    g.pause_side_quest(sq.id)
    g.log_focus(25, D, quest_id=q.id, note="morning", partial=True)
    return g


def test_schema3_save_round_trip(tmp_path):
    g = _v12_game()
    path = g.save(tmp_path / "save.json")
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["schema"] == storage.SCHEMA == 5
    for key in ("templates", "hidden_templates", "focus_sessions"):
        assert key in raw
    assert raw["bills"][0]["start_cycle"] == 1 and raw["bills"][0]["paid_due"] == [D.isoformat()]
    assert Game.load(path).data == g.data


def test_export_import_json_round_trip():
    g = _v12_game()
    text = storage.export_json(g.data)
    data = storage.import_json(text)
    assert data == g.data
    assert storage.export_json(data) == text
    g2 = Game(data)  # restored game keeps playing
    sq = g2.data.side_quests[0]
    g2.resume_side_quest(sq.id)
    assert g2.complete_step(sq.id, 2, day(1)).xp > 0
    assert g2.next_due(g2.bill(g.data.bills[0].id)) == date(2026, 12, 20)


def test_import_json_migrates_older_saves():
    v0 = {"name": "Old", "level": 2, "xp": 5, "quests": [{"title": "A", "xp": 10, "done": True}]}
    data = storage.import_json(json.dumps(v0), today=D)
    assert data.profile.name == "Old" and data.legacy == v0
    s1 = storage.import_json(json.dumps({"schema": 1, "profile": {"name": "One"}}))
    assert s1.profile.name == "One" and s1.templates == [] and s1.focus_sessions == []


@pytest.mark.parametrize("text", [
    "not json",
    "[1, 2]",
    json.dumps({"schema": 99}),
    json.dumps({"schema": "3"}),
    json.dumps({"schema": 3, "quests": {"a": 1}}),
    json.dumps({"schema": 3, "quests": [1]}),
    json.dumps({"schema": 3, "profile": []}),
    json.dumps({"schema": 3, "quests": [{"title": "no id"}]}),
    json.dumps({"schema": 3, "logs": [{"id": "l1", "day": "yesterday", "kind": "note"}]}),
    json.dumps({"schema": 3, "quests": [{"id": "q1", "title": "a", "path_id": "chef"},
                                        {"id": "q1", "title": "b", "path_id": "chef"}]}),
    json.dumps({"schema": 3, "hidden_templates": [{"x": 1}]}),
])
def test_import_json_rejects_invalid(text):
    with pytest.raises(ValueError):
        storage.import_json(text)


def test_import_fixes_next_id_so_ids_never_collide():
    raw = {"schema": 3, "next_id": 1,
           "quests": [{"id": "q7", "title": "a", "path_id": "chef"}],
           "templates": [{"id": "t-gym", "title": "x", "builtin": True}]}
    g = Game(storage.import_json(json.dumps(raw)))
    assert g.data.next_id == 8 and g.add_quest("b", "chef", today=D).id == "q8"


# --- schema 2 -> 3 migration ----------------------------------------------------------------------
SCHEMA2 = {
    "schema": 2,
    "profile": {"name": "Jarvin", "coins": 40, "path_xp": {"steward": 30}, "onboarded": True},
    "quests": [{"id": "q1", "title": "Read", "path_id": "scholar", "kind": "daily", "xp": 20,
                "coins": 10, "difficulty": 1, "note": "", "created": "2026-01-01",
                "done_on": ["2026-01-02"], "minutes": None}],
    "bills": [{"id": "b2", "name": "Rent", "amount": 100.0, "due": "2026-01-31",
               "repeat": "monthly", "paid": ["2026-01-30", "2026-02-27"]},
              {"id": "b3", "name": "Fee", "amount": 5.0, "due": "2026-03-01",
               "repeat": "none", "paid": ["2026-03-01"]}],
    "rewards": [{"id": "r4", "title": "Movie", "cost": 50, "kind": "personal",
                 "theme_id": None, "redeemed": ["2026-01-05", "2026-02-05"]}],
    "logs": [],
    "side_quests": [{"id": "s5", "skill_name": "Knife Skills", "path_id": "chef",
                     "steps": [{"title": "a", "note": "", "xp": 20, "coins": 10,
                                "done_on": "2026-01-03"},
                               {"title": "b", "note": "", "xp": 20, "coins": 10,
                                "done_on": None}],
                     "custom": False, "rank_target": 1, "created": "2026-01-01",
                     "catalog_id": "knife-skills", "abandoned": False}],
    "skills": [],
    "next_id": 6,
}


def test_schema2_migrates_to_3_without_loss():
    data = storage.from_dict(json.loads(json.dumps(SCHEMA2)))
    out = storage.to_dict(data)
    assert out["schema"] == storage.SCHEMA
    for key in ("quests", "bills", "rewards", "side_quests"):  # every old field kept as is
        for old, new in zip(SCHEMA2[key], out[key], strict=True):
            for k, v in old.items():
                if k != "steps":
                    assert new[k] == v, (key, k)
    rent, fee = data.bills
    assert rent.paid_due == ["2026-01-31", "2026-02-28"] and rent.paid_amounts == [100.0, 100.0]
    assert (rent.start_cycle, rent.archived) == (0, False)
    assert fee.paid_due == ["2026-03-01"]
    assert data.rewards[0].redeemed_costs == [50, 50] and not data.rewards[0].archived
    sq = data.side_quests[0]
    assert (sq.ordered, sq.paused, sq.target_date) == (False, False, None)
    assert sq.steps[0].skipped_on is None
    assert data.templates == [] and data.hidden_templates == [] and data.focus_sessions == []
    g = Game(data)  # behaviour is unchanged after migration
    assert g.next_due(rent) == date(2026, 3, 31)
    assert g.bill_status(fee, date(2026, 3, 2)) == "paid"
    assert g.bill_status(rent, date(2026, 2, 28)) == "paid"


def test_migrated_save_round_trips(tmp_path):
    data = storage.from_dict(json.loads(json.dumps(SCHEMA2)))
    path = storage.save(data, tmp_path / "save.json")
    assert storage.load(path) == data


# --- CSV ----------------------------------------------------------------------------------------
def _read(text: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(text)))


def test_export_csv_tables():
    g = _v12_game()
    tables = storage.export_csv(g.data)
    assert set(tables) == set(storage.CSV_TABLES)
    for name, text in tables.items():
        assert text.splitlines()[0].split(",") == list(storage.CSV_TABLES[name])
    quests = _read(tables["quests.csv"])
    assert quests[0]["title"] == "Stretch, gently" and quests[0]["note"] == 'say "hi"'
    assert quests[0]["times_done"] == "2" and quests[1]["template_id"] == "t-oral-care"
    done = _read(tables["quest_completions.csv"])
    assert [r["day"] for r in done] == [D.isoformat(), day(1).isoformat()]
    steps = _read(tables["side_quest_steps.csv"])
    assert len(steps) == 4 and steps[0]["done_on"] == D.isoformat()
    assert steps[1]["skipped_on"] == D.isoformat() and steps[0]["paused"] == "True"
    pays = _read(tables["bill_payments.csv"])
    assert [(p["name"], p["cycle_due"], p["amount"]) for p in pays] == [
        ("Rent", D.isoformat(), "8000.5"), ("Old gym", D.isoformat(), "30.0")]
    bills = _read(tables["bills.csv"])
    assert [b["archived"] for b in bills] == ["False", "True"] and bills[0]["amount"] == "9000.0"
    red = _read(tables["reward_redemptions.csv"])
    assert red == [{"reward_id": g.data.rewards[0].id, "title": "Movie", "day": D.isoformat(),
                    "cost": "50"}]
    assert _read(tables["rewards.csv"])[0]["archived"] == "True"
    assert _read(tables["logs.csv"])[0]["text"] == "'=SUM(A1)"  # formula neutralised
    focus = _read(tables["focus_sessions.csv"])
    assert focus[0]["minutes"] == "25" and focus[0]["partial"] == "True"
    assert focus[0]["path_id"] == "warrior"


def test_export_csv_empty_save_has_headers_only():
    tables = storage.export_csv(SaveData())
    assert all(len(t.splitlines()) == 1 for t in tables.values())


def test_summary():
    s = storage.summary(_v12_game().data)
    assert s["quests"] == 2 and s["quest_completions"] == 2 and s["bill_payments"] == 2
    assert s["redemptions"] == 1 and s["focus_sessions"] == 1 and s["templates"] == 2
