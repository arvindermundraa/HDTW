"""Static wording check — nutrition team 2026-11-06, item 3 ("Feedback
wording"). Scans:

1. Every student-facing content JSON in ``backend/content/**``.
2. Every student-facing string literal in ``backend/*.py`` (but NOT in
   AI system prompts, test files, or code comments — the avoid list
   legitimately appears in a prompt that tells the model *not* to use
   those words).
3. Every student-facing string literal + JSX text in
   ``frontend/app/**`` and ``frontend/src/**`` (same exclusions — AI
   prompts, test fixtures, comments, variable/function names).

Hits are matched whole-word, case-insensitive, against
``wording_rules.AVOID``. An entry in ``tests/wording_allowlist.json``
suppresses a specific (file, phrase) pair with a documented reason.

Also checks that Future Me's SYSTEM_PROMPT_FRAGMENT contains every
avoid-list phrase, so the system prompt and the guardrail can't drift
apart.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "llhs_unit_unused")

import wording_rules  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND = REPO_ROOT / "backend"
FRONTEND = REPO_ROOT / "frontend"
ALLOWLIST_PATH = Path(__file__).parent / "wording_allowlist.json"


def _load_allowlist():
    data = json.loads(ALLOWLIST_PATH.read_text())
    allowed = {}
    for entry in data.get("allowed", []):
        allowed.setdefault(entry["file"], set()).add(entry["phrase"].lower())
    return allowed


# --- content JSON scan -------------------------------------------------------


# JSON keys that hold developer-facing metadata the student never sees.
_NON_USER_FACING_KEYS = {
    "_comment",       # module-level documentation in content files
    "_about",         # twin_library.json uses this instead of _comment
    "scoring",        # HEI methodology string
    "source",         # KB citation reference
    "data_source",    # engine-internal routing
    # swaps.json "review" block: nutrition-team review metadata (status,
    # date, action_type, setting, equipment, caveat). Never rendered to
    # the student — these describe the reviewer's intent, not what the
    # app says. `caveat` is the field inside `review` that holds text
    # notes for engineering ("not whole grain, do not count"); keeping
    # it out of the wording scan.
    "caveat",
    # future_me_redirects.json — the `trigger_examples` arrays are
    # documentation of what a student might ask (so the nutrition team
    # can sanity-check the regex); they're never rendered to a student.
    # ``description`` is likewise an internal summary of the topic.
    "trigger_examples",
    "description",
}


def _json_string_values(obj, out, parent_key: str = ""):
    if isinstance(obj, str):
        if parent_key in _NON_USER_FACING_KEYS:
            return
        out.append(obj)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            _json_string_values(v, out, parent_key=k)
    elif isinstance(obj, list):
        for v in obj:
            _json_string_values(v, out, parent_key=parent_key)


def _content_files():
    return list((BACKEND / "content").rglob("*.json"))


def test_avoid_list_in_content_files():
    allow = _load_allowlist()
    hits = []
    for f in _content_files():
        allow_for_file = allow.get(str(f.relative_to(REPO_ROOT)), set())
        values: list[str] = []
        _json_string_values(json.loads(f.read_text()), values)
        for s in values:
            for phrase in wording_rules.find_avoid_hits(s):
                if phrase in allow_for_file:
                    continue
                hits.append(
                    f"{f.relative_to(REPO_ROOT)}: {phrase!r} in {s[:80]!r}"
                )
    assert not hits, "Avoid-list words in student-facing content:\n" + "\n".join(hits)


# --- backend source scan -----------------------------------------------------

# Backend files that contain AI system prompts, developer comments, or
# wording rules themselves — excluded from the check because they
# legitimately mention the avoid list.
BACKEND_SKIP_FILES = {
    "server.py",          # mixes user-facing strings with AI system prompts;
                          # the prompts are the main source of false positives
                          # ("you must not"). Future Me's own prompt is also
                          # here; we check it via SYSTEM_PROMPT_FRAGMENT below.
    "twin_llm.py",        # AI system prompt for From-your-meals.
    "wording_rules.py",   # this file defines the avoid list as data.
    "coach_kb.py",        # knowledge-base lookup; cites research text.
    "future_me.py",       # Future Me engine + prompt helpers.
}


_INTERNAL_CALL_NAMES = {
    # logging
    "logger", "logging", "_log", "log",
    # warnings / dev-only
    "warnings",
}

_INTERNAL_CALL_METHODS = {
    "info", "debug", "warning", "warn", "error", "exception", "critical",
}


def _is_internal_call(node) -> bool:
    """True when ``node`` is a call like ``logger.warning(...)`` / ``_log.info(...)`` /
    ``warnings.warn(...)`` — strings in those calls are not student-facing."""
    import ast
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Attribute):
        obj = func.value
        if isinstance(obj, ast.Name) and obj.id in _INTERNAL_CALL_NAMES:
            return True
        if func.attr in _INTERNAL_CALL_METHODS:
            return True
    if isinstance(func, ast.Name) and func.id in {"print"}:
        return True
    return False


def _py_user_facing_strings(path: Path):
    """Yield string literals in a Python file that could reasonably reach
    a student — i.e. not docstrings, not logger/warn calls, not raise/
    assert messages. Uses the AST to avoid false positives from module
    and function docstrings (which are the bulk of the first-pass hits)."""
    import ast
    try:
        tree = ast.parse(path.read_text())
    except Exception:
        return

    # Collect node ids of every string that is a docstring, or a direct
    # argument to an internal call (logger/warn), or the message of a
    # raise/assert. We then yield every other string Constant.
    skip_ids: set = set()

    def _mark_string_subtree(node, into: set) -> None:
        """Mark every ``ast.Constant[str]`` reachable from this node —
        covers plain string literals and f-string components alike."""
        import ast as _ast
        if node is None:
            return
        for child in _ast.walk(node):
            if isinstance(child, _ast.Constant) and isinstance(child.value, str):
                into.add(id(child))

    def _mark_docstring(body: list) -> None:
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                and isinstance(body[0].value.value, str):
            skip_ids.add(id(body[0].value))

    # Module docstring.
    _mark_docstring(tree.body)

    for node in ast.walk(tree):
        # Function / class docstrings.
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            _mark_docstring(node.body)
        # Internal call args.
        if _is_internal_call(node):
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    skip_ids.add(id(arg))
            for kw in node.keywords:
                if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                    skip_ids.add(id(kw.value))
        # Raise / assert messages — these are developer-facing exceptions,
        # not student-facing copy.
        if isinstance(node, ast.Raise) and node.exc is not None:
            exc = node.exc
            if isinstance(exc, ast.Call):
                for arg in exc.args:
                    _mark_string_subtree(arg, skip_ids)
                for kw in exc.keywords:
                    _mark_string_subtree(kw.value, skip_ids)
        if isinstance(node, ast.Assert) and node.msg is not None:
            _mark_string_subtree(node.msg, skip_ids)
        # Validator pattern: `return False, "developer-facing message"` —
        # the string is handed to callers as an API error reason, not
        # rendered verbatim to the student.
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Tuple):
            elts = node.value.elts
            if elts and isinstance(elts[0], ast.Constant) and elts[0].value is False:
                for elt in elts[1:]:
                    _mark_string_subtree(elt, skip_ids)

    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip_ids:
            yield node.value


_py_string_literals = _py_user_facing_strings  # backwards compat alias


def test_avoid_list_in_backend_sources():
    allow = _load_allowlist()
    hits = []
    for path in BACKEND.glob("*.py"):
        if path.name in BACKEND_SKIP_FILES or path.name.startswith("test_"):
            continue
        allow_for_file = allow.get(str(path.relative_to(REPO_ROOT)), set())
        for s in _py_string_literals(path):
            for phrase in wording_rules.find_avoid_hits(s):
                if phrase in allow_for_file:
                    continue
                hits.append(f"{path.relative_to(REPO_ROOT)}: {phrase!r} in {s[:80]!r}")
    assert not hits, "Avoid-list words in student-facing backend strings:\n" + "\n".join(hits)


# --- frontend scan -----------------------------------------------------------

# Frontend files that carry AI system prompts, test fixtures, or helpers
# that reference the avoid list as data (none today — keep the allow-list
# narrow).
FRONTEND_SKIP_FILES = {
    # none right now
}


def _frontend_text_candidates(path: Path):
    """Yield every string literal and JSX text node from a .tsx/.ts/.js
    file. This is a regex-based heuristic — it will miss some edge cases
    but is good enough to catch avoid-list words in user-facing copy."""
    text = path.read_text()
    # Strip single-line comments and block comments.
    text = re.sub(r"//.*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    # Match "...", '...', `...` literals (allow basic escapes).
    for m in re.finditer(r"(?:\"((?:[^\"\\]|\\.)*)\"|'((?:[^'\\]|\\.)*)'|`((?:[^`\\]|\\.)*)`)", text):
        s = m.group(1) or m.group(2) or m.group(3) or ""
        if s:
            yield s
    # JSX text nodes: >text< between tags, not import paths or attributes.
    for m in re.finditer(r">([^<>{]{3,}?)<", text):
        s = m.group(1).strip()
        if s:
            yield s


def _frontend_files():
    out = []
    for base in (FRONTEND / "app", FRONTEND / "src"):
        if not base.exists():
            continue
        for p in base.rglob("*.tsx"):
            out.append(p)
        for p in base.rglob("*.ts"):
            out.append(p)
    return out


def test_avoid_list_in_frontend_sources():
    allow = _load_allowlist()
    hits = []
    for path in _frontend_files():
        rel = str(path.relative_to(REPO_ROOT))
        if path.name in FRONTEND_SKIP_FILES or "__tests__" in path.parts or ".test." in path.name:
            continue
        allow_for_file = allow.get(rel, set())
        for s in _frontend_text_candidates(path):
            for phrase in wording_rules.find_avoid_hits(s):
                if phrase in allow_for_file:
                    continue
                hits.append(f"{rel}: {phrase!r} in {s[:80]!r}")
    assert not hits, "Avoid-list words in student-facing frontend strings:\n" + "\n".join(hits)


# --- Future Me prompt fragment -----------------------------------------------


def test_system_prompt_fragment_lists_every_avoid_phrase():
    """Catches drift between the guardrail data and the Future Me
    instructions: the system prompt must name every avoid phrase so the
    model is told not to use any of them."""
    fragment = wording_rules.SYSTEM_PROMPT_FRAGMENT.lower()
    missing = [p for p in wording_rules.AVOID if p.lower() not in fragment]
    assert not missing, f"System prompt fragment is missing avoid phrases: {missing}"
