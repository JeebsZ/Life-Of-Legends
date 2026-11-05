# Life Of Legends — Expanded Feature Design

## Product direction

Life Of Legends is a personal life tracker wrapped in a flexible role-playing game. Users choose what to track, create or accept quests, and earn Path XP and coins for real-world actions. The game should make progress visible without punishing missed days or pressuring users to spend money.

## Existing feature status

- **Flexible quest difficulty is already implemented.** Keep the easy, standard, and challenging options, and make sure editing a quest preserves or lets the user change its difficulty.
- The feature ideas below expand the product beyond the previously described MVP.

## Feature designs

### 1. Quest chains

Let users connect quests into a multi-step objective. A chain has a title, optional description, Path, steps, target date, and completion reward. Steps can unlock in order or remain available together, and generate one that is best suitable in learning that skill.

**Example:** Learn a safe knife grip → practice dicing an onion → cook a simple recipe using that technique.

**Suggestions:** Allow users to pause, reorder, skip, or edit steps. Award most XP per step and a modest completion bonus for the chain, so the same effort is not rewarded twice at full value. Show the next step on Today after a step is completed.

### 2. Quest templates

Users can save a quest as a reusable template with its title, details, Path, difficulty, estimate, recurrence, and default XP/coin reward. Templates speed up creating common routines such as gym sessions, weekly planning, or meal preparation.

Adding mundane tasks as well like Do your facial, oral, skin care and so on.

**Suggestions:** Include a small starter library, but make every template editable. Let a user create a quest from a template without changing the original.

### 3. Flexible difficulty — already implemented

Retain the existing easy, medium, and hard quest choices. Each choice should adjust the expected effort and reward transparently. Users should be able to change difficulty when editing or rescheduling a quest.

**Suggestions:** Avoid framing the easy version as failure. Make it a valid way to keep momentum on a busy or low-energy day.

### 4. Energy check-in

Offer an optional one-tap check-in such as low, okay, or high energy, with an optional mood note. Use it to sort or suggest quests that fit the user's current capacity.

**Suggestions:** Never block a quest based on a check-in or make health conclusions from it. Keep the log private, skippable, and easy to delete. Users can turn off suggestions or energy tracking.

### 5. Focus timer

Provide a configurable work/study timer with focus and break intervals, pause/resume, and a note or linked quest. On completion, offer to log the session and award the related Path XP.

**Suggestions:** Allow custom interval lengths and a simple stopwatch mode. Do not require the user to finish a preset interval to count their work; support partial sessions and interruptions.

### 6. Habit and activity calendar

Show quests, habits, workouts, sleep entries, and bill due dates in day, week, and month views. Use distinct, readable symbols and let users filter categories.

**Suggestions:** Mark rest days and intentionally skipped items neutrally. Let users tap a day to review or edit its entries. Avoid a calendar that visually treats every blank day as a broken streak.

### 7. Achievements (Can be skipped for now  but create me a list of achievements so I can plan a design for it or actually you can use claude design to create them, do these last)

Create optional badges for meaningful milestones: first quest, first quest chain, trying several new skills, or returning to a habit after a break. Achievements can be tied to a Path or the whole account.

**Suggestions:** Prefer effort and exploration milestones over body, weight, spending, or perfect-streak targets. Make progress toward an achievement visible and explain how it is earned.

### 8. Boss quests

A boss quest represents a larger task and breaks it into manageable stages, such as a room cleanup, project, or appointment preparation. Show stage progress and the next actionable step.

**Suggestions:** Let users define their own stages, due dates, and rewards. Keep the boss metaphor optional or renameable for users who prefer a calm productivity style. Avoid large XP payouts that encourage users to create artificial task splits just to farm rewards. Adding a health bar for the boss would work perfectly.

### 9. Inventory and collectibles

Add an optional collection screen for cosmetic items, profile decorations, titles, and perhaps a customizable personal space. Users earn coins through quests and spend them on items.

**Suggestions:** Start with simple cosmetics and seasonal collections. Show prices before purchase, confirm coin spending, and make it clear that coins have no cash value. Avoid loot boxes or random paid rewards.

### 10. Monthly challenges

