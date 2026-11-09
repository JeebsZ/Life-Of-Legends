"""Interactive Device Permissions & Local Storage Trust Manager.

Provides user-friendly explanations and interactive permission request flows for:
- Local Storage & Photos (saving/reading payment QR codes, receipt scans, JSON/CSV backups)
- Camera (scanning receipts, meal photos, study flashcards)
- Notifications (daily quest & water reminders)
- Location (GPS walk/run route tracking)

If a permission is denied or permanently denied on Android/iOS, offers a one-tap
"Open System Settings" action via `flet_permission_handler.PermissionHandler().open_app_settings()`.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

import flet as ft

from lol.ui import components as ui
from lol.ui import sfx
from lol.ui.screens import common
from lol.ui.theme import C, Radius, Space, Type

if TYPE_CHECKING:
    from lol.ui.app import App

try:
    import flet_permission_handler as fph
except ImportError:  # pragma: no cover
    fph = None  # type: ignore[assignment]


def is_mobile(page: ft.Page | None) -> bool:
    """Return True when running on native Android or iOS."""
    if page is None:
        return False
    try:
        return bool(page.platform and page.platform.is_mobile() and not page.web)
    except (AttributeError, TypeError, ValueError):
        return False


def _handler(page: ft.Page) -> Any:
    if fph is None:
        return None
    cached = getattr(page, "_luma_perm_handler", None)
    if cached is not None:
        return cached
    try:
        ph = fph.PermissionHandler()
        page._luma_perm_handler = ph  # type: ignore[attr-defined]
        return ph
    except Exception:  # noqa: BLE001
        return None


async def open_system_settings(app: App) -> bool:
    """Open the operating system's App Settings screen for LUMA."""
    ph = _handler(app.page)
    if ph is None:
        app.toast("Open your device Settings > Apps > LUMA > Permissions.", ft.Icons.SETTINGS)
        return False
    try:
        opened = await ph.open_app_settings()
        return bool(opened)
    except Exception:  # noqa: BLE001
        app.toast("Open your device Settings > Apps > LUMA > Permissions.", ft.Icons.SETTINGS)
        return False


async def check_status(page: ft.Page, perm_key: str) -> str:
    """Check live permission status ('granted', 'denied', 'permanently_denied', or 'desktop')."""
    if not is_mobile(page) or fph is None:
        return "granted"
    ph = _handler(page)
    if ph is None:
        return "granted"

    perm_map = {
        "storage": [fph.Permission.PHOTOS, fph.Permission.STORAGE],
        "camera": [fph.Permission.CAMERA],
        "notification": [fph.Permission.NOTIFICATION],
        "location": [fph.Permission.LOCATION_WHEN_IN_USE, fph.Permission.LOCATION],
    }
    targets = perm_map.get(perm_key, [])
    for p in targets:
        with contextlib.suppress(Exception):
            st = await ph.get_status(p)
            if st in (
                fph.PermissionStatus.GRANTED,
                fph.PermissionStatus.LIMITED,
                fph.PermissionStatus.PROVISIONAL,
            ):
                return "granted"
            if st == fph.PermissionStatus.PERMANENTLY_DENIED:
                return "permanently_denied"
    return "denied"


async def request_permission_interactive(
    app: App,
    perm_key: str,
    title: str,
    reason: str,
    icon: ft.IconData = ft.Icons. SECURITY_ROUNDED,
) -> bool:
    """Explain why a permission is needed, request it, or offer System Settings if blocked."""
    if not is_mobile(app.page) or fph is None:
        return True

    status = await check_status(app.page, perm_key)
    if status == "granted":
        return True

    # Ask the user with a friendly explanation first so it builds trust
    proceed = await common.confirm(
        app.page,
        title,
        f"{reason}\n\nTap 'Continue' to grant access, or 'Open Settings' if you previously disabled it.",
        "Continue",
    )
    if not proceed:
        return False

    ph = _handler(app.page)
    if ph is None:
        return True

    perm_map = {
        "storage": [fph.Permission.PHOTOS, fph.Permission.STORAGE],
        "camera": [fph.Permission.CAMERA],
        "notification": [fph.Permission.NOTIFICATION],
        "location": [fph.Permission.LOCATION_WHEN_IN_USE],
    }
    for p in perm_map.get(perm_key, []):
        with contextlib.suppress(Exception):
            st = await ph.request(p)
            if st in (
                fph.PermissionStatus.GRANTED,
                fph.PermissionStatus.LIMITED,
                fph.PermissionStatus.PROVISIONAL,
            ):
                sfx.play("milestone")
                app.toast(f"{title} enabled!", icon)
                return True

    # If still not granted, offer one-tap jump to Android/iOS System Settings
    open_set = await common.confirm(
        app.page,
        f"Enable {title} in Settings",
        f"Your phone blocked the popup for {title}. Would you like to open LUMA's System Settings to toggle it on?",
        "Open Settings",
    )
    if open_set:
        await open_system_settings(app)
    return False


