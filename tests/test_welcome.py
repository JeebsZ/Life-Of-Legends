from datetime import date, datetime

from lol.core import welcome
from lol.ui import audio, voice


def test_slot_by_time_of_day():
    d = date(2026, 11, 5)
    at = {h: welcome.slot_for(datetime(2026, 11, 5, h), d) for h in range(24)}
    assert at[5] == at[11] == "morning"
    assert at[12] == at[16] == "day"
    assert at[17] == at[21] == "evening"
    assert at[22] == at[0] == at[4] == "night"


def test_away_after_two_quiet_days_and_new_player_gets_the_hour():
    now = datetime(2026, 11, 5, 9)
    assert welcome.slot_for(now, date(2026, 11, 3)) == "away"
    assert welcome.slot_for(now, date(2026, 11, 4)) == "morning"
    assert welcome.slot_for(now, None) == "morning"


def test_pick_stays_in_slot_and_alternates():
    noon = datetime(2026, 11, 5, 13)
    a = welcome.pick(noon, None)
    b = welcome.pick(noon, None, previous=a)
    assert welcome.SLOTS[a] == welcome.SLOTS[b] == "day" and a != b
    eve = welcome.pick(datetime(2026, 11, 5, 19), None, previous=None)
    assert welcome.pick(datetime(2026, 11, 5, 19), None, previous=eve) == eve  # only one


def test_cooldown():
    assert welcome.due(1000.0, None)
    assert not welcome.due(1000.0 + 29 * 60, 1000.0)
    assert welcome.due(1000.0 + 30 * 60, 1000.0)


def test_lines_and_clips_cover_every_slot():
    assert len(voice.LINES["hello_again"]) == len(welcome.SLOTS) == audio.CLIPS["hello_again"]
    assert set(welcome.SLOTS) == {"morning", "day", "evening", "night", "away"}
    assert all(len(line) <= 70 for line in voice.LINES["hello_again"])
