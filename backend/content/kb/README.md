# Coach knowledge base

The Coach (the Q&A helper, not Future Me) answers **only** from these entries. It searches them for each question (BM25 in `backend/coach_kb.py`), answers in plain words, and names the entry it used ("From: Whole grains basics"). If nothing relevant is found, it says it doesn't have that information and suggests asking the study team.

## Files
Each `*.json` file in this folder is a list of entries. All files are loaded at server start.

| Field | Meaning |
|---|---|
| `id` | Unique, lowercase with underscores (e.g. `whole_grains`). Never reuse an id. |
| `title` | Short name shown to students as the citation ("From: …"). |
| `topic` | `food_group`, `curriculum`, `college`, `move`, `sleep` or `safety`. |
| `hei_component` | The HEI-2020 component id this covers, or `null`. |
| `curriculum_area` | `planning`, `applying`, `assembling`, or `null`. |
| `tags` | Extra search words students might use (e.g. "brown rice", "dining hall"). Optional but helpful. |
| `text` | The content: 2–4 plain sentences. |
| `source` | The citation (e.g. "Dietary Guidelines for Americans, 2020–2025, Chapter 1"). Required. |
| `reviewed` | `false` until the nutrition team approves the entry, then `true`. |

## Writing rules (the app's guardrails enforce these)
- No calories, grams, milligrams, % Daily Value numbers or scores like "4/10". A reply that contains them is blocked.
- No restriction or weight language ("cut back", "eat less", "lose weight", "guilt-free", "lighter option"). Frame everything as what to add or swap.
- No "good food / bad food" labels and no medical advice.

## How the nutrition team adds or edits an entry
1. Edit the JSON (or add a new file in this folder) following the fields above.
2. Keep `reviewed: false` for drafts; set it to `true` once the team approves.
3. Run the tests: `cd backend && python -m pytest tests/test_coach_kb.py -n 0`. They check every entry has the required fields and a source, that ids are unique, and that sample questions find the right entries. If you add a common question, add it to the sample list in the test.
4. Restart the backend to load the change.

All entries in this folder are **drafts** written from the Dietary Guidelines for Americans 2020–2025, USDA MyPlate, the HEI-2020 documentation, the FDA Nutrition Facts guidance, the Physical Activity Guidelines and CDC sleep guidance, and need review.
