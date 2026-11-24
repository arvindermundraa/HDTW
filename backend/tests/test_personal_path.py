"""Unit tests for personal_path.build_personal_path and daily_goals snapshots.
Pure functions — no server or database needed."""
from datetime import date, datetime, timezone

import pytest

import daily_goals
import personal_path
import program
import study_time


@pytest.fixture
def freeze_now(monkeypatch):
    """`build_snapshot` and `daily_mood` now get "today" from study_today(),
    not a function arg. Tests that previously passed a `now` datetime to
    build_snapshot pin the global clock with this fixture instead."""
    def _apply(now_utc_moment):
        monkeypatch.setattr(study_time, "_now_utc", lambda: now_utc_moment)
    return _apply

START = date(2026, 9, 1)
VIDEOS = {"c1": {"id": "c1"}, "c2": {"id": "c2"}, "c3": {"id": "c3"}}
CHECKIN = {"days_until": 5, "message": "5 days until your next check-in"}


def meal(day, cats=(), skipped=False):
    return {"created_at": f"2026-09-{day:02d}T17:00:00+00:00", "categories": list(cats), "skipped": skipped}


def build(user=None, meals=(), assessments=(), today=date(2026, 9, 10), done_steps=(), games_done=()):
    user = {"created_at": "2026-09-01T00:00:00+00:00", "onboarded": True, "focus_areas": [], **(user or {})}
    prog = program.build(START, today, done_steps=set(done_steps), videos_done=set(), games_done=set(games_done),
                         focus_set_on=None, videos=VIDEOS)
    return personal_path.build_personal_path(user, list(meals), prog, list(assessments), CHECKIN)


def ids(path):
    return [m["id"] for m in path["milestones"]]


GRAINS = {"focus_area": "grains", "focus_areas": ["whole_grains", "refined_grains"],
          "focus_goal": {"goal": "Brown rice at lunch"}}


def test_all_eight_weeks_are_visible_with_matching_counts():
    p = build()
    assert [w["week"] for w in p["weeks"]] == list(range(1, 9))
    assert p["total"] == len(p["milestones"]) == sum(w["total"] for w in p["weeks"])
    assert [w["status"] for w in p["weeks"]][:3] == ["available", "current", "upcoming"]


def test_milestones_are_skills_not_content_views_or_counts():
    labels = [m["label"] for m in build()["milestones"]]
    assert "Built a balanced meal from the dining menu" in labels
    assert "Planned meals for the week" in labels
    assert not any(l.startswith(("Watched", "Logged ", "Moved")) for l in labels)
    behaviors = {m["behavior"] for m in build()["milestones"]}
    assert behaviors <= {"assessment", "practice", "apply", "reflect", "focus_area"}


def test_recall_check_ins_sit_in_weeks_1_4_and_8():
    p = build(assessments=[{"assessment_type": "baseline", "created_at": "2026-09-05T00:00:00+00:00"}])
    recall = {m["id"]: m for m in p["milestones"] if m["behavior"] == "assessment"}
    assert set(recall) == {"recall_1", "recall_4", "recall_8"}
    assert recall["recall_1"]["achieved"] and not recall["recall_4"]["achieved"]


def test_program_progress_marks_milestones_done():
    p = build(done_steps={"1:do_it"}, games_done={"g2"})
    got = {m["id"]: m["achieved"] for m in p["milestones"]}
    assert got["w1_do_it"] and got["w2_practice"] and not got["w1_reflect"]


def test_focus_milestone_counts_this_weeks_meals_with_the_focus_food():
    # Week 2 runs Sep 8-14; one whole-grain meal in week 1 doesn't count toward it.
    p = build(GRAINS, meals=[meal(3, ["whole_grains"]), meal(9, ["whole_grains"]), meal(10, ["vegetables"])])
    w2 = next(m for m in p["milestones"] if m["id"] == "w2_focus")
    assert (w2["label"], w2["progress"]["current"], w2["achieved"]) == ("Whole grains in 3 meals this week", 1, False)
    assert not any(m["id"] == "w3_focus" for m in p["milestones"])  # upcoming week: not yet


