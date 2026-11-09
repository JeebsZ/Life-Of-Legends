"""Built-in data: Paths, themes, the Quest Board, side quest chains, quest templates and the
learning-chain generator text.

Plain data only. The UI owns theme colors; it must use the same theme ids as THEMES.
"""

from lol.core.models import (
    CatalogChain,
    CatalogQuest,
    CatalogStep,
    PathDef,
    QuestTemplate,
    ThemeDef,
)

PATHS: list[PathDef] = [
    PathDef("chef", "Chef", "restaurant", "#E76F51"),
    PathDef("warrior", "Warrior", "fitness_center", "#D62828"),
    PathDef("scholar", "Scholar", "menu_book", "#457B9D"),
    PathDef("artisan", "Artisan", "palette", "#9B5DE5"),
    PathDef("ranger", "Ranger", "forest", "#2A9D8F"),
    PathDef("steward", "Steward", "account_balance_wallet", "#E9C46A"),
    PathDef("monk", "Monk", "self_improvement", "#84A98C"),  # self-care, hygiene, calm routines
]
PATH_IDS: tuple[str, ...] = tuple(p.id for p in PATHS)

DEFAULT_THEME = "arcane"  # new saves start here
FREE_THEMES: tuple[str, ...] = ("arcane", "ember", "rose")  # every save owns these
THEMES: list[ThemeDef] = [
    ThemeDef("arcane", "Default Theme", 0),
    ThemeDef("ember", "Ember Theme", 0),  # free: the default before Arcane, so old saves keep it
    ThemeDef("rose", "Rose Theme", 0),  # free for everyone, never gated
    # Coin-unlockable themes for everyone:
    ThemeDef("matcha", "Matcha Theme", 250),
    ThemeDef("lavender", "Lavender Theme", 250),
    ThemeDef("sakura", "Sakura Theme", 300),
    ThemeDef("cyber", "Cyber Theme", 350),
    ThemeDef("solar", "Solar Theme", 400),
    ThemeDef("crimson", "Bloodmoon Theme", 450),
    ThemeDef("aurora", "Aurora Theme", 500),
    ThemeDef("abyss", "Abyssal Theme", 600),
    # premium-only: Legends+ unlocks the right to buy these with coins (never grants them)
    ThemeDef("ocean", "Ocean Theme", 300, premium_only=True),
    ThemeDef("forest", "Forest Theme", 300, premium_only=True),
    ThemeDef("royal", "Royal Theme", 600, premium_only=True),
]
THEME_PRICES: dict[str, int] = {t.id: t.price for t in THEMES}
THEME_BY_ID: dict[str, ThemeDef] = {t.id: t for t in THEMES}

