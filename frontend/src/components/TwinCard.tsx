import React, { useState } from "react";
import { View, StyleSheet, Pressable, TextInput } from "react-native";
import { useRouter } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { AppText, Button, Card } from "@/src/components/ui";
import { api } from "@/src/api";
import { colors, domain as domainColors, fonts, radius, spacing } from "@/src/theme";

// The behavioral twin on Future Me: one card across food, movement and
// sleep (the three behavior areas of AHA Life's Essential 8, never combined
// into a score). It ASKS about patterns it notices before treating them as
// true ("Is this right?"), offers one or two small steps from a reviewed
// library with the reason each was chosen, remembers why a step didn't
// work ("Too expensive", "Doesn't fit my schedule"), keeps steps that
// worked going, and shows everything it has learned so the student can
// correct it. The only numbers are counts of what the student logged and
// clock times their own tracker or log reported.

type Option = { id: string; label: string };
type Question = { key: string; domain: string; question: string; evidence: string; circumstances: Option[] };
type MenuMatch = { hall: string; hall_label: string; period: string; station: string; item_id: string; item_name: string };
type Step = {
  id: string;
  origin: "library" | "swap";
  domains: string[];
  type: string;
  type_label: string;
  title: string;
  text: string;
  why: string | null;
  model_why?: string | null;
  evidence?: string | null;
  techniques: string[];
  when_options: Option[];
  coping: { barrier: string; if: string; then: string }[];
  grocery: string[];
  on_menu_today: MenuMatch[];
  where?: string | null;
  status: "trying" | null;
  plan: { when?: string | null; coping?: string | null } | null;
};
type Reinforce = { id: string; title: string; domains: string[]; message: string; check_in: boolean; grocery: string[] };
type Learned = { key: string; label: string; source: string };
type GroceryItem = { id: string; text: string; done: boolean };
export type TwinData = {
  status: Record<string, string>;
  notes: Record<string, string | null>;
  questions: Question[];
  recommendations: Step[];
  reinforcing: Reinforce[];
  learned: Learned[];
  offer_domains: ("activity" | "sleep")[];
  grocery_list: GroceryItem[];
  reasons: Option[];
  paused: boolean;
};

const DOMAIN: Record<string, { label: string; color: string; tint: string }> = {
  diet: { label: "Food", color: domainColors.food.text, tint: domainColors.food.tint },
  activity: { label: "Move", color: domainColors.move.text, tint: domainColors.move.tint },
  sleep: { label: "Sleep", color: domainColors.rest.text, tint: domainColors.rest.tint },
  cross: { label: "Across your week", color: colors.brandPrimary, tint: colors.brandTertiary },
};
const SLOT_WORD: Record<string, string> = { breakfast: "breakfast", lunch: "lunch", dinner: "dinner" };

function DomainTags({ domains }: { domains: string[] }) {
  return (
    <View style={styles.tags}>
      {domains.map((d) => (
        <View key={d} style={[styles.tag, { backgroundColor: (DOMAIN[d] ?? DOMAIN.cross).tint }]}>
          <AppText variant="caption" color={(DOMAIN[d] ?? DOMAIN.cross).color} style={{ fontSize: 11, fontFamily: fonts.semibold }}>
            {(DOMAIN[d] ?? DOMAIN.cross).label}
          </AppText>
        </View>
      ))}
    </View>
  );
}

function Chips({ options, selected, onToggle, testID }: { options: Option[]; selected: string[]; onToggle: (id: string) => void; testID: string }) {
  return (
    <View style={styles.chips}>
      {options.map((o) => {
        const on = selected.includes(o.id);
        return (
          <Pressable
            key={o.id}
            onPress={() => onToggle(o.id)}
            style={[styles.chip, on && styles.chipOn]}
            accessibilityRole="checkbox"
            accessibilityState={{ checked: on }}
            testID={`${testID}-${o.id}`}
          >
            <AppText variant="caption" color={on ? colors.onSurfaceInverse : colors.onSurfaceSecondary} style={{ fontSize: 12 }}>
              {o.label}
            </AppText>
          </Pressable>
        );
      })}
    </View>
  );
}

const toggle = (list: string[], id: string) => (list.includes(id) ? list.filter((x) => x !== id) : [...list, id]);

