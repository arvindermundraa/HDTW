"""twin_suggest — the swap table and the rules that pick a swap for one
student, against the real menus captured on 2026-10-26. No database.
    python -m pytest tests/test_twin_suggest.py -n 0"""
import json
import os
import re
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "llhs_unit_unused")
import dining_scraper  # noqa: E402
import server  # noqa: E402
import twin_habits  # noqa: E402
import twin_suggest as ts  # noqa: E402

TODAY = date(2026, 10, 26)
FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "apiv4_dineoncampus_2026-10-26.json")


def live_menus():
    """{hall: {period: menu}} parsed from the captured real responses."""
    captured = json.load(open(FIXTURE))
    out = {}
    for hall in ("sbisa", "commons"):
        out[hall] = {}
        for pid, body in captured[hall]["menu_responses"].items():
            out[hall][body["period"]["slug"]] = dining_scraper.parse_period_menu(
                hall, body["period"]["slug"], body["period"], "2026-10-26")
    return out


MENUS = live_menus()
NO_BLOCK = lambda item: False  # noqa: E731


def meal(name, days_ago=0, slot="breakfast"):
    stamp = (TODAY - timedelta(days=days_ago)).isoformat() + "T14:00:00+00:00"
    return {"name": name, "meal_type": slot, "created_at": stamp}


def detected(*meals):
    return twin_habits.detect_habits(list(meals), TODAY)


YOGURT_DAYS = [meal("whole milk yogurt and granola", d) for d in (1, 2, 4, 6, 8)]


# ---- the swap table ----------------------------------------------------------------
def test_every_swap_passes_the_guardrail_and_names_a_source():
    for s in ts.SWAPS:
        for text in (s["swap_label"], s["text"]):
            assert server._guardrail_violation_type(text) is None, s["id"]
            assert not re.search(r"\d", text), s["id"]
            low = text.lower()
            # "less" was allowed by the nutrition team's 2026-11-16 review
            # ("ask for less syrup", "less of the seasoning packet").
            for banned in ("avoid", "cut ", "skip ", "lighter", "guilt", "unhealthy", "bad "):
                assert banned not in low, (s["id"], banned)
        assert s["source"].strip() and isinstance(s["reviewed"], bool)


def test_every_focus_area_has_a_default_and_every_habit_swap_names_a_real_habit():
    areas = {s["focus_area"] for s in ts.SWAPS if s["habit"] is None}
    assert areas == set(a["id"] for a in server.focus_areas.FOCUS_AREAS)
    for s in ts.SWAPS:
        if s["habit"]:
            assert s["habit"] in twin_habits.LEXICON_BY_ID


# ---- the user's two examples -------------------------------------------------------
def test_whole_milk_yogurt_habit_with_a_fats_focus_becomes_low_fat_yogurt_on_todays_menu():
    out = ts.build_suggestions("fats", detected(*YOGURT_DAYS), {"kitchen_access": "none", "university_meal_plan": "yes"},
                               MENUS, NO_BLOCK, today_iso=TODAY.isoformat())
    assert out and out[0]["kind"] == "habit_swap" and out[0]["id"] == "fats_whole_milk_yogurt"
    assert out[0]["habit"]["label"] == "whole-milk yogurt" and out[0]["habit"]["times"] == 5
    assert out[0]["evidence"].startswith("You've logged whole-milk yogurt in 5 meals")
    names = [m["item_name"] for m in out[0]["on_menu_today"]]
    assert names[0] == "Low Fat Vanilla Yogurt" and out[0]["on_menu_today"][0]["period"] == "breakfast"
    assert out[0]["where"].startswith("On today's breakfast menu at")


def test_no_kitchen_with_a_grains_focus_gets_oatmeal_even_before_any_habit():
    out = ts.build_suggestions("grains", detected(meal("coffee", 1), meal("coffee", 2), meal("coffee", 3)),
                               {"kitchen_access": "none"}, MENUS, NO_BLOCK, today_iso=TODAY.isoformat())
    assert out[0]["kind"] == "focus_add" and out[0]["id"] == "grains_default_oatmeal"
    assert out[0]["needs"] == "none"
    assert out[0]["on_menu_today"][0]["item_name"] == "Oatmeal"


