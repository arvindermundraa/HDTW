"""Content-rule guard for the weekly workflow content files
(backend/content/weeks/weekN.json).

Rules enforced here reflect the project-wide "no numbers to students
about their own diet" guidance:

* No calories / grams / mg / %DV / HEI score mentions in participant-
  facing strings.
* No "N/M meals" or "meals to go" quota wording (that's test_meal_wording's
  rule; mirrored here so a regression in the content file alone trips
  without having to touch the broader source scan).

The ``WEEK2_LESSON_NUTRIENTS`` allow-list (see
``backend/week2_scenarios.py``) is the single, narrow exception. It only
applies to the ``choices`` of the cafeteria and grocery scenarios in
Week 2 (where nutrient numbers on label-looking cards are the lesson)
AND to the two SAMPLE content files
(``backend/content/week2_dining_menu.json``,
``backend/content/week2_grocery_products.json``) which live OUTSIDE this
test's scan path. Those files hold integer / float nutrient values on
JSON number keys, not inside participant-facing strings — the walker
below only visits strings, so numeric values on JSON number fields
never trip the rules anyway. If someone later tries to inline a
``"saturated_fat: 7g"`` string into week2.json's option labels, this
test will catch it.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


WEEKS_DIR = Path(__file__).resolve().parent.parent / "content" / "weeks"

# Patterns that must not appear in participant-facing strings in any
# weekN.json. The patterns are intentionally lenient on surrounding
# punctuation so a stringified template interpolation can't sneak past.
FORBIDDEN = [
    (re.compile(r"\b\d+\s*calorie", re.IGNORECASE), "calories mentioned to students"),
    (re.compile(r"\b\d+\s*(?:g|mg)\b"), "grams or milligrams mentioned to students"),
    (re.compile(r"\b\d+\s*%\s*DV\b", re.IGNORECASE), "%DV mentioned to students"),
    (re.compile(r"\bHEI\s*(?:score|total)\b", re.IGNORECASE), "HEI score mentioned to students"),
    (re.compile(r"\d+\s*/\s*\d+\s*meals?\b", re.IGNORECASE), '"N/M meals" quota wording'),
    (re.compile(r"\bmeals?\s+to\s+go\b", re.IGNORECASE), '"meal(s) to go" quota wording'),
]

# Keys inside the JSON that are internal metadata — not shown to
# students — and therefore skipped by the scan.
NON_PARTICIPANT_KEYS = {"_comment", "id", "type", "video_id", "captions_url", "data_source", "completion_rule",
                        "route", "sequence", "steps", "label", "variant_by_focus_kind", "video_id_by_area",
                        "captions_url_by_area", "cta_next_label", "phases", "key"}


def _iter_week_files():
    files = sorted(WEEKS_DIR.glob("week*.json"))
    assert files, "No weekN.json content files found."
    for p in files:
        yield p


def _walk_strings(node, *, parent_key=""):
    """Yield every string value under ``node`` that would be shown to a
    participant. Keys in :data:`NON_PARTICIPANT_KEYS` are skipped so an
    internal id like ``"type": "video"`` isn't scanned."""
    if isinstance(node, str) and parent_key not in NON_PARTICIPANT_KEYS:
        yield parent_key, node
    elif isinstance(node, dict):
        for k, v in node.items():
            yield from _walk_strings(v, parent_key=k)
    elif isinstance(node, list):
        for v in node:
            yield from _walk_strings(v, parent_key=parent_key)


@pytest.mark.parametrize("week_file", list(_iter_week_files()), ids=lambda p: p.name)
def test_no_numeric_health_strings_in_week_content(week_file):
    data = json.loads(week_file.read_text())
    offenders = []
    for key, text in _walk_strings(data):
        for pattern, label in FORBIDDEN:
            if pattern.search(text):
                offenders.append((key, text, label))
    assert not offenders, (
        f"{week_file.name} contains participant-facing numeric health strings:\n"
        + "\n".join(f"  key={k!r}  text={t!r}  rule={label}" for k, t, label in offenders)
    )


def test_each_week_declares_a_sequence_and_phases():
    for p in _iter_week_files():
        data = json.loads(p.read_text())
        assert "week" in data and isinstance(data["week"], int)
        assert "sequence" in data and data["sequence"], f"{p.name} has no sequence"
        assert "phases" in data and data["phases"], f"{p.name} has no phases"
        # Every id in sequence must have a step definition.
        for sid in data["sequence"]:
            assert sid in data.get("steps", {}), f"{p.name} sequence refers to undefined step {sid!r}"


def test_sample_content_files_are_outside_the_weeks_scan_path():
    """The two SAMPLE files (dining menu, grocery products) carry
    nutrient values and %DV legitimately — they're the lesson. The
    walker's scope is backend/content/weeks/, so they're out of scope
    here. This test documents the exception: if a future refactor moves
    the SAMPLE files into weeks/, the walker will start scanning them
    and this test (and its author) will need to teach it the allow-list."""
    content_root = WEEKS_DIR.parent
    for name in ("week2_dining_menu.json", "week2_grocery_products.json"):
        p = content_root / name
        assert p.exists(), f"{name} missing — the Week 2 scenario loader depends on it."
        assert p.parent == content_root, (
            f"{name} must stay in backend/content/, not under weeks/, so the content-rule "
            "walker doesn't scan it."
        )


def test_week2_scenario_option_text_does_not_leak_calorie_mentions():
    """Option labels on the dining and grocery scenarios ride a narrow
    numeric allow-list — but calories are explicitly out of that
    allow-list per the Week 2 spec ("Calories should not be emphasized
    or introduced into the generated feedback"). The dining menu and
    grocery product files hold nutrient *numbers* on JSON fields, but
    their *name* and *notes* fields are strings — this test scans those
    strings for calorie mentions."""
    content_root = WEEKS_DIR.parent
    for name in ("week2_dining_menu.json", "week2_grocery_products.json"):
        data = json.loads((content_root / name).read_text())
        for _key, text in _walk_strings(data):
            assert "calori" not in text.lower(), (
                f"{name} has a string that mentions calories: {text!r}. "
                "Calories are not allow-listed for Week 2 scenarios."
            )


def test_forbidden_patterns_actually_catch_known_bad_strings():
    """Belt-and-braces: a confirming positive test so a future refactor
    that silently defangs the regexes doesn't leave this suite happily
    green while numbers quietly leak into participant copy."""
    bad = [
        "You logged 200 calories at breakfast.",
        "Your sodium intake was 1800 mg today.",
        "This item is 15 %DV.",
        "Your HEI score is lower than expected.",
        "You're 2/3 meals done today.",
        "One more meal to go!",
    ]
    for s in bad:
        assert any(p.search(s) for p, _ in FORBIDDEN), f"No rule caught {s!r}"


def test_each_step_has_a_type_and_points():
    for p in _iter_week_files():
        data = json.loads(p.read_text())
        for sid, step in (data.get("steps") or {}).items():
            assert isinstance(step, dict), f"{p.name} step {sid!r} is not an object"
            assert "type" in step, f"{p.name} step {sid!r} missing 'type'"
            assert "points" in step, f"{p.name} step {sid!r} missing 'points'"
