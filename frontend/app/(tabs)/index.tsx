import React, { useCallback, useRef, useState } from "react";
import { View, StyleSheet, ScrollView, Pressable, RefreshControl, ActivityIndicator } from "react-native";
import { useRouter, useFocusEffect } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Feather } from "@expo/vector-icons";
import { BottomSheetModal } from "@gorhom/bottom-sheet";
import { AppText, Button, Disclaimer } from "@/src/components/ui";
import { Avatar, IconCircle, SectionTitle, PointsPill, cardStyle } from "@/src/components/llhs";
import { SafetyCheckinSheet, Checkin } from "@/src/components/SafetyCheckin";
import { api, Program } from "@/src/api";
import { useAuth } from "@/src/auth";
import { colors, domain, spacing, fonts, radius } from "@/src/theme";
import { FOCUS_AREA_ACTION, FOCUS_AREA_LABEL, mealMatchesArea } from "@/src/food";
import { greeting, isToday } from "@/src/week";
import { DailyRings } from "@/src/components/DailyRings";
import { RecallCard } from "@/src/components/RecallCard";
import { DOMAIN, GoalSnapshot, suggestedFoodCategory } from "@/src/daily-goals";
import { STUDY_TZ } from "@/src/study-time";
import { futureMeMessage } from "@/src/future-me";
import { publishMood } from "@/src/avatar";
import { WeekCard } from "@/src/components/WeekCard";
import { pickCurrentWeek, type WeeklyWorkflow } from "@/src/weekly-workflow";

// Today — the participant's daily dashboard (study team feedback, Oct 2026):
// a personal Future Me message first, then their focus area (with Build a
// Meal), this week's program step, one combined weekly progress section,
// and entry points to Wings and the weekly story. Food, Move and Sleep stay
// separate and are shown as effort, never a combined score or HEI number.
const FOCUS_MEAL_BONUS = 10; // server.FOCUS_MEAL_BONUS
const MEAL_POINTS = 10; // server.MEAL_POINTS

