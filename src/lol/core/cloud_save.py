"""Core Cloud Save logic for Life of Legends.

Pure Python, zero UI dependencies. Handles:
- Sync status tracking (synced, syncing, conflict, error)
- Google Drive AppData file metadata parsing
- Conflict resolution (comparing local vs cloud save modified dates and progression)
- Save serialization/deserialization validation
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum

from lol.core import storage
from lol.core.models import SaveData


class SyncState(str, Enum):
    IDLE = "idle"
    SYNCING = "syncing"
    SYNCED = "synced"
    CONFLICT = "conflict"
    ERROR = "error"


@dataclass(frozen=True)
class CloudFile:
    file_id: str
    name: str
    modified_time: datetime | None
    size_bytes: int = 0


def parse_iso_time(iso_str: str | None) -> datetime | None:
    """Parse Google Drive RFC 3339 / ISO 8601 timestamp string into UTC datetime."""
    if not iso_str:
        return None
    try:
        # Handles e.g. "2026-11-06T12:34:56.789Z"
        clean = iso_str.replace("Z", "+00:00")
        return datetime.fromisoformat(clean)
    except (ValueError, TypeError):
        return None


def format_iso_time(dt: datetime | None) -> str:
    """Format datetime into standard ISO 8601 UTC string."""
    if dt is None:
        dt = datetime.now(UTC)
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat()


def compare_saves(
    local_data: SaveData,
    local_modified: datetime | None,
    cloud_modified: datetime | None,
    cloud_raw_json: str | None = None,
) -> str:
    """Compare local vs cloud saves.

    Returns:
    - "cloud_newer": Cloud save is strictly newer
    - "local_newer": Local save is newer or equal
    - "identical": Both have identical timestamps or identical content
    """
    if cloud_modified is None:
        return "local_newer"
    if local_modified is None:
        return "cloud_newer"

    # Normalize to UTC
    loc = local_modified if local_modified.tzinfo else local_modified.replace(tzinfo=UTC)
    cld = cloud_modified if cloud_modified.tzinfo else cloud_modified.replace(tzinfo=UTC)

    # Allow a small 3-second tolerance for file transfer latency
    delta = (cld - loc).total_seconds()
    if abs(delta) <= 3.0:
        return "identical"
    if delta > 3.0:
        return "cloud_newer"
    return "local_newer"


def validate_cloud_json(raw_json: str) -> tuple[bool, str]:
    """Validate whether downloaded cloud JSON is a valid Life of Legends save."""
    if not raw_json or not raw_json.strip():
        return False, "Empty cloud data"
    try:
        import json
        parsed = json.loads(raw_json)
        if not isinstance(parsed, dict):
            return False, "JSON root is not an object"
        if "schema" not in parsed and "hero" not in parsed:
            return False, "Missing schema or hero key in save payload"
        return True, "Valid"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def serialize_for_cloud(save: SaveData) -> str:
    """Serialize local save for cloud upload."""
    return storage.export_json(save)


def deserialize_from_cloud(raw_json: str) -> SaveData:
    """Deserialize cloud JSON into SaveData, performing all migrations automatically."""
    import json
    data_dict = json.loads(raw_json)
    return storage.from_dict(data_dict)
