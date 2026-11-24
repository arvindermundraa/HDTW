// Client types + helpers for the weekly workflow engine (backend/weekly_workflow.py).
// Shape mirrors what GET /api/weekly-workflow returns per week; see
// backend/content/weeks/weekN.json for the authoritative content.

export type StepType =
  | "video"
  | "feedback"
  | "focus_selection"
  | "reflection"
  | "goal_and_plan"
  | "scenario_set"
  | "plan"
  | "review";

export type WeekStepStatus = {
  id: string;
  type: StepType;
  label: string;
  title?: string;
  cta_next_label?: string;
  draft: boolean;
  points: number;
  status: "done" | "pending";
  completed_at?: string | null;
  auto: boolean;
  route?: string | null;
};

export type WeekPhase = {
  id: string;
  label: string;
  steps: string[];
  done: number;
  total: number;
};

export type WeekView = {
  mode: "off" | "test_only" | "on";
  enabled: boolean;
  week: number;
  title: string;
  summary?: string;
  sequence: string[];
  phases: WeekPhase[];
  steps: WeekStepStatus[];
  steps_done: number;
  steps_total: number;
  next_step_id: string | null;
  carried: Record<string, unknown>;
};

export type WeeklyWorkflow = { weeks: WeekView[] };

export type StepDetail = {
  week: number;
  step_id: string;
  content: Record<string, any>;
  status: WeekStepStatus | null;
  carried: Record<string, unknown>;
};

// Which week the student is on *for the new workflow*. For Phase 1 we only
// ship Week 1; a future PR will add Week 2 handling. The decision for which
// card to show on Today lives on the client, driven by the per-week `enabled`
// flag the server returns.
export function pickCurrentWeek(data: WeeklyWorkflow | null | undefined): WeekView | null {
  if (!data?.weeks?.length) return null;
  // Prefer any enabled week that still has pending steps; else the earliest
  // enabled week; else null.
  const enabled = data.weeks.filter((w) => w.enabled);
  const inProgress = enabled.find((w) => w.steps_done < w.steps_total);
  return inProgress ?? enabled[0] ?? null;
}

export function stepById(view: WeekView | null | undefined, id: string): WeekStepStatus | null {
  return view?.steps.find((s) => s.id === id) ?? null;
}

// Week 2 scenarios — one shape per endpoint.
export type Week2SettingOption = { id: string; label: string };

export type Week2ScenariosConfig = {
  available_settings: Week2SettingOption[];
  settings_question: string;
  required_scenarios: number;
  settings_chosen: string[];
  responded_settings: string[];
  completed_count: number;
  step_done: boolean;
  completion_message?: string;
  cta_next_label?: string;
  try_another_label?: string;
};

export type Week2ScenarioFollowUp = {
  id: string;
  prompt: string;
  options: string[];
};

export type Week2ScenarioChoice = {
  id: string;
  // Scripted scenarios ship with a human-readable `text`; dining items
  // and grocery products ship with `name`.
  text?: string;
  name?: string;
  brand?: string;
  serving_size?: string;
  serving?: string;
  // Nutrient values on options are allow-listed for Week 2 scenarios.
  saturated_fat_g?: number;
  sodium_mg?: number;
  fiber_g?: number;
  added_sugars_g?: number;
  // Calories on the Week 2 lesson label (grocery + dining) —
  // nutrition team 2026-11-06, item 3: "Calories can be visible."
  // Shown as a header line separate from the four highlighted nutrients
  // the scenario feedback uses.
  calories?: number;
  sat_fat_dv_pct?: number;
  sodium_dv_pct?: number;
  added_sugars_dv_pct?: number;
  fiber_dv_pct?: number;
};

export type Week2ScenarioBody = {
  setting: string;
  label: string;
  source: "scripted" | "dining_file" | "grocery_file";
  prompt?: string;
  choices: Week2ScenarioChoice[];
  follow_up?: Week2ScenarioFollowUp | null;
  highlighted_nutrients?: string[];
  nutrient_display_labels?: Record<string, string>;
  meal_period?: string;
  dining_hall?: string;
  category_id?: string;
  category_label?: string;
  already_responded?: boolean;
  previous_response?: Record<string, any> | null;
  is_in_chosen_set?: boolean;
  coming_soon?: boolean;
};

export type Week2ScenarioFeedback = {
  chosen_id: string;
  chosen_name?: string;
  body: string;
  sentences?: string[];
  draft?: boolean;
  strengths?: Array<{ nutrient: string; phrase: string }>;
  trade_off?: { nutrient: string; phrase: string } | null;
  suggestion?: string | null;
};

export type Week2ScenarioResponseResult = {
  feedback: Week2ScenarioFeedback;
  points_awarded: number;
  step_done: boolean;
  config: Week2ScenariosConfig;
};

// Week 2 planning (Phase 2).
export type PlanningOption = { id: string; label: string; custom_text?: boolean };
export type PlanningOccasion = {
  id: string;
  label: string;
  default_time: string;
  default_reminder_time: string;
};
export type PlanningDay = { iso: string; label: string };

export type PlanningCardForToday = {
  id: string;
  source_week: number;
  status: "active" | "replaced" | "kept";
  focus_area: string | null;
  goal: string | null;
  situation_text: string;
  action_text: string | null;
  reminder_time: string | null;
  reminder_enabled: boolean;
};

export type PlanningConfig = {
  intro: string;
  settings: PlanningOption[];
  occasions: PlanningOccasion[];
  days: PlanningDay[];
  barriers: PlanningOption[];
  plan_management_options: PlanningOption[];
  prompts: Record<string, any>;
  completion_summary_template?: string;
  completion_summary_keep_only_template?: string;
  week1_plan: PlanningCardForToday | null;
};

export type PlanningSubmit = {
  situation: {
    setting?: string | null;
    custom_setting_text?: string;
    day?: string | null;
    day_label?: string;
    occasion?: string | null;
  };
  action: { text: string; source: "preset" | "custom"; preset_index?: number };
  barrier: { id?: string; label?: string; custom_text?: string };
  coping: { text: string; source: "preset" | "custom" };
  reminder: { time?: string };
  plan_management: "keep_and_add" | "replace" | "keep_week1_only";
  edit_plan_id?: string | null;
};

export type PlanningSubmitResult = {
  summary: string;
  points_awarded: number;
  plans: PlanningCardForToday[];
};
