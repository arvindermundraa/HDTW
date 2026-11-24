"""Nutrition team feedback (2026-10-29, item 7): the old Nutrition /
Menu Challenge (game id g2) was flagged for inaccurate information. It
MUST be hidden from everyone — including pilots — until the team ships
a reworked version. These tests pin the gate and the Week 2 practice-
step override that fills the gap.
"""
from __future__ import annotations

import copy
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "llhs_unit_unused")

import server  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from test_coach_and_future_me import FakeDB, USER  # reuse fixtures


def _client(monkeypatch, *, user=None):
    db = FakeDB()
    base_user = dict(user or USER)
    # Pin study_start six weeks before "today" so Week 2 has already opened
    # (otherwise the Week 2 workflow is clock-gated regardless of mode).
    base_user.setdefault("created_at", "2026-09-20T00:00:00+00:00")
    db.users.docs.append(base_user)
    monkeypatch.setattr(server, "db", db)
    monkeypatch.setattr(server.limiter, "enabled", False)
    monkeypatch.setattr(server, "now_utc", lambda: datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc))
    monkeypatch.setattr(server, "study_today", lambda: datetime(2026, 11, 3).date())
    server.app.dependency_overrides[server.current_user] = lambda: dict(base_user)
    return TestClient(server.app), db


def test_menu_challenge_flag_defaults_off(monkeypatch):
    monkeypatch.delenv("MENU_CHALLENGE_ENABLED", raising=False)
    assert server.menu_challenge_enabled() is False


def test_menu_challenge_flag_flips_on(monkeypatch):
    for v in ("1", "true", "YES", "on"):
        monkeypatch.setenv("MENU_CHALLENGE_ENABLED", v)
        assert server.menu_challenge_enabled() is True


def test_games_endpoint_hides_g2_by_default(monkeypatch):
    monkeypatch.delenv("MENU_CHALLENGE_ENABLED", raising=False)
    client, _ = _client(monkeypatch)
    try:
        r = client.get("/api/games")
        assert r.status_code == 200
        ids = [g["id"] for g in r.json()]
        assert "g2" not in ids, "g2 is nutritionally inaccurate; must stay hidden until reworked."
        # Other games still show.
        assert any(g in ids for g in ("g1", "g3")), "Other games should still show."
    finally:
        server.app.dependency_overrides.clear()


def test_games_endpoint_shows_g2_when_flag_is_on(monkeypatch):
    monkeypatch.setenv("MENU_CHALLENGE_ENABLED", "true")
    client, _ = _client(monkeypatch)
    try:
        r = client.get("/api/games")
        ids = [g["id"] for g in r.json()]
        assert "g2" in ids
    finally:
        server.app.dependency_overrides.clear()


def test_g2_complete_endpoint_410_when_disabled(monkeypatch):
    monkeypatch.delenv("MENU_CHALLENGE_ENABLED", raising=False)
    client, _ = _client(monkeypatch)
    try:
        r = client.post("/api/games/g2/complete", json={"markers": [], "score": 0})
        assert r.status_code == 410, "A stale client posting to the disabled game must get 410."
    finally:
        server.app.dependency_overrides.clear()


def test_program_week2_practice_shows_coming_soon_when_both_flags_off(monkeypatch):
    monkeypatch.delenv("MENU_CHALLENGE_ENABLED", raising=False)
    monkeypatch.delenv("WEEK2_WORKFLOW_MODE", raising=False)
    client, _ = _client(monkeypatch)
    try:
        r = client.get("/api/program")
        week2 = next(u for u in r.json()["units"] if u["week"] == 2)
        practice = next(s for s in week2["steps"] if s["key"] == "practice")
        assert practice["title"] == "Week 2 activities are coming soon"
        assert practice["route"] is None
        assert practice["ready"] is False
    finally:
        server.app.dependency_overrides.clear()


def test_program_week2_practice_routes_to_workflow_when_week2_enabled(monkeypatch):
    monkeypatch.delenv("MENU_CHALLENGE_ENABLED", raising=False)
    monkeypatch.setenv("WEEK2_WORKFLOW_MODE", "on")
    client, _ = _client(monkeypatch)
    try:
        r = client.get("/api/program")
        week2 = next(u for u in r.json()["units"] if u["week"] == 2)
        practice = next(s for s in week2["steps"] if s["key"] == "practice")
        assert practice["route"] == "/week/overview_video"
        assert (practice.get("params") or {}).get("week") == "2"
        assert practice["ready"] is True
        assert "Week 2" in practice["title"]
    finally:
        server.app.dependency_overrides.clear()


def test_program_week2_practice_untouched_when_menu_challenge_enabled(monkeypatch):
    monkeypatch.setenv("MENU_CHALLENGE_ENABLED", "true")
    monkeypatch.delenv("WEEK2_WORKFLOW_MODE", raising=False)
    client, _ = _client(monkeypatch)
    try:
        r = client.get("/api/program")
        week2 = next(u for u in r.json()["units"] if u["week"] == 2)
        practice = next(s for s in week2["steps"] if s["key"] == "practice")
        # Legacy behaviour preserved: the Learn screen keeps routing to
        # the old game while the flag is on.
        assert practice["title"] == "Nutrition / Menu Challenge"
        assert practice["route"] == "/game/g2"
    finally:
        server.app.dependency_overrides.clear()
