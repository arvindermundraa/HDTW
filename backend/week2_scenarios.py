"""Week 2 scenario engine — picks the three items / three products for the
cafeteria and grocery scenarios and generates rule-based feedback.

Pure functions only. The HTTP surface + the per-student record live in
server.py (same pattern as weekly_workflow.py). The SAMPLE JSON files in
backend/content/week2_dining_menu.json and week2_grocery_products.json
feed this; a live TAMU Dining API or a USDA FoodData Central integration
will slot in later behind the same loader signatures.

Three invariants the generator enforces for the dining scenario:

1. Every candidate is an eligible main dish (``eligible=true``, i.e.
   not a condiment / topping / beverage / standalone side).
2. Every candidate has all three highlighted nutrients present
   (saturated fat, sodium, dietary fiber).
3. The chosen three carry real trade-offs — no single item is best on
   all three nutrients at once. The spec is explicit about this; a
   student should always have something to weigh.

Feedback never mentions calories. The vocabulary is intentionally
limited to ``more``, ``less``, ``most``, ``least``, and ``the same as``
(ties get called out as ties). The practical suggestion is pulled from
the content file so the research team can rewrite it without touching
Python.
"""
from __future__ import annotations

import json
import logging
from itertools import combinations
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_log = logging.getLogger("llhs.week2_scenarios")
_CONTENT_DIR = Path(__file__).resolve().parent / "content"


# Nutrients the Week 2 scenarios may surface to students. Allow-listed
# here so the content-rule test can let numeric values through only in
# the two SAMPLE files + the two scenario step bodies in week2.json.
# Nutrition team 2026-11-06, item 3: calories ARE now visible on the
# lesson's Nutrition Facts labels (grocery and dining) — ``calories``
# added to the allow-list. The scenario feedback still focuses on
# saturated fat, sodium, added sugars and fiber only (see
# highlighted_nutrients + nutrient_direction in week2.json; calories
# are deliberately not in those lists, so rule-based feedback never
# mentions calories).
WEEK2_LESSON_NUTRIENTS = (
    "saturated_fat_g",
    "sodium_mg",
    "added_sugars_g",
    "fiber_g",
    "calories",
    # Percent Daily Value is allowed on grocery labels only.
    "pct_dv",
)


# --- Loaders -----------------------------------------------------------------

_DINING_CACHE: Optional[Dict[str, Any]] = None
_GROCERY_CACHE: Optional[Dict[str, Any]] = None


def load_dining_menu() -> Dict[str, Any]:
    global _DINING_CACHE
    if _DINING_CACHE is None:
        with (_CONTENT_DIR / "week2_dining_menu.json").open() as f:
            _DINING_CACHE = json.load(f)
    return _DINING_CACHE


def load_grocery_products() -> Dict[str, Any]:
    global _GROCERY_CACHE
    if _GROCERY_CACHE is None:
        with (_CONTENT_DIR / "week2_grocery_products.json").open() as f:
            _GROCERY_CACHE = json.load(f)
    return _GROCERY_CACHE


def _clear_cache() -> None:  # pragma: no cover — test helper only
    global _DINING_CACHE, _GROCERY_CACHE
    _DINING_CACHE = None
    _GROCERY_CACHE = None


# --- Dining picker -----------------------------------------------------------

def _has_required_nutrients(item: Dict[str, Any], nutrients: Tuple[str, ...]) -> bool:
    return all(item.get(n) is not None for n in nutrients)


def _is_best_on_every_nutrient(
    candidate: Dict[str, Any],
    others: List[Dict[str, Any]],
    nutrient_direction: Dict[str, str],
) -> bool:
    """True iff ``candidate`` is strictly best (not tied) on every
    nutrient. Used to reject item sets where one option dominates — the
    spec requires meaningful trade-offs."""
    for nutrient, direction in nutrient_direction.items():
        c_val = candidate[nutrient]
        for other in others:
            o_val = other[nutrient]
            if direction == "lower_is_better" and c_val >= o_val:
                return False
            if direction == "higher_is_better" and c_val <= o_val:
                return False
    return True


