"""Personal daily habits derived from logs; independent of HEI and health scores.

Every day / week boundary here goes through `study_time.py`. Timestamps on
disk stay in UTC; what changes is how a given moment is bucketed into a
day. Older clients may still send a `?tz=` query param or a `timezone`
field in the goal body — both are accepted and ignored so a stale app
build doesn't 422. The stored `profile.timezone` field is left in place
for existing documents but is no longer read.
"""
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import avatar
from study_time import STUDY_TZ, study_today, study_week_window, study_day_key, study_day_start_utc_iso

DOMAINS = ("food", "move", "rest")
FOODS = {
    "vegetables": "vegetables", "fruit": "fruit", "whole_grains": "whole grains",
    "beans_fish_nuts": "beans, fish, or nuts", "dairy": "dairy",
    "other_protein": "protein foods",
}


class DailyGoalIn(BaseModel):
    target: float = Field(gt=0, le=600, allow_inf_nan=False)
    category: Optional[Literal["vegetables", "fruit", "whole_grains", "beans_fish_nuts", "dairy", "other_protein"]] = None
    # Older clients still send this; it is accepted and ignored. The server
    # owns "today" via STUDY_TZ now, same for every participant.
    timezone: Optional[str] = Field(default=None, max_length=80)


def goal_label(domain, plan):
    target = f"{plan['target']:g}"
    if domain == "food":
        # The Eat ring is activity-oriented: it fills once a meal is logged, with
        # no required daily count. The chosen food group is a focus — a prompt
        # for what to add — not a quota.
        if plan.get("category") in FOODS:
            return f"Log a meal — add {FOODS[plan['category']]} when you can"
        return "Log a meal when you're ready"
    if domain == "move":
        return f"Move for {target} minutes"
    return f"Aim for {target} hours of sleep"


def active_plan(versions, day):
    eligible = [v for v in versions if v["start_date"] <= day]
    return max(eligible, key=lambda v: v["start_date"]) if eligible else None


def _counts(log):
    return not (log.get("source") == "wearable" or log.get("kind") == "wearable" or log.get("simulated"))


def week_move_minutes(logs, first_day: str, last_day: str) -> float:
    """Movement minutes logged over the 7-day study-TZ window. A small
    secondary line toward ~150 min/week (pending team sign-off)."""
    total = 0
    for log in {l["id"]: l for l in logs if _counts(l)}.values():
        if first_day <= study_day_key(log["created_at"]) <= last_day:
            total += max(0, log.get("minutes", 0))
    return round(total, 2)


def week_days_logged(logs, first_day: str, last_day: str) -> dict:
    """Days with at least one real log, per domain, over the 7-day STUDY_TZ
    window (inclusive bounds). ``logs`` is the same ``{food, move, rest}``
    dict passed to :func:`build_snapshot`.

    This is the single source of truth every screen reads from — Today's
    week strip, Future Me's week line and Progress's streaks all go
    through here so the numbers can never disagree. Skipped meals don't
    count (same rule as the Eat ring); simulated / wearable entries are
    excluded by ``_counts`` (same rule as everywhere else).
    """
    def _day_keys(rows, drop_skipped=False):
        return {
            study_day_key(r["created_at"])
            for r in rows
            if _counts(r)
            and first_day <= study_day_key(r["created_at"]) <= last_day
            and not (drop_skipped and r.get("skipped"))
        }

    eat = _day_keys(logs.get("food", []), drop_skipped=True)
    move = _day_keys(logs.get("move", []))
    rest = _day_keys(logs.get("rest", []))
    return {
        "eat_days": len(eat),
        "move_days": len(move),
        "rest_days": len(rest),
        "any_days": len(eat | move | rest),
    }


def daily_progress(domain, plan, logs, day: str):
    """Count distinct confirmed meals, sum movement, use latest manual sleep.

    A sleep entry describes last night's sleep and belongs to its logging
    day (keyed in the study TZ). Wearable data is excluded until the
    existing simulated integration is real.
    """
    entries = {}
    for log in logs:
        if not _counts(log):
            continue
        if study_day_key(log["created_at"]) == day:
            entries[log["id"]] = log
    records = list(entries.values())
    if domain == "food":
        # Count any confirmed, non-skipped meal — the ring is about logging
        # activity, not meeting a per-day meal count. The category stored on
        # the plan is still used for focus-area milestones and coaching, just
        # not for whether the ring is "closed".
        value = sum(1 for log in records if not log.get("skipped") and log.get("confirmed", True))
        return {**plan, "domain": domain, "label": goal_label(domain, plan),
                "value": int(value), "target": 1,
                "ratio": 1.0 if value >= 1 else 0.0,
                "complete": value >= 1}
    if domain == "move":
        value = sum(max(0, log.get("minutes", 0)) for log in records)
    else:
        latest = max(records, key=lambda log: log["created_at"], default=None)
        value = max(0, latest.get("hours", 0)) if latest else 0
    return {**plan, "domain": domain, "label": goal_label(domain, plan),
            "value": round(value, 2), "ratio": min(1, value / plan["target"]),
            "complete": value >= plan["target"]}


