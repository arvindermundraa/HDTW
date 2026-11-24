"""Every feature agrees that "today" is a study-TZ day, not UTC.

Two late-evening cases every feature must pass:

- 2026-10-11 (Sun) 20:00 Chicago = 2026-10-12 (Mon) 01:00 UTC
  → an entry logged "tonight" is still on Sunday's rings / streak / cohort
    week / My Path, not Monday's.
- 2026-10-10 (Sat) 23:30 Chicago = 2026-10-11 (Sun) 05:30 UTC
  → a late-night Saturday log counts in the right week, with Saturday on
    the 7-day strip, not Sunday.

Timestamps on disk stay in UTC. Only the day/week boundary moves. The two
helpers under test are `study_today()` and `study_week_window()`.

    python -m pytest tests/test_study_time.py -n 0
"""
from __future__ import annotations

import os
import sys
from datetime import date, datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "llhs_unit_unused")
import server  # noqa: E402
import avatar  # noqa: E402
import daily_goals  # noqa: E402
import personal_path  # noqa: E402
import study_time  # noqa: E402


# ---- The two moments every test freezes to ----------------------------------
#
# Keep CDT in mind: America/Chicago is UTC-5 (CDT) until 2026-11-01 02:00 CDT.
# Both moments below are inside CDT, so UTC - 5h gives the Chicago wall clock.
EIGHT_PM_SUN = datetime(2026, 10, 12, 1, 0, 0, tzinfo=timezone.utc)   # 20:00 Sun Chicago
ELEVEN_THIRTY_PM_SAT = datetime(2026, 10, 11, 4, 30, 0, tzinfo=timezone.utc)  # 23:30 Sat Chicago


