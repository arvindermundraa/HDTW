# 8. TAMU Dining data source — plain-language explanation and draft permission request

The nutrition team asked on 2026-11-06 whether permission from TAMU Dining
is needed, and asked for more details about the source we use (Week 2
content, Q2). This document explains the source in plain language and
drafts a permission request the team could send.

## 1. Where the menu data comes from

The app's dining-hall menus come from the same backing service that powers
the public "What's on the Menu" pages on the TAMU Dining website
(**dineoncampus.com/tamu**). When a student opens one of those pages in
a browser, the browser calls a public web service and the page fills in
with today's menu for the dining hall and meal period selected. The app
reads from that same web service — not from a private or official TAMU
Dining API, and not by scraping the HTML of the page.

The web service is run by a third-party company called **DineOnCampus**
(part of Compass Group), which contracts with campuses — including TAMU —
to publish their menus online. There is **no official LLHS integration or
agreement with TAMU Dining**. Access is through the same public endpoint
the website itself uses.

## 2. What the app reads

For each of the two dining halls (Sbisa Dining Hall and The Commons
Dining Hall) and each of the three meal periods (breakfast, lunch, dinner),
the app reads a single list of what the hall is serving today. For every
dish on that list, the app keeps:

1. The dish **name** (e.g. "Grilled Chicken Breast").
2. The **station** the dish is served at (e.g. "Comfort", "Greens &
   Grains").
3. The dish's **portion** description, if the feed includes one.
4. A short **description** of the dish, if the feed includes one.
5. The **ingredients** list (as a plain sentence), which the app uses
   privately for allergy matching.
6. **Qualitative labels** attached to the dish — things like allergens
   (Egg, Milk, Wheat, Soy, Sesame) and diet markers (Vegan, Vegetarian).

## 3. What the app deliberately does NOT read or store

1. **Calorie counts** — even when the public feed includes a calorie number
   for a dish, the app strips that number out at the moment the data arrives
   and never stores or shows it.
2. **Nutrient values** (sodium, fat, protein, carbohydrate, fiber, etc.) —
   same treatment as calories: stripped at the source. The only numbers the
   app shows to students in Week 2 come from a separate reviewed sample
   list of grocery products and from a separate reviewed dining-menu sample
   used for the scenario labels, not from the public TAMU Dining feed.
3. The dish's photo, nutrition-label image or any PDF attachment.
4. Any personally identifying information (the public feed does not include
   student data of any kind).

## 4. How often the app reads it

The app reads the menu **per-request and per-day**. When a student opens
the dining-hall screen for a hall and meal period, the app makes one
request to the public service for that hall and that meal period on that
date. There is no background crawl of the whole TAMU Dining site, no
scheduled refresh outside of a student's interaction with the app, and no
automated collection of multiple days ahead or in the past.

If the request to the public service fails for any reason (service down,
network issue, a day when a hall publishes no menu at all), the app falls
back to a small built-in sample menu instead, so a student's experience
is never blocked.

## 5. What the app stores

The app does **not** store the menu as its own historical record. The
response from the public service is used in-memory to render the dining
screen for that student in that moment, and a short-lived server cache is
used so that repeated requests on the same day for the same hall and meal
period do not re-hit the public service unnecessarily. The cache is cleared
the next day.

The app does store, per student, which menu items they themselves have
logged as part of a meal (e.g. "I had the grilled chicken sandwich at
Sbisa for lunch"). That record is tied to the student, not to the dining
hall, and is saved in the student's own meal log.

## 6. Draft permission request — for the team to send

The team can send the following draft to TAMU Dining (University Dining
Services, a unit of University Services at Texas A&M). Please edit before
sending — this is a starting point, not an approved request.

---

**Subject:** Permission request — read-only use of DineOnCampus menu data
for LLHS, a TAMU student nutrition app in development

Dear TAMU Dining team,

I'm writing from the Digital Twin Lab at Texas A&M, on behalf of the
Live Long, Heart Strong (LLHS) student nutrition app project
(IRB approval in progress). We're building a mobile app to support
heart-healthy eating habits among TAMU undergraduates aged 18–25, and I'd
like to confirm your comfort with how we read from the public TAMU Dining
menu data.

What the app does: when a student opens the dining-hall screen, we fetch
today's menu for a single hall (Sbisa or The Commons) and meal period
(breakfast, lunch or dinner) from the same public **dineoncampus.com/tamu**
endpoint that your "What's on the Menu" pages already use. We read the
dish name, station, portion, description, ingredients and allergen/diet
labels. **We do not read or store calorie or nutrient values** — those are
stripped from the response at the moment it arrives — and **we do not show
numerical nutrient information to students for dining-hall items**. We do
not crawl the site in bulk, and we do not keep a copy of the menu beyond
a short in-memory cache that is cleared each day.

What we would like to confirm with you:

1. Whether you consider this read-only use of the public menu feed to be
   within the intended public use of the DineOnCampus service, or whether
   it would require a specific agreement with TAMU Dining or with
   DineOnCampus.
2. Whether you would like us to display a "menu data courtesy of TAMU
   Dining / dineoncampus.com" credit in the app.
3. Whether there are days or meal periods when a specific dining hall
   does not want its menu rendered outside of the official site.

We're happy to meet to walk through the app and show exactly how the data
is used, and to share the app's internal design note on this (which we've
attached in plain language). Our goal is a transparent, read-only
integration that supports your students without putting any additional
load on your systems.

Thank you for your time, and please let us know how you'd like to proceed.

Best regards,  
*[Nutrition team member name]*  
*[Role, LLHS project]*  
*[Email]*

---

## 7. For the engineering side (not for the team to review)

Technical pointers in case the team is asked a specific question:

- The backend endpoint we call is `https://apiv4.dineoncampus.com`. It is
  the same JSON web service that `dineoncampus.com/tamu` uses behind the
  scenes.
- The verified TAMU location ids: Commons `59972586ee596fe55d2eef75`, Sbisa
  `587909deee596f31cedc179c` (stable). Period ids change per day and are
  always fetched fresh.
- The scraper module is `backend/dining_scraper.py`; it strips `calories`
  and `nutrients` at parse time (`_NEVER_KEEP = ("calories", "nutrients")`)
  before any value is persisted or sent to the frontend.
- A scrape failure returns `None` and the server falls back to the built-in
  sample menus so a student's meal log is never blocked.
