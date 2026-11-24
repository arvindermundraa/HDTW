"""The two From-your-meals engines side by side: TWIN_ENGINE decides what
the participant sees, both decisions are recorded, the AI engine falls
back to rules, and staff can read and recompute the comparison. Fake DB,
stubbed model, menus replayed from the captured live fixture.
    python -m pytest tests/test_twin_engines.py -n 0"""
import json
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
import twin_llm  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from test_coach_and_future_me import FakeDB  # noqa: E402
from test_twin_suggest import MENUS  # noqa: E402

USER = {"id": "u1", "email": "t@example.com", "name": "T", "focus_area": "fats",
        "focus_areas": ["fatty_acids", "saturated_fats"], "allergy_terms": [], "tamus_api_key_encrypted": "x",
        "profile": {"kitchen_access": "none", "university_meal_plan": "yes"}}


@pytest.fixture
def app(monkeypatch):
    db = FakeDB()
    db.users.docs.append(dict(USER))
    db.hei_assessments.docs.append({"user_id": "u1", "assessment_type": "baseline",
                                    "components": {"fatty_acids": 2.0, "saturated_fats": 3.0},
                                    "recorded_at": "2026-09-22T12:00:00+00:00"})
    monkeypatch.setattr(server, "db", db)
    monkeypatch.setattr(server.limiter, "enabled", False)
    monkeypatch.setattr(tamus_client, "resolve_user_key", lambda u: "key")

    async def menus_today():
        return MENUS
    monkeypatch.setattr(server, "_twin_menus_today", menus_today)
    calls = []

    async def fake_llm(user, system, user_text, session_id, history=None):
        calls.append({"system": system, "text": user_text, "session": session_id})
        if session_id.startswith("twin-regulars"):
            rows = twin_llm.meal_rows(db.meals.docs, server.study_today())
            flip = [r["i"] for r in rows if "chobani" in r["text"]]
            return json.dumps({"regulars": [{"food": "Chobani Flip", "meals": flip, "slot": "breakfast"}]})
        if session_id.startswith("twin-pick"):
            return json.dumps({"picks": [{"swap_id": "fats_whole_milk_yogurt", "regular": "Chobani Flip",
                                          "menu_items": ["Low Fat Vanilla Yogurt"],
                                          "why": "Your Chobani is already a yogurt habit, so this is the same stop."}]})
        return app.reply
    monkeypatch.setattr(server, "run_llm", fake_llm)
    server.app.dependency_overrides[server.current_user] = lambda: dict(USER)
    server.app.dependency_overrides[server.require_research_key] = lambda: {"kind": "api_key", "role": "admin"}
    client = TestClient(server.app)
    app = type("App", (), {"client": client, "db": db, "calls": calls, "reply": ""})()
    yield app
    server.app.dependency_overrides.clear()


def log(app, name, days_ago, slot="breakfast"):
    stamp = (server.study_today() - timedelta(days=days_ago)).isoformat() + "T14:00:00+00:00"
    app.db.meals.docs.append({"id": f"m{len(app.db.meals.docs)}", "user_id": "u1", "name": name, "items": [],
                              "meal_type": slot, "categories": ["dairy"], "created_at": stamp, "skipped": False})


def chobani_week(app):
    for d in (1, 2, 4, 6, 8):
        log(app, "Chobani Flip key lime crumble", d)  # a yogurt the lexicon doesn't know


def llm_calls(app):
    return [c for c in app.calls if c["session"].startswith("twin-")]


# ---- the switch -----------------------------------------------------------------------
def test_rules_engine_is_the_default_and_the_ai_engine_is_not_called(app, monkeypatch):
    monkeypatch.setattr(server, "TWIN_ENGINE", "rules")
    chobani_week(app)
    fym = app.client.get("/api/future-me").json()["from_your_meals"]
    assert fym["engine"] == "rules" and fym["habits"] == []             # the lexicon doesn't know Chobani Flip
    assert fym["suggestions"][0]["kind"] == "focus_add" and llm_calls(app) == []
    row = app.db.twin_decisions.docs[0]
    assert row["shown"] == "rules" and "llm" not in row and row["rules"]["engine"] == "rules"


