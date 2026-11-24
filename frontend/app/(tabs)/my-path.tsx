import React, { useCallback, useEffect, useRef, useState } from "react";
import { View, StyleSheet, ScrollView, ActivityIndicator, Pressable, Animated, Easing } from "react-native";
import { useScreenSize } from "@/src/components/PhoneFrame";
import { useFocusEffect, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Svg, { Circle, Path, Rect } from "react-native-svg";
import { Feather } from "@expo/vector-icons";
import { AppText, Button, Disclaimer } from "@/src/components/ui";
import { Avatar, IconCircle, cardStyle } from "@/src/components/llhs";
import { api } from "@/src/api";
import { colors, domain, radius, spacing } from "@/src/theme";
import { BEHAVIOR_ICON, Milestone, PathWeek, TRAIL_D, stopPositions } from "@/src/path";
import { useReducedMotion } from "@/src/hooks/use-reduced-motion";

// My Path — the illustrated trail with one stop per week of the 8-week
// program (backend personal_path.py; study team feedback, section 3). The
// avatar stands on the current week; done weeks are checked; upcoming weeks
// are "Coming up" (no locks); the trail runs on past week 8 into an open
// horizon instead of ending at a flag. Hover a stop (web) to peek at that
// week's parts; tap it to open them below. Milestones are skills applied,
// never content views, weight or an outcome.

function tone(behavior: string) {
  if (["focus_area", "practice", "apply"].includes(behavior)) return { color: domain.food.text, tint: domain.food.tint };
  return { color: colors.brandPrimary, tint: colors.surfaceTertiary };
}

const dayLabel = (iso: string) => {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("en-US", { month: "short", day: "numeric" });
};

export default function MyPath() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { width } = useScreenSize();
  const reduced = useReducedMotion();
  const [path, setPath] = useState<any>(null);
  const [error, setError] = useState(false);
  const [selectedWeek, setSelectedWeek] = useState<number | null>(null);
  const [hoverWeek, setHoverWeek] = useState<number | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);

  const load = useCallback(() => {
    setError(false);
    api
      .getPath()
      .then(setPath)
      .catch(() => setError(true));
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  // A gentle bob for the avatar (off with reduced motion).
  const bob = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    if (reduced) return;
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(bob, { toValue: -4, duration: 900, easing: Easing.inOut(Easing.sin), useNativeDriver: true }),
        Animated.timing(bob, { toValue: 0, duration: 900, easing: Easing.inOut(Easing.sin), useNativeDriver: true }),
      ])
    );
    loop.start();
    return () => loop.stop();
  }, [bob, reduced]);

  if (!path) {
    return (
      <View style={styles.center}>
        {error ? (
          <>
            <AppText variant="subtitle">We couldn&apos;t load your path</AppText>
            <Button title="Try again" onPress={load} style={{ marginTop: spacing.lg, paddingHorizontal: spacing["2xl"] }} />
          </>
        ) : (
          <ActivityIndicator color={colors.brandPrimary} />
        )}
      </View>
    );
  }

  const weeks: PathWeek[] = path.weeks ?? [];
  const now: number = path.current_week;
  const shownWeek = weeks.find((w) => w.week === (selectedWeek ?? now)) ?? weeks[0];
  const peekWeek = hoverWeek != null ? weeks.find((w) => w.week === hoverWeek) : null;
  const days = path.next_checkin?.days_until;

  const w = Math.min(width, 520);
  const s = w / 390;
  const h = 440 * s;
  const stops = stopPositions(weeks.length);
  const here = stops[now - 1];

  const go = (m: Milestone) => {
    if (!m.action) return;
    router.push({ pathname: m.action.route as any, params: m.action.params ?? {} });
  };
  const select = (week: number) => {
    setSelectedWeek(week);
    setOpenId(null);
  };

  return (
    <View style={styles.c} testID="path-detail-screen">
      <ScrollView contentContainerStyle={{ paddingTop: insets.top + spacing.md, paddingBottom: spacing["3xl"] }} showsVerticalScrollIndicator={false}>
        <View style={{ paddingHorizontal: spacing.xl, gap: 4 }}>
          <AppText variant="display">My Path</AppText>
          <AppText variant="body" testID="path-count">
            Week {now} of {weeks.length} · {path.achieved_count} of {path.total} milestones · tap a week to see it
          </AppText>
        </View>

        {/* A goal-specific line, only from what was logged */}
        {!!path.message && (
          <View style={[styles.message, { marginHorizontal: spacing.xl, marginTop: spacing.lg }]} testID="path-message">
            <Avatar size={40} />
            <AppText variant="body" style={{ flex: 1, fontSize: 15, lineHeight: 21 }}>
              {path.message}
            </AppText>
          </View>
        )}

        {/* Illustrated trail: one stop per week, open horizon at the top */}
        <View style={{ width: w, height: h, marginTop: spacing.lg, alignSelf: "center", backgroundColor: "#EFF2F0" }} testID="path-trail">
          <Svg width={w} height={h} viewBox="0 0 390 440" style={StyleSheet.absoluteFill}>
            {/* sunrise on the horizon, where the trail keeps going */}
            <Circle cx={316} cy={92} r={46} fill="#F4E3BF" />
            <Circle cx={316} cy={92} r={30} fill="#EFD198" />
            <Path d="M0 120 C 80 96, 170 104, 240 112 S 350 92, 390 100 L 390 440 L 0 440 Z" fill="#E7ECE8" />
            <Path d="M0 150 C 80 110, 150 120, 220 140 S 340 100, 390 120 L 390 440 L 0 440 Z" fill="#E3E9E5" />
            <Path d="M0 240 C 90 200, 180 230, 260 210 S 360 190, 390 200 L 390 440 L 0 440 Z" fill="#D6E0DA" />
            <Path d="M0 340 C 100 300, 200 330, 290 310 S 370 300, 390 305 L 390 440 L 0 440 Z" fill="#C8D5CD" />
            <Path d={TRAIL_D} fill="none" stroke="#F7F5EF" strokeWidth={30} strokeLinecap="round" />
            <Path d={TRAIL_D} fill="none" stroke="#CFC7B5" strokeWidth={2} strokeDasharray="6 9" strokeLinecap="round" />
            <Rect x={46} y={300} width={6} height={26} rx={2} fill="#8C8171" />
            <Circle cx={49} cy={290} r={20} fill="#8FA99A" />
            <Rect x={346} y={236} width={6} height={24} rx={2} fill="#8C8171" />
            <Circle cx={349} cy={226} r={18} fill="#9AB3A5" />
            <Rect x={30} y={170} width={5} height={20} rx={2} fill="#8C8171" />
            <Circle cx={32} cy={162} r={14} fill="#A6BCAF" />
            <Rect x={336} y={386} width={7} height={30} rx={2} fill="#8C8171" />
            <Circle cx={339} cy={372} r={24} fill="#7F9C8B" />
            <Circle cx={96} cy={400} r={9} fill="#AFC2B7" />
          </Svg>

          <View style={[styles.horizonTag, { left: 250 * s, top: 34 * s }]} pointerEvents="none">
            <AppText variant="label" style={{ fontSize: 11 }} color={colors.onWarm}>
              Beyond week 8
            </AppText>
          </View>

          {/* Week stops */}
          {weeks.map((wk, i) => {
            if (wk.week === now) return null; // the avatar stands here
            const p = stops[i];
            const isSel = shownWeek?.week === wk.week && selectedWeek != null;
            const done = wk.status === "done";
            const upcoming = !wk.available;
            return (
              <Pressable
                key={wk.week}
                onPress={() => select(wk.week)}
                onHoverIn={() => setHoverWeek(wk.week)}
                onHoverOut={() => setHoverWeek((v) => (v === wk.week ? null : v))}
                hitSlop={10}
                accessibilityRole="button"
                accessibilityLabel={`Week ${wk.week}, ${wk.title}: ${done ? "done" : upcoming ? "coming up" : `${wk.achieved} of ${wk.total} done`}`}
                testID={`stop-${wk.week}`}
                style={{ position: "absolute", left: p.x * s - 18, top: p.y * s - 18, width: 36, height: 36, alignItems: "center", justifyContent: "center" }}
              >
                <View style={[styles.stop, done ? styles.stopDone : upcoming ? styles.stopSoon : styles.stopOpen, isSel && styles.stopSelected]}>
                  {done ? (
                    <Feather name="check" size={15} color="#FFFFFF" />
                  ) : (
                    <AppText variant="label" style={{ fontSize: 12 }} color={upcoming ? colors.muted : colors.onWarm}>
                      {wk.week}
                    </AppText>
                  )}
                </View>
              </Pressable>
            );
          })}

          {/* You are here */}
          {here && (
            <Animated.View style={{ position: "absolute", left: here.x * s - 28, top: here.y * s - 28, transform: [{ translateY: bob }] }}>
              <Pressable
                onPress={() => select(now)}
                onHoverIn={() => setHoverWeek(now)}
                onHoverOut={() => setHoverWeek((v) => (v === now ? null : v))}
                accessibilityRole="button"
                accessibilityLabel={`You are here: week ${now}`}
                testID="path-avatar"
              >
                <Avatar size={56} ring />
              </Pressable>
            </Animated.View>
          )}
          {here && (
            <View pointerEvents="none" style={[styles.here, here.x > 200 ? { right: w - here.x * s + 34, top: here.y * s - 14 } : { left: here.x * s + 34, top: here.y * s - 14 }]}>
              <AppText variant="label" color="#FFFFFF" style={{ fontSize: 12 }} numberOfLines={1}>
                You are here · Week {now}
              </AppText>
            </View>
          )}

          {/* Hover peek: the week's parts at a glance */}
          {peekWeek && (() => {
            const p = stops[peekWeek.week - 1];
            const left = Math.min(Math.max(8, p.x * s - 110), w - 228);
            const below = p.y * s < h / 2;
            return (
              <View pointerEvents="none" style={[styles.peek, { left }, below ? { top: p.y * s + 30 } : { bottom: h - p.y * s + 30 }]} testID="path-peek">
                <AppText variant="label" color={colors.muted} style={{ fontSize: 11 }}>
                  WEEK {peekWeek.week}
                  {!peekWeek.available ? ` · COMING UP ${dayLabel(peekWeek.opens_on).toUpperCase()}` : ` · ${peekWeek.achieved} OF ${peekWeek.total}`}
                </AppText>
                <AppText variant="subtitle" style={{ fontSize: 14 }}>
                  {peekWeek.title}
                </AppText>
                {peekWeek.milestones.map((m) => (
                  <View key={m.id} style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                    <Feather name={m.achieved ? "check-circle" : "circle"} size={12} color={m.achieved ? domain.food.text : colors.muted} />
                    <AppText variant="caption" style={{ fontSize: 12, flex: 1 }} numberOfLines={1}>
                      {m.label}
                    </AppText>
                  </View>
                ))}
              </View>
            );
          })()}
        </View>

        <View style={{ paddingHorizontal: spacing.xl, gap: spacing.lg, marginTop: spacing.lg }}>
          {/* The selected week (this week by default) and its parts */}
          {shownWeek && (
            <View style={[cardStyle, { gap: 2, padding: spacing.lg }]} testID="path-week-card">
              <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
                <AppText variant="label" color={shownWeek.week === now ? colors.brandPrimary : colors.muted} style={{ fontSize: 11, letterSpacing: 0.8 }}>
                  WEEK {shownWeek.week}
                  {shownWeek.week === now ? " · YOU ARE HERE" : !shownWeek.available ? ` · COMING UP ${dayLabel(shownWeek.opens_on).toUpperCase()}` : ""}
                </AppText>
                <View style={{ flex: 1 }} />
                <AppText variant="caption">
                  {shownWeek.achieved} of {shownWeek.total}
                </AppText>
              </View>
              <AppText variant="subtitle" style={{ fontSize: 17 }}>
                {shownWeek.title}
              </AppText>
              <View style={{ gap: 2, marginTop: spacing.xs }}>
                {shownWeek.milestones.map((m) => (
                  <MilestoneRow
                    key={m.id}
                    m={m}
                    upcoming={!shownWeek.available}
                    open={openId === m.id}
                    onPress={() => setOpenId(openId === m.id ? null : m.id)}
                    onAction={() => go(m)}
                  />
                ))}
              </View>
            </View>
          )}

          {/* Food-recall countdown — anticipation, never a "results day" */}
          <View style={[cardStyle, { flexDirection: "row", alignItems: "center", gap: spacing.lg, padding: spacing.lg }]} testID="checkin-countdown">
            <View style={styles.countRing}>
              {days == null ? (
                <Feather name="calendar" size={20} color={colors.onSurface} />
              ) : (
                <>
                  <AppText variant="subtitle" style={{ fontSize: 18, lineHeight: 20 }}>
                    {days}
                  </AppText>
                  <AppText variant="label" color={colors.muted} style={{ fontSize: 9 }}>
                    {days === 1 ? "DAY" : "DAYS"}
                  </AppText>
                </>
              )}
            </View>
            <View style={{ flex: 1, gap: 2 }}>
              <AppText variant="subtitle">{days == null ? "Your food recalls" : days === 0 ? "Food recalls are open" : "Until your next food recalls"}</AppText>
              <AppText variant="caption" style={{ color: colors.onSurfaceSecondary }}>
                {days == null ? path.next_checkin?.message : "Your habits so far are already part of your path. Nothing to prepare."}
              </AppText>
            </View>
          </View>

          <Disclaimer text="Your path moves with what you do, never with weight, appearance or a predicted outcome." />
        </View>
      </ScrollView>
    </View>
  );
}

