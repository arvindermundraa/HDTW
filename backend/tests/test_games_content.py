"""Rule check: no gram/calorie/nutrient-maths text in games.json.

The non-negotiable design rules say "no calories, weight or grams" in any
participant-facing text. Game and daily-challenge content is participant-
facing. This test fails if any user-facing string in `backend/content/
games.json` contains "calorie" / "kcal" / a digit followed by 'g' / "grams".

Keep the forbidden-pattern list in step with the design brief. When a new
forbidden unit is agreed by the team (e.g. "mg" of sodium), add it here
first — the test should fail before the content does.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


GAMES_FILE = Path(__file__).resolve().parent.parent / "content" / "games.json"

# Each pattern must be a compiled regex; the label is used only for error text.
# `\d+mg\b` is listed separately from `\d+g\b` because `\d+g\b` won't match
# "1200mg" (the digits are followed by 'm', not 'g') — milligrams would slip
# through otherwise, and sodium / calcium nutrient-mass units are just as
# off-limits as grams.
FORBIDDEN = [
    (re.compile(r"calorie", re.IGNORECASE), "'calorie'"),
    (re.compile(r"kcal", re.IGNORECASE), "'kcal'"),
    (re.compile(r"\d+mg\b", re.IGNORECASE), "a number immediately followed by 'mg' (nutrient mass)"),
    (re.compile(r"\d+g\b", re.IGNORECASE), "a number immediately followed by 'g' (nutrient weight)"),
    (re.compile(r"grams", re.IGNORECASE), "'grams'"),
]

# User-facing text fields in the games.json data model. Anything NOT in this
# set is internal (ids, markers, type, flags, _comment keys) and never shown
# to the participant, so it is skipped by design.
USER_FACING_FIELDS = {"title", "intro", "rehearses", "prompt", "text", "feedback"}


def _iter_user_facing_text(data):
    """Yield (path, text) for every user-facing string in games.json."""
    def walk(prefix, obj):
        if isinstance(obj, dict):
            for key, value in obj.items():
                if isinstance(value, str) and key in USER_FACING_FIELDS:
                    yield f"{prefix}.{key}", value
                elif isinstance(value, (dict, list)):
                    yield from walk(f"{prefix}.{key}", value)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                yield from walk(f"{prefix}[{i}]", item)
    yield from walk("games.json", data)


def test_games_content_file_loads():
    assert GAMES_FILE.exists(), f"missing content file: {GAMES_FILE}"
    with GAMES_FILE.open() as fh:
        data = json.load(fh)
    assert "games" in data and "daily_challenges" in data


def test_no_grams_calories_or_kcal_in_user_facing_text():
    """No participant-facing text in games.json may contain gram/calorie
    nutrient maths. Educational label-reading practice must use food groups,
    plate balance and ingredient order instead of numeric nutrient units."""
    with GAMES_FILE.open() as fh:
        data = json.load(fh)

    violations = []
    for path, text in _iter_user_facing_text(data):
        for pattern, label in FORBIDDEN:
            match = pattern.search(text)
            if match:
                violations.append(
                    f"{path}: contains {label} — matched {match.group(0)!r} in: {text!r}"
                )

    assert not violations, (
        "games.json contains forbidden gram/calorie/nutrient-maths text:\n  "
        + "\n  ".join(violations)
    )


def test_scanner_actually_catches_each_forbidden_pattern():
    """The scanner above would be useless if its regexes were broken. This
    sanity-check feeds it a crafted blob that trips every pattern — a
    regression here is a sign the regex list drifted from the design rule.
    """
    probe = {
        "games": [
            {
                "id": "probe",
                "title": "probe",
                "rounds": [
                    {
                        "id": "r1",
                        "title": "r",
                        "scenarios": [
                            {
                                "id": "s1",
                                "prompt": "This has 12g of sugar.",
                                "choices": [
                                    {"id": "a", "text": "150 calories here"},
                                    {"id": "b", "text": "nothing bad"},
                                ],
                            },
                            {
                                "id": "s2",
                                "prompt": "kcal check",
                                "choices": [
                                    {"id": "a", "text": "has grams"},
                                    {"id": "b", "text": "contains 1200mg sodium"},
                                ],
                            },
                        ],
                    }
                ],
            }
        ],
        "daily_challenges": {"pool": []},
    }
    hits = []
    for path, text in _iter_user_facing_text(probe):
        for pattern, label in FORBIDDEN:
            if pattern.search(text):
                hits.append(label)
    # Each of the four forbidden patterns is tripped at least once by the probe.
    for _, label in FORBIDDEN:
        assert label in hits, f"regex for {label} did not match the probe text"
