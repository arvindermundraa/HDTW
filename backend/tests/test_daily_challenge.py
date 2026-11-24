"""Daily-challenge endpoint — time zone, idempotency, race and date-field rules.

Covers the four fixes in `fix/daily-challenge-tz-and-index`:

1. "Today" is a single study time zone (America/Chicago) for both reading
   today's challenge and validating the answer. A student playing at 8 PM
   Chicago time (01:00 UTC the next day) must still see today's question.
2. Answering twice awards the fixed daily-challenge points only once.
3. If two answer requests race and both pass the `completions.find_one`
   guard, only one `completions.insert_one` wins (the other hits the
   partial unique index and raises DuplicateKeyError); `awarded` stays 0
   on the losing request.
4. The POST body is `{challenge_id, choice_id}` — `date` is not accepted.
   An older client that still sends it gets HTTP 422.

Run:
    python -m pytest tests/test_daily_challenge.py -n 0
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

import pytest
from pymongo.errors import DuplicateKeyError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "llhs_unit_unused")
import server  # noqa: E402
import study_time  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


# --- Minimal in-memory stand-in for the Motor collections used by the handler.
def _match(doc, query):
    for k, v in query.items():
        if doc.get(k) != v:
            return False
    return True


class Coll:
    def __init__(self):
        self.docs = []
        # Partial unique indexes: list of (filter_dict, [key_fields]).
        # Mirrors the partialFilterExpression on completions created at
        # startup for daily_challenge rows.
        self._unique_partials: list[tuple[dict, list[str]]] = []

    def add_unique_partial(self, filter_: dict, keys: list[str]):
        self._unique_partials.append((filter_, keys))

    async def find_one(self, query=None, sort=None):
        hits = [d for d in self.docs if _match(d, query or {})]
        return hits[0] if hits else None

    async def insert_one(self, doc):
        for filter_, keys in self._unique_partials:
            if not _match(doc, filter_):
                continue
            doc_key = tuple(doc.get(k) for k in keys)
            for existing in self.docs:
                if _match(existing, filter_) and tuple(existing.get(k) for k in keys) == doc_key:
                    raise DuplicateKeyError(f"duplicate on {keys}")
        self.docs.append(dict(doc))

    async def update_one(self, query, update, upsert=False):
        for d in self.docs:
            if _match(d, query):
                for k, v in update.get("$set", {}).items():
                    d[k] = v
                for k, v in update.get("$inc", {}).items():
                    d[k] = d.get(k, 0) + v
                return
        if upsert:
            self.docs.append({**query, **update.get("$set", {})})


class FakeDB:
    def __init__(self):
        self._c: dict[str, Coll] = {}
        self.completions.add_unique_partial({"kind": "daily_challenge"}, ["user_id", "ref"])

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return self._c.setdefault(name, Coll())

    def __getitem__(self, name):
        return getattr(self, name)


USER = {"id": "u1", "email": "t@example.com", "name": "T", "points": 0, "badges": []}


def _first_pool_challenge_id() -> str:
    pool = server._GAMES_CONTENT.get("daily_challenges", {}).get("pool", [])
    assert pool, "games.json has no daily_challenges.pool entries — fix the fixture, not this test"
    return pool[0]["id"]


@pytest.fixture
def app(monkeypatch):
    """Fresh in-memory DB + stubbed current_user + patchable clock."""
    db = FakeDB()
    db.users.docs.append(dict(USER))
    monkeypatch.setattr(server, "db", db)
    monkeypatch.setattr(server.limiter, "enabled", False)
    server.app.dependency_overrides[server.current_user] = lambda: dict(USER)
    # Pin the clock to a known Chicago evening: 2026-10-10 20:00 CDT =
    # 2026-10-11 01:00 UTC. CDT (UTC-5) is in effect until Nov 2 2026, so
    # this stays before DST changes. The default is overridden per-test.
    clock = {"now": datetime(2026, 10, 11, 1, 0, 0, tzinfo=timezone.utc)}
    # Patch both: server.now_utc for `created_at` timestamps on inserts, and
    # study_time._now_utc for the day/week boundary helpers that server imports.
    monkeypatch.setattr(server, "now_utc", lambda: clock["now"])
    monkeypatch.setattr(study_time, "_now_utc", lambda: clock["now"])
    client = TestClient(server.app)
    bundle = type("App", (), {"client": client, "db": db, "clock": clock})()
    yield bundle
    server.app.dependency_overrides.clear()


def _get_challenge(app) -> dict:
    r = app.client.get("/api/games/daily-challenge")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["challenge"] is not None, "games.json pool is empty — fix the fixture"
    return data["challenge"]


def _correct_choice_id(challenge: dict) -> str:
    # The GET response strips `correct`, so look it up from the server-side
    # content. The handler validates `choice_id` against the same source.
    pool = server._GAMES_CONTENT["daily_challenges"]["pool"]
    source = next(c for c in pool if c["id"] == challenge["id"])
    return next(c["id"] for c in source["choices"] if c.get("correct"))


# --- 1. Study time zone -------------------------------------------------------
def test_8pm_chicago_counts_as_todays_challenge(app):
    """At 01:00 UTC on 2026-10-11, Chicago is still 20:00 on 2026-10-10 (CDT).
    The GET and POST must agree the day is 2026-10-10, and the answer must be
    accepted — not 404'd as 'that daily challenge isn't today's'."""
    app.clock["now"] = datetime(2026, 10, 11, 1, 0, 0, tzinfo=timezone.utc)
    challenge = _get_challenge(app)
    assert challenge["date"] == "2026-10-10", (
        f"GET returned date {challenge['date']}; the study TZ is America/Chicago "
        "and 01:00 UTC on 2026-10-11 is 20:00 on 2026-10-10 in Chicago."
    )
    r = app.client.post(
        "/api/games/daily-challenge/answer",
        json={"challenge_id": challenge["id"], "choice_id": _correct_choice_id(challenge)},
    )
    assert r.status_code == 200, r.text
    assert r.json()["correct"] is True
    assert r.json()["points_awarded"] == server.DAILY_CHALLENGE_POINTS


