import { useEffect, useState } from "react";
import { AccessibilityInfo } from "react-native";

/**
 * PRD §14.4 (hard requirement): OS-level reduced-motion settings must
 * hard-override all motion/atmosphere effects to their static equivalent.
 * This is the single shared source of truth for that check — every
 * animated component (RewardBurst, word-by-word text reveal, Weekly
 * Story chapter transitions) should read from this hook rather than
 * animating unconditionally.
 *
 * NOTE: this reads AccessibilityInfo.isReduceMotionEnabled() (the OS-level
 * setting on iOS/Android), NOT the CSS `prefers-reduced-motion` media query
 * — that has no equivalent outside a browser DOM context. See PRD §9.4.
 */
export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    let mounted = true;
    AccessibilityInfo.isReduceMotionEnabled?.()
      .then((v) => mounted && setReduced(!!v))
      .catch(() => {});
    const sub = AccessibilityInfo.addEventListener?.("reduceMotionChanged", (v: boolean) => {
      if (mounted) setReduced(!!v);
    });
    return () => {
      mounted = false;
      // RN's newer AccessibilityInfo.addEventListener returns a subscription
      // object with .remove(); older versions returned nothing to clean up.
      // @ts-ignore
      sub?.remove?.();
    };
  }, []);

  return reduced;
}
