import React, { useEffect, useState, useRef } from "react";
import { View, StyleSheet, Pressable, ScrollView, ActivityIndicator, TextInput, KeyboardAvoidingView, Platform } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Feather } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import { AppText, Button, Card, Pill } from "@/src/components/ui";
import { DraggableChip, PlateZone, useMeasuredPlateRef, Ingredient } from "@/src/components/PlateBuilder";
import { useReducedMotion } from "@/src/hooks/use-reduced-motion";
import { api } from "@/src/api";
import { colors, spacing } from "@/src/theme";
import { goBack } from "@/src/navigation";

type Hall = "commons" | "sbisa";
type Period = "breakfast" | "lunch" | "dinner";
type Tab = "suggested" | "build" | "chat";
type ChatMsg = { id: string; role: "user" | "assistant"; text: string; plateItems?: { id: string; name: string }[] };

/**
 * Build a Meal — grounded entirely in today's real Aggie Dining menu.
 *
 * Three modes sharing one plate:
 *   - Suggested: Plate Composer output (appeal-first, never health-ranked).
 *   - Build: drag-and-drop / tap-to-add from the real live menu.
 *   - Chat: grounded AI helper (hard server-side guardrail against any
 *     numeric calorie/gram/sodium leakage — see server.py).
 * "Tweak it" and "Add to my plate" hand off between modes onto the same
 * plateIds state, so switching modes never loses what's been built.
 *
 * Deep link (Future Me's "Find it at Sbisa"): /build-meal?hall=sbisa&
 * period=breakfast&add=<item id>&tab=build opens that hall and meal and
 * puts the item on the plate once the live menu confirms it's served today.
 */
const HALLS: Hall[] = ["commons", "sbisa"];
const PERIODS: Period[] = ["breakfast", "lunch", "dinner"];
const TABS: Tab[] = ["suggested", "build", "chat"];

