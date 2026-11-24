"""Unit tests for asa24_schedule: recall windows, the recall card state, the
upload date filter and which assessment counts as current.
Pure functions — no server or database needed."""
from datetime import date, timedelta

import asa24_schedule as sch

START = date(2026, 10, 1)


def test_windows_follow_the_protocol_constants():
    ws = {w["assessment_type"]: w for w in sch.windows(START)}
    assert ws["baseline"]["opens_on"] == START
    assert ws["baseline"]["due_by"] == START + timedelta(days=sch.RECALL_WINDOW_DAYS)
    c2 = ws["checkin_2"]
    # Check-ins are now RECALL_WINDOW_DAYS long, with CHECKIN_LEEWAY_BEFORE_DAYS
    # of that window before the week-8 centre and the rest after.
    assert c2["opens_on"] == START + timedelta(days=2 * sch.CHECKIN_INTERVAL_DAYS - sch.CHECKIN_LEEWAY_BEFORE_DAYS)
    assert c2["due_by"] == c2["opens_on"] + timedelta(days=sch.RECALL_WINDOW_DAYS)
    # Windows never overlap, so every recall date maps to at most one point.
    ordered = sch.windows(START)
    assert all(a["due_by"] < b["opens_on"] for a, b in zip(ordered, ordered[1:]))


def test_every_window_is_seven_days_long():
    """11/6 — the team asked that every recall window (baseline and each
    check-in) stays open for 7 days. Guard this against future edits."""
    for offset in range(7):  # whatever weekday the participant joined on
        for w in sch.windows(START + timedelta(days=offset)):
            assert (w["due_by"] - w["opens_on"]).days == sch.RECALL_WINDOW_DAYS, w


def test_three_recalls_day_1_week_4_week_8():
    ws = sch.windows(START)
    assert [w["assessment_type"] for w in ws] == ["baseline", "checkin_1", "checkin_2"]
    assert ws[0]["opens_on"] == START
    # Week 4 and week 8 recalls open CHECKIN_LEEWAY_BEFORE_DAYS before the
    # centre day (day 28, day 56) and stay open for RECALL_WINDOW_DAYS.
    assert ws[1]["opens_on"] + timedelta(days=sch.CHECKIN_LEEWAY_BEFORE_DAYS) == START + timedelta(days=28)
    assert ws[2]["opens_on"] + timedelta(days=sch.CHECKIN_LEEWAY_BEFORE_DAYS) == START + timedelta(days=56)


def test_baseline_open_on_day_one():
    st = sch.recall_status(START, START, {}, [])
    assert (st["assessment_type"], st["state"], st["days_until_open"]) == ("baseline", "open", 0)


def test_finished_stays_finished_until_imported():
    finished = {"baseline": ["2026-10-03T12:00:00+00:00"]}
    later = START + timedelta(days=20)  # well past the baseline window
    st = sch.recall_status(START, later, finished, [])
    assert (st["assessment_type"], st["state"]) == ("baseline", "finished")
    st = sch.recall_status(START, START + timedelta(days=5), finished, ["baseline"])
    assert (st["assessment_type"], st["state"]) == ("checkin_1", "upcoming")


def test_two_recalls_per_point():
    one = {"baseline": ["2026-10-02T01:00:00+00:00"]}
    st = sch.recall_status(START, START + timedelta(days=2), one, [])
    assert (st["state"], st["recalls_done"], st["recalls_needed"]) == ("open", 1, 2)
    two = {"baseline": one["baseline"] + ["2026-10-04T01:00:00+00:00"]}
    st = sch.recall_status(START, START + timedelta(days=4), two, [])
    assert (st["state"], st["recalls_done"]) == ("finished", 2)


def test_finished_times_reads_rows_saved_before_two_recalls():
    assert sch.finished_times({"finished_at": "t1"}) == ["t1"]
    assert sch.finished_times({"finished_at": "t1", "finished_times": ["t1", "t2"]}) == ["t1", "t2"]
    assert sch.finished_times({}) == []


def test_every_window_contains_a_weekend():
    for offset in range(7):  # whatever weekday the student joins on
        for w in sch.windows(START + timedelta(days=offset)):
            days = [w["opens_on"] + timedelta(days=i) for i in range((w["due_by"] - w["opens_on"]).days + 1)]
            assert any(d.weekday() == 5 for d in days) and any(d.weekday() == 6 for d in days)


def test_weekday_weekend_check():
    # "Past 24 hours": an evening recall is about that day.
    fri = {"IntakeStartDateTime": "10/15/2026 20:00:00", "IntakeEndDateTime": "10/16/2026 20:00:00"}
    sat = {"IntakeStartDateTime": "10/16/2026 20:00:00", "IntakeEndDateTime": "10/17/2026 20:00:00"}
    mon_morning = {"IntakeStartDateTime": "10/18/2026 09:00:00", "IntakeEndDateTime": "10/19/2026 09:00:00"}  # mostly Sunday
    wed = {"ReportingDate": "10/14/2026 21:00:00"}
    assert sch.weekday_weekend_problem([fri, sat]) is None
    assert sch.weekday_weekend_problem([wed, mon_morning]) is None
    assert sch.weekday_weekend_problem([fri, wed]) == "both recalls are about weekdays"
    assert sch.weekday_weekend_problem([sat, mon_morning]) == "both recalls are about weekend days"
    assert sch.weekday_weekend_problem([fri, {}]) is None  # undated: not judged


def test_missed_window_moves_on_without_a_failure_state():
    day = START + timedelta(days=sch.RECALL_WINDOW_DAYS + 1)
    st = sch.recall_status(START, day, {}, [])
    assert st["assessment_type"] == "checkin_1"
    assert st["state"] == "upcoming"
    assert st["days_until_open"] > 0


def test_all_points_done_is_complete():
    assert sch.recall_status(START, START, {}, sch.ASSESSMENT_TYPES)["state"] == "complete"


def test_parse_recall_date_formats():
    assert sch.parse_recall_date("10/05/2026 14:03:11") == date(2026, 10, 5)
    assert sch.parse_recall_date("10/5/2026") == date(2026, 10, 5)
    assert sch.parse_recall_date("2026-10-05T14:03:11") == date(2026, 10, 5)
    assert sch.parse_recall_date("not a date") is None
    assert sch.parse_recall_date("") is None


def test_split_keeps_only_this_points_recalls():
    window = sch.window_for(START, "baseline")
    recalls = [
        {"ReportingDate": "10/03/2026 10:00:00"},  # baseline
        {"ReportingDate": "10/06/2026 10:00:00"},  # baseline
        {"ReportingDate": "10/15/2026 10:00:00"},  # check-in 1, must not be blended in
        {"IntakeStartDateTime": "10/02/2026"},     # no ReportingDate: falls back to intake date
        {},                                        # no date at all
    ]
    split = sch.split_by_window(recalls, window)
    assert len(split["inside"]) == 3
    assert len(split["outside"]) == 1
    assert len(split["undated"]) == 1


def test_split_allows_one_day_of_slack():
    window = sch.window_for(START, "baseline")
    edge = (window["due_by"] + timedelta(days=1)).strftime("%m/%d/%Y")
    assert sch.split_by_window([{"ReportingDate": edge}], window)["inside"]


def test_latest_is_latest_study_point_not_latest_upload():
    rows = [
        {"assessment_type": "checkin_1", "recorded_at": "2026-10-20T00:00:00"},
        {"assessment_type": "baseline", "recorded_at": "2026-10-25T00:00:00"},  # re-imported later
    ]
    assert sch.latest(rows)["assessment_type"] == "checkin_1"
    assert sch.latest([]) is None
