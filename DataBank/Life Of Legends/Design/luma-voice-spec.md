# Luma: system voice and Arcane theme (spec)

> Renamed from Lumen on 2026-11-05 (user-facing text and voice clips). Code identifiers keep `Lumen` (`LumenNotice`, `LumenThinking`, `flet_lumen_*`, `lumen_hum`).

Inspired by the isekai "inner wise-assistant" *genre feel*. Original design: no names, characters, logos or exact styling from any show.

## Decisions (user, 4 Nov)
- The assistant's name is **Luma**. The voice is **always on**.
- New **Arcane** theme is the **default and free**. Ember, Ocean, Forest and Royal stay in the shop. Ember also becomes free, so existing players who chose it keep it.

## Arcane theme
- Background: near-black navy (#070B14). Panels are translucent navy with a 1px cyan glow border.
- Primary: cyan (#4FE3F0). Accent (coins): soft violet (#A78BFA). Success: mint. Danger: soft rose.
- Panels have a faint outer glow (`shadow` with cyan at low opacity), a 12–16 radius, and corner ticks optional.
- Type: headings tracked-out uppercase small caps for labels ("QUEST CLEARED"), body stays readable.

## Luma voice (copy layer: one module, `ui/voice.py`, all strings in one place)
| Moment | Luma line (examples, rotate 2–3 variants) |
|---|---|
| Quest done | "Notice: Quest cleared. +40 XP to Warrior Path." |
| Coin cap | "Notice: Today's coin limit reached. Experience still counts." |
| Path level-up | "Confirmed: Chef Path has reached Lv 3." |
| Overall level-up | "Notice: Individual level increased → Lv 5." |
| Quest Board | Button "Ask Luma". Card header "Proposal:" + "Analysis: 10 min, beginner-friendly." |
| First completion of a board quest | "Skill acquired: Onion Dicing." |
| Bill due soon | "Advisory: Phone bill is due in 2 days." |
| Bill paid | "Confirmed: Payment recorded. Steward Path +15 XP." |
| Reward redeemed | "Confirmed: Reward granted. Enjoy it, you earned it." |
| Missed day | "Resuming is also a skill. Shall we continue?" (never guilt) |
| Weekly review | Titled "Luma Report". |
| App open / resume (after power_up, max once per 30 min) | Time-aware welcome back, e.g. "Welcome back. Luma online. Your quests are waiting." / "Good morning. Luma online. Your quests are ready when you are." / after 2+ quiet days: "Welcome back. It has been a few days. We begin again from here." (`core/welcome.py`, `voice.LINES["hello_again"]`) |
| Empty Today | "No active quests. Proposal: Ask Luma for one." |

## UI pieces
- **LumenNotice**: a top-anchored announcement panel (slides down, typewriter text reveal ~25ms/char, soft chime haptic, auto-hides after about 2.2s, queues). It replaces SnackBars and adds to the existing juice: the XP bar fill, card pop, floaters and level banner all stay.
- **Level banner** restyled in Arcane: glowing cyan frame and "CONFIRMED" eyebrow text.
- **Me → Skills**: board quests you've completed are listed as acquired skills. A later version adds levels like *Acquired → Refining → Mastered*, which you set yourself, never automatically.
- Voice lines go through one `say(kind, **values)` function, so wording can be tuned in one file.

## Out of scope for this pass
Voice audio or text-to-speech, and changing the skill-state data model (it needs a save-format change, so ask first).
