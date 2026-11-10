"""Daily Journal: A warm, lined notebook-style journal for LUMA.

Features:
- Notebook page aesthetic with distraction-free writing.
- Mood stamp & timestamp.
- Quick inspiration prompt chips (+ Grateful for, + Today's win, + Lesson).
- Full scrollability when virtual keyboard is open.
- Awards +20 Monk Path XP per reflection.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

import flet as ft

from lol.core.models import JournalEntry
from lol.ui import components as ui
from lol.ui import sfx
from lol.ui.screens import common
from lol.ui.theme import C, Radius, Space, Type

if TYPE_CHECKING:
    from lol.ui.app import App

MOODS = (
    ("great", "😄", "Great", "#06D6A0"),
    ("good", "😊", "Good", "#FFD166"),
    ("neutral", "😐", "Okay", "#7FB2FF"),
    ("tired", "🥱", "Tired", "#A78BFA"),
    ("stressed", "⚡", "Stressed", "#FF6B6B"),
)


def open_journal_sheet(app: App, on_done: Any = None) -> None:
    """Open a warm, scrollable notebook-style page to write journal thoughts."""
    selected_mood = ["good"]
    now_dt = datetime.now()
    date_display = now_dt.strftime("%A, %b %d • %I:%M %p")

    title_field = ft.TextField(
        hint_text="Title or Theme (optional)...",
        hint_style=ft.TextStyle(color=C.a(C.TEXT_DIM, 0.6), size=Type.TITLE),
        text_style=ft.TextStyle(color=C.TEXT, size=Type.TITLE, weight=ft.FontWeight.BOLD),
        border=ft.InputBorder.NONE,
        content_padding=ft.Padding.symmetric(horizontal=4, vertical=6),
    )

    body_field = ft.TextField(
        hint_text="Write freely... your thoughts, feelings, gratitude, or reflections on today...",
        hint_style=ft.TextStyle(color=C.a(C.TEXT_DIM, 0.5), size=Type.BODY),
        text_style=ft.TextStyle(color=C.TEXT, size=Type.BODY, height=1.5),
        multiline=True,
        min_lines=6,
        max_lines=14,
        border=ft.InputBorder.NONE,
        content_padding=ft.Padding.symmetric(horizontal=4, vertical=8),
        autofocus=True,
    )

    word_count_text = ft.Text("0 words", size=Type.CAPTION - 2, color=C.TEXT_DIM)

    def on_body_change(e: Any) -> None:
        text = e.control.value or ""
        words = len(text.strip().split()) if text.strip() else 0
        word_count_text.value = f"{words} words"
        ui.refresh(word_count_text)

    body_field.on_change = on_body_change

    # Quick prompt inserts
    def insert_prompt(prompt_text: str):
        def do_insert(_):
            current = body_field.value or ""
            if current and not current.endswith("\n"):
                current += "\n\n"
            body_field.value = f"{current}{prompt_text} "
            ui.refresh(body_field)
            sfx.play("tap")
        return do_insert

    prompt_chips = [
        ft.Container(
            ft.Text("+ Grateful for...", size=Type.CAPTION - 2, color=C.GOLD),
            padding=ft.Padding.symmetric(horizontal=8, vertical=4),
            border_radius=Radius.PILL,
            bgcolor=C.a(C.GOLD, 0.12),
            border=ft.Border.all(1, C.a(C.GOLD, 0.3)),
            on_click=insert_prompt("✨ Grateful for:"),
        ),
        ft.Container(
            ft.Text("+ Today's Win:", size=Type.CAPTION - 2, color="#06D6A0"),
            padding=ft.Padding.symmetric(horizontal=8, vertical=4),
            border_radius=Radius.PILL,
            bgcolor=C.a("#06D6A0", 0.12),
            border=ft.Border.all(1, C.a("#06D6A0", 0.3)),
            on_click=insert_prompt("🏆 Today's Win:"),
        ),
        ft.Container(
            ft.Text("+ Lesson learned:", size=Type.CAPTION - 2, color="#C77DFF"),
            padding=ft.Padding.symmetric(horizontal=8, vertical=4),
            border_radius=Radius.PILL,
            bgcolor=C.a("#C77DFF", 0.12),
            border=ft.Border.all(1, C.a("#C77DFF", 0.3)),
            on_click=insert_prompt("💡 Lesson learned:"),
        ),
    ]

    mood_chips: list[ft.Container] = []

    def update_chips() -> None:
        for c in mood_chips:
            m_key = c.data
            active = m_key == selected_mood[0]
            color = next((col for k, _, _, col in MOODS if k == m_key), C.PRIMARY)
            c.bgcolor = C.a(color, 0.25) if active else C.a(C.SURFACE_HI, 0.4)
            c.border = ft.Border.all(1.5 if active else 1, color if active else C.a(C.OUTLINE, 0.3))
            ui.refresh(c)

    for key, emoji, label, color in MOODS:
        def make_pick(k: str):
            def on_pick(_):
                selected_mood[0] = k
                sfx.play("tap")
                update_chips()
            return on_pick

        chip = ft.Container(
            ft.Row(
                [
                    ft.Text(emoji, size=18),
                    ft.Text(label, size=Type.CAPTION, weight=ft.FontWeight.BOLD, color=C.TEXT),
                ],
                spacing=4,
                tight=True,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            data=key,
            padding=ft.Padding.symmetric(horizontal=10, vertical=6),
            border_radius=Radius.PILL,
            bgcolor=C.a(color, 0.25) if key == "good" else C.a(C.SURFACE_HI, 0.4),
            border=ft.Border.all(1.5 if key == "good" else 1, color if key == "good" else C.a(C.OUTLINE, 0.3)),
            on_click=make_pick(key),
        )
        mood_chips.append(chip)

    def save_reflection(_: Any = None) -> None:
        title = (title_field.value or "").strip()
        body_text = (body_field.value or "").strip()
        if not body_text and not title:
            app.toast("Write a few thoughts before saving!", ft.Icons.EDIT)
            return

        app.game.add_journal(
            mood=selected_mood[0],
            gratitude="",
            highlight=title,
            notes=body_text,
            today=app.today(),
        )
        app.save()
        sfx.play("quest_done")
        app.toast("📖 Notebook entry saved! +20 Monk XP", ft.Icons.AUTO_AWESOME)
        common.close(bs)
        if callable(on_done):
            on_done()

    # The Notebook Page container
    notebook_page = ft.Container(
        ft.Column(
            [
                # Date and Header bar
                ft.Row(
                    [
                        ft.Row(
                            [
                                ft.Icon(ft.Icons.AUTO_STORIES, color="#C77DFF", size=20),
                                ft.Text(
                                    date_display,
                                    size=Type.CAPTION,
                                    weight=ft.FontWeight.W_600,
                                    color="#C77DFF",
                                ),
                            ],
                            spacing=Space.SM,
                        ),
                        ft.IconButton(
                            ft.Icons.CLOSE,
                            icon_size=20,
                            icon_color=C.TEXT_DIM,
                            on_click=lambda _: common.close(bs),
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                # Mood selector row
                ft.Row(mood_chips, spacing=Space.XS, scroll=ft.ScrollMode.AUTO),
                ft.Divider(height=1, color=C.a(C.OUTLINE, 0.4)),
                # Title line
                title_field,
                ft.Divider(height=1, color=C.a(C.OUTLINE, 0.25)),
                # Main journal writing area
                body_field,
                # Prompt chips and word count
                ft.Row(
                    [
                        ft.Row(prompt_chips, spacing=Space.XS, scroll=ft.ScrollMode.AUTO, expand=True),
                        word_count_text,
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Divider(height=1, color=C.a(C.OUTLINE, 0.3)),
                # Save Button
                ft.Row(
                    [
                        ft.FilledButton(
                            "Save Notebook Entry (+20 XP)",
                            icon=ft.Icons.BOOKMARK_ADDED,
                            style=ft.ButtonStyle(
                                bgcolor="#C77DFF",
                                color="#0D1F2D",
                                shape=ft.RoundedRectangleBorder(radius=Radius.PILL),
                            ),
                            on_click=save_reflection,
                            expand=True,
                        ),
                    ],
                ),
            ],
            spacing=Space.SM,
            scroll=ft.ScrollMode.AUTO,  # Allows smooth scrolling when keyboard appears
        ),
        padding=Space.LG,
        bgcolor=C.SURFACE,
        border_radius=ft.BorderRadius(top_left=Radius.LG, top_right=Radius.LG, bottom_left=0, bottom_right=0),
    )

    bs = ft.BottomSheet(
        notebook_page,
        bgcolor=ft.Colors.TRANSPARENT,
        scrollable=True,  # Ensures Android keyboard moves sheet up and lets user scroll freely
    )
    app.page.show_dialog(bs)


class JournalScreen:
    title = "Daily Journal"

    def __init__(self, app: App) -> None:
        self.app = app
        self.list = common.screen_list()
        self.view = ft.Container(self.list, expand=True, key="journal_screen")
        self.fab = ft.FloatingActionButton(
            icon=ft.Icons.EDIT_NOTE,
            bgcolor="#C77DFF",
            foreground_color="#0D1F2D",
            tooltip="New Journal Page",
            on_click=lambda _: open_journal_sheet(self.app, self.render),
        )

    def render(self) -> None:
        self.list.controls.clear()
        g = self.app.game
        entries = g.journal_entries()

        # Notebook Binder Header Card
        header = common.card(
            ft.Row(
                [
                    ft.Container(
                        ft.Icon(ft.Icons.AUTO_STORIES_ROUNDED, color="#C77DFF", size=30),
                        width=52,
                        height=52,
                        border_radius=Radius.MD,
                        bgcolor=C.a("#C77DFF", 0.18),
                        alignment=ft.Alignment(0, 0),
                    ),
                    ft.Column(
                        [
                            ft.Text(
                                "MY NOTEBOOK JOURNAL",
                                size=Type.CAPTION,
                                weight=ft.FontWeight.W_800,
                                color="#C77DFF",
                            ),
                            ft.Text(
                                f"{len(entries)} Written Pages",
                                size=Type.TITLE,
                                weight=ft.FontWeight.BOLD,
                                color=C.TEXT,
                            ),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    ft.FilledButton(
                        "Write",
                        icon=ft.Icons.EDIT,
                        style=ft.ButtonStyle(
                            bgcolor="#C77DFF",
                            color="#0D1F2D",
                            shape=ft.RoundedRectangleBorder(radius=Radius.PILL),
                        ),
                        on_click=lambda _: open_journal_sheet(self.app, self.render),
                    ),
                ],
                spacing=Space.MD,
            ),
            tint="#C77DFF",
        )
        self.list.controls.append(header)

        if not entries:
            self.list.controls.append(
                common.card(
                    ui.EmptyState(
                        "Your notebook is waiting",
                        "Open a blank page to write your thoughts, celebrate your wins, and capture your journey.",
                        icon=ft.Icons.AUTO_STORIES,
                        action_text="Open Blank Page",
                        on_action=lambda _: open_journal_sheet(self.app, self.render),
                    ),
                    padding=0,
                )
            )
        else:
            for entry in entries:
                self.list.controls.append(self._notebook_page_card(entry))

        ui.refresh(self.list)

    def _notebook_page_card(self, entry: JournalEntry) -> ft.Control:
        mood_meta = next((m for m in MOODS if m[0] == entry.mood), MOODS[1])
        emoji, label, color = mood_meta[1], mood_meta[2], mood_meta[3]

        entry_title = entry.highlight or "Journal Entry"

        content_rows: list[ft.Control] = [
            ft.Row(
                [
                    ft.Row(
                        [
                            ft.Container(
                                ft.Text(emoji, size=18),
                                width=32,
                                height=32,
                                border_radius=Radius.SM,
                                bgcolor=C.a(color, 0.2),
                                alignment=ft.Alignment(0, 0),
                            ),
                            ft.Column(
                                [
                                    ft.Text(
                                        entry_title,
                                        size=Type.BODY,
                                        weight=ft.FontWeight.BOLD,
                                        color=C.TEXT,
                                        max_lines=1,
                                        overflow=ft.TextOverflow.ELLIPSIS,
                                    ),
                                    ft.Text(
                                        f"{entry.day} • {entry.time or ''} • {label}",
                                        size=Type.CAPTION - 1,
                                        color=C.TEXT_DIM,
                                    ),
                                ],
                                spacing=0,
                            ),
                        ],
                        spacing=Space.SM,
                        expand=True,
                    ),
                    ft.IconButton(
                        ft.Icons.DELETE_OUTLINE,
                        icon_size=18,
                        icon_color=C.TEXT_DIM,
                        tooltip="Tear page out",
                        on_click=lambda _, eid=entry.id: self._confirm_delete(eid),
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            ft.Divider(height=1, color=C.a(C.OUTLINE, 0.25)),
        ]

        if entry.notes:
            content_rows.append(
                ft.Text(
                    entry.notes,
                    size=Type.BODY - 1,
                    color=C.a(C.TEXT, 0.9),
                    style=ft.TextStyle(height=1.4),
                )
            )
        if entry.gratitude:
            content_rows.append(
                ft.Row(
                    [
                        ft.Icon(ft.Icons.FAVORITE_ROUNDED, size=14, color="#FF8FA3"),
                        ft.Text(f"Grateful for: {entry.gratitude}", size=Type.CAPTION, color=C.TEXT_DIM, expand=True),
                    ],
                    spacing=Space.SM,
                )
            )

        return common.card(
            ft.Column(content_rows, spacing=Space.SM),
            tint=color,
        )

    def _confirm_delete(self, entry_id: str) -> None:
        async def do_delete():
            ok = await common.confirm(
                self.app.page,
                "Tear out this notebook page?",
                "This journal entry will be permanently deleted.",
                "Delete",
                danger=True,
            )
            if ok:
                self.app.game.delete_journal(entry_id)
                self.app.save()
                self.render()

        self.app.page.run_task(do_delete)
