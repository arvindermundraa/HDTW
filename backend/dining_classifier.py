"""
Dining item classifier - local rules/keyword engine with optional LLM
upgrade via the TAMU Chat API.

This is a heuristic recommendation-surfacing tool, not a dietary
assessment instrument. It has no connection to a participant's HEI-2020
score: HEI-2020 scoring happens outside this app entirely, from ASA24
dietary recalls processed by the nutrition team's own pipeline. What this
module does is tag real dining-hall menu items with a handful of coarse,
keyword-derived signals (fiber source, lean protein, whole grain, high
sodium, and — since the 9 lightweight-logging categories were added — a
best-guess mapping to those same category labels) so the plate-suggestion
and chat meal-builder surfaces can make reasonable, non-ranked
recommendations. Running 100+ items x 6 hall/period combos through an
external API on every render also isn't fast or affordable, so the
keyword path is the default and the LLM path (see llm_classify_menu) is an
optional upgrade for the long tail of menu names keyword lists miss.

HONESTY ABOUT ACCURACY: the keyword path is a heuristic, not a nutrient
database lookup. Every classification carries a confidence level;
low-confidence items should be treated conservatively by callers rather
than guessed at. The log_categories mapping is provisional and intended
for personalization/recommendation grouping only — never presented to a
participant as a diet-quality score.
"""
import json
import logging
import re
from typing import List, Optional

logger = logging.getLogger("llhs.classifier")

_VEGETABLE_WORDS = [
    "salad", "broccoli", "spinach", "kale", "carrot", "pepper", "zucchini",
    "cucumber", "tomato", "tomatoes", "greens", "vegetable", "asparagus",
    "brussels", "cauliflower", "squash", "green bean", "mixed veg",
    "roasted veg", "steamed veg", "coleslaw", "slaw",
    # Added from live 142-item Commons lunch pull (2026-08-28):
    "onion", "mushroom", "beet", "celery", "jalapeno", "jalapeño",
    "bell pepper", "corn salad", "corn", "pico", "guacamole", "avocado",
    "lettuce", "arugula", "cabbage", "bok choy", "eggplant", "artichoke",
    "radish", "leek", "turnip", "parsnip",
    # Added from the 2026-09 live pulls (all six hall/period menus):
    "spring mix", "romaine", "pea", "snow pea", "sweet potato", "aloo gobi",
]
# NOTE: deliberately excludes the bare word "veggie" — caught via execution
# testing that it false-positives on "Veggie Burger" (a protein patty, not
# a vegetable side). "vegetable" (the fuller word) is kept since it still
# correctly matches "mixed vegetable," "steamed vegetable," etc.
# NOTE: "corn" is included but "popcorn" and "corn dog" are higher-fat/sodium
# items — both are caught by _HIGH_SODIUM_INDICATORS/"fried" before the
# vegetable tag matters to the plate composer.

# "Salad" is a mayo-based protein dish as often as it's a leafy vegetable
# dish ("Tuna Salad," "Egg Salad Sandwich," "Chicken Salad") - caught via
# an expanded execution test after the initial battery passed, exactly the
# kind of long-tail gap a small test set won't surface. These specific
# compounds are excluded from the vegetable match; "Caesar Salad," "Side
# Salad," "Garden Salad," bare "Salad," etc. still match correctly, since
# those are genuinely lettuce-based.
_SALAD_PROTEIN_EXCEPTIONS = [
    "tuna salad", "egg salad", "chicken salad", "ham salad", "pasta salad",
    "macaroni salad", "shrimp salad", "crab salad", "lobster salad",
]

