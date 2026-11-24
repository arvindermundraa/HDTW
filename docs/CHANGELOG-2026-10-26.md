# 2026-10-26 — "From your meals": the behavior side of Future Me, and the live dining menu

## 1. What this adds, in one paragraph

Future Me now notices what a student actually eats. It reads their own lightweight meal logs, finds the foods that keep coming back ("whole-milk yogurt, most mornings"), and matches one or two swaps from a reviewable table to their focus area and their setup — kitchen, microwave, meal plan, allergies, dislikes. Each swap points at where it is on **today's real Aggie Dining menu** ("Low Fat Vanilla Yogurt · Sbisa breakfast (Rooted)") with a button that opens Build a Meal at that hall and meal with the item already on the plate. The student says "I'll try it", "I tried it" or "Not for me"; Future Me's chat can bring the swap up and propose it as a confirmable action. No LLM is involved in detecting habits or choosing swaps; the model may only reword what the table says.

The two examples that motivated it both work against the real 2026-10-26 menus:

| Student | What Future Me shows |
|---|---|
| Focus **Fats**; logged "whole milk yogurt and granola" at breakfast on 5 of the last 8 days | *You've logged whole-milk yogurt in 5 meals over the last 3 weeks, mostly at breakfast.* **Low-fat or nonfat yogurt** — Your usual yogurt, in a low-fat or nonfat version. Same breakfast, same spot, just a different tub. → Low Fat Vanilla Yogurt · Sbisa breakfast (Rooted) · **Find it at Sbisa** |
| Focus **Grains**; profile says no kitchen; no regular yet | **Oatmeal at breakfast** — Oatmeal is the easiest whole grain to add. Microwave or hot-water oatmeal needs no kitchen, and both dining halls serve it most mornings. → Oatmeal · Sbisa breakfast (Homestyle) |

## 2. Live Aggie Dining — verified and improved

The build sandbox cannot reach `apiv4.dineoncampus.com` (outbound allowlist), which is why the README had carried an "unverified" note since August. Today the API was exercised from a real browser on a team member's machine:

- Both halls × breakfast/lunch/dinner returned real menus (77–133 items each) in exactly the shape `dining_scraper.py` expects: `periods[]` with date-specific ids and `isDefault`, the default period's full menu embedded in the periods response, `menu.period.categories[].items[]` with `name`, `portion`, `desc`, `ingredients`, `filters[]` (allergen and diet labels), `calories` and a `nutrients[]` table. A far-future date returns HTTP 200 with `periods: []`. The location ids from August are unchanged.
- That shape is captured (trimmed to 3 stations × 6 items per period, nutrient rows replaced with representative values) in `backend/tests/fixtures/apiv4_dineoncampus_2026-10-26.json` and replayed through the parser by `tests/test_dining_scraper.py` (13 tests), so the parser stays verified without network access.
- `dining_scraper.py` now keeps each item's plain-text `ingredients` and its `labels` (Egg, Milk, Wheat, Soy, Sesame, Vegan, Vegetarian, …), and `server.item_matches_allergy()` checks both in addition to the name — "Brioche Bun" is now suppressed for an egg allergy. `calories` and `nutrients` are dropped at the source (a test asserts `kcal` never appears in a parsed menu). When the periods call already embeds the wanted period's menu, the second round-trip is skipped. The menu cache is keyed by the study-timezone date, not the server's (Vercel runs on UTC).

A live spot-check from the deployed app (which has no egress restriction) is still the final confirmation; the sample-menu fallback remains in place.

## 3. New modules

- **`backend/twin_habits.py`** — `FOOD_LEXICON` (≈35 foods; whole-word/phrase matching with per-food `exclude` lists and optional `all` groups so "Chobani whole-milk vanilla Greek yogurt" counts as whole-milk yogurt; `parent` links so "yogurt" is dropped when every yogurt was whole-milk yogurt), `detect_habits()` (trailing 21 days in study time; a food in 3+ non-skipped meals is a regular, with its usual slot; status `learning` until 3 distinct logging days), `evidence_line()`, `learning_line()`, `coach_lines()`. Pure functions.
- **`backend/content/swaps.json`** — 44 swaps across the eight focus areas: 35 anchored to a lexicon habit, 9 area defaults. Fields: `focus_area`, `habit`, `slot`, `swap_label`, `text`, `needs` (`none`/`microwave`/`stove`), `log_categories` (what the swap adds — used for allergy suppression), `dining` (search-term groups, priority order), `dining_exclude`, `source`, `reviewed` (all `false` until the nutrition team approves). Loaded and validated at import like the Coach KB; a test runs every label and text through the chat guardrail and asserts no digits.
- **`backend/twin_suggest.py`** — `setup_from_profile()` (no kitchen → `none`/`microwave` ideas only; appliance answers honored; no survey → nothing ruled out), whole-word dislike matching with plural folding, `menu_matches()` (live menus only; slot/habit-slot first; term priority; one listing per dish per hall and meal), `swap_allowed()` / `allowed_swap_ids()` (the authorization check behind every write), `build_suggestions()`, `coach_lines()`.

## 4. `server.py`

