# Week 1 User Workflow and Educational Content Integration (team spec)

1.  **Week 1 Overview**

Week 1 introduces participants to the LLHS intervention, explains the
importance of cardiovascular disease prevention during emerging
adulthood, and helps participants use their baseline dietary feedback to
identify an area for improvement. The central objective is to move
participants from understanding their current dietary behaviors to
selecting a personally relevant nutrition focus and developing an
achievable behavioral goal. Week 1 should function as a connected
learning experience rather than a collection of independent videos and
activities. Information from earlier steps should inform subsequent
screens and activities wherever appropriate.

**Week 1 participant journey:**

1.  Watch the Week 1 overview video.

2.  Review personalized baseline dietary feedback.

3.  Select a nutrition focus area.

4.  Watch the educational mini-lecture for that focus area.

5.  Complete the interactive activity, "Reflecting on Your Starting
    Point."

6.  Set a small, specific behavioral goal and create an action plan.

7.  Access the goal and relevant progress-tracking features within the
    app.


2.  **Step 1: Week 1 Overview Video**

**App location:** Today screen → Week 1 educational content

**Educational content:** Week 1 Overview Video

**Purpose:** Introduce participants to cardiovascular health, explain
why dietary habits during emerging adulthood matter, and prepare
participants to interpret their personalized dietary feedback.

The video introduces the American Heart Association's Life's Essential 8
and explains why LLHS focuses primarily on nutrition. It emphasizes that
participants do not need to change all aspects of their eating habits
simultaneously. The final scenes introduce the baseline dietary recalls,
explain the purpose of personalized feedback, and prepare participants
to select an area for improvement.

**Required app functionality:**

- Display the Week 1 overview video within the Today screen.

- Provide a clear next step directing participants to their personalized
  dietary feedback.

- Allow participants to navigate from the video to the Eat dashboard or
  relevant feedback screen.

**Integration requirement:** The video should lead directly into
participants' own dietary results so they can apply the concepts
introduced in the educational content.

3.  **Step 2: Personalized Baseline Dietary Feedback**

**App location:** Eat dashboard

**Data source:** Two baseline 24-hour dietary recalls completed using
ASA24.

**Assessment framework:** Healthy Eating Index-2020 (HEI-2020).

The app should use participants' baseline dietary assessment results to
provide personalized feedback on their eating patterns. The feedback
should help participants identify:

- **Strengths:** Dietary areas where their reported intake shows closer
  alignment with dietary recommendations.

- **Areas for improvement:** Dietary areas where their reported intake
  shows room for improvement.

Because the baseline assessment is based on two dietary recall days, the
feedback should be presented as an estimate of reported dietary patterns
rather than a definitive assessment of usual dietary intake.

The eight LLHS nutrition focus areas are:

1.  Fruit

2.  Vegetables and Beans

3.  Grains

4.  Dairy

5.  Protein Foods

6.  Fats

7.  Sodium

8.  Added Sugars

These focus areas are derived from relevant HEI-2020 components and the
dietary priorities of the intervention.

**Required app functionality:**

- Retrieve the participant's baseline dietary assessment results.

- Map the relevant HEI-2020 components to the eight LLHS focus areas.

- Display strengths and areas for improvement using clear visual
  feedback.

- Present the information in accessible, nonjudgmental language.

- Provide a clear transition from reviewing results to selecting a
  nutrition focus area.

**Important:** Participants should not see numerical HEI scores in the
Week 1 interactive reflection activity. The reflection uses a visual
progress bar showing alignment with dietary recommendations.

**Development clarification:** The methodology for combining HEI
components into LLHS focus-area results, particularly for Grains and
Fats, must follow the approved scientific scoring specifications.

4.  **Step 3: Nutrition Focus Selection**

**App location:** Eat dashboard → Nutrition Focus selection

After reviewing their personalized results, participants select one
nutrition focus area they would like to work on first. The selection
process should encourage participants to consider their areas for
improvement while preserving their autonomy to choose an area that feels
personally relevant.

**Required app functionality:**

- Display the available nutrition focus areas.

- Highlight areas identified through baseline feedback as having room
  for improvement.

- Allow participants to select one focus area to begin with.

- Keep other focus areas accessible for exploration rather than
  restricting access only to highlighted areas.

- Save the participant's selected focus area and associate it with the
  subsequent educational activity and goal-setting process.

**Integration requirement:** The selected focus area determines which
educational mini-lecture and personalized reflection content the
participant receives next. For example, a participant selecting Whole
Grains should be directed to the Grains educational video, followed by
the reflection activity populated with that participant's baseline
grain-related feedback.

