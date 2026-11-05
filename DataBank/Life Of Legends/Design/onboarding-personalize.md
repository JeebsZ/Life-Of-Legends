# Onboarding: Personalize with Luma (Nov 5, 2026)

The first-run flow is now a short, personal quiz over the mind-space. Each screen asks one question, and it takes about a minute.

**Steps:** Luma intro (orb, hum, typewriter) → hero name + sigil on a live name plate → "Which parts of life feel out of control?" (choose all that apply) → 3 "Do you relate?" cards (Yes/No, moves on by itself) → age range → sex for formulas (optional, "Prefer not to say") → daily time (5/15/30/60), best time of day, and a reminder opt-in → mind-space theme with a live preview → Luma's staged analysis → plan reveal → **Begin your legend** (lands on Today with the Welcome seal).
The top bar shows "NN% complete" with a short cheer that changes on each screen, plus Back and Skip on question screens. Continue stays off until the screen is answered.

**Existing players are never sent through it again.** Settings → Personalize → *Redo personalize* runs it again. Level, coins and quests are kept, and open starter quests are not added a second time.

**Data:** `Profile.onboarding` (OnboardingAnswers) is additive in schema 5. It stores focus, relate, age_band, minutes, day_time, reminders, paths, difficulty and done_on. Sex goes into `BodyProfile.sex`, so the Body screen does not ask for it again. Age is stored as a band only.

**Rules (`core/onboarding.py`):**
- Each focus area adds 2 to its main Path and 1 to the other Paths. "Phone eats my evenings" adds 1 to Monk. The top 3 Paths are recommended. If fewer than 2 score, the plan fills up from Monk, Scholar and Warrior.
- Starter difficulty is 1 when the daily time is 15 min or less, or when the player relates to "lose steam" or "never start". Otherwise it is 2, and it is never 3.
- Each starter quest fits inside the daily time. "Never start" caps each quest at 10 min.
- 3 starter quests come from the base Quest Board, taken in turn from each recommended Path.
- The first side quest is the Path's hand-written rank-1 chain.
- The best time of day sets the daily reminder time. Reminders turn on only after an explicit yes. A first run with no answer leaves them off.

**Safety:** An age band of 13-17 means `Game.is_minor()` is true. It is also true when the Body age is under 18. Either source is enough. A minor gets no weight-loss plan and no run-ladder challenges.

Tests: `tests/test_onboarding.py`.
