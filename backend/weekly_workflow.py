"""Weekly workflow engine — content-driven per-week step tracking.

What this module is for
-----------------------
Weeks 1 and 2 are redesigned as connected journeys with a per-student
record, step-by-step completion, and a Today "This week" card that
reflects where the student is. The content for each week lives in
``backend/content/weeks/weekN.json`` so the research team can review and
replace copy without touching Python. This module is the engine that
reads those files and the per-student record and tells callers what to
show.

The engine is deliberately a set of pure functions. Database IO (reading
and writing ``db.weekly_workflow`` records, reading signals like the
user's focus area or ASA24 recall status) lives in ``server.py``; the
engine just takes dicts in and returns dicts out, which keeps it
unit-testable without a running Mongo.

The gate
--------
``WEEK1_WORKFLOW_MODE`` (and later ``WEEK2_WORKFLOW_MODE``) follows the
same pattern as ``WINGS_PHOTOS_MODE``:

    "off"        → nobody sees the new workflow; the Today card falls
                   back to the existing ``program.py`` unit.
    "test_only"  → only ``is_test_account`` students see it. Default
                   while the full flow is being built, so lab testers
                   can rehearse without pilot users seeing a
                   half-finished experience.
    "on"         → every eligible student (gated at env level).

Signals
-------
Two steps complete themselves from state the student already has:

* ``focus_selection`` is marked done once ``users.focus_area`` is set.
* ``goal_and_plan`` is marked done once both ``users.focus_goal.goal``
  and ``users.focus_goal.plan`` are set.

Everything else is marked by the student via the step screen (video
completed, feedback acknowledged, reflection submitted). Steps whose
content is still ``draft`` or whose ``video_id`` is null still render —
the frontend shows a "Content coming soon" or "Video coming soon" card
with a Continue button, so no step can block the flow.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_log = logging.getLogger("llhs.weekly_workflow")

VALID_MODES = ("off", "test_only", "on")
SUPPORTED_WEEKS = (1, 2)

_CONTENT_DIR = Path(__file__).resolve().parent / "content" / "weeks"


# --- Mode flag ----------------------------------------------------------------

def _mode_env_var(week: int) -> str:
    return f"WEEK{week}_WORKFLOW_MODE"


def workflow_mode(week: int) -> str:
    """Read the per-week mode flag at call time (never cached) so the env
    can be flipped without a code change. Anything other than the three
    valid values falls back to ``"off"`` — a typo must never silently
    enable a half-built workflow."""
    raw = (os.environ.get(_mode_env_var(week)) or "off").strip().lower()
    return raw if raw in VALID_MODES else "off"


def week_opens_on(study_start: date, week: int) -> date:
    """Study-TZ date on which ``week`` opens for a student who joined
    on ``study_start``. Week 1 is day 0, Week 2 is day 7, etc. Mirrors
    the schedule used by ``program.py`` so the two systems can't
    disagree on when a week becomes active."""
    return study_start + timedelta(days=7 * (week - 1))


def week_has_opened(study_start: date, today: date, week: int) -> bool:
    return today >= week_opens_on(study_start, week)


def is_enabled_for(
    week: int, *, is_test: bool,
    study_start: Optional[date] = None,
    today: Optional[date] = None,
) -> bool:
    """Whether the student should see the new workflow for ``week``.
    Mirrors ``wings_photos.can_user_post``: ``"test_only"`` requires
    ``is_test`` true; ``"on"`` enables every student. Also respects the
    study clock — a week that hasn't opened yet (``today`` is before
    the week's start day) is never enabled, regardless of mode. The
    study-clock gate is a safety net alongside the mode flag: a
    production deploy that accidentally flips ``WEEK2_WORKFLOW_MODE=on``
    before the real Week 2 open date must not surface Week 2 content
    to a cohort that's still on Week 1."""
    mode = workflow_mode(week)
    if mode == "off":
        return False
    if mode == "test_only" and not is_test:
        return False
    if study_start is not None and today is not None:
        if not week_has_opened(study_start, today, week):
            return False
    return True


# --- Content loader -----------------------------------------------------------

_CONTENT_CACHE: Dict[int, Dict[str, Any]] = {}