export default function BuildMeal() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const reducedMotion = useReducedMotion();
  const params = useLocalSearchParams<{ hall?: string; period?: string; add?: string; tab?: string }>();
  const pick = <T extends string>(value: string | undefined, allowed: T[], fallback: T): T =>
    allowed.includes(value as T) ? (value as T) : fallback;

  const [hall, setHall] = useState<Hall>(pick(params.hall, HALLS, "sbisa"));
  const [period, setPeriod] = useState<Period>(pick(params.period, PERIODS, "lunch"));
  const [tab, setTab] = useState<Tab>(pick(params.tab, TABS, "suggested"));
  // The item a deep link asked for; cleared once it's been placed (or
  // found not to be on today's menu) so hall/period changes start clean.
  const pendingAddRef = useRef<string | null>(typeof params.add === "string" && params.add ? params.add : null);
  // Building a plate is a recommendation surface, so the tray hides items
  // matching the participant's allergies by default; "Show everything"
  // is their own explicit choice to see the full menu.
  const [showAllItems, setShowAllItems] = useState(false);

  const [menu, setMenu] = useState<any>(null);
  const [plates, setPlates] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [plateIds, setPlateIds] = useState<string[]>([]);
  const [logging, setLogging] = useState(false);
  const [logged, setLogged] = useState(false);

  const plateRef = useMeasuredPlateRef();

  const load = async () => {
    setLoading(true);
    try {
      const [menuRes, platesRes] = await Promise.all([
        api.getDiningMenu(hall, period, !showAllItems),
        api.getSuggestedPlates(hall, period),
      ]);
      setMenu(menuRes);
      setPlates(platesRes.plates);
      const wanted = pendingAddRef.current;
      if (wanted) {
        pendingAddRef.current = null;
        const served = (menuRes?.stations ?? []).some((st: any) => st.items.some((it: any) => it.id === wanted));
        if (served) setPlateIds((p) => (p.includes(wanted) ? p : [...p, wanted].slice(0, 5)));
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    setPlateIds([]);
    setLogged(false);
    load();
  }, [hall, period, showAllItems]);

  const allItems: (Ingredient & { tags?: any })[] = menu
    ? menu.stations.flatMap((st: any) => st.items.map((it: any) => ({ id: it.id, name: it.name, icon: "🍽️", tags: it.tags })))
    : [];
  const plateItems = allItems.filter((i) => plateIds.includes(i.id));
  const MAX_ITEMS = 5;

  const addToPlate = (id: string) => {
    if (plateIds.includes(id) || plateIds.length >= MAX_ITEMS) return;
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    setPlateIds((p) => [...p, id]);
  };
  const removeFromPlate = (id: string) => setPlateIds((p) => p.filter((x) => x !== id));

  const buildFromSuggestion = (plate: any) => {
    setPlateIds(plate.items.map((i: any) => i.id));
    setTab("build");
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
  };

  const logSuggestedPlate = async (plate: any) => {
    setLogging(true);
    try {
      // plate.aggregate is the Plate Composer's internal-phrasing summary
      // (never presented to the user as a score) — map it onto the
      // lightweight logging category taxonomy for the actual log entry.
      const categories: string[] = [];
      if (plate.aggregate?.has_vegetables) categories.push("vegetables");
      if (plate.aggregate?.has_whole_grains) categories.push("whole_grains");
      if (plate.aggregate?.has_lean_protein) categories.push("other_protein");
      if ((plate.aggregate?.high_sodium_items?.length ?? 0) > 0) categories.push("salty_processed");
      await api.createMeal({
        name: plate.items.map((i: any) => i.name).join(", "),
        source: "dining_hall",
        meal_type: period,
        categories,
        confirmed: true,
      });
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      goBack(router, "/");
    } finally {
      setLogging(false);
    }
  };

  const logBuiltPlate = async () => {
    if (plateItems.length === 0) return;
    setLogging(true);
    try {
      // Each menu item's tags carry its own log_categories (from
      // dining_classifier.py); union across the plate for the log entry.
      const categories = Array.from(
        new Set(plateItems.flatMap((i: any) => i.tags?.log_categories || []))
      );
      await api.createMeal({
        name: plateItems.map((i) => i.name).join(", "),
        source: "dining_hall",
        meal_type: period,
        categories,
        confirmed: true,
      });
      setLogged(true);
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      setTimeout(() => goBack(router, "/"), 700);
    } finally {
      setLogging(false);
    }
  };

  return (
    <View style={[styles.c, { paddingTop: insets.top + spacing.sm }]} testID="build-meal-screen">
      <View style={styles.header}>
        <Pressable onPress={() => goBack(router, "/")} hitSlop={10} testID="build-meal-close">
          <Feather name="x" size={26} color={colors.onSurface} />
        </Pressable>
        <AppText variant="title">Build a Meal</AppText>
        <View style={{ width: 26 }} />
      </View>

      <View style={styles.pickerRow}>
        <Pill label="Sbisa" active={hall === "sbisa"} onPress={() => setHall("sbisa")} testID="hall-sbisa" />
        <Pill label="Commons" active={hall === "commons"} onPress={() => setHall("commons")} testID="hall-commons" />
      </View>
      <View style={[styles.pickerRow, { marginTop: spacing.sm }]}>
        {(["breakfast", "lunch", "dinner"] as Period[]).map((p) => (
          <Pill key={p} label={p[0].toUpperCase() + p.slice(1)} active={period === p} onPress={() => setPeriod(p)} testID={`period-${p}`} />
        ))}
      </View>

      <View style={[styles.pickerRow, { marginTop: spacing.lg }]}>
        <Pill label="Suggested" active={tab === "suggested"} onPress={() => setTab("suggested")} testID="tab-suggested" />
        <Pill label="Build" active={tab === "build"} onPress={() => setTab("build")} testID="tab-build" />
        <Pill label="Chat" active={tab === "chat"} onPress={() => setTab("chat")} testID="tab-chat" />
      </View>

      {loading ? (
        <View style={styles.center}>
          <ActivityIndicator color={colors.brandPrimary} />
        </View>
      ) : tab === "suggested" ? (
        <SuggestedTab plates={plates} onBuildFrom={buildFromSuggestion} onLog={logSuggestedPlate} logging={logging} menuSource={menu?.source} />
      ) : tab === "build" ? (
        <BuildTab
          plateItems={plateItems}
          plateRef={plateRef}
          onAdd={addToPlate}
          onRemove={removeFromPlate}
          onLog={logBuiltPlate}
          logging={logging}
          logged={logged}
          reducedMotion={reducedMotion}
          stations={menu?.stations || []}
          hiddenCount={menu?.hidden_count || 0}
          showAllItems={showAllItems}
          onToggleShowAll={() => setShowAllItems((v) => !v)}
        />
      ) : (
        <ChatTab hall={hall} period={period} onAddToPlate={(ids) => { setPlateIds(ids); setTab("build"); }} />
      )}
    </View>
  );
}

