"""Study: notes parser, answer checking, question generators, runs, spaced repetition, XP, save."""

import json
import random
from datetime import date, timedelta

import pytest

from lol.core import storage, study
from lol.core.game import Game
from lol.core.models import StudyCard

D = date(2026, 11, 5)

NOTES = """# Biology
Mitochondria - the powerhouse of the cell
Osmosis: movement of water across a membrane
  from low to high solute concentration
1. Ribosome = makes proteins
Q: Capital of France? A: Paris
Q: What gas do plants absorb?
A: Carbon dioxide
**Nucleus** contains the genetic material
## Photosynthesis
Plants turn light into chemical energy.
Enzyme\tA protein that speeds up reactions
Meeting at 10:30 today
Cell wall
Rigid outer layer in plant cells
- **Golgi body**: packages proteins
Diffusion:
Movement of particles from high to low concentration.
"""


def drafts_by_term(text: str) -> dict[str, study.Draft]:
    return {d.term: d for d in study.parse_notes(text).drafts}


def make_cards(n: int) -> list[StudyCard]:
    words = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel"]
    return [StudyCard(f"sc{i}", f"Term {words[i]}",
                      f"Definition about {words[i]} and its special meaning number {i}")
            for i in range(n)]


def game_with_deck(n: int = 6) -> tuple[Game, str]:
    g = Game()
    deck = g.add_deck("Bio", D)
    for c in make_cards(n):
        g.add_card(deck.id, c.term, c.definition)
    return g, deck.id


# --- parser ---------------------------------------------------------------------------------------
def test_parser_finds_every_format():
    d = drafts_by_term(NOTES)
    assert d["Mitochondria"].definition == "the powerhouse of the cell"
    assert d["Mitochondria"].source == "dash"
    assert d["Osmosis"].source == "colon"
    assert d["Osmosis"].definition.endswith("from low to high solute concentration")  # wrapped
    assert d["Ribosome"].source == "equals"  # numbered list item
    assert d["Capital of France?"].definition == "Paris"
    assert d["What gas do plants absorb?"].definition == "Carbon dioxide"
    assert d["Nucleus"].definition == "contains the genetic material"
    assert d["Photosynthesis"].definition == "Plants turn light into chemical energy."
    assert d["Enzyme"].source == "tab"
    assert d["Golgi body"].definition == "packages proteins"
    assert d["Diffusion"].source == "heading"
    assert d["Cell wall"].confidence == "low"  # plain short line + longer line


def test_parser_confidence_and_skipped():
    r = study.parse_notes(NOTES)
    assert "# Biology" in r.skipped  # a heading with no definition under it
    assert "Meeting at 10:30 today" in r.skipped  # a time is not a separator
    by = {x.term: x for x in r.drafts}
    assert by["Mitochondria"].confidence == "high"
    assert by["Photosynthesis"].confidence == "medium"
    assert all(x.confidence in study.CONFIDENCES for x in r.drafts)
    assert by["Osmosis"].line == 3


def test_parser_dash_inside_words_is_not_a_separator():
    d = drafts_by_term("Self-esteem - how you value yourself\nwell-known fact without pair")
    assert list(d) == ["Self-esteem"]


def test_parser_long_term_is_medium_and_empty_input():
    d = drafts_by_term("the process by which green plants and some other organisms use "
                       "light - photosynthesis")
    assert next(iter(d.values())).confidence == "medium"
    assert study.parse_notes("").drafts == []
    assert study.parse_notes("   \n\n").skipped == []


def test_mark_duplicates():
    r = study.parse_notes("Atom - smallest unit\natom: tiny thing\nIon - charged atom")
    study.mark_duplicates(r.drafts, ["Ion"])
    assert [x.duplicate for x in r.drafts] == [False, True, True]


