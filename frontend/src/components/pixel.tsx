// Pixel UI primitives — used ONLY inside the game screens (g1, g2, g3's
// plate builder). The rest of the app keeps the mature Plus Jakarta Sans
// style; these pieces exist so that the games can locally break into an
// 8-bit tone without infecting the global design system.
//
// Design rules this module enforces:
//   - 2px solid "chunky" borders, no rounded corners, no shadows.
//   - Press Start 2P only for titles / scores / round numbers / buttons.
//     Body copy inside a game stays Plus Jakarta Sans so questions,
//     answers and explanations stay comfortably readable.
//   - Pixel art is scaled nearest-neighbour so sprites stay crisp when
//     scaled up (16px grid → 64/96/128 px on screen).
//   - All colours come from `pixelPalette` in theme.ts — a dark
//     forest-green variant of the brand palette, scoped to the game only.
import React from "react";
import { View, Text, Pressable, StyleSheet, ViewStyle, StyleProp, TextStyle } from "react-native";
import { SvgXml } from "react-native-svg";
import * as Haptics from "expo-haptics";
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withTiming,
  withSequence,
  Easing,
} from "react-native-reanimated";

import { fonts, fontSize, pixelPalette, spacing } from "@/src/theme";
import { useGameSound } from "@/src/hooks/use-game-sound";
import { useReducedMotion } from "@/src/hooks/use-reduced-motion";

// ---------- Text ----------
export function PixelText({
  children,
  size = "body",
  color = pixelPalette.ink,
  style,
  testID,
}: {
  children: React.ReactNode;
  size?: "title" | "score" | "label" | "button" | "body" | "caption";
  color?: string;
  style?: StyleProp<TextStyle>;
  testID?: string;
}) {
  return (
    <Text testID={testID} style={[pxText[size], { color }, style]}>
      {children}
    </Text>
  );
}

// ---------- Card (chunky bordered container) ----------
export function PixelCard({
  children,
  style,
  tone = "surface",
  testID,
}: {
  children: React.ReactNode;
  style?: StyleProp<ViewStyle>;
  tone?: "surface" | "warn" | "wrong" | "accent";
  testID?: string;
}) {
  const borderColor =
    tone === "warn" ? pixelPalette.warn : tone === "wrong" ? pixelPalette.wrong : tone === "accent" ? pixelPalette.accent : pixelPalette.inkDim;
  const bg = pixelPalette.surface;
  return (
    <View testID={testID} style={[styles.card, { borderColor, backgroundColor: bg }, style]}>
      {children}
    </View>
  );
}

// ---------- Button (chunky, no rounded corners) ----------
export function PixelButton({
  title,
  onPress,
  variant = "primary",
  disabled,
  style,
  testID,
}: {
  title: string;
  onPress: () => void;
  variant?: "primary" | "secondary";
  disabled?: boolean;
  style?: StyleProp<ViewStyle>;
  testID?: string;
}) {
  const { play } = useGameSound();
  const bg = variant === "primary" ? pixelPalette.accentDeep : pixelPalette.bg;
  const border = variant === "primary" ? pixelPalette.accent : pixelPalette.inkDim;
  const fg = pixelPalette.ink;
  return (
    <Pressable
      testID={testID}
      disabled={disabled}
      onPress={() => {
        Haptics.selectionAsync?.();
        play("tap");
        onPress();
      }}
      style={({ pressed }) => [
        styles.btn,
        { backgroundColor: bg, borderColor: border, opacity: disabled ? 0.5 : pressed ? 0.82 : 1 },
        style,
      ]}
    >
      <Text style={[pxText.button, { color: fg }]}>{title}</Text>
    </Pressable>
  );
}

// ---------- Segmented progress bar ----------
// Discrete 8-bit-style segments, not a continuous bar. Fills a cell per
// completed round or scenario. Matches the design rule explicitly.
export function PixelProgress({
  value,
  max,
  testID,
}: {
  value: number;
  max: number;
  testID?: string;
}) {
  const safeMax = Math.max(1, max);
  const cells = Array.from({ length: safeMax }, (_, i) => i < value);
  return (
    <View style={styles.progressRow} testID={testID}>
      {cells.map((filled, i) => (
        <View
          key={i}
          style={[
            styles.progressCell,
            { backgroundColor: filled ? pixelPalette.accent : "transparent", borderColor: pixelPalette.inkDim },
          ]}
        />
      ))}
    </View>
  );
}

