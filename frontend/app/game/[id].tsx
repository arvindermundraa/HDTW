// Game screen — the one place in the LLHS app that steps outside the
// mature Plus Jakarta Sans style and plays like a tiny retro pixel game.
// Everything OUTSIDE this screen (the Learn tab's game cards, Settings,
// profile, etc.) stays on the normal design. Rules the design enforces:
//
//   - Press Start 2P is used ONLY for titles, score, round numbers and
//     buttons. Questions, answers and explanations stay on Plus Jakarta
//     Sans at normal size so they're easy to read.
//   - Chunky 2px pixel borders around cards and buttons. No shadows,
//     no rounded corners inside a game.
//   - 8-bit segmented progress bar (not continuous).
//   - Pixel sprites render nearest-neighbour so they stay crisp.
//   - Dark forest-green palette (`pixelPalette` in theme.ts).
//   - Short 8-bit sound effects, same sound every time for an event.
//     Mute button in the header and a Settings switch — both share the
//     same persisted preference.
//   - No lives, no "Game Over" screen, no timer pressure. A wrong answer
//     shows the one-line explanation and a Try again / Next button.
//   - End-of-round screen is "Round complete!" with the fixed point award.
//   - Sparkles on correct answers; disabled under reduced motion. Never
//     flashes more than 3× per second.
import React, { useEffect, useMemo, useRef, useState } from "react";
import { View, StyleSheet, Pressable, ActivityIndicator, ScrollView } from "react-native";
import Animated, { FadeIn, Easing, useAnimatedStyle, useSharedValue, withTiming } from "react-native-reanimated";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Feather } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import { api } from "@/src/api";
import { goBack } from "@/src/navigation";
import { fonts, pixelPalette, spacing } from "@/src/theme";
import {
  PixelButton,
  PixelCard,
  PixelProgress,
  PixelScore,
  PixelSparkle,
  PixelSprite,
  PixelText,
} from "@/src/components/pixel";
import { useGameSound, useGameSoundEnabled } from "@/src/hooks/use-game-sound";
import { useReducedMotion } from "@/src/hooks/use-reduced-motion";

type Choice = { id: string; text: string; correct?: boolean; feedback: string; marker?: string };
type Scenario = { id: string; prompt: string; choices: Choice[] };
type Round = { id: string; title: string; scenarios: Scenario[] };
type Game = {
  id: string;
  title: string;
  rehearses: string;
  points: number;
  type?: "plate_builder";
  rounds?: Round[];
  scenarios?: Scenario[]; // legacy flat fallback
};

// A tiny deterministic sprite rotation per scenario — same scenario id
// always gets the same decorative sprite. Not variable rewards: it's
// stable per content, not per answer.
import { spriteNames, type SpriteName } from "@/src/components/game-sprites";
const SCENARIO_SPRITE_POOL: SpriteName[] = [
  "apple", "carrot", "broccoli", "egg", "rice-bowl",
  "bread", "fish", "cheese", "water", "salad",
];

function hashString(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) & 0xffffffff;
  return Math.abs(h);
}

function spriteFor(scenarioId: string | undefined): SpriteName {
  return SCENARIO_SPRITE_POOL[hashString(scenarioId || "x") % SCENARIO_SPRITE_POOL.length];
}

export default function GameScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const [game, setGame] = useState<Game | null>(null);

  useEffect(() => {
    api.getGames().then((list: Game[]) => setGame(list.find((g) => g.id === id) || null));
  }, [id]);

  if (!game) {
    return (
      <View style={[styles.c, styles.center]}>
        <ActivityIndicator color={pixelPalette.accent} />
      </View>
    );
  }

  // Plate builder has its own screen chrome — we lazy-load the old module
  // and just repaint its chrome in pixel style via a small wrapper.
  if (game.type === "plate_builder") {
    return <PlateBuilderGameWrapper gameId={game.id} title={game.title} />;
  }

  return <ScenarioGame game={game} />;
}

