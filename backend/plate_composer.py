"""
Plate Composer - builds suggested plates from today's real, classified
dining-hall menu.

Design principle (from design review, directly): DO NOT sort by health.
A "healthiest first" list puts salad at #1 every time and gets ignored by
students who wouldn't pick it anyway - an ignored feature helps no one.
Instead: anchor each suggestion in a familiar/appealing entree (protein or
grain-forward, not vegetable-only), then round it out with a fiber/veg
side. The health logic is invisible - no scores, no ranking, no "best for
your heart" framing anywhere in the output. Every suggestion is already
reasonably balanced; the student just picks whichever sounds good.

This also implements the anti-repetition variety engine: suggestions
de-prioritize items the student logged in the last few days, so the same
hall doesn't feel stale even with a fixed daily menu.
"""
import re
from typing import List, Optional

from dining_classifier import is_condiment

MAX_PLATE_ITEMS = 4

# Balance rule (same three groups the plate-builder game and the review
# prompt use): each plate aims for a protein anchor + a vegetable or fruit
# + a whole grain (a starchy side only when no whole grain works), with at
# most ONE salty/processed item and no dessert-style sides. The anchor is
# always a protein, so a plate is never sides-only (fries + peppers + rice).
_PREP_PREFIX = re.compile(r"^(sliced|diced|chopped|shredded|julienne|shaved|minced|crushed|grated|"
                          r"thinly sliced|cubed tofu|lettuce leaf)\b", re.IGNORECASE)


def _all_items(menu: dict) -> List[dict]:
    items = []
    for station in menu.get("stations", []):
        for item in station.get("items", []):
            items.append({**item, "station": station.get("station", "")})
    return items


def _cats(item: dict) -> set:
    return set(item.get("tags", {}).get("log_categories") or [])


def _condiment(item: dict) -> bool:
    tags = item.get("tags", {})
    return tags["is_condiment"] if "is_condiment" in tags else is_condiment(item.get("name", ""))


def _is_protein(item: dict) -> bool:
    return bool(item.get("tags", {}).get("has_lean_protein") or _cats(item) & {"beans_fish_nuts", "other_protein"})


def _is_produce(item: dict) -> bool:
    return bool(item.get("tags", {}).get("has_vegetables") or _cats(item) & {"vegetables", "fruit"})


def _is_whole_grain(item: dict) -> bool:
    return bool(item.get("tags", {}).get("has_whole_grains") or "whole_grains" in _cats(item))


def _is_starch(item: dict) -> bool:
    return "refined_grains_starchy" in _cats(item)


def _is_salty(item: dict) -> bool:
    return bool(item.get("tags", {}).get("high_sodium") or "salty_processed" in _cats(item))


def _is_sugary(item: dict) -> bool:
    return "added_sugars" in _cats(item)


def _is_topping(item: dict) -> bool:
    """Salad-bar/omelet-bar components ("Sliced Red Onion", "Diced Ham") —
    usable, but a real side or entree is preferred when one exists."""
    name = item.get("name", "").strip()
    return bool(_PREP_PREFIX.match(name)) or "hummus" in name.lower()


def _is_anchor_candidate(item: dict) -> bool:
    """An anchor is a protein-forward entree - NOT a plain vegetable side
    or a starch. This avoids both the "salad wins every time" failure and
    sides-only plates."""
    return _is_protein(item) and not _condiment(item) and not _is_sugary(item)


def _aggregate_tags(items: List[dict]) -> dict:
    return {
        "has_vegetables": any(i.get("tags", {}).get("has_vegetables") or "vegetables" in _cats(i) for i in items),
        "has_fruit": any("fruit" in _cats(i) for i in items),
        "has_whole_grains": any(_is_whole_grain(i) for i in items),
        "has_lean_protein": any(i.get("tags", {}).get("has_lean_protein") for i in items),
        "has_protein": any(_is_protein(i) for i in items),
        "high_sodium_items": [i["name"] for i in items if _is_salty(i)],
    }


def _pick_side(candidates: List[dict], anchor: dict, plate: List[dict], usage: dict) -> Optional[dict]:
    """Deterministic pick: real sides before toppings, same station as the
    anchor first (that's how the hall pairs its own entrees), then the
    least-used side across plates (variety), then menu order."""
    names = {i["name"] for i in plate}
    plate_salty = any(_is_salty(i) for i in plate)
    ok = [c for c in candidates
          if c["name"] not in names and not (plate_salty and _is_salty(c))]
    if not ok:
        return None
    return min(ok, key=lambda c: (_is_topping(c), c.get("station") != anchor.get("station"),
                                  usage.get(c["name"], 0), candidates.index(c)))