Let a user set a month-long goal, such as trying four recipes, completing a chosen number of workouts, or reading regularly. Display progress and allow the target to be adjusted.

**Suggestions:** Make challenges private by default and self-paced. Offer pause/edit controls and avoid all-or-nothing expiration penalties. Social/group challenges can be a later opt-in feature.

### 11. Calendar integration

Allow users to view or add quests to a device calendar, subject to platform permissions. Start with one-way export so the app can place a scheduled quest on a calendar without importing private calendar details.

**Suggestions:** Let users select which quests sync, choose a calendar, and revoke access. Keep reminders configurable and prevent duplicate events when a quest changes.

### 12. Voice capture

Allow speech to create a draft quest, note, or reminder. Show the recognized text for review before saving, with fields such as title, date, Path, and details editable.

**Suggestions:** Ask permission only when voice capture is used. Provide equivalent text entry and avoid recording continuously in the background.

### 13. Widgets and quick actions

Offer mobile widgets and desktop shortcuts for today’s next quest, completing a quest, starting a focus timer, adding a note, or logging water.

**Suggestions:** Keep sensitive details off the lock screen unless the user opts in. Sync actions reliably and show a clear confirmation if an offline change is pending.

### 14. Progress insights

Summarize user-controlled trends, such as completed quests by Path, workout frequency, sleep duration, or consistency with a chosen habit. Use plain descriptions and time ranges.

**Suggestions:** Show the data behind each insight and avoid claiming that one activity caused another. Let users hide categories and exclude unusual weeks. Do not turn financial or health trends into prescriptive advice.

### 15. Backup and export

Let users back up and restore their profile, quests, Path progress, notes, bills, and logs. Offer a readable export such as CSV for tables and JSON for a full backup.

**Suggestions:** Explain what is included, allow category selection where practical, and provide a clear delete-account/data option. Protect backups because they may contain financial and health information.

### 16. Savings and investment tracker

Add a Finance area with separate **Savings Goals** and **Investment Holdings**.

**Savings goals** can include a name, target amount, current amount, currency, target date, and optional contributions. Examples: emergency fund, new computer, or travel. Show amount remaining and progress. Let users log deposits and withdrawals with dates and notes; edits should preserve a transaction history or clearly update the record.

**Investment holdings** can be recorded manually with asset name or ticker, account label, quantity, cost basis, currency, and optional current value/date. A portfolio overview can show user-entered totals and changes over time. Begin with manual values; live prices, brokerage connections, and automatic trading add substantial integration and security work.

**Suggestions:** Clearly label values as user-entered and time-stamped. Do not present projections as guaranteed, recommend investments, or suggest a user buy/sell. Keep financial tracking separate from game rewards: XP may reward reviewing a budget or logging a contribution, but coins should never be tied to investment gains or encourage risky behavior. Support multiple currencies only if the user selects them, and do not silently convert values.

### 17. Edit quests, rewards, and bills

Provide an edit action from the item detail view and from list/calendar views. Users should be able to change titles, details, dates, recurrence, amounts, categories/Paths, and status.

**Quest editing:** Change difficulty, Path, schedule, XP/coin reward, and chain membership. Preserve completion history when editing a recurring quest. Ask whether an edit applies to this occurrence or future occurrences. For custom task only, also to avoid over pricing the coins lets limit the maximum coin to gain depending on the difficulty of the task no?

**Reward editing:** Change name, description, coin price, category, and availability. Keep a redemption history so changing a reward does not rewrite past redemptions. If a user deletes a reward that has been redeemed, retain the historical record with an archived label.

**Bill editing:** Change payee/name, amount, due date, recurrence, reminder timing, and paid status. Preserve previous payment records when the bill amount or schedule changes. For recurring bills, distinguish editing one occurrence from changing the series. Provide archive/delete controls and a confirmation when deletion removes future reminders.

### 18. Robust workout logging

Design the workout area around structured sessions, with a quick-log path for users who do not want detailed tracking.

**Workout session fields:** date/time, workout type, duration, notes, perceived effort, and optional linked quest/Path. Allow templates for common workouts and a history view with filters.

