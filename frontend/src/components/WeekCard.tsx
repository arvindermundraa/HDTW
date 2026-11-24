import React from "react";
import { View, StyleSheet, Pressable } from "react-native";
import { useRouter } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { AppText } from "@/src/components/ui";
import { IconCircle, PointsPill, cardStyle } from "@/src/components/llhs";
import { colors, spacing, fonts } from "@/src/theme";
import type { StepType, WeekStepStatus, WeekView, PlanningCardForToday } from "@/src/weekly-workflow";
import { FOCUS_AREA_LABEL } from "@/src/food";

// Today's "This week" card for the content-driven weekly workflow (Weeks 1
// and 2). Mirrors the shape of the old program-step card so the Today
// screen looks the same whether a student is on the new engine or still
// on program.py.
//
// Phase 2 PR: every Week 1 step type is now implemented, so the whole
// sequence is tappable. The focus-area panel at the top surfaces the
// participant's chosen area + goal + plan when they're set — the
// "connection to ongoing app features" from spec §8.
const IMPLEMENTED_STEP_TYPES: ReadonlyArray<StepType> = [
  "video",
  "feedback",
  "focus_selection",
  "reflection",
  "goal_and_plan",
  "scenario_set",
];

const STEP_ICON: Record<StepType, React.ComponentProps<typeof Feather>["name"]> = {
  video: "play-circle",
  feedback: "bar-chart-2",
  focus_selection: "target",
  reflection: "message-square",
  goal_and_plan: "flag",
  scenario_set: "edit-3",
  plan: "calendar",
  review: "check-circle",
};

function isActionable(step: WeekStepStatus): boolean {
  return IMPLEMENTED_STEP_TYPES.includes(step.type);
}

export type FocusForCard = {
  area?: string | null;
  goal?: string | null;
  plan?: string | null;
};

export function WeekCard({
  view,
  focus,
  plans,
  testID,
}: {
  view: WeekView;
  focus?: FocusForCard;
  plans?: PlanningCardForToday[];
  testID?: string;
}) {
  const router = useRouter();
  const nextStep = view.next_step_id ? view.steps.find((s) => s.id === view.next_step_id) ?? null : null;
  const focusLabel = focus?.area ? FOCUS_AREA_LABEL[focus.area] ?? focus.area : null;
  const hasGoal = !!focus?.goal;
  const hasPlan = !!focus?.plan;

  const openNext = () => {
    if (!nextStep) return;
    if (!isActionable(nextStep)) return;
    router.push({ pathname: "/week/[step]" as any, params: { step: nextStep.id, week: String(view.week) } });
  };

  return (
    <View style={[cardStyle, { gap: spacing.md }]} testID={testID ?? `week-card-${view.week}`}>
      <View style={{ gap: 2 }}>
        <AppText variant="label" color={colors.brandPrimary} style={{ fontSize: 12, letterSpacing: 0.6 }}>
          WEEK {view.week} · {view.steps_done} OF {view.steps_total} DONE
        </AppText>
        <AppText variant="subtitle" style={{ fontSize: 18 }}>
          {view.title}
        </AppText>
        {view.summary ? <AppText variant="caption">{view.summary}</AppText> : null}
      </View>

      {focusLabel ? (
        <Pressable
          style={styles.focusPanel}
          onPress={() => router.push("/focus-areas")}
          testID={`week-card-${view.week}-focus`}
          accessibilityRole="button"
          accessibilityLabel={`Your focus: ${focusLabel}. Open to edit.`}
        >
          <View style={{ flex: 1, gap: 2 }}>
            <AppText variant="caption" color={colors.brandPrimary} style={{ letterSpacing: 0.4 }}>
              YOUR FOCUS
            </AppText>
            <AppText variant="subtitle" style={{ fontSize: 15 }}>
              {focusLabel}
            </AppText>
            {hasGoal ? (
              <AppText variant="body" style={{ fontSize: 13 }} numberOfLines={2}>
                <AppText variant="body" style={{ fontSize: 13, fontFamily: fonts.semibold }}>Goal: </AppText>
                {focus?.goal}
              </AppText>
            ) : null}
            {hasPlan ? (
              <AppText variant="body" style={{ fontSize: 13 }} numberOfLines={2}>
                <AppText variant="body" style={{ fontSize: 13, fontFamily: fonts.semibold }}>Plan: </AppText>
                {focus?.plan}
              </AppText>
            ) : null}
          </View>
          <Feather name="chevron-right" size={18} color={colors.onSurfaceSecondary} />
        </Pressable>
      ) : null}

      {nextStep ? (
        <Pressable
          onPress={openNext}
          disabled={!isActionable(nextStep)}
          style={styles.nextRow}
          testID={`week-card-${view.week}-next`}
          accessibilityRole="button"
          accessibilityLabel={`Next step: ${nextStep.label}`}
        >
          <IconCircle
            icon={STEP_ICON[nextStep.type] ?? "arrow-right-circle"}
            color={colors.brandPrimary}
            tint={colors.surfaceTertiary}
            size={44}
            iconSize={20}
          />
          <View style={{ flex: 1 }}>
            <AppText variant="caption">Next step</AppText>
            <AppText variant="subtitle" style={{ fontSize: 15 }} numberOfLines={2}>
              {nextStep.title || nextStep.label}
            </AppText>
            {!isActionable(nextStep) ? (
              <AppText variant="caption" color={colors.onSurfaceSecondary} style={{ marginTop: 2 }}>
                Opens in the next release
              </AppText>
            ) : null}
          </View>
          {nextStep.points ? <PointsPill points={nextStep.points} /> : null}
        </Pressable>
      ) : (
        <AppText variant="body" style={{ fontSize: 14 }}>
          You&apos;re done with this week. Nice work.
        </AppText>
      )}

      <View style={{ gap: spacing.xs, marginTop: spacing.xs }} testID={`week-card-${view.week}-steps`}>
        {view.steps.map((s) => (
          <StepRow key={s.id} step={s} week={view.week} />
        ))}
      </View>

      {plans && plans.length > 0 ? (
        <View style={{ gap: spacing.sm, marginTop: spacing.sm }} testID={`week-card-${view.week}-plans`}>
          <AppText variant="caption" color={colors.onSurfaceSecondary} style={{ letterSpacing: 0.4 }}>
            YOUR ACTIVE PLANS
          </AppText>
          {plans.map((p) => (
            <PlanRow key={p.id} plan={p} />
          ))}
        </View>
      ) : null}
    </View>
  );
}