// ---- "Is this right?" ------------------------------------------------------------------
function QuestionBlock({ q, onDone, disabled }: { q: Question; onDone: (next: TwinData) => void; disabled?: boolean }) {
  const [answer, setAnswer] = useState<"yes" | "sometimes" | null>(null);
  const [picked, setPicked] = useState<string[]>([]);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const send = async (a: "yes" | "sometimes" | "no", circs: string[] = [], text = "") => {
    setBusy(true);
    try {
      const res: any = await api.answerTwinQuestion(q.key, a, circs, text.trim() || undefined);
      if (res?.twin) onDone(res.twin);
    } catch {
      // leave it as it was; they can tap again
    } finally {
      setBusy(false);
    }
  };
  return (
    <View style={styles.block} testID={`twin-question-${q.key}`}>
      <DomainTags domains={[q.domain]} />
      {!!q.evidence && (
        <AppText variant="caption" style={{ fontSize: 12 }}>
          {q.evidence}
        </AppText>
      )}
      <AppText variant="subtitle" style={{ fontSize: 16 }}>
        {q.question}
      </AppText>
      {answer === null ? (
        <View style={styles.row}>
          <Button title="Yes" onPress={() => setAnswer("yes")} disabled={disabled || busy} style={{ flex: 1 }} testID={`twin-q-yes-${q.key}`} />
          <Button title="Sometimes" variant="secondary" onPress={() => setAnswer("sometimes")} disabled={disabled || busy} style={{ flex: 1 }} testID={`twin-q-sometimes-${q.key}`} />
          <Button title="Not really" variant="ghost" onPress={() => send("no")} loading={busy} disabled={disabled} testID={`twin-q-no-${q.key}`} />
        </View>
      ) : (
        <View style={{ gap: spacing.sm }}>
          <AppText variant="caption">What&apos;s behind it? Optional, and it helps me suggest things that fit.</AppText>
          <Chips options={q.circumstances} selected={picked} onToggle={(id) => setPicked(toggle(picked, id))} testID={`twin-circ-${q.key}`} />
          <TextInput
            value={note}
            onChangeText={setNote}
            placeholder="Anything else? (optional)"
            placeholderTextColor={colors.muted}
            style={styles.input}
            maxLength={200}
            testID={`twin-q-note-${q.key}`}
          />
          <View style={styles.row}>
            <Button title="Save" onPress={() => send(answer, picked, note)} loading={busy} disabled={disabled} style={{ flex: 1 }} testID={`twin-q-save-${q.key}`} />
            <Button title="Back" variant="ghost" onPress={() => setAnswer(null)} disabled={busy} testID={`twin-q-back-${q.key}`} />
          </View>
        </View>
      )}
    </View>
  );
}

// ---- reasons, for "Not for me" and "Didn't fit" ------------------------------------------------------
function ReasonPanel({
  reasons,
  allowAlreadyDo,
  busy,
  onSave,
  onCancel,
  testID,
}: {
  reasons: Option[];
  allowAlreadyDo: boolean;
  busy: boolean;
  onSave: (reasons: string[], note: string) => void;
  onCancel: () => void;
  testID: string;
}) {
  const [picked, setPicked] = useState<string[]>([]);
  const [note, setNote] = useState("");
  const options = reasons.filter((r) => allowAlreadyDo || r.id !== "already_do");
  return (
    <View style={styles.panel} testID={testID}>
      <AppText variant="label" style={{ fontSize: 13 }}>
        What got in the way? I&apos;ll remember it.
      </AppText>
      <Chips options={options} selected={picked} onToggle={(id) => setPicked(toggle(picked, id))} testID={`${testID}-reason`} />
      <TextInput
        value={note}
        onChangeText={setNote}
        placeholder="In your own words (optional)"
        placeholderTextColor={colors.muted}
        style={styles.input}
        maxLength={200}
        testID={`${testID}-note`}
      />
      <View style={styles.row}>
        <Button title="Save" onPress={() => onSave(picked, note)} loading={busy} style={{ flex: 1 }} testID={`${testID}-save`} />
        <Button title="Cancel" variant="ghost" onPress={onCancel} disabled={busy} testID={`${testID}-cancel`} />
      </View>
    </View>
  );
}

