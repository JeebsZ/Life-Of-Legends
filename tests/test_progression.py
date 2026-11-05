import pytest

from lol.core.progression import Hero, Quest, bar_steps, xp_for_level


def test_xp_curve_grows():
    assert xp_for_level(1) == 100
    assert xp_for_level(2) == 125
    with pytest.raises(ValueError):
        xp_for_level(0)


def test_level_up_rolls_over_xp():
    hero = Hero()
    assert hero.gain_xp(230) == 2  # 100 + 125 = 225, 5 left over
    assert (hero.level, hero.xp) == (3, 5)


def test_negative_xp_rejected():
    with pytest.raises(ValueError):
        Hero().gain_xp(-1)


def test_quest_awards_xp_only_once():
    hero, q = Hero(), Quest("Walk 5k", xp=40)
    hero.complete(q)
    hero.complete(q)
    assert hero.xp == 40 and q.done


def test_bar_steps_without_level_up():
    assert bar_steps(1, 10, 40) == [0.5]


def test_bar_steps_with_level_ups():
    # 1 -> 2 at 100, 2 -> 3 at 125; 230 XP leaves 5/156 into level 3
    assert bar_steps(1, 0, 230) == [1.0, 1.0, 5 / xp_for_level(3)]


def test_bar_steps_matches_hero_state():
    hero = Hero(xp=90)
    steps = bar_steps(hero.level, hero.xp, 25)
    hero.gain_xp(25)
    assert steps[-1] == hero.xp / hero.xp_to_next
