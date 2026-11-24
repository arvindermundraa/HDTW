"""The behavioral twin's endpoints (/api/twin/*, the Coach's try_step, the
wearable day sync, and the researcher evaluation), run against the
in-memory fake database with the LLM stubbed and today's menus replayed
from the captured live fixture.
    python -m pytest tests/test_twin_api.py -n 0"""
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
from fastapi.testclient import TestClient  # noqa: E402
from test_coach_and_future_me import FakeDB  # noqa: E402
from test_twin_suggest import MENUS  # noqa: E402

USER = {"id": "u1", "email": "t@tamu.edu", "name": "T", "focus_area": "fats", "allergy_terms": [],
        "tamus_api_key_encrypted": "x", "wearable_connected": True,
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
        if session_id.startswith("twin-interpret"):
            return app.interpret
        return app.reply
    monkeypatch.setattr(server, "run_llm", fake_llm)
    who = {"user": dict(USER)}
    server.app.dependency_overrides[server.current_user] = lambda: dict(who["user"])
    server.app.dependency_overrides[server.require_research_key] = lambda: {"kind": "api_key", "role": "admin"}
    client = TestClient(server.app)
    app = type("App", (), {"client": client, "db": db, "calls": calls, "reply": "", "who": who,
                           "interpret": '{"codes": []}'})()
    yield app
    server.app.dependency_overrides.clear()


def day(n):
    return server.study_today() - timedelta(days=n)


def tracker_weeks(app, weekday_minutes=10, weekend_minutes=60, weekday_sleep=None):
    for n in range(21):
        d = day(n)
        wk = d.weekday() < 5
        app.db.activities.docs.append({"id": f"a{n}", "user_id": "u1", "created_at": server.now_utc().isoformat(),
                                       "minutes": weekday_minutes if wk else weekend_minutes, "source": "wearable",
                                       "recorded_date": d.isoformat()})
        if weekday_sleep:
            app.db.sleeps.docs.append({"id": f"s{n}", "user_id": "u1", "created_at": server.now_utc().isoformat(),
                                       "hours": weekday_sleep if wk else 8.5, "source": "wearable",
                                       "recorded_date": d.isoformat(), "bedtime": "01:00" if wk else "23:00",
                                       "wake": "07:00"})


def yogurt_week(app):
    for n in (1, 2, 4, 6, 8):
        app.db.meals.docs.append({"id": f"m{n}", "user_id": "u1", "name": "whole milk yogurt and granola", "items": [],
                                  "meal_type": "breakfast", "categories": ["dairy"], "skipped": False,
                                  "created_at": day(n).isoformat() + "T14:00:00+00:00"})


def twin(app):
    r = app.client.get("/api/twin")
    assert r.status_code == 200, r.text
    return r.json()


def answer(app, key, ans="yes", circumstances=(), note=None):
    r = app.client.post("/api/twin/questions/answer",
                        json={"key": key, "answer": ans, "circumstances": list(circumstances), "note": note})
    assert r.status_code == 200, r.text
    return r.json()["twin"]


def respond(app, rec_id, response, status=200, **kw):
    r = app.client.post("/api/twin/steps/respond", json={"rec_id": rec_id, "response": response, **kw})
    assert r.status_code == status, r.text
    return r.json()


def rec_ids(v):
    return [r["id"] for r in v["recommendations"]]


# ---- cold start and asking first ------------------------------------------------------------------------------
def test_cold_start_offers_food_steps_for_the_focus_area_and_asks_before_anything_else(app):
    v = twin(app)
    assert v["questions"] == [] and v["offer_domains"] == ["activity", "sleep"]
    assert v["recommendations"] and all(r["domains"] == ["diet"] for r in v["recommendations"])
    assert v["notes"]["activity"].startswith("Connect a tracker") and v["notes"]["sleep"].startswith("Connect a tracker")
    assert {"key": "context.dining_hall", "label": "You often eat at the dining hall", "source": "From your profile"} in v["learned"]
    assert any(r["id"] == "cost" for r in v["reasons"])


def test_the_yogurt_regular_is_asked_about_before_the_swap_is_offered(app):
    yogurt_week(app)
    v = twin(app)
    q = next(q for q in v["questions"] if q["key"] == "diet.regular.whole_milk_yogurt")
    assert q["question"] == "Is whole-milk yogurt a regular breakfast for you?"
    assert q["evidence"].startswith("You've logged whole-milk yogurt in 5 meals")
    assert "fats_whole_milk_yogurt" not in rec_ids(v)  # not a habit until they say so

    v = answer(app, "diet.regular.whole_milk_yogurt", "yes", ["like_it"])
    swap = next(r for r in v["recommendations"] if r["id"] == "fats_whole_milk_yogurt")
    assert swap["why"].startswith("Because you said whole-milk yogurt is a regular breakfast for you.")
    assert swap["on_menu_today"][0]["item_name"] == "Low Fat Vanilla Yogurt"
    assert swap["grocery"] == ["Low-fat or nonfat yogurt"]
    assert any(l["label"].endswith("and you like it") for l in v["learned"])
    assert not any(l["key"] == "circ.like_it" for l in v["learned"])  # about the food, not a fact about them


def test_not_really_keeps_the_swap_away_and_the_question_rests(app):
    yogurt_week(app)
    v = answer(app, "diet.regular.whole_milk_yogurt", "no")
    assert "fats_whole_milk_yogurt" not in rec_ids(v)
    assert all(q["key"] != "diet.regular.whole_milk_yogurt" for q in v["questions"])
    assert app.db.twin_events.docs[-1]["answer"] == "no"


def test_a_weekday_movement_pattern_is_asked_and_its_steps_follow_the_answer(app):
    tracker_weeks(app)
    v = twin(app)
    assert any(q["key"] == "activity.low_weekdays" for q in v["questions"])
    assert not any("activity" in r["domains"] for r in v["recommendations"])
    v = answer(app, "activity.low_weekdays", "yes", ["back_to_back_classes"])
    walk = next(r for r in v["recommendations"] if "activity" in r["domains"])
    assert walk["id"] == "act_walk_between_classes"
    assert walk["why"] == ("Because you said weekdays are harder to fit movement into. "
                           "It works around classes back to back.")
    assert "Your classes run back to back" in [l["label"] for l in v["learned"]]


def test_unknown_or_closed_questions_and_bad_circumstances_are_refused(app):
    assert app.client.post("/api/twin/questions/answer", json={"key": "sleep.irregular_timing", "answer": "yes"}).status_code == 404
    tracker_weeks(app)
    r = app.client.post("/api/twin/questions/answer",
                        json={"key": "activity.low_weekdays", "answer": "yes", "circumstances": ["roommates_noise"]})
    assert r.status_code == 422


def test_weekday_signals_in_two_domains_lead_to_one_integrated_step(app):
    tracker_weeks(app, weekday_sleep=6)
    v = twin(app)
    assert v["questions"][0]["key"] == "cross.weekday_squeeze"
    assert v["questions"][0]["evidence"] == "Weekdays look tighter than weekends: shorter sleep and less movement."
    v = answer(app, "cross.weekday_squeeze", "yes", ["early_classes"])
    multi = [r for r in v["recommendations"] if len(r["domains"]) > 1]
    assert len(multi) == 1 and v["recommendations"][0] is not None
    assert multi[0]["why"].startswith("Because you said your schedule squeezes your weekdays.")


def test_a_free_text_circumstance_is_understood(app):
    tracker_weeks(app)
    answer(app, "activity.low_weekdays", "yes", [], note="my job shifts are brutal")
    assert any(f["key"] == "circ.work_shifts" for f in app.db.twin_facts.docs)
    assert app.db.twin_events.docs[-1]["interpreted_by"] == "rules"


# ---- steps and what the twin learns from them ---------------------------------------------------------------------
def test_not_for_me_because_of_cost_is_remembered_and_respected(app):
    app.client.post("/api/twin/domains", json={"domain": "activity"})
    v = twin(app)
    rid = next(r["id"] for r in v["recommendations"] if "activity" in r["domains"])
    d = respond(app, rid, "decline", note="honestly too pricey")
    assert d["status"] == "dismissed" and d["learned"] == ["cost"]
    assert rid not in rec_ids(d["twin"])
    assert {"key": "constraint.cost", "label": "Cost matters to you", "source": "From your feedback"} in d["twin"]["learned"]
    ev = app.db.twin_events.docs[-1]
    assert ev["reasons"] == ["cost"] and ev["interpreted_by"] == "rules" and ev["note"] == "honestly too pricey"
    st = _sync_state(app)
    assert "cost" in st["constraints"]
    assert server.twin_recommend.eligible(server.twin_recommend.ITEMS_BY_ID["act_rec_center_class"], st,
                                          lambda i: False) == (False, "cost")


def _sync_state(app):
    import asyncio
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(server._twin_compute(dict(app.who["user"]), record=False))["state"]
    finally:
        loop.close()


def test_a_note_with_no_keywords_goes_to_the_model_and_only_listed_codes_are_kept(app):
    app.client.post("/api/twin/domains", json={"domain": "sleep"})
    rid = next(r["id"] for r in twin(app)["recommendations"] if "sleep" in r["domains"])
    app.interpret = '{"codes": ["energy", "delete_everything"]}'
    d = respond(app, rid, "decline", note="meh, vibes were off")
    assert d["learned"] == ["energy"]
    assert app.db.twin_events.docs[-1]["interpreted_by"] == "llm"
    assert any(c["session"].startswith("twin-interpret") for c in app.calls)


def test_try_then_didnt_fit_rests_it_and_offers_a_different_approach(app):
    tracker_weeks(app)
    answer(app, "activity.low_weekdays", "yes", ["back_to_back_classes"])
    d = respond(app, "act_walk_between_classes", "accept", when="between_classes")
    tr = next(r for r in d["twin"]["recommendations"] if r["id"] == "act_walk_between_classes")
    assert tr["status"] == "trying" and tr["plan"]["when"] == "between_classes"
    d = respond(app, "act_walk_between_classes", "didnt_fit", reasons=["schedule"])
    assert d["status"] == "didnt_fit" and d["learned"] == ["schedule"]
    v = d["twin"]
    assert "act_walk_between_classes" not in rec_ids(v)
    alt = next(r for r in v["recommendations"] if "activity" in r["domains"])
    assert "different approach from “The long way between two classes”" in alt["why"]
    assert all(not server.twin_recommend.ITEMS_BY_ID.get(r["id"], {}).get("new_time_block") for r in v["recommendations"])


def test_a_step_that_worked_is_reinforced_and_checked_in_on(app):
    tracker_weeks(app)
    answer(app, "activity.low_weekdays", "yes")
    respond(app, "act_walk_between_classes", "accept")
    d = respond(app, "act_walk_between_classes", "worked")
    v = d["twin"]
    assert d["status"] == "adopted" and "act_walk_between_classes" not in rec_ids(v)
    keep = next(r for r in v["reinforcing"] if r["id"] == "act_walk_between_classes")
    assert keep["message"].startswith("You said this worked.")
    assert respond(app, "act_walk_between_classes", "still_doing")["status"] == "adopted"
    assert respond(app, "act_walk_between_classes", "lapsed")["status"] == "lapsed"


def test_i_already_do_this_is_reinforced_instead_of_rested(app):
    d = twin(app)
    rid = d["recommendations"][0]["id"]
    out = respond(app, rid, "decline", reasons=["already_do"])
    assert out["status"] == "adopted" and any(r["id"] == rid for r in out["twin"]["reinforcing"])


def test_only_a_step_offered_to_this_student_can_be_accepted(app):
    respond(app, "grains_default_oatmeal", "accept", status=404)  # another focus area's swap
    respond(app, "act_rec_center_class", "accept", status=404)    # activity not in play for them
    respond(app, "not_a_step", "accept", status=422)
    respond(app, "diet_fats_cooking_oil", "worked", status=404)  # never tried, never shown (needs a stove)
    assert app.db.twin_plans.docs == []


def test_accepting_a_food_swap_keeps_the_older_card_and_the_coach_in_step(app):
    yogurt_week(app)
    answer(app, "diet.regular.whole_milk_yogurt", "yes")
    respond(app, "fats_whole_milk_yogurt", "accept")
    assert app.db.swap_plans.docs[0]["status"] == "trying"
    fym = app.client.get("/api/future-me/from-your-meals").json()
    assert fym["suggestions"][0]["id"] == "fats_whole_milk_yogurt" and fym["suggestions"][0]["status"] == "trying"
    respond(app, "fats_whole_milk_yogurt", "worked")
    assert app.db.swap_plans.docs[0]["status"] == "tried"


def test_what_i_learned_can_be_corrected(app):
    v = twin(app)
    assert any(l["key"] == "context.dining_hall" for l in v["learned"])
    r = app.client.post("/api/twin/learned/remove", json={"key": "context.dining_hall"})
    assert r.status_code == 200
    assert not any(l["key"] == "context.dining_hall" for l in r.json()["twin"]["learned"])
    assert app.client.post("/api/twin/learned/remove", json={"key": "context.dining_hall"}).status_code == 404


def test_a_recent_safety_check_in_pauses_food_and_exercise_steps(app):
    yogurt_week(app)
    tracker_weeks(app)
    app.db.safety_checkins.docs.append({"id": "c1", "user_id": "u1", "created_at": server.now_utc().isoformat()})
    v = twin(app)
    assert v["paused"] and v["notes"]["paused"]
    assert all(not r["domains"] or set(r["domains"]) <= {"sleep"} for r in v["recommendations"])
    assert all(not q["key"].startswith("diet.") for q in v["questions"])


# ---- grocery list ------------------------------------------------------------------------------------------------
def test_grocery_list_from_a_step_and_by_hand(app):
    r = app.client.post("/api/twin/grocery", json={"rec_id": "fats_whole_milk_yogurt"})
    assert r.status_code == 200 and r.json()["added"] == ["Low-fat or nonfat yogurt"]
    assert app.client.post("/api/twin/grocery", json={"rec_id": "fats_whole_milk_yogurt"}).json()["added"] == []
    r = app.client.post("/api/twin/grocery", json={"text": "  bananas  "})
    items = r.json()["items"]
    assert [i["text"] for i in items] == ["Low-fat or nonfat yogurt", "bananas"]
    iid = items[0]["id"]
    assert app.client.patch(f"/api/twin/grocery/{iid}", json={"done": True}).json()["items"][0]["done"] is True
    assert len(app.client.delete(f"/api/twin/grocery/{iid}").json()["items"]) == 1
    assert app.client.delete(f"/api/twin/grocery/{iid}").status_code == 404
    assert app.client.post("/api/twin/grocery", json={"rec_id": "act_walk_after_lunch"}).status_code == 404
    assert app.client.post("/api/twin/grocery", json={}).status_code == 422


# ---- Future Me and the Coach --------------------------------------------------------------------------------------
def test_future_me_home_carries_the_twin(app):
    d = app.client.get("/api/future-me").json()
    assert "twin" in d and "from_your_meals" in d and d["twin"]["recommendations"]


def test_the_coach_sees_confirmed_vs_noticed_and_can_propose_a_step(app):
    tracker_weeks(app, weekday_sleep=6)
    answer(app, "activity.low_weekdays", "yes", ["back_to_back_classes"])
    app.reply = ("A walk between classes fits your day. Tap Confirm to add it to your plan.\nSOURCE: none\n"
                 'ACTION_JSON: {"type": "try_step", "payload": {"rec_id": "act_walk_between_classes"}}')
    d = app.client.post("/api/chat", json={"message": "how can I fit in movement on my weekdays?", "session_id": "s"}).json()
    system = next(c["system"] for c in app.calls if c["session"].startswith("coach-"))
    assert "Confirmed with them: Weekdays are harder to fit movement into" in system
    assert "NOT confirmed" in system and "Does your bedtime change a lot" in system
    assert "step_id=act_walk_between_classes" in system
    assert d["pending_action"]["type"] == "try_step"
    assert d["pending_action"]["summary"] == 'Add "The long way between two classes" to your plan'
    assert app.db.twin_plans.docs == []  # proposal only
    r = app.client.post("/api/chat/confirm-action", json=d["pending_action"])
    assert r.status_code == 200 and r.json()["result"]["status"] == "trying"


def test_the_coach_cannot_propose_a_step_this_student_isnt_offered(app):
    app.reply = ('Sure.\nSOURCE: none\nACTION_JSON: {"type": "try_step", "payload": {"rec_id": "act_rec_center_class"}}')
    d = app.client.post("/api/chat", json={"message": "what step should I try for my sleep?", "session_id": "s"}).json()
    assert d["pending_action"] is None
    assert app.client.post("/api/chat/confirm-action",
                           json={"type": "try_step", "payload": {"rec_id": "act_rec_center_class"}}).status_code == 404


# ---- wearable days -----------------------------------------------------------------------------------------------
def test_device_days_are_upserted_with_sleep_timing_and_steps(app):
    days = [{"recorded_date": day(n).isoformat(), "hours": 7, "sleep_start": "23:30", "sleep_end": "06:30",
             "activity_minutes": 20, "steps": 6000} for n in range(3)]
    assert app.client.post("/api/wearable/sync-days", json={"days": days}).status_code == 200
    again = [{**days[0], "hours": 7.5, "activity_minutes": 25}]
    assert app.client.post("/api/wearable/sync-days", json={"days": again}).status_code == 200
    assert len(app.db.sleeps.docs) == 3 and len(app.db.activities.docs) == 3
    first = next(s for s in app.db.sleeps.docs if s["recorded_date"] == days[0]["recorded_date"])
    assert first["hours"] == 7.5 and first["bedtime"] == "23:30" and first["wake"] == "06:30"
    assert app.client.post("/api/wearable/sync-sleep", json={"steps": 100}).status_code == 400
    assert app.client.post("/api/wearable/sync-days", json={"days": [{"hours": 7}]}).status_code == 422
    assert app.client.post("/api/wearable/sync-sleep", json={"hours": 7, "sleep_start": "25:00"}).status_code == 422


def test_manual_sleep_can_carry_bed_and_wake_times(app):
    r = app.client.post("/api/sleep", json={"hours": 7, "bedtime": "00:30", "wake": "07:30"})
    assert r.status_code == 200 and r.json()["bedtime"] == "00:30" and r.json()["source"] == "manual"
    assert app.client.post("/api/sleep", json={"hours": 7, "bedtime": "7pm"}).status_code == 422


# ---- researcher page -----------------------------------------------------------------------------------------------
def test_researchers_see_the_profile_rate_steps_and_get_the_evaluation(app):
    tracker_weeks(app)
    answer(app, "activity.low_weekdays", "yes", ["back_to_back_classes"])
    respond(app, "act_walk_between_classes", "accept")
    respond(app, "act_walk_between_classes", "didnt_fit", reasons=["schedule"])
    # tomorrow's snapshot, so feedback incorporation has something later to look at
    snap = next(s for s in app.db.twin_snapshots.docs if s["user_id"] == "u1")
    later = {**json.loads(json.dumps(snap)), "id": "later", "day": (server.study_today() + timedelta(days=1)).isoformat()}
    app.db.twin_snapshots.docs.append(later)

    prof = app.client.get("/api/research/twin-profile", params={"user_id": "u1"}).json()
    assert {f["key"] for f in prof["facts"]} >= {"activity.low_weekdays", "circ.back_to_back_classes", "constraint.schedule"}
    assert prof["events"][0]["response"] == "didnt_fit" and prof["decisions"]
    today = server.study_today().isoformat()
    shown = prof["now"]["recommendations"][0]["id"]
    r = app.client.post("/api/research/twin-snapshots/rate",
                        json={"user_id": "u1", "day": today, "rec_id": shown, "rating": "appropriate"})
    assert r.status_code == 200
    assert app.client.post("/api/research/twin-snapshots/rate", json={"user_id": "u1", "day": today, "rec_id": "nope",
                                                                      "rating": "appropriate"}).status_code == 404

    ev = app.client.get("/api/research/twin-eval", params={"include_test": "true"}).json()
    assert ev["pattern_accuracy"]["activity.low_weekdays"] == {"answered": 1, "yes": 1, "sometimes": 0, "no": 0,
                                                               "confirmed_rate": 1.0}
    assert ev["steps_by_domain"]["activity"]["accept"] == 1 and ev["steps_by_domain"]["activity"]["didnt_fit"] == 1
    assert ev["appropriateness"] == {"rated": 1, "appropriate": 1, "rate": 1.0}
    assert ev["constraint_adherence"]["new_steps_with_violation"] == 0
    fi = ev["feedback_incorporation"]
    assert fi["reasons_checked"] == 1 and fi["respected_later"] == 1
    assert fi["declines_with_pattern"] == 1 and fi["alternative_offered"] == 1
