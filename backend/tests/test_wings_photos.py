"""Wings Phase 2 — photo posts with moderation.

Covers the brief's hard-constraint tests:

  * The ``WINGS_PHOTOS_MODE`` gate is enforced server-side ("off", or
    "test_only" with a live account, both block the Share button).
  * The image pipeline rejects fake file types (magic-byte sniff beats
    extension spoofing), rejects >5 MB files, re-encodes to <=1600 px,
    and strips **all** EXIF — the whole metadata block, GPS included.
  * The content filter blocks calorie / gram / lose-weight framing and
    personal contacts (emails, phones, @handles, URLs).
  * The storage interface's in-memory adapter round-trips bytes and
    deletes them irreversibly (so a per-post cascade in server.py
    really does leave no bytes on disk).

Endpoint-level tests (per-day limit, feed excludes rejected/removed,
reactions anonymous) live in `test_wings_photos_endpoints.py` so this
module stays dependency-light (no fake DB).
"""
from __future__ import annotations

import asyncio
import io
import os

import pytest

import wings_photos


# --- Mode flag --------------------------------------------------------------

def test_photos_mode_defaults_to_test_only(monkeypatch):
    monkeypatch.delenv("WINGS_PHOTOS_MODE", raising=False)
    monkeypatch.delenv("WINGS_PHOTOS_IRB_CONFIRMED", raising=False)
    assert wings_photos.photos_mode() == "test_only"


def test_photos_mode_accepts_off(monkeypatch):
    monkeypatch.setenv("WINGS_PHOTOS_MODE", "off")
    assert wings_photos.photos_mode() == "off"


def test_photos_mode_refuses_on_without_irb_flag(monkeypatch):
    """Even with `WINGS_PHOTOS_MODE=on`, the server stays in test_only
    unless the IRB confirmation env is also set. This is the belt-and-
    braces that stops a dashboard typo shipping photos before PI sign-off."""
    monkeypatch.setenv("WINGS_PHOTOS_MODE", "on")
    monkeypatch.delenv("WINGS_PHOTOS_IRB_CONFIRMED", raising=False)
    assert wings_photos.photos_mode() == "test_only"
    monkeypatch.setenv("WINGS_PHOTOS_IRB_CONFIRMED", "1")
    assert wings_photos.photos_mode() == "on"


def test_photos_mode_rejects_unknown_values(monkeypatch):
    monkeypatch.setenv("WINGS_PHOTOS_MODE", "yolo")
    assert wings_photos.photos_mode() == "test_only"


def test_can_user_post_gates_by_mode_and_test_flag(monkeypatch):
    live = {"id": "u1", "email": "r@tamu.edu"}
    tester = {"id": "u2", "email": "lab@example.com"}

    monkeypatch.setenv("WINGS_PHOTOS_MODE", "off")
    assert not wings_photos.can_user_post(live, is_test=False)
    assert not wings_photos.can_user_post(tester, is_test=True)

    monkeypatch.setenv("WINGS_PHOTOS_MODE", "test_only")
    assert not wings_photos.can_user_post(live, is_test=False)
    assert wings_photos.can_user_post(tester, is_test=True)

    # "on" needs the IRB flag too
    monkeypatch.setenv("WINGS_PHOTOS_MODE", "on")
    monkeypatch.setenv("WINGS_PHOTOS_IRB_CONFIRMED", "1")
    assert wings_photos.can_user_post(live, is_test=False)
    assert wings_photos.can_user_post(tester, is_test=True)


# --- Image pipeline ---------------------------------------------------------

def _tiny_jpeg_with_gps() -> bytes:
    """Build a tiny JPEG that CONTAINS EXIF including GPS, so the strip
    test has something real to prove it removed. Pure Pillow — no fixture
    files on disk."""
    from PIL import Image
    img = Image.new("RGB", (40, 30), (120, 180, 120))
    # Build a minimal EXIF block with GPS tags using piexif-free syntax.
    # Pillow 10+ supports Image.getexif() + ExifTags.
    buf = io.BytesIO()
    exif_bytes = _handrolled_exif_with_gps()
    img.save(buf, format="JPEG", exif=exif_bytes)
    return buf.getvalue()


def _handrolled_exif_with_gps() -> bytes:
    """Pillow's `Image.Exif` writes EXIF including a GPS IFD. Rational
    tags on modern Pillow want `IFDRational` or `Fraction` objects (plain
    `(num, den)` tuples trip ``abs()`` in the writer). We use the
    `Fraction` route so this test fixture builds on vanilla Pillow with
    no extra deps."""
    from fractions import Fraction
    from PIL import Image
    exif = Image.Exif()
    # Camera make/model — regular ASCII tags.
    exif[0x010f] = "LLHS-Test-Camera"
    exif[0x0110] = "Model-X"
    gps_ifd = exif.get_ifd(0x8825)
    # GPSVersionID — a simple 4-byte sentinel, enough to prove the GPS
    # IFD exists in the fixture even on Pillow builds where rationals
    # are picky.
    gps_ifd[0] = b"\x02\x02\x00\x00"
    # Lat/lng: Fraction tuples, which Pillow coerces into IFDRational.
    gps_ifd[1] = "N"
    gps_ifd[2] = (Fraction(30, 1), Fraction(36, 1), Fraction(0, 1))
    gps_ifd[3] = "W"
    gps_ifd[4] = (Fraction(96, 1), Fraction(18, 1), Fraction(0, 1))
    return exif.tobytes()