_WHOLE_GRAIN_WORDS = [
    "brown rice", "whole wheat", "whole grain", "quinoa", "farro",
    "oat", "barley", "multigrain", "wild rice",
    "oatmeal", "brown basmati",
]
_REFINED_GRAIN_WORDS = [
    "white rice", "white bread", "biscuit", "pancake", "waffle", "bagel",
    "roll", "bun", "pasta", "noodle", "tortilla",
    # Starchy sides / bread-based entrees seen on live menus. Generic "rice"
    # is refined unless a whole-grain word also matches (checked below).
    "rice", "potato", "potatoe", "tater tot", "hash brown", "fries", "penne",
    "ziti", "bread", "toast", "croissant", "sandwich", "burger", "pizza",
    "garlic knot", "flatbread", "pita", "mac and cheese", "mac & cheese",
]
_LEAN_PROTEIN_WORDS = [
    "grilled chicken", "grilled fish", "salmon", "tilapia", "turkey",
    "tofu", "bean", "lentil", "egg white", "chickpea", "chick pea",
    "black bean", "edamame", "shrimp", "grilled", "baked chicken",
    "rotisserie",
    # Added from live pull: protein items that had zero tags before
    "chicken breast", "chicken tenders", "deli turkey", "deli chicken",
    "tuna", "cod", "halibut", "mahi", "catfish", "scallop",
    "tempeh", "seitan", "kidney bean", "pinto bean", "navy bean",
    "white bean", "cannellini", "hummus",
    # Plain "chicken" (roasted/marinated/tikka/thigh) — fried forms are
    # excluded from the lean tag in classify_item.
    "chicken",
    # NOTE: "crab" and "shrimp" stay — they ARE lean proteins when not fried.
    # NOTE: "tuna salad" is in _SALAD_PROTEIN_EXCEPTIONS so the salad form
    # is excluded from has_lean_protein via the exception check in classify_item.
]
# Protein foods that are neither "lean" nor salty/processed by default —
# they map to other_protein only.
_OTHER_PROTEIN_WORDS = [
    "egg", "omelet", "pork", "pulled pork", "steak", "meatball", "meatloaf",
    "brisket", "burger", "ham", "beef",
]
_HIGHER_FAT_PROTEIN_WORDS = [
    "bacon", "sausage", "fried chicken", "fried fish", "chicken tender",
    "hot dog", "ribs", "pepperoni", "salami",
    # Added from live pull
    "beef", "pork belly", "carnitas", "chorizo", "bratwurst", "bologna",
]
_HIGH_SODIUM_INDICATORS = [
    "fried", "gravy", "cheese sauce", "queso", "bacon", "sausage",
    "cured", "smoked", "brine", "pickled", "soy sauce", "teriyaki",
    "buffalo", "bbq", "cheese", "alfredo", "salted", "chips", "fries",
    "processed", "pepperoni", "salami", "chorizo", "bratwurst", "bologna",
    "barbeque", "barbecue", "ham",
]
_HIGH_FIBER_HINTS = [
    "beans", "lentil", "chickpea", "chick pea", "whole", "bran", "oat",
    "quinoa", "berries", "fruit", "vegetable", "broccoli", "avocado",
    # Added from live pull
    "sweet potato", "black bean", "kidney bean", "pinto bean", "edamame",
]
_FRIED_WORDS = ["fried", "crispy", "battered", "breaded", "tempura"]

# Added to support the 9-category lightweight-logging taxonomy
# (LLHS App Review Notes: Vegetables / Fruit / Whole grains / Refined
# grains or starchy sides / Beans, fish, or nuts / Other protein sources /
# Dairy / Added sugars / Salty or heavily processed foods).
_FRUIT_WORDS = [
    "apple", "banana", "orange", "grape", "melon", "watermelon",
    "cantaloupe", "honeydew", "pineapple", "mango", "peach", "pear",
    "strawberry", "blueberry", "raspberry", "blackberry", "berries",
    "fruit cup", "fruit bowl", "fresh fruit", "fruit salad", "kiwi",
    "cherries", "plum", "apricot", "clementine", "tangerine", "fig",
    "dried fruit", "raisin",
    "strawberries", "blueberries", "raspberries", "blackberries", "honeydew",
    "grapefruit",
]
_DAIRY_WORDS = [
    "milk", "yogurt", "cheese", "cottage cheese", "cream cheese",
    "greek yogurt", "parfait", "latte", "cheddar", "mozzarella",
    "string cheese", "queso fresco", "ricotta", "custard", "pudding",
]
_ADDED_SUGAR_WORDS = [
    "soda", "pop", "lemonade", "sweet tea", "cinnamon roll", "donut",
    "doughnut", "cookie", "cake", "brownie", "candy", "syrup", "honey",
    "frosting", "icing", "sweetened", "chocolate milk", "milkshake",
    "ice cream", "pastry", "danish", "pop-tart", "sports drink",
    "energy drink", "fruit punch", "juice cocktail", "sweet roll",
]
# NOTE: fruit juice and dessert-adjacent items can legitimately also carry
# a fruit or dairy tag (e.g. "chocolate milk" is dairy + added sugar,
# "cinnamon roll" is refined grain + added sugar) — log_categories below
# is a list, not a single label, so an item can land in more than one
# bucket rather than forcing a single, possibly-wrong choice.


