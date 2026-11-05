import random
from datetime import date, timedelta

import pytest

from lol.core import catalog
from lol.core.game import (
    COINS_BY_DIFFICULTY,
    DAILY_COIN_CAP,
    STEWARD_BILL_COINS,
    STEWARD_BILL_XP,
    XP_BY_DIFFICULTY,
    Game,
    add_months,
)
from lol.core.progression import xp_for_level

D = date(2026, 11, 4)


def day(n: int) -> date:
    return D + timedelta(days=n)


# --- catalog ------------------------------------------------------------------------------------
def test_seven_paths_and_catalog_coverage():
    assert [p.id for p in Game().paths()] == [
        "chef", "warrior", "scholar", "artisan", "ranger", "steward", "monk"
    ]
    for pid in catalog.PATH_IDS:
        entries = [c for c in catalog.QUEST_BOARD if c.path_id == pid]
        assert len(entries) >= 4
        for c in entries:
            assert c.title and c.note and c.difficulty in (1, 2, 3) and c.minutes > 0


def test_themes_catalog():
    prices = catalog.THEME_PRICES
    assert prices["arcane"] == 0 and prices["ember"] == 0
    assert catalog.DEFAULT_THEME == "arcane"
    assert {"ocean", "forest", "royal"} <= prices.keys()
    assert all(prices[t] > 0 for t in ("ocean", "forest", "royal"))


# --- quests -------------------------------------------------------------------------------------
def test_add_quest_uses_difficulty_balance():
    g = Game()
    q = g.add_quest("Read", "scholar", difficulty=2, note="10 pages", today=D)
    assert (q.xp, q.coins, q.kind, q.created) == (XP_BY_DIFFICULTY[2], COINS_BY_DIFFICULTY[2],
                                                 "once", D.isoformat())
    assert q.id and g.quest(q.id) is q


def test_add_quest_validates():
    g = Game()
    with pytest.raises(ValueError):
        g.add_quest("x", "wizard")
    with pytest.raises(ValueError):
        g.add_quest("x", "chef", kind="weekly")
    with pytest.raises(ValueError):
        g.add_quest("x", "chef", difficulty=4)
    with pytest.raises(ValueError):
        g.add_quest("   ", "chef")


def test_ids_are_unique():
    g = Game()
    ids = {g.add_quest(f"q{i}", "chef", today=D).id for i in range(5)}
    ids.add(g.add_bill("Rent", 100, D).id)
    ids.add(g.add_reward("Snack", 10).id)
    assert len(ids) == 7


def test_complete_once_quest_is_idempotent():
    g = Game()
    q = g.add_quest("Walk", "warrior", today=D)
    c = g.complete_quest(q.id, D)
    assert (c.xp, c.coins, c.path_id) == (q.xp, q.coins, "warrior")
    again = g.complete_quest(q.id, D)
    later = g.complete_quest(q.id, day(1))
    assert (again.xp, again.coins, later.xp, later.coins) == (0, 0, 0, 0)
    assert g.profile.xp == q.xp and g.profile.coins == q.coins
    assert g.profile.path_xp["warrior"] == q.xp


def test_daily_quest_once_per_day():
    g = Game()
    q = g.add_quest("Stretch", "warrior", kind="daily", today=D)
    assert g.complete_quest(q.id, D).xp == q.xp
    assert g.complete_quest(q.id, D).xp == 0
    assert g.complete_quest(q.id, day(1)).xp == q.xp
    assert q.done_on == [D.isoformat(), day(1).isoformat()]


def test_complete_unknown_quest_raises():
    with pytest.raises(KeyError):
        Game().complete_quest("nope", D)


