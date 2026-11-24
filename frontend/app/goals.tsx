import React, { useEffect, useState } from "react";
import { View, StyleSheet, ScrollView, Pressable, ActivityIndicator } from "react-native";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Feather } from "@expo/vector-icons";
import { AppText, Button } from "@/src/components/ui";
import { IconCircle, cardStyle } from "@/src/components/llhs";
import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { DOMAIN, DOMAINS, Domain, FOOD_OPTIONS, GoalSnapshot, suggestedFoodCategory } from "@/src/daily-goals";
import { colors, radius, spacing } from "@/src/theme";
import { goBack } from "@/src/navigation";

// Daily ring goals. A participant's first goal for a ring starts today;
// changing or pausing an existing one takes effect tomorrow, so today's
// ring never jumps around mid-day (enforced by the backend too).
type Draft = { enabled: boolean; target: number; category: string; existed: boolean; wasEnabled: boolean; startsTomorrow: boolean };

export default function Goals() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user, refresh } = useAuth();
  const initialSchedule = user?.sleep_schedule ?? { bedtime: "23:00", wake: "07:00" };
  const [schedule, setSchedule] = useState(initialSchedule);
  const [drafts, setDrafts] = useState<Record<Domain, Draft> | null>(null);
  const [initial, setInitial] = useState<Record<Domain, Draft> | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .getDailyGoals()
      .catch(() => null)
      .then((snap: GoalSnapshot | null) => {
        const today = snap?.days?.[snap.days.length - 1]?.goals ?? [];
        const next = {} as Record<Domain, Draft>;
        for (const d of DOMAINS) {
          const pending = snap?.pending?.find((p) => p.domain === d);
          const active = today.find((g) => g.domain === d);
          const src = pending ?? active;
          const enabled = pending ? pending.enabled : !!active;
          next[d] = {
            enabled: src ? enabled : true,
            target: (src?.target as number) ?? DOMAIN[d].defaultTarget,
            category: (src?.category as string) ?? suggestedFoodCategory(user?.focus_areas),
            existed: !!(active || pending),
            wasEnabled: enabled,
            startsTomorrow: !!pending,
          };
        }
        setDrafts(next);
        setInitial(next);
      });
  }, [user?.focus_areas]);

  if (!drafts || !initial) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color={colors.brandPrimary} />
      </View>
    );
  }

  const update = (d: Domain, patch: Partial<Draft>) => setDrafts({ ...drafts, [d]: { ...drafts[d], ...patch } });
  const step = (d: Domain, dir: 1 | -1) => {
    const m = DOMAIN[d];
    const v = Math.round((drafts[d].target + dir * m.step) * 2) / 2;
    update(d, { target: Math.min(m.max, Math.max(m.min, v)) });
  };

  const save = async () => {
    setSaving(true);
    setError("");
    try {
      for (const d of DOMAINS) {
        const now = drafts[d];
        const was = initial[d];
        const changed = now.target !== was.target || (d === "food" && now.category !== was.category) || now.enabled !== was.wasEnabled || !was.existed;
        if (!changed) continue;
        if (now.enabled) {
          // Food's target is always 1 — the ring is binary (filled once a meal
          // is logged). Only the chosen food group varies.
          const target = d === "food" ? 1 : now.target;
          await api.setDailyGoal(d, { target, category: d === "food" ? now.category : undefined });
        } else if (was.existed && was.wasEnabled) {
          await api.pauseDailyGoal(d);
        }
      }
      if (!user?.sleep_schedule || schedule.bedtime !== initialSchedule.bedtime || schedule.wake !== initialSchedule.wake) {
        await api.setSleepSchedule(schedule.bedtime, schedule.wake);
        await refresh();
      }
      goBack(router, "/");
    } catch (e: any) {
      setError(e?.message || "Couldn't save your goals. Try again.");
    } finally {
      setSaving(false);
    }
  };

  const anyExisting = DOMAINS.some((d) => initial[d].existed);

  return (
    <View style={styles.c} testID="goals-screen">
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <AppText variant="display">
          Daily goals
        </AppText>
        <Pressable onPress={() => goBack(router, "/")} hitSlop={10} accessibilityLabel="Close" testID="goals-close">
          <Feather name="x" size={26} color={colors.onSurface} />
        </Pressable>
      </View>
      <ScrollView contentContainerStyle={{ paddingHorizontal: spacing.xl, paddingBottom: spacing["3xl"], gap: spacing.lg }}>
        <AppText variant="body">
          Pick a small daily target for each ring. Your logs fill them in, and they reset every morning.
          {anyExisting ? " Changes to a goal you already have start tomorrow." : ""}
        </AppText>

        {DOMAINS.map((d) => {
          const m = DOMAIN[d];
          const dr = drafts[d];
          return (
            <View key={d} style={[cardStyle, { gap: spacing.md, padding: spacing.lg }, !dr.enabled && { opacity: 0.7 }]} testID={`goal-${d}`}>
              <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.md }}>
                <IconCircle icon={m.icon} color={m.text} tint={m.pale} size={40} iconSize={19} />
                <View style={{ flex: 1 }}>
                  <AppText variant="subtitle" style={{ fontSize: 17 }}>
                    {m.name}
                  </AppText>
                  {initial[d].startsTomorrow && (
                    <AppText variant="caption" style={{ fontSize: 12 }}>
                      Your change starts tomorrow
                    </AppText>
                  )}
                </View>
                <Pressable
                  onPress={() => update(d, { enabled: !dr.enabled })}
                  style={[styles.toggle, dr.enabled && { backgroundColor: m.color }]}
                  accessibilityRole="switch"
                  accessibilityState={{ checked: dr.enabled }}
                  accessibilityLabel={`${m.name} ring on`}
                  testID={`goal-${d}-toggle`}
                >
                  <View style={[styles.knob, dr.enabled && { transform: [{ translateX: 20 }] }]} />
                </Pressable>
              </View>

              {dr.enabled && (
                <>
                  {d === "food" ? (
                    <View style={{ gap: spacing.sm }}>
                      <AppText variant="label" color={colors.onSurfaceSecondary}>
                        A food group you&apos;d like to add
                      </AppText>
                      <AppText variant="caption">
                        No required number of meals — the ring fills as soon as you log one.
                      </AppText>
                      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginTop: 2 }}>
                        {FOOD_OPTIONS.map((o) => {
                          const on = dr.category === o.id;
                          return (
                            <Pressable
                              key={o.id}
                              onPress={() => update(d, { category: o.id })}
                              style={[styles.chip, on && { backgroundColor: m.color, borderColor: m.color }]}
                              testID={`goal-food-${o.id}`}
                            >
                              <AppText variant="label" color={on ? "#FFFFFF" : colors.onSurface} style={{ fontSize: 13 }}>
                                {o.label}
                              </AppText>
                            </Pressable>
                          );
                        })}
                      </View>
                    </View>
                  ) : (
                    <>
                      <View style={styles.stepper}>
                        <Pressable onPress={() => step(d, -1)} style={styles.stepBtn} accessibilityLabel={`Less ${m.name}`} testID={`goal-${d}-minus`}>
                          <Feather name="minus" size={20} color={colors.onSurface} />
                        </Pressable>
                        <View style={{ alignItems: "center" }}>
                          <AppText variant="display" style={{ fontSize: 26, lineHeight: 30 }}>
                            {dr.target}
                          </AppText>
                          <AppText variant="caption">
                            {d === "move" ? "minutes a day" : "hours a night"}
                          </AppText>
                        </View>
                        <Pressable onPress={() => step(d, 1)} style={styles.stepBtn} accessibilityLabel={`More ${m.name}`} testID={`goal-${d}-plus`}>
                          <Feather name="plus" size={20} color={colors.onSurface} />
                        </Pressable>
                      </View>
                      {d === "rest" && (
                        <View style={{ gap: spacing.sm }} testID="sleep-schedule">
                          <AppText variant="label" color={colors.onSurfaceSecondary}>
                            Your usual sleep schedule
                          </AppText>
                          <AppText variant="caption">
                            Sleep is a morning check-in: you log last night after you wake up, so the ring never counts as behind during the day.
                          </AppText>
                          <TimeStepper label="Bedtime" value={schedule.bedtime} onChange={(v) => setSchedule({ ...schedule, bedtime: v })} testID="sleep-bedtime" />
                          <TimeStepper label="Wake up" value={schedule.wake} onChange={(v) => setSchedule({ ...schedule, wake: v })} testID="sleep-wake" />
                        </View>
                      )}
                    </>
                  )}
                </>
              )}
            </View>
          );
        })}

        {!!error && (
          <AppText variant="caption" color={colors.error}>
            {error}
          </AppText>
        )}
        <Button title="Save goals" onPress={save} loading={saving} testID="goals-save" />
      </ScrollView>
    </View>
  );
}

