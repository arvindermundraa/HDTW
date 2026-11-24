# 3. Future Me knowledge base

**Source:** `backend/content/kb/` — three files that together form the
entire knowledge base the Future Me / Coach chat may draw from.

Context: Every answer from Future Me / the Coach must cite one of these
entries (the LLM is told to append `SOURCE: <id>`, and the server strips
that line before showing the answer, but the id becomes the citation
shown under the answer). Entries without a review-approved source are
marked **DRAFT** (`reviewed: false` in the file).

The team asked where to find this list (Meal Logging and Future Me, Q3).

The "question" column below is phrased from the student's perspective
and reflects the kind of question each entry is meant to answer — the
actual entries store a `title` + `text`, which is what the KB retrieval
matches on.

## General guidelines (dietary reference values + scope)

*File: `backend/content/kb/general_guidelines.json` — 9 entries.*

### 1. Daily sodium guideline **DRAFT**

- **Entry id:** `guideline_sodium`
- **Topic:** guideline  **HEI component:** sodium  **Curriculum area:** —
- **Tags (matched in student questions):** sodium, salt, mg, daily value, blood pressure, cut back on salt, lower sodium, reduce sodium
- **Question this entry is meant to answer:** Daily sodium guideline
- **Answer (as stored in the KB and used verbatim in LLM prompts):**

  > Most adults should aim for less than 2,300 mg of sodium a day — about one teaspoon of salt total from all food and drink combined, not just what you add. On packaged food labels, 5% Daily Value (DV) or less per serving is a 'low' amount of sodium and 20% DV or more is 'high'. Most sodium in a typical U.S. diet comes from packaged, restaurant, and dining-hall foods rather than the salt shaker — the practical move is to compare labels at the store and ask for sauce or dressing on the side when eating out.

- **Source:** FDA Nutrition Facts label education; Dietary Guidelines for Americans, 2020–2025 (sodium)

### 2. Daily fiber guideline **DRAFT**

- **Entry id:** `guideline_fiber`
- **Topic:** guideline  **HEI component:** fiber  **Curriculum area:** —
- **Tags (matched in student questions):** fiber, fibre, whole grains, beans, lentils, how much fiber, daily value, dv
- **Question this entry is meant to answer:** Daily fiber guideline
- **Answer (as stored in the KB and used verbatim in LLM prompts):**

  > The FDA Daily Value for fiber is 28 grams per day. Most college-aged adults get about half that. Easy ways to close the gap: a cup of oats or a slice of 100% whole-grain bread at breakfast (about 4–5 g each), a cup of beans or lentils with a meal (about 7–10 g), a piece of fruit for a snack (2–4 g), and vegetables at lunch and dinner.

- **Source:** FDA Nutrition Facts label (Daily Values); Dietary Guidelines for Americans, 2020–2025

### 3. Daily fruit and vegetable guideline **DRAFT**

- **Entry id:** `guideline_fruit_vegetables`
- **Topic:** guideline  **HEI component:** total_fruits  **Curriculum area:** —
- **Tags (matched in student questions):** fruit, fruits, vegetables, veggies, produce, cups, how much fruit, how many vegetables
- **Question this entry is meant to answer:** Daily fruit and vegetable guideline
- **Answer (as stored in the KB and used verbatim in LLM prompts):**

  > The Dietary Guidelines for Americans suggest about 2 cups of fruit and 2½ cups of vegetables per day for most college-aged adults — slightly more or less depending on activity level. Whole fruit counts fully; 100% juice counts once (about 1 cup max). Dark leafy greens, red/orange vegetables, and beans/peas are the ones that most people fall short on. Frozen and canned (rinsed) count — fresh isn't a requirement.

- **Source:** Dietary Guidelines for Americans, 2020–2025, Chapter 1 and MyPlate

### 4. Daily whole grain guideline **DRAFT**

- **Entry id:** `guideline_whole_grains`
- **Topic:** guideline  **HEI component:** whole_grains  **Curriculum area:** —
- **Tags (matched in student questions):** whole grains, grain, brown rice, quinoa, oats, whole wheat bread, half your grains
- **Question this entry is meant to answer:** Daily whole grain guideline
- **Answer (as stored in the KB and used verbatim in LLM prompts):**

  > The Dietary Guidelines recommend making at least HALF of your grains whole. On packaged food labels, look for 'whole wheat' or 'whole grain' as the first ingredient — not just 'wheat flour' or 'enriched flour'. In a dining hall, swapping white rice for brown rice, or white bread for 100% whole-wheat, is the single easiest move.

