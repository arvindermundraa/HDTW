"""Unit tests for the weekly workflow engine (backend/weekly_workflow.py).

Pure functions only — no server or database needed. The database IO
layer lives in server.py and is exercised by the integration suite.
"""
from __future__ import annotations

import pytest

import weekly_workflow


# --- Mode flag ---------------------------------------------------------------

def test_mode_defaults_to_off_when_env_unset(monkeypatch):
    monkeypatch.delenv("WEEK1_WORKFLOW_MODE", raising=False)
    assert weekly_workflow.workflow_mode(1) == "off"


def test_mode_round_trips_the_three_valid_values(monkeypatch):
    for v in ("off", "test_only", "on"):
        monkeypatch.setenv("WEEK1_WORKFLOW_MODE", v)
        assert weekly_workflow.workflow_mode(1) == v


def test_mode_rejects_typos_and_falls_back_to_off(monkeypatch):
    # A typo in Vercel's dashboard must NEVER silently enable a
    # half-built workflow — fall back to "off" instead.
    monkeypatch.setenv("WEEK1_WORKFLOW_MODE", "ON ")  # trailing space + case
    assert weekly_workflow.workflow_mode(1) == "on"
    monkeypatch.setenv("WEEK1_WORKFLOW_MODE", "yes-please")
    assert weekly_workflow.workflow_mode(1) == "off"


def test_mode_is_per_week(monkeypatch):
    # Week 1 can be "on" while Week 2 is still "test_only" — each flag
    # is read independently so phases can roll out at different cadences.
    monkeypatch.setenv("WEEK1_WORKFLOW_MODE", "on")
    monkeypatch.setenv("WEEK2_WORKFLOW_MODE", "test_only")
    assert weekly_workflow.workflow_mode(1) == "on"
    assert weekly_workflow.workflow_mode(2) == "test_only"


def test_is_enabled_for_gates_test_only_on_is_test(monkeypatch):
    monkeypatch.setenv("WEEK1_WORKFLOW_MODE", "test_only")
    assert weekly_workflow.is_enabled_for(1, is_test=True) is True
    assert weekly_workflow.is_enabled_for(1, is_test=False) is False


def test_is_enabled_for_on_covers_every_user(monkeypatch):
    monkeypatch.setenv("WEEK1_WORKFLOW_MODE", "on")
    assert weekly_workflow.is_enabled_for(1, is_test=True) is True
    assert weekly_workflow.is_enabled_for(1, is_test=False) is True


def test_is_enabled_for_off_covers_no_one(monkeypatch):
    monkeypatch.setenv("WEEK1_WORKFLOW_MODE", "off")
    assert weekly_workflow.is_enabled_for(1, is_test=True) is False
    assert weekly_workflow.is_enabled_for(1, is_test=False) is False


# --- Content loader ----------------------------------------------------------

def test_load_week_returns_week_metadata():
    week = weekly_workflow.load_week(1)
    assert week["week"] == 1
    assert "sequence" in week
    assert isinstance(week["sequence"], list) and week["sequence"]


def test_load_week_raises_for_missing_week():
    with pytest.raises(FileNotFoundError):
        weekly_workflow.load_week(99)


def test_get_step_content_returns_the_definition():
    step = weekly_workflow.get_step_content(1, "overview_video")
    assert step is not None and step["type"] == "video"


def test_get_step_content_returns_none_for_unknown_step():
    assert weekly_workflow.get_step_content(1, "nope") is None


# --- Week view ---------------------------------------------------------------

def _content():
    return weekly_workflow.load_week(1)


def test_empty_record_marks_every_step_pending():
    view = weekly_workflow.build_week_view(_content(), record={}, signals={})
    assert view["steps_done"] == 0
    assert view["next_step_id"] == "overview_video"
    assert all(s["status"] == "pending" for s in view["steps"])


