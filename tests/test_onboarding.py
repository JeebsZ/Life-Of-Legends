"""Personalize flow: answers -> plan (core/onboarding.py), applying it, safety, save format."""

import json
from datetime import date

import pytest

from lol.core import catalog, nutrition, runlog, storage
from lol.core import onboarding as ob
from lol.core.game import Game
from lol.core.models import OnboardingAnswers

TODAY = date(2026, 11, 5)


def answers(**kw) -> OnboardingAnswers:
    return OnboardingAnswers(**kw)


# --- data integrity ----------------------------------------------------------------------------
def test_focus_areas_map_to_real_paths_and_every_path_is_reachable():
    reachable = set()
    for label, paths in ob.FOCUS_AREAS.values():
        assert label and paths
        assert all(p in catalog.PATH_IDS for p in paths)
        reachable.update(paths)
    assert reachable == set(catalog.PATH_IDS)
    assert all(p in catalog.PATH_IDS for p in ob.DEFAULT_PATHS)


def test_phone_picks_exist_in_the_base_board():
    titles = {q.title for q in catalog.BASE_QUEST_BOARD}
    assert set(ob.PHONE_PICKS) <= titles


# --- path ranking ------------------------------------------------------------------------------
def test_rank_paths_primary_beats_secondary_and_ties_keep_path_order():
    assert ob.rank_paths(["money"]) == ("steward", "monk")  # 1 Path -> filled from defaults
    # mind: scholar 2, monk 1; creativity: artisan 2 -> artisan/scholar tie keeps PATH_ORDER
    assert ob.rank_paths(["mind", "creativity"]) == ("scholar", "artisan", "monk")


def test_rank_paths_caps_at_three_and_counts_duplicates_once():
    ranked = ob.rank_paths(["energy", "food", "money", "home", "energy"])
    assert len(ranked) == ob.MAX_PATHS
    assert ranked[0] == "steward"  # money 2 + home 2
    assert ob.path_scores(["energy", "energy"])["warrior"] == ob.PRIMARY_W


def test_no_focus_gives_default_paths_and_phone_boosts_monk():
    assert ob.rank_paths([]) == ob.DEFAULT_PATHS[:ob.MIN_PATHS]
    assert ob.rank_paths(["creativity"], {"phone": True}) == ("artisan", "monk")
    assert ob.path_scores([], {"phone": True})["monk"] == ob.PHONE_BOOST


# --- difficulty, minutes, reminders --------------------------------------------------------------
@pytest.mark.parametrize(("minutes", "relate", "want"), [
    (5, {}, 1), (15, {}, 1), (30, {}, 2), (60, {}, 2), (0, {}, 1),
    (60, {"fade": True}, 1), (60, {"stuck": True}, 1), (60, {"phone": True}, 2),
    (60, {"fade": False, "stuck": False}, 2),
])
def test_difficulty_for(minutes, relate, want):
    assert ob.difficulty_for(minutes, relate) == want


def test_minutes_cap():
    assert ob.minutes_cap(5) == 5
    assert ob.minutes_cap(0) == ob.DEFAULT_MINUTES
    assert ob.minutes_cap(60) == 60
    assert ob.minutes_cap(60, {"stuck": True}) == ob.TINY_MIN
    assert ob.minutes_cap(5, {"stuck": True}) == 5


def test_reminder_time():
    assert ob.reminder_time("evening") == "19:00"
    assert ob.reminder_time("") == ""
    assert ob.reminder_time("bogus") == ""


# --- starter quests ------------------------------------------------------------------------------
def test_pick_quests_round_robin_within_caps():
    picks = ob.pick_quests(("warrior", "scholar", "monk"), 1, 15)
    assert [q.path_id for q in picks] == ["warrior", "scholar", "monk"]
    assert all(q.difficulty <= 1 and q.minutes <= 15 for q in picks)
    assert len({q.title for q in picks}) == 3


def test_pick_quests_two_paths_still_gives_three_distinct():
    picks = ob.pick_quests(("steward", "monk"), 1, 15)
    assert len(picks) == 3 and len({q.title for q in picks}) == 3
    assert [q.path_id for q in picks] == ["steward", "monk", "steward"]


def test_pick_quests_falls_back_to_gentlest_when_nothing_fits():
    picks = ob.pick_quests(("scholar",), 1, 5, count=1)  # no 5-minute scholar quest
    assert len(picks) == 1 and picks[0].path_id == "scholar" and picks[0].difficulty == 1


def test_phone_prefers_an_evening_touch_for_monk():
    picks = ob.pick_quests(("monk",), 2, 30, phone=True, count=1)
    assert picks[0].title == "Make a calm evening wind-down"
    tiny = ob.pick_quests(("monk",), 1, 5, phone=True, count=1)
    assert tiny[0].title == "Take three slow breaths"


def test_build_plan_never_starts_above_difficulty_two():
    for focus in (list(ob.FOCUS_AREAS), ["energy"], []):
        plan = ob.build_plan(answers(focus=focus, minutes=60))
        assert len(plan.quests) == ob.STARTER_COUNT
        assert all(q.difficulty <= ob.MAX_STARTER_DIFFICULTY for q in plan.quests)


def test_build_plan_stuck_and_tiny_budget_keep_first_steps_small():
    plan = ob.build_plan(answers(focus=["mind", "home"], minutes=60, relate={"stuck": True}))
    assert plan.difficulty == 1 and plan.max_minutes == ob.TINY_MIN
    fits = [q for q in plan.quests if q.minutes <= ob.TINY_MIN]
    assert len(fits) == len(plan.quests)


