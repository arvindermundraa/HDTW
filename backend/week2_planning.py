"""Week 2 planning engine — pure functions behind the "Planning Where
You'll Use It" step and the multi-plan Today card.

The HTTP surface + the per-student plan records live in server.py (same
pattern as weekly_workflow.py and week2_scenarios.py). This module
owns:

* Lookups into the content file (``actions_by_focus_and_setting``,
  ``coping_by_barrier``, ``settings``, ``occasions``, prompt copy).
* The Plan record shape and the status transitions driven by the Phase
  5 "keep and add / replace / keep last week's only" choice.
* Default reminder-time derivation (one hour before the chosen
  occasion, per spec §5.6).
* The completion summary filler that honours the student's actual
  answers, with natural grammar for custom text.

Nothing in this module touches Mongo — tests exercise it with plain
dicts.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Optional, Tuple


# --- Plan record shape -------------------------------------------------------

ACTIVE = "active"
REPLACED = "replaced"
KEPT = "kept"
VALID_STATUSES = (ACTIVE, REPLACED, KEPT)

PlanRecord = Dict[str, Any]


def make_plan(
    *,
    user_id: str,
    source_week: int,
    focus_area: Optional[str],
    focus_goal: Optional[Dict[str, Any]],
    situation: Dict[str, Any],
    action: Optional[Dict[str, Any]],
    barrier: Optional[Dict[str, Any]],
    coping: Optional[Dict[str, Any]],
    reminder: Optional[Dict[str, Any]],
    status: str = ACTIVE,
    plan_id: Optional[str] = None,
    now_iso: Optional[str] = None,
) -> PlanRecord:
    """Build a new ``PlanRecord``. All fields are optional at the
    engine layer because:

    * Week 1 plans synthesized from the pilot migration carry only
      ``focus_area`` + ``focus_goal`` and may have NO situation /
      action / barrier / coping / reminder saved against them.
    * Week 2 plans always have the full set when ``status=active``.
    * ``status=kept`` plans record the Week 2 answers verbatim but
      flag them as dormant (no reminder dispatch in Phase 3).
    """
    if status not in VALID_STATUSES:
        raise ValueError(f"Unknown plan status: {status!r}")
    now = now_iso or datetime.utcnow().isoformat()
    return {
        "id": plan_id,
        "user_id": user_id,
        "source_week": source_week,
        "status": status,
        "focus_area": focus_area,
        "focus_goal": focus_goal or {},
        "situation": situation or {},
        "action": action or {},
        "barrier": barrier or {},
        "coping": coping or {},
        "reminder": reminder or {},
        "created_at": now,
        "updated_at": now,
    }


# --- Content lookups ---------------------------------------------------------

def _planning(content: Dict[str, Any]) -> Dict[str, Any]:
    """The planning step body out of the week content dict."""
    return (content.get("steps") or {}).get("planning") or {}


def actions_for(content: Dict[str, Any], focus_area: Optional[str], setting: Optional[str]) -> List[str]:
    """3-4 preset actions matched to the student's focus + setting.
    Returns an empty list when either is unknown; the UI then shows
    just the "Write my own action" field — a soft fallback that never
    blocks the planning step."""
    if not focus_area or not setting:
        return []
    by_focus = (_planning(content).get("actions_by_focus_and_setting") or {}).get(focus_area) or {}
    return list(by_focus.get(setting) or [])


def copings_for(content: Dict[str, Any], barrier: Optional[str]) -> List[str]:
    """2-3 preset coping responses matched to the chosen barrier."""
    if not barrier:
        return []
    return list((_planning(content).get("coping_by_barrier") or {}).get(barrier) or [])


def available_settings(content: Dict[str, Any]) -> List[Dict[str, Any]]:
    return list(_planning(content).get("settings") or [])


def available_occasions(content: Dict[str, Any]) -> List[Dict[str, Any]]:
    return list(_planning(content).get("occasions") or [])


def available_barriers(content: Dict[str, Any]) -> List[Dict[str, Any]]:
    return list(((_planning(content).get("prompts") or {}).get("p3_barrier") or {}).get("options") or [])


def plan_management_options(content: Dict[str, Any]) -> List[Dict[str, Any]]:
    return list(((_planning(content).get("prompts") or {}).get("p5_plan_management") or {}).get("options") or [])


# --- Default reminder time --------------------------------------------------

def default_reminder_time_for_occasion(content: Dict[str, Any], occasion_id: Optional[str]) -> Optional[str]:
    """"06:00" one hour before "07:00" breakfast, etc. Pulled from the
    content file so the team can tune the clock without redeploying.
    Returns None for an unknown occasion or when no default is set."""
    if not occasion_id:
        return None
    for occ in available_occasions(content):
        if occ.get("id") == occasion_id:
            return occ.get("default_reminder_time")
    return None


def default_occasion_time(content: Dict[str, Any], occasion_id: Optional[str]) -> Optional[str]:
    if not occasion_id:
        return None
    for occ in available_occasions(content):
        if occ.get("id") == occasion_id:
            return occ.get("default_time")
    return None


def next_seven_study_days(today: date) -> List[Dict[str, str]]:
    """Day picker options. The engine returns 7 upcoming days starting
    today in the study TZ; the UI renders them. Keeping this out of the
    content file so the dates roll naturally."""
    out = []
    for offset in range(7):
        d = today + timedelta(days=offset)
        label = d.strftime("%a %b %-d") if hasattr(d, "strftime") else d.isoformat()
        out.append({"iso": d.isoformat(), "label": label})
    return out


# --- Summary filler + natural grammar ---------------------------------------

def _trim_period(text: str) -> str:
    """Drop one trailing period / exclamation so a sentence like
    'Ask for sauce on the side.' can slot inside '…you'll {action}.'
    without producing '…you'll Ask for sauce on the side..'. Keeps
    other punctuation (e.g., question marks are intentional)."""
    s = text.strip()
    while s.endswith(".") or s.endswith("!"):
        s = s[:-1].rstrip()
    return s


def _lower_leading(text: str) -> str:
    """Lowercase the first letter so the action reads as a continuation
    of 'you'll …'. Preserves acronyms and proper nouns (if the first
    word is all-caps, leave it alone)."""
    s = text.lstrip()
    if not s:
        return text
    first_word = s.split()[0]
    if first_word.isupper() and len(first_word) > 1:
        return s
    return s[:1].lower() + s[1:]


def action_phrase(action_text: str) -> str:
    """Natural-grammar fit for '…you'll <action>…'. Strips the "DRAFT —"
    prefix the content file puts on team-review strings so the preview
    never shows it to a student."""
    s = action_text.strip()
    if s.startswith("DRAFT — "):
        s = s[len("DRAFT — "):]
    elif s.startswith("DRAFT —"):
        s = s[len("DRAFT —"):].lstrip()
    s = _trim_period(s)
    return _lower_leading(s)


def barrier_phrase(label: str) -> str:
    """'Not enough time' → 'you're short on time'. The planning summary
    is a sentence, so the raw barrier label often reads awkwardly. We
    keep a small lookup for the eight canonical barriers; anything
    custom falls through to the label verbatim.

    These maps aren't content-file material because they're wiring:
    canonical ids to a sentence fragment. The team's wording lives in
    the ``label`` field of each barrier option in week2.json; the
    phrasing here just makes it fit the summary template."""
    return _BARRIER_SUMMARY_PHRASE.get(label, label.lower())


_BARRIER_SUMMARY_PHRASE: Dict[str, str] = {
    "Not enough time": "you're short on time",
    "Cost": "cost gets in the way",
    "What's available": "what you want isn't available",
    "Someone else choosing": "someone else is choosing",
    "Feeling tired or stressed": "you're tired or stressed",
    "A craving for something else": "a craving pulls you another way",
    "I might forget": "you might forget",
    "Something else": "something else comes up",
}


def coping_phrase(coping_text: str) -> str:
    """Same shape as action_phrase — strip DRAFT prefix + period +
    lowercase the leading letter so '{coping}' slots into 'you'll
    {coping}' smoothly."""
    s = coping_text.strip()
    if s.startswith("DRAFT — "):
        s = s[len("DRAFT — "):]
    elif s.startswith("DRAFT —"):
        s = s[len("DRAFT —"):].lstrip()
    s = _trim_period(s)
    return _lower_leading(s)


