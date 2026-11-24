# Week 2 User Workflow and Educational Content Integration (team spec)

1.  **Week 2 Overview**

Week 2 builds on the dietary focus area and behavioral goal established
during Week 1 by helping participants recognize opportunities to make
heart-healthy food choices in the environments where they regularly eat.
The central objective is to move participants from understanding their
dietary goals to identifying and selecting foods that support those
goals within real-world eating situations. The educational content
introduces practical food-selection strategies, including interpreting
Nutrition Facts labels, recognizing relevant information on menus, and
comparing available food options. Participants apply these skills
through interactive scenarios, observe a Youth Ambassador demonstrating
a goal-supportive choice, and update their existing action plan to
identify an upcoming opportunity to apply what they learned.

Week 2 should function as a connected learning experience in which
educational content prepares participants for guided practice, guided
practice informs action planning, and the resulting plan is incorporated
into the app's ongoing behavior-change features.

**Week 2 participant journey:**

1.  Watch the Week 2 overview video, including the nutrition label
    education.

2.  Select and complete at least three of five interactive food-choice
    scenarios.

3.  Watch a Youth Ambassador modeling video demonstrating a
    goal-supportive food choice.

4.  Complete the interactive activity, "Planning Where You'll Use It."

5.  Review the updated "This Week" card containing the participant's
    active goal, planned action, and reminder.

6.  Apply the selected action in everyday eating situations, supported
    by available LLHS app features.

The estimated duration of the structured Week 2 activities is
approximately 20 minutes.

2.  **Step 1: Week 2 Overview Video**

**App location:** Today screen → Week 2 educational content

**Educational content:** Week 2 Overview Video — Know What to Look For

**Purpose:** Teach participants how to recognize and compare food
choices that support their selected dietary focus area across common
eating environments. The overview video builds on the Week 1 focus-area
education by moving from understanding dietary recommendations to
identifying practical cues for selecting foods. The central message is
"Look for the clue before you choose."

The video begins by introducing the importance of examining nutrition
information, including the contribution of packaged and commercially
prepared foods to sodium intake. A relatable scenario involving a
student named Jordan demonstrates how the Nutrition Facts label can help
compare food choices. Participants are introduced to a label-reading
process that emphasizes checking the serving size, identifying relevant
nutrient information, interpreting percent Daily Values, and comparing
similar products. The video highlights saturated fat, sodium, added
sugars, and dietary fiber as useful nutrients to examine, while
explaining that the information most relevant to a decision may depend
on the participant's nutrition focus.

The video then provides practical examples across all eight LLHS dietary
focus areas: Fruit, Vegetables and Beans, Grains, Dairy, Protein Foods,
Fats, Sodium, and Added Sugars. These examples demonstrate how
participants can recognize goal-supportive choices in dining halls,
restaurants and takeout settings, grocery and convenience stores, meals
prepared by others, and foods prepared at home. The final scenes
emphasize that participants do not need to find a perfect food choice.
Instead, they can identify useful information and select an option that
supports their goals within the circumstances and foods available to
them.

**Required app functionality:**

- Display the Week 2 overview video within the Today screen.

- Maintain the participant's previously selected nutrition focus area
  throughout the Week 2 experience.

- Provide the video with standard playback controls and available
  captions.

- Allow participants to revisit the video and its educational content.

- Provide a clear transition from the overview video to the interactive
  scenario activities.

- Record video completion according to the established LLHS
  activity-tracking procedures.

**Integration requirement:** The overview video should directly prepare
participants for the interactive scenarios by introducing the
food-selection cues and nutrition-label skills they will practice. The
scenarios should reinforce the concepts demonstrated in the video rather
than introduce unrelated decision-making tasks.

3.  **Step 2: Interactive Scenario Activities**

**App location:** Today screen → Week 2 Scenario Activities

**Educational content:** LLHS Week 2 Scenario Activities

