"""Unit tests for program.py: the 8-week program's weekly release, step
completion and the next step. No server or database."""
from datetime import date, timedelta

import program

START = date(2026, 10, 14)
VIDEOS = {"c1": {"id": "c1"}, "c2": {"id": "c2"}, "c3": {"id": "c3"}}


def build(today, **kw):
    args = dict(done_steps=set(), videos_done=set(), games_done=set(), focus_set_on=None, videos=VIDEOS)
    args.update(kw)
    return program.build(START, today, **args)


def unit(p, week):
    return next(u for u in p["units"] if u["week"] == week)


def step(p, week, key):
    return next(s for s in unit(p, week)["steps"] if s["key"] == key)


def test_eight_weeks_released_one_per_week():
    assert program.current_week(START, START) == 1
    assert program.current_week(START, START + timedelta(days=6)) == 1
    assert program.current_week(START, START + timedelta(days=7)) == 2
    assert program.current_week(START, START + timedelta(days=200)) == 8
    p = build(START + timedelta(days=8))
    assert [u["status"] for u in p["units"]][:3] == ["available", "current", "upcoming"]
    assert unit(p, 3)["opens_on"] == (START + timedelta(days=14)).isoformat()
    assert len(p["units"]) == 8 and all(len(u["steps"]) == 4 for u in p["units"])


def test_steps_complete_from_the_rest_of_the_app():
    p = build(START + timedelta(days=10), videos_done={"c2"}, games_done={"g2"}, focus_set_on=START)
    assert step(p, 2, "watch")["done"] and step(p, 2, "practice")["done"]
    assert step(p, 1, "practice")["done"]  # chose a focus area
    assert not step(p, 2, "do_it")["done"]


def test_week_5_refocus_needs_a_choice_made_in_week_5():
    week5 = START + timedelta(days=29)
    assert not step(build(week5, focus_set_on=START), 5, "practice")["done"]
    assert step(build(week5, focus_set_on=week5), 5, "practice")["done"]


def test_missing_videos_are_coming_soon_not_invented():
    p = build(START)
    w = step(p, 1, "watch")
    assert not w["ready"] and w["route"] is None
    # ...and don't count, so a week can still be finished.
    p = build(START, focus_set_on=START, done_steps={"1:do_it", "1:reflect"})
    assert (unit(p, 1)["steps_done"], unit(p, 1)["steps_total"], unit(p, 1)["status"]) == (3, 3, "done")


def test_next_step_is_this_weeks_first_unfinished_ready_step():
    p = build(START + timedelta(days=8), videos_done={"c2"})
    assert (program.next_step(p)["week"], program.next_step(p)["key"]) == (2, "practice")
    p = build(START + timedelta(days=8), videos_done={"c2"}, games_done={"g2"},
              done_steps={"2:do_it", "2:reflect"})
    nxt = program.next_step(p)
    assert nxt["week"] == 1  # back-fills week 1 once this week is done


def test_only_do_reflect_and_plain_practice_steps_can_be_marked():
    assert program.can_mark(1, "do_it") and program.can_mark(1, "reflect")
    assert not program.can_mark(2, "watch") and not program.can_mark(2, "practice")  # video / game
    assert not program.can_mark(1, "practice")  # completes by choosing a focus area
    assert program.can_mark(3, "practice")  # Build a Meal
    assert not program.can_mark(9, "do_it") and not program.can_mark(1, "nap")


def test_applying_counts_at_least_as_much_as_watching():
    assert program.POINTS["do_it"] >= program.POINTS["watch"]
    assert program.POINTS["practice"] >= program.POINTS["watch"]
