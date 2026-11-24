import React, { useCallback, useEffect, useRef, useState } from "react";
import { View, Text, StyleSheet, TextInput, Pressable, FlatList, Animated, Easing, Platform } from "react-native";
import { KeyboardAvoidingView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useFocusEffect, useLocalSearchParams, useRouter } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { AppText, Button } from "@/src/components/ui";
import { Avatar, IconCircle } from "@/src/components/llhs";
import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { futureMeMessage } from "@/src/future-me";
import { TwinCard, TwinData } from "@/src/components/TwinCard";
import { colors, fonts, radius, spacing } from "@/src/theme";
import { useReducedMotion } from "@/src/hooks/use-reduced-motion";

// Future Me — the app's one conversational guide (study team feedback 5.1,
// 5.2; it replaces the separate "Coach"). Top: the avatar, one message tied
// to the participant's goal, and suggested prompts, including the what-if
// scenarios from the rule-based engine (direction only, never a number).
// Then "Your routines", the behavioral twin across food, movement and
// sleep (src/components/TwinCard.tsx): it asks about patterns it notices in
// the student's own logs and tracker before treating them as true, offers
// one or two small steps from a reviewed library (food swaps from the meal
// logs among them, with today's real dining menu) and says why, and
// remembers the reasons a step didn't fit. Main: the conversation and a text
// box. Food answers come only from the reviewed knowledge base (named
// under each reply); questions about their own goal, progress and regular
// meals come only from their own data. Proposed actions stay proposals
// until the participant taps Confirm.

type PendingAction = { type: string; payload: Record<string, any>; summary: string };
type Citation = { id: string; title: string; source?: string };
type Msg = {
  id: string;
  role: "user" | "assistant";
  text: string;
  citations?: Citation[];
  pendingAction?: PendingAction | null;
  actionState?: "pending" | "confirming" | "confirmed" | "dismissed" | "error";
  failedPrompt?: string;
};
type Scenario = { id: string; title: string; domain: "food" | "move" | "rest" };

const FALLBACK_PROMPTS = ["What's one thing I could work on this week?", "What's a balanced plate?", "Help me check in on my progress"];