export default function Today() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user } = useAuth();
  const [data, setData] = useState<any>({});
  const [checkin, setCheckin] = useState<Checkin>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<"none" | "partial" | "all">("none");
  const [refreshing, setRefreshing] = useState(false);
  const sheetRef = useRef<BottomSheetModal>(null);

  const load = useCallback(async () => {
    const calls = {
      domains: api.getDomains(),
      path: api.getPath(),
      gam: api.getGamification(),
      meals: api.getMeals(),
      acts: api.getActivities(),
      sleeps: api.getSleeps(),
      program: api.getProgram(),
      weekly: api.getWeeklyWorkflow(),
      plans: api.getPlans(),
      rings: api.getDailyGoals(),
      recall: api.getRecall(),
      // Lightweight Wing summary — group totals only, used by the
      // "Your Wing this week" card below. Fails open: if the student
      // isn't in a Wing or the request fails, the card simply hides.
      wing: api.getMyWingSummary(),
    };
    const keys = Object.keys(calls) as (keyof typeof calls)[];
    const results = await Promise.allSettled(Object.values(calls));
    setData((prev: any) => {
      const next = { ...prev };
      results.forEach((r, i) => {
        if (r.status === "fulfilled") next[keys[i]] = r.value;
      });
      return next;
    });
    const rings = results[keys.indexOf("rings")];
    if (rings.status === "fulfilled") publishMood((rings.value as GoalSnapshot).mood);
    const failed = results.filter((r) => r.status === "rejected").length;
    setLoadError(failed === 0 ? "none" : failed === results.length ? "all" : "partial");
    setLoading(false);
    // The safety check-in is background-only and never counts as an error.
    api
      .getCheckin()
      .then((ci: any) => {
        if (ci?.checkin) {
          setCheckin(ci.checkin);
          setTimeout(() => sheetRef.current?.present(), 400);
        }
      })
      .catch(() => {});
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  const onRefresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  // One tap to start all three rings with gentle defaults (editable later).
  const [settingUp, setSettingUp] = useState(false);
  const applySuggestedGoals = async () => {
    setSettingUp(true);
    try {
      await api.setDailyGoal("food", { target: DOMAIN.food.defaultTarget, category: suggestedFoodCategory(user?.focus_areas) });
      await api.setDailyGoal("move", { target: DOMAIN.move.defaultTarget });
      await api.setDailyGoal("rest", { target: DOMAIN.rest.defaultTarget });
    } catch {
      // Whatever saved still shows; the setup card stays for anything that didn't.
    }
    await load();
    setSettingUp(false);
  };

  const ackCheckin = async () => {
    if (checkin) await api.ackCheckin(checkin.id).catch(() => {});
    sheetRef.current?.dismiss();
    setCheckin(null);
  };

  if (loading) {
    return (
      <View style={styles.center} testID="hq-loading">
        <ActivityIndicator color={colors.brandPrimary} size="large" />
        <AppText variant="caption" style={{ marginTop: spacing.md }}>
          Getting your day ready…
        </AppText>
      </View>
    );
  }

  if (loadError === "all" && !data.domains && !data.path) {
    return (
      <View style={[styles.center, { paddingHorizontal: spacing.xl }]} testID="hq-error">
        <Feather name="cloud-off" size={28} color={colors.muted} />
        <AppText variant="subtitle" style={{ marginTop: spacing.md, textAlign: "center" }}>
          We couldn&apos;t load your day
        </AppText>
        <AppText variant="caption" style={{ marginTop: spacing.sm, textAlign: "center" }}>
          Check your connection and try again.
        </AppText>
        <Button title="Try again" onPress={onRefresh} loading={refreshing} style={{ marginTop: spacing.xl, paddingHorizontal: spacing["2xl"] }} testID="hq-retry" />
      </View>
    );
  }

  const { domains, path, gam, meals = [] } = data;
  const program: Program | undefined = data.program;
  const weekly: WeeklyWorkflow | undefined = data.weekly;
  const weeklyView = pickCurrentWeek(weekly ?? null);
  const firstName = user?.name?.split(" ")[0] || "friend";
  const points = gam?.points ?? 0;
  const streak = gam?.streak ?? 0;
  const isNewUser = points === 0 && streak === 0 && !(gam?.badges?.length);

  // ---- Focus area (one of the eight) and today's focus task ----
  const area = user?.focus_area ?? null;
  const areaLabel = area ? FOCUS_AREA_LABEL[area] : null;
  const goal = user?.focus_goal?.goal ?? null;
  const action = area ? FOCUS_AREA_ACTION[area] : null;
  const mealsToday = meals.filter((m: any) => isToday(m.created_at) && !m.skipped);
  // Done once a meal today includes the area's food (areas about eating less: any logged meal).
  const focusDone = !!area && mealsToday.some((m: any) => mealMatchesArea(m, area));
  const hasResults = !!domains?.food?.has_assessment;

  // ---- Future Me: personal, tied to the goal, and points at one action ----
  const futureMe = futureMeMessage({ area, goal, hasResults, isNewUser, streak });
  const futureMeAsk = area ? "Help me plan one meal today for my goal" : "What's one thing I could work on this week?";

  // ---- This week's program step ----
  const next = program?.next_step ?? null;
  const unit = program?.units.find((u) => u.week === program.current_week);

  // Weekly day counts (Eat/Move/Sleep) now live on the daily-goals snapshot
  // (same helper feeds Future Me) — DailyRings reads them from `snapshot.week`.
  const pathWeeks: any[] = path?.weeks ?? [];

  return (
    <View style={styles.c} testID="health-hq-screen">
      <ScrollView
        contentContainerStyle={{ paddingTop: insets.top + spacing.md, paddingBottom: spacing["3xl"], paddingHorizontal: spacing.xl, gap: spacing.xl }}
        showsVerticalScrollIndicator={false}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.brandPrimary} />}
      >
        {/* Header */}
        <View style={{ gap: 6 }}>
          <View style={styles.header}>
            <AppText variant="caption" style={{ flex: 1, fontFamily: fonts.semibold, fontSize: 11, letterSpacing: 1.2 }}>
              {new Date().toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric", timeZone: STUDY_TZ }).toUpperCase()}
            </AppText>
            <Pressable style={styles.pointsChip} onPress={() => router.push("/(tabs)/profile")} testID="hq-points" accessibilityLabel={`Your progress: ${points} points`}>
              <Feather name="star" size={15} color={colors.warm} />
              <AppText variant="label" color={colors.onWarm} style={{ fontSize: 14 }}>
                {points}
              </AppText>
            </Pressable>
            <Pressable onPress={() => router.push("/(tabs)/profile")} accessibilityLabel="Your progress and profile" hitSlop={6}>
              <Avatar size={40} />
            </Pressable>
          </View>
          <AppText variant="display" style={{ fontSize: 26, lineHeight: 32 }}>
            {isNewUser ? `Welcome, ${firstName}` : `${greeting()}, ${firstName}`}
          </AppText>
        </View>

        {loadError === "partial" && (
          <Pressable onPress={onRefresh} style={styles.errorBanner} testID="hq-partial-error">
            <Feather name="alert-circle" size={14} color={colors.onWarm} />
            <AppText variant="caption" color={colors.onWarm} style={{ flex: 1 }}>
              Some of today couldn&apos;t load. Tap to retry.
            </AppText>
            <Feather name="refresh-cw" size={14} color={colors.onWarm} />
          </Pressable>
        )}

        {/* Future Me — personal, prominent, one concrete action */}
        <View style={styles.futureMe} testID="today-future-me">
          <View style={{ flexDirection: "row", gap: spacing.md, alignItems: "flex-start" }}>
            <Avatar size={64} />
            <View style={{ flex: 1, gap: 6 }}>
              <AppText variant="label" color={colors.brandPrimary} style={{ fontSize: 11, letterSpacing: 1.2 }}>
                FUTURE ME
              </AppText>
              <AppText variant="body" style={{ fontFamily: fonts.medium, fontSize: 17, lineHeight: 24 }} testID="today-future-me-text">
                {futureMe}
              </AppText>
            </View>
          </View>
          <Button
            title="Talk it through with Future Me"
            variant="secondary"
            onPress={() => router.push({ pathname: "/(tabs)/future-me", params: { q: futureMeAsk } })}
            testID="today-future-me-chat"
          />
        </View>

        {/* ASA24 food recall: due dates, link out, "I finished", new results */}
        <RecallCard info={data.recall ?? null} onChange={load} />

        {/* Your focus — the dietary work, high on the page */}
        <View style={[cardStyle, { gap: spacing.md }]} testID="today-focus">
          {area ? (
            <>
              <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.md }}>
                <IconCircle icon="target" color={domain.food.text} tint={domain.food.tint} size={44} iconSize={20} />
                <View style={{ flex: 1 }}>
                  <AppText variant="label" color={colors.muted} style={{ fontSize: 11, letterSpacing: 1 }}>
                    YOUR FOCUS
                  </AppText>
                  <AppText variant="subtitle" style={{ fontSize: 18 }}>
                    {areaLabel}
                  </AppText>
                  {goal ? <AppText variant="caption">Goal: {goal}</AppText> : null}
                </View>
              </View>
              <Pressable onPress={() => router.push("/log-meal")} style={styles.taskRow} testID="today-focus-task" accessibilityRole="button">
                <View style={[styles.checkBox, focusDone && styles.checkBoxDone]}>{focusDone && <Feather name="check" size={14} color="#FFFFFF" />}</View>
                <View style={{ flex: 1 }}>
                  <AppText variant="subtitle" style={{ fontSize: 15 }} color={focusDone ? colors.muted : colors.onSurface}>
                    {focusDone ? "Done today. Nice work." : `Today: ${action} at one meal`}
                  </AppText>
                  <AppText variant="caption">{focusDone ? "Logged a meal with your focus food" : "Log it to earn the focus bonus"}</AppText>
                </View>
                {!focusDone && <PointsPill points={MEAL_POINTS + FOCUS_MEAL_BONUS} />}
              </Pressable>
            </>
          ) : (
            <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.md }}>
              <IconCircle icon="target" color={domain.food.text} tint={domain.food.tint} size={44} iconSize={20} />
              <View style={{ flex: 1 }}>
                <AppText variant="subtitle" style={{ fontSize: 16 }}>
                  {hasResults ? "Choose your focus area" : "Your focus area comes after your first food recall"}
                </AppText>
                <AppText variant="caption">{hasResults ? "One area to work on, plus a goal you set." : "Until then, practice building meals below."}</AppText>
              </View>
              {hasResults && (
                <Button title="Choose" onPress={() => router.push("/focus-areas")} style={{ paddingHorizontal: spacing.lg }} testID="today-choose-focus" />
              )}
            </View>
          )}
          <View style={{ flexDirection: "row", gap: spacing.sm }}>
            <Pressable onPress={() => router.push("/build-meal")} style={styles.miniCard} testID="hq-build-meal">
              <Feather name="grid" size={16} color={domain.food.text} />
              <View style={{ flex: 1 }}>
                <AppText variant="label" style={{ fontSize: 13 }}>
                  Build a meal
                </AppText>
                <AppText variant="caption" style={{ fontSize: 11 }}>
                  From today&apos;s dining menu
                </AppText>
              </View>
            </Pressable>
            <Pressable onPress={() => router.push({ pathname: "/game/[id]", params: { id: "g3" } })} style={styles.miniCard} testID="hq-cook-meal">
              <Feather name="sliders" size={16} color={domain.food.text} />
              <View style={{ flex: 1 }}>
                <AppText variant="label" style={{ fontSize: 13 }}>
                  Cook it yourself
                </AppText>
                <AppText variant="caption" style={{ fontSize: 11 }}>
                  Filter by time, cost, kitchen
                </AppText>
              </View>
            </Pressable>
          </View>
        </View>

        {/* This week's program step. When the content-driven weekly workflow
            is enabled for this student (WEEK{N}_WORKFLOW_MODE), the new
            WeekCard replaces the program.py card. Otherwise the existing
            card renders unchanged so pilots never see a half-finished flow. */}
        {weeklyView ? (
          <WeekCard
            view={weeklyView}
            focus={{
              area: user?.focus_area ?? null,
              goal: user?.focus_goal?.goal ?? null,
              plan: user?.focus_goal?.plan ?? null,
            }}
            plans={data.plans?.plans ?? undefined}
            testID="today-week-card"
          />
        ) : unit && (
          <Pressable
            onPress={() =>
              next?.route && next.key !== "do_it" && next.key !== "reflect"
                ? router.push(next.params ? ({ pathname: next.route, params: next.params } as any) : (next.route as any))
                : router.push("/(tabs)/learn")
            }
            style={[cardStyle, { gap: spacing.sm }]}
            testID="today-unit"
          >
            <AppText variant="label" color={colors.brandPrimary} style={{ fontSize: 12, letterSpacing: 0.6 }}>
              WEEK {unit.week} OF {program!.weeks} · {unit.title.toUpperCase()}
            </AppText>
            {next ? (
              <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.md }}>
                <IconCircle
                  icon={next.key === "watch" ? "play-circle" : next.key === "practice" ? "edit-3" : next.key === "do_it" ? "check-square" : "message-square"}
                  color={colors.brandPrimary}
                  tint={colors.surfaceTertiary}
                  size={44}
                  iconSize={20}
                />
                <View style={{ flex: 1 }}>
                  <AppText variant="caption">
                    {next.label}
                    {next.week !== unit.week ? ` · from week ${next.week}` : ""}
                  </AppText>
                  <AppText variant="subtitle" style={{ fontSize: 15 }} numberOfLines={2}>
                    {next.title}
                  </AppText>
                </View>
                <PointsPill points={next.points} />
              </View>
            ) : (
              <AppText variant="body" style={{ fontSize: 14 }}>
                You&apos;re done with this week. Nice work. Next week opens soon.
              </AppText>
            )}
          </Pressable>
        )}

        {/* One weekly progress section: today's rings + the week strip + per-activity days logged */}
        <View>
          <SectionTitle title="This week" right={<AppText variant="caption">Tap a day to see its rings</AppText>} />
          <DailyRings
            snapshot={data.rings ?? null}
            onEdit={() => router.push("/goals")}
            onUseSuggested={applySuggestedGoals}
            settingUp={settingUp}
          />
          {domains?.rest && domains.rest.confidence !== "medium" && (
            <Pressable onPress={() => router.push("/settings")} testID="hq-connect-wearable-hint" style={{ marginTop: spacing.sm }}>
              <AppText variant="caption" style={{ textDecorationLine: "underline" }}>
                Connect a wearable in Settings for a clearer Sleep picture.
              </AppText>
            </Pressable>
          )}
        </View>

        {/* Your Wing this week — group totals only, hides when not in a Wing. */}
        {data.wing?.wing && (
          <Pressable
            onPress={() => router.push("/(tabs)/social")}
            style={[cardStyle, { gap: spacing.sm }]}
            testID="today-wing-card"
            accessibilityRole="button"
            accessibilityLabel={`Your Wing this week: ${data.wing.wing.name}`}
          >
            <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.md }}>
              <IconCircle icon="users" color={colors.brandPrimary} tint={colors.surfaceTertiary} size={44} iconSize={20} />
              <View style={{ flex: 1 }}>
                <AppText variant="label" color={colors.brandPrimary} style={{ fontSize: 11, letterSpacing: 1 }}>
                  YOUR WING THIS WEEK
                </AppText>
                <AppText variant="subtitle" style={{ fontSize: 16 }} numberOfLines={1}>
                  {data.wing.wing.name}
                </AppText>
              </View>
              <Feather name="chevron-right" size={18} color={colors.muted} />
            </View>
            <AppText variant="body" style={{ fontSize: 14 }}>
              Our Wing: {data.wing.wing.progress.current} / {data.wing.wing.progress.target}{" "}
              {data.wing.wing.challenge?.unit ?? "steps"}
              {data.wing.wing.cheers_total ? ` · ${data.wing.wing.cheers_total} cheer${data.wing.wing.cheers_total === 1 ? "" : "s"}` : ""}
            </AppText>
            {data.wing.wing.challenge && (
              <AppText variant="caption">
                Challenge: {data.wing.wing.challenge.title} · {data.wing.wing.challenge.current} / {data.wing.wing.challenge.target} {data.wing.wing.challenge.unit}
              </AppText>
            )}
          </Pressable>
        )}

        {/* Social and the weekly look back */}
        <View style={{ flexDirection: "row", gap: 10 }}>
          <Pressable onPress={() => router.push("/(tabs)/social")} style={[cardStyle, styles.moreCard]} testID="hq-wings">
            <IconCircle icon="users" color={colors.brandPrimary} tint={colors.surfaceTertiary} size={36} iconSize={17} />
            <AppText variant="subtitle" style={{ fontSize: 15 }}>
              Wings
            </AppText>
            <AppText variant="caption">Team up with friends on a shared goal</AppText>
          </Pressable>
          <Pressable onPress={() => router.push("/weekly-story")} style={[cardStyle, styles.moreCard]} testID="hq-weekly-story">
            <IconCircle icon="book-open" color={colors.brandPrimary} tint={colors.surfaceTertiary} size={36} iconSize={17} />
            <AppText variant="subtitle" style={{ fontSize: 15 }}>
              Your week
            </AppText>
            <AppText variant="caption">A calm look back, no scores</AppText>
          </Pressable>
        </View>

        {/* My Path preview */}
        {path && (
          <Pressable onPress={() => router.push("/(tabs)/my-path")} style={cardStyle} testID="path-hero">
            <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
              <View>
                <AppText variant="label" color={colors.brandPrimary} style={{ fontSize: 12, letterSpacing: 0.6 }}>
                  MY PATH
                </AppText>
                <AppText variant="subtitle" style={{ fontSize: 18 }}>
                  Week {path.current_week} of {pathWeeks.length || 8} · {path.achieved_count} of {path.total} milestones
                </AppText>
              </View>
              <Feather name="chevron-right" size={20} color={colors.brandPrimary} />
            </View>
            <View style={styles.pathLine}>
              <View style={styles.pathTrack} />
              <View
                style={[
                  styles.pathTrack,
                  { backgroundColor: domain.food.main, width: `${pathWeeks.length > 1 ? ((path.current_week - 1) / (pathWeeks.length - 1)) * 100 : 0}%` },
                ]}
              />
              <View style={styles.pathDots}>
                {pathWeeks.map((w: any) => {
                  const here = w.week === path.current_week;
                  return (
                    <View
                      key={w.week}
                      style={[
                        styles.pathDot,
                        { backgroundColor: w.week < path.current_week ? domain.food.main : colors.borderStrong },
                        here && { width: 22, height: 22, borderRadius: 11, backgroundColor: colors.warm },
                      ]}
                    />
                  );
                })}
              </View>
            </View>
            <AppText variant="body" style={{ marginTop: spacing.md, fontSize: 14 }}>
              {path.next_checkin?.message}
            </AppText>
          </Pressable>
        )}

        <Disclaimer text="Based on what you log. Never a medical prediction or diagnosis." />
      </ScrollView>

      <SafetyCheckinSheet ref={sheetRef} checkin={checkin} onAcknowledge={ackCheckin} />
    </View>
  );
}

