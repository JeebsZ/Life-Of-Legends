"""On-device notes scan: the core `TextRecognizer` backed by our `flet_lumen_ocr` extension.

    rec = ocr.recognizer_for(page)            # OcrRecognizer on Android, else Manual
    text = await rec.recognize_async(path)    # from an async handler ("" = nothing read)

The extension runs Google ML Kit text recognition (bundled Latin model, on the phone, no
network). Android only: on web/desktop, or when the extension isn't in the build,
`recognizer_for` returns `ManualTextRecognizer` and the Study screen asks the player to paste
or type the text. The text then goes through the same notes parser and draft review.
"""

from __future__ import annotations

import logging
from typing import Any

from lol.core.study import ManualTextRecognizer, TextRecognizer

log = logging.getLogger(__name__)

RECOGNIZE_TIMEOUT = 25.0  # seconds on the device

_page: Any = None
_svc: Any = None  # flet_lumen_ocr.LumenOcr, one per page


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
    """The page's LumenOcr service (created once), or None when unavailable."""
    global _page, _svc
    if page is not _page:
        _page, _svc = page, None
    if _svc is None and _is_android(page):
        try:
            from flet_lumen_ocr import LumenOcr

            _svc = LumenOcr()  # services auto-register with the current page
        except Exception:
            log.debug("flet_lumen_ocr unavailable", exc_info=True)
            _svc = None
    return _svc


class OcrRecognizer:
    """`TextRecognizer` that reads the photo on the device. Use `recognize_async` from the UI;
    the sync `recognize` exists for the protocol and returns "" (never blocks the loop)."""

    name = "On-device"

    def __init__(self, page: Any, timeout: float = RECOGNIZE_TIMEOUT) -> None:
        self.page = page
        self.timeout = timeout

    async def recognize_async(self, image_path: str) -> str:
        svc = _service(self.page)
        if svc is None or not image_path:
            return ""
        text = await svc.recognize(image_path, timeout=self.timeout)
        if not text and getattr(svc, "last_error", None):
            log.info("on-device OCR failed: %s", svc.last_error)
        return text

    def recognize(self, image_path: str) -> str:
        return ""


def recognizer_for(page: Any) -> TextRecognizer:
    """THE single hook for the notes-scan engine: OcrRecognizer on Android when the extension
    is in the build, else ManualTextRecognizer (paste or type the text)."""
    try:
        if _service(page) is not None:
            return OcrRecognizer(page)
    except Exception:
        log.debug("OCR engine unavailable", exc_info=True)
    return ManualTextRecognizer()
