import React, { useEffect, useRef, useState } from "react";
import { Animated, Easing, GestureResponderEvent, Platform, Pressable, View } from "react-native";
import Svg, { Circle } from "react-native-svg";
import { DOMAIN, DOMAINS, Domain, GoalProgress } from "@/src/daily-goals";
import { ringLaps } from "@/src/rings";
import { useReducedMotion } from "@/src/hooks/use-reduced-motion";

// Apple-Watch-style daily rings: outer Eat, middle Move, inner Sleep.
// `bold` thickens the strokes so tiny rings (the 7-day strip, Streaks) stay
// legible. Past the goal, Eat and Move draw one extra lap (max 200%): the
// first lap turns a lighter shade and the extra lap is drawn on top in full
// colour, with a soft shadow at its leading end. Sleep never overflows.
// Overflow is visual only — no points, no extra avatar mood.

const VIEW = 260;
const C = VIEW / 2;
const radiusOf = (index: number) => 113 - index * 28;

function lighten(hex: string, amount: number): string {
  const n = parseInt(hex.slice(1), 16);
  const mix = (c: number) => Math.round(c + (255 - c) * amount);
  return `rgb(${mix(n >> 16)},${mix((n >> 8) & 255)},${mix(n & 255)})`;
}

/** Point on a ring `turns` of the way round, starting at 12 o'clock. */
function pointAt(r: number, turns: number) {
  const a = turns * 2 * Math.PI;
  return { x: C + r * Math.sin(a), y: C - r * Math.cos(a) };
}

function Arc({ r, stroke, color, turns }: { r: number; stroke: number; color: string; turns: number }) {
  const circumference = 2 * Math.PI * r;
  return (
    <Circle
      cx={C}
      cy={C}
      r={r}
      stroke={color}
      strokeWidth={stroke}
      fill="none"
      strokeLinecap="round"
      strokeDasharray={`${circumference} ${circumference}`}
      strokeDashoffset={circumference * (1 - Math.min(1, turns))}
      transform={`rotate(-90 ${C} ${C})`}
    />
  );
}

/** One fixed closing pulse: the same 700 ms expand-and-fade every time. */
function ClosePulse({ domain, size, stroke }: { domain: Domain; size: number; stroke: number }) {
  const t = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    Animated.timing(t, { toValue: 1, duration: 700, easing: Easing.out(Easing.quad), useNativeDriver: Platform.OS !== "web" }).start();
  }, [t]);
  const scale = size / VIEW;
  const r = radiusOf(DOMAINS.indexOf(domain)) * scale;
  const w = stroke * scale;
  return (
    <Animated.View
      pointerEvents="none"
      style={{
        position: "absolute", left: size / 2 - r - w / 2, top: size / 2 - r - w / 2,
        width: 2 * r + w, height: 2 * r + w, borderRadius: r + w, borderWidth: w, borderColor: DOMAIN[domain].color,
        opacity: t.interpolate({ inputRange: [0, 1], outputRange: [0.55, 0] }),
        transform: [{ scale: t.interpolate({ inputRange: [0, 1], outputRange: [1, 1.14] }) }],
      }}
    />
  );
}

