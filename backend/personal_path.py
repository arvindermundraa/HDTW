"""My Path: the 8-week program as a path, built from each participant's
own data (study team feedback, Oct 2026, section 3).

* one stage per program week, all 8 visible from the start, upcoming ones
  marked "coming up" with the date they open;
* milestones are skills applied, never content views or a health outcome:
  the week's practice, trying it in real life, reflecting and adapting,
  the participant's own focus-area milestone for the week, and the
  food-recall check-ins at weeks 1, 4 and 8;
* one goal-specific message, built only from what was actually logged.

Pure functions only (no database), so the rules are unit-testable.
"""
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import focus_areas

from study_time import study_day_key

# HEI-2020 component -> in-app logging categories that "include" it.
# Moderation components (sodium, refined grains, added sugars, saturated
# fats) have no include-this tag, so their milestone counts logging days.
FOCUS_CATEGORIES: Dict[str, List[str]] = {
    "total_fruits": ["fruit"],
    "whole_fruits": ["fruit"],
    "total_vegetables": ["vegetables"],
    "greens_beans": ["vegetables", "beans_fish_nuts"],
    "whole_grains": ["whole_grains"],
    "dairy": ["dairy"],
    "total_protein_foods": ["other_protein", "beans_fish_nuts"],
    "seafood_plant_proteins": ["beans_fish_nuts"],
    "fatty_acids": ["beans_fish_nuts"],
}
FOCUS_TARGET = 3          # meals that include a focus food
FOCUS_DAYS_TARGET = 5     # logging days while working on a moderation focus



def _day(iso: str) -> str:
    """YYYY-MM-DD in the study TZ — not iso[:10] (that was keyed by UTC)."""
    return study_day_key(iso)


def _distinct_days(stamps: List[str]) -> int:
    return len({_day(s) for s in stamps})


def _milestone(mid, label, behavior, *, done_at=None, current=0, target=1, detail="", action=None, achieved=None):
    achieved = bool(done_at) if achieved is None else achieved
    if achieved:
        current = target  # a reached milestone always reads "done", never "0 of 1"
    return {
        "id": mid,
        "label": label,
        "behavior": behavior,
        "achieved": achieved,
        "achieved_at": done_at if achieved else None,
        "progress": {"current": min(current, target), "target": target},
        "detail": detail,
        "action": action,
    }


FOCUS_FOOD = {
    "fruit": "fruit", "vegetables_beans": "vegetables or beans", "grains": "whole grains", "dairy": "dairy",
    "protein_foods": "protein foods", "fats": "nuts, seeds or fish",
}
FOCUS_DAYS_IN_WEEK = 4    # logging days in a week, for areas with no "include" food (sodium, added sugars)
RECALL_WEEK = {1: "baseline", 4: "checkin_1", 8: "checkin_2"}


def _ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _focus_cats(area_id: Optional[str]) -> List[str]:
    return sorted({c for cid in focus_areas.components_of(area_id) for c in FOCUS_CATEGORIES.get(cid, [])})


