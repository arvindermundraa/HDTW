"""
HEI-2020 scoring from ASA24 "Totals" exports — a line-for-line Python port
of NCI's published SAS code, so study staff never have to run SAS by hand.

Sources (downloaded 2026-09-24 from https://epi.grants.cancer.gov/hei/sas-code.html):
  - hei2020.score.macro.sas, VERSION 1.0 12/11/2024 — the density/score rules
    in `score_hei2020()` below mirror it statement by statement.
  - "HEI-2015 ByPerson SAS program_ASA24-2016-2018" — NCI's ASA24 example.
    The page says HEI-2020 is computed "by substituting the HEI-2020 macro
    into the example", so the derived inputs (`derive_inputs()`) and the
    per-person method (SUM every recall's totals, then score ONCE — not an
    average of per-day scores) come from that program.

ASA24 has no API and its site may not be scraped, so the one manual step is
staff downloading the Totals CSV from the ASA24 Researcher website; see the
/research/asa24/* endpoints in server.py for the upload path.

Pure functions only — no database or network access — so this can be
unit-tested and cross-checked against NCI's SAS output or the R package
`dietaryindex` on the same export.
"""
import csv
import io
import math
from typing import Any, Dict, List, Optional, Tuple

# Columns of the ASA24 Totals file that the NCI example reads.
TOTALS_ID_COLUMNS = ["UserName"]
TOTALS_NUMERIC_COLUMNS = [
    "KCAL", "F_TOTAL", "F_CITMLB", "F_OTHER", "V_TOTAL", "V_DRKGR", "V_LEGUMES",
    "G_WHOLE", "G_REFINED", "D_TOTAL", "PF_MPS_TOTAL", "PF_EGGS", "PF_NUTSDS",
    "PF_SOY", "PF_LEGUMES", "PF_SEAFD_HI", "PF_SEAFD_LOW", "MFAT", "PFAT",
    "SFAT", "SODI", "ADD_SUGARS",
]
REQUIRED_TOTALS_COLUMNS = TOTALS_ID_COLUMNS + TOTALS_NUMERIC_COLUMNS

# Macro inputs summed per person (Step 2 of the NCI example's PROC MEANS).
SUMMED_INPUTS = [
    "KCAL", "VTOTALLEG", "VDRKGRLEG", "F_TOTAL", "FWHOLEFRT", "G_WHOLE", "D_TOTAL",
    "PFALLPROTLEG", "PFSEAPLANTLEG", "MONOPOLY", "SFAT", "SODI", "G_REFINED", "ADD_SUGARS",
]

# NCI macro output name -> the app's component id (server.HEI2020_COMPONENTS).
NCI_TO_COMPONENT_ID = {
    "HEI2020_TOTALFRUIT": "total_fruits",
    "HEI2020_WHOLEFRUIT": "whole_fruits",
    "HEI2020_TOTALVEG": "total_vegetables",
    "HEI2020_GREEN_AND_BEAN": "greens_beans",
    "HEI2020_WHOLEGRAIN": "whole_grains",
    "HEI2020_TOTALDAIRY": "dairy",
    "HEI2020_TOTPROT": "total_protein_foods",
    "HEI2020_SEAPLANT_PROT": "seafood_plant_proteins",
    "HEI2020_FATTYACID": "fatty_acids",
    "HEI2020_REFINEDGRAIN": "refined_grains",
    "HEI2020_SODIUM": "sodium",
    "HEI2020_ADDSUG": "added_sugars",
    "HEI2020_SFAT": "saturated_fats",
}


class Asa24FileError(ValueError):
    """The uploaded file isn't a usable ASA24 Totals export. Message is safe
    to show to study staff."""


