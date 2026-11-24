// Run: npm run test:unit   (node --test with built-in type stripping)
import { test } from "node:test";
import assert from "node:assert/strict";
import { clockMinutes, ringLaps, ringNote, ringText, ringToGo } from "./rings.ts";

const near = (a: number, b: number) => assert.ok(Math.abs(a - b) < 1e-9, `${a} ≈ ${b}`);

// Move, target 60 min: 0%, 50%, 100%, 117%, 200%, 350%.
const MOVE = [
  { value: 0, first: 0, extra: 0, over: 0, text: "0 / 60 min", toGo: "60 min to go" },
  { value: 30, first: 0.5, extra: 0, over: 0, text: "30 / 60 min", toGo: "30 min to go" },
  { value: 60, first: 1, extra: 0, over: 0, text: "60 / 60 min", toGo: null },
  { value: 70, first: 1, extra: 10 / 60, over: 10, text: "60 / 60 min · +10 min", toGo: null },
  { value: 120, first: 1, extra: 1, over: 60, text: "60 / 60 min · +60 min", toGo: null },
  { value: 210, first: 1, extra: 1, over: 150, text: "60 / 60 min · +150 min", toGo: null },
];

for (const c of MOVE) {
  test(`move ${Math.round((c.value / 60) * 100)}%`, () => {
    const laps = ringLaps(c.value, 60, "move");
    near(laps.first, c.first);
    near(laps.extra, c.extra);
    assert.equal(laps.over, c.over);
    assert.equal(laps.closed, c.value >= 60);
    assert.equal(ringText(c.value, 60, "move"), c.text);
    assert.equal(ringToGo(c.value, 60, "move"), c.toGo);
  });
}

test("extra lap is capped at one lap (200%) however far past the goal", () => {
  assert.equal(ringLaps(600, 60, "move").extra, 1);
  assert.equal(ringText(600, 60, "move"), "60 / 60 min · +540 min");
});

test("eat ring is binary: fills once a meal is logged, no required count", () => {
  // No meals: ring is empty and prompts activity, never a quota.
  assert.deepEqual(ringLaps(0, 1, "food"), { first: 0, extra: 0, over: 0, closed: false });
  assert.equal(ringText(0, 1, "food"), "Log a meal when you're ready");
  assert.equal(ringToGo(0, 1, "food"), null);

  // One meal: ring is closed and shows a plain count.
  assert.deepEqual(ringLaps(1, 1, "food"), { first: 1, extra: 0, over: 0, closed: true });
  assert.equal(ringText(1, 1, "food"), "Meals logged today: 1");
  assert.equal(ringToGo(1, 1, "food"), null);

  // More meals: still binary — no overflow lap, no "+N", no "/N meals".
  assert.deepEqual(ringLaps(3, 1, "food"), { first: 1, extra: 0, over: 0, closed: true });
  assert.equal(ringText(3, 1, "food"), "Meals logged today: 3");
  // Stale clients may still send target 2; the ring stays binary either way.
  assert.deepEqual(ringLaps(1, 2, "food"), { first: 1, extra: 0, over: 0, closed: true });
  assert.equal(ringText(1, 2, "food"), "Meals logged today: 1");
  assert.equal(ringToGo(1, 2, "food"), null);
});

test("sleep closes at the goal but never draws an extra lap or +N", () => {
  const laps = ringLaps(10, 8, "rest");
  assert.equal(laps.first, 1);
  assert.equal(laps.extra, 0);
  assert.equal(laps.closed, true);
  assert.equal(ringText(10, 8, "rest"), "8 / 8 h");
  assert.equal(ringText(6.5, 8, "rest"), "6.5 / 8 h");
  assert.equal(ringToGo(6.5, 8, "rest"), "1.5 h to go");
});

test("bad input never breaks the ring", () => {
  assert.deepEqual(ringLaps(-5, 30, "move"), { first: 0, extra: 0, over: 0, closed: false });
  assert.deepEqual(ringLaps(10, 0, "move"), { first: 0, extra: 0, over: 0, closed: false });
});

// Study team feedback 2.4–2.5: no meal quota, sleep as a morning check-in,
// supportive wording that depends on the time of day.
const CTX = { nowMinutes: 10 * 60, bedtime: 23 * 60, wake: 7 * 60, food: "vegetables" };

test("food ring counts meals logged and suggests the focus food, never a quota", () => {
  assert.deepEqual(ringNote("food", 0, 1, CTX), { line: "Log a meal when you're ready", note: "Add vegetables when you can" });
  assert.deepEqual(ringNote("food", 2, 1, CTX), { line: "Meals logged today: 2", note: "Add vegetables when you can" });
  assert.equal(ringNote("food", 1, 1, { ...CTX, food: undefined }).note, null);
  assert.ok(!/to go|\//.test(ringNote("food", 1, 1, CTX).line + ringNote("food", 1, 1, CTX).note));
});

test("move ring is supportive and time-aware", () => {
  assert.equal(ringNote("move", 0, 30, CTX).note, "Plenty of day left");
  assert.equal(ringNote("move", 0, 30, { ...CTX, nowMinutes: 22 * 60 }).note, "A short walk counts, or pick it up tomorrow");
  assert.equal(ringNote("move", 10, 30, CTX).note, "Every minute counts");
  assert.equal(ringNote("move", 30, 30, CTX).note, "Goal reached today");
});

test("sleep is a morning check-in, never behind during the day", () => {
  assert.equal(ringNote("rest", 0, 8, CTX).line, "Morning check-in");
  assert.equal(ringNote("rest", 0, 8, CTX).note, "How did you sleep last night?");
  assert.equal(ringNote("rest", 0, 8, { ...CTX, nowMinutes: 2 * 60 }).note, "Log last night's sleep after you wake up");
  assert.equal(ringNote("rest", 7.5, 8, CTX).line, "7.5 h last night");
  assert.equal(clockMinutes("23:30", 0), 1410);
  assert.equal(clockMinutes(null, 420), 420);
});
