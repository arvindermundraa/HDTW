"""Unit tests for backend/scripts/migrate_week1.py — the pilot migration
that pre-fills Week 1 workflow records for students who already finished
the equivalent flow under program.py.

These tests exercise the pure logic (``_collect_rows``, ``_summary``,
``_apply``) against a tiny in-memory DB. The CLI prompt and the dry-run
JSON artifact are only lightly covered — the harness that drives them
is a few lines of ``argparse`` + ``input()`` that doesn't carry the
risk the migration itself does.
"""
from __future__ import annotations

import asyncio
import copy
import importlib.util
import sys
from pathlib import Path

import pytest


BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

# Load the migration script by file path so renaming the enclosing
# folder doesn't force a dotted import rewrite here. The script is
# written as a module (functions + an __main__ guard), so importing
# like this is safe.
_spec = importlib.util.spec_from_file_location(
    "migrate_week1", BACKEND / "scripts" / "migrate_week1.py"
)
migrate_week1 = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(migrate_week1)  # type: ignore[union-attr]


# --- A minimal async DB double --------------------------------------------

class _Cursor:
    def __init__(self, docs):
        self._docs = [copy.deepcopy(d) for d in docs]
        self._i = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._i >= len(self._docs):
            raise StopAsyncIteration
        d = self._docs[self._i]
        self._i += 1
        return d


class _Coll:
    def __init__(self, docs=None):
        self.docs = list(docs or [])

    def find(self, _query=None, _projection=None):
        return _Cursor(self.docs)

    async def find_one(self, query, _projection=None):
        for d in self.docs:
            if all(d.get(k) == v for k, v in query.items()):
                return copy.deepcopy(d)
        return None

    async def update_one(self, query, update, upsert=False):
        for d in self.docs:
            if all(d.get(k) == v for k, v in query.items()):
                d.update(update.get("$set", {}))
                return
        if upsert:
            new = dict(query)
            new.update(update.get("$set", {}))
            new.update(update.get("$setOnInsert", {}))
            self.docs.append(new)


class _DB:
    def __init__(self, users, weekly_workflow=None):
        self.users = _Coll(users)
        self.weekly_workflow = _Coll(weekly_workflow or [])


# --- Fixtures --------------------------------------------------------------

ELIGIBLE_PILOT = {
    "id": "pilot-aaaa", "email": "alice@tamu.edu", "is_test_account": False,
    "focus_area": "sodium",
    "focus_goal": {"goal": "Lower-sodium snacks on busy afternoons.", "plan": "Pack fruit by Monday morning."},
}
NO_GOAL = {
    "id": "pilot-bbbb", "email": "bob@tamu.edu", "is_test_account": False,
    "focus_area": "sodium",
    "focus_goal": {"goal": "", "plan": ""},
}
NO_FOCUS = {
    "id": "pilot-cccc", "email": "carol@tamu.edu", "is_test_account": False,
}
TEST_ACCT = {
    "id": "pilot-dddd", "email": "demo@example.com", "is_test_account": True,
    "focus_area": "fruit",
    "focus_goal": {"goal": "Add fruit to breakfast.", "plan": "Keep bananas in the dorm."},
}


# --- Tests -----------------------------------------------------------------

def test_collect_rows_only_returns_eligible_users(monkeypatch):
    monkeypatch.delenv("INCLUDE_TEST", raising=False)
    db = _DB(users=[ELIGIBLE_PILOT, NO_GOAL, NO_FOCUS, TEST_ACCT])
    rows = asyncio.run(migrate_week1._collect_rows(db))
    anon_ids = [r["anon_id"] for r in rows]
    # The eligible pilot shows up; the test account, the no-goal and the
    # no-focus users don't.
    assert len(rows) == 1
    assert anon_ids == [migrate_week1._anon(ELIGIBLE_PILOT["id"])]
    r = rows[0]
    assert r["goal_chars"] == len(ELIGIBLE_PILOT["focus_goal"]["goal"])
    assert r["plan_chars"] == len(ELIGIBLE_PILOT["focus_goal"]["plan"])
    assert r["would_write_steps"] == list(migrate_week1.MIGRATED_STEPS)


def test_include_test_env_var_opens_the_door_for_test_accounts(monkeypatch):
    monkeypatch.setenv("INCLUDE_TEST", "1")
    db = _DB(users=[ELIGIBLE_PILOT, TEST_ACCT])
    rows = asyncio.run(migrate_week1._collect_rows(db))
    assert {r["is_test"] for r in rows} == {False, True}


def test_existing_record_is_detected_and_skipped(monkeypatch):
    monkeypatch.delenv("INCLUDE_TEST", raising=False)
    db = _DB(
        users=[ELIGIBLE_PILOT],
        weekly_workflow=[{
            "user_id": ELIGIBLE_PILOT["id"], "week": 1,
            "step_statuses": {"overview_video": {"status": "done"}},
        }],
    )
    rows = asyncio.run(migrate_week1._collect_rows(db))
    assert len(rows) == 1
    assert rows[0]["existing_record"] is True
    assert rows[0]["would_write_steps"] == []
    summary = migrate_week1._summary(rows)
    assert summary == {
        "eligible_total": 1, "would_write": 0, "would_skip_existing": 1,
        "by_focus_area": {},
    }


def test_apply_writes_a_record_without_awarding_points(monkeypatch):
    monkeypatch.delenv("INCLUDE_TEST", raising=False)
    db = _DB(users=[ELIGIBLE_PILOT])
    rows = asyncio.run(migrate_week1._collect_rows(db))
    written = asyncio.run(migrate_week1._apply(db, rows, "2026-10-29T12:00:00+00:00"))
    assert written == 1
    rec = db.weekly_workflow.docs[0]
    assert rec["user_id"] == ELIGIBLE_PILOT["id"] and rec["week"] == 1
    assert rec["migrated"] is True
    for sid in migrate_week1.MIGRATED_STEPS:
        step = rec["step_statuses"][sid]
        assert step["status"] == "done"
        assert step["migrated"] is True
        # The explicit zero is important — the research team reviews it
        # to confirm no step was double-paid.
        assert step["points_awarded_at_migration"] == 0


def test_apply_is_idempotent(monkeypatch):
    monkeypatch.delenv("INCLUDE_TEST", raising=False)
    db = _DB(users=[ELIGIBLE_PILOT])
    rows_1 = asyncio.run(migrate_week1._collect_rows(db))
    asyncio.run(migrate_week1._apply(db, rows_1, "2026-10-29T12:00:00+00:00"))
    # Second pass: collect again, apply again. Nothing new is written —
    # the existing record flag flips every row to "skip".
    rows_2 = asyncio.run(migrate_week1._collect_rows(db))
    assert rows_2[0]["existing_record"] is True
    written = asyncio.run(migrate_week1._apply(db, rows_2, "2026-10-29T13:00:00+00:00"))
    assert written == 0
    assert len(db.weekly_workflow.docs) == 1


def test_anonymiser_strips_recognisable_tails():
    # The demo user id is "demo-maya" — a last-4-chars anonymiser would
    # emit "maya", which is a known handle for the study team. The real
    # anonymiser uses a hash, so no human-recognisable fragment leaks.
    out = migrate_week1._anon("demo-maya")
    assert out != "…maya"
    assert out.startswith("…") and len(out) == 7


def test_anonymiser_is_deterministic():
    assert migrate_week1._anon("demo-maya") == migrate_week1._anon("demo-maya")