# ---- constraints -------------------------------------------------------------------------
def test_setup_from_profile_rules_out_what_they_cannot_cook():
    assert ts.setup_from_profile({"kitchen_access": "none"})["allowed_needs"] == {"none", "microwave"}
    assert ts.setup_from_profile({"kitchen_access": "personal", "appliance_stove": "personal",
                                  "appliance_microwave": "not_available"})["allowed_needs"] == {"none", "stove"}
    assert ts.setup_from_profile({})["allowed_needs"] == {"none", "microwave", "stove"}  # no survey: rule nothing out
    assert ts.setup_from_profile({"university_meal_plan": "yes"})["meal_plan"] is True


def test_a_swap_that_needs_a_stove_is_not_offered_to_someone_without_one():
    pasta = [meal("penne alfredo", d, "dinner") for d in (1, 2, 3)]
    stove = ts.build_suggestions("grains", detected(*pasta), {"kitchen_access": "personal", "appliance_stove": "personal"},
                                 MENUS, NO_BLOCK, today_iso=TODAY.isoformat())
    none = ts.build_suggestions("grains", detected(*pasta), {"kitchen_access": "none"}, MENUS, NO_BLOCK,
                                today_iso=TODAY.isoformat())
    assert stove[0]["id"] == "grains_pasta"
    assert all(s["id"] != "grains_pasta" for s in none) and none[0]["kind"] == "focus_add"


def test_allergies_suppress_both_the_swap_and_menu_items():
    blocked = lambda item: server.item_matches_allergy(item, ["milk", "lactose", "dairy"])  # noqa: E731
    out = ts.build_suggestions("fats", detected(*YOGURT_DAYS), {}, MENUS, blocked, today_iso=TODAY.isoformat())
    assert all(s["id"] != "fats_whole_milk_yogurt" for s in out)      # the swap itself adds dairy
    for s in out:
        for m in s["on_menu_today"]:
            assert "yogurt" not in m["item_name"].lower() and "cheese" not in m["item_name"].lower()


def test_live_items_are_matched_on_their_allergen_labels_not_just_names():
    """The live feed labels Scrambled Eggs with 'Egg' (and lists Liquid Egg
    in its ingredients); an egg allergy now hides it on every
    recommendation surface, name or no name."""
    eggs = next(it for st in MENUS["sbisa"]["breakfast"]["stations"] for it in st["items"]
                if it["name"] == "Scrambled Eggs")
    assert server.item_matches_allergy(eggs, ["egg"])
    assert not server.item_matches_allergy({"name": "Scrambled Eggs"}, ["milk"])


def test_dislikes_from_the_profile_drop_matching_swaps_and_items():
    fries = [meal("cheeseburger and fries", d, "lunch") for d in (1, 2, 3)]
    out = ts.build_suggestions("fats", detected(*fries), {"food_dislikes": "I can't stand potatoes or anything grilled"},
                               MENUS, NO_BLOCK, today_iso=TODAY.isoformat())
    assert out, "the nuts/oils default is still fine"
    for s in out:
        assert "grilled" not in s["swap_label"].lower() and "potato" not in s["swap_label"].lower()
        for m in s["on_menu_today"]:
            assert "potato" not in m["item_name"].lower() and "grilled" not in m["item_name"].lower()


