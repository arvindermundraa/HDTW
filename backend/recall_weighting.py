"""5:2 weekday/weekend weighting for ASA24 recalls, applied to the
underlying dietary intake variables BEFORE HEI-2020 scoring.

Nutrition team confirmed on 2026-11-06 (Scoring and Feedback, Q1):

  "I agree that 5:2 weighting is a reasonable approach to representing
  dietary intake across a typical week … However, it is important to
  apply the weighting to the underlying dietary intake variables before
  calculating HEI-2020 component scores, rather than averaging the
  HEI scores from the two recalls. This is consistent with NCI guidance
  on calculating person-level HEI scores from multiple recalls. I
  suggest provisionally using 5:2 weighting for the baseline dashboard,
  with equal-day pooling as a sensitivity analysis."

Day classification (nutrition team answers, 2026-11-12):

  1. ``IntakeStartDateTime`` is the eating day; use its date as-is.
  2. If it is missing, use ``ReportingDate`` minus one day, because
     ASA24 recalls cover the previous day (midnight to midnight).
  3. If that is also missing, use ``finished_at`` minus one day, after
     converting ``finished_at`` from UTC to America/Chicago (the study
     clock).
  4. Weekend = Saturday and Sunday; weekday = Monday to Friday.
  5. For every recall we store the derived eating date, the day type,
     and which source the date came from — written to the hei_assessments
     document on import so research can audit it later.
  6. If a time point does not have ONE weekday AND ONE weekend recall
     (two weekdays, two weekend days, or a single recall), the 5:2
     weight is not applied for that person / time point. Equal-day
     pooling is used instead, flagged with ``weighting_fallback`` and
     a reason; the research export and the staff comparison report
     include the flag.

Pure functions; no database access.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import asa24_schedule
import hei2020_scoring


STUDY_TZ = ZoneInfo("America/Chicago")

# Nutrition team 2026-11-06 — 5 weekday recalls + 2 weekend recalls =
# 7 days of typical-week intake. Used only when a time point has one of
# each; see FALLBACK_REASONS below for the branches that fall back to
# equal pooling.
WEEKDAY_WEIGHT = 5
WEEKEND_WEIGHT = 2

DAY_SOURCE_INTAKE = "intake_start_datetime"
DAY_SOURCE_REPORTING_MINUS_ONE = "reporting_date_minus_one"
DAY_SOURCE_FINISHED_MINUS_ONE = "finished_at_study_tz_minus_one"
DAY_SOURCE_UNKNOWN = "unknown"

DAY_TYPE_WEEKDAY = "weekday"
DAY_TYPE_WEEKEND = "weekend"

FALLBACK_REASON_TWO_WEEKDAYS = "two weekday recalls"
FALLBACK_REASON_TWO_WEEKENDS = "two weekend recalls"
FALLBACK_REASON_INSUFFICIENT_RECALLS = "fewer than two recalls"
FALLBACK_REASON_UNDATED = "one or more recalls with no usable date"

METHOD_WEIGHTED = "weighted_5_2_by_day_type"
METHOD_EQUAL = "equal_day_pooling"


# --- day classification -------------------------------------------------------


def _parse_dt(raw: Optional[str]) -> Optional[datetime]:
    """Tolerant timestamp parser mirroring ``asa24_schedule._parse_dt``."""
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        pass
    for fmt in ("%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M", "%m/%d/%Y %I:%M:%S %p",
                "%m/%d/%Y %I:%M %p", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def _finished_at_eating_date(raw: Optional[str]) -> Optional[date]:
    """Convert ``finished_at`` (stored as UTC ISO) to the study-TZ date
    MINUS one day. The minus-one-day rule mirrors ASA24's "past 24 hours"
    mode: a student who hits Finish Tuesday evening is reporting what
    they ate on Monday."""
    dt = _parse_dt(raw)
    if dt is None:
        return None
    # Naive timestamps are assumed to be UTC — same assumption the rest
    # of the codebase makes when it writes ``.isoformat()`` on
    # ``datetime.utcnow()``.
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    local = dt.astimezone(STUDY_TZ)
    return local.date() - timedelta(days=1)


def _reporting_date_minus_one(raw: Optional[str]) -> Optional[date]:
    dt = _parse_dt(raw)
    if dt is None:
        return None
    return dt.date() - timedelta(days=1)


def classify_recall_day(recall: Dict[str, Any]) -> Dict[str, Any]:
    """Return ``{"eating_date", "day_type", "source"}`` for one recall,
    following the four-step precedence above.

    * ``eating_date`` is a ``date`` (or ``None`` if nothing is usable).
    * ``day_type`` is ``"weekday"`` / ``"weekend"`` (or ``None``).
    * ``source`` is one of the ``DAY_SOURCE_*`` constants.
    """
    # 1. IntakeStartDateTime is the eating day; use its date as-is.
    intake = _parse_dt(recall.get("IntakeStartDateTime"))
    if intake is not None:
        d = intake.date()
        return _result(d, DAY_SOURCE_INTAKE)
    # 2. ReportingDate minus one day — ASA24 covers the prior day.
    d = _reporting_date_minus_one(recall.get("ReportingDate"))
    if d is not None:
        return _result(d, DAY_SOURCE_REPORTING_MINUS_ONE)
    # 3. finished_at converted to the study clock, minus one day.
    d = _finished_at_eating_date(recall.get("finished_at"))
    if d is not None:
        return _result(d, DAY_SOURCE_FINISHED_MINUS_ONE)
    # 4. Nothing usable.
    return {"eating_date": None, "day_type": None, "source": DAY_SOURCE_UNKNOWN}


def _result(d: date, source: str) -> Dict[str, Any]:
    day_type = DAY_TYPE_WEEKEND if d.weekday() >= 5 else DAY_TYPE_WEEKDAY
    return {"eating_date": d, "day_type": day_type, "source": source}


# --- weighted vs equal-day pooling --------------------------------------------


def _weighted_sum(rows: List[Dict[str, float]], weights: List[int]) -> Dict[str, float]:
    """Weighted per-variable sum of the ``derive_inputs`` output for each
    recall. Returns the same shape ``hei2020_scoring.sum_recalls``
    returns, so ``score_hei2020`` can be called on it directly."""
    totals = {k: 0.0 for k in hei2020_scoring.SUMMED_INPUTS}
    for row, w in zip(rows, weights):
        derived = hei2020_scoring.derive_inputs(row)
        for k in hei2020_scoring.SUMMED_INPUTS:
            totals[k] += derived[k] * w
    return totals


def _fallback_for(classifications: List[Dict[str, Any]]) -> Optional[str]:
    """Return a ``FALLBACK_REASON_*`` constant if 5:2 weighting cannot
    be applied as the team specified; else None (the pair is one of each)."""
    if any(c["day_type"] is None for c in classifications):
        return FALLBACK_REASON_UNDATED
    if len(classifications) < 2:
        return FALLBACK_REASON_INSUFFICIENT_RECALLS
    weekday_count = sum(c["day_type"] == DAY_TYPE_WEEKDAY for c in classifications)
    weekend_count = sum(c["day_type"] == DAY_TYPE_WEEKEND for c in classifications)
    if weekend_count == 0:
        return FALLBACK_REASON_TWO_WEEKDAYS
    if weekday_count == 0:
        return FALLBACK_REASON_TWO_WEEKENDS
    return None


def score_with_weighting(recalls: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Run both scoring methods on a person's recalls and return both
    results plus provenance.

    Returns::

        {
          "primary": {                  # shown to the student
            "method": "weighted_5_2_by_day_type" | "equal_day_pooling",
            "weighting_fallback": None or FALLBACK_REASON_*,
            "scored": score_person-shaped dict,
          },
          "sensitivity": {              # equal-day pooling (research only)
            "method": "equal_day_pooling",
            "scored": score_person-shaped dict,
          },
          "classifications": [
             {"eating_date": "...", "day_type": "...", "source": "..."}, ...
          ],
        }

    Always computes both sides. When 5:2 can't be applied cleanly, the
    primary falls back to equal pooling and carries ``weighting_fallback``
    with the reason; the sensitivity analysis still runs.
    """
    # Equal-day pooling — the pre-existing path, still the sensitivity.
    equal_scored = hei2020_scoring.score_person(recalls) if recalls else {
        "recall_count": 0, "components": {}, "total_score": 0.0, "summed_inputs": {}, "nci_output": {},
    }
    classifications = [classify_recall_day(r) for r in recalls]
    serializable_classifications = [
        {
            "eating_date": c["eating_date"].isoformat() if c["eating_date"] else None,
            "day_type": c["day_type"],
            "source": c["source"],
        }
        for c in classifications
    ]

    fallback_reason = _fallback_for(classifications)
    if fallback_reason or not recalls:
        return {
            "primary": {
                "method": METHOD_EQUAL,
                "weighting_fallback": fallback_reason,
                "scored": equal_scored,
            },
            "sensitivity": {"method": METHOD_EQUAL, "scored": equal_scored},
            "classifications": serializable_classifications,
        }

    # Clean 5:2 — one weekday recall and one weekend recall. Weight each
    # recall by its day type, run NCI's per-person method on the weighted
    # totals.
    weights = [WEEKDAY_WEIGHT if c["day_type"] == DAY_TYPE_WEEKDAY else WEEKEND_WEIGHT
               for c in classifications]
    weighted_totals = _weighted_sum(recalls, weights)
    weighted_nci = hei2020_scoring.score_hei2020(weighted_totals)
    weighted_scored = {
        "recall_count": len(recalls),
        "summed_inputs": {k: round(v, 4) for k, v in weighted_totals.items()},
        "components": hei2020_scoring.component_scores(weighted_nci),
        "total_score": round(weighted_nci["HEI2020_TOTAL_SCORE"], 2),
        "nci_output": {k: (None if v is None else round(float(v), 4)) for k, v in weighted_nci.items()},
    }
    return {
        "primary": {
            "method": METHOD_WEIGHTED,
            "weighting_fallback": None,
            "scored": weighted_scored,
        },
        "sensitivity": {"method": METHOD_EQUAL, "scored": equal_scored},
        "classifications": serializable_classifications,
    }


