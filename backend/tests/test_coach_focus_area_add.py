"""Focus areas: one of the eight areas at a time (focus_areas.py).

- The candidates are areas with room for improvement, most room first,
  labels only; the first is suggested.
- Saving an area stores its component ids too, plus the goal and plan.
- Changing area without a new goal clears the old goal; same area keeps it.
- The Coach's set_focus_areas action proposes one area; the area they
  already have, or a made-up one, never becomes a card.
- Dismiss leaves the database unchanged; SOURCE: never leaks.

    python -m pytest tests/test_coach_focus_area_add.py -n 0
"""
from __future__ import annotations

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "llhs_unit_unused")
import server  # noqa: E402
import tamus_client  # noqa: E402
import coach_kb  # noqa: E402
import focus_areas  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


# ---- Minimal in-memory stand-in for Motor collections ---------------------
def _match(doc, query):
    for k, v in query.items():
        have = doc.get(k)
        if isinstance(v, dict):
            for op, arg in v.items():
                if op == "$gte" and not (have is not None and have >= arg):
                    return False
                if op == "$lte" and not (have is not None and have <= arg):
                    return False
                if op == "$ne" and have == arg:
                    return False
                if op == "$in" and have not in arg:
                    return False
        elif have != v:
            return False
    return True


class Cursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, key, direction=1):
        self.docs = sorted(self.docs, key=lambda d: d.get(key) or "", reverse=direction == -1)
        return self

    async def to_list(self, n):
        return list(self.docs[:n] if n else self.docs)


class Coll:
    def __init__(self):
        self.docs = []

    def find(self, query=None, *_):
        return Cursor([d for d in self.docs if _match(d, query or {})])

    async def find_one(self, query=None, sort=None):
        docs = [d for d in self.docs if _match(d, query or {})]
        if sort:
            key, direction = sort[0]
            docs.sort(key=lambda d: d.get(key) or "", reverse=direction == -1)
        return docs[0] if docs else None

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def update_one(self, query, update, upsert=False):
        for d in self.docs:
            if _match(d, query):
                for k, v in update.get("$set", {}).items():
                    d[k] = v
                for k, v in update.get("$inc", {}).items():
                    d[k] = d.get(k, 0) + v

    async def count_documents(self, query):
        return sum(1 for d in self.docs if _match(d, query))


class FakeDB:
    def __init__(self):
        self._c = {}

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return self._c.setdefault(name, Coll())


# A full HEI assessment where whole_grains, greens_beans and sodium are
# below benchmark (focus candidates) and total_fruits + dairy are strengths.
BASELINE_SCORES = {
    "total_fruits": 4.5, "whole_fruits": 2.0, "total_vegetables": 2.5,
    "greens_beans": 1.1, "whole_grains": 1.0, "dairy": 7.0,
    "total_protein_foods": 4.0, "seafood_plant_proteins": 2.0,
    "fatty_acids": 3.0, "refined_grains": 5.0, "sodium": 2.3,
    "added_sugars": 7.0, "saturated_fats": 5.0,
}


def _user(area_id):
    return {
        "id": "u1", "email": "t@example.com", "name": "T",
        "focus_area": area_id, "focus_areas": ["whole_grains", "refined_grains"] if area_id == "grains" else [],
        "focus_goal": {"goal": "Brown rice at dinner", "plan": "Mon/Wed/Fri"} if area_id else {},
        "allergy_terms": [], "tamus_api_key_encrypted": "x",
    }