def situation_phrase(
    *,
    day_label: Optional[str],
    occasion_label: Optional[str],
    setting_label: Optional[str],
    custom_setting_text: Optional[str],
    occasion_time: Optional[str],
) -> str:
    """Builds the 'When {situation_and_time}' slot. Honours whatever
    the student actually filled in — any missing field is dropped
    rather than papered over. Examples:
      - "Monday Nov 3, breakfast at the dining hall"
      - "Wednesday, lunch somewhere else (campus coffee stop)"
      - "Tuesday, dinner" (no setting)
    """
    setting_text = (custom_setting_text.strip() if custom_setting_text else None) or setting_label
    parts: List[str] = []
    if day_label:
        parts.append(day_label)
    occasion_bit = occasion_label.lower() if occasion_label else None
    if occasion_bit and setting_text and setting_text.lower() not in {"somewhere else", "elsewhere"}:
        parts.append(f"{occasion_bit} at {setting_text.lower()}")
    elif occasion_bit and setting_text:
        parts.append(f"{occasion_bit} ({setting_text})")
    elif occasion_bit:
        parts.append(occasion_bit)
    elif setting_text:
        parts.append(setting_text.lower())
    if occasion_time:
        parts.append(f"around {_pretty_time(occasion_time)}")
    return ", ".join(parts) if parts else "the moment you pick"