def _set_has_meaningful_tradeoffs(
    items: List[Dict[str, Any]],
    nutrient_direction: Dict[str, str],
) -> bool:
    """No single item is best on every nutrient."""
    for i, candidate in enumerate(items):
        others = [x for j, x in enumerate(items) if j != i]
        if _is_best_on_every_nutrient(candidate, others, nutrient_direction):
            return False
    return True


def pick_dining_items(
    menu: Dict[str, Any],
    hall_id: str,
    meal_period: str,
    nutrient_direction: Dict[str, str],
    *,
    desired: int = 3,
) -> Optional[List[Dict[str, Any]]]:
    """Return ``desired`` eligible main items from the given hall and
    meal period that together carry real trade-offs. Returns ``None``
    when no such set exists (the caller falls back to a different meal
    period or to "coming soon")."""
    hall = next((h for h in menu.get("halls", []) if h.get("id") == hall_id), None)
    if not hall:
        return None
    period_items = (hall.get("periods") or {}).get(meal_period) or []
    nutrients = tuple(nutrient_direction.keys())
    eligible = [
        i for i in period_items
        if i.get("eligible") and _has_required_nutrients(i, nutrients)
    ]
    if len(eligible) < desired:
        return None
    for combo in combinations(eligible, desired):
        if _set_has_meaningful_tradeoffs(list(combo), nutrient_direction):
            return list(combo)
    return None