def test_sniff_jpeg_png_heic_vs_junk():
    assert wings_photos.sniff_image_kind(b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 20) == "jpeg"
    assert wings_photos.sniff_image_kind(b"\x89PNG\r\n\x1a\n" + b"\x00" * 20) == "png"
    # Minimal HEIC-ish header: ....ftypheic
    assert wings_photos.sniff_image_kind(b"\x00\x00\x00\x20ftypheic\x00\x00\x00\x00") == "heic"
    # A bare text file isn't an image, even if it's called foo.jpg.
    assert wings_photos.sniff_image_kind(b"GIF89a\x00\x00\x00\x00\x00\x00") is None
    assert wings_photos.sniff_image_kind(b"not an image at all") is None


def test_process_image_strips_all_exif_including_gps():
    data = _tiny_jpeg_with_gps()

    # Confirm the fixture actually DID carry GPS before the pipeline runs —
    # otherwise the "strip" assertion would be meaningless.
    from PIL import Image
    with Image.open(io.BytesIO(data)) as im:
        exif = im.getexif()
        assert exif.get_ifd(0x8825), "fixture should have GPS IFD"

    processed = wings_photos.process_image(data, declared_kind="image/jpeg")
    with Image.open(io.BytesIO(processed.jpeg_bytes)) as cleaned:
        cleaned_exif = cleaned.getexif()
        # Pillow writes EITHER no segment or an empty block depending on
        # version; both are fine. The important assertion is "no GPS and
        # no camera make/model survived".
        assert not cleaned_exif.get_ifd(0x8825), "GPS must be gone"
        assert 0x010f not in cleaned_exif, "camera make must be gone"
        assert 0x0110 not in cleaned_exif, "camera model must be gone"


def _tiny_heic_with_gps() -> bytes:
    """Build a real HEIC fixture with camera make/model + a GPS IFD so
    the "EXIF stripped" assertion is meaningful on the HEIC path too.
    Skips gracefully if pillow-heif isn't present in the venv."""
    from fractions import Fraction
    from PIL import Image
    pytest.importorskip("pillow_heif")
    import pillow_heif
    pillow_heif.register_heif_opener()
    im = Image.new("RGB", (400, 300), (120, 180, 120))
    exif = Image.Exif()
    exif[0x010f] = "LLHS-Test-Camera"
    exif[0x0110] = "Model-X"
    gps = exif.get_ifd(0x8825)
    gps[0] = b"\x02\x02\x00\x00"
    gps[1] = "N"
    gps[2] = (Fraction(30, 1), Fraction(36, 1), Fraction(0, 1))
    buf = io.BytesIO()
    im.save(buf, format="HEIF", exif=exif.tobytes())
    return buf.getvalue()


def test_process_image_decodes_heic_and_strips_exif():
    """iPhone camera-roll format path: pillow-heif registers the decoder
    at wings_photos import, so a HEIC with GPS + camera metadata loads,
    re-encodes to JPEG, and comes out with no EXIF at all."""
    data = _tiny_heic_with_gps()
    assert wings_photos.sniff_image_kind(data) == "heic"
    processed = wings_photos.process_image(data, declared_kind="image/heic")
    # Output is JPEG (first 3 magic bytes).
    assert processed.jpeg_bytes[:3] == b"\xff\xd8\xff"
    # And EXIF is gone — GPS IFD empty, camera make/model absent.
    from PIL import Image
    with Image.open(io.BytesIO(processed.jpeg_bytes)) as cleaned:
        exif = cleaned.getexif()
        assert not exif.get_ifd(0x8825), "GPS leaked from the HEIC path"
        assert 0x010f not in exif, "camera make leaked from the HEIC path"


def test_process_image_decode_failure_surfaces_friendly_message():
    """A corrupt-but-magic-byte-looking JPEG fails inside Pillow; the
    student must see the same calm fallback for every decode failure,
    not a raw Python error string."""
    # Four JPEG magic bytes + garbage that Pillow can't decode.
    broken = b"\xff\xd8\xff\xe0" + b"\x00" * 100
    with pytest.raises(wings_photos.ImageRejected) as exc:
        wings_photos.process_image(broken, declared_kind="image/jpeg")
    assert str(exc.value) == wings_photos.FRIENDLY_IMAGE_ERROR


def test_process_image_rejects_fake_extension():
    # A PNG file with a JPEG magic header? No — the magic and the declared
    # kind must agree.
    jpeg_bytes = _tiny_jpeg_with_gps()
    with pytest.raises(wings_photos.ImageRejected):
        wings_photos.process_image(jpeg_bytes, declared_kind="image/png")