export function GoalRings({
  goals,
  size = 260,
  bold = false,
  children,
  onPressRing,
  celebrate = [],
}: {
  goals: GoalProgress[];
  size?: number;
  bold?: boolean;
  children?: React.ReactNode;
  /** Tap a ring to open its log mode. */
  onPressRing?: (domain: Domain) => void;
  /** Rings that just closed: play the fixed closing pulse once. */
  celebrate?: Domain[];
}) {
  const stroke = bold ? 22 : 15;
  const reduced = useReducedMotion();
  const animation = useRef(new Animated.Value(0)).current;
  const [fraction, setFraction] = useState(0);
  const signature = goals.map((g) => `${g.domain}:${g.value}/${g.target}`).join("|");
  useEffect(() => {
    // With reduced motion every lap, including the extra one, is drawn at once.
    const listener = animation.addListener(({ value }) => setFraction(value));
    animation.setValue(reduced ? 1 : 0);
    const run = Animated.timing(animation, { toValue: 1, duration: reduced ? 0 : 650, easing: Easing.out(Easing.cubic), useNativeDriver: false });
    run.start();
    return () => {
      run.stop();
      animation.removeListener(listener);
    };
  }, [signature, reduced, animation]);

  const box = useRef<View>(null);
  const pickRing = (locationX: number, locationY: number) => {
    if (!onPressRing) return;
    const k = VIEW / size;
    const dist = Math.hypot(locationX * k - C, locationY * k - C);
    let best: Domain | null = null;
    let gap = Infinity;
    DOMAINS.forEach((d, i) => {
      const off = Math.abs(dist - radiusOf(i));
      if (off < gap) [gap, best] = [off, d];
    });
    if (best && gap <= 14) onPressRing(best);
  };
  const onPress = (e: GestureResponderEvent) => {
    const { locationX, locationY, pageX, pageY } = e.nativeEvent as any;
    // Native gives the tap position inside the rings; web only gives page
    // coordinates, so measure where the rings sit on the page.
    if (typeof locationX === "number" && typeof locationY === "number") return pickRing(locationX, locationY);
    box.current?.measure((_x, _y, _w, _h, left, top) => pickRing(pageX - left, pageY - top));
  };

  const label = DOMAINS.map((d) => {
    const g = goals.find((x) => x.domain === d);
    if (!g) return `${DOMAIN[d].name}: no goal set`;
    const { closed, over } = ringLaps(g.value, g.target, d);
    if (d === "food") {
      return `${DOMAIN[d].name}: ${g.value >= 1 ? `${g.value} meal${g.value === 1 ? "" : "s"} logged today` : "no meal logged yet"}`;
    }
    return `${DOMAIN[d].name}: ${closed ? `closed${over > 0 && d !== "rest" ? `, plus ${over}` : ""}` : `${g.value} of ${g.target} ${DOMAIN[d].unit}`}`;
  }).join(". ");

  const rings = (
    <Svg width={size} height={size} viewBox={`0 0 ${VIEW} ${VIEW}`} aria-hidden>
      {DOMAINS.map((d, index) => {
        const r = radiusOf(index);
        const goal = goals.find((g) => g.domain === d);
        const laps = goal ? ringLaps(goal.value, goal.target, d) : { first: 0, extra: 0 };
        // Animate along the whole drawn length: first lap, then the extra lap.
        const drawn = (laps.first + laps.extra) * fraction;
        const first = Math.min(1, drawn);
        const extra = Math.max(0, drawn - 1);
        const color = DOMAIN[d].color;
        const tip = pointAt(r, extra + (stroke * 0.32) / (2 * Math.PI * r));
        return (
          <React.Fragment key={d}>
            <Circle cx={C} cy={C} r={r} stroke={DOMAIN[d].track} strokeWidth={stroke} fill="none" opacity={goal ? 1 : 0.5} />
            {first > 0 && <Arc r={r} stroke={stroke} color={extra > 0 ? lighten(color, 0.45) : color} turns={first} />}
            {extra > 0 && (
              <>
                <Circle cx={tip.x} cy={tip.y} r={stroke / 2} fill="#000000" opacity={0.28} />
                <Arc r={r} stroke={stroke} color={color} turns={extra} />
              </>
            )}
          </React.Fragment>
        );
      })}
    </Svg>
  );

  return (
    <View ref={box} style={{ width: size, height: size }} accessible={!onPressRing} accessibilityRole="image" accessibilityLabel={label}>
      {onPressRing ? (
        <Pressable onPress={onPress} accessibilityRole="button" accessibilityLabel={`${label}. Tap a ring to log it.`} testID="rings-tap">
          {rings}
        </Pressable>
      ) : (
        rings
      )}
      {!reduced && celebrate.map((d) => <ClosePulse key={d} domain={d} size={size} stroke={stroke} />)}
      {children && (
        <View pointerEvents="none" style={{ position: "absolute", top: 0, right: 0, bottom: 0, left: 0, alignItems: "center", justifyContent: "center" }}>
          {children}
        </View>
      )}
    </View>
  );
}
