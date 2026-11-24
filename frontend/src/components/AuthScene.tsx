import React, { useEffect, useMemo, useRef } from "react";
import { Animated, Easing, Platform, StyleSheet, View } from "react-native";
import { useScreenSize } from "@/src/components/PhoneFrame";
import Svg, { Circle, Ellipse, Path } from "react-native-svg";
import { LinearGradient } from "expo-linear-gradient";
import { useReducedMotion } from "@/src/hooks/use-reduced-motion";
import { AuthQuote } from "@/src/components/AuthQuotes";
import { VEGGIE_COMPONENTS } from "@/src/components/AuthVeggies";
import {
  FLOATERS, FloatSpec, SkyPalette, floatersFor, skyForHour, VeggieKey,
} from "@/src/components/auth-scene-helpers";
import { STUDY_TZ } from "@/src/study-time";

// Re-export for existing callers / tests that imported from the component.
export { FLOATERS, floatersFor, skyForHour };
export type { FloatSpec, SkyPalette, VeggieKey };

/**
 * The storybook landscape used across every auth screen (sign-in, sign-up,
 * verify-code, forgot-password / reset). Everything here is **original**
 * artwork drawn in-code as SVG + layered gradients — the brief explicitly
 * says do not copy any film studio's characters or scenes, so no imported
 * raster assets and no stylistic references to any protected work.
 *
 * Structure, back to front:
 *   1. Soft dawn / afternoon / evening sky gradient, tinted by the study
 *      clock (America/Chicago). Fallback to the dawn gradient off-TZ.
 *   2. Two layers of rolling hills (far hills paler and higher).
 *   3. A handful of simple clouds drifting slowly across the sky.
 *   4. A rotating line of encouragement (`AuthQuote`) in a calm sky area.
 *   5. Floating fruit/veg characters at different depths, bobbing gently.
 *   6. The form itself (passed as `children`) on top.
 *
 * Motion is strictly `transform` / `opacity` — Reanimated-via-Animated so
 * it drives the same spring on native and web. `useReducedMotion` kills
 * every animation and keeps the scene exactly where it would freeze.
 */

type Props = { children: React.ReactNode };

function studyHour(): number {
  // The study clock is Chicago — if `Intl.DateTimeFormat` can give us the
  // zone, use it; otherwise fall back to UTC which is still close enough
  // to pick the right palette.
  try {
    const parts = new Intl.DateTimeFormat("en-US", {
      timeZone: STUDY_TZ,
      hour: "2-digit",
      hourCycle: "h23",
    }).formatToParts(new Date());
    const h = Number(parts.find((p) => p.type === "hour")?.value ?? 0);
    return Number.isFinite(h) ? h : new Date().getUTCHours();
  } catch {
    return new Date().getUTCHours();
  }
}

/** Clouds drift horizontally; subtle, slow (30s) and always `transform` only. */
function Cloud({
  x,
  y,
  w,
  travel,
  duration,
  fill,
  delay = 0,
}: {
  x: number;
  y: number;
  w: number;
  travel: number;
  duration: number;
  fill: string;
  delay?: number;
}) {
  const reduced = useReducedMotion();
  const t = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    if (reduced) {
      t.setValue(0);
      return;
    }
    const native = Platform.OS !== "web";
    const anim = Animated.loop(
      Animated.sequence([
        Animated.delay(delay),
        Animated.timing(t, { toValue: 1, duration, easing: Easing.inOut(Easing.sin), useNativeDriver: native }),
        Animated.timing(t, { toValue: 0, duration, easing: Easing.inOut(Easing.sin), useNativeDriver: native }),
      ])
    );
    anim.start();
    return () => anim.stop();
  }, [reduced, t, duration, delay]);
  const translateX = t.interpolate({ inputRange: [0, 1], outputRange: [0, travel] });
  const h = w * 0.5;
  return (
    <Animated.View style={{ position: "absolute", left: x, top: y, width: w, height: h, transform: [{ translateX }] }}>
      <Svg width={w} height={h} viewBox="0 0 120 60">
        <Ellipse cx="38" cy="36" rx="22" ry="14" fill={fill} />
        <Ellipse cx="62" cy="30" rx="26" ry="18" fill={fill} />
        <Ellipse cx="86" cy="38" rx="22" ry="14" fill={fill} />
        <Ellipse cx="60" cy="42" rx="34" ry="12" fill={fill} />
      </Svg>
    </Animated.View>
  );
}

