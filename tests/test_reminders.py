"""Reminder planning (v1.3): pure data for the notification scheduler."""

from datetime import date, datetime, timedelta

import pytest

from lol.core.game import COMEBACK_DAYS, Game

D = date(2026, 11, 4)  # a Wednesday
NOW = datetime(2026, 11, 4, 8, 0)


def _only(g: Game, **on) -> None:
    """Switch every category off except the given ones."""
    flags = {"bills_on": False, "daily_on": False, "water_on": False, "comeback_on": False}
    g.set_reminders(**{**flags, **on})


def test_defaults_and_master_switch():
    g = Game()
    r = g.profile.reminders
    assert (r.enabled, r.bills_on, r.daily_on, r.water_on, r.focus_on, r.comeback_on) == (
        True, True, True, False, True, False)
    assert (r.quiet_start, r.quiet_end) == ("22:00", "07:00")
    g.add_quest("Read", "scholar", today=D)
    g.add_bill("Rent", 100, D + timedelta(days=2))
    assert g.planned_reminders(NOW)
    g.set_reminders(enabled=False)
    assert g.planned_reminders(NOW) == []
    assert g.focus_reminder(NOW) is None


def test_set_reminders_validation():
    g = Game()
    g.set_reminders(quiet_start="9:30", water_active_days=[6, 0, 0])
    assert g.profile.reminders.quiet_start == "09:30"
    assert g.profile.reminders.water_active_days == [0, 6]
    for bad in ({"quiet_end": "7pm"}, {"bill_days_before": 40}, {"water_interval_min": 5},
                {"water_snooze_min": 0}, {"water_active_days": [7]}, {"volume": 3}):
        with pytest.raises(ValueError):
            g.set_reminders(**bad)


def test_bill_reminders_unpaid_cycles_only():
    g = Game()
    _only(g, bills_on=True)
    g.set_reminders(bill_days_before=2, bill_time="10:00")
    b = g.add_bill("Phone", 499, date(2026, 11, 6), "weekly")
    once = g.add_bill("Fee", 50, date(2026, 11, 9))
    archived = g.add_bill("Old", 1, date(2026, 11, 7))
    g.archive_bill(archived.id)
    rem = g.planned_reminders(NOW, horizon_days=8)
    ids = [r.id for r in rem]
    assert ids == [f"bill:{b.id}:2026-11-06", f"bill:{once.id}:2026-11-09",
                   f"bill:{b.id}:2026-11-13"]
    first = rem[0]
    assert first.when == datetime(2026, 11, 4, 10, 0) and first.category == "bill"
    assert "Phone" in first.title and "499.00" in first.body
    g.pay_bill(b.id, D)  # pays the Nov 6 cycle
    g.pay_bill(once.id, D)
    assert [r.id for r in g.planned_reminders(NOW, 8)] == [f"bill:{b.id}:2026-11-13"]
    assert g.planned_reminders(NOW, 7) == []  # Nov 11 10:00 is past the 7-day horizon
    g.mark_bill_unpaid(once.id)
    assert f"bill:{once.id}:2026-11-09" in [r.id for r in g.planned_reminders(NOW)]


def test_past_bill_reminder_times_are_skipped():
    g = Game()
    _only(g, bills_on=True)
    g.add_bill("Due today", 10, D)  # reminder would have been yesterday 09:00
    assert g.planned_reminders(NOW) == []


def test_quiet_hours_shift_to_quiet_end():
    g = Game()
    _only(g, bills_on=True, daily_on=True)
    g.set_reminders(bill_time="23:15", daily_time="06:00", bill_days_before=0)
    g.add_bill("Late", 10, date(2026, 11, 5))
    g.add_quest("Read", "scholar", kind="daily", today=D)
    rem = g.planned_reminders(NOW, horizon_days=2)
    bill = next(r for r in rem if r.category == "bill")
    assert bill.when == datetime(2026, 11, 6, 7, 0)  # 23:15 Nov 5 -> 07:00 next morning
    dailies = [r for r in rem if r.category == "daily"]
    assert [r.when for r in dailies] == [datetime(2026, 11, 5, 7, 0), datetime(2026, 11, 6, 7, 0)]
    assert g.in_quiet_hours(datetime(2026, 11, 4, 23, 0))
    assert not g.in_quiet_hours(datetime(2026, 11, 4, 7, 0))
    g.set_reminders(quiet_start="12:00", quiet_end="12:00")  # no quiet hours
    assert not g.in_quiet_hours(datetime(2026, 11, 4, 3, 0))


