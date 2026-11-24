"""twin_habits — the lexicon and the habit rules, no database.
    python -m pytest tests/test_twin_habits.py -n 0"""
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import twin_habits as th  # noqa: E402

TODAY = date(2026, 10, 26)


def meal(name, days_ago=0, slot="breakfast", items=None, skipped=False):
    stamp = (TODAY - timedelta(days=days_ago)).isoformat() + "T14:00:00+00:00"  # 9 AM Chicago
    return {"name": name, "items": items or [], "meal_type": slot, "created_at": stamp, "skipped": skipped}


# ---- lexicon -------------------------------------------------------------------
def test_specific_foods_are_recognised_in_any_word_order():
    assert "whole_milk_yogurt" in th.foods_in("whole milk yogurt and granola")
    assert "whole_milk_yogurt" in th.foods_in("Chobani whole-milk vanilla Greek yogurt")
    assert "whole_milk_yogurt" not in th.foods_in("Low Fat Vanilla Yogurt")
    assert "whole_milk_yogurt" not in th.foods_in("plain greek yogurt")


def test_whole_words_only_and_exclusions():
    assert "vegetables" not in th.foods_in("pepperoni pizza")        # "pepper" is not in "pepperoni"
    assert "vegetables" in th.foods_in("bell pepper salad")
    assert "burger" not in th.foods_in("veggie burger and fries")     # excluded by "veggie burger"
    assert "burger" in th.foods_in("cheeseburger and fries")
    assert "white_bread" not in th.foods_in("turkey sandwich on wheat")
    assert "white_bread" in th.foods_in("turkey sandwich")
    assert "soda" not in th.foods_in("diet coke") and "soda" in th.foods_in("coke")
    assert "pasta" not in th.foods_in("whole wheat pasta") and "pasta" in th.foods_in("penne alfredo")
    assert th.foods_in("egg roll") == []


def test_dining_hall_plates_and_photo_items_count_too():
    text = th.meal_text({"name": "Meal", "items": ["Cheeseburger", "French Fries"]})
    assert {"burger", "fries"} <= set(th.foods_in(text))


# ---- habits ----------------------------------------------------------------------
def test_nothing_is_claimed_until_three_logging_days():
    meals = [meal("whole milk yogurt", 0), meal("whole milk yogurt", 0, "snack"), meal("whole milk yogurt", 1)]
    d = th.detect_habits(meals, TODAY)
    assert d["status"] == "learning" and d["days_logged"] == 2
    assert d["habits"][0]["food_id"] == "whole_milk_yogurt"  # counted, but the caller holds it back
    assert "more day" in th.learning_line(2)


def test_a_food_logged_three_times_becomes_a_regular_with_its_usual_slot():
    meals = [meal("whole milk yogurt and granola", d) for d in (1, 3, 5, 8)] + [meal("whole milk yogurt", 2, "snack")]
    meals += [meal("white rice and orange chicken", 4, "dinner"), meal("white rice bowl", 6, "dinner")]
    d = th.detect_habits(meals, TODAY)
    assert d["status"] == "ready"
    ids = [h["food_id"] for h in d["habits"]]
    assert ids[0] == "whole_milk_yogurt" and "white_rice" not in ids  # twice is not a habit yet
    yog = d["habits"][0]
    assert yog["times"] == 5 and yog["days"] == 5 and yog["top_slot"] == "breakfast"
    assert yog["slots"] == {"breakfast": 4, "snack": 1}
    assert th.evidence_line(yog) == "You've logged whole-milk yogurt in 5 meals over the last 3 weeks, mostly at breakfast."


def test_the_broad_entry_is_dropped_when_the_specific_one_explains_it():
    meals = [meal("whole milk yogurt", d) for d in (1, 2, 3)]
    ids = [h["food_id"] for h in th.detect_habits(meals, TODAY)["habits"]]
    assert ids == ["whole_milk_yogurt"]  # not also "yogurt"
    meals += [meal("plain yogurt", d) for d in (4, 5)]
    ids = [h["food_id"] for h in th.detect_habits(meals, TODAY)["habits"]]
    assert ids == ["yogurt", "whole_milk_yogurt"]  # now "yogurt" (5) says more than "whole-milk yogurt" (3)


def test_old_logs_skipped_meals_and_unlogged_days_do_not_count():
    meals = [meal("whole milk yogurt", d) for d in (30, 31, 32)]   # outside the 21-day window
    meals += [meal("Skipped meal", d, skipped=True) for d in (1, 2, 3)]
    d = th.detect_habits(meals, TODAY)
    assert d["days_logged"] == 3 and d["meals_considered"] == 0 and d["habits"] == []


def test_coach_line_is_counts_only():
    meals = [meal("cheeseburger and fries", d, "lunch") for d in (1, 2, 3)]
    line = th.coach_lines(th.detect_habits(meals, TODAY))
    assert line.startswith("Their regular foods") and "burgers (3 meals, mostly lunch)" in line
    assert th.coach_lines({"status": "learning", "habits": []}) is None


def test_lexicon_is_well_formed():
    ids = [e["id"] for e in th.FOOD_LEXICON]
    assert len(ids) == len(set(ids))
    for e in th.FOOD_LEXICON:
        assert e["label"] and e["match"]
        if e.get("parent"):
            assert e["parent"] in th.LEXICON_BY_ID
