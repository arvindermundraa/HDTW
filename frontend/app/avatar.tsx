import React, { useEffect, useMemo, useState } from "react";
import { View, StyleSheet, ScrollView, Pressable } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Feather } from "@expo/vector-icons";
import { AppText, Button } from "@/src/components/ui";
import { Avatar, cardStyle } from "@/src/components/llhs";
import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import {
  AvatarConfig, AvatarMood, BACKGROUND, FACE, GLASSES, HAIR, HAIR_COLOR, OUTFIT, OUTFIT_COLOR, SKIN, normalizeAvatar,
} from "@/src/avatar";
import { colors, fonts, radius, spacing } from "@/src/theme";
import { goBack } from "@/src/navigation";

// Avatar builder: appearance is chosen here once and kept. There is no body
// size or shape control, on purpose. Reached once (optional) after first-time
// onboarding, and any time from Progress or Settings.

type Choice = { id: string; label: string };
type Swatch = Choice & { color: string };

const PREVIEW_MOODS: { id: AvatarMood["mood"]; label: string; mood: AvatarMood }[] = [
  { id: "calm", label: "Calm", mood: { date: "", mood: "calm", rings_closed: 0, glow: false, props: [] } },
  { id: "content", label: "Content", mood: { date: "", mood: "content", rings_closed: 1, glow: false, props: ["salad"] } },
  { id: "energised", label: "Energised", mood: { date: "", mood: "energised", rings_closed: 3, glow: true, props: ["salad", "sneakers", "rested"] } },
];

