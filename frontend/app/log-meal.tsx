import React, { useEffect, useState } from "react";
import { View, StyleSheet, Pressable, ScrollView, ActivityIndicator, Linking } from "react-native";
import { Image } from "expo-image";
import * as ImagePicker from "expo-image-picker";
import * as Haptics from "expo-haptics";
import { useRouter, useLocalSearchParams } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import { TextInput } from "react-native";
import { Feather } from "@expo/vector-icons";
import { AppText, Button, Card, Pill } from "@/src/components/ui";
import { RewardBurst } from "@/src/components/visuals";
import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { colors, spacing, fonts, fontSize, radius } from "@/src/theme";
import { FOCUS_AREA_LABEL } from "@/src/food";
import { goBack } from "@/src/navigation";

type Mode = "meal" | "move" | "rest";
type CaptureSource = "text" | "photo";

// Voice Logging (record-a-voice-note-to-log-a-meal) was removed as of
// 2026-09 along with Emergent — TAMU AI, now the app's sole AI provider,
// documents no audio/speech input to transcribe against. See README/PRD.
export default function LogMeal() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user } = useAuth();
  // Today's Move / Sleep cards open this screen straight on their tab.
  const { mode: initialMode } = useLocalSearchParams<{ mode?: string }>();
  const [mode, setMode] = useState<Mode>(initialMode === "move" || initialMode === "rest" ? initialMode : "meal");
  const [burst, setBurst] = useState(0);
  const [saving, setSaving] = useState(false);

  // meal state — 9 lightweight qualitative categories (not booleans), per
  // the review notes. The category list itself comes from the server
  // (GET /meals/categories) so nutrition-team copy changes don't need a
  // client release.
  const [categoryOptions, setCategoryOptions] = useState<{ id: string; label: string }[]>([]);
  const [name, setName] = useState("");
  const [mealType, setMealType] = useState<"breakfast" | "lunch" | "dinner" | "snack">("lunch");
  const [categories, setCategories] = useState<string[]>([]);
  const [portion, setPortion] = useState<"small" | "normal" | "large">("normal");
  const [skipped, setSkipped] = useState(false);
  // Optional self-report tied to the student's current focus goal (Week 1
  // spec §8 "Meal Logging"). null = unanswered; true/false = answered.
  // Only surfaced when the student has an active focus_goal.goal.
  const [goalHit, setGoalHit] = useState<boolean | null>(null);
  const [photoUri, setPhotoUri] = useState<string | null>(null);
  const [captureSource, setCaptureSource] = useState<CaptureSource>("text");
  const [analyzing, setAnalyzing] = useState(false);
  const [analysis, setAnalysis] = useState<any>(null);
  const [permError, setPermError] = useState(false);
  const [allergyFlag, setAllergyFlag] = useState(false);
  const [tamusKeyRequired, setTamusKeyRequired] = useState(false);

  useEffect(() => {
    api.getLogCategories().then((d: any) => setCategoryOptions(d.categories || []));
  }, []);

  const toggleCategory = (id: string) => {
    setCategories((c) => (c.includes(id) ? c.filter((x) => x !== id) : [...c, id]));
  };

  // Answers the open technical question from the review notes: can a
  // typed description be auto-mapped to categories instead of manual
  // ticking? Debounced-free simple version — triggered on blur/submit.
  const categorizeFromText = async () => {
    if (!name.trim()) return;
    try {
      const out = await api.categorizeMealText(name.trim());
      if (out.categories?.length) setCategories(out.categories);
      if (out.allergy_flag) setAllergyFlag(true);
      if (out.tamus_key_required) setTamusKeyRequired(true);
    } catch {
      // Silent fallback — manual category chips are always still available.
    }
  };

  // move / rest
  const [minutes, setMinutes] = useState(30);
  const [hours, setHours] = useState(7.5);
  // Optional bed and wake times (30-minute steps, minutes since midnight),
  // so the behavioral twin can notice irregular sleep timing from manual
  // logs too, not only from a tracker.
  const [addTimes, setAddTimes] = useState(false);
  const [bedMin, setBedMin] = useState(23 * 60);
  const [wakeMin, setWakeMin] = useState(7 * 60);

  const success = () => {
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    setBurst((b) => b + 1);
    setTimeout(() => goBack(router, "/"), 950);
  };

  const pickPhoto = async (fromCamera: boolean) => {
    setPermError(false);
    const perm = fromCamera
      ? await ImagePicker.requestCameraPermissionsAsync()
      : await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!perm.granted) {
      setPermError(true);
      return;
    }
    const res = fromCamera
      ? await ImagePicker.launchCameraAsync({ base64: true, quality: 0.4, mediaTypes: ["images"] })
      : await ImagePicker.launchImageLibraryAsync({ base64: true, quality: 0.4, mediaTypes: ["images"] });
    if (res.canceled || !res.assets?.[0]?.base64) return;
    const asset = res.assets[0];
    setPhotoUri(asset.uri);
    setCaptureSource("photo");
    setAnalyzing(true);
    try {
      const out = await api.analyzePhoto(asset.base64!);
      setAnalysis(out);
      setName(out.suggested_name || "Meal");
      setCategories(out.categories || []);
      setAllergyFlag(!!out.allergy_flag);
      if (out.tamus_key_required) setTamusKeyRequired(true);
    } catch {
      setAnalysis({ error: true });
    } finally {
      setAnalyzing(false);
    }
  };

  const saveMeal = async () => {
    if (!name.trim() && !skipped) {
      setName("Meal");
    }
    setSaving(true);
    try {
      await api.createMeal({
        name: skipped ? "Skipped meal" : name.trim() || "Meal",
        source: skipped ? "text" : captureSource,
        meal_type: mealType,
        categories: skipped ? [] : categories,
        portion,
        skipped,
        photo_confidence: analysis?.confidence ?? null,
        confirmed: true,
        goal_hit: skipped ? null : goalHit,
      });
      success();
    } catch {
      setSaving(false);
    }
  };

  const saveMove = async () => {
    setSaving(true);
    try {
      await api.createActivity({ minutes, kind: "moderate" });
      success();
    } catch {
      setSaving(false);
    }
  };

  const saveRest = async () => {
    setSaving(true);
    try {
      await api.createSleep({ hours, source: "manual", ...(addTimes ? { bedtime: hhmm(bedMin), wake: hhmm(wakeMin) } : {}) });
      success();
    } catch {
      setSaving(false);
    }
  };

  return (
    <View style={styles.c} testID="log-screen">
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <AppText variant="title">Log</AppText>
        <Pressable onPress={() => goBack(router, "/")} hitSlop={10} testID="log-close">
          <Feather name="x" size={26} color={colors.onSurface} />
        </Pressable>
      </View>

      <View style={styles.modeRow}>
        <Pill label="Food" active={mode === "meal"} onPress={() => setMode("meal")} testID="mode-meal" />
        <Pill label="Move" active={mode === "move"} onPress={() => setMode("move")} testID="mode-move" />
        <Pill label="Rest" active={mode === "rest"} onPress={() => setMode("rest")} testID="mode-rest" />
      </View>

      {mode === "meal" && (
        <KeyboardAwareScrollView
          contentContainerStyle={styles.scroll}
          bottomOffset={20}
          showsVerticalScrollIndicator={false}
        >
          {/* Photo capture */}
          {photoUri ? (
            <Image source={{ uri: photoUri }} style={styles.preview} contentFit="cover" />
          ) : (
            <View style={styles.photoButtons}>
              <Pressable style={styles.photoBtn} onPress={() => pickPhoto(true)} testID="log-camera">
                <Feather name="camera" size={22} color={colors.onSurface} />
                <AppText variant="label">Take photo</AppText>
              </Pressable>
              <Pressable style={styles.photoBtn} onPress={() => pickPhoto(false)} testID="log-gallery">
                <Feather name="image" size={22} color={colors.onSurface} />
                <AppText variant="label">Choose photo</AppText>
              </Pressable>
            </View>
          )}

          {permError && (
            <Card style={{ marginTop: spacing.md, backgroundColor: colors.surfaceTertiary }}>
              <AppText variant="body">Camera access is needed to log this way.</AppText>
              <Button
                title="Open Settings"
                variant="secondary"
                onPress={() => Linking.openSettings()}
                style={{ marginTop: spacing.md }}
                testID="open-settings"
              />
            </Card>
          )}

          {tamusKeyRequired && (
            <Card style={{ marginTop: spacing.md, backgroundColor: colors.surfaceTertiary }} testID="tamus-key-required-notice">
              <AppText variant="body">Add your TAMU AI key in Settings to enable photo recognition and auto-categorizing — you can still fill everything in manually below.</AppText>
              <Button
                title="Go to Settings"
                variant="secondary"
                onPress={() => router.push("/settings")}
                style={{ marginTop: spacing.md }}
                testID="tamus-key-required-settings"
              />
            </Card>
          )}

          {analyzing && (
            <View style={styles.analyzing}>
              <ActivityIndicator color={colors.brandPrimary} />
              <AppText variant="caption" style={{ marginTop: spacing.sm }}>
                Reading your photo…
              </AppText>
            </View>
          )}

          {/* Confidence-gated review */}
          {analysis && !analysis.error && (
            <Card style={{ marginTop: spacing.lg }} >
              <View style={styles.reviewHead}>
                <AppText variant="label">ASSISTED ENTRY — REVIEW</AppText>
                <View
                  style={[
                    styles.confBadge,
                    { backgroundColor: analysis.needs_confirmation ? colors.warning : colors.brand },
                  ]}
                  testID="confidence-badge"
                >
                  <AppText variant="caption" color="#fff">
                    {Math.round((analysis.confidence || 0) * 100)}% sure
                  </AppText>
                </View>
              </View>
              <AppText variant="caption" style={{ marginTop: spacing.xs }}>
                {analysis.note}
              </AppText>
              {analysis.needs_confirmation && (
                <AppText variant="caption" color={colors.warning} style={{ marginTop: spacing.sm }} testID="needs-confirm">
                  Low confidence — please double-check the details below before saving.
                </AppText>
              )}
            </Card>
          )}

          {/* Manual details */}
          <AppText variant="label" style={{ marginTop: spacing.xl, marginBottom: spacing.sm }}>
            What did you eat?
          </AppText>
          <TextInput
            style={styles.input}
            value={name}
            onChangeText={setName}
            onBlur={categorizeFromText}
            placeholder="e.g. grilled chicken, brown rice, broccoli"
            placeholderTextColor={colors.muted}
            testID="meal-name"
          />
          <AppText variant="caption" style={{ marginTop: spacing.xs }}>
            Describe what you ate and we'll suggest categories below — or just tap them yourself.
          </AppText>
          {allergyFlag && (
            <Card style={{ marginTop: spacing.md, backgroundColor: colors.surfaceTertiary }} testID="allergy-flag-notice">
              <AppText variant="caption">
                This looks like it might touch one of your listed allergies or restrictions — worth a quick
                double-check before saving.
              </AppText>
            </Card>
          )}

          <AppText variant="label" style={{ marginTop: spacing.lg, marginBottom: spacing.sm }}>
            Meal
          </AppText>
          <View style={styles.chipRow}>
            {(["breakfast", "lunch", "dinner", "snack"] as const).map((t) => (
              <Pill key={t} label={t[0].toUpperCase() + t.slice(1)} active={mealType === t} onPress={() => setMealType(t)} testID={`meal-type-${t}`} />
            ))}
          </View>

          <AppText variant="label" style={{ marginTop: spacing.lg, marginBottom: spacing.sm }}>
            What was on the plate? (tap all that apply)
          </AppText>
          <View style={styles.categoryGrid}>
            {categoryOptions.map((c) => (
              <Pressable
                key={c.id}
                testID={`category-${c.id}`}
                onPress={() => toggleCategory(c.id)}
                style={[styles.categoryChip, categories.includes(c.id) && styles.categoryChipActive]}
              >
                <AppText
                  variant="body"
                  color={categories.includes(c.id) ? colors.onSurfaceInverse : colors.onSurface}
                >
                  {c.label}
                </AppText>
              </Pressable>
            ))}
          </View>

          <AppText variant="label" style={{ marginTop: spacing.lg, marginBottom: spacing.sm }}>
            Portion (no calorie counting here)
          </AppText>
          <View style={styles.chipRow}>
            {(["small", "normal", "large"] as const).map((p) => (
              <Pill key={p} label={p[0].toUpperCase() + p.slice(1)} active={portion === p} onPress={() => setPortion(p)} testID={`portion-${p}`} />
            ))}
          </View>

          {!skipped && user?.focus_area && user?.focus_goal?.goal ? (
            <View style={{ marginTop: spacing.lg }} testID="goal-hit-section">
              <AppText variant="label" style={{ marginBottom: spacing.xs }}>
                Did this meal include your goal?
              </AppText>
              <AppText variant="caption" color={colors.onSurfaceSecondary} style={{ marginBottom: spacing.sm }}>
                Your goal: {user.focus_goal.goal}
              </AppText>
              <View style={styles.chipRow}>
                <Pill label="Yes" active={goalHit === true} onPress={() => setGoalHit(goalHit === true ? null : true)} testID="goal-hit-yes" />
                <Pill label="No" active={goalHit === false} onPress={() => setGoalHit(goalHit === false ? null : false)} testID="goal-hit-no" />
                <Pill label="Skip" active={goalHit === null} onPress={() => setGoalHit(null)} testID="goal-hit-skip" />
              </View>
              <AppText variant="caption" color={colors.onSurfaceSecondary} style={{ marginTop: spacing.xs }}>
                Optional — this doesn&apos;t change your Eat feedback. It&apos;s a note to yourself.
              </AppText>
            </View>
          ) : null}

          <View style={{ height: spacing.xl }} />
          <Button title={saving ? "Saving…" : "Save meal"} onPress={saveMeal} loading={saving} testID="save-meal" />
          <View style={{ height: spacing["2xl"] }} />
        </KeyboardAwareScrollView>
      )}

      {mode === "move" && (
        <ScrollView contentContainerStyle={styles.scroll}>
          <AppText variant="body" style={{ marginBottom: spacing.lg }}>
            How many minutes of moderate activity today? Aim for 150 min/week — even walking counts.
          </AppText>
          <Stepper value={minutes} onChange={(v) => setMinutes(Math.max(0, v))} step={5} suffix="min" testID="move" />
          <View style={{ height: spacing.xl }} />
          <Button title={saving ? "Saving…" : "Save activity"} onPress={saveMove} loading={saving} testID="save-move" />
        </ScrollView>
      )}

      {mode === "rest" && (
        <ScrollView contentContainerStyle={styles.scroll}>
          <View style={styles.lowConfBanner} testID="rest-low-confidence">
            <Feather name="alert-circle" size={16} color={colors.warning} />
            <AppText variant="caption" color={colors.onWarning} style={{ flex: 1 }}>
              Manual sleep is a low-confidence estimate. Treat it as gentle guidance, not a precise reading.
            </AppText>
          </View>
          <AppText variant="body" style={{ marginTop: spacing.lg, marginBottom: spacing.lg }}>
            About how many hours did you sleep last night?
          </AppText>
          <Stepper value={hours} onChange={(v) => setHours(Math.max(0, Math.round(v * 2) / 2))} step={0.5} suffix="hrs" testID="rest" />
          <Pressable onPress={() => setAddTimes(!addTimes)} style={styles.addTimes} testID="rest-add-times">
            <Feather name={addTimes ? "minus-circle" : "plus-circle"} size={16} color={colors.brandPrimary} />
            <AppText variant="label" color={colors.brandPrimary} style={{ fontSize: 13 }}>
              {addTimes ? "Leave out the times" : "Add when you fell asleep and woke up (optional)"}
            </AppText>
          </Pressable>
          {addTimes && (
            <View style={{ gap: spacing.sm }}>
              <TimeRow label="Fell asleep" minutes={bedMin} onChange={setBedMin} testID="rest-bed" />
              <TimeRow label="Woke up" minutes={wakeMin} onChange={setWakeMin} testID="rest-wake" />
              <AppText variant="caption">Roughly is fine. It helps Future Me notice if your sleep timing moves around.</AppText>
            </View>
          )}
          <View style={{ height: spacing.xl }} />
          <Button title={saving ? "Saving…" : "Save sleep"} onPress={saveRest} loading={saving} testID="save-rest" />
        </ScrollView>
      )}

      <RewardBurst trigger={burst} />
    </View>
  );
}

