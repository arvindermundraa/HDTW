"""dining_scraper.fetch_live_menu against the REAL apiv4.dineoncampus.com
response shape, captured on 2026-10-26 (tests/fixtures/apiv4_dineoncampus_2026-10-26.json)
and replayed through an httpx MockTransport — the build sandbox can't reach
the live host, so this is how the parser stays verified against what the
API actually sends.
    python -m pytest tests/test_dining_scraper.py -n 0"""
import asyncio
import json
import os
import sys
from datetime import date

import httpx
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import dining_scraper  # noqa: E402

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "apiv4_dineoncampus_2026-10-26.json")
CAPTURED = json.load(open(FIXTURE))
DAY = date(2026, 10, 26)


class Replay:
    """Serves the captured responses; counts the calls it answered."""

    def __init__(self, closed=False, periods_status=200, menu_status=200):
        self.calls = []
        self.closed = closed
        self.periods_status = periods_status
        self.menu_status = menu_status

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(str(request.url))
        assert request.headers["user-agent"].startswith("Mozilla/5.0"), "the API needs a browser UA"
        hall = next(h for h, loc in dining_scraper.LOCATION_IDS.items() if loc in request.url.path)
        if request.url.path.endswith("/periods/"):
            if request.url.params.get("date") == "2027-07-04":
                return httpx.Response(200, json=CAPTURED["_far_future_periods_response"])
            return httpx.Response(self.periods_status, json=CAPTURED[hall]["periods_response"])
        body = dict(CAPTURED[hall]["menu_responses"][request.url.params["period"]])
        if self.closed:
            body["closedOnDate"] = True
        return httpx.Response(self.menu_status, json=body)

    def transport(self):
        return httpx.MockTransport(self.handler)


def fetch(hall, period, replay, on_date=DAY):
    """Sync wrapper (the suite doesn't use pytest-asyncio)."""
    return asyncio.run(dining_scraper.fetch_live_menu(hall, period, on_date=on_date, transport=replay.transport()))


@pytest.mark.parametrize("hall", ["sbisa", "commons"])
@pytest.mark.parametrize("period", ["breakfast", "lunch", "dinner"])
def test_every_hall_and_period_parses_into_the_app_shape(hall, period):
    replay = Replay()
    menu = fetch(hall, period, replay)
    assert menu is not None
    assert menu["source"] == "live" and menu["period"] == period and menu["fetched_date"] == "2026-10-26"
    assert menu["hall"] == dining_scraper.HALL_DISPLAY_NAMES[hall]
    assert menu["stations"], "live menus always have at least one station"
    for st in menu["stations"]:
        assert st["station"] and st["items"]
        for it in st["items"]:
            assert it["id"].startswith(f"{hall}_") and it["name"]
            assert set(it) == {"id", "name", "portion", "desc", "ingredients", "labels"}


def test_breakfast_uses_the_menu_embedded_in_the_periods_response():
    """The periods call already carries the default period's full menu —
    one round-trip instead of two for that period."""
    replay = Replay()
    menu = fetch("sbisa", "breakfast", replay)
    assert len(replay.calls) == 1 and replay.calls[0].endswith("periods/?date=2026-10-26")
    names = [it["name"] for st in menu["stations"] for it in st["items"]]
    assert "Oatmeal" in names and "Low Fat Vanilla Yogurt" in names


def test_other_periods_make_the_second_call():
    replay = Replay()
    menu = fetch("commons", "lunch", replay)
    assert len(replay.calls) == 2 and "/menu?" in replay.calls[1] and "period=" in replay.calls[1]
    names = [it["name"] for st in menu["stations"] for it in st["items"]]
    assert "Crispy Chicken Sandwich" in names


def test_nutrient_numbers_never_leave_the_scraper():
    """The live feed carries calories and a nutrients table per item. This
    app never shows those, and the raw menu goes to the client, so they're
    dropped at the source."""
    menu = fetch("sbisa", "breakfast", Replay())
    for st in menu["stations"]:
        for it in st["items"]:
            assert "calories" not in it and "nutrients" not in it
    assert "kcal" not in json.dumps(menu)


def test_ingredients_and_allergen_labels_are_kept():
    menu = fetch("sbisa", "breakfast", Replay())
    eggs = next(it for st in menu["stations"] for it in st["items"] if it["name"] == "Scrambled Eggs")
    assert "Egg" in eggs["ingredients"]
    assert "Egg" in eggs["labels"] and "Vegetarian" in eggs["labels"]


def test_a_day_with_no_published_menu_falls_back():
    assert fetch("sbisa", "lunch", Replay(), on_date=date(2027, 7, 4)) is None


def test_closed_hall_and_http_errors_fall_back_without_raising():
    assert fetch("commons", "dinner", Replay(closed=True)) is None
    assert fetch("commons", "dinner", Replay(menu_status=503)) is None
    assert fetch("commons", "dinner", Replay(periods_status=403)) is None
    assert fetch("nowhere", "dinner", Replay()) is None


def test_parse_period_menu_is_pure_and_defensive():
    assert dining_scraper.parse_period_menu("sbisa", "lunch", {}, "2026-10-26") is None
    assert dining_scraper.parse_period_menu("sbisa", "lunch", {"categories": [{"items": [{"name": " "}]}]},
                                            "2026-10-26") is None
    menu = dining_scraper.parse_period_menu(
        "sbisa", "lunch", {"categories": [{"name": "Grill", "items": [{"name": "Cheeseburger", "filters": None}]}]},
        "2026-10-26")
    assert menu["stations"][0]["items"][0] == {
        "id": "sbisa_cheeseburger", "name": "Cheeseburger", "portion": "", "desc": "", "ingredients": "", "labels": []}
