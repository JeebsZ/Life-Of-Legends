"""Quests tab: Side Quests (skill chains) on top, the Quest Board ("Ask Luma"), then every
quest grouped by Path."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import flet as ft

from lol.core.models import Quest
from lol.ui import components as ui
from lol.ui import theme as th
from lol.ui import voice
from lol.ui.screens import common, editors
from lol.ui.screens.side_quests import SideQuestsSection
from lol.ui.screens.today import open_quest_sheet
from lol.ui.theme import C, Space, Type

# Quest Board 'Give me a quest': Luma's reference staged analysis (the default stages)
BOARD_STAGES = ("ANALYSIS…", "MATCHING PATHS…", "PROPOSAL READY")

if TYPE_CHECKING:
    from lol.ui.app import App


class QuestsScreen:
    def __init__(self, app: App) -> None:
        self.app = app
        self.path_filter = "all"
        self.difficulty = "any"
        self.view_mode = "active"
        self.seen: set[str] = set()  # titles suggested this session (reroll avoids repeats)
        self.current: Quest | None = None
        self.side = SideQuestsSection(app, on_change=self.refresh)

        self.board = ui.QuestSuggestionCard(on_accept=self._accept, on_reroll=self._next,
                                            on_skip=self._next)
        self.board_slot = ft.Container(self.board, visible=False)
        self.give_btn = common.primary_button("Ask Luma", self._give,
                                              icon=ft.Icons.AUTO_AWESOME)
        self.list = common.screen_list()
        self.view = ft.Container(self.list, expand=True, key="quests")
        self.fab = ft.FloatingActionButton(icon=ft.Icons.ADD, on_click=self._open_add,
                                           bgcolor=C.PRIMARY, foreground_color=C.ON_PRIMARY,
                                           tooltip="New quest")

    # ------------------------------------------------------------------ Quest Board
    def _suggest(self) -> Quest:
        g, today = self.app.game, self.app.today()
        mine = {q.title for q in g.quests if not g.is_done(q, today)}
        path = None if self.path_filter == "all" else self.path_filter
        diff = None if self.difficulty == "any" else int(self.difficulty)
        q = g.suggest_quest(path, diff, exclude=self.seen | mine)
        if q.title in self.seen:  # pool exhausted for this filter: start a fresh cycle
            self.seen.clear()
        self.seen.add(q.title)
        self.current = q
        return q

    def _as_kwargs(self, q: Quest) -> dict:
        return {"title": q.title, "path_id": q.path_id, "xp": q.xp, "coins": q.coins,
                "difficulty": q.difficulty, "note": q.note,
                "header": voice.say("board_header"),
                "analysis": voice.say("board_analysis", minutes=voice.minutes_text(q.minutes),
                                      difficulty=voice.difficulty_text(q.difficulty))}

    async def _give(self, _: Any = None) -> None:
        await ui.buzz("light")
        q = await ui.lumen_analyze(self.app.page, BOARD_STAGES, self._suggest, seconds=2.5)
        if not self.board_slot.visible:
            self.board_slot.visible = True
            self.give_btn.content = "Ask again"
            ui.refresh(self.board_slot, self.give_btn)
        await self.board.show(**self._as_kwargs(q))

    def _next(self, _card: Any) -> dict:
        return self._as_kwargs(self._suggest())

    def _accept(self, _card: Any) -> dict | bool:
        if self.current is None:
            return False
        q = self.app.game.accept(self.current, self.app.today())
        self.app.save()
        self.app.lumen("quest_accepted", ft.Icons.ADD_TASK, title=q.title)
        nxt = self._as_kwargs(self._suggest())
        self._render_list()
        ui.refresh(self.list)
        return nxt

    def _filters_changed(self) -> None:
        if self.board_slot.visible:
            self.app.page.run_task(self.board.show, **self._as_kwargs(self._suggest()))

    def _set_path(self, v: str) -> None:
        self.path_filter = v
        self._filters_changed()

    def _set_diff(self, v: str) -> None:
        self.difficulty = v
        self._filters_changed()

    # ------------------------------------------------------------------ render
    def render(self) -> None:
        self.board.restyle()
        self.filters = common.ChoicePills(common.path_options(include_all=True),
                                          self.path_filter, on_change=self._set_path,
                                          grid_cols=0)
        self.diff = common.segmented(
            [("any", "Any"), ("1", "Easy"), ("2", "Medium"), ("3", "Hard")], self.difficulty,
            on_change=self._set_diff)
        self.mode = common.segmented(
            [("active", "Active"), ("daily", "Daily"), ("done", "Done")], self.view_mode,
            on_change=self._set_mode)
        self._render_list()

    def _set_mode(self, v: str) -> None:
        self.view_mode = v
        self._render_list()
        ui.refresh(self.list)

    def _render_list(self) -> None:
        g, today = self.app.game, self.app.today()
        board = common.card(ft.Column([
            ft.Text("Not sure what to do? Pick a Path and a size, and Luma will propose one.",
                    size=Type.LABEL, color=C.TEXT_DIM),
            self.filters, ft.Row([self.diff], scroll=ft.ScrollMode.HIDDEN),
            ft.Row([self.give_btn]),
        ], spacing=Space.MD, tight=True))
        items: list[ft.Control] = [*self.side.controls(),
                                   ui.SectionHeader("Quest Board"), board, self.board_slot,
                                   ui.SectionHeader("My quests", count=len(g.quests)),
                                   ft.Row([self.mode], scroll=ft.ScrollMode.HIDDEN)]

        def keep(q: Quest) -> bool:
            done = g.is_done(q, today)
            if self.view_mode == "daily":
                return q.kind == "daily"
            if self.view_mode == "done":
                return done
            return not done

        shown = [q for q in g.quests if keep(q)]
        if not shown:
            msg = {"active": ("Nothing open right now", "Ask Luma above, or tap + to add."),
                   "daily": ("No daily quests yet", "Dailies reset each morning. Try one!"),
                   "done": ("Nothing done yet today", "Your wins will show up here.")}
            t, m = msg[self.view_mode]
            items.append(ui.EmptyState(t, m, icon=ft.Icons.FLAG))
        for pid in th.PATH_IDS:
            group = [q for q in shown if q.path_id == pid]
            if not group:
                continue
            lvl = g.path_level(pid)[0]
            items.append(ft.Container(ft.Row([ui.PathBadge(pid, level=lvl)]),
                                      padding=ft.Padding.only(top=Space.SM)))
            items += [self._card(q) for q in group]
        if shown:
            items.append(ft.Container(common.hint("Tap the dots on a quest to edit it, save it "
                                                  "as a template or focus on it."),
                                      alignment=ft.Alignment.CENTER, padding=Space.SM))
        self.list.controls = items

    def refresh(self) -> None:
        """Re-render after a side quest starts, finishes or is set aside. Swaps in a fresh
        ListView: Flet's in-place diff of this list (after a dialog/sheet closed) could leave
        a stale duplicate row ("QUEST BOARD" twice) on web."""
        self.list = common.screen_list()
        self._render_list()
        self.view.content = self.list
        ui.refresh(self.view)

    def _card(self, q: Quest) -> ui.QuestCard:
        g, today = self.app.game, self.app.today()
        return ui.QuestCard(
            q.title, path_id=q.path_id, xp=q.xp, coins=q.coins, done=g.is_done(q, today),
            streak=g.streak(q, today), kind=q.kind, note=q.note,
            on_complete=lambda card, qid=q.id: self._complete(qid, card),
            on_long_press=lambda e, qid=q.id: self._edit(qid),
            menu=editors.quest_menu(self.app, q.id, on_edited=self._edited,
                            on_delete=lambda qid=q.id: self._delete(qid)),
            data=q.id,
        )

    def _edit(self, quest_id: str) -> None:
        editors.edit_quest(self.app, quest_id, self._edited)

    def _edited(self) -> None:
        self._render_list()
        ui.refresh(self.list)

    async def _complete(self, quest_id: str, card: Any = None) -> bool:
        g, today = self.app.game, self.app.today()
        await self.app.award(lambda: g.complete_quest(quest_id, today),
                             cleared=g.quest(quest_id).title,
                             at=getattr(card, "tap_pos", None))
        return True

    async def _delete(self, quest_id: str) -> None:
        await ui.buzz("medium")
        q = self.app.game.quest(quest_id)
        ok = await common.confirm(self.app.page, "Remove quest?",
                                  f"\"{q.title}\" leaves your list. XP and coins you already "
                                  "earned stay yours.", "Remove", danger=True)
        if not ok:
            return
        self.app.game.delete_quest(quest_id)
        self.app.save()
        self._render_list()
        ui.refresh(self.list)
        self.app.toast("Quest removed", ft.Icons.DELETE_OUTLINE)

    def _open_add(self, _: Any = None) -> None:
        def added(q: Quest) -> None:
            self._render_list()
            ui.refresh(self.list)
            self.app.toast(f"Added: {q.title}", ft.Icons.ADD_TASK)

        open_quest_sheet(self.app, on_added=added, with_difficulty=True)

