"""Google Drive AppData REST API client for Life of Legends.

Stores save.json in the user's private Google Drive hidden application folder (appDataFolder).
Uses Python's standard library urllib with asyncio.to_thread for non-blocking HTTP calls.
"""

from __future__ import annotations

import asyncio
import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from lol.core.cloud_save import CloudFile, parse_iso_time

log = logging.getLogger(__name__)

DRIVE_FILES_URL = "https://www.googleapis.com/drive/v3/files"
DRIVE_UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files"
SAVE_FILE_NAME = "save.json"


def _headers(token: str, content_type: str | None = None) -> dict[str, str]:
    h = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    if content_type:
        h["Content-Type"] = content_type
    return h


def _find_save_sync(token: str) -> CloudFile | None:
    """Query Google Drive appDataFolder for save.json."""
    params = urllib.parse.urlencode({
        "spaces": "appDataFolder",
        "q": f"name='{SAVE_FILE_NAME}' and trashed=false",
        "fields": "files(id, name, modifiedTime, size)",
        "pageSize": "1",
    })
    url = f"{DRIVE_FILES_URL}?{params}"
    req = urllib.request.Request(url, headers=_headers(token), method="GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            files = data.get("files", [])
            if not files:
                return None
            f = files[0]
            size = int(f.get("size", 0))
            return CloudFile(
                file_id=f["id"],
                name=f["name"],
                modified_time=parse_iso_time(f.get("modifiedTime")),
                size_bytes=size,
            )
    except Exception as exc:  # noqa: BLE001
        log.warning("Drive AppData find failed: %s", exc)
        return None


def _download_save_sync(token: str, file_id: str) -> str | None:
    """Download save.json content as text."""
    url = f"{DRIVE_FILES_URL}/{file_id}?alt=media"
    req = urllib.request.Request(url, headers=_headers(token), method="GET")
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            return resp.read().decode("utf-8")
    except Exception as exc:  # noqa: BLE001
        log.warning("Drive AppData download failed: %s", exc)
        return None


def _upload_save_sync(token: str, json_text: str, existing_file_id: str | None = None) -> CloudFile | None:
    """Upload save.json to appDataFolder (update existing or multipart create)."""
    data_bytes = json_text.encode("utf-8")
    if existing_file_id:
        # Patch media directly
        url = f"{DRIVE_UPLOAD_URL}/{existing_file_id}?uploadType=media"
        req = urllib.request.Request(
            url,
            data=data_bytes,
            headers=_headers(token, "application/json; charset=utf-8"),
            method="PATCH",
        )
        try:
            with urllib.request.urlopen(req, timeout=25) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                return CloudFile(
                    file_id=res.get("id", existing_file_id),
                    name=SAVE_FILE_NAME,
                    modified_time=parse_iso_time(res.get("modifiedTime")),
                    size_bytes=len(data_bytes),
                )
        except Exception as exc:  # noqa: BLE001
            log.warning("Drive AppData update failed: %s", exc)
            return None

    # New file creation: multipart upload
    boundary = "-------314159265358979323846"
    delimiter = f"\r\n--{boundary}\r\n".encode()
    close_delim = f"\r\n--{boundary}--\r\n".encode()

    metadata = json.dumps({"name": SAVE_FILE_NAME, "parents": ["appDataFolder"]}).encode("utf-8")

    body = (
        delimiter
        + b"Content-Type: application/json; charset=UTF-8\r\n\r\n"
        + metadata
        + delimiter
        + b"Content-Type: application/json; charset=UTF-8\r\n\r\n"
        + data_bytes
        + close_delim
    )

    url = f"{DRIVE_UPLOAD_URL}?uploadType=multipart"
    req = urllib.request.Request(
        url,
        data=body,
        headers=_headers(token, f"multipart/related; boundary={boundary}"),
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            return CloudFile(
                file_id=res["id"],
                name=SAVE_FILE_NAME,
                modified_time=parse_iso_time(res.get("modifiedTime")),
                size_bytes=len(data_bytes),
            )
    except Exception as exc:  # noqa: BLE001
        log.warning("Drive AppData create failed: %s", exc)
        return None


# --- Asynchronous wrappers ---

async def find_save(token: str) -> CloudFile | None:
    return await asyncio.to_thread(_find_save_sync, token)


async def download_save(token: str, file_id: str) -> str | None:
    return await asyncio.to_thread(_download_save_sync, token, file_id)


async def upload_save(token: str, json_text: str, existing_file_id: str | None = None) -> CloudFile | None:
    return await asyncio.to_thread(_upload_save_sync, token, json_text, existing_file_id)
