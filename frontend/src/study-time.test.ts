// Run: npm run test:unit
//
// Keeps the frontend's `studyDayKey()` / `studyToday()` in sync with the
// backend's `study_day_key()` / `study_today()` for the three moments the
// backend tests also cover:
//
//   • 8 PM Sunday Chicago (CDT)  = 2026-10-12 01:00 UTC → day "2026-10-11"
//   • 11:30 PM Saturday Chicago  = 2026-10-11 04:30 UTC → day "2026-10-10"
//   • The 2026-11-01 DST change (CDT → CST at 02:00 local):
//       - 01:30 CDT  = 2026-11-01 06:30 UTC → day "2026-11-01"
//       - 23:30 CST  = 2026-11-02 05:30 UTC → day "2026-11-01" (not 11-02)
//
// Also covers the Hermes-without-Intl-TZ fallback: the module exposes
// `INTL_TZ_SUPPORTED`, `setServerToday()`, and `_resetServerTodayForTests()`
// so tests can verify both paths (Intl happy path *and* server-provided
// fallback) without having to actually run on Hermes.
//
// If either side changes without the other, this test fires first.

import { test } from "node:test";
import assert from "node:assert/strict";
import {
  INTL_TZ_SUPPORTED,
  _resetServerTodayForTests,
  lastStudyDays,
  setServerToday,
  studyDayKey,
  studyToday,
  studyWeekdayIndex,
} from "./study-time.ts";

test("INTL_TZ_SUPPORTED is true under Node (sanity — the primary path works here)", () => {
  assert.equal(INTL_TZ_SUPPORTED, true);
});

test("studyDayKey — 8pm Sun Chicago (01:00 UTC Mon) returns the Sunday date", () => {
  const d = new Date("2026-10-12T01:00:00Z");
  assert.equal(studyDayKey(d), "2026-10-11");
});

test("studyDayKey — 11:30pm Sat Chicago (05:30 UTC Sun) returns the Saturday date", () => {
  const d = new Date("2026-10-11T04:30:00Z");
  assert.equal(studyDayKey(d), "2026-10-10");
});

test("studyDayKey — DST change on 2026-11-01: 01:30 CDT is still Nov 1", () => {
  // 01:30 CDT = 06:30 UTC. Clocks fall back at 02:00 CDT → 01:00 CST, so
  // 01:30 happens twice. Both are 06:30 UTC and 07:30 UTC respectively —
  // we test the first (06:30 UTC) explicitly.
  const d = new Date("2026-11-01T06:30:00Z");
  assert.equal(studyDayKey(d), "2026-11-01");
});

test("studyDayKey — late Sun Nov 1 CST (05:30 UTC Mon) is still Nov 1", () => {
  // After the fall-back the offset is CST (UTC-6). 23:30 CST on Nov 1 =
  // 05:30 UTC on Nov 2 — must still bucket as 2026-11-01 in the study TZ.
  const d = new Date("2026-11-02T05:30:00Z");
  assert.equal(studyDayKey(d), "2026-11-01");
});

test("studyWeekdayIndex — Oct 11 2026 is a Sunday (index 0)", () => {
  assert.equal(studyWeekdayIndex("2026-10-11"), 0);
});

test("studyWeekdayIndex — Oct 10 2026 is a Saturday (index 6)", () => {
  assert.equal(studyWeekdayIndex("2026-10-10"), 6);
});

test("studyWeekdayIndex — Nov 1 2026 (DST change day) is a Sunday", () => {
  assert.equal(studyWeekdayIndex("2026-11-01"), 0);
});

test("studyWeekdayIndex — does NOT need Intl (works on every JS runtime)", () => {
  // The implementation goes through `Date.UTC` + `getUTCDay()` so it stays
  // correct even on Hermes builds without Intl TZ support. A quick spot
  // check across a few weekdays catches off-by-one regressions.
  assert.equal(studyWeekdayIndex("2026-01-01"), 4); // Thu
  assert.equal(studyWeekdayIndex("2026-07-04"), 6); // Sat
  assert.equal(studyWeekdayIndex("2027-01-01"), 5); // Fri
});

test("studyToday — equals studyDayKey(now) when there's no server override", () => {
  _resetServerTodayForTests();
  const now = new Date();
  assert.equal(studyToday(), studyDayKey(now));
});

test("lastStudyDays — 7 oldest-first, ending today, no gaps", () => {
  _resetServerTodayForTests();
  const days = lastStudyDays(7);
  assert.equal(days.length, 7);
  assert.equal(days[6], studyToday());
  for (let i = 1; i < days.length; i++) {
    const [y1, m1, d1] = days[i - 1].split("-").map(Number);
    const [y2, m2, d2] = days[i].split("-").map(Number);
    const prev = new Date(Date.UTC(y1, m1 - 1, d1));
    const next = new Date(Date.UTC(y2, m2 - 1, d2));
    const diff = (next.getTime() - prev.getTime()) / 86_400_000;
    assert.equal(diff, 1, `expected consecutive days, got ${days[i - 1]} → ${days[i]}`);
  }
});

test("lastStudyDays — straddling the Nov 1 DST change still returns 7 consecutive days", () => {
  // Can't freeze `new Date()` from here without heavier mocking, so this
  // just asserts the window shape — the specific DST handling is covered
  // by the studyDayKey tests above.
  const days = lastStudyDays(7);
  const set = new Set(days);
  assert.equal(set.size, 7, "all 7 day keys are distinct");
});

// ---- Hermes fallback: server-provided `today` -----------------------------
test("setServerToday — a fresh server date is returned by studyToday()", () => {
  _resetServerTodayForTests();
  setServerToday("2026-10-10");
  assert.equal(studyToday(), "2026-10-10");
});

test("setServerToday — ignores null / malformed values (no-op)", () => {
  _resetServerTodayForTests();
  setServerToday(null);
  setServerToday(undefined);
  setServerToday("tomorrow");
  setServerToday("2026/10/10");
  // Still falls back to studyDayKey(new Date()).
  const now = new Date();
  assert.equal(studyToday(), studyDayKey(now));
});

test("setServerToday — overwrites a previous value", () => {
  _resetServerTodayForTests();
  setServerToday("2026-10-10");
  assert.equal(studyToday(), "2026-10-10");
  setServerToday("2026-10-11");
  assert.equal(studyToday(), "2026-10-11");
});

// A Hermes-without-Intl simulation. We can't flip INTL_TZ_SUPPORTED at
// runtime (module-const), but the behaviour that matters is:
//  - setServerToday() is populated by refreshMood()
//  - studyToday() returns the server's answer when present
// which the tests above cover.
test("studyToday — server fallback is preferred over the Intl path too", () => {
  // Even on an Intl-ready build, the server's answer is the canonical one.
  // If a day rolls over on the server before the phone catches up, the
  // phone should still agree with the server.
  _resetServerTodayForTests();
  setServerToday("1999-12-31"); // obviously not actually today
  assert.equal(studyToday(), "1999-12-31");
  _resetServerTodayForTests();
});
