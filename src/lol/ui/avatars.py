"""Player avatars: original icon + color sigils and layered chibi character customization.

The save stores `profile.avatar_id` ("a1".."a10") for sigil color/ring tinting and
`profile.avatar_customization` (`AvatarCustomization`) for the modular 256x256 chibi layers.
Unknown ids fall back to defaults, so an old or hand-edited save never breaks.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import flet as ft

from lol.core import avatar_catalog
from lol.core import cosmetics as cos
from lol.core.models import AvatarCustomization
from lol.ui import sfx
from lol.ui import theme as th
from lol.ui.theme import C, Motion, Radius, Size, Space, Type

if TYPE_CHECKING:
    from lol.ui.app import App


@dataclass(frozen=True)
class Avatar:
    id: str
    name: str
    icon: ft.IconData
    color: str  # concrete hex: an avatar keeps its color in every theme


AVATARS: dict[str, Avatar] = {
    a.id: a
    for a in (
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
    )
}
DEFAULT_AVATAR = "a1"


def get(avatar_id: str | None) -> Avatar:
    return AVATARS.get(avatar_id or "", AVATARS[DEFAULT_AVATAR])


def _mounted_page(ctrl: ft.Control) -> ft.Page | None:
    try:
        return ctrl.page
    except Exception:  # noqa: BLE001
        return None


class AvatarView(ft.Container):
    """Layered 256x256 pixel-art chibi character renderer (with optional companion badge)."""

    def __init__(
        self,
        custom: AvatarCustomization | None = None,
        size: int = 64,
        *,
        pet_id: str | None = None,
    ) -> None:
        self.size = size
        self.custom = avatar_catalog.sanitize(custom)
        self.pet_id = pet_id
        self._stack = ft.Stack([], width=size, height=size)
        self.set_custom(self.custom, pet_id=pet_id)
        super().__init__(
            self._stack,
            width=size,
            height=size,
            alignment=ft.Alignment.CENTER,
            scale=1,
            animate_scale=Motion.anim(Motion.POP_MS, Motion.BACK),
        )

    def set_custom(
        self,
        custom: AvatarCustomization | None,
        *,
        pet_id: str | None = None,
    ) -> None:
        self.custom = avatar_catalog.sanitize(custom)
        if pet_id is not None:
            self.pet_id = pet_id
        layers: list[ft.Control] = [
            ft.Image(
                src=p,
                width=self.size,
                height=self.size,
                fit=ft.BoxFit.CONTAIN,
                filter_quality=ft.FilterQuality.NONE,
            )
            for p in avatar_catalog.layer_paths(self.custom)
        ]
        if self.pet_id and self.pet_id != "pet_none":
            pet = cos.get_cosmetic(self.pet_id, "pet")
            if pet.badge_text:
                badge_sz = max(14, round(self.size * 0.28))
                layers.append(
                    ft.Container(
                        ft.Text(
                            pet.badge_text,
                            size=max(10, round(self.size * 0.20)),
                            text_align=ft.TextAlign.CENTER,
                        ),
                        width=badge_sz,
                        height=badge_sz,
                        border_radius=badge_sz / 2,
                        bgcolor=C.a(pet.color, 0.30),
                        border=ft.Border.all(1.0, C.a(pet.color, 0.85)),
                        alignment=ft.Alignment.CENTER,
                        right=max(1, round(self.size * 0.04)),
                        bottom=max(1, round(self.size * 0.04)),
                    )
                )
        self._stack.controls = layers


def _frame_styles(
    size: int,
    ring: bool,
    frame_id: str | None,
) -> tuple[str, float, ft.Border | None, list[ft.BoxShadow] | ft.BoxShadow]:
    """Compute (bgcolor, border_w, border, shadow) for an avatar bubble given frame_id."""
    frame = cos.get_cosmetic(frame_id, "frame") if frame_id else cos.get_cosmetic("frame_default", "frame")
    if frame.id == "frame_default":
        col = th.current().primary
        border_w = round(max(1.5, size / 24), 1) if ring else 0.0
        border = ft.Border.all(border_w, C.a(col, 0.80)) if ring else None
        shadow: list[ft.BoxShadow] | ft.BoxShadow = ft.BoxShadow(blur_radius=size / 3, color=C.a(col, 0.30))
        return C.a(col, 0.18), border_w, border, shadow

    col = frame.color
    sec = frame.secondary_color or col
    border_w = round(max(2.2, size / 18), 1) if ring else 0.0
    border = ft.Border.all(border_w, C.a(col, 0.92)) if ring else None
    shadow = [
        ft.BoxShadow(blur_radius=size / 2.4, spread_radius=1.0, color=C.a(col, 0.50)),
        ft.BoxShadow(blur_radius=size / 1.6, spread_radius=0.5, color=C.a(sec, 0.32)),
    ]
    return C.a(col, 0.22), border_w, border, shadow


def bubble(
    avatar_id: str | None,
    size: int = 40,
    *,
    ring: bool = True,
    custom: AvatarCustomization | None = None,
    frame_id: str | None = None,
    pet_id: str | None = None,
) -> ft.Container:
    """Round avatar: theme/frame-tinted disc, ring and circular-clipped chibi AvatarView."""
    _ = get(avatar_id)
    bg_col, border_w, border, shadow = _frame_styles(size, ring, frame_id)
    inner_size = max(16, round(size - border_w * 2))
    inner_clip = ft.Container(
        AvatarView(custom, size=inner_size, pet_id=pet_id),
        width=inner_size,
        height=inner_size,
        border_radius=inner_size / 2,
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
        alignment=ft.Alignment.BOTTOM_CENTER,
    )
    return ft.Container(
        inner_clip,
        width=size,
        height=size,
        border_radius=size / 2,
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        alignment=ft.Alignment.CENTER,
        bgcolor=bg_col,
        border=border,
        shadow=shadow,
        animate=Motion.anim(Motion.FADE_MS),
        scale=1,
        animate_scale=Motion.anim(Motion.POP_MS * 2, Motion.BACK),
    )


def restyle_bubble(
    ctrl: ft.Container,
    avatar_id: str | None,
    *,
    custom: AvatarCustomization | None = None,
    frame_id: str | None = None,
    pet_id: str | None = None,
) -> None:
    """Point an existing bubble() at another avatar/customization/frame/pet and refresh colors in place."""
    a = get(avatar_id)
    size = ctrl.width or 40
    ring = ctrl.border is not None
    bg_col, _border_w, border, shadow = _frame_styles(int(size), ring, frame_id)
    if isinstance(ctrl.content, AvatarView):
        ctrl.content.set_custom(
            custom if custom is not None else ctrl.content.custom,
            pet_id=pet_id,
        )
    elif isinstance(ctrl.content, ft.Container) and isinstance(ctrl.content.content, AvatarView):
        av_view = ctrl.content.content
        av_view.set_custom(
            custom if custom is not None else av_view.custom,
            pet_id=pet_id,
        )
    elif isinstance(ctrl.content, ft.Icon):
        ctrl.content.icon, ctrl.content.color = a.icon, th.current().primary
    ctrl.bgcolor = bg_col
    if ring:
        ctrl.border = border
    ctrl.shadow = shadow


class AvatarPicker(ft.Container):
    """Grid of avatars; the chosen one gets a ring, a pop and its name. on_change(avatar_id)."""

    def __init__(self, value: str | None, *, size: int = 52, on_change=None) -> None:
        self.value = get(value).id
        self.on_change = on_change
        self._cells: dict[str, ft.Container] = {}
        for a in AVATARS.values():
            self._cells[a.id] = ft.Container(
                bubble(a.id, size, ring=False),
                padding=3,
                border_radius=size,
                on_click=lambda e, aid=a.id: self._pick(aid),
                tooltip=a.name,
                animate=Motion.anim(Motion.FADE_MS),
                scale=1,
                animate_scale=Motion.anim(Motion.POP_MS, Motion.BACK),
            )
        super().__init__(
            ft.Row(
                list(self._cells.values()),
                wrap=True,
                spacing=6,
                run_spacing=6,
                alignment=ft.MainAxisAlignment.CENTER,
            )
        )
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
        pg = _mounted_page(self)
        if pg:
            pg.run_task(buzz, "select")
            pg.run_task(pop, self._cells[avatar_id], 1.12)
            self.update()
        if self.on_change:
            self.on_change(avatar_id)


class CharacterCustomizer(ft.Container):
    """Interactive layered character customizer with live preview, dice randomizer,
    scrollable category tabs, and multi-select skin details (up to 3 stacked makeups)."""

    def __init__(
        self,
        custom: AvatarCustomization | None = None,
        hero_name: str = "Legend",
        on_change: Callable[[AvatarCustomization], None] | None = None,
        on_limit_toast: Callable[[str], None] | None = None,
    ) -> None:
        self.custom = avatar_catalog.sanitize(custom)
        self.hero_name = hero_name or "Legend"
        self.on_change = on_change
        self.on_limit_toast = on_limit_toast
        self.active_cat = avatar_catalog.CATEGORIES[0][0]

        self.name_label = ft.Text(
            self.hero_name,
            size=Type.TITLE + 1,
            weight=ft.FontWeight.W_900,
            color="#F8FAFC",
            text_align=ft.TextAlign.CENTER,
        )
        self.preview_avatar = AvatarView(self.custom, size=180)
        self.random_btn = ft.Container(
            ft.Icon(ft.Icons.CASINO, size=22, color="#F8FAFC"),
            width=44,
            height=44,
            border_radius=22,
            bgcolor="#132032",
            border=ft.Border.all(2, "#FFFFFF"),
            shadow=ft.BoxShadow(blur_radius=10, color=C.a("#000000", 0.45)),
            alignment=ft.Alignment.CENTER,
            right=12,
            bottom=12,
            on_click=self._on_randomize,
            tooltip="Randomize Avatar",
            scale=1,
            animate_scale=Motion.anim(Motion.POP_MS, Motion.BACK),
        )

        # Subtle floating pixel sparks in the preview stage
        sparks = [
            ft.Container(width=4, height=4, bgcolor="#5EEAB0", left=28, top=36, opacity=0.75),
            ft.Container(width=4, height=4, bgcolor="#4FE3F0", right=34, top=44, opacity=0.65),
            ft.Container(width=4, height=4, bgcolor="#5EEAB0", left=46, bottom=32, opacity=0.55),
            ft.Container(width=4, height=4, bgcolor="#4FE3F0", right=64, bottom=28, opacity=0.7),
        ]

        self.preview_stage = ft.Container(
            ft.Stack(
                [
                    *sparks,
                    ft.Column(
                        [
                            self.name_label,
                            ft.Container(
                                self.preview_avatar,
                                alignment=ft.Alignment.CENTER,
                            ),
                        ],
                        spacing=4,
                        tight=True,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                    self.random_btn,
                ],
                alignment=ft.Alignment.CENTER,
            ),
            height=228,
            bgcolor="#0B1320",
            border=ft.Border.all(1.5, "#1E293B"),
            border_radius=Radius.LG,
            padding=ft.Padding.symmetric(horizontal=Space.MD, vertical=Space.SM),
            alignment=ft.Alignment.CENTER,
        )

        self.tab_row = ft.Row(
            [],
            scroll=ft.ScrollMode.HIDDEN,
            spacing=Space.SM,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        self.item_grid = ft.Row(
            [],
            wrap=True,
            spacing=8,
            run_spacing=8,
            alignment=ft.MainAxisAlignment.CENTER,
        )

        self._rebuild_tabs()
        self._rebuild_grid()

        super().__init__(
            ft.Column(
                [
                    self.preview_stage,
                    self.tab_row,
                    ft.Container(
                        self.item_grid,
                        bgcolor="#09101B",
                        border=ft.Border.all(1, "#1E293B"),
                        border_radius=Radius.MD,
                        padding=Space.MD,
                        alignment=ft.Alignment.CENTER,
                    ),
                ],
                spacing=Space.MD,
                tight=True,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            ),
        )

    def _cat_label(self, cat_id: str, label: str) -> str:
        if cat_id == "skin" and self.custom.makeups:
            return f"{label} ({len(self.custom.makeups)}/{avatar_catalog.MAX_MAKEUPS})"
        return label

    def _rebuild_tabs(self) -> None:
        tabs: list[ft.Control] = []
        for cat_id, label, _items, _allow_none in avatar_catalog.CATEGORIES:
            active = cat_id == self.active_cat
            text = self._cat_label(cat_id, label)
            tabs.append(
                ft.Container(
                    ft.Text(
                        text,
                        size=Type.LABEL,
                        weight=ft.FontWeight.W_800 if active else ft.FontWeight.W_600,
                        color="#FFFFFF" if active else C.TEXT_DIM,
                    ),
                    padding=ft.Padding.symmetric(horizontal=14, vertical=8),
                    border_radius=Radius.PILL,
                    bgcolor="#17253B" if active else "#0D1524",
                    border=ft.Border.all(2 if active else 1, "#FFFFFF" if active else "#1E293B"),
                    on_click=lambda e, cid=cat_id: self._select_cat(cid),
                    animate=Motion.anim(Motion.FADE_MS),
                )
            )
        self.tab_row.controls = tabs

    def _is_equipped(self, cat_id: str, item_id: str) -> bool:
        c = self.custom
        if cat_id == "base":
            return c.body == item_id
        if cat_id == "skin":
            return (not c.makeups) if item_id == "" else (item_id in c.makeups)
        if cat_id == "eyes":
            return c.eyes == item_id
        if cat_id == "nose":
            return c.nose == item_id
        if cat_id == "mouth":
            return c.mouth == item_id
        if cat_id == "hair":
            return c.hair == item_id
        if cat_id == "clothes":
            return c.clothes == item_id
        return False

    def _rebuild_grid(self) -> None:
        cat_tuple = next(
            (c for c in avatar_catalog.CATEGORIES if c[0] == self.active_cat),
            avatar_catalog.CATEGORIES[0],
        )
        cat_id, _label, items, allow_none = cat_tuple
        tiles: list[ft.Control] = []

        if allow_none:
            none_active = self._is_equipped(cat_id, "")
            tiles.append(
                ft.Container(
                    ft.Icon(
                        ft.Icons.BLOCK,
                        size=26,
                        color="#FFFFFF" if none_active else C.TEXT_DIM,
                    ),
                    width=68,
                    height=68,
                    border_radius=14,
                    bgcolor="#17253B" if none_active else "#0D1524",
                    border=ft.Border.all(
                        2.5 if none_active else 1,
                        "#FFFFFF" if none_active else C.OUTLINE,
                    ),
                    alignment=ft.Alignment.CENTER,
                    on_click=lambda e, cid=cat_id: self._select_item(cid, ""),
                    tooltip="None",
                )
            )

        for item_id in items:
            active = self._is_equipped(cat_id, item_id)
            tiles.append(
                ft.Container(
                    ft.Image(
                        src=avatar_catalog.asset_path(item_id),
                        width=54,
                        height=54,
                        fit=ft.BoxFit.CONTAIN,
                        filter_quality=ft.FilterQuality.NONE,
                    ),
                    width=68,
                    height=68,
                    border_radius=14,
                    bgcolor="#17253B" if active else "#0D1524",
                    border=ft.Border.all(
                        2.5 if active else 1,
                        "#FFFFFF" if active else C.OUTLINE,
                    ),
                    alignment=ft.Alignment.CENTER,
                    on_click=lambda e, cid=cat_id, iid=item_id: self._select_item(cid, iid),
                    tooltip=item_id,
                )
            )

        self.item_grid.controls = tiles

    def _select_cat(self, cat_id: str) -> None:
        if self.active_cat == cat_id:
            return
        self.active_cat = cat_id
        sfx.play("tap")
        self._rebuild_tabs()
        self._rebuild_grid()
        pg = _mounted_page(self)
        if pg:
            from lol.ui.components import buzz

            pg.run_task(buzz, "select")
            self.update()

    def _select_item(self, cat_id: str, item_id: str) -> None:
        from lol.ui.components import buzz, pop

        if cat_id == "skin":
            new_makeups, ok = avatar_catalog.toggle_makeup(self.custom.makeups, item_id)
            if not ok:
                sfx.play("error_soft")
                if self.on_limit_toast:
                    self.on_limit_toast(
                        "Max 3 skin details stacked! Tap an active one to remove it."
                    )
                return
            self.custom = dataclasses.replace(self.custom, makeups=new_makeups)
        elif cat_id == "base":
            self.custom = dataclasses.replace(self.custom, body=item_id)
        elif cat_id == "eyes":
            self.custom = dataclasses.replace(self.custom, eyes=item_id)
        elif cat_id == "nose":
            self.custom = dataclasses.replace(self.custom, nose=item_id)
        elif cat_id == "mouth":
            self.custom = dataclasses.replace(self.custom, mouth=item_id)
        elif cat_id == "hair":
            self.custom = dataclasses.replace(self.custom, hair=item_id)
        elif cat_id == "clothes":
            self.custom = dataclasses.replace(self.custom, clothes=item_id)

        sfx.play("text_blip_01")
        self.preview_avatar.set_custom(self.custom)
        self._rebuild_tabs()
        self._rebuild_grid()
        pg = _mounted_page(self)
        if pg:
            pg.run_task(buzz, "select")
            pg.run_task(pop, self.preview_avatar, 1.05)
            self.update()
        if self.on_change:
            self.on_change(self.custom)

    def _on_randomize(self, _: Any = None) -> None:
        from lol.ui.components import buzz, pop

        self.custom = avatar_catalog.randomize_avatar()
        sfx.play("text_blip_01")
        self.preview_avatar.set_custom(self.custom)
        self._rebuild_tabs()
        self._rebuild_grid()
        pg = _mounted_page(self)
        if pg:
            pg.run_task(buzz, "medium")
            pg.run_task(pop, self.random_btn, 1.15)
            pg.run_task(pop, self.preview_avatar, 1.08)
            self.update()
        if self.on_change:
            self.on_change(self.custom)


def open_character_editor(app: App, *, on_saved: Callable[[], None] | None = None) -> None:
    """Open a bottom sheet with CharacterCustomizer to edit and save the player's chibi avatar."""
    from lol.ui.screens import common

    p = app.game.profile
    customizer = CharacterCustomizer(
        custom=avatar_catalog.sanitize(p.avatar_customization),
        hero_name=p.name,
        on_limit_toast=lambda msg: app.toast(msg, ft.Icons.INFO_OUTLINE),
    )

    body: list[ft.Control] = []
    if not p.avatar_bonus_claimed:
        body.append(
            ft.Container(
                ft.Row(
                    [
                        ft.Icon(ft.Icons.MONETIZATION_ON, color=C.ACCENT, size=20),
                        ft.Text(
                            "+200 Coins first-time reward!",
                            size=Type.LABEL,
                            weight=ft.FontWeight.W_800,
                            color=C.ACCENT,
                            expand=True,
                        ),
                    ],
                    spacing=Space.SM,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                bgcolor=C.a(C.ACCENT, 0.14),
                border=ft.Border.all(1, C.a(C.ACCENT, 0.45)),
                border_radius=Radius.MD,
                padding=ft.Padding.symmetric(horizontal=Space.MD, vertical=Space.SM),
            )
        )

    def save(_: Any = None) -> None:
        app.game.set_profile(
            avatar_customization=customizer.custom,
            avatar_configured=True,
        )
        bonus = app.game.claim_avatar_bonus()
        app.save()
        common.close(sheet)
        app.refresh_profile()
        if bonus > 0:
            sfx.play("level_up", 0.8)
            if app.page:
                app.page.run_task(app.coins_changed)
            app.toast(f"Avatar saved! +{bonus} coins awarded!", ft.Icons.MONETIZATION_ON)
        else:
            app.toast("Avatar updated!", ft.Icons.FACE)
        if on_saved:
            on_saved()

    body.append(customizer)
    body.append(ft.Row([common.primary_button("Save Avatar", save, icon=ft.Icons.CHECK)]))
    sheet = common.open_sheet(app.page, "Customize Avatar", body)


def prompt_existing_user_avatar(app: App) -> None:
    """Prompt an existing onboarded user who hasn't configured their chibi avatar yet."""
    from lol.ui.app import run_onboarding
    from lol.ui.screens import common

    p = app.game.profile

    def go_create(_: Any = None) -> None:
        common.close(sheet)
        open_character_editor(app)

    def go_redo(_: Any = None) -> None:
        common.close(sheet)
        run_onboarding(app, redo=True)

    def go_later(_: Any = None) -> None:
        common.close(sheet)

    preview = bubble(p.avatar_id, 88, custom=p.avatar_customization)
    sheet = common.open_sheet(
        app.page,
        "Meet Your New Chibi Avatar!",
        [
            ft.Container(preview, alignment=ft.Alignment.CENTER),
            ft.Text(
                "Character Creation is here! Customize your chibi hero's hair, eyes, "
                "outfit, and stacked skin details — or redo onboarding — and claim a "
                "one-time +200 Coins bonus!",
                size=Type.BODY,
                color=C.TEXT_DIM,
                text_align=ft.TextAlign.CENTER,
            ),
            ft.Row(
                [
                    common.primary_button(
                        "Create My Avatar (+200 Coins)",
                        go_create,
                        icon=ft.Icons.FACE_RETROUCHING_NATURAL
                        if hasattr(ft.Icons, "FACE_RETROUCHING_NATURAL")
                        else ft.Icons.FACE_RETOUCHING_NATURAL,
                    )
                ]
            ),
            ft.Row(
                [
                    common.secondary_button(
                        "Redo Onboarding (+200 Coins)",
                        go_redo,
                        icon=ft.Icons.AUTO_AWESOME,
                    )
                ]
            ),
            ft.Row(
                [
                    ft.TextButton(
                        "Maybe later",
                        on_click=common.with_sound(go_later),
                        height=Size.TAP,
                        style=ft.ButtonStyle(color=C.TEXT_DIM),
                    )
                ],
                alignment=ft.MainAxisAlignment.CENTER,
            ),
        ],
    )