async def ensure_storage_permission(app: App, purpose: str = "save and load files locally on your device") -> bool:
    """Request Local Storage / Photos permission before saving backups, QR codes, or scanning receipts."""
    return await request_permission_interactive(
        app,
        "storage",
        "Local Storage & Photos Access",
        f"LUMA needs permission to {purpose}. All files stay private on your device.",
        ft.Icons.FOLDER_SPECIAL_ROUNDED,
    )


async def ensure_camera_permission(app: App, purpose: str = "scan receipts, meals, and study notes") -> bool:
    """Request Camera permission with a clear explanation."""
    return await request_permission_interactive(
        app,
        "camera",
        "Camera Access",
        f"LUMA uses your camera to {purpose}. Photos are processed locally and never uploaded.",
        ft.Icons.CAMERA_ALT_ROUNDED,
    )


PERM_ITEMS: tuple[tuple[str, str, str, ft.IconData], ...] = (
    (
        "camera",
        "Camera",
        "Scan paper receipts, meals, and study flashcards.",
        ft.Icons.CAMERA_ALT_ROUNDED,
    ),
    (
        "notification",
        "Notifications",
        "Quest reminders, hydration pings, and streak alerts.",
        ft.Icons.NOTIFICATIONS_ACTIVE_ROUNDED,
    ),
    (
        "location",
        "GPS Location",
        "Map your walk/run routes and distance challenges.",
        ft.Icons.LOCATION_ON_ROUNDED,
    ),
)


def permissions_card(app: App) -> ft.Control:
    """Interactive card for Settings & Backup screens showing device permissions & System Settings link."""
    rows_col = ft.Column(spacing=Space.XS, tight=True)

    async def refresh_statuses() -> None:
        new_rows: list[ft.Control] = []
        mobile = is_mobile(app.page)
        for key, label, desc, icon in PERM_ITEMS:
            st = await check_status(app.page, key) if mobile else "granted"
            granted = st == "granted"
            badge_text = "Granted ✓" if granted else ("Settings" if st == "permanently_denied" else "Allow")
            badge_col = C.SUCCESS if granted else C.PRIMARY

            async def on_tap(_: Any = None, k=key, lbl=label, d=desc, ic=icon, is_ok=granted) -> None:
                await ui.buzz("light")
                if is_ok and mobile:
                    await open_system_settings(app)
                elif not is_ok:
                    await request_permission_interactive(app, k, lbl, d, ic)
                    await refresh_statuses()
                else:
                    app.toast(f"{lbl} is active on this device.", ic)

            btn = ft.Container(
                ft.Text(
                    badge_text,
                    size=Type.CAPTION,
                    weight=ft.FontWeight.W_800,
                    color=C.SUCCESS if granted else C.ON_PRIMARY,
                ),
                bgcolor=C.a(C.SUCCESS, 0.16) if granted else badge_col,
                border_radius=Radius.PILL,
                padding=ft.Padding.symmetric(horizontal=12, vertical=6),
                on_click=lambda e, fn=on_tap: app.page.run_task(fn),
                ink=True,
            )
            new_rows.append(
                ft.Row(
                    [
                        ft.Icon(icon, color=C.PRIMARY if granted else C.TEXT_DIM, size=22),
                        ft.Column(
                            [
                                ft.Text(label, size=Type.BODY, weight=ft.FontWeight.W_700, color=C.TEXT),
                                ft.Text(desc, size=Type.CAPTION, color=C.TEXT_DIM),
                            ],
                            spacing=1,
                            expand=True,
                            tight=True,
                        ),
                        btn,
                    ],
                    spacing=Space.SM,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                )
            )
        rows_col.controls = new_rows
        ui.refresh(rows_col)

    if app.page:
        app.page.run_task(refresh_statuses)

    return common.card(
        ft.Column(
            [
                common.hint(
                    "Photos and backups use Android's private photo & file pickers — no broad storage access needed! "
                    "Review or toggle device permissions anytime:"
                ),
                rows_col,
                ft.Row(
                    [
                        common.secondary_button(
                            "Open System Settings",
                            lambda _: app.page.run_task(open_system_settings, app),
                            icon=ft.Icons.OPEN_IN_NEW,
                        ),
                    ]
                ),
            ],
            spacing=Space.SM,
            tight=True,
        ),
        padding=Space.MD,
    )
