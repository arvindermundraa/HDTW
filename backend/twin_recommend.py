"""The behavioral twin — choosing one or two small, feasible steps from a
reviewed library, for THIS participant, and saying why.

What it draws on:
  * content/twin_library.json — reviewed diet, activity, sleep and
    cross-domain items (add, modify, grocery, routine, plan), each tagged
    with the behavior-change techniques it uses (BCT Taxonomy v1), where it
    happens, what it fits and what it needs. reviewed:false until approved.
  * the food swaps in content/swaps.json, as From your meals already finds
    them (twin_suggest / twin_llm), wrapped into the same shape.
  * the participant's profile state (twin_profile.build_state): their
    confirmed patterns, stated circumstances, constraints learned from
    their feedback, eating contexts, setup, allergies, dislikes, and what
    happened with earlier steps.

How a step is chosen — every rule is plain code a reviewer can read:
  1. Hard filters (never shown): wrong focus area; a pattern-targeted step
     whose pattern they haven't confirmed; a domain they haven't asked for
     help with; somewhere they don't eat; something they can't prepare; an
     allergy or dislike; something they said "not for me" to recently; a
     constraint they told us about (cost, time, schedule, equipment);
     during a recent safety check-in, anything about food or exercise.
  2. Scoring (ranked): it addresses a confirmed pattern; it fits a
     circumstance they named; it works where they actually eat; it respects
     a constraint they named; it uses a technique that worked for them
     before, or a different approach to a goal where one step didn't fit.
  3. One or two new steps at a time, from different domains where there's
     a choice, after anything they're already trying.
Every chosen step carries the factors that put it there, turned into one
or two plain sentences ("Because you said weekdays are harder to fit
movement into. It fits into something you already do."). No model writes
or picks these steps. Pure functions only.
"""
import json
import re
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import focus_areas
import twin_patterns
import twin_suggest

LIBRARY_PATH = Path(__file__).parent / "content" / "twin_library.json"

DOMAINS = ("diet", "activity", "sleep")
TYPES = {"add": "Add something", "modify": "Tweak a meal you have", "grocery": "Grocery list",
         "routine": "Fit it into your routine", "plan": "Plan it", "swap": "Swap"}
# Behavior-change techniques, with their BCT Taxonomy v1 numbers
# (Michie et al., Ann Behav Med 2013) so the research team can code them.
BCT = {
    "goal_setting": ("Goal setting", "1.1"),
    "coping_planning": ("Problem solving / coping planning", "1.2"),
    "action_planning": ("Action planning", "1.4"),
    "review_goals": ("Review behavior goals", "1.5"),
    "self_monitoring": ("Self-monitoring of behavior", "2.3"),
    "social_support": ("Social support", "3.1"),
    "prompts_cues": ("Prompts and cues", "7.1"),
    "behavior_substitution": ("Behavior substitution", "8.2"),
    "habit_formation": ("Habit formation", "8.3"),
    "graded_tasks": ("Graded tasks", "8.7"),
    "restructuring_environment": ("Restructuring the physical environment", "12.1"),
    "adding_objects": ("Adding objects to the environment", "12.5"),
}
CONTEXTS = {
    "dining_hall": "at the dining hall", "campus_food": "at campus food spots", "takeout": "when you order out",
    "grocery": "when you shop", "at_home": "at home", "convenience": "at a convenience store",
    "someone_else_prepares": "when someone else cooks", "campus": "on campus", "anywhere": "anywhere",
}
# When a step happens: the chip's label, and how the reinforcement line
# names that moment ("Keep it tied to the end of lunch").
WHEN = {
    "morning": ("In the morning", "your morning"),
    "between_classes": ("Between classes", "the walk between classes"),
    "lunch": ("At lunch", "lunch"),
    "after_lunch": ("After lunch", "the end of lunch"),
    "afternoon": ("In the afternoon", "your afternoon"),
    "dinner": ("At dinner", "dinner"),
    "after_dinner": ("After dinner", "the end of dinner"),
    "evening": ("In the evening", "your evening"),
    "before_bed": ("Before bed", "getting ready for bed"),
    "weekend": ("On weekends", "your weekends"),
    "when_shopping": ("When I shop", "your grocery runs"),
    "when_ordering": ("When I order", "ordering"),
}
EFFORTS = ("low", "medium")
COSTS = ("none", "low", "some")
# Constraints a step can respect (`helps`) and that feedback can teach the
# twin (twin_profile.REASONS maps reasons to these).
CONSTRAINTS = ("cost", "time", "schedule", "forgot", "energy", "environment", "someone_else", "equipment",
               "availability")
