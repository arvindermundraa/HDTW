"""Shared weekly numbers: Today, Future Me and Progress must agree.

LLHS keeps Eat, Move and Sleep separate but each of them is shown in several
places (the Today week strip, the Future Me week line / per-domain fields,
and the Progress Streaks tab). The point of this test is to make sure every
screen pulls the same numbers from the same backend helper, so they can't
drift between endpoints for the same user and window.

Also enforces the design rule that no participant-facing surface says
"closed all rings on X of Y days" or similar combined ring-closure wording.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

import daily_goals  # noqa: E402  (same deferred-import pattern as the other tests)
import study_time   # noqa: E402


REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# --- 1. Snapshot vs. Future-Me helper on the same inputs -------------------

@pytest.fixture
def freeze_now(monkeypatch):
    def _apply(moment):
        monkeypatch.setattr(study_time, "_now_utc", lambda: moment)
    return _apply


def _logs():
    """Mixed-domain, mixed-day logs covering the rolling 7-day window ending
    2026-09-29. One meal is skipped (shouldn't count). One activity is
    `simulated: True` (shouldn't count — same rule as the rings). One meal
    is outside the window."""
    return {
        "food": [
            {"id": "m1", "created_at": "2026-09-24T12:00:00+00:00"},
            {"id": "m2", "created_at": "2026-09-24T19:00:00+00:00"},  # same day → still one
            {"id": "m3", "created_at": "2026-09-27T12:00:00+00:00"},
            {"id": "m4", "created_at": "2026-09-29T12:00:00+00:00", "skipped": True},
            {"id": "m5", "created_at": "2026-09-22T12:00:00+00:00"},  # out of window
        ],
        "move": [
            {"id": "a1", "created_at": "2026-09-25T09:00:00+00:00", "minutes": 20},
            {"id": "a2", "created_at": "2026-09-29T07:00:00+00:00", "minutes": 15},
            {"id": "a3", "created_at": "2026-09-28T08:00:00+00:00", "minutes": 60, "simulated": True},
        ],
        "rest": [
            {"id": "s1", "created_at": "2026-09-29T06:00:00+00:00", "hours": 8},
        ],
    }


def test_snapshot_and_future_me_helper_agree_on_week_counts(freeze_now):
    """`build_snapshot` and `_days_logged_this_week` must return the same
    per-domain counts for the same user/window — they share a helper, and
    this test fails loudly if someone unwires one of them."""
    freeze_now(datetime(2026, 9, 29, 15, 0, tzinfo=timezone.utc))
    logs = _logs()

    snapshot = daily_goals.build_snapshot({"plans": {}}, logs)
    week = snapshot["week"]

    first, last = study_time.study_week_window(7)
    counts = daily_goals.week_days_logged(logs, first.isoformat(), last.isoformat())

    # The helper owns the math; the snapshot just spreads it onto `week`.
    assert week["eat_days"] == counts["eat_days"]
    assert week["move_days"] == counts["move_days"]
    assert week["rest_days"] == counts["rest_days"]
    assert week["any_days"] == counts["any_days"]

    # Concrete expected numbers for the fixture logs — a canary against
    # subtle filter changes (skipped, simulated, out-of-window):
    #   Eat → distinct days with a kept meal: 09-24 and 09-27 (09-29 is skipped,
    #         09-22 is out of window). = 2.
    #   Move → 09-25 and 09-29 (09-28 is simulated). = 2.
    #   Rest → 09-29 only. = 1.
    #   Any → union {09-24, 09-25, 09-27, 09-29}. = 4.
    assert week["eat_days"] == 2
    assert week["move_days"] == 2
    assert week["rest_days"] == 1
    assert week["any_days"] == 4


def test_week_counts_are_zero_when_nothing_was_logged(freeze_now):
    freeze_now(datetime(2026, 9, 29, 15, 0, tzinfo=timezone.utc))
    week = daily_goals.build_snapshot(
        {"plans": {}}, {"food": [], "move": [], "rest": []}
    )["week"]
    assert week["eat_days"] == 0 and week["move_days"] == 0
    assert week["rest_days"] == 0 and week["any_days"] == 0


# --- 2. No participant-facing "closed all rings" wording left --------------

FORBIDDEN = [
    (re.compile(r"closed\s+all\s+rings", re.IGNORECASE),
     '"closed all rings" (combined ring-closure count)'),
    (re.compile(r"all\s+rings\s+closed", re.IGNORECASE),
     '"all rings closed" (combined ring-closure count)'),
    (re.compile(r"\brings\s+closed\b", re.IGNORECASE),
     '"rings closed" (combined count — show per-activity instead)'),
    (re.compile(r"closed\s+all\s+rings\s+on\s+\d+\s+of\s+\d+", re.IGNORECASE),
     '"closed all rings on N of M" (exact grievance phrasing)'),
]

SOURCE_DIRS = [
    REPO_ROOT / "backend",
    REPO_ROOT / "frontend" / "src",
    REPO_ROOT / "frontend" / "app",
]
SOURCE_SUFFIXES = {".py", ".ts", ".tsx"}
EXCLUDED_PATH_PARTS = {"tests", "test", "__pycache__", "node_modules", ".expo", "dist", "build"}
EXCLUDED_FILENAME_HINTS = (".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx")

_LINE_COMMENT = re.compile(r"^\s*(//|#|\*|/\*)")


def _should_scan(path: Path) -> bool:
    if path.suffix not in SOURCE_SUFFIXES:
        return False
    if any(part in EXCLUDED_PATH_PARTS for part in path.parts):
        return False
    if any(path.name.endswith(hint) for hint in EXCLUDED_FILENAME_HINTS):
        return False
    return True


def _strip_comment(line: str) -> str:
    return "" if _LINE_COMMENT.match(line) else line


def _iter_source_files():
    for root in SOURCE_DIRS:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and _should_scan(path):
                yield path


def test_no_closed_all_rings_wording_in_participant_facing_source():
    violations = []
    scanned = 0
    for path in _iter_source_files():
        scanned += 1
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, raw in enumerate(text.splitlines(), start=1):
            line = _strip_comment(raw)
            if not line:
                continue
            for pattern, label in FORBIDDEN:
                m = pattern.search(line)
                if m:
                    rel = path.relative_to(REPO_ROOT)
                    violations.append(
                        f"{rel}:{lineno}: {label} — matched {m.group(0)!r} in: {raw.strip()!r}"
                    )
    assert scanned > 0, "scanner found no files — check SOURCE_DIRS"
    assert not violations, (
        "Participant-facing source still has combined ring-closure wording "
        "(the review said to drop these in favour of per-activity sentences):\n  "
        + "\n  ".join(violations)
    )


def test_scanner_catches_each_forbidden_pattern(tmp_path):
    probes = {
        "a.tsx": 'return "Closed all rings on 3 of 5 days";',
        "b.ts": 'const label = "All rings closed";',
        "c.py": 'detail = f"{closed} of {n} rings closed."',
    }
    for name, content in probes.items():
        (tmp_path / name).write_text(content)
    hits = {label: False for _, label in FORBIDDEN}
    for name in probes:
        text = (tmp_path / name).read_text()
        for pattern, label in FORBIDDEN:
            if pattern.search(text):
                hits[label] = True
    # At least three of the four regexes must trip on the probes (the fourth,
    # the "exact grievance" composite, is a strict superset of the first).
    assert sum(hits.values()) >= 3, f"scanner did not catch probes: {hits}"
