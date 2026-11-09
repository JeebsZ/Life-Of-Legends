"""Store update checker for LUMA (Google Play Store & optional JSON version manifest)."""

from __future__ import annotations

import asyncio
import contextlib
import json
import re
import urllib.request
from dataclasses import dataclass

from lol.core import cloud_config

# Matches semantic versions such as "0.1.4" or "1.2.0" in Play Store AF_initDataCallback blobs
# or JSON version manifests.
_PLAY_VERSION_PATTERNS = (
    re.compile(r'\[\[\["(\d+\.\d+(?:\.\d+)*)"\]\]'),
    re.compile(r'"softwareVersion"\s*:\s*"(\d+\.\d+(?:\.\d+)*)"'),
    re.compile(r'Current Version.*?>(\d+\.\d+(?:\.\d+)*)<', re.DOTALL),
)


@dataclass(frozen=True)
class UpdateInfo:
    """Result of checking for a newer store version."""

    available: bool
    current_version: str
    latest_version: str | None = None
    store_url: str = cloud_config.PLAY_STORE_URL


def parse_version(version_str: str) -> tuple[int, ...]:
    """Parse a dotted version string like '0.1.3' or 'v1.2.0-beta' into an int tuple."""
    if not version_str:
        return ()
    cleaned = version_str.strip().lstrip("vV").split("-")[0].split("+")[0]
    parts: list[int] = []
    for seg in cleaned.split("."):
        digits = "".join(ch for ch in seg if ch.isdigit())
        if not digits:
            return ()
        parts.append(int(digits))
    return tuple(parts)


def is_newer_version(current: str, latest: str) -> bool:
    """Return True if `latest` represents a strictly higher version than `current`."""
    cur_t = parse_version(current)
    lat_t = parse_version(latest)
    if not cur_t or not lat_t:
        return False
    max_len = max(len(cur_t), len(lat_t))
    cur_pad = cur_t + (0,) * (max_len - len(cur_t))
    lat_pad = lat_t + (0,) * (max_len - len(lat_t))
    return lat_pad > cur_pad


def extract_play_store_version(raw_text: str) -> str | None:
    """Extract the published version string from a Play Store HTML response or JSON manifest."""
    if not raw_text:
        return None
    stripped = raw_text.strip()
    if stripped.startswith("{"):
        with contextlib.suppress(Exception):
            data = json.loads(stripped)
            for key in ("latest_version", "version", "softwareVersion"):
                val = data.get(key)
                if isinstance(val, str) and parse_version(val):
                    return val.strip()

    for pattern in _PLAY_VERSION_PATTERNS:
        m = pattern.search(raw_text)
        if m:
            candidate = m.group(1)
            if parse_version(candidate):
                return candidate
    return None


def check_for_store_update(
    current_version: str | None = None,
    *,
    check_url: str | None = None,
    store_url: str | None = None,
    timeout: float = 4.0,
) -> UpdateInfo:
    """Synchronously check whether a newer version is live on the store (safe offline)."""
    cur = current_version or cloud_config.APP_VERSION
    s_url = store_url or cloud_config.PLAY_STORE_URL
    urls_to_try: list[str] = []
    manifest_url = check_url if check_url is not None else cloud_config.VERSION_CHECK_URL
    if manifest_url:
        urls_to_try.append(manifest_url)
    urls_to_try.append(f"{s_url}&hl=en&gl=US" if "?" in s_url else f"{s_url}?hl=en&gl=US")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }
    for url in urls_to_try:
        with contextlib.suppress(Exception):
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read(250_000).decode("utf-8", errors="ignore")
            latest = extract_play_store_version(body)
            if latest:
                if is_newer_version(cur, latest):
                    return UpdateInfo(
                        available=True,
                        current_version=cur,
                        latest_version=latest,
                        store_url=s_url,
                    )
                return UpdateInfo(
                    available=False,
                    current_version=cur,
                    latest_version=latest,
                    store_url=s_url,
                )

    return UpdateInfo(available=False, current_version=cur, latest_version=None, store_url=s_url)


async def check_for_store_update_async(
    current_version: str | None = None,
    *,
    check_url: str | None = None,
    store_url: str | None = None,
    timeout: float = 4.0,
) -> UpdateInfo:
    """Run `check_for_store_update` in a worker thread so the UI never blocks."""
    return await asyncio.to_thread(
        check_for_store_update,
        current_version,
        check_url=check_url,
        store_url=store_url,
        timeout=timeout,
    )
