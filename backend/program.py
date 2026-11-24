"""
The 8-week LLHS program ("Updated HEI for LLHS", curriculum table): one unit
per week, released week by week from the day the participant joined, each a
connected sequence of four steps:

  watch    a short video introducing the week's idea (+ Youth Ambassador clip)
  practice an in-app exercise (a scenario game, Build a Meal, the focus screen)
  do_it    try it in real life this week
  reflect  a short written reflection: what worked, what was hard, what to adjust

Existing content is reused where it fits (the three curriculum videos and the
three practice games); a step whose content isn't produced yet is listed as
"coming soon" rather than invented. Pure functions, no database.
"""
from datetime import date, timedelta
from typing import Dict, List, Optional, Set

WEEKS = 8

# Points per step. Doing and reflecting count at least as much as watching
# (study team: reward applying skills over consuming content).
POINTS = {"watch": 15, "practice": 20, "do_it": 20, "reflect": 15}

UNITS: List[Dict] = [
    {"week": 1, "title": "Your First Step",
     "summary": "Why heart-healthy eating matters now, and choosing what you'll work on.",
     "steps": {
         "watch": {"title": "Heart health and your focus area", "video": None},
         "practice": {"milestone": "Set your goal and action plan", "title": "Choose your focus area and set a goal", "route": "/focus-areas", "auto": "focus_area"},
         "do_it": {"milestone": "Tried your goal at a meal", "title": "Try your goal at one meal this week"},
         "reflect": {"milestone": "Reflected on your eating patterns", "title": "Reflect", "prompt": "What did you notice about how you usually eat?"},
     }},
    {"week": 2, "title": "Know What to Look For",
     "summary": "Spotting food choices that support your goal on menus and labels.",
     "steps": {
         "watch": {"title": "Applying Nutrition Information", "video": "c2"},
         "practice": {"milestone": "Spotted goal-friendly choices on a menu", "title": "Nutrition / Menu Challenge", "route": "/game/g2", "game": "g2"},
         "do_it": {"milestone": "Found a goal-friendly choice in real life", "title": "Find one choice that fits your goal at the dining hall or store"},
         "reflect": {"milestone": "Planned your next chance to use your goal", "title": "Reflect", "prompt": "When is your next chance to use your goal, and what will you choose?"},
     }},
    {"week": 3, "title": "Build It Into What You Already Eat",
     "summary": "Small changes to meals you already like.",
     "steps": {
         "watch": {"title": "Assembling Balanced Meals", "video": "c3"},
         "practice": {"milestone": "Built a balanced meal from the dining menu", "title": "Build a meal from today's dining menu", "route": "/build-meal"},
         "do_it": {"milestone": "Tried a change to a meal you eat", "title": "Try one change to a meal you usually eat"},
         "reflect": {"milestone": "Reflected on what worked", "title": "Reflect", "prompt": "Which change did you try, and would you do it again?"},
     }},
    {"week": 4, "title": "Make It Work in Real Life",
     "summary": "Planning around time, money, what's available and the people you eat with.",
     "steps": {
         "watch": {"title": "Planning for Healthy Eating", "video": "c1"},
         "practice": {"milestone": "Planned meals for the week", "title": "Plan Your Week", "route": "/game/g1", "game": "g1"},
         "do_it": {"milestone": "Made a backup plan for a busy day", "title": "Make a backup plan for a busy or social day"},
         "reflect": {"milestone": "Worked through a barrier", "title": "Reflect", "prompt": "What got in the way this week, and what's your backup plan?"},
     }},
    {"week": 5, "title": "Review, Refocus, and Build on Progress",
     "summary": "Your updated results: keep your focus area or choose a new one.",
     "steps": {
         "watch": {"title": "Reading your updated results", "video": None},
         "practice": {"milestone": "Reviewed your results and refocused", "title": "Review your results; keep or change your focus area", "route": "/focus-areas",
                      "auto": "focus_area_since_week"},
         "do_it": {"milestone": "Tried your updated goal", "title": "Try your updated goal this week"},
         "reflect": {"milestone": "Revised your goal", "title": "Reflect", "prompt": "What's going well, and what will you change about your goal?"},
     }},
    {"week": 6, "title": "Patterns, Not Perfection",
     "summary": "Looking at your overall pattern instead of single meals.",
     "steps": {
         "watch": {"title": "Patterns, not perfection", "video": None},
         "practice": {"milestone": "Looked back at your week's patterns", "title": "Look back at your week", "route": "/weekly-story"},
         "do_it": {"milestone": "Made a practical adjustment", "title": "Make one practical adjustment"},
         "reflect": {"milestone": "Reflected on patterns, not perfection", "title": "Reflect", "prompt": "What pattern did you notice, and what's one small adjustment?"},
     }},
    {"week": 7, "title": "Adjust When Life Changes",
     "summary": "Keeping your goal going through exams, travel and busy weeks.",
     "steps": {
         "watch": {"title": "Getting back on track", "video": None},
         "practice": {"milestone": "Planned for a disruption", "title": "Plan for a disruption", "route": None},
         "do_it": {"milestone": "Adapted when life changed", "title": "Use your plan when something changes"},
         "reflect": {"milestone": "Reflected on getting back on track", "title": "Reflect", "prompt": "What disrupted your routine, and how did you adapt?"},
     }},
    {"week": 8, "title": "Keep What Works",
     "summary": "Making your changes last after the program.",
     "steps": {
         "watch": {"title": "Keeping it going", "video": None},
         "practice": {"milestone": "Made a plan to keep going", "title": "Make your plan to keep going", "route": None},
         "do_it": {"milestone": "Picked a habit to keep", "title": "Pick one habit to keep"},
         "reflect": {"milestone": "Looked back on 8 weeks", "title": "Reflect", "prompt": "Looking back on 8 weeks, what will you keep doing?"},
     }},
]
STEP_ORDER = ["watch", "practice", "do_it", "reflect"]
STEP_LABEL = {"watch": "Watch", "practice": "Practice", "do_it": "Do it", "reflect": "Reflect"}