def test_parse_table_csv_tsv_and_roundtrip():
    r = study.parse_table("term,definition\nAtom,smallest unit\n\"Cell, plant\",\"has a wall\"\n")
    assert [(x.term, x.definition) for x in r.drafts] == [("Atom", "smallest unit"),
                                                          ("Cell, plant", "has a wall")]
    assert study.parse_table("A\tone\nB\ttwo").drafts[1].term == "B"
    cards = [StudyCard("sc1", "=SUM", "-negative, quoted"), StudyCard("sc2", "Ion", "charged")]
    for delim in (",", "\t"):
        text = study.deck_to_text(cards, delim)
        assert "'=SUM" in text  # formula guard
        back = study.parse_table(text).drafts
        assert [(x.term, x.definition) for x in back] == [(c.term, c.definition) for c in cards]
    # no tab or comma at all: treated as notes
    assert study.parse_table("Atom - smallest unit").drafts[0].source == "dash"


# --- answer checking ----------------------------------------------------------------------------
@pytest.mark.parametrize(("given", "expected", "verdict"), [
    ("Paris", "paris", "exact"),
    ("  the Mitochondria! ", "Mitochondria", "exact"),
    ("cafe", "Café", "exact"),
    ("mitocondria", "Mitochondria", "close"),
    ("photosynthesys", "photosynthesis", "close"),
    ("cat", "car", "wrong"),  # short answers must be exact
    ("", "Paris", "wrong"),
    ("ribosome", "nucleus", "wrong"),
    ("automobile", "car / automobile", "exact"),
])
def test_check_text(given, expected, verdict):
    assert study.check_text(given, expected) == verdict


def test_edit_distance():
    assert study.edit_distance("kitten", "sitting") == 3
    assert study.edit_distance("", "abc") == 3


# --- generators ---------------------------------------------------------------------------------
def test_mc_has_four_unique_shuffled_options_and_is_seeded():
    cards = make_cards(6)
    q = study.make_question(cards[0], "mc", cards, random.Random(3))
    assert q.kind == "mc" and len(q.options) == 4 and len(set(q.options)) == 4
    assert q.options[q.correct] == cards[0].definition
    again = study.make_question(cards[0], "mc", cards, random.Random(3))
    assert again == q
    positions = {study.make_question(cards[0], "mc", cards, random.Random(s)).correct
                 for s in range(30)}
    assert len(positions) > 1  # the right answer is not always in the same slot


def test_mc_falls_back_with_too_few_cards():
    cards = make_cards(3)
    assert study.make_question(cards[0], "mc", cards, random.Random(1)).kind == "tf"
    one = make_cards(1)
    assert study.make_question(one[0], "mc", one, random.Random(1)).kind == "type"


def test_mc_distractors_skip_duplicate_definitions():
    cards = make_cards(4)
    cards[1].definition = cards[0].definition.upper()  # same text, other case
    assert study.make_question(cards[0], "mc", cards, random.Random(1)).kind == "tf"


def test_tf_true_and_false():
    cards = make_cards(5)
    seen = set()
    for s in range(40):
        q = study.make_question(cards[0], "tf", cards, random.Random(s))
        truth = q.statement == cards[0].definition
        assert q.correct == (0 if truth else 1)
        seen.add(truth)
    assert seen == {True, False}


def test_fill_blanks_the_longest_specific_word():
    card = StudyCard("sc1", "Osmosis", "movement of water across a semipermeable membrane")
    q = study.make_question(card, "fill", [card], random.Random(1))
    assert q.kind == "fill" and q.answer == "semipermeable"
    assert study.BLANK in q.prompt and "semipermeable" not in q.prompt
    assert study.grade(q, "Semipermiable").correct  # typo tolerated
    assert study.grade(q, "Semipermiable").close
    assert not study.grade(q, "water").correct


def test_fill_skips_term_words_and_falls_back():
    card = StudyCard("sc1", "Paris", "capital")
    assert study.make_question(card, "fill", [card], random.Random(1)).kind == "type"
    card2 = StudyCard("sc2", "Photosynthesis", "Photosynthesis makes sugar in leaves")
    q = study.make_question(card2, "fill", [card2], random.Random(1))
    assert q.answer != "Photosynthesis"


