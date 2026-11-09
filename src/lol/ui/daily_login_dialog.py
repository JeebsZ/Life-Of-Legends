"""Daily Login Streak Dialog (7-Day & 30-Day Rewards Track) for Life of Legends.

Displays the current login streak, 7-day card strip, expandable full 30-day track,
milestone rewards (Day 7 cosmetic title, Day 14/28 frames, Day 30 companion pet),
and an interactive claiming animation with sound and haptic feedback.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import flet as ft

from lol.core import daily_login
from lol.ui import components as ui
from lol.ui import sfx
from lol.ui import theme as th
from lol.ui.screens import common
from lol.ui.theme import Radius, Space, Type

if TYPE_CHECKING:
    from lol.ui.app import App


def prompt_daily_login(app: App, *, force: bool = False) -> ft.BottomSheet | None:
    """Prompt the user with the Daily Login modal if today's reward is unclaimed."""
    p = app.game.profile
    if not force and (not p.onboarded):
        return None

    status = daily_login.check_daily_status(p, app.today())
    if not force and status.claimed_today:
        return None

    # Dialog state
    is_expanded = [False]
    active_status = [status]
    sheet_ref: list[ft.BottomSheet | None] = [None]
    today_cards: list[ft.Container] = []

    def close_dlg(_: Any = None) -> None:
        if sheet_ref[0] is not None:
            common.close(sheet_ref[0])

    # Dynamic track container
    track_column = ft.Column(spacing=Space.SM, tight=True)
    claim_area = ft.Column(spacing=Space.SM, tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
    streak_label = ft.Text(
        f"🔥 {status.streak}-Day Login Streak",
        size=Type.TITLE,
        weight=ft.FontWeight.W_800,
        color=th.C.GOLD,
    )

    def build_day_card(day_num: int, reward: daily_login.DailyReward, is_today: bool, is_claimed: bool) -> ft.Container:
        """Card for a single day in the reward strip."""
        if is_claimed:
            bg_col = th.C.a(th.C.SUCCESS, 0.12)
            border_col = th.C.a(th.C.SUCCESS, 0.6)
            status_icon = ft.Icon(ft.Icons.CHECK_CIRCLE, size=16, color=th.C.SUCCESS)
            status_text = "Claimed"
            text_col = th.C.SUCCESS
        elif is_today:
            bg_col = th.C.a(th.C.GOLD, 0.22)
            border_col = th.C.GOLD
            status_icon = ft.Icon(ft.Icons.AUTO_AWESOME, size=16, color=th.C.GOLD)
            status_text = "READY!"
            text_col = th.C.GOLD
        else:
            bg_col = th.C.a(th.C.SURFACE_HI, 0.4)
            border_col = th.C.a(th.C.TEXT_DIM, 0.25)
            status_icon = ft.Icon(ft.Icons.LOCK_OUTLINE, size=14, color=th.C.TEXT_DIM)
            status_text = f"Day {day_num}"
            text_col = th.C.TEXT_DIM

        # Icon for reward
        if reward.cosmetic_id:
            ico_name = ft.Icons.PETS if "pet" in reward.cosmetic_id else ft.Icons.MILITARY_TECH
            ico_col = th.C.GOLD
        elif reward.is_milestone:
            ico_name = ft.Icons.WORKSPACE_PREMIUM
            ico_col = th.C.PRIMARY
        else:
            ico_name = ft.Icons.SAVINGS
            ico_col = th.C.GOLD if is_today else th.C.TEXT

        card = ft.Container(
            content=ft.Column(
                [
                    ft.Text(f"Day {day_num}", size=Type.LABEL - 1, weight=ft.FontWeight.BOLD, color=text_col),
                    ft.Icon(ico_name, size=24, color=ico_col),
                    ft.Text(f"+{reward.coins}c", size=Type.LABEL - 1, weight=ft.FontWeight.BOLD, color=th.C.GOLD),
                    ft.Text(f"+{reward.xp}xp", size=Type.LABEL - 2, color=th.C.PRIMARY),
                    status_icon,
                    ft.Text(status_text, size=Type.LABEL - 2, weight=ft.FontWeight.W_600, color=text_col),
                ],
                spacing=2,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            width=76,
            height=120,
            border_radius=Radius.MD,
            bgcolor=bg_col,
            border=ft.Border.all(2 if is_today else 1, border_col),
            padding=ft.Padding.all(4),
            alignment=ft.Alignment.CENTER,
            animate_scale=th.Motion.anim(200),
        )

        if is_today:
            today_cards.append(card)

        return card

    def render_track() -> None:
        """Render either the 7-day strip or the full 30-day track grid."""
        cur_stat = active_status[0]
        cur_day = cur_stat.current_day
        claimed_set = set(cur_stat.claimed_days)
        today_cards.clear()

        # Update streak label
        streak_label.value = (
            f"🔥 {cur_stat.streak}-Day Login Streak"
            if cur_stat.streak > 0
            else "Start Your 30-Day Legend Streak!"
        )

        track_column.controls.clear()

        if not is_expanded[0]:
            # 7-day strip view (Week 1 or current cycle week)
            cards = []
            for d in range(1, 8):
                rew = daily_login.get_reward(d)
                is_claimed = d in claimed_set
                is_today = (d == cur_day) and not cur_stat.claimed_today
                cards.append(build_day_card(d, rew, is_today, is_claimed))

            track_column.controls.append(
                ft.Row(
                    cards,
                    scroll=ft.ScrollMode.AUTO,
                    spacing=Space.SM,
                    alignment=ft.MainAxisAlignment.START,
                )
            )
        else:
            # 30-day full track grid
            rows: list[ft.Row] = []
            row_items: list[ft.Control] = []
            for d in range(1, 31):
                rew = daily_login.get_reward(d)
                is_claimed = d in claimed_set
                is_today = (d == cur_day) and not cur_stat.claimed_today
                row_items.append(build_day_card(d, rew, is_today, is_claimed))
                if len(row_items) == 5 or d == 30:
                    rows.append(
                        ft.Row(
                            row_items,
                            scroll=ft.ScrollMode.AUTO,
                            spacing=Space.XS,
                            alignment=ft.MainAxisAlignment.CENTER,
                        )
                    )
                    row_items = []

            track_column.controls.append(
                ft.Column(
                    rows,
                    spacing=Space.XS,
                    tight=True,
                    scroll=ft.ScrollMode.AUTO,
                )
            )

    def toggle_expand(_: Any = None) -> None:
        is_expanded[0] = not is_expanded[0]
        expand_btn.text = "Show 7-Day View" if is_expanded[0] else "View Full 30-Day Track"
        expand_btn.icon = ft.Icons.UNFOLD_LESS if is_expanded[0] else ft.Icons.UNFOLD_MORE
        render_track()
        if sheet_ref[0] is not None and sheet_ref[0].page:
            sheet_ref[0].update()

    expand_btn = common.secondary_button(
        "View Full 30-Day Track",
        toggle_expand,
        icon=ft.Icons.UNFOLD_MORE,
        color=th.C.PRIMARY,
    )

    async def on_claim(_: Any = None) -> None:
        claim_btn.disabled = True
        claim_btn.text = "Claiming..."
        if sheet_ref[0] and sheet_ref[0].page:
            sheet_ref[0].update()

        res = daily_login.claim_daily_login(app.game, app.today())
        if not res:
            render_claim_area()
            if sheet_ref[0] and sheet_ref[0].page:
                sheet_ref[0].update()
            return

        # Success! Trigger juice animations and sound
        if res.reward.is_milestone:
            sfx.play("milestone", 0.9)
            await ui.buzz("heavy")
        else:
            sfx.play("coin_many", 0.8)
            await ui.buzz("medium")

        app.space.pulse(th.C.GOLD, 1.2)

        # Refresh active status
        active_status[0] = daily_login.check_daily_status(app.game.profile, app.today())

        # Update track and claim button
        render_track()
        render_claim_area()

        # Pop effect on today's card
        for card in today_cards:
            app.page.run_task(ui.pop, card, 1.25)

        # Award floaters in header
        app.page.run_task(app.coin_float.coins, res.coins_awarded)
        app.page.run_task(app.xp_float.xp, res.xp_awarded)
        app.page.run_task(app.coins_changed)
        app.refresh_profile()

        # Level up notification if reached
        if res.levels_gained > 0:
            app.page.run_task(
                app.banner.show,
                app.game.profile.level,
                title="LEVEL UP!",
                subtitle="Daily streak power surge!",
            )

        # Cosmetic announcement if unlocked
        if res.cosmetic_awarded:
            cosmetic_title = res.reward.title or res.reward.description
            app.lumen("cosmetic_unlocked", ft.Icons.AUTO_AWESOME, title=f"Unlocked: {cosmetic_title}")

        if sheet_ref[0] and sheet_ref[0].page:
            sheet_ref[0].update()

    def render_claim_area() -> None:
        """Render the bottom action and reward highlight."""
        cur_stat = active_status[0]
        claim_area.controls.clear()

        rew = cur_stat.reward_today

        # Reward chips row
        chips = [
            ui.coin_chip(rew.coins),
            ui.xp_chip(rew.xp),
        ]
        if rew.cosmetic_id:
            tag = "Title" if "title" in rew.cosmetic_id else "Pet" if "pet" in rew.cosmetic_id else "Frame"
            chips.append(ui.chip(f"{tag}: {rew.title}", color=th.C.GOLD, icon=ft.Icons.WORKSPACE_PREMIUM))

        reward_box = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.CARD_GIFTCARD, color=th.C.GOLD, size=18),
                            ft.Text(
                                f"Day {cur_stat.current_day} Reward: {rew.title}",
                                size=Type.BODY,
                                weight=ft.FontWeight.BOLD,
                                color=th.C.TEXT,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                    ft.Row(chips, alignment=ft.MainAxisAlignment.CENTER, spacing=Space.SM),
                    ft.Text(
                        rew.description,
                        size=Type.LABEL,
                        color=th.C.TEXT_DIM,
                        text_align=ft.TextAlign.CENTER,
                    ),
                ],
                spacing=Space.XS,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=th.C.a(th.C.SURFACE_HI, 0.5),
            border=ft.Border.all(1, th.C.a(th.C.GOLD, 0.4)),
            border_radius=Radius.MD,
            padding=ft.Padding.symmetric(vertical=Space.SM, horizontal=Space.MD),
            alignment=ft.Alignment.CENTER,
        )

        claim_area.controls.append(reward_box)

        if not cur_stat.claimed_today:
            claim_btn.disabled = False
            claim_btn.text = f"Claim Day {cur_stat.current_day} Reward"
            claim_btn.icon = ft.Icons.AUTO_AWESOME
            claim_area.controls.append(
                ft.Row([claim_btn], alignment=ft.MainAxisAlignment.CENTER)
            )
        else:
            claim_area.controls.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Icon(ft.Icons.CHECK_CIRCLE, color=th.C.SUCCESS, size=20),
                            ft.Text(
                                "Today's reward already claimed! Come back tomorrow.",
                                size=Type.BODY,
                                color=th.C.SUCCESS,
                                weight=ft.FontWeight.W_600,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                        spacing=Space.XS,
                    ),
                    padding=ft.Padding.only(top=Space.XS, bottom=Space.XS),
                )
            )
            claim_area.controls.append(
                ft.Row(
                    [
                        common.primary_button("Awesome!", close_dlg, icon=ft.Icons.CHECK)
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                )
            )

    claim_btn = common.primary_button(
        f"Claim Day {status.current_day} Reward",
        on_claim,
        icon=ft.Icons.AUTO_AWESOME,
    )

    render_track()
    render_claim_area()

    # Modal header with flame badge
    header_content = ft.Row(
        [
            ft.Container(
                ft.Icon(ft.Icons.LOCAL_FIRE_DEPARTMENT, size=32, color=th.C.GOLD),
                width=52,
                height=52,
                shape=ft.BoxShape.CIRCLE,
                bgcolor=th.C.a(th.C.GOLD, 0.16),
                border=ft.Border.all(1.5, th.C.a(th.C.GOLD, 0.7)),
                alignment=ft.Alignment.CENTER,
            ),
            ft.Column(
                [
                    streak_label,
                    ft.Text(
                        "Log in daily to unlock scaling Coins, XP, and Exclusive Cosmetics!",
                        size=Type.LABEL,
                        color=th.C.TEXT_DIM,
                    ),
                ],
                spacing=2,
                expand=True,
            ),
        ],
        spacing=Space.SM,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    body = [
        header_content,
        ft.Divider(height=1, color=th.C.a(th.C.TEXT, 0.1)),
        track_column,
        ft.Row([expand_btn], alignment=ft.MainAxisAlignment.CENTER),
        ft.Container(height=Space.XS),
        claim_area,
    ]

    sheet = common.open_sheet(app.page, "Daily Login Rewards", body)
    sheet_ref[0] = sheet
    return sheet