**Purpose:** Provide participants with opportunities to practice
identifying and selecting food choices that support their dietary goals
in realistic eating environments, with immediate feedback. The activity
consists of five scenarios representing common eating situations.
Participants select three settings that are relevant to their own lives
and complete one scenario in each selected setting. Each scenario
presents a brief situation, three food options, and a prompt asking
participants to make a selection. Feedback appears immediately after the
participant chooses an option.The emphasis is on understanding the
nutritional features and trade-offs associated with each choice. Options
should not be labeled as wrong or bad.

**3.1 Scenario Selection**

**Display text:**

"Choose three places or situations where you actually eat."

Participants choose three settings from the following options:

- Cafeteria or dining hall

- Restaurant or takeout

- Grocery or convenience store

- A meal someone else prepares

- At home

**Required app functionality:**

- Display the five available eating environments.

- Allow participants to select three settings.

- Present the corresponding scenario for each selected setting.

- Track the number of completed scenarios.

- After three scenarios are completed, provide a "Try another" option
  for participants who wish to practice in additional settings.

- Save participant selections and activity completion status.

**Integration requirement:** Participants should be able to choose
settings relevant to their everyday eating experiences. The selected
settings should determine which scenarios appear, rather than requiring
every participant to complete the same three scenarios.

**3.2 Scenario 1 — Cafeteria or Dining Hall**

This scenario teaches participants to compare nutrition information
across food choices using real dining hall menu information. Unlike
packaged Nutrition Facts labels, dining hall nutrition information may
report nutrient amounts without percent Daily Values. Participants
therefore practice comparing the same nutrient information across
multiple food options.

**Example display text:**

"You're grabbing \[breakfast/lunch/dinner\] at \[dining hall\]. Here are
three options. Let's take a look at their labels and pick one."

The participant sees three menu items, with nutrition information
displayed for each. Saturated fat, sodium, and dietary fiber are
highlighted.

**Required app functionality:**

- Retrieve current dining hall menu information for the relevant dining
  location and meal period.

- Select three eligible main menu items.

- Exclude condiments, toppings, beverages, and standalone side items.

- Include only items with available saturated fat, sodium, and dietary
  fiber information.

- Select options with meaningful nutritional trade-offs rather than one
  item being most favorable across all three highlighted nutrients.

- Display the available nutrition information while highlighting
  saturated fat, sodium, and fiber.

- Allow the participant to select one option without a timer.

- Optionally ask which nutrient information they examined first.

- Generate immediate comparative feedback using the actual nutrient
  values.

**Feedback structure:**

The feedback should identify up to two favorable features of the
selected option and one potential nutritional trade-off. It should then
provide a practical suggestion associated with the less favorable
nutrient characteristic. Comparisons should use terms such as "more,"
"less," "most," and "least," while acknowledging ties appropriately.
Calories should not be emphasized or introduced into the generated
feedback.

**3.3 Scenario 2 — Restaurant or Takeout**

This scenario teaches participants to recognize useful information from
menu descriptions when full nutrient information is unavailable.

**Display text:**

"You're out for dinner with friends and ordering from the menu. Which
would you go for?"

**Food options:**

- Grilled chicken sandwich with fries

- Roasted salmon with steamed vegetables and rice

- Crispy chicken wrap with a side salad

Participants select one option and receive corresponding feedback.

The feedback explains useful clues in the menu wording, such as grilled,
roasted, steamed, and crispy, and identifies possible modifications or
questions participants might consider when ordering.

**Required app functionality:**

- Display the three predefined menu descriptions.

- Allow the participant to select one option.

- Present the corresponding predefined feedback.

- Optionally ask which menu word the participant noticed first.

- Save the selected option and activity completion status.

**Integration requirement:** This scenario does not require
restaurant-specific menu data. The options and feedback should be
implemented using the approved scenario script.

**3.4 Scenario 3 — Grocery or Convenience Store**

This scenario teaches participants how to compare packaged foods using
Nutrition Facts labels.

**Display text:**

