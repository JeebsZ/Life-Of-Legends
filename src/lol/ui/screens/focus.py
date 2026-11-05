"""More -> Focus Timer: focus / break countdowns (custom minutes) and a stopwatch on the
ClockSpiral, start / pause / resume / stop, an optional linked quest or Path, and today's stats.

Sessions are logged with Game.log_focus when a focus countdown finishes or when you stop early
(partial sessions count, from 1 minute). The timer keeps a start timestamp, so elapsed time
survives switching tabs; the once-per-second display loop only runs while this screen shows."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

import flet as ft

from lol.ui import components as ui
from lol.ui import effects as fx
from lol.ui import sfx
from lol.ui import theme as th
from lol.ui.screens import common
from lol.ui.theme import C, Radius, Space, Type

if TYPE_CHECKING:
    from lol.ui.app import App

PRESETS = {"focus": (15, 25, 45, 60), "break": (5, 10, 15)}
MODE_LABEL = {"focus": "Focus", "break": "Break", "stopwatch": "Stopwatch"}
MAX_MINUTES = 240


def clock(seconds: float) -> str:
    s = max(0, int(seconds))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"


class FocusScreen:
    title = "Focus Timer"

    def __init__(self, app: App) -> None:
        self.app = app
        self.mode = "focus"
        self.minutes = {"focus": 25, "break": 5}
        self.running = False  # a session exists (running or paused)
        self.paused = False
        self.started_at = 0.0  # time.time() when the current run segment began
        self.acc = 0.0  # seconds from earlier segments (before pauses)
        self.started_iso = ""
        self.link = ""  # "", "q:<quest id>" or "p:<path id>"
        self.tick_sound = False
        self._alive = False
        self._loop_task = False

        self._new_spiral()
        self.list = common.screen_list()
        self.view = ft.Container(self.list, expand=True, key="focus")

    def _web(self) -> bool:
        """Flutter web (skwasm) crashed with the rotating clock rings in testing (memory access
        out of bounds within a minute), so on web the rings stay still; the progress ring and
        the time still update every second. Native builds keep the rotation."""
        try:
            return bool(self.app.page.web)
        except AttributeError:
            return False

    def _new_spiral(self) -> None:
        """A fresh ClockSpiral per render. Its rings are turned by advance() from the
        once-per-second loop, never by start(): a long implicit rotation crashed the Flutter
        web renderer (skwasm out-of-bounds) after a tab switch."""
        self.time_text = ft.Text("25:00", size=40, weight=ft.FontWeight.W_800, color="#FFFFFF",
                                 style=ft.TextStyle(shadow=ft.BoxShadow(
                                     blur_radius=12, color=ft.Colors.with_opacity(0.85,
                                                                                   "#1A1440"))))
        self.mode_text = ft.Text("FOCUS", size=11, weight=ft.FontWeight.BOLD, color="#E4F0FF",
                                 style=ft.TextStyle(letter_spacing=3))
        self.spiral = fx.ClockSpiral(280, reduce=True if self._web() else None, content=ft.Column(
            [self.mode_text, self.time_text], spacing=0, tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER))

    # ------------------------------------------------------------------ time
    def elapsed(self) -> float:
        live = time.time() - self.started_at if self.running and not self.paused else 0.0
        return self.acc + live

    def planned(self) -> float | None:
        return None if self.mode == "stopwatch" else self.minutes[self.mode] * 60.0

    # ------------------------------------------------------------------ lifecycle
    def prepare(self, quest_id: str | None = None, **_: object) -> None:
        if quest_id and not self.running:
            self.link = f"q:{quest_id}"
            self.mode = "focus"

    def on_enter(self) -> None:
        self._alive = True
        if self.running and not self.paused:
            self._ensure_loop()

    def on_leave(self) -> None:
        self._alive = False  # the loop ends; elapsed time keeps counting from started_at

    def _ensure_loop(self) -> None:
        if not self._loop_task:
            self._loop_task = True
            self.app.page.run_task(self._loop)

    async def _loop(self) -> None:
        try:
            while self._alive and self.running and not self.paused:
                self._paint_time()
                self.spiral.advance(1.0)  # rings turn one second's worth per tick
                planned = self.planned()
                if planned is not None and self.elapsed() >= planned:
                    await self._finish()
                    return
                if self.tick_sound:
                    sfx.play("timer_tick", 0.5)
                await asyncio.sleep(1.0 - (self.elapsed() % 1.0) + 0.01)
        finally:
            self._loop_task = False

    # ------------------------------------------------------------------ render
    def render(self) -> None:
        g, today = self.app.game, self.app.today()
        if self.running and not self.paused:
            planned = self.planned()
            if planned is not None and self.elapsed() >= planned:
                self.app.page.run_task(self._finish)  # it ran out while you were away
        self._new_spiral()
        self._paint_time(update=False)
        locked = self.running
        mode = common.segmented([("focus", "Focus"), ("break", "Break"),
                                 ("stopwatch", "Stopwatch")], self.mode,
                                on_change=self._set_mode)
        mode.disabled = locked
        items: list[ft.Control] = [
            ft.Row([mode], alignment=ft.MainAxisAlignment.CENTER),
            ft.Container(self.spiral, alignment=ft.Alignment.CENTER,
                         padding=ft.Padding.symmetric(vertical=Space.SM)),
            self._buttons(),
        ]
        if self.mode != "stopwatch":
            items.append(self._minutes_row(locked))
        items.append(self._link_picker(locked))
        items.append(common.switch_row("Tick sound", "A very soft tick each second",
                                       self.tick_sound, lambda v: setattr(self, "tick_sound", v),
                                       icon=ft.Icons.GRAPHIC_EQ))
        st = g.focus_stats(today)
        items += [ui.SectionHeader("Today"), common.card(ft.Column([
            ft.Row([self._stat(str(st["sessions"]), "sessions"),
                    self._stat(f"{st['minutes']}", "minutes"),
                    self._stat(f"{st['xp']}", "XP earned")], spacing=Space.SM),
            common.hint(f"{st['xp_left']} focus XP left today. Short or interrupted sessions "
                        "count too: XP comes per 5 minutes."),
        ], spacing=Space.SM, tight=True), padding=Space.MD)]
        for s in g.focus_sessions(today)[:8]:
            what = s.note or self._link_name(s.quest_id, s.path_id) or MODE_LABEL.get(s.mode, "")
            items.append(ft.Row([
                ft.Icon(ft.Icons.TIMER if s.mode == "focus" else ft.Icons.AV_TIMER,
                        color=th.path_color(s.path_id) if s.path_id else C.PRIMARY, size=18),
                ft.Text(f"{s.minutes} min · {what}", size=Type.LABEL, color=C.TEXT,
                        expand=True, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                common.hint(("partial · " if s.partial else "") + f"+{s.xp} XP"),
            ], spacing=Space.SM))
        self.list.controls = items

    def restyle(self) -> None:
        self.render()
        ui.refresh(self.list)

    def _rerender(self) -> None:
        if self._alive:
            self.render()
            ui.refresh(self.list)

    def _paint_time(self, update: bool = True) -> None:
        el, planned = self.elapsed(), self.planned()
        if planned is None:
            self.time_text.value = clock(el)
            progress = (el % 60) / 60 if self.running else 0.0
        else:
            self.time_text.value = clock(planned - el if self.running else planned)
            progress = min(1.0, el / planned) if self.running else 0.0
        label = MODE_LABEL[self.mode].upper()
        self.mode_text.value = f"{label} · PAUSED" if self.paused else label
        self.spiral.set_progress(progress)
        if update:
            ui.refresh(self.time_text, self.mode_text)

    @staticmethod
    def _stat(value: str, label: str) -> ft.Control:
        return ft.Container(ft.Column([
            ft.Text(value, size=Type.TITLE + 2, weight=ft.FontWeight.W_900, color=C.PRIMARY),
            ft.Text(label, size=Type.CAPTION, color=C.TEXT_DIM),
        ], spacing=0, tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            expand=True, bgcolor=C.SURFACE_HI, border_radius=Radius.SM,
            padding=ft.Padding.symmetric(vertical=Space.SM), alignment=ft.Alignment.CENTER)

    def _buttons(self) -> ft.Control:
        if not self.running:
            row = [common.primary_button("Start", self._start, icon=ft.Icons.PLAY_ARROW)]
        else:
            pr = (common.primary_button("Resume", self._resume, icon=ft.Icons.PLAY_ARROW)
                  if self.paused else
                  common.secondary_button("Pause", self._pause, icon=ft.Icons.PAUSE))
            row = [pr, common.secondary_button("Stop", self._stop, icon=ft.Icons.STOP,
                                               color=C.DANGER)]
        return ft.Row(row, spacing=Space.SM)

    def _minutes_row(self, locked: bool) -> ft.Control:
        cur = self.minutes[self.mode]
        chips: list[ft.Control] = []
        for m in PRESETS[self.mode]:
            on = m == cur
            chips.append(ft.Container(
                ft.Text(f"{m}m", size=Type.LABEL, weight=ft.FontWeight.BOLD,
                        color=C.PRIMARY if on else C.TEXT_DIM),
                height=40, width=52, border_radius=Radius.PILL, alignment=ft.Alignment.CENTER,
                bgcolor=C.a(C.PRIMARY, 0.18) if on else C.a(C.TEXT, 0.05),
                border=ft.Border.all(1.2, C.a(C.PRIMARY, 0.6) if on else C.a(C.TEXT, 0.08)),
                on_click=None if locked else (lambda e, mm=m: self._set_minutes(mm))))
        custom = common.text_field("Custom", number=True)
        custom.value = "" if cur in PRESETS[self.mode] else str(cur)
        custom.width = 92
        custom.dense = True
        custom.disabled = locked

        def submit(e: Any) -> None:
            try:
                m = int((custom.value or "").strip())
            except ValueError:
                m = 0
            if not 1 <= m <= MAX_MINUTES:
                sfx.play("error_soft")
                custom.error_text = f"1-{MAX_MINUTES}"
                custom.update()
                return
            self._set_minutes(m)

        custom.on_submit = submit
        custom.on_blur = lambda e: submit(e) if (custom.value or "").strip() else None
        return ft.Row([*chips, custom], spacing=Space.XS, wrap=True, run_spacing=Space.XS,
                      alignment=ft.MainAxisAlignment.CENTER,
                      vertical_alignment=ft.CrossAxisAlignment.CENTER,
                      opacity=0.5 if locked else 1)

    def _link_name(self, quest_id: str | None, path_id: str | None) -> str:
        if quest_id:
            try:
                return self.app.game.quest(quest_id).title
            except KeyError:
                return ""
        return f"{th.path_name(path_id)} Path" if path_id else ""

    def _link_picker(self, locked: bool) -> ft.Control:
        g, today = self.app.game, self.app.today()
        opts = [ft.DropdownOption(key="none", text="No link (overall XP only)")]
        opts += [ft.DropdownOption(key=f"p:{pid}", text=f"Path · {th.path_name(pid)}")
                 for pid in th.PATH_IDS]
        opts += [ft.DropdownOption(key=f"q:{q.id}", text=f"Quest · {q.title}")
                 for q in g.quests if not g.is_done(q, today) or f"q:{q.id}" == self.link]
        if self.link and not any(o.key == self.link for o in opts):
            self.link = ""

        def picked(e: Any) -> None:
            sfx.play("tap")
            v = e.control.value or ""
            self.link = "" if v == "none" else v

        return ft.Dropdown(label="Link to (XP goes to its Path)", value=self.link or "none", options=opts,
                           on_select=picked, disabled=locked, expand=True, filled=True,
                           border_radius=Radius.SM, fill_color=C.SURFACE_HI,
                           menu_height=360)

    # ------------------------------------------------------------------ actions
    def _set_mode(self, mode: str) -> None:
        sfx.play("toggle")
        self.mode = mode
        self._rerender()

    def _set_minutes(self, m: int) -> None:
        sfx.play("toggle")
        self.minutes[self.mode] = m
        self._rerender()

    def _start(self, _: Any = None) -> None:
        self.running, self.paused = True, False
        self.started_at, self.acc = time.time(), 0.0
        self.started_iso = datetime.now().isoformat(timespec="minutes")
        self._arm_alarm()
        self._rerender()
        self._ensure_loop()

    def _arm_alarm(self) -> None:
        """Phone notification for when a focus countdown ends (cancelled on pause / stop)."""
        planned = self.planned()
        if self.mode == "focus" and planned is not None:
            left = max(0.0, planned - self.elapsed())
            self.app.set_focus_alarm(datetime.now() + timedelta(seconds=left))

    def _pause(self, _: Any = None) -> None:
        self.acc = self.elapsed()
        self.paused = True
        self.app.set_focus_alarm(None)
        self._rerender()

    def _resume(self, _: Any = None) -> None:
        self.started_at = time.time()
        self.paused = False
        self._arm_alarm()
        self._rerender()
        self._ensure_loop()

    def _reset(self) -> None:
        self.running = self.paused = False
        self.acc = 0.0
        if self.app.focus_ends is not None:
            self.app.set_focus_alarm(None)

    async def _stop(self, _: Any = None) -> None:
        el = self.elapsed()
        mode = self.mode
        self._reset()
        if mode == "break":
            self.app.toast("Break ended", ft.Icons.FREE_BREAKFAST)
            self._rerender()
            return
        minutes = int(el // 60)
        if minutes < 1:
            self.app.toast("Under a minute, so nothing was logged.", ft.Icons.TIMER)
            self._rerender()
            return
        await self._log(minutes, partial=mode == "focus", mode=mode)

    async def _finish(self) -> None:
        """A countdown reached zero."""
        if not self.running:
            return
        mode = self.mode
        minutes = self.minutes[mode]
        self._reset()
        sfx.play("timer_done")
        await ui.buzz("heavy")
        if mode == "break":
            self.app.toast("Break over. Ready when you are.", ft.Icons.FREE_BREAKFAST)
            self.mode = "focus"
            self._rerender()
            return
        await self._log(minutes, partial=False, mode="focus")
        self.mode = "break"  # offer a break next (tap Start when ready)
        self._rerender()

    async def _log(self, minutes: int, *, partial: bool, mode: str) -> None:
        g, today = self.app.game, self.app.today()
        qid = self.link[2:] if self.link.startswith("q:") else None
        pid = self.link[2:] if self.link.startswith("p:") else None
        name = self._link_name(qid, pid)

        def line(c: Any) -> str:
            where = f" to {th.path_name(c.path_id)} Path" if c.path_id else ""
            return f"Notice: Focus session logged: {minutes} min. +{c.xp} XP{where}."

        c = await self.app.award(lambda: g.log_focus(
            minutes, today, quest_id=qid, path_id=pid, note=name if qid else "",
            partial=partial, mode=mode, started=self.started_iso), line=line)
        if not (c.xp or c.coins):
            self.app.toast(f"{minutes} min logged. Focus XP comes per 5 minutes "
                           "(or today's focus cap is reached).", ft.Icons.TIMER)
        self._rerender()
