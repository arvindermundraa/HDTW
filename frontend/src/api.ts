import { storage } from "@/src/utils/storage";

// Empty means same origin: the web build served next to the API (Vercel).
const BASE = process.env.EXPO_PUBLIC_BACKEND_URL || "";
export const TOKEN_KEY = "llhs.token";

// Writes that can change today's rings or logs, and so the avatar's mood.
const MOOD_WRITES = /^\/(meals(\?|$)|activities|sleep|daily-goals|chat\/confirm-action|wearable\/sync)/;
let onMoodInputsChanged = () => {};
export function setMoodRefresher(fn: () => void) {
  onMoodInputsChanged = fn;
}

async function req<T = any>(path: string, options: RequestInit = {}, auth = true): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (auth) {
    const token = await storage.secureGet<string>(TOKEN_KEY, "");
    if (token) headers.Authorization = `Bearer ${token}`;
  }
  const res = await fetch(`${BASE}/api${path}`, {
    ...options,
    headers: { ...headers, ...(options.headers as Record<string, string>) },
  });
  const text = await res.text();
  let data: any = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!res.ok) {
    const detail = (data && data.detail) || `Request failed (${res.status})`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  if ((options.method ?? "GET") !== "GET" && MOOD_WRITES.test(path)) onMoodInputsChanged();
  return data as T;
}

/** Rejects if a request takes longer than `ms`, so nothing spins forever. */
function withTimeout<T>(p: Promise<T>, ms: number): Promise<T> {
  return Promise.race([p, new Promise<T>((_, reject) => setTimeout(() => reject(new Error("timeout")), ms))]);
}

export type RecallStatus = {
  assessment_type: string | null;
  label?: string;
  state: "upcoming" | "open" | "finished" | "complete";
  opens_on?: string;
  due_by?: string;
  days_until_open?: number;
  days_until_due?: number;
  finished_at?: string | null;
  recalls_done?: number;
  recalls_needed?: number;
};
export type ProgramStep = {
  key: "watch" | "practice" | "do_it" | "reflect";
  label: string;
  title: string;
  prompt?: string | null;
  route: string | null;
  params: Record<string, string> | null;
  ready: boolean;
  done: boolean;
  points: number;
  self_marked: boolean;
};
export type ProgramUnit = {
  week: number;
  title: string;
  summary: string;
  opens_on: string;
  available: boolean;
  status: "done" | "current" | "available" | "upcoming";
  steps_done: number;
  steps_total: number;
  steps: ProgramStep[];
};
export type Program = {
  current_week: number;
  weeks: number;
  units: ProgramUnit[];
  next_step: (ProgramStep & { week: number; unit_title: string }) | null;
};
export type RecallInfo = {
  asa24_username: string | null;
  asa24_password: string | null;
  link: string;
  recall: RecallStatus;
  new_results: boolean;
};

