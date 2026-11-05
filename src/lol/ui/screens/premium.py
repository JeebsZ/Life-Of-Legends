"""More -> Legends+ (name: core.premium.PREMIUM_NAME): the premium offer page.

Soft, honest offer: benefits, plans (monthly / yearly best value / lifetime), the active season
deal with its real end date, a student code field, Restore purchases, plain trial terms and a
clear close. No store yet (Part 2): purchase buttons say so; in a dev build they can simulate
premium through the dev toggle. Prices and dates live in core/premium.py."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any

import flet as ft

from lol.core import premium
from lol.core.premium import PREMIUM_NAME
from lol.ui import components as ui
from lol.ui import sfx, voice
from lol.ui.screens import common
from lol.ui.theme import C, Motion, Radius, Size, Space, Type

if TYPE_CHECKING:
    from lol.ui.app import App

GOLD = "#F5C66B"
STORE_MISSING = "Store not connected yet. Purchases arrive in a later update."


def benefits() -> list[tuple[ft.IconData, str, str]]:
    """(icon, title, detail) from the limits table, so the page never drifts from the rules."""
    L = premium.LIMITS
    return [
        (ft.Icons.BLOCK, "No ads, ever", "Not even the optional ones."),
        (ft.Icons.SAVINGS, "A big weekly bank",
         (f"{L['meal_scan'].premium_weekly} meal scans, {L['generate_steps'].premium_weekly} "
          f"Luma step drafts and {L['note_scan'].premium_weekly} note scans a week "
          f"(free: {L['meal_scan'].free_daily}, {L['generate_steps'].free_daily} and "
          f"{L['note_scan'].free_daily} a day).")),
        (ft.Icons.DIRECTIONS_RUN, "Full run tracking, every run",
         "Map, pace, splits and kcal without the stretch ad, plus all your run history."),
        (ft.Icons.ROUTE, "Unlimited custom side quests",
         f"Free keeps {premium.ACTIVE_CAPS['custom_chains'][0]} running at a time."),
        (ft.Icons.QUERY_STATS, "Insights for all time", "Free shows the last 7 days."),
        (ft.Icons.PALETTE, "Premium themes and cosmetics",
         "Unlocks the right to buy them with the coins you earn. Coins are never sold."),
    ]


ALWAYS_FREE = ("Quests, bills and rewards", "Safety notes and limits", "Your data export",
               "Accessibility and reduce motion", "Typing meals and notes by hand")


class PremiumScreen:
    title = PREMIUM_NAME

    def __init__(self, app: App) -> None:
        self.app = app
        self.plan = "yearly"
        self.list = common.screen_list()
        self.view = ft.Container(self.list, expand=True, key="premium")
        self.trailing = ft.IconButton(ft.Icons.CLOSE, icon_color=C.TEXT, tooltip="Close",
                                      width=Size.TAP, height=Size.TAP,
                                      on_click=lambda e: self.app.more.back())
        self.plan_cards: dict[str, ft.Container] = {}

    def _refresh(self) -> None:
        self.render()
        ui.refresh(self.list)

    def restyle(self) -> None:
        self._refresh()

    # ------------------------------------------------------------------ render
    def render(self) -> None:
        g, today = self.app.game, self.app.today()
        is_prem = g.is_premium(today)
        items: list[ft.Control] = [self._hero(is_prem)]
        deals = premium.active_deals(today)
        if deals and not is_prem:
            items.append(self._deal(deals[0]))
        items.append(ui.SectionHeader("What you get"))
        items.append(common.card(ft.Column(
            [self._benefit(*b) for b in benefits()], spacing=Space.MD, tight=True)))
        if not is_prem:
            items.append(ui.SectionHeader("Pick a plan"))
            self.plan_cards = {p.id: self._plan_card(p) for p in premium.PLANS}
            items.append(ft.Column(list(self.plan_cards.values()), spacing=Space.SM,
                                   tight=True))
            items.append(ft.Container(common.primary_button(
                f"Start {premium.TRIAL_DAYS}-day free trial" if self.plan != "lifetime"
                else "Buy lifetime", self._buy, icon=ft.Icons.WORKSPACE_PREMIUM), height=56))
            items.append(common.hint(self._terms()))
            items.append(self._promo())
        items.append(ft.Row([common.secondary_button("Restore purchases", self._restore,
                                                     icon=ft.Icons.RESTORE)]))
        items.append(ui.SectionHeader("Always free"))
        items.append(common.card(ft.Column([
            ft.Row([ft.Icon(ft.Icons.CHECK_CIRCLE, size=18, color=C.SUCCESS),
                    ft.Text(t, size=Type.BODY, color=C.TEXT, expand=True)], spacing=Space.SM)
            for t in ALWAYS_FREE], spacing=Space.SM, tight=True)))
        items.append(ft.Container(common.hint(
            "Your support keeps LUMA: Your Lifestyle QoL growing. No pressure: the core game "
            "stays free forever."), alignment=ft.Alignment.CENTER, padding=Space.SM))
        self.list.controls = items

    def _hero(self, is_prem: bool) -> ft.Control:
        ent = self.app.game.entitlement()
        sub = (f"Active ({'dev toggle' if ent.source == 'dev' else 'store'}). Thank you!"
               if is_prem else "Support the app, unlock the big weekly bank. "
               "The core stays free forever.")
        return ft.Container(ft.Column([
            ft.Container(ft.Icon(ft.Icons.WORKSPACE_PREMIUM, size=40, color=C.BG), width=72,
                         height=72, border_radius=36, alignment=ft.Alignment.CENTER,
                         gradient=ft.LinearGradient(colors=[GOLD, "#E8A33D"],
                                                    begin=ft.Alignment.TOP_LEFT,
                                                    end=ft.Alignment.BOTTOM_RIGHT),
                         shadow=ft.BoxShadow(blur_radius=24, color=C.a(GOLD, 0.45))),
            ft.Text(PREMIUM_NAME, size=Type.HEADLINE + 6, weight=ft.FontWeight.W_900,
                    color=C.TEXT),
            ft.Text(sub, size=Type.BODY, color=C.TEXT_DIM, text_align=ft.TextAlign.CENTER),
        ], spacing=Space.SM, tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            padding=Space.LG, border_radius=Radius.LG,
            gradient=ft.LinearGradient(colors=[C.a(GOLD, 0.16), C.a(C.PRIMARY, 0.08)],
                                       begin=ft.Alignment.TOP_CENTER,
                                       end=ft.Alignment.BOTTOM_CENTER),
            border=ft.Border.all(1, C.a(GOLD, 0.35)))

    def _deal(self, d: premium.ShopOffer) -> ft.Control:
        today = self.app.today()
        left = premium.days_left(d, today) or 0
        end = date.fromisoformat(d.ends_on) if d.ends_on else today
        return ft.Container(ft.Row([
            ft.Icon(ft.Icons.LOCAL_OFFER, color=C.BG, size=22),
            ft.Column([
                ft.Text(f"{d.title}: ₱{d.price_php} first month", size=Type.BODY,
                        weight=ft.FontWeight.W_800, color=C.BG),
                ft.Text(f"Then ₱{d.regular_php}/month. Ends {common.short_date(end)} "
                        f"({left} day{'s' if left != 1 else ''} left).", size=Type.CAPTION,
                        color=C.a(C.BG, 0.85)),
            ], spacing=0, tight=True, expand=True),
        ], spacing=Space.MD, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            bgcolor=GOLD, border_radius=Radius.MD, padding=Space.MD, key="season_deal",
            on_click=lambda e: self._pick("monthly"), ink=True)

    @staticmethod
    def _benefit(icon: ft.IconData, title: str, detail: str) -> ft.Control:
        return ft.Row([
            ft.Container(ft.Icon(icon, size=20, color=GOLD), width=36, height=36,
                         border_radius=18, bgcolor=C.a(GOLD, 0.14),
                         alignment=ft.Alignment.CENTER),
            ft.Column([ft.Text(title, size=Type.BODY, weight=ft.FontWeight.W_700,
                               color=C.TEXT), common.hint(detail)],
                      spacing=0, tight=True, expand=True),
        ], spacing=Space.MD, vertical_alignment=ft.CrossAxisAlignment.START)

    def _plan_card(self, p: premium.ShopOffer) -> ft.Container:
        on = p.id == self.plan
        unit = {"month": "/month", "year": "/year", "once": " once"}[p.period]
        sub = (f"₱{premium.per_month(p)}/month, billed yearly" if p.period == "year"
               else "Pay once, yours for good" if p.period == "once"
               else "Cancel anytime")
        badge = ft.Container(ft.Text(p.note.upper(), size=10, weight=ft.FontWeight.BOLD,
                                     color=C.BG), bgcolor=GOLD, border_radius=Radius.PILL,
                             padding=ft.Padding.symmetric(horizontal=8, vertical=2),
                             visible=p.id == "yearly")
        return ft.Container(ft.Row([
            ft.Icon(ft.Icons.RADIO_BUTTON_CHECKED if on else ft.Icons.RADIO_BUTTON_OFF,
                    color=GOLD if on else C.TEXT_DIM, size=22),
            ft.Column([ft.Row([ft.Text(p.title, size=Type.BODY, weight=ft.FontWeight.W_700,
                                       color=C.TEXT), badge], spacing=Space.SM),
                       common.hint(sub)], spacing=0, tight=True, expand=True),
            ft.Text(f"₱{p.price_php:,}{unit}", size=Type.BODY, weight=ft.FontWeight.W_800,
                    color=C.TEXT),
        ], spacing=Space.MD, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=Space.MD, border_radius=Radius.MD, data=p.id, key=f"plan:{p.id}",
            bgcolor=C.a(GOLD, 0.1) if on else C.SURFACE,
            border=ft.Border.all(2 if on else 1, GOLD if on else C.OUTLINE),
            on_click=lambda e, pid=p.id: self._pick(pid), ink=True, scale=1,
            animate_scale=Motion.anim(Motion.POP_MS, Motion.BACK))

    def _pick(self, plan_id: str) -> None:
        if plan_id == self.plan:
            return
        sfx.play("toggle")
        self.plan = plan_id
        self._refresh()

    def _terms(self) -> str:
        if self.plan == "lifetime":
            return ("Lifetime is a one-time payment of ₱1,990 through Google Play. No "
                    "subscription, no renewals.")
        p = premium.plan(self.plan)
        per = "month" if p.period == "month" else "year"
        return (f"{premium.TRIAL_DAYS} days free, then ₱{p.price_php:,} per {per}. It renews "
                f"automatically until you cancel. Cancel any time in Google Play → "
                f"Subscriptions, at least a day before the trial ends to pay nothing.")

    def _promo(self) -> ft.Control:
        field = common.text_field("Student or promo code")
        field.capitalization = ft.TextCapitalization.CHARACTERS

        def apply(_: Any = None) -> None:
            ok, msg = premium.check_promo(field.value or "")
            field.error_text = None if ok else msg
            ui.refresh(field)
            if ok:
                sfx.play("granted")
                self.app.toast(msg, ft.Icons.SCHOOL)
            else:
                sfx.play("error_soft")

        field.on_submit = apply
        return common.card(ft.Column([
            ft.Row([ft.Icon(ft.Icons.SCHOOL, color=C.PRIMARY, size=20),
                    ft.Text("Student discount", size=Type.BODY, weight=ft.FontWeight.W_700,
                            color=C.TEXT)], spacing=Space.SM),
            common.hint("Got a school or promo code? Enter it here; it applies when the store "
                        "is connected."),
            field,
            ft.Row([common.secondary_button("Apply code", apply, icon=ft.Icons.CHECK)]),
        ], spacing=Space.SM, tight=True), padding=Space.MD)

    # ------------------------------------------------------------------ actions
    async def _buy(self, _: Any = None) -> None:
        app = self.app
        if not app.game.dev_allowed():
            sfx.play("error_soft")
            app.toast(STORE_MISSING, ft.Icons.STOREFRONT)
            return
        ok = await common.confirm(app.page, "Store not connected yet",
                                  "This is a dev build. Simulate premium with the dev toggle? "
                                  "Nothing is charged.", "Simulate")
        if not ok:
            return
        app.game.set_dev_premium(True)
        app.save()
        app.notice.say(voice.say("premium_on", name=PREMIUM_NAME), ft.Icons.WORKSPACE_PREMIUM)
        app.page.run_task(app.reveal, PREMIUM_NAME, "Simulated · dev toggle")
        self._refresh()

    def _restore(self, _: Any = None) -> None:
        self.app.toast("Store not connected yet. Nothing to restore.", ft.Icons.RESTORE)


# ---------------------------------------------------------------------- Settings blocks
APP_VERSION = "0.1.0"  # keep in step with pyproject.toml


def _usage_row(app: App, feature: str) -> ft.Control:
    g, today = app.game, app.today()
    lim = premium.LIMITS[feature]
    is_prem = g.is_premium(today)
    left = g.remaining(feature, today)
    total = (premium.allowance(feature, is_prem) or 0) + max(
        0, premium.AD_BONUS_MAX_PER_DAY - g.bonus_left(feature, today)) * (not is_prem)
    span = "this week" if is_prem else "today"
    when = (f"refills Monday {common.short_date(premium.resets_on(True, today))}" if is_prem
            else "refills tomorrow")
    frac = (left or 0) / total if total else 1.0
    return ft.Column([
        ft.Row([ft.Text(lim.label, size=Type.BODY, color=C.TEXT, expand=True),
                ft.Text("unlimited" if left is None else f"{left} of {total} left {span}",
                        size=Type.CAPTION, weight=ft.FontWeight.W_700,
                        color=C.TEXT if left else C.DANGER)]),
        ft.ProgressBar(value=frac, color=GOLD if is_prem else C.PRIMARY,
                       bgcolor=C.a(C.TEXT, 0.1), height=5, border_radius=3),
        common.hint(when),
    ], spacing=2, tight=True)


def settings_blocks(app: App, on_change: Any) -> list[ft.Control]:
    """Settings: the premium status + remaining uses, the version label (tap it DEV_TAPS times
    to reveal Developer) and, when revealed, the Developer section."""
    g, today = app.game, app.today()
    is_prem = g.is_premium(today)
    chains = g.custom_chains_active()
    cap = premium.active_cap("custom_chains", is_prem)
    rows: list[ft.Control] = [
        ft.Row([ft.Icon(ft.Icons.WORKSPACE_PREMIUM, color=GOLD, size=22),
                ft.Text(f"{PREMIUM_NAME}: {'active' if is_prem else 'not active'}",
                        size=Type.BODY, weight=ft.FontWeight.W_700, color=C.TEXT,
                        expand=True),
                ft.TextButton("Open", height=Size.TAP, style=ft.ButtonStyle(color=GOLD),
                              on_click=lambda e: app.more.open("premium"))],
               vertical_alignment=ft.CrossAxisAlignment.CENTER),
        common.hint("Free uses refill every day; premium uses a big weekly bank that refills "
                    "on Monday. Typing things in by hand is always unlimited."),
    ]
    rows += [_usage_row(app, f) for f in premium.LIMITS]
    rows.append(ft.Row([
        ft.Text("Custom side quests running", size=Type.BODY, color=C.TEXT, expand=True),
        ft.Text(f"{chains} of {cap}" if cap is not None else f"{chains} · unlimited",
                size=Type.CAPTION, weight=ft.FontWeight.W_700, color=C.TEXT)]))
    out: list[ft.Control] = [ui.SectionHeader(f"{PREMIUM_NAME} & limits"),
                             common.card(ft.Column(rows, spacing=Space.MD, tight=True),
                                         padding=Space.MD)]
    if g.dev_allowed():
        out += [ui.SectionHeader("Developer"), _dev_card(app, on_change)]
    out.append(_version_label(app, on_change))
    return out


def _dev_card(app: App, on_change: Any) -> ft.Control:
    g = app.game

    def toggle(on: bool) -> None:
        g.set_dev_premium(on)
        app.save()
        app.toast(f"{PREMIUM_NAME} {'on' if on else 'off'} (dev toggle)",
                  ft.Icons.WORKSPACE_PREMIUM)
        on_change()

    def reset(_: Any = None) -> None:
        g.reset_usage()
        app.save()
        app.toast("Usage counters reset", ft.Icons.RESTART_ALT)
        on_change()

    st = g.data.premium
    return common.card(ft.Column([
        common.hint("Test switches only. Store builds ignore this whole section."),
        common.switch_row(f"Simulate {PREMIUM_NAME}", "Dev toggle, nothing is charged",
                          st.dev_premium, toggle, icon=ft.Icons.WORKSPACE_PREMIUM),
        ft.Row([common.secondary_button("Reset usage counters", reset,
                                        icon=ft.Icons.RESTART_ALT)]),
        common.hint(f"Ads: test placeholder only · non-personalized flag "
                    f"{'on (13-17)' if st.ads_non_personalized else 'off'}"),
    ], spacing=Space.SM, tight=True), padding=Space.MD)


def _version_label(app: App, on_change: Any) -> ft.Control:
    taps = {"n": 0}

    def tap(_: Any = None) -> None:
        if app.game.dev_allowed():
            return
        taps["n"] += 1
        left = premium.DEV_TAPS - taps["n"]
        if left <= 0 and app.game.unlock_dev():
            app.save()
            sfx.play("granted")
            app.toast("Developer options revealed", ft.Icons.BUILD)
            on_change()
        elif 0 < left <= 3:
            app.toast(f"{left} more tap{'s' if left > 1 else ''} for developer options",
                      ft.Icons.BUILD)

    return ft.Container(common.hint(f"LUMA: Your Lifestyle QoL v{APP_VERSION}"),
                        alignment=ft.Alignment.CENTER, height=Size.TAP, on_click=tap,
                        key="version_label")
