"""POST /api/settings/tamus/test — three failure modes must all return
`{ok: false, message: ...}` with HTTP 200 so CORS headers reach the browser
and the client sees a clean error, not "Failed to fetch".

Regression for an incident where a pasted key with non-ASCII characters
(smart quotes / NBSP) hit `httpx._models._normalize_header_value`,
raised `UnicodeEncodeError`, propagated out as a 500 that lost its CORS
header, and the frontend reported `Failed to fetch`.

    python -m pytest tests/test_tamus_test_endpoint.py -n 0
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "llhs_unit_unused")
import server  # noqa: E402
import tamus_client  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


USER = {
    "id": "u1",
    "email": "t@example.com",
    "name": "T",
    # The encrypted-key value is replaced per-test via monkeypatch of
    # tamus_client.decrypt_key, so a dummy string is fine.
    "tamus_api_key_encrypted": "ENC",
    "tamus_model_chat": tamus_client.DEFAULT_CHAT_MODEL,
}


@pytest.fixture
def client(monkeypatch):
    class FakeUsers:
        async def find_one(self, q):
            return dict(USER)

    class FakeDB:
        users = FakeUsers()

    monkeypatch.setattr(server, "db", FakeDB())
    monkeypatch.setattr(server.limiter, "enabled", False)
    server.app.dependency_overrides[server.current_user] = lambda: dict(USER)
    yield TestClient(server.app)
    server.app.dependency_overrides.clear()


def test_non_ascii_key_returns_200_with_clean_message(client, monkeypatch):
    """Pasted a key with a smart quote in it. Must come back as a 200 with
    `{ok: false, message: ...}` — not a 500 that strips CORS headers.
    The message must NOT contain the key."""
    bad_key = "sk-pa“ste-with-smart-quote-–-and-nbsp here"
    monkeypatch.setattr(tamus_client, "decrypt_key", lambda _: bad_key)

    res = client.post("/api/settings/tamus/test")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body == {"ok": False, "message": body["message"]}, body
    assert body["ok"] is False
    assert "invalid characters" in body["message"].lower(), body["message"]
    # The response must NEVER echo the key back.
    assert "sk-pa" not in body["message"]
    assert "paste" not in body["message"].lower()  # don't let the raw key leak via f-string


def test_slow_tamus_returns_200_with_timeout_message(client, monkeypatch):
    """Simulate a hung TAMU AI service — the test endpoint must still return
    a clean JSON answer, not time out the client's fetch."""
    import asyncio

    async def _timeout(*_args, **_kwargs):
        raise asyncio.TimeoutError()

    monkeypatch.setattr(tamus_client, "decrypt_key", lambda _: "sk-ascii-ok")
    monkeypatch.setattr(tamus_client, "chat", _timeout)

    res = client.post("/api/settings/tamus/test")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is False
    assert "timed out" in body["message"].lower() or "try again" in body["message"].lower()


def test_broken_client_returns_200_with_class_name_message(client, monkeypatch):
    """Any unexpected error in the TAMU client (TLS cert chain blow-up, DNS
    failure, …) still returns a clean 200 — never a 500."""
    async def _boom(*_args, **_kwargs):
        raise RuntimeError("some internal thing")

    monkeypatch.setattr(tamus_client, "decrypt_key", lambda _: "sk-ascii-ok")
    monkeypatch.setattr(tamus_client, "chat", _boom)

    res = client.post("/api/settings/tamus/test")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is False
    assert "RuntimeError" in body["message"]
    # Never echoes the exception message (which might reveal the key).
    assert "some internal thing" not in body["message"]


def test_no_key_saved_returns_clean_not_400(client, monkeypatch):
    """A new user with no key hits Test — should see a friendly message,
    not an HTTP 400 that spawns an error toast."""
    monkeypatch.setattr(tamus_client, "decrypt_key", lambda _: "sk-ascii-ok")
    no_key_user = {**USER, "tamus_api_key_encrypted": None}
    server.app.dependency_overrides[server.current_user] = lambda: no_key_user
    try:
        res = client.post("/api/settings/tamus/test")
        assert res.status_code == 200
        body = res.json()
        assert body == {"ok": False, "message": "No TAMU API key saved yet."}
    finally:
        server.app.dependency_overrides[server.current_user] = lambda: dict(USER)
