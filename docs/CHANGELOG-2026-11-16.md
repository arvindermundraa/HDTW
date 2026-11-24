# 2026-11-16 — Food swaps: nutrition team review applied

Source: `Swaps.xlsx` from the nutrition team (Chinanu), 2026-11-16: 44 revised originals and 39 new proposals.

## What changed

**The 44 original swaps** (`backend/content/swaps.json`)
- Label and participant-facing text replaced with the team's wording. Ids, triggers and allergy categories are unchanged, so saved "trying" / "dismissed" states carry over.
- All 44 are now `reviewed: true` (40 "Revised", 4 "Approved with edit").
- Each row gains a `review` block with the team's status, action type, setting, equipment and caveat, for traceability.
- Menu search terms realigned where the revised wording changed the food (13 swaps). For example, `grains_pasta` no longer matches chickpea pasta (per the caveat), the burger swaps match bean or veggie burgers only, and `fats_default_nuts_oils` (now an olive-oil dressing or hummus) no longer matches nuts.
- `added_sugars_juice` now triggers on sweetened fruit drinks (lemonade, fruit punch, Capri Sun…) instead of any juice, per the caveat on #43; plain juice stays with `fruit_juice`.

**38 new proposals** added as `reviewed: false`, so they show only while `TWIN_ONLY_REVIEWED` is off.
- #73 (noodle seasoning) is skipped: the sheet marks it a duplicate of #34 (`sodium_instant_noodles`).
- Four have no trigger food and work as area defaults: ready-to-eat vegetable, yogurt with a snack, nuts or seeds as a snack, and oil in place of butter.

**27 new trigger foods** in `backend/twin_habits.py`, e.g. toast, tacos, quesadillas, sandwiches, rice and beans, crackers, smoothies, bubble tea, sports drinks and sweet tea. Sweet tea folds into soda when it explains every soda meal.

**Allergy check now reads the whole swap** (`twin_suggest.swap_allowed`). Revised labels are often general ("Include seafood or plant protein in a meal"), with the food named only in the text, so checking the label alone would have offered fish or nut swaps to students with those allergies. It may over-block (for example, "Nutrition Facts" trips "nut"); that is the safe direction. Dislikes are still checked on the label only.

## Needs the nutrition team

1. **Wording without digits.** The app shows no numbers, so "100%" was rephrased in three rows; each is marked `reworded_for_app`:
   - #12 `grains_white_bread`: "…bread that lists whole wheat first…"
   - #43 `added_sugars_juice`: "…whole fruit or juice with no added sugar…"
   - new `fruit_fruit_cup`: "…packed in water or its own juice…"
2. **"less" is now allowed.** The swap-text tests used to ban it; the team's wording uses it in 5 rows ("ask for less syrup", "less of the seasoning packet"). The ban list keeps avoid, cut, skip, lighter, guilt, unhealthy and bad.
3. **Equipment the app can't express.** "Blender" (smoothie) and "Sink" (rinsing canned beans) are mapped to no equipment; the text is conditional ("If you make smoothies…").
4. **Approve the 38 new proposals**, then flip `reviewed` to true.

## Known gaps

- Allergies named by ingredient (sesame in hummus, soy in tofu or edamame) aren't caught unless the allergy term itself appears in the swap text. This is unchanged from before.

## Tests

`cd backend && python -m pytest tests -q --ignore=tests/backend_test.py` → **492 passed** (was 489). Old-label assertions were updated, the "nut swap" examples now use `fats_butter_toast`, and there are new tests for allergens named only in the text, the new triggers, and the sweet-tea fold.
