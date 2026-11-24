"""The behavioral twin — noticing possible patterns across diet, activity
and sleep, so Future Me can ASK about them.

The study team's direction (2026-11): the twin should learn each
participant's routines across the three behavioral components of the AHA's
Life's Essential 8 framework (diet, physical activity, sleep) — never a
combined LE8 score, which this app deliberately doesn't compute — and it
must not make unsupported assumptions about why a behavior happens. So
everything here produces a *possible* pattern with its evidence and a
question; nothing becomes part of the participant's profile until they
answer it (twin_profile.py), and nothing drives a recommendation until it
is confirmed (twin_recommend.py).

Design rules, the same as twin_habits.py:
  * Deterministic and explainable. Medians and counts over the trailing
    window, with the evidence shown to the participant in plain counts
    ("On 6 of the 8 weekdays your tracker has, you moved less than on a
    usual weekend day").
  * Honest about sparse data. A day with no activity row is not a day of
    no activity; a night with no sleep row is not a short night; a meal
    that wasn't logged was not skipped (only an explicit "skipped" log
    counts). Each detector says nothing until it has enough days.
  * No body or outcome numbers. Only counts of logged days and clock
    times the participant's own tracker or log reported.
  * Thresholds are named constants, placeholders until the study team
    confirms them (docs/CHANGELOG-2026-11-11.md lists them).

Pure functions only (no database, no network).
"""
from datetime import date, timedelta
from statistics import median
from typing import Dict, List, Optional

from study_time import study_day_key

WINDOW_DAYS = 21                    # same three weeks as the meal regulars
WEEKDAYS = (0, 1, 2, 3, 4)          # Monday..Friday

# Activity
ACT_MIN_WEEKDAYS = 4                # weekdays with activity data before comparing
ACT_MIN_WEEKEND_DAYS = 2
ACT_RATIO = 0.6                     # weekday median below 60% of the weekend median ...
ACT_MIN_GAP_MINUTES = 15            # ... and at least this many minutes lower
ACT_ALREADY_ACTIVE_MINUTES = 45     # a weekday median this high is never called "low"
ACT_READY_DAYS = 6                  # days with data before the domain counts as "ready"

# Sleep
SLEEP_MIN_TIMED_NIGHTS = 5          # nights with a bedtime before judging timing
SLEEP_SPREAD_MINUTES = 90           # bedtime range (outliers trimmed) at or above this = irregular
SLEEP_SHIFT_MINUTES = 90            # weekday vs weekend bedtime shift at or above this = irregular
SLEEP_MIN_WEEKDAY_NIGHTS = 4        # class-day nights (wake Mon-Fri) before comparing durations
SLEEP_MIN_WEEKEND_NIGHTS = 2
SLEEP_SHORT_GAP_HOURS = 1.0         # weekday median this much below weekend = shorter weekday sleep
SLEEP_READY_NIGHTS = 5

# Breakfast (explicit "skipped" logs only; see ASK_ABOUT_SKIPPED_BREAKFAST)
BREAKFAST_MIN_SKIPPED_WEEKDAYS = 3
# Whether the twin may raise skipped weekday breakfasts as a question at
# all. On by default because the study team's cross-domain example names
# limited time for breakfast; the twin also never raises it while a safety
# check-in is recent (see `paused` in detect_all). A decision for the team.
ASK_ABOUT_SKIPPED_BREAKFAST = True

