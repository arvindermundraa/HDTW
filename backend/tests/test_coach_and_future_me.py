"""The Coach (POST /api/chat, KB-grounded) and Future Me (the digital twin,
/api/future-me). Runs the real endpoints against an in-memory fake database,
with the LLM stubbed, so no server, Mongo or TAMU key is needed.
    python -m pytest tests/test_coach_and_future_me.py -n 0"""
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "llhs_unit_unused")
import server  # noqa: E402
import tamus_client  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


# ---- A tiny in-memory stand-in for the Motor collections used here --------
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

    async def delete_one(self, query):
        for i, d in enumerate(self.docs):
            if _match(d, query):
                del self.docs[i]
                return


class FakeDB:
    def __init__(self):
        self._c = {}

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return self._c.setdefault(name, Coll())

    def __getitem__(self, name):
        return getattr(self, name)


USER = {"id": "u1", "email": "t@example.com", "name": "T", "focus_area": "grains",
        "focus_areas": ["whole_grains", "refined_grains"],
        "allergy_terms": [], "tamus_api_key_encrypted": "x"}
SCORES = {"whole_grains": 1.1, "refined_grains": 5.0, "sodium": 2.3, "total_fruits": 4.5, "dairy": 7.0}


@pytest.fixture
def app(monkeypatch):
    db = FakeDB()
    db.users.docs.append(dict(USER))
    db.hei_assessments.docs.append({"user_id": "u1", "assessment_type": "baseline", "components": SCORES,
                                    "recorded_at": "2026-09-22T12:00:00+00:00"})
    monkeypatch.setattr(server, "db", db)
    monkeypatch.setattr(server.limiter, "enabled", False)
    monkeypatch.setattr(tamus_client, "resolve_user_key", lambda u: "key")
    calls = []

    async def fake_llm(user, system, user_text, session_id, history=None):
        calls.append({"system": system, "text": user_text, "history": history or []})
        return app.reply

    monkeypatch.setattr(server, "run_llm", fake_llm)
    server.app.dependency_overrides[server.current_user] = lambda: dict(USER)
    client = TestClient(server.app)
    app = type("App", (), {"client": client, "db": db, "calls": calls, "reply": ""})()
    yield app
    server.app.dependency_overrides.clear()


def ask(app, message, session="s1"):
    r = app.client.post("/api/chat", json={"message": message, "session_id": session})
    assert r.status_code == 200, r.text
    return r.json()


# ---- Coach ---------------------------------------------------------------------
def test_coach_answers_from_the_kb_and_names_the_entry(app):
    app.reply = "Yes, brown rice is a whole grain.\nSOURCE: whole_grains"
    d = ask(app, "Is brown rice a whole grain?")
    assert d["answer"] == "Yes, brown rice is a whole grain."
    assert d["citations"][0]["title"] == "Whole grains basics"
    assert "[whole_grains]" in app.calls[0]["system"]  # the retrieved entry was given to the model


def test_coach_keeps_memory_per_session(app):
    app.reply = "Brown rice counts.\nSOURCE: whole_grains"
    ask(app, "Is brown rice a whole grain?")
    ask(app, "And oatmeal, is that a whole grain?")
    history = app.calls[1]["history"]
    assert [h["role"] for h in history] == ["user", "assistant"]
    assert history[0]["content"] == "Is brown rice a whole grain?"
    ask(app, "Is brown rice a whole grain?", session="other")
    assert app.calls[2]["history"] == []  # a new session starts fresh


def test_coach_history_is_capped_at_ten_messages(app):
    app.reply = "Whole grains count.\nSOURCE: whole_grains"
    for i in range(7):
        ask(app, f"Is brown rice a whole grain? ({i})")
    assert len(app.calls[-1]["history"]) == 10


def test_coach_says_it_does_not_know_and_never_calls_the_model(app):
    d = ask(app, "How do I fix my car?")
    # Reworded NOT_FOUND (nutrition team, 2026-10-29): acknowledges the
    # question is outside scope AND offers concrete topics the Coach can
    # help with, instead of a vague "I don't have information" dodge.
    assert "outside what my reviewed notes cover" in d["answer"]
    assert "study team" in d["answer"]
    assert d["citations"] == [] and app.calls == []


@pytest.mark.parametrize("question", ["How many calories are in rice?", "How do I lose weight?",
                                      "Should I take a vitamin supplement?"])
def test_coach_declines_out_of_scope_questions(app, question):
    d = ask(app, question)
    assert d["citations"] == [] and app.calls == []
    # The scope-decline branch returns the nutrition team's reviewed
    # DECLINE copy verbatim (2026-11-06, Follow-ups item 2). The server
    # skips the drift-catcher guardrail on this branch — reviewed copy
    # intentionally names what LLHS doesn't do ("weight loss", "calorie
    # targets"). The redirect texts are instead validated once by
    # test_future_me_redirects.py (wording check + required-cues check).
    assert d["answer"], question
    assert d["answer"] != server._SAFE_FALLBACK_REPLY, question


