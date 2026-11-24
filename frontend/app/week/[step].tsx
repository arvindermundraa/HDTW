// Week step detail screen — one route for every step in the weekly workflow
// engine (backend/weekly_workflow.py). The step id in the URL + the ?week=
// query param pick a step out of the week's content file; this screen
// dispatches on the step's `type` to the right sub-view.
//
// Phase 1 PR shipped video, feedback, focus_selection. Phase 2 (this PR)
// adds mini_lecture (video with per-focus-area selection), reflection
// (three sub-prompts with exact wording from docs/week1_spec.md), and
// goal_and_plan (writes through /profile/focus-areas; the engine's
// goal_and_plan_set rule marks it done).
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { View, StyleSheet, ScrollView, Pressable, ActivityIndicator, TextInput } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Feather } from "@expo/vector-icons";
import { AppText, Button } from "@/src/components/ui";
import { cardStyle } from "@/src/components/llhs";
import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { colors, spacing, radius, fonts } from "@/src/theme";
import { goBack } from "@/src/navigation";
import type {
  StepDetail,
  Week2ScenariosConfig,
  Week2ScenarioBody,
  Week2ScenarioChoice,
  Week2ScenarioFeedback,
  PlanningConfig,
  PlanningSubmit,
  PlanningSubmitResult,
  PlanningCardForToday,
} from "@/src/weekly-workflow";
import { WeekFocusBanner } from "@/src/components/WeekFocusBanner";

type FocusCandidate = { id: string; label: string; description?: string; suggested?: boolean };
type HeiComponentBar = { id: string; label: string; fill: number; kind: "adequacy" | "moderation" };
type HeiBar = { id: string; label: string; fill: number; expandable: boolean; components: HeiComponentBar[] };
type FocusCandidatesResponse = {
  has_assessment: boolean;
  candidates: FocusCandidate[];
  current?: { id: string; label: string } | null;
  bars?: HeiBar[];
};

type ReflectionResponses = {
  p1_behind?: { selected: string[]; text?: string };
  p2_room?: { selected: string | null };
  p3_working?: { text: string };
};

export default function WeekStepScreen() {
  const params = useLocalSearchParams<{ step?: string; week?: string }>();
  const stepId = params.step ?? "";
  const week = Number(params.week ?? 1);
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { refresh } = useAuth();

  const [detail, setDetail] = useState<StepDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string>("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const d = await api.getWeeklyStep(week, stepId);
      setDetail(d);
    } catch (e: any) {
      setError(e?.message || "Couldn't load this step.");
    } finally {
      setLoading(false);
    }
  }, [week, stepId]);

  useEffect(() => {
    load();
  }, [load]);

  const complete = async (body?: { responses?: Record<string, any>; note?: string }) => {
    setSaving(true);
    setError("");
    try {
      await api.completeWeeklyStep(week, stepId, body);
      // Keep user state fresh (focus_area, focus_goal may have changed
      // on the server as a side-effect of completing related screens).
      await refresh?.();
      router.replace("/(tabs)");
    } catch (e: any) {
      setError(e?.message || "Couldn't save this step. Try again.");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color={colors.brandPrimary} />
      </View>
    );
  }

  const content = detail?.content ?? {};
  const alreadyDone = detail?.status?.status === "done";
  const type = content.type as string | undefined;
  const title = content.title ?? detail?.status?.label ?? "This step";
  const carried = detail?.carried ?? {};

  return (
    <View style={styles.c}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable onPress={() => goBack(router, "/(tabs)")} hitSlop={10} testID="week-step-back">
          <Feather name="chevron-left" size={26} color={colors.onSurface} />
        </Pressable>
        <AppText variant="label">
          WEEK {week} · {content.label || "Step"}
        </AppText>
        <View style={{ width: 26 }} />
      </View>

      <ScrollView contentContainerStyle={styles.scroll} testID="week-step-scroll">
        {week === 2 ? <WeekFocusBanner week={week} /> : null}
        <AppText variant="display" style={{ marginBottom: spacing.sm }}>
          {title}
        </AppText>

        {alreadyDone ? (
          <View style={[cardStyle, styles.doneBadge]} testID="week-step-done">
            <Feather name="check-circle" size={20} color={colors.brandPrimary} />
            <AppText variant="body" style={{ marginLeft: spacing.sm }}>
              You already finished this step.
            </AppText>
          </View>
        ) : null}

        {type === "video" ? (
          <VideoStep content={content} />
        ) : type === "feedback" ? (
          <FeedbackStep content={content} />
        ) : type === "focus_selection" ? (
          <FocusSelectionStep content={content} router={router} />
        ) : type === "reflection" ? (
          <ReflectionStep
            content={content}
            saving={saving}
            onSubmit={(responses) => complete({ responses })}
          />
        ) : type === "goal_and_plan" ? (
          <GoalAndPlanStep
            content={content}
            carried={carried as Record<string, any>}
            onSaved={() => router.replace("/(tabs)")}
          />
        ) : type === "scenario_set" ? (
          <ScenarioSetStep
            content={content}
            onDone={() => router.replace("/(tabs)")}
          />
        ) : type === "planning" ? (
          <PlanningStep
            content={content}
            editPlanId={(params as any)?.edit ?? null}
            onDone={() => router.replace("/(tabs)")}
          />
        ) : type === "review" ? (
          <ReviewStep content={content} onDone={() => router.replace("/(tabs)")} />
        ) : (
          <ComingSoonStep content={content} />
        )}

        {error ? (
          <AppText variant="body" color={colors.error} style={{ marginTop: spacing.md }}>
            {error}
          </AppText>
        ) : null}

        {/* Simple-form steps use the top-level Continue; the reflection
            and goal-and-plan steps have their own submit buttons inside
            the sub-view because they need validation + response payloads. */}
        {!alreadyDone && isSimpleStep(type) ? (
          <Button
            title={saving ? "Saving…" : content.cta_next_label || "Continue"}
            onPress={() => complete()}
            disabled={saving}
            style={{ marginTop: spacing.xl }}
            testID="week-step-continue"
          />
        ) : null}

        {alreadyDone ? (
          <Button
            title="Back to Today"
            onPress={() => router.replace("/(tabs)")}
            style={{ marginTop: spacing.lg }}
            variant="secondary"
            testID="week-step-back-today"
          />
        ) : null}
      </ScrollView>
    </View>
  );
}

function isSimpleStep(type: string | undefined): boolean {
  // Steps whose "Continue" button is the one at the bottom of the
  // screen (no responses to collect, no inline validation).
  return type === "video" || type === "feedback";
}

function VideoStep({ content }: { content: any }) {
  // When `video_url` is null (overview video, or a mini-lecture without
  // its per-area URL yet) the frontend shows a calm "coming soon" card
  // and still allows Continue so the flow never blocks on missing content.
  const hasVideo = !!content.video_url;
  const comingSoonBody = content.coming_soon_body as string | undefined;
  return (
    <View style={[cardStyle, { gap: spacing.md }]} testID="week-step-video">
      <View style={styles.videoBox}>
        <Feather
          name={hasVideo ? "play-circle" : "clock"}
          size={48}
          color={colors.brandPrimary}
        />
      </View>
      {content.summary ? <AppText variant="body">{content.summary}</AppText> : null}
      {content.duration_hint ? (
        <AppText variant="caption">{content.duration_hint}</AppText>
      ) : null}
      {!hasVideo ? (
        <AppText variant="caption" color={colors.onSurfaceSecondary}>
          {comingSoonBody || "Video coming soon. You can continue — the team is finishing this one."}
        </AppText>
      ) : null}
    </View>
  );
}