- **Source:** Dietary Guidelines for Americans, 2020–2025, Chapter 1 and MyPlate (grains)

### 5. Daily added sugars guideline **DRAFT**

- **Entry id:** `guideline_added_sugars`
- **Topic:** guideline  **HEI component:** added_sugars  **Curriculum area:** —
- **Tags (matched in student questions):** added sugars, sugar, sugary drinks, soda, daily value, dv, how much sugar
- **Question this entry is meant to answer:** Daily added sugars guideline
- **Answer (as stored in the KB and used verbatim in LLM prompts):**

  > Most adults should keep added sugars to less than 10% of daily calories, which the FDA sets as about 50 g (12 teaspoons) per day on Nutrition Facts labels. The biggest source for most college-aged adults is sugar-sweetened drinks (soda, sweet tea, flavored coffees, energy drinks, specialty lattes). A 12 oz can of regular soda has about 39 g — close to a full day's worth in one drink. On labels, look for 10% DV or less for added sugars per serving.

- **Source:** FDA Nutrition Facts label (added sugars); Dietary Guidelines for Americans, 2020–2025

### 6. Daily saturated fat guideline **DRAFT**

- **Entry id:** `guideline_saturated_fat`
- **Topic:** guideline  **HEI component:** saturated_fats  **Curriculum area:** —
- **Tags (matched in student questions):** saturated fat, fat, butter, cheese, fatty meat, cholesterol, heart health
- **Question this entry is meant to answer:** Daily saturated fat guideline
- **Answer (as stored in the KB and used verbatim in LLM prompts):**

  > Keep saturated fat to less than 10% of daily calories — the FDA Daily Value is 20 g per day on Nutrition Facts labels. Big sources: fatty meats, butter, full-fat cheese and ice cream, and most fried fast food. Swaps that stack up: fish or beans in place of a fatty meat a couple of nights a week; olive oil in place of butter when cooking; a thinner layer of cheese on sandwiches.

- **Source:** FDA Nutrition Facts label (saturated fat); Dietary Guidelines for Americans, 2020–2025

### 7. How to read a Nutrition Facts label in 15 seconds **DRAFT**

- **Entry id:** `guideline_label_reading`
- **Topic:** guideline  **HEI component:** —  **Curriculum area:** applying
- **Tags (matched in student questions):** label, nutrition facts, serving size, percent daily value, dv, sodium, compare labels
- **Question this entry is meant to answer:** How to read a Nutrition Facts label in 15 seconds
- **Answer (as stored in the KB and used verbatim in LLM prompts):**

  > A fast way to read any Nutrition Facts label: (1) Serving size first — the whole package often holds 2 or 3 servings. (2) Scan 'Added sugars', 'Saturated fat', and 'Sodium' — 5% Daily Value or less is 'low', 20% DV or more is 'high'. (3) Scan 'Fiber' — 20% DV or more per serving is 'high' and generally helpful. When comparing two products, lower sat fat, lower sodium, lower added sugars, and higher fiber per serving are the four to watch.

- **Source:** FDA Nutrition Facts label education

### 8. Calorie-counting and weight questions in LLHS **DRAFT**

- **Entry id:** `guideline_calorie_topic`
- **Topic:** scope  **HEI component:** —  **Curriculum area:** —
- **Tags (matched in student questions):** calories, calorie counting, weight loss, weight, lose weight, diet
- **Question this entry is meant to answer:** Calorie-counting and weight questions in LLHS
- **Answer (as stored in the KB and used verbatim in LLM prompts):**

  > LLHS is a habit-based program — not something that works with calorie counts or body-size targets. If a student asks about calorie amounts or body-size change, respond with a short, supportive sentence that reframes toward the habit (what to add, build, swap, or try), and suggest reaching out to the study team or a dietitian for the specifics.

- **Source:** LLHS study team guidance (October 2026)

### 9. When the planned food option isn't available **DRAFT**

