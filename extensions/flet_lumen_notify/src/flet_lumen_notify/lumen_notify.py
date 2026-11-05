"""LumenNotify: a Flet service for local (on-device) notifications.

The Dart side (flutter/flet_lumen_notify) wraps the `flutter_local_notifications`
plugin. Only Android is implemented; on other platforms every method returns None
without raising (the Dart side is a no-op, or the service has no client at all).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import flet as ft

__all__ = ["LumenNotify"]

_TIMEOUT = 15.0


@ft.control("LumenNotify")
class LumenNotify(ft.Service):
    """Schedules and shows local notifications through one Android channel.

    Ids are Android notification ids: signed 32-bit ints, unique per reminder.
    Scheduling is *inexact* (`AndroidScheduleMode.inexactAllowWhileIdle`), so a
    reminder can arrive some minutes late; this avoids the SCHEDULE_EXACT_ALARM
    permission.
    """

    async def init(
        self,
        channel_id: str = "lumen",
        channel_name: str = "Lumen",
        channel_description: str = "Reminders from Lumen",
        icon: str | None = None,
    ) -> bool | None:
        """Initialize the plugin and create the notification channel.

        `icon` is an Android drawable/mipmap resource (default `@mipmap/ic_launcher`).
        Safe to call more than once (only the first call takes effect).
        """
        return await self._invoke_method(
            "init",
            {
                "channel_id": channel_id,
                "channel_name": channel_name,
                "channel_description": channel_description,
                "icon": icon,
            },
            timeout=_TIMEOUT,
        )

    async def request_permission(self) -> bool | None:
        """Ask for POST_NOTIFICATIONS (Android 13+). True when notifications are allowed."""
        return await self._invoke_method("request_permission", timeout=120.0)

    async def are_enabled(self) -> bool | None:
        """Whether the user currently allows notifications for this app."""
        return await self._invoke_method("are_enabled", timeout=_TIMEOUT)

    async def open_settings(self) -> bool | None:
        """Open the system notification settings page for this app."""
        return await self._invoke_method("open_settings", timeout=_TIMEOUT)

    async def show(self, id: int, title: str, body: str, payload: str | None = None,
                   sound: str | None = None) -> bool | None:
        """Show a notification right now. `sound`: "notify_01".."notify_08" (a raw resource
        of this extension, played through its own channel) or None for the system sound."""
        return await self._invoke_method(
            "show",
            {"id": int(id), "title": title, "body": body, "payload": payload, "sound": sound},
            timeout=_TIMEOUT,
        )

    async def schedule(
        self,
        id: int,
        when_iso_local: str | datetime,
        title: str,
        body: str,
        payload: str | None = None,
        sound: str | None = None,
    ) -> bool | None:
        """Schedule a one-shot notification (`sound`: as in `show`).

        `when_iso_local` is an ISO date-time in the device's local time
        (e.g. "2026-11-05T09:00:00"); an offset, if present, is honoured. A naive
        `datetime` is accepted too. Returns False if the time is already past.
        """
        when = (
            when_iso_local.isoformat(timespec="seconds")
            if isinstance(when_iso_local, datetime)
            else str(when_iso_local)
        )
        return await self._invoke_method(
            "schedule",
            {"id": int(id), "when": when, "title": title, "body": body, "payload": payload,
             "sound": sound},
            timeout=_TIMEOUT,
        )

    async def cancel(self, id: int) -> bool | None:
        """Cancel one scheduled or shown notification."""
        return await self._invoke_method("cancel", {"id": int(id)}, timeout=_TIMEOUT)

    async def cancel_all(self) -> bool | None:
        """Cancel every scheduled and shown notification of this app."""
        return await self._invoke_method("cancel_all", timeout=_TIMEOUT)

    async def pending(self) -> list[dict[str, Any]]:
        """Scheduled-but-not-yet-shown notifications: [{id, title, body, payload}]."""
        r = await self._invoke_method("pending", timeout=_TIMEOUT)
        return list(r or [])
