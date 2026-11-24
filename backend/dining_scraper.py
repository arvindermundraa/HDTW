"""
Aggie Dining menu source — Commons + Sbisa.

HOW THIS WORKS (first verified 2026-08-27, re-verified 2026-10-26):

  The public dineoncampus.com site is a Vite SPA — raw HTML is just a shell
  (<div id="app">), so HTML scraping does not work server-side.

  The backing REST API is at https://apiv4.dineoncampus.com (NOT the older
  api.dineoncampus.com/v1 which is Cloudflare-blocked). This v4 API returns
  JSON directly, provided a browser User-Agent is sent.

  Verified two-step flow:
    Step 1: GET /locations/{location_id}/periods/?date={YYYY-MM-DD}
            → {"locationId", "date", "periods": [{id, name, slug, isDefault,
               inWindow}], "menu": {...}}. `periods` is [] on a day the hall
               publishes nothing (e.g. a holiday). `menu` is the FULL menu of
               the default period (breakfast today), in the same shape step 2
               returns — so for that period step 2 can be skipped.
    Step 2: GET /locations/{location_id}/menu?date={YYYY-MM-DD}&period={period_id}
            → {"id", "locationId", "date", "closedOnDate": bool,
               "status": {label, message, color}, "updatedAt",
               "period": {id, name, slug, "categories": [{id, name, sortOrder,
               "items": [{id, name, desc, portion, ingredients, filters: [{name,
               ...}], nutrients: [...], calories, ...}]}]}}

  Verified IDs (discovered 2026-08-27, still valid 2026-10-26):
    TAMU site ID:  5751fd4290975b60e0489534
    Commons:       59972586ee596fe55d2eef75
    Sbisa:         587909deee596f31cedc179c

  Period IDs are date-specific — they change day to day — so we always look
  them up fresh from Step 1 rather than hardcoding them.

  A scrape failure must NEVER break a student's meal-logging request.
  fetch_live_menu() returns None on any failure and callers fall back to the
  sample menus in server.py.

WHAT WE KEEP FROM EACH ITEM — and what we deliberately drop:
  Kept: id, name, portion, desc, ingredients (a plain text list), and
  `labels` — the API's own qualitative "filters" (allergens such as Egg,
  Milk, Wheat, Soy, Sesame; diet labels such as Vegan, Vegetarian). The
  allergen labels make the app's allergy suppression far more reliable than
  name matching alone ("Brioche Bun" says nothing about egg; its label does).
  Dropped: `calories` and the whole `nutrients` array. This app never shows
  a calorie or nutrient number to a participant, and the raw menu is sent to
  the client as-is, so those numbers are stripped right here at the source
  rather than trusted to be hidden downstream.

VERIFICATION LOG:
  2026-08-27 — endpoint discovered and verified 6/6 (hall x period) in a
  session with live internet access.
  2026-10-26 — re-verified from a real browser on a team member's machine:
  both halls, all three periods, 77–133 items each, same response shape as
  documented above; a far-future date returns HTTP 200 with "periods": [].
  The build sandbox itself still cannot reach apiv4.dineoncampus.com
  (outbound allowlist), so `tests/test_dining_scraper.py` replays the
  captured real response shape through this parser instead of hitting the
  network. The deployed app (Vercel) has no such restriction.
"""
import logging
from datetime import date as date_cls
from typing import Any, List, Optional

import httpx

logger = logging.getLogger("llhs.dining")

API_BASE = "https://apiv4.dineoncampus.com"

# Verified location IDs for TAMU College Station (stable — these are
# permanent identifiers, not date-specific like period IDs).
LOCATION_IDS = {
    "commons": "59972586ee596fe55d2eef75",
    "sbisa":   "587909deee596f31cedc179c",
}

HALL_DISPLAY_NAMES = {
    "commons": "The Commons Dining Hall (South Campus)",
    "sbisa":   "Sbisa Dining Hall (North Campus)",
}

# A browser User-Agent is required — the API rejects obvious bot agents.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Origin": "https://dineoncampus.com",
    "Referer": "https://dineoncampus.com/tamu/",
}

# Fields on each live item that must never reach the app. Listed explicitly
# so a future reader sees the decision, not just its absence.
_NEVER_KEEP = ("calories", "nutrients")


def _slug(name: str) -> str:
    return "".join(c.lower() if c.isalnum() else "_" for c in name).strip("_") or "item"


def _clean_text(value: Any, limit: int = 400) -> str:
    return (value if isinstance(value, str) else "").strip()[:limit]


