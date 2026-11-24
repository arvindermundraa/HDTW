import React from "react";
import { View, StyleSheet, Pressable } from "react-native";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Feather } from "@expo/vector-icons";
import { AppText, Button } from "@/src/components/ui";
import { colors, spacing, fonts, IMAGES } from "@/src/theme";

export default function Welcome() {
  const router = useRouter();
  const insets = useSafeAreaInsets();

  return (
    <View style={styles.c} testID="welcome-screen">
      <Image source={{ uri: IMAGES.hero }} style={StyleSheet.absoluteFill} contentFit="cover" />
      <LinearGradient
        colors={["rgba(44,47,45,0.15)", "rgba(44,47,45,0.55)", "rgba(44,47,45,0.92)"]}
        style={StyleSheet.absoluteFill}
      />
      <View style={[styles.content, { paddingTop: insets.top + spacing.xl, paddingBottom: insets.bottom + spacing.xl }]}>
        <View style={styles.brandRow}>
          <Feather name="heart" size={20} color={colors.onSurfaceInverse} />
          <AppText variant="label" color={colors.onSurfaceInverse} style={{ letterSpacing: 1.5 }}>
            LLHS
          </AppText>
        </View>

        <View style={{ flex: 1 }} />

        <AppText variant="displayLg" color={colors.onSurfaceInverse}>
          Live Long,{"\n"}Heart Strong
        </AppText>
        <AppText variant="body" color="rgba(253,251,247,0.85)" style={{ marginTop: spacing.md, fontSize: 16, lineHeight: 24 }}>
          Small habits, built one choice at a time. A gentle, process-based guide to heart-healthy living — never about weight, calories, or appearance.
        </AppText>

        <View style={{ height: spacing.xl }} />
        <Button title="Create account" onPress={() => router.push("/auth?mode=signup")} testID="welcome-signup" />
        <Pressable onPress={() => router.push("/auth")} style={styles.note} testID="welcome-signin">
          <AppText variant="body" color={colors.onSurfaceInverse}>
            I already have an account
          </AppText>
        </Pressable>
        <AppText variant="caption" color="rgba(253,251,247,0.7)" style={{ textAlign: "center" }}>
          For TAMU students in the LLHS study.
        </AppText>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  c: { flex: 1, backgroundColor: colors.surfaceInverse },
  content: { flex: 1, paddingHorizontal: spacing.xl },
  brandRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  note: { alignItems: "center", paddingVertical: spacing.lg },
});
