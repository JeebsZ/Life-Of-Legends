"""LumenVision: a Flet service that classifies a food photo on the device.

The Dart side (flutter/flet_lumen_vision) runs Google's AIY food_V1 TFLite classifier
(MobileNet V1, ~2,000 dishes) through `tflite_flutter`. Android (and iOS) only. On web and
desktop, or when the extension is not in the build, every method returns an empty / False
result instead of raising.
"""

from __future__ import annotations

import logging
from typing import Any

import flet as ft

__all__ = ["LumenVision"]

log = logging.getLogger(__name__)

# The first ready()/classify() loads a 21 MB model from the APK (typically < 1 s, slower on
# old phones); one inference is tens of milliseconds.
_LOAD_TIMEOUT = 40.0
_CLASSIFY_TIMEOUT = 20.0


@ft.control("LumenVision")
class LumenVision(ft.Service):
    """On-device food photo classifier.

    `last_error` (Python-only) keeps the last failure reason ("unsupported", "timeout",
    "load: ...", ...) for diagnostics; `last_ms` the last classify duration on the device.
    """

    def init(self):
        super().init()
        self.last_error: str | None = None
        self.last_ms: int | None = None

    async def ready(self, timeout: float = _LOAD_TIMEOUT) -> bool:
        """Load the model if needed. True when classify() can run on this device."""
        info = await self.info(timeout=timeout)
        return bool(info.get("ok"))

    async def info(self, timeout: float = _LOAD_TIMEOUT) -> dict[str, Any]:
        """ready() with details: {ok, error?, labels, input, input_type, output_type, load_ms}."""
        r = await self._call("ready", None, timeout)
        return r if isinstance(r, dict) else {"ok": False, "error": self.last_error}

    async def classify(
        self, path: str, top_k: int = 5, timeout: float = _CLASSIFY_TIMEOUT
    ) -> list[tuple[str, float]]:
        """Top-k (label, probability 0..1) for the photo at `path`, best first.

        Labels are the model's own names (e.g. "Philippine adobo", "__background__").
        Returns [] when the service is unavailable, the model failed to load, the image
        could not be read, or the call timed out (see `last_error`).
        """
        r = await self._call(
            "classify",
            {"path": str(path), "top_k": int(top_k), "timeout_s": int(timeout)},
            timeout + 5.0,  # the device enforces `timeout`; this is the safety net
        )
        if not isinstance(r, dict) or not r.get("ok"):
            return []
        self.last_ms = r.get("ms")
        out: list[tuple[str, float]] = []
        for item in r.get("top") or []:
            try:
                out.append((str(item[0]), float(item[1])))
            except (TypeError, ValueError, IndexError):
                continue
        return out

    async def _call(self, method: str, args: dict[str, Any] | None, timeout: float) -> Any:
        try:
            r = await self._invoke_method(method, args, timeout=timeout)
        except TimeoutError:
            self.last_error = "timeout"
            return None
        except Exception as ex:  # no client side (desktop/web build), page gone, ...
            self.last_error = f"{type(ex).__name__}: {ex}"
            log.debug("LumenVision.%s failed", method, exc_info=True)
            return None
        if isinstance(r, dict) and not r.get("ok"):
            self.last_error = str(r.get("error") or "failed")
        else:
            self.last_error = None
        return r