- **Entry id:** `guideline_plan_option_unavailable`
- **Topic:** coping  **HEI component:** —  **Curriculum area:** —
- **Tags (matched in student questions):** plan unavailable, not available, sold out, backup, fallback, what if
- **Question this entry is meant to answer:** When the planned food option isn't available
- **Answer (as stored in the KB and used verbatim in LLM prompts):**

  > If the option in your plan isn't available, pick the closest thing on offer — a better choice still counts even when it's not the one you wrote down. The three usual swaps: (1) if a whole-grain option is missing, pick the dish with vegetables or beans on it instead; (2) if a fish entrée is missing, grab beans or a lean grilled option; (3) if a lower-sodium side is missing, add a piece of fruit or a side salad to balance a saltier main. Save the actual plan for the next day it IS available.

- **Source:** LLHS coping strategies (based on Week 2 planning spec)

## HEI-2020 components (food groups covered by the app)

*File: `backend/content/kb/hei_components.json` — 13 entries.*

### 10. Fruits basics **DRAFT**

- **Entry id:** `total_fruits`
- **Topic:** food_group  **HEI component:** total_fruits  **Curriculum area:** —
- **Tags (matched in student questions):** fruit, fruits, juice, berries, apple, banana, snack
- **Question this entry is meant to answer:** Fruits basics
- **Answer (as stored in the KB and used verbatim in LLM prompts):**

  > Fruit counts whether it's fresh, frozen, canned or dried. The Dietary Guidelines suggest most young adults make room for more fruit across the day. Easy adds: a banana or apple on the way to class, berries on oatmeal or yogurt, or fruit from the dining hall as a side.

- **Source:** Dietary Guidelines for Americans, 2020–2025, Chapter 1 (fruits); USDA MyPlate, Fruit Group (myplate.gov)

### 11. Whole fruit vs. juice **DRAFT**

- **Entry id:** `whole_fruits`
- **Topic:** food_group  **HEI component:** whole_fruits  **Curriculum area:** —
- **Tags (matched in student questions):** whole fruit, juice, fiber, fibre, smoothie, fruit
- **Question this entry is meant to answer:** Whole fruit vs. juice
- **Answer (as stored in the KB and used verbatim in LLM prompts):**

  > Whole fruit (fresh, frozen, canned or dried, not juice) keeps the fiber that juice loses. The Dietary Guidelines recommend that most of the fruit you have be whole fruit. If you like juice, pairing it with a piece of whole fruit is an easy swap.

- **Source:** Dietary Guidelines for Americans, 2020–2025, Chapter 1 (fruits); HEI-2020 component definitions (NCI/USDA)

### 12. Vegetables basics **DRAFT**

- **Entry id:** `total_vegetables`
- **Topic:** food_group  **HEI component:** total_vegetables  **Curriculum area:** —
- **Tags (matched in student questions):** vegetable, vegetables, veggies, salad, side, frozen
- **Question this entry is meant to answer:** Vegetables basics
- **Answer (as stored in the KB and used verbatim in LLM prompts):**

  > All vegetables count: fresh, frozen or canned, raw or cooked. Most young adults have fewer vegetables than the Dietary Guidelines recommend. A simple habit is adding one vegetable to a meal you already eat, like a side salad, roasted vegetables from the hot line, or frozen vegetables stirred into pasta or rice.

- **Source:** Dietary Guidelines for Americans, 2020–2025, Chapter 1 (vegetables); USDA MyPlate, Vegetable Group (myplate.gov)

### 13. Greens and beans **DRAFT**

- **Entry id:** `greens_beans`
- **Topic:** food_group  **HEI component:** greens_beans  **Curriculum area:** —
- **Tags (matched in student questions):** greens, beans, legumes, lentils, spinach, kale, chickpeas, dark green
- **Question this entry is meant to answer:** Greens and beans
- **Answer (as stored in the KB and used verbatim in LLM prompts):**

  > This HEI component covers dark-green vegetables (like spinach, broccoli, kale and romaine) and beans, peas and lentils. Easy adds: spinach in a wrap or omelet, black beans in a burrito bowl, chickpeas on a salad, or lentil soup. Canned beans count, and rinsing them is a quick habit.

- **Source:** HEI-2020 component definitions (NCI/USDA); Dietary Guidelines for Americans, 2020–2025, vegetable subgroups

### 14. Whole grains basics **DRAFT**

- **Entry id:** `whole_grains`
- **Topic:** food_group  **HEI component:** whole_grains  **Curriculum area:** —
- **Tags (matched in student questions):** whole grain, whole grains, brown rice, oats, oatmeal, whole wheat, quinoa, bread, grain
- **Question this entry is meant to answer:** Whole grains basics
- **Answer (as stored in the KB and used verbatim in LLM prompts):**

  > Whole grains keep all parts of the grain kernel. Brown rice, oats and oatmeal, quinoa, popcorn, whole-wheat bread and whole-wheat pasta are all whole grains. The Dietary Guidelines suggest making at least half your grains whole. On a label, look for "whole" as the first word in the ingredient list, like "whole wheat flour".

