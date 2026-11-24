import React, { useCallback, useState } from "react";
import { View, StyleSheet, ScrollView, Pressable, ActivityIndicator } from "react-native";
import { useRouter, useFocusEffect } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Feather } from "@expo/vector-icons";
import { AppText, Button } from "@/src/components/ui";
import { IconCircle, cardStyle } from "@/src/components/llhs";
import { ProgramUnitCard } from "@/src/components/ProgramUnit";
import { api, Program, ProgramUnit } from "@/src/api";
import { colors, domain, spacing, radius } from "@/src/theme";

// Learn — the 8-week program, one unit per week (backend/program.py), not an
// open library: this week's unit leads, earlier weeks stay open for review,
// and later weeks show when they open. Each unit is Watch → Practice → Do it
// → Reflect.
const shortDate = (iso: string) => {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("en-US", { month: "short", day: "numeric" });
};

export default function Learn() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [program, setProgram] = useState<Program | null>(null);
  const [error, setError] = useState(false);
  const [openWeek, setOpenWeek] = useState<number | null>(null);

  const load = useCallback(async () => {
    try {
      setProgram(await api.getProgram());
      setError(false);
    } catch {
      setError(true);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  if (!program) {
    return (
      <View style={[styles.center, { paddingHorizontal: spacing.xl }]} testID={error ? "learn-error" : "learn-loading"}>
        {error ? (
          <>
            <Feather name="cloud-off" size={28} color={colors.muted} />
            <AppText variant="subtitle" style={{ marginTop: spacing.md, textAlign: "center" }}>
              We couldn&apos;t load Learn right now
            </AppText>
            <Button title="Try again" onPress={load} style={{ marginTop: spacing.xl, paddingHorizontal: spacing["2xl"] }} testID="learn-retry" />
          </>
        ) : (
          <ActivityIndicator color={colors.brandPrimary} size="large" />
        )}
      </View>
    );
  }

  const now = program.current_week;
  const current = program.units.find((u) => u.week === now)!;
  const earlier = program.units.filter((u) => u.week < now).sort((a, b) => b.week - a.week);
  const later = program.units.filter((u) => u.week > now);

  return (
    <ScrollView style={styles.c} contentContainerStyle={{ paddingBottom: 120 }} showsVerticalScrollIndicator={false} testID="learn-screen">
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <AppText variant="display">Learn</AppText>
        <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.md, marginTop: spacing.sm }}>
          <AppText variant="label" color={colors.brandPrimary} testID="learn-week">
            Week {now} of {program.weeks}
          </AppText>
          <View style={styles.track}>
            <View style={[styles.fill, { width: `${(now / program.weeks) * 100}%` }]} />
          </View>
        </View>
      </View>

      <View style={{ paddingHorizontal: spacing.xl, gap: spacing.lg }}>
        <View style={{ gap: spacing.sm }}>
          <AppText variant="label" color={colors.muted} style={{ letterSpacing: 1 }}>
            THIS WEEK
          </AppText>
          <ProgramUnitCard unit={current} onChange={setProgram} testID="learn-current-unit" />
        </View>

        {earlier.length > 0 && (
          <View style={{ gap: spacing.sm }}>
            <AppText variant="label" color={colors.muted} style={{ letterSpacing: 1 }}>
              EARLIER WEEKS
            </AppText>
            {earlier.map((u) =>
              openWeek === u.week ? (
                <ProgramUnitCard key={u.week} unit={u} onChange={setProgram} compact />
              ) : (
                <UnitRow key={u.week} unit={u} onPress={() => setOpenWeek(u.week)} />
              )
            )}
          </View>
        )}

        {later.length > 0 && (
          <View style={{ gap: spacing.sm }}>
            <AppText variant="label" color={colors.muted} style={{ letterSpacing: 1 }}>
              COMING UP
            </AppText>
            {later.map((u) => (
              <UnitRow key={u.week} unit={u} />
            ))}
          </View>
        )}

        {/* Practice beyond the weekly unit: still easy to find */}
        <View style={{ gap: spacing.sm }}>
          <AppText variant="label" color={colors.muted} style={{ letterSpacing: 1 }}>
            MORE TO EXPLORE
          </AppText>
          <View style={{ flexDirection: "row", gap: 10 }}>
            <Pressable onPress={() => router.push("/build-meal")} style={[cardStyle, styles.more]} testID="learn-build-meal">
              <IconCircle icon="grid" color={domain.food.text} tint={domain.food.tint} size={36} iconSize={17} />
              <AppText variant="subtitle" style={{ fontSize: 15 }}>
                Build a meal
              </AppText>
              <AppText variant="caption">From today&apos;s dining menu</AppText>
            </Pressable>
            <Pressable onPress={() => router.push("/(tabs)/social")} style={[cardStyle, styles.more]} testID="learn-wings">
              <IconCircle icon="users" color={colors.brandPrimary} tint={colors.surfaceTertiary} size={36} iconSize={17} />
              <AppText variant="subtitle" style={{ fontSize: 15 }}>
                Wings
              </AppText>
              <AppText variant="caption">Team up on a shared goal</AppText>
            </Pressable>
          </View>
          <View style={[cardStyle, styles.soon]} testID="learn-recipes">
            <IconCircle icon="book" color={colors.muted} tint={colors.surfaceTertiary} size={36} iconSize={17} />
            <View style={{ flex: 1 }}>
              <AppText variant="subtitle" style={{ fontSize: 15 }} color={colors.muted}>
                Recipe library
              </AppText>
              <AppText variant="caption">Coming soon</AppText>
            </View>
          </View>
        </View>
      </View>
    </ScrollView>
  );
}

