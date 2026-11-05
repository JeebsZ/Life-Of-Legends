from datetime import date, timedelta

import pytest

from lol.core import catalog
from lol.core.game import (
    COINS_BY_DIFFICULTY,
    DAILY_COIN_CAP,
    SKILL_BONUS_MULT,
    XP_BY_DIFFICULTY,
    Game,
)
from lol.core.models import RANK_NAMES, Completion

D = date(2026, 11, 4)


def day(n: int) -> date:
    return D + timedelta(days=n)


def _finish(g: Game, sq_id: str, today: date = D) -> list[Completion]:
    return [g.complete_step(sq_id, i, today) for i in range(len(g.side_quest(sq_id).steps))]


# --- catalog ------------------------------------------------------------------------------------
def test_side_quest_catalog_shape():
    chains = catalog.SIDE_QUESTS
    base = [c for c in chains if c.rank == 1]
    assert len(base) >= 12
    assert len(catalog.SIDE_QUEST_BY_ID) == len(chains)  # unique ids
    for p in catalog.PATH_IDS:
        assert sum(c.path_id == p for c in base) >= 2, p
    for c in chains:
        assert len(c.steps) == 3, c.id
        assert c.path_id in catalog.PATH_IDS
        assert all(s.title and s.note and s.difficulty in XP_BY_DIFFICULTY for s in c.steps)
    for b in base:  # one follow-up per skill for rank 2 and rank 3
        for r in (2, 3):
            f = catalog.SIDE_QUEST_BY_ID[f"{b.id}-r{r}"]
            assert (f.skill_name, f.path_id, f.rank) == (b.skill_name, b.path_id, r)
    assert len({c.skill_name for c in base}) == len(base)  # one base chain per skill


def test_spec_example_marketing():
    m = catalog.SIDE_QUEST_BY_ID["marketing"]
    assert m.path_id == "scholar"
    assert m.steps[0].title.startswith("Read a marketing book")


def test_side_quest_catalog_filter():
    g = Game()
    assert all(c.rank == 1 for c in g.side_quest_catalog())
    assert {c.path_id for c in g.side_quest_catalog("chef")} == {"chef"}
    with pytest.raises(ValueError):
        g.side_quest_catalog("wizard")


# --- start and complete -------------------------------------------------------------------------
def test_start_side_quest_copies_steps_with_balance():
    g = Game()
    sq = g.start_side_quest("knife-skills", D)
    c = catalog.SIDE_QUEST_BY_ID["knife-skills"]
    assert sq.id and sq.catalog_id == "knife-skills" and not sq.custom
    assert (sq.skill_name, sq.path_id, sq.rank_target, sq.created) == (
        "Knife Skills", "chef", 1, D.isoformat())
    assert [s.xp for s in sq.steps] == [XP_BY_DIFFICULTY[s.difficulty] for s in c.steps]
    assert [s.coins for s in sq.steps] == [COINS_BY_DIFFICULTY[s.difficulty] for s in c.steps]
    assert all(s.done_on is None for s in sq.steps)
    assert g.side_quests() == [sq] and g.side_quests(active_only=True) == [sq]


def test_start_unknown_or_duplicate_or_wrong_rank():
    g = Game()
    with pytest.raises(KeyError):
        g.start_side_quest("nope", D)
    g.start_side_quest("sketching", D)
    assert not g.can_start("sketching")
    with pytest.raises(ValueError):
        g.start_side_quest("sketching", D)  # already running
    with pytest.raises(ValueError):
        g.start_side_quest("sketching-r2", D)  # rank 2 needs the skill unlocked first
    with pytest.raises(ValueError):
        g.start_side_quest("sketching-r3", D)