- **Source:** Dietary Guidelines for Americans, 2020–2025, Chapter 1 (grains); USDA MyPlate, Grains Group (myplate.gov)

### 15. Dairy and fortified soy **DRAFT**

- **Entry id:** `dairy`
- **Topic:** food_group  **HEI component:** dairy  **Curriculum area:** —
- **Tags (matched in student questions):** dairy, milk, yogurt, cheese, soy milk, calcium, lactose
- **Question this entry is meant to answer:** Dairy and fortified soy
- **Answer (as stored in the KB and used verbatim in LLM prompts):**

  > The dairy group includes milk, yogurt, cheese and fortified soy milk or soy yogurt. Lactose-free milk and fortified soy alternatives count too. Easy adds: yogurt with fruit at breakfast, milk with cereal, or a soy latte.

- **Source:** Dietary Guidelines for Americans, 2020–2025, Chapter 1 (dairy); USDA MyPlate, Dairy Group (myplate.gov)

### 16. Protein foods **DRAFT**

- **Entry id:** `total_protein_foods`
- **Topic:** food_group  **HEI component:** total_protein_foods  **Curriculum area:** —
- **Tags (matched in student questions):** protein, meat, chicken, eggs, tofu, beans, nuts, fish
- **Question this entry is meant to answer:** Protein foods
- **Answer (as stored in the KB and used verbatim in LLM prompts):**

  > Protein foods include meat, poultry, eggs, seafood, beans, peas, lentils, nuts, seeds and soy products like tofu. Variety matters more than any single choice. Pairing each meal with a protein you enjoy helps meals feel satisfying.

- **Source:** Dietary Guidelines for Americans, 2020–2025, Chapter 1 (protein foods); USDA MyPlate, Protein Foods Group (myplate.gov)

### 17. Seafood and plant proteins **DRAFT**

- **Entry id:** `seafood_plant_proteins`
- **Topic:** food_group  **HEI component:** seafood_plant_proteins  **Curriculum area:** —
- **Tags (matched in student questions):** seafood, fish, salmon, tuna, nuts, seeds, beans, tofu, plant protein, peanut butter
- **Question this entry is meant to answer:** Seafood and plant proteins
- **Answer (as stored in the KB and used verbatim in LLM prompts):**

  > This HEI component counts seafood plus plant proteins: beans, peas, lentils, nuts, seeds and soy. The Dietary Guidelines encourage seafood a couple of times a week and plant proteins often. Easy ideas: a tuna or salmon sandwich, peanut butter on whole-grain toast, edamame, or a bean chili.

- **Source:** HEI-2020 component definitions (NCI/USDA); Dietary Guidelines for Americans, 2020–2025, protein subgroups

### 18. Healthy fats (fatty acids) **DRAFT**

- **Entry id:** `fatty_acids`
- **Topic:** food_group  **HEI component:** fatty_acids  **Curriculum area:** —
- **Tags (matched in student questions):** fat, fats, healthy fats, olive oil, avocado, nuts, oil, butter, fatty acids
- **Question this entry is meant to answer:** Healthy fats (fatty acids)
- **Answer (as stored in the KB and used verbatim in LLM prompts):**

  > The Fatty Acids component looks at the balance of unsaturated fats (from foods like nuts, seeds, avocado, fish and oils such as olive or canola) compared with saturated fats. Choosing oils in place of butter now and then, or adding nuts or avocado, shifts that balance in a heart-healthy direction.

- **Source:** HEI-2020 component definitions (NCI/USDA); Dietary Guidelines for Americans, 2020–2025, Chapter 1 (oils)

### 19. Refined grains and swaps **DRAFT**

- **Entry id:** `refined_grains`
- **Topic:** food_group  **HEI component:** refined_grains  **Curriculum area:** —
- **Tags (matched in student questions):** refined grains, white bread, white rice, pasta, tortilla, crackers, swap
- **Question this entry is meant to answer:** Refined grains and swaps
- **Answer (as stored in the KB and used verbatim in LLM prompts):**

  > Refined grains (like white bread, white rice and many crackers and tortillas) have had part of the kernel removed. They still fit in meals. A simple habit is swapping one refined grain for a whole grain when it's easy, like brown rice at the grain bar or a whole-wheat wrap.