"You're picking up \[category\] for the week. Here are three options.
Let's check the labels."

The participant sees three packaged products from the same food
category. The category should be relevant to the participant's dietary
focus area where appropriate. For example, a participant focusing on
Sodium might compare canned soups, while a participant focusing on Added
Sugars might compare breakfast cereals or yogurts. Participants review
serving sizes and nutrient information, including saturated fat, sodium,
added sugars, dietary fiber, and percent Daily Values.

**Required app functionality:**

- Display three comparable packaged food products.

- Present the corresponding Nutrition Facts labels.

- Highlight saturated fat, sodium, added sugars, and dietary fiber.

- Include percent Daily Values where available.

- Allow participants to compare the products and select one.

- Optionally ask which label information they examined first.

- Provide immediate feedback explaining the nutritional features and
  trade-offs of the selected product.

- Save the selected product and completion status.

**Integration requirement:** The products and labels must use accurate
nutrition information. Product categories should be connected to the
participant's selected nutrition focus area where feasible.

**3.5 Scenario 4 — A Meal Someone Else Prepares**

This scenario helps participants practice choosing from foods available
at a family meal, gathering, or friend's home.

**Display text:**

"You're at a family dinner, or a friend's place, and the food is set
out. You're filling your plate."

**Food options:**

- Fried chicken and mac and cheese

- Grilled chicken, rice and beans, and a salad

- A little of everything, with seconds on the vegetables

Participants select one option and receive feedback about the potential
strengths and limitations of their selection. The scenario emphasizes
that participants may not control what foods are prepared but can still
make decisions about what they select from the available options.

**Required app functionality:**

- Display the three predefined plate descriptions.

- Allow participants to select one option.

- Present the corresponding predefined feedback.

- Save the response and activity completion status.

**Integration requirement:** The scenario should reinforce realistic
decision-making within social and family eating environments without
presenting culturally familiar foods or particular food choices as
inherently wrong.

**3.6 Scenario 5 — At Home**

This scenario focuses on small changes that participants can make when
preparing a familiar meal.

**Display text:**

"You're making dinner at home with a can of beans, rice, and some
vegetables. You have about 20 minutes."

**Food options:**

- Beans straight from the can with the liquid, over white rice

- Rinsed beans with vegetables and brown rice

- Beans and vegetables with cheese, over white rice

Participants choose an option and receive feedback explaining how
preparation choices can influence sodium intake, fiber, and other
nutritional characteristics.

**Required app functionality:**

- Display three predefined preparation options.

- Allow participants to select one option.

- Present corresponding feedback.

- Save the participant's selection and activity completion status.

**Integration requirement:** The activity should reinforce the broader
Week 2 message that practical, achievable choices can support dietary
goals without requiring participants to abandon familiar meals.

**3.7 Scenario Activity Completion**

After completing three scenarios, participants receive a brief
completion message acknowledging their practice and introducing the
Youth Ambassador modeling video.

**Required app functionality:**

- Recognize completion after three distinct scenarios.

- Allow participants to complete additional scenarios voluntarily.

- Preserve responses and completion status for each scenario.

- Provide a clear transition to the Youth Ambassador video.

- Avoid requiring all five scenarios for completion of the structured
  Week 2 activity.

4.  **Step 3: Youth Ambassador Modeling Video**

**App location:** Today screen → Week 2 Youth Ambassador Video

**Educational content:** Week 2 Youth Ambassador Modeling Video

**Purpose:** Demonstrate how an emerging adult identifies and makes a
goal-supportive food choice in a realistic everyday eating environment.
The Week 2 Youth Ambassador videos illustrate practical food-selection
decisions in situations such as dining halls, grocery stores,
restaurants, takeout settings, and meals prepared by others. Unlike the
interactive scenarios, which require participants to evaluate predefined
choices, the modeling videos demonstrate how a peer approaches the
decision-making process, identifies relevant information, considers
available options, and selects a practical action. The video should
reinforce the idea that heart-healthy choices can be made within
ordinary eating circumstances and that participants do not need access
to ideal food environments.

