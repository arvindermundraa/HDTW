"""Weekly Wing challenge helpers.

Picks ONE challenge per study week for every Wing. Deterministic (never
random) and shared cohort-wide — Wing A and Wing B see the same challenge
on 2026-10-26, regardless of when either Wing was created.

The content lives in ``backend/content/wing_challenges.json`` so the
nutrition / UX team can edit titles and targets without a code change.
If the pool is empty, callers get ``None`` and the UI quietly hides the
challenge card.

Pure functions here (no DB, no FastAPI). ``server.py`` does the Wing
progress math and plugs the result in.
"""
from __future__ import annotations

import json
from datetime import date as date_cls, datetime, timezone
from pathlib import Path
from typing import Optional


_CONTENT_PATH = Path(__file__).resolve().parent / "content" / "wing_challenges.json"


def _load_pool() -> list[dict]:
    try:
        with _CONTENT_PATH.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return []
    pool = data.get("challenges") or []
    # Shape-guard so a bad edit can't crash the Wings screen; callers rely on
    # these fields being present.
    valid = []
    for c in pool:
        if not isinstance(c, dict):
            continue
        if not all(c.get(k) for k in ("id", "title", "description", "metric", "unit")):
            continue
        if not isinstance(c.get("target"), (int, float)):
            continue
        valid.append(c)
    return valid


# Module-level cache — content changes require a restart (matches the
# `_GAMES_CONTENT` convention already used in server.py).
_POOL = _load_pool()


def _epoch_study_week(d: date_cls) -> int:
    """A deterministic, cohort-wide week number.

    Uses the ISO calendar's week counter anchored at 1970-01-05 (the first
    Monday of the Unix epoch), so every Wing sees the same challenge on the
    same calendar week — regardless of signup date, cohort or season.
    """
    anchor = date_cls(1970, 1, 5)  # Monday
    return (d - anchor).days // 7


def challenge_for_week(week_date: date_cls, pool: Optional[list[dict]] = None) -> Optional[dict]:
    """The challenge every Wing sees for the study week containing
    ``week_date``. Returns ``None`` when the pool is empty.

    Deterministic: ``challenge_for_week(d)`` is a pure function of the
    week index — same input, same output, every run.
    """
    p = _POOL if pool is None else pool
    if not p:
        return None
    week = _epoch_study_week(week_date)
    return p[week % len(p)]


def challenge_week_window(week_date: date_cls) -> tuple[date_cls, date_cls]:
    """``[monday, sunday]`` calendar window of the week containing
    ``week_date``. Used by the server to count a Wing's combined progress
    toward the current challenge."""
    monday = week_date - __import__("datetime").timedelta(days=week_date.weekday())
    sunday = monday + __import__("datetime").timedelta(days=6)
    return monday, sunday


# Preset Wing cheers. Fixed list, never user-authored — see server.py's
# `/wings/cheer` endpoint. Keys are stable; the frontend reads the labels.
CHEER_PRESETS: list[dict] = [
    {"key": "nice_work",   "label": "Nice work, Wing"},
    {"key": "keep_going",  "label": "Keep going"},
    {"key": "proud_of_us", "label": "Proud of us"},
]
CHEER_KEYS = {c["key"] for c in CHEER_PRESETS}


def ingest_pool_for_tests(pool: list[dict]) -> None:
    """Test hook: let tests substitute a tiny pool without touching the file."""
    global _POOL
    _POOL = list(pool)


def refresh_pool() -> int:
    """Reload the content file (restart-equivalent). Returns the pool size."""
    global _POOL
    _POOL = _load_pool()
    return len(_POOL)
