"""Center nav slot ("Middle button"): which More feature the player pinned to the big arcane
button between Quests and Rewards. Pure rules; the UI owns the registry (labels, icons) and
passes plain keys in.

- `pinnable` filters the More registry: coming-soon tiles and features whose module is
  switched off in Settings are not offered.
- The pin is stored as `Profile.center_pin` (None = empty slot). A pin whose feature was
  switched off is kept (turning it back on restores it) but reads as empty via `active_pin`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from lol.core.models import MODULES, Profile


def pinnable(keys: Iterable[str], *, module_on: Callable[[str], bool],
             exclude: Iterable[str] = ()) -> list[str]:
    """Registry keys that can be pinned, in registry order, without duplicates."""
    skip = set(exclude)
    out: list[str] = []
    for key in keys:
        if key in skip or key in out:
            continue
        if key in MODULES and not module_on(key):
            continue
        out.append(key)
    return out


def active_pin(profile: Profile, allowed: Iterable[str]) -> str | None:
    """The pinned feature if it can show right now, else None (the slot reads as empty)."""
    pin = profile.center_pin
    return pin if pin and pin in set(allowed) else None


def set_pin(profile: Profile, key: str | None, allowed: Iterable[str]) -> str | None:
    """Pin `key` (must be in `allowed`) or clear the slot with None. Returns the previous pin
    (for undo). Raises ValueError for a key that cannot be pinned."""
    if key is not None and key not in set(allowed):
        raise ValueError(f"cannot pin {key!r}")
    previous = profile.center_pin
    profile.center_pin = key
    return previous