function SuggestedTab({ plates, onBuildFrom, onLog, logging, menuSource }: any) {
  return (
    <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
      {menuSource === "sample" && (
        <AppText variant="caption" style={{ marginBottom: spacing.md }}>
          Showing a sample menu right now — not today's live Aggie Dining feed.
        </AppText>
      )}
      {plates.length === 0 ? (
        <AppText variant="body">No suggestions available for this hall/period right now.</AppText>
      ) : (
        plates.map((plate: any, i: number) => (
          <Card key={i} style={{ marginBottom: spacing.md }}>
            <AppText variant="body" color={colors.onSurface}>
              {plate.items.map((it: any) => it.name).join(" · ")}
            </AppText>
            <AppText variant="caption" style={{ marginTop: spacing.sm }}>
              {plate.blurb}
            </AppText>
            <View style={{ flexDirection: "row", gap: spacing.sm, marginTop: spacing.lg }}>
              <Button title="Tweak it" variant="secondary" onPress={() => onBuildFrom(plate)} style={{ flex: 1 }} testID={`suggestion-tweak-${i}`} />
              <Button title={logging ? "Logging…" : "Log it"} onPress={() => onLog(plate)} disabled={logging} style={{ flex: 1 }} testID={`suggestion-log-${i}`} />
            </View>
          </Card>
        ))
      )}
    </ScrollView>
  );
}

function BuildTab({ plateItems, plateRef, onAdd, onRemove, onLog, logging, logged, reducedMotion, stations,
                    hiddenCount, showAllItems, onToggleShowAll }: any) {
  return (
    <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
      <PlateZone plateRef={plateRef} items={plateItems} onRemove={onRemove} emptyLabel="Drag items here, or tap one below to add it" />
      {(hiddenCount > 0 || showAllItems) && (
        <Pressable onPress={onToggleShowAll} style={{ marginTop: spacing.md }} testID="build-toggle-allergy-filter">
          <AppText variant="caption">
            {showAllItems
              ? "Showing everything served, including items that may contain your allergens · Hide them"
              : `${hiddenCount} item${hiddenCount === 1 ? "" : "s"} hidden because of your allergies or restrictions · Show everything`}
          </AppText>
        </Pressable>
      )}
      {stations.map((st: any) => (
        <View key={st.station} style={{ marginTop: spacing.xl }}>
          <AppText variant="label" style={{ marginBottom: spacing.sm }}>
            {st.station.toUpperCase()}
          </AppText>
          <View style={styles.tray}>
            {st.items.map((it: any) => (
              <DraggableChip
                key={it.id}
                ingredient={{ id: it.id, name: it.name, icon: "🍽️" }}
                plateRef={plateRef}
                onAdd={onAdd}
                disabled={plateItems.some((p: any) => p.id === it.id)}
                reducedMotion={reducedMotion}
                testID={`build-ingredient-${it.id}`}
              />
            ))}
          </View>
        </View>
      ))}
      <Button
        title={logged ? "Logged ✓" : logging ? "Logging…" : "Log this meal"}
        onPress={onLog}
        disabled={logging || logged || plateItems.length === 0}
        style={{ marginTop: spacing.xl }}
        testID="build-log-meal"
      />
      <View style={{ height: spacing["3xl"] }} />
    </ScrollView>
  );
}