# --- staff comparison report --------------------------------------------------


def comparison_rows(assessments: List[Dict[str, Any]], component_ids: List[str]) -> List[Dict[str, Any]]:
    """One row per imported assessment that has BOTH a weighted
    ``components`` field and a ``sensitivity`` block, summarising how
    the two methods differ per the fields the team asked us to track:
    total score, strengths change, room-to-grow change.

    ``component_ids`` is the 13 HEI-2020 ids in display order; used to
    pull component scores out of the two methods' outputs.
    """
    import focus_areas  # local import to avoid a cycle at module load time
    rows: List[Dict[str, Any]] = []
    for a in assessments:
        sens = a.get("sensitivity") or {}
        primary_scored = a.get("components") or {}
        sens_scored = (sens.get("scored") or {}).get("components") or {}
        if not primary_scored or not sens_scored:
            continue
        # Use the module-level defaults for strengths/room-to-grow counts,
        # which is the single source of truth per the ranking test.
        components_lookup = {cid: {"max_score": _MAX_BY_ID.get(cid, 10)} for cid in component_ids}
        primary_buckets = focus_areas.strengths_and_room_to_grow(primary_scored, components_lookup)
        sens_buckets = focus_areas.strengths_and_room_to_grow(sens_scored, components_lookup)
        rows.append({
            "user_id": a.get("user_id"),
            "assessment_type": a.get("assessment_type"),
            "recorded_at": a.get("recorded_at"),
            "primary_method": (a.get("scoring_method") or METHOD_WEIGHTED),
            "weighting_fallback": a.get("weighting_fallback"),
            "primary_total": a.get("total_score"),
            "sensitivity_total": (sens.get("scored") or {}).get("total_score"),
            "total_score_difference": _diff(a.get("total_score"), (sens.get("scored") or {}).get("total_score")),
            "strengths_primary": sorted(a["id"] for a in primary_buckets["strengths"]),
            "strengths_sensitivity": sorted(a["id"] for a in sens_buckets["strengths"]),
            "strengths_changed": sorted(a["id"] for a in primary_buckets["strengths"]) !=
                                 sorted(a["id"] for a in sens_buckets["strengths"]),
            "room_to_grow_primary": sorted(a["id"] for a in primary_buckets["room_to_grow"]),
            "room_to_grow_sensitivity": sorted(a["id"] for a in sens_buckets["room_to_grow"]),
            "room_to_grow_changed": sorted(a["id"] for a in primary_buckets["room_to_grow"]) !=
                                     sorted(a["id"] for a in sens_buckets["room_to_grow"]),
        })
    return rows


def _diff(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None:
        return None
    return round(float(a) - float(b), 2)


# Populated at module load so the comparison report doesn't need to drag
# the full HEI2020_COMPONENTS list through its signature.
_MAX_BY_ID: Dict[str, int] = {}


def register_component_maxes(components: List[Dict[str, Any]]) -> None:
    """Called once from ``server.py`` after ``HEI2020_COMPONENTS`` is
    defined so the comparison helper can look up each component's
    ``max_score`` without taking a dependency on ``server``."""
    _MAX_BY_ID.clear()
    _MAX_BY_ID.update({c["id"]: c["max_score"] for c in components})