def current_week(start: date, today: date) -> int:
    """Week 1 starts the day the participant joined; capped at 8."""
    return max(1, min(WEEKS, (today - start).days // 7 + 1))


def week_opens(start: date, week: int) -> date:
    return start + timedelta(days=7 * (week - 1))


def build(start: date, today: date, *, done_steps: Set[str], videos_done: Set[str], games_done: Set[str],
          focus_set_on: Optional[date], videos: Dict[str, Dict]) -> Dict:
    """The participant's program. `done_steps` holds "week:step" keys the
    participant marked done; video, game and focus-area steps also complete
    from what they did elsewhere in the app."""
    now = current_week(start, today)
    weeks = []
    for u in UNITS:
        w = u["week"]
        opens = week_opens(start, w)
        available = w <= now
        steps = []
        for key in STEP_ORDER:
            s = u["steps"][key]
            ready = True
            route, params = s.get("route"), None
            if key == "watch":
                v = videos.get(s.get("video") or "")
                ready = bool(v)
                route, params = ("/video/[id]", {"id": v["id"]}) if v else (None, None)
                done = bool(v) and v["id"] in videos_done
            elif s.get("game"):
                done = s["game"] in games_done
            elif s.get("auto") == "focus_area":
                done = focus_set_on is not None
            elif s.get("auto") == "focus_area_since_week":
                done = focus_set_on is not None and focus_set_on >= opens
            else:
                ready = key in ("do_it", "reflect") or bool(route)
                done = False
            done = done or f"{w}:{key}" in done_steps
            steps.append({
                "key": key, "label": STEP_LABEL[key], "title": s["title"], "prompt": s.get("prompt"),
                "milestone": s.get("milestone"),
                "route": route, "params": params, "ready": ready, "done": done,
                "points": POINTS[key],
                # Video, game and focus steps complete themselves; the rest are marked by the participant.
                "self_marked": key in ("do_it", "reflect") or (key == "practice" and not s.get("game") and not s.get("auto")),
            })
        # Steps whose content isn't produced yet ("coming soon") don't count.
        n_total = sum(1 for s in steps if s["ready"] or s["done"])
        n_done = sum(1 for s in steps if s["done"])
        status = "done" if available and n_done == n_total else "current" if w == now else "available" if available else "upcoming"
        weeks.append({"week": w, "title": u["title"], "summary": u["summary"], "opens_on": opens.isoformat(),
                      "available": available, "status": status, "steps_done": n_done, "steps_total": n_total,
                      "steps": steps})
    return {"current_week": now, "weeks": WEEKS, "units": weeks}


def next_step(program: Dict) -> Optional[Dict]:
    """The next thing to do this week: the first unfinished, ready step of the
    current week, else of an earlier week still unfinished."""
    for unit in sorted(program["units"], key=lambda u: (u["week"] != program["current_week"], -u["week"])):
        if not unit["available"]:
            continue
        for s in unit["steps"]:
            if not s["done"] and s["ready"]:
                return {**s, "week": unit["week"], "unit_title": unit["title"]}
    return None


def can_mark(week: int, step: str) -> bool:
    unit = next((u for u in UNITS if u["week"] == week), None)
    if not unit or step not in STEP_ORDER:
        return False
    s = unit["steps"][step]
    return step in ("do_it", "reflect") or (step == "practice" and not s.get("game") and not s.get("auto")
                                            and bool(s.get("route")))
