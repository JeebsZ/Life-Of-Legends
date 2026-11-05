"""Phone notifications: Luma's reminders as local, on-device notifications.

    notify.init(page, settings=lambda: game.profile)    # once, inside main
    ok = await notify.ensure_permission()               # e.g. when the user turns reminders on
    await notify.sync(game.planned_reminders(now, 7))   # after launch / any reminder change
    await notify.test_now()                             # Settings > "Send a test notification"

From a sync handler use `page.run_task(notify.sync, reminders)`.

Backed by our own Flet extension `flet_lumen_notify` (extensions/flet_lumen_notify, wrapping the
Flutter plugin flutter_local_notifications) and, for the Android 13+ permission prompt, the
official `flet_permission_handler`. Android only: on web, desktop and iOS, or when the
extension isn't in the build, every call is a quiet no-op that returns False / an empty result
and never raises.

Reminders are any objects with `id: str` (stable, unique), `when: datetime`, `title`, `body`
and `category`. A naive `when` is wall-clock time on the phone; an aware one is honoured as is.
Each string id maps to a deterministic 31-bit notification id, so re-syncing replaces instead
of duplicating. Android delivers scheduled notifications *inexactly* (they can be some minutes
late; no exact-alarm permission is used) and only the next MAX_SCHEDULED are kept scheduled -
the app re-syncs on every launch to top the queue up.

Sound: the profile's `notify_sound` (Settings picker, notify_01..08) plays with every
notification, through one Android channel per sound (a channel's sound is fixed once created;
see extensions/flet_lumen_notify/README.md). Changing it re-schedules pending reminders on the
next sync.
"""

from __future__ import annotations

import contextlib
import hashlib
import logging
from collections.abc import Iterable
from datetime import datetime, timedelta
from typing import Any

log = logging.getLogger(__name__)

MAX_SCHEDULED = 50  # Android caps pending alarms per app (~500); stay far below.
TEST_ID = 1  # test_now(); test_in() uses TEST_ID + 1. Stable ids are >= ID_FLOOR
ID_FLOOR = 1000
_ID_SPAN = 0x7FFFFFFF - ID_FLOOR
MIN_LEAD = timedelta(seconds=30)  # skip reminders that would fire (almost) immediately

_page: Any = None
_svc: Any = None  # flet_lumen_notify.LumenNotify
_perm: Any = None  # flet_permission_handler.PermissionHandler
_ready = False
_scheduled: dict[int, tuple[str, ...]] = {}  # id -> (when iso, title, body, sound) last sent
_settings: Any = None  # () -> profile (notify_sound)
SOUNDS = tuple(f"notify_{i:02d}" for i in range(1, 9))  # = models.NOTIFY_SOUNDS


def sound() -> str | None:
    """The picked notification sound (profile.notify_sound), None = system default."""
    try:
        s = getattr(_settings(), "notify_sound", None) if _settings else None
    except Exception:
        log.debug("notify sound setting unreadable", exc_info=True)
        return None
    return s if s in SOUNDS else None


def stable_id(key: str) -> int:
    """Deterministic Android notification id for a reminder id (same on every run/device)."""
    digest = hashlib.sha1(str(key).encode("utf-8")).digest()
    return ID_FLOOR + int.from_bytes(digest[:4], "big") % _ID_SPAN


def _is_android(page: Any) -> bool:
    try:
        if page is None or getattr(page, "web", False):
            return False
        import flet as ft

        return page.platform in (ft.PagePlatform.ANDROID, ft.PagePlatform.ANDROID_TV)
    except Exception:
        log.debug("platform check failed", exc_info=True)
        return False


def init(page: Any, settings: Any = None) -> None:
    """Create the notification services for this page (call once in main). `settings()`
    returns the profile (notify_sound). Never raises."""
    global _page, _svc, _perm, _ready, _settings
    _page, _svc, _perm, _ready, _settings = page, None, None, False, settings
    _scheduled.clear()
    if not _is_android(page):
        return
    try:
        from flet_lumen_notify import LumenNotify

        _svc = LumenNotify()  # services auto-register with the current page
    except Exception:
        log.debug("flet_lumen_notify unavailable", exc_info=True)
        _svc = None
        return
    try:
        from flet_permission_handler import PermissionHandler

        _perm = PermissionHandler()
    except Exception:
        log.debug("flet_permission_handler unavailable", exc_info=True)
        _perm = None


def available() -> bool:
    """True when notifications can work here (Android build with the extension)."""
    return _svc is not None


async def _ensure_ready() -> bool:
    global _ready
    if _svc is None:
        return False
    if not _ready:
        try:
            await _svc.init(channel_id="lumen", channel_name="Luma")
            _ready = True
        except Exception:
            log.debug("notify init failed", exc_info=True)
            return False
    return True


async def permission_granted() -> bool:
    """Whether notifications are currently allowed (no prompt)."""
    if not await _ensure_ready():
        return False
    try:
        return bool(await _svc.are_enabled())
    except Exception:
        log.debug("are_enabled failed", exc_info=True)
        return False