CONSTRAINT_WORDS = {
    "cost": "it costs little or nothing", "time": "it takes almost no extra time",
    "schedule": "it fits into something you already do", "forgot": "it has a built-in reminder",
    "energy": "it's an easy version", "environment": "it works around your room or the weather",
    "someone_else": "it works even when someone else is choosing", "equipment": "it needs no equipment",
    "availability": "it works where you usually are",
}
GENERIC_COPING = {
    "time": ("If I'm short on time", "I'll do the smallest version of it"),
    "schedule": ("If my day changes", "I'll do it at the next natural break"),
    "forgot": ("If I forget", "I'll tie it to something I already do every day"),
    "energy": ("If I'm worn out", "a small version still counts"),
    "cost": ("If money is tight this week", "I'll pick the cheapest version"),
    "availability": ("If it isn't there", "I'll pick the closest thing that is"),
    "environment": ("If the weather or my room gets in the way", "I'll do the indoor or quiet version"),
    "someone_else": ("If someone else is choosing", "I'll add my part on the side"),
    "equipment": ("If I don't have what it needs", "I'll do the version that needs nothing"),
}
PATTERN_REASON = {
    "activity.low_weekdays": "you said weekdays are harder to fit movement into",
    "activity.low_weekends": "you said weekends tend to be quieter",
    "sleep.irregular_timing": "you said your bedtime changes a lot",
    "sleep.short_weekdays": "you said you get less sleep before class days",
    "diet.rushed_weekday_breakfast": "you said mornings are rushed on class days",
    "cross.weekday_squeeze": "you said your schedule squeezes your weekdays",
}
REST_DAYS = 14             # "Not for me" / "Didn't fit" rests a step this long
MAX_NEW = 2                # new steps shown at once
MAX_SHOWN = 4              # including the ones they're already trying
_DIGIT = re.compile(r"\d")
REQUIRED = ("id", "domains", "type", "title", "text", "targets", "contexts", "fits", "helps", "anchor", "when_options",
            "bct", "effort", "cost", "needs", "new_time_block", "tags", "log_categories", "grocery", "coping", "source",
            "reviewed")
# Food words in a swap's label, used as its tags: "I don't like it" on the
# yogurt swap also rests other yogurt steps.
FOOD_TAG_WORDS = {
    "yogurt", "milk", "oatmeal", "cereal", "beans", "bean", "nuts", "seeds", "fruit", "berries", "banana", "tuna",
    "tofu", "edamame", "eggs", "egg", "chicken", "turkey", "sausage", "rice", "quinoa", "pasta", "bread", "hummus",
    "salad", "spinach", "broccoli", "tea", "coffee", "latte", "water", "noodles", "potato", "vegetables", "vegetable",
    "fish", "salmon", "chickpea", "lettuce", "tomato",
}