_Q = CatalogQuest
QUEST_BOARD: list[CatalogQuest] = [
    # Chef
    _Q("Cook a simple egg breakfast", "chef",
       "Scrambled or fried, your way. Cook eggs until no runny white is left.", 1, 15),
    _Q("Make a fresh salad", "chef",
       "Wash the greens, add 2-3 toppings you like, and a simple dressing.", 1, 15),
    _Q("Cook rice on the stove or rice cooker", "chef",
       "Rinse the rice, use about 1 part rice to 1.5-2 parts water, and let it rest a bit.", 1, 30),
    _Q("Cook a one-pan meal", "chef",
       "Pick a recipe with 5 ingredients or less and follow it step by step.", 2, 40),
    _Q("Try a new recipe", "chef",
       "Read the whole recipe first, then prep all ingredients before you start.", 2, 60),
    _Q("Plan and prep meals for 3 days", "chef",
       "Write a short menu, shop once, and store portions in the fridge.", 3, 90),
    # Warrior
    _Q("Take a 10-minute walk", "warrior",
       "Any pace that feels comfortable. Outside or around the house counts.", 1, 10),
    _Q("Stretch for 5 minutes", "warrior",
       "Gentle stretches only. Stop if anything hurts.", 1, 5),
    _Q("Do a short bodyweight set", "warrior",
       "A few easy reps of squats or wall push-ups. Go at your own pace.", 2, 15),
    _Q("Walk or jog for 20 minutes", "warrior",
       "Keep a pace where you can still talk. Bring water.", 2, 20),
    _Q("Try a beginner workout video", "warrior",
       "Pick a beginner-level video and take breaks whenever you need.", 3, 30),
    # Scholar
    _Q("Read for 10 minutes", "scholar",
       "Any book or long article. Note one idea you liked.", 1, 10),
    _Q("Learn 5 new words", "scholar",
       "In any language. Write them down with a short example sentence.", 1, 10),
    _Q("Watch a short lesson and take notes", "scholar",
       "Pick a topic you are curious about. Write 3 key points.", 2, 25),
    _Q("Explain something you learned", "scholar",
       "Write a short paragraph as if teaching a friend.", 2, 20),
    _Q("Finish a chapter or module", "scholar",
       "Work through one full chapter or course module, then summarize it.", 3, 60),
    # Artisan
    _Q("Doodle for 10 minutes", "artisan",
       "No goal, no eraser. Just draw what you see or imagine.", 1, 10),
    _Q("Take 5 photos of one theme", "artisan",
       "Pick a color or shape and find it around you.", 1, 15),
    _Q("Write a short poem or story", "artisan",
       "Keep it under a page. Done is better than perfect.", 2, 20),
    _Q("Fix or tidy up something you own", "artisan",
       "Sew a button, glue a crack, or organize a drawer.", 2, 30),
    _Q("Start a small creative project", "artisan",
       "Pick something you can finish this week and do the first step.", 3, 60),
    # Ranger
    _Q("Step outside for fresh air", "ranger",
       "Spend a few minutes outdoors and notice 3 things around you.", 1, 10),
    _Q("Water or care for a plant", "ranger",
       "Check the soil first; water only if it feels dry.", 1, 5),
    _Q("Visit a park or green space", "ranger",
       "Walk around and take in the view. Bring water and sun protection.", 2, 40),
    _Q("Spot and name 3 birds or plants", "ranger",
       "Use a free app or guide book to identify them.", 2, 30),
    _Q("Go on a short easy trail walk", "ranger",
       "Pick a well-marked, beginner trail and tell someone where you are going.", 3, 90),
    # Steward
    _Q("Write down today's spending", "steward",
       "List what you spent today, even small things.", 1, 5),
    _Q("Tidy one small area", "steward",
       "A desk, a shelf, or a bag. Five focused minutes.", 1, 10),
    _Q("Check your upcoming bills", "steward",
       "Add any missing bills to the Bills tab with their due dates.", 1, 10),
    _Q("Set a simple weekly budget", "steward",
       "Decide how much you will spend on food and fun this week.", 2, 20),
    _Q("Sort out one subscription", "steward",
       "Review one subscription and decide to keep it or cancel it.", 2, 15),
    _Q("Do a full room clean-up", "steward",
       "Declutter, wipe surfaces, and take out the trash.", 3, 60),
    # Monk
    _Q("Take three slow breaths", "monk",
       "Breathe in through your nose, out a little longer. Just three.", 1, 2),
    _Q("Brush and floss with care", "monk",
       "Two unhurried minutes of brushing, then floss.", 1, 5),
    _Q("Do a gentle skin care routine", "monk",
       "Cleanse and use the products you already like. Gentle is fine.", 1, 10),
    _Q("Sit quietly for 5 minutes", "monk",
       "Sit comfortably, notice your breath, let thoughts pass by.", 1, 5),
    _Q("Fill your water bottle and keep it near", "monk",
       "Sip when you feel like it. No target needed.", 1, 2),
    _Q("Make a calm evening wind-down", "monk",
       "Warm shower, comfy clothes, dim the screens a little earlier.", 2, 30),
    _Q("Write three things that went okay today", "monk",
       "Small things count: a good meal, a kind word, a quiet moment.", 2, 10),
    _Q("Have a phone-free hour", "monk",
       "Put the phone in another room and do something slow you enjoy.", 3, 60),
]

# --- Side quest chains ---------------------------------------------------------------------------
# Each skill: a rank-1 base chain (id = skill id) plus follow-ups "<id>-r2" and "<id>-r3".
# Steps are (title, note, difficulty). Wording stays safe and beginner-level.
_S = tuple[str, str, int]


def _skill(
    skill_id: str, name: str, path_id: str, blurb: str,
    r1: tuple[_S, _S, _S], r2: tuple[_S, _S, _S], r3: tuple[_S, _S, _S],
) -> list[CatalogChain]:
    out = []
    for rank, steps in ((1, r1), (2, r2), (3, r3)):
        cid = skill_id if rank == 1 else f"{skill_id}-r{rank}"
        out.append(CatalogChain(cid, name, path_id, rank,
                                tuple(CatalogStep(*s) for s in steps), blurb))
    return out


