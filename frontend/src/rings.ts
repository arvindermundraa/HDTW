// Pure ring maths (no React, no imports) so it can be unit-tested with
// `node --test`. Apple-Watch-style overflow for Move:
// - the first lap fills to 100% at the target;
// - past the target an extra lap is drawn for the surplus, capped at one
//   extra lap (200% total) so the ring never seems to reward overdoing it;
//   beyond that only the "+N" number keeps counting.
// Sleep never draws an extra lap — sleeping past the goal isn't something
// to encourage — it simply stays closed.
// Eat is binary: the ring fills once at least one meal is logged. There is
// no required meal count, no "to go" and no overflow lap — the point is
// diet quality and the practice of logging, not meal frequency.
// Overflow is visual only: no points, no extra avatar mood.

export type RingDomain = "food" | "move" | "rest";

export type RingLaps = {
  /** 0–1: how much of the first lap to draw. */
  first: number;
  /** 0–1: how much of the extra lap to draw (always 0 for Sleep and Eat). */
  extra: number;
  /** Amount past the target (unbounded; 0 when not past it, and always 0 for Eat). */
  over: number;
  closed: boolean;
};

const clamp = (n: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, n));

export function ringLaps(value: number, target: number, domain: RingDomain): RingLaps {
  const v = Math.max(0, Number.isFinite(value) ? value : 0);
  if (domain === "food") {
    const closed = v >= 1;
    return { first: closed ? 1 : 0, extra: 0, over: 0, closed };
  }
  const ratio = target > 0 ? v / target : 0;
  return {
    first: clamp(ratio, 0, 1),
    extra: domain === "rest" ? 0 : clamp(ratio - 1, 0, 1),
    over: target > 0 ? Math.max(0, round1(v - target)) : 0,
    closed: target > 0 && v >= target,
  };
}

function round1(n: number): number {
  return Math.round(n * 10) / 10;
}

function fmt(n: number): string {
  return `${round1(n)}`;
}

/**
 * "20 / 30 min", "60 / 60 min · +10 min". Eat shows a plain count of
 * what the student logged today — never a "/N" target or "to go".
 * Sleep past its goal shows the closed goal only, with no "+N".
 */
export function ringText(value: number, target: number, domain: RingDomain): string {
  if (domain === "food") {
    const n = Math.max(0, Math.floor(Number.isFinite(value) ? value : 0));
    if (n === 0) return "Log a meal when you're ready";
    return `Meals logged today: ${n}`;
  }
  const { over, closed } = ringLaps(value, target, domain);
  const shown = closed ? target : round1(Math.max(0, value));
  const unit = domain === "move" ? "min" : "h";
  const base = `${fmt(shown)} / ${fmt(target)} ${unit}`;
  if (!closed || over === 0 || domain === "rest") return base;
  return `${base} · +${fmt(over)} min`;
}

/**
 * Move / Sleep: "10 min to go", "1.5 h to go"; null once closed.
 * Eat has no "to go" — logging a meal is an act, not a quota.
 */
export function ringToGo(value: number, target: number, domain: RingDomain): string | null {
  if (domain === "food") return null;
  const left = round1(target - Math.max(0, value));
  if (target <= 0 || left <= 0) return null;
  const unit = domain === "move" ? "min" : "h";
  return `${fmt(left)} ${unit} to go`;
}

export type RingContext = {
  /** Minutes since midnight now, in the study time zone. */
  nowMinutes: number;
  /** Usual bedtime / wake time as minutes since midnight. */
  bedtime: number;
  wake: number;
  /** Food ring only: the focus food group to suggest, e.g. "vegetables". */
  food?: string;
};

export type RingNote = { line: string; note: string | null };

/** Before wake time, or after it but before the day's later stretch. */
function lateInDay(c: RingContext): boolean {
  // "Late" = within two hours of bedtime (handles bedtimes after midnight).
  const untilBed = (((c.bedtime - c.nowMinutes) % 1440) + 1440) % 1440;
  return untilBed <= 120;
}

/**
 * What a ring row says (study team feedback, 2.4–2.5): progress on the
 * activity itself, never "N to go" or a meal count to hit. Food counts the
 * meals logged today (any meal fills it) and suggests the focus food; Sleep is a morning check-in
 * about last night; Move acknowledges any minutes and the time of day.
 */
export function ringNote(domain: RingDomain, value: number, target: number, c: RingContext): RingNote {
  const v = Math.max(0, Number.isFinite(value) ? value : 0);
  const closed = target > 0 && v >= target;
  if (domain === "food") {
    const note = c.food ? `Add ${c.food} when you can` : null;
    if (v === 0) return { line: "Log a meal when you're ready", note };
    return { line: `Meals logged today: ${round1(v)}`, note };
  }
  if (domain === "move") {
    const line = `${round1(v)} of ${round1(target)} min today`;
    if (closed) return { line, note: "Goal reached today" };
    if (v > 0) return { line, note: "Every minute counts" };
    return { line, note: lateInDay(c) ? "A short walk counts, or pick it up tomorrow" : "Plenty of day left" };
  }
  if (v > 0) return { line: `${round1(v)} h last night`, note: "Thanks for checking in" };
  const beforeWake = (((c.wake - c.nowMinutes) % 1440) + 1440) % 1440 < (((c.wake - c.bedtime) % 1440) + 1440) % 1440;
  return beforeWake
    ? { line: "Morning check-in", note: "Log last night's sleep after you wake up" }
    : { line: "Morning check-in", note: "How did you sleep last night?" };
}

/** "23:30" → 1410. */
export function clockMinutes(hhmm: string | null | undefined, fallback: number): number {
  const m = /^(\d{1,2}):(\d{2})$/.exec(hhmm ?? "");
  return m ? (Number(m[1]) * 60 + Number(m[2])) % 1440 : fallback;
}
