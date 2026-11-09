"""More -> Profile: name, avatar, Luma voice, the six Paths and the theme picker (the old Me
tab's profile half; skills, report and logbook have their own sub-screens)."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import flet as ft

from lol.core import cosmetics as cos
from lol.core.game import level_from_total
from lol.core.progression import bar_steps
from lol.ui import audio, avatars, sfx
from lol.ui import components as ui
from lol.ui import theme as th
from lol.ui.screens import common
from lol.ui.theme import C, Motion, Size, Space, Type

if TYPE_CHECKING:
    from lol.ui.app import App

CREDITS = "Luma voice dataset: Alba (University of Edinburgh, CC BY 4.0)"
DATA_CREDIT = ("Food data: USDA FoodData Central (U.S. Department of Agriculture, Agricultural "
               "Research Service), public domain CC0. Restaurant items: chain sites or "
               "labelled estimates.")


class ProfileScreen:
    title = "Profile"

    def __init__(self, app: App) -> None:
        self.app = app
        self.seen_path_xp: dict[str, int] | None = None  # Path XP when Profile was last shown
        self.list = common.screen_list()
        self.view = ft.Container(self.list, expand=True, key="profile")

    # ------------------------------------------------------------------ render
    def render(self) -> None:
        p = self.app.game.profile
        items: list[ft.Control] = [self._profile_card()]

        # --- Paths: bars catch up on XP earned since you last looked ---
        items.append(ui.SectionHeader("Paths"))
        seen = self.seen_path_xp or dict(p.path_xp)
        gains: list[tuple[ui.PathProgress, list[float], str]] = []
        for pid in th.PATH_IDS:
            total, before = p.path_xp.get(pid, 0), seen.get(pid, 0)
            lvl, xp, need = level_from_total(min(before, total))
            pp = ui.PathProgress(pid, level=lvl, value=xp / need, caption=f"{xp} / {need} XP")
            items.append(pp)
            if total > before:
                _, end_xp, end_need = level_from_total(total)
                gains.append((pp, bar_steps(lvl, xp, total - before),
                              f"{end_xp} / {end_need} XP"))
        self.seen_path_xp = dict(p.path_xp)
        for pp, steps, caption in gains:
            self.app.page.run_task(self._play_path, pp, steps, caption)

        items += [ui.SectionHeader("Theme"), theme_picker(self.app)]
        items.append(ft.Container(ft.Column([
            common.hint("Life of Legends · guest profile, saved on this device"),
            common.hint(CREDITS),
            common.hint(DATA_CREDIT),
        ], spacing=2, tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            alignment=ft.Alignment.CENTER, padding=ft.Padding.only(top=Space.MD)))
        self.list.controls = items

    def restyle(self) -> None:
        self.render()
        ui.refresh(self.list)

    async def _play_path(self, pp: ui.PathProgress, steps: list[float], caption: str) -> None:
        await asyncio.sleep(0.45)  # let the slide-in finish first
        await pp.play(steps, caption=caption)

    def _profile_card(self) -> ft.Control:
        g = self.app.game
        p = g.profile
        total_path = sum(p.path_xp.values())
        top = max(th.PATH_IDS, key=lambda pid: p.path_xp.get(pid, 0))
        top_txt = (f"Strongest Path: {th.path_name(top)}" if p.path_xp.get(top, 0)
                   else "Complete a quest to start a Path")
        bubble = avatars.bubble(
            p.avatar_id,
            88,
            custom=p.avatar_customization,
            frame_id=p.frame_id,
            pet_id=p.pet_id,
        )
        bubble.on_click = lambda e: avatars.open_character_editor(self.app, on_saved=self.restyle)
        equipped_tids = getattr(p, "equipped_titles", []) or []
        titles_to_show = [t for t in equipped_tids if t and t != "title_none"]
        if not titles_to_show and p.title_id and p.title_id != "title_none":
            titles_to_show = [p.title_id]

        pet_item = cos.get_cosmetic(p.pet_id, "pet")
        chips: list[ft.Control] = [
            ui.chip(f"{p.coins:,}", icon=ui.COIN_ICON, color=C.ACCENT),
            ui.chip(f"{total_path:,} XP earned", icon=ui.XP_ICON),
        ]
        for tid in reversed(titles_to_show[:3]):
            t_item = cos.get_cosmetic(tid, "title")
            if t_item.id != "title_none" and t_item.badge_text:
                chips.insert(0, ui.chip(t_item.badge_text, icon=ft.Icons.MILITARY_TECH, color=t_item.color))
        if pet_item.id != "pet_none" and pet_item.badge_text:
            chips.append(ui.chip(f"{pet_item.badge_text} {pet_item.name}", color=pet_item.color))
        identity = ft.Row([
            bubble,
            ft.Column([
                ft.Text(f"{p.name} · Lv {p.level}", size=Type.TITLE + 1,
                        weight=ft.FontWeight.W_900, color=C.TEXT, max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS),
                ft.Row(chips, spacing=Space.SM, wrap=True, run_spacing=Space.XS),
                common.hint(top_txt),
            ], spacing=Space.XS, expand=True, tight=True),
            ft.IconButton(ft.Icons.EDIT, icon_color=C.PRIMARY, tooltip="Edit profile",
                          width=Size.TAP, height=Size.TAP,
                          on_click=lambda e: self._open_profile()),
        ], spacing=Space.MD, vertical_alignment=ft.CrossAxisAlignment.CENTER)
        customize_row = ft.Row([
            common.secondary_button(
                "Customize Avatar",
                lambda _: avatars.open_character_editor(self.app, on_saved=self.restyle),
                icon=ft.Icons.FACE_RETOUCHING_NATURAL,
            )
        ])
        return common.card(ft.Column([identity, customize_row,
                                      ft.Divider(height=1, color=C.OUTLINE),
                                      voice_controls(self.app)],
                                     spacing=Space.MD, tight=True))

    def _open_profile(self) -> None:
        app, g = self.app, self.app.game
        p = g.profile
        name = common.text_field("Your name")
        name.value = p.name
        name.max_length = 24
        name.capitalization = ft.TextCapitalization.WORDS
        preview = ft.Container(
            avatars.bubble(
                p.avatar_id,
                96,
                custom=p.avatar_customization,
                frame_id=p.frame_id,
                pet_id=p.pet_id,
            ),
            alignment=ft.Alignment.CENTER,
            padding=ft.Padding.symmetric(vertical=Space.XS),
        )

        def open_customizer(_: Any = None) -> None:
            common.close(sheet)
            avatars.open_character_editor(app, on_saved=self.restyle)

        def save(_: Any = None) -> None:
            text = (name.value or "").strip()
            if not text:
                sfx.play("error_soft")
                name.error_text = "A name, nickname or title works"
                name.update()
                return
            g.set_profile(name=text)
            app.save()
            common.close(sheet)
            app.refresh_profile()
            self.render()
            ui.refresh(self.list)
            app.lumen("profile_saved", ft.Icons.PERSON)

        name.on_submit = save
        sheet = common.open_sheet(app.page, "Edit profile", [
            preview,
            name,
            ft.Row([
                common.secondary_button(
                    "Customize Avatar",
                    open_customizer,
                    icon=ft.Icons.FACE_RETOUCHING_NATURAL,
                )
            ]),
            ft.Row([common.primary_button("Save", save, icon=ft.Icons.CHECK)]),
        ])


def voice_controls(app: App) -> ft.Control:
    """Luma voice on/off + volume (shared by Profile and Settings)."""
    g = app.game
    p = g.profile
    icon = ft.Icon(ft.Icons.RECORD_VOICE_OVER if p.voice_on else ft.Icons.VOLUME_OFF,
                   color=C.PRIMARY if p.voice_on else C.TEXT_DIM, size=22)
    vol_label = ft.Text(f"{round(p.voice_volume * 100)}%", size=Type.CAPTION,
                        color=C.TEXT_DIM, width=40, text_align=ft.TextAlign.RIGHT)
    slider = ft.Slider(value=p.voice_volume, min=0, max=1, divisions=10,
                       active_color=C.PRIMARY, inactive_color=C.a(C.TEXT, 0.12),
                       expand=True, disabled=not p.voice_on)
    vol_row = ft.Row([ft.Icon(ft.Icons.VOLUME_UP, size=18, color=C.TEXT_DIM), slider,
                      vol_label], spacing=Space.XS,
                     vertical_alignment=ft.CrossAxisAlignment.CENTER,
                     opacity=1 if p.voice_on else 0.45,
                     animate_opacity=Motion.anim(Motion.FADE_MS))

    def toggle(e: Any) -> None:
        on = bool(e.control.value)
        sfx.play("toggle")
        g.set_profile(voice_on=on)
        app.save()
        icon.icon = ft.Icons.RECORD_VOICE_OVER if on else ft.Icons.VOLUME_OFF
        icon.color = C.PRIMARY if on else C.TEXT_DIM
        slider.disabled = not on
        vol_row.opacity = 1 if on else 0.45
        ui.refresh(icon, slider, vol_row)
        app.page.run_task(ui.buzz, "select")
        if on:
            audio.play("quest_done", 0)  # a short sample so you hear it's back
        app.toast("Luma voice on" if on else "Luma voice off. Notices still show.",
                  ft.Icons.RECORD_VOICE_OVER if on else ft.Icons.VOLUME_OFF)

    def sliding(e: Any) -> None:
        vol_label.value = f"{round(float(e.control.value) * 100)}%"
        ui.refresh(vol_label)

    def slid(e: Any) -> None:
        g.set_profile(voice_volume=float(e.control.value))
        app.save()
        audio.play("quest_done", 0)  # preview at the new volume (read live from profile)

    slider.on_change = sliding
    slider.on_change_end = slid
    return ft.Column([
        ft.Row([icon,
                ft.Column([ft.Text("Luma voice", size=Type.BODY, weight=ft.FontWeight.W_600,
                                   color=C.TEXT),
                           common.hint("Spoken notices for wins and reminders")],
                          spacing=0, expand=True, tight=True),
                ft.Switch(value=p.voice_on, active_color=C.PRIMARY, on_change=toggle)],
               spacing=Space.MD, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        vol_row,
    ], spacing=Space.XS, tight=True)


def theme_picker(app: App) -> ft.Control:
    """Theme swatches (shared by Profile and Settings)."""
    g = app.game

    def pick(theme_id: str) -> None:
        if theme_id not in g.profile.owned_themes:
            app.error("Unlock this theme in Rewards first")
            app.go(3)
            return
        if g.set_theme(theme_id):
            sfx.play("toggle")
            app.save()
            th.apply_theme(app.page, theme_id)  # re-renders the screen via callback

    swatches = [
        ui.ThemeSwatch(t.id, selected=t.id == g.profile.theme_id,
                       owned=t.id in g.profile.owned_themes,
                       price=None if t.id in g.profile.owned_themes else t.price,
                       on_select=pick)
        for t in g.themes() if t.id in th.THEMES
    ]
    return common.card(ft.Column([
        ft.Row(swatches, alignment=ft.MainAxisAlignment.CENTER, spacing=0,
               wrap=True, run_spacing=Space.XS),  # 3 per row at 375 px: a tidy 3x2 grid
        common.hint("Locked themes can be unlocked with coins in Rewards."),
    ], spacing=Space.SM, tight=True), padding=Space.MD)