def load_library(path: Path = LIBRARY_PATH) -> Tuple[List[dict], Dict[str, List[str]]]:
    data = json.loads(path.read_text())
    items, grocery_for_swaps = data["items"], data.get("grocery_for_swaps", {})
    seen = set()
    for it in items:
        missing = [k for k in REQUIRED if k not in it]
        if missing:
            raise ValueError(f"twin_library: {it.get('id')} is missing {missing}")
        iid = it["id"]
        if iid in seen or iid in twin_suggest.SWAPS_BY_ID:
            raise ValueError(f"twin_library: duplicate id {iid}")
        seen.add(iid)
        if not it["domains"] or any(d not in DOMAINS for d in it["domains"]):
            raise ValueError(f"twin_library: {iid} has unknown domains {it['domains']}")
        if it["type"] not in TYPES or it["type"] == "swap":
            raise ValueError(f"twin_library: {iid} has unknown type {it['type']}")
        if any(b not in BCT for b in it["bct"]) or not it["bct"]:
            raise ValueError(f"twin_library: {iid} needs known bct codes")
        if any(c not in CONTEXTS for c in it["contexts"]) or not it["contexts"]:
            raise ValueError(f"twin_library: {iid} has unknown contexts")
        if any(w not in WHEN for w in it["when_options"]):
            raise ValueError(f"twin_library: {iid} has unknown when_options")
        if any(h not in CONSTRAINTS for h in it["helps"]):
            raise ValueError(f"twin_library: {iid} has unknown helps")
        if it["effort"] not in EFFORTS or it["cost"] not in COSTS or it["needs"] not in twin_suggest.NEEDS:
            raise ValueError(f"twin_library: {iid} has a bad effort/cost/needs")
        fa = it["targets"].get("focus_areas")
        if fa is not None and any(a not in focus_areas.BY_ID for a in fa):
            raise ValueError(f"twin_library: {iid} names an unknown focus area")
        if "diet" in it["domains"] and fa is None and not it["targets"].get("patterns"):
            raise ValueError(f"twin_library: {iid} is a diet step with neither a focus area nor a pattern")
        for c in it["coping"]:
            if c.get("barrier") not in CONSTRAINTS or not c.get("if") or not c.get("then"):
                raise ValueError(f"twin_library: {iid} has a malformed coping plan")
        shown = [it["title"], it["text"], *it["grocery"], *(c["if"] + " " + c["then"] for c in it["coping"])]
        if any(_DIGIT.search(t) for t in shown):
            raise ValueError(f"twin_library: {iid} text must not contain digits")
        if not it["source"].strip():
            raise ValueError(f"twin_library: {iid} needs a source citation")
    for sid in grocery_for_swaps:
        if sid not in twin_suggest.SWAPS_BY_ID:
            raise ValueError(f"twin_library: grocery_for_swaps names unknown swap {sid}")
    return items, grocery_for_swaps


ITEMS, GROCERY_FOR_SWAPS = load_library()
ITEMS_BY_ID: Dict[str, dict] = {i["id"]: i for i in ITEMS}


def known_step(rec_id: str) -> bool:
    return rec_id in ITEMS_BY_ID or rec_id in twin_suggest.SWAPS_BY_ID


# ---- swaps in the library's shape --------------------------------------------------------------
def swap_tags(label: str) -> List[str]:
    words = re.findall(r"[a-z]+", (label or "").lower())
    return sorted({w for w in words if w in FOOD_TAG_WORDS})


def swap_item(s: dict, regular_key: Optional[str]) -> dict:
    """A From-your-meals suggestion as a library-shaped step. A habit swap
    targets the meal regular it's anchored to (which must be confirmed);
    an area default is general for the focus area."""
    swap = twin_suggest.SWAPS_BY_ID[s["id"]]
    slot = swap.get("slot") or ((s.get("habit") or {}).get("top_slot"))
    when = [slot] if slot in ("lunch", "dinner") else (["morning"] if slot == "breakfast" else [])
    return {
        "id": s["id"], "origin": "swap", "domains": ["diet"], "type": "swap",
        "title": swap["swap_label"], "text": swap["text"],
        "targets": {"patterns": [regular_key] if regular_key else [], "focus_areas": [swap["focus_area"]],
                    "general": regular_key is None},
        "contexts": ["anywhere"], "fits": [], "helps": ["time", "schedule"],
        "anchor": f"your usual {slot}" if slot and slot != "snack" else None, "when_options": when,
        "bct": ["behavior_substitution"], "effort": "low", "cost": "low", "needs": swap["needs"],
        "new_time_block": False, "tags": swap_tags(swap["swap_label"]), "log_categories": swap["log_categories"],
        "grocery": list(GROCERY_FOR_SWAPS.get(s["id"], [])), "coping": [], "source": swap["source"],
        "reviewed": swap["reviewed"],
        # From your meals' own fields, kept for the card
        "habit": s.get("habit"), "evidence": s.get("evidence"), "on_menu_today": s.get("on_menu_today") or [],
        "where": s.get("where"), "model_why": s.get("why"),
    }


