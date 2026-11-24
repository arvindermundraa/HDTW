"""The behavioral twin's pattern detectors (twin_patterns.py): weekday vs
weekend movement, sleep timing and duration, skipped weekday breakfasts,
meal regulars as questions, and the one pattern across domains. Pure
functions, no server.
    python -m pytest tests/test_twin_patterns.py -n 0"""
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "llhs_unit_unused")
import twin_patterns as tp  # noqa: E402

TODAY = date(2026, 11, 11)  # a Wednesday


def days_back(n):
    return [TODAY - timedelta(days=i) for i in range(n)]


def act(d, minutes, source="wearable", at="2026-11-11T12:00:00+00:00"):
    return {"recorded_date": d.isoformat(), "minutes": minutes, "source": source, "created_at": at}


def night(d, hours, bed=None, wake=None, source="wearable"):
    return {"recorded_date": d.isoformat(), "hours": hours, "bedtime": bed, "wake": wake, "source": source,
            "created_at": "2026-11-11T12:00:00+00:00"}


def keys(found):
    return [p["key"] for p in found]


# ---- activity ------------------------------------------------------------------------------------
def test_quieter_weekdays_are_noticed_with_counts_as_evidence():
    rows = [act(d, 10 if d.weekday() < 5 else 60) for d in days_back(21)]
    found = tp.detect_activity(tp.activity_days(rows, TODAY))
    assert keys(found) == ["activity.low_weekdays"]
    assert found[0]["evidence"] == "On 15 of the 15 weekdays your tracker has, you moved less than on a usual weekend day."
    assert found[0]["question"].endswith("?") and "other" in found[0]["circumstances"]


def test_too_few_days_or_an_already_active_week_says_nothing():
    few = [act(d, 10 if d.weekday() < 5 else 60) for d in days_back(4)]
    assert tp.detect_activity(tp.activity_days(few, TODAY)) == []
    active = [act(d, 50 if d.weekday() < 5 else 120) for d in days_back(21)]  # weekday median >= 45: never "low"
    assert tp.detect_activity(tp.activity_days(active, TODAY)) == []


def test_a_day_without_rows_is_absent_not_zero_and_the_latest_device_sync_wins():
    rows = [act(TODAY, 20, at="2026-11-11T08:00:00+00:00"), act(TODAY, 35, at="2026-11-11T20:00:00+00:00"),
            act(TODAY - timedelta(days=1), 15, source="manual"), act(TODAY - timedelta(days=1), 10, source="manual")]
    days = tp.activity_days(rows, TODAY)
    assert set(days) == {TODAY.isoformat(), (TODAY - timedelta(days=1)).isoformat()}
    assert days[TODAY.isoformat()]["minutes"] == 35  # the re-sent day replaces, never adds
    assert days[(TODAY - timedelta(days=1)).isoformat()] == {"minutes": 25, "steps": None, "source": "manual"}


def test_quieter_weekends_are_their_own_question():
    rows = [act(d, 50 if d.weekday() < 5 else 5) for d in days_back(21)]
    assert keys(tp.detect_activity(tp.activity_days(rows, TODAY))) == ["activity.low_weekends"]


# ---- sleep -----------------------------------------------------------------------------------------
def test_a_weekday_weekend_bedtime_shift_and_shorter_weekday_nights():
    rows = [night(d, 6 if d.weekday() < 5 else 8.5, "01:00" if d.weekday() < 5 else "23:00", "07:00")
            for d in days_back(14)]
    found = {p["key"]: p for p in tp.detect_sleep(tp.sleep_nights(rows, TODAY))}
    assert set(found) == {"sleep.irregular_timing", "sleep.short_weekdays"}
    assert "around 1 am before class days" in found["sleep.irregular_timing"]["evidence"]
    assert "11 pm" in found["sleep.irregular_timing"]["evidence"]