def test_coach_reply_passes_the_guardrail(app):
    app.reply = "A cup has 200 calories.\nSOURCE: whole_grains"
    d = ask(app, "Is brown rice a whole grain?")
    assert d["answer"] == server._SAFE_FALLBACK_REPLY and d["citations"] == []
    assert app.db.guardrail_blocks.docs


def test_coach_actions_stay_proposals(app):
    app.reply = ('Sure, I can log that.\nSOURCE: whole_grains\nACTION_JSON: {"type": "log_meal", "payload": '
                 '{"name": "Brown rice bowl", "categories": ["whole_grains"], "meal_type": "lunch"}}')
    d = ask(app, "Is brown rice a whole grain? log my brown rice bowl")
    assert d["pending_action"]["type"] == "log_meal"
    assert not app.db.meals.docs  # nothing written until confirmed


def test_coach_without_a_key_explains_how_to_add_one(app, monkeypatch):
    def no_key(u):
        raise tamus_client.TamusKeyRequiredError("no key")
    monkeypatch.setattr(tamus_client, "resolve_user_key", no_key)
    d = ask(app, "Is brown rice a whole grain?")
    assert d["tamus_key_required"] is True and "Settings" in d["answer"]


def test_future_me_suggests_the_three_study_team_prompts(app):
    prompts = app.client.get("/api/chat/suggested-prompts").json()["prompts"]
    assert prompts == ["What's one thing I could work on this week?",
                       "How can I change my regular meals to include more whole grains?",
                       "Help me check in on my progress"]
    assert all(server._guardrail_violation_type(p) is None for p in prompts)
    for area, q in server.FOCUS_AREA_PROMPT.items():
        assert server.COACH_KB.retrieve(q), f"{area}: the KB can't answer its starter question"
    for cid, q in server.COACH_FOCUS_QUESTIONS.items():
        assert server.COACH_KB.retrieve(q), f"{cid}: the KB can't answer its own starter question"


def test_progress_questions_use_their_own_data_not_the_kb(app):
    app.reply = "You're working on grains. Try brown rice at lunch this week.\nSOURCE: none"
    d = ask(app, "Help me check in on my progress")
    assert "working on grains" in d["answer"]  # reached the model instead of "I don't have information"
    system = app.calls[-1]["system"]
    assert "You are Future Me" in system and "Focus area: Grains" in system
    assert "Program: week" in system and "meals logged on" in system


# ---- Future Me -------------------------------------------------------------------
NUM = re.compile(r"\d")


def test_future_me_home_has_three_domains_and_no_scores(app):
    d = app.client.get("/api/future-me").json()
    assert set(d) >= {"week_line", "eat", "move", "sleep", "scenarios", "checkin"}
    assert "participant_score" not in str(d) and "maximum_score" not in str(d)
    assert 3 <= len(d["scenarios"]) <= 4
    assert [s["id"] for s in d["scenarios"]][:2] == ["hei:whole_grains", "hei:refined_grains"]


def test_what_if_shows_direction_only(app):
    app.reply = "Swapping in a whole grain would move your Whole Grains closer to where you want it."
    d = app.client.post("/api/future-me/what-if", json={"scenario_id": "hei:whole_grains"}).json()
    assert d["phrased_by"] == "llm" and not NUM.search(d["text"])


def test_what_if_never_passes_on_a_number(app):
    app.reply = "That would take your score from 1.1 to 3/10!"
    d = app.client.post("/api/future-me/what-if", json={"scenario_id": "hei:whole_grains"}).json()
    assert d["phrased_by"] == "engine"
    assert "closer to your goal" in d["text"] and not NUM.search(d["text"])


def test_what_if_rejects_unknown_scenarios(app):
    r = app.client.post("/api/future-me/what-if", json={"scenario_id": "hei:dairy"})  # not a focus area
    assert r.status_code == 404


# ---- Guardrail on the other AI endpoints ---------------------------------------
def test_categorize_text_name_is_guardrailed(app):
    app.reply = '{"categories": ["vegetables"], "suggested_name": "Guilt-free salad", "confidence": 0.9}'
    d = app.client.post("/api/meals/categorize-text", json={"description": "salad"}).json()
    assert d["suggested_name"] == "salad"
    assert d["categories"] == ["vegetables"]


def test_review_plate_text_is_guardrailed(app):
    app.reply = ('{"has_produce": true, "summary": "Keep it light: about 450 kcal.", '
                 '"strengths": ["Has vegetables"], "suggestions": ["Cut back on the rice", "Add a fruit"]}')
    d = app.client.post("/api/dining/review-plate", json={"item_names": ["Rice", "Broccoli"]}).json()
    assert "kcal" not in d["summary"]
    assert d["suggestions"] == ["Add a fruit"] and d["strengths"] == ["Has vegetables"]
