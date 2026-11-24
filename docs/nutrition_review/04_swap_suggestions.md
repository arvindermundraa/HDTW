# 4. Swap suggestions

**Source:** `backend/content/swaps.json` — the current swap list used
both by "From your meals" (in Future Me) and by the meal-logging
"Satvika swaps" table.

Context: A **swap** is a small, specific alternative the app can offer
a student in place of a food they already eat — "same breakfast, same
spot, just a different tub." Every swap belongs to one focus area, may
be tied to a slot (breakfast/lunch/dinner/snack/null = any), and carries
dining-hall keyword triggers so the swap only surfaces when a matching
item is actually on the menu.

Every entry in the current file is marked `reviewed: false` and is
therefore **DRAFT**. The nutrition team said on 2026-11-06 that they
will "review and expand the swap list from Satvika as soon as possible"
(Meal Logging and Future Me, Q1).

Total swaps today: **44**. Count by focus area:
- Fruit: 4
- Vegetables and beans: 6
- Grains: 7
- Dairy: 3
- Protein foods: 4
- Fats (saturated fat): 8
- Sodium: 5
- Added sugars: 7

## Swap record fields

Each swap has these fields (shown in the tables below):

1. **swap_label** — short label the student sees as the suggestion title.
2. **text** — the full suggestion body shown under the label.
3. **habit** — what the student currently does, that this swap replaces.
4. **slot** — meal slot this swap targets (`breakfast`, `lunch`, `dinner`,
   `snack`, or blank = any meal).
5. **needs** — equipment or constraint the student needs to make the
   swap (`none`, `stove`, `oven`, `microwave`, etc.).
6. **log_categories** — which of the 9 meal-log categories this swap
   counts toward.
7. **dining triggers** — keyword tuples that must appear in a dining-hall
   item name for the swap to surface in that hall (empty = no dining tie).
8. **source** — reference supporting the swap.

## Fruit — 4 swaps

### 1. Whole fruit in place of juice — **DRAFT**

- **id:** `fruit_juice`
- **habit:** `juice`  **slot:** breakfast  **needs:** none
- **log categories:** fruit
- **text (shown to the student):**

  > An orange, apple or banana where the juice usually goes. Whole fruit counts more than juice toward this focus area.

- **dining triggers:** orange; apple; banana; fresh fruit; grapefruit
- **dining excludes:** juice, chicken, pie, compote, cake, pudding, bread, muffin, bacon, pork, sausage, cobbler, crisp, tart, glazed, jam, jelly, butter
- **source:** Dietary Guidelines for Americans, 2020–2025, Chapter 1 (fruits); HEI-2020 whole fruits component (NCI/USDA)

### 2. Fruit for the sweet moment — **DRAFT**

- **id:** `fruit_candy_dessert`
- **habit:** `candy_dessert`  **slot:** any  **needs:** none
- **log categories:** fruit
- **text (shown to the student):**

  > Fruit at the moment you'd usually reach for a sweet. Berries, a banana or grapes, from the same fruit bar both halls keep out all day.

- **dining triggers:** fresh fruit; banana; apple; strawberries; blueberries; grapes; melon; pineapple
- **dining excludes:** pie, cake, compote, juice, chicken, cobbler, pudding, bread, muffin, bacon, pork, sausage, crisp, tart, glazed, jam, jelly, butter
- **source:** Dietary Guidelines for Americans, 2020–2025, Chapter 1 (fruits)

### 3. Berries or a banana on your yogurt — **DRAFT**

- **id:** `fruit_yogurt_or_cereal`
- **habit:** `yogurt`  **slot:** breakfast  **needs:** none
- **log categories:** fruit
- **text (shown to the student):**

  > Berries, a sliced banana or peach slices on the yogurt you already have. Same breakfast, plus fruit.

- **dining triggers:** strawberries; blueberries; blackberries; banana; peach; fresh fruit
- **dining excludes:** pie, compote, yogurt, cake, pudding, bread, muffin, bacon, chicken, pork, sausage, juice, cobbler, crisp, tart, glazed, jam, jelly, butter
- **source:** Dietary Guidelines for Americans, 2020–2025, Chapter 1 (fruits); USDA MyPlate, Fruit Group (myplate.gov)

