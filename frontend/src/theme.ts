// LLHS design tokens — "BetterMe clarity × client mockups": white cards on a
// soft ground, one bold sans heading per screen, and colour used mainly to
// tell Eat / Move / Sleep apart. Key names are unchanged from the earlier
// editorial theme so every screen picks the new look up without edits.
// Mature, restrained palette: near-black ink, neutral greys, a deep forest
// primary, and muted Eat / Move / Sleep accents used sparingly.
export const colors = {
  surface: "#F5F6F5", // page ground
  onSurface: "#101A16",
  surfaceSecondary: "#FFFFFF", // cards
  onSurfaceSecondary: "#3A4541",
  surfaceTertiary: "#EEF0EF", // tracks, quiet fills
  onSurfaceTertiary: "#3A4541",
  surfaceInverse: "#101A16",
  onSurfaceInverse: "#FFFFFF",
  brand: "#256B4D",
  brandPrimary: "#153D31",
  onBrandPrimary: "#FFFFFF",
  brandSecondary: "#B4582B",
  onBrandSecondary: "#FFFFFF",
  brandTertiary: "#EAF0ED",
  onBrandTertiary: "#153D31",
  success: "#256B4D",
  onSuccess: "#FFFFFF",
  warning: "#8A6414",
  onWarning: "#5A410B",
  error: "#A93A2A",
  onError: "#FFFFFF",
  info: "#40549C",
  onInfo: "#FFFFFF",
  border: "#E2E6E4",
  borderStrong: "#CDD3D0",
  divider: "#ECEFED",
  muted: "#66706C",
  // Points / streak highlight — muted gold, not yellow
  warm: "#B8862B",
  warmTint: "#F4EFE3",
  onWarm: "#5F4610",
};

// One colour family per domain. `text` is the shade for words and icons
// (readable on the tint); `main` is for fills and dots.
export const domain = {
  food: { name: "Eat", main: "#2E7A58", text: "#256B4D", tint: "#EDF3F0", dotOff: "#D6E3DC" },
  move: { name: "Move", main: "#BF6232", text: "#A04E24", tint: "#F6EFEA", dotOff: "#EAD9CE" },
  rest: { name: "Sleep", main: "#4A5EA6", text: "#3D5094", tint: "#EEF0F6", dotOff: "#D7DCEC" },
};

export const fonts = {
  display: "PlusJakartaSans_600SemiBold",
  displaySemi: "PlusJakartaSans_600SemiBold",
  regular: "PlusJakartaSans_400Regular",
  medium: "PlusJakartaSans_500Medium",
  semibold: "PlusJakartaSans_600SemiBold",
  bold: "PlusJakartaSans_700Bold",
  // 8-bit face — used ONLY inside the game screens (titles, scores, round
  // numbers, buttons). Questions, answers and explanations in a game stay
  // on Plus Jakarta Sans so they're easy to read.
  pixel: "PressStart2P_400Regular",
};

// Palette used only inside the pixel-style game screens — a darker,
// contrast-heavy variant of the forest-green brand palette, intentionally
// scoped so it never leaks into the rest of the mature app style.
export const pixelPalette = {
  bg: "#0D1E17",
  bgDeep: "#071510",
  surface: "#1A3328",
  surfaceEdge: "#0A1D15",
  ink: "#F4F7F2",
  inkDim: "#9FB7A6",
  accent: "#5FE07A",
  accentDeep: "#2E7A58",
  warn: "#F7C752",
  wrong: "#E07A5F",
  // Hard-edge borders — chunky, 2px solid, no shadows.
  borderWidth: 2,
};

export const spacing = { xs: 4, sm: 8, md: 12, lg: 16, xl: 20, "2xl": 32, "3xl": 48 };
export const radius = { sm: 6, md: 10, lg: 14, pill: 999 };
export const fontSize = { sm: 13, base: 15, lg: 16, xl: 18, "2xl": 20, "3xl": 24, "4xl": 30 };