export default function AvatarBuilder() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { mode } = useLocalSearchParams<{ mode?: string }>();
  const onboarding = mode === "onboarding";
  const { user, refresh } = useAuth();
  const initial = useMemo(() => normalizeAvatar(user?.avatar), [user?.avatar]);
  const [draft, setDraft] = useState<AvatarConfig>(initial);
  const [touched, setTouched] = useState(false);
  // The saved avatar can arrive after first render (cold start on this route).
  useEffect(() => {
    if (!touched) setDraft(initial);
  }, [initial, touched]);
  const [preview, setPreview] = useState<AvatarMood["mood"]>("content");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const set = (key: keyof AvatarConfig, value: string) => {
    setTouched(true);
    setDraft((d) => ({ ...d, [key]: value }));
  };
  const changed = !user?.avatar || (Object.keys(draft) as (keyof AvatarConfig)[]).some((k) => draft[k] !== initial[k]);

  const leave = () => (onboarding ? router.replace("/(tabs)") : goBack(router, "/(tabs)/profile"));

  const save = async () => {
    setSaving(true);
    setError("");
    try {
      await api.setAvatar(draft);
      await refresh();
      leave();
    } catch (e: any) {
      setError(e?.message || "Couldn't save your avatar. Try again.");
    } finally {
      setSaving(false);
    }
  };

  const previewMood = PREVIEW_MOODS.find((m) => m.id === preview)!.mood;

  const tiles = (key: keyof AvatarConfig, options: Choice[]) => (
    <View style={styles.tiles}>
      {options.map((o) => {
        const on = draft[key] === o.id;
        return (
          <Pressable
            key={o.id}
            onPress={() => set(key, o.id)}
            style={[styles.tile, on && styles.tileOn]}
            accessibilityRole="radio"
            accessibilityState={{ selected: on }}
            accessibilityLabel={o.label}
            testID={`avatar-${key}-${o.id}`}
          >
            <Avatar size={52} config={{ ...draft, [key]: o.id }} mood={null} showProps={false} />
            <AppText variant="caption" color={on ? colors.onSurface : colors.muted} style={{ fontSize: 12, fontFamily: on ? fonts.semibold : fonts.regular }}>
              {o.label}
            </AppText>
          </Pressable>
        );
      })}
    </View>
  );

  const swatches = (key: keyof AvatarConfig, options: Swatch[]) => (
    <View style={styles.swatches}>
      {options.map((o) => {
        const on = draft[key] === o.id;
        return (
          <Pressable
            key={o.id}
            onPress={() => set(key, o.id)}
            style={[styles.swatchRing, on && { borderColor: colors.brandPrimary }]}
            accessibilityRole="radio"
            accessibilityState={{ selected: on }}
            accessibilityLabel={o.label}
            testID={`avatar-${key}-${o.id}`}
            hitSlop={4}
          >
            <View style={[styles.swatch, { backgroundColor: o.color }]} />
          </Pressable>
        );
      })}
    </View>
  );

  const section = (title: string, body: React.ReactNode) => (
    <View style={[cardStyle, { gap: spacing.md, padding: spacing.lg }]}>
      <AppText variant="subtitle" style={{ fontSize: 15 }}>
        {title}
      </AppText>
      {body}
    </View>
  );

  return (
    <View style={[styles.c, { paddingTop: insets.top + spacing.sm }]} testID="avatar-builder">
      <View style={styles.header}>
        <AppText variant="title" style={{ fontSize: 19 }}>
          {onboarding ? "Make your avatar" : "Your avatar"}
        </AppText>
        {onboarding ? (
          <Pressable onPress={leave} hitSlop={8} testID="avatar-skip">
            <AppText variant="label" color={colors.muted}>
              Skip for now
            </AppText>
          </Pressable>
        ) : (
          <Pressable onPress={leave} hitSlop={8} accessibilityLabel="Close" testID="avatar-close">
            <Feather name="x" size={22} color={colors.onSurface} />
          </Pressable>
        )}
      </View>

      <ScrollView contentContainerStyle={{ padding: spacing.xl, paddingTop: spacing.sm, gap: spacing.lg, paddingBottom: spacing["3xl"] }}>
        <View style={[cardStyle, { alignItems: "center", gap: spacing.md }]}>
          <View style={{ padding: 10 }}>
            <Avatar size={136} config={draft} mood={previewMood} />
          </View>
          <View style={styles.segment} accessibilityRole="radiogroup">
            {PREVIEW_MOODS.map((m) => (
              <Pressable
                key={m.id}
                onPress={() => setPreview(m.id)}
                style={[styles.segBtn, preview === m.id && styles.segOn]}
                accessibilityRole="radio"
                accessibilityState={{ selected: preview === m.id }}
                testID={`avatar-preview-${m.id}`}
              >
                <AppText variant="label" color={preview === m.id ? colors.onSurface : colors.muted} style={{ fontSize: 13 }}>
                  {m.label}
                </AppText>
              </Pressable>
            ))}
          </View>
          <AppText variant="caption" style={{ textAlign: "center" }}>
            Your avatar looks the way you choose. Each day its expression brightens as your rings close, with small touches for what you log. It starts calm every morning, and its body never changes.
          </AppText>
        </View>

        {section("Skin tone", swatches("skin", SKIN))}
        {section("Hair", <>{tiles("hair", HAIR)}{draft.hair !== "none" && swatches("hair_color", HAIR_COLOR)}</>)}
        {section("Face", tiles("face", FACE))}
        {section("Glasses", tiles("glasses", GLASSES))}
        {section("Outfit", <>{tiles("outfit", OUTFIT)}{swatches("outfit_color", OUTFIT_COLOR)}</>)}
        {section("Background", swatches("background", BACKGROUND))}

        {!!error && (
          <AppText variant="caption" color={colors.error} style={{ textAlign: "center" }}>
            {error}
          </AppText>
        )}
        <Button title={onboarding ? "Save and continue" : "Save"} onPress={save} loading={saving} disabled={!changed && !onboarding} testID="avatar-save" />
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  c: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.xl, paddingVertical: spacing.md },
  tiles: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  tile: {
    width: 72, paddingVertical: 8, alignItems: "center", gap: 4, borderRadius: radius.md,
    borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary,
  },
  tileOn: { borderColor: colors.brandPrimary, borderWidth: 2, paddingVertical: 7, backgroundColor: colors.brandTertiary },
  swatches: { flexDirection: "row", flexWrap: "wrap", gap: 10 },
  swatchRing: { width: 40, height: 40, borderRadius: 20, borderWidth: 2, borderColor: "transparent", alignItems: "center", justifyContent: "center" },
  swatch: { width: 30, height: 30, borderRadius: 15, borderWidth: 1, borderColor: "rgba(16,26,22,0.12)" },
  segment: { flexDirection: "row", gap: 4, backgroundColor: colors.surfaceTertiary, borderRadius: radius.md, padding: 4, alignSelf: "stretch" },
  segBtn: { flex: 1, height: 34, borderRadius: 8, alignItems: "center", justifyContent: "center" },
  segOn: { backgroundColor: colors.surfaceSecondary, boxShadow: "0px 1px 3px rgba(14,42,36,0.10)" },
});