function ChatTab({ hall, period, onAddToPlate }: { hall: Hall; period: Period; onAddToPlate: (ids: string[]) => void }) {
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const scrollRef = useRef<ScrollView>(null);

  const send = async () => {
    const text = input.trim();
    if (!text || sending) return;
    setInput("");
    setMessages((m) => [...m, { id: `u-${Date.now()}`, role: "user", text }]);
    setSending(true);
    try {
      const res = await api.chatBuildMeal(text, hall, period);
      setMessages((m) => [...m, { id: `a-${Date.now()}`, role: "assistant", text: res.reply, plateItems: res.plate_items }]);
      setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 100);
    } catch {
      setMessages((m) => [...m, { id: `a-err-${Date.now()}`, role: "assistant", text: "Something went wrong — try again?" }]);
    } finally {
      setSending(false);
    }
  };

  return (
    <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={{ flex: 1 }}>
      <ScrollView ref={scrollRef} contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
        {messages.length === 0 && (
          <AppText variant="body">
            Tell me what you're in the mood for — "something filling with chicken" or "no dairy" — and I'll pull from today's real menu.
          </AppText>
        )}
        {messages.map((m) => (
          <View key={m.id} style={[styles.bubbleWrap, m.role === "user" ? styles.right : styles.left]}>
            <View style={[styles.bubble, m.role === "user" ? styles.userBubble : styles.botBubble]}>
              <AppText variant="body" color={m.role === "user" ? colors.onBrandPrimary : colors.onSurface}>
                {m.text}
              </AppText>
            </View>
            {!!m.plateItems?.length && (
              <Pressable
                onPress={() => onAddToPlate(m.plateItems!.map((i) => i.id))}
                style={styles.addToPlateBtn}
                testID="chat-add-to-plate"
              >
                <AppText variant="caption" color={colors.brandPrimary}>
                  Add {m.plateItems!.map((i) => i.name).join(", ")} to my plate →
                </AppText>
              </Pressable>
            )}
          </View>
        ))}
        {sending && <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.md }} />}
      </ScrollView>
      <View style={styles.inputRow}>
        <TextInput
          value={input}
          onChangeText={setInput}
          placeholder="What sounds good today?"
          placeholderTextColor={colors.muted}
          style={styles.chatInput}
          onSubmitEditing={send}
          testID="chat-input"
        />
        <Pressable onPress={send} disabled={sending || !input.trim()} style={styles.sendBtn} testID="chat-send">
          <Feather name="arrow-up" size={18} color={colors.onBrandPrimary} />
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  c: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingHorizontal: spacing.xl, paddingBottom: spacing.md },
  pickerRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, paddingHorizontal: spacing.xl },
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  scroll: { paddingHorizontal: spacing.xl, paddingTop: spacing.lg, paddingBottom: spacing["3xl"] },
  tray: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  bubbleWrap: { marginBottom: spacing.lg, maxWidth: "85%" },
  left: { alignSelf: "flex-start" },
  right: { alignSelf: "flex-end" },
  bubble: { borderRadius: 16, paddingHorizontal: spacing.lg, paddingVertical: spacing.md },
  userBubble: { backgroundColor: colors.brandPrimary },
  botBubble: { backgroundColor: colors.surfaceSecondary },
  addToPlateBtn: { marginTop: spacing.xs, paddingHorizontal: spacing.sm },
  inputRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.md,
    borderTopWidth: 1,
    borderTopColor: colors.border,
  },
  chatInput: {
    flex: 1,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 999,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    color: colors.onSurface,
  },
  sendBtn: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: colors.brandPrimary,
    alignItems: "center",
    justifyContent: "center",
  },
});
