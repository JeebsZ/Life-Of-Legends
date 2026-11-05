"""Premium foundation: entitlement boundary, daily vs weekly limits, ad bonuses, coin-unlock,
never-gated list, minors' ad flag, offers, soft-offer timing and save compatibility."""

from datetime import date, timedelta

import pytest

from lol.core import catalog, premium, storage, stretch
from lol.core.game import Game
from lol.core.models import PremiumState, ThemeDef
from lol.core.premium import Entitlement

WED = date(2026, 11, 4)  # a Wednesday
MON = date(2026, 11, 2)


def dev_game(on: bool = True) -> Game:
    g = Game()
    g.dev_env = True
    g.set_dev_premium(on)
    return g


# --- entitlement boundary ------------------------------------------------------------------------
def test_free_by_default_and_save_flag_alone_is_not_premium():
    g = Game()
    assert not g.is_premium(WED)
    g.data.premium.dev_premium = True  # e.g. a hand-edited save
    assert not g.is_premium(WED)  # no dev env, Developer menu never revealed
    assert g.set_dev_premium(True) is False


def test_dev_toggle_needs_dev_env_or_unlocked_menu():
    g = Game()
    g.unlock_dev()
    assert g.set_dev_premium(True)
    assert g.is_premium(WED) and g.entitlement().source == "dev"
    assert dev_game().is_premium(WED)


def test_store_build_ignores_dev(monkeypatch):
    monkeypatch.setattr(premium, "DEV_BUILD", False)
    g = Game()
    g.dev_env = True
    g.data.premium.dev_premium = True
    assert not g.is_premium(WED)
    assert g.unlock_dev() is False


def test_store_entitlement_wins_and_expires():
    g = Game()
    g.store_entitlement = Entitlement("premium", "store", "2026-11-10")
    assert g.is_premium(WED)
    assert not g.is_premium(date(2026, 11, 11))
    assert premium.resolve_entitlement(None, True, False) == premium.FREE_ENTITLEMENT


# --- periods -------------------------------------------------------------------------------------
def test_week_starts_monday():
    assert premium.week_start(WED) == MON
    assert premium.week_start(MON) == MON
    assert premium.week_start(date(2026, 11, 8)) == MON  # Sunday
    assert premium.resets_on(True, WED) == date(2026, 11, 9)
    assert premium.resets_on(False, WED) == date(2026, 11, 5)


def test_free_daily_limit_resets_next_day():
    g = Game()
    for _ in range(3):
        assert g.use("meal_scan", WED)
    assert g.remaining("meal_scan", WED) == 0
    assert not g.can_use("meal_scan", WED) and not g.use("meal_scan", WED)
    nxt = WED + timedelta(days=1)
    assert g.remaining("meal_scan", nxt) == 3 and g.use("meal_scan", nxt)


def test_premium_weekly_bank_spans_days_and_resets_monday():
    g = dev_game()
    for i in range(70):
        assert g.use("meal_scan", MON + timedelta(days=i % 7))
    assert g.remaining("meal_scan", date(2026, 11, 8)) == 0
    assert not g.use("meal_scan", date(2026, 11, 8))
    assert g.remaining("meal_scan", date(2026, 11, 9)) == 70  # next Monday


def test_each_feature_has_its_own_numbers():
    g = Game()
    assert g.remaining("generate_steps", WED) == 3
    assert g.remaining("note_scan", WED) == 5
    p = dev_game()
    assert p.remaining("generate_steps", WED) == 50
    assert p.remaining("note_scan", WED) == 100
    with pytest.raises(KeyError):
        g.use("quests", WED)


def test_tier_switch_starts_a_fresh_period():
    g = Game()
    g.dev_env = True
    for _ in range(3):
        g.use("meal_scan", WED)
    g.set_dev_premium(True)
    assert g.remaining("meal_scan", WED) == 70


# --- ad bonuses ----------------------------------------------------------------------------------
def test_bonus_adds_uses_and_is_capped_per_day():
    g = Game()
    for _ in range(3):
        g.use("meal_scan", WED)
    assert g.grant_bonus("meal_scan", 1, WED) == 1
    assert g.remaining("meal_scan", WED) == 1 and g.use("meal_scan", WED)
    assert g.grant_bonus("meal_scan", 5, WED) == premium.AD_BONUS_MAX_PER_DAY - 1
    assert g.bonus_left("meal_scan", WED) == 0
    assert g.grant_bonus("meal_scan", 1, WED) == 0
    assert g.bonus_left("meal_scan", WED + timedelta(days=1)) == premium.AD_BONUS_MAX_PER_DAY


