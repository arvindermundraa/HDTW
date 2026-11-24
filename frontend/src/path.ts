import type { Feather } from "@expo/vector-icons";
import type React from "react";

export type Milestone = {
  id: string;
  label: string;
  behavior: string;
  achieved: boolean;
  achieved_at?: string | null;
  progress?: { current: number; target: number };
  detail?: string;
  action?: { label: string; route: string; params?: Record<string, string> } | null;
  week?: number;
};

/** One week of the 8-week path (backend personal_path.py). */
export type PathWeek = {
  week: number;
  title: string;
  opens_on: string;
  status: "done" | "current" | "available" | "upcoming";
  available: boolean;
  milestones: Milestone[];
  achieved: number;
  total: number;
};

type FeatherName = React.ComponentProps<typeof Feather>["name"];

export const BEHAVIOR_ICON: Record<string, FeatherName> = {
  start: "flag",
  onboarding: "user",
  logging: "coffee",
  priority_selection: "target",
  focus_area: "target",
  movement: "activity",
  sleep: "moon",
  curriculum: "play-circle",
  practice: "grid",
  apply: "check-square",
  reflect: "message-square",
  assessment: "calendar",
};

// The trail drawn on My Path, in a 390 × 440 box: three cubic segments
// (the SVG path "M150 460 C 150 380, 300 380, 280 320 S 90 250, 130 200
// S 320 160, 300 100", with its S-segments' reflected control points
// written out). It runs on past the last week into the horizon.
export const TRAIL_D = "M150 460 C 150 380, 300 380, 280 320 S 90 250, 130 200 S 320 160, 300 100";
const SEGMENTS: [number, number][][] = [
  [[150, 460], [150, 380], [300, 380], [280, 320]],
  [[280, 320], [260, 260], [90, 250], [130, 200]],
  [[130, 200], [170, 150], [320, 160], [300, 100]],
];

function cubic(p: [number, number][], t: number): [number, number] {
  const u = 1 - t;
  const a = u * u * u, b = 3 * u * u * t, c = 3 * u * t * t, d = t * t * t;
  return [a * p[0][0] + b * p[1][0] + c * p[2][0] + d * p[3][0], a * p[0][1] + b * p[1][1] + c * p[2][1] + d * p[3][1]];
}

// Sample the trail once and index it by distance, so stops are evenly spaced.
const SAMPLES: { x: number; y: number; len: number }[] = (() => {
  const pts: { x: number; y: number; len: number }[] = [];
  let len = 0;
  let prev: [number, number] | null = null;
  for (const seg of SEGMENTS) {
    for (let i = 0; i <= 80; i++) {
      const [x, y] = cubic(seg, i / 80);
      if (prev) len += Math.hypot(x - prev[0], y - prev[1]);
      pts.push({ x, y, len });
      prev = [x, y];
    }
  }
  return pts;
})();
const TOTAL = SAMPLES[SAMPLES.length - 1].len;

/** Point at fraction f of the trail (0 = bottom, 1 = where it meets the horizon). */
export function trailPoint(f: number): { x: number; y: number } {
  const target = Math.max(0, Math.min(1, f)) * TOTAL;
  const i = SAMPLES.findIndex((s) => s.len >= target);
  return SAMPLES[Math.max(0, i)];
}

/** Evenly spaced stops for the n weeks, leaving trail beyond the last one. */
export function stopPositions(n: number): { x: number; y: number }[] {
  if (n <= 0) return [];
  if (n === 1) return [trailPoint(0.5)];
  const from = 0.07, to = 0.86;
  return Array.from({ length: n }, (_, i) => trailPoint(from + ((to - from) * i) / (n - 1)));
}
