"""Server-level integration tests for Week 2 Phase 2.

Covers:
  * HEI feedback is unchanged after a planning submit.
  * keep_and_add → two active plans exist, Week 1 plan untouched.
  * replace → Week 1 plan marked REPLACED, its pending reminder row
    is gone, Week 2 plan is ACTIVE.
  * keep_week1_only → Week 1 plan untouched, Week 2 answers stored
    with status=KEPT and no reminder.
  * Migrated pilot users (focus_area + focus_goal, no reflection
    responses saved) can plan without ever seeing a broken situation.
  * Reminder dispatch collection has no row for a replaced plan.

Pattern: FakeDB + FastAPI TestClient (same shape as the Phase 1 test
file).
"""
from __future__ import annotations

import copy
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "llhs_unit_unused")
os.environ.setdefault("WEEK1_WORKFLOW_MODE", "on")
os.environ.setdefault("WEEK2_WORKFLOW_MODE", "on")

import server  # noqa: E402
import week2_planning  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


BASELINE_HEI = {
    "id": "hei-1", "assessment_type": "baseline",
    "components": {
        "total_fruits": 4.5, "whole_fruits": 4.5, "total_vegetables": 3.8,
        "greens_beans": 3.2, "whole_grains": 4.0, "refined_grains": 7.0,
        "dairy": 5.8, "total_protein_foods": 4.5, "seafood_plant_proteins": 2.8,
        "fatty_acids": 6.0, "saturated_fats": 6.1, "sodium": 2.3, "added_sugars": 7.9,
    },
    "total_score": 62.4, "recall_count": 2,
    "recorded_at": "2026-10-20T00:00:00+00:00",
    "created_at": "2026-10-20T00:00:00+00:00",
    "source": "asa24_totals_upload",
}


def _user(*, with_focus: bool = True, with_goal: bool = True, is_test: bool = True) -> dict:
    u = {
        "id": "u-w2p2",
        "email": "w2p2@example.com" if is_test else "w2p2@tamu.edu",
        "name": "W2P2 Student",
        "created_at": "2026-09-01T00:00:00+00:00",
        "focus_area": "sodium" if with_focus else None,
        "focus_areas": ["sodium"] if with_focus else [],
        "focus_goal": {"goal": "Lower-sodium snacks.", "plan": "Pack fruit."} if with_goal else {},
        "is_test_account": is_test,
    }
    return u


def _match(doc, query):
    for k, v in query.items():
        if isinstance(v, dict):
            if "$ne" in v and doc.get(k) == v["$ne"]:
                return False
            if "$gt" in v and not (doc.get(k) and doc[k] > v["$gt"]):
                return False
            if "$gte" in v and not (doc.get(k) and doc[k] >= v["$gte"]):
                return False
            if "$in" in v and doc.get(k) not in v["$in"]:
                return False
        elif doc.get(k) != v:
            return False
    return True


class _Cursor:
    def __init__(self, docs): self.docs = docs
    async def to_list(self, _n): return [copy.deepcopy(d) for d in self.docs]
    def sort(self, *_, **__): return self


class _Coll:
    def __init__(self): self.docs = []
    def find(self, query=None, projection=None, **_):
        return _Cursor([d for d in self.docs if _match(d, query or {})])
    async def find_one(self, query=None, projection=None):
        hits = [d for d in self.docs if _match(d, query or {})]
        return copy.deepcopy(hits[0]) if hits else None
    async def insert_one(self, doc): self.docs.append(copy.deepcopy(doc))
    async def update_one(self, query, update, upsert=False):
        for d in self.docs:
            if _match(d, query):
                for k, v in (update.get("$set") or {}).items():
                    if "." in k:
                        parts = k.split("."); tgt = d
                        for p in parts[:-1]: tgt = tgt.setdefault(p, {})
                        tgt[parts[-1]] = v
                    else:
                        d[k] = v
                for k, v in (update.get("$inc") or {}).items():
                    d[k] = d.get(k, 0) + v
                return
        if upsert:
            new = copy.deepcopy(query)
            for k, v in (update.get("$set") or {}).items():
                if "." in k:
                    parts = k.split("."); tgt = new
                    for p in parts[:-1]: tgt = tgt.setdefault(p, {})
                    tgt[parts[-1]] = v
                else:
                    new[k] = v
            for k, v in (update.get("$setOnInsert") or {}).items():
                new.setdefault(k, v)
            self.docs.append(new)
    async def delete_many(self, query):
        self.docs = [d for d in self.docs if not _match(d, query)]
    async def count_documents(self, query):
        return sum(1 for d in self.docs if _match(d, query))