function MilestoneRow({
  m,
  upcoming,
  open,
  onPress,
  onAction,
}: {
  m: Milestone;
  upcoming: boolean;
  open: boolean;
  onPress: () => void;
  onAction: () => void;
}) {
  const t = tone(m.behavior);
  const prog = m.progress;
  const showProgress = !m.achieved && prog && prog.target > 1 && !upcoming;
  return (
    <View>
      <Pressable onPress={onPress} style={styles.mRow} testID={`milestone-${m.id}`} accessibilityRole="button">
        {m.achieved ? (
          <View style={[styles.mDot, { backgroundColor: t.color }]}>
            <Feather name="check" size={11} color="#FFFFFF" />
          </View>
        ) : (
          <View style={[styles.mDot, styles.mDotOpen]} />
        )}
        <AppText variant="body" style={{ flex: 1, fontSize: 14 }} color={m.achieved ? colors.onSurface : colors.onSurfaceSecondary}>
          {m.label}
        </AppText>
        {showProgress ? (
          <AppText variant="caption">
            {prog!.current}/{prog!.target}
          </AppText>
        ) : !m.achieved && upcoming ? (
          <AppText variant="caption" color={colors.muted}>
            Coming up
          </AppText>
        ) : null}
      </Pressable>
      {open && (
        <View style={styles.mDetail} testID="milestone-card">
          <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
            <IconCircle icon={BEHAVIOR_ICON[m.behavior] ?? "circle"} color={t.color} tint={t.tint} size={32} iconSize={15} />
            <AppText variant="caption" style={{ flex: 1 }}>
              {m.detail}
            </AppText>
          </View>
          {m.action && !m.achieved && <Button title={m.action.label} variant="secondary" onPress={onAction} testID="milestone-action" />}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  c: { flex: 1, backgroundColor: colors.surface },
  center: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.surface },
  message: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    padding: spacing.lg,
    borderRadius: radius.lg,
    backgroundColor: domain.food.tint,
  },
  stop: { width: 30, height: 30, borderRadius: 15, alignItems: "center", justifyContent: "center", borderWidth: 3 },
  stopDone: { backgroundColor: domain.food.main, borderColor: "#FFFFFF" },
  stopOpen: { backgroundColor: colors.warmTint, borderColor: colors.warm },
  stopSoon: { backgroundColor: "#FFFFFF", borderColor: "#9DB5AB", borderStyle: "dashed", borderWidth: 2 },
  stopSelected: { transform: [{ scale: 1.2 }], boxShadow: "0px 0px 0px 4px rgba(245,184,46,0.45)" },
  here: {
    position: "absolute",
    paddingHorizontal: 12,
    paddingVertical: 7,
    borderRadius: 14,
    borderBottomLeftRadius: 4,
    backgroundColor: colors.surfaceInverse,
  },
  horizonTag: { position: "absolute", paddingHorizontal: 10, paddingVertical: 4, borderRadius: 10, backgroundColor: "rgba(255,255,255,0.75)" },
  peek: {
    position: "absolute",
    width: 220,
    gap: 3,
    padding: spacing.md,
    borderRadius: radius.md,
    backgroundColor: "#FFFFFF",
    boxShadow: "0px 4px 14px rgba(14,42,36,0.16)",
  },
  mRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingVertical: 6 },
  mDot: { width: 18, height: 18, borderRadius: 9, alignItems: "center", justifyContent: "center" },
  mDotOpen: { borderWidth: 1.5, borderColor: colors.borderStrong },
  mDetail: { marginLeft: 26, marginBottom: spacing.sm, gap: spacing.sm },
  countRing: {
    width: 56,
    height: 56,
    borderRadius: 28,
    borderWidth: 3,
    borderColor: colors.warm,
    alignItems: "center",
    justifyContent: "center",
  },
});