# The circumstances a participant can name when they confirm a pattern.
# Each becomes a "stated" fact in their profile (twin_profile), and some
# recommendations fit some circumstances (twin_recommend). Labels are what
# the chip says; `fact` is how the profile says it back to them.
CIRCUMSTANCES: Dict[str, Dict[str, str]] = {
    "early_classes": {"label": "Early classes", "fact": "You have early classes"},
    "back_to_back_classes": {"label": "Classes back to back", "fact": "Your classes run back to back"},
    "late_classes_work": {"label": "Late classes or work", "fact": "You have late classes or work"},
    "work_shifts": {"label": "Work shifts", "fact": "Work shifts shape your week"},
    "studying_late": {"label": "Studying late", "fact": "You often study late"},
    "commute": {"label": "Commute", "fact": "Your commute takes time"},
    "prefer_weekends": {"label": "I'd rather move on weekends", "fact": "You'd rather move on weekends"},
    "rest_days": {"label": "Weekends are my rest days", "fact": "Weekends are your rest days"},
    "no_routine": {"label": "No set routine", "fact": "Your days don't follow a set routine"},
    "roommates_noise": {"label": "Roommates or noise", "fact": "Roommates or noise affect your sleep"},
    "screens_winding_down": {"label": "Phone or screens at night", "fact": "Your phone keeps you up some nights"},
    "no_time_morning": {"label": "No time in the morning", "fact": "Mornings are rushed"},
    "not_hungry_early": {"label": "Not hungry early", "fact": "You're not hungry early in the day"},
    "nothing_nearby": {"label": "Nothing nearby to grab", "fact": "There's nothing nearby to grab in the morning"},
    "like_it": {"label": "I like it", "fact": "You like it", "scope": "item"},
    "quick": {"label": "It's quick", "fact": "Quick options matter to you"},
    "cheap": {"label": "It's cheap", "fact": "Cost matters to you"},
    "whats_available": {"label": "It's what's available", "fact": "You go with what's available"},
    "someone_else_picks": {"label": "Someone else picks", "fact": "Someone else often picks your food"},
    "other": {"label": "Something else", "fact": "Something else is going on"},
}

# Circumstances that also tell the twin what to respect in every step
# (twin_profile.build_state adds them to the constraints).
CIRCUMSTANCE_CONSTRAINTS = {"cheap": "cost", "quick": "time", "someone_else_picks": "someone_else"}

# Circumstances that say something about the participant's schedule — a
# stated one can stand in for a second detected weekday signal when the
# twin looks for a pattern across domains.
SCHEDULE_CIRCUMSTANCES = {"early_classes", "back_to_back_classes", "work_shifts", "late_classes_work", "studying_late",
                          "commute"}


# ---- reading the logs ---------------------------------------------------------------
def _day_of(row: dict) -> str:
    """The day a row describes: a device row's recorded_date, otherwise
    the study-time day it was logged on."""
    rd = row.get("recorded_date")
    if isinstance(rd, str) and len(rd) == 10:
        return rd
    iso = row.get("created_at") or ""
    try:
        return study_day_key(iso) if isinstance(iso, str) and iso else ""
    except (ValueError, TypeError):
        return ""  # a malformed timestamp is skipped, never a crash


def _in_window(day: str, today: date, window_days: int) -> bool:
    return bool(day) and (today - timedelta(days=window_days - 1)).isoformat() <= day <= today.isoformat()


def _is_weekday(day: str) -> bool:
    return date.fromisoformat(day).weekday() in WEEKDAYS


def activity_days(activities: List[dict], today: date, window_days: int = WINDOW_DAYS) -> Dict[str, dict]:
    """Minutes per day with data. A day the tracker covers uses the
    tracker's reading (the latest sync for that date — a device re-sends
    days); otherwise the manual logs for that day are added up. Days with
    no rows at all are absent, never zero."""
    wearable: Dict[str, dict] = {}
    manual: Dict[str, int] = {}
    for a in activities:
        day = _day_of(a)
        if not _in_window(day, today, window_days):
            continue
        minutes = a.get("minutes")
        if isinstance(minutes, bool) or not isinstance(minutes, (int, float)) or minutes < 0:
            continue
        if a.get("source") == "wearable":
            prev = wearable.get(day)
            if prev is None or str(a.get("created_at") or "") >= prev["_at"]:
                wearable[day] = {"minutes": int(minutes), "steps": a.get("steps"), "_at": str(a.get("created_at") or "")}
        else:
            manual[day] = manual.get(day, 0) + int(minutes)
    out: Dict[str, dict] = {}
    for day in set(wearable) | set(manual):
        if day in wearable:
            out[day] = {"minutes": wearable[day]["minutes"], "steps": wearable[day]["steps"], "source": "wearable"}
        else:
            out[day] = {"minutes": manual[day], "steps": None, "source": "manual"}
    return out