def test_dislikes_match_whole_food_words_only():
    assert ts._dislike_terms("I don't eat red meat") == ["meat", "red"]
    assert ts._dislike_terms("eggs, sweet potatoes and mushrooms") == ["egg", "mushroom", "potato", "sweet"]
    # "eat" is filler, so whole-wheat swaps survive; "ice" (cream) never hides rice.
    assert not ts._blocked_by_dislikes("Whole wheat or multigrain bread", ts._dislike_terms("I don't eat red meat"))
    assert not ts._blocked_by_dislikes("Brown rice or quinoa", ts._dislike_terms("ice cream"))
    assert not ts._blocked_by_dislikes("Grilled chicken sandwich or veggie burger", ["egg"])
    assert ts._blocked_by_dislikes("Hummus, tuna or egg on the sandwich", ["egg"])
    assert ts._blocked_by_dislikes("Baked Potatoes", ["potato"]) and ts._blocked_by_dislikes("Sweet Potato", ["potato"])


def test_menu_terms_match_whole_words():
    """"milk" is not Buttermilk Pancakes; "apple" is not Applewood bacon."""
    menus = {"sbisa": {"breakfast": {"source": "live", "stations": [{"station": "Griddle", "items": [
        {"id": "a", "name": "Buttermilk Pancakes"}, {"id": "b", "name": "Applewood Smoked Bacon"},
        {"id": "c", "name": "Apple Compote"}, {"id": "d", "name": "Skim Milk"}, {"id": "e", "name": "Gala Apple"}]}]}}}
    dairy = ts.SWAPS_BY_ID["dairy_default_breakfast"]
    assert [m["item_name"] for m in ts.menu_matches(dairy, menus, NO_BLOCK)] == ["Skim Milk"]
    fruit = ts.SWAPS_BY_ID["fruit_default_breakfast"]
    assert [m["item_name"] for m in ts.menu_matches(fruit, menus, NO_BLOCK)] == ["Gala Apple"]


def test_an_allergen_named_only_in_the_swap_text_still_blocks_it():
    """Reviewed labels are often general; the food may only be in the text."""
    no_fish = lambda item: server.item_matches_allergy(item, ["fish"])  # noqa: E731
    no_kitchen = ts.setup_from_profile({"kitchen_access": "none"})
    seafood = ts.SWAPS_BY_ID["protein_foods_default"]
    assert "fish" not in seafood["swap_label"].lower() and "fish" in seafood["text"].lower()
    assert not ts.swap_allowed(seafood, "protein_foods", no_kitchen, no_fish)
    assert ts.swap_allowed(seafood, "protein_foods", no_kitchen, NO_BLOCK)


def test_new_review_triggers_are_detected_from_meal_text():
    found = lambda text: twin_habits.foods_in(text)  # noqa: E731
    assert "sweet_tea" in found("chick fil a sweet tea") and "soda" in found("chick fil a sweet tea")
    assert "sweet_tea" not in found("unsweetened iced tea")
    assert "rice_and_beans" in found("white rice with black beans") and "rice_and_beans" not in found("brown rice and beans")
    assert "butter_toast" in found("toast with butter") and "butter_toast" not in found("toast with peanut butter")
    assert "flour_tortilla" in found("chicken burrito") and "flour_tortilla" not in found("tortilla chips and salsa")
    assert "fruit_drink" in found("capri sun") and "sports_drink" not in found("gatorade zero")
    assert "crackers" in found("cheez-its") and "crackers" not in found("triscuit crackers")


def test_sweet_tea_folds_into_soda_when_it_explains_every_soda_meal():
    tea = [meal("sweet tea", d) for d in (1, 2, 3)]
    ids = [h["food_id"] for h in detected(*tea)["habits"]]
    assert "sweet_tea" in ids and "soda" not in ids


def test_swap_allowed_is_the_authorization_check_behind_every_write():
    nut_free = lambda item: server.item_matches_allergy(item, ["peanut", "nut"])  # noqa: E731
    no_kitchen = ts.setup_from_profile({"kitchen_access": "none"})
    assert not ts.swap_allowed(ts.SWAPS_BY_ID["fats_butter_toast"], "fats", no_kitchen, nut_free)
    assert ts.swap_allowed(ts.SWAPS_BY_ID["fats_butter_toast"], "fats", no_kitchen, NO_BLOCK)
    assert not ts.swap_allowed(ts.SWAPS_BY_ID["fats_default_nuts_oils"], "grains", no_kitchen, NO_BLOCK)  # other area
    assert not ts.swap_allowed(ts.SWAPS_BY_ID["grains_pasta"], "grains", no_kitchen, NO_BLOCK)           # needs a stove
    assert "grains_pasta" not in ts.allowed_swap_ids("grains", {"kitchen_access": "none"}, NO_BLOCK)
    assert "grains_default_oatmeal" in ts.allowed_swap_ids("grains", {"kitchen_access": "none"}, NO_BLOCK)


