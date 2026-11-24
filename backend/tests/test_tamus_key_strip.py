"""The save (PATCH /settings/tamus) and test (POST /settings/tamus/test)
endpoints auto-strip leading/trailing whitespace from a pasted TAMU key —
including non-breaking spaces, zero-width spaces and byte-order marks that
commonly ride along when a key is copied from a doc.

Interior non-ASCII characters are LEFT in place and still trip the
"invalid characters" error from `chat()`, so a typo in the middle of a
key can't be silently rewritten into a different one.

    python -m pytest tests/test_tamus_key_strip.py -n 0
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
    "tamus_model_chat": tamus_client.DEFAULT_CHAT_MODEL,
}


# ---- clean_api_key — the pure helper ---------------------------------------
def test_strip_ascii_whitespace():
    assert tamus_client.clean_api_key("  sk-abc  ") == "sk-abc"
    assert tamus_client.clean_api_key("\tsk-abc\n") == "sk-abc"
    assert tamus_client.clean_api_key("\r\nsk-abc\r\n") == "sk-abc"


def test_strip_non_breaking_space():
    # NBSP (U+00A0) at both ends — the exact character that broke the live Test.
    nbsp = " "
    assert tamus_client.clean_api_key(f"{nbsp}sk-abc{nbsp}") == "sk-abc"


def test_strip_zero_width_characters():
    for cp in ("​", "‌", "‍", "﻿", "⁠"):
        assert tamus_client.clean_api_key(f"{cp}sk-abc{cp}") == "sk-abc", f"did not strip U+{ord(cp):04X}"


def test_strip_ideographic_and_narrow_spaces():
    # Narrow no-break (U+202F), medium math (U+205F), ideographic (U+3000),
    # en space (U+2002), em space (U+2003), line sep (U+2028), para sep (U+2029).
    for cp in (" ", " ", "　", " ", " ", " ", " "):
        assert tamus_client.clean_api_key(f"{cp}sk-abc{cp}") == "sk-abc", f"did not strip U+{ord(cp):04X}"


def test_strip_mixed_whitespace_runs():
    # Several invisibles stacked at both ends.
    assert tamus_client.clean_api_key("  ​\tsk-abc\n ​ ") == "sk-abc"


def test_strip_leaves_interior_characters_alone():
    # Smart quote INSIDE the key must stay — the ASCII check will catch it.
    key = "sk-abc“def"
    assert tamus_client.clean_api_key(f"  {key}  ") == key


def test_strip_handles_none_and_empty():
    assert tamus_client.clean_api_key(None) == ""
    assert tamus_client.clean_api_key("") == ""
    # A key that's entirely whitespace collapses to empty.
    assert tamus_client.clean_api_key("  ​") == ""


def test_strip_is_idempotent():
    # Running the helper twice must match running it once — essential because
    # the test endpoint strips a (possibly pre-cleaned) stored key.
    once = tamus_client.clean_api_key(" sk-abc​")
    twice = tamus_client.clean_api_key(once)
    assert once == twice == "sk-abc"


# ---- Save endpoint (PATCH /settings/tamus) ---------------------------------
@pytest.fixture
def client(monkeypatch):
    stored = {"doc": dict(USER)}

    class FakeUsers:
        async def find_one(self, q):
            return dict(stored["doc"])

        async def update_one(self, q, update):
            stored["doc"].update(update.get("$set", {}))

    class FakeDB:
        users = FakeUsers()

    monkeypatch.setattr(server, "db", FakeDB())
    monkeypatch.setattr(server.limiter, "enabled", False)
    server.app.dependency_overrides[server.current_user] = lambda: dict(stored["doc"])
    client = TestClient(server.app)
    bundle = type("B", (), {"client": client, "stored": stored})()
    yield bundle
    server.app.dependency_overrides.clear()


def test_save_strips_wrapping_invisibles_before_encrypting(client, monkeypatch):
    """A padded key is stored in the same encrypted form as the already-clean one."""
    captured: list = []

    def fake_encrypt(k):
        captured.append(k)
        return f"ENC({k})"

    monkeypatch.setattr(tamus_client, "encrypt_key", fake_encrypt)

    padded = " ​ sk-clean-key ​ "
    res = client.client.patch("/api/settings/tamus", json={"api_key": padded})
    assert res.status_code == 200
    assert captured == ["sk-clean-key"], f"saved form was {captured!r}, want the stripped key"


def test_save_empty_after_strip_returns_400(client, monkeypatch):
    """A key that passes Pydantic's min_length=8 but strips down to nothing
    (an entirely-invisible paste) must be rejected with a plain 400, not a
    silent empty encrypted blob."""
    monkeypatch.setattr(tamus_client, "encrypt_key", lambda k: f"ENC({k})")
    # 10 chars, every one an invisible — passes Pydantic min_length=8,
    # then clean_api_key() strips the lot and the handler returns 400.
    all_whitespace = "\xa0 \u200b\xa0 \u200b\xa0 \u200b\xa0 "
    assert len(all_whitespace) >= 8
    res = client.client.patch("/api/settings/tamus", json={"api_key": all_whitespace})
    assert res.status_code == 400, res.text
    assert "empty" in res.json()["detail"].lower()


def test_save_leaves_interior_invalid_characters_for_test_to_catch(client, monkeypatch):
    """Interior smart quote should survive the save (so the ASCII check still
    sees it on first use), not be silently rewritten by the strip."""
    captured: list = []
    monkeypatch.setattr(tamus_client, "encrypt_key", lambda k: (captured.append(k) or f"ENC({k})"))
    key_with_smart_quote = "sk-abc“def"
    res = client.client.patch("/api/settings/tamus", json={"api_key": f"  {key_with_smart_quote}  "})
    assert res.status_code == 200
    assert captured == [key_with_smart_quote]


# ---- Test endpoint (POST /settings/tamus/test) ------------------------------
def test_test_endpoint_strips_a_pre_fix_dirty_stored_key(client, monkeypatch):
    """A key saved before this fix landed will have trailing invisibles in
    the encrypted blob. The test endpoint must strip them before use —
    otherwise an existing user whose Test used to crash would still crash."""
    stored_dirty = "sk-already-saved-with-nbsp "
    sent_to_chat: list = []

    async def fake_chat(api_key, *_a, **_kw):
        sent_to_chat.append(api_key)
        return "HELLO"

    monkeypatch.setattr(tamus_client, "decrypt_key", lambda _: stored_dirty)
    monkeypatch.setattr(tamus_client, "chat", fake_chat)
    client.stored["doc"]["tamus_api_key_encrypted"] = "ENC(dirty)"

    res = client.client.post("/api/settings/tamus/test")
    assert res.status_code == 200
    body = res.json()
    assert body == {"ok": True, "message": "HELLO"}, body
    assert sent_to_chat == ["sk-already-saved-with-nbsp"], (
        "test endpoint must strip the stored key before passing to chat()"
    )


def test_test_endpoint_still_reports_invalid_interior_character(client, monkeypatch):
    """Keep the invalid-character error for anything strip() didn't catch."""
    # An interior smart quote survives the strip (which only touches the ends)
    # and must still be caught by chat()'s ASCII check as before.
    stored_mid_dirty = f" sk-abc“def "  # padded ends + interior smart quote
    monkeypatch.setattr(tamus_client, "decrypt_key", lambda _: stored_mid_dirty)
    client.stored["doc"]["tamus_api_key_encrypted"] = "ENC(dirty)"
    # DO NOT monkeypatch chat — we want the real ASCII pre-check to fire.

    res = client.client.post("/api/settings/tamus/test")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is False
    assert "invalid characters" in body["message"].lower(), body["message"]
    # And of course the key is not echoed.
    assert "sk-abc" not in body["message"]
