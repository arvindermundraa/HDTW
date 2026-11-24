"""POST /asa24/recall/finished — two recalls per assessment point.

A participant taps "I finished" once per recall (a weekday and a weekend
day). The point is finished after the second tap; a quick double tap counts
once, and rows saved before two recalls per point (finished_at only) still
count as one recall.
"""
from __future__ import annotations

import os
import sys
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "llhs_unit_unused")
import server  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

JOINED = "2026-10-13T15:00:00+00:00"  # a Tuesday, in the study time zone too
USER = {"id": "u1", "email": "amy@tamu.edu", "created_at": JOINED}


def _match(doc, query):
    return all(doc.get(k) == v for k, v in query.items())


class Cursor:
    def __init__(self, docs):
        self.docs = docs

    async def to_list(self, _n):
        return [dict(d) for d in self.docs]


class Coll:
    def __init__(self):
        self.docs = []

    def find(self, query=None, projection=None):
        return Cursor([d for d in self.docs if _match(d, query or {})])

    async def find_one(self, query=None, projection=None):
        hits = [d for d in self.docs if _match(d, query or {})]
        return dict(hits[0]) if hits else None

    async def update_one(self, query, update, upsert=False):
        for d in self.docs:
            if _match(d, query):
                d.update(update.get("$set", {}))
                return
        if upsert:
            self.docs.append({**query, **update.get("$set", {})})


class FakeDB:
    def __init__(self):
        self.asa24_recall_finished = Coll()
        self.hei_assessments = Coll()


def _client(monkeypatch, now):
    fake = FakeDB()
    clock = {"now": now}
    monkeypatch.setattr(server, "db", fake)
    monkeypatch.setattr(server, "now_utc", lambda: clock["now"])
    monkeypatch.setattr(server, "study_today", lambda: clock["now"].date())
    server.app.dependency_overrides[server.current_user] = lambda: USER
    return TestClient(server.app), fake, clock


def _tap(c):
    r = c.post("/api/asa24/recall/finished", json={"assessment_type": "baseline"})
    assert r.status_code == 200, r.text
    return r.json()["recall"]


def test_two_taps_finish_the_point(monkeypatch):
    c, fake, clock = _client(monkeypatch, datetime(2026, 10, 15, 2, 0, tzinfo=timezone.utc))
    try:
        st = _tap(c)
        assert (st["state"], st["recalls_done"]) == ("open", 1)
        clock["now"] += timedelta(days=3)  # the weekend recall
        st = _tap(c)
        assert (st["state"], st["recalls_done"]) == ("finished", 2)
        clock["now"] += timedelta(hours=2)
        assert _tap(c)["recalls_done"] == 2  # a third tap isn't counted
        assert len(fake.asa24_recall_finished.docs[0]["finished_times"]) == 2
    finally:
        server.app.dependency_overrides.clear()


def test_a_quick_double_tap_counts_once(monkeypatch):
    c, _, clock = _client(monkeypatch, datetime(2026, 10, 15, 2, 0, tzinfo=timezone.utc))
    try:
        _tap(c)
        clock["now"] += timedelta(seconds=20)
        assert _tap(c)["recalls_done"] == 1
    finally:
        server.app.dependency_overrides.clear()


def test_a_row_saved_before_two_recalls_counts_as_one(monkeypatch):
    c, fake, clock = _client(monkeypatch, datetime(2026, 10, 18, 2, 0, tzinfo=timezone.utc))
    fake.asa24_recall_finished.docs.append(
        {"user_id": "u1", "assessment_type": "baseline", "finished_at": "2026-10-15T02:00:00+00:00"})
    try:
        st = _tap(c)
        assert (st["state"], st["recalls_done"]) == ("finished", 2)
        assert fake.asa24_recall_finished.docs[0]["finished_times"][0] == "2026-10-15T02:00:00+00:00"
    finally:
        server.app.dependency_overrides.clear()