# --- 2. Idempotency on repeated correct answer --------------------------------
def test_answering_correctly_twice_awards_points_only_once(app):
    challenge = _get_challenge(app)
    correct = _correct_choice_id(challenge)
    first = app.client.post(
        "/api/games/daily-challenge/answer",
        json={"challenge_id": challenge["id"], "choice_id": correct},
    )
    second = app.client.post(
        "/api/games/daily-challenge/answer",
        json={"challenge_id": challenge["id"], "choice_id": correct},
    )
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["points_awarded"] == server.DAILY_CHALLENGE_POINTS
    assert second.json()["points_awarded"] == 0
    # And the user's points on `db.users` tally with only one award.
    user_doc = app.db.users.docs[0]
    assert user_doc["points"] == server.DAILY_CHALLENGE_POINTS


# --- 3. Race: both pass find_one, only one wins the index --------------------
def test_two_simultaneous_answers_award_points_only_once(app, monkeypatch):
    """Simulate two parallel requests both passing the pre-check (no completion
    row visible yet) and both reaching `insert_one`. The partial unique index
    on completions (user_id, ref) where kind="daily_challenge" lets exactly one
    insert succeed; the other raises DuplicateKeyError. The handler catches
    DuplicateKeyError and leaves `awarded` at 0 for the losing request."""
    challenge = _get_challenge(app)
    correct = _correct_choice_id(challenge)

    # Force find_one to return None for the completions guard — the race
    # window would normally be sub-millisecond on a real DB; the fake lets
    # us hold it open deterministically.
    real_find_one = app.db.completions.find_one

    async def blind_find_one(query=None, sort=None):
        if query and query.get("kind") == "daily_challenge":
            return None
        return await real_find_one(query, sort)

    monkeypatch.setattr(app.db.completions, "find_one", blind_find_one)

    first = app.client.post(
        "/api/games/daily-challenge/answer",
        json={"challenge_id": challenge["id"], "choice_id": correct},
    )
    second = app.client.post(
        "/api/games/daily-challenge/answer",
        json={"challenge_id": challenge["id"], "choice_id": correct},
    )
    assert first.status_code == 200 and second.status_code == 200
    awards = sorted([first.json()["points_awarded"], second.json()["points_awarded"]])
    assert awards == [0, server.DAILY_CHALLENGE_POINTS], (
        f"expected exactly one request to award points, got {awards}"
    )
    # Exactly one `completions` row for this (user, challenge, date).
    completions = [d for d in app.db.completions.docs if d.get("kind") == "daily_challenge"]
    assert len(completions) == 1


# --- 4. Client-supplied date is rejected --------------------------------------
def test_past_or_future_date_in_body_is_rejected(app):
    challenge = _get_challenge(app)
    correct = _correct_choice_id(challenge)
    for stray_date in ("2020-01-01", "2099-12-31", "yesterday"):
        r = app.client.post(
            "/api/games/daily-challenge/answer",
            json={"challenge_id": challenge["id"], "choice_id": correct, "date": stray_date},
        )
        assert r.status_code == 422, (
            f"client-supplied date {stray_date!r} should be rejected with 422 — "
            "the server owns 'today' now. Got: " + r.text
        )
        detail = r.json().get("detail", [])
        assert any(e.get("type") == "extra_forbidden" for e in detail), (
            f"expected extra_forbidden on `date`, got: {detail}"
        )
