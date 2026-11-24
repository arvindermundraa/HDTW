"""
TAMU Chat API client — student bring-your-own-key (BYOK) support.

Adapted from the TAMUS API wrapper template provided by the team, converted
to async httpx (the original used sync `requests`; this server is FastAPI/
async throughout, and a blocking sync call inside an `async def` route would
stall the event loop for every other request while it waits). The template's
messages/content-processing shape is preserved so behavior matches what was
already validated: text, and PDF/image content translated to the OpenAI-
compatible `image_url` data-URL format.

SCOPE NOTE: this client supports text chat and image input, matching the
model catalog's `/v1/chat/completions` surface. It does NOT support audio
input — neither TAMU IT's own service page nor the team's reference wrapper
(taugroup/TAMU-Chat-AI) documents an audio/speech endpoint or an audio-
capable model, so there is nothing for a Voice Logging feature to call. As
of 2026-09, LLHS has removed Voice Logging entirely rather than ship a
feature with no working backend — see README/PRD for that decision. If TAMU
AI adds audio support in the future, re-add it here rather than reaching
for a third-party provider.

MANDATORY, SOLE AI PROVIDER: as of 2026-09, TAMU AI is the only LLM backend
this app calls — the prior Emergent-routed default (shared Claude Sonnet /
Gemini access via `emergentintegrations`) has been fully removed, at the
team's explicit request, so there is no silent fallback if a call fails.
Every participant must have a usable TAMU key before any AI feature (the
coach, photo/text meal-log assist, dining plate review and chat-build-meal)
will respond — see `resolve_user_key()` below. `run_llm()`/`llm_vision_call()`
in server.py raise `TamusKeyRequiredError` when a user has none, and every
call site is expected to surface that plainly ("add your TAMU key in
Settings") rather than degrade silently, since silence would look like a
bug rather than a missing setup step.

ADMIN/TESTING KEY POOL: a small number of participants — QA/demo accounts
that can't reasonably be expected to hold a personal TAMU credit — can be
allowlisted by email via the TAMUS_ADMIN_TEST_EMAILS env var (comma-
separated) to draw from a small shared pool of TAU-provisioned keys in
TAMUS_ADMIN_API_KEYS (also comma-separated). This is checked only as a
fallback for accounts with no personal key of their own, is not visible or
settable from the app, and is meant for staff to hand out sparingly, not as
a general shared key for the whole student body.

SECURITY NOTE: student TAMUS API keys are encrypted at rest with Fernet
(symmetric encryption) using a server-side secret (TAMUS_KEY_ENCRYPTION_SECRET
env var). This is a real improvement over plaintext storage, but is not a
substitute for a proper secrets manager / KMS with key rotation — that
remains a recommended follow-up before this handles real student credentials
at scale. The admin/testing pool keys are read straight from an env var for
the same reason plaintext secrets normally aren't: keep TAMUS_ADMIN_API_KEYS
in your deployment's secret manager, not committed anywhere.
"""
import asyncio
import os
import base64
import hashlib
import logging
from typing import Optional, List, Dict, Any

import httpx
from cryptography.fernet import Fernet

logger = logging.getLogger("llhs.tamus")

TAMUS_API_BASE = "https://chat-api.tamu.ai"
TAMUS_TIMEOUT = 60.0