// A single focus-area bar. Tapping a bar whose area combines two HEI-2020
// components (Grains = Whole + Refined; Fats = Fatty Acids + Saturated)
// expands it to show the two sub-component bars. The `fill` is a 0..1
// width; the bar carries no displayed number — nutrition team 2026-11-06
// item 1 ("Grains and Fats results").
function FeedbackBarRow({ bar }: { bar: HeiBar }) {
  const [open, setOpen] = useState(false);
  const toggle = () => bar.expandable && setOpen((v) => !v);
  return (
    <View style={{ gap: spacing.xs }}>
      <Pressable
        onPress={toggle}
        disabled={!bar.expandable}
        accessibilityRole={bar.expandable ? "button" : "summary"}
        accessibilityLabel={
          bar.expandable
            ? `${bar.label} bar. Tap to ${open ? "collapse" : "expand"} component bars.`
            : `${bar.label} bar.`
        }
        style={styles.barRow}
        testID={`feedback-bar-${bar.id}`}
      >
        <AppText variant="body" style={{ flex: 1 }}>
          {bar.label}
        </AppText>
        <View style={styles.barTrack}>
          <View style={[styles.barFill, { width: `${Math.round(bar.fill * 100)}%` }]} />
        </View>
        {bar.expandable ? (
          <Feather name={open ? "chevron-up" : "chevron-down"} size={16} color={colors.muted} />
        ) : null}
      </Pressable>
      {open ? (
        <View style={styles.subBarGroup} testID={`feedback-bar-${bar.id}-children`}>
          {bar.components.map((c) => (
            <View key={c.id} style={styles.subBarRow}>
              <AppText variant="caption" style={{ flex: 1 }} color={colors.onSurfaceSecondary}>
                {c.label}
              </AppText>
              <View style={[styles.barTrack, styles.subBarTrack]}>
                <View style={[styles.barFill, styles.subBarFill, { width: `${Math.round(c.fill * 100)}%` }]} />
              </View>
            </View>
          ))}
        </View>
      ) : null}
    </View>
  );
}

function FeedbackStep({ content }: { content: any }) {
  const [data, setData] = useState<FocusCandidatesResponse | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    (async () => {
      try {
        const r = (await api.getFocusCandidates()) as FocusCandidatesResponse;
        setData(r);
      } catch (e: any) {
        setErr(e?.message || "Couldn't load feedback.");
      }
    })();
  }, []);
  const candidates = data?.candidates ?? [];
  const bars = data?.bars ?? [];
  return (
    <View style={[cardStyle, { gap: spacing.md }]} testID="week-step-feedback">
      {content.intro ? <AppText variant="body">{content.intro}</AppText> : null}
      {!data ? (
        err ? (
          <AppText variant="caption" color={colors.error}>
            {err}
          </AppText>
        ) : (
          <ActivityIndicator color={colors.brandPrimary} />
        )
      ) : !data.has_assessment ? (
        <AppText variant="body">
          Your baseline results aren&apos;t in yet. When your recalls are imported, this is where
          your strengths and areas with room to grow will appear. You can continue when you&apos;re
          ready.
        </AppText>
      ) : (
        <View style={{ gap: spacing.md }}>
          {bars.length > 0 ? (
            <View style={{ gap: spacing.sm }} testID="feedback-bars">
              <AppText variant="subtitle" style={{ fontSize: 15 }}>
                Where you are, by focus area
              </AppText>
              <AppText variant="caption" color={colors.onSurfaceSecondary}>
                Tap Grains or Fats to see the two parts of that bar.
              </AppText>
              {bars.map((b) => (
                <FeedbackBarRow key={b.id} bar={b} />
              ))}
            </View>
          ) : null}
          <View style={{ gap: spacing.sm }}>
            <AppText variant="subtitle" style={{ fontSize: 15 }}>
              Areas with room to grow
            </AppText>
            {candidates.slice(0, 3).map((c) => (
              <View key={c.id} style={styles.candidateRow}>
                <Feather name="trending-up" size={16} color={colors.brandPrimary} />
                <AppText variant="body" style={{ flex: 1 }}>
                  {c.label}
                  {c.suggested ? "  · suggested" : ""}
                </AppText>
              </View>
            ))}
            {candidates.length === 0 ? (
              <AppText variant="body">
                Based on the days you reported, your baseline is close to the Dietary Guidelines
                across the board. You can still pick an area to focus on.
              </AppText>
            ) : null}
          </View>
        </View>
      )}
      {content.lead_in ? (
        <AppText variant="caption" color={colors.onSurfaceSecondary}>
          {content.lead_in}
        </AppText>
      ) : null}
    </View>
  );
}

function FocusSelectionStep({ content, router }: { content: any; router: ReturnType<typeof useRouter> }) {
  // Routing step: send the student to the existing /focus-areas screen. The
  // engine's `focus_area_set` completion rule auto-marks this step done the
  // next time Today loads, so there's no POST from this screen.
  return (
    <View style={[cardStyle, { gap: spacing.md }]} testID="week-step-focus-selection">
      {content.subtitle ? <AppText variant="body">{content.subtitle}</AppText> : null}
      <Button
        title={content.cta_next_label || "Open focus areas"}
        onPress={() => router.push("/focus-areas")}
        testID="week-step-focus-cta"
      />
      <AppText variant="caption" color={colors.onSurfaceSecondary}>
        This step completes itself once your focus area is saved.
      </AppText>
    </View>
  );
}

