"""Server-level integration tests for Week 2 Phase 1:

1. Baseline HEI feedback is unchanged after responding to all five
   scenarios (spec §7, "Eat Dashboard"): Week 2 activity completion
   must not alter ``db.hei_assessments`` or ``/focus-candidates``.
2. Week 2 opens only on the study day Week 2 starts — before day 7
   the engine refuses to serve Week 2 and the Today card has no Week 2
   view, regardless of ``WEEK2_WORKFLOW_MODE``.
3. The cafeteria setting is hidden from real participants while the
   dining menu is still SAMPLE; test accounts still see it.

Pattern follows ``test_week1_hei_unchanged.py`` (in-memory FakeDB +
FastAPI TestClient).
"""
from __future__ import annotations

import copy
import os
import sys
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "llhs_unit_unused")
os.environ.setdefault("WEEK1_WORKFLOW_MODE", "on")
os.environ.setdefault("WEEK2_WORKFLOW_MODE", "on")

import server  # noqa: E402
import weekly_workflow  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


BASELINE_HEI = {
    "id": "hei-1",
    "assessment_type": "baseline",
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


def _user(*, is_test: bool = False, created_at: str = "2026-09-01T00:00:00+00:00") -> dict:
    return {
        "id": "u-w2",
        "email": "w2@example.com" if is_test else "w2@tamu.edu",
        "name": "W2 Student",
        "created_at": created_at,
        "focus_area": "sodium",
        "focus_areas": ["sodium"],
        "focus_goal": {"goal": "Lower-sodium snacks.", "plan": "Bring fruit."},
        "is_test_account": is_test,
    }


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
    def __init__(self, docs):
        self.docs = docs
    async def to_list(self, _n):
        return [copy.deepcopy(d) for d in self.docs]
    def sort(self, *_, **__):
        return self


class _Coll:
    def __init__(self):
        self.docs = []
    def find(self, query=None, projection=None, **_):
        return _Cursor([d for d in self.docs if _match(d, query or {})])
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
                        parts = k.split(".")
                        tgt = d
                        for p in parts[:-1]:
                            tgt = tgt.setdefault(p, {})
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
                    parts = k.split(".")
                    tgt = new
                    for p in parts[:-1]:
                        tgt = tgt.setdefault(p, {})
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
        for name in (
            "users", "hei_assessments", "weekly_workflow", "meals",
            "activities", "sleeps", "completions", "program_steps",
            "safety_checkins", "focus_meal_bonus", "chat_messages",
            "guardrail_blocks",
        ):
            setattr(self, name, _Coll())
    def __getitem__(self, name):
        if not hasattr(self, name):
            setattr(self, name, _Coll())
        return getattr(self, name)


def _client(monkeypatch, *, user: dict, today: date | None = None):
    fake = _DB()
    now = datetime(today.year, today.month, today.day, 15, 0, tzinfo=timezone.utc) \
        if today else datetime(2026, 10, 29, 15, 0, tzinfo=timezone.utc)
    fake.users.docs.append(copy.deepcopy(user))
    fake.hei_assessments.docs.append({**copy.deepcopy(BASELINE_HEI), "user_id": user["id"]})
    monkeypatch.setattr(server, "db", fake)
    monkeypatch.setattr(server, "now_utc", lambda: now)
    monkeypatch.setattr(server, "study_today", lambda: now.date())
    server.app.dependency_overrides[server.current_user] = lambda: fake.users.docs[0]
    return TestClient(server.app), fake, now


# --- 1. HEI unchanged after all 5 scenarios ---------------------------------

def _pick_first_choice_id(scenario_body: dict) -> str:
    return scenario_body["choices"][0]["id"]


def test_hei_feedback_unchanged_after_all_five_scenarios(monkeypatch):
    client, fake, _ = _client(monkeypatch, user=_user(is_test=True))
    try:
        before_assess = copy.deepcopy(fake.hei_assessments.docs)
        before_fc = client.get("/api/assessments/hei2020/focus-candidates").json()

        # Pick three settings and answer them.
        r = client.post("/api/weekly-workflow/2/scenarios/settings",
                        json={"settings": ["cafeteria", "restaurant", "home"]})
        assert r.status_code == 200, r.text
        for setting in ("cafeteria", "restaurant", "home"):
            body = client.get(f"/api/weekly-workflow/2/scenario/{setting}").json()
            r = client.post(f"/api/weekly-workflow/2/scenario/{setting}/respond",
                            json={"choice_id": _pick_first_choice_id(body),
                                  "shown_option_ids": [c["id"] for c in body["choices"]]})
            assert r.status_code == 200, (setting, r.text)
        # Try-another the remaining two (optional practice, per spec).
        for setting in ("grocery", "someone_else"):
            body = client.get(f"/api/weekly-workflow/2/scenario/{setting}").json()
            r = client.post(f"/api/weekly-workflow/2/scenario/{setting}/respond",
                            json={"choice_id": _pick_first_choice_id(body),
                                  "shown_option_ids": [c["id"] for c in body["choices"]]})
            assert r.status_code == 200, (setting, r.text)

        after_assess = copy.deepcopy(fake.hei_assessments.docs)
        after_fc = client.get("/api/assessments/hei2020/focus-candidates").json()

        assert before_assess == after_assess, (
            "db.hei_assessments drifted after Week 2 scenarios — "
            "scoring must only change when a new ASA24 recall is imported."
        )
        assert before_fc == after_fc, (
            "/focus-candidates drifted after Week 2 scenarios. Baseline Eat "
            "feedback must stay stable."
        )
    finally:
        server.app.dependency_overrides.clear()


# --- 2. Week 2 opens only on the study day ----------------------------------

def test_week2_closed_before_study_day():
    # Student joined six days ago; Week 2 opens on day 7, so still closed.
    start = date(2026, 10, 23)
    today = date(2026, 10, 29)
    assert weekly_workflow.week_has_opened(start, today, 1) is True
    assert weekly_workflow.week_has_opened(start, today, 2) is False
    assert weekly_workflow.is_enabled_for(
        2, is_test=True, study_start=start, today=today,
    ) is False
    # Mode and is_test don't override the clock.
    assert weekly_workflow.is_enabled_for(
        2, is_test=False, study_start=start, today=today,
    ) is False


def test_week2_opens_exactly_on_day_seven():
    start = date(2026, 10, 23)
    day_seven = start + timedelta(days=7)
    assert weekly_workflow.week_has_opened(start, day_seven, 2) is True
    assert weekly_workflow.is_enabled_for(
        2, is_test=False, study_start=start, today=day_seven,
    ) is True


def test_week2_gate_without_study_clock_falls_back_to_mode_only():
    """``study_start`` and ``today`` default to None so legacy callers
    (the Phase 1 unit tests, pre-study-day gate) still exercise the
    pure mode/is_test branch."""
    assert weekly_workflow.is_enabled_for(2, is_test=True) is True


def test_server_returns_week2_disabled_before_study_day(monkeypatch):
    # User joined "today" — only Week 1 should be served.
    today = date(2026, 10, 29)
    user = _user(is_test=True, created_at=f"{today.isoformat()}T00:00:00+00:00")
    client, _, _ = _client(monkeypatch, user=user, today=today)
    try:
        r = client.get("/api/weekly-workflow")
        assert r.status_code == 200
        weeks = {w["week"]: w for w in r.json()["weeks"]}
        assert weeks[1]["enabled"] is True
        assert weeks[2]["enabled"] is False, (
            "Week 2 must not be enabled when today < study_start + 7 days."
        )
        # Direct access to Week 2 endpoints returns 403.
        r = client.get("/api/weekly-workflow/2/scenarios/config")
        assert r.status_code == 403
    finally:
        server.app.dependency_overrides.clear()


# --- 3. Cafeteria gate for real participants --------------------------------

def test_cafeteria_hidden_from_real_user_while_dining_is_sample(monkeypatch):
    client, _, _ = _client(monkeypatch, user=_user(is_test=False))
    try:
        r = client.get("/api/weekly-workflow/2/scenarios/config")
        assert r.status_code == 200
        settings = [s["id"] for s in r.json()["available_settings"]]
        assert "cafeteria" not in settings, (
            "Real participants must not see the cafeteria setting while "
            "backend/content/week2_dining_menu.json is still SAMPLE."
        )
        # A hand-crafted POST with cafeteria is rejected.
        r = client.post("/api/weekly-workflow/2/scenarios/settings",
                        json={"settings": ["cafeteria", "restaurant", "home"]})
        assert r.status_code == 422
        # A GET for the cafeteria body is also refused.
        r = client.get("/api/weekly-workflow/2/scenario/cafeteria")
        assert r.status_code == 404
    finally:
        server.app.dependency_overrides.clear()


def test_cafeteria_visible_to_test_user_even_with_sample_dining(monkeypatch):
    client, _, _ = _client(monkeypatch, user=_user(is_test=True))
    try:
        r = client.get("/api/weekly-workflow/2/scenarios/config")
        assert r.status_code == 200
        settings = [s["id"] for s in r.json()["available_settings"]]
        assert "cafeteria" in settings
    finally:
        server.app.dependency_overrides.clear()
