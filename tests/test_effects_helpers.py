"""Pure helpers behind the v1.4 effects: icosphere geometry and staged-analysis sequencing."""

import math

import pytest

from lol.ui import effects as fx


@pytest.mark.parametrize(("freq", "v", "e", "f"), [(1, 12, 30, 20), (2, 42, 120, 80),
                                                    (3, 92, 270, 180)])
def test_icosphere_counts(freq: int, v: int, e: int, f: int) -> None:
    verts, edges, faces = fx.icosphere_mesh(freq)
    assert (len(verts), len(edges), len(faces)) == (v, e, f)
    assert len(verts) - len(edges) + len(faces) == 2  # Euler: a closed sphere


def test_icosphere_is_on_unit_sphere_and_well_formed() -> None:
    verts, edges, faces = fx.icosphere_mesh(2)
    assert all(math.isclose(math.hypot(*p), 1.0, abs_tol=1e-9) for p in verts)
    assert all(0 <= i < j < len(verts) for i, j in edges)
    assert len(set(edges)) == len(edges)
    # every vertex: 5 neighbours (the 12 originals) or 6 (the new ones)
    degree = [0] * len(verts)
    for i, j in edges:
        degree[i] += 1
        degree[j] += 1
    assert sorted(set(degree)) == [5, 6]
    assert degree.count(5) == 12
    # faces only use known edges
    es = set(edges)
    for a, b, c in faces:
        for x, y in ((a, b), (b, c), (a, c)):
            assert (min(x, y), max(x, y)) in es


def test_icosphere_edges_are_short_and_even() -> None:
    verts, edges, _ = fx.icosphere_mesh(2)
    lengths = [math.dist(verts[i], verts[j]) for i, j in edges]
    assert max(lengths) / min(lengths) < 1.25  # geodesic: no long seams


def test_stage_labels_default() -> None:
    names, dots = fx.stage_labels(fx.LumenThinking.STAGES)
    assert names == ["ANALYSIS", "MATCHING PATHS", "PROPOSAL READY"]
    assert dots == [True, True, False]


def test_stage_labels_custom_and_single() -> None:
    names, dots = fx.stage_labels(("Scanning body data…", "calculating...", "Plan ready."))
    assert names == ["SCANNING BODY DATA", "CALCULATING", "PLAN READY"]
    assert dots == [True, True, False]  # the ready line never ticks
    assert fx.stage_labels(("Analysis…",)) == (["ANALYSIS"], [True])


def test_stage_at_splits_working_time_evenly() -> None:
    # 2 working stages over 2.0 s -> switch at 1.0 s, never past the last working stage
    assert [fx.stage_at(t, 2.0, 2) for t in (0, 0.5, 0.99, 1.0, 1.9, 5.0)] == [0, 0, 0, 1, 1, 1]
    assert fx.stage_at(0.8, 2.1, 3) == 1
    assert fx.stage_at(1.0, 2.0, 1) == 0
    assert fx.stage_at(1.0, 0, 3) == 0


def test_mix_colors() -> None:
    assert fx._mix("#000000", "#FFFFFF", 0.5) == "#808080"
    assert fx._mix("#4FE3F0", "#FFFFFF", 0) == "#4FE3F0"
    assert fx._mix("#4FE3F0", "#FFFFFF", 1) == "#FFFFFF"
    assert fx._mix("primary", "#FFFFFF", 0.5) == "primary"  # not hex: unchanged
