"""Effects gallery - every v1.2/v1.3 Arcane effect on a 375 px page, with a Reduce-effects toggle.

Run:  .venv/Scripts/flet run src/lol/ui/effects_gallery.py
Web:  .venv/Scripts/flet run --web --port 8630 src/lol/ui/effects_gallery.py
"""

from __future__ import annotations

import asyncio
import contextlib
import sys
from pathlib import Path

if __package__ in (None, ""):  # run as a file: make `lol` importable
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import flet as ft

from lol.ui import components as ui
from lol.ui import effects as fx
from lol.ui import theme as th

SKILLS = [
    {"id": "knife", "label": "Knife Basics", "state": "acquired", "path_color": "#FFA071",
     "parent": None},
    {"id": "dice", "label": "Onion Dicing", "state": "acquired", "path_color": "#FFA071",
     "parent": "knife"},
    {"id": "julienne", "label": "Julienne Cut", "state": "next", "path_color": "#FFA071",
     "parent": "knife"},
    {"id": "fillet", "label": "Fish Filleting", "state": "locked", "path_color": "#FFA071",
     "parent": "knife"},
    {"id": "brunoise", "label": "Brunoise", "state": "locked", "path_color": "#FFA071",
     "parent": "dice"},
]


def main(page: ft.Page) -> None:
    page.title = "Life of Legends - Effects"
    page.padding = 0
    with contextlib.suppress(Exception):
        page.window.width, page.window.height = 390, 844
    th.apply_theme(page, "arcane", update=False)

    notice = fx.NoticeEmblem()
    seal = fx.MilestoneSeal()
    hums = [0]

    def hum() -> None:  # the app plays sfx 'lumen_hum' here
        hums[0] += 1

    thinking = fx.LumenThinking(on_start=hum)
    reveal = fx.IdentifyReveal()
    cleared = fx.QuestCleared()
    banner = ui.LevelUpBanner()
    page.overlay.extend([notice, seal, reveal, cleared, banner, thinking])
    ico = fx.Icosphere(220, freq=2, facets=True)
    ico_on = [False]

    status = ft.Text("", size=12, color=th.C.TEXT_DIM)
    spiral_time = ft.Text("25:00", size=34, weight=ft.FontWeight.W_800, color="#FFFFFF",
                          style=ft.TextStyle(shadow=ft.BoxShadow(blur_radius=10,
                                                                 color=ft.Colors.with_opacity(0.8, "#1A1440"))))
    spiral = fx.ClockSpiral(300, content=spiral_time)
    progress = {"v": 0.0}

    def on_reduce(e: ft.ControlEvent) -> None:
        fx.set_reduce(bool(e.control.value))
        status.value = f"Reduce effects: {'ON' if e.control.value else 'OFF'}"
        page.update()

    async def do_notice(_: object) -> None:
        await notice.show("Onion Dicing", "SKILL ACQUIRED", subtitle="Chef Path")

    async def do_seal(_: object) -> None:
        await seal.show("LEVEL 5", "Individual level increased")

    async def do_think(_: object) -> None:
        await thinking.play(0.9, "Analysis…")

    async def do_think_ctx(_: object) -> None:
        async with thinking.session("Analysis…"):
            await asyncio.sleep(1.6)  # stand-in for real work
        status.value = "Proposal ready."
        page.update()

    async def do_staged(_: object) -> None:
        await thinking.play_staged(2.5)
        status.value = f"Staged done - on_start fired {hums[0]}x in total."
        page.update()

    async def do_cleared(_: object) -> None:
        await cleared.show("Drink a glass of water")

    async def do_reveal(_: object) -> None:
        await reveal.show("Ember Theme", "Theme unlocked")

    async def do_banner(_: object) -> None:
        await banner.show(4, title="CHEF LEVEL UP", subtitle="Chef Path reached level 4",
                          color="#FFA071", icon=ft.Icons.RESTAURANT)

    async def do_cleared_path(_: object) -> None:
        await cleared.show("30 push-ups", color="#FF6F91", x=120, y=520)

    def do_ico(_: object) -> None:
        ico_on[0] = not ico_on[0]
        if ico_on[0]:
            ico.prime()
            ico.update()
            ico.appear()
            ico.start(30)
        else:
            ico.vanish()
        ico.update()

    def do_punch(_: object) -> None:
        ico.punch(1.35, settle=1.0)
        ico.update()

    def do_distort(strength: float) -> object:
        def go(_: object) -> None:
            fx.distort(page, strength)
        return go

    async def do_staged_body(_: object) -> None:
        await thinking.play_staged(2.5, ("SCANNING BODY DATA…", "CALCULATING…", "PLAN READY"))

    async def do_analyze_work(_: object) -> None:
        async def work() -> str:
            await asyncio.sleep(1.0)
            return "ok"
        res = await ui.lumen_analyze(page, ("READING THE CHAIN…", "PLOTTING STEPS…",
                                            "CHAIN READY"), work, seconds=2.2)
        status.value = f"lumen_analyze -> {res}"
        page.update()

    async def do_short(_: object) -> None:
        await ui.lumen_analyze(page, ("READING YOUR SETS…", "RECORDS FOUND"), seconds=1.4)

    async def tick(_: object) -> None:
        progress["v"] = (progress["v"] + 0.125) % 1.0001
        spiral.set_progress(progress["v"])
        mins = round(25 * (1 - progress["v"]))
        spiral_time.value = f"{mins:02d}:00"
        spiral_time.update()

    def start(_: object) -> None:
        spiral.start()

    def stop(_: object) -> None:
        spiral.stop()

    async def on_skill(node_id: str) -> None:
        status.value = f"Tapped skill: {node_id}"
        page.update()

    def btn(label: str, handler: object) -> ft.Control:
        return ft.FilledTonalButton(label, on_click=handler, height=40)

    root = ft.Container(
        ft.Column([
            ft.Text("EFFECTS", size=12, weight=ft.FontWeight.BOLD, color=th.C.PRIMARY,
                    style=ft.TextStyle(letter_spacing=3)),
            ft.Switch(label="Reduce effects", value=False, on_change=on_reduce),
            status,
            ft.Row([btn("Notice", do_notice), btn("Milestone", do_seal)], wrap=True),
            ft.Row([btn("Luma 0.9 s", do_think), btn("Luma session", do_think_ctx)],
                   wrap=True),
            ft.Row([btn("Luma staged 2.5 s", do_staged), btn("Quest cleared", do_cleared)],
                   wrap=True),
            ft.Row([btn("Identify", do_reveal), btn("Path level-up", do_banner)], wrap=True),
            ft.Row([btn("Cleared (path, tap pos)", do_cleared_path)], wrap=True),
            ft.Divider(),
            ft.Text("IMPACT", size=12, weight=ft.FontWeight.BOLD, color=th.C.PRIMARY,
                    style=ft.TextStyle(letter_spacing=3)),
            ft.Row([btn("Icosphere on/off", do_ico), btn("Punch", do_punch)], wrap=True),
            ft.Container(ico, alignment=ft.Alignment.CENTER, height=230),
            ft.Row([btn("Distort 0.4", do_distort(0.4)), btn("Distort 1.0", do_distort(1.0))],
                   wrap=True),
            ft.Row([btn("Staged: body", do_staged_body), btn("Analyze + work", do_analyze_work)],
                   wrap=True),
            ft.Row([btn("Staged short 1.4 s", do_short)], wrap=True),
            ft.Divider(),
            ft.Text("SKILL LINKS", size=12, weight=ft.FontWeight.BOLD, color=th.C.PRIMARY,
                    style=ft.TextStyle(letter_spacing=3)),
            fx.SkillLinkTree(SKILLS, on_tap=on_skill),
            ft.Divider(),
            ft.Text("FOCUS TIMER", size=12, weight=ft.FontWeight.BOLD, color=th.C.PRIMARY,
                    style=ft.TextStyle(letter_spacing=3)),
            ft.Row([btn("Start", start), btn("Stop", stop), btn("+12.5%", tick)], wrap=True),
            ft.Container(spiral, alignment=ft.Alignment.CENTER),
            ft.Container(height=40),
        ], spacing=10, scroll=ft.ScrollMode.AUTO, expand=True),
        padding=16, width=375, expand=True)
    fx.install_distortion(page, root=root)
    page.add(ft.SafeArea(root, expand=True))


if __name__ == "__main__":
    ft.run(main)
