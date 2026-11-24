# Changelog — 2026-09-24 test & fix session

A full test pass of LLHS against the requirement documents, fixes for everything that
didn't need a team decision, and a new ASA24 → HEI-2020 upload pipeline.

Requirement documents used (from `~/Downloads/OneDrive_1_9-24-2026`):
*LLHS App Review Notes*, *LLHS App Onboarding Nutrition & Lifestyle Profile*,
*LLHS HEI-2020 National Benchmark Reference* (+ `LLHS_HEI2020_18-25_developer_benchmarks.xlsx`),
*8.18 Meeting Slides*, *Updated DTL Slides 9.10.26*.

**Results at end of session:** backend suite **155 passed, 2 skipped, 0 failed**
(start of session: 101 passed, 3 failed, plus rate-limit noise). Frontend
`tsc --noEmit`: 6 errors, all pre-existing, none new. All screens walked through
in Chrome against a live backend with a real TAMU AI key.

`HDTW-main 3/` is now its own git repository (it was untracked inside the `~/Downloads` repo); this session's work is its first commit.

---

## 1. TAMU AI was failing on the default model (fixed)

**Symptom:** with a valid key, Settings → *Test connection* said *"TAMU AI service
returned an unexpected response"*, and every AI feature on the default chat model
failed.

**Cause:** TAMU's gateway runs the Claude **Sonnet/Opus** model groups with extended
thinking forced on. Bedrock then rejects any `temperature` other than 1 and any
`max_tokens` not above the thinking budget. The app sent `temperature: 0`
(`max_tokens: 20` for the connection test). TAMU also reports upstream failures as
**HTTP 200 with an `error` body**, which the client read as an unexpected response.
Haiku, Gemini and OpenAI models were unaffected (probed live).

**Fix** (`backend/tamus_client.py`): for Claude Sonnet/Opus ids, send
`temperature=1` and `max_tokens ≥ 4096`; detect a 200-with-error body and raise a
readable `TAMUSError` (details logged server-side). Also added the 7 models the live
`/v1/models` listing had but the catalog lacked (Claude Sonnet 4, Opus 4.1–4.8,
3.5 Haiku).

**Verified live:** connection test, Future Me coach, typed-meal categorization,
photo meal analysis, dining chat-build-meal.

## 2. Safety fixes

| Problem | Fix |
|---|---|
| Coach told a participant with a **peanut allergy** to eat "a handful of nuts" — the coach prompt never received onboarding answers | `_profile_survey_context()` adds survey answers (minus gender/race) to the coach context; new prompt rule 8 + an `AVOID` list from the participant's allergy terms. Retested: no nut suggestions; replies now use meal plan / mini fridge / hardest meal. |
| Typed allergy "dairy" still showed yogurt/cheese; "eggs" didn't match "Egg" | `ALLERGEN_FAMILIES` expands typed allergens to foods; plurals singularized; whole-word family matching, so "peanuts" doesn't hide tree nuts (see §4b). |
| Allergy filter skipped dining swap, plate review, plate-builder dining tray; matched names only | Filter applied on every recommendation surface; also checks category/tags (dairy terms drop the dairy category). `GET /dining/menu?for_recommendation=true` returns a filtered menu. Plain menu browse stays unfiltered by design. |

## 3. Bugs fixed

**Backend (`backend/server.py`, `plate_composer.py`, `dining_classifier.py`)**
- Chat-build-meal returned the same dish twice (served at two stations) — deduped, capped at 4.
- Survey: numeric ranges (age 16–99 integer, work hours 0–80) enforced; exclusive "None" options rejected alongside others; answers hidden by skip logic stripped before saving; schema exposes `min`/`max`/`exclusive`/`group_label`.
- `GET /onboarding/profile-survey` returns saved `answers` when authenticated; `PATCH` treats `null` as "clear this answer".
- Focus areas: 1 allowed when the shortlist has fewer than 2 candidates (was a permanent dead end).
- Suggested prompts: 3–4 deterministic, personalized prompts from focus areas, logging gaps and the survey.
- Cohort / weekly-story counts exclude test accounts (`@example.com`, admin test emails, `is_test_account`).
- Wearable sync rejects implausible values (sleep 2–14 h, activity 0–600 min, no future dates).
- Plate suggestions rebuilt: protein-anchored, veg/fruit + whole grain, max one salty item, no condiment-only plates. Classifier now tags by item name only (station names were mis-tagging whole stations).
- Dining menus cached (30 min live / 5 min sample fallback) and pre-loaded at startup — first load was ~23 s.
- `RATE_LIMIT_ENABLED` env var (default on) so the test suite can run without hitting the 5/hour register limit.
- `pillow` added to `requirements.txt` (tests needed it).

