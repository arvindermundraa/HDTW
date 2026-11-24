"""Wings photo posts — Phase 2.

Responsibilities (pure helpers; endpoints live in server.py):

- **Mode flag** ``WINGS_PHOTOS_MODE`` controls who can post:
  "off"        → nobody; feature invisible.
  "test_only"  → only ``is_test_account`` students see the Share button.
                  Default for the Tue Oct 27 lab test, so students in the
                  Lab Test Wing can rehearse the flow without any real
                  participant being able to post before IRB sign-off.
  "on"         → every student (gated at env level; the server REFUSES to
                  boot with "on" unless ``WINGS_PHOTOS_IRB_CONFIRMED=1``
                  is also set, so a stray typo in a dashboard can't ship
                  the feature live before PI approval).

- **Content filters** on captions and "How I made it" steps: block
  calorie / weight / gram talk, insults, personal details (emails,
  phones, @handles, URLs). Reuses the design-rule vocabulary already
  enforced in chat guardrails.

- **Image pipeline**: validate the real file type by magic bytes (never
  trust the extension), reject >5 MB, re-encode via Pillow to max
  1600 px JPEG, and **strip ALL EXIF/metadata (especially GPS)**.

- **Storage interface** so the Vercel-Blob adapter (production) and the
  in-memory adapter (local dev / tests) are interchangeable from the
  endpoint's point of view.
"""
from __future__ import annotations

import io
import logging
import os
import re
import uuid
from dataclasses import dataclass
from typing import Protocol, Optional

from PIL import Image, ImageOps

# Register the HEIC/HEIF decoder with Pillow so iPhone camera-roll
# photos load through `Image.open` just like JPEG / PNG. The register
# call is idempotent; a missing wheel (older dev venvs without
# pillow-heif) is logged as a warning but doesn't crash the import —
# the magic-byte sniff below will then reject HEIC uploads cleanly.
try:
    from pillow_heif import register_heif_opener  # type: ignore
    register_heif_opener()
    _HEIF_SUPPORT = True
except Exception as _e:  # pragma: no cover
    _HEIF_SUPPORT = False
    import logging as _bootstrap_log
    _bootstrap_log.getLogger("llhs.wings_photos").warning(
        "pillow-heif not available (%s); HEIC uploads will be rejected", _e,
    )


_log = logging.getLogger("llhs.wings_photos")


# --- Mode flag --------------------------------------------------------------

VALID_MODES = ("off", "test_only", "on")


def photos_mode() -> str:
    """Read ``WINGS_PHOTOS_MODE`` at call time (never cached) so the env can
    be flipped without a code change. ``"on"`` is refused unless the
    operator has also set ``WINGS_PHOTOS_IRB_CONFIRMED=1`` — belt-and-
    braces against a dashboard typo shipping photos before IRB sign-off."""
    raw = (os.environ.get("WINGS_PHOTOS_MODE") or "test_only").strip().lower()
    if raw not in VALID_MODES:
        raw = "test_only"
    if raw == "on" and os.environ.get("WINGS_PHOTOS_IRB_CONFIRMED", "").strip() != "1":
        return "test_only"
    return raw


def _running_on_vercel() -> bool:
    """Vercel sets ``VERCEL=1`` in every function invocation. Treat that as
    "we're in production" for the storage-fallback refusal below. Local dev
    (``uvicorn ... --port 8001``) never has this set."""
    return os.environ.get("VERCEL") == "1"


def storage_mode() -> str:
    """Which storage adapter *will* be used on the next request:
      ``"blob"``       — ``BLOB_READ_WRITE_TOKEN`` is set, use Vercel Blob.
      ``"memory"``     — token absent AND we're in local dev, dev fallback.
      ``"unavailable"``— token absent AND we're on Vercel: the backend must
                         refuse to accept posts rather than silently store
                         bytes in a per-worker dict that disappears when
                         the function cold-starts.
    """
    if os.environ.get("BLOB_READ_WRITE_TOKEN"):
        return "blob"
    if _running_on_vercel():
        return "unavailable"
    return "memory"


def can_user_post(user: dict, is_test: bool) -> bool:
    """Server-side gate — the frontend's hide/show is a UX nicety; this is
    the real authority. Returns ``False`` if storage is unavailable so the
    Share button hides itself when the Vercel deploy is missing the Blob
    token, instead of letting students upload into the void."""
    mode = photos_mode()
    if mode == "off":
        return False
    if storage_mode() == "unavailable":
        return False
    if mode == "test_only":
        return bool(is_test)
    return True  # "on"