# ----------------------------------------------------------------------------
# Exact model catalog, as provided by the team (verified against TAMU Chat
# API's own /v1/models endpoint). Pass model ids through EXACTLY as listed —
# note some contain spaces/capitalization (e.g. "protected.Claude Sonnet
# 4.5") which is unusual for an API identifier; do not "clean" or reformat
# these strings, as that risks breaking the call against the real API.
# ----------------------------------------------------------------------------
TAMUS_MODEL_CATALOG: List[Dict[str, Any]] = [
    {"id": "protected.Claude Sonnet 4.5", "display_name": "Claude Sonnet 4.5", "provider": "Anthropic", "vision_capable": True},
    {"id": "protected.Claude Sonnet 4.6", "display_name": "Claude Sonnet 4.6", "provider": "Anthropic", "vision_capable": True},
    {"id": "protected.Claude-Haiku-4.5", "display_name": "Claude Haiku 4.5", "provider": "Anthropic", "vision_capable": True},
    # Added 2026-09 from the live /v1/models listing (embedding model omitted — not a chat model).
    {"id": "protected.Claude Sonnet 4", "display_name": "Claude Sonnet 4", "provider": "Anthropic", "vision_capable": True},
    {"id": "protected.Claude Opus 4.1", "display_name": "Claude Opus 4.1", "provider": "Anthropic", "vision_capable": True},
    {"id": "protected.Claude Opus 4.5", "display_name": "Claude Opus 4.5", "provider": "Anthropic", "vision_capable": True},
    {"id": "protected.Claude Opus 4.6", "display_name": "Claude Opus 4.6", "provider": "Anthropic", "vision_capable": True},
    {"id": "protected.Claude Opus 4.7", "display_name": "Claude Opus 4.7", "provider": "Anthropic", "vision_capable": True},
    {"id": "protected.Claude Opus 4.8", "display_name": "Claude Opus 4.8", "provider": "Anthropic", "vision_capable": True},
    {"id": "protected.Claude 3.5 Haiku", "display_name": "Claude 3.5 Haiku", "provider": "Anthropic", "vision_capable": False},
    {"id": "protected.gemini-2.5-flash", "display_name": "Gemini 2.5 Flash", "provider": "Google", "vision_capable": True},
    {"id": "protected.gemini-2.5-flash-lite", "display_name": "Gemini 2.5 Flash Lite", "provider": "Google", "vision_capable": True},
    {"id": "protected.gemini-2.5-pro", "display_name": "Gemini 2.5 Pro", "provider": "Google", "vision_capable": True},
    {"id": "protected.gemini-3.1-flash-lite", "display_name": "Gemini 3.1 Flash Lite", "provider": "Google", "vision_capable": True},
    {"id": "protected.gemini-3.5-flash", "display_name": "Gemini 3.5 Flash", "provider": "Google", "vision_capable": True},
    {"id": "protected.gpt-4o", "display_name": "GPT-4o (migrate to 4.1)", "provider": "OpenAI", "vision_capable": True},
    {"id": "protected.gpt-4.1", "display_name": "GPT-4.1", "provider": "OpenAI", "vision_capable": True},
    {"id": "protected.gpt-4.1-mini", "display_name": "GPT-4.1 Mini", "provider": "OpenAI", "vision_capable": True},
    {"id": "protected.gpt-4.1-nano", "display_name": "GPT-4.1 Nano", "provider": "OpenAI", "vision_capable": True},
    {"id": "protected.gpt-5", "display_name": "GPT-5", "provider": "OpenAI", "vision_capable": True},
    {"id": "protected.gpt-5-mini", "display_name": "GPT-5 Mini", "provider": "OpenAI", "vision_capable": True},
    {"id": "protected.gpt-5-nano", "display_name": "GPT-5 Nano", "provider": "OpenAI", "vision_capable": True},
    {"id": "protected.gpt-5.1", "display_name": "GPT-5.1", "provider": "OpenAI", "vision_capable": True},
    {"id": "protected.gpt-5.2", "display_name": "GPT-5.2", "provider": "OpenAI", "vision_capable": True},
    {"id": "protected.gpt-5.4", "display_name": "GPT-5.4", "provider": "OpenAI", "vision_capable": True},
    {"id": "protected.gpt-5.4-mini", "display_name": "GPT-5.4 Mini", "provider": "OpenAI", "vision_capable": True},
    {"id": "protected.gpt-5.4-nano", "display_name": "GPT-5.4 Nano", "provider": "OpenAI", "vision_capable": True},
    {"id": "protected.gpt-5.5", "display_name": "GPT-5.5", "provider": "OpenAI", "vision_capable": True},
    {"id": "protected.o3", "display_name": "o3", "provider": "OpenAI (reasoning)", "vision_capable": False},
    {"id": "protected.o3-mini", "display_name": "o3-mini", "provider": "OpenAI (reasoning)", "vision_capable": False},
    {"id": "protected.o4-mini", "display_name": "o4-mini", "provider": "OpenAI (reasoning)", "vision_capable": False},
    {"id": "protected.llama3.2", "display_name": "Llama 3.2 (multimodal)", "provider": "Meta", "vision_capable": True},
    {"id": "tamu-study-mode", "display_name": "TAMU: Study Mode", "provider": "TAMU Preset", "vision_capable": False},
]

DEFAULT_CHAT_MODEL = "protected.Claude Sonnet 4.6"
DEFAULT_VISION_MODEL = "protected.gemini-3.5-flash"

_CATALOG_IDS = {m["id"] for m in TAMUS_MODEL_CATALOG}


def is_known_model(model_id: str) -> bool:
    return model_id in _CATALOG_IDS


# TAMU's gateway runs its Claude Sonnet/Opus model groups with extended
# thinking forced on (verified 2026-09 against the live API). Bedrock then
# rejects any temperature other than 1 and any max_tokens not above the
# thinking budget — so the app's default temperature=0 made every call to
# the default chat model fail. Haiku, Gemini and OpenAI models are unaffected.
THINKING_MIN_MAX_TOKENS = 4096