def derive_inputs(row: Dict[str, float]) -> Dict[str, float]:
    """Step 1 of the NCI example: the combined variables the macro expects.
    Legumes count toward vegetables AND protein, exactly as NCI adds them."""
    return {
        "KCAL": row["KCAL"],
        "F_TOTAL": row["F_TOTAL"],
        "FWHOLEFRT": row["F_CITMLB"] + row["F_OTHER"],
        "MONOPOLY": row["MFAT"] + row["PFAT"],
        "VTOTALLEG": row["V_TOTAL"] + row["V_LEGUMES"],
        "VDRKGRLEG": row["V_DRKGR"] + row["V_LEGUMES"],
        "PFALLPROTLEG": row["PF_MPS_TOTAL"] + row["PF_EGGS"] + row["PF_NUTSDS"] + row["PF_SOY"] + row["PF_LEGUMES"],
        "PFSEAPLANTLEG": row["PF_SEAFD_HI"] + row["PF_SEAFD_LOW"] + row["PF_NUTSDS"] + row["PF_SOY"] + row["PF_LEGUMES"],
        "G_WHOLE": row["G_WHOLE"],
        "D_TOTAL": row["D_TOTAL"],
        "SFAT": row["SFAT"],
        "SODI": row["SODI"],
        "G_REFINED": row["G_REFINED"],
        "ADD_SUGARS": row["ADD_SUGARS"],
    }


def sum_recalls(rows: List[Dict[str, float]]) -> Dict[str, float]:
    """Step 2 of the NCI example: per-person SUM over every recall day."""
    totals = {k: 0.0 for k in SUMMED_INPUTS}
    for r in rows:
        d = derive_inputs(r)
        for k in SUMMED_INPUTS:
            totals[k] += d[k]
    return totals


def _adequacy(amount: float, kcal: float, standard: float, max_points: float) -> Tuple[Optional[float], float]:
    den = amount / (kcal / 1000) if kcal > 0 else None
    if not den:  # macro: density 0 (or no energy) scores 0
        return den, 0.0
    return den, min(max_points, max_points * (den / standard))


def _moderation(value: Optional[float], best: float, worst: float) -> float:
    # SAS compares a missing value as smaller than any number, so with
    # kcal=0 these branches score 10 — then the kcal=0 block zeroes them.
    if value is None or value <= best:
        return 10.0
    if value >= worst:
        return 0.0
    return 10 - (10 * (value - best) / (worst - best))


def score_hei2020(i: Dict[str, float]) -> Dict[str, Any]:
    """Port of %HEI2020 in hei2020.score.macro.sas v1.0. `i` holds the
    SUMMED_INPUTS for one person (or one day, for per-day scoring). Returns
    NCI-named densities and component scores plus the total."""
    kcal = i["KCAL"]
    out: Dict[str, Any] = {}

    # Adequacy components: standard is the density earning full points.
    for name, den_name, key, standard, pts in [
        ("HEI2020_TOTALFRUIT", "FRTDEN", "F_TOTAL", 0.8, 5),
        ("HEI2020_WHOLEFRUIT", "WHFRDEN", "FWHOLEFRT", 0.4, 5),
        ("HEI2020_TOTALVEG", "VEGDEN", "VTOTALLEG", 1.1, 5),
        ("HEI2020_GREEN_AND_BEAN", "GRBNDEN", "VDRKGRLEG", 0.2, 5),
        ("HEI2020_WHOLEGRAIN", "WGRNDEN", "G_WHOLE", 1.5, 10),
        ("HEI2020_TOTALDAIRY", "DAIRYDEN", "D_TOTAL", 1.3, 10),
        ("HEI2020_TOTPROT", "PROTDEN", "PFALLPROTLEG", 2.5, 5),
        ("HEI2020_SEAPLANT_PROT", "SEAPLDEN", "PFSEAPLANTLEG", 0.8, 5),
    ]:
        out[den_name], out[name] = _adequacy(i[key], kcal, standard, pts)

    # Fatty acids: (MUFA+PUFA)/SFA ratio, 0 points at <=1.2, 10 at >=2.5.
    sfat, monopoly = i["SFAT"], i["MONOPOLY"]
    faratio = monopoly / sfat if sfat > 0 else None
    out["FARATIO"] = faratio
    if sfat == 0 and monopoly == 0:
        out["HEI2020_FATTYACID"] = 0.0
    elif sfat == 0 and monopoly > 0:
        out["HEI2020_FATTYACID"] = 10.0
    elif faratio is None:  # sfat == 0 with negative monopoly: SAS missing <= FARMIN
        out["HEI2020_FATTYACID"] = 0.0
    elif faratio >= 2.5:
        out["HEI2020_FATTYACID"] = 10.0
    elif faratio <= 1.2:
        out["HEI2020_FATTYACID"] = 0.0
    else:
        out["HEI2020_FATTYACID"] = 10 * ((faratio - 1.2) / (2.5 - 1.2))

    # Moderation components: less is better.
    rgden = i["G_REFINED"] / (kcal / 1000) if kcal > 0 else None
    sodden = i["SODI"] / kcal if kcal > 0 else None  # mg/kcal == g per 1000 kcal
    addsug_perc = 100 * (i["ADD_SUGARS"] * 16 / kcal) if kcal > 0 else None  # tsp -> 4 g -> 16 kcal
    sfat_perc = 100 * (sfat * 9 / kcal) if kcal > 0 else None
    out.update({"RGDEN": rgden, "SODDEN": sodden, "ADDSUG_PERC": addsug_perc, "SFAT_PERC": sfat_perc})
    out["HEI2020_REFINEDGRAIN"] = _moderation(rgden, 1.8, 4.3)
    out["HEI2020_SODIUM"] = _moderation(sodden, 1.1, 2.0)
    out["HEI2020_ADDSUG"] = _moderation(addsug_perc, 6.5, 26)
    out["HEI2020_SFAT"] = _moderation(sfat_perc, 8, 16)

    if kcal == 0:
        for name in NCI_TO_COMPONENT_ID:
            out[name] = 0.0

    out["HEI2020_TOTAL_SCORE"] = sum(out[name] for name in NCI_TO_COMPONENT_ID)
    return out


