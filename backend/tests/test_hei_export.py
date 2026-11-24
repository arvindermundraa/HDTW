"""Unit tests for hei_export.scores_csv: the staff page's scores download.
No server or database."""
import csv
import io

import hei_export

COMPONENTS = ["total_fruits", "whole_grains"]
LABELS = {"baseline": "Baseline", "checkin_1": "Week 4 check-in", "checkin_2": "Week 8 check-in"}
ORDER = ["baseline", "checkin_1", "checkin_2"]
USERS = {"u1": {"name": "Rachel", "email": "rachel@tamu.edu"},
         "u2": {"name": "Amy", "email": "amy@tamu.edu", "is_test_account": False}}
LINKS = {"u1": "LLHSTEST7", "u2": "LLHSTEST3"}


def _rows(text):
    return list(csv.DictReader(io.StringIO(text)))


def test_one_row_per_participant_and_point_in_study_order():
    assessments = [
        {"user_id": "u1", "assessment_type": "checkin_1", "components": {"total_fruits": 3.0, "whole_grains": 4.5},
         "total_score": 61.2, "recall_count": 2, "recall_dates": ["2026-11-10", "2026-11-14"], "recorded_at": "2026-11-16"},
        {"user_id": "u1", "assessment_type": "baseline", "components": {"total_fruits": 2.0, "whole_grains": 1.5},
         "total_score": 52.0, "recall_count": 1, "recall_dates": ["2026-10-15"], "recorded_at": "2026-10-19",
         "warnings": ["1 recall(s) in file — study design expects 2."], "summed_inputs": {"KCAL": 1850.0}},
        {"user_id": "u2", "assessment_type": "baseline", "components": {"total_fruits": 5.0}, "total_score": 70.1,
         "recall_count": 2, "recall_dates": ["2026-10-15", "2026-10-18"], "recorded_at": "2026-10-19"},
    ]
    rows = _rows(hei_export.scores_csv(USERS, LINKS, assessments, COMPONENTS, LABELS, ORDER))
    assert [(r["name"], r["assessment_type"]) for r in rows] == [
        ("Amy", "baseline"), ("Rachel", "baseline"), ("Rachel", "checkin_1")]
    rachel = rows[1]
    assert rachel["asa24_username"] == "LLHSTEST7"
    assert rachel["assessment_label"] == "Baseline"
    assert (rachel["total_fruits"], rachel["total_score"], rachel["recall_count"]) == ("2.0", "52.0", "1")
    assert rachel["warnings"].startswith("1 recall(s)")
    assert rachel["input_KCAL"] == "1850.0"
    assert rows[0]["whole_grains"] == ""  # missing component stays blank, never 0
    assert rows[2]["recall_dates"] == "2026-11-10; 2026-11-14"


def test_empty_export_still_has_a_header():
    text = hei_export.scores_csv(USERS, LINKS, [], COMPONENTS, LABELS, ORDER)
    assert text.splitlines()[0].startswith("name,email,asa24_username")
    assert len(text.splitlines()) == 1