# ---- what this participant may be offered at all ----------------------------------------------
def _usable_contexts(state: dict) -> Optional[set]:
    ctx = state.get("contexts")
    if not ctx:
        return None  # unknown setup: don't rule anything out
    gone = {c.split(":", 1)[1] for c in state.get("constraints", set()) if c.startswith("availability:")}
    return {c for c in ctx if c not in gone} | {"anywhere"}


def _not_into(item: dict, state: dict) -> bool:
    nots = {c.split(":", 1)[1] for c in state.get("constraints", set()) if c.startswith("not_into:")}
    return bool(nots & set(item.get("tags") or [])) or f"#{item['id']}" in nots


_NON_FOOD_TAGS = {"walking", "biking", "stairs", "indoor", "stretching", "gym", "class", "breakfast_push"}


def _probe(item: dict) -> dict:
    """What the allergy filter sees: the title, plus every tag and grocery
    item as 'ingredients', plus the log categories (a dairy allergy rules
    out a dairy step). Errs toward hiding, like the rest of the app."""
    return {"name": item["title"], "ingredients": " ".join([*item.get("tags", []), *item.get("grocery", [])]),
            "log_categories": item.get("log_categories") or []}


def safety_ok(item: dict, state: dict, is_blocked: Callable[[dict], bool]) -> Tuple[bool, str]:
    """The checks that apply even to a step they're already trying:
    allergies, dislikes, what they can prepare, a recent safety check-in."""
    if state.get("paused") and ("diet" in item["domains"] or "activity" in item["domains"]):
        return False, "paused"
    if "breakfast_push" in (item.get("tags") or []) and ("not_hungry_early" in state.get("stated", set())
                                                          or state.get("paused")):
        return False, "not_hungry_early"
    if item["needs"] not in state["setup"]["allowed_needs"]:
        return False, "needs"
    # Allergies and food dislikes apply to anything involving food (a food
    # step, or one whose tags, categories or grocery items name a food) — not to "A
    # minute each night to plan tomorrow", whose title happens to contain
    # "nut", or a sleep step for someone who wrote "mornings" in dislikes.
    food = item["domains"] == ["diet"] or item.get("log_categories") or item.get("grocery") \
        or any(t not in _NON_FOOD_TAGS for t in item.get("tags") or [])
    if food and is_blocked(_probe(item)):
        return False, "allergy"
    probe_text = " ".join([item["title"], *item.get("tags", [])])
    if food and twin_suggest._blocked_by_dislikes(probe_text, state["setup"].get("dislikes") or []):
        return False, "dislike"
    if state.get("only_reviewed") and not item.get("reviewed"):
        return False, "not_reviewed"
    return True, ""


def eligible(item: dict, state: dict, is_blocked: Callable[[dict], bool]) -> Tuple[bool, str]:
    """(may it be offered as a NEW step now, why not)."""
    ok, why = safety_ok(item, state, is_blocked)
    if not ok:
        return False, why
    targets = item["targets"]
    area = state.get("focus_area")
    fa = targets.get("focus_areas")
    if fa is not None and area not in fa:
        return False, "focus_area"
    confirmed = state.get("confirmed", {})
    if not any(p in confirmed for p in targets.get("patterns") or []):
        if not targets.get("general"):
            return False, "pattern_not_confirmed"
        for d in item["domains"]:
            if d == "diet":
                if not area:
                    return False, "no_focus_area"
            elif not state.get("domains_on", {}).get(d):
                return False, "domain_not_on"
    usable = _usable_contexts(state)
    if usable is not None and not (set(item["contexts"]) & usable):
        return False, "context"
    cons = state.get("constraints", set())
    if "cost" in cons and item["cost"] == "some":
        return False, "cost"
    if ("time" in cons or "energy" in cons) and item["effort"] == "medium":
        return False, "effort"
    if "schedule" in cons and item["new_time_block"]:
        return False, "schedule"
    if "equipment" in cons and item["needs"] != "none":
        return False, "equipment"
    if _not_into(item, state):
        return False, "not_into"
    plan = (state.get("plans") or {}).get(item["id"]) or {}
    status = plan.get("status")
    if status in ("trying", "adopted"):
        return False, status
    if status in ("dismissed", "didnt_fit", "tried") and _recent(plan.get("day"), state.get("today")):
        return False, "resting"
    return True, ""


