import React, { useCallback, useState } from "react";
import { View, StyleSheet, ScrollView, Pressable, ActivityIndicator, Image } from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Feather } from "@expo/vector-icons";
import { AppText, Button } from "@/src/components/ui";
import { Avatar, cardStyle } from "@/src/components/llhs";
import { api } from "@/src/api";
import { colors, domain, fonts, radius, spacing } from "@/src/theme";
import { AREA_META, COACH_FOCUS_QUESTION, mealMatchesArea } from "@/src/food";
import { useAuth } from "@/src/auth";
import { FLUENT } from "@/src/fluent";
import { weekFlags } from "@/src/week";
import { goBack } from "@/src/navigation";

// Eat — "your eating pattern at a glance", laid out like the client mockup
// (9/10/26 deck, slide 11) in the app's mature style.
// - Everything is one of the eight focus areas (your focus, your strengths,
//   other areas), never the 13 HEI-2020 components; the API sends no scores.
// - Each bar is DAYS LOGGED THIS WEEK with that area's food (src/food.ts;
//   areas about eating less count days with any meal logged), labelled
//   "N of 7 days". It is never the HEI score.
// - Strengths carry only the direction-only national note; the focus area
//   and other areas never get a national comparison.
// - Encouraging lines are fixed per area (src/food.ts), never random.
const EAT = domain.food;

const WARM = domain.move;

type Kind = "strength" | "focus" | "room_to_grow" | "other";

function FoodTile({ images, tint }: { images: number[]; tint: string }) {
  const two = images.length > 1;
  return (
    <View style={[styles.foodTile, { backgroundColor: tint }]}>
      {images.slice(0, 2).map((src, i) => (
        <Image
          key={i}
          source={src}
          style={two ? [styles.foodPair, i === 0 ? { left: 5, top: 7 } : { right: 5, bottom: 7 }] : { width: 30, height: 30 }}
          resizeMode="contain"
          accessibilityIgnoresInvertColors
        />
      ))}
    </View>
  );
}

function DaysBar({ days, color }: { days: number; color: string }) {
  return (
    <View style={styles.track}>
      <View style={[styles.fill, { width: `${(days / 7) * 100}%`, backgroundColor: color }]} />
    </View>
  );
}

function AreaRow({ id, label, kind, meals, last }: { id: string; label: string; kind: Kind; meals: any[]; last: boolean }) {
  const meta = AREA_META[id] ?? { images: [], categories: null, cheer: "Small steps add up!" };
  const days = weekFlags(meals, (m) => mealMatchesArea(m, id)).filter(Boolean).length;
  const c = kind === "strength" ? EAT : kind === "focus" ? WARM : { tint: colors.surfaceTertiary, main: colors.borderStrong, text: colors.onSurfaceSecondary };
  return (
    <View style={[styles.row, !last && styles.rowDivider]} testID={`eat-row-${id}`}>
      <FoodTile images={meta.images} tint={c.tint} />
      <View style={{ flex: 1, gap: 5 }}>
        <AppText variant="subtitle" style={{ fontSize: 15 }} numberOfLines={2}>
          {label}
        </AppText>
        <DaysBar days={days} color={c.main} />
        <AppText variant="caption" style={{ fontSize: 12, lineHeight: 15 }} color={colors.onSurfaceSecondary}>
          {days} of 7 days
        </AppText>
        {kind === "strength" && (
          <AppText variant="caption" style={{ fontSize: 11, lineHeight: 14 }}>
            Above the national average for adults 18–25
          </AppText>
        )}
      </View>
      {kind !== "other" && (
        <View style={[styles.cheer, { backgroundColor: c.tint }]}>
          <AppText variant="caption" color={c.text} style={{ fontSize: 11, lineHeight: 14, fontFamily: fonts.medium, textAlign: "center" }}>
            {meta.cheer}
          </AppText>
        </View>
      )}
    </View>
  );
}