// "23:30" ± 30 minutes, wrapping around midnight; shown as "11:30 PM".
function TimeStepper({ label, value, onChange, testID }: { label: string; value: string; onChange: (v: string) => void; testID: string }) {
  const [h, m] = value.split(":").map(Number);
  const shift = (dir: 1 | -1) => {
    const mins = (((h * 60 + m + dir * 30) % 1440) + 1440) % 1440;
    onChange(`${String(Math.floor(mins / 60)).padStart(2, "0")}:${String(mins % 60).padStart(2, "0")}`);
  };
  const shown = `${((h + 11) % 12) + 1}:${String(m).padStart(2, "0")} ${h < 12 ? "AM" : "PM"}`;
  return (
    <View style={[styles.stepper, { paddingVertical: 4 }]} testID={testID}>
      <Pressable onPress={() => shift(-1)} style={[styles.stepBtn, { width: 40, height: 40 }]} accessibilityLabel={`${label} earlier`}>
        <Feather name="minus" size={18} color={colors.onSurface} />
      </Pressable>
      <View style={{ alignItems: "center" }}>
        <AppText variant="caption">{label}</AppText>
        <AppText variant="subtitle" style={{ fontSize: 17 }}>
          {shown}
        </AppText>
      </View>
      <Pressable onPress={() => shift(1)} style={[styles.stepBtn, { width: 40, height: 40 }]} accessibilityLabel={`${label} later`}>
        <Feather name="plus" size={18} color={colors.onSurface} />
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  c: { flex: 1, backgroundColor: colors.surface },
  center: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.surface },
  header: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingHorizontal: spacing.xl, paddingBottom: spacing.md },
  toggle: { width: 48, height: 28, borderRadius: 14, backgroundColor: colors.borderStrong, padding: 3 },
  knob: { width: 22, height: 22, borderRadius: 11, backgroundColor: "#FFFFFF" },
  chip: { paddingHorizontal: 12, paddingVertical: 8, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary },
  stepper: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", backgroundColor: colors.surfaceTertiary, borderRadius: radius.md, padding: spacing.sm },
  stepBtn: { width: 48, height: 48, borderRadius: 24, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center" },
});
