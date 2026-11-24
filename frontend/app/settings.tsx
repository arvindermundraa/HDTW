import React, { useEffect, useState } from "react";
import { View, StyleSheet, Pressable, ScrollView, Switch, Linking, ActivityIndicator, TextInput } from "react-native";
import * as Notifications from "expo-notifications";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Feather } from "@expo/vector-icons";
import { AppText, Button, Card, Pill } from "@/src/components/ui";
import { api } from "@/src/api";
import { colors, spacing } from "@/src/theme";
import * as Health from "@/src/native/health";
import { goBack } from "@/src/navigation";
import { useGameSoundEnabled } from "@/src/hooks/use-game-sound";

const NUDGE_NOTIFICATION_ID = "llhs-gentle-nudge";
const NUDGE_TIMES = ["08:00", "12:30", "19:00", "20:30"];

// Fixed, calm, pressure-free copy — owned entirely by the client so no
// server-side change could ever introduce urgency or streak language here.
const NUDGE_TITLE = "No pressure";
const NUDGE_BODY = "Want to jot down what you ate today? Totally optional, whenever works.";

export default function Settings() {
  const insets = useSafeAreaInsets();
  const router = useRouter();

  const [wearable, setWearable] = useState<{ connected: boolean; provider: string | null; last_sync: string | null }>({
    connected: false,
    provider: null,
    last_sync: null,
  });
  const [wearableBusy, setWearableBusy] = useState(false);

  const [nudgesEnabled, setNudgesEnabled] = useState(false);
  const [nudgeTime, setNudgeTime] = useState("19:00");
  const [nudgeBusy, setNudgeBusy] = useState(false);
  const [permissionDenied, setPermissionDenied] = useState(false);
  const [gameSoundEnabled, setGameSoundEnabled] = useGameSoundEnabled();

  // TAMU AI — mandatory, sole AI provider (see backend/tamus_client.py).
  // There's no on/off toggle any more: a saved key is used automatically.
  const [tamusModels, setTamusModels] = useState<any[]>([]);
  const [tamusHasKey, setTamusHasKey] = useState(false);
  const [tamusOnAdminPool, setTamusOnAdminPool] = useState(false);
  const [tamusAiAvailable, setTamusAiAvailable] = useState(false);
  const [tamusModelChat, setTamusModelChat] = useState("");
  const [tamusKeyInput, setTamusKeyInput] = useState("");
  const [tamusBusy, setTamusBusy] = useState(false);
  const [tamusTestResult, setTamusTestResult] = useState<{ ok: boolean; message: string } | null>(null);

  useEffect(() => {
    api.getWearableStatus().then(setWearable).catch(() => {});
    api.getNudgeSettings().then((d: any) => {
      setNudgesEnabled(d.enabled);
      setNudgeTime(d.time);
    }).catch(() => {});
    api.getTamusModels().then((d: any) => setTamusModels(d.models)).catch(() => {});
    api.getTamusSettings().then((d: any) => {
      setTamusHasKey(d.has_key);
      setTamusOnAdminPool(d.on_admin_pool);
      setTamusAiAvailable(d.ai_available);
      setTamusModelChat(d.model_chat);
    }).catch(() => {});
  }, []);

  const connectWearable = async () => {
    setWearableBusy(true);
    try {
      const provider = Health.preferredProvider();
      const granted = await Health.requestPermission();
      if (!granted) {
        setWearableBusy(false);
        return;
      }
      const state = await api.connectWearable(provider as any);
      setWearable(state);
      // Bridge the first reading immediately so the Rest domain has
      // something to work with right away (Health.SIMULATED — see
      // native/health.ts for exactly where a real native SDK call
      // replaces this).
      const night = await Health.readLastNight();
      await api.syncWearable(night.hours, undefined, undefined,
        night.sleepStart && night.sleepEnd ? { sleep_start: night.sleepStart, sleep_end: night.sleepEnd } : undefined);
      const fresh = await api.getWearableStatus();
      setWearable(fresh);
    } finally {
      setWearableBusy(false);
    }
  };

  const disconnectWearable = async () => {
    setWearableBusy(true);
    try {
      const state = await api.disconnectWearable();
      setWearable(state);
    } finally {
      setWearableBusy(false);
    }
  };

  const cancelNudges = async () => {
    try {
      await Notifications.cancelScheduledNotificationAsync(NUDGE_NOTIFICATION_ID);
    } catch {
      // nothing scheduled — fine
    }
  };

  const scheduleNudges = async (time: string) => {
    await cancelNudges();
    const [hour, minute] = time.split(":").map(Number);
    await Notifications.scheduleNotificationAsync({
      identifier: NUDGE_NOTIFICATION_ID,
      content: { title: NUDGE_TITLE, body: NUDGE_BODY, sound: false },
      trigger: {
        type: Notifications.SchedulableTriggerInputTypes.DAILY,
        hour,
        minute,
      },
    });
  };

  const toggleNudges = async (value: boolean) => {
    setPermissionDenied(false);
    if (value) {
      const perm = await Notifications.requestPermissionsAsync();
      if (!perm.granted) {
        setPermissionDenied(true);
        return;
      }
    }
    setNudgeBusy(true);
    try {
      await api.updateNudgeSettings(value, nudgeTime);
      setNudgesEnabled(value);
      if (value) {
        await scheduleNudges(nudgeTime);
      } else {
        await cancelNudges();
      }
    } finally {
      setNudgeBusy(false);
    }
  };

  const changeNudgeTime = async (time: string) => {
    setNudgeTime(time);
    setNudgeBusy(true);
    try {
      await api.updateNudgeSettings(nudgesEnabled, time);
      if (nudgesEnabled) await scheduleNudges(time);
    } finally {
      setNudgeBusy(false);
    }
  };

  // ---------- TAMU AI (mandatory) ----------
  // `fetch` throws `TypeError: Failed to fetch` when the browser can't reach
  // the backend (network down, CORS strip from a 500, server not running).
  // Returning that as the on-screen message doesn't help the student; this
  // helper turns it into something plain-English and keeps the backend's own
  // error text when we actually got a response.
  const friendlyError = (e: unknown): string => {
    const msg = e instanceof Error ? e.message : String(e);
    // The browser's own message when fetch itself fails is "Failed to fetch"
    // (Chrome) or "Load failed" / "NetworkError when attempting to fetch
    // resource." (Safari / Firefox). Anything matching these is a transport
    // failure, not a backend answer.
    if (/failed to fetch|load failed|network/i.test(msg)) {
      return "Couldn't reach the server. Check your connection and try again.";
    }
    return msg;
  };

  const saveTamusKey = async () => {
    if (tamusKeyInput.trim().length < 8) return;
    setTamusBusy(true);
    setTamusTestResult(null);
    try {
      const res = await api.updateTamusSettings({
        api_key: tamusKeyInput.trim(),
        model_chat: tamusModelChat || undefined,
      });
      setTamusHasKey(res.has_key);
      setTamusOnAdminPool(res.on_admin_pool);
      setTamusAiAvailable(res.ai_available);
      setTamusModelChat(res.model_chat);
      setTamusKeyInput("");
    } catch (e) {
      // Do not include the key in the error message or the console.
      setTamusTestResult({ ok: false, message: friendlyError(e) });
    } finally {
      setTamusBusy(false);
    }
  };

  const changeTamusModel = async (modelId: string) => {
    setTamusModelChat(modelId);
    setTamusBusy(true);
    try {
      await api.updateTamusSettings({ model_chat: modelId });
    } finally {
      setTamusBusy(false);
    }
  };

  const clearTamus = async () => {
    setTamusBusy(true);
    try {
      const res = await api.clearTamusSettings();
      setTamusHasKey(res.has_key);
      setTamusOnAdminPool(res.on_admin_pool);
      setTamusAiAvailable(res.ai_available);
      setTamusTestResult(null);
    } finally {
      setTamusBusy(false);
    }
  };

  const testTamus = async () => {
    setTamusBusy(true);
    setTamusTestResult(null);
    try {
      const res = await api.testTamusConnection();
      setTamusTestResult(res);
    } catch (e) {
      // Network / CORS / timeout failure — surfaces as the same card the
      // backend's own {ok, message} answer uses, so there is no red screen
      // and the Test button clears itself.
      setTamusTestResult({ ok: false, message: friendlyError(e) });
    } finally {
      setTamusBusy(false);
    }
  };

  const tamusByProvider: Record<string, any[]> = {};
  for (const m of tamusModels) {
    (tamusByProvider[m.provider] ||= []).push(m);
  }

  return (
    <View style={styles.c} testID="settings-screen">
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <AppText variant="title">Settings</AppText>
        <Pressable onPress={() => goBack(router, "/profile")} hitSlop={10} testID="settings-close">
          <Feather name="x" size={26} color={colors.onSurface} />
        </Pressable>
      </View>

      <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
        {/* Profile survey — reuses the onboarding screen in edit mode */}
        <AppText variant="label" style={{ marginBottom: spacing.sm }}>
          PROFILE
        </AppText>
        <Pressable
          onPress={() => router.push({ pathname: "/onboarding", params: { mode: "edit" } })}
          testID="settings-edit-profile"
        >
          <Card>
            <View style={styles.rowBetween}>
              <View style={{ flex: 1 }}>
                <AppText variant="body" color={colors.onSurface}>
                  Edit my profile
                </AppText>
                <AppText variant="caption" style={{ marginTop: 4 }}>
                  Update your Nutrition & Lifestyle answers — kitchen setup, dietary restrictions, and more.
                </AppText>
              </View>
              <Feather name="chevron-right" size={20} color={colors.muted} />
            </View>
          </Card>
        </Pressable>

        <Pressable
          onPress={() => router.push({ pathname: "/avatar", params: { mode: "edit" } })}
          testID="settings-edit-avatar"
          style={{ marginTop: spacing.md }}
        >
          <Card>
            <View style={styles.rowBetween}>
              <View style={{ flex: 1 }}>
                <AppText variant="body" color={colors.onSurface}>
                  Your avatar
                </AppText>
                <AppText variant="caption" style={{ marginTop: 4 }}>
                  Change your avatar's skin tone, hair, face, glasses, outfit and background any time.
                </AppText>
              </View>
              <Feather name="chevron-right" size={20} color={colors.muted} />
            </View>
          </Card>
        </Pressable>

        {/* Wearable Rest */}
        <AppText variant="label" style={{ marginTop: spacing.xl, marginBottom: spacing.sm }}>
          REST
        </AppText>
        <Card>
          <View style={styles.rowBetween}>
            <View style={{ flex: 1 }}>
              <AppText variant="body" color={colors.onSurface}>
                {Health.providerLabel(Health.preferredProvider())}
              </AppText>
              <AppText variant="caption" style={{ marginTop: 4 }}>
                {wearable.connected
                  ? "Connected — sleep is a high-confidence reading."
                  : "Not connected — sleep is a manual, low-confidence guess."}
              </AppText>
            </View>
            {wearableBusy ? (
              <ActivityIndicator color={colors.brandPrimary} />
            ) : (
              <Switch
                value={wearable.connected}
                onValueChange={(v) => (v ? connectWearable() : disconnectWearable())}
                trackColor={{ true: colors.brandPrimary, false: colors.surfaceTertiary }}
                thumbColor="#fff"
                testID="wearable-toggle"
              />
            )}
          </View>
          {wearable.connected && wearable.last_sync && (
            <AppText variant="caption" style={{ marginTop: spacing.sm }}>
              Last synced {new Date(wearable.last_sync).toLocaleDateString()}
            </AppText>
          )}
        </Card>
        <AppText variant="caption" style={{ marginTop: spacing.sm }}>
          Manual sleep entry always stays available in Log → Rest, whether or not a wearable is connected.
        </AppText>

        {/* Gentle Nudges */}
        <AppText variant="label" style={{ marginTop: spacing.xl, marginBottom: spacing.sm }}>
          GENTLE NUDGES
        </AppText>
        <Card>
          <View style={styles.rowBetween}>
            <View style={{ flex: 1 }}>
              <AppText variant="body" color={colors.onSurface}>
                Meal-log reminder
              </AppText>
              <AppText variant="caption" style={{ marginTop: 4 }}>
                A soft, optional nudge — never a streak or a penalty.
              </AppText>
            </View>
            {nudgeBusy ? (
              <ActivityIndicator color={colors.brandPrimary} />
            ) : (
              <Switch
                value={nudgesEnabled}
                onValueChange={toggleNudges}
                trackColor={{ true: colors.brandPrimary, false: colors.surfaceTertiary }}
                thumbColor="#fff"
                testID="nudges-toggle"
              />
            )}
          </View>

          {nudgesEnabled && (
            <View style={{ marginTop: spacing.lg }}>
              <AppText variant="caption" style={{ marginBottom: spacing.sm }}>
                When?
              </AppText>
              <View style={styles.chipRow}>
                {NUDGE_TIMES.map((t) => (
                  <Pill key={t} label={to12h(t)} active={nudgeTime === t} onPress={() => changeNudgeTime(t)} testID={`nudge-time-${t}`} />
                ))}
              </View>
            </View>
          )}
        </Card>

        {permissionDenied && (
          <Card style={{ marginTop: spacing.md, backgroundColor: colors.surfaceTertiary }}>
            <AppText variant="body">Notifications are off for this app, so gentle nudges can't be scheduled.</AppText>
            <Button title="Open Settings" variant="secondary" onPress={() => Linking.openSettings()} style={{ marginTop: spacing.md }} testID="open-notif-settings" />
          </Card>
        )}

        {/* Game sounds — short 8-bit effects used only inside the mini-games.
            Flipping this stays in sync with the mute button in the game header
            and is the same preference across sessions. */}
        <AppText variant="label" style={{ marginTop: spacing.xl, marginBottom: spacing.sm }}>
          GAMES
        </AppText>
        <Card>
          <View style={styles.rowBetween}>
            <View style={{ flex: 1 }}>
              <AppText variant="body" color={colors.onSurface}>
                Game sounds
              </AppText>
              <AppText variant="caption" style={{ marginTop: 4 }}>
                Short 8-bit effects inside the practice games — same every time, never a slot-machine jingle.
              </AppText>
            </View>
            <Switch
              value={gameSoundEnabled}
              onValueChange={(v) => setGameSoundEnabled(v)}
              trackColor={{ true: colors.brandPrimary, false: colors.surfaceTertiary }}
              thumbColor="#fff"
              testID="game-sounds-toggle"
            />
          </View>
        </Card>

        {/* TAMU AI (required) */}
        <AppText variant="label" style={{ marginTop: spacing.xl, marginBottom: spacing.sm }}>
          AI ASSISTANT — REQUIRED SETUP
        </AppText>
        <Card>
          <View style={{ flex: 1 }}>
            <AppText variant="body" color={colors.onSurface}>
              {tamusAiAvailable ? "TAMU AI is connected" : "Add your TAMU AI key to chat with Future Me"}
            </AppText>
            <AppText variant="caption" style={{ marginTop: 4 }}>
              {tamusOnAdminPool
                ? "This account is on TAU's shared testing key — you don't need to add your own, but you can if you'd like to use your personal TAMU credit instead."
                : "TAMU AI powers Future Me's conversation and the wording of its what-if answers, photo/text meal-log assist, and the dining chat helper — nothing else in the app runs the AI. TAMU gives each student a $5 AI credit; there's no other assistant to fall back to, so these features won't respond until your key is added here."}
            </AppText>
          </View>

          <View style={{ marginTop: spacing.lg }}>
            <AppText variant="caption" style={{ marginBottom: spacing.sm }}>
              {tamusHasKey ? "TAMU API key saved. Enter a new one to replace it." : "TAMU API key"}
            </AppText>
            <TextInput
              value={tamusKeyInput}
              onChangeText={setTamusKeyInput}
              placeholder="Paste your TAMU Chat API key"
              placeholderTextColor={colors.muted}
              secureTextEntry
              autoCapitalize="none"
              autoCorrect={false}
              style={styles.keyInput}
              testID="tamus-key-input"
            />
            <Button
              title="Save key"
              variant="secondary"
              onPress={saveTamusKey}
              disabled={tamusKeyInput.trim().length < 8 || tamusBusy}
              style={{ marginTop: spacing.sm }}
              testID="tamus-save-key"
            />
          </View>

          {tamusHasKey && (
            <View style={{ marginTop: spacing.lg }}>
              <AppText variant="caption" style={{ marginBottom: spacing.sm }}>
                Chat model
              </AppText>
              {/* One wrapping chip row per provider, so every model stays
                  visible on narrow screens (no hidden horizontal overflow). */}
              <View style={{ gap: spacing.md }}>
                {Object.entries(tamusByProvider).map(([provider, models]) => (
                  <View key={provider}>
                    <AppText variant="caption" style={{ marginBottom: 4, opacity: 0.6 }}>
                      {provider}
                    </AppText>
                    <View style={styles.chipRow}>
                      {models.map((m) => (
                        <Pill
                          key={m.id}
                          label={m.display_name}
                          active={tamusModelChat === m.id}
                          onPress={() => changeTamusModel(m.id)}
                          testID={`tamus-model-${m.id}`}
                        />
                      ))}
                    </View>
                  </View>
                ))}
              </View>

              <View style={{ flexDirection: "row", gap: spacing.sm, marginTop: spacing.lg }}>
                <Button title="Test connection" variant="secondary" onPress={testTamus} disabled={tamusBusy} style={{ flex: 1 }} testID="tamus-test" />
                <Button title="Remove key" variant="secondary" onPress={clearTamus} disabled={tamusBusy} style={{ flex: 1 }} testID="tamus-clear" />
              </View>

              {tamusTestResult && (
                <AppText
                  variant="caption"
                  color={tamusTestResult.ok ? colors.brandPrimary : colors.warning}
                  style={{ marginTop: spacing.sm }}
                  testID="tamus-test-result"
                >
                  {tamusTestResult.ok ? `Connected: "${tamusTestResult.message}"` : tamusTestResult.message}
                </AppText>
              )}
            </View>
          )}
        </Card>

        <View style={{ height: spacing["3xl"] }} />
      </ScrollView>
    </View>
  );
}

function to12h(t: string) {
  const [h, m] = t.split(":").map(Number);
  const period = h >= 12 ? "PM" : "AM";
  const h12 = h % 12 === 0 ? 12 : h % 12;
  return `${h12}:${m.toString().padStart(2, "0")} ${period}`;
}

const styles = StyleSheet.create({
  c: { flex: 1, backgroundColor: colors.surface },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingHorizontal: spacing.xl,
    paddingBottom: spacing.md,
  },
  scroll: { paddingHorizontal: spacing.xl, paddingBottom: spacing["3xl"] },
  rowBetween: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  chipRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  keyInput: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 10,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md,
    color: colors.onSurface,
    backgroundColor: colors.surface,
  },
});
