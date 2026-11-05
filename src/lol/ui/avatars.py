"""Player avatars: original icon + color sigils (no characters, no IP).

The save only stores `profile.avatar_id` ("a1".."a10"); everything about how an avatar looks
lives here. Unknown ids fall back to the default, so an old or hand-edited save never breaks.
"""

from __future__ import annotations

from dataclasses import dataclass

import flet as ft

from lol.ui.theme import C, Motion


@dataclass(frozen=True)
class Avatar:
    id: str
    name: str
    icon: ft.IconData
    color: str  # concrete hex: an avatar keeps its color in every theme


AVATARS: dict[str, Avatar] = {a.id: a for a in (
    Avatar("a1", "Spark", ft.Icons.AUTO_AWESOME, "#4FE3F0"),
    Avatar("a2", "Ember", ft.Icons.LOCAL_FIRE_DEPARTMENT, "#FF8A4C"),
    Avatar("a3", "Sprout", ft.Icons.ECO, "#5EEAB0"),
    Avatar("a4", "Moon", ft.Icons.NIGHTLIGHT_ROUND, "#A78BFA"),
    Avatar("a5", "Bolt", ft.Icons.BOLT, "#FFD36E"),
    Avatar("a6", "Tide", ft.Icons.WATER_DROP, "#6BB8FF"),
    Avatar("a7", "Shield", ft.Icons.SHIELD, "#FF6F91"),
    Avatar("a8", "Compass", ft.Icons.EXPLORE, "#FFA071"),
    Avatar("a9", "Peak", ft.Icons.TERRAIN, "#8FD3A8"),
    Avatar("a10", "Gem", ft.Icons.DIAMOND, "#E08CFF"),
)}
DEFAULT_AVATAR = "a1"


def get(avatar_id: str | None) -> Avatar:
    return AVATARS.get(avatar_id or "", AVATARS[DEFAULT_AVATAR])


def bubble(avatar_id: str | None, size: int = 40, *, ring: bool = True) -> ft.Container:
    """Round avatar: tinted disc, colored ring and icon. Animates when its look changes."""
    a = get(avatar_id)
    return ft.Container(
        ft.Icon(a.icon, color=a.color, size=size * 0.52),
        width=size, height=size, border_radius=size / 2, alignment=ft.Alignment.CENTER,
        bgcolor=C.a(a.color, 0.18),
        border=ft.Border.all(max(1.5, size / 28), C.a(a.color, 0.75)) if ring else None,
        shadow=ft.BoxShadow(blur_radius=size / 3, color=C.a(a.color, 0.30)),
        animate=Motion.anim(Motion.FADE_MS), scale=1,
        animate_scale=Motion.anim(Motion.POP_MS * 2, Motion.BACK),
    )


def restyle_bubble(ctrl: ft.Container, avatar_id: str | None) -> None:
    """Point an existing bubble() at another avatar in place (keeps its animations)."""
    a = get(avatar_id)
    size = ctrl.width or 40
    icon: ft.Icon = ctrl.content  # type: ignore[assignment]
    icon.icon, icon.color = a.icon, a.color
    ctrl.bgcolor = C.a(a.color, 0.18)
    if ctrl.border is not None:
        ctrl.border = ft.Border.all(max(1.5, size / 28), C.a(a.color, 0.75))
    ctrl.shadow = ft.BoxShadow(blur_radius=size / 3, color=C.a(a.color, 0.30))


class AvatarPicker(ft.Container):
    """Grid of avatars; the chosen one gets a ring, a pop and its name. on_change(avatar_id)."""

    def __init__(self, value: str | None, *, size: int = 52, on_change=None) -> None:
        self.value = get(value).id
        self.on_change = on_change
        self._cells: dict[str, ft.Container] = {}
        for a in AVATARS.values():
            self._cells[a.id] = ft.Container(
                bubble(a.id, size, ring=False), padding=3, border_radius=size,
                on_click=lambda e, aid=a.id: self._pick(aid), tooltip=a.name,
                animate=Motion.anim(Motion.FADE_MS), scale=1,
                animate_scale=Motion.anim(Motion.POP_MS, Motion.BACK),
            )
        super().__init__(ft.Row(list(self._cells.values()), wrap=True, spacing=6,
                                run_spacing=6, alignment=ft.MainAxisAlignment.CENTER))
        self._paint()

    def _paint(self) -> None:
        for aid, cell in self._cells.items():
            on = aid == self.value
            col = get(aid).color
            cell.border = ft.Border.all(2.5, col if on else "#00000000")
            cell.bgcolor = C.a(col, 0.10) if on else None
            cell.opacity = 1 if on else 0.8

    def _pick(self, avatar_id: str) -> None:
        from lol.ui.components import buzz, pop  # local import: components imports theme only

        self.value = avatar_id
        self._paint()
        if self.page:
            self.page.run_task(buzz, "select")
            self.page.run_task(pop, self._cells[avatar_id], 1.12)
        self.update()
        if self.on_change:
            self.on_change(avatar_id)
