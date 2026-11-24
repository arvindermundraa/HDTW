"""Unit tests for pure safety helpers in server.py — no running server, no
TAMU key, no database calls (importing server only builds a lazy Motor
client). Covers the paths HTTP tests can't reach because test accounts
have no TAMU key, so the model never answers:
    python -m pytest tests/test_server_helpers.py -n 0"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "llhs_unit_unused")
import server  # noqa: E402


def test_review_suggestions_drop_allergens_and_junk():
    terms = server._extract_allergy_terms({"dietary_restrictions": ["food_allergy"], "food_allergy_detail": "peanuts, dairy"})
    raw = ["Add a side of roasted broccoli", "Try peanut butter on toast", "Top it with shredded cheese",
           "Swap in a glass of milk", 42, "", None, "Add brown rice for a whole grain"]
    assert server.safe_review_suggestions(raw, terms) == [
        "Add a side of roasted broccoli", "Add brown rice for a whole grain"]


def test_review_suggestions_handle_non_list_and_no_allergies():
    assert server.safe_review_suggestions("not a list", ["peanut"]) == []
    assert server.safe_review_suggestions(None, []) == []
    assert server.safe_review_suggestions(["Add fruit"], []) == ["Add fruit"]


def test_allergen_families_expand_typed_allergies():
    terms = set(server._extract_allergy_terms({"dietary_restrictions": ["food_allergy"], "food_allergy_detail": "eggs; shellfish"}))
    assert {"egg", "shrimp", "crab"} <= terms


def test_eight_focus_areas_cover_all_13_components_once():
    import focus_areas
    assert len(focus_areas.FOCUS_AREAS) == 8
    comps = [c for a in focus_areas.FOCUS_AREAS for c in a["components"]]
    assert sorted(comps) == sorted(c["id"] for c in server.HEI2020_COMPONENTS)
    assert sum(server.HEI2020_BY_ID[c]["max_score"] for c in comps) == 100


def test_focus_candidates_always_list_the_bottom_three_areas_by_rank():
    """Rank-based model (nutrition team 2026-11-06, item 2): there's no
    cut-off any more. Even a participant at the national benchmark on
    every component still has three areas with the most room to grow.
    A separate test (``test_focus_area_ranking.py``) covers the rank
    order itself; this one guards the "always three" invariant that
    replaces the old "empty if above the cut-off" behaviour."""
    import focus_areas
    at_bench = {c["id"]: c["national_benchmark"] for c in server.HEI2020_COMPONENTS}
    out = focus_areas.candidates(at_bench, server.HEI2020_BY_ID, server.BENCHMARK_TOLERANCE)
    assert len(out) == focus_areas.ROOM_TO_GROW_COUNT
    assert out[0]["suggested"] is True
    assert all(a.get("suggested") is False for a in out[1:])


def test_peanut_allergy_does_not_hide_tree_nuts_or_coconut():
    terms = server._extract_allergy_terms({"dietary_restrictions": ["food_allergy"], "food_allergy_detail": "peanuts"})
    menu = [{"name": n} for n in ["Creamy Peanut Butter", "Shredded Coconut", "Almond Milk", "Nutella", "Oatmeal"]]
    assert [i["name"] for i in server.filter_items_for_allergies(menu, terms)] == [
        "Shredded Coconut", "Almond Milk", "Nutella", "Oatmeal"]


def test_tree_nut_and_shellfish_families_stay_specific():
    tree = set(server._extract_allergy_terms({"dietary_restrictions": ["food_allergy"], "food_allergy_detail": "tree nuts"}))
    assert {"almond", "walnut", "cashew"} <= tree
    shell = set(server._extract_allergy_terms({"dietary_restrictions": ["food_allergy"], "food_allergy_detail": "shellfish"}))
    assert "shrimp" in shell and "salmon" not in shell