def constraint_violations(item: dict, state: dict) -> List[str]:
    """Which of the participant's stated constraints a shown step goes
    against. Used for evaluation (a step they were already trying when they
    named a new constraint shows up here), independent of how the step was
    chosen."""
    out = []
    cons = state.get("constraints", set())
    if "cost" in cons and item.get("cost") == "some":
        out.append("cost")
    if ("time" in cons or "energy" in cons) and item.get("effort") == "medium":
        out.append("time")
    if "schedule" in cons and item.get("new_time_block"):
        out.append("schedule")
    if "equipment" in cons and item.get("needs") != "none":
        out.append("equipment")
    if _not_into(item, state):
        out.append("not_into")
    usable = _usable_contexts(state)
    if usable is not None and not (set(item.get("contexts") or []) & usable):
        out.append("context")
    if "breakfast_push" in (item.get("tags") or []) and "not_hungry_early" in state.get("stated", set()):
        out.append("not_hungry_early")
    return out


def _recent(day: Optional[str], today_iso: Optional[str], days: int = REST_DAYS) -> bool:
    if not day or not today_iso:
        return True
    try:
        return (date.fromisoformat(today_iso) - date.fromisoformat(day)).days < days
    except ValueError:
        return True


# ---- ranking ----------------------------------------------------------------------------------------
def score(item: dict, state: dict) -> Tuple[float, List[tuple]]:
    """(score, factors). Each factor is (code, detail, points) and becomes a
    sentence in the explanation and a column on the researcher page."""
    f: List[tuple] = []
    confirmed = state.get("confirmed", {})
    for p in item["targets"].get("patterns") or []:
        if p in confirmed:
            f.append(("pattern", p, 3 if confirmed[p] == "yes" else 2))
    if len(item["domains"]) > 1 and "cross.weekday_squeeze" in confirmed:
        f.append(("cross", "cross.weekday_squeeze", 2))
    fits = [c for c in item.get("fits") or [] if c in state.get("stated", set())]
    for c in fits[:2]:  # the circumstance a step was designed around (listed first) counts most
        f.append(("fits", c, 2 if c == item["fits"][0] else 1))
    ctx = state.get("contexts") or []
    usable = _usable_contexts(state) or set()
    ranked = [c for c in ctx if c in usable]
    hit = next((c for c in ranked if c in item["contexts"]), None)
    if hit and hit != "campus":
        f.append(("context", hit, 2 if ranked and hit == ranked[0] else 1))
    helps = [c for c in item.get("helps") or [] if c in state.get("constraints", set())]
    for c in helps[:2]:
        f.append(("helps", c, 2))
    hist = state.get("history") or {}
    worked, failed = hist.get("worked_bct") or Counter(), hist.get("failed_bct") or Counter()
    good = [b for b in item["bct"] if worked.get(b)]
    for b in good[:2]:
        f.append(("worked_bct", b, 1))
    bad = [b for b in item["bct"] if failed.get(b) and not worked.get(b)]
    for b in bad[:2]:
        f.append(("failed_bct", b, -1))
    alt = None
    for p in item["targets"].get("patterns") or []:
        for prev_id in (hist.get("failed_targets") or {}).get(p, []):
            prev = lookup(prev_id)
            if prev and prev["id"] != item["id"] and prev["bct"][0] != item["bct"][0]:
                alt = prev_id
                break
        if alt:
            break
    if alt:
        f.append(("alternative", alt, 2))
    # The focus area is the one diet priority that comes from an assessment
    # (ASA24), and a swap anchored to a regular they confirmed is the most
    # personal step there is — both weigh as much as a fitting circumstance.
    if "diet" in item["domains"] and state.get("focus_area") in (item["targets"].get("focus_areas") or []):
        f.append(("focus", state["focus_area"], 2))
    if item.get("origin") == "swap" and item.get("habit"):
        f.append(("habit", item["habit"].get("label"), 2))
    if item.get("on_menu_today") and usable is not None and "dining_hall" in usable:
        m = item["on_menu_today"][0]
        f.append(("menu", f"{m.get('hall_label')} {m.get('period')}", 1))
    if ((state.get("plans") or {}).get(item["id"]) or {}).get("status") == "lapsed":
        f.append(("lapsed", None, 1))
    return float(sum(p for _, _, p in f)), f


