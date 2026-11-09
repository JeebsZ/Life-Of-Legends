"""Rewards tab: self-set personal rewards bought with coins, plus cosmetic themes."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import flet as ft

from lol.core import cosmetics as cos
from lol.core.models import Reward
from lol.core.premium import PREMIUM_NAME
from lol.ui import avatars, sfx
from lol.ui import components as ui
from lol.ui import theme as th
from lol.ui.screens import common, editors
from lol.ui.theme import C, Radius, Size, Space, Type

if TYPE_CHECKING:
    from lol.ui.app import App

COSMETIC_CAT_ICONS: dict[str, ft.IconData] = {
    "particles": ft.Icons.AUTO_AWESOME,
    "frame": ft.Icons.RADIO_BUTTON_CHECKED,
    "title": ft.Icons.MILITARY_TECH,
    "pet": ft.Icons.PETS,
    "fx_style": ft.Icons.BOLT,
}


class RewardsScreen:
    def __init__(self, app: App) -> None:
        self.app = app
        self.tiles: list[ui.RewardTile] = []
        self.theme_tiles: dict[str, ui.RewardTile] = {}
        self.cosmetic_tiles: dict[str, ui.RewardTile] = {}
        self.selected_cat: str = "theme"
        self.list = common.screen_list()
        self.view = ft.Container(self.list, expand=True, key="rewards")
        self.fab = ft.FloatingActionButton(icon=ft.Icons.ADD, on_click=self._open_add,
                                           bgcolor=C.PRIMARY, foreground_color=C.ON_PRIMARY,
                                           tooltip="New reward")

    # ------------------------------------------------------------------ render
    def render(self) -> None:
        g = self.app.game
        coins = g.profile.coins
        self.coin_text = ft.Text(f"You have {coins:,} coins", size=Type.TITLE,
                                 weight=ft.FontWeight.BOLD, color=C.TEXT)
        intro = common.card(ft.Row([
            ft.Icon(ft.Icons.REDEEM, color=C.ACCENT, size=28),
            ft.Column([
                self.coin_text,
                ft.Text("These are rewards you set for yourself, not real coupons. "
                        "Earn coins, then treat yourself for real.",
                        size=Type.LABEL, color=C.TEXT_DIM),
            ], spacing=2, expand=True, tight=True),
        ], spacing=Space.MD, vertical_alignment=ft.CrossAxisAlignment.START))

        wardrobe_sub = (
            "Create your chibi look and claim +200 free coins!"
            if not g.profile.avatar_bonus_claimed
            else "Customize your chibi hair, outfit, eyes, and stacked makeup."
        )
        wardrobe = common.card(
            ft.Row(
                [
                    avatars.bubble(
                        g.profile.avatar_id,
                        52,
                        custom=g.profile.avatar_customization,
                        frame_id=g.profile.frame_id,
                        pet_id=g.profile.pet_id,
                    ),
                    ft.Column(
                        [
                            ft.Text(
                                "Character Wardrobe",
                                size=Type.TITLE,
                                weight=ft.FontWeight.W_800,
                                color=C.TEXT,
                            ),
                            ft.Text(wardrobe_sub, size=Type.CAPTION, color=C.TEXT_DIM),
                        ],
                        spacing=2,
                        expand=True,
                        tight=True,
                    ),
                    common.secondary_button(
                        "Customize",
                        lambda _: avatars.open_character_editor(
                            self.app, on_saved=self._refresh
                        ),
                        icon=ft.Icons.FACE_RETOUCHING_NATURAL,
                        expand=False,
                    ),
                ],
                spacing=Space.MD,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=Space.MD,
        )

        personal = [r for r in g.rewards if r.kind == "personal"]
        self.tiles = []
        items: list[ft.Control] = [
            intro,
            wardrobe,
            ui.SectionHeader("My rewards", count=len(personal), action_text="New",
                             on_action=self._open_add),
        ]
        if personal:
            grid = []
            for r in personal:
                tile = ui.RewardTile(r.title, r.cost, coins=coins, icon=ft.Icons.CARD_GIFTCARD,
                                     on_redeem=lambda t, rid=r.id: self._redeem(t, rid),
                                     data=r.id, note=r.note)
                self.tiles.append(tile)
                edit = ft.Container(
                    common.menu_button([
                        ("Edit", ft.Icons.EDIT, lambda rid=r.id: self._edit(rid)),
                        ("Archive", ft.Icons.ARCHIVE, lambda rid=r.id: self._archive(rid)),
                        ("Remove", ft.Icons.DELETE_OUTLINE,
                         lambda rid=r.id: self._delete(rid), True),
                    ], tooltip="Reward options"), right=0, top=0)
                grid.append(ft.Container(
                    ft.Stack([tile, edit]), col=6,
                    on_long_press=lambda e, rid=r.id: self._edit(rid)))
            items.append(ft.ResponsiveRow(grid, spacing=Space.SM, run_spacing=Space.SM))
            items.append(ft.Container(common.hint("Tap the dots (or long-press) to edit a "
                                                  "reward."), alignment=ft.Alignment.CENTER))
        else:
            items.append(ui.EmptyState(
                "Set your first reward", "A snack, a movie night, a new game. "
                "Pick a coin price that feels fair.", icon=ft.Icons.CARD_GIFTCARD,
                color=C.ACCENT, action_text="Add a reward", on_action=self._open_add))

        archived = g.archived_rewards()
        if archived:
            items.append(ui.SectionHeader("Archived", count=len(archived)))
            items += [self._archived_row(r) for r in archived]

        # --- Personalization Shop (Themes, Background FX, Frames, Titles, Pets, XP & Trail FX) ---
        items.append(ui.SectionHeader("Personalization Shop"))
        items.append(
            common.hint(
                "Customize themes, background particles, avatar frames, hero titles, "
                "companions, and XP/GPS trail glow."
            )
        )
        cat_chips: list[ft.Control] = []
        shop_cats = {"theme": "Themes", **cos.CATEGORIES}
        for cat_id, cat_label in shop_cats.items():
            active_cat = cat_id == self.selected_cat
            cat_chips.append(
                ft.Container(
                    ft.Row(
                        [
                            ft.Icon(
                                ft.Icons.PALETTE if cat_id == "theme" else COSMETIC_CAT_ICONS.get(cat_id, ft.Icons.STAR),
                                size=15,
                                color=C.ON_PRIMARY if active_cat else C.PRIMARY,
                            ),
                            ft.Text(
                                cat_label,
                                size=Type.CAPTION,
                                weight=ft.FontWeight.W_800,
                                color=C.ON_PRIMARY if active_cat else C.TEXT,
                            ),
                        ],
                        spacing=5,
                        tight=True,
                    ),
                    bgcolor=C.PRIMARY if active_cat else C.SURFACE_HI,
                    border=ft.Border.all(
                        1, C.PRIMARY if active_cat else C.a(C.PRIMARY, 0.28)
                    ),
                    border_radius=Radius.PILL,
                    padding=ft.Padding.symmetric(horizontal=12, vertical=7),
                    on_click=common.with_sound(lambda e, cid=cat_id: self._select_cat(cid)),
                    ink=True,
                )
            )
        items.append(ft.Row(cat_chips, spacing=Space.XS, wrap=True, run_spacing=Space.XS))

        if self.selected_cat == "theme":
            items.append(common.hint("Change how the whole app looks. Bought once, yours forever. "
                                     f"Crowned themes need {PREMIUM_NAME} to buy with coins."))
            theme_grid = []
            self.theme_tiles = {}
            for t in g.themes():
                pal = th.THEMES.get(t.id)
                if pal is None:
                    continue
                owned = t.id in g.profile.owned_themes
                theme_title = t.name if t.name.lower().endswith("theme") else f"{t.name} Theme"
                tile = ui.RewardTile(
                    theme_title, t.price, coins=coins, kind="theme",
                    swatch=[pal.primary, pal.surface_hi, pal.bg], owned=owned,
                    active=t.id == g.profile.theme_id,
                    on_redeem=lambda tl, tid=t.id: self._buy(tl, tid),
                    on_use=lambda tl, tid=t.id: self._use(tid), data=t.id,
                    crown=t.premium_only,
                    premium_locked=g.theme_status(t, self.app.today()) == "premium",
                    on_premium=lambda tl: self.app.open_sub("premium"))
                self.theme_tiles[t.id] = tile
                if not owned:
                    self.tiles.append(tile)
                theme_grid.append(ft.Container(tile, col=6))
            items.append(ft.ResponsiveRow(theme_grid, spacing=Space.SM, run_spacing=Space.SM))
        else:
            cos_grid: list[ft.Control] = []
            self.cosmetic_tiles = {}
            equipped_id = g.equipped_cosmetic_id(self.selected_cat)
            is_title_cat = self.selected_cat == "title"
            for c_item in cos.items_for_category(self.selected_cat):
                if is_title_cat:
                    owned_c = cos.is_title_unlocked(g, c_item.id)
                    active_c = g.is_title_equipped(c_item.id)
                else:
                    owned_c = c_item.id in g.profile.owned_cosmetics or c_item.price == 0
                    active_c = c_item.id == equipped_id
                sw = [
                    c_item.color,
                    c_item.secondary_color or c_item.color,
                    th.current().bg,
                ]
                label_title = (
                    f"{c_item.badge_text} {c_item.name}"
                    if c_item.category == "pet" and c_item.badge_text
                    else c_item.name
                )
                if is_title_cat:
                    eq_cnt = len(getattr(g.profile, "equipped_titles", []))
                    if not owned_c:
                        item_note = f"🔒 {c_item.subtitle}"
                    elif active_c:
                        item_note = f"✓ Equipped ({eq_cnt}/3 active)"
                    else:
                        item_note = "Unlocked · Tap to equip (up to 3)"
                else:
                    item_note = c_item.subtitle

                c_tile = ui.RewardTile(
                    label_title,
                    c_item.price,
                    coins=coins,
                    kind="theme",
                    swatch=sw,
                    owned=owned_c,
                    active=active_c,
                    on_redeem=lambda tl, cid=c_item.id: self._buy_cosmetic(tl, cid),
                    on_use=lambda tl, cid=c_item.id: self._use_cosmetic(cid),
                    data=c_item.id,
                    crown=getattr(c_item, "premium_only", False),
                    premium_locked=g.cosmetic_status(c_item, self.app.today()) == "premium",
                    on_premium=lambda tl: self.app.open_sub("premium"),
                    note=item_note,
                )
                self.cosmetic_tiles[c_item.id] = c_tile
                if not owned_c and c_item.price > 0:
                    self.tiles.append(c_tile)
                cos_grid.append(ft.Container(c_tile, col=6))
            items.append(ft.ResponsiveRow(cos_grid, spacing=Space.SM, run_spacing=Space.SM))
        self.list.controls = items

    def _refresh(self) -> None:
        if self.app.tab == 3:
            self.render()
            ui.refresh(self.list)

    def _edit(self, reward_id: str) -> None:
        editors.edit_reward(self.app, reward_id, self._refresh)

    def _archive(self, reward_id: str) -> None:
        r = self.app.game.reward(reward_id)
        self.app.game.archive_reward(reward_id)
        self.app.save()
        self._refresh()
        self.app.toast(f"{r.title} archived. History kept.", ft.Icons.ARCHIVE)

    def _archived_row(self, r: Reward) -> ft.Control:
        def restore(_: Any = None) -> None:
            self.app.game.unarchive_reward(r.id)
            self.app.save()
            self._refresh()
            self.app.toast(f"{r.title} is back in your shop", ft.Icons.UNARCHIVE)

        n = len(r.redeemed)
        return ft.Container(ft.Row([
            ft.Icon(ft.Icons.ARCHIVE, color=C.TEXT_DIM, size=20),
            ft.Column([ft.Text(r.title, size=Type.BODY, color=C.TEXT_DIM,
                               weight=ft.FontWeight.W_600),
                       common.hint(f"{r.cost:,} coins · redeemed {n}x · archived")],
                      spacing=0, expand=True, tight=True),
            ft.TextButton("Restore", icon=ft.Icons.UNARCHIVE, height=Size.TAP,
                          on_click=common.with_sound(restore)),
        ], spacing=Space.MD, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            bgcolor=C.SURFACE, border_radius=Radius.MD,
            padding=ft.Padding.symmetric(horizontal=Space.MD, vertical=Space.XS))

    def restyle(self) -> None:
        """Theme switched: flip Equipped/Use in place. (Rebuilding the grids inside the same
        update as a theme change left the ResponsiveRows blank on Flet web.)"""
        p = self.app.game.profile
        for tid, tile in self.theme_tiles.items():
            tile.set_owned(tid in p.owned_themes, tid == p.theme_id)
        eq_id = self.app.game.equipped_cosmetic_id(self.selected_cat)
        is_title_cat = self.selected_cat == "title"
        for cid, tile in self.cosmetic_tiles.items():
            item = cos.COSMETIC_BY_ID.get(cid)
            if is_title_cat:
                owned = cos.is_title_unlocked(self.app.game, cid)
                active = self.app.game.is_title_equipped(cid)
            else:
                owned = cid in p.owned_cosmetics or (item is not None and item.price == 0)
                active = cid == eq_id
            tile.set_owned(owned, active)

    def _select_cat(self, cat_id: str) -> None:
        self.selected_cat = cat_id
        self._refresh()

    def _coins_spent(self, tile: ui.RewardTile) -> None:
        coins = self.app.game.profile.coins
        self.coin_text.value = f"You have {coins:,} coins"
        ui.refresh(self.coin_text)
        tile.coins = coins  # the tapped tile settles itself after its celebration
        for t in self.tiles:
            if t is not tile:
                t.set_coins(coins)
        self.app.page.run_task(self.app.coins_changed)

    # ------------------------------------------------------------------ actions
    async def _redeem(self, tile: ui.RewardTile, reward_id: str) -> bool:
        r: Reward = next(x for x in self.app.game.rewards if x.id == reward_id)
        ok = await common.confirm(
            self.app.page, f"Redeem {r.title}?",
            f"Spend {r.cost:,} coins on this reward you set for yourself. Then go enjoy it!",
            "Redeem")
        if not ok or not self.app.game.redeem(reward_id, self.app.today()):
            return False
        self.app.save()
        sfx.play("purchase")
        self._coins_spent(tile)
        self.app.lumen("reward_redeemed", ft.Icons.CELEBRATION, reward=r.title)
        return True

    async def _buy(self, tile: ui.RewardTile, theme_id: str) -> bool:
        t = next(x for x in self.app.game.themes() if x.id == theme_id)
        ok = await common.confirm(self.app.page, f"Unlock {t.name}?",
                                  f"Spend {t.price:,} coins on {t.name}. "
                                  "You can switch back any time.", "Unlock")
        if not ok or not self.app.game.buy_theme(theme_id, self.app.today()):
            return False
        self.app.save()
        self._coins_spent(tile)
        self.app.page.run_task(self.app.reveal, t.name, "Theme unlocked")
        self.app.lumen("theme_bought", ft.Icons.PALETTE, theme=t.name)
        return True

    def _use(self, theme_id: str) -> None:
        if not self.app.game.set_theme(theme_id):
            return
        self.app.save()
        th.apply_theme(self.app.page, theme_id)  # restyles this screen via callback

    async def _buy_cosmetic(self, tile: ui.RewardTile, item_id: str) -> bool:
        item = cos.COSMETIC_BY_ID.get(item_id)
        if item is None:
            return False
        if (
            getattr(item, "premium_only", False)
            and self.app.game.cosmetic_status(item, self.app.today()) == "premium"
        ):
            self.app.open_sub("premium")
            return False
        cat_name = cos.CATEGORIES.get(item.category, "Cosmetic")
        ok = await common.confirm(
            self.app.page,
            f"Unlock {item.name}?",
            f"Spend {item.price:,} coins on {item.name} ({cat_name}).\n{item.subtitle}",
            "Unlock",
        )
        if not ok or not self.app.game.buy_cosmetic(item_id):
            return False
        self.app.game.equip_cosmetic(item_id)
        self.app.save()
        sfx.play("purchase")
        self._coins_spent(tile)
        self.app.refresh_profile()
        self.restyle()
        self.app.page.run_task(self.app.reveal, item.name, f"{cat_name} unlocked & equipped")
        return True

    def _use_cosmetic(self, item_id: str) -> None:
        item = cos.COSMETIC_BY_ID.get(item_id)
        was_equipped = self.app.game.is_title_equipped(item_id) if (item and item.category == "title") else False
        if not self.app.game.equip_cosmetic(item_id):
            if item and item.category == "title":
                self.app.toast(f"Locked: {item.subtitle}", ft.Icons.LOCK)
            return
        self.app.save()
        sfx.play("tap")
        self.app.refresh_profile()
        self.restyle()
        if item is not None:
            if item.category == "title":
                if was_equipped:
                    self.app.toast(f"Unequipped title '{item.name}'", ft.Icons.REMOVE_CIRCLE_OUTLINE)
                else:
                    self.app.toast(f"Equipped title '{item.name}'", ft.Icons.CHECK_CIRCLE)
            else:
                self.app.toast(f"Equipped {item.name}", ft.Icons.CHECK_CIRCLE_OUTLINE)

    async def _delete(self, reward_id: str) -> None:
        await ui.buzz("medium")
        r = self.app.game.reward(reward_id)
        msg = ("It was redeemed before, so it is archived with its history instead."
               if r.redeemed else f"\"{r.title}\" leaves your shop. Your coins stay.")
        ok = await common.confirm(self.app.page, "Remove reward?", msg, "Remove", danger=True)
        if not ok:
            return
        self.app.game.delete_reward(reward_id)
        self.app.save()
        self._refresh()

    def _open_add(self, _: Any = None) -> None:
        app = self.app
        title = common.text_field("Reward (e.g. Jollibee meal)", autofocus=True)
        cost = common.text_field("Coin price", number=True)
        note = common.text_field("Note (optional)")
        presets = ft.Row([
            ft.OutlinedButton(str(n), height=Size.TAP,
                              on_click=lambda e, n=n: (setattr(cost, "value", str(n)),
                                                       cost.update()))
            for n in (50, 100, 250, 500)
        ], spacing=Space.SM, wrap=True)

        def add(_: Any = None) -> None:
            text = (title.value or "").strip()
            try:
                price = int((cost.value or "").replace(",", "").strip())
            except ValueError:
                price = -1
            title.error_text = None if text else "Name your reward"
            cost.error_text = None if price > 0 else "Pick a price, like 100"
            if not text or price <= 0:
                sfx.play("error_soft")
                title.update()
                cost.update()
                return
            app.game.add_reward(text, price, note=(note.value or "").strip())
            app.save()
            common.close(sheet)
            self.render()
            ui.refresh(self.list)
            app.toast(f"Added {text} for {price:,} coins", ft.Icons.CARD_GIFTCARD)

        sheet = common.open_sheet(app.page, "New reward", [
            common.hint("A treat you promise yourself. Not a real coupon."),
            title, cost, presets, note,
            common.hint("The price is fixed once the reward is added."),
            ft.Row([common.primary_button("Add reward", add, icon=ft.Icons.ADD)]),
        ])
