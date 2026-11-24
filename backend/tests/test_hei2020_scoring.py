"""Unit tests for the NCI HEI-2020 macro port (hei2020_scoring.py). Pure
functions — no server or database needed:
    python -m pytest tests/test_hei2020_scoring.py -n 0
Expected values are worked by hand from hei2020.score.macro.sas v1.0."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import hei2020_scoring as hei  # noqa: E402

COLS = hei.TOTALS_NUMERIC_COLUMNS

# Two recall days whose SUM hits every standard at a known point. Summed:
# KCAL 4000; fruit 3.2 (den 0.8 -> 5); whole fruit 0.8 (0.2 -> 2.5);
# veg+leg 2.2 (0.55 -> 2.5); dkgr+leg 0.4 (0.1 -> 2.5); whole grain 3.0
# (0.75 -> 5); dairy 2.6 (0.65 -> 5); protein 10 (2.5 -> 5); sea+plant 2.4
# (0.6 -> 3.75); MUFA+PUFA/SFA 74/40=1.85 (-> 5); refined 12.2 (3.05 -> 5);
# sodium 6200 mg (1.55 g/1000 kcal -> 5); added sugar 40.625 tsp (16.25% ->
# 5); sat fat 40 g (9% -> 8.75). Total 60.
SUMMED = {
    "KCAL": 4000, "F_TOTAL": 3.2, "F_CITMLB": 0.3, "F_OTHER": 0.5, "V_TOTAL": 2.0, "V_DRKGR": 0.2,
    "V_LEGUMES": 0.2, "G_WHOLE": 3.0, "G_REFINED": 12.2, "D_TOTAL": 2.6, "PF_MPS_TOTAL": 7.0,
    "PF_EGGS": 1.0, "PF_NUTSDS": 1.0, "PF_SOY": 0.2, "PF_LEGUMES": 0.8, "PF_SEAFD_HI": 0.4,
    "PF_SEAFD_LOW": 0.0, "MFAT": 50.0, "PFAT": 24.0, "SFAT": 40.0, "SODI": 6200.0, "ADD_SUGARS": 40.625,
}
EXPECTED = {
    "total_fruits": 5.0, "whole_fruits": 2.5, "total_vegetables": 2.5, "greens_beans": 2.5,
    "whole_grains": 5.0, "dairy": 5.0, "total_protein_foods": 5.0, "seafood_plant_proteins": 3.75,
    "fatty_acids": 5.0, "refined_grains": 5.0, "sodium": 5.0, "added_sugars": 5.0, "saturated_fats": 8.75,
}


def _split(frac):
    return [{c: SUMMED[c] * frac for c in COLS}, {c: SUMMED[c] * (1 - frac) for c in COLS}]


def test_hand_worked_person_matches_macro():
    out = hei.score_person(_split(0.6))
    assert out["recall_count"] == 2
    for cid, want in EXPECTED.items():
        assert out["components"][cid] == pytest.approx(want, abs=1e-6), cid
    assert out["total_score"] == pytest.approx(60.0, abs=1e-6)


def test_per_person_sums_recalls_before_scoring():
    # NCI's per-person method scores the SUM once; any split of the same
    # totals must give the same result. (Averaging two per-day scores would not.)
    a = hei.score_person(_split(0.5))["components"]
    b = hei.score_person(_split(0.9))["components"]
    assert a == b


def test_adequacy_capped_at_max_and_zero_when_absent():
    s = hei.score_hei2020({**hei.sum_recalls([{**{c: 0.0 for c in COLS}, "KCAL": 2000, "F_TOTAL": 50}])})
    assert s["HEI2020_TOTALFRUIT"] == 5
    assert s["HEI2020_WHOLEFRUIT"] == 0
    assert s["HEI2020_TOTALDAIRY"] == 0


def test_moderation_boundaries():
    base = {c: 0.0 for c in COLS}
    best = hei.score_hei2020(hei.sum_recalls([{**base, "KCAL": 2000, "SODI": 2200, "G_REFINED": 3.6}]))
    assert best["HEI2020_SODIUM"] == 10 and best["HEI2020_REFINEDGRAIN"] == 10  # exactly at the best standard
    worst = hei.score_hei2020(hei.sum_recalls([{**base, "KCAL": 2000, "SODI": 4000, "G_REFINED": 8.6, "ADD_SUGARS": 32.5, "SFAT": 35.6}]))
    assert worst["HEI2020_SODIUM"] == 0 and worst["HEI2020_REFINEDGRAIN"] == 0
    assert worst["HEI2020_ADDSUG"] == 0 and worst["HEI2020_SFAT"] == pytest.approx(0)


def test_fatty_acid_special_cases():
    base = {c: 0.0 for c in COLS}
    assert hei.score_hei2020(hei.sum_recalls([{**base, "KCAL": 2000}]))["HEI2020_FATTYACID"] == 0
    assert hei.score_hei2020(hei.sum_recalls([{**base, "KCAL": 2000, "MFAT": 10}]))["HEI2020_FATTYACID"] == 10
    assert hei.score_hei2020(hei.sum_recalls([{**base, "KCAL": 2000, "MFAT": 12, "SFAT": 10}]))["HEI2020_FATTYACID"] == 0


def test_zero_energy_scores_zero_everywhere():
    s = hei.score_hei2020(hei.sum_recalls([{c: 0.0 for c in COLS}]))
    assert s["HEI2020_TOTAL_SCORE"] == 0
    assert s["HEI2020_SODIUM"] == 0  # macro's kcal=0 block overrides the moderation 10s


def _csv(rows, header=None):
    header = header or (["UserName", "RecallNo"] + COLS)
    lines = [",".join(header)]
    for r in rows:
        lines.append(",".join(str(r.get(h, "")) for h in header))
    return "\n".join(lines)


def test_parse_totals_csv_groups_by_user_and_handles_bom_and_blanks():
    d1, d2 = _split(0.6)
    text = "﻿" + _csv([{**d1, "UserName": "llhs001", "RecallNo": 1}, {**d2, "UserName": "llhs001", "RecallNo": 2},
                            {"UserName": "llhs002", "RecallNo": 1, "KCAL": 1800}])
    by_user = hei.parse_totals_csv(text)
    assert set(by_user) == {"llhs001", "llhs002"}
    assert len(by_user["llhs001"]) == 2
    assert by_user["llhs002"][0]["F_TOTAL"] == 0.0  # blank cell -> 0
    assert hei.score_person(by_user["llhs001"])["total_score"] == pytest.approx(60.0, abs=1e-6)


def test_parse_rejects_wrong_file():
    with pytest.raises(hei.Asa24FileError, match="Totals"):
        hei.parse_totals_csv("UserName,FoodCode,KCAL\nx,1,2\n")


def test_parse_rejects_non_numeric():
    with pytest.raises(hei.Asa24FileError, match="Line 2: KCAL"):
        hei.parse_totals_csv(_csv([{"UserName": "a", "KCAL": "lots"}]))