export default function Eat() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [food, setFood] = useState<any>(null);
  const [meals, setMeals] = useState<any[]>([]);
  const [error, setError] = useState(false);
  const [showAll, setShowAll] = useState(false);
  const [showOthers, setShowOthers] = useState(false);
  const { user } = useAuth();

  const load = useCallback(async () => {
    setError(false);
    const [f, m] = await Promise.allSettled([api.getFoodDomain(), api.getMeals()]);
    if (f.status === "fulfilled") setFood(f.value);
    else setError(true);
    if (m.status === "fulfilled") setMeals(m.value ?? []);
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  const header = (
    <View style={{ gap: spacing.md }}>
      <Pressable onPress={() => goBack(router, "/")} style={styles.back} accessibilityLabel="Back" testID="eat-back">
        <Feather name="chevron-left" size={22} color={colors.onSurface} />
      </Pressable>
      <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.md }}>
        <Avatar size={76} />
        <View style={{ flex: 1, gap: 4 }}>
          <AppText variant="display" style={{ fontSize: 21, lineHeight: 26 }}>
            Your eating pattern at a glance
          </AppText>
          <AppText variant="caption" style={{ fontSize: 13, lineHeight: 18 }}>
            A snapshot of the areas you&apos;re focusing on. Small changes add up!
          </AppText>
        </View>
      </View>
    </View>
  );

  if (!food) {
    return (
      <View style={[styles.c, { paddingTop: insets.top + spacing.md, paddingHorizontal: spacing.xl }]}>
        {header}
        <View style={{ alignItems: "center", marginTop: spacing["3xl"] }}>
          {error ? (
            <>
              <AppText variant="subtitle">We couldn&apos;t load this right now</AppText>
              <Button title="Try again" onPress={load} style={{ marginTop: spacing.lg, paddingHorizontal: spacing["2xl"] }} />
            </>
          ) : (
            <ActivityIndicator color={colors.brandPrimary} />
          )}
        </View>
      </View>
    );
  }

  // Only area ids and labels come from the API — never any score.
  const strengths: { id: string; label: string }[] = (food.strengths ?? []).map((s: any) => ({ id: s.id, label: s.label }));
  const shownStrengths = showAll ? strengths : strengths.slice(0, 3);
  // Rank-based bucket (nutrition team 2026-11-06, item 2). `room_to_grow`
  // is the bottom N areas by rank, most room first; `other_areas` is the
  // middle ground in between.
  const roomToGrow: { id: string; label: string }[] = (food.room_to_grow ?? []).map((s: any) => ({ id: s.id, label: s.label }));
  const others: { id: string; label: string }[] = (food.other_areas ?? []).map((s: any) => ({ id: s.id, label: s.label }));
  const area: { id: string; label: string; description?: string; goal?: string | null; plan?: string | null } | null =
    food.focus_area ?? null;
  const futureMeText = area
    ? `You chose ${area.label}. I'm here to help you with it.`
    : "Once you choose your focus area, I'll help you with it.";

  return (
    <View style={styles.c} testID="eat-screen">
      <ScrollView
        contentContainerStyle={{ paddingTop: insets.top + spacing.md, paddingHorizontal: spacing.xl, paddingBottom: spacing["3xl"], gap: spacing.lg }}
        showsVerticalScrollIndicator={false}
      >
        {header}

        {!food.has_assessment ? (
          <View style={cardStyle}>
            <AppText variant="subtitle">Your first check-in is coming</AppText>
            <AppText variant="body" style={{ marginTop: spacing.sm }}>
              {food.message || "Once your first dietary check-in is in, you'll see your strengths and choose what to focus on here."}
            </AppText>
          </View>
        ) : food.needs_focus_selection ? (
          <View style={cardStyle}>
            <AppText variant="subtitle">Your check-in is in</AppText>
            <AppText variant="body" style={{ marginTop: spacing.sm }}>
              Choose one area to work on and set a goal for it. You can change it after your next check-in.
            </AppText>
            <Button title="Choose your focus area" onPress={() => router.push("/focus-areas")} style={{ marginTop: spacing.lg }} testID="eat-choose-focus" />
          </View>
        ) : null}

        {/* Your strengths — pale Eat tint, direction-only note */}
        {strengths.length > 0 && (
          <View style={[styles.section, { backgroundColor: EAT.tint, borderColor: "#DCE8E1" }]} testID="eat-strengths">
            <View style={styles.sectionHead}>
              <View style={styles.headTile}>
                <Image source={FLUENT.trophy} style={{ width: 26, height: 26 }} resizeMode="contain" />
              </View>
              <View style={{ flex: 1 }}>
                <AppText variant="subtitle" style={{ fontSize: 18 }} color={EAT.text}>
                  Your strengths
                </AppText>
                <AppText variant="caption">You&apos;re doing well here!</AppText>
              </View>
            </View>
            <View style={styles.panel}>
              {shownStrengths.map((st, i) => (
                <AreaRow key={st.id} id={st.id} label={st.label} kind="strength" meals={meals} last={i === shownStrengths.length - 1} />
              ))}
              {strengths.length > 3 && (
                <Pressable onPress={() => setShowAll((v) => !v)} style={styles.showAll} testID="eat-show-all-strengths">
                  <AppText variant="label" color={EAT.text}>
                    {showAll ? "Show fewer" : `Show all ${strengths.length} strengths`}
                  </AppText>
                  <Feather name={showAll ? "chevron-up" : "chevron-down"} size={16} color={EAT.text} />
                </Pressable>
              )}
            </View>
          </View>
        )}

        {/* Your focus area — pale warm tint, no national comparison */}
        {area && (
          <View style={[styles.section, { backgroundColor: WARM.tint, borderColor: "#EFE1D8" }]} testID="eat-focus">
            <View style={styles.sectionHead}>
              <View style={styles.headTile}>
                <Image source={FLUENT.target} style={{ width: 26, height: 26 }} resizeMode="contain" />
              </View>
              <View style={{ flex: 1 }}>
                <AppText variant="subtitle" style={{ fontSize: 18 }} color={WARM.text}>
                  Your focus: {area?.label}
                </AppText>
                <AppText variant="caption">{area?.description}</AppText>
                <View style={styles.chip}>
                  <AppText variant="label" color={WARM.text} style={{ fontSize: 11 }}>
                    Progress over perfection
                  </AppText>
                </View>
              </View>
            </View>
            {area?.goal || area?.plan ? (
              <View style={[styles.panel, { padding: spacing.md, gap: 4 }]} testID="eat-focus-goal">
                {area.goal ? (
                  <AppText variant="body" style={{ fontSize: 14 }}>
                    <AppText variant="body" style={{ fontSize: 14, fontFamily: fonts.semibold }}>My goal: </AppText>
                    {area.goal}
                  </AppText>
                ) : null}
                {area.plan ? (
                  <AppText variant="body" style={{ fontSize: 14 }}>
                    <AppText variant="body" style={{ fontSize: 14, fontFamily: fonts.semibold }}>My plan: </AppText>
                    {area.plan}
                  </AppText>
                ) : null}
              </View>
            ) : null}
            <View style={styles.panel}>
              <AreaRow id={area.id} label={area.label} kind="focus" meals={meals} last />
              <Pressable onPress={() => router.push("/focus-areas")} style={styles.showAll} testID="eat-change-focus">
                <AppText variant="label" color={WARM.text}>
                  {area?.goal ? "Change focus area or goal" : "Set a goal or change focus area"}
                </AppText>
                <Feather name="chevron-right" size={16} color={WARM.text} />
              </Pressable>
            </View>
          </View>
        )}

        {/* Areas with room to grow — the rank-based bottom 3 (nutrition
            team 2026-11-06, item 2). Shown as a dedicated card so the
            team's wording ("one area to build on", "an opportunity to try
            something different") sits alongside them. Based on the days
            you reported — not a definitive statement about usual diet. */}
        {roomToGrow.length > 0 && (
          <View style={[styles.section, { backgroundColor: WARM.tint, borderColor: "#EFE1D8" }]} testID="eat-room-to-grow">
            <View style={styles.sectionHead}>
              <View style={{ flex: 1 }}>
                <AppText variant="subtitle" style={{ fontSize: 16 }} color={WARM.text}>
                  Areas with room to grow
                </AppText>
                <AppText variant="caption">
                  Based on the days you reported. One area to build on — you choose which.
                </AppText>
              </View>
            </View>
            <View style={styles.panel}>
              {roomToGrow.map((r, i) => (
                <AreaRow key={r.id} id={r.id} label={r.label} kind="room_to_grow" meals={meals} last={i === roomToGrow.length - 1} />
              ))}
            </View>
            {area ? (
              <AppText variant="caption" color={colors.onSurfaceSecondary} style={{ paddingHorizontal: spacing.sm, paddingTop: 2 }}>
                {area.label} is your current focus, so it's shown above instead of listed here.
              </AppText>
            ) : null}
          </View>
        )}

        {/* The rest of the eight areas — neither strength nor room to grow. */}
        {others.length > 0 && (
          <View style={[styles.section, { backgroundColor: colors.surfaceSecondary, borderColor: colors.border }]} testID="eat-other-areas">
            <Pressable onPress={() => setShowOthers((v) => !v)} style={styles.sectionHead} testID="eat-show-other-areas">
              <View style={{ flex: 1 }}>
                <AppText variant="subtitle" style={{ fontSize: 16 }}>
                  Other areas
                </AppText>
                <AppText variant="caption">
                  {others.length} more of the eight. You can switch your focus after your next check-in.
                </AppText>
              </View>
              <Feather name={showOthers ? "chevron-up" : "chevron-down"} size={18} color={colors.muted} />
            </Pressable>
            {showOthers && (
              <View style={styles.panel}>
                {others.map((o, i) => (
                  <AreaRow key={o.id} id={o.id} label={o.label} kind="other" meals={meals} last={i === others.length - 1} />
                ))}
              </View>
            )}
          </View>
        )}

        {/* Future Me says */}
        <View style={[cardStyle, { gap: spacing.md, padding: spacing.lg }]} testID="eat-future-me">
          <View style={{ flexDirection: "row", alignItems: "flex-start", gap: spacing.md }}>
            <Avatar size={56} />
            <View style={{ flex: 1, gap: 6 }}>
              <AppText variant="label" color={colors.muted} style={{ fontSize: 11, letterSpacing: 1.2 }}>
                FUTURE ME SAYS
              </AppText>
              <View style={styles.speech}>
                <AppText variant="body" color={colors.onSurface} style={{ fontFamily: fonts.medium, fontSize: 14, lineHeight: 20 }}>
                  {futureMeText}
                </AppText>
              </View>
            </View>
          </View>
          <View style={{ flexDirection: "row", gap: spacing.sm }}>
            <Button
              title="Ask Future Me"
              onPress={() => router.push({ pathname: "/(tabs)/future-me", params: { q: COACH_FOCUS_QUESTION[(user?.focus_areas ?? [])[0]] ?? "What's a balanced plate?" } })}
              style={{ flex: 1 }}
              testID="eat-ask-coach"
            />
          </View>
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  c: { flex: 1, backgroundColor: colors.surface },
  back: {
    width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border,
    alignItems: "center", justifyContent: "center",
  },
  section: { borderRadius: radius.lg, borderWidth: 1, padding: spacing.md, gap: spacing.md },
  sectionHead: { flexDirection: "row", alignItems: "center", gap: spacing.md, paddingHorizontal: 4, paddingTop: 4 },
  headTile: { width: 44, height: 44, borderRadius: 22, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center" },
  chip: { alignSelf: "flex-start", marginTop: 6, backgroundColor: colors.surfaceSecondary, borderRadius: radius.pill, paddingHorizontal: 10, paddingVertical: 4 },
  panel: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, paddingHorizontal: spacing.md },
  row: { flexDirection: "row", alignItems: "center", gap: 10, paddingVertical: spacing.md },
  rowDivider: { borderBottomWidth: 1, borderBottomColor: colors.divider },
  foodTile: { width: 48, height: 48, borderRadius: 24, alignItems: "center", justifyContent: "center" },
  foodPair: { position: "absolute", width: 24, height: 24 },
  track: { height: 8, borderRadius: 4, backgroundColor: colors.surfaceTertiary, overflow: "hidden" },
  fill: { height: 8, borderRadius: 4 },
  cheer: { width: 92, borderRadius: radius.md, paddingHorizontal: 8, paddingVertical: 8 },
  showAll: { flexDirection: "row", alignItems: "center", gap: 4, paddingVertical: spacing.md, borderTopWidth: 1, borderTopColor: colors.divider },
  speech: { backgroundColor: EAT.tint, borderRadius: radius.md, borderTopLeftRadius: 4, paddingHorizontal: spacing.md, paddingVertical: 10 },
});