5.  **Step 4: Focus-Area Educational Mini-Lecture**

**App location:** Today screen / selected nutrition focus area

After selecting a focus area, the participant watches its corresponding
educational mini-lecture.

Each mini-lecture is designed to explain:

- What the nutrition focus area includes.

- Why it matters for cardiovascular health.

- How the relevant dietary behaviors influence cardiovascular risk
  factors.

- What recommended dietary choices look like in everyday life.

- Practical ways participants can improve their eating patterns.

The eight mini-lectures are developed using AHA dietary guidance and
theory-informed educational messaging, including scientific
explanations, relatable examples, and actionable takeaways.

**Required app functionality:**

- Display the mini-lecture corresponding to the selected focus area.

- Maintain the participant's selected focus throughout the remaining
  Week 1 workflow.

- Provide a clear transition from the mini-lecture to the interactive
  reflection activity.

**Integration requirement:** Educational content should prepare
participants to understand and interpret the specific dietary behavior
that will be examined in their reflection activity. For example, the
Added Sugars mini-lecture explains common sources of added sugars, their
cardiovascular implications, and how to identify them on Nutrition Facts
labels. The participant then reflects on where foods and beverages
higher in added sugars appeared during their baseline dietary recall
days.

6.  **Step 5: Interactive Activity — Reflecting on Your Starting Point**

**App location:** Today screen → Week 1 interactive activity

**Theoretical basis:** Social Cognitive Theory — self-regulation and
self-efficacy.

**Purpose:** Help participants examine their baseline dietary behaviors,
compare them with dietary recommendations, recognize existing strengths,
and identify an opportunity for a realistic behavior change. The
activity should take place after the participant watches the focus-area
mini-lecture and before goal-setting and action planning.

**6.1 Personalized Feedback Display**

At the beginning of the activity, participants see a visual bar
representing their alignment with dietary recommendations for the
selected focus area.

**Display text:**

"Here's how close your eating in this area is to the Dietary Guidelines.
This is based on the two days you recorded."

**Required app functionality:**

- Retrieve the participant's baseline result for their selected focus
  area.

- Display the result as a visual bar.

- Do not display numerical scores.

- For Grains and Fats, display the combined focus-area result, with the
  two underlying component results available when tapped.

- Ensure the displayed result corresponds to the participant's selected
  nutrition focus.

The visual bar should support reflection without making participants
feel that their dietary results represent a grade or judgment.

**6.2 Reflection Prompt 1 — Look at What's Behind the Result**

This prompt encourages participants to recall when foods relevant to
their focus area appeared during their two recorded dietary recall days.

**For focus areas emphasizing adding foods (Fruit, Vegetables and Beans,
Grains, Dairy, Protein Foods):**

"Think about the two days you recorded. When did \[focus area\] show up
in your meals and snacks, if at all?"

**For focus areas emphasizing swaps or reductions (Fats, Sodium, Added
Sugars):**

"Think about the two days you recorded. When did foods higher in
\[saturated fat, sodium, or added sugars\] show up in your meals,
snacks, and drinks, if at all?"

**Response format: Select all that apply.**

- Breakfast

- Lunch

- Dinner

- Snacks

- Drinks

- It rarely showed up

- This isn't part of how I eat

Optional free-text response should also be available.

**Required app functionality:**

- Populate the appropriate question based on the selected focus area.

- Support multiple selections.

- Allow optional written responses.

- Save responses for the participant's reflection record.

**Theoretical construct:** Self-regulation, through self-monitoring of
dietary behavior.

**6.3 Reflection Prompt 2 — Find the Room to Move**

**Display text:**

"The space left on the bar shows where this area has room to grow. Where
in your day could a small change fit most easily?"

**Response options:**

- Breakfast

- Lunch

- Dinner

- Snacks

- Drinks

- Not sure yet

**Required app functionality:**

- Display the participant's focus-area feedback alongside or immediately
  before the question.

- Allow participants to select the occasion where they believe a change
  would fit most easily.

- Save the selected occasion.

- Carry this response forward into the goal-setting and action-planning
  interface.

**Integration requirement:** This selection should reduce repetition by
informing the next step. For example, if a participant selects
"Breakfast," the goal-setting screen should recognize breakfast as their
preferred opportunity for change.

**Theoretical constructs:** Self-regulation and self-efficacy.

**6.4 Reflection Prompt 3 — Notice What's Working**

**Display text:**

"What's one thing in your eating that's already working?"

**Purpose:** Encourage participants to identify an existing strength
rather than focusing exclusively on dietary inadequacies.

**Required app functionality:**