def _pretty_time(hhmm: str) -> str:
    """'06:00' → '6 AM'. Returns the input verbatim if parsing fails."""
    try:
        t = time.fromisoformat(hhmm)
    except ValueError:
        return hhmm
    hour12 = t.hour % 12 or 12
    suffix = "AM" if t.hour < 12 else "PM"
    if t.minute == 0:
        return f"{hour12} {suffix}"
    return f"{hour12}:{t.minute:02d} {suffix}"


def reminder_phrase(reminder_time: Optional[str]) -> str:
    if not reminder_time:
        return "at the time you set"
    return f"at {_pretty_time(reminder_time)}"


def build_completion_summary(
    content: Dict[str, Any],
    *,
    plan_management: str,
    situation: Dict[str, Any],
    action: Dict[str, Any],
    barrier: Dict[str, Any],
    coping: Dict[str, Any],
    reminder: Dict[str, Any],
    settings_lookup: Dict[str, str],
    occasions_lookup: Dict[str, Dict[str, Any]],
) -> str:
    """Fill the completion summary template using only the student's
    answers. ``plan_management`` chooses between the two templates:
    the keep-week1-only variant is a shorter sentence that doesn't
    assume the Week 2 plan is active."""
    pl = _planning(content)
    if plan_management == "keep_week1_only":
        return pl.get("completion_summary_keep_only_template") or (
            "Thanks. You kept last week's plan."
        )
    tpl = pl.get("completion_summary_template") or ""
    sit = situation_phrase(
        day_label=situation.get("day_label"),
        occasion_label=(occasions_lookup.get(situation.get("occasion") or "") or {}).get("label"),
        setting_label=settings_lookup.get(situation.get("setting") or ""),
        custom_setting_text=situation.get("custom_setting_text"),
        occasion_time=(occasions_lookup.get(situation.get("occasion") or "") or {}).get("default_time"),
    )
    action_text = action.get("text") or action.get("preset") or ""
    barrier_label = barrier.get("label") or ""
    coping_text = coping.get("text") or coping.get("preset") or ""
    reminder_time = (reminder or {}).get("time")
    return (
        tpl.replace("{situation_and_time}", sit)
        .replace("{action}", action_phrase(action_text))
        .replace("{barrier}", barrier_phrase(barrier_label))
        .replace("{coping}", coping_phrase(coping_text))
        .replace("{reminder_time}", reminder_phrase(reminder_time))
    )


# --- Keep / add / replace ----------------------------------------------------

