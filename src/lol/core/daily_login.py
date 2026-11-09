"""Daily Login Streak & 7-Day / 30-Day Rewards Track for Life of Legends.

Matrix:
- Days 1-6: Progressive coins & XP (30-100 coins, 50-150 XP)
- Day 7: 250 coins + 200 XP + exclusive cosmetic title ("title_sprinter")
- Days 8-29: Scaling coins, XP, and milestone rewards / protections
- Day 30: 1,000 coins + 500 XP + exclusive companion pet ("pet_kitsune")
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

from lol.core.progression import xp_for_level

if TYPE_CHECKING:
    from lol.core.game import Game
    from lol.core.models import Profile


@dataclass(frozen=True)
class DailyReward:
    day: int  # 1..30
    coins: int
    xp: int
    cosmetic_id: str | None = None
    title: str = ""
    description: str = ""
    is_milestone: bool = False
    icon: str = "auto_awesome"


# --- 30-Day Rewards Track ---
DAILY_REWARDS: dict[int, DailyReward] = {
    1: DailyReward(1, 30, 50, title="Day 1 Welcome", description="Kickstart your journey"),
    2: DailyReward(2, 40, 65, title="Day 2 Momentum", description="Building discipline"),
    3: DailyReward(3, 50, 80, title="Day 3 Focus", description="Keep the flame burning"),
    4: DailyReward(4, 65, 100, title="Day 4 Tenacity", description="Forging consistency"),
    5: DailyReward(5, 80, 120, title="Day 5 Dedication", description="Rising above limits"),
    6: DailyReward(6, 100, 150, title="Day 6 Eve of Glory", description="One day to milestone"),
    7: DailyReward(
        7,
        250,
        200,
        cosmetic_id="title_sprinter",
        title="Week 1 Victor",
        description="Exclusive 'Streak Sprinter' Title + Coin Bounty",
        is_milestone=True,
        icon="military_tech",
    ),
    8: DailyReward(8, 110, 160, title="Day 8 Resilient", description="Stepping into week 2"),
    9: DailyReward(9, 120, 170, title="Day 9 Flow", description="Steady and unstoppable"),
    10: DailyReward(10, 130, 180, title="Day 10 Double Digits", description="A whole decade of logins"),
    11: DailyReward(11, 140, 190, title="Day 11 Ascending", description="Sharpening every skill"),
    12: DailyReward(12, 150, 200, title="Day 12 Guardian", description="Steadfast daily resolve"),
    13: DailyReward(13, 160, 210, title="Day 13 Fortitude", description="Almost at the half-month mark"),
    14: DailyReward(
        14,
        300,
        250,
        cosmetic_id="frame_gold",
        title="2-Week Champion",
        description="Liquid Gold Ring Frame + 300 Coins",
        is_milestone=True,
        icon="workspace_premium",
    ),
    15: DailyReward(15, 175, 220, title="Day 15 Halfway", description="Midpoint of the monthly track"),
    16: DailyReward(16, 190, 230, title="Day 16 Habitual", description="Action becomes identity"),
    17: DailyReward(17, 205, 240, title="Day 17 Relentless", description="No excuses, just progress"),
    18: DailyReward(18, 220, 250, title="Day 18 Iron Will", description="Mind and body in sync"),
    19: DailyReward(19, 235, 260, title="Day 19 Catalyst", description="Energy surging forward"),
    20: DailyReward(20, 250, 270, title="Day 20 Zenith", description="Closing in on 3 weeks"),
    21: DailyReward(
        21,
        400,
        300,
        cosmetic_id="title_early",
        title="3-Week Master",
        description="Exclusive 'Early Bird' Title + 400 Coins",
        is_milestone=True,
        icon="stars",
    ),
    22: DailyReward(22, 270, 280, title="Day 22 Unshakable", description="Entering the final stretch"),
    23: DailyReward(23, 290, 290, title="Day 23 Trailblazer", description="Setting new personal bests"),
    24: DailyReward(24, 310, 300, title="Day 24 Veteran", description="Unwavering dedication"),
    25: DailyReward(25, 330, 320, title="Day 25 Titan", description="True strength in consistency"),
    26: DailyReward(26, 350, 340, title="Day 26 Apex", description="Almost at the summit"),
    27: DailyReward(27, 380, 360, title="Day 27 Luminary", description="A beacon of daily habit"),
    28: DailyReward(
        28,
        500,
        400,
        cosmetic_id="frame_void",
        title="4-Week Sovereign",
        description="Abyssal Orbit Frame + 500 Coins",
        is_milestone=True,
        icon="blur_circular",
    ),
    29: DailyReward(29, 450, 420, title="Day 29 Pinnacle", description="Eve of legend completion"),
    30: DailyReward(
        30,
        1000,
        500,
        cosmetic_id="pet_kitsune",
        title="Monthly Legend",
        description="Ember Kitsune Companion Pet + 1,000 Coins & 500 XP!",
        is_milestone=True,
        icon="pets",
    ),
}


def get_reward(day: int) -> DailyReward:
    """Return the DailyReward for day 1..30 (wraps smoothly for streaks beyond 30)."""
    norm_day = ((int(day) - 1) % 30) + 1
    return DAILY_REWARDS[norm_day]


@dataclass
class DailyStatus:
    streak: int  # Current streak count (or 0 if reset)
    current_day: int  # 1..30 track day to claim or claimed today
    claimed_today: bool  # True if claimed today
    can_claim: bool  # True if eligible to claim today
    last_claim_date: str  # ISO date of last claim
    claimed_days: list[int]  # Days claimed in current 30-day track cycle
    reward_today: DailyReward


@dataclass
class ClaimResult:
    day: int
    streak: int
    reward: DailyReward
    coins_awarded: int
    xp_awarded: int
    levels_gained: int
    cosmetic_awarded: str | None = None


def _to_date(val: date | str | None) -> date:
    if val is None:
        return date.today()
    if isinstance(val, str):
        return date.fromisoformat(val)
    return val


def check_daily_status(profile: Profile, today: date | str | None = None) -> DailyStatus:
    """Check daily login status for `profile` on date `today` (defaults to today)."""
    t = _to_date(today)
    last_str = getattr(profile, "last_login_claim", "") or ""
    streak = int(getattr(profile, "daily_login_streak", 0) or 0)
    raw_claimed = getattr(profile, "daily_login_claimed_days", []) or []
    claimed_days = list(raw_claimed)

    if not last_str:
        # First-ever login
        return DailyStatus(
            streak=0,
            current_day=1,
            claimed_today=False,
            can_claim=True,
            last_claim_date="",
            claimed_days=[],
            reward_today=get_reward(1),
        )

    try:
        last_d = date.fromisoformat(last_str)
    except (ValueError, TypeError):
        last_d = t

    delta = (t - last_d).days

    if delta == 0:
        # Already claimed today
        current_day = ((streak - 1) % 30) + 1 if streak > 0 else 1
        return DailyStatus(
            streak=streak,
            current_day=current_day,
            claimed_today=True,
            can_claim=False,
            last_claim_date=last_str,
            claimed_days=claimed_days,
            reward_today=get_reward(current_day),
        )

    if delta == 1:
        # Consecutive login (claimed yesterday)
        next_day = (streak % 30) + 1
        return DailyStatus(
            streak=streak,
            current_day=next_day,
            claimed_today=False,
            can_claim=True,
            last_claim_date=last_str,
            claimed_days=claimed_days if next_day > 1 else [],
            reward_today=get_reward(next_day),
        )

    if delta < 0:
        # Clock skew / backdated
        current_day = ((streak - 1) % 30) + 1 if streak > 0 else 1
        return DailyStatus(
            streak=streak,
            current_day=current_day,
            claimed_today=True,
            can_claim=False,
            last_claim_date=last_str,
            claimed_days=claimed_days,
            reward_today=get_reward(current_day),
        )

    # Missed > 1 day -> streak breaks and resets to Day 1
    return DailyStatus(
        streak=0,
        current_day=1,
        claimed_today=False,
        can_claim=True,
        last_claim_date=last_str,
        claimed_days=[],
        reward_today=get_reward(1),
    )


def claim_daily_login(game: Game, today: date | str | None = None) -> ClaimResult | None:
    """Award daily login rewards, advance streak, and save game state.

    Returns ClaimResult on success, or None if already claimed today.
    """
    t = _to_date(today)
    status = check_daily_status(game.profile, t)
    if not status.can_claim:
        return None

    p = game.profile
    last_str = getattr(p, "last_login_claim", "") or ""
    current_streak = int(getattr(p, "daily_login_streak", 0) or 0)

    if last_str:
        try:
            last_d = date.fromisoformat(last_str)
            delta = (t - last_d).days
        except (ValueError, TypeError):
            delta = 999
    else:
        delta = 999

    if delta == 1:
        new_streak = current_streak + 1
    else:
        new_streak = 1
        p.daily_login_claimed_days = []

    p.daily_login_streak = new_streak
    day = ((new_streak - 1) % 30) + 1

    if day == 1:
        p.daily_login_claimed_days = [1]
    else:
        if day not in p.daily_login_claimed_days:
            p.daily_login_claimed_days.append(day)

    p.last_login_claim = t.isoformat()

    reward = get_reward(day)

    # Award coins (uncapped daily login bonus)
    p.coins += reward.coins

    # Award XP and handle level-ups
    level = p.level
    xp = p.xp + reward.xp
    gained_levels = 0
    while xp >= xp_for_level(level):
        xp -= xp_for_level(level)
        level += 1
        gained_levels += 1
    p.level = level
    p.xp = xp

    # Award cosmetic if specified
    cosmetic_awarded: str | None = None
    if reward.cosmetic_id and reward.cosmetic_id not in p.owned_cosmetics:
        p.owned_cosmetics.append(reward.cosmetic_id)
        cosmetic_awarded = reward.cosmetic_id

    # Persist game
    game.save()

    return ClaimResult(
        day=day,
        streak=new_streak,
        reward=reward,
        coins_awarded=reward.coins,
        xp_awarded=reward.xp,
        levels_gained=gained_levels,
        cosmetic_awarded=cosmetic_awarded,
    )
