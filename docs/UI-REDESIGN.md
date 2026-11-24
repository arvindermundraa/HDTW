# UI redesign (branch `ui-redesign`)

A refreshed look and navigation for the LLHS app, based on the client mockups in the *Updated DTL Slides 9.10.26* (slides 11, 19 and 21) and on BetterMe-style clarity. The result was then toned down to a mature, restrained style suited to college students. **Every existing feature is kept**; what changed is how the app looks and how you move around it, plus two new features: a personal, interactive My Path, and daily rings.

`main` is unchanged. Nothing here is merged yet.

## What changed

### Look and feel
- **Colours:** neutral greys, a deep forest-green primary, and muted accents that tell the three domains apart: **Eat** forest green, **Move** burnt orange, **Sleep** slate blue. This replaces the earlier sage-and-cream "editorial" theme.
- **Type:** Plus Jakarta Sans throughout, with semi-bold headings and tighter spacing. Playfair serif headings and handwritten notes are gone.
- **Cards:** white, with hairline borders and 14px corners.
- These tokens live in `frontend/src/theme.ts`. Screens that weren't rewritten (Learn, Future Me chat, Log, Settings, Wings, Build a Meal, and others) pick up the new look automatically.

### Navigation
- **Bottom bar:** Today · Path · **+** (log) · Learn · Future Me. It stays at 5 items.
- **The Coach is not a tab.** It opens from "Ask the Coach" buttons on Eat, Learn, the daily rings, My Path and Future Me (each pre-fills a suitable question), and from the chat icon in the Today header. *Tab naming is still a team decision; this is the current choice.*
- **Progress** (the old *Me* tab) opens from the points badge or avatar on Today. **Wings** (Social) is under Progress → Challenges. Both keep their routes.
- The old `/path` link redirects to the Path tab.

### Screens
| Screen | What it shows |
|---|---|
| **Today** (replaces Health HQ) | Daily rings, one Future Me note, a 4-item plan for today built from real logs (log a meal, add your focus food, move, next lesson), the days you logged Eat, Move and Sleep, a My Path preview, and links to Build a Meal and Weekly Story. The safety check-in, pull-to-refresh and error states are kept. |
| **My Path** (now a tab) | The personal, interactive trail (see below), a check-in countdown, and "Up next" and "Done" lists. |
| **Eat** (`app/(tabs)/eat.tsx`, a hidden tab so the bottom bar stays) | Laid out like the client mockup (slide 11): your avatar and title; a pale green **Your strengths** card and a pale warm **Your focus areas** card, where each row has a Fluent food picture, a bar for **days logged this week ("N of 7 days")** and the component's own fixed encouraging line; strengths also get the direction-only note "Above the national average for adults 18–25", and focus areas get no national comparison; then **Future Me says** with Ask Future Me and Build a meal. The bars are never the HEI score, and no HEI numbers appear. |
| **Progress** (replaces Me) | Laid out like the client's Progress mockup: your avatar with one Future Me line, a stat card (points, day streak, badges "X of 4"), a level card with a mountain, then Badges / Challenges / Streaks tabs. Streaks shows the last 7 days as rings. It also holds Focus areas, Daily goals, Your avatar, Settings and Sign out. |
| **Daily goals** (new, `app/goals.tsx`) | Set, change or pause each ring's daily target. |

### New: personal, interactive My Path
- **Milestones come from each participant's own data** (`backend/personal_path.py`). They are always behaviours, never outcomes:
  - Focus-area milestones exist only for the areas this participant chose, e.g. "Whole Grains in 3 meals".
  - Meals, movement and sleep use levels (1 → 5 → 15 → 30 meals…). The path shows every level reached plus the next one, so it grows with the participant.
  - Lessons, practice games and check-ins reflect what they've actually done, plus the next one.
  - Reached milestones are dated and in the order they happened; upcoming ones are ordered by how close the participant is.
- **Interactive:** tap a pin, the avatar or a list row to see the milestone, its date or progress ("24 of 30"), and a shortcut button (Log a meal, Watch, Play, and so on).

