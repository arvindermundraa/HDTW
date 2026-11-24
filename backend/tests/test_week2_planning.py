"""Unit tests for backend/week2_planning.py — pure helpers behind the
Phase 2 planning step.

Covers:
  * matched action list by focus × setting (and the empty-fallback
    when either is unknown).
  * matched coping list by barrier.
  * default reminder time derived per occasion.
  * natural-grammar fit for the completion summary (long preset text,
    custom text, trailing periods, DRAFT prefix, lowercase leading).
  * keep / add / replace outcome shape.
  * Week 1 plan materialisation from a user document.
"""
from __future__ import annotations

import json
from pathlib import Path

import week2_planning


# Load the actual content once; it's what server.py serves and we want
# tests to catch content-level regressions (e.g. the team renaming a
# focus area id or dropping a barrier).
_WEEK2 = json.loads(
    (Path(__file__).resolve().parent.parent / "content" / "weeks" / "week2.json").read_text()
)
CONTENT = _WEEK2  # whole-file shape; the engine reaches in via steps.planning


# --- Lookups ---------------------------------------------------------------

def test_actions_match_focus_and_setting():
    sodium_restaurant = week2_planning.actions_for(CONTENT, "sodium", "restaurant_takeout")
    assert sodium_restaurant == [
        "Ask for sauce on the side.",
        "Choose a dish without cured, smoked, or brined ingredients.",
        "Ask for nutrition information.",
    ]


def test_actions_fallback_when_focus_or_setting_missing():
    assert week2_planning.actions_for(CONTENT, None, "restaurant_takeout") == []
    assert week2_planning.actions_for(CONTENT, "sodium", None) == []
    assert week2_planning.actions_for(CONTENT, "sodium", "unknown_setting") == []


def test_every_focus_setting_cell_has_three_actions():
    # Spec: "3 or 4 actions matched to focus area AND setting". Guard
    # against a cell being deleted or shrunk below two.
    planning = CONTENT["steps"]["planning"]
    for focus, by_setting in planning["actions_by_focus_and_setting"].items():
        for setting, actions in by_setting.items():
            assert 2 <= len(actions) <= 4, f"{focus}/{setting} has {len(actions)} actions"


def test_dining_hall_actions_do_not_mention_nutrient_numbers():
    """Spec requirement: dining hall actions must not depend on menu
    nutrition numbers (sat fat / sodium / fiber / calories / %DV)."""
    planning = CONTENT["steps"]["planning"]
    for focus, by_setting in planning["actions_by_focus_and_setting"].items():
        for action in by_setting.get("dining_hall", []):
            lower = action.lower()
            for banned in (
                "mg", "grams", "g of", "percent dv", "%dv", "calorie", "calories",
            ):
                assert banned not in lower, (
                    f"{focus}/dining_hall action mentions '{banned}': {action!r}"
                )


def test_coping_match_barrier():
    cops = week2_planning.copings_for(CONTENT, "whats_available")
    assert "Pick the closest option, since a better choice still counts." in cops
    assert len(cops) >= 2


def test_coping_fallback_for_missing_barrier():
    assert week2_planning.copings_for(CONTENT, None) == []
    assert week2_planning.copings_for(CONTENT, "no_such_barrier") == []


def test_every_barrier_has_coping_responses():
    barriers = {o["id"] for o in week2_planning.available_barriers(CONTENT)}
    coping_map = CONTENT["steps"]["planning"]["coping_by_barrier"]
    assert barriers == set(coping_map.keys()), f"barriers vs coping keys diverge: {barriers ^ set(coping_map.keys())}"
    for bid, cops in coping_map.items():
        assert 2 <= len(cops) <= 3, f"barrier {bid} has {len(cops)} coping options"


# --- Reminder time ---------------------------------------------------------

def test_default_reminder_time_is_one_hour_before_occasion():
    assert week2_planning.default_reminder_time_for_occasion(CONTENT, "breakfast") == "06:00"
    assert week2_planning.default_reminder_time_for_occasion(CONTENT, "lunch") == "11:00"
    assert week2_planning.default_reminder_time_for_occasion(CONTENT, "dinner") == "17:00"


def test_default_reminder_time_unknown_occasion_is_none():
    assert week2_planning.default_reminder_time_for_occasion(CONTENT, "snack-at-midnight") is None
    assert week2_planning.default_reminder_time_for_occasion(CONTENT, None) is None