def _clock_minutes(value) -> Optional[int]:
    if not isinstance(value, str) or len(value) != 5 or value[2] != ":":
        return None
    try:
        h, m = int(value[:2]), int(value[3:])
    except ValueError:
        return None
    if not (0 <= h < 24 and 0 <= m < 60):
        return None
    return h * 60 + m


def _from_noon(minutes: int) -> int:
    """Bedtimes straddle midnight; measured from noon they sort and
    average properly (11 pm = 660, 1 am = 780)."""
    return (minutes - 720) % 1440


def clock_words(from_noon: int) -> str:
    """A bedtime as plain words, rounded to the half hour: "11:30 pm"."""
    total = (int(round(from_noon / 30.0)) * 30 + 720) % 1440
    h, m = divmod(total, 60)
    suffix = "am" if h < 12 else "pm"
    h12 = h % 12 or 12
    return f"{h12}:{m:02d} {suffix}" if m else f"{h12} {suffix}"


def sleep_nights(sleeps: List[dict], today: date, window_days: int = WINDOW_DAYS) -> Dict[str, dict]:
    """One reading per night, keyed by the day they woke up: the tracker's
    when there is one (latest sync wins), otherwise their latest manual
    log that day."""
    out: Dict[str, dict] = {}
    for s in sleeps:
        day = _day_of(s)
        if not _in_window(day, today, window_days):
            continue
        hours = s.get("hours")
        if isinstance(hours, bool) or not isinstance(hours, (int, float)) or hours <= 0:
            continue
        rank = (1 if s.get("source") == "wearable" else 0, str(s.get("created_at") or ""))
        prev = out.get(day)
        if prev is not None and prev["_rank"] >= rank:
            continue
        bed = _clock_minutes(s.get("bedtime"))
        wake = _clock_minutes(s.get("wake"))
        out[day] = {"hours": float(hours), "bed": _from_noon(bed) if bed is not None else None,
                    "wake": wake, "source": "wearable" if s.get("source") == "wearable" else "manual", "_rank": rank}
    for v in out.values():
        v.pop("_rank", None)
    return out


# ---- detectors ------------------------------------------------------------------------
def _pattern(key: str, domain: str, label: str, question: str, evidence: str, circumstances: List[str],
             detail: Optional[dict] = None, strength: int = 1) -> dict:
    return {"key": key, "domain": domain, "label": label, "question": question, "evidence": evidence,
            "circumstances": circumstances, "detail": detail or {}, "strength": strength}


def detect_activity(days: Dict[str, dict]) -> List[dict]:
    """A weekday/weekend difference in movement, either way round."""
    weekday = [v["minutes"] for d, v in days.items() if _is_weekday(d)]
    weekend = [v["minutes"] for d, v in days.items() if not _is_weekday(d)]
    if len(weekday) < ACT_MIN_WEEKDAYS or len(weekend) < ACT_MIN_WEEKEND_DAYS:
        return []
    wd, we = median(weekday), median(weekend)
    tracker = any(v["source"] == "wearable" for v in days.values())
    src = "your tracker has" if tracker else "you logged movement on"
    if wd < ACT_RATIO * we and we - wd >= ACT_MIN_GAP_MINUTES and wd < ACT_ALREADY_ACTIVE_MINUTES:
        lower = sum(1 for m in weekday if m < we)
        return [_pattern(
            "activity.low_weekdays", "activity", "Weekdays are harder to fit movement into",
            "Are weekdays harder to fit movement into?",
            f"On {lower} of the {len(weekday)} weekdays {src}, you moved less than on a usual weekend day.",
            ["back_to_back_classes", "work_shifts", "studying_late", "commute", "prefer_weekends", "other"],
            {"weekday_days": len(weekday), "weekend_days": len(weekend)}, strength=2)]
    if we < ACT_RATIO * wd and wd - we >= ACT_MIN_GAP_MINUTES and we < ACT_ALREADY_ACTIVE_MINUTES:
        lower = sum(1 for m in weekend if m < wd)
        return [_pattern(
            "activity.low_weekends", "activity", "Weekends are quieter for movement",
            "Do weekends tend to be quieter for you?",
            f"On {lower} of the {len(weekend)} weekend days {src}, you moved less than on a usual weekday.",
            ["rest_days", "work_shifts", "no_routine", "other"],
            {"weekday_days": len(weekday), "weekend_days": len(weekend)})]
    return []