SIDE_QUESTS: list[CatalogChain] = [
    # Chef
    *_skill("knife-skills", "Knife Skills", "chef", "Cut food safely, evenly and calmly.",
            (("Learn a safe knife grip",
              "Watch a short beginner guide on the claw grip. Tuck your fingertips in.", 1),
             ("Dice an onion slowly",
              "Use a stable board and a sharp knife. Slow is safe; speed comes later.", 1),
             ("Chop the vegetables for one meal",
              "Prep everything before you start cooking.", 2)),
            (("Practice even slices",
              "Cut a carrot or cucumber into rounds of the same thickness.", 1),
             ("Mince garlic or herbs", "Rock the knife gently and keep your fingers clear.", 2),
             ("Prep a full stir-fry",
              "Cut every ingredient to a similar size so it cooks evenly.", 2)),
            (("Cut a carrot into thin sticks",
              "Square it off first so it sits flat, then slice and stack.", 2),
             ("Prep a three-vegetable dish without rushing",
              "Take your time and keep the board tidy as you go.", 2),
             ("Cook a meal using only food you cut yourself",
              "Plan it, prep it, cook it. Enjoy the result.", 3))),
    *_skill("baking-basics", "Baking Basics", "chef", "Measure, mix and bake simple treats.",
            (("Pick a simple muffin recipe",
              "Read it twice and gather every ingredient before you start.", 1),
             ("Measure ingredients carefully",
              "Level off cups and spoons. Baking likes accurate amounts.", 1),
             ("Bake a batch of muffins",
              "Use oven mitts and set a timer. Check doneness with a toothpick.", 2)),
            (("Bake simple cookies", "Space them out on the tray; they spread as they bake.", 1),
             ("Make an easy no-knead bread", "Follow the rising times in the recipe.", 2),
             ("Share your bake and ask for feedback", "Note one thing to try next time.", 2)),
            (("Plan a bake for a small get-together",
              "Pick a recipe and write a shopping list.", 2),
             ("Try a recipe with a new technique",
              "Folding, rolling or piping. Watch a short guide first.", 2),
             ("Bake a cake or loaf from scratch",
              "Prep everything first. Let it cool before slicing.", 3))),
    # Warrior
    *_skill("bodyweight-basics", "Bodyweight Basics", "warrior",
            "Simple strength moves at your own pace.",
            (("Learn a basic squat",
              "Watch a beginner guide, then try 5 slow reps. Stop if anything hurts.", 1),
             ("Try wall or knee push-ups",
              "A few easy reps with good form beat many rushed ones.", 1),
             ("Do a 10-minute beginner circuit",
              "Squats, push-ups and marching in place. Rest whenever you need.", 2)),
            (("Hold a plank for a comfortable time",
              "Knees down is fine. Keep breathing steadily.", 1),
             ("Add one new move", "Try glute bridges or gentle lunges with good form.", 2),
             ("Do 3 short circuits in one week", "Spread them out and rest between days.", 2)),
            (("Build your own 20-minute routine",
              "Write down the moves, reps and rest. Keep it beginner-friendly.", 2),
             ("Do your routine 3 times in a week", "Go easy on any day you feel tired.", 2),
             ("Finish a full beginner workout",
              "Start to finish at your own pace. Bring water.", 3))),
    *_skill("running-start", "Running Start", "warrior", "Ease into running with walk-jogs.",
            (("Take a brisk 15-minute walk", "Wear comfortable shoes and bring water.", 1),
             ("Try a gentle walk-jog",
              "Jog 1 minute, walk 2 minutes, five times. Keep a talking pace.", 1),
             ("Walk-jog for 20 minutes", "Slow down whenever you need to.", 2)),
            (("Learn a warm-up and cool-down",
              "A few minutes of easy walking and gentle stretches.", 1),
             ("Walk-jog for 25 minutes",
              "Make the jog parts a little longer if it feels okay.", 2),
             ("Do 3 walk-jogs in one week", "Leave a rest day between them.", 2)),
            (("Jog 10 minutes without stopping",
              "Go slower than you think. A talking pace is perfect.", 2),
             ("Plan a safe 3 km route", "Pick well-lit paths with even ground.", 2),
             ("Complete a 3 km walk-jog", "Any mix of walking and jogging counts.", 3))),
    # Scholar
    *_skill("marketing", "Marketing", "scholar", "Understand how ideas find their people.",
            (("Read a marketing book (or 3 chapters)",
              "Any beginner-friendly book or a free online guide.", 1),
             ("Write 3 takeaways", "Put each idea in your own words.", 1),
             ("Try one idea on something real",
              "A post, a flyer or a pitch for a project or a friend's shop.", 2)),
            (("Describe your ideal customer",
              "Write one paragraph: who they are and what they need.", 1),
             ("Study 3 ads you like", "Note why each one works for you.", 2),
             ("Write a short offer for something real",
              "One clear message: what it is and why it helps.", 2)),
            (("Make a one-week promotion plan",
              "Pick 2-3 simple actions and when to do them.", 2),
             ("Run your plan and track one result",
              "Views, replies or sign-ups. Keep it simple.", 2),
             ("Review what worked",
              "Write a short report with one thing to keep and one to change.", 3))),
    *_skill("basic-coding", "Basic Coding", "scholar", "Write small programs that work.",
            (("Set up a beginner coding site or editor",
              "Pick any free beginner course or online editor.", 1),
             ("Write your first program", "Make it print 'Hello, world'.", 1),
             ("Finish a lesson on variables",
              "Try changing the examples to see what happens.", 2)),
            (("Learn if-statements and loops", "Do one beginner lesson and its exercises.", 1),
             ("Write a tiny program", "A tip calculator or a number guessing game.", 2),
             ("Fix a bug", "Read the error message slowly; it usually points to the line.", 2)),
            (("Plan a small project", "Describe a simple to-do list app in plain words.", 2),
             ("Build a first working version", "Small and working beats big and unfinished.", 2),
             ("Finish and share your project",
              "Show it to a friend and explain how it works.", 3))),
    # Artisan
    *_skill("sketching", "Sketching", "artisan", "See shapes and put them on paper.",
            (("Draw 5 simple shapes with shading",
              "Cubes, spheres and cylinders. Light pencil first.", 1),
             ("Sketch one object on your desk", "Look more than you draw.", 1),
             ("Sketch a small scene for 20 minutes", "Big shapes first, details last.", 2)),
            (("Practice light and shadow on a cup",
              "Use one lamp so the shadows are clear.", 1),
             ("Draw one object from 3 angles", "Notice how the shapes change.", 2),
             ("Fill a page with quick gesture sketches",
              "Two minutes each. Capture the pose, not the details.", 2)),
            (("Sketch a room in simple perspective",
              "Watch a short guide on one-point perspective first.", 2),
             ("Copy a drawing you admire to learn", "Study how the artist built it up.", 2),
             ("Finish a detailed sketch you are proud of",
              "Take as many sittings as you need.", 3))),
    *_skill("photography", "Photography", "artisan", "Frame, light and tell stories in photos.",
            (("Learn your camera's focus and exposure",
              "Tap to focus, then slide to brighten or darken.", 1),
             ("Take 10 photos using the rule of thirds",
              "Turn on the grid and place your subject on a line.", 1),
             ("Shoot a mini-series of 5 photos", "Pick one theme, like doors or shadows.", 2)),
            (("Shoot in morning or evening light",
              "Soft, low light is kind to most subjects.", 1),
             ("Edit 3 photos with a free app", "Crop, straighten and adjust light gently.", 2),
             ("Take a portrait of a friend",
              "Ask first, and only share it if they say it is okay.", 2)),
            (("Plan a themed photo walk", "Pick a theme and a safe, familiar route.", 2),
             ("Pick and arrange your best 10 photos", "Order them so they tell a story.", 2),
             ("Share a small photo story", "Show it to someone and tell them about it.", 3))),
    # Ranger
    *_skill("trail-walking", "Trail Walking", "ranger", "Enjoy the outdoors safely on foot.",
            (("Pack a small day kit", "Water, a snack, sun protection and a charged phone.", 1),
             ("Walk a local park path for 30 minutes", "Keep a pace that feels comfortable.", 1),
             ("Walk a short marked beginner trail",
              "Tell someone where you are going and when you will be back.", 2)),
            (("Learn to read a trail map", "Check the route and distance before you go.", 1),
             ("Walk a slightly longer marked trail",
              "Turn back early if the weather changes.", 2),
             ("Practice leave-no-trace", "Pack out all trash and stay on the path.", 2)),
            (("Plan a half-day route with rest stops",
              "Share the plan with someone you trust.", 2),
             ("Walk with a friend or group", "Trails are more fun, and safer, together.", 2),
             ("Complete a longer marked trail",
              "Go at your own pace and bring plenty of water.", 3))),
    *_skill("plant-care", "Plant Care", "ranger", "Keep green things happy and growing.",
            (("Pick an easy plant", "Pothos or a snake plant are forgiving starters.", 1),
             ("Learn its light and water needs", "Look it up and pick a good spot.", 1),
             ("Keep a watering log for a week", "Check the soil before each watering.", 2)),
            (("Repot a plant", "Use a pot one size bigger with a drainage hole.", 1),
             ("Grow a plant from a cutting", "Pothos roots well in a glass of water.", 2),
             ("Start a small herb pot", "Basil or mint on a sunny windowsill.", 2)),
            (("Plan a small plant corner", "Sketch where each plant goes and its light.", 2),
             ("Care for 3 plants for two weeks", "Keep your watering log going.", 2),
             ("Harvest or share something you grew",
              "Herbs for a meal or a cutting for a friend.", 3))),
    # Steward
    *_skill("budgeting", "Budgeting", "steward", "Know where your money goes.",
            (("List your monthly income and fixed bills",
              "Rent, utilities, phone. Add them to the Bills tab too.", 1),
             ("Track every expense for 3 days",
              "Small things count. No judging, just notes.", 1),
             ("Make a simple monthly budget", "Needs, wants and savings. Keep it rough.", 2)),
            (("Sort last week's spending into categories",
              "Food, transport, fun. See where most of it went.", 1),
             ("Set one small saving goal", "Pick an amount and a date that feel doable.", 2),
             ("Stick to a weekly spending limit", "Check in halfway through the week.", 2)),
            (("Make a small emergency fund plan",
              "Pick a starting target and a little to set aside each payday.", 2),
             ("Review a full month of spending", "Note one thing you are happy with.", 2),
             ("Plan next month's budget", "Use what you learned this month.", 3))),
    *_skill("home-organizing", "Home Organizing", "steward",
            "A calm, tidy space that stays tidy.",
            (("Declutter one drawer", "Keep, donate or toss. Five focused minutes.", 1),
             ("Give everything on one shelf a home", "Group similar things together.", 1),
             ("Set up a 10-minute daily reset",
              "Put things back where they live before bed.", 2)),
            (("Declutter a closet", "Keep, donate or toss, one section at a time.", 1),
             ("Label your storage boxes", "Simple labels make tidying faster.", 2),
             ("Do the daily reset 5 days in a row", "A short timer helps.", 2)),
            (("Plan a room makeover on paper", "List what stays, what goes and where.", 2),
             ("Organize a whole room", "Work in small zones and take breaks.", 2),
             ("Keep it tidy for two weeks", "Do a quick weekly check.", 3))),
    # Monk
    *_skill("calm-breathing", "Calm Breathing", "monk",
            "Slow, easy breathing you can use anywhere.",
            (("Try three slow breaths",
              "In through the nose, out a little longer. Stop if you feel dizzy.", 1),
             ("Breathe slowly for 3 minutes", "Sit comfortably. A timer helps.", 1),
             ("Use slow breathing on a busy day",
              "Pause once when things feel rushed and take a few calm breaths.", 2)),
            (("Learn box breathing",
              "In 4, hold 4, out 4, hold 4. Shorten the counts if it feels hard.", 1),
             ("Breathe slowly 5 minutes a day for 3 days", "Same time each day helps.", 2),
             ("Pair a breath break with a daily habit",
              "For example, three breaths before every meal.", 2)),
            (("Sit quietly for 10 minutes",
              "Notice your breath; when your mind wanders, gently come back.", 2),
             ("Keep a breath break going for a week", "Missed days are fine; just resume.", 2),
             ("Teach slow breathing to someone",
              "Explaining it helps you remember it.", 3))),
    *_skill("self-care-routine", "Self-Care Routine", "monk",
            "Small daily care that feels good, not like a chore.",
            (("List the care steps you already do",
              "Brushing, washing your face, a shower. Everything counts.", 1),
             ("Pick a simple morning routine", "Two or three steps you can do on autopilot.", 1),
             ("Follow your routine for 3 days", "Keep it easy. Done beats perfect.", 2)),
            (("Add a calm evening routine",
              "Shower, comfy clothes, screens a little dimmer.", 1),
             ("Set up your care corner", "Keep what you use together and within reach.", 2),
             ("Do both routines for 5 days", "Skip a step on tired days; that is okay.", 2)),
            (("Plan a weekly reset",
              "Fresh sheets, nails, a longer shower: pick what feels good.", 2),
             ("Do your weekly reset", "Put on music and take your time.", 2),
             ("Keep your routines going for two weeks",
              "Adjust anything that feels like a chore.", 3))),
]
# Extra content (free-resource quests and chains) lives in catalog_extra; keep the hand-written
# base lists for comparisons, then merge.
from lol.core.catalog_extra import EXTRA_QUEST_BOARD, EXTRA_SIDE_QUESTS