def lookup(rec_id: str) -> Optional[dict]:
    """A step by id, library or swap, in the library's shape (swaps without
    their per-day menu fields)."""
    if rec_id in ITEMS_BY_ID:
        return ITEMS_BY_ID[rec_id]
    if rec_id in twin_suggest.SWAPS_BY_ID:
        return swap_item({"id": rec_id}, None)
    return None


def explain(item: dict, factors: List[tuple], state: dict) -> str:
    """One to three short sentences built only from the factors, so the
    participant can see why this step and not another."""
    parts: List[str] = []
    labels = state.get("pattern_labels") or {}
    pats = [d for c, d, _ in factors if c == "pattern"]
    fits = [d for c, d, _ in factors if c == "fits"]
    if pats:
        p = pats[0]
        reason = PATTERN_REASON.get(p) or (f"you said {labels[p][:1].lower()}{labels[p][1:]}" if p in labels else None)
        if reason:
            parts.append(f"Because {reason}.")
    elif any(c == "focus" for c, _, _ in factors):
        parts.append(f"It fits your focus area, {focus_areas.BY_ID[state['focus_area']]['label'].lower()}.")
    alt = next((d for c, d, _ in factors if c == "alternative"), None)
    worked = next((d for c, d, _ in factors if c == "worked_bct"), None)
    if alt and lookup(alt):  # learning from feedback is said right after the main reason
        parts.append(f"It's a different approach from “{lookup(alt)['title']}”, which didn't fit.")
    elif worked:
        parts.append("It uses the same kind of step as one that worked for you.")
    if fits:
        words = twin_patterns.CIRCUMSTANCES.get(fits[0], {}).get("label", "").lower()
        if words:
            parts.append(f"It works around {words}.")
    helps = [d for c, d, _ in factors if c == "helps"]
    ctx = next((d for c, d, _ in factors if c == "context"), None)
    if helps:
        parts.append(f"It fits what you told me: {CONSTRAINT_WORDS[helps[0]]}.")
    elif ctx:
        parts.append(f"It works {CONTEXTS[ctx]}, where you usually are.")
    menu = next((d for c, d, _ in factors if c == "menu"), None)
    if menu and len(parts) < 3:
        parts.append(f"It's on today's menu ({menu}).")
    if any(c == "lapsed" for c, _, _ in factors):
        parts.append("You've done this one before.")
    if not parts and item.get("anchor"):
        parts.append(f"It attaches to {item['anchor']}.")
    return " ".join(parts[:3])


def coping_for(item: dict, state: dict, limit: int = 2) -> List[dict]:
    """If-then plans for the barriers this participant actually named,
    the step's own first, then generic ones; one from the step itself when
    they've named none (coping planning, BCT 1.2)."""
    cons = state.get("constraints", set())
    out: List[dict] = []
    for c in item.get("coping") or []:
        if c["barrier"] in cons:
            out.append({"barrier": c["barrier"], "if": c["if"], "then": c["then"]})
    for c in sorted(cons):
        if c in GENERIC_COPING and not any(o["barrier"] == c for o in out):
            i, t = GENERIC_COPING[c]
            out.append({"barrier": c, "if": i, "then": t})
    if not out and item.get("coping"):
        c = item["coping"][0]
        out.append({"barrier": c["barrier"], "if": c["if"], "then": c["then"]})
    return out[:limit]


def view(item: dict, factors: List[tuple], state: dict, status: Optional[str] = None,
         plan: Optional[dict] = None) -> dict:
    """What the participant's card shows for one step."""
    usable = _usable_contexts(state)
    menu = item.get("on_menu_today") or []
    where = item.get("where")
    if item.get("origin") == "swap" and usable is not None and "dining_hall" not in usable:
        # Not a dining-hall eater: the step is for where they do eat.
        menu = []
        if "grocery" in usable and item.get("grocery"):
            where = "Pick it up next time you shop"
        elif "takeout" in usable or "campus_food" in usable:
            where = "Look for it when you order out"
    return {
        "id": item["id"], "origin": item.get("origin", "library"), "domains": item["domains"],
        "type": item["type"], "type_label": TYPES[item["type"]], "title": item["title"], "text": item["text"],
        "why": explain(item, factors, state) or None, "model_why": item.get("model_why"),
        "evidence": item.get("evidence"),
        "techniques": [BCT[b][0] for b in item["bct"]],
        "when_options": [{"id": w, "label": WHEN[w][0]} for w in item.get("when_options") or []],
        "coping": coping_for(item, state), "grocery": item.get("grocery") or [],
        "on_menu_today": menu, "where": where,
        "status": status, "plan": {k: (plan or {}).get(k) for k in ("when", "coping")} if plan else None,
        "reviewed": item.get("reviewed", False), "source": item["source"],
    }


