import json
from unittest.mock import MagicMock, patch

from lol.ui import cloud_drive


def test_find_save_mock():
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps({
        "files": [{
            "id": "file_12345",
            "name": "save.json",
            "modifiedTime": "2026-11-06T12:00:00.000Z",
            "size": "4096",
        }],
    }).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = cloud_drive._find_save_sync("fake_token")
        assert res is not None
        assert res.file_id == "file_12345"
        assert res.name == "save.json"
        assert res.size_bytes == 4096


def test_download_save_mock():
    mock_resp = MagicMock()
    mock_resp.read.return_value = b'{"schema": 5, "profile": {"name": "Jeebs"}}'
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        content = cloud_drive._download_save_sync("fake_token", "file_12345")
        assert content is not None
        assert "Jeebs" in content