// ---- one step ---------------------------------------------------------------------------------------------
function StepBlock({
  s,
  reasons,
  onDone,
  onAsk,
  onGrocery,
  disabled,
}: {
  s: Step;
  reasons: Option[];
  onDone: (next: TwinData) => void;
  onAsk?: (text: string) => void;
  onGrocery: (recId: string) => void;
  disabled?: boolean;
}) {
  const router = useRouter();
  const [when, setWhen] = useState<string | null>(null);
  const [asking, setAsking] = useState<null | "decline" | "didnt_fit">(null);
  const [busy, setBusy] = useState(false);
  const first = s.on_menu_today?.[0];
  const send = async (response: "accept" | "decline" | "worked" | "didnt_fit", extra: { reasons?: string[]; note?: string } = {}) => {
    setBusy(true);
    try {
      const res: any = await api.respondTwinStep({
        rec_id: s.id,
        response,
        when: response === "accept" ? when ?? undefined : undefined,
        reasons: extra.reasons,
        note: extra.note?.trim() || undefined,
      });
      if (res?.twin) onDone(res.twin);
      setAsking(null);
    } catch {
      // unchanged; they can tap again
    } finally {
      setBusy(false);
    }
  };
  const whenLabel = s.plan?.when ? s.when_options.find((w) => w.id === s.plan?.when)?.label : null;
  return (
    <View style={styles.block} testID={`twin-step-${s.id}`}>
      <View style={[styles.row, { justifyContent: "space-between" }]}>
        <DomainTags domains={s.domains.length > 1 ? ["cross", ...s.domains] : s.domains} />
        <AppText variant="caption" style={{ fontSize: 11 }}>
          {s.type_label}
        </AppText>
      </View>
      {!!s.evidence && (
        <AppText variant="caption" style={{ fontSize: 12 }}>
          {s.evidence}
        </AppText>
      )}
      <AppText variant="subtitle" style={{ fontSize: 16 }}>
        {s.title}
      </AppText>
      <AppText variant="body" style={{ fontSize: 14 }}>
        {s.text}
      </AppText>
      {!!s.why && (
        <View style={styles.why} testID={`twin-why-${s.id}`}>
          <Feather name="info" size={12} color={colors.muted} style={{ marginTop: 2 }} />
          <AppText variant="caption" style={{ flex: 1, fontSize: 12 }}>
            Why this: {s.why}
          </AppText>
        </View>
      )}
      {!!s.model_why && (
        <AppText variant="body" style={{ fontSize: 13, fontStyle: "italic" }}>
          {s.model_why}
        </AppText>
      )}
      {(first || s.where) && (
        <View style={styles.where}>
          <Feather name={first ? "map-pin" : "home"} size={13} color={colors.muted} />
          <AppText variant="caption" style={{ flex: 1, fontSize: 12 }}>
            {first ? `${first.item_name} · ${first.hall_label} ${SLOT_WORD[first.period] ?? first.period} (${first.station})` : s.where}
          </AppText>
        </View>
      )}
      {first && (
        <Pressable
          onPress={() => router.push({ pathname: "/build-meal", params: { hall: first.hall, period: first.period, add: first.item_id, tab: "build" } })}
          style={styles.find}
          disabled={disabled}
          testID={`twin-find-${s.id}`}
        >
          <Feather name="compass" size={14} color={colors.brandPrimary} />
          <AppText variant="label" color={colors.brandPrimary} style={{ fontSize: 13 }}>
            Find it at {first.hall_label}
          </AppText>
        </Pressable>
      )}

      {s.status === "trying" ? (
        <View style={{ gap: spacing.sm }}>
          <AppText variant="caption" color={colors.success}>
            You&apos;re trying this{whenLabel ? ` · ${whenLabel.toLowerCase()}` : ""}
          </AppText>
          {s.coping.map((c) => (
            <AppText key={c.barrier} variant="caption" style={{ fontSize: 12 }}>
              If it gets hard: {c.if.charAt(0).toLowerCase() + c.if.slice(1)}, {c.then}.
            </AppText>
          ))}
          {asking === "didnt_fit" ? (
            <ReasonPanel
              reasons={reasons}
              allowAlreadyDo={false}
              busy={busy}
              onSave={(r, n) => send("didnt_fit", { reasons: r, note: n })}
              onCancel={() => setAsking(null)}
              testID={`twin-didnt-${s.id}`}
            />
          ) : (
            <View style={styles.row}>
              <Button title="It's working" onPress={() => send("worked")} loading={busy} disabled={disabled} style={{ flex: 1 }} testID={`twin-worked-${s.id}`} />
              <Button title="Didn't fit" variant="secondary" onPress={() => setAsking("didnt_fit")} disabled={disabled || busy} style={{ flex: 1 }} testID={`twin-didnt-fit-${s.id}`} />
            </View>
          )}
        </View>
      ) : asking === "decline" ? (
        <ReasonPanel
          reasons={reasons}
          allowAlreadyDo
          busy={busy}
          onSave={(r, n) => send("decline", { reasons: r, note: n })}
          onCancel={() => setAsking(null)}
          testID={`twin-decline-${s.id}`}
        />
      ) : (
        <View style={{ gap: spacing.sm }}>
          {s.when_options.length > 1 && (
            <View style={{ gap: 4 }}>
              <AppText variant="caption" style={{ fontSize: 12 }}>
                When would it fit? (optional)
              </AppText>
              <Chips options={s.when_options} selected={when ? [when] : []} onToggle={(id) => setWhen(when === id ? null : id)} testID={`twin-when-${s.id}`} />
            </View>
          )}
          <View style={styles.row}>
            <Button title="I'll try it" onPress={() => send("accept")} loading={busy} disabled={disabled} style={{ flex: 1 }} testID={`twin-try-${s.id}`} />
            <Button title="Not for me" variant="secondary" onPress={() => setAsking("decline")} disabled={disabled || busy} style={{ flex: 1 }} testID={`twin-decline-btn-${s.id}`} />
          </View>
        </View>
      )}
      <View style={[styles.row, { gap: spacing.lg }]}>
        {s.grocery.length > 0 && (
          <Pressable onPress={() => onGrocery(s.id)} style={styles.link} disabled={disabled} testID={`twin-grocery-${s.id}`}>
            <Feather name="shopping-cart" size={13} color={colors.muted} />
            <AppText variant="caption" style={{ fontSize: 12 }}>
              Add to grocery list
            </AppText>
          </Pressable>
        )}
        {onAsk && (
          <Pressable onPress={() => onAsk(`Tell me more about this step: ${s.title.toLowerCase()}`)} style={styles.link} disabled={disabled} testID={`twin-ask-${s.id}`}>
            <Feather name="message-circle" size={13} color={colors.muted} />
            <AppText variant="caption" style={{ fontSize: 12 }}>
              Ask Future Me
            </AppText>
          </Pressable>
        )}
      </View>
    </View>
  );
}