def test_today_quests_lists_open_then_done_today():
    g = Game()
    daily = g.add_quest("Daily", "chef", kind="daily", today=D)
    once_open = g.add_quest("Open", "chef", today=D)
    once_old = g.add_quest("Old", "chef", today=D)
    once_today = g.add_quest("Today", "chef", today=D)
    g.complete_quest(once_old.id, D)
    g.complete_quest(daily.id, D)
    # next day: daily resets, once_old (done on D) disappears
    g.complete_quest(once_today.id, day(1))
    assert [q.title for q in g.today_quests(day(1))] == ["Daily", "Open", "Today"]
    assert g.is_done(once_today, day(1)) and not g.is_done(daily, day(1))
    assert [q.title for q in g.today_quests(D)] == ["Open", "Today", "Daily", "Old"]
    assert once_open in g.today_quests(day(5))


def test_delete_quest_keeps_rewards():
    g = Game()
    q = g.add_quest("Walk", "warrior", today=D)
    g.complete_quest(q.id, D)
    g.delete_quest(q.id)
    assert g.quests == [] and g.profile.xp == q.xp


# --- coins --------------------------------------------------------------------------------------
def test_daily_coin_cap_and_reset():
    g = Game()
    per = COINS_BY_DIFFICULTY[3]
    n = DAILY_COIN_CAP // per + 2
    results = [g.complete_quest(g.add_quest(f"q{i}", "chef", difficulty=3, today=D).id, D)
               for i in range(n)]
    assert g.profile.coins == DAILY_COIN_CAP
    assert sum(c.coins for c in results) == DAILY_COIN_CAP
    assert results[0].capped is False and results[-1].capped is True
    assert results[-1].coins == 0 and results[-1].xp == XP_BY_DIFFICULTY[3]  # XP not capped
    # new day, fresh cap
    c = g.complete_quest(g.add_quest("next", "chef", difficulty=3, today=D).id, day(1))
    assert c.coins == per and not c.capped
    assert g.profile.coins_today == per and g.profile.coins_day == day(1).isoformat()