**Strength training:** Support routines, exercises, sets, reps, weight, rest timer, and optional distance/time for cardio. Let users reorder exercises, copy a past session, and compare an exercise with their own prior sessions. Support bodyweight exercises and units such as kg/lb.

**Suggestions:** Keep personal records descriptive and user-owned; don’t prescribe a training plan or infer medical readiness. Make edits possible after a session is saved. Offer an optional rest timer that can be started between sets. Manual entry should work without wearable integrations.

### 19. Robust sleep logging

Support bedtime, wake time, total sleep duration, optional naps, and a simple restedness rating. Allow users to enter sleep after waking and correct times later. Display nightly entries, weekly averages, and a simple trend chart.

**Suggestions:** Handle sleep crossing midnight and missing entries gracefully. Keep sleep scoring optional and explain how any score is calculated. Avoid diagnosis or medical claims; users should be able to disable sleep insights and delete entries.

### 20. Water intake and timer

Allow a daily water goal and quick-add buttons for common amounts, plus custom amounts and units. Show progress toward the user's chosen goal and a daily history.

Add an optional hydration timer/reminder: users choose an interval or reminder schedule, quiet hours, and active days. Notifications should be snoozable or dismissible, and the timer should pause when the user disables it.

**Suggestions:** Do not prescribe a universal water target. Let users set or disable goals and reminders. Avoid nagging when the goal is reached, during quiet hours, or after repeated dismissal. Keep hydration logging separate from XP farming; use a modest daily cap if it grants game rewards.

## Navigation suggestion

Use a bottom navigation bar on mobile with **Today**, **Paths**, **Logbook**, **Finance**, and **Profile/Rewards**. On desktop, use a left sidebar. Keep quest creation available from Today and Paths, bill/savings/investment editing in Finance, and workout/sleep/water history in Logbook.

Keep every button from overcrowding, keep the 5 buttons as is but change the last button to be a "more" button insted of just me, after opening it the other implemented traits would be listed there as a button similar to how GCASH handles buttons.

## Suggested delivery order

### Phase 1: Core game quality

- Quest editing and recurring quest behavior
- Quest templates and quest chains
- Focus timer and calendar view
- Achievements and flexible difficulty polish
- Backup/export basics

### Phase 2: Health and daily tracking

- Structured workout sessions and exercise history
- Sleep logging and trends
- Water quick-log and configurable timer
- Energy check-in and progress insights

### Phase 3: Finance and collections

- Bill editing, recurrence, reminders, and payment history
- Savings goals and contribution history
- Manual investment holdings and dated valuations
- Personal rewards, collectibles, and cosmetic inventory

### Phase 4: Convenience and expansion

- Calendar export, voice capture, widgets
- Monthly challenges and boss quests
- Optional coupon integrations if an authorized provider is available

## Product rules to keep the app healthy

- Make tracking optional and quick; users choose which modules appear.
- Never remove earned XP or coins because of missed days.
- Keep real money, bills, savings, and investments out of reward pressure mechanics.
- Make edits and history clear, especially for recurring quests and bills.
- Give users control over reminders, sensitive data, exports, and deletion.
- Treat photo-based food estimates and all health data as uncertain, private information.

# Lifestyle and Companion Features — Design Expansion

This section incorporates the latest product direction. Energy check-ins and routine quests already exist; keep those as foundations and avoid adding duplicate screens for them.

## Existing features to extend

### Energy-aware companion suggestions

The current low/okay/high energy check-in already adjusts suggestions and offers encouragement. Extend it into the recommendation system: suggest a short reset, a suitable quest, a hobby activity, or a small next step. Keep suggestions optional, explain why they appeared, and let users dismiss them or tune the categories. Encouragement should be warm without implying the user has failed or needs fixing.

### Routines

Routines already use quests. Add optional routine templates and a sequence view if useful, but keep routine steps in the existing quest system instead of creating a separate competing tracker.

## New lifestyle feature designs

### 1. Private Journal

Give users a private space for freeform entries, prompts, and reflections. A journal entry can optionally link to the day, a Path, a quest, an energy check-in, or a photo. Possible prompts include “What felt good today?”, “What is taking up space in your mind?”, and “What would make tomorrow easier?”

