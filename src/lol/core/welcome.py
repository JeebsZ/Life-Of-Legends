"""Luma's 'welcome back' on app open / resume: which line, and whether it is due.

Pure rules (no Flet, no clock reads): the UI passes the current time and the last activity
day. The line texts live in ui/voice.py LINES["hello_again"]; SLOTS maps each variant index
there (and voice clip hello_again_<i+1>) to the moment it fits.
"""

from __future__ import annotations

from datetime import date, datetime

# variant index -> slot (keep aligned with voice.LINES["hello_again"])
SLOTS: tuple[str, ...] = ("morning", "day", "day", "evening", "night", "away")
AWAY_DAYS = 2              # no activity for this many days -> the gentle 'been away' line
COOLDOWN_S = 30 * 60       # at most one welcome per 30 min (open + quick resumes stay quiet)


def slot_for(now: datetime, last_active: date | None) -> str:
    """'away' after AWAY_DAYS+ days without activity, else by the hour: morning 5-11,
    day 12-16, evening 17-21, night 22-4. A brand-new player (no activity) gets the hour."""
    if last_active is not None and (now.date() - last_active).days >= AWAY_DAYS:
        return "away"
    h = now.hour
    if 5 <= h < 12:
        return "morning"
    if 12 <= h < 17:
        return "day"
    if 17 <= h < 22:
        return "evening"
    return "night"


def pick(now: datetime, last_active: date | None, previous: int | None = None) -> int:
    """Variant index for this welcome: one of the slot's variants, not `previous` when the
    slot has another one."""
    slot = slot_for(now, last_active)
    options = [i for i, s in enumerate(SLOTS) if s == slot]
    fresh = [i for i in options if i != previous]
    return (fresh or options)[0]


def due(now_s: float, last_s: float | None, cooldown_s: float = COOLDOWN_S) -> bool:
    """True when no welcome played yet, or the last one is at least `cooldown_s` old."""
    return last_s is None or now_s - last_s >= cooldown_s
