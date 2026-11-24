"""Unit tests for the two previously-unawarded gamification badges —
Consistent Logger and Balanced Week.

These exercise the pure criteria functions (`days_logged_streak`,
`balanced_meals_count`) directly, without a running database. Both are
intentionally decoupled from Motor so the badge definitions can be
reviewed in isolation.

    python -m pytest tests/test_badges.py -n 0
"""
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "llhs_unit_unused")
import server  # noqa: E402


def _meal(d: date, categories=None):
    """Minimal meal dict matching the shape stored in db.meals."""
    return {"created_at": d.isoformat() + "T12:00:00+00:00", "categories": list(categories or [])}


# ----------------------------------------------------------------------------
# Consistent Logger — 7 consecutive calendar days of logging, ending today.
# ----------------------------------------------------------------------------
def test_consistent_logger_awards_at_seven_consecutive_days():
    today = date(2026, 10, 6)
    meals = [_meal(today - timedelta(days=i)) for i in range(7)]
    assert server.days_logged_streak(meals, today) == 7
    assert server.days_logged_streak(meals, today) >= server.CONSISTENT_LOGGER_DAYS


def test_consistent_logger_withholds_before_seven_days():
    today = date(2026, 10, 6)
    meals = [_meal(today - timedelta(days=i)) for i in range(6)]
    assert server.days_logged_streak(meals, today) == 6
    assert server.days_logged_streak(meals, today) < server.CONSISTENT_LOGGER_DAYS


def test_consistent_logger_resets_on_gap_day():
    today = date(2026, 10, 6)
    # Logged today, yesterday, then nothing day-before-yesterday — streak = 2.
    meals = [_meal(today), _meal(today - timedelta(days=1))]
    meals += [_meal(today - timedelta(days=i)) for i in range(3, 10)]
    assert server.days_logged_streak(meals, today) == 2


def test_consistent_logger_counts_multiple_meals_per_day_once():
    today = date(2026, 10, 6)
    # Three meals today, three yesterday — streak is calendar-days, not count.
    meals = [_meal(today), _meal(today), _meal(today)]
    meals += [_meal(today - timedelta(days=1))] * 3
    assert server.days_logged_streak(meals, today) == 2


# ----------------------------------------------------------------------------
# Balanced Week — ≥5 "balanced" meals (≥2 core food categories each) in the
# trailing 7-day window ending today.
# ----------------------------------------------------------------------------
BALANCED = ["vegetables", "whole_grains"]
NOT_BALANCED = ["refined_grains_starchy"]


def test_balanced_week_awards_at_five_balanced_meals_in_window():
    today = date(2026, 10, 6)
    meals = [_meal(today - timedelta(days=i), BALANCED) for i in range(5)]
    assert server.balanced_meals_count(meals, today) == 5
    assert server.balanced_meals_count(meals, today) >= server.BALANCED_WEEK_MIN_MEALS


def test_balanced_week_withholds_below_five_balanced_meals():
    today = date(2026, 10, 6)
    meals = [_meal(today - timedelta(days=i), BALANCED) for i in range(4)]
    meals.append(_meal(today - timedelta(days=5), NOT_BALANCED))
    assert server.balanced_meals_count(meals, today) == 4
    assert server.balanced_meals_count(meals, today) < server.BALANCED_WEEK_MIN_MEALS


def test_balanced_week_ignores_meals_older_than_seven_days():
    today = date(2026, 10, 6)
    # Four balanced meals in window, three balanced meals older than window.
    meals = [_meal(today - timedelta(days=i), BALANCED) for i in range(4)]
    meals += [_meal(today - timedelta(days=i), BALANCED) for i in (8, 9, 10)]
    assert server.balanced_meals_count(meals, today) == 4


def test_balanced_week_ignores_single_category_meals():
    today = date(2026, 10, 6)
    # One category each — not balanced by the ≥2-kinds predicate.
    meals = [_meal(today - timedelta(days=i), ["vegetables"]) for i in range(7)]
    assert server.balanced_meals_count(meals, today) == 0


def test_balanced_week_counts_meals_logged_today():
    today = date(2026, 10, 6)
    # Four earlier balanced meals plus a fifth logged today → threshold hit.
    meals = [_meal(today - timedelta(days=i), BALANCED) for i in range(1, 5)]
    meals.append(_meal(today, BALANCED))
    assert server.balanced_meals_count(meals, today) >= server.BALANCED_WEEK_MIN_MEALS


# ----------------------------------------------------------------------------
# Badge definitions remain the authoritative list — the two previously
# unawarded names must still be present (regression guard against them being
# accidentally renamed or dropped as part of future refactors).
# ----------------------------------------------------------------------------
def test_both_logging_badges_are_still_in_badge_defs():
    assert "Consistent Logger" in server.BADGE_DEFS
    assert "Balanced Week" in server.BADGE_DEFS
