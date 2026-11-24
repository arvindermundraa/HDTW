"""Unit tests for backend/week2_scenarios.py — the dining picker,
grocery category picker, and rule-based feedback generator.

Pure functions only. These exercise the three invariants from the spec:

1. The dining picker returns three eligible main items with real
   trade-offs (no single item best on every highlighted nutrient).
2. Feedback mentions up to two strengths and one trade-off, uses
   more/less/most/least/the-same-as, and NEVER mentions calories.
3. Completion counts distinct scenario responses; the step is done at
   three.
"""
from __future__ import annotations

import copy

import week2_scenarios


# --- Dining fixtures -------------------------------------------------------

# Three items that between them have a true trade-off:
#   LEAN  — lowest sat fat, lowest sodium, mid fiber
#   HIGH_FIBER — mid sat fat, mid sodium, highest fiber
#   RICH  — highest sat fat, highest sodium, lowest fiber (dominant worst)
# None of the three is best on all three nutrients.
LEAN = {"id": "lean", "name": "Grilled chicken bowl", "eligible": True,
        "saturated_fat_g": 2, "sodium_mg": 400, "fiber_g": 5}
HIGH_FIBER = {"id": "fiber", "name": "Three-bean chili", "eligible": True,
              "saturated_fat_g": 5, "sodium_mg": 600, "fiber_g": 10}
RICH = {"id": "rich", "name": "Chicken alfredo", "eligible": True,
        "saturated_fat_g": 12, "sodium_mg": 1000, "fiber_g": 2}
SIDE_ONLY = {"id": "side", "name": "Steamed broccoli (side)", "eligible": False,
             "saturated_fat_g": 0, "sodium_mg": 20, "fiber_g": 3}
NO_SODIUM = {"id": "mystery", "name": "Mystery item", "eligible": True,
             "saturated_fat_g": 3, "sodium_mg": None, "fiber_g": 2}


MENU = {
    "halls": [
        {"id": "test_hall", "name": "Test Hall", "periods": {
            "lunch": [LEAN, HIGH_FIBER, RICH, SIDE_ONLY, NO_SODIUM],
        }},
    ]
}

NUTRIENT_DIRECTION = {
    "saturated_fat_g": "lower_is_better",
    "sodium_mg": "lower_is_better",
    "fiber_g": "higher_is_better",
}


# --- Picker tests ---------------------------------------------------------

def test_picker_excludes_ineligible_and_missing_nutrient_items():
    picked = week2_scenarios.pick_dining_items(MENU, "test_hall", "lunch", NUTRIENT_DIRECTION)
    assert picked is not None
    ids = {i["id"] for i in picked}
    # SIDE_ONLY is eligible=false; NO_SODIUM is missing a nutrient.
    assert "side" not in ids
    assert "mystery" not in ids


def test_picker_enforces_meaningful_tradeoff():
    # Build a menu where one item dominates — the picker must return None.
    dominant = {"id": "dom", "name": "Dominant", "eligible": True,
                "saturated_fat_g": 1, "sodium_mg": 100, "fiber_g": 20}
    worse_a = {"id": "wa", "name": "Worse A", "eligible": True,
               "saturated_fat_g": 5, "sodium_mg": 500, "fiber_g": 5}
    worse_b = {"id": "wb", "name": "Worse B", "eligible": True,
               "saturated_fat_g": 6, "sodium_mg": 600, "fiber_g": 3}
    menu = {"halls": [{"id": "h", "name": "H", "periods": {"lunch": [dominant, worse_a, worse_b]}}]}
    assert week2_scenarios.pick_dining_items(menu, "h", "lunch", NUTRIENT_DIRECTION) is None


def test_pick_scenario_falls_through_periods_when_first_has_no_tradeoff():
    # Lunch has a dominant item (LEAN is strictly best on every nutrient
    # against the two worse options). Dinner has a real trade-off set.
    worse_a = {"id": "wa", "name": "Worse A", "eligible": True,
               "saturated_fat_g": 5, "sodium_mg": 500, "fiber_g": 2}
    worse_b = {"id": "wb", "name": "Worse B", "eligible": True,
               "saturated_fat_g": 6, "sodium_mg": 600, "fiber_g": 1}
    menu = {"halls": [{"id": "h", "name": "H", "periods": {
        "lunch": [LEAN, worse_a, worse_b],
        "dinner": [LEAN, HIGH_FIBER, RICH],
    }}]}
    picked = week2_scenarios.pick_dining_scenario(menu, NUTRIENT_DIRECTION, period_preference="lunch")
    assert picked is not None and picked["meal_period"] == "dinner"


