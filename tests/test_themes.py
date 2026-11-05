"""Every theme is complete, readable and wired to the catalog; Rose Arcana is free."""

import itertools
import math
import re

import pytest

from lol.core import catalog
from lol.core.game import Game
from lol.ui import theme as th

HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
COLOR_TOKENS = ("bg", "surface", "surface_hi", "primary", "on_primary", "accent", "success",
                "danger", "text", "text_dim")


def _lin(h: str) -> list[float]:
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]


def contrast(a: str, b: str) -> float:
    la, lb = (0.2126 * r + 0.7152 * g + 0.0722 * b_ for r, g, b_ in (_lin(a), _lin(b)))
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def delta_e(a: str, b: str) -> float:
    """CIE76 distance in Lab: ~2 is just noticeable, 20+ is clearly a different colour."""
    def lab(h: str) -> tuple[float, float, float]:
        r, g, b_ = _lin(h)
        x = (0.4124 * r + 0.3576 * g + 0.1805 * b_) / 0.95047
        y = 0.2126 * r + 0.7152 * g + 0.0722 * b_
        z = (0.0193 * r + 0.1192 * g + 0.9505 * b_) / 1.08883
        f = [t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116 for t in (x, y, z)]
        return 116 * f[1] - 16, 500 * (f[0] - f[1]), 200 * (f[1] - f[2])
    return math.dist(lab(a), lab(b))


@pytest.mark.parametrize("pal", th.THEMES.values(), ids=lambda p: p.id)
def test_theme_defines_every_token(pal):
    assert pal.name and pal.id in th.THEMES
    for token in COLOR_TOKENS:
        assert HEX.match(getattr(pal, token)), f"{pal.id}.{token}"
    assert set(pal.paths) == set(th.PATH_IDS), pal.id
    assert all(HEX.match(c) for c in pal.paths.values())


@pytest.mark.parametrize("pal", th.THEMES.values(), ids=lambda p: p.id)
def test_theme_is_readable(pal):
    for panel in (pal.surface, pal.surface_hi):
        assert contrast(pal.text, panel) >= 4.5
        assert contrast(pal.text_dim, panel) >= 4.5
    assert contrast(pal.on_primary, pal.primary) >= 4.5  # dark text on accent buttons
    for role in (pal.primary, pal.accent, pal.success, pal.danger):
        assert contrast(role, pal.surface) >= 4.5


@pytest.mark.parametrize("pal", th.THEMES.values(), ids=lambda p: p.id)
def test_path_colors_stay_distinguishable(pal):
    for (a, ca), (b, cb) in itertools.combinations(pal.paths.items(), 2):
        assert delta_e(ca, cb) >= 20, f"{pal.id}: {a} vs {b}"


def test_catalog_and_ui_themes_match():
    assert {t.id for t in catalog.THEMES} == set(th.THEMES)
    assert th.DEFAULT_THEME == catalog.DEFAULT_THEME


def test_rose_arcana_is_free_and_persists(tmp_path):
    assert "rose" in catalog.FREE_THEMES and catalog.THEME_PRICES["rose"] == 0
    g = Game()  # brand-new player, no coins: can still pick it
    assert g.profile.coins == 0 and g.set_theme("rose") is True
    path = g.save(tmp_path / "save.json")
    assert Game.load(path).profile.theme_id == "rose"  # survives a restart