// ---- the card ---------------------------------------------------------------------------------------------
export function TwinCard({
  data,
  onChange,
  onAsk,
  disabled,
}: {
  data: TwinData | null;
  onChange: (next: TwinData) => void;
  onAsk?: (text: string) => void;
  disabled?: boolean;
}) {
  const [showLearned, setShowLearned] = useState(false);
  const [showGrocery, setShowGrocery] = useState(false);
  const [groceryText, setGroceryText] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  if (!data) return null;

  const run = async (tag: string, fn: () => Promise<any>) => {
    setBusy(tag);
    try {
      const res: any = await fn();
      if (res?.twin) onChange(res.twin);
      else if (res?.items) onChange({ ...data, grocery_list: res.items });
    } catch {
      // unchanged; they can try again
    } finally {
      setBusy(null);
    }
  };
  const openItems = data.grocery_list.filter((g) => !g.done).length;
  const notes = (["activity", "sleep"] as const).map((d) => data.notes?.[d]).filter((n): n is string => !!n);

  return (
    <Card style={styles.card} testID="twin-card">
      <View style={styles.head}>
        <Feather name="layers" size={15} color={colors.brandPrimary} />
        <AppText variant="label" color={colors.brandPrimary} style={{ fontSize: 13 }}>
          Your routines
        </AppText>
      </View>
      <AppText variant="caption" style={{ fontSize: 12, marginTop: -6 }}>
        Food, movement and sleep: what I&apos;ve noticed, and one small step at a time.
      </AppText>

      {!!data.notes?.paused && (
        <AppText variant="body" style={{ fontSize: 14 }} testID="twin-paused">
          {data.notes.paused}
        </AppText>
      )}

      {data.questions.length > 0 && (
        <View style={{ gap: spacing.sm }}>
          <AppText variant="label" style={{ fontSize: 13 }}>
            Is this right?
          </AppText>
          {data.questions.map((q) => (
            <QuestionBlock key={q.key} q={q} onDone={onChange} disabled={disabled} />
          ))}
        </View>
      )}

      {data.recommendations.length > 0 && (
        <View style={{ gap: spacing.sm }}>
          <AppText variant="label" style={{ fontSize: 13 }}>
            {data.recommendations.length > 1 ? "Small steps that fit your week" : "One small step"}
          </AppText>
          {data.recommendations.map((s) => (
            <StepBlock
              key={s.id}
              s={s}
              reasons={data.reasons}
              onDone={onChange}
              onAsk={onAsk}
              onGrocery={(id) => run(`grocery-${id}`, () => api.addGrocery({ rec_id: id }))}
              disabled={disabled}
            />
          ))}
        </View>
      )}

      {data.reinforcing.length > 0 && (
        <View style={{ gap: spacing.sm }} testID="twin-reinforcing">
          <AppText variant="label" style={{ fontSize: 13 }}>
            Keep going
          </AppText>
          {data.reinforcing.map((r) => (
            <View key={r.id} style={styles.keep} testID={`twin-keep-${r.id}`}>
              <Feather name="check-circle" size={15} color={colors.success} style={{ marginTop: 2 }} />
              <View style={{ flex: 1, gap: 4 }}>
                <AppText variant="label" style={{ fontSize: 14 }}>
                  {r.title}
                </AppText>
                <AppText variant="caption" style={{ fontSize: 12 }}>
                  {r.message}
                </AppText>
                {r.check_in && (
                  <View style={styles.row}>
                    <AppText variant="caption" style={{ flex: 1 }}>
                      Still doing it?
                    </AppText>
                    <Button
                      title="Yes"
                      variant="secondary"
                      onPress={() => run(`keep-${r.id}`, () => api.respondTwinStep({ rec_id: r.id, response: "still_doing" }))}
                      loading={busy === `keep-${r.id}`}
                      disabled={disabled}
                      testID={`twin-still-${r.id}`}
                    />
                    <Button
                      title="Not lately"
                      variant="ghost"
                      onPress={() => run(`keep-${r.id}`, () => api.respondTwinStep({ rec_id: r.id, response: "lapsed" }))}
                      disabled={disabled || busy === `keep-${r.id}`}
                      testID={`twin-lapsed-${r.id}`}
                    />
                  </View>
                )}
              </View>
            </View>
          ))}
        </View>
      )}

      {data.offer_domains.length > 0 && !data.paused && (
        <View style={{ gap: 6 }}>
          <AppText variant="caption" style={{ fontSize: 12 }}>
            Want help with {data.offer_domains.map((d) => (d === "activity" ? "movement" : "sleep")).join(" or ")} too?
          </AppText>
          <View style={styles.chips}>
            {data.offer_domains.map((d) => (
              <Pressable
                key={d}
                onPress={() => run(`domain-${d}`, () => api.setTwinDomain(d))}
                style={styles.chip}
                disabled={disabled || busy === `domain-${d}`}
                testID={`twin-domain-${d}`}
              >
                <AppText variant="caption" color={colors.onSurfaceSecondary} style={{ fontSize: 12 }}>
                  {d === "activity" ? "Yes, movement" : "Yes, sleep"}
                </AppText>
              </Pressable>
            ))}
          </View>
        </View>
      )}

      {notes.length > 0 && (
        <View style={{ gap: 2 }}>
          {notes.map((n) => (
            <AppText key={n} variant="caption" style={{ fontSize: 11 }}>
              {n}
            </AppText>
          ))}
        </View>
      )}

      <Pressable onPress={() => setShowLearned(!showLearned)} style={styles.toggle} testID="twin-learned-toggle">
        <Feather name={showLearned ? "chevron-down" : "chevron-right"} size={14} color={colors.muted} />
        <AppText variant="label" style={{ fontSize: 13 }}>
          What I&apos;ve learned about you ({data.learned.length})
        </AppText>
      </Pressable>
      {showLearned && (
        <View style={{ gap: 6 }} testID="twin-learned">
          {data.learned.length === 0 && <AppText variant="caption">Nothing yet. Answer a question above and it shows up here.</AppText>}
          {data.learned.map((l) => (
            <View key={l.key} style={styles.learnedRow}>
              <View style={{ flex: 1 }}>
                <AppText variant="body" style={{ fontSize: 13 }}>
                  {l.label}
                </AppText>
                <AppText variant="caption" style={{ fontSize: 11 }}>
                  {l.source}
                </AppText>
              </View>
              <Pressable
                onPress={() => run(`forget-${l.key}`, () => api.removeTwinLearned(l.key))}
                hitSlop={8}
                accessibilityLabel={`Remove: ${l.label}`}
                disabled={disabled || busy === `forget-${l.key}`}
                testID={`twin-forget-${l.key}`}
              >
                <AppText variant="caption" color={colors.brandPrimary} style={{ fontSize: 12 }}>
                  Not right
                </AppText>
              </Pressable>
            </View>
          ))}
        </View>
      )}

      <Pressable onPress={() => setShowGrocery(!showGrocery)} style={styles.toggle} testID="twin-grocery-toggle">
        <Feather name={showGrocery ? "chevron-down" : "chevron-right"} size={14} color={colors.muted} />
        <AppText variant="label" style={{ fontSize: 13 }}>
          Grocery list{openItems ? ` (${openItems})` : ""}
        </AppText>
      </Pressable>
      {showGrocery && (
        <View style={{ gap: 6 }} testID="twin-grocery">
          {data.grocery_list.map((g) => (
            <View key={g.id} style={styles.learnedRow}>
              <Pressable
                onPress={() => run(`g-${g.id}`, () => api.setGroceryDone(g.id, !g.done))}
                style={[styles.row, { flex: 1 }]}
                accessibilityRole="checkbox"
                accessibilityState={{ checked: g.done }}
                testID={`twin-grocery-item-${g.id}`}
              >
                <Feather name={g.done ? "check-square" : "square"} size={16} color={g.done ? colors.success : colors.muted} />
                <AppText variant="body" style={[{ fontSize: 13, flex: 1 }, g.done && { textDecorationLine: "line-through", color: colors.muted }]}>
                  {g.text}
                </AppText>
              </Pressable>
              <Pressable onPress={() => run(`g-${g.id}`, () => api.removeGrocery(g.id))} hitSlop={8} accessibilityLabel={`Remove ${g.text}`} testID={`twin-grocery-remove-${g.id}`}>
                <Feather name="x" size={15} color={colors.muted} />
              </Pressable>
            </View>
          ))}
          <View style={styles.row}>
            <TextInput
              value={groceryText}
              onChangeText={setGroceryText}
              placeholder="Add an item"
              placeholderTextColor={colors.muted}
              style={[styles.input, { flex: 1 }]}
              maxLength={80}
              testID="twin-grocery-input"
            />
            <Button
              title="Add"
              variant="secondary"
              onPress={() => {
                const t = groceryText.trim();
                if (!t) return;
                setGroceryText("");
                run("g-add", () => api.addGrocery({ text: t }));
              }}
              loading={busy === "g-add"}
              testID="twin-grocery-add"
            />
          </View>
        </View>
      )}
    </Card>
  );
}