def test_no_bonus_for_premium_or_zero():
    assert dev_game().grant_bonus("meal_scan", 1, WED) == 0
    assert Game().grant_bonus("meal_scan", 0, WED) == 0


# --- caps and history ----------------------------------------------------------------------------
def test_custom_chain_cap():
    g = Game()
    for name in ("A", "B"):
        assert g.can_add_custom_chain(WED)
        g.add_side_quest(name, "scholar", ["one"], today=WED)
    assert not g.can_add_custom_chain(WED)
    g.dev_env = True
    g.set_dev_premium(True)
    assert g.can_add_custom_chain(WED)


def test_history_windows():
    assert Game().history_cutoff("insights", WED) == WED - timedelta(days=6)
    assert Game().history_cutoff("run_history", WED) == WED - timedelta(days=29)
    assert dev_game().history_cutoff("insights", WED) is None


def test_never_gated():
    for f in ("safety_notes", "data_export", "quests", "bills", "rewards", "accessibility",
              "reduce_motion", "manual_meal_log"):
        assert f in premium.NEVER_GATED and not premium.is_gated(f)
    gated = set(premium.LIMITS) | set(premium.ACTIVE_CAPS) | set(premium.HISTORY_DAYS)
    assert not gated & premium.NEVER_GATED
    assert all(premium.is_gated(f) for f in gated)


# --- coin unlock ---------------------------------------------------------------------------------
def test_free_themes_stay_free_and_unlocked():
    for tid in ("arcane", "rose"):
        t = catalog.THEME_BY_ID[tid]
        assert t.price == 0 and not t.premium_only
    assert {t.id for t in catalog.THEMES if t.premium_only} == {"ocean", "forest", "royal"}


def test_coin_status_rule():
    t = ThemeDef("x", "X", 100, premium_only=True)
    assert premium.coin_status(t, False, False) == "premium"
    assert premium.coin_status(t, False, True) == "buy"
    assert premium.coin_status(t, True, False) == "owned"
    assert premium.coin_status(ThemeDef("y", "Y", 100), False, False) == "buy"


def test_premium_does_not_grant_items_only_unlocks_buying():
    g = dev_game()
    assert "royal" not in g.profile.owned_themes
    g.profile.coins = 0
    assert g.buy_theme("royal", WED) is False  # premium, but coins are still needed
    g.profile.coins = 600
    assert g.buy_theme("royal", WED) and g.profile.coins == 0


def test_owned_premium_theme_stays_after_premium_ends():
    g = dev_game()
    g.profile.coins = 300
    g.buy_theme("ocean", WED)
    g.set_dev_premium(False)
    assert g.theme_status(catalog.THEME_BY_ID["ocean"], WED) == "owned"
    assert g.set_theme("ocean")


# --- ads -----------------------------------------------------------------------------------------
def test_run_tracking_rule():
    assert premium.run_tracking(True, None) == "full"
    assert premium.run_tracking(False, "watched") == "full"
    assert premium.run_tracking(False, "unavailable") == "full"  # no fill never punishes
    assert premium.run_tracking(False, "skipped") == "basic"
    assert premium.run_tracking(False, None) == "basic"
    assert not premium.shows_ads(True) and premium.shows_ads(False)


def test_minors_get_non_personalized_flag():
    g = Game()
    g.profile.onboarding.age_band = "13-17"
    g.sync_ad_flags()
    assert g.data.premium.ads_non_personalized
    g.profile.onboarding.age_band = "18-24"
    g.sync_ad_flags()
    assert not g.data.premium.ads_non_personalized


# --- offers --------------------------------------------------------------------------------------
def test_plans_and_season_deal_have_real_end_dates():
    assert [p.price_php for p in premium.PLANS] == [149, 999, 1990]
    assert premium.per_month(premium.plan("yearly")) == 83
    deal = premium.SEASON_DEALS[0]
    assert deal.price_php == 59 and deal.regular_php == 149
    end = date.fromisoformat(deal.ends_on)
    assert premium.days_left(deal, end) == 1
    assert premium.active_deals(end) == [deal]
    assert premium.active_deals(end + timedelta(days=1)) == []
    assert premium.days_left(premium.plan("monthly"), WED) is None


def test_promo_stub():
    assert premium.check_promo("STUDENT-2026")[0]
    assert not premium.check_promo("")[0]
    assert not premium.check_promo("no way!")[0]


