import React from "react";
import { View, StyleSheet } from "react-native";
import { Feather } from "@expo/vector-icons";
import { AppText } from "@/src/components/ui";
import { useAuth } from "@/src/auth";
import { FOCUS_AREA_LABEL } from "@/src/food";
import { colors, spacing, radius, fonts } from "@/src/theme";

// Thin chip pinned to the top of every Week 2 step screen. Mirrors the
// focus panel inside the Week card so the student's chosen focus and
// goal are visible context on every scenario / plan / review screen.
// Hidden when the student hasn't picked a focus area yet.
export function WeekFocusBanner({ week }: { week: number }) {
  const { user } = useAuth();
  const focusLabel = user?.focus_area ? FOCUS_AREA_LABEL[user.focus_area] ?? user.focus_area : null;
  if (!focusLabel) return null;
  const goal = user?.focus_goal?.goal;
  return (
    <View style={styles.banner} testID={`week-focus-banner-${week}`} accessibilityRole="summary">
      <Feather name="target" size={14} color={colors.brandPrimary} />
      <View style={{ flex: 1 }}>
        <AppText variant="caption" color={colors.brandPrimary} style={{ letterSpacing: 0.4 }}>
          YOUR FOCUS · {focusLabel.toUpperCase()}
        </AppText>
        {goal ? (
          <AppText variant="body" style={{ fontSize: 13 }} numberOfLines={2}>
            <AppText variant="body" style={{ fontSize: 13, fontFamily: fonts.semibold }}>Goal: </AppText>
            {goal}
          </AppText>
        ) : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  banner: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    borderRadius: radius.md,
    backgroundColor: colors.surfaceSecondary,
    borderWidth: 1,
    borderColor: colors.border,
    marginBottom: spacing.sm,
  },
});
