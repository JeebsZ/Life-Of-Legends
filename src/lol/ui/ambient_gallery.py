"""Ambient gallery - MindSpace behind glass panels laid out like the Today screen (fake data),
plus buttons for ParticleBurst, QuestCleared, staged LumenThinking, pulse, reduce mode, glass
quality and theme.

Run:  .venv/Scripts/flet run src/lol/ui/ambient_gallery.py
Web:  .venv/Scripts/flet run --web --port 8680 src/lol/ui/ambient_gallery.py
"""

from __future__ import annotations

import contextlib
import sys
from pathlib import Path

if __package__ in (None, ""):  # run as a file: make `lol` importable
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import flet as ft

from lol.ui import ambient as amb
from lol.ui import effects as fx
from lol.ui import theme as th
from lol.ui.theme import C, Radius, Space, Type

QUESTS = [
    ("Drink a glass of water", "ranger", ft.Icons.WATER_DROP, 10, 2),
    ("Read 10 pages", "scholar", ft.Icons.MENU_BOOK, 25, 5),
    ("20-minute walk", "warrior", ft.Icons.DIRECTIONS_WALK, 30, 6),
    ("Cook a simple dinner", "chef", ft.Icons.RESTAURANT, 35, 8),
    ("Log today's spending", "steward", ft.Icons.ACCOUNT_BALANCE_WALLET, 15, 3),
]
THEME_ORDER = ["arcane", "rose", "ocean", "ember", "forest", "royal"]


def chip(text: str, color: str) -> ft.Container:
    return ft.Container(ft.Text(text, size=11, weight=ft.FontWeight.W_700, color=color),
                        bgcolor=C.a(color, 0.14), border_radius=Radius.PILL,
                        padding=ft.Padding.symmetric(horizontal=8, vertical=2))