// --------------------------------------------------------------------------
// Scenario game (g1, g2) — rounds of multiple-choice questions with instant
// per-answer feedback and no fail state.
// --------------------------------------------------------------------------
function ScenarioGame({ game }: { game: Game }) {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const reduce = useReducedMotion();
  const { play } = useGameSound();
  const [enabled, setEnabled] = useGameSoundEnabled();

  // Normalize into rounds — older game payloads expose a flat scenarios
  // list; we wrap it in a single "Round 1" so the code only ever walks
  // rounds[].
  const rounds: Round[] = useMemo(() => {
    if (game.rounds?.length) return game.rounds;
    return [{ id: "r1", title: "Round 1", scenarios: game.scenarios || [] }];
  }, [game]);

  const [roundIdx, setRoundIdx] = useState(0);
  const [scenarioIdx, setScenarioIdx] = useState(0);
  const [chosen, setChosen] = useState<Choice | null>(null);
  const [markers, setMarkers] = useState<string[]>([]);
  const [score, setScore] = useState(0);
  const [sparkle, setSparkle] = useState(0);
  const [roundDone, setRoundDone] = useState(false);
  const [gameDone, setGameDone] = useState(false);
  const [awarded, setAwarded] = useState(0);

  const round = rounds[roundIdx];
  const scenario = round?.scenarios[scenarioIdx];

  const choose = (choice: Choice) => {
    if (chosen) return;
    setChosen(choice);
    if (choice.marker) setMarkers((m) => [...m, choice.marker!]);
    if (choice.correct) {
      setScore((s) => s + 1);
      setSparkle((n) => n + 1);
      play("correct");
      if (!reduce) Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    } else {
      play("notQuite");
      // No harsh haptic — soft light impact matches the "not quite" tone.
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    }
  };

  const next = async () => {
    const isLastInRound = scenarioIdx + 1 >= round.scenarios.length;
    const isLastRound = roundIdx + 1 >= rounds.length;
    setChosen(null);
    if (!isLastInRound) {
      setScenarioIdx((i) => i + 1);
      return;
    }
    // End of this round.
    if (!isLastRound) {
      play("roundComplete");
      setRoundDone(true);
      return;
    }
    // End of game — hit backend for the fixed point award, then show the
    // "Round complete!" summary screen (the design calls the summary a
    // "round complete" screen for all games, including the final one).
    play("gameComplete");
    try {
      const res = await api.completeGame(game.id, markers, score);
      setAwarded(res.points_awarded ?? 0);
    } catch {
      setAwarded(0);
    }
    setGameDone(true);
  };

  const tryAgain = () => {
    play("tap");
    setChosen(null);
  };

  const toNextRound = () => {
    setRoundDone(false);
    setRoundIdx((i) => i + 1);
    setScenarioIdx(0);
    setChosen(null);
  };

  if (gameDone) {
    return <RoundCompleteScreen title="GAME COMPLETE!" points={awarded} score={score} total={totalScenarios(rounds)} onExit={() => goBack(router, "/learn")} />;
  }

  if (roundDone) {
    return (
      <RoundCompleteScreen
        title="ROUND COMPLETE!"
        points={0}
        score={score}
        total={totalScenarios(rounds)}
        continueLabel="Next round"
        onExit={toNextRound}
      />
    );
  }

  const totalInRound = round.scenarios.length;
  return (
    <View style={[styles.c, { paddingTop: insets.top + spacing.sm }]} testID="game-screen">
      <PixelSparkle trigger={sparkle} />
      <View style={styles.header}>
        <Pressable onPress={() => goBack(router, "/learn")} hitSlop={12} testID="game-close">
          <Feather name="x" size={22} color={pixelPalette.ink} />
        </Pressable>
        <View style={{ flex: 1, marginHorizontal: spacing.md }}>
          <PixelText size="label" color={pixelPalette.inkDim}>
            {`ROUND ${roundIdx + 1} / ${rounds.length}`}
          </PixelText>
          <View style={{ height: 6 }} />
          <PixelProgress value={scenarioIdx + (chosen ? 1 : 0)} max={totalInRound} />
        </View>
        <Pressable
          onPress={() => setEnabled(!enabled)}
          hitSlop={12}
          testID="game-mute"
          style={styles.muteBtn}
        >
          <Feather name={enabled ? "volume-2" : "volume-x"} size={18} color={pixelPalette.ink} />
        </Pressable>
        <View style={{ width: spacing.md }} />
        <PixelScore score={score} testID="game-score" />
      </View>

      <ScrollView contentContainerStyle={styles.body} showsVerticalScrollIndicator={false}>
        <View style={styles.titleRow}>
          <PixelSprite name={spriteFor(scenario?.id)} size={48} />
          <View style={{ flex: 1, marginLeft: spacing.md }}>
            <PixelText size="label" color={pixelPalette.accent}>
              {game.title.toUpperCase()}
            </PixelText>
            <PixelText size="title" style={{ marginTop: 6 }}>
              {round.title.toUpperCase()}
            </PixelText>
          </View>
        </View>

        <PixelCard style={{ marginTop: spacing.xl }}>
          {/* Prompt stays in Plus Jakarta Sans so it's easy to read. */}
          <PixelText size="body" style={styles.prompt}>
            {scenario?.prompt}
          </PixelText>
        </PixelCard>

        <View style={{ marginTop: spacing.lg, gap: spacing.md }}>
          {scenario?.choices.map((c) => {
            const isChosen = chosen?.id === c.id;
            const showState = !!chosen;
            const isCorrect = !!c.correct;
            const tone =
              showState && isCorrect ? "accent" : showState && isChosen && !isCorrect ? "wrong" : "surface";
            return (
              <Pressable
                key={c.id}
                testID={`choice-${c.id}`}
                onPress={() => choose(c)}
                disabled={showState}
              >
                <PixelCard tone={tone as any}>
                  <View style={styles.choiceRow}>
                    <PixelText size="body" style={{ flex: 1 }}>
                      {c.text}
                    </PixelText>
                    {showState && isCorrect && (
                      <Feather name="check" size={18} color={pixelPalette.accent} style={{ marginLeft: spacing.sm }} />
                    )}
                    {showState && isChosen && !isCorrect && (
                      <Feather name="x" size={18} color={pixelPalette.wrong} style={{ marginLeft: spacing.sm }} />
                    )}
                  </View>
                </PixelCard>
              </Pressable>
            );
          })}
        </View>

        {chosen && (
          <Animated.View entering={reduce ? undefined : FadeIn.duration(260)}>
            <PixelCard
              style={{ marginTop: spacing.lg }}
              tone={chosen.correct ? "accent" : "warn"}
              testID="choice-feedback"
            >
              <PixelText size="label" color={chosen.correct ? pixelPalette.accent : pixelPalette.warn}>
                {chosen.correct ? "CORRECT" : "NOT QUITE"}
              </PixelText>
              <PixelText size="body" style={{ marginTop: spacing.sm }}>
                {chosen.feedback}
              </PixelText>
            </PixelCard>
          </Animated.View>
        )}
        <View style={{ height: spacing["3xl"] }} />
      </ScrollView>

      {chosen && (
        <View style={[styles.footer, { paddingBottom: insets.bottom + spacing.lg }]}>
          {chosen.correct ? (
            <PixelButton
              title={scenarioIdx + 1 < totalInRound ? "NEXT" : roundIdx + 1 < rounds.length ? "FINISH ROUND" : "FINISH"}
              onPress={next}
              testID="game-continue"
            />
          ) : (
            // No fail state — give the player both options so they can learn
            // from the explanation and move on, or retry the question.
            <View style={{ flexDirection: "row", gap: spacing.md }}>
              <PixelButton title="TRY AGAIN" variant="secondary" onPress={tryAgain} style={{ flex: 1 }} testID="game-retry" />
              <PixelButton
                title={scenarioIdx + 1 < totalInRound ? "NEXT" : "FINISH"}
                onPress={next}
                style={{ flex: 1 }}
                testID="game-continue"
              />
            </View>
          )}
        </View>
      )}
    </View>
  );
}