/** Each veggie bobs up and down a few pixels on its own long loop. */
function Floating({
  Component,
  size,
  left,
  top,
  amplitude,
  duration,
  delay,
  testID,
}: {
  Component: React.ComponentType<{ size?: number }>;
  size: number;
  left: number | string;
  top: number | string;
  amplitude: number;
  duration: number;
  delay: number;
  testID?: string;
}) {
  const reduced = useReducedMotion();
  const t = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    if (reduced) {
      t.setValue(0.5);
      return;
    }
    const native = Platform.OS !== "web";
    const anim = Animated.loop(
      Animated.sequence([
        Animated.delay(delay),
        Animated.timing(t, { toValue: 1, duration, easing: Easing.inOut(Easing.sin), useNativeDriver: native }),
        Animated.timing(t, { toValue: 0, duration, easing: Easing.inOut(Easing.sin), useNativeDriver: native }),
      ])
    );
    anim.start();
    return () => anim.stop();
  }, [reduced, t, duration, delay]);
  const translateY = t.interpolate({ inputRange: [0, 1], outputRange: [amplitude, -amplitude] });
  return (
    <Animated.View
      pointerEvents="none"
      // Animated.View expects the exact numeric | `${number}%` | "auto" style
      // on `left` / `top`. The caller's `FloatSpec` keeps that union too but
      // once the value passes through the record it widens to `string |
      // number`; cast to Animated's narrower expectation.
      style={[{ position: "absolute" }, { left, top } as any, { transform: [{ translateY }] }]}
      testID={testID}
    >
      <Component size={size} />
    </Animated.View>
  );
}

export function AuthScene({ children }: Props) {
  const { width, height } = useScreenSize();
  const palette = useMemo(() => skyForHour(studyHour()), []);
  const floaters = useMemo(() => floatersFor(width), [width]);

  return (
    <View style={styles.root} testID="auth-scene">
      {/* Sky — layered gradient, time-of-day. */}
      <LinearGradient
        colors={palette.colors}
        locations={palette.locations}
        style={StyleSheet.absoluteFillObject}
        pointerEvents="none"
      />

      {/* Soft sun / horizon glow — a huge pale ellipse, no detail. */}
      {palette.sun && (
        <View style={StyleSheet.absoluteFillObject} pointerEvents="none">
          <Svg width={width} height={height}>
            <Circle cx={width * 0.78} cy={height * 0.14} r={Math.min(width, height) * 0.18} fill={palette.sun} opacity={0.35} />
            <Circle cx={width * 0.78} cy={height * 0.14} r={Math.min(width, height) * 0.11} fill={palette.sun} opacity={0.35} />
          </Svg>
        </View>
      )}

      {/* Hills — two overlapping ranges painted as broad SVG curves. */}
      <View style={StyleSheet.absoluteFillObject} pointerEvents="none">
        <Svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
          <Path
            d={`M0 ${height * 0.72} Q ${width * 0.25} ${height * 0.6} ${width * 0.52} ${height * 0.7} T ${width} ${height * 0.68} L ${width} ${height} L 0 ${height} Z`}
            fill={palette.hillBack}
            opacity={0.75}
          />
          <Path
            d={`M0 ${height * 0.82} Q ${width * 0.3} ${height * 0.72} ${width * 0.6} ${height * 0.82} T ${width} ${height * 0.82} L ${width} ${height} L 0 ${height} Z`}
            fill={palette.hillFront}
          />
        </Svg>
      </View>

      {/* Clouds — 3 at different sizes/speeds. All animations are opacity /
          transform only; a reduced-motion user sees them static. */}
      <Cloud x={-40} y={height * 0.08} w={160} travel={Math.max(80, width * 0.35)} duration={28000} fill={palette.cloud} />
      <Cloud x={width * 0.45} y={height * 0.04} w={120} travel={Math.max(60, width * 0.3)} duration={32000} delay={2000} fill={palette.cloud} />
      <Cloud x={width * 0.2} y={height * 0.22} w={100} travel={Math.max(60, width * 0.25)} duration={24000} delay={4000} fill={palette.cloud} />

      {/* Rotating encouragement line in a reserved sky strip above the card.
          On narrow (phone) widths we tuck it just under the back-button bar
          so it never gets covered by the frosted card below. */}
      <View
        style={[styles.quoteSlot, { top: Math.min(72, Math.max(40, height * 0.06)) }]}
        pointerEvents="none"
      >
        <AuthQuote />
      </View>

      {/* Floating veggies — placed around the frosted card so they never
          sit under the inputs on narrow screens. */}
      {floaters.map((f) => (
        <Floating
          key={f.key}
          Component={VEGGIE_COMPONENTS[f.key]}
          size={f.size}
          left={f.left}
          top={f.top}
          amplitude={f.amplitude}
          duration={f.duration}
          delay={f.delay}
          testID={`auth-floater-${f.key}`}
        />
      ))}

      {/* Form. Children are expected to render whatever card / content they
          need; the scene is agnostic about the layout above it. */}
      <View style={styles.foreground} pointerEvents="box-none">
        {children}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: "#CFE3EC" }, // dawn-friendly fallback
  quoteSlot: {
    position: "absolute",
    left: 24,
    right: 24,
    alignItems: "center",
  },
  foreground: {
    flex: 1,
  },
});
