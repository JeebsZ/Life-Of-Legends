# Paywall + ads plan (suggestions, not built)

**Model:** free core forever + **Legends+** subscription (name TBD), with a 7-day free trial and a lifetime option. Premium also removes ads.

## Free vs Premium (suggested limits)
| Area | Free | Premium |
|---|---|---|
| Quests / bills / rewards | Unlimited (the core loop is never gated) | Unlimited |
| Custom side-quest chains | 2 active | Unlimited, plus Luma "Generate steps" |
| Meal scan (on-device) | 3 scans a day; manual log unlimited | Unlimited scans, favorites sync |
| Body plan | BMI, plan, macros (safety info never gated) | Plan history, weekly re-calibration |
| Run tracker | Tracking, map, ladder to 10K, 30-day history | Full ladder, all history, PR analytics, route export (GPX) |
| Insights / Report | Last 7 days | All time, trends, CSV export of charts |
| Themes / voice | Arcane + Rose Arcana | All themes, premium Luma voice lines, cosmetics |
| Ads | Rewarded only (opt-in) | None |
| Backup | Local export/import (your data is always yours) | Cloud backup (later) |

## Never paywall
Safety notes and floors, data export, the core quest loop, accessibility, and reduce-motion.

## Ads (suggested)
- **Rewarded only, opt-in:** "watch an ad for +1 scan today" or "+10% coins on this quest".
- **No interstitials:** none in Focus, Run, onboarding, or right after a reward.
- **Under-18 (13–17 band):** non-personalized ads or no ads; follow Google Play Families policy.

## When to show the offer
Not straight after onboarding with a hard wall. Show a **soft offer** when the user first hits a limit, after their first level-up, or on day 3. Always have a clear ✕ and plain trial terms, with no countdown pressure.

## Price ideas (PH)
₱149/month · ₱999/year (best value) · ₱1,990 lifetime. Test it; don't guess forever.

## Tech
- **Android:** Google Play Billing is required for digital goods. Easiest route is a **RevenueCat** Flet extension (wrapping `purchases_flutter`; free tier up to ~$2.5k monthly revenue). Same approach as our notify/vision extensions.
- **Ads:** **AdMob** (`google_mobile_ads`) extension plus Google's consent form (UMP) for privacy rules.
- **Entitlement:** a single `is_premium` check in core with limits as constants, so they're easy to tune. Trial and expiry come from the store, never trusted from the save file.

## Your decisions (5 Nov) — these override the table above where they differ
- Core stays free forever.
- **Premium unlocks the RIGHT to buy** premium cosmetics, themes and voice packs **with coins**; it doesn't grant them outright.
- **Limits:** free = daily limit; premium = a big **weekly bank** instead.
- **Ads are opt-in only.**
  - **Before a run (free):** "an ad plays while you stretch". Watching it unlocks the full tracker. Skipping still tracks **steps and time only** (no map, pace, splits or kcal).
  - **Other features:** rewarded ads for bonuses.
- **Offers:** upgrade offers plus small timed deals for real-money unique cosmetics, themes and voice packs.
- **Prices:** ₱149/mo, ₱999/yr, ₱1,990 lifetime, plus season deals (e.g. "Running season" ₱59 first month) and student discounts.
- **Tiers:** a single premium tier (no ads, big weekly bank).

**Flagged:** the feature doc says "keep real money out of reward pressure" and "no loot boxes". Fixed-price timed deals are fine, but I'd keep countdowns honest (real end dates, no fake timers) and never sell coins or random items.

## Decisions for you (original)
1. Brand name for premium, and the free limits above (tweak any number).
2. Ads at all, or premium-only income? Rewarded-only is the least annoying.
3. Lifetime option yes/no.
4. Timing: before or after public launch? It needs a Play Console account (one-time US$25).