def test_focus_selection_auto_completes_from_user_signal():
    # The engine must overlay auto-complete steps at read time, so a
    # student who sets their focus from the Eat tab (bypassing the
    # workflow) still sees focus_selection ticked off on Today.
    view = weekly_workflow.build_week_view(
        _content(),
        record={},
        signals={"focus_area": "sodium", "focus_goal": {}},
    )
    focus_step = next(s for s in view["steps"] if s["id"] == "focus_selection")
    assert focus_step["status"] == "done"


def test_goal_and_plan_requires_both_goal_and_plan_strings():
    partial = weekly_workflow.build_week_view(
        _content(),
        record={},
        signals={"focus_area": "sodium", "focus_goal": {"goal": "Pack a snack"}},
    )
    gp = next(s for s in partial["steps"] if s["id"] == "goal_and_plan")
    assert gp["status"] == "pending"
    full = weekly_workflow.build_week_view(
        _content(),
        record={},
        signals={"focus_area": "sodium", "focus_goal": {"goal": "Pack a snack", "plan": "Bring fruit"}},
    )
    gp = next(s for s in full["steps"] if s["id"] == "goal_and_plan")
    assert gp["status"] == "done"


def test_recorded_steps_count_as_done():
    record = {"step_statuses": {"overview_video": {"status": "done", "completed_at": "2026-10-29T00:00:00Z"}}}
    view = weekly_workflow.build_week_view(_content(), record=record, signals={})
    overview = next(s for s in view["steps"] if s["id"] == "overview_video")
    assert overview["status"] == "done"
    assert overview["completed_at"] == "2026-10-29T00:00:00Z"
    assert view["next_step_id"] == "feedback"


def test_next_step_is_null_when_everything_is_done():
    seq = _content()["sequence"]
    record = {"step_statuses": {sid: {"status": "done"} for sid in seq}}
    view = weekly_workflow.build_week_view(
        _content(),
        record=record,
        signals={"focus_area": "sodium", "focus_goal": {"goal": "G", "plan": "P"}},
    )
    assert view["next_step_id"] is None
    assert view["steps_done"] == view["steps_total"]


def test_week_view_phases_count_done_per_phase():
    record = {"step_statuses": {"overview_video": {"status": "done"}, "feedback": {"status": "done"}}}
    view = weekly_workflow.build_week_view(_content(), record=record, signals={})
    phase1 = next(p for p in view["phases"] if p["id"] == "p1")
    assert phase1["total"] == 3  # overview_video + feedback + focus_selection
    assert phase1["done"] == 2


# --- Response validation -----------------------------------------------------

def test_validate_reflection_text_response_length_cap():
    long = "x" * 2000
    ok, _ = weekly_workflow.validate_step_response(1, "reflection", {"responses": {"p3_working": {"text": long}}})
    assert ok is False


def test_validate_reflection_single_select_must_be_in_options():
    ok, _ = weekly_workflow.validate_step_response(
        1, "reflection", {"responses": {"p2_room": {"selected": "Breakfast"}}},
    )
    assert ok is True
    ok, _ = weekly_workflow.validate_step_response(
        1, "reflection", {"responses": {"p2_room": {"selected": "Midnight"}}},
    )
    assert ok is False


def test_validate_reflection_multi_select_must_be_a_list():
    ok, _ = weekly_workflow.validate_step_response(
        1, "reflection", {"responses": {"p1_behind": {"selected": ["Breakfast", "Lunch"]}}},
    )
    assert ok is True
    ok, _ = weekly_workflow.validate_step_response(
        1, "reflection", {"responses": {"p1_behind": {"selected": "Breakfast"}}},
    )
    assert ok is False


def test_validate_unknown_step_rejected():
    ok, reason = weekly_workflow.validate_step_response(1, "nope", {})
    assert ok is False and "Unknown" in reason


# --- Points -------------------------------------------------------------------