function ReflectionStep({
  content,
  saving,
  onSubmit,
}: {
  content: any;
  saving: boolean;
  onSubmit: (responses: ReflectionResponses) => void;
}) {
  const resolvedPrompts = (content.resolved_prompts ?? content.prompts ?? []) as any[];
  const notSureOption = resolvedPrompts.find((p) => p.not_sure_option)?.not_sure_option ?? "Not sure yet";

  const [p1Selected, setP1Selected] = useState<string[]>([]);
  const [p1Text, setP1Text] = useState("");
  const [p2Selected, setP2Selected] = useState<string | null>(null);
  const [p3Text, setP3Text] = useState("");

  // The completion message depends on p2's current pick. The server
  // computes an authoritative version at submit time; this preview is
  // just so the student sees the shape of what's next before saving.
  const previewMessage = useMemo(() => {
    if (!p2Selected) return null;
    if (p2Selected === notSureOption) return content.not_sure_yet_message as string | null;
    const tpl = (content.completion_message_template as string | undefined) ?? "";
    return tpl.replace("{occasion}", p2Selected);
  }, [p2Selected, content.completion_message_template, content.not_sure_yet_message, notSureOption]);

  const toggleP1 = (opt: string) =>
    setP1Selected((prev) => (prev.includes(opt) ? prev.filter((v) => v !== opt) : [...prev, opt]));

  const canSubmit = !saving && p1Selected.length > 0 && p2Selected && p3Text.trim().length > 0;

  const submit = () => {
    onSubmit({
      p1_behind: { selected: p1Selected, text: p1Text.trim() || undefined },
      p2_room: { selected: p2Selected },
      p3_working: { text: p3Text.trim() },
    });
  };

  return (
    <View style={{ gap: spacing.md }} testID="week-step-reflection">
      {content.intro_text ? (
        <View style={[cardStyle, { gap: spacing.sm }]} testID="reflection-intro">
          <AppText variant="body">{content.intro_text}</AppText>
          <ProgressBarPlaceholder />
        </View>
      ) : null}

      <PromptCard label="1" testID="reflection-p1">
        <AppText variant="subtitle" style={{ fontSize: 15 }}>
          {resolvedPrompts[0]?.prompt || resolvedPrompts[0]?.variant_by_focus_kind?.adequacy || ""}
        </AppText>
        <AppText variant="caption" style={{ marginBottom: spacing.sm }}>
          Select all that apply
        </AppText>
        <View style={styles.chipRow}>
          {(resolvedPrompts[0]?.options ?? []).map((opt: string) => (
            <Pressable
              key={opt}
              onPress={() => toggleP1(opt)}
              style={[styles.chip, p1Selected.includes(opt) && styles.chipOn]}
              testID={`reflection-p1-${opt.toLowerCase().replace(/\s+/g, "-")}`}
            >
              <AppText
                variant="body"
                style={{ fontSize: 13 }}
                color={p1Selected.includes(opt) ? colors.onBrandPrimary : colors.onSurface}
              >
                {opt}
              </AppText>
            </Pressable>
          ))}
        </View>
        {resolvedPrompts[0]?.optional_text ? (
          <TextInput
            value={p1Text}
            onChangeText={setP1Text}
            placeholder={resolvedPrompts[0]?.optional_text_label || "Anything to add"}
            style={styles.input}
            maxLength={resolvedPrompts[0]?.optional_text_max_length ?? 500}
            multiline
            testID="reflection-p1-text"
          />
        ) : null}
      </PromptCard>

      <PromptCard label="2" testID="reflection-p2">
        <AppText variant="subtitle" style={{ fontSize: 15 }}>
          {resolvedPrompts[1]?.prompt || ""}
        </AppText>
        <View style={styles.chipRow}>
          {(resolvedPrompts[1]?.options ?? []).map((opt: string) => (
            <Pressable
              key={opt}
              onPress={() => setP2Selected(opt)}
              style={[styles.chip, p2Selected === opt && styles.chipOn]}
              testID={`reflection-p2-${opt.toLowerCase().replace(/\s+/g, "-")}`}
            >
              <AppText
                variant="body"
                style={{ fontSize: 13 }}
                color={p2Selected === opt ? colors.onBrandPrimary : colors.onSurface}
              >
                {opt}
              </AppText>
            </Pressable>
          ))}
        </View>
      </PromptCard>

      <PromptCard label="3" testID="reflection-p3">
        <AppText variant="subtitle" style={{ fontSize: 15 }}>
          {resolvedPrompts[2]?.prompt || ""}
        </AppText>
        <TextInput
          value={p3Text}
          onChangeText={setP3Text}
          placeholder={resolvedPrompts[2]?.placeholder || "A strength you'd like to keep"}
          style={styles.input}
          maxLength={resolvedPrompts[2]?.max_length ?? 500}
          multiline
          testID="reflection-p3-text"
        />
      </PromptCard>

      {previewMessage ? (
        <View style={[cardStyle, styles.previewMessage]} testID="reflection-preview">
          <Feather name="arrow-right-circle" size={18} color={colors.brandPrimary} />
          <AppText variant="body" style={{ flex: 1 }}>
            {previewMessage}
          </AppText>
        </View>
      ) : null}

      <Button
        title={saving ? "Saving…" : content.cta_next_label || "Save my reflection"}
        onPress={submit}
        disabled={!canSubmit}
        style={{ marginTop: spacing.sm }}
        testID="reflection-submit"
      />
      {!canSubmit && !saving ? (
        <AppText variant="caption" color={colors.onSurfaceSecondary}>
          Pick at least one option in prompt 1, pick a moment in prompt 2, and write a short note in
          prompt 3.
        </AppText>
      ) : null}
    </View>
  );
}

function PromptCard({ label, testID, children }: { label: string; testID?: string; children: React.ReactNode }) {
  return (
    <View style={[cardStyle, { gap: spacing.sm }]} testID={testID}>
      <View style={styles.promptHeader}>
        <View style={styles.promptNum}>
          <AppText variant="caption" color={colors.onBrandPrimary} style={{ fontSize: 11 }}>
            {label}
          </AppText>
        </View>
      </View>
      {children}
    </View>
  );
}

function ProgressBarPlaceholder() {
  // Visual bar for the student's alignment with the Dietary Guidelines
  // for their focus area. Phase 2 ships without numbers (no gradient
  // tie to the HEI component score) — the bar is a labels-only
  // illustration per spec 6.1 ("do not display numerical scores").
  return (
    <View style={styles.progressTrack} accessibilityRole="progressbar">
      <View style={styles.progressFill} />
      <AppText
        variant="caption"
        color={colors.onBrandPrimary}
        style={styles.progressLabel}
      >
        Where you are
      </AppText>
    </View>
  );
}

