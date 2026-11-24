"""From your own meals — the behavior side of Future Me (the digital twin).

Future Me already knows a student's focus area (from ASA24) and their
setup (the onboarding profile). This module adds what they actually eat:
it reads the student's own lightweight meal logs and notices the foods
that keep coming back ("whole-milk yogurt, most mornings"), so a
suggestion can be anchored to a meal they already have rather than to a
generic tip.

Design rules, in line with the rest of the app:
  * Deterministic. A curated lexicon of foods matched against the free-text
    meal names and items the student logged — no LLM in the loop, no
    network, works without a TAMU key, and every match is explainable
    ("you logged X on these days").
  * Counts only. A "habit" is a food logged at least HABIT_MIN_TIMES times
    in the last HABIT_WINDOW_DAYS days. No amounts, no nutrients, no score.
  * Honest about sparse data. Lightweight logging is optional and uneven,
    so an unlogged meal is never read as a skipped one, and nothing is
    claimed until the student has logged on LEARNING_MIN_DAYS days.
  * Reviewable. The lexicon is plain data the nutrition team can read and
    edit; adding a food is adding a row.

Pure functions only (no database), so the rules are unit-testable.
"""
import re
from collections import defaultdict
from datetime import date, timedelta
from typing import Dict, List, Optional

from study_time import study_day_key

HABIT_WINDOW_DAYS = 21     # three weeks of logs
HABIT_MIN_TIMES = 3        # a food becomes a "regular" at three logged meals
LEARNING_MIN_DAYS = 3      # days with any log before Future Me says anything
MEAL_SLOTS = ("breakfast", "lunch", "dinner", "snack")

