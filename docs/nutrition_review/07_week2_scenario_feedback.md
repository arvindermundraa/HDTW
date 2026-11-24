# 7. Week 2 scenario feedback — DRAFT copy for the team to replace

**Source:** `backend/content/weeks/week2.json`, step `scenarios.scenario_defs`,
sub-objects `restaurant`, `someone_else`, and `home`.

Context: Week 2's "Practice with real choices" step asks the student to run
through three settings. Two of those settings — cafeteria and grocery —
generate feedback from the student's actual nutrient comparison (rule-based,
no scripted copy). The other three — **restaurant**, **a meal someone else
prepares**, and **at home** — are scripted: three choices per scenario, each
choice followed by a short feedback paragraph.

The nutrition team said on 2026-11-06 that they will provide approved
scripts (Content of app, Q5). Every row below is **DRAFT** — please replace
the feedback text and send it back. Choice text is what the student sees
when choosing; please leave the choice column alone unless you want to
rewrite the choice itself, in which case flag that too.

## 7A. Scenario: Restaurant or takeout

**Prompt the student sees:** *You're out for dinner with friends and ordering
from the menu. Which would you go for?*

**Follow-up after the feedback:** *Which menu word did you notice first?*
Options: Grilled, Roasted, Steamed, Crispy.

| # | Choice (text shown to student) | Current DRAFT feedback | Approved replacement (team to fill) |
|---|---|---|---|
| 1 | Grilled chicken sandwich with fries | DRAFT — Grilled is a useful menu clue: it usually means less added fat than fried or crispy. The fries are the sodium and saturated-fat side of this choice, so a swap or share is worth asking about. One ask that often works: 'Can I get a side salad or fruit instead of fries?' | |
| 2 | Roasted salmon with steamed vegetables and rice | DRAFT — Roasted, steamed, and salmon are all strong menu clues: unsaturated fats from the fish, cooking methods without added fat, and vegetables you can see on the plate. If the rice is white, you could ask whether brown rice is available. | |
| 3 | Crispy chicken wrap with a side salad | DRAFT — Crispy on a menu usually means fried, which adds saturated fat and sometimes sodium. The side salad is a strong move for fiber and vegetables. If you want to lean further into the wrap, ask whether grilled chicken is available instead of crispy. | |

## 7B. Scenario: A meal someone else prepares

**Prompt the student sees:** *You're at a family dinner, or a friend's place,
and the food is set out. You're filling your plate.*

No follow-up question on this scenario.

| # | Choice (text shown to student) | Current DRAFT feedback | Approved replacement (team to fill) |
|---|---|---|---|
| 1 | Fried chicken and mac and cheese | DRAFT — These are familiar comfort foods. If this is what's on the table, you can enjoy it and still keep your goal in play — a smaller spoon of the mac, or saving room for whatever vegetable is in reach. There's no need to swap out foods that matter to the people you're with. | |
| 2 | Grilled chicken, rice and beans, and a salad | DRAFT — Lots to work with: a lean protein, beans for fiber, a vegetable side. Rice and beans together are a classic combination that stretches both into something more filling. If dressing is on the salad, asking for it on the side is an easy ask when you can. | |
| 3 | A little of everything, with seconds on the vegetables | DRAFT — A plate that samples what's served honors the host and still leaves room for your goal — the "seconds on vegetables" move is a quietly strong one and nobody has to notice. You get to enjoy the meal and still support what you're working on. | |

## 7C. Scenario: At home

**Prompt the student sees:** *You're making dinner at home with a can of
beans, rice, and some vegetables. You have about 20 minutes.*

No follow-up question on this scenario.

| # | Choice (text shown to student) | Current DRAFT feedback | Approved replacement (team to fill) |
|---|---|---|---|
| 1 | Beans straight from the can with the liquid, over white rice | DRAFT — Fast and filling. The canned bean liquid usually carries a lot of sodium — a quick rinse in a colander takes about 30 seconds and makes a real difference without changing the meal. White rice works; whole-grain brown rice would add more fiber if you have it on hand next time. | |
| 2 | Rinsed beans with vegetables and brown rice | DRAFT — Strong move. Rinsing the beans cuts a chunk of the sodium, the vegetables add fiber and bulk, and brown rice brings whole grains into the plate. This is a weeknight staple worth having in rotation. | |
| 3 | Beans and vegetables with cheese, over white rice | DRAFT — The vegetables and beans are a strong foundation. Cheese adds flavor and some saturated fat; a smaller handful goes a long way when it's melted on top. If you reach for brown rice next time, you'll also pick up more fiber. | |

## How to send replacements back

The engineering team can drop the approved text directly into
`backend/content/weeks/week2.json` under each scenario's `choices[*].feedback`
field, and flip `draft_feedback: true` to `false`. You can either edit the
right-hand column of the tables above and send the file back, or paste a
new version of each feedback paragraph in an email referenced by its row
number (e.g. "7A #2: *…new text…*").
