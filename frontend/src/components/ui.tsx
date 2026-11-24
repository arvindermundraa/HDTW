import React from "react";
import {
  Text,
  TextProps,
  Pressable,
  View,
  StyleSheet,
  ActivityIndicator,
  ViewStyle,
  StyleProp,
  TextStyle,
} from "react-native";
import * as Haptics from "expo-haptics";
import { colors, fonts, fontSize, radius, spacing, shadow } from "@/src/theme";

export function AppText({
  variant = "body",
  color,
  style,
  ...props
}: TextProps & { variant?: "display" | "displayLg" | "title" | "subtitle" | "body" | "label" | "caption"; color?: string }) {
  return <Text {...props} style={[styles[variant], color ? { color } : null, style]} />;
}

export function Button({
  title,
  onPress,
  variant = "primary",
  loading,
  disabled,
  style,
  testID,
  icon,
}: {
  title: string;
  onPress: () => void;
  variant?: "primary" | "secondary" | "ghost";
  loading?: boolean;
  disabled?: boolean;
  style?: StyleProp<ViewStyle>;
  testID?: string;
  icon?: React.ReactNode;
}) {
  const bg =
    variant === "primary" ? colors.brandPrimary : variant === "secondary" ? colors.surfaceTertiary : "transparent";
  const fg = variant === "primary" ? colors.onBrandPrimary : colors.onSurface;
  return (
    <Pressable
      testID={testID}
      disabled={disabled || loading}
      onPress={() => {
        Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
        onPress();
      }}
      style={({ pressed }) => [
        styles.btn,
        { backgroundColor: bg, opacity: disabled ? 0.5 : pressed ? 0.85 : 1 },
        variant === "ghost" && { paddingVertical: spacing.sm },
        style,
      ]}
    >
      {loading ? (
        <ActivityIndicator color={fg} />
      ) : (
        <View style={styles.btnRow}>
          {icon}
          <Text style={[styles.btnText, { color: fg }]}>{title}</Text>
        </View>
      )}
    </Pressable>
  );
}

export function Card({
  children,
  style,
  testID,
}: {
  children: React.ReactNode;
  style?: StyleProp<ViewStyle>;
  testID?: string;
}) {
  return (
    <View testID={testID} style={[styles.card, style]}>
      {children}
    </View>
  );
}

export function Disclaimer({ text, style }: { text: string; style?: StyleProp<TextStyle> }) {
  return (
    <Text testID="illustrative-disclaimer" style={[styles.disclaimer, style]}>
      {text}
    </Text>
  );
}

export function ProgressBar({
  value,
  max = 100,
  color = colors.brandPrimary,
  track = colors.surfaceTertiary,
  height = 10,
}: {
  value: number;
  max?: number;
  color?: string;
  track?: string;
  height?: number;
}) {
  const pct = Math.max(0, Math.min(1, value / max));
  return (
    <View style={[styles.track, { backgroundColor: track, height, borderRadius: height }]}>
      <View style={{ width: `${pct * 100}%`, backgroundColor: color, height, borderRadius: height }} />
    </View>
  );
}

export function Pill({ label, active, onPress, testID }: { label: string; active?: boolean; onPress?: () => void; testID?: string }) {
  return (
    <Pressable
      testID={testID}
      onPress={onPress}
      style={[
        styles.pill,
        { backgroundColor: active ? colors.surfaceInverse : colors.surfaceSecondary, borderColor: active ? colors.surfaceInverse : colors.border },
      ]}
    >
      <Text style={[styles.pillText, { color: active ? colors.onSurfaceInverse : colors.onSurfaceSecondary }]}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  display: { fontFamily: fonts.displaySemi, fontSize: fontSize["3xl"], color: colors.onSurface, lineHeight: 30, letterSpacing: -0.5 },
  displayLg: { fontFamily: fonts.displaySemi, fontSize: fontSize["4xl"], color: colors.onSurface, lineHeight: 36, letterSpacing: -0.7 },
  title: { fontFamily: fonts.display, fontSize: fontSize["2xl"], color: colors.onSurface, lineHeight: 26, letterSpacing: -0.3 },
  subtitle: { fontFamily: fonts.semibold, fontSize: fontSize.lg, color: colors.onSurface, letterSpacing: -0.1 },
  body: { fontFamily: fonts.regular, fontSize: fontSize.base, color: colors.onSurfaceSecondary, lineHeight: 22 },
  label: { fontFamily: fonts.semibold, fontSize: fontSize.sm, color: colors.onSurface, letterSpacing: 0.1 },
  caption: { fontFamily: fonts.regular, fontSize: fontSize.sm, color: colors.muted, lineHeight: 18 },
  btn: {
    borderRadius: radius.md,
    paddingVertical: 15,
    paddingHorizontal: spacing.xl,
    alignItems: "center",
    justifyContent: "center",
    minHeight: 50,
  },
  btnRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  btnText: { fontFamily: fonts.semibold, fontSize: fontSize.base, letterSpacing: 0.1 },
  card: {
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.lg,
    padding: spacing.lg,
    borderWidth: 1,
    borderColor: colors.border,
    ...shadow.card,
  },
  disclaimer: { fontFamily: fonts.regular, fontSize: 11, color: colors.muted, lineHeight: 15, fontStyle: "italic" },
  track: { width: "100%", overflow: "hidden" },
  pill: {
    paddingHorizontal: spacing.lg,
    height: 36,
    borderRadius: radius.pill,
    borderWidth: 1,
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
  },
  pillText: { fontFamily: fonts.medium, fontSize: fontSize.sm },
});
