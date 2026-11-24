import React, { useEffect } from "react";
import { View, StyleSheet } from "react-native";
import Svg, { Circle, Line } from "react-native-svg";
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withTiming,
  withSequence,
  withDelay,
  Easing,
  runOnJS,
} from "react-native-reanimated";
import { colors } from "@/src/theme";
import { useReducedMotion } from "@/src/hooks/use-reduced-motion";

/**
 * "My Path" — the single, consistent trail/milestone avatar (per the
 * 9/10/26 deck: "Avatar's appearance never changes, only position on the
 * path... Milestones labeled by specific behavior built, never a health
 * outcome or prediction"). This replaces the retired LE8-style single
 * 0-100 score gauge entirely — there is no overall score to render here,
 * only a position (0..1) along a trail and a fixed-appearance marker.
 */
export function PathTrail({
  position,
  milestoneCount = 6,
  size = 260,
}: {
  position: number; // 0..1
  milestoneCount?: number;
  size?: number;
}) {
  const height = 64;
  const pad = 20;
  const trackY = height / 2;
  const pct = Math.max(0, Math.min(1, position));
  const markerX = pad + pct * (size - pad * 2);

  const dots = Array.from({ length: milestoneCount }, (_, i) => {
    const t = i / (milestoneCount - 1);
    return { x: pad + t * (size - pad * 2), achieved: t <= pct + 0.001 };
  });

  return (
    <View style={{ width: size, height, alignItems: "center", justifyContent: "center" }}>
      <Svg width={size} height={height}>
        <Line x1={pad} y1={trackY} x2={size - pad} y2={trackY} stroke={colors.surfaceTertiary} strokeWidth={4} strokeLinecap="round" />
        <Line x1={pad} y1={trackY} x2={markerX} y2={trackY} stroke={colors.brandPrimary} strokeWidth={4} strokeLinecap="round" />
        {dots.map((d, i) => (
          <Circle
            key={i}
            cx={d.x}
            cy={trackY}
            r={5}
            fill={d.achieved ? colors.brandPrimary : colors.surfaceTertiary}
          />
        ))}
        {/* Fixed-appearance avatar marker — only its position ever changes. */}
        <Circle cx={markerX} cy={trackY} r={11} fill={colors.onSurface} />
        <Circle cx={markerX} cy={trackY} r={5} fill={colors.surface} />
      </Svg>
    </View>
  );
}

/**
 * Non-variable process reward (REQ-GAM-02).
 * Same trigger -> same fixed response, EVERY time. No randomized intensity/rarity.
 */
const FIXED_PARTICLES = [
  { x: -60, y: -70 },
  { x: 60, y: -70 },
  { x: -80, y: -10 },
  { x: 80, y: -10 },
  { x: 0, y: -95 },
  { x: -30, y: -50 },
  { x: 30, y: -50 },
];

function Particle({ dx, dy, trigger }: { dx: number; dy: number; trigger: number }) {
  const p = useSharedValue(0);
  useEffect(() => {
    p.value = 0;
    p.value = withTiming(1, { duration: 700, easing: Easing.out(Easing.cubic) });
  }, [trigger]);
  const style = useAnimatedStyle(() => ({
    transform: [{ translateX: dx * p.value }, { translateY: dy * p.value }, { scale: 1 - p.value * 0.6 }],
    opacity: 1 - p.value,
  }));
  return <Animated.View style={[styles.particle, style]} />;
}

export function RewardBurst({ trigger, onDone }: { trigger: number; onDone?: () => void }) {
  const wrap = useSharedValue(0);
  const reducedMotion = useReducedMotion();

  useEffect(() => {
    if (trigger === 0) return;
    if (reducedMotion) {
      // PRD §14.4 hard override: skip the particle animation entirely.
      // The burst is decorative confirmation of an action already
      // reflected elsewhere in state — nothing informational is lost by
      // not animating it, so the static equivalent is simply "no burst."
      onDone?.();
      return;
    }
    wrap.value = withSequence(
      withTiming(1, { duration: 200 }),
      withDelay(500, withTiming(0, { duration: 200 }, (f) => {
        if (f && onDone) runOnJS(onDone)();
      }))
    );
  }, [trigger, reducedMotion]);
  const wrapStyle = useAnimatedStyle(() => ({ opacity: wrap.value }));
  if (trigger === 0 || reducedMotion) return null;
  return (
    <View pointerEvents="none" style={styles.burstWrap} testID="reward-burst">
      <Animated.View style={[styles.burstCenter, wrapStyle]}>
        {FIXED_PARTICLES.map((pt, i) => (
          <Particle key={i} dx={pt.x} dy={pt.y} trigger={trigger} />
        ))}
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  burstWrap: { ...StyleSheet.absoluteFillObject, alignItems: "center", justifyContent: "center", zIndex: 50 },
  burstCenter: { position: "absolute", alignItems: "center", justifyContent: "center" },
  particle: {
    position: "absolute",
    width: 12,
    height: 12,
    borderRadius: 6,
    backgroundColor: colors.brand,
  },
});