def test_type_direction():
    qa = StudyCard("sc1", "Capital of France?", "Paris")
    q = study.make_question(qa, "type", [qa], random.Random(1))
    assert q.prompt == "Capital of France?" and q.answer == "Paris"
    vocab = StudyCard("sc2", "Mitochondria", "the powerhouse of the cell, makes ATP")
    q = study.make_question(vocab, "type", [vocab], random.Random(1))
    assert q.answer == "Mitochondria"


def test_build_quiz_count_kinds_and_due_first():
    cards = make_cards(8)
    for c in cards[:6]:
        c.box, c.due = 3, (D + timedelta(days=3)).isoformat()  # not due
    qs = study.build_quiz(cards, ["mc", "tf", "fill"], 4, D, random.Random(2))
    assert len(qs) == 4 and len({q.card_id for q in qs}) == 4
    assert {"sc6", "sc7"} <= {q.card_id for q in qs}  # due/new cards lead
    assert {q.kind for q in qs} <= {"mc", "tf", "fill", "type"}
    assert len(study.build_quiz(cards, [], 50, D, random.Random(2))) == 8
    assert study.build_quiz(cards, ["mc"], 5, D, random.Random(9)) == \
        study.build_quiz(cards, ["mc"], 5, D, random.Random(9))


# --- runs --------------------------------------------------------------------------------------
def answer_right(run: study.StudyRun) -> None:
    q = run.current
    run.answer(q.correct if q.kind in ("mc", "tf") else (True if q.kind == "flip" else q.answer))


def answer_wrong(run: study.StudyRun) -> None:
    q = run.current
    run.answer((q.correct + 1) % len(q.options) if q.kind in ("mc", "tf")
               else (False if q.kind == "flip" else "zzzz"))


def test_exam_run_scores_first_answers():
    cards = make_cards(5)
    run = study.StudyRun(study.build_quiz(cards, ["mc", "tf", "type"], 5, D, random.Random(1)))
    answer_wrong(run)
    while not run.finished:
        answer_right(run)
    assert run.score() == (4, 5) and len(run.missed()) == 1
    with pytest.raises(RuntimeError):
        run.answer(0)


def test_learn_run_repeats_misses_until_right():
    cards = make_cards(4)
    run = study.StudyRun(study.build_quiz(cards, ["flip"], 4, D, random.Random(1)), learn=True)
    missed = run.current.card_id
    answer_wrong(run)
    answer_wrong(run)  # the second card too
    asked = 2
    while not run.finished:
        answer_right(run)
        asked += 1
    assert asked == 6  # two repeats
    assert run.score() == (2, 4)  # first tries only
    assert missed in run.missed() and run.progress == 1.0


def test_run_expire_marks_unanswered_missed():
    cards = make_cards(4)
    run = study.StudyRun(study.build_quiz(cards, ["type"], 4, D, random.Random(1)),
                         time_limit_s=60)
    answer_right(run)
    run.expire()
    assert run.finished and run.score() == (1, 4)


# --- spaced repetition + XP ---------------------------------------------------------------------
def test_leitner_review():
    c = StudyCard("sc1", "a", "b")
    study.review(c, True, D)
    assert c.box == 1 and c.due == (D + timedelta(days=1)).isoformat()
    for _ in range(10):
        study.review(c, True, D)
    assert c.box == study.MAX_BOX
    study.review(c, False, D)
    assert c.box == 0 and c.due == D.isoformat() and study.is_due(c, D)
    assert c.seen == 12 and c.right == 11


def test_study_xp_rules():
    assert study.study_xp(2, 0, 0) == 0  # too short
    assert study.study_xp(10, 0, 0) == 10
    assert study.study_xp(40, 0, 0) == study.STUDY_SESSION_XP_CAP
    assert study.study_xp(10, 1, 0) == 5
    assert study.study_xp(10, 2, 0) == 2
    assert study.study_xp(10, 3, 0) == 0
    assert study.study_xp(10, 0, study.STUDY_DAILY_XP_CAP - 3) == 3


