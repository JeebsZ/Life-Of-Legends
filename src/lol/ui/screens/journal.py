"""Daily Journal & Mindfulness Reflection for LUMA.

Tracks mood, gratitude, and daily highlights to reward Monk Path XP.
"""

from __future__ import annotations

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
    """Open a quick reflection sheet to log mood, gratitude, and thoughts."""
    selected_mood = ["good"]

    gratitude_field = ft.TextField(
        label="One thing I am grateful for...",
        hint_text="e.g. Morning coffee, a kind message, fresh air",
        multiline=False,
        border_color=C.a(C.OUTLINE, 0.5),
        border_radius=Radius.MD,
    )
    highlight_field = ft.TextField(
        label="Today's win or highlight...",
        hint_text="e.g. Finished my workout, made progress on my goal",
        multiline=False,
        border_color=C.a(C.OUTLINE, 0.5),
        border_radius=Radius.MD,
    )
    notes_field = ft.TextField(
        label="Thoughts & Reflection (optional)",
        hint_text="How was your day? Any insights or lessons?",
        multiline=True,
        min_lines=2,
        max_lines=4,
        border_color=C.a(C.OUTLINE, 0.5),
        border_radius=Radius.MD,
    )

    mood_chips: list[ft.Container] = []

    def update_chips() -> None:
        for c in mood_chips:
            m_key = c.data
            active = m_key == selected_mood[0]
            color = next((col for k, _, _, col in MOODS if k == m_key), C.PRIMARY)
            c.bgcolor = C.a(color, 0.25) if active else C.a(C.SURFACE_HI, 0.5)
            c.border = ft.Border.all(1.5 if active else 1, color if active else C.a(C.OUTLINE, 0.4))
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
            padding=ft.Padding.symmetric(horizontal=10, vertical=8),
            border_radius=Radius.PILL,
            bgcolor=C.a(color, 0.25) if key == "good" else C.a(C.SURFACE_HI, 0.5),
            border=ft.Border.all(1.5 if key == "good" else 1, color if key == "good" else C.a(C.OUTLINE, 0.4)),
            on_click=make_pick(key),
        )
        mood_chips.append(chip)

    def save_reflection(_: Any = None) -> None:
        app.game.add_journal(
            mood=selected_mood[0],
            gratitude=gratitude_field.value or "",
            highlight=highlight_field.value or "",
            notes=notes_field.value or "",
            today=app.today(),
        )
        app.save()
        sfx.play("quest_done")
        app.toast("🧘 Mindful reflection recorded! +20 Monk XP", ft.Icons.AUTO_AWESOME)
        common.close(bs)
        if callable(on_done):
            on_done()

    bs = ft.BottomSheet(
        ft.Container(
            ft.Column(
                [
                    ft.Row(
                        [
                            ft.Row(
                                [
                                    ft.Icon(ft.Icons.AUTO_STORIES, color="#C77DFF", size=22),
                                    ft.Text(
                                        "Daily Reflection",
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
                    ft.Text("How are you feeling today?", size=Type.CAPTION, color=C.TEXT_DIM),
                    ft.Row(mood_chips, spacing=Space.XS, wrap=True),
                    gratitude_field,
                    highlight_field,
                    notes_field,
                    ft.Row(
                        [
                            ft.FilledButton(
                                "Save Reflection (+20 XP)",
                                icon=ft.Icons.CHECK,
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
                spacing=Space.MD,
                tight=True,
            ),
            padding=Space.LG,
            bgcolor=C.SURFACE,
            border_radius=ft.BorderRadius(top_left=Radius.LG, top_right=Radius.LG, bottom_left=0, bottom_right=0),
        )
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
            tooltip="New Reflection",
            on_click=lambda _: open_journal_sheet(self.app, self.render),
        )

    def render(self) -> None:
        self.list.controls.clear()
        g = self.app.game
        entries = g.journal_entries()

        # Header card
        header = common.card(
            ft.Row(
                [
                    ft.Icon(ft.Icons.AUTO_STORIES_ROUNDED, color="#C77DFF", size=28),
                    ft.Column(
                        [
                            ft.Text(
                                "DAILY JOURNAL",
                                size=Type.CAPTION,
                                weight=ft.FontWeight.W_800,
                                color="#C77DFF",
                            ),
                            ft.Text(
                                f"{len(entries)} Mindful Entries",
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
                        icon=ft.Icons.ADD,
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
                        "No journal entries yet",
                        "Capture your thoughts, celebrate small wins, and reflect on your days.",
                        icon=ft.Icons.AUTO_STORIES,
                        action_text="Write First Entry",
                        on_action=lambda _: open_journal_sheet(self.app, self.render),
                    ),
                    padding=0,
                )
            )
        else:
            for entry in entries:
                self.list.controls.append(self._entry_card(entry))

        ui.refresh(self.list)

    def _entry_card(self, entry: JournalEntry) -> ft.Control:
        mood_meta = next((m for m in MOODS if m[0] == entry.mood), MOODS[1])
        emoji, label, color = mood_meta[1], mood_meta[2], mood_meta[3]

        content_rows: list[ft.Control] = [
            ft.Row(
                [
                    ft.Container(
                        ft.Text(emoji, size=20),
                        width=36,
                        height=36,
                        border_radius=Radius.SM,
                        bgcolor=C.a(color, 0.2),
                        alignment=ft.Alignment(0, 0),
                    ),
                    ft.Column(
                        [
                            ft.Text(
                                f"{entry.day} • {entry.time or ''}",
                                size=Type.CAPTION,
                                color=C.TEXT_DIM,
                            ),
                            ft.Text(
                                f"Felt {label}",
                                size=Type.BODY,
                                weight=ft.FontWeight.BOLD,
                                color=C.TEXT,
                            ),
                        ],
                        spacing=0,
                        expand=True,
                    ),
                    ft.IconButton(
                        ft.Icons.DELETE_OUTLINE,
                        icon_size=18,
                        icon_color=C.TEXT_DIM,
                        tooltip="Delete entry",
                        on_click=lambda _, eid=entry.id: self._confirm_delete(eid),
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
        ]

        if entry.gratitude:
            content_rows.append(
                ft.Row(
                    [
                        ft.Icon(ft.Icons.FAVORITE_ROUNDED, size=14, color="#FF8FA3"),
                        ft.Text(entry.gratitude, size=Type.BODY - 1, color=C.TEXT, expand=True),
                    ],
                    spacing=Space.SM,
                )
            )
        if entry.highlight:
            content_rows.append(
                ft.Row(
                    [
                        ft.Icon(ft.Icons.EMOJI_EVENTS_ROUNDED, size=14, color=C.GOLD),
                        ft.Text(entry.highlight, size=Type.BODY - 1, color=C.TEXT, expand=True),
                    ],
                    spacing=Space.SM,
                )
            )
        if entry.notes:
            content_rows.append(
                ft.Text(entry.notes, size=Type.CAPTION, color=C.a(C.TEXT, 0.85))
            )

        return common.card(
            ft.Column(content_rows, spacing=Space.SM),
            tint=color,
        )

    def _confirm_delete(self, entry_id: str) -> None:
        async def do_delete():
            ok = await common.confirm(
                self.app.page,
                "Delete journal entry?",
                "This cannot be undone.",
                "Delete",
                danger=True,
            )
            if ok:
                self.app.game.delete_journal(entry_id)
                self.app.save()
                self.render()

        self.app.page.run_task(do_delete)

