from datetime import date, timedelta

import pytest

from lol.core.game import (
    COINS_BY_DIFFICULTY,
    COINS_MAX_BY_DIFFICULTY,
    STEWARD_BILL_XP,
    XP_BY_DIFFICULTY,
    XP_MAX_BY_DIFFICULTY,
    Game,
    bill_occurrence,
    clamp_rewards,
    reward_limits,
)

D = date(2026, 11, 4)


def day(n: int) -> date:
    return D + timedelta(days=n)


# --- reward limits ------------------------------------------------------------------------------
def test_reward_limits_are_1_5x_defaults():
    assert XP_MAX_BY_DIFFICULTY == {1: 30, 2: 60, 3: 105}
    assert COINS_MAX_BY_DIFFICULTY == {1: 15, 2: 30, 3: 53}
    assert reward_limits(2) == (60, 30)
    assert clamp_rewards(1, None, None) == (XP_BY_DIFFICULTY[1], COINS_BY_DIFFICULTY[1])
    assert clamp_rewards(1, 999, 999) == (30, 15)
    assert clamp_rewards(3, -5, -1) == (0, 0)
    with pytest.raises(ValueError):
        reward_limits(4)


def test_add_quest_custom_rewards_are_clamped():
    g = Game()
    q = g.add_quest("Big", "chef", difficulty=1, today=D, coins=500, xp=500)
    assert (q.xp, q.coins) == (30, 15)
    q2 = g.add_quest("Small", "chef", difficulty=2, today=D, coins=5, xp=12)
    assert (q2.xp, q2.coins) == (12, 5)
    assert g.complete_quest(q.id, D).coins == 15


# --- quests -------------------------------------------------------------------------------------
def test_edit_quest_fields_and_keeps_history():
    g = Game()
    q = g.add_quest("Stretch", "warrior", kind="daily", today=D)
    g.complete_quest(q.id, D)
    g.complete_quest(q.id, day(1))
    xp_before = g.profile.xp
    g.edit_quest(q.id, title="  Long stretch ", path_id="ranger", note="outside", minutes=15)
    assert (q.title, q.path_id, q.note, q.minutes, q.kind) == (
        "Long stretch", "ranger", "outside", 15, "daily")
    assert q.done_on == [D.isoformat(), day(1).isoformat()]
    assert g.profile.xp == xp_before  # editing never changes earned XP
    assert g.complete_quest(q.id, day(1)).xp == 0  # still done today
    assert g.streak(q, day(1)) == 2


def test_edit_quest_difficulty_resets_rewards_unless_given():
    g = Game()
    q = g.add_quest("Run", "warrior", today=D, coins=12)
    g.edit_quest(q.id, difficulty=3)
    assert (q.difficulty, q.xp, q.coins) == (3, XP_BY_DIFFICULTY[3], COINS_BY_DIFFICULTY[3])
    g.edit_quest(q.id, difficulty=1, coins=999)
    assert (q.xp, q.coins) == (XP_BY_DIFFICULTY[1], 15)
    g.edit_quest(q.id, xp=25)  # same difficulty: only xp changes
    assert (q.xp, q.coins) == (25, 15)
    g.edit_quest(q.id, coins=1000)
    assert q.coins == COINS_MAX_BY_DIFFICULTY[1]


def test_edit_quest_kind_and_minutes_clear():
    g = Game()
    q = g.add_quest("Read", "scholar", today=D, minutes=10)
    g.complete_quest(q.id, D)
    g.edit_quest(q.id, kind="daily", minutes=None)
    assert q.kind == "daily" and q.minutes is None
    assert not g.is_done(q, day(1)) and g.complete_quest(q.id, day(1)).xp > 0
    assert q.done_on == [D.isoformat(), day(1).isoformat()]


def test_edit_quest_validates():
    g = Game()
    q = g.add_quest("A", "chef", today=D)
    for kw in ({"title": " "}, {"path_id": "wizard"}, {"kind": "hourly"}, {"difficulty": 0}):
        with pytest.raises(ValueError):
            g.edit_quest(q.id, **kw)
    assert q.title == "A" and q.path_id == "chef"  # nothing half-applied
    with pytest.raises(KeyError):
        g.edit_quest("nope", title="x")


