"""Unit tests for the 5:2 weekday/weekend weighting + sensitivity analysis
+ fallback branches. Nutrition team confirmed on 2026-11-06 (Scoring
and Feedback Q1) and the day-classification rules on 2026-11-12."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "llhs_unit_unused")

import recall_weighting as rw  # noqa: E402
import hei2020_scoring  # noqa: E402

COLS = hei2020_scoring.TOTALS_NUMERIC_COLUMNS
BASE = {c: 0.0 for c in COLS}


def _recall(kcal=2000.0, **overrides):
    return {**BASE, "KCAL": kcal, **overrides}


# --- day classification ------------------------------------------------------


def test_intake_start_datetime_wins_over_reporting_and_finished():
    rec = {
        "IntakeStartDateTime": "10/17/2026",      # Saturday
        "ReportingDate": "10/20/2026",            # (earlier source would give Monday)
        "finished_at": "2026-10-21T04:00:00+00:00",
    }
    c = rw.classify_recall_day(rec)
    assert c["eating_date"].isoformat() == "2026-10-17"
    assert c["day_type"] == "weekend"
    assert c["source"] == rw.DAY_SOURCE_INTAKE


def test_reporting_date_minus_one_day_rule():
    # ReportingDate is Tuesday 10/20 -> eating date was Monday 10/19.
    rec = {"ReportingDate": "10/20/2026"}
    c = rw.classify_recall_day(rec)
    assert c["eating_date"].isoformat() == "2026-10-19"
    assert c["day_type"] == "weekday"
    assert c["source"] == rw.DAY_SOURCE_REPORTING_MINUS_ONE


def test_finished_at_converts_to_study_tz_then_minus_one():
    # 2026-10-21 04:00 UTC is 2026-10-20 23:00 America/Chicago (CDT -5).
    # Eating date = local date (2026-10-20) - 1 day = 2026-10-19 (Monday).
    rec = {"finished_at": "2026-10-21T04:00:00+00:00"}
    c = rw.classify_recall_day(rec)
    assert c["eating_date"].isoformat() == "2026-10-19"
    assert c["day_type"] == "weekday"
    assert c["source"] == rw.DAY_SOURCE_FINISHED_MINUS_ONE


def test_finished_at_late_night_near_midnight_stays_in_the_right_day():
    # 2026-10-20 03:59 UTC = 2026-10-19 22:59 America/Chicago. Local date
    # is still Sunday (10/19); eating date = Saturday 10/18.
    rec = {"finished_at": "2026-10-20T03:59:00+00:00"}
    c = rw.classify_recall_day(rec)
    assert c["eating_date"].isoformat() == "2026-10-18"
    assert c["day_type"] == "weekend"


def test_unknown_source_when_nothing_is_dated():
    c = rw.classify_recall_day({})
    assert c["eating_date"] is None and c["day_type"] is None
    assert c["source"] == rw.DAY_SOURCE_UNKNOWN


# --- weighting: clean 5:2 ----------------------------------------------------


def test_one_weekday_and_one_weekend_runs_weighted_5_2():
    # Weekday recall has 1000 mg sodium; weekend recall has 5000 mg sodium.
    # Weighted sum: 5*1000 + 2*5000 = 15000 mg over 7 person-days of intake.
    wkday = _recall(SODI=1000, IntakeStartDateTime="10/19/2026")  # Monday
    wkend = _recall(SODI=5000, IntakeStartDateTime="10/17/2026")  # Saturday
    out = rw.score_with_weighting([wkday, wkend])
    assert out["primary"]["method"] == rw.METHOD_WEIGHTED
    assert out["primary"]["weighting_fallback"] is None
    assert out["primary"]["scored"]["summed_inputs"]["SODI"] == 15000.0
    # Sensitivity = 1:1 pooling -> 6000 mg sodium.
    assert out["sensitivity"]["method"] == rw.METHOD_EQUAL
    assert out["sensitivity"]["scored"]["summed_inputs"]["SODI"] == 6000.0


def test_weighted_hei_total_differs_from_equal_pooling_when_days_differ():
    wkday = _recall(F_TOTAL=0, SODI=800, IntakeStartDateTime="10/19/2026")
    wkend = _recall(F_TOTAL=4, SODI=4000, IntakeStartDateTime="10/17/2026")
    out = rw.score_with_weighting([wkday, wkend])
    assert out["primary"]["scored"]["total_score"] != out["sensitivity"]["scored"]["total_score"]


# --- fallback branches -------------------------------------------------------


def test_two_weekday_recalls_fall_back_with_a_clear_reason():
    r1 = _recall(SODI=1000, IntakeStartDateTime="10/19/2026")  # Monday
    r2 = _recall(SODI=5000, IntakeStartDateTime="10/20/2026")  # Tuesday
    out = rw.score_with_weighting([r1, r2])
    assert out["primary"]["method"] == rw.METHOD_EQUAL
    assert out["primary"]["weighting_fallback"] == rw.FALLBACK_REASON_TWO_WEEKDAYS
    # Primary == sensitivity under equal-day pooling.
    assert out["primary"]["scored"]["total_score"] == out["sensitivity"]["scored"]["total_score"]


def test_two_weekend_recalls_fall_back_with_a_clear_reason():
    r1 = _recall(IntakeStartDateTime="10/17/2026")  # Saturday
    r2 = _recall(IntakeStartDateTime="10/18/2026")  # Sunday
    out = rw.score_with_weighting([r1, r2])
    assert out["primary"]["weighting_fallback"] == rw.FALLBACK_REASON_TWO_WEEKENDS


def test_a_single_recall_falls_back():
    r = _recall(IntakeStartDateTime="10/19/2026")
    out = rw.score_with_weighting([r])
    assert out["primary"]["weighting_fallback"] == rw.FALLBACK_REASON_INSUFFICIENT_RECALLS


def test_any_undated_recall_blocks_weighting():
    r1 = _recall(IntakeStartDateTime="10/19/2026")  # Monday
    r2 = _recall()  # no date at all
    out = rw.score_with_weighting([r1, r2])
    assert out["primary"]["weighting_fallback"] == rw.FALLBACK_REASON_UNDATED


# --- classifications stored for audit ----------------------------------------


def test_classifications_are_serializable_and_record_source():
    r1 = _recall(IntakeStartDateTime="10/19/2026")  # Monday
    r2 = _recall(ReportingDate="10/20/2026")        # -> Monday
    out = rw.score_with_weighting([r1, r2])
    cls = out["classifications"]
    assert len(cls) == 2
    assert cls[0]["source"] == rw.DAY_SOURCE_INTAKE
    assert cls[0]["eating_date"] == "2026-10-19"
    assert cls[1]["source"] == rw.DAY_SOURCE_REPORTING_MINUS_ONE
    assert cls[1]["eating_date"] == "2026-10-19"
    # Both Mondays -> two weekdays -> fallback for primary.
    assert out["primary"]["weighting_fallback"] == rw.FALLBACK_REASON_TWO_WEEKDAYS
