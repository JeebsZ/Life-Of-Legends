"""More tab: a grid of icon tiles (GCash-style services) that open sub-screens on an in-app
stack with a back arrow and slide transitions.

Sub-screen protocol (duck-typed): `title`, `view` (a Control), `render()`; optional `fab`,
`prepare(**kw)` (called before render when opened with arguments), `on_enter()` (after it is
on screen) and `on_leave()` (popped, or the user switched tabs)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import flet as ft

from lol.core import pins
from lol.ui import components as ui
from lol.ui import sfx
from lol.ui import theme as th
from lol.ui.screens import common
from lol.ui.theme import C, Motion, Radius, Space, Type

if TYPE_CHECKING:
    from lol.ui.app import App

# key: (label, icon, color role or hex)
TILES: dict[str, tuple[str, ft.IconData, str]] = {
    "profile": ("Profile", ft.Icons.PERSON, C.PRIMARY),
    "skills": ("Skills", ft.Icons.ACCOUNT_TREE, "#A78BFA"),
    "achievements": ("Achievements", ft.Icons.EMOJI_EVENTS, "#F5C66B"),
    "report": ("Luma Report", ft.Icons.INSIGHTS, "#4FE3F0"),
    "calendar": ("Calendar", ft.Icons.CALENDAR_MONTH, "#5EEAB0"),
    "bills": ("Bills", ft.Icons.RECEIPT_LONG, "#F5B94A"),
    "focus": ("Focus Timer", ft.Icons.TIMER, "#FFB347"),
    "templates": ("Templates", ft.Icons.LIBRARY_BOOKS, "#7FB2FF"),
    "logbook": ("Logbook", ft.Icons.BOOK, "#F08CB4"),
    "backup": ("Backup & Export", ft.Icons.BACKUP, "#9FD3C7"),
    "settings": ("Settings", ft.Icons.SETTINGS, "#B9C3D6"),
    "workout": ("Workout", ft.Icons.FITNESS_CENTER, "#FF6F91"),
    "sleep": ("Sleep", ft.Icons.NIGHTLIGHT, "#A78BFA"),
    "water": ("Water", ft.Icons.WATER_DROP, "#5EC8F2"),
    "energy": ("Energy", ft.Icons.BOLT, "#FFB347"),
    "insights": ("Insights", ft.Icons.QUERY_STATS, "#84A98C"),
    "body": ("Body", ft.Icons.MONITOR_WEIGHT, "#6EE7B7"),
    "meals": ("Meals", ft.Icons.RESTAURANT, "#FFB86B"),
    "run": ("Run", ft.Icons.DIRECTIONS_RUN, "#FF8A5B"),
    "study": ("Study", ft.Icons.STYLE, "#8EA2FF"),
    "premium": ("Premium", ft.Icons.WORKSPACE_PREMIUM, "#F5C66B"),
}
MODULE_TILES = {"workout", "sleep", "water", "energy", "insights", "body", "meals", "run"}  # hidden when switched off
SECTIONS = (
    ("You", ("profile", "skills", "achievements", "report")),
    ("Track", ("workout", "run", "sleep", "water", "energy", "body", "meals", "insights")),
    ("Plan & focus", ("bills", "calendar", "focus", "study", "templates", "logbook")),
    ("Data & app", ("backup", "settings", "premium")),
)
COMING_SOON = {"achievements"}
SLIDE = 0.18  # slide distance (fraction of the width)


def _make(app: App, key: str) -> Any:
    """Sub-screens are created lazily, once, and kept (the focus timer keeps its state)."""
    if key == "profile":
        from lol.ui.screens.profile import ProfileScreen
        return ProfileScreen(app)
    if key == "skills":
        from lol.ui.screens.skills import SkillsScreen
        return SkillsScreen(app)
    if key == "report":
        from lol.ui.screens.report import ReportScreen
        return ReportScreen(app)
    if key == "calendar":
        from lol.ui.screens.calendar import CalendarScreen
        return CalendarScreen(app)
    if key == "bills":
        from lol.ui.screens.bills import BillsScreen
        return BillsScreen(app)
    if key == "focus":
        from lol.ui.screens.focus import FocusScreen
        return FocusScreen(app)
    if key == "templates":
        from lol.ui.screens.templates import TemplatesScreen
        return TemplatesScreen(app)
    if key == "logbook":
        from lol.ui.screens.logbook import LogbookScreen
        return LogbookScreen(app)
    if key == "backup":
        from lol.ui.screens.backup import BackupScreen
        return BackupScreen(app)
    if key == "workout":
        from lol.ui.screens.workout import WorkoutScreen
        return WorkoutScreen(app)
    if key == "run":
        from lol.ui.screens.run import RunScreen
        return RunScreen(app)
    if key == "sleep":
        from lol.ui.screens.sleep import SleepScreen
        return SleepScreen(app)
    if key == "water":
        from lol.ui.screens.water import WaterScreen
        return WaterScreen(app)
    if key == "energy":
        from lol.ui.screens.energy import EnergyScreen
        return EnergyScreen(app)
    if key == "insights":
        from lol.ui.screens.insights import InsightsScreen
        return InsightsScreen(app)
    if key == "body":
        from lol.ui.screens.health import BodyScreen
        return BodyScreen(app)
    if key == "meals":
        from lol.ui.screens.meal import MealScreen
        return MealScreen(app)
    if key == "meal_review":  # not a tile: the meal confirm/edit screen
        from lol.ui.screens.meal import MealReviewScreen
        return MealReviewScreen(app)
    if key.startswith("study"):  # study, study_deck, study_drafts, study_run
        from lol.ui.screens.study import make
        return make(app, key)
    if key == "premium":
        from lol.ui.screens.premium import PremiumScreen
        return PremiumScreen(app)
    if key == "settings":
        from lol.ui.screens.settings import SettingsScreen
        return SettingsScreen(app)
    raise KeyError(key)


class MoreScreen:
    TAB = 4  # app.TAB_MORE: the bottom-nav index this stack host is shown under

    def __init__(self, app: App) -> None:
        self.app = app
        self.stack: list[str] = []
        self.subs: dict[str, Any] = {}
        self.pending: dict[str, object] = {}
        self.grid = common.screen_list()
        self.host = ft.Container(self.grid, expand=True, offset=ft.Offset(0, 0), opacity=1)
        self.view = ft.Container(self.host, expand=True, key="more")

    # ------------------------------------------------------------------ stack
    @property
    def fab(self) -> ft.Control | None:
        top = self._top()
        return getattr(top, "fab", None) if top is not None else None

    def _top(self) -> Any:
        return self.sub(self.stack[-1]) if self.stack else None

    def sub(self, key: str) -> Any:
        if key not in self.subs:
            self.subs[key] = _make(self.app, key)
        return self.subs[key]

    def reset(self, key: str | None = None, **kw: object) -> None:
        """Set the stack before the More tab is shown (app.open_sub from another tab)."""
        top = self._top()
        if top is not None and self.app.tab == self.TAB:
            getattr(top, "on_leave", lambda: None)()
        self.stack = [key] if key else []
        self.pending = dict(kw)

    def render(self) -> None:
        """Called by the app when the More tab is shown: draw the top of the stack."""
        self.host.content = self._content()
        self.host.offset, self.host.opacity = ft.Offset(0, 0), 1
        self.app.page.run_task(self._entered)

    async def _entered(self) -> None:
        await asyncio.sleep(0.05)
        top = self._top()
        if top is not None and self.app.tab == self.TAB:
            getattr(top, "on_enter", lambda: None)()

    def on_leave(self) -> None:
        top = self._top()
        if top is not None:
            getattr(top, "on_leave", lambda: None)()

    def _content(self) -> ft.Control:
        top = self._top()
        if top is None:
            self._render_grid()
            return self.grid
        if self.pending and hasattr(top, "prepare"):
            top.prepare(**self.pending)
        self.pending = {}
        top.render()
        return ft.Column([common.back_bar(top.title, self.back,
                                          trailing=getattr(top, "trailing", None)),
                          ft.Container(top.view, expand=True)], spacing=0, expand=True)

    def open(self, key: str, **kw: object) -> None:
        if key in COMING_SOON:
            sfx.play("error_soft")
            self.app.toast("Achievements are coming soon. Your effort is already counted.",
                           ft.Icons.EMOJI_EVENTS)
            return
        current = self._top()
        if current is not None:
            getattr(current, "on_leave", lambda: None)()
        sfx.play("tab_open")
        self.stack.append(key)
        self.pending = dict(kw)
        self.app.page.run_task(self._slide, 1)

    def back(self) -> None:
        if not self.stack:
            return
        sfx.play("back")
        top = self._top()
        getattr(top, "on_leave", lambda: None)()
        self.stack.pop()
        self.app.page.run_task(self._slide, -1)

    async def _slide(self, direction: int) -> None:
        """New content slides in from the right (open) or the left (back)."""
        h = self.host
        h.animate_offset = h.animate_opacity = ui.SNAP
        h.content = self._content()
        h.offset, h.opacity = ft.Offset(SLIDE * direction, 0), 0
        self.app.refresh_fab()
        self.app.page.update()
        await asyncio.sleep(0.02)
        h.animate_offset = Motion.anim(260, Motion.EASE_CUBIC)
        h.animate_opacity = Motion.anim(200)
        h.offset, h.opacity = ft.Offset(0, 0), 1
        ui.refresh(h)
        await self._entered()

    def refresh_top(self) -> None:
        """Re-render the visible sub-screen in place (after a sheet saved something)."""
        if self.stack and self.app.tab == self.TAB:
            self.host.content = self._content()
            ui.refresh(self.host)

    # ------------------------------------------------------------------ grid
    def _render_grid(self) -> None:
        items: list[ft.Control] = []
        for title, all_keys in SECTIONS:
            keys = [k for k in all_keys
                    if k not in MODULE_TILES or self.app.game.module_on(k)]
            if not keys:
                continue
            items.append(ft.Container(
                ft.Text(th.label(title), size=Type.CAPTION, weight=ft.FontWeight.BOLD,
                        color=C.TEXT_DIM, style=ft.TextStyle(letter_spacing=th.label_spacing())),
                padding=ft.Padding.only(left=Space.XS, top=Space.SM)))
            items.append(common.card(ft.ResponsiveRow(
                [self._tile(k) for k in keys], spacing=Space.XS, run_spacing=Space.MD),
                padding=Space.MD))
        items.append(ft.Container(common.hint("LUMA: Your Lifestyle QoL · saved on this device"),
                                  alignment=ft.Alignment.CENTER, padding=Space.MD))
        self.grid.controls = items

    def _tile(self, key: str) -> ft.Control:
        label, icon, color = TILES[key]
        soon = key in COMING_SOON
        square = ft.Container(
            ft.Icon(icon, size=26, color=C.a(color, 0.45) if soon else color),
            width=56, height=56, border_radius=Radius.MD + 2, alignment=ft.Alignment.CENTER,
            bgcolor=C.a(color, 0.08 if soon else 0.16),
            border=ft.Border.all(1, C.a(color, 0.2 if soon else 0.45)), scale=1,
            animate_scale=Motion.anim(Motion.POP_MS, Motion.BACK))
        badge = ft.Container(
            ft.Text("SOON", size=8, weight=ft.FontWeight.BOLD, color=C.TEXT_DIM),
            bgcolor=C.SURFACE_HI, border_radius=Radius.PILL, right=0, top=0,
            padding=ft.Padding.symmetric(horizontal=4, vertical=1), visible=soon)
        lock = ft.Container(ft.Icon(ft.Icons.LOCK, size=12, color=C.TEXT_DIM), left=2, bottom=2,
                            visible=soon)
        overdue = self.app.overdue_bills() if key == "bills" else 0
        alert = ft.Container(  # overdue bills: red dot (count) on the Bills tile
            ft.Text(str(overdue), size=9, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
            bgcolor=C.DANGER, border_radius=Radius.PILL, right=0, top=0, visible=overdue > 0,
            padding=ft.Padding.symmetric(horizontal=5, vertical=1))

        async def tap(_: Any) -> None:
            await ui.pop(square, 1.1)
            self.open(key)

        return ft.Container(
            ft.Column([
                ft.Stack([square, badge, lock, alert], width=62, height=58),
                ft.Text(label, size=Type.CAPTION if len(label) < 12 else 11,
                        color=C.TEXT_DIM if soon else C.TEXT,
                        weight=ft.FontWeight.W_600, text_align=ft.TextAlign.CENTER,
                        max_lines=2, overflow=ft.TextOverflow.ELLIPSIS,
                        style=ft.TextStyle(height=1.15)),
            ], spacing=Space.XS, tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            col=3, on_click=tap, ink=False, data=key,
            padding=ft.Padding.only(top=2, bottom=2),
        )


# ---------------------------------------------------------------------- center slot (v1.5)


def pinnable_keys(app: App) -> list[str]:
    """Every More feature the center nav slot can hold, in grid order: built from SECTIONS, so
    a new tile is pinnable automatically; coming-soon tiles and modules switched off in
    Settings are left out."""
    keys = [k for _, ks in SECTIONS for k in ks]
    return pins.pinnable(keys, module_on=app.game.module_on, exclude=COMING_SOON | {"premium"})


def pin_picker(app: App, on_pick: Callable[[str], Any], *,
               title: str = "Pin to the middle button") -> None:
    """Sheet: a grid of every pinnable feature; the current pin is ringed. on_pick(key)."""
    current = pins.active_pin(app.game.profile, pinnable_keys(app))
    sheet: ft.BottomSheet | None = None

    def choose(key: str) -> Callable[[Any], Any]:
        async def tap(_: Any) -> None:
            if sheet is not None:
                common.close(sheet)
            on_pick(key)
        return tap

    tiles: list[ft.Control] = []
    for key in pinnable_keys(app):
        label, icon, color = TILES[key]
        mine = key == current
        tiles.append(ft.Container(
            ft.Column([
                ft.Container(ft.Icon(ft.Icons.CHECK if mine else icon, size=24, color=color),
                             width=52, height=52, border_radius=Radius.MD + 2,
                             alignment=ft.Alignment.CENTER, bgcolor=C.a(color, 0.16),
                             border=ft.Border.all(2 if mine else 1,
                                                  C.a(color, 0.95 if mine else 0.45))),
                ft.Text(label, size=11, color=C.TEXT, weight=ft.FontWeight.W_600,
                        text_align=ft.TextAlign.CENTER, max_lines=2,
                        overflow=ft.TextOverflow.ELLIPSIS, style=ft.TextStyle(height=1.15)),
            ], spacing=Space.XS, tight=True,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            col=3, on_click=choose(key), data=f"pin:{key}", ink=False,
            padding=ft.Padding.only(top=2, bottom=2)))
    sheet = common.open_sheet(app.page, title, [
        common.hint("Your favorite feature, one tap away in the middle of the bar. "
                    "Hold the middle button to unpin it."),
        ft.ResponsiveRow(tiles, spacing=Space.XS, run_spacing=Space.MD),
    ])


class CenterScreen(MoreScreen):
    """The center nav slot's own stack: the pinned feature is its root (same sub-screen
    instances as More, so e.g. a running focus timer is the one you see from either place).
    Back at the root returns to the tab you came from."""

    TAB = 2  # app.TAB_CENTER

    def __init__(self, app: App) -> None:
        super().__init__(app)
        self.view.key = "center"
        self.root: str | None = None

    def sub(self, key: str) -> Any:
        return self.app.screens[MoreScreen.TAB].sub(key)  # shared with More

    def show(self, key: str, **kw: object) -> None:
        """Make `key` the root (a new pin, or re-tapping the slot pops back to it)."""
        if self.root != key or len(self.stack) != 1 or kw:
            self.reset(key, **kw)
        self.root = key

    def _content(self) -> ft.Control:
        if not self.stack:  # nothing pinned (only reachable mid-unpin): calm placeholder
            return ft.Container(common.empty_card(
                "Middle button is empty", "Tap it to pin a feature.", ft.Icons.ADD_CIRCLE),
                padding=Space.GUTTER)
        return super()._content()

    def back(self) -> None:
        if len(self.stack) > 1:
            super().back()
            return
        sfx.play("back")
        self.app.go(self.app.prev_tab)