def test_ai_engine_names_the_regular_the_lexicon_missed_and_both_are_recorded(app, monkeypatch):
    monkeypatch.setattr(server, "TWIN_ENGINE", "llm")
    chobani_week(app)
    fym = app.client.get("/api/future-me").json()["from_your_meals"]
    assert fym["engine"] == "llm" and fym["engine_note"] is None
    assert fym["habits"][0]["label"] == "Chobani Flip" and fym["habits"][0]["times"] == 5
    s = fym["suggestions"][0]
    assert s["id"] == "fats_whole_milk_yogurt" and s["kind"] == "habit_swap" and s["habit"]["label"] == "Chobani Flip"
    assert s["why"].startswith("Your Chobani") and s["on_menu_today"][0]["item_name"] == "Low Fat Vanilla Yogurt"
    assert s["text"] == server.twin_suggest.SWAPS_BY_ID["fats_whole_milk_yogurt"]["text"]  # table text, not the model's
    assert server._guardrail_violation_type(json.dumps(fym)) is None
    row = app.db.twin_decisions.docs[0]
    assert row["shown"] == "llm" and row["rules"]["habits"] == [] and row["llm"]["habits"][0]["label"] == "Chobani Flip"
    assert [c["session"][:12] for c in llm_calls(app)] == ["twin-regular", "twin-pick-u1"]
    # The pick prompt only offered swaps this student may have, and real items.
    pick = llm_calls(app)[1]["text"]
    assert "swap_id=fats_whole_milk_yogurt" in pick and "swap_id=grains_default_oatmeal" not in pick
    assert "Low Fat Vanilla Yogurt" in pick


def test_ai_result_is_reused_until_the_logs_change(app, monkeypatch):
    monkeypatch.setattr(server, "TWIN_ENGINE", "llm")
    chobani_week(app)
    app.client.get("/api/future-me")
    app.client.get("/api/future-me/from-your-meals")
    app.client.post("/api/chat", json={"message": "what do I usually eat?", "session_id": "s"})  # coach reads it too
    assert len(llm_calls(app)) == 2  # one regulars call + one pick call, then cached
    assert "Chobani Flip (5 meals, mostly breakfast)" in app.calls[-1]["system"]
    assert "Why it fits them: Your Chobani" in app.calls[-1]["system"]
    log(app, "Chobani Flip", 0)
    app.client.get("/api/future-me")
    assert len(llm_calls(app)) == 4  # a new log → recomputed
    assert len(app.db.twin_decisions.docs) == 1  # one row per student per day


def test_ai_engine_falls_back_to_rules_without_a_key_or_on_failure_and_retries_later(app, monkeypatch):
    monkeypatch.setattr(server, "TWIN_ENGINE", "llm")
    chobani_week(app)

    def no_key(u):
        raise tamus_client.TamusKeyRequiredError("no key")
    monkeypatch.setattr(tamus_client, "resolve_user_key", no_key)
    fym = app.client.get("/api/future-me/from-your-meals").json()
    assert fym["engine"] == "rules" and fym["engine_note"] == "AI engine unavailable right now; rules shown"
    assert app.db.twin_decisions.docs[0]["llm"]["available"] is False and "no_key" not in fym["engine_note"]
    assert app.db.twin_decisions.docs[0]["llm_computed"]["reason"] == "no_key"  # staff see why; the student doesn't
    # The student adds a key: the next read runs the AI engine (a key-less run is never held for the day).
    monkeypatch.setattr(tamus_client, "resolve_user_key", lambda u: "key")
    assert app.client.get("/api/future-me/from-your-meals").json()["engine"] == "llm"

    real_llm = server.run_llm

    async def boom(user, system, user_text, session_id, history=None):
        raise RuntimeError("TAMU down")
    monkeypatch.setattr(server, "run_llm", boom)
    app.db.twin_decisions.docs.clear()
    fym = app.client.get("/api/future-me/from-your-meals").json()
    assert fym["engine"] == "rules" and fym["suggestions"]  # the rules default stands in
    # A failed call is not retried on every request (five-minute rest)…
    monkeypatch.setattr(server, "run_llm", real_llm)
    assert app.client.get("/api/future-me/from-your-meals").json()["engine"] == "rules"
    # …but it is once the rest is over.
    app.db.twin_decisions.docs[0]["llm_computed_at"] = "2000-01-01T00:00:00+00:00"
    assert app.client.get("/api/future-me/from-your-meals").json()["engine"] == "llm"


def test_taps_on_the_ai_card_take_effect_despite_the_cache(app, monkeypatch):
    monkeypatch.setattr(server, "TWIN_ENGINE", "llm")
    chobani_week(app)
    first = app.client.get("/api/future-me/from-your-meals").json()  # the model runs and is cached here
    assert first["engine"] == "llm" and first["suggestions"][0]["id"] == "fats_whole_milk_yogurt"
    r = app.client.post("/api/future-me/swaps/dismissed", json={"swap_id": "fats_whole_milk_yogurt"})
    after = r.json()["from_your_meals"]
    assert after["engine"] == "llm" and all(s["id"] != "fats_whole_milk_yogurt" for s in after["suggestions"])
    assert after["suggestions"], "the rules default stands in when the model's only pick is rested"
    r = app.client.post("/api/future-me/swaps/trying", json={"swap_id": "fats_fries"})  # never picked by the model
    pinned = r.json()["from_your_meals"]["suggestions"][0]
    assert pinned["id"] == "fats_fries" and pinned["status"] == "trying"
    assert len(llm_calls(app)) == 2  # no re-run for any of this
    assert app.client.post("/api/future-me/swaps/trying", json={"swap_id": "grains_default_oatmeal"}).status_code == 404


