import { Platform } from "react-native";

/**
 * Wearable Rest — native health-data bridge (PRD §12.2, §6.2 ENGINE-03).
 *
 * IMPORTANT — read before wiring this to a real device build:
 * Reading Apple HealthKit or Android Health Connect requires a native
 * module (e.g. `react-native-health` on iOS, `react-native-health-connect`
 * on Android) loaded via a custom EAS dev client. Expo Go CANNOT load
 * native health modules — there is no Expo Go-compatible path to a real
 * HealthKit/Health Connect read.
 *
 * This module defines the exact interface the rest of the app talks to
 * (`isAvailable`, `requestPermission`, `readLastNightSleepHours`) so that
 * swapping in the real native SDK later is a one-file change: implement
 * these three functions against the native module's actual API, and
 * nothing in settings.tsx or elsewhere needs to change.
 *
 * Until that native build exists, `readLastNightSleepHours` returns a
 * clearly-labeled simulated reading rather than silently pretending to be
 * real data — see `SIMULATED` below. Do not remove that flag without
 * actually wiring a native SDK call in its place.
 */

export type HealthProvider = "apple_health" | "health_connect";

export function preferredProvider(): HealthProvider {
  return Platform.OS === "ios" ? "apple_health" : "health_connect";
}

export function providerLabel(provider: HealthProvider): string {
  return provider === "apple_health" ? "Apple Health" : "Health Connect";
}

export async function isAvailable(): Promise<boolean> {
  // Real implementation: check native module presence, e.g.
  //   AppleHealthKit.isAvailable() on iOS, or
  //   initialize() from react-native-health-connect on Android.
  // Expo Go / this build: no native module is present, so this is always
  // reachable at the UI level, but downstream reads are simulated.
  return Platform.OS === "ios" || Platform.OS === "android";
}

export async function requestPermission(): Promise<boolean> {
  // Real implementation: AppleHealthKit.initHealthKit({ permissions: { read: ['SleepAnalysis'] } }, cb)
  // or Health Connect's requestPermission([{ accessType: 'read', recordType: 'SleepSession' }]).
  // This stub always grants, matching the "connect" flow being a real,
  // persisted app-level state even before a native SDK is wired in.
  return true;
}

// Marks readings that are not yet backed by a real native SDK call.
export const SIMULATED = true;

// What a device reading can carry. `sleepStart` / `sleepEnd` ("HH:MM",
// local time) let the behavioral twin notice irregular sleep timing; the
// simulated reading below deliberately leaves them out rather than invent
// a bedtime. A native build fills them from the sleep session's start/end.
export type NightReading = { hours: number; sleepStart?: string; sleepEnd?: string };

export async function readLastNight(): Promise<NightReading> {
  // TODO(native build): read the most recent sleep session and return its
  // duration plus its start and end clock times.
  return { hours: await readLastNightSleepHours() };
}

export async function readLastNightSleepHours(): Promise<number> {
  // TODO(native build): replace this with a real query, e.g.
  //   iOS:     AppleHealthKit.getSleepSamples({ startDate, endDate }, cb)
  //   Android: healthConnectClient.readRecords('SleepSession', { timeRangeFilter })
  // and sum session duration for the most recent night.
  //
  // Simulated reading: a plausible value in the 6-9h healthy range, so the
  // rest of the pipeline (confidence upgrade in the Rest domain, Weekly
  // Story's "wearable-synced" framing) can be exercised end-to-end today.
  const plausible = 6.5 + Math.random() * 2.5;
  return Math.round(plausible * 10) / 10;
}