def test_spending_does_not_restore_cap():
    g = Game()
    for i in range(DAILY_COIN_CAP // COINS_BY_DIFFICULTY[3] + 1):
        g.complete_quest(g.add_quest(f"q{i}", "chef", difficulty=3, today=D).id, D)
    g.buy_theme("ocean")
    c = g.complete_quest(g.add_quest("more", "chef", today=D).id, D)
    assert c.coins == 0 and c.capped


# --- levels -------------------------------------------------------------------------------------
def test_overall_and_path_level_up():
    g = Game()
    gained = 0
    path_gained = 0
    for i in range(3):  # 3 x 70 XP = 210 > 100 (level 2), < 225 (level 3)
        c = g.complete_quest(g.add_quest(f"q{i}", "scholar", difficulty=3, today=D).id, D)
        gained += c.levels_gained
        path_gained += c.path_levels_gained
    assert gained == 1 and path_gained == 1
    assert (g.profile.level, g.profile.xp) == (2, 210 - xp_for_level(1))
    assert g.path_level("scholar") == (2, 110, xp_for_level(2))
    assert g.path_level("chef") == (1, 0, xp_for_level(1))


def test_path_level_from_large_total():
    g = Game()
    g.profile.path_xp["chef"] = 100 + 125 + 5
    assert g.path_level("chef") == (3, 5, xp_for_level(3))


# --- streaks ------------------------------------------------------------------------------------
def test_streak_counts_consecutive_days():
    g = Game()
    q = g.add_quest("Stretch", "warrior", kind="daily", today=D)
    for n in range(4):
        g.complete_quest(q.id, day(n))
    assert g.streak(q, day(3)) == 4
    assert g.streak(q, day(4)) == 4  # today not done yet: still alive


def test_streak_grace_and_reset_never_remove_rewards():
    g = Game()
    q = g.add_quest("Stretch", "warrior", kind="daily", today=D)
    g.complete_quest(q.id, day(0))
    g.complete_quest(q.id, day(1))
    g.complete_quest(q.id, day(3))  # missed day 2: forgiven by grace
    assert g.streak(q, day(3)) == 3
    xp, coins = g.profile.xp, g.profile.coins
    assert g.streak(q, day(6)) == 0  # two missed days: streak resets ("resume")
    assert (g.profile.xp, g.profile.coins) == (xp, coins)
    g.complete_quest(q.id, day(6))
    assert g.streak(q, day(6)) == 1


def test_streak_once_quest_is_zero():
    g = Game()
    q = g.add_quest("Once", "chef", today=D)
    g.complete_quest(q.id, D)
    assert g.streak(q, D) == 0


def test_streak_ignores_future_dates():
    g = Game()
    q = g.add_quest("Stretch", "warrior", kind="daily", today=D)
    g.complete_quest(q.id, day(5))
    assert g.streak(q, D) == 0


# --- Quest Board --------------------------------------------------------------------------------
def test_suggest_quest_is_deterministic_and_not_added():
    g = Game()
    a = g.suggest_quest("chef", None, random.Random(42))
    b = g.suggest_quest("chef", None, random.Random(42))
    assert (a.title, a.note, a.difficulty) == (b.title, b.note, b.difficulty)
    assert a.path_id == "chef" and a.id == "" and g.quests == []
    assert a.xp == XP_BY_DIFFICULTY[a.difficulty] and a.minutes


def test_suggest_quest_filters():
    g = Game()
    rng = random.Random(1)
    for _ in range(20):
        q = g.suggest_quest("ranger", 2, rng)
        assert q.path_id == "ranger" and q.difficulty == 2
    paths = {g.suggest_quest(None, None, rng).path_id for _ in range(200)}
    assert paths == set(catalog.PATH_IDS)


def test_suggest_quest_reroll_excludes_and_falls_back():
    g = Game()
    rng = random.Random(7)
    pool = [c.title for c in catalog.QUEST_BOARD if c.path_id == "steward"]
    first = g.suggest_quest("steward", None, rng)
    for _ in range(20):
        assert g.suggest_quest("steward", None, rng, exclude=[first.title]).title != first.title
    # everything excluded: still returns something
    assert g.suggest_quest("steward", None, rng, exclude=pool).title in pool
    # no quest at that difficulty for the path would fall back to the path pool
    with pytest.raises(ValueError):
        g.suggest_quest("wizard", None, rng)


def test_accept_adds_quest():
    g = Game()
    q = g.accept(g.suggest_quest("artisan", 1, random.Random(3)), today=D)
    assert q.id and q.created == D.isoformat() and g.quests == [q]
    assert g.complete_quest(q.id, D).xp == XP_BY_DIFFICULTY[1]


# --- bills --------------------------------------------------------------------------------------
def test_add_months_clamps_month_end():
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2028, 1, 31), 1) == date(2028, 2, 29)
    assert add_months(date(2026, 12, 15), 1) == date(2027, 1, 15)
    assert add_months(date(2026, 3, 31), -1) == date(2026, 2, 28)


def test_bill_status_due_soon_overdue_upcoming():
    g = Game()
    soon = g.add_bill("Phone", 500, day(3))
    late = g.add_bill("Water", 300, day(-1))
    later = g.add_bill("Rent", 8000, day(4))
    today_ = g.add_bill("Net", 1500, D)
    status = {b.name: (s, nd) for b, s, nd in g.bills_status(D)}
    assert status["Phone"] == ("due_soon", day(3))
    assert status["Water"] == ("overdue", day(-1))
    assert status["Rent"] == ("upcoming", day(4))
    assert status["Net"][0] == "due_soon"
    assert g.bills_status(D)[0][0].name == "Water"  # most urgent first
    assert soon.repeat == later.repeat == "none" and today_.paid == [] and late.amount == 300.0