BASE_QUEST_BOARD: tuple[CatalogQuest, ...] = tuple(QUEST_BOARD)
BASE_SIDE_QUESTS: tuple[CatalogChain, ...] = tuple(SIDE_QUESTS)
QUEST_BOARD.extend(EXTRA_QUEST_BOARD)
SIDE_QUESTS.extend(EXTRA_SIDE_QUESTS)
SIDE_QUEST_BY_ID: dict[str, CatalogChain] = {c.id: c for c in SIDE_QUESTS}

# Follow-ups for custom skills (no catalog chain): generic steps, "{skill}" is filled in.
GENERIC_FOLLOWUPS: dict[int, tuple[_S, _S, _S]] = {
    2: (("Practice {skill} for 20 minutes", "Focus on one thing you want to improve.", 1),
        ("Try a slightly harder {skill} task", "Stretch a little, but stay comfortable.", 2),
        ("Show or explain your {skill} to someone", "Teaching is a great way to learn.", 2)),
    3: (("Set a small {skill} goal for this week", "Make it clear and doable.", 2),
        ("Practice {skill} three times this week", "Short sessions count.", 2),
        ("Finish one complete {skill} project", "Something you can show or use.", 3)),
}
CUSTOM_FOLLOWUP_PREFIX = "custom-r"  # generated ids: "custom-r2:<skill name>"


