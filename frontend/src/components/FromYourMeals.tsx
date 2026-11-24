import React, { useState } from "react";
import { View, StyleSheet, Pressable } from "react-native";
import { useRouter } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { AppText, Button, Card } from "@/src/components/ui";
import { api } from "@/src/api";
import { colors, radius, spacing } from "@/src/theme";

// From your meals — the behavior side of Future Me (the digital twin).
// The server reads the student's own meal logs, notices the foods that
// keep coming back, and matches one or two swaps from the reviewed swap
// table to their focus area and their setup (kitchen, meal plan,
// allergies, dislikes). Each swap points at where it is on today's real
// Aggie Dining menu. Nothing here is a score or an amount: the only
// numbers are counts of meals the student logged themselves.

export type MenuMatch = { hall: "sbisa" | "commons"; hall_label: string; period: string; station: string; item_id: string; item_name: string };
export type Suggestion = {
  id: string;
  kind: "habit_swap" | "focus_add";
  habit: { food_id: string; label: string; times: number; days: number; top_slot: string } | null;
  evidence: string | null;
  swap_label: string;
  text: string;
  where: string;
  on_menu_today: MenuMatch[];
  status: "trying" | null;
  // Only the AI engine adds this: one short sentence, guardrail-checked server-side.
  why?: string | null;
};
export type FromYourMealsData = {
  status: "learning" | "ready";
  days_logged: number;
  note: string | null;
  habits: { food_id: string; label: string; times: number; top_slot: string }[];
  suggestions: Suggestion[];
  menu_source: "live" | "sample" | "none";
  // Which engine produced this block ("rules" or "llm"); set by the server's
  // TWIN_ENGINE and never a choice the student makes.
  engine?: "rules" | "llm";
};

const SLOT_WORD: Record<string, string> = { breakfast: "breakfast", lunch: "lunch", dinner: "dinner", snack: "a snack" };

export function FromYourMeals({
  data,
  onChange,
  onAsk,
  disabled,
}: {
  data: FromYourMealsData | null;
  onChange: (next: FromYourMealsData) => void;
  // Hands a question to the Future Me conversation ("Tell me more about…").
  onAsk?: (text: string) => void;
  disabled?: boolean;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  if (!data) return null;

  const setStatus = async (s: Suggestion, status: "trying" | "tried" | "dismissed") => {
    setBusy(s.id);
    try {
      const res: any = await api.setSwapStatus(s.id, status);
      if (res?.from_your_meals) onChange(res.from_your_meals);
    } catch {
      // Leave the card as it was; the student can tap again.
    } finally {
      setBusy(null);
    }
  };

  const findIt = (m: MenuMatch) =>
    router.push({ pathname: "/build-meal", params: { hall: m.hall, period: m.period, add: m.item_id, tab: "build" } });

  return (
    <Card style={styles.card} testID="from-your-meals">
      <View style={styles.head}>
        <Feather name="repeat" size={15} color={colors.brandPrimary} />
        <AppText variant="label" color={colors.brandPrimary} style={{ fontSize: 13 }}>
          From your meals
        </AppText>
      </View>

      {data.note && (
        <AppText variant="body" style={{ fontSize: 14 }} testID="from-your-meals-note">
          {data.note}
        </AppText>
      )}

      {data.suggestions.map((s) => {
        const first = s.on_menu_today[0];
        return (
          <View key={s.id} style={styles.swap} testID={`swap-${s.id}`}>
            <AppText variant="caption" style={{ fontSize: 12 }}>
              {s.evidence ?? "An easy add for your focus area"}
            </AppText>
            <AppText variant="subtitle" style={{ fontSize: 16 }}>
              {s.swap_label}
            </AppText>
            <AppText variant="body" style={{ fontSize: 14 }}>
              {s.text}
            </AppText>
            {!!s.why && (
              <AppText variant="body" style={{ fontSize: 14, fontStyle: "italic" }} testID={`swap-why-${s.id}`}>
                {s.why}
              </AppText>
            )}
            <View style={styles.where}>
              <Feather name={first ? "map-pin" : "home"} size={13} color={colors.muted} />
              <AppText variant="caption" style={{ flex: 1, fontSize: 12 }}>
                {first ? `${first.item_name} · ${first.hall_label} ${SLOT_WORD[first.period] ?? first.period} (${first.station})` : s.where}
              </AppText>
            </View>
            {first && (
              <Pressable onPress={() => findIt(first)} style={styles.find} testID={`swap-find-${s.id}`} disabled={disabled}>
                <Feather name="compass" size={14} color={colors.brandPrimary} />
                <AppText variant="label" color={colors.brandPrimary} style={{ fontSize: 13 }}>
                  Find it at {first.hall_label}
                </AppText>
              </Pressable>
            )}
            {s.status === "trying" ? (
              <View style={styles.row}>
                <AppText variant="caption" color={colors.success} style={{ flex: 1 }}>
                  You&apos;re trying this one
                </AppText>
                <Button title="I tried it" variant="secondary" onPress={() => setStatus(s, "tried")} loading={busy === s.id} disabled={disabled} testID={`swap-tried-${s.id}`} />
                <Button title="Not for me" variant="ghost" onPress={() => setStatus(s, "dismissed")} disabled={disabled || busy === s.id} testID={`swap-dismiss-${s.id}`} />
              </View>
            ) : (
              <View style={styles.row}>
                <Button title="I'll try it" onPress={() => setStatus(s, "trying")} loading={busy === s.id} disabled={disabled} style={{ flex: 1 }} testID={`swap-try-${s.id}`} />
                <Button title="Not for me" variant="secondary" onPress={() => setStatus(s, "dismissed")} disabled={disabled || busy === s.id} style={{ flex: 1 }} testID={`swap-dismiss-${s.id}`} />
              </View>
            )}
            {onAsk && (
              <Pressable onPress={() => onAsk(`Tell me more about this swap: ${s.swap_label.toLowerCase()}`)} style={styles.ask} disabled={disabled} testID={`swap-ask-${s.id}`}>
                <Feather name="message-circle" size={13} color={colors.muted} />
                <AppText variant="caption" style={{ fontSize: 12 }}>
                  Ask Future Me about it
                </AppText>
              </Pressable>
            )}
          </View>
        );
      })}

      {data.status === "ready" && data.habits.length > 0 && (
        <AppText variant="caption" style={{ fontSize: 11 }} testID="from-your-meals-habits">
          Noticed in your logs: {data.habits.map((h) => `${h.label} (${h.times} ${h.times === 1 ? "meal" : "meals"})`).join(", ")}. Counts of what you logged, nothing more.
        </AppText>
      )}
    </Card>
  );
}

const styles = StyleSheet.create({
  card: { gap: spacing.md, padding: spacing.lg },
  head: { flexDirection: "row", alignItems: "center", gap: 6 },
  swap: { gap: 6, paddingTop: spacing.sm, borderTopWidth: 1, borderTopColor: colors.divider },
  where: { flexDirection: "row", alignItems: "center", gap: 6, paddingTop: 2 },
  find: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    alignSelf: "flex-start",
    paddingHorizontal: spacing.md,
    paddingVertical: 8,
    borderRadius: radius.lg,
    backgroundColor: colors.brandTertiary,
  },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingTop: 4 },
  ask: { flexDirection: "row", alignItems: "center", gap: 5, paddingTop: 2 },
});