def test_message_references_the_goal_and_only_logged_behaviour():
    assert build(GRAINS)["message"] is None  # nothing logged this week, nothing claimed
    p = build(GRAINS, meals=[meal(8, ["whole_grains"]), meal(9, ["whole_grains", "dairy"]), meal(9, ["fruit"])])
    assert p["message"] == "You set a goal: “Brown rice at lunch”. That's your 2nd meal with whole grains this week!"
    assert build()["message"] is None  # no focus area chosen


def test_moderation_areas_count_logging_days():
    sodium = {"focus_area": "sodium", "focus_areas": ["sodium"]}
    p = build(sodium, meals=[meal(8), meal(9), meal(9, skipped=True)])
    w2 = next(m for m in p["milestones"] if m["id"] == "w2_focus")
    assert (w2["label"], w2["progress"]["current"]) == ("Tracked meals on 4 days this week", 2)
    assert "logged meals on 2 days this week" in p["message"]


# ---- Daily rings -------------------------------------------------------
def test_daily_ring_counts_todays_logs_only(freeze_now):
    # Pin "today" (study TZ) to 2026-09-29. 15:00 UTC = 10:00 CDT — well
    # inside the Chicago day. Every log in this test is at 09:00 UTC
    # (04:00 CDT) or later, so study-TZ keying matches UTC-slicing.
    freeze_now(datetime(2026, 9, 29, 15, 0, tzinfo=timezone.utc))
    profile = {"plans": {
        "food": [{"start_date": "2026-09-29", "enabled": True, "target": 2, "category": "vegetables"}],
        "move": [{"start_date": "2026-09-29", "enabled": True, "target": 30, "category": None}],
    }}
    logs = {
        "food": [{"id": "a", "created_at": "2026-09-29T09:00:00+00:00", "categories": ["vegetables"]},
                 {"id": "b", "created_at": "2026-09-28T09:00:00+00:00", "categories": ["vegetables"]}],
        "move": [{"id": "c", "created_at": "2026-09-29T10:00:00+00:00", "minutes": 20},
                 {"id": "d", "created_at": "2026-09-29T11:00:00+00:00", "minutes": 15}],
        "rest": [],
    }
    snap = daily_goals.build_snapshot(profile, logs)
    today = {g["domain"]: g for g in snap["days"][-1]["goals"]}
    # Eat ring is binary: one meal today closes it. Yesterday's meal does not.
    assert today["food"]["value"] == 1 and today["food"]["complete"]
    assert today["food"]["target"] == 1  # always 1 regardless of what's stored
    assert today["move"]["value"] == 35 and today["move"]["complete"] and today["move"]["ratio"] == 1


def test_week_move_total_counts_all_logged_minutes_in_window(freeze_now):
    freeze_now(datetime(2026, 9, 29, 15, 0, tzinfo=timezone.utc))
    profile = {"plans": {}}  # no Move goal: still counted
    logs = {"food": [], "rest": [], "move": [
        {"id": "a", "created_at": "2026-09-23T09:00:00+00:00", "minutes": 20},  # first day of window
        {"id": "b", "created_at": "2026-09-29T09:00:00+00:00", "minutes": 45},
        {"id": "c", "created_at": "2026-09-22T09:00:00+00:00", "minutes": 90},  # 8 days ago: out
        {"id": "d", "created_at": "2026-09-28T09:00:00+00:00", "minutes": 60, "simulated": True},
    ]}
    week = daily_goals.build_snapshot(profile, logs)["week"]
    # Movement total unchanged; snapshot now also carries per-domain
    # weekly day counts so Today, Future Me and Progress all read the
    # same numbers from one place. Two distinct days have real logs
    # (2026-09-23 and 2026-09-29); the simulated entry on 09-28 and the
    # out-of-window one on 09-22 don't count.
    assert week == {
        "move_minutes": 65,
        "move_reference_minutes": 150,
        "eat_days": 0,
        "move_days": 2,
        "rest_days": 0,
        "any_days": 2,
    }
