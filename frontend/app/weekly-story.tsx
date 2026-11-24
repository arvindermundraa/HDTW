import React, { useEffect, useRef, useState } from "react";
import { View, StyleSheet, Pressable, ScrollView, ActivityIndicator, NativeSyntheticEvent, NativeScrollEvent } from "react-native";
import { useScreenSize } from "@/src/components/PhoneFrame";
import Animated, { useSharedValue, useAnimatedStyle, withTiming, Easing } from "react-native-reanimated";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Feather } from "@expo/vector-icons";
import { AppText } from "@/src/components/ui";
import { api } from "@/src/api";
import { colors, spacing, fonts } from "@/src/theme";
import { useReducedMotion } from "@/src/hooks/use-reduced-motion";
import { goBack } from "@/src/navigation";

type Chapter = { id: string; kicker: string; title: string; stat: string; body: string };

export default function WeeklyStory() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { width } = useScreenSize();
  const reducedMotion = useReducedMotion();

  const [chapters, setChapters] = useState<Chapter[] | null>(null);
  const [activeIndex, setActiveIndex] = useState(0);
  const scrollRef = useRef<ScrollView>(null);

  useEffect(() => {
    api.getWeeklyStory().then((d: any) => setChapters(d.chapters)).catch(() => setChapters([]));
  }, []);

  const onMomentumEnd = (e: NativeSyntheticEvent<NativeScrollEvent>) => {
    const idx = Math.round(e.nativeEvent.contentOffset.x / width);
    setActiveIndex(idx);
  };

  return (
    <View style={styles.c} testID="weekly-story-screen">
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <View>
          <AppText variant="label">YOUR WEEK</AppText>
          <AppText variant="title">In Review</AppText>
        </View>
        <Pressable onPress={() => goBack(router, "/")} hitSlop={10} testID="weekly-story-close">
          <Feather name="x" size={26} color={colors.onSurface} />
        </Pressable>
      </View>

      {!chapters ? (
        <View style={styles.loading}>
          <ActivityIndicator color={colors.brandPrimary} />
        </View>
      ) : chapters.length === 0 ? (
        <View style={styles.loading}>
          <AppText variant="body">Your week in review will be here once there's something to look back on.</AppText>
        </View>
      ) : (
        <>
          <ScrollView
            ref={scrollRef}
            horizontal
            pagingEnabled
            showsHorizontalScrollIndicator={false}
            onMomentumScrollEnd={onMomentumEnd}
            accessibilityRole="none"
          >
            {chapters.map((ch, i) => (
              <View key={ch.id} style={{ width }}>
                <ChapterPage chapter={ch} active={activeIndex === i} reducedMotion={reducedMotion} />
              </View>
            ))}
          </ScrollView>

          <View style={styles.dots} accessibilityElementsHidden importantForAccessibility="no-hide-descendants">
            {chapters.map((ch, i) => (
              <View key={ch.id} style={[styles.dot, activeIndex === i && styles.dotActive]} />
            ))}
          </View>
        </>
      )}
    </View>
  );
}

function ChapterPage({ chapter, active, reducedMotion }: { chapter: Chapter; active: boolean; reducedMotion: boolean }) {
  const opacity = useSharedValue(reducedMotion ? 1 : 0);
  const translateY = useSharedValue(reducedMotion ? 0 : 14);

  useEffect(() => {
    if (!active) return;
    if (reducedMotion) {
      opacity.value = 1;
      translateY.value = 0;
      return;
    }
    // Cosmetic "arrival" per chapter — PRD §7 governing principle: pacing
    // only, never hides content. The AppText children below render the full
    // chapter text immediately regardless of this animation, so a screen
    // reader gets everything at once (same pattern as coach.tsx's LLM-04 fix).
    opacity.value = 0;
    translateY.value = 14;
    opacity.value = withTiming(1, { duration: 420, easing: Easing.out(Easing.cubic) });
    translateY.value = withTiming(0, { duration: 420, easing: Easing.out(Easing.cubic) });
  }, [active, reducedMotion]);

  const style = useAnimatedStyle(() => ({
    opacity: opacity.value,
    transform: [{ translateY: translateY.value }],
  }));

  return (
    <View style={styles.page}>
      <Animated.View style={style}>
        <AppText variant="label" color={colors.brandPrimary}>
          {chapter.kicker}
        </AppText>
        <AppText variant="displayLg" style={{ marginTop: spacing.sm }}>
          {chapter.title}
        </AppText>
        {!!chapter.stat && (
          <AppText variant="title" color={colors.onSurface} style={{ marginTop: spacing.lg }}>
            {chapter.stat}
          </AppText>
        )}
        <AppText variant="body" style={{ marginTop: spacing.lg, lineHeight: 26 }}>
          {chapter.body}
        </AppText>
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  c: { flex: 1, backgroundColor: colors.surface },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "flex-start",
    paddingHorizontal: spacing.xl,
    paddingBottom: spacing.lg,
  },
  loading: { flex: 1, alignItems: "center", justifyContent: "center", paddingHorizontal: spacing.xl },
  page: { flex: 1, paddingHorizontal: spacing.xl, justifyContent: "center", paddingBottom: spacing["3xl"] },
  dots: { flexDirection: "row", justifyContent: "center", gap: spacing.sm, paddingBottom: spacing.xl },
  dot: { width: 6, height: 6, borderRadius: 3, backgroundColor: colors.surfaceTertiary },
  dotActive: { backgroundColor: colors.brandPrimary, width: 18 },
});
