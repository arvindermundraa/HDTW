"""One source of truth for day / week boundaries, used by every feature
whose "today" or "this week" is a shared study answer.

Why this exists: before this module every feature decided its own "today"
differently — some used UTC, some used the student's stored profile zone,
some used a `?tz=` query param from the phone. Backend and phone could
disagree about the same moment: a Chicago student logging at 11:30 PM saw
the entry on today's rings (phone zone) but on tomorrow's streak (UTC).
Everything that cares about a shared study day/week imports from here.

Timestamps on disk stay in UTC (ISO 8601). Only how they're bucketed into
days / weeks changes. No stored data is rewritten.

Mirrored on the frontend by `frontend/src/study-time.ts` with matching
`studyToday()` / `studyDayKey()`. Change both or neither — a frontend
test keeps them in sync for the DST change on 2026-11-01.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone, date as date_cls
from typing import Optional, Tuple, Union
from zoneinfo import ZoneInfo


# TAMU pilot — all participants are on Central Time. If the study ever
# runs in a second zone, this becomes a per-cohort setting, not per-user.
STUDY_TZ = ZoneInfo("America/Chicago")


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def study_today() -> date_cls:
    """Today's calendar date in the study TZ."""
    return _now_utc().astimezone(STUDY_TZ).date()


def study_week_window(days: int = 7) -> Tuple[date_cls, date_cls]:
    """Rolling N-day window ending today in the study TZ.

    Returns `(first, last)` as calendar dates — not moments. Every "week"
    in this app is a rolling N-day window ending today; there is no fixed
    Mon-Sun boundary. See docs/UI-REDESIGN.md for the open team question
    about turning the cohort "this week" into a true calendar week later.
    """
    last = study_today()
    return last - timedelta(days=days - 1), last


def study_day_key(iso_or_dt: Union[str, datetime]) -> str:
    """YYYY-MM-DD for a stored UTC ISO timestamp (or `datetime`) in the
    study TZ. Replaces every `created_at[:10]` slice: that was silently
    keyed by UTC, so a Chicago late-night log landed on the wrong day."""
    if isinstance(iso_or_dt, str):
        stamp = datetime.fromisoformat(iso_or_dt)
    else:
        stamp = iso_or_dt
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(STUDY_TZ).date().isoformat()


def study_day_start_utc_iso(day: Optional[date_cls] = None) -> str:
    """UTC-encoded moment of 00:00:00 on the given study-TZ day. Use for
    `$gte` lower bounds (DAILY_POINT_CAPS, cohort week, Move weekly, …)
    so the query line up with Chicago midnight, not UTC midnight."""
    day = day or study_today()
    midnight_in_zone = datetime.combine(day, time.min, STUDY_TZ)
    return midnight_in_zone.astimezone(timezone.utc).isoformat()
