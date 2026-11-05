"""More -> Skills: a linked skill tree per skill (ACQUIRED / NEXT / LOCKED nodes), the rank
list with Rank up, running side quests as chains, and Quest Board practices."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import flet as ft

from lol.core.models import MAX_RANK, RANK_NAMES, Skill
from lol.ui import components as ui
from lol.ui import effects as fx
from lol.ui import theme as th
from lol.ui import voice
from lol.ui.screens import common
from lol.ui.theme import C, Motion, Radius, Space, Type

# Luma's staged analysis before a rank-up chain starts
RANK_UP_STAGES = ("MEASURING MASTERY…", "FORGING THE NEXT RANK…", "RANK-UP READY")

if TYPE_CHECKING:
    from lol.ui.app import App


def skill_nodes(app: App, sk: Skill) -> list[dict]:
    """Rank chain of one skill: earned ranks ACQUIRED, the next one NEXT, the rest LOCKED."""
    g = app.game
    pc = th.path_color(sk.path_id)
    nodes = [{"id": f"rank:{sk.name}:1", "label": sk.name, "state": "acquired",
              "path_color": pc, "parent": None}]
    follow = g.followups_for(sk.name)
    for rank in range(2, MAX_RANK + 1):
        if rank <= sk.rank:
            state = "acquired"
        elif rank == sk.rank + 1 and follow:
            state = "next"
        else:
            state = "locked"
        nodes.append({"id": f"rank:{sk.name}:{rank}", "label": RANK_NAMES.get(rank, ""),
                      "state": state, "path_color": pc, "parent": f"rank:{sk.name}:{rank - 1}"})
    return nodes


def chain_nodes(app: App, sq: Any) -> list[dict]:
    """A running side quest: the chain on top, its steps below (done / next / locked)."""
    g = app.game
    pc = th.path_color(sq.path_id)
    nxt = g.next_step(sq)
    nodes = [{"id": f"sq:{sq.id}", "label": sq.skill_name, "state": "next" if not sq.paused
              else "paused", "path_color": pc, "parent": None}]
    for i, st in enumerate(sq.steps):
        if st.done_on:
            state = "acquired"
        elif st.skipped_on:
            state = "skipped"
        elif i == nxt or not sq.ordered:
            state = "next" if i == nxt else "open"
        else:
            state = "locked"
        nodes.append({"id": f"step:{sq.id}:{i}", "label": st.title, "state": state,
                      "path_color": pc, "parent": f"sq:{sq.id}"})
    return nodes


class SkillsScreen:
    title = "Skills"

    def __init__(self, app: App) -> None:
        self.app = app
        self.list = common.screen_list()
        self.view = ft.Container(self.list, expand=True, key="skills")

    def render(self) -> None:
        g = self.app.game
        skills = g.skills()
        running = [sq for sq in g.side_quests(active_only=True)]
        items: list[ft.Control] = [ui.SectionHeader("Skill links", count=len(skills))]
        if not skills and not running:
            items.append(common.card(ui.EmptyState(
                "No skills yet", voice.say("skills_empty"), icon=ft.Icons.MILITARY_TECH,
                action_text="Start a side quest", on_action=lambda e: self._to_catalog()),
                padding=0))
        for sk in skills:
            items.append(common.card(ft.Column([
                fx.SkillLinkTree(skill_nodes(self.app, sk), on_tap=self._tap_node,
                                 node_width=100, node_height=74, v_gap=28),
                self._skill_row(sk),
            ], spacing=Space.MD, tight=True), padding=Space.MD))
        if running:
            items.append(ui.SectionHeader("Chains in progress", count=len(running)))
            for sq in running:
                items.append(common.card(ft.Column([
                    fx.SkillLinkTree(chain_nodes(self.app, sq), on_tap=self._tap_node,
                                     node_width=100, node_height=74, v_gap=28),
                    common.hint("Paused. Resume it from the Quests tab." if sq.paused else
                                "Tap a step on the Quests tab when it's done."),
                ], spacing=Space.SM, tight=True), padding=Space.MD))
        practiced = g.practiced()
        if practiced:
            items.append(ui.SectionHeader("Practiced", count=len(practiced)))
            items.append(ft.Row([
                ui.chip(q.title, icon=th.path_icon(q.path_id), color=th.path_color(q.path_id))
                for q in practiced
            ], wrap=True, spacing=Space.XS + 2, run_spacing=Space.XS + 2))
        self.list.controls = items

    def restyle(self) -> None:
        self.render()
        ui.refresh(self.list)

    async def _tap_node(self, node_id: str) -> None:
        kind, _, rest = node_id.partition(":")
        if kind == "rank":
            name, _, rank_s = rest.rpartition(":")
            sk = self.app.game.skill(name)
            if sk is None:
                return
            rank = int(rank_s)
            if rank <= sk.rank:
                self.app.toast(f"{sk.name} · {RANK_NAMES.get(rank, '')} acquired",
                               ft.Icons.MILITARY_TECH)
                return
            follow = self.app.game.followups_for(sk.name)
            if rank == sk.rank + 1 and follow:
                if self.app.game.can_start(follow[0].id):
                    await self._rank_up(follow[0].id)
                else:
                    self.app.toast("That rank-up chain is already running", ft.Icons.HOURGLASS_TOP)
                return
            self.app.toast(f"Reach {RANK_NAMES.get(rank - 1, '')} first", ft.Icons.LOCK)
        else:  # a running chain or one of its steps
            self.app.go(1)

    def _skill_row(self, sk: Skill) -> ft.Control:
        g = self.app.game
        pc = th.path_color(sk.path_id)
        stars = ft.Row([ft.Icon(ft.Icons.STAR if i < sk.rank else ft.Icons.STAR_BORDER,
                                size=14, color=pc if i < sk.rank else C.a(C.TEXT, 0.25))
                        for i in range(3)], spacing=0, tight=True)
        follow = g.followups_for(sk.name)
        trailing: ft.Control
        if not follow:
            trailing = ui.chip("Max rank", icon=ft.Icons.WORKSPACE_PREMIUM, color=C.ACCENT)
        elif g.can_start(follow[0].id):
            nxt = follow[0]
            btn = ft.Container(
                ft.Row([ft.Icon(ft.Icons.TRENDING_UP, size=16, color=C.ON_PRIMARY),
                        ft.Text("Rank up", size=Type.LABEL, weight=ft.FontWeight.BOLD,
                                color=C.ON_PRIMARY)], spacing=Space.XS, tight=True),
                height=40, border_radius=Radius.PILL, bgcolor=pc, alignment=ft.Alignment.CENTER,
                padding=ft.Padding.symmetric(horizontal=Space.MD), scale=1,
                animate_scale=Motion.anim(Motion.POP_MS, Motion.BACK),
                tooltip=f"Start: {RANK_NAMES.get(nxt.rank, '')} chain",
            )

            async def go(_: Any, cid: str = nxt.id, b: ft.Control = btn) -> None:
                await ui.pop(b, 1.1)
                await self._rank_up(cid)

            btn.on_click = go
            trailing = btn
        else:
            trailing = ft.TextButton("In progress", icon=ft.Icons.HOURGLASS_TOP,
                                     on_click=lambda e: self.app.go(1),
                                     style=ft.ButtonStyle(color=C.TEXT_DIM))
        return ft.Row([
            ft.Column([
                ft.Text(sk.name, size=Type.BODY, weight=ft.FontWeight.W_600, color=C.TEXT,
                        max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                ft.Row([ui.chip(sk.rank_name, icon=ft.Icons.MILITARY_TECH, color=pc), stars],
                       spacing=Space.SM, tight=True,
                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ], spacing=Space.XS, expand=True, tight=True),
            trailing,
        ], spacing=Space.MD, vertical_alignment=ft.CrossAxisAlignment.CENTER)

    async def _rank_up(self, catalog_id: str) -> None:
        await ui.buzz("medium")
        await ui.lumen_analyze(self.app.page, RANK_UP_STAGES, seconds=2.2)
        quests = self.app.screens[1]
        if quests.side.start(catalog_id, rank_up=True):
            self.app.go(1)

    def _to_catalog(self) -> None:
        self.app.go(1)
        self.app.screens[1].side.open_catalog()