**Keep it distinct from activity logs:** logs capture structured events such as a workout, sleep time, or completed quest. The journal is for thoughts and context. Do not automatically turn journal text into quests, recommendations, or analytics. Make it private by default, searchable/exportable, and deletable. Offer optional local lock or biometric protection where supported.

### 2. Outfit planner and clothing design studio

Build a wardrobe workspace where users can save clothing items, create outfit combinations, plan looks for occasions, and sketch or design original clothing. Users can photograph an item they own, add tags such as color, type, season, or occasion, and combine it with other items on a visual board. For original designs, support a simple canvas with shapes, colors, labels, and reference photos before investing in advanced drawing tools.

**Reference photos and selfies:** allow an optional full-body or selfie reference for personal styling or design inspiration. Keep the image private by default, explain where it is stored, and let users remove it. Avoid body ratings, attractiveness scores, or claims about what someone should wear for their body. Offer suggestions based on user-selected style, color, comfort, weather, and occasion instead.

**Sharing and safety:** sharing should be opt-in and separate from private wardrobe storage. Before posting, show a preview and allow the user to crop out faces, surroundings, school/work identifiers, name tags, addresses, and other personal details. Remove location metadata. Add block, report, and moderation controls. Do not publish a user’s face or reference photo by default. For public inspiration posts, prioritize outfit/design images and user-written descriptions; prohibit sexualized content involving minors and other unsafe content under clearly stated community rules. Consider starting with private saves and curated inspiration before opening user posts.

**Useful additions:** outfit calendar, packing lists generated from selected outfits, “wear again” rotation, favorite combinations, and a weather-aware suggestion only after users opt into location or provide a destination.

### 3. Cookbook, recipes, and grocery planning

Let users save recipes, plan meals, and turn chosen recipes into a combined grocery list. Recipe details can include ingredients, quantities and units, servings, preparation steps, estimated time, equipment, tags, and step timers. Users should be able to scale servings and check off ingredients. Pantry staples and dietary preferences can be optional filters, not assumptions.

**Recipe sources:** use a licensed recipe dataset, public-domain/appropriately licensed material, user-created recipes, or a permitted recipe provider. Do not copy whole recipes from arbitrary websites without permission. When a recipe comes from an external source, store its source link and attribution and respect the provider’s terms. Users should be able to save their own notes and substitutions.

**Timers and measurements:** allow multiple named timers attached to recipe steps; support common units and let users choose metric or US customary units. Make ingredient quantities explicit and editable. For food safety instructions or nutrition claims, use reputable sources and show source context rather than inventing guidance.

**Grocery list:** combine ingredients across planned recipes, aggregate compatible quantities when possible, preserve separate units when conversion is unclear, and let users add non-recipe items. Support aisle/category grouping, manual check-off, and sharing/export later. Meal planning should not require calorie tracking.

### 4. Social reminders and phone calendar connection

Use the existing calendar integration for birthdays, occasions, and user-created reminders to contact someone. A reminder such as “Send a greeting to Sam” should be created only from information the user enters or permits the app to access.

**Suggestions:** request calendar/contact permissions only when a feature needs them. Offer a manual option that needs no contacts permission. Show the event source and let the user edit, snooze, or delete it. Keep contact details private and avoid importing an entire address book when a single reminder is enough. Do not generate or send messages without user review.

### 5. Bucket list with guided plans

Create a Bucket List area for experiences and long-term personal goals. Each item can have a title, why it matters, target season/date, estimated budget, status, notes, and optional photos. A **Make a plan** action can turn the goal into an editable sequence of steps, quests, savings targets, and a checklist.

**Example — travel to Japan:** clarify the traveler’s dates, departure city, trip length, interests, and rough budget; draft research steps for choosing destinations, comparing flights, checking entry documents, planning local transport, and preparing a packing list. Add a savings goal and optional contribution quests. Keep itinerary and estimated costs editable.

**Current information matters:** travel prices, entry requirements, airport/security rules, and local conditions change. The planner should link to official, current sources, show when information was checked, and distinguish verified facts from estimates or user notes. Avoid promising exact costs or eligibility. Before purchase or travel, prompt the user to confirm requirements with the relevant official source. Keep any generated itinerary as a draft that the user reviews.

