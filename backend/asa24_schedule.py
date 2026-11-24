"""
When each ASA24 recall is due, and which recalls in an uploaded Totals file
belong to which assessment point. Pure functions, no database.

The protocol is six recalls: RECALLS_PER_POINT (two) at each of three
points, one about a weekday and one about a weekend day, in either order.
ASA24 is set to "past 24 hours", so students do each one in the evening.
Points are counted from the day the participant joined the app
(users.created_at):
  - baseline:   week 1, open from day 0
  - check-in 1: week 4, centred on day CHECKIN_INTERVAL_DAYS, then widened
                to a full window (see ``CHECKIN_LEEWAY_BEFORE_DAYS``)
  - check-in 2: week 8, centred on day 2 * CHECKIN_INTERVAL_DAYS, likewise

Nutrition team confirmed on 2026-11-06 that every recall window
(baseline and each check-in) should stay open for ``RECALL_WINDOW_DAYS``.
Any 7 consecutive days contains at least one Saturday AND one Sunday,
which satisfies the one-weekday/one-weekend protocol for recall pairs.
"""
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

# The number of calendar days every recall window stays open for
# (opens_on + RECALL_WINDOW_DAYS == due_by, giving the student seven
# opportunities to submit a recall + the due date itself).
# Confirmed by the nutrition team on 2026-11-06 ("Study Logistics and
# Approvals, Q1") specifically because ASA24 had been offline during
# earlier weeks of the pilot and the previous shorter check-in windows
# left too little slack.
RECALL_WINDOW_DAYS = 7

CHECKIN_INTERVAL_DAYS = 28  # week 4, week 8

# Days of the ``RECALL_WINDOW_DAYS`` window that fall before each check-in
# centre day. 3 days before + 4 days after keeps the check-in roughly
# centred on day 28 / day 56 while still giving every window a full
# weekend regardless of which day the participant joined on.
CHECKIN_LEEWAY_BEFORE_DAYS = 3

# Kept for backwards compatibility with callers that read the old name.
# Equal to ``CHECKIN_LEEWAY_BEFORE_DAYS`` only when the window is
# symmetric; new code should read the two LEEWAY_* constants above.
CHECKIN_LEEWAY_DAYS = CHECKIN_LEEWAY_BEFORE_DAYS

RECALLS_PER_POINT = 2  # one weekday, one weekend day
ASSESSMENT_TYPES = ["baseline", "checkin_1", "checkin_2"]
LABELS = {"baseline": "Baseline", "checkin_1": "Week 4 check-in", "checkin_2": "Week 8 check-in"}


def windows(start: date) -> List[Dict]:
    """Every assessment point's window for a participant who joined on `start`.

    All three windows last ``RECALL_WINDOW_DAYS`` (opens_on → due_by).
    """
    out = [{"assessment_type": "baseline", "label": LABELS["baseline"],
            "opens_on": start, "due_by": start + timedelta(days=RECALL_WINDOW_DAYS)}]
    for k in range(1, len(ASSESSMENT_TYPES)):
        centre = start + timedelta(days=CHECKIN_INTERVAL_DAYS * k)
        opens_on = centre - timedelta(days=CHECKIN_LEEWAY_BEFORE_DAYS)
        t = ASSESSMENT_TYPES[k]
        out.append({"assessment_type": t, "label": LABELS[t],
                    "opens_on": opens_on,
                    "due_by": opens_on + timedelta(days=RECALL_WINDOW_DAYS)})
    return out


def window_for(start: date, assessment_type: str) -> Dict:
    return next(w for w in windows(start) if w["assessment_type"] == assessment_type)


def finished_times(doc: Dict) -> List[str]:
    """When a participant tapped "I finished" for one point, oldest first.
    Rows saved before two recalls per point only have `finished_at`."""
    return list(doc.get("finished_times") or ([doc["finished_at"]] if doc.get("finished_at") else []))


