"""From your own meals — the Future Me endpoints and the Coach's use of
them, run against the in-memory fake database with the LLM stubbed and
today's menus replayed from the captured live fixture.
    python -m pytest tests/test_from_your_meals.py -n 0"""
import os
import sys
from datetime import timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "llhs_unit_unused")
import server  # noqa: E402
import tamus_client  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from test_coach_and_future_me import FakeDB  # noqa: E402
from test_twin_suggest import MENUS  # noqa: E402

USER = {"id": "u1", "email": "t@example.com", "name": "T", "focus_area": "fats",
        "focus_areas": ["fatty_acids", "saturated_fats"], "allergy_terms": [], "tamus_api_key_encrypted": "x",
        "profile": {"kitchen_access": "none", "university_meal_plan": "yes"}}
SCORES = {"fatty_acids": 2.0, "saturated_fats": 3.0, "whole_grains": 1.1, "refined_grains": 5.0, "dairy": 7.0}


@pytest.fixture
def app(monkeypatch):
    db = FakeDB()
    db.users.docs.append(dict(USER))
    db.hei_assessments.docs.append({"user_id": "u1", "assessment_type": "baseline", "components": SCORES,
                                    "recorded_at": "2026-09-22T12:00:00+00:00"})
    monkeypatch.setattr(server, "db", db)
    monkeypatch.setattr(server.limiter, "enabled", False)
    monkeypatch.setattr(tamus_client, "resolve_user_key", lambda u: "key")

    async def menus_today():
        return MENUS
    monkeypatch.setattr(server, "_twin_menus_today", menus_today)
    calls = []

    async def fake_llm(user, system, user_text, session_id, history=None):
        calls.append({"system": system, "text": user_text})
        return app.reply
    monkeypatch.setattr(server, "run_llm", fake_llm)
    server.app.dependency_overrides[server.current_user] = lambda: dict(USER)
    client = TestClient(server.app)
    app = type("App", (), {"client": client, "db": db, "calls": calls, "reply": ""})()
    yield app
    server.app.dependency_overrides.clear()


def log(app, name, days_ago, slot="breakfast"):
    stamp = (server.study_today() - timedelta(days=days_ago)).isoformat() + "T14:00:00+00:00"
    app.db.meals.docs.append({"id": f"m{len(app.db.meals.docs)}", "user_id": "u1", "name": name, "items": [],
                              "meal_type": slot, "categories": ["dairy"], "created_at": stamp, "skipped": False})


def yogurt_week(app):
    for d in (1, 2, 4, 6, 8):
        log(app, "whole milk yogurt and granola", d)


# ---- Future Me home ----------------------------------------------------------------
def test_future_me_is_still_learning_before_three_logging_days(app):
    log(app, "whole milk yogurt", 1)
    fym = app.client.get("/api/future-me").json()["from_your_meals"]
    assert fym["status"] == "learning" and fym["days_logged"] == 1
    assert fym["note"] == "Log on 2 more days and I'll start noticing your regulars."
    assert fym["suggestions"] == [] or fym["suggestions"][0]["kind"] == "focus_add"  # never a habit claim yet


def test_future_me_shows_the_habit_the_swap_and_todays_menu(app):
    yogurt_week(app)
    d = app.client.get("/api/future-me").json()
    fym = d["from_your_meals"]
    assert fym["status"] == "ready" and fym["note"] is None and fym["menu_source"] == "live"
    assert fym["habits"][0]["label"] == "whole-milk yogurt" and fym["habits"][0]["times"] == 5
    s = fym["suggestions"][0]
    assert s["id"] == "fats_whole_milk_yogurt" and s["swap_label"] == "Try lower-fat yogurt"
    assert s["evidence"] == "You've logged whole-milk yogurt in 5 meals over the last 3 weeks, mostly at breakfast."
    assert s["on_menu_today"][0]["item_name"] == "Low Fat Vanilla Yogurt"
    assert s["on_menu_today"][0]["hall"] == "sbisa" and s["on_menu_today"][0]["period"] == "breakfast"
    assert s["on_menu_today"][0]["item_id"] == "sbisa_low_fat_vanilla_yogurt"  # deep-links into Build a Meal
    assert fym["setup"] == {"label": "no kitchen", "meal_plan": True}
    # Nothing numeric beyond counts of logged meals ever leaves this block.
    import json
    assert server._guardrail_violation_type(json.dumps(fym)) is None


def test_no_focus_area_yet_means_no_swaps_but_still_the_regulars(app):
    yogurt_week(app)
    server.app.dependency_overrides[server.current_user] = lambda: {**USER, "focus_area": None, "focus_areas": []}
    fym = app.client.get("/api/future-me/from-your-meals").json()
    assert fym["habits"][0]["food_id"] == "whole_milk_yogurt" and fym["suggestions"] == []
    assert "focus area" in fym["note"]


# ---- the student's taps ---------------------------------------------------------------------
def test_try_it_pins_the_swap_and_not_for_me_rests_it(app):
    yogurt_week(app)
    r = app.client.post("/api/future-me/swaps/trying", json={"swap_id": "fats_whole_milk_yogurt"})
    assert r.status_code == 200 and r.json()["status"] == "trying"
    assert r.json()["from_your_meals"]["suggestions"][0]["status"] == "trying"
    assert app.db.swap_plans.docs[0]["user_id"] == "u1" and app.db.swap_plans.docs[0]["status"] == "trying"

    r = app.client.post("/api/future-me/swaps/dismissed", json={"swap_id": "fats_whole_milk_yogurt"})
    ids = [s["id"] for s in r.json()["from_your_meals"]["suggestions"]]
    assert "fats_whole_milk_yogurt" not in ids and len(app.db.swap_plans.docs) == 1  # one row, latest status wins

    assert app.client.post("/api/future-me/swaps/trying", json={"swap_id": "made_up"}).status_code == 422
    assert app.client.post("/api/future-me/swaps/maybe", json={"swap_id": "fats_whole_milk_yogurt"}).status_code == 422