**Frontend (`frontend/app/**`, `frontend/src/**`)**
- Onboarding: digits-only number fields with range checks and inline errors (was: "abc" → saved age 0); exclusive options; hidden answers pruned; missing frequency-grid heading added.
- New **Settings → Edit my profile** (reuses onboarding with `?mode=edit`, prefilled, saves via PATCH).
- Health HQ and Learn: per-request error handling + retry instead of crashing on a failed load.
- `src/navigation.ts` `goBack()` replaces all 17 `router.back()` calls — no more stuck spinner after a web refresh/deep link.
- Focus-areas screen supports the 1-candidate case and a 0-candidate empty state.
- Coach: Enter sends on web (Shift+Enter = newline); suggestion chips shown above the input; **auto-scroll to newest message**; `**bold**`/`*italic*` rendered instead of raw asterisks.
- "Welcome" (not "Welcome back") for brand-new users; FAB no longer covers Health HQ content.
- Plate builder: allergy-filtered dining tray, meal type from time of day, categories from item tags.
- Settings model chips wrap instead of being cut off.

**Tests (`backend/tests/`)** — two stale dining tests updated for the live menu; rate-limit test skips when limiting is off; `.env` loading falls back gracefully; new classes for survey validation, allergy surfaces, cohort exclusion, wearable plausibility, plate balance, profile edit.

## 4. New: ASA24 → HEI-2020 upload

ASA24 has no API and may not be scraped, so the one manual step is staff exporting
the **Totals** CSV from the ASA24 Researcher website. Everything after that is in
the app. Staff guide: [`ASA24-STAFF-GUIDE.md`](ASA24-STAFF-GUIDE.md).

- **`backend/hei2020_scoring.py`** — line-for-line Python port of NCI's
  `hei2020.score.macro.sas` v1.0 (12/11/2024), with derived inputs and the
  **per-person method (sum all recalls, score once)** taken from NCI's ASA24
  per-person example program. Both downloaded 2026-09-24 from
  <https://epi.grants.cancer.gov/hei/sas-code.html>.
- **Endpoints** (all require a researcher sign-in or the shared `X-Research-Key` — see §4b):
  - `GET /api/research/participants` — participants, linked ASA24 username, assessments imported
  - `PUT /api/research/asa24/links` · `DELETE /api/research/asa24/links/{username}`
  - `POST /api/research/asa24/preview` — parse + score, read-only; per-row status `ready` / `unmatched` / `exists` / `not_selected` and warnings (≠2 recalls, duplicate RecallNo, kcal outside 500–5000)
  - `POST /api/research/asa24/import` — stores selected rows into `hei_assessments` (same shape as before, plus `summed_inputs`, `total_score`, `recall_count`, `warnings` for audit); skips existing unless `overwrite`
