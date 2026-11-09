"""Unit tests for the 7-Day & 30-Day Daily Login Streak System.

Verifies:
- 30-Day rewards matrix definitions (coins, XP, Day 7 title, Day 30 companion pet)
- Daily status checks for first login, consecutive days, same day, and broken streak
- Streak incrementing on consecutive days
- Milestone cosmetics unlocking (Day 7 'title_sprinter', Day 30 'pet_kitsune')
- Streak resetting to Day 1 when missing > 1 day
- Duplicate claim prevention on the same calendar day
- Rollover to new 30-day cycle on Day 31
- Save/load persistence of streak, last claim date, and claimed days
- Level progression and XP rollover
"""

from datetime import date, timedelta
from pathlib import Path

import pytest

from lol.core import daily_login, storage
from lol.core.game import Game
from lol.core.models import Profile


@pytest.fixture(autouse=True)
def _isolated_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path))


def test_daily_rewards_matrix_definitions():
    """Verify reward matrix structure for all 30 days and milestone rewards."""
    assert len(daily_login.DAILY_REWARDS) == 30

    # Days 1-6: Progressive coins & XP (30-100 coins, 50-150 XP)
    for day in range(1, 7):
        rew = daily_login.get_reward(day)
        assert rew.day == day
        assert 30 <= rew.coins <= 100, f"Day {day} coins out of range: {rew.coins}"
        assert 50 <= rew.xp <= 150, f"Day {day} XP out of range: {rew.xp}"

    # Day 7: 250 coins + 200 XP + cosmetic title "title_sprinter"
    day7 = daily_login.get_reward(7)
    assert day7.coins == 250
    assert day7.xp == 200
    assert day7.cosmetic_id == "title_sprinter"
    assert day7.is_milestone

    # Days 8-29: Scaling coins & XP with milestone frames / titles
    for day in range(8, 30):
        rew = daily_login.get_reward(day)
        assert rew.day == day
        assert rew.coins >= 100
        assert rew.xp >= 150

    # Day 14 milestone
    day14 = daily_login.get_reward(14)
    assert day14.is_milestone
    assert day14.cosmetic_id == "frame_gold"

    # Day 21 milestone
    day21 = daily_login.get_reward(21)
    assert day21.is_milestone
    assert day21.cosmetic_id == "title_early"

    # Day 30: 1,000 coins + 500 XP + exclusive companion pet "pet_kitsune"
    day30 = daily_login.get_reward(30)
    assert day30.coins == 1000
    assert day30.xp == 500
    assert day30.cosmetic_id == "pet_kitsune"
    assert day30.is_milestone

    # Wrap-around helper check
    assert daily_login.get_reward(31).day == 1
    assert daily_login.get_reward(37).day == 7
    assert daily_login.get_reward(60).day == 30


def test_first_login_status():
    """New profile has no streak and is ready to claim Day 1."""
    prof = Profile()
    status = daily_login.check_daily_status(prof, date(2026, 11, 1))

    assert status.streak == 0
    assert status.current_day == 1
    assert not status.claimed_today
    assert status.can_claim
    assert status.last_claim_date == ""
    assert status.claimed_days == []
    assert status.reward_today.coins == 30


def test_claim_day_1_success(tmp_path: Path):
    """First claim properly awards coins, XP, advances streak to 1, and marks claimed."""
    save_file = tmp_path / "save.json"
    game = Game.load(save_file)
    init_coins = game.profile.coins
    init_xp = game.profile.xp

    res = game.claim_daily_login(date(2026, 11, 1))
    assert res is not None
    assert res.day == 1
    assert res.streak == 1
    assert res.coins_awarded == 30
    assert res.xp_awarded == 50

    p = game.profile
    assert p.daily_login_streak == 1
    assert p.last_login_claim == "2026-11-01"
    assert p.daily_login_claimed_days == [1]
    assert p.coins == init_coins + 30
    assert p.xp == init_xp + 50


def test_prevent_duplicate_claim_same_day(tmp_path: Path):
    """Claiming twice on the same calendar day returns None and preserves state."""
    save_file = tmp_path / "save.json"
    game = Game.load(save_file)

    first = daily_login.claim_daily_login(game, date(2026, 11, 1))
    assert first is not None
    coins_after_first = game.profile.coins

    # Second claim on same day
    second = daily_login.claim_daily_login(game, date(2026, 11, 1))
    assert second is None

    # Third claim using string iso date
    third = daily_login.claim_daily_login(game, "2026-11-01")
    assert third is None

    assert game.profile.daily_login_streak == 1
    assert game.profile.coins == coins_after_first

    # Check status on same day
    status = daily_login.check_daily_status(game.profile, date(2026, 11, 1))
    assert status.claimed_today
    assert not status.can_claim
    assert status.current_day == 1
    assert status.claimed_days == [1]