def test_pay_one_off_bill():
    g = Game()
    b = g.add_bill("Water", 300, day(-2))
    c = g.pay_bill(b.id, D)
    assert (c.xp, c.coins, c.path_id) == (STEWARD_BILL_XP, STEWARD_BILL_COINS, "steward")
    assert g.profile.path_xp["steward"] == STEWARD_BILL_XP
    assert g.bills_status(D)[0][1] == "paid"
    again = g.pay_bill(b.id, day(1))
    assert (again.xp, again.coins) == (0, 0) and b.paid == [D.isoformat()]


def test_monthly_bill_repeats_with_month_end_rollover():
    g = Game()
    b = g.add_bill("Rent", 8000, date(2026, 1, 31), repeat="monthly")
    assert g.next_due(b) == date(2026, 1, 31)
    g.pay_bill(b.id, date(2026, 1, 29))
    assert g.next_due(b) == date(2026, 2, 28)
    assert g.bill_status(b, date(2026, 1, 30)) == "paid"  # current cycle paid, not past due
    assert g.bill_status(b, date(2026, 2, 1)) == "upcoming"
    assert g.bill_status(b, date(2026, 2, 26)) == "due_soon"
    assert g.bill_status(b, date(2026, 3, 1)) == "overdue"
    g.pay_bill(b.id, date(2026, 3, 1))
    assert g.next_due(b) == date(2026, 3, 31)  # back to the 31st, no drift


def test_weekly_and_yearly_repeat():
    g = Game()
    w = g.add_bill("Gym", 200, D, repeat="weekly")
    y = g.add_bill("Domain", 700, date(2028, 2, 29), repeat="yearly")
    g.pay_bill(w.id, D)
    g.pay_bill(y.id, date(2028, 2, 20))
    assert g.next_due(w) == day(7)
    assert g.next_due(y) == date(2029, 2, 28)


def test_overdue_repeating_bill_pays_oldest_cycle_first():
    g = Game()
    b = g.add_bill("Net", 1500, date(2026, 9, 10), repeat="monthly")
    assert g.bill_status(b, D) == "overdue"
    g.pay_bill(b.id, D)
    assert g.next_due(b) == date(2026, 10, 10) and g.bill_status(b, D) == "overdue"
    g.pay_bill(b.id, D)  # second cycle same day: recorded, no extra reward
    assert g.next_due(b) == date(2026, 11, 10) and g.bill_status(b, D) == "upcoming"
    assert g.profile.path_xp["steward"] == STEWARD_BILL_XP


def test_upcoming_total():
    g = Game()
    g.add_bill("Late", 100, day(-5))
    g.add_bill("Soon", 50.5, day(10))
    g.add_bill("Far", 999, day(45))
    g.add_bill("Weekly", 10, D, repeat="weekly")  # D, +7, +14, +21, +28 within 30 days
    paid = g.add_bill("Paid", 1000, day(2))
    g.pay_bill(paid.id, D)
    assert g.upcoming_total(D) == 100 + 50.5 + 5 * 10
    assert g.upcoming_total(D, days=45) == 100 + 50.5 + 999 + 7 * 10


def test_add_bill_validates():
    g = Game()
    with pytest.raises(ValueError):
        g.add_bill("x", 1, D, repeat="daily")
    with pytest.raises(ValueError):
        g.add_bill("x", -1, D)


# --- rewards and themes -------------------------------------------------------------------------
def test_redeem_needs_enough_coins():
    g = Game()
    r = g.add_reward("Jollibee meal", 50)
    assert g.redeem(r.id, D) is False and r.redeemed == []
    g.profile.coins = 60
    assert g.redeem(r.id, D) is True
    assert g.profile.coins == 10 and r.redeemed == [D.isoformat()]
    assert g.redeem(r.id, D) is False and g.profile.coins == 10


