"""Cloud Save synchronization manager for Life of Legends.

Coordinates Google OAuth sign-in, Google Drive AppData uploads/downloads,
and automatic background sync.
"""

from __future__ import annotations

import contextlib
import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import flet as ft
from flet.auth.providers import GoogleOAuthProvider

from lol.core import cloud_config, cloud_save, storage
from lol.core.cloud_save import SyncState
from lol.core.update_checker import UpdateInfo
from lol.ui import cloud_drive
from lol.ui import components as ui
from lol.ui.screens import common
from lol.ui.theme import C, Space, Type

if TYPE_CHECKING:
    from lol.ui.app import App

log = logging.getLogger(__name__)

AUTH_FILE = "cloud_auth.json"


class CloudSyncManager:
    """Singleton manager for Google Drive AppData cloud saving."""

    def __init__(self, app: App) -> None:
        self.app = app
        self.user_email: str | None = None
        self.user_name: str | None = None
        self.access_token: str | None = None
        self.refresh_token: str | None = None
        self.last_sync_time: datetime | None = None
        self.state: SyncState = SyncState.IDLE
        self.error_message: str | None = None
        self.cloud_file_id: str | None = None
        self.first_open_prompted: bool = False
        self.on_change: Callable[[], None] | None = None

    @property
    def is_signed_in(self) -> bool:
        return bool(self.access_token and self.user_email)

    def _notify(self) -> None:
        if self.on_change:
            with contextlib.suppress(Exception):
                self.on_change()

    def _auth_file_path(self):
        return storage.data_dir() / AUTH_FILE

    def restore_session(self) -> None:
        """Attempt to restore persisted Google OAuth session from disk."""
        try:
            path = self._auth_file_path()
            if not path.is_file():
                return
            data = json.loads(path.read_text(encoding="utf-8"))
            self.user_email = data.get("user_email")
            self.user_name = data.get("user_name")
            self.access_token = data.get("access_token")
            self.refresh_token = data.get("refresh_token")
            self.first_open_prompted = bool(data.get("first_open_prompted", False))
            last_sync_iso = data.get("last_sync_time")
            if last_sync_iso:
                self.last_sync_time = cloud_save.parse_iso_time(last_sync_iso)
            if self.is_signed_in:
                self.state = SyncState.SYNCED
        except Exception as exc:  # noqa: BLE001
            log.debug("Could not restore cloud auth session: %s", exc)

    def mark_first_open_prompted(self) -> None:
        """Record that the initial Google sign-in prompt has been shown."""
        self.first_open_prompted = True
        self._save_auth_state()

    def _save_auth_state(self) -> None:
        try:
            path = self._auth_file_path()
            payload = {
                "user_email": self.user_email,
                "user_name": self.user_name,
                "access_token": self.access_token,
                "refresh_token": self.refresh_token,
                "first_open_prompted": self.first_open_prompted,
                "last_sync_time": (
                    self.last_sync_time.isoformat() if self.last_sync_time else None
                ),
            }
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            log.warning("Could not persist cloud auth session: %s", exc)

    def init_page(self, page: ft.Page) -> None:
        """Register the login event listener on the Flet page and restore session."""
        page.on_login = self._on_login_event
        self.restore_session()

    def _on_login_event(self, e: Any) -> None:
        """Handle OAuth callback from page.login()."""
        page = self.app.page
        if getattr(e, "error", None):
            self.state = SyncState.ERROR
            self.error_message = str(e.error)
            log.warning("Google Login failed: %s", e.error)
            self.app.toast("Google sign-in failed", None)
            self._notify()
            return

        auth = getattr(page, "auth", None)
        if auth and auth.token:
            self.access_token = auth.token.access_token
            self.refresh_token = getattr(auth.token, "refresh_token", None)
            user = getattr(auth, "user", {}) or {}
            self.user_email = user.get("email") or "User"
            self.user_name = user.get("name") or self.user_email
            self.state = SyncState.IDLE
            self.error_message = None
            if (
                self.user_email
                and self.user_email.strip().lower() in cloud_config.DEV_EMAILS
                and self.app.game.unlock_dev()
            ):
                self.app.save()
            self._save_auth_state()
            self._notify()
            log.info("Signed in as %s", self.user_email)
            self.app.toast(f"Signed in as {self.user_email}", None)
            # Immediately trigger an initial sync in background
            page.run_task(self.sync)

    async def start_login(self) -> None:
        """Initiate the Google OAuth sign-in flow."""
        client_id = cloud_config.GOOGLE_CLIENT_ID
        client_secret = cloud_config.GOOGLE_CLIENT_SECRET
        if not client_id:
            self.app.toast("Google OAuth Client ID not configured", None)
            return

        provider = GoogleOAuthProvider(
            client_id=client_id,
            client_secret=client_secret,
            redirect_url=cloud_config.GOOGLE_REDIRECT_URL,
        )
        try:
            await self.app.page.login(provider, scope=cloud_config.DRIVE_SCOPES)
        except Exception as exc:  # noqa: BLE001
            log.warning("Google login exception: %s", exc)
            self.app.toast(f"Google sign-in error: {exc}", ft.Icons.ERROR_OUTLINE)

    async def sync(self) -> tuple[bool, str]:
        """Perform a bi-directional sync with Google Drive AppData."""
        if not self.is_signed_in or not self.access_token:
            return False, "Not signed in"

        self.state = SyncState.SYNCING
        self._notify()
        token = self.access_token
        try:
            # 1. Search for existing cloud save in AppData folder
            cloud_file = await cloud_drive.find_save(token)
            local_save = self.app.game.data
            local_json = storage.export_json(local_save)

            if cloud_file is not None:
                self.cloud_file_id = cloud_file.file_id
                # Download cloud save to compare
                cloud_raw = await cloud_drive.download_save(token, cloud_file.file_id)
                valid, _ = cloud_save.validate_cloud_json(cloud_raw or "")
                if valid and cloud_raw:
                    decision = cloud_save.compare_saves(
                        local_save,
                        self.last_sync_time,
                        cloud_file.modified_time,
                        cloud_raw,
                    )
                    if decision == "cloud_newer":
                        # Cloud save is newer: restore from cloud
                        was_onboarded = self.app.game.profile.onboarded
                        new_data = cloud_save.deserialize_from_cloud(cloud_raw)
                        self.app.game.data = new_data
                        storage.save(new_data)
                        self.last_sync_time = cloud_file.modified_time or datetime.now(UTC)
                        self.state = SyncState.SYNCED
                        self._save_auth_state()
                        self._notify()
                        with contextlib.suppress(Exception):
                            if not was_onboarded and new_data.profile.onboarded:
                                from lol.ui.app import TAB_TODAY, mount_shell

                                self.app.page.controls.clear()
                                mount_shell(self.app, TAB_TODAY, fade_in=True)
                            self.app.reload_state()
                        self.app.toast("Restored newer save from Google Drive!", None)
                        return True, "Restored newer save from cloud"

            # 2. Upload local save to Google Drive AppData
            uploaded = await cloud_drive.upload_save(
                token, local_json, existing_file_id=self.cloud_file_id
            )
            if uploaded:
                self.cloud_file_id = uploaded.file_id
                self.last_sync_time = datetime.now(UTC)
                self.state = SyncState.SYNCED
                self.error_message = None
                self._save_auth_state()
                self._notify()
                log.info("Cloud save synced successfully")
                return True, "Synced to Google Drive"

            self.state = SyncState.ERROR
            self.error_message = "Failed to upload to Google Drive"
            self._notify()
            return False, "Upload failed"

        except Exception as exc:  # noqa: BLE001
            self.state = SyncState.ERROR
            self.error_message = str(exc)
            self._notify()
            log.warning("Sync failed: %s", exc)
            return False, str(exc)

    def logout(self) -> None:
        """Sign out from Google Drive AppData."""
        self.access_token = None
        self.refresh_token = None
        self.user_email = None
        self.user_name = None
        self.cloud_file_id = None
        self.state = SyncState.IDLE
        self.last_sync_time = None
        self.error_message = None
        with contextlib.suppress(Exception):
            p = self._auth_file_path()
            if p.is_file():
                p.unlink()
        with contextlib.suppress(Exception):
            page_auth = getattr(self.app.page, "auth", None)
            if page_auth:
                page_auth.token = None
                page_auth.user = None
        self._notify()
        self.app.toast("Signed out from Google Drive", None)