def test_complete_step_awards_and_is_idempotent():
    g = Game()
    sq = g.start_side_quest("budgeting", D)
    c = g.complete_step(sq.id, 0, D)
    assert (c.xp, c.coins, c.path_id) == (sq.steps[0].xp, sq.steps[0].coins, "steward")
    assert c.skill_unlocked is None and c.skill_rank is None
    assert sq.steps[0].done_on == D.isoformat()
    xp, coins = g.profile.path_xp["steward"], g.profile.coins
    again = g.complete_step(sq.id, 0, day(1))
    assert (again.xp, again.coins) == (0, 0) and again.path_id == "steward"
    assert (g.profile.path_xp["steward"], g.profile.coins) == (xp, coins)
    assert sq.steps[0].done_on == D.isoformat()  # first date kept


def test_complete_step_bad_index_and_unknown_id():
    g = Game()
    sq = g.start_side_quest("budgeting", D)
    with pytest.raises(IndexError):
        g.complete_step(sq.id, 3, D)
    with pytest.raises(IndexError):
        g.complete_step(sq.id, -1, D)
    with pytest.raises(KeyError):
        g.complete_step("s999", 0, D)


def test_side_quest_steps_share_daily_coin_cap():
    g = Game()
    g.profile.coins_day, g.profile.coins_today = D.isoformat(), DAILY_COIN_CAP - 5
    sq = g.start_side_quest("plant-care", D)
    c = g.complete_step(sq.id, 0, D)
    assert c.coins == 5 and c.capped and c.xp == sq.steps[0].xp  # XP is never capped
    c2 = g.complete_step(sq.id, 1, D)
    assert c2.coins == 0 and c2.capped and c2.xp > 0
    c3 = g.complete_step(sq.id, 2, day(1))  # new day: cap resets
    assert c3.coins == sq.steps[2].coins and not c3.capped


def test_last_step_unlocks_skill_with_bonus():
    g = Game()
    sq = g.start_side_quest("knife-skills", D)
    first, second = g.complete_step(sq.id, 0, D), g.complete_step(sq.id, 1, D)
    assert first.skill_unlocked is None and second.skill_unlocked is None
    assert g.skills() == []
    last = g.complete_step(sq.id, 2, day(1))
    bonus = SKILL_BONUS_MULT * round(sum(s.xp for s in sq.steps) / 3)
    assert last.xp == sq.steps[2].xp + bonus
    assert last.coins == sq.steps[2].coins  # bonus is XP only
    assert (last.skill_unlocked, last.skill_rank) == ("Knife Skills", 1)
    [skill] = g.skills()
    assert (skill.name, skill.path_id, skill.rank, skill.unlocked_on, skill.chain_ids) == (
        "Knife Skills", "chef", 1, day(1).isoformat(), [sq.id])
    assert skill.rank_name == "Novice" == RANK_NAMES[1]
    assert sq.finished and not sq.active and g.side_quests(active_only=True) == []
    total = sum(s.xp for s in sq.steps) + bonus
    assert g.profile.path_xp["chef"] == total
    assert g.complete_step(sq.id, 2, day(2)).xp == 0  # no double unlock


def test_steps_can_finish_in_any_order():
    g = Game()
    sq = g.start_side_quest("sketching", D)
    assert g.complete_step(sq.id, 2, D).skill_unlocked is None
    assert g.complete_step(sq.id, 0, D).skill_unlocked is None
    assert g.complete_step(sq.id, 1, D).skill_unlocked == "Sketching"


def test_bonus_is_about_two_steps():
    g = Game()
    sq = g.start_side_quest("knife-skills", D)
    avg = sum(s.xp for s in sq.steps) / len(sq.steps)
    assert 1.5 * avg <= g.skill_bonus(sq) <= 2.5 * avg


