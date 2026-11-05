"""More -> Templates: the starter library plus your own templates. "Use" adds a quest (the
template never changes); edit any template; hide/restore built-ins; delete your own."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import flet as ft

from lol.core.models import QuestTemplate
from lol.ui import components as ui
from lol.ui import sfx, voice
from lol.ui import theme as th
from lol.ui.screens import common, editors
from lol.ui.theme import C, Motion, Radius, Space, Type

if TYPE_CHECKING:
    from lol.ui.app import App

DIFF_NAMES = {1: "Easy", 2: "Medium", 3: "Hard"}


class TemplatesScreen:
    title = "Templates"

    def __init__(self, app: App) -> None:
        self.app = app
        self.list = common.screen_list()
        self.view = ft.Container(self.list, expand=True, key="templates")
        self.fab = ft.FloatingActionButton(icon=ft.Icons.ADD, on_click=self._new,
                                           bgcolor=C.PRIMARY, foreground_color=C.ON_PRIMARY,
                                           tooltip="New template")

    def render(self) -> None:
        g = self.app.game
        hidden_ids = set(g.data.hidden_templates)
        everything = g.templates(include_hidden=True)
        mine = [t for t in everything if not t.builtin]
        builtin = [t for t in everything if t.builtin and t.id not in hidden_ids]
        hidden = [t for t in everything if t.builtin and t.id in hidden_ids]
        items: list[ft.Control] = [common.hint(
            "Reusable quests. Use one to add it to your list; the template stays as it is. "
            "Save any quest as a template from its dots menu.")]
        items.append(ui.SectionHeader("My templates", count=len(mine), action_text="New",
                                      on_action=self._new))
        if mine:
            items += [self._row(t) for t in mine]
        else:
            items.append(common.hint("None yet. Tap New, or save a quest as a template."))
        items.append(ui.SectionHeader("Starter library", count=len(builtin)))
        items += [self._row(t) for t in builtin]
        if hidden:
            items.append(ui.SectionHeader("Hidden", count=len(hidden)))
            items += [self._hidden_row(t) for t in hidden]
        self.list.controls = items

    def restyle(self) -> None:
        self.render()
        ui.refresh(self.list)

    def _refresh(self) -> None:
        self.app.more.refresh_top()

    def _row(self, t: QuestTemplate) -> ft.Control:
        pc = th.path_color(t.path_id)
        meta = [ui.xp_chip(t.xp), ui.coin_chip(t.coins),
                ui.chip(DIFF_NAMES.get(t.difficulty, ""), color=C.TEXT_DIM)]
        if t.kind == "daily":
            meta.append(ft.Icon(ft.Icons.EVENT_REPEAT, size=16, color=C.TEXT_DIM))
        if t.minutes:
            meta.append(common.hint(voice.minutes_text(t.minutes)))
        use = ft.Container(
            ft.Text("Use", size=Type.LABEL, weight=ft.FontWeight.BOLD, color=C.ON_PRIMARY),
            height=40, border_radius=Radius.PILL, bgcolor=pc, alignment=ft.Alignment.CENTER,
            padding=ft.Padding.symmetric(horizontal=Space.LG), scale=1,
            animate_scale=Motion.anim(Motion.POP_MS, Motion.BACK))

        async def tap_use(_: Any, tid: str = t.id) -> None:
            sfx.play("tap")
            await ui.pop(use, 1.1)
            q = self.app.game.quest_from_template(tid, self.app.today())
            self.app.save()
            self.app.lumen("quest_accepted", ft.Icons.ADD_TASK, title=q.title)
            self.app.toast(f"Added: {q.title}", ft.Icons.ADD_TASK)

        use.on_click = tap_use
        menu: list[tuple] = [("Edit", ft.Icons.EDIT, lambda tid=t.id: self._edit(tid))]
        if t.builtin:
            menu.append(("Hide", ft.Icons.VISIBILITY_OFF, lambda tid=t.id: self._hide(tid)))
        else:
            menu.append(("Delete", ft.Icons.DELETE_OUTLINE,
                         lambda tid=t.id: self._delete(tid), True))
        edited = t.builtin and any(x.id == t.id for x in self.app.game.data.templates)
        full_tip = f"{t.title}\n{t.note}" if t.note else t.title
        col_items: list[ft.Control] = [
            ft.Text(t.title + (" · edited" if edited else ""), size=Type.BODY,
                    weight=ft.FontWeight.W_600, color=C.TEXT, max_lines=2,
                    overflow=ft.TextOverflow.ELLIPSIS, tooltip=full_tip),
        ]
        if t.note:
            col_items.append(ft.Text(t.note, size=Type.CAPTION, color=C.TEXT_DIM, max_lines=2,
                                     overflow=ft.TextOverflow.ELLIPSIS, tooltip=t.note))
        col_items.append(ft.Row(meta, spacing=Space.XS, wrap=True, run_spacing=2,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER))
        return ft.Container(ft.Row([
            ui.path_avatar(th.path_icon(t.path_id), pc, 38),
            ft.Column(col_items, spacing=Space.XS, expand=True, tight=True),
            use, common.menu_button(menu, tooltip="Template options"),
        ], spacing=Space.SM, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            bgcolor=C.SURFACE_HI, border_radius=Radius.MD,
            padding=ft.Padding.only(left=Space.MD, right=0, top=Space.SM, bottom=Space.SM),
            on_long_press=lambda e, tid=t.id: self._edit(tid), tooltip=full_tip)

    def _hidden_row(self, t: QuestTemplate) -> ft.Control:
        def restore(_: Any = None) -> None:
            self.app.game.restore_template(t.id)
            self.app.save()
            self._refresh()
            self.app.toast(f"{t.title} restored", ft.Icons.RESTORE)

        return ft.Container(ft.Row([
            ft.Icon(ft.Icons.VISIBILITY_OFF, color=C.TEXT_DIM, size=20),
            ft.Text(t.title, size=Type.BODY, color=C.TEXT_DIM, expand=True),
            ft.TextButton("Restore", icon=ft.Icons.RESTORE, on_click=common.with_sound(restore)),
        ], spacing=Space.MD, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            bgcolor=C.SURFACE, border_radius=Radius.MD,
            padding=ft.Padding.symmetric(horizontal=Space.MD, vertical=Space.XS))

    def _values(self, t: QuestTemplate) -> dict:
        return {"title": t.title, "path_id": t.path_id, "difficulty": t.difficulty,
                "kind": t.kind, "note": t.note, "xp": t.xp, "coins": t.coins}

    def _edit(self, template_id: str) -> None:
        t = self.app.game.template(template_id)

        def save(v: dict) -> bool:
            try:
                self.app.game.edit_template(template_id, **v)
            except ValueError as exc:
                self.app.error(f"Couldn't save: {exc}")
                return False
            self.app.save()
            self._refresh()
            self.app.toast("Template saved", ft.Icons.LIBRARY_BOOKS)
            return True

        intro = ("A starter template: your edits are kept, and Restore (after hiding) brings "
                 "back the original.") if t.builtin else None
        editors.quest_form(self.app, "Edit template", self._values(t), save, intro=intro)

    def _new(self, _: Any = None) -> None:
        def save(v: dict) -> bool:
            try:
                self.app.game.add_template(v["title"], v["path_id"], v["difficulty"],
                                           v["kind"], v["note"], xp=v["xp"], coins=v["coins"])
            except ValueError as exc:
                self.app.error(f"Couldn't save: {exc}")
                return False
            self.app.save()
            self._refresh()
            self.app.toast(f"Template added: {v['title']}", ft.Icons.LIBRARY_BOOKS)
            return True

        editors.quest_form(self.app, "New template", {}, save, save_text="Save template")

    def _hide(self, template_id: str) -> None:
        t = self.app.game.template(template_id)
        self.app.game.delete_template(template_id)
        self.app.save()
        self._refresh()
        self.app.toast(f"{t.title} hidden. Restore it any time.", ft.Icons.VISIBILITY_OFF)

    async def _delete(self, template_id: str) -> None:
        t = self.app.game.template(template_id)
        if not await common.confirm(self.app.page, "Delete template?",
                                    f"\"{t.title}\" is removed. Quests made from it stay.",
                                    "Delete", danger=True):
            return
        self.app.game.delete_template(template_id)
        self.app.save()
        self._refresh()
        self.app.toast("Template deleted", ft.Icons.DELETE_OUTLINE)