# Each entry: id, label (how Future Me names it), match (words/phrases;
# plural s/es allowed), exclude (phrases that cancel a match — "veggie
# burger" is not a burger habit, "whole wheat pasta" is not refined pasta),
# and optionally `all` (groups of phrases that must each appear somewhere
# in the meal text; an alternative to `match` for foods people describe in
# any order) and `parent` (a broader entry this one refines — "whole-milk
# yogurt" is also "yogurt"; the broader habit is dropped from the list
# when the specific one explains every one of its meals).
# Order doesn't matter: every matching entry counts, and the swap table
# decides which ones have a swap for a given focus area.
FOOD_LEXICON: List[Dict] = [
    # ---- dairy ----
    {"id": "whole_milk_yogurt", "label": "whole-milk yogurt", "parent": "yogurt",
     # `all`: every group must be present somewhere in the meal text, so
     # "Chobani whole-milk vanilla Greek yogurt" counts too.
     "match": ["whole milk yogurt", "whole-milk yogurt", "full fat yogurt", "full-fat yogurt"],
     "all": [["whole milk", "whole-milk", "full fat", "full-fat"], ["yogurt", "yoghurt"]]},
    {"id": "sweetened_yogurt", "label": "flavored yogurt", "parent": "yogurt",
     "match": ["vanilla yogurt", "strawberry yogurt", "flavored yogurt", "fruit on the bottom", "yoplait",
               "gogurt", "go-gurt", "honey yogurt", "key lime yogurt", "peach yogurt"],
     "exclude": ["plain"]},
    {"id": "yogurt", "label": "yogurt", "match": ["yogurt", "yoghurt", "greek yogurt", "parfait"],
     "exclude": ["frozen yogurt", "froyo"]},
    {"id": "whole_milk", "label": "whole milk", "parent": "milk", "match": ["whole milk", "vitamin d milk"],
     "exclude": ["yogurt", "yoghurt"]},
    {"id": "milk", "label": "milk", "match": ["milk", "latte", "cappuccino", "chocolate milk"],
     "exclude": ["almond milk", "oat milk", "soy milk", "coconut milk", "milkshake", "yogurt", "yoghurt"]},
    {"id": "cheese_heavy", "label": "cheese sauces",
     "match": ["queso", "cheese sauce", "alfredo", "extra cheese", "nacho cheese", "cheese dip", "cheese fries",
               "loaded"]},
    {"id": "ice_cream", "label": "ice cream", "match": ["ice cream", "milkshake", "frozen yogurt", "froyo", "gelato"]},

    # ---- grains ----
    {"id": "white_rice", "label": "white rice",
     "match": ["white rice", "jasmine rice", "basmati rice", "fried rice", "garlic rice", "steamed rice",
               "sticky rice", "rice bowl", "rice"],
     "exclude": ["brown rice", "wild rice", "cauliflower rice", "rice cake", "rice krispies", "rice crispies"]},
    {"id": "white_bread", "label": "white bread, rolls or sandwiches",
     "match": ["white bread", "white toast", "toast", "dinner roll", "hamburger bun", "white bun", "biscuit",
               "croissant", "bagel", "flour tortilla", "garlic bread", "breadstick", "naan", "pita", "sandwich",
               "sub", "hoagie", "wrap"],
     "exclude": ["wheat", "whole grain", "whole-grain", "multigrain", "lettuce wrap", "rye"]},
    {"id": "pasta", "label": "regular pasta",
     "match": ["pasta", "spaghetti", "penne", "fettuccine", "linguine", "mac and cheese", "mac n cheese",
               "macaroni", "lasagna", "ravioli", "lo mein", "noodles", "ziti"],
     "exclude": ["whole wheat pasta", "whole-wheat pasta", "whole grain pasta", "chickpea pasta",
                 "lentil pasta", "zucchini noodles", "zoodles", "ramen", "instant noodles", "cup noodles"]},
    {"id": "instant_noodles", "label": "ramen or noodle cups",
     "match": ["ramen", "instant noodles", "cup noodles", "cup of noodles", "maruchan", "top ramen", "shin ramyun",
               "ramyun"]},
    {"id": "cereal", "label": "cereal",
     "match": ["cereal", "frosted flakes", "lucky charms", "froot loops", "fruit loops", "cinnamon toast crunch",
               "cocoa puffs", "honey nut cheerios", "cheerios", "frosted mini wheats", "cap'n crunch", "captain crunch",
               "raisin bran", "chex", "rice krispies"]},
    {"id": "oatmeal", "label": "oatmeal", "match": ["oatmeal", "oats", "overnight oats", "porridge", "steel cut"]},
    {"id": "whole_grains", "label": "whole grains",
     "match": ["whole wheat", "whole-wheat", "whole grain", "whole-grain", "wholegrain", "multigrain", "brown rice",
               "wild rice", "quinoa", "farro", "barley", "bulgur", "popcorn"],
     "exclude": ["popcorn chicken", "popcorn shrimp"]},

    # ---- drinks and sweets ----
    {"id": "soda", "label": "soda",
     "match": ["soda", "coke", "coca cola", "coca-cola", "pepsi", "dr pepper", "dr. pepper", "sprite", "mountain dew",
               "root beer", "fanta", "big red", "ginger ale", "sweet tea"],
     "exclude": ["diet coke", "diet pepsi", "diet dr pepper", "coke zero", "zero sugar", "diet soda", "unsweet tea",
                 "unsweetened tea"]},
    {"id": "energy_drink", "label": "energy drinks",
     "match": ["energy drink", "red bull", "redbull", "monster energy", "celsius", "alani", "bang energy", "rockstar",
               "prime energy", "reign", "ghost energy", "c4"]},
    {"id": "sweet_coffee", "label": "sweet coffee drinks",
     "match": ["frappuccino", "frappe", "mocha", "caramel latte", "vanilla latte", "pumpkin spice", "sweet cream",
               "caramel macchiato", "frozen coffee", "white chocolate", "dunkin refresher", "refresher"]},
    {"id": "juice", "label": "juice", "match": ["juice", "orange juice", "apple juice", "cranberry juice", "lemonade"],
     "exclude": ["juice box"]},
    {"id": "candy_dessert", "label": "sweets",
     "match": ["candy", "cookie", "brownie", "cupcake", "donut", "doughnut", "pastry", "cinnamon roll", "churro",
               "apple pie", "pecan pie", "pumpkin pie", "cheesecake", "chocolate cake", "birthday cake", "coffee cake",
               "pound cake", "cake pop", "chocolate bar", "snickers", "m&m", "skittles", "sour patch", "gummies",
               "pop tart", "poptart", "blueberry muffin", "chocolate muffin", "ice cream sandwich"],
     "exclude": ["rice cake", "pancake", "english muffin", "crab cake", "pot pie"]},

    # ---- salty, fried, and processed ----
    {"id": "fries", "label": "fries or tots",
     "match": ["fries", "french fries", "curly fries", "waffle fries", "tater tots", "tots", "hash brown", "hashbrown"]},
    {"id": "chips", "label": "chips",
     "match": ["chips", "doritos", "cheetos", "takis", "pringles", "lays", "fritos", "hot cheetos", "potato chips",
               "tortilla chips"],
     "exclude": ["chocolate chip", "fish and chips"]},
    {"id": "fried_chicken", "label": "fried chicken",
     "match": ["fried chicken", "chicken tenders", "chicken nuggets", "nuggets", "crispy chicken", "popcorn chicken",
               "chick-fil-a", "chick fil a", "canes", "cane's", "raising cane", "wings", "chicken strips",
               "tempura chicken", "hot honey chicken"]},
    {"id": "burger", "label": "burgers",
     "match": ["burger", "cheeseburger", "hamburger", "whataburger", "big mac", "quarter pounder", "double double",
               "smash burger"],
     "exclude": ["veggie burger", "turkey burger", "black bean burger", "beyond burger", "impossible burger",
                 "salmon burger"]},
    {"id": "pizza", "label": "pizza", "match": ["pizza", "pizza rolls", "calzone"]},
    {"id": "bacon_sausage", "label": "bacon or sausage",
     "match": ["bacon", "sausage", "pork sausage", "chorizo", "breakfast sausage", "sausage biscuit",
               "sausage egg", "bacon egg"],
     "exclude": ["chicken sausage", "turkey sausage", "turkey bacon", "beyond", "veggie sausage", "plant-based"]},
    {"id": "processed_meat", "label": "hot dogs or pepperoni",
     "match": ["hot dog", "hotdog", "corn dog", "pepperoni", "salami", "bologna", "spam", "deli ham", "jerky"]},

    # ---- foods Future Me likes to see ----
    {"id": "fruit", "label": "fruit",
     "match": ["fruit", "banana", "apple", "orange", "berries", "berry", "strawberries", "strawberry", "blueberries",
               "blueberry", "raspberries", "blackberries", "grapes", "melon", "watermelon", "cantaloupe", "honeydew",
               "mango", "pineapple", "peach", "pear", "kiwi", "clementine", "mandarin", "plum", "cherries", "grapefruit"],
     "exclude": ["fruit loops", "froot loops", "fruit snacks", "fruit punch", "apple pie", "banana bread",
                 "banana pudding", "strawberry yogurt", "peach yogurt", "fruit on the bottom", "orange chicken",
                 "applewood"]},
    {"id": "vegetables", "label": "vegetables",
     "match": ["salad", "broccoli", "spinach", "carrot", "veggie", "veggies", "vegetable", "vegetables", "greens",
               "kale", "cucumber", "tomato", "green beans", "brussels", "cauliflower", "zucchini", "sweet potato",
               "corn", "peas", "asparagus", "squash", "cabbage", "lettuce", "romaine", "bell pepper", "mushroom",
               "mushrooms", "onion", "onions", "edamame", "collard", "bok choy", "slaw"],
     "exclude": ["egg salad", "tuna salad", "chicken salad", "potato salad", "pasta salad", "macaroni salad",
                 "corn dog", "popcorn", "cornbread", "corn chips", "onion rings"]},
    {"id": "beans", "label": "beans or lentils",
     "match": ["beans", "black beans", "pinto beans", "refried beans", "chickpea", "chickpeas", "chick peas", "garbanzo",
               "lentil", "lentils", "hummus", "edamame", "tofu", "tempeh", "falafel"],
     "exclude": ["green beans", "jelly beans", "coffee beans", "baked beans"]},
    {"id": "nuts", "label": "nuts or seeds",
     "match": ["nuts", "almond", "almonds", "peanut", "peanuts", "walnut", "walnuts", "cashew", "cashews", "pistachio",
               "pistachios", "trail mix", "peanut butter", "almond butter", "sunflower seeds", "chia", "pecans"],
     "exclude": ["donut", "doughnut", "coconut", "peanut butter cup", "almond milk"]},
    {"id": "fish", "label": "fish or seafood",
     "match": ["fish", "salmon", "tuna", "shrimp", "tilapia", "cod", "sushi", "poke", "crab", "sardines", "catfish",
               "mahi"],
     "exclude": ["fish and chips", "fried fish", "fish sticks", "swedish fish"]},
    {"id": "eggs", "label": "eggs", "match": ["egg", "eggs", "omelet", "omelette", "scrambled eggs", "egg whites"],
     "exclude": ["egg roll", "eggplant"]},
    {"id": "grilled_chicken", "label": "grilled chicken",
     "match": ["grilled chicken", "roasted chicken", "rotisserie chicken", "baked chicken", "chicken breast",
               "chicken thigh"]},

    # ---- added with the nutrition team's swap review (2026-11-16) ----
    # Triggers for the new proposals in content/swaps.json. Several overlap
    # broader entries above on purpose ("toast" is also white_bread when
    # it isn't wheat); the swap table decides which one has a swap for a
    # given focus area.
    {"id": "toast", "label": "toast", "match": ["toast", "avocado toast", "texas toast"],
     "exclude": ["french toast", "toast crunch"]},
    {"id": "snack_bar", "label": "snack bars",
     "match": ["granola bar", "protein bar", "snack bar", "cereal bar", "breakfast bar", "nature valley", "clif bar",
               "kind bar", "rxbar", "nutri-grain", "nutrigrain", "fiber one bar", "quest bar", "larabar"]},
    {"id": "fruit_cup", "label": "fruit cups",
     "match": ["fruit cup", "mandarin orange cup", "peach cup", "diced peaches", "fruit cocktail", "canned fruit",
               "canned peaches", "dole cup"]},
    {"id": "tacos", "label": "tacos", "match": ["taco", "street taco", "taco bell", "birria"],
     "exclude": ["taco salad", "taco seasoning"]},
    {"id": "quesadilla", "label": "quesadillas", "match": ["quesadilla", "crunchwrap"]},
    {"id": "fried_rice", "label": "fried rice", "match": ["fried rice"]},
    {"id": "sandwich", "label": "sandwiches",
     "match": ["sandwich", "sub", "hoagie", "panini", "wrap", "blt", "po boy", "subway", "jimmy john"],
     "exclude": ["lettuce wrap", "ice cream sandwich"]},
    {"id": "flour_tortilla", "label": "flour tortillas, burritos or wraps",
     "match": ["flour tortilla", "tortilla", "burrito", "wrap", "fajita"],
     "exclude": ["corn tortilla", "tortilla chips", "tortilla soup", "whole wheat", "whole-wheat", "lettuce wrap",
                 "burrito bowl"]},
    {"id": "rice_and_beans", "label": "rice and beans",
     "match": ["rice and beans", "beans and rice", "red beans and rice", "gallo pinto"],
     "all": [["rice"], ["beans", "black beans", "pinto beans", "red beans"]],
     "exclude": ["brown rice", "green beans", "jelly beans", "coffee beans"]},
    {"id": "crackers", "label": "crackers",
     "match": ["cracker", "cheez-it", "cheez it", "goldfish", "ritz", "saltine", "town house"],
     "exclude": ["whole grain", "whole-grain", "whole wheat", "triscuit", "wheat thins", "graham cracker"]},
    {"id": "smoothie", "label": "smoothies", "match": ["smoothie", "smoothie king", "tropical smoothie"]},
    {"id": "chicken_sandwich", "label": "chicken sandwiches or wraps",
     "match": ["chicken sandwich", "chicken wrap", "chicken sub", "chicken club", "chicken panini",
               "spicy chicken sandwich"]},
    {"id": "butter_toast", "label": "buttered toast",
     "match": ["buttered toast", "butter toast", "toast with butter", "bagel with butter"],
     "all": [["butter", "buttered"], ["toast", "bagel", "english muffin", "biscuit"]],
     "exclude": ["peanut butter", "almond butter", "nut butter", "sunflower butter", "apple butter", "cookie butter",
                 "butter chicken", "buttermilk"]},
    {"id": "creamy_dressing", "label": "creamy dressings",
     "match": ["ranch", "caesar dressing", "caesar salad", "blue cheese dressing", "thousand island", "creamy dressing",
               "creamy italian"]},
    {"id": "cheese_sandwich", "label": "cheese-heavy sandwiches",
     "match": ["grilled cheese", "cheese sandwich", "ham and cheese", "turkey and cheese", "patty melt", "tuna melt",
               "cheesesteak", "philly cheesesteak"]},
    {"id": "margarine_spread", "label": "margarine or sweet spreads",
     "match": ["margarine", "nutella", "hazelnut spread", "chocolate spread", "country crock",
               "i can't believe it's not butter"]},
    {"id": "canned_beans", "label": "canned beans",
     "match": ["canned beans", "can of beans", "canned black beans", "canned chickpeas", "canned pinto beans",
               "canned kidney beans", "bush's beans", "bushs beans"]},
    {"id": "sauced_bowl", "label": "saucy rice bowls or stir-fries",
     "match": ["teriyaki", "stir fry", "stir-fry", "soy sauce", "orange chicken", "general tso", "sesame chicken",
               "panda express", "rice bowl", "poke bowl", "hibachi"]},
    {"id": "canned_soup", "label": "canned or instant soup",
     "match": ["canned soup", "soup can", "campbell", "campbell's", "progresso", "cup of soup", "instant soup",
               "chicken noodle soup", "tomato soup"]},
    {"id": "dipping_sauce", "label": "dipping sauces",
     "match": ["dipping sauce", "cane's sauce", "canes sauce", "chick-fil-a sauce", "bbq sauce", "barbecue sauce",
               "honey mustard", "sweet and sour sauce", "buffalo sauce"]},
    {"id": "sweet_tea", "label": "sweet tea", "parent": "soda",
     "match": ["sweet tea", "sweetened tea", "sweetened iced tea", "peach tea", "arizona tea", "arizona iced tea",
               "snapple", "lipton iced tea"],
     "exclude": ["unsweet", "unsweetened"]},
    {"id": "flavored_oatmeal", "label": "flavored oatmeal packets",
     "match": ["instant oatmeal", "oatmeal packet", "flavored oatmeal", "maple brown sugar", "apple cinnamon oatmeal",
               "peaches and cream oatmeal", "quaker oatmeal"],
     "exclude": ["plain oatmeal", "steel cut"]},
    {"id": "sweet_cereal", "label": "sweetened cereal",
     "match": ["frosted flakes", "lucky charms", "froot loops", "fruit loops", "cinnamon toast crunch", "cocoa puffs",
               "honey nut cheerios", "cap'n crunch", "captain crunch", "frosted mini wheats", "apple jacks",
               "cookie crisp", "reese's puffs", "fruity pebbles", "cocoa pebbles", "golden grahams",
               "honey bunches of oats", "trix"]},
    {"id": "sports_drink", "label": "sports drinks",
     "match": ["gatorade", "powerade", "bodyarmor", "body armor", "sports drink", "prime hydration"],
     "exclude": ["zero", "gatorade zero", "powerade zero", "g zero", "lyte"]},
    {"id": "flavored_milk", "label": "flavored milk",
     "match": ["chocolate milk", "strawberry milk", "flavored milk", "vanilla milk", "nesquik", "trumoo", "tru moo"],
     "exclude": ["almond", "oat milk"]},
    {"id": "bubble_tea", "label": "bubble tea",
     "match": ["boba", "bubble tea", "milk tea", "thai tea", "taro tea", "kung fu tea", "sharetea", "tapioca tea"]},
    {"id": "fruit_drink", "label": "sweetened fruit drinks",
     "match": ["lemonade", "fruit punch", "juice cocktail", "cranberry juice cocktail", "capri sun", "kool aid",
               "kool-aid", "sunny d", "sunny delight", "hi-c", "fruit drink", "juice drink", "agua fresca", "tampico"]},
]
LEXICON_BY_ID: Dict[str, Dict] = {e["id"]: e for e in FOOD_LEXICON}