def component_scores(nci_scores: Dict[str, Any], ndigits: int = 2) -> Dict[str, float]:
    """NCI-named scores -> {app component id: score}, the shape
    /research/hei2020-assessments has always stored."""
    return {cid: round(float(nci_scores[name]), ndigits) for name, cid in NCI_TO_COMPONENT_ID.items()}


def _to_float(raw: Any, column: str, line: int) -> float:
    try:
        v = float(str(raw).strip())
    except ValueError:
        raise Asa24FileError(f"Line {line}: {column} is not a number ({raw!r}).")
    if math.isnan(v) or math.isinf(v):
        raise Asa24FileError(f"Line {line}: {column} is not a finite number.")
    return v


def parse_totals_csv(text: str) -> Dict[str, List[Dict[str, float]]]:
    """Reads an ASA24 Totals CSV into {UserName: [one dict per recall]}.
    Blank numeric cells are treated as 0 (a food group nobody ate), matching
    how PROC MEANS sums skip missing values. Raises Asa24FileError on a file
    that is missing required columns or holds non-numeric values."""
    text = text.lstrip("﻿")  # Excel-saved CSVs often carry a BOM
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise Asa24FileError("The file is empty.")
    header = {h.strip(): h for h in reader.fieldnames if h}
    missing = [c for c in REQUIRED_TOTALS_COLUMNS if c not in header]
    if missing:
        raise Asa24FileError(
            "This doesn't look like an ASA24 'Totals' file — missing column(s): "
            + ", ".join(missing[:8]) + ("…" if len(missing) > 8 else "")
            + ". Export the daily 'Totals' analysis file from the ASA24 Researcher website."
        )
    by_user: Dict[str, List[Dict[str, float]]] = {}
    for line, raw in enumerate(reader, start=2):
        username = (raw.get(header["UserName"]) or "").strip()
        if not username:
            continue
        row: Dict[str, Any] = {}
        for col in TOTALS_NUMERIC_COLUMNS:
            cell = raw.get(header[col])
            row[col] = 0.0 if cell is None or str(cell).strip() == "" else _to_float(cell, col, line)
        for optional in ("RecallNo", "IntakeStartDateTime", "ReportingDate"):
            if optional in header:
                row[optional] = (raw.get(header[optional]) or "").strip()
        row["_line"] = line
        by_user.setdefault(username, []).append(row)
    if not by_user:
        raise Asa24FileError("No recall rows with a UserName were found in the file.")
    return by_user


def score_person(recalls: List[Dict[str, float]]) -> Dict[str, Any]:
    """Per-person HEI-2020 (NCI 'simple algorithm, per person') for one
    participant's recalls, plus the summed inputs kept for audit."""
    summed = sum_recalls(recalls)
    nci = score_hei2020(summed)
    return {
        "recall_count": len(recalls),
        "summed_inputs": {k: round(v, 4) for k, v in summed.items()},
        "components": component_scores(nci),
        "total_score": round(nci["HEI2020_TOTAL_SCORE"], 2),
        "nci_output": {k: (None if v is None else round(float(v), 4)) for k, v in nci.items()},
    }
