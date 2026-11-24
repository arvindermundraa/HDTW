"""From your own meals — turning what Future Me knows into one small swap.

Inputs (all of them the student's own data):
  * their focus area (chosen after ASA24 results — focus_areas.py),
  * their regulars (twin_habits.detect_habits over their meal logs),
  * their setup (the onboarding profile: kitchen, microwave, meal plan,
    dislikes) and allergy terms,
  * today's real Aggie Dining menus (dining_scraper via server.py's cache).

Output: a short list of suggestions, each anchored to a habit when one
matches ("you usually have whole-milk yogurt at breakfast → low-fat
yogurt") and otherwise an area default that fits their setup ("no
kitchen → oatmeal, microwave or hot water"), with the matching items on
today's menu so the student can go find it.

Every swap comes from content/swaps.json — a reviewable table, like the
Coach's knowledge base — never from the LLM. The LLM (Future Me's chat)
may only reword one of these, through the same guardrail as everything
else. Pure functions only (no database, no network).
"""
import json
import re
from pathlib import Path
from typing import Dict, List, Optional

import focus_areas
import twin_habits

SWAPS_PATH = Path(__file__).parent / "content" / "swaps.json"
REQUIRED = ("id", "focus_area", "habit", "slot", "swap_label", "text", "needs", "log_categories", "dining",
            "dining_exclude", "source", "reviewed")
NEEDS = ("none", "microwave", "stove")
HALL_SHORT = {"sbisa": "Sbisa", "commons": "Commons"}
PERIOD_ORDER = ("breakfast", "lunch", "dinner")
DISMISS_DAYS = 14          # a dismissed swap stays out of the way this long
MAX_SUGGESTIONS = 2
MAX_MENU_MATCHES = 3
_HAS_APPLIANCE = {"shared", "personal"}
_DIGIT = re.compile(r"\d")


def load_swaps(path: Path = SWAPS_PATH) -> List[dict]:
    swaps = json.loads(path.read_text())
    seen = set()
    for s in swaps:
        missing = [k for k in REQUIRED if k not in s]
        if missing:
            raise ValueError(f"swaps.json: {s.get('id')} is missing {missing}")
        if s["focus_area"] not in focus_areas.BY_ID:
            raise ValueError(f"swaps.json: {s['id']} has unknown focus_area {s['focus_area']}")
        if s["habit"] is not None and s["habit"] not in twin_habits.LEXICON_BY_ID:
            raise ValueError(f"swaps.json: {s['id']} names unknown habit {s['habit']}")
        if s["needs"] not in NEEDS:
            raise ValueError(f"swaps.json: {s['id']} has unknown needs {s['needs']}")
        if s["slot"] is not None and s["slot"] not in twin_habits.MEAL_SLOTS:
            raise ValueError(f"swaps.json: {s['id']} has unknown slot {s['slot']}")
        if _DIGIT.search(s["swap_label"]) or _DIGIT.search(s["text"]):
            raise ValueError(f"swaps.json: {s['id']} text must not contain digits")
        if not s["source"].strip():
            raise ValueError(f"swaps.json: {s['id']} needs a source citation")
        if s["id"] in seen:
            raise ValueError(f"swaps.json: duplicate id {s['id']}")
        seen.add(s["id"])
    return swaps


SWAPS: List[dict] = load_swaps()
SWAPS_BY_ID: Dict[str, dict] = {s["id"]: s for s in SWAPS}


# ---- the student's setup --------------------------------------------------
def setup_from_profile(profile: Optional[dict]) -> dict:
    """What the onboarding survey says about where the student can prepare
    food. Unknown (no survey yet) means "don't rule anything out"."""
    profile = profile or {}
    kitchen = profile.get("kitchen_access")  # personal | shared | none | None
    has = lambda key: profile.get(f"appliance_{key}") in _HAS_APPLIANCE  # noqa: E731
    if kitchen == "none":
        # The survey skips the appliance questions without a kitchen. A
        # dorm room usually still has a microwave or a kettle, so
        # microwave-level ideas stay in; anything needing a stove is out.
        allowed = {"none", "microwave"}
        label = "no kitchen"
    elif kitchen in _HAS_APPLIANCE:
        allowed = {"none"}
        if has("microwave") or "appliance_microwave" not in profile:
            allowed.add("microwave")
        if has("stove") or has("hot_plate") or "appliance_stove" not in profile:
            allowed.add("stove")
        label = "a kitchen" if "stove" in allowed else "a kitchen without a stove"
    else:
        allowed = set(NEEDS)
        label = "unknown"
    return {
        "kitchen": kitchen,
        "allowed_needs": allowed,
        "label": label,
        "meal_plan": profile.get("university_meal_plan") == "yes",
        "uses_dining": (profile.get("university_meal_plan") == "yes"
                        or "campus_dining_hall" in (profile.get("food_acquisition") or [])),
        "dislikes": _dislike_terms(profile.get("food_dislikes")),
    }