def test_bedtimes_straddling_midnight_are_measured_properly():
    steady = [night(d, 7.5, bed, "07:30") for d, bed in zip(days_back(8), ["23:30", "00:00", "23:45", "00:15",
                                                                           "23:30", "00:00", "23:45", "00:10"])]
    assert tp.detect_sleep(tp.sleep_nights(steady, TODAY)) == []  # 11:30 pm to 12:15 am is regular, not a 23-hour spread
    wild = [night(d, 7, bed, "08:00") for d, bed in zip(days_back(8), ["22:00", "02:30", "23:00", "03:00",
                                                                        "22:30", "01:30", "22:00", "02:00"])]
    assert keys(tp.detect_sleep(tp.sleep_nights(wild, TODAY))) == ["sleep.irregular_timing"]


def test_hours_without_times_never_claim_anything_about_timing():
    rows = [night(d, 7) for d in days_back(14)]
    assert tp.detect_sleep(tp.sleep_nights(rows, TODAY)) == []


def test_clock_words():
    assert tp.clock_words(tp._from_noon(23 * 60)) == "11 pm"
    assert tp.clock_words(tp._from_noon(90)) == "1:30 am"
    assert tp.clock_words(tp._from_noon(12 * 60)) == "12 pm"


# ---- breakfast, regulars, across domains --------------------------------------------------------------
def meal(d, slot="breakfast", skipped=False, name="Skipped meal"):
    return {"created_at": f"{d.isoformat()}T15:00:00+00:00", "meal_type": slot, "skipped": skipped, "name": name}


def test_only_explicitly_skipped_weekday_breakfasts_count():
    weekdays = [d for d in days_back(21) if d.weekday() < 5]
    assert tp.detect_breakfast([meal(d, skipped=True) for d in weekdays[:2]], TODAY) == []
    assert tp.detect_breakfast([meal(d, skipped=False) for d in weekdays], TODAY) == []  # logged ≠ skipped
    found = tp.detect_breakfast([meal(d, skipped=True) for d in weekdays[:3]], TODAY)
    assert keys(found) == ["diet.rushed_weekday_breakfast"]
    assert "skipped on 3 weekday mornings" in found[0]["evidence"]


def test_a_meal_regular_becomes_a_question_with_a_stable_key():
    habit = {"food_id": "whole_milk_yogurt", "label": "whole-milk yogurt", "top_slot": "breakfast", "times": 5}
    p = tp.regular_patterns([habit], {"diet.regular.whole_milk_yogurt": "You've logged whole-milk yogurt in 5 meals."})[0]
    assert p["key"] == "diet.regular.whole_milk_yogurt"
    assert p["question"] == "Is whole-milk yogurt a regular breakfast for you?"
    assert tp.regular_key({"food_id": None, "label": "Chobani Flip"}) == "diet.regular.chobani_flip"


def test_weekday_signals_in_two_domains_become_one_question():
    sleep = {"key": "sleep.short_weekdays"}
    move = {"key": "activity.low_weekdays"}
    assert tp.detect_cross([sleep], set()) == []
    both = tp.detect_cross([sleep, move], set())
    assert keys(both) == ["cross.weekday_squeeze"] and "shorter sleep and less movement" in both[0]["evidence"]
    with_schedule = tp.detect_cross([move], {"early_classes"})  # one signal + a schedule they told us about
    assert keys(with_schedule) == ["cross.weekday_squeeze"] and "mentioned your schedule" in with_schedule[0]["evidence"]


def test_a_recent_safety_check_in_keeps_meals_out_of_the_questions():
    weekdays = [d for d in days_back(21) if d.weekday() < 5]
    skipped = [meal(d, skipped=True) for d in weekdays[:4]]
    assert "diet.rushed_weekday_breakfast" in keys(tp.detect_all(skipped, [], [], TODAY, set())["patterns"])
    assert tp.detect_all(skipped, [], [], TODAY, set(), paused=True)["patterns"] == []


def test_every_question_and_label_is_free_of_body_or_nutrition_numbers():
    import server  # noqa: F401  (the guardrail lives in server)
    for c in tp.CIRCUMSTANCES.values():
        assert server._guardrail_violation_type(c["label"] + " " + c["fact"], strict=True) is None