function totalScenarios(rounds: Round[]): number {
  return rounds.reduce((n, r) => n + r.scenarios.length, 0);
}

function RoundCompleteScreen({
  title,
  points,
  score,
  total,
  continueLabel = "Back to Learn",
  onExit,
}: {
  title: string;
  points: number;
  score: number;
  total: number;
  continueLabel?: string;
  onExit: () => void;
}) {
  const insets = useSafeAreaInsets();
  return (
    <View style={[styles.c, styles.center, { paddingTop: insets.top }]} testID="game-done">
      <PixelSprite name="apple" size={96} />
      <PixelText size="title" color={pixelPalette.accent} style={{ marginTop: spacing.xl, textAlign: "center" }}>
        {title}
      </PixelText>
      <PixelText size="body" style={{ marginTop: spacing.md, textAlign: "center", color: pixelPalette.inkDim }}>
        {`You got ${score} of ${total} on point. Nice work practicing this.`}
      </PixelText>
      {points > 0 && (
        <View style={{ marginTop: spacing.xl }}>
          <PixelText size="score" color={pixelPalette.accent}>
            +{points} POINTS
          </PixelText>
        </View>
      )}
      <View style={{ height: spacing["3xl"] }} />
      <PixelButton title={continueLabel.toUpperCase()} onPress={onExit} style={{ paddingHorizontal: spacing["3xl"] }} testID="game-finish" />
    </View>
  );
}

