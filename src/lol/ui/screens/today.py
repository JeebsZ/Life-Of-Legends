"""Today tab: today's quests, one-tap complete, quick add, gentle bills nudge."""

from __future__ import annotations

import asyncio
from datetime import date
from typing import TYPE_CHECKING, Any

import flet as ft

from lol.core.models import Quest
from lol.ui import ambient, sfx, voice
from lol.ui import components as ui
from lol.ui import theme as th
from lol.ui.screens import common, editors
from lol.ui.theme import C, Motion, Radius, Size, Space, Type

if TYPE_CHECKING:
    from lol.ui.app import App


class TodayScreen:
    def __init__(self, app: App) -> None:
        self.app = app
        self.bill_voiced = False  # Luma speaks the bills nudge once per app open
        self.energy_skipped: date | None = None  # "skip for today" on the energy chip
        self.list = common.screen_list()
        self.view = ft.Container(self.list, expand=True, key="today")
        self.fab = ft.FloatingActionButton(icon=ft.Icons.ADD, on_click=self.open_add,
                                           bgcolor=C.PRIMARY, foreground_color=C.ON_PRIMARY,
                                           tooltip="Add quest")

    # ------------------------------------------------------------------ render
    def render(self) -> None:
        g, today = self.app.game, self.app.today()
        quests = g.today_quests(today)
        energy = g.energy_today(today) if g.module_on("energy") else None
        if energy is not None:  # re-sorted for today's energy (never filtered)
            quests = g.suggest_order(quests, energy)
        open_ = [q for q in quests if not g.is_done(q, today)]
        done = [q for q in quests if g.is_done(q, today)]
        items: list[ft.Control] = []

        nudge = self._bills_nudge()
        if nudge:
            items.append(nudge)
        if g.module_on("energy") and (energy is not None or self.energy_skipped != today):
            from lol.ui.screens import energy as energy_screen

            items.append(energy_screen.chip_row(self.app, self._rerender, self._skip_energy))

        items.append(self._quick_records_hub())

        self._header_at = len(items)
        items.append(self._header(len(open_)))
        if not quests:
            items.append(common.card(ui.EmptyState(
                "Your day is wide open", voice.say("empty_today"),
                icon=ft.Icons.AUTO_AWESOME, action_text="Ask Luma",
                on_action=lambda e: self.app.go(1)), padding=0))
        elif not open_:
            items.append(common.card(ui.EmptyState(
                "All quests done!", "Rest counts too. Want a bonus quest?",
                icon=ft.Icons.CELEBRATION, action_text="Ask Luma",
                on_action=lambda e: self.app.go(1)), padding=0))
        items += [self._card(q) for q in open_]
        if g.module_on("water"):
            from lol.ui.screens import water

            items.append(water.mini_card(self.app, self._rerender))
        from lol.ui.screens import meal  # opt-in kcal-left chip (off by default)

        chip = meal.today_chip(self.app)
        if chip is not None:
            items.append(chip)
        items += self._next_steps()
        if done:
            items.append(ui.SectionHeader("Done today", count=len(done)))
            items += [self._card(q) for q in done]
        self.list.controls = items

    def _quick_records_hub(self) -> ft.Control:
        g, today = self.app.game, self.app.today()

        def quick_water(amount_ml: int):
            def do_water(_):
                g.add_water(amount_ml, today)
                self.app.save()
                sfx.play("coin")
                self.app.toast(f"💧 +{amount_ml} mL water logged!", ft.Icons.WATER_DROP)
                self.render()
                ui.refresh(self.list)
            return do_water

        def open_journal(_):
            from lol.ui.screens import journal
            journal.open_journal_sheet(self.app, self._rerender)

        def open_workout(_):
            self.app.open_sub("workout")

        def open_run(_):
            self.app.open_sub("run")

        def open_grove(_):
            self.app.open_sub("grove")

        actions = [
            ("Workout", ft.Icons.FITNESS_CENTER_ROUNDED, "#FF6F91", open_workout),
            ("+250ml", ft.Icons.WATER_DROP_ROUNDED, "#5EC8F2", quick_water(250)),
            ("Journal", ft.Icons.AUTO_STORIES_ROUNDED, "#C77DFF", open_journal),
            ("Run/Walk", ft.Icons.DIRECTIONS_RUN_ROUNDED, "#FF8A5B", open_run),
            ("Farm", ft.Icons.PARK_ROUNDED, "#06D6A0", open_grove),
        ]

        action_chips: list[ft.Control] = []
        for label, icon, color, handler in actions:
            action_chips.append(
                ft.Container(
                    ft.Column(
                        [
                            ft.Container(
                                ft.Icon(icon, size=20, color=color),
                                width=42,
                                height=42,
                                border_radius=Radius.MD,
                                bgcolor=C.a(color, 0.15),
                                alignment=ft.Alignment(0, 0),
                            ),
                            ft.Text(
                                label,
                                size=Type.CAPTION - 1,
                                weight=ft.FontWeight.W_600,
                                color=C.TEXT,
                                no_wrap=True,
                            ),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=4,
                    ),
                    padding=ft.Padding.symmetric(horizontal=8, vertical=6),
                    border_radius=Radius.MD,
                    bgcolor=C.a(C.SURFACE, 0.4),
                    on_click=handler,
                )
            )

        return common.card(
            ft.Column(
                [
                    ft.Row(
                        [
                            ft.Row(
                                [
                                    ft.Icon(ft.Icons.FLASH_ON_ROUNDED, color=C.GOLD, size=16),
                                    ft.Text(
                                        "QUICK RECORD",
                                        size=Type.CAPTION - 1,
                                        weight=ft.FontWeight.BOLD,
                                        color=C.GOLD,
                                    ),
                                ],
                                spacing=Space.XS,
                            ),
                            ft.Text("1-tap logging", size=Type.CAPTION - 2, color=C.TEXT_DIM),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Row(
                        action_chips,
                        alignment=ft.MainAxisAlignment.SPACE_AROUND,
                        spacing=Space.XS,
                    ),
                ],
                spacing=Space.SM,
            ),
            tint=C.GOLD,
            padding=Space.MD,
        )

    def _header(self, open_count: int) -> ui.SectionHeader:
        return ui.SectionHeader("Today's quests", count=open_count, action_text="Add",
                                on_action=self.open_add)

    def _card(self, q: Quest) -> ui.QuestCard:
        g, today = self.app.game, self.app.today()
        return ui.QuestCard(
            q.title, path_id=q.path_id, xp=q.xp, coins=q.coins, done=g.is_done(q, today),
            streak=g.streak(q, today), kind=q.kind, note=q.note,
            on_complete=lambda card, qid=q.id: self._complete(qid, card), data=q.id,
            on_long_press=lambda e, qid=q.id: editors.edit_quest(self.app, qid, self._edited),
            menu=editors.quest_menu(self.app, q.id, on_edited=self._edited),
        )

    def _rerender(self) -> None:
        if self.app.tab == 0:
            self.render()
            ui.refresh(self.list)

    def _skip_energy(self) -> None:
        self.energy_skipped = self.app.today()
        self._rerender()

    def _edited(self) -> None:
        if self.app.tab == 0:
            self.render()
            ui.refresh(self.list)

    # ------------------------------------------------------------------ next steps
    def _next_steps(self) -> list[ft.Control]:
        """The next step of every running (unpaused) side quest, nearest target date first."""
        rows = self.app.game.today_next_steps(self.app.today())
        if not rows:
            return []
        out: list[ft.Control] = [ui.SectionHeader("Next steps", count=len(rows),
                                                  action_text="Chains",
                                                  on_action=lambda e: self.app.go(1))]
        out += [self._step_row(sq, i, st) for sq, i, st in rows]
        return out

    def _step_row(self, sq, index: int, step) -> ft.Control:
        pc = th.path_color(sq.path_id)
        check = ft.Icon(ft.Icons.RADIO_BUTTON_UNCHECKED, size=Size.ICON, color=pc, scale=1,
                        animate_scale=Motion.anim(Motion.POP_MS * 2, Motion.BACK))
        sub = f"{sq.skill_name} · step {index + 1} of {len(sq.steps)}"
        if sq.target_date:
            sub += f" · by {common.short_date(date.fromisoformat(sq.target_date))}"
        step_tip = f"{step.title}\n{step.note}" if step.note else step.title
        col_items: list[ft.Control] = [
            ft.Text(step.title, size=Type.BODY, weight=ft.FontWeight.W_600,
                    color=C.TEXT, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS,
                    tooltip=step_tip),
        ]
        if step.note:
            col_items.append(ft.Text(step.note, size=Type.CAPTION, color=C.TEXT_DIM,
                                     max_lines=2, overflow=ft.TextOverflow.ELLIPSIS,
                                     tooltip=step.note))
        col_items.append(ft.Text(sub, size=Type.CAPTION, color=C.TEXT_DIM, max_lines=1,
                                 overflow=ft.TextOverflow.ELLIPSIS))
        row = ft.Container(
            ft.Row([
                ui.path_avatar(th.path_icon(sq.path_id), pc, 36),
                ft.Column(col_items, spacing=1, expand=True, tight=True),
                ui.xp_chip(step.xp), check,
            ], spacing=Space.MD - 2, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            bgcolor=C.SURFACE_HI, border_radius=Radius.MD, border=ft.Border.all(1, C.a(pc, 0.3)),
            padding=ft.Padding.symmetric(horizontal=Space.MD, vertical=Space.SM + 2),
            scale=1, animate_scale=Motion.anim(Motion.POP_MS, Motion.BACK),
            animate_opacity=Motion.anim(Motion.DONE_FADE_MS), opacity=1,
            tooltip=step_tip,
        )

        async def tap(_: Any) -> None:
            g = self.app.game
            if not g.can_complete_step(sq.id, index):
                self.app.error("That step isn't open yet")
                return
            await ui.buzz("medium")
            check.icon, check.color, check.scale = ft.Icons.CHECK_CIRCLE, C.SUCCESS, 1.35
            row.scale, row.bgcolor = Motion.POP_SCALE, C.a(C.SUCCESS, 0.22)
            ui.refresh(row)
            await asyncio.sleep(Motion.POP_MS / 1000)
            row.scale, check.scale = 1, 1
            ui.refresh(row)
            await self.app.award(lambda: g.complete_step(sq.id, index, self.app.today()),
                                 cleared=step.title, at=pos.get("at"))
            await asyncio.sleep(0.6)
            if self.app.tab == 0:  # the chain's next step slides in
                self.render()
                ui.refresh(self.list)

        pos: dict[str, Any] = {}
        row.on_click = tap
        row.on_tap_down = lambda e: pos.update(at=ambient.card_center(e))
        ambient.apply_glass(row, "frost", tint=pc)
        row.border = ft.Border.all(1, C.a(pc, 0.3))
        return row

    def _bills_nudge(self) -> ft.Control | None:
        rows = self.app.game.bills_status(self.app.today())
        overdue = [b for b, s, _ in rows if s == "overdue"]
        soon = [b for b, s, _ in rows if s == "due_soon"]
        if not (overdue or soon):
            return None
        bills = overdue + soon
        names = ", ".join(b.name for b in bills[:2]) + (" +more" if len(bills) > 2 else "")
        total = sum(b.amount for b in bills)
        first, due = next((b, d) for b, s, d in rows if b is bills[0])
        days = (due - self.app.today()).days
        when = ("is due today" if days == 0 else "is due tomorrow" if days == 1
                else f"is due in {days} days" if days > 1
                else f"was due {common.short_date(due)}")
        more = f" (+{len(bills) - 1} more)" if len(bills) > 1 else ""
        title = voice.say("bill_due", bill=first.name + more, when=when)
        if not self.bill_voiced:
            from lol.ui.app import clip_for  # local: app imports this module

            self.bill_voiced = True
            sfx.play("alert_soft", 0.8)
            ui.voice(clip_for("bill_due", title))
        color = C.DANGER if overdue else C.ACCENT
        return ft.Container(
            ft.Row([
                ft.Icon(ft.Icons.RECEIPT_LONG, color=color, size=22),
                ft.Column([
                    ft.Text(spans=ui.lead_spans(title, color=color), size=Type.BODY,
                            weight=ft.FontWeight.W_600, color=C.TEXT),
                    ft.Text(f"{names} · {ui.peso(total)}", size=Type.CAPTION,
                            color=C.TEXT_DIM, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                ], spacing=2, expand=True, tight=True),
                ft.Icon(ft.Icons.CHEVRON_RIGHT, color=C.TEXT_DIM),
            ], spacing=Space.MD, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            bgcolor=C.a(color, 0.10), border=ft.Border.all(1, C.a(color, 0.35)),
            border_radius=Radius.MD, padding=ft.Padding.symmetric(horizontal=Space.MD,
                                                                  vertical=Space.SM + 2),
            on_click=lambda e: self.app.open_sub("bills"), ink=True,
        )

    # ------------------------------------------------------------------ actions
    async def _complete(self, quest_id: str, card: Any = None) -> bool:
        g, today = self.app.game, self.app.today()
        await self.app.award(lambda: g.complete_quest(quest_id, today),
                             cleared=g.quest(quest_id).title,
                             at=getattr(card, "tap_pos", None))
        open_count = sum(1 for q in g.quests if not g.is_done(q, today))
        if self.app.tab == 0 and len(self.list.controls) > self._header_at:
            self.list.controls[self._header_at] = self._header(open_count)
            ui.refresh(self.list)
        if not open_count:
            # last one: let the card settle, then show the "all done" state
            await asyncio.sleep(0.9)
            if self.app.tab == 0:
                self.render()
                ui.refresh(self.list)
        return True

    def open_add(self, _: Any = None) -> None:
        open_quest_sheet(self.app, on_added=lambda q: self._added(q))

    def _added(self, q: Quest) -> None:
        self.render()
        ui.refresh(self.list)
        self.app.toast(f"Added: {q.title}", ft.Icons.ADD_TASK)


def open_quest_sheet(app: App, *, on_added, with_difficulty: bool = False) -> None:
    """Bottom sheet: title, Path, once/daily (+ difficulty on the Quests tab)."""
    state = {"path": "warrior", "kind": "once", "diff": "1"}
    title = common.text_field("What's the quest?", autofocus=True)
    paths = common.ChoicePills(common.path_options(), state["path"],
                               on_change=lambda v: state.update(path=v))
    kind = common.segmented([("once", "Once"), ("daily", "Daily")], "once",
                            on_change=lambda v: state.update(kind=v))
    diff = common.segmented([("1", "Easy"), ("2", "Medium"), ("3", "Hard")], "1",
                            on_change=lambda v: state.update(diff=v))
    note = common.text_field("Note (optional)")

    def add(_: Any = None) -> None:
        text = (title.value or "").strip()
        if not text:
            sfx.play("error_soft")
            title.error_text = "Give it a short name"
            title.update()
            return
        q = app.game.add_quest(text, state["path"], kind=state["kind"],
                               difficulty=int(state["diff"]), note=(note.value or "").strip(),
                               today=app.today())
        app.save()
        sfx.play("objective_new")
        common.close(sheet)
        on_added(q)

    title.on_submit = add
    body: list[ft.Control] = [title, common.hint("Path"), paths, common.hint("How often"), kind]
    if with_difficulty:
        body += [common.hint("Difficulty (more XP and coins)"), diff, note]
    body.append(ft.Row([common.primary_button("Add quest", add, icon=ft.Icons.ADD_TASK)]))

    def from_template(_: Any = None) -> None:
        common.close(sheet)
        app.open_sub("templates")

    body.append(ft.TextButton("Start from a template", icon=ft.Icons.LIBRARY_BOOKS,
                              on_click=common.with_sound(from_template), height=Size.TAP,
                              style=ft.ButtonStyle(color=C.PRIMARY)))
    sheet = common.open_sheet(app.page, "New quest", body)