### New: daily rings (Apple Watch style)
- Three rings: **Eat** (meals that include a chosen food group), **Move** (minutes) and **Sleep** (hours). They fill from what the participant logs that day, in their own timezone, and reset daily.
- One tap on **Start** uses suggested goals (2 meals, 30 minutes, 8 hours), or the participant can **Customize**.
- A participant's first goals start immediately; changes to an existing goal start the next day.
- This is built on the rings work from `codex/goals-progress` (`backend/daily_goals.py`, `GoalRings.tsx`).
- **Tap to log:** tapping a ring, or its row in the legend, opens the matching log mode (Eat → log a meal, Move → activity, Sleep → sleep).
- **"X to go"** under each open ring ("1 meal to go", "10 min to go", "1.5 h to go").
- **Closing animation:** when a ring goes from open to closed, one fixed pulse plays (the same 700 ms expand-and-fade every time). It plays once per ring per day, never for the extra lap, and not at all with reduce-motion on.
- **Weekly recap** under the 7-day strip: "Closed all rings on N of 7 days", with a count for each ring. Days before any goal was set show as **"not set"** (a dashed circle), never as misses, and don't count toward the recap.
- **Past the goal (Apple Watch style):** Eat and Move keep drawing a second lap for the extra amount. The first lap turns a lighter shade, the extra lap is drawn on top in full colour with a soft shadow at its leading end, and the text shows the extra ("30 / 30 min · +10 min", "2 / 2 meals · +1"). At most 2 laps are drawn (200%); beyond that only the "+N" keeps counting. The small rings in the 7-day strip and on Progress → Streaks show it too. With reduce-motion on, the extra lap is drawn without animating. **Overflow is visual only:** no extra points and no extra avatar mood beyond "ring closed". The maths lives in `src/rings.ts`, tested by `src/rings.test.ts` (`npm run test:unit`).
- **Sleep never draws an extra lap.** It closes at the goal and stays closed, because sleeping more than the goal isn't something to encourage.
- **Move this week:** a small secondary line, "Move this week: N of about 150 min", counted from all Move logs over the 7 days (with or without a goal). It comes from the backend as `week.move_minutes` in `GET /api/daily-goals`.

### New: your own avatar, with a daily mood
- **Build it once:** skin tone, hair (style and colour), face, glasses, outfit (style and colour) and background. The builder (`app/avatar.tsx`) is an optional step at the end of first-time onboarding ("Skip for now"), and it opens any time from **Progress → Your avatar** or **Settings → Your avatar**.
- **Art:** original layered SVG parts drawn for LLHS (`src/components/AvatarArt.tsx`), in the app's muted palette. No Memoji, Bitmoji or third-party avatar art is used, so there are no licence terms to track.
- **Daily mood**, computed on the backend from today's rings and logs (`backend/avatar.py`, returned as `mood` by `GET /api/daily-goals`) so every screen agrees:
  - 0 rings closed → **calm**, 1–2 → **content**, 3 → **energised** with a soft glow.
  - Small props for today's logs: a salad bowl after a meal with vegetables, sneakers after any movement, brighter "rested" eyes after a sleep entry.
  - Only the expression, glow and props change. **The body, its size and its shape never change**, there is no sad, sick or tired state, and the mood resets to calm each morning. Simulated wearable data doesn't count, matching the rings.
  - The glow's gentle pulse is turned off when the device's reduce-motion setting is on.
- The avatar appears on Today (header and the Future Me card), My Path, the Future Me tab and Progress.

> **⚠ Team decision needed — avatar vs. the 9/10 deck.** Slide 20 of the 9/10 deck says *"the avatar's appearance never changes, only its position on the path."* Our version keeps the body fixed forever, but the **expression and small props do change day to day** (and reset each morning), following the participant-driven request for a customisable avatar that reflects daily logging. Please confirm this is acceptable, especially against the body-image caution on slide 13 of the 8/18 deck. Turning the daily mood off is a one-line change (always return `calm` with no props).