def compose_plates(menu: dict, recent_item_names: Optional[List[str]] = None, n: int = 4) -> List[dict]:
    """Returns up to n suggested plates from real items on today's menu.
    Order is variety-biased, NOT a health ranking - never present these as
    ranked by healthiness.

    Every plate carries an 'aggregate' tag summary for internal phrasing
    use; callers must present it additively - never as a score, percentage,
    or "best/worst" label."""
    recent = set(recent_item_names or [])
    items = _all_items(menu)
    if not items:
        return []

    def side_ok(i: dict) -> bool:
        return not _condiment(i) and not _is_sugary(i)

    anchors = [i for i in items if _is_anchor_candidate(i)]
    # Flavored yogurts ("Strawberry Yogurt") carry a fruit tag but aren't a produce side.
    produce = [i for i in items if _is_produce(i) and side_ok(i) and not _is_protein(i) and not _is_starch(i)
               and "dairy" not in _cats(i)]
    whole_grains = [i for i in items if _is_whole_grain(i) and side_ok(i) and not _is_protein(i)]
    starches = [i for i in items if _is_starch(i) and side_ok(i) and not _is_protein(i) and not _is_salty(i)]

    # Variety: recently-logged anchors and toppings sort to the back (not
    # removed), then stations are taken round-robin so four plates don't
    # all come from the first station on the menu.
    anchors.sort(key=lambda i: (i["name"] in recent, _is_topping(i)))
    by_station: dict = {}
    for a in anchors:
        by_station.setdefault(a.get("station", ""), []).append(a)
    queues = list(by_station.values())
    ordered = []
    while any(queues):
        for q in queues:
            if q:
                ordered.append(q.pop(0))
    # Keep the recent/topping bias global rather than per round-robin lap.
    ordered.sort(key=lambda i: (i["name"] in recent, _is_topping(i)))

    plates = []
    used_names = set()
    usage: dict = {}
    for anchor in ordered:
        if len(plates) >= n:
            break
        if anchor["name"] in used_names:
            continue

        plate_items = [anchor]
        # Fruit words in an entree ("Orange Chicken") don't make it a produce serving.
        if not (anchor.get("tags", {}).get("has_vegetables") or "vegetables" in _cats(anchor)):
            pick = _pick_side(produce, anchor, plate_items, usage)
            if pick:
                plate_items.append(pick)
        if not (_is_whole_grain(anchor) or _is_starch(anchor)):
            pick = _pick_side(whole_grains, anchor, plate_items, usage) or \
                _pick_side(starches, anchor, plate_items, usage)
            if pick:
                plate_items.append(pick)

        # A protein plus nothing else isn't a plate suggestion.
        if len(plate_items) < 2:
            continue
        used_names.add(anchor["name"])
        for i in plate_items[1:]:
            usage[i["name"]] = usage.get(i["name"], 0) + 1

        plate_items = plate_items[:MAX_PLATE_ITEMS]
        agg = _aggregate_tags(plate_items)
        plates.append({
            "items": [{"id": i["id"], "name": i["name"], "station": i.get("station", "")} for i in plate_items],
            "aggregate": agg,
            "blurb": _blurb(plate_items, agg),
        })

    return plates


def _blurb(items: List[dict], agg: dict) -> str:
    """Short, additive, number-free description. Never mentions calories,
    grams, or a health score."""
    names = [i["name"] for i in items]
    if not names:
        return "A plate for today."
    lead = names[0]
    rest = " with " + " and ".join(names[1:]) if len(names) > 1 else ""
    base = f"{lead}{rest}."
    if agg["high_sodium_items"]:
        return base + " A saltier plate — pairing it with something fresh later today is a nice move if you want to."
    extras = []
    if agg["has_vegetables"]:
        extras.append("a veg side")
    elif agg.get("has_fruit"):
        extras.append("some fruit")
    if agg["has_whole_grains"]:
        extras.append("a whole grain")
    if extras:
        return base + f" Already brings {' and '.join(extras)}."
    return base


def suggest_swap(menu: dict, item_id: str, exclude_ids: Optional[List[str]] = None) -> List[dict]:
    """Given one item on a plate, suggest same-station alternatives - the
    tactile "swap" interaction, not a ranked replacement list."""
    exclude = set(exclude_ids or []) | {item_id}
    items = _all_items(menu)
    target = next((i for i in items if i["id"] == item_id), None)
    if not target:
        return []
    same_station = [i for i in items if i.get("station") == target.get("station") and i["id"] not in exclude]
    return [{"id": i["id"], "name": i["name"]} for i in same_station[:6]]
