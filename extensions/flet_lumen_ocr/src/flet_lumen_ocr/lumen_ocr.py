"""LumenOcr: a Flet service that reads Latin-script text from a photo on the device.

The Dart side (flutter/flet_lumen_ocr) runs Google ML Kit text recognition v2 (bundled Latin
model, on-device, no network) through `google_mlkit_text_recognition`. Android (and iOS) only.
On web and desktop, or when the extension is not in the build, every method returns an empty /
False result instead of raising.
"""

from __future__ import annotations

import logging
from typing import Any

import flet as ft

__all__ = ["LumenOcr"]

log = logging.getLogger(__name__)

_READY_TIMEOUT = 15.0
_RECOGNIZE_TIMEOUT = 25.0


@ft.control("LumenOcr")
class LumenOcr(ft.Service):
    """On-device text recognition.

    `last_error` (Python-only) keeps the last failure reason ("unsupported", "timeout", ...);
    `last_ms` the last recognize duration on the device; `last_lines` the last result as
    blocks of (text, left, top) lines (layout hints for the notes parser).
    """

    def init(self):
        super().init()
        self.last_error: str | None = None
        self.last_ms: int | None = None
        self.last_lines: list[list[tuple[str, int, int]]] = []

    async def ready(self, timeout: float = _READY_TIMEOUT) -> bool:
        """True when recognize() can run on this device (creates the recognizer)."""
        r = await self._call("ready", None, timeout)
        return bool(isinstance(r, dict) and r.get("ok"))

    async def recognize(self, path: str, timeout: float = _RECOGNIZE_TIMEOUT) -> str:
        """All text in the photo at `path`: lines joined by newlines, blocks (paragraphs)
        separated by a blank line. "" when unavailable, nothing was read, or on any failure
        (see `last_error`). Never raises."""
        r = await self._call("recognize", {"path": str(path), "timeout_s": int(timeout)},
                             timeout + 5.0)
        if not isinstance(r, dict) or not r.get("ok"):
            self.last_lines = []
            return ""
        self.last_ms = r.get("ms")
        blocks: list[list[tuple[str, int, int]]] = []
        for block in r.get("blocks") or []:
            lines: list[tuple[str, int, int]] = []
            for line in block or []:
                try:
                    lines.append((str(line[0]), int(line[1]), int(line[2])))
                except (TypeError, ValueError, IndexError):
                    continue
            if lines:
                blocks.append(lines)
        self.last_lines = blocks
        if blocks:
            return "\n\n".join("\n".join(t for t, _, _ in b) for b in blocks)
        return str(r.get("text") or "")

    async def _call(self, method: str, args: dict[str, Any] | None, timeout: float) -> Any:
        try:
            r = await self._invoke_method(method, args, timeout=timeout)
        except TimeoutError:
            self.last_error = "timeout"
            return None
        except Exception as ex:  # no client side (desktop/web build), page gone, ...
            self.last_error = f"{type(ex).__name__}: {ex}"
            log.debug("LumenOcr.%s failed", method, exc_info=True)
            return None
        if isinstance(r, dict) and not r.get("ok"):
            self.last_error = str(r.get("error") or "failed")
        else:
            self.last_error = None
        return r
