import { FOCUS_AREA_ACTION, FOCUS_AREA_LABEL } from "@/src/food";

/**
 * Future Me's one-line message (study team feedback 2.6, 5.1): tied to the
 * participant's focus area and goal when they have one, pointing at one
 * concrete thing to do today. Shared by Today and the Future Me tab.
 */
export function futureMeMessage(opts: {
  area?: string | null;
  goal?: string | null;
  hasResults: boolean;
  isNewUser: boolean;
  streak: number;
}): string {
  const { area, goal, hasResults, isNewUser, streak } = opts;
  if (area && FOCUS_AREA_LABEL[area]) {
    const label = FOCUS_AREA_LABEL[area].toLowerCase();
    return goal
      ? `You're working on ${label}. Your goal: “${goal}”. What's one meal today where you could do that?`
      : `You're working on ${label}. What's one meal today where you could ${FOCUS_AREA_ACTION[area]}?`;
  }
  if (hasResults) return "Your food recall results are in. Choose one area to work on, and I'll help you plan it.";
  if (isNewUser) return "Start small: log one meal today. That's the whole plan.";
  if (streak >= 2) return `${streak} days of logging in a row. Keep it easy today.`;
  return "Log a meal when you're ready. Every log helps me help you.";
}
