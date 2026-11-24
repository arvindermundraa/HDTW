// One source of truth for day boundaries on the phone — mirrors
// `backend/study_time.py`. Every day-key comparison on the frontend
// (ring strip labels, Eat "N of 7 days" bars, Progress Streaks tab,
// avatar's stale-mood check, the Today header date) routes through
// studyDayKey() so the phone and server agree about "today" even when
// the phone is in a different TZ or crosses midnight before the server.
//
// Change this and `backend/study_time.py` together — a frontend test
// (src/study-time.test.ts) keeps them in sync for the 2026-11-01 DST
// change, 8 PM Sunday Chicago (01:00 UTC Mon) and 11:30 PM Saturday
// Chicago (05:30 UTC Sun).
//
// Hermes caveat: Expo SDK 54's default Hermes build on both iOS and
// Android has `Intl.DateTimeFormat` with the `timeZone` option, so the
// primary path below works. A small number of edge-case builds (Hermes
// with `HERMES_ENABLE_INTL=0`, pre-API-26 Android, custom ROMs that
// strip ICU) either throw or silently fall back to UTC on `timeZone`.
// `INTL_TZ_SUPPORTED` probes for this at module load. If false,
// `studyToday()` / `studyDayKey()` fall back to the server-provided
// `today` from `/api/daily-goals` (populated via `setServerToday`
// whenever the mood snapshot is refreshed).

export const STUDY_TZ = "America/Chicago";

/** True iff `Intl.DateTimeFormat` + `timeZone` returns the right answer
 *  for a known Chicago evening moment. False on Hermes builds without
 *  full ICU, or when the Android / custom-ROM TZ database is stripped. */
export const INTL_TZ_SUPPORTED: boolean = (() => {
  try {
    // 2026-10-12 01:00 UTC = 2026-10-11 20:00 CDT (Chicago).
    const probe = new Intl.DateTimeFormat("en-CA", {
      timeZone: STUDY_TZ,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(new Date("2026-10-12T01:00:00Z"));
    return probe === "2026-10-11";
  } catch {
    return false;
  }
})();

// Server-provided "today" (from `/api/daily-goals` → `today` or
// `mood.date`). Updated whenever the mood snapshot is refreshed. On
// Hermes-without-Intl this is the canonical fallback; even on Intl-ready
// builds it's preferred as "today" because it's the server's own answer.
let serverToday: { date: string; fetchedAtMs: number } | null = null;

const SERVER_TODAY_FRESH_MS = 10 * 60 * 1000; // 10 min; mood is refreshed well under this

/** Called by the mood-refresh path with the server's `today`. Ignores
 *  anything that isn't a YYYY-MM-DD string, so the pre-rings snapshot
 *  (`today: null`) and junk values are no-ops. */
export function setServerToday(date: string | null | undefined): void {
  if (date && /^\d{4}-\d{2}-\d{2}$/.test(date)) {
    serverToday = { date, fetchedAtMs: Date.now() };
  }
}

/** Internal — the current cached server date, or null if stale/absent. */
function freshServerToday(): string | null {
  if (serverToday && Date.now() - serverToday.fetchedAtMs < SERVER_TODAY_FRESH_MS) {
    return serverToday.date;
  }
  return null;
}

/** YYYY-MM-DD for a `Date` in the study TZ. Replaces every
 *  "y-m-d from getFullYear/getMonth/getDate" idiom, which was keyed
 *  by the phone's local zone — see src/week.ts and src/avatar.ts.
 *
 *  Fallback path (Hermes without Intl TZ):
 *   - For a Date within ~60 seconds of now, return the server's today.
 *   - For arbitrary Dates (e.g. a log's created_at), approximate by
 *     subtracting a 5h30m midpoint-of-CDT-CST offset from UTC and taking
 *     the UTC date part. Good enough for day-key labelling; the real
 *     authority on bucketing lives on the server.
 */
export function studyDayKey(d: Date = new Date()): string {
  if (INTL_TZ_SUPPORTED) {
    const parts = new Intl.DateTimeFormat("en-CA", {
      timeZone: STUDY_TZ,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).formatToParts(d);
    const by = Object.fromEntries(parts.map((p) => [p.type, p.value])) as Record<string, string>;
    return `${by.year}-${by.month}-${by.day}`;
  }
  // Fallback 1: for a near-now Date, trust the server's own answer.
  const fresh = freshServerToday();
  if (fresh && Math.abs(d.getTime() - Date.now()) < 60_000) return fresh;
  // Fallback 2: UTC - 5h30m (midpoint between CDT and CST) → close enough
  // for arbitrary dates on an Intl-less build. The server is authoritative
  // for anything that affects data (streaks, badges, etc.).
  const nudged = new Date(d.getTime() - 5.5 * 60 * 60 * 1000);
  const y = nudged.getUTCFullYear();
  const m = String(nudged.getUTCMonth() + 1).padStart(2, "0");
  const day = String(nudged.getUTCDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/** YYYY-MM-DD for "today" in the study TZ. Prefers the server's answer
 *  when it's fresh (< 10 min old) — that's the canonical answer whether
 *  or not Intl TZ works on this device. Falls back to studyDayKey(now). */
export function studyToday(): string {
  const fresh = freshServerToday();
  if (fresh) return fresh;
  return studyDayKey(new Date());
}

/** 0 (Sunday) through 6 (Saturday) for a YYYY-MM-DD in the study TZ.
 *  Does not need Intl — a YYYY-MM-DD is a wall-clock date, so we can
 *  construct a `Date.UTC` and read `getUTCDay()` directly. Works on
 *  every JS runtime. */
export function studyWeekdayIndex(dayIso: string): number {
  const [y, m, d] = dayIso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d)).getUTCDay();
}

/** The last `n` study-TZ day keys, oldest first, ending today. */
export function lastStudyDays(n = 7): string[] {
  const today = studyToday();
  const [y, m, d] = today.split("-").map(Number);
  // Anchor at 18:00 UTC — noon-ish in Chicago in both CDT and CST, well
  // inside the day so DST crossings never shift the key.
  const anchor = new Date(Date.UTC(y, m - 1, d, 18, 0, 0));
  return Array.from({ length: n }, (_, i) => {
    const d2 = new Date(anchor);
    d2.setUTCDate(anchor.getUTCDate() - (n - 1 - i));
    if (INTL_TZ_SUPPORTED) return studyDayKey(d2);
    // Without Intl: the anchor is noon-in-Chicago, so the UTC date part
    // is the Chicago date part.
    const y2 = d2.getUTCFullYear();
    const m2 = String(d2.getUTCMonth() + 1).padStart(2, "0");
    const dd2 = String(d2.getUTCDate()).padStart(2, "0");
    return `${y2}-${m2}-${dd2}`;
  });
}

/** Test-only. Resets module state so a test can simulate a fresh app launch. */
export function _resetServerTodayForTests(): void {
  serverToday = null;
}
