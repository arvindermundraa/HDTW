"""Guard that baseline HEI feedback never shifts because of Week 1 workflow
progress.

Spec §8 is explicit: "baseline HEI feedback should not be presented as
having improved simply because the participant watched a video,
completed an activity, or logged a meal. Any later changes to
diet-quality feedback must be based on the scientifically specified
dietary assessment and scoring process."

This test writes an HEI assessment to the fake DB, runs the engine
through the full set of Week 1 side effects (step completions, a meal
log with ``goal_hit=true``), and asserts the stored assessment and the
/focus-candidates response are byte-identical before and after.
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

import server  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


USER = {
    "id": "u-hei-stable",
    "email": "stable@example.com",
    "name": "Stable Student",
    "created_at": "2026-09-01T00:00:00+00:00",
    "focus_area": "sodium",
    "focus_areas": ["sodium"],
    "focus_goal": {"goal": "I will keep snacks lower in sodium.", "plan": "Pack fruit on busy afternoons."},
    "is_test_account": False,
}


def _match(doc, query):
    for k, v in query.items():
        if isinstance(v, dict):
            # Only the subset of operators the engine actually uses.
            if "$ne" in v and doc.get(k) == v["$ne"]:
                return False
            if "$gt" in v and not (doc.get(k) and doc[k] > v["$gt"]):
                return False
            if "$in" in v and doc.get(k) not in v["$in"]:
                return False
        elif doc.get(k) != v:
            return False
    return True


class Cursor:
    def __init__(self, docs):
        self.docs = docs

    async def to_list(self, _n):
        return [copy.deepcopy(d) for d in self.docs]

    def sort(self, *_args, **_kwargs):
        return self


class Coll:
    def __init__(self):
        self.docs = []

    def find(self, query=None, projection=None, **_):
        return Cursor([d for d in self.docs if _match(d, query or {})])

    async def find_one(self, query=None, projection=None):
        hits = [d for d in self.docs if _match(d, query or {})]
        return copy.deepcopy(hits[0]) if hits else None

    async def insert_one(self, doc):
        self.docs.append(copy.deepcopy(doc))

    async def update_one(self, query, update, upsert=False):
        for d in self.docs:
            if _match(d, query):
                for k, v in (update.get("$set") or {}).items():
                    if "." in k:
                        top, rest = k.split(".", 1)
                        if "." in rest:
                            # Not needed by the engine's writes today.
                            d.setdefault(top, {})[rest] = v
                        else:
                            d.setdefault(top, {})[rest] = v
                    else:
                        d[k] = v
                for k, v in (update.get("$inc") or {}).items():
                    d[k] = d.get(k, 0) + v
                return
        if upsert:
            new = copy.deepcopy(query)
            for k, v in (update.get("$set") or {}).items():
                if "." in k:
                    top, rest = k.split(".", 1)
                    new.setdefault(top, {})[rest] = v
                else:
                    new[k] = v
            for k, v in (update.get("$setOnInsert") or {}).items():
                new.setdefault(k, v)
            self.docs.append(new)

    async def delete_many(self, query):
        self.docs = [d for d in self.docs if not _match(d, query)]

    async def count_documents(self, query):
        return sum(1 for d in self.docs if _match(d, query))


class FakeDB:
    def __init__(self):
        self.users = Coll()
        self.hei_assessments = Coll()
        self.weekly_workflow = Coll()
        self.meals = Coll()
        self.activities = Coll()
        self.sleeps = Coll()
        self.completions = Coll()
        self.program_steps = Coll()
        self.safety_checkins = Coll()
        self.focus_meal_bonus = Coll()
        self.badges_awarded = Coll()
        self.chat_messages = Coll()
        self.guardrail_blocks = Coll()

    def __getitem__(self, name: str) -> Coll:
        # Motor supports `db["collection_name"]`; the server uses that in
        # award_points_capped. Create on first access so new collections
        # don't need to be enumerated above.
        if not hasattr(self, name):
            setattr(self, name, Coll())
        return getattr(self, name)


def _client(monkeypatch):
    fake = FakeDB()
    now = datetime(2026, 10, 29, 15, 0, tzinfo=timezone.utc)
    fake.users.docs.append(copy.deepcopy(USER))
    # Pre-existing HEI baseline that must stay fixed through the test.
    fake.hei_assessments.docs.append({
        "id": "hei-1",
        "user_id": USER["id"],
        "assessment_type": "baseline",
        "components": {
            "total_fruits": 4.5, "whole_fruits": 4.5, "total_vegetables": 3.8,
            "greens_beans": 3.2, "whole_grains": 4.0, "refined_grains": 7.0,
            "dairy": 5.8, "total_protein_foods": 4.5, "seafood_plant_proteins": 2.8,
            "fatty_acids": 6.0, "saturated_fats": 6.1, "sodium": 2.3, "added_sugars": 7.9,
        },
        "total_score": 62.4,
        "recall_count": 2,
        "recorded_at": "2026-10-20T00:00:00+00:00",
        "created_at": "2026-10-20T00:00:00+00:00",
    })
    monkeypatch.setattr(server, "db", fake)
    monkeypatch.setattr(server, "now_utc", lambda: now)
    monkeypatch.setattr(server, "study_today", lambda: now.date())
    server.app.dependency_overrides[server.current_user] = lambda: fake.users.docs[0]
    return TestClient(server.app), fake


def _hei_snapshot(fake):
    """Deep-copy snapshot of the only thing that must not drift: the
    db.hei_assessments documents and the /focus-candidates response."""
    assessments = copy.deepcopy(fake.hei_assessments.docs)
    return assessments


def test_week1_steps_and_meal_log_do_not_change_hei(monkeypatch):
    client, fake = _client(monkeypatch)
    try:
        before_assessments = _hei_snapshot(fake)
        before_fc = client.get("/api/assessments/hei2020/focus-candidates").json()

        # Complete every Week 1 step the student can POST (focus_selection
        # and goal_and_plan auto-complete from the user doc).
        for sid in ("overview_video", "feedback", "mini_lecture"):
            r = client.post(f"/api/weekly-workflow/1/step/{sid}/complete", json={})
            assert r.status_code == 200, (sid, r.text)
        reflect = client.post("/api/weekly-workflow/1/step/reflection/complete", json={
            "responses": {
                "p1_behind": {"selected": ["Snacks", "Drinks"], "text": "Chips in the afternoon"},
                "p2_room": {"selected": "Snacks"},
                "p3_working": {"text": "I eat fruit at breakfast most days."},
            },
        })
        assert reflect.status_code == 200, reflect.text

        # Log a meal that reports the goal was hit.
        r = client.post("/api/meals", json={
            "name": "Afternoon snack", "meal_type": "snack",
            "categories": ["fruit"], "goal_hit": True,
        })
        assert r.status_code == 200, r.text

        after_assessments = _hei_snapshot(fake)
        after_fc = client.get("/api/assessments/hei2020/focus-candidates").json()

        assert before_assessments == after_assessments, (
            "db.hei_assessments drifted after Week 1 progress — scoring must only "
            "change when a new ASA24 recall is imported, never because of workflow activity."
        )
        assert before_fc == after_fc, (
            "/focus-candidates drifted after Week 1 progress. Baseline feedback must be stable."
        )
    finally:
        server.app.dependency_overrides.clear()