class _DB:
    def __init__(self):
        for name in ("users", "hei_assessments", "weekly_workflow", "meals",
                     "activities", "sleeps", "completions", "program_steps",
                     "safety_checkins", "focus_meal_bonus", "chat_messages",
                     "guardrail_blocks", "plans", "plans_reminders"):
            setattr(self, name, _Coll())
    def __getitem__(self, name):
        if not hasattr(self, name): setattr(self, name, _Coll())
        return getattr(self, name)


def _client(monkeypatch, *, user: dict):
    fake = _DB()
    now = datetime(2026, 11, 1, 15, 0, tzinfo=timezone.utc)
    fake.users.docs.append(copy.deepcopy(user))
    fake.hei_assessments.docs.append({**copy.deepcopy(BASELINE_HEI), "user_id": user["id"]})
    monkeypatch.setattr(server, "db", fake)
    monkeypatch.setattr(server, "now_utc", lambda: now)
    monkeypatch.setattr(server, "study_today", lambda: now.date())
    server.app.dependency_overrides[server.current_user] = lambda: fake.users.docs[0]
    return TestClient(server.app), fake


def _submit_body(choice: str, with_reminder: bool = True) -> dict:
    return {
        "situation": {
            "setting": "dining_hall",
            "day": "2026-11-03",
            "day_label": "Mon Nov 3",
            "occasion": "lunch",
        },
        "action": {"text": "Ask for sauce on the side.", "source": "preset", "preset_index": 0},
        "barrier": {"id": "not_enough_time", "label": "Not enough time"},
        "coping": {"text": "Decide before I get there and pick the quickest option on my list.", "source": "preset"},
        "reminder": {"time": "11:00"} if with_reminder else {},
        "plan_management": choice,
    }


# --- HEI invariant ---------------------------------------------------------

def test_hei_unchanged_after_planning_submit(monkeypatch):
    client, fake = _client(monkeypatch, user=_user())
    try:
        before_assess = copy.deepcopy(fake.hei_assessments.docs)
        before_fc = client.get("/api/assessments/hei2020/focus-candidates").json()
        r = client.post("/api/weekly-workflow/2/planning/submit", json=_submit_body("keep_and_add"))
        assert r.status_code == 200, r.text
        after_assess = copy.deepcopy(fake.hei_assessments.docs)
        after_fc = client.get("/api/assessments/hei2020/focus-candidates").json()
        assert before_assess == after_assess
        assert before_fc == after_fc
    finally:
        server.app.dependency_overrides.clear()


# --- Keep / add / replace flows ------------------------------------------

def test_keep_and_add_results_in_two_active_plans(monkeypatch):
    client, fake = _client(monkeypatch, user=_user())
    try:
        r = client.post("/api/weekly-workflow/2/planning/submit", json=_submit_body("keep_and_add"))
        assert r.status_code == 200, r.text
        plans = client.get("/api/plans").json()["plans"]
        assert len(plans) == 2
        source_weeks = sorted(p["source_week"] for p in plans)
        assert source_weeks == [1, 2]
        # Both plans should be active + both should carry some reminder
        # information (Week 1 may have no reminder time; the Today card
        # just doesn't render the "reminder" bit).
        for p in plans:
            assert p["status"] == "active"
    finally:
        server.app.dependency_overrides.clear()


def test_replace_marks_week1_replaced_and_cancels_pending_reminder(monkeypatch):
    client, fake = _client(monkeypatch, user=_user())
    try:
        # Seed a pending reminder on the Week 1 plan the way the
        # Phase 3 dispatcher will — the submit flow must delete it.
        week1_plan_id = f"{_user()['id']}:w1"
        fake.plans_reminders.docs.append({
            "plan_id": week1_plan_id, "user_id": _user()["id"],
            "time": "08:00", "status": "scheduled",
        })

        r = client.post("/api/weekly-workflow/2/planning/submit", json=_submit_body("replace"))
        assert r.status_code == 200, r.text

        plans_in_db = [p for p in fake.plans.docs if p["user_id"] == _user()["id"]]
        by_source = {p["source_week"]: p for p in plans_in_db}
        assert by_source[1]["status"] == week2_planning.REPLACED
        assert by_source[2]["status"] == week2_planning.ACTIVE

        active_from_api = client.get("/api/plans").json()["plans"]
        assert all(p["status"] == "active" for p in active_from_api)
        assert all(p["source_week"] == 2 for p in active_from_api)

        # Pending reminder for the replaced plan must be gone.
        remaining = [r for r in fake.plans_reminders.docs if r["plan_id"] == week1_plan_id]
        assert remaining == [], (
            "Replaced plans must never fire reminders. Found rows still in "
            "plans_reminders for the Week 1 plan."
        )
    finally:
        server.app.dependency_overrides.clear()


