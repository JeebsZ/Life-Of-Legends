"""Opt-in rewarded ads (Part 1: stub, no SDK) and the free-limit sheet.

`show_rewarded(app, placement)` -> "watched" | "skipped" | "unavailable". Premium users never
see an ad. Without an ad SDK (Part 2: AdMob) the only "ad" is a clearly labelled dev
placeholder, shown in dev builds (LOL_DEV=1 or the Developer menu); everywhere else the result
is "unavailable", and callers treat that generously (no ad to watch never punishes the user).

Part 2 replaces `_available()` and `_play()` with the AdMob rewarded unit for the placement,
sending `game.data.premium.ads_non_personalized` (13-17 band) with the request.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import flet as ft

from lol.core import premium
from lol.ui import components as ui
from lol.ui import sfx
from lol.ui.screens import common
from lol.ui.theme import C, Radius, Size, Space, Type

if TYPE_CHECKING:
    from lol.ui.app import App

GOLD = "#F5C66B"
PLACEMENT_TEXT = {
    "pre_run_stretch": "Unlocks full run tracking",
    "bonus_scan": "+1 use today",
    "bonus_coins": "+10% coins on this quest",
}


class AdCard(ft.Container):
    """The dev placeholder: 'Ad (test)', a AD_SECONDS countdown and Skip. on_done(result) is
    called once with "watched" (timer ran out) or "skipped"."""

    def __init__(self, page: ft.Page, placement: str,
                 on_done: Callable[[str], Any], *, seconds: int = premium.AD_SECONDS) -> None:
        self.page_ref, self.placement, self.on_done = page, placement, on_done
        self.seconds = seconds
        self.result: str | None = None
        self.bar = ft.ProgressBar(value=0, color=GOLD, bgcolor=C.a(C.TEXT, 0.1), height=6,
                                  border_radius=3)
        self.count = ft.Text(f"{seconds} s", size=Type.CAPTION, color=C.TEXT_DIM)
        self.skip = ft.TextButton("Skip ad", icon=ft.Icons.SKIP_NEXT, height=Size.TAP,
                                  on_click=self._skip, style=ft.ButtonStyle(color=C.TEXT_DIM))
        self.status = ft.Text("", size=Type.CAPTION, color=C.TEXT_DIM, visible=False)
        super().__init__(
            ft.Column([
                ft.Row([
                    ft.Container(ft.Text("AD (TEST)", size=10, weight=ft.FontWeight.BOLD,
                                         color=C.BG), bgcolor=GOLD, border_radius=Radius.PILL,
                                 padding=ft.Padding.symmetric(horizontal=8, vertical=2)),
                    ft.Text(PLACEMENT_TEXT.get(placement, "Reward"), size=Type.CAPTION,
                            color=C.TEXT, expand=True),
                    self.count,
                ], spacing=Space.SM, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Container(
                    ft.Column([ft.Icon(ft.Icons.SMART_DISPLAY, size=34, color=C.a(GOLD, 0.8)),
                               ft.Text("Test ad placeholder · no real ad, nothing tracked",
                                       size=Type.CAPTION, color=C.TEXT_DIM,
                                       text_align=ft.TextAlign.CENTER)],
                              spacing=Space.XS, tight=True,
                              horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    height=92, alignment=ft.Alignment.CENTER, border_radius=Radius.SM,
                    bgcolor=C.a(GOLD, 0.06), border=ft.Border.all(1, C.a(GOLD, 0.3))),
                self.bar,
                ft.Row([self.status, ft.Container(expand=True), self.skip],
                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ], spacing=Space.SM, tight=True),
            bgcolor=C.SURFACE_HI, border_radius=Radius.MD, padding=Space.MD,
            border=ft.Border.all(1, C.a(GOLD, 0.45)), key=f"ad:{placement}",
        )

    def start(self) -> None:
        self.page_ref.run_task(self._run)

    async def _run(self) -> None:
        t0 = time.monotonic()
        while self.result is None:
            left = self.seconds - (time.monotonic() - t0)
            if left <= 0:
                break
            self.bar.value = 1 - left / self.seconds
            self.count.value = f"{int(left) + 1} s"
            ui.refresh(self.bar, self.count)
            await asyncio.sleep(0.25)
        if self.result is None:
            self._finish("watched")

    def _skip(self, _: Any = None) -> None:
        if self.result is None:
            sfx.play("back")
            self._finish("skipped")

    def _finish(self, result: str) -> None:
        self.result = result
        watched = result == "watched"
        self.bar.value = 1 if watched else self.bar.value
        self.count.value = ""
        self.skip.visible = False
        self.status.visible = True
        self.status.value = "Thanks! Reward unlocked." if watched else "Ad skipped."
        self.status.color = C.SUCCESS if watched else C.TEXT_DIM
        if watched:
            sfx.play("granted")
        ui.refresh(self)
        self.on_done(result)


def _available(app: App) -> bool:
    """An ad can be shown: Part 1 = the dev placeholder only (Part 2: AdMob loaded)."""
    return app.game.dev_allowed()


def can_show(app: App) -> bool:
    return premium.shows_ads(app.game.is_premium(app.today())) and _available(app)


async def show_rewarded(app: App, placement: str) -> str:
    """Show one opt-in rewarded ad. Premium: never ("unavailable")."""
    if placement not in premium.AD_PLACEMENTS:
        raise ValueError(f"unknown placement: {placement}")
    if not can_show(app):
        return "unavailable"
    fut: asyncio.Future[str] = asyncio.get_running_loop().create_future()

    def done(result: str) -> None:
        async def later() -> None:
            await asyncio.sleep(0.8 if result == "watched" else 0.2)
            common.close(dlg)
            if not fut.done():
                fut.set_result(result)
        app.page.run_task(later)

    card = AdCard(app.page, placement, done)

    def dismissed(_: Any) -> None:
        if not fut.done():
            fut.set_result(card.result or "skipped")

    dlg = ft.AlertDialog(content=ft.Container(card, width=320), bgcolor=C.SURFACE,
                         modal=True, on_dismiss=dismissed,
                         content_padding=ft.Padding.all(Space.SM))
    app.page.show_dialog(dlg)
    card.start()
    return await fut


# ---------------------------------------------------------------------- free-limit sheet


async def limit_gate(app: App, feature: str, *, manual: Callable[[], Any] | None = None,
                     manual_label: str = "Enter it by hand") -> bool:
    """True if `feature` can be used now. When the allowance is empty, a calm sheet offers:
    watch an ad for +1 (free, opt-in), see the premium page, or the manual way (never
    blocked). Returns True only if a bonus was granted. The caller spends the use
    (`spend`) once the action really happens (e.g. a photo was taken)."""
    g, today = app.game, app.today()
    if g.can_use(feature, today):
        return True
    lim = premium.LIMITS[feature]
    is_prem = g.is_premium(today)
    app.offer_premium("limit")
    sfx.play("error_soft")
    fut: asyncio.Future[str] = asyncio.get_running_loop().create_future()

    def pick(choice: str) -> Callable[[Any], None]:
        def go(_: Any = None) -> None:
            if not fut.done():
                fut.set_result(choice)
            common.close(sheet)
        return go

    resets = premium.resets_on(is_prem, today)
    when = "tomorrow" if not is_prem else f"Monday {common.short_date(resets)}"
    body: list[ft.Control] = [
        common.hint(f"{lim.label}: {premium.allowance(feature, is_prem)} "
                    f"{'a week' if is_prem else 'a day'}. They refill {when}."),
    ]
    buttons: list[ft.Control] = []
    if can_show(app) and g.bonus_left(feature, today) > 0:
        buttons.append(common.primary_button("Watch an ad for +1", pick("ad"),
                                             icon=ft.Icons.SMART_DISPLAY))
    if not is_prem:
        buttons.append(common.secondary_button(f"See {premium.PREMIUM_NAME}", pick("premium"),
                                               icon=ft.Icons.WORKSPACE_PREMIUM, color=GOLD))
    if manual is not None:
        buttons.append(common.secondary_button(manual_label, pick("manual"),
                                               icon=ft.Icons.EDIT_NOTE))
    body += [ft.Row([b], spacing=Space.SM) for b in buttons]
    body.append(common.hint("Typing it in yourself is always free and unlimited."
                            if manual is not None else "Everything else keeps working."))
    title = ("This week's bank is used" if is_prem else f"Today's free {lim.unit} are used")
    sheet = common.open_sheet(app.page, title, body,
                              on_dismiss=lambda: None if fut.done() else fut.set_result(""))
    choice = await fut
    if choice == "ad":
        await asyncio.sleep(0.3)  # let the sheet close first
        result = await show_rewarded(app, "bonus_scan")
        if result == "watched" and g.grant_bonus(feature, 1, app.today()):
            app.save()
            app.toast("+1 use added for today", ft.Icons.CELEBRATION)
            return True
        if result == "skipped":
            app.toast("No problem. Manual entry still works.", ft.Icons.INFO_OUTLINE)
        else:
            app.toast("No ad available right now.", ft.Icons.INFO_OUTLINE)
        return False
    if choice == "premium":
        app.open_sub("premium")
    elif choice == "manual" and manual is not None:
        res = manual()
        if asyncio.iscoroutine(res):
            await res
    return False


def spend(app: App, feature: str) -> None:
    """Count one use (after the action really happened) and save."""
    if app.game.use(feature, app.today()):
        app.save()
