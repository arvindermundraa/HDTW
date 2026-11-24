"""Future Me scope redirects — nutrition team 2026-11-06, Follow-ups
item 2 ("Topics Future Me should not answer").

Six topics must redirect briefly and kindly, pointing at the study team
or the right healthcare professional:

  a. medical  — diagnosis / treatment / condition-specific diet;
  b. medications — meds and supplements (use, safety, dosing, interactions);
  c. eating_support — restriction / purging / compensatory behaviours /
     body-image concerns (with the campus counseling referral);
  d. weight — weight loss and calorie restriction;
  e. specialized_diets — keto, detox, fasting, other restrictive /
     therapeutic diets;
  f. urgent — tells the student to call 911 (or go to the ER).

Normal nutrition questions MUST still be answered (not flagged as out
of scope). That is what the final test block guards against.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "llhs_unit_unused")

import coach_kb  # noqa: E402
import wording_rules  # noqa: E402


# --- Per-topic triggers (>= 2 questions each so the test set is deep
# enough to catch regressions in the regex detection) -------------------

MEDICAL_QUESTIONS = [
    "What should I eat with high blood pressure?",
    "What's the best diet for type 2 diabetes?",
    "I was just diagnosed with celiac — what can I eat?",
]

MEDICATIONS_QUESTIONS = [
    "Should I take a multivitamin?",
    "How much vitamin D do I need?",
    "Does fish oil interact with any foods?",
]

EATING_SUPPORT_QUESTIONS = [
    "I feel guilty after eating",
    "I keep skipping dinner to save calories",
    "I think I might have an eating disorder",
]

WEIGHT_QUESTIONS = [
    "How do I lose 10 lbs?",
    "What calorie deficit should I aim for?",
    "Can you give me a weight-loss plan?",
]

CALORIES_QUESTIONS = [
    "How many calories a day?",
    "Should I be counting calories?",
]

SPECIALIZED_DIETS_QUESTIONS = [
    "Should I try keto?",
    "Does a detox cleanse work?",
    "Is intermittent fasting good for me?",
]

URGENT_QUESTIONS = [
    "I'm having chest pain right now",
    "I'm having trouble breathing and my lips are swelling",
    "I think I'm having an allergic reaction",
]

NORMAL_NUTRITION_QUESTIONS = [
    "Is brown rice a whole grain?",
    "How much fiber should I eat a day?",   # a reference-value question
    "What's an easy breakfast at the dining hall?",
    "How do I read a sodium label?",
    "What are some lower-sodium swaps?",
    "What's a balanced plate?",
    "How can I add more vegetables and beans to lunch?",
]


# --- Detection: each topic fires on its own triggers --------------------


@pytest.mark.parametrize("q", MEDICAL_QUESTIONS)
def test_medical_questions_route_to_the_medical_redirect(q):
    assert coach_kb.scope_check(q) == "medical", q


@pytest.mark.parametrize("q", MEDICATIONS_QUESTIONS)
def test_medications_questions_route_to_the_medications_redirect(q):
    assert coach_kb.scope_check(q) == "medications", q


@pytest.mark.parametrize("q", EATING_SUPPORT_QUESTIONS)
def test_eating_support_questions_route_to_the_eating_support_redirect(q):
    assert coach_kb.scope_check(q) == "eating_support", q


@pytest.mark.parametrize("q", WEIGHT_QUESTIONS)
def test_weight_questions_route_to_the_weight_redirect(q):
    assert coach_kb.scope_check(q) in {"weight", "eating_support"}, q


@pytest.mark.parametrize("q", CALORIES_QUESTIONS)
def test_calorie_questions_route_to_the_calories_redirect(q):
    assert coach_kb.scope_check(q) in {"calories", "weight"}, q


@pytest.mark.parametrize("q", SPECIALIZED_DIETS_QUESTIONS)
def test_specialized_diet_questions_route_to_the_specialized_diets_redirect(q):
    assert coach_kb.scope_check(q) == "specialized_diets", q


@pytest.mark.parametrize("q", URGENT_QUESTIONS)
def test_urgent_questions_route_to_the_urgent_redirect(q):
    scope = coach_kb.scope_check(q)
    # Urgent can share a signal with medical ("allergic reaction" is also
    # a medical-condition phrase); the student MUST see the 911 message
    # first, so urgent must win the tie.
    assert scope == "urgent", f"{q} -> {scope}"


@pytest.mark.parametrize("q", NORMAL_NUTRITION_QUESTIONS)
def test_normal_nutrition_questions_are_not_flagged(q):
    assert coach_kb.scope_check(q) is None, q


# --- Content: every redirect text passes the wording check -------------


def test_every_redirect_text_passes_the_wording_check():
    for topic, text in coach_kb.DECLINE.items():
        hits = wording_rules.find_avoid_hits(text)
        assert not hits, f"{topic!r} redirect contains avoid phrases: {hits}\nText: {text}"


def test_every_scope_name_scope_check_can_return_has_a_redirect_text():
    scope_names = {"medical", "medications", "eating_support", "weight",
                   "calories", "specialized_diets", "urgent"}
    assert scope_names <= set(coach_kb.DECLINE)


# --- Content: the required cues are present in the right texts ---------


def test_urgent_redirect_mentions_911():
    assert "911" in coach_kb.DECLINE["urgent"]


def test_eating_support_redirect_has_the_campus_counseling_number():
    # 979-845-4427 is TAMU Student Counseling Services; the Nov-6 PDF
    # keeps this verbatim.
    assert "979-845-4427" in coach_kb.DECLINE["eating_support"]


def test_medical_redirect_points_at_a_healthcare_professional_and_the_study_team():
    text = coach_kb.DECLINE["medical"].lower()
    assert "healthcare" in text or "campus health" in text
    assert "study team" in text


def test_boundary_notes_cover_the_nov6_requirements():
    joined = " ".join(coach_kb.BOUNDARY_NOTES).lower()
    assert "never diagnose" in joined or "never diagnoses" in joined
    assert "study team" in joined
    assert "2,000-calorie" in joined or "2000-calorie" in joined
