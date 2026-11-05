"""More -> Backup & Export: what a backup holds, full JSON backup, CSV tables (one .zip), and
restore from a JSON backup (with a confirm step). Files go through ft.FilePicker.save_file
(desktop: a save dialog; web: a download; mobile: the system save dialog), plus the share sheet
on phones. If saving fails, the JSON is shown as copyable text instead."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

import flet as ft

from lol.core import storage
from lol.ui import components as ui
from lol.ui import sfx
from lol.ui.screens import common
from lol.ui.theme import C, Radius, Space, Type

if TYPE_CHECKING:
    from lol.ui.app import App

# Luma's staged analysis while a confirmed backup is applied
RESTORE_STAGES = ("VERIFYING BACKUP…", "RESTORING RECORDS…", "RESTORE COMPLETE")

LABELS = {
    "quests": "Quests", "quest_completions": "Quest completions",
    "side_quests": "Side quests", "skills": "Skills", "bills": "Bills",
    "bill_payments": "Bill payments", "rewards": "Rewards", "redemptions": "Redemptions",
    "logs": "Log entries", "focus_sessions": "Focus sessions", "templates": "Your templates",
}


class BackupScreen:
    title = "Backup & Export"

    def __init__(self, app: App) -> None:
        self.app = app
        self._picker: ft.FilePicker | None = None
        self.list = common.screen_list()
        self.view = ft.Container(self.list, expand=True, key="backup")

    def picker(self) -> ft.FilePicker:
        if self._picker is None:
            self._picker = ft.FilePicker()  # a service: registers itself with the page
        return self._picker

    def _mobile(self) -> bool:
        try:
            return bool(self.app.page.platform and self.app.page.platform.is_mobile()
                        and not self.app.page.web)
        except (AttributeError, TypeError, ValueError):
            return False

    # ------------------------------------------------------------------ render
    def render(self) -> None:
        summary = storage.summary(self.app.game.data)
        rows = [ft.Row([ft.Text(LABELS.get(k, k), size=Type.LABEL, color=C.TEXT_DIM,
                                expand=True),
                        ft.Text(f"{v:,}", size=Type.LABEL, color=C.TEXT,
                                weight=ft.FontWeight.BOLD)])
                for k, v in summary.items()]
        items: list[ft.Control] = [
            ui.SectionHeader("What's included"),
            common.card(ft.Column([
                common.hint("Your profile (name, avatar, level, coins, Path XP, settings, "
                            "themes) plus everything below, with full history."),
                *rows,
                ft.Row([ft.Icon(ft.Icons.LOCK, size=16, color=C.ACCENT),
                        ft.Text("Backups can include bills and personal notes. Keep the file "
                                "somewhere private.", size=Type.CAPTION, color=C.TEXT_DIM,
                                expand=True)], spacing=Space.SM),
            ], spacing=Space.XS + 2, tight=True), padding=Space.MD),
            ui.SectionHeader("Export"),
            self._action("Export full backup (JSON)", "Everything, restorable later",
                         ft.Icons.DOWNLOAD, self._export_json),
            self._action("Export tables (CSV, .zip)", "Readable in any spreadsheet app",
                         ft.Icons.TABLE_CHART, self._export_csv),
        ]
        if self._mobile():
            items.append(self._action("Share backup", "Send the JSON with the share sheet",
                                      ft.Icons.SHARE, self._share_json))
        items += [
            ui.SectionHeader("Restore"),
            self._action("Restore from a JSON backup", "Replaces your current progress",
                         ft.Icons.UPLOAD_FILE, self._restore, color=C.DANGER),
        ]
        self.list.controls = items

    def restyle(self) -> None:
        self.render()
        ui.refresh(self.list)

    @staticmethod
    def _action(title: str, sub: str, icon: ft.IconData, fn, *,
                color: str = C.PRIMARY) -> ft.Control:
        return ft.Container(ft.Row([
            ui.path_avatar(icon, color, 40),
            ft.Column([ft.Text(title, size=Type.BODY, weight=ft.FontWeight.W_600,
                               color=C.TEXT), common.hint(sub)],
                      spacing=0, expand=True, tight=True),
            ft.Icon(ft.Icons.CHEVRON_RIGHT, color=C.TEXT_DIM),
        ], spacing=Space.MD, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            bgcolor=C.SURFACE_HI, border_radius=Radius.MD, ink=True,
            padding=ft.Padding.symmetric(horizontal=Space.MD, vertical=Space.SM + 2),
            on_click=common.with_sound(fn))

    # ------------------------------------------------------------------ export
    def _stamp(self) -> str:
        return self.app.today().isoformat()

    def _json_bytes(self) -> bytes:
        return storage.export_json(self.app.game.data).encode("utf-8")

    def _csv_zip(self) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for name, text in storage.export_csv(self.app.game.data).items():
                z.writestr(name, text.encode("utf-8-sig"))  # BOM: Excel reads UTF-8 right
        return buf.getvalue()

    async def _save(self, name: str, data: bytes, ext: str) -> bool | None:
        """True saved / downloading, False cancelled, None failed."""
        try:
            path = await self.picker().save_file(
                dialog_title="Save LUMA: Your Lifestyle QoL export", file_name=name,
                file_type=ft.FilePickerFileType.CUSTOM, allowed_extensions=[ext],
                src_bytes=data)
        except Exception as exc:  # noqa: BLE001 - any platform failure -> fallback below
            self.app.error(f"Couldn't save the file ({exc.__class__.__name__}).")
            return None
        if self.app.page.web:
            self.app.toast(f"Downloading {name}", ft.Icons.DOWNLOAD)
            return True
        if not path:
            self.app.toast("Export cancelled", ft.Icons.INFO_OUTLINE)
            return False
        p = Path(path)
        if not self._mobile() and (not p.exists() or p.stat().st_size == 0):
            p.write_bytes(data)  # desktop pickers that only return a path
        self.app.toast(f"Saved {p.name}", ft.Icons.TASK_ALT)
        return True

    async def _export_json(self, _: Any = None) -> None:
        name = f"life-of-legends-backup-{self._stamp()}.json"
        if await self._save(name, self._json_bytes(), "json") is None:
            self._show_text(storage.export_json(self.app.game.data))

    async def _export_csv(self, _: Any = None) -> None:
        name = f"life-of-legends-tables-{self._stamp()}.zip"
        await self._save(name, self._csv_zip(), "zip")

    async def _share_json(self, _: Any = None) -> None:
        name = f"life-of-legends-backup-{self._stamp()}.json"
        try:
            await ft.Share().share_files(
                [ft.ShareFile.from_bytes(self._json_bytes(), mime_type="application/json",
                                         name=name)],
                subject="LUMA: Your Lifestyle QoL backup")
        except Exception:  # noqa: BLE001
            self.app.error("Sharing isn't available here. Try Export instead.")

    def _show_text(self, text: str) -> None:
        """Fallback: the backup as copyable text."""
        field = ft.TextField(value=text, multiline=True, min_lines=6, max_lines=12,
                             read_only=True, text_size=11, border_radius=Radius.SM,
                             filled=True, fill_color=C.SURFACE_HI, color=C.TEXT)

        async def copy(_: Any = None) -> None:
            await ft.Clipboard().set(text)
            self.app.toast("Backup copied", ft.Icons.CONTENT_COPY)

        common.open_sheet(self.app.page, "Backup as text", [
            common.hint("Saving a file didn't work here. Copy this text and keep it somewhere "
                        "private; restoring needs it saved as a .json file."),
            field, ft.Row([common.primary_button("Copy", copy, icon=ft.Icons.CONTENT_COPY)]),
        ])

    # ------------------------------------------------------------------ restore
    async def _restore(self, _: Any = None) -> None:
        app = self.app
        try:
            files = await self.picker().pick_files(
                dialog_title="Choose a LUMA: Your Lifestyle QoL backup",
                file_type=ft.FilePickerFileType.CUSTOM, allowed_extensions=["json"],
                with_data=True)
        except Exception as exc:  # noqa: BLE001
            app.error(f"Couldn't open the file picker ({exc.__class__.__name__}).")
            return
        if not files:
            return
        f = files[0]
        try:
            raw = f.bytes if f.bytes is not None else Path(f.path or "").read_bytes()
            data = storage.import_json(raw.decode("utf-8-sig"), app.today())
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            app.error(f"That file isn't a LUMA: Your Lifestyle QoL backup: {exc}")
            return
        s = storage.summary(data)
        what = (f"{data.profile.name} · Lv {data.profile.level} · {s['quests']} quests, "
                f"{s['bills']} bills, {s['logs']} logs, {s['focus_sessions']} focus sessions.")
        sfx.play("alert_soft", 0.7)
        ok = await common.confirm(
            app.page, "Restore this backup?",
            f"This replaces your current progress on this device with the backup:\n{what}\n\n"
            "Tip: export your current progress first if you might want it back.",
            "Replace and restore", danger=True)
        if not ok:
            return

        def apply() -> None:
            app.game.data = data
            app.save()

        await ui.lumen_analyze(app.page, RESTORE_STAGES, apply, seconds=2.2)
        app.reload_state()
        app.lumen("profile_saved", ft.Icons.RESTORE)
        app.toast(f"Restored {f.name}", ft.Icons.RESTORE)