def build_personal_path(
    user: Dict[str, Any],
    meals: List[Dict[str, Any]],
    program: Dict[str, Any],
    assessments: List[Dict[str, Any]],
    next_checkin: Dict[str, Any],
) -> Dict[str, Any]:
    """The 8-week path (study team feedback, section 3): one stage per program
    week, each with skill milestones (the week's practice, applying it in real
    life, reflecting and adapting), the participant's focus-area milestone for
    that week, and the food-recall check-ins at weeks 1, 4 and 8. Upcoming
    stages are listed too, so the whole 8 weeks is visible."""
    meals = sorted((m for m in meals if not m.get("skipped")), key=lambda m: m["created_at"])
    area = user.get("focus_area") if user.get("focus_area") in focus_areas.BY_ID else None
    cats = set(_focus_cats(area))
    imported = {a.get("assessment_type"): a.get("created_at") for a in assessments}
    now = program["current_week"]

    weeks: List[Dict[str, Any]] = []
    for unit in program["units"]:
        w = unit["week"]
        first = unit["opens_on"]
        last = (datetime.fromisoformat(first) + timedelta(days=6)).date().isoformat()
        in_week = [m for m in meals if first <= _day(m["created_at"]) <= last]
        ms: List[Dict[str, Any]] = []
        if w in RECALL_WEEK:
            t = RECALL_WEEK[w]
            label = "Baseline food recalls" if w == 1 else f"Week {w} food recalls"
            ms.append(_milestone(f"recall_{w}", label, "assessment", done_at=imported.get(t),
                                 detail="Two ASA24 recalls: one about a weekday, one about a weekend day."))
        for step in unit["steps"]:
            if not step.get("milestone"):
                continue
            action = ({"label": step["label"], "route": step["route"], "params": step.get("params") or {}}
                      if step.get("route") and step["key"] == "practice" else {"label": "Open this week", "route": "/(tabs)/learn"})
            ms.append(_milestone(f"w{w}_{step['key']}", step["milestone"],
                                 {"practice": "practice", "do_it": "apply", "reflect": "reflect"}[step["key"]],
                                 achieved=step["done"], detail=step["title"],
                                 action=action if unit["available"] else None))
        if area and unit["available"]:
            if cats:
                hits = [m for m in in_week if cats & set(m.get("categories") or [])]
                food = FOCUS_FOOD.get(area, "your focus food")
                ms.append(_milestone(f"w{w}_focus", f"{food[0].upper()}{food[1:]} in {FOCUS_TARGET} meals this week",
                                     "focus_area", achieved=len(hits) >= FOCUS_TARGET, current=len(hits),
                                     target=FOCUS_TARGET, detail=f"{min(len(hits), FOCUS_TARGET)} of {FOCUS_TARGET} meals so far.",
                                     action={"label": "Log a meal", "route": "/log-meal"}))
            else:
                days = _distinct_days([m["created_at"] for m in in_week])
                ms.append(_milestone(f"w{w}_focus", f"Tracked meals on {FOCUS_DAYS_IN_WEEK} days this week",
                                     "focus_area", achieved=days >= FOCUS_DAYS_IN_WEEK, current=days,
                                     target=FOCUS_DAYS_IN_WEEK, detail=f"{min(days, FOCUS_DAYS_IN_WEEK)} of {FOCUS_DAYS_IN_WEEK} days so far.",
                                     action={"label": "Log a meal", "route": "/log-meal"}))
        for m in ms:
            m["week"] = w
        weeks.append({"week": w, "title": unit["title"], "opens_on": first, "status": unit["status"],
                      "available": unit["available"], "milestones": ms,
                      "achieved": sum(1 for m in ms if m["achieved"]), "total": len(ms)})

    flat = [m for wk in weeks for m in wk["milestones"]]
    achieved = sum(1 for m in flat if m["achieved"])
    return {"current_week": now, "weeks": weeks, "milestones": flat, "achieved_count": achieved,
            "total": len(flat), "position": round(achieved / len(flat), 2) if flat else 0.0,
            "message": _personal_message(user, area, cats, meals, weeks[now - 1]),
            "next_checkin": next_checkin}


def _personal_message(user, area, cats, meals, week) -> Optional[str]:
    """A goal-specific line about this week, only from what was logged."""
    if not area:
        return None
    first = week["opens_on"]
    last = (datetime.fromisoformat(first) + timedelta(days=6)).date().isoformat()
    in_week = [m for m in meals if first <= _day(m["created_at"]) <= last]
    goal = ((user.get("focus_goal") or {}).get("goal") or "").strip()
    lead = f"You set a goal: “{goal}”." if goal else f"You're working on {focus_areas.BY_ID[area]['label'].lower()}."
    if cats:
        n = sum(1 for m in in_week if cats & set(m.get("categories") or []))
        if n:
            return f"{lead} That's your {_ordinal(n)} meal with {FOCUS_FOOD.get(area, 'your focus food')} this week!"
        return None
    days = _distinct_days([m["created_at"] for m in in_week])
    if days:
        return f"{lead} You've logged meals on {days} day{'s' if days != 1 else ''} this week, which helps you spot where to make swaps."
    return None
