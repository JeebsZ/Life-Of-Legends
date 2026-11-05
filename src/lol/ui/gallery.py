"""Component gallery - every component in its states, fake data, live theme switcher.

Run:  .venv/Scripts/flet run src/lol/ui/gallery.py
Web:  .venv/Scripts/flet run --web --port 8560 src/lol/ui/gallery.py
"""

from __future__ import annotations

import contextlib
import random
import sys
from pathlib import Path

if __package__ in (None, ""):  # run as a file: make `lol` importable
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import flet as ft

from lol.ui import components as ui
from lol.ui import theme as th
from lol.ui.theme import C, Space, Type

# --- fake data (the gallery owns no game rules; this mimics progression.bar_steps) ---


def _need(level: int) -> int:
    return round(100 * 1.25 ** (level - 1))


def _steps(level: int, xp: int, amount: int) -> tuple[list[float], int, int]:
    steps, xp = [], xp + amount
    while xp >= _need(level):
        xp -= _need(level)
        level += 1
        steps.append(1.0)
    steps.append(xp / _need(level))
    return steps, level, xp


CATALOG = [
    {"title": "Cook a new vegetable dish", "path_id": "chef", "xp": 30, "coins": 6,
     "difficulty": 2, "note": "Bonus if it's from a recipe you've never tried."},
    {"title": "20 push-ups, any time today", "path_id": "warrior", "xp": 20, "coins": 4,
     "difficulty": 1},
    {"title": "Read one chapter", "path_id": "scholar", "xp": 25, "coins": 5, "difficulty": 1},
    {"title": "Sketch for 15 minutes", "path_id": "artisan", "xp": 25, "coins": 5,
     "difficulty": 2},
    {"title": "Walk 5,000 steps outside", "path_id": "ranger", "xp": 35, "coins": 7,
     "difficulty": 2},
    {"title": "Review this week's spending", "path_id": "steward", "xp": 40, "coins": 8,
     "difficulty": 3, "note": "Just look - no judging."},
]