def test_a_swap_being_tried_stays_on_the_card_after_the_habit_fades():
    few = [meal("whole milk yogurt", d) for d in (1, 2)] + [meal("coffee", d) for d in (3, 4)]  # habit gone, still 4 days
    trying = {"fats_whole_milk_yogurt": {"status": "trying", "day": TODAY.isoformat()}}
    out = ts.build_suggestions("fats", detected(*few), {}, MENUS, NO_BLOCK, plan_state=trying,
                               today_iso=TODAY.isoformat())
    assert out[0]["id"] == "fats_whole_milk_yogurt" and out[0]["status"] == "trying" and out[0]["habit"] is None


# ---- the student's own say ----------------------------------------------------------
def test_dismissed_swaps_rest_and_trying_ones_come_first():
    plan = {"fats_whole_milk_yogurt": {"status": "dismissed", "day": TODAY.isoformat()}}
    out = ts.build_suggestions("fats", detected(*YOGURT_DAYS), {}, MENUS, NO_BLOCK, plan_state=plan,
                               today_iso=TODAY.isoformat())
    assert all(s["id"] != "fats_whole_milk_yogurt" for s in out)
    old = {"fats_whole_milk_yogurt": {"status": "dismissed", "day": (TODAY - timedelta(days=20)).isoformat()}}
    out = ts.build_suggestions("fats", detected(*YOGURT_DAYS), {}, MENUS, NO_BLOCK, plan_state=old,
                               today_iso=TODAY.isoformat())
    assert out[0]["id"] == "fats_whole_milk_yogurt" and out[0]["status"] is None  # back after two weeks
    trying = {"fats_default_nuts_oils": {"status": "trying", "day": TODAY.isoformat()}}
    out = ts.build_suggestions("fats", detected(*YOGURT_DAYS), {}, MENUS, NO_BLOCK, plan_state=trying,
                               today_iso=TODAY.isoformat())
    assert out[0]["id"] == "fats_default_nuts_oils" and out[0]["status"] == "trying"


def test_only_the_live_menu_is_searched_never_the_sample():
    sample = {"sbisa": {"breakfast": {**server.COMMONS_SAMPLE_MENU, "source": "sample"}}}
    out = ts.build_suggestions("fats", detected(*YOGURT_DAYS), {}, sample, NO_BLOCK, today_iso=TODAY.isoformat())
    assert out[0]["on_menu_today"] == [] and out[0]["where"] == "No kitchen needed"


def test_no_focus_area_means_no_suggestions():
    assert ts.build_suggestions(None, detected(*YOGURT_DAYS), {}, MENUS, NO_BLOCK) == []


def test_coach_lines_name_the_swap_id_and_the_menu_item():
    out = ts.build_suggestions("fats", detected(*YOGURT_DAYS), {"kitchen_access": "none", "university_meal_plan": "yes"},
                               MENUS, NO_BLOCK, today_iso=TODAY.isoformat())
    lines = ts.coach_lines(out, ts.setup_from_profile({"kitchen_access": "none", "university_meal_plan": "yes"}))
    assert lines[0] == "- Their setup: no kitchen, on a university meal plan"
    assert "swap_id=fats_whole_milk_yogurt" in lines[1] and "they usually have whole-milk yogurt" in lines[1]
    assert lines[2].startswith("  On today's Aggie Dining menu: Low Fat Vanilla Yogurt (Sbisa, breakfast")