# ---- the Coach -----------------------------------------------------------------------------------
def test_coach_sees_the_regulars_the_swap_and_the_menu_item(app):
    yogurt_week(app)
    app.reply = ("You usually have whole-milk yogurt; low-fat yogurt at Sbisa breakfast is the same meal.\n"
                 "SOURCE: fats_whole_milk_yogurt")
    d = app.client.post("/api/chat", json={"message": "What do I usually eat for breakfast?", "session_id": "s"}).json()
    system = app.calls[0]["system"]
    assert "whole-milk yogurt (5 meals, mostly breakfast)" in system
    assert "swap_id=fats_whole_milk_yogurt" in system
    assert "Low Fat Vanilla Yogurt (Sbisa, breakfast" in system
    assert "Their setup: no kitchen, on a university meal plan" in system
    assert d["citations"] == [{"id": "fats_whole_milk_yogurt", "title": "Try lower-fat yogurt",
                               "source": server.twin_suggest.SWAPS_BY_ID["fats_whole_milk_yogurt"]["source"]}]


def test_coach_can_propose_the_swap_and_only_confirm_writes_it(app):
    yogurt_week(app)
    app.reply = ('Tap Confirm to add low-fat yogurt to your plan.\nSOURCE: none\n'
                 'ACTION_JSON: {"type": "try_swap", "payload": {"swap_id": "fats_whole_milk_yogurt"}}')
    d = app.client.post("/api/chat", json={"message": "ok let's swap my yogurt", "session_id": "s"}).json()
    assert d["answer"] == "Tap Confirm to add low-fat yogurt to your plan."
    assert d["pending_action"] == {"type": "try_swap", "payload": {"swap_id": "fats_whole_milk_yogurt"},
                                   "summary": 'Add "Try lower-fat yogurt" to your plan'}
    assert app.db.swap_plans.docs == []  # proposal only
    r = app.client.post("/api/chat/confirm-action", json=d["pending_action"])
    assert r.status_code == 200 and r.json()["result"]["status"] == "trying"
    assert app.db.swap_plans.docs[0]["swap_id"] == "fats_whole_milk_yogurt"


def test_a_valid_swap_this_student_may_not_have_is_refused_at_proposal_and_confirm(app):
    """A swap id that exists in the table but was never offered to THIS
    student (here: a nut-allergic student with a fats focus, and a swap from
    another focus area) can't become a card, can't be confirmed, and can't
    be saved from the Future Me buttons either."""
    yogurt_week(app)
    nut_free = {**USER, "allergy_terms": ["peanut", "nut"]}
    server.app.dependency_overrides[server.current_user] = lambda: dict(nut_free)
    app.reply = ('Tap Confirm to add nuts to your plan.\nSOURCE: none\n'
                 'ACTION_JSON: {"type": "try_swap", "payload": {"swap_id": "fats_butter_toast"}}')
    d = app.client.post("/api/chat", json={"message": "swap my yogurt", "session_id": "s"}).json()
    assert d["pending_action"] is None and d["answer"] == "Tap Confirm to add nuts to your plan."
    for sid in ("fats_butter_toast", "grains_default_oatmeal"):  # allergy-blocked; other focus area
        assert app.client.post("/api/chat/confirm-action",
                               json={"type": "try_swap", "payload": {"swap_id": sid}}).status_code == 404
        assert app.client.post("/api/future-me/swaps/trying", json={"swap_id": sid}).status_code == 404
    assert app.db.swap_plans.docs == []


def test_a_made_up_swap_id_is_dropped_silently(app):
    yogurt_week(app)
    app.reply = ('Sure.\nSOURCE: none\nACTION_JSON: {"type": "try_swap", "payload": {"swap_id": "fats_bacon_cake"}}')
    d = app.client.post("/api/chat", json={"message": "swap my yogurt", "session_id": "s"}).json()
    assert d["answer"] == "Sure." and d["pending_action"] is None
    assert app.client.post("/api/chat/confirm-action",
                           json={"type": "try_swap", "payload": {"swap_id": "fats_bacon_cake"}}).status_code == 422


def test_questions_about_regular_meals_reach_the_model_even_without_a_kb_hit(app):
    yogurt_week(app)
    question = "what do I usually eat?"
    # Personal questions reach the model with or without KB hits. Adding
    # the general-guideline KB entries (nutrition team, 2026-10-29) can
    # nudge BM25 to return something for a vague "eat" query, but the
    # chat endpoint takes the LLM path whenever hits is non-empty OR
    # ``_is_personal_question`` is true — the real contract.
    assert server._is_personal_question(question)
    app.reply = "Whole-milk yogurt, most mornings.\nSOURCE: none"
    d = app.client.post("/api/chat", json={"message": question, "session_id": "s"}).json()
    assert app.calls and d["answer"].startswith("Whole-milk yogurt")
    assert server._is_personal_question("can I swap my yogurt for something?")
    assert not server._is_personal_question("how do I read a nutrition label")  # a KB question, not a personal one