# --- ranks --------------------------------------------------------------------------------------
def test_rank_up_only_through_followups_the_player_starts():
    g = Game()
    _finish(g, g.start_side_quest("marketing", D).id)
    skill = g.skill("marketing")  # case-insensitive lookup
    assert skill and skill.rank == 1
    # nothing is assigned automatically
    assert len(g.side_quests()) == 1 and g.side_quests(active_only=True) == []
    [f2] = g.followups_for("Marketing")
    assert (f2.id, f2.rank) == ("marketing-r2", 2) and g.can_start(f2.id)
    assert not g.can_start("marketing-r3")  # can't skip a rank
    assert not g.can_start("marketing")  # base chain done: no repeat for rank 1

    sq2 = g.start_side_quest(f2.id, day(1))
    assert sq2.rank_target == 2 and not g.can_start(f2.id)
    assert g.followups_for("Marketing") == [f2]  # still shown, but running
    *_, last = _finish(g, sq2.id, day(2))
    assert (last.skill_unlocked, last.skill_rank) == ("Marketing", 2)
    assert skill.rank == 2 and skill.rank_name == "Apprentice"
    assert skill.unlocked_on == D.isoformat()  # first unlock date kept

    [f3] = g.followups_for("Marketing")
    sq3 = g.start_side_quest(f3.id, day(3))
    *_, last = _finish(g, sq3.id, day(3))
    assert (last.skill_rank, skill.rank, skill.rank_name) == (3, 3, "Adept")
    assert skill.chain_ids == [g.side_quests()[0].id, sq2.id, sq3.id]
    assert g.followups_for("Marketing") == []  # maxed
    assert not any(g.can_start(f"marketing{s}") for s in ("", "-r2", "-r3"))
    assert len(g.skills()) == 1


def test_followups_for_locked_or_unknown_skill_is_empty():
    g = Game()
    assert g.followups_for("Knife Skills") == []
    g.start_side_quest("knife-skills", D)
    assert g.followups_for("Knife Skills") == []  # started but not unlocked


def test_starter_side_quest():
    g = Game()
    first = g.starter_side_quest("ranger")
    assert first is not None and first.path_id == "ranger" and first.rank == 1
    sq = g.start_side_quest(first.id, D)
    second = g.starter_side_quest("ranger")
    assert second is not None and second.id != first.id
    _finish(g, sq.id)
    g.start_side_quest(second.id, D)
    # keep starting until every ranger chain is running or done (catalog size may grow)
    while (nxt := g.starter_side_quest("ranger")) is not None:
        g.start_side_quest(nxt.id, D)
    assert g.starter_side_quest("ranger") is None


# --- custom chains ------------------------------------------------------------------------------
def test_custom_chain_validation():
    g = Game()
    for steps in ([], ["a"] * 6, ["ok", "  "]):
        with pytest.raises(ValueError):
            g.add_side_quest("Juggling", "artisan", steps, today=D)
    with pytest.raises(ValueError):
        g.add_side_quest("  ", "artisan", ["a"], today=D)
    with pytest.raises(ValueError):
        g.add_side_quest("Juggling", "wizard", ["a"], today=D)
    with pytest.raises(ValueError):
        g.add_side_quest("Juggling", "artisan", ["a"], difficulty=4, today=D)
    assert g.side_quests() == []
    for n in (1, 5):
        assert len(g.add_side_quest("Juggling", "artisan", ["x"] * n, today=D).steps) == n


def test_custom_chain_defaults_and_unlock():
    g = Game()
    sq = g.add_side_quest("  Juggling ", "artisan", [" Learn a 2-ball toss ", "Try 3 balls"],
                          today=D)
    assert sq.custom and sq.catalog_id is None and sq.rank_target == 1
    assert sq.skill_name == "Juggling" and [s.title for s in sq.steps] == [
        "Learn a 2-ball toss", "Try 3 balls"]
    assert all(s.xp == XP_BY_DIFFICULTY[1] and s.coins == COINS_BY_DIFFICULTY[1]
               for s in sq.steps)
    hard = g.add_side_quest("Chess", "scholar", ["a"], difficulty=3, today=D)
    assert hard.steps[0].xp == XP_BY_DIFFICULTY[3]
    *_, last = _finish(g, sq.id)
    assert (last.skill_unlocked, last.skill_rank) == ("Juggling", 1)
    assert g.skill("juggling").path_id == "artisan"


