// Run: npm run test:unit  (node --test with built-in type stripping)
//
// Checks the auth-screen redesign the way the brief asks for:
//   1. Pure helpers in AuthScene (`skyForHour`, `floatersFor`) behave right —
//      including the narrow-screen rule that drops any floater that would
//      sit behind the frosted card at 390 px.
//   2. The quote constant `AUTH_QUOTES` has the right shape and never names
//      weight / calories / appearance (brief).
//   3. `auth.tsx` renders every form field + button the auth flow needs, each
//      with the testID AND an accessibilityLabel the brief requires.
//   4. Both AuthScene and AuthQuote read `useReducedMotion` AND short-circuit
//      their animations when it's on (the structural proof — a full render
//      harness would need jest-expo wiring; this is enough to spot regressions
//      and runs on the same `node --test` as every other frontend test).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

import { skyForHour, floatersFor, FLOATERS } from "./components/auth-scene-helpers.ts";
import type { VeggieKey } from "./components/auth-scene-helpers.ts";
import { AUTH_QUOTES } from "./components/auth-quotes-data.ts";

// Known veggie keys the FLOATERS roster should correspond to. (Kept inline
// so we don't need to import the TSX file — node --test can't resolve .tsx
// imports or React Native primitives.)
const KNOWN_VEGGIES: VeggieKey[] = [
  "apple", "strawberry", "carrot", "avocado",
  "broccoli", "banana", "blueberries", "oats",
];

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (rel: string) => readFileSync(resolve(HERE, rel), "utf8");