def test_finish_study_awards_scholar_with_diminishing_returns():
    g, deck_id = game_with_deck(6)
    ids = [c.id for c in g.deck(deck_id).cards]
    results = [(cid, i != 0) for i, cid in enumerate(ids)]
    c1 = g.finish_study(deck_id, "exam", results, D, seconds=90)
    assert c1.xp == 6 and c1.path_id == "scholar" and c1.coins == study.STUDY_COINS
    assert g.profile.path_xp["scholar"] == 6
    s = g.study_sessions(D)[0]
    assert (s.total, s.right, s.seconds, s.mode) == (6, 5, 90, "exam") and c1.ref_id == s.id
    cards = {c.id: c for c in g.deck(deck_id).cards}
    assert cards[ids[0]].box == 0 and cards[ids[1]].box == 1
    c2 = g.finish_study(deck_id, "learn", results, D)
    c3 = g.finish_study(deck_id, "flip", results, D)
    c4 = g.finish_study(deck_id, "exam", results, D)
    assert (c2.xp, c3.xp, c4.xp) == (3, 1, 0)
    assert c2.coins == c3.coins == 0
    # another deck still pays, a new day resets
    other = g.add_deck("Chem", D)
    for c in make_cards(5):
        g.add_card(other.id, c.term, c.definition)
    assert g.finish_study(other.id, "exam", [(c.id, True) for c in other.cards], D).xp == 5
    assert g.finish_study(deck_id, "exam", results, D + timedelta(days=1)).xp == 6


def test_finish_study_daily_cap_and_unknown_cards():
    g = Game()
    total = 0
    for k in range(6):
        d = g.add_deck(f"D{k}", D)
        for c in make_cards(8):
            g.add_card(d.id, c.term, c.definition)
        total += g.finish_study(d.id, "exam", [(c.id, True) for c in d.cards], D).xp
    assert total == study.STUDY_DAILY_XP_CAP
    assert sum(s.coins for s in g.study_sessions(D)) == study.STUDY_DAILY_COIN_CAP
    d0 = g.decks[0]
    assert g.finish_study(d0.id, "exam", [("nope", True)], D + timedelta(days=2)).xp == 0
    with pytest.raises(ValueError):
        g.finish_study(d0.id, "cram", [], D)


def test_is_strong_and_deck_stats():
    assert study.is_strong(4, 5) and not study.is_strong(3, 5) and not study.is_strong(2, 2)
    g, deck_id = game_with_deck(4)
    deck = g.deck(deck_id)
    g.finish_study(deck_id, "exam", [(deck.cards[0].id, True)], D)
    st = study.deck_stats(deck, D)
    assert (st.total, st.due, st.new, st.mastered) == (4, 3, 3, 0)


# --- decks and cards ------------------------------------------------------------------------------
def test_deck_and_card_crud():
    g = Game()
    with pytest.raises(ValueError):
        g.add_deck("   ", D)
    d = g.add_deck("  World   History ", D, subject="HIST 101")
    assert d.title == "World History" and d.path_id == "scholar" and d.color
    c = g.add_card(d.id, "Magna Carta", "1215 charter", tags=["england", " "])
    assert c.tags == ["england"]
    with pytest.raises(ValueError):
        g.add_card(d.id, "x", "  ")
    g.edit_card(d.id, c.id, definition="Charter of 1215", hint="King John")
    assert g.card(d.id, c.id).hint == "King John"
    added = g.add_cards(d.id, [study.Draft("A", "one"), study.Draft("B", " ")])
    assert len(added) == 1 and len(d.cards) == 2
    g.delete_card(d.id, c.id)
    g.edit_deck(d.id, title="Hist", subject="")
    assert d.title == "Hist" and d.subject == ""
    g.delete_deck(d.id)
    assert g.decks == []


