// Display data for the eight focus areas (AREA_META, below): Fluent food
// pictures, the logging tags that "include" each area, and a fixed
// encouraging line — effort and habits only, never a score.
const F = (name: string) => FLUENT_FOOD[name];
const FLUENT_FOOD: Record<string, number> = {
  apple: require("@/assets/icons/fluent/red-apple.png"),
  banana: require("@/assets/icons/fluent/banana.png"),
  leafyGreen: require("@/assets/icons/fluent/leafy-green.png"),
  carrot: require("@/assets/icons/fluent/carrot.png"),
  beans: require("@/assets/icons/fluent/beans.png"),
  grain: require("@/assets/icons/fluent/sheaf-of-rice.png"),
  milk: require("@/assets/icons/fluent/glass-of-milk.png"),
  poultry: require("@/assets/icons/fluent/poultry-leg.png"),
  fish: require("@/assets/icons/fluent/fish.png"),
  peanuts: require("@/assets/icons/fluent/peanuts.png"),
  avocado: require("@/assets/icons/fluent/avocado.png"),
  bread: require("@/assets/icons/fluent/bread.png"),
  salt: require("@/assets/icons/fluent/salt.png"),
  candy: require("@/assets/icons/fluent/candy.png"),
  butter: require("@/assets/icons/fluent/butter.png"),
};

// A starter question the knowledge base can answer, per HEI-2020 component.
export const COACH_FOCUS_QUESTION: Record<string, string> = {
  total_fruits: "What's an easy fruit to grab between classes?",
  whole_fruits: "Is juice as good as whole fruit?",
  total_vegetables: "How can I add a vegetable at the dining hall?",
  greens_beans: "What counts as greens and beans?",
  whole_grains: "Is brown rice a whole grain?",
  dairy: "What counts as dairy if I don't drink milk?",
  total_protein_foods: "What are easy protein foods for a busy day?",
  seafood_plant_proteins: "What are easy plant proteins at the dining hall?",
  fatty_acids: "Is olive oil a healthy fat?",
  refined_grains: "What's an easy swap for white bread?",
  sodium: "What are easy swaps for salty snacks?",
  added_sugars: "What can I drink in place of soda?",
  saturated_fats: "What's an easy swap for fried food?",
};

/** A Future Me starter question for a ring's food group (log category). */
export const COACH_CATEGORY_QUESTION: Record<string, string> = {
  vegetables: COACH_FOCUS_QUESTION.total_vegetables,
  fruit: COACH_FOCUS_QUESTION.total_fruits,
  whole_grains: COACH_FOCUS_QUESTION.whole_grains,
  beans_fish_nuts: COACH_FOCUS_QUESTION.seafood_plant_proteins,
  dairy: COACH_FOCUS_QUESTION.dairy,
  other_protein: COACH_FOCUS_QUESTION.total_protein_foods,
};

/** The eight focus areas' labels (backend/focus_areas.py is the source). */
export const FOCUS_AREA_LABEL: Record<string, string> = {
  fruit: "Fruit",
  vegetables_beans: "Vegetables and beans",
  grains: "Grains",
  dairy: "Dairy",
  protein_foods: "Protein foods",
  fats: "Fats",
  sodium: "Sodium",
  added_sugars: "Added sugars",
};

/** A small, concrete action per focus area, for Today and Future Me. */
export const FOCUS_AREA_ACTION: Record<string, string> = {
  fruit: "add a piece of fruit",
  vegetables_beans: "add some vegetables or beans",
  grains: "pick a whole grain",
  dairy: "add milk, yogurt or a fortified soy drink",
  protein_foods: "add beans, fish, nuts or seeds",
  fats: "swap in nuts, seeds or olive oil",
  sodium: "swap a salty side for something fresh",
  added_sugars: "swap a sweet drink for water",
};

type AreaMeta = { images: number[]; categories: string[] | null; cheer: string };

/**
 * The eight focus areas on the Eat screen: pictures, the logging categories
 * that "include" the area (null for areas that are about eating less, which
 * count any logged day instead), and a fixed encouraging line.
 */
export const AREA_META: Record<string, AreaMeta> = {
  fruit: { images: [F("apple"), F("banana")], categories: ["fruit"], cheer: "Nice work! Keep it up!" },
  vegetables_beans: { images: [F("leafyGreen"), F("beans")], categories: ["vegetables", "beans_fish_nuts"], cheer: "Every bowl of greens or beans counts!" },
  grains: { images: [F("grain")], categories: ["whole_grains"], cheer: "Every swap you try counts!" },
  dairy: { images: [F("milk")], categories: ["dairy"], cheer: "Steady choices add up!" },
  protein_foods: { images: [F("poultry"), F("fish")], categories: ["other_protein", "beans_fish_nuts"], cheer: "Mixing it up keeps meals interesting!" },
  fats: { images: [F("avocado"), F("peanuts")], categories: ["beans_fish_nuts"], cheer: "Simple adds make a difference!" },
  sodium: { images: [F("salt")], categories: null, cheer: "Small swaps make a big difference!" },
  added_sugars: { images: [F("candy")], categories: null, cheer: "One small change at a time." },
};

/** Does a logged meal touch this focus area? Areas about eating less count any logged meal. */
export function mealMatchesArea(meal: any, areaId: string): boolean {
  const cats = AREA_META[areaId]?.categories;
  if (!cats) return !meal.skipped;
  return !meal.skipped && (meal.categories ?? []).some((c: string) => cats.includes(c));
}
