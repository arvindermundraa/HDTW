import React, { useCallback, useEffect, useMemo, useState } from "react";
import { View, StyleSheet, Pressable, ScrollView, ActivityIndicator, TextInput, KeyboardAvoidingView, Platform } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Feather } from "@expo/vector-icons";
import { AppText, Button, ProgressBar } from "@/src/components/ui";
import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { goBack } from "@/src/navigation";
import { colors, spacing, fonts, fontSize, radius } from "@/src/theme";

// Schema-driven renderer for the LLHS Nutrition & Lifestyle Profile survey.
// Per the review notes, this questionnaire is personalization/context for
// the coach — NOT a diet-quality screener. Baseline diet quality comes from
// ASA24 recalls, imported separately by the research team. The schema
// (sections + questions, including skip-logic `condition`s) comes entirely
// from GET /onboarding/profile-survey — no question content is hardcoded
// here, so the nutrition team's final copy can change server-side without
// a client release.

type Option = { id: string; label: string; exclusive?: boolean };
type Question = {
  id: string;
  section: string;
  type: "number" | "single_select" | "multi_select" | "text";
  label: string;
  options?: Option[];
  max_length?: number;
  min?: number;
  max?: number;
  required?: boolean;
  condition?: { question: string; in: string[] };
  // Optional grouping heading for a run of related questions (e.g. the
  // Food Environment frequency grid). Rendered once, above the first
  // question of the run.
  group?: string;
  group_label?: string;
};
type Section = { id: string; title: string };

// Fallbacks for when the schema doesn't (yet) carry min/max, `exclusive`,
// or a group heading — keeps behaviour correct across backend versions.
const NUMBER_RANGE_FALLBACK: Record<string, { min: number; max: number }> = {
  age: { min: 16, max: 99 },
  weekly_work_hours: { min: 0, max: 80 },
};
const FREQ_GROUP_FALLBACK = { id: "frequency", label: "How often do you typically do each of the following?" };

function numberRange(q: Question): { min?: number; max?: number } {
  const fb = NUMBER_RANGE_FALLBACK[q.id];
  return { min: q.min ?? fb?.min, max: q.max ?? fb?.max };
}

function isExclusiveOption(q: Question, opt: Option): boolean {
  const opts = q.options || [];
  if (opts.some((o) => o.exclusive !== undefined)) return !!opt.exclusive;
  if (q.id === "dietary_restrictions") return opt.id === "none";
  if (q.id === "support_needs") return opt.label.trim().toLowerCase().startsWith("none of these");
  return false;
}

function groupOf(q: Question): { id: string; label: string } | null {
  if (q.group_label) return { id: q.group || q.group_label, label: q.group_label };
  if (q.id.startsWith("freq_")) return FREQ_GROUP_FALLBACK;
  return null;
}

function conditionMet(cond: Question["condition"], answers: Record<string, any>): boolean {
  if (!cond) return true;
  const val = answers[cond.question];
  if (Array.isArray(val)) return val.some((v) => cond.in.includes(v));
  return cond.in.includes(val);
}

function isEmpty(v: any) {
  return v === undefined || v === null || v === "" || (Array.isArray(v) && v.length === 0);
}

// Skip logic on submit: drop answers to questions whose condition is no
// longer met (e.g. "Please specify" text after its "Other" option was
// unselected). Repeats until stable so chained conditions (kitchen_access →
// appliance_refrigerator → appliance_refrigerator_size) are stripped too.
function pruneAnswers(questions: Question[], answers: Record<string, any>): Record<string, any> {
  let out: Record<string, any> = {};
  for (const [k, v] of Object.entries(answers)) if (!isEmpty(v)) out[k] = v;
  let changed = true;
  while (changed) {
    changed = false;
    for (const q of questions) {
      if (q.id in out && !conditionMet(q.condition, out)) {
        const { [q.id]: _drop, ...rest } = out;
        out = rest;
        changed = true;
      }
    }
  }
  return out;
}