export const api = {
  login: (email: string, password: string) =>
    req("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }, false),
  signupStart: (email: string) =>
    req<{ sent: boolean; message: string }>("/auth/signup/start", { method: "POST", body: JSON.stringify({ email }) }, false),
  signup: (email: string, password: string, name: string, code: string) =>
    req("/auth/signup", { method: "POST", body: JSON.stringify({ email, password, name, code }) }, false),
  forgotPassword: (email: string) =>
    req<{ sent: boolean; message: string }>("/auth/password/forgot", { method: "POST", body: JSON.stringify({ email }) }, false),
  resetPassword: (email: string, code: string, new_password: string) =>
    req("/auth/password/reset", { method: "POST", body: JSON.stringify({ email, code, new_password }) }, false),
  me: () => req("/auth/me"),
  logout: () => req("/auth/logout", { method: "POST" }),

  // Onboarding — Nutrition & Lifestyle Profile survey (schema-driven;
  // personalization/context for the LLM, NOT a diet-quality screener —
  // baseline diet quality comes from ASA24 recalls, imported separately).
  // Sent with the auth token (when signed in) so the backend can include
  // the participant's current `answers` for the edit-my-profile flow.
  getProfileSurvey: () => req("/onboarding/profile-survey"),
  submitProfileSurvey: (answers: Record<string, any>) =>
    req("/onboarding/profile-survey", { method: "POST", body: JSON.stringify({ answers }) }),
  updateProfileSurvey: (answers: Record<string, any>) =>
    req("/onboarding/profile-survey", { method: "PATCH", body: JSON.stringify({ answers }) }),

  // HEI-2020 assessments (ASA24-derived, imported by researchers — this
  // app never computes HEI-2020 itself) + Priority Selection Flow
  getHeiHistory: () => req("/assessments/hei2020/history"),
  // ASA24 recall card: recalls happen on NCI's ASA24 site; the app links
  // out, records "I finished", and flags newly imported results.
  getRecall: () => req<RecallInfo>("/asa24/recall"),
  recallFinished: (assessment_type: string) =>
    req<{ recall: RecallStatus }>("/asa24/recall/finished", { method: "POST", body: JSON.stringify({ assessment_type }) }),
  recallResultsSeen: () => req("/asa24/results/seen", { method: "POST" }),
  getFocusCandidates: () => req("/assessments/hei2020/focus-candidates"),
  setFocusAreas: (area_id: string, goal?: string, plan?: string) =>
    req("/profile/focus-areas", { method: "POST", body: JSON.stringify({ area_id, goal: goal || null, plan: plan || null }) }),

  // FOOD / MOVE / REST domains — kept distinct, never combined
  getFoodDomain: () => req("/domains/food"),
  getMoveDomain: () => req("/domains/move"),
  getRestDomain: () => req("/domains/rest"),
  getDomains: () => req("/domains"),

  // My Path — trail/milestone avatar
  getPath: () => req("/path"),

  getMeals: () => req("/meals"),
  getLogCategories: () => req("/meals/categories", {}, false),
  createMeal: (payload: any) => req("/meals", { method: "POST", body: JSON.stringify(payload) }),
  categorizeMealText: (description: string) =>
    req("/meals/categorize-text", { method: "POST", body: JSON.stringify({ description }) }),
  analyzePhoto: (image_base64: string) =>
    req("/meals/analyze-photo", { method: "POST", body: JSON.stringify({ image_base64 }) }),
  // Voice Logging was removed as of 2026-09 — TAMU AI, now the app's sole
  // AI provider, documents no audio/speech input. See README/PRD.

  createActivity: (payload: any) => req("/activities", { method: "POST", body: JSON.stringify(payload) }),
  createSleep: (payload: any) => req("/sleep", { method: "POST", body: JSON.stringify(payload) }),
  getActivities: () => req("/activities"),
  getSleeps: () => req("/sleep"),
  // Daily rings (Eat / Move / Sleep) — targets the participant sets; progress
  // is counted from what they log each day in the study TZ, decided by the
  // server. The `tz` parameter is kept for backwards-compat with older
  // callers but is no longer sent.
  getDailyGoals: (tz?: string): Promise<import("./daily-goals").GoalSnapshot> => {
    void tz;
    return req("/daily-goals");
  },
  setAvatar: (avatar: Partial<import("./avatar").AvatarConfig>): Promise<{ avatar: import("./avatar").AvatarConfig }> =>
    req("/profile/avatar", { method: "PATCH", body: JSON.stringify(avatar) }),
  setDailyGoal: (domain: import("./daily-goals").Domain, payload: { target: number; category?: string }) =>
    req(`/daily-goals/${domain}`, { method: "PUT", body: JSON.stringify(payload) }),
  pauseDailyGoal: (domain: import("./daily-goals").Domain) => req(`/daily-goals/${domain}`, { method: "DELETE" }),
  getGoals: () => req("/goals"),
  createGoal: (payload: any) => req("/goals", { method: "POST", body: JSON.stringify(payload) }),

  // Wearable Move/Rest (Fitbit primary per the 9/10/26 deck; Apple Health /
  // Health Connect kept as alternates — manual entry always retained)
  getWearableStatus: () => req("/wearable/status"),
  connectWearable: (provider: "fitbit" | "apple_health" | "health_connect") =>
    req("/wearable/connect", { method: "POST", body: JSON.stringify({ provider }) }),
  disconnectWearable: () => req("/wearable/disconnect", { method: "POST" }),
  syncWearable: (
    hours?: number,
    activity_minutes?: number,
    recorded_date?: string,
    extra?: { sleep_start?: string; sleep_end?: string; steps?: number }
  ) => req("/wearable/sync-sleep", { method: "POST", body: JSON.stringify({ hours, activity_minutes, recorded_date, ...extra }) }),
  // Several device days at once (each upserted by its date), so the
  // behavioral twin has the history it needs for weekday/weekend patterns.
  syncWearableDays: (
    days: { recorded_date: string; hours?: number; sleep_start?: string; sleep_end?: string; activity_minutes?: number; steps?: number }[]
  ) => req("/wearable/sync-days", { method: "POST", body: JSON.stringify({ days }) }),

  // Gentle Nudges
  getNudgeSettings: () => req("/settings/nudges"),
  updateNudgeSettings: (enabled: boolean, time: string) =>
    req("/settings/nudges", { method: "PATCH", body: JSON.stringify({ enabled, time }) }),

  // Weekly Story
  getWeeklyStory: () => req("/weekly-story"),

  getCheckin: () => req("/safety/checkin"),
  ackCheckin: (id: string) => req(`/safety/checkin/${id}/ack`, { method: "POST" }),

  getCurriculum: () => req("/curriculum"),
  setSleepSchedule: (bedtime: string, wake: string) =>
    req("/settings/sleep-schedule", { method: "PUT", body: JSON.stringify({ bedtime, wake }) }),
  getProgram: () => req<Program>("/program"),
  completeProgramStep: (week: number, step: string, text?: string) =>
    req<{ points_awarded: number; program: Program }>(`/program/${week}/${step}/done`, { method: "POST", body: JSON.stringify({ text: text ?? null }) }),

  // Weekly workflow (content-driven per-week journey; backend/weekly_workflow.py).
  // Returns the per-week view for every supported week; the UI reads the
  // `enabled` flag to decide whether to show the new Week card or fall back
  // to the existing program.py card.
  getWeeklyWorkflow: () => req<import("./weekly-workflow").WeeklyWorkflow>("/weekly-workflow"),
  getWeeklyStep: (week: number, stepId: string) =>
    req<import("./weekly-workflow").StepDetail>(`/weekly-workflow/${week}/step/${stepId}`),
  completeWeeklyStep: (week: number, stepId: string, body?: { responses?: Record<string, any>; note?: string }) =>
    req<{ already: boolean; points_awarded: number; week: import("./weekly-workflow").WeekView }>(
      `/weekly-workflow/${week}/step/${stepId}/complete`,
      { method: "POST", body: JSON.stringify(body ?? {}) },
    ),
  // Week 2 scenarios: settings picker + per-setting scenario body + choice response.
  getWeek2ScenariosConfig: () =>
    req<import("./weekly-workflow").Week2ScenariosConfig>("/weekly-workflow/2/scenarios/config"),
  setWeek2Settings: (settings: string[]) =>
    req<import("./weekly-workflow").Week2ScenariosConfig>(
      "/weekly-workflow/2/scenarios/settings",
      { method: "POST", body: JSON.stringify({ settings }) },
    ),
  getWeek2Scenario: (setting: string) =>
    req<import("./weekly-workflow").Week2ScenarioBody>(`/weekly-workflow/2/scenario/${setting}`),
  respondWeek2Scenario: (setting: string, body: {
    choice_id: string;
    follow_up?: { id: string; answer: string } | null;
    shown_option_ids?: string[];
    shown_option_payload?: Array<Record<string, any>>;
  }) => req<import("./weekly-workflow").Week2ScenarioResponseResult>(
    `/weekly-workflow/2/scenario/${setting}/respond`,
    { method: "POST", body: JSON.stringify(body) },
  ),

  // Week 2 planning (Phase 2).
  getWeek2PlanningConfig: () =>
    req<import("./weekly-workflow").PlanningConfig>("/weekly-workflow/2/planning/config"),
  getWeek2PlanningActions: (focusArea?: string | null, setting?: string | null) =>
    req<{ focus_area: string | null; setting: string | null; actions: string[] }>(
      `/weekly-workflow/2/planning/actions?focus_area=${encodeURIComponent(focusArea ?? "")}&setting=${encodeURIComponent(setting ?? "")}`,
    ),
  getWeek2PlanningCoping: (barrier?: string | null) =>
    req<{ barrier: string | null; coping_options: string[] }>(
      `/weekly-workflow/2/planning/coping?barrier=${encodeURIComponent(barrier ?? "")}`,
    ),
  submitWeek2Planning: (body: import("./weekly-workflow").PlanningSubmit) =>
    req<import("./weekly-workflow").PlanningSubmitResult>(
      "/weekly-workflow/2/planning/submit",
      { method: "POST", body: JSON.stringify(body) },
    ),
  getPlans: () =>
    req<{ plans: import("./weekly-workflow").PlanningCardForToday[] }>("/plans"),
  getPlan: (id: string) => req<Record<string, any>>(`/plans/${encodeURIComponent(id)}`),
  completeVideo: (id: string) => req(`/curriculum/${id}/complete`, { method: "POST" }),

  getGames: () => req("/games"),
  completeGame: (id: string, markers: string[], score: number) =>
    req(`/games/${id}/complete`, { method: "POST", body: JSON.stringify({ markers, score }) }),

  // Daily challenge — same question for everyone each day, chosen by date.
  getDailyChallenge: () => req("/games/daily-challenge"),
  answerDailyChallenge: (challenge_id: string, choice_id: string) =>
    req("/games/daily-challenge/answer", { method: "POST", body: JSON.stringify({ challenge_id, choice_id }) }),

  // Build a Balanced Meal — drag-and-drop plate builder
  getIngredients: () => req("/games/ingredients"),
  scorePlate: (round_id: string, ingredient_ids: string[]) =>
    req("/games/g3/score-plate", { method: "POST", body: JSON.stringify({ round_id, ingredient_ids }) }),

  // Texas A&M Dining — Commons + Sbisa, generic endpoint
  // `forRecommendation` asks the backend for the allergy-filtered menu (use
  // it wherever items are suggested/offered to the participant).
  getDiningMenu: (hall: "commons" | "sbisa", period: "breakfast" | "lunch" | "dinner" = "lunch", forRecommendation = false) =>
    req(`/dining/menu?hall=${hall}&period=${period}${forRecommendation ? "&for_recommendation=true" : ""}`),
  reviewPlate: (item_names: string[]) =>
    req("/dining/review-plate", { method: "POST", body: JSON.stringify({ item_names }) }),

  // Plate Composer — appeal-first suggested plates from today's real menu
  getSuggestedPlates: (hall: "commons" | "sbisa", period: "breakfast" | "lunch" | "dinner" = "lunch") =>
    req(`/dining/plates?hall=${hall}&period=${period}`),
  swapDiningItem: (hall: "commons" | "sbisa", period: "breakfast" | "lunch" | "dinner", item_id: string, exclude_ids: string[] = []) =>
    req("/dining/swap", { method: "POST", body: JSON.stringify({ hall, period, item_id, exclude_ids }) }),
  chatBuildMeal: (message: string, hall: "commons" | "sbisa", period: "breakfast" | "lunch" | "dinner") =>
    req("/dining/chat-build-meal", { method: "POST", body: JSON.stringify({ message, hall, period }) }),
  getSbisaMenu: () => req("/dining/sbisa/menu"),
  reviewSbisaPlate: (item_names: string[]) =>
    req("/dining/sbisa/review-plate", { method: "POST", body: JSON.stringify({ item_names }) }),

  // TAMU AI — mandatory, sole AI provider. Every participant needs a
  // personal key (a small staff-managed admin/testing pool is the only
  // exception, invisible from here — see backend/tamus_client.py).
  getTamusModels: () => req("/settings/tamus/models"),
  getTamusSettings: () => req("/settings/tamus"),
  updateTamusSettings: (payload: { api_key?: string; model_chat?: string; model_vision?: string }) =>
    req("/settings/tamus", { method: "PATCH", body: JSON.stringify(payload) }),
  clearTamusSettings: () => req("/settings/tamus", { method: "DELETE" }),
  testTamusConnection: () => req("/settings/tamus/test", { method: "POST" }),

  getGamification: () => req("/gamification"),
  getCohort: () => req("/cohort"),

  // Social Page — Wings
  getWingGoalPresets: () => req("/wings/goals/presets"),
  createWing: (name: string, goal_metric: string, goal_target?: number) =>
    req("/wings", { method: "POST", body: JSON.stringify({ name, goal_metric, goal_target }) }),
  joinWing: (join_code: string) =>
    req("/wings/join", { method: "POST", body: JSON.stringify({ join_code }) }),
  leaveWing: () => req("/wings/leave", { method: "POST" }),
  getMyWing: () => req("/wings/mine"),
  // Lightweight pollable response — only the fields that can change tap-to-
  // tap (combined progress, cheer totals, challenge count, member count).
  getMyWingSummary: () => req("/wings/mine/summary"),
  sendWingCheer: (key: string) =>
    req("/wings/cheer", { method: "POST", body: JSON.stringify({ key }) }),
  sendLabFeedback: (payload: {
    screen: string; device: string; what_doing: string; what_happened: string; rating?: number | null;
  }) => req("/wings/feedback", { method: "POST", body: JSON.stringify(payload) }),

  // --- Wings Phase 2: photo posts (behind WINGS_PHOTOS_MODE gate) ----------
  //
  // `uploadWingPost` sends multipart, so it can't go through `req()` (which
  // sets Content-Type: application/json). We let the browser pick the
  // multipart boundary and only inject the auth header manually.
  getWingsPhotosConfig: () => req("/wings/photos/config"),
  getMyWingPosts: () => req("/wings/posts/mine"),
  getWingFeed: () => req("/wings/feed"),
  reactToWingPost: (postId: string, key: string) =>
    req(`/wings/posts/${encodeURIComponent(postId)}/react`,
        { method: "POST", body: JSON.stringify({ key }) }),
  reportWingPost: (postId: string) =>
    req(`/wings/posts/${encodeURIComponent(postId)}/report`, { method: "POST" }),
  deleteWingPost: (postId: string) =>
    req(`/wings/posts/${encodeURIComponent(postId)}`, { method: "DELETE" }),
  uploadWingPost: async (payload: {
    file: { uri: string; name: string; type: string } | File;
    caption: string;
    steps: string[];
    focusTag?: string | null;
  }) => {
    const form = new FormData();
    // React Native and web both accept a File/Blob OR a {uri,name,type}
    // object in FormData.append; the native layer serialises each the
    // right way.
    form.append("photo", payload.file as any, (payload.file as any).name);
    form.append("caption", payload.caption);
    form.append("steps_json", JSON.stringify(payload.steps));
    if (payload.focusTag) form.append("focus_tag", payload.focusTag);
    const token = await storage.secureGet<string>(TOKEN_KEY, "");
    const res = await fetch(`${BASE}/api/wings/posts`, {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: form as any,
    });
    const text = await res.text();
    let data: any = null;
    try { data = text ? JSON.parse(text) : null; } catch { data = text; }
    if (!res.ok) {
      const detail = (data && data.detail) || `Upload failed (${res.status})`;
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }
    return data;
  },

  // The Coach (Q&A from the reviewed knowledge base). Memory is per session.
  chatHistory: (sessionId: string) => req(`/chat/history?session_id=${encodeURIComponent(sessionId)}`),
  chat: (message: string, sessionId: string) =>
    withTimeout(req("/chat", { method: "POST", body: JSON.stringify({ message, session_id: sessionId }) }), 45000),
  getSuggestedPrompts: () => req("/chat/suggested-prompts"),
  // The Coach can PROPOSE an action (log a meal/activity/sleep, or change
  // focus areas) via chat()'s `pending_action` field, but nothing is ever
  // written until the participant explicitly confirms it here.
  confirmChatAction: (action: { type: string; payload: Record<string, any> }) =>
    withTimeout(req("/chat/confirm-action", { method: "POST", body: JSON.stringify(action) }), 30000),

  // Future Me (the digital twin): own data + the rule-based what-if engine.
  getFutureMe: (tz?: string) => {
    void tz;
    return req("/future-me");
  },
  whatIf: (scenarioId: string) =>
    withTimeout(req("/future-me/what-if", { method: "POST", body: JSON.stringify({ scenario_id: scenarioId }) }), 45000),
  // From your own meals: the regulars Future Me noticed in the student's
  // own meal logs, the swap from the reviewed swap table that fits their
  // focus area and setup, and where it is on today's real dining menu.
  // Also returned inside getFutureMe() as `from_your_meals`.
  getFromYourMeals: () => req("/future-me/from-your-meals"),
  // "I'll try it" / "I tried it" / "Not for me" — the student's own say on
  // a swap. Returns the refreshed from_your_meals block.
  setSwapStatus: (swapId: string, status: "trying" | "tried" | "dismissed") =>
    req(`/future-me/swaps/${status}`, { method: "POST", body: JSON.stringify({ swap_id: swapId }) }),

  // The behavioral twin across food, movement and sleep (also returned as
  // getFutureMe().twin). Patterns are asked about, never assumed; steps come
  // from a reviewed library and say why; reasons the student gives are
  // remembered. Every write returns the refreshed twin as `twin`.
  getTwin: () => req("/twin"),
  answerTwinQuestion: (key: string, answer: "yes" | "sometimes" | "no", circumstances: string[] = [], note?: string) =>
    req("/twin/questions/answer", { method: "POST", body: JSON.stringify({ key, answer, circumstances, note: note || null }) }),
  respondTwinStep: (body: {
    rec_id: string;
    response: "accept" | "decline" | "worked" | "didnt_fit" | "still_doing" | "lapsed";
    reasons?: string[];
    note?: string;
    when?: string;
    coping?: string;
  }) => req("/twin/steps/respond", { method: "POST", body: JSON.stringify(body) }),
  setTwinDomain: (domain: "activity" | "sleep", on = true) =>
    req("/twin/domains", { method: "POST", body: JSON.stringify({ domain, on }) }),
  removeTwinLearned: (key: string) => req("/twin/learned/remove", { method: "POST", body: JSON.stringify({ key }) }),
  getGroceryList: () => req("/twin/grocery"),
  addGrocery: (body: { rec_id?: string; text?: string }) => req("/twin/grocery", { method: "POST", body: JSON.stringify(body) }),
  setGroceryDone: (id: string, done: boolean) =>
    req(`/twin/grocery/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify({ done }) }),
  removeGrocery: (id: string) => req(`/twin/grocery/${encodeURIComponent(id)}`, { method: "DELETE" }),
};

export { req };
