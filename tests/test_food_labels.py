from pathlib import Path

import pytest

from lol.core import foods
from lol.core.food_labels import (
    ALIASES,
    BACKGROUND,
    FILIPINO_LABELS,
    MAX_CANDIDATES,
    candidates_from_predictions,
    food_id_for_label,
    is_food_label,
)

LABELS_FILE = (
    Path(__file__).resolve().parents[1]
    / "extensions/flet_lumen_vision/src/flutter/flet_lumen_vision/assets/food_v1_labels.txt"
)


def _model_labels() -> list[str]:
    if not LABELS_FILE.exists():
        pytest.skip("flet_lumen_vision labels not present")
    return LABELS_FILE.read_text(encoding="utf-8").splitlines()


def test_label_file_matches_model_layout():
    labels = _model_labels()
    assert len(labels) == 2024
    assert labels[0] == BACKGROUND


def test_every_alias_key_is_a_real_model_label():
    labels = set(_model_labels())
    assert set(ALIASES) - labels == set()
    assert set(FILIPINO_LABELS) - labels == set()


def test_every_alias_points_to_a_known_food():
    missing = {k: v for k, v in ALIASES.items() if not foods.has(v)}
    assert missing == {}


def test_filipino_labels_mostly_mapped():
    unmapped = [lbl for lbl in FILIPINO_LABELS if food_id_for_label(lbl) is None]
    assert unmapped == ["Palitaw"]  # no palitaw in foods.py yet -> name-only


def test_non_food_labels_are_rejected():
    assert not is_food_label(BACKGROUND)
    assert not is_food_label("/g/11b8_rxx4d")
    assert not is_food_label("  ")
    assert is_food_label("Sinigang")
    assert food_id_for_label(BACKGROUND) is None


def test_alias_beats_matcher_and_matcher_is_fallback():
    assert food_id_for_label("Philippine adobo", matcher=lambda s: "nope") == "adobo_chicken"
    assert food_id_for_label("Some new dish", matcher=lambda s: "x1") == "x1"
    assert food_id_for_label("Some new dish", matcher=lambda s: None) is None


def test_candidates_filter_merge_and_rank():
    preds = [
        (BACKGROUND, 0.30),
        ("Fried rice", 0.25),
        ("Yangzhou fried rice", 0.15),  # merges into fried_rice -> 0.40
        ("Philippine adobo", 0.20),
        ("/g/11b8_rxx4d", 0.05),
        ("Mystery stew", 0.04),  # below MIN_CONFIDENCE
    ]
    out = candidates_from_predictions(preds, matcher=lambda s: None)
    assert [c.food_id for c in out] == ["fried_rice", "adobo_chicken"]
    assert out[0].confidence == pytest.approx(0.40)
    assert out[0].name == foods.food("fried_rice").name


def test_unmapped_label_stays_as_name_only_candidate():
    out = candidates_from_predictions([("Palitaw", 0.6)], matcher=lambda s: None)
    assert len(out) == 1
    assert out[0].food_id is None and out[0].name == "Palitaw"
    assert out[0].confidence == pytest.approx(0.6)


def test_relative_floor_drops_weak_alternatives():
    out = candidates_from_predictions(
        [("Sinigang", 0.80), ("Bistek", 0.15)], matcher=lambda s: None
    )
    assert [c.food_id for c in out] == ["sinigang_pork"]  # 0.15 < 0.25 * 0.80


def test_limit_and_garbage_input():
    preds = [(f"Dish {i}", 0.2) for i in range(10)] + [("x", "bad"), ("y", float("nan"))]
    out = candidates_from_predictions(preds, matcher=lambda s: None)
    assert len(out) == MAX_CANDIDATES
    assert candidates_from_predictions([]) == []
    assert candidates_from_predictions([(BACKGROUND, 0.99)]) == []


def test_default_matcher_uses_food_db():
    # Not in ALIASES, but foods.match_food knows it.
    assert food_id_for_label("Tinola") == "tinola"