_DISLIKE_STOP = {
    "and", "the", "any", "all", "not", "but", "with", "really", "dont", "don't", "cant", "can't", "like", "food", "foods",
    "kind", "kinds", "sort", "sorts", "too", "much", "very", "also", "none", "nothing", "n/a", "eat", "eating", "hate",
    "avoid", "stand", "dislike", "strongly", "anything", "everything", "something", "except", "especially", "mostly",
    "most", "some", "only", "just", "that", "this", "them", "they", "things", "stuff", "have", "want", "never", "ever",
    "when", "its", "it's", "cooked", "raw", "kinda", "lot", "lots", "pretty", "quite", "cannot", "wont", "won't",
}


def _dislike_terms(text: Optional[str]) -> List[str]:
    """Food words from "foods you strongly dislike or avoid": lowercased,
    three letters or more, filler removed, plurals folded ("eggs" → "egg")
    so they match either form as whole words."""
    if not text or not isinstance(text, str):
        return []
    words = re.findall(r"[a-z][a-z'-]+", text.lower())
    out = set()
    for w in words:
        w = w.strip("'-")
        if len(w) < 3 or w in _DISLIKE_STOP:
            continue
        out.add(_singular(w))
    return sorted(out)


def _singular(word: str) -> str:
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 4 and word.endswith("es") and word[-3] in "sxzho":
        return word[:-2]  # dishes, boxes, tomatoes, potatoes
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _word_re(phrase: str) -> "re.Pattern":
    """Whole words only, plural tolerated: "milk" never matches "buttermilk",
    "apple" never matches "applewood", "egg" matches "eggs" but not
    "veggie" or "eggplant"."""
    parts = [re.escape(part) for part in re.split(r"[\s-]+", phrase.strip().lower()) if part]
    if not parts:
        return re.compile(r"(?!x)x")  # never matches
    inner = r"[\s-]+".join(parts)
    return re.compile(rf"(?<![a-z0-9]){inner}(?:s|es)?(?![a-z0-9])")


_WORD_RE_CACHE: Dict[str, "re.Pattern"] = {}


def _has_word(text: str, phrase: str) -> bool:
    rx = _WORD_RE_CACHE.get(phrase)
    if rx is None:
        rx = _WORD_RE_CACHE[phrase] = _word_re(phrase)
    return bool(rx.search(text))


# ---- matching today's menus -----------------------------------------------
def _item_text(item: dict) -> str:
    return str(item.get("name") or "").lower()