- **Researcher page:** `GET /research-admin` (static HTML served by the backend; session token held only in that tab's sessionStorage).
- **Tests:** `tests/test_hei2020_scoring.py` (9 unit tests incl. a hand-worked two-recall case = 60.00) + `TestAsa24Upload` (link → preview → import → overwrite → unlink). Synthetic fixture: `tests/fixtures/asa24_totals_sample.csv`.

**Not yet verified:** cross-check against R `dietaryindex` or NCI SAS on a real
de-identified export (R isn't installed here); ASA24-2022/2024 column names
(the port uses NCI's 2016/2018/2020 example's names — the upload names any
missing column); the 500–5000 kcal review range is a placeholder.

## 4b. Follow-up the same day (open items 12–17)

- **Coach focus-area actions:** the prompt said "focus-candidate ids below" but never listed any. It now lists the participant's real shortlist and the count the server accepts (1 when there's only one candidate; "never propose" with no assessment). Verified live.
- **Plate-review suggestion filter** extracted to `safe_review_suggestions()` and unit-tested (`tests/test_server_helpers.py`), since HTTP tests can't reach it without a TAMU key.
- **Allergy over-filtering fixed:** allergen families now match whole words, so "peanuts" no longer hides every tree nut and coconut (or "shellfish" all finfish). Stored `allergy_terms` are re-derived for every participant at startup, so rule changes reach existing accounts.
- **Researcher accounts** replace the shared key for people: `db.researchers` (bcrypt), `POST /research/auth/login|logout`, `GET /research/auth/me`, admin-only `GET/POST /research/researchers` and `PATCH /research/researchers/{id}`. Tokens are scoped `research` (8 h, `RESEARCH_TOKEN_HOURS`) and can't be used on participant endpoints, or vice versa. Imports and links record `imported_by`/`updated_by`. The shared `RESEARCH_API_KEY` still works for scripts while set. First admin: `python backend/manage_researchers.py add <email> --admin`. `/research-admin` now has a sign-in form and an admin Researchers section.
- **Mark test accounts:** `PATCH /research/participants/{id}` (`is_test_account`) plus a checkbox on the research page; the weekly-story test uses it to clean up.
- **Build tab filtered:** the Build-a-Meal tray now uses `for_recommendation=true` and shows "N items hidden because of your allergies or restrictions · Show everything" (`hidden_count`, distinct dishes).
- **Git:** `HDTW-main 3/` initialised as its own repository with a first commit.

## 5. Files changed

Backend: `server.py`, `tamus_client.py`, `plate_composer.py`, `dining_classifier.py`,
`requirements.txt`, `tests/backend_test.py`; **new** `hei2020_scoring.py`, `manage_researchers.py`,
`research_admin.html`, `tests/test_hei2020_scoring.py`, `tests/test_server_helpers.py`, `tests/fixtures/asa24_totals_sample.csv`.

Frontend: `app/_layout.tsx`, `app/(tabs)/coach.tsx`, `app/(tabs)/index.tsx`,
`app/(tabs)/learn.tsx`, `app/auth.tsx`, `app/build-meal.tsx`, `app/focus-areas.tsx`,
`app/game/[id].tsx`, `app/log-meal.tsx`, `app/onboarding.tsx`, `app/path.tsx`,
`app/settings.tsx`, `app/video/[id].tsx`, `app/weekly-story.tsx`, `src/api.ts`;
**new** `src/navigation.ts`.

Docs: this file, `docs/ASA24-STAFF-GUIDE.md`, `README.md`, `memory/PRD.md`, `QUICK_START.md`.

## 6. Still open

**Needs a team decision (nutrition team / DTL)**
1. Show participants their own HEI component numbers ("4.2 / 10" on Health HQ), or direction only?
2. "Strength" vs "room for improvement": judged against the national benchmark or HEI max? Tolerance (0.3 is a placeholder)?
3. "Score This Plate" scoring criteria.
4. Allergies: is free-text + name/category matching enough, or a structured allergen checklist?
5. Wearables: Fitbit Web API vs HealthKit/Health Connect vs manual only (currently simulated random sleep).
6. Move / Rest reference values and feedback.
7. Wings: usernames/identifiers and privacy.
8. Final bottom navigation and Coach tab name ("Coach" vs "Future Me"); Learn header mixes baseline videos with "Youth Ambassador".
9. ASA24 data-quality rules (kcal range, incomplete recalls) and the one-sum vs per-day choice confirmed in the protocol.

**Known remaining technical items**
- ~~Coach focus-area prompt, plate-review suggestion test, weekly-story test leftover, shared research key, git~~ — done, see §4b.
- Once every staff member has a researcher account, unset `RESEARCH_API_KEY` in production.
- Expo started with `CI=1` has no file watching; restart after frontend edits.

## 7. Environment notes from this session

- Ran against a scratch MongoDB on port 27018 and backend on 8010 (8000/8081 were in use by another local project); frontend on 3000 with `EXPO_PUBLIC_BACKEND_URL=http://localhost:8010`.
- The TAMU key was never written to any file; it's stored only Fernet-encrypted in the scratch dev database. Since it was pasted into a chat, rotate it.
- Browser safety rules prevented typing passwords/keys into web forms during testing; those steps went through the API instead.