# --- Feedback tests -------------------------------------------------------

def test_feedback_names_strengths_and_one_tradeoff_for_mid_pick():
    fb = week2_scenarios.build_dining_feedback(
        [LEAN, HIGH_FIBER, RICH], chosen_id="fiber",
        nutrient_direction=NUTRIENT_DIRECTION,
    )
    # HIGH_FIBER is strongest on fiber, middle on both others; it's not the
    # worst on anything, so the strengths may include fiber + a middle call.
    assert fb["chosen_id"] == "fiber"
    assert fb["body"]
    assert len(fb["strengths"]) <= 2
    assert "calori" not in fb["body"].lower()


def test_feedback_identifies_trade_off_for_worst_pick():
    fb = week2_scenarios.build_dining_feedback(
        [LEAN, HIGH_FIBER, RICH], chosen_id="rich",
        nutrient_direction=NUTRIENT_DIRECTION,
        practical_suggestions={"saturated_fat_g": "Try a smaller portion or add a vegetable side."},
    )
    # RICH is the worst on sat fat AND sodium AND fiber; it ends up with
    # three unfavourable notes, so trade_off is present.
    assert fb["trade_off"] is not None
    assert fb["trade_off"]["nutrient"] in NUTRIENT_DIRECTION
    assert "most" in fb["trade_off"]["phrase"] or "least" in fb["trade_off"]["phrase"]
    assert "Try a smaller portion" in fb["body"]
    assert "calori" not in fb["body"].lower()


def test_feedback_handles_ties_with_the_same_as_wording():
    # Two items with identical sodium so the chosen is tied with one other.
    tied_a = {"id": "a", "name": "Dish A", "eligible": True,
              "saturated_fat_g": 2, "sodium_mg": 500, "fiber_g": 5}
    tied_b = {"id": "b", "name": "Dish B", "eligible": True,
              "saturated_fat_g": 4, "sodium_mg": 500, "fiber_g": 7}
    third = {"id": "c", "name": "Dish C", "eligible": True,
             "saturated_fat_g": 6, "sodium_mg": 800, "fiber_g": 3}
    fb = week2_scenarios.build_dining_feedback(
        [tied_a, tied_b, third], chosen_id="a",
        nutrient_direction=NUTRIENT_DIRECTION,
    )
    assert "the same" in fb["body"], f"expected 'the same …' tie wording in: {fb['body']}"


def test_feedback_never_calls_an_option_wrong_or_bad():
    for chosen in ("lean", "fiber", "rich"):
        fb = week2_scenarios.build_dining_feedback(
            [LEAN, HIGH_FIBER, RICH], chosen_id=chosen,
            nutrient_direction=NUTRIENT_DIRECTION,
        )
        body = fb["body"].lower()
        for banned in ("wrong", "bad", "poor choice", "failed", "worst"):
            assert banned not in body, (
                f"Feedback for {chosen!r} uses banned word {banned!r}: {fb['body']}"
            )


def test_strength_count_capped_at_two():
    # The chosen is best on every nutrient — the picker would normally
    # reject such an item set, but build_feedback itself must still cap
    # the strengths list at 2.
    all_best = {"id": "ab", "name": "AB", "eligible": True,
                "saturated_fat_g": 1, "sodium_mg": 100, "fiber_g": 20}
    worse1 = {"id": "w1", "name": "W1", "eligible": True,
              "saturated_fat_g": 5, "sodium_mg": 500, "fiber_g": 5}
    worse2 = {"id": "w2", "name": "W2", "eligible": True,
              "saturated_fat_g": 6, "sodium_mg": 600, "fiber_g": 4}
    fb = week2_scenarios.build_dining_feedback(
        [all_best, worse1, worse2], chosen_id="ab",
        nutrient_direction=NUTRIENT_DIRECTION,
    )
    assert len(fb["strengths"]) == 2


# --- Grocery picker + feedback -------------------------------------------

def test_grocery_picker_matches_focus_area_to_category():
    products = week2_scenarios.load_grocery_products()
    cat = week2_scenarios.pick_grocery_category(products, focus_area="sodium", is_test=True)
    assert cat is not None and cat["focus_area_hint"] == "sodium"