### 4. A piece of fruit at breakfast — **DRAFT**

- **id:** `fruit_default_breakfast`
- **habit:** `—`  **slot:** breakfast  **needs:** none
- **log categories:** fruit
- **text (shown to the student):**

  > A banana, apple or orange with breakfast, or on the way to class. Both dining halls keep whole fruit out, and it needs no kitchen.

- **dining triggers:** banana; apple; orange; fresh fruit; grapefruit; strawberries
- **dining excludes:** juice, chicken, pie, compote, cake, pudding, bread, muffin, bacon, pork, sausage, cobbler, crisp, tart, glazed, jam, jelly, butter
- **source:** Dietary Guidelines for Americans, 2020–2025, Chapter 1 (fruits); USDA MyPlate, Fruit Group (myplate.gov)

## Vegetables and beans — 6 swaps

### 5. A side salad with the pizza — **DRAFT**

- **id:** `vegetables_beans_pizza`
- **habit:** `pizza`  **slot:** any  **needs:** none
- **log categories:** vegetables
- **text (shown to the student):**

  > A side salad from the salad bar next to the pizza, or the veggie slice. The pizza stays; the plate gains a vegetable.

- **dining triggers:** side salad; spring mix; romaine; veggie pizza; baby spinach
- **dining excludes:** egg salad, tuna salad, chicken salad, potato salad, pasta salad
- **source:** Dietary Guidelines for Americans, 2020–2025, Chapter 1 (vegetables); USDA MyPlate, Vegetable Group (myplate.gov)

### 6. Black beans on your rice bowl — **DRAFT**

- **id:** `vegetables_beans_white_rice`
- **habit:** `white_rice`  **slot:** any  **needs:** none
- **log categories:** beans_fish_nuts, vegetables
- **text (shown to the student):**

  > Black beans, chickpeas or edamame added to the rice bowl you already build. Beans count toward this focus area, and they're on the line most days.

- **dining triggers:** black beans; chick peas; chickpeas; kidney beans; edamame; garbanzo; cuban black beans
- **dining excludes:** green beans
- **source:** Dietary Guidelines for Americans, 2020–2025, Chapter 1 (vegetables; beans, peas and lentils); HEI-2020 greens and beans component

### 7. Spinach or broccoli stirred into the pasta — **DRAFT**

- **id:** `vegetables_beans_pasta`
- **habit:** `pasta`  **slot:** any  **needs:** none
- **log categories:** vegetables
- **text (shown to the student):**

  > A handful of spinach or broccoli stirred into the pasta you already make or build. Frozen works in a microwave; the pasta station keeps spinach and mushrooms out.

- **dining triggers:** baby spinach; spinach; broccoli; roasted vegetables; sliced mushrooms
- **dining excludes:** dip, artichoke dip
- **source:** Dietary Guidelines for Americans, 2020–2025, Chapter 1 (vegetables); USDA MyPlate, Vegetable Group (myplate.gov)

### 8. Lettuce, tomato and a side salad with the burger — **DRAFT**

- **id:** `vegetables_beans_burger`
- **habit:** `burger`  **slot:** any  **needs:** none
- **log categories:** vegetables
- **text (shown to the student):**

  > Load the burger with lettuce, tomato and onion, and add a side salad or green beans in place of one side. The burger stays.

- **dining triggers:** side salad; green beans; spring mix; romaine; sliced tomato; broccoli
- **dining excludes:** egg salad, tuna salad, chicken salad, potato salad, fried
- **source:** Dietary Guidelines for Americans, 2020–2025, Chapter 1 (vegetables); USDA MyPlate, Vegetable Group (myplate.gov)

### 9. Frozen vegetables in the ramen — **DRAFT**

- **id:** `vegetables_beans_instant_noodles`
- **habit:** `instant_noodles`  **slot:** any  **needs:** microwave
- **log categories:** vegetables
- **text (shown to the student):**

  > A handful of frozen vegetables or a few spinach leaves dropped into the noodles before they go in the microwave. Same meal, plus a vegetable.