# --- soft offer ----------------------------------------------------------------------------------
def test_soft_offer_once_per_reason_with_gap():
    g = Game()
    premium.touch(g.data.premium, MON)
    assert g.offer_due("level_up", MON)
    g.mark_offer("level_up", MON)
    assert not g.offer_due("level_up", MON + timedelta(days=10))  # once per reason
    assert not g.offer_due("limit", MON + timedelta(days=1))  # gap
    assert g.offer_due("limit", MON + timedelta(days=premium.OFFER_GAP_DAYS))
    assert not dev_game().offer_due("limit", WED)  # premium: never


def test_day3_offer():
    st = PremiumState()
    premium.touch(st, MON)
    assert not premium.offer_due(st, "day3", False, MON + timedelta(days=1))
    assert premium.offer_due(st, "day3", False, MON + timedelta(days=2))
    with pytest.raises(ValueError):
        premium.offer_due(st, "nag", False, MON)


# --- save compatibility (schema 5 additive) ------------------------------------------------------
def test_old_save_without_premium_loads_defaults():
    g = Game()
    raw = storage.to_dict(g.data)
    del raw["premium"]
    for r in raw.get("runs", []):
        r.pop("basic", None)
    data = storage.from_dict(raw)
    assert data.premium == PremiumState()


def test_premium_state_round_trips():
    g = Game()
    g.use("meal_scan", WED)
    g.grant_bonus("meal_scan", 1, WED)
    g.mark_offer("limit", WED)
    back = storage.from_dict(storage.to_dict(g.data))
    assert back.premium == g.data.premium
    assert back.premium.usage["meal_scan"].bonus == 1


def test_odd_premium_value_loads_default():
    raw = storage.to_dict(Game().data)
    raw["premium"] = "broken"
    assert storage.from_dict(raw).premium == PremiumState()
    raw["premium"] = {"usage": {"meal_scan": {"period": "D2026-11-04", "used": 2},
                                "bad": 3}, "unknown": 1}
    st = storage.from_dict(raw).premium
    assert st.usage["meal_scan"].used == 2 and "bad" not in st.usage


def test_old_run_entry_is_full_tracking():
    from lol.core.models import RunEntry
    assert RunEntry("r1", "2026-11-04").basic is False


def test_stretch_guide():
    ids = [s.id for s in stretch.STRETCHES]
    assert ids == ["calf", "hamstring", "quad", "hip"]
    assert stretch.total_seconds() == 160
    assert "stop" in stretch.SAFETY.lower()


def test_basic_run_is_stored_and_round_trips():
    from tests.test_run import stats

    g = Game()
    c = g.log_run(stats(1.2), WED, basic=True)
    assert g.run(c.ref_id).basic
    back = storage.from_dict(storage.to_dict(g.data))
    assert back.runs[0].basic and back.runs[0].steps > 0


def test_i18n_translations_and_non_ai_credits():
    from lol.core import i18n

    for lang in ("en", "tl", "zh", "ja", "ar", "hi", "es", "id", "ko", "pt", "fr", "de"):
        assert lang in i18n.LANGUAGES
    assert i18n.tr("Today", "zh") == "今日"
    assert i18n.tr("Today", "ja") == "今日"
    assert i18n.tr("Today", "tl") == "Ngayon"
    assert i18n.tr("Today", "ar") == "اليوم"
    assert i18n.tr("Today", "hi") == "आज"
    g = Game()
    g.set_profile(language="ja")
    back = storage.from_dict(storage.to_dict(g.data))
    assert back.profile.language == "ja"
    all_credits = " ".join(
        f"{title} {name} {detail}"
        for title, items in i18n.CREDITS_SECTIONS
        for name, detail in items
    ).lower()
    assert "openstax" in all_credits
    assert "gutenberg" in all_credits
    assert "usda" in all_credits
    assert "piper" not in all_credits
    assert "tflite" not in all_credits
    assert "ml kit" not in all_credits


def test_quest_and_step_tooltips_preserve_full_descriptions():
    from lol.ui import components as ui

    long_note = "Read chapters 1 to 3 carefully and write a two-sentence summary in your notebook."
    qc = ui.QuestCard("Evening Study", note=long_note)
    assert qc.tooltip == f"Evening Study\n{long_note}"
    assert qc._note.tooltip == long_note
    assert qc._note.max_lines == 2

    sq = ui.SideQuestCard(
        "Deep Reading",
        path_id="scholar",
        steps=[("Step 1", long_note, 25, 5, False)],
    )
    assert sq._rows[0].tooltip == f"Step 1\n{long_note}"
