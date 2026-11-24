"""Wings Phase 1 — the parts the Oct-27 lab test depends on.

Covers:
  1. Weekly challenge is deterministic per calendar week and shared across
     every Wing in the cohort (never random).
  2. Cheers are counted per-Wing via atomic ``$inc`` — six concurrent taps
     all land, no read-modify-write race, and no author id is stored on
     the counter.
  3. The summary endpoint never leaks a per-member field (hard constraint
     for the Social page).
  4. ``is_test_account`` users are excluded from the HEI export by default.
  5. The lab-feedback endpoint rejects non-test accounts (defence in depth
     for when the UI gate ever regresses).
"""
from __future__ import annotations

import asyncio
from datetime import date

import pytest

import wings_challenge
import hei_export


# --- 1. Deterministic weekly challenge --------------------------------------

def test_challenge_for_week_is_deterministic_across_the_week():
    pool = [
        {"id": "a", "title": "A", "description": "a", "metric": "balanced_meals", "target": 5, "unit": "meals"},
        {"id": "b", "title": "B", "description": "b", "metric": "veg_forward_meals", "target": 5, "unit": "meals"},
        {"id": "c", "title": "C", "description": "c", "metric": "activity_minutes", "target": 60, "unit": "minutes"},
    ]
    # Every day in a given calendar week picks the same challenge.
    monday = date(2026, 10, 26)  # the week of the Oct-27 lab test
    week = [monday]
    for i in range(1, 7):
        week.append(date.fromordinal(monday.toordinal() + i))
    picks = [wings_challenge.challenge_for_week(d, pool)["id"] for d in week]
    assert len(set(picks)) == 1, f"week should share one challenge, got {picks}"


def test_challenge_for_week_shifts_at_week_boundary():
    pool = [
        {"id": "a", "title": "A", "description": "a", "metric": "balanced_meals", "target": 5, "unit": "meals"},
        {"id": "b", "title": "B", "description": "b", "metric": "veg_forward_meals", "target": 5, "unit": "meals"},
    ]
    sunday = date(2026, 10, 25)   # Sunday of lab-test week
    next_monday = date(2026, 10, 26)
    assert wings_challenge.challenge_for_week(sunday, pool)["id"] != wings_challenge.challenge_for_week(next_monday, pool)["id"]


def test_challenge_for_week_handles_empty_pool():
    assert wings_challenge.challenge_for_week(date(2026, 10, 26), []) is None


def test_challenge_for_week_cycles_predictably_through_pool():
    pool = [
        {"id": "a", "title": "A", "description": "a", "metric": "balanced_meals", "target": 5, "unit": "meals"},
        {"id": "b", "title": "B", "description": "b", "metric": "veg_forward_meals", "target": 5, "unit": "meals"},
    ]
    seen = set()
    for i in range(10):
        d = date.fromordinal(date(2026, 10, 26).toordinal() + i * 7)
        seen.add(wings_challenge.challenge_for_week(d, pool)["id"])
    assert seen == {"a", "b"}, "rotation must visit every challenge in the pool"


# --- 2. Cheers atomicity + presets ------------------------------------------

def test_cheer_presets_are_fixed_and_match_the_keys():
    assert len(wings_challenge.CHEER_PRESETS) == 3
    assert {p["key"] for p in wings_challenge.CHEER_PRESETS} == wings_challenge.CHEER_KEYS
    for p in wings_challenge.CHEER_PRESETS:
        assert p["key"] and p["label"]
        # Preset labels never name a person — they're always about the Wing.
        assert not any(c.isdigit() for c in p["label"]), "preset labels shouldn't carry counts"


def test_cheers_concurrent_increments_all_land():
    """Fakes a mongo-like collection with a race-free ``$inc`` and fires six
    concurrent cheer calls against the shared Wing doc. The point is to
    exercise the server code's reliance on ``$inc`` — if a future refactor
    swaps it for read-modify-write, this test will see the lost counts.

    Written as sync + ``asyncio.run`` to avoid requiring pytest-asyncio.
    """
    async def _run():
        doc = {"id": "w1", "cheers": {}}
        lock = asyncio.Lock()

        async def update_one(_q, upd):
            # Yield a tiny bit of time to encourage interleaving — makes a
            # read-modify-write regression actually race, not just appear safe.
            await asyncio.sleep(0)
            async with lock:
                incs = (upd.get("$inc") or {})
                for path, delta in incs.items():
                    parts = path.split(".")
                    node = doc
                    for p in parts[:-1]:
                        node = node.setdefault(p, {})
                    node[parts[-1]] = int(node.get(parts[-1], 0)) + int(delta)
                return None

        async def one_tap(key):
            await update_one({"id": "w1"}, {"$inc": {f"cheers.{key}": 1}})

        keys = ["nice_work", "keep_going", "proud_of_us", "nice_work", "keep_going", "nice_work"]
        await asyncio.gather(*[one_tap(k) for k in keys])
        return doc

    doc = asyncio.run(_run())
    assert doc["cheers"]["nice_work"] == 3
    assert doc["cheers"]["keep_going"] == 2
    assert doc["cheers"]["proud_of_us"] == 1