// Hairline border + faint lift: crisp rather than floaty.
export const shadow = {
  card: { boxShadow: "0px 1px 2px rgba(16,26,22,0.05)" },
  lifted: { boxShadow: "0px 4px 12px rgba(16,26,22,0.25)" },
};

// --- Hand-drawn extension tokens (added for the Path screen illustration +
// character creator hand-drawn overhaul) ---------------------------------
// Purely additive: nothing above this line was renamed or altered. Kept so
// the avatar-customization components (character.tsx, character-create.tsx,
// sketch.tsx) still resolve correctly, even though the currently-active My
// Path screen doesn't reference this namespace itself right now.
export const handDrawn = {
  paper: "#FBF3E3",
  paperDeep: "#F3E8D0",
  ink: "#332A22",
  inkSoft: "rgba(51,42,34,0.5)",
  inkFaint: "rgba(51,42,34,0.22)",
  watercolor: {
    sun: "#F0C36B",
    moss: "#89A66B",
    clay: "#D98E63",
    sky: "#8FB8C7",
    berry: "#C97B94",
    plum: "#A186B5",
  },
  // Curated skin-tone swatches for character customization — identity
  // expression only, never a body-size/shape axis.
  skinTones: ["#F4CFA0", "#E3AD77", "#B97D4B", "#8B5E3C", "#5C3A21"],
  wobble: { strokeJitter: 2.2, cornerJitter: 5, boilingAmplitude: 0.6 },
};

// --- Neo-Brutalist extension tokens (character-creator token-color swatch
// options only) ------------------------------------------------------------
export const neoBrutalist = {
  ink: "#15130F",
  canvasBg: "#F2EFE6",
  pathActive: "#FF4B3E",
  onPathActive: "#FFFFFF",
  pathLocked: "#D9D4C6",
  lockedFill: "#EDEAE0",
  cardFills: ["#FFD23F", "#6FE3D0", "#FF8B6B", "#9C8CFF"],
};

// --- Journal / flat-matte skin tokens (kept for the illustrated Path
// components; the currently-active My Path screen uses `colors`/`domain`
// directly instead and does not read from this namespace) -----------------
export const journal = {
  bg: colors.surface,
  hillFar: colors.surfaceTertiary,
  hillMid: colors.surfaceSecondary,
  pineFill: colors.brandTertiary,
  pineTrunk: colors.borderStrong,
  trailFill: colors.surfaceTertiary,
  trailBorder: colors.border,
  trailActiveFill: colors.brandPrimary,
  trailActiveBorder: colors.brandPrimary,
  nodeAchievedFill: colors.brandPrimary,
  nodeAchievedIcon: colors.onBrandPrimary,
  nodeGoalFill: colors.brandSecondary,
  nodeGoalIcon: colors.onBrandSecondary,
  nodeNextFill: colors.surface,
  nodeNextBorder: colors.brandPrimary,
  nodeNextIcon: colors.brandPrimary,
  nodeLockedFill: colors.surfaceTertiary,
  nodeLockedBorder: colors.border,
  nodeLockedText: colors.muted,
  labelText: colors.onSurface,
  labelTextLocked: colors.muted,
  leaderLine: colors.borderStrong,
  tokenBorder: colors.brandPrimary,
  tokenBg: colors.surfaceSecondary,
  youPillBg: colors.brandPrimary,
  youPillText: colors.onBrandPrimary,
};

export const IMAGES = {
  hero: "https://images.unsplash.com/photo-1603277578692-c699f37c67d3?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjAzMzl8MHwxfHNlYXJjaHwxfHxhYnN0cmFjdCUyMGF0bW9zcGhlcmljJTIwd2VsbG5lc3MlMjB0ZXh0dXJlJTIwc2FnZSUyMGdyZWVuJTIwYW5kJTIwY3JlYW18ZW58MHx8fHwxNzg3NzE1NTY0fDA&ixlib=rb-4.1.0&q=85",
  hqBotanical: "https://images.pexels.com/photos/19045066/pexels-photo-19045066.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
  foodFlatlay: "https://images.pexels.com/photos/9717268/pexels-photo-9717268.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
};