def recall_status(start: date, today: date, finished: Dict[str, List[str]], imported: List[str]) -> Dict:
    """What the participant's recall card should show today.

    `finished` maps assessment_type -> the times they tapped "I finished"
    (one per recall); `imported` lists assessment types the study team has
    scored. Picks the first point that isn't scored yet. A point is
    "finished" once both recalls are done, or once its window closes with at
    least one. A missed window is never shown as a failure: the card just
    moves on to the next point.
    """
    for w in windows(start):
        t = w["assessment_type"]
        if t in imported:
            continue
        times = finished.get(t) or []
        if today > w["due_by"] and not times:
            continue  # window passed without a recall; quietly move on
        if len(times) >= RECALLS_PER_POINT or today > w["due_by"]:
            state = "finished"
        elif today < w["opens_on"]:
            state = "upcoming"
        else:
            state = "open"
        return {**_public(w), "state": state, "finished_at": times[-1] if times else None,
                "recalls_done": min(len(times), RECALLS_PER_POINT), "recalls_needed": RECALLS_PER_POINT,
                "days_until_open": max(0, (w["opens_on"] - today).days),
                "days_until_due": (w["due_by"] - today).days}
    return {"assessment_type": None, "state": "complete"}


def _public(w: Dict) -> Dict:
    return {**w, "opens_on": w["opens_on"].isoformat(), "due_by": w["due_by"].isoformat()}


_DATE_FORMATS = ("%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M", "%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y %I:%M %p",
                 "%m/%d/%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d")


def _parse_dt(raw: Optional[str]) -> Optional[datetime]:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        pass
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def parse_recall_date(raw: Optional[str]) -> Optional[date]:
    """ASA24 exports dates as M/D/YYYY with a time, or ISO; anything else is
    treated as unknown rather than guessed."""
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw).date()
    except ValueError:
        pass
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def recall_date(recall: Dict) -> Optional[date]:
    """When the recall was completed: ReportingDate if the export has it,
    else the intake date (the day being recalled)."""
    return parse_recall_date(recall.get("ReportingDate")) or parse_recall_date(recall.get("IntakeStartDateTime"))


def recall_day(recall: Dict) -> Optional[date]:
    """The day a recall is about. With ASA24's "past 24 hours" setting the
    recall covers the 24 hours before it was done, so it's mostly the day
    it ended on; use the middle of the intake period when the export has
    both ends, else the day it was done."""
    start = _parse_dt(recall.get("IntakeStartDateTime"))
    end = _parse_dt(recall.get("IntakeEndDateTime"))
    if start and end:
        return (start + (end - start) / 2).date()
    return parse_recall_date(recall.get("ReportingDate")) or (start.date() if start else None)


def weekday_weekend_problem(recalls: List[Dict]) -> Optional[str]:
    """A warning when a point's two recalls aren't one weekday and one
    weekend day, or None. Recalls without a usable date aren't judged."""
    days = [d for d in (recall_day(r) for r in recalls) if d]
    if len(days) < RECALLS_PER_POINT:
        return None
    weekend = sum(d.weekday() >= 5 for d in days)
    if weekend == 0:
        return "both recalls are about weekdays"
    if weekend == len(days):
        return "both recalls are about weekend days"
    return None


def split_by_window(recalls: List[Dict], window: Dict) -> Dict[str, List[Dict]]:
    """Recalls completed inside the window, outside it, and with no usable date.
    The window is widened by one day each side: the intake date is the day
    before the recall was done, and time zones can shift a day."""
    lo = window["opens_on"] - timedelta(days=1)
    hi = window["due_by"] + timedelta(days=1)
    out: Dict[str, List[Dict]] = {"inside": [], "outside": [], "undated": []}
    for r in recalls:
        d = recall_date(r)
        if d is None:
            out["undated"].append(r)
        elif lo <= d <= hi:
            out["inside"].append(r)
        else:
            out["outside"].append(r)
    return out


def latest(assessments: List[Dict]) -> Optional[Dict]:
    """The current assessment is the latest point in the study, not the most
    recent upload: re-importing baseline must not replace a check-in."""
    known = [a for a in assessments if a.get("assessment_type") in ASSESSMENT_TYPES]
    if not known:
        return None
    return max(known, key=lambda a: (ASSESSMENT_TYPES.index(a["assessment_type"]), a.get("recorded_at") or ""))