# --- rewards ------------------------------------------------------------------------------------
def test_edit_reward_keeps_redemptions():
    g = Game()
    g.profile.coins = 200
    r = g.add_reward("Movie", 50)
    g.redeem(r.id, D)
    g.edit_reward(r.id, title="Cinema", cost=80)
    assert (r.title, r.cost, r.redeemed, r.redeemed_costs) == (
        "Cinema", 80, [D.isoformat()], [50])
    assert g.redeem(r.id, day(1)) and g.profile.coins == 200 - 50 - 80
    assert r.redeemed_costs == [50, 80]
    with pytest.raises(ValueError):
        g.edit_reward(r.id, cost=-1)
    with pytest.raises(ValueError):
        g.edit_reward(r.id, title="")


def test_delete_redeemed_reward_archives_it():
    g = Game()
    g.profile.coins = 100
    used, unused = g.add_reward("Snack", 10), g.add_reward("Never", 10)
    g.redeem(used.id, D)
    g.delete_reward(used.id)
    g.delete_reward(unused.id)
    assert g.rewards == [] and g.archived_rewards() == [used]
    assert [r.id for r in g.data.rewards] == [used.id]  # history kept
    assert g.redeem(used.id, D) is False and g.profile.coins == 90
    g.unarchive_reward(used.id)
    assert g.rewards == [used] and g.redeem(used.id, D)
    g.archive_reward(used.id)
    assert g.rewards == []


# --- bills: editing and paid history --------------------------------------------------------------
def _cycle_dates(g: Game, bill, n: int) -> list[date]:
    return [bill_occurrence(bill, i) for i in range(n)]


def test_pay_records_cycle_due_and_amount():
    g = Game()
    b = g.add_bill("Rent", 100, date(2026, 1, 31), "monthly")
    g.pay_bill(b.id, date(2026, 1, 30))
    g.pay_bill(b.id, date(2026, 2, 27))
    assert b.paid_due == ["2026-01-31", "2026-02-28"] and b.paid_amounts == [100.0, 100.0]


def test_edit_bill_name_amount_only_keeps_schedule():
    g = Game()
    b = g.add_bill("Rent", 100, date(2026, 1, 31), "monthly")
    g.pay_bill(b.id, date(2026, 1, 30))
    g.pay_bill(b.id, date(2026, 2, 27))
    g.edit_bill(b.id, name="Home rent", amount=120)
    assert (b.name, b.amount, b.start_cycle) == ("Home rent", 120.0, 0)
    assert g.next_due(b) == date(2026, 3, 31)  # no drift to the 28th
    assert b.paid_amounts == [100.0, 100.0]  # past payments keep their amount
    g.pay_bill(b.id, date(2026, 3, 30))
    assert b.paid_amounts == [100.0, 100.0, 120.0]


def test_edit_bill_due_reanchors_without_losing_or_doubling_cycles():
    g = Game()
    b = g.add_bill("Phone", 50, date(2026, 1, 5), "monthly")
    g.pay_bill(b.id, date(2026, 1, 5))
    g.pay_bill(b.id, date(2026, 2, 4))
    assert g.next_due(b) == date(2026, 3, 5)
    g.edit_bill(b.id, due=date(2026, 3, 20))
    assert g.next_due(b) == date(2026, 3, 20)  # exactly the new date
    assert len(b.paid) == 2 and b.start_cycle == 2  # paid count unchanged
    assert _cycle_dates(g, b, 4) == [date(2026, 1, 5), date(2026, 2, 5),
                                     date(2026, 3, 20), date(2026, 4, 20)]
    assert g.bill_status(b, date(2026, 3, 10)) == "upcoming"
    assert g.upcoming_total(date(2026, 3, 10), 30) == 50.0  # only Mar 20 in the window
    g.pay_bill(b.id, date(2026, 3, 19))
    assert g.next_due(b) == date(2026, 4, 20)
    assert g.bill_status(b, date(2026, 3, 19)) == "paid"
    assert b.paid_due == ["2026-01-05", "2026-02-05", "2026-03-20"]