def _contains_any(text: str, words: List[str]) -> bool:
    """Word-boundary matching with optional trailing 's' for plurals.

    Uses word boundaries to prevent substring collisions (e.g. "pepper"
    inside "pepperoni", "veggie" inside "Veggie Burger"). Also matches
    simple plurals so "tomato" catches "tomatoes", "carrot" catches
    "carrots", etc., without needing duplicate entries in every list."""
    for w in words:
        pattern = r"\b" + re.escape(w) + r"s?\b"
        if re.search(pattern, text):
            return True
    return False


# Condiments, dressings, sauces, spreads and garnishes: matched against the
# END of the dish's head phrase (the part before " with "/" and "), so
# "Ranch Dressing" and "Country Sausage Gravy" are condiments but "Meatloaf
# with Gravy" and "Mashed Potatoes and Gravy" are not. These are never a
# plate's vegetable, grain or protein — a garnish of cilantro isn't a veg side.
_CONDIMENT_HEADS = [
    "dressing", "sauce", "seasoning", "seasoning blend", "spice", "vinaigrette", "vinegar", "mayo",
    "mayonnaise", "aioli", "glaze", "syrup", "jelly", "jam", "relish", "ketchup", "mustard", "gravy",
    "oil", "butter", "topping", "compote", "puree", "puree mix", "dip", "spread", "nutella", "honey",
    "sprinkles", "crouton", "cracker", "seed", "chocolate chip", "coconut", "queso", "queso blanco",
    "pickle", "cilantro", "garlic", "ginger", "ginger root", "jalapeno", "jalapeño", "green onion",
    "crushed red pepper", "pickled ginger", "salsa verde",
]


def is_condiment(name: str) -> bool:
    head = re.split(r"\s+(?:with|and|&)\s+", name.lower().strip())[0]
    head = re.sub(r"[^a-zñé' ]+", " ", head).strip()
    return any(re.search(r"(?:^|\s)" + re.escape(w) + r"s?$", head) for w in _CONDIMENT_HEADS)


def _log_categories_for(
    text: str,
    *,
    has_vegetables: bool,
    has_whole_grains: bool,
    is_refined_grain: bool,
    has_lean_protein: bool,
    is_higher_fat_protein: bool,
    high_sodium: bool,
) -> List[str]:
    """Best-guess mapping from a menu item's text/signals to zero or more
    of the 9 lightweight-logging category ids (see LIGHTWEIGHT_LOG_CATEGORIES
    in server.py). Provisional and heuristic — an item can land in more
    than one bucket (e.g. "Buttered Dinner Roll" is refined_grains_starchy
    and, once buttered/salted framing is present, arguably salty_processed
    too), so callers should treat this as a coarse hint, not ground truth."""
    is_fish_or_nut = any(
        w in text for w in ("fish", "salmon", "tilapia", "tuna", "cod", "halibut",
                             "mahi", "catfish", "shrimp", "scallop", "bean", "lentil",
                             "chickpea", "chick pea", "edamame", "tofu", "tempeh",
                             "nut", "almond", "peanut", "walnut", "cashew", "hummus")
    )
    has_fruit = _contains_any(text, _FRUIT_WORDS)
    has_dairy = _contains_any(text, _DAIRY_WORDS)
    has_added_sugar = _contains_any(text, _ADDED_SUGAR_WORDS)

    cats: List[str] = []
    if has_vegetables:
        cats.append("vegetables")
    if has_fruit:
        cats.append("fruit")
    if has_whole_grains:
        cats.append("whole_grains")
    if is_refined_grain:
        cats.append("refined_grains_starchy")
    if has_lean_protein and is_fish_or_nut:
        cats.append("beans_fish_nuts")
    elif has_lean_protein or is_higher_fat_protein:
        cats.append("other_protein")
    if has_dairy:
        cats.append("dairy")
    if has_added_sugar:
        cats.append("added_sugars")
    if high_sodium or is_higher_fat_protein:
        cats.append("salty_processed")
    # De-duplicate while preserving first-seen order
    return list(dict.fromkeys(cats))


