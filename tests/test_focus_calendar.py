from datetime import date, timedelta

import pytest

from lol.core.game import (
    DAILY_COIN_CAP,
    FOCUS_DAILY_COIN_CAP,
    FOCUS_DAILY_XP_CAP,
    FOCUS_MAX_MINUTES,
    FOCUS_XP_PER_BLOCK,
    Game,
)
from lol.core.models import ENTRY_KINDS, Entry

D = date(2026, 11, 4)


def day(n: int) -> date:
    return D + timedelta(days=n)


# --- focus --------------------------------------------------------------------------------------
def test_focus_awards_xp_per_block_to_linked_path():
    g = Game()
    c = g.log_focus(25, D, path_id="scholar", note="essay")
    assert (c.xp, c.coins, c.path_id) == (5 * FOCUS_XP_PER_BLOCK, 1, "scholar")
    assert g.profile.path_xp["scholar"] == 10
    [s] = g.focus_sessions()
    assert (s.id, s.day, s.minutes, s.mode, s.note, s.xp, s.coins) == (
        c.ref_id, D.isoformat(), 25, "focus", "essay", 10, 1)


def test_focus_linked_quest_gives_path_but_does_not_complete_it():
    g = Game()
    q = g.add_quest("Study", "scholar", today=D)
    c = g.log_focus(30, D, quest_id=q.id)
    assert c.path_id == "scholar" and q.done_on == []
    assert g.focus_sessions(D)[0].quest_id == q.id
    with pytest.raises(KeyError):
        g.log_focus(10, D, quest_id="q999")


def test_unlinked_focus_gives_overall_xp_only():
    g = Game()
    c = g.log_focus(10, D, mode="stopwatch")
    assert c.xp == 4 and c.path_id == "" and g.profile.path_xp == {}
    assert g.profile.xp == 4


def test_partial_and_tiny_sessions_count():
    g = Game()
    c = g.log_focus(7, D, path_id="artisan", partial=True)
    assert c.xp == FOCUS_XP_PER_BLOCK and c.coins == 0
    tiny = g.log_focus(2, D, path_id="artisan", partial=True)
    assert tiny.xp == 0 and len(g.focus_sessions(D)) == 2  # still logged
    assert g.focus_sessions(D)[0].partial


def test_focus_daily_caps():
    g = Game()
    for _ in range(4):
        g.log_focus(60, D, path_id="scholar")
    st = g.focus_stats(D)
    assert st["xp"] == FOCUS_DAILY_XP_CAP and st["xp_left"] == 0
    assert st["coins"] == FOCUS_DAILY_COIN_CAP and st["minutes"] == 240 and st["sessions"] == 4
    assert g.log_focus(60, D, path_id="scholar").xp == 0
    assert g.log_focus(60, day(1), path_id="scholar").xp == 24  # new day


def test_focus_coins_respect_global_cap():
    g = Game()
    g.profile.coins_day, g.profile.coins_today = D.isoformat(), DAILY_COIN_CAP
    c = g.log_focus(60, D)
    assert c.coins == 0 and c.capped and g.focus_sessions()[0].coins == 0


def test_focus_validation_and_clamp():
    g = Game()
    for bad in ({"minutes": 0}, {"minutes": 5, "mode": "nap"}, {"minutes": 5, "path_id": "x"}):
        with pytest.raises(ValueError):
            g.log_focus(today=D, **bad)
    g.log_focus(999, D)
    assert g.focus_sessions()[0].minutes == FOCUS_MAX_MINUTES


def test_focus_sessions_order_and_delete():
    g = Game()
    a = g.log_focus(5, D).ref_id
    b = g.log_focus(5, day(1)).ref_id
    c = g.log_focus(5, day(1)).ref_id
    assert [s.id for s in g.focus_sessions()] == [c, b, a]
    xp = g.profile.xp
    g.delete_focus_session(b)
    assert [s.id for s in g.focus_sessions(day(1))] == [c] and g.profile.xp == xp


def test_weekly_review_counts_focus():
    g = Game()
    g.log_focus(25, D, path_id="scholar")
    g.log_focus(10, D)
    r = g.weekly_review(D)
    assert r["focus_minutes"] == 35 and r["xp_by_path"]["scholar"] == 10
    assert r["xp_total"] == 14


# --- calendar -----------------------------------------------------------------------------------
def _busy_game() -> Game:
    g = Game()
    q = g.add_quest("Stretch", "warrior", kind="daily", today=D)
    g.complete_quest(q.id, D)
    g.complete_quest(q.id, day(2))
    sq = g.add_side_quest("Juggling", "artisan", ["a", "b"], today=D)
    g.complete_step(sq.id, 0, day(1))
    g.skip_step(sq.id, 1, day(1))
    g.add_log("note", "good day", today=day(1))
    g.log_focus(25, day(2), path_id="scholar")
    rent = g.add_bill("Rent", 100, D, "weekly")
    g.pay_bill(rent.id, D)
    g.add_bill("Fee", 5, day(3))
    return g


def test_calendar_entries_kinds_and_neutral_blanks():
    g = _busy_game()
    cal = g.calendar_entries(D, day(13))
    assert list(cal) == [D, day(1), day(2), day(3), day(7)]  # sorted; day(14) is out of range
    kinds = {d: [e.kind for e in es] for d, es in cal.items()}
    assert kinds[D] == ["quest", "bill_due", "bill_paid"]
    assert kinds[day(1)] == ["step", "log"]  # skipped step is not shown
    assert kinds[day(2)] == ["quest", "focus"]
    assert kinds[day(3)] == ["bill_due"]
    assert kinds[day(7)] == ["bill_due"]  # future occurrence
    assert all(e.kind in ENTRY_KINDS for es in cal.values() for e in es)
    assert day(4) not in cal  # blank day is simply absent
    assert cal[day(1)][0] == Entry("step", "Juggling: a", "artisan", g.data.side_quests[0].id)


def test_calendar_filter_and_range():
    g = _busy_game()
    only = g.calendar_entries(D, day(30), {"bill_due"})
    assert all(e.kind == "bill_due" for es in only.values() for e in es)
    assert [d for d in only if any(e.title == "Rent" for e in only[d])] == [
        D, day(7), day(14), day(21), day(28)]
    assert g.calendar_entries(day(5), day(6)) == {}
    with pytest.raises(ValueError):
        g.calendar_entries(D, day(1), {"missed"})


def test_calendar_overdue_bill_is_just_a_due_entry_and_archived_hidden():
    g = Game()
    b = g.add_bill("Old", 10, D)
    cal = g.calendar_entries(D, day(40))
    assert [e.kind for e in cal[D]] == ["bill_due"]
    g.pay_bill(b.id, day(5))
    g.archive_bill(b.id)
    cal = g.calendar_entries(D, day(40))
    assert D not in cal and [e.kind for e in cal[day(5)]] == ["bill_paid"]


def test_calendar_after_bill_edit_shows_true_history():
    g = Game()
    b = g.add_bill("Phone", 50, date(2026, 1, 5), "monthly")
    g.pay_bill(b.id, date(2026, 1, 5))
    g.edit_bill(b.id, due=date(2026, 2, 20))
    cal = g.calendar_entries(date(2026, 1, 1), date(2026, 3, 31), {"bill_due"})
    assert list(cal) == [date(2026, 1, 5), date(2026, 2, 20), date(2026, 3, 20)]
