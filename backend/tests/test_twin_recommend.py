"""The behavioral twin's library and step selection (content/twin_library.json,
twin_recommend.py, twin_profile.build_state). Pure functions, no server
calls except the guardrail check over every participant-facing text.
    python -m pytest tests/test_twin_recommend.py -n 0"""
import os
import re
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "llhs_unit_unused")
import server  # noqa: E402
import twin_profile  # noqa: E402
import twin_recommend as tr  # noqa: E402
import twin_suggest  # noqa: E402

TODAY = date(2026, 11, 11)
NO_ALLERGY = lambda item: False  # noqa: E731


def state(**over):
    base = dict(facts=[], profile={"kitchen_access": "none", "university_meal_plan": "yes"}, meals=[],
                focus_area="fats", setup=twin_suggest.setup_from_profile({"kitchen_access": "none"}), plans={},
                feedback=[], detected_keys=set(), paused=False, today=TODAY, pattern_labels={})
    base.update(over)
    return twin_profile.build_state(**base)


def confirmed(*keys, answer="confirmed"):
    return [{"key": k, "kind": "pattern", "status": answer, "answered_day": TODAY.isoformat()} for k in keys]


def circ(*ids):
    return [{"key": f"circ.{c}", "kind": "circumstance", "status": "stated"} for c in ids]


def ids(sel):
    return [r["id"] for r in sel["recommendations"]]


# ---- the library itself -------------------------------------------------------------------------
def test_every_item_is_reviewable_and_safe_to_show():
    assert len(tr.ITEMS) >= 40
    for it in tr.ITEMS:
        texts = [it["title"], it["text"], *it["grocery"], *(c["if"] + " " + c["then"] for c in it["coping"])]
        for t in texts:
            assert not re.search(r"\d", t), (it["id"], t)
            assert server._guardrail_violation_type(t, strict=True) is None, (it["id"], t)
            for word in ("cut back", "skip", "lighter", "burn", "earn", "work off", "less ", "avoid"):
                assert word not in t.lower(), (it["id"], word, t)
        assert it["reviewed"] is False and it["source"].strip()
        assert all(b in tr.BCT for b in it["bct"])


def test_the_library_covers_every_domain_type_and_focus_area():
    domains = {d for it in tr.ITEMS for d in it["domains"]}
    types = {it["type"] for it in tr.ITEMS}
    assert domains == {"diet", "activity", "sleep"}
    assert {"add", "modify", "grocery", "routine", "plan"} <= types
    for area in ("fruit", "vegetables_beans", "grains", "dairy", "protein_foods", "fats", "sodium", "added_sugars"):
        assert any(area in (it["targets"]["focus_areas"] or []) for it in tr.ITEMS), area
    assert sum(1 for it in tr.ITEMS if len(it["domains"]) > 1) >= 4  # steps that work across domains
    assert {"action_planning", "coping_planning", "prompts_cues", "goal_setting"} & {b for it in tr.ITEMS for b in it["bct"]}
    for ctx in ("dining_hall", "grocery", "at_home", "takeout"):
        assert any(ctx in it["contexts"] for it in tr.ITEMS if "diet" in it["domains"]), ctx


def test_grocery_items_for_swaps_point_at_real_swaps():
    assert set(tr.GROCERY_FOR_SWAPS) <= set(twin_suggest.SWAPS_BY_ID)
    assert tr.GROCERY_FOR_SWAPS["fats_whole_milk_yogurt"] == ["Low-fat or nonfat yogurt"]


# ---- asking before assuming ----------------------------------------------------------------------------
def test_activity_and_sleep_steps_wait_for_a_confirmed_pattern_or_an_ask():
    sel = tr.select(tr.ITEMS, state(), NO_ALLERGY)
    assert all(r["domains"] == ["diet"] for r in sel["recommendations"])
    walk = tr.ITEMS_BY_ID["act_walk_between_classes"]
    assert tr.eligible(walk, state(), NO_ALLERGY) == (False, "domain_not_on")
    asked = state(facts=[{"key": "goal.activity", "kind": "goal", "status": "stated"}])
    assert tr.eligible(walk, asked, NO_ALLERGY)[0]
    pattern_only = tr.ITEMS_BY_ID["act_weekend_into_weekday"]  # not general: needs the pattern itself
    assert tr.eligible(pattern_only, asked, NO_ALLERGY) == (False, "pattern_not_confirmed")
    yes = state(facts=confirmed("activity.low_weekdays"), detected_keys={"activity.low_weekdays"})
    assert tr.eligible(pattern_only, yes, NO_ALLERGY)[0]


