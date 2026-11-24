"""The participant's avatar: chosen once, plus a daily mood derived from logs.

Body-image guardrail (8/18 deck slide 13; 9/10 deck slide 20): nothing here
describes body size or shape. The participant picks appearance parts once;
each day only the *mood* (expression + a soft glow) and small *props* change,
and both reset to neutral every morning. There is no sad, sick or tired state.
"""
from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict

# Mood is a single, shared answer: STUDY_TZ decides "today" for every
# screen (rings, streaks, badges, cohort, this one). Imported from
# study_time.py so there's only ever one source of truth for the zone.
from study_time import STUDY_TZ

# Option ids are mirrored in frontend/src/avatar.ts — keep the two in sync.
OPTIONS = {
    "skin": ("porcelain", "light", "tan", "olive", "brown", "deep"),
    "hair": ("short", "crop", "wavy", "curly", "long", "bun", "covered", "none"),
    "hair_color": ("black", "dark_brown", "brown", "auburn", "blonde", "grey"),
    "face": ("classic", "soft", "freckles", "stubble", "beard"),
    "glasses": ("none", "round", "square"),
    "outfit": ("tee", "hoodie", "collar", "sweater"),
    "outfit_color": ("forest", "slate", "clay", "charcoal", "sand", "plum"),
    "background": ("sage", "stone", "mist", "sand", "clay", "slate"),
}

DEFAULT_AVATAR = {
    "skin": "tan", "hair": "short", "hair_color": "dark_brown", "face": "classic",
    "glasses": "none", "outfit": "tee", "outfit_color": "forest", "background": "sage",
}

MOODS = ("calm", "content", "energised")


class AvatarPatch(BaseModel):
    """Partial update; unknown fields or values are rejected (422)."""
    model_config = ConfigDict(extra="forbid")

    skin: Optional[Literal[OPTIONS["skin"]]] = None  # type: ignore[valid-type]
    hair: Optional[Literal[OPTIONS["hair"]]] = None  # type: ignore[valid-type]
    hair_color: Optional[Literal[OPTIONS["hair_color"]]] = None  # type: ignore[valid-type]
    face: Optional[Literal[OPTIONS["face"]]] = None  # type: ignore[valid-type]
    glasses: Optional[Literal[OPTIONS["glasses"]]] = None  # type: ignore[valid-type]
    outfit: Optional[Literal[OPTIONS["outfit"]]] = None  # type: ignore[valid-type]
    outfit_color: Optional[Literal[OPTIONS["outfit_color"]]] = None  # type: ignore[valid-type]
    background: Optional[Literal[OPTIONS["background"]]] = None  # type: ignore[valid-type]


def merge_avatar(current: Optional[dict], patch: AvatarPatch) -> dict:
    """Stored avatar (or the default) with the patch's non-null fields applied.
    Stale or unknown stored values fall back to the default for that part."""
    base = {k: v for k, v in (current or {}).items() if k in OPTIONS and v in OPTIONS[k]}
    return {**DEFAULT_AVATAR, **base, **patch.model_dump(exclude_none=True)}


def _counts(log: dict) -> bool:
    # Same exclusions as the rings: simulated wearable data never counts.
    return not (log.get("source") == "wearable" or log.get("kind") == "wearable" or log.get("simulated"))


def _on_study_day(log: dict, day: str) -> bool:
    stamp = datetime.fromisoformat(log["created_at"])
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(STUDY_TZ).date().isoformat() == day


def daily_mood(today_goals: list, logs: dict, day: str) -> dict:
    """Today's mood from the number of complete rings, plus props from
    today's own logs.

    `day` is a YYYY-MM-DD string in the study TZ — the single answer every
    screen agrees on. The mood steps from `calm` (no complete rings today),
    to `content` (one or two complete), to `energised` with a soft glow
    (all three complete). Props: a salad bowl once a meal with vegetables
    is logged, sneakers after any movement entry, rested eyes after a
    sleep entry. Never negative.
    """
    closed = sum(1 for g in today_goals if g.get("complete"))
    mood = "energised" if closed >= 3 else "content" if closed >= 1 else "calm"
    today = {d: [l for l in logs.get(d, []) if _counts(l) and _on_study_day(l, day)] for d in ("food", "move", "rest")}
    props = []
    if any(not m.get("skipped") and m.get("confirmed", True) and "vegetables" in m.get("categories", [])
           for m in today["food"]):
        props.append("salad")
    if any(a.get("minutes", 0) > 0 for a in today["move"]):
        props.append("sneakers")
    if any(s.get("hours", 0) > 0 for s in today["rest"]):
        props.append("rested")
    return {"date": day, "mood": mood, "rings_closed": closed, "glow": mood == "energised", "props": props}