# --- save -----------------------------------------------------------------------------------------
def test_save_roundtrip_and_old_save_without_decks(tmp_path):
    g, deck_id = game_with_deck(4)
    g.finish_study(deck_id, "exam", [(c.id, True) for c in g.deck(deck_id).cards], D)
    path = tmp_path / "save.json"
    g.save(path)
    back = Game.load(path)
    assert back.data.decks == g.data.decks
    assert back.data.study_sessions == g.data.study_sessions
    # next_id never collides with card ids
    assert back.data.next_id >= g.data.next_id
    raw = json.loads(path.read_text(encoding="utf-8"))
    del raw["decks"], raw["study_sessions"]
    old = storage.from_dict(raw)
    assert old.decks == [] and old.study_sessions == []


def test_min_next_id_counts_cards():
    g, _ = game_with_deck(3)
    raw = storage.to_dict(g.data)
    raw["next_id"] = 1
    data = storage.from_dict(raw)
    biggest = max(int(c.id[2:]) for c in data.decks[0].cards)
    assert data.next_id > biggest


def test_backup_includes_decks_and_validates():
    g, deck_id = game_with_deck(3)
    g.finish_study(deck_id, "exam", [(c.id, True) for c in g.deck(deck_id).cards], D)
    data = storage.import_json(storage.export_json(g.data))
    assert len(data.decks[0].cards) == 3
    s = storage.summary(data)
    assert (s["study_decks"], s["study_cards"], s["study_sessions"]) == (1, 3, 1)
    tables = storage.export_csv(data)
    assert tables["study_cards.csv"].count("\n") == 4
    assert tables["study_sessions.csv"].count("\n") == 2
    raw = json.loads(storage.export_json(g.data))
    raw["decks"] = ["junk"]
    with pytest.raises(ValueError):
        storage.import_json(json.dumps(raw))
    raw = json.loads(storage.export_json(g.data))
    raw["study_sessions"][0]["day"] = "not a day"
    with pytest.raises(ValueError):
        storage.import_json(json.dumps(raw))


def test_manual_text_recognizer():
    rec = study.ManualTextRecognizer()
    assert isinstance(rec, study.TextRecognizer)
    assert rec.recognize("x.jpg") == ""


# --- ratings, states, limits, quests, exam, weak cards -----------------------------------------
def test_flip_ratings_drive_the_schedule():
    c = StudyCard("sc1", "a", "b", box=2)
    study.review(c, True, D, "hard")
    assert c.box == 2 and c.due == (D + timedelta(days=1)).isoformat()
    study.review(c, True, D, "easy")
    assert c.box == 4 and c.due == (D + timedelta(days=study.BOX_DAYS[4])).isoformat()
    study.review(c, True, D, "good")
    assert c.box == 5
    study.review(c, False, D, "again")
    assert c.box == 0 and c.due == D.isoformat() and c.right == 3
    fresh = StudyCard("sc2", "a", "b")
    study.review(fresh, True, D, "hard")
    assert fresh.box == 1


def test_flip_run_records_ratings_and_finish_uses_them():
    g, deck_id = game_with_deck(4)
    deck = g.deck(deck_id)
    run = study.StudyRun(study.build_quiz(deck.cards, ["flip"], 4, D, random.Random(1)))
    rates = ["again", "hard", "good", "easy"]
    for r in rates:
        run.answer(r)
    assert run.score() == (3, 4)
    order = [q.card_id for q in run.queue]
    assert run.ratings == dict(zip(order, rates, strict=True))
    g.finish_study(deck_id, "flip", run.results(), D, ratings=run.ratings)
    boxes = [g.card(deck_id, cid).box for cid in order]
    assert boxes == [0, 1, 1, 2]


def test_card_states_and_deck_progress():
    g, deck_id = game_with_deck(4)
    cards = g.deck(deck_id).cards
    cards[1].seen, cards[1].box = 1, 1
    cards[2].seen, cards[2].box = 3, 3
    cards[3].seen, cards[3].box = 5, 5
    assert [study.card_state(c) for c in cards] == ["new", "learning", "reviewing", "confident"]
    assert study.deck_progress(g.deck(deck_id)) == {"new": 1, "learning": 1, "reviewing": 1,
                                                    "confident": 1}


