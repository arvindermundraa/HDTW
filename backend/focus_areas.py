"""
The eight focus areas ("Updated HEI for LLHS"): HEI-2020's 13 components
grouped into actionable dietary targets. Scoring still uses all 13
components; the areas are only what participants see and choose from.

Each participant works on ONE focus area at a time: chosen after the
baseline results (week 1), then kept or changed after the week 4 results
(week 5, "Review, Refocus"). users.focus_area holds the area id and
users.focus_areas its component ids, which the Eat rings, the Coach's
suggested questions, Future Me and My Path read.

Ranking (nutrition team 2026-11-06, "Strength or room to grow")
----------------------------------------------------------------
The team confirmed that strengths and room-to-grow areas are chosen by
RANK, not by a numeric cut-off:

  * the top ``STRENGTHS_COUNT`` areas by ``score / max`` are the
    participant's "Strengths";
  * the bottom ``ROOM_TO_GROW_COUNT`` areas are the participant's "Room
    to grow" / focus-area candidates;
  * everything in between is a plain "Other area".

Both counts live in module constants below so the team can change either
of them in one place.

Tie-break
~~~~~~~~~
When two areas tie on ``score / max``, the area with the LARGER
``max_points - score`` (i.e. further from its own maximum, in absolute
points) ranks LOWER. Rationale (per the team): a tie between a 2.9/5
area and a 5.8/10 area is really two areas at the same relative place,
but the 10-point area has more absolute room to grow — so it should come
first on the room-to-grow list and last on the strengths list.

Pure functions; no numbers ever leave this module for participants.
"""
from typing import Dict, List, Optional, Tuple

FOCUS_AREAS: List[Dict] = [
    {"id": "fruit", "label": "Fruit", "components": ["total_fruits", "whole_fruits"],
     "description": "More fruit, especially whole fruit rather than juice."},
    {"id": "vegetables_beans", "label": "Vegetables and beans", "components": ["total_vegetables", "greens_beans"],
     "description": "More vegetables, especially dark greens, beans and peas."},
    {"id": "grains", "label": "Grains", "components": ["whole_grains", "refined_grains"],
     "description": "More whole grains in place of refined grains."},
    {"id": "dairy", "label": "Dairy", "components": ["dairy"],
     "description": "Enough dairy or fortified soy alternatives."},
    {"id": "protein_foods", "label": "Protein foods", "components": ["total_protein_foods", "seafood_plant_proteins"],
     "description": "Enough protein, more of it from seafood, beans, nuts and seeds."},
    {"id": "fats", "label": "Fats", "components": ["fatty_acids", "saturated_fats"],
     "description": "More unsaturated fats, like oils, nuts and fish, in place of saturated fats."},
    {"id": "sodium", "label": "Sodium", "components": ["sodium"],
     "description": "Less salt, mostly from packaged and restaurant foods."},
    {"id": "added_sugars", "label": "Added sugars", "components": ["added_sugars"],
     "description": "Fewer added sugars, like sweet drinks and desserts."},
]
BY_ID = {a["id"]: a for a in FOCUS_AREAS}
AREA_OF_COMPONENT = {c: a["id"] for a in FOCUS_AREAS for c in a["components"]}

# Nutrition-team-controlled counts (confirmed 2026-11-06, "Strength or
# room to grow"). Change here in one place and every surface follows.
STRENGTHS_COUNT = 2
ROOM_TO_GROW_COUNT = 3


def public(area_id: str) -> Dict:
    a = BY_ID[area_id]
    return {"id": a["id"], "label": a["label"], "description": a["description"]}


def _area_ratio(area: Dict, scores: Dict[str, float], components: Dict[str, Dict]) -> Optional[Tuple[float, float]]:
    """``(score / max, max - score)`` for an area, or ``None`` when no
    component has a score yet. The second value is the absolute gap
    used only for tie-breaking (further from max ranks lower)."""
    have = [c for c in area["components"] if scores.get(c) is not None]
    if not have:
        return None
    maximum = sum(components[c]["max_score"] for c in have)
    total = sum(scores[c] for c in have)
    return (total / maximum if maximum else 0.0, maximum - total)


def ranked(scores: Dict[str, float], components: Dict[str, Dict]) -> List[Dict]:
    """The eight focus areas ranked best-first by ``score / max``, with
    the tie-break documented in the module docstring.

    Returned shape per item:
    ``{id, label, description, _ratio, _gap}``. The underscore-prefixed
    fields are internal and must be dropped before responding to the
    student; use ``public()`` or ``_strip_private()`` below.
    """
    rows: List[Dict] = []
    for a in FOCUS_AREAS:
        r = _area_ratio(a, scores, components)
        if r is None:
            continue
        ratio, gap = r
        rows.append({**public(a["id"]), "_ratio": ratio, "_gap": gap})
    # Best first: higher ratio wins; tie -> smaller gap wins.
    rows.sort(key=lambda r: (-r["_ratio"], r["_gap"]))
    return rows


def _strip_private(area: Dict) -> Dict:
    return {k: v for k, v in area.items() if not k.startswith("_")}