def _phrase_re(phrase: str) -> "re.Pattern":
    # Whole words/phrases only ("pepper" never matches "pepperoni"), with
    # an optional plural; any whitespace or hyphen inside a phrase matches
    # either.
    inner = r"[\s-]+".join(re.escape(part) for part in re.split(r"[\s-]+", phrase.strip()) if part)
    return re.compile(rf"(?<![a-z0-9]){inner}(?:s|es)?(?![a-z0-9])", re.IGNORECASE)


_COMPILED = [
    (e["id"], [_phrase_re(p) for p in e["match"]], [_phrase_re(p) for p in e.get("exclude", [])],
     [[_phrase_re(p) for p in group] for group in e.get("all", [])])
    for e in FOOD_LEXICON
]


def meal_text(meal: dict) -> str:
    """Everything the student wrote about a meal, lowercased: the name plus
    any item list (photo logging and dining-hall plates fill `items`)."""
    parts = [str(meal.get("name") or "")]
    parts.extend(str(i) for i in (meal.get("items") or []) if i)
    return " ; ".join(parts).lower()


def foods_in(text: str) -> List[str]:
    """Lexicon ids found in a meal description, in lexicon order."""
    text = (text or "").lower()
    found = []
    for fid, matchers, excluders, all_groups in _COMPILED:
        hit = any(m.search(text) for m in matchers)
        if not hit and all_groups:
            hit = all(any(m.search(text) for m in group) for group in all_groups)
        if hit and not any(x.search(text) for x in excluders):
            found.append(fid)
    return found


