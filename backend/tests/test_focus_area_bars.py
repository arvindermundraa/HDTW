"""Combined Grains/Fats bars (nutrition team 2026-11-06, item 1).

The team confirmed: each pair of HEI-2020 components that feeds a single
focus area should be combined by adding the component scores and
dividing by the sum of their maximum points. Tapping the combined bar
expands it to show the two sub-component bars. No absolute HEI scores or
maximum-point totals leave the server; the UI gets 0.0–1.0 fills."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "llhs_unit_unused")
import focus_areas  # noqa: E402
import server  # noqa: E402


COMPONENTS = server.HEI2020_BY_ID


def test_grains_bar_combines_whole_and_refined_grains():
    scores = {c["id"]: c["max_score"] for c in server.HEI2020_COMPONENTS}
    scores["whole_grains"] = 5    # 5/10
    scores["refined_grains"] = 3  # 3/10
    out = {b["id"]: b for b in focus_areas.bars(scores, COMPONENTS)}
    grains = out["grains"]
    # (5 + 3) / (10 + 10) == 0.4
    assert abs(grains["fill"] - 0.4) < 1e-9
    assert grains["expandable"] is True
    sub = {c["id"]: c for c in grains["components"]}
    assert set(sub) == {"whole_grains", "refined_grains"}
    assert abs(sub["whole_grains"]["fill"] - 0.5) < 1e-9
    assert abs(sub["refined_grains"]["fill"] - 0.3) < 1e-9


def test_fats_bar_combines_fatty_acids_and_saturated_fats():
    scores = {c["id"]: c["max_score"] for c in server.HEI2020_COMPONENTS}
    scores["fatty_acids"] = 8     # 8/10
    scores["saturated_fats"] = 4  # 4/10
    bars = {b["id"]: b for b in focus_areas.bars(scores, COMPONENTS)}
    fats = bars["fats"]
    # (8 + 4) / (10 + 10) == 0.6
    assert abs(fats["fill"] - 0.6) < 1e-9
    assert fats["expandable"] is True


def test_single_component_bar_is_not_expandable():
    scores = {c["id"]: c["max_score"] for c in server.HEI2020_COMPONENTS}
    bars = {b["id"]: b for b in focus_areas.bars(scores, COMPONENTS)}
    assert bars["sodium"]["expandable"] is False
    assert bars["dairy"]["expandable"] is False


def test_bars_omit_unscored_areas_and_never_leak_absolute_points():
    scores = {c["id"]: c["max_score"] for c in server.HEI2020_COMPONENTS}
    del scores["whole_grains"]
    del scores["refined_grains"]
    bars = {b["id"]: b for b in focus_areas.bars(scores, COMPONENTS)}
    assert "grains" not in bars  # both components missing -> area dropped

    # Only fills come through (and ids/labels); nothing with points.
    for b in bars.values():
        assert set(b) == {"id", "label", "fill", "components", "expandable"}
        for c in b["components"]:
            assert set(c) == {"id", "label", "fill", "kind"}
            assert 0.0 <= c["fill"] <= 1.0
        assert 0.0 <= b["fill"] <= 1.0