- **Source:** Dietary Guidelines for Americans, 2020–2025, Chapter 1 (grains); HEI-2020 component definitions (NCI/USDA)

### 20. Sodium and salt **DRAFT**

- **Entry id:** `sodium`
- **Topic:** food_group  **HEI component:** sodium  **Curriculum area:** —
- **Tags (matched in student questions):** sodium, salt, salty, chips, soup, processed, seasoning, blood pressure
- **Question this entry is meant to answer:** Sodium and salt
- **Answer (as stored in the KB and used verbatim in LLM prompts):**

  > Most sodium comes from packaged and restaurant foods rather than the salt shaker. Heart-healthy swaps: flavor food with herbs, spices, lemon or salsa; choose fresh or frozen vegetables; rinse canned beans; and try a fruit or unsalted nuts as a snack in place of chips now and then. Small swaps add up.

- **Source:** Dietary Guidelines for Americans, 2020–2025, Chapter 1 (sodium); HEI-2020 component definitions (NCI/USDA)

### 21. Added sugars **DRAFT**

- **Entry id:** `added_sugars`
- **Topic:** food_group  **HEI component:** added_sugars  **Curriculum area:** —
- **Tags (matched in student questions):** sugar, added sugars, soda, sweet, dessert, energy drink, candy, drinks
- **Question this entry is meant to answer:** Added sugars
- **Answer (as stored in the KB and used verbatim in LLM prompts):**

  > Added sugars are sugars put into foods and drinks during processing or preparation; the sugar naturally in fruit and milk isn't counted. Sweetened drinks are the biggest source for many young adults. Easy swaps: water or sparkling water alongside a sweet drink, unsweetened tea, or fruit for something sweet.

- **Source:** Dietary Guidelines for Americans, 2020–2025, Chapter 1 (added sugars); HEI-2020 component definitions (NCI/USDA)

### 22. Saturated fats **DRAFT**

- **Entry id:** `saturated_fats`
- **Topic:** food_group  **HEI component:** saturated_fats  **Curriculum area:** —
- **Tags (matched in student questions):** saturated fat, saturated, butter, cheese, fried, bacon, pizza, fat
- **Question this entry is meant to answer:** Saturated fats
- **Answer (as stored in the KB and used verbatim in LLM prompts):**

  > Saturated fat is found in foods like butter, cheese, fatty and processed meats, and many fried and baked foods. Heart-healthy swaps: grilled in place of fried now and then, olive or canola oil in place of butter, and beans or chicken as a pizza or taco topping.

- **Source:** Dietary Guidelines for Americans, 2020–2025, Chapter 1 (saturated fat); HEI-2020 component definitions (NCI/USDA)

## Curriculum & college life (planning, applying, assembling)

*File: `backend/content/kb/curriculum_and_college.json` — 12 entries.*

### 23. Planning for healthy eating **DRAFT**

- **Entry id:** `planning_healthy_eating`
- **Topic:** curriculum  **HEI component:** —  **Curriculum area:** planning
- **Tags (matched in student questions):** plan, planning, week, schedule, busy, prep, meal prep, time
- **Question this entry is meant to answer:** Planning for healthy eating
- **Answer (as stored in the KB and used verbatim in LLM prompts):**

  > Planning ahead makes healthy eating easier on a busy schedule. Look at your week, note which meals happen on campus and which at home, and keep a few easy staples on hand (frozen vegetables, oats, canned beans, eggs, fruit). Batch-cooking one grain and one protein can cover several meals.

- **Source:** Dietary Guidelines for Americans, 2020–2025, Chapter 3 (young adults); USDA MyPlate, Plan Healthy Meals (myplate.gov)

### 24. Reading nutrition labels **DRAFT**

- **Entry id:** `applying_nutrition_information`
- **Topic:** curriculum  **HEI component:** —  **Curriculum area:** applying
- **Tags (matched in student questions):** label, labels, nutrition facts, ingredients, daily value, dv, read, package
- **Question this entry is meant to answer:** Reading nutrition labels
- **Answer (as stored in the KB and used verbatim in LLM prompts):**

  > On a Nutrition Facts label, start with the serving size, then use the percent Daily Value column to see whether a food has a little or a lot of a nutrient. Check the ingredient list too: ingredients are listed from most to least, so "whole wheat" first means a whole grain is the main ingredient.