def menu_matches(swap: dict, menus: Dict[str, Dict[str, dict]], is_blocked, limit: int = MAX_MENU_MATCHES,
                 prefer_period: Optional[str] = None) -> List[dict]:
    """Items on today's menus that are the swap, as {hall, hall_label,
    period, station, item_id, item_name}. `menus` is {hall: {period: menu}}
    in the app's menu shape; `is_blocked(item)` applies the student's
    allergy terms (a recommendation surface, so always filtered).

    Terms match whole words ("milk" is not "Buttermilk Pancakes"). Ranking:
    the meal the swap is for first (`prefer_period`, else the swap's own
    slot), then the other periods in day order; within a period the swap's
    search terms are in priority order (the first group is the best match),
    then menu order. The same dish at several stations is listed once per
    hall and period."""
    first = prefer_period if prefer_period in PERIOD_ORDER else (swap.get("slot") if swap.get("slot") in PERIOD_ORDER else None)
    periods = ([first] if first else []) + [p for p in PERIOD_ORDER if p != first]
    groups = [[t.lower() for t in g] for g in (swap.get("dining") or []) if g]
    excludes = [ex.lower() for ex in (swap.get("dining_exclude") or [])]
    found: List[tuple] = []
    seen = set()
    order = 0
    for p_rank, period in enumerate(periods):
        for hall in ("sbisa", "commons"):
            menu = (menus.get(hall) or {}).get(period)
            if not menu or menu.get("source") != "live":
                continue  # only the real menu — never the demo sample
            for station in menu.get("stations", []):
                for item in station.get("items", []):
                    text = _item_text(item)
                    key = (hall, period, text)
                    if not text or key in seen or any(_has_word(text, ex) for ex in excludes):
                        continue
                    g_rank = next((i for i, g in enumerate(groups) if all(_has_word(text, t) for t in g)), None)
                    if g_rank is None or is_blocked(item):
                        continue
                    seen.add(key)
                    order += 1
                    found.append((p_rank, g_rank, order, {
                        "hall": hall, "hall_label": HALL_SHORT.get(hall, hall), "period": period,
                        "station": station.get("station", ""), "item_id": item.get("id"), "item_name": item.get("name"),
                    }))
    found.sort(key=lambda f: f[:3])
    return [f[3] for f in found[:limit]]


# ---- what this student may be offered at all --------------------------------
def _blocked_by_dislikes(text: str, dislikes: List[str]) -> bool:
    low = (text or "").lower()
    return any(_has_word(low, d) for d in dislikes)


def swap_allowed(swap: dict, focus_area: Optional[str], setup: dict, is_blocked) -> bool:
    """Whether a swap may be shown to, or saved for, this student at all:
    their focus area, something they can prepare, and nothing their
    allergies or dislikes rule out. This is the authorization check behind
    every write (the card's buttons and the Coach's try_swap action), so a
    swap id the model made up — valid in the table but never offered to
    this student — can't get through."""
    if swap["focus_area"] != focus_area or swap["needs"] not in setup["allowed_needs"]:
        return False
    # Allergies are checked against the whole swap, label and text: the
    # nutrition team's labels are often general ("Include seafood or plant
    # protein in a meal") and name the food only in the text. Over-blocking
    # (a "nutrition" mention trips "nut") is the safe direction here.
    # Dislikes stay on the label, so a text that mentions a food only as the
    # thing being replaced doesn't hide the swap.
    probe = {"name": f"{swap['swap_label']} — {swap['text']}", "log_categories": swap["log_categories"]}
    return not (is_blocked(probe) or _blocked_by_dislikes(swap["swap_label"], setup["dislikes"]))


def allowed_swap_ids(focus_area: Optional[str], profile: Optional[dict], is_blocked) -> set:
    setup = setup_from_profile(profile)
    return {s["id"] for s in SWAPS if swap_allowed(s, focus_area, setup, is_blocked)}


