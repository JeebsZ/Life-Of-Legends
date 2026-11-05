from datetime import date, timedelta

import pytest

from lol.core import catalog
from lol.core.game import SKILL_BONUS_MULT, Game
from lol.core.models import CatalogStep

D = date(2026, 11, 4)


def day(n: int) -> date:
    return D + timedelta(days=n)


def _chain(g: Game, n: int = 3, ordered: bool = True, **kw):
    return g.add_side_quest("Juggling", "artisan", [f"step {i}" for i in range(n)], today=D,
                            ordered=ordered, **kw)


def test_ordered_chain_only_next_step_completable():
    g = Game()
    sq = _chain(g)
    assert g.next_step(sq) == 0
    assert not g.can_complete_step(sq.id, 1)
    locked = g.complete_step(sq.id, 1, D)
    assert locked.xp == 0 and sq.steps[1].done_on is None
    assert g.complete_step(sq.id, 0, D).xp > 0
    assert g.next_step(sq) == 1 and g.can_complete_step(sq.id, 1)
    g.complete_step(sq.id, 1, D)
    last = g.complete_step(sq.id, 2, D)
    assert last.skill_unlocked == "Juggling" and g.next_step(sq) is None


def test_any_order_is_default():
    g = Game()
    sq = _chain(g, ordered=False)
    assert not sq.ordered and g.can_complete_step(sq.id, 2)


def test_skip_resolves_without_xp_and_unlocks_next():
    g = Game()
    sq = _chain(g)
    xp = g.profile.path_xp.get("artisan", 0)
    c = g.skip_step(sq.id, 0, D)
    assert (c.xp, c.coins) == (0, 0) and sq.steps[0].skipped_on == D.isoformat()
    assert g.profile.path_xp.get("artisan", 0) == xp
    assert g.next_step(sq) == 1 and g.can_complete_step(sq.id, 1)
    assert not g.can_complete_step(sq.id, 0)  # skipped can't be completed
    assert g.skip_step(sq.id, 0, D).xp == 0  # idempotent
    assert sq.resolved_count == 1 and sq.done_count == 0


def test_skip_can_finish_chain_with_scaled_bonus():
    g = Game()
    sq = _chain(g)
    g.complete_step(sq.id, 0, D)
    g.skip_step(sq.id, 1, D)
    full = SKILL_BONUS_MULT * round(sum(s.xp for s in sq.steps) / 3)
    assert g.skill_bonus(sq) == round(full * 2 / 3)
    c = g.skip_step(sq.id, 2, D)
    assert sq.finished and c.skill_unlocked == "Juggling"
    assert c.xp == round(full * 1 / 3) and c.coins == 0


def test_all_skipped_chain_finishes_without_skill():
    g = Game()
    sq = _chain(g, n=2)
    g.skip_step(sq.id, 0, D)
    c = g.skip_step(sq.id, 1, D)
    assert sq.finished and c.skill_unlocked is None and g.skills() == [] and c.xp == 0


def test_unskip():
    g = Game()
    sq = _chain(g)
    g.skip_step(sq.id, 0, D)
    assert g.unskip_step(sq.id, 0) and sq.steps[0].skipped_on is None
    assert not g.unskip_step(sq.id, 0)
    assert g.next_step(sq) == 0


def test_pause_and_resume():
    g = Game()
    sq = _chain(g)
    g.pause_side_quest(sq.id)
    assert sq.paused and sq.active
    assert g.complete_step(sq.id, 0, D).xp == 0 and g.skip_step(sq.id, 0, D).xp == 0
    assert sq.resolved_count == 0
    assert g.today_next_steps(D) == []
    g.resume_side_quest(sq.id)
    assert g.complete_step(sq.id, 0, D).xp > 0