// One conversation per app session; "New chat" starts another.
let currentSession = newSessionId();
function newSessionId() {
  return `s${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
}

function renderInlineMarkdown(text: string): React.ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**") && part.length > 4 ? (
      <Text key={i} style={{ fontFamily: fonts.bold }}>
        {part.slice(2, -2)}
      </Text>
    ) : (
      part
    )
  );
}

function TypingDots() {
  const reduced = useReducedMotion();
  const t = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    if (reduced) return;
    const loop = Animated.loop(Animated.timing(t, { toValue: 1, duration: 1200, easing: Easing.linear, useNativeDriver: Platform.OS !== "web" }));
    loop.start();
    return () => loop.stop();
  }, [reduced, t]);
  if (reduced) {
    return (
      <AppText variant="caption" testID="coach-typing">
        Future Me is typing…
      </AppText>
    );
  }
  return (
    <View style={{ flexDirection: "row", gap: 5, paddingVertical: 4 }} testID="coach-typing" accessibilityLabel="Future Me is typing">
      {[0, 1, 2].map((i) => (
        <Animated.View
          key={i}
          style={[styles.dot, { opacity: t.interpolate({ inputRange: [0, (i + 1) / 4, (i + 2) / 4, 1], outputRange: [0.3, 1, 0.3, 0.3] }) }]}
        />
      ))}
    </View>
  );
}

export default function FutureMe() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { q } = useLocalSearchParams<{ q?: string }>();
  const { user } = useAuth();
  const hasKey = user?.tamus_ai_available !== false;
  const [session, setSession] = useState(currentSession);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState(typeof q === "string" ? q : "");
  const [sending, setSending] = useState(false);
  const [prompts, setPrompts] = useState<string[]>(FALLBACK_PROMPTS);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [twin, setTwin] = useState<TwinData | null>(null);
  const [message, setMessage] = useState<string>("");
  const listRef = useRef<FlatList>(null);
  const messagesRef = useRef<Msg[]>([]);
  messagesRef.current = messages;

  useEffect(() => {
    if (typeof q === "string" && q) setInput(q);
  }, [q]);

  // The top message and what-ifs reflect today's data, so refresh on focus.
  useFocusEffect(
    useCallback(() => {
      let alive = true;
      Promise.allSettled([api.getFutureMe(), api.getGamification()]).then(([fm, gam]) => {
        if (!alive) return;
        const home: any = fm.status === "fulfilled" ? fm.value : null;
        const g: any = gam.status === "fulfilled" ? gam.value : null;
        setScenarios((home?.scenarios ?? []).slice(0, 3));
        setTwin(home?.twin ?? null);
        setMessage(
          futureMeMessage({
            area: user?.focus_area,
            goal: user?.focus_goal?.goal,
            hasResults: !!home?.eat?.has_assessment,
            isNewUser: !g || ((g.points ?? 0) === 0 && (g.streak ?? 0) === 0),
            streak: g?.streak ?? 0,
          })
        );
      });
      api
        .getSuggestedPrompts()
        .then((d: any) => alive && d?.prompts?.length && setPrompts(d.prompts.slice(0, 3)))
        .catch(() => {});
      return () => {
        alive = false;
      };
    }, [user?.focus_area, user?.focus_goal?.goal])
  );

  useEffect(() => {
    let alive = true;
    api
      .chatHistory(session)
      .then((h: any[]) => alive && setMessages((h || []).map((m) => ({ id: m.id, role: m.role, text: m.text, citations: m.citations }))))
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [session]);

  const scrollEnd = () => setTimeout(() => listRef.current?.scrollToEnd({ animated: true }), 80);

  const send = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || sending) return;
      setInput("");
      setMessages((m) => [...m.filter((x) => !x.failedPrompt), { id: `u-${Date.now()}`, role: "user", text: trimmed }]);
      setSending(true);
      scrollEnd();
      try {
        const res = await api.chat(trimmed, session);
        const pendingAction: PendingAction | null = res.pending_action || null;
        setMessages((m) => [
          ...m,
          {
            id: `a-${Date.now()}`,
            role: "assistant",
            text: res.answer,
            citations: res.citations || [],
            pendingAction,
            actionState: pendingAction ? "pending" : undefined,
            failedPrompt: res.error ? trimmed : undefined,
          },
        ]);
      } catch {
        setMessages((m) => [...m, { id: `e-${Date.now()}`, role: "assistant", text: "Sorry, I couldn't answer just now.", failedPrompt: trimmed }]);
      } finally {
        setSending(false);
        scrollEnd();
      }
    },
    [sending, session]
  );

  // What-ifs come from the rule-based engine (direction only), shown in the conversation.
  const whatIf = async (s: Scenario) => {
    if (sending) return;
    setMessages((m) => [...m, { id: `u-${Date.now()}`, role: "user", text: `What if I ${s.title.charAt(0).toLowerCase()}${s.title.slice(1)}?` }]);
    setSending(true);
    scrollEnd();
    try {
      const res = await api.whatIf(s.id);
      setMessages((m) => [...m, { id: `a-${Date.now()}`, role: "assistant", text: res.text }]);
    } catch {
      setMessages((m) => [...m, { id: `e-${Date.now()}`, role: "assistant", text: "Sorry, I couldn't work that out just now." }]);
    } finally {
      setSending(false);
      scrollEnd();
    }
  };

  const setActionState = (id: string, actionState: Msg["actionState"]) =>
    setMessages((m) => m.map((x) => (x.id === id ? { ...x, actionState } : x)));

  const confirmAction = useCallback(async (id: string) => {
    const target = messagesRef.current.find((x) => x.id === id);
    if (!target?.pendingAction) return;
    setActionState(id, "confirming");
    try {
      await api.confirmChatAction({ type: target.pendingAction.type, payload: target.pendingAction.payload });
      setActionState(id, "confirmed");
      // A confirmed step, swap or focus-area change alters what the twin
      // card shows (a new area means new food steps).
      if (["try_swap", "try_step", "set_focus_areas", "log_meal", "log_activity", "log_sleep"].includes(target.pendingAction.type)) {
        api.getTwin().then((d: any) => d && setTwin(d)).catch(() => {});
      }
    } catch {
      setActionState(id, "error");
    }
  }, []);

  const newChat = () => {
    currentSession = newSessionId();
    setSession(currentSession);
    setMessages([]);
  };

  const renderItem = ({ item }: { item: Msg }) => {
    const mine = item.role === "user";
    return (
      <View style={{ alignItems: mine ? "flex-end" : "flex-start", gap: 6, paddingHorizontal: spacing.xl }} testID={mine ? "coach-user-msg" : "coach-reply"}>
        <View style={[styles.bubble, mine ? styles.mine : styles.theirs]}>
          <Text style={[styles.msgText, mine && { color: colors.onBrandPrimary }]}>{renderInlineMarkdown(item.text)}</Text>
          {!!item.citations?.length && (
            <View style={styles.cite} testID="coach-citation">
              <Feather name="book-open" size={12} color={colors.muted} />
              <AppText variant="caption" style={{ fontSize: 12 }}>
                From: {item.citations.map((c) => c.title).join(", ")}
              </AppText>
            </View>
          )}
        </View>
        {item.failedPrompt && (
          <Pressable onPress={() => send(item.failedPrompt!)} style={styles.retry} testID="coach-retry">
            <Feather name="rotate-cw" size={13} color={colors.brandPrimary} />
            <AppText variant="label" color={colors.brandPrimary} style={{ fontSize: 13 }}>
              Try again
            </AppText>
          </Pressable>
        )}
        {item.pendingAction && (
          <View style={styles.action} testID="coach-action">
            <AppText variant="label" style={{ fontSize: 13 }}>
              {item.pendingAction.summary}
            </AppText>
            {item.actionState === "pending" || item.actionState === "error" ? (
              <>
                {item.actionState === "error" && (
                  <AppText variant="caption" color={colors.error}>
                    That didn&apos;t save. You can try again.
                  </AppText>
                )}
                <View style={{ flexDirection: "row", gap: spacing.sm }}>
                  <Button title="Confirm" onPress={() => confirmAction(item.id)} style={{ flex: 1 }} testID="coach-action-confirm" />
                  <Button title="Dismiss" variant="secondary" onPress={() => setActionState(item.id, "dismissed")} style={{ flex: 1 }} testID="coach-action-dismiss" />
                </View>
              </>
            ) : (
              <AppText variant="caption" color={item.actionState === "confirmed" ? colors.success : colors.muted}>
                {item.actionState === "confirming" ? "Saving…" : item.actionState === "confirmed" ? "Saved" : "Dismissed. Nothing was changed."}
              </AppText>
            )}
          </View>
        )}
      </View>
    );
  };

  const top = (
    <View style={styles.top} testID="future-me-top">
      <View style={{ flexDirection: "row", gap: spacing.md, alignItems: "flex-start" }}>
        <Avatar size={72} />
        <View style={[styles.bubble, styles.theirs, { flex: 1, maxWidth: undefined }]}>
          <Text style={[styles.msgText, { fontFamily: fonts.medium }]} testID="future-me-message">
            {message || " "}
          </Text>
        </View>
      </View>
      <TwinCard data={twin} onChange={setTwin} onAsk={hasKey ? (text) => send(text) : (text) => setInput(text)} disabled={sending} />
      <View style={{ gap: spacing.sm }}>
        {prompts.map((p) => (
          <Pressable
            key={p}
            onPress={() => (hasKey ? send(p) : setInput(p))}
            style={styles.suggestion}
            testID="coach-suggestion"
            disabled={sending}
          >
            <Feather name="message-circle" size={15} color={colors.brandPrimary} />
            <AppText variant="body" color={colors.onSurface} style={{ flex: 1, fontSize: 14 }}>
              {p}
            </AppText>
          </Pressable>
        ))}
        {scenarios.map((s) => (
          <Pressable key={s.id} onPress={() => whatIf(s)} style={styles.suggestion} testID={`what-if-${s.id}`} disabled={sending}>
            <Feather name="git-branch" size={15} color={colors.warm} />
            <AppText variant="body" color={colors.onSurface} style={{ flex: 1, fontSize: 14 }}>
              What if: {s.title}
            </AppText>
          </Pressable>
        ))}
      </View>
    </View>
  );

  return (
    <View style={[styles.c, { paddingTop: insets.top }]} testID="future-me-screen">
      <View style={styles.header}>
        <View style={{ flex: 1 }}>
          <AppText variant="title">Future Me</AppText>
          <AppText variant="caption">The you you&apos;re becoming, built from your own habits</AppText>
        </View>
        {messages.length > 0 && (
          <Pressable onPress={newChat} hitSlop={8} style={styles.newChat} testID="coach-new-chat">
            <Feather name="edit" size={15} color={colors.brandPrimary} />
            <AppText variant="label" color={colors.brandPrimary} style={{ fontSize: 13 }}>
              New chat
            </AppText>
          </Pressable>
        )}
      </View>

      <KeyboardAvoidingView style={{ flex: 1 }} behavior="padding" keyboardVerticalOffset={0}>
        <FlatList
          ref={listRef}
          data={messages}
          keyExtractor={(m) => m.id}
          renderItem={renderItem}
          ListHeaderComponent={top}
          contentContainerStyle={{ paddingBottom: spacing.xl, gap: spacing.md, flexGrow: 1 }}
          ListFooterComponent={
            sending ? (
              <View style={{ paddingHorizontal: spacing.xl }}>
                <View style={[styles.bubble, styles.theirs, { alignSelf: "flex-start" }]}>
                  <TypingDots />
                </View>
              </View>
            ) : null
          }
        />
        {hasKey ? (
          <>
            <View style={[styles.inputRow, { paddingBottom: spacing.sm }]}>
              <TextInput
                value={input}
                onChangeText={setInput}
                placeholder="Ask Future Me"
                placeholderTextColor={colors.muted}
                style={styles.input}
                multiline
                maxLength={2000}
                onSubmitEditing={() => send(input)}
                testID="coach-input"
              />
              <Pressable
                onPress={() => send(input)}
                disabled={!input.trim() || sending}
                style={[styles.send, (!input.trim() || sending) && { opacity: 0.4 }]}
                accessibilityLabel="Send"
                testID="coach-send"
              >
                <Feather name="arrow-up" size={20} color={colors.onBrandPrimary} />
              </Pressable>
            </View>
            <AppText variant="caption" style={{ textAlign: "center", fontSize: 11, paddingBottom: 6 }}>
              General guidance from reviewed notes and your own logs, not medical advice.
            </AppText>
          </>
        ) : (
          <View style={styles.noKey} testID="coach-no-key">
            <IconCircle icon="key" color={colors.brandPrimary} tint={colors.brandTertiary} size={36} iconSize={16} />
            <AppText variant="caption" style={{ flex: 1 }}>
              Add your TAMU AI key in Settings to chat with Future Me. What-ifs work without it.
            </AppText>
            <Button title="Settings" variant="secondary" onPress={() => router.push("/settings")} testID="coach-open-settings" />
          </View>
        )}
      </KeyboardAvoidingView>
    </View>
  );
}

const styles = StyleSheet.create({
  c: { flex: 1, backgroundColor: colors.surface },
  header: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  top: { gap: spacing.lg, padding: spacing.xl, paddingBottom: spacing.md },
  newChat: { flexDirection: "row", alignItems: "center", gap: 5 },
  bubble: { maxWidth: "86%", borderRadius: radius.lg, paddingHorizontal: 14, paddingVertical: 10, gap: 8 },
  mine: { backgroundColor: colors.brandPrimary, borderBottomRightRadius: 4 },
  theirs: { backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, borderBottomLeftRadius: 4 },
  msgText: { fontFamily: fonts.regular, fontSize: 15, lineHeight: 21, color: colors.onSurface },
  cite: { flexDirection: "row", alignItems: "center", gap: 5, paddingTop: 6, borderTopWidth: 1, borderTopColor: colors.divider },
  retry: { flexDirection: "row", alignItems: "center", gap: 5, paddingHorizontal: 4 },
  action: {
    width: "86%",
    gap: spacing.sm,
    padding: spacing.md,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.brandTertiary,
  },
  dot: { width: 7, height: 7, borderRadius: 4, backgroundColor: colors.muted },
  suggestion: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    backgroundColor: colors.surfaceSecondary,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.lg,
    paddingHorizontal: spacing.lg,
    paddingVertical: 12,
  },
  inputRow: { flexDirection: "row", alignItems: "flex-end", gap: spacing.sm, paddingHorizontal: spacing.lg, paddingTop: spacing.sm },
  input: {
    flex: 1,
    minHeight: 44,
    maxHeight: 120,
    borderRadius: 22,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surfaceSecondary,
    paddingHorizontal: 16,
    paddingTop: 11,
    paddingBottom: 11,
    fontFamily: fonts.regular,
    fontSize: 15,
    color: colors.onSurface,
  },
  send: { width: 44, height: 44, borderRadius: 22, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" },
  noKey: { flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.lg, borderTopWidth: 1, borderTopColor: colors.border },
});
