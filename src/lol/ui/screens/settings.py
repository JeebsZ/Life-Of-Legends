"""More -> Settings: Luma voice, sound effects (on/off + volume), Reduce effects, theme,
tracking modules (v1.3) and phone notifications (v1.3).

Notifications: a master switch (asks for the Android permission after explaining why; if it
was refused, offers the system settings), quiet hours and per-category settings. Every change
is saved and the phone's reminder queue is re-planned (App.save -> resync_reminders)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import flet as ft

from lol.core.models import NOTIFY_SOUNDS
from lol.ui import components as ui
from lol.ui import notify, sfx
from lol.ui.screens import common
from lol.ui.screens.premium import settings_blocks as premium_settings
from lol.ui.screens.profile import theme_picker, voice_controls
from lol.ui.theme import C, Motion, Space, Type

if TYPE_CHECKING:
    from lol.ui.app import App


class SettingsScreen:
    title = "Settings"

    def __init__(self, app: App) -> None:
        self.app = app
        self.list = common.screen_list()
        self.view = ft.Container(self.list, expand=True, key="settings")
        self.permission: bool | None = None  # last known phone permission (None = unknown)

    def render(self) -> None:
        self.list.controls = [
            ui.SectionHeader("Sound"),
            common.card(ft.Column([voice_controls(self.app),
                                   ft.Divider(height=1, color=C.OUTLINE),
                                   self._sfx_controls()], spacing=Space.MD, tight=True)),
            ui.SectionHeader("Effects"),
            common.card(common.switch_row(
                "Reduce effects", "Simple fades instead of bursts and spinning rings. "
                "Sounds play a little quieter.", self.app.game.profile.reduce_effects,
                self._set_reduce, icon=ft.Icons.MOTION_PHOTOS_OFF)),
            ui.SectionHeader("Theme"),
            theme_picker(self.app),
            ui.SectionHeader("Middle button"),
            self._middle_button(),
            ui.SectionHeader("Tracking"),
            self._modules(),
            ui.SectionHeader("Notifications"),
            self._notifications(),
            ui.SectionHeader("Personalize"),
            common.card(ft.Column([
                common.hint("Retake Luma's short quiz to retune your Paths, starter quests "
                            "and reminder time. Level, coins and quests stay as they are."),
                common.secondary_button("Redo personalize", self._redo,
                                        icon=ft.Icons.AUTO_AWESOME),
            ], spacing=Space.SM, tight=True), padding=Space.MD),
            *premium_settings(self.app, self.restyle),  # usage left, version, Developer
        ]

    async def _redo(self, _: Any = None) -> None:
        from lol.ui.app import run_onboarding

        await ui.buzz("medium")
        run_onboarding(self.app, redo=True)

    def on_enter(self) -> None:
        if notify.available():
            self.app.page.run_task(self._check_permission)

    async def _check_permission(self) -> None:
        granted = await notify.permission_granted()
        if granted != self.permission:
            self.permission = granted
            self.restyle()

    # ------------------------------------------------------------------ middle button
    def _middle_button(self) -> ft.Control:
        """The center nav slot: which feature it holds, Change (same picker) and Unpin."""
        from lol.ui.screens.more import TILES, pin_picker

        app = self.app
        key = app.pinned()
        label, icon, color = TILES[key] if key else ("Empty", ft.Icons.ADD, C.PRIMARY)

        def pick(new: str) -> None:
            app.set_pin(new)
            self.restyle()

        def unpin(_: Any = None) -> None:
            app.set_pin(None)
            sfx.play("back")
            app.toast("Middle button cleared. Tap it to pin another.", ft.Icons.PUSH_PIN_OUTLINED)
            self.restyle()

        buttons: list[ft.Control] = [common.secondary_button(
            "Change" if key else "Pin a feature", lambda e: pin_picker(app, pick),
            icon=ft.Icons.PUSH_PIN)]
        if key:
            buttons.append(ft.TextButton("Unpin", icon=ft.Icons.CLOSE, height=48,
                                         on_click=unpin))
        return common.card(ft.Column([
            ft.Row([
                ft.Container(ft.Icon(icon, color=color, size=24), width=44, height=44,
                             shape=ft.BoxShape.CIRCLE, alignment=ft.Alignment.CENTER,
                             bgcolor=C.a(color, 0.16), border=ft.Border.all(1.5, C.a(color, 0.7))),
                ft.Column([ft.Text(label, size=Type.BODY, weight=ft.FontWeight.W_600,
                                   color=C.TEXT),
                           common.hint("Tap the big middle button to open it. Hold it to unpin.")],
                          spacing=2, tight=True, expand=True),
            ], spacing=Space.MD, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Row(buttons, spacing=Space.SM),
        ], spacing=Space.MD, tight=True), padding=Space.MD)

    # ------------------------------------------------------------------ modules
    MODULE_INFO: ClassVar[dict[str, tuple[str, str, ft.IconData]]] = {
        "workout": ("Workout", "Log sessions, sets and routines", ft.Icons.FITNESS_CENTER),
        "sleep": ("Sleep", "Bedtime, wake time and how rested you feel", ft.Icons.NIGHTLIGHT),
        "water": ("Water", "Your own daily goal and quick-add buttons", ft.Icons.WATER_DROP),
        "energy": ("Energy check-in", "Low / okay / high sorts Today's list", ft.Icons.BOLT),
        "insights": ("Insights", "Plain trends with the data behind them",
                     ft.Icons.QUERY_STATS),
        "body": ("Body", "Weight log, BMI and an optional Luma plan",
                 ft.Icons.MONITOR_WEIGHT),
        "meals": ("Meals", "Meal log and photo scan (calories opt-in)",
                  ft.Icons.RESTAURANT),
        "run": ("Run & walk", "GPS route map, pace, distance ladder, voice cues",
                ft.Icons.DIRECTIONS_RUN),
    }

    def _modules(self) -> ft.Control:
        g, app = self.app.game, self.app

        def setter(name: str):
            def changed(on: bool) -> None:
                g.set_module(name, on)
                app.save()
                app.refresh_center()  # a pinned feature switched off reads as an empty slot
                label = self.MODULE_INFO[name][0]
                app.toast(f"{label} {'on' if on else 'off'}"
                          + ("" if on else ". Your data is kept."), self.MODULE_INFO[name][2])
            return changed

        rows: list[ft.Control] = [common.hint("Turn a module off to hide its tile and Today "
                                              "widgets. Nothing is deleted.")]
        for name, (title, sub, icon) in self.MODULE_INFO.items():
            rows.append(common.switch_row(title, sub, g.module_on(name), setter(name),
                                          icon=icon))
        return common.card(ft.Column(rows, spacing=Space.SM, tight=True))

    # ------------------------------------------------------------------ notifications
    def _set(self, **changes: Any) -> None:
        try:
            self.app.game.set_reminders(**changes)
        except ValueError as exc:
            self.app.error(f"Couldn't save: {exc}")
            return
        self.app.save()  # re-plans the phone's reminders

    def _notifications(self) -> ft.Control:
        app = self.app
        r = app.game.profile.reminders
        on_phone = notify.available()
        rows: list[ft.Control] = []
        if not on_phone:
            rows.append(ft.Container(ft.Row([
                ft.Icon(ft.Icons.PHONE_ANDROID, color=C.ACCENT, size=20),
                ft.Text("Notifications work on the phone app. You can set them up here; "
                        "they start once the app runs on Android.", size=Type.CAPTION,
                        color=C.TEXT, expand=True)], spacing=Space.SM),
                bgcolor=C.a(C.ACCENT, 0.1), border_radius=8, padding=Space.SM))
        elif self.permission is False and r.enabled:
            rows.append(ft.Container(ft.Column([
                ft.Text("Notifications are blocked for Life of Legends on this phone.",
                        size=Type.CAPTION, color=C.TEXT),
                common.secondary_button("Open phone settings", self._open_settings,
                                        icon=ft.Icons.SETTINGS),
            ], spacing=Space.XS, tight=True), bgcolor=C.a(C.DANGER, 0.1), border_radius=8,
                padding=Space.SM))
        rows.append(common.switch_row("Reminders", "Gentle local reminders. Nothing is sent "
                                      "to a server.", r.enabled, self._master,
                                      icon=ft.Icons.NOTIFICATIONS))
        detail: list[ft.Control] = [
            common.hint("Quiet hours (bill and daily reminders wait until they end; water "
                        "reminders skip them)"),
            common.time_row(app.page, "Quiet from", r.quiet_start,
                            lambda v: self._set(quiet_start=v), icon=ft.Icons.BEDTIME),
            common.time_row(app.page, "Quiet until", r.quiet_end,
                            lambda v: self._set(quiet_end=v), icon=ft.Icons.WB_SUNNY),
            ft.Divider(height=1, color=C.OUTLINE),
            common.switch_row("Bills", "Before a bill is due", r.bills_on,
                              lambda on: self._set(bills_on=on), icon=ft.Icons.RECEIPT_LONG),
            ft.Row([common.hint("Days before"), ft.Container(expand=True),
                    common.stepper(r.bill_days_before,
                                   lambda v: self._set(bill_days_before=v), lo=0, hi=30)],
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
            common.time_row(app.page, "Bill reminder at", r.bill_time,
                            lambda v: self._set(bill_time=v)),
            ft.Divider(height=1, color=C.OUTLINE),
            common.switch_row("Daily quests", "Once a day while a quest is open", r.daily_on,
                              lambda on: self._set(daily_on=on), icon=ft.Icons.FLAG),
            common.time_row(app.page, "Daily reminder at", r.daily_time,
                            lambda v: self._set(daily_time=v)),
            ft.Divider(height=1, color=C.OUTLINE),
            common.switch_row("Water", "Every so often in your waking hours; stops once "
                              "today's goal is reached", r.water_on,
                              lambda on: self._set(water_on=on), icon=ft.Icons.WATER_DROP),
            ft.Row([common.hint("Every"), ft.Container(expand=True),
                    common.stepper(r.water_interval_min,
                                   lambda v: self._set(water_interval_min=v), lo=15, hi=720,
                                   step=15, suffix=" min", width=72)],
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
            common.hint("Active days"),
            common.ToggleChips([(str(i), d, None, C.PRIMARY) for i, d in
                                enumerate(("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"))],
                               {str(d) for d in r.water_active_days},
                               lambda sel: self._set(water_active_days=[int(x) for x in sel])),
            ft.Row([common.hint("Snooze for"), ft.Container(expand=True),
                    common.stepper(r.water_snooze_min,
                                   lambda v: self._set(water_snooze_min=v), lo=5, hi=240,
                                   step=5, suffix=" min", width=72)],
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Divider(height=1, color=C.OUTLINE),
            common.switch_row("Focus timer done", "When a focus countdown ends", r.focus_on,
                              lambda on: self._set(focus_on=on), icon=ft.Icons.TIMER),
            common.switch_row("Comeback nudge", "One gentle note after a few quiet days "
                              "(off by default)", r.comeback_on,
                              lambda on: self._set(comeback_on=on),
                              icon=ft.Icons.WB_TWILIGHT),
            ft.Divider(height=1, color=C.OUTLINE),
            ft.Row([common.secondary_button("Send test", self._test_now,
                                            icon=ft.Icons.NOTIFICATIONS_ACTIVE),
                    common.secondary_button("Test in 1 min", self._test_in,
                                            icon=ft.Icons.ALARM)], spacing=Space.SM),
            common.hint("Timing is approximate (a few minutes late is normal). Open the app "
                        "now and then to keep reminders topped up."),
        ]
        box = ft.Column(detail, spacing=Space.SM, tight=True, disabled=not r.enabled,
                        opacity=1 if r.enabled else 0.45,
                        animate_opacity=Motion.anim(Motion.FADE_MS))
        self._detail = box
        rows.append(box)
        return common.card(ft.Column(rows, spacing=Space.SM, tight=True))

    async def _master(self, on: bool) -> None:
        app = self.app
        if on and notify.available():
            ok = await common.confirm(
                app.page, "Turn on reminders?",
                "Luma can remind you about bills, today's quests, water and your focus "
                "timer. Android will ask once if Life of Legends may send notifications.",
                "Continue")
            if not ok:
                self.restyle()  # put the switch back
                return
            granted = await notify.ensure_permission()
            self.permission = granted
            if not granted:
                app.error("Notifications are blocked. You can allow them in phone settings.")
        self._set(enabled=on)
        if not on:
            app.page.run_task(notify.cancel_all)
        app.toast("Reminders on" if on else "Reminders off. Nothing will be scheduled.",
                  ft.Icons.NOTIFICATIONS if on else ft.Icons.NOTIFICATIONS_OFF)
        self.restyle()

    async def _open_settings(self, _: Any = None) -> None:
        await notify.open_settings()

    async def _test_now(self, _: Any = None) -> None:
        if not notify.available():
            self.app.toast("Notifications work on the phone app.", ft.Icons.PHONE_ANDROID)
            return
        if not await notify.ensure_permission():
            self.permission = False
            self.app.error("Notifications are blocked. Allow them in phone settings.")
            self.restyle()
            return
        ok = await notify.test_now()
        self.app.toast("Test sent - check your notifications" if ok
                       else "Couldn't send the test", ft.Icons.NOTIFICATIONS_ACTIVE)

    async def _test_in(self, _: Any = None) -> None:
        if not notify.available():
            self.app.toast("Notifications work on the phone app.", ft.Icons.PHONE_ANDROID)
            return
        if not await notify.ensure_permission():
            self.permission = False
            self.app.error("Notifications are blocked. Allow them in phone settings.")
            self.restyle()
            return
        ok = await notify.test_in(60)
        self.app.toast("A test arrives in about a minute (lock the phone to try it)" if ok
                       else "Couldn't schedule the test", ft.Icons.ALARM)

    def restyle(self) -> None:
        self.render()
        ui.refresh(self.list)

    def _set_reduce(self, on: bool) -> None:
        self.app.game.set_profile(reduce_effects=on)
        self.app.save()
        self.app.apply_settings()
        self.app.toast("Reduce effects on: simple fades" if on else "Full effects on",
                       ft.Icons.MOTION_PHOTOS_OFF if on else ft.Icons.AUTO_AWESOME)

    def _sfx_controls(self) -> ft.Control:
        g, app = self.app.game, self.app
        p = g.profile
        vol_label = ft.Text(f"{round(p.sfx_volume * 100)}%", size=Type.CAPTION,
                            color=C.TEXT_DIM, width=40, text_align=ft.TextAlign.RIGHT)
        slider = ft.Slider(value=p.sfx_volume, min=0, max=1, divisions=10,
                           active_color=C.PRIMARY, inactive_color=C.a(C.TEXT, 0.12),
                           expand=True, disabled=not p.sfx_on)
        vol_row = ft.Row([ft.Icon(ft.Icons.VOLUME_UP, size=18, color=C.TEXT_DIM), slider,
                          vol_label], spacing=Space.XS,
                         vertical_alignment=ft.CrossAxisAlignment.CENTER,
                         opacity=1 if p.sfx_on else 0.45,
                         animate_opacity=Motion.anim(Motion.FADE_MS))

        def toggle(on: bool) -> None:
            g.set_profile(sfx_on=on)
            app.save()
            slider.disabled = not on
            vol_row.opacity = 1 if on else 0.45
            ui.refresh(slider, vol_row)
            if on:
                sfx.play("toggle")  # the switch sound fired while off; play it now
            app.toast("Sound effects on" if on else "Sound effects off",
                      ft.Icons.MUSIC_NOTE if on else ft.Icons.MUSIC_OFF)

        def sliding(e: Any) -> None:
            vol_label.value = f"{round(float(e.control.value) * 100)}%"
            ui.refresh(vol_label)

        def slid(e: Any) -> None:
            g.set_profile(sfx_volume=float(e.control.value))
            app.save()
            sfx.play("coin")  # preview at the new volume

        slider.on_change = sliding
        slider.on_change_end = slid
        return ft.Column([
            common.switch_row("Sound effects", "Taps, tabs, rewards and the timer bell",
                              p.sfx_on, toggle, icon=ft.Icons.MUSIC_NOTE),
            vol_row,
            self._notify_sound_picker(),
        ], spacing=Space.XS, tight=True)

    def _notify_sound_picker(self) -> ft.Control:
        """Notification sound (notify_01..08): Luma's in-app ping and the phone alerts.
        Tapping one saves it (re-plans the phone reminders) and previews it."""
        g, app = self.app.game, self.app
        chips: list[ft.Container] = []

        def paint() -> None:
            for c in chips:
                on = c.data == g.profile.notify_sound
                c.bgcolor = C.a(C.PRIMARY, 0.22) if on else C.a(C.TEXT, 0.06)
                c.border = ft.Border.all(1.5 if on else 1, C.PRIMARY if on else C.OUTLINE)
                c.content.color = C.PRIMARY if on else C.TEXT_DIM
            ui.refresh(*chips)

        def pick(name: str) -> None:
            if name != g.profile.notify_sound:
                g.set_profile(notify_sound=name)
                app.save()
                paint()
            sfx.play("notice")  # preview (reads the new setting)

        for i, name in enumerate(NOTIFY_SOUNDS, start=1):
            chips.append(ft.Container(
                ft.Text(str(i), size=Type.BODY, weight=ft.FontWeight.W_600),
                data=name, width=48, height=48, border_radius=12,
                alignment=ft.Alignment.CENTER, ink=True,
                tooltip=f"Notification sound {i}",
                on_click=lambda e, n=name: pick(n)))
        paint()
        return ft.Column([
            ft.Row([ft.Icon(ft.Icons.NOTIFICATIONS_ACTIVE, size=18, color=C.TEXT_DIM),
                    ft.Text("Notification sound", size=Type.BODY, color=C.TEXT),
                    ft.Text("tap to preview", size=Type.CAPTION, color=C.TEXT_DIM)],
                   spacing=Space.XS, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Row(chips, wrap=True, spacing=Space.XS, run_spacing=Space.XS),
        ], spacing=Space.XS, tight=True)