async def open_store_url(page: ft.Page, url: str | None = None) -> None:
    """Open the app's Google Play Store listing using Flet's UrlLauncher."""
    target = url or cloud_config.PLAY_STORE_URL
    with contextlib.suppress(Exception):
        launcher_fn = getattr(page, "launch_url", None)
        if callable(launcher_fn):
            res = launcher_fn(target)
            if hasattr(res, "__await__"):
                await res
            return
        await ft.UrlLauncher().launch_url(target)


def prompt_first_open_google_login(app: App, on_done: Any = None) -> None:
    """Prompt the user on first open to sign in with Google for Cloud Save backup/restore."""
    if app.cloud.is_signed_in:
        if callable(on_done):
            on_done()
        return
    app.cloud.mark_first_open_prompted()

    sheet_ref: list[ft.BottomSheet] = []

    async def sign_in(_: Any = None) -> None:
        if sheet_ref:
            common.close(sheet_ref[0])
        await ui.buzz("light")
        await app.cloud.start_login()
        if callable(on_done):
            on_done()

    def skip(_: Any = None) -> None:
        if sheet_ref:
            common.close(sheet_ref[0])
        if callable(on_done):
            on_done()

    body = ft.Column(
        [
            ft.Container(
                ft.Icon(ft.Icons.CLOUD_DONE_ROUNDED, size=40, color=C.PRIMARY),
                width=72,
                height=72,
                shape=ft.BoxShape.CIRCLE,
                alignment=ft.Alignment.CENTER,
                bgcolor=C.a(C.PRIMARY, 0.14),
                border=ft.Border.all(1.5, C.a(C.PRIMARY, 0.65)),
            ),
            ft.Text(
                "Back up your hero, quests, and progress to Google Drive — or restore an "
                "existing save from another device.",
                size=Type.BODY,
                color=C.TEXT_DIM,
                text_align=ft.TextAlign.CENTER,
            ),
            ft.Container(height=Space.XS),
            common.primary_button("Sign in with Google", sign_in, icon=ft.Icons.LOGIN),
            common.secondary_button("Continue as Guest", skip, color=C.TEXT_DIM),
        ],
        spacing=Space.SM,
        tight=True,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
    )
    sheet_ref.append(common.open_sheet(app.page, "Sign in with Google", [body]))