**Required app functionality:**

- Display an assigned Week 2 Youth Ambassador video within the Today
  screen.

- Provide standard playback controls and captions where available.

- Record video completion according to established LLHS procedures.

- Allow participants to revisit the video.

- Provide a clear transition to the Week 2 interactive planning
  activity.

**Integration requirement:** The video should reinforce the
food-selection skills taught in the overview and practiced in the
scenario activities.

5.  **Step 4: Interactive Activity — Planning Where You'll Use It**

**App location:** Today screen → Week 2 Interactive Activity

**Purpose:** Help participants translate the food-selection skills
practiced during Week 2 into a specific action plan for an upcoming
eating situation. The activity should take place after participants
complete the interactive scenarios and watch the Youth Ambassador video.

It builds on the initial behavioral goal and action plan developed
during Week 1. Participants identify where they will apply their
food-selection skills, what they intend to choose, a possible barrier,
and how they will respond if the barrier arises.

**5.1 Display Previous Action Plan**

At the beginning of the activity, participants see their Week 1 "This
Week" card containing their existing nutrition focus, behavioral goal,
and cue.

**Display text:**

"Here's your plan from last week. This week you practiced spotting
better choices. Now, pick a moment to use it."

No numerical dietary scores should be displayed.

**Required app functionality:**

- Retrieve the participant's existing Week 1 goal and action plan.

- Display the current nutrition focus, goal, and cue.

- Maintain these details throughout the Week 2 planning process.

- Allow the participant to retain or modify the existing plan.

**5.2 Prompt 1 — Pick Your Moment**

**Display text:**

"Pick one eating situation coming up this week where you can use what
you practiced."

**Response options:**

Participants select a setting:

- Dining hall

- Restaurant or takeout

- Grocery or convenience store

- A meal someone else prepares

- At home

- Somewhere else

Participants then select a day and eating occasion, such as breakfast,
lunch, dinner, snack, or drink.

An option to use the situation from the Week 1 plan should also be
available.

**Required app functionality:**

- Display the available setting options.

- Allow the participant to select a day and eating occasion.

- Provide an option to reuse the Week 1 situation.

- Save the selected situation and timing information.

- Carry the response forward into the remaining planning prompts.

**5.3 Prompt 2 — Choose What You'll Go For**

**Display text:**

"What will you look for or choose there?"

The app displays a short list of possible actions matched to the
participant's dietary focus area and selected eating environment.

For example, a participant focusing on Sodium who selects a restaurant
might see:

- Ask for sauce on the side.

- Choose a dish without cured, smoked, or brined ingredients.

- Ask for nutrition information.

- Write my own action.

**Required app functionality:**

- Retrieve the participant's selected dietary focus area.

- Use the selected eating environment from Prompt 1.

- Display relevant predefined action options.

- Allow participants to select one option or enter their own.

- Save the selected action for inclusion in the final plan.

**Integration requirement:** The action suggestions should be consistent
with the scientific guidance provided in the Week 1 focus-area education
and the Week 2 overview video.

**5.4 Prompt 3 — Spot What Could Get in the Way**

**Display text:**

"What's one thing that could make this harder?"

**Response options:**

- Not enough time

- Cost

- What's available

- Someone else choosing

- Feeling tired or stressed

- A craving for something else

- I might forget

- Something else

An optional free-text response should be available.

**Required app functionality:**

- Display the predefined barrier options.

- Allow participants to select one barrier.

- Provide an optional free-text response where appropriate.

- Save the participant's response.

- Use the selected barrier to determine the coping responses displayed
  in the next prompt.

**5.5 Prompt 4 — Decide What You'll Do About It**

**Display text:**

"If that happens, what will you do?"

The app displays possible coping responses matched to the barrier
selected in Prompt 3.

For example:

If the participant selects "Not enough time":

"Decide before I get there and pick the quickest option on my list."