# "Photo sharing isn't available right now" — one source of truth for the
# friendly 503 the upload endpoint returns when storage is unavailable.
STORAGE_UNAVAILABLE_MESSAGE = "Photo sharing isn't available right now."


class StorageUnavailable(RuntimeError):
    """Raised by `default_storage()` when running on Vercel without a
    Blob token. Endpoints catch this and surface a kind 503 — nothing
    silent falls back to in-memory in production."""


def log_storage_mode_at_startup() -> None:
    """Emit one audit-friendly line at boot so an operator can grep logs
    for the active storage path. Never prints the token value."""
    _log.info("photo storage: %s", storage_mode())


# --- Content filters --------------------------------------------------------
# Patterns are intentionally generous — a false positive here is a kind
# "pick different words" prompt, never a hidden ban. All participant-facing
# messages the filter returns live in CONTENT_FILTER_MESSAGES below so staff
# can read them in one place.

_NUMERIC_NUTRITION = re.compile(
    r"\b(\d+\s*(kcal|cal|calories?|g|kg|lbs?|mg|grams?|%\s*dv))\b",
    re.IGNORECASE,
)
_RESTRICTION_WORDS = re.compile(
    r"\b(diet|lose weight|weight loss|slim|skinny|cheat day|cheat meal|guilt-?free|low[-\s]?cal|fewer calories)\b",
    re.IGNORECASE,
)
_PERSONAL_CONTACT = re.compile(
    r"(\b[\w.+-]+@[\w-]+\.[\w.-]+\b"          # email
    r"|\b\+?\d[\d\s().-]{7,}\d\b"             # phone numbers
    r"|(?<!\w)@[A-Za-z0-9_]{2,}\b"            # @handles
    r"|https?://\S+|www\.\S+)",               # URLs
)
_INSULTS = re.compile(
    r"\b(fuck|shit|bitch|nigger|faggot|cunt|retard|slut|whore|dumbass|fatty)\b",
    re.IGNORECASE,
)


@dataclass
class ContentFilterResult:
    """Returned by ``check_text`` so endpoints can surface a specific,
    friendly message instead of a generic 'blocked'."""
    ok: bool
    code: Optional[str] = None
    message: Optional[str] = None


CONTENT_FILTER_MESSAGES = {
    "numeric_nutrition":
        "Captions here aren't about numbers — calories, grams and percentages all stay out. "
        "Try describing the food instead ('bright, fresh, plenty of greens').",
    "restriction_framing":
        "This community keeps language supportive and additive. Try a kinder way to describe "
        "the meal — what's in it, how it tastes, how it came together.",
    "personal_contact":
        "Please leave out personal details (emails, phone numbers, handles or links). "
        "Keep posts about the food.",
    "insults":
        "Let's keep the Wing kind. Try different wording.",
    "too_long":
        "A bit shorter, please — captions under 200 characters, each step under 80.",
}


def check_text(caption: str, steps: Optional[list[str]] = None) -> ContentFilterResult:
    """Run every content rule over the caption + optional steps and return
    the first mismatch (specific message > generic blocked). Case-insensitive."""
    if steps is None:
        steps = []
    if len(caption) > 200 or any(len(s) > 80 for s in steps) or len(steps) > 5:
        return ContentFilterResult(False, "too_long", CONTENT_FILTER_MESSAGES["too_long"])
    pieces = [caption] + list(steps)
    joined = "\n".join(pieces)
    for code, pat in (
        ("numeric_nutrition", _NUMERIC_NUTRITION),
        ("restriction_framing", _RESTRICTION_WORDS),
        ("personal_contact", _PERSONAL_CONTACT),
        ("insults", _INSULTS),
    ):
        if pat.search(joined):
            return ContentFilterResult(False, code, CONTENT_FILTER_MESSAGES[code])
    return ContentFilterResult(True)


# --- Image pipeline ---------------------------------------------------------

# Max image on disk — 5 MB — matches the brief; prevents the bytes from
# ever reaching Pillow's decoder if a client ignores the client-side cap.
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_LONG_EDGE = 1600  # pixels

# Magic-byte sniffer: trust the file's own header, not the extension (an
# "image.jpg" with executable bytes should be rejected on sight).
_MAGIC_SNIFFERS: list[tuple[bytes, str]] = [
    (b"\xff\xd8\xff", "jpeg"),
    (b"\x89PNG\r\n\x1a\n", "png"),
    # HEIC/HEIF — the "ftyp" box at offset 4 carries one of several brand codes;
    # we accept any ftyp with a known HEIC-family brand.
]
_HEIC_BRANDS = (b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"hevm", b"hevs", b"mif1", b"msf1")