const styles = StyleSheet.create({
  card: { gap: spacing.md, padding: spacing.lg },
  head: { flexDirection: "row", alignItems: "center", gap: 6 },
  block: { gap: 6, paddingTop: spacing.sm, borderTopWidth: 1, borderTopColor: colors.divider },
  tags: { flexDirection: "row", flexWrap: "wrap", gap: 4 },
  tag: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: radius.pill },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
  chip: {
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surfaceSecondary,
  },
  chipOn: { backgroundColor: colors.surfaceInverse, borderColor: colors.surfaceInverse },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  why: { flexDirection: "row", gap: 6, alignItems: "flex-start" },
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
  panel: { gap: spacing.sm, padding: spacing.md, borderRadius: radius.md, backgroundColor: colors.surfaceTertiary },
  input: {
    minHeight: 40,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surfaceSecondary,
    paddingHorizontal: 12,
    paddingVertical: 8,
    fontFamily: fonts.regular,
    fontSize: 14,
    color: colors.onSurface,
  },
  link: { flexDirection: "row", alignItems: "center", gap: 5, paddingTop: 2 },
  keep: { flexDirection: "row", gap: spacing.sm, alignItems: "flex-start" },
  toggle: { flexDirection: "row", alignItems: "center", gap: 6, paddingTop: spacing.xs },
  learnedRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
});