def test_a_pattern_said_no_to_steers_nothing():
    st = state(facts=[{"key": "sleep.irregular_timing", "kind": "pattern", "status": "rejected",
                       "answered_day": TODAY.isoformat()}], detected_keys={"sleep.irregular_timing"})
    assert st["confirmed"] == {} and not st["domains_on"]["sleep"]


def test_a_confirmed_pattern_long_gone_from_the_data_stops_steering():
    old = [{"key": "sleep.irregular_timing", "kind": "pattern", "status": "confirmed", "answered_day": "2026-08-01"}]
    assert state(facts=old)["confirmed"] == {}
    assert state(facts=old, detected_keys={"sleep.irregular_timing"})["confirmed"] == {"sleep.irregular_timing": "yes"}


# ---- one integrated step instead of three ----------------------------------------------------------------
def test_a_confirmed_cross_domain_pattern_leads_with_one_cross_domain_step():
    st = state(facts=confirmed("cross.weekday_squeeze") + circ("early_classes"), detected_keys={"cross.weekday_squeeze"})
    sel = tr.select(tr.ITEMS, st, NO_ALLERGY)
    recs = sel["recommendations"]
    assert len(recs[0]["domains"]) > 1
    assert sum(1 for r in recs if len(r["domains"]) > 1) == 1  # never two cross-domain steps at once
    assert recs[0]["why"].startswith("Because you said your schedule squeezes your weekdays.")
    assert "early classes" in recs[0]["why"]


# ---- the participant's setup and context ---------------------------------------------------------------
def test_contexts_decide_where_food_steps_happen():
    home_cook = {"kitchen_access": "personal", "appliance_stove": "personal", "appliance_microwave": "personal",
                 "food_acquisition": ["grocery_store"], "meal_preparation": ["self"], "freq_cook_meals": "daily"}
    st = state(profile=home_cook, setup=twin_suggest.setup_from_profile(home_cook), focus_area="sodium")
    assert st["contexts"][:2] == ["at_home", "grocery"] and "dining_hall" not in st["contexts"]
    assert tr.eligible(tr.ITEMS_BY_ID["diet_sodium_low_sodium_grocery"], st, NO_ALLERGY)[0]
    assert tr.eligible(tr.ITEMS_BY_ID["diet_sodium_sauce_on_side"], st, NO_ALLERGY) == (False, "context")
    dining = state(focus_area="sodium")  # meal plan, no kitchen
    assert tr.eligible(tr.ITEMS_BY_ID["diet_sodium_sauce_on_side"], dining, NO_ALLERGY)[0]
    assert tr.eligible(tr.ITEMS_BY_ID["diet_sodium_flavor_swap"], dining, NO_ALLERGY) == (False, "context")


def test_no_survey_rules_nothing_out_by_context():
    st = state(profile={}, setup=twin_suggest.setup_from_profile({}))
    assert st["contexts"] == []
    assert tr.eligible(tr.ITEMS_BY_ID["diet_fats_cooking_oil"], st, NO_ALLERGY)[0]


def test_kitchen_allergies_and_dislikes_are_hard_filters():
    st = state()
    oil = tr.ITEMS_BY_ID["diet_fats_cooking_oil"]  # needs a stove; this student has no kitchen
    assert tr.eligible(oil, state(profile={}, setup=twin_suggest.setup_from_profile({})), NO_ALLERGY)[0]
    assert tr.eligible(oil, st, NO_ALLERGY)[1] in ("needs", "context")
    nuts = tr.ITEMS_BY_ID["diet_protein_nut_snack"]
    peanut = lambda item: server.item_matches_allergy(item, ["peanut"])  # noqa: E731
    assert tr.eligible(nuts, st, peanut) == (False, "allergy")
    hates = twin_suggest.setup_from_profile({"kitchen_access": "none", "food_dislikes": "I hate nuts"})
    assert tr.eligible(nuts, state(setup=hates), NO_ALLERGY) == (False, "dislike")


def test_a_swap_for_someone_who_doesnt_eat_at_the_dining_hall_points_at_the_store():
    home = {"food_acquisition": ["grocery_store"], "meal_preparation": ["self"]}
    st = state(profile=home, setup=twin_suggest.setup_from_profile(home))
    s = {"id": "fats_whole_milk_yogurt", "habit": None, "evidence": None, "where": "On today's breakfast menu",
         "on_menu_today": [{"hall": "sbisa", "hall_label": "Sbisa", "period": "breakfast", "station": "Rooted",
                            "item_id": "x", "item_name": "Low Fat Vanilla Yogurt"}]}
    v = tr.view(tr.swap_item(s, None), [], st)
    assert v["on_menu_today"] == [] and v["where"] == "Pick it up next time you shop"
    assert v["grocery"] == ["Low-fat or nonfat yogurt"]
    v2 = tr.view(tr.swap_item(s, None), [], state())  # a meal-plan student keeps the menu
    assert v2["on_menu_today"][0]["item_name"] == "Low Fat Vanilla Yogurt"