def sniff_image_kind(data: bytes) -> Optional[str]:
    """Return ``"jpeg" | "png" | "heic"`` based on the file's own first
    bytes, or ``None`` if nothing matches (reject)."""
    if len(data) < 12:
        return None
    for prefix, kind in _MAGIC_SNIFFERS:
        if data.startswith(prefix):
            return kind
    # HEIC: ...ftyp<brand>
    if data[4:8] == b"ftyp":
        brand = data[8:12].lower()
        if brand in _HEIC_BRANDS:
            return "heic"
    return None


class ImageRejected(ValueError):
    """Raised when the pipeline refuses to process a file. The message is
    safe to show to the student verbatim."""


# Fallback student-facing message for any decode / processing failure that
# doesn't have a specific friendly message of its own. Deliberately plain —
# we never surface Pillow's Python-level exception text to a student (it
# can look like a stack trace and sometimes includes the filename, which
# we treat as user data on the server). The real cause is logged in
# `process_image` without any user-provided fields.
FRIENDLY_IMAGE_ERROR = "We couldn't use that photo. Try a JPG or PNG, or take a new photo."


@dataclass
class ProcessedImage:
    """Clean JPEG bytes + the width/height actually encoded, so the DB can
    store the real dimensions (helpful for feed layout)."""
    jpeg_bytes: bytes
    width: int
    height: int


