# 2026-11-11 — The behavioral twin: diet, activity and sleep in one profile

## 1. Why

After the "Rules vs AI for From Your Meals" write-up (Oct 28), the study lead asked for the twin to grow from a food-swap card into a multidomain behavioral model: one participant-specific profile across diet, physical activity and sleep (the three behavioral components of AHA Life's Essential 8), built from ASA24 + meal logs, wearable data, what participants tell us, and how earlier recommendations went — and, above all, **no unsupported assumptions**: the twin notices possible patterns, asks participants to confirm them, and adapts. This pass builds that on top of the existing From-your-meals engines (both kept, unchanged).

No LE8 score is computed. The three domains organize the profile; they are never combined into a number (the README's rule from the September rebuild stands).

## 2. What the participant sees

Future Me's "From your meals" card is replaced by **Your routines** (`src/components/TwinCard.tsx`, data from `GET /twin`, also `GET /future-me` → `twin`):

| Part | What it does |
|---|---|
| **Is this right?** | Up to two questions about patterns the twin noticed, each with its evidence in counts ("On 15 of the 15 weekdays your tracker has, you moved less than on a usual weekend day"). Yes / Sometimes / Not really, then optional "What's behind it?" chips (Early classes, Work shifts, Studying late, …) and a free-text note. |
| **Small steps that fit your week** | One or two steps from the reviewed library or the swap table, each with **Why this** (built only from the factors that chose it), when it could fit, an if-then plan for barriers they've named, today's menu item (dining-hall eaters only) and "Add to grocery list". I'll try it / Not for me → reasons; while trying: It's working / Didn't fit → reasons. |
| **Keep going** | Steps that worked stay visible with a reinforcement line tied to the moment they chose; after two weeks, "Still doing it?" |
| **Want help with movement or sleep too?** | Activity and sleep steps are only offered after a confirmed pattern in that domain or an explicit opt-in. |
| **What I've learned about you** | Every fact steering their steps, with its source (You confirmed / You told me / From your feedback / From your profile), each with "Not right" to remove it. |
| **Grocery list** | Items added from steps (text from the reviewed library, never the client) or typed by hand; check off, remove. |

The Rest log gains optional "fell asleep / woke up" times so timing patterns can come from manual logs too.

## 3. New modules (pure functions)

- **`backend/twin_patterns.py`** — detectors over the trailing 21 days: `activity.low_weekdays` / `activity.low_weekends` (weekday vs weekend median minutes, tracker day wins over manual, re-sent device days replace), `sleep.irregular_timing` (trimmed bedtime range or weekday/weekend shift, measured from noon so midnight doesn't break it), `sleep.short_weekdays`, `diet.rushed_weekday_breakfast` (explicit skipped logs only), meal regulars as questions (`diet.regular.<food_id or slug>`), and `cross.weekday_squeeze` (weekday signals in two domains, or one plus a stated schedule). The circumstance vocabulary lives here.
- **`backend/twin_recommend.py`** + **`content/twin_library.json`** — 44 reviewed-pending items (21 diet, 9 activity, 9 sleep, 5 spanning two or three domains) of types add / modify / grocery / routine / plan, each tagged with BCT Taxonomy v1 techniques, contexts, the circumstances it fits, the constraints it respects, effort, cost, needs, food tags and if-then coping plans, plus grocery items for 31 existing swaps. Hard filters, transparent scoring, one step per lane (diet / activity / sleep / across domains), never two cross-domain steps, explanations from factors, reinforcement, and an independent `constraint_violations()` for evaluation.
- **`backend/twin_profile.py`** — the profile: statuses (noticed / confirmed / sometimes / rejected / stated / removed), eating contexts from the survey (dining hall, campus food, takeout, grocery, at home, convenience, someone else cooks) and dining-hall logs, constraints from support needs, circumstances and feedback, the reason taxonomy and keyword interpretation of free-text notes, plan reconciliation with `db.swap_plans`, question selection, the "What I've learned" list, Coach lines.

## 4. `server.py`

- **Endpoints** — `GET /twin`; `POST /twin/questions/answer`; `POST /twin/steps/respond` (accept, decline, worked, didnt_fit, still_doing, lapsed + reasons, note, when, coping); `POST /twin/domains`; `POST /twin/learned/remove`; `GET/POST /twin/grocery`, `PATCH/DELETE /twin/grocery/{id}`. Answer and respond are rate-limited (30/min). Accepting requires the step to be one the twin would offer this participant now (`_twin_step_offered`), the same authorization idea as `swap_allowed`.
- **Storage** — `db.twin_facts` (answers, circumstances, constraints, goals, removals; one row per user+key), `db.twin_plans` (step status, when, coping; swaps mirrored to `db.swap_plans` so the older card and the Coach's try_swap agree), `db.twin_events` (append-only answers and step responses with reasons, note and how it was interpreted), `db.twin_snapshots` (one per user per day: questions, steps with factors and constraint violations, staff ratings), `db.twin_grocery`. Indexes added.
- **AI** — TAMU AI keeps its two jobs from October (naming meal regulars; picking among vetted swaps when `TWIN_ENGINE=llm`) and gains one: mapping a free-text note onto the fixed reason / circumstance lists, only when no keyword matched, keeping only listed codes. Everything else is rules.
- **Coach** — THEIR CONTEXT now carries "Confirmed with them", "They told me", "What matters to them", "Noticed … NOT confirmed (never state as fact; you may ask)", the twin's steps with `step_id`, and steps that worked. New rule 10 (separate domains, no score, ask don't assume, respect constraints, never link movement to food). New action `try_step`, re-checked at proposal and confirm.
- **Safety** — a safety check-in in the last 14 days pauses food and exercise steps and meal questions (sleep steps and reinforcement continue). `not_hungry_early` holds every breakfast-pushing step. Allergy and food-dislike filters apply to every food step, including ones already being tried.
- **Wearables** — `WearableSyncIn` gains `sleep_start`, `sleep_end`, `steps`; a device day is upserted per date (re-syncs replace); `POST /wearable/sync-days` takes up to 31 days. `SleepIn` gains optional `bedtime` / `wake`.
- **Research** — `GET /research/twin-profile?user_id=` (facts, events, plans, snapshots, live view and every candidate's verdict), `POST /research/twin-snapshots/rate`, `GET /research/twin-eval` (pattern accuracy from participants' answers, step outcomes by domain / type / technique, reasons, note interpretation, appropriateness from staff ratings, constraint adherence, feedback incorporation). Researcher page section 9.
- `TWIN_ONLY_REVIEWED=true` restricts participants to steps whose `reviewed` flag is true.

## 5. Tests

`cd backend && python -m pytest tests -q --ignore=tests/backend_test.py` → **549 passed** (was 489). New: `test_twin_patterns.py` (13), `test_twin_recommend.py` (24, including a guardrail and digit check over every library text), `test_twin_api.py` (23, endpoints end to end against the fake DB). A randomized check over 3,000 synthetic profiles (5,598 steps) found no explanation or coping text that trips the guardrail or contains a digit, no new step against a stated constraint, and never two cross-domain steps. `tsc --noEmit` shows only the three pre-existing errors; eslint shows no new findings. The web build was exported and the card and researcher section were exercised in a headless browser against the fake-DB server.

## 6. Decisions for the team

- Review `content/twin_library.json` (44 items) and the grocery map; flip `reviewed` as approved, then consider `TWIN_ONLY_REVIEWED=true`.
- Thresholds in `twin_patterns.py` are placeholders: 21-day window; activity — 4 weekdays + 2 weekend days of data, weekday median below 60% of weekend and 15+ minutes lower, never "low" at 45+ minutes; sleep — 5 timed nights, 90-minute bedtime range or shift, 1 hour shorter on class nights; 3 skipped weekday breakfasts.
- `ASK_ABOUT_SKIPPED_BREAKFAST` is on (the cross-domain example names rushed breakfasts); it never fires during a safety pause. Confirm or turn off.
- Re-ask a "Not really" after 28 days; a confirmed pattern no longer in the data stops steering after 42; a reason keeps shaping steps for 90 days; "Not for me" / "Didn't fit" rest a step 14 days.
- Reminders for an accepted step's chosen time (prompts and cues) are not scheduled yet; the Week 2 reminder plumbing could carry them.
- A real Fitbit / HealthKit / Health Connect read is still the open native-build item (`frontend/src/native/health.ts`); the stub sends hours only and never invents a bedtime.