def custom_followup_id(skill_name: str, rank: int) -> str:
    return f"{CUSTOM_FOLLOWUP_PREFIX}{rank}:{skill_name}"


def generic_followup(skill_name: str, path_id: str, rank: int) -> CatalogChain:
    """The rank-2/3 follow-up chain for a skill with no catalog follow-up (a custom skill)."""
    steps = tuple(CatalogStep(t.format(skill=skill_name), n, d)
                  for t, n, d in GENERIC_FOLLOWUPS[rank])
    return CatalogChain(custom_followup_id(skill_name, rank), skill_name, path_id, rank, steps,
                        f"Rank up your {skill_name}.")


# --- Quest templates (starter library) ----------------------------------------------------------
# (id, title, note, path, difficulty, kind, minutes). Rewards come from game.XP_BY_DIFFICULTY /
# COINS_BY_DIFFICULTY when the template is used. Wording is everyday and non-medical.
_T = tuple[str, str, str, str, int, str, int]
_TEMPLATE_ROWS: tuple[_T, ...] = (
    # self-care (Monk since v1.3; quests made from them earlier keep their Path)
    ("t-skin-care", "Skin care routine", "Cleanse, then your usual products. Gentle is fine.",
     "monk", 1, "daily", 5),
    ("t-oral-care", "Oral care", "Brush for two minutes and floss.", "monk", 1, "daily", 5),
    ("t-facial", "Face mask routine", "A relaxing face mask or skincare session at home with products you already like.",
     "monk", 1, "once", 20),
    ("t-stretch", "Stretching", "Gentle stretches only. Stop if anything hurts.",
     "monk", 1, "daily", 10),
    ("t-water", "Water check", "Refill your water bottle and take a few sips.",
     "monk", 1, "daily", 1),
    ("t-shower-reset", "Evening wind-down", "Shower, comfy clothes, screens a little dimmer.",
     "monk", 1, "daily", 20),
    # warrior
    ("t-gym", "Gym session", "Warm up first and go at a pace that feels right today.",
     "warrior", 2, "once", 60),
    ("t-walk", "Take a walk", "Any pace, inside or outside.", "warrior", 1, "daily", 15),
    # chef
    ("t-meal-prep", "Meal prep", "Cook a few portions ahead and store them in the fridge.",
     "chef", 2, "once", 90),
    ("t-cook-home", "Cook a meal at home", "Something simple you enjoy.", "chef", 1, "once", 30),
    # scholar
    ("t-read-20", "Read 20 pages", "Any book. Note one idea you liked.", "scholar", 1, "daily", 25),
    ("t-study", "Study session", "One topic, phone away, short break after.",
     "scholar", 2, "once", 45),
    # artisan
    ("t-journal", "Journal", "A few lines about today. No rules.", "artisan", 1, "daily", 10),
    ("t-create", "Make something", "Draw, write, build or play for a little while.",
     "artisan", 1, "once", 20),
    # ranger
    ("t-fresh-air", "Get some fresh air", "Step outside for a few minutes.", "ranger", 1,
     "daily", 5),
    ("t-plants", "Water the plants", "Check the soil first; not every plant needs water daily.",
     "ranger", 1, "once", 5),
    # steward
    ("t-weekly-plan", "Weekly planning", "Look at the week ahead: bills, plans, a few goals.",
     "steward", 2, "once", 30),
    ("t-tidy-desk", "Tidy desk", "Clear the surface and put things back where they live.",
     "steward", 1, "once", 10),
    ("t-laundry", "Laundry", "Wash, dry, fold. Putting it away counts too.",
     "steward", 1, "once", 45),
    ("t-bills-check", "Check upcoming bills", "Glance at what is due this week.",
     "steward", 1, "once", 5),
)