def test_daily_review_limit_global_and_per_deck():
    g, deck_id = game_with_deck(8)
    g.set_study_limit(5)
    assert len(g.due_today(deck_id, D)) == 5
    g.edit_deck(deck_id, daily_limit=3)
    due = g.due_today(deck_id, D)
    assert len(due) == 3
    g.finish_study(deck_id, "review", [(c.id, True) for c in due[:2]], D)
    assert len(g.due_today(deck_id, D)) == 1  # 3 - 2 reviewed today
    g.edit_deck(deck_id, daily_limit=0)
    g.set_study_limit(0)  # no limit
    assert len(g.due_today(deck_id, D)) == 6
    assert g.due_today(deck_id, D)[0].seen == 0  # never-seen (box 0) before box-1 cards


def test_deck_category_exam_countdown():
    g = Game()
    d = g.add_deck("Forklift safety", D, subject="Warehouse onboarding", category="skill")
    assert d.category == "skill"
    with pytest.raises(ValueError):
        g.add_deck("x", D, category="hobby")
    g.edit_deck(d.id, exam_date=D + timedelta(days=12), category="project")
    assert study.days_to_exam(d, D) == 12 and d.category == "project"
    assert study.days_to_exam(d, D + timedelta(days=13)) is None
    g.edit_deck(d.id, exam_date="")
    assert study.days_to_exam(d, D) is None


def test_linked_quest_completes_once_per_day():
    g, deck_id = game_with_deck(4)
    q = g.link_quest(deck_id, D)
    assert q.kind == "daily" and q.path_id == "scholar" and "Bio" in q.title
    assert g.link_quest(deck_id, D) is q  # idempotent
    ids = [c.id for c in g.deck(deck_id).cards]
    c1 = g.finish_study(deck_id, "exam", [(i, True) for i in ids], D)
    assert c1.xp == 4 + q.xp and D.isoformat() in q.done_on
    c2 = g.finish_study(deck_id, "exam", [(i, True) for i in ids], D)
    assert c2.xp == 2  # repeat session, quest already done today
    g.delete_quest(q.id)
    assert g.linked_quest(deck_id) is None
    assert g.finish_study(deck_id, "exam", [(i, True) for i in ids],
                          D + timedelta(days=1)).xp == 4  # a missing quest is ignored
    g.unlink_quest(deck_id)
    assert g.deck(deck_id).quest_id == ""


def test_weak_cards():
    g, deck_id = game_with_deck(4)
    cards = g.deck(deck_id).cards
    cards[0].seen, cards[0].right, cards[0].box = 4, 1, 2  # 25% right
    cards[1].seen, cards[1].right, cards[1].box = 2, 1, 1  # box 1
    cards[2].seen, cards[2].right, cards[2].box = 5, 5, 4  # strong
    assert [c.id for c in study.weak_cards(g.deck(deck_id))] == [cards[0].id, cards[1].id]


def test_study_settings_saved_and_defaulted(tmp_path):
    g, deck_id = game_with_deck(2)
    g.set_study_limit(12)
    g.edit_deck(deck_id, exam_date=D, daily_limit=7)
    path = tmp_path / "save.json"
    g.save(path)
    back = Game.load(path)
    assert back.data.study_settings.daily_limit == 12
    assert back.deck(deck_id).exam_date == D.isoformat() and back.deck(deck_id).daily_limit == 7
    raw = json.loads(path.read_text(encoding="utf-8"))
    del raw["study_settings"]
    for d in raw["decks"]:
        for k in ("category", "daily_limit", "exam_date", "quest_id"):
            del d[k]
    old = storage.from_dict(raw)
    assert old.study_settings.daily_limit == study.DEFAULT_DAILY_LIMIT
    assert old.decks[0].category == "course" and old.decks[0].exam_date == ""
