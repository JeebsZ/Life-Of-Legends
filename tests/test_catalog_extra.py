import re
from collections import Counter

from lol.core import catalog
from lol.core.catalog_extra import EXTRA_QUEST_BOARD, EXTRA_SIDE_QUESTS
from lol.core.models import CatalogChain, CatalogQuest, CatalogStep

ALL_PATHS = ("chef", "warrior", "scholar", "artisan", "ranger", "steward", "monk")
URL_RE = re.compile(r"\b[a-z]+://\S+")


def _all_notes() -> list[str]:
    notes = [q.note for q in EXTRA_QUEST_BOARD]
    notes += [s.note for c in EXTRA_SIDE_QUESTS for s in c.steps]
    return notes


def test_board_shapes():
    for q in EXTRA_QUEST_BOARD:
        assert isinstance(q, CatalogQuest)
        assert q.title.strip() and q.note.strip()
        assert q.path_id in ALL_PATHS
        assert q.difficulty in (1, 2, 3)
        assert 1 <= q.minutes <= 240


def test_board_counts_and_unique_titles():
    counts = Counter(q.path_id for q in EXTRA_QUEST_BOARD)
    for p in ALL_PATHS:
        assert counts[p] >= 8, p
    titles = [q.title.lower() for q in EXTRA_QUEST_BOARD]
    assert len(titles) == len(set(titles))
    existing = {q.title.lower() for q in catalog.BASE_QUEST_BOARD}
    assert not existing & set(titles)


def test_chain_shapes():
    for c in EXTRA_SIDE_QUESTS:
        assert isinstance(c, CatalogChain)
        assert c.path_id in ALL_PATHS
        assert c.rank in (1, 2, 3)
        assert c.skill_name.strip() and c.blurb.strip()
        assert len(c.steps) == 3
        for s in c.steps:
            assert isinstance(s, CatalogStep)
            assert s.title.strip() and s.note.strip()
            assert s.difficulty in (1, 2, 3)


def test_chain_ids_and_followups():
    ids = [c.id for c in EXTRA_SIDE_QUESTS]
    assert len(ids) == len(set(ids))
    existing_ids = {c.id for c in catalog.BASE_SIDE_QUESTS}
    assert not existing_ids & set(ids)
    bases = [c for c in EXTRA_SIDE_QUESTS if c.rank == 1]
    by_id = {c.id: c for c in EXTRA_SIDE_QUESTS}
    for b in bases:
        assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", b.id)
        assert not re.search(r"-r\d$", b.id)
        for rank in (2, 3):
            f = by_id[f"{b.id}-r{rank}"]
            assert f.rank == rank
            assert f.skill_name == b.skill_name and f.path_id == b.path_id
    assert len(EXTRA_SIDE_QUESTS) == 3 * len(bases)


def test_skill_counts_and_unique_names():
    bases = [c for c in EXTRA_SIDE_QUESTS if c.rank == 1]
    names = [b.skill_name.lower() for b in bases]
    assert len(names) == len(set(names))
    existing = {c.skill_name.lower() for c in catalog.BASE_SIDE_QUESTS}
    assert not existing & set(names)
    counts = Counter(b.path_id for b in bases)
    for p in ALL_PATHS:
        assert counts[p] >= 3, p
    assert len(bases) >= 21


def test_resources_use_https():
    urls = [u for n in _all_notes() for u in URL_RE.findall(n)]
    assert urls, "expected some resource links"
    for u in urls:
        assert u.startswith("https://"), u
    for n in _all_notes():
        if "Resource:" in n:
            assert " — https://" in n, n