@pytest.fixture
def app(monkeypatch):
    """Wires an in-memory DB with Maya-like state, a stubbed LLM whose
    reply can be set per-test, and returns the test client + a mutable
    user doc + the recorded LLM calls."""
    db = FakeDB()
    user = _user("grains")
    db.users.docs.append(dict(user))
    db.hei_assessments.docs.append({
        "user_id": "u1", "assessment_type": "baseline", "components": BASELINE_SCORES,
        "recorded_at": "2026-09-22T12:00:00+00:00",
    })
    monkeypatch.setattr(server, "db", db)
    monkeypatch.setattr(server.limiter, "enabled", False)
    monkeypatch.setattr(tamus_client, "resolve_user_key", lambda u: "key")

    reply = {"text": ""}

    async def fake_llm(user, system, user_text, session_id, history=None):
        return reply["text"]

    monkeypatch.setattr(server, "run_llm", fake_llm)
    server.app.dependency_overrides[server.current_user] = lambda: db.users.docs[0]
    client = TestClient(server.app)
    bundle = type("A", (), {"client": client, "db": db, "reply": reply})()
    yield bundle
    server.app.dependency_overrides.clear()


def ask(app, msg: str, session: str = "s1"):
    r = app.client.post("/api/chat", json={"message": msg, "session_id": session})
    assert r.status_code == 200, r.text
    return r.json()


def set_coach_reply(app, prose: str, action_payload: dict | None = None, source="greens_beans"):
    """Build a Coach-style raw reply the way the real LLM would."""
    tail = f"SOURCE: {source}"
    if action_payload is not None:
        import json as _json
        tail += "\nACTION_JSON: " + _json.dumps({"type": "set_focus_areas", "payload": action_payload})
    app.reply["text"] = f"{prose}\n{tail}"


# ---- Candidates and saving ------------------------------------------------
def test_candidates_are_areas_most_room_first_without_numbers(app):
    r = app.client.get("/api/assessments/hei2020/focus-candidates").json()
    ids = [c["id"] for c in r["candidates"]]
    # Ranked by share of the area's points missed: sodium 7.7/10 before
    # grains 14/20; dairy and added sugars are at or above the benchmark.
    assert ids[:2] == ["sodium", "grains"] and r["candidates"][0]["suggested"]
    assert "dairy" not in ids and "added_sugars" not in ids
    assert not any(c["suggested"] for c in r["candidates"][1:])
    assert set(r["candidates"][0]) == {"id", "label", "description", "suggested"}
    assert r["current"]["id"] == "grains" and r["goal"] == "Brown rice at dinner"
    assert (r["min_selection"], r["max_selection"]) == (1, 1)


def test_saving_an_area_stores_components_goal_and_plan(app):
    r = app.client.post("/api/profile/focus-areas",
                        json={"area_id": "vegetables_beans", "goal": " Beans twice a week ", "plan": "Chili on Sundays"})
    assert r.status_code == 200, r.text
    u = app.db.users.docs[0]
    assert u["focus_area"] == "vegetables_beans"
    assert u["focus_areas"] == ["total_vegetables", "greens_beans"]
    assert u["focus_goal"] == {"goal": "Beans twice a week", "plan": "Chili on Sundays"}


def test_changing_area_without_a_goal_clears_it_keeping_area_keeps_it(app):
    app.client.post("/api/profile/focus-areas", json={"area_id": "grains"})
    assert app.db.users.docs[0]["focus_goal"]["goal"] == "Brown rice at dinner"
    app.client.post("/api/profile/focus-areas", json={"area_id": "sodium"})
    assert app.db.users.docs[0]["focus_goal"] == {}


def test_unknown_area_is_rejected(app):
    r = app.client.post("/api/profile/focus-areas", json={"area_id": "whole_grains"})
    assert r.status_code == 422
    assert app.db.users.docs[0]["focus_area"] == "grains"