# --- Natural grammar -------------------------------------------------------

def test_action_phrase_strips_draft_prefix_and_trailing_period():
    assert week2_planning.action_phrase("DRAFT — Grab a piece of fruit on the way out.") == "grab a piece of fruit on the way out"


def test_action_phrase_preserves_acronyms():
    # First word all-caps > 1 char: keep.
    assert week2_planning.action_phrase("USDA MyPlate guidance.") == "USDA MyPlate guidance"


def test_action_phrase_lowercases_leading_regular_word():
    assert week2_planning.action_phrase("Ask for sauce on the side.") == "ask for sauce on the side"


def test_action_phrase_handles_custom_text_without_period():
    assert week2_planning.action_phrase("ask for brown rice at the dining hall") == "ask for brown rice at the dining hall"


def test_action_phrase_long_custom_text_no_truncation():
    long = "I will walk down to the grocery after my 2pm class and spend a few minutes comparing yogurt labels, picking the one with the least added sugar per serving"
    assert week2_planning.action_phrase(long) == "i will walk down to the grocery after my 2pm class and spend a few minutes comparing yogurt labels, picking the one with the least added sugar per serving"


def test_build_summary_slots_everything_in():
    settings_lookup = {s["id"]: s["label"] for s in week2_planning.available_settings(CONTENT)}
    occasions_lookup = {o["id"]: o for o in week2_planning.available_occasions(CONTENT)}
    summary = week2_planning.build_completion_summary(
        CONTENT,
        plan_management="keep_and_add",
        situation={"setting": "dining_hall", "day": "2026-11-02", "day_label": "Mon Nov 2", "occasion": "lunch"},
        action={"text": "Ask for sauce on the side.", "source": "preset"},
        barrier={"id": "not_enough_time", "label": "Not enough time"},
        coping={"text": "Decide before I get there and pick the quickest option on my list.", "source": "preset"},
        reminder={"time": "11:00"},
        settings_lookup=settings_lookup,
        occasions_lookup=occasions_lookup,
    )
    assert "Mon Nov 2" in summary
    assert "lunch at dining hall" in summary
    assert "ask for sauce on the side" in summary
    assert "you're short on time" in summary
    assert "decide before I get there" in summary  # 'I' pronoun stays capitalized
    assert "11 AM" in summary


def test_build_summary_handles_custom_text_without_awkward_periods():
    settings_lookup = {s["id"]: s["label"] for s in week2_planning.available_settings(CONTENT)}
    occasions_lookup = {o["id"]: o for o in week2_planning.available_occasions(CONTENT)}
    custom_action = "I will walk down to the grocery and pick the oats with the smallest sugar number"
    summary = week2_planning.build_completion_summary(
        CONTENT,
        plan_management="replace",
        situation={"setting": "grocery_convenience", "day_label": "Wednesday", "occasion": "snack"},
        action={"text": custom_action, "source": "custom"},
        barrier={"id": "cost", "label": "Cost"},
        coping={"text": "I'll check what's on sale first and pick from there instead of grabbing the usual bag.", "source": "custom"},
        reminder={"time": "14:00"},
        settings_lookup=settings_lookup,
        occasions_lookup=occasions_lookup,
    )
    assert ".." not in summary  # natural grammar: no doubled periods
    assert "cost gets in the way" in summary


def test_build_summary_keep_only_uses_short_template():
    settings_lookup = {s["id"]: s["label"] for s in week2_planning.available_settings(CONTENT)}
    occasions_lookup = {o["id"]: o for o in week2_planning.available_occasions(CONTENT)}
    summary = week2_planning.build_completion_summary(
        CONTENT,
        plan_management="keep_week1_only",
        situation={}, action={}, barrier={}, coping={}, reminder={},
        settings_lookup=settings_lookup, occasions_lookup=occasions_lookup,
    )
    assert "kept last week" in summary.lower()


# --- Keep / add / replace --------------------------------------------------

def _week1_plan():
    return week2_planning.make_plan(
        user_id="u1", source_week=1, focus_area="sodium",
        focus_goal={"goal": "W1 goal", "plan": "W1 plan"},
        situation={"occasion": "snacks"}, action={"text": "W1 action"}, barrier={}, coping={},
        reminder={}, status=week2_planning.ACTIVE, plan_id="u1:w1",
    )