If the participant selects "What's available":

"Pick the closest option, since a better choice still counts."

Participants should also have the option to enter their own coping
response.

**Required app functionality:**

- Retrieve the selected barrier.

- Display corresponding predefined coping suggestions.

- Allow the participant to select one option or write their own.

- Save the selected coping response.

- Associate the coping response with the planned action.

**Integration requirement:** The final action plan should retain the
connection between the anticipated barrier and the participant's
selected response.

**5.6 Prompt 5 — Keep It, Add It, or Replace It**

**Display text:**

"What do you want to do with last week's plan?"

**Response options:**

- Keep last week's plan and add this one.

- Replace last week's plan with this one.

- Keep last week's plan only.

Participants are then asked:

"When should we remind you?"

The participant selects a reminder time associated with the chosen
eating situation.

**Required app functionality:**

- Retrieve the Week 1 action plan.

- Allow the participant to decide whether to retain, replace, or add to
  the existing plan.

- Save the selected plan-management choice.

- Provide a reminder-time selection.

- Associate active reminders with the appropriate action plan.

- Prevent a discarded plan from continuing to generate reminders.

**Development clarification:** If participants keep both plans, the app
should support displaying and managing multiple active goals or planned
actions. If participants retain only the Week 1 plan, the previously
established action should remain active without being unintentionally
replaced.

**5.7 Activity Completion Feedback**

After the planning activity, participants receive a personalized
summary.

**Display text:**

"Thanks. Here's your plan: When \[situation and time\], you'll
\[choice\]. If \[barrier\], you'll \[response\]. We'll remind you
\[time\]. You can change it any time."

The app populates the statement using the participant's selected
situation, intended action, barrier, coping response, and reminder.

**Required app functionality:**

- Generate the summary using the participant's actual responses.

- Save the final active plan.

- Display the saved plan within the updated "This Week" card.

- Allow participants to revisit and edit the plan.

6.  **Step 5: Updated "This Week" Card**

**App location:** Today screen → This Week

After completing the planning activity, participants return to their
updated "This Week" card.

The card should reflect their selected dietary focus area, active
behavioral goal, planned eating situation, intended action, and
reminder.

If the participant chose to keep both their Week 1 plan and the new Week
2 plan, the app should preserve access to both. If they chose to replace
the previous plan, the new plan should be displayed as active. If they
chose to keep only the previous plan, that plan should remain unchanged.

**Required app functionality:**

- Retrieve the saved active plan or plans.

- Display the participant's current nutrition focus area.

- Display the behavioral goal and planned action.

- Display the associated situation and reminder cue.

- Allow participants to review or edit their plan.

- Ensure the displayed information corresponds to their selection during
  Prompt 5.

**Integration requirement:** The updated "This Week" card should serve
as the connection between structured Week 2 educational activities and
the participant's real-world behavior throughout the week.

7.  **Step 6: Connection to Ongoing App Features**

Once the participant has completed the Week 2 activities and reviewed
the updated action plan, the plan should remain accessible through
relevant LLHS app features.

**Today Screen**

The Today screen should display progress through Week 2 activities and
provide access to the participant's active goal and planned action.

Potential functions include activity completion indicators, links to the
educational content, and access to the current action plan.

**Eat Dashboard**

The Eat dashboard should continue displaying the participant's dietary
focus area and existing nutrition feedback. Week 2 activity completion
should not automatically change baseline HEI-related feedback. Any
changes to dietary assessment results must follow the approved
scientific scoring procedures.

**Reminders and Prompts**

The reminder system should use the participant's selected action-plan
cue to support implementation in everyday life.

For example, if a participant plans to compare packaged foods while
grocery shopping on Saturday, a reminder could be associated with the
selected shopping occasion.

Reminders should be updated when the participant modifies their action
plan.

**Meal Logging**