- **dining triggers:** steamed + vegetables; baby spinach; broccoli; green beans; edamame
- **dining excludes:** fried
- **source:** Dietary Guidelines for Americans, 2020–2025, Chapter 1 (vegetables)

### 10. One vegetable at lunch — **DRAFT**

- **id:** `vegetables_beans_default_lunch`
- **habit:** `—`  **slot:** lunch  **needs:** none
- **log categories:** vegetables, beans_fish_nuts
- **text (shown to the student):**

  > One vegetable added to a lunch you already eat: a side salad, a vegetable from the hot line, or beans in a bowl. No kitchen needed on campus.

- **dining triggers:** side salad; spring mix; black beans; broccoli; green beans; roasted + vegetables; steamed + vegetables; baby spinach
- **dining excludes:** egg salad, tuna salad, chicken salad, potato salad, pasta salad, fried
- **source:** Dietary Guidelines for Americans, 2020–2025, Chapter 1 (vegetables); USDA MyPlate, Vegetable Group (myplate.gov)

## Grains — 7 swaps

### 11. Brown rice or quinoa — **DRAFT**

- **id:** `grains_white_rice`
- **habit:** `white_rice`  **slot:** any  **needs:** none
- **log categories:** whole_grains
- **text (shown to the student):**

  > Brown rice or quinoa as the base of the same bowl, whenever the line has it. Same toppings, different base.

- **dining triggers:** brown rice; wild rice; quinoa; farro; barley
- **source:** Dietary Guidelines for Americans, 2020–2025, Chapter 1 (grains); USDA MyPlate, Grains Group (myplate.gov)

### 12. Whole wheat or multigrain bread — **DRAFT**

- **id:** `grains_white_bread`
- **habit:** `white_bread`  **slot:** any  **needs:** none
- **log categories:** whole_grains
- **text (shown to the student):**

  > Whole wheat or multigrain bread for the same sandwich. The deli line keeps both next to the white bread.

- **dining triggers:** whole wheat; whole grain; multigrain; wheat bread; wheat bun; wheat tortilla
- **source:** Dietary Guidelines for Americans, 2020–2025, Chapter 1 (grains); USDA MyPlate, Grains Group (myplate.gov)

### 13. Whole wheat or chickpea pasta — **DRAFT**

- **id:** `grains_pasta`
- **habit:** `pasta`  **slot:** any  **needs:** stove
- **log categories:** whole_grains
- **text (shown to the student):**

  > Whole wheat or chickpea pasta with the same sauce. The box cooks the same way; the first ingredient on the label is the tell.

- **dining triggers:** whole wheat + pasta; whole grain + pasta; chickpea pasta
- **source:** Dietary Guidelines for Americans, 2020–2025, Chapter 1 (grains); FDA, How to Understand and Use the Nutrition Facts Label

### 14. Oatmeal or a whole-grain cereal — **DRAFT**

- **id:** `grains_cereal`
- **habit:** `cereal`  **slot:** breakfast  **needs:** none
- **log categories:** whole_grains
- **text (shown to the student):**

  > Oatmeal, or a cereal that lists a whole grain first on the box, in the same bowl at the same time. Microwave or hot-water oatmeal works with no kitchen at all.

- **dining triggers:** oatmeal; steel cut; oats
- **dining excludes:** cookie, granola
- **source:** Dietary Guidelines for Americans, 2020–2025, Chapter 1 (grains); USDA MyPlate, Grains Group (myplate.gov)

### 15. Microwave oatmeal or whole-grain noodle cups — **DRAFT**

- **id:** `grains_instant_noodles`
- **habit:** `instant_noodles`  **slot:** any  **needs:** none
- **log categories:** whole_grains
- **text (shown to the student):**

  > For the same hot, quick, no-kitchen meal: microwave oatmeal, or a noodle cup that lists whole wheat or brown rice first.