function PlanRow({ plan }: { plan: PlanningCardForToday }) {
  const router = useRouter();
  const edit = () =>
    router.push({ pathname: "/week/[step]" as any, params: { step: "planning", week: "2", edit: plan.id } });
  return (
    <View style={styles.planRow} testID={`plan-row-${plan.id}`}>
      <View style={{ flex: 1, gap: 2 }}>
        <AppText variant="caption" color={colors.brandPrimary} style={{ letterSpacing: 0.3 }}>
          FROM WEEK {plan.source_week}
        </AppText>
        {plan.action_text ? (
          <AppText variant="subtitle" style={{ fontSize: 14 }} numberOfLines={2}>
            {plan.action_text}
          </AppText>
        ) : plan.goal ? (
          <AppText variant="subtitle" style={{ fontSize: 14 }} numberOfLines={2}>
            {plan.goal}
          </AppText>
        ) : null}
        {plan.situation_text ? (
          <AppText variant="caption" numberOfLines={2}>
            {plan.situation_text}
            {plan.reminder_time ? ` · reminder ${plan.reminder_time}` : ""}
          </AppText>
        ) : null}
      </View>
      <Pressable onPress={edit} hitSlop={8} style={styles.editButton} testID={`plan-row-${plan.id}-edit`}>
        <Feather name="edit-2" size={14} color={colors.brandPrimary} />
        <AppText variant="caption" color={colors.brandPrimary} style={{ marginLeft: 4 }}>
          Edit
        </AppText>
      </Pressable>
    </View>
  );
}

function StepRow({ step, week }: { step: WeekStepStatus; week: number }) {
  const router = useRouter();
  const done = step.status === "done";
  const actionable = isActionable(step) && !done;
  const press = () => {
    if (!actionable) return;
    router.push({ pathname: "/week/[step]" as any, params: { step: step.id, week: String(week) } });
  };
  return (
    <Pressable
      onPress={press}
      disabled={!actionable}
      style={styles.stepRow}
      testID={`week-${week}-step-${step.id}`}
      accessibilityRole={actionable ? "button" : "text"}
    >
      <Feather
        name={done ? "check-circle" : "circle"}
        size={16}
        color={done ? colors.brandPrimary : colors.onSurfaceSecondary}
      />
      <AppText
        variant="body"
        style={{ fontSize: 14, flex: 1, color: done ? colors.onSurfaceSecondary : colors.onSurface }}
        numberOfLines={1}
      >
        {step.label}
        {step.draft ? "  (draft)" : ""}
      </AppText>
      {!actionable && !done ? (
        <AppText variant="caption" color={colors.onSurfaceSecondary}>
          Soon
        </AppText>
      ) : null}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  nextRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
  },
  stepRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    paddingVertical: 6,
  },
  focusPanel: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    borderRadius: 10,
    backgroundColor: colors.surfaceSecondary,
    borderWidth: 1,
    borderColor: colors.border,
  },
  planRow: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: spacing.sm,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    borderRadius: 10,
    backgroundColor: colors.surfaceSecondary,
    borderWidth: 1,
    borderColor: colors.border,
  },
  editButton: {
    flexDirection: "row",
    alignItems: "center",
  },
});