def _trimmed(values: List[int]) -> List[int]:
    vals = sorted(values)
    return vals[1:-1] if len(vals) >= 7 else vals  # one odd night each way doesn't make a pattern


def detect_sleep(nights: Dict[str, dict]) -> List[dict]:
    """Irregular bedtimes (a wide range, or a big weekday/weekend shift),
    and shorter sleep before class days."""
    out: List[dict] = []
    timed = {d: v for d, v in nights.items() if v.get("bed") is not None}
    if len(timed) >= SLEEP_MIN_TIMED_NIGHTS:
        beds = _trimmed([v["bed"] for v in timed.values()])
        spread = beds[-1] - beds[0]
        wd = [v["bed"] for d, v in timed.items() if _is_weekday(d)]
        we = [v["bed"] for d, v in timed.items() if not _is_weekday(d)]
        shift = abs(median(we) - median(wd)) if len(wd) >= 3 and len(we) >= 2 else 0
        if spread >= SLEEP_SPREAD_MINUTES or shift >= SLEEP_SHIFT_MINUTES:
            if shift >= SLEEP_SHIFT_MINUTES and spread < SLEEP_SPREAD_MINUTES * 1.5:
                later = "later" if median(we) > median(wd) else "earlier"
                evidence = (f"Across {len(timed)} nights, your bedtime was usually around {clock_words(median(wd))} "
                            f"before class days and {later}, around {clock_words(median(we))}, on weekends.")
                kind = "weekend_shift"
            else:
                evidence = (f"Across {len(timed)} nights, your bedtime ranged from about {clock_words(beds[0])} "
                            f"to about {clock_words(beds[-1])}.")
                kind = "spread"
            out.append(_pattern(
                "sleep.irregular_timing", "sleep", "Your bedtime changes a lot from night to night",
                "Does your bedtime change a lot from night to night?", evidence,
                ["late_classes_work", "studying_late", "roommates_noise", "screens_winding_down", "early_classes", "other"],
                {"nights": len(timed), "kind": kind}, strength=2))
    wd_h = [v["hours"] for d, v in nights.items() if _is_weekday(d)]
    we_h = [v["hours"] for d, v in nights.items() if not _is_weekday(d)]
    if len(wd_h) >= SLEEP_MIN_WEEKDAY_NIGHTS and len(we_h) >= SLEEP_MIN_WEEKEND_NIGHTS \
            and median(wd_h) <= median(we_h) - SLEEP_SHORT_GAP_HOURS:
        shorter = sum(1 for h in wd_h if h < median(we_h))
        out.append(_pattern(
            "sleep.short_weekdays", "sleep", "You get less sleep before class days",
            "Do you tend to get less sleep before class days?",
            f"On {shorter} of {len(wd_h)} class-day mornings, you had slept less than on a usual weekend night.",
            ["early_classes", "studying_late", "work_shifts", "commute", "other"],
            {"weekday_nights": len(wd_h), "weekend_nights": len(we_h)}, strength=2))
    return out


def detect_breakfast(meals: List[dict], today: date, window_days: int = WINDOW_DAYS) -> List[dict]:
    """Weekday mornings the participant marked breakfast as skipped
    themselves. An unlogged breakfast is never counted."""
    if not ASK_ABOUT_SKIPPED_BREAKFAST:
        return []
    days = set()
    for m in meals:
        if not m.get("skipped") or m.get("meal_type") != "breakfast":
            continue
        day = _day_of({"created_at": m.get("created_at")})
        if _in_window(day, today, window_days) and _is_weekday(day):
            days.add(day)
    if len(days) < BREAKFAST_MIN_SKIPPED_WEEKDAYS:
        return []
    return [_pattern(
        "diet.rushed_weekday_breakfast", "diet", "Mornings are rushed on class days",
        "Are mornings rushed on class days?",
        f"Breakfast was marked skipped on {len(days)} weekday mornings in the last three weeks.",
        ["no_time_morning", "early_classes", "not_hungry_early", "nothing_nearby", "other"],
        {"weekdays": len(days)})]


