# Meal photo scan — plan & scope (proposal, not built)

**Goal:** snap a meal, get the likely foods with a calorie *range*, fix anything wrong, then save it. It counts as a Logbook "meal" entry and can complete a Chef or health quest.

## How it would work
1. **Capture.** `ft.FilePicker` (gallery, works now) → later `flet-camera` 1.0.5 (live camera; this is a new dependency and needs your OK).
2. **Shrink.** Resize to about 1024px on-device before sending. That's cheaper and faster, and keeps less of your data.
3. **Recognize.** Send the photo to a vision model (Claude) and ask for strict JSON: `[{food, portion_guess, kcal_low, kcal_high, confidence}]`.
4. **Confirm.** An editable card shows each item with chips like "~450–650 kcal · medium confidence". You can rename items, change the portion size and delete items. Nothing saves until you tap **Save**.
5. **Store.** Save a `MealEntry` in the Logbook. Keep the photo only if you choose to (default: discard after scan).

## Why a cloud model, not on-device
On-device food classifiers name the dish but can't estimate portions. They're also heavy to ship in a Flet APK. A vision model handles mixed Filipino plates (rice + ulam) much better. The trade-off: it needs internet, and each scan costs money.

## Scope by phase
| Phase | What | Depends on |
|---|---|---|
| **M0 — Manual meal log** | Quick meal entry (name + optional kcal), "favorites" for repeat meals. No AI. | v1 Logbook |
| **M1 — Spike (me-only)** | Photo → Claude → JSON → confirm card. API key stored in your local settings. Test 20 real meals and measure accuracy, latency and cost per scan. | M0, your API key |
| **M2 — Daily use** | Daily kcal *range* on Today (optional, off by default), meal history, re-use past items | M1 passes your accuracy bar |
| **M3 — Public-ready** | Small backend proxy so no API key ships in the APK. Rate limits, privacy notice, photo delete, opt-in toggle | Store release |

## Rules (from the design chat, kept)
- Always show a range and a confidence level, never "exactly 512 kcal".
- Calorie tracking is opt-in. A plain meal log works without numbers.
- No streaks or penalties tied to eating less.

## Decisions needed from you
1. OK to add `flet-camera` (and later an HTTP client) as dependencies?
2. Is a personal API key fine for M1? It's paid per scan.
3. What accuracy bar must M1 hit before M2? Suggestion: correct food in 8 of 10 meals, and kcal range contains your own estimate in 7 of 10.
   
   ## Answers
1. Yes please add it.
2. Would that cost me money to use? If yes find me alternatives please.
3. Correct food in 8 of 10 meals, kcal range, and can input or adjust if needed when the user has a weighing scale.

## Follow-up (4 Nov), from your answers
**Does it cost money?** Yes. The Claude vision API is paid per scan. Free routes, best first:

| Route | Cost | Accuracy for you | Notes |
|---|---|---|---|
| **A. Scale-first (recommended)** | Free | Best: grams come from your scale | Photo is optional. You pick the food (search + your favorites), enter grams, kcal = grams × kcal/100 g. Data from **USDA FoodData Central** (free key, about 1,000 requests/hour) + **Open Food Facts** (free, no key, has barcodes for packaged food). Filipino dishes: we build a local list of your own ulam favorites. |
| B. Free-tier vision APIs (LogMeal, SnapCalorie, CaloAI on RapidAPI) | Free tier, then paid | Unverified | Limits and accuracy aren't confirmed. Would need testing before relying on them. |
| C. Claude vision (original M1) | Paid per scan | Likely best photo guess | Keep it as a later option if you want "snap and forget". |

**Your accuracy bar (locked in):** correct food in 8 of 10 meals, show a kcal range, and always let you **type or adjust grams** from your weighing scale. Grams entered by you override the photo estimate.

**Revised M1:** Route A first (free, no AI), with a photo kept only as a memory and optional. Try Route B's free tier as an add-on and test it against your 8/10 bar.

**flet-camera:** installed 4 Nov (1.0.5).
