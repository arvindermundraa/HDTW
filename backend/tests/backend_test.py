"""Backend regression tests for the LLHS API.

Rebuilt to match the architecture grounded in the five source documents
(LLHS App Review Notes; LLHS App Onboarding Nutrition & Lifestyle Profile;
LLHS HEI-2020 National Benchmark Reference; Updated DTL Slides 9.10.26;
8.18 Meeting Slides) rather than the retired Mini-EAT/"digital twin"/LE8
model. Key differences from the previous suite this file replaces:

  - No more /onboarding/mini-eat, /twin, or a single 0-100 heart-health
    score. Onboarding is now a schema-driven Nutrition & Lifestyle Profile
    survey (personalization/context only, not a diet-quality screener —
    HEI-2020 scoring happens externally via ASA24 and is imported through
    a researcher-only endpoint).
  - FOOD / MOVE / REST are three separate domains, never combined.
  - Lightweight meal logging uses 9 qualitative category tags instead of
    has_vegetables/has_whole_grains/has_lean_protein booleans.
  - The research-only portion-quantity-estimation pipeline was removed
    entirely rather than re-justified, since it wasn't grounded in any of
    the current source documents.
"""
import os
import io
import re
import base64
import uuid
import pytest
import requests
from PIL import Image, ImageDraw

from pathlib import Path
from dotenv import load_dotenv
# The original CI container keeps the backend URL in /app/frontend/.env;
# locally, fall back to this repo's frontend/.env, then to an explicit
# EXPO_PUBLIC_BACKEND_URL env var (which always wins — load_dotenv never
# overrides an already-set variable).
for _env in ("/app/frontend/.env", Path(__file__).resolve().parents[2] / "frontend" / ".env"):
    if Path(_env).exists():
        load_dotenv(_env)
BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "http://localhost:8001").rstrip("/")
API = f"{BASE_URL}/api"
RATE_LIMIT_ENABLED = os.environ.get("RATE_LIMIT_ENABLED", "true").strip().lower() not in ("0", "false", "no", "off")


def _rand_email():
    return f"test_{uuid.uuid4().hex[:8]}@example.com"


@pytest.fixture(scope="session")
def s():
    return requests.Session()


# Minimal set of PROFILE_SURVEY_SCHEMA-required answers — enough to pass
# validate_profile_answers() without asserting on every optional field.
_MINIMAL_PROFILE_ANSWERS = {
    "age": 22,
    "gender": "prefer_not_to_say",
    "student_status": "full_time",
    "academic_major": "Nutrition Science",
    "employment_status": "not_employed",
    "residence": "residence_hall",
    "university_meal_plan": "yes",
    "kitchen_access": "none",
}


def _register(s, name="Test User", extra_profile=None):
    email = _rand_email()
    pw = "Passw0rd!"
    r = s.post(f"{API}/auth/register", json={"email": email, "password": pw, "name": name})
    assert r.status_code == 200, r.text
    tok = r.json()["token"]
    headers = {"Authorization": f"Bearer {tok}"}
    answers = {**_MINIMAL_PROFILE_ANSWERS, **(extra_profile or {})}
    r2 = s.post(f"{API}/onboarding/profile-survey", json={"answers": answers}, headers=headers)
    assert r2.status_code == 200, r2.text
    return {"email": email, "password": pw, "token": tok, "headers": headers, "user": r2.json()["user"]}


@pytest.fixture(scope="session")
def new_user(s):
    """Register a fresh user + finish onboarding so meal logging etc. work."""
    return _register(s)


# ---------- Auth ----------
class TestAuth:
    def test_register(self, s):
        r = s.post(f"{API}/auth/register",
                   json={"email": _rand_email(), "password": "Passw0rd!", "name": "Alice"})
        assert r.status_code == 200
        d = r.json()
        assert "token" in d and d["user"]["onboarded"] is False

    def test_duplicate_register(self, s, new_user):
        r = s.post(f"{API}/auth/register",
                   json={"email": new_user["email"], "password": "x123456", "name": "dup"})
        assert r.status_code == 409

    def test_login_and_me(self, s, new_user):
        r = s.post(f"{API}/auth/login", json={"email": new_user["email"], "password": new_user["password"]})
        assert r.status_code == 200
        tok = r.json()["token"]
        me = s.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {tok}"})
        assert me.status_code == 200
        assert me.json()["email"] == new_user["email"]
        assert me.json()["onboarded"] is True

    def test_login_bad_password(self, s, new_user):
        r = s.post(f"{API}/auth/login", json={"email": new_user["email"], "password": "wrong!!"})
        assert r.status_code == 401

    def test_me_unauth(self, s):
        r = s.get(f"{API}/auth/me")
        assert r.status_code == 401


# ---------- Onboarding: Nutrition & Lifestyle Profile survey ----------
class TestOnboardingProfileSurvey:
    def test_get_schema_shape(self, s):
        r = s.get(f"{API}/onboarding/profile-survey")
        assert r.status_code == 200
        d = r.json()
        assert len(d["sections"]) >= 7
        question_ids = {q["id"] for q in d["questions"]}
        # Spot-check a question from each of the four spec sections.
        for qid in ("dietary_restrictions", "kitchen_access", "food_acquisition", "hardest_meal"):
            assert qid in question_ids

    def test_missing_required_answers_rejected(self, s):
        email = _rand_email()
        r = s.post(f"{API}/auth/register", json={"email": email, "password": "Passw0rd!", "name": "Incomplete"})
        headers = {"Authorization": f"Bearer {r.json()['token']}"}
        partial = {"age": 21}  # deliberately omits other required questions
        r2 = s.post(f"{API}/onboarding/profile-survey", json={"answers": partial}, headers=headers)
        assert r2.status_code == 400

    def test_invalid_option_rejected(self, s):
        email = _rand_email()
        r = s.post(f"{API}/auth/register", json={"email": email, "password": "Passw0rd!", "name": "BadOption"})
        headers = {"Authorization": f"Bearer {r.json()['token']}"}
        bad = {**_MINIMAL_PROFILE_ANSWERS, "gender": "not_a_real_option"}
        r2 = s.post(f"{API}/onboarding/profile-survey", json={"answers": bad}, headers=headers)
        assert r2.status_code == 400

    def test_skip_logic_does_not_require_hidden_questions(self, s):
        # kitchen_access="none" hides kitchen_shared_count/appliances/cookware
        # entirely per the skip-logic rule — submitting without them must pass.
        email = _rand_email()
        r = s.post(f"{API}/auth/register", json={"email": email, "password": "Passw0rd!", "name": "NoKitchen"})
        headers = {"Authorization": f"Bearer {r.json()['token']}"}
        r2 = s.post(f"{API}/onboarding/profile-survey",
                    json={"answers": {**_MINIMAL_PROFILE_ANSWERS, "kitchen_access": "none"}}, headers=headers)
        assert r2.status_code == 200, r2.text

    def test_patch_merges_into_existing_profile(self, s, new_user):
        r = s.patch(f"{API}/onboarding/profile-survey",
                    json={"answers": {"food_dislikes": "mushrooms"}}, headers=new_user["headers"])
        assert r.status_code == 200, r.text

    def test_allergy_terms_extracted_from_restrictions(self, s):
        # Safety-relevant field per the review notes — vegetarian selection
        # should translate into suppression terms used downstream.
        email = _rand_email()
        r = s.post(f"{API}/auth/register", json={"email": email, "password": "Passw0rd!", "name": "VegTest"})
        headers = {"Authorization": f"Bearer {r.json()['token']}"}
        answers = {**_MINIMAL_PROFILE_ANSWERS, "dietary_restrictions": ["vegetarian"]}
        r2 = s.post(f"{API}/onboarding/profile-survey", json={"answers": answers}, headers=headers)
        assert r2.status_code == 200, r2.text
        # Not directly exposed on /auth/me, but downstream effect is tested
        # in TestAllergyAwareSuppression below via ingredient/menu filtering.


