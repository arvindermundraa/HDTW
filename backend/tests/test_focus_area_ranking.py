"""Rank-based strengths / room-to-grow — nutrition team 2026-11-06,
item 2 ("Strength or room to grow"): no numeric cut-off; the top
STRENGTHS_COUNT areas by score-as-share-of-maximum are strengths, the
bottom ROOM_TO_GROW_COUNT are room-to-grow, with a documented tie-break
(the area further from its own maximum ranks lower)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "llhs_unit_unused")
import focus_areas  # noqa: E402
import server  # noqa: E402


COMPONENTS = server.HEI2020_BY_ID


def _at_max() -> dict:
    return {c["id"]: c["max_score"] for c in server.HEI2020_COMPONENTS}


def _at_zero() -> dict:
    return {c["id"]: 0.0 for c in server.HEI2020_COMPONENTS}


def test_strengths_are_the_top_two_areas_by_ratio():
    scores = _at_max()
    # Knock Fats and Grains down — they should become bottom-of-ranked.
    scores["whole_grains"] = 0
    scores["refined_grains"] = 0
    scores["fatty_acids"] = 0
    scores["saturated_fats"] = 0
    buckets = focus_areas.strengths_and_room_to_grow(scores, COMPONENTS)
    assert len(buckets["strengths"]) == focus_areas.STRENGTHS_COUNT
    # None of the strengths are the areas we knocked down.
    strength_ids = {a["id"] for a in buckets["strengths"]}
    assert "grains" not in strength_ids and "fats" not in strength_ids


def test_room_to_grow_is_the_bottom_three_areas_by_rank_most_room_first():
    scores = _at_max()
    # Make three areas clearly the worst.
    scores["sodium"] = 1          # 1/10 ratio = 0.1
    scores["added_sugars"] = 2    # 2/10 ratio = 0.2
    scores["dairy"] = 3           # 3/10 ratio = 0.3
    buckets = focus_areas.strengths_and_room_to_grow(scores, COMPONENTS)
    ids_in_order = [a["id"] for a in buckets["room_to_grow"]]
    assert ids_in_order == ["sodium", "added_sugars", "dairy"]


def test_rank_ties_break_further_from_max_ranks_lower():
    """Two areas tie at ``score / max`` = 0.5. The area with the larger
    gap in absolute points ranks LOWER (i.e. comes later in the
    best-first ranking, earlier in the room-to-grow list)."""
    scores = _at_max()
    # Sodium (max 10): 5.0 -> ratio 0.5, gap 5.
    # Dairy  (max 10): 5.0 -> ratio 0.5, gap 5. Tie on both; keep stable order.
    scores["sodium"] = 5.0
    scores["dairy"] = 5.0
    # Fats (components max 20): 10.0 total -> ratio 0.5, gap 10.
    scores["fatty_acids"] = 5.0
    scores["saturated_fats"] = 5.0
    # Candidates: fats has gap 10 vs sodium/dairy gap 5 — fats ranks lower.
    full = focus_areas.ranked(scores, COMPONENTS)
    tied = [a for a in full if abs(a["_ratio"] - 0.5) < 1e-9]
    # The last of the three tied areas (by rank) should be fats.
    assert tied[-1]["id"] == "fats"


def test_focus_area_is_removed_from_all_buckets_but_not_from_ranking():
    scores = _at_max()
    scores["total_fruits"] = 0
    scores["whole_fruits"] = 0
    # Fruit is the lowest-ranked area; still the student is "working on"
    # fruit as focus, so it disappears from the room-to-grow list.
    buckets = focus_areas.strengths_and_room_to_grow(
        scores, COMPONENTS, focus_area="fruit"
    )
    for name in ("strengths", "room_to_grow", "other"):
        assert "fruit" not in {a["id"] for a in buckets[name]}


def test_strengths_and_room_to_grow_never_overlap():
    scores = _at_max()
    for cid in ("sodium", "added_sugars", "dairy", "whole_grains"):
        scores[cid] = 1.0
    buckets = focus_areas.strengths_and_room_to_grow(scores, COMPONENTS)
    strength_ids = {a["id"] for a in buckets["strengths"]}
    room_ids = {a["id"] for a in buckets["room_to_grow"]}
    assert strength_ids.isdisjoint(room_ids)


def test_every_area_shows_up_somewhere_when_all_eight_are_scored():
    scores = _at_max()
    scores["sodium"] = 1
    buckets = focus_areas.strengths_and_room_to_grow(scores, COMPONENTS)
    all_ids = {a["id"] for group in buckets.values() for a in group}
    assert all_ids == set(focus_areas.BY_ID)


def test_response_is_numeric_free():
    """Students must only see labels, not scores — the rank function may
    use ratios internally but the public bucket output must not carry
    them."""
    scores = _at_max()
    scores["sodium"] = 2
    buckets = focus_areas.strengths_and_room_to_grow(scores, COMPONENTS)
    for group in buckets.values():
        for item in group:
            for k in item.keys():
                assert not k.startswith("_"), f"private key leaked: {k}"
            assert set(item) == {"id", "label", "description"}


def test_counts_can_be_overridden_per_call():
    scores = _at_max()
    scores["sodium"] = 1
    scores["added_sugars"] = 2
    buckets = focus_areas.strengths_and_room_to_grow(
        scores, COMPONENTS, strengths_count=1, room_to_grow_count=2
    )
    assert len(buckets["strengths"]) == 1
    assert len(buckets["room_to_grow"]) == 2
