// Pure helpers used by `AuthScene.tsx` — split out so `node --test` can
// unit-test them without pulling in React Native (TSX, SVG, Reanimated).
// Kept small and import-free on purpose.

export type SkyPalette = {
  colors: [string, string, string];
  locations: [number, number, number];
  hillBack: string;
  hillFront: string;
  cloud: string;
  sun: string | null;
};

/**
 * Painterly sky gradient driven by the study-TZ hour of day.
 *
 * Low-saturation stops so text on the frosted card stays legible (AA against
 * white). No sun ellipse at midday (would wash out) or at night (would read
 * as a moon). The hill shades track the sky mood.
 */
export function skyForHour(hour: number): SkyPalette {
  if (hour >= 5 && hour < 11) {
    // Dawn / morning: warm peach lifting into pale blue.
    return {
      colors: ["#FFD6B8", "#FBE6D4", "#CFE3EC"],
      locations: [0, 0.55, 1],
      hillBack: "#A9C8A1",
      hillFront: "#7BA873",
      cloud: "rgba(255,255,255,0.75)",
      sun: "#FFC188",
    };
  }
  if (hour >= 11 && hour < 17) {
    // Afternoon: calm pale blue, lightly warm at the horizon.
    return {
      colors: ["#B9D7E6", "#D2E4ED", "#F3EBD9"],
      locations: [0, 0.65, 1],
      hillBack: "#9CBE94",
      hillFront: "#6E9D67",
      cloud: "rgba(255,255,255,0.85)",
      sun: null,
    };
  }
  if (hour >= 17 && hour < 21) {
    // Evening: rose and lavender settling onto the hills.
    return {
      colors: ["#F3C4B0", "#E7B9C4", "#B9B9D4"],
      locations: [0, 0.5, 1],
      hillBack: "#8FA68D",
      hillFront: "#5F8763",
      cloud: "rgba(255, 236, 220, 0.75)",
      sun: "#F2A77E",
    };
  }
  // Night / early morning: deeper dawn, no sun.
  return {
    colors: ["#5A6A86", "#8CA0B6", "#C8D7D7"],
    locations: [0, 0.55, 1],
    hillBack: "#6E8E6A",
    hillFront: "#4F7452",
    cloud: "rgba(220, 230, 240, 0.65)",
    sun: null,
  };
}

export type VeggieKey =
  | "apple" | "strawberry" | "carrot" | "avocado" | "broccoli"
  | "banana" | "blueberries" | "oats";

export type FloatSpec = {
  key: VeggieKey;
  size: number;
  left: `${number}%` | number;
  top: `${number}%` | number;
  amplitude: number;
  duration: number;
  delay: number;
};

const NARROW_WIDTH = 480;

// Positions are in viewport %, placed around the frosted card rather than
// behind it. Narrow screens drop the mid-vertical ones so nothing sits
// behind the inputs on 390px.
export const FLOATERS: FloatSpec[] = [
  { key: "apple",       size: 68, left: "6%",  top: "12%", amplitude: 6, duration: 14000, delay: 0 },
  { key: "strawberry",  size: 60, left: "82%", top: "20%", amplitude: 7, duration: 17000, delay: 1400 },
  { key: "carrot",      size: 64, left: "5%",  top: "68%", amplitude: 6, duration: 15000, delay: 900 },
  { key: "avocado",     size: 64, left: "82%", top: "70%", amplitude: 7, duration: 18000, delay: 2200 },
  { key: "broccoli",    size: 70, left: "72%", top: "50%", amplitude: 8, duration: 20000, delay: 500 },
  { key: "banana",      size: 70, left: "14%", top: "48%", amplitude: 7, duration: 16000, delay: 1800 },
  { key: "blueberries", size: 60, left: "88%", top: "6%",  amplitude: 6, duration: 14000, delay: 2800 },
  { key: "oats",        size: 68, left: "4%",  top: "40%", amplitude: 6, duration: 19000, delay: 600 },
];

/** On narrow screens drop the two mid-vertical floaters that would otherwise
 *  sit close to the frosted card at 390 px wide. */
export function floatersFor(width: number): FloatSpec[] {
  const narrow = width < NARROW_WIDTH;
  return FLOATERS.filter((f) => !(narrow && (f.key === "broccoli" || f.key === "banana")));
}