- Provide a response field for participants to identify a personal
  strength.

- Save the response as part of their Week 1 reflection.

**Theoretical construct:** Self-efficacy, through recognition of
existing capabilities.

**6.5 Activity Completion Feedback**

After completing the reflection, participants receive a brief transition
message.

**Display text:**

"Thanks. \[Selected occasion\] is a good place to look. Next, you'll
pick one small change and plan when you'll try it."

The selected occasion should be populated from Prompt 2.

**Required app functionality:**

- Personalize the message using the participant's response.

- Direct participants to goal-setting and action planning.

**Development clarification:** The team should provide appropriate
alternative language when a participant selects "Not sure yet," rather
than inserting that answer into the standard completion message.

7.  **Step 6: Goal-Setting and Action Planning**

**App location:** Today screen → Goal-setting activity

**Theoretical basis:** Social Cognitive Theory — self-regulation and
self-efficacy.

After completing the interactive reflection, participants develop a
small, specific behavioral goal related to their selected nutrition
focus area.

The goal-setting process should build on the information participants
have already provided.

For example:

**Selected focus:** Fruit

**Reflection response:** Breakfast

**Possible goal:** "I will add fruit to breakfast on weekday mornings."

**Action plan:** "When I prepare breakfast before class, I will add a
banana or frozen berries."

**Required app functionality:**

- Retain the participant's selected nutrition focus area.

- Carry forward the meal occasion identified in the reflection activity.

- Allow participants to specify the behavior they intend to try.

- Allow participants to specify when and where the behavior will occur.

- Save the goal and associated action plan.

- Make the goal accessible for subsequent self-monitoring and
  reflection.

The goal-setting interface should support personalized goals rather than
assigning the same behavior to all participants within a focus area.

**Integration requirement:** The participant's selected focus,
reflection response, and action plan should form a connected record.

**Proposed enhancement:** The app could use the participant's selected
meal occasion to present relevant goal examples, while still allowing
participants to develop their own goal.

8.  **Step 7: Connection to Ongoing App Features**

Once the participant has established a Week 1 goal, it should be
accessible through the app's ongoing behavior-change features.

**Today Screen**

The Today screen should communicate the participant's current nutrition
focus and the action they intend to practice. Potential functions
include displaying the current goal, linking to the relevant focus area,
and providing access to daily activities.

**Eat Dashboard**

The Eat dashboard should continue to display the participant's baseline
nutrition feedback and selected focus area. Importantly, baseline HEI
feedback should not be presented as having improved simply because the
participant watched a video, completed an activity, or logged a meal.
Any later changes to diet-quality feedback must be based on the
scientifically specified dietary assessment and scoring process.

**Meal Logging**

The meal-logging feature can support behavioral self-monitoring by
allowing participants to record food choices and reflect on how their
actions relate to their goals. For example, a participant whose goal is
to add vegetables at dinner may use meal logging to record whether they
included vegetables in a meal. Meal logging should be distinguished from
the baseline ASA24 dietary assessment used to calculate the
participant's HEI-2020 feedback.

9.  **Key Data Connections**

The Week 1 experience requires information to move between several app
components.

**Baseline dietary assessment → Eat dashboard**

Inputs: Two baseline ASA24 recalls and scientifically calculated
HEI-2020 results.

Outputs: Personalized feedback on dietary strengths and areas for
improvement.

**Eat dashboard → Nutrition Focus selection**

Input: Baseline focus-area feedback.

Output: Participant-selected nutrition focus.

**Nutrition Focus selection → Mini-lecture**

Input: Selected focus area.

Output: Corresponding educational video.

**Nutrition Focus selection → Interactive reflection**

Inputs: Selected focus area and corresponding baseline dietary result.

Outputs: Focus-specific visual bar and reflection prompts.

**Interactive reflection → Goal-setting**

Inputs: Selected focus area, reflection responses, and selected meal
occasion.

Outputs: Context for the participant's goal and action plan.

**Goal-setting → Ongoing self-monitoring**

Inputs: Saved behavioral goal, planned action, and intended occasion.

Outputs: Goal information accessible through relevant app features.

The app should preserve these connections so participants are not
repeatedly required to enter information that has already been
collected.

10. **Week 1 Completion and Navigation**

Week 1 should provide a clear and intuitive progression through the
educational and behavioral activities.

The Today screen should help participants understand which steps they
have completed and which steps remain.

The intended sequence is:

Overview Video → Dietary Feedback → Focus Selection → Focus-Area
Mini-Lecture → Interactive Reflection → Goal and Action Plan

Completion of these steps represents the intended Week 1 onboarding and
behavior-change workflow.
