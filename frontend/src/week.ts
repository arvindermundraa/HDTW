// Small date helpers for "days you logged" views. Log timestamps are UTC
// ISO strings; every view here buckets them by the **study TZ** day
// (see src/study-time.ts) so the phone and server agree about which day
// a late-night log belongs to.

import { lastStudyDays, studyDayKey, studyToday } from "@/src/study-time";

/** YYYY-MM-DD for a Date, in the study TZ. */
export function localDayKey(d: Date): string {
  return studyDayKey(d);
}

/** The last `n` study-TZ days, oldest first, ending today. Returned as
 *  `Date` objects (anchored at noon that day in UTC) for callers that
 *  pass results into `toLocaleDateString` — the labels those callers
 *  render still come from `studyDayKey(...)` via `localDayKey`. */
export function lastDays(n = 7): Date[] {
  return lastStudyDays(n).map((iso) => {
    const [y, m, d] = iso.split("-").map(Number);
    return new Date(Date.UTC(y, m - 1, d, 18, 0, 0));
  });
}

export function dayKeysOf(logs: { created_at: string }[] | null | undefined, filter?: (log: any) => boolean): Set<string> {
  const keys = new Set<string>();
  for (const log of logs ?? []) {
    if (filter && !filter(log)) continue;
    keys.add(studyDayKey(new Date(log.created_at)));
  }
  return keys;
}

/** Seven booleans (oldest → today): was anything logged that day? */
export function weekFlags(logs: { created_at: string }[] | null | undefined, filter?: (log: any) => boolean): boolean[] {
  const keys = dayKeysOf(logs, filter);
  return lastStudyDays(7).map((iso) => keys.has(iso));
}

export function isToday(iso: string): boolean {
  return studyDayKey(new Date(iso)) === studyToday();
}

export function greeting(): string {
  // Based on the study TZ's hour, not the phone's — so a Chicago student
  // travelling east doesn't see "Good morning" at noon.
  const h = Number(
    new Intl.DateTimeFormat("en-US", {
      timeZone: "America/Chicago",
      hour: "numeric",
      hour12: false,
    }).format(new Date()),
  );
  return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
}