def build_snapshot(profile, logs, now=None):
    """`now` is accepted for backwards-compat with existing callers / tests
    but is intentionally unused — "today" is `study_today()` now."""
    del now
    today = study_today()
    plans = profile.get("plans", {})
    days = []
    for offset in range(6, -1, -1):
        day = (today - timedelta(days=offset)).isoformat()
        goals = []
        for domain in DOMAINS:
            plan = active_plan(plans.get(domain, []), day)
            if plan and plan["enabled"]:
                goals.append(daily_progress(domain, plan, logs[domain], day))
        days.append({"date": day, "goals": goals})
    tomorrow = (today + timedelta(days=1)).isoformat()
    # One mood for every screen; it depends only on today, so it resets daily.
    mood = avatar.daily_mood(days[-1]["goals"], logs, today.isoformat())
    first_day, last_day = study_week_window(7)
    first_iso, last_iso = first_day.isoformat(), last_day.isoformat()
    week = {
        "move_minutes": week_move_minutes(logs.get("move", []), first_iso, last_iso),
        "move_reference_minutes": 150,
        **week_days_logged(logs, first_iso, last_iso),
    }
    return {"today": today.isoformat(), "timezone": str(STUDY_TZ), "days": days, "mood": mood, "week": week,
            "pending": [{"domain": domain, **v} for domain in DOMAINS
                        for v in plans.get(domain, []) if v["start_date"] == tomorrow]}


def make_router(db, current_user, now_utc):
    router = APIRouter(prefix="/api/daily-goals", tags=["Daily goals"])

    async def profile_for(uid):
        # Mongo's _id is unique: one settings record per student. The
        # stored `timezone` field is kept for compatibility; nothing reads
        # it any more.
        await db.daily_goal_plans.update_one({"_id": uid}, {"$setOnInsert": {
            "timezone": str(STUDY_TZ), "plans": {},
        }}, upsert=True)
        return await db.daily_goal_plans.find_one({"_id": uid})

    @router.get("")
    async def get_progress(tz: Optional[str] = None, user: dict = Depends(current_user)):
        # `tz` is accepted (older clients still send it) and ignored.
        del tz
        profile = await db.daily_goal_plans.find_one({"_id": user["id"]})
        if not profile:
            # No rings yet — nothing is saved, but the avatar's mood still
            # reflects today's logs in the study TZ so every screen agrees.
            snap = build_snapshot({"timezone": str(STUDY_TZ), "plans": {}},
                                  await logs_since(user["id"], 6))
            return {"today": None, "timezone": None, "days": [], "pending": [], "mood": snap["mood"]}
        return build_snapshot(profile, await logs_since(user["id"], 6))

    async def logs_since(uid, days_back):
        first = study_today() - timedelta(days=days_back)
        start = study_day_start_utc_iso(first)
        end = now_utc().isoformat()
        query = {"user_id": uid, "created_at": {"$gte": start, "$lte": end}}
        logs = {}
        for domain, collection in (("food", db.meals), ("move", db.activities), ("rest", db.sleeps)):
            logs[domain] = [doc async for doc in collection.find(query)]
        return logs

    async def save_version(uid, domain, version):
        field = f"plans.{domain}"
        # Atomic per-domain update prevents simultaneous Food and Move saves
        # from overwriting each other. A new pending choice replaces the old one.
        await db.daily_goal_plans.update_one({"_id": uid}, [{"$set": {field: {
            "$concatArrays": [{"$filter": {"input": {"$ifNull": [f"${field}", []]},
                "as": "v", "cond": {"$lt": ["$$v.start_date", version["start_date"]]}}},
                {"$literal": [version]}]
        }}}])
        return {"effective_date": version["start_date"], "timezone": str(STUDY_TZ)}

    @router.put("/{domain}")
    async def set_goal(domain: Literal["food", "move", "rest"], body: DailyGoalIn,
                       user: dict = Depends(current_user)):
        if domain == "food" and (body.category is None or body.target > 4 or not body.target.is_integer()):
            raise HTTPException(422, "Choose a food group and a target of 1–4 meals.")
        if domain != "food" and body.category is not None:
            raise HTTPException(422, "Food groups apply only to Food goals.")
        if domain == "move" and not body.target.is_integer():
            raise HTTPException(422, "Movement minutes must be a whole number.")
        if domain == "rest" and (body.target > 16 or body.target * 2 % 1):
            raise HTTPException(422, "Sleep targets use half-hour steps, up to 16 hours.")
        profile = await profile_for(user["id"])
        today = study_today()
        versions = profile["plans"].get(domain, [])
        # First goal starts today. All subsequent changes begin tomorrow.
        # "Tomorrow" is the study TZ's tomorrow — not the phone's — so a
        # change made at 11 PM Chicago starts at 00:00 Chicago, not 00:00
        # UTC (which was already yesterday for the student).
        effective = today + timedelta(days=1) if versions else today
        version = {"start_date": effective.isoformat(), "enabled": True,
                   "target": body.target, "category": body.category}
        return await save_version(user["id"], domain, version)

    @router.delete("/{domain}")
    async def pause_goal(domain: Literal["food", "move", "rest"], user: dict = Depends(current_user)):
        profile = await db.daily_goal_plans.find_one({"_id": user["id"]})
        if not profile or not profile["plans"].get(domain):
            raise HTTPException(404, "No goal to pause.")
        tomorrow = study_today() + timedelta(days=1)
        return await save_version(user["id"], domain,
                                  {"start_date": tomorrow.isoformat(), "enabled": False})

    return router