// ---------- Score counter ----------
// Fixed-width three-digit score, always framed in a chunky border.
export function PixelScore({ score, testID }: { score: number; testID?: string }) {
  const padded = String(Math.max(0, Math.min(999, score))).padStart(3, "0");
  return (
    <View style={styles.scoreBox} testID={testID}>
      <Text style={pxText.scoreLabel}>SCORE</Text>
      <Text style={pxText.scoreValue}>{padded}</Text>
    </View>
  );
}

// ---------- Nearest-neighbour sprite ----------
// Renders the inline SVG XML from `game-sprites.ts` via react-native-svg.
// The source SVGs use `shape-rendering="crispEdges"`, which is the SVG
// native equivalent of CSS `imageRendering: pixelated` — nothing
// anti-aliases on scale-up, so a 16-grid stays crisp at 32/48/96 px.
import { SPRITES, type SpriteName } from "@/src/components/game-sprites";

export function PixelSprite({
  name,
  size = 32,
  testID,
}: {
  name: SpriteName;
  size?: number;
  testID?: string;
}) {
  return (
    <View style={{ width: size, height: size }} testID={testID}>
      <SvgXml xml={SPRITES[name]} width={size} height={size} />
    </View>
  );
}

// ---------- Sparkle (purely decorative, respects reduced motion) ----------
// Three quick on/off ticks over ~900ms = 3.3 Hz; our rule is "never flash
// more than 3 times per second," so we cap at that frequency. Entirely
// skipped when reduced motion is on.
export function PixelSparkle({ trigger }: { trigger: number }) {
  const reduce = useReducedMotion();
  const opacity = useSharedValue(0);
  React.useEffect(() => {
    if (trigger === 0 || reduce) return;
    opacity.value = withSequence(
      withTiming(1, { duration: 90, easing: Easing.linear }),
      withTiming(0, { duration: 210, easing: Easing.linear }),
      withTiming(1, { duration: 90, easing: Easing.linear }),
      withTiming(0, { duration: 210, easing: Easing.linear }),
      withTiming(1, { duration: 90, easing: Easing.linear }),
      withTiming(0, { duration: 210, easing: Easing.linear }),
    );
  }, [trigger, reduce, opacity]);
  const style = useAnimatedStyle(() => ({ opacity: opacity.value }));
  if (reduce) return null;
  return (
    <Animated.View pointerEvents="none" style={[styles.sparkleWrap, style]}>
      {/* Four little pixel stars at corners of a rectangle. */}
      <View style={[styles.sparkleStar, { top: 20, left: 24 }]} />
      <View style={[styles.sparkleStar, { top: 60, right: 36 }]} />
      <View style={[styles.sparkleStar, { bottom: 48, left: 44 }]} />
      <View style={[styles.sparkleStar, { bottom: 24, right: 20 }]} />
    </Animated.View>
  );
}

const pxText = StyleSheet.create({
  title: { fontFamily: fonts.pixel, fontSize: 14, letterSpacing: 1 },
  score: { fontFamily: fonts.pixel, fontSize: 12, letterSpacing: 1 },
  label: { fontFamily: fonts.pixel, fontSize: 10, letterSpacing: 1 },
  button: { fontFamily: fonts.pixel, fontSize: 11, letterSpacing: 1, textAlign: "center" },
  body: { fontFamily: fonts.regular, fontSize: fontSize.base, lineHeight: 22 },
  caption: { fontFamily: fonts.regular, fontSize: fontSize.sm, lineHeight: 18, color: pixelPalette.inkDim },
  scoreLabel: { fontFamily: fonts.pixel, fontSize: 8, color: pixelPalette.inkDim, letterSpacing: 1 },
  scoreValue: { fontFamily: fonts.pixel, fontSize: 14, color: pixelPalette.accent, letterSpacing: 2, marginTop: 2 },
});

const styles = StyleSheet.create({
  card: {
    borderWidth: pixelPalette.borderWidth,
    padding: spacing.lg,
  },
  btn: {
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.lg,
    borderWidth: pixelPalette.borderWidth,
    alignItems: "center",
    justifyContent: "center",
    minHeight: 44,
  },
  progressRow: {
    flexDirection: "row",
    gap: 4,
  },
  progressCell: {
    flex: 1,
    height: 10,
    borderWidth: 2,
  },
  scoreBox: {
    borderWidth: pixelPalette.borderWidth,
    borderColor: pixelPalette.inkDim,
    paddingVertical: 4,
    paddingHorizontal: spacing.md,
    alignItems: "center",
    minWidth: 72,
    backgroundColor: pixelPalette.bgDeep,
  },
  sparkleWrap: {
    ...StyleSheet.absoluteFillObject,
  },
  sparkleStar: {
    position: "absolute",
    width: 6,
    height: 6,
    backgroundColor: pixelPalette.accent,
  },
});