def test_food_domain_shows_the_eight_areas_only_and_no_numbers(app):
    food = app.client.get("/api/domains/food").json()
    assert food["focus_area"]["id"] == "grains" and food["focus_area"]["goal"] == "Brown rice at dinner"
    strengths = [a["id"] for a in food["strengths"]]
    room = [a["id"] for a in food["room_to_grow"]]
    others = [a["id"] for a in food["other_areas"]]
    # Every area in exactly one group: focus + strengths + room-to-grow +
    # other areas = 8. The nutrition team's 2026-11-06 rank-based model
    # (item 2) splits "the rest" into room-to-grow (bottom of the rank)
    # and other (middle), where it used to be lumped together.
    assert sorted(["grains"] + strengths + room + others) == sorted(a["id"] for a in focus_areas.FOCUS_AREAS)
    assert "dairy" in strengths and "added_sugars" in strengths  # top of the rank
    assert "sodium" in room  # bottom of the rank
    assert "fruit" in others  # middle of the rank, not a focus candidate
    # Bars and fill fractions are OK (they're how the bar is drawn, not a
    # number shown to the student); everything else has to be numeric-free.
    body_no_bars = {k: v for k, v in food.items() if k not in ("disclaimer", "bars")}
    assert not re.search(r"\d", str(body_no_bars))
    assert "whole_grains" not in str({k: v for k, v in food.items() if k != "bars"})
    # Someone who picked components before the eight areas existed chooses again.
    app.db.users.docs[0].update({"focus_area": None, "focus_areas": ["sodium", "dairy"]})
    food = app.client.get("/api/domains/food").json()
    assert food["needs_focus_selection"] and food["focus_area"] is None
    assert len(food["strengths"]) + len(food["room_to_grow"]) + len(food["other_areas"]) == 8


# ---- Coach ------------------------------------------------------------------
def test_coach_proposes_one_area_and_confirm_saves_it(app):
    set_coach_reply(app, "Tap Confirm to make Vegetables and beans your focus.",
                    action_payload={"area_id": "vegetables_beans"})
    r = ask(app, "please make greens_beans my focus area")
    pa = r["pending_action"]
    assert pa == {"type": "set_focus_areas", "payload": {"area_id": "vegetables_beans", "goal": None, "plan": None},
                  "summary": "Change your focus area to Vegetables and beans"}
    assert app.client.post("/api/chat/confirm-action", json=pa).status_code == 200
    assert app.db.users.docs[0]["focus_area"] == "vegetables_beans"


def test_coach_no_card_for_the_area_they_have_or_a_made_up_one(app):
    set_coach_reply(app, "Tap Confirm to focus on Grains.", action_payload={"area_id": "grains"})
    r = ask(app, "please add whole_grains as my focus area")
    assert r["pending_action"] is None and "already your focus area" in r["answer"]
    set_coach_reply(app, "Tap Confirm.", action_payload={"area_id": "whole_grains"})
    assert ask(app, "please add whole_grains as my focus area")["pending_action"] is None
    assert app.db.users.docs[0]["focus_area"] == "grains"


def test_dismiss_does_not_write_to_db(app):
    set_coach_reply(app, "Tap Confirm.", action_payload={"area_id": "sodium"})
    assert ask(app, "please make greens_beans my focus area")["pending_action"] is not None
    assert app.db.users.docs[0]["focus_area"] == "grains"


def test_old_component_payload_to_confirm_action_is_a_clean_422(app):
    body = {"type": "set_focus_areas", "payload": {"component_ids": ["greens_beans"]}}
    r = app.client.post("/api/chat/confirm-action", json=body)
    assert r.status_code == 422 and isinstance(r.json().get("detail"), str)
    assert app.db.users.docs[0]["focus_area"] == "grains"


# ---- 8. SOURCE: never leaks to the user text ------------------------------
def test_no_message_shown_contains_source_line(app):
    """Several awkward SOURCE: placements (end, inline, with surrounding
    punctuation, duplicate) all get stripped from the student-facing text."""
    cases = [
        "Yes, Greens & Beans is a great focus.\nSOURCE: greens_beans",
        "Yes. SOURCE: greens_beans",
        "Yes.\n   SOURCE: greens_beans   \n",
        "Yes.\nSOURCE: greens_beans\nSOURCE: whole_grains",
        "Short reply.\n*SOURCE: greens_beans*",
    ]
    for raw in cases:
        app.reply["text"] = raw
        r = ask(app, "any question")
        assert "SOURCE:" not in r["answer"], f"SOURCE leaked for raw={raw!r} → answer={r['answer']!r}"
