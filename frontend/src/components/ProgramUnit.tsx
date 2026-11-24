import React, { useState } from "react";
import { View, StyleSheet, Pressable, TextInput } from "react-native";
import { useRouter } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { AppText, Button } from "@/src/components/ui";
import { PointsPill, cardStyle } from "@/src/components/llhs";
import { api, Program, ProgramStep, ProgramUnit } from "@/src/api";
import { colors, spacing, radius, fonts, fontSize } from "@/src/theme";

// One week of the 8-week program: Watch → Practice → Do it → Reflect, shown
// as one connected sequence. Video, game and focus-area steps complete from
// the rest of the app; "Do it" and "Reflect" are marked here.
const STEP_ICON: Record<ProgramStep["key"], React.ComponentProps<typeof Feather>["name"]> = {
  watch: "play-circle",
  practice: "edit-3",
  do_it: "check-square",
  reflect: "message-square",
};

export function ProgramUnitCard({
  unit,
  onChange,
  compact = false,
  testID,
}: {
  unit: ProgramUnit;
  onChange: (p: Program) => void;
  compact?: boolean;
  testID?: string;
}) {
  return (
    <View style={[cardStyle, { gap: spacing.md }]} testID={testID ?? `unit-${unit.week}`}>
      <View style={{ gap: 4 }}>
        <AppText variant="label" color={colors.brandPrimary} style={{ fontSize: 12, letterSpacing: 0.6 }}>
          WEEK {unit.week} · {unit.steps_done} OF {unit.steps_total} DONE
        </AppText>
        <AppText variant="subtitle" style={{ fontSize: 18 }}>
          {unit.title}
        </AppText>
        {!compact && <AppText variant="caption">{unit.summary}</AppText>}
      </View>
      <View style={{ gap: spacing.xs }}>
        {unit.steps.map((s, i) => (
          <StepRow key={s.key} step={s} week={unit.week} last={i === unit.steps.length - 1} onChange={onChange} />
        ))}
      </View>
    </View>
  );
}

function StepRow({ step, week, last, onChange }: { step: ProgramStep; week: number; last: boolean; onChange: (p: Program) => void }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const mark = async (body?: string) => {
    setSaving(true);
    setError("");
    try {
      const r = await api.completeProgramStep(week, step.key, body);
      setOpen(false);
      onChange(r.program);
    } catch (e: any) {
      setError(e?.message || "Couldn't save that. Try again.");
    } finally {
      setSaving(false);
    }
  };

  const press = () => {
    if (!step.ready) return;
    if (step.key === "reflect" || step.key === "do_it") return setOpen((v) => !v);
    if (step.route) router.push(step.params ? ({ pathname: step.route, params: step.params } as any) : (step.route as any));
  };

  return (
    <View>
      <Pressable onPress={press} style={styles.row} testID={`step-${week}-${step.key}`} accessibilityRole="button" disabled={!step.ready}>
        <View style={styles.rail}>
          <View style={[styles.dot, step.done && styles.dotDone, !step.ready && styles.dotSoon]}>
            <Feather name={step.done ? "check" : STEP_ICON[step.key]} size={15} color={step.done ? "#FFFFFF" : step.ready ? colors.brandPrimary : colors.muted} />
          </View>
          {!last && <View style={styles.line} />}
        </View>
        <View style={{ flex: 1, paddingBottom: last ? 0 : spacing.md }}>
          <AppText variant="label" color={colors.muted} style={{ fontSize: 11, letterSpacing: 0.6 }}>
            {step.label.toUpperCase()}
          </AppText>
          <AppText variant="subtitle" style={{ fontSize: 15 }} color={step.ready ? colors.onSurface : colors.muted}>
            {step.title}
          </AppText>
          {!step.ready && <AppText variant="caption">Coming soon</AppText>}
        </View>
        {step.done ? null : step.ready ? <PointsPill points={step.points} /> : null}
      </Pressable>

      {open && !step.done && (
        <View style={styles.panel}>
          {step.key === "reflect" ? (
            <>
              <AppText variant="body" style={{ fontSize: 14 }}>
                {step.prompt}
              </AppText>
              <TextInput
                value={text}
                onChangeText={setText}
                placeholder="A sentence or two is plenty"
                placeholderTextColor={colors.muted}
                multiline
                maxLength={1000}
                style={styles.input}
                testID={`reflect-${week}`}
              />
              <Button title="Save reflection" onPress={() => mark(text)} loading={saving} disabled={!text.trim()} testID={`reflect-save-${week}`} />
            </>
          ) : (
            <>
              <AppText variant="body" style={{ fontSize: 14 }}>
                Tried it this week? Mark it done. A note about how it went is optional.
              </AppText>
              <TextInput
                value={text}
                onChangeText={setText}
                placeholder="Optional: what did you try?"
                placeholderTextColor={colors.muted}
                maxLength={1000}
                style={styles.input}
                testID={`doit-${week}`}
              />
              <Button title="I did it" onPress={() => mark(text)} loading={saving} testID={`doit-save-${week}`} />
            </>
          )}
          {error ? (
            <AppText variant="caption" color={colors.error}>
              {error}
            </AppText>
          ) : null}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", gap: spacing.md, alignItems: "flex-start" },
  rail: { alignItems: "center", width: 32 },
  dot: {
    width: 32,
    height: 32,
    borderRadius: 16,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.surfaceTertiary,
  },
  dotDone: { backgroundColor: colors.brandPrimary },
  dotSoon: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
  line: { flex: 1, width: 2, backgroundColor: colors.border, marginTop: 2, minHeight: 14 },
  panel: { marginLeft: 44, marginBottom: spacing.md, gap: spacing.sm },
  input: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    paddingVertical: 10,
    fontFamily: fonts.medium,
    fontSize: fontSize.base,
    color: colors.onSurface,
    minHeight: 44,
  },
});