def detect_habits(meals: List[dict], today: date, window_days: int = HABIT_WINDOW_DAYS,
                  min_times: int = HABIT_MIN_TIMES) -> dict:
    """The student's regulars over the trailing window.

    Returns {"window_days", "days_logged", "meals_considered", "status",
    "habits": [{"food_id", "label", "times", "days", "slots": {slot: n},
    "top_slot", "last_day"}, ...]} with habits sorted most-logged first.
    `status` is "learning" until the student has logged on LEARNING_MIN_DAYS
    distinct days, otherwise "ready" (even when no food has reached
    min_times yet — "no regulars yet" is a real answer)."""
    start = (today - timedelta(days=window_days - 1)).isoformat()
    end = today.isoformat()
    days_logged = set()
    considered = 0
    times: Dict[str, int] = defaultdict(int)
    days: Dict[str, set] = defaultdict(set)
    slots: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    last_day: Dict[str, str] = {}

    for m in meals:
        iso = m.get("created_at") or ""
        try:
            day = study_day_key(iso) if isinstance(iso, str) and iso else ""
        except (ValueError, TypeError):
            day = ""  # a malformed timestamp is skipped, never a crash
        if not day:
            continue
        if not (start <= day <= end):
            continue
        days_logged.add(day)
        if m.get("skipped"):
            continue  # a skipped meal says nothing about what they eat
        considered += 1
        slot = m.get("meal_type") if m.get("meal_type") in MEAL_SLOTS else "snack"
        for fid in foods_in(meal_text(m)):
            times[fid] += 1
            days[fid].add(day)
            slots[fid][slot] += 1
            if day > last_day.get(fid, ""):
                last_day[fid] = day

    habits = []
    for fid, n in times.items():
        if n < min_times:
            continue
        by_slot = dict(slots[fid])
        top_slot = max(by_slot, key=lambda s: (by_slot[s], MEAL_SLOTS.index(s) * -1))
        habits.append({
            "food_id": fid,
            "label": LEXICON_BY_ID[fid]["label"],
            "times": n,
            "days": len(days[fid]),
            "slots": by_slot,
            "top_slot": top_slot,
            "last_day": last_day[fid],
        })
    # A broad entry whose meals are all explained by a more specific one
    # ("yogurt" when every yogurt was whole-milk yogurt) just repeats it.
    by_id = {h["food_id"]: h for h in habits}
    for h in list(habits):
        parent = LEXICON_BY_ID[h["food_id"]].get("parent")
        if parent in by_id and by_id[parent]["times"] <= h["times"] and by_id[parent] in habits:
            habits.remove(by_id[parent])
    habits.sort(key=lambda h: (-h["times"], -h["days"], h["food_id"]))
    return {
        "window_days": window_days,
        "days_logged": len(days_logged),
        "meals_considered": considered,
        "status": "learning" if len(days_logged) < LEARNING_MIN_DAYS else "ready",
        "habits": habits,
    }