def test_edit_bill_due_earlier_can_make_it_overdue_but_history_stays():
    g = Game()
    b = g.add_bill("Gym", 30, date(2026, 1, 10), "monthly")
    g.pay_bill(b.id, date(2026, 1, 10))
    g.edit_bill(b.id, due=date(2026, 1, 20))
    assert g.bill_status(b, date(2026, 1, 25)) == "overdue"
    assert b.paid_due == ["2026-01-10"]


def test_edit_bill_repeat_keeps_next_due_then_follows_new_repeat():
    g = Game()
    b = g.add_bill("Water", 20, date(2026, 1, 1), "monthly")
    g.pay_bill(b.id, date(2026, 1, 1))
    g.edit_bill(b.id, repeat="weekly")
    assert g.next_due(b) == date(2026, 2, 1)
    g.pay_bill(b.id, date(2026, 2, 1))
    assert g.next_due(b) == date(2026, 2, 8)
    assert len(b.paid) == 2


def test_edit_bill_same_values_is_not_a_schedule_change():
    g = Game()
    b = g.add_bill("Rent", 100, date(2026, 1, 31), "monthly")
    g.pay_bill(b.id, date(2026, 1, 31))
    g.edit_bill(b.id, due=g.next_due(b), repeat="monthly")
    assert b.start_cycle == 0 and b.due == "2026-01-31"


def test_edit_paid_one_off_bill():
    g = Game()
    b = g.add_bill("Fee", 10, D)
    g.pay_bill(b.id, D)
    g.edit_bill(b.id, due=day(2))  # stays one-off: still paid, date corrected
    assert g.bill_status(b, D) == "paid" and b.due == day(2).isoformat()
    assert g.pay_bill(b.id, D).xp == 0
    g.edit_bill(b.id, repeat="monthly")  # becomes a series starting a month later
    assert g.next_due(b) == date(2026, 12, 6) and len(b.paid) == 1
    assert g.bill_status(b, day(10)) == "upcoming"
    assert g.pay_bill(b.id, day(30)).xp == STEWARD_BILL_XP


def test_repeating_bill_switched_to_one_off():
    g = Game()
    b = g.add_bill("Sub", 5, date(2026, 1, 1), "monthly")
    for m in (1, 2, 3):
        g.pay_bill(b.id, date(2026, m, 1))
    g.edit_bill(b.id, repeat="none", due=date(2026, 6, 1))
    assert g.bill_status(b, date(2026, 5, 1)) == "upcoming"
    assert g.upcoming_total(date(2026, 5, 15), 30) == 5.0
    g.pay_bill(b.id, date(2026, 5, 20))
    assert g.bill_status(b, date(2026, 5, 20)) == "paid" and len(b.paid) == 4
    assert g.pay_bill(b.id, date(2026, 5, 21)).xp == 0


def test_edit_bill_validates():
    g = Game()
    b = g.add_bill("A", 1, D)
    for kw in ({"repeat": "daily"}, {"amount": -1}, {"name": " "}):
        with pytest.raises(ValueError):
            g.edit_bill(b.id, **kw)


def test_archive_bill_hides_but_keeps_history():
    g = Game()
    b = g.add_bill("Old", 100, D, "monthly")
    other = g.add_bill("Rent", 50, day(1))
    g.pay_bill(b.id, D)
    g.archive_bill(b.id)
    assert [r[0] for r in g.bills_status(D)] == [other]
    assert g.upcoming_total(D, 60) == 50.0
    assert g.bills == [other] and g.archived_bills() == [b]
    assert g.bill(b.id) is b and b.paid == [D.isoformat()]
    assert g.pay_bill(b.id, day(30)).xp == 0 and len(b.paid) == 1
    assert g.weekly_review(D)["bills_paid"] == 1  # archived history still counts
    g.unarchive_bill(b.id)
    assert len(g.bills_status(D)) == 2
    g.delete_bill(b.id)
    with pytest.raises(KeyError):
        g.bill(b.id)