Participants may use lightweight meal logging to record eating behaviors
or reflect on their food choices. Meal logging is optional and should
not be required for completing the Week 2 educational module. Meal logs
should remain distinct from the baseline ASA24 dietary recalls used to
calculate HEI-2020 feedback.

**Digital Twin**

The digital twin features, including "What if?" and "My Path," remain
available throughout the week. Participants may use these tools to
explore food choices or reflect on their goals, but no additional Week
2-specific digital twin activity is required by the current educational
materials.

**Future Me LLM Guidance**

The Future Me chatbot remains available for participants seeking
assistance with applying dietary guidance in everyday situations.

For example, participants may ask about nutrition-label information,
restaurant choices, or alternatives when their planned food option is
unavailable.

Guidance should remain consistent with approved LLHS nutrition
recommendations.

**Gamification**

Points or other established gamification features may recognize
completion of the Week 2 educational activities according to the LLHS
point system.

The app development team should confirm the point values for the
overview video, scenario activities, Youth Ambassador video, and
planning activity.

**Social Wing**

The Social Wing remains available for optional participant interaction
and peer support.

Week 2 does not require a dedicated social-sharing activity.

**Fitbit Integration**

Existing Fitbit-related features remain available, but Week 2 does not
introduce a new wearable-specific educational activity.

8.  **Key Data Connections**

The Week 2 experience requires information to move between educational
activities, scenario interactions, action planning, and ongoing app
features.

**Week 1 Goal and Nutrition Focus → Week 2 Educational Content**

Inputs: Participant-selected dietary focus area, existing behavioral
goal, and action plan.

Outputs: Week 2 educational context and continued emphasis on the
participant's selected nutrition focus.

**Week 2 Overview Video → Interactive Scenarios**

Input: Education on food-selection cues, Nutrition Facts labels, and
practical dietary choices.

Output: Participant readiness to apply the demonstrated skills in
realistic scenarios.

**Scenario Selection → Scenario Presentation**

Input: Three participant-selected eating environments.

Output: Corresponding scenario activities, food options, and feedback.

**Scenario Responses → Activity Progress**

Inputs: Selected options, completed scenarios, and optional follow-up
responses.

Outputs: Completion tracking and access to additional practice
opportunities.

**Scenario Activities → Youth Ambassador Video**

Input: Completion of at least three scenario activities.

Output: Transition to peer modeling of food-selection behaviors.

**Week 1 Action Plan → Week 2 Planning Activity**

Inputs: Existing focus area, behavioral goal, and cue.

Outputs: Previous plan displayed as the starting point for Week 2
planning.

**Week 2 Planning Responses → Updated Action Plan**

Inputs: Selected situation, intended action, anticipated barrier, coping
response, plan-management choice, and reminder.

Outputs: Updated or retained behavioral action plan.

**Updated Action Plan → This Week Card**

Input: Participant's saved active plan or plans.

Output: Current nutrition focus, planned action, and cue displayed
within the Today screen.

**Updated Action Plan → Ongoing App Support**

Inputs: Saved plan, relevant situation, and reminder time.

Outputs: Plan information accessible through the appropriate LLHS
features, including reminders and self-monitoring tools.

The app should preserve these connections so participants do not need to
repeatedly enter information already provided during Week 1 or earlier
Week 2 activities.

9.  **Week 2 Completion and Navigation**

Week 2 should provide a clear progression from educational content to
practice, modeling, planning, and real-world application. The Today
screen should indicate which Week 2 activities have been completed and
which remain available.

**Intended sequence:**

Overview Video → Three Scenario Activities → Youth Ambassador Modeling
Video → Interactive Planning Activity → Updated This Week Card

Completing three scenarios should satisfy the structured scenario
requirement. Additional scenarios should remain available for
participants who wish to continue practicing.

The full Week 2 module should support completion of the overview video,
minimum scenario practice, Youth Ambassador video, and planning
activity.

The exact video completion thresholds and associated point values should
follow the established LLHS app specifications.

Participants should be able to revisit educational content and their
saved action plans after completing the module.