def process_image(data: bytes, declared_kind: Optional[str] = None) -> ProcessedImage:
    """Validate, decode, re-encode and strip EXIF.

    Rejects:
      - anything that isn't a recognised JPEG / PNG / HEIC;
      - anything larger than 5 MB on disk;
      - anything Pillow can't decode (malformed, truncated).

    Always returns a JPEG with NO EXIF, max 1600 px on the long edge, and
    EXIF orientation applied first (so a sideways phone photo is rotated,
    not just tagged). GPS metadata is impossible to leak at this point —
    Pillow's `Image.save(..., exif=b"")` writes an empty EXIF segment.
    """
    if not isinstance(data, (bytes, bytearray)):
        raise ImageRejected("Image data couldn't be read.")
    if len(data) == 0:
        raise ImageRejected("Image file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ImageRejected("Image is too large — please pick one under 5 MB.")
    kind = sniff_image_kind(bytes(data))
    if kind is None:
        raise ImageRejected("That doesn't look like a JPEG, PNG or HEIC photo.")
    if declared_kind and declared_kind.lower() not in (kind, f"image/{kind}", f"image/{kind}eg"):
        # Declared extension/MIME doesn't match the real bytes — reject even
        # if the bytes themselves are a valid image, so a renamed exploit
        # doesn't slip through on content-type confusion.
        raise ImageRejected("The file's name doesn't match its contents.")
    try:
        with Image.open(io.BytesIO(data)) as im:
            # Apply EXIF-based orientation BEFORE we discard EXIF.
            im = ImageOps.exif_transpose(im)
            if im.mode in ("P", "LA", "RGBA"):
                background = Image.new("RGB", im.size, (255, 255, 255))
                background.paste(im, mask=im.split()[-1] if im.mode in ("LA", "RGBA") else None)
                im = background
            elif im.mode != "RGB":
                im = im.convert("RGB")
            # Resize so the longest edge is MAX_LONG_EDGE (preserve aspect).
            w, h = im.size
            if max(w, h) > MAX_LONG_EDGE:
                scale = MAX_LONG_EDGE / float(max(w, h))
                im = im.resize((int(round(w * scale)), int(round(h * scale))), Image.LANCZOS)
            out = io.BytesIO()
            # exif=b"" guarantees an empty EXIF segment — no GPS, no camera
            # model, no Apple-specific maker notes. Progressive JPEG keeps
            # the feed card feeling snappy on slower connections.
            im.save(out, format="JPEG", quality=82, optimize=True, progressive=True, exif=b"")
            return ProcessedImage(jpeg_bytes=out.getvalue(), width=im.width, height=im.height)
    except ImageRejected:
        raise
    except Exception as e:
        # Log the real error server-side (type + message), but ONLY the
        # exception detail — never the raw bytes, never the declared
        # filename / caption / user id (those stay in the endpoint's
        # context, which we don't pass down here). The student sees a
        # single friendly line that works for any decode failure.
        _log.exception("wings photo decode failed: %s: %s", type(e).__name__, str(e)[:200])
        raise ImageRejected(FRIENDLY_IMAGE_ERROR) from None


# --- Storage interface ------------------------------------------------------

class WingPhotoStorage(Protocol):
    """Backends must implement these three. Keys are opaque strings owned
    by the storage; the endpoint stores whatever ``put`` returns and
    passes it back to ``get`` / ``delete``."""
    async def put(self, data: bytes, filename: str) -> str: ...
    async def get(self, key: str) -> bytes: ...
    async def delete(self, key: str) -> None: ...


class MemoryStorage:
    """Dev / test adapter: holds bytes in a dict. **Not for production** —
    photos vanish on restart. Keys are stable UUIDs so the moderation
    endpoint links keep working across requests in-process."""
    def __init__(self) -> None:
        self._bytes: dict[str, bytes] = {}

    async def put(self, data: bytes, filename: str) -> str:
        del filename
        key = uuid.uuid4().hex
        self._bytes[key] = bytes(data)
        return key

    async def get(self, key: str) -> bytes:
        if key not in self._bytes:
            raise FileNotFoundError(key)
        return self._bytes[key]

    async def delete(self, key: str) -> None:
        self._bytes.pop(key, None)


class VercelBlobStorage:
    """Production adapter — reads/writes via the Vercel Blob REST API using
    ``BLOB_READ_WRITE_TOKEN``. The token stays on the server side; the
    actual URL returned by Vercel is kept server-only (we proxy bytes
    through ``/wings/posts/image/{id}`` so a Blob URL never reaches the
    student's browser or any index). Each key is the full Blob URL."""
    _BASE = "https://blob.vercel-storage.com"

    def __init__(self, token: str, prefix: str = "wings/photos/") -> None:
        self._token = token
        self._prefix = prefix

    async def put(self, data: bytes, filename: str) -> str:
        import httpx
        pathname = f"{self._prefix}{uuid.uuid4().hex}-{self._safe_name(filename)}"
        headers = {
            "authorization": f"Bearer {self._token}",
            "x-content-type": "image/jpeg",
            "x-add-random-suffix": "0",
        }
        async with httpx.AsyncClient(timeout=30.0) as c:
            r = await c.put(f"{self._BASE}/{pathname}", content=bytes(data), headers=headers)
            r.raise_for_status()
            return r.json()["url"]

    async def get(self, key: str) -> bytes:
        import httpx
        async with httpx.AsyncClient(timeout=30.0) as c:
            r = await c.get(key)  # key IS the Blob URL
            r.raise_for_status()
            return r.content

    async def delete(self, key: str) -> None:
        import httpx
        headers = {"authorization": f"Bearer {self._token}"}
        async with httpx.AsyncClient(timeout=30.0) as c:
            # Vercel Blob's DELETE accepts the URL as a query param on the
            # root endpoint, not as a path component.
            await c.request("DELETE", f"{self._BASE}/delete", headers=headers,
                            json={"urls": [key]})

    @staticmethod
    def _safe_name(name: str) -> str:
        # Keep letters, digits, dot, dash, underscore; strip anything else.
        return re.sub(r"[^a-zA-Z0-9._-]", "_", name)[:64] or "upload"


def default_storage() -> WingPhotoStorage:
    """Pick the right adapter from env. In production (Vercel) the
    ``BLOB_READ_WRITE_TOKEN`` is wired automatically; in local dev / tests
    we fall back to the in-memory adapter so nothing crashes offline.

    **Refusal in production**: if we're running on Vercel but the token
    is missing, raise ``StorageUnavailable`` so the upload endpoint
    returns a kind 503 ("Photo sharing isn't available right now") —
    never silently store bytes in a per-worker dict that evaporates on
    the next cold start.
    """
    token = os.environ.get("BLOB_READ_WRITE_TOKEN")
    if token:
        return VercelBlobStorage(token)
    if _running_on_vercel():
        raise StorageUnavailable(
            "BLOB_READ_WRITE_TOKEN missing on Vercel — refusing to use the "
            "in-memory fallback in production."
        )
    return MemoryStorage()


# --- Preset data (reactions, reject reasons) ---------------------------------

REACTION_PRESETS: list[dict] = [
    {"key": "looks_delicious", "label": "Looks delicious"},
    {"key": "want_to_try",     "label": "Want to try this"},
    {"key": "great_swap",      "label": "Great swap"},
    {"key": "so_colourful",    "label": "So colourful"},
]
REACTION_KEYS = {r["key"] for r in REACTION_PRESETS}

REJECT_REASONS: dict[str, str] = {
    "shows_person":            "Photo shows a person",
    "not_a_food_photo":        "Not a food photo",
    "breaks_guidelines":       "Caption breaks our community guidelines",
    "unclear":                 "Not clear enough to approve",
}

MAX_POSTS_PER_STUDY_DAY = 3

POSTING_GUIDE = (
    "Share food, not faces. No other people, names, ID cards or locations "
    "in the photo. Keep captions kind and about the food."
)
