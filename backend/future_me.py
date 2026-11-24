"""Future Me — the digital twin. Pure helpers (no database, no LLM).

Future Me reflects the student's OWN data: HEI-2020 focus areas and strengths
from ASA24, their Eat / Move / Sleep logs, rings, My Path, and the rule-based
what-if engine (`simulate_scenario` in server.py). It never shows a number the
engine computes, never combines Eat, Move and Sleep into one score, and every
line it says is either fixed text chosen by a rule or an LLM rewording of a
direction-only result that has passed the guardrail.
"""
import re
from typing import Dict, List, Optional

# One preset behaviour per HEI-2020 component (no digits, so a reworded reply
# can never carry an amount). The simulation runs on the component itself.
COMPONENT_PRESETS: Dict[str, str] = {
    "total_fruits": "Add a piece of fruit at breakfast",
    "whole_fruits": "Choose whole fruit in place of juice",
    "total_vegetables": "Add a vegetable at lunch most days",
    "greens_beans": "Add beans or leafy greens to dinner a few times a week",
    "whole_grains": "Swap in a whole grain at lunch",
    "dairy": "Add yogurt or milk at breakfast",
    "total_protein_foods": "Pair each meal with a protein you like",
    "seafood_plant_proteins": "Have fish, beans or nuts a few times a week",
    "fatty_acids": "Cook with olive oil or add nuts a few times a week",
    "refined_grains": "Swap one white-bread meal for a whole grain",
    "sodium": "Swap one salty snack for fruit or unsalted nuts",
    "added_sugars": "Swap one sweet drink for water",
    "saturated_fats": "Choose grilled over fried now and then",
}

# Move and Sleep have no HEI component; their direction is a fixed rule.
DOMAIN_PRESETS = {
    "move_walk": {"title": "Take a short walk after dinner", "domain": "move",
                  "direction": "A short walk after dinner would move your weekly Move time toward the activity guideline."},
    "sleep_routine": {"title": "Keep a regular bedtime", "domain": "rest",
                      "direction": "A regular bedtime would help your Sleep become steadier from night to night."},
}


def scenarios(focus_ids: List[str], has_assessment: bool) -> List[dict]:
    """3–4 presets: one per chosen focus area (up to 3), topped up with
    Move and Sleep so there are always at least 3."""
    out = []
    if has_assessment:
        for cid in focus_ids[:3]:
            if cid in COMPONENT_PRESETS:
                out.append({"id": f"hei:{cid}", "title": COMPONENT_PRESETS[cid], "domain": "food", "component_id": cid})
    for sid, p in DOMAIN_PRESETS.items():
        if len(out) >= 4 or (len(out) >= 3 and sid == "sleep_routine"):
            break
        out.append({"id": sid, "title": p["title"], "domain": p["domain"], "component_id": None})
    return out


def direction_text(title: str, component_label: str, moves_toward_alignment: bool) -> str:
    """Direction-only wording of the engine's result. Never a number."""
    action = title[:1].lower() + title[1:]
    if moves_toward_alignment:
        return (f"If you {action}, that would move your {component_label} closer to your goal. "
                "Small, steady steps like this add up over time.")
    return f"If you {action}, your {component_label} would stay about where it is. Another small step could help it grow."


_DIGIT = re.compile(r"\d")


def safe_rewording(text: Optional[str], guardrail) -> bool:
    """An LLM rewording is only used if it passes the app guardrail AND has no
    digits at all (the engine's values must never reach a participant)."""
    return bool(text) and not _DIGIT.search(text) and guardrail(text) is None and len(text) <= 400


def week_line(days_logged: int) -> str:
    """Future Me's fixed line about this week, chosen by a simple rule."""
    if days_logged <= 0:
        return "A fresh week. Whatever you log, I'll show you where it's heading."
    if days_logged >= 5:
        return f"You logged on {days_logged} days this week. Steady weeks like this are how you get to me."
    day = "day" if days_logged == 1 else "days"
    return f"You logged on {days_logged} {day} this week. Every day you log brings us a little closer."