### New: 3D figures (Microsoft Fluent Emoji)
- The figures are Microsoft **Fluent Emoji 3D** PNGs (MIT licence). Only the 28 that are used are bundled, under `frontend/assets/icons/fluent/`, with a `LICENSE` file that lists each one. The registry is `src/fluent.ts`.
- **Used only for things that exist:** points ⭐, streak 🔥, badges 🛡; the 4 real badges (First Lesson 🎓, Skill Builder 🧩, Consistent Logger 🌱, Balanced Week 🥗); the cohort goal 🤝 and Your Wing 🪽; the level card ⛰️ with a 🚩; 🏆 and 🎯 on the Eat cards; and food pictures for every HEI-2020 component (two where the mockup combines them: fruits 🍎🍌, vegetables 🥬🥕, seafood & plant protein 🐟🥜). The component mapping, with each component's log categories, pictures and fixed encouraging line, lives in one place: `src/food.ts`.
- They sit inside pale domain-tinted circles or tiles as accents. The layout, type and neutral palette stay the same.
- **Progress, compared with the mockup:**
  - Kept: the stat row, the level card with the mountain, the badge row, and the challenge rows with segmented bars.
  - Left out: the **Rewards** tab (it hints at variable rewards), the invented badges (Meal Logger, Move More, and others), the invented challenges (More Plants, Step It Up, Hydration Hero), and anything about water.
  - Badges show as "X of 4"; badges not yet earned are greyed with "Not yet" (no locks).
  - "Completed challenges" appears only when the cohort goal or your Wing really reaches its target.
  - Future Me's line is fixed text chosen by how many days you logged this week, never random.
- **Eat, compared with the mockup:** the layout is copied. The handwritten notes are dropped ("Progress over perfection" survives as a small Plus Jakarta Sans chip), as are the decorative leaves and sparkles. The tints are paler, every bar is labelled "N of 7 days" so it can't be read as a score, and the bottom bar is ours.

### New: Future Me and the Coach are now two separate features
| | **Future Me** (the digital twin) | **Coach** (questions and answers) |
|---|---|---|
| Screen | The Future Me tab, `app/(tabs)/future-me.tsx` | `app/coach.tsx` |
| Answers from | The student's own data: focus areas and strengths from ASA24, logs and the rule-based what-if engine | The reviewed knowledge base in `backend/content/kb/`, searched with BM25 for each question |
| Backend | `GET /api/future-me`, `POST /api/future-me/what-if` (`backend/future_me.py`) | `POST /api/chat`, `/chat/history`, `/chat/suggested-prompts`, `/chat/confirm-action` (`backend/coach_kb.py`) |
| Output | Direction only, never a number | Short answers naming the entry used ("From: Whole grains basics") |

**Future Me** shows the student's avatar with a fixed line about this week, three separate Eat / Move / Sleep cards (never one score), "What if…?" with 3–4 presets built from their own focus areas plus a Move one, and the check-in countdown. Tapping a preset runs `simulate_scenario()`. The reply is direction-only text ("If you swap in a whole grain at lunch, that would move your Whole Grains closer to your goal."). The LLM may only reword that sentence, and its rewording is used only if it passes the guardrail and contains no digits at all; otherwise the engine's own sentence is shown. The engine's values are never returned by the API. The "Future Me says" cards on Today, Eat and Progress open this screen.

**The Coach** answers only from what it retrieves and names the entry it used. If nothing relevant is found it says it doesn't have that information and suggests asking the study team, without calling the model. It politely declines medical, weight-loss and calorie questions (also without calling the model). The guardrail runs on every reply. It keeps the last 10 messages of each conversation (stored per user and session, "New chat" starts another) and sends them to `run_llm`. Starter questions are personalised from the student's focus areas, recent logs and onboarding answers. Logging actions stay proposals with Confirm / Dismiss. The old bug where Confirm could stay on "confirming" forever is fixed (it read a stale message list). Requests time out instead of spinning, with a "Try again" on errors, and with no TAMU key the screen explains how to add one in Settings.

