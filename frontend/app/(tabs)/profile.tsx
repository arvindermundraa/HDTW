import React, { useCallback, useState } from "react";
import { View, StyleSheet, ScrollView, Pressable, ActivityIndicator, Image, ImageStyle, StyleProp } from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Feather } from "@expo/vector-icons";
import { AppText, Button } from "@/src/components/ui";
import { Avatar, IconCircle, cardStyle } from "@/src/components/llhs";
import { FOCUS_AREA_LABEL } from "@/src/food";
import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { colors, domain, fonts, radius, spacing } from "@/src/theme";
import { GoalRings } from "@/src/components/GoalRings";
import { DOMAIN, GoalSnapshot } from "@/src/daily-goals";
import { publishMood } from "@/src/avatar";
import { BADGE_ART, FLUENT } from "@/src/fluent";
import { STUDY_TZ } from "@/src/study-time";

// Progress — follows the client mockup's layout (9/10/26 deck, Progress /
// "Play" screen) inside the app's mature style. Points, streak, badges and
// levels are effort-only. Deliberately left out of the mockup: the Rewards
// tab (it hints at variable rewards), invented badges and challenges, and
// anything about water. Only the 4 real badges and the 2 real challenges
// (cohort goal, Your Wing) appear. Fluent 3D figures are accents only.
const LEVEL_SIZE = 200; // points per level
const LEVEL_NAMES = ["Getting started", "Building healthy habits", "Finding your rhythm", "Steady habits", "Habit builder"];

type Tab = "badges" | "challenges" | "streaks";
const TAB_LABEL: Record<Tab, string> = { badges: "Badges", challenges: "Challenges", streaks: "Streaks" };

// Pale domain tints behind each figure — never bright pastels.
const BADGE_TINT: Record<string, string> = {
  "First Lesson": domain.rest.tint,
  "Skill Builder": domain.move.tint,
  "Consistent Logger": domain.food.tint,
  "Balanced Week": colors.warmTint,
};

function dayLabel(isoDate: string, isToday: boolean): string {
  if (isToday) return "Today";
  const [y, m, d] = isoDate.split("-").map(Number);
  // 18:00 UTC is noon-ish in Chicago both during CDT and CST — well inside
  // the study day, so DST crossings never shift the weekday label.
  const anchor = new Date(Date.UTC(y, m - 1, d, 18, 0, 0));
  return anchor.toLocaleDateString(undefined, { weekday: "long", month: "short", day: "numeric", timeZone: STUDY_TZ });
}

/** Future Me's line: fixed text chosen by a simple rule, never random.
 *  `daysLogged` is the number of distinct study-TZ days this week with at
 *  least one Eat, Move or Sleep log — read from the daily-goals snapshot's
 *  `week.any_days` so Today, Future Me and Progress stay in step. */
function futureMeLine(daysLogged: number): string {
  if (daysLogged >= 7) return "You logged every day this week. That's real consistency.";
  if (daysLogged >= 2) return `You logged ${daysLogged} days this week. Keep it going!`;
  if (daysLogged === 1) return "You logged 1 day this week. One more makes a rhythm.";
  return "A fresh week. One small log is a great start.";
}

/** Per-activity week summary — "Logged a meal on 3 days this week" etc.
 *  Never a combined "all rings on X of Y" count: Eat, Move and Sleep stay
 *  separate per the design brief. */
function weekLine(d: "food" | "move" | "rest", n: number): string {
  if (d === "food") {
    if (n === 0) return "No meals logged yet this week";
    if (n === 1) return "Logged a meal on 1 day this week";
    return `Logged a meal on ${n} days this week`;
  }
  if (d === "move") {
    if (n === 0) return "No movement logged yet this week";
    if (n === 1) return "Moved on 1 day this week";
    return `Moved on ${n} days this week`;
  }
  if (n === 0) return "No sleep logged yet this week";
  if (n === 1) return "Logged sleep on 1 night this week";
  return `Logged sleep on ${n} nights this week`;
}

function Fluent({ source, size, style }: { source: number; size: number; style?: StyleProp<ImageStyle> }) {
  return <Image source={source} style={[{ width: size, height: size }, style]} resizeMode="contain" accessibilityIgnoresInvertColors />;
}