export default function Onboarding() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { mode } = useLocalSearchParams<{ mode?: string }>();
  const isEdit = mode === "edit";
  const { user, refresh } = useAuth();
  const [sections, setSections] = useState<Section[]>([]);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [sectionIndex, setSectionIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<string, any>>({});
  // Edit mode: the answers we started from (null = backend didn't send any).
  const [initialAnswers, setInitialAnswers] = useState<Record<string, any> | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState("");

  const load = useCallback(() => {
    setLoadError("");
    api
      .getProfileSurvey()
      .then((d: any) => {
        setSections(d.sections || []);
        setQuestions(d.questions || []);
        if (isEdit) {
          // Prefill with the participant's current answers when the backend
          // provides them (GET /onboarding/profile-survey `answers`, or a
          // `profile` on the user object).
          const current = d.answers || d.profile || (user as any)?.profile;
          if (current && typeof current === "object") {
            setAnswers(current);
            setInitialAnswers(current);
          }
        }
      })
      .catch((e: any) => setLoadError(e?.message || "Couldn't load the survey."));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isEdit]);

  useEffect(() => {
    load();
  }, [load]);

  const currentSection = sections[sectionIndex];
  const visibleQuestions = useMemo(
    () =>
      questions.filter((q) => q.section === currentSection?.id && conditionMet(q.condition, answers)),
    [questions, currentSection, answers]
  );

  const clearFieldError = (id: string) =>
    setFieldErrors((fe) => {
      if (!fe[id]) return fe;
      const { [id]: _drop, ...rest } = fe;
      return rest;
    });

  const setAnswer = (id: string, val: any) => {
    clearFieldError(id);
    setAnswers((a) => ({ ...a, [id]: val }));
  };

  const toggleMulti = (q: Question, optId: string) => {
    clearFieldError(q.id);
    setAnswers((a) => {
      const cur: string[] = Array.isArray(a[q.id]) ? a[q.id] : [];
      if (cur.includes(optId)) return { ...a, [q.id]: cur.filter((v) => v !== optId) };
      const opt = (q.options || []).find((o) => o.id === optId);
      // An exclusive option ("None") clears everything else; picking
      // anything else clears the exclusive one.
      if (opt && isExclusiveOption(q, opt)) return { ...a, [q.id]: [optId] };
      const exclusiveIds = new Set((q.options || []).filter((o) => isExclusiveOption(q, o)).map((o) => o.id));
      return { ...a, [q.id]: [...cur.filter((v) => !exclusiveIds.has(v)), optId] };
    });
  };

  const validateSection = (): Record<string, string> => {
    const errs: Record<string, string> = {};
    for (const q of visibleQuestions) {
      const v = answers[q.id];
      if (q.required && isEmpty(v)) {
        errs[q.id] = "This one's required.";
        continue;
      }
      if (q.type === "number" && !isEmpty(v)) {
        const { min, max } = numberRange(q);
        const rangeMsg =
          min !== undefined && max !== undefined
            ? `Please enter a number between ${min} and ${max}.`
            : min !== undefined
              ? `Please enter a number of at least ${min}.`
              : `Please enter a number no higher than ${max}.`;
        if (typeof v !== "number" || !Number.isFinite(v)) errs[q.id] = "Please enter a whole number.";
        else if ((min !== undefined && v < min) || (max !== undefined && v > max)) errs[q.id] = rangeMsg;
      }
    }
    return errs;
  };

  const finish = async () => {
    const cleaned = pruneAnswers(questions, answers);
    if (isEdit) {
      // PATCH merges into the stored profile, so explicitly null out
      // previously-saved answers that are now cleared/not applicable
      // instead of leaving stale values behind. Only keys we actually
      // loaded are nulled — without a prefill, unanswered questions keep
      // their saved values.
      const payload: Record<string, any> = { ...cleaned };
      for (const k of Object.keys(initialAnswers || {})) if (!(k in cleaned)) payload[k] = null;
      await api.updateProfileSurvey(payload);
      await refresh();
      goBack(router, "/settings");
    } else {
      await api.submitProfileSurvey(cleaned);
      await refresh();
      // First-time setup offers the avatar builder once (optional — it can
      // be skipped) before entering the tabs. Re-editable later from
      // Progress or Settings.
      router.replace({ pathname: "/avatar", params: { mode: "onboarding" } });
    }
  };

  const goNext = async () => {
    setError("");
    const errs = validateSection();
    setFieldErrors(errs);
    const firstId = visibleQuestions.find((q) => errs[q.id])?.id;
    if (firstId) {
      const q = visibleQuestions.find((x) => x.id === firstId)!;
      setError(`Please check: ${q.label}`);
      return;
    }
    if (sectionIndex < sections.length - 1) {
      setSectionIndex((i) => i + 1);
    } else {
      setSubmitting(true);
      try {
        await finish();
      } catch (e: any) {
        setError(e.message || "Something went wrong — please try again.");
        setSubmitting(false);
      }
    }
  };

  const onBack = () => {
    setError("");
    setFieldErrors({});
    if (sectionIndex > 0) setSectionIndex((i) => i - 1);
    else goBack(router, isEdit ? "/settings" : "/welcome");
  };

  if (loadError) {
    return (
      <View style={[styles.center, { paddingHorizontal: spacing.xl }]}>
        <AppText variant="body" style={{ textAlign: "center", marginBottom: spacing.lg }}>
          We couldn&apos;t load the survey. {loadError}
        </AppText>
        <Button title="Try again" onPress={load} testID="onboarding-retry" />
      </View>
    );
  }

  if (!sections.length || !questions.length) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color={colors.brandPrimary} />
      </View>
    );
  }

  const isLast = sectionIndex === sections.length - 1;

  return (
    <KeyboardAvoidingView
      style={{ flex: 1 }}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <View style={[styles.c, { paddingTop: insets.top + spacing.md }]} testID="onboarding-screen">
        <View style={styles.header}>
          <Pressable onPress={onBack} testID="onboarding-back" hitSlop={10}>
            <Feather name="chevron-left" size={26} color={colors.onSurface} />
          </Pressable>
          <View style={{ flex: 1, marginHorizontal: spacing.lg }}>
            <ProgressBar value={sectionIndex + 1} max={sections.length} height={6} />
          </View>
          <AppText variant="caption">
            {sectionIndex + 1}/{sections.length}
          </AppText>
        </View>

        <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false} keyboardShouldPersistTaps="handled">
          <AppText variant="label" color={colors.brandPrimary} style={{ marginBottom: spacing.sm }}>
            {isEdit ? "EDIT MY PROFILE" : "NUTRITION & LIFESTYLE PROFILE"}
          </AppText>
          <AppText variant="display">{currentSection.title}</AppText>
          <AppText variant="caption" style={{ marginTop: spacing.sm, marginBottom: spacing.xl }}>
            {isEdit
              ? initialAnswers
                ? "Update anything that's changed — the app uses these answers for context, not a diet score."
                : "Update anything that's changed. We couldn't load your previous answers here, so optional questions you leave blank keep their saved values."
              : "This just helps the app get useful context about you early on — it isn't a diet score. There are no wrong answers, and you can update these later in Settings."}
          </AppText>

          <View style={{ gap: spacing.xl }}>
            {visibleQuestions.map((q, i) => {
              const group = groupOf(q);
              const prevGroup = i > 0 ? groupOf(visibleQuestions[i - 1]) : null;
              const showHeading = group && group.id !== prevGroup?.id;
              return (
                <View key={q.id}>
                  {showHeading && (
                    <AppText variant="subtitle" style={{ marginBottom: spacing.md }} testID={`group-heading-${group.id}`}>
                      {group.label}
                    </AppText>
                  )}
                  <FieldRenderer
                    question={q}
                    value={answers[q.id]}
                    error={fieldErrors[q.id]}
                    onChange={(v) => setAnswer(q.id, v)}
                    onToggleMulti={(optId) => toggleMulti(q, optId)}
                  />
                </View>
              );
            })}
          </View>

          {!!error && (
            <AppText variant="caption" color={colors.error} style={{ marginTop: spacing.lg }}>
              {error}
            </AppText>
          )}

          <View style={{ height: spacing["2xl"] }} />
          <Button
            title={isLast ? (isEdit ? "Save changes" : "Finish setup") : "Continue"}
            onPress={goNext}
            loading={submitting}
            testID="onboarding-continue"
          />
        </ScrollView>
      </View>
    </KeyboardAvoidingView>
  );
}

