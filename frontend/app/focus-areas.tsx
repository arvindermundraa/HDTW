import React, { useEffect, useState } from "react";
import { View, StyleSheet, ScrollView, Pressable, ActivityIndicator, TextInput } from "react-native";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Feather } from "@expo/vector-icons";
import { AppText, Button, Card } from "@/src/components/ui";
import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { colors, spacing, radius, fonts, fontSize } from "@/src/theme";
import { goBack } from "@/src/navigation";

// Choosing a focus area ("Updated HEI for LLHS"): HEI-2020's 13 components
// form eight focus areas, and a participant works on ONE at a time. After
// the baseline results (week 1) they choose an area with room for
// improvement, then set a goal and an action plan. After the week 4 results
// (week 5) they keep it or change it and revise the goal. The list comes
// from the server, most room first; no scores ever reach this screen.
type Area = { id: string; label: string; description: string; suggested?: boolean };

export default function FocusAreas() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { refresh } = useAuth();
  const [candidates, setCandidates] = useState<Area[] | null>(null);
  const [current, setCurrent] = useState<Area | null>(null);
  const [saved, setSaved] = useState({ goal: "", plan: "" });
  const [hasAssessment, setHasAssessment] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [goal, setGoal] = useState("");
  const [plan, setPlan] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const load = () => {
    setLoadError(false);
    setCandidates(null);
    api
      .getFocusCandidates()
      .then((d: any) => {
        setHasAssessment(d.has_assessment !== false);
        setCandidates(d.candidates || []);
        setCurrent(d.current || null);
        setSelected(d.current?.id ?? d.candidates?.[0]?.id ?? null);
        setSaved({ goal: d.goal || "", plan: d.plan || "" });
        setGoal(d.goal || "");
        setPlan(d.plan || "");
      })
      .catch(() => setLoadError(true));
  };

  useEffect(() => {
    load();
  }, []);

  // The current area stays choosable ("keep it") even once it's no longer
  // among the areas with the most room.
  const options: Area[] = candidates
    ? current && !candidates.some((c) => c.id === current.id)
      ? [current, ...candidates]
      : candidates
    : [];
  const keeping = !!current && selected === current.id;

  const pick = (id: string) => {
    if (id === selected) return;
    setSelected(id);
    // A goal belongs to its area: start fresh when switching, restore when coming back.
    const back = current?.id === id;
    setGoal(back ? saved.goal : "");
    setPlan(back ? saved.plan : "");
  };

  const submit = async () => {
    if (!selected) {
      setError("Choose an area to focus on.");
      return;
    }
    if (!goal.trim()) {
      setError("Write a short goal for this area.");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      await api.setFocusAreas(selected, goal.trim(), plan.trim());
      await refresh();
      goBack(router, "/");
    } catch (e: any) {
      setError(e.message || "Something went wrong. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  const chosen = options.find((o) => o.id === selected);

  return (
    <View style={styles.c} testID="focus-areas-screen">
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <AppText variant="title">{current ? "Your focus area" : "Choose your focus"}</AppText>
        <Pressable onPress={() => goBack(router, "/")} hitSlop={10} testID="focus-areas-close">
          <Feather name="x" size={26} color={colors.onSurface} />
        </Pressable>
      </View>

      <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false} keyboardShouldPersistTaps="handled">
        {options.length > 0 && (
          <AppText variant="body" style={{ marginBottom: spacing.lg }}>
            {current
              ? `Keep working on ${current.label}, or choose a new area. Then check your goal still fits.`
              : "Based on your food recalls, these are the areas with the most room to grow. Choose one to work on. We'll build your suggestions around it."}
          </AppText>
        )}

        {loadError ? (
          <Card>
            <AppText variant="body">We couldn&apos;t load your focus options just now.</AppText>
            <Button title="Try again" variant="secondary" onPress={load} style={{ marginTop: spacing.md }} testID="focus-areas-retry" />
          </Card>
        ) : candidates === null ? (
          <ActivityIndicator color={colors.brandPrimary} />
        ) : options.length === 0 ? (
          <Card>
            <AppText variant="subtitle">Nothing to choose just yet</AppText>
            <AppText variant="body" style={{ marginTop: spacing.sm }}>
              {hasAssessment
                ? "Your food recalls don't show an area with much room to grow right now. Nice work. We'll suggest one after your next check-in."
                : "Your focus area comes from your food recalls (ASA24), which we don't have yet. Check back after your first check-in."}
            </AppText>
          </Card>
        ) : (
          <>
            <View style={{ gap: spacing.sm }}>
              {options.map((a) => {
                const active = selected === a.id;
                const tag = current?.id === a.id ? "Current" : a.suggested ? "Suggested" : null;
                return (
                  <Pressable
                    key={a.id}
                    testID={`focus-area-${a.id}`}
                    onPress={() => pick(a.id)}
                    style={[styles.option, active && styles.optionActive]}
                    accessibilityRole="radio"
                    accessibilityState={{ selected: active }}
                  >
                    <View style={{ flex: 1, gap: 2 }}>
                      <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
                        <AppText variant="subtitle" style={{ fontSize: 15 }} color={active ? colors.onSurfaceInverse : colors.onSurface}>
                          {a.label}
                        </AppText>
                        {tag ? (
                          <View style={[styles.tag, active && styles.tagActive]}>
                            <AppText variant="label" style={{ fontSize: 10 }} color={active ? colors.onSurfaceInverse : colors.onSurfaceSecondary}>
                              {tag.toUpperCase()}
                            </AppText>
                          </View>
                        ) : null}
                      </View>
                      <AppText variant="caption" color={active ? colors.onSurfaceInverse : colors.onSurfaceSecondary}>
                        {a.description}
                      </AppText>
                    </View>
                    <Feather name={active ? "check-circle" : "circle"} size={20} color={active ? colors.onSurfaceInverse : colors.muted} />
                  </Pressable>
                );
              })}
            </View>

            {chosen ? (
              <View style={{ marginTop: spacing["2xl"], gap: spacing.md }} testID="focus-goal">
                <AppText variant="subtitle">Your goal for {chosen.label.toLowerCase()}</AppText>
                <AppText variant="caption">Small and specific works best. You can change it any time.</AppText>
                <View>
                  <AppText variant="label" style={{ marginBottom: spacing.sm }}>
                    What will you do?
                  </AppText>
                  <TextInput
                    value={goal}
                    onChangeText={setGoal}
                    placeholder={goalExample(chosen.id)}
                    placeholderTextColor={colors.muted}
                    maxLength={200}
                    style={styles.input}
                    testID="focus-goal-input"
                  />
                </View>
                <View>
                  <AppText variant="label" style={{ marginBottom: spacing.sm }}>
                    When and where? (optional)
                  </AppText>
                  <TextInput
                    value={plan}
                    onChangeText={setPlan}
                    placeholder="e.g. At lunch on weekdays, at the dining hall"
                    placeholderTextColor={colors.muted}
                    maxLength={200}
                    style={styles.input}
                    testID="focus-plan-input"
                  />
                </View>
              </View>
            ) : null}
          </>
        )}

        {!!error && (
          <AppText variant="caption" color={colors.error} style={{ marginTop: spacing.lg }}>
            {error}
          </AppText>
        )}

        <View style={{ height: spacing["2xl"] }} />
        <Button
          title={keeping ? "Save my goal" : current ? "Change my focus area" : "Save my focus area"}
          onPress={submit}
          loading={submitting}
          disabled={options.length === 0}
          testID="focus-areas-save"
        />
      </ScrollView>
    </View>
  );
}

// One example goal per area, as a placeholder only.
function goalExample(id: string): string {
  const examples: Record<string, string> = {
    fruit: "e.g. Add a piece of fruit to breakfast",
    vegetables_beans: "e.g. Add a vegetable to dinner",
    grains: "e.g. Pick brown rice or whole-wheat bread",
    dairy: "e.g. Have milk or yogurt with breakfast",
    protein_foods: "e.g. Have beans or fish twice a week",
    fats: "e.g. Snack on nuts instead of chips",
    sodium: "e.g. Swap one salty snack for fruit",
    added_sugars: "e.g. Swap one sweet drink for water",
  };
  return examples[id] ?? "e.g. One small change you can repeat";
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
  option: {
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    paddingVertical: 14,
    paddingHorizontal: spacing.lg,
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
  },
  optionActive: { backgroundColor: colors.surfaceInverse, borderColor: colors.surfaceInverse },
  tag: { paddingHorizontal: 6, paddingVertical: 2, borderRadius: radius.sm, backgroundColor: colors.surface },
  tagActive: { backgroundColor: "rgba(255,255,255,0.18)" },
  input: {
    backgroundColor: colors.surfaceSecondary,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    paddingHorizontal: spacing.lg,
    paddingVertical: 14,
    fontFamily: fonts.medium,
    fontSize: fontSize.base,
    color: colors.onSurface,
  },
});