def main(page: ft.Page) -> None:
    page.title = "Life of Legends - Gallery"
    page.padding = 0
    with contextlib.suppress(Exception):  # web/mobile have no window to size
        page.window.width, page.window.height = 410, 860
    ui.use_haptics(ft.HapticFeedback())
    th.apply_theme(page, th.DEFAULT_THEME, update=False)

    hero = {"level": 4, "xp": 60, "coins": 135}
    paths = {pid: {"level": 1 + i % 3, "xp": 20 * i} for i, pid in enumerate(th.PATH_IDS)}

    banner = ui.LevelUpBanner()
    page.overlay.append(banner)

    # --- header: XP bar + floaters + coins ---
    xp_bar = ui.XpBar(hero["xp"] / _need(hero["level"]), level=hero["level"],
                      caption=f"{hero['xp']} / {_need(hero['level'])} XP",
                      on_rollover=lambda lvl: banner.show(lvl))
    xp_float = ui.FloatingGain(right=0, top=0)
    coin_float = ui.FloatingGain(right=0, top=26)
    coins = ui.CoinCounter(hero["coins"])
    header = ft.Container(
        content=ft.Stack([
            ft.Column([
                ft.Row([ft.Text("Jarvin", size=Type.DISPLAY, weight=ft.FontWeight.W_900,
                                color=C.TEXT), coins],
                       alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                xp_bar,
            ], spacing=Space.SM),
            xp_float, coin_float,
        ]),
        bgcolor=C.SURFACE, border_radius=th.Radius.LG, padding=Space.LG,
    )

    async def gain(xp: int, c: int = 0) -> None:
        steps, hero["level"], hero["xp"] = _steps(hero["level"], hero["xp"], xp)
        page.run_task(xp_float.xp, xp)
        if c:
            hero["coins"] += c
            page.run_task(coin_float.coins, c)
            page.run_task(coins.count_to, hero["coins"])
            for t in reward_tiles:
                t.set_coins(hero["coins"])
        await xp_bar.play(steps, caption=f"{hero['xp']} / {_need(hero['level'])} XP")

    # --- theme picker (rebuilt on switch so the selected ring moves) ---
    owned = {"ember", "ocean", "forest"}
    picker = ft.Row(spacing=Space.SM, alignment=ft.MainAxisAlignment.SPACE_AROUND)

    def build_picker() -> None:
        picker.controls = [
            ui.ThemeSwatch(tid, selected=tid == th.current().id, owned=tid in owned,
                           price=None if tid in owned else 300, on_select=switch)
            for tid in th.THEMES
        ]

    def switch(theme_id: str) -> None:
        if theme_id not in owned:
            owned.add(theme_id)  # gallery: unlocking is free
        th.apply_theme(page, theme_id, update=False)
        build_picker()
        page.update()

    build_picker()

    # --- quests ---
    def complete(card: ui.QuestCard):
        page.run_task(gain, card.xp, card.coins)

    def capped(card: ui.QuestCard) -> bool:
        page.show_dialog(ft.SnackBar(ft.Text("Demo: callback returned False -> reverted")))
        return False

    quests = [
        ui.QuestCard("Cook adobo for dinner", path_id="chef", xp=25, coins=5,
                     on_complete=complete),
        ui.QuestCard("Morning stretch", path_id="warrior", xp=15, coins=3, kind="daily",
                     streak=6, note="10 minutes is plenty", on_complete=complete),
        ui.QuestCard("Big one: finish the budget spreadsheet for the whole household",
                     path_id="steward", xp=300, coins=20, on_complete=complete),
        ui.QuestCard("Read 10 pages", path_id="scholar", xp=20, coins=4, kind="daily",
                     done=True, streak=12),
        ui.QuestCard("Rejected tap (reverts)", path_id="artisan", xp=10, coins=2,
                     on_complete=capped),
    ]

    # --- quest board ---
    async def reroll(_card):
        return random.choice(CATALOG)

    def accept(card):
        page.show_dialog(ft.SnackBar(ft.Text("Quest added to Today")))
        return random.choice(CATALOG)

    board = ui.QuestSuggestionCard(**CATALOG[0], on_accept=accept, on_reroll=reroll,
                                   on_skip=reroll)

    # --- paths ---
    async def path_level_up(pid: str, level: int) -> None:
        await banner.show(level, title=f"{th.path_name(pid).upper()} LEVEL UP",
                          subtitle="New Path rank", color=th.path_color(pid),
                          icon=th.path_icon(pid))

    progress: dict[str, ui.PathProgress] = {}
    for pid in th.PATH_IDS:
        p = paths[pid]
        progress[pid] = ui.PathProgress(
            pid, level=p["level"], value=p["xp"] / _need(p["level"]),
            caption=f"{p['xp']} / {_need(p['level'])} XP",
            on_level_up=lambda lvl, pid=pid: path_level_up(pid, lvl))

    async def path_gain(pid: str, amount: int) -> None:
        p = paths[pid]
        steps, p["level"], p["xp"] = _steps(p["level"], p["xp"], amount)
        await progress[pid].play(steps, caption=f"{p['xp']} / {_need(p['level'])} XP")

    # --- bills ---
    bills = [
        ui.BillRow("Meralco", 2450.5, status="overdue", due_label="Due Nov 1",
                   repeat_label="Monthly", on_pay=lambda r: page.run_task(gain, 10)),
        ui.BillRow("PLDT Fiber", 1699, status="due_soon", due_label="Due Nov 6",
                   repeat_label="Monthly", on_pay=lambda r: page.run_task(gain, 10)),
        ui.BillRow("Netflix", 549, status="upcoming", due_label="Due Nov 21",
                   repeat_label="Monthly"),
        ui.BillRow("Car insurance", 18500, status="paid", due_label="Paid Oct 28",
                   repeat_label="Yearly"),
    ]

    # --- rewards ---
    def redeem(tile: ui.RewardTile) -> bool:
        if hero["coins"] < tile.cost:
            return False
        hero["coins"] -= tile.cost
        page.run_task(coins.count_to, hero["coins"])
        for t in reward_tiles:
            if t is not tile:
                t.set_coins(hero["coins"])
        tile.coins = hero["coins"]
        return True

    oc, fo = th.THEMES["ocean"], th.THEMES["royal"]
    reward_tiles = [
        ui.RewardTile("Jollibee meal", 100, coins=hero["coins"], icon=ft.Icons.FASTFOOD,
                      on_redeem=redeem),
        ui.RewardTile("New video game", 1200, coins=hero["coins"],
                      icon=ft.Icons.SPORTS_ESPORTS, on_redeem=redeem),
        ui.RewardTile("Ocean theme", 300, coins=hero["coins"], kind="theme",
                      swatch=[oc.primary, oc.bg], owned=True, active=False,
                      on_use=lambda t: switch("ocean")),
        ui.RewardTile("Royal theme", 120, coins=hero["coins"], kind="theme",
                      swatch=[fo.primary, fo.bg], on_redeem=redeem),
    ]

    def btn(label: str, handler, icon=None) -> ft.Control:
        return ft.OutlinedButton(label, icon=icon, on_click=handler, height=40,
                                 style=ft.ButtonStyle(color=C.PRIMARY))

    def section(title: str, *controls: ft.Control, **kw) -> list[ft.Control]:
        return [ui.SectionHeader(title, **kw), *controls]

    # ArcaneNavBar: tap a tab to move the highlight; tap the center slot to cycle
    # empty -> pinned (Focus) -> active; hold it to clear. More shows the overdue-bills dot.
    def nav_tab(i: int) -> None:
        nav.select(i)

    def nav_center(_=None) -> None:
        if not nav.slot.pinned:
            nav.slot.set_pin("Focus", ft.Icons.TIMER, "#FFB347")
        else:
            nav.select(ui.NAV_CENTER)
        page.run_task(nav.slot.pulse)

    def nav_hold(_=None) -> None:
        nav.slot.set_pin(None)
        nav.select(0)
        page.run_task(nav.slot.pulse, 0.88)

    nav = ui.ArcaneNavBar(0, on_select=nav_tab, on_center=nav_center, on_center_hold=nav_hold,
                          badges={4: True})
    page.bottom_appbar = nav
    page.run_task(nav.slot.spin)

    body = ft.ListView(
        expand=True, spacing=Space.SM,
        padding=ft.Padding.symmetric(vertical=Space.LG, horizontal=Space.GUTTER),
        controls=[
            ft.Text("Component gallery", size=Type.HEADLINE, weight=ft.FontWeight.W_900,
                    color=C.TEXT),
            picker,
            header,
            ft.Row([btn("+40 XP", lambda e: page.run_task(gain, 40)),
                    btn("+300 XP", lambda e: page.run_task(gain, 300, 15))], wrap=True),
            *section("Today's quests", *quests, count=len(quests), action_text="Add"),
            *section("Quest Board", board),
            *section("Paths",
                     ft.Row([ui.PathBadge(pid, level=paths[pid]["level"])
                             for pid in th.PATH_IDS], wrap=True, spacing=Space.SM,
                            run_spacing=Space.SM),
                     *progress.values(),
                     ft.Row([btn("Chef +80", lambda e: page.run_task(path_gain, "chef", 80)),
                             btn("Ranger +200",
                                 lambda e: page.run_task(path_gain, "ranger", 200))],
                            wrap=True)),
            *section("Bills", *bills,
                     trailing=ft.Text("₱23,198 due in 30 days", size=Type.CAPTION,
                                      color=C.TEXT_DIM)),
            *section("Rewards",
                     ft.ResponsiveRow([ft.Container(t, col=6) for t in reward_tiles],
                                      spacing=Space.SM, run_spacing=Space.SM)),
            *section("Empty states",
                     ft.Container(ui.EmptyState(
                         "All quests done!", "Rest counts too. Want a bonus quest?",
                         icon=ft.Icons.CELEBRATION, action_text="Give me a quest"),
                         bgcolor=C.SURFACE, border_radius=th.Radius.MD),
                     ft.Container(ui.EmptyState(
                         "No bills yet", "Add one and we'll keep an eye on due dates.",
                         icon=ft.Icons.RECEIPT_LONG, color=C.ACCENT),
                         bgcolor=C.SURFACE, border_radius=th.Radius.MD)),
            *section("Banners",
                     ft.Row([btn("Level up", lambda e: page.run_task(banner.show, 5)),
                             btn("Path level up",
                                 lambda e: page.run_task(path_level_up, "scholar", 3))],
                            wrap=True)),
            ft.Container(height=Space.XL),
        ],
    )
    page.add(ft.SafeArea(body, expand=True))


if __name__ == "__main__":
    ft.run(main)