def test_keep_only_leaves_week1_unchanged_and_week2_dormant(monkeypatch):
    client, fake = _client(monkeypatch, user=_user())
    try:
        r = client.post("/api/weekly-workflow/2/planning/submit", json=_submit_body("keep_week1_only"))
        assert r.status_code == 200, r.text

        plans_in_db = [p for p in fake.plans.docs if p["user_id"] == _user()["id"]]
        by_source = {p["source_week"]: p for p in plans_in_db}
        # Week 1 plan is untouched — still ACTIVE.
        assert by_source[1]["status"] == week2_planning.ACTIVE
        # Week 2 answers stored as KEPT (dormant) with no reminder.
        assert by_source[2]["status"] == week2_planning.KEPT
        assert by_source[2]["reminder"] == {}

        # /plans returns only the active Week 1 plan on the Today card.
        active_from_api = client.get("/api/plans").json()["plans"]
        assert [p["source_week"] for p in active_from_api] == [1]

        # No reminder row for the dormant plan.
        week2_rem = [r for r in fake.plans_reminders.docs if r["plan_id"].startswith(_user()["id"] + ":w2:")]
        assert week2_rem == [], "Dormant (kept) plans must not schedule reminders."
    finally:
        server.app.dependency_overrides.clear()


# --- Migrated pilot user ---------------------------------------------------

def test_migrated_user_with_no_week1_reflection_still_plans(monkeypatch):
    """Pilot migration (PR #38) marked Week 1 steps done without saving
    reflection sub-prompt answers. The planning step must synthesize a
    Week 1 plan from focus_area + focus_goal alone and let the student
    plan Week 2 without ever hitting a broken situation."""
    user = _user()
    client, fake = _client(monkeypatch, user=user)
    try:
        # Simulate what the pilot migration wrote: weekly_workflow row
        # for week=1 with steps marked done but no reflection responses.
        fake.weekly_workflow.docs.append({
            "user_id": user["id"], "week": 1, "migrated": True,
            "step_statuses": {
                sid: {"status": "done", "completed_at": "2026-10-29T00:00:00Z",
                      "points_awarded_at_migration": 0, "migrated": True}
                for sid in ("overview_video", "feedback", "mini_lecture", "reflection")
            },
        })

        config = client.get("/api/weekly-workflow/2/planning/config").json()
        assert config["week1_plan"] is not None
        # The engine materialised a Week 1 plan with occasion=None (no
        # Week 1 reflection), and the UI will ask for the missing bits.
        assert config["week1_plan"]["goal"] == "Lower-sodium snacks."

        # Submitting works — the Week 1 plan is now a real row in db.plans.
        r = client.post("/api/weekly-workflow/2/planning/submit", json=_submit_body("replace"))
        assert r.status_code == 200, r.text
        plans_in_db = [p for p in fake.plans.docs if p["user_id"] == user["id"]]
        assert any(p["source_week"] == 1 and p["status"] == week2_planning.REPLACED for p in plans_in_db)
        assert any(p["source_week"] == 2 and p["status"] == week2_planning.ACTIVE for p in plans_in_db)
    finally:
        server.app.dependency_overrides.clear()


# --- Phase 3 safety guarantee --------------------------------------------

def test_dormant_plan_never_gets_a_reminder_row(monkeypatch):
    """Second guard against the Phase 3 dispatcher firing from a
    replaced or kept plan."""
    client, fake = _client(monkeypatch, user=_user())
    try:
        r = client.post("/api/weekly-workflow/2/planning/submit", json=_submit_body("keep_week1_only"))
        assert r.status_code == 200
        assert fake.plans_reminders.docs == []
    finally:
        server.app.dependency_overrides.clear()
