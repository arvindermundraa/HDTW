# 9. Templates — files for the team to fill in

Four CSV templates live under `docs/nutrition_review/templates/`. Each
template matches a specific item the nutrition team said on 2026-11-06
that they would provide. Column headers are below for quick reference;
the CSV itself is the artifact to edit.

## 1. `grocery_labels.csv` — grocery product labels

For the Week 2 grocery scenario. The nutrition team wrote on 2026-11-06
(Content of app, Q3): *"Yes, I can provide labels for each product type."*

**Columns:**
1. `category` — the Week 2 category this product belongs to. Allowed
   values: `canned_soups`, `cereals`, `breads`, `snack_bars`, `fruit_cups`,
   `canned_vegetables`, `yogurts`, `nut_butters`.
2. `product` — product display name (brand + descriptor).
3. `serving_size` — serving size as it appears on the Nutrition Facts
   label (e.g. "1 cup (240 mL)").
4. `calories` — calories per serving.
5. `saturated_fat_g` — grams of saturated fat per serving.
6. `sodium_mg` — milligrams of sodium per serving.
7. `added_sugars_g` — grams of added sugars per serving.
8. `fiber_g` — grams of dietary fiber per serving.
9. `pct_dv_saturated_fat`, `pct_dv_sodium`, `pct_dv_added_sugars`,
   `pct_dv_fiber` — the four %DV values the app can surface alongside the
   grams/milligrams on Week 2 labels.

The file ships with two empty rows per category to make it easy to drop in
more than one product per category.

## 2. `youth_ambassador_video_tags.csv` — Youth Ambassador video tags

For the recommender described in 11/6, Week 2 content, Q5: *"the app should
use an algorithm to recommend, first, a video featuring a Youth Ambassador
whose circumstances are similar to the user's based on their onboarding
profile … When we provide the Youth Ambassador videos, I will also provide
these 'tags.'"*

**Columns:**
1. `video_id` — short slug the app will store with the video.
2. `video_title` — display title.
3. `ambassador_name` — Youth Ambassador's first name (or pseudonym for
   anonymized clips).
4. `living_situation` — one of: `dorm`, `apartment`, `commuter`,
   `family_home`, `greek_house`. More values welcome — tell us.
5. `eating_setting` — one of: `dining_hall`, `at_home`, `restaurant_takeout`,
   `grocery_convenience`, `someone_else_prepares`. More values welcome.
6. `cooks_or_not` — `yes` or `no`.
7. `other_tags` — a comma-separated list of any other tags that should
   match the onboarding profile (allergy-related, work schedule, etc.).
8. `notes` — anything the engineering team should know about the clip
   (e.g. captions still coming, prefers nickname).

The file ships with 8 example rows pre-filled with representative
living/eating combinations — please overwrite with the real video list.

## 3. `wings.csv` — Wings

For the updated Wing names and goals described in 11/6, Follow-ups, items
5 and 6: *"I will provide the updated Wing names as soon as possible"* and
*"I will specify what counts toward a goal, as this will vary by group.
Users can also be part of multiple Wings."*

**Columns:**
1. `wing_name` — the Wing name as it should appear in the app.
2. `focus_area` — the focus area this Wing is organised around. Allowed
   values: `fruit`, `vegetables_beans`, `grains`, `dairy`, `protein_foods`,
   `fats`, `sodium`, `added_sugars`. More than one? Add extra rows with
   the same `wing_name`.
3. `what_counts_toward_the_goal` — a short, plain-language description of
   the actions/foods that count. The app currently uses one of four
   built-in metrics (balanced meals, veg-forward meals, activity minutes,
   participation days); please describe what you want in words, and the
   engineering team will map it.
4. `weekly_target` — numerical target per week for the Wing's cohort as a
   whole (e.g. "300 balanced meals/week"). Leave blank if "to be set from
   enrollment."
5. `notes` — anything else (e.g. Wing is seasonal, Wing overlaps with
   another Wing by design).

The file ships with one empty row per focus area as a placeholder — please
overwrite with the real Wing list and add rows as needed.

## 4. `week2_scenario_scripts.csv` — Week 2 scenario scripts

For the approved feedback scripts promised in 11/6, Content of app, Q5:
*"I will provide approved feedback scripts for these scenarios as soon as
possible."*

This template is pre-filled with every scripted choice across the
restaurant, "someone else prepares" and at-home scenarios (nine rows
total). Please drop the approved feedback text into the
`approved_feedback` column for each row. The engineering team will replace
the current DRAFT text in `backend/content/weeks/week2.json` with these.

**Columns:**
1. `scenario_id` — one of `restaurant`, `someone_else`, `home`.
2. `scenario_prompt` — the prompt the student sees (shown here so you
   don't have to cross-reference the week2 spec).
3. `option_id` — the stable id for the option; please leave unchanged.
4. `option_text` — the choice text the student sees. Edit only if you want
   to rewrite the choice itself; flag that in `notes` so engineering knows.
5. `approved_feedback` — the approved feedback text, to replace the
   current DRAFT. See `07_week2_scenario_feedback.md` for the current
   DRAFT text side by side.
6. `notes` — anything else.
