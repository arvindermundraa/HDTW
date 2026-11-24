import { domain } from "@/src/theme";
import { ringText } from "@/src/rings";

export type Domain = "food" | "move" | "rest";
export type GoalPlan = { start_date: string; enabled: boolean; target?: number; category?: string | null; domain: Domain };
export type GoalProgress = GoalPlan & { target: number; label: string; value: number; ratio: number; complete: boolean };
export type GoalDay = { date: string; goals: GoalProgress[] };
export type GoalSnapshot = {
  today: string | null; timezone: string | null; days: GoalDay[]; pending: GoalPlan[];
  mood?: import("./avatar").AvatarMood;
  /**
   * Rolling 7-day STUDY_TZ-window figures. `eat_days`, `move_days` and
   * `rest_days` count distinct days with any real log for that ring;
   * `any_days` is their union. Today, Future Me and Progress all read
   * from these so the numbers can't drift (same backend helper feeds
   * `/api/future-me`).
   */
  week?: {
    move_minutes: number;
    move_reference_minutes: number;
    eat_days: number;
    move_days: number;
    rest_days: number;
    any_days: number;
  };
};
export const DOMAINS: Domain[] = ["food", "move", "rest"];

// Ring colours follow the app's Eat / Move / Sleep families.
export const DOMAIN = {
  // The Eat ring is binary (filled once at least one meal is logged); its
  // "target" is 1 by construction and the server ignores stored targets > 1.
  food: { name: "Eat", color: domain.food.main, text: domain.food.text, pale: domain.food.tint, track: "#DDE7E2", icon: "coffee" as const, unit: "meals", defaultTarget: 1, step: 1, min: 1, max: 1 },
  move: { name: "Move", color: domain.move.main, text: domain.move.text, pale: domain.move.tint, track: "#EEE2DA", icon: "activity" as const, unit: "minutes", defaultTarget: 30, step: 5, min: 5, max: 180 },
  rest: { name: "Sleep", color: domain.rest.main, text: domain.rest.text, pale: domain.rest.tint, track: "#DFE3EF", icon: "moon" as const, unit: "hours", defaultTarget: 8, step: 0.5, min: 0.5, max: 16 },
};
export const FOOD_OPTIONS = [
  { id: "vegetables", label: "Vegetables" }, { id: "fruit", label: "Fruit" },
  { id: "whole_grains", label: "Whole grains" }, { id: "beans_fish_nuts", label: "Beans, fish & nuts" },
  { id: "dairy", label: "Dairy" }, { id: "other_protein", label: "Protein foods" },
];

// deviceTimezone() used to be exported here. Every day/week boundary is
// decided by the server in STUDY_TZ now; the phone no longer sends its
// zone. If some future screen genuinely needs the device zone (not for
// day math), inline `Intl.DateTimeFormat().resolvedOptions().timeZone`.

/** A sensible starting Eat ring, taken from the participant's first focus area. */
export function suggestedFoodCategory(focusAreas: string[] | null | undefined): string {
  const map: Record<string, string> = {
    total_fruits: "fruit", whole_fruits: "fruit", total_vegetables: "vegetables", greens_beans: "vegetables",
    whole_grains: "whole_grains", dairy: "dairy", total_protein_foods: "other_protein",
    seafood_plant_proteins: "beans_fish_nuts", fatty_acids: "beans_fish_nuts",
  };
  for (const id of focusAreas ?? []) if (map[id]) return map[id];
  return "vegetables";
}

/** "20 / 30 min", or once past the goal "60 / 60 min · +10 min" (see src/rings.ts). */
export function ringValueText(g: GoalProgress): string {
  return ringText(g.value, g.target, g.domain);
}