def evidence_line(habit: dict, window_days: int = HABIT_WINDOW_DAYS) -> str:
    """Plain-language evidence Future Me shows next to a suggestion, so the
    student can see why it came up and correct it if it's wrong. Counts of
    logged meals only — never an amount."""
    weeks = max(1, round(window_days / 7))
    span = f"the last {weeks} weeks" if weeks > 1 else "the last week"
    times = habit["times"]
    meals = "meal" if times == 1 else "meals"
    slot = habit.get("top_slot")
    mostly = ""
    if slot and habit.get("slots", {}).get(slot, 0) >= max(2, (times * 2 + 2) // 3):  # two thirds or more
        mostly = f", mostly at {slot}" if slot != "snack" else ", mostly as a snack"
    return f"You've logged {habit['label']} in {times} {meals} over {span}{mostly}."


def learning_line(days_logged: int) -> str:
    if days_logged <= 0:
        return "Log a few meals and I'll start noticing your regulars."
    left = max(0, LEARNING_MIN_DAYS - days_logged)
    day = "day" if left == 1 else "days"
    return f"Log on {left} more {day} and I'll start noticing your regulars."


def coach_lines(detected: dict, limit: int = 4) -> Optional[str]:
    """One line for the Coach's THEIR CONTEXT block, or None while learning."""
    if detected["status"] != "ready":
        return None
    if not detected["habits"]:
        return "Their regular foods (from their own meal logs): nothing has come up three times yet"
    parts = []
    for h in detected["habits"][:limit]:
        slot = h["top_slot"]
        where = f"mostly {slot}" if h["slots"].get(slot, 0) >= 2 else "no usual time"
        parts.append(f"{h['label']} ({h['times']} meals, {where})")
    return "Their regular foods (from their own meal logs, last three weeks): " + "; ".join(parts)