- **Source:** U.S. Food and Drug Administration, How to Understand and Use the Nutrition Facts Label (fda.gov)

### 25. Building a balanced plate **DRAFT**

- **Entry id:** `assembling_balanced_meals`
- **Topic:** curriculum  **HEI component:** —  **Curriculum area:** assembling
- **Tags (matched in student questions):** balanced, plate, myplate, meal, half, build, assemble
- **Question this entry is meant to answer:** Building a balanced plate
- **Answer (as stored in the KB and used verbatim in LLM prompts):**

  > MyPlate is a flexible guide: fill about half your plate with vegetables and fruit, about a quarter with grains (ideally whole), and about a quarter with protein, plus dairy or fortified soy on the side. It's a pattern to aim for across the day, not a rule for every plate.

- **Source:** USDA MyPlate (myplate.gov); Dietary Guidelines for Americans, 2020–2025, Chapter 1

### 26. Eating well in the dining hall **DRAFT**

- **Entry id:** `dining_hall_tips`
- **Topic:** college  **HEI component:** —  **Curriculum area:** assembling
- **Tags (matched in student questions):** dining hall, dining, sbisa, commons, buffet, campus, cafeteria, lunch, dinner
- **Question this entry is meant to answer:** Eating well in the dining hall
- **Answer (as stored in the KB and used verbatim in LLM prompts):**

  > In the dining hall, take a lap before you choose. Start with the salad bar or a vegetable side, pick a protein from the hot line, and add a whole grain from the grain bar if there's one. Fruit makes an easy side or dessert. The Build a Meal screen in this app uses today's real menu.

- **Source:** USDA MyPlate, Eating Away From Home (myplate.gov); Dietary Guidelines for Americans, 2020–2025

### 27. Making the most of a meal plan **DRAFT**

- **Entry id:** `meal_plan_tips`
- **Topic:** college  **HEI component:** —  **Curriculum area:** planning
- **Tags (matched in student questions):** meal plan, swipes, dining dollars, campus, budget
- **Question this entry is meant to answer:** Making the most of a meal plan
- **Answer (as stored in the KB and used verbatim in LLM prompts):**

  > With a meal plan, think about which meals you'll eat on campus each day and use those for your most balanced meals. Grab a piece of fruit or a yogurt on the way out for a later snack. On days you're off campus, a few staples at home fill the gaps.

- **Source:** USDA MyPlate, Plan Healthy Meals (myplate.gov); Dietary Guidelines for Americans, 2020–2025, Chapter 3

### 28. Cheap healthy swaps **DRAFT**

- **Entry id:** `budget_swaps`
- **Topic:** college  **HEI component:** —  **Curriculum area:** planning
- **Tags (matched in student questions):** cheap, budget, money, affordable, grocery, frozen, canned, save
- **Question this entry is meant to answer:** Cheap healthy swaps
- **Answer (as stored in the KB and used verbatim in LLM prompts):**

  > Eating well on a budget: frozen and canned vegetables and fruit are as nutritious as fresh and last longer; dry or canned beans, oats, brown rice, eggs and peanut butter are low-cost staples; and store brands work just as well. Buying what you'll use this week saves money.

- **Source:** USDA MyPlate, Healthy Eating on a Budget (myplate.gov); Dietary Guidelines for Americans, 2020–2025

### 29. Easy high-fibre breakfasts **DRAFT**

- **Entry id:** `high_fiber_breakfast`
- **Topic:** college  **HEI component:** whole_grains  **Curriculum area:** assembling
- **Tags (matched in student questions):** breakfast, fiber, fibre, high fiber, high fibre, oatmeal, cereal, morning
- **Question this entry is meant to answer:** Easy high-fibre breakfasts
- **Answer (as stored in the KB and used verbatim in LLM prompts):**

  > Fibre-rich breakfasts combine a whole grain with fruit or nuts: oatmeal with berries, whole-grain toast with peanut butter and banana, a whole-grain cereal with milk and fruit, or yogurt with fruit and a sprinkle of granola. Most dining halls have oatmeal and fruit at breakfast.

- **Source:** Dietary Guidelines for Americans, 2020–2025, Chapter 1 (dietary fiber, grains); USDA MyPlate (myplate.gov)

### 30. Snacks between classes **DRAFT**

