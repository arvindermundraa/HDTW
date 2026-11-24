import React, { useEffect, useRef, useState } from "react";
import { StyleProp, StyleSheet, View, ViewStyle, Platform, Animated, Easing } from "react-native";
import { AppText } from "@/src/components/ui";
import { fonts } from "@/src/theme";
import { useReducedMotion } from "@/src/hooks/use-reduced-motion";
import { AUTH_QUOTES } from "@/src/components/auth-quotes-data";

export { AUTH_QUOTES };

const HOLD_MS = 7500;
const FADE_MS = 1200;

/**
 * One line of encouragement fading in and out in the sky. Transforms and
 * opacity only (no layout shift). Respects OS "reduce motion": the first
 * line is shown statically with the animation turned off.
 */
export function AuthQuote({
  quotes = AUTH_QUOTES,
  style,
  testID = "auth-quote",
}: {
  quotes?: readonly string[];
  style?: StyleProp<ViewStyle>;
  testID?: string;
}) {
  const reduced = useReducedMotion();
  const [index, setIndex] = useState(0);
  const opacity = useRef(new Animated.Value(reduced ? 1 : 0)).current;

  useEffect(() => {
    if (reduced) {
      // One static line, no animation at all — same component tree, same
      // layout, so the keyboard-aware form never jumps as motion toggles.
      opacity.setValue(1);
      return;
    }
    let cancelled = false;
    const native = Platform.OS !== "web";
    const step = () => {
      Animated.sequence([
        Animated.timing(opacity, { toValue: 1, duration: FADE_MS, easing: Easing.out(Easing.quad), useNativeDriver: native }),
        Animated.delay(HOLD_MS),
        Animated.timing(opacity, { toValue: 0, duration: FADE_MS, easing: Easing.in(Easing.quad), useNativeDriver: native }),
      ]).start(({ finished }) => {
        if (!finished || cancelled) return;
        setIndex((i) => (i + 1) % quotes.length);
        step();
      });
    };
    step();
    return () => {
      cancelled = true;
      opacity.stopAnimation();
    };
  }, [opacity, quotes.length, reduced]);

  return (
    <View style={[styles.wrap, style]} pointerEvents="none" accessibilityElementsHidden={!reduced}>
      <Animated.View style={{ opacity }} testID={testID}>
        <AppText
          variant="subtitle"
          style={styles.text}
          accessibilityLabel={reduced ? quotes[0] : undefined}
        >
          {reduced ? quotes[0] : quotes[index]}
        </AppText>
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { alignItems: "center", justifyContent: "center" },
  text: {
    fontFamily: fonts.semibold,
    fontSize: 16,
    lineHeight: 22,
    color: "#3F3824",
    textAlign: "center",
    letterSpacing: 0.2,
    // Keep the quote readable against the brightest part of the sky
    // without needing an extra pill — a quiet shadow is enough.
    textShadowColor: "rgba(255, 255, 255, 0.6)",
    textShadowOffset: { width: 0, height: 1 },
    textShadowRadius: 2,
  },
});