def pick_dining_scenario(
    menu: Dict[str, Any],
    nutrient_direction: Dict[str, str],
    *,
    hall_preference: Optional[str] = None,
    period_preference: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Walk the halls/periods and return ``{hall, meal_period, items}``
    for the first combination that produces a trade-off set. Preferences
    (if provided) are tried first; otherwise the walk is deterministic
    for a given menu."""
    halls = menu.get("halls", [])
    hall_order = [hall_preference] + [h["id"] for h in halls if h["id"] != hall_preference] if hall_preference else [h["id"] for h in halls]
    period_order = [period_preference, "lunch", "dinner", "breakfast"] if period_preference else ["lunch", "dinner", "breakfast"]
    seen_periods: set = set()
    normalized_periods = []
    for p in period_order:
        if p and p not in seen_periods:
            seen_periods.add(p)
            normalized_periods.append(p)
    for hall_id in hall_order:
        if hall_id is None:
            continue
        hall = next((h for h in halls if h.get("id") == hall_id), None)
        if not hall:
            continue
        for period in normalized_periods:
            items = pick_dining_items(menu, hall_id, period, nutrient_direction)
            if items:
                return {
                    "hall_id": hall_id,
                    "hall_label": hall.get("name"),
                    "meal_period": period,
                    "items": items,
                }
    return None


# --- Grocery picker ----------------------------------------------------------

def is_category_served_to_real_users(category: Dict[str, Any]) -> bool:
    """A category is served to real participants only when every product
    in it has ``sample=false``. While any product is still sample, the
    category is restricted to is_test accounts so made-up labels never
    reach the study."""
    return all(not p.get("sample") for p in category.get("products", []))


def is_dining_served_to_real_users(menu: Dict[str, Any]) -> bool:
    """Mirrors ``is_category_served_to_real_users`` for the dining menu
    file. The cafeteria scenario is removed from the settings choice
    list for real participants whenever any item across any hall/period
    is still ``sample=true``. The intent is identical to the grocery
    gate: no made-up nutrient numbers should ever reach the study
    cohort, and silently serving a sample card to a real participant
    would be worse than hiding the setting."""
    halls = menu.get("halls") or []
    if not halls:
        return False
    for hall in halls:
        for period_items in (hall.get("periods") or {}).values():
            for item in period_items:
                if item.get("sample"):
                    return False
    return True


def pick_grocery_category(
    products: Dict[str, Any],
    focus_area: Optional[str],
    *,
    default_category: str = "canned_soups",
    is_test: bool = False,
) -> Optional[Dict[str, Any]]:
    """Return the category matched to the student's focus_area, or the
    default if the focus-area category isn't available (or is still
    sample for a non-test account)."""
    categories = {c["id"]: c for c in products.get("categories", [])}
    want = None
    if focus_area:
        want = next(
            (c for c in categories.values() if c.get("focus_area_hint") == focus_area),
            None,
        )
    if want and (is_test or is_category_served_to_real_users(want)):
        return want
    fallback = categories.get(default_category)
    if fallback and (is_test or is_category_served_to_real_users(fallback)):
        return fallback
    # Last resort: any category this user is allowed to see.
    for c in categories.values():
        if is_test or is_category_served_to_real_users(c):
            return c
    return None


# --- Rule-based feedback -----------------------------------------------------

def _comparative(
    chosen: Dict[str, Any],
    others: List[Dict[str, Any]],
    nutrient: str,
    direction: str,
) -> Tuple[str, bool]:
    """Describe how the chosen item compares to the other two on this
    nutrient. Returns ``(phrase, is_favourable)``.

    ``phrase`` reads: ``"more fiber than the other two"``,
    ``"the same sodium as the <other-brand>"``, ``"the most saturated
    fat of the three"``, ``"the least sodium"``, and so on.
    """
    c_val = chosen[nutrient]
    o_vals = [o[nutrient] for o in others]

    best_val = min([c_val] + o_vals) if direction == "lower_is_better" else max([c_val] + o_vals)
    worst_val = max([c_val] + o_vals) if direction == "lower_is_better" else min([c_val] + o_vals)

    # Count how many of the three (including chosen) sit at best/worst.
    all_vals = [c_val] + o_vals
    chosen_is_best_unique = c_val == best_val and all_vals.count(best_val) == 1
    chosen_is_worst_unique = c_val == worst_val and all_vals.count(worst_val) == 1
    all_tied = len(set(all_vals)) == 1

    favourable_word = "least" if direction == "lower_is_better" else "most"
    unfavourable_word = "most" if direction == "lower_is_better" else "least"
    more_or_less_fav = "less" if direction == "lower_is_better" else "more"
    more_or_less_unfav = "more" if direction == "lower_is_better" else "less"

    if all_tied:
        return (f"the same {nutrient_phrase(nutrient)} as the other two", True)

    if chosen_is_best_unique:
        return (f"the {favourable_word} {nutrient_phrase(nutrient)} of the three", True)

    if chosen_is_worst_unique:
        return (f"the {unfavourable_word} {nutrient_phrase(nutrient)} of the three", False)

    # Chosen is between (not uniquely best or worst). Could be tied with
    # exactly one other; call that out explicitly so the student sees
    # the shape of the trade-off.
    if o_vals.count(c_val) == 1:
        other = next(o for o in others if o[nutrient] == c_val)
        other_name = other.get("name") or other.get("id")
        return (f"the same {nutrient_phrase(nutrient)} as the {other_name}", True)

    # Chosen is in the middle; neither best nor worst and no tie.
    is_fav = (direction == "lower_is_better" and c_val < max(o_vals)) or (
        direction == "higher_is_better" and c_val > min(o_vals)
    )
    word = more_or_less_fav if is_fav else more_or_less_unfav
    return (f"{word} {nutrient_phrase(nutrient)} than one of the others", is_fav)


# Human phrase for a nutrient code — overridden per-scenario in content
# (nutrient_display_labels on the scenario def) when callers want to
# render these themselves, but the feedback generator keeps a default
# mapping so unit tests don't need a content-file in the loop.
_NUTRIENT_PHRASES = {
    "saturated_fat_g": "saturated fat",
    "sodium_mg": "sodium",
    "added_sugars_g": "added sugars",
    "fiber_g": "fiber",
}


def nutrient_phrase(nutrient: str) -> str:
    return _NUTRIENT_PHRASES.get(nutrient, nutrient)


def build_dining_feedback(
    items: List[Dict[str, Any]],
    chosen_id: str,
    *,
    nutrient_direction: Dict[str, str],
    practical_suggestions: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Rule-based feedback for the chosen dining item.

    Produces up to two favourable notes about the chosen item + up to
    one trade-off, plus a practical suggestion tied to the trade-off's
    nutrient. The feedback NEVER mentions calories — the function only
    looks at the nutrients in ``nutrient_direction``.
    """
    chosen = next((i for i in items if i["id"] == chosen_id), None)
    if chosen is None:
        return {"strengths": [], "trade_off": None, "suggestion": None, "chosen_id": chosen_id}
    others = [i for i in items if i["id"] != chosen_id]

    nutrient_notes: List[Tuple[str, bool, str]] = []  # (nutrient, is_fav, phrase)
    for nutrient, direction in nutrient_direction.items():
        phrase, is_fav = _comparative(chosen, others, nutrient, direction)
        nutrient_notes.append((nutrient, is_fav, phrase))

    strengths = [n for n in nutrient_notes if n[1]]
    weaknesses = [n for n in nutrient_notes if not n[1]]

    # Up to 2 strengths, 1 trade-off per spec 3.2.
    chosen_strengths = strengths[:2]
    trade_off_tuple = weaknesses[0] if weaknesses else None

    strength_phrases = [
        f"It has {phrase}." for (_, _, phrase) in chosen_strengths
    ]
    trade_off_phrase = None
    suggestion = None
    if trade_off_tuple is not None:
        _, _, phrase = trade_off_tuple
        trade_off_phrase = f"The trade-off: it has {phrase}."
        if practical_suggestions is not None:
            suggestion = practical_suggestions.get(trade_off_tuple[0])

    sentences: List[str] = []
    sentences.extend(strength_phrases)
    if trade_off_phrase:
        sentences.append(trade_off_phrase)
    if suggestion:
        sentences.append(suggestion)

    return {
        "chosen_id": chosen_id,
        "chosen_name": chosen.get("name"),
        "strengths": [{"nutrient": n, "phrase": p} for (n, _, p) in chosen_strengths],
        "trade_off": {"nutrient": trade_off_tuple[0], "phrase": trade_off_tuple[2]} if trade_off_tuple else None,
        "suggestion": suggestion,
        "sentences": sentences,
        "body": " ".join(sentences),
    }


