"""Lab Test Wing goal — the Oct-27 live session's shared progress bar.

Phase 1 of the Wings rebuild originally created the Lab Test Wing with
``participation_days`` / target 10. That doesn't move during a 30-minute
rehearsal (one tester logging anything = 1 day = 10% of the bar), so the
group never sees a shared win in the time they're together.

This file pins down the new choice:

* **Metric**: ``balanced_meals``. One tap per lab tester = one meal with
  two+ core categories = +1 on the bar.
* **Target**: 6. With 5-6 testers each logging one quick meal in the
  session, the bar reliably hits 100% and triggers the fixed Wing
  celebration — the whole point of the exercise.
* **Config-driven**: ``LAB_TEST_WING_GOAL_METRIC`` /
  ``LAB_TEST_WING_GOAL_TARGET`` env vars override without a code change.
* Other Wings keep their own goal — the lab goal lives only on the
  "Lab Test Wing" row.
"""
from __future__ import annotations

import asyncio

import pytest


# --- 1. Config helper ------------------------------------------------------

def test_lab_test_wing_goal_defaults_to_balanced_meals_target_6(monkeypatch):
    monkeypatch.delenv("LAB_TEST_WING_GOAL_METRIC", raising=False)
    monkeypatch.delenv("LAB_TEST_WING_GOAL_TARGET", raising=False)
    import server
    metric, target = server._lab_test_wing_goal()
    assert metric == "balanced_meals"
    assert target == 6


def test_lab_test_wing_goal_env_override(monkeypatch):
    import server
    monkeypatch.setenv("LAB_TEST_WING_GOAL_METRIC", "activity_minutes")
    monkeypatch.setenv("LAB_TEST_WING_GOAL_TARGET", "60")
    metric, target = server._lab_test_wing_goal()
    assert metric == "activity_minutes"
    assert target == 60


def test_lab_test_wing_goal_invalid_env_falls_back(monkeypatch):
    """Bad env values can't crash the "ensure wing" endpoint during the
    live test — they just revert to the default."""
    import server
    monkeypatch.setenv("LAB_TEST_WING_GOAL_METRIC", "nonsense")
    monkeypatch.setenv("LAB_TEST_WING_GOAL_TARGET", "not-a-number")
    metric, target = server._lab_test_wing_goal()
    assert metric == "balanced_meals"
    assert target == 6


def test_lab_test_wing_goal_zero_or_negative_falls_back(monkeypatch):
    import server
    monkeypatch.setenv("LAB_TEST_WING_GOAL_TARGET", "0")
    _, target = server._lab_test_wing_goal()
    assert target == 6


# --- 2. 6 lab users each logging a balanced meal reaches 100% ---------------

def test_six_balanced_meals_fill_the_lab_wing_bar(monkeypatch):
    """`compute_wing_progress` with balanced_meals / 6 and 6 meals from
    distinct members (each with 2+ core categories so
    `meal_has_core_categories` fires) must land on current=6, achieved=True."""
    import server

    # Lab Test Wing with 6 members and the new goal.
    wing = {
        "id": "wing-lab", "name": server.LAB_TEST_WING_NAME,
        "member_ids": [f"u{i}" for i in range(1, 7)],
        "goal_metric": "balanced_meals", "goal_target": 6,
        "season_start": "2026-10-01T00:00:00+00:00",
    }
    # One balanced meal per member: vegetables + whole_grains is 2 core
    # categories, enough to trip meal_has_core_categories(min_kinds=2).
    meals = [
        {"id": f"m{i}", "user_id": f"u{i}",
         "created_at": "2026-10-27T18:00:00+00:00",
         "categories": ["vegetables", "whole_grains"]}
        for i in range(1, 7)
    ]

    # Minimal fake collections — only the two attributes compute_wing_progress
    # touches on `db.meals` and `db.activities`.
    class _Cursor:
        def __init__(self, rows): self._rows = rows
        async def to_list(self, _n): return list(self._rows)

    class _Coll:
        def __init__(self, rows): self._rows = rows
        def find(self, *_a, **_k): return _Cursor(self._rows)

    class _FakeDB: pass
    fake = _FakeDB()
    fake.meals = _Coll(meals)
    fake.activities = _Coll([])
    monkeypatch.setattr(server, "db", fake, raising=False)
    result = asyncio.run(server.compute_wing_progress(wing))
    assert result == {"current": 6, "target": 6, "achieved": True}


def test_five_balanced_meals_do_not_cross_the_line(monkeypatch):
    """One short of target → not yet achieved. Keeps the celebration
    deterministic (bar fills at exactly 6, not 5-ish)."""
    import server
    wing = {
        "id": "wing-lab", "name": server.LAB_TEST_WING_NAME,
        "member_ids": [f"u{i}" for i in range(1, 7)],
        "goal_metric": "balanced_meals", "goal_target": 6,
        "season_start": "2026-10-01T00:00:00+00:00",
    }
    meals = [
        {"id": f"m{i}", "user_id": f"u{i}",
         "created_at": "2026-10-27T18:00:00+00:00",
         "categories": ["vegetables", "whole_grains"]}
        for i in range(1, 6)  # only 5
    ]
    class _Cursor:
        def __init__(self, rows): self._rows = rows
        async def to_list(self, _n): return list(self._rows)
    class _Coll:
        def __init__(self, rows): self._rows = rows
        def find(self, *_a, **_k): return _Cursor(self._rows)
    class _FakeDB: pass
    fake = _FakeDB(); fake.meals = _Coll(meals); fake.activities = _Coll([])
    monkeypatch.setattr(server, "db", fake, raising=False)
    result = asyncio.run(server.compute_wing_progress(wing))
    assert result["current"] == 5 and result["achieved"] is False


def test_unbalanced_meals_do_not_count(monkeypatch):
    """`meal_has_core_categories(min_kinds=2)` requires 2+ core categories.
    A single-category meal doesn't move the bar, so the lab-session goal
    stays an honest "balanced plate" count."""
    import server
    wing = {
        "id": "wing-lab", "name": server.LAB_TEST_WING_NAME,
        "member_ids": [f"u{i}" for i in range(1, 7)],
        "goal_metric": "balanced_meals", "goal_target": 6,
        "season_start": "2026-10-01T00:00:00+00:00",
    }
    meals = [
        {"id": f"m{i}", "user_id": f"u{i}",
         "created_at": "2026-10-27T18:00:00+00:00",
         "categories": ["vegetables"]}
        for i in range(1, 7)
    ]
    class _Cursor:
        def __init__(self, rows): self._rows = rows
        async def to_list(self, _n): return list(self._rows)
    class _Coll:
        def __init__(self, rows): self._rows = rows
        def find(self, *_a, **_k): return _Cursor(self._rows)
    class _FakeDB: pass
    fake = _FakeDB(); fake.meals = _Coll(meals); fake.activities = _Coll([])
    monkeypatch.setattr(server, "db", fake, raising=False)
    result = asyncio.run(server.compute_wing_progress(wing))
    assert result["current"] == 0 and result["achieved"] is False