def test_luma_lines_are_short_and_kind():
    a = answers(relate={"fade": True, "stuck": True, "phone": True}, age_band="13-17")
    lines = ob.luma_lines(a, ())
    assert 1 <= len(lines) <= 3
    for line in lines + ob.luma_lines(answers(), ()):
        low = line.lower()
        assert "fail" not in low and "lazy" not in low and "should" not in low


def test_validate_drops_unknown_values():
    a = ob.validate(answers(focus=["mind", "nope", "mind"], relate={"fade": 1, "x": True},
                            age_band="9-12", minutes=7, day_time="dawn", reminders="maybe"))
    assert a.focus == ["mind"] and a.relate == {"fade": True}
    assert (a.age_band, a.minutes, a.day_time, a.reminders) == ("", 0, "", "")


# --- applying ------------------------------------------------------------------------------------
def test_apply_adds_starters_sets_reminder_time_and_onboards():
    g = Game()
    a = answers(focus=["money", "mind"], minutes=15, day_time="evening", reminders="on")
    plan, added = ob.apply(g, a, TODAY, first_run=True)
    assert g.profile.onboarded is True
    assert [q.title for q in added] == [c.title for c in plan.quests]
    assert all(q.created == TODAY.isoformat() for q in added)
    r = g.profile.reminders
    assert (r.enabled, r.daily_on, r.daily_time) == (True, True, "19:00")
    stored = g.profile.onboarding
    assert stored.paths == list(plan.paths) and stored.done_on == TODAY.isoformat()


def test_first_run_never_switches_reminders_on_silently():
    g = Game()
    ob.apply(g, answers(focus=["mind"]), TODAY, first_run=True)
    assert g.profile.reminders.enabled is False
    g2 = Game()
    ob.apply(g2, answers(focus=["mind"], reminders="off"), TODAY, first_run=False)
    assert g2.profile.reminders.enabled is False


def test_redo_keeps_progress_and_never_duplicates_open_quests():
    g = Game()
    a = answers(focus=["money"], minutes=15)
    _, first = ob.apply(g, a, TODAY, first_run=True)
    g.complete_quest(first[0].id, TODAY)
    xp, coins, level = g.profile.xp, g.profile.coins, g.profile.level
    g.set_reminders(enabled=True)  # turned on later in Settings
    _, again = ob.apply(g, answers(focus=["money"], minutes=15), TODAY, first_run=False)
    # the open ones are skipped, the one finished today may be offered again
    assert {q.title for q in again} <= {first[0].title}
    assert (g.profile.xp, g.profile.coins, g.profile.level) == (xp, coins, level)
    assert g.profile.reminders.enabled is True  # redo without an answer keeps the setting


# --- safety --------------------------------------------------------------------------------------
def _ready_body(g: Game, age: int) -> None:
    g.set_body(height_cm=170, sex="female")
    g.set_age(age, TODAY)
    g.log_weight(80, "kg", TODAY)


def test_minor_band_refuses_weight_loss_even_if_body_age_says_adult():
    g = Game()
    _ready_body(g, 30)
    assert g.propose_plan(TODAY, goal_kg=75).goal == "lose"  # adult, no band: allowed
    g.profile.onboarding.age_band = "13-17"
    assert g.is_minor(TODAY)
    with pytest.raises(nutrition.PlanRefused):
        g.propose_plan(TODAY, goal_kg=75)


def test_minor_band_keeps_run_ladder_gentle():
    g = Game()
    assert g.is_minor(TODAY) is False
    g.profile.onboarding.age_band = "13-17"
    adv = g.run_advice("run", TODAY)
    assert adv.suggest_challenge is False
    assert adv.reason == runlog.YOUTH_NOTE and runlog.YOUTH_NOTE in adv.notes


def test_adult_band_with_under_18_body_age_is_still_minor():
    g = Game()
    g.set_age(16, TODAY)
    g.profile.onboarding.age_band = "25-34"
    assert g.is_minor(TODAY) is True


# --- save format ---------------------------------------------------------------------------------
def test_answers_round_trip(tmp_path):
    path = tmp_path / "save.json"
    g = Game()
    ob.apply(g, answers(focus=["food", "outside"], relate={"phone": True}, age_band="18-24",
                        minutes=30, day_time="morning", reminders="off"), TODAY, first_run=True)
    g.save(path)
    again = Game.load(path, TODAY).profile.onboarding
    assert again == g.profile.onboarding
    assert again.relate == {"phone": True} and again.age_band == "18-24"


def test_schema5_save_without_onboarding_key_loads_with_defaults(tmp_path):
    path = tmp_path / "save.json"
    raw = {"schema": 5, "profile": {"name": "Jarvin", "onboarded": True, "coins": 12}}
    path.write_text(json.dumps(raw), encoding="utf-8")
    data = storage.load(path, TODAY)
    assert data.profile.onboarded is True  # existing players are never forced through it
    assert data.profile.onboarding == OnboardingAnswers()
    assert data.profile.coins == 12


def test_garbage_onboarding_value_loads_as_defaults(tmp_path):
    path = tmp_path / "save.json"
    raw = {"schema": 5, "profile": {"onboarding": "oops"}}
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert storage.load(path, TODAY).profile.onboarding == OnboardingAnswers()


def test_starter_chain_prefers_a_hand_written_beginner_chain():
    g = Game()
    for pid in catalog.PATH_IDS:
        c = ob.starter_chain(g, pid)
        assert c is not None and c.path_id == pid and c.rank == 1
        if any(b.path_id == pid for b in catalog.BASE_SIDE_QUESTS):
            assert c in catalog.BASE_SIDE_QUESTS
    first = ob.starter_chain(g, "scholar")
    g.start_side_quest(first.id, TODAY)
    nxt = ob.starter_chain(g, "scholar")
    assert nxt is None or nxt.id != first.id
