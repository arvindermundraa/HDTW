// Microsoft Fluent Emoji 3D (MIT — see assets/icons/fluent/LICENSE). Only the
// figures LLHS actually uses are bundled; they're accents inside neutral or
// pale-tinted tiles, never decoration on their own.

export const FLUENT = {
  star: require("@/assets/icons/fluent/star.png"),
  fire: require("@/assets/icons/fluent/fire.png"),
  shield: require("@/assets/icons/fluent/shield.png"),
  mountain: require("@/assets/icons/fluent/mountain.png"),
  flag: require("@/assets/icons/fluent/triangular-flag.png"),
  graduationCap: require("@/assets/icons/fluent/graduation-cap.png"),
  puzzle: require("@/assets/icons/fluent/puzzle-piece.png"),
  seedling: require("@/assets/icons/fluent/seedling.png"),
  salad: require("@/assets/icons/fluent/green-salad.png"),
  handshake: require("@/assets/icons/fluent/handshake.png"),
  wing: require("@/assets/icons/fluent/wing.png"),
  trophy: require("@/assets/icons/fluent/trophy.png"),
  target: require("@/assets/icons/fluent/bullseye.png"),
} as const;

// Food pictures for the HEI-2020 components live with the rest of each
// component's display data in src/food.ts.

/** One picture per existing badge (backend BADGE_DEFS) and its real rule. */
export const BADGE_ART: Record<string, { image: number; rule: string }> = {
  "First Lesson": { image: FLUENT.graduationCap, rule: "Watch your first lesson" },
  "Skill Builder": { image: FLUENT.puzzle, rule: "Finish a practice game" },
  "Consistent Logger": { image: FLUENT.seedling, rule: "Log on 3 days in a row" },
  "Balanced Week": { image: FLUENT.salad, rule: "Balanced meals across a week" },
};
