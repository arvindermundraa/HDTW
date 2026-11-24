"""Week 5 feedback engine — qualitative labels only, cautious wording,
PROVISIONAL thresholds. Nutrition team 2026-11-06, item 4 ("Week 5
feedback")."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "llhs_unit_unused")

import week5_feedback as w5  # noqa: E402
import server  # noqa: E402

COMPONENTS = server.HEI2020_BY_ID
SODIUM_AREA = ["sodium"]
FATS_AREA = ["fatty_acids", "saturated_fats"]


def test_making_progress_when_ratio_rises_by_at_least_the_threshold():
    # Sodium max is 10; +1.1 points = 0.11 of the max = past the 0.10 threshold.
    base = {"sodium": 2.0}
    week4 = {"sodium": 3.1}
    label = w5.area_label(base, week4, SODIUM_AREA, COMPONENTS)
    assert label == w5.LABEL_PROGRESS


def test_area_to_revisit_when_ratio_falls_by_at_least_the_threshold():
    base = {"sodium": 5.0}
    week4 = {"sodium": 3.9}  # -0.11 of the max -> past the drop threshold
    label = w5.area_label(base, week4, SODIUM_AREA, COMPONENTS)
    assert label == w5.LABEL_REVISIT


def test_similar_when_the_change_is_below_the_threshold_in_either_direction():
    base = {"sodium": 5.0}
    for week4_val in (4.5, 5.0, 5.4):  # within ±0.10 of baseline
        label = w5.area_label(base, {"sodium": week4_val}, SODIUM_AREA, COMPONENTS)
        assert label == w5.LABEL_SIMILAR, (week4_val, label)


def test_combined_areas_use_the_summed_ratio_not_a_per_component_label():
    # Fats max is 10+10=20. Baseline: 10 points -> 0.50.
    base = {"fatty_acids": 5.0, "saturated_fats": 5.0}
    # Rise by 3 points on one component = +0.15 of the area's max.
    better = {"fatty_acids": 8.0, "saturated_fats": 5.0}
    assert w5.area_label(base, better, FATS_AREA, COMPONENTS) == w5.LABEL_PROGRESS


def test_missing_component_scores_fall_back_to_similar_rather_than_a_bogus_delta():
    base = {"sodium": 5.0}
    assert w5.area_label(base, {}, SODIUM_AREA, COMPONENTS) == w5.LABEL_SIMILAR
    assert w5.area_label({}, {"sodium": 5.0}, SODIUM_AREA, COMPONENTS) == w5.LABEL_SIMILAR


def test_area_feedback_payload_carries_cautious_prose_and_the_provisional_flag():
    base = {"sodium": 2.0}
    week4 = {"sodium": 4.0}
    out = w5.area_feedback(base, week4, SODIUM_AREA, "Sodium", COMPONENTS)
    assert out["label"] == w5.LABEL_PROGRESS
    assert out["thresholds_provisional"] is True
    # Uses the team's "Based on the days you reported…" / "Your recent meals
    # suggest…" style so no definitive statement about usual diet is made.
    assert "Based on the days you reported" in out["message"]
    assert "usual" not in out["message"].lower()  # no claim about "usual" intake
    assert "Sodium" in out["message"]


def test_prose_is_numeric_free():
    base = {"sodium": 2.0}
    for week4_val in (2.0, 4.0, 0.5):  # similar / progress / revisit
        out = w5.area_feedback(base, {"sodium": week4_val}, SODIUM_AREA, "Sodium", COMPONENTS)
        # No digits anywhere in the prose — the dashboard never shows a
        # numerical change (nutrition team 2026-11-06, item 4).
        for ch in out["message"]:
            assert not ch.isdigit(), out["message"]


def test_reflection_choice_includes_the_current_area_in_both_options():
    out = w5.reflection_choice_for("Sodium")
    labels = [o["label"] for o in out["options"]]
    assert any("Sodium" in lbl for lbl in labels)
    # Two options: continue the same area; choose a new one.
    assert sorted(o["id"] for o in out["options"]) == sorted([w5.CONTINUE, w5.CHOOSE_NEW])


def test_thresholds_are_overridable_per_call_for_sensitivity_analysis():
    base = {"sodium": 5.0}
    week4 = {"sodium": 5.6}  # +0.06 of max — below the 0.10 default
    assert w5.area_label(base, week4, SODIUM_AREA, COMPONENTS) == w5.LABEL_SIMILAR
    # With a stricter threshold (0.05) the same change crosses into progress.
    assert w5.area_label(base, week4, SODIUM_AREA, COMPONENTS, progress_min_delta=0.05) == w5.LABEL_PROGRESS