def test_an_allergy_declared_after_the_model_ran_is_applied_on_the_next_read(app, monkeypatch):
    monkeypatch.setattr(server, "TWIN_ENGINE", "llm")
    chobani_week(app)
    assert app.client.get("/api/future-me/from-your-meals").json()["suggestions"][0]["id"] == "fats_whole_milk_yogurt"
    server.app.dependency_overrides[server.current_user] = lambda: {**USER, "allergy_terms": ["milk", "lactose", "dairy"]}
    fym = app.client.get("/api/future-me/from-your-meals").json()
    assert fym["engine"] == "llm" and all(s["id"] != "fats_whole_milk_yogurt" for s in fym["suggestions"])
    for s in fym["suggestions"]:
        for m in s["on_menu_today"]:
            assert "yogurt" not in m["item_name"].lower()
    assert len(llm_calls(app)) == 2  # re-filtered from the cache, not recomputed


def test_menus_arriving_after_the_model_ran_are_picked_up(app, monkeypatch):
    monkeypatch.setattr(server, "TWIN_ENGINE", "llm")
    chobani_week(app)

    async def no_menus():
        return {h: {} for h in server.DINING_HALLS}
    monkeypatch.setattr(server, "_twin_menus_today", no_menus)
    cold = app.client.get("/api/future-me/from-your-meals").json()
    assert cold["engine"] == "llm" and cold["suggestions"][0]["on_menu_today"] == [] and cold["menu_source"] == "none"

    async def menus_today():
        return MENUS
    monkeypatch.setattr(server, "_twin_menus_today", menus_today)
    warm = app.client.get("/api/future-me/from-your-meals").json()
    assert warm["menu_source"] == "live" and warm["suggestions"][0]["on_menu_today"][0]["item_name"] == "Low Fat Vanilla Yogurt"


# ---- staff comparison ---------------------------------------------------------------------
def test_staff_can_read_both_engines_and_the_agreement_summary(app, monkeypatch):
    monkeypatch.setattr(server, "TWIN_ENGINE", "llm")
    chobani_week(app)
    app.client.get("/api/future-me")
    d = app.client.get("/api/research/twin-decisions?user_id=u1").json()
    assert d["engine_setting"] == "llm" and len(d["decisions"]) == 1
    row = d["decisions"][0]
    assert row["email"] == "t@example.com" and row["shown"] == "llm"
    assert row["rules"]["habits"] == [] and row["llm"]["habits"][0]["label"] == "Chobani Flip"
    assert row["rules"]["suggestions"][0]["id"] == "fats_default_nuts_oils"
    assert row["llm"]["suggestions"][0]["id"] == "fats_whole_milk_yogurt" and row["agree_top_swap"] is False
    # Agreement is undefined, not "yes", when neither engine has a suggestion.
    assert server._twin_decision_view({"rules": {"habits": [], "suggestions": []},
                                       "llm": {"available": True, "habits": [], "suggestions": []}})["agree_top_swap"] is None
    assert "Low Fat Vanilla Yogurt (Sbisa, breakfast)" in row["llm"]["suggestions"][0]["on_menu_today"]
    s = app.client.get("/api/research/twin-decisions/summary").json()
    assert s["decisions"] == 1 and s["with_both_engines"] == 1 and s["top_swap_agreement"] == 0.0
    assert s["mean_habits_rules"] == 0 and s["mean_habits_llm"] == 1


def test_staff_recompute_runs_both_engines_even_when_rules_are_shown(app, monkeypatch):
    monkeypatch.setattr(server, "TWIN_ENGINE", "rules")
    chobani_week(app)
    assert app.client.get("/api/future-me").json()["from_your_meals"]["engine"] == "rules"
    assert "llm" not in app.db.twin_decisions.docs[0]
    r = app.client.post("/api/research/twin-decisions/recompute", json={"user_id": "u1"})
    assert r.status_code == 200 and r.json()["llm"]["habits"][0]["label"] == "Chobani Flip"
    assert r.json()["shown"] == "rules"  # the participant still sees the rules engine
    log(app, "Chobani Flip", 0)
    app.client.get("/api/future-me")  # the student's next read doesn't erase the staff comparison data
    assert app.db.twin_decisions.docs[0]["llm"]["habits"][0]["label"] == "Chobani Flip"
    assert app.client.post("/api/research/twin-decisions/recompute", json={"user_id": "nobody"}).status_code == 404


def test_research_endpoints_need_staff_auth(app):
    server.app.dependency_overrides.pop(server.require_research_key, None)
    assert app.client.get("/api/research/twin-decisions").status_code == 401
    assert app.client.get("/api/research/twin-decisions/summary").status_code == 401
    assert app.client.post("/api/research/twin-decisions/recompute", json={"user_id": "u1"}).status_code == 401