def prompt_store_update(app: App, info: UpdateInfo) -> None:
    """Show a modal prompt when a newer version of the app is available in the Play Store."""
    if not info.available:
        return

    sheet_ref: list[ft.BottomSheet] = []

    async def go_store(_: Any = None) -> None:
        if sheet_ref:
            common.close(sheet_ref[0])
        await ui.buzz("medium")
        await open_store_url(app.page, info.store_url)

    def later(_: Any = None) -> None:
        if sheet_ref:
            common.close(sheet_ref[0])

    ver_badge = f"v{info.latest_version}" if info.latest_version else "New Version"
    body = ft.Column(
        [
            ft.Container(
                ft.Icon(ft.Icons.SYSTEM_UPDATE_ROUNDED, size=40, color=C.PRIMARY),
                width=72,
                height=72,
                shape=ft.BoxShape.CIRCLE,
                alignment=ft.Alignment.CENTER,
                bgcolor=C.a(C.PRIMARY, 0.14),
                border=ft.Border.all(1.5, C.a(C.PRIMARY, 0.65)),
            ),
            ft.Text(
                "A newer version of LUMA is live on the Google Play Store! Tap below to "
                "open the store and update for the latest features and fixes.",
                size=Type.BODY,
                color=C.TEXT_DIM,
                text_align=ft.TextAlign.CENTER,
            ),
            ft.Container(height=Space.XS),
            common.primary_button(
                "Update in Play Store",
                go_store,
                icon=ft.Icons.OPEN_IN_NEW,
            ),
            common.secondary_button("Later", later, color=C.TEXT_DIM),
        ],
        spacing=Space.SM,
        tight=True,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
    )
    sheet_ref.append(common.open_sheet(app.page, f"Update Available ({ver_badge})", [body]))