def _is_thinking_model(model_id: str) -> bool:
    m = model_id.lower()
    return "claude" in m and ("sonnet" in m or "opus" in m)


# Invisible characters that commonly ride along when a key is copied from
# a doc / Slack / email. Only stripped from the *ends* of the key — leaving
# any interior invisible to the ASCII check in `chat()`, which rejects it
# with a clear "invalid characters" message rather than silently rewriting
# a key the student thought was correct.
_LEAD_TRAIL_INVISIBLES = (
    " \t\n\r\x0b\x0c"           # ASCII whitespace (what str.strip() alone covers)
    " "                    # non-breaking space
    "    "  # en quad, em quad, en space, em space
    "    "  # three-per-em / four-per-em / six-per-em / figure
    "   "        # punctuation space, thin space, hair space
    "​‌‍"        # zero-width space, ZWNJ, ZWJ
    "  "              # line separator, paragraph separator
    "  "              # narrow no-break space, medium mathematical space
    "⁠"                    # word joiner
    "　"                    # ideographic space
    "﻿"                    # zero-width no-break space / BOM
)


def clean_api_key(raw: Optional[str]) -> str:
    """Strip leading/trailing ASCII whitespace plus common invisible
    characters (NBSP, zero-width spaces, BOM) that come along when a key
    is pasted from a doc. Interior characters are left alone — if any
    remain non-ASCII, `chat()`'s header check still rejects with a clear
    "invalid characters" message, so an interior typo can't be silently
    rewritten into a different key.

    Returns an empty string for None so callers don't have to pre-check.
    """
    if not raw:
        return ""
    return raw.strip(_LEAD_TRAIL_INVISIBLES)


class TAMUSError(Exception):
    """Raised on any TAMUS call failure. Message is safe to show to a user
    or log — it never includes the API key."""


class TamusKeyRequiredError(TAMUSError):
    """Raised when a participant has no usable TAMU key — no personal key
    saved, and not an allowlisted admin/testing account with pool access.
    TAMU AI is the app's only AI provider, so there is nothing to fall back
    to: callers must surface this as an actionable "add your key" prompt,
    never swallow it into a generic error."""


def _fernet() -> Fernet:
    secret = os.environ.get("TAMUS_KEY_ENCRYPTION_SECRET", "")
    if not secret:
        logger.warning(
            "TAMUS_KEY_ENCRYPTION_SECRET is not set - falling back to an insecure "
            "development key. Set this environment variable before storing any real "
            "student API keys."
        )
        secret = "dev-only-insecure-tamus-secret"
    digest = hashlib.sha256(secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_key(raw_key: str) -> str:
    return _fernet().encrypt(raw_key.encode()).decode()


def decrypt_key(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()


def _admin_test_emails() -> set:
    raw = os.environ.get("TAMUS_ADMIN_TEST_EMAILS", "")
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def is_admin_test_account(email: Optional[str]) -> bool:
    """True only for the small, staff-managed allowlist in
    TAMUS_ADMIN_TEST_EMAILS — never settable from the app itself."""
    return bool(email) and email.strip().lower() in _admin_test_emails()


def admin_key_pool() -> List[str]:
    raw = os.environ.get("TAMUS_ADMIN_API_KEYS", "")
    return [k.strip() for k in raw.split(",") if k.strip()]


def resolve_user_key(user: Dict[str, Any]) -> str:
    """Returns the raw TAMU API key to use for this participant's AI calls.

    TAMU AI is the app's sole LLM provider — there is no shared default to
    silently fall back to. Precedence:
      1. The participant's own saved key (the expected path for everyone).
      2. For a staff-allowlisted admin/testing account (TAMUS_ADMIN_TEST_EMAILS)
         with no personal key of their own, a stable pick from the shared
         TAMUS_ADMIN_API_KEYS pool — keyed off the user id so the same
         account always lands on the same pool key.

    Raises TamusKeyRequiredError otherwise. Callers must surface that as an
    explicit "add your TAMU key in Settings" prompt, not a generic failure.
    """
    encrypted = user.get("tamus_api_key_encrypted")
    if encrypted:
        try:
            return decrypt_key(encrypted)
        except Exception:
            raise TamusKeyRequiredError(
                "Your saved TAMU key couldn't be read — please re-enter it in Settings."
            )

    if is_admin_test_account(user.get("email")):
        pool = admin_key_pool()
        if pool:
            ident = user.get("id") or user.get("email") or ""
            idx = int(hashlib.sha256(ident.encode()).hexdigest(), 16) % len(pool)
            return pool[idx]

    raise TamusKeyRequiredError("Add your TAMU AI key in Settings to use this feature.")


def _build_messages(system: str, user_text: str, image_base64: Optional[str], image_mime: str,
                    history: Optional[List[Dict[str, str]]] = None) -> List[Dict[str, Any]]:
    messages = [{"role": "system", "content": system}]
    # Earlier turns of this conversation (oldest first), text only.
    for turn in history or []:
        if turn.get("role") in ("user", "assistant") and turn.get("content"):
            messages.append({"role": turn["role"], "content": turn["content"]})
    if image_base64:
        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": user_text},
                {"type": "image_url", "image_url": {"url": f"data:{image_mime};base64,{image_base64}"}},
            ],
        })
    else:
        messages.append({"role": "user", "content": user_text})
    return messages


