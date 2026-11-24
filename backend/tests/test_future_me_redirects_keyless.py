"""The 7 scope redirects + the "not in my notes" fallback must work with
no TAMU AI key, an invalid key, or TAMU AI down. Only the LLM branch
needs the key.

Nutrition team + 2026-11-24 review of PR #48 (scope_check / key-check
order fix). Covers:

* no key saved -> every scope redirect returns the DECLINE text verbatim,
  AND the non-redirect "I don't have information" fallback (NOT_FOUND)
  also comes back without the "add your key" message;
* TAMU AI rejects the key mid-call -> same as above for redirects, and
  a normal nutrition question (which would take the LLM branch) gets
  the "add your key" message;
* no key saved AND the student asks a normal nutrition question ->
  "add your key" message (unchanged behaviour on this path).
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "llhs_unit_unused")

import coach_kb  # noqa: E402
import server  # noqa: E402
import tamus_client  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from test_coach_and_future_me import FakeDB, USER, SCORES  # reuse fixtures


REDIRECT_QUESTIONS = [
    ("medical", "What should I eat with high blood pressure?"),
    ("calories", "How many calories a day?"),
    ("medications", "Should I take a multivitamin?"),
    ("eating_support", "I feel guilty after eating"),
    ("weight", "Can you give me a weight-loss plan?"),
    ("specialized_diets", "Should I try keto?"),
    ("urgent", "I'm having chest pain right now"),
]

# A normal nutrition question that goes through the KB / LLM branch —
# NOT in any scope bucket.
NORMAL_QUESTION = "Is brown rice a whole grain?"


def _app_with_key_behavior(monkeypatch, *, resolve_behavior):
    """Builds a chat TestClient where ``tamus_client.resolve_user_key``
    has the given behavior and ``server.run_llm`` is wired to a stub so
    we can tell whether the LLM was reached."""
    db = FakeDB()
    db.users.docs.append(dict(USER))
    db.hei_assessments.docs.append({
        "user_id": "u1", "assessment_type": "baseline", "components": SCORES,
        "recorded_at": "2026-09-22T12:00:00+00:00",
    })
    monkeypatch.setattr(server, "db", db)
    monkeypatch.setattr(server.limiter, "enabled", False)
    monkeypatch.setattr(tamus_client, "resolve_user_key", resolve_behavior)

    llm_called = {"count": 0}

    async def fake_llm(user, system, user_text, session_id, history=None):
        llm_called["count"] += 1
        return "Brown rice is a whole grain.\nSOURCE: whole_grains"

    monkeypatch.setattr(server, "run_llm", fake_llm)
    server.app.dependency_overrides[server.current_user] = lambda: dict(USER)
    client = TestClient(server.app)
    return client, llm_called


def _no_key(_user):
    raise tamus_client.TamusKeyRequiredError("Add your TAMU AI key in Settings to use this feature.")


def _ok_key(_user):
    return "a-valid-key"


# --- No key: every redirect still fires -----------------------------------

@pytest.mark.parametrize("scope,question", REDIRECT_QUESTIONS)
def test_every_redirect_returns_its_text_with_no_key(monkeypatch, scope, question):
    client, llm_called = _app_with_key_behavior(monkeypatch, resolve_behavior=_no_key)
    try:
        d = client.post("/api/chat", json={"message": question, "session_id": "s"}).json()
    finally:
        server.app.dependency_overrides.clear()
    assert d["answer"] == coach_kb.DECLINE[scope], (scope, d["answer"][:80])
    assert d.get("tamus_key_required") is not True
    assert llm_called["count"] == 0  # LLM must not have been touched


def test_not_found_fallback_works_with_no_key(monkeypatch):
    """A question with nothing in the KB and no scope hit must land on
    coach_kb.NOT_FOUND, not on the 'add your key' prompt."""
    client, llm_called = _app_with_key_behavior(monkeypatch, resolve_behavior=_no_key)
    try:
        d = client.post("/api/chat", json={"message": "Who won the football game?", "session_id": "s"}).json()
    finally:
        server.app.dependency_overrides.clear()
    assert d["answer"] == coach_kb.NOT_FOUND
    assert d.get("tamus_key_required") is not True
    assert llm_called["count"] == 0


def test_normal_question_with_no_key_prompts_to_add_one(monkeypatch):
    client, llm_called = _app_with_key_behavior(monkeypatch, resolve_behavior=_no_key)
    try:
        d = client.post("/api/chat", json={"message": NORMAL_QUESTION, "session_id": "s"}).json()
    finally:
        server.app.dependency_overrides.clear()
    assert d["tamus_key_required"] is True
    assert "Add your TAMU AI key" in d["answer"]
    assert llm_called["count"] == 0


# --- Rejected key: every redirect still fires -----------------------------

@pytest.mark.parametrize("scope,question", REDIRECT_QUESTIONS)
def test_every_redirect_returns_its_text_with_a_rejected_key(monkeypatch, scope, question):
    """``resolve_user_key`` succeeds (the key IS saved) but a hypothetical
    LLM call would raise a ``TAMUSError("... rejected ...")``. Redirects
    must still fire — they never touch the LLM — so the rejected key
    never gets a chance to surface."""
    client, llm_called = _app_with_key_behavior(monkeypatch, resolve_behavior=_ok_key)

    async def reject(*_a, **_kw):
        raise tamus_client.TAMUSError("That TAMU API key was rejected - please check it in Settings.")

    monkeypatch.setattr(server, "run_llm", reject)
    try:
        d = client.post("/api/chat", json={"message": question, "session_id": "s"}).json()
    finally:
        server.app.dependency_overrides.clear()
    assert d["answer"] == coach_kb.DECLINE[scope], (scope, d["answer"][:80])
    assert d.get("tamus_key_required") is not True
    assert llm_called["count"] == 0  # wasn't our stub either


def test_normal_question_with_a_rejected_key_prompts_to_add_one(monkeypatch):
    client, _ = _app_with_key_behavior(monkeypatch, resolve_behavior=_ok_key)

    async def reject(*_a, **_kw):
        raise tamus_client.TAMUSError("That TAMU API key was rejected - please check it in Settings.")

    monkeypatch.setattr(server, "run_llm", reject)
    try:
        d = client.post("/api/chat", json={"message": NORMAL_QUESTION, "session_id": "s"}).json()
    finally:
        server.app.dependency_overrides.clear()
    assert d["tamus_key_required"] is True
    assert "Add your TAMU AI key" in d["answer"]


# --- TAMU AI service down (not a key problem): old copy stays -------------

def test_normal_question_when_tamu_ai_is_simply_down_keeps_the_old_couldnt_reach_copy(monkeypatch):
    """Service-level failures (connection refused, 5xx, timeout) are a
    different student problem from a bad key — the student should see
    the 'couldn't reach TAMU AI just now' copy, not 'add your key'."""
    client, _ = _app_with_key_behavior(monkeypatch, resolve_behavior=_ok_key)

    async def service_down(*_a, **_kw):
        raise tamus_client.TAMUSError("Could not reach the TAMU AI service: RequestError")

    monkeypatch.setattr(server, "run_llm", service_down)
    try:
        d = client.post("/api/chat", json={"message": NORMAL_QUESTION, "session_id": "s"}).json()
    finally:
        server.app.dependency_overrides.clear()
    assert d.get("tamus_key_required") is False
    assert "couldn't reach TAMU AI" in d["answer"]


# --- The order invariant --------------------------------------------------

def test_resolve_user_key_is_only_called_inside_the_llm_branch(monkeypatch):
    """A scope redirect must not trigger resolve_user_key at all. Catches
    any future edit that re-introduces an endpoint-level key check."""
    client, _ = _app_with_key_behavior(monkeypatch, resolve_behavior=_ok_key)
    calls = []

    def spy(user):
        calls.append(user.get("id"))
        return "ok"

    monkeypatch.setattr(tamus_client, "resolve_user_key", spy)
    try:
        for _, q in REDIRECT_QUESTIONS:
            client.post("/api/chat", json={"message": q, "session_id": "s"}).json()
    finally:
        server.app.dependency_overrides.clear()
    assert calls == [], f"resolve_user_key called during redirect branch: {calls}"