def test_daily_reminder_only_when_quests_are_open():
    g = Game()
    _only(g, daily_on=True)
    assert g.planned_reminders(NOW) == []  # no quests at all
    q = g.add_quest("Walk", "warrior", kind="daily", today=D)
    rem = g.planned_reminders(NOW, horizon_days=3)
    assert [r.id for r in rem] == ["daily:2026-11-04", "daily:2026-11-05", "daily:2026-11-06"]
    assert rem[0].when == datetime(2026, 11, 4, 9, 0)  # Nov 7 09:00 is past now + 3 days
    g.complete_quest(q.id, D)
    assert g.planned_reminders(NOW, horizon_days=3)[0].id == "daily:2026-11-05"


def test_water_reminders_window_active_days_and_goal():
    g = Game()
    _only(g, water_on=True)
    g.set_reminders(water_interval_min=180, water_active_days=[2, 3])  # Wed, Thu
    rem = g.planned_reminders(NOW, horizon_days=6)
    times = [r.when for r in rem]
    # window 07:00..22:00 every 3 h -> 10, 13, 16, 19, 22 (22:00 is quiet: dropped)
    assert times[:4] == [datetime(2026, 11, 4, h) for h in (10, 13, 16, 19)]
    assert {t.date() for t in times} == {D, D + timedelta(days=1)}
    assert len(rem) == 8 and rem[0].id == "water:2026-11-04T10:00"
    assert all(not g.in_quiet_hours(t) for t in times)
    g.set_water_settings(daily_goal_ml=1000)
    g.add_water(1000, D)
    rem = g.planned_reminders(NOW, horizon_days=6)
    assert all(r.when.date() != D for r in rem)  # no nagging after today's goal
    assert len(rem) == 4


def test_water_window_without_overnight_quiet_hours():
    g = Game()
    _only(g, water_on=True)
    g.set_reminders(quiet_start="11:30", quiet_end="12:30", water_interval_min=120)
    rem = g.planned_reminders(datetime(2026, 11, 4, 0, 0), horizon_days=1)
    # WATER_DAY_START 08:00 + 2 h steps up to WATER_DAY_END 21:00; 12:00 is quiet: dropped
    assert [r.when.hour for r in rem] == [10, 14, 16, 18, 20]


def test_ids_are_stable_and_unique():
    g = Game()
    g.set_reminders(water_on=True, comeback_on=True)
    g.add_quest("Read", "scholar", kind="daily", today=D)
    g.add_bill("Rent", 100, date(2026, 11, 8), "monthly")
    a = g.planned_reminders(NOW)
    b = g.planned_reminders(NOW)
    assert a == b and len({r.id for r in a}) == len(a)
    later = g.planned_reminders(NOW + timedelta(hours=5))
    assert {r.id for r in later} <= {r.id for r in a} | {r.id for r in later}
    common = {r.id for r in a} & {r.id for r in later}
    assert common and all(next(x for x in a if x.id == i).when ==
                          next(x for x in later if x.id == i).when for i in common)
    assert all(NOW < r.when <= NOW + timedelta(days=7) for r in a)
    assert a == sorted(a, key=lambda r: r.when)


def test_comeback_nudge_is_opt_in_and_gentle():
    g = Game()
    _only(g)
    q = g.add_quest("Walk", "warrior", today=D)
    g.complete_quest(q.id, D - timedelta(days=1))
    assert g.planned_reminders(NOW) == []
    g.set_reminders(comeback_on=True)
    rem = g.planned_reminders(NOW)
    assert len(rem) == 1 and rem[0].category == "comeback"
    assert rem[0].when.date() == D - timedelta(days=1) + timedelta(days=COMEBACK_DAYS)
    assert "ready" in rem[0].body
    assert Game().last_active_day() is None


def test_snooze_and_focus():
    g = Game()
    r = g.focus_reminder(datetime(2026, 11, 4, 23, 30), "Deep work")
    assert r.id == "focus:timer" and r.when.hour == 23 and "Deep work" in r.title  # not shifted
    s = g.snooze_reminder(r, datetime(2026, 11, 4, 12, 0))
    assert s.id == "focus:timer:snooze" and s.when == datetime(2026, 11, 4, 12, 15)
    s2 = g.snooze_reminder(s, datetime(2026, 11, 4, 21, 50))
    assert s2.id == s.id and s2.when == datetime(2026, 11, 5, 7, 0)  # lands in quiet hours
    g.set_reminders(focus_on=False)
    assert g.focus_reminder(NOW) is None