function UnitRow({ unit, onPress }: { unit: ProgramUnit; onPress?: () => void }) {
  const upcoming = !unit.available;
  return (
    <Pressable onPress={onPress} disabled={!onPress} style={[cardStyle, styles.unitRow]} testID={`unit-row-${unit.week}`}>
      <View style={[styles.weekBadge, upcoming && { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border }]}>
        <AppText variant="label" color={upcoming ? colors.muted : colors.brandPrimary}>
          {unit.week}
        </AppText>
      </View>
      <View style={{ flex: 1 }}>
        <AppText variant="subtitle" style={{ fontSize: 15 }} color={upcoming ? colors.onSurfaceSecondary : colors.onSurface}>
          {unit.title}
        </AppText>
        <AppText variant="caption">
          {upcoming
            ? `Coming in Week ${unit.week} · ${shortDate(unit.opens_on)}`
            : unit.status === "done"
              ? "Done · tap to review"
              : `${unit.steps_done} of ${unit.steps_total} done · tap to open`}
        </AppText>
      </View>
      {unit.status === "done" ? (
        <Feather name="check-circle" size={18} color={colors.brandPrimary} />
      ) : onPress ? (
        <Feather name="chevron-down" size={18} color={colors.muted} />
      ) : null}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  c: { flex: 1, backgroundColor: colors.surface },
  center: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.surface },
  header: { paddingHorizontal: spacing.xl, paddingBottom: spacing.lg },
  track: { flex: 1, height: 6, borderRadius: 3, backgroundColor: colors.surfaceTertiary, overflow: "hidden" },
  fill: { height: 6, borderRadius: 3, backgroundColor: colors.brandPrimary },
  unitRow: { flexDirection: "row", alignItems: "center", gap: spacing.md, paddingVertical: spacing.md },
  weekBadge: {
    width: 36,
    height: 36,
    borderRadius: radius.md,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.surfaceTertiary,
  },
  more: { flex: 1, gap: spacing.sm, padding: spacing.lg },
  soon: { flexDirection: "row", alignItems: "center", gap: spacing.md, paddingVertical: spacing.md },
});
