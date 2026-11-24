"""LLHS — Live Long, Heart Strong :: backend API.

REWRITTEN against the project's actual source documents (2026-09), replacing
an earlier build that had drifted from real requirements and had invented
governance narrative not grounded in anything the team produced — fabricated
IRB/DUA gates, a "Protective Mode"/SCOFF safety mode that was discussed only
as a hypothetical, a CARDIA long-term clinical trajectory, and an LE8-style
single 0-100 "heart health score." None of that is carried forward here.

Source documents this build is grounded in (all provided by the team,
2026-09):
  - "LLHS App Review and Development Notes" — DTL's screen-by-screen review,
    the primary source of truth for what changed and why.
  - "Updated DTL Slides 9.10.26" — current architecture: HEI-2020 replaces
    LE8, a rule-based simulation engine replaces the CARDIA trajectory, the
    Population Reference Marker spec, the Priority Selection flow, "My Path"
    avatar concept.
  - "LLHS App Onboarding Nutrition & Lifestyle Profile" — the onboarding
    survey (personalization context, explicitly NOT a diet-quality
    screener — that's ASA24's job, run outside this app).
  - "LLHS HEI-2020 National Benchmark Reference" + the accompanying
    benchmarks spreadsheet — static national reference values, U.S. adults
    18-25, NHANES 2017-March 2020 pre-pandemic.
  - "8.18 Meeting Slides" — earlier architecture overview; superseded on the
    specific points the 9/10/26 deck explicitly retired (CARDIA, LE8,
    nicotine tracking), still useful for the four-feature structure and the
    gamification/data-flow picture, which didn't change.

Architecture, in one paragraph: participant dietary quality is assessed
OUTSIDE this app via ASA24 (two recalls, a weekday and a weekend day, at
week 1, week 4 and week 8).
Staff export ASA24's Totals CSV and upload it via /research-admin;
the app scores it with a line-for-line port of NCI's HEI-2020 SAS macro
(hei2020_scoring.py) — it never invents its own diet-quality formula. What
the app also does: store the imported 13-component scores, compare each to a
static national benchmark, run a deterministic (not ML) "what-if" scenario
engine whose output only ever reaches participants as directional LLM
guidance, drive a Priority Selection flow (2-3 focus components chosen from
the ones with the most room for improvement), and present three separate
FOOD / MOVE / REST domains — never a single combined score. Move and Rest
reference values are still being finalized by the nutrition team (per the
review notes), so this build tracks the underlying data (wearable + manual)
without inventing a scoring formula for them.
"""

import os
import re
import hmac
import copy
import json
import math
import uuid
import asyncio
import logging
from pathlib import Path
from datetime import datetime, time, timezone, timedelta, date as date_cls
from collections import Counter
from typing import List, Optional, Literal, Dict, Any

import jwt
import bcrypt
from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, Header, Response, UploadFile, File, Form
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

import tamus_client
import dining_scraper
import dining_classifier
import plate_composer
import hei2020_scoring
import recall_weighting
import wording_rules
import personal_path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import avatar
import coach_kb
import daily_goals
import asa24_schedule
import hei_export
import focus_areas
import program
import asa24_accounts
import password_reset
import signup
import wings_challenge
import wings_photos
import weekly_workflow
import week2_scenarios
import week2_planning
import mailer
import future_me
import twin_habits
import twin_suggest
import twin_llm
import twin_patterns
import twin_profile
import twin_recommend

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret")
JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
TOKEN_MINUTES = int(os.environ.get("ACCESS_TOKEN_MINUTES", "20160"))
# TAMU AI is the app's sole LLM provider (Emergent has been fully removed —
# see tamus_client.py's module docstring). There is intentionally no
# app-wide default key here: every AI call resolves a key per-user via
# tamus_client.resolve_user_key(), which raises TamusKeyRequiredError when
# the participant has none.
# Optional shared-secret fallback for /research/* (X-Research-Key header),
# for scripts and bootstrap. Staff normally sign in with researcher accounts
# instead — see require_research_key() below. Leave unset in production once
# every staff member has an account.
RESEARCH_API_KEY = os.environ.get("RESEARCH_API_KEY", "")

if JWT_SECRET == "dev-secret":
    logging.getLogger("uvicorn.error").warning(
        "JWT_SECRET is not set — using the insecure 'dev-secret' default. "
        "Set the JWT_SECRET environment variable before deploying anywhere real users can reach."
    )
if not RESEARCH_API_KEY:
    logging.getLogger("uvicorn.error").warning(
        "RESEARCH_API_KEY is not set — /research/* accepts researcher sign-ins only. "
        "Create the first admin with: python manage_researchers.py add <email> --admin"
    )

app = FastAPI(title="LLHS API")
api = APIRouter(prefix="/api")

# RATE_LIMIT_ENABLED (default true): set to "false" only for local/CI test
# runs, which sign in far more often than the per-minute login limit.
RATE_LIMIT_ENABLED = os.environ.get("RATE_LIMIT_ENABLED", "true").strip().lower() not in ("0", "false", "no", "off")
# ON_VERCEL: Vercel sets VERCEL=1 in every function.
ON_VERCEL = bool(os.environ.get("VERCEL"))


def client_ip(request: Request) -> str:
    """Rate-limit key. Behind Vercel's proxy the socket address is the
    proxy's, which would put every visitor in one bucket; Vercel sets
    x-real-ip itself, so it's trusted there and nowhere else."""
    if ON_VERCEL and request.headers.get("x-real-ip"):
        return request.headers["x-real-ip"]
    return get_remote_address(request)


limiter = Limiter(key_func=client_ip, enabled=RATE_LIMIT_ENABLED)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
bearer = HTTPBearer(auto_error=False)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("llhs")


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def now_utc() -> datetime:
    return datetime.now(timezone.utc)


# Day / week boundaries live in backend/study_time.py so avatar.py and
# daily_goals.py can import them without a circular dep. Re-exported here
# because the daily-challenge code (and most places in this file) was
# already written against the names `STUDY_TZ` / `study_today`.
from study_time import (  # noqa: E402
    STUDY_TZ,
    study_today,
    study_week_window,
    study_day_key,
    study_day_start_utc_iso,
)


def new_id() -> str:
    return str(uuid.uuid4())


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode("utf-8")[:72], bcrypt.gensalt()).decode("utf-8")


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode("utf-8")[:72], hashed.encode("utf-8"))
    except Exception:
        return False


def create_token(user_id: str) -> str:
    exp = now_utc() + timedelta(minutes=TOKEN_MINUTES)
    payload = {"sub": user_id, "iat": now_utc(), "exp": exp, "jti": new_id()}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


async def current_user(creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer)) -> dict:
    if not creds or creds.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(creds.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        uid = payload["sub"]
        jti = payload.get("jti")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if payload.get("scope") == "research":
        raise HTTPException(status_code=401, detail="Researcher sessions can't use participant endpoints")
    if jti and await db.revoked_tokens.find_one({"jti": jti}):
        raise HTTPException(status_code=401, detail="This session has been signed out")
    user = await db.users.find_one({"id": uid})
    if not user:
        raise HTTPException(status_code=401, detail="User no longer exists")
    # A password reset signs out every session issued before it.
    valid_after = user.get("sessions_valid_after")
    if valid_after and int(payload.get("iat", 0)) < int(datetime.fromisoformat(valid_after).timestamp()):
        raise HTTPException(status_code=401, detail="Your password was changed. Sign in again.")
    user["_jti"] = jti
    return user


async def optional_user(creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer)) -> Optional[dict]:
    """current_user for routes that also serve anonymous callers: None when
    there's no bearer token; a bad/expired token still gets a 401."""
    if not creds:
        return None
    return await current_user(creds)


# ----------------------------------------------------------------------------
# Researcher access. Staff sign in with their own researcher account
# (db.researchers — separate from participants) and get a short-lived token
# scoped "research", so imports are attributable to a person. The shared
# RESEARCH_API_KEY still works as an X-Research-Key header for scripts,
# but only while it's set; unset it once every staff member has an account.
# First admin: `python manage_researchers.py add <email> --admin`.
# ----------------------------------------------------------------------------
RESEARCH_TOKEN_HOURS = int(os.environ.get("RESEARCH_TOKEN_HOURS", "8"))


def create_research_token(researcher_id: str) -> str:
    exp = now_utc() + timedelta(hours=RESEARCH_TOKEN_HOURS)
    payload = {"sub": researcher_id, "scope": "research", "iat": now_utc(), "exp": exp, "jti": new_id()}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def public_researcher(r: dict) -> dict:
    return {"id": r["id"], "email": r["email"], "name": r.get("name", ""), "role": r.get("role", "staff"),
            "active": r.get("active", True), "last_login_at": r.get("last_login_at")}


async def require_research_key(
    x_research_key: Optional[str] = Header(default=None),
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
) -> dict:
    """Returns who is acting: a signed-in researcher, or the legacy shared key."""
    if creds and creds.scheme.lower() == "bearer":
        try:
            payload = jwt.decode(creds.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        except Exception:
            raise HTTPException(status_code=401, detail="Invalid or expired researcher session")
        if payload.get("scope") != "research":
            raise HTTPException(status_code=401, detail="Sign in with a researcher account")
        if payload.get("jti") and await db.revoked_tokens.find_one({"jti": payload["jti"]}):
            raise HTTPException(status_code=401, detail="This session has been signed out")
        researcher = await db.researchers.find_one({"id": payload["sub"]})
        if not researcher or not researcher.get("active", True):
            raise HTTPException(status_code=401, detail="Researcher account is disabled or no longer exists")
        return {"kind": "researcher", "id": researcher["id"], "email": researcher["email"],
                "role": researcher.get("role", "staff"), "jti": payload.get("jti"), "exp": payload.get("exp")}
    if RESEARCH_API_KEY and x_research_key and hmac.compare_digest(x_research_key, RESEARCH_API_KEY):
        return {"kind": "api_key", "id": None, "email": None, "role": "admin"}
    raise HTTPException(status_code=401, detail="Missing or invalid research API key")


async def require_research_admin(principal: dict = Depends(require_research_key)) -> dict:
    if principal["role"] != "admin":
        raise HTTPException(status_code=403, detail="Only research admins can manage researcher accounts")
    return principal


DISCLAIMER = (
    "Illustrative only, based on your own logged process behaviors and published reference "
    "data — never an individual medical prediction, diagnosis, or clinical outcome claim."
)


# ----------------------------------------------------------------------------
# HEI-2020 — 13 components + static national benchmarks (U.S. adults 18-25).
#
# Source: "LLHS HEI-2020 National Benchmark Reference" + the accompanying
# benchmarks spreadsheet. Data: WWEIA/NHANES 2017-March 2020 pre-pandemic
# Day 1 dietary data + USDA FPED; NCI HEI-2020 Population Ratio Method.
# These are FIXED CONSTANTS per that document — no NHANES access, survey
# weighting, or Monte Carlo simulation happens in this app. If the benchmark
# file is ever updated, update this table; do not recompute it here.
#
# IMPORTANT (per the same document): for every component, a HIGHER score is
# better alignment with the Dietary Guidelines — including the four
# moderation components (Sodium, Added Sugars, Saturated Fats, Refined
# Grains), where a higher score means LOWER intake, not higher. Never invert
# this when writing participant-facing copy.
# ----------------------------------------------------------------------------
HEI2020_COMPONENTS = [
    {"id": "total_fruits", "label": "Total Fruits", "max_score": 5, "national_benchmark": 1.95, "kind": "adequacy"},
    {"id": "whole_fruits", "label": "Whole Fruits", "max_score": 5, "national_benchmark": 2.85, "kind": "adequacy"},
    {"id": "total_vegetables", "label": "Total Vegetables", "max_score": 5, "national_benchmark": 3.02, "kind": "adequacy"},
    {"id": "greens_beans", "label": "Greens & Beans", "max_score": 5, "national_benchmark": 2.55, "kind": "adequacy"},
    {"id": "whole_grains", "label": "Whole Grains", "max_score": 10, "national_benchmark": 1.70, "kind": "adequacy"},
    {"id": "dairy", "label": "Dairy", "max_score": 10, "national_benchmark": 5.59, "kind": "adequacy"},
    {"id": "total_protein_foods", "label": "Total Protein Foods", "max_score": 5, "national_benchmark": 5.00, "kind": "adequacy"},
    {"id": "seafood_plant_proteins", "label": "Seafood & Plant Proteins", "max_score": 5, "national_benchmark": 4.16, "kind": "adequacy"},
    {"id": "fatty_acids", "label": "Fatty Acids", "max_score": 10, "national_benchmark": 3.81, "kind": "adequacy"},
    {"id": "refined_grains", "label": "Refined Grains", "max_score": 10, "national_benchmark": 4.98, "kind": "moderation"},
    {"id": "sodium", "label": "Sodium", "max_score": 10, "national_benchmark": 3.67, "kind": "moderation"},
    {"id": "added_sugars", "label": "Added Sugars", "max_score": 10, "national_benchmark": 6.80, "kind": "moderation"},
    {"id": "saturated_fats", "label": "Saturated Fats", "max_score": 10, "national_benchmark": 4.72, "kind": "moderation"},
]
HEI2020_BY_ID = {c["id"]: c for c in HEI2020_COMPONENTS}
HEI2020_VERSION = "LLHS HEI-2020 National Benchmarks — U.S. Adults Ages 18–25 — NHANES 2017–March 2020 Pre-Pandemic"

# Let the weighting module look up component maxes for the staff
# comparison report (see recall_weighting.comparison_rows) without
# pulling server.py into its import graph.
recall_weighting.register_component_maxes(HEI2020_COMPONENTS)

# "A tolerance/rounding rule should be defined before implementing the final
# 'above/below/at' classification so that trivial numerical differences
# aren't presented as meaningful" — the source document flags this as an
# open item. 0.3 points is a placeholder pending nutrition-team sign-off,
# not a validated clinical threshold.
BENCHMARK_TOLERANCE = 0.3

ASSESSMENT_TYPES = asa24_schedule.ASSESSMENT_TYPES


def _benchmark_direction(participant_score: float, benchmark: float, tol: float = BENCHMARK_TOLERANCE) -> str:
    """'above' / 'below' / 'approximately_at' the national benchmark, using
    the placeholder tolerance above. Internal helper — see the module-level
    rule about where this may and may not reach the participant."""
    diff = participant_score - benchmark
    if abs(diff) <= tol:
        return "approximately_at"
    return "above" if diff > 0 else "below"


async def _latest_assessment(uid: str) -> Optional[dict]:
    # Latest study point, not latest upload (see asa24_schedule.latest).
    return asa24_schedule.latest(await db.hei_assessments.find({"user_id": uid}).to_list(20))


# ----------------------------------------------------------------------------
# Deterministic "what-if" simulation engine — NOT a trained model.
#
# Per the 9/10/26 deck: "Deterministic, rule-based, not a machine-learning
# model... Output feeds the LLM's internal reasoning only, never displayed
# to participants as a number or score... the LLM should never output the
# raw computed value from this engine directly to a participant, only the
# directional guidance it informs."
#
# HONEST SCOPE NOTE: the same deck flags an open item — "calorie-neutrality
# of substitution scenarios... not yet standardized, needs a rule before
# implementation." Because that rule doesn't exist yet, this engine does
# NOT invent a numeric point-delta formula (e.g. "+0.4 points per serving")
# — that would just be a new fabricated precision in place of the old one.
# It returns a DIRECTIONAL result only: which way a hypothetical behavior
# change would move a component relative to where the participant already
# stands against the national benchmark. Once the nutrition team defines
# real transformation rules (the "Scenario/Transformation Table" the deck
# references), swap the body of `simulate_scenario` for real point deltas —
# the calling contract (directional summary string, never a raw number)
# should not need to change.
# ----------------------------------------------------------------------------
def simulate_scenario(component_id: str, participant_score: float, behavior: str) -> dict:
    """Returns an internal-only directional scenario result. NEVER return
    the numeric fields from this function directly to a participant —
    only `directional_summary` (or an LLM's own paraphrase of it) may
    reach chat output, and only after passing the guardrail."""
    comp = HEI2020_BY_ID[component_id]
    bench = comp["national_benchmark"]
    current_gap = bench - participant_score
    if comp["kind"] == "adequacy":
        moves_toward_alignment = True  # adding more of an adequacy component always helps
    else:
        moves_toward_alignment = True  # the behaviors offered for moderation components are always reduction framed
    return {
        "component_id": component_id,
        "behavior": behavior,
        "moves_toward_alignment": moves_toward_alignment,
        "currently_below_benchmark": current_gap > BENCHMARK_TOLERANCE,
        "directional_summary": (
            f"Continuing with '{behavior}' would move {comp['label']} further toward alignment with the "
            f"Dietary Guidelines over time — a direction, not a computed score."
        ),
    }


# ----------------------------------------------------------------------------
# Lightweight in-app meal-logging categories — a SEPARATE, lower-burden
# layer from the ASA24-driven HEI-2020 assessment (per the review notes:
# "Does NOT trigger HEI component recalculation, only ASA24 data feeds the
# Current State Engine"). Tentative list, per the review notes; feeds
# engagement (points/streaks) and tag-level LLM reinforcement only.
# ----------------------------------------------------------------------------
LIGHTWEIGHT_LOG_CATEGORIES = [
    {"id": "vegetables", "label": "Vegetables"},
    {"id": "fruit", "label": "Fruit"},
    {"id": "whole_grains", "label": "Whole grains"},
    {"id": "refined_grains_starchy", "label": "Refined grains or starchy sides"},
    {"id": "beans_fish_nuts", "label": "Beans, fish, or nuts"},
    {"id": "other_protein", "label": "Other protein sources (meat, poultry, eggs, dairy protein)"},
    {"id": "dairy", "label": "Dairy"},
    {"id": "added_sugars", "label": "Added sugars (soda, desserts, sweetened beverages)"},
    {"id": "salty_processed", "label": "Salty or heavily processed foods"},
]
LOG_CATEGORY_IDS = {c["id"] for c in LIGHTWEIGHT_LOG_CATEGORIES}
_CORE_LOG_CATEGORIES = {"vegetables", "fruit", "whole_grains", "beans_fish_nuts", "other_protein", "dairy"}


def meal_has_core_categories(meal: dict, min_kinds: int = 2) -> bool:
    """A lightweight, provisional 'balanced-ish' check used only for
    non-clinical purposes (cohort/wing shared-goal counters) — never
    presented to a participant as a score. Counts how many distinct core
    food categories are represented, not a nutrient calculation."""
    cats = set(meal.get("categories", []))
    return len(cats & _CORE_LOG_CATEGORIES) >= min_kinds


# ----------------------------------------------------------------------------
# Models
# ----------------------------------------------------------------------------
class LoginIn(BaseModel):
    email: EmailStr
    password: str


class SignupStartIn(BaseModel):
    email: EmailStr


class SignupIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    name: str = Field(min_length=1, max_length=60)
    code: str = Field(min_length=6, max_length=12)


class ForgotPasswordIn(BaseModel):
    email: EmailStr


class ResetPasswordIn(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=12)
    new_password: str = Field(min_length=6, max_length=128)


class ProfileSurveyIn(BaseModel):
    answers: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("answers")
    @classmethod
    def _cap_size(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        if len(v) > 200:
            raise ValueError("Too many answers in one submission.")
        for key, val in v.items():
            if isinstance(val, str) and len(val) > 1000:
                raise ValueError(f"Answer for '{key}' is too long.")
            if isinstance(val, list) and len(val) > 30:
                raise ValueError(f"Answer for '{key}' has too many selections.")
        return v


class MealIn(BaseModel):
    name: str = Field(max_length=200)
    source: Literal["photo", "text", "voice", "dining_hall"] = "text"
    meal_type: Literal["breakfast", "lunch", "dinner", "snack"] = "lunch"
    items: List[str] = Field(default=[], max_length=30)
    categories: List[str] = Field(default=[], max_length=len(LIGHTWEIGHT_LOG_CATEGORIES))
    portion: Literal["small", "normal", "large"] = "normal"
    skipped: bool = False
    photo_confidence: Optional[float] = Field(default=None, ge=0, le=1)
    confirmed: bool = True
    # Optional self-report tied to the student's current focus_goal (per the
    # Week 1 spec §8 "Meal Logging"). ``null`` means the question wasn't
    # asked (participant has no active goal, or the UI hasn't surfaced it);
    # ``true/false`` is the student's answer. This field is read by the
    # research export only — it never influences HEI feedback, which is
    # computed from ASA24 recalls in db.hei_assessments.
    goal_hit: Optional[bool] = None

    @field_validator("categories")
    @classmethod
    def _valid_categories(cls, v: List[str]) -> List[str]:
        bad = [c for c in v if c not in LOG_CATEGORY_IDS]
        if bad:
            raise ValueError(f"Unknown log categories: {bad}")
        return v


class MealTextCategorizeIn(BaseModel):
    description: str = Field(min_length=1, max_length=500)


class ActivityIn(BaseModel):
    minutes: int = Field(ge=0, le=600)
    kind: str = Field(default="moderate", max_length=60)


_CLOCK_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$"


class SleepIn(BaseModel):
    hours: float = Field(ge=0, le=16)
    source: Literal["manual", "wearable"] = "manual"
    # Optional, roughly when they fell asleep and woke up (study-time clock,
    # "HH:MM"). Lets the behavioral twin notice irregular sleep timing from
    # manual logs too, not only from a tracker. Never required.
    bedtime: Optional[str] = Field(default=None, pattern=_CLOCK_PATTERN)
    wake: Optional[str] = Field(default=None, pattern=_CLOCK_PATTERN)


class GoalIn(BaseModel):
    metric: Literal["vegetables_servings", "fruit_servings", "whole_grains_servings", "activity_minutes", "sleep_hours"]
    target: float
    label: str = Field(max_length=120)


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    # One Coach conversation; memory is per user and session.
    session_id: str = Field(default="default", min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")


class PhotoIn(BaseModel):
    image_base64: str = Field(max_length=8_000_000)


class GameResultIn(BaseModel):
    markers: List[str] = Field(default=[], max_length=20)
    score: int = Field(default=0, ge=0, le=1000)


class WearableConnectIn(BaseModel):
    provider: Literal["fitbit", "apple_health", "health_connect"]


class WearableSyncIn(BaseModel):
    # Tighter than manual entry (SleepIn allows 0-16): a device-reported
    # night under 2h or over 14h is far more likely a sync artifact (an
    # unworn band, a merged multi-day export) than a real reading.
    hours: Optional[float] = Field(default=None, ge=2, le=14, allow_inf_nan=False)
    activity_minutes: Optional[int] = Field(default=None, ge=0, le=600)
    recorded_date: Optional[str] = None
    # Sleep timing from the device (study-time clock, "HH:MM"): when the main
    # sleep started and ended. The behavioral twin uses these to notice
    # irregular sleep timing; hours alone can't show it.
    sleep_start: Optional[str] = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    sleep_end: Optional[str] = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    # Daily step count, stored alongside that day's activity minutes.
    steps: Optional[int] = Field(default=None, ge=0, le=100000)

    @field_validator("recorded_date")
    @classmethod
    def _valid_recorded_date(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        try:
            d = date_cls.fromisoformat(v)
        except ValueError:
            raise ValueError("recorded_date must be YYYY-MM-DD")
        if d > date_cls.today() + timedelta(days=1):
            raise ValueError("recorded_date can't be in the future")
        return d.isoformat()


class NudgeSettingsIn(BaseModel):
    enabled: bool
    time: str = Field(default="19:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")


class SleepScheduleIn(BaseModel):
    # Usual bedtime and wake time, so Today treats sleep as a morning
    # check-in and doesn't count the day as "behind" before it's over.
    bedtime: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    wake: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")


class TamusSettingsIn(BaseModel):
    # No "enabled" toggle: TAMU AI is mandatory and the app's only AI
    # provider, so a saved key is used automatically — there is nothing
    # to opt in or out of. See public_user()/get_tamus_settings().
    api_key: Optional[str] = Field(default=None, min_length=8, max_length=500)
    model_chat: Optional[str] = Field(default=None, max_length=100)
    model_vision: Optional[str] = Field(default=None, max_length=100)


class FocusAreasIn(BaseModel):
    # One focus area at a time (focus_areas.py), with the participant's own
    # goal and action plan for it. Week 5 keeps it or changes it.
    area_id: str = Field(min_length=1, max_length=40)
    goal: Optional[str] = Field(default=None, max_length=200)
    plan: Optional[str] = Field(default=None, max_length=200)

    @field_validator("area_id")
    @classmethod
    def _valid_area(cls, v: str) -> str:
        if v not in focus_areas.BY_ID:
            raise ValueError(f"Unknown focus area: {v}")
        return v

    @field_validator("goal", "plan")
    @classmethod
    def _strip(cls, v: Optional[str]) -> Optional[str]:
        return (v or "").strip() or None


class HeiAssessmentImportIn(BaseModel):
    """Researcher-facing import of already-scored HEI-2020 component values,
    for scores computed outside the app (e.g. NCI's SAS macro). The normal
    path is the ASA24 Totals upload below, which scores the file itself."""
    participant_email: EmailStr
    assessment_type: Literal["baseline", "checkin_1", "checkin_2"]
    components: Dict[str, float]
    recorded_at: Optional[str] = None
    notes: Optional[str] = Field(default=None, max_length=1000)

    @field_validator("components")
    @classmethod
    def _valid_components(cls, v: Dict[str, float]) -> Dict[str, float]:
        for cid, score in v.items():
            if cid not in HEI2020_BY_ID:
                raise ValueError(f"Unknown HEI-2020 component id: {cid}")
            if score < 0 or score > HEI2020_BY_ID[cid]["max_score"]:
                raise ValueError(f"Score for {cid} must be between 0 and {HEI2020_BY_ID[cid]['max_score']}")
        return v


# ----------------------------------------------------------------------------
# Onboarding — Nutrition & Lifestyle Profile survey.
#
# Source: "LLHS App Onboarding Nutrition & Lifestyle Profile." This is
# EXPLICITLY NOT a diet-quality screener or eligibility gate — baseline diet
# quality comes from two ASA24 recalls administered outside this app. This
# survey's only job is personalization/early context for the LLM before
# ASA24-derived data exists. There is no scoring, no eligibility flag.
#
# Schema-driven (one source of truth for the participant-facing form AND
# server-side validation/skip-logic), same pattern the old Mini-EAT
# screener used for its question list — extended here to cover select,
# multi-select, number, and free-text question types plus conditional
# (skip-logic) questions.
#
# The dietary-restrictions/allergy question is flagged directly in the
# source document as SAFETY-RELEVANT, not just a personalization field —
# "needs reliable downstream handling (e.g., suppressing ingredient-matched
# recommendations)." See `_extract_allergy_terms` and every place that
# calls `filter_items_for_allergies` below for where that's enforced.
# ----------------------------------------------------------------------------
def _q(id, section, type, label, options=None, max_length=None, required=False, condition=None,
       min=None, max=None, integer=False, group=None, group_label=None):
    d = {"id": id, "section": section, "type": type, "label": label, "required": required}
    if options is not None:
        d["options"] = options
    if max_length is not None:
        d["max_length"] = max_length
    if condition is not None:
        d["condition"] = condition  # {"question": id, "in": [...]} — shown only if that question's answer matches
    # Number questions: inclusive bounds, enforced server-side in
    # validate_profile_answers and exposed so the form can enforce them too.
    if min is not None:
        d["min"] = min
    if max is not None:
        d["max"] = max
    if integer:
        d["integer"] = True
    if group is not None:
        d["group"] = group
        d["group_label"] = group_label
    return d


_YES_NO = [{"id": "yes", "label": "Yes"}, {"id": "no", "label": "No"}]
_FREQ_OPTIONS = [
    {"id": "never", "label": "Never"},
    {"id": "few_times_month", "label": "A few times a month"},
    {"id": "about_once_week", "label": "About once a week"},
    {"id": "few_times_week", "label": "A few times a week"},
    {"id": "daily", "label": "Daily"},
]
_AVAILABILITY_OPTIONS = [
    {"id": "not_available", "label": "Not available"},
    {"id": "shared", "label": "Shared access"},
    {"id": "personal", "label": "Personal"},
]

PROFILE_SURVEY_SCHEMA: List[dict] = [
    # ---- Section 1: Participant Profile — Demographics ----
    _q("age", "demographics", "number", "Age", required=True, min=16, max=99, integer=True),
    _q("gender", "demographics", "single_select", "Gender", options=[
        {"id": "male", "label": "Male"}, {"id": "female", "label": "Female"},
        {"id": "non_binary", "label": "Non-binary"},
        {"id": "self_describe", "label": "Prefer to self-describe"},
        {"id": "prefer_not_to_say", "label": "Prefer not to say"},
    ], required=True),
    _q("gender_self_describe", "demographics", "text", "Self-describe", max_length=100,
       condition={"question": "gender", "in": ["self_describe"]}),
    _q("race_ethnicity", "demographics", "multi_select", "Race/Ethnicity (optional)", options=[
        {"id": "american_indian_alaska_native", "label": "American Indian or Alaska Native"},
        {"id": "asian", "label": "Asian"},
        {"id": "black_african_american", "label": "Black or African American"},
        {"id": "hispanic_latino", "label": "Hispanic or Latino"},
        {"id": "native_hawaiian_pacific_islander", "label": "Native Hawaiian or Other Pacific Islander"},
        {"id": "white", "label": "White"},
        {"id": "two_or_more", "label": "Two or more races"},
        {"id": "self_describe", "label": "Prefer to self-describe"},
        {"id": "prefer_not_to_say", "label": "Prefer not to say"},
    ]),
    _q("race_ethnicity_self_describe", "demographics", "text", "Self-describe", max_length=100,
       condition={"question": "race_ethnicity", "in": ["self_describe"]}),
    _q("student_status", "demographics", "single_select", "Student status", options=[
        {"id": "full_time", "label": "Full-time student"}, {"id": "part_time", "label": "Part-time student"},
    ], required=True),
    _q("academic_major", "demographics", "text", "Academic major", max_length=150, required=True),
    _q("employment_status", "demographics", "single_select", "Employment status", options=[
        {"id": "not_employed", "label": "Not employed"},
        {"id": "part_time", "label": "Employed part-time"},
        {"id": "full_time", "label": "Employed full-time"},
    ], required=True),
    _q("weekly_work_hours", "demographics", "number", "Weekly work hours", min=0, max=80,
       condition={"question": "employment_status", "in": ["part_time", "full_time"]}),

    # ---- Section 1: Dietary Restrictions — SAFETY-RELEVANT ----
    _q("dietary_restrictions", "dietary_restrictions", "multi_select",
       "Do you have any food allergies or dietary restrictions? (select all that apply)", options=[
           {"id": "food_allergy", "label": "Food allergy"},
           {"id": "lactose_intolerance", "label": "Lactose intolerance"},
           {"id": "gluten_free_celiac", "label": "Gluten-free / Celiac"},
           {"id": "vegetarian", "label": "Vegetarian"},
           {"id": "vegan", "label": "Vegan"},
           {"id": "religious", "label": "Religious dietary restriction"},
           {"id": "other", "label": "Other"},
           # `exclusive`: can't be combined with any other selection.
           {"id": "none", "label": "None", "exclusive": True},
       ]),
    _q("food_allergy_detail", "dietary_restrictions", "text", "Please specify your food allergy", max_length=300,
       condition={"question": "dietary_restrictions", "in": ["food_allergy"]}),
    _q("religious_restriction_detail", "dietary_restrictions", "text", "Please specify", max_length=300,
       condition={"question": "dietary_restrictions", "in": ["religious"]}),
    _q("other_restriction_detail", "dietary_restrictions", "text", "Please specify", max_length=300,
       condition={"question": "dietary_restrictions", "in": ["other"]}),

    # ---- Section 1: Living Environment ----
    _q("residence", "living_environment", "single_select", "Current residence", options=[
        {"id": "residence_hall", "label": "Residence hall"}, {"id": "apartment", "label": "Apartment"},
        {"id": "house", "label": "House"}, {"id": "with_family", "label": "Living with family"},
        {"id": "other", "label": "Other"},
    ], required=True),
    _q("residence_other", "living_environment", "text", "Please specify", max_length=150,
       condition={"question": "residence", "in": ["other"]}),
    _q("university_meal_plan", "living_environment", "single_select", "University meal plan", options=_YES_NO, required=True),
    _q("kitchen_access", "living_environment", "single_select", "Do you have access to a kitchen where you live?", options=[
        {"id": "personal", "label": "Yes, it's mine"}, {"id": "shared", "label": "Yes, shared with others"},
        {"id": "none", "label": "No"},
    ], required=True),
    _q("kitchen_shared_count", "living_environment", "single_select", "If shared: how many people share it?", options=[
        {"id": "1-2", "label": "1–2"}, {"id": "3-4", "label": "3–4"}, {"id": "5+", "label": "5+"},
    ], condition={"question": "kitchen_access", "in": ["shared"]}),

    # Appliances — skipped entirely if kitchen_access == "none" (skip logic
    # per the source document). Handled client-side by the generic renderer
    # via the same `condition` mechanism, inverted (see frontend).
    *[
        _q(f"appliance_{key}", "appliances", "single_select", label, options=_AVAILABILITY_OPTIONS,
           condition={"question": "kitchen_access", "in": ["personal", "shared"]})
        for key, label in [
            ("stove", "Stove/stovetop"), ("oven", "Oven"), ("microwave", "Microwave"),
            ("refrigerator", "Refrigerator"), ("freezer", "Freezer"), ("air_fryer", "Air fryer"),
            ("electric_kettle", "Electric kettle"), ("toaster", "Toaster / toaster oven"),
            ("hot_plate", "Hot plate / portable burner"), ("slow_cooker", "Slow cooker or Instant Pot"),
            ("rice_cooker", "Rice cooker"), ("blender", "Blender"),
        ]
    ],
    _q("appliance_refrigerator_size", "appliances", "single_select", "Refrigerator size", options=[
        {"id": "mini", "label": "Mini/dorm-size"}, {"id": "full", "label": "Full-size"},
    ], condition={"question": "appliance_refrigerator", "in": ["shared", "personal"]}),
    _q("appliance_freezer_size", "appliances", "single_select", "Freezer size", options=[
        {"id": "mini", "label": "Mini/attached to mini-fridge"}, {"id": "full", "label": "Full-size"},
    ], condition={"question": "appliance_freezer", "in": ["shared", "personal"]}),
    _q("appliance_other", "appliances", "text", "Other appliance", max_length=200,
       condition={"question": "kitchen_access", "in": ["personal", "shared"]}),

    _q("cookware_pots", "appliances", "single_select", "Pots you have access to", options=[
        {"id": "0", "label": "0"}, {"id": "1-2", "label": "1–2"}, {"id": "3+", "label": "3+"},
    ], condition={"question": "kitchen_access", "in": ["personal", "shared"]}),
    _q("cookware_pans", "appliances", "single_select", "Pans you have access to", options=[
        {"id": "0", "label": "0"}, {"id": "1-2", "label": "1–2"}, {"id": "3+", "label": "3+"},
    ], condition={"question": "kitchen_access", "in": ["personal", "shared"]}),
    _q("cooking_setup_notes", "appliances", "text",
       "Anything else about your cooking setup that would help us give you better guidance?", max_length=500),

    # ---- Section 2: Food Environment ----
    _q("food_acquisition", "food_environment", "multi_select", "Food Acquisition Channel (select all that apply)", options=[
        {"id": "grocery_store", "label": "Grocery store"}, {"id": "campus_dining_hall", "label": "Campus dining hall"},
        {"id": "campus_food_court", "label": "Campus food court"}, {"id": "fast_food", "label": "Fast-food restaurants"},
        {"id": "sit_down_restaurants", "label": "Sit-down restaurants"}, {"id": "meal_delivery", "label": "Meal delivery services"},
        {"id": "convenience_stores", "label": "Convenience stores"}, {"id": "other", "label": "Other"},
    ]),
    _q("food_acquisition_other", "food_environment", "text", "Please specify", max_length=150,
       condition={"question": "food_acquisition", "in": ["other"]}),
    _q("meal_preparation", "food_environment", "multi_select", "Meal Preparation (select all that apply)", options=[
        {"id": "self", "label": "I prepare my own meals"}, {"id": "family", "label": "Prepared by family"},
        {"id": "friends", "label": "Prepared by friends"},
        {"id": "dining_staff", "label": "Prepared by dining hall or restaurant staff"},
        {"id": "other", "label": "Other"},
    ]),
    _q("meal_preparation_other", "food_environment", "text", "Please specify", max_length=150,
       condition={"question": "meal_preparation", "in": ["other"]}),
    *[
        _q(f"freq_{key}", "food_environment", "single_select", label, options=_FREQ_OPTIONS,
           group="frequency", group_label="How often do you typically do each of the following?")
        for key, label in [
            ("grocery_shop", "Grocery shop"), ("cook_meals", "Cook meals"),
            ("eat_restaurant", "Eat restaurant meals"), ("fast_food", "Purchase fast food"),
            ("convenience", "Purchase convenience foods"), ("eat_on_campus", "Eat on campus"),
        ]
    ],
    _q("food_dislikes", "food_environment", "text",
       "Are there any foods you strongly dislike or actively avoid?", max_length=500),

    # ---- Section 3: Getting You the Right Support ----
    _q("support_needs", "support_needs", "multi_select", "What could you use help with? (select all that apply)", options=[
        {"id": "meal_planning", "label": "Meal planning and prepping ahead"},
        {"id": "grocery_tips", "label": "Grocery shopping tips and strategies"},
        {"id": "time_management", "label": "Finding time to eat well when life is busy"},
        {"id": "limited_equipment", "label": "Cooking with limited equipment"},
        {"id": "quick_meals", "label": "Quick/easy meal ideas"},
        {"id": "healthy_snacking", "label": "Healthy snacking"},
        {"id": "portion_control", "label": "Portion control"},
        {"id": "reading_labels", "label": "Reading and understanding nutrition labels"},
        {"id": "understanding_guidelines", "label": "Understanding nutrition guidelines/recommendations"},
        {"id": "balanced_meals", "label": "Building balanced meals"},
        {"id": "budget_eating", "label": "Healthy eating on a budget"},
        {"id": "eating_out", "label": "Eating well when eating out or on campus"},
        {"id": "cravings_stress", "label": "Managing cravings or stress eating"},
        {"id": "none", "label": "None of these / not sure yet", "exclusive": True},
    ]),

    # ---- Section 4: Real-World Food Decision Context ----
    _q("hardest_meal", "decision_context", "single_select",
       "Which meal is typically the most difficult for you to make a healthy decision?", options=[
           {"id": "breakfast", "label": "Breakfast"}, {"id": "lunch", "label": "Lunch"},
           {"id": "dinner", "label": "Dinner"}, {"id": "snacks", "label": "Snacks"},
       ]),
    _q("hardest_meal_location", "decision_context", "single_select", "Where does this usually occur?", options=[
        {"id": "home", "label": "Home"}, {"id": "campus", "label": "Campus"}, {"id": "restaurant", "label": "Restaurant"},
        {"id": "fast_food", "label": "Fast food"}, {"id": "work", "label": "Work"}, {"id": "traveling", "label": "While traveling"},
        {"id": "other", "label": "Other"},
    ]),
    _q("hardest_meal_reason", "decision_context", "text",
       "Please briefly describe why this situation is challenging.", max_length=800),
]
PROFILE_SURVEY_BY_ID = {q["id"]: q for q in PROFILE_SURVEY_SCHEMA}
PROFILE_SURVEY_SECTIONS = [
    {"id": "demographics", "title": "Demographics"},
    {"id": "dietary_restrictions", "title": "Dietary Restrictions"},
    {"id": "living_environment", "title": "Living Environment"},
    {"id": "appliances", "title": "Kitchen & Cooking Setup"},
    {"id": "food_environment", "title": "Food Environment"},
    {"id": "support_needs", "title": "Getting You the Right Support"},
    {"id": "decision_context", "title": "Real-World Food Decision Context"},
]


def _condition_met(cond: Optional[dict], answers: Dict[str, Any]) -> bool:
    if not cond:
        return True
    val = answers.get(cond["question"])
    if isinstance(val, list):
        return any(v in cond["in"] for v in val)
    return val in cond["in"]


def strip_inapplicable_answers(answers: Dict[str, Any]) -> Dict[str, Any]:
    """Drops answers to schema questions whose skip-logic condition isn't
    met — e.g. appliance answers after kitchen_access became "none", or a
    "Please specify" detail whose parent option was unselected — so stale
    answers can't be stored or feed allergy_terms. Repeats until stable so
    chained conditions (kitchen_access -> appliance_refrigerator -> its
    size follow-up) cascade. Unknown keys are kept (see below)."""
    out = dict(answers)
    changed = True
    while changed:
        changed = False
        for q in PROFILE_SURVEY_SCHEMA:
            if q["id"] in out and not _condition_met(q.get("condition"), out):
                del out[q["id"]]
                changed = True
    return out


def validate_profile_answers(answers: Dict[str, Any]) -> None:
    """Validates required-ness, option membership, number ranges, exclusive
    options, and skip-logic against PROFILE_SURVEY_SCHEMA. Raises
    HTTPException(400) with the first problem found. This is intentionally
    permissive about EXTRA keys (schema can evolve without breaking old
    submissions) but strict about known ones."""
    for q in PROFILE_SURVEY_SCHEMA:
        if not _condition_met(q.get("condition"), answers):
            continue  # not applicable, skip-logic hides it — don't require it
        val = answers.get(q["id"])
        if q.get("required") and (val is None or val == "" or val == []):
            raise HTTPException(400, f"Missing required answer: {q['id']}")
        if val is None:
            continue
        if q["type"] == "single_select":
            valid = {o["id"] for o in q["options"]}
            if val not in valid:
                raise HTTPException(400, f"Invalid option for {q['id']}: {val}")
        elif q["type"] == "multi_select":
            valid = {o["id"] for o in q["options"]}
            if not isinstance(val, list) or any(v not in valid for v in val):
                raise HTTPException(400, f"Invalid selection for {q['id']}")
            exclusive = {o["id"] for o in q["options"] if o.get("exclusive")}
            if len(val) > 1 and exclusive & set(val):
                raise HTTPException(400, f"'{next(iter(exclusive & set(val)))}' can't be combined with other "
                                         f"selections for {q['id']}")
        elif q["type"] == "number":
            # bool is an int subclass in Python; NaN/inf slip through JSON parsing.
            if isinstance(val, bool) or not isinstance(val, (int, float)) or not math.isfinite(val):
                raise HTTPException(400, f"{q['id']} must be a number")
            if q.get("integer") and not float(val).is_integer():
                raise HTTPException(400, f"{q['id']} must be a whole number")
            if ("min" in q and val < q["min"]) or ("max" in q and val > q["max"]):
                raise HTTPException(400, f"{q['id']} must be between {q.get('min')} and {q.get('max')}")
        elif q["type"] == "text":
            if not isinstance(val, str) or len(val) > q.get("max_length", 1000):
                raise HTTPException(400, f"{q['id']} is invalid or too long")


def _extract_allergy_terms(answers: Dict[str, Any]) -> List[str]:
    """Turns the dietary-restrictions answers into a normalized list of
    lowercase terms used to suppress ingredient-matched recommendations
    (dining suggestions, plate-builder ingredient list, chat-build-meal
    candidates). Flagged as safety-relevant in the source document — this
    is the 'reliable downstream handling' it asks for, not just storage."""
    terms: List[str] = []
    restrictions = answers.get("dietary_restrictions") or []
    if "lactose_intolerance" in restrictions:
        terms += ["milk", "cheese", "yogurt", "cream", "butter", "lactose"]
    if "gluten_free_celiac" in restrictions:
        terms += ["wheat", "gluten", "bread", "pasta", "barley", "rye"]
    if "vegan" in restrictions:
        terms += ["meat", "chicken", "beef", "pork", "fish", "egg", "dairy", "milk", "cheese", "honey"]
    elif "vegetarian" in restrictions:
        terms += ["meat", "chicken", "beef", "pork", "fish", "bacon", "sausage"]
    free_text = " ".join(filter(None, [
        answers.get("food_allergy_detail"), answers.get("religious_restriction_detail"),
        answers.get("other_restriction_detail"),
    ])).lower()
    # Simple comma/space-separated term extraction from free text — a
    # heuristic, not an allergen-database lookup. Errs toward suppressing
    # more rather than less, since the failure direction here matters.
    for chunk in re.split(r"[,/;]| and ", free_text):
        chunk = chunk.strip()
        if 2 <= len(chunk) <= 40:
            terms.append(chunk)
            # Participants type allergen families ("dairy", "tree nuts"),
            # plurals ("eggs") or phrasing ("allergic to shellfish") — item
            # names never contain those words, so expand to the foods they cover.
            # Whole-word match, so "peanuts" doesn't pull in every tree nut
            # (and coconut) via "nut", nor "shellfish" all finfish via "fish".
            for family, foods in ALLERGEN_FAMILIES.items():
                if re.search(rf"\b{re.escape(family)}s?\b", chunk):
                    terms += foods
            if chunk.endswith("s") and len(chunk) > 3:
                terms.append(chunk[:-1])
    return sorted(set(t for t in terms if t))


ALLERGEN_FAMILIES: Dict[str, List[str]] = {
    "dairy": ["milk", "cheese", "yogurt", "cream", "butter", "whey", "queso", "dairy"],
    "milk": ["milk", "cheese", "yogurt", "cream", "butter", "whey", "queso"],
    "lactose": ["milk", "cheese", "yogurt", "cream", "butter", "queso"],
    "egg": ["egg", "omelet", "mayo", "aioli", "quiche"],
    "peanut": ["peanut"],
    "tree nut": ["almond", "walnut", "pecan", "cashew", "pistachio", "hazelnut", "macadamia"],
    "nut": ["nut", "peanut", "almond", "walnut", "pecan", "cashew", "pistachio", "hazelnut"],
    "shellfish": ["shrimp", "crab", "lobster", "crawfish", "clam", "mussel", "oyster", "scallop"],
    "fish": ["fish", "salmon", "tuna", "cod", "tilapia", "catfish", "pollock"],
    "soy": ["soy", "tofu", "edamame", "tempeh"],
    "wheat": ["wheat", "bread", "pasta", "flour", "tortilla", "bun", "roll", "noodle"],
    "gluten": ["wheat", "bread", "pasta", "flour", "tortilla", "bun", "roll", "noodle", "barley", "rye"],
    "sesame": ["sesame", "tahini", "hummus"],
}


# Allergy terms that also rule out a whole log category. Only dairy maps
# cleanly: fish/shellfish/nut terms are deliberately name-only, because
# "beans_fish_nuts" would also drop beans, lentils and tofu.
_ALLERGY_TERM_LOG_CATEGORIES = {"dairy": "dairy", "milk": "dairy", "lactose": "dairy"}


def item_matches_allergy(item: dict, allergy_terms: List[str]) -> bool:
    """True if an item's name contains an allergy term, or its category /
    log categories (top-level, as in INGREDIENT_LIBRARY, or classifier
    tags, as on dining items) fall in a category an allergy term rules out."""
    if not allergy_terms:
        return False
    name = (item.get("name") or "").lower()
    if any(term in name for term in allergy_terms):
        return True
    # Live Aggie Dining items also carry their ingredient list and the
    # feed's own allergen labels (Egg, Milk, Wheat, Soy, Sesame, ...) — see
    # dining_scraper.parse_period_menu. "Brioche Bun" says nothing about egg
    # in its name; its ingredients and labels do. Checked the same way as
    # the name, so an allergy term suppresses on any of the three.
    detail = " ".join([
        str(item.get("ingredients") or ""),
        " ".join(str(label) for label in (item.get("labels") or [])),
    ]).lower()
    if detail.strip() and any(term in detail for term in allergy_terms):
        return True
    blocked = {_ALLERGY_TERM_LOG_CATEGORIES[t] for t in allergy_terms if t in _ALLERGY_TERM_LOG_CATEGORIES}
    if not blocked:
        return False
    cats = {str(item.get("category") or "").lower()}
    cats.update(item.get("log_categories") or [])
    cats.update((item.get("tags") or {}).get("log_categories") or [])
    return bool(cats & blocked)


def filter_items_for_allergies(items: List[dict], allergy_terms: List[str]) -> List[dict]:
    """Drops any item matching an allergy term (see item_matches_allergy).
    Applied to RECOMMENDATION surfaces (plate suggestions, swaps, plate-review
    suggestions, ingredient library, chat meal-builder candidates, and
    /dining/menu?for_recommendation=true) — never to the plain dining-hall
    menu browse view, which should still show everything actually served."""
    if not allergy_terms:
        return items
    return [it for it in items if not item_matches_allergy(it, allergy_terms)]


def filter_menu_for_allergies(menu: dict, allergy_terms: List[str], keep_ids: Optional[set] = None) -> dict:
    """Station-by-station filter_items_for_allergies; `keep_ids` exempts
    specific items (e.g. the one being swapped out, so its station is still
    known). Stations left empty are dropped."""
    if not allergy_terms:
        return menu
    keep_ids = keep_ids or set()
    stations = []
    for station in menu.get("stations", []):
        items = [it for it in station.get("items", [])
                 if it.get("id") in keep_ids or not item_matches_allergy(it, allergy_terms)]
        if items:
            stations.append({**station, "items": items})
    return {**menu, "stations": stations}


# ----------------------------------------------------------------------------
# Social Page — Wings (shared goals, never individual leaderboards).
#
# Scoped conservatively: aggregate progress only, no per-member stats ever
# returned. The source review notes flag one open item here — whether
# participants get usernames/identifiers for social features at all — as
# still pending DTL/nutrition-team confirmation, not resolved by this
# build. Member display stays name-only (no handles/usernames) until that's
# settled, and photo/text posting stays out of scope, matching how little
# social surface the source documents actually describe.
#
# HARD CONSTRAINT, enforced by construction: compute_wing_progress() only
# ever returns a single summed/counted value, never a per-member breakdown.
# ----------------------------------------------------------------------------
SAFE_WING_GOALS = [
    {"metric": "balanced_meals", "label": "Balanced meals logged", "unit": "meals", "default_target": 300},
    {"metric": "activity_minutes", "label": "Activity minutes logged", "unit": "minutes", "default_target": 3000},
    {"metric": "participation_days", "label": "Days someone in the wing logged something", "unit": "days", "default_target": 20},
    {"metric": "veg_forward_meals", "label": "Meals with a vegetable in them", "unit": "meals", "default_target": 150},
]
_SAFE_WING_METRIC_IDS = {g["metric"] for g in SAFE_WING_GOALS}
_BLOCKED_NAME_SUBSTRINGS = {"fuck", "shit", "bitch", "nigger", "faggot", "cunt", "retard"}


def _clean_wing_name_ok(name: str) -> bool:
    lowered = name.lower()
    return not any(bad in lowered for bad in _BLOCKED_NAME_SUBSTRINGS)


def _gen_join_code() -> str:
    import random, string
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=6))


def _season_start_iso() -> str:
    n = now_utc()
    return n.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()


class WingCreateIn(BaseModel):
    name: str = Field(min_length=2, max_length=40)
    goal_metric: Literal["balanced_meals", "activity_minutes", "participation_days", "veg_forward_meals"]
    goal_target: Optional[int] = Field(default=None, ge=1, le=100000)


class WingJoinIn(BaseModel):
    join_code: str = Field(min_length=6, max_length=8)


async def compute_wing_progress(wing: dict) -> dict:
    member_ids = wing.get("member_ids", [])
    season_start = wing.get("season_start", _season_start_iso())
    metric = wing["goal_metric"]
    target = wing.get("goal_target") or next(g["default_target"] for g in SAFE_WING_GOALS if g["metric"] == metric)

    if not member_ids:
        return {"current": 0, "target": target, "achieved": False}

    if metric in ("balanced_meals", "veg_forward_meals"):
        meals = await db.meals.find(
            {"user_id": {"$in": member_ids}, "created_at": {"$gte": season_start}, "skipped": {"$ne": True}}
        ).to_list(20000)
        if metric == "balanced_meals":
            current = sum(1 for m in meals if meal_has_core_categories(m))
        else:
            current = sum(1 for m in meals if "vegetables" in (m.get("categories") or []))
    elif metric == "activity_minutes":
        acts = await db.activities.find(
            {"user_id": {"$in": member_ids}, "created_at": {"$gte": season_start}}
        ).to_list(20000)
        current = sum(a.get("minutes", 0) for a in acts)
    elif metric == "participation_days":
        meals = await db.meals.find(
            {"user_id": {"$in": member_ids}, "created_at": {"$gte": season_start}, "skipped": {"$ne": True}}
        ).to_list(20000)
        acts = await db.activities.find(
            {"user_id": {"$in": member_ids}, "created_at": {"$gte": season_start}}
        ).to_list(20000)
        days = {study_day_key(m["created_at"]) for m in meals} | {study_day_key(a["created_at"]) for a in acts}
        current = len(days)
    else:
        current = 0

    return {"current": current, "target": target, "achieved": current >= target}


async def _wing_public(wing: dict) -> dict:
    members = await db.users.find({"id": {"$in": wing.get("member_ids", [])}}).to_list(200)
    progress = await compute_wing_progress(wing)
    goal_def = next(g for g in SAFE_WING_GOALS if g["metric"] == wing["goal_metric"])
    return {
        "id": wing["id"], "name": wing["name"], "join_code": wing["join_code"], "created_by": wing["created_by"],
        "goal_metric": wing["goal_metric"], "goal_label": goal_def["label"], "goal_unit": goal_def["unit"],
        "members": [{"id": m["id"], "name": m.get("name", "")} for m in members],
        "progress": progress, "season_start": wing.get("season_start"),
    }


@api.get("/wings/goals/presets")
async def get_wing_goal_presets(user: dict = Depends(current_user)):
    return {"presets": SAFE_WING_GOALS}


@api.post("/wings")
async def create_wing(body: WingCreateIn, user: dict = Depends(current_user)):
    if await db.wings.find_one({"member_ids": user["id"]}):
        raise HTTPException(409, "You're already in a wing — leave it before creating a new one.")
    if not _clean_wing_name_ok(body.name):
        raise HTTPException(400, "That wing name isn't allowed — please choose another.")
    if body.goal_metric not in _SAFE_WING_METRIC_IDS:
        raise HTTPException(400, "Unknown goal metric.")

    join_code = _gen_join_code()
    while await db.wings.find_one({"join_code": join_code}):
        join_code = _gen_join_code()

    wing = {
        "id": new_id(), "name": body.name.strip(), "join_code": join_code, "created_by": user["id"],
        "member_ids": [user["id"]], "goal_metric": body.goal_metric, "goal_target": body.goal_target,
        "season_start": _season_start_iso(), "created_at": now_utc().isoformat(),
    }
    await db.wings.insert_one(dict(wing))
    return await _wing_public(wing)


@api.post("/wings/join")
async def join_wing(body: WingJoinIn, user: dict = Depends(current_user)):
    if await db.wings.find_one({"member_ids": user["id"]}):
        raise HTTPException(409, "You're already in a wing — leave it before joining another.")
    wing = await db.wings.find_one({"join_code": body.join_code.strip().upper()})
    if not wing:
        raise HTTPException(404, "No wing found with that code.")
    if len(wing.get("member_ids", [])) >= 40:
        raise HTTPException(400, "That wing is full.")
    await db.wings.update_one({"id": wing["id"]}, {"$addToSet": {"member_ids": user["id"]}})
    wing = await db.wings.find_one({"id": wing["id"]})
    return await _wing_public(wing)


@api.post("/wings/leave")
async def leave_wing(user: dict = Depends(current_user)):
    wing = await db.wings.find_one({"member_ids": user["id"]})
    if not wing:
        raise HTTPException(404, "You're not in a wing.")
    await db.wings.update_one({"id": wing["id"]}, {"$pull": {"member_ids": user["id"]}})
    remaining = await db.wings.find_one({"id": wing["id"]})
    if not remaining.get("member_ids"):
        await db.wings.delete_one({"id": wing["id"]})
    return {"ok": True}


@api.get("/wings/mine")
async def get_my_wing(user: dict = Depends(current_user)):
    wing = await db.wings.find_one({"member_ids": user["id"]})
    if not wing:
        return {"wing": None}
    return {"wing": await _wing_public(wing)}


# ----------------------------------------------------------------------------
# Wings extras: cheers, lightweight summary for polling, weekly challenge.
# Everything here stays group-aggregate — no per-member stats are ever
# returned (same hard constraint as compute_wing_progress above).
# ----------------------------------------------------------------------------
async def _wing_cheer_totals(wing: dict) -> dict:
    cheers = wing.get("cheers") or {}
    return {k: int(cheers.get(k, 0)) for k in wings_challenge.CHEER_KEYS}


async def _wing_weekly_challenge_progress(wing: dict) -> Optional[dict]:
    """This Wing's combined progress toward the current week's challenge.
    The challenge is deterministic per calendar week and shared across all
    Wings; only the progress number is Wing-specific."""
    today = study_today()
    ch = wings_challenge.challenge_for_week(today)
    if not ch:
        return None
    monday, sunday = wings_challenge.challenge_week_window(today)
    start = study_day_start_utc_iso(monday)
    end = study_day_start_utc_iso(sunday + timedelta(days=1))
    member_ids = wing.get("member_ids") or []
    if not member_ids:
        current = 0
    else:
        q = {"user_id": {"$in": member_ids}, "created_at": {"$gte": start, "$lt": end}}
        if ch["metric"] == "balanced_meals":
            meals = await db.meals.find({**q, "skipped": {"$ne": True}}).to_list(5000)
            current = sum(1 for m in meals if meal_has_core_categories(m))
        elif ch["metric"] == "veg_forward_meals":
            meals = await db.meals.find({**q, "skipped": {"$ne": True}}).to_list(5000)
            current = sum(1 for m in meals if "vegetables" in (m.get("categories") or []))
        elif ch["metric"] == "activity_minutes":
            acts = await db.activities.find(q).to_list(5000)
            current = int(sum(a.get("minutes", 0) for a in acts))
        elif ch["metric"] == "participation_days":
            meals = await db.meals.find({**q, "skipped": {"$ne": True}}).to_list(5000)
            acts = await db.activities.find(q).to_list(5000)
            days = {study_day_key(m["created_at"]) for m in meals} | {study_day_key(a["created_at"]) for a in acts}
            current = len(days)
        else:
            current = 0
    target = int(ch["target"])
    return {
        "id": ch["id"],
        "title": ch["title"],
        "description": ch["description"],
        "unit": ch["unit"],
        "metric": ch["metric"],
        "week_start": monday.isoformat(),
        "week_end": sunday.isoformat(),
        "current": int(current),
        "target": target,
        "achieved": int(current) >= target,
    }


@api.get("/wings/mine/summary")
async def wing_summary(user: dict = Depends(current_user)):
    """Lightweight response used by the 15s poll on the Wings screen.
    Returns ONLY the fields that can change tap-to-tap (progress, cheers,
    challenge count, member count) — never the full member list, never any
    per-member value. Safe to hit at 1 req/15 s per user; shape chosen so
    the frontend can diff + re-render without flicker."""
    wing = await db.wings.find_one({"member_ids": user["id"]})
    if not wing:
        return {"wing": None}
    progress = await compute_wing_progress(wing)
    cheers = await _wing_cheer_totals(wing)
    challenge = await _wing_weekly_challenge_progress(wing)
    return {
        "wing": {
            "id": wing["id"],
            "name": wing["name"],
            "member_count": len(wing.get("member_ids") or []),
            "progress": progress,
            "cheers": cheers,
            "cheers_total": sum(cheers.values()),
            "challenge": challenge,
        },
        "cheer_presets": wings_challenge.CHEER_PRESETS,
    }


class WingCheerIn(BaseModel):
    # Preset key only — the client never sends free text. The server rejects
    # anything outside wings_challenge.CHEER_KEYS so the preset list stays
    # the single source of allowed reactions.
    key: str = Field(min_length=1, max_length=40)


@api.post("/wings/cheer")
async def send_wing_cheer(body: WingCheerIn, user: dict = Depends(current_user)):
    if body.key not in wings_challenge.CHEER_KEYS:
        raise HTTPException(400, "Unknown cheer.")
    wing = await db.wings.find_one({"member_ids": user["id"]})
    if not wing:
        raise HTTPException(404, "You're not in a wing.")
    # Atomic increment on the shared subdoc field — six people tapping at
    # the same moment all land, no read-modify-write race. The counter is
    # per Wing, never per member; no author id is written anywhere, so the
    # response can never surface who tapped what.
    await db.wings.update_one(
        {"id": wing["id"]},
        {"$inc": {f"cheers.{body.key}": 1}},
    )
    wing = await db.wings.find_one({"id": wing["id"]})
    cheers = await _wing_cheer_totals(wing)
    return {"ok": True, "cheers": cheers, "cheers_total": sum(cheers.values())}


# ----------------------------------------------------------------------------
# Lab-test tooling. Staff-only. Lab members sign up themselves on the live
# app with their TAMU emails; we flip is_test_account=true on each one so
# they're excluded from every research export, then drop them into a Wing
# named "Lab Test Wing". No DB writes to llhs_db from Claude Code — all of
# this runs against the staff-controlled DB (whichever it is).
# ----------------------------------------------------------------------------
LAB_TEST_WING_NAME = "Lab Test Wing"

# The goal shown on the Lab Test Wing during a 30-minute live session.
# "balanced_meals" with target 6 moves the shared progress bar as each of
# the ~6 lab testers logs one quick meal — meals log faster than movement
# minutes do (log-meal is one tap + a category pick), and the number is
# low enough that the group can realistically fill the bar during the
# session, which is the whole point of the test.
#
# Overridable via env for future sessions without a code change.
# `LAB_TEST_WING_GOAL_METRIC` must be one of the SAFE_WING_GOALS metric
# ids; invalid values fall back to the default so a bad env can't crash
# the staff "ensure" endpoint mid-test.
_LAB_TEST_WING_DEFAULT_METRIC = "balanced_meals"
_LAB_TEST_WING_DEFAULT_TARGET = 6


def _lab_test_wing_goal() -> tuple[str, int]:
    metric = (os.environ.get("LAB_TEST_WING_GOAL_METRIC") or _LAB_TEST_WING_DEFAULT_METRIC).strip()
    if metric not in _SAFE_WING_METRIC_IDS:
        metric = _LAB_TEST_WING_DEFAULT_METRIC
    try:
        target = int(os.environ.get("LAB_TEST_WING_GOAL_TARGET") or _LAB_TEST_WING_DEFAULT_TARGET)
    except (TypeError, ValueError):
        target = _LAB_TEST_WING_DEFAULT_TARGET
    if target <= 0:
        target = _LAB_TEST_WING_DEFAULT_TARGET
    return metric, target


async def _get_or_create_lab_test_wing(creator_id: str) -> dict:
    metric, target = _lab_test_wing_goal()
    existing = await db.wings.find_one({"name": LAB_TEST_WING_NAME})
    if existing:
        # Backfill the goal if an older Lab Test Wing row was created with
        # a different metric / target (e.g. the pre-Oct-27 version with
        # participation_days / 10 that never moves in a 30-min session).
        if existing.get("goal_metric") != metric or existing.get("goal_target") != target:
            await db.wings.update_one(
                {"id": existing["id"]},
                {"$set": {"goal_metric": metric, "goal_target": target}},
            )
            existing["goal_metric"] = metric
            existing["goal_target"] = target
        return existing
    join_code = _gen_join_code()
    while await db.wings.find_one({"join_code": join_code}):
        join_code = _gen_join_code()
    wing = {
        "id": new_id(), "name": LAB_TEST_WING_NAME, "join_code": join_code,
        "created_by": creator_id, "member_ids": [],
        "goal_metric": metric, "goal_target": target,
        "season_start": _season_start_iso(), "created_at": now_utc().isoformat(),
        "is_lab_test": True,
    }
    await db.wings.insert_one(dict(wing))
    return wing


class LabTestAddIn(BaseModel):
    email: str = Field(min_length=3, max_length=120)


@api.post("/research/lab-test-wing/ensure", dependencies=[Depends(require_research_key)])
async def lab_test_wing_ensure(principal: dict = Depends(require_research_key)):
    wing = await _get_or_create_lab_test_wing(creator_id=principal["id"])
    return {"id": wing["id"], "name": wing["name"], "join_code": wing["join_code"],
            "member_ids": wing.get("member_ids") or []}


@api.get("/research/lab-test-wing", dependencies=[Depends(require_research_key)])
async def lab_test_wing_get():
    wing = await db.wings.find_one({"name": LAB_TEST_WING_NAME})
    if not wing:
        return {"wing": None}
    members = await db.users.find(
        {"id": {"$in": wing.get("member_ids") or []}},
        {"_id": 0, "id": 1, "email": 1, "name": 1, "is_test_account": 1},
    ).to_list(200)
    return {
        "wing": {
            "id": wing["id"], "name": wing["name"], "join_code": wing["join_code"],
            "created_at": wing.get("created_at"),
            "members": members,
        }
    }


@api.post("/research/lab-test-wing/add", dependencies=[Depends(require_research_key)])
async def lab_test_wing_add(body: LabTestAddIn, principal: dict = Depends(require_research_key)):
    email = body.email.strip().lower()
    if not email or "@" not in email:
        raise HTTPException(400, "Enter a valid email address.")
    u = await db.users.find_one({"email": email})
    if not u:
        raise HTTPException(404, "No account found with that email. Ask the student to sign up on the app first.")
    wing = await _get_or_create_lab_test_wing(creator_id=principal["id"])
    # Flip is_test on the user so every research export filters them out,
    # and $addToSet so repeated clicks are a no-op (not an error).
    await db.users.update_one({"id": u["id"]}, {"$set": {"is_test_account": True}})
    # Yank them out of any other Wing first — one Wing per user is a hard
    # rule enforced by every other wing endpoint.
    await db.wings.update_many(
        {"id": {"$ne": wing["id"]}, "member_ids": u["id"]},
        {"$pull": {"member_ids": u["id"]}},
    )
    await db.wings.update_one({"id": wing["id"]}, {"$addToSet": {"member_ids": u["id"]}})
    return {"ok": True, "user_id": u["id"], "email": email}


@api.post("/research/lab-test-wing/remove", dependencies=[Depends(require_research_key)])
async def lab_test_wing_remove(body: LabTestAddIn):
    email = body.email.strip().lower()
    u = await db.users.find_one({"email": email})
    if not u:
        return {"ok": True}  # idempotent — "not there" is a success
    await db.wings.update_many(
        {"name": LAB_TEST_WING_NAME},
        {"$pull": {"member_ids": u["id"]}},
    )
    # Keep is_test_account=true even after removal — once a lab tester,
    # always a lab tester, so a late-arriving log never pollutes real data.
    return {"ok": True, "user_id": u["id"]}


# ----------------------------------------------------------------------------
# Lab-test in-app feedback. Only is_test accounts see the button; the route
# itself double-checks (defence in depth) so a stray live-user token could
# never write a feedback row and bloat staff review. Captured per-session:
# screen name, device type, what-doing, what-happened, optional 1–5 rating.
# ----------------------------------------------------------------------------
class LabFeedbackIn(BaseModel):
    screen: str = Field(min_length=1, max_length=60)
    device: str = Field(min_length=1, max_length=60)
    what_doing: str = Field(min_length=1, max_length=500)
    what_happened: str = Field(min_length=1, max_length=1000)
    rating: Optional[int] = Field(default=None, ge=1, le=5)


@api.post("/wings/feedback")
async def submit_lab_feedback(body: LabFeedbackIn, user: dict = Depends(current_user)):
    # Belt + braces: don't accept feedback from live participants even if
    # the client somehow shows the button to them. Also prevents a load of
    # noise rows if the UI gate ever regresses.
    if not is_test_account(user):
        raise HTTPException(403, "Feedback is only collected during lab tests.")
    doc = {
        "id": new_id(), "user_id": user["id"], "email": user.get("email", ""),
        "screen": body.screen.strip(), "device": body.device.strip(),
        "what_doing": body.what_doing.strip(), "what_happened": body.what_happened.strip(),
        "rating": body.rating, "created_at": now_utc().isoformat(),
    }
    await db.lab_feedback.insert_one(dict(doc))
    doc.pop("_id", None)
    return {"ok": True}


@api.get("/research/lab-feedback", dependencies=[Depends(require_research_key)])
async def list_lab_feedback(limit: int = 500):
    rows = await db.lab_feedback.find(
        {}, {"_id": 0}
    ).sort("created_at", -1).to_list(min(max(1, limit), 2000))
    return {"feedback": rows}


@api.get("/research/lab-feedback.csv", dependencies=[Depends(require_research_key)])
async def export_lab_feedback_csv():
    import csv as _csv, io as _io
    rows = await db.lab_feedback.find({}, {"_id": 0}).sort("created_at", 1).to_list(5000)
    buf = _io.StringIO()
    w = _csv.writer(buf)
    w.writerow(["created_at", "email", "screen", "device", "rating", "what_doing", "what_happened"])
    for r in rows:
        w.writerow([
            r.get("created_at", ""), r.get("email", ""), r.get("screen", ""),
            r.get("device", ""), r.get("rating", ""), r.get("what_doing", ""), r.get("what_happened", ""),
        ])
    from fastapi.responses import Response
    return Response(content=buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=lab_feedback.csv"})


# ----------------------------------------------------------------------------
# Wings Phase 2 — photo posts with moderation.
#
# Flow (never relaxes without PI/IRB sign-off, enforced by wings_photos
# `photos_mode()`):
#     student uploads --[auto filters]--> `pending` --[staff approve]-->
#     `approved` (visible in Wing feed) -or- `rejected` (hidden, preset
#     reason shown to poster) -or- `removed` (previously approved,
#     retracted by staff).
#
# Posts are app content, not research data. The image bytes NEVER appear
# in any research export; only engagement counts (posts made, reactions
# given) are exportable, and `is_test` posts are filtered out of those.
# ----------------------------------------------------------------------------
_wing_photo_storage: Optional[wings_photos.WingPhotoStorage] = None


def _photo_storage() -> wings_photos.WingPhotoStorage:
    """Lazy singleton — picks the Vercel-Blob adapter when
    `BLOB_READ_WRITE_TOKEN` is set, otherwise the in-memory dev adapter.
    Reads env each process start (not each call) so a prod deploy without
    the token loudly falls back to Memory in logs, not silently."""
    global _wing_photo_storage
    if _wing_photo_storage is None:
        _wing_photo_storage = wings_photos.default_storage()
    return _wing_photo_storage


_FOCUS_TAG_IDS = {"total_fruits", "whole_fruits", "total_vegetables", "greens_beans",
                  "whole_grains", "dairy", "total_protein_foods",
                  "seafood_plant_proteins", "fatty_acids", "refined_grains",
                  "sodium", "added_sugars", "saturated_fats"}


def _public_wing_post(doc: dict, viewer_id: Optional[str] = None, staff: bool = False) -> dict:
    """Only ever expose what the viewer is allowed to see. Students see
    reaction totals but never who reacted; staff see the poster's id so
    they can act on repeated breaches, but students never do."""
    out = {
        "id": doc["id"], "status": doc["status"], "caption": doc.get("caption", ""),
        "steps": list(doc.get("steps") or []),
        "focus_tag": doc.get("focus_tag"),
        "image_url": f"/api/wings/posts/{doc['id']}/image",
        "image_width": doc.get("image_width"), "image_height": doc.get("image_height"),
        "reactions": {k: int((doc.get("reactions") or {}).get(k, 0))
                      for k in wings_photos.REACTION_KEYS},
        "created_at": doc.get("created_at"),
        "reported": bool(doc.get("reported")),
    }
    # Posters see their own posts' moderation state verbatim. Non-posters
    # only see "approved" posts (filtered upstream in the feed query), so
    # for them `status` is always "approved".
    if viewer_id and viewer_id == doc.get("user_id"):
        out["mine"] = True
        if doc.get("status") == "rejected":
            out["reject_reason"] = doc.get("reject_reason")
    if staff:
        out["user_id"] = doc.get("user_id")
        out["wing_id"] = doc.get("wing_id")
        out["is_test"] = bool(doc.get("is_test"))
        out["filter"] = doc.get("filter_results") or {}
        out["moderated_at"] = doc.get("moderated_at")
        out["moderated_by"] = doc.get("moderated_by")
    return out


async def _study_today_key_now() -> str:
    return study_today().isoformat()


async def _user_posts_today(uid: str) -> int:
    today_key = (await _study_today_key_now())
    # Query by `created_at` lower bound (UTC midnight for the study day).
    start = study_day_start_utc_iso(date_cls.fromisoformat(today_key))
    return await db.wing_posts.count_documents(
        {"user_id": uid, "created_at": {"$gte": start}, "status": {"$ne": "removed_by_poster"}}
    )


@api.get("/wings/photos/config")
async def wings_photos_config(user: dict = Depends(current_user)):
    """Lightweight hints the frontend needs to render the posting flow:
    whether the student can see the Share button, the preset reactions,
    reject-reason labels (staff only read them, but students see the one
    chosen for their own post), the guide copy and the per-day limit."""
    is_test = is_test_account(user)
    return {
        "mode": wings_photos.photos_mode(),
        "can_post": wings_photos.can_user_post(user, is_test),
        "max_posts_per_day": wings_photos.MAX_POSTS_PER_STUDY_DAY,
        "max_bytes": wings_photos.MAX_UPLOAD_BYTES,
        "guide": wings_photos.POSTING_GUIDE,
        "reactions": wings_photos.REACTION_PRESETS,
        "reject_reasons": wings_photos.REJECT_REASONS,
    }


@api.post("/wings/posts")
async def create_wing_post(
    photo: UploadFile = File(...),
    caption: str = Form(""),
    focus_tag: Optional[str] = Form(None),
    steps_json: str = Form("[]"),  # JSON-encoded list of strings
    user: dict = Depends(current_user),
):
    """Student uploads a food photo. The server:
      1. Checks the WINGS_PHOTOS_MODE gate (double-checks is_test for
         test_only — frontend hide is UX, not security).
      2. Enforces 3 posts / day (study TZ).
      3. Runs the content filter on caption + steps.
      4. Validates / re-encodes / strips EXIF via wings_photos.process_image.
      5. Stores the clean JPEG via the storage adapter and persists the
         post as `pending` (NEVER auto-approved — a human still OKs it).
    """
    is_test = is_test_account(user)
    if not wings_photos.can_user_post(user, is_test):
        raise HTTPException(403, "Photo sharing isn't open for your account right now.")

    # Student must be in a Wing — a lone-wolf post has nowhere to appear.
    wing = await db.wings.find_one({"member_ids": user["id"]})
    if not wing:
        raise HTTPException(400, "Join or create a Wing before sharing a meal.")

    # Per-day limit (study TZ). Rejected posts count against the quota so
    # a chain of blocked uploads doesn't let someone pile on tries.
    if await _user_posts_today(user["id"]) >= wings_photos.MAX_POSTS_PER_STUDY_DAY:
        raise HTTPException(
            429,
            f"You've shared your {wings_photos.MAX_POSTS_PER_STUDY_DAY} posts for today — see you tomorrow.",
        )

    try:
        steps = json.loads(steps_json) if steps_json else []
        if not isinstance(steps, list) or not all(isinstance(s, str) for s in steps):
            raise ValueError("steps must be a list of strings")
    except (ValueError, json.JSONDecodeError):
        raise HTTPException(400, "Couldn't read the recipe steps.")
    steps = [s.strip() for s in steps if s.strip()][:5]

    text = wings_photos.check_text(caption.strip(), steps)
    if not text.ok:
        raise HTTPException(400, text.message)

    # Validate focus tag against the known set; silently drop unknowns.
    tag = focus_tag if focus_tag in _FOCUS_TAG_IDS else None

    # Read bytes once; wings_photos.process_image hard-caps at 5 MB and
    # verifies the real file type by magic bytes.
    try:
        raw = await photo.read()
        processed = wings_photos.process_image(raw, declared_kind=photo.content_type or "")
    except wings_photos.ImageRejected as e:
        raise HTTPException(400, str(e))

    try:
        storage = _photo_storage()
    except wings_photos.StorageUnavailable:
        # Prod (Vercel) deploy without BLOB_READ_WRITE_TOKEN: refuse rather
        # than silently drop the upload into a per-worker memory dict that
        # evaporates on the next cold start. Friendly message to the
        # student; the operator sees `photo storage: unavailable` in the
        # boot log and in the config endpoint.
        logger.error("wings photo storage unavailable — refusing upload (BLOB_READ_WRITE_TOKEN missing on Vercel)")
        raise HTTPException(503, wings_photos.STORAGE_UNAVAILABLE_MESSAGE)
    try:
        image_key = await storage.put(processed.jpeg_bytes, photo.filename or "post.jpg")
    except Exception:
        # Log the real error without any user data (no caption, no email,
        # no filename) so a staff-side triage can reproduce without
        # exposing the student's content in the log stream.
        logger.exception("wings photo storage put failed")
        raise HTTPException(502, "Couldn't save your photo just now. Please try again.")

    # The filter never approves — just annotates. Human moderation gates
    # visibility either way. "auto_checked" is false until a cloud image
    # moderation provider is wired; staff see "not auto-checked" and
    # know to look a little harder.
    filter_results = {
        "auto_checked": False,
        "text_ok": True,
        "image_ok": True,
        "flags": [],
        "reencoded": True,
        "exif_stripped": True,
    }

    doc = {
        "id": new_id(),
        "user_id": user["id"],
        "wing_id": wing["id"],
        "is_test": is_test,
        "caption": caption.strip(),
        "steps": steps,
        "focus_tag": tag,
        "image_key": image_key,
        "image_width": processed.width,
        "image_height": processed.height,
        "status": "pending",
        "reported": False,
        "filter_results": filter_results,
        "reactions": {k: 0 for k in wings_photos.REACTION_KEYS},
        "created_at": now_utc().isoformat(),
    }
    await db.wing_posts.insert_one(dict(doc))
    doc.pop("_id", None)
    return _public_wing_post(doc, viewer_id=user["id"])


@api.get("/wings/posts/mine")
async def my_wing_posts(user: dict = Depends(current_user)):
    """The poster's own posts, newest first, with full status (pending /
    approved / rejected / removed). Only the student sees their own
    rejected posts and the preset reason."""
    rows = await db.wing_posts.find(
        {"user_id": user["id"]},
        {"_id": 0},
    ).sort("created_at", -1).to_list(50)
    return {"posts": [_public_wing_post(r, viewer_id=user["id"]) for r in rows]}


@api.get("/wings/feed")
async def wing_feed(user: dict = Depends(current_user)):
    """Approved posts in the student's own Wing, newest first. Reported
    posts are hidden until staff re-review; removed posts never show. No
    cross-Wing posts, ever (hard constraint, enforced here with a
    `$in: [wing_id]` query)."""
    wing = await db.wings.find_one({"member_ids": user["id"]})
    if not wing:
        return {"posts": []}
    rows = await db.wing_posts.find(
        {"wing_id": wing["id"], "status": "approved", "reported": {"$ne": True}},
        {"_id": 0},
    ).sort("created_at", -1).to_list(100)
    return {"posts": [_public_wing_post(r, viewer_id=user["id"]) for r in rows]}


class WingReactionIn(BaseModel):
    key: str = Field(min_length=1, max_length=40)


@api.post("/wings/posts/{post_id}/react")
async def react_to_wing_post(post_id: str, body: WingReactionIn, user: dict = Depends(current_user)):
    """Preset reactions only, counted per Wing-post, never per person.
    Atomic $inc so simultaneous taps all land. We never write a
    `reacted_by` list anywhere — the server can't surface who reacted
    because it never knows."""
    if body.key not in wings_photos.REACTION_KEYS:
        raise HTTPException(400, "Unknown reaction.")
    post = await db.wing_posts.find_one({"id": post_id}, {"_id": 0})
    if not post or post.get("status") != "approved" or post.get("reported"):
        raise HTTPException(404, "That post isn't available.")
    # Membership check — only students in the post's Wing can react.
    wing = await db.wings.find_one({"id": post["wing_id"], "member_ids": user["id"]})
    if not wing:
        raise HTTPException(403, "That post isn't in your Wing.")
    await db.wing_posts.update_one({"id": post_id}, {"$inc": {f"reactions.{body.key}": 1}})
    post = await db.wing_posts.find_one({"id": post_id}, {"_id": 0})
    return {"ok": True, "reactions": _public_wing_post(post, viewer_id=user["id"])["reactions"]}


@api.post("/wings/posts/{post_id}/report")
async def report_wing_post(post_id: str, user: dict = Depends(current_user)):
    """Any Wing member can report a post. Reporting flips `reported=True`
    so the post disappears from the feed until staff re-review it; the
    report count is for staff triage only and never surfaces to students."""
    post = await db.wing_posts.find_one({"id": post_id})
    if not post or post.get("status") not in ("approved", "pending"):
        raise HTTPException(404, "That post isn't available.")
    wing = await db.wings.find_one({"id": post["wing_id"], "member_ids": user["id"]})
    if not wing and post.get("user_id") != user["id"]:
        raise HTTPException(403, "That post isn't in your Wing.")
    await db.wing_posts.update_one(
        {"id": post_id},
        {"$set": {"reported": True, "reported_at": now_utc().isoformat()},
         "$addToSet": {"reported_by": user["id"]}},
    )
    return {"ok": True}


@api.delete("/wings/posts/{post_id}")
async def delete_my_wing_post(post_id: str, user: dict = Depends(current_user)):
    """Students can delete their own posts at any time. We cascade the
    image delete through the storage adapter, so the Blob (or dev memory)
    doesn't keep orphan bytes. The DB row is left as `removed_by_poster`
    for engagement counts only, with the image_key cleared."""
    post = await db.wing_posts.find_one({"id": post_id})
    if not post:
        raise HTTPException(404, "That post isn't available.")
    if post.get("user_id") != user["id"]:
        raise HTTPException(403, "You can only delete your own posts.")
    image_key = post.get("image_key")
    try:
        if image_key:
            await _photo_storage().delete(image_key)
    except Exception:
        logger.exception("wings photo storage delete failed (post=%s)", post_id)
        # Still mark the row deleted — the image is unreachable to students
        # because serving goes through our membership check.
    await db.wing_posts.update_one(
        {"id": post_id},
        {"$set": {"status": "removed_by_poster", "image_key": None,
                  "removed_at": now_utc().isoformat()}},
    )
    return {"ok": True}


@api.get("/wings/posts/{post_id}/image")
async def wing_post_image(post_id: str, user: dict = Depends(current_user)):
    """Serve the processed JPEG to viewers who are allowed to see it.
    The image URL in post responses points here, NEVER at the raw Blob
    URL — a Blob URL in a page's `<img src>` would be visible to every
    network observer, and we need Wing-scoped access."""
    post = await db.wing_posts.find_one({"id": post_id})
    if not post or not post.get("image_key"):
        raise HTTPException(404, "That image isn't available.")
    # Who can see it:
    #   * the poster (any state)
    #   * other Wing members, if status == "approved" and not reported
    #   * staff (via require_research_key'd routes — not this one)
    viewer_id = user["id"]
    allowed = post.get("user_id") == viewer_id
    if not allowed and post.get("status") == "approved" and not post.get("reported"):
        wing = await db.wings.find_one({"id": post["wing_id"], "member_ids": viewer_id})
        allowed = bool(wing)
    if not allowed:
        raise HTTPException(403, "That image isn't available to you.")
    try:
        data = await _photo_storage().get(post["image_key"])
    except Exception:
        logger.exception("wings photo storage get failed (post=%s)", post_id)
        raise HTTPException(404, "That image isn't available.")
    from fastapi.responses import Response
    # Short cache for a feed that scrolls — the image bytes themselves
    # never change for a given post id once stored.
    return Response(content=data, media_type="image/jpeg",
                    headers={"Cache-Control": "private, max-age=3600"})


# ---- Staff moderation ------------------------------------------------------
class WingModerateIn(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=40)


@api.get("/research/moderation/counts", dependencies=[Depends(require_research_key)])
async def moderation_counts():
    """Just the number — used by the 15-second refresh in the staff tab
    header so a facilitator approving posts live sees the queue tick down
    without reloading the whole table."""
    pending = await db.wing_posts.count_documents(
        {"status": {"$in": ["pending"]}, "reported": {"$ne": True}}
    )
    reported = await db.wing_posts.count_documents(
        {"status": "approved", "reported": True}
    )
    return {"pending": pending, "reported": reported}


@api.get("/research/moderation/pending", dependencies=[Depends(require_research_key)])
async def moderation_pending():
    """Pending + reported posts for staff triage, newest first. Includes
    poster id (visible to staff only — never surfaced to students) + Wing
    name + filter flags. Image bytes are at
    /research/moderation/{id}/image."""
    pending = await db.wing_posts.find(
        {"$or": [
            {"status": "pending"},
            {"status": "approved", "reported": True},
        ]},
        {"_id": 0},
    ).sort("created_at", 1).to_list(500)
    wings_by_id = {w["id"]: w for w in await db.wings.find(
        {"id": {"$in": [p["wing_id"] for p in pending if p.get("wing_id")]}},
        {"_id": 0, "id": 1, "name": 1},
    ).to_list(500)}
    users_by_id = {u["id"]: u for u in await db.users.find(
        {"id": {"$in": [p["user_id"] for p in pending]}},
        {"_id": 0, "id": 1, "email": 1, "name": 1, "is_test_account": 1},
    ).to_list(500)}
    out = []
    for p in pending:
        pub = _public_wing_post(p, staff=True)
        wing = wings_by_id.get(p.get("wing_id"), {})
        user = users_by_id.get(p.get("user_id"), {})
        pub["wing_name"] = wing.get("name", "—")
        pub["poster_email"] = user.get("email", "")
        pub["poster_name"] = user.get("name", "")
        out.append(pub)
    return {"posts": out}


@api.get("/research/moderation/{post_id}/image", dependencies=[Depends(require_research_key)])
async def moderation_image(post_id: str):
    post = await db.wing_posts.find_one({"id": post_id})
    if not post or not post.get("image_key"):
        raise HTTPException(404, "That image isn't available.")
    try:
        data = await _photo_storage().get(post["image_key"])
    except Exception:
        logger.exception("wings photo storage get failed (post=%s)", post_id)
        raise HTTPException(404, "That image isn't available.")
    from fastapi.responses import Response
    return Response(content=data, media_type="image/jpeg",
                    headers={"Cache-Control": "private, max-age=60"})


@api.post("/research/moderation/{post_id}/approve", dependencies=[Depends(require_research_key)])
async def moderation_approve(post_id: str, principal: dict = Depends(require_research_key)):
    post = await db.wing_posts.find_one({"id": post_id})
    if not post:
        raise HTTPException(404, "That post isn't available.")
    await db.wing_posts.update_one(
        {"id": post_id},
        {"$set": {"status": "approved", "reported": False,
                  "moderated_at": now_utc().isoformat(),
                  "moderated_by": principal.get("email") or principal.get("id"),
                  "reject_reason": None}},
    )
    return {"ok": True}


@api.post("/research/moderation/{post_id}/reject", dependencies=[Depends(require_research_key)])
async def moderation_reject(post_id: str, body: WingModerateIn,
                             principal: dict = Depends(require_research_key)):
    """Reject sets a preset reason the student sees verbatim. The image is
    deleted from storage immediately — a rejected post never needs to be
    served again, and this keeps storage lean."""
    reason = (body.reason or "").strip()
    if reason not in wings_photos.REJECT_REASONS:
        raise HTTPException(400, "Pick a preset reject reason.")
    post = await db.wing_posts.find_one({"id": post_id})
    if not post:
        raise HTTPException(404, "That post isn't available.")
    image_key = post.get("image_key")
    try:
        if image_key:
            await _photo_storage().delete(image_key)
    except Exception:
        logger.exception("wings photo storage delete failed (reject post=%s)", post_id)
    await db.wing_posts.update_one(
        {"id": post_id},
        {"$set": {"status": "rejected", "reported": False, "image_key": None,
                  "moderated_at": now_utc().isoformat(),
                  "moderated_by": principal.get("email") or principal.get("id"),
                  "reject_reason": wings_photos.REJECT_REASONS[reason]}},
    )
    return {"ok": True, "reason": wings_photos.REJECT_REASONS[reason]}


@api.post("/research/moderation/{post_id}/remove", dependencies=[Depends(require_research_key)])
async def moderation_remove(post_id: str, principal: dict = Depends(require_research_key)):
    """Pull a previously-approved post back out of the feed. Keeps the DB
    row (so engagement counts stay honest) but drops the image."""
    post = await db.wing_posts.find_one({"id": post_id})
    if not post:
        raise HTTPException(404, "That post isn't available.")
    try:
        if post.get("image_key"):
            await _photo_storage().delete(post["image_key"])
    except Exception:
        logger.exception("wings photo storage delete failed (remove post=%s)", post_id)
    await db.wing_posts.update_one(
        {"id": post_id},
        {"$set": {"status": "removed", "reported": False, "image_key": None,
                  "moderated_at": now_utc().isoformat(),
                  "moderated_by": principal.get("email") or principal.get("id")}},
    )
    return {"ok": True}


@api.get("/research/weekly-workflow/week{week}.csv", dependencies=[Depends(require_research_key)])
async def weekly_workflow_csv(week: int):
    """Per-student weekly workflow export: step timestamps + the reflection
    responses captured by the engine. Test accounts are excluded by
    default (same filter as the HEI and wing-posts exports). Free text
    (reflection prompts' optional notes, prompt 3's "what's working") is
    serialised into its own CSV columns verbatim and is NEVER written to
    the server log — the DB is the only place it lives.

    Columns, left to right: email, name, migrated flag, per-step
    completed_at timestamps, reflection p1 selected list, p1 optional
    text, p2 selected, p3 free text, Week 1 goal + plan character counts
    (not the text itself, which already lives in the audit-friendly
    users collection and is deliberately not duplicated here).
    """
    import csv as _csv, io as _io
    if week not in weekly_workflow.SUPPORTED_WEEKS:
        raise HTTPException(404, f"Week {week} isn't served by the weekly workflow.")
    content = weekly_workflow.load_week(week)
    sequence: List[str] = list(content.get("sequence") or [])

    users = {u["id"]: u for u in await db.users.find(
        {}, {"_id": 0, "id": 1, "email": 1, "name": 1, "is_test_account": 1,
             "focus_area": 1, "focus_goal": 1},
    ).to_list(5000)}
    rows = await db.weekly_workflow.find({"week": week}, {"_id": 0}).to_list(10000)

    buf = _io.StringIO()
    w = _csv.writer(buf)
    header = ["email", "name", "focus_area", "goal_chars", "plan_chars", "migrated"]
    header += [f"{sid}_completed_at" for sid in sequence]
    header += ["reflection_p1_selected", "reflection_p1_text",
               "reflection_p2_selected", "reflection_p3_text"]
    w.writerow(header)

    for rec in rows:
        u = users.get(rec.get("user_id")) or {}
        if u.get("is_test_account"):
            continue
        statuses = rec.get("step_statuses") or {}
        completed_ats = [((statuses.get(sid) or {}).get("completed_at") or "") for sid in sequence]
        reflection = (statuses.get("reflection") or {}).get("responses") or {}
        p1 = reflection.get("p1_behind") or {}
        p2 = reflection.get("p2_room") or {}
        p3 = reflection.get("p3_working") or {}
        goal = (u.get("focus_goal") or {}).get("goal") or ""
        plan = (u.get("focus_goal") or {}).get("plan") or ""
        w.writerow([
            u.get("email", ""), u.get("name", ""), u.get("focus_area") or "",
            len(goal), len(plan),
            "yes" if rec.get("migrated") else "no",
            *completed_ats,
            "; ".join(p1.get("selected") or []) if isinstance(p1.get("selected"), list) else "",
            p1.get("text") or "",
            p2.get("selected") or "",
            p3.get("text") or "",
        ])
    from fastapi.responses import Response
    return Response(
        content=buf.getvalue(), media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=weekly_workflow_week{week}.csv"},
    )


@api.get("/research/wing-posts/engagement.csv", dependencies=[Depends(require_research_key)])
async def wing_posts_engagement_csv():
    """Non-content engagement export: how many posts someone shared, how
    many reactions were sent to them (totals, never who reacted). Photos
    and captions NEVER appear in a research export. Test accounts are
    excluded by default to match the HEI export's behaviour."""
    import csv as _csv, io as _io
    users = {u["id"]: u for u in await db.users.find(
        {}, {"_id": 0, "id": 1, "email": 1, "name": 1, "is_test_account": 1},
    ).to_list(5000)}
    posts = await db.wing_posts.find({}, {"_id": 0}).to_list(10000)
    buf = _io.StringIO()
    w = _csv.writer(buf)
    w.writerow(["email", "name", "posts_shared", "posts_pending", "posts_rejected",
                "reactions_received_total"])
    agg: dict[str, dict] = {}
    for p in posts:
        if users.get(p.get("user_id"), {}).get("is_test_account"):
            continue
        bucket = agg.setdefault(p["user_id"], {
            "approved": 0, "pending": 0, "rejected": 0, "reactions": 0,
        })
        if p.get("status") == "approved":
            bucket["approved"] += 1
        elif p.get("status") == "pending":
            bucket["pending"] += 1
        elif p.get("status") == "rejected":
            bucket["rejected"] += 1
        bucket["reactions"] += sum(int(v) for v in (p.get("reactions") or {}).values())
    for uid, b in agg.items():
        u = users.get(uid) or {}
        w.writerow([u.get("email", ""), u.get("name", ""),
                    b["approved"], b["pending"], b["rejected"], b["reactions"]])
    from fastapi.responses import Response
    return Response(content=buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=wing_post_engagement.csv"})


# ----------------------------------------------------------------------------
# Behavioral Safety Layer — a reactive pattern detector, not a diagnostic
# tool and not an onboarding screener. Runs after every meal log and after
# repeated chat-guardrail blocks; never a penalty, never a lost streak.
# ----------------------------------------------------------------------------
async def _create_safety_checkin_if_needed(uid: str, reason: str) -> Optional[dict]:
    last = await db.safety_checkins.find_one(
        {"user_id": uid, "created_at": {"$gte": (now_utc() - timedelta(hours=24)).isoformat()}}
    )
    if last:
        return None
    checkin = {
        "id": new_id(), "user_id": uid, "reason": reason, "created_at": now_utc().isoformat(),
        "acknowledged": False,
        "message": (
            "We noticed your logging looks a little different lately. There's no wrong way to eat, "
            "and this app never judges or penalizes you. How are you feeling about food right now?"
        ),
    }
    await db.safety_checkins.insert_one(dict(checkin))
    return {k: v for k, v in checkin.items() if k != "_id"}


async def run_safety_check(user: dict) -> Optional[dict]:
    uid = user["id"]
    three_days = (now_utc() - timedelta(days=3)).isoformat()
    recent = await db.meals.find({"user_id": uid, "created_at": {"$gte": three_days}}).to_list(200)

    skipped = sum(1 for m in recent if m.get("skipped"))
    small = sum(1 for m in recent if m.get("portion") == "small" and not m.get("skipped"))
    total = len(recent)

    trigger, reason = False, ""
    if skipped >= 3:
        trigger, reason = True, "repeated skipped meals"
    elif total >= 4 and small / total >= 0.75:
        trigger, reason = True, "sustained small-portion pattern"

    if not trigger:
        return None
    return await _create_safety_checkin_if_needed(uid, reason)


async def check_guardrail_block_pattern(uid: str) -> Optional[dict]:
    three_days = (now_utc() - timedelta(days=3)).isoformat()
    blocks = await db.guardrail_blocks.count_documents({"user_id": uid, "created_at": {"$gte": three_days}})
    if blocks < 3:
        return None
    return await _create_safety_checkin_if_needed(
        uid, "repeated attempts to get numeric nutrition or restriction-framed content from the meal chat"
    )


# ----------------------------------------------------------------------------
# The Coach's knowledge base: reviewed-content entries in
# backend/content/kb/*.json, searched with BM25 (see coach_kb.py).
# ----------------------------------------------------------------------------
COACH_KB = coach_kb.KnowledgeBase(coach_kb.load_entries())


# ----------------------------------------------------------------------------
# Auth
# ----------------------------------------------------------------------------
def public_user(u: dict) -> dict:
    profile = u.get("profile", {}) or {}
    has_key = bool(u.get("tamus_api_key_encrypted"))
    on_admin_pool = (not has_key) and tamus_client.is_admin_test_account(u.get("email")) and bool(tamus_client.admin_key_pool())
    return {
        "id": u["id"], "email": u["email"], "name": u.get("name", ""),
        "onboarded": u.get("onboarded", False),
        "age": profile.get("age"),
        "focus_areas": u.get("focus_areas", []),
        "focus_area": u.get("focus_area"),
        "focus_goal": u.get("focus_goal"),
        # null until the participant builds one; the app then shows the default.
        "avatar": u.get("avatar"),
        "wearable_connected": u.get("wearable_connected", False),
        "wearable_provider": u.get("wearable_provider"),
        "wearable_last_sync": u.get("wearable_last_sync"),
        "nudges_enabled": u.get("nudges_enabled", False),
        "nudge_time": u.get("nudge_time", "19:00"),
        "sleep_schedule": u.get("sleep_schedule"),
        # TAMU AI is mandatory and the app's only AI provider. `tamus_has_key`
        # tells the client whether THIS participant needs to add a key
        # before the coach/photo logging/dining assistant will respond;
        # `tamus_on_admin_pool` covers the small staff-allowlisted
        # QA/testing exception (see tamus_client.py).
        "tamus_has_key": has_key,
        "tamus_on_admin_pool": on_admin_pool,
        "tamus_ai_available": has_key or on_admin_pool,
        "tamus_model_chat": u.get("tamus_model_chat") or tamus_client.DEFAULT_CHAT_MODEL,
        "tamus_model_vision": u.get("tamus_model_vision") or tamus_client.DEFAULT_VISION_MODEL,
    }


@api.get("/")
async def root():
    return {"app": "LLHS — Live Long, Heart Strong", "status": "ok"}


# ----------------------------------------------------------------------------
# ASA24 accounts: each participant is given the next free account from the
# batch on /research-admin when they create their account (or, if the batch
# was empty then, the next time they open the app; see get_recall).
# ----------------------------------------------------------------------------
async def _assign_asa24_account(user_id: str) -> Optional[str]:
    """Links the participant to the next free ASA24 account from the
    uploaded batch. Returns the username, or None if the batch is used up
    (it is assigned on a later visit, once staff add more)."""
    for _ in range(5):
        if (link := await db.asa24_links.find_one({"user_id": user_id})):
            return link["asa24_username"]
        acct = await db.asa24_accounts.find_one_and_update(
            {"assigned_to": None}, {"$set": {"assigned_to": user_id, "assigned_at": now_utc().isoformat()}},
            sort=[("username", 1)], return_document=ReturnDocument.AFTER,
        )
        if not acct:
            return None
        try:
            await db.asa24_links.insert_one({"user_id": user_id, "asa24_username": acct["username"],
                                             "updated_at": now_utc().isoformat(), "updated_by": "auto-assigned"})
            return acct["username"]
        except DuplicateKeyError:
            other = await db.asa24_links.find_one({"asa24_username": acct["username"]})
            if other and other["user_id"] != user_id:
                # Staff linked this username to someone by hand: mark it
                # taken and try the next free account.
                await db.asa24_accounts.update_one({"username": acct["username"]}, {"$set": {"assigned_to": other["user_id"]}})
            else:
                # A parallel request already linked this participant.
                await db.asa24_accounts.update_one({"username": acct["username"]}, {"$set": {"assigned_to": None, "assigned_at": None}})
    return None


@api.post("/auth/login")
@limiter.limit("10/minute")
async def login(request: Request, body: LoginIn):
    email = body.email.strip().lower()
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(body.password, user["password"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return {"token": create_token(user["id"]), "user": public_user(user)}


# ----------------------------------------------------------------------------
# Create account: anyone with an email at ALLOWED_EMAIL_DOMAIN (default
# tamu.edu) who doesn't have an account yet, after proving the address with
# a 6-digit emailed code (see signup.py). They're given an ASA24 login from
# the batch on /research-admin straight away.
# ----------------------------------------------------------------------------
def _domain_message() -> str:
    return f"Use your @{signup.allowed_domain()} email address."


@api.post("/auth/signup/start")
@limiter.limit("5/hour")
async def signup_start(request: Request, body: SignupStartIn):
    email = body.email.strip().lower()
    if not signup.email_allowed(email):
        raise HTTPException(400, _domain_message())
    if not mailer.configured() and ON_VERCEL:
        raise HTTPException(503, "Creating an account by email isn't set up yet. Contact the study team.")
    if await db.users.find_one({"email": email}, {"_id": 0, "id": 1}):
        raise HTTPException(409, "That email already has an account. Sign in instead, or use Forgot password.")
    prev = await db.signup_codes.find_one({"email": email})
    if prev and (now_utc() - datetime.fromisoformat(prev["sent_at"])).total_seconds() < signup.CODE_RESEND_SECONDS:
        # Don't email again, but let them enter the code they already have.
        return {"sent": True, "already_sent": True,
                "message": f"We already sent a code to {email} a moment ago. Enter it below. It expires in {signup.CODE_TTL_MINUTES} minutes."}
    code = signup.new_code()
    if mailer.configured():
        try:
            await asyncio.to_thread(signup.send_signup_email, email, code)
        except Exception as e:
            logger.error(f"Sign-up email to {email} failed: {e}")
            raise HTTPException(502, "We couldn't send the email. Check the address and try again.")
    else:
        logger.warning(f"Email not configured; sign-up code for {email}: {code}")
    await db.signup_codes.update_one({"email": email}, {"$set": {
        "email": email, "code_hash": signup.hash_code(email, code, JWT_SECRET),
        "sent_at": now_utc().isoformat(), "attempts": 0,
        "expires_at": now_utc() + timedelta(minutes=signup.CODE_TTL_MINUTES),
    }}, upsert=True)
    return {"sent": True, "message": f"We sent a 6-digit code to {email}. It expires in {signup.CODE_TTL_MINUTES} minutes."}


@api.post("/auth/signup")
@limiter.limit("10/hour")
async def signup_finish(request: Request, body: SignupIn):
    email = body.email.strip().lower()
    if not signup.email_allowed(email):
        raise HTTPException(400, _domain_message())
    rec = await db.signup_codes.find_one({"email": email})
    if not rec:
        raise HTTPException(400, "Ask for a sign-up code first.")
    expires = rec["expires_at"] if rec["expires_at"].tzinfo else rec["expires_at"].replace(tzinfo=timezone.utc)
    if expires < now_utc() or rec.get("attempts", 0) >= signup.CODE_MAX_ATTEMPTS:
        raise HTTPException(400, "That code has expired. Ask for a new one.")
    if not signup.codes_match(rec["code_hash"], email, body.code, JWT_SECRET):
        await db.signup_codes.update_one({"email": email}, {"$inc": {"attempts": 1}})
        raise HTTPException(400, "That code doesn't match. Check the email and try again.")
    user = {
        "id": new_id(), "email": email, "name": body.name.strip(), "password": hash_password(body.password),
        "onboarded": False, "profile": {}, "focus_areas": [], "allergy_terms": [],
        "created_at": now_utc().isoformat(), "points": 0, "badges": [],
        "wearable_connected": False, "wearable_provider": None, "wearable_last_sync": None,
        "nudges_enabled": False, "nudge_time": "19:00",
        "tamus_api_key_encrypted": None, "tamus_model_chat": None, "tamus_model_vision": None,
    }
    try:
        await db.users.insert_one(user)
    except DuplicateKeyError:
        raise HTTPException(409, "That email already has an account. Sign in instead, or use Forgot password.")
    await db.signup_codes.delete_one({"email": email})
    await _assign_asa24_account(user["id"])
    return {"token": create_token(user["id"]), "user": public_user(user)}


# ----------------------------------------------------------------------------
# Forgot password: a 6-digit code emailed to the account, then a new password
# (see password_reset.py). The request step answers the same way whether or
# not the email has an account, so it can't be used to find out who's enrolled.
# ----------------------------------------------------------------------------
RESET_SENT_MESSAGE = "If an account exists for that email, we sent a 6-digit code. It expires in 15 minutes."


@api.post("/auth/password/forgot")
@limiter.limit("5/hour")
async def forgot_password(request: Request, body: ForgotPasswordIn):
    email = body.email.strip().lower()
    if not mailer.configured() and ON_VERCEL:
        raise HTTPException(503, "Password reset by email isn't set up yet. Contact the study team.")
    user = await db.users.find_one({"email": email}, {"_id": 0, "id": 1})
    prev = await db.password_resets.find_one({"email": email})
    too_soon = prev and (now_utc() - datetime.fromisoformat(prev["sent_at"])).total_seconds() < password_reset.CODE_RESEND_SECONDS
    if user and not too_soon:
        code = password_reset.new_code()
        if mailer.configured():
            try:
                await asyncio.to_thread(password_reset.send_reset_email, email, code)
            except Exception as e:
                logger.error(f"Password reset email to {email} failed: {e}")
                raise HTTPException(502, "We couldn't send the email. Try again in a few minutes.")
        else:
            logger.warning(f"Email not configured; password reset code for {email}: {code}")
        await db.password_resets.update_one({"email": email}, {"$set": {
            "email": email, "code_hash": password_reset.hash_code(email, code, JWT_SECRET),
            "sent_at": now_utc().isoformat(), "attempts": 0,
            "expires_at": now_utc() + timedelta(minutes=password_reset.CODE_TTL_MINUTES),
        }}, upsert=True)
    return {"sent": True, "message": RESET_SENT_MESSAGE}


@api.post("/auth/password/reset")
@limiter.limit("10/minute")
async def reset_password(request: Request, body: ResetPasswordIn):
    email = body.email.strip().lower()
    rec = await db.password_resets.find_one({"email": email})
    if not rec:
        raise HTTPException(400, "That code isn't valid. Ask for a new one.")
    expires = rec["expires_at"] if rec["expires_at"].tzinfo else rec["expires_at"].replace(tzinfo=timezone.utc)
    if expires < now_utc() or rec.get("attempts", 0) >= password_reset.CODE_MAX_ATTEMPTS:
        raise HTTPException(400, "That code has expired. Ask for a new one.")
    if not password_reset.codes_match(rec["code_hash"], email, body.code, JWT_SECRET):
        await db.password_resets.update_one({"email": email}, {"$inc": {"attempts": 1}})
        raise HTTPException(400, "That code doesn't match. Check the email and try again.")
    user = await db.users.find_one({"email": email})
    if not user:
        raise HTTPException(400, "That code isn't valid. Ask for a new one.")
    await db.users.update_one({"id": user["id"]}, {"$set": {
        "password": hash_password(body.new_password), "sessions_valid_after": now_utc().isoformat()}})
    await db.password_resets.delete_one({"email": email})
    return {"token": create_token(user["id"]), "user": public_user(await db.users.find_one({"id": user["id"]}))}


@api.get("/auth/me")
async def me(user: dict = Depends(current_user)):
    return public_user(user)


@api.post("/auth/logout")
async def logout(creds: HTTPAuthorizationCredentials = Depends(bearer), user: dict = Depends(current_user)):
    try:
        payload = jwt.decode(creds.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        jti = payload.get("jti")
        exp = payload.get("exp")
    except Exception:
        return {"ok": True}
    if jti and exp:
        await db.revoked_tokens.update_one(
            {"jti": jti},
            {"$set": {"jti": jti, "expires_at": datetime.fromtimestamp(exp, tz=timezone.utc)}},
            upsert=True,
        )
    return {"ok": True}


# ----------------------------------------------------------------------------
# Onboarding — Nutrition & Lifestyle Profile survey
# ----------------------------------------------------------------------------
@api.get("/onboarding/profile-survey")
async def get_profile_survey(user: Optional[dict] = Depends(optional_user)):
    """Schema for everyone; an authenticated caller also gets their saved
    answers so the same form can be reused for "Edit my profile"."""
    answers = (user.get("profile") or {}) if user else {}
    return {"sections": PROFILE_SURVEY_SECTIONS, "questions": PROFILE_SURVEY_SCHEMA, "answers": answers}


@api.post("/onboarding/profile-survey")
async def submit_profile_survey(body: ProfileSurveyIn, user: dict = Depends(current_user)):
    answers = strip_inapplicable_answers(body.answers)
    validate_profile_answers(answers)
    allergy_terms = _extract_allergy_terms(answers)
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {"onboarded": True, "profile": answers, "allergy_terms": allergy_terms}},
    )
    updated = await db.users.find_one({"id": user["id"]})
    return {"user": public_user(updated)}


@api.patch("/onboarding/profile-survey")
async def update_profile_survey(body: ProfileSurveyIn, user: dict = Depends(current_user)):
    """Lets a participant update answers later (e.g. a change in kitchen
    access or a newly-disclosed allergy) — merges into the existing profile
    rather than requiring a full resubmission. A null value clears that
    answer (the key is removed, never stored as null)."""
    merged = {**(user.get("profile") or {}), **body.answers}
    merged = strip_inapplicable_answers({k: v for k, v in merged.items() if v is not None})
    validate_profile_answers(merged)
    allergy_terms = _extract_allergy_terms(merged)
    await db.users.update_one({"id": user["id"]}, {"$set": {"profile": merged, "allergy_terms": allergy_terms}})
    updated = await db.users.find_one({"id": user["id"]})
    return {"user": public_user(updated)}


# ----------------------------------------------------------------------------
# F4 — logging
# ----------------------------------------------------------------------------
async def award_points(uid: str, amount: int, badge: Optional[str] = None):
    update: dict = {"$inc": {"points": amount}}
    if badge:
        update["$addToSet"] = {"badges": badge}
    await db.users.update_one({"id": uid}, update)


# ----------------------------------------------------------------------------
# Badges — the "First Lesson" and "Skill Builder" badges are awarded inline
# at the point they're earned (video-complete / game-complete). Two badges
# were previously defined but never awarded; this is the single place they
# get checked. Called after any meal is logged.
#
#   Consistent Logger  — logged a meal on every one of the last 7 calendar
#                        days (local-date-wise, derived from the stored UTC
#                        ISO timestamps). "Consistent," not "perfect": 7
#                        consecutive days is enough, there's no higher tier.
#   Balanced Week      — in the trailing 7 days, at least 5 of the logged
#                        meals cover ≥2 distinct core food categories
#                        (`meal_has_core_categories`, min_kinds=2). Matches
#                        the cohort-side "balanced plate" definition so the
#                        two counters can never contradict each other.
#
# Pure functions here (`days_logged_streak`, `balanced_meals_count`) so the
# tests can exercise the criteria without a database.
# ----------------------------------------------------------------------------
CONSISTENT_LOGGER_DAYS = 7
BALANCED_WEEK_MIN_MEALS = 5


def _meal_local_day(meal: dict) -> str:
    """YYYY-MM-DD of the meal's `created_at`, in the study TZ. A log at
    11:30 PM Chicago (04:30 UTC the next day) belongs to today's bucket,
    not tomorrow's — slicing the UTC ISO string would hand it to tomorrow."""
    iso = meal.get("created_at") or ""
    if not iso:
        return ""
    return study_day_key(iso)


def days_logged_streak(meals: List[dict], today: date_cls) -> int:
    """How many consecutive calendar days up to and including `today` have at
    least one logged meal. Used for the Consistent Logger badge."""
    days = {_meal_local_day(m) for m in meals if _meal_local_day(m)}
    streak = 0
    cursor = today
    while cursor.isoformat() in days:
        streak += 1
        cursor = cursor - timedelta(days=1)
    return streak


def balanced_meals_count(meals: List[dict], today: date_cls, window_days: int = 7) -> int:
    """Count of meals in the trailing `window_days` window (ending `today`)
    that pass the lightweight balanced-ish check. Used for Balanced Week."""
    start = today - timedelta(days=window_days - 1)
    return sum(
        1 for m in meals
        if _meal_local_day(m) >= start.isoformat()
        and _meal_local_day(m) <= today.isoformat()
        and meal_has_core_categories(m, min_kinds=2)
    )


async def check_and_award_logging_badges(uid: str) -> List[str]:
    """Idempotent: can be called after every meal log, awards each badge at
    most once per user. Returns the list of badges newly awarded on this
    call (so the client can show a one-time acknowledgement)."""
    u = await db.users.find_one({"id": uid}) or {}
    already = set(u.get("badges", []))
    newly: List[str] = []
    today = study_today()
    meals = await db.meals.find({"user_id": uid}).to_list(1000)

    if "Consistent Logger" not in already:
        if days_logged_streak(meals, today) >= CONSISTENT_LOGGER_DAYS:
            await award_points(uid, 0, badge="Consistent Logger")
            newly.append("Consistent Logger")

    if "Balanced Week" not in already:
        if balanced_meals_count(meals, today) >= BALANCED_WEEK_MIN_MEALS:
            await award_points(uid, 0, badge="Balanced Week")
            newly.append("Balanced Week")

    return newly


DAILY_POINT_CAPS = {"meals": 8, "activities": 6, "sleeps": 3, "chat_messages": 15}
MEAL_POINTS = 10
# A meal that includes the participant's focus-area food earns a bonus, once a
# day, so working on the focus area is rewarded at least as much as watching
# a lesson (program.POINTS["watch"]).
FOCUS_MEAL_BONUS = 10


async def _focus_meal_bonus(user: dict, meal: dict) -> int:
    cats = {c for cid in user.get("focus_areas") or [] for c in personal_path.FOCUS_CATEGORIES.get(cid, [])}
    if not cats or meal.get("skipped") or not cats & set(meal.get("categories") or []):
        return 0
    day = study_day_key(meal["created_at"])
    if await db.focus_meal_bonus.find_one({"user_id": user["id"], "day": day}):
        return 0
    await db.focus_meal_bonus.insert_one({"user_id": user["id"], "day": day, "meal_id": meal["id"]})
    await award_points(user["id"], FOCUS_MEAL_BONUS)
    return FOCUS_MEAL_BONUS


async def award_points_capped(collection_name: str, uid: str, amount: int, day_start_iso: str) -> int:
    count_today = await db[collection_name].count_documents({"user_id": uid, "created_at": {"$gte": day_start_iso}})
    cap = DAILY_POINT_CAPS.get(collection_name, 999999)
    if count_today > cap:
        return 0
    await award_points(uid, amount)
    return amount


def _today_start_iso() -> str:
    """Lower bound for "today's" $gte queries (DAILY_POINT_CAPS, chat caps).
    Chicago midnight, expressed in UTC — so caps roll over at the student's
    midnight, not whenever UTC rolls over."""
    return study_day_start_utc_iso()


@api.get("/meals/categories")
async def get_log_categories():
    return {"categories": LIGHTWEIGHT_LOG_CATEGORIES}


async def _internal_log_meal(user: dict, body: MealIn) -> dict:
    """Shared write path for logging a meal — used by both POST /meals and
    the chat coach's confirmed action flow (see /chat/confirm-action), so
    there is exactly one place that awards points, runs the safety check,
    and inserts the row. Never bypassed by the coach: the model can only
    propose this action, this function is what actually writes it."""
    meal = {"id": new_id(), "user_id": user["id"], "created_at": now_utc().isoformat(), **body.dict()}
    await db.meals.insert_one(dict(meal))
    checkin = await run_safety_check(user)
    awarded = await award_points_capped("meals", user["id"], MEAL_POINTS, _today_start_iso())
    awarded += await _focus_meal_bonus(user, meal)
    newly_awarded_badges = await check_and_award_logging_badges(user["id"])
    meal.pop("_id", None)
    return {
        "meal": meal,
        "safety_checkin": checkin,
        "points_awarded": awarded,
        "badges_awarded": newly_awarded_badges,
    }


@api.post("/meals")
async def create_meal(body: MealIn, user: dict = Depends(current_user)):
    return await _internal_log_meal(user, body)


@api.get("/meals")
async def list_meals(user: dict = Depends(current_user)):
    meals = await db.meals.find({"user_id": user["id"]}).sort("created_at", -1).to_list(200)
    return [{k: v for k, v in m.items() if k != "_id"} for m in meals]


@api.get("/activities")
async def list_activities(user: dict = Depends(current_user)):
    acts = await db.activities.find({"user_id": user["id"]}).sort("created_at", -1).to_list(200)
    return [{k: v for k, v in a.items() if k != "_id"} for a in acts]


@api.get("/sleep")
async def list_sleeps(user: dict = Depends(current_user)):
    sleeps = await db.sleeps.find({"user_id": user["id"]}).sort("created_at", -1).to_list(200)
    return [{k: v for k, v in s.items() if k != "_id"} for s in sleeps]


@api.post("/meals/categorize-text")
@limiter.limit("20/minute")
async def categorize_meal_text(request: Request, body: MealTextCategorizeIn, user: dict = Depends(current_user)):
    """Answers the specific open technical question in the review notes:
    can a participant type a natural-language description and have it
    auto-mapped to the lightweight log categories, instead of manually
    ticking each one? Yes — this is that path."""
    import json

    system = (
        "You help a college student log a meal in a heart-health app by mapping a free-text description to a "
        "fixed set of food categories. NEVER estimate or mention calories, grams, or portion weight. "
        f"Categories: {', '.join(c['id'] for c in LIGHTWEIGHT_LOG_CATEGORIES)}. "
        'Respond ONLY with compact JSON: {"categories": ["subset of the category ids above"], '
        '"suggested_name": "short meal name", "confidence": number between 0 and 1}. No prose, no markdown.'
    )
    tamus_key_required = False
    try:
        raw = await run_llm(user, system, body.description, f"categorize-{user['id']}")
        cleaned = raw.strip().strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        start, end = cleaned.find("{"), cleaned.rfind("}")
        data = json.loads(cleaned[start:end + 1]) if start >= 0 else {}
    except tamus_client.TamusKeyRequiredError:
        tamus_key_required = True
        data = {}
    except Exception as e:
        logger.error(f"Meal text categorization error: {e}")
        data = {}

    categories = [c for c in (data.get("categories") or []) if c in LOG_CATEGORY_IDS]
    allergy_terms = user.get("allergy_terms", [])
    allergy_flag = any(term in body.description.lower() for term in allergy_terms) if allergy_terms else False
    return {
        "categories": categories,
        "suggested_name": await _guard_text(user, "categorize-text", data.get("suggested_name"), body.description[:60]),
        "confidence": float(data.get("confidence", 0.0) or 0.0),
        "allergy_flag": allergy_flag,
        "tamus_key_required": tamus_key_required,
    }


async def _internal_log_activity(user: dict, body: ActivityIn) -> dict:
    """Shared write path for POST /activities and the chat coach's
    confirmed action flow."""
    doc = {"id": new_id(), "user_id": user["id"], "created_at": now_utc().isoformat(), **body.dict()}
    await db.activities.insert_one(dict(doc))
    awarded = await award_points_capped("activities", user["id"], 10, _today_start_iso())
    doc.pop("_id", None)
    doc["points_awarded"] = awarded
    return doc


@api.post("/activities")
async def create_activity(body: ActivityIn, user: dict = Depends(current_user)):
    return await _internal_log_activity(user, body)


async def _internal_log_sleep(user: dict, body: SleepIn) -> dict:
    """Shared write path for POST /sleep and the chat coach's confirmed
    action flow. Always force-sets source="manual" regardless of what's
    passed in — real wearable-sourced sleep can only ever arrive through
    /wearable/sync-sleep (see the #5 security fix); the coach can never
    claim a higher-confidence reading than the user actually gave it."""
    doc = {"id": new_id(), "user_id": user["id"], "created_at": now_utc().isoformat(),
           **{**body.dict(), "source": "manual"}}
    await db.sleeps.insert_one(dict(doc))
    awarded = await award_points_capped("sleeps", user["id"], 5, _today_start_iso())
    doc.pop("_id", None)
    doc["points_awarded"] = awarded
    return doc


@api.post("/sleep")
async def create_sleep(body: SleepIn, user: dict = Depends(current_user)):
    return await _internal_log_sleep(user, body)


# ----------------------------------------------------------------------------
# Wearable Rest/Move — Fitbit primary per the 9/10/26 deck ("Move & Sleep:
# continuous Fitbit-derived data, participant can manually correct
# inaccurate entries"), Apple Health / Health Connect kept as alternates.
# Manual entry is always retained — never excludes a participant without
# hardware.
#
# NOTE FOR ENGINEERING: real native reads (HealthKit/Health Connect, or a
# Fitbit OAuth integration) require work this build doesn't include — see
# frontend/src/native/health.ts. The connect/sync/status contract below is
# real and persisted; the review notes mark the final wearable decision as
# still pending, so this stays intentionally provider-agnostic.
# ----------------------------------------------------------------------------
@api.get("/wearable/status")
async def wearable_status(user: dict = Depends(current_user)):
    return {
        "connected": user.get("wearable_connected", False),
        "provider": user.get("wearable_provider"),
        "last_sync": user.get("wearable_last_sync"),
    }


@api.post("/wearable/connect")
async def wearable_connect(body: WearableConnectIn, user: dict = Depends(current_user)):
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {"wearable_connected": True, "wearable_provider": body.provider, "wearable_last_sync": None}},
    )
    return {"connected": True, "provider": body.provider, "last_sync": None}


@api.post("/wearable/disconnect")
async def wearable_disconnect(user: dict = Depends(current_user)):
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {"wearable_connected": False, "wearable_provider": None, "wearable_last_sync": None}},
    )
    return {"connected": False, "provider": None, "last_sync": None}


async def _upsert_wearable_day(user: dict, body: WearableSyncIn, ts: str) -> str:
    """Stores one device day. A wearable reading is ONE row per participant,
    collection and recorded_date: re-syncing the same day replaces it
    rather than adding a second night (a device re-sends days it already
    sent). Manual rows are never touched."""
    if body.hours is None and body.activity_minutes is None:
        raise HTTPException(400, "Nothing to sync — send sleep hours and/or activity minutes.")
    if body.steps is not None and body.activity_minutes is None:
        raise HTTPException(400, "Send steps together with that day's activity minutes.")
    if (body.sleep_start or body.sleep_end) and body.hours is None:
        raise HTTPException(400, "Send sleep start and end together with that night's hours.")
    recorded_date = body.recorded_date or study_today().isoformat()
    if body.hours is not None:
        doc = {"user_id": user["id"], "created_at": ts, "hours": body.hours, "source": "wearable",
               "recorded_date": recorded_date, "bedtime": body.sleep_start, "wake": body.sleep_end}
        key = {"user_id": user["id"], "source": "wearable", "recorded_date": recorded_date}
        if await db.sleeps.find_one(key):
            await db.sleeps.update_one(key, {"$set": doc})
        else:
            await db.sleeps.insert_one({"id": new_id(), **doc})
    if body.activity_minutes is not None:
        doc = {"user_id": user["id"], "created_at": ts, "minutes": body.activity_minutes, "kind": "wearable",
               "source": "wearable", "recorded_date": recorded_date, "steps": body.steps}
        key = {"user_id": user["id"], "source": "wearable", "recorded_date": recorded_date}
        if await db.activities.find_one(key):
            await db.activities.update_one(key, {"$set": doc})
        else:
            await db.activities.insert_one({"id": new_id(), **doc})
    return recorded_date


@api.post("/wearable/sync-sleep")
async def wearable_sync_sleep(body: WearableSyncIn, user: dict = Depends(current_user)):
    if not user.get("wearable_connected"):
        raise HTTPException(400, "Connect a wearable before syncing.")
    ts = now_utc().isoformat()
    recorded_date = await _upsert_wearable_day(user, body, ts)
    await db.users.update_one({"id": user["id"]}, {"$set": {"wearable_last_sync": ts}})
    return {"synced": True, "hours": body.hours, "activity_minutes": body.activity_minutes, "recorded_date": recorded_date,
            "sleep_start": body.sleep_start, "sleep_end": body.sleep_end, "steps": body.steps}


class WearableBatchIn(BaseModel):
    # Up to a month of device days at once (a first sync after connecting,
    # or catching up after the phone was off). Each day names its date.
    days: List[WearableSyncIn] = Field(min_length=1, max_length=31)

    @field_validator("days")
    @classmethod
    def _dated(cls, v: List[WearableSyncIn]) -> List[WearableSyncIn]:
        dates = [d.recorded_date for d in v]
        if any(d is None for d in dates):
            raise ValueError("Every day needs a recorded_date")
        if len(set(dates)) != len(dates):
            raise ValueError("Each recorded_date may appear once")
        return v


@api.post("/wearable/sync-days")
async def wearable_sync_days(body: WearableBatchIn, user: dict = Depends(current_user)):
    """Several device days in one call, each upserted by its date (see
    _upsert_wearable_day), so the behavioral twin has the history it needs
    to notice weekday/weekend and timing patterns."""
    if not user.get("wearable_connected"):
        raise HTTPException(400, "Connect a wearable before syncing.")
    ts = now_utc().isoformat()
    synced = [await _upsert_wearable_day(user, day, ts) for day in body.days]
    await db.users.update_one({"id": user["id"]}, {"$set": {"wearable_last_sync": ts}})
    return {"synced": True, "days": sorted(synced)}


# ----------------------------------------------------------------------------
# Gentle Nudges — optional, no-pressure meal-log reminders. Opt-in only.
# ----------------------------------------------------------------------------
@api.get("/settings/nudges")
async def get_nudge_settings(user: dict = Depends(current_user)):
    return {"enabled": user.get("nudges_enabled", False), "time": user.get("nudge_time", "19:00")}


@api.patch("/settings/nudges")
async def update_nudge_settings(body: NudgeSettingsIn, user: dict = Depends(current_user)):
    await db.users.update_one({"id": user["id"]}, {"$set": {"nudges_enabled": body.enabled, "nudge_time": body.time}})
    return {"enabled": body.enabled, "time": body.time}


@api.put("/settings/sleep-schedule")
async def set_sleep_schedule(body: SleepScheduleIn, user: dict = Depends(current_user)):
    schedule = {"bedtime": body.bedtime, "wake": body.wake}
    await db.users.update_one({"id": user["id"]}, {"$set": {"sleep_schedule": schedule}})
    return schedule


# ----------------------------------------------------------------------------
# TAMU AI — the app's sole AI provider, mandatory per participant. A saved
# key is used automatically for every AI feature (the coach, photo/text meal
# logging assist, dining plate review and chat-build-meal); there is no
# separate on/off toggle and no default to fall back to if a participant
# hasn't added one yet (see tamus_client.py's module docstring, and
# resolve_user_key() for the small staff-managed admin/testing exception).
# ----------------------------------------------------------------------------
@api.get("/settings/tamus/models")
async def get_tamus_models(user: dict = Depends(current_user)):
    return {"models": tamus_client.TAMUS_MODEL_CATALOG, "default_chat": tamus_client.DEFAULT_CHAT_MODEL,
            "default_vision": tamus_client.DEFAULT_VISION_MODEL}


def _tamus_settings_view(u: dict) -> dict:
    has_key = bool(u.get("tamus_api_key_encrypted"))
    on_admin_pool = (not has_key) and tamus_client.is_admin_test_account(u.get("email")) and bool(tamus_client.admin_key_pool())
    return {
        "has_key": has_key,
        "on_admin_pool": on_admin_pool,
        "ai_available": has_key or on_admin_pool,
        "model_chat": u.get("tamus_model_chat") or tamus_client.DEFAULT_CHAT_MODEL,
        "model_vision": u.get("tamus_model_vision") or tamus_client.DEFAULT_VISION_MODEL,
    }


@api.get("/settings/tamus")
async def get_tamus_settings(user: dict = Depends(current_user)):
    return _tamus_settings_view(user)


@api.patch("/settings/tamus")
async def update_tamus_settings(body: TamusSettingsIn, user: dict = Depends(current_user)):
    if body.model_chat and not tamus_client.is_known_model(body.model_chat):
        raise HTTPException(400, "Unknown chat model id")
    if body.model_vision and not tamus_client.is_known_model(body.model_vision):
        raise HTTPException(400, "Unknown vision model id")

    update: dict = {}
    if body.model_chat:
        update["tamus_model_chat"] = body.model_chat
    if body.model_vision:
        update["tamus_model_vision"] = body.model_vision
    if body.api_key:
        # Strip ASCII whitespace plus invisible characters (NBSP, zero-width
        # spaces, BOM) that commonly ride along when a key is pasted from a
        # doc. Interior non-ASCII characters are left for chat()'s header
        # check to reject with a clear message — see tamus_client.clean_api_key.
        key = tamus_client.clean_api_key(body.api_key)
        if not key:
            raise HTTPException(400, "That TAMU API key is empty after trimming whitespace.")
        update["tamus_api_key_encrypted"] = tamus_client.encrypt_key(key)

    if update:
        await db.users.update_one({"id": user["id"]}, {"$set": update})
    fresh = await db.users.find_one({"id": user["id"]})
    return _tamus_settings_view(fresh)


@api.delete("/settings/tamus")
async def clear_tamus_settings(user: dict = Depends(current_user)):
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {"tamus_api_key_encrypted": None, "tamus_model_chat": None, "tamus_model_vision": None}},
    )
    fresh = await db.users.find_one({"id": user["id"]})
    return _tamus_settings_view(fresh)


@api.post("/settings/tamus/test")
@limiter.limit("10/minute")
async def test_tamus_connection(request: Request, user: dict = Depends(current_user)):
    encrypted = user.get("tamus_api_key_encrypted")
    if not encrypted:
        return {"ok": False, "message": "No TAMU API key saved yet."}
    try:
        raw_key = tamus_client.decrypt_key(encrypted)
    except Exception:
        return {"ok": False, "message": "Saved key could not be read — please re-enter it."}
    # Also strip here: a key saved before this fix landed may still have
    # trailing invisibles stored. The strip is idempotent so a freshly-saved
    # clean key is unchanged.
    raw_key = tamus_client.clean_api_key(raw_key)
    model = user.get("tamus_model_chat") or tamus_client.DEFAULT_CHAT_MODEL
    # test_key() never raises — belt-and-suspenders catch here anyway so a
    # future refactor can't accidentally regress the CORS-strip crash where
    # an unhandled 500 means the browser reports "Failed to fetch".
    try:
        ok, message = await tamus_client.test_key(raw_key, model)
    except Exception as e:  # pragma: no cover — defensive
        logger.warning("TAMU test endpoint caught %s", e.__class__.__name__)
        ok, message = False, f"Couldn't test the TAMU AI key ({e.__class__.__name__}) — try again."
    return {"ok": ok, "message": message}


async def llm_vision_call(user: dict, system: str, user_text: str, session_id: str, image_base64: str, mime_type: str = "image/jpeg") -> str:
    """TAMU AI is the sole vision provider. Raises TamusKeyRequiredError
    (uncaught) when the participant has no usable key — callers decide how
    to surface that (see analyze_photo's except block)."""
    raw_key = tamus_client.resolve_user_key(user)
    model = user.get("tamus_model_vision") or tamus_client.DEFAULT_VISION_MODEL
    return await tamus_client.chat(raw_key, model, system, user_text, image_base64=image_base64, image_mime=mime_type)


@api.get("/goals")
async def list_goals(user: dict = Depends(current_user)):
    goals = await db.goals.find({"user_id": user["id"]}).to_list(100)
    return [{k: v for k, v in g.items() if k != "_id"} for g in goals]


@api.post("/goals")
async def create_goal(body: GoalIn, user: dict = Depends(current_user)):
    doc = {"id": new_id(), "user_id": user["id"], "created_at": now_utc().isoformat(), "progress": 0, "achieved": False, **body.dict()}
    await db.goals.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


# ----------------------------------------------------------------------------
# HEI-2020 assessments — researcher import + participant-facing read/compare
# ----------------------------------------------------------------------------
@api.post("/research/hei2020-assessments")
async def import_hei_assessment(body: HeiAssessmentImportIn, principal: dict = Depends(require_research_key)):
    participant = await db.users.find_one({"email": body.participant_email.strip().lower()})
    if not participant:
        raise HTTPException(404, "No participant with that email.")
    doc = {
        "id": new_id(), "user_id": participant["id"], "assessment_type": body.assessment_type,
        "components": body.components, "source": "asa24_import",
        "imported_by": principal.get("email") or "shared research key",
        "recorded_at": body.recorded_at or now_utc().isoformat(), "notes": body.notes,
        "created_at": now_utc().isoformat(),
    }
    await db.hei_assessments.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


# ----------------------------------------------------------------------------
# ASA24 upload — staff export the Totals CSV from the ASA24 Researcher site
# (no API exists and the site may not be scraped), upload it here, and the
# app scores it with the NCI HEI-2020 macro port in hei2020_scoring.py.
# Participants are matched by the ASA24 username staff assigned them, kept
# in db.asa24_links, so no names or emails ever go through ASA24.
# ----------------------------------------------------------------------------
ASA24_MAX_CSV_CHARS = 5_000_000
ASA24_EXPECTED_RECALLS = asa24_schedule.RECALLS_PER_POINT  # a weekday and a weekend day per point
# Per-recall energy outside this range is flagged for staff review, not
# dropped — a screening aid pending the nutrition team's own QC rules.
ASA24_KCAL_REVIEW_RANGE = (500, 5000)


class Asa24LinkIn(BaseModel):
    participant_email: EmailStr
    asa24_username: str = Field(min_length=1, max_length=100)


class Asa24UploadIn(BaseModel):
    csv_text: str = Field(min_length=1, max_length=ASA24_MAX_CSV_CHARS)
    assessment_type: Literal["baseline", "checkin_1", "checkin_2"]
    # Import only: restrict to these ASA24 usernames (e.g. the ones staff
    # ticked in the preview), and whether to replace an existing assessment
    # of the same type instead of skipping that participant.
    usernames: Optional[List[str]] = Field(default=None, max_length=2000)
    overwrite: bool = False


def _norm_asa24_username(u: str) -> str:
    return u.strip().lower()


# Where "Start recall" sends participants. Set ASA24_RESPONDENT_URL to the
# study's own respondent login link from the ASA24 researcher site.
ASA24_RESPONDENT_URL = os.environ.get("ASA24_RESPONDENT_URL", "https://asa24.nci.nih.gov/")


def _study_start(user: dict) -> date_cls:
    """Day 0 of a participant's recall schedule: the day they joined, in
    the study time zone (like every other day boundary in the app)."""
    raw = user.get("created_at")
    return date_cls.fromisoformat(study_day_key(raw)) if raw else study_today()


class ResearchLoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class ResearcherCreateIn(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=10, max_length=200)
    role: Literal["staff", "admin"] = "staff"


class ResearcherUpdateIn(BaseModel):
    active: Optional[bool] = None
    role: Optional[Literal["staff", "admin"]] = None
    password: Optional[str] = Field(default=None, min_length=10, max_length=200)


@api.post("/research/auth/login")
@limiter.limit("10/minute")
async def research_login(request: Request, body: ResearchLoginIn):
    r = await db.researchers.find_one({"email": body.email.strip().lower()})
    if not r or not verify_password(body.password, r["password"]) or not r.get("active", True):
        raise HTTPException(401, "Invalid email or password")
    await db.researchers.update_one({"id": r["id"]}, {"$set": {"last_login_at": now_utc().isoformat()}})
    return {"token": create_research_token(r["id"]), "researcher": public_researcher(r)}


@api.post("/research/auth/logout")
async def research_logout(principal: dict = Depends(require_research_key)):
    if principal["kind"] == "researcher" and principal.get("jti") and principal.get("exp"):
        await db.revoked_tokens.update_one(
            {"jti": principal["jti"]},
            {"$set": {"jti": principal["jti"], "expires_at": datetime.fromtimestamp(principal["exp"], tz=timezone.utc)}},
            upsert=True,
        )
    return {"ok": True}


@api.get("/research/auth/me")
async def research_me(principal: dict = Depends(require_research_key)):
    return {k: principal[k] for k in ("kind", "id", "email", "role")}


@api.get("/research/researchers")
async def list_researchers(_: dict = Depends(require_research_admin)):
    return [public_researcher(r) for r in await db.researchers.find({}, {"_id": 0}).to_list(500)]


@api.post("/research/researchers")
async def create_researcher(body: ResearcherCreateIn, principal: dict = Depends(require_research_admin)):
    email = body.email.strip().lower()
    if await db.researchers.find_one({"email": email}):
        raise HTTPException(409, "A researcher with that email already exists.")
    r = {"id": new_id(), "email": email, "name": body.name.strip(), "password": hash_password(body.password),
         "role": body.role, "active": True, "created_at": now_utc().isoformat(), "created_by": principal.get("email")}
    await db.researchers.insert_one(dict(r))
    return public_researcher(r)


@api.patch("/research/researchers/{researcher_id}")
async def update_researcher(researcher_id: str, body: ResearcherUpdateIn, principal: dict = Depends(require_research_admin)):
    if principal.get("id") == researcher_id and (body.active is False or body.role == "staff"):
        raise HTTPException(400, "You can't disable or demote your own account.")
    update: Dict[str, Any] = {}
    if body.active is not None:
        update["active"] = body.active
    if body.role is not None:
        update["role"] = body.role
    if body.password:
        update["password"] = hash_password(body.password)
    if not update:
        raise HTTPException(400, "Nothing to update.")
    res = await db.researchers.update_one({"id": researcher_id}, {"$set": update})
    if not res.matched_count:
        raise HTTPException(404, "No researcher with that id.")
    return public_researcher(await db.researchers.find_one({"id": researcher_id}))


@api.get("/research/participants", dependencies=[Depends(require_research_key)])
async def research_participants():
    users = await db.users.find(
        {}, {"_id": 0, "id": 1, "name": 1, "email": 1, "created_at": 1, "is_test_account": 1}).to_list(5000)
    links = {l["user_id"]: l["asa24_username"] for l in await db.asa24_links.find({}, {"_id": 0}).to_list(5000)}
    done: Dict[str, List[str]] = {}
    for a in await db.hei_assessments.find({}, {"_id": 0, "user_id": 1, "assessment_type": 1}).to_list(20000):
        done.setdefault(a["user_id"], []).append(a["assessment_type"])
    finished: Dict[str, Dict[str, List[str]]] = {}
    for f in await db.asa24_recall_finished.find({}, {"_id": 0}).to_list(20000):
        finished.setdefault(f["user_id"], {})[f["assessment_type"]] = asa24_schedule.finished_times(f)
    today = study_today()
    out = []
    for u in users:
        st = asa24_schedule.recall_status(_study_start(u), today, finished.get(u["id"], {}), done.get(u["id"], []))
        out.append({**u,
            "is_test_account": is_test_account(u), "asa24_username": links.get(u["id"]),
            "assessments": sorted(set(done.get(u["id"], [])), key=ASSESSMENT_TYPES.index),
            # What staff need to act on: whose recall is finished and waiting
            # for the Totals download, and who is still due.
            "recall": {k: st.get(k) for k in ("assessment_type", "label", "state", "due_by", "finished_at",
                                              "recalls_done", "recalls_needed")},
        })
    return out


class ParticipantFlagsIn(BaseModel):
    is_test_account: bool


@api.patch("/research/participants/{user_id}", dependencies=[Depends(require_research_key)])
async def set_participant_flags(user_id: str, body: ParticipantFlagsIn):
    """Lets staff mark QA/demo accounts so they drop out of cohort counts
    without having to use an @example.com address."""
    res = await db.users.update_one({"id": user_id}, {"$set": {"is_test_account": body.is_test_account}})
    if not res.matched_count:
        raise HTTPException(404, "No participant with that id.")
    return {"id": user_id, "is_test_account": body.is_test_account}


# ---- From your meals: rules vs AI, side by side (staff only) ----------------------
# Every time a participant's block is computed, both engines' decisions for
# that day are recorded in db.twin_decisions. These endpoints let the study
# team read them per participant and in aggregate, and recompute both on
# demand, so the two engines can be compared before converging on one.
def _twin_decision_view(row: dict) -> dict:
    def summary(block: Optional[dict]) -> Optional[dict]:
        if not block:
            return None
        return {
            "available": block.get("available", True),
            "reason": block.get("reason"),
            "status": block.get("status"),
            "habits": [{"label": h.get("label"), "times": h.get("times"), "top_slot": h.get("top_slot"),
                        "food_id": h.get("food_id")} for h in block.get("habits") or []],
            "suggestions": [{"id": s.get("id"), "kind": s.get("kind"), "swap_label": s.get("swap_label"),
                             "habit": (s.get("habit") or {}).get("label"), "why": s.get("why"),
                             "on_menu_today": [f"{m.get('item_name')} ({m.get('hall_label')}, {m.get('period')})"
                                               for m in s.get("on_menu_today") or []]}
                            for s in block.get("suggestions") or []],
        }
    rules, llm = summary(row.get("rules")), summary(row.get("llm"))
    top = lambda b: ((b or {}).get("suggestions") or [{}])[0].get("id") if b else None  # noqa: E731
    return {
        "user_id": row.get("user_id"), "day": row.get("day"), "shown": row.get("shown"),
        "engine_setting": row.get("engine_setting"), "focus_area": row.get("focus_area"),
        "menu_source": row.get("menu_source"), "updated_at": row.get("updated_at"),
        "rules": rules, "llm": llm,
        "agree_top_swap": ((top(rules) == top(llm)) if (top(rules) or top(llm)) else None)
        if (rules and llm and llm.get("available")) else None,
    }


@api.get("/research/twin-decisions", dependencies=[Depends(require_research_key)])
async def research_twin_decisions(user_id: Optional[str] = None, days: int = 14):
    """Both engines' decisions, newest first, for one participant (or all)
    over the last `days` days."""
    days = max(1, min(days, 90))
    since = (study_today() - timedelta(days=days - 1)).isoformat()
    query: Dict[str, Any] = {"day": {"$gte": since}}
    if user_id:
        query["user_id"] = user_id
    rows = await db.twin_decisions.find(query).sort("day", -1).to_list(2000)
    users = {u["id"]: u for u in await db.users.find(
        {}, {"_id": 0, "id": 1, "name": 1, "email": 1, "is_test_account": 1}).to_list(5000)}
    out = []
    for r in rows:
        u = users.get(r.get("user_id"), {})
        out.append({**_twin_decision_view(r), "name": u.get("name"), "email": u.get("email")})
    return {"engine_setting": TWIN_ENGINE, "days": days, "decisions": out}


@api.get("/research/twin-decisions/summary", dependencies=[Depends(require_research_key)])
async def research_twin_decisions_summary(days: int = 14):
    """How often the two engines agree, over the last `days` days."""
    days = max(1, min(days, 90))
    since = (study_today() - timedelta(days=days - 1)).isoformat()
    rows = await db.twin_decisions.find({"day": {"$gte": since}}).to_list(5000)
    both = [r for r in rows if r.get("rules") and (r.get("llm") or {}).get("available")]
    views = [_twin_decision_view(r) for r in both]
    def labels(block):  # noqa: E306
        return {str(h.get("label") or "").lower() for h in (block or {}).get("habits") or [] if h.get("label")}
    habit_overlap = [len(labels(v["rules"]) & labels(v["llm"])) / len(labels(v["rules"]) | labels(v["llm"]))
                     for v in views if labels(v["rules"]) | labels(v["llm"])]
    return {
        "engine_setting": TWIN_ENGINE, "days": days,
        "decisions": len(rows),
        "with_both_engines": len(both),
        "participants_with_both": len({r["user_id"] for r in both}),
        "llm_unavailable": sum(1 for r in rows if r.get("llm") and not r["llm"].get("available")),
        "llm_not_run": sum(1 for r in rows if r.get("llm") is None),
        "top_swap_agreement": (sum(1 for v in views if v["agree_top_swap"]) / len(views)) if views else None,
        "mean_habit_overlap": (sum(habit_overlap) / len(habit_overlap)) if habit_overlap else None,
        "mean_habits_rules": (sum(len(v["rules"]["habits"]) for v in views) / len(views)) if views else None,
        "mean_habits_llm": (sum(len(v["llm"]["habits"]) for v in views) / len(views)) if views else None,
    }


class TwinRecomputeIn(BaseModel):
    user_id: str = Field(min_length=1, max_length=80)


@api.post("/research/twin-decisions/recompute", dependencies=[Depends(require_research_key)])
async def research_twin_recompute(body: TwinRecomputeIn):
    """Runs BOTH engines for one participant now (the AI engine uses that
    participant's own TAMU key, or the admin pool) and stores the result.
    Nothing shown to the participant changes unless TWIN_ENGINE says so."""
    user = await db.users.find_one({"id": body.user_id})
    if not user:
        raise HTTPException(404, "No participant with that id.")
    await _from_your_meals(user, force_llm=True)
    row = await db.twin_decisions.find_one({"user_id": user["id"], "day": study_today().isoformat()}) or {}
    return _twin_decision_view(row)


# ---- The behavioral twin, for staff ----------------------------------------------
# One participant's profile (every fact with its status and source), what
# they said and why, and each day's steps with the factors that chose them;
# plus the study-wide evaluation the team asked for: are the noticed
# patterns right (participants' own answers), are the steps appropriate
# (staff ratings), do they respect stated constraints, and does feedback
# change what comes next.
@api.get("/research/twin-profile", dependencies=[Depends(require_research_key)])
async def research_twin_profile(user_id: str, days: int = 14):
    user = await db.users.find_one({"id": user_id})
    if not user:
        raise HTTPException(404, "No participant with that id.")
    days = max(1, min(days, 90))
    since = (study_today() - timedelta(days=days - 1)).isoformat()
    strip = lambda rows: [{k: v for k, v in r.items() if k != "_id"} for r in rows]  # noqa: E731
    comp = await _twin_compute(user)  # first, so today's snapshot is in the list below
    facts = strip(await db.twin_facts.find({"user_id": user_id}).to_list(500))
    events = strip(await db.twin_events.find({"user_id": user_id}).sort("created_at", -1).to_list(300))
    plans = strip(await db.twin_plans.find({"user_id": user_id}).to_list(500))
    snaps = strip(await db.twin_snapshots.find({"user_id": user_id, "day": {"$gte": since}}).sort("day", -1).to_list(90))
    return {"user": {"id": user["id"], "name": user.get("name"), "email": user.get("email"),
                     "focus_area": user.get("focus_area")},
            "now": comp["view"], "decisions": comp["selection"]["decisions"],
            "state": {"confirmed": comp["state"]["confirmed"], "stated": sorted(comp["state"]["stated"]),
                      "constraints": sorted(comp["state"]["constraints"]), "contexts": comp["state"]["contexts"],
                      "domains_on": comp["state"]["domains_on"], "paused": comp["state"]["paused"]},
            "facts": facts, "events": events, "plans": plans, "snapshots": snaps}


class TwinRatingIn(BaseModel):
    user_id: str = Field(min_length=1, max_length=80)
    day: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    rec_id: str = Field(min_length=1, max_length=80)
    rating: Literal["appropriate", "not_appropriate"]
    note: Optional[str] = Field(default=None, max_length=500)


@api.post("/research/twin-snapshots/rate")
async def research_rate_twin_step(body: TwinRatingIn, principal: dict = Depends(require_research_key)):
    """A staff judgement of one step shown to one participant on one day —
    the 'appropriateness of recommendations' measure."""
    key = {"user_id": body.user_id, "day": body.day}
    snap = await db.twin_snapshots.find_one(key)
    if not snap or not any(r.get("id") == body.rec_id for r in snap.get("recommendations") or []):
        raise HTTPException(404, "That step wasn't shown to this participant that day.")
    ratings = dict(snap.get("ratings") or {})
    ratings[body.rec_id] = {"rating": body.rating, "note": (body.note or "").strip() or None,
                            "by": principal.get("email") or principal.get("kind"), "at": now_utc().isoformat()}
    await db.twin_snapshots.update_one(key, {"$set": {"ratings": ratings}})
    return {"ok": True, "ratings": ratings}


_TWIN_VIOLATION_CODE = {"availability": "context", "energy": "time"}


def _rate(n: int, d: int) -> Optional[float]:
    return round(n / d, 3) if d else None


@api.get("/research/twin-eval", dependencies=[Depends(require_research_key)])
async def research_twin_eval(days: int = 30, include_test: bool = False):
    """Study-wide evaluation of the behavioral twin over the last `days`."""
    days = max(1, min(days, 180))
    since = (study_today() - timedelta(days=days - 1)).isoformat()
    users = await db.users.find({}, {"_id": 0, "id": 1, "is_test_account": 1, "email": 1}).to_list(5000)
    keep = {u["id"] for u in users if include_test or not is_test_account(u)}
    events = [e for e in await db.twin_events.find({"day": {"$gte": since}}).to_list(20000) if e.get("user_id") in keep]
    snaps = [s for s in await db.twin_snapshots.find({"day": {"$gte": since}}).to_list(20000) if s.get("user_id") in keep]

    # 1. Pattern accuracy: of the patterns participants answered, how many they said were right.
    patterns: Dict[str, Counter] = {}
    for e in events:
        if e.get("kind") != "answer":
            continue
        fam = "diet.regular" if str(e.get("key", "")).startswith("diet.regular.") else e.get("key")
        patterns.setdefault(fam, Counter())[e.get("answer")] += 1
    accuracy = {k: {"answered": sum(c.values()), "yes": c["yes"], "sometimes": c["sometimes"], "no": c["no"],
                    "confirmed_rate": _rate(c["yes"] + c["sometimes"], sum(c.values()))} for k, c in sorted(patterns.items())}

    # 2. What participants did with the steps, by domain, type and technique.
    def tally(key_fn):
        out: Dict[str, Counter] = {}
        for e in events:
            if e.get("kind") == "step":
                for k in key_fn(e):
                    out.setdefault(k, Counter())[e.get("response")] += 1
        return {k: {**dict(c), "acceptance_rate": _rate(c["accept"], c["accept"] + c["decline"]),
                    "success_rate": _rate(c["worked"] + c["still_doing"], c["worked"] + c["still_doing"] + c["didnt_fit"]
                                          + c["lapsed"])} for k, c in sorted(out.items())}
    reasons = Counter(r for e in events if e.get("kind") == "step" for r in e.get("reasons") or [])
    notes = Counter(e.get("interpreted_by") for e in events if e.get("note"))

    # 3. Appropriateness (staff ratings) and constraint adherence (every step shown).
    shown = [(s, r) for s in snaps for r in s.get("recommendations") or []]
    rated = [rt for s in snaps for rt in (s.get("ratings") or {}).values()]
    with_violation = [(s, r) for s, r in shown if r.get("violations")]
    new_with_violation = [(s, r) for s, r in with_violation if r.get("status") != "trying"]

    # 4. Feedback incorporation: after a reason is given, do later steps respect it, and is
    #    a different approach to the same pattern offered within REST_DAYS?
    by_user: Dict[str, List[dict]] = {}
    for s in snaps:
        by_user.setdefault(s["user_id"], []).append(s)
    respected = checked = alt_offered = alt_checked = 0
    for e in events:
        if e.get("kind") != "step" or e.get("response") not in ("decline", "didnt_fit"):
            continue
        later = [s for s in by_user.get(e["user_id"], []) if s["day"] > e["day"]]
        if not later:
            continue
        codes = {_TWIN_VIOLATION_CODE.get(c.split(":", 1)[0], c.split(":", 1)[0]) for c in e.get("learned") or []}
        codes &= {"cost", "time", "schedule", "equipment", "not_into", "context"}
        if codes:  # reasons that rule steps out (forgetting or the weather only re-rank them)
            checked += 1
            bad = any(set(r.get("violations") or []) & codes
                      for s in later for r in s.get("recommendations") or [] if r.get("status") != "trying")
            respected += 0 if bad else 1
        if e.get("patterns"):
            alt_checked += 1
            window_end = (date_cls.fromisoformat(e["day"]) + timedelta(days=twin_recommend.REST_DAYS)).isoformat()
            alt_offered += int(any(
                r.get("id") != e.get("rec_id") and set(r.get("patterns") or []) & set(e["patterns"])
                for s in later if s["day"] <= window_end for r in s.get("recommendations") or []))
    return {
        "days": days, "participants": len({e["user_id"] for e in events} | {s["user_id"] for s in snaps}),
        "pattern_accuracy": accuracy,
        "steps_by_domain": tally(lambda e: e.get("domains") or []),
        "steps_by_type": tally(lambda e: [e.get("type")]),
        "steps_by_technique": tally(lambda e: e.get("bct") or []),
        "reasons": dict(reasons.most_common()),
        "notes_interpreted_by": dict(notes),
        "appropriateness": {"rated": len(rated), "appropriate": sum(1 for r in rated if r.get("rating") == "appropriate"),
                            "rate": _rate(sum(1 for r in rated if r.get("rating") == "appropriate"), len(rated))},
        "constraint_adherence": {"steps_shown": len(shown), "with_violation": len(with_violation),
                                 "new_steps_with_violation": len(new_with_violation),
                                 "rate": _rate(len(shown) - len(new_with_violation), len(shown))},
        "feedback_incorporation": {"reasons_checked": checked, "respected_later": respected,
                                   "respected_rate": _rate(respected, checked),
                                   "declines_with_pattern": alt_checked, "alternative_offered": alt_offered,
                                   "alternative_rate": _rate(alt_offered, alt_checked)},
    }


@api.put("/research/asa24/links")
async def link_asa24_username(body: Asa24LinkIn, principal: dict = Depends(require_research_key)):
    participant = await db.users.find_one({"email": body.participant_email.strip().lower()})
    if not participant:
        raise HTTPException(404, "No participant with that email.")
    username = _norm_asa24_username(body.asa24_username)
    taken = await db.asa24_links.find_one({"asa24_username": username})
    if taken and taken["user_id"] != participant["id"]:
        raise HTTPException(409, "That ASA24 username is already linked to another participant.")
    await db.asa24_links.update_one(
        {"user_id": participant["id"]},
        {"$set": {"user_id": participant["id"], "asa24_username": username,
                  "display_username": body.asa24_username.strip(), "updated_at": now_utc().isoformat(),
                  "updated_by": principal.get("email") or "shared research key"}},
        upsert=True,
    )
    return {"user_id": participant["id"], "asa24_username": username}


@api.delete("/research/asa24/links/{asa24_username}", dependencies=[Depends(require_research_key)])
async def unlink_asa24_username(asa24_username: str):
    res = await db.asa24_links.delete_one({"asa24_username": _norm_asa24_username(asa24_username)})
    if not res.deleted_count:
        raise HTTPException(404, "No link with that ASA24 username.")
    return {"ok": True}


class Asa24AccountsIn(BaseModel):
    text: str = Field(min_length=1, max_length=200_000)


@api.post("/research/asa24/accounts")
async def add_asa24_accounts(body: Asa24AccountsIn, principal: dict = Depends(require_research_key)):
    """Adds ASA24 respondent accounts (created on the ASA24 researcher site)
    to the pool new participants are assigned from. Passwords are stored
    encrypted, with the same key as participants' TAMU AI keys."""
    try:
        rows = asa24_accounts.parse_accounts(body.text)
    except asa24_accounts.AccountsFileError as e:
        raise HTTPException(400, str(e))
    linked = {l["asa24_username"] for l in await db.asa24_links.find({}, {"_id": 0, "asa24_username": 1}).to_list(20000)}
    added, skipped = [], []
    for r in rows:
        if r["username"] in linked:
            skipped.append(r["username"])
            continue
        try:
            await db.asa24_accounts.insert_one({
                "username": r["username"], "password_encrypted": tamus_client.encrypt_key(r["password"]),
                "assigned_to": None, "assigned_at": None, "added_at": now_utc().isoformat(),
                "added_by": principal.get("email") or "shared research key",
            })
            added.append(r["username"])
        except DuplicateKeyError:
            skipped.append(r["username"])
    return {"added": len(added), "skipped": skipped}


@api.get("/research/asa24/accounts", dependencies=[Depends(require_research_key)])
async def list_asa24_accounts():
    accts = await db.asa24_accounts.find({}, {"_id": 0, "password_encrypted": 0}).sort("username", 1).to_list(20000)
    ids = [a["assigned_to"] for a in accts if a.get("assigned_to")]
    emails = {u["id"]: u["email"] for u in await db.users.find({"id": {"$in": ids}}, {"_id": 0, "id": 1, "email": 1}).to_list(20000)}
    free = sum(1 for a in accts if not a.get("assigned_to"))
    return {"free": free, "assigned": len(accts) - free, "accounts": [
        {"username": a["username"], "assigned_email": emails.get(a.get("assigned_to") or ""),
         "assigned_at": a.get("assigned_at")} for a in accts]}


async def _asa24_plan(body: Asa24UploadIn) -> Dict[str, Any]:
    """Parses + scores the upload and works out, per ASA24 username, what an
    import would do. Shared by preview (read-only) and import."""
    try:
        by_user = hei2020_scoring.parse_totals_csv(body.csv_text)
    except hei2020_scoring.Asa24FileError as e:
        raise HTTPException(400, str(e))

    links = {l["asa24_username"]: l["user_id"] for l in await db.asa24_links.find({}, {"_id": 0}).to_list(5000)}
    users = {u["id"]: u for u in await db.users.find(
        {"id": {"$in": list(links.values())}}, {"_id": 0, "id": 1, "email": 1, "name": 1, "created_at": 1}).to_list(5000)}
    existing = {a["user_id"] for a in await db.hei_assessments.find(
        {"assessment_type": body.assessment_type}, {"_id": 0, "user_id": 1}).to_list(20000)}
    wanted = {_norm_asa24_username(u) for u in body.usernames} if body.usernames is not None else None

    rows = []
    for raw_username, recalls in sorted(by_user.items()):
        username = _norm_asa24_username(raw_username)
        user_id = links.get(username)
        participant = users.get(user_id) if user_id else None
        warnings = []
        in_window = True
        if participant:
            # Only recalls done in this point's window count toward it, so an
            # export spanning several points can't blend them into one score.
            window = asa24_schedule.window_for(_study_start(participant), body.assessment_type)
            split = asa24_schedule.split_by_window(recalls, window)
            if split["outside"]:
                warnings.append(f"{len(split['outside'])} recall(s) dated outside the {window['label']} window "
                                f"({window['opens_on']:%b %d}–{window['due_by']:%b %d}) left out.")
            if split["undated"]:
                warnings.append(f"{len(split['undated'])} recall(s) have no date in the file, so they couldn't be "
                                "checked against the window; included.")
            recalls = split["inside"] + split["undated"]
            in_window = bool(recalls)
        if in_window and len(recalls) != ASA24_EXPECTED_RECALLS:
            warnings.append(f"{len(recalls)} recall(s) in file — study design expects {ASA24_EXPECTED_RECALLS}.")
        elif in_window and (problem := asa24_schedule.weekday_weekend_problem(recalls)):
            warnings.append(f"Expected one weekday and one weekend-day recall, but {problem}.")
        recall_nos = [r.get("RecallNo") for r in recalls if r.get("RecallNo")]
        if len(recall_nos) != len(set(recall_nos)):
            warnings.append("Duplicate RecallNo rows — the same recall may be in the file twice.")
        lo, hi = ASA24_KCAL_REVIEW_RANGE
        odd = [r for r in recalls if not (lo <= r["KCAL"] <= hi)]
        if odd:
            warnings.append(f"{len(odd)} recall(s) with energy outside {lo}–{hi} kcal — review before importing.")

        if not participant:
            status = "unmatched"
        elif not in_window:
            status = "out_of_window"
        elif wanted is not None and username not in wanted:
            status = "not_selected"
        elif user_id in existing and not body.overwrite:
            status = "exists"
        else:
            status = "ready"

        # 5:2 weekday/weekend weighting on intake variables (nutrition
        # team 2026-11-06, Scoring and Feedback Q1), plus equal-day
        # pooling as sensitivity. The student side shows primary only;
        # the research export includes both. When a point has two
        # weekdays or two weekend days or any undated recall, the
        # primary falls back to equal pooling with a ``weighting_fallback``
        # flag so the comparison report can track it.
        weighted = recall_weighting.score_with_weighting(recalls) if recalls else {
            "primary": {"method": recall_weighting.METHOD_EQUAL,
                        "weighting_fallback": recall_weighting.FALLBACK_REASON_INSUFFICIENT_RECALLS,
                        "scored": {"recall_count": 0, "components": {}, "total_score": 0.0, "summed_inputs": {}}},
            "sensitivity": {"method": recall_weighting.METHOD_EQUAL,
                            "scored": {"recall_count": 0, "components": {}, "total_score": 0.0, "summed_inputs": {}}},
            "classifications": [],
        }
        scored = weighted["primary"]["scored"]
        if weighted["primary"]["weighting_fallback"]:
            warnings.append(
                "5:2 weighting not applied: "
                f"{weighted['primary']['weighting_fallback']}. "
                "Equal-day pooling was used as a fallback."
            )
        rows.append({
            "asa24_username": username,
            "participant": {"email": participant["email"], "name": participant.get("name")} if participant else None,
            "user_id": user_id if participant else None,
            "status": status,
            "warnings": warnings,
            "recall_count": scored["recall_count"],
            "recall_dates": sorted(d.isoformat() for d in (asa24_schedule.recall_date(x) for x in recalls) if d),
            "components": scored["components"],
            "total_score": scored["total_score"],
            "scoring_method": weighted["primary"]["method"],
            "weighting_fallback": weighted["primary"]["weighting_fallback"],
            "_scored": scored,
            "_weighted": weighted,
        })
    return {"assessment_type": body.assessment_type, "rows": rows}


def _public_plan(plan: Dict[str, Any]) -> Dict[str, Any]:
    rows = [{k: v for k, v in r.items() if k not in ("_scored", "_weighted", "user_id")} for r in plan["rows"]]
    counts: Dict[str, int] = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return {"assessment_type": plan["assessment_type"], "counts": counts, "rows": rows}


@api.post("/research/asa24/preview", dependencies=[Depends(require_research_key)])
async def preview_asa24_upload(body: Asa24UploadIn):
    return _public_plan(await _asa24_plan(body))


@api.post("/research/asa24/import")
async def import_asa24_upload(body: Asa24UploadIn, principal: dict = Depends(require_research_key)):
    plan = await _asa24_plan(body)
    imported = []
    for r in plan["rows"]:
        if r["status"] != "ready":
            continue
        scored = r["_scored"]
        weighted = r.get("_weighted") or {}
        if body.overwrite:
            await db.hei_assessments.delete_many({"user_id": r["user_id"], "assessment_type": body.assessment_type})
        await db.hei_assessments.insert_one({
            "id": new_id(), "user_id": r["user_id"], "assessment_type": body.assessment_type,
            # The STUDENT-FACING components are the primary (5:2 weighted
            # when applicable; equal-day pooling as a documented fallback —
            # see `scoring_method` and `weighting_fallback` below).
            "components": scored["components"], "source": "asa24_totals_upload",
            "scoring": "NCI hei2020.score.macro.sas v1.0 (Python port), simple algorithm per person",
            "scoring_method": r.get("scoring_method"),
            "weighting_fallback": r.get("weighting_fallback"),
            "recall_count": scored["recall_count"], "summed_inputs": scored["summed_inputs"],
            "recall_dates": r["recall_dates"],
            # Day classifications per recall — the derived eating date,
            # day type, and which date source it came from. Stored for
            # research audit; never shown to the student.
            "recall_classifications": weighted.get("classifications") or [],
            # Equal-day-pooling sensitivity analysis. Research-only.
            "sensitivity": weighted.get("sensitivity"),
            "total_score": scored["total_score"], "warnings": r["warnings"],
            "imported_by": principal.get("email") or "shared research key",
            "recorded_at": now_utc().isoformat(), "created_at": now_utc().isoformat(),
        })
        r["status"] = "imported"
        imported.append(r["asa24_username"])
    out = _public_plan(plan)
    out["imported"] = imported
    return out


@api.get("/research/hei/weighting-comparison.csv", dependencies=[Depends(require_research_key)])
async def export_weighting_comparison(include_test: bool = False):
    """Staff-only side-by-side of the 5:2-weighted scores (shown to the
    student) vs equal-day pooling (sensitivity analysis). Nutrition team
    2026-11-06, Scoring and Feedback Q1: "We should examine whether the
    two approaches meaningfully change participants' HEI scores,
    identified dietary strengths, or recommended focus areas." One row
    per assessment; columns include ``total_score_difference``, booleans
    for whether the strengths set or room-to-grow set changed, and the
    ``weighting_fallback`` reason (if any) for the primary method.

    Test accounts are excluded by default; pass ``?include_test=true``
    to include them."""
    users = {u["id"]: {**u, "is_test_account": is_test_account(u)} for u in await db.users.find(
        {}, {"_id": 0, "id": 1, "name": 1, "email": 1, "is_test_account": 1}).to_list(5000)}
    links = {l["user_id"]: l.get("display_username") or l["asa24_username"]
             for l in await db.asa24_links.find({}, {"_id": 0}).to_list(5000)}
    rows = await db.hei_assessments.find({}, {"_id": 0}).to_list(50000)
    comparison = recall_weighting.comparison_rows(rows, [c["id"] for c in HEI2020_COMPONENTS])
    text = hei_export.weighting_comparison_csv(users, links, comparison,
                                               asa24_schedule.LABELS, include_test=include_test)
    suffix = "" if include_test else "-no-test"
    name = f"llhs-hei-weighting-comparison{suffix}-{study_today().isoformat()}.csv"
    return Response(content=text, media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"})


@api.get("/research/hei/scores.csv", dependencies=[Depends(require_research_key)])
async def export_hei_scores(include_test: bool = False):
    """Every imported HEI-2020 assessment as CSV, for analysis (staff only).

    Test accounts (``is_test_account=True`` — the Lab Test Wing cohort,
    anything on ``@example.com``, anything on the TAMUS admin test
    allowlist) are **excluded by default**: without this, a 30-minute
    rehearsal session's worth of fake plates would silently appear in
    the analysis file.

    Pass ``?include_test=true`` to opt them back in — the staff page
    exposes this as an "Include test accounts" checkbox so the operator
    doing a scheduled export never has to remember the URL knob."""
    users = {u["id"]: {**u, "is_test_account": is_test_account(u)} for u in await db.users.find(
        {}, {"_id": 0, "id": 1, "name": 1, "email": 1, "is_test_account": 1}).to_list(5000)}
    links = {l["user_id"]: l.get("display_username") or l["asa24_username"]
             for l in await db.asa24_links.find({}, {"_id": 0}).to_list(5000)}
    rows = await db.hei_assessments.find({}, {"_id": 0}).to_list(50000)
    text = hei_export.scores_csv(users, links, rows, [c["id"] for c in HEI2020_COMPONENTS],
                                 asa24_schedule.LABELS, ASSESSMENT_TYPES,
                                 include_test=include_test)
    suffix = "" if include_test else "-no-test"
    name = f"llhs-hei-scores{suffix}-{study_today().isoformat()}.csv"
    return Response(content=text, media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"})


@api.get("/assessments/hei2020/history")
async def hei_assessment_history(user: dict = Depends(current_user)):
    rows = await db.hei_assessments.find({"user_id": user["id"]}).sort("recorded_at", 1).to_list(10)
    return [{"id": r["id"], "assessment_type": r["assessment_type"], "recorded_at": r["recorded_at"]} for r in rows]


@api.get("/assessments/hei2020/focus-candidates")
async def hei_focus_candidates(user: dict = Depends(current_user)):
    """The eight focus areas with room for improvement, most room first
    (labels only, never numbers), plus the participant's current area and
    goal so week 5 can offer "keep it or change it". Also returns the
    per-area bars (combined Grains / combined Fats, expandable to show
    the two component bars — nutrition team 2026-11-06 item 1); fills
    are 0.0–1.0 ratios used only for bar widths, never as displayed
    numbers."""
    assessment = await _latest_assessment(user["id"])
    current = user.get("focus_area")
    goal = user.get("focus_goal") or {}
    base = {"current": focus_areas.public(current) if current in focus_areas.BY_ID else None,
            "goal": goal.get("goal"), "plan": goal.get("plan"), "min_selection": 1, "max_selection": 1}
    if not assessment:
        return {"has_assessment": False, "candidates": [], "bars": [], **base}
    return {"has_assessment": True, "assessment_type": assessment["assessment_type"],
            "candidates": _area_candidates(assessment),
            "bars": focus_areas.bars(assessment.get("components", {}), HEI2020_BY_ID),
            **base}


def _area_candidates(assessment: dict) -> List[dict]:
    return focus_areas.candidates(assessment.get("components", {}), HEI2020_BY_ID, BENCHMARK_TOLERANCE)


async def _internal_set_focus_areas(user: dict, body: FocusAreasIn) -> dict:
    """Shared write path for POST /profile/focus-areas and the chat coach's
    confirmed action flow. Any of the eight areas can be chosen (the
    suggestions are guidance, not a rule). Changing area without a new goal
    clears the old goal, which belonged to the old area."""
    assessment = await _latest_assessment(user["id"])
    if not assessment:
        raise HTTPException(400, "Your focus area can be chosen once your first food recall results are in.")
    same_area = user.get("focus_area") == body.area_id
    goal = {"goal": body.goal, "plan": body.plan}
    if not (body.goal or body.plan):
        goal = (user.get("focus_goal") or {}) if same_area else {}
    components = focus_areas.components_of(body.area_id)
    # focus_areas (component ids) keeps the Eat rings, Coach prompts, Future Me
    # and My Path working; focus_areas_set_at dates the My Path milestone.
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {"focus_area": body.area_id, "focus_areas": components, "focus_goal": goal,
                  "focus_areas_set_at": now_utc().isoformat()}},
    )
    return {"focus_area": focus_areas.public(body.area_id), "focus_areas": components,
            "goal": goal.get("goal"), "plan": goal.get("plan")}


@api.post("/profile/focus-areas")
async def set_focus_areas(body: FocusAreasIn, user: dict = Depends(current_user)):
    return await _internal_set_focus_areas(user, body)


@api.patch("/profile/avatar")
async def set_avatar(body: avatar.AvatarPatch, user: dict = Depends(current_user)):
    """Save the participant's chosen avatar parts. Appearance only — there is
    deliberately no body size or shape field (see avatar.py)."""
    merged = avatar.merge_avatar(user.get("avatar"), body)
    await db.users.update_one({"id": user["id"]}, {"$set": {"avatar": merged}})
    return {"avatar": merged}


# ----------------------------------------------------------------------------
# FOOD / MOVE / REST domains — replaces the old single 0-100 "digital twin"
# score entirely, per the review notes ("The participant-facing LE8 framing
# should be removed... these domains should remain distinct rather than
# being combined into a single overall heart-health score").
#
# Participant-facing number discipline, enforced HERE (not just trusted to
# the frontend):
#   - Food is reported as the eight focus areas only: the chosen focus
#     area, strengths and other areas, labels only. No component or score
#     number is returned; the 13 HEI-2020 components stay on the server.
#   - Strengths carry ONLY a direction string ("above_national_benchmark")
#     — per the Population Reference Marker spec ("Direction only, never a
#     number").
#   - Move/Rest: raw logged stats only, no invented 0-100 score — the
#     review notes mark those domains' reference values as still being
#     determined by the nutrition team.
# ----------------------------------------------------------------------------
@api.get("/domains/food")
async def domain_food(user: dict = Depends(current_user)):
    assessment = await _latest_assessment(user["id"])
    if not assessment:
        return {
            "has_assessment": False,
            "message": "Your Food results will appear here after your first dietary assessment is processed.",
            "focus_area": None, "strengths": [], "room_to_grow": [], "other_areas": [],
        }
    # Students see the eight focus areas only (focus, strengths, room to
    # grow, other areas); the 13 components are used for scoring and never
    # leave the server. Ranking (strengths = top STRENGTHS_COUNT, room-to-
    # grow = bottom ROOM_TO_GROW_COUNT) is in focus_areas.py per the
    # nutrition team's 2026-11-06 confirmation (item 2, "Strength or room
    # to grow").
    area_id = user.get("focus_area") if user.get("focus_area") in focus_areas.BY_ID else None
    buckets = focus_areas.strengths_and_room_to_grow(
        assessment["components"], HEI2020_BY_ID, focus_area=area_id,
    )
    # Per-area + per-component bars for the baseline-feedback / Food view,
    # with Grains and Fats as combined bars that expand on tap. Fills are
    # 0.0–1.0 ratios (never shown as numbers) — nutrition team 2026-11-06,
    # item 1 ("Grains and Fats results").
    bars = focus_areas.bars(assessment["components"], HEI2020_BY_ID)
    goal = user.get("focus_goal") or {}
    return {
        "has_assessment": True, "assessment_type": assessment["assessment_type"],
        "focus_area": ({**focus_areas.public(area_id), "goal": goal.get("goal"), "plan": goal.get("plan")}
                       if area_id else None),
        "strengths": [{**a, "direction": "strength"} for a in buckets["strengths"]],
        "room_to_grow": [{**a, "direction": "room_to_grow"} for a in buckets["room_to_grow"]],
        # Kept for the older client UI that reads `other_areas`; now it's
        # specifically the middle ground (neither strength nor room to grow).
        "other_areas": buckets["other"],
        "bars": bars,
        "needs_focus_selection": not area_id,
        "disclaimer": DISCLAIMER,
    }


@api.get("/domains/move")
async def domain_move(user: dict = Depends(current_user)):
    first, _ = study_week_window(7)
    start = study_day_start_utc_iso(first)
    acts = await db.activities.find({"user_id": user["id"], "created_at": {"$gte": start}}).to_list(200)
    weekly_minutes = sum(a.get("minutes", 0) for a in acts)
    return {
        "weekly_activity_minutes": weekly_minutes,
        "wearable_connected": user.get("wearable_connected", False),
        "reference_note": "Move reference values are still being finalized with the nutrition team.",
    }


@api.get("/domains/rest")
async def domain_rest(user: dict = Depends(current_user)):
    first, _ = study_week_window(7)
    start = study_day_start_utc_iso(first)
    sleeps = await db.sleeps.find({"user_id": user["id"], "created_at": {"$gte": start}}).to_list(50)
    has_data = len(sleeps) > 0
    avg = round(sum(s.get("hours", 0) for s in sleeps) / len(sleeps), 1) if sleeps else None
    confidence = "none" if not has_data else ("medium" if any(s.get("source") == "wearable" for s in sleeps) else "low")
    return {
        "avg_sleep_hours": avg, "confidence": confidence,
        "wearable_connected": user.get("wearable_connected", False),
        "reference_note": "Rest reference values are still being finalized with the nutrition team.",
    }


@api.get("/domains")
async def domains(user: dict = Depends(current_user)):
    return {"food": await domain_food(user), "move": await domain_move(user), "rest": await domain_rest(user)}


# ----------------------------------------------------------------------------
# My Path — the single, consistent trail/milestone avatar (per the 9/10/26
# deck: "Avatar's appearance never changes, only position on the path...
# Milestones labeled by specific behavior built, never a health outcome or
# prediction"). Replaces the old dual illustrative CARDIA-style trajectory
# entirely — that projection is explicitly retired.
# ----------------------------------------------------------------------------
async def _recall_status(user: dict) -> dict:
    finished = {f["assessment_type"]: asa24_schedule.finished_times(f) for f in await db.asa24_recall_finished.find(
        {"user_id": user["id"]}, {"_id": 0}).to_list(10)}
    imported = [a["assessment_type"] for a in await db.hei_assessments.find(
        {"user_id": user["id"]}, {"_id": 0, "assessment_type": 1}).to_list(20)]
    return asa24_schedule.recall_status(_study_start(user), study_today(), finished, imported)


async def _next_checkin_info(user: dict) -> dict:
    """The My Path / Future Me countdown, from the same recall schedule as
    the Today card. No guilt wording for missed windows."""
    st = await _recall_status(user)
    if st["state"] == "complete":
        return {"days_until": None, "message": "All your check-ins are done. Thank you!"}
    if st["state"] == "finished":
        return {"days_until": None, "label": st["label"],
                "message": "Thanks for finishing your food recall. Your results will appear after the study team reviews them."}
    days = st["days_until_open"]
    due = date_cls.fromisoformat(st["due_by"])
    left = st["recalls_needed"] - st["recalls_done"]
    if days == 0 and st["recalls_done"]:
        message = f"One more {st['label'].lower()} food recall, open until {due:%b} {due.day}."
    elif days == 0:
        message = f"Your {st['label'].lower()} food recalls are open until {due:%b} {due.day}. There are {left}."
    else:
        message = f"{days} days until your {st['label'].lower()} food recalls. Nothing to prepare."
    return {"days_until": days, "label": st["label"], "opens_on": st["opens_on"], "due_by": st["due_by"],
            "message": message}


# ----------------------------------------------------------------------------
# ASA24 recall card. Recalls happen on NCI's ASA24 site (no API), so the app
# only links out, records the participant's "I finished" tap so staff know
# when to download the Totals file, and tells them when new results are in.
# ----------------------------------------------------------------------------
# Two "I finished" taps this close together are one recall, not two.
RECALL_DOUBLE_TAP_SECONDS = 10 * 60


class RecallFinishedIn(BaseModel):
    assessment_type: Literal["baseline", "checkin_1", "checkin_2"]


async def _new_results(user: dict) -> bool:
    latest = await _latest_assessment(user["id"])
    if not latest:
        return False
    seen = user.get("asa24_results_seen_at")
    return not seen or (latest.get("created_at") or "") > seen


@api.get("/asa24/recall")
async def get_recall(user: dict = Depends(current_user)):
    # Assigns now if the batch was empty when they signed up.
    username = await _assign_asa24_account(user["id"])
    acct = await db.asa24_accounts.find_one({"username": username}) if username else None
    link = await db.asa24_links.find_one({"user_id": user["id"]}) if username else None
    password = None
    if acct and acct.get("password_encrypted"):
        try:
            password = tamus_client.decrypt_key(acct["password_encrypted"])
        except Exception:
            logger.error(f"Can't decrypt ASA24 password for {username} (encryption secret changed?)")
    return {
        # As staff typed it (e.g. LLHSTEST3); matching stays case-insensitive.
        "asa24_username": (link or {}).get("display_username") or username,
        "asa24_password": password,
        "link": ASA24_RESPONDENT_URL,
        "recall": await _recall_status(user),
        "new_results": await _new_results(user),
    }


@api.post("/asa24/recall/finished")
async def recall_finished(body: RecallFinishedIn, user: dict = Depends(current_user)):
    """One tap per recall: two per assessment point (a weekday and a
    weekend day). Taps after the second, or a second tap within a few
    minutes of the first, are ignored rather than counted."""
    st = await _recall_status(user)
    if st.get("assessment_type") != body.assessment_type or st["state"] not in ("open", "finished"):
        raise HTTPException(400, "That food recall isn't open right now.")
    key = {"user_id": user["id"], "assessment_type": body.assessment_type}
    times = asa24_schedule.finished_times(await db.asa24_recall_finished.find_one(key, {"_id": 0}) or {})
    now = now_utc()
    double_tap = times and (now - datetime.fromisoformat(times[-1])).total_seconds() < RECALL_DOUBLE_TAP_SECONDS
    if st["state"] == "open" and not double_tap:
        times.append(now.isoformat())
        await db.asa24_recall_finished.update_one(
            key, {"$set": {**key, "finished_at": times[0], "finished_times": times}}, upsert=True)
    return {"recall": await _recall_status(user)}


@api.post("/asa24/results/seen")
async def recall_results_seen(user: dict = Depends(current_user)):
    await db.users.update_one({"id": user["id"]}, {"$set": {"asa24_results_seen_at": now_utc().isoformat()}})
    return {"ok": True}


@api.get("/path")
async def get_path(user: dict = Depends(current_user)):
    # The 8-week path, built from this participant's program progress, focus
    # area, meals and check-ins (personal_path.py). Every milestone is a skill.
    uid = user["id"]
    proj = {"_id": 0}
    meals = await db.meals.find({"user_id": uid}, proj).to_list(1000)
    assessments = await db.hei_assessments.find({"user_id": uid}, proj).sort("recorded_at", 1).to_list(20)
    return personal_path.build_personal_path(
        user, meals, await _program(user), assessments, next_checkin=await _next_checkin_info(user))


# ----------------------------------------------------------------------------
# Safety check-in
# ----------------------------------------------------------------------------
@api.get("/safety/checkin")
async def get_checkin(user: dict = Depends(current_user)):
    ci = await db.safety_checkins.find_one({"user_id": user["id"], "acknowledged": False})
    if not ci:
        return {"checkin": None}
    return {"checkin": {k: v for k, v in ci.items() if k != "_id"}}


@api.post("/safety/checkin/{checkin_id}/ack")
async def ack_checkin(checkin_id: str, user: dict = Depends(current_user)):
    await db.safety_checkins.update_one({"id": checkin_id, "user_id": user["id"]}, {"$set": {"acknowledged": True}})
    return {"ok": True}


# ----------------------------------------------------------------------------
# F1 — Curriculum + Youth Ambassador peer-modeling videos
#
# Per the review notes: the baseline 3-part curriculum and the Youth
# Ambassador modeling component are separate but should be presented
# together — the peer segment goes "underneath" each baseline video so
# participants see the concept translated into a realistic peer behavior.
# ----------------------------------------------------------------------------
CURRICULUM = [
    {"id": "c1", "title": "Planning for Healthy Eating", "duration": "6 min",
     "summary": "How planning around your schedule, budget, and pantry makes healthy eating realistic.",
     "video_url": "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4",
     "points": program.POINTS["watch"], "key_points": ["Plan meals around your real week", "Keep flexible staples on hand", "Budget-friendly swaps"],
     "peer_video": {
         "ambassador_name": "Kirby", "title": "How Kirby plans on a college meal plan",
         "video_url": "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4",
         "transition_line": "Now that you've learned about planning balanced meals while using a college meal plan, see how Kirby does it!",
     }},
    {"id": "c2", "title": "Applying Nutrition Information", "duration": "7 min",
     "summary": "Reading labels and menus with confidence, focusing on process not calories.",
     "video_url": "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ElephantsDream.mp4",
     "points": program.POINTS["watch"], "key_points": ["Scan for fiber and sodium", "Compare, don't obsess", "Menus: build a balanced order"],
     "peer_video": {
         "ambassador_name": "Maya", "title": "How Maya reads a fast-food menu",
         "video_url": "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ElephantsDream.mp4",
         "transition_line": "Now that you've learned about reading labels and menus, see how Maya orders at a fast-food counter!",
     }},
    {"id": "c3", "title": "Assembling Balanced Meals", "duration": "5 min",
     "summary": "A flexible balanced-plate approach — vegetables, whole grains, and protein.",
     "video_url": "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4",
     "points": program.POINTS["watch"], "key_points": ["Half the plate vegetables", "A quarter whole grains", "A quarter protein"],
     "peer_video": {
         "ambassador_name": "Deshawn", "title": "How Deshawn builds a plate with no stove",
         "video_url": "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4",
         "transition_line": "Now that you've learned about assembling balanced meals, see how Deshawn does it with a dorm-room setup!",
     }},
]


@api.get("/curriculum")
async def get_curriculum(user: dict = Depends(current_user)):
    done = await db.completions.find({"user_id": user["id"], "kind": "video"}).to_list(100)
    done_ids = {d["ref"] for d in done}
    return [{**c, "completed": c["id"] in done_ids} for c in CURRICULUM]


@api.post("/curriculum/{video_id}/complete")
async def complete_video(video_id: str, user: dict = Depends(current_user)):
    video = next((c for c in CURRICULUM if c["id"] == video_id), None)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    if await db.completions.find_one({"user_id": user["id"], "kind": "video", "ref": video_id}):
        return {"already": True, "points_awarded": 0}
    await db.completions.insert_one(
        {"id": new_id(), "user_id": user["id"], "kind": "video", "ref": video_id, "created_at": now_utc().isoformat()}
    )
    await award_points(user["id"], video["points"], badge="First Lesson")
    return {"already": False, "points_awarded": video["points"]}


# ----------------------------------------------------------------------------
# The 8-week program (program.py): Learn shows one unit per week, released
# week by week; Today and My Path read the same structure.
# ----------------------------------------------------------------------------
async def _program(user: dict) -> dict:
    uid = user["id"]
    steps = await db.program_steps.find({"user_id": uid}, {"_id": 0, "week": 1, "step": 1}).to_list(200)
    videos = await db.completions.find({"user_id": uid, "kind": "video"}).to_list(100)
    games = await db.completions.find({"user_id": uid, "kind": "game"}).to_list(100)
    set_at = user.get("focus_areas_set_at") if user.get("focus_area") else None
    return program.build(
        _study_start(user), study_today(),
        done_steps={f"{s['week']}:{s['step']}" for s in steps},
        videos_done={v["ref"] for v in videos}, games_done={g["ref"] for g in games},
        focus_set_on=date_cls.fromisoformat(study_day_key(set_at)) if set_at else None,
        videos={c["id"]: c for c in CURRICULUM},
    )


def menu_challenge_enabled() -> bool:
    """``MENU_CHALLENGE_ENABLED`` controls whether the old Week 2
    Nutrition / Menu Challenge (game id g2) is visible. Nutrition team
    flagged it on 2026-10-29 as having inaccurate numbers and being the
    wrong Week 2 activity — the Week 2 workflow (PR #39/#40) is the
    correct activity. Default off for everyone, including pilots. The
    old code stays behind the flag so the team can inspect / rework it;
    nothing routes to it when the flag is off."""
    return (os.environ.get("MENU_CHALLENGE_ENABLED") or "").strip().lower() in {"1", "true", "yes", "on"}


def _apply_menu_challenge_override(prog: dict, *, week2_enabled_for_user: bool) -> dict:
    """Replace the Week 2 practice step on the fly when the old menu
    challenge is disabled. Two outcomes:
      (a) ``week2_enabled_for_user`` → point practice at the Week 2
          workflow (/week/overview_video?week=2). The Today card still
          renders the WeekCard for Week 2 users, but the Learn screen's
          program-step view also needs this override.
      (b) otherwise → mark the practice step as "Week 2 activities are
          coming soon" (route null, not ready).
    """
    if menu_challenge_enabled():
        return prog
    for unit in prog.get("units", []):
        if unit.get("week") != 2:
            continue
        for step in unit.get("steps", []):
            if step.get("key") != "practice":
                continue
            if week2_enabled_for_user:
                step["title"] = "Week 2 activities (new workflow)"
                step["route"] = "/week/overview_video"
                step["params"] = {"week": "2"}
                step["ready"] = True
            else:
                step["title"] = "Week 2 activities are coming soon"
                step["route"] = None
                step["params"] = None
                step["ready"] = False
    return prog


@api.get("/program")
async def get_program(user: dict = Depends(current_user)):
    p = await _program(user)
    w2_enabled = weekly_workflow.is_enabled_for(
        2, is_test=is_test_account(user),
        study_start=_study_start(user), today=study_today(),
    )
    p = _apply_menu_challenge_override(p, week2_enabled_for_user=w2_enabled)
    return {**p, "next_step": program.next_step(p)}


class ProgramStepIn(BaseModel):
    text: Optional[str] = Field(default=None, max_length=1000)


@api.post("/program/{week}/{step}/done")
async def complete_program_step(week: int, step: str, body: ProgramStepIn, user: dict = Depends(current_user)):
    if not program.can_mark(week, step):
        raise HTTPException(404, "That step can't be marked done.")
    if week > program.current_week(_study_start(user), study_today()):
        raise HTTPException(400, f"Week {week} isn't open yet.")
    text = (body.text or "").strip()
    if step == "reflect" and not text:
        raise HTTPException(422, "Write a sentence or two to reflect.")
    key = {"user_id": user["id"], "week": week, "step": step}
    if await db.program_steps.find_one(key):
        await db.program_steps.update_one(key, {"$set": {"text": text or None, "updated_at": now_utc().isoformat()}})
        return {"already": True, "points_awarded": 0, "program": await get_program(user)}
    await db.program_steps.insert_one({**key, "text": text or None, "created_at": now_utc().isoformat()})
    awarded = program.POINTS[step]
    await award_points(user["id"], awarded)
    return {"already": False, "points_awarded": awarded, "program": await get_program(user)}


# ----------------------------------------------------------------------------
# Weekly workflow — new per-week connected journey for Weeks 1 and 2.
#
# Content lives in ``backend/content/weeks/weekN.json``; the engine
# (``weekly_workflow.py``) is pure functions. Here we add the HTTP
# surface and the database IO. The ``WEEK{N}_WORKFLOW_MODE`` env flag
# (``off`` | ``test_only`` | ``on``) controls who sees the new flow;
# while a week's flag is off, the existing ``program.py`` card on
# Today keeps serving that week unchanged, so no pilot sees a
# half-finished experience.
# ----------------------------------------------------------------------------
class WeeklyWorkflowStepIn(BaseModel):
    responses: Optional[Dict[str, Any]] = None  # reflection sub-prompts, etc.
    note: Optional[str] = Field(default=None, max_length=2000)


async def _weekly_signals(user: dict, record: Optional[dict] = None) -> Dict[str, Any]:
    """External state the engine's auto-complete rules read: focus area
    and goal/plan from the user document; for Week 2, how many distinct
    scenarios the student has responded to. Looked up fresh so a student
    who sets their focus on the Eat tab (bypassing the workflow) still
    sees the ``focus_selection`` step auto-complete the next time they
    open Today. Open map, so new rules (ASA24 recall finished, meal
    logged on the plan occasion, …) can be added without changing this
    function's callers."""
    return {
        "focus_area": user.get("focus_area"),
        "focus_goal": user.get("focus_goal") or {},
        "completed_scenarios_count": week2_scenarios.completed_scenario_count(record or {}),
    }


async def _weekly_view(user: dict, week: int) -> Dict[str, Any]:
    content = weekly_workflow.load_week(week)
    record = await db.weekly_workflow.find_one(
        {"user_id": user["id"], "week": week}, {"_id": 0}
    ) or {}
    view = weekly_workflow.build_week_view(content, record, await _weekly_signals(user, record))
    view["mode"] = weekly_workflow.workflow_mode(week)
    view["enabled"] = weekly_workflow.is_enabled_for(week, is_test=is_test_account(user), study_start=_study_start(user), today=study_today())
    return view


@api.get("/weekly-workflow")
async def get_weekly_workflow(user: dict = Depends(current_user)):
    """One payload with the per-week view for every supported week, so
    the client renders the right card without a second round trip. The
    ``enabled`` flag per week tells the client whether to show the new
    Week card or fall back to the existing program.py card."""
    out: Dict[str, Any] = {"weeks": []}
    for w in weekly_workflow.SUPPORTED_WEEKS:
        try:
            out["weeks"].append(await _weekly_view(user, w))
        except FileNotFoundError as e:
            logger.warning("Weekly workflow content missing: %s", e)
    return out


@api.get("/weekly-workflow/{week}/step/{step_id}")
async def get_weekly_step(week: int, step_id: str, user: dict = Depends(current_user)):
    """Full step body (prompts, options, video URL) for a step detail
    screen. Served separately from the week view so the Today card
    stays small."""
    if week not in weekly_workflow.SUPPORTED_WEEKS:
        raise HTTPException(404, f"Week {week} isn't served by the weekly workflow.")
    if not weekly_workflow.is_enabled_for(week, is_test=is_test_account(user), study_start=_study_start(user), today=study_today()):
        raise HTTPException(403, f"Week {week} workflow is not enabled for this account.")
    step_raw = weekly_workflow.get_step_content(week, step_id)
    if step_raw is None:
        raise HTTPException(404, f"Step {step_id!r} isn't defined in week {week}.")
    view = await _weekly_view(user, week)
    status = next((s for s in view["steps"] if s["id"] == step_id), None)
    focus_area = user.get("focus_area") if user.get("focus_area") in focus_areas.BY_ID else None
    focus_label = focus_areas.BY_ID[focus_area]["label"] if focus_area else None
    # Add the Week 2 scenarios' chosen settings to the carried map so
    # the ambassador video resolver can pick a scenario-matched clip.
    extended_carried = dict(view["carried"])
    if week == WEEK2:
        rec = await _week2_record(user)
        extended_carried["scenario_settings_chosen"] = (
            _record_scenarios_state(rec).get("settings_chosen") or []
        )
    content = weekly_workflow.resolve_step(
        week, step_id,
        focus_area=focus_area, focus_area_label=focus_label,
        carried=extended_carried,
    )
    return {"week": week, "step_id": step_id, "content": content, "status": status, "carried": extended_carried}


@api.post("/weekly-workflow/{week}/step/{step_id}/complete")
async def complete_weekly_step(
    week: int,
    step_id: str,
    body: WeeklyWorkflowStepIn,
    user: dict = Depends(current_user),
):
    """Mark a step done. Idempotent — repeat calls return
    ``{"already": true}`` and award no further points. Steps with a
    ``completion_rule`` (``focus_selection``, ``goal_and_plan``) are
    auto-completed from the user document and MUST NOT be POSTed here;
    the engine will overlay their status at read time."""
    if week not in weekly_workflow.SUPPORTED_WEEKS:
        raise HTTPException(404, f"Week {week} isn't served by the weekly workflow.")
    if not weekly_workflow.is_enabled_for(week, is_test=is_test_account(user), study_start=_study_start(user), today=study_today()):
        raise HTTPException(403, f"Week {week} workflow is not enabled for this account.")

    step = weekly_workflow.get_step_content(week, step_id)
    if step is None:
        raise HTTPException(404, f"Step {step_id!r} isn't defined in week {week}.")
    if step.get("completion_rule"):
        raise HTTPException(
            400,
            "This step completes itself from your profile; nothing to post.",
        )

    payload = body.model_dump(exclude_none=True) if body else {}
    ok, reason = weekly_workflow.validate_step_response(week, step_id, payload)
    if not ok:
        raise HTTPException(422, reason or "Invalid step response.")

    key = {"user_id": user["id"], "week": week}
    now_iso = now_utc().isoformat()
    existing = await db.weekly_workflow.find_one(key)
    already = bool((existing or {}).get("step_statuses", {}).get(step_id, {}).get("status") == "done")

    status_doc: Dict[str, Any] = {
        "status": "done",
        "completed_at": now_iso,
        "responses": payload.get("responses"),
        "note": payload.get("note"),
    }
    update = {
        "$set": {
            f"step_statuses.{step_id}": status_doc,
            "updated_at": now_iso,
        },
        "$setOnInsert": {**key, "created_at": now_iso},
    }
    await db.weekly_workflow.update_one(key, update, upsert=True)

    points_awarded = 0
    if not already:
        pts = weekly_workflow.step_points(week, step_id)
        if pts:
            await award_points(user["id"], pts)
            points_awarded = pts

    return {
        "already": already,
        "points_awarded": points_awarded,
        "week": await _weekly_view(user, week),
    }


# ----------------------------------------------------------------------------
# Week 2 — scenario endpoints
#
# The "scenarios" step is a scenario_set type: the student picks three of
# five settings, each setting presents a scenario, each scenario records
# one choice + an optional follow-up. The scenarios step is marked done
# the moment three distinct responses are saved (the engine's
# ``three_scenarios_completed`` auto-complete rule), after which "Try
# another" responses no longer award points.
#
# Cafeteria + grocery scenarios draw options from the SAMPLE content
# files (week2_dining_menu.json, week2_grocery_products.json); feedback
# is rule-based (week2_scenarios.build_dining_feedback /
# build_grocery_feedback). Scripted scenarios (restaurant / someone-else
# / home) read options + draft feedback from week2.json directly.
# ----------------------------------------------------------------------------
WEEK2 = 2
_SCENARIOS_STEP_ID = "scenarios"


def _week2_scenarios_meta() -> Dict[str, Any]:
    """The scenarios step body from week2.json. Centralised so the
    endpoints below never re-walk the content file."""
    content = weekly_workflow.get_step_content(WEEK2, _SCENARIOS_STEP_ID) or {}
    return content


def _week2_scenario_defs() -> Dict[str, Any]:
    return (_week2_scenarios_meta().get("scenario_defs") or {})


def _week2_period_from_study_clock() -> str:
    """Dining meal period from the study clock. Simple cut-offs so the
    scenario reflects "where you are now" without needing campus-specific
    serving windows. Falls back to lunch outside the three windows."""
    hour = study_today_hour()
    if 4 <= hour < 10:
        return "breakfast"
    if 10 <= hour < 15:
        return "lunch"
    if 15 <= hour < 22:
        return "dinner"
    return "lunch"


def study_today_hour() -> int:
    """Current hour in the study timezone. Pulled through study_time so
    tests can monkeypatch the clock."""
    from datetime import datetime
    return datetime.now(tz=STUDY_TZ).hour


def _record_scenarios_state(record: Optional[dict]) -> Dict[str, Any]:
    """Normalise the scenarios step state out of a weekly_workflow
    record. The step state carries ``settings_chosen`` (3 setting ids)
    and ``responses`` (keyed by setting id)."""
    step = (record or {}).get("step_statuses", {}).get(_SCENARIOS_STEP_ID) or {}
    return {
        "settings_chosen": list(step.get("settings_chosen") or []),
        "responses": dict(step.get("responses") or {}),
    }


class SettingsIn(BaseModel):
    settings: List[str] = Field(min_length=3, max_length=3)


class ScenarioResponseIn(BaseModel):
    choice_id: str = Field(min_length=1, max_length=200)
    follow_up: Optional[Dict[str, Any]] = None
    shown_option_ids: List[str] = Field(default_factory=list, max_length=10)
    # The nutrient values that were shown to the student at pick time.
    # Captured so the research export can report what the student saw,
    # even if the content file is updated after the fact.
    shown_option_payload: Optional[List[Dict[str, Any]]] = None


def _ensure_week2_enabled(user: dict) -> None:
    if not weekly_workflow.is_enabled_for(WEEK2, is_test=is_test_account(user), study_start=_study_start(user), today=study_today()):
        raise HTTPException(403, "Week 2 workflow is not enabled for this account.")


async def _week2_record(user: dict) -> dict:
    rec = await db.weekly_workflow.find_one(
        {"user_id": user["id"], "week": WEEK2}, {"_id": 0}
    )
    return rec or {}


def _build_scenario_payload(
    setting_id: str,
    *,
    user: dict,
    chosen_settings: List[str],
) -> Dict[str, Any]:
    """Assemble the scenario body for a chosen setting. Returns the
    options + prompt + follow-up config; the frontend renders it."""
    defs = _week2_scenario_defs()
    sdef = defs.get(setting_id)
    if sdef is None:
        raise HTTPException(404, f"Unknown setting {setting_id!r}.")
    source = sdef.get("source")
    focus_area = user.get("focus_area") if user.get("focus_area") in focus_areas.BY_ID else None
    base: Dict[str, Any] = {
        "setting": setting_id,
        "label": sdef.get("label"),
        "source": source,
        "follow_up": sdef.get("follow_up"),
    }

    if source == "scripted":
        base["prompt"] = sdef.get("prompt")
        base["choices"] = sdef.get("choices") or []
        return base

    if source == "dining_file":
        menu = week2_scenarios.load_dining_menu()
        direction = sdef.get("nutrient_direction") or {}
        picked = week2_scenarios.pick_dining_scenario(
            menu, direction,
            period_preference=_week2_period_from_study_clock(),
        )
        if picked is None:
            base["prompt"] = "The dining menu doesn't have a good comparison right now."
            base["coming_soon"] = True
            base["choices"] = []
            return base
        prompt = (sdef.get("prompt_template") or "").format(
            meal_period=picked["meal_period"],
            dining_hall=picked["hall_label"] or picked["hall_id"],
        )
        base.update({
            "prompt": prompt,
            "meal_period": picked["meal_period"],
            "dining_hall": picked["hall_label"],
            "highlighted_nutrients": sdef.get("highlighted_nutrients") or [],
            "nutrient_display_labels": sdef.get("nutrient_display_labels") or {},
            "choices": picked["items"],
        })
        return base

    if source == "grocery_file":
        products = week2_scenarios.load_grocery_products()
        is_test = is_test_account(user)
        category_id = (sdef.get("category_by_focus_area") or {}).get(focus_area or "") \
            or sdef.get("default_category")
        category = next(
            (c for c in products.get("categories", []) if c.get("id") == category_id),
            None,
        )
        if category is None or (not is_test and not week2_scenarios.is_category_served_to_real_users(category)):
            category = week2_scenarios.pick_grocery_category(
                products, focus_area,
                default_category=sdef.get("default_category") or "canned_soups",
                is_test=is_test,
            )
        if category is None:
            base["prompt"] = "Nothing to compare in this category yet."
            base["coming_soon"] = True
            base["choices"] = []
            return base
        prompt = (sdef.get("prompt_template") or "").format(
            category_label_lower=category.get("label_lower") or category.get("label"),
        )
        base.update({
            "prompt": prompt,
            "category_id": category.get("id"),
            "category_label": category.get("label"),
            "highlighted_nutrients": sdef.get("highlighted_nutrients") or [],
            "nutrient_display_labels": sdef.get("nutrient_display_labels") or {},
            "choices": category.get("products") or [],
        })
        return base

    raise HTTPException(500, f"Unknown scenario source {source!r} for {setting_id!r}.")


def _available_week2_settings(meta: Dict[str, Any], *, is_test: bool) -> List[Dict[str, Any]]:
    """Settings the student may pick from. Mirrors the grocery
    ``is_category_served_to_real_users`` gate — if the dining menu is
    still sample-only, the cafeteria setting is hidden from real
    participants (no made-up nutrient card ever reaches the cohort).
    Test and demo accounts still see it so the lab can rehearse the
    full five-of-five flow."""
    settings = list(meta.get("available_settings") or [])
    if is_test:
        return settings
    try:
        menu = week2_scenarios.load_dining_menu()
    except FileNotFoundError:
        menu = {}
    if week2_scenarios.is_dining_served_to_real_users(menu):
        return settings
    return [s for s in settings if s.get("id") != "cafeteria"]


@api.get("/weekly-workflow/2/scenarios/config")
async def week2_scenarios_config(user: dict = Depends(current_user)):
    """What the client needs to render the settings picker + progress:
    the available settings (five for test accounts; cafeteria is hidden
    for real participants while the dining menu is still SAMPLE), which
    three the student picked (if any), which they've responded to, and
    whether the scenarios step is already complete."""
    _ensure_week2_enabled(user)
    meta = _week2_scenarios_meta()
    rec = await _week2_record(user)
    state = _record_scenarios_state(rec)
    responded = list(state["responses"].keys())
    chosen = state["settings_chosen"]
    done_count = week2_scenarios.completed_scenario_count(rec)
    return {
        "available_settings": _available_week2_settings(meta, is_test=is_test_account(user)),
        "settings_question": meta.get("settings_question"),
        "required_scenarios": meta.get("required_scenarios") or 3,
        "settings_chosen": chosen,
        "responded_settings": responded,
        "completed_count": done_count,
        "step_done": done_count >= (meta.get("required_scenarios") or 3),
        "completion_message": meta.get("completion_message"),
        "cta_next_label": meta.get("cta_next_label"),
        "try_another_label": meta.get("try_another_label"),
    }


@api.post("/weekly-workflow/2/scenarios/settings")
async def week2_choose_settings(body: SettingsIn, user: dict = Depends(current_user)):
    """Save the three settings the student will practice in. The engine
    then presents one scenario per chosen setting. Must be exactly three
    distinct settings from the available list; the request is rejected
    otherwise. Re-posting replaces the earlier choice ONLY if no
    scenario has been responded to yet — once responses exist, the three
    settings are locked in (the alternative would make 'Try another'
    ambiguous)."""
    _ensure_week2_enabled(user)
    meta = _week2_scenarios_meta()
    # Mirror the gated list the config endpoint serves — reject cafeteria
    # for real participants when the dining menu is still SAMPLE. A
    # hand-crafted request can't bypass the UI's filtered picker.
    valid_ids = {s["id"] for s in _available_week2_settings(meta, is_test=is_test_account(user))}
    if len(set(body.settings)) != 3 or not set(body.settings).issubset(valid_ids):
        raise HTTPException(422, "Pick exactly three distinct settings.")

    rec = await _week2_record(user)
    state = _record_scenarios_state(rec)
    if state["responses"] and set(state["settings_chosen"]) != set(body.settings):
        raise HTTPException(
            409,
            "You've already started these scenarios; try another setting instead of swapping.",
        )

    now_iso = now_utc().isoformat()
    key = {"user_id": user["id"], "week": WEEK2}
    await db.weekly_workflow.update_one(
        key,
        {
            "$set": {
                f"step_statuses.{_SCENARIOS_STEP_ID}.settings_chosen": body.settings,
                f"step_statuses.{_SCENARIOS_STEP_ID}.settings_chosen_at": now_iso,
                "updated_at": now_iso,
            },
            "$setOnInsert": {**key, "created_at": now_iso},
        },
        upsert=True,
    )
    return await week2_scenarios_config(user=user)


@api.get("/weekly-workflow/2/scenario/{setting}")
async def week2_scenario_body(setting: str, user: dict = Depends(current_user)):
    """Return the scenario body for a single setting. The content file
    + loader decide what to serve (dining options / grocery products /
    scripted choices)."""
    _ensure_week2_enabled(user)
    # Defense in depth: a real participant can't hand-craft a GET for
    # the cafeteria scenario while the dining menu is still SAMPLE.
    meta = _week2_scenarios_meta()
    allowed = {s["id"] for s in _available_week2_settings(meta, is_test=is_test_account(user))}
    if setting not in allowed:
        raise HTTPException(404, f"Scenario {setting!r} isn't available for this account.")
    rec = await _week2_record(user)
    state = _record_scenarios_state(rec)
    chosen = state["settings_chosen"]
    responded = state["responses"].get(setting)
    body = _build_scenario_payload(setting, user=user, chosen_settings=chosen)
    body["already_responded"] = bool(responded)
    body["previous_response"] = responded
    body["is_in_chosen_set"] = setting in chosen
    return body


@api.post("/weekly-workflow/2/scenario/{setting}/respond")
async def week2_scenario_respond(
    setting: str,
    body: ScenarioResponseIn,
    user: dict = Depends(current_user),
):
    """Record the student's chosen option, generate the feedback, and
    (if it's one of the first three distinct responses) award the
    scenarios step's points once. "Try another" responses after the
    first three save the response and feedback but award no additional
    points — the user's spec is explicit about this."""
    _ensure_week2_enabled(user)
    meta = _week2_scenarios_meta()
    defs = _week2_scenario_defs()
    sdef = defs.get(setting)
    if sdef is None:
        raise HTTPException(404, f"Unknown setting {setting!r}.")

    rec = await _week2_record(user)
    state = _record_scenarios_state(rec)
    required = int(meta.get("required_scenarios") or 3)
    # Rebuild the scenario body so we can validate the choice id against
    # the actual options and generate feedback from the real values.
    payload = _build_scenario_payload(setting, user=user, chosen_settings=state["settings_chosen"])
    choices = payload.get("choices") or []
    chosen = next((c for c in choices if c.get("id") == body.choice_id), None)
    if chosen is None:
        raise HTTPException(422, f"That option isn't one of the available choices for {setting!r}.")

    source = sdef.get("source")
    if source == "scripted":
        feedback = {
            "chosen_id": chosen["id"],
            "chosen_name": chosen.get("text"),
            "body": chosen.get("feedback"),
            "draft": bool(chosen.get("draft_feedback")),
        }
    elif source == "dining_file":
        feedback = week2_scenarios.build_dining_feedback(
            choices, body.choice_id,
            nutrient_direction=sdef.get("nutrient_direction") or {},
            practical_suggestions=sdef.get("practical_suggestions"),
        )
    elif source == "grocery_file":
        feedback = week2_scenarios.build_grocery_feedback(
            choices, body.choice_id,
            nutrient_direction=sdef.get("nutrient_direction") or {},
            practical_suggestions=sdef.get("practical_suggestions"),
        )
    else:
        raise HTTPException(500, f"Unknown scenario source {source!r}.")

    now_iso = now_utc().isoformat()
    key = {"user_id": user["id"], "week": WEEK2}
    is_already_responded = setting in state["responses"]
    is_within_required = (
        is_already_responded
        or len([k for k in state["responses"].keys()]) < required
    )

    response_doc = {
        "chosen_id": body.choice_id,
        "chosen_name": feedback.get("chosen_name") or chosen.get("name") or chosen.get("text"),
        "feedback_body": feedback.get("body"),
        "follow_up": body.follow_up,
        "shown_option_ids": body.shown_option_ids or [c.get("id") for c in choices],
        "shown_option_payload": body.shown_option_payload,
        "updated_at": now_iso,
        "within_required": is_within_required,
    }
    await db.weekly_workflow.update_one(
        key,
        {
            "$set": {
                f"step_statuses.{_SCENARIOS_STEP_ID}.responses.{setting}": response_doc,
                "updated_at": now_iso,
            },
            "$setOnInsert": {**key, "created_at": now_iso},
        },
        upsert=True,
    )

    # Award points once per student when the required set is first met.
    # Re-posts and "Try another" responses never add points, matching the
    # user's spec ("Points are awarded once per step per student. 'Try
    # another' scenarios beyond the first three earn no extra points.").
    points_awarded = 0
    scenarios_step = (await _week2_record(user)).get("step_statuses", {}).get(_SCENARIOS_STEP_ID) or {}
    is_now_done = week2_scenarios.scenarios_completed(
        {"step_statuses": {_SCENARIOS_STEP_ID: scenarios_step}},
        required=required,
    )
    was_marked_done = scenarios_step.get("status") == "done"
    if is_now_done and not was_marked_done:
        pts = weekly_workflow.step_points(WEEK2, _SCENARIOS_STEP_ID)
        if pts:
            await award_points(user["id"], pts)
            points_awarded = pts
        await db.weekly_workflow.update_one(
            key,
            {"$set": {
                f"step_statuses.{_SCENARIOS_STEP_ID}.status": "done",
                f"step_statuses.{_SCENARIOS_STEP_ID}.completed_at": now_iso,
            }},
        )

    return {
        "feedback": feedback,
        "points_awarded": points_awarded,
        "step_done": is_now_done,
        "config": await week2_scenarios_config(user=user),
    }


# ----------------------------------------------------------------------------
# Week 2 — planning endpoints
#
# "Planning Where You'll Use It" (spec §5): the student picks a
# situation + action + barrier + coping + reminder + plan-management
# choice (keep-and-add / replace / keep-last-week-only). Those answers
# become one or more Plan records in ``db.plans``. The Today "This
# Week" card lists every active plan with an Edit button; replaced
# plans never fire reminders (reminders ship in Phase 3).
# ----------------------------------------------------------------------------
_PLANNING_STEP_ID = "planning"
_AMBASSADOR_STEP_ID = "ambassador_video"


def _planning_content() -> Dict[str, Any]:
    return weekly_workflow.get_step_content(WEEK2, _PLANNING_STEP_ID) or {}


def _ambassador_content() -> Dict[str, Any]:
    return weekly_workflow.get_step_content(WEEK2, _AMBASSADOR_STEP_ID) or {}


def _settings_lookup() -> Dict[str, str]:
    return {s["id"]: s["label"] for s in week2_planning.available_settings({"steps": {"planning": _planning_content()}})}


def _occasions_lookup() -> Dict[str, Dict[str, Any]]:
    return {o["id"]: o for o in week2_planning.available_occasions({"steps": {"planning": _planning_content()}})}


async def _materialize_week1_plan_if_needed(user: dict) -> Optional[dict]:
    """Lazily seed a Week 1 plan row for a user who has focus_area +
    focus_goal but no row in ``db.plans``. The pilot migration (PR #38)
    writes weekly_workflow records but not plan records, so Phase 2
    needs to backfill the first time it looks."""
    pid = f"{user['id']}:w1"
    existing = await db.plans.find_one({"id": pid, "user_id": user["id"]}, {"_id": 0})
    if existing:
        return existing
    w1_record = await db.weekly_workflow.find_one(
        {"user_id": user["id"], "week": 1}, {"_id": 0},
    ) or {}
    reflection_responses = ((w1_record.get("step_statuses") or {}).get("reflection") or {}).get("responses") or {}
    plan = week2_planning.week1_plan_from_user(user, week1_reflection_responses=reflection_responses)
    if plan is None:
        return None
    plan["id"] = pid
    now_iso = now_utc().isoformat()
    plan["created_at"] = plan["updated_at"] = now_iso
    await db.plans.insert_one(dict(plan))
    return plan


async def _plans_for_user(user: dict, *, statuses: Optional[tuple] = None) -> List[dict]:
    query: Dict[str, Any] = {"user_id": user["id"]}
    if statuses:
        query["status"] = {"$in": list(statuses)}
    rows = await db.plans.find(query, {"_id": 0}).to_list(100)
    return rows


def _normalise_setting(setting_id: Optional[str]) -> Optional[str]:
    """The scenario-step setting ids and the planning-step setting ids
    differ slightly (``cafeteria`` vs ``dining_hall``). This maps the
    planning-step ids into the single canonical set we store on plan
    records."""
    if not setting_id:
        return None
    aliases = {
        "cafeteria": "dining_hall",
        "restaurant": "restaurant_takeout",
        "grocery": "grocery_convenience",
        "someone_else": "someone_else_prepares",
        "home": "at_home",
    }
    return aliases.get(setting_id, setting_id)


@api.get("/weekly-workflow/2/planning/config")
async def week2_planning_config(user: dict = Depends(current_user)):
    """Everything the planning step UI needs: the student's Week 1 plan
    (materialized on demand), the full set of pickers (settings,
    occasions, next-7-days, barriers, plan-management choices),
    exact-wording prompt copy, and the completion-summary templates.
    Clients never see the raw actions_by_focus_and_setting dict — they
    fetch the matched list from ``/planning/actions`` once p1 is
    answered."""
    _ensure_week2_enabled(user)
    content = {"steps": {"planning": _planning_content()}}
    pl = _planning_content()
    settings = week2_planning.available_settings(content)
    occasions = week2_planning.available_occasions(content)
    barriers = week2_planning.available_barriers(content)
    mgmt = week2_planning.plan_management_options(content)
    week1_plan = await _materialize_week1_plan_if_needed(user)
    return {
        "intro": pl.get("intro"),
        "settings": settings,
        "occasions": occasions,
        "days": week2_planning.next_seven_study_days(study_today()),
        "barriers": barriers,
        "plan_management_options": mgmt,
        "prompts": pl.get("prompts") or {},
        "completion_summary_template": pl.get("completion_summary_template"),
        "completion_summary_keep_only_template": pl.get("completion_summary_keep_only_template"),
        "week1_plan": (
            week2_planning.plan_card_for_today(
                week1_plan,
                settings_lookup=_settings_lookup(),
                occasions_lookup=_occasions_lookup(),
            ) if week1_plan else None
        ),
    }


@api.get("/weekly-workflow/2/planning/actions")
async def week2_planning_actions(
    focus_area: Optional[str] = None,
    setting: Optional[str] = None,
    user: dict = Depends(current_user),
):
    """3-4 preset actions matched to the student's focus + setting. The
    setting id is normalised (so a scenario-step ``cafeteria`` id maps
    to the planning ``dining_hall`` list), and the student's own focus
    overrides any override passed by the UI if one isn't supplied."""
    _ensure_week2_enabled(user)
    focus = focus_area or (user.get("focus_area") if user.get("focus_area") in focus_areas.BY_ID else None)
    norm = _normalise_setting(setting)
    content = {"steps": {"planning": _planning_content()}}
    return {
        "focus_area": focus,
        "setting": norm,
        "actions": week2_planning.actions_for(content, focus, norm),
    }


@api.get("/weekly-workflow/2/planning/coping")
async def week2_planning_coping(
    barrier: Optional[str] = None,
    user: dict = Depends(current_user),
):
    _ensure_week2_enabled(user)
    content = {"steps": {"planning": _planning_content()}}
    return {
        "barrier": barrier,
        "coping_options": week2_planning.copings_for(content, barrier),
    }


class PlanningSubmitIn(BaseModel):
    situation: Dict[str, Any]        # {setting, day, occasion, custom_setting_text?}
    action: Dict[str, Any]           # {text, source: "preset"|"custom", preset_index?}
    barrier: Dict[str, Any]          # {id, label, custom_text?}
    coping: Dict[str, Any]           # {text, source: "preset"|"custom"}
    reminder: Dict[str, Any]         # {time: "HH:MM"}
    plan_management: str             # "keep_and_add" | "replace" | "keep_week1_only"
    edit_plan_id: Optional[str] = None


@api.post("/weekly-workflow/2/planning/submit")
async def week2_planning_submit(
    body: PlanningSubmitIn,
    user: dict = Depends(current_user),
):
    """Finalize the planning step: materialize (or update) the Week 2
    plan record, apply the keep/add/replace choice, cancel reminders
    for anything that was replaced, mark the step done, and award
    points once. The response carries the completion summary so the
    client can render it immediately."""
    _ensure_week2_enabled(user)
    valid_choices = {o["id"] for o in week2_planning.plan_management_options(
        {"steps": {"planning": _planning_content()}}
    )}
    if body.plan_management not in valid_choices:
        raise HTTPException(422, f"Invalid plan_management choice: {body.plan_management!r}")

    # Build (or update) the Week 2 plan draft.
    situation = dict(body.situation or {})
    situation["setting"] = _normalise_setting(situation.get("setting"))
    now_iso = now_utc().isoformat()
    focus_area = user.get("focus_area") if user.get("focus_area") in focus_areas.BY_ID else None
    focus_goal = user.get("focus_goal") or {}

    plan_id = body.edit_plan_id or f"{user['id']}:w2:{new_id()}"
    draft_plan = week2_planning.make_plan(
        user_id=user["id"],
        source_week=2,
        focus_area=focus_area,
        focus_goal=focus_goal,
        situation=situation,
        action=body.action,
        barrier=body.barrier,
        coping=body.coping,
        reminder=body.reminder if body.plan_management != "keep_week1_only" else {},
        status=week2_planning.ACTIVE,
        plan_id=plan_id,
        now_iso=now_iso,
    )

    week1_plan = await _materialize_week1_plan_if_needed(user)
    outcome = week2_planning.apply_plan_management(
        choice=body.plan_management,
        week1_plan=week1_plan,
        draft_week2_plan=draft_plan,
        now_iso=now_iso,
    )

    for pid, plan in outcome["to_upsert"]:
        existing = await db.plans.find_one({"id": pid, "user_id": user["id"]})
        if existing:
            await db.plans.update_one(
                {"id": pid, "user_id": user["id"]},
                {"$set": {k: v for k, v in plan.items() if k not in ("id", "user_id", "created_at")}},
            )
        else:
            await db.plans.insert_one(dict(plan))

    # Cancel pending reminders for replaced plans. Reminders are a Phase
    # 3 feature; today the deletion is a safety guarantee that nothing
    # will fire from the replaced plan when the dispatcher lands.
    for pid in outcome["cancel_reminders_for"]:
        await db.plans_reminders.delete_many({"plan_id": pid, "user_id": user["id"]})

    # Record the reminder on db.plans_reminders for every active plan
    # that carries a time. Phase 3 dispatcher will read this collection;
    # for now the row is a durable write only.
    for pid, plan in outcome["to_upsert"]:
        reminder = (plan.get("reminder") or {})
        if plan.get("status") == week2_planning.ACTIVE and reminder.get("time"):
            await db.plans_reminders.update_one(
                {"plan_id": pid, "user_id": user["id"]},
                {"$set": {
                    "plan_id": pid, "user_id": user["id"], "time": reminder["time"],
                    "updated_at": now_iso, "status": "scheduled",
                }},
                upsert=True,
            )

    # Mark the planning step done + award points (once).
    key = {"user_id": user["id"], "week": WEEK2}
    existing_record = await db.weekly_workflow.find_one(key)
    already_done = bool(((existing_record or {}).get("step_statuses") or {}).get(_PLANNING_STEP_ID, {}).get("status") == "done")
    await db.weekly_workflow.update_one(
        key,
        {
            "$set": {
                f"step_statuses.{_PLANNING_STEP_ID}": {
                    "status": "done",
                    "completed_at": now_iso,
                    "plan_management": body.plan_management,
                },
                "updated_at": now_iso,
            },
            "$setOnInsert": {**key, "created_at": now_iso},
        },
        upsert=True,
    )
    points_awarded = 0
    if not already_done:
        pts = weekly_workflow.step_points(WEEK2, _PLANNING_STEP_ID)
        if pts:
            await award_points(user["id"], pts)
            points_awarded = pts

    # Build the completion summary from the student's answers.
    summary = week2_planning.build_completion_summary(
        {"steps": {"planning": _planning_content()}},
        plan_management=body.plan_management,
        situation=situation,
        action=body.action,
        barrier=body.barrier,
        coping=body.coping,
        reminder=body.reminder or {},
        settings_lookup=_settings_lookup(),
        occasions_lookup=_occasions_lookup(),
    )
    return {
        "summary": summary,
        "points_awarded": points_awarded,
        "plans": [
            week2_planning.plan_card_for_today(
                p, settings_lookup=_settings_lookup(), occasions_lookup=_occasions_lookup(),
            )
            for p in await _plans_for_user(user, statuses=(week2_planning.ACTIVE,))
        ],
    }


@api.get("/plans")
async def list_plans(user: dict = Depends(current_user)):
    """Active plans for the Today 'This Week' card. Replaced plans are
    kept in the collection (research export reads them), but excluded
    from the Today card. ``kept`` plans — the Week 2 answers a student
    saved but didn't activate — are returned too, with their status
    flag so the UI can show them in a subtle secondary row if we want
    to later; the current Today card only lists ``active`` ones."""
    rows = await _plans_for_user(user, statuses=(week2_planning.ACTIVE,))
    return {
        "plans": [
            week2_planning.plan_card_for_today(
                p, settings_lookup=_settings_lookup(), occasions_lookup=_occasions_lookup(),
            )
            for p in rows
        ]
    }


@api.get("/plans/{plan_id}")
async def get_plan(plan_id: str, user: dict = Depends(current_user)):
    """Full plan record for the Edit flow. Raw situation/action/
    barrier/coping/reminder dicts so the planning screen can repopulate
    every field."""
    plan = await db.plans.find_one({"id": plan_id, "user_id": user["id"]}, {"_id": 0})
    if plan is None:
        raise HTTPException(404, "Plan not found.")
    return plan


# ----------------------------------------------------------------------------
# F2 — Mini-games (Plan Your Week / Nutrition-Menu Challenge / Build a Meal)
#
# Scenario content lives in backend/content/games.json so the nutrition team
# can review copy without touching Python. New items are marked `draft: true`
# in that file; this module doesn't filter on that flag — the client can show
# a "draft" chip if desired, and admins can inspect it via /games.
# ----------------------------------------------------------------------------
_GAMES_JSON_PATH = ROOT_DIR / "content" / "games.json"


def _flatten_rounds_to_scenarios(game: dict) -> dict:
    """Expose rounds as a flat `scenarios` list too, so older clients that
    read `game.scenarios` keep working. New clients can walk `rounds`."""
    g = dict(game)
    if "rounds" in g and "scenarios" not in g:
        g["scenarios"] = [s for r in g["rounds"] for s in r.get("scenarios", [])]
    return g


def _load_games_content() -> dict:
    with _GAMES_JSON_PATH.open() as f:
        data = json.load(f)
    data["games"] = [_flatten_rounds_to_scenarios(g) for g in data.get("games", [])]
    return data


_GAMES_CONTENT = _load_games_content()
GAMES = _GAMES_CONTENT["games"]
DAILY_CHALLENGE_POOL = _GAMES_CONTENT.get("daily_challenges", {}).get("pool", [])
DAILY_CHALLENGE_POINTS = _GAMES_CONTENT.get("daily_challenges", {}).get("fixed_points", 5)


def _daily_challenge_for(day: date_cls) -> Optional[dict]:
    """Deterministic daily-challenge pick: same question for every
    participant on the same calendar day. Hashing the ISO date keeps the
    sequence pseudo-random across the week without using actual randomness."""
    if not DAILY_CHALLENGE_POOL:
        return None
    # SHA-free, dependency-free: a tiny stable hash of YYYY-MM-DD.
    h = 0
    for ch in day.isoformat():
        h = (h * 131 + ord(ch)) & 0xFFFFFFFF
    return DAILY_CHALLENGE_POOL[h % len(DAILY_CHALLENGE_POOL)]


# ----------------------------------------------------------------------------
# Build a Balanced Meal — drag-and-drop plate builder.
#
# Per the review notes, the standard-ingredients library should be
# organized by food category (protein, grain, vegetable, fruit, dairy,
# other) rather than one flat grid, so it stays usable as the library
# grows — DTL still needs to confirm exactly how large it can get.
#
# "Score This Plate" scoring rule — HONEST STATUS: the review notes flag
# this as an open item ("the underlying meaning of 'scoring' still needs to
# be defined... the nutrition team will need to determine what criteria
# constitute the score"). `score_plate` below is a PROVISIONAL placeholder
# (category-coverage across the new lightweight categories), not a
# finalized nutrition rubric.
#
# TODO(nutrition-team): Define real Score This Plate criteria.
# The current `score_plate()` implementation is intentionally kept as-is
# until the team provides the actual scoring rubric — we are NOT inventing
# nutrition criteria downstream of this file. Open questions for the team:
#   1. What qualifies as a "balanced" plate (coverage, portions, HEI-2020
#      components, something else)?
#   2. Should "salty_processed" or "added_sugars" subtract or just caution?
#   3. Should dairy and fruit each have independent requirements, or share
#      the current single "vegetable or fruit" slot?
# Once the rubric lands, replace score_plate() below (and update
# PlateScoreIn / /games/g3/score-plate accordingly) — not before.
# ----------------------------------------------------------------------------
# prep_minutes / cost / kitchen drive the practical filters on Build a
# Balanced Meal (study team feedback 2.2: time, budget, no-kitchen, equipment).
# They are rough estimates for a student cooking at home (cost "$" = under
# about $2 a serving), for the nutrition team to review.
INGREDIENT_LIBRARY = [
    # Protein
    {"id": "grilled_chicken", "name": "Grilled chicken breast", "category": "protein", "icon": "🍗", "log_categories": ["other_protein"], "prep_minutes": 20, "cost": "$$", "kitchen": "stove"},
    {"id": "baked_salmon", "name": "Baked salmon", "category": "protein", "icon": "🐟", "log_categories": ["beans_fish_nuts"], "prep_minutes": 20, "cost": "$$", "kitchen": "oven"},
    {"id": "black_beans", "name": "Black beans", "category": "protein", "icon": "🫘", "log_categories": ["beans_fish_nuts"], "prep_minutes": 5, "cost": "$", "kitchen": "none"},
    {"id": "almonds", "name": "Almonds", "category": "protein", "icon": "🥜", "log_categories": ["beans_fish_nuts"], "prep_minutes": 0, "cost": "$$", "kitchen": "none"},
    {"id": "fried_chicken", "name": "Fried chicken", "category": "protein", "icon": "🍗", "log_categories": ["salty_processed"], "prep_minutes": 25, "cost": "$$", "kitchen": "stove"},
    {"id": "bacon", "name": "Bacon", "category": "protein", "icon": "🥓", "log_categories": ["salty_processed"], "prep_minutes": 10, "cost": "$$", "kitchen": "stove"},
    # Grain
    {"id": "brown_rice", "name": "Brown rice", "category": "grain", "icon": "🍚", "log_categories": ["whole_grains"], "prep_minutes": 15, "cost": "$", "kitchen": "microwave"},
    {"id": "whole_wheat_tortilla", "name": "Whole-wheat tortilla", "category": "grain", "icon": "🫓", "log_categories": ["whole_grains"], "prep_minutes": 0, "cost": "$", "kitchen": "none"},
    {"id": "white_rice", "name": "White rice", "category": "grain", "icon": "🍚", "log_categories": ["refined_grains_starchy"], "prep_minutes": 15, "cost": "$", "kitchen": "microwave"},
    {"id": "dinner_roll", "name": "Buttered dinner roll", "category": "grain", "icon": "🥖", "log_categories": ["refined_grains_starchy"], "prep_minutes": 0, "cost": "$", "kitchen": "none"},
    # Vegetable
    {"id": "steamed_broccoli", "name": "Steamed broccoli", "category": "vegetable", "icon": "🥦", "log_categories": ["vegetables"], "prep_minutes": 5, "cost": "$", "kitchen": "microwave"},
    {"id": "side_salad", "name": "Side salad", "category": "vegetable", "icon": "🥗", "log_categories": ["vegetables"], "prep_minutes": 5, "cost": "$", "kitchen": "none"},
    {"id": "roasted_carrots", "name": "Roasted carrots", "category": "vegetable", "icon": "🥕", "log_categories": ["vegetables"], "prep_minutes": 25, "cost": "$", "kitchen": "oven"},
    {"id": "french_fries", "name": "French fries", "category": "vegetable", "icon": "🍟", "log_categories": ["salty_processed"], "prep_minutes": 20, "cost": "$", "kitchen": "oven"},
    # Fruit
    {"id": "apple_slices", "name": "Apple slices", "category": "fruit", "icon": "🍎", "log_categories": ["fruit"], "prep_minutes": 2, "cost": "$", "kitchen": "none"},
    {"id": "fruit_cup", "name": "Fresh fruit cup", "category": "fruit", "icon": "🍓", "log_categories": ["fruit"], "prep_minutes": 5, "cost": "$$", "kitchen": "none"},
    # Dairy
    {"id": "greek_yogurt", "name": "Greek yogurt", "category": "dairy", "icon": "🥣", "log_categories": ["dairy"], "prep_minutes": 0, "cost": "$", "kitchen": "none"},
    {"id": "cheese_slice", "name": "Cheese slice", "category": "dairy", "icon": "🧀", "log_categories": ["dairy"], "prep_minutes": 0, "cost": "$", "kitchen": "none"},
    # Other
    {"id": "avocado", "name": "Avocado slices", "category": "other", "icon": "🥑", "log_categories": ["other_protein"], "prep_minutes": 2, "cost": "$$", "kitchen": "none"},
    {"id": "cheese_sauce", "name": "Cheese sauce", "category": "other", "icon": "🧀", "log_categories": ["salty_processed"], "prep_minutes": 5, "cost": "$", "kitchen": "microwave"},
    {"id": "gravy", "name": "Gravy", "category": "other", "icon": "🥣", "log_categories": ["salty_processed"], "prep_minutes": 5, "cost": "$", "kitchen": "microwave"},
    {"id": "hummus", "name": "Hummus", "category": "other", "icon": "🫙", "log_categories": ["beans_fish_nuts"], "prep_minutes": 0, "cost": "$", "kitchen": "none"},
]

PLATE_ROUNDS = [
    {"id": "r1", "title": "Dinner, full kitchen", "constraint_note": "Everything's available tonight. Build a balanced plate.",
     "ingredient_ids": [i["id"] for i in INGREDIENT_LIBRARY], "min_items": 2, "max_items": 5},
    {"id": "r2", "title": "No stove tonight", "constraint_note": "Pantry and fridge only — assemble what you can without cooking.",
     "ingredient_ids": ["black_beans", "whole_wheat_tortilla", "white_rice", "side_salad", "avocado", "hummus",
                         "french_fries", "cheese_sauce", "greek_yogurt", "apple_slices"],
     "min_items": 2, "max_items": 4},
]


def score_plate(ingredient_ids: List[str], library: List[dict]) -> dict:
    """PROVISIONAL scoring — see module comment above. Coverage-based across
    the lightweight log categories, never calories or portion weight."""
    by_id = {i["id"]: i for i in library}
    items = [by_id[iid] for iid in ingredient_ids if iid in by_id]
    present = set()
    for i in items:
        present.update(i.get("log_categories", []))
    has_veg_or_fruit = bool(present & {"vegetables", "fruit"})
    has_whole_grain = "whole_grains" in present
    has_protein = bool(present & {"beans_fish_nuts", "other_protein"})
    less_healthy = present & {"salty_processed", "added_sugars"}

    missing = []
    if not has_veg_or_fruit:
        missing.append("a vegetable or fruit")
    if not has_whole_grain:
        missing.append("a whole grain")
    if not has_protein:
        missing.append("a protein source")

    if less_healthy:
        names = [i["name"] for i in items if set(i.get("log_categories", [])) & less_healthy]
        feedback = f"Great mix, but {', '.join(names)} leans salty/processed — a lighter side would round it out."
    elif missing:
        feedback = f"Good start — try adding {' and '.join(missing)} to round this plate out."
    else:
        feedback = "That's a well-rounded plate — vegetable or fruit, whole grain, and a protein source, no salty extras."

    return {
        "balanced": has_veg_or_fruit and has_whole_grain and has_protein and not less_healthy,
        "categories_present": sorted(present),
        "feedback": feedback,
        "marker": None if (has_veg_or_fruit and has_whole_grain and has_protein and not less_healthy) else "balance_gap",
    }


@api.get("/games/ingredients")
async def get_ingredients(user: dict = Depends(current_user)):
    allergy_terms = user.get("allergy_terms", [])
    library = filter_items_for_allergies(INGREDIENT_LIBRARY, allergy_terms)
    grouped: Dict[str, list] = {}
    for i in library:
        grouped.setdefault(i["category"], []).append(i)
    return {"ingredients": library, "grouped": grouped, "rounds": PLATE_ROUNDS}


class PlateScoreIn(BaseModel):
    round_id: str
    ingredient_ids: List[str]


@api.post("/games/g3/score-plate")
async def score_plate_route(body: PlateScoreIn, user: dict = Depends(current_user)):
    round_def = next((r for r in PLATE_ROUNDS if r["id"] == body.round_id), None)
    if not round_def:
        raise HTTPException(404, "Round not found")
    if not (round_def["min_items"] <= len(body.ingredient_ids) <= round_def["max_items"]):
        raise HTTPException(400, f"Plate must have {round_def['min_items']}-{round_def['max_items']} items")
    return score_plate(body.ingredient_ids, INGREDIENT_LIBRARY)


# ----------------------------------------------------------------------------
# Texas A&M / Sbisa + Commons Dining Hall sub-mode. Real menu sample data
# used as fallback when the live scraper can't be verified (see
# dining_scraper.py) — DTL still needs to confirm feasibility/status of the
# real-time integration per the review notes; this build does not overclaim
# that it's settled.
# ----------------------------------------------------------------------------
SBISA_SAMPLE_MENU = {
    "hall": "Sbisa Dining Hall (North Campus)",  # matches dining_scraper.HALL_DISPLAY_NAMES
    "stations": [
        {"station": "Grill", "items": [
            {"id": "sb_grilled_chicken", "name": "Grilled Chicken Breast"},
            {"id": "sb_cheeseburger", "name": "Cheeseburger"},
            {"id": "sb_veggie_burger", "name": "Veggie Burger"},
        ]},
        {"station": "Comfort", "items": [
            {"id": "sb_mac_cheese", "name": "Mac and Cheese"},
            {"id": "sb_fried_chicken_tenders", "name": "Fried Chicken Tenders"},
            {"id": "sb_meatloaf", "name": "Meatloaf with Gravy"},
        ]},
        {"station": "Greens & Grains", "items": [
            {"id": "sb_brown_rice", "name": "Brown Rice"},
            {"id": "sb_quinoa_salad", "name": "Quinoa Salad"},
            {"id": "sb_steamed_veg", "name": "Steamed Seasonal Vegetables"},
            {"id": "sb_side_salad", "name": "Build-Your-Own Side Salad"},
        ]},
        {"station": "Sides", "items": [
            {"id": "sb_fries", "name": "French Fries"},
            {"id": "sb_mashed_potatoes", "name": "Mashed Potatoes and Gravy"},
            {"id": "sb_fruit_cup", "name": "Fresh Fruit Cup"},
            {"id": "sb_dinner_roll", "name": "Dinner Roll with Butter"},
        ]},
    ],
}

COMMONS_SAMPLE_MENU = {
    "hall": "The Commons Dining Hall (South Campus)",
    "stations": [
        {"station": "Breakfast Grill", "items": [
            {"id": "cm_scrambled_eggs", "name": "Scrambled Eggs"},
            {"id": "cm_bacon", "name": "Bacon"},
            {"id": "cm_turkey_sausage", "name": "Turkey Sausage Links"},
        ]},
        {"station": "Griddle", "items": [
            {"id": "cm_pancakes", "name": "Buttermilk Pancakes"},
            {"id": "cm_waffles", "name": "Belgian Waffles"},
        ]},
        {"station": "Fresh Start", "items": [
            {"id": "cm_oatmeal", "name": "Steel-Cut Oatmeal"},
            {"id": "cm_yogurt_parfait", "name": "Greek Yogurt Parfait"},
            {"id": "cm_fruit_bowl", "name": "Fresh Fruit Bowl"},
        ]},
        {"station": "Bakery", "items": [
            {"id": "cm_whole_wheat_toast", "name": "Whole Wheat Toast"},
            {"id": "cm_cinnamon_roll", "name": "Cinnamon Roll"},
            {"id": "cm_bagel", "name": "Plain Bagel with Cream Cheese"},
        ]},
    ],
}

SAMPLE_MENUS = {"sbisa": SBISA_SAMPLE_MENU, "commons": COMMONS_SAMPLE_MENU}


# ----------------------------------------------------------------------------
# Menu cache. Every dining surface (menu, plates, swap, chat-build-meal)
# re-derives from the same fetched + classified menu, and a cold fetch is
# two apiv4 round-trips plus classification — so results are cached per
# hall/period/day, in-process. Keyword and LLM classifications are cached
# separately (the LLM one only exists once a user with a TAMU key asks).
# A failed live fetch caches the sample fallback only briefly, so a
# transient outage doesn't pin the sample menu for the whole TTL.
# ----------------------------------------------------------------------------
DINING_HALLS = ("sbisa", "commons")
DINING_PERIODS = ("breakfast", "lunch", "dinner")
_MENU_TTL = timedelta(minutes=30)
_MENU_RETRY_TTL = timedelta(minutes=5)
_menu_cache: Dict[tuple, tuple] = {}  # key -> (expires_at, value)
_menu_locks: Dict[tuple, asyncio.Lock] = {}


def _menu_cache_get(key: tuple):
    hit = _menu_cache.get(key)
    if hit and hit[0] > now_utc():
        return hit[1]
    return None


async def _raw_menu(hall: str, period: str) -> dict:
    """Live menu for today, or the sample fallback. Cached; concurrent
    callers for the same key share one fetch."""
    today = study_today()  # the student's "today" (Central), not the server's — Vercel runs on UTC
    key = ("raw", hall, period, today.isoformat())
    hit = _menu_cache_get(key)
    if hit is not None:
        return hit
    async with _menu_locks.setdefault(key, asyncio.Lock()):
        hit = _menu_cache_get(key)
        if hit is not None:
            return hit
        live = await dining_scraper.fetch_live_menu(hall, period, on_date=today)
        if live:
            menu, ttl = live, _MENU_TTL
        else:
            menu = {**copy.deepcopy(SAMPLE_MENUS[hall]), "source": "sample",
                    "date_note": "Sample menu for demo purposes — not a live Texas A&M Dining feed."}
            ttl = _MENU_RETRY_TTL
        menu["_cache_version"] = new_id()  # ties classified entries to this exact fetch
        _menu_cache[key] = (now_utc() + ttl, menu)
        return menu


async def _classified_menu(hall: str, period: str, tamu_key: Optional[str] = None) -> dict:
    """Menu classification degrades to the deterministic keyword classifier
    (dining_classifier.classify_menu) whenever TAMU AI isn't available for
    this user — including the mandatory-key case — rather than blocking the
    whole dining screen on a missing key. This is a non-AI fallback, not a
    different AI provider, so it stays even though Emergent is gone.
    Returns a deep copy — callers may mutate it freely."""
    raw = await _raw_menu(hall, period)
    kind = "llm" if tamu_key else "keyword"
    key = ("classified", kind, hall, period, raw["_cache_version"])
    hit = _menu_cache_get(key)
    if hit is None:
        async with _menu_locks.setdefault(key, asyncio.Lock()):
            hit = _menu_cache_get(key)
            if hit is None:
                ttl = _MENU_TTL
                if tamu_key:
                    try:
                        hit = await dining_classifier.llm_classify_menu(raw, tamu_key)
                    except Exception as e:
                        logger.warning(f"LLM classify fallback for {hall}/{period}: {e}")
                        hit = dining_classifier.classify_menu(raw)
                    if hit.get("classifier") != "llm":
                        ttl = _MENU_RETRY_TTL  # LLM fell back internally; retry it soon
                else:
                    hit = dining_classifier.classify_menu(raw)
                _menu_cache[key] = (now_utc() + ttl, hit)
                # Drop entries for older fetches of this hall/period.
                for k in [k for k in _menu_cache if k[0] == "classified" and k[2:4] == (hall, period)
                          and k[4] != raw["_cache_version"]]:
                    _menu_cache.pop(k, None)
    out = copy.deepcopy(hit)
    out.pop("_cache_version", None)
    return out


async def prewarm_dining_cache() -> None:
    """Startup background task: fetch + keyword-classify today's menus for
    every hall/period so the first participant request hits the cache.
    Never raises — a failure here just means that request fetches cold."""
    for hall in DINING_HALLS:
        for period in DINING_PERIODS:
            try:
                await _classified_menu(hall, period)
            except Exception as e:
                logger.warning(f"Dining prewarm failed for {hall}/{period}: {e}")
    logger.info("Dining menu cache prewarm finished")


def _user_tamu_key(user: dict) -> Optional[str]:
    try:
        return tamus_client.resolve_user_key(user)
    except tamus_client.TamusKeyRequiredError:
        return None


@api.get("/dining/menu")
async def get_dining_menu(hall: Literal["sbisa", "commons"] = "sbisa",
                           period: Literal["breakfast", "lunch", "dinner"] = "lunch",
                           for_recommendation: bool = False,
                           user: dict = Depends(current_user)):
    """Plain browse (default) shows everything served. for_recommendation=true
    is for surfaces that SUGGEST items (e.g. the plate-builder tray) and
    applies the participant's allergy/restriction filter."""
    menu = await _classified_menu(hall, period, _user_tamu_key(user))
    if for_recommendation:
        names = lambda m: {it["name"] for st in m.get("stations", []) for it in st.get("items", [])}  # noqa: E731
        served = names(menu)
        menu = filter_menu_for_allergies(menu, user.get("allergy_terms", []))
        menu["allergy_filtered"] = True
        # Distinct dishes: the same item is often served at several stations.
        menu["hidden_count"] = len(served - names(menu))
    return menu


@api.get("/dining/plates")
async def get_suggested_plates(hall: Literal["sbisa", "commons"] = "sbisa",
                                period: Literal["breakfast", "lunch", "dinner"] = "lunch",
                                user: dict = Depends(current_user)):
    menu = await get_dining_menu(hall=hall, period=period, user=user)
    safe_menu = filter_menu_for_allergies(menu, user.get("allergy_terms", []))

    first, _ = study_week_window(4)
    start = study_day_start_utc_iso(first)
    recent_meals = await db.meals.find(
        {"user_id": user["id"], "created_at": {"$gte": start}, "skipped": {"$ne": True}}
    ).to_list(50)
    recent_names = [m.get("name", "") for m in recent_meals]
    plates = plate_composer.compose_plates(safe_menu, recent_item_names=recent_names)
    return {"hall": menu["hall"], "source": menu.get("source", "sample"), "plates": plates}


class SwapIn(BaseModel):
    hall: Literal["sbisa", "commons"] = "sbisa"
    period: Literal["breakfast", "lunch", "dinner"] = "lunch"
    item_id: str = Field(max_length=200)
    exclude_ids: List[str] = Field(default=[], max_length=20)


@api.post("/dining/swap")
async def swap_item(body: SwapIn, user: dict = Depends(current_user)):
    menu = await get_dining_menu(hall=body.hall, period=body.period, user=user)
    # Alternatives are a recommendation surface: filter them, but keep the
    # item being swapped out so its station can still be found.
    safe_menu = filter_menu_for_allergies(menu, user.get("allergy_terms", []), keep_ids={body.item_id})
    return {"alternatives": plate_composer.suggest_swap(safe_menu, body.item_id, body.exclude_ids)}


# ----------------------------------------------------------------------------
# Future Me + chat guardrail. Rule set (nutrition team, 2026-10-29 /
# 2026-11-06):
#  - General guideline numbers are allowed — "less than 2,300 mg of sodium
#    a day", "look for 5% DV or less for sodium", "about 2 cups of fruit
#    a day" — and the four FDA Daily Values the team approved (sodium
#    2,300 mg, saturated fat 20 g, added sugars 50 g, fiber 28 g) are
#    quoted as general reference values for a 2,000-calorie diet, never
#    personal targets.
#  - Calorie counts are always blocked. The old FUTURE_ME_ALLOW_CALORIE_INFO
#    env switch is removed (2026-11-06, item 1: "Keep ... off, and remove
#    the setting if nothing else uses it"). The spelled-out and numeric
#    calorie patterns below stay — a drifted LLM reply that says "1,800
#    calories" still gets caught.
#  - Still blocked, always: the student's OWN HEI score (any x/5, x/10,
#    x/13), body-weight and weight-loss talk.
#  - FUTURE_ME_ALLOW_CALORIE_INFO was removed (2026-11-06, item 1).
# ----------------------------------------------------------------------------

# Always blocked: HEI-style score reveals.
_SCORE_REVEAL_PATTERNS = [
    # x/5, x/10, x/13, x/60, x/40, x/100 → the HEI engine's possible denominators.
    re.compile(r"\b\d+(\.\d+)?\s*/\s*(5|10|13|40|60|100)\b"),
    # 'your HEI score is …', 'you scored …', 'your score of …' — plain-English leaks.
    re.compile(r"\byour\s+(hei|heart[-\s]health|diet[-\s]quality)\s+score\b", re.IGNORECASE),
    re.compile(r"\byou(?:'ve|'ll| have)?\s+scored\b", re.IGNORECASE),
]

# Numeric calorie patterns (digits + 'calorie(s)' or 'kcal', or spelled-out
# number words + 'calories'). Always blocked (nutrition team 2026-11-06).
# One narrow exception: the 2,000-calorie diet context when framing a
# Daily Value, which reads as "2,000-calorie diet" — matched and allowed
# explicitly below.
_CALORIE_NUMERIC_PATTERNS = [
    re.compile(r"\b\d+(\.\d+)?\s*(k?cal(ories)?)\b", re.IGNORECASE),
]
# The 4 FDA DV entries say things like "based on a 2,000-calorie diet" as
# a *reference value frame*, not a target. The guardrail lets those through.
_CALORIE_REFERENCE_CONTEXT = re.compile(
    r"\b(2[,.]?000)[-\s]?(calorie|kcal)[-\s]?(diet|reference)\b",
    re.IGNORECASE,
)
_NUMBER_WORD = r"(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|" \
               r"twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand)"
_SPELLED_OUT_CALORIE_PATTERN = re.compile(
    rf"\b({_NUMBER_WORD}[\s-]+){{1,4}}\s*(calories|kcal)\b", re.IGNORECASE
)

# Weight-loss / body-size framing. Always blocked — reasonable guideline
# talk about sodium/sat fat/fiber/added sugars never needs to say these.
_RESTRICTION_PHRASES = [
    "watching your weight", "watching my weight",
    "lose weight", "losing weight", "weight loss", "weight-loss",
    "trim down", "trimming down", "slim down", "slimming down",
    "fat burn", "burn fat", "burn calories", "burn off",
    "shed pounds", "drop pounds", "drop a size", "drop sizes",
    "beach body", "bikini body", "summer body", "skinny",
    "diet to lose", "cutting weight", "cutting to lose",
    # Explicit calorie-counting framing (independent of the digit pattern).
    "counting calories", "count calories", "low-cal", "low cal",
    "guilt-free", "guilt free",
]


def _contains_prohibited_numeric_nutrition(text: str) -> bool:
    """Score reveals are ALWAYS blocked. Calorie numbers are always blocked
    (nutrition team 2026-11-06), with one narrow exception for the "2,000-
    calorie diet" phrase the KB uses to frame FDA Daily Values as general
    reference values rather than personal targets."""
    if any(p.search(text) for p in _SCORE_REVEAL_PATTERNS):
        return True
    scrubbed = _CALORIE_REFERENCE_CONTEXT.sub("", text)
    if any(p.search(scrubbed) for p in _CALORIE_NUMERIC_PATTERNS):
        return True
    return bool(_SPELLED_OUT_CALORIE_PATTERN.search(scrubbed))


# Strict plate-review restriction phrases. The plate-review LLM reviews a
# specific plate the student built; "Cut back on the rice" there frames
# a specific food as bad. Future Me chat uses the broader
# ``_RESTRICTION_PHRASES`` list only, because that endpoint benefits
# from being able to say things like "cut back on packaged soups to
# lower sodium" in the context of a general sodium answer.
_PLATE_REVIEW_RESTRICTION_PHRASES = _RESTRICTION_PHRASES + [
    "cut back on", "cut down on", "cut the", "keep it light", "keep things lighter",
    "lighter option", "lighter choice", "leaner choice", "fewer calories",
    "portion control", "eat less", "diet-friendly", "diet friendly",
    "scaling back", "scale back", "reduce your portion",
    "avoid the carbs", "avoid carbs",
    "skip the rice", "skip the bread", "skip the pasta", "skip the dressing",
]


def _contains_restriction_framing(text: str, *, strict: bool = False) -> bool:
    lowered = text.lower()
    phrases = _PLATE_REVIEW_RESTRICTION_PHRASES if strict else _RESTRICTION_PHRASES
    return any(phrase in lowered for phrase in phrases)


# Nutrition team feedback (2026-11-03): Future Me (and game feedback) must
# NEVER tell a student to skip a meal, cut out a whole food group, or eat
# very few calories. Even if the student asked, even if the LLM went off-
# script, the reply is replaced with a kind redirect to the study team.
# Catches both imperatives ("skip breakfast") and endorsements ("it's okay
# to skip dinner") — any sentence that frames one of these as a recommended
# behaviour trips the check.
_DISORDERED_EATING_ADVICE_PATTERNS = [
    # Skip a meal — imperative or endorsement.
    re.compile(r"\b(try|recommend\w*|suggest\w*|consider|it'?s?\s+okay\s+to|it'?s?\s+fine\s+to|you\s+can|you\s+could)\s+skip(ping)?\s+(breakfast|lunch|dinner|a\s+meal|meals|snacks?)\b", re.IGNORECASE),
    re.compile(r"\bskip(ping)?\s+(breakfast|lunch|dinner|a\s+meal|meals)\s+(is\s+(fine|okay|ok|fine for)|will\s+help|helps\s+you|to\s+(lose|cut|save))\b", re.IGNORECASE),
    # Cut out an entire food group — tolerate hyphens ("no-carbs diet"),
    # the word "all"/"every" preceding the food group, and compound
    # food names ("whole grains").
    re.compile(r"\bcut\s+out\s+(all|every)?\s*(carbs?|fats?|grains?|dairy|sugar|fruit|protein|food\s+groups?)\b", re.IGNORECASE),
    re.compile(r"\beliminat\w*\s+(all\s+|every\s+)?(carbs?|fats?|grains?|dairy|sugar|fruit|protein|food\s+groups?)\b", re.IGNORECASE),
    re.compile(r"\bavoid\s+all\s+(carbs?|fats?|grains?|dairy|sugar|fruit|protein)\b", re.IGNORECASE),
    re.compile(r"\bno[-\s]+(carbs?|fats?|grains?|dairy|sugar|fruit|protein)\s+(diet|meal|eating|approach|plan)\b", re.IGNORECASE),
    # Very-low-calorie recommendations ONLY. The threshold is 1,500 kcal;
    # anything below is flagged as restrictive regardless of the
    # FUTURE_ME_ALLOW_CALORIE_INFO flag (the flag covers reference
    # numbers like the "2,000 kcal" standard diet, not prescriptions of
    # restrictive targets). Supports commas in numbers (1,100 kcal) and
    # omitted "a day" / "per day".
    re.compile(r"\b(aim\s+for|try|eat|stick\s+to|stay\s+(at|under|below))\s+(?:about\s+)?(?:[1-9]\d{0,2}|1[0-4]\d{2}|1,[0-4]\d{2})\s+(k?cal(ories)?)\b", re.IGNORECASE),
    re.compile(r"\bunder\s+(?:[1-9]\d{0,2}|1[0-4]\d{2}|1,[0-4]\d{2})\s+(k?cal(ories)?)\s*(a\s+day|per\s+day|daily)?\b", re.IGNORECASE),
    re.compile(r"\bvery\s+low\s+calor(ie|y)\b", re.IGNORECASE),
    re.compile(r"\bstarvation\s+diet\b", re.IGNORECASE),
    re.compile(r"\bcrash\s+diet\b", re.IGNORECASE),
    re.compile(r"\bfast(ing)?\s+for\s+\d+\s+(days?|hours?)\b", re.IGNORECASE),
]


def _contains_disordered_eating_advice(text: str) -> bool:
    return any(p.search(text) for p in _DISORDERED_EATING_ADVICE_PATTERNS)


_DISORDERED_EATING_FALLBACK_REPLY = (
    "I'm going to pause before I answer that one — the direction sounds like it's headed toward skipping "
    "meals, cutting out food groups, or going very low on food. That's not something LLHS would ever suggest. "
    "If something's weighing on how you're eating, please reach out to the LLHS study team or TAMU Student "
    "Counseling Services (979-845-4427) — they're the right people. I'm here when you want to talk food habits "
    "(what to add, label-reading, dining-hall picks)."
)


def _guardrail_violation_type(text: str, *, strict: bool = False) -> Optional[str]:
    """``strict=True`` turns on the plate-review phrase list (which
    additionally blocks food-specific "cut back on X" wording). Future
    Me chat and game feedback use ``strict=False`` so general-guideline
    answers like "aim for less than 2,300 mg of sodium a day" survive.
    The disordered-eating-advice rule applies in BOTH modes — a reply
    suggesting skipping meals / cutting out food groups / very low
    intake is always blocked.

    The nutrition team's 2026-11-06 wording avoid list (item 3) is also
    enforced here as the ``wording_avoid`` layer — a reply that uses
    "unhealthy", "poor choices", "should", etc., is blocked and the
    model is retried / the safe fallback shown. The team expects these
    words never to appear in app feedback, so we treat a drift past the
    system prompt as a guardrail hit rather than a nudge."""
    if _contains_disordered_eating_advice(text):
        return "disordered_eating_advice"
    if _contains_prohibited_numeric_nutrition(text):
        return "numeric"
    if _contains_restriction_framing(text, strict=strict):
        return "restriction_phrase"
    if wording_rules.contains_avoid_phrase(text):
        return "wording_avoid"
    return None


# Fallback used when the model's reply trips a guardrail. Deliberately NOT
# the old "I keep things additive here" line — the nutrition team flagged
# that as dodging the question. The new fallback acknowledges the
# limitation and directs the student at the study team / dietitian; the
# knowledge-base lookup usually catches the question before we land here.
_SAFE_FALLBACK_REPLY = (
    "I'd rather hand this one to the study team — I don't want to guess with specifics "
    "about weight or calorie counts. For habit questions (what to add, swap, or try at "
    "the dining hall or when you shop), ask me and I'll help."
)


def _fallback_for_violation(violation: Optional[str], generic_fallback: str) -> str:
    """Pick the right student-facing reply for a given guardrail
    violation. ``disordered_eating_advice`` always gets the
    compassionate redirect, no matter which endpoint tripped it."""
    if violation == "disordered_eating_advice":
        return _DISORDERED_EATING_FALLBACK_REPLY
    return generic_fallback


# "Add your TAMU AI key" copy, shared by the chat endpoint's two paths
# (no key saved at the start of the LLM branch, or a mid-call failure
# that looks like a key problem: rejected key, invalid characters,
# exhausted credit). Nutrition team 2026-11-24: the scope redirects and
# the "not in my notes" fallback no longer sit behind this check.
def _tamus_key_missing_chat_response() -> dict:
    return {
        "answer": (
            "Add your TAMU AI key in Settings to chat with Future Me. That's what powers these replies. "
            "Everything else in the app still works without it."
        ),
        "citations": [], "disclaimer": DISCLAIMER, "points_awarded": 0,
        "pending_action": None, "tamus_key_required": True,
    }


def _is_tamus_key_problem(err: BaseException) -> bool:
    """True when a ``TAMUSError`` from ``tamus_client.chat`` looks like a
    key problem (rejected, malformed, exhausted credit) rather than a
    service outage. Keeps the "add your key" copy and the "couldn't
    reach TAMU AI" copy pointed at the right students."""
    msg = str(err).lower()
    return (
        "rejected" in msg
        or "invalid characters" in msg
        or "exhausted" in msg
    )


async def _guard_text(user: dict, endpoint: str, text: Any, fallback: str, *, strict: bool = False) -> str:
    """Model text shown to a participant: blocked (and logged) if it trips
    any guardrail layer, replaced with the right fallback copy. ``strict``
    turns on the plate-review phrase list (used only by the plate-review
    endpoint where food-specific restriction framing is also blocked)."""
    if not isinstance(text, str) or not text.strip():
        return fallback
    violation = _guardrail_violation_type(text, strict=strict)
    if not violation:
        return text
    logger.warning(f"Blocked {endpoint} text (layer={violation}) for user {user['id']}")
    await db.guardrail_blocks.insert_one({"id": new_id(), "user_id": user["id"], "endpoint": endpoint,
                                          "trigger_type": violation, "created_at": now_utc().isoformat()})
    await check_guardrail_block_pattern(user["id"])
    return _fallback_for_violation(violation, fallback)


async def _guard_list(user: dict, endpoint: str, items: Any, *, strict: bool = False) -> List[str]:
    """Keeps only string items that pass the guardrail."""
    out = []
    for it in items if isinstance(items, list) else []:
        if isinstance(it, str) and it.strip() and await _guard_text(user, endpoint, it, "", strict=strict) :
            out.append(it)
    return out


class ChatBuildMealIn(BaseModel):
    message: str = Field(min_length=1, max_length=500)
    hall: Literal["sbisa", "commons"] = "sbisa"
    period: Literal["breakfast", "lunch", "dinner"] = "lunch"


@api.post("/dining/chat-build-meal")
@limiter.limit("15/minute")
async def chat_build_meal(request: Request, body: ChatBuildMealIn, user: dict = Depends(current_user)):
    import json as _json

    menu = await get_dining_menu(hall=body.hall, period=body.period, user=user)
    allergy_terms = user.get("allergy_terms", [])
    all_items = []
    menu_lines = []
    for station in menu.get("stations", []):
        safe_items = filter_items_for_allergies(station.get("items", []), allergy_terms)
        names = [it["name"] for it in safe_items]
        all_items.extend(safe_items)
        if names:
            menu_lines.append(f"{station['station']}: " + ", ".join(names[:25]))
    menu_context = "\n".join(menu_lines[:20])
    valid_ids = {it["id"]: it["name"] for it in all_items}

    system = (
        f"You are a friendly meal-building helper for a college student at {menu.get('hall', 'their dining hall')}, "
        f"helping them build a plate for {body.period} using ONLY the real items listed below. "
        "Today's menu:\n" + menu_context + "\n\n"
        "HARD RULES:\n"
        "- Only ever suggest items from the list above — never invent a dish, never suggest something not listed.\n"
        "- NEVER mention or estimate calories, grams, milligrams, or percent-daily-value, for any reason, even if asked directly. "
        "If asked for calorie counts, lowest-calorie options, or to rank foods best-to-worst, redirect warmly to "
        "building a satisfying plate instead — do not comply with the numeric request.\n"
        "- NEVER reveal a numeric score of any kind, including anything that looks like 'X/10' or 'X out of 13'.\n"
        "- NEVER use restriction language — no 'watching your intake,' 'keep it light,' 'cut back,' 'guilt-free,' "
        "'skip the X,' or any framing that implies eating less is the goal. Frame everything as what to ADD, never what to cut.\n"
        "- Never say 'avoid' or label anything as bad — frame everything additively.\n"
        "- Never give medical or diagnostic advice.\n"
        "- Keep your reply to 2-3 sentences, warm and conversational.\n"
        "Respond ONLY with compact JSON: "
        '{"reply": "your conversational response", "plate_item_names": ["exact item name from the list", ...]}. '
        "plate_item_names must be a subset of the exact names listed above (0-4 items). No markdown, no prose outside the JSON."
    )

    tamus_key_required = False
    try:
        raw = await run_llm(user, system, body.message, f"dining-chat-{user['id']}")
        cleaned = raw.strip().strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        start, end = cleaned.find("{"), cleaned.rfind("}")
        data = _json.loads(cleaned[start:end + 1]) if start >= 0 else {}
    except tamus_client.TamusKeyRequiredError:
        tamus_key_required = True
        data = {}
    except Exception as e:
        logger.error(f"Dining chat-build-meal error: {e}")
        data = {}

    safety_checkin = None
    if tamus_key_required:
        reply = "Add your TAMU AI key in Settings to use the meal-building chat — you can still browse and build a plate manually."
    else:
        reply = data.get("reply", "").strip()
        violation = _guardrail_violation_type(reply) if reply else None
        if not reply or violation:
            if reply:
                logger.warning(f"Blocked a chat-build-meal reply (layer={violation}) for user {user['id']}")
                await db.guardrail_blocks.insert_one({
                    "id": new_id(), "user_id": user["id"], "endpoint": "chat-build-meal",
                    "trigger_type": violation, "created_at": now_utc().isoformat(),
                })
                safety_checkin = await check_guardrail_block_pattern(user["id"])
            reply = _fallback_for_violation(violation, _SAFE_FALLBACK_REPLY)

    valid_names = set(valid_ids.values())
    suggested_names = [n for n in data.get("plate_item_names", []) if n in valid_names]
    # The same dish can be served at several stations — keep one per name,
    # in the model's order, capped at the 4 the prompt allows.
    first_by_name: Dict[str, dict] = {}
    for it in all_items:
        first_by_name.setdefault(it["name"], it)
    suggested_items = [first_by_name[n] for n in dict.fromkeys(suggested_names)][:4]

    return {
        "reply": reply,
        "plate_items": [{"id": it["id"], "name": it["name"]} for it in suggested_items],
        "disclaimer": "Illustrative suggestions from today's real menu, not medical or dietary advice.",
        "safety_checkin": safety_checkin,
        "tamus_key_required": tamus_key_required,
    }


@api.get("/dining/sbisa/menu")
async def get_sbisa_menu(user: dict = Depends(current_user)):
    return await get_dining_menu(hall="sbisa", period="lunch", user=user)


class SbisaReviewIn(BaseModel):
    item_names: List[str] = Field(min_length=1, max_length=6)

    @field_validator("item_names")
    @classmethod
    def _cap_item_length(cls, v: List[str]) -> List[str]:
        for name in v:
            if len(name) > 120:
                raise ValueError("Each dish name must be 120 characters or fewer.")
        return v


def safe_review_suggestions(raw: Any, allergy_terms: List[str]) -> List[str]:
    """The model's plate-review suggestions, minus anything that isn't a
    string or mentions one of the participant's allergens — enforced here
    even though the prompt already forbids it."""
    if not isinstance(raw, list):
        return []
    return [sug for sug in raw if isinstance(sug, str) and sug.strip()
            and not item_matches_allergy({"name": sug}, allergy_terms)]


@api.post("/dining/review-plate")
@api.post("/dining/sbisa/review-plate")
@limiter.limit("15/minute")
async def review_sbisa_plate(request: Request, body: SbisaReviewIn, user: dict = Depends(current_user)):
    import json

    allergy_terms = user.get("allergy_terms", [])
    # Reviewed names are free text, so classify them to get log categories
    # (e.g. "Greek Yogurt" -> dairy) for the category-level allergy check.
    reviewed = [{"name": n, "tags": dining_classifier.classify_item(n)} for n in body.item_names]
    allergy_items = [it["name"] for it in reviewed if item_matches_allergy(it, allergy_terms)]

    system = (
        "You are a heart-health reviewer for a college student's dining hall plate. Given a list of real dish "
        "names from a dining hall menu, evaluate the plate using ONLY these criteria: presence of vegetables or "
        "fruit, presence of whole grains, presence of a protein source, and salty/heavily processed items. "
        "NEVER mention or estimate calories, weight, portion size, or a numeric score. "
        + (f"The student must avoid foods containing: {', '.join(allergy_terms)} — never suggest adding any of "
           "these. " if allergy_terms else "") +
        "Respond ONLY with compact JSON: "
        '{"has_produce": bool, "has_whole_grains": bool, "has_protein": bool, '
        '"salty_processed_items": ["..."], "balanced": bool, "strengths": ["short phrase", ...], '
        '"suggestions": ["short phrase", ...], "summary": "1-2 sentence calm, non-judgmental summary"}. '
        "No prose outside the JSON, no markdown fences."
    )
    tamus_key_required = False
    try:
        raw = await run_llm(
            user, system, "Plate items: " + "; ".join(body.item_names) + ". Return JSON only.",
            f"sbisa-{user['id']}",
        )
        cleaned = raw.strip().strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        start, end = cleaned.find("{"), cleaned.rfind("}")
        data = json.loads(cleaned[start:end + 1]) if start >= 0 else {}
    except tamus_client.TamusKeyRequiredError:
        tamus_key_required = True
        data = {}
    except Exception as e:
        logger.error(f"Sbisa plate review error: {e}")
        data = {}

    summary = (
        "Add your TAMU AI key in Settings for plate feedback — your plate choices are still saved."
        if tamus_key_required else
        data.get("summary", "Review unavailable right now — your plate choices are still saved.")
    )
    # Suggestions are free text from the model — drop any that name an
    # allergen even though the prompt already forbids it.
    suggestions = await _guard_list(user, "review-plate", safe_review_suggestions(data.get("suggestions"), allergy_terms), strict=True)
    summary = await _guard_text(
        user, "review-plate", summary,
        "Thanks for building a plate. Your plate choices are saved.",
        strict=True,
    )
    strengths = await _guard_list(user, "review-plate", data.get("strengths", []), strict=True)
    return {
        "has_produce": bool(data.get("has_produce", False)),
        "has_whole_grains": bool(data.get("has_whole_grains", False)),
        "has_protein": bool(data.get("has_protein", False)),
        "salty_processed_items": data.get("salty_processed_items", []),
        "balanced": bool(data.get("balanced", False)),
        "strengths": strengths,
        "suggestions": suggestions,
        "summary": summary,
        "disclaimer": "Illustrative heart-health feedback, not medical or dietary advice.",
        "tamus_key_required": tamus_key_required,
        "allergy_flag": bool(allergy_items),
        "allergy_items": allergy_items,
    }


_MENU_CHALLENGE_GAME_IDS = {"g2"}  # old Nutrition / Menu Challenge


def _games_visible_to_user() -> list:
    """Filter the games list so g2 (Nutrition / Menu Challenge) only
    appears when MENU_CHALLENGE_ENABLED is on. Nutrition team flagged
    g2 on 2026-10-29 as inaccurate; it's hidden for all accounts (not
    gated by is_test) because the inaccuracy would reach any viewer."""
    if menu_challenge_enabled():
        return GAMES
    return [g for g in GAMES if g["id"] not in _MENU_CHALLENGE_GAME_IDS]


@api.get("/games")
async def get_games(user: dict = Depends(current_user)):
    done = await db.completions.find({"user_id": user["id"], "kind": "game"}).to_list(100)
    done_ids = {d["ref"] for d in done}
    return [{**g, "points": program.POINTS["practice"], "completed": g["id"] in done_ids}
            for g in _games_visible_to_user()]


@api.post("/games/{game_id}/complete")
async def complete_game(game_id: str, body: GameResultIn, user: dict = Depends(current_user)):
    # Also refuses completion for a hidden game — a stale client that
    # still has /games/g2 bookmarked would otherwise be able to post
    # a completion event.
    if game_id in _MENU_CHALLENGE_GAME_IDS and not menu_challenge_enabled():
        raise HTTPException(410, "That activity is no longer available.")
    game = next((g for g in GAMES if g["id"] == game_id), None)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    await db.game_results.insert_one({
        "id": new_id(), "user_id": user["id"], "game_id": game_id,
        "markers": body.markers, "score": body.score, "created_at": now_utc().isoformat(),
    })
    awarded = 0
    if not await db.completions.find_one({"user_id": user["id"], "kind": "game", "ref": game_id}):
        await db.completions.insert_one(
            {"id": new_id(), "user_id": user["id"], "kind": "game", "ref": game_id, "created_at": now_utc().isoformat()}
        )
        awarded = program.POINTS["practice"]
        await award_points(user["id"], awarded, badge="Skill Builder")
    return {"points_awarded": awarded}


# ----------------------------------------------------------------------------
# Daily challenge — same question for every participant on the same day,
# chosen deterministically by date (never random). Awards a fixed point
# amount on first correct answer; wrong answers still return feedback but
# don't award. No streaks and no shame states — matches the regular
# mini-game rules.
# ----------------------------------------------------------------------------
class DailyChallengeIn(BaseModel):
    # extra="forbid" so a client (or an older frontend build) can't sneak
    # in a `date` field and pretend an answer is for a different day.
    # "Today" is the server-decided study-today — see study_today() above.
    model_config = ConfigDict(extra="forbid")
    challenge_id: str
    choice_id: str


@api.get("/games/daily-challenge")
async def get_daily_challenge(user: dict = Depends(current_user)):
    today = study_today()
    challenge = _daily_challenge_for(today)
    if not challenge:
        return {"challenge": None, "already_completed": False, "points": DAILY_CHALLENGE_POINTS}
    done = await db.daily_challenge_results.find_one({
        "user_id": user["id"], "challenge_id": challenge["id"], "date": today.isoformat(), "correct": True,
    })
    # Scrub the server-only `correct` flag from the challenge payload — the
    # client reveals it on answer, not before.
    public_choices = [{k: v for k, v in c.items() if k != "correct"} for c in challenge.get("choices", [])]
    return {
        "challenge": {**{k: v for k, v in challenge.items() if k != "choices"}, "choices": public_choices, "date": today.isoformat()},
        "already_completed": bool(done),
        "points": DAILY_CHALLENGE_POINTS,
    }


@api.post("/games/daily-challenge/answer")
async def answer_daily_challenge(body: DailyChallengeIn, user: dict = Depends(current_user)):
    day = study_today()
    challenge = _daily_challenge_for(day)
    if not challenge or challenge["id"] != body.challenge_id:
        raise HTTPException(status_code=404, detail="That daily challenge isn't today's")
    choice = next((c for c in challenge["choices"] if c["id"] == body.choice_id), None)
    if not choice:
        raise HTTPException(status_code=404, detail="Choice not found")
    correct = bool(choice.get("correct"))
    awarded = 0  # Default: no points awarded. Only overwritten on first-correct insert.
    # Every attempt is recorded so the research team can see unassisted vs.
    # corrected answers. The uniqueness guard lives on `completions` below,
    # not here — this collection intentionally allows multiple rows.
    await db.daily_challenge_results.insert_one({
        "id": new_id(), "user_id": user["id"], "challenge_id": challenge["id"],
        "date": day.isoformat(), "choice_id": body.choice_id, "correct": correct,
        "created_at": now_utc().isoformat(),
    })
    if correct:
        ref = f"{challenge['id']}:{day.isoformat()}"
        already = await db.completions.find_one({
            "user_id": user["id"], "kind": "daily_challenge", "ref": ref,
        })
        if not already:
            try:
                await db.completions.insert_one({
                    "id": new_id(), "user_id": user["id"], "kind": "daily_challenge",
                    "ref": ref, "created_at": now_utc().isoformat(),
                })
                awarded = DAILY_CHALLENGE_POINTS
                await award_points(user["id"], awarded)
            except DuplicateKeyError:
                # Another request landed between our find_one and insert_one —
                # the partialFilterExpression unique index on completions
                # (see create_indexes) rejected the second insert. Keep
                # `awarded` at 0: the first request already awarded the points.
                pass
    return {
        "correct": correct,
        "feedback": choice.get("feedback", ""),
        "points_awarded": awarded,
    }


# ----------------------------------------------------------------------------
# Gamification + cooperative cohort challenge
# ----------------------------------------------------------------------------
BADGE_DEFS = ["First Lesson", "Skill Builder", "Consistent Logger", "Balanced Week"]


@api.get("/gamification")
async def get_gamification(user: dict = Depends(current_user)):
    u = await db.users.find_one({"id": user["id"]})
    meals = await db.meals.find({"user_id": user["id"]}).sort("created_at", -1).to_list(500)
    # Day buckets in the study TZ, not UTC — a 11:30 PM Chicago log belongs
    # to that evening's bucket, not the next day's.
    days = sorted({study_day_key(m["created_at"]) for m in meals}, reverse=True)
    streak = 0
    today = study_today()
    cursor = today
    for _ in range(len(days) + 2):
        if cursor.isoformat() in days:
            streak += 1
            cursor = cursor - timedelta(days=1)
        elif cursor == today:
            cursor = cursor - timedelta(days=1)
        else:
            break
    return {"points": u.get("points", 0), "badges": u.get("badges", []), "all_badges": BADGE_DEFS, "streak": streak}


def is_test_account(u: dict) -> bool:
    """QA/demo accounts that must never inflate cohort-facing counts:
    @example.com addresses (what the test suite uses), the staff
    TAMUS_ADMIN_TEST_EMAILS allowlist, and anything flagged is_test_account."""
    email = (u.get("email") or "").strip().lower()
    return bool(u.get("is_test_account")) or email.endswith("@example.com") \
        or tamus_client.is_admin_test_account(email)


def real_participant_filter() -> dict:
    """Mongo filter over db.users equivalent to `not is_test_account(u)` —
    the one place cohort/weekly-story counts decide who counts."""
    return {"$and": [
        {"is_test_account": {"$ne": True}},
        {"email": {"$not": re.compile(r"@example\.com$", re.IGNORECASE)}},
        {"email": {"$nin": sorted(tamus_client._admin_test_emails())}},
    ]}


async def real_participant_ids() -> List[str]:
    users = await db.users.find(real_participant_filter(), {"id": 1}).to_list(100000)
    return [u["id"] for u in users]


@api.get("/cohort")
async def get_cohort(user: dict = Depends(current_user)):
    # Rolling 7 calendar days ending today in the study TZ. See the open
    # team question in docs/UI-REDESIGN.md about turning this into a true
    # calendar week (Mon-Sun) later.
    first, _ = study_week_window(7)
    week_start = study_day_start_utc_iso(first)
    all_week_meals = await db.meals.find({
        "created_at": {"$gte": week_start}, "skipped": {"$ne": True},
        "user_id": {"$in": await real_participant_ids()},
    }).to_list(5000)
    cohort_balanced = sum(1 for m in all_week_meals if meal_has_core_categories(m))
    # Your own contribution counts even on a test account — only the shared total excludes them.
    your_meals = await db.meals.find(
        {"user_id": user["id"], "created_at": {"$gte": week_start}, "skipped": {"$ne": True}}
    ).to_list(500)
    your_balanced = sum(1 for m in your_meals if meal_has_core_categories(m))

    demo_seed = int(os.environ.get("COHORT_DEMO_SEED", "0"))
    total = demo_seed + cohort_balanced
    target = 500
    return {
        "title": "Balanced Meals This Week",
        "description": "The whole cohort works toward a shared, process-based milestone. No rankings, no comparison — everyone contributes together.",
        "current": min(total, target), "raw_current": total, "target": target, "your_contribution": your_balanced,
    }


# ----------------------------------------------------------------------------
# TAMU AI calls shared by the Coach (KB Q&A, /chat) and Future Me (the
# digital twin, /future-me). Neither ever sees or repeats a raw HEI-2020 or
# simulation-engine number; every reply passes the two-layer guardrail.
# ----------------------------------------------------------------------------
async def run_llm(user: dict, system: str, user_text: str, session_id: str,
                  history: Optional[List[Dict[str, str]]] = None) -> str:
    """TAMU AI is the sole text-chat provider. Raises TamusKeyRequiredError
    (uncaught) when the participant has no usable key — every call site
    decides how to surface that: the endpoints where the model's reply IS
    the whole response (/chat, dining chat-build-meal) catch it specifically
    and return a clear "add your key" prompt; assistive/optional endpoints
    (categorize-text, analyze-photo, plate review) let it fall into their
    existing broad except-and-degrade-to-manual-entry handling."""
    raw_key = tamus_client.resolve_user_key(user)
    model = user.get("tamus_model_chat") or tamus_client.DEFAULT_CHAT_MODEL
    return await tamus_client.chat(raw_key, model, system, user_text, history=history)


@api.get("/chat/history")
async def chat_history(session_id: Optional[str] = None, user: dict = Depends(current_user)):
    query = {"user_id": user["id"], **({"session_id": session_id} if session_id else {})}
    msgs = await db.chat_messages.find(query).sort("created_at", 1).to_list(200)
    return [{k: v for k, v in m.items() if k != "_id"} for m in msgs]


_SUPPORT_NEED_PROMPTS = {
    "meal_planning": "Can you help me plan a few meals for this week?",
    "grocery_tips": "What should I grab on a quick grocery run?",
    "time_management": "How can I eat well on my busiest days?",
    "limited_equipment": "What can I make with the kitchen setup I have?",
    "quick_meals": "What's a quick meal I can put together in 10 minutes?",
    "healthy_snacking": "What are some satisfying snack ideas?",
    # Additive phrasing on purpose — "portion control" is itself a blocked
    # restriction phrase in the chat guardrail.
    "portion_control": "How do I build a plate that keeps me full and satisfied?",
    "reading_labels": "What should I look for first on a nutrition label?",
    "understanding_guidelines": "What do the Dietary Guidelines actually recommend?",
    "balanced_meals": "How do I build a balanced plate?",
    "budget_eating": "How can I eat well on a tight budget?",
    "eating_out": "How can I build a balanced order when I eat out?",
    "cravings_stress": "What helps when stress makes me crave snacks?",
}
_HARDEST_MEAL_WORD = {"breakfast": "breakfast", "lunch": "lunch", "dinner": "dinner", "snacks": "snack"}
_HARDEST_MEAL_PLACE = {
    "home": "at home", "campus": "on campus", "restaurant": "at a restaurant", "fast_food": "at a fast-food spot",
    "work": "at work", "traveling": "while traveling",
}
_HAS_APPLIANCE = {"shared", "personal"}


def _profile_prompts(profile: Dict[str, Any]) -> List[str]:
    """Deterministic, template-based prompts from the onboarding survey, in
    priority order: hardest meal/location, cooking-setup limits, stated
    support needs, then meal plan."""
    prompts: List[str] = []
    meal = _HARDEST_MEAL_WORD.get(profile.get("hardest_meal"))
    if meal:
        place = _HARDEST_MEAL_PLACE.get(profile.get("hardest_meal_location"), "")
        prompts.append(f"What's an easy, balanced {meal} I can get {place}?".replace(" ?", "?"))

    kitchen = profile.get("kitchen_access")
    if kitchen == "none":
        prompts.append("What balanced meals work with no kitchen at all?")
    elif kitchen in ("personal", "shared"):
        has = lambda k: profile.get(f"appliance_{k}") in _HAS_APPLIANCE
        if not has("stove") and not has("oven") and has("microwave"):
            prompts.append("What balanced meals can I make with just a microwave?")
        elif not has("stove") and not has("oven") and not has("microwave") and "appliance_stove" in profile:
            prompts.append("What can I put together without any cooking?")
        elif profile.get("appliance_refrigerator_size") == "mini":
            prompts.append("What should I keep stocked in a mini fridge?")

    for need in profile.get("support_needs") or []:
        if need in _SUPPORT_NEED_PROMPTS:
            prompts.append(_SUPPORT_NEED_PROMPTS[need])

    if profile.get("university_meal_plan") == "yes":
        prompts.append("How do I build a balanced plate at the dining hall?")
    return prompts


# Coach starter questions for each focus area — things the KB can answer.
COACH_FOCUS_QUESTIONS = {
    "total_fruits": "What's an easy fruit to grab between classes?",
    "whole_fruits": "Is juice as good as whole fruit?",
    "total_vegetables": "How can I add a vegetable at the dining hall?",
    "greens_beans": "What counts as greens and beans?",
    "whole_grains": "Is brown rice a whole grain?",
    "dairy": "What counts as dairy if I don't drink milk?",
    "total_protein_foods": "What are easy protein foods for a busy day?",
    "seafood_plant_proteins": "What are easy plant proteins at the dining hall?",
    "fatty_acids": "Is olive oil a healthy fat?",
    "refined_grains": "What's an easy swap for white bread?",
    "sodium": "What are easy swaps for salty snacks?",
    "added_sugars": "What can I drink in place of soda?",
    "saturated_fats": "What's an easy swap for fried food?",
}


FOCUS_AREA_PROMPT = {
    "fruit": "How can I eat more whole fruit with my meals?",
    "vegetables_beans": "How can I change my regular meals to include more vegetables and beans?",
    "grains": "How can I change my regular meals to include more whole grains?",
    "dairy": "How can I change my regular meals to include more dairy?",
    "protein_foods": "How can I change my regular meals to include more beans, fish or nuts?",
    "fats": "How can I swap in healthier fats at my regular meals?",
    "sodium": "How can I cut back on salt in my regular meals?",
    "added_sugars": "How can I cut back on added sugars in my regular meals?",
}


@api.get("/chat/suggested-prompts")
async def suggested_prompts(user: dict = Depends(current_user)):
    """Three conversation starters for Future Me, personalized to the
    participant's focus area."""
    # Study team feedback 5.1: what to focus on, the focus area in everyday
    # meals, and a progress check-in. The middle one is worded per area so
    # the knowledge base can answer it.
    area = user.get("focus_area")
    middle = FOCUS_AREA_PROMPT.get(area)
    if not middle:  # no focus area yet: their onboarding answers, else a starter
        middle = next(iter(_profile_prompts(user.get("profile") or {})), "What's a balanced plate?")
    return {"prompts": ["What's one thing I could work on this week?", middle, "Help me check in on my progress"]}


# ----------------------------------------------------------------------------
# Chat-driven actions — lets the Coach LOG something or change focus areas
# on the participant's behalf when they ask in plain language ("log that I
# had a salad for lunch"). The model never writes to the database itself:
# it may only propose a single trailing "ACTION_JSON: {...}" block, which
# is (1) stripped from the visible reply before the user ever sees it,
# (2) parsed and re-validated here against the EXACT SAME Pydantic models
# the manual REST endpoints use, and (3) returned to the client as an
# unexecuted `pending_action` — nothing is written until the participant
# explicitly confirms it via POST /chat/confirm-action, which re-validates
# it again and executes it through the same shared helpers as the manual
# logging screens (see _internal_log_meal / _internal_log_activity /
# _internal_log_sleep / _internal_set_focus_areas above). A malformed,
# unrecognized, or hallucinated action is silently dropped — the
# conversational reply is never blocked or altered because of it.
# ----------------------------------------------------------------------------
CHAT_ACTION_TYPES = {"log_meal", "log_activity", "log_sleep", "set_focus_areas", "try_swap", "try_step"}
_ACTION_JSON_RE = re.compile(r"\n?ACTION_JSON:\s*(\{.*\})[\s`]*$", re.DOTALL)


def _build_action_summary(action_type: str, payload: dict, current_area: Optional[str] = None) -> str:
    if action_type == "log_meal":
        label_by_id = {c["id"]: c["label"] for c in LIGHTWEIGHT_LOG_CATEGORIES}
        cats = ", ".join(label_by_id.get(c, c) for c in payload.get("categories", [])) or "no categories"
        return f'Log "{payload.get("name", "Meal")}" ({payload.get("meal_type", "lunch")}) — {cats}'
    if action_type == "log_activity":
        return f"Log {payload.get('minutes', 0)} minutes of activity ({payload.get('kind', 'moderate')})"
    if action_type == "log_sleep":
        return f"Log {payload.get('hours', 0)} hours of sleep"
    if action_type == "set_focus_areas":
        label = focus_areas.BY_ID[payload["area_id"]]["label"]
        return f"Change your focus area to {label}" if current_area else f"Make {label} your focus area"
    if action_type == "try_swap":
        return f"Add \"{twin_suggest.SWAPS_BY_ID[payload['swap_id']]['swap_label']}\" to your plan"
    if action_type == "try_step":
        return f"Add \"{twin_recommend.lookup(payload['rec_id'])['title']}\" to your plan"
    return "Confirm this action"


def _prevalidate_focus_area_action(current_area: Optional[str], payload: dict) -> tuple:
    """Decides what to do with the model's proposed focus area *before* it
    leaves the server as a pending_action. Returns (final_payload,
    decline_reason): an unknown area is dropped silently (the model made it
    up); the area they already have gets a short note and no card."""
    area_id = payload.get("area_id")
    if not isinstance(area_id, str) or area_id not in focus_areas.BY_ID:
        return None, None
    if area_id == current_area:
        return None, f"{focus_areas.BY_ID[area_id]['label']} is already your focus area."
    return {"area_id": area_id}, None


def _validate_chat_action_payload(action_type: str, payload: dict) -> dict:
    """Re-runs the SAME Pydantic validation the manual endpoints use.
    Raises on anything invalid — the caller treats that as 'no action'."""
    if action_type == "log_meal":
        name = (payload.get("name") or "").strip()
        if not name:
            cats = payload.get("categories") or []
            labels = [c["label"] for c in LIGHTWEIGHT_LOG_CATEGORIES if c["id"] in cats]
            name = ", ".join(labels) or "Meal"
        model = MealIn(
            name=name[:200], source="text", meal_type=payload.get("meal_type", "lunch"),
            categories=payload.get("categories", []), portion=payload.get("portion", "normal"), confirmed=True,
        )
    elif action_type == "log_activity":
        model = ActivityIn(minutes=payload.get("minutes", 0), kind=payload.get("kind", "moderate"))
    elif action_type == "log_sleep":
        model = SleepIn(hours=payload.get("hours", 0))
    elif action_type == "set_focus_areas":
        model = FocusAreasIn(area_id=payload.get("area_id", ""))
    elif action_type == "try_swap":
        model = SwapPlanIn(swap_id=str(payload.get("swap_id", "")))  # rejects any swap_id not in the table
    elif action_type == "try_step":
        model = TwinStepRefIn(rec_id=str(payload.get("rec_id") or payload.get("step_id") or ""))
    else:
        raise ValueError(f"unknown chat action type: {action_type}")
    return model.dict()


def _parse_chat_action(raw_text: str, current_area: Optional[str] = None) -> tuple:
    """Strips a trailing ACTION_JSON block from the model's raw reply
    (always, whether or not it validates) and returns
    (visible_text, pending_action_or_None, decline_reason_or_None).

    For set_focus_areas, the payload is one of the eight focus areas; the
    area they already have, or one that doesn't exist, never becomes a card.
    """
    match = _ACTION_JSON_RE.search(raw_text)
    if not match:
        return raw_text, None, None
    visible = raw_text[:match.start()].rstrip()
    try:
        data = json.loads(match.group(1).strip().strip("`"))
        action_type = data.get("type")
        payload = data.get("payload") if isinstance(data.get("payload"), dict) else {
            k: v for k, v in data.items() if k != "type"
        }
        if action_type not in CHAT_ACTION_TYPES:
            return visible, None, None

        decline: Optional[str] = None
        if action_type == "set_focus_areas":
            final_payload, decline = _prevalidate_focus_area_action(current_area, payload)
            if final_payload is None:
                return visible, None, decline
            payload = final_payload

        validated = _validate_chat_action_payload(action_type, payload)
    except Exception as e:
        logger.info(f"Dropped an unparseable/invalid chat action: {e}")
        return visible, None, None

    summary = _build_action_summary(action_type, validated, current_area=current_area)
    return visible, {"type": action_type, "payload": validated, "summary": summary}, None


class ChatActionIn(BaseModel):
    type: Literal["log_meal", "log_activity", "log_sleep", "set_focus_areas", "try_swap", "try_step"]
    payload: dict


class TwinStepRefIn(BaseModel):
    """A behavioral-twin step the Coach proposes (try_step): must exist in
    the reviewed library or swap table; whether THIS participant may have
    it is checked separately at proposal and confirm time."""
    rec_id: str = Field(min_length=1, max_length=80)

    @field_validator("rec_id")
    @classmethod
    def _known(cls, v: str) -> str:
        if not twin_recommend.known_step(v):
            raise ValueError("Unknown step")
        return v


# ----------------------------------------------------------------------------
# Future Me — the digital twin. Reflects the student's OWN data (focus areas
# and strengths from ASA24, logs, rings, the check-in countdown) and runs the
# rule-based what-if engine. Never a number from the engine, never one
# combined score; the LLM may only reword the engine's direction, and that
# rewording must pass the guardrail and contain no digits.
# ----------------------------------------------------------------------------
async def _days_logged_this_week(uid: str) -> dict:
    """Weekly counts for Future Me, built from the same helper that feeds the
    daily-goals snapshot — so Today, Future Me and Progress always report
    the same numbers for the same user and window."""
    first, last = study_week_window(7)
    start = study_day_start_utc_iso(first)
    q = {"user_id": uid, "created_at": {"$gte": start}}
    meals = await db.meals.find(q).to_list(500)
    acts = await db.activities.find(q).to_list(500)
    sleeps = await db.sleeps.find(q).to_list(100)
    first_iso, last_iso = first.isoformat(), last.isoformat()
    counts = daily_goals.week_days_logged(
        {"food": meals, "move": acts, "rest": sleeps}, first_iso, last_iso
    )
    move_minutes = daily_goals.week_move_minutes(acts, first_iso, last_iso)
    return {
        "any": counts["any_days"],
        "eat": counts["eat_days"],
        "move": counts["move_days"],
        "rest": counts["rest_days"],
        "meals": sum(1 for m in meals if not m.get("skipped")),
        "move_minutes": move_minutes,
    }


# ---- From your own meals ------------------------------------------------------
# The behavior side of the twin: Future Me reads the student's own meal
# logs (twin_habits), their onboarding setup and allergies, and today's
# real Aggie Dining menus, and offers one or two swaps from the reviewed
# swap table (twin_suggest / content/swaps.json) anchored to a meal they
# already have. No LLM anywhere in this path; the Coach may only reword it.
_TWIN_MENU_WAIT_SECONDS = 6.0
_twin_menu_tasks: set = set()  # keeps background fetches referenced until they finish


def _twin_menu_task_done(task: "asyncio.Task") -> None:
    _twin_menu_tasks.discard(task)
    if not task.cancelled() and task.exception() is not None:  # retrieve it so asyncio doesn't warn
        logger.warning(f"From-your-meals background menu fetch failed: {task.exception()}")


async def _twin_menus_today() -> Dict[str, Dict[str, dict]]:
    """Today's menus for both halls and all periods, from the shared cache
    (keyword-classified, so no TAMU key is needed). A hall/period that
    can't be fetched is simply absent; the sample menu is never used for
    suggestions (twin_suggest checks `source == "live"`).

    All six lookups run at once, and Future Me waits only a few seconds
    for them: the cache is prewarmed at startup, so this is normally
    instant, and on a cold cache a slow fetch keeps running in the
    background (shielded) to fill the cache for the next request rather
    than holding up a chat reply."""
    combos = [(hall, period) for hall in DINING_HALLS for period in DINING_PERIODS]
    tasks = [asyncio.ensure_future(_classified_menu(hall, period)) for hall, period in combos]
    for t in tasks:
        _twin_menu_tasks.add(t)
        t.add_done_callback(_twin_menu_task_done)
    out: Dict[str, Dict[str, dict]] = {hall: {} for hall in DINING_HALLS}
    deadline = asyncio.get_running_loop().time() + _TWIN_MENU_WAIT_SECONDS  # one budget for all six
    for (hall, period), task in zip(combos, tasks):
        try:
            remaining = max(0.0, deadline - asyncio.get_running_loop().time())
            out[hall][period] = await asyncio.wait_for(asyncio.shield(task), timeout=remaining)
        except asyncio.TimeoutError:
            logger.info(f"From-your-meals: {hall}/{period} menu not ready yet; continuing without it")
        except Exception as e:  # never let a menu problem break Future Me
            logger.warning(f"From-your-meals menu lookup failed for {hall}/{period}: {e}")
    return out


async def _swap_plan_state(uid: str) -> Dict[str, dict]:
    rows = await db.swap_plans.find({"user_id": uid}).to_list(200)
    return {r["swap_id"]: {"status": r.get("status"), "day": r.get("day")} for r in rows}


# Which engine participants see. "rules" (default): twin_habits + twin_suggest,
# deterministic. "llm": the TAMU AI engine in twin_llm, which names regulars
# from the raw log text and picks among the same vetted swaps and real menu
# items; falls back to rules when the student has no key or the call fails.
# Whenever the AI engine runs (TWIN_ENGINE=llm, or a staff recompute from
# the researcher page) both engines' results are stored side by side in
# db.twin_decisions, so the study team can compare them and converge later.
# The rules engine is always computed; it costs nothing.
TWIN_ENGINES = ("rules", "llm")
TWIN_ENGINE = os.environ.get("TWIN_ENGINE", "rules").strip().lower() or "rules"
if TWIN_ENGINE not in TWIN_ENGINES:
    logger.warning(f"TWIN_ENGINE={TWIN_ENGINE!r} is not one of {TWIN_ENGINES}; using 'rules'")
    TWIN_ENGINE = "rules"
logger.info(f"From-your-meals engine shown to participants: {TWIN_ENGINE}")
_TWIN_LLM_RETRY = timedelta(minutes=5)  # after a failed model call, don't retry on every request


def _twin_note(detected: dict, area: Optional[str], habits: List[dict]) -> Optional[str]:
    if detected["status"] == "learning":
        return twin_habits.learning_line(detected["days_logged"])
    if not area:
        return "Once you've chosen a focus area, I'll match swaps to the meals you log."
    if not habits:
        return "Nothing has come up three times yet. Here's an easy add for your focus area in the meantime."
    return None


def _twin_rules_block(user: dict, detected: dict, area: Optional[str], menus: Dict[str, Dict[str, dict]],
                      plan_state: Dict[str, dict], today: date_cls) -> dict:
    """The rules engine's block: counts of the student's own logged meals,
    a swap from the reviewed table, item names from today's real menu."""
    allergy_terms = user.get("allergy_terms") or []
    is_blocked = lambda item: item_matches_allergy(item, allergy_terms)  # noqa: E731
    setup = twin_suggest.setup_from_profile(user.get("profile") or {})
    suggestions = twin_suggest.build_suggestions(
        area, detected, user.get("profile") or {}, menus, is_blocked,
        plan_state=plan_state, today_iso=today.isoformat()) if area else []
    habits = [{k: h[k] for k in ("food_id", "label", "times", "days", "slots", "top_slot")}
              for h in detected["habits"][:3]]
    return {
        "engine": "rules",
        "status": detected["status"],
        "days_logged": detected["days_logged"],
        "window_days": detected["window_days"],
        "note": _twin_note(detected, area, habits),
        "habits": habits,
        "suggestions": suggestions,
        "setup": {"label": setup["label"], "meal_plan": setup["meal_plan"]},
    }


async def _twin_llm_compute(user: dict, meals: List[dict], detected: dict, area: Optional[str],
                            menus: Dict[str, Dict[str, dict]], today: date_cls) -> dict:
    """The AI engine's model calls, verified into plain data that can be
    cached: {"available", "reason", "regulars": [...], "picks": [...]}.
    Two calls: name the regulars (checked against the cited meals), then
    pick among the swaps this student may be offered and today's real
    menu items (checked again). Nothing here is shown directly — see
    _twin_llm_render, which re-applies every per-student filter on each
    read. See twin_llm for what the model can and can't do."""
    allergy_terms = user.get("allergy_terms") or []
    is_blocked = lambda item: item_matches_allergy(item, allergy_terms)  # noqa: E731
    setup = twin_suggest.setup_from_profile(user.get("profile") or {})
    try:
        tamus_client.resolve_user_key(user)
    except tamus_client.TamusKeyRequiredError:
        return {"available": False, "reason": "no_key", "regulars": [], "picks": []}
    try:
        rows = twin_llm.meal_rows(meals, today)
        regulars: List[dict] = []
        if rows and detected["status"] == "ready":
            raw = await run_llm(user, twin_llm.REGULARS_SYSTEM, twin_llm.regulars_prompt(rows),
                                f"twin-regulars-{user['id']}")
            regulars = twin_llm.verify_regulars(raw, rows, _guardrail_violation_type)
        picks: List[dict] = []
        if area:
            allowed = [sw for sw in twin_suggest.SWAPS if twin_suggest.swap_allowed(sw, area, setup, is_blocked)]
            if allowed:
                raw = await run_llm(user, twin_llm.PICK_SYSTEM,
                                    twin_llm.pick_prompt(area, regulars, setup, allergy_terms, allowed, menus, is_blocked),
                                    f"twin-pick-{user['id']}")
                picks = twin_llm.verify_picks(raw, regulars, {sw["id"]: sw for sw in allowed}, _guardrail_violation_type)
    except tamus_client.TamusKeyRequiredError:
        return {"available": False, "reason": "no_key", "regulars": [], "picks": []}
    except Exception as e:
        logger.warning(f"From-your-meals AI engine failed for user {user['id']}: {e}")
        return {"available": False, "reason": "error", "regulars": [], "picks": []}
    return {"available": True, "reason": None, "regulars": regulars, "picks": picks,
            "saw_menu": any(m.get("source") == "live" for h in menus.values() for m in h.values())}


def _twin_llm_render(user: dict, computed: dict, detected: dict, area: Optional[str], rules: dict,
                     menus: Dict[str, Dict[str, dict]], plan_state: Dict[str, dict], today: date_cls) -> dict:
    """The AI engine's block as of NOW: the cached, verified model output
    re-filtered against the student's current allergies, setup, dislikes
    and taps, with menu items re-resolved against today's menus. When the
    model's picks all fail those checks, the rules engine's suggestions
    stand in (the card is never empty with a focus area set)."""
    allergy_terms = user.get("allergy_terms") or []
    is_blocked = lambda item: item_matches_allergy(item, allergy_terms)  # noqa: E731
    setup = twin_suggest.setup_from_profile(user.get("profile") or {})
    regulars = computed.get("regulars") or []
    suggestions: List[dict] = []
    if area:
        suggestions = twin_llm.render(computed.get("picks") or [], regulars, area, setup, allergy_terms, is_blocked,
                                      menus, _guardrail_violation_type, plan_state, today.isoformat())
        if not suggestions:
            suggestions = rules["suggestions"]
    habits = [{k: h[k] for k in ("food_id", "label", "times", "days", "slots", "top_slot")} for h in regulars[:3]]
    return {
        "engine": "llm",
        "available": True,
        "reason": None,
        "status": detected["status"],
        "days_logged": detected["days_logged"],
        "window_days": detected["window_days"],
        "note": _twin_note(detected, area, habits),
        "habits": habits,
        "suggestions": suggestions,
        "setup": {"label": setup["label"], "meal_plan": setup["meal_plan"]},
    }


def _twin_llm_key(area: Optional[str], detected: dict, saw_menu: bool) -> str:
    """The model output is reused until its inputs change: a new meal log,
    a new day, a new focus area, or the menus becoming available."""
    return f"{area}|{detected['meals_considered']}|{detected['days_logged']}|{'menu' if saw_menu else 'nomenu'}"


async def _from_your_meals(user: dict, engine: Optional[str] = None, force_llm: bool = False) -> dict:
    """The block Future Me's home shows and the Coach reads, from the
    engine TWIN_ENGINE names (or `engine`), with both engines' results
    recorded in db.twin_decisions for comparison whenever the AI engine
    ran. The AI engine's verified model output is cached per day until the
    student's logs, focus area or the menus change (`force_llm` recomputes
    it); everything safety-relevant is re-applied on every read."""
    engine = engine if engine in TWIN_ENGINES else TWIN_ENGINE
    today = study_today()
    start = study_day_start_utc_iso(today - timedelta(days=twin_habits.HABIT_WINDOW_DAYS - 1))
    meals = await db.meals.find({"user_id": user["id"], "created_at": {"$gte": start}}).to_list(1000)
    detected = twin_habits.detect_habits(meals, today)
    area = user.get("focus_area") if user.get("focus_area") in focus_areas.BY_ID else None
    menus = await _twin_menus_today() if area else {}
    plan_state = await _swap_plan_state(user["id"])
    live = any(m.get("source") == "live" for h in menus.values() for m in h.values())
    menu_source = "live" if live else ("sample" if any(h for h in menus.values()) else "none")

    rules = _twin_rules_block(user, detected, area, menus, plan_state, today)
    key = {"user_id": user["id"], "day": today.isoformat()}
    row = await db.twin_decisions.find_one(key) or {}
    llm_key = _twin_llm_key(area, detected, live)
    computed = row.get("llm_computed") if row.get("llm_key") == llm_key and not force_llm else None
    if computed is not None and not computed.get("available"):
        # A failed or key-less run is kept only briefly, so the student
        # isn't pinned to rules all day by one bad call or a key added later.
        tried_at = row.get("llm_computed_at") or ""
        if computed.get("reason") == "no_key" or tried_at < (now_utc() - _TWIN_LLM_RETRY).isoformat():
            computed = None
    if computed is None and (engine == "llm" or force_llm):
        computed = await _twin_llm_compute(user, meals, detected, area, menus, today)
    llm_block = (_twin_llm_render(user, computed, detected, area, rules, menus, plan_state, today)
                 if computed and computed.get("available") else
                 ({"engine": "llm", "available": False, "reason": computed.get("reason"), "habits": [], "suggestions": []}
                  if computed else None))
    shown_engine = "llm" if engine == "llm" and llm_block and llm_block.get("available") else "rules"
    record = {**key, "rules": rules, "engine_setting": engine, "shown": shown_engine, "focus_area": area,
              "menu_source": menu_source, "updated_at": now_utc().isoformat()}
    if computed is not None:  # a fresh or still-valid AI run; an older one is left in place for comparison
        record.update({"llm": llm_block, "llm_computed": computed, "llm_key": llm_key,
                       "llm_computed_at": row.get("llm_computed_at") if row.get("llm_key") == llm_key and not force_llm
                       else now_utc().isoformat()})
    if row:
        await db.twin_decisions.update_one(key, {"$set": record})
    else:
        try:
            await db.twin_decisions.insert_one({"id": new_id(), **record})
        except DuplicateKeyError:
            await db.twin_decisions.update_one(key, {"$set": record})
    block = llm_block if shown_engine == "llm" else rules
    note = "AI engine unavailable right now; rules shown" if engine == "llm" and shown_engine == "rules" else None
    return {**block, "menu_source": menu_source, "engine_note": note}


@api.get("/future-me/from-your-meals")
async def future_me_from_your_meals(user: dict = Depends(current_user)):
    return await _from_your_meals(user)


SWAP_PLAN_STATUSES = ("trying", "tried", "dismissed")


class SwapPlanIn(BaseModel):
    swap_id: str = Field(min_length=1, max_length=80)

    @field_validator("swap_id")
    @classmethod
    def _known(cls, v: str) -> str:
        if v not in twin_suggest.SWAPS_BY_ID:
            raise ValueError("Unknown swap")
        return v


def _swap_allowed_for(user: dict, swap_id: str) -> bool:
    """May this swap be shown to, or saved for, this student? Their focus
    area, their setup, and their allergy terms and dislikes all have to
    allow it. Re-checked on every write, so a swap id the model (or a
    client) names that was never offered to this student is refused —
    being a valid id in the table is not enough."""
    swap = twin_suggest.SWAPS_BY_ID.get(swap_id)
    if not swap:
        return False
    area = user.get("focus_area") if user.get("focus_area") in focus_areas.BY_ID else None
    allergy_terms = user.get("allergy_terms") or []
    setup = twin_suggest.setup_from_profile(user.get("profile") or {})
    return twin_suggest.swap_allowed(swap, area, setup, lambda item: item_matches_allergy(item, allergy_terms))


async def _internal_set_swap_status(user: dict, swap_id: str, status: str) -> dict:
    """Shared write path for the Future Me card's buttons and the Coach's
    confirmed try_swap action: one row per student and swap, latest status
    wins. Only ever writes the authenticated student's own row, and only
    for a swap this student may actually be offered (_swap_allowed_for)."""
    if not _swap_allowed_for(user, swap_id):
        raise HTTPException(404, "That swap isn't available for you.")
    if status not in SWAP_PLAN_STATUSES:
        raise HTTPException(422, "Unknown status")
    row = {"user_id": user["id"], "swap_id": swap_id, "status": status,
           "day": study_today().isoformat(), "updated_at": now_utc().isoformat()}
    key = {"user_id": user["id"], "swap_id": swap_id}
    if await db.swap_plans.find_one(key):
        await db.swap_plans.update_one(key, {"$set": row})
    else:
        try:
            await db.swap_plans.insert_one({"id": new_id(), **row})
        except DuplicateKeyError:  # two taps at once: the unique index wins, apply the latest status
            await db.swap_plans.update_one(key, {"$set": row})
    swap = twin_suggest.SWAPS_BY_ID[swap_id]
    return {"swap_id": swap_id, "status": status, "swap_label": swap["swap_label"]}


@api.post("/future-me/swaps/{status}")
async def future_me_set_swap_status(status: Literal["trying", "tried", "dismissed"], body: SwapPlanIn,
                                    user: dict = Depends(current_user)):
    """The card's buttons: "I'll try it" (trying), "I tried it" (tried) and
    "Not for me" (dismissed). Returns the refreshed block."""
    result = await _internal_set_swap_status(user, body.swap_id, status)
    return {**result, "from_your_meals": await _from_your_meals(user)}


# ---- The behavioral twin: diet, activity and sleep in one profile ------------
# The study team's 2026-11 direction: one participant-specific profile across
# the three behavioral components of AHA Life's Essential 8 (never an LE8
# score — this app doesn't compute one), built from (1) ASA24 + meal logs,
# (2) tracker / manual activity and sleep, (3) what the participant tells us,
# and (4) how earlier steps went and why. Patterns are only ever ASKED about
# (twin_patterns); a step is chosen from a reviewed library by readable rules
# and explained (twin_recommend); reasons for "Not for me" / "Didn't fit"
# become constraints every later step respects (twin_profile). The model's
# jobs stay narrow: naming meal regulars (twin_llm, as before) and mapping a
# free-text note onto the fixed reason / circumstance lists.
TWIN_ONLY_REVIEWED = (os.environ.get("TWIN_ONLY_REVIEWED") or "").strip().lower() in {"1", "true", "yes", "on"}
TWIN_SAFETY_PAUSE_DAYS = 14   # after a safety check-in, no new food or exercise steps, no meal questions
_TWIN_FEEDBACK_DAYS = 180
_SWAP_STATUS_FOR = {"trying": "trying", "dismissed": "dismissed", "adopted": "tried", "didnt_fit": "tried",
                    "lapsed": "tried", "tried": "tried"}
_TWIN_STATUS_FOR = {"accept": "trying", "decline": "dismissed", "worked": "adopted", "didnt_fit": "didnt_fit",
                    "still_doing": "adopted", "lapsed": "lapsed"}


async def _twin_upsert(coll, key: dict, doc: dict) -> None:
    """One row per key: update it if it's there, insert it otherwise (a
    double tap that races the unique index just updates)."""
    if await coll.find_one(key):
        await coll.update_one(key, {"$set": doc})
        return
    try:
        await coll.insert_one({"id": new_id(), **key, **doc})
    except DuplicateKeyError:
        await coll.update_one(key, {"$set": doc})


async def _twin_safety_paused(uid: str) -> bool:
    since = (now_utc() - timedelta(days=TWIN_SAFETY_PAUSE_DAYS)).isoformat()
    return bool(await db.safety_checkins.find_one({"user_id": uid, "created_at": {"$gte": since}}))


def _twin_notes(status: Dict[str, str], diet_note: Optional[str], area: Optional[str], paused: bool) -> Dict[str, Optional[str]]:
    notes = {
        "diet": diet_note if area else "Once you've chosen a focus area, I'll match food steps to your meals.",
        "activity": {
            "no_data": "Connect a tracker in Settings, or log movement on a few days, and I'll look for patterns in your week.",
            "learning": "A few more days of movement and I'll look for patterns in your week.",
        }.get(status["activity"]),
        "sleep": {
            "no_data": "Connect a tracker, or add bed and wake times when you log sleep, and I'll learn your sleep routine.",
            "learning": "A few more nights and I'll look for patterns in your sleep.",
        }.get(status["sleep"]),
    }
    if paused:
        notes["paused"] = "Taking it easy for a bit: I'll hold off on new food and movement steps for now."
    return notes


async def _twin_compute(user: dict, fym: Optional[dict] = None, record: bool = True) -> dict:
    """Everything the twin knows about this participant right now, and what
    it would show them. Recomputed on every read from their own records;
    `record` stores today's snapshot for evaluation (db.twin_snapshots)."""
    uid = user["id"]
    today = study_today()
    start = study_day_start_utc_iso(today - timedelta(days=twin_patterns.WINDOW_DAYS + 1))
    q = {"user_id": uid, "created_at": {"$gte": start}}
    meals = await db.meals.find(q).to_list(1000)
    acts = await db.activities.find(q).to_list(1000)
    sleeps = await db.sleeps.find(q).to_list(500)
    facts = await db.twin_facts.find({"user_id": uid}).to_list(500)
    twin_plans = await db.twin_plans.find({"user_id": uid}).to_list(500)
    swap_plans = await db.swap_plans.find({"user_id": uid}).to_list(200)
    since_fb = (now_utc() - timedelta(days=_TWIN_FEEDBACK_DAYS)).isoformat()
    feedback = await db.twin_events.find({"user_id": uid, "kind": "step", "created_at": {"$gte": since_fb}}).to_list(1000)
    paused = await _twin_safety_paused(uid)
    area = user.get("focus_area") if user.get("focus_area") in focus_areas.BY_ID else None
    profile = user.get("profile") or {}
    allergy_terms = user.get("allergy_terms") or []
    is_blocked = lambda item: item_matches_allergy(item, allergy_terms)  # noqa: E731
    setup = twin_suggest.setup_from_profile(profile)
    fym = fym if fym is not None else await _from_your_meals(user)
    plans = twin_profile.reconcile_plans(twin_plans, swap_plans)
    stated = {f["key"].split(".", 1)[1] for f in facts if f.get("kind") == "circumstance" and f.get("status") == "stated"}
    detected = twin_patterns.detect_all(meals, acts, sleeps, today, stated, paused=paused)

    # Food swaps for every regular (not only the top two the older card
    # shows), from the same reviewed table, menus and per-student checks.
    swaps: List[dict] = []
    if area and not paused:
        menus = await _twin_menus_today()
        # "lapsed" (it worked, then stopped) is offered again rather than rested
        swap_state = {rid: {"status": None if p.get("status") == "lapsed" else _SWAP_STATUS_FOR.get(p.get("status"),
                                                                                                  p.get("status")),
                            "day": p.get("day")}
                      for rid, p in plans.items() if rid in twin_suggest.SWAPS_BY_ID}
        rules_detected = twin_habits.detect_habits(meals, today)
        swaps = twin_suggest.build_suggestions(area, rules_detected, profile, menus, is_blocked, plan_state=swap_state,
                                               today_iso=today.isoformat(), limit=12)
        if fym.get("engine") == "llm":  # the AI engine's picks (own-words regulars, a 'why') take precedence
            llm_ids = {s["id"] for s in fym.get("suggestions") or []}
            swaps = list(fym.get("suggestions") or []) + [s for s in swaps if s["id"] not in llm_ids]
    regular_candidates: List[dict] = []
    seen_regulars = set()
    for s in swaps:
        if s.get("habit"):
            key = twin_patterns.regular_key(s["habit"])
            if key not in seen_regulars:
                seen_regulars.add(key)
                regular_candidates += twin_patterns.regular_patterns([s["habit"]], {key: s.get("evidence") or ""})
    patterns = detected["patterns"] + regular_candidates
    labels = {f["key"]: f.get("label") for f in facts if f.get("kind") == "pattern" and f.get("label")}
    labels.update({p["key"]: p["label"] for p in patterns})
    state = twin_profile.build_state(
        facts=facts, profile=profile, meals=meals, focus_area=area, setup=setup, plans=plans, feedback=feedback,
        detected_keys={p["key"] for p in patterns}, paused=paused, today=today, pattern_labels=labels,
        only_reviewed=TWIN_ONLY_REVIEWED)

    steps: Dict[str, dict] = {}
    for s in swaps:
        steps[s["id"]] = twin_recommend.swap_item(s, twin_patterns.regular_key(s["habit"]) if s.get("habit") else None)
    for rid, p in plans.items():  # a swap they're trying stays pinned even if their focus area moved on
        if p.get("status") == "trying" and rid in twin_suggest.SWAPS_BY_ID and rid not in steps:
            steps[rid] = twin_recommend.swap_item({"id": rid}, None)
    for item in twin_recommend.ITEMS:
        steps[item["id"]] = item
    selection = twin_recommend.select(list(steps.values()), state, is_blocked)
    grocery = await db.twin_grocery.find({"user_id": uid}).sort("created_at", 1).to_list(100)
    view = {
        "status": {"diet": ("needs_focus" if not area else fym.get("status")), **detected["status"]},
        "notes": _twin_notes(detected["status"], fym.get("note"), area, paused),
        "questions": twin_profile.questions(patterns, facts, today),
        "recommendations": selection["recommendations"],
        "reinforcing": twin_recommend.reinforcing(state, today.isoformat()),
        "learned": twin_profile.learned(state, facts, profile),
        "offer_domains": [d for d in ("activity", "sleep") if not state["domains_on"][d]],
        "grocery_list": [{"id": g["id"], "text": g["text"], "done": bool(g.get("done"))} for g in grocery],
        "reasons": [{"id": k, "label": v["label"]} for k, v in twin_profile.REASONS.items()],
        "paused": paused,
    }
    if record:
        await _twin_record_snapshot(uid, today, view, state, steps, selection)
    return {"view": view, "state": state, "steps": steps, "patterns": patterns, "selection": selection, "fym": fym,
            "is_blocked": is_blocked}


async def _twin_record_snapshot(uid: str, today: date_cls, view: dict, state: dict, steps: Dict[str, dict],
                                selection: dict) -> None:
    """Today's questions and steps with the factors that chose each and any
    stated constraint a shown step goes against — what the researcher page
    evaluates. Staff ratings on the same day's row are kept."""
    recs = []
    for r in view["recommendations"]:
        item = steps.get(r["id"]) or twin_recommend.lookup(r["id"]) or {}
        recs.append({"id": r["id"], "status": r.get("status"), "domains": r["domains"], "type": r["type"],
                     "title": r["title"], "why": r.get("why"), "factors": selection["factors"].get(r["id"], []),
                     "patterns": (item.get("targets") or {}).get("patterns") or [],
                     "violations": twin_recommend.constraint_violations(item, state) if item else []})
    doc = {"questions": [q["key"] for q in view["questions"]], "recommendations": recs,
           "reinforcing": [r["id"] for r in view["reinforcing"]], "constraints": sorted(state["constraints"]),
           # pairs, not a dict: pattern keys contain dots, which Mongo field names shouldn't
           "stated": sorted(state["stated"]), "confirmed": sorted(state["confirmed"].items()), "contexts": state["contexts"],
           "domains_on": state["domains_on"], "paused": state["paused"], "updated_at": now_utc().isoformat()}
    try:
        await _twin_upsert(db.twin_snapshots, {"user_id": uid, "day": today.isoformat()}, doc)
    except Exception as e:  # evaluation bookkeeping must never break the participant's screen
        logger.warning(f"Twin snapshot not stored for {uid}: {e}")


async def _twin_interpret(user: dict, note: str, allowed: Dict[str, str], rules) -> tuple:
    """Codes for a free-text note: keywords first; TAMU AI only when no
    keyword matched (and only codes from `allowed` are kept). Returns
    (codes, how) where how is 'rules', 'llm' or 'none'."""
    if not note or not allowed:
        return [], "none"
    codes = rules(note, list(allowed))
    if codes:
        return codes, "rules"
    try:
        raw = await run_llm(user, twin_profile.INTERPRET_SYSTEM, twin_profile.interpret_prompt(note, allowed),
                            f"twin-interpret-{user['id']}")
        codes = twin_profile.verify_interpretation(raw, list(allowed))
        return codes, ("llm" if codes else "none")
    except Exception:  # no key, or the call failed: the note is still stored
        return [], "none"


async def twin_view(user: dict) -> dict:
    return (await _twin_compute(user))["view"]


@api.get("/twin")
async def get_twin(user: dict = Depends(current_user)):
    """The participant's behavioral twin: questions about possible
    patterns, one or two small steps with why, steps to keep going, what it
    has learned about them (each removable), and their grocery list."""
    return await twin_view(user)


class TwinAnswerIn(BaseModel):
    key: str = Field(min_length=1, max_length=80)
    answer: Literal["yes", "sometimes", "no"]
    circumstances: List[str] = Field(default_factory=list, max_length=8)
    note: Optional[str] = Field(default=None, max_length=twin_profile.NOTE_MAX)


@api.post("/twin/questions/answer")
@limiter.limit("30/minute")
async def answer_twin_question(request: Request, body: TwinAnswerIn, user: dict = Depends(current_user)):
    """Yes / Sometimes / Not really to a pattern the twin noticed, plus what's
    behind it. Only a pattern the twin is actually asking about (or one
    they answered before) can be answered."""
    comp = await _twin_compute(user, record=False)
    pattern = next((p for p in comp["patterns"] if p["key"] == body.key), None)
    fact = await db.twin_facts.find_one({"user_id": user["id"], "key": body.key})
    if pattern is None and not (fact and fact.get("kind") == "pattern"):
        raise HTTPException(404, "That question isn't open any more.")
    options = (pattern or {}).get("circumstances") or (fact or {}).get("circumstance_options") or []
    bad = [c for c in body.circumstances if c not in options]
    if bad:
        raise HTTPException(422, f"Unknown circumstance for this question: {bad}")
    note = twin_profile.clean_note(body.note)
    extra, how = await _twin_interpret(
        user, note, {c: twin_patterns.CIRCUMSTANCES[c]["label"] for c in options if c != "other"},
        twin_profile.interpret_circumstance_note) if body.answer != "no" else ([], "none")
    circs = list(dict.fromkeys([*body.circumstances, *extra]))
    today = study_today().isoformat()
    status = {"yes": "confirmed", "sometimes": "sometimes", "no": "rejected"}[body.answer]
    src = pattern or fact
    await _twin_upsert(db.twin_facts, {"user_id": user["id"], "key": body.key}, {
        "kind": "pattern", "domain": src.get("domain"), "label": src.get("label"), "question": src.get("question"),
        "evidence": src.get("evidence"), "detail": src.get("detail") or {}, "circumstance_options": options,
        "status": status, "answer": body.answer, "circumstances": circs, "note": note or None,
        "source": "participant", "answered_day": today, "updated_at": now_utc().isoformat()})
    for c in circs:
        if c == "other" or twin_patterns.CIRCUMSTANCES[c].get("scope") == "item":
            continue  # "I like it" is about that one food; it stays on the pattern's own fact
        await _twin_upsert(db.twin_facts, {"user_id": user["id"], "key": f"circ.{c}"}, {
            "kind": "circumstance", "status": "stated", "source": "participant", "via": body.key,
            "last_day": today, "updated_at": now_utc().isoformat()})
    await db.twin_events.insert_one({
        "id": new_id(), "user_id": user["id"], "kind": "answer", "key": body.key, "domain": src.get("domain"),
        "answer": body.answer, "circumstances": circs, "note": note or None, "interpreted_by": how,
        "day": today, "created_at": now_utc().isoformat()})
    return {"key": body.key, "status": status, "twin": await twin_view(user)}


class TwinStepIn(BaseModel):
    rec_id: str = Field(min_length=1, max_length=80)
    response: Literal["accept", "decline", "worked", "didnt_fit", "still_doing", "lapsed"] = "accept"
    reasons: List[str] = Field(default_factory=list, max_length=6)
    note: Optional[str] = Field(default=None, max_length=twin_profile.NOTE_MAX)
    when: Optional[str] = Field(default=None, max_length=40)
    coping: Optional[str] = Field(default=None, max_length=40)

    @field_validator("rec_id")
    @classmethod
    def _known(cls, v: str) -> str:
        if not twin_recommend.known_step(v):
            raise ValueError("Unknown step")
        return v

    @field_validator("reasons")
    @classmethod
    def _reasons(cls, v: List[str]) -> List[str]:
        bad = [r for r in v if r not in twin_profile.REASONS]
        if bad:
            raise ValueError(f"Unknown reasons: {bad}")
        return list(dict.fromkeys(v))


def _twin_step_offered(comp: dict, rec_id: str) -> bool:
    """Is this step one the twin would show this participant now — on their
    card, or eligible as a new step? The authorization check behind accepting
    a step (from the card or the Coach), so an id that exists in the library
    but was never offered to this student can't be saved for them."""
    if any(r["id"] == rec_id for r in comp["view"]["recommendations"]):
        return True
    item = comp["steps"].get(rec_id)
    return bool(item) and twin_recommend.eligible(item, comp["state"], comp["is_blocked"])[0]


def _twin_learned_constraints(item: dict, reasons: List[str], state: dict) -> List[str]:
    out = []
    for r in reasons:
        c = twin_profile.REASONS[r]["constraint"]
        if c is None:
            continue
        if c == "availability":
            mine = [x for x in state.get("contexts") or [] if x not in ("campus", "anywhere")]
            ctx = next((x for x in item.get("contexts") or [] if x in mine), None)
            if ctx is None and item.get("origin") == "swap" and item.get("on_menu_today"):
                ctx = "dining_hall"
            if ctx is None:
                ctx = next((x for x in item.get("contexts") or [] if x not in ("anywhere", "campus")), None)
            if ctx:
                out.append(f"availability:{ctx}")
        elif c == "not_into":
            tags = [t for t in item.get("tags") or [] if t != "breakfast_push"]
            out += [f"not_into:{t}" for t in tags] or [f"not_into:#{item['id']}"]
        else:
            out.append(c)
    return list(dict.fromkeys(out))


async def _internal_twin_respond(user: dict, body: TwinStepIn) -> dict:
    """Shared write path for the twin card's buttons and the Coach's
    confirmed try_step: the step's status, what the participant said and
    why, and what the twin learns from it. Only ever the authenticated
    participant's own rows."""
    comp = await _twin_compute(user, record=False)
    item = comp["steps"].get(body.rec_id) or twin_recommend.lookup(body.rec_id)
    plan = comp["state"]["plans"].get(body.rec_id) or {}
    shown = any(r["id"] == body.rec_id for r in comp["view"]["recommendations"])
    reinforcing = any(r["id"] == body.rec_id for r in comp["view"]["reinforcing"])
    if body.response == "accept":
        allowed = _twin_step_offered(comp, body.rec_id) or plan.get("status") in ("trying", "lapsed")
    elif body.response == "decline":
        allowed = shown or bool(plan)
    else:
        allowed = shown or reinforcing or plan.get("status") in ("trying", "tried", "adopted", "lapsed")
    if not item or not allowed:
        raise HTTPException(404, "That step isn't available for you.")
    if body.when and body.when not in (item.get("when_options") or []):
        raise HTTPException(422, "Pick one of the times offered for this step.")
    if body.coping and body.coping not in twin_recommend.CONSTRAINTS:
        raise HTTPException(422, "Unknown coping plan.")
    note = twin_profile.clean_note(body.note)
    reasons = list(body.reasons)
    how = "none"
    if note and body.response in ("decline", "didnt_fit", "lapsed"):
        extra, how = await _twin_interpret(
            user, note, {k: v["label"] for k, v in twin_profile.REASONS.items() if k != "other"},
            twin_profile.interpret_reason_note)
        reasons = list(dict.fromkeys([*reasons, *extra]))
    status = _TWIN_STATUS_FOR[body.response]
    if body.response == "decline" and "already_do" in reasons:
        status = "adopted"  # nothing to change: reinforce what they already do
    today = study_today().isoformat()
    row = {"status": status, "day": today, "updated_at": now_utc().isoformat(),
           "when": body.when or plan.get("when"), "coping": body.coping or plan.get("coping"),
           "checked": today if body.response in ("still_doing", "worked") else plan.get("checked")}
    await _twin_upsert(db.twin_plans, {"user_id": user["id"], "rec_id": body.rec_id}, row)
    if body.rec_id in twin_suggest.SWAPS_BY_ID:  # keep the From-your-meals card and the Coach's try_swap in step
        await _twin_upsert(db.swap_plans, {"user_id": user["id"], "swap_id": body.rec_id},
                           {"status": _SWAP_STATUS_FOR[status], "day": today, "updated_at": row["updated_at"]})
    learned = _twin_learned_constraints(item, reasons, comp["state"]) if body.response in ("decline", "didnt_fit", "lapsed") else []
    for c in learned:
        prev = await db.twin_facts.find_one({"user_id": user["id"], "key": f"constraint.{c}"}) or {}
        await _twin_upsert(db.twin_facts, {"user_id": user["id"], "key": f"constraint.{c}"}, {
            "kind": "constraint", "status": "stated", "source": "feedback", "via": body.rec_id,
            "count": int(prev.get("count") or 0) + 1, "last_day": today, "updated_at": now_utc().isoformat()})
    await db.twin_events.insert_one({
        "id": new_id(), "user_id": user["id"], "kind": "step", "rec_id": body.rec_id,
        "origin": item.get("origin", "library"), "domains": item["domains"], "type": item["type"], "bct": item["bct"],
        "patterns": (item.get("targets") or {}).get("patterns") or [], "response": body.response, "reasons": reasons,
        "note": note or None, "interpreted_by": how, "status": status, "learned": learned, "when": body.when,
        "day": today, "created_at": now_utc().isoformat()})
    return {"rec_id": body.rec_id, "status": status, "title": item["title"], "learned": learned}


@api.post("/twin/steps/respond")
@limiter.limit("30/minute")
async def respond_to_twin_step(request: Request, body: TwinStepIn, user: dict = Depends(current_user)):
    """"I'll try it" (accept), "Not for me" (decline, with reasons), "It's
    working" (worked), "Didn't fit" (didnt_fit, with reasons), and the
    later check-in on a step that worked (still_doing / lapsed)."""
    result = await _internal_twin_respond(user, body)
    return {**result, "twin": await twin_view(user)}


class TwinDomainIn(BaseModel):
    domain: Literal["activity", "sleep"]
    on: bool = True


@api.post("/twin/domains")
async def set_twin_domain(body: TwinDomainIn, user: dict = Depends(current_user)):
    """'Want help with movement / sleep too?' The twin offers general steps
    in a domain only once the participant asks for them (or confirms a
    pattern there) — it never decides on its own that they need them."""
    today = study_today().isoformat()
    await _twin_upsert(db.twin_facts, {"user_id": user["id"], "key": f"goal.{body.domain}"}, {
        "kind": "goal", "status": "stated" if body.on else "removed", "source": "participant",
        "last_day": today, "updated_at": now_utc().isoformat()})
    await db.twin_events.insert_one({"id": new_id(), "user_id": user["id"], "kind": "domain", "key": body.domain,
                                     "on": body.on, "day": today, "created_at": now_utc().isoformat()})
    return {"twin": await twin_view(user)}


class TwinForgetIn(BaseModel):
    key: str = Field(min_length=1, max_length=120)


@api.post("/twin/learned/remove")
async def remove_twin_learned(body: TwinForgetIn, user: dict = Depends(current_user)):
    """'That's not right': removes one line from What I've learned. A
    confirmed pattern isn't asked about again for a while; a fact from the
    onboarding profile stays out until they put it back in their profile."""
    comp = await _twin_compute(user, record=False)
    if not any(l["key"] == body.key for l in comp["view"]["learned"]):
        raise HTTPException(404, "That isn't in what I've learned.")
    today = study_today().isoformat()
    kind = body.key.split(".", 1)[0]
    kind = {"circ": "circumstance", "constraint": "constraint", "goal": "goal", "context": "context"}.get(kind, "pattern")
    await _twin_upsert(db.twin_facts, {"user_id": user["id"], "key": body.key}, {
        "kind": kind, "status": "removed", "source": "participant", "answered_day": today, "last_day": today,
        "updated_at": now_utc().isoformat()})
    await db.twin_events.insert_one({"id": new_id(), "user_id": user["id"], "kind": "remove", "key": body.key,
                                     "day": today, "created_at": now_utc().isoformat()})
    return {"twin": await twin_view(user)}


class GroceryAddIn(BaseModel):
    rec_id: Optional[str] = Field(default=None, max_length=80)
    text: Optional[str] = Field(default=None, min_length=1, max_length=80)


class GroceryPatchIn(BaseModel):
    done: bool


@api.get("/twin/grocery")
async def get_twin_grocery(user: dict = Depends(current_user)):
    rows = await db.twin_grocery.find({"user_id": user["id"]}).sort("created_at", 1).to_list(100)
    return {"items": [{"id": g["id"], "text": g["text"], "done": bool(g.get("done")), "rec_id": g.get("rec_id")}
                      for g in rows]}


@api.post("/twin/grocery")
async def add_twin_grocery(body: GroceryAddIn, user: dict = Depends(current_user)):
    """Adds a step's grocery items (the server takes them from the reviewed
    library, never from the client) or one item the participant typed."""
    if bool(body.rec_id) == bool(body.text):
        raise HTTPException(422, "Send a step or one item.")
    if body.rec_id:
        item = twin_recommend.lookup(body.rec_id)
        if not item or not item.get("grocery"):
            raise HTTPException(404, "That step has nothing for a grocery list.")
        texts = list(item["grocery"])
    else:
        texts = [re.sub(r"[\x00-\x1f\x7f]", " ", body.text).strip()]
    rows = await db.twin_grocery.find({"user_id": user["id"]}).to_list(100)
    have = {g["text"].lower() for g in rows if not g.get("done")}
    if len(rows) + len(texts) > 100:
        raise HTTPException(400, "Your list is full. Clear some items first.")
    added = []
    for t in texts:
        if t and t.lower() not in have:
            doc = {"id": new_id(), "user_id": user["id"], "text": t, "rec_id": body.rec_id, "done": False,
                   "created_at": now_utc().isoformat()}
            await db.twin_grocery.insert_one(dict(doc))
            have.add(t.lower())
            added.append(t)
    return {"added": added, **(await get_twin_grocery(user))}


@api.patch("/twin/grocery/{item_id}")
async def patch_twin_grocery(item_id: str, body: GroceryPatchIn, user: dict = Depends(current_user)):
    key = {"id": item_id, "user_id": user["id"]}
    if not await db.twin_grocery.find_one(key):
        raise HTTPException(404, "Not on your list.")
    await db.twin_grocery.update_one(key, {"$set": {"done": body.done}})
    return await get_twin_grocery(user)


@api.delete("/twin/grocery/{item_id}")
async def delete_twin_grocery(item_id: str, user: dict = Depends(current_user)):
    key = {"id": item_id, "user_id": user["id"]}
    if not await db.twin_grocery.find_one(key):
        raise HTTPException(404, "Not on your list.")
    await db.twin_grocery.delete_one(key)
    return await get_twin_grocery(user)


@api.get("/future-me")
async def future_me_home(tz: Optional[str] = None, user: dict = Depends(current_user)):
    # `tz` is accepted and ignored so older app versions don't 422. Every
    # day/week calc runs in the study TZ now — see `study_today()`.
    del tz
    week = await _days_logged_this_week(user["id"])
    food = await domain_food(user)
    rest = await domain_rest(user)
    focus_ids = focus_areas.components_of(user.get("focus_area")) if food.get("focus_area") else []
    twin = await _twin_compute(user)
    return {
        "week_line": future_me.week_line(week["any"]),
        # Kept for older app versions; the behavioral twin below includes these swaps.
        "from_your_meals": twin["fym"],
        "twin": twin["view"],
        # Three separate domains — never combined into one score. Only labels
        # and logged counts; no HEI score or engine value is ever returned.
        "eat": {
            "has_assessment": food.get("has_assessment", False),
            "focus_area": ({"id": food["focus_area"]["id"], "label": food["focus_area"]["label"]}
                           if food.get("focus_area") else None),
            "strengths": [{"id": f["id"], "label": f["label"]} for f in food.get("strengths", [])],
            "days_logged": week["eat"], "meals_logged": week["meals"],
        },
        "move": {"days_logged": week["move"], "minutes": week["move_minutes"]},
        "sleep": {"days_logged": week["rest"], "usual_hours": rest.get("avg_sleep_hours")},
        "scenarios": future_me.scenarios(focus_ids, food.get("has_assessment", False)),
        "checkin": await _next_checkin_info(user),
        "disclaimer": DISCLAIMER,
    }


class WhatIfIn(BaseModel):
    scenario_id: str = Field(min_length=1, max_length=60)


@api.post("/future-me/what-if")
@limiter.limit("20/minute")
async def future_me_what_if(request: Request, body: WhatIfIn, user: dict = Depends(current_user)):
    food = await domain_food(user)
    focus_ids = focus_areas.components_of(user.get("focus_area")) if food.get("focus_area") else []
    scenario = next((sc for sc in future_me.scenarios(focus_ids, food.get("has_assessment", False))
                     if sc["id"] == body.scenario_id), None)
    if not scenario:
        raise HTTPException(404, "That scenario isn't available.")
    if scenario["component_id"]:
        cid = scenario["component_id"]
        assessment = await _latest_assessment(user["id"])
        score = (assessment or {}).get("components", {}).get(cid)
        if score is None:
            raise HTTPException(404, "That scenario isn't available.")
        result = simulate_scenario(cid, score, scenario["title"].lower())  # internal only
        text = future_me.direction_text(scenario["title"], HEI2020_BY_ID[cid]["label"], result["moves_toward_alignment"])
    else:
        text = future_me.DOMAIN_PRESETS[scenario["id"]]["direction"]

    phrased_by = "engine"
    try:
        reworded = await run_llm(
            user,
            "You are Future Me, the student's future self, speaking warmly in the first person. Reword the "
            "sentence you're given in at most two short sentences. Keep exactly the same direction and meaning. "
            "Do not add facts. Never use any numbers, scores, percentages, calories, grams or weight. "
            "Reply with the reworded text only.",
            text, f"future-me-{user['id']}",
        )
        reworded = (reworded or "").strip().strip('"')
        if future_me.safe_rewording(reworded, _guardrail_violation_type):
            text, phrased_by = reworded, "llm"
        elif reworded and _guardrail_violation_type(reworded):
            await db.guardrail_blocks.insert_one({
                "id": new_id(), "user_id": user["id"], "endpoint": "future-me", "created_at": now_utc().isoformat(),
                "trigger_type": _guardrail_violation_type(reworded),
            })
            await check_guardrail_block_pattern(user["id"])
    except Exception:
        pass  # no key or AI unavailable: the engine's own direction text stands
    return {"scenario_id": scenario["id"], "title": scenario["title"], "text": text, "phrased_by": phrased_by}


# ----------------------------------------------------------------------------
# The Coach — questions and answers from the reviewed knowledge base.
# ----------------------------------------------------------------------------
COACH_HISTORY_TURNS = 10
# Strips a SOURCE: line anywhere in the model's reply — not just when
# anchored at the end. The old anchor-at-end regex missed cases where the
# model's own prose referenced the citation inline, and left "SOURCE: …"
# visible to the student. The id extraction still prefers the LAST SOURCE
# line (the one the model intended as the citation).
_SOURCE_LINE_RE = re.compile(
    r"(?mi)^[ \t*_>-]*SOURCE:\s*([A-Za-z0-9_-]+)[ \t*_`.]*$"
)


def _parse_source(text: str) -> tuple:
    """Strip EVERY 'SOURCE: <entry id>' line from the text and return
    (visible_text, last_id_or_None). Any residual SOURCE: fragment is
    further scrubbed so nothing like it reaches the UI."""
    matches = list(_SOURCE_LINE_RE.finditer(text))
    source_id = matches[-1].group(1).lower() if matches else None
    cleaned = _SOURCE_LINE_RE.sub("", text).strip()
    # Belt-and-suspenders: if the model wrote SOURCE: in a format our line
    # regex missed (inline, no newline, trailing comma, etc.) strip the token
    # itself so the student never sees it. The id is already captured above.
    cleaned = re.sub(r"\s*\bSOURCE:\s*[A-Za-z0-9_-]+[\s.,:;)]*", "", cleaned, flags=re.IGNORECASE).strip()
    return cleaned, source_id


async def _coach_history(uid: str, session_id: str) -> List[Dict[str, str]]:
    """The last ~10 messages of this Coach conversation, oldest first."""
    recent = await db.chat_messages.find({"user_id": uid, "session_id": session_id}) \
        .sort("created_at", -1).to_list(COACH_HISTORY_TURNS)
    return [{"role": m["role"], "content": m["text"]} for m in reversed(recent)]


_PERSONAL_PATTERNS = re.compile(
    r"\b(my (goal|focus|progress|plan|week|path|meals?|logs?|habits?|regulars?|breakfasts?|lunch(es)?|dinners?|snacks?)|"
    r"focus on this week|check in|how am i doing|what should i (focus|work) on|this week|i'?m working on|"
    r"what do i (usually|normally|often|always) (eat|have|get|grab)|(what|which) (should|could|can) i (change|switch|swap|try)|"
    r"(based on|from) what i('ve| have)? ?logged|(a|the|this|that|my|one) swap|swap (my|the|this|that|it|out)|"
    r"usually (eat|have|get)|today'?s menu|on the menu (today|at)|dining hall today|"
    r"my (sleep|bedtime|routine|schedule|steps|activity|movement|grocery list|weekdays?|mornings?)|"
    r"(sleep|move|walk) (more|better)|fit in (exercise|activity|movement|a walk)|(a|the|this|that|my) step)\b",
    re.IGNORECASE)


def _is_personal_question(text: str) -> bool:
    """About the student's own goal / week / progress / regular meals —
    answered from their data (THEIR CONTEXT), including the from-your-meals
    swap and today's menu lines."""
    return bool(_PERSONAL_PATTERNS.search(text or ""))


async def _participant_context(user: dict) -> str:
    """What Future Me may say about this student: their focus area, goal and
    plan, this week's program step, and what they logged this week (counts
    of days, never scores or amounts)."""
    area = user.get("focus_area") if user.get("focus_area") in focus_areas.BY_ID else None
    goal = user.get("focus_goal") or {}
    prog = await _program(user)
    nxt = program.next_step(prog)
    unit = next(u for u in prog["units"] if u["week"] == prog["current_week"])
    first, _ = study_week_window(7)
    start = study_day_start_utc_iso(first)
    q = {"user_id": user["id"], "created_at": {"$gte": start}}
    meals = [m for m in await db.meals.find(q).to_list(200) if not m.get("skipped")]
    acts = await db.activities.find(q).to_list(200)
    sleeps = await db.sleeps.find(q).to_list(200)
    days = lambda rows: len({study_day_key(r["created_at"]) for r in rows})
    cats = {c for cid in focus_areas.components_of(area) for c in personal_path.FOCUS_CATEGORIES.get(cid, [])}
    focus_meals = sum(1 for m in meals if cats & set(m.get("categories") or []))
    lines = [
        f"- Focus area: {focus_areas.BY_ID[area]['label']} ({focus_areas.BY_ID[area]['description']})" if area
        else "- Focus area: not chosen yet",
        f"- Their goal: {goal.get('goal') or 'not set'}; their plan: {goal.get('plan') or 'not set'}",
        f"- Program: week {prog['current_week']} of {prog['weeks']}, \"{unit['title']}\" ({unit['summary']})",
        f"- Next step this week: {nxt['label']}: {nxt['title']}" if nxt else "- This week's steps are all done",
        f"- Last 7 days: meals logged on {days(meals)} days, movement on {days(acts)} days, sleep on {days(sleeps)} nights",
    ]
    if cats:
        lines.append(f"- Meals with their focus food in the last 7 days: {focus_meals}")
    # From their own meals: their regulars, and the swap Future Me's home
    # is showing them (with where it is on today's real menu). Deterministic
    # and from the reviewed swap table — the model only rewords it.
    twin = await _twin_compute(user, record=False)
    fym = twin["fym"]
    detected_line = twin_habits.coach_lines({"status": fym["status"], "habits": fym["habits"]})
    if detected_line:
        lines.append(f"- {detected_line} (noticed in logs; treat as a habit only if listed under 'Confirmed with them')")
    else:
        lines.append(f"- Their regular foods: still learning ({fym['note']})")
    lines.extend(twin_llm.coach_lines(fym["suggestions"],
                                      twin_suggest.setup_from_profile(user.get("profile") or {})))
    # The behavioral twin across food, movement and sleep: what they've
    # confirmed or told us, what's only been noticed, the constraints they
    # named, and the steps it suggests (with step_id for a try_step action).
    lines.extend(twin_profile.coach_lines(twin["view"]))
    return "\n".join(lines)


@api.post("/chat")
@limiter.limit("15/minute")
async def chat(request: Request, body: ChatIn, user: dict = Depends(current_user)):
    """Future Me's conversation (study team feedback 5.1-5.2: one name, no
    separate "Coach"). Food and eating questions are answered ONLY from the
    reviewed knowledge base (backend/content/kb), naming the entry used;
    questions about the participant's own focus, goal, week or progress are
    answered ONLY from their own data (_participant_context). Medical,
    weight, calorie and off-topic questions are declined."""
    session_id = body.session_id
    citations: List[dict] = []
    pending_action = None
    # Scope redirects and the "not in my notes" fallback must work with no
    # TAMU AI key, an invalid key, or TAMU AI down — only the LLM branch
    # actually needs the key. The key is resolved inside the else branch
    # below (nutrition team 2026-11-06 Follow-ups item 2 + 2026-11-24
    # review of PR #48).
    scope = coach_kb.scope_check(body.message)
    hits = [] if scope else COACH_KB.retrieve(body.message, k=3)
    personal = not scope and _is_personal_question(body.message)

    if scope:
        answer = coach_kb.DECLINE[scope]
        history = []
    elif not hits and not personal:
        answer = coach_kb.NOT_FOUND
        history = []
    else:
        # LLM branch — now and only now does the key matter. A missing key
        # or a key TAMU AI rejects both surface the same "add your key"
        # prompt (same classification helper); real TAMU AI outages keep
        # the pre-existing "couldn't reach" fallback.
        try:
            tamus_client.resolve_user_key(user)
        except tamus_client.TamusKeyRequiredError:
            return _tamus_key_missing_chat_response()
        history = await _coach_history(user["id"], session_id)
        # The current focus area goes into the prompt so the Coach can tell a
        # change from a no-op, and into _parse_chat_action, which drops a card
        # for the area they already have.
        current_area = user.get("focus_area") if user.get("focus_area") in focus_areas.BY_ID else None
        current_focus_line = (f"{current_area} ({focus_areas.BY_ID[current_area]['label']})"
                              if current_area else "none chosen yet")
        assessment = await _latest_assessment(user["id"])
        focus_candidates = _area_candidates(assessment) if assessment else []
        focus_candidates_line = (
            ", ".join(f"{c['id']} ({c['label']})" for c in focus_candidates) if focus_candidates
            else ("none" if assessment else "none — no results yet, so never propose set_focus_areas")
        )
        all_areas_line = ", ".join(f"{a['id']} ({a['label']})" for a in focus_areas.FOCUS_AREAS)
        entries = "\n\n".join(f"[{h['id']}] {h['title']}\n{h['text']}" for h in hits) or "(none for this question)"
        context = await _participant_context(user)
        boundary_notes_block = "\n   - ".join(coach_kb.BOUNDARY_NOTES) if coach_kb.BOUNDARY_NOTES else ""
        system = (
            "You are Future Me: the student's own future self in the LLHS app, warm and encouraging, talking with a "
            "college student (18-25) about food, everyday eating habits and their own goal. NON-NEGOTIABLE rules:\n"
            "1. ANSWER THE STUDENT'S ACTUAL QUESTION in the FIRST SENTENCE. Then follow with 2-4 practical, specific, "
            "evidence-based tips that fit a college student (dining hall, dorm, little time, budget). Never dodge the "
            "question with a redirect — if you can give a useful answer, give it. Nutrition facts come from the "
            "KNOWLEDGE ENTRIES below; questions about the student's own focus, goal, plan, week, progress, or what "
            "they usually eat are answered ONLY from THEIR CONTEXT below, with one small concrete next step tied to "
            "their goal. When THEIR CONTEXT lists 'A swap that fits', name it, say why it fits, and if an 'On today's "
            "Aggie Dining menu' line is there, say exactly which item, hall and meal. Never invent a menu item or a "
            "swap that isn't listed. If the entries + context genuinely don't cover the question, say plainly 'that's "
            "not something I can answer here — ask the study team' rather than making something up.\n"
            "2. Keep it concise — 3-6 sentences for most answers.\n"
            "3. REFERENCE NUMBERS. You MAY cite the four FDA Daily Values the nutrition team approved on 2026-11-06, "
            "ALWAYS framed as general reference values based on a 2,000-calorie diet — never a personal target: "
            "sodium less than 2,300 mg a day; saturated fat less than 20 g a day; added sugars less than 50 g a day; "
            "dietary fiber at least 28 g a day. You may also use other general public-health guideline numbers from "
            "the KNOWLEDGE ENTRIES (Dietary Guidelines for Americans; FDA label %DV). NEVER give a calorie target "
            "(e.g. '1,800 kcal/day', '500 calories'). The '2,000-calorie diet' frame is the ONE calorie number "
            "permitted, and only as the reference frame for the Daily Values above. If asked for a personal calorie "
            "target, redirect briefly to the study team or a dietitian.\n"
            "4. NEVER mention the student's OWN HEI score, any x/5 or x/10 or x/13 number, body weight, weight loss, "
            "or body size. If asked about weight loss or body weight, answer with one short supportive sentence that "
            "reframes toward habits and suggest the study team. Never label a food 'good' or 'bad'; use 'more X / "
            "less Y / swap A for B' framing.\n"
            "5. No medical advice or diagnosis.\n"
            "6. If the student sounds distressed or restrictive about food, respond with compassion and suggest "
            "talking to someone they trust or campus health services.\n"
            "7. After your answer, write one line 'SOURCE: <entry id>' naming the entry you used (the id in square "
            "brackets), or 'SOURCE: none' if the entries don't answer the question.\n"
            "8. ACTIONS (optional). Nothing is written until the student confirms — ALWAYS phrase action prose as "
            "'Tap Confirm to …', NEVER 'I'll update … now' or 'I've set …'. The following rules are strict:\n"
            "   - Logging meals/activities/sleep: add a final ACTION_JSON line as before.\n"
            "   - FOCUS AREA: a student works on ONE focus area at a time, one of FOCUS AREA IDS. If they ask "
            "to choose or change it, emit ACTION_JSON with the ONE 'area_id' they asked for (it replaces the current "
            "one). If they ask for the area they already have (CURRENT_FOCUS_AREA), say so and do NOT emit "
            "ACTION_JSON. Only suggest areas from FOCUS CANDIDATE IDS; never mention scores.\n"
            "   - SWAPS: if the student says they want to try a swap from THEIR CONTEXT, emit ACTION_JSON type "
            "\"try_swap\" with the swap_id shown there, phrased 'Tap Confirm to add it to your plan'. Only a listed "
            "swap_id; never one you made up.\n"
            "   - STEPS: if they want to try a step listed as 'A small step the twin suggests (step_id=...)', emit "
            "ACTION_JSON type \"try_step\" with that step_id, phrased 'Tap Confirm to add it to your plan'. Only a "
            "listed step_id.\n"
            "ACTION_JSON formats:\n"
            "   {\"type\": \"log_meal\", \"payload\": {\"name\": \"...\", \"categories\": [subset of the category "
            "ids below], \"meal_type\": \"breakfast|lunch|dinner|snack\"}} — or type \"log_activity\" with payload "
            "{\"minutes\": number, \"kind\": \"...\"} — or type \"log_sleep\" with payload {\"hours\": number} — or "
            "type \"set_focus_areas\" with payload {\"area_id\": \"<one focus area id>\"} — or type \"try_swap\" "
            "with payload {\"swap_id\": \"<a swap_id from THEIR CONTEXT>\"} — or type \"try_step\" with payload "
            "{\"rec_id\": \"<a step_id from THEIR CONTEXT>\"}.\n"
            "9. ALLERGIES: never suggest a food containing anything in AVOID.\n"
            "10. THE TWIN: food, movement and sleep are three separate areas — never combine them into a score. Treat "
            "only 'Confirmed with them' and 'They told me' lines as facts about the student. Anything 'Noticed ... "
            "NOT confirmed' is a possibility: you may ask whether it's right, never state it or explain why it "
            "happens. Every suggestion must respect 'What matters to them'. Never link movement to food (no "
            "'earning' or 'working off' food).\n"
            "11. WORDING — NUTRITION TEAM FEEDBACK RULES.\n   "
            + wording_rules.SYSTEM_PROMPT_FRAGMENT.replace("\n", "\n   ")
            + "\n"
            "12. SCOPE — TOPICS FUTURE ME DOES NOT ANSWER (nutrition team "
            "2026-11-06, Follow-ups item 2). If the student asks about any of these, the server has already matched "
            "them to the right redirect text and you will NOT be called. If you ever find yourself about to answer "
            "one anyway, stop: say briefly that it's outside your scope and direct them to the study team or an "
            "appropriate healthcare professional. The topics are: medical conditions (diagnosis, treatment, "
            "condition-specific diets); medications and supplements (use, effectiveness, safety, dosing, "
            "interactions); eating disorders or disordered eating (restriction, purging, body-image concerns); "
            "weight loss and calorie restriction; specialised diets (keto, detox, fasting, other restrictive or "
            "therapeutic diets); urgent health concerns (tell them to call 911).\n"
            + ("   Extra boundaries:\n   - " + boundary_notes_block + "\n" if boundary_notes_block else "")
            + "\n"
            f"AVOID: {', '.join(user.get('allergy_terms') or []) or 'none reported'}\n"
            f"VALID LOGGING CATEGORY IDS: {', '.join(LOG_CATEGORY_IDS)}\n"
            f"FOCUS AREA IDS: {all_areas_line}\n"
            f"CURRENT_FOCUS_AREA: {current_focus_line}\n"
            f"FOCUS CANDIDATE IDS (most room first): {focus_candidates_line}\n\n"
            f"THEIR CONTEXT:\n{context}\n\n"
            f"KNOWLEDGE ENTRIES:\n{entries}"
        )
        try:
            raw = await run_llm(user, system, body.message, f"coach-{user['id']}-{session_id}", history=history)
        except tamus_client.TamusKeyRequiredError:
            # Key disappeared between resolve_user_key and the call —
            # same surface as the start-of-branch check.
            return _tamus_key_missing_chat_response()
        except tamus_client.TAMUSError as e:
            if _is_tamus_key_problem(e):
                return _tamus_key_missing_chat_response()
            logger.error(f"Coach LLM error: {e}")
            raw = None
        except Exception as e:
            logger.error(f"Coach LLM error: {e}")
            raw = None
        if raw is None:
            return {
                "answer": "I couldn't reach TAMU AI just now. Please try again in a moment.",
                "citations": [], "disclaimer": DISCLAIMER, "points_awarded": 0,
                "pending_action": None, "tamus_key_required": False, "error": True,
            }
        answer, pending_action, decline_reason = _parse_chat_action(raw, current_area=current_area)
        if pending_action and pending_action["type"] == "try_swap" \
                and not _swap_allowed_for(user, pending_action["payload"]["swap_id"]):
            # A real swap id, but not one this student may be offered (wrong
            # focus area, needs a stove they don't have, or an allergy or
            # dislike rules it out). The model made it up; no card.
            logger.info(f"Dropped a try_swap for a swap not offered to user {user['id']}")
            pending_action = None
        if pending_action and pending_action["type"] == "try_step" \
                and not _twin_step_offered(await _twin_compute(user, record=False), pending_action["payload"]["rec_id"]):
            logger.info(f"Dropped a try_step for a step not offered to user {user['id']}")
            pending_action = None
        answer, source_id = _parse_source(answer)
        if decline_reason:
            # The model proposed a focus-area action we rejected before it
            # left the server; append the plain-English reason so the student
            # knows why no Confirm button appeared.
            answer = (answer + "\n\n" + decline_reason).strip()
        used = next((h for h in hits if h["id"] == source_id), None)
        if used is None and source_id in twin_suggest.SWAPS_BY_ID:
            sw = twin_suggest.SWAPS_BY_ID[source_id]  # the swap it offered, from the reviewed swap table
            used = {"id": sw["id"], "title": sw["swap_label"], "source": sw["source"]}
        if used is None and source_id != "none" and hits:
            used = hits[0]
        if used:
            citations = [{"id": used["id"], "title": used["title"], "source": used["source"]}]

    # Guardrail on every LLM reply. The kind redirect takes over if the LLM
    # drifted into restrictive advice (skip meals, cut out food groups, very
    # low calories) — nutrition team feedback 2026-11-03.
    #
    # We skip this on the scope-decline branch: ``coach_kb.DECLINE`` texts
    # are reviewed content written by the nutrition team as the response
    # for each scope topic (2026-11-06, Follow-ups item 2). A phrase like
    # "weight loss" in the weight-redirect is intentional — telling the
    # student what LLHS doesn't do — and reworking the guardrail to re-
    # classify its own reviewed copy would force a reword every time the
    # team writes the plain-English topic name. The redirect texts are
    # instead validated once at import time by
    # ``tests/test_future_me_redirects.py`` (wording check + required-cues
    # checks) so drift there is caught in CI, not at runtime.
    violation = _guardrail_violation_type(answer) if not scope else None
    if violation:
        logger.warning(f"Blocked a Coach reply (layer={violation}) for user {user['id']}")
        await db.guardrail_blocks.insert_one({
            "id": new_id(), "user_id": user["id"], "endpoint": "chat", "trigger_type": violation,
            "created_at": now_utc().isoformat(),
        })
        await check_guardrail_block_pattern(user["id"])
        answer, citations, pending_action = _fallback_for_violation(violation, _SAFE_FALLBACK_REPLY), [], None

    stamp = now_utc().isoformat()
    await db.chat_messages.insert_one({"id": new_id(), "user_id": user["id"], "session_id": session_id,
                                       "role": "user", "text": body.message, "created_at": stamp})
    await db.chat_messages.insert_one({"id": new_id(), "user_id": user["id"], "session_id": session_id,
                                       "role": "assistant", "text": answer, "citations": citations,
                                       "created_at": now_utc().isoformat()})
    turns_today = await db.chat_messages.count_documents(
        {"user_id": user["id"], "role": "user", "created_at": {"$gte": _today_start_iso()}}
    )
    awarded = 0
    if turns_today <= DAILY_POINT_CAPS["chat_messages"]:
        await award_points(user["id"], 5)
        awarded = 5
    return {
        "answer": answer, "citations": citations, "disclaimer": DISCLAIMER, "points_awarded": awarded,
        "pending_action": pending_action, "tamus_key_required": False,
    }


@api.post("/chat/confirm-action")
@limiter.limit("20/minute")
async def confirm_chat_action(request: Request, body: ChatActionIn, user: dict = Depends(current_user)):
    """Executes an action the coach proposed and the participant explicitly
    confirmed. Re-validates the payload from scratch (never trusts what the
    client echoes back) and always writes through the same shared helper
    the manual logging screens use — this endpoint can only ever act on the
    authenticated user's own account, never anyone else's.

    On any failure the real exception is logged server-side; the student sees
    a short, non-leaky message. Chat shows "That didn't save." in the UI."""
    try:
        validated = _validate_chat_action_payload(body.type, body.payload)
    except Exception as e:
        logger.warning("confirm-action rejected %s payload (user=%s): %s", body.type, user["id"], e)
        raise HTTPException(422, "That action isn't valid any more. Ask Future Me again.")

    try:
        if body.type == "log_meal":
            result = await _internal_log_meal(user, MealIn(**validated))
        elif body.type == "log_activity":
            result = await _internal_log_activity(user, ActivityIn(**validated))
        elif body.type == "log_sleep":
            result = await _internal_log_sleep(user, SleepIn(**validated))
        elif body.type == "set_focus_areas":
            result = await _internal_set_focus_areas(user, FocusAreasIn(**validated))
        elif body.type == "try_swap":
            result = await _internal_set_swap_status(user, validated["swap_id"], "trying")
        elif body.type == "try_step":
            result = await _internal_twin_respond(user, TwinStepIn(rec_id=validated["rec_id"], response="accept"))
        else:
            raise HTTPException(422, "Unknown action type")
    except HTTPException as e:
        # The internal helper already raised a 4xx with a friendly detail —
        # log the real reason for debugging, keep its wording for the UI.
        logger.warning(
            "confirm-action for %s failed with %s: %s (user=%s)",
            body.type, e.status_code, e.detail, user["id"],
        )
        raise

    return {"type": body.type, "result": result}


# ----------------------------------------------------------------------------
# F4 — Photo meal capture (assisted entry, confidence-gated review)
#
# Voice Logging (record-a-voice-note-to-log-a-meal) has been removed as of
# 2026-09: it only ever worked through Emergent's audio-capable Gemini
# model, and TAMU AI — now the app's sole AI provider — documents no
# audio/speech input anywhere (checked against TAMU IT's own service page
# and the team's reference wrapper, taugroup/TAMU-Chat-AI). Rather than ship
# a mic button with no working backend, it's gone; manual text entry and
# photo capture below both remain and both now run on TAMU. See
# README/PRD for the full record of this decision.
# ----------------------------------------------------------------------------
@api.post("/meals/analyze-photo")
@limiter.limit("15/minute")
async def analyze_photo(request: Request, body: PhotoIn, user: dict = Depends(current_user)):
    import json

    system = (
        "You are a food-recognition assistant for a heart-health app. Identify the foods in the photo and map "
        f"them to this fixed set of categories: {', '.join(c['id'] for c in LIGHTWEIGHT_LOG_CATEGORIES)}. "
        "NEVER estimate calories, weight, or portion size in grams. "
        "Respond ONLY with compact JSON: "
        '{"items": ["..."], "categories": ["subset of the category ids above"], '
        '"confidence": number between 0 and 1, "suggested_name": "short meal name"}. No prose, no markdown.'
    )
    image_b64 = body.image_base64
    if image_b64.strip().startswith("data:") and "," in image_b64:
        image_b64 = image_b64.split(",", 1)[1]

    tamus_key_required = False
    try:
        raw = await llm_vision_call(
            user, system, "Identify the foods and map them to categories in this meal photo. Return JSON only.",
            f"food-{user['id']}", image_b64,
        )
        cleaned = raw.strip().strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        start, end = cleaned.find("{"), cleaned.rfind("}")
        data = json.loads(cleaned[start:end + 1]) if start >= 0 else {}
    except tamus_client.TamusKeyRequiredError:
        tamus_key_required = True
        data = {}
    except Exception as e:
        logger.error(f"Photo analysis error: {e}")
        data = {}

    confidence = float(data.get("confidence", 0.0) or 0.0)
    categories = [c for c in (data.get("categories") or []) if c in LOG_CATEGORY_IDS]
    items_text = " ".join(data.get("items", [])).lower()
    allergy_terms = user.get("allergy_terms", [])
    allergy_flag = any(term in items_text for term in allergy_terms) if allergy_terms else False
    note = (
        "Add your TAMU AI key in Settings to enable photo recognition — you can still fill this in manually."
        if tamus_key_required else
        "Assisted manual entry — please review and confirm. Photo recognition is roughly 2-in-3 accurate."
    )
    return {
        "items": await _guard_list(user, "analyze-photo", data.get("items", [])), "categories": categories,
        "suggested_name": await _guard_text(user, "analyze-photo", data.get("suggested_name"), "Meal"),
        "confidence": confidence,
        "needs_confirmation": confidence < 0.7,
        "allergy_flag": allergy_flag,
        "tamus_key_required": tamus_key_required,
        "note": note,
    }


# ----------------------------------------------------------------------------
# Weekly Story — calm end-of-week recap, computed from real logged data.
# ----------------------------------------------------------------------------
@api.get("/weekly-story")
async def weekly_story(user: dict = Depends(current_user)):
    uid = user["id"]
    first, _ = study_week_window(7)
    week_ago = study_day_start_utc_iso(first)

    meals = await db.meals.find({"user_id": uid, "created_at": {"$gte": week_ago}}).to_list(200)
    activities = await db.activities.find({"user_id": uid, "created_at": {"$gte": week_ago}}).to_list(200)
    sleeps = await db.sleeps.find({"user_id": uid, "created_at": {"$gte": week_ago}}).to_list(200)
    completions = await db.completions.find({"user_id": uid, "created_at": {"$gte": week_ago}}).to_list(200)
    games = await db.game_results.find({"user_id": uid, "created_at": {"$gte": week_ago}}).to_list(200)

    logged_meals = [m for m in meals if not m.get("skipped")]
    balanced_meals = [m for m in logged_meals if meal_has_core_categories(m, min_kinds=1)]
    activity_minutes = sum(a.get("minutes", 0) for a in activities)
    sleep_hours = [s.get("hours", 0) for s in sleeps]
    avg_sleep = round(sum(sleep_hours) / len(sleep_hours), 1) if sleep_hours else None
    wearable_nights = sum(1 for s in sleeps if s.get("source") == "wearable")
    videos_watched = sum(1 for c in completions if c.get("kind") == "video")
    games_played = len(games)
    cohort = await db.users.count_documents(real_participant_filter())

    chapters = [
        {"id": "food", "kicker": "Chapter One", "title": "Food", "stat": f"{len(balanced_meals)} balanced meals",
         "body": (
             f"You logged {len(logged_meals)} meals this week, and {len(balanced_meals)} of them mixed in a "
             "vegetable, fruit, whole grain, or protein source. That's the practice — not a perfect week, a present one."
             if logged_meals else
             "No meals logged this week, and that's alright — the log is here whenever you're ready to pick it back up."
         )},
        {"id": "move", "kicker": "Chapter Two", "title": "Move", "stat": f"{activity_minutes} minutes",
         "body": (
             f"{activity_minutes} minutes of movement logged this week. Every minute counted the same — "
             "there's no threshold you needed to clear."
             if activity_minutes else "No movement logged this week. Whatever this week held, it's noted without judgment."
         )},
        {"id": "rest", "kicker": "Chapter Three", "title": "Rest", "stat": f"{avg_sleep}h avg" if avg_sleep is not None else "Not tracked",
         "body": (
             (f"About {avg_sleep} hours a night on average, from {wearable_nights} wearable-synced night(s)."
              if wearable_nights else
              f"About {avg_sleep} hours a night on average, from manual entries. Connect a wearable in Settings any time.")
             if avg_sleep is not None else "No sleep logged this week — Rest is always the gentlest of the three to skip, no explanation needed."
         )},
        {"id": "learning", "kicker": "Chapter Four", "title": "Learning", "stat": f"{videos_watched} videos · {games_played} scenarios",
         "body": (
             f"You watched {videos_watched} video(s) and worked through {games_played} scenario(s) this week — "
             "each one a small rehearsal for a real decision."
             if (videos_watched or games_played) else "No lessons or scenarios this week. They'll be right where you left them."
         )},
        {"id": "community", "kicker": "Chapter Five", "title": "Community", "stat": f"{cohort} people alongside you",
         "body": "Your cohort's shared milestones move together — your process wins this week added to that total, quietly."},
        {"id": "coach", "kicker": "Closing", "title": "This Week", "stat": "",
         "body": "Whatever this week looked like, you showed up in the ways you could. That's the whole practice — see you next week."},
    ]
    return {"chapters": chapters, "week_start": week_ago}


app.include_router(api)
app.include_router(daily_goals.make_router(db, current_user, now_utc))


# Staff-only ASA24 upload page. The page itself is public static HTML; every
# action it takes goes through the RESEARCH_API_KEY-gated /api/research/*.
@app.get("/research-admin", include_in_schema=False)
async def research_admin_page():
    from fastapi.responses import FileResponse
    return FileResponse(ROOT_DIR / "research_admin.html", media_type="text/html",
                        headers={"Cache-Control": "no-store", "X-Frame-Options": "DENY"})

_DEFAULT_DEV_ORIGINS = "http://localhost:8081,http://localhost:19006,http://localhost:3000"
CORS_ALLOWED_ORIGINS = [o.strip() for o in os.environ.get("CORS_ALLOWED_ORIGINS", _DEFAULT_DEV_ORIGINS).split(",") if o.strip()]
if not os.environ.get("CORS_ALLOWED_ORIGINS"):
    logger.warning(
        "CORS_ALLOWED_ORIGINS is not set — falling back to localhost-only dev origins. "
        "Set this to your real web deployment origin(s) before shipping the web build."
    )

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def create_indexes():
    try:
        await db.meals.create_index([("user_id", 1), ("created_at", -1)])
        await db.asa24_links.create_index("asa24_username", unique=True)
        await db.asa24_links.create_index("user_id", unique=True)
        await db.asa24_recall_finished.create_index([("user_id", 1), ("assessment_type", 1)], unique=True)
        await db.program_steps.create_index([("user_id", 1), ("week", 1), ("step", 1)], unique=True)
        await db.weekly_workflow.create_index([("user_id", 1), ("week", 1)], unique=True)
        await db.focus_meal_bonus.create_index([("user_id", 1), ("day", 1)], unique=True)
        await db.asa24_accounts.create_index("username", unique=True)
        await db.password_resets.create_index("email", unique=True)
        await db.signup_codes.create_index("email", unique=True)
        await db.signup_codes.create_index("expires_at", expireAfterSeconds=0)
        await db.password_resets.create_index("expires_at", expireAfterSeconds=0)
        await db.activities.create_index([("user_id", 1), ("created_at", -1)])
        await db.sleeps.create_index([("user_id", 1), ("created_at", -1)])
        await db.completions.create_index([("user_id", 1), ("kind", 1), ("created_at", -1)])
        # The partial-unique index for daily_challenge completions is defined
        # below in its own try/except, together with the one-time dedup of
        # pre-existing duplicate rows. Only one definition for that index.
        await db.game_results.create_index([("user_id", 1), ("created_at", -1)])
        await db.chat_messages.create_index([("user_id", 1), ("created_at", 1)])
        await db.safety_checkins.create_index([("user_id", 1), ("acknowledged", 1)])
        await db.goals.create_index([("user_id", 1)])
        await db.wings.create_index("member_ids")
        await db.wings.create_index("join_code", unique=True)
        await db.guardrail_blocks.create_index([("user_id", 1), ("created_at", -1)])
        await db.swap_plans.create_index([("user_id", 1), ("swap_id", 1)], unique=True)
        await db.twin_decisions.create_index([("user_id", 1), ("day", 1)], unique=True)
        await db.twin_facts.create_index([("user_id", 1), ("key", 1)], unique=True)
        await db.twin_plans.create_index([("user_id", 1), ("rec_id", 1)], unique=True)
        await db.twin_snapshots.create_index([("user_id", 1), ("day", 1)], unique=True)
        await db.twin_events.create_index([("user_id", 1), ("created_at", -1)])
        await db.twin_events.create_index([("day", 1)])
        await db.twin_grocery.create_index([("user_id", 1), ("created_at", 1)])
        await db.hei_assessments.create_index([("user_id", 1), ("recorded_at", -1)])
        await db.researchers.create_index("email", unique=True)
        await db.researchers.create_index("id", unique=True)
        await db.users.create_index("email", unique=True)
        await db.users.create_index("id", unique=True)
        await db.revoked_tokens.create_index("jti", unique=True)
        await db.revoked_tokens.create_index("expires_at", expireAfterSeconds=0)
    except Exception as e:
        logger.error(f"Index creation failed (non-fatal, queries will just be slower): {e}")

    # Daily-challenge: at most one awarded completion per (user, challenge, date).
    # Kept in its own try/except so dedup or index failure here never skips
    # the general indexes above and never crashes startup. The partial filter
    # keeps every other `completions` row (meals, videos, games, …) free of
    # a uniqueness constraint. Pre-existing duplicates — possible on databases
    # that ran the daily challenge before this index landed — are collapsed to
    # the earliest row before the index is built, so the build itself can't
    # trip over them.
    try:
        # Drop the pre-rebase vestigial index if present. A short-lived
        # post-merge version of this fix created an equivalent partial unique
        # index under Mongo's auto-generated name `user_id_1_kind_1_ref_1`,
        # keyed on (user_id, kind, ref). The canonical index below is named
        # `completions_daily_challenge_unique` and keyed on (user_id, ref) —
        # same filter, same uniqueness guarantee. Dropping the vestige keeps
        # every database (local, demo, deployed) at exactly one definition.
        try:
            await db.completions.drop_index("user_id_1_kind_1_ref_1")
            logger.info(
                "Dropped vestigial daily-challenge index user_id_1_kind_1_ref_1 "
                "(superseded by completions_daily_challenge_unique)."
            )
        except Exception:
            # Fresh databases never had this index — the drop raises
            # OperationFailure/IndexNotFound. That's the happy path; move on.
            pass
        pipeline = [
            {"$match": {"kind": "daily_challenge"}},
            {"$sort": {"created_at": 1}},
            {"$group": {
                "_id": {"user_id": "$user_id", "ref": "$ref"},
                "earliest": {"$first": "$id"},
                "all_ids": {"$push": "$id"},
            }},
        ]
        extras: List[str] = []
        async for grp in db.completions.aggregate(pipeline):
            extras.extend(i for i in grp.get("all_ids", []) if i != grp.get("earliest"))
        if extras:
            logger.warning(
                f"Daily-challenge dedup: removing {len(extras)} duplicate completion row(s) "
                "before building the unique index."
            )
            await db.completions.delete_many({"id": {"$in": extras}})
        await db.completions.create_index(
            [("user_id", 1), ("ref", 1)],
            unique=True,
            partialFilterExpression={"kind": "daily_challenge"},
            name="completions_daily_challenge_unique",
        )
    except Exception as e:
        logger.error(f"Daily-challenge unique index setup failed (non-fatal): {e}")


@app.on_event("startup")
async def refresh_allergy_terms():
    """allergy_terms are derived from profile answers when the profile is
    saved; re-derive them at startup so a change to the extraction rules
    (e.g. ALLERGEN_FAMILIES) reaches existing participants too."""
    try:
        async for u in db.users.find({"profile": {"$ne": {}}}, {"_id": 0, "id": 1, "profile": 1, "allergy_terms": 1}):
            terms = _extract_allergy_terms(u.get("profile") or {})
            if terms != u.get("allergy_terms"):
                await db.users.update_one({"id": u["id"]}, {"$set": {"allergy_terms": terms}})
    except Exception as e:
        logger.warning(f"Allergy-term refresh failed: {e}")


@app.on_event("startup")
async def start_dining_prewarm():
    # Fire-and-forget: startup must not wait on the dining API. The task is
    # kept on app.state so it isn't garbage-collected mid-run. Skipped on
    # Vercel, where a function is frozen between requests and the cache
    # fills on first use instead.
    if ON_VERCEL:
        return
    app.state.dining_prewarm_task = asyncio.create_task(prewarm_dining_cache())


@app.on_event("startup")
async def log_photo_storage_mode():
    """One audit-friendly line in the boot log — "photo storage: blob"
    for a prod Vercel deploy that has the token wired, "memory" for
    local dev, or "unavailable" when we're on Vercel but somebody forgot
    to add BLOB_READ_WRITE_TOKEN (the upload endpoint will then surface
    a kind 503 instead of silently losing bytes to a per-worker dict)."""
    wings_photos.log_storage_mode_at_startup()


@app.on_event("startup")
async def log_weekly_workflow_mode():
    """One line per supported week — "weekly workflow: week 1 mode=off" —
    so the boot log makes it obvious which weeks are open to real users
    and which are still ``test_only``. Matches the Wings-photos audit
    line pattern."""
    for w in weekly_workflow.SUPPORTED_WEEKS:
        logger.info(f"weekly workflow: week {w} mode={weekly_workflow.workflow_mode(w)}")


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
