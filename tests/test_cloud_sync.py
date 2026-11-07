import json
from unittest.mock import MagicMock

from lol.core.cloud_save import SyncState
from lol.ui.cloud_sync import CloudSyncManager


def test_cloud_sync_manager_initial_state():
    mock_app = MagicMock()
    mgr = CloudSyncManager(mock_app)
    assert not mgr.is_signed_in
    assert mgr.user_email is None
    assert mgr.access_token is None
    assert mgr.state == SyncState.IDLE


def test_cloud_sync_manager_login_event():
    mock_app = MagicMock()
    page = MagicMock()
    mock_app.page = page
    page.auth.token.access_token = "mock_access_token_123"
    page.auth.token.refresh_token = "mock_refresh_token_456"
    page.auth.user = {"email": "hero@gmail.com", "name": "Hero"}

    mgr = CloudSyncManager(mock_app)
    event = MagicMock()
    event.error = None
    mgr._on_login_event(event)

    assert mgr.is_signed_in
    assert mgr.user_email == "hero@gmail.com"
    assert mgr.access_token == "mock_access_token_123"
    assert mgr.refresh_token == "mock_refresh_token_456"
    page.run_task.assert_called_once_with(mgr.sync)


def test_cloud_sync_manager_login_failure():
    mock_app = MagicMock()
    mgr = CloudSyncManager(mock_app)
    event = MagicMock()
    event.error = "access_denied"
    mgr._on_login_event(event)

    assert not mgr.is_signed_in
    assert mgr.state == SyncState.ERROR
    assert mgr.error_message == "access_denied"
    mock_app.toast.assert_called_once_with("Google sign-in failed", None)


def test_cloud_sync_manager_session_persistence(tmp_path, monkeypatch):
    monkeypatch.setattr("lol.core.storage.data_dir", lambda: tmp_path)
    mock_app = MagicMock()
    mock_app.page = MagicMock()

    mgr = CloudSyncManager(mock_app)
    mgr.user_email = "test@example.com"
    mgr.user_name = "Test User"
    mgr.access_token = "saved_token_xyz"
    mgr.refresh_token = "saved_refresh_xyz"
    mgr._save_auth_state()

    auth_file = tmp_path / "cloud_auth.json"
    assert auth_file.exists()
    data = json.loads(auth_file.read_text(encoding="utf-8"))
    assert data["user_email"] == "test@example.com"

    # Restore in new manager instance
    mgr2 = CloudSyncManager(mock_app)
    mgr2.restore_session()
    assert mgr2.is_signed_in
    assert mgr2.user_email == "test@example.com"
    assert mgr2.access_token == "saved_token_xyz"

    # Logout cleans up
    mgr2.logout()
    assert not mgr2.is_signed_in
    assert not auth_file.exists()