# ---- learning from feedback --------------------------------------------------------------------------------
def test_constraints_from_feedback_rule_steps_out():
    st = state(facts=[{"key": "goal.activity", "kind": "goal", "status": "stated"},
                      {"key": "constraint.cost", "kind": "constraint", "status": "stated", "last_day": TODAY.isoformat()},
                      {"key": "constraint.schedule", "kind": "constraint", "status": "stated", "last_day": TODAY.isoformat()}])
    assert tr.eligible(tr.ITEMS_BY_ID["act_rec_center_class"], st, NO_ALLERGY) == (False, "cost")
    assert tr.eligible(tr.ITEMS_BY_ID["act_walk_with_friend"], st, NO_ALLERGY) == (False, "schedule")
    assert tr.eligible(tr.ITEMS_BY_ID["act_walk_after_lunch"], st, NO_ALLERGY)[0]


def test_old_constraints_expire_and_removed_ones_dont_come_back_from_the_profile():
    stale = [{"key": "constraint.cost", "kind": "constraint", "status": "stated", "last_day": "2026-05-01"}]
    assert "cost" not in state(facts=stale)["constraints"]
    budget = {"support_needs": ["budget_eating"]}
    assert "cost" in state(profile=budget)["constraints"]
    gone = [{"key": "constraint.cost", "kind": "constraint", "status": "removed"}]
    assert "cost" not in state(profile=budget, facts=gone)["constraints"]


def test_a_step_that_didnt_fit_brings_a_different_approach_to_the_same_goal():
    facts = confirmed("activity.low_weekdays") + circ("back_to_back_classes")
    fb = [{"rec_id": "act_walk_between_classes", "response": "didnt_fit", "reasons": ["schedule"],
           "patterns": ["activity.low_weekdays"], "created_at": "2026-11-10T12:00:00+00:00"}]
    plans = {"act_walk_between_classes": {"status": "didnt_fit", "day": "2026-11-10"}}
    st = state(facts=facts, feedback=fb, plans=plans, detected_keys={"activity.low_weekdays"})
    sel = tr.select(tr.ITEMS, st, NO_ALLERGY)
    assert "act_walk_between_classes" not in ids(sel)  # rested
    alt = [r for r in sel["recommendations"] if "different approach" in (r["why"] or "")]
    assert alt and alt[0]["domains"] == ["activity"]
    s, factors = tr.score(tr.ITEMS_BY_ID[alt[0]["id"]], st)
    assert ("alternative", "act_walk_between_classes", 2) in factors


def test_a_technique_that_worked_is_preferred_next_time():
    fb = [{"rec_id": "sleep_phone_across_room", "response": "worked", "reasons": [],
           "created_at": "2026-11-01T12:00:00+00:00"}]
    st = state(facts=confirmed("sleep.irregular_timing"), feedback=fb, detected_keys={"sleep.irregular_timing"})
    _, f = tr.score(tr.ITEMS_BY_ID["sleep_shared_room_setup"], st)  # also restructures the environment
    assert ("worked_bct", "restructuring_environment", 1) in f


def test_adopted_steps_are_reinforced_not_dropped_and_checked_in_on_later():
    plans = {"act_walk_after_lunch": {"status": "adopted", "day": "2026-11-10", "when": "after_lunch"},
             "sleep_wind_down_alarm": {"status": "adopted", "day": "2026-10-01"}}
    st = state(plans=plans)
    rein = {r["id"]: r for r in tr.reinforcing(st, TODAY.isoformat())}
    assert rein["act_walk_after_lunch"]["message"].endswith("Keep it tied to the end of lunch so it becomes automatic.")
    assert rein["act_walk_after_lunch"]["check_in"] is False
    assert rein["sleep_wind_down_alarm"]["check_in"] is True  # a while ago: "still doing it?"
    assert "act_walk_after_lunch" not in ids(tr.select(tr.ITEMS, st, NO_ALLERGY))


def test_a_step_being_tried_stays_pinned_but_still_obeys_a_new_allergy():
    plans = {"diet_protein_nut_snack": {"status": "trying", "day": "2026-11-09"}}
    sel = tr.select(tr.ITEMS, state(plans=plans), NO_ALLERGY)
    assert sel["recommendations"][0]["id"] == "diet_protein_nut_snack" and sel["recommendations"][0]["status"] == "trying"
    peanut = lambda item: server.item_matches_allergy(item, ["peanut"])  # noqa: E731
    assert "diet_protein_nut_snack" not in ids(tr.select(tr.ITEMS, state(plans=plans), peanut))