def apply_plan_management(
    *,
    choice: str,
    week1_plan: Optional[PlanRecord],
    draft_week2_plan: PlanRecord,
    now_iso: str,
) -> Dict[str, Any]:
    """Turn the student's answers into concrete DB writes.

    Returns a dict with three fields:
      - ``to_upsert``: list[(plan_id, PlanRecord)] — plans the server
        should upsert. Includes the Week 2 plan and (for 'replace')
        the Week 1 plan with status flipped.
      - ``cancel_reminders_for``: list[plan_id] — plans whose pending
        reminders must be cancelled by the server (dropped from
        db.plans_reminders).
      - ``summary_variant``: which completion-summary template to use.

    'keep_week1_only' saves the Week 2 answers as a KEPT record so the
    research export can see what the student planned without the
    engine mistakenly activating a reminder for it.
    """
    to_upsert: List[Tuple[str, PlanRecord]] = []
    cancel: List[str] = []

    if choice == "keep_and_add":
        new_plan = {**draft_week2_plan, "status": ACTIVE, "updated_at": now_iso}
        to_upsert.append((draft_week2_plan["id"], new_plan))
        # Week 1 plan untouched.
        variant = "full"
    elif choice == "replace":
        new_plan = {**draft_week2_plan, "status": ACTIVE, "updated_at": now_iso}
        to_upsert.append((draft_week2_plan["id"], new_plan))
        if week1_plan and week1_plan.get("status") != REPLACED:
            replaced = {**week1_plan, "status": REPLACED, "updated_at": now_iso, "replaced_at": now_iso}
            to_upsert.append((week1_plan["id"], replaced))
            cancel.append(week1_plan["id"])
        variant = "full"
    elif choice == "keep_week1_only":
        # Save the student's answers as a dormant record. No reminder.
        kept = {**draft_week2_plan, "status": KEPT, "reminder": {}, "updated_at": now_iso}
        to_upsert.append((draft_week2_plan["id"], kept))
        variant = "keep_only"
    else:
        raise ValueError(f"Unknown plan-management choice: {choice!r}")

    return {"to_upsert": to_upsert, "cancel_reminders_for": cancel, "summary_variant": variant}


# --- Week 1 plan materialisation --------------------------------------------

def week1_plan_from_user(
    user: Dict[str, Any],
    *,
    week1_reflection_responses: Optional[Dict[str, Any]] = None,
) -> Optional[PlanRecord]:
    """Synthesize a Week 1 plan from the user document + whatever
    occasion the student picked in the Week 1 reflection (p2_room).
    Returns None when the student has no focus area or goal yet
    (nothing to materialize). Called lazily when the Phase 2 planning
    step opens — the pilot migration (PR #38) doesn't populate
    ``db.plans``, so we have to backfill on demand."""
    focus_area = user.get("focus_area")
    goal_doc = user.get("focus_goal") or {}
    if not focus_area or not (goal_doc.get("goal") or goal_doc.get("plan")):
        return None
    occasion = None
    if week1_reflection_responses:
        p2 = (week1_reflection_responses or {}).get("p2_room") or {}
        occasion = p2.get("selected")
        if occasion and occasion.lower() == "not sure yet":
            occasion = None
    return make_plan(
        user_id=user["id"],
        source_week=1,
        focus_area=focus_area,
        focus_goal=goal_doc,
        situation={"setting": None, "day": None, "occasion": (occasion or "").lower() if occasion else None},
        action={"text": goal_doc.get("plan") or goal_doc.get("goal") or "", "source": "week1_goal"},
        barrier={},
        coping={},
        reminder={},
        status=ACTIVE,
        plan_id=f"{user['id']}:w1",
    )


# --- Public summary / card rendering ----------------------------------------

def plan_card_for_today(plan: PlanRecord, *, settings_lookup: Dict[str, str], occasions_lookup: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """A shaped dict for the Today 'This Week' card. The focus and
    goal come straight from the plan; the situation is formatted via
    ``situation_phrase`` so the UI doesn't duplicate the grammar
    rules."""
    situation = plan.get("situation") or {}
    occ = occasions_lookup.get(situation.get("occasion") or "") or {}
    sit = situation_phrase(
        day_label=situation.get("day_label"),
        occasion_label=occ.get("label"),
        setting_label=settings_lookup.get(situation.get("setting") or ""),
        custom_setting_text=situation.get("custom_setting_text"),
        occasion_time=occ.get("default_time"),
    )
    action = plan.get("action") or {}
    reminder = plan.get("reminder") or {}
    return {
        "id": plan.get("id"),
        "source_week": plan.get("source_week"),
        "status": plan.get("status"),
        "focus_area": plan.get("focus_area"),
        "goal": (plan.get("focus_goal") or {}).get("goal"),
        "situation_text": sit,
        "action_text": action.get("text"),
        "reminder_time": reminder.get("time"),
        "reminder_enabled": bool(reminder.get("time") and plan.get("status") == ACTIVE),
    }