// --- 1. Sky palette by study-TZ hour ----------------------------------------
test("skyForHour returns a well-formed palette for every hour", () => {
  for (let h = 0; h < 24; h++) {
    const p = skyForHour(h);
    assert.equal(p.colors.length, 3, `hour ${h}: 3 gradient stops`);
    for (const c of p.colors) assert.ok(/^#([0-9A-Fa-f]{6}|[0-9A-Fa-f]{3})$/.test(c), `hour ${h}: valid hex ${c}`);
    assert.equal(p.locations.length, 3);
    assert.ok(p.locations[0] === 0 && p.locations[2] === 1, "gradient spans the full range");
    assert.ok(p.hillBack && p.hillFront, "hills defined");
    assert.ok(p.cloud, "cloud fill defined");
  }
});

test("skyForHour follows the study clock", () => {
  // Morning (dawn warmth) vs afternoon vs evening vs night should each
  // produce a distinct top-stop colour.
  const unique = new Set([
    skyForHour(7).colors[0],
    skyForHour(14).colors[0],
    skyForHour(19).colors[0],
    skyForHour(2).colors[0],
  ]);
  assert.equal(unique.size, 4, "four distinct skies for morning/afternoon/evening/night");
  // Sun ellipse only appears at times of day where a horizon glow fits.
  assert.ok(skyForHour(7).sun, "morning has a sun glow");
  assert.ok(skyForHour(19).sun, "evening has a sun glow");
  assert.equal(skyForHour(14).sun, null, "afternoon is sky-only");
  assert.equal(skyForHour(2).sun, null, "night has no sun");
});

// --- 2. Floater layout for narrow screens ----------------------------------
test("floatersFor drops mid-level items that sit near the card at 390px", () => {
  const narrow = floatersFor(390);
  const wide = floatersFor(1440);
  const narrowKeys = narrow.map((f) => f.key);
  // The brief says reduce floaters on narrow screens so they never sit
  // behind the inputs. Specifically the two mid-vertical ones go.
  assert.ok(!narrowKeys.includes("broccoli"), "broccoli hidden on narrow");
  assert.ok(!narrowKeys.includes("banana"), "banana hidden on narrow");
  assert.ok(narrow.length < wide.length, "narrow set is strictly smaller");
  // Every floater on a narrow screen must still have 10–30s loops.
  for (const f of narrow) {
    assert.ok(f.duration >= 10000 && f.duration <= 30000, `${f.key}: 10–30s loop`);
    assert.ok(f.amplitude >= 2 && f.amplitude <= 12, `${f.key}: subtle bob amplitude`);
  }
});

test("every floater maps to one of the known veggies", () => {
  const known = new Set<string>(KNOWN_VEGGIES);
  for (const f of FLOATERS) {
    assert.ok(known.has(f.key), `veggie "${f.key}" is in the known roster`);
  }
});

// --- 3. Quotes --------------------------------------------------------------
const BANNED = /\b(weight|calorie|calories|kcal|pound|lbs|body\s+size|appearance|skinny|thin|fat)\b/i;

test("AUTH_QUOTES: 6 original, body/weight/appearance-free lines", () => {
  assert.ok(AUTH_QUOTES.length >= 5, "at least 5 lines so rotation feels fresh");
  const seen = new Set<string>();
  for (const q of AUTH_QUOTES) {
    assert.ok(q.trim().length > 0, "non-empty");
    assert.ok(q.length <= 80, `short enough for the sky slot: ${q!}`);
    assert.ok(!BANNED.test(q), `brief forbids body/weight/calorie wording: ${q}`);
    assert.ok(!seen.has(q), `no duplicate quote: ${q}`);
    seen.add(q);
  }
});

// --- 4. Form fields, testIDs, labels ---------------------------------------
const AUTH_SOURCE = read("../app/auth.tsx");

const REQUIRED_FIELD_IDS = [
  "auth-screen", "auth-card", "auth-back", "auth-welcome", "auth-subtitle",
  "auth-name", "auth-email", "auth-password", "auth-password-toggle",
  "auth-signup-code", "auth-reset-code", "auth-new-password",
  "auth-forgot", "auth-signup-resend", "auth-signup-change",
  "auth-resend", "auth-change-email", "auth-back-to-signin",
  "auth-to-signup", "auth-to-signin",
  "auth-error", "auth-submit",
];

test("auth.tsx declares every testID the auth flow needs", () => {
  // Some IDs are passed as the 3rd arg of `link(label, onPress, testID)`
  // rather than as a `testID="..."` attribute literal, so accept either form.
  for (const id of REQUIRED_FIELD_IDS) {
    const asAttr = AUTH_SOURCE.includes(`testID="${id}"`);
    const asLiteral = AUTH_SOURCE.includes(`"${id}"`);
    assert.ok(asAttr || asLiteral, `auth.tsx missing testID "${id}"`);
  }
});

test("every form Field wires the label as an accessibility label", () => {
  // Field helper in auth.tsx forwards the label as both the visible label
  // text and the TextInput's `accessibilityLabel` — otherwise a screen
  // reader would announce only the placeholder.
  assert.match(AUTH_SOURCE, /accessibilityLabel=\{label\}/,
    "Field must forward `label` to the TextInput's accessibilityLabel");
  // Password toggle, back button both have explicit a11y labels.
  assert.match(AUTH_SOURCE, /accessibilityLabel=\{showPassword \? "Hide password" : "Show password"\}/);
  assert.match(AUTH_SOURCE, /accessibilityLabel="Back"/);
});

test("auth-submit button changes title per mode (and still has the testID)", () => {
  // The button title string must appear per mode. If any single auth flow
  // loses the button we fail here.
  for (const label of [
    "Sign in", "Verify and sign in", "Set new password", "Email me a code",
  ]) {
    assert.ok(AUTH_SOURCE.includes(`"${label}"`), `missing submit title: ${label}`);
  }
});

// --- 5. Reduce-motion wiring (structural proof) ----------------------------
const SCENE_SOURCE  = read("./components/AuthScene.tsx");
const QUOTES_SOURCE = read("./components/AuthQuotes.tsx");

test("AuthScene reads useReducedMotion and short-circuits every loop", () => {
  assert.match(SCENE_SOURCE, /useReducedMotion/, "AuthScene imports useReducedMotion");
  // Both animated bits (Cloud + Floating) must gate on it.
  const reducedGuards = (SCENE_SOURCE.match(/if \(reduced\)/g) || []).length;
  assert.ok(reducedGuards >= 2, `expected ≥2 reduced-motion guards in AuthScene, got ${reducedGuards}`);
});

test("AuthQuote freezes to a single static line when reduce-motion is on", () => {
  assert.match(QUOTES_SOURCE, /useReducedMotion/);
  assert.match(QUOTES_SOURCE, /if \(reduced\)/,
    "AuthQuote should bail out of the fade loop on reduced motion");
  // The static branch renders quotes[0] — not a random one, not an animated
  // one — so a screen that just loaded is predictable for accessibility.
  assert.match(QUOTES_SOURCE, /reduced \? quotes\[0\]/);
});