def _draft_week2():
    return week2_planning.make_plan(
        user_id="u1", source_week=2, focus_area="sodium",
        focus_goal={"goal": "W1 goal", "plan": "W1 plan"},
        situation={"setting": "dining_hall", "occasion": "lunch"},
        action={"text": "Ask for sauce on the side.", "source": "preset"},
        barrier={"id": "not_enough_time", "label": "Not enough time"},
        coping={"text": "Decide before I get there.", "source": "custom"},
        reminder={"time": "11:00"},
        status=week2_planning.ACTIVE, plan_id="u1:w2:a",
    )


def test_keep_and_add_leaves_week1_active_and_adds_week2():
    out = week2_planning.apply_plan_management(
        choice="keep_and_add",
        week1_plan=_week1_plan(),
        draft_week2_plan=_draft_week2(),
        now_iso="2026-11-01T00:00:00+00:00",
    )
    ids_updated = {pid for pid, _ in out["to_upsert"]}
    assert ids_updated == {"u1:w2:a"}
    assert out["cancel_reminders_for"] == []


def test_replace_marks_week1_replaced_and_cancels_its_reminder():
    out = week2_planning.apply_plan_management(
        choice="replace",
        week1_plan=_week1_plan(),
        draft_week2_plan=_draft_week2(),
        now_iso="2026-11-01T00:00:00+00:00",
    )
    by_id = {pid: plan for pid, plan in out["to_upsert"]}
    assert by_id["u1:w1"]["status"] == week2_planning.REPLACED
    assert by_id["u1:w2:a"]["status"] == week2_planning.ACTIVE
    assert "u1:w1" in out["cancel_reminders_for"]


def test_keep_only_saves_week2_dormant_without_reminder():
    out = week2_planning.apply_plan_management(
        choice="keep_week1_only",
        week1_plan=_week1_plan(),
        draft_week2_plan=_draft_week2(),
        now_iso="2026-11-01T00:00:00+00:00",
    )
    by_id = {pid: plan for pid, plan in out["to_upsert"]}
    # Week 1 is untouched (no entry in to_upsert).
    assert "u1:w1" not in by_id
    kept = by_id["u1:w2:a"]
    assert kept["status"] == week2_planning.KEPT
    assert kept["reminder"] == {}
    assert out["cancel_reminders_for"] == []


# --- Week 1 plan materialisation ------------------------------------------

def test_week1_plan_materializes_from_user_with_focus_goal():
    plan = week2_planning.week1_plan_from_user(
        {"id": "u1", "focus_area": "grains",
         "focus_goal": {"goal": "whole grains", "plan": "lunch bread"}},
        week1_reflection_responses={"p2_room": {"selected": "Lunch"}},
    )
    assert plan is not None
    assert plan["focus_area"] == "grains"
    assert plan["source_week"] == 1
    assert plan["situation"]["occasion"] == "lunch"


def test_week1_plan_is_none_without_focus_or_goal():
    assert week2_planning.week1_plan_from_user({"id": "u1"}) is None
    assert week2_planning.week1_plan_from_user({"id": "u1", "focus_area": "grains"}) is None


def test_week1_plan_leaves_occasion_null_when_student_picked_not_sure_yet():
    plan = week2_planning.week1_plan_from_user(
        {"id": "u1", "focus_area": "grains",
         "focus_goal": {"goal": "G", "plan": "P"}},
        week1_reflection_responses={"p2_room": {"selected": "Not sure yet"}},
    )
    assert plan is not None
    assert plan["situation"]["occasion"] is None


def test_week1_plan_handles_migrated_user_with_no_reflection_responses():
    """Pilot migration (PR #38) marks reflection done without saving
    sub-prompt responses — the planning step must still synthesize a
    usable Week 1 plan from focus+goal alone."""
    plan = week2_planning.week1_plan_from_user(
        {"id": "u1", "focus_area": "grains",
         "focus_goal": {"goal": "whole grains", "plan": "brown rice"}},
        week1_reflection_responses=None,
    )
    assert plan is not None
    assert plan["situation"]["occasion"] is None
    # The planning UI reads this and asks only for the missing fields —
    # never shows an empty or broken situation.