def main(page: ft.Page) -> None:
    page.title = "Life of Legends - Ambient"
    page.padding = 0
    page.spacing = 0
    with contextlib.suppress(Exception):
        page.window.width, page.window.height = 390, 844
    th.apply_theme(page, "arcane", update=False)

    space = amb.MindSpace()
    burst = amb.ParticleBurst()
    cleared = fx.QuestCleared()
    hum_log: list[str] = []
    thinking = fx.LumenThinking(on_start=lambda: hum_log.append("hum"))
    notice = fx.NoticeEmblem()
    seal = fx.MilestoneSeal()
    reveal = fx.IdentifyReveal()
    page.overlay.extend([notice, seal, reveal, burst, cleared, thinking])
    status = ft.Text("", size=11, color=C.TEXT_DIM)

    def say(text: str) -> None:
        status.value = text
        with contextlib.suppress(Exception):
            status.update()

    # ---------------------------------------------------------------- header (real blur)
    xp_fill = ft.Container(width=210, height=10, border_radius=5, bgcolor=C.PRIMARY,
                           shadow=ft.BoxShadow(blur_radius=8, color=C.a(C.PRIMARY, 0.6)))
    header = amb.glass(ft.Column([
        ft.Row([
            ft.Container(ft.Icon(ft.Icons.PERSON, color=C.PRIMARY, size=22), width=38,
                         height=38, border_radius=19, bgcolor=C.a(C.PRIMARY, 0.16),
                         alignment=ft.Alignment.CENTER),
            ft.Text("Aria", size=Type.HEADLINE, weight=ft.FontWeight.W_900, color=C.TEXT,
                    expand=True),
            ft.Container(ft.Row([ft.Icon(ft.Icons.TOLL, size=16, color=C.ACCENT),
                                 ft.Text("1,240", size=13, weight=ft.FontWeight.W_800,
                                         color=C.ACCENT)], spacing=4, tight=True),
                         bgcolor=C.a(C.ACCENT, 0.12), border_radius=Radius.PILL,
                         padding=ft.Padding.symmetric(horizontal=10, vertical=5)),
        ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        ft.Stack([ft.Container(height=10, border_radius=5, bgcolor=C.a(C.TEXT, 0.10)),
                  xp_fill], height=10),
        ft.Text("LV 7  ·  340 / 500 XP", size=11, color=C.TEXT_DIM,
                style=ft.TextStyle(letter_spacing=1.2)),
    ], spacing=8, tight=True), "blur",
        radius=0, padding=ft.Padding.only(left=16, right=16, top=12, bottom=12))
    header.border_radius = ft.BorderRadius.only(bottom_left=Radius.LG, bottom_right=Radius.LG)

    # ---------------------------------------------------------------- Luma line (frost)
    lumen = amb.glass(ft.Row([
        ft.Container(width=7, height=7, border_radius=4, bgcolor=C.PRIMARY,
                     shadow=ft.BoxShadow(blur_radius=8, color=C.a(C.PRIMARY, 0.9))),
        ft.Text(spans=[ft.TextSpan("LUMA  ", ft.TextStyle(color=C.PRIMARY, size=11,
                                                            weight=ft.FontWeight.BOLD,
                                                            letter_spacing=2)),
                       ft.TextSpan("Five quests stand ready. Start with the easy one.",
                                   ft.TextStyle(color=C.TEXT, size=13))], expand=True),
    ], spacing=10), "frost", padding=ft.Padding.symmetric(horizontal=14, vertical=12))

    # ---------------------------------------------------------------- quest cards (frost)
    def quest_card(title: str, path: str, icon: ft.IconData, xp: int, coins: int) -> ft.Control:
        pc = th.path_color(path)
        check = ft.Icon(ft.Icons.RADIO_BUTTON_UNCHECKED, size=28, color=C.a(C.TEXT, 0.4))
        name = ft.Text(title, size=Type.BODY + 1, weight=ft.FontWeight.W_600, color=C.TEXT)
        state = {"done": False}
        card = amb.glass(ft.Row([
            ft.Container(width=4, height=44, border_radius=2, bgcolor=pc,
                         shadow=ft.BoxShadow(blur_radius=8, color=C.a(pc, 0.7))),
            ft.Container(ft.Icon(icon, color=pc, size=20), width=40, height=40,
                         border_radius=20, bgcolor=C.a(pc, 0.16), alignment=ft.Alignment.CENTER),
            ft.Column([name, ft.Row([chip(f"+{xp} XP", C.PRIMARY), chip(f"+{coins}", C.ACCENT)],
                                    spacing=6)], spacing=4, expand=True, tight=True),
            ft.Container(check, width=44, height=44, alignment=ft.Alignment.CENTER),
        ], spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER), "frost", tint=pc,
            padding=ft.Padding.only(left=10, right=6, top=10, bottom=10))

        async def tap(e: ft.TapEvent) -> None:
            x, y = amb.card_center(e)
            state["done"] = not state["done"]
            check.icon = ft.Icons.CHECK_CIRCLE if state["done"] else ft.Icons.RADIO_BUTTON_UNCHECKED
            check.color = C.SUCCESS if state["done"] else C.a(C.TEXT, 0.4)
            name.color = C.TEXT_DIM if state["done"] else C.TEXT
            card.update()
            if state["done"]:
                space.pulse(pc, 0.7)
                page.run_task(burst.burst, x, y, color=pc, count=26)
                await cleared.show(title, x=x, y=y, color=th.current().primary)

        card.on_tap_down = tap
        return card

    cards = [quest_card(*q) for q in QUESTS]

    # ---------------------------------------------------------------- lab panel
    def btn(label: str, handler: object) -> ft.Control:
        return ft.FilledTonalButton(label, on_click=handler, height=36,
                                    style=ft.ButtonStyle(padding=ft.Padding.symmetric(
                                        horizontal=12)))

    async def do_burst(_: object) -> None:
        await burst.burst(color=th.current().primary, count=36)

    async def do_cleared(_: object) -> None:
        await cleared.show("Read 10 pages")

    async def do_staged(_: object) -> None:
        hum_log.clear()
        await thinking.play_staged(2.5)
        say(f"Luma staged done - on_start fired {len(hum_log)}x")

    async def do_session(_: object) -> None:
        import asyncio
        async with thinking.session(min_s=2.3, stages=fx.LumenThinking.STAGES):
            await asyncio.sleep(1.2)
        say("Session done.")

    def do_pulse(_: object) -> None:
        space.pulse()

    async def do_notice(_: object) -> None:
        await notice.show("Onion Dicing", "SKILL ACQUIRED", subtitle="Chef Path")

    async def do_seal(_: object) -> None:
        space.pulse(fx.GOLD, 1.2)
        await seal.show("LEVEL 8", "Individual level increased")

    async def do_reveal(_: object) -> None:
        await reveal.show("Ember Theme", "Theme unlocked")

    def on_reduce(e: ft.ControlEvent) -> None:
        fx.set_reduce(bool(e.control.value))
        space.set_reduce(None)
        say(f"Reduce effects {'ON' if e.control.value else 'OFF'}")

    def on_quality(e: ft.ControlEvent) -> None:
        sel = e.control.selected
        q = next(iter(sel)) if sel else "blur"
        amb.set_glass_cap(q, page)
        say(f"Glass cap: {q}")

    def on_pause(_: object) -> None:
        if space.paused:
            space.resume()
        else:
            space.pause()
        say("MindSpace paused" if space.paused else "MindSpace running")

    async def on_peek(_: object) -> None:
        """Fade the UI out for 8 s to see the MindSpace alone."""
        import asyncio
        shell.opacity = nav.opacity = 0.06
        page.update()
        await asyncio.sleep(8)
        shell.opacity = nav.opacity = 1
        page.update()

    theme_i = [0]

    def on_theme(_: object) -> None:
        theme_i[0] = (theme_i[0] + 1) % len(THEME_ORDER)
        th.apply_theme(page, THEME_ORDER[theme_i[0]])
        say(f"Theme: {THEME_ORDER[theme_i[0]]}")

    lab = amb.glass(ft.Column([
        ft.Text("EFFECTS LAB", size=11, weight=ft.FontWeight.BOLD, color=C.PRIMARY,
                style=ft.TextStyle(letter_spacing=3)),
        ft.Row([btn("Burst", do_burst), btn("Cleared", do_cleared), btn("Pulse", do_pulse)],
               wrap=True, spacing=6, run_spacing=6),
        ft.Row([btn("Luma staged", do_staged), btn("Luma session", do_session)],
               wrap=True, spacing=6, run_spacing=6),
        ft.Row([btn("Notice", do_notice), btn("Milestone", do_seal), btn("Identify", do_reveal)],
               wrap=True, spacing=6, run_spacing=6),
        ft.Row([ft.Switch(label="Reduce", value=False, on_change=on_reduce),
                btn("Pause/Resume", on_pause), btn("Theme", on_theme), btn("Peek", on_peek)],
               wrap=True, spacing=6, run_spacing=6),
        ft.Text("GLASS CAP", size=10, color=C.TEXT_DIM, style=ft.TextStyle(letter_spacing=2)),
        ft.SegmentedButton(
            segments=[ft.Segment(value="flat", label=ft.Text("Flat")),
                      ft.Segment(value="frost", label=ft.Text("Frost")),
                      ft.Segment(value="blur", label=ft.Text("Blur"))],
            selected=["blur"], on_change=on_quality),
        status,
    ], spacing=8, tight=True), "frost", fill=1.1)

    section = ft.Row([
        ft.Text("TODAY'S QUESTS", size=12, weight=ft.FontWeight.BOLD, color=C.TEXT,
                style=ft.TextStyle(letter_spacing=2.4)),
        chip(str(len(QUESTS)), C.PRIMARY),
    ], spacing=8)

    body = ft.Column(
        [lumen, ft.Container(section, padding=ft.Padding.only(top=6, left=4)), *cards, lab,
         ft.Container(height=90)],
        spacing=10, scroll=ft.ScrollMode.AUTO, expand=True)

    # ---------------------------------------------------------------- nav bar (real blur)
    def nav_item(icon: ft.IconData, label: str, on: bool = False) -> ft.Control:
        col = C.PRIMARY if on else C.TEXT_DIM
        return ft.Container(ft.Column([
            ft.Container(ft.Icon(icon, color=col, size=22), border_radius=12,
                         bgcolor=C.a(C.PRIMARY, 0.18) if on else None,
                         padding=ft.Padding.symmetric(horizontal=14, vertical=3)),
            ft.Text(label, size=11, color=col)], spacing=2, tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER), expand=True)

    nav = amb.glass(ft.Row([
        nav_item(ft.Icons.WB_SUNNY, "Today", True), nav_item(ft.Icons.EXPLORE, "Quests"),
        nav_item(ft.Icons.RECEIPT_LONG, "Bills"), nav_item(ft.Icons.REDEEM, "Rewards"),
        nav_item(ft.Icons.APPS, "More")]), "blur", radius=0,
        padding=ft.Padding.symmetric(vertical=8), left=0, right=0, bottom=0)
    nav.border_radius = ft.BorderRadius.only(top_left=Radius.LG, top_right=Radius.LG)

    shell = ft.Column([header, ft.Container(body, padding=ft.Padding.only(
        left=Space.GUTTER, right=Space.GUTTER, top=Space.MD), expand=True)],
        spacing=0, expand=True)
    shell_box = ft.SafeArea(shell, expand=True)
    shell.opacity = 1
    shell.animate_opacity = 300
    page.on_resize = lambda e: space.resize(page.width, page.height)
    page.add(ft.Stack([space, shell_box, nav], expand=True))


if __name__ == "__main__":
    ft.run(main)