- **Entry id:** `snacks_between_classes`
- **Topic:** college  **HEI component:** —  **Curriculum area:** planning
- **Tags (matched in student questions):** snack, snacks, between classes, hungry, backpack, study
- **Question this entry is meant to answer:** Snacks between classes
- **Answer (as stored in the KB and used verbatim in LLM prompts):**

  > Snacks can add food groups to your day. Easy backpack options: fruit, a handful of nuts, trail mix, whole-grain crackers with peanut butter, or yogurt. Pairing a fruit or vegetable with a protein helps a snack keep you going.

- **Source:** USDA MyPlate, Snacks (myplate.gov); Dietary Guidelines for Americans, 2020–2025

### 31. Ordering when you eat out **DRAFT**

- **Entry id:** `eating_out`
- **Topic:** college  **HEI component:** —  **Curriculum area:** applying
- **Tags (matched in student questions):** restaurant, fast food, eating out, order, menu, takeout
- **Question this entry is meant to answer:** Ordering when you eat out
- **Answer (as stored in the KB and used verbatim in LLM prompts):**

  > When eating out, look for a vegetable you can add (a side salad, veggies on a bowl or sandwich), choose grilled or baked options sometimes, and ask for sauces on the side so you choose how much. Water or unsweetened drinks are an easy default.

- **Source:** USDA MyPlate, Eating Away From Home (myplate.gov); Dietary Guidelines for Americans, 2020–2025

### 32. Physical activity basics **DRAFT**

- **Entry id:** `move_guideline`
- **Topic:** move  **HEI component:** —  **Curriculum area:** —
- **Tags (matched in student questions):** activity, exercise, move, walk, workout, steps, minutes
- **Question this entry is meant to answer:** Physical activity basics
- **Answer (as stored in the KB and used verbatim in LLM prompts):**

  > The Physical Activity Guidelines for Americans suggest adults aim for about 150 minutes of moderate activity a week, plus muscle-strengthening activity on two days. Any movement counts: walking to class, taking stairs, a bike ride, or a pickup game. Consistency matters more than intensity.

- **Source:** U.S. Department of Health and Human Services, Physical Activity Guidelines for Americans, 2nd edition (health.gov)

### 33. Sleep basics **DRAFT**

- **Entry id:** `sleep_basics`
- **Topic:** sleep  **HEI component:** —  **Curriculum area:** —
- **Tags (matched in student questions):** sleep, rest, tired, bedtime, hours, nap
- **Question this entry is meant to answer:** Sleep basics
- **Answer (as stored in the KB and used verbatim in LLM prompts):**

  > Most adults do best with 7 or more hours of sleep a night. A regular bedtime and wake time, a wind-down routine, and keeping screens out of bed are simple habits that help. Sleep reference values in this app are still being finalised by the study team.

- **Source:** Centers for Disease Control and Prevention, Sleep and Sleep Disorders: How Much Sleep Do I Need? (cdc.gov)

### 34. Getting support **DRAFT**

- **Entry id:** `support_resources`
- **Topic:** safety  **HEI component:** —  **Curriculum area:** —
- **Tags (matched in student questions):** stress, guilt, restrict, struggle, anxious, binge, help, support
- **Question this entry is meant to answer:** Getting support
- **Answer (as stored in the KB and used verbatim in LLM prompts):**

  > If eating ever feels stressful or restrictive, be gentle with yourself. LLHS is about building habits, never about weight or restriction. Talking with someone you trust, the study team, or campus counseling and health services can help.

- **Source:** LLHS study protocol (safety and support guidance)

## Follow-up — FDA Daily Values Future Me may cite when relevant

Per the nutrition team's 2026-11-06 follow-up (October 29 feedback, item
1), Future Me may cite the following FDA Daily Values when relevant. The
corresponding KB entries above already carry these numbers in their
`text`. Calories are deliberately excluded.

1. **Sodium:** less than 2,300 mg/day — covered in entry `guideline_sodium`.
2. **Saturated fat:** less than 20 g/day — covered in entry `guideline_saturated_fat`.
3. **Added sugars:** less than 50 g/day — covered in entry `guideline_added_sugars`.
4. **Dietary fiber:** at least 28 g/day — covered in entry `guideline_fiber`.

These are presented as general reference values based on a 2,000-calorie
diet, not individualized targets. Participants' own dietary intake and
HEI-2020 scores are never displayed numerically.