- **dining triggers:** oatmeal; brown rice; whole wheat
- **dining excludes:** cookie, granola
- **source:** Dietary Guidelines for Americans, 2020–2025, Chapter 1 (grains); FDA, How to Understand and Use the Nutrition Facts Label

### 16. Oatmeal at breakfast — **DRAFT**

- **id:** `grains_default_oatmeal`
- **habit:** `—`  **slot:** breakfast  **needs:** none
- **log categories:** whole_grains
- **text (shown to the student):**

  > Oatmeal is the easiest whole grain to add. Microwave or hot-water oatmeal needs no kitchen, and both dining halls serve it most mornings.

- **dining triggers:** oatmeal; steel cut; oats
- **dining excludes:** cookie, granola
- **source:** Dietary Guidelines for Americans, 2020–2025, Chapter 1 (grains); USDA MyPlate, Grains Group (myplate.gov)

### 17. Whole wheat bread at the deli line — **DRAFT**

- **id:** `grains_default_whole_wheat_bread`
- **habit:** `—`  **slot:** lunch  **needs:** none
- **log categories:** whole_grains
- **text (shown to the student):**

  > Ask for whole wheat or multigrain bread on your sandwich. Same sandwich, one small change.

- **dining triggers:** whole wheat; whole grain; multigrain
- **source:** Dietary Guidelines for Americans, 2020–2025, Chapter 1 (grains); USDA MyPlate, Grains Group (myplate.gov)

## Dairy — 3 swaps

### 18. A latte or milk-based coffee — **DRAFT**

- **id:** `dairy_sweet_coffee`
- **habit:** `sweet_coffee`  **slot:** any  **needs:** none
- **log categories:** dairy
- **text (shown to the student):**

  > Your coffee made as a latte, or with a real pour of milk. Milk-based coffee drinks count toward dairy; fortified soy milk counts too.

- **dining triggers:** milk; latte
- **dining excludes:** almond milk, oat milk, coconut milk, milkshake, cake, muffin, ice cream, cookie, rub, glaze, macaroni, mac, nacho, sauce, pizza, burger, sandwich, bread, sticks, dip, queso, pancake, pancakes, waffle, shake
- **source:** Dietary Guidelines for Americans, 2020–2025, Chapter 1 (dairy and fortified soy alternatives)

### 19. Milk on the cereal you already have — **DRAFT**

- **id:** `dairy_cereal`
- **habit:** `cereal`  **slot:** breakfast  **needs:** none
- **log categories:** dairy
- **text (shown to the student):**

  > Milk, or fortified soy milk, on the cereal you already have, or a yogurt next to it. Same breakfast, counts toward dairy.

- **dining triggers:** milk; yogurt; cottage cheese
- **dining excludes:** frozen, almond milk, oat milk, coconut milk, macaroni, mac, nacho, sauce, pizza, burger, sandwich, bread, sticks, dip, queso, pancake, pancakes, waffle, shake
- **source:** Dietary Guidelines for Americans, 2020–2025, Chapter 1 (dairy and fortified soy alternatives)

### 20. Yogurt or milk at breakfast — **DRAFT**

- **id:** `dairy_default_breakfast`
- **habit:** `—`  **slot:** breakfast  **needs:** none
- **log categories:** dairy
- **text (shown to the student):**

  > A yogurt or a glass of milk with breakfast. Both dining halls keep yogurt at the fruit bar, and a yogurt cup needs no kitchen.

- **dining triggers:** yogurt; milk; cottage cheese; cheese
- **dining excludes:** frozen, almond milk, oat milk, coconut milk, cheese sauce, mac and cheese, cheeseburger, cheese pizza, macaroni, mac, nacho, sauce, pizza, burger, sandwich, bread, sticks, dip, queso, pancake, pancakes, waffle, shake
- **source:** Dietary Guidelines for Americans, 2020–2025, Chapter 1 (dairy and fortified soy alternatives); USDA MyPlate, Dairy Group (myplate.gov)

## Protein foods — 4 swaps

### 21. A bean burger, tuna or grilled chicken — **DRAFT**

