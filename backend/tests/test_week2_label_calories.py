"""Week 2 label calories — nutrition team 2026-11-06, item 3.

Calories are now visible on the Week 2 lesson's Nutrition Facts labels
(grocery and dining). What stays unchanged:

- Students' own food inputs are still never shown as numbers.
- The scripted scenario feedback still focuses on saturated fat, sodium,
  added sugars and fiber — not calories.

These tests pin the new behaviour so a future edit can't silently remove
calories from labels or leak them into scenario feedback.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "llhs_unit_unused")

import week2_scenarios  # noqa: E402

CONTENT = Path(__file__).resolve().parent.parent / "content"
DINING = CONTENT / "week2_dining_menu.json"
GROCERY = CONTENT / "week2_grocery_products.json"


def test_calories_is_on_the_lesson_nutrient_allowlist():
    assert "calories" in week2_scenarios.WEEK2_LESSON_NUTRIENTS


def _walk_items(node, out):
    if isinstance(node, dict):
        if "sample" in node and isinstance(node.get("id"), str):
            out.append(node)
        for v in node.values():
            _walk_items(v, out)
    elif isinstance(node, list):
        for v in node:
            _walk_items(v, out)


def _items(path: Path):
    items: list = []
    _walk_items(json.loads(path.read_text()), items)
    return items


@pytest.mark.parametrize("path", [DINING, GROCERY], ids=["dining", "grocery"])
def test_every_sample_label_carries_a_calorie_number(path):
    items = _items(path)
    assert items, path
    for it in items:
        assert isinstance(it.get("calories"), int), f"{it['id']} missing calories"
        assert 0 < it["calories"] < 2000, f"{it['id']} has an unreasonable calorie value"


def test_scenario_feedback_still_does_not_mention_calories_in_the_week2_content_file():
    """The rule-based feedback is built from highlighted_nutrients +
    nutrient_direction in week2.json, and those lists stay as the four
    the team wanted (saturated fat, sodium, added sugars, fiber). This
    pins that calories are not sneaked in."""
    data = json.loads((CONTENT / "weeks" / "week2.json").read_text())
    scenarios = (data["steps"]["scenarios"]["scenario_defs"] or {})
    for sid, scen in scenarios.items():
        highlighted = scen.get("highlighted_nutrients") or []
        assert "calories" not in highlighted, (
            f"scenarios[{sid}].highlighted_nutrients must not include calories; "
            "the rule-based feedback would then mention calories, which the "
            "nutrition team deliberately keeps off (2026-11-06, item 3)."
        )
        direction = scen.get("nutrient_direction") or {}
        assert "calories" not in direction


def test_rule_based_feedback_never_mentions_calories_for_any_pick():
    """End-to-end: for every eligible dining pick the engine could offer,
    the generated feedback text contains no calorie mention."""
    menu = week2_scenarios.load_dining_menu()
    nutrient_direction = {
        "saturated_fat_g": "lower_is_better",
        "sodium_mg": "lower_is_better",
        "fiber_g": "higher_is_better",
    }
    labels = {
        "saturated_fat_g": "saturated fat",
        "sodium_mg": "sodium",
        "fiber_g": "fiber",
    }
    suggestions = {
        "saturated_fat_g": "Pair it with a vegetable side.",
        "sodium_mg": "Ask for sauce on the side.",
        "fiber_g": "Add a side of beans or vegetables.",
    }
    seen_at_least_one = False
    for hall in menu.get("halls", []):
        for period in hall.get("periods", {}):
            picks = week2_scenarios.pick_dining_items(menu, hall["id"], period, nutrient_direction)
            if not picks:
                continue
            for pick in picks:
                feedback = week2_scenarios.build_dining_feedback(
                    picks, pick["id"],
                    nutrient_direction=nutrient_direction,
                    practical_suggestions=suggestions,
                )
                seen_at_least_one = True
                combined = (
                    (feedback.get("suggestion") or "")
                    + " " + " ".join((n or {}).get("phrase", "") for n in (feedback.get("strengths") or []))
                    + " " + ((feedback.get("trade_off") or {}).get("phrase") or "")
                )
                assert "calori" not in combined.lower(), (pick["id"], feedback)
    assert seen_at_least_one, "no dining picks were produced — the fixture is empty"