def test_not_hungry_early_and_a_safety_pause_hold_back_breakfast_and_food_and_exercise_steps():
    st = state(facts=confirmed("cross.weekday_squeeze") + circ("not_hungry_early"), detected_keys={"cross.weekday_squeeze"})
    assert all("breakfast_push" not in tr.ITEMS_BY_ID[i]["tags"] for i in ids(tr.select(tr.ITEMS, st, NO_ALLERGY)))
    paused = state(facts=confirmed("cross.weekday_squeeze", "sleep.irregular_timing"), paused=True,
                   detected_keys={"cross.weekday_squeeze", "sleep.irregular_timing"})
    recs = tr.select(tr.ITEMS, paused, NO_ALLERGY)["recommendations"]
    assert recs and all(r["domains"] == ["sleep"] for r in recs)


def test_every_shown_step_explains_itself_and_offers_a_coping_plan_for_named_barriers():
    st = state(facts=confirmed("sleep.irregular_timing") + [
        {"key": "constraint.forgot", "kind": "constraint", "status": "stated", "last_day": TODAY.isoformat()}],
        detected_keys={"sleep.irregular_timing"})
    for r in tr.select(tr.ITEMS, st, NO_ALLERGY)["recommendations"]:
        assert r["why"] and not re.search(r"\d", r["why"])
        assert server._guardrail_violation_type(r["why"]) is None
    alarm = tr.view(tr.ITEMS_BY_ID["sleep_wind_down_alarm"], [], st)
    assert alarm["coping"][0] == {"barrier": "forgot", "if": "If I forget", "then": "I'll tie it to something I already do every day"}
    assert alarm["techniques"] == ["Prompts and cues", "Action planning"]


def test_constraint_violations_are_reported_independently():
    st = state(facts=[{"key": "constraint.cost", "kind": "constraint", "status": "stated", "last_day": TODAY.isoformat()}])
    assert tr.constraint_violations(tr.ITEMS_BY_ID["act_rec_center_class"], st) == ["cost"]
    assert tr.constraint_violations(tr.ITEMS_BY_ID["act_walk_after_lunch"], st) == []


# ---- free-text notes ------------------------------------------------------------------------------------------
def test_notes_map_onto_the_fixed_lists_by_keywords():
    assert twin_profile.interpret_reason_note("honestly way too pricey for me") == ["cost"]
    assert twin_profile.interpret_reason_note("they didn't have it at sbisa") == ["availability"]
    assert twin_profile.interpret_reason_note("i forgot every single day") == ["forgot"]
    assert twin_profile.interpret_reason_note("meh") == []
    assert twin_profile.interpret_circumstance_note("my 8am lab", ["early_classes", "commute"]) == ["early_classes"]


def test_a_model_interpretation_keeps_only_codes_from_the_list():
    assert twin_profile.verify_interpretation('{"codes": ["energy", "hack_the_db", "cost"]}', ["energy", "cost"]) == ["energy", "cost"]
    assert twin_profile.verify_interpretation("not json", ["cost"]) == []
    assert twin_profile.verify_interpretation('{"codes": "cost"}', ["cost"]) == []


def test_allergy_and_dislike_checks_apply_to_food_steps_only():
    nut = lambda item: server.item_matches_allergy(item, ["nut", "peanut"])  # noqa: E731
    plan = tr.ITEMS_BY_ID["cross_plan_tomorrow"]  # "A minute each night..." contains "nut" as letters, not food
    st = state(facts=confirmed("cross.weekday_squeeze"), detected_keys={"cross.weekday_squeeze"})
    assert tr.eligible(plan, st, nut)[0]
    assert tr.eligible(tr.ITEMS_BY_ID["cross_grab_and_go_breakfast"], st, nut) == (False, "allergy")
    hates = twin_suggest.setup_from_profile({"kitchen_access": "none", "food_dislikes": "mornings and walking"})
    st2 = state(setup=hates, facts=confirmed("sleep.irregular_timing"), detected_keys={"sleep.irregular_timing"})
    assert tr.eligible(tr.ITEMS_BY_ID["sleep_morning_light"], st2, NO_ALLERGY)[0]


def test_a_lapsed_step_can_be_offered_again():
    plans = {"act_walk_after_lunch": {"status": "lapsed", "day": TODAY.isoformat()}}
    st = state(plans=plans, facts=confirmed("activity.low_weekdays"), detected_keys={"activity.low_weekdays"})
    assert tr.eligible(tr.ITEMS_BY_ID["act_walk_after_lunch"], st, NO_ALLERGY)[0]
    assert ("lapsed", None, 1) in tr.score(tr.ITEMS_BY_ID["act_walk_after_lunch"], st)[1]
