// Game sound effect hook — the single owner of the mute preference, the
// AudioPlayer instances, and web first-tap unlock.
//
// Rules the design calls out:
//   - Same event always plays the same sound. No random jingles.
//   - All effects < 1s and quiet by default.
//   - A mute toggle in the game header AND in Settings; both share this
//     hook so flipping either flips both. Persisted via AsyncStorage.
//   - iOS silent switch is respected (expo-audio defaults to that mode).
//   - Web browsers block playback before a user gesture — we delay creating
//     the players until the first interaction, so the unlock lands quietly
//     the first time a player taps anything on the game screen.
//   - Preload once per game session; cleanup on unmount.
//
// This module intentionally does NOT touch haptics — those live in the
// game screen itself and share the mute preference via `useGameSoundEnabled`.
import { useEffect, useRef, useCallback, useState } from "react";
import { Platform } from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";
// expo-audio ships only on Expo SDK 54+; `createAudioPlayer` returns a
// cheap, in-memory audio handle that can be played/stopped/released.
import { createAudioPlayer, setAudioModeAsync, type AudioPlayer } from "expo-audio";

export type GameSoundEvent = "tap" | "correct" | "notQuite" | "roundComplete" | "gameComplete";

const SOURCES: Record<GameSoundEvent, number> = {
  tap: require("@/assets/games/sfx/tap.wav"),
  correct: require("@/assets/games/sfx/correct.wav"),
  notQuite: require("@/assets/games/sfx/not-quite.wav"),
  roundComplete: require("@/assets/games/sfx/round-complete.wav"),
  gameComplete: require("@/assets/games/sfx/game-complete.wav"),
};

const MUTE_STORAGE_KEY = "llhs/game-sounds-muted";

// Simple pub/sub so the Settings screen's toggle and the game header's
// mute button stay in sync without a global state library.
type Listener = (muted: boolean) => void;
const listeners = new Set<Listener>();
let mutedCache: boolean | null = null;

async function loadMuted(): Promise<boolean> {
  if (mutedCache != null) return mutedCache;
  const raw = await AsyncStorage.getItem(MUTE_STORAGE_KEY);
  mutedCache = raw === "1";
  return mutedCache;
}

async function setMuted(v: boolean): Promise<void> {
  mutedCache = v;
  await AsyncStorage.setItem(MUTE_STORAGE_KEY, v ? "1" : "0");
  listeners.forEach((l) => l(v));
}

/**
 * Shared mute preference. Returns [enabled, setEnabled] — pass `true` to
 * un-mute, `false` to mute. Live-updates when flipped from anywhere.
 */
export function useGameSoundEnabled(): [boolean, (enabled: boolean) => Promise<void>] {
  const [muted, setLocalMuted] = useState<boolean>(mutedCache ?? false);
  useEffect(() => {
    let alive = true;
    loadMuted().then((v) => alive && setLocalMuted(v));
    const l: Listener = (v) => setLocalMuted(v);
    listeners.add(l);
    return () => {
      alive = false;
      listeners.delete(l);
    };
  }, []);
  const setEnabled = useCallback(async (next: boolean) => {
    await setMuted(!next);
  }, []);
  return [!muted, setEnabled];
}

interface PlayerBag {
  tap?: AudioPlayer;
  correct?: AudioPlayer;
  notQuite?: AudioPlayer;
  roundComplete?: AudioPlayer;
  gameComplete?: AudioPlayer;
}

/**
 * Preloads the five game SFX on mount and returns a `play` callback. Honors
 * the shared mute preference. Safe to call before web first-tap: on web we
 * delay player creation until the first invocation, which (by definition)
 * fires inside a user-gesture event handler.
 */
export function useGameSound() {
  const [enabled] = useGameSoundEnabled();
  const bagRef = useRef<PlayerBag>({});
  const unlockedRef = useRef(Platform.OS !== "web"); // native unlocks on first play too, but the audio API doesn't gate it

  useEffect(() => {
    // Allow the iPhone silent switch to mute the sounds — matches the
    // design rule and is the default most players expect from a game.
    setAudioModeAsync({ playsInSilentMode: false }).catch(() => {});
    if (Platform.OS !== "web") {
      // Native: safe to create the players immediately.
      createPlayers(bagRef.current);
    }
    return () => {
      Object.values(bagRef.current).forEach((p) => p?.release?.());
      bagRef.current = {};
    };
  }, []);

  const play = useCallback(
    (event: GameSoundEvent) => {
      if (!enabled) return;
      // Web unlock: create the players on first tap so the browser's
      // autoplay policy accepts the resulting playback.
      if (!unlockedRef.current && Object.keys(bagRef.current).length === 0) {
        createPlayers(bagRef.current);
        unlockedRef.current = true;
      }
      const p = bagRef.current[event];
      if (!p) return;
      try {
        p.seekTo?.(0);
        p.play?.();
      } catch {
        /* best-effort; audio failures must never break the game loop */
      }
    },
    [enabled]
  );

  return { play, enabled };
}

function createPlayers(bag: PlayerBag): void {
  (Object.keys(SOURCES) as GameSoundEvent[]).forEach((event) => {
    try {
      const player = createAudioPlayer(SOURCES[event]);
      // Quiet, consistent — never slot-machine loud.
      if (player && "volume" in player) {
        (player as any).volume = 0.5;
      }
      bag[event] = player;
    } catch {
      // Missing codec, denied permission, etc. — swallow; silence is a
      // valid fallback for an optional feature.
    }
  });
}
