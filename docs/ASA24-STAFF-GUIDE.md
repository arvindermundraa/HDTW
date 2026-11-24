# ASA24 → LLHS: staff guide

How to get participants' ASA24 recalls scored and into the app. ASA24 has no API and
its site may not be scraped, so staff download one file per recall window; the app
does the HEI-2020 scoring.

You need: the LLHS research page (`<backend URL>/research-admin`) and a
**researcher account** (email + password). Ask a research admin to add you from the
page's *Researcher accounts* section; the very first admin is created on the server
with `python manage_researchers.py add <email> --admin`. Sessions last 8 hours.
(The shared `RESEARCH_API_KEY` under *Use shared key instead* is only for scripts —
don't share it.)

## Once per participant: link their ASA24 username

1. In the ASA24 Researcher website, create the participant's respondent account as usual. Note the **ASA24 username**.
2. Open the LLHS research page → **Sign in**.
3. Under **Participants & ASA24 usernames**, pick the participant (they must already have signed up in the app), type their ASA24 username, **Save link**.

Usernames aren't case-sensitive. One username = one participant; the page refuses a
username that's already linked to someone else. Use **Unlink** to fix a mistake.

## After each recall window (baseline, check-in 1–4)

1. **Wait until both recalls are complete.** The study design is 2 recalls per assessment point.
2. **Export** from the ASA24 Researcher website: the daily **"Totals"** analysis file (NCI calls it "Daily Total Nutrient and Pyramid Equivalents"), as **CSV**. Not the per-food Items file — the page will say so if you pick the wrong one.
3. On the LLHS research page, **Upload ASA24 Totals CSV**: choose the file and the **assessment point**, then **Preview**.
4. **Check the preview.** Nothing is saved yet.

   | Status | Meaning | What to do |
   |---|---|---|
   | **ready** | Linked participant, can be imported | Import (ticked by default) |
   | **unmatched** | Username in the file isn't linked to anyone | Link it first, then preview again — or ignore if not an LLHS participant |
   | **exists** | Already scored for this assessment point | Leave it, or tick **Replace existing scores** if this file is the corrected one |
   | **not selected** | You unticked it | — |

   Warnings to review before importing: *not 2 recalls*, *duplicate RecallNo* (same recall exported twice), *energy outside 500–5000 kcal* (possible incomplete or mis-entered recall).
5. Untick anyone you don't want imported → **Import selected**. Participants see updated Food feedback and focus areas the next time they open the app.

## How the score is calculated

The app uses a direct Python port of NCI's official **HEI-2020 SAS macro (v1.0, Dec 2024)**
with NCI's **per-person** method: each participant's recalls in the file are **added
together, then scored once** (not an average of two daily scores). Source:
<https://epi.grants.cancer.gov/hei/sas-code.html>. Each import also stores the summed
inputs, so any score can be re-checked in SAS or R (`dietaryindex`) later.

Participants never see the numbers — only direction-based guidance.

## If something goes wrong

- **"This doesn't look like an ASA24 'Totals' file — missing column(s)…"** — wrong file, or an ASA24 version with renamed columns. Send the message (not the file) to the dev team.
- **"Line N: KCAL is not a number"** — the CSV was edited or re-saved oddly; re-export from ASA24 rather than fixing it by hand.
- **401 / "Invalid or expired researcher session"** — sign in again (sessions last 8 hours). If your account was disabled, ask a research admin.
- **Test accounts:** tick *Test account* next to QA/demo participants so they don't count in cohort numbers.