**Knowledge base:** 25 draft entries covering all 13 HEI-2020 components, the three curriculum areas (planning, applying nutrition information, assembling balanced meals), and common college questions (dining halls, meal plans, cheap swaps, label reading, snacks, eating out), plus activity, sleep and support. Each is based on the Dietary Guidelines for Americans 2020–2025, MyPlate, the HEI-2020 documentation (and FDA, Physical Activity Guidelines and CDC sources where relevant) and cites its source. **All entries are `reviewed: false` until the nutrition team approves them.** See `backend/content/kb/README.md` for how to add or edit entries.

**Guardrail on the other AI endpoints:** plate review (summary, strengths, suggestions), meal text categorisation (suggested name) and photo analysis (items, suggested name) now run model text through the same two-layer guardrail, block and log anything that trips it, and fall back to neutral text. This closes the open bug from the earlier review.

### Future Me vs. the Coach: what existed and who owns it
Before this step, the Future Me tab opened one chat (`app/(tabs)/coach.tsx` → `POST /api/chat`) that mixed two jobs. This is where each part lived (all in `backend/server.py`) and which feature it now belongs to:

| Existing part | Where | Belongs to |
|---|---|---|
| What-if engine `simulate_scenario()` (rule-based, direction only) | "Deterministic what-if simulation engine" block | **Future Me** |
| `build_ai_chat_context()` (focus areas, strengths, logs, My Path, Wing, profile) | before the chat-actions block | **Future Me**: retired, `GET /api/future-me` now reads the same sources directly |
| `_next_checkin_info()` check-in countdown | next to `GET /api/path` | **Future Me** |
| Hardcoded `KB` list + keyword `retrieve()` | "Curated knowledge base" block | **Coach** (moved to `backend/content/kb/`) |
| `POST /api/chat`, `/chat/history`, `/chat/suggested-prompts` | "Future Me — RAG-lite grounded coach" block | **Coach** |
| `ACTION_JSON` proposals + `POST /chat/confirm-action` | "Chat-driven actions" block | **Coach** (proposals stay proposals until confirmed) |
| Two-layer guardrail `_guardrail_violation_type()` (numbers + restriction phrases) and `guardrail_blocks` logging | "Chat AI meal-builder" block | **Both**: every Future Me and Coach reply passes through it |
| `run_llm()` → `tamus_client.chat()` | before `/chat` | **Both** |

### Backend changes
- `GET /api/path` is rebuilt per participant. The response keeps the fields the old one had (`position`, `milestones[].id/label/behavior/achieved`, `next_checkin`) and adds new ones.
- New `GET/PUT/DELETE /api/daily-goals` endpoints.
- New read-only `GET /api/activities` and `GET /api/sleep` endpoints, used for Today's "days logged".
- Choosing focus areas now records `focus_areas_set_at`, which dates that milestone.
- New `PATCH /api/profile/avatar` saves the chosen parts in `users.avatar` (unknown values and any body/size field are rejected with 422). `GET /api/auth/me` returns `avatar` (`null` until one is built).
- `GET /api/daily-goals` now also returns `mood` (see above), even before any ring goals are set; it takes an optional `tz` for that case.

## Rules the design keeps
- No calories, weight or HEI numbers are shown to participants. Strengths get a direction-only national note; focus areas never do.
- Eat, Move and Sleep are never combined into one score.
- The avatar's body never changes. Only its expression and small props respond to the day's logs, and they reset every morning (pending team confirmation, see above).
- Points, levels and badges are effort-only, and there is no "Rewards" tab.

## How to try it
```bash
git fetch origin && git checkout ui-redesign
./start-mongodb.sh
./start-backend.sh      # backend/.env as usual
./start-frontend.sh     # frontend/.env → EXPO_PUBLIC_BACKEND_URL
```
Create an account with a TAMU email (or sign in), complete onboarding, log a few meals, and open Today → **Start** to set up the rings.

