"""Week 5 feedback — comparing the Week 4 check-in to baseline.

Nutrition team confirmed on 2026-11-06 (Content of app Q2 /
"Week 5 feedback"):

  "For Week 5, we should use the two new dietary recalls collected
  around Week 4 to generate updated HEI-2020 feedback. We would compare
  these results with the two baseline recalls, using the same scoring
  and weighting approach at both time points. Rather than showing
  numerical changes on the participant-facing dashboard, we could use
  qualitative indicators such as 'Making progress,' 'Similar to where
  you started,' and 'An area to revisit.' These would be based on
  changes in the underlying HEI component scores. Since two recalls at
  each time point cannot fully capture habitual dietary intake, the
  language should be appropriately cautious. Week 5 could then
  encourage participants to reflect on their original focus area,
  recognize progress, and choose whether to continue with it or begin
  addressing another suggested focus area."

Thresholds for "Making progress" and "An area to revisit" are **PROVISIONAL**
(see ``MAKING_PROGRESS_MIN_DELTA_RATIO`` / ``AREA_TO_REVISIT_MIN_DELTA_RATIO``
below). They are a change of 10 percentage points of the area's maximum,
in either direction, per-focus-area. The team is asked to approve them.

No numeric changes are rendered to the student; only one of the three
qualitative labels + a short, cautious prose line.

This is the ENGINE only. The Week 5 screens are a follow-up PR; this
module gives server.py the pure functions it will need when those land.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# --- PROVISIONAL thresholds (nutrition team approval pending) ----------------

#: The change (as a share of the area's maximum points) that counts as
#: "Making progress" between baseline and the Week 4 check-in. 10 points
#: of 100 (i.e. 10 percentage points of the area's maximum) is a common
#: rule of thumb for component-level HEI change in the literature; it is
#: PROVISIONAL and marked for the nutrition team to approve.
MAKING_PROGRESS_MIN_DELTA_RATIO = 0.10

#: Symmetric threshold for "An area to revisit" — a drop of at least this
#: much, again as a share of the area's maximum.
AREA_TO_REVISIT_MIN_DELTA_RATIO = 0.10

LABEL_PROGRESS = "Making progress"
LABEL_SIMILAR = "Similar to where you started"
LABEL_REVISIT = "An area to revisit"

# Cautious prose per label, applying the team's wording rules. "Based on
# the days you reported" explicitly avoids making a statement about the
# student's usual diet.
PROSE = {
    LABEL_PROGRESS: (
        "Based on the days you reported, your {label} score has improved since baseline. "
        "You're making progress. Two recalls can't capture a full picture, so keep the "
        "pattern in mind rather than any single number."
    ),
    LABEL_SIMILAR: (
        "Based on the days you reported, your {label} score is similar to where you started. "
        "Two recalls can't capture a full picture; this doesn't tell us about your usual eating, "
        "but it's worth noting."
    ),
    LABEL_REVISIT: (
        "Based on the days you reported, your {label} score is lower than at baseline. "
        "Progress isn't always consistent — this is one area to revisit. "
        "What might work better for you next time?"
    ),
}


# --- Per-area label -----------------------------------------------------------


def _area_ratio(area_components: List[str], scores: Dict[str, float],
                components_meta: Dict[str, Dict]) -> Optional[float]:
    """``score / max`` for a focus area, summed across its HEI-2020
    components. Returns ``None`` when no component has a score (so the
    label resolves to "similar / insufficient" rather than a spurious
    delta)."""
    have = [c for c in area_components if scores.get(c) is not None]
    if not have:
        return None
    maximum = sum(components_meta[c]["max_score"] for c in have)
    total = sum(scores[c] for c in have)
    return (total / maximum) if maximum else None


def area_label(
    baseline_scores: Dict[str, float],
    week4_scores: Dict[str, float],
    area_components: List[str],
    components_meta: Dict[str, Dict],
    *,
    progress_min_delta: float = MAKING_PROGRESS_MIN_DELTA_RATIO,
    revisit_min_delta: float = AREA_TO_REVISIT_MIN_DELTA_RATIO,
) -> str:
    """Return one of the three team-approved labels for an area, based on
    the change in its combined ``score / max`` ratio between baseline and
    the Week 4 check-in."""
    base = _area_ratio(area_components, baseline_scores, components_meta)
    week4 = _area_ratio(area_components, week4_scores, components_meta)
    if base is None or week4 is None:
        return LABEL_SIMILAR
    delta = week4 - base
    if delta >= progress_min_delta:
        return LABEL_PROGRESS
    if delta <= -revisit_min_delta:
        return LABEL_REVISIT
    return LABEL_SIMILAR


def area_feedback(
    baseline_scores: Dict[str, float],
    week4_scores: Dict[str, float],
    area_components: List[str],
    area_label_name: str,
    components_meta: Dict[str, Dict],
) -> Dict[str, Any]:
    """Full Week 5 feedback payload for one focus area.

    Returned shape::

        {
          "label": "Making progress" | "Similar to where you started" | "An area to revisit",
          "message": "<cautious sentence or two referencing the area label>",
          "thresholds_provisional": True,
        }
    """
    label = area_label(baseline_scores, week4_scores, area_components, components_meta)
    return {
        "label": label,
        "message": PROSE[label].format(label=area_label_name),
        "thresholds_provisional": True,
    }


# --- Week 5 reflection choice ------------------------------------------------

CONTINUE = "continue_same"
CHOOSE_NEW = "choose_new"

REFLECTION_PROMPT = (
    "Where would you like to go next with your focus area?"
)
REFLECTION_OPTIONS = [
    {
        "id": CONTINUE,
        "label": "Continue with {current_label}",
        "subtitle": "Keep the same focus area and refresh your goal or plan.",
    },
    {
        "id": CHOOSE_NEW,
        "label": "Choose a different focus area",
        "subtitle": "Pick another area suggested by your Week 4 results.",
    },
]


def reflection_choice_for(current_area_label: Optional[str]) -> Dict[str, Any]:
    """Shape the Week 5 reflection choice (same focus area, or pick
    another suggested one), with the current area's label inlined so
    the UI can render it as a chip."""
    options = []
    for opt in REFLECTION_OPTIONS:
        label = opt["label"].format(current_label=current_area_label or "your focus area")
        options.append({**opt, "label": label})
    return {"prompt": REFLECTION_PROMPT, "options": options}