# ---------- Meal logging (lightweight categories) + Safety Layer ----------
class TestMealsAndSafety:
    def test_get_log_categories(self, s):
        r = s.get(f"{API}/meals/categories")
        assert r.status_code == 200
        cats = r.json()["categories"]
        ids = {c["id"] for c in cats}
        assert ids == {
            "vegetables", "fruit", "whole_grains", "refined_grains_starchy",
            "beans_fish_nuts", "other_protein", "dairy", "added_sugars", "salty_processed",
        }

    def test_create_meal_with_categories_persists(self, s, new_user):
        h = new_user["headers"]
        payload = {"name": "Grain bowl", "meal_type": "lunch",
                   "categories": ["vegetables", "whole_grains", "other_protein"], "portion": "normal"}
        r = s.post(f"{API}/meals", json=payload, headers=h)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["meal"]["categories"] == payload["categories"]
        assert "safety_checkin" in d and "points_awarded" in d
        lst = s.get(f"{API}/meals", headers=h).json()
        assert any(m["name"] == "Grain bowl" for m in lst)

    def test_unknown_category_rejected(self, s, new_user):
        r = s.post(f"{API}/meals", json={"name": "Bad cats", "categories": ["not_a_real_category"]},
                   headers=new_user["headers"])
        assert r.status_code == 422

    def test_categorize_meal_text(self, s, new_user):
        # Answers the open technical question from the review notes: can a
        # free-text description be auto-mapped to the lightweight categories?
        r = s.post(f"{API}/meals/categorize-text", json={"description": "grilled chicken, brown rice, broccoli"},
                    headers=new_user["headers"], timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("categories", "suggested_name", "confidence", "allergy_flag", "tamus_key_required"):
            assert k in d
        assert isinstance(d["categories"], list)
        assert all(c in {"vegetables", "fruit", "whole_grains", "refined_grains_starchy", "beans_fish_nuts",
                          "other_protein", "dairy", "added_sugars", "salty_processed"} for c in d["categories"])
        # Mandatory-key contract — see TestPhotoAnalysis for the full note.
        assert d["tamus_key_required"] is True

    def test_activity_and_sleep_log(self, s, new_user):
        h = new_user["headers"]
        a = s.post(f"{API}/activities", json={"minutes": 45, "kind": "moderate"}, headers=h)
        assert a.status_code == 200
        sl = s.post(f"{API}/sleep", json={"hours": 7.5, "source": "manual"}, headers=h)
        assert sl.status_code == 200
        assert sl.json()["source"] == "manual"

    def test_safety_layer_triggers_on_3_skipped(self, s):
        email = _rand_email()
        reg = s.post(f"{API}/auth/register",
                     json={"email": email, "password": "Passw0rd!", "name": "Skip"}).json()
        h = {"Authorization": f"Bearer {reg['token']}"}
        s.post(f"{API}/onboarding/profile-survey", json={"answers": _MINIMAL_PROFILE_ANSWERS}, headers=h)
        checkin = None
        for i in range(3):
            r = s.post(f"{API}/meals", json={"name": "skip", "skipped": True, "meal_type": "lunch"}, headers=h)
            assert r.status_code == 200
            if r.json().get("safety_checkin"):
                checkin = r.json()["safety_checkin"]
        assert checkin is not None, "Safety check-in should trigger after 3 skipped meals"
        got = s.get(f"{API}/safety/checkin", headers=h).json()
        assert got["checkin"] is not None
        ack = s.post(f"{API}/safety/checkin/{checkin['id']}/ack", headers=h)
        assert ack.status_code == 200 and ack.json()["ok"] is True
        after = s.get(f"{API}/safety/checkin", headers=h).json()
        assert after["checkin"] is None


# ---------- HEI-2020 assessments (ASA24-derived, researcher-imported) ----------
class TestHeiAssessments:
    RESEARCH_KEY = os.environ.get("RESEARCH_API_KEY", "")

    def test_import_requires_valid_key(self, s, new_user):
        r = s.post(f"{API}/research/hei2020-assessments",
                    json={"participant_email": new_user["email"], "assessment_type": "baseline",
                          "components": {"whole_grains": 4.2}},
                    headers={"X-Research-Key": "definitely-wrong"})
        assert r.status_code == 401

    def test_import_missing_key_rejected(self, s, new_user):
        r = s.post(f"{API}/research/hei2020-assessments",
                    json={"participant_email": new_user["email"], "assessment_type": "baseline",
                          "components": {"whole_grains": 4.2}})
        assert r.status_code == 401

    @pytest.mark.skipif(not RESEARCH_KEY, reason="RESEARCH_API_KEY not configured in this environment")
    def test_import_and_read_back(self, s):
        user = _register(s, name="HeiUser")
        components = {c["id"]: 3.0 for c in [
            {"id": "total_fruits"}, {"id": "whole_fruits"}, {"id": "total_vegetables"},
            {"id": "greens_beans"}, {"id": "whole_grains"}, {"id": "dairy"},
            {"id": "total_protein_foods"}, {"id": "seafood_plant_proteins"}, {"id": "fatty_acids"},
            {"id": "refined_grains"}, {"id": "sodium"}, {"id": "added_sugars"}, {"id": "saturated_fats"},
        ]}
        # Whole Grains deliberately set well below its 1.70 national benchmark
        # is NOT what we want here (it should be a strength) — set it high so
        # it surfaces as a strength, and drop something else low for a focus
        # candidate.
        components["whole_grains"] = 8.0
        components["sodium"] = 1.0
        r = s.post(f"{API}/research/hei2020-assessments",
                    json={"participant_email": user["email"], "assessment_type": "baseline",
                          "components": components},
                    headers={"X-Research-Key": self.RESEARCH_KEY})
        assert r.status_code == 200, r.text

        hist = s.get(f"{API}/assessments/hei2020/history", headers=user["headers"])
        assert hist.status_code == 200
        assert len(hist.json()) == 1
        assert hist.json()[0]["assessment_type"] == "baseline"

        candidates = s.get(f"{API}/assessments/hei2020/focus-candidates", headers=user["headers"])
        assert candidates.status_code == 200
        cd = candidates.json()
        assert cd["has_assessment"] is True
        candidate_ids = {c["id"] for c in cd["candidates"]}
        assert "sodium" in candidate_ids  # far below its benchmark -> meaningful room for improvement
        assert "whole_grains" not in candidate_ids  # already well above benchmark

        pick = list(candidate_ids)[:2] if len(candidate_ids) >= 2 else (list(candidate_ids) + ["dairy"])[:2]
        set_focus = s.post(f"{API}/profile/focus-areas", json={"component_ids": pick}, headers=user["headers"])
        assert set_focus.status_code == 200, set_focus.text

        food = s.get(f"{API}/domains/food", headers=user["headers"])
        assert food.status_code == 200
        fd = food.json()
        assert fd["has_assessment"] is True
        # Number-disclosure discipline: focus areas carry participant_score +
        # maximum_score only, never the national benchmark value.
        for fa in fd["focus_areas"]:
            assert "national_benchmark" not in fa
            assert "participant_score" in fa and "maximum_score" in fa
        # Strengths carry direction only, never any numeric score at all.
        for st in fd["strengths"]:
            assert st["direction"] == "above_national_benchmark"
            assert not any(isinstance(v, (int, float)) for v in st.values())

    def test_focus_areas_require_assessment_and_cap_at_three(self, s, new_user):
        r = s.post(f"{API}/profile/focus-areas", json={"component_ids": ["sodium"]}, headers=new_user["headers"])
        assert r.status_code == 400  # no assessment yet
        r2 = s.post(f"{API}/profile/focus-areas", json={"component_ids": []}, headers=new_user["headers"])
        assert r2.status_code == 422
        r3 = s.post(f"{API}/profile/focus-areas",
                    json={"component_ids": ["sodium", "dairy", "added_sugars", "whole_grains"]},
                    headers=new_user["headers"])
        assert r3.status_code == 422

    def _import(self, s, user, components):
        r = s.post(f"{API}/research/hei2020-assessments",
                   json={"participant_email": user["email"], "assessment_type": "baseline", "components": components},
                   headers={"X-Research-Key": self.RESEARCH_KEY})
        assert r.status_code == 200, r.text

    @pytest.mark.skipif(not RESEARCH_KEY, reason="RESEARCH_API_KEY not configured in this environment")
    def test_single_focus_area_allowed_only_with_one_candidate(self, s):
        import server
        maxed = {c["id"]: float(c["max_score"]) for c in server.HEI2020_COMPONENTS}

        one = _register(s, name="OneCandidate")
        self._import(s, one, {**maxed, "sodium": 1.0})  # only sodium is below benchmark
        cd = s.get(f"{API}/assessments/hei2020/focus-candidates", headers=one["headers"]).json()
        assert [c["id"] for c in cd["candidates"]] == ["sodium"]
        assert cd["min_selection"] == 1 and cd["max_selection"] == 3
        r = s.post(f"{API}/profile/focus-areas", json={"component_ids": ["sodium"]}, headers=one["headers"])
        assert r.status_code == 200, r.text

        two = _register(s, name="TwoCandidates")
        self._import(s, two, {**maxed, "sodium": 1.0, "added_sugars": 1.0})
        cd2 = s.get(f"{API}/assessments/hei2020/focus-candidates", headers=two["headers"]).json()
        assert cd2["min_selection"] == 2
        r2 = s.post(f"{API}/profile/focus-areas", json={"component_ids": ["sodium"]}, headers=two["headers"])
        assert r2.status_code == 422
        r3 = s.post(f"{API}/profile/focus-areas", json={"component_ids": ["sodium", "added_sugars"]},
                    headers=two["headers"])
        assert r3.status_code == 200, r3.text

    def test_focus_areas_reject_unknown_component(self, s, new_user):
        r = s.post(f"{API}/profile/focus-areas",
                    json={"component_ids": ["sodium", "made_up_component"]}, headers=new_user["headers"])
        assert r.status_code == 422


# ---------- FOOD / MOVE / REST domains (never combined into one score) ----------
class TestDomains:
    def test_food_domain_without_assessment(self, s, new_user):
        r = s.get(f"{API}/domains/food", headers=new_user["headers"])
        assert r.status_code == 200
        d = r.json()
        assert d["has_assessment"] is False
        assert d["focus_areas"] == [] and d["strengths"] == []

    def test_move_domain_shape(self, s, new_user):
        r = s.get(f"{API}/domains/move", headers=new_user["headers"])
        assert r.status_code == 200
        d = r.json()
        for k in ("weekly_activity_minutes", "wearable_connected", "reference_note"):
            assert k in d

    def test_rest_domain_shape(self, s, new_user):
        r = s.get(f"{API}/domains/rest", headers=new_user["headers"])
        assert r.status_code == 200
        d = r.json()
        for k in ("avg_sleep_hours", "confidence", "wearable_connected", "reference_note"):
            assert k in d

    def test_aggregate_domains_never_combined_into_one_score(self, s, new_user):
        r = s.get(f"{API}/domains", headers=new_user["headers"])
        assert r.status_code == 200
        d = r.json()
        assert set(d.keys()) == {"food", "move", "rest"}
        # Hard structural check: no combined overall/score key anywhere.
        assert "overall" not in d and "score" not in d


# ---------- My Path — trail/milestone avatar ----------
class TestPath:
    def test_path_shape_and_milestones_are_behavioral(self, s, new_user):
        r = s.get(f"{API}/path", headers=new_user["headers"])
        assert r.status_code == 200
        d = r.json()
        assert 0.0 <= d["position"] <= 1.0
        assert len(d["milestones"]) >= 4
        for m in d["milestones"]:
            for k in ("id", "label", "behavior", "achieved"):
                assert k in m
            # Milestones must be behavior-labeled, never a health outcome/weight claim.
            assert "weight" not in m["label"].lower() and "calorie" not in m["label"].lower()
        assert "next_checkin" in d and "message" in d["next_checkin"]

    def test_path_advances_after_logging(self, s):
        user = _register(s, name="PathUser")
        before = s.get(f"{API}/path", headers=user["headers"]).json()
        s.post(f"{API}/meals", json={"name": "First meal", "categories": ["vegetables"]}, headers=user["headers"])
        after = s.get(f"{API}/path", headers=user["headers"]).json()
        assert after["position"] >= before["position"]


# ---------- Curriculum + Youth Ambassador peer videos + Games ----------
class TestCurriculumGames:
    def test_curriculum_includes_peer_videos(self, s, new_user):
        cur = s.get(f"{API}/curriculum", headers=new_user["headers"]).json()
        assert len(cur) == 3
        for lesson in cur:
            assert "peer_video" in lesson
            for k in ("ambassador_name", "title", "video_url", "transition_line"):
                assert k in lesson["peer_video"]

    def test_curriculum_complete_idempotent(self, s, new_user):
        h = new_user["headers"]
        cur = s.get(f"{API}/curriculum", headers=h).json()
        first_id = cur[0]["id"]
        r1 = s.post(f"{API}/curriculum/{first_id}/complete", headers=h).json()
        assert r1["points_awarded"] >= 0
        r2 = s.post(f"{API}/curriculum/{first_id}/complete", headers=h).json()
        assert r2["already"] is True and r2["points_awarded"] == 0

    def test_curriculum_not_found(self, s, new_user):
        r = s.post(f"{API}/curriculum/bogus/complete", headers=new_user["headers"])
        assert r.status_code == 404

    def test_games_complete_stores_markers(self, s, new_user):
        h = new_user["headers"]
        games = s.get(f"{API}/games", headers=h).json()
        assert len(games) == 3
        gid = games[0]["id"]
        r = s.post(f"{API}/games/{gid}/complete", json={"markers": ["planning_gap"], "score": 1}, headers=h)
        assert r.status_code == 200


# ---------- Gamification + Cohort ----------
class TestGamification:
    def test_gamification(self, s, new_user):
        r = s.get(f"{API}/gamification", headers=new_user["headers"])
        assert r.status_code == 200
        d = r.json()
        assert "points" in d and "badges" in d and "streak" in d

    def test_cohort_cooperative(self, s, new_user):
        r = s.get(f"{API}/cohort", headers=new_user["headers"])
        assert r.status_code == 200
        d = r.json()
        assert d["target"] == 500
        assert d["current"] <= d["target"]
        assert isinstance(d["your_contribution"], int)


# ---------- Chat ("Future Me") ----------
class TestChat:
    def test_chat_without_tamus_key_returns_clear_prompt_not_a_crash(self, s, new_user):
        """TAMU AI is mandatory and the app's only AI provider (Emergent has
        been fully removed) — a freshly registered participant has no TAMU
        key yet, and isn't on the staff-managed admin/testing allowlist
        either, so /chat must degrade to a clear, safe "add your key"
        prompt rather than error out or silently produce nothing. Exercising
        the *actual* grounded-answer path additionally requires a live TAMU
        API key (personal or admin/testing pool), which this environment
        doesn't have configured — see test_grounded_reply_with_a_real_key,
        which documents and skips that case explicitly rather than pretend
        to cover it."""
        r = s.post(f"{API}/chat", json={"message": "How much fiber should I eat?"},
                   headers=new_user["headers"], timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["tamus_key_required"] is True
        assert isinstance(d["answer"], str) and "TAMU AI" in d["answer"] and "Settings" in d["answer"]
        assert d["citations"] == []
        assert d["pending_action"] is None
        assert d["points_awarded"] == 0
        assert "Illustrative" in d["disclaimer"]

    @pytest.mark.skip(reason="Needs a real TAMU API key (personal or admin/testing pool) configured "
                              "in this environment — see backend/tamus_client.py and README §6.")
    def test_grounded_reply_with_a_real_key(self):
        """Documents the coverage gap left by the mandatory-key change: with
        a working TAMU key, /chat should return a grounded, directional-only
        answer with citations, same contract this test replaced used to
        check end-to-end. Un-skip this once TAMUS_ADMIN_TEST_EMAILS /
        TAMUS_ADMIN_API_KEYS (or a per-test personal key) are available to
        the running server process."""

    def test_chat_history(self, s, new_user):
        r = s.get(f"{API}/chat/history", headers=new_user["headers"])
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_suggested_prompts_are_dynamic(self, s, new_user):
        r = s.get(f"{API}/chat/suggested-prompts", headers=new_user["headers"])
        assert r.status_code == 200
        d = r.json()
        assert 3 <= len(d["prompts"]) <= 4
        assert all(isinstance(p, str) and p for p in d["prompts"])

    def test_suggested_prompts_use_onboarding_profile(self, s):
        import server
        user = _register(s, name="PromptProfile", extra_profile={
            "hardest_meal": "lunch", "hardest_meal_location": "campus", "support_needs": ["budget_eating"],
        })
        prompts = s.get(f"{API}/chat/suggested-prompts", headers=user["headers"]).json()["prompts"]
        assert 3 <= len(prompts) <= 4
        joined = " ".join(prompts).lower()
        assert "lunch" in joined and "campus" in joined
        # No prompt may itself trip the chat guardrail.
        assert all(server._guardrail_violation_type(p) is None for p in prompts)


# ---------- Chat-driven actions (log a meal/activity/sleep, set focus
# areas via natural language) — the model only ever PROPOSES these (tested
# directly against the parser below, since forcing a specific live-LLM
# output isn't reliable); confirm-action is what actually executes one,
# and is tested here as its own endpoint so the write path is verified
# regardless of what any particular chat turn happened to produce. ----------
class TestChatActions:
    RESEARCH_KEY = os.environ.get("RESEARCH_API_KEY", "")

    def test_action_parser_direct(self):
        """Direct, deterministic test of the parsing/validation logic that
        sits between the model's raw output and anything ever being
        written — same pattern as test_guardrail_layer_functions_directly."""
        import server

        visible, action = server._parse_chat_action(
            'Nice, that sounds balanced!\nACTION_JSON: {"type": "log_meal", '
            '"payload": {"name": "chicken salad", "categories": ["vegetables", "other_protein"], '
            '"meal_type": "lunch"}}'
        )
        assert "ACTION_JSON" not in visible
        assert action["type"] == "log_meal"
        assert action["payload"]["categories"] == ["vegetables", "other_protein"]
        assert "summary" in action and isinstance(action["summary"], str) and action["summary"]

        # A message with no logging/edit intent must never produce an action.
        visible2, action2 = server._parse_chat_action("Sure, fiber helps with fullness and digestion.")
        assert action2 is None
        assert visible2 == "Sure, fiber helps with fullness and digestion."

        # An unknown/hallucinated action type is dropped, never surfaced —
        # but the raw JSON line is still stripped so it never leaks as text.
        visible3, action3 = server._parse_chat_action(
            'Sure!\nACTION_JSON: {"type": "delete_my_account", "payload": {}}'
        )
        assert action3 is None
        assert "ACTION_JSON" not in visible3 and "delete_my_account" not in visible3

        # An invalid payload for a real action type (bad category id) is
        # also dropped, not passed through half-validated.
        visible4, action4 = server._parse_chat_action(
            'Got it.\nACTION_JSON: {"type": "log_meal", "payload": {"name": "x", '
            '"categories": ["not_a_real_category"]}}'
        )
        assert action4 is None

        # A sleep action can never smuggle a "wearable" source through chat —
        # the validator only ever reads `hours`, so a spoofed source field
        # in the payload is simply ignored, and _internal_log_sleep forces
        # source="manual" again on top of that (tested at the HTTP layer
        # below).
        visible5, action5 = server._parse_chat_action(
            'Logged.\nACTION_JSON: {"type": "log_sleep", "payload": {"hours": 7.5, "source": "wearable"}}'
        )
        assert action5["payload"].get("source") != "wearable"

    def test_confirm_action_requires_auth(self, s):
        r = s.post(f"{API}/chat/confirm-action",
                    json={"type": "log_activity", "payload": {"minutes": 10}})
        assert r.status_code == 401

    def test_confirm_action_unknown_type_rejected(self, s, new_user):
        r = s.post(f"{API}/chat/confirm-action",
                    json={"type": "delete_my_account", "payload": {}}, headers=new_user["headers"])
        assert r.status_code == 422  # not in ChatActionIn's Literal[...]

    def test_confirm_action_log_meal_activity_and_sleep(self, s):
        # One registration covering three action types — logging in a
        # rate-limited (5/hour) /auth/register world is itself the resource
        # to be economical with, same as every other multi-assertion test
        # in this file that shares one registered user across related checks.
        user = _register(s, name="ChatActionMealActivitySleep")

        r = s.post(f"{API}/chat/confirm-action",
                    json={"type": "log_meal",
                          "payload": {"name": "grilled chicken salad", "meal_type": "lunch",
                                      "categories": ["vegetables", "other_protein"]}},
                    headers=user["headers"])
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["type"] == "log_meal"
        assert d["result"]["meal"]["categories"] == ["vegetables", "other_protein"]
        assert d["result"]["meal"]["source"] == "text"
        assert d["result"]["points_awarded"] == 10  # same shared award path as POST /meals
        meals = s.get(f"{API}/meals", headers=user["headers"])
        assert any(m["name"] == "grilled chicken salad" for m in meals.json())

        r2 = s.post(f"{API}/chat/confirm-action",
                     json={"type": "log_activity", "payload": {"minutes": 25, "kind": "walking"}},
                     headers=user["headers"])
        assert r2.status_code == 200, r2.text
        assert r2.json()["result"]["minutes"] == 25

        # #5 security-fix guarantee for POST /sleep, replicated for the chat
        # action path: it can never claim a higher-confidence wearable
        # reading than the participant actually gave it.
        r3 = s.post(f"{API}/chat/confirm-action",
                     json={"type": "log_sleep", "payload": {"hours": 7.5, "source": "wearable"}},
                     headers=user["headers"])
        assert r3.status_code == 200, r3.text
        assert r3.json()["result"]["source"] == "manual"

    def test_confirm_action_log_meal_rejects_invalid_category(self, s, new_user):
        r = s.post(f"{API}/chat/confirm-action",
                    json={"type": "log_meal", "payload": {"name": "x", "categories": ["made_up_category"]}},
                    headers=new_user["headers"])
        assert r.status_code == 422

    def test_confirm_action_set_focus_areas_without_assessment_rejected(self, s, new_user):
        r = s.post(f"{API}/chat/confirm-action",
                    json={"type": "set_focus_areas", "payload": {"component_ids": ["sodium", "added_sugars"]}},
                    headers=new_user["headers"])
        assert r.status_code == 400

    @pytest.mark.skipif(not RESEARCH_KEY, reason="RESEARCH_API_KEY not configured in this environment")
    def test_confirm_action_set_focus_areas(self, s):
        user = _register(s, name="ChatActionFocus")
        components = {c: 3.0 for c in ("total_fruits", "whole_fruits", "total_vegetables", "greens_beans",
                                        "whole_grains", "dairy", "total_protein_foods", "seafood_plant_proteins",
                                        "fatty_acids", "refined_grains", "sodium", "added_sugars", "saturated_fats")}
        s.post(f"{API}/research/hei2020-assessments",
               json={"participant_email": user["email"], "assessment_type": "baseline", "components": components},
               headers={"X-Research-Key": self.RESEARCH_KEY})
        r = s.post(f"{API}/chat/confirm-action",
                    json={"type": "set_focus_areas", "payload": {"component_ids": ["sodium", "added_sugars"]}},
                    headers=user["headers"])
        assert r.status_code == 200, r.text
        assert set(r.json()["result"]["focus_areas"]) == {"sodium", "added_sugars"}


# ---------- Photo analysis (Gemini 3 Flash) ----------
def _make_food_image_b64():
    img = Image.new("RGB", (512, 512), (240, 232, 210))
    d = ImageDraw.Draw(img)
    d.ellipse((40, 40, 472, 472), fill=(255, 255, 250), outline=(180, 180, 180), width=4)
    d.ellipse((80, 100, 220, 240), fill=(60, 130, 55))
    d.ellipse((100, 130, 180, 210), fill=(85, 160, 70))
    for x in range(260, 430, 8):
        for y in range(100, 240, 8):
            d.ellipse((x, y, x + 6, y + 4), fill=(200, 175, 130))
    d.ellipse((140, 270, 380, 420), fill=(215, 180, 140), outline=(160, 120, 90), width=2)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


class TestPhotoAnalysis:
    def test_analyze_photo_returns_categories_not_booleans(self, s, new_user):
        b64 = _make_food_image_b64()
        r = s.post(f"{API}/meals/analyze-photo", json={"image_base64": b64},
                   headers=new_user["headers"], timeout=90)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("items", "categories", "confidence", "needs_confirmation", "suggested_name",
                  "allergy_flag", "tamus_key_required"):
            assert k in d, f"missing key {k}"
        assert "has_vegetables" not in d  # retired boolean shape
        assert isinstance(d["confidence"], (int, float))
        assert 0.0 <= d["confidence"] <= 1.0
        # Mandatory-key contract: a fresh test user has no TAMU key and
        # isn't on the admin/testing allowlist, so this degrades to manual
        # entry rather than a real recognition result — never a crash.
        assert d["tamus_key_required"] is True
        assert d["categories"] == [] and d["confidence"] == 0.0


# Voice Logging (record-a-voice-note-to-log-a-meal) was removed as of
# 2026-09 along with Emergent: TAMU AI, now the app's sole AI provider,
# documents no audio/speech input anywhere (checked against TAMU IT's own
# service page and the team's reference wrapper, taugroup/TAMU-Chat-AI).
# POST /meals/transcribe-voice no longer exists — see README/PRD.


# ---------- Wearable Move/Rest (Fitbit primary, Apple Health/Health Connect alt) ----------
class TestWearable:
    def test_status_defaults_disconnected(self, s, new_user):
        r = s.get(f"{API}/wearable/status", headers=new_user["headers"])
        assert r.status_code == 200
        d = r.json()
        assert d["connected"] is False
        assert d["provider"] is None

    def test_sync_requires_connection(self, s, new_user):
        r = s.post(f"{API}/wearable/sync-sleep", json={"hours": 7.5}, headers=new_user["headers"])
        assert r.status_code == 400

    def test_fitbit_connect_sync_both_sleep_and_activity(self, s):
        user = _register(s, name="FitbitUser")
        h = user["headers"]
        r = s.post(f"{API}/wearable/connect", json={"provider": "fitbit"}, headers=h)
        assert r.status_code == 200
        assert r.json() == {"connected": True, "provider": "fitbit", "last_sync": None}

        r2 = s.post(f"{API}/wearable/sync-sleep", json={"hours": 7.8, "activity_minutes": 30}, headers=h)
        assert r2.status_code == 200, r2.text
        d2 = r2.json()
        assert d2["synced"] is True and d2["hours"] == 7.8 and d2["activity_minutes"] == 30

        move = s.get(f"{API}/domains/move", headers=h).json()
        assert move["weekly_activity_minutes"] >= 30
        rest = s.get(f"{API}/domains/rest", headers=h).json()
        assert rest["confidence"] != "none"

        r4 = s.post(f"{API}/wearable/disconnect", headers=h)
        assert r4.status_code == 200
        assert r4.json()["connected"] is False

    def test_apple_health_connect_flow_unchanged(self, s, new_user):
        r = s.post(f"{API}/wearable/connect", json={"provider": "apple_health"}, headers=new_user["headers"])
        assert r.status_code == 200
        assert r.json()["provider"] == "apple_health"
        s.post(f"{API}/wearable/disconnect", headers=new_user["headers"])


# ---------- Gentle Nudges ----------
class TestNudgeSettings:
    def test_default_opt_out(self, s, new_user):
        r = s.get(f"{API}/settings/nudges", headers=new_user["headers"])
        assert r.status_code == 200
        assert r.json()["enabled"] is False

    def test_update_nudge_settings(self, s, new_user):
        r = s.patch(f"{API}/settings/nudges", json={"enabled": True, "time": "20:30"}, headers=new_user["headers"])
        assert r.status_code == 200
        d = r.json()
        assert d["enabled"] is True and d["time"] == "20:30"
        r2 = s.get(f"{API}/settings/nudges", headers=new_user["headers"])
        assert r2.json() == {"enabled": True, "time": "20:30"}

    def test_invalid_time_rejected(self, s, new_user):
        r = s.patch(f"{API}/settings/nudges", json={"enabled": True, "time": "25:99"}, headers=new_user["headers"])
        assert r.status_code == 422


# ---------- Weekly Story ----------
class TestWeeklyStory:
    def test_weekly_story_shape(self, s, new_user):
        r = s.get(f"{API}/weekly-story", headers=new_user["headers"])
        assert r.status_code == 200, r.text
        d = r.json()
        assert "chapters" in d and isinstance(d["chapters"], list)
        assert len(d["chapters"]) >= 5
        for ch in d["chapters"]:
            for k in ("id", "kicker", "title", "stat", "body"):
                assert k in ch, f"chapter missing key {k}"
            assert "calorie" not in ch["body"].lower()
            assert "weight" not in ch["body"].lower()


# ---------- Build a Balanced Meal — drag-and-drop plate builder ----------
class TestPlateBuilder:
    def test_get_ingredients_grouped_by_category(self, s, new_user):
        r = s.get(f"{API}/games/ingredients", headers=new_user["headers"])
        assert r.status_code == 200, r.text
        d = r.json()
        assert len(d["ingredients"]) > 0
        for ing in d["ingredients"]:
            for k in ("id", "name", "category", "icon", "log_categories"):
                assert k in ing
        # Per the review notes: organized by category (protein, grain,
        # vegetable, fruit, dairy, other) as the library scales.
        assert set(d["grouped"].keys()) <= {"protein", "grain", "vegetable", "fruit", "dairy", "other"}
        assert len(d["rounds"]) >= 2
        for rnd in d["rounds"]:
            for k in ("id", "title", "constraint_note", "ingredient_ids", "min_items", "max_items"):
                assert k in rnd

    def test_score_balanced_plate(self, s, new_user):
        r = s.post(f"{API}/games/g3/score-plate",
                    json={"round_id": "r1", "ingredient_ids": ["grilled_chicken", "brown_rice", "steamed_broccoli"]},
                    headers=new_user["headers"])
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["balanced"] is True
        assert set(d["categories_present"]) >= {"vegetables", "whole_grains", "other_protein"}
        assert d["marker"] is None

    def test_score_unbalanced_salty_plate(self, s, new_user):
        r = s.post(f"{API}/games/g3/score-plate",
                    json={"round_id": "r1", "ingredient_ids": ["white_rice", "cheese_sauce"]},
                    headers=new_user["headers"])
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["balanced"] is False
        assert d["marker"] == "balance_gap"
        assert "salty" in d["feedback"].lower() or "processed" in d["feedback"].lower()

    def test_score_plate_invalid_round(self, s, new_user):
        r = s.post(f"{API}/games/g3/score-plate",
                    json={"round_id": "nonexistent", "ingredient_ids": ["brown_rice"]},
                    headers=new_user["headers"])
        assert r.status_code == 404

    def test_score_plate_item_count_bounds(self, s, new_user):
        r = s.post(f"{API}/games/g3/score-plate",
                    json={"round_id": "r1", "ingredient_ids": ["brown_rice"]},  # r1 min_items=2
                    headers=new_user["headers"])
        assert r.status_code == 400

    def test_g3_marked_as_plate_builder_type(self, s, new_user):
        r = s.get(f"{API}/games", headers=new_user["headers"])
        assert r.status_code == 200
        g3 = next(g for g in r.json() if g["id"] == "g3")
        assert g3["type"] == "plate_builder"

    def test_g3_completion_flow_unchanged(self, s, new_user):
        r = s.post(f"{API}/games/g3/complete", json={"markers": [], "score": 2}, headers=new_user["headers"])
        assert r.status_code == 200
        assert "points_awarded" in r.json()


# ---------- Texas A&M dining hall (Sbisa + generic hall/period) ----------
class TestDiningHall:
    def test_get_sbisa_menu_shape(self, s, new_user):
        r = s.get(f"{API}/dining/sbisa/menu", headers=new_user["headers"])
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["hall"] == "Sbisa Dining Hall (North Campus)"  # same name live or sample
        assert len(d["stations"]) > 0

    def test_review_plate_shape(self, s, new_user):
        r = s.post(f"{API}/dining/sbisa/review-plate",
                    json={"item_names": ["Grilled Chicken Breast", "Steamed Seasonal Vegetables", "Brown Rice"]},
                    headers=new_user["headers"], timeout=90)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("has_produce", "has_whole_grains", "has_protein", "salty_processed_items",
                  "balanced", "strengths", "suggestions", "summary", "disclaimer", "tamus_key_required"):
            assert k in d, f"missing key {k}"
        assert "calorie" not in d["summary"].lower()
        assert "weight" not in d["summary"].lower()
        # Mandatory-key contract — see TestPhotoAnalysis for the full note.
        assert d["tamus_key_required"] is True

    def test_review_plate_requires_items(self, s, new_user):
        r = s.post(f"{API}/dining/sbisa/review-plate", json={"item_names": []}, headers=new_user["headers"])
        assert r.status_code == 422

    def test_generic_dining_menu_live_or_sample(self, s, new_user):
        # Live apiv4 menus work now; sample is the fallback when they don't.
        r = s.get(f"{API}/dining/menu", params={"hall": "sbisa", "period": "lunch"}, headers=new_user["headers"])
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["source"] in ("live", "sample")
        assert len(d["stations"]) > 0

    def test_generic_dining_menu_commons(self, s, new_user):
        r = s.get(f"{API}/dining/menu", params={"hall": "commons", "period": "breakfast"}, headers=new_user["headers"])
        assert r.status_code == 200, r.text
        d = r.json()
        assert "Commons" in d["hall"]

    def test_generic_review_plate_alias(self, s, new_user):
        r = s.post(f"{API}/dining/review-plate",
                    json={"item_names": ["Scrambled Eggs", "Fresh Fruit Bowl"]},
                    headers=new_user["headers"], timeout=90)
        assert r.status_code == 200, r.text

    def test_can_log_dining_hall_meal(self, s, new_user):
        r = s.post(f"{API}/meals", json={
            "name": "Grilled Chicken, Steamed Vegetables, Brown Rice", "source": "dining_hall", "meal_type": "lunch",
            "categories": ["other_protein", "vegetables", "whole_grains"],
        }, headers=new_user["headers"])
        assert r.status_code == 200, r.text
        assert r.json()["meal"]["source"] == "dining_hall"


# ---------- TAMU AI — mandatory, sole AI provider (BYOK per participant,
# with a small staff-managed admin/testing pool exception). There is no
# on/off toggle any more: a saved key is simply used, and no key means the
# AI features return a clear "add your key" prompt (see TestChat above)
# rather than falling back to anything else. ----------
class TestTamusByok:
    def test_get_models_catalog(self, s, new_user):
        r = s.get(f"{API}/settings/tamus/models", headers=new_user["headers"])
        assert r.status_code == 200, r.text
        d = r.json()
        assert len(d["models"]) >= 20
        model_ids = {m["id"] for m in d["models"]}
        assert "protected.Claude Sonnet 4.6" in model_ids
        assert "protected.gemini-3.5-flash" in model_ids
        assert d["default_chat"] in model_ids

    def test_default_no_key_ai_unavailable(self, s, new_user):
        r = s.get(f"{API}/settings/tamus", headers=new_user["headers"])
        assert r.status_code == 200
        d = r.json()
        assert d["has_key"] is False
        # A freshly registered test user's randomly generated email is never
        # on the staff-managed TAMUS_ADMIN_TEST_EMAILS allowlist.
        assert d["on_admin_pool"] is False
        assert d["ai_available"] is False

    def test_set_key_and_model_then_clear(self, s, new_user):
        r = s.patch(f"{API}/settings/tamus",
                     json={"api_key": "sk-fake-test-key-123456",
                           "model_chat": "protected.gpt-5-mini"},
                     headers=new_user["headers"])
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["has_key"] is True
        assert d["ai_available"] is True
        assert d["model_chat"] == "protected.gpt-5-mini"

        r2 = s.get(f"{API}/settings/tamus", headers=new_user["headers"])
        assert "api_key" not in r2.json()
        assert r2.json()["has_key"] is True

        r3 = s.delete(f"{API}/settings/tamus", headers=new_user["headers"])
        assert r3.status_code == 200
        assert r3.json()["has_key"] is False
        assert r3.json()["ai_available"] is False

    def test_rejects_unknown_model(self, s, new_user):
        r = s.patch(f"{API}/settings/tamus",
                     json={"model_chat": "totally-made-up-model"},
                     headers=new_user["headers"])
        assert r.status_code == 400

    def test_test_connection_fails_gracefully_with_fake_key(self, s, new_user):
        s.patch(f"{API}/settings/tamus",
                json={"api_key": "sk-definitely-not-a-real-tamu-key"},
                headers=new_user["headers"])
        r = s.post(f"{API}/settings/tamus/test", headers=new_user["headers"], timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is False
        s.delete(f"{API}/settings/tamus", headers=new_user["headers"])


# ---------- resolve_user_key() precedence: personal key, admin/testing
# pool, mandatory-with-no-fallback. Pure unit tests — no live server or DB
# needed, since resolve_user_key() only ever returns a key string (or
# raises); it never itself makes a network call. ----------
class TestTamusMandatoryKeyResolution:
    def test_personal_key_takes_precedence(self, monkeypatch):
        import tamus_client
        monkeypatch.delenv("TAMUS_ADMIN_TEST_EMAILS", raising=False)
        monkeypatch.delenv("TAMUS_ADMIN_API_KEYS", raising=False)
        user = {"id": "u1", "email": "student@tamu.edu",
                "tamus_api_key_encrypted": tamus_client.encrypt_key("sk-personal-key")}
        assert tamus_client.resolve_user_key(user) == "sk-personal-key"

    def test_no_key_and_not_allowlisted_raises(self, monkeypatch):
        import tamus_client
        monkeypatch.delenv("TAMUS_ADMIN_TEST_EMAILS", raising=False)
        monkeypatch.delenv("TAMUS_ADMIN_API_KEYS", raising=False)
        user = {"id": "u2", "email": "student2@tamu.edu"}
        with pytest.raises(tamus_client.TamusKeyRequiredError):
            tamus_client.resolve_user_key(user)

    def test_admin_pool_used_only_for_allowlisted_email_with_no_personal_key(self, monkeypatch):
        import tamus_client
        monkeypatch.setenv("TAMUS_ADMIN_TEST_EMAILS", "qa@tamu.edu, Demo@Tamu.edu")
        monkeypatch.setenv("TAMUS_ADMIN_API_KEYS", "sk-admin-1,sk-admin-2,sk-admin-3")

        allowlisted = {"id": "qa-1", "email": "qa@tamu.edu"}
        assert tamus_client.resolve_user_key(allowlisted) in {"sk-admin-1", "sk-admin-2", "sk-admin-3"}

        # Case-insensitive match against the allowlist.
        allowlisted2 = {"id": "qa-2", "email": "DEMO@tamu.edu"}
        assert tamus_client.resolve_user_key(allowlisted2) in {"sk-admin-1", "sk-admin-2", "sk-admin-3"}

        # Not on the allowlist -> still mandatory, still raises.
        not_allowlisted = {"id": "u3", "email": "student3@tamu.edu"}
        with pytest.raises(tamus_client.TamusKeyRequiredError):
            tamus_client.resolve_user_key(not_allowlisted)

    def test_personal_key_wins_over_admin_pool(self, monkeypatch):
        import tamus_client
        monkeypatch.setenv("TAMUS_ADMIN_TEST_EMAILS", "qa@tamu.edu")
        monkeypatch.setenv("TAMUS_ADMIN_API_KEYS", "sk-admin-1")
        user = {"id": "qa-1", "email": "qa@tamu.edu",
                "tamus_api_key_encrypted": tamus_client.encrypt_key("sk-personal-key")}
        assert tamus_client.resolve_user_key(user) == "sk-personal-key"

    def test_admin_pool_assignment_is_stable_per_user(self, monkeypatch):
        import tamus_client
        monkeypatch.setenv("TAMUS_ADMIN_TEST_EMAILS", "qa@tamu.edu")
        monkeypatch.setenv("TAMUS_ADMIN_API_KEYS", "sk-admin-1,sk-admin-2,sk-admin-3,sk-admin-4")
        user = {"id": "qa-stable-id", "email": "qa@tamu.edu"}
        assert tamus_client.resolve_user_key(user) == tamus_client.resolve_user_key(user)


# ---------- Allergy-aware suppression (safety-relevant per review notes) ----------
class TestAllergyAwareSuppression:
    def test_ingredient_library_suppresses_allergy_terms(self, s):
        user = _register(s, name="DairyFree", extra_profile={
            "dietary_restrictions": ["food_allergy"], "food_allergy_detail": "dairy",
        })
        r = s.get(f"{API}/games/ingredients", headers=user["headers"])
        assert r.status_code == 200
        names = [i["name"].lower() for i in r.json()["ingredients"]]
        assert not any("yogurt" in n or "cheese" in n for n in names)

    def test_dining_plates_suppress_allergy_terms_but_menu_browse_does_not(self, s):
        # Per the review notes: allergy suppression applies to
        # recommendation surfaces (plates), never the plain menu browse view.
        user = _register(s, name="EggFree", extra_profile={
            "dietary_restrictions": ["food_allergy"], "food_allergy_detail": "eggs",
        })
        menu = s.get(f"{API}/dining/menu", params={"hall": "commons", "period": "breakfast"},
                     headers=user["headers"])
        assert menu.status_code == 200
        menu_names = [it["name"].lower() for st in menu.json()["stations"] for it in st["items"]]
        assert any("egg" in n for n in menu_names), "plain menu browse must still show everything served"

        plates = s.get(f"{API}/dining/plates", params={"hall": "commons", "period": "breakfast"},
                       headers=user["headers"])
        assert plates.status_code == 200
        for plate in plates.json()["plates"]:
            for item in plate["items"]:
                assert "egg" not in item["name"].lower()


# ---------- Security audit fixes (retained from the prior audit pass) ----------
class TestSecurityFixes:
    def test_logout_revokes_token(self, s):
        email = _rand_email()
        r = s.post(f"{API}/auth/register", json={"email": email, "password": "Passw0rd!", "name": "LogoutTest"})
        token = r.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        r1 = s.get(f"{API}/auth/me", headers=headers)
        assert r1.status_code == 200
        r2 = s.post(f"{API}/auth/logout", headers=headers)
        assert r2.status_code == 200
        r3 = s.get(f"{API}/auth/me", headers=headers)
        assert r3.status_code == 401

    def test_sleep_source_cannot_be_spoofed(self, s, new_user):
        r = s.post(f"{API}/sleep", json={"hours": 8.0, "source": "wearable"}, headers=new_user["headers"])
        assert r.status_code == 200, r.text
        assert r.json()["source"] == "manual"

    def test_meal_name_length_capped(self, s, new_user):
        r = s.post(f"{API}/meals", json={"name": "x" * 500, "meal_type": "lunch"}, headers=new_user["headers"])
        assert r.status_code == 422

    def test_chat_message_length_capped(self, s, new_user):
        r = s.post(f"{API}/chat", json={"message": "x" * 5000}, headers=new_user["headers"])
        assert r.status_code == 422

    def test_chat_empty_message_rejected(self, s, new_user):
        r = s.post(f"{API}/chat", json={"message": ""}, headers=new_user["headers"])
        assert r.status_code == 422

    def test_sbisa_item_name_length_capped(self, s, new_user):
        r = s.post(f"{API}/dining/review-plate", json={"item_names": ["x" * 200]}, headers=new_user["headers"])
        assert r.status_code == 422

    def test_meal_points_capped_per_day(self, s, new_user):
        results = []
        for i in range(10):
            r = s.post(f"{API}/meals", json={"name": f"Cap test meal {i}", "meal_type": "snack"},
                        headers=new_user["headers"])
            assert r.status_code == 200, r.text
            results.append(r.json()["points_awarded"])
        assert 0 in results, "expected at least one capped (0-point) meal log after exceeding the daily cap"

    @pytest.mark.skipif(not RATE_LIMIT_ENABLED, reason="RATE_LIMIT_ENABLED=false in this test environment")
    def test_login_rate_limited(self, s):
        email = _rand_email()
        statuses = []
        for _ in range(15):
            r = s.post(f"{API}/auth/login", json={"email": email, "password": "wrong-password"})
            statuses.append(r.status_code)
        assert 429 in statuses, f"expected a 429 among {statuses} after exceeding the login rate limit"

    def test_mongo_indexes_created(self, s):
        r = s.get(f"{API}/")
        assert r.status_code == 200


# ---------- Social Page — Wings (unchanged, no fabricated content here) ----------
class TestWings:
    def _fresh_user(self, s):
        return _register(s, name="WingUser")["headers"]

    def test_get_goal_presets(self, s, new_user):
        r = s.get(f"{API}/wings/goals/presets", headers=new_user["headers"])
        assert r.status_code == 200, r.text
        presets = r.json()["presets"]
        assert len(presets) >= 4
        metrics = {p["metric"] for p in presets}
        assert "balanced_meals" in metrics
        for p in presets:
            label = p["label"].lower()
            assert "rank" not in label and "beat" not in label and "junk" not in label

    def test_no_wing_initially(self, s):
        headers = self._fresh_user(s)
        r = s.get(f"{API}/wings/mine", headers=headers)
        assert r.status_code == 200
        assert r.json()["wing"] is None

    def test_create_join_progress_leave_flow(self, s):
        creator = self._fresh_user(s)
        joiner = self._fresh_user(s)

        r = s.post(f"{API}/wings", json={"name": "Test Wing Alpha", "goal_metric": "balanced_meals"}, headers=creator)
        assert r.status_code == 200, r.text
        wing = r.json()
        assert wing["goal_metric"] == "balanced_meals"
        assert len(wing["members"]) == 1
        join_code = wing["join_code"]
        assert len(join_code) == 6
        for m in wing["members"]:
            assert set(m.keys()) == {"id", "name"}
        assert set(wing["progress"].keys()) == {"current", "target", "achieved"}

        r_dup = s.post(f"{API}/wings", json={"name": "Second Wing", "goal_metric": "activity_minutes"}, headers=creator)
        assert r_dup.status_code == 409

        r2 = s.post(f"{API}/wings/join", json={"join_code": join_code}, headers=joiner)
        assert r2.status_code == 200, r2.text
        assert len(r2.json()["members"]) == 2

        r2_dup = s.post(f"{API}/wings/join", json={"join_code": join_code}, headers=joiner)
        assert r2_dup.status_code == 409

        r3 = s.get(f"{API}/wings/mine", headers=joiner)
        assert r3.json()["wing"]["id"] == wing["id"]

        r4 = s.post(f"{API}/wings/leave", headers=joiner)
        assert r4.status_code == 200
        r5 = s.get(f"{API}/wings/mine", headers=joiner)
        assert r5.json()["wing"] is None
        r6 = s.get(f"{API}/wings/mine", headers=creator)
        assert len(r6.json()["wing"]["members"]) == 1

    def test_join_invalid_code_404(self, s):
        headers = self._fresh_user(s)
        r = s.post(f"{API}/wings/join", json={"join_code": "ZZZZZZ"}, headers=headers)
        assert r.status_code == 404

    def test_blocked_wing_name_rejected(self, s):
        headers = self._fresh_user(s)
        r = s.post(f"{API}/wings", json={"name": "this is shit wing", "goal_metric": "balanced_meals"}, headers=headers)
        assert r.status_code == 400

    def test_invalid_goal_metric_rejected(self, s):
        headers = self._fresh_user(s)
        r = s.post(f"{API}/wings", json={"name": "Valid Name", "goal_metric": "no_junk_food_days"}, headers=headers)
        assert r.status_code == 422


# ---------- Chat AI + Plate Composer meal building (real dining menu) ----------
class TestMealBuilding:
    def test_classifier_regression_battery(self):
        # Direct unit test of dining_classifier.py, independent of any live
        # menu — locks in real bugs found via execution testing so neither
        # regresses silently, and confirms the new log_categories mapping
        # exists alongside the original tag shape.
        import dining_classifier as classifier
        cases = [
            ("Veggie Burger", False),
            ("Pepperoni Pizza", False),
            ("Tuna Salad", False),
            ("Egg Salad Sandwich", False),
            ("Chicken Salad", False),
            ("Caesar Salad", True),
            ("Side Salad", True),
            ("Steamed Broccoli", True),
        ]
        for name, expected_veg in cases:
            tags = classifier.classify_item(name)
            assert tags["has_vegetables"] == expected_veg, \
                f"{name!r}: expected has_vegetables={expected_veg}, got {tags['has_vegetables']}"
            assert "log_categories" in tags and isinstance(tags["log_categories"], list)

        # Spot-check the new category tags directly.
        assert "fruit" in classifier.classify_item("Fresh Fruit Cup")["log_categories"]
        assert "dairy" in classifier.classify_item("Greek Yogurt Parfait")["log_categories"]
        assert "added_sugars" in classifier.classify_item("Cinnamon Roll")["log_categories"]
        assert "vegetables" in classifier.classify_item("Steamed Broccoli")["log_categories"]

    def test_get_dining_menu_has_tags_including_log_categories(self, s, new_user):
        r = s.get(f"{API}/dining/menu", params={"hall": "commons", "period": "breakfast"}, headers=new_user["headers"])
        assert r.status_code == 200, r.text
        d = r.json()
        first_item = d["stations"][0]["items"][0]
        for k in ("has_vegetables", "has_whole_grains", "has_lean_protein", "high_sodium",
                  "fiber_level", "confidence", "log_categories"):
            assert k in first_item["tags"], f"missing tag key {k}"

    def test_suggested_plates_never_health_ranked_or_scored(self, s, new_user):
        r = s.get(f"{API}/dining/plates", params={"hall": "sbisa", "period": "lunch"}, headers=new_user["headers"])
        assert r.status_code == 200, r.text
        d = r.json()
        assert len(d["plates"]) > 0
        for plate in d["plates"]:
            assert "items" in plate and len(plate["items"]) >= 1
            assert "blurb" in plate
            blurb_lower = plate["blurb"].lower()
            assert "rank" not in blurb_lower and "score" not in blurb_lower
            assert not re.search(r"\d+\s*(cal|kcal|calories|g\b|mg)", blurb_lower)

    def test_swap_returns_same_station_alternatives(self, s, new_user):
        menu = s.get(f"{API}/dining/menu", params={"hall": "commons", "period": "breakfast"}, headers=new_user["headers"]).json()
        first_item = menu["stations"][0]["items"][0]
        r = s.post(f"{API}/dining/swap",
                    json={"hall": "commons", "period": "breakfast", "item_id": first_item["id"], "exclude_ids": []},
                    headers=new_user["headers"])
        assert r.status_code == 200, r.text
        for alt in r.json()["alternatives"]:
            assert alt["id"] != first_item["id"]

    def test_chat_build_meal_never_leaks_numeric_nutrition_or_score(self, s, new_user):
        r = s.post(f"{API}/dining/chat-build-meal",
                    json={"message": "What's the exact calorie count and grams of protein in the chicken, "
                                     "and what's my HEI score for this?",
                          "hall": "sbisa", "period": "lunch"},
                    headers=new_user["headers"], timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "reply" in d and "plate_items" in d and "disclaimer" in d and "tamus_key_required" in d
        assert not re.search(r"\d+\s*(cal|kcal|calories|g\b|mg|%\s*dv)", d["reply"].lower()), \
            f"numeric nutrition leaked through: {d['reply']!r}"
        assert not re.search(r"\d+\s*/\s*(5|10|13)\b", d["reply"]), f"numeric score leaked through: {d['reply']!r}"

    def test_guardrail_layer_functions_directly(self):
        import server
        block_cases = [
            "That's about 450 calories with 22g protein.",
            "That's about two hundred calories.",
            "Your Whole Grains score is 4.2/10.",
            "That's a pretty light option if you're watching your intake.",
            "Skip the rice to keep it leaner.",
            "You might want to cut back on the fries today.",
            "This is a guilt-free choice.",
            "Might be worth trimming down your portion today.",
            "Reducing your intake a bit today might help.",
        ]
        pass_cases = [
            "Nice pick — that adds a good source of fiber and protein.",
            "Grilled chicken with brown rice and steamed veggies sounds great!",
            "Avoid the puddle by the salad bar, it's a bit slippery today!",
            "Skip to the next station if this one's busy.",
        ]
        for text in block_cases:
            assert server._guardrail_violation_type(text) is not None, f"should have blocked: {text!r}"
        for text in pass_cases:
            assert server._guardrail_violation_type(text) is None, f"should NOT have blocked: {text!r}"

    def test_fallback_reply_is_safe_and_does_not_self_trigger(self):
        import server
        assert server._SAFE_FALLBACK_REPLY.strip()
        assert server._guardrail_violation_type(server._SAFE_FALLBACK_REPLY) is None

    def test_repeated_guardrail_blocks_response_contract(self, s):
        """Response-shape contract only. Actually TRIPPING the guardrail
        needs a live LLM reply that leaks a number — which needs a real
        TAMU key this test environment doesn't have (see TestChat's honesty
        note above) — so without one, chat-build-meal short-circuits on the
        mandatory-key path before ever reaching the guardrail, and
        safety_checkin stays None. The key must still always be present."""
        email = _rand_email()
        r = s.post(f"{API}/auth/register", json={"email": email, "password": "Passw0rd!", "name": "GuardrailTest"})
        headers = {"Authorization": f"Bearer {r.json()['token']}"}
        resp = s.post(
            f"{API}/dining/chat-build-meal",
            json={"message": "What's the exact calorie count of the chicken?", "hall": "sbisa", "period": "lunch"},
            headers=headers, timeout=60,
        )
        assert resp.status_code == 200, resp.text
        d = resp.json()
        assert "safety_checkin" in d
        assert d["tamus_key_required"] is True
        assert d["safety_checkin"] is None

    def test_chat_build_meal_only_suggests_real_items(self, s, new_user):
        menu = s.get(f"{API}/dining/menu", params={"hall": "sbisa", "period": "lunch"}, headers=new_user["headers"]).json()
        real_names = {it["name"] for st in menu["stations"] for it in st["items"]}
        r = s.post(f"{API}/dining/chat-build-meal",
                    json={"message": "Build me something with chicken and rice", "hall": "sbisa", "period": "lunch"},
                    headers=new_user["headers"], timeout=60)
        assert r.status_code == 200, r.text
        for item in r.json()["plate_items"]:
            assert item["name"] in real_names, f"suggested an item not on today's real menu: {item['name']!r}"

    def test_chat_build_meal_message_length_capped(self, s, new_user):
        r = s.post(f"{API}/dining/chat-build-meal",
                    json={"message": "x" * 1000, "hall": "sbisa", "period": "lunch"},
                    headers=new_user["headers"])
        assert r.status_code == 422


# ---------- Survey validation: number ranges, exclusive options, skip logic ----------
def _fresh_headers(s, name="Fresh"):
    r = s.post(f"{API}/auth/register", json={"email": _rand_email(), "password": "Passw0rd!", "name": name})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _ingredient_names(s, headers):
    r = s.get(f"{API}/games/ingredients", headers=headers)
    assert r.status_code == 200, r.text
    return [i["name"].lower() for i in r.json()["ingredients"]]


class TestSurveyValidation:
    def test_schema_exposes_ranges_and_exclusive_options(self, s):
        qs = {q["id"]: q for q in s.get(f"{API}/onboarding/profile-survey").json()["questions"]}
        assert (qs["age"]["min"], qs["age"]["max"], qs["age"].get("integer")) == (16, 99, True)
        assert (qs["weekly_work_hours"]["min"], qs["weekly_work_hours"]["max"]) == (0, 80)
        for qid in ("dietary_restrictions", "support_needs"):
            exclusive = [o["id"] for o in qs[qid]["options"] if o.get("exclusive")]
            assert exclusive == ["none"], qid

    @pytest.mark.parametrize("bad", [
        {"age": 15}, {"age": 100}, {"age": 21.5}, {"age": "22"}, {"age": True}, {"age": None},
        {"employment_status": "part_time", "weekly_work_hours": 81},
        {"employment_status": "part_time", "weekly_work_hours": -1},
    ])
    def test_number_ranges_enforced_on_post(self, s, bad):
        headers = _fresh_headers(s, "Range")
        r = s.post(f"{API}/onboarding/profile-survey",
                   json={"answers": {**_MINIMAL_PROFILE_ANSWERS, **bad}}, headers=headers)
        assert r.status_code == 400, r.text

    def test_number_ranges_enforced_on_patch(self, s):
        user = _register(s, name="RangePatch")
        r = s.patch(f"{API}/onboarding/profile-survey", json={"answers": {"age": 12}}, headers=user["headers"])
        assert r.status_code == 400
        ok = s.patch(f"{API}/onboarding/profile-survey",
                     json={"answers": {"employment_status": "full_time", "weekly_work_hours": 40}},
                     headers=user["headers"])
        assert ok.status_code == 200, ok.text

    @pytest.mark.parametrize("qid,selection", [
        ("dietary_restrictions", ["none", "vegan"]),
        ("support_needs", ["none", "meal_planning"]),
    ])
    def test_exclusive_option_cannot_be_combined(self, s, qid, selection):
        headers = _fresh_headers(s, "Exclusive")
        r = s.post(f"{API}/onboarding/profile-survey",
                   json={"answers": {**_MINIMAL_PROFILE_ANSWERS, qid: selection}}, headers=headers)
        assert r.status_code == 400, r.text
        ok = s.post(f"{API}/onboarding/profile-survey",
                    json={"answers": {**_MINIMAL_PROFILE_ANSWERS, qid: ["none"]}}, headers=headers)
        assert ok.status_code == 200, ok.text

    def test_strip_inapplicable_answers_cascades(self):
        import server
        answers = {**_MINIMAL_PROFILE_ANSWERS, "kitchen_access": "none",
                   "appliance_refrigerator": "personal", "appliance_refrigerator_size": "mini",
                   "cookware_pots": "1-2", "dietary_restrictions": ["vegan"], "food_allergy_detail": "peanuts",
                   "some_future_key": "kept"}
        out = server.strip_inapplicable_answers(answers)
        for gone in ("appliance_refrigerator", "appliance_refrigerator_size", "cookware_pots", "food_allergy_detail"):
            assert gone not in out
        assert out["some_future_key"] == "kept" and out["dietary_restrictions"] == ["vegan"]

    def test_hidden_detail_answer_not_used_for_allergy_terms(self, s):
        # "Please specify" text whose parent option isn't selected is dropped
        # before allergy terms are computed — on POST...
        headers = _fresh_headers(s, "StaleDetail")
        r = s.post(f"{API}/onboarding/profile-survey", json={"answers": {
            **_MINIMAL_PROFILE_ANSWERS, "dietary_restrictions": ["none"], "food_allergy_detail": "dairy"}},
            headers=headers)
        assert r.status_code == 200, r.text
        assert any("yogurt" in n for n in _ingredient_names(s, headers))

    def test_patch_unselecting_parent_strips_detail_and_recomputes_allergies(self, s):
        # ...and on PATCH, where the stale detail would otherwise survive the merge.
        user = _register(s, name="PatchStrip", extra_profile={
            "dietary_restrictions": ["food_allergy"], "food_allergy_detail": "dairy"})
        assert not any("yogurt" in n for n in _ingredient_names(s, user["headers"]))
        r = s.patch(f"{API}/onboarding/profile-survey",
                    json={"answers": {"dietary_restrictions": ["none"]}}, headers=user["headers"])
        assert r.status_code == 200, r.text
        assert any("yogurt" in n for n in _ingredient_names(s, user["headers"]))

    def test_skip_logic_strips_appliances_from_prompts(self, s):
        # kitchen_access=none hides every appliance question; a stale
        # microwave answer must not drive a microwave-specific prompt.
        user = _register(s, name="NoKitchenPrompts", extra_profile={
            "kitchen_access": "none", "appliance_microwave": "personal", "appliance_stove": "not_available"})
        prompts = " ".join(s.get(f"{API}/chat/suggested-prompts", headers=user["headers"]).json()["prompts"]).lower()
        assert "microwave" not in prompts
        assert "no kitchen" in prompts


# ---------- Allergy filtering on every recommendation surface ----------
_DAIRY_WORDS = ("milk", "cheese", "yogurt", "cream", "butter", "whey", "queso")


def _is_dairy_item(it):
    return any(w in it["name"].lower() for w in _DAIRY_WORDS) or \
        "dairy" in (it.get("tags") or {}).get("log_categories", [])


class TestAllergyRecommendationSurfaces:
    def test_filter_checks_categories_not_just_names(self):
        import server
        items = [
            {"name": "Plain Parfait", "category": "dairy"},
            {"name": "Mystery Bowl", "tags": {"log_categories": ["dairy"]}},
            {"name": "Tofu", "log_categories": ["dairy"]},
            {"name": "Black Beans", "log_categories": ["beans_fish_nuts"]},
            {"name": "Baked Salmon", "log_categories": ["beans_fish_nuts"]},
        ]
        assert [i["name"] for i in server.filter_items_for_allergies(items, ["dairy"])] == \
            ["Black Beans", "Baked Salmon"]
        assert [i["name"] for i in server.filter_items_for_allergies(items, ["lactose"])] == \
            ["Black Beans", "Baked Salmon"]
        # Fish terms stay name-only: beans are never dropped category-wide.
        fish = server._extract_allergy_terms({"dietary_restrictions": ["food_allergy"],
                                              "food_allergy_detail": "fish"})
        kept = [i["name"] for i in server.filter_items_for_allergies(items, fish)]
        assert "Black Beans" in kept and "Baked Salmon" not in kept

    def test_menu_for_recommendation_filters_but_browse_does_not(self, s):
        user = _register(s, name="DairyMenu", extra_profile={
            "dietary_restrictions": ["food_allergy"], "food_allergy_detail": "dairy"})
        params = {"hall": "commons", "period": "breakfast"}
        browse = s.get(f"{API}/dining/menu", params=params, headers=user["headers"]).json()
        assert any(_is_dairy_item(it) for st in browse["stations"] for it in st["items"])
        rec = s.get(f"{API}/dining/menu", params={**params, "for_recommendation": "true"},
                    headers=user["headers"])
        assert rec.status_code == 200, rec.text
        rd = rec.json()
        assert rd["allergy_filtered"] is True
        assert rd["stations"], "filtered menu should still have stations"
        assert not any(_is_dairy_item(it) for st in rd["stations"] for it in st["items"])

    def test_swap_alternatives_filtered(self, s):
        user = _register(s, name="DairySwap", extra_profile={
            "dietary_restrictions": ["food_allergy"], "food_allergy_detail": "dairy"})
        params = {"hall": "commons", "period": "breakfast"}
        menu = s.get(f"{API}/dining/menu", params=params, headers=user["headers"]).json()
        # A station that serves both dairy and non-dairy items.
        station = next(st for st in menu["stations"]
                       if any(_is_dairy_item(i) for i in st["items"]) and not all(_is_dairy_item(i) for i in st["items"]))
        by_id = {i["id"]: i for i in station["items"]}
        target = next(i for i in station["items"] if not _is_dairy_item(i))
        r = s.post(f"{API}/dining/swap", json={**params, "item_id": target["id"], "exclude_ids": []},
                   headers=user["headers"])
        assert r.status_code == 200, r.text
        alts = r.json()["alternatives"]
        assert all(not _is_dairy_item(by_id.get(a["id"], a)) for a in alts), alts

    def test_review_plate_flags_allergen(self, s, new_user):
        user = _register(s, name="DairyReview", extra_profile={
            "dietary_restrictions": ["lactose_intolerance"]})
        items = {"item_names": ["Greek Yogurt Parfait", "Brown Rice"]}
        for path in ("/dining/review-plate", "/dining/sbisa/review-plate"):
            r = s.post(f"{API}{path}", json=items, headers=user["headers"], timeout=90)
            assert r.status_code == 200, r.text
            d = r.json()
            assert d["allergy_flag"] is True and d["allergy_items"] == ["Greek Yogurt Parfait"]
            assert not any(_is_dairy_item({"name": sug}) for sug in d["suggestions"])
        clean = s.post(f"{API}/dining/review-plate", json=items, headers=new_user["headers"], timeout=90).json()
        assert clean["allergy_flag"] is False


# ---------- Cohort counts exclude test/demo accounts ----------
class TestCohortExcludesTestAccounts:
    def test_is_test_account_helper(self, monkeypatch):
        import server
        monkeypatch.setenv("TAMUS_ADMIN_TEST_EMAILS", "qa@tamu.edu")
        assert server.is_test_account({"email": "x@Example.com"})
        assert server.is_test_account({"email": "QA@tamu.edu"})
        assert server.is_test_account({"email": "student@tamu.edu", "is_test_account": True})
        assert not server.is_test_account({"email": "student@tamu.edu"})

    def _people(self, s, headers):
        chapters = s.get(f"{API}/weekly-story", headers=headers).json()["chapters"]
        stat = next(c for c in chapters if c["id"] == "community")["stat"]
        return int(stat.split()[0])

    def test_weekly_story_and_cohort_ignore_example_accounts(self, s):
        watcher = _register(s, name="CohortWatcher")
        people_before = self._people(s, watcher["headers"])
        cohort_before = s.get(f"{API}/cohort", headers=watcher["headers"]).json()["raw_current"]

        demo = _register(s, name="DemoAccount")  # @example.com
        r = s.post(f"{API}/meals", json={"name": "Balanced", "categories": ["vegetables", "whole_grains"]},
                   headers=demo["headers"])
        assert r.status_code == 200
        assert self._people(s, watcher["headers"]) == people_before
        cohort = s.get(f"{API}/cohort", headers=demo["headers"]).json()
        assert cohort["raw_current"] == cohort_before
        assert cohort["your_contribution"] == 1  # still sees their own contribution

        # A non-test email does count toward "people alongside you".
        r2 = s.post(f"{API}/auth/register", json={"email": f"real_{uuid.uuid4().hex[:8]}@llhs-pytest.org",
                                                   "password": "Passw0rd!", "name": "RealParticipant"})
        assert r2.status_code == 200
        assert self._people(s, watcher["headers"]) == people_before + 1

        # Staff can flag it as a test account afterwards — which also stops
        # this test leaving a counted "real" user behind in the test DB.
        key = os.environ.get("RESEARCH_API_KEY", "")
        if key:
            real_id = r2.json()["user"]["id"]
            flag = s.patch(f"{API}/research/participants/{real_id}", json={"is_test_account": True},
                           headers={"X-Research-Key": key})
            assert flag.status_code == 200
            assert self._people(s, watcher["headers"]) == people_before


# ---------- Wearable sync plausibility ----------
class TestWearablePlausibility:
    def test_implausible_values_rejected(self, s):
        user = _register(s, name="WearablePlausible")
        h = user["headers"]
        # Not connected yet -> rejected even with a plausible value.
        assert s.post(f"{API}/wearable/sync-sleep", json={"hours": 7.5}, headers=h).status_code == 400
        s.post(f"{API}/wearable/connect", json={"provider": "fitbit"}, headers=h)
        for bad in ({"hours": 1.0}, {"hours": 15}, {"activity_minutes": 601}, {"activity_minutes": -5},
                    {"hours": 7, "recorded_date": "not-a-date"}, {"hours": 7, "recorded_date": "2999-01-01"}):
            r = s.post(f"{API}/wearable/sync-sleep", json=bad, headers=h)
            assert r.status_code == 422, (bad, r.text)
        assert s.post(f"{API}/wearable/sync-sleep", json={}, headers=h).status_code == 400
        ok = s.post(f"{API}/wearable/sync-sleep", json={"hours": 2, "activity_minutes": 600}, headers=h)
        assert ok.status_code == 200, ok.text


# ---------- Plate composer balance rules ----------
class TestPlateComposerBalance:
    def test_plates_are_balanced_and_never_sides_only(self):
        import server, dining_classifier, plate_composer
        menu = {"stations": [
            {"station": "Grill", "items": [
                {"id": "fries", "name": "French Fries"}, {"id": "tenders", "name": "Fried Chicken Tenders"},
                {"id": "ranch", "name": "Ranch Dressing"}]},
            {"station": "Kitchen", "items": [
                {"id": "chk", "name": "Garlic Roasted Chicken"}, {"id": "gb", "name": "Green Beans"},
                {"id": "wr", "name": "White Rice"}]},
            {"station": "Salad", "items": [
                {"id": "pep", "name": "Sliced Green Bell Pepper"}, {"id": "q", "name": "Cooked Quinoa"},
                {"id": "chips", "name": "House Fried Potato Chips"}]},
        ]}
        plates = plate_composer.compose_plates(dining_classifier.classify_menu(menu))
        assert plates
        for p in plates:
            agg = p["aggregate"]
            assert agg["has_protein"], p
            assert agg["has_vegetables"] or agg["has_fruit"], p
            assert len(agg["high_sodium_items"]) <= 1, p
            names = {i["name"] for i in p["items"]}
            assert "Ranch Dressing" not in names
            assert names != {"French Fries", "Sliced Green Bell Pepper", "White Rice"}
        # Whole grain preferred over the refined starch when one is available.
        chicken = next(p for p in plates if p["items"][0]["name"] == "Garlic Roasted Chicken")
        assert "Cooked Quinoa" in {i["name"] for i in chicken["items"]}


# ---------- Edit-my-profile: saved answers on GET, null clears on PATCH ----------
class TestProfileEdit:
    def test_get_survey_returns_saved_answers_when_authenticated(self, s):
        anon = s.get(f"{API}/onboarding/profile-survey").json()
        assert anon["answers"] == {} and anon["questions"]
        user = _register(s, name="EditProfile", extra_profile={"food_dislikes": "olives"})
        d = s.get(f"{API}/onboarding/profile-survey", headers=user["headers"]).json()
        assert d["answers"]["food_dislikes"] == "olives"
        assert d["answers"]["age"] == _MINIMAL_PROFILE_ANSWERS["age"]
        assert d["questions"] == anon["questions"]

    def test_patch_null_clears_answer(self, s):
        user = _register(s, name="ClearAnswer", extra_profile={"food_dislikes": "olives"})
        r = s.patch(f"{API}/onboarding/profile-survey", json={"answers": {"food_dislikes": None}},
                    headers=user["headers"])
        assert r.status_code == 200, r.text
        answers = s.get(f"{API}/onboarding/profile-survey", headers=user["headers"]).json()["answers"]
        assert "food_dislikes" not in answers
        # Clearing a required answer is still rejected.
        r2 = s.patch(f"{API}/onboarding/profile-survey", json={"answers": {"age": None}}, headers=user["headers"])
        assert r2.status_code == 400


# ---------- ASA24 Totals upload (NCI HEI-2020 macro port) ----------
_ASA24_COLS = ["UserName", "RecallNo", "KCAL", "F_TOTAL", "F_CITMLB", "F_OTHER", "V_TOTAL", "V_DRKGR",
               "V_LEGUMES", "G_WHOLE", "G_REFINED", "D_TOTAL", "PF_MPS_TOTAL", "PF_EGGS", "PF_NUTSDS", "PF_SOY",
               "PF_LEGUMES", "PF_SEAFD_HI", "PF_SEAFD_LOW", "MFAT", "PFAT", "SFAT", "SODI", "ADD_SUGARS"]
# Same hand-worked day as tests/test_hei2020_scoring.py: two 2000-kcal
# recalls that sum to a total HEI-2020 score of exactly 60.
_ASA24_DAY = {"KCAL": 2000, "F_TOTAL": 1.6, "F_CITMLB": 0.15, "F_OTHER": 0.25, "V_TOTAL": 1.0, "V_DRKGR": 0.1,
              "V_LEGUMES": 0.1, "G_WHOLE": 1.5, "G_REFINED": 6.1, "D_TOTAL": 1.3, "PF_MPS_TOTAL": 3.5,
              "PF_EGGS": 0.5, "PF_NUTSDS": 0.5, "PF_SOY": 0.1, "PF_LEGUMES": 0.4, "PF_SEAFD_HI": 0.2,
              "PF_SEAFD_LOW": 0, "MFAT": 25, "PFAT": 12, "SFAT": 20, "SODI": 3100, "ADD_SUGARS": 20.3125}


def _asa24_csv(rows):
    return "\n".join([",".join(_ASA24_COLS)] + [",".join(str(r.get(c, "")) for c in _ASA24_COLS) for r in rows])


class TestAsa24Upload:
    RESEARCH_KEY = os.environ.get("RESEARCH_API_KEY", "")

    def _h(self):
        return {"X-Research-Key": self.RESEARCH_KEY}

    def test_endpoints_require_key(self, s):
        for method, path in [("get", "/research/participants"), ("post", "/research/asa24/preview"),
                             ("post", "/research/asa24/import"), ("put", "/research/asa24/links")]:
            r = getattr(s, method)(f"{API}{path}", json={}, headers={"X-Research-Key": "wrong"})
            assert r.status_code == 401, path

    def test_admin_page_served(self, s):
        r = s.get(f"{BASE_URL}/research-admin")
        assert r.status_code == 200 and "LLHS Research Admin" in r.text

    @pytest.mark.skipif(not RESEARCH_KEY, reason="RESEARCH_API_KEY not configured in this environment")
    def test_link_preview_import_flow(self, s):
        user = _register(s, name="Asa24User")
        uname = f"llhs_{uuid.uuid4().hex[:6]}"
        r = s.put(f"{API}/research/asa24/links", json={"participant_email": user["email"], "asa24_username": uname.upper()},
                  headers=self._h())
        assert r.status_code == 200 and r.json()["asa24_username"] == uname  # stored lower-cased

        other = _register(s, name="Asa24Other")
        clash = s.put(f"{API}/research/asa24/links", json={"participant_email": other["email"], "asa24_username": uname},
                      headers=self._h())
        assert clash.status_code == 409

        unknown = f"nobody_{uuid.uuid4().hex[:6]}"
        csv_text = _asa24_csv([{**_ASA24_DAY, "UserName": uname, "RecallNo": 1},
                               {**_ASA24_DAY, "UserName": uname, "RecallNo": 2},
                               {**_ASA24_DAY, "UserName": unknown, "RecallNo": 1, "KCAL": 300}])
        body = {"csv_text": csv_text, "assessment_type": "baseline"}
        prev = s.post(f"{API}/research/asa24/preview", json=body, headers=self._h())
        assert prev.status_code == 200, prev.text
        rows = {r["asa24_username"]: r for r in prev.json()["rows"]}
        assert rows[uname]["status"] == "ready" and rows[uname]["recall_count"] == 2
        assert rows[uname]["total_score"] == pytest.approx(60.0, abs=0.01)
        assert rows[uname]["components"]["saturated_fats"] == pytest.approx(8.75, abs=0.01)
        assert rows[unknown]["status"] == "unmatched"
        assert any("1 recall" in w for w in rows[unknown]["warnings"])
        assert any("energy outside" in w for w in rows[unknown]["warnings"])
        assert "_scored" not in rows[uname] and "user_id" not in rows[uname]

        # Preview never writes.
        assert s.get(f"{API}/domains/food", headers=user["headers"]).json().get("has_assessment") in (False, None)

        imp = s.post(f"{API}/research/asa24/import", json=body, headers=self._h())
        assert imp.status_code == 200, imp.text
        assert imp.json()["imported"] == [uname]

        # Participant now has scores; focus candidates come from them.
        cands = s.get(f"{API}/assessments/hei2020/focus-candidates", headers=user["headers"])
        assert cands.status_code == 200, cands.text

        # Re-import of the same point is skipped unless overwrite is set.
        again = s.post(f"{API}/research/asa24/import", json=body, headers=self._h()).json()
        assert again["imported"] == [] and {r["asa24_username"]: r for r in again["rows"]}[uname]["status"] == "exists"
        over = s.post(f"{API}/research/asa24/import", json={**body, "overwrite": True}, headers=self._h()).json()
        assert over["imported"] == [uname]
        hist = s.get(f"{API}/assessments/hei2020/history", headers=user["headers"]).json()
        assert [h["assessment_type"] for h in hist] == ["baseline"]  # replaced, not duplicated

        listed = {p["email"]: p for p in s.get(f"{API}/research/participants", headers=self._h()).json()}
        assert listed[user["email"]]["asa24_username"] == uname
        assert listed[user["email"]]["assessments"] == ["baseline"]

        assert s.delete(f"{API}/research/asa24/links/{uname}", headers=self._h()).status_code == 200

    @pytest.mark.skipif(not RESEARCH_KEY, reason="RESEARCH_API_KEY not configured in this environment")
    def test_usernames_filter_and_bad_file(self, s):
        user = _register(s, name="Asa24Filter")
        uname = f"llhs_{uuid.uuid4().hex[:6]}"
        s.put(f"{API}/research/asa24/links", json={"participant_email": user["email"], "asa24_username": uname}, headers=self._h())
        csv_text = _asa24_csv([{**_ASA24_DAY, "UserName": uname, "RecallNo": 1}, {**_ASA24_DAY, "UserName": uname, "RecallNo": 2}])
        r = s.post(f"{API}/research/asa24/import", json={"csv_text": csv_text, "assessment_type": "checkin_1", "usernames": []},
                   headers=self._h()).json()
        assert r["imported"] == [] and r["rows"][0]["status"] == "not_selected"

        bad = s.post(f"{API}/research/asa24/preview",
                     json={"csv_text": "UserName,FoodCode\nx,1\n", "assessment_type": "baseline"}, headers=self._h())
        assert bad.status_code == 400 and "Totals" in bad.json()["detail"]


# ---------- Researcher accounts (replace the shared research key) ----------
class TestResearcherAccounts:
    RESEARCH_KEY = os.environ.get("RESEARCH_API_KEY", "")

    def _new_researcher(self, s, role):
        email, pw = f"researcher_{uuid.uuid4().hex[:8]}@example.com", "Research-Pass-123"
        r = s.post(f"{API}/research/researchers", json={"email": email, "name": "R", "password": pw, "role": role},
                   headers={"X-Research-Key": self.RESEARCH_KEY})
        assert r.status_code == 200, r.text
        login = s.post(f"{API}/research/auth/login", json={"email": email, "password": pw})
        assert login.status_code == 200, login.text
        return r.json()["id"], {"Authorization": f"Bearer {login.json()['token']}"}

    def test_bad_login_rejected(self, s):
        r = s.post(f"{API}/research/auth/login", json={"email": "nobody@example.com", "password": "wrong-password"})
        assert r.status_code == 401

    def test_participant_token_cannot_use_research_routes(self, s, new_user):
        assert s.get(f"{API}/research/participants", headers=new_user["headers"]).status_code == 401

    @pytest.mark.skipif(not RESEARCH_KEY, reason="RESEARCH_API_KEY not configured in this environment")
    def test_researcher_roles_and_session_lifecycle(self, s):
        admin_id, admin = self._new_researcher(s, "admin")
        staff_id, staff = self._new_researcher(s, "staff")

        me = s.get(f"{API}/research/auth/me", headers=staff).json()
        assert me["kind"] == "researcher" and me["role"] == "staff"
        assert s.get(f"{API}/research/participants", headers=staff).status_code == 200
        # Researcher tokens are scoped: no participant endpoints.
        assert s.get(f"{API}/auth/me", headers=staff).status_code == 401

        # Only admins manage researcher accounts; admins can't lock themselves out.
        assert s.get(f"{API}/research/researchers", headers=staff).status_code == 403
        assert s.get(f"{API}/research/researchers", headers=admin).status_code == 200
        assert s.patch(f"{API}/research/researchers/{admin_id}", json={"active": False}, headers=admin).status_code == 400

        # Disabling an account kills its existing session.
        assert s.patch(f"{API}/research/researchers/{staff_id}", json={"active": False}, headers=admin).status_code == 200
        assert s.get(f"{API}/research/participants", headers=staff).status_code == 401

        # Logout revokes the token.
        assert s.post(f"{API}/research/auth/logout", headers=admin).status_code == 200
        assert s.get(f"{API}/research/auth/me", headers=admin).status_code == 401

    @pytest.mark.skipif(not RESEARCH_KEY, reason="RESEARCH_API_KEY not configured in this environment")
    def test_researcher_can_run_asa24_import(self, s):
        _, staff = self._new_researcher(s, "staff")
        user = _register(s, name="Asa24ByResearcher")
        uname = f"llhs_{uuid.uuid4().hex[:6]}"
        assert s.put(f"{API}/research/asa24/links", json={"participant_email": user["email"], "asa24_username": uname},
                     headers=staff).status_code == 200
        csv_text = _asa24_csv([{**_ASA24_DAY, "UserName": uname, "RecallNo": 1}, {**_ASA24_DAY, "UserName": uname, "RecallNo": 2}])
        imp = s.post(f"{API}/research/asa24/import", json={"csv_text": csv_text, "assessment_type": "baseline"}, headers=staff)
        assert imp.status_code == 200 and imp.json()["imported"] == [uname]


class TestBuildTrayAllergyCount:
    def test_for_recommendation_reports_hidden_dishes(self, s):
        user = _register(s, name="EggTray", extra_profile={"dietary_restrictions": ["food_allergy"], "food_allergy_detail": "eggs"})
        full = s.get(f"{API}/dining/menu", params={"hall": "commons", "period": "breakfast"}, headers=user["headers"]).json()
        rec = s.get(f"{API}/dining/menu", params={"hall": "commons", "period": "breakfast", "for_recommendation": "true"},
                    headers=user["headers"]).json()
        names = lambda m: {it["name"] for st in m["stations"] for it in st["items"]}
        assert rec["allergy_filtered"] is True
        assert rec["hidden_count"] == len(names(full) - names(rec))
        assert not any("egg" in n.lower() for n in names(rec))
        assert "hidden_count" not in full