function GoalAndPlanStep({
  content,
  carried,
  onSaved,
}: {
  content: any;
  carried: Record<string, any>;
  onSaved: () => void;
}) {
  const { user, refresh } = useAuth();
  const focusAreaId = user?.focus_area ?? null;
  const example = (content.resolved_example ?? null) as { goal: string; plan: string } | null;
  const occasionCarried = (carried?.occasion as string | undefined) ?? null;
  const existingGoal = (user?.focus_goal?.goal as string | undefined) ?? "";
  const existingPlan = (user?.focus_goal?.plan as string | undefined) ?? "";
  const [goal, setGoal] = useState(existingGoal);
  const [plan, setPlan] = useState(existingPlan);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");

  const canSave = !saving && !!focusAreaId && goal.trim().length > 0 && plan.trim().length > 0;

  const save = async () => {
    if (!focusAreaId) {
      setErr("Pick a focus area first.");
      return;
    }
    setSaving(true);
    setErr("");
    try {
      await api.setFocusAreas(focusAreaId, goal.trim(), plan.trim());
      await refresh?.();
      // Completion for this step is auto-overlaid by the engine's
      // goal_and_plan_set rule the next time Today loads; no explicit
      // POST to /complete is needed.
      onSaved();
    } catch (e: any) {
      setErr(e?.message || "Couldn't save your goal and plan.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <View style={{ gap: spacing.md }} testID="week-step-goal-and-plan">
      <View style={[cardStyle, { gap: spacing.sm }]} testID="goal-intro">
        {content.intro ? <AppText variant="body">{content.intro}</AppText> : null}
        {occasionCarried ? (
          <View style={styles.carriedRow}>
            <Feather name="corner-down-right" size={16} color={colors.brandPrimary} />
            <AppText variant="body" style={{ flex: 1 }}>
              You picked <AppText variant="body" style={{ fontFamily: fonts.semibold }}>{occasionCarried}</AppText> as the easiest
              moment to try something new.
            </AppText>
          </View>
        ) : null}
      </View>

      {!focusAreaId ? (
        <View style={[cardStyle, { gap: spacing.sm }]}>
          <AppText variant="body">
            Pick your focus area first — it tells us what kind of goal makes sense.
          </AppText>
        </View>
      ) : null}

      {example ? (
        <View style={[cardStyle, styles.exampleCard]} testID="goal-example">
          <AppText variant="caption" color={colors.onSurfaceSecondary}>
            Example you can edit
          </AppText>
          <AppText variant="body">
            <AppText variant="body" style={{ fontFamily: fonts.semibold }}>Goal: </AppText>
            {example.goal}
          </AppText>
          <AppText variant="body">
            <AppText variant="body" style={{ fontFamily: fonts.semibold }}>Plan: </AppText>
            {example.plan}
          </AppText>
          <Pressable
            onPress={() => {
              setGoal(example.goal);
              setPlan(example.plan);
            }}
            style={styles.useExample}
            testID="goal-use-example"
          >
            <Feather name="copy" size={14} color={colors.brandPrimary} />
            <AppText variant="caption" color={colors.brandPrimary}>
              Use this as a starting point
            </AppText>
          </Pressable>
        </View>
      ) : null}

      <View style={[cardStyle, { gap: spacing.md }]} testID="goal-form">
        <View style={{ gap: 4 }}>
          <AppText variant="subtitle" style={{ fontSize: 14 }}>
            {content.goal_prompt || "I will…"}
          </AppText>
          <TextInput
            value={goal}
            onChangeText={setGoal}
            placeholder={content.goal_placeholder || "A behavior you want to try, in your own words"}
            style={styles.input}
            maxLength={Number(content.goal_max_length ?? 200)}
            multiline
            testID="goal-input"
          />
        </View>
        <View style={{ gap: 4 }}>
          <AppText variant="subtitle" style={{ fontSize: 14 }}>
            {content.plan_prompt || "When / where will you try it?"}
          </AppText>
          <TextInput
            value={plan}
            onChangeText={setPlan}
            placeholder={content.plan_placeholder || "The moment this will happen"}
            style={styles.input}
            maxLength={Number(content.plan_max_length ?? 200)}
            multiline
            testID="plan-input"
          />
        </View>
      </View>

      {err ? (
        <AppText variant="body" color={colors.error}>
          {err}
        </AppText>
      ) : null}

      <Button
        title={saving ? "Saving…" : content.cta_next_label || "Save my goal and plan"}
        onPress={save}
        disabled={!canSave}
        testID="goal-save"
      />
    </View>
  );
}

function ScenarioSetStep({ content, onDone }: { content: any; onDone: () => void }) {
  const [config, setConfig] = useState<Week2ScenariosConfig | null>(null);
  const [body, setBody] = useState<Week2ScenarioBody | null>(null);
  const [feedback, setFeedback] = useState<Week2ScenarioFeedback | null>(null);
  const [draftSelection, setDraftSelection] = useState<string[]>([]);
  const [choiceId, setChoiceId] = useState<string | null>(null);
  const [followUpAnswer, setFollowUpAnswer] = useState<string | null>(null);
  const [savingSettings, setSavingSettings] = useState(false);
  const [savingResponse, setSavingResponse] = useState(false);
  const [err, setErr] = useState("");

  const loadConfig = useCallback(async () => {
    try {
      const c = await api.getWeek2ScenariosConfig();
      setConfig(c);
      return c;
    } catch (e: any) {
      setErr(e?.message || "Couldn't load scenarios.");
      return null;
    }
  }, []);

  useEffect(() => { loadConfig(); }, [loadConfig]);

  // Pick the next setting to show once settings are chosen.
  const nextSetting = useMemo(() => {
    if (!config || config.settings_chosen.length !== 3) return null;
    const responded = new Set(config.responded_settings);
    return config.settings_chosen.find((s) => !responded.has(s)) ?? null;
  }, [config]);

  useEffect(() => {
    // Only auto-fetch the next scenario body when the student has
    // moved on (no feedback card showing). Fetching while feedback is
    // visible would wipe it immediately after the submit — the student
    // never gets to read what we told them.
    if (feedback) return;
    if (nextSetting && (!body || body.setting !== nextSetting)) {
      setChoiceId(null);
      setFollowUpAnswer(null);
      api.getWeek2Scenario(nextSetting).then(setBody).catch((e: any) => setErr(e?.message || "Couldn't load the scenario."));
    } else if (!nextSetting && body) {
      setBody(null);
    }
  }, [nextSetting, body, feedback]);

  const toggleSetting = (id: string) => {
    setDraftSelection((prev) => {
      if (prev.includes(id)) return prev.filter((v) => v !== id);
      if (prev.length >= 3) return prev;
      return [...prev, id];
    });
  };

  const saveSettings = async () => {
    if (draftSelection.length !== 3) return;
    setSavingSettings(true); setErr("");
    try {
      const c = await api.setWeek2Settings(draftSelection);
      setConfig(c);
    } catch (e: any) {
      setErr(e?.message || "Couldn't save your settings. Try again.");
    } finally {
      setSavingSettings(false);
    }
  };

  const openScenario = async (setting: string) => {
    setFeedback(null);
    setChoiceId(null);
    setFollowUpAnswer(null);
    setErr("");
    try {
      const b = await api.getWeek2Scenario(setting);
      setBody(b);
    } catch (e: any) {
      setErr(e?.message || "Couldn't open that setting.");
    }
  };

  const submitChoice = async () => {
    if (!body || !choiceId) return;
    setSavingResponse(true); setErr("");
    try {
      const res = await api.respondWeek2Scenario(body.setting, {
        choice_id: choiceId,
        follow_up: body.follow_up && followUpAnswer
          ? { id: body.follow_up.id, answer: followUpAnswer }
          : null,
        shown_option_ids: body.choices.map((c) => c.id),
        shown_option_payload: body.choices as any,
      });
      // Only setFeedback here. We deliberately do NOT update config in
      // the same event handler: that would advance `nextSetting` and the
      // body-fetching useEffect would race the feedback render and wipe
      // it before the student reads anything. `onContinue` refreshes
      // config when the student is ready.
      setFeedback(res.feedback);
    } catch (e: any) {
      setErr(e?.message || "Couldn't save your choice.");
    } finally {
      setSavingResponse(false);
    }
  };

  if (!config) {
    return <ActivityIndicator color={colors.brandPrimary} />;
  }

  // 1) Settings not chosen yet.
  if (config.settings_chosen.length !== 3) {
    return (
      <View style={{ gap: spacing.md }} testID="scenarios-settings-picker">
        <AppText variant="body">{config.settings_question}</AppText>
        <AppText variant="caption" color={colors.onSurfaceSecondary}>
          Pick exactly three. These decide which scenarios you&apos;ll practice.
        </AppText>
        <View style={styles.chipRow}>
          {config.available_settings.map((opt) => {
            const on = draftSelection.includes(opt.id);
            return (
              <Pressable
                key={opt.id}
                onPress={() => toggleSetting(opt.id)}
                style={[styles.chip, on && styles.chipOn]}
                testID={`settings-chip-${opt.id}`}
              >
                <AppText variant="body" style={{ fontSize: 13 }} color={on ? colors.onBrandPrimary : colors.onSurface}>
                  {opt.label}
                </AppText>
              </Pressable>
            );
          })}
        </View>
        {err ? <AppText variant="body" color={colors.error}>{err}</AppText> : null}
        <Button
          title={savingSettings ? "Saving…" : "Start scenarios"}
          onPress={saveSettings}
          disabled={savingSettings || draftSelection.length !== 3}
          testID="settings-start"
        />
      </View>
    );
  }

  // 2) Settings chosen — show the next unanswered scenario OR the completion state.
  if (nextSetting && body) {
    return (
      <ScenarioView
        body={body}
        choiceId={choiceId}
        setChoiceId={setChoiceId}
        followUpAnswer={followUpAnswer}
        setFollowUpAnswer={setFollowUpAnswer}
        feedback={feedback}
        submitChoice={submitChoice}
        savingResponse={savingResponse}
        err={err}
        onContinue={async () => {
          setFeedback(null);
          setChoiceId(null);
          setFollowUpAnswer(null);
          await loadConfig();
        }}
      />
    );
  }

  // 3) Three (or more) done. Completion state + Try another + Continue.
  const remainingSettings = config.available_settings.filter(
    (s) => !config.responded_settings.includes(s.id),
  );

  if (body) {
    // Mid-flow after "Try another" — same ScenarioView.
    return (
      <ScenarioView
        body={body}
        choiceId={choiceId}
        setChoiceId={setChoiceId}
        followUpAnswer={followUpAnswer}
        setFollowUpAnswer={setFollowUpAnswer}
        feedback={feedback}
        submitChoice={submitChoice}
        savingResponse={savingResponse}
        err={err}
        onContinue={async () => {
          setBody(null);
          setFeedback(null);
          setChoiceId(null);
          setFollowUpAnswer(null);
          await loadConfig();
        }}
      />
    );
  }

  return (
    <View style={{ gap: spacing.md }} testID="scenarios-complete">
      <View style={[cardStyle, { gap: spacing.sm }]}>
        <View style={styles.doneRow}>
          <Feather name="check-circle" size={22} color={colors.brandPrimary} />
          <AppText variant="subtitle" style={{ fontSize: 16 }}>
            {config.completed_count} of {config.required_scenarios} done — nice work.
          </AppText>
        </View>
        {config.completion_message ? (
          <AppText variant="body">{config.completion_message}</AppText>
        ) : null}
      </View>

      {remainingSettings.length > 0 ? (
        <View style={{ gap: spacing.sm }}>
          <AppText variant="caption">
            {content.try_another_label || "Try another setting"} (optional — no extra points)
          </AppText>
          <View style={styles.chipRow}>
            {remainingSettings.map((opt) => (
              <Pressable
                key={opt.id}
                onPress={() => openScenario(opt.id)}
                style={[styles.chip]}
                testID={`scenarios-try-${opt.id}`}
              >
                <AppText variant="body" style={{ fontSize: 13 }}>
                  {opt.label}
                </AppText>
              </Pressable>
            ))}
          </View>
        </View>
      ) : null}

      {err ? <AppText variant="body" color={colors.error}>{err}</AppText> : null}

      <Button
        title={content.cta_next_label || "Continue"}
        onPress={onDone}
        testID="scenarios-done-continue"
      />
    </View>
  );
}

function ScenarioView({
  body, choiceId, setChoiceId, followUpAnswer, setFollowUpAnswer,
  feedback, submitChoice, savingResponse, err, onContinue,
}: {
  body: Week2ScenarioBody;
  choiceId: string | null; setChoiceId: (id: string) => void;
  followUpAnswer: string | null; setFollowUpAnswer: (v: string | null) => void;
  feedback: Week2ScenarioFeedback | null;
  submitChoice: () => void; savingResponse: boolean; err: string;
  onContinue: () => void;
}) {
  if (body.coming_soon) {
    return (
      <View style={[cardStyle, { gap: spacing.sm }]} testID="scenario-coming-soon">
        <Feather name="clock" size={22} color={colors.brandPrimary} />
        <AppText variant="subtitle">This scenario is being prepared.</AppText>
        <AppText variant="body">{body.prompt || "The team is finishing this one."}</AppText>
        <Button title="Pick another setting" onPress={onContinue} variant="secondary" />
      </View>
    );
  }
  const highlighted = body.highlighted_nutrients || [];
  const labels = body.nutrient_display_labels || {};
  return (
    <View style={{ gap: spacing.md }} testID={`scenario-${body.setting}`}>
      <View style={[cardStyle, { gap: spacing.sm }]}>
        <AppText variant="caption" color={colors.brandPrimary} style={{ letterSpacing: 0.4 }}>
          {body.label?.toUpperCase()}
        </AppText>
        <AppText variant="body">{body.prompt}</AppText>
      </View>

      {body.choices.map((c) => (
        <ChoiceCard
          key={c.id}
          choice={c}
          selected={choiceId === c.id}
          onSelect={() => setChoiceId(c.id)}
          source={body.source}
          highlighted={highlighted}
          labels={labels}
        />
      ))}

      {body.follow_up ? (
        <View style={[cardStyle, { gap: spacing.sm }]} testID="scenario-follow-up">
          <AppText variant="caption">Optional follow-up</AppText>
          <AppText variant="subtitle" style={{ fontSize: 14 }}>
            {body.follow_up.prompt}
          </AppText>
          <View style={styles.chipRow}>
            {body.follow_up.options.map((opt) => (
              <Pressable
                key={opt}
                onPress={() => setFollowUpAnswer(followUpAnswer === opt ? null : opt)}
                style={[styles.chip, followUpAnswer === opt && styles.chipOn]}
                testID={`follow-up-${opt.toLowerCase().replace(/\s+/g, "-")}`}
              >
                <AppText variant="body" style={{ fontSize: 13 }} color={followUpAnswer === opt ? colors.onBrandPrimary : colors.onSurface}>
                  {opt}
                </AppText>
              </Pressable>
            ))}
          </View>
        </View>
      ) : null}

      {feedback ? (
        <View style={[cardStyle, styles.feedbackCard]} testID="scenario-feedback">
          <View style={styles.feedbackHeader}>
            <Feather name="message-circle" size={18} color={colors.brandPrimary} />
            <AppText variant="subtitle" style={{ fontSize: 15 }}>
              {feedback.chosen_name || "Your pick"}
            </AppText>
            {feedback.draft ? (
              <AppText variant="caption" color={colors.onSurfaceSecondary}>
                (draft copy)
              </AppText>
            ) : null}
          </View>
          <AppText variant="body">{feedback.body}</AppText>
        </View>
      ) : null}

      {err ? <AppText variant="body" color={colors.error}>{err}</AppText> : null}

      {feedback ? (
        <Button
          title="Continue"
          onPress={onContinue}
          testID="scenario-continue"
        />
      ) : (
        <Button
          title={savingResponse ? "Saving…" : "Save my pick"}
          onPress={submitChoice}
          disabled={!choiceId || savingResponse}
          testID="scenario-submit"
        />
      )}
    </View>
  );
}

function ChoiceCard({
  choice, selected, onSelect, source, highlighted, labels,
}: {
  choice: Week2ScenarioChoice;
  selected: boolean;
  onSelect: () => void;
  source: Week2ScenarioBody["source"];
  highlighted: string[];
  labels: Record<string, string>;
}) {
  const title = choice.name || choice.text || choice.id;
  const servingDisplay = choice.serving_size || choice.serving || null;
  const dvForNutrient = (n: string): number | undefined => {
    switch (n) {
      case "saturated_fat_g": return choice.sat_fat_dv_pct;
      case "sodium_mg": return choice.sodium_dv_pct;
      case "added_sugars_g": return choice.added_sugars_dv_pct;
      case "fiber_g": return choice.fiber_dv_pct;
      default: return undefined;
    }
  };
  return (
    <Pressable
      onPress={onSelect}
      style={[cardStyle, styles.choiceCard, selected && styles.choiceCardOn]}
      testID={`scenario-choice-${choice.id}`}
      accessibilityRole="button"
      accessibilityState={{ selected }}
    >
      <View style={styles.choiceHeader}>
        <Feather
          name={selected ? "check-circle" : "circle"}
          size={18}
          color={selected ? colors.brandPrimary : colors.onSurfaceSecondary}
        />
        <AppText variant="subtitle" style={{ fontSize: 15, flex: 1 }}>{title}</AppText>
      </View>
      {source !== "scripted" && servingDisplay ? (
        <AppText variant="caption" color={colors.onSurfaceSecondary}>
          Serving: {servingDisplay}
        </AppText>
      ) : null}
      {/* Calories on the Nutrition Facts label. Nutrition team 2026-11-06,
          item 3: "Calories can be visible" on the Week 2 lesson labels
          (grocery and dining). Renders on top of the label, separate from
          the 4 highlighted nutrients the scenario feedback uses. */}
      {source !== "scripted" && typeof choice.calories === "number" ? (
        <AppText variant="body" style={{ fontSize: 14, fontFamily: fonts.semibold }}>
          Calories: {choice.calories}
        </AppText>
      ) : null}
      {source !== "scripted" && highlighted.length ? (
        <View style={styles.nutrientGrid}>
          {highlighted.map((n) => {
            const val = (choice as any)[n] as number | undefined;
            if (val === undefined || val === null) return null;
            const unit = n.endsWith("_g") ? "g" : n.endsWith("_mg") ? "mg" : "";
            const dv = dvForNutrient(n);
            return (
              <View key={n} style={styles.nutrientCell}>
                <AppText variant="caption" color={colors.onSurfaceSecondary}>
                  {labels[n] || n}
                </AppText>
                <AppText variant="body" style={{ fontSize: 14, fontFamily: fonts.semibold }}>
                  {val}{unit}
                  {dv !== undefined ? `  (${dv}% DV)` : ""}
                </AppText>
              </View>
            );
          })}
        </View>
      ) : null}
    </Pressable>
  );
}

function PlanningStep({
  content,
  editPlanId,
  onDone,
}: {
  content: any;
  editPlanId: string | null;
  onDone: () => void;
}) {
  const [config, setConfig] = useState<PlanningConfig | null>(null);
  const [editing, setEditing] = useState<Record<string, any> | null>(null);

  // --- p1: situation
  const [setting, setSetting] = useState<string | null>(null);
  const [customSetting, setCustomSetting] = useState<string>("");
  const [dayIso, setDayIso] = useState<string | null>(null);
  const [occasion, setOccasion] = useState<string | null>(null);
  // --- p2: action
  const [actions, setActions] = useState<string[]>([]);
  const [chosenAction, setChosenAction] = useState<string | null>(null);
  const [customAction, setCustomAction] = useState<string>("");
  // --- p3: barrier
  const [barrier, setBarrier] = useState<{ id: string; label: string } | null>(null);
  const [barrierCustom, setBarrierCustom] = useState<string>("");
  // --- p4: coping
  const [copings, setCopings] = useState<string[]>([]);
  const [chosenCoping, setChosenCoping] = useState<string | null>(null);
  const [customCoping, setCustomCoping] = useState<string>("");
  // --- p5: plan management + reminder
  const [planManagement, setPlanManagement] = useState<string | null>(null);
  const [reminderTime, setReminderTime] = useState<string>("");

  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [result, setResult] = useState<PlanningSubmitResult | null>(null);

  useEffect(() => {
    (async () => {
      const c = await api.getWeek2PlanningConfig();
      setConfig(c);
      if (editPlanId) {
        try {
          const plan = await api.getPlan(editPlanId);
          setEditing(plan);
          const sit = plan.situation || {};
          setSetting(sit.setting ?? null);
          setCustomSetting(sit.custom_setting_text ?? "");
          setDayIso(sit.day ?? null);
          setOccasion(sit.occasion ?? null);
          const act = plan.action || {};
          if (act.source === "preset") setChosenAction(act.text);
          else setCustomAction(act.text ?? "");
          const br = plan.barrier || {};
          if (br.id) setBarrier({ id: br.id, label: br.label });
          setBarrierCustom(br.custom_text ?? "");
          const cp = plan.coping || {};
          if (cp.source === "preset") setChosenCoping(cp.text);
          else setCustomCoping(cp.text ?? "");
          setReminderTime((plan.reminder || {}).time ?? "");
        } catch {
          /* fall through to a fresh form */
        }
      }
    })();
  }, [editPlanId]);

  // Re-fetch the matched action list whenever setting changes.
  useEffect(() => {
    if (!setting) {
      setActions([]);
      return;
    }
    api.getWeek2PlanningActions(null, setting).then((r) => setActions(r.actions)).catch(() => setActions([]));
  }, [setting]);
  // Re-fetch coping list whenever barrier changes.
  useEffect(() => {
    if (!barrier) {
      setCopings([]);
      return;
    }
    api.getWeek2PlanningCoping(barrier.id).then((r) => setCopings(r.coping_options)).catch(() => setCopings([]));
  }, [barrier]);
  // Default reminder time: one hour before the chosen occasion.
  useEffect(() => {
    if (!config || !occasion) return;
    const occ = config.occasions.find((o) => o.id === occasion);
    if (occ && !reminderTime) setReminderTime(occ.default_reminder_time);
  }, [config, occasion, reminderTime]);

  const useWeek1Situation = () => {
    const w1 = config?.week1_plan;
    if (!w1) return;
    const parts = (w1.situation_text || "").toLowerCase();
    // Best-effort: parse the Week 1 occasion if the plan carries one.
    const occ = config?.occasions.find((o) => parts.includes(o.id));
    if (occ) setOccasion(occ.id);
  };

  const actionTextForSubmit = (): { text: string; source: "preset" | "custom"; preset_index?: number } | null => {
    if (chosenAction) {
      const idx = actions.indexOf(chosenAction);
      return { text: chosenAction, source: "preset", preset_index: idx >= 0 ? idx : undefined };
    }
    if (customAction.trim()) {
      return { text: customAction.trim(), source: "custom" };
    }
    return null;
  };

  const copingTextForSubmit = (): { text: string; source: "preset" | "custom" } | null => {
    if (chosenCoping) return { text: chosenCoping, source: "preset" };
    if (customCoping.trim()) return { text: customCoping.trim(), source: "custom" };
    return null;
  };

  const canSubmit =
    !submitting &&
    !!setting &&
    (setting !== "somewhere_else" || customSetting.trim().length > 0) &&
    !!dayIso &&
    !!occasion &&
    !!actionTextForSubmit() &&
    !!barrier &&
    !!copingTextForSubmit() &&
    !!planManagement;

  const previewSummary = useMemo(() => {
    if (!config) return "";
    const settingLabel = setting === "somewhere_else"
      ? customSetting.trim()
      : (config.settings.find((s) => s.id === setting)?.label ?? "");
    const occ = config.occasions.find((o) => o.id === occasion);
    const dayLabel = config.days.find((d) => d.iso === dayIso)?.label;
    const action = actionTextForSubmit()?.text || "";
    const barrierLabel = barrier?.label || "";
    const coping = copingTextForSubmit()?.text || "";
    const rem = reminderTime;
    if (planManagement === "keep_week1_only") {
      return config.completion_summary_keep_only_template || "";
    }
    const sit = [dayLabel, occ?.label?.toLowerCase() && settingLabel ? `${occ.label.toLowerCase()} at ${settingLabel.toLowerCase()}` : (occ?.label?.toLowerCase() || settingLabel)]
      .filter(Boolean).join(", ");
    const tpl = config.completion_summary_template || "";
    return tpl
      .replace("{situation_and_time}", sit)
      .replace("{action}", action.replace(/^DRAFT —\s*/, "").replace(/\.$/, ""))
      .replace("{barrier}", (barrierLabel || "").toLowerCase())
      .replace("{coping}", coping.replace(/^DRAFT —\s*/, "").replace(/\.$/, ""))
      .replace("{reminder_time}", rem ? `at ${rem}` : "at the time you set");
  }, [config, setting, customSetting, dayIso, occasion, actionTextForSubmit, barrier, copingTextForSubmit, reminderTime, planManagement]);

  const submit = async () => {
    const act = actionTextForSubmit();
    const cop = copingTextForSubmit();
    if (!setting || !dayIso || !occasion || !act || !barrier || !cop || !planManagement) return;
    setSubmitting(true); setSubmitError("");
    try {
      const body: PlanningSubmit = {
        situation: {
          setting,
          custom_setting_text: setting === "somewhere_else" ? customSetting.trim() : undefined,
          day: dayIso,
          day_label: config?.days.find((d) => d.iso === dayIso)?.label,
          occasion,
        },
        action: act,
        barrier: {
          id: barrier.id,
          label: barrier.label,
          custom_text: barrierCustom.trim() || undefined,
        },
        coping: cop,
        reminder: planManagement === "keep_week1_only" ? {} : (reminderTime ? { time: reminderTime } : {}),
        plan_management: planManagement as PlanningSubmit["plan_management"],
        edit_plan_id: editPlanId ?? undefined,
      };
      const r = await api.submitWeek2Planning(body);
      setResult(r);
    } catch (e: any) {
      setSubmitError(e?.message || "Couldn't save your plan. Try again.");
    } finally {
      setSubmitting(false);
    }
  };

  if (!config) return <ActivityIndicator color={colors.brandPrimary} />;

  if (result) {
    return (
      <View style={{ gap: spacing.md }} testID="planning-complete">
        <View style={[cardStyle, styles.feedbackCard]}>
          <View style={styles.feedbackHeader}>
            <Feather name="check-circle" size={22} color={colors.brandPrimary} />
            <AppText variant="subtitle" style={{ fontSize: 16 }}>Your plan is saved</AppText>
          </View>
          <AppText variant="body">{result.summary}</AppText>
        </View>
        {result.plans.length ? (
          <View style={[cardStyle, { gap: spacing.sm }]} testID="planning-active-plans">
            <AppText variant="caption">Active plans on your Today</AppText>
            {result.plans.map((p) => (
              <View key={p.id} style={{ gap: 2 }}>
                <AppText variant="subtitle" style={{ fontSize: 14 }}>
                  Week {p.source_week}: {p.action_text}
                </AppText>
                <AppText variant="caption">
                  {p.situation_text}{p.reminder_time ? ` · reminder ${p.reminder_time}` : ""}
                </AppText>
              </View>
            ))}
          </View>
        ) : null}
        <Button title="Back to Today" onPress={onDone} testID="planning-back-today" />
      </View>
    );
  }

  const settingsOpts = config.settings;
  const barriers = config.barriers;
  const mgmtOpts = config.plan_management_options;

  return (
    <View style={{ gap: spacing.md }} testID="week-step-planning">
      {config.intro ? (
        <View style={[cardStyle, { gap: spacing.sm }]} testID="planning-intro">
          <AppText variant="body">{config.intro}</AppText>
          {config.week1_plan ? (
            <View style={{ gap: 2 }} testID="planning-week1-card">
              <AppText variant="caption" color={colors.onSurfaceSecondary}>Your Week 1 plan</AppText>
              <AppText variant="body" style={{ fontFamily: fonts.semibold }}>{config.week1_plan.goal}</AppText>
              {config.week1_plan.situation_text ? (
                <AppText variant="caption">{config.week1_plan.situation_text}</AppText>
              ) : null}
            </View>
          ) : null}
        </View>
      ) : null}

      <PromptCard label="1" testID="planning-p1">
        <AppText variant="subtitle" style={{ fontSize: 15 }}>
          {config.prompts?.p1_moment?.prompt || "Pick one eating situation…"}
        </AppText>
        {config.week1_plan ? (
          <Pressable onPress={useWeek1Situation} style={styles.useExample} testID="planning-use-week1">
            <Feather name="corner-down-right" size={14} color={colors.brandPrimary} />
            <AppText variant="caption" color={colors.brandPrimary}>
              {config.prompts?.p1_moment?.use_week1_label || "Use my Week 1 situation"}
            </AppText>
          </Pressable>
        ) : null}
        <View style={styles.chipRow}>
          {settingsOpts.map((o) => (
            <Pressable
              key={o.id}
              onPress={() => setSetting(o.id === setting ? null : o.id)}
              style={[styles.chip, setting === o.id && styles.chipOn]}
              testID={`planning-setting-${o.id}`}
            >
              <AppText variant="body" style={{ fontSize: 13 }} color={setting === o.id ? colors.onBrandPrimary : colors.onSurface}>
                {o.label}
              </AppText>
            </Pressable>
          ))}
        </View>
        {setting === "somewhere_else" ? (
          <TextInput
            value={customSetting}
            onChangeText={setCustomSetting}
            placeholder={config.prompts?.p1_moment?.custom_text_label || "Tell us where"}
            style={styles.input}
            maxLength={120}
            testID="planning-setting-custom"
          />
        ) : null}

        <AppText variant="caption" style={{ marginTop: spacing.sm }}>Day</AppText>
        <View style={styles.chipRow}>
          {config.days.map((d) => (
            <Pressable
              key={d.iso}
              onPress={() => setDayIso(d.iso === dayIso ? null : d.iso)}
              style={[styles.chip, dayIso === d.iso && styles.chipOn]}
              testID={`planning-day-${d.iso}`}
            >
              <AppText variant="body" style={{ fontSize: 13 }} color={dayIso === d.iso ? colors.onBrandPrimary : colors.onSurface}>
                {d.label}
              </AppText>
            </Pressable>
          ))}
        </View>
        <AppText variant="caption" style={{ marginTop: spacing.sm }}>Occasion</AppText>
        <View style={styles.chipRow}>
          {config.occasions.map((o) => (
            <Pressable
              key={o.id}
              onPress={() => setOccasion(o.id === occasion ? null : o.id)}
              style={[styles.chip, occasion === o.id && styles.chipOn]}
              testID={`planning-occasion-${o.id}`}
            >
              <AppText variant="body" style={{ fontSize: 13 }} color={occasion === o.id ? colors.onBrandPrimary : colors.onSurface}>
                {o.label}
              </AppText>
            </Pressable>
          ))}
        </View>
      </PromptCard>

      <PromptCard label="2" testID="planning-p2">
        <AppText variant="subtitle" style={{ fontSize: 15 }}>
          {config.prompts?.p2_action?.prompt || "What will you look for or choose there?"}
        </AppText>
        {actions.map((a, i) => (
          <Pressable
            key={i}
            onPress={() => setChosenAction(a === chosenAction ? null : a)}
            style={[styles.actionRow, chosenAction === a && styles.chipOn]}
            testID={`planning-action-${i}`}
          >
            <Feather
              name={chosenAction === a ? "check-circle" : "circle"}
              size={16}
              color={chosenAction === a ? colors.onBrandPrimary : colors.brandPrimary}
            />
            <AppText variant="body" style={{ fontSize: 14, flex: 1 }} color={chosenAction === a ? colors.onBrandPrimary : colors.onSurface}>
              {a}
            </AppText>
          </Pressable>
        ))}
        <TextInput
          value={customAction}
          onChangeText={(t) => { setCustomAction(t); if (t.trim()) setChosenAction(null); }}
          placeholder={config.prompts?.p2_action?.write_my_own_label || "Write my own action"}
          style={styles.input}
          maxLength={200}
          multiline
          testID="planning-action-custom"
        />
      </PromptCard>

      <PromptCard label="3" testID="planning-p3">
        <AppText variant="subtitle" style={{ fontSize: 15 }}>
          {config.prompts?.p3_barrier?.prompt || "What's one thing that could make this harder?"}
        </AppText>
        <View style={styles.chipRow}>
          {barriers.map((b) => (
            <Pressable
              key={b.id}
              onPress={() => setBarrier(barrier?.id === b.id ? null : { id: b.id, label: b.label })}
              style={[styles.chip, barrier?.id === b.id && styles.chipOn]}
              testID={`planning-barrier-${b.id}`}
            >
              <AppText variant="body" style={{ fontSize: 13 }} color={barrier?.id === b.id ? colors.onBrandPrimary : colors.onSurface}>
                {b.label}
              </AppText>
            </Pressable>
          ))}
        </View>
        <TextInput
          value={barrierCustom}
          onChangeText={setBarrierCustom}
          placeholder={config.prompts?.p3_barrier?.optional_text_label || "Add a note (optional)"}
          style={styles.input}
          maxLength={200}
          testID="planning-barrier-note"
        />
      </PromptCard>

      <PromptCard label="4" testID="planning-p4">
        <AppText variant="subtitle" style={{ fontSize: 15 }}>
          {config.prompts?.p4_coping?.prompt || "If that happens, what will you do?"}
        </AppText>
        {copings.map((c, i) => (
          <Pressable
            key={i}
            onPress={() => setChosenCoping(c === chosenCoping ? null : c)}
            style={[styles.actionRow, chosenCoping === c && styles.chipOn]}
            testID={`planning-coping-${i}`}
          >
            <Feather
              name={chosenCoping === c ? "check-circle" : "circle"}
              size={16}
              color={chosenCoping === c ? colors.onBrandPrimary : colors.brandPrimary}
            />
            <AppText variant="body" style={{ fontSize: 14, flex: 1 }} color={chosenCoping === c ? colors.onBrandPrimary : colors.onSurface}>
              {c}
            </AppText>
          </Pressable>
        ))}
        <TextInput
          value={customCoping}
          onChangeText={(t) => { setCustomCoping(t); if (t.trim()) setChosenCoping(null); }}
          placeholder={config.prompts?.p4_coping?.write_my_own_label || "Write my own"}
          style={styles.input}
          maxLength={200}
          multiline
          testID="planning-coping-custom"
        />
      </PromptCard>

      <PromptCard label="5" testID="planning-p5">
        <AppText variant="subtitle" style={{ fontSize: 15 }}>
          {config.prompts?.p5_plan_management?.prompt || "What do you want to do with last week's plan?"}
        </AppText>
        {mgmtOpts.map((o) => (
          <Pressable
            key={o.id}
            onPress={() => setPlanManagement(o.id === planManagement ? null : o.id)}
            style={[styles.actionRow, planManagement === o.id && styles.chipOn]}
            testID={`planning-mgmt-${o.id}`}
          >
            <Feather
              name={planManagement === o.id ? "check-circle" : "circle"}
              size={16}
              color={planManagement === o.id ? colors.onBrandPrimary : colors.brandPrimary}
            />
            <AppText variant="body" style={{ fontSize: 14, flex: 1 }} color={planManagement === o.id ? colors.onBrandPrimary : colors.onSurface}>
              {o.label}
            </AppText>
          </Pressable>
        ))}
        {planManagement && planManagement !== "keep_week1_only" ? (
          <View style={{ gap: 4, marginTop: spacing.sm }}>
            <AppText variant="caption">{config.prompts?.p5_plan_management?.reminder_prompt || "What's a good time for a reminder?"}</AppText>
            <TextInput
              value={reminderTime}
              onChangeText={setReminderTime}
              placeholder="HH:MM (24h)"
              style={styles.input}
              maxLength={5}
              testID="planning-reminder-time"
            />
            <AppText variant="caption" color={colors.onSurfaceSecondary}>
              {config.prompts?.p5_plan_management?.reminder_note || "Default is one hour before the eating moment."}
            </AppText>
          </View>
        ) : null}
      </PromptCard>

      {previewSummary ? (
        <View style={[cardStyle, styles.previewMessage]} testID="planning-preview">
          <Feather name="arrow-right-circle" size={18} color={colors.brandPrimary} />
          <AppText variant="body" style={{ flex: 1 }}>{previewSummary}</AppText>
        </View>
      ) : null}

      {submitError ? (
        <AppText variant="body" color={colors.error}>{submitError}</AppText>
      ) : null}

      <Button
        title={submitting ? "Saving…" : (content.cta_next_label || "Save my plan")}
        onPress={submit}
        disabled={!canSubmit}
        testID="planning-submit"
      />
    </View>
  );
}

function ReviewStep({ content, onDone }: { content: any; onDone: () => void }) {
  return (
    <View style={{ gap: spacing.md }} testID="week-step-review">
      <View style={[cardStyle, { gap: spacing.sm }]}>
        {content.intro ? <AppText variant="body">{content.intro}</AppText> : null}
      </View>
      <Button title={content.cta_next_label || "Open Today"} onPress={onDone} testID="review-open-today" />
    </View>
  );
}

function ComingSoonStep({ content }: { content: any }) {
  return (
    <View style={[cardStyle, { gap: spacing.md }]} testID="week-step-coming-soon">
      <Feather name="clock" size={28} color={colors.brandPrimary} />
      <AppText variant="subtitle">Coming in the next release</AppText>
      <AppText variant="body">
        {content.summary ||
          "This step is being finished. You'll see it unlock in a later update — no action needed from you right now."}
      </AppText>
    </View>
  );
}

const styles = StyleSheet.create({
  c: { flex: 1, backgroundColor: colors.surface },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.sm,
  },
  scroll: {
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing["3xl"],
    gap: spacing.md,
  },
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  doneBadge: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.surfaceSecondary,
  },
  videoBox: {
    height: 160,
    borderRadius: radius.lg,
    backgroundColor: colors.surfaceTertiary,
    alignItems: "center",
    justifyContent: "center",
  },
  candidateRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    paddingVertical: 4,
  },
  barRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    paddingVertical: 6,
  },
  barTrack: {
    flex: 1.4,
    height: 14,
    borderRadius: radius.pill,
    backgroundColor: colors.surfaceTertiary,
    overflow: "hidden",
  },
  barFill: {
    height: "100%",
    backgroundColor: colors.brandPrimary,
    opacity: 0.9,
  },
  subBarGroup: {
    gap: 6,
    paddingLeft: spacing.md,
    paddingBottom: spacing.sm,
    marginTop: -2,
  },
  subBarRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
  },
  subBarTrack: {
    height: 10,
  },
  subBarFill: {
    opacity: 0.7,
  },
  chipRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.sm,
  },
  chip: {
    paddingVertical: 8,
    paddingHorizontal: 14,
    borderRadius: radius.pill,
    backgroundColor: colors.surfaceTertiary,
    borderWidth: 1,
    borderColor: colors.border,
  },
  chipOn: {
    backgroundColor: colors.brandPrimary,
    borderColor: colors.brandPrimary,
  },
  input: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    padding: spacing.sm,
    minHeight: 68,
    textAlignVertical: "top",
    fontFamily: fonts.regular,
    color: colors.onSurface,
    backgroundColor: colors.surface,
  },
  previewMessage: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: spacing.sm,
    backgroundColor: colors.surfaceSecondary,
  },
  promptHeader: {
    flexDirection: "row",
    alignItems: "center",
    marginBottom: 4,
  },
  promptNum: {
    width: 22,
    height: 22,
    borderRadius: radius.pill,
    backgroundColor: colors.brandPrimary,
    alignItems: "center",
    justifyContent: "center",
  },
  progressTrack: {
    height: 36,
    borderRadius: radius.md,
    backgroundColor: colors.surfaceTertiary,
    overflow: "hidden",
    justifyContent: "center",
  },
  progressFill: {
    position: "absolute",
    left: 0,
    top: 0,
    bottom: 0,
    width: "55%",
    backgroundColor: colors.brandPrimary,
    opacity: 0.9,
  },
  progressLabel: {
    paddingHorizontal: spacing.md,
    fontSize: 12,
  },
  exampleCard: {
    gap: spacing.xs,
    backgroundColor: colors.surfaceSecondary,
  },
  useExample: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    marginTop: 4,
  },
  carriedRow: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: spacing.sm,
  },
  choiceCard: {
    gap: spacing.sm,
    borderWidth: 1,
    borderColor: colors.border,
  },
  choiceCardOn: {
    borderColor: colors.brandPrimary,
    backgroundColor: colors.surfaceSecondary,
  },
  choiceHeader: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
  },
  nutrientGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.md,
  },
  nutrientCell: {
    flexBasis: "45%",
    gap: 2,
  },
  doneRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
  },
  feedbackCard: {
    gap: spacing.sm,
    backgroundColor: colors.surfaceSecondary,
  },
  feedbackHeader: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
  },
  actionRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    borderRadius: radius.md,
    backgroundColor: colors.surfaceSecondary,
    borderWidth: 1,
    borderColor: colors.border,
  },
});
