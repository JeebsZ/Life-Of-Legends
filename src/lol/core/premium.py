"""Premium foundation (Part 1): entitlement, usage limits, rewarded-ad bonuses, the coin-unlock
rule, real-money offers (model only) and soft-offer timing. Pure: no flet, no clock, no I/O.

TRUST BOUNDARY (read before Part 2)
- `resolve_entitlement()` is the ONE place that decides free vs premium. In Part 2 the store
  check (RevenueCat / Play Billing) passes its result as `store`; nothing else changes.
- The save file is never proof of purchase. PremiumState holds usage counters and dev switches
  only. `dev_premium` counts only when `dev_allowed` is True (a dev build: DEV_BUILD and the
  LOL_DEV=1 env var or the hidden Developer section). Store builds set DEV_BUILD = False, so a
  hand-edited save cannot unlock anything.

Limits: free = a DAILY allowance, premium = a big WEEKLY bank (resets Monday 00:00 local).
Counters are stored per period ("D<iso day>" / "W<iso Monday>"); a new period starts at 0.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

from lol.core.models import PremiumState, ThemeDef, UsageCount

if TYPE_CHECKING:
    from lol.core.models import SaveData

# --- Tuning (change here) ----------------------------------------------------------------------
PREMIUM_NAME = "Legends+"  # placeholder brand name: use this constant, never the literal
DEV_BUILD = True  # Part 2: False in store builds (dev premium + Developer menu are ignored)
DEV_TAPS = 7  # taps on the version label that reveal Settings -> Developer
FREE, PREMIUM = "free", "premium"
SOURCES = ("dev", "store")


@dataclass(frozen=True)
class Limit:
    feature: str
    label: str
    unit: str  # plural noun for "3 scans left"
    free_daily: int
    premium_weekly: int | None  # None = unlimited


LIMITS: dict[str, Limit] = {
    "meal_scan": Limit("meal_scan", "Meal scans", "scans", 3, 70),
    "generate_steps": Limit("generate_steps", "Luma Generate steps", "drafts", 3, 50),
    "note_scan": Limit("note_scan", "Note scans (Study)", "scans", 5, 100),
}
# Counts of active things (not per period): (free cap, premium cap); None = unlimited.
ACTIVE_CAPS: dict[str, tuple[int, int | None]] = {"custom_chains": (2, None)}
# History windows in days: (free, premium); None = all time.
HISTORY_DAYS: dict[str, tuple[int, int | None]] = {"insights": (7, None),
                                                   "run_history": (30, None)}
AD_BONUS_MAX_PER_DAY = 3  # rewarded "+1" bonuses per feature per day
NEVER_GATED: frozenset[str] = frozenset({
    "safety_notes", "safety_floors", "data_export", "quests", "bills", "rewards",
    "accessibility", "reduce_motion", "manual_meal_log", "manual_entry",
})

# --- Ads (opt-in, rewarded only) -----------------------------------------------------------------
AD_PLACEMENTS = ("pre_run_stretch", "bonus_scan", "bonus_coins")
AD_RESULTS = ("watched", "skipped", "unavailable")
AD_SECONDS = 5  # the dev placeholder's length
MINOR_BANDS = frozenset({"13-17"})  # onboarding age bands that get non-personalized ads

# --- Soft offer ----------------------------------------------------------------------------------
OFFER_REASONS = ("limit", "level_up", "day3")
OFFER_GAP_DAYS = 3  # at most one gentle notice every few days
OFFER_DAY = 3  # "day 3" = the third day since first_seen


# --- Entitlement --------------------------------------------------------------------------------
@dataclass(frozen=True)
class Entitlement:
    tier: str = FREE  # "free" | "premium"
    source: str = "dev"  # "dev" | "store"
    expires: str | None = None  # ISO date; None = no end (lifetime / dev)

    def active(self, today: date) -> bool:
        """Premium right now (an expired store entitlement reads as free)."""
        if self.tier != PREMIUM:
            return False
        return self.expires is None or today <= date.fromisoformat(self.expires)


FREE_ENTITLEMENT = Entitlement()


def resolve_entitlement(store: Entitlement | None, dev_premium: bool,
                        dev_allowed: bool) -> Entitlement:
    """THE single decision point. The store's answer wins; the dev toggle only in dev builds;
    a raw boolean flag in the save file alone is never enough."""
    if store is not None and store.tier == PREMIUM:
        return store
    if dev_allowed and DEV_BUILD and dev_premium:
        return Entitlement(PREMIUM, "dev")
    return FREE_ENTITLEMENT


def dev_allowed(env_flag: bool, state: PremiumState) -> bool:
    """Dev switches count only in a dev build, with LOL_DEV=1 or the revealed Developer menu."""
    return DEV_BUILD and (env_flag or state.dev_unlocked)


# --- Periods ------------------------------------------------------------------------------------
def week_start(today: date) -> date:
    """Monday of today's week (the weekly bank resets Monday 00:00 local)."""
    return today - timedelta(days=today.weekday())