def classify_item(name: str, station: str = "", portion: str = "") -> dict:
    """Returns heuristic dining-recommendation tags for a single real menu
    item, purely from name/station keyword matching. Never estimates or
    returns a numeric quantity, calorie, gram, or diet-quality-score
    figure — that's out of scope by design, not an oversight. These tags
    are unrelated to a participant's HEI-2020 score, which is computed
    externally from ASA24 dietary recalls."""
    # Name only: live station names are brands ("Bok Choy", "Pasta & Co.",
    # "500 Degrees") that tagged every item at that station as a vegetable
    # or refined grain. The station argument is kept for call compatibility.
    text = name.lower()
    # "Green beans" are a vegetable, not a bean-protein.
    protein_text = re.sub(r"\bgreen beans?\b", " ", text)
    condiment = is_condiment(name)

    is_protein_salad = any(exc in text for exc in _SALAD_PROTEIN_EXCEPTIONS)
    has_vegetables = _contains_any(text, _VEGETABLE_WORDS) and not is_protein_salad and not condiment
    has_whole_grains = _contains_any(text, _WHOLE_GRAIN_WORDS) and not condiment
    is_refined_grain = _contains_any(text, _REFINED_GRAIN_WORDS) and not has_whole_grains and not condiment
    is_fried = _contains_any(text, _FRIED_WORDS)
    # Protein-salads (tuna salad, egg salad, etc.) are mayo-based — not lean proteins
    has_lean_protein = _contains_any(protein_text, _LEAN_PROTEIN_WORDS) and not is_protein_salad \
        and not is_fried and not condiment
    is_higher_fat_protein = _contains_any(protein_text, _HIGHER_FAT_PROTEIN_WORDS) and not condiment
    is_other_protein = _contains_any(protein_text, _OTHER_PROTEIN_WORDS) and not condiment
    high_sodium = _contains_any(text, _HIGH_SODIUM_INDICATORS) or is_fried
    fiber_hint = _contains_any(text, _HIGH_FIBER_HINTS)

    if fiber_hint or has_vegetables or has_whole_grains:
        fiber_level = "higher"
    elif is_refined_grain or is_higher_fat_protein:
        fiber_level = "lower"
    else:
        fiber_level = "unknown"

    matched_any = has_vegetables or has_whole_grains or is_refined_grain or \
        has_lean_protein or is_higher_fat_protein or is_other_protein or high_sodium or fiber_hint
    confidence = "medium" if matched_any else "low"

    log_categories = _log_categories_for(
        text,
        has_vegetables=has_vegetables,
        has_whole_grains=has_whole_grains,
        is_refined_grain=is_refined_grain,
        has_lean_protein=has_lean_protein,
        is_higher_fat_protein=is_higher_fat_protein or is_other_protein,
        high_sodium=high_sodium,
    )
    if is_other_protein and not (is_higher_fat_protein or high_sodium) and "salty_processed" in log_categories:
        log_categories.remove("salty_processed")  # plain eggs/pork/steak aren't salty_processed by default

    return {
        "has_vegetables": has_vegetables,
        "has_whole_grains": has_whole_grains,
        "has_lean_protein": has_lean_protein,
        "high_sodium": high_sodium,
        "fiber_level": fiber_level,
        "confidence": confidence,
        "log_categories": log_categories,
        "is_condiment": condiment,
    }


def classify_menu(menu: dict) -> dict:
    """Attaches a 'tags' dict to every item in a fetched menu (live or
    sample). Returns a new dict, does not mutate the input."""
    out = dict(menu)
    out["stations"] = []
    for station in menu.get("stations", []):
        new_items = []
        for item in station.get("items", []):
            tags = classify_item(item["name"], station.get("station", ""), item.get("portion", ""))
            new_items.append({**item, "tags": tags})
        out["stations"].append({**station, "items": new_items})
    return out


# ----------------------------------------------------------------------------
# LLM-powered batch classifier (one call per menu, not per item)
# ----------------------------------------------------------------------------

_LLM_CLASSIFY_MODEL = "protected.gpt-4.1-nano"  # non-reasoning, cheap, fast; o4-mini exhausts its
# thinking budget before producing output on a 125-item batch