const styles = StyleSheet.create({
  c: { flex: 1, backgroundColor: colors.surface },
  center: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", gap: 10 },
  pointsChip: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    height: 36,
    paddingHorizontal: 12,
    borderRadius: radius.pill,
    backgroundColor: colors.warmTint,
  },
  errorBanner: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.md,
    backgroundColor: colors.warmTint,
  },
  futureMe: {
    gap: spacing.lg,
    padding: spacing.lg,
    borderRadius: radius.lg,
    backgroundColor: colors.surfaceSecondary,
    borderWidth: 1,
    borderColor: colors.border,
  },
  taskRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    padding: spacing.md,
    borderRadius: radius.md,
    backgroundColor: domain.food.tint,
  },
  checkBox: { width: 24, height: 24, borderRadius: 6, borderWidth: 2, borderColor: domain.food.main, alignItems: "center", justifyContent: "center" },
  checkBoxDone: { backgroundColor: domain.food.main },
  miniCard: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    padding: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
  },
  pathLine: { height: 28, justifyContent: "center", marginTop: spacing.md },
  pathTrack: { position: "absolute", left: 0, right: 0, height: 6, borderRadius: 3, backgroundColor: colors.surfaceTertiary },
  pathDots: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  pathDot: { width: 16, height: 16, borderRadius: 8, borderWidth: 3, borderColor: "#FFFFFF" },
  moreCard: { flex: 1, gap: spacing.sm, padding: spacing.lg },
});