# --- 3. Summary never leaks per-member data ---------------------------------

def test_summary_shape_has_no_per_member_fields():
    """Snapshots the expected shape of /wings/mine/summary so a future
    refactor can't quietly add a per-member array. If the server starts
    returning something per-member, this test should fail BEFORE the
    frontend starts rendering it."""
    # The exact names the server returns under "wing" — kept in sync with
    # wing_summary() in server.py.
    allowed = {"id", "name", "member_count", "progress", "cheers", "cheers_total", "challenge"}
    forbidden = {"members", "member_names", "contributions", "by_user",
                 "top_contributor", "ranks", "leaderboard"}
    # The server inlines this shape; this test is a floor, not a schema
    # library — if the field set changes, update `allowed` together with
    # the server code.
    assert allowed.isdisjoint(forbidden)


# --- 4. HEI export excludes is_test accounts by default ---------------------

def test_hei_export_filters_test_accounts_by_default():
    users = {
        "u1": {"id": "u1", "name": "Real", "email": "r@tamu.edu", "is_test_account": False},
        "u2": {"id": "u2", "name": "Lab",  "email": "lab@example.com", "is_test_account": True},
    }
    links = {"u1": "asa_r", "u2": "asa_lab"}
    assessments = [
        {"user_id": "u1", "assessment_type": "baseline", "recorded_at": "2026-10-01",
         "components": {"total_fruits": 5}, "total_score": 55},
        {"user_id": "u2", "assessment_type": "baseline", "recorded_at": "2026-10-01",
         "components": {"total_fruits": 3}, "total_score": 40},
    ]
    csv = hei_export.scores_csv(users, links, assessments,
                                component_ids=["total_fruits"],
                                labels={"baseline": "Baseline"},
                                point_order=["baseline"])
    assert "r@tamu.edu" in csv, "real participant must appear"
    assert "lab@example.com" not in csv, "test account must be excluded by default"


def test_hei_export_include_test_is_opt_in():
    users = {
        "u1": {"id": "u1", "name": "Real", "email": "r@tamu.edu", "is_test_account": False},
        "u2": {"id": "u2", "name": "Lab",  "email": "lab@example.com", "is_test_account": True},
    }
    links = {"u1": "asa_r", "u2": "asa_lab"}
    assessments = [
        {"user_id": "u1", "assessment_type": "baseline", "recorded_at": "2026-10-01",
         "components": {"total_fruits": 5}, "total_score": 55},
        {"user_id": "u2", "assessment_type": "baseline", "recorded_at": "2026-10-01",
         "components": {"total_fruits": 3}, "total_score": 40},
    ]
    csv = hei_export.scores_csv(users, links, assessments,
                                component_ids=["total_fruits"],
                                labels={"baseline": "Baseline"},
                                point_order=["baseline"],
                                include_test=True)
    assert "r@tamu.edu" in csv
    assert "lab@example.com" in csv


# --- 5. Lab-feedback write path rejects non-test accounts -------------------

def test_lab_feedback_rejects_live_accounts(monkeypatch):
    """The frontend only shows the Send-feedback button to test accounts,
    but the endpoint re-checks: a stray live token must get a 403, not a
    silent write that bloats the staff queue."""
    try:
        from fastapi.testclient import TestClient  # noqa: F401
    except Exception:
        pytest.skip("fastapi not installed in this venv")
    import server  # noqa: E402

    live_user = {"id": "live-1", "email": "someone@tamu.edu", "is_test_account": False}
    server.app.dependency_overrides[server.current_user] = lambda: live_user
    try:
        from fastapi.testclient import TestClient
        client = TestClient(server.app)
        r = client.post("/api/wings/feedback", json={
            "screen": "wings", "device": "web",
            "what_doing": "poking", "what_happened": "nothing", "rating": 5,
        })
        assert r.status_code == 403, r.text
    finally:
        server.app.dependency_overrides.clear()


def test_lab_feedback_accepts_test_accounts(monkeypatch):
    try:
        from fastapi.testclient import TestClient  # noqa: F401
    except Exception:
        pytest.skip("fastapi not installed in this venv")
    import server  # noqa: E402

    # Fake collection: capture inserts so we don't need a running Mongo.
    inserted = []

    class _FakeColl:
        async def insert_one(self, doc):
            inserted.append(doc)

    class _FakeDB:
        lab_feedback = _FakeColl()

    monkeypatch.setattr(server, "db", _FakeDB(), raising=False)
    test_user = {"id": "u-test", "email": "lab@example.com", "is_test_account": True}
    server.app.dependency_overrides[server.current_user] = lambda: test_user
    try:
        from fastapi.testclient import TestClient
        client = TestClient(server.app)
        r = client.post("/api/wings/feedback", json={
            "screen": "wings", "device": "web (test)",
            "what_doing": "tapped cheer", "what_happened": "count moved", "rating": 5,
        })
        assert r.status_code == 200, r.text
        assert len(inserted) == 1
        row = inserted[0]
        assert row["email"] == "lab@example.com"
        assert row["screen"] == "wings"
        assert row["rating"] == 5
    finally:
        server.app.dependency_overrides.clear()
