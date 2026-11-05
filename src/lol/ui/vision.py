"""On-device meal photo recognition: the `Recognizer` backed by our `flet_lumen_vision` extension.

    recognizer = vision.recognizer_for(page)        # VisionRecognizer on Android, else Manual
    cands = await recognizer.recognize_async(path)  # from an async handler, or
    cands = recognizer.recognize(path)              # from a worker thread (blocks it)

The extension runs Google's AIY food_V1 TFLite classifier on the phone (no network, no cost).
Labels -> foods.py ids lives in core (`lol.core.food_labels`); this module only bridges the
async Flet service to the sync `Recognizer` protocol. Android only: on web/desktop, or when
the extension isn't in the build, `recognizer_for` returns `ManualRecognizer`, and a
VisionRecognizer whose service fails just returns [] (the screen then shows "pick foods").
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from lol.core import food_labels
from lol.core.recognize import Candidate, ManualRecognizer, Recognizer

log = logging.getLogger(__name__)

CLASSIFY_TIMEOUT = 20.0  # seconds on the device (first call also loads the model)

_page: Any = None
_svc: Any = None  # flet_lumen_vision.LumenVision, one per page
_ready: bool | None = None  # None = not checked yet


def _is_android(page: Any) -> bool:
    try:
        if page is None or getattr(page, "web", False):
            return False
        import flet as ft

        return page.platform in (ft.PagePlatform.ANDROID, ft.PagePlatform.ANDROID_TV)
    except Exception:
        log.debug("platform check failed", exc_info=True)
        return False


def _service(page: Any) -> Any:
    """The page's LumenVision service (created once), or None when unavailable."""
    global _page, _svc, _ready
    if page is not _page:
        _page, _svc, _ready = page, None, None
    if _svc is None and _is_android(page):
        try:
            from flet_lumen_vision import LumenVision

            _svc = LumenVision()  # services auto-register with the current page
        except Exception:
            log.debug("flet_lumen_vision unavailable", exc_info=True)
            _svc = None
    return _svc


def available(page: Any) -> bool:
    """True when this page can try on-device recognition (Android + extension in the build)."""
    return _service(page) is not None and _ready is not False


async def warm_up(page: Any) -> bool:
    """Load the model now so the first scan is fast. False if it can't run here."""
    global _ready
    svc = _service(page)
    if svc is None:
        return False
    _ready = await svc.ready()
    if not _ready:
        log.info("on-device vision not ready: %s", getattr(svc, "last_error", None))
    return _ready


class VisionRecognizer:
    """`Recognizer` that classifies the photo on the device and maps labels to foods."""

    name = "On-device"

    def __init__(self, page: Any, timeout: float = CLASSIFY_TIMEOUT):
        self.page = page
        self.timeout = timeout
        self.last_predictions: list[tuple[str, float]] = []  # raw model output (debug/tuning)

    async def recognize_async(self, image_path: str) -> list[Candidate]:
        svc = _service(self.page)
        if svc is None or not image_path:
            return []
        preds = await svc.classify(image_path, top_k=food_labels.TOP_K, timeout=self.timeout)
        self.last_predictions = preds
        if not preds and getattr(svc, "last_error", None):
            log.info("on-device vision failed: %s", svc.last_error)
        return food_labels.candidates_from_predictions(preds)

    def recognize(self, image_path: str) -> list[Candidate]:
        """Sync form of the protocol. Call it from a worker thread (page.run_thread /
        asyncio.to_thread); on the page's event-loop thread it can't block and returns []."""
        loop = getattr(self.page, "loop", None)
        if loop is None:
            return []
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is loop:
            log.warning("VisionRecognizer.recognize called on the event loop; use recognize_async")
            return []
        fut = asyncio.run_coroutine_threadsafe(self.recognize_async(image_path), loop)
        try:
            return fut.result(timeout=self.timeout + 15.0)
        except TimeoutError:
            fut.cancel()
            return []


def recognizer_for(page: Any) -> Recognizer:
    """VisionRecognizer when on-device recognition can run on this page, else ManualRecognizer.

    Also starts loading the model in the background, so open the meal screen with this."""
    if not available(page):
        return ManualRecognizer()
    if _ready is None:
        try:
            page.run_task(warm_up, page)
        except Exception:
            log.debug("vision warm-up not started", exc_info=True)
    return VisionRecognizer(page)
