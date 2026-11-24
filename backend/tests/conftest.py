"""Shared test setup for the unit suite.

Future Me's "From your meals" block (and therefore /future-me and every
/chat turn) looks up today's dining menus. Nothing in this suite should
reach apiv4.dineoncampus.com, so the lookup is stubbed to "no menus" for
every test that imports `server`; a test that wants menus (see
test_from_your_meals.py) patches `server._twin_menus_today` itself after
this fixture has run.
"""
import sys

import pytest


@pytest.fixture(autouse=True)
def _no_live_dining_lookups(monkeypatch):
    srv = sys.modules.get("server")
    if srv is not None:
        async def no_menus():
            return {hall: {} for hall in srv.DINING_HALLS}
        monkeypatch.setattr(srv, "_twin_menus_today", no_menus)
    yield