- **id:** `protein_foods_burger`
- **habit:** `burger`  **slot:** any  **needs:** none
- **log categories:** beans_fish_nuts, other_protein
- **text (shown to the student):**

  > A black bean or veggie burger, tuna salad or grilled chicken where the burger usually goes. This focus area is about more of your protein coming from seafood, beans and nuts.

- **dining triggers:** black bean burger; veggie burger; tuna; grilled chicken; salmon; hummus
- **dining excludes:** fried, crispy
- **source:** Dietary Guidelines for Americans, 2020–2025, Chapter 1 (protein foods; seafood and plant proteins); HEI-2020 seafood and plant proteins component

### 22. Beans, tofu or edamame on the rice bowl — **DRAFT**

- **id:** `protein_foods_white_rice`
- **habit:** `white_rice`  **slot:** any  **needs:** none
- **log categories:** beans_fish_nuts
- **text (shown to the student):**

  > Black beans, tofu or edamame added to the rice bowl you already build. Plant proteins count toward this focus area, and the bowl line keeps them out.

- **dining triggers:** black beans; tofu; edamame; chick peas; chickpeas; garbanzo; kidney beans
- **dining excludes:** green beans
- **source:** Dietary Guidelines for Americans, 2020–2025, Chapter 1 (protein foods; seafood and plant proteins)

### 23. Hummus, tuna or egg on the sandwich — **DRAFT**

- **id:** `protein_foods_white_bread`
- **habit:** `white_bread`  **slot:** lunch  **needs:** none
- **log categories:** beans_fish_nuts, other_protein
- **text (shown to the student):**

  > Hummus, tuna salad or egg on the sandwich you already make. The deli line keeps all three next to the deli meat.

- **dining triggers:** hummus; tuna; egg salad; eggs
- **dining excludes:** fried
- **source:** Dietary Guidelines for Americans, 2020–2025, Chapter 1 (protein foods; seafood and plant proteins)

### 24. Beans, nuts, eggs or fish with one meal — **DRAFT**

- **id:** `protein_foods_default`
- **habit:** `—`  **slot:** any  **needs:** none
- **log categories:** beans_fish_nuts, other_protein
- **text (shown to the student):**

  > Hummus, a handful of nuts, eggs, tuna or beans added to one meal a day. None of them need a kitchen, and the dining halls keep most of them out.

- **dining triggers:** hummus; tuna; black beans; chick peas; chickpeas; edamame; tofu; eggs; sunflower seeds; salmon
- **dining excludes:** fried, green beans
- **source:** Dietary Guidelines for Americans, 2020–2025, Chapter 1 (protein foods); USDA MyPlate, Protein Foods Group (myplate.gov)

## Fats (saturated fat) — 8 swaps

### 25. Low-fat or nonfat yogurt — **DRAFT**

- **id:** `fats_whole_milk_yogurt`
- **habit:** `whole_milk_yogurt`  **slot:** breakfast  **needs:** none
- **log categories:** dairy
- **text (shown to the student):**

  > Your usual yogurt, in a low-fat or nonfat version. Same breakfast, same spot, just a different tub.

- **dining triggers:** low fat + yogurt; lowfat + yogurt; nonfat + yogurt; non-fat + yogurt; skim + yogurt
- **dining excludes:** frozen
- **source:** Dietary Guidelines for Americans, 2020–2025, Chapter 1 (dairy; saturated fat); USDA MyPlate, Dairy Group (myplate.gov)

### 26. Low-fat or skim milk — **DRAFT**

- **id:** `fats_whole_milk`
- **habit:** `whole_milk`  **slot:** any  **needs:** none
- **log categories:** dairy
- **text (shown to the student):**

  > The milk you already drink, in a low-fat or skim version. Same cereal, same coffee.

- **dining triggers:** skim milk; low fat milk; lowfat milk; 1% milk; 2% milk; nonfat milk
- **source:** Dietary Guidelines for Americans, 2020–2025, Chapter 1 (dairy; saturated fat)

### 27. Chicken or turkey sausage — **DRAFT**

