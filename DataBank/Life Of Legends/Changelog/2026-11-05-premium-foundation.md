# Premium foundation (Part 1, 5 Nov)

No real billing or ads yet. Everything is stubbed behind one boundary so Part 2 swaps it in.

- **core/premium.py**: `Entitlement`, `resolve_entitlement()` (the ONE place Part 2's store check plugs in via `Game.store_entitlement`), LIMITS table (free daily / premium weekly bank, Monday reset), ad bonuses (max 3/day, free only), custom-chain cap (2), history windows (Insights 7 d, runs 30 d), NEVER_GATED list, coin-unlock rule (`ThemeDef.premium_only`: Ocean/Forest/Royal need premium to buy, with coins), ShopOffer/PLANS/season deal (Running season PHP 59, ends 2026-11-30), promo-code stub, soft-offer timing.
- **Trust**: the save never proves a purchase. `PremiumState.dev_premium` counts only when `DEV_BUILD` and (LOL_DEV=1 or Settings version tapped 7x). Set `DEV_BUILD = False` for store builds.
- **Save** (schema 5, additive): `premium` (PremiumState), `RunEntry.basic`.
- **UI**: More -> Premium (Legends+ page, name = `PREMIUM_NAME`), `ui/ads.py` (AdCard placeholder "Ad (test)", 5 s, Skip; `limit_gate` sheet: ad for +1 / premium / by hand), `screens/stretch.py` (pre-run stretch guide), Run: watched -> full tracking, skipped -> basic (steps + time), premium -> straight in. Meals / Generate steps / Study scan gated; manual entry never. Crown + "Premium" button on premium-only shop themes. Settings shows remaining uses + Developer.
- **Part 2 TODO**: RevenueCat/Play Billing in place of `store_entitlement`; AdMob in `ads._available/_play` (send `ads_non_personalized` for 13-17); real promo redemption; DEV_BUILD False.
- Known: `ui/adventure_layer.py` (another batch) used Flet 0.x `ft.border`/`ft.padding`, crashing the Run screen; QA ran with a shim.