def test_grocery_picker_hides_sample_category_from_non_test_user():
    # Every real product in the SAMPLE file is sample=true, so every
    # category must be filtered out for a non-test user — picker returns None.
    products = week2_scenarios.load_grocery_products()
    assert week2_scenarios.pick_grocery_category(
        products, focus_area="sodium", is_test=False,
    ) is None


def test_grocery_picker_shows_everything_to_test_user():
    products = week2_scenarios.load_grocery_products()
    cat = week2_scenarios.pick_grocery_category(
        products, focus_area="unmapped_area", is_test=True,
    )
    assert cat is not None  # falls back to default_category or any available


def test_grocery_feedback_notes_serving_size_difference():
    a = {"id": "a", "name": "A", "serving_size": "1 cup", "saturated_fat_g": 1, "sodium_mg": 200, "added_sugars_g": 0, "fiber_g": 2}
    b = {"id": "b", "name": "B", "serving_size": "1/2 cup", "saturated_fat_g": 0, "sodium_mg": 50, "added_sugars_g": 0, "fiber_g": 1}
    c = {"id": "c", "name": "C", "serving_size": "1 cup", "saturated_fat_g": 2, "sodium_mg": 300, "added_sugars_g": 1, "fiber_g": 3}
    direction = {
        "saturated_fat_g": "lower_is_better", "sodium_mg": "lower_is_better",
        "added_sugars_g": "lower_is_better", "fiber_g": "higher_is_better",
    }
    fb = week2_scenarios.build_grocery_feedback([a, b, c], chosen_id="b", nutrient_direction=direction)
    assert "Serving sizes differ" in fb["body"]


# --- Completion rule -----------------------------------------------------

def test_scenarios_step_completes_at_three_distinct_responses():
    record = {"step_statuses": {"scenarios": {"responses": {
        "cafeteria": {"chosen_id": "x"},
        "restaurant": {"chosen_id": "y"},
    }}}}
    assert week2_scenarios.scenarios_completed(record) is False
    record["step_statuses"]["scenarios"]["responses"]["home"] = {"chosen_id": "z"}
    assert week2_scenarios.scenarios_completed(record) is True


def test_dining_sample_gate_hides_cafeteria_from_real_users():
    """Mirror of ``is_category_served_to_real_users`` for the dining
    menu. While any item is sample=true the whole menu is served to
    is_test accounts only — the server drops the cafeteria setting
    from a real participant's picker."""
    sample_menu = {"halls": [{"id": "h", "name": "H", "periods": {
        "lunch": [{"id": "x", "name": "X", "eligible": True,
                   "saturated_fat_g": 1, "sodium_mg": 100, "fiber_g": 2,
                   "sample": True}],
    }}]}
    verified_menu = copy.deepcopy(sample_menu)
    for item in verified_menu["halls"][0]["periods"]["lunch"]:
        item["sample"] = False
    assert week2_scenarios.is_dining_served_to_real_users(sample_menu) is False
    assert week2_scenarios.is_dining_served_to_real_users(verified_menu) is True


def test_dining_sample_gate_with_mixed_items_still_hides():
    """One stray sample=true item is enough to keep the cafeteria
    behind the gate — the research team flipping SOME items to
    verified isn't enough to serve them to real participants."""
    mixed = {"halls": [{"id": "h", "name": "H", "periods": {
        "lunch": [
            {"id": "a", "sample": False, "saturated_fat_g": 1, "sodium_mg": 100, "fiber_g": 2, "eligible": True},
            {"id": "b", "sample": True, "saturated_fat_g": 1, "sodium_mg": 100, "fiber_g": 2, "eligible": True},
        ],
    }}]}
    assert week2_scenarios.is_dining_served_to_real_users(mixed) is False


def test_dining_sample_gate_empty_menu_is_not_served():
    assert week2_scenarios.is_dining_served_to_real_users({}) is False
    assert week2_scenarios.is_dining_served_to_real_users({"halls": []}) is False


def test_dining_sample_gate_covers_actual_shipped_menu():
    """The SAMPLE file shipped in this PR has sample=true on every
    item. Until the research team replaces those with verified labels,
    the cafeteria setting must not be offered to real participants."""
    menu = week2_scenarios.load_dining_menu()
    assert week2_scenarios.is_dining_served_to_real_users(menu) is False


def test_completed_scenario_count_ignores_empty_responses():
    record = {"step_statuses": {"scenarios": {"responses": {
        "cafeteria": {"chosen_id": "x"},
        "restaurant": {"chosen_id": ""},  # empty — doesn't count
        "home": None,
    }}}}
    assert week2_scenarios.completed_scenario_count(record) == 1