def load_week(week: int) -> Dict[str, Any]:
    """Load (and cache) the Week ``week`` content file. Raises
    ``FileNotFoundError`` for an unsupported week — content files are
    required to exist for every week the engine serves. The cache is
    process-local; tests that want a fresh read can call
    :func:`_clear_cache`."""
    if week in _CONTENT_CACHE:
        return _CONTENT_CACHE[week]
    path = _CONTENT_DIR / f"week{week}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"No content file for week {week} at {path}. "
            "Add backend/content/weeks/week{week}.json."
        )
    with path.open() as f:
        data = json.load(f)
    _CONTENT_CACHE[week] = data
    return data


def _clear_cache() -> None:
    _CONTENT_CACHE.clear()


# --- Step state ---------------------------------------------------------------

def _completion_rule_satisfied(rule: Optional[str], signals: Dict[str, Any]) -> bool:
    """A step with a non-null ``completion_rule`` is auto-completed when
    the matching external signal is present. The engine never writes
    these auto-complete rows into the record — they are overlaid at read
    time so a student who sets their focus area outside the workflow
    (via the existing Eat screen) still has ``focus_selection`` marked
    done."""
    if rule is None:
        return False
    if rule == "focus_area_set":
        return bool(signals.get("focus_area"))
    if rule == "goal_and_plan_set":
        goal = signals.get("focus_goal") or {}
        return bool(goal.get("goal") and goal.get("plan"))
    if rule == "three_scenarios_completed":
        # Week 2 scenarios step: done after three distinct scenario
        # responses are saved. The count is derived from the record
        # itself (see week2_scenarios.completed_scenario_count), so
        # the server passes it through the signals map as a precomputed
        # integer rather than importing week2_scenarios here (keeps the
        # engine free of Week-2-specific imports).
        return int(signals.get("completed_scenarios_count") or 0) >= 3
    _log.warning("Unknown completion_rule %r in content; ignoring", rule)
    return False


def _extract_response_value(resp: Any) -> Any:
    """Pull the user-visible value out of a saved reflection response.
    Single-select answers are stored as ``{"selected": "Breakfast"}``,
    multi-select as ``{"selected": [...], "text": "..."}``, text as
    ``{"text": "..."}`` — the carried map always wants the chosen
    singular, so this helper centralises the key check."""
    if isinstance(resp, dict):
        if resp.get("selected") is not None:
            return resp["selected"]
        if resp.get("text") is not None:
            return resp["text"]
        return None
    return resp


def build_week_view(
    content: Dict[str, Any],
    record: Dict[str, Any],
    signals: Dict[str, Any],
) -> Dict[str, Any]:
    """Merge the week content, the per-student record and external
    signals into the shape the client renders.

    ``record`` is the raw ``db.weekly_workflow`` document (or an empty
    dict for a student who hasn't started the week). ``signals`` carries
    external state the engine checks against auto-complete rules — today
    just ``focus_area`` and ``focus_goal`` from the user document, but
    the signal map is open so new rules (e.g. ASA24 recall finished)
    can be added without touching the engine's public surface.

    The returned dict is JSON-safe and designed to be served verbatim
    from ``/api/weekly-workflow``."""
    sequence: List[str] = list(content.get("sequence") or [])
    phases: Dict[str, Any] = content.get("phases") or {}
    steps_content: Dict[str, Any] = content.get("steps") or {}
    recorded = (record.get("step_statuses") or {})

    carried: Dict[str, Any] = {}
    steps_out: List[Dict[str, Any]] = []
    next_step_id: Optional[str] = None
    done_count = 0
    for step_id in sequence:
        meta = steps_content.get(step_id) or {}
        done_via_record = (recorded.get(step_id) or {}).get("status") == "done"
        done_via_rule = _completion_rule_satisfied(meta.get("completion_rule"), signals)
        done = done_via_record or done_via_rule
        if done:
            done_count += 1
        elif next_step_id is None:
            next_step_id = step_id
        completed_at = (recorded.get(step_id) or {}).get("completed_at")
        steps_out.append({
            "id": step_id,
            "type": meta.get("type"),
            "label": meta.get("label") or step_id.replace("_", " ").title(),
            "title": meta.get("title"),
            "cta_next_label": meta.get("cta_next_label"),
            "draft": bool(meta.get("draft")),
            "points": int(meta.get("points") or 0),
            "status": "done" if done else "pending",
            "completed_at": completed_at,
            "auto": meta.get("completion_rule") is not None,
            "route": meta.get("route"),
        })
        # Collect carried values once the source step is recorded, so
        # later steps can read them without re-walking. The carry link
        # ``prompt.carries_to = "<dest_step>.<field>"`` means "when the
        # reflection step is done, expose this prompt's answer under
        # ``carried.<field>`` for the goal-and-plan screen to pre-fill".
        if done_via_record:
            step_responses = (recorded.get(step_id) or {}).get("responses") or {}
            prompts = meta.get("prompts") or []
            # The reflection step carries ``prompts`` as a list (one entry
            # per sub-prompt). The planning step carries ``prompts`` as a
            # dict keyed by prompt id. The carried-value walker only
            # needs the reflection shape, so skip when it isn't a list.
            if not isinstance(prompts, list):
                prompts = []
            for prompt in prompts:
                if not isinstance(prompt, dict):
                    continue
                carry = prompt.get("carries_to")
                if not carry or "." not in carry:
                    continue
                _, field = carry.split(".", 1)
                val = _extract_response_value(step_responses.get(prompt["id"]))
                if val is not None:
                    carried[field] = val

    phase_views: List[Dict[str, Any]] = []
    for pid, phase in phases.items():
        phase_steps = [s for s in steps_out if s["id"] in (phase.get("steps") or [])]
        phase_views.append({
            "id": pid,
            "label": phase.get("label"),
            "steps": [s["id"] for s in phase_steps],
            "done": sum(1 for s in phase_steps if s["status"] == "done"),
            "total": len(phase_steps),
        })

    return {
        "week": content["week"],
        "title": content["title"],
        "summary": content.get("summary"),
        "sequence": sequence,
        "phases": phase_views,
        "steps": steps_out,
        "steps_done": done_count,
        "steps_total": len(sequence),
        "next_step_id": next_step_id,
        "carried": carried,
    }