def period_key(premium: bool, today: date) -> str:
    return f"W{week_start(today).isoformat()}" if premium else f"D{today.isoformat()}"


def resets_on(premium: bool, today: date) -> date:
    """The day the current allowance refills: tomorrow (free) or next Monday (premium)."""
    return week_start(today) + timedelta(days=7) if premium else today + timedelta(days=1)


def allowance(feature: str, premium: bool) -> int | None:
    """Base uses per period (None = unlimited)."""
    lim = LIMITS[feature]
    return lim.premium_weekly if premium else lim.free_daily


def _counter(state: PremiumState, feature: str, premium: bool, today: date) -> UsageCount:
    if feature not in LIMITS:
        raise KeyError(f"not a limited feature: {feature}")
    key = period_key(premium, today)
    c = state.usage.get(feature)
    if c is None or c.period != key:
        c = UsageCount(key)
        state.usage[feature] = c
    return c


def remaining(state: PremiumState, feature: str, premium: bool, today: date) -> int | None:
    """Uses left in this period, bonuses included (None = unlimited)."""
    base = allowance(feature, premium)
    if base is None:
        return None
    c = state.usage.get(feature)
    if c is None or c.period != period_key(premium, today):
        return base
    return max(0, base + c.bonus - c.used)


def used(state: PremiumState, feature: str, premium: bool, today: date) -> int:
    c = state.usage.get(feature)
    return c.used if c is not None and c.period == period_key(premium, today) else 0


def can_use(state: PremiumState, feature: str, premium: bool, today: date) -> bool:
    left = remaining(state, feature, premium, today)
    return left is None or left > 0


def use(state: PremiumState, feature: str, premium: bool, today: date) -> bool:
    """Spend one use. False (nothing counted) when the allowance is empty."""
    if not can_use(state, feature, premium, today):
        return False
    _counter(state, feature, premium, today).used += 1
    return True


def grant_bonus(state: PremiumState, feature: str, n: int, premium: bool,
                today: date) -> int:
    """Rewarded-ad bonus: +n uses this period. Free only (premium sees no ads), at most
    AD_BONUS_MAX_PER_DAY a day. Returns how many were granted."""
    if n <= 0 or premium:
        return 0
    c = _counter(state, feature, premium, today)
    granted = max(0, min(n, AD_BONUS_MAX_PER_DAY - c.bonus))
    c.bonus += granted
    return granted


def bonus_left(state: PremiumState, feature: str, premium: bool, today: date) -> int:
    """How many more rewarded bonuses can be granted this period (0 for premium)."""
    if premium:
        return 0
    c = state.usage.get(feature)
    got = c.bonus if c is not None and c.period == period_key(premium, today) else 0
    return max(0, AD_BONUS_MAX_PER_DAY - got)


# --- Caps and history ---------------------------------------------------------------------------
def active_cap(kind: str, premium: bool) -> int | None:
    free, prem = ACTIVE_CAPS[kind]
    return prem if premium else free


def can_add_active(kind: str, active_now: int, premium: bool) -> bool:
    cap = active_cap(kind, premium)
    return cap is None or active_now < cap


def history_days(feature: str, premium: bool) -> int | None:
    free, prem = HISTORY_DAYS[feature]
    return prem if premium else free


def history_cutoff(feature: str, premium: bool, today: date) -> date | None:
    """First day shown (None = all time)."""
    days = history_days(feature, premium)
    return None if days is None else today - timedelta(days=days - 1)


def is_gated(feature: str) -> bool:
    """True for anything with a free limit. NEVER_GATED features are never limited."""
    if feature in NEVER_GATED:
        return False
    return feature in LIMITS or feature in ACTIVE_CAPS or feature in HISTORY_DAYS