def test_consecutive_days_streak_progression_and_day_7_cosmetic(tmp_path: Path):
    """Consecutive daily logins advance streak 1..7 and award Day 7 cosmetic title."""
    save_file = tmp_path / "save.json"
    game = Game.load(save_file)

    start_date = date(2026, 11, 1)
    for day in range(1, 8):
        cur_date = start_date + timedelta(days=day - 1)
        res = daily_login.claim_daily_login(game, cur_date)
        assert res is not None, f"Failed claim on day {day}"
        assert res.day == day
        assert res.streak == day
        assert game.profile.daily_login_streak == day
        assert game.profile.last_login_claim == cur_date.isoformat()

    assert game.profile.daily_login_claimed_days == list(range(1, 8))
    # Verify Day 7 unlocked the title
    assert "title_sprinter" in game.profile.owned_cosmetics


def test_missing_more_than_one_day_resets_streak(tmp_path: Path):
    """Missing > 1 day resets streak to Day 1."""
    save_file = tmp_path / "save.json"
    game = Game.load(save_file)

    # Days 1, 2, 3 claimed consecutively
    daily_login.claim_daily_login(game, date(2026, 11, 1))
    daily_login.claim_daily_login(game, date(2026, 11, 2))
    res3 = daily_login.claim_daily_login(game, date(2026, 11, 3))
    assert res3 is not None and res3.streak == 3

    # Skip 2026-11-04 and 2026-11-05 (2 missed days)
    # Check status on 2026-11-06 (delta = 3 days)
    status = daily_login.check_daily_status(game.profile, date(2026, 11, 6))
    assert not status.claimed_today
    assert status.can_claim
    assert status.streak == 0
    assert status.current_day == 1
    assert status.claimed_days == []

    # Claim on 2026-11-06
    res_reset = daily_login.claim_daily_login(game, date(2026, 11, 6))
    assert res_reset is not None
    assert res_reset.streak == 1
    assert res_reset.day == 1
    assert res_reset.coins_awarded == 30
    assert game.profile.daily_login_streak == 1
    assert game.profile.daily_login_claimed_days == [1]


def test_30_day_track_pet_reward_and_day_31_rollover(tmp_path: Path):
    """Completing 30 days awards companion pet 'pet_kitsune', and Day 31 rolls over track."""
    save_file = tmp_path / "save.json"
    game = Game.load(save_file)

    start_date = date(2026, 1, 1)
    for day in range(1, 31):
        cur_date = start_date + timedelta(days=day - 1)
        res = daily_login.claim_daily_login(game, cur_date)
        assert res is not None
        assert res.day == day
        assert res.streak == day

    # Verify Day 30 companion pet reward
    assert "pet_kitsune" in game.profile.owned_cosmetics
    assert game.profile.daily_login_streak == 30
    assert len(game.profile.daily_login_claimed_days) == 30

    # Claim Day 31 (next cycle begins)
    day31_date = start_date + timedelta(days=30)
    res31 = daily_login.claim_daily_login(game, day31_date)
    assert res31 is not None
    assert res31.streak == 31
    assert res31.day == 1
    assert res31.coins_awarded == 30  # Day 1 reward
    assert game.profile.daily_login_streak == 31
    assert game.profile.daily_login_claimed_days == [1]


def test_storage_save_load_persistence(tmp_path: Path):
    """daily_login_streak, last_login_claim, and daily_login_claimed_days persist across saves."""
    save_file = tmp_path / "save_daily.json"
    game = Game.load(save_file)
    p = game.profile
    p.daily_login_streak = 14
    p.last_login_claim = "2026-11-14"
    p.daily_login_claimed_days = list(range(1, 15))
    game.save(save_file)

    loaded_game = Game.load(save_file)
    lp = loaded_game.profile
    assert lp.daily_login_streak == 14
    assert lp.last_login_claim == "2026-11-14"
    assert lp.daily_login_claimed_days == list(range(1, 15))

    # Test roundtrip with storage.to_dict and storage._profile directly
    raw = storage.to_dict(loaded_game.data)
    assert raw["profile"]["daily_login_streak"] == 14
    assert raw["profile"]["last_login_claim"] == "2026-11-14"
    assert raw["profile"]["daily_login_claimed_days"] == list(range(1, 15))


def test_level_up_from_login_xp(tmp_path: Path):
    """Daily login XP triggers level up when crossing the level threshold."""
    save_file = tmp_path / "save.json"
    game = Game.load(save_file)
    game.profile.level = 1
    game.profile.xp = 80  # near Level 1 boundary

    res = daily_login.claim_daily_login(game, date(2026, 11, 1))
    assert res is not None
    assert res.xp_awarded == 50
    # 80 + 50 = 130 XP >= 100 (Level 1 threshold), level becomes 2
    assert game.profile.level == 2
    assert res.levels_gained >= 1


def test_backdated_protection(tmp_path: Path):
    """Clock skew or backdated check treats claim as not allowed."""
    save_file = tmp_path / "save.json"
    game = Game.load(save_file)

    # Claim today
    daily_login.claim_daily_login(game, date(2026, 11, 10))

    # Attempt to claim with yesterday's date
    status = daily_login.check_daily_status(game.profile, date(2026, 11, 9))
    assert not status.can_claim
    assert status.claimed_today
