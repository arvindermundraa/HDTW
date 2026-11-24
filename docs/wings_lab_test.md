# Wings — Lab Group Test (Tue, Oct 27, 1:45 PM)

A 20-minute, 5–6 person live test of the redesigned Wings screen on
<https://llhs.vercel.app>. Everyone uses their own phone (or laptop) at the
same time; we want to see group behaviour (cheer counters updating in near
real time, challenge progress adding up) with real network variance, not a
local-only run.

## Prep (facilitator, before the session)

1. Confirm the backend is deployed from `main` and the Wings endpoints
   respond — a browser hit to `/api/wings/mine/summary` with any signed-in
   session should return `{wing: null | {...}, cheer_presets: [...]}`.
2. Message everyone the day before: *"On Tuesday, sign up on
   <https://llhs.vercel.app> with your TAMU email before 1:40 PM. You'll
   need the 6-digit verification code from your inbox."*
3. By 1:40 PM, open the staff page (`/research-admin`), scroll to
   **5. Lab Test Wing**, and paste each tester's TAMU email in turn. The
   first add creates the "Lab Test Wing" and prints its join code.
   Flipping `is_test_account=true` is automatic — confirm the "test flag"
   column shows **yes** for each row.
4. Share the join code in the group chat so anyone who signs up late can
   join themselves from the app (**Wings → Join a Wing**).

**Never touch `llhs_db` from Claude Code or any ad-hoc script.** The
staff page writes to whichever DB the deployed backend is pointing at;
that's the only path that should mutate production.

## What testers do (20 minutes)

Each tester has the Wings tab open on their phone the whole time.

1. **Sign in** on `llhs.vercel.app` using the TAMU email they signed up with.
2. **Open the Wings tab.** They should see the Lab Test Wing card:
   name, member count, join code, shared progress bar, cheers row, and
   this week's challenge card below.
3. **Log something — any ring.** Go to Today, open the Eat / Move /
   Sleep flow, log one small entry (e.g. a 10-minute walk).
4. **Switch back to Wings.** Within ~15 seconds the Wing's shared
   progress should move. (Not instant — the screen polls every 15s;
   pull-to-refresh for instant.)
5. **Tap each cheer** (`Nice work, Wing`, `Keep going`, `Proud of us`).
   The totals update immediately for the tapper (optimistic). On every
   other phone they should move within the next poll.
6. **Check the challenge card.** It should show *this week's* challenge
   and the Wing's combined count, same for every tester.