def test_reorder_and_edit_steps():
    g = Game()
    sq = _chain(g)
    g.complete_step(sq.id, 0, D)
    g.reorder_steps(sq.id, [2, 0, 1])
    assert [s.title for s in sq.steps] == ["step 2", "step 0", "step 1"]
    assert sq.steps[1].done_on == D.isoformat()  # state moved with the step
    assert g.next_step(sq) == 0
    for bad in ([0, 1], [0, 0, 1], [0, 1, 3]):
        with pytest.raises(ValueError):
            g.reorder_steps(sq.id, bad)
    g.edit_step(sq.id, 0, title=" Warm up ", note="slow")
    assert (sq.steps[0].title, sq.steps[0].note) == ("Warm up", "slow")
    with pytest.raises(ValueError):
        g.edit_step(sq.id, 0, title=" ")


def test_target_date_and_edit_side_quest():
    g = Game()
    sq = _chain(g, target_date=day(10))
    assert sq.target_date == day(10).isoformat()
    g.edit_side_quest(sq.id, ordered=False, target_date=None)
    assert not sq.ordered and sq.target_date is None
    g.edit_side_quest(sq.id, target_date=day(3))
    assert sq.target_date == day(3).isoformat()


def test_today_next_steps_order_and_filters():
    g = Game()
    a = _chain(g)
    b = g.start_side_quest("knife-skills", D, target_date=day(5))
    c = _chain(g, target_date=day(2))
    done = _chain(g, n=1)
    g.complete_step(done.id, 0, D)
    gone = _chain(g)
    g.abandon_side_quest(gone.id)
    g.complete_step(a.id, 0, D)
    rows = g.today_next_steps(D)
    assert [(sq.id, i) for sq, i, _ in rows] == [(c.id, 0), (b.id, 0), (a.id, 1)]
    assert rows[2][2] is a.steps[1]
    assert g.today_next_steps(day(30))[0][0] is c  # past target date: still listed, no flag


def test_generate_chain_is_deterministic_and_previewable():
    g = Game()
    steps = g.generate_chain("Guitar", "artisan")
    assert steps == g.generate_chain("Guitar", "artisan")
    assert len(steps) == 4 and all(isinstance(s, CatalogStep) for s in steps)
    assert steps[0].title == "Learn the basics of Guitar"
    assert "Reflect" in steps[-1].title and "Use Guitar in real life" == steps[2].title
    assert "small piece you make" in steps[2].note
    assert len(g.generate_chain("X", "chef", 3)) == 3 and len(g.generate_chain("X", "chef", 5)) == 5
    assert len(g.generate_chain("X", "chef", 1)) == 3 and len(g.generate_chain("X", "chef", 9)) == 5
    assert g.data.side_quests == []  # nothing added
    with pytest.raises(ValueError):
        g.generate_chain(" ", "chef")
    with pytest.raises(ValueError):
        g.generate_chain("X", "wizard")
    assert set(catalog.LEARNING_WHERE) == set(catalog.PATH_IDS)


def test_generated_chain_feeds_add_side_quest():
    g = Game()
    steps = g.generate_chain("Guitar", "artisan", 5)
    sq = g.add_side_quest("Guitar", "artisan", steps, today=D, ordered=True)
    assert [s.title for s in sq.steps] == [s.title for s in steps]
    assert [s.note for s in sq.steps] == [s.note for s in steps]
    assert sq.steps[2].xp > sq.steps[0].xp  # step difficulty from the generator
    for i in range(5):
        c = g.complete_step(sq.id, i, D)
    assert c.skill_unlocked == "Guitar"
    with pytest.raises(ValueError):
        g.add_side_quest("Bad", "chef", [CatalogStep("a", "", 7)], today=D)


def test_completion_bonus_stays_modest():
    g = Game()
    sq = g.add_side_quest("Guitar", "artisan", g.generate_chain("Guitar", "artisan"), today=D)
    total_steps = sum(s.xp for s in sq.steps)
    assert g.skill_bonus(sq) < total_steps  # most XP comes from the steps
