"""The Coach's knowledge base: entry schema and BM25 retrieval.
    python -m pytest tests/test_coach_kb.py -n 0"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import coach_kb  # noqa: E402

ENTRIES = coach_kb.load_entries()
KB = coach_kb.KnowledgeBase(ENTRIES)
HEI_COMPONENTS = {"total_fruits", "whole_fruits", "total_vegetables", "greens_beans", "whole_grains", "dairy",
                  "total_protein_foods", "seafood_plant_proteins", "fatty_acids", "refined_grains", "sodium",
                  "added_sugars", "saturated_fats"}


def test_every_entry_is_a_cited_draft():
    for e in ENTRIES:
        assert e["source"].strip(), e["id"]
        assert e["reviewed"] is False, f"{e['id']} must stay a draft until the nutrition team reviews it"


def test_covers_all_hei_components_and_curriculum_areas():
    assert HEI_COMPONENTS <= {e["hei_component"] for e in ENTRIES}
    assert {"planning", "applying", "assembling"} <= {e["curriculum_area"] for e in ENTRIES}


def test_entries_pass_the_reply_guardrail():
    # If the model quotes an entry, the guardrail must not block it.
    import server
    for e in ENTRIES:
        assert server._guardrail_violation_type(e["text"]) is None, e["id"]


@pytest.mark.parametrize("question,expected", [
    ("Is brown rice a whole grain?", "whole_grains"),
    ("What's an easy high-fibre breakfast in the dining hall?", "high_fiber_breakfast"),
    # Multiple KB entries legitimately answer label questions now (the
    # curriculum chapter + the quick-reference guideline added for the
    # 2026-10-29 nutrition-team updates). Either is a correct hit.
    ("How do I read a nutrition label?", {"applying_nutrition_information", "guideline_label_reading"}),
    ("cheap healthy food on a budget", "budget_swaps"),
    ("What counts as greens and beans?", "greens_beans"),
    ("Is juice as good as fruit?", "whole_fruits"),
    ("How do I use my meal plan better?", "meal_plan_tips"),
    ("Ideas for snacks between classes", "snacks_between_classes"),
    ("How much exercise should I get?", "move_guideline"),
    ("What should I order at a fast food restaurant?", "eating_out"),
    ("Is salt bad for me?", "sodium"),
    ("What are added sugars?", "added_sugars"),
    ("How do I plan my meals for the week?", "planning_healthy_eating"),
    ("What's a balanced plate?", "assembling_balanced_meals"),
    ("Is olive oil healthy?", "fatty_acids"),
])
def test_sample_questions_find_the_right_entry(question, expected):
    hits = KB.retrieve(question)
    assert hits, question
    if isinstance(expected, (set, frozenset)):
        assert hits[0]["id"] in expected, (question, hits[0]["id"])
    else:
        assert hits[0]["id"] == expected, (question, hits[0]["id"])


@pytest.mark.parametrize("question", ["Who won the football game?", "How do I fix my car?", "Tell me about quantum physics"])
def test_off_topic_questions_find_nothing(question):
    assert KB.retrieve(question) == []


@pytest.mark.parametrize("question,kind", [
    ("How many calories are in rice?", "calories"),
    ("I want to lose weight fast", "weight"),
    # Nutrition team 2026-11-06, Follow-ups item 2: supplements get the
    # medications redirect (new, separate from medical).
    ("Should I take a vitamin supplement?", "medications"),
    ("Is intermittent fasting good for me?", "specialized_diets"),
    ("I'm having chest pain right now", "urgent"),
    ("Is brown rice a whole grain?", None),
])
def test_scope_check(question, kind):
    assert coach_kb.scope_check(question) == kind
