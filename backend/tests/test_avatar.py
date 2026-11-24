"""Avatar choice (PATCH /api/profile/avatar) and the daily avatar mood.
No running server or database: the endpoint test swaps in a fake users
collection and overrides the auth dependency.
    python -m pytest tests/test_avatar.py -n 0"""
import os
import sys
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "llhs_unit_unused")
import avatar  # noqa: E402
import daily_goals  # noqa: E402
import study_time  # noqa: E402

UTC = timezone.utc
NOW = datetime(2026, 10, 5, 18, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _freeze_study_now(monkeypatch):
    """Pin "today" (in the study TZ) to 2026-10-05 for every test here —
    `build_snapshot` and `daily_mood` now derive "today" from study_today(),
    not from a function parameter. 18:00 UTC on 2026-10-05 is 13:00 CDT —
    well inside the Chicago day."""
    monkeypatch.setattr(study_time, "_now_utc", lambda: NOW)


# ---- Choice and validation ---------------------------------------------
def test_patch_rejects_unknown_values_and_body_fields():
    with pytest.raises(ValidationError):
        avatar.AvatarPatch(hair="mohawk")
    for field in ("body", "size", "weight", "shape"):
        with pytest.raises(ValidationError):
            avatar.AvatarPatch(**{field: "slim"})


def test_options_have_no_body_axis():
    assert not {"body", "size", "weight", "shape", "build"} & set(avatar.OPTIONS)
    assert set(avatar.DEFAULT_AVATAR) == set(avatar.OPTIONS)


def test_merge_applies_patch_over_stored_or_default():
    merged = avatar.merge_avatar(None, avatar.AvatarPatch(hair="curly", glasses="round"))
    assert merged == {**avatar.DEFAULT_AVATAR, "hair": "curly", "glasses": "round"}
    again = avatar.merge_avatar({**merged, "skin": "not-a-tone", "junk": 1}, avatar.AvatarPatch(outfit="hoodie"))
    assert again["hair"] == "curly" and again["outfit"] == "hoodie"
    assert again["skin"] == avatar.DEFAULT_AVATAR["skin"] and "junk" not in again


# ---- Daily mood ----------------------------------------------------------
def snapshot(meals=(), acts=(), sleeps=(), plans=None):
    profile = {"plans": plans or {}}
    logs = {"food": list(meals), "move": list(acts), "rest": list(sleeps)}
    return daily_goals.build_snapshot(profile, logs)["mood"]


def at(day, **kw):
    return {"id": f"{day}-{len(kw)}-{sorted(kw.items())}", "created_at": f"2026-10-{day:02d}T12:00:00+00:00", **kw}


PLANS = {
    "food": [{"start_date": "2026-10-01", "enabled": True, "target": 1, "category": "vegetables"}],
    "move": [{"start_date": "2026-10-01", "enabled": True, "target": 30, "category": None}],
    "rest": [{"start_date": "2026-10-01", "enabled": True, "target": 8, "category": None}],
}


def test_no_logs_is_calm_never_negative():
    m = snapshot(plans=PLANS)
    assert m == {"date": "2026-10-05", "mood": "calm", "rings_closed": 0, "glow": False, "props": []}
    assert m["mood"] in avatar.MOODS


def test_mood_steps_with_rings_closed():
    veg = at(5, categories=["vegetables"])
    walk = at(5, minutes=30)
    sleep = at(5, hours=8)
    assert snapshot([veg], plans=PLANS)["mood"] == "content"
    assert snapshot([veg], [walk], plans=PLANS)["mood"] == "content"
    full = snapshot([veg], [walk], [sleep], plans=PLANS)
    assert full["mood"] == "energised" and full["glow"] and full["rings_closed"] == 3


def test_props_come_from_todays_logs_even_without_rings():
    m = snapshot([at(5, categories=["vegetables", "fruit"])], [at(5, minutes=10)], [at(5, hours=6)])
    assert m["mood"] == "calm" and m["props"] == ["salad", "sneakers", "rested"]


def test_mood_resets_each_day_and_ignores_simulated_wearable():
    yesterday = snapshot([at(4, categories=["vegetables"])], [at(4, minutes=60)], [at(4, hours=8)], plans=PLANS)
    assert yesterday["mood"] == "calm" and yesterday["props"] == []
    sim = snapshot(acts=[at(5, minutes=60, simulated=True)], sleeps=[at(5, hours=8, source="wearable")])
    assert sim["props"] == []


def test_skipped_meal_gives_no_salad():
    assert snapshot([at(5, categories=["vegetables"], skipped=True)])["props"] == []


# ---- Endpoint --------------------------------------------------------------
class FakeUsers:
    def __init__(self, doc):
        self.doc = doc

    async def update_one(self, query, update):
        assert query == {"id": self.doc["id"]}
        self.doc.update(update["$set"])


class FakeDB:
    def __init__(self, doc):
        self.users = FakeUsers(doc)


def test_patch_avatar_endpoint(monkeypatch):
    from fastapi.testclient import TestClient
    import server

    user = {"id": "u1", "email": "a@example.com", "name": "A"}
    monkeypatch.setattr(server, "db", FakeDB(user))
    server.app.dependency_overrides[server.current_user] = lambda: user
    try:
        client = TestClient(server.app)
        res = client.patch("/api/profile/avatar", json={"hair": "bun", "background": "mist"})
        assert res.status_code == 200
        assert res.json()["avatar"] == {**avatar.DEFAULT_AVATAR, "hair": "bun", "background": "mist"}
        assert user["avatar"]["hair"] == "bun"
        assert server.public_user(user)["avatar"] == user["avatar"]

        assert client.patch("/api/profile/avatar", json={"hair": "mohawk"}).status_code == 422
        assert client.patch("/api/profile/avatar", json={"body_size": "small"}).status_code == 422
        assert user["avatar"]["hair"] == "bun"
    finally:
        server.app.dependency_overrides.clear()
