import React from "react";
import { View, Pressable, StyleSheet, StyleProp, ViewStyle } from "react-native";
import { Feather } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { AppText } from "@/src/components/ui";
import { colors, fonts, radius, spacing, shadow } from "@/src/theme";
import { useAuth } from "@/src/auth";
import { AvatarConfig, AvatarMood, normalizeAvatar, useAvatarMood } from "@/src/avatar";
import { AvatarArt } from "@/src/components/AvatarArt";

/**
 * The participant's avatar: the parts they chose (Progress → Settings or
 * onboarding) plus today's mood from the backend. Only the mood and small
 * props change day to day — never the body — and they reset each morning.
 * Pass `config` / `mood` to preview (the builder); otherwise it's the
 * signed-in participant's own avatar.
 */
export function Avatar({
  size = 44,
  ring = false,
  config,
  mood,
  showProps = true,
}: {
  size?: number;
  ring?: boolean;
  config?: AvatarConfig;
  mood?: AvatarMood | null;
  showProps?: boolean;
}) {
  const { user } = useAuth();
  const live = useAvatarMood(mood === undefined && !!user);
  return (
    <AvatarArt
      size={size}
      ring={ring}
      config={config ?? normalizeAvatar(user?.avatar)}
      mood={mood === undefined ? live : mood}
      showProps={showProps}
    />
  );
}

export function IconCircle({
  icon,
  color,
  tint,
  size = 44,
  iconSize,
  children,
}: {
  icon?: React.ComponentProps<typeof Feather>["name"];
  color?: string;
  tint: string;
  size?: number;
  iconSize?: number;
  children?: React.ReactNode;
}) {
  return (
    <View style={{ width: size, height: size, borderRadius: size / 2, backgroundColor: tint, alignItems: "center", justifyContent: "center" }}>
      {children ?? (icon ? <Feather name={icon} size={iconSize ?? Math.round(size * 0.45)} color={color} /> : null)}
    </View>
  );
}

/** Seven small dots — effort only (days logged), never an outcome. */
export function WeekDots({
  days,
  on,
  off,
  size = 9,
  bar = false,
}: {
  days: boolean[];
  on: string;
  off: string;
  size?: number;
  bar?: boolean;
}) {
  return (
    <View style={{ flexDirection: "row", gap: bar ? 4 : 3 }}>
      {days.map((d, i) => (
        <View
          key={i}
          style={
            bar
              ? { flex: 1, height: 8, borderRadius: 4, backgroundColor: d ? on : off }
              : { width: size, height: size, borderRadius: size / 2, backgroundColor: d ? on : off }
          }
        />
      ))}
    </View>
  );
}

/** One Future Me bubble per screen. */
export function FutureMeCard({
  text,
  onPress,
  children,
  style,
  testID,
}: {
  text: string;
  onPress?: () => void;
  children?: React.ReactNode;
  style?: StyleProp<ViewStyle>;
  testID?: string;
}) {
  const body = (
    <View style={[styles.fm, style]}>
      <View style={{ flexDirection: "row", gap: spacing.md, alignItems: children ? "flex-start" : "center" }}>
        <Avatar size={48} />
        <View style={{ flex: 1, gap: 4 }}>
          <AppText variant="label" color={colors.muted} style={{ fontSize: 11, letterSpacing: 1.2 }}>
            FUTURE ME
          </AppText>
          <AppText variant="body" color={colors.onSurface} style={{ fontFamily: fonts.medium }}>
            {text}
          </AppText>
        </View>
        {onPress && !children && <Feather name="chevron-right" size={18} color={colors.brandPrimary} />}
      </View>
      {children}
    </View>
  );
  if (!onPress) return <View testID={testID}>{body}</View>;
  return (
    <Pressable onPress={onPress} testID={testID} accessibilityRole="button">
      {body}
    </Pressable>
  );
}

/** Opens Future Me's conversation with a question pre-filled for this screen. */
export function AskCoachButton({ question, label = "Ask Future Me", testID }: { question: string; label?: string; testID?: string }) {
  const router = useRouter();
  return (
    <Pressable
      onPress={() => router.push({ pathname: "/(tabs)/future-me", params: { q: question } })}
      style={styles.askCoach}
      accessibilityRole="button"
      accessibilityLabel={`${label}: ${question}`}
      testID={testID ?? "ask-coach"}
    >
      <Feather name="message-circle" size={15} color={colors.brandPrimary} />
      <AppText variant="label" color={colors.brandPrimary} style={{ fontSize: 13 }}>
        {label}
      </AppText>
    </Pressable>
  );
}

export function SectionTitle({ title, right }: { title: string; right?: React.ReactNode }) {
  return (
    <View style={{ flexDirection: "row", alignItems: "baseline", justifyContent: "space-between", marginBottom: spacing.md }}>
      <AppText variant="title" style={{ fontSize: 19 }}>
        {title}
      </AppText>
      {right}
    </View>
  );
}

export function PointsPill({ points }: { points: number }) {
  return (
    <View style={styles.pts}>
      <AppText variant="label" color={colors.onWarm} style={{ fontSize: 12 }}>
        +{points}
      </AppText>
    </View>
  );
}

/** A quiet white card with the soft lift used everywhere. */
export const cardStyle: ViewStyle = {
  backgroundColor: colors.surfaceSecondary,
  borderRadius: radius.lg,
  padding: spacing.xl,
  borderWidth: 1,
  borderColor: colors.border,
  ...(shadow.card as ViewStyle),
};

const styles = StyleSheet.create({
  fm: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, gap: spacing.md, borderWidth: 1, borderColor: colors.border, borderLeftWidth: 3, borderLeftColor: colors.brandPrimary },
  askCoach: {
    flexDirection: "row", alignItems: "center", alignSelf: "flex-start", gap: 6, paddingHorizontal: 12, paddingVertical: 8,
    borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary,
  },
  pts: { paddingHorizontal: 10, paddingVertical: 5, borderRadius: radius.pill, backgroundColor: colors.warmTint },
});