def test_step_points_reads_from_content():
    # Values moved to the nutrition team's 2026-11-06 point structure
    # (see tests/test_points_structure.py for the full mapping). This
    # test just pins that step_points is reading them from the content
    # file (not a hard-coded fallback).
    assert weekly_workflow.step_points(1, "overview_video") == 10   # video
    assert weekly_workflow.step_points(1, "focus_selection") == 15  # selecting focus area
    assert weekly_workflow.step_points(1, "nope") == 0


# --- Carried map + resolver (Phase 2 additions) ------------------------------

def _reflection_record(selected: str):
    return {
        "step_statuses": {
            "reflection": {
                "status": "done",
                "responses": {
                    "p1_behind": {"selected": ["Snacks"]},
                    "p2_room": {"selected": selected},
                    "p3_working": {"text": "I drink water with meals."},
                },
            }
        }
    }


def test_reflection_carries_occasion_into_carried_map():
    view = weekly_workflow.build_week_view(_content(), record=_reflection_record("Breakfast"),
                                           signals={})
    assert view["carried"] == {"occasion": "Breakfast"}


def test_resolve_reflection_substitutes_focus_word_for_moderation_area():
    # Sodium is a moderation focus; the prompt should read
    # "foods higher in sodium" per spec 6.2.
    r = weekly_workflow.resolve_step(
        1, "reflection", focus_area="sodium", focus_area_label="Sodium", carried={},
    )
    assert r["resolved_focus_kind"] == "moderation"
    assert "foods higher in sodium" in r["resolved_prompts"][0]["prompt"]


def test_resolve_reflection_substitutes_focus_label_for_adequacy_area():
    # Vegetables and beans is adequacy; the prompt should read
    # "When did vegetables and beans show up…".
    r = weekly_workflow.resolve_step(
        1, "reflection", focus_area="vegetables_beans",
        focus_area_label="Vegetables and beans", carried={},
    )
    assert r["resolved_focus_kind"] == "adequacy"
    assert "When did vegetables and beans show up" in r["resolved_prompts"][0]["prompt"]


def test_resolve_reflection_fills_completion_template_with_occasion():
    r = weekly_workflow.resolve_step(
        1, "reflection", focus_area="fruit", focus_area_label="Fruit",
        carried={"occasion": "Breakfast"},
    )
    assert r["resolved_completion_message"] == (
        "Thanks. Breakfast is a good place to look. Next, you'll pick one small change and plan when you'll try it."
    )


def test_resolve_reflection_uses_not_sure_message_when_user_is_not_sure():
    r = weekly_workflow.resolve_step(
        1, "reflection", focus_area="fruit", focus_area_label="Fruit",
        carried={"occasion": "Not sure yet"},
    )
    assert r["resolved_completion_message"] == (
        "Thanks for reflecting. When you're ready to pick a spot, your focus area will help you narrow it down. "
        "Next, you'll pick one small change and plan when you'll try it."
    )


def test_resolve_goal_and_plan_surfaces_example_for_focus_area():
    r = weekly_workflow.resolve_step(
        1, "goal_and_plan", focus_area="fruit", focus_area_label="Fruit", carried={},
    )
    assert r["resolved_example"]["goal"].startswith("I will add fruit")
    assert "banana or frozen berries" in r["resolved_example"]["plan"]


def test_resolve_mini_lecture_picks_video_by_focus_area():
    r = weekly_workflow.resolve_step(
        1, "mini_lecture", focus_area="sodium", focus_area_label="Sodium", carried={},
    )
    # Content ships with null URLs today; the resolver surfaces them as
    # top-level fields so the frontend's "coming soon" fallback fires.
    assert r["video_id"] is None
    assert r["video_url"] is None


# --- Supported weeks ---------------------------------------------------------

def test_supported_weeks_covers_week1_and_week2():
    assert 1 in weekly_workflow.SUPPORTED_WEEKS
    assert 2 in weekly_workflow.SUPPORTED_WEEKS