def builtin_templates() -> list[QuestTemplate]:
    """Fresh copies of the starter templates (rewards filled in by the game)."""
    from lol.core.game import COINS_BY_DIFFICULTY, XP_BY_DIFFICULTY  # lazy: game imports catalog

    return [QuestTemplate(tid, title, note, path, diff, kind, minutes,
                          COINS_BY_DIFFICULTY[diff], XP_BY_DIFFICULTY[diff], builtin=True)
            for tid, title, note, path, diff, kind, minutes in _TEMPLATE_ROWS]


TEMPLATE_IDS: tuple[str, ...] = tuple(r[0] for r in _TEMPLATE_ROWS)

# --- Learning-chain generator ("generate a chain" for any skill name, no AI) ---------------------
# Shapes by step count; each step is (title, note, difficulty) with "{skill}" and "{where}".
LEARNING_STEPS: dict[str, _S] = {
    "basics": ("Learn the basics of {skill}",
               "Find one beginner guide or video and note 3 key ideas.", 1),
    "guided": ("Guided practice: {skill}",
               "Follow a beginner tutorial step by step. Go slow.", 1),
    "solo": ("Practice {skill} on your own",
             "Repeat what you learned without the guide. Mistakes are fine.", 2),
    "apply": ("Use {skill} in real life",
              "Try it for real {where}. Keep it small and simple.", 2),
    "reflect": ("Reflect on your {skill}",
                "Write 2-3 lines: what went well, what to try next.", 1),
}
LEARNING_SHAPES: dict[int, tuple[str, ...]] = {
    3: ("basics", "guided", "apply"),
    4: ("basics", "guided", "apply", "reflect"),
    5: ("basics", "guided", "solo", "apply", "reflect"),
}
LEARNING_WHERE: dict[str, str] = {  # Path flavor for the "apply" step
    "chef": "in your kitchen",
    "warrior": "in a short session at your own pace",
    "scholar": "on something you are studying or reading",
    "artisan": "in a small piece you make",
    "ranger": "outdoors or with your plants",
    "steward": "with your own home or budget",
    "monk": "as part of a calm daily routine",
}
SELF_CARE_TEMPLATE_IDS: tuple[str, ...] = (  # moved from Warrior to Monk in v1.3
    "t-skin-care", "t-oral-care", "t-facial", "t-stretch", "t-water", "t-shower-reset")


def learning_chain(skill_name: str, path_id: str, steps: int = 4) -> list[CatalogStep]:
    """Deterministic learn -> practice -> apply -> reflect chain for any skill name."""
    shape = LEARNING_SHAPES[min(max(steps, min(LEARNING_SHAPES)), max(LEARNING_SHAPES))]
    where = LEARNING_WHERE.get(path_id, "in your day")
    out = []
    for key in shape:
        title, note, diff = LEARNING_STEPS[key]
        out.append(CatalogStep(title.format(skill=skill_name),
                               note.format(skill=skill_name, where=where), diff))
    return out