def test_process_image_rejects_not_an_image():
    with pytest.raises(wings_photos.ImageRejected):
        wings_photos.process_image(b"<html>hello</html>", declared_kind="image/jpeg")


def test_process_image_rejects_oversize():
    too_big = b"\xff\xd8\xff" + b"\x00" * (wings_photos.MAX_UPLOAD_BYTES + 1)
    with pytest.raises(wings_photos.ImageRejected):
        wings_photos.process_image(too_big, declared_kind="image/jpeg")


def test_process_image_rejects_empty():
    with pytest.raises(wings_photos.ImageRejected):
        wings_photos.process_image(b"", declared_kind="image/jpeg")


def test_process_image_resizes_long_edge_to_1600():
    from PIL import Image
    big = Image.new("RGB", (2400, 1200), (210, 210, 210))
    buf = io.BytesIO(); big.save(buf, format="JPEG"); raw = buf.getvalue()
    processed = wings_photos.process_image(raw, declared_kind="image/jpeg")
    assert max(processed.width, processed.height) == 1600
    assert processed.width / processed.height == pytest.approx(2.0, rel=0.01)


# --- Content filter ---------------------------------------------------------

def test_check_text_passes_plain_food_caption():
    r = wings_photos.check_text("Rice bowl with roasted vegetables and tofu.")
    assert r.ok and r.code is None


@pytest.mark.parametrize("bad", [
    "350 kcal in this bowl",
    "about 20g of protein",
    "roughly 2 lbs of pasta",
    "cut 100 calories by skipping cheese",
    "25% DV sodium per serving",
])
def test_check_text_blocks_numeric_nutrition(bad):
    r = wings_photos.check_text(bad)
    assert not r.ok and r.code == "numeric_nutrition"


@pytest.mark.parametrize("bad", [
    "my favourite low-cal cheat meal",
    "trying to lose weight before break",
    "a slim dinner for a slim week",
    "guilt-free pizza alternative",
])
def test_check_text_blocks_restriction_framing(bad):
    r = wings_photos.check_text(bad)
    assert not r.ok and r.code == "restriction_framing"


@pytest.mark.parametrize("bad", [
    "DM me at test@example.com",
    "+1 (555) 123-4567",
    "find my recipes @coolchef on insta",
    "https://my-blog.example.com/recipe",
])
def test_check_text_blocks_personal_contact(bad):
    r = wings_photos.check_text(bad)
    assert not r.ok and r.code == "personal_contact"


def test_check_text_blocks_insults():
    r = wings_photos.check_text("you're a dumbass for eating that")
    assert not r.ok and r.code == "insults"


def test_check_text_enforces_length_limits():
    assert not wings_photos.check_text("x" * 201).ok
    assert not wings_photos.check_text("ok", ["y" * 81]).ok
    assert not wings_photos.check_text("ok", ["a"] * 6).ok


# --- Storage adapter --------------------------------------------------------

def test_memory_storage_round_trips_bytes():
    async def _run():
        s = wings_photos.MemoryStorage()
        key = await s.put(b"abc123", "food.jpg")
        got = await s.get(key)
        return key, got
    key, got = asyncio.run(_run())
    assert isinstance(key, str) and got == b"abc123"


def test_memory_storage_delete_is_irreversible():
    async def _run():
        s = wings_photos.MemoryStorage()
        key = await s.put(b"delete-me", "f.jpg")
        await s.delete(key)
        return s, key
    s, key = asyncio.run(_run())
    with pytest.raises(FileNotFoundError):
        asyncio.run(s.get(key))


def test_default_storage_picks_blob_when_token_present(monkeypatch):
    monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", "fake-token-not-used-in-tests")
    s = wings_photos.default_storage()
    assert isinstance(s, wings_photos.VercelBlobStorage)


def test_default_storage_falls_back_to_memory_when_no_token(monkeypatch):
    monkeypatch.delenv("BLOB_READ_WRITE_TOKEN", raising=False)
    # Reset module-level cache so the fallback is observable in the test.
    import importlib
    importlib.reload(wings_photos)
    s = wings_photos.default_storage()
    assert isinstance(s, wings_photos.MemoryStorage)


# --- Preset data snapshot (no free-text reactions / reject reasons) --------

def test_reactions_are_preset_only():
    keys = {r["key"] for r in wings_photos.REACTION_PRESETS}
    assert keys == wings_photos.REACTION_KEYS
    for r in wings_photos.REACTION_PRESETS:
        assert r["label"] and r["key"]


def test_reject_reasons_are_preset_only():
    assert wings_photos.REJECT_REASONS, "there must be at least one preset reason"
    for k, label in wings_photos.REJECT_REASONS.items():
        assert isinstance(k, str) and isinstance(label, str) and label


def test_max_posts_per_study_day_is_three():
    assert wings_photos.MAX_POSTS_PER_STUDY_DAY == 3