/** A bar split into equal segments, filled in proportion to progress. */
function SegmentBar({ current, target, color, segments = 7 }: { current: number; target: number; color: string; segments?: number }) {
  const filled = target > 0 ? Math.min(segments, Math.floor((current / target) * segments)) : 0;
  return (
    <View style={{ flexDirection: "row", gap: 3 }}>
      {Array.from({ length: segments }, (_, i) => (
        <View key={i} style={{ flex: 1, height: 8, borderRadius: 3, backgroundColor: i < filled ? color : colors.surfaceTertiary }} />
      ))}
    </View>
  );
}

type Challenge = {
  id: string; image: number; tint: string; color: string; title: string; description: string;
  current: number; target: number; unit: string; done: boolean; onPress?: () => void;
};

export default function Progress() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user, signOut } = useAuth();
  const [gam, setGam] = useState<any>(null);
  const [cohort, setCohort] = useState<any>(null);
  const [wing, setWing] = useState<any>(undefined);
  const [rings, setRings] = useState<GoalSnapshot | null>(null);
  const [error, setError] = useState(false);
  const [tab, setTab] = useState<Tab>("badges");

  const load = useCallback(async () => {
    setError(false);
    const [g, c, w, r] = await Promise.allSettled([
      api.getGamification(), api.getCohort(), api.getMyWing(), api.getDailyGoals(),
    ]);
    if (g.status === "fulfilled") setGam(g.value);
    else setError(true);
    if (c.status === "fulfilled") setCohort(c.value);
    if (w.status === "fulfilled") setWing(w.value?.wing ?? null);
    if (r.status === "fulfilled") {
      setRings(r.value);
      publishMood(r.value.mood);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  const onSignOut = async () => {
    await signOut();
    router.replace("/welcome");
  };

  if (!gam) {
    return (
      <View style={styles.center}>
        {error ? (
          <>
            <AppText variant="subtitle">We couldn&apos;t load your progress</AppText>
            <Button title="Try again" onPress={load} style={{ marginTop: spacing.lg, paddingHorizontal: spacing["2xl"] }} />
          </>
        ) : (
          <ActivityIndicator color={colors.brandPrimary} />
        )}
      </View>
    );
  }

  const points = gam.points ?? 0;
  const level = Math.floor(points / LEVEL_SIZE) + 1;
  const into = points % LEVEL_SIZE;
  const earned: string[] = gam.badges ?? [];
  const allBadges: string[] = gam.all_badges ?? Object.keys(BADGE_ART);
  const ringDays = [...(rings?.days ?? [])].reverse(); // today first
  // Per-activity weekly counts come straight from the daily-goals snapshot —
  // same backend helper feeds /api/future-me, so these numbers match the
  // ones Today shows and the ones Future Me reads for its week line.
  const weekly = rings?.week ?? null;
  const daysLogged = weekly?.any_days ?? null;

  const stats = [
    { label: "Points", value: `${points}`, image: FLUENT.star, tint: colors.warmTint },
    { label: "Day streak", value: `${gam.streak ?? 0}`, image: FLUENT.fire, tint: domain.move.tint },
    { label: "Badges", value: `${earned.filter((b) => allBadges.includes(b)).length} of ${allBadges.length}`, image: FLUENT.shield, tint: domain.food.tint },
  ];

  // The only two challenges that exist: the cohort goal and Your Wing.
  const challenges: Challenge[] = [];
  if (cohort) {
    challenges.push({
      id: "cohort", image: FLUENT.handshake, tint: domain.food.tint, color: domain.food.main,
      title: cohort.title, description: `Everyone's balanced meals add up together. You've added ${cohort.your_contribution}.`,
      current: cohort.current, target: cohort.target, unit: "meals", done: cohort.current >= cohort.target,
    });
  }
  if (wing) {
    const cur = wing.progress?.current ?? 0;
    const tgt = wing.progress?.target ?? 0;
    challenges.push({
      id: "wing", image: FLUENT.wing, tint: domain.rest.tint, color: domain.rest.main,
      title: wing.name, description: `${wing.goal_label} · ${wing.members?.length ?? 1} in your Wing`,
      current: cur, target: tgt, unit: wing.goal_unit ?? "", done: tgt > 0 && cur >= tgt,
      onPress: () => router.push("/(tabs)/social"),
    });
  }
  const active = challenges.filter((c) => !c.done);
  const completed = challenges.filter((c) => c.done);

  const challengeRow = (c: Challenge) => {
    const body = (
      <View style={[cardStyle, styles.challenge]} testID={`challenge-${c.id}`}>
        <View style={[styles.figure, { backgroundColor: c.tint }]}>
          <Fluent source={c.image} size={30} />
        </View>
        <View style={{ flex: 1, gap: 4 }}>
          <AppText variant="subtitle" style={{ fontSize: 15 }} numberOfLines={1}>
            {c.title}
          </AppText>
          <AppText variant="caption" style={{ color: colors.onSurfaceSecondary }} numberOfLines={2}>
            {c.description}
          </AppText>
          {c.done ? (
            <View style={styles.doneChip}>
              <Feather name="check" size={13} color={domain.food.text} />
              <AppText variant="label" color={domain.food.text} style={{ fontSize: 12 }}>
                Completed
              </AppText>
            </View>
          ) : (
            <View style={{ gap: 4, marginTop: 4 }}>
              <SegmentBar current={c.current} target={c.target} color={c.color} />
              <AppText variant="caption" style={{ fontSize: 12 }}>
                {c.current} of {c.target} {c.unit}
              </AppText>
            </View>
          )}
        </View>
        {c.onPress && <Feather name="chevron-right" size={18} color={colors.muted} />}
      </View>
    );
    return c.onPress ? (
      <Pressable key={c.id} onPress={c.onPress} accessibilityRole="button">
        {body}
      </Pressable>
    ) : (
      <View key={c.id}>{body}</View>
    );
  };

  const challengeSections = (
    <>
      <View style={{ gap: spacing.md }} testID="active-challenges">
        <AppText variant="title" style={{ fontSize: 17 }}>
          Active challenges
        </AppText>
        {active.map(challengeRow)}
        {wing === null && (
          <Pressable onPress={() => router.push("/(tabs)/social")} style={[cardStyle, styles.challenge]} testID="challenge-join-wing">
            <View style={[styles.figure, { backgroundColor: domain.rest.tint }]}>
              <Fluent source={FLUENT.wing} size={30} />
            </View>
            <View style={{ flex: 1, gap: 4 }}>
              <AppText variant="subtitle" style={{ fontSize: 15 }}>
                Join or create a Wing
              </AppText>
              <AppText variant="caption" style={{ color: colors.onSurfaceSecondary }}>
                A small group working toward one shared goal. No rankings.
              </AppText>
            </View>
            <Feather name="chevron-right" size={18} color={colors.muted} />
          </Pressable>
        )}
      </View>
      {completed.length > 0 && (
        <View style={{ gap: spacing.md }} testID="completed-challenges">
          <AppText variant="title" style={{ fontSize: 17 }}>
            Completed challenges
          </AppText>
          {completed.map(challengeRow)}
        </View>
      )}
    </>
  );

  return (
    <ScrollView
      style={styles.c}
      contentContainerStyle={{ paddingTop: insets.top + spacing.md, paddingHorizontal: spacing.xl, paddingBottom: spacing["3xl"], gap: spacing.lg }}
      showsVerticalScrollIndicator={false}
      testID="progress-screen"
    >
      {/* Header: title on the left; your avatar and one Future Me line on the right */}
      <View style={{ gap: spacing.md }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.md }}>
          <View style={{ flex: 1, gap: 2 }}>
            <AppText variant="display">Your Progress</AppText>
            <AppText variant="body">Small steps. Real progress.</AppText>
          </View>
          <Pressable onPress={() => router.push("/avatar")} accessibilityRole="button" accessibilityLabel="Edit your avatar" hitSlop={6} testID="progress-avatar">
            <Avatar size={64} />
          </Pressable>
        </View>
        {daysLogged !== null && (
          <Pressable onPress={() => router.push("/(tabs)/future-me")} style={styles.bubble} accessibilityRole="button" testID="future-me-bubble">
            <View style={styles.bubbleTail} />
            <AppText variant="body" color={colors.onSurface} style={{ fontFamily: fonts.medium, fontSize: 14, lineHeight: 20 }}>
              {futureMeLine(daysLogged)}
            </AppText>
            <AppText variant="caption" style={{ fontSize: 11, marginTop: 2 }}>
              — Future Me
            </AppText>
          </Pressable>
        )}
      </View>

      {/* Stat row: one card, three tinted tiles */}
      <View style={[cardStyle, styles.statCard]} testID="stat-row">
        {stats.map((s) => (
          <View key={s.label} style={[styles.statTile, { backgroundColor: s.tint }]}>
            <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
              <Fluent source={s.image} size={28} />
              <AppText variant="display" style={{ fontSize: 19, lineHeight: 23, flexShrink: 1 }} numberOfLines={1}>
                {s.value}
              </AppText>
            </View>
            <AppText variant="caption" style={{ fontSize: 12, lineHeight: 15 }} numberOfLines={1}>
              {s.label}
            </AppText>
          </View>
        ))}
      </View>

      {/* Level card */}
      <View style={[cardStyle, styles.levelCard]} testID="level-card">
        <View style={{ flex: 1, gap: 6 }}>
          <AppText variant="subtitle" style={{ fontSize: 18 }}>
            Level {level}
          </AppText>
          <AppText variant="caption">{LEVEL_NAMES[Math.min(level, LEVEL_NAMES.length) - 1]}</AppText>
          <View style={[styles.track, { marginTop: 6 }]}>
            <View style={[styles.fill, { width: `${(into / LEVEL_SIZE) * 100}%` }]} />
          </View>
          <AppText variant="caption" style={{ fontSize: 12 }}>
            {into} / {LEVEL_SIZE} points
          </AppText>
        </View>
        <View style={{ alignItems: "center", gap: 6, width: 104 }}>
          <View style={styles.mountainTile}>
            <Fluent source={FLUENT.mountain} size={50} />
            <Fluent source={FLUENT.flag} size={22} style={styles.flag} />
          </View>
          <View style={styles.levelChip}>
            <AppText variant="label" color={colors.onBrandTertiary} style={{ fontSize: 11, lineHeight: 14, textAlign: "center" }}>
              On your way to Level {level + 1}
            </AppText>
          </View>
        </View>
      </View>

      {/* Tabs — no Rewards tab, on purpose */}
      <View style={styles.segment} accessibilityRole="tablist">
        {(["badges", "challenges", "streaks"] as Tab[]).map((t) => (
          <Pressable
            key={t}
            onPress={() => setTab(t)}
            style={[styles.segBtn, tab === t && styles.segOn]}
            accessibilityRole="tab"
            accessibilityState={{ selected: tab === t }}
            testID={`progress-tab-${t}`}
          >
            <AppText variant="label" color={tab === t ? colors.onBrandPrimary : colors.muted} style={{ fontSize: 14 }}>
              {TAB_LABEL[t]}
            </AppText>
          </Pressable>
        ))}
      </View>

      {tab === "badges" && (
        <>
          <View style={{ gap: spacing.md }} testID="your-badges">
            <AppText variant="title" style={{ fontSize: 17 }}>
              Your badges
            </AppText>
            <View style={[cardStyle, styles.badgeRow]}>
              {allBadges.map((b) => {
                const art = BADGE_ART[b];
                const has = earned.includes(b);
                return (
                  <View key={b} style={styles.badge} testID={`badge-${b}`} accessibilityLabel={`${b}: ${has ? "earned" : "not yet"}. ${art?.rule ?? ""}`}>
                    <View style={[styles.badgeCircle, { backgroundColor: has ? BADGE_TINT[b] ?? colors.surfaceTertiary : colors.surfaceTertiary }]}>
                      {art && <Fluent source={art.image} size={34} style={!has && styles.unearned} />}
                    </View>
                    <AppText variant="label" style={{ textAlign: "center", fontSize: 12, lineHeight: 15 }} color={has ? colors.onSurface : colors.muted}>
                      {b}
                    </AppText>
                    <AppText variant="caption" style={{ textAlign: "center", fontSize: 11, lineHeight: 14 }}>
                      {art?.rule}
                    </AppText>
                    {!has && (
                      <AppText variant="caption" style={{ fontSize: 11, lineHeight: 14, fontFamily: fonts.semibold }}>
                        Not yet
                      </AppText>
                    )}
                  </View>
                );
              })}
            </View>
          </View>
          {challengeSections}
        </>
      )}

      {tab === "challenges" && challengeSections}

      {tab === "streaks" && (
        <View style={{ gap: spacing.md }} testID="ring-history">
          <View style={[cardStyle, { flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.lg }]}>
            <View style={[styles.figure, { backgroundColor: domain.move.tint }]}>
              <Fluent source={FLUENT.fire} size={30} />
            </View>
            <View style={{ flex: 1 }}>
              <AppText variant="subtitle" style={{ fontSize: 16 }}>
                {gam.streak ?? 0} day logging streak
              </AppText>
              <AppText variant="caption">Missing a day never costs you anything.</AppText>
            </View>
          </View>
          {weekly && (
            <View style={[cardStyle, { gap: 6, padding: spacing.lg }]} testID="week-activity-summary">
              <AppText variant="label" style={{ fontSize: 13 }}>
                This week
              </AppText>
              {(["food", "move", "rest"] as const).map((d) => {
                const n = d === "food" ? weekly.eat_days : d === "move" ? weekly.move_days : weekly.rest_days;
                return (
                  <View key={d} style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                    <View style={[styles.weekDot, { backgroundColor: domain[d].main }]} />
                    <AppText variant="caption" style={{ fontSize: 12 }} testID={`week-days-${d}`}>
                      {weekLine(d, n)}
                    </AppText>
                  </View>
                );
              })}
            </View>
          )}
          {ringDays.length === 0 ? (
            <AppText variant="caption" style={{ textAlign: "center" }}>
              Set your daily goals and each day&apos;s rings will show here.
            </AppText>
          ) : (
            <View style={[cardStyle, { paddingVertical: spacing.xs }]}>
              {ringDays.map((d, i) => {
                const n = d.goals.length;
                const logged = d.goals.filter((g) => g.complete).map((g) => DOMAIN[g.domain].name);
                const summary = n === 0 ? "Goals not set yet" : logged.length === 0 ? "Nothing logged yet" : logged.join(" · ");
                return (
                  <View key={d.date} style={[styles.navRow, i < ringDays.length - 1 && styles.divider]} testID={`history-${d.date}`}>
                    {n === 0 ? <View style={styles.notSet} /> : <GoalRings goals={d.goals} size={44} bold />}
                    <View style={{ flex: 1 }}>
                      <AppText variant="subtitle" style={{ fontSize: 15 }}>
                        {dayLabel(d.date, i === 0)}
                      </AppText>
                      <AppText variant="caption">{summary}</AppText>
                    </View>
                  </View>
                );
              })}
            </View>
          )}
        </View>
      )}

      {/* Account */}
      <View style={{ gap: spacing.md, marginTop: spacing.sm }}>
        <AppText variant="title" style={{ fontSize: 17 }}>
          You
        </AppText>
        <View style={[cardStyle, { paddingVertical: spacing.xs }]}>
          <Pressable onPress={() => router.push("/focus-areas")} style={[styles.navRow, styles.divider]} testID="profile-focus-areas-link">
            <IconCircle icon="target" color={domain.food.text} tint={domain.food.tint} size={36} iconSize={16} />
            <View style={{ flex: 1 }}>
              <AppText variant="subtitle" style={{ fontSize: 15 }}>
                Focus area
              </AppText>
              <AppText variant="caption">
                {user?.focus_area ? `Working on ${FOCUS_AREA_LABEL[user.focus_area] ?? "your focus area"}` : "Chosen after your first check-in"}
              </AppText>
            </View>
            <Feather name="chevron-right" size={18} color={colors.muted} />
          </Pressable>
          <Pressable onPress={() => router.push("/goals")} style={[styles.navRow, styles.divider]} testID="profile-goals-link">
            <IconCircle icon="target" color={domain.move.text} tint={domain.move.tint} size={36} iconSize={16} />
            <View style={{ flex: 1 }}>
              <AppText variant="subtitle" style={{ fontSize: 15 }}>
                Daily goals
              </AppText>
              <AppText variant="caption">Your Eat, Move and Sleep rings</AppText>
            </View>
            <Feather name="chevron-right" size={18} color={colors.muted} />
          </Pressable>
          <Pressable onPress={() => router.push("/avatar")} style={[styles.navRow, styles.divider]} testID="profile-avatar-link">
            <Avatar size={36} showProps={false} />
            <View style={{ flex: 1 }}>
              <AppText variant="subtitle" style={{ fontSize: 15 }}>
                Your avatar
              </AppText>
              <AppText variant="caption">Hair, face, glasses, outfit and colours</AppText>
            </View>
            <Feather name="chevron-right" size={18} color={colors.muted} />
          </Pressable>
          <Pressable onPress={() => router.push("/settings")} style={[styles.navRow, styles.divider]} testID="profile-settings-link">
            <IconCircle icon="sliders" color={colors.onSurface} tint={colors.surfaceTertiary} size={36} iconSize={16} />
            <View style={{ flex: 1 }}>
              <AppText variant="subtitle" style={{ fontSize: 15 }}>
                Settings
              </AppText>
              <AppText variant="caption">Profile, AI key, wearable, reminders</AppText>
            </View>
            <Feather name="chevron-right" size={18} color={colors.muted} />
          </Pressable>
          <View style={styles.navRow}>
            <IconCircle icon="shield" color={colors.brandPrimary} tint={colors.brandTertiary} size={36} iconSize={16} />
            <AppText variant="caption" style={{ flex: 1, color: colors.onSurfaceSecondary }}>
              LLHS never tracks weight, calories or appearance. No rankings, no surprise rewards.
            </AppText>
          </View>
        </View>
        <AppText variant="caption" style={{ textAlign: "center" }}>
          Signed in as {user?.email}
        </AppText>
        <Button title="Sign out" variant="secondary" onPress={onSignOut} testID="profile-signout" />
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  c: { flex: 1, backgroundColor: colors.surface },
  center: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.surface },
  bubble: {
    alignSelf: "flex-end", maxWidth: "82%", backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border,
    borderRadius: radius.lg, paddingHorizontal: spacing.md, paddingVertical: 10, marginRight: 4, marginTop: 4,
  },
  bubbleTail: {
    position: "absolute", top: -6, right: 26, width: 11, height: 11, backgroundColor: colors.surfaceSecondary,
    borderLeftWidth: 1, borderTopWidth: 1, borderColor: colors.border, transform: [{ rotate: "45deg" }],
  },
  statCard: { flexDirection: "row", gap: 8, padding: 8 },
  statTile: { flex: 1, gap: 6, borderRadius: radius.md, paddingVertical: 12, paddingHorizontal: 10 },
  levelCard: { flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.lg },
  mountainTile: { width: 72, height: 60, borderRadius: radius.md, backgroundColor: domain.rest.tint, alignItems: "center", justifyContent: "flex-end", paddingBottom: 4 },
  flag: { position: "absolute", top: 2, left: 33 },
  levelChip: { backgroundColor: colors.brandTertiary, borderRadius: radius.pill, paddingHorizontal: 10, paddingVertical: 5 },
  track: { height: 10, borderRadius: 5, backgroundColor: colors.surfaceTertiary, overflow: "hidden" },
  fill: { height: 10, borderRadius: 5, backgroundColor: colors.brandPrimary },
  segment: { flexDirection: "row", gap: 6, backgroundColor: colors.surfaceTertiary, borderRadius: radius.md, padding: 4 },
  segBtn: { flex: 1, height: 38, borderRadius: 8, alignItems: "center", justifyContent: "center" },
  segOn: { backgroundColor: colors.brandPrimary },
  badgeRow: { flexDirection: "row", paddingHorizontal: 4, paddingVertical: spacing.lg },
  badge: { flex: 1, alignItems: "center", gap: 4, paddingHorizontal: 2 },
  badgeCircle: { width: 58, height: 58, borderRadius: 29, alignItems: "center", justifyContent: "center", marginBottom: 4 },
  // Unearned: quietly greyed, no lock or "missing" styling.
  unearned: { opacity: 0.4, filter: "grayscale(1)" } as ImageStyle,
  figure: { width: 48, height: 48, borderRadius: 24, alignItems: "center", justifyContent: "center" },
  challenge: { flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.lg },
  doneChip: {
    flexDirection: "row", alignItems: "center", gap: 4, alignSelf: "flex-start", marginTop: 4,
    backgroundColor: domain.food.tint, borderRadius: radius.pill, paddingHorizontal: 10, paddingVertical: 4,
  },
  notSet: { width: 44, height: 44, borderRadius: 22, borderWidth: 1.5, borderStyle: "dashed", borderColor: colors.borderStrong },
  weekDot: { width: 8, height: 8, borderRadius: 4 },
  navRow: { flexDirection: "row", alignItems: "center", gap: spacing.md, paddingVertical: 12 },
  divider: { borderBottomWidth: 1, borderBottomColor: colors.divider },
});
