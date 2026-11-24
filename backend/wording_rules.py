"""Nutrition team feedback wording rules (2026-11-06, item 3 "Feedback
wording" and the 2026-11-06 PDF's bullet lists).

This module is the single source of truth for the avoid list that
Future Me's system prompt, the runtime guardrail on AI replies, and the
static wording check (``tests/test_wording_rules.py``) all share.

The team's rule is:

  **Avoid:** "unhealthy", "poor choices", "cheating", "should", "must",
    "not enough", "too much", "fix your diet", "you need to improve".
    Also avoid labeling foods as "good" or "bad".

  **Prefer:** "You're making progress", "One area to build on",
    "An opportunity to try something different", "Consider adding…",
    "You might try…", "Small changes can add up".

  **For dietary feedback:** Use "Your recent meals suggest…" or "Based
    on the days you reported…" rather than definitive statements about
    someone's usual diet.

  **For setbacks:** Use "Progress isn't always consistent" or "What might
    work better for you next time?" rather than emphasising failure.

  **Overall:** No exaggerated praise or overly playful language.

The avoid list is checked on student-facing *content files* (whole word,
case-insensitive) and on student-facing string literals / JSX text in
backend/*.py and frontend/app/** + frontend/src/**. AI system prompts,
knowledge-base source attribution, code comments, variable names, and
test fixtures are excluded from the static check because they
legitimately say things like "you should never recommend…".
"""
from __future__ import annotations

import re
from typing import Iterable, List, Tuple

# Whole-word avoid matches (case-insensitive). Multi-word entries are
# escaped as a single pattern so "fix your diet" matches across the
# phrase but "your diet" alone doesn't.
AVOID = [
    "unhealthy",
    "poor choices",
    "poor choice",
    "cheating",
    "should",
    "must",
    "not enough",
    "too much",
    "fix your diet",
    "you need to improve",
    # Food labelling — only flag when applied to food/choice itself,
    # which the generic whole-word check below will catch
    # ("good foods", "bad foods", "good choice", "bad choice").
    "good foods",
    "bad foods",
    "good food",
    "bad food",
    "good choice",
    "bad choice",
    "good choices",
    "bad choices",
]

# Prefer-language replacements (used in the test's "what should it say
# instead?" guidance when a hit is reported). This list is informational
# only; nothing enforces it mechanically.
PREFER_LANGUAGE = [
    "You're making progress",
    "One area to build on",
    "An opportunity to try something different",
    "Consider adding…",
    "You might try…",
    "Small changes can add up",
]

DIETARY_FEEDBACK_HEDGE = [
    "Your recent meals suggest…",
    "Based on the days you reported…",
]

SETBACK_WORDING = [
    "Progress isn't always consistent",
    "What might work better for you next time?",
]


def _compile() -> List[Tuple[str, re.Pattern]]:
    patterns: List[Tuple[str, re.Pattern]] = []
    for phrase in AVOID:
        # \b anchors around a phrase that starts/ends with a word char.
        # Multi-word phrases need \b at the outer boundary only.
        escaped = re.escape(phrase)
        patterns.append((phrase, re.compile(rf"\b{escaped}\b", re.IGNORECASE)))
    return patterns


_AVOID_PATTERNS = _compile()


def find_avoid_hits(text: str) -> List[str]:
    """Return every ``AVOID`` phrase matched in ``text``, lowercase,
    deduped, in the order they appear. Case-insensitive, whole-word."""
    seen = []
    seen_set = set()
    for phrase, pattern in _AVOID_PATTERNS:
        if pattern.search(text):
            key = phrase.lower()
            if key not in seen_set:
                seen.append(key)
                seen_set.add(key)
    return seen


def contains_avoid_phrase(text: str) -> bool:
    """True if ``text`` contains any avoid-list phrase (whole word,
    case-insensitive). Used as a runtime guardrail layer on AI replies
    to catch drift that the system prompt didn't prevent."""
    return bool(find_avoid_hits(text))


# A short prompt fragment that Future Me's SYSTEM_PROMPT includes
# verbatim. Kept here so the prompt and the guardrail can't drift.
SYSTEM_PROMPT_FRAGMENT = (
    "Feedback wording rules (nutrition team, 2026-11-06):\n"
    "- Be supportive, nonjudgmental, strengths-based and action-oriented.\n"
    "- Never use these words or phrases: " + ", ".join(f'"{w}"' for w in AVOID) + ".\n"
    "- Never label foods as 'good' or 'bad'.\n"
    "- Prefer: " + ", ".join(f'"{w}"' for w in PREFER_LANGUAGE) + ".\n"
    "- For dietary feedback, use: " + ", ".join(f'"{w}"' for w in DIETARY_FEEDBACK_HEDGE)
    + " — rather than definitive statements about usual diet.\n"
    "- For setbacks, use: " + ", ".join(f'"{w}"' for w in SETBACK_WORDING)
    + " — rather than emphasising failure.\n"
    "- No exaggerated praise or overly playful language."
)


def is_avoid_phrase_in(phrases: Iterable[str], text: str) -> bool:
    """Test helper — like ``contains_avoid_phrase`` but scoped to a
    subset of the avoid list (used by the wording-check test when
    building a targeted report)."""
    lowered = text.lower()
    return any(re.search(rf"\b{re.escape(p)}\b", lowered) for p in phrases)
