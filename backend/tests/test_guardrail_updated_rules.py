"""Guardrail behaviour under the nutrition team's 2026-10-29 rule change.

New rules:
  * General nutrition-guideline numbers are ALLOWED in Future Me and game
    feedback (sodium 2,300 mg/day, 5% DV, 2 cups fruit, etc.).
  * Student's own HEI scores (x/5, x/10, x/13) remain BLOCKED.
  * Weight-loss and body-size framing remain BLOCKED.
  * Calorie counts (``\\d+ calories/kcal``) are BLOCKED by default; the
    ``FUTURE_ME_ALLOW_CALORIE_INFO`` env flag turns them on.
  * Plate-review suggestions keep the stricter "cut back on X" phrase list
    (judgmental context about a specific plate the student built).

These tests pin the exact pass/fail behaviour so a future tightening or
loosening of the guardrails trips a review.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "llhs_unit_unused")
os.environ.pop("FUTURE_ME_ALLOW_CALORIE_INFO", None)

import server  # noqa: E402


# --- General guideline numbers are now ALLOWED in Future Me ---------------

# Rewritten from an earlier set that used "should" — the nutrition team
# removed "should" from the allowed vocabulary on 2026-11-06 (item 3).
# These sentences still cite the standard public-health numbers the
# guardrail allows; they just use team-approved framing.
ALLOWED_GUIDELINE_SNIPPETS = [
    "The Dietary Guidelines point most adults toward less than 2,300 mg of sodium a day.",
    "Look for 5% Daily Value or less for sodium — that's low.",
    "20% DV or more per serving is considered high.",
    "The FDA Daily Value for fiber is 28 g per day.",
    "A cup of beans has 7–10 g of fiber.",
    "About 2 cups of fruit and 2½ cups of vegetables a day.",
    "The Dietary Guidelines put at least half of your grains as whole grains.",
    "Keep added sugars under about 50 g a day (10% of calories on the label).",
    "A 12-oz can of regular soda has about 39 g of added sugar.",
    "Olive oil is mostly unsaturated fat — a heart-healthy swap for butter.",
]


@pytest.mark.parametrize("text", ALLOWED_GUIDELINE_SNIPPETS)
def test_guardrail_allows_general_guideline_numbers(text):
    """Future Me (and game feedback) must now be able to cite the
    standard public-health numbers without being blocked."""
    assert server._guardrail_violation_type(text) is None, text


# --- Student's own HEI score reveals: STILL BLOCKED -----------------------

OWN_SCORE_SNIPPETS = [
    "Your HEI score is 7/13.",
    "You scored 4.2/10 on grains.",
    "You scored 60/100 overall.",
    "Your diet-quality score has gone up.",
    "You have a 3/5 on whole grains.",
    "Your heart-health score last week was 65/100.",
]


@pytest.mark.parametrize("text", OWN_SCORE_SNIPPETS)
def test_guardrail_blocks_student_own_score_reveals(text):
    assert server._guardrail_violation_type(text) is not None, text


# --- Weight-loss / body-size framing: STILL BLOCKED -----------------------

WEIGHT_LOSS_SNIPPETS = [
    "This swap will help you lose weight quickly.",
    "You can slim down by cutting dinner.",
    "A great way to burn fat is cardio.",
    "This is a weight-loss friendly plate.",
    "Try watching your weight by skipping dessert.",
    "This counts as weight-loss advice.",
]


@pytest.mark.parametrize("text", WEIGHT_LOSS_SNIPPETS)
def test_guardrail_blocks_weight_loss_and_body_size_framing(text):
    assert server._guardrail_violation_type(text) is not None, text


# --- Calorie counts: ALWAYS BLOCKED (nutrition team 2026-11-06, item 1).
# The old FUTURE_ME_ALLOW_CALORIE_INFO flag was removed.

CALORIE_COUNT_SNIPPETS = [
    "A cup of brown rice has about 220 calories.",
    "Aim for 2,000 kcal a day.",
    "That meal is around 650 calories.",
    "Fifteen hundred calories a day is the goal.",
]


@pytest.mark.parametrize("text", CALORIE_COUNT_SNIPPETS)
def test_guardrail_always_blocks_calorie_counts(text):
    assert server._guardrail_violation_type(text) is not None, text


def test_guardrail_allows_2000_calorie_diet_as_a_reference_frame():
    """The one calorie number the team keeps: the 2,000-calorie diet
    used to FRAME each FDA Daily Value as a general reference value
    (nutrition team 2026-11-06, item 1)."""
    assert server._guardrail_violation_type(
        "The FDA Daily Value for sodium is less than 2,300 mg a day — a "
        "general reference value based on a 2,000-calorie diet, not a "
        "personal target."
    ) is None


# --- Score reveals ALWAYS block ------------------------------------------

def test_score_reveals_always_block():
    assert server._guardrail_violation_type("You scored 60/100.") is not None


# --- Plate-review ``strict=True`` keeps judgmental framing out ------------

PLATE_REVIEW_BLOCKED_SUGGESTIONS = [
    "Cut back on the rice.",
    "Cut down on the cheese.",
    "Skip the pasta next time.",
    "Keep it light.",
    "A lighter choice would be a smaller portion.",
]


@pytest.mark.parametrize("text", PLATE_REVIEW_BLOCKED_SUGGESTIONS)
def test_plate_review_strict_mode_blocks_food_specific_restriction_framing(text):
    assert server._guardrail_violation_type(text, strict=True) is not None, text


@pytest.mark.parametrize("text", [
    # Future Me's broader list lets through things that are legitimate
    # public-health language when framed as general guidance.
    "Try to cut back on packaged soups to lower your sodium.",
    "A good move is to cut down on sugary drinks over the week.",
])
def test_future_me_normal_mode_allows_general_cut_back_framing(text):
    assert server._guardrail_violation_type(text) is None, text


# --- Existing content-rule guard still holds for weekN.json ----------------

def test_week_content_rule_file_still_exists():
    """The weekly-workflow content files are participant-facing scripted
    copy, not Future Me answers. The content-rule test
    (test_week_content_rules.py) still enforces the stricter rule on
    weekN.json — the 2026-10-29 rule change is NOT retroactive to those
    files. This pointer just keeps the invariant visible."""
    from pathlib import Path
    assert (Path(__file__).parent / "test_week_content_rules.py").exists()