def _labels(item: dict) -> List[str]:
    """The API's qualitative filter names (allergens and diet labels), as
    plain strings. A trailing '*' marks a "may contain" allergen on the
    live feed; keep the mark so callers can tell the two apart."""
    out: List[str] = []
    for f in item.get("filters") or []:
        name = _clean_text((f or {}).get("name"), 60) if isinstance(f, dict) else ""
        if name and name not in out:
            out.append(name)
    return out


def parse_period_menu(hall: str, period: str, period_data: dict, on_date: str) -> Optional[dict]:
    """Turns the API's `period` object into the app's menu shape:
    {hall, stations: [{station, items: [{id, name, portion, desc,
    ingredients, labels}]}], source: "live", fetched_date, period}.
    Returns None when nothing parseable is there. Pure; no network."""
    try:
        categories = period_data.get("categories", [])
        stations = []
        for cat in categories:
            items = []
            for item in cat.get("items", []) or []:
                name = _clean_text((item or {}).get("name"), 200)
                if not name:
                    continue
                items.append({
                    "id": f"{hall}_{_slug(name)}",
                    "name": name,
                    "portion": _clean_text(item.get("portion"), 60),
                    "desc": _clean_text(item.get("desc"), 200),
                    "ingredients": _clean_text(item.get("ingredients"), 2000),  # allergy matching reads all of it
                    "labels": _labels(item),
                })
            if items:
                stations.append({
                    "station": _clean_text(cat.get("name"), 80) or "Menu",
                    "items": items,
                })

        if not stations:
            logger.warning(f"No stations parsed for {hall}/{period} on {on_date}")
            return None

        return {
            "hall": HALL_DISPLAY_NAMES.get(hall, hall),
            "stations": stations,
            "source": "live",
            "fetched_date": on_date,
            "period": period,
        }
    except (KeyError, TypeError, AttributeError) as e:
        logger.warning(f"Unexpected apiv4 response shape for {hall}/{period} on {on_date}: {e}")
        return None


async def fetch_live_menu(
    hall: str,
    period: str,
    on_date: Optional[date_cls] = None,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> Optional[dict]:
    """Fetch the live menu from apiv4.dineoncampus.com.

    Two-step:
      1. Fetch available periods for the date to get the period_id. If the
         response already carries the full menu for the period we want
         (the hall's default period), use it and skip step 2.
      2. Otherwise fetch the full menu for that period_id.

    Returns None on ANY failure — callers must treat None as "fall back to
    sample data." This function never raises. `transport` is for tests
    (an httpx.MockTransport replaying captured responses)."""
    location_id = LOCATION_IDS.get(hall)
    if not location_id:
        logger.warning(f"Unknown hall key: {hall!r}")
        return None

    d = (on_date or date_cls.today()).isoformat()

    try:
        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True, transport=transport) as client:

            # ---- Step 1: get period IDs for this date ----
            r_periods = await client.get(
                f"{API_BASE}/locations/{location_id}/periods/",
                params={"date": d},
                headers=_HEADERS,
            )
            if r_periods.status_code != 200:
                logger.warning(
                    f"apiv4 periods endpoint returned HTTP {r_periods.status_code} "
                    f"for {hall} on {d}"
                )
                return None

            body = r_periods.json()
            periods = body.get("periods") or []
            matched = next(
                (p for p in periods if str(p.get("slug", "")).lower() == period.lower()),
                None,
            )
            if not matched:
                logger.info(
                    f"Period '{period}' not available for {hall} on {d}. "
                    f"Available: {[p.get('slug') for p in periods]}"
                )
                return None

            period_id = matched["id"]

            # The periods response embeds the default period's whole menu —
            # same shape as step 2 — so use it when it's the one we want.
            embedded = ((body.get("menu") or {}).get("period") or {})
            if embedded.get("id") == period_id and embedded.get("categories"):
                period_data = embedded
            else:
                # ---- Step 2: get full menu for that period ----
                r_menu = await client.get(
                    f"{API_BASE}/locations/{location_id}/menu",
                    params={"date": d, "period": period_id},
                    headers=_HEADERS,
                )
                if r_menu.status_code != 200:
                    logger.warning(
                        f"apiv4 menu endpoint returned HTTP {r_menu.status_code} "
                        f"for {hall}/{period} on {d}"
                    )
                    return None
                menu_body = r_menu.json()
                if menu_body.get("closedOnDate"):
                    logger.info(f"{hall} is marked closed on {d}")
                    return None
                period_data = menu_body.get("period") or {}

    except Exception as e:
        logger.warning(f"Live dining fetch failed for {hall}/{period} on {d}: {e}")
        return None

    return parse_period_menu(hall, period, period_data, d)