function FieldRenderer({
  question,
  value,
  error,
  onChange,
  onToggleMulti,
}: {
  question: Question;
  value: any;
  error?: string;
  onChange: (v: any) => void;
  onToggleMulti: (optId: string) => void;
}) {
  return (
    <View>
      <AppText variant="label" style={{ marginBottom: spacing.sm }}>
        {question.label}
        {question.required ? " *" : ""}
      </AppText>

      {question.type === "number" && (
        <NumberField question={question} value={value} error={error} onChange={onChange} />
      )}

      {question.type === "text" && (
        <TextInput
          testID={`field-${question.id}`}
          style={[styles.input, { minHeight: 48 }]}
          value={value || ""}
          onChangeText={onChange}
          maxLength={question.max_length}
          placeholder="Type your answer"
          placeholderTextColor={colors.muted}
          multiline
        />
      )}

      {question.type === "single_select" && (
        <View style={{ gap: spacing.sm }}>
          {(question.options || []).map((opt) => {
            const selected = value === opt.id;
            return (
              <Pressable
                key={opt.id}
                testID={`field-${question.id}-${opt.id}`}
                onPress={() => onChange(opt.id)}
                style={[styles.option, selected && styles.optionActive]}
              >
                <AppText
                  variant="body"
                  color={selected ? colors.onSurfaceInverse : colors.onSurface}
                  style={{ fontFamily: fonts.medium }}
                >
                  {opt.label}
                </AppText>
                {selected && <Feather name="check" size={18} color={colors.onSurfaceInverse} />}
              </Pressable>
            );
          })}
        </View>
      )}

      {question.type === "multi_select" && (
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm }}>
          {(question.options || []).map((opt) => {
            const selected = Array.isArray(value) && value.includes(opt.id);
            return (
              <Pressable
                key={opt.id}
                testID={`field-${question.id}-${opt.id}`}
                onPress={() => onToggleMulti(opt.id)}
                style={[styles.chip, selected && styles.chipActive]}
              >
                <AppText variant="caption" color={selected ? colors.onSurfaceInverse : colors.onSurfaceSecondary}>
                  {opt.label}
                </AppText>
              </Pressable>
            );
          })}
        </View>
      )}

      {!!error && question.type !== "number" && (
        <AppText variant="caption" color={colors.error} style={{ marginTop: spacing.sm }} testID={`field-${question.id}-error`}>
          {error}
        </AppText>
      )}
    </View>
  );
}