- **Phone-sized view in Chrome:** press Cmd+Option+I, then Cmd+Shift+M, and pick an iPhone.
- **Focus areas:** the focus-area milestones and the Eat screen need an HEI assessment. A researcher can import one via `/research-admin`.

## Testing
- `backend/tests/test_personal_path.py`: 11 new unit tests covering the personal path rules and ring counting.
- `backend/tests/test_avatar.py`: 9 tests for avatar validation (including that no body field exists), the mood steps, props, the daily reset, and the `PATCH /api/profile/avatar` endpoint.
- `backend/tests/test_coach_kb.py` (25 tests): every KB entry is a cited draft, all 13 HEI components and 3 curriculum areas are covered, no entry would trip the reply guardrail, sample questions find the right entry, off-topic questions find nothing, and the medical / weight / calorie checks.
- `backend/tests/test_coach_and_future_me.py` (17 tests, real endpoints with an in-memory database and a stubbed LLM): the Coach cites its entry, keeps 10 messages of memory per session, says "I don't have that information" without calling the model, declines out-of-scope questions, blocks a reply that mentions calories, keeps actions as proposals and explains a missing key; Future Me returns three domains with no scores and never passes on a number from the model; the guardrail now covers categorize-text and review-plate.
- `frontend/src/rings.test.ts`: 10 tests for ring laps, "+N" and "to go" text at 0%, 50%, 100%, 117%, 200% and 350%, the 2-lap cap, Eat's "+N", and Sleep never overflowing. Run with `cd frontend && npm run test:unit` (Node's built-in test runner, no extra dependencies).
- With the existing HEI and helper tests, **78 backend unit tests pass**:
  ```bash
  cd backend && python -m pytest tests/test_coach_and_future_me.py tests/test_coach_kb.py tests/test_avatar.py tests/test_personal_path.py tests/test_hei2020_scoring.py tests/test_server_helpers.py -n 0
  ```
- Frontend `tsc --noEmit`: 3 errors remain, all ones `main` already has (it has 6; this branch fixes 3).
- Every rebuilt screen was checked in a phone-sized browser against a live backend.
- **Not yet run on this branch:** the full HTTP suite (`backend/tests/backend_test.py`), and testing on a physical device through Expo Go.

## Open questions for the team
1. **Avatar:** is a daily mood (expression and props only, never the body) acceptable given 9/10 slide 20? See the note under "your own avatar".
2. **Ring targets:** are the suggested goals (2 meals / 30 min / 8 h) and the "changes start tomorrow" rule right?
2a. **Weekly Move line:** is showing "Move this week: N of about 150 min" (the adult activity guideline) acceptable, given that Move reference values are still an open team decision? It's a small secondary line and can be removed in one place.
2c. **Coach knowledge base:** all 25 entries are drafts (`reviewed: false`). The nutrition team needs to review them, and to say whether the Coach should hide unreviewed entries until then.
2d. **Tab naming:** the bottom bar keeps "Future Me" for the digital twin, and the Coach opens from buttons and the Today header rather than having its own tab.
2b. **Sleep past the goal:** Sleep closes at the goal but deliberately draws no extra lap and no "+N" (Eat and Move do). Is that the right call?
3. **Levels:** these are 200 points per level, calculated on the phone. Should the backend own them?
4. **Two badges can never be earned.** The backend never awards "Consistent Logger" or "Balanced Week" (an existing bug, not introduced here).
5. **Naming:** the Log screen still says "Rest" where the new screens say "Sleep". Pick one.
6. **Cohort "this week":** every "week" in the app — rings' 7-day strip, Progress → Streaks, Move 150-min target, Future Me "days logged", cohort balanced-meals total — is a **rolling 7-day window ending today** in the study TZ (America/Chicago). There is no calendar-week boundary anywhere. The cohort window especially could become a true Mon–Sun calendar week later (e.g. a Sunday-night reset banner, a weekly recap post), which would be a product/team decision — the plumbing is one new helper (`study_calendar_week_start()` in `backend/study_time.py`) when needed. Flagging here so the choice isn't accidentally made by one PR.
