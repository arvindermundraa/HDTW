# 5. Build a Balanced Meal

**Source:** `backend/server.py` — `INGREDIENT_LIBRARY`, `PLATE_ROUNDS`,
and `score_plate()` (one source of truth for all three).

Context: "Build a Balanced Meal" (game g3) is a drag-and-drop screen.
The student picks a situation (a "round"), drags 2–5 items from the tray
onto a plate, and the app reads back a feedback sentence based on what's
on the plate. All feedback is coverage-based (does the plate cover a
vegetable or fruit, a whole grain, and a protein?) — never calories or
grams.

The nutrition team said on 2026-11-06 (Follow-ups, item 3) that all four
practical filters (time, budget, no-kitchen, equipment) should show at
the same time, and that they would review the expanded food list.

The food list, the situations (rounds), and the feedback rules and texts
are below. All of the plate-scoring text is **DRAFT** — the code carries
an explicit TODO for the nutrition team to replace it.

## 5A. Food list — ingredients tray

All 22 ingredients the student can add to the plate, grouped by the
category the game draws from. Each row shows the food group + log
categories (which of the 9 meal-log tags it counts toward) + the
practical filters the team asked for (prep minutes, cost, kitchen).

Cost scale: `$` = under about \$2 / serving, `$$` = \$2–5 / serving.
Kitchen: `none`, `microwave`, `stove`, `oven`.

### Protein (6)

| # | id | Name | Log categories (tags) | Prep (min) | Cost | Kitchen |
|---|---|---|---|---|---|---|
| 1 | `grilled_chicken` | Grilled chicken breast | other_protein | 20 | $$ | stove |
| 2 | `baked_salmon` | Baked salmon | beans_fish_nuts | 20 | $$ | oven |
| 3 | `black_beans` | Black beans | beans_fish_nuts | 5 | $ | none |
| 4 | `almonds` | Almonds | beans_fish_nuts | 0 | $$ | none |
| 5 | `fried_chicken` | Fried chicken | salty_processed | 25 | $$ | stove |
| 6 | `bacon` | Bacon | salty_processed | 10 | $$ | stove |

### Grain (4)

| # | id | Name | Log categories (tags) | Prep (min) | Cost | Kitchen |
|---|---|---|---|---|---|---|
| 7 | `brown_rice` | Brown rice | whole_grains | 15 | $ | microwave |
| 8 | `whole_wheat_tortilla` | Whole-wheat tortilla | whole_grains | 0 | $ | none |
| 9 | `white_rice` | White rice | refined_grains_starchy | 15 | $ | microwave |
| 10 | `dinner_roll` | Buttered dinner roll | refined_grains_starchy | 0 | $ | none |

### Vegetable (4)

| # | id | Name | Log categories (tags) | Prep (min) | Cost | Kitchen |
|---|---|---|---|---|---|---|
| 11 | `steamed_broccoli` | Steamed broccoli | vegetables | 5 | $ | microwave |
| 12 | `side_salad` | Side salad | vegetables | 5 | $ | none |
| 13 | `roasted_carrots` | Roasted carrots | vegetables | 25 | $ | oven |
| 14 | `french_fries` | French fries | salty_processed | 20 | $ | oven |

### Fruit (2)

| # | id | Name | Log categories (tags) | Prep (min) | Cost | Kitchen |
|---|---|---|---|---|---|---|
| 15 | `apple_slices` | Apple slices | fruit | 2 | $ | none |
| 16 | `fruit_cup` | Fresh fruit cup | fruit | 5 | $$ | none |

### Dairy (2)

| # | id | Name | Log categories (tags) | Prep (min) | Cost | Kitchen |
|---|---|---|---|---|---|---|
| 17 | `greek_yogurt` | Greek yogurt | dairy | 0 | $ | none |
| 18 | `cheese_slice` | Cheese slice | dairy | 0 | $ | none |

### Other (4)

| # | id | Name | Log categories (tags) | Prep (min) | Cost | Kitchen |
|---|---|---|---|---|---|---|
| 19 | `avocado` | Avocado slices | other_protein | 2 | $$ | none |
| 20 | `cheese_sauce` | Cheese sauce | salty_processed | 5 | $ | microwave |
| 21 | `gravy` | Gravy | salty_processed | 5 | $ | microwave |
| 22 | `hummus` | Hummus | beans_fish_nuts | 0 | $ | none |

## 5B. Situations (rounds)

The student picks a situation before building. Current rounds, verbatim
from `PLATE_ROUNDS` — these are **DRAFT**:

### 1. Dinner, full kitchen — **DRAFT**

- **id:** `r1`
- **Constraint note shown to the student:** *Everything's available
  tonight. Build a balanced plate.*
- **Tray:** the full ingredient list above (all 21 items).
- **Plate size:** 2–5 items.

### 2. No stove tonight — **DRAFT**

- **id:** `r2`
- **Constraint note shown to the student:** *Pantry and fridge only —
  assemble what you can without cooking.*
- **Tray (10 items):** Black beans, Whole-wheat tortilla, White rice,
  Side salad, Avocado slices, Hummus, French fries, Cheese sauce, Greek
  yogurt, Apple slices.
- **Plate size:** 2–4 items.

## 5C. Feedback rules — `score_plate()`

When the student submits a plate, the server runs these rules against
the `log_categories` tags of every item on the plate. No numbers come
into the rule. All feedback strings below are **DRAFT** (the module
carries an explicit TODO for the nutrition team to replace them).

### Rules, in order

1. **Does the plate have a vegetable or fruit?**  
   `has_veg_or_fruit = any item has log_category in {"vegetables", "fruit"}`

2. **Does the plate have a whole grain?**  
   `has_whole_grain = any item has log_category "whole_grains"`

3. **Does the plate have a protein source?**  
   `has_protein = any item has log_category in {"beans_fish_nuts", "other_protein"}`

4. **Is any item salty/processed or added-sugar heavy?**  
   `less_healthy = any item has log_category in {"salty_processed", "added_sugars"}`

5. **"Balanced" is reserved for** vegetable-or-fruit AND whole-grain AND
   protein AND NO salty/processed/added-sugar item.

### Feedback texts — **DRAFT**

| # | When | Feedback text |
|---|---|---|
| 1 | Plate includes a salty/processed or added-sugar item | DRAFT — "Great mix, but *[item names]* leans salty/processed — a lighter side would round it out." |
| 2 | Plate is missing one or more of vegetable/fruit, whole grain, protein | DRAFT — "Good start — try adding *[a vegetable or fruit / a whole grain / a protein source]* to round this plate out." |
| 3 | Plate covers all three groups and has no salty/processed item | DRAFT — "That's a well-rounded plate — vegetable or fruit, whole grain, and a protein source, no salty extras." |

### Notes from the engineering side (for context — not for review)

- The code carries a TODO for the nutrition team to define the actual
  rubric, including: whether dairy and fruit should each have independent
  slots (they currently share the single "vegetable or fruit" slot), and
  whether salty/processed and added-sugar items should subtract from the
  score or only caution.
- There is a separate chat-review feature (not scored) that presents the
  plate to Claude via TAMU AI and asks for a plain-language review; its
  guardrails strip anything numeric before the student sees it.