- **id:** `fats_bacon_sausage`
- **habit:** `bacon_sausage`  **slot:** breakfast  **needs:** none
- **log categories:** other_protein
- **text (shown to the student):**

  > Chicken or turkey sausage in place of pork sausage or bacon. The dining halls usually serve both side by side.

- **dining triggers:** chicken sausage; turkey sausage; turkey bacon
- **source:** Dietary Guidelines for Americans, 2020–2025, Chapter 1 (protein foods; saturated fat)

### 28. Grilled or roasted chicken — **DRAFT**

- **id:** `fats_fried_chicken`
- **habit:** `fried_chicken`  **slot:** any  **needs:** none
- **log categories:** other_protein
- **text (shown to the student):**

  > Grilled or roasted chicken in place of the fried kind. Same sauces, same sides.

- **dining triggers:** grilled chicken; roasted chicken; rotisserie; chicken thigh; baked chicken
- **dining excludes:** fried, crispy, tempura, tenders, nuggets, sandwich, wrap
- **source:** Dietary Guidelines for Americans, 2020–2025, Chapter 1 (saturated fat); USDA MyPlate, Protein Foods Group

### 29. Grilled chicken sandwich or veggie burger — **DRAFT**

- **id:** `fats_burger`
- **habit:** `burger`  **slot:** any  **needs:** none
- **log categories:** other_protein
- **text (shown to the student):**

  > A grilled chicken sandwich or a veggie burger from the same grill line, with the same toppings you like.

- **dining triggers:** grilled chicken + sandwich; veggie burger; turkey burger; black bean burger; grilled chicken
- **dining excludes:** fried, crispy, tempura
- **source:** Dietary Guidelines for Americans, 2020–2025, Chapter 1 (saturated fat); USDA MyPlate, Protein Foods Group

### 30. Baked potato or roasted sweet potato — **DRAFT**

- **id:** `fats_fries`
- **habit:** `fries`  **slot:** any  **needs:** none
- **log categories:** vegetables
- **text (shown to the student):**

  > A baked potato or roasted sweet potato on the side instead of fries. Both are usually at the grill or kitchen station.

- **dining triggers:** baked potato; baked sweet potato; roasted sweet potato; roasted potato; sweet potato
- **dining excludes:** fried, fries, chips
- **source:** Dietary Guidelines for Americans, 2020–2025, Chapter 1 (saturated fat; vegetables)

### 31. Red sauce in place of cheese sauce — **DRAFT**

- **id:** `fats_cheese_heavy`
- **habit:** `cheese_heavy`  **slot:** any  **needs:** none
- **log categories:** vegetables
- **text (shown to the student):**

  > Marinara or another red sauce on the pasta line in place of alfredo or queso. Same pasta, same station.

- **dining triggers:** marinara; red sauce; pomodoro; salsa; pico de gallo
- **source:** Dietary Guidelines for Americans, 2020–2025, Chapter 1 (saturated fat)

### 32. Nuts, seeds, hummus or an oil-based dressing — **DRAFT**

- **id:** `fats_default_nuts_oils`
- **habit:** `—`  **slot:** any  **needs:** none
- **log categories:** beans_fish_nuts
- **text (shown to the student):**

  > Add nuts or sunflower seeds to a salad, hummus to a sandwich, or an olive-oil dressing. Unsaturated fats, no cooking needed.

- **dining triggers:** sunflower seeds; hummus; almonds; walnuts; guacamole; avocado; italian dressing; vinaigrette
- **dining excludes:** ranch, caesar
- **source:** Dietary Guidelines for Americans, 2020–2025, Chapter 1 (oils; unsaturated fats)

## Sodium — 5 swaps

### 33. Fruit or unsalted nuts for the crunch — **DRAFT**

- **id:** `sodium_chips`
- **habit:** `chips`  **slot:** snack  **needs:** none
- **log categories:** fruit, beans_fish_nuts
- **text (shown to the student):**

  > An apple, grapes or a handful of unsalted nuts at the same snack time. The crunch stays.

- **dining triggers:** fresh fruit; apple; grapes; banana; unsalted
- **dining excludes:** pie, juice, chicken, compote, cake, pudding, bread, muffin, bacon, pork, sausage, cobbler, crisp, tart, glazed, jam, jelly, butter
- **source:** Dietary Guidelines for Americans, 2020–2025, Chapter 1 (sodium; snacks)

