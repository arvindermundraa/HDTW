import React, { useEffect, useState } from "react";
import { View, Pressable, StyleSheet } from "react-native";
import { useRouter } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { AppText, Button } from "@/src/components/ui";
import { GoalRings } from "@/src/components/GoalRings";
import { AskCoachButton, cardStyle } from "@/src/components/llhs";
import { COACH_CATEGORY_QUESTION } from "@/src/food";
import { DOMAIN, DOMAINS, Domain, FOOD_OPTIONS, GoalSnapshot } from "@/src/daily-goals";
import { clockMinutes, ringNote } from "@/src/rings";
import { STUDY_TZ, studyWeekdayIndex } from "@/src/study-time";
import { useAuth } from "@/src/auth";
import { colors, spacing } from "@/src/theme";

const WEEKDAY = ["S", "M", "T", "W", "T", "F", "S"];
const WEEKDAY_LONG = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

// Weekday for a YYYY-MM-DD day key, in the study TZ — not the phone's local
// zone — so the Monday initial stays "M" even if the phone is in Tokyo.
function dayIndex(isoDate: string): number {
  return studyWeekdayIndex(isoDate);
}

/** Minutes since midnight now, in the study time zone. */
function studyNowMinutes(): number {
  try {
    const parts = new Intl.DateTimeFormat("en-US", { timeZone: STUDY_TZ, hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).formatToParts(new Date());
    const get = (t: string) => Number(parts.find((p) => p.type === t)?.value ?? 0);
    return get("hour") * 60 + get("minute");
  } catch {
    const d = new Date();
    return d.getHours() * 60 + d.getMinutes();
  }
}

/** Where each ring's tap goes: the matching mode of the log screen. */
export const LOG_ROUTE: Record<Domain, { pathname: "/log-meal"; params?: { mode: string } }> = {
  food: { pathname: "/log-meal" },
  move: { pathname: "/log-meal", params: { mode: "move" } },
  rest: { pathname: "/log-meal", params: { mode: "rest" } },
};

// Which of today's rings we've already seen closed, shared across screens
// so the closing pulse plays once, when a ring goes from open to closed —
// never on first load and never again for the extra lap.
const seenClosed: Record<string, boolean> = {};

function useJustClosed(snapshot: GoalSnapshot | null): Domain[] {
  const [fresh, setFresh] = useState<Domain[]>([]);
  const today = snapshot?.days?.[snapshot.days.length - 1];
  const key = today ? today.goals.map((g) => `${g.domain}:${g.complete}`).join("|") : "";
  useEffect(() => {
    if (!today) return;
    const now: Domain[] = [];
    for (const g of today.goals) {
      const k = `${today.date}:${g.domain}`;
      if (g.complete && seenClosed[k] === false) now.push(g.domain);
      seenClosed[k] = g.complete;
    }
    if (now.length) {
      setFresh(now);
      const t = setTimeout(() => setFresh([]), 900);
      return () => clearTimeout(t);
    }
  }, [today?.date, key]); // eslint-disable-line react-hooks/exhaustive-deps
  return fresh;
}

/** "Logged a meal on 3 days this week" — the per-activity week recap. The
 *  verb and noun are different per ring: Eat is about logging the meal,
 *  Move about moving, Rest about logging sleep. Never a combined count. */
function perActivityLine(d: Domain, n: number): string {
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

/**
 * One "This week" section: today's Eat/Move/Sleep rings + the rolling 7-day
 * strip + per-activity weekly counts. Tapping a day in the strip swaps the
 * big rings and the per-ring rows to that day; the rings pulse on close only
 * for today, and tap-to-log on the big rings always logs for today.
 *
 * Weekly counts (`eat_days` / `move_days` / `rest_days`) come straight from
 * the daily-goals snapshot — the same helper feeds `/api/future-me`, so
 * Today, Future Me and Progress always report the same numbers.
 */
export function DailyRings({
  snapshot,
  onEdit,
  onUseSuggested,
  settingUp,
  showWeek = true,
  testID,
}: {
  snapshot: GoalSnapshot | null;
  onEdit: () => void;
  onUseSuggested: () => void;
  settingUp?: boolean;
  showWeek?: boolean;
  testID?: string;
}) {
  const router = useRouter();
  const { user } = useAuth();
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const todayEntry = snapshot?.days?.[snapshot.days.length - 1];
  const justClosed = useJustClosed(snapshot);

  // If the snapshot refreshes to a new "today", drop any stale past-day
  // selection so Today reopens on today.
  useEffect(() => {
    if (!todayEntry) return;
    if (selectedDate && !snapshot?.days.some((d) => d.date === selectedDate)) {
      setSelectedDate(null);
    }
  }, [snapshot, todayEntry, selectedDate]);

  if (!snapshot || !todayEntry || todayEntry.goals.length === 0) {
    return (
      <View style={[cardStyle, { gap: spacing.lg }]} testID={testID ?? "rings-setup"}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.lg }}>
          <GoalRings goals={[]} size={96} />
          <View style={{ flex: 1, gap: 4 }}>
            <AppText variant="subtitle" style={{ fontSize: 18 }}>
              Close your rings each day
            </AppText>
            <AppText variant="caption" style={{ color: colors.onSurfaceSecondary }}>
              Eat, Move and Sleep each get a small daily target. Your logs fill the rings. Start with suggested goals, or pick your own.
            </AppText>
          </View>
        </View>
        <View style={{ flexDirection: "row", gap: spacing.sm }}>
          <Button title="Start" onPress={onUseSuggested} loading={settingUp} style={{ flex: 1 }} testID="rings-use-suggested" />
          <Button title="Customize" variant="secondary" onPress={onEdit} style={{ flex: 1 }} testID="rings-customize" />
        </View>
      </View>
    );
  }

  const activeDate = selectedDate ?? todayEntry.date;
  const activeDay = snapshot.days.find((d) => d.date === activeDate) ?? todayEntry;
  const activeGoals = activeDay.goals;
  const viewingToday = activeDate === todayEntry.date;
  // Tap-to-log always creates an entry for *today* (we never backfill past
  // days from the ring). On a past day the "+" is hidden to avoid implying
  // otherwise, and the big rings stop responding to taps.
  const openLog = (d: Domain) => router.push(LOG_ROUTE[d]);
  const ctx = {
    nowMinutes: studyNowMinutes(),
    bedtime: clockMinutes(user?.sleep_schedule?.bedtime, 23 * 60),
    wake: clockMinutes(user?.sleep_schedule?.wake, 7 * 60),
  };
  const week = snapshot.week;
  const centerLabel = viewingToday
    ? "Today"
    : WEEKDAY_LONG[dayIndex(activeDate)].slice(0, 3);

  return (
    <View style={[cardStyle, { gap: spacing.lg }]} testID={testID ?? "rings-card"}>
      <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.lg }}>
        <GoalRings
          goals={activeGoals}
          size={148}
          onPressRing={viewingToday ? openLog : undefined}
          celebrate={viewingToday ? justClosed : []}
        >
          <AppText variant="label" style={{ fontSize: 14 }}>
            {centerLabel}
          </AppText>
        </GoalRings>
        <View style={{ flex: 1, gap: 10 }}>
          {DOMAINS.map((d) => {
            const g = activeGoals.find((x) => x.domain === d);
            const food = FOOD_OPTIONS.find((o) => o.id === g?.category)?.label.toLowerCase();
            const n = g ? ringNote(d, g.value, g.target, { ...ctx, food }) : null;
            const Row = viewingToday ? Pressable : View;
            const rowProps = viewingToday
              ? {
                  onPress: () => openLog(d),
                  accessibilityRole: "button" as const,
                  accessibilityLabel: `Log ${DOMAIN[d].name}`,
                }
              : {};
            return (
              <Row
                key={d}
                style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}
                testID={`ring-row-${d}`}
                {...rowProps}
              >
                <View style={[styles.dot, { backgroundColor: g ? DOMAIN[d].color : DOMAIN[d].track }]} />
                <View style={{ flex: 1 }}>
                  <AppText variant="label" style={{ fontSize: 14 }}>
                    {DOMAIN[d].name}
                  </AppText>
                  <AppText variant="caption" style={{ fontSize: 12, lineHeight: 15 }} testID={`ring-line-${d}`}>
                    {n ? n.line : "No goal"}
                  </AppText>
                  {n?.note && (
                    <AppText variant="caption" color={DOMAIN[d].text} style={{ fontSize: 11, lineHeight: 14 }}>
                      {n.note}
                    </AppText>
                  )}
                </View>
                {g?.complete ? (
                  <Feather name="check-circle" size={16} color={DOMAIN[d].text} />
                ) : viewingToday ? (
                  <Feather name="plus" size={15} color={colors.muted} />
                ) : null}
              </Row>
            );
          })}
          {viewingToday ? (
            <Pressable onPress={onEdit} hitSlop={8} testID="rings-edit">
              <AppText variant="label" color={colors.brandPrimary} style={{ fontSize: 13 }}>
                Edit goals
              </AppText>
            </Pressable>
          ) : (
            <Pressable onPress={() => setSelectedDate(null)} hitSlop={8} testID="rings-back-today">
              <AppText variant="label" color={colors.brandPrimary} style={{ fontSize: 13 }}>
                ← Back to today
              </AppText>
            </Pressable>
          )}
        </View>
      </View>
      {viewingToday && (
        <AskCoachButton
          question={COACH_CATEGORY_QUESTION[activeGoals.find((g) => g.domain === "food")?.category ?? ""] ?? "What's a balanced plate?"}
          testID="rings-ask-coach"
        />
      )}

      {showWeek && (
        <View style={{ gap: spacing.md }}>
          <View style={styles.week}>
            {snapshot.days.map((day) => {
              const isTodayCol = day.date === todayEntry.date;
              const isSelected = day.date === activeDate;
              const notSet = day.goals.length === 0;
              return (
                <Pressable
                  key={day.date}
                  onPress={() => setSelectedDate(isTodayCol ? null : day.date)}
                  style={[styles.dayCol, isTodayCol && styles.todayCol, isSelected && !isTodayCol && styles.selectedCol]}
                  accessibilityRole="button"
                  accessibilityLabel={`${WEEKDAY_LONG[dayIndex(day.date)]}${isTodayCol ? ", today" : ""}: ${notSet ? "goals not set yet" : "tap to see this day's rings"}`}
                  testID={`week-${day.date}`}
                >
                  <AppText
                    variant="label"
                    color={isTodayCol ? colors.onSurfaceInverse : isSelected ? colors.brandPrimary : colors.muted}
                    style={{ fontSize: 11 }}
                  >
                    {WEEKDAY[dayIndex(day.date)]}
                  </AppText>
                  {notSet ? (
                    <View style={styles.notSet}>
                      <AppText variant="caption" style={{ fontSize: 8, lineHeight: 10, textAlign: "center" }}>
                        not{"\n"}set
                      </AppText>
                    </View>
                  ) : (
                    <GoalRings goals={day.goals} size={32} bold />
                  )}
                </Pressable>
              );
            })}
          </View>
          <View style={styles.recap} testID="rings-week-recap">
            {week && (
              <View style={{ gap: 4 }}>
                {DOMAINS.map((d) => {
                  const n = d === "food" ? week.eat_days : d === "move" ? week.move_days : week.rest_days;
                  return (
                    <View key={d} style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                      <View style={[styles.dot, { width: 8, height: 8, backgroundColor: DOMAIN[d].color }]} />
                      <AppText variant="caption" style={{ fontSize: 12 }} testID={`days-logged-${d}`}>
                        {perActivityLine(d, n)}
                      </AppText>
                    </View>
                  );
                })}
                <AppText variant="caption" style={{ fontSize: 11, lineHeight: 14, marginTop: 2 }} testID="rings-move-week">
                  {week.move_minutes} min of movement logged this week · a steady weekly rhythm is around {week.move_reference_minutes} min
                </AppText>
              </View>
            )}
          </View>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  dot: { width: 10, height: 10, borderRadius: 5 },
  week: { flexDirection: "row", justifyContent: "space-between" },
  dayCol: { alignItems: "center", gap: 6, paddingVertical: 6, width: 42, borderRadius: 14 },
  todayCol: { backgroundColor: colors.surfaceInverse },
  selectedCol: { backgroundColor: colors.brandTertiary },
  notSet: {
    width: 32, height: 32, borderRadius: 16, borderWidth: 1.5, borderStyle: "dashed", borderColor: colors.borderStrong,
    alignItems: "center", justifyContent: "center",
  },
  recap: { gap: 6, paddingTop: spacing.md, borderTopWidth: 1, borderTopColor: colors.divider },
});