async def chat(
    api_key: str,
    model: str,
    system: str,
    user_text: str,
    image_base64: Optional[str] = None,
    image_mime: str = "image/jpeg",
    max_tokens: int = 2048,
    temperature: float = 0.0,
    history: Optional[List[Dict[str, str]]] = None,
) -> str:
    """Call against TAMU's OpenAI-compatible endpoint (optionally with prior
    conversation turns in `history`). Raises
    TAMUSError on any failure - callers are expected to catch this and fall
    back to the app's default model (see server.py call sites)."""
    url = f"{TAMUS_API_BASE}/api/v1/chat/completions"
    # Reject keys with characters httpx can't put in an HTTP header. Pasting a
    # key from a doc sometimes drags along a smart-quote or non-breaking space;
    # without this check, httpx raises UnicodeEncodeError deep inside
    # client.post() and the whole endpoint 500s. Message must not include the
    # key itself.
    try:
        f"Bearer {api_key}".encode("ascii")
    except UnicodeEncodeError:
        raise TAMUSError(
            "That TAMU API key contains invalid characters (smart quotes or non-breaking "
            "spaces are common culprits). Re-copy the key from the TAMU AI portal."
        )
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if _is_thinking_model(model):
        temperature = 1.0
        max_tokens = max(max_tokens, THINKING_MIN_MAX_TOKENS)
    body = {
        "model": model,
        "messages": _build_messages(system, user_text, image_base64, image_mime, history),
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }
    try:
        async with httpx.AsyncClient(timeout=TAMUS_TIMEOUT) as client:
            resp = await client.post(url, headers=headers, json=body)
            if resp.status_code == 401:
                raise TAMUSError("That TAMU API key was rejected - please check it in Settings.")
            if resp.status_code == 429:
                raise TAMUSError("TAMU AI credit appears to be exhausted for this key.")
            resp.raise_for_status()
            data = resp.json()
    except httpx.RequestError as e:
        raise TAMUSError(f"Could not reach the TAMU AI service: {e.__class__.__name__}")
    except httpx.HTTPStatusError as e:
        raise TAMUSError(f"TAMU AI service returned an error ({e.response.status_code}).")

    # The gateway reports upstream failures as HTTP 200 with an "error" body.
    if isinstance(data, dict) and data.get("error"):
        err = data["error"]
        msg = err.get("message", "") if isinstance(err, dict) else str(err)
        logger.warning("TAMU AI error for model %s: %s", model, msg[:300])
        raise TAMUSError(f"TAMU AI couldn't complete the request with {model} — try another model in Settings.")

    try:
        content = data["choices"][0]["message"]["content"]
        if not content:
            raise ValueError("empty content")
        return content
    except (KeyError, IndexError, ValueError):
        raise TAMUSError("TAMU AI service returned an unexpected response.")


async def test_key(api_key: str, model: str) -> tuple:
    """Mirrors the template's own __main__ demo call ('Say HELLO').
    Never raises — the endpoint handler relies on this to always return a
    (ok, message) tuple, so a slow or broken TAMU call becomes a friendly
    message instead of a 500 that strips CORS headers (the symptom seen
    on the client as 'Failed to fetch')."""
    try:
        reply = await chat(api_key, model, system="You are a connectivity test.", user_text="Say HELLO", max_tokens=20)
        return True, reply.strip()[:120]
    except TAMUSError as e:
        return False, str(e)
    except asyncio.TimeoutError:
        return False, f"Timed out after {int(TAMUS_TIMEOUT)}s waiting for TAMU AI — try again."
    except Exception as e:
        # Last-resort: never let an unexpected exception escape — the endpoint
        # must return clean JSON so CORS headers reach the browser. Message
        # names only the exception class, never the key.
        logger.warning("TAMU test_key unexpected failure: %s", e.__class__.__name__)
        return False, f"Couldn't test the TAMU AI key ({e.__class__.__name__}) — try again."