- `from_your_meals` block on `GET /future-me`; `GET /future-me/from-your-meals`; `POST /future-me/swaps/{trying|tried|dismissed}` with `SwapPlanIn` (id must exist) and `_internal_set_swap_status()` (`db.swap_plans`, unique per user+swap, latest status wins, `DuplicateKeyError` on a double tap handled). `_twin_menus_today()` runs the six hall/period lookups concurrently with a 6-second budget; slow fetches keep running in the background to fill the cache.
- Coach: `THEIR CONTEXT` gains their regulars, the swap (with `swap_id`), today's menu items and their setup; rule 1 of the system prompt says to use them; `_PERSONAL_PATTERNS` recognizes "what do I usually eat", "my meals", "swap my …", "today's menu"; a `SOURCE: <swap id>` is cited with the swap's own source.
- New chat action `try_swap` through the existing propose → strip → re-validate → `pending_action` → `POST /chat/confirm-action` path, plus `_swap_allowed_for()` at proposal time **and** confirm time: a swap id that exists but was never offered to this student (other focus area, needs a stove they don't have, ruled out by an allergy term or a dislike) is dropped silently at proposal and refused with 404 at confirm and on the card's own endpoints.

## 5. Frontend

- `src/components/FromYourMeals.tsx` — the card on the Future Me tab (evidence, swap, where it is today, Find it at …, I'll try it / Not for me / I tried it, Ask Future Me about it, and the "Noticed in your logs" line in counts only).
- `app/(tabs)/future-me.tsx` — renders the card from `getFutureMe().from_your_meals`; refreshes it after a confirmed `try_swap` or `set_focus_areas`.
- `app/build-meal.tsx` — accepts `hall`, `period`, `add` (item id) and `tab` params; the linked item is put on the plate once the allergy-filtered live menu confirms it's served today.
- `src/api.ts` — `getFromYourMeals()`, `setSwapStatus()`.

## 6. Review pass and what it changed

An independent review of the full diff was run before delivery. Findings and fixes:

1. **Authorization gap (high)** — a valid-but-unoffered `swap_id` passed `SwapPlanIn` and could be confirmed for a nut-allergic student. Fixed with `swap_allowed()` on every write and at proposal time; covered by `test_a_valid_swap_this_student_may_not_have_is_refused_at_proposal_and_confirm`.
2. **Dislike matching** — raw substrings ("eat" ⊂ "wheat", "ice" ⊂ "rice", "egg" ⊂ "veggie") hid unrelated swaps. Fixed: whole-word matching, plural folding, larger stop list.
3. **Existing endpoint tests reached the network** — `tests/conftest.py` now stubs the menu lookup suite-wide.
4. **Menu-term matching** — "milk" matched Buttermilk Pancakes, "apple" matched Applewood bacon, Apple Compote passed as fruit. Fixed: whole-word terms plus fuller exclude lists.
5. **Lexicon false positives** — cream cheese as a cheese sauce, "chicken pot pie" as a sweet, "popcorn chicken" as a whole grain, bare "monster"/"bang" as energy drinks. Fixed.
6. A swap being tried vanished once the habit faded from the logs — it now stays pinned.
7. Background menu tasks are kept referenced; `menu_source` reports `none` correctly; malformed `created_at` is skipped; ingredient text kept in full for allergy matching.

## 7. Tests

`cd backend && python -m pytest tests -n 0 -q --ignore=tests/backend_test.py` → **294 passed** (was 225). New: `test_dining_scraper.py` (13), `test_twin_habits.py` (9), `test_twin_suggest.py` (17), `test_from_your_meals.py` (9), `test_twin_llm.py` (11), `test_twin_engines.py` (10). `tsc --noEmit` reports no errors in any changed frontend file (three pre-existing errors in `log-meal.tsx`/`PlateBuilder.tsx` remain); eslint is clean on the changed files.

## 8. Later the same day — the AI engine, kept alongside the rules engine

Sumanth wanted both ways of making these decisions available during testing, with the team converging later. Built as a staff-side switch (`TWIN_ENGINE=rules|llm`, default `rules`) plus a side-by-side record:

- **`backend/twin_llm.py`** — TAMU AI (a) names the student's regulars from the raw meal-log text, citing the meals that support each one, and the server re-counts those meals itself (whole-word grounding, most of the name's words, 3+ meals; the name is guardrail-checked and shown in the student's own words — "Chobani Flip" needs no lexicon entry); (b) picks among the swaps this student may be offered at all and names today's menu items exactly; (c) adds one short "why". Two stages: the verified model output is cached per day; every read re-applies allergies, dislikes, kitchen setup and the student's taps, re-resolves menu items against the menus available now, pins a swap being tried, and rests dismissed ones — so a cached pick never outlives a newly declared allergy or a "Not for me". No key or a failed call → the rules engine (failures rest five minutes; a missing key is re-checked on the next read). When every model pick fails verification, the rules suggestions stand in.
- **Comparison** — `db.twin_decisions` holds one row per participant per day with both engines' output whenever the AI engine ran; the researcher page's section 8 lists them with a top-swap agreement rate and a regulars-overlap rate, and can run both engines for one participant on demand (`POST /research/twin-decisions/recompute`, using that participant's TAMU key).
- **Review pass #2** on the AI engine found three high-severity holes (cached block bypassing a new allergy; taps not applied to the cache; substring grounding accepting "eggs" for "veggie wrap") and several medium ones (unguarded regular names, a `why` naming allergens or invented items, incoherent regular→swap pairings, failures cached for the day, frozen cold-menu results, malformed-field crashes, inflated agreement when both engines are empty). All fixed by the two-stage design; `test_twin_llm.py` (11) and `test_twin_engines.py` (10) cover them. **294 unit tests pass.**

## 9. Decisions for the nutrition team

- Review `content/swaps.json` and `twin_habits.FOOD_LEXICON`; flip `reviewed` per entry as approved. Some swaps assume a dorm has a microwave or hot water when the profile says "no kitchen" — the texts say "microwave or hot-water", but confirm that's acceptable.
- The threshold (3 meals in 21 days, 3 logging days before anything is said) and the 14-day rest after "Not for me" / "I tried it" are placeholders.
- A grocery list was deliberately not built this pass (the dining menu took its place); the swap table already carries what each swap needs, so a list is a small follow-up if wanted.