def test_buy_and_set_theme():
    g = Game()
    assert g.profile.theme_id == "arcane"
    assert g.profile.owned_themes == ["arcane", "ember", "rose"]
    assert g.set_theme("ember") is True and g.profile.theme_id == "ember"  # free, owned
    assert g.set_theme("ocean") is False
    price = catalog.THEME_PRICES["ocean"]
    g.profile.coins = price - 1
    assert g.buy_theme("ocean") is False and g.profile.coins == price - 1
    g.profile.coins = price + 5
    assert g.buy_theme("ocean") is False and g.profile.coins == price + 5  # premium-only
    g.dev_env = True
    assert g.set_dev_premium(True)
    assert g.buy_theme("ocean") is True and g.profile.coins == 5
    assert g.buy_theme("ocean") is True and g.profile.coins == 5  # owned: no double charge
    assert g.set_theme("ocean") is True and g.profile.theme_id == "ocean"
    with pytest.raises(ValueError):
        g.buy_theme("neon")


# --- practiced (old "skills") -----------------------------------------------------------------
def test_practiced_are_board_quests_done_at_least_once():
    g = Game()
    assert g.practiced() == []
    board = catalog.QUEST_BOARD
    a = g.accept(g.suggest_quest(board[3].path_id, board[3].difficulty,
                                 exclude=[c.title for c in board if c is not board[3]]), D)
    b = g.accept(g.suggest_quest(board[0].path_id, board[0].difficulty,
                                 exclude=[c.title for c in board if c is not board[0]]), D)
    g.add_quest("My own quest", "chef", today=D)
    assert g.practiced() == []  # accepted but not done: not a skill yet
    g.complete_quest(a.id, day(1))
    g.complete_quest(b.id, day(2))
    custom = next(q for q in g.quests if q.title == "My own quest")
    g.complete_quest(custom.id, D)  # custom quests are not skills
    assert [c.title for c in g.practiced()] == [a.title, b.title]  # first completion order
    g.accept(g.suggest_quest(board[3].path_id, board[3].difficulty,
                             exclude=[c.title for c in board if c is not board[3]]), D)
    assert len(g.practiced()) == 2  # same title twice is still one skill


# --- logbook ------------------------------------------------------------------------------------
def test_logbook():
    g = Game()
    g.add_log("workout", "Push-ups", 15, today=D)
    g.add_log("sleep", "", 420, today=day(1))
    g.add_log("note", "Felt good", today=day(1))
    assert [e.kind for e in g.logs(day(1))] == ["sleep", "note"]
    assert len(g.logs()) == 3 and g.logs()[-1].day == D.isoformat()
    with pytest.raises(ValueError):
        g.add_log("dream", "x", today=D)


# --- weekly review ------------------------------------------------------------------------------
def test_weekly_review():
    g = Game()
    start = day(-6)
    daily = g.add_quest("Stretch", "warrior", kind="daily", today=start)
    once = g.add_quest("Cook", "chef", difficulty=2, today=start)
    for n in (-6, -5, -4, -2, -1, 0):  # skipped day -3
        g.complete_quest(daily.id, day(n))
    g.complete_quest(daily.id, day(-10))  # outside the window
    g.complete_quest(once.id, day(-1))
    g.pay_bill(g.add_bill("Water", 1, D).id, D)
    g.add_log("note", "hi", today=D)
    r = g.weekly_review(D)
    assert (r["start"], r["end"]) == (start.isoformat(), D.isoformat())
    assert r["done"] == 7
    assert r["skipped"] == 1
    assert r["xp_by_path"]["warrior"] == 6 * daily.xp
    assert r["xp_by_path"]["chef"] == once.xp
    assert r["xp_by_path"]["steward"] == STEWARD_BILL_XP
    assert r["xp_total"] == 6 * daily.xp + once.xp + STEWARD_BILL_XP
    assert r["bills_paid"] == 1 and r["logs"] == 1
    assert r["best_streak"] == 6 and r["best_streak_quest"] == "Stretch"  # grace covers day -3


def test_weekly_review_does_not_count_days_before_quest_existed():
    g = Game()
    g.add_quest("New", "warrior", kind="daily", today=day(-1))
    assert g.weekly_review(D)["skipped"] == 1  # only yesterday; today still in progress