async def ensure_permission() -> bool:
    """Make sure we may post notifications, prompting once if needed (Android 13+).
    Returns True when allowed. If the user has permanently refused, returns False without a
    prompt; offer `open_settings()` then."""
    if not await _ensure_ready():
        return False
    if _perm is not None:
        try:
            from flet_permission_handler import Permission, PermissionStatus

            status = await _perm.get_status(Permission.NOTIFICATION)
            if status == PermissionStatus.GRANTED:
                return True
            if status in (PermissionStatus.PERMANENTLY_DENIED, PermissionStatus.RESTRICTED):
                return False
            status = await _perm.request(Permission.NOTIFICATION)
            return status == PermissionStatus.GRANTED
        except Exception:
            log.debug("permission_handler failed; falling back to plugin", exc_info=True)
    try:
        return bool(await _svc.request_permission())
    except Exception:
        log.debug("request_permission failed", exc_info=True)
        return False


async def open_settings() -> bool:
    """Open this app's system notification settings."""
    if not await _ensure_ready():
        return False
    try:
        return bool(await _svc.open_settings())
    except Exception:
        log.debug("open_settings failed", exc_info=True)
        return False


def _when_iso(when: datetime) -> str:
    # naive -> phone-local wall clock (parsed as local by Dart); aware -> keeps its offset
    return when.isoformat(timespec="seconds")


def _is_future(when: datetime, now: datetime | None) -> bool:
    try:
        if when.tzinfo is not None:
            ref = (
                now if (now is not None and now.tzinfo is not None) else datetime.now().astimezone()
            )
        else:
            ref = now.replace(tzinfo=None) if now is not None else datetime.now()
        return when > ref + MIN_LEAD
    except Exception:
        log.debug("bad reminder time %r", when, exc_info=True)
        return False


async def sync(reminders: Iterable[Any], now: datetime | None = None) -> dict[str, int]:
    """Make the phone's scheduled notifications match `reminders`.

    Keeps the next MAX_SCHEDULED future reminders scheduled (re-sending only new or changed
    ones), cancels every other pending notification of this app. Returns counts
    {"scheduled", "unchanged", "cancelled", "skipped"}; all zero when unavailable."""
    result = {"scheduled": 0, "unchanged": 0, "cancelled": 0, "skipped": 0}
    if not await _ensure_ready():
        return result
    wanted: dict[int, tuple[str, str, str, str]] = {}
    try:
        items = []
        for r in reminders or ():
            when = getattr(r, "when", None)
            if not isinstance(when, datetime) or not _is_future(when, now):
                result["skipped"] += 1
                continue
            items.append(r)
        items.sort(key=lambda r: r.when.timestamp())
        for r in items:
            if len(wanted) >= MAX_SCHEDULED:
                result["skipped"] += 1
                continue
            nid = stable_id(r.id)
            if nid in wanted:  # hash collision or duplicate id: keep the earlier one
                log.debug("notify id collision for %r", r.id)
                result["skipped"] += 1
                continue
            wanted[nid] = (
                _when_iso(r.when),
                str(getattr(r, "title", "") or "Luma"),
                str(getattr(r, "body", "") or ""),
                str(getattr(r, "category", "") or ""),
            )
    except Exception:
        log.debug("notify sync: bad reminders", exc_info=True)
        return result

    try:
        pending = {int(p.get("id")) for p in await _svc.pending() if p.get("id") is not None}
    except Exception:
        log.debug("notify pending() failed", exc_info=True)
        pending = set(_scheduled)

    for nid in {n for n in pending if n >= ID_FLOOR} - set(wanted):  # leave test ids alone
        with contextlib.suppress(Exception):
            await _svc.cancel(nid)
            result["cancelled"] += 1
        _scheduled.pop(nid, None)
    for nid in set(_scheduled) - set(wanted):
        _scheduled.pop(nid, None)

    snd = sound()
    for nid, (when, title, body, category) in wanted.items():
        sig = (when, title, body, snd or "")
        if nid in pending and _scheduled.get(nid) == sig:
            result["unchanged"] += 1
            continue
        try:
            ok = await _svc.schedule(nid, when, title, body, payload=category or None,
                                     sound=snd)
        except Exception:
            log.debug("notify schedule(%s) failed", nid, exc_info=True)
            ok = False
        if ok:
            _scheduled[nid] = sig
            result["scheduled"] += 1
        else:
            result["skipped"] += 1
    return result


async def cancel_all() -> bool:
    """Cancel every notification of this app (e.g. master toggle off)."""
    _scheduled.clear()
    if not await _ensure_ready():
        return False
    try:
        return bool(await _svc.cancel_all())
    except Exception:
        log.debug("cancel_all failed", exc_info=True)
        return False


async def test_now(title: str = "Luma", body: str = "Notifications are working!") -> bool:
    """Show a notification immediately (asks for permission first). True if it was posted."""
    if not await ensure_permission():
        return False
    try:
        return bool(await _svc.show(TEST_ID, title, body, sound=sound()))
    except Exception:
        log.debug("test notification failed", exc_info=True)
        return False


async def test_in(seconds: int = 60) -> bool:
    """Schedule a test notification `seconds` from now (checks the scheduled path)."""
    if not await ensure_permission():
        return False
    try:
        when = (datetime.now() + timedelta(seconds=max(5, int(seconds)))).isoformat(
            timespec="seconds"
        )
        return bool(await _svc.schedule(TEST_ID + 1, when, "Luma", "Scheduled test reminder",
                                        sound=sound()))
    except Exception:
        log.debug("scheduled test failed", exc_info=True)
        return False
