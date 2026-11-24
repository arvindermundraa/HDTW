"""
The staff page's "Download scores (CSV)": every imported HEI-2020 assessment,
one row per participant per assessment point, for analysis in R or Excel.
Pure function; the route lives in server.py.

Columns: who (name, email, ASA24 username, test account), which point, the
13 component scores and the total, how many recalls were combined and their
dates, the upload warnings, and the summed food-group amounts the scores were
computed from (input_*), so the scoring can be checked independently.

Also exports the equal-day-pooling sensitivity analysis the nutrition team
asked for on 2026-11-06 (Scoring and Feedback Q1): the primary columns above
show the 5:2-weighted scores the student sees (or equal-day pooling when a
``weighting_fallback`` reason applies); a second set of columns prefixed
``sensitivity_`` shows the equal-day-pooling scores for every assessment,
and ``scoring_method`` / ``weighting_fallback`` record which branch was taken.
"""
import csv
import io
from typing import Dict, List

LEAD = ["name", "email", "asa24_username", "is_test_account", "assessment_type", "assessment_label",
        "recorded_at", "recall_count", "recall_dates"]
TAIL = ["warnings", "imported_by"]
METHOD = ["scoring_method", "weighting_fallback"]


def scores_csv(users: Dict[str, Dict], links: Dict[str, str], assessments: List[Dict],
               component_ids: List[str], labels: Dict[str, str], point_order: List[str],
               include_test: bool = False) -> str:
    """`users` and `links` are keyed by user id; `assessments` are
    hei_assessments rows. Rows are sorted by participant, then study point.

    Test accounts (``is_test_account == True`` — e.g. the Lab Test Wing used
    for pre-launch rehearsals) are **excluded by default** so analysis
    counts never silently absorb lab-rehearsal data. Set
    ``include_test=True`` to opt them back in."""
    if not include_test:
        test_ids = {uid for uid, u in users.items() if u.get("is_test_account")}
        assessments = [a for a in assessments if a.get("user_id") not in test_ids]
    input_keys = sorted({k for a in assessments for k in (a.get("summed_inputs") or {})})
    sens_component_cols = [f"sensitivity_{c}" for c in component_ids]
    header = (LEAD + component_ids + ["total_score"]
              + METHOD
              + sens_component_cols + ["sensitivity_total_score"]
              + TAIL + [f"input_{k}" for k in input_keys])

    def order(a):
        u = users.get(a["user_id"], {})
        t = a.get("assessment_type")
        return ((u.get("name") or "").lower(), u.get("email") or "",
                point_order.index(t) if t in point_order else len(point_order), a.get("recorded_at") or "")

    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(header)
    for a in sorted(assessments, key=order):
        u = users.get(a["user_id"], {})
        comps = a.get("components") or {}
        inputs = a.get("summed_inputs") or {}
        t = a.get("assessment_type")
        sens = (a.get("sensitivity") or {}).get("scored") or {}
        sens_comps = sens.get("components") or {}
        w.writerow([u.get("name", ""), u.get("email", ""), links.get(a["user_id"], ""),
                    bool(u.get("is_test_account")), t, labels.get(t, t),
                    a.get("recorded_at", ""), a.get("recall_count", ""), "; ".join(a.get("recall_dates") or [])]
                   + [comps.get(c, "") for c in component_ids] + [a.get("total_score", "")]
                   + [a.get("scoring_method", ""), a.get("weighting_fallback", "") or ""]
                   + [sens_comps.get(c, "") for c in component_ids] + [sens.get("total_score", "")]
                   + ["; ".join(a.get("warnings") or []), a.get("imported_by", "")]
                   + [inputs.get(k, "") for k in input_keys])
    return out.getvalue()


# --- staff weighting comparison report ----------------------------------------

COMPARE_HEADER = [
    "name", "email", "asa24_username", "is_test_account",
    "assessment_type", "assessment_label", "recorded_at",
    "primary_method", "weighting_fallback",
    "primary_total", "sensitivity_total", "total_score_difference",
    "strengths_primary", "strengths_sensitivity", "strengths_changed",
    "room_to_grow_primary", "room_to_grow_sensitivity", "room_to_grow_changed",
]


def weighting_comparison_csv(users: Dict[str, Dict], links: Dict[str, str],
                             comparison_rows: List[Dict], labels: Dict[str, str],
                             include_test: bool = False) -> str:
    """CSV side-by-side of the 5:2-weighted result vs equal-day pooling,
    one row per assessment. Nutrition team 2026-11-06 ("Scoring and
    Feedback" Q1) asked for a staff-only report that tracks how many
    participants' total score, strengths, or room-to-grow areas change
    between the two methods — this is the row-level data behind that.
    ``comparison_rows`` come from ``recall_weighting.comparison_rows``."""
    if not include_test:
        test_ids = {uid for uid, u in users.items() if u.get("is_test_account")}
        comparison_rows = [r for r in comparison_rows if r.get("user_id") not in test_ids]
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(COMPARE_HEADER)
    for r in comparison_rows:
        u = users.get(r.get("user_id"), {})
        t = r.get("assessment_type")
        w.writerow([u.get("name", ""), u.get("email", ""), links.get(r.get("user_id"), ""),
                    bool(u.get("is_test_account")),
                    t, labels.get(t, t), r.get("recorded_at", ""),
                    r.get("primary_method", ""), r.get("weighting_fallback", "") or "",
                    r.get("primary_total", ""), r.get("sensitivity_total", ""),
                    r.get("total_score_difference", ""),
                    "; ".join(r.get("strengths_primary", [])),
                    "; ".join(r.get("strengths_sensitivity", [])),
                    bool(r.get("strengths_changed")),
                    "; ".join(r.get("room_to_grow_primary", [])),
                    "; ".join(r.get("room_to_grow_sensitivity", [])),
                    bool(r.get("room_to_grow_changed"))])
    return out.getvalue()