def select(candidates: List[dict], state: dict, is_blocked: Callable[[dict], bool]) -> dict:
    """The steps to show now: the ones they're trying (pinned, still
    safety-checked), then up to MAX_NEW new ones, preferring different
    domains; plus the steps that worked (to reinforce) and a record of
    every candidate's verdict for the researcher page."""
    plans = state.get("plans") or {}
    trying, fresh, decisions = [], [], []
    seen = set()
    for item in candidates:
        if item["id"] in seen:
            continue
        seen.add(item["id"])
        status = (plans.get(item["id"]) or {}).get("status")
        if status == "trying":
            ok, why = safety_ok(item, state, is_blocked)
            if ok:
                s, f = score(item, state)
                trying.append((s, f, item))
            decisions.append({"id": item["id"], "verdict": "trying" if ok else f"hidden:{why}"})
            continue
        ok, why = eligible(item, state, is_blocked)
        if not ok:
            decisions.append({"id": item["id"], "verdict": f"out:{why}"})
            continue
        s, f = score(item, state)
        fresh.append((s, f, item))
        decisions.append({"id": item["id"], "verdict": "eligible", "score": s})
    fresh.sort(key=lambda t: (-t[0], -len(t[2]["domains"]), t[2]["id"]))
    chosen: List[tuple] = []
    covered = set()
    multi = lambda it: len(it["domains"]) > 1  # noqa: E731
    lane = lambda it: "cross" if multi(it) else it["domains"][0]  # noqa: E731
    for s, f, item in fresh:  # first pass: one step per lane (diet, activity, sleep, across domains)
        if len(chosen) >= MAX_NEW:
            break
        if lane(item) in covered:
            continue
        chosen.append((s, f, item))
        covered.add(lane(item))
    for s, f, item in fresh:  # then fill, still never two cross-domain steps
        if len(chosen) >= MAX_NEW:
            break
        if all(item is not c[2] for c in chosen) and not (multi(item) and any(multi(c[2]) for c in chosen)):
            chosen.append((s, f, item))
    room = max(0, MAX_SHOWN - len(trying))
    shown = [view(i, f, state, "trying", plans.get(i["id"])) for _, f, i in trying] + \
            [view(i, f, state) for _, f, i in chosen[:room]]
    chosen_ids = {i["id"] for _, _, i in chosen[:room]}
    for d in decisions:
        if d["id"] in chosen_ids:
            d["verdict"] = "shown"
    factors = {i["id"]: [list(x) for x in f] for _, f, i in trying + chosen[:room]}
    return {"recommendations": shown, "decisions": decisions, "factors": factors}


def reinforcing(state: dict, today_iso: str) -> List[dict]:
    """Steps that worked for them, to keep going — not removed from view
    just because they succeeded. After a while, a gentle 'still doing it?'."""
    out = []
    for rec_id, plan in (state.get("plans") or {}).items():
        if plan.get("status") != "adopted":
            continue
        item = lookup(rec_id)
        if not item:
            continue
        when = (plan or {}).get("when")
        anchor = WHEN[when][1] if when in WHEN else item.get("anchor")
        msg = "You said this worked. Keep it tied to the same moment each day so it becomes automatic." \
            if not anchor else f"You said this worked. Keep it tied to {anchor} so it becomes automatic."
        due = not _recent(plan.get("checked") or plan.get("day"), today_iso, days=REST_DAYS)
        out.append({"id": rec_id, "title": item["title"], "domains": item["domains"], "message": msg,
                    "check_in": due, "grocery": item.get("grocery") or []})
    out.sort(key=lambda r: r["id"])
    return out[:4]