# ---- putting it together -----------------------------------------------------
def build_suggestions(focus_area: Optional[str], detected: dict, profile: Optional[dict],
                      menus: Dict[str, Dict[str, dict]], is_blocked, plan_state: Optional[Dict[str, dict]] = None,
                      today_iso: str = "", limit: int = MAX_SUGGESTIONS) -> List[dict]:
    """The suggestions Future Me shows. Habit-anchored swaps first (the
    most-logged habit first), then one area default so there's always
    something concrete even before any regular has shown up. Swaps the
    student dismissed recently are left out; one they're trying is pinned
    first with its status — and stays on the card even once the habit it
    was anchored to has faded from the logs, which is the point.

    `plan_state` is {swap_id: {"status": "trying"|"tried"|"dismissed",
    "day": "YYYY-MM-DD"}} from the student's own taps: "trying" pins the
    swap first, "tried" and "dismissed" rest it for DISMISS_DAYS."""
    if focus_area not in focus_areas.BY_ID:
        return []
    setup = setup_from_profile(profile)
    plan_state = plan_state or {}
    by_habit: Dict[str, List[dict]] = {}
    defaults: List[dict] = []
    for s in SWAPS:
        if s["focus_area"] != focus_area:
            continue
        (by_habit.setdefault(s["habit"], []) if s["habit"] else defaults).append(s)

    ordered: List[tuple] = []  # (habit_or_None, swap)
    if detected.get("status") == "ready":
        for h in detected.get("habits", []):
            for s in by_habit.get(h["food_id"], []):
                ordered.append((h, s))
    for s in defaults:
        ordered.append((None, s))
    # A swap they're trying stays visible whatever the logs say now.
    listed = {s["id"] for _, s in ordered}
    for sid, state in plan_state.items():
        if state.get("status") == "trying" and sid in SWAPS_BY_ID and sid not in listed:
            ordered.append((None, SWAPS_BY_ID[sid]))

    out: List[dict] = []
    used_swaps = set()
    for habit, swap in ordered:
        if swap["id"] in used_swaps:
            continue
        state = plan_state.get(swap["id"]) or {}
        if state.get("status") in ("dismissed", "tried") and _recent(state.get("day"), today_iso):
            continue  # not for them, or already done — give it a rest
        if not swap_allowed(swap, focus_area, setup, is_blocked):
            continue
        prefer = habit["top_slot"] if habit and not swap["slot"] else None
        matches = [m for m in menu_matches(swap, menus, is_blocked, prefer_period=prefer)
                   if not _blocked_by_dislikes(m["item_name"], setup["dislikes"])]
        used_swaps.add(swap["id"])
        out.append({
            "id": swap["id"],
            "kind": "habit_swap" if habit else "focus_add",
            "focus_area": focus_area,
            "habit": ({"food_id": habit["food_id"], "label": habit["label"], "times": habit["times"],
                       "days": habit["days"], "top_slot": habit["top_slot"]} if habit else None),
            "evidence": twin_habits.evidence_line(habit, detected.get("window_days", twin_habits.HABIT_WINDOW_DAYS))
            if habit else None,
            "swap_label": swap["swap_label"],
            "text": swap["text"],
            "slot": swap["slot"],
            "needs": swap["needs"],
            "where": _where_line(swap, matches, setup),
            "on_menu_today": matches,
            "status": "trying" if state.get("status") == "trying" else None,
            "source": swap["source"],
            "reviewed": swap["reviewed"],
        })
    # Anything they're already trying goes first, then habit swaps by how
    # often the habit shows up, then the area default.
    out.sort(key=lambda s: (0 if s["status"] == "trying" else 1,
                            0 if s["kind"] == "habit_swap" else 1,
                            -(s["habit"] or {}).get("times", 0)))
    return out[:limit]


def _recent(day: Optional[str], today_iso: str) -> bool:
    if not day or not today_iso:
        return True
    try:
        from datetime import date
        return (date.fromisoformat(today_iso) - date.fromisoformat(day)).days < DISMISS_DAYS
    except ValueError:
        return True


def _where_line(swap: dict, matches: List[dict], setup: dict) -> str:
    """One short line on where this fits in the student's day."""
    if matches:
        m = matches[0]
        return f"On today's {m['period']} menu at {m['hall_label']} ({m['station']})"
    if swap["needs"] == "none":
        return "No kitchen needed"
    if swap["needs"] == "microwave":
        return "A microwave is enough"
    return "Needs a stove"


def coach_lines(suggestions: List[dict], setup: dict) -> List[str]:
    """Lines for the Coach's THEIR CONTEXT block, so Future Me can bring the
    swap up in conversation and point at today's menu. The swap id is
    included so the model can propose a try_swap action on it."""
    lines = [f"- Their setup: {setup['label']}"
             + (", on a university meal plan" if setup["meal_plan"] else "")]
    for s in suggestions:
        anchor = f"they usually have {s['habit']['label']}" if s["habit"] else "an easy add for their focus area"
        lines.append(f"- A swap that fits ({anchor}; swap_id={s['id']}): {s['swap_label']} — {s['text']}")
        if s["on_menu_today"]:
            where = "; ".join(f"{m['item_name']} ({m['hall_label']}, {m['period']}, {m['station']})"
                              for m in s["on_menu_today"])
            lines.append(f"  On today's Aggie Dining menu: {where}")
        if s["status"] == "trying":
            lines.append("  (they already said they'd try this one)")
    return lines
