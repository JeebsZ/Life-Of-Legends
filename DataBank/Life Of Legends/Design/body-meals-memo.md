# Body + Meals: build memo (5 Nov 2026)

**What's new:** two tiles under More → Track, **Body** and **Meals**. You can turn either off in Settings → Modules.

## Body
- Stats: height (cm or ft/in), age or birth year, sex (you can pick "prefer not to say", which averages the two formulas), and activity level.
- Weight log in kg or lb with a trend chart, plus BMI with its WHO category and a note that BMI is only a rough screening number.
- **Lumen plan:** pick a goal (lose, keep or gain) and a pace (gentle, steady or fast). Lumen shows a staged analysis, then a proposal you can accept or skip.
  - **Daily calories:** shown as a range around a daily target. The target is your daily burn minus a deficit (7700 kcal per kg) and never goes below a safe minimum: your resting burn, or 1200 / 1500 / 1350 kcal (female / male / not given), whichever is higher. When that minimum kicks in, the plan takes longer and says so.
  - **Pace:** capped at 1% of your body weight per week.
  - **Macros:** protein about 1.8 g per kg (for a BMI above 25, it uses your weight at BMI 25). Fat is 25–30% of calories. Carbs make up the rest.
  - **Hints:** fiber and water.
- **Safety:** Lumen won't make a plan for a target below BMI 18.5. Weight-loss plans are for adults only. Every plan shows a "not medical advice" note.

## Meals
- A daily log split into breakfast, lunch, dinner and snack. Every food shows a **kcal range** with a confidence label.
- You can use favorites, recents and your own foods ("My foods"). Search forgives typos.
- **Calorie tracking is off by default.** With it on and a plan saved, you see a ring for calories and bars for each macro. A "kcal left" chip on Today is a separate setting and also off by default.
- **Scan:** take a photo (or pick one from the gallery on web/PC). Lumen analyses it, then you confirm each item. Grams you type count as scale grams, override any estimate and narrow the range. You can also pick small, medium or large portions. The photo is deleted unless you turn on "Keep meal photos".
- **XP:** small Monk XP for logging a weigh-in (once a day) or a meal (up to 9 XP a day). You never get XP for eating less.

## Food data
- 214 foods: 105 from USDA FoodData Central/SR Legacy (public domain) and 109 estimates for dishes (adobo, sinigang, kare-kare, kakanin, …).
- Dishes vary by cook, so their ranges are wider.

## Save
- The save file moves to schema 5. The change only adds data: older saves load with empty logs and default settings.

## Not checked yet
- The live camera on a real phone, and camera permission on Android. The web/PC picker path was tested.

## Round 2 (5 Nov): USDA databank and restaurants
- **Databank:** 8,077 foods from USDA FoodData Central (374 from Foundation Foods, released 2026-10-29, and 7,703 from SR Legacy, released 2018-04). It's in `src/assets/data/usda_foods.json.gz` (0.24 MB) and loads the first time you search. Search takes about 3–40 ms on a PC. Rebuild it with `python -I tools/foods/build_usda.py` (instructions are at the top of the script).
- **Curated foods:** the 104 single-ingredient foods now use real FDC values (`tools/foods/sync_curated.py`). 54 of them changed a little; only beef steak (+17%) and plain yogurt (+27%) changed by more than 10%. Instant noodles is now marked as an estimate.
- **Restaurants:** a chain filter in Add food.
  - McDonald's PH uses the numbers the chain publishes (labelled "official"). Their site doesn't name each nutrition panel, so items were matched by page order, and serving weights in grams are estimates.
  - Jollibee, Chowking, Mang Inasal, Greenwich, KFC PH, Max's, Shakey's and Starbucks PH publish nothing usable, so their items are labelled estimates built from USDA foods, with a ±30% range.
  - US chains (McDonald's, KFC, Burger King, Pizza Hut, and others) come from USDA's own lab tests.
- **Credit:** the USDA credit line is on Me → Profile.