// --------------------------------------------------------------------------
// Plate Builder wrapper — the g3 flow has rich drag-and-drop logic in the
// legacy PlateBuilder module; we keep that logic and just repaint the
// chrome with pixel-style primitives. Keeping the existing api/data flow
// avoids re-doing allergy filtering, dining-hall sub-mode, etc.
// --------------------------------------------------------------------------
import { DraggableChip, PlateZone, useMeasuredPlateRef, Ingredient } from "@/src/components/PlateBuilder";

function PlateBuilderGameWrapper({ gameId, title }: { gameId: string; title: string }) {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const reduce = useReducedMotion();
  const { play } = useGameSound();
  const [enabled, setEnabled] = useGameSoundEnabled();

  const [loading, setLoading] = useState(true);
  const [ingredients, setIngredients] = useState<any[]>([]);
  const [rounds, setRounds] = useState<any[]>([]);
  const [roundIdx, setRoundIdx] = useState(0);
  const [plateIds, setPlateIds] = useState<string[]>([]);
  const [feedback, setFeedback] = useState<any>(null);
  const [scoring, setScoring] = useState(false);
  const [score, setScore] = useState(0);
  const [sparkle, setSparkle] = useState(0);
  const [done, setDone] = useState(false);
  const [awarded, setAwarded] = useState(0);
  const [markers, setMarkers] = useState<string[]>([]);
  // Practical filters (study team feedback 2.2): time, budget, kitchen.
  const [quick, setQuick] = useState(false);
  const [budget, setBudget] = useState(false);
  const [tools, setTools] = useState<string[] | null>(null); // null = any kitchen

  const plateRef = useMeasuredPlateRef();

  useEffect(() => {
    api
      .getIngredients()
      .then((d) => {
        setIngredients(d?.ingredients || []);
        setRounds(d?.rounds || []);
      })
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <View style={[styles.c, styles.center]}>
        <ActivityIndicator color={pixelPalette.accent} />
      </View>
    );
  }

  const round = rounds[roundIdx];
  const inRound: Ingredient[] = round ? ingredients.filter((i) => round.ingredient_ids.includes(i.id)) : [];
  const fits = (i: any) =>
    (!quick || (i.prep_minutes ?? 0) <= 10) &&
    (!budget || i.cost !== "$$") &&
    (!tools || i.kitchen === "none" || tools.includes(i.kitchen));
  // Anything already on the plate stays visible even if a filter now hides it.
  const roundIngredients: Ingredient[] = inRound.filter((i) => fits(i) || plateIds.includes(i.id));
  const hiddenCount = inRound.length - roundIngredients.length;
  const toggleTool = (t: string) =>
    setTools((cur) => {
      if (t === "none") return cur && cur.length === 0 ? null : [];
      const base = cur ?? [];
      const next = base.includes(t) ? base.filter((x) => x !== t) : [...base, t];
      return next.length ? next : null;
    });
  const plateItems = roundIngredients.filter((i) => plateIds.includes(i.id));
  const minItems = round?.min_items ?? 2;
  const canScore = plateItems.length >= minItems && !scoring && !feedback;

  const addToPlate = (id: string) => {
    if (plateIds.includes(id)) return;
    if (round && plateIds.length >= round.max_items) return;
    play("tap");
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    setPlateIds((p) => [...p, id]);
  };

  const removeFromPlate = (id: string) => {
    play("tap");
    setPlateIds((p) => p.filter((x) => x !== id));
  };

  const scoreRound = async () => {
    if (!round) return;
    setScoring(true);
    try {
      const res = await api.scorePlate(round.id, plateIds);
      setFeedback(res);
      if (res.marker) setMarkers((m) => [...m, res.marker]);
      if (res.balanced) {
        setScore((n) => n + 1);
        setSparkle((n) => n + 1);
        play("correct");
      } else {
        play("notQuite");
      }
    } finally {
      setScoring(false);
    }
  };

  const nextRound = async () => {
    const isLast = roundIdx + 1 >= rounds.length;
    setFeedback(null);
    setPlateIds([]);
    if (!isLast) {
      setRoundIdx((i) => i + 1);
      return;
    }
    play("gameComplete");
    try {
      const res = await api.completeGame(gameId, markers, score);
      setAwarded(res.points_awarded ?? 0);
    } catch {
      setAwarded(0);
    }
    setDone(true);
  };

  if (done) {
    return (
      <RoundCompleteScreen
        title="GAME COMPLETE!"
        points={awarded}
        score={score}
        total={rounds.length}
        onExit={() => goBack(router, "/learn")}
      />
    );
  }

  return (
    <View style={[styles.c, { paddingTop: insets.top + spacing.sm }]} testID="plate-builder-screen">
      <PixelSparkle trigger={sparkle} />
      <View style={styles.header}>
        <Pressable onPress={() => goBack(router, "/learn")} hitSlop={12} testID="game-close">
          <Feather name="x" size={22} color={pixelPalette.ink} />
        </Pressable>
        <View style={{ flex: 1, marginHorizontal: spacing.md }}>
          <PixelText size="label" color={pixelPalette.inkDim}>
            {`ROUND ${roundIdx + 1} / ${rounds.length}`}
          </PixelText>
          <View style={{ height: 6 }} />
          <PixelProgress value={roundIdx + (feedback ? 1 : 0)} max={rounds.length} />
        </View>
        <Pressable
          onPress={() => setEnabled(!enabled)}
          hitSlop={12}
          testID="game-mute"
          style={styles.muteBtn}
        >
          <Feather name={enabled ? "volume-2" : "volume-x"} size={18} color={pixelPalette.ink} />
        </Pressable>
        <View style={{ width: spacing.md }} />
        <PixelScore score={score} />
      </View>

      <ScrollView contentContainerStyle={styles.body} showsVerticalScrollIndicator={false}>
        <View style={styles.titleRow}>
          <PixelSprite name="salad" size={48} />
          <View style={{ flex: 1, marginLeft: spacing.md }}>
            <PixelText size="label" color={pixelPalette.accent}>
              {title.toUpperCase()}
            </PixelText>
            <PixelText size="title" style={{ marginTop: 6 }}>
              {(round?.title || "").toUpperCase()}
            </PixelText>
          </View>
        </View>

        <PixelCard style={{ marginTop: spacing.lg }}>
          <PixelText size="body">{round?.constraint_note}</PixelText>
        </PixelCard>

        <View style={styles.filters} testID="plate-filters">
          {[
            { key: "quick", label: "UNDER 10 MIN", on: quick, press: () => setQuick((v) => !v) },
            { key: "budget", label: "BUDGET", on: budget, press: () => setBudget((v) => !v) },
            { key: "none", label: "NO KITCHEN", on: !!tools && tools.length === 0, press: () => toggleTool("none") },
            { key: "microwave", label: "MICROWAVE", on: !!tools?.includes("microwave"), press: () => toggleTool("microwave") },
            { key: "stove", label: "STOVE", on: !!tools?.includes("stove"), press: () => toggleTool("stove") },
            { key: "oven", label: "OVEN", on: !!tools?.includes("oven"), press: () => toggleTool("oven") },
          ].map((f) => (
            <Pressable
              key={f.key}
              onPress={f.press}
              style={[styles.filterChip, f.on && styles.filterChipOn]}
              accessibilityRole="switch"
              accessibilityState={{ checked: f.on }}
              testID={`plate-filter-${f.key}`}
            >
              <PixelText size="label" color={f.on ? pixelPalette.bg : pixelPalette.ink}>
                {f.label}
              </PixelText>
            </Pressable>
          ))}
        </View>
        {hiddenCount > 0 && (
          <PixelText size="label" color={pixelPalette.inkDim} style={{ marginTop: spacing.sm }}>
            {`${hiddenCount} HIDDEN BY FILTERS`}
          </PixelText>
        )}

        <View style={{ marginTop: spacing.xl }}>
          <PlateZone
            plateRef={plateRef}
            items={plateItems}
            onRemove={removeFromPlate}
            emptyLabel="Drag ingredients here, or tap one to add it"
          />
        </View>

        {/* Grouped by category (protein, grain, vegetable, fruit, dairy, other).
            Review notes called this out explicitly. */}
        {Object.entries(
          roundIngredients.reduce((acc: Record<string, Ingredient[]>, ing: any) => {
            const cat = ing.category || "other";
            (acc[cat] ||= []).push(ing);
            return acc;
          }, {})
        ).map(([category, items]) => (
          <View key={category} style={{ marginTop: spacing.xl }}>
            <PixelText size="label" color={pixelPalette.inkDim}>
              {category.toUpperCase()}
            </PixelText>
            <View style={styles.tray}>
              {items.map((ing) => (
                <DraggableChip
                  key={ing.id}
                  ingredient={ing}
                  plateRef={plateRef}
                  onAdd={addToPlate}
                  disabled={plateIds.includes(ing.id) || !!feedback}
                  reducedMotion={reduce}
                  testID={`ingredient-${ing.id}`}
                />
              ))}
            </View>
          </View>
        ))}

        {feedback && (
          <Animated.View entering={reduce ? undefined : FadeIn.duration(260)}>
            <PixelCard style={{ marginTop: spacing.xl }} tone={feedback.balanced ? "accent" : "warn"}>
              <PixelText size="label" color={feedback.balanced ? pixelPalette.accent : pixelPalette.warn}>
                {feedback.balanced ? "BALANCED PLATE" : "ROOM TO GROW"}
              </PixelText>
              <PixelText size="body" style={{ marginTop: spacing.sm }}>
                {feedback.feedback}
              </PixelText>
            </PixelCard>
          </Animated.View>
        )}

        <View style={{ height: spacing["3xl"] }} />
      </ScrollView>

      <View style={[styles.footer, { paddingBottom: insets.bottom + spacing.lg }]}>
        {feedback ? (
          <PixelButton title={roundIdx + 1 < rounds.length ? "NEXT ROUND" : "FINISH"} onPress={nextRound} testID="plate-continue" />
        ) : (
          <PixelButton title={scoring ? "REVIEWING…" : "SCORE PLATE"} onPress={scoreRound} disabled={!canScore} testID="plate-score" />
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  c: { flex: 1, backgroundColor: pixelPalette.bg },
  filters: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginTop: spacing.lg },
  filterChip: { paddingHorizontal: 10, paddingVertical: 8, borderWidth: 2, borderColor: pixelPalette.ink },
  filterChipOn: { backgroundColor: pixelPalette.accent, borderColor: pixelPalette.accent },
  center: { alignItems: "center", justifyContent: "center" },
  header: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.md,
    gap: spacing.sm,
  },
  muteBtn: {
    width: 32,
    height: 32,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: pixelPalette.borderWidth,
    borderColor: pixelPalette.inkDim,
    backgroundColor: pixelPalette.bgDeep,
  },
  body: { paddingHorizontal: spacing.lg, paddingTop: spacing.md },
  titleRow: { flexDirection: "row", alignItems: "center" },
  prompt: {
    color: pixelPalette.ink,
    fontFamily: fonts.semibold,
    fontSize: 16,
    lineHeight: 23,
  },
  choiceRow: { flexDirection: "row", alignItems: "center" },
  footer: {
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.md,
    borderTopWidth: pixelPalette.borderWidth,
    borderTopColor: pixelPalette.surfaceEdge,
    backgroundColor: pixelPalette.bg,
  },
  tray: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginTop: spacing.sm },
});