const hhmm = (m: number) => `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
const clockWords = (m: number) => {
  const h = Math.floor(m / 60);
  const mm = m % 60;
  const h12 = h % 12 || 12;
  return `${h12}${mm ? `:${String(mm).padStart(2, "0")}` : ""} ${h < 12 ? "am" : "pm"}`;
};

function TimeRow({ label, minutes, onChange, testID }: { label: string; minutes: number; onChange: (m: number) => void; testID: string }) {
  const shift = (d: number) => onChange((minutes + d + 1440) % 1440);
  return (
    <View style={styles.timeRow}>
      <AppText variant="label" style={{ flex: 1 }}>
        {label}
      </AppText>
      <Pressable onPress={() => shift(-30)} style={styles.timeBtn} accessibilityLabel={`${label} earlier`} testID={`${testID}-minus`}>
        <Feather name="minus" size={18} color={colors.onSurface} />
      </Pressable>
      <AppText variant="subtitle" style={{ minWidth: 84, textAlign: "center" }} testID={`${testID}-value`}>
        {clockWords(minutes)}
      </AppText>
      <Pressable onPress={() => shift(30)} style={styles.timeBtn} accessibilityLabel={`${label} later`} testID={`${testID}-plus`}>
        <Feather name="plus" size={18} color={colors.onSurface} />
      </Pressable>
    </View>
  );
}

function Stepper({ value, onChange, step, suffix, testID }: any) {
  return (
    <View style={styles.stepper}>
      <Pressable onPress={() => onChange(value - step)} style={styles.stepBtn} testID={`${testID}-minus`}>
        <Feather name="minus" size={22} color={colors.onSurface} />
      </Pressable>
      <View style={{ alignItems: "center" }}>
        <AppText variant="display" style={{ fontSize: 40 }} testID={`${testID}-value`}>
          {value}
        </AppText>
        <AppText variant="caption">{suffix}</AppText>
      </View>
      <Pressable onPress={() => onChange(value + step)} style={styles.stepBtn} testID={`${testID}-plus`}>
        <Feather name="plus" size={22} color={colors.onSurface} />
      </Pressable>
    </View>
  );
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
  modeRow: { flexDirection: "row", gap: spacing.sm, paddingHorizontal: spacing.xl, marginBottom: spacing.md },
  scroll: { paddingHorizontal: spacing.xl, paddingBottom: spacing["3xl"] },
  photoButtons: { flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" },
  photoBtn: {
    flex: 1,
    minWidth: 96,
    height: 100,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    borderStyle: "dashed",
    backgroundColor: colors.surfaceSecondary,
    alignItems: "center",
    justifyContent: "center",
    gap: spacing.sm,
  },
  preview: { width: "100%", height: 200, borderRadius: radius.md },
  analyzing: { alignItems: "center", paddingVertical: spacing.xl },
  reviewHead: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  confBadge: { paddingHorizontal: spacing.md, paddingVertical: 4, borderRadius: radius.pill },
  input: {
    backgroundColor: colors.surfaceSecondary,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    paddingHorizontal: spacing.lg,
    paddingVertical: 14,
    fontFamily: fonts.medium,
    fontSize: fontSize.lg,
    color: colors.onSurface,
  },
  chipRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  categoryGrid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  categoryChip: {
    maxWidth: "100%",
    paddingHorizontal: spacing.md,
    paddingVertical: 10,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surfaceSecondary,
  },
  categoryChipActive: { backgroundColor: colors.surfaceInverse, borderColor: colors.surfaceInverse },
  lowConfBanner: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    backgroundColor: "rgba(212,163,115,0.15)",
    borderRadius: radius.md,
    padding: spacing.md,
    marginTop: spacing.sm,
  },
  addTimes: { flexDirection: "row", alignItems: "center", gap: 6, paddingTop: spacing.lg, paddingBottom: spacing.sm },
  timeRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
  },
  timeBtn: {
    width: 40,
    height: 40,
    borderRadius: radius.pill,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    alignItems: "center",
    justifyContent: "center",
  },
  stepper: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.xl,
  },
  stepBtn: {
    width: 52,
    height: 52,
    borderRadius: radius.pill,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    alignItems: "center",
    justifyContent: "center",
  },
});