_LLM_SYSTEM = """\
You are a food classification assistant for a college dining hall app.
Given a list of menu item names, classify each one for these diet signals:
  has_vegetables  - true if the item is primarily a vegetable (not a dressing, sauce, or seasoning)
  has_whole_grains - true if the item is primarily a whole grain (brown rice, quinoa, whole wheat, etc.)
  has_lean_protein - true if the item is primarily a lean protein (grilled/baked poultry, fish, legumes, tofu)
  high_sodium      - true if the item is fried, cured, smoked, heavily sauced, or contains cheese/bacon/sausage
  log_categories   - zero or more of: "vegetables", "fruit", "whole_grains", "refined_grains_starchy",
                     "beans_fish_nuts", "other_protein", "dairy", "added_sugars", "salty_processed"
                     (an item can belong to more than one, e.g. a buttered cinnamon roll is
                     refined_grains_starchy AND added_sugars; a plain grilled fish fillet is beans_fish_nuts only)

Rules:
- Condiments, dressings, seasonings, and sauces: set has_vegetables/has_whole_grains/has_lean_protein/
  high_sodium to false and log_categories to an empty list.
- Mixed dishes: use the dominant ingredient(s).
- When genuinely uncertain, prefer false / an empty list (conservative default).
- NEVER return calorie counts, gram weights, or any numeric nutrition figures or diet-quality scores.

Respond ONLY with a JSON object mapping each item name exactly to its tags:
{"Item Name": {"has_vegetables": bool, "has_whole_grains": bool, "has_lean_protein": bool, "high_sodium": bool, "log_categories": [string, ...]}, ...}
No markdown, no prose, just the JSON object.\
"""


async def llm_classify_menu(
    menu: dict,
    tamu_api_key: str,
    model: str = _LLM_CLASSIFY_MODEL,
) -> dict:
    """Classify a full menu in one batched LLM call via the TAMU Chat API.

    Returns a new menu dict with 'tags' attached to every item, same shape
    as classify_menu(). Falls back to the keyword classifier for any item
    the LLM result doesn't cover, and falls back entirely to classify_menu()
    if the LLM call fails. Never raises."""
    import tamus_client  # imported here to avoid a circular import at module load

    # Collect all unique item names across stations
    all_items: List[dict] = []
    for station in menu.get("stations", []):
        for item in station.get("items", []):
            all_items.append({**item, "station": station.get("station", "")})

    if not all_items:
        return classify_menu(menu)

    names = [it["name"] for it in all_items]
    # Deduplicate while preserving order (same item can appear at multiple stations)
    unique_names = list(dict.fromkeys(names))

    user_prompt = "Classify these dining hall items:\n" + "\n".join(
        f"- {n}" for n in unique_names
    )

    try:
        raw = await tamus_client.chat(
            api_key=tamu_api_key,
            model=model,
            system=_LLM_SYSTEM,
            user_text=user_prompt,
            max_tokens=8192,
            temperature=0.0,
        )
        # Strip markdown fences if present
        cleaned = raw.strip().strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
        llm_tags: dict = json.loads(cleaned)
    except Exception as e:
        logger.warning(f"LLM menu classification failed ({e}), falling back to keyword classifier")
        return classify_menu(menu)

    _VALID_LOG_CATEGORY_IDS = {
        "vegetables", "fruit", "whole_grains", "refined_grains_starchy",
        "beans_fish_nuts", "other_protein", "dairy", "added_sugars",
        "salty_processed",
    }

    def _tags_from_llm(name: str) -> Optional[dict]:
        raw_tags = llm_tags.get(name)
        if not isinstance(raw_tags, dict):
            return None
        # Validate shape — never trust arbitrary LLM output blindly
        raw_cats = raw_tags.get("log_categories", [])
        log_categories = [
            c for c in raw_cats if isinstance(c, str) and c in _VALID_LOG_CATEGORY_IDS
        ] if isinstance(raw_cats, list) else []
        return {
            "has_vegetables":  bool(raw_tags.get("has_vegetables", False)),
            "has_whole_grains": bool(raw_tags.get("has_whole_grains", False)),
            "has_lean_protein": bool(raw_tags.get("has_lean_protein", False)),
            "high_sodium":      bool(raw_tags.get("high_sodium", False)),
            "fiber_level": (
                "higher" if raw_tags.get("has_vegetables") or raw_tags.get("has_whole_grains")
                else "lower" if raw_tags.get("high_sodium")
                else "unknown"
            ),
            "confidence": "high",  # LLM-sourced, not a keyword guess
            "log_categories": log_categories,
        }

    out = dict(menu)
    out["stations"] = []
    for station in menu.get("stations", []):
        new_items = []
        for item in station.get("items", []):
            tags = _tags_from_llm(item["name"])
            if tags is None:
                # LLM didn't return this item — fall back to keyword for it
                tags = classify_item(item["name"], station.get("station", ""), item.get("portion", ""))
            new_items.append({**item, "tags": tags})
        out["stations"].append({**station, "items": new_items})

    out["classifier"] = "llm"
    return out
