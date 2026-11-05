"""Side quests on the Quests tab: active chain cards, the preset catalog sheet (by Path), the
"Make your own" sheet and set-aside. Draw + wire only: rules live in Game."""

from __future__ import annotations

import asyncio
from datetime import date
from typing import TYPE_CHECKING, Any

import flet as ft

from lol.core.models import RANK_NAMES, CatalogChain, CatalogStep, SideQuest
from lol.ui import ads, sfx, voice
from lol.ui import components as ui
from lol.ui import theme as th
from lol.ui.screens import common, editors
from lol.ui.theme import C, Motion, Radius, Size, Space, Type

if TYPE_CHECKING:
    from lol.ui.app import App

MAX_STEPS = 5
# Luma's staged analysis: starting a preset chain, and drafting custom steps
CHAIN_STAGES = ("READING THE CHAIN…", "PLOTTING STEPS…", "CHAIN READY")
DRAFT_STAGES = ("STUDYING THE SKILL…", "DRAFTING STEPS…", "STEPS READY")


class SideQuestsSection:
    """Builds the Side Quests block; `on_change()` asks the Quests screen to re-render."""

    def __init__(self, app: App, on_change) -> None:
        self.app, self.on_change = app, on_change
        self.catalog_path = "all"

    # ------------------------------------------------------------------ section
    def controls(self) -> list[ft.Control]:
        g = self.app.game
        active = g.side_quests(active_only=True)
        actions = ft.Row([
            self._action("Start a side quest", ft.Icons.ROUTE, self.open_catalog, True),
            self._action("Make your own", ft.Icons.EDIT_NOTE, self.open_custom, False),
        ], spacing=Space.SM)
        out: list[ft.Control] = [ui.SectionHeader("Side Quests", count=len(active))]
        if not active:
            out.append(common.card(ft.Column([
                ft.Row([ui.path_avatar(ft.Icons.MILITARY_TECH, C.PRIMARY, 40),
                        ft.Text("Three small steps, one new skill. Pick a chain and Luma "
                                "tracks it here.", size=Type.LABEL, color=C.TEXT_DIM,
                                expand=True)],
                       spacing=Space.MD, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                actions,
            ], spacing=Space.MD, tight=True), padding=Space.MD))
            return out
        out += [self._card(sq) for sq in active]
        out.append(actions)
        out.append(ft.Container(common.hint("Tap a step when it's done. The dots open order, "
                                            "target date, pause, skip and edit."),
                                alignment=ft.Alignment.CENTER))
        return out

    @staticmethod
    def _action(text: str, icon: ft.IconData, fn, primary: bool) -> ft.Control:
        fg = C.ON_PRIMARY if primary else C.PRIMARY
        return ft.Container(
            ft.Row([ft.Icon(icon, size=18, color=fg),
                    ft.Text(text, size=Type.LABEL, weight=ft.FontWeight.BOLD, color=fg,
                            no_wrap=True)],
                   spacing=Space.XS, tight=True, alignment=ft.MainAxisAlignment.CENTER),
            height=Size.TAP, expand=True, border_radius=Radius.PILL,
            alignment=ft.Alignment.CENTER, ink=True,
            bgcolor=C.PRIMARY if primary else C.a(C.PRIMARY, 0.12),
            on_click=lambda e: fn(),
        )

    def _card(self, sq: SideQuest) -> ui.SideQuestCard:
        g = self.app.game
        rank = sq.rank_target
        if rank <= 1:
            eyebrow = "Side quest · " + ("Custom" if sq.custom else RANK_NAMES[1])
        else:
            eyebrow = f"Rank up → {RANK_NAMES.get(rank, '')}"
        footer = (f"Finish every step: {sq.skill_name} "
                  f"{'unlocks' if rank <= 1 else 'ranks up'} · +{g.skill_bonus(sq)} bonus XP")
        if rank <= 1 and g.skill(sq.skill_name):
            footer = "You already know this skill. Steps still earn XP and coins."
        bits = []
        if sq.paused:
            eyebrow = "Paused · " + eyebrow
        if sq.ordered:
            bits.append("In order")
        if sq.target_date:
            bits.append(f"Target {common.short_date(date.fromisoformat(sq.target_date))}")
        if bits:
            footer = " · ".join(bits) + "\n" + footer
        steps = [(s.title + (" (skipped)" if s.skipped_on else ""), s.note, s.xp, s.coins,
                  s.resolved) for s in sq.steps]
        card = ui.SideQuestCard(
            sq.skill_name, path_id=sq.path_id, eyebrow=eyebrow, footer=footer, steps=steps,
            on_step=lambda card, i, sid=sq.id: self._complete(card, sid, i),
            on_menu=lambda card, sid=sq.id: self._manage(sid), data=sq.id,
        )
        if sq.paused:
            card.opacity = 0.7
        return card

    def _manage(self, sq_id: str) -> None:
        editors.manage_side_quest(self.app, sq_id, on_changed=self.on_change,
                                  on_set_aside=lambda: self._set_aside(sq_id))

    async def _complete(self, card: ui.SideQuestCard, sq_id: str, index: int) -> bool:
        g, today = self.app.game, self.app.today()
        if not g.can_complete_step(sq_id, index):
            sq = g.side_quest(sq_id)
            nxt = g.next_step(sq)
            if sq.paused:
                self.app.error("This chain is paused. Resume it from the dots menu.")
            elif nxt is not None:
                self.app.error(f"Steps go in order: do step {nxt + 1} first.")
            return False
        step_title = g.side_quest(sq_id).steps[index].title
        await self.app.award(lambda: g.complete_step(sq_id, index, today), cleared=step_title,
                             stinger="chain_step",
                             at=getattr(card, "tap_pos", None))
        if g.side_quest(sq_id).finished:
            async def swap_out() -> None:
                await asyncio.sleep(1.1)  # let the card celebrate first
                card.opacity, card.scale = 0, 0.96
                ui.refresh(card)
                await asyncio.sleep(Motion.DONE_FADE_MS / 1000)
                self.on_change()

            self.app.page.run_task(swap_out)
        return True

    async def _set_aside(self, sq_id: str) -> None:
        sq = self.app.game.side_quest(sq_id)
        ok = await common.confirm(
            self.app.page, "Set this side quest aside?",
            f"\"{sq.skill_name}\" leaves your list. XP and coins you've earned stay yours. "
            "You can pick it up again anytime.", "Set aside")
        if not ok:
            return
        self.app.game.abandon_side_quest(sq_id)
        self.app.save()
        self.app.lumen("side_quest_set_aside", ft.Icons.BEDTIME, skill=sq.skill_name)
        self.on_change()

    # ------------------------------------------------------------------ start (shared)
    def start(self, catalog_id: str, *, rank_up: bool = False) -> bool:
        """Start a preset or follow-up chain. False if it can't start now."""
        g = self.app.game
        if not g.can_start(catalog_id):
            self.app.toast("That chain is already running", ft.Icons.INFO_OUTLINE)
            return False
        sq = g.start_side_quest(catalog_id, self.app.today())
        self.app.save()
        kind = "rank_up_started" if rank_up else "side_quest_started"
        self.app.notice.say(voice.say(kind, skill=sq.skill_name), ft.Icons.ROUTE,
                            ("quest_accepted", 1))  # "Confirmed. Proposal accepted."
        self.app.page.run_task(self.app.reveal, sq.skill_name,
                               "Rank-up chain started" if rank_up else "Side quest started")
        return True

    # ------------------------------------------------------------------ catalog sheet
    def open_catalog(self) -> None:
        app = self.app
        listing = ft.Column(spacing=Space.SM, tight=True)

        def fill() -> None:
            pid = None if self.catalog_path == "all" else self.catalog_path
            chains = app.game.side_quest_catalog(pid)
            listing.controls = [self._chain_tile(c, sheet_ref) for c in chains] or [
                common.hint("No chains for this Path yet.")]

        def set_path(v: str) -> None:
            self.catalog_path = v
            fill()
            ui.refresh(listing)

        sheet_ref: list[ft.BottomSheet] = []
        pills = common.ChoicePills(common.path_options(include_all=True), self.catalog_path,
                                   on_change=set_path, grid_cols=0)
        fill()
        sheet = common.open_sheet(app.page, "Start a side quest", [
            common.hint("Each chain is three small steps. Finish them to unlock the skill."),
            pills, listing,
        ])
        sheet_ref.append(sheet)

    def _chain_tile(self, c: CatalogChain, sheet_ref: list[ft.BottomSheet]) -> ft.Control:
        g = self.app.game
        pc = th.path_color(c.path_id)
        running = any(sq.active and sq.catalog_id == c.id for sq in g.side_quests())
        known = g.skill(c.skill_name) is not None
        can = g.can_start(c.id)
        steps = [ft.Row([
            ft.Container(ft.Text(str(i + 1), size=Type.CAPTION, weight=ft.FontWeight.BOLD,
                                 color=pc), width=22, height=22, border_radius=11,
                         bgcolor=C.a(pc, 0.16), alignment=ft.Alignment.CENTER),
            ft.Text(s.title, size=Type.LABEL, color=C.TEXT, expand=True),
        ], spacing=Space.SM) for i, s in enumerate(c.steps)]
        if running:
            label, icon = "In progress", ft.Icons.HOURGLASS_TOP
        elif known:
            label, icon = "Acquired", ft.Icons.CHECK
        else:
            label, icon = "Start", ft.Icons.PLAY_ARROW

        async def go(_: Any = None) -> None:
            if not can:
                await ui.buzz("select")
                await ui.nudge(btn)
                return
            await ui.buzz("medium")
            await ui.pop(btn, 1.1)
            if sheet_ref:  # overlays draw under sheets: step out while Luma thinks
                common.close(sheet_ref[0])
            await ui.lumen_analyze(self.app.page, CHAIN_STAGES, seconds=2.2)
            if self.start(c.id):
                self.on_change()

        btn = ft.Container(
            ft.Row([ft.Icon(icon, size=18, color=C.ON_PRIMARY if can else C.TEXT_DIM),
                    ft.Text(label, size=Type.LABEL, weight=ft.FontWeight.BOLD,
                            color=C.ON_PRIMARY if can else C.TEXT_DIM)],
                   spacing=Space.XS, tight=True, alignment=ft.MainAxisAlignment.CENTER),
            height=40, border_radius=Radius.PILL, alignment=ft.Alignment.CENTER,
            padding=ft.Padding.symmetric(horizontal=Space.LG),
            bgcolor=pc if can else C.a(C.TEXT, 0.08), on_click=go, scale=1,
            animate_scale=Motion.anim(Motion.POP_MS, Motion.BACK),
        )
        return ft.Container(ft.Column([
            ft.Row([ui.PathBadge(c.path_id), ft.Container(expand=True), btn],
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Text(c.skill_name, size=Type.TITLE, weight=ft.FontWeight.BOLD, color=C.TEXT),
            common.hint(c.blurb) if c.blurb else ft.Container(),
            ft.Column(steps, spacing=Space.XS + 2, tight=True),
        ], spacing=Space.SM, tight=True), bgcolor=C.SURFACE_HI, border_radius=Radius.MD,
            padding=Space.MD, border=ft.Border.all(1, C.a(pc, 0.3)),
            opacity=1 if can else 0.75)

    def _chain_cap(self) -> None:
        """Free keeps a few custom chains running at once (preset chains are never limited)."""
        from lol.core.premium import ACTIVE_CAPS, PREMIUM_NAME

        app = self.app
        sfx.play("error_soft")
        app.offer_premium("limit")
        cap = ACTIVE_CAPS["custom_chains"][0]

        def premium(_: object = None) -> None:
            common.close(sheet)
            app.open_sub("premium")

        def presets(_: object = None) -> None:
            common.close(sheet)
            self.open_catalog()

        sheet = common.open_sheet(app.page, f"{cap} custom side quests are running", [
            common.hint(f"Free keeps {cap} of your own chains going at a time. Finish or "
                        "abandon one to make another. Preset chains are always open."),
            ft.Row([common.secondary_button("Browse preset chains", presets,
                                            icon=ft.Icons.ROUTE)]),
            ft.Row([common.secondary_button(f"See {PREMIUM_NAME} (unlimited)", premium,
                                            icon=ft.Icons.WORKSPACE_PREMIUM,
                                            color="#F5C66B")]),
        ])

    # ------------------------------------------------------------------ custom sheet
    def open_custom(self) -> None:
        app = self.app
        if not app.game.can_add_custom_chain(app.today()):
            self._chain_cap()
            return
        state: dict = {"path": "scholar", "diff": "1", "ordered": False, "target": None}
        name = common.text_field("Skill name (e.g. Guitar Basics)", autofocus=True)
        name.capitalization = ft.TextCapitalization.WORDS
        name.max_length = 40
        paths = common.ChoicePills(common.path_options(), state["path"],
                                   on_change=lambda v: state.update(path=v))
        diff = common.segmented([("1", "Easy"), ("2", "Medium"), ("3", "Hard")], "1",
                                on_change=lambda v: state.update(diff=v))
        fields: list[ft.TextField] = []
        steps_col = ft.Column(spacing=Space.SM, tight=True)
        add_btn = ft.TextButton("Add a step", icon=ft.Icons.ADD_CIRCLE_OUTLINE,
                                height=Size.TAP, style=ft.ButtonStyle(color=C.PRIMARY))
        error = ft.Text("", size=Type.CAPTION, color=C.DANGER, visible=False)

        def paint_steps() -> None:
            rows: list[ft.Control] = []
            for i, f in enumerate(fields):
                f.label = f"Step {i + 1}"
                rows.append(ft.Row([
                    ft.Container(f, expand=True),
                    ft.IconButton(ft.Icons.REMOVE_CIRCLE_OUTLINE, icon_color=C.TEXT_DIM,
                                  tooltip="Remove step", width=Size.TAP, height=Size.TAP,
                                  visible=len(fields) > 1,
                                  on_click=lambda e, ff=f: remove(ff)),
                ], spacing=Space.XS, vertical_alignment=ft.CrossAxisAlignment.CENTER))
            steps_col.controls = rows
            add_btn.visible = len(fields) < MAX_STEPS

        def new_field(value: str = "", spec: CatalogStep | None = None) -> ft.TextField:
            f = common.text_field("Step")
            f.value = value
            f.max_length = 60
            f.data = spec  # generated step: keeps its note and difficulty
            return f

        ordered_row = common.switch_row("Steps in order", "Only the next step can be completed",
                                        False, lambda v: state.update(ordered=v),
                                        icon=ft.Icons.FORMAT_LIST_NUMBERED)
        ordered_switch = ordered_row.controls[-1]

        async def generate(_: Any = None) -> None:
            skill = (name.value or "").strip()
            if not skill:
                sfx.play("error_soft")
                name.error_text = "Name the skill first, then Luma drafts the steps"
                name.update()
                return
            name.error_text = None
            # the overlay effect sits under dialogs: step out of the sheet while Luma thinks
            common.close(sheet)
            if not await ads.limit_gate(app, "generate_steps", manual=lambda: None,
                                        manual_label="Type the steps myself"):
                if not app.showing("premium"):
                    common.reopen(app.page, sheet)
                return
            ads.spend(app, "generate_steps")
            specs = await ui.lumen_analyze(
                app.page, DRAFT_STAGES, lambda: app.game.generate_chain(skill, state["path"]),
                seconds=2.5)
            fields.clear()
            fields.extend(new_field(sp.title, sp) for sp in specs[:MAX_STEPS])
            state["ordered"] = True
            ordered_switch.value = True
            paint_steps()
            common.reopen(app.page, sheet)
            app.toast("Luma drafted the steps. Edit anything before saving.",
                      ft.Icons.AUTO_AWESOME)

        gen_btn = ft.Container(
            ft.Row([ft.Icon(ft.Icons.AUTO_AWESOME, size=18, color=C.PRIMARY),
                    ft.Text("Generate steps with Luma", size=Type.LABEL,
                            weight=ft.FontWeight.BOLD, color=C.PRIMARY)],
                   spacing=Space.XS, tight=True, alignment=ft.MainAxisAlignment.CENTER),
            height=Size.TAP, border_radius=Radius.PILL, alignment=ft.Alignment.CENTER,
            bgcolor=C.a(C.PRIMARY, 0.12), border=ft.Border.all(1, C.a(C.PRIMARY, 0.4)),
            ink=True, on_click=common.with_sound(generate))

        def add_step(_: Any = None) -> None:
            if len(fields) >= MAX_STEPS:
                return
            fields.append(new_field())
            paint_steps()
            ui.refresh(steps_col, add_btn)
            app.page.run_task(ui.buzz, "select")

        def remove(f: ft.TextField) -> None:
            if len(fields) > 1:
                fields.remove(f)
                paint_steps()
                ui.refresh(steps_col, add_btn)

        add_btn.on_click = add_step
        for _ in range(3):
            fields.append(new_field())
        paint_steps()

        def create(_: Any = None) -> None:
            skill = (name.value or "").strip()
            steps: list = []
            for f in fields:
                t = (f.value or "").strip()
                if not t:
                    continue
                spec = f.data
                steps.append(CatalogStep(t, spec.note, spec.difficulty)
                             if isinstance(spec, CatalogStep) else t)
            if not skill:
                sfx.play("error_soft")
                name.error_text = "Give the skill a short name"
                name.update()
                return
            name.error_text = None
            if not steps:
                sfx.play("error_soft")
                error.value, error.visible = "Add at least one step", True
                ui.refresh(error, name)
                return
            try:
                sq = app.game.add_side_quest(skill, state["path"], steps,
                                             difficulty=int(state["diff"]), today=app.today(),
                                             ordered=state["ordered"],
                                             target_date=state["target"])
            except ValueError as exc:
                error.value, error.visible = f"Couldn't make it: {exc}", True
                ui.refresh(error, name)
                return
            app.save()
            common.close(sheet)
            app.notice.say(voice.say("side_quest_made", skill=sq.skill_name),
                           ft.Icons.EDIT_NOTE, ("quest_accepted", 1))
            app.page.run_task(app.reveal, sq.skill_name, "Side quest started")
            self.on_change()

        sheet = common.open_sheet(app.page, "Make your own side quest", [
            name, common.hint("Path"), paths, gen_btn,
            common.hint(f"Steps (1–{MAX_STEPS}). Small and doable beats big and vague."),
            steps_col, add_btn, ordered_row,
            common.date_row(app.page, "Target", None, app.today(),
                            lambda d: state.update(target=d), clearable=True,
                            help_text="A soft goal, never a penalty"),
            common.hint("Difficulty for steps you type (more XP and coins)"), diff, error,
            ft.Row([common.primary_button("Create side quest", create, icon=ft.Icons.ROUTE)]),
        ])