def test_custom_skill_gets_generated_followups():
    g = Game()
    _finish(g, g.add_side_quest("Juggling", "artisan", ["a", "b"], today=D).id)
    [f2] = g.followups_for("Juggling")
    assert f2.rank == 2 and f2.path_id == "artisan" and len(f2.steps) == 3
    assert "Juggling" in f2.steps[0].title and "{" not in f2.steps[0].title
    assert g.chain(f2.id) == f2 and g.can_start(f2.id)
    *_, last = _finish(g, g.start_side_quest(f2.id, D).id)
    assert last.skill_rank == 2
    [f3] = g.followups_for("Juggling")
    *_, last = _finish(g, g.start_side_quest(f3.id, D).id)
    assert last.skill_rank == 3 and g.followups_for("Juggling") == []


def test_generated_followup_needs_unlocked_skill():
    g = Game()
    with pytest.raises(KeyError):
        g.chain("custom-r2:Juggling")
    assert not g.can_start("custom-r2:Juggling")
    _finish(g, g.add_side_quest("Juggling", "artisan", ["a"], today=D).id)
    for bad in ("custom-r1:Juggling", "custom-r4:Juggling", "custom-rx:Juggling"):
        with pytest.raises(KeyError):
            g.chain(bad)


def test_repeat_custom_chain_for_unlocked_skill_gives_no_rank():
    g = Game()
    _finish(g, g.add_side_quest("Juggling", "artisan", ["a"], today=D).id)
    [c] = _finish(g, g.add_side_quest("juggling", "artisan", ["b"], today=D).id)
    assert c.xp == XP_BY_DIFFICULTY[1] and c.skill_unlocked is None  # step XP, no bonus
    assert g.skill("Juggling").rank == 1 and len(g.skills()) == 1


# --- abandon ------------------------------------------------------------------------------------
def test_abandon_keeps_earned_xp_and_allows_restart():
    g = Game()
    sq = g.start_side_quest("trail-walking", D)
    c = g.complete_step(sq.id, 0, D)
    xp, coins, level_xp = g.profile.path_xp["ranger"], g.profile.coins, g.profile.xp
    g.abandon_side_quest(sq.id)
    assert sq.abandoned and not sq.active and g.side_quests(active_only=True) == []
    assert (g.profile.path_xp["ranger"], g.profile.coins, g.profile.xp) == (xp, coins, level_xp)
    assert xp == c.xp
    after = g.complete_step(sq.id, 1, D)  # abandoned: no progress
    assert (after.xp, after.coins) == (0, 0) and sq.steps[1].done_on is None
    assert g.can_start("trail-walking")
    fresh = g.start_side_quest("trail-walking", day(1))
    assert fresh.id != sq.id and fresh.done_count == 0
    assert sq in g.side_quests()  # history kept


def test_abandon_finished_chain_is_noop():
    g = Game()
    sq = g.start_side_quest("trail-walking", D)
    _finish(g, sq.id)
    g.abandon_side_quest(sq.id)
    assert not sq.abandoned and g.skill("Trail Walking")


# --- profile ------------------------------------------------------------------------------------
def test_profile_defaults_and_settings():
    g = Game()
    p = g.profile
    assert (p.avatar_id, p.onboarded, p.voice_on, p.voice_volume) == ("a1", False, True, 0.8)
    g.set_profile(voice_on=False, voice_volume=1.7)
    assert (p.voice_on, p.voice_volume) == (False, 1.0)
    g.set_profile(voice_volume=-1)
    assert p.voice_volume == 0.0
    with pytest.raises(ValueError):
        g.set_profile(name="  ")
    with pytest.raises(ValueError):
        g.set_profile(avatar_id="")
    g.finish_onboarding(" Jarvin ", "a5")
    assert (p.name, p.avatar_id, p.onboarded) == ("Jarvin", "a5", True)


def test_weekly_review_counts_side_quest_steps():
    g = Game()
    sq = g.start_side_quest("bodyweight-basics", D)
    g.complete_step(sq.id, 0, D)
    g.complete_step(sq.id, 1, day(-10))  # outside the window
    r = g.weekly_review(D)
    assert r["done"] == 1 and r["xp_by_path"]["warrior"] == sq.steps[0].xp