# --- Coin-unlock rule ---------------------------------------------------------------------------
def coin_status(item: ThemeDef, owned: bool, premium: bool) -> str:
    """'owned' | 'buy' (coins) | 'premium' (premium-only and not premium: locked).
    Premium never grants an item: it unlocks the right to buy it with coins."""
    if owned:
        return "owned"
    if item.premium_only and not premium:
        return "premium"
    return "buy"


# --- Ads ----------------------------------------------------------------------------------------
def shows_ads(premium: bool) -> bool:
    return not premium


def ads_non_personalized(age_band: str) -> bool:
    return age_band in MINOR_BANDS


def run_tracking(premium: bool, ad_result: str | None) -> str:
    """'full' or 'basic'. Premium: full. Free: full after the stretch ad was watched, or when
    no ad could be served ('unavailable' never punishes the user); skipped/declined: basic."""
    if premium or ad_result in ("watched", "unavailable"):
        return "full"
    return "basic"


# --- Real-money offers (Part 2 billing; model + honest dates only) ------------------------------
OFFER_KINDS = ("cosmetic", "theme", "voice_pack", "subscription")


@dataclass(frozen=True)
class ShopOffer:
    id: str
    kind: str  # OFFER_KINDS
    price_php: int
    ends_on: str | None = None  # ISO date (last day it is sold); None = permanent
    title: str = ""
    note: str = ""
    regular_php: int | None = None  # the normal price a deal is cut from
    period: str = ""  # "month" | "year" | "once" (subscriptions/lifetime)
    store_id: str = ""  # Play product / base plan / offer id (Part 2)


PLANS: tuple[ShopOffer, ...] = (
    ShopOffer("monthly", "subscription", 149, title="Monthly", period="month",
              store_id="legends_plus:monthly"),
    ShopOffer("yearly", "subscription", 999, title="Yearly", note="Best value",
              period="year", store_id="legends_plus:yearly"),
    ShopOffer("lifetime", "subscription", 1990, title="Lifetime", note="Pay once",
              period="once", store_id="legends_lifetime"),
)
SEASON_DEALS: tuple[ShopOffer, ...] = (
    ShopOffer("running_season", "subscription", 59, ends_on="2026-11-30",
              title="Running season", note="First month, then ₱149/month",
              regular_php=149, period="month", store_id="legends_plus:monthly:running-season"),
)
TRIAL_DAYS = 7


def plan(plan_id: str) -> ShopOffer:
    return next(p for p in PLANS if p.id == plan_id)


def offer_active(offer: ShopOffer, today: date) -> bool:
    return offer.ends_on is None or today <= date.fromisoformat(offer.ends_on)


def days_left(offer: ShopOffer, today: date) -> int | None:
    """Whole days the deal is still sold, today included (None = no end). Real dates only."""
    if offer.ends_on is None:
        return None
    return max(0, (date.fromisoformat(offer.ends_on) - today).days + 1)


def active_deals(today: date, deals: Iterable[ShopOffer] = SEASON_DEALS) -> list[ShopOffer]:
    return [d for d in deals if offer_active(d, today)]


def per_month(offer: ShopOffer) -> int | None:
    """Monthly equivalent of a yearly plan (rounded), for "₱83/mo"."""
    return round(offer.price_php / 12) if offer.period == "year" else None


PROMO_RE = re.compile(r"^[A-Z0-9]{4,16}(-[A-Z0-9]{2,8})?$")


def check_promo(code: str) -> tuple[bool, str]:
    """Part 1 stub: validate the shape; real codes are checked by the store in Part 2."""
    c = code.strip().upper()
    if not c:
        return False, "Type your code first."
    if not PROMO_RE.match(c):
        return False, "That doesn't look like a code. Check the letters and numbers."
    return True, "Code saved. It applies at checkout once the store is connected."


# --- Soft offer timing --------------------------------------------------------------------------
def touch(state: PremiumState, today: date) -> None:
    """Stamp first_seen (the day-3 offer counts from here)."""
    if not state.first_seen:
        state.first_seen = today.isoformat()


def day3_reached(state: PremiumState, today: date) -> bool:
    if not state.first_seen:
        return False
    return (today - date.fromisoformat(state.first_seen)).days >= OFFER_DAY - 1


