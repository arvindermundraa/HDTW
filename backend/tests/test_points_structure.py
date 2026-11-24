"""Points structure (nutrition team 2026-11-06, item 4).

Every Week 1 and Week 2 step is mapped to one of four point values:

  10  — watching an educational or Youth Ambassador video.
  15  — reviewing feedback, or selecting a focus area.
  20  — completing interactive challenges and reflection activities
        (including the Week 2 scenarios).
  25  — setting goals or developing action plans (including the Week 2
        planning activity).

The mapping below is the full source of truth and is asserted against
``backend/content/weeks/weekN.json``. Points are awarded once per step
(enforced in ``server.py`` by the ``already`` flag check around
``award_points``); any points students earned before this PR are
preserved.
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

import weekly_workflow  # noqa: E402


POINTS_BY_CATEGORY = {
    "video": 10,
    "review_feedback_or_focus": 15,
    "interactive_challenge_or_reflection": 20,
    "goal_or_action_plan": 25,
}


# (week, step_id) -> category
MAPPING = {
    # --- Week 1 ---
    (1, "overview_video"): "video",
    (1, "feedback"): "review_feedback_or_focus",
    (1, "focus_selection"): "review_feedback_or_focus",
    (1, "mini_lecture"): "video",
    (1, "reflection"): "interactive_challenge_or_reflection",
    (1, "goal_and_plan"): "goal_or_action_plan",
    # --- Week 2 ---
    (2, "overview_video"): "video",
    (2, "scenarios"): "interactive_challenge_or_reflection",
    (2, "ambassador_video"): "video",
    (2, "planning"): "goal_or_action_plan",
    (2, "this_week_reviewed"): "review_feedback_or_focus",
}


@pytest.mark.parametrize("key,category", sorted(MAPPING.items()))
def test_every_step_has_the_points_value_the_team_assigned(key, category):
    week, step_id = key
    expected = POINTS_BY_CATEGORY[category]
    actual = weekly_workflow.step_points(week, step_id)
    assert actual == expected, (
        f"week {week} step {step_id!r} expected {expected} points "
        f"({category!r} per nutrition team 2026-11-06, item 4), got {actual}."
    )


def test_mapping_covers_every_step_defined_in_the_content_files():
    content_dir = Path(__file__).resolve().parent.parent / "content" / "weeks"
    mapped = {k for k in MAPPING}
    for path in content_dir.glob("week*.json"):
        data = json.loads(path.read_text())
        week = int(data["week"])
        steps = (data.get("steps") or {}).keys()
        for sid in steps:
            assert (week, sid) in mapped, (
                f"week {week} step {sid!r} exists in {path.name} but has no "
                "entry in the points-structure mapping; add one."
            )


def test_every_mapped_point_value_is_one_of_the_four_team_approved_values():
    allowed = set(POINTS_BY_CATEGORY.values())
    for key in MAPPING:
        week, step_id = key
        assert weekly_workflow.step_points(week, step_id) in allowed, (
            f"{key} has an off-structure point value."
        )