def bars(scores: Dict[str, float], components: Dict[str, Dict]) -> List[Dict]:
    """A bar per focus area for the baseline-feedback / Food dashboard,
    with per-component "sub-bars" so the Grains and Fats bars (each of
    which combines two HEI-2020 components) can expand on tap. Nutrition
    team 2026-11-06, item 1 ("Grains and Fats results").

    Each item carries only ``fill`` (0.0–1.0) and is deliberately free
    of absolute HEI scores and maximum-point numbers — the UI uses
    ``fill`` as a bar width, never as a displayed number. For combined
    areas, ``fill`` is the sum of component scores divided by the sum of
    their maximum points, as the team asked for. Un-scored components
    (``scores[cid] is None``) are dropped from that area's totals, and
    the area is omitted if no component has a score.
    """
    out: List[Dict] = []
    for a in FOCUS_AREAS:
        have = [c for c in a["components"] if scores.get(c) is not None]
        if not have:
            continue
        maximum = sum(components[c]["max_score"] for c in have)
        total = sum(scores[c] for c in have)
        sub = [
            {
                "id": c,
                "label": components[c]["label"],
                "fill": (scores[c] / components[c]["max_score"]) if components[c]["max_score"] else 0.0,
                "kind": components[c]["kind"],  # adequacy vs moderation
            }
            for c in a["components"] if scores.get(c) is not None
        ]
        out.append({
            "id": a["id"],
            "label": a["label"],
            "fill": (total / maximum) if maximum else 0.0,
            "components": sub,
            "expandable": len(sub) > 1,
        })
    return out


def strengths_and_room_to_grow(
    scores: Dict[str, float],
    components: Dict[str, Dict],
    *,
    focus_area: Optional[str] = None,
    strengths_count: int = STRENGTHS_COUNT,
    room_to_grow_count: int = ROOM_TO_GROW_COUNT,
) -> Dict[str, List[Dict]]:
    """Returns ``{strengths, room_to_grow, other}`` — always numeric-free.

    * ``strengths``: the top ``strengths_count`` areas by rank.
    * ``room_to_grow``: the bottom ``room_to_grow_count`` areas by rank
      (most room first).
    * ``other``: the areas in between.

    ``focus_area`` (the area the student is currently working on) is
    removed from all three lists so the Food dashboard can show it
    separately. The buckets still use the full-eight ranking — the
    chosen focus area is excluded at the end, not before ranking.
    """
    full = ranked(scores, components)
    if not full:
        return {"strengths": [], "room_to_grow": [], "other": []}
    # Ranked order: best first. Strengths = first N. Room-to-grow = last M,
    # but presented most-room-first (reverse of the tail).
    strengths_slice = full[:strengths_count]
    room_slice = list(reversed(full[-room_to_grow_count:])) if room_to_grow_count else []
    tail_ids = {a["id"] for a in room_slice}
    strength_ids = {a["id"] for a in strengths_slice}
    other_slice = [a for a in full if a["id"] not in tail_ids and a["id"] not in strength_ids]

    def drop_focus(items: List[Dict]) -> List[Dict]:
        return [_strip_private(a) for a in items if a["id"] != focus_area]

    return {
        "strengths": drop_focus(strengths_slice),
        "room_to_grow": drop_focus(room_slice),
        "other": drop_focus(other_slice),
    }


def candidates(
    scores: Dict[str, float],
    components: Dict[str, Dict],
    tolerance: float = 0.0,  # kept for signature compatibility; not used
    *,
    room_to_grow_count: int = ROOM_TO_GROW_COUNT,
) -> List[Dict]:
    """The focus-area candidates shown on the Week 1 selection screen,
    most room first (the first is marked ``suggested``). Backed by the
    rank-based bucket above — no numeric cut-off. The ``tolerance``
    argument is retained so existing callers keep working, but is
    ignored (kept for one release, then removable).
    """
    buckets = strengths_and_room_to_grow(
        scores, components, focus_area=None, room_to_grow_count=room_to_grow_count,
    )
    out = list(buckets["room_to_grow"])
    for i, a in enumerate(out):
        a["suggested"] = i == 0
    return out


def components_of(area_id: Optional[str]) -> List[str]:
    return list(BY_ID[area_id]["components"]) if area_id in BY_ID else []


def groups(
    scores: Dict[str, float],
    components: Dict[str, Dict],
    tolerance: float = 0.0,  # kept for signature compatibility; not used
    focus_area: Optional[str] = None,
) -> Dict[str, List[Dict]]:
    """Backwards-compatible wrapper used by ``/domains/food``.

    Returns ``{strengths, others}`` the way the old cutoff-based version
    did. ``strengths`` now comes from the top-``STRENGTHS_COUNT`` rank
    (same areas callers rendered as "Strengths" before). ``others``
    includes every non-strength, non-focus area — i.e. the room-to-grow
    plus everything in between — so existing UI that lists "the rest"
    keeps the same visual behaviour until the UI is updated to split
    them apart explicitly. The ``tolerance`` arg is ignored (kept so
    callers don't have to migrate at once).
    """
    buckets = strengths_and_room_to_grow(scores, components, focus_area=focus_area)
    return {
        "strengths": buckets["strengths"],
        "others": buckets["room_to_grow"] + buckets["other"],
    }
