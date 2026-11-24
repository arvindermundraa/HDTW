"""Re-create Maya, the demo participant, in the llhs_ui_compare database.

Safe to run twice: every write is an upsert keyed on a stable `id` field,
so re-running tops the data up to the target (24 meals, 3 activities,
3 sleeps, 1 lesson, baseline HEI, focus areas, ring goals) instead of
duplicating rows.

NEVER writes to llhs_db — the live local database. If DB_NAME points at
anything other than llhs_ui_compare the script refuses and exits 1.

Run:
    cd ~/HDTW/backend && ./venv/bin/python scripts/seed_demo.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent
sys.path.insert(0, str(BACKEND))

import bcrypt
from motor.motor_asyncio import AsyncIOMotorClient

EMAIL = "maya.demo@example.com"
PASSWORD = "demo-pass-123"
NAME = "Maya Demo"
TIMEZONE = "America/Chicago"

# Reach fixed targets so the second run is a no-op, not a duplicator.
TARGET_MEALS = 24
TARGET_ACTIVITIES = 3
TARGET_SLEEPS = 3
LESSON_ID = "c1"

FOCUS_AREA = "grains"  # one of the eight areas (focus_areas.py)
FOCUS_AREAS = ["whole_grains", "refined_grains"]

# Baseline HEI assessment that puts Maya below the national benchmark on her
# three focus areas and comfortably above on a couple of strengths. Numbers
# are stored only in the hei_assessments collection; participants never see
# them (direction only, see §3 of the design rules).
BASELINE_HEI = {
    "total_fruits": 2.6,
    "whole_fruits": 3.4,
    "total_vegetables": 3.3,
    "greens_beans": 1.1,
    "whole_grains": 1.0,
    "dairy": 5.8,
    "total_protein_foods": 4.9,
    "seafood_plant_proteins": 3.0,
    "fatty_acids": 4.2,
    "refined_grains": 5.5,
    "sodium": 2.1,
    "added_sugars": 7.0,
    "saturated_fats": 5.0,
}


def _hash(pw: str) -> str:
    return bcrypt.hashpw(pw.encode("utf-8")[:72], bcrypt.gensalt()).decode()


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


async def _ensure_user(db) -> dict:
    existing = await db.users.find_one({"email": EMAIL})
    now = _iso(datetime.now(timezone.utc))
    fas_at = _iso(datetime.now(timezone.utc) - timedelta(days=10))
    base = {
        "email": EMAIL,
        "name": NAME,
        "onboarded": True,
        "profile": {"age_band": "18_25", "campus": "tamu"},
        "focus_area": FOCUS_AREA, "focus_areas": FOCUS_AREAS,
        "focus_goal": {"goal": "Pick brown rice or whole-wheat bread", "plan": "At lunch on weekdays"},
        "focus_areas_set_at": fas_at,
        "allergy_terms": [],
        "points": 220,
        "badges": ["First Lesson"],
        "wearable_connected": False,
        "wearable_provider": None,
        "wearable_last_sync": None,
        "nudges_enabled": False,
        "nudge_time": "19:00",
        "tamus_api_key_encrypted": None,
        "tamus_model_chat": None,
        "tamus_model_vision": None,
    }
    if existing:
        await db.users.update_one({"_id": existing["_id"]}, {"$set": base})
        existing.update(base)
        return existing
    new = {
        "id": "demo-maya",
        "password": _hash(PASSWORD),
        "created_at": now,
        **base,
    }
    await db.users.insert_one(new)
    return new


async def _ensure_hei(db, uid: str) -> None:
    recorded = _iso(datetime.now(timezone.utc) - timedelta(days=12))
    doc = {
        "id": "demo-maya-hei-baseline",
        "user_id": uid,
        "assessment_type": "baseline",
        "components": BASELINE_HEI,
        "source": "seed_demo",
        "recorded_at": recorded,
    }
    await db.hei_assessments.update_one(
        {"id": doc["id"]}, {"$set": doc}, upsert=True
    )


# Representative 2-week log pattern. The exact tags matter for Eat screen
# strengths/focus areas; the pattern deliberately logs vegetables most days
# so her Eat ring stays interesting.
MEAL_PATTERN = [
    ("Oats with berries", "breakfast", ["whole_grains", "fruit"]),
    ("Caprese salad", "lunch", ["vegetables", "dairy"]),
    ("Chicken rice bowl", "dinner", ["other_protein", "refined_grains_starchy"]),
    ("Greek yogurt", "snack", ["dairy", "fruit"]),
    ("Avocado toast", "breakfast", ["whole_grains", "vegetables"]),
    ("Lentil soup", "lunch", ["beans_fish_nuts", "vegetables"]),
    ("Grilled salmon with greens", "dinner", ["beans_fish_nuts", "vegetables"]),
    ("Apple with peanut butter", "snack", ["fruit", "beans_fish_nuts"]),
    ("Scrambled eggs & toast", "breakfast", ["other_protein", "refined_grains_starchy"]),
    ("Veggie wrap", "lunch", ["vegetables", "whole_grains"]),
    ("Stir-fry tofu & brown rice", "dinner", ["beans_fish_nuts", "whole_grains", "vegetables"]),
    ("Carrots & hummus", "snack", ["vegetables", "beans_fish_nuts"]),
]


async def _ensure_meals(db, uid: str) -> None:
    pattern = MEAL_PATTERN * ((TARGET_MEALS // len(MEAL_PATTERN)) + 1)
    pattern = pattern[:TARGET_MEALS]
    # Spread the 24 meals across the last 12 days (ending today) so the
    # 7-day strip has data every day, and today has one veg-tagged meal
    # so the avatar's "salad" prop and non-zero ring progress are visible.
    base_day = datetime.now(timezone.utc) - timedelta(days=11)
    hours_in_day = [8, 12, 18, 15]  # breakfast/lunch/dinner/snack-ish
    for idx, (name, kind, cats) in enumerate(pattern):
        day_offset = idx // 2
        hour = hours_in_day[idx % len(hours_in_day)]
        when = base_day + timedelta(days=day_offset, hours=hour)
        doc = {
            "id": f"demo-maya-meal-{idx:02d}",
            "user_id": uid,
            "created_at": _iso(when),
            "name": name,
            "source": "text",
            "meal_type": kind,
            "items": [],
            "categories": cats,
            "portion": "normal",
            "skipped": False,
            "confirmed": True,
        }
        await db.meals.update_one({"id": doc["id"]}, {"$set": doc}, upsert=True)


async def _ensure_activities(db, uid: str) -> None:
    # One of the three activities is today so the avatar's "sneakers"
    # prop shows up on the smoke test.
    recents = [
        ("walk", 35, 0),
        ("run", 25, 3),
        ("yoga", 40, 6),
    ]
    for idx, (kind, minutes, days_ago) in enumerate(recents):
        when = datetime.now(timezone.utc) - timedelta(days=days_ago, hours=1)
        doc = {
            "id": f"demo-maya-act-{idx:02d}",
            "user_id": uid,
            "created_at": _iso(when),
            "minutes": minutes,
            "kind": kind,
        }
        await db.activities.update_one({"id": doc["id"]}, {"$set": doc}, upsert=True)


async def _ensure_sleeps(db, uid: str) -> None:
    # Today's sleep belongs to this morning (last night's sleep logged
    # today), so the avatar's "rested" prop shows up.
    recents = [(7.5, 0), (8.0, 1), (6.5, 2)]
    for idx, (hours, days_ago) in enumerate(recents):
        when = datetime.now(timezone.utc) - timedelta(days=days_ago, hours=16)
        doc = {
            "id": f"demo-maya-sleep-{idx:02d}",
            "user_id": uid,
            "created_at": _iso(when),
            "hours": hours,
            "source": "manual",
        }
        await db.sleeps.update_one({"id": doc["id"]}, {"$set": doc}, upsert=True)


async def _ensure_lesson(db, uid: str) -> None:
    doc = {
        "id": "demo-maya-lesson-c1",
        "user_id": uid,
        "kind": "video",
        "ref": LESSON_ID,
        "created_at": _iso(datetime.now(timezone.utc) - timedelta(days=4)),
    }
    await db.completions.update_one({"id": doc["id"]}, {"$set": doc}, upsert=True)


async def _ensure_ring_goals(db, uid: str) -> None:
    # First goals start the same day they were saved; this seed records the
    # ring targets as if Maya set them up a week ago, so the 7-day strip has
    # already been active for the whole window.
    seven_days_ago = (datetime.now(timezone.utc) - timedelta(days=7)).date().isoformat()
    plans = {
        "food": [{"start_date": seven_days_ago, "enabled": True, "target": 2, "category": "vegetables"}],
        "move": [{"start_date": seven_days_ago, "enabled": True, "target": 30, "category": None}],
        "rest": [{"start_date": seven_days_ago, "enabled": True, "target": 8, "category": None}],
    }
    await db.daily_goal_plans.update_one(
        {"_id": uid},
        {"$set": {"timezone": TIMEZONE, "plans": plans}},
        upsert=True,
    )


async def main() -> int:
    db_name = os.environ.get("DB_NAME", "").strip()
    if db_name != "llhs_ui_compare":
        print(
            f"refusing to seed into DB_NAME={db_name!r}; "
            "set DB_NAME=llhs_ui_compare before running",
            file=sys.stderr,
        )
        return 1
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    user = await _ensure_user(db)
    uid = user["id"]
    await _ensure_hei(db, uid)
    await _ensure_meals(db, uid)
    await _ensure_activities(db, uid)
    await _ensure_sleeps(db, uid)
    await _ensure_lesson(db, uid)
    await _ensure_ring_goals(db, uid)

    counts = {
        "meals": await db.meals.count_documents({"user_id": uid}),
        "activities": await db.activities.count_documents({"user_id": uid}),
        "sleeps": await db.sleeps.count_documents({"user_id": uid}),
        "completions": await db.completions.count_documents({"user_id": uid}),
        "hei_assessments": await db.hei_assessments.count_documents({"user_id": uid}),
    }
    print(f"seeded {EMAIL} ({uid}) in {db_name}:")
    for k, v in counts.items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
