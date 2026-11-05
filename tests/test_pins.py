import json

import pytest

from lol.core import pins, storage
from lol.core.game import Game
from lol.core.models import Profile

REGISTRY = ("profile", "bills", "focus", "workout", "run", "water", "achievements", "focus")


def test_pinnable_keeps_order_and_drops_duplicates_and_excluded():
    keys = pins.pinnable(REGISTRY, module_on=lambda m: True, exclude={"achievements"})
    assert keys == ["profile", "bills", "focus", "workout", "run", "water"]


def test_pinnable_hides_features_switched_off_in_settings():
    off = {"workout", "water"}
    keys = pins.pinnable(REGISTRY, module_on=lambda m: m not in off)
    assert "workout" not in keys and "water" not in keys
    assert "bills" in keys and "focus" in keys and "run" in keys  # non-modules always shown


def test_set_pin_and_unpin_returns_previous_for_undo():
    p = Profile()
    assert p.center_pin is None
    assert pins.set_pin(p, "focus", ["focus", "bills"]) is None
    assert p.center_pin == "focus"
    assert pins.set_pin(p, None, ["focus"]) == "focus"
    assert p.center_pin is None


def test_set_pin_rejects_unknown_feature():
    p = Profile()
    with pytest.raises(ValueError):
        pins.set_pin(p, "nope", ["focus"])
    assert p.center_pin is None


def test_active_pin_reads_empty_when_feature_is_switched_off_but_keeps_it():
    p = Profile(center_pin="water")
    assert pins.active_pin(p, ["water", "bills"]) == "water"
    assert pins.active_pin(p, ["bills"]) is None
    assert p.center_pin == "water"  # turning the module back on restores the pin


def test_pin_survives_save_and_load(tmp_path):
    path = tmp_path / "save.json"
    g = Game()
    pins.set_pin(g.profile, "bills", ["bills"])
    g.save(path)
    assert Game.load(path).profile.center_pin == "bills"
    pins.set_pin(g.profile, None, ["bills"])
    g.save(path)
    assert Game.load(path).profile.center_pin is None


@pytest.mark.parametrize("raw", [None, "", 7, ["focus"]])
def test_old_or_junk_save_loads_with_empty_center_slot(tmp_path, raw):
    path = tmp_path / "save.json"
    data = storage.to_dict(Game().data)
    if raw is None:
        data["profile"].pop("center_pin", None)  # a save from before the center slot
    else:
        data["profile"]["center_pin"] = raw
    path.write_text(json.dumps(data), encoding="utf-8")
    assert Game.load(path).profile.center_pin is None
