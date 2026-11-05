"""App shell: loads the game, owns the shared header (level bar + coins), the overlay effects
(level-up banner, Luma notice, Arcane effects), the bottom nav, tab switching and the More
tab's sub-screen stack. Screens live in lol.ui.screens.*; rules live in lol.core.

Effect priority for one reward beat (never stack big overlays): overall level-up ->
MilestoneSeal; else skill acquired / ranked up -> NoticeEmblem; else Path level-up -> the
lighter LevelUpBanner. Whatever is not the big effect is folded into Luma notices.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import re
import string
import time
from collections.abc import Callable
from datetime import date, datetime

import flet as ft

from lol.core import i18n, pins, premium, welcome
from lol.core.game import COINS_BY_DIFFICULTY, Game
from lol.core.models import RANK_NAMES, Completion
from lol.core.progression import bar_steps, xp_for_level
from lol.ui import ambient, audio, avatars, notify, sfx, voice
from lol.ui import components as ui
from lol.ui import effects as fx
from lol.ui import theme as th
from lol.ui.screens import common
from lol.ui.theme import C, Radius, Space, Type


def _tolerate_orphan_method_results() -> None:
    """Flet raises when a method result (scroll_to, map move, audio play ...) arrives for a
    control that was unmounted while the call was in flight - e.g. leaving a screen mid-call.
    That exception ends the session's receive loop, so every later tap is silently lost.
    Drop such results instead: the control is gone, nobody is left to read them."""
    from flet.messaging.session import Session

    original = Session.handle_invoke_method_results
    if getattr(original, "_lol_guarded", False):
        return

    def guarded(self, control_id, call_id, result, error):
        try:
            original(self, control_id, call_id, result, error)
        except RuntimeError as exc:
            if "is not registered" not in str(exc):
                raise

    guarded._lol_guarded = True  # type: ignore[attr-defined]
    Session.handle_invoke_method_results = guarded


with contextlib.suppress(Exception):
    _tolerate_orphan_method_results()

TAB_TODAY, TAB_QUESTS, TAB_CENTER, TAB_REWARDS, TAB_MORE = range(5)  # center: pinned slot
TAB_ME = TAB_MORE  # old name: the Me content now lives under More -> Profile
HEADER_H = 108  # shared header height at phone width; Luma notices sit just below it

# voice.say kind -> Luma voice clip kind (ui.audio.CLIPS). Kinds in ALIGNED speak the clip
# variant that matches the on-screen line (clip n mirrors voice.LINES[kind][n]); others pick one.
CLIP_FOR = {
    "quest_done": "quest_done", "level_up": "level_up", "path_level": "path_level",
    "skill_acquired": "skill_acquired", "quest_accepted": "quest_accepted",
    "board_header": "proposal", "board_analysis": "analysis", "report_title": "analysis",
    "bill_due": "bill_due", "bill_paid": "bill_paid", "bill_marked": "bill_paid",
    "reward_redeemed": "reward_redeemed", "theme_bought": "reward_redeemed",
    "coin_cap": "coin_cap", "comeback": "welcome_back",
}
ALIGNED = {"quest_done", "level_up", "path_level", "skill_acquired", "quest_accepted",
           "board_header", "bill_due", "bill_paid", "reward_redeemed", "coin_cap", "comeback"}
_PATTERNS: dict[str, list[re.Pattern[str]]] = {}
# Luma's welcome back (core/welcome.py slot) -> notice icon
WELCOME_ICONS = {"morning": ft.Icons.WB_SUNNY, "day": ft.Icons.AUTO_AWESOME,
                 "evening": ft.Icons.WB_TWILIGHT, "night": ft.Icons.NIGHTLIGHT_ROUND,
                 "away": ft.Icons.WB_TWILIGHT}


def _patterns(kind: str) -> list[re.Pattern[str]]:
    """voice.LINES[kind] templates as regexes ('{xp}' -> any text), cached."""
    if kind not in _PATTERNS:
        out = []
        for tpl in voice.LINES.get(kind, ()):
            parts = [re.escape(lit) + ("(.+?)" if field is not None else "")
                     for lit, field, _, _ in string.Formatter().parse(tpl)]
            out.append(re.compile("".join(parts), re.DOTALL))
        _PATTERNS[kind] = out
    return _PATTERNS[kind]


def clip_for(kind: str, text: str = "") -> ui.Clip:
    """Voice clip for a line said as voice.say(kind) -> (clip kind, variant) or a clip kind."""
    clip = CLIP_FOR.get(kind, kind if kind in audio.CLIPS else None)
    if clip is None or kind not in ALIGNED or not text:
        return clip
    for i, pat in enumerate(_patterns(kind)):
        if pat.fullmatch(text):
            return (clip, i)
    return clip


def clip_of_line(text: str, default: str | None = None) -> ui.Clip:
    """Clip for a ready-made line whose kind is unknown (e.g. award's `line` callback)."""
    for kind, clip in CLIP_FOR.items():
        for i, pat in enumerate(_patterns(kind)):
            if pat.fullmatch(text):
                return (clip, i) if kind in ALIGNED else clip
    return default


class App:
    """Shared state + juice for every screen."""

    def __init__(self, page: ft.Page) -> None:
        self.page = page
        self.game = Game.load(today=date.today())
        # premium: dev switches count only with LOL_DEV=1 or the hidden Developer menu
        self.game.dev_env = os.getenv("LOL_DEV", "").strip().lower() in ("1", "true", "yes")
        premium.touch(self.game.data.premium, date.today())
        self.game.sync_ad_flags()
        self.tab = TAB_TODAY
        self.prev_tab = TAB_TODAY  # where the center slot's back arrow returns to
        p = self.game.profile
        i18n.set_language(p.language)

        # --- overlays: banner, Luma notice, Arcane effects (v1.2; calls queue) ---
        self.banner = ui.LevelUpBanner()
        self.notice = ui.LumenNotice(top=HEADER_H + Space.SM)  # below the header: XP bar stays visible
        self.fx_notice = fx.NoticeEmblem()
        self.fx_seal = fx.MilestoneSeal()
        self.fx_think = fx.LumenThinking(on_start=lambda: sfx.play("lumen_hum"))
        self.fx_reveal = fx.IdentifyReveal()
        fx.set_reduce(p.reduce_effects)
        # --- v1.3 ambience: living mind-space background, glass panels, quest-clear juice ---
        ambient.set_glass_cap("frost" if p.reduce_effects else "blur")
        self.space = ambient.MindSpace()
        self.fx_cleared = fx.QuestCleared()
        self.fx_burst = ambient.ParticleBurst()
        self.focus_ends: datetime | None = None  # running focus countdown -> 'timer done' alert
        self._sync_gen = 0
        self._welcomed_at: float | None = None  # wall clock of Luma's last welcome back
        self._welcome_variant: int | None = None

        # --- header: name + coins, overall XP bar, floaters ---
        self.xp_bar = ui.XpBar(p.xp / xp_for_level(p.level), level=p.level,
                               caption=self._xp_caption(),
                               on_rollover=self._level_seal)
        self.coins = ui.CoinCounter(p.coins, on_click=lambda e: self.go(TAB_REWARDS))
        # floaters rise from just under the bar's right end, clear of the coin pill
        self.xp_float = ui.FloatingGain(right=0, top=56)
        self.coin_float = ui.FloatingGain(right=96, top=56)
        self.name = ft.Text(p.name, size=Type.HEADLINE, weight=ft.FontWeight.W_900,
                            color=C.TEXT, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS,
                            expand=True)
        self.avatar = avatars.bubble(p.avatar_id, 38)
        self.avatar.on_click = lambda e: self.open_sub("profile")
        self.avatar.tooltip = "Profile"
        self.header = ambient.apply_glass(ft.Container(
            ft.Stack([
                ft.Column([
                    ft.Row([self.avatar, self.name, self.coins], spacing=Space.SM + 2,
                           vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    self.xp_bar,
                ], spacing=Space.SM),
                self.xp_float, self.coin_float,
            ]),
            padding=ft.Padding.only(left=Space.GUTTER, right=Space.GUTTER, top=Space.MD,
                                    bottom=Space.MD),
            border_radius=ft.BorderRadius.only(bottom_left=Radius.LG, bottom_right=Radius.LG),
        ), "blur", fill=1.15)

        from lol.ui.screens.more import CenterScreen, MoreScreen
        from lol.ui.screens.quests import QuestsScreen
        from lol.ui.screens.rewards import RewardsScreen
        from lol.ui.screens.today import TodayScreen

        self.screens = [TodayScreen(self), QuestsScreen(self), CenterScreen(self),
                        RewardsScreen(self), MoreScreen(self)]
        self.body = ft.Container(self.screens[0].view, expand=True)
        self.nav = ui.ArcaneNavBar(TAB_TODAY, on_select=self._on_nav,
                                   on_center=self._center_tap, on_center_hold=self._center_hold)
        self._unpinned: str | None = None  # last unpinned feature (Undo)

    # ------------------------------------------------------------------ helpers
    def today(self) -> date:
        return date.today()  # the only clock read; screens call this

    def save(self) -> None:
        self.game.save()
        self.resync_reminders()

    # ------------------------------------------------------------------ reminders
    def reminders(self) -> list:
        """Everything that should be scheduled on the phone right now."""
        now = datetime.now()
        out = list(self.game.planned_reminders(now, 7))
        if self.focus_ends is not None and self.focus_ends > now:
            r = self.game.focus_reminder(self.focus_ends)
            if r is not None:
                out.append(r)
        return out

    def resync_reminders(self, delay: float = 1.0) -> None:
        """Re-plan the phone's notification queue (debounced; no-op off Android)."""
        if not notify.available():
            return
        self._sync_gen += 1
        gen = self._sync_gen

        async def run() -> None:
            await asyncio.sleep(delay)
            if gen == self._sync_gen:
                with contextlib.suppress(Exception):
                    await notify.sync(self.reminders())

        with contextlib.suppress(Exception):
            self.page.run_task(run)

    def set_focus_alarm(self, ends_at: datetime | None) -> None:
        """Focus timer started/resumed (ends_at) or paused/stopped (None)."""
        self.focus_ends = ends_at
        self.resync_reminders(0.2)

    def _xp_caption(self) -> str:
        p = self.game.profile
        return f"{p.xp} / {xp_for_level(p.level)} XP"

    def toast(self, text: str, icon: ft.IconData | None = None) -> None:
        common.toast(self.page, text, icon=icon)

    def error(self, text: str) -> None:
        """Gentle validation/error feedback: soft sound + toast."""
        sfx.play("error_soft")
        common.toast(self.page, text, icon=ft.Icons.INFO_OUTLINE)

    def lumen(self, kind: str, icon: ft.IconData | None = None, **values: object) -> None:
        """Queue a Luma notice: voice.say(kind, **values) in the top announcement panel, with
        the matching voice clip spoken as it appears."""
        text = voice.say(kind, **values)
        self.notice.say(text, icon, clip_for(kind, text))

    async def _level_seal(self, lvl: int) -> None:
        """Overall level-up (XpBar rollover): MilestoneSeal 'LEVEL n', voiced."""
        sub = voice.say("level_up", level=lvl)
        sfx.play("milestone")
        self.space.pulse(fx.GOLD, 1.2)
        ui.voice(clip_for("level_up", sub))
        await self.fx_seal.show(f"LEVEL {lvl}", ui.split_lead(sub)[1].strip(),
                                eyebrow="LEVEL UP")
        self.offer_premium("level_up")

    # ------------------------------------------------------------------ effects
    async def think(self, seconds: float = 0.8, label: str = "Analysis…") -> None:
        """LumenThinking for about `seconds` (Luma Report). The orb opens with the hum."""
        await self.fx_think.play(seconds, label)

    async def think_staged(self, seconds: float = 2.5) -> None:
        """Ask Luma / generate steps: the slower staged analysis (hum, ANALYSIS… ->
        MATCHING PATHS… -> PROPOSAL READY). Tap to skip."""
        await self.fx_think.play_staged(seconds)

    async def cleared(self, title: str, at: tuple[float | None, float | None] | None = None,
                      color: str | None = None) -> None:
        """QuestCleared + particle burst + a brightening of the mind-space (every quest
        completion that has no bigger effect)."""
        x, y = at or (None, None)
        col = color or th.current().primary
        self.space.pulse(col, 0.7)
        self.page.run_task(self.fx_burst.burst, x, y, color=col, count=28)
        await self.fx_cleared.show(title, x=x, y=y, color=th.current().primary)

    def juice(self, color: str | None = None, at: tuple[float | None, float | None] | None = None,
              strength: float = 0.7) -> None:
        """Small reward beat without QuestCleared (bill paid, water goal, workout logged)."""
        x, y = at or (None, None)
        col = color or th.current().primary
        self.space.pulse(col, strength)
        self.page.run_task(self.fx_burst.burst, x, y, color=col, count=24)

    async def reveal(self, title: str, subtitle: str | None = None) -> None:
        """IdentifyReveal (theme bought, side quest started)."""
        sfx.play("skill_acquired", 0.7)
        await self.fx_reveal.show(title, subtitle)

    def apply_settings(self) -> None:
        """Profile settings read outside the profile (Reduce effects is a module switch)."""
        reduce = self.game.profile.reduce_effects
        i18n.set_language(self.game.profile.language)
        fx.set_reduce(reduce)
        self.space.set_reduce(None)
        ambient.set_glass_cap("frost" if reduce else "blur", self.page)
        if hasattr(self, "nav"):
            self.nav.refresh_labels()
            self.refresh_center()

    def overdue_bills(self) -> int:
        return sum(1 for _, s, _ in self.game.bills_status(self.today()) if s == "overdue")

    def update_badges(self) -> None:
        """Overdue bills: a red dot on More (Bills lives there), or on the center slot when
        Bills is pinned; the Bills tile itself shows the count."""
        overdue = self.overdue_bills() > 0
        bills_pinned = self.pinned() == "bills"
        self.nav.set_badge(TAB_MORE, overdue and not bills_pinned)
        self.nav.set_badge(TAB_CENTER, overdue and bills_pinned)
        ui.refresh(self.nav)

    def refresh_profile(self) -> None:
        """Header avatar + name after a profile edit (pops the avatar)."""
        p = self.game.profile
        self.name.value = p.name
        avatars.restyle_bubble(self.avatar, p.avatar_id)
        ui.refresh(self.name, self.avatar)
        if self.avatar.page:
            self.page.run_task(ui.pop, self.avatar, 1.18)

    async def coins_changed(self) -> None:
        """Animate the header coin pill to the saved balance (after spending/earning)."""
        await self.coins.count_to(self.game.profile.coins)

    # ------------------------------------------------------------------ the reward beat
    async def award(self, mutate: Callable[[], Completion],
                    line: Callable[[Completion], str] | None = None, *,
                    cleared: str | None = None, stinger: str = "quest_clear",
                    at: tuple[float | None, float | None] | None = None) -> Completion:
        """Run a core mutation that awards XP/coins, save, then play the juice:
        sounds + Luma notice + floaters + coin count (parallel), XP bar (awaited), then ONE big
        effect (see the module docstring); the rest are folded into Luma notices. `line(c)` is
        Luma's announcement (default: quest cleared). A Quest Board quest cleared for the first
        time is announced as a new practice. `cleared`: the quest/step title - shows the
        QuestCleared flash + burst at `at` (page coords of the tap) unless a level-up or skill
        effect plays instead; other awards get a soft burst + mind-space pulse."""
        p = self.game.profile
        level, xp = p.level, p.xp
        practiced_before = {q.title for q in self.game.practiced()}
        c = mutate()
        self.save()  # save before animating: an interrupted animation never loses XP
        if not (c.xp or c.coins):
            return c
        path = th.path_name(c.path_id)
        path_up = bool(c.path_levels_gained and c.path_id)
        big = ("level" if c.levels_gained else "skill" if c.skill_unlocked
               else "path" if path_up else None)
        pc = th.path_color(c.path_id)
        if big in ("level", "skill"):
            # a skill comes from finishing a side-quest chain: mission_complete on top
            sfx.play("chain_complete" if c.skill_unlocked else "quest_done")
            self.space.pulse(fx.GOLD, 1.2)
        elif cleared:
            sfx.play(stinger)  # quest_clear / chain_step; replaces quest_done (no stacking)
            self.page.run_task(self.cleared, cleared, at, pc)
        else:
            sfx.play("quest_done", 0.5)
            self.juice(pc, at)
        if line:
            text = line(c)
            clip = clip_of_line(text, "quest_done")
        else:
            text = voice.say("quest_done", xp=c.xp, path=path)
            clip = clip_for("quest_done", text)
        self.notice.say(text, th.path_icon(c.path_id), clip)
        for q in self.game.practiced():
            if q.title not in practiced_before:
                self.lumen("practiced", ft.Icons.AUTO_AWESOME, title=q.title)
        skill_line = None
        if c.skill_unlocked:
            rank_name = RANK_NAMES.get(c.skill_rank or 1, "")
            skill_line = voice.say("skill_acquired", skill=f"{c.skill_unlocked} · {rank_name}")
            # the emblem speaks the clip when it plays, so the notice stays silent then
            self.notice.say(skill_line, ft.Icons.MILITARY_TECH,
                            None if big == "skill" else clip_for("skill_acquired", skill_line))
        path_lvl = self.game.path_level(c.path_id)[0] if path_up else 0
        if path_up and big != "path":  # folded into a notice: one big effect per beat
            self.lumen("path_level", th.path_icon(c.path_id), path=path, level=path_lvl)
        if c.capped:
            self.lumen("coin_cap", ft.Icons.SAVINGS)
        self.page.run_task(self.xp_float.xp, c.xp)
        if c.coins:
            self.page.run_task(self.coin_float.coins, c.coins)
            self.page.run_task(self._coin_sound, c.coins)
            self.page.run_task(self.coins_changed)
        sfx.play("xp_fill", 0.35)  # quiet bed under the chime and Luma's voice
        final_level = self.game.profile.level

        async def rollover(lvl: int) -> None:  # several levels at once: seal only the last
            if lvl >= final_level:
                await self._level_seal(lvl)

        await self.xp_bar.play(bar_steps(level, xp, c.xp), caption=self._xp_caption(),
                               on_rollover=rollover)
        if big == "skill" and skill_line:
            self.page.run_task(self.skill_banner, c.skill_unlocked, c.skill_rank or 1,
                               c.path_id, clip_for("skill_acquired", skill_line))
        if big == "path":
            self.space.pulse(fx.GOLD, 1.2)
            sub = voice.say("path_level", path=path, level=path_lvl)
            sfx.play("path_level_up", 0.8)  # level_up with rank_up under it
            self.page.run_task(
                self.banner.show, path_lvl, title=f"{path.upper()} LEVEL UP", subtitle=sub,
                color=th.path_color(c.path_id), icon=th.path_icon(c.path_id),
                clip=clip_for("path_level", sub))
        return c

    async def _coin_sound(self, coins: int = 0) -> None:
        await asyncio.sleep(0.35)  # after the quest chime, as the coin pill counts up
        # credits / credits_many (a hard quest's payout); the voice follows the chime (mixer)
        sfx.play("coin_many" if coins >= COINS_BY_DIFFICULTY[3] else "coin", 0.55)

    async def skill_banner(self, skill: str, rank: int, path_id: str,
                           clip: ui.Clip = "skill_acquired") -> None:
        """NoticeEmblem: SKILL ACQUIRED / SKILL RANK UP, the skill name and rank, voiced."""
        self.space.pulse(fx.GOLD, 1.2)
        stars = "★" * rank + "☆" * max(0, 3 - rank)
        eyebrow = "SKILL ACQUIRED" if rank <= 1 else "SKILL RANK UP"
        sfx.play("skill_unlock" if rank <= 1 else "skill_rank_up")  # skill_acquired + layers
        ui.voice(clip)
        await self.fx_notice.show(skill, eyebrow,
                                  subtitle=f"{RANK_NAMES.get(rank, '')} {stars}",
                                  color=th.path_color(path_id))

    # ------------------------------------------------------------------ app open
    def last_active_day(self) -> date | None:
        """Most recent day before today with any recorded activity (quests, steps, logs)."""
        today = self.today().isoformat()
        days = [d for q in self.game.quests for d in q.done_on]
        days += [st.done_on for sq in self.game.side_quests() for st in sq.steps if st.done_on]
        days += [e.day for e in self.game.logs()]
        past = [d for d in days if d < today]
        return date.fromisoformat(max(past)) if past else None

    def greet_on_open(self) -> None:
        """App open / resume, right after power_up: Luma's 'welcome back' (a notice + voice
        line by time of day, or the gentle 'been away' one after 2+ quiet days; never guilt).
        At most once per welcome.COOLDOWN_S. The notice's ping + voice wait for power_up to
        finish (mixer FOREGROUND); voice off -> the notice still shows, silently."""
        now = time.time()  # wall clock: monotonic may stop while the phone sleeps
        if not self.game.profile.onboarded or not welcome.due(now, self._welcomed_at):
            return
        self._welcomed_at = now
        i = welcome.pick(datetime.now(), self.last_active_day(), self._welcome_variant)
        self._welcome_variant = i
        self.notice.say(voice.LINES["hello_again"][i], WELCOME_ICONS.get(welcome.SLOTS[i]),
                        ("hello_again", i))
        self.offer_premium("day3")

    def offer_premium(self, reason: str) -> bool:
        """One gentle Luma notice about premium (first limit / first level-up / day 3): once
        per reason, at most every few days, never for premium users. 'limit' only records
        the moment (the limit sheet itself shows the offer)."""
        today = self.today()
        if not self.game.offer_due(reason, today):
            return False
        self.game.mark_offer(reason, today)
        self.save()
        if reason != "limit":
            self.notice.say(voice.say(f"premium_{reason}", name=premium.PREMIUM_NAME),
                            ft.Icons.WORKSPACE_PREMIUM)
        return True

    # ------------------------------------------------------------------ navigation
    def go(self, index: int) -> None:
        self._show(index)

    def _on_nav(self, index: int) -> None:
        self.page.run_task(ui.buzz, "select")
        sfx.play("tab_close" if self.tab == TAB_MORE and index != TAB_MORE else "tab_open")
        self._show(index)

    def _show(self, index: int) -> None:
        self.nav.select(index)  # the highlight always follows the shown screen
        if self.tab != index:
            leave = getattr(self.screens[self.tab], "on_leave", None)
            if leave:
                leave()
            if self.tab != TAB_CENTER:
                self.prev_tab = self.tab
        self.tab = index
        screen = self.screens[index]
        screen.render()
        self.body.content = screen.view
        self.refresh_fab()
        self.page.update()

    def refresh_fab(self) -> None:
        self.page.floating_action_button = getattr(self.screens[self.tab], "fab", None)

    @property
    def more(self):  # the visible sub-screen stack: center slot's or More's (untyped: no cycle)
        return self.screens[TAB_CENTER if self.tab == TAB_CENTER else TAB_MORE]

    def showing(self, key: str) -> bool:
        """True while sub-screen `key` is on top of the visible stack (More or center)."""
        return self.tab in (TAB_MORE, TAB_CENTER) and self.more.stack[-1:] == [key]

    def open_sub(self, key: str, **kw: object) -> None:
        """Open a More sub-screen (profile, skills, calendar, focus, ...) from anywhere.
        kw goes to the sub-screen's `prepare(**kw)` (e.g. focus: quest_id=...). The pinned
        feature opens under the center slot, so the highlight matches what is shown."""
        if self.tab in (TAB_MORE, TAB_CENTER):
            self.more.open(key, **kw)
        elif key == self.pinned():
            self.screens[TAB_CENTER].show(key, **kw)
            sfx.play("tab_open")
            self.go(TAB_CENTER)
        else:
            self.screens[TAB_MORE].reset(key, **kw)
            sfx.play("tab_open")
            self.go(TAB_MORE)

    # ------------------------------------------------------------------ center slot
    def pinned(self) -> str | None:
        """The center slot's feature, if it can show (a switched-off module reads empty)."""
        from lol.ui.screens.more import pinnable_keys

        return pins.active_pin(self.game.profile, pinnable_keys(self))

    def refresh_center(self) -> None:
        """Slot look (icon, color, short label) from the saved pin, plus badges."""
        from lol.ui.screens.more import TILES

        key = self.pinned()
        if key is None:
            self.nav.slot.set_pin(None)
        else:
            label, icon, color = TILES[key]
            self.nav.slot.set_pin(label if len(label) <= 9 else label.split(" ")[0], icon,
                                  color)
        self.update_badges()

    def set_pin(self, key: str | None, *, announce: bool = True) -> None:
        """Pin a feature to the center slot (None clears it): saves, restyles the slot."""
        from lol.ui.screens.more import TILES, pinnable_keys

        pins.set_pin(self.game.profile, key, pinnable_keys(self))
        self.save()
        self.refresh_center()
        if self.tab == TAB_CENTER:  # the pinned feature changed under us
            if key is None:
                self.screens[TAB_CENTER].reset()
                self.go(self.prev_tab)
            else:
                self.screens[TAB_CENTER].show(key)
                self._show(TAB_CENTER)
        if key is not None and announce:
            sfx.play("unlock")
            self.page.run_task(ui.buzz, "medium")
            self.page.run_task(self.nav.slot.pulse)
            self.toast(f"{TILES[key][0]} pinned to the middle button", TILES[key][1])

    def pick_pin(self) -> None:
        from lol.ui.screens.more import pin_picker

        pin_picker(self, self.set_pin)

    def _center_tap(self, _: object = None) -> None:
        key = self.pinned()
        self.page.run_task(ui.buzz, "select")
        if key is None:
            self.page.run_task(self.nav.slot.pulse, 1.08)
            self.pick_pin()
            return
        self.page.run_task(self.nav.slot.pulse, 1.1)
        center = self.screens[TAB_CENTER]
        if self.tab == TAB_CENTER and center.stack == [key]:
            return  # already showing it
        sfx.play("tab_open")
        center.show(key)
        self._show(TAB_CENTER)

    def _center_hold(self, _: object = None) -> None:
        """Long-press: unpin (toast with Undo); the next tap picks a new feature."""
        from lol.ui.screens.more import TILES

        key = self.pinned()
        if key is None:
            self.page.run_task(ui.buzz, "select")
            self.pick_pin()
            return
        self._unpinned = key
        self.set_pin(None, announce=False)
        sfx.play("back")
        self.page.run_task(ui.buzz, "heavy")
        self.page.run_task(self.nav.slot.pulse, 0.88)

        def undo(_: object = None) -> None:
            if self._unpinned and self.pinned() is None:
                self.set_pin(self._unpinned)

        self.page.show_dialog(ft.SnackBar(
            ft.Row([ft.Icon(ft.Icons.PUSH_PIN_OUTLINED, color=C.PRIMARY, size=18),
                    ft.Text(f"Unpinned {TILES[key][0]}. Tap the middle button to pin another.",
                            color=C.TEXT, size=Type.BODY - 1, expand=True)],
                   spacing=Space.SM),
            action=ft.SnackBarAction("Undo", text_color=C.PRIMARY, on_click=undo),
            bgcolor=C.SURFACE_HI, behavior=ft.SnackBarBehavior.FLOATING, duration=4000))

    def connected(self) -> bool:
        """False once this page's session has gone (web reload / closed tab)."""
        try:
            return self.page.session.connection is not None
        except (AttributeError, RuntimeError):
            return False

    def rerender(self) -> None:
        """Rebuild the visible screen (e.g. after a theme switch recolors Path chips)."""
        if not self.connected():
            return  # a closed web session whose theme callback is still registered
        screen = self.screens[self.tab]
        getattr(screen, "restyle", screen.render)()

    def reload_state(self) -> None:
        """After a restore: header, settings, theme, badges and the visible screen."""
        p = self.game.profile
        self.name.value = p.name
        avatars.restyle_bubble(self.avatar, p.avatar_id)
        self.xp_bar.set(p.xp / xp_for_level(p.level), caption=self._xp_caption(), level=p.level)
        self.coins.set(p.coins)
        self.apply_settings()
        self.screens[TAB_TODAY].bill_voiced = True  # no surprise voice after a restore
        th.apply_theme(self.page, p.theme_id if p.theme_id in th.THEMES else th.DEFAULT_THEME)
        ui.refresh(self.name, self.avatar, self.coins)
        self.update_badges()
        self.rerender()
        self.page.update()


def main(page: ft.Page) -> None:
    page.title = "LUMA: Your Lifestyle QoL"
    page.padding = 0
    page.spacing = 0
    with contextlib.suppress(Exception):  # web/mobile have no window to size
        page.window.width, page.window.height = 400, 860
        page.window.icon = "icons/LumaAppIcon.jpg"
    ui.use_haptics(ft.HapticFeedback())

    app = App(page)
    audio.init(page, settings=lambda: app.game.profile)  # voice_on / voice_volume, read live
    sfx.init(page, settings=lambda: app.game.profile)  # sfx_on / sfx_volume / reduce_effects
    th.apply_theme(page, app.game.profile.theme_id, update=False)
    th.on_theme_change(callback=lambda pal: app.rerender())

    notify.init(page, settings=lambda: app.game.profile)  # phone alerts (+ notify_sound)

    page.overlay.append(app.banner)
    page.overlay.extend([app.fx_notice, app.fx_seal, app.fx_reveal])
    page.overlay.extend([app.fx_burst, app.fx_cleared])  # tap-through quest-clear juice
    page.overlay.append(app.notice)
    page.overlay.append(app.fx_think)  # Luma thinking sits on top

    def lifecycle(e: ft.Event) -> None:
        state = getattr(e, "state", None)
        if state in (ft.AppLifecycleState.HIDE, ft.AppLifecycleState.PAUSE):
            app.space.pause()
        elif state in (ft.AppLifecycleState.RESUME, ft.AppLifecycleState.SHOW):
            if state == ft.AppLifecycleState.RESUME:
                sfx.play("power_up", 0.7)  # back in the app
                app.greet_on_open()  # Luma's welcome back after it (30 min cooldown)
            app.space.resume()
            app.resync_reminders()  # top the reminder queue up on return

    page.on_app_lifecycle_state_change = lifecycle
    page.on_resize = lambda e: app.space.resize(page.width, page.height)

    if app.game.profile.onboarded:
        mount_shell(app)
        sfx.play("power_up", 0.7)  # app opened; Luma's welcome back follows it
        app.greet_on_open()
        app.resync_reminders(2.0)
        return

    run_onboarding(app)


def run_onboarding(app: App, *, redo: bool = False) -> None:
    """Show the Personalize flow (first run, or Settings -> redo: progress is kept), then land
    on Today with a level-up-style welcome."""
    from lol.ui.screens.onboarding import Onboarding

    page = app.page

    async def welcome() -> None:
        await asyncio.sleep(0.6)
        sfx.play("level_up", 0.8)
        app.space.pulse(th.current().primary, 1.2)
        await ui.buzz("heavy")
        await app.fx_seal.show(app.game.profile.name,
                               "Your plan is updated" if redo else "Your legend begins",
                               eyebrow="PERSONALIZED" if redo else "WELCOME")
        app.lumen("profile_saved" if redo else "welcome", ft.Icons.AUTO_AWESOME)

    def done(_started_side_quest: bool) -> None:
        page.controls.clear()
        mount_shell(app, TAB_TODAY, fade_in=True)
        app.refresh_profile()
        page.run_task(welcome)

    if redo:
        with contextlib.suppress(Exception):
            app.more.reset()
        page.controls.clear()
        page.navigation_bar = None
        page.bottom_appbar = None
        page.floating_action_button = None
    flow = Onboarding(app, on_done=done, redo=redo)
    page.add(flow)
    flow.start()


def mount_shell(app: App, tab: int = TAB_TODAY, *, fade_in: bool = False) -> None:
    """Header + body + bottom nav (after onboarding, or straight away for existing players)."""
    page = app.page
    shell = ft.Container(ft.Column([app.header, app.body], spacing=0, expand=True),
                         expand=True, opacity=0 if fade_in else 1,
                         offset=ft.Offset(0, 0.04) if fade_in else ft.Offset(0, 0),
                         animate_opacity=th.Motion.anim(450),
                         animate_offset=th.Motion.anim(450, th.Motion.EASE_CUBIC))
    page.bottom_appbar = app.nav  # ArcaneNavBar: Today · Quests · [center] · Rewards · More
    fx.install_distortion(page, root=shell)  # reward impacts punch/jitter the app content
    page.add(ft.Stack([app.space, ft.SafeArea(shell, expand=True)], expand=True))
    app.refresh_center()
    app.go(tab)
    page.run_task(app.nav.slot.spin, lambda: app.game.profile.reduce_effects)
    if fade_in:
        async def _in() -> None:
            await asyncio.sleep(0.05)
            shell.opacity, shell.offset = 1, ft.Offset(0, 0)
            ui.refresh(shell)

        page.run_task(_in)
