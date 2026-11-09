"""Media Studio & Aesthetic Lens: Smart Gallery Declutter & Instagram Post Scorer screen.

Batch purges screenshots and TikTok saves, and evaluates photos for Instagram aesthetic readiness.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import flet as ft

from lol.core import media_curator
from lol.ui import components as ui
from lol.ui import sfx
from lol.ui.screens import common
from lol.ui.theme import C, Radius, Space, Type

if TYPE_CHECKING:
    from lol.ui.app import App


class MediaCuratorScreen:
    title = "Media Studio"

    def __init__(self, app: App) -> None:
        self.app = app
        self.list = common.screen_list()
        self.view = ft.Container(self.list, expand=True, key="media_curator_screen")
        self.current_folder: str = self._default_folder()
        self.items: list[media_curator.MediaFileItem] = []
        self.current_filter: str = "all"  # "all", "screenshot", "social_save", "camera"
        self.file_picker = ft.FilePicker()
        self.app.page.overlay.append(self.file_picker)

    def _default_folder(self) -> str:
        # Standard pictures / downloads / screenshots directories
        home = Path.home()
        for candidate in [
            home / "Pictures" / "Screenshots",
            home / "Pictures",
            home / "Downloads",
            home / "DCIM",
        ]:
            if candidate.exists() and candidate.is_dir():
                return str(candidate)
        return str(home)

    def on_enter(self) -> None:
        self._rescan()
        self.render()

    def _rescan(self) -> None:
        self.items = media_curator.scan_media_folder(self.current_folder, max_items=120)

    def render(self) -> None:
        self.list.controls.clear()

        # 1. Header Card with Folder Info & Stats
        self.list.controls.append(self._header_card())

        # 2. Filter Tabs
        self.list.controls.append(self._filter_tabs())

        # 3. Batch Action Bar
        self.list.controls.append(self._batch_bar())

        # 4. Media Items
        filtered = self._filtered_items()
        if not filtered:
            self.list.controls.append(
                common.card(
                    ui.EmptyState(
                        "No photos found in this category",
                        f"Folder: {Path(self.current_folder).name}",
                        icon=ft.Icons.PHOTO_LIBRARY_OUTLINED,
                        action_text="Change Folder",
                        on_action=lambda _: self._open_folder_picker(),
                    ),
                    padding=0,
                )
            )
        else:
            for item in filtered:
                self.list.controls.append(self._item_card(item))

        ui.refresh(self.list)

    def _filtered_items(self) -> list[media_curator.MediaFileItem]:
        if self.current_filter == "all":
            return self.items
        return [it for it in self.items if it.category == self.current_filter]

    def _header_card(self) -> ft.Control:
        total = len(self.items)
        screenshots = sum(1 for it in self.items if it.category == "screenshot")
        social = sum(1 for it in self.items if it.category == "social_save")
        camera = sum(1 for it in self.items if it.category == "camera")

        folder_name = Path(self.current_folder).name or self.current_folder

        return common.card(
            ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.PHOTO_LIBRARY_ROUNDED, color="#FF6B6B", size=26),
                            ft.Column(
                                [
                                    ft.Text(
                                        "MEDIA STUDIO & CLEANER",
                                        size=Type.CAPTION,
                                        weight=ft.FontWeight.W_800,
                                        color="#FF6B6B",
                                    ),
                                    ft.Text(
                                        "Declutter & Aesthetic Lens",
                                        size=Type.TITLE,
                                        weight=ft.FontWeight.BOLD,
                                        color=C.TEXT,
                                    ),
                                ],
                                spacing=0,
                                expand=True,
                            ),
                            ft.FilledButton(
                                "Folder",
                                icon=ft.Icons.FOLDER_OPEN,
                                style=ft.ButtonStyle(
                                    bgcolor=C.a(C.SURFACE_HI, 0.6),
                                    color=C.TEXT,
                                    shape=ft.RoundedRectangleBorder(radius=Radius.PILL),
                                ),
                                on_click=lambda _: self._open_folder_picker(),
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Text(
                        f"Scanning: {folder_name} ({total} images found)",
                        size=Type.CAPTION,
                        color=C.TEXT_DIM,
                    ),
                    ft.Divider(height=1, color=C.a(C.OUTLINE, 0.4)),
                    ft.Row(
                        [
                            ft.Container(
                                ft.Column(
                                    [
                                        ft.Text(str(screenshots), size=Type.TITLE, weight=ft.FontWeight.BOLD, color="#FFB347"),
                                        ft.Text("Screenshots", size=Type.CAPTION - 2, color=C.TEXT_DIM),
                                    ],
                                    spacing=0,
                                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                ),
                                expand=True,
                            ),
                            ft.Container(
                                ft.Column(
                                    [
                                        ft.Text(str(social), size=Type.TITLE, weight=ft.FontWeight.BOLD, color="#C77DFF"),
                                        ft.Text("TikTok / Social", size=Type.CAPTION - 2, color=C.TEXT_DIM),
                                    ],
                                    spacing=0,
                                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                ),
                                expand=True,
                            ),
                            ft.Container(
                                ft.Column(
                                    [
                                        ft.Text(str(camera), size=Type.TITLE, weight=ft.FontWeight.BOLD, color="#06D6A0"),
                                        ft.Text("Camera", size=Type.CAPTION - 2, color=C.TEXT_DIM),
                                    ],
                                    spacing=0,
                                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                ),
                                expand=True,
                            ),
                        ],
                        spacing=Space.SM,
                    ),
                ],
                spacing=Space.SM,
            ),
            tint="#FF6B6B",
        )

    def _filter_tabs(self) -> ft.Control:
        tabs = [
            ("all", "All"),
            ("screenshot", "📱 Screenshots"),
            ("social_save", "🎵 TikTok/Social"),
            ("camera", "📸 Camera"),
        ]

        chips: list[ft.Control] = []
        for key, label in tabs:
            is_active = self.current_filter == key

            def make_click(k: str):
                def on_click(_):
                    if self.current_filter != k:
                        self.current_filter = k
                        sfx.play("tab_open")
                        self.render()
                return on_click

            chips.append(
                ft.Container(
                    ft.Text(
                        label,
                        size=Type.CAPTION,
                        weight=ft.FontWeight.BOLD if is_active else ft.FontWeight.W_500,
                        color=C.TEXT if is_active else C.TEXT_DIM,
                    ),
                    padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                    border_radius=Radius.PILL,
                    bgcolor=C.a("#FF6B6B", 0.25) if is_active else C.a(C.SURFACE_HI, 0.4),
                    border=ft.Border.all(1, "#FF6B6B" if is_active else C.a(C.OUTLINE, 0.4)),
                    on_click=make_click(key),
                )
            )

        return ft.Row(chips, spacing=Space.SM, scroll=ft.ScrollMode.AUTO)

    def _batch_bar(self) -> ft.Control:
        filtered = self._filtered_items()
        selected = [it for it in filtered if it.is_selected]
        sel_count = len(selected)
        total_kb = sum(it.file_size_kb for it in selected)
        size_str = f"{total_kb / 1024:.1f} MB" if total_kb >= 1024 else f"{total_kb} KB"

        def toggle_all(_):
            all_on = all(it.is_selected for it in filtered)
            for it in filtered:
                it.is_selected = not all_on
            self.render()

        def do_batch_delete(_):
            if not selected:
                return

            async def confirm_del():
                ok = await common.confirm(
                    self.app.page,
                    f"Delete {sel_count} files?",
                    f"This will permanently delete the selected images and free up {size_str}.",
                    "Delete",
                    danger=True,
                )
                if ok:
                    paths = [it.path for it in selected]
                    succeeded, _failed = media_curator.batch_delete_files(paths)
                    sfx.play("trash" if "trash" in sfx.SOUNDS else "coin")
                    self.app.toast(f"🗑️ Deleted {succeeded} files ({size_str} freed)!", ft.Icons.DELETE_SWEEP)
                    self._rescan()
                    self.render()

            self.app.page.run_task(confirm_del)

        return common.card(
            ft.Row(
                [
                    ft.Row(
                        [
                            ft.Checkbox(
                                value=all(it.is_selected for it in filtered) if filtered else False,
                                on_change=toggle_all,
                            ),
                            ft.Text(
                                f"Select All ({sel_count} selected • {size_str})",
                                size=Type.CAPTION,
                                color=C.TEXT,
                            ),
                        ],
                        spacing=Space.XS,
                        expand=True,
                    ),
                    ft.FilledButton(
                        f"Purge ({sel_count})",
                        icon=ft.Icons.DELETE_FOREVER,
                        style=ft.ButtonStyle(
                            bgcolor=C.ERROR if sel_count > 0 else C.a(C.SURFACE_HI, 0.5),
                            color="#FFFFFF" if sel_count > 0 else C.TEXT_DIM,
                            shape=ft.RoundedRectangleBorder(radius=Radius.PILL),
                        ),
                        disabled=sel_count == 0,
                        on_click=do_batch_delete,
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            padding=Space.SM,
        )

    def _item_card(self, item: media_curator.MediaFileItem) -> ft.Control:
        cat_badge_color = "#FFB347" if item.category == "screenshot" else ("#C77DFF" if item.category == "social_save" else "#06D6A0")
        cat_label = "Screenshot" if item.category == "screenshot" else ("TikTok/Social" if item.category == "social_save" else "Camera")

        def on_check(e):
            item.is_selected = bool(e.control.value)
            self.render()

        def analyze_ig(_):
            report = media_curator.analyze_image_aesthetic(item.path)
            item.report = report
            self._show_aesthetic_modal(item, report)

        return common.card(
            ft.Row(
                [
                    ft.Checkbox(value=item.is_selected, on_change=on_check),
                    ft.Container(
                        ft.Image(
                            src=item.path,
                            width=60,
                            height=60,
                            fit=ft.BoxFit.COVER,
                            border_radius=Radius.SM,
                        ),
                        width=60,
                        height=60,
                        border_radius=Radius.SM,
                        bgcolor=C.a(C.SURFACE_HI, 0.5),
                    ),
                    ft.Column(
                        [
                            ft.Text(
                                item.filename,
                                size=Type.BODY - 1,
                                weight=ft.FontWeight.BOLD,
                                color=C.TEXT,
                                max_lines=1,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                            ft.Row(
                                [
                                    ft.Container(
                                        ft.Text(cat_label, size=Type.CAPTION - 3, color=cat_badge_color, weight=ft.FontWeight.BOLD),
                                        padding=ft.Padding.symmetric(horizontal=6, vertical=2),
                                        bgcolor=C.a(cat_badge_color, 0.18),
                                        border_radius=Radius.PILL,
                                    ),
                                    ft.Text(f"{item.file_size_kb} KB", size=Type.CAPTION - 2, color=C.TEXT_DIM),
                                ],
                                spacing=4,
                            ),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    ft.FilledButton(
                        "IG Score",
                        icon=ft.Icons.AUTO_AWESOME,
                        style=ft.ButtonStyle(
                            bgcolor=C.a(C.PRIMARY, 0.2),
                            color=C.PRIMARY,
                            shape=ft.RoundedRectangleBorder(radius=Radius.PILL),
                        ),
                        on_click=analyze_ig,
                    ),
                ],
                spacing=Space.SM,
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            padding=Space.SM,
        )

    def _show_aesthetic_modal(
        self, item: media_curator.MediaFileItem, report: media_curator.AestheticReport
    ) -> None:
        score_color = C.GOLD if report.score >= 80 else (C.PRIMARY if report.score >= 70 else C.TEXT_DIM)

        badges_chips: list[ft.Control] = []
        for b in report.badges:
            badges_chips.append(
                ft.Container(
                    ft.Text(b, size=Type.CAPTION - 1, weight=ft.FontWeight.BOLD, color=C.GOLD),
                    padding=ft.Padding.symmetric(horizontal=8, vertical=4),
                    bgcolor=C.a(C.GOLD, 0.15),
                    border_radius=Radius.PILL,
                )
            )

        tips_rows: list[ft.Control] = []
        for s in report.suggestions:
            tips_rows.append(
                ft.Row(
                    [
                        ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, size=15, color="#06D6A0"),
                        ft.Text(s, size=Type.CAPTION, color=C.TEXT, expand=True),
                    ],
                    spacing=Space.SM,
                )
            )

        bs = ft.BottomSheet(
            ft.Container(
                ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Row(
                                    [
                                        ft.Icon(ft.Icons.CAMERA_ENHANCE_ROUNDED, color=C.GOLD, size=24),
                                        ft.Text(
                                            "Aesthetic Lens (IG Readiness)",
                                            size=Type.TITLE,
                                            weight=ft.FontWeight.BOLD,
                                            color=C.TEXT,
                                        ),
                                    ],
                                    spacing=Space.SM,
                                ),
                                ft.IconButton(ft.Icons.CLOSE, on_click=lambda _: common.close(bs)),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                        ft.Divider(height=1, color=C.a(C.OUTLINE, 0.4)),
                        # Score Badge
                        ft.Row(
                            [
                                ft.Container(
                                    ft.Image(
                                        src=item.path,
                                        width=90,
                                        height=90,
                                        fit=ft.BoxFit.COVER,
                                        border_radius=Radius.MD,
                                    ),
                                    border_radius=Radius.MD,
                                    border=ft.Border.all(1.5, score_color),
                                ),
                                ft.Column(
                                    [
                                        ft.Text(
                                            f"{report.score} / 100",
                                            size=Type.HERO,
                                            weight=ft.FontWeight.W_900,
                                            color=score_color,
                                        ),
                                        ft.Text(
                                            report.rating_label,
                                            size=Type.BODY,
                                            weight=ft.FontWeight.BOLD,
                                            color=C.TEXT,
                                        ),
                                        ft.Text(
                                            f"{report.aspect_ratio_str} • {report.resolution_str}",
                                            size=Type.CAPTION,
                                            color=C.TEXT_DIM,
                                        ),
                                    ],
                                    spacing=2,
                                    expand=True,
                                ),
                            ],
                            spacing=Space.MD,
                        ),
                        # Badges
                        ft.Row(badges_chips, spacing=Space.XS, wrap=True) if badges_chips else ft.Container(),
                        # Breakdown meters
                        common.card(
                            ft.Column(
                                [
                                    self._metric_bar("Sharpness & Focus", report.sharpness_score, "#06D6A0"),
                                    self._metric_bar("Lighting & Exposure", report.lighting_score, "#FFD166"),
                                    self._metric_bar("Color Vibrancy", report.vibrancy_score, "#FF6B6B"),
                                    self._metric_bar("IG Framing (4:5 / 1:1)", report.framing_score, "#C77DFF"),
                                ],
                                spacing=Space.SM,
                            ),
                            padding=Space.SM,
                        ),
                        # Recommendations
                        ft.Text("Optimization Tips:", size=Type.CAPTION, weight=ft.FontWeight.BOLD, color=C.TEXT_DIM),
                        *tips_rows,
                    ],
                    spacing=Space.SM,
                    tight=True,
                ),
                padding=Space.LG,
                bgcolor=C.SURFACE,
                border_radius=ft.BorderRadius(top_left=Radius.LG, top_right=Radius.LG, bottom_left=0, bottom_right=0),
            )
        )
        self.app.page.show_dialog(bs)

    def _metric_bar(self, label: str, value: int, color: str) -> ft.Control:
        return ft.Column(
            [
                ft.Row(
                    [
                        ft.Text(label, size=Type.CAPTION - 1, color=C.TEXT),
                        ft.Text(f"{value}%", size=Type.CAPTION - 1, weight=ft.FontWeight.BOLD, color=color),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.ProgressBar(
                    value=value / 100.0,
                    color=color,
                    bgcolor=C.a(C.SURFACE_HI, 0.5),
                    border_radius=Radius.PILL,
                ),
            ],
            spacing=2,
        )

    def _open_folder_picker(self) -> None:
        def on_result(e: ft.FilePickerResultEvent) -> None:
            if e.path:
                self.current_folder = e.path
                self._rescan()
                self.render()

        self.file_picker.on_result = on_result
        self.file_picker.get_directory_path(dialog_title="Select Photo Folder")
