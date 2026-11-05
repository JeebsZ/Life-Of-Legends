# Paywall + ads — your setup guide (Part 2 prerequisites)

Do these steps yourself. They involve your identity, payment profile and legal agreements, so I can't do them for you. Then send me the IDs and keys marked 🔑 and I'll wire them in.

## 1. Google Play Console (required for payments and ads)
1. Go to play.google.com/console, then **Create developer account** (one-time US$25). Choose **Personal** or **Organization**, then verify your ID.
2. **Create app**: "Life of Legends", App, Free (it can still sell subscriptions).
3. **Monetization setup**: create a **payments profile** (bank account for payouts).
4. Upload one build to **Internal testing** (I'll make an `.aab` for you). Play only enables subscriptions after an upload.
5. **Monetize → Products → Subscriptions**: create `legends_plus` with base plans:
   - `monthly` ₱149
   - `yearly` ₱999
6. **Season deal:** add an **offer** on monthly, e.g. "running-season" at ₱59 for the 1st month. Offers can be time-limited and can target new or returning users.
7. **Student discount:** Play has no student verification. Two options:
   - a **promo code** offer that you hand out (school partnerships, social posts);
   - a separate `student_monthly` base plan unlocked by a code.
   - I recommend promo codes.
8. **Lifetime:** create an **in-app product** (one-time) `legends_lifetime` at ₱1,990, plus one-time products for paid cosmetics, themes and voice packs.

## 2. RevenueCat (handles purchases, trials and restore; free until US$2.5k a month in revenue)
1. Go to app.revenuecat.com and create a project, then add an Android app (package `com.companions.LUMA`).
2. Link Google Play: create a Google Cloud **service account** and give it Play Console access. Follow RevenueCat's "Google Play service credentials" guide; it walks you through every click.
3. Create an **Entitlement** `premium`. Attach `legends_plus` monthly and yearly, plus `legends_lifetime`.
4. Create an **Offering** `default`, plus `season` for the ₱59 deal.
5. 🔑 Send me: the **public Android SDK key** (starts with `goog_`). It's safe to ship in the app. Never send your secret key.

## 3. AdMob (opt-in rewarded ads)
1. Go to admob.google.com, sign in with the same Google account, and add the app (link it to Play once it's listed).
2. Create ad units, type **Rewarded**:
   - `pre_run_stretch` (the stretch ad before a run)
   - `bonus_scan`
   - `bonus_coins`
3. **Privacy & messaging**: create a **GDPR** consent message and a **US states** message (Google's own consent form).
4. Your app is used by 13–17s, so in AdMob mark ad requests for minors as "under age of consent". The code will send that flag for the 13–17 age band.
5. 🔑 Send me: the **App ID** (`ca-app-pub-…~…`) and the **ad unit IDs**. Until then I use Google's official test IDs, so nothing is billed and nothing breaks policy.

## 4. Legal pages (needed before release)
A **Privacy Policy** URL is required (health, location, camera and ads data). I can draft the text for you to host, for example on GitHub Pages for free. Also needed: Terms, and the Play **Data safety** form; I'll fill in the answers for you to paste.

## What I build in Part 2 once I have the keys
Two Flet extensions, the same way notify and vision are built:
- `flet_lumen_billing` wrapping RevenueCat's `purchases_flutter`;
- `flet_lumen_ads` wrapping `google_mobile_ads` + UMP.

Both need your OK to add those Flutter packages. Premium status always comes from the store, never from the save file.