def get_step_content(week: int, step_id: str) -> Optional[Dict[str, Any]]:
    """Return the content definition for a single step, or ``None`` if
    the step doesn't exist. Used by the step-detail endpoint to serve
    the full step body (prompts, options, video URL) without exposing
    the whole week file to the client in one shot."""
    content = load_week(week)
    return (content.get("steps") or {}).get(step_id)


def resolve_step(
    week: int,
    step_id: str,
    *,
    focus_area: Optional[str],
    focus_area_label: Optional[str],
    carried: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return a copy of the step content with every per-user
    substitution already filled in — reflection prompt 1 picks the
    adequacy vs moderation variant and swaps ``{focus}`` for the right
    phrase, reflection's completion message swaps ``{occasion}`` for
    the carried answer, and goal_and_plan surfaces the example for the
    student's focus area. The client renders strings, not templates.

    If ``focus_area`` is None (the student hasn't chosen one yet) the
    reflection step comes back with a null ``resolved_prompt_1`` and a
    friendly fallback label; the frontend treats that as "not ready".
    """
    step = dict(get_step_content(week, step_id) or {})
    if not step:
        return {}
    carried = carried or {}

    if step.get("type") == "reflection":
        kind_by_area = step.get("focus_kind_by_area") or {}
        word_by_area = step.get("focus_word_overrides") or {}
        kind = kind_by_area.get(focus_area or "")
        focus_word = word_by_area.get(focus_area or "") or (
            focus_area_label.lower() if focus_area_label else None
        )
        resolved_prompts = []
        for p in step.get("prompts") or []:
            pp = dict(p)
            variant = p.get("variant_by_focus_kind")
            if variant and kind:
                tpl = variant.get(kind) or ""
                pp["prompt"] = tpl.replace("{focus}", focus_word or "it")
            resolved_prompts.append(pp)
        step["resolved_prompts"] = resolved_prompts
        step["resolved_focus_word"] = focus_word
        step["resolved_focus_kind"] = kind
        # Fill the completion template using any already-carried occasion
        # ("Not sure yet" uses the alternative language, per spec 6.5).
        occasion = (carried or {}).get("occasion")
        not_sure_option = next(
            (p.get("not_sure_option") for p in step.get("prompts") or [] if p.get("not_sure_option")),
            "Not sure yet",
        )
        if occasion and occasion != not_sure_option:
            tpl = step.get("completion_message_template") or ""
            step["resolved_completion_message"] = tpl.replace("{occasion}", occasion)
        elif occasion == not_sure_option:
            step["resolved_completion_message"] = step.get("not_sure_yet_message")
        else:
            step["resolved_completion_message"] = None

    elif step.get("type") == "goal_and_plan":
        examples = step.get("examples") or {}
        step["resolved_example"] = examples.get(focus_area or "") if focus_area else None

    elif step.get("type") == "video" and step_id == "mini_lecture":
        ids = step.get("video_id_by_area") or {}
        urls = step.get("video_url_by_area") or {}
        captions = step.get("captions_url_by_area") or {}
        step["video_id"] = ids.get(focus_area or "") if focus_area else None
        step["video_url"] = urls.get(focus_area or "") if focus_area else None
        step["captions_url"] = captions.get(focus_area or "") if focus_area else None

    elif step.get("subtype") == "ambassador":
        # Pick the first scenario-setting video that matches the
        # student's chosen three; fall back to the default clip when
        # none match or when none of the picks have a URL yet.
        chosen = (carried or {}).get("scenario_settings_chosen") or []
        assignment = step.get("assignment_by_setting") or {}
        chosen_match = next((assignment[s] for s in chosen if assignment.get(s)), None) or {}
        step["video_id"] = chosen_match.get("video_id") or step.get("default_video_id")
        step["video_url"] = chosen_match.get("video_url") or step.get("default_video_url")
        step["captions_url"] = chosen_match.get("captions_url") or step.get("default_captions_url")
        step["ambassador_name"] = chosen_match.get("ambassador_name")
        step["subtitle"] = chosen_match.get("subtitle")

    return step


def step_points(week: int, step_id: str) -> int:
    """Points to award on first completion. Zero when the step isn't
    found or hasn't declared a value — keeps the award call safe for
    unknown ids."""
    step = get_step_content(week, step_id) or {}
    try:
        return int(step.get("points") or 0)
    except (TypeError, ValueError):
        return 0


def validate_step_response(
    week: int,
    step_id: str,
    response: Dict[str, Any],
) -> Tuple[bool, Optional[str]]:
    """Lightweight shape check on a step response before it's written.
    Returns ``(True, None)`` or ``(False, reason)``. The engine does not
    try to be a full form-validator; it only enforces constraints the
    content file declares (``response_type``, ``max_length``, allowed
    option values) so a buggy or malicious client can't shove a
    ``{"status": "done"}`` response into a free-text slot.

    The frontend still validates for UX; this is a server-side guard
    against bypasses, not a replacement for client validation.
    """
    step = get_step_content(week, step_id)
    if step is None:
        return False, "Unknown step."
    step_type = step.get("type")
    if step_type == "reflection":
        prompts = {p["id"]: p for p in step.get("prompts") or []}
        responses = response.get("responses") or {}
        if not isinstance(responses, dict):
            return False, "Reflection responses must be an object keyed by prompt id."
        for pid, resp in responses.items():
            prompt = prompts.get(pid)
            if prompt is None:
                return False, f"Unknown reflection prompt: {pid!r}."
            rtype = prompt.get("response_type")
            if rtype == "text":
                val = resp.get("text") if isinstance(resp, dict) else resp
                if val is None:
                    continue
                if not isinstance(val, str):
                    return False, f"Reflection {pid!r} expected a string."
                max_len = prompt.get("max_length") or 1000
                if len(val) > max_len:
                    return False, f"Reflection {pid!r} is longer than {max_len} characters."
            elif rtype == "single_select":
                val = resp.get("selected") if isinstance(resp, dict) else resp
                if val is not None and val not in (prompt.get("options") or []):
                    return False, f"Reflection {pid!r} choice is not one of the allowed options."
            elif rtype == "multi_select":
                vals = resp.get("selected") if isinstance(resp, dict) else resp
                if vals is None:
                    continue
                if not isinstance(vals, list):
                    return False, f"Reflection {pid!r} expected a list of selections."
                allowed = set(prompt.get("options") or [])
                for v in vals:
                    if v not in allowed:
                        return False, f"Reflection {pid!r} includes an option not on the list."
                if prompt.get("optional_text"):
                    text = resp.get("text") if isinstance(resp, dict) else None
                    if text is not None and not isinstance(text, str):
                        return False, f"Reflection {pid!r} optional text must be a string."
    return True, None