def regular_key(habit: dict) -> str:
    """The profile key for a meal regular: the lexicon id when there is one
    (stable across both engines), otherwise a slug of the name the AI
    engine gave it in the participant's own words."""
    fid = habit.get("food_id")
    if fid:
        return f"diet.regular.{fid}"
    slug = "".join(ch if ch.isalnum() else "_" for ch in str(habit.get("label") or "").lower()).strip("_")
    return f"diet.regular.{slug[:40] or 'food'}"


def regular_patterns(habits: List[dict], evidence_lines: Dict[str, str]) -> List[dict]:
    """A meal regular noticed in the logs becomes a question before it is
    treated as a habit: "Is whole-milk yogurt a regular breakfast for you?"
    `evidence_lines` maps the habit's key to the evidence line the
    From-your-meals card already shows."""
    out = []
    for h in habits:
        key = regular_key(h)
        slot = h.get("top_slot") or "snack"
        when = "a regular snack" if slot == "snack" else f"a regular {slot}"
        out.append(_pattern(
            key, "diet", f"{h['label'][:1].upper()}{h['label'][1:]} is {when} for you",
            f"Is {h['label']} {when} for you?", evidence_lines.get(key) or "",
            ["like_it", "quick", "cheap", "whats_available", "someone_else_picks", "other"],
            {"food_id": h.get("food_id"), "label": h["label"], "slot": slot, "times": h.get("times")},
            strength=2))  # a regular with a swap for their focus area gates that swap, so it's asked early
    return out


def detect_cross(patterns: List[dict], stated: set) -> List[dict]:
    """Weekday signals in more than one domain — or one, plus a schedule
    the participant already told us about — become ONE question about what
    they share, instead of three separate ones."""
    parts = []
    names = {"sleep.short_weekdays": "shorter sleep", "diet.rushed_weekday_breakfast": "breakfast missed more often",
             "activity.low_weekdays": "less movement"}
    keys = {p["key"] for p in patterns}
    for k in ("sleep.short_weekdays", "diet.rushed_weekday_breakfast", "activity.low_weekdays"):
        if k in keys:
            parts.append(k)
    schedule = sorted(stated & SCHEDULE_CIRCUMSTANCES)
    if len(parts) < 2 and not (parts and schedule):
        return []
    words = [names[k] for k in parts]
    listed = words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1]
    evidence = f"Weekdays look tighter than weekends: {listed}."
    if len(parts) == 1:
        evidence += " You also mentioned your schedule."
    return [_pattern(
        "cross.weekday_squeeze", "cross", "Your weekday schedule squeezes sleep, meals and movement",
        "Is your class or work schedule the main thing squeezing your weekdays?", evidence,
        ["early_classes", "back_to_back_classes", "work_shifts", "studying_late", "commute", "other"],
        {"parts": parts, "stated_schedule": schedule}, strength=3)]


def domain_status(act_days: Dict[str, dict], nights: Dict[str, dict]) -> Dict[str, str]:
    def level(n, ready):
        return "no_data" if n == 0 else ("learning" if n < ready else "ready")
    return {"activity": level(len(act_days), ACT_READY_DAYS), "sleep": level(len(nights), SLEEP_READY_NIGHTS)}


def detect_all(meals: List[dict], activities: List[dict], sleeps: List[dict], today: date, stated: set,
               paused: bool = False) -> dict:
    """Every possible pattern the twin could ask about now, with per-domain
    data status. `stated` is the participant's stated circumstances (for
    the cross-domain check); `paused` (a recent safety check-in) keeps
    anything about meals out."""
    act = activity_days(activities, today)
    nights = sleep_nights(sleeps, today)
    patterns = detect_activity(act) + detect_sleep(nights)
    if not paused:
        patterns += detect_breakfast(meals, today)
    patterns += detect_cross(patterns, stated)
    return {"patterns": patterns, "status": domain_status(act, nights),
            "counts": {"activity_days": len(act), "sleep_nights": len(nights),
                       "timed_nights": sum(1 for v in nights.values() if v.get("bed") is not None)}}