### 34. Noodles with low-sodium broth and vegetables — **DRAFT**

- **id:** `sodium_instant_noodles`
- **habit:** `instant_noodles`  **slot:** any  **needs:** microwave
- **log categories:** vegetables
- **text (shown to the student):**

  > The same noodles made with a low-sodium broth, plus frozen vegetables stirred in. A microwave is enough.

- **dining triggers:** low sodium; steamed + vegetables; green beans; broccoli
- **source:** Dietary Guidelines for Americans, 2020–2025, Chapter 1 (sodium); FDA, Sodium in Your Diet

### 35. Roasted chicken or eggs in place of cured meat — **DRAFT**

- **id:** `sodium_processed_meat`
- **habit:** `processed_meat`  **slot:** any  **needs:** none
- **log categories:** other_protein
- **text (shown to the student):**

  > Roasted or grilled chicken, or eggs, where you'd usually have pepperoni, hot dogs or deli ham. Same sandwich or plate, different protein.

- **dining triggers:** roasted chicken; grilled chicken; egg salad; eggs; chicken thigh
- **dining excludes:** fried, crispy, sausage
- **source:** Dietary Guidelines for Americans, 2020–2025, Chapter 1 (sodium; processed meats)

### 36. Grilled or roasted chicken — **DRAFT**

- **id:** `sodium_fried_chicken`
- **habit:** `fried_chicken`  **slot:** any  **needs:** none
- **log categories:** other_protein
- **text (shown to the student):**

  > Grilled or roasted chicken in place of breaded tenders or nuggets. The breading and the brine are where most of the salt lives.

- **dining triggers:** grilled chicken; roasted chicken; rotisserie; chicken thigh
- **dining excludes:** fried, crispy, tempura, tenders, nuggets, sandwich, wrap
- **source:** Dietary Guidelines for Americans, 2020–2025, Chapter 1 (sodium)

### 37. A fresh or steamed vegetable side — **DRAFT**

- **id:** `sodium_default_fresh_sides`
- **habit:** `—`  **slot:** any  **needs:** none
- **log categories:** vegetables
- **text (shown to the student):**

  > A steamed or roasted vegetable from the hot line, or a side salad, in place of a packaged or fried side. Most of the salt in a meal comes from the packaged parts.

- **dining triggers:** steamed + vegetables; roasted + vegetables; green beans; broccoli; roasted carrots; side salad; spring mix
- **dining excludes:** fried, pickled, pickle
- **source:** Dietary Guidelines for Americans, 2020–2025, Chapter 1 (sodium); FDA, Sodium in Your Diet

## Added sugars — 7 swaps

### 38. Sparkling water or water with fruit — **DRAFT**

- **id:** `added_sugars_soda`
- **habit:** `soda`  **slot:** any  **needs:** none
- **log categories:** —
- **text (shown to the student):**

  > Sparkling water, or water with a squeeze of lemon or a few berries, in place of the soda you'd usually grab. Same fizz, same cold can.

- **dining triggers:** sparkling water; lemon; lime; infused water
- **dining excludes:** lemonade, pie, cake, compote, pudding, bread, muffin, bacon, chicken, pork, sausage, juice, cobbler, crisp, tart, glazed, jam, jelly, butter, rice, pepper, bar, shrimp, fish, cilantro, dressing, vinaigrette
- **source:** Dietary Guidelines for Americans, 2020–2025, Chapter 1 (added sugars; beverages)

### 39. Coffee or tea, unsweetened — **DRAFT**

- **id:** `added_sugars_energy_drink`
- **habit:** `energy_drink`  **slot:** any  **needs:** none
- **log categories:** —
- **text (shown to the student):**

  > Plain coffee or tea for the same caffeine, with milk if you like it. Sugar-free versions of your usual drink count too.