def offer_due(state: PremiumState, reason: str, premium: bool, today: date) -> bool:
    """One gentle notice per reason, ever, and at most once every OFFER_GAP_DAYS."""
    if reason not in OFFER_REASONS:
        raise ValueError(f"reason must be one of {OFFER_REASONS}")
    if premium or reason in state.offer_reasons:
        return False
    if reason == "day3" and not day3_reached(state, today):
        return False
    if state.offer_last:
        last = date.fromisoformat(state.offer_last)
        if (today - last).days < OFFER_GAP_DAYS:
            return False
    return True


def mark_offer(state: PremiumState, reason: str, today: date) -> None:
    if reason not in state.offer_reasons:
        state.offer_reasons.append(reason)
    state.offer_last = today.isoformat()


# --- Game mixin ---------------------------------------------------------------------------------
class PremiumMixin:
    """Premium on Game. The UI sets `store_entitlement` (Part 2) and `dev_env` at startup."""

    data: SaveData
    store_entitlement: Entitlement | None = None  # Part 2: the store's answer
    dev_env: bool = False  # LOL_DEV=1 (read by the UI; core never reads the environment)

    @property
    def premium_state(self) -> PremiumState:
        return self.data.premium

    def dev_allowed(self) -> bool:
        return dev_allowed(self.dev_env, self.data.premium)

    def entitlement(self) -> Entitlement:
        return resolve_entitlement(
            self.store_entitlement,
            self.data.premium.dev_premium,
            self.dev_allowed(),
        )

    def is_premium(self, today: date | None = None) -> bool:
        """Premium now. Without a day the store's expiry is not checked (tier only)."""
        ent = self.entitlement()
        return ent.tier == PREMIUM if today is None else ent.active(today)

    def set_dev_premium(self, on: bool) -> bool:
        """Dev toggle. False (nothing changed) outside a dev build."""
        if not self.dev_allowed():
            return False
        self.data.premium.dev_premium = on
        return True

    def unlock_dev(self) -> bool:
        if not DEV_BUILD:
            return False
        self.data.premium.dev_unlocked = True
        return True

    def can_use(self, feature: str, today: date) -> bool:
        return can_use(self.data.premium, feature, self.is_premium(today), today)

    def use(self, feature: str, today: date) -> bool:
        return use(self.data.premium, feature, self.is_premium(today), today)

    def remaining(self, feature: str, today: date) -> int | None:
        return remaining(self.data.premium, feature, self.is_premium(today), today)

    def grant_bonus(self, feature: str, n: int, today: date) -> int:
        return grant_bonus(self.data.premium, feature, n, self.is_premium(today), today)

    def bonus_left(self, feature: str, today: date) -> int:
        return bonus_left(self.data.premium, feature, self.is_premium(today), today)

    def reset_usage(self) -> None:
        """Dev: clear every counter."""
        self.data.premium.usage.clear()

    def custom_chains_active(self) -> int:
        return sum(1 for sq in self.data.side_quests if sq.active and sq.custom)

    def can_add_custom_chain(self, today: date) -> bool:
        return can_add_active("custom_chains", self.custom_chains_active(),
                              self.is_premium(today))

    def history_cutoff(self, feature: str, today: date) -> date | None:
        return history_cutoff(feature, self.is_premium(today), today)

    def theme_status(self, theme: ThemeDef, today: date) -> str:
        return coin_status(theme, theme.id in self.data.profile.owned_themes,
                           self.is_premium(today))

    def cosmetic_status(self, item: Any, today: date) -> str:
        owned = item.id in self.data.profile.owned_cosmetics or getattr(item, "price", 0) == 0
        if owned:
            return "owned"
        if getattr(item, "premium_only", False) and not self.is_premium(today):
            return "premium"
        return "buy"

    def sync_ad_flags(self) -> None:
        """13-17 band -> non-personalized ads flag (sent to AdMob in Part 2)."""
        self.data.premium.ads_non_personalized = ads_non_personalized(
            self.data.profile.onboarding.age_band)

    def offer_due(self, reason: str, today: date) -> bool:
        return offer_due(self.data.premium, reason, self.is_premium(today), today)

    def mark_offer(self, reason: str, today: date) -> None:
        mark_offer(self.data.premium, reason, today)
