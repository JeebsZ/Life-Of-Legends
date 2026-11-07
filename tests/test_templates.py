from datetime import date

import pytest

from lol.core import catalog
from lol.core.game import COINS_BY_DIFFICULTY, XP_BY_DIFFICULTY, Game

D = date(2026, 11, 4)


def test_starter_library():
    g = Game()
    ts = g.templates()
    assert len(ts) >= 15 and all(t.builtin for t in ts)
    titles = " ".join(t.title.lower() for t in ts)
    for word in ("skin care", "oral care", "face mask", "stretch", "gym", "weekly planning",
                 "meal prep", "read 20 pages", "tidy desk", "water", "journal", "walk"):
        assert word in titles, word
    assert len({t.id for t in ts}) == len(ts)
    for t in ts:
        assert t.path_id in catalog.PATH_IDS and t.kind in ("once", "daily")
        assert (t.xp, t.coins) == (XP_BY_DIFFICULTY[t.difficulty], COINS_BY_DIFFICULTY[t.difficulty])


def test_quest_from_template_copies_and_leaves_template_alone():
    g = Game()
    t = g.template("t-skin-care")
    q = g.quest_from_template("t-skin-care", D)
    assert (q.title, q.path_id, q.kind, q.difficulty, q.note, q.minutes, q.template_id) == (
        t.title, t.path_id, t.kind, t.difficulty, t.note, t.minutes, "t-skin-care")
    assert q.created == D.isoformat() and q in g.quests
    g.edit_quest(q.id, title="Changed")
    assert g.template("t-skin-care").title == t.title
    q2 = g.quest_from_template("t-skin-care", D)
    assert q2.id != q.id and q2.title == t.title


def test_add_and_edit_user_template():
    g = Game()
    t = g.add_template("Practice guitar", "artisan", difficulty=2, minutes=30, coins=999)
    assert not t.builtin and t.coins == 30 and t.xp == XP_BY_DIFFICULTY[2]
    assert g.templates()[-1] is t
    g.edit_template(t.id, title="Guitar", difficulty=1, note="scales")
    assert (t.title, t.difficulty, t.note, t.xp, t.coins) == (
        "Guitar", 1, "scales", XP_BY_DIFFICULTY[1], COINS_BY_DIFFICULTY[1])
    g.edit_template(t.id, coins=12, minutes=None)
    assert t.coins == 12 and t.minutes is None
    with pytest.raises(ValueError):
        g.add_template(" ", "chef")
    with pytest.raises(ValueError):
        g.edit_template(t.id, path_id="nope")
    g.delete_template(t.id)
    with pytest.raises(KeyError):
        g.template(t.id)


def test_template_from_quest():
    g = Game()
    q = g.add_quest("Evening walk", "warrior", kind="daily", difficulty=2, note="slow",
                    today=D, minutes=20, coins=25)
    t = g.template_from_quest(q.id)
    assert (t.title, t.path_id, t.kind, t.difficulty, t.note, t.minutes, t.coins) == (
        "Evening walk", "warrior", "daily", 2, "slow", 20, 25)
    assert not t.builtin and q.template_id is None


def test_edit_builtin_stores_override_and_restore_resets():
    g = Game()
    original = g.template("t-gym").title
    g.edit_template("t-gym", title="Leg day", minutes=45)
    assert g.template("t-gym").title == "Leg day" and g.template("t-gym").builtin
    assert [t.id for t in g.templates()].count("t-gym") == 1
    assert len(g.data.templates) == 1
    g.edit_template("t-gym", note="warm up")  # edits the same override
    assert len(g.data.templates) == 1 and g.template("t-gym").note == "warm up"
    assert catalog.builtin_templates()[0].title != "Leg day"  # catalog untouched
    g.restore_template("t-gym")
    assert g.template("t-gym").title == original and g.data.templates == []


def test_delete_builtin_only_hides_it():
    g = Game()
    n = len(g.templates())
    g.delete_template("t-facial")
    g.delete_template("t-facial")
    assert len(g.templates()) == n - 1 and g.data.hidden_templates == ["t-facial"]
    assert "t-facial" in {t.id for t in g.templates(include_hidden=True)}
    assert g.template("t-facial").title  # still reachable
    g.restore_template("t-facial")
    assert len(g.templates()) == n
    with pytest.raises(KeyError):
        g.restore_template("t99")