7. **Hit "Send feedback"** at the bottom. Fill in what you were doing +
   what happened + a 1–5 rating. Send. ("Send feedback" only appears
   when `is_test_account=true` — if a tester doesn't see it, their flag
   didn't flip; add them from the staff page again.)
8. **Share a meal (photos, new in Phase 2).** Scroll on the Wings tab
   to the **Share a meal** button (visible only to lab-test accounts
   while `WINGS_PHOTOS_MODE=test_only`). Then:
   - Tap **Share a meal** → a sheet opens. Expand the **Posting guide**
     and read it once: *"Share food, not faces. No other people, names,
     ID cards or locations in the photo. Keep captions kind and about
     the food."*
   - **Pick a photo** of a food item (JPG / PNG / HEIC, under 5 MB).
     The server strips every EXIF tag including GPS automatically.
   - **Caption** (up to 200 characters) — try something plain, then try
     a blocked one on purpose ("about 500 calories", or an email) and
     notice the friendly error.
   - Optional: add up to 5 short **How I made it** steps.
   - Optional: pick a **focus area** tag (defaults to your own focus).
   - Tap **Share**. The post appears in your **My recent posts** strip
     with "**Waiting for approval**".
   - Try a 4th post in the same study day — the server returns a
     friendly 429 and the attempt counter stays correct.
9. **Watch for approval.** Within ~15 s of the facilitator tapping
   **Approve** on the staff page, the chip flips to "**Shared with
   your Wing**" and the post appears in the **Wing kitchen** feed
   below for every other tester in the Wing.
10. **React to a Wing-mate's post.** Tap each preset reaction (`Looks
    delicious`, `Want to try this`, `Great swap`, `So colourful`). Your
    tap bumps immediately; counts never show who tapped.
11. **Report a post.** Tap **Report** on any feed card — the post
    drops out of the feed for everyone instantly and shows up in the
    staff Moderation tab with a `reported` chip for re-review.

## Facilitator: moderating photo posts live

Keep the staff page's **Moderation** tab open on a laptop next to you.
The tab auto-refreshes every 15 seconds; the heading badge (e.g.
*"3 to review"*) shows the queue size at a glance.

For each pending post:
1. Glance at the image, caption and steps on the right of the card.
2. Check filter chips. A post marked **not auto-checked** just means
   the cloud image moderator isn't wired yet — the file-type / size /
   EXIF-strip / caption filters already ran, and your human eye is the
   final check. **Approve every post explicitly** — the auto layer
   never approves on its own.
3. Click **Approve** (post appears in the Wing feed) or pick a reject
   reason from the dropdown and click **Reject** (image deleted, poster
   sees "Not shared" + the preset reason). For something previously
   approved that was reported, click **Remove**.
4. Record anything odd in the **Test feedback** tab, or jot the
   session note next to the tester's email.

If the auto-refresh gets noisy on your Wi-Fi, uncheck
"Auto-refresh (15 s)" and use **Refresh now** as needed. The tab
pauses automatically when it's hidden in another browser tab.

## 5-minute live-site smoke check (facilitator, right after merge/redeploy)

Do this on <https://llhs.vercel.app> **before** telling the testers to log
in. Takes ~5 min and catches the three regressions this prep PR is
guarding against. All actions use a `@example.com` or already-flagged
test account; nothing writes to real-participant data.

1. **Vercel env sanity.** On the project's Deployments → latest, confirm
   `BLOB_READ_WRITE_TOKEN`, `WINGS_PHOTOS_MODE=test_only` are present
   (and `WINGS_PHOTOS_IRB_CONFIRMED` is **unset**). In Logs, grep for
   `photo storage:` — should read `blob`, not `memory` or `unavailable`.
2. **Lab Test Wing bar can move.** As a test account, open **Wings**:
   the shared bar should say `0 / 6 balanced meals` (not the old
   `0 / 10 days`). On Today, log a quick meal with 2+ categories (e.g.
   "Rice bowl with greens") → within ~15 s the bar on Wings bumps to
   `1 / 6`.
3. **Post a photo from an iPhone.** On an iPhone's Safari, hit the
   Wings tab → **Share a meal** → pick a photo from the camera roll
   (HEIC default). Caption "Lab test photo", **Share** → chip shows
   "**Waiting for approval**" immediately.
4. **Post a photo from a laptop.** On your laptop (another test
   account), same flow with a JPG or PNG.
5. **Approve both.** Open `/research-admin` → section 7 **Moderation**.
   Both posts show up with the pending-count badge; images render
   (the HEIC one as a JPEG after the server re-encode). Click
   **Approve** on each.
6. **Second-device check.** On a third phone/laptop (another test
   account in the Lab Test Wing), reload Wings → both posts are in
   the **Wing kitchen** feed. Tap a reaction → the count bumps.
7. **Send feedback.** On the test account, hit **Send feedback**;
   write one line, send; confirm it appears in `/research-admin` →
   **Test feedback** within 15 s.

If any of 1–6 fails, roll back the merge (or flip `WINGS_PHOTOS_MODE=off`
in Vercel for item 3+) before 1:45 PM. Step 7 is non-blocking.

## Group debrief (5 min)

Ask, in order:

1. **Could you tell what your Wing was doing together?** Did the group
   progress feel real?
2. **Did the cheers feel good to tap?** Did you look at the counts?
3. **Did anything spin forever, or get stuck?** Any dead buttons?
4. **One thing you'd change on this screen?**
5. **Any wording that felt off** — pushy, judgy, confusing?

Jot down what each person says next to their email in the staff
**Test feedback** tab. Export the CSV at the end.

## After the test

1. Staff page → **Test feedback** → **Download CSV**. Keep it with the
   session notes.
2. Leave the test accounts flagged `is_test_account=true` forever —
   late-arriving logs still get filtered out of research exports.
3. If anyone wants their account repurposed as a real participant later,
   flip the flag off from **1. Participants**.

## Photo data: retention and privacy

Wing photo posts are **app content**, not research data. The following
rules are enforced by code; this section documents them so the team can
answer PI/IRB questions without reading the server:

- **Research exports never include photos or captions.** The HEI scores
  export has always excluded test accounts; the new
  `/research/wing-posts/engagement.csv` adds non-content engagement
  counts (posts shared, pending, rejected, reactions received) and
  excludes `is_test_account` users by the same rule. No image bytes or
  captions ever leave the server through a staff export route.
- **Rejected posts: image deleted immediately.** When staff pick a
  reject reason, the Vercel-Blob (or dev-memory) object is dropped as
  part of the same request. The DB row stays with `status="rejected"`
  so the poster still sees the preset reason, but there's nothing to
  serve.
- **Removed posts (previously approved): image deleted.** Same rule.
  The row stays for engagement-count honesty; the bytes do not.
- **Posts deleted by their author: image deleted.** The row flips to
  `status="removed_by_poster"` with `image_key=null`.
- **Reported posts: hidden from the feed until staff re-review.** No
  deletion — staff can either approve again (clearing `reported`) or
  remove the post entirely.
- **Account deletion** cascades: any post with that `user_id` is
  deleted along with its image via the same storage adapter.
- **Blob URLs never reach the browser.** Every image render uses
  `/api/wings/posts/{id}/image` (or
  `/api/research/moderation/{id}/image` for staff), both of which do a
  per-request Wing-membership / staff auth check and stream bytes
  through the backend.

## If the live site breaks mid-test

- Direct everyone to pull-to-refresh. If that doesn't help, close the tab
  and reopen. Nothing they've done is lost — logs and cheers both post
  from the server, not the browser cache.
- If the backend is unreachable, say so and keep testers busy with the
  Learn tab (or send everyone back to class with a note that you'll
  reschedule). We never fabricate successful posts.

## Local rehearsal (facilitator only, same day earlier)

Before the 1:45 live session, run the 2-minute load check locally against
`llhs_ui_compare` to confirm nothing regressed on your laptop stack:

```bash
# Start the stack if it isn't already:
docker start llhs-mongo
cd backend && source venv/bin/activate && \
  DB_NAME=llhs_ui_compare RATE_LIMIT_ENABLED=false \
  CORS_ALLOWED_ORIGINS="http://localhost:3001,http://127.0.0.1:3001" \
  uvicorn server:app --port 8001 &
cd ../frontend && npx expo start --web --port 3001 &

# Sign up 6 demo accounts in llhs_ui_compare (one time), make one wing,
# share its join code, then:
cd ../backend && LOAD_CHECK_DB_NAME=llhs_ui_compare \
  python scripts/wings_load_check.py \
  --accounts lab1@example.com:...,lab2@example.com:...,...  \
  --wing-code ABC123 \
  --duration 120
```

Target: 0 errors, p95 latency < 500 ms on
`GET /wings/mine/summary` and `POST /wings/cheer`.

If the load check fails, fix it before the live session — the live site
is public and we don't want testers' first impression to be a hang.
