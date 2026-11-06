"""Where GPS fixes come from: the phone (flet_geolocator) or, for testing on PC/web, a replayed
loop around Rizal Park (core/run_sim.py) when the env var LOL_FAKE_GPS=1 is set.
LOL_FAKE_GPS_SPEED=10 replays ten times faster (simulated clock; QA only).

Both sources share one small interface used by screens/run.py:
    status() / request() -> "granted" | "denied" | "denied_forever" | "service_off" |
                            "unavailable"
    start(on_fix) / stop()        (on_fix gets a core.run.Fix)
    now()                         (the clock the fixes use: time.time(), or the sim clock)
Tracking continues in the background and while the screen is off via Android foreground
notification service (`ForegroundNotificationConfiguration`) and iOS background location updates.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import time
from collections.abc import Callable
from typing import Any

from lol.core import run_sim
from lol.core.run import Fix

log = logging.getLogger(__name__)
GRANTED = "granted"


def fake_enabled() -> bool:
    return os.getenv("LOL_FAKE_GPS", "").strip() in ("1", "true", "yes")


class FakeGps:
    """Replays the Rizal Park loop at run (or walk) pace. Debug only."""

    fake = True

    def __init__(self, page: Any, speed: float | None = None) -> None:
        self.page = page
        default_speed = float(os.getenv("LOL_FAKE_GPS_SPEED", "1") or 1)
        self.speed = max(0.1, float(speed) if speed is not None else default_speed)
        self.mode = "run"
        self._gen = 0
        self._wall0 = time.monotonic()
        self._t0 = time.time()

    def now(self) -> float:
        return self._t0 + (time.monotonic() - self._wall0) * self.speed

    async def status(self) -> str:
        return GRANTED

    async def request(self) -> str:
        return GRANTED

    async def open_settings(self) -> bool:
        return False

    def start(self, on_fix: Callable[[Fix], None], mode: str = "run") -> None:
        self.stop()
        self.mode = mode
        self._gen += 1
        self.page.run_task(self._loop, self._gen, on_fix)

    def stop(self) -> None:
        self._gen += 1

    async def _loop(self, gen: int, on_fix: Callable[[Fix], None]) -> None:
        start = self.now()
        for fix in run_sim.simulate(self.mode, start_t=start):
            if gen != self._gen:
                return
            wait = (fix.t - self.now()) / self.speed
            if wait > 0:
                await asyncio.sleep(wait)
            if gen != self._gen:
                return
            with contextlib.suppress(Exception):
                on_fix(fix)


class PhoneGps:
    """flet_geolocator wrapper. The position stream runs only between start() and stop()."""

    fake = False

    def __init__(self, page: Any) -> None:
        self.page = page
        self._gl: Any = None
        self._on_fix: Callable[[Fix], None] | None = None
        try:
            import flet_geolocator as fg

            self._fg = fg
            self._gl = fg.Geolocator(configuration=self._config(), on_error=self._error)
        except Exception:
            log.debug("geolocator unavailable", exc_info=True)

    def now(self) -> float:
        return time.time()

    def _config(self) -> Any:
        fg = self._fg
        plat = str(getattr(getattr(self.page, "platform", None), "value", "") or "").lower()
        if plat == "android":
            import flet as ft

            return fg.GeolocatorAndroidConfiguration(
                accuracy=fg.GeolocatorPositionAccuracy.BEST,
                distance_filter=0,
                interval_duration=ft.Duration(seconds=1),
                foreground_notification_config=fg.ForegroundNotificationConfiguration(
                    notification_title="LUMA: Run & Walk Active",
                    notification_text="Tracking your route and Adventure Run in the background.",
                    notification_channel_name="LUMA Run Tracking",
                    notification_enable_wake_lock=True,
                    notification_set_ongoing=True,
                ),
            )
        if plat == "ios":
            return fg.GeolocatorIosConfiguration(
                accuracy=fg.GeolocatorPositionAccuracy.BEST,
                distance_filter=0,
                activity_type=fg.GeolocatorIosActivityType.FITNESS,
                pause_location_updates_automatically=False,
                allow_background_location_updates=True,
                show_background_location_indicator=True,
            )
        return fg.GeolocatorConfiguration(accuracy=fg.GeolocatorPositionAccuracy.BEST)

    @staticmethod
    def _map(status: Any) -> str:
        v = str(getattr(status, "value", status) or "")
        if v in ("whileInUse", "always"):
            return GRANTED
        if v == "deniedForever":
            return "denied_forever"
        if v == "denied":
            return "denied"
        return "unavailable"

    async def status(self) -> str:
        if self._gl is None:
            return "unavailable"
        try:
            st = self._map(await asyncio.wait_for(self._gl.get_permission_status(), 5))
            if st == GRANTED and not self.page.web:
                on = await asyncio.wait_for(self._gl.is_location_service_enabled(), 5)
                if not on:
                    return "service_off"
            return st
        except Exception:
            log.debug("permission status failed", exc_info=True)
            return "unavailable"

    async def request(self) -> str:
        if self._gl is None:
            return "unavailable"
        try:
            self._map(await asyncio.wait_for(self._gl.request_permission(), 60))
        except Exception:
            log.debug("permission request failed", exc_info=True)
            return "unavailable"
        return await self.status()

    async def open_settings(self, location: bool = False) -> bool:
        if self._gl is None or self.page.web:
            return False
        try:
            if location:
                return bool(await self._gl.open_location_settings())
            return bool(await self._gl.open_app_settings())
        except Exception:
            log.debug("open settings failed", exc_info=True)
            return False

    def start(self, on_fix: Callable[[Fix], None], mode: str = "run") -> None:
        if self._gl is None:
            return
        self._on_fix = on_fix
        self._gl.on_position_change = self._position
        with contextlib.suppress(Exception):
            self._gl.update()

    def stop(self) -> None:
        self._on_fix = None
        if self._gl is not None:
            self._gl.on_position_change = None
            with contextlib.suppress(Exception):
                self._gl.update()

    def _position(self, e: Any) -> None:
        p = getattr(e, "position", None)
        if p is None or p.latitude is None or p.longitude is None or self._on_fix is None:
            return
        ts = p.timestamp.timestamp() if getattr(p, "timestamp", None) else time.time()
        acc = float(p.accuracy) if p.accuracy is not None else 999.0
        alt = float(p.altitude) if p.altitude not in (None, 0) else None
        self._on_fix(Fix(float(p.latitude), float(p.longitude), acc, ts, alt))

    def _error(self, e: Any) -> None:
        log.debug("geolocator error: %s", getattr(e, "data", e))


def make(page: Any) -> FakeGps | PhoneGps:
    return FakeGps(page) if fake_enabled() else PhoneGps(page)
