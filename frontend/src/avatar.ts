import { useEffect, useSyncExternalStore } from "react";
import { api, setMoodRefresher } from "@/src/api";
import { setServerToday, studyToday } from "@/src/study-time";

// The participant's avatar: appearance chosen once, mood from today's logs.
// Option ids mirror backend/avatar.py. There is deliberately no body size or
// shape option anywhere — only colours and fixed-silhouette overlays change.

export type AvatarConfig = {
  skin: string; hair: string; hair_color: string; face: string;
  glasses: string; outfit: string; outfit_color: string; background: string;
};
export type AvatarMood = {
  date: string;
  mood: "calm" | "content" | "energised";
  rings_closed: number;
  glow: boolean;
  props: ("salad" | "sneakers" | "rested")[];
};

export const DEFAULT_AVATAR: AvatarConfig = {
  skin: "tan", hair: "short", hair_color: "dark_brown", face: "classic",
  glasses: "none", outfit: "tee", outfit_color: "forest", background: "sage",
};

type Swatch = { id: string; label: string; color: string };
type Choice = { id: string; label: string };

export const SKIN: Swatch[] = [
  { id: "porcelain", label: "Porcelain", color: "#F3D9C6" },
  { id: "light", label: "Light", color: "#E7C1A2" },
  { id: "tan", label: "Tan", color: "#C99572" },
  { id: "olive", label: "Olive", color: "#B08458" },
  { id: "brown", label: "Brown", color: "#8A5A3C" },
  { id: "deep", label: "Deep", color: "#5C3A26" },
];
export const HAIR_COLOR: Swatch[] = [
  { id: "black", label: "Black", color: "#1E1A18" },
  { id: "dark_brown", label: "Dark brown", color: "#3B2618" },
  { id: "brown", label: "Brown", color: "#6B4428" },
  { id: "auburn", label: "Auburn", color: "#8C3F22" },
  { id: "blonde", label: "Blonde", color: "#C7A15E" },
  { id: "grey", label: "Grey", color: "#9A9C9B" },
];
export const OUTFIT_COLOR: Swatch[] = [
  { id: "forest", label: "Forest", color: "#2E5A48" },
  { id: "slate", label: "Slate", color: "#4A5E7A" },
  { id: "clay", label: "Clay", color: "#A9634A" },
  { id: "charcoal", label: "Charcoal", color: "#3A403E" },
  { id: "sand", label: "Sand", color: "#C9B48E" },
  { id: "plum", label: "Plum", color: "#6E4A63" },
];
export const BACKGROUND: Swatch[] = [
  { id: "sage", label: "Sage", color: "#DCE6E0" },
  { id: "stone", label: "Stone", color: "#E6E3DC" },
  { id: "mist", label: "Mist", color: "#DDE3EC" },
  { id: "sand", label: "Sand", color: "#EFE6D8" },
  { id: "clay", label: "Clay", color: "#EBDDD5" },
  { id: "slate", label: "Slate", color: "#D5DADE" },
];
export const HAIR: Choice[] = [
  { id: "short", label: "Short" }, { id: "crop", label: "Crop" }, { id: "wavy", label: "Wavy" },
  { id: "curly", label: "Curly" }, { id: "long", label: "Long" }, { id: "bun", label: "Bun" },
  { id: "covered", label: "Head scarf" }, { id: "none", label: "None" },
];
export const FACE: Choice[] = [
  { id: "classic", label: "Classic" }, { id: "soft", label: "Soft" }, { id: "freckles", label: "Freckles" },
  { id: "stubble", label: "Stubble" }, { id: "beard", label: "Beard" },
];
export const GLASSES: Choice[] = [{ id: "none", label: "None" }, { id: "round", label: "Round" }, { id: "square", label: "Square" }];
export const OUTFIT: Choice[] = [
  { id: "tee", label: "Tee" }, { id: "hoodie", label: "Hoodie" }, { id: "collar", label: "Collar" }, { id: "sweater", label: "Sweater" },
];

const pick = (list: Swatch[], id: string) => (list.find((s) => s.id === id) ?? list[0]).color;
export const avatarColors = (c: AvatarConfig) => ({
  skin: pick(SKIN, c.skin), hair: pick(HAIR_COLOR, c.hair_color),
  outfit: pick(OUTFIT_COLOR, c.outfit_color), background: pick(BACKGROUND, c.background),
});

/** Stored avatar with anything missing or unknown filled from the default. */
export function normalizeAvatar(a?: Partial<AvatarConfig> | null): AvatarConfig {
  const known: Record<keyof AvatarConfig, { id: string }[]> = {
    skin: SKIN, hair: HAIR, hair_color: HAIR_COLOR, face: FACE, glasses: GLASSES,
    outfit: OUTFIT, outfit_color: OUTFIT_COLOR, background: BACKGROUND,
  };
  const out = { ...DEFAULT_AVATAR };
  for (const key of Object.keys(known) as (keyof AvatarConfig)[]) {
    const v = a?.[key];
    if (v && known[key].some((o) => o.id === v)) out[key] = v;
  }
  return out;
}

export const MOOD_TEXT: Record<AvatarMood["mood"], string> = {
  calm: "feeling calm",
  content: "feeling content",
  energised: "feeling energised",
};

// ---- Today's mood, shared by every screen --------------------------------
// The backend computes it (GET /api/daily-goals → mood). Screens that already
// fetch the snapshot publish it here; any Avatar without fresh data fetches
// once. A mood from an earlier day is never shown.
let current: AvatarMood | null = null;
let fetchedAt = 0;
let inflight: Promise<void> | null = null;
const listeners = new Set<() => void>();

// Stale-mood check uses the study TZ, same as every other day comparison.
function localDate() {
  return studyToday();
}

export function publishMood(mood: AvatarMood | null | undefined) {
  if (!mood) return;
  current = mood;
  fetchedAt = Date.now();
  listeners.forEach((l) => l());
}

export function refreshMood() {
  if (inflight) return inflight;
  // Server owns "today" (study TZ). `?tz=` is deliberately not sent.
  // We also cache the server's `today` for study-time.ts's fallback —
  // important on Hermes builds that don't support Intl timeZone.
  inflight = api
    .getDailyGoals()
    .then((s) => {
      setServerToday(s.today ?? s.mood?.date);
      publishMood(s.mood);
    })
    .catch(() => {})
    .finally(() => {
      inflight = null;
    });
  return inflight;
}

setMoodRefresher(() => {
  // A write that just landed beats any in-flight read: re-read afterwards.
  const pending = inflight;
  if (pending) pending.then(() => refreshMood());
  else refreshMood();
});

export function clearMood() {
  current = null;
  fetchedAt = 0;
  listeners.forEach((l) => l());
}

const subscribe = (l: () => void) => {
  listeners.add(l);
  return () => listeners.delete(l);
};

/** Today's mood, or null (shown as calm) until it loads or after midnight. */
export function useAvatarMood(enabled = true): AvatarMood | null {
  const mood = useSyncExternalStore(subscribe, () => current, () => current);
  useEffect(() => {
    if (enabled && (!current || Date.now() - fetchedAt > 60_000)) refreshMood();
  }, [enabled]);
  // Mood dates use the rings' time zone; anything from before today is stale.
  return mood && mood.date >= localDate() ? mood : null;
}