- **dining triggers:** coffee; hot tea; iced tea; green tea
- **dining excludes:** sweet tea, frappe, mocha, cake, muffin, ice cream, cookie, rub, glaze
- **source:** Dietary Guidelines for Americans, 2020–2025, Chapter 1 (added sugars; beverages)

### 40. A latte with cinnamon or vanilla, no syrup — **DRAFT**

- **id:** `added_sugars_sweet_coffee`
- **habit:** `sweet_coffee`  **slot:** any  **needs:** none
- **log categories:** dairy
- **text (shown to the student):**

  > Your usual coffee order, made with milk and cinnamon or a vanilla sprinkle in place of the syrup. Same drink, same shop.

- **dining triggers:** coffee; latte
- **dining excludes:** frappe, mocha, caramel, cake, muffin, ice cream, cookie, rub, glaze
- **source:** Dietary Guidelines for Americans, 2020–2025, Chapter 1 (added sugars; beverages)

### 41. Plain yogurt with fruit — **DRAFT**

- **id:** `added_sugars_sweetened_yogurt`
- **habit:** `sweetened_yogurt`  **slot:** breakfast  **needs:** none
- **log categories:** dairy, fruit
- **text (shown to the student):**

  > Plain yogurt with real fruit on top in place of the flavored kind. Same breakfast, and you pick the fruit.

- **dining triggers:** plain + yogurt; greek yogurt; cottage cheese
- **dining excludes:** frozen, vanilla, strawberry, honey
- **source:** Dietary Guidelines for Americans, 2020–2025, Chapter 1 (added sugars; dairy)

### 42. Fruit for the sweet moment — **DRAFT**

- **id:** `added_sugars_candy_dessert`
- **habit:** `candy_dessert`  **slot:** any  **needs:** none
- **log categories:** fruit
- **text (shown to the student):**

  > Fruit at the same moment you'd usually reach for a sweet: a banana after class, berries after dinner. Both dining halls keep fruit out all day.

- **dining triggers:** fresh fruit; banana; apple; orange; strawberries; blueberries; grapes; melon; pineapple
- **dining excludes:** pie, cake, compote, juice, chicken, cobbler, crisp, pudding, bread, muffin, bacon, pork, sausage, tart, glazed, jam, jelly, butter
- **source:** Dietary Guidelines for Americans, 2020–2025, Chapter 1 (added sugars; fruits)

### 43. Whole fruit in place of juice — **DRAFT**

- **id:** `added_sugars_juice`
- **habit:** `juice`  **slot:** breakfast  **needs:** none
- **log categories:** fruit
- **text (shown to the student):**

  > An orange or an apple in place of the glass of juice. The fiber comes along, and it travels to class.

- **dining triggers:** orange; apple; banana; fresh fruit; grapefruit
- **dining excludes:** juice, chicken, pie, compote, cake, pudding, bread, muffin, bacon, pork, sausage, cobbler, crisp, tart, glazed, jam, jelly, butter
- **source:** Dietary Guidelines for Americans, 2020–2025, Chapter 1 (added sugars; whole fruit)

### 44. Water or sparkling water with meals — **DRAFT**

- **id:** `added_sugars_default_water_fruit`
- **habit:** `—`  **slot:** any  **needs:** none
- **log categories:** —
- **text (shown to the student):**

  > Water or sparkling water with one meal a day where you'd usually have a sweet drink. One meal is enough to start.

- **dining triggers:** sparkling water; infused water
- **source:** Dietary Guidelines for Americans, 2020–2025, Chapter 1 (added sugars; beverages)

## Where these swaps surface

1. **"From your meals"** (Future Me home + Coach): the rules engine picks
   a swap from this file that matches the student's focus area, is
   allowed by their equipment and allergies, and (when a hall menu is
   live) matches today's menu via the dining triggers above.
2. **Meal-logging swap table**: after a student logs a meal, the app may
   surface a matching swap from the same table, phrased as a next-time
   suggestion rather than a correction.
3. **The Coach**: the chat assistant may reference a swap id from this
   table when it suggests "tap Confirm to add it to your plan." Only swap
   ids from this file are accepted by the server; invented ones are
   silently dropped before the student sees them.
