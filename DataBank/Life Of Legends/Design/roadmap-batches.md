# Roadmap — batches (Part 1 → Final)

Each Part ships as a working, tested APK before the next one starts.

| Part | Contents | Needs from you |
|---|---|---|
| **1 — now** | New onboarding · Luma rename + welcome back · quiet taps · **custom middle nav slot** (Bills → More) · **Study** (flashcards, multiple choice / fill-in / true-false, notes → cards) · **Premium foundation**: weekly limit bank, coin-unlock cosmetics, opt-in ad flow (stretch screen before a run), offer + season deal screens. Dev toggle only, no real payments. | OK for the on-device text-recognition plugin (Study scan) |
| **2** | **Real payments + ads**: Play Billing via RevenueCat, AdMob rewarded ads, consent form, student discount · **Translations** (Filipino, Spanish, Indonesian, Japanese, Korean, Chinese, Portuguese, French, German, Arabic + more; the app follows the phone language) · **Food scan accuracy** (see below) | Play Console + RevenueCat + AdMob accounts ([[paywall-setup-guide]]) |
| **3** | Lifestyle 1: Private Journal (with lock) · Hobbies space · Bucket list with guided plans · Life Admin lists · Boss quests with HP bars · Monthly challenges · Savings goals | — |
| **3b** | **Students & Workers** (from [[chatgpt-2026-11-05-planning]]): Student / Worker / Personal context modes · assignment & project breakdowns · class/meeting schedule · study/work session planner (uses Focus timer) · weekly review · end-of-day shutdown routine · reading/research log · distraction log · workload/capacity view · career-skills Path | — |
| **4** | Lifestyle 2: Cookbook + grocery list (licensed or user recipes) · Outfit planner (private) · Calendar export + social reminders · Digital wellbeing (opt-in) · Recommendation engine with controls | Recipe data source choice |
| **5** | **DLC skill packs**: downloadable free content (e.g. guitar chords and songs, using licensed/public material), each showing its size before install · Achievements · Collectibles/inventory | Hosting for packs (GitHub Releases, free) |
| **6** | **Character creation** + Companion Room · **Widget** (premium): one-tap tracking of the middle-slot feature · Companion on the widget | Avatar art batch |
| **7** | **Social** (opt-in feed: runs, gym, food, scores; block/report/moderation) · **Multiplayer**: friends, parties, guilds, guild boss fights | A backend: Firebase/Supabase free tier, plus moderation plan |

## Food scan "100%"
No photo model can be right 100% of the time; portions and hidden oil can't be seen in a photo. A scan can still *feel* 100% reliable:
1. **Barcode scan** for packaged food. Exact label data from Open Food Facts (free).
2. **Learns from you.** Every correction is remembered, so your usual adobo gets recognised next time. This is an on-device personal match on the model's own image features.
3. **Restaurant menu shortcut.** Pick "Jollibee" and choose items instead of photographing.
4. **Better base model** fine-tuned on Food-101 plus Filipino dishes (needs a training pass).
5. **Optional premium cloud fallback** (Claude vision) when the on-device guess is unsure. It's paid per scan, so it stays premium-only.
6. **Scale grams always override.** Confirm before saving, as now.

## Flags from the ChatGPT planning doc (not resolved)
- It opens with "they are all implemented now". Only Phases 1–2 and parts of 3 are built. Journal, hobbies, bucket list, life admin, outfit, cookbook and recommendations are **not built yet** (Parts 3–4).
- It says "bills remain in **Finance**". There's no Finance area yet: Bills currently lives in More, and Savings is Part 3. Do we create a Finance group in More then?
- Rest/reset activities: plan is **quests that raise Monk XP** (no new tracker). Memory journal and seasonal themes are dropped as redundant, per you.

## Future feasibility notes
- **Companion walking over other apps** needs Android's "display over other apps" permission. It's doable on Android only, Google Play reviews it strictly, and it's impossible on iOS. A home-screen widget companion is the safe version.
- **Social and multiplayer** need a server, accounts, moderation and privacy rules (minors are in the 13–17 band). That's the biggest jump in this roadmap.