// Digits-only input. Empty stays unset (undefined) rather than coercing to
// 0, and the range is shown as the placeholder; out-of-range values are
// flagged by the section validation on Continue.
function NumberField({
  question,
  value,
  error,
  onChange,
}: {
  question: Question;
  value: any;
  error?: string;
  onChange: (v: any) => void;
}) {
  const { min, max } = numberRange(question);
  const placeholder = min !== undefined && max !== undefined ? `${min}–${max}` : "Enter a number";
  return (
    <>
      <TextInput
        testID={`field-${question.id}`}
        style={[styles.input, !!error && { borderColor: colors.error }]}
        keyboardType="number-pad"
        inputMode="numeric"
        value={value !== undefined && value !== null ? String(value) : ""}
        maxLength={max !== undefined ? String(max).length + 1 : 6}
        onChangeText={(t) => {
          const digits = t.replace(/[^0-9]/g, "");
          onChange(digits === "" ? undefined : parseInt(digits, 10));
        }}
        placeholder={placeholder}
        placeholderTextColor={colors.muted}
      />
      {!!error && (
        <AppText variant="caption" color={colors.error} style={{ marginTop: spacing.sm }} testID={`field-${question.id}-error`}>
          {error}
        </AppText>
      )}
    </>
  );
}

const styles = StyleSheet.create({
  c: { flex: 1, backgroundColor: colors.surface },
  center: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.lg, marginBottom: spacing.md },
  scroll: { paddingHorizontal: spacing.xl, paddingTop: spacing.lg, paddingBottom: spacing["3xl"] },
  option: {
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    paddingVertical: 14,
    paddingHorizontal: spacing.lg,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  optionActive: { backgroundColor: colors.surfaceInverse, borderColor: colors.surfaceInverse },
  chip: {
    paddingHorizontal: spacing.md,
    paddingVertical: 10,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surfaceSecondary,
  },
  chipActive: { backgroundColor: colors.surfaceInverse, borderColor: colors.surfaceInverse },
  input: {
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: spacing.lg,
    paddingVertical: 14,
    fontFamily: fonts.regular,
    fontSize: fontSize.base,
    color: colors.onSurface,
  },
});