def _utc(y, mo, d, h, mi=0):
    return datetime(y, mo, d, h, mi, 0, tzinfo=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


# ---- 1. study_today() + study_week_window() --------------------------------
def test_study_today_handles_both_late_evening_cases(monkeypatch):
    monkeypatch.setattr(study_time, "_now_utc", lambda: EIGHT_PM_SUN)
    assert study_time.study_today() == date(2026, 10, 11), "8 PM Sunday Chicago"

    monkeypatch.setattr(study_time, "_now_utc", lambda: ELEVEN_THIRTY_PM_SAT)
    assert study_time.study_today() == date(2026, 10, 10), "11:30 PM Saturday Chicago"


def test_study_week_window_is_rolling_seven_days(monkeypatch):
    monkeypatch.setattr(study_time, "_now_utc", lambda: EIGHT_PM_SUN)
    first, last = study_time.study_week_window(7)
    assert last == date(2026, 10, 11)
    assert first == date(2026, 10, 5)
    assert (last - first).days == 6


def test_study_day_key_buckets_late_night_logs_into_the_right_day():
    # 11:30 PM Sat Chicago → 05:30 UTC Sun → should bucket as 2026-10-10.
    assert study_time.study_day_key(_iso(ELEVEN_THIRTY_PM_SAT)) == "2026-10-10"
    # 8 PM Sun Chicago → 01:00 UTC Mon → should bucket as 2026-10-11.
    assert study_time.study_day_key(_iso(EIGHT_PM_SUN)) == "2026-10-11"


# ---- 2. Avatar mood — day belongs to Chicago, not UTC ----------------------
def test_avatar_mood_counts_a_late_night_sat_log_on_saturday():
    sat_night = _iso(ELEVEN_THIRTY_PM_SAT)
    logs = {
        "food": [{"id": "m1", "created_at": sat_night, "confirmed": True, "categories": ["vegetables"]}],
        "move": [{"id": "a1", "created_at": sat_night, "minutes": 20}],
        "rest": [{"id": "s1", "created_at": sat_night, "hours": 7.5, "source": "manual"}],
    }
    mood = avatar.daily_mood([], logs, "2026-10-10")  # Chicago Saturday
    assert mood["props"] == ["salad", "sneakers", "rested"], (
        "a 23:30 Chicago log must count on Saturday (its study-TZ day), not Sunday"
    )


def test_avatar_mood_does_not_bleed_a_sat_night_log_into_sunday():
    sat_night = _iso(ELEVEN_THIRTY_PM_SAT)
    logs = {
        "food": [{"id": "m1", "created_at": sat_night, "confirmed": True, "categories": ["vegetables"]}],
        "move": [], "rest": [],
    }
    sun_mood = avatar.daily_mood([], logs, "2026-10-11")  # Chicago Sunday
    assert sun_mood["props"] == []


# ---- 3. Streaks + Consistent Logger badge --------------------------------
def test_streak_helpers_bucket_logs_in_study_tz(monkeypatch):
    monkeypatch.setattr(study_time, "_now_utc", lambda: EIGHT_PM_SUN)
    # Seven Chicago days, each with a late-evening (23:30 CDT) meal — stored
    # in UTC as 2026-10-06..2026-10-12 04:30. Study-TZ keying puts them on
    # 2026-10-05..2026-10-11, a clean 7-day run ending today (2026-10-11).
    # Plus one noon-today meal so today's bucket is populated regardless of
    # keying — otherwise today's 23:30 log would be in the future.
    meals = [
        *({"id": f"m{i}", "created_at": _iso(_utc(2026, 10, 6 + i, 4, 30))} for i in range(6)),
        {"id": "today-noon", "created_at": _iso(_utc(2026, 10, 11, 17, 0))},  # 12:00 CDT Sun
    ]
    assert server.days_logged_streak(meals, study_time.study_today()) == 7, (
        "UTC-slicing would miss 2026-10-05 Chicago (keyed as 10-06 under UTC); "
        "study-TZ keying gives a full 7-day run."
    )


def test_balanced_week_counts_late_night_sat_log(monkeypatch):
    monkeypatch.setattr(study_time, "_now_utc", lambda: EIGHT_PM_SUN)
    # One late-night Saturday meal with ≥2 core categories: Chicago-Saturday is
    # inside the 7-day window ending Sunday 2026-10-11.
    meals = [{
        "id": "m1",
        "created_at": _iso(ELEVEN_THIRTY_PM_SAT),
        "categories": ["vegetables", "whole_grains"],
    }]
    assert server.balanced_meals_count(meals, study_time.study_today(), window_days=7) == 1


# ---- 4. Rings / daily goals / weekly recap ---------------------------------
def _single_food_plan():
    # A simple always-on plan starting last week so every day in the strip picks it up.
    return {"start_date": "2026-10-01", "enabled": True, "target": 1, "category": "vegetables"}


def test_rings_strip_buckets_late_sat_log_on_saturday(monkeypatch):
    monkeypatch.setattr(study_time, "_now_utc", lambda: EIGHT_PM_SUN)
    profile = {"plans": {"food": [_single_food_plan()]}}
    sat_night = _iso(ELEVEN_THIRTY_PM_SAT)
    logs = {
        "food": [{"id": "m1", "created_at": sat_night, "confirmed": True,
                  "categories": ["vegetables"]}],
        "move": [], "rest": [],
    }
    snap = daily_goals.build_snapshot(profile, logs)
    saturday = next(d for d in snap["days"] if d["date"] == "2026-10-10")
    sunday = next(d for d in snap["days"] if d["date"] == "2026-10-11")
    assert saturday["goals"] and saturday["goals"][0]["complete"], (
        "the 23:30 Chicago meal should close Saturday's Eat ring, not Sunday's"
    )
    assert all(not g["complete"] for g in sunday["goals"])


def test_rings_today_is_study_today(monkeypatch):
    monkeypatch.setattr(study_time, "_now_utc", lambda: EIGHT_PM_SUN)
    snap = daily_goals.build_snapshot({"plans": {}}, {"food": [], "move": [], "rest": []})
    assert snap["today"] == "2026-10-11"
    assert snap["timezone"] == "America/Chicago"


# ---- 5. Daily-goal versioning: "start tomorrow" uses study_today() + 1 ----
def test_set_goal_second_version_starts_study_tomorrow_not_phone_tomorrow(monkeypatch):
    # 11:30 PM Sat Chicago. For a phone in UTC, "today" would be Sunday
    # already and "tomorrow" Monday — but the study-TZ answer is Sunday.
    monkeypatch.setattr(study_time, "_now_utc", lambda: ELEVEN_THIRTY_PM_SAT)
    assert study_time.study_today() == date(2026, 10, 10)
    tomorrow = study_time.study_today() + timedelta(days=1)
    assert tomorrow.isoformat() == "2026-10-11"


# ---- 6. Cohort week — rolling 7 study-days -------------------------------
def test_study_week_window_bounds_match_late_night_saturday_log(monkeypatch):
    monkeypatch.setattr(study_time, "_now_utc", lambda: EIGHT_PM_SUN)
    first, last = study_time.study_week_window(7)
    assert first.isoformat() == "2026-10-05" and last.isoformat() == "2026-10-11"
    # The Saturday 23:30 log sits inside this window.
    assert first.isoformat() <= study_time.study_day_key(_iso(ELEVEN_THIRTY_PM_SAT)) <= last.isoformat()


def test_study_day_start_utc_iso_is_chicago_midnight(monkeypatch):
    monkeypatch.setattr(study_time, "_now_utc", lambda: EIGHT_PM_SUN)
    start = study_time.study_day_start_utc_iso()  # defaults to study_today()
    # 2026-10-11 00:00 Chicago (CDT, UTC-5) = 2026-10-11 05:00 UTC.
    assert start.startswith("2026-10-11T05:00:00")


# ---- 7. My Path — distinct days keyed by study TZ -------------------------
def test_personal_path_distinct_days_are_study_tz():
    # Three ISO stamps: two land on 2026-10-10 Chicago (one UTC, one 23:30 CDT
    # that slips into UTC-Sunday), one lands on 2026-10-11 Chicago. UTC-slicing
    # would see three distinct days; study-TZ keying sees two.
    stamps = [
        _iso(_utc(2026, 10, 10, 12, 0)),        # 07:00 CDT Sat
        _iso(ELEVEN_THIRTY_PM_SAT),            # 23:30 CDT Sat (05:30 UTC Sun)
        _iso(_utc(2026, 10, 11, 14, 0)),        # 09:00 CDT Sun
    ]
    assert personal_path._distinct_days(stamps) == 2


# ---- 8. Check-in countdown — study-TZ calendar days -----------------------
def test_checkin_countdown_is_calendar_days_in_study_tz(monkeypatch):
    # Now = 2026-10-12 01:00 UTC (20:00 CDT Sun Oct 11). The baseline was
    # recorded earlier this morning: 2026-10-11 05:00 UTC = 00:00 CDT Sun Oct 11.
    # Next check-in in 14 days = 2026-10-25 05:00 UTC = 00:00 CDT Sat Oct 25.
    # Calendar days (study TZ): Oct 25 - Oct 11 = 14.
    # Moment-delta would give (13 days, 4 hours).days = 13 — a day short.
    monkeypatch.setattr(study_time, "_now_utc", lambda: EIGHT_PM_SUN)
    baseline_recorded = _utc(2026, 10, 11, 5, 0)
    next_due = baseline_recorded + timedelta(days=14)
    next_due_study_date = study_time.study_day_key(next_due)
    days_until = (date.fromisoformat(next_due_study_date) - study_time.study_today()).days
    assert days_until == 14, (
        "Calendar-days-in-study-TZ should read 14 — moment-delta `.days` would read 13."
    )
    # Sanity: the moment-delta version would have been off.
    moment_delta_days = (next_due - EIGHT_PM_SUN).days
    assert moment_delta_days == 13