def build_grocery_feedback(
    products: List[Dict[str, Any]],
    chosen_id: str,
    *,
    nutrient_direction: Dict[str, str],
    practical_suggestions: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Grocery feedback uses the same comparative shape as dining — the
    only difference is the Nutrition Facts label on the product carries
    four nutrients instead of three. Serving-size differences are called
    out when they differ across the three products so students know the
    comparison is on the same basis."""
    base = build_dining_feedback(
        products,
        chosen_id,
        nutrient_direction=nutrient_direction,
        practical_suggestions=practical_suggestions,
    )
    serving_sizes = {p.get("serving_size") for p in products if p.get("serving_size")}
    if len(serving_sizes) > 1:
        base["sentences"].insert(
            0,
            "Serving sizes differ across these labels — check them before you compare.",
        )
        base["body"] = " ".join(base["sentences"])
    return base


# --- Completion rule ---------------------------------------------------------

def completed_scenario_count(record: Dict[str, Any]) -> int:
    """How many distinct scenario responses the student has saved.
    Weekly workflow's ``three_scenarios_completed`` completion rule reads
    this: once >= 3, the ``scenarios`` step is marked done."""
    scenarios_step = (record.get("step_statuses") or {}).get("scenarios") or {}
    responses = scenarios_step.get("responses") or {}
    return sum(1 for v in responses.values() if v and v.get("chosen_id"))


def scenarios_completed(record: Dict[str, Any], required: int = 3) -> bool:
    return completed_scenario_count(record) >= required
