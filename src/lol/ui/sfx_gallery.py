"""SFX gallery - one button per sound effect, to audition src/assets/sfx/*.wav, plus a
"Quest complete sequence" button that replays the app's reward beat with Luma's voice (same
mixer sequencing as App.award + LumenNotice) to audition the timing. Sounds muted in the app
(sfx.SILENT: button taps, toggle clicks) are shown as "muted" and stay silent here too.

Run:  .venv/Scripts/flet run src/lol/ui/sfx_gallery.py
Web:  .venv/Scripts/flet run --web --port 8620 src/lol/ui/sfx_gallery.py
(Rebuild the pack-based sounds: .venv/Scripts/python tools/sfx/pack_sfx.py; the synth ones
- level_up, skill_acquired, milestone, lumen_hum: .venv/Scripts/python tools/sfx/make_sfx.py)
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

if __package__ in (None, ""):  # run as a file: make `lol` importable
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import flet as ft

from lol.ui import audio, mixer, sfx

ASSETS = str(Path(__file__).resolve().parents[2] / "assets")
CYAN = "#5CE1E6"
BG = "#0B1220"
PANEL = "#121B2E"
DIM = "#8FA3BF"

GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Buttons and navigation", ("tap", "toggle", "tab_open", "tab_close", "back", "sheet_open",
                                "sheet_close")),
    ("Layered moments (combos)", ("chain_step", "chain_complete", "skill_unlock",
                                  "skill_rank_up", "path_level_up")),
    ("Rewards and moments", ("quest_done", "quest_clear", "coin", "coin_many", "xp_fill",
                             "purchase", "level_up", "skill_acquired", "milestone")),
    ("Layers", ("granted", "holo_flicker", "unlock", "upgrade", "mission_complete",
                "rank_up")),
    ("Luma", ("lumen_hum", "type", "loading", "power_up")),
    ("Notification sounds (Settings)", tuple(f"notify_{i:02d}" for i in range(1, 9))),
    ("Notices and alerts", ("alert_soft", "error_soft", "objective_new", "low_energy",
                            "low_health")),
    ("Timer", ("timer_tick", "timer_done")),
    ("Analysis and camera", ("scan_tick", "scan_done", "distort", "shutter")),
)


def main(page: ft.Page) -> None:
    page.title = "Life of Legends - SFX"
    page.bgcolor = BG
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 0
    if not page.web:
        page.window.width, page.window.height = 375, 780

    # fake profile: the gallery's switches drive the same settings sfx.py reads in the app
    prof = SimpleNamespace(sfx_on=True, sfx_volume=sfx.DEFAULT_VOLUME, reduce_effects=False,
                           voice_on=True, voice_volume=audio.DEFAULT_VOLUME)
    sfx.init(page, settings=lambda: prof)
    audio.init(page, settings=lambda: prof)
    status = ft.Text("Tap a sound.", size=12, color=DIM)

    def on_play(name: str) -> None:
        sfx.play(name)
        status.value = (f"{name}  -  muted in the app (sfx.SILENT)" if sfx.silent(name)
                        else f"{name}  -  volume {sfx.effective_volume():.2f}")
        status.update()

    async def quest_sequence() -> None:
        """App.award's sound beat: chime + quiet xp_fill at once, the coin sparkle at 0.35 s,
        then (via the mixer) the notice ping + Luma's quest_done line after the chime."""
        sfx.play("quest_done")
        sfx.play("xp_fill", 0.35)
        await asyncio.sleep(0.05)  # LumenNotice slides in, then cues its ping + voice
        wait = mixer.cue(page, lambda: (sfx.play("notice", 0.7), audio.play("quest_done")))
        status.value = f"quest complete  -  voice in {wait + 0.05:.2f} s"
        status.update()
        await asyncio.sleep(0.3)
        sfx.play("coin", 0.55)

    def sound_button(name: str, label: str | None = None, action=None) -> ft.Control:
        return ft.Container(
            ft.Text(label or (f"{name} · muted" if sfx.silent(name) else name), size=13, color=CYAN, weight=ft.FontWeight.W_500),
            padding=ft.Padding.symmetric(horizontal=12, vertical=10),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.45, CYAN)),
            border_radius=10,
            bgcolor=PANEL,
            ink=True,
            on_click=action or (lambda e, n=name: on_play(n)),
        )

    def set_on(e: ft.Event) -> None:
        prof.sfx_on = bool(e.control.value)

    def set_reduce(e: ft.Event) -> None:
        prof.reduce_effects = bool(e.control.value)

    def set_vol(e: ft.Event) -> None:
        prof.sfx_volume = float(e.control.value)

    sections: list[ft.Control] = [
        ft.Text("SEQUENCES", size=11, color=DIM, weight=ft.FontWeight.W_600),
        ft.Row([sound_button("seq", "Quest complete sequence",
                             lambda e: page.run_task(quest_sequence))], wrap=True),
    ]
    for title, names in GROUPS:
        sections.append(ft.Text(title.upper(), size=11, color=DIM, weight=ft.FontWeight.W_600))
        sections.append(ft.Row([sound_button(n) for n in names], wrap=True, spacing=8,
                               run_spacing=8))

    body = ft.Column(
        [
            ft.Text("Arcane SFX", size=22, color=CYAN, weight=ft.FontWeight.W_700),
            status,
            ft.Row([ft.Text("SFX on", color=DIM, size=13),
                    ft.Switch(value=True, on_change=set_on, active_color=CYAN),
                    ft.Text("Reduce effects", color=DIM, size=13),
                    ft.Switch(value=False, on_change=set_reduce, active_color=CYAN)],
                   wrap=True),
            ft.Row([ft.Text("Volume", color=DIM, size=13),
                    ft.Slider(value=sfx.DEFAULT_VOLUME, min=0, max=1, divisions=20,
                              active_color=CYAN, on_change=set_vol, expand=True)]),
            *sections,
        ],
        spacing=12,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )
    page.add(ft.SafeArea(ft.Container(body, padding=16, width=375), expand=True))


if __name__ == "__main__":
    ft.run(main, assets_dir=ASSETS)
