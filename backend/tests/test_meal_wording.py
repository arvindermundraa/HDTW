"""Rule check: no participant-facing meal-count wording.

LLHS targets diet quality, not meal frequency. Review flagged phrases like
"0/2 meals" and "2 meals to go" because they imply students must eat a set
number of meals each day. The Eat ring is activity-oriented: it fills once
a meal is logged, with no required daily count.

This test fails if any participant-facing string in the backend or frontend
source matches:
  * ``\\d+/\\d+ meals`` — a fraction-style meal count (e.g. "2/3 meals").
  * ``meals to go`` — "to go" wording that frames logging as a quota.

Tests, fixtures and code comments are excluded (tests may still assert that
the production code no longer produces these strings).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Both patterns are intentionally generous: `meals?` catches singular too so a
# "1 meal to go" regression also trips, and `\d+\s*/\s*\d+\s*meals?` accepts
# optional whitespace around the slash so templated / interpolated outputs
# can't sneak through with "`${v} / ${t} meals`".
FORBIDDEN = [
    (re.compile(r"\d+\s*/\s*\d+\s*meals?\b", re.IGNORECASE),
     'a "N/M meals" fraction (implies a required meal count)'),
    (re.compile(r"\bmeals?\s+to\s+go\b", re.IGNORECASE),
     '"meal(s) to go" (frames logging as a quota)'),
]

SOURCE_DIRS = [
    REPO_ROOT / "backend",
    REPO_ROOT / "frontend" / "src",
    REPO_ROOT / "frontend" / "app",
]
SOURCE_SUFFIXES = {".py", ".ts", ".tsx"}

# Tests, fixtures, generated assets and vendor code are not participant-
# facing. Comments inside production files are not shown to students either,
# so lines that are purely a comment are stripped before scanning.
EXCLUDED_PATH_PARTS = {"tests", "test", "__pycache__", "node_modules", ".expo", "dist", "build"}
EXCLUDED_FILENAME_HINTS = (".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx")


def _should_scan(path: Path) -> bool:
    if path.suffix not in SOURCE_SUFFIXES:
        return False
    if any(part in EXCLUDED_PATH_PARTS for part in path.parts):
        return False
    if any(path.name.endswith(hint) for hint in EXCLUDED_FILENAME_HINTS):
        return False
    return True


_LINE_COMMENT = re.compile(r"^\s*(//|#|\*|/\*)")


def _strip_comment(line: str) -> str:
    """Blank out a line that is purely a comment. Non-pure lines (code with
    a trailing comment) still get scanned in full — a stringified meal-count
    on the same line as a `//` is still worth catching."""
    return "" if _LINE_COMMENT.match(line) else line


def _iter_source_files():
    for root in SOURCE_DIRS:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and _should_scan(path):
                yield path


def test_source_dirs_exist():
    # Guard against the test silently scanning nothing (e.g. a repo layout change).
    found_roots = [d for d in SOURCE_DIRS if d.exists()]
    assert found_roots, f"none of the expected source roots exist: {SOURCE_DIRS}"


def test_no_meal_count_wording_in_participant_facing_source():
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
                match = pattern.search(line)
                if match:
                    rel = path.relative_to(REPO_ROOT)
                    violations.append(
                        f"{rel}:{lineno}: contains {label} — matched {match.group(0)!r} in: {raw.strip()!r}"
                    )
    assert scanned > 0, "scanner found no files — check SOURCE_DIRS"
    assert not violations, (
        "Participant-facing source contains meal-count wording that implies "
        "a required daily number of meals:\n  " + "\n  ".join(violations)
    )


def test_scanner_actually_catches_each_forbidden_pattern(tmp_path):
    # If this fails, the regex list drifted away from the design rule and
    # the real scan above is giving a false sense of safety.
    probes = {
        "frac.ts": '  return "2/3 meals";',
        "to_go.py": 'return f"{n} meals to go"',
        "singular.tsx": 'return `${n} meal to go`;',
    }
    for name, content in probes.items():
        (tmp_path / name).write_text(content)

    hits = {label: False for _, label in FORBIDDEN}
    for name in probes:
        text = (tmp_path / name).read_text()
        for pattern, label in FORBIDDEN:
            if pattern.search(text):
                hits[label] = True
    for label, hit in hits.items():
        assert hit, f"regex for {label} did not match any probe"


def test_comment_lines_do_not_count():
    """Pure-comment lines are stripped. A production comment that merely
    mentions "to go" (for context) must not break the test."""
    sample = '// no required meal count, no "to go" and no overflow lap'
    assert _strip_comment(sample) == ""
    # But code with a trailing comment still gets scanned.
    sample2 = 'return "2/3 meals"; // caption text'
    assert _strip_comment(sample2) == sample2