**Make it work for non-travel goals too:** support goals such as learn to play a song, attend a concert, finish a creative project, or try a new hobby. Plans should be optional, adjustable, and broken into manageable next actions rather than presented as a rigid prescription.

### 6. Separate Hobby Tracker

Add a standalone **Hobbies** space so hobby activity and inspiration do not clutter daily task lists. This should fit the current navigation groupings: **YOU, TRACK, PLAN & FOCUS, DATA & APP**. Place Hobbies under the most natural existing group or let users pin it; do not create an extra top-level grouping unless the app’s navigation needs it.

Each hobby space can have a description, images/links, current project, ideas backlog, practice log, materials list, and optional related Path. A user could track a guitar practice session without having to turn every practice into a quest. They can promote an idea or session into a quest when they want game progression.

### 7. Digital Wellbeing — opt-in

Offer optional screen-time goals, focus boundaries, app-break reminders, and an offline activity list. Where operating-system screen-time permissions are unavailable or declined, support manual check-ins instead.

**Suggestions:** make the feature easy to disable and avoid shaming language, streak loss, or lockouts. Users set their own boundaries and quiet hours. Keep collected app-usage data local or minimized where feasible, explain permissions in plain language, and never require it for other LifeQuest features.

### 8. Home and Life Admin

Keep bills in Finance. Add a separate Life Admin area for household and personal maintenance that does not fit naturally under bills: chores, errands, appointments, renewals, document checklists, warranties, and household supply reminders.

Examples include “replace air filter,” “renew ID,” “book dentist,” and “buy detergent.” Support recurring schedules, categories, notes, attachments, and reminders. For sensitive documents, store only what is necessary and clearly explain access, backup, and deletion. Do not turn all life maintenance into mandatory quests; users can manage it as a simple list.

### 9. Companion Room

Let users decorate a room for their in-app companion using earned cosmetics, collected items, and themes. The companion can react with small animations or dialogue to milestones, rest, and Path progress, while staying supportive rather than guilt-inducing.

**Art scope:** start with a small modular art kit: a few room backgrounds, palettes, furniture silhouettes, and companion poses that can be recombined. Add more art packs over time. This gives customization early without requiring a huge catalog of unique illustrations. Keep items cosmetic and avoid random paid loot mechanics. A user should be able to hide the companion or mute its reactions.

### 10. Personal Recommendation Engine

Make LifeQuest feel like a companion by offering a small number of useful, timely suggestions across quests, hobbies, rest, study/work, and personal goals. Use user-selected interests, available time, current energy, upcoming calendar items, and previously saved preferences where the user has enabled them.

Example: “You have 15 minutes before your next event and your energy is low. Want to do a short reset, review five flashcards, or take a break?”

**Controls and quality:**

- Explain briefly why each suggestion appeared.
- Offer accept, edit, dismiss, and “show me less like this.”
- Respect quiet hours, rest days, calendar availability, and opt-outs.
- Limit suggestion frequency and avoid repeating a dismissed suggestion immediately.
- Do not infer sensitive traits or make medical, financial, or psychological claims.
- Keep recommendations useful even if the user does not connect a calendar or enable tracking.
- Let the user choose which data sources the feature may use and clear recommendation history.

## Lifestyle navigation and delivery order

Keep the current **YOU, TRACK, PLAN & FOCUS, DATA & APP** organization. A possible placement is Journal and Hobbies under **YOU**; calendar, routines, and lifestyle logs under **TRACK**; bucket-list planning and recipes/groceries under **PLAN & FOCUS**; sharing, recommendation controls, and privacy settings under **DATA & APP**. Outfit planning may be pinned or placed under **YOU** depending on the existing navigation structure.

Suggested order:

1. Journal with privacy controls; hobby spaces; bucket-list items with user-authored steps.
2. Outfit boards and private wardrobe capture; grocery lists and user-saved recipes.
3. Calendar-based social reminders; opt-in digital wellbeing; life-admin lists.
4. Companion room using a small modular art set.
5. Guided travel planning with current, linked sources; safe outfit inspiration sharing; richer personalized recommendations.

Build the recommendation controls and privacy choices alongside the feature that uses them, rather than postponing them until after launch.
