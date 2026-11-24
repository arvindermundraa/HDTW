import React, { useEffect, useId, useRef } from "react";
import { Animated, Platform, View } from "react-native";
import Svg, { Circle, ClipPath, Defs, Ellipse, G, Line, Path, RadialGradient, Rect, Stop } from "react-native-svg";
import { AvatarConfig, AvatarMood, MOOD_TEXT, avatarColors } from "@/src/avatar";
import { useReducedMotion } from "@/src/hooks/use-reduced-motion";
import { colors } from "@/src/theme";

// Original layered SVG parts (no third-party art, so no licence questions).
// HARD RULE: the head and shoulders are the same fixed paths for every
// participant on every day. Options only change colours or swap fixed
// overlays (hair, glasses, outfit details); mood only changes the mouth,
// brows, cheeks and a soft background glow. Nothing can resize the body.

const INK = "#2A2523";
const SHOULDERS = "M8 64 C8 51 18 46.5 32 46.5 C46 46.5 56 51 56 64 Z";

function shade(hex: string, amt: number) {
  const n = parseInt(hex.slice(1), 16);
  const f = (c: number) => Math.max(0, Math.min(255, Math.round(c + amt * 255)));
  return `rgb(${f(n >> 16)},${f((n >> 8) & 255)},${f(n & 255)})`;
}

function HairBack({ style, color }: { style: string; color: string }) {
  switch (style) {
    case "long":
      return <Path d="M18.5 29 C18 15 46 15 45.5 29 L47.5 49 C42 51 22 51 16.5 49 Z" fill={color} />;
    case "curly":
      return (
        <G fill={color}>
          {[[19, 25, 6], [23, 17.5, 6.5], [32, 14, 7], [41, 17.5, 6.5], [45, 25, 6], [18.5, 33, 4.5], [45.5, 33, 4.5]].map(([x, y, r], i) => (
            <Circle key={i} cx={x} cy={y} r={r} />
          ))}
        </G>
      );
    case "bun":
      return <Circle cx={32} cy={11.5} r={5.5} fill={color} />;
    case "covered":
      return <Path d="M17 31 C16.5 13 47.5 13 47 31 L50 50 C44 53 20 53 14 50 Z" fill={color} />;
    default:
      return null;
  }
}

function HairFront({ style, color }: { style: string; color: string }) {
  switch (style) {
    case "short":
    case "bun":
      return <Path d="M19.6 27.5 C19 16.5 25.5 13.8 32 13.8 C38.5 13.8 45 16.5 44.4 27.5 C42 22.5 38 20 32 20.8 C26 20 22 22.5 19.6 27.5 Z" fill={color} />;
    case "crop":
      return <Path d="M20.2 24.5 C21 16.8 27 15 32 15 C37 15 43 16.8 43.8 24.5 C40 21 24 21 20.2 24.5 Z" fill={color} />;
    case "wavy":
      return <Path d="M19.2 30 C17.5 17 25 13 33 13.2 C41 13.5 46.5 18 44.8 30 C43.5 24.5 41.5 21.5 37.5 20.5 C33.5 23.5 26.5 24.3 21.3 23.3 C20.3 25.3 19.6 27.5 19.2 30 Z" fill={color} />;
    case "curly":
      return (
        <G fill={color}>
          {[[23, 20, 4.2], [28, 18, 4.4], [33, 17.6, 4.4], [38, 18.5, 4.2], [42, 21.5, 3.6]].map(([x, y, r], i) => (
            <Circle key={i} cx={x} cy={y} r={r} />
          ))}
        </G>
      );
    case "long":
      return <Path d="M19.5 31 C19 16.5 25.5 13.8 32 13.8 C38.5 13.8 45 16.5 44.5 31 C43 23 38.5 19 32.5 18.8 L31.5 18.8 C25.5 19 21 23 19.5 31 Z" fill={color} />;
    case "covered":
      return <Path d="M18.6 34 C18 17.5 25 14.5 32 14.5 C39 14.5 46 17.5 45.4 34 C44 25 39.5 20 32 20 C24.5 20 20 25 18.6 34 Z" fill={shade(color, 0.06)} />;
    default:
      return null;
  }
}

function Outfit({ style, color, skin }: { style: string; color: string; skin: string }) {
  const dark = shade(color, -0.08);
  switch (style) {
    case "hoodie":
      return (
        <G>
          <Path d="M20 49.5 C23 44.5 41 44.5 44 49.5 L40.5 51.5 C37 48.2 27 48.2 23.5 51.5 Z" fill={dark} />
          <Path d="M27 46.6 Q32 50.5 37 46.6 Z" fill={skin} />
          <Line x1={29.5} y1={50.5} x2={29.5} y2={57} stroke={shade(color, 0.25)} strokeWidth={0.9} strokeLinecap="round" />
          <Line x1={34.5} y1={50.5} x2={34.5} y2={57} stroke={shade(color, 0.25)} strokeWidth={0.9} strokeLinecap="round" />
        </G>
      );
    case "collar":
      return (
        <G>
          <Path d="M27.5 46.5 L32 53 L36.5 46.5 Z" fill={skin} />
          <Path d="M26.5 46.2 L32 53 L28 54.5 L24.8 48 Z" fill="#F4F2EE" />
          <Path d="M37.5 46.2 L32 53 L36 54.5 L39.2 48 Z" fill="#F4F2EE" />
        </G>
      );
    case "sweater":
      return (
        <G>
          <Path d="M26.8 46.5 L32 54.5 L37.2 46.5 Z" fill={skin} />
          <Path d="M26 46.4 L32 55.6 L38 46.4" fill="none" stroke={dark} strokeWidth={1.6} strokeLinejoin="round" />
        </G>
      );
    default:
      return <Path d="M26.5 46.6 Q32 51.2 37.5 46.6 Z" fill={skin} />;
  }
}

function Face({ config, mood, skin, hair }: { config: AvatarConfig; mood: AvatarMood | null; skin: string; hair: string }) {
  const m = mood?.mood ?? "calm";
  const lift = m === "energised" ? 1 : 0;
  const rested = mood?.props.includes("rested");
  const browColor = config.hair === "none" || config.hair === "covered" ? shade(skin, -0.35) : hair;
  const mouth =
    m === "energised" ? (
      <Path d="M27.6 35.6 Q32 41.6 36.4 35.6 Z" fill="#6B2F2A" />
    ) : m === "content" ? (
      <Path d="M28.2 36 Q32 39.6 35.8 36" fill="none" stroke={INK} strokeWidth={1.5} strokeLinecap="round" />
    ) : (
      <Path d="M28.8 36.6 Q32 38.2 35.2 36.6" fill="none" stroke={INK} strokeWidth={1.4} strokeLinecap="round" />
    );
  return (
    <G>
      {config.face === "stubble" && <Path d="M20.5 33 C21 41 26 43.5 32 43.5 C38 43.5 43 41 43.5 33 C41 38 36 39.5 32 39.5 C28 39.5 23 38 20.5 33 Z" fill={hair} opacity={0.28} />}
      {config.face === "beard" && (
        <Path d="M20 31.5 C20 41 25 44.5 32 44.5 C39 44.5 44 41 44 31.5 C42.5 36 39 38 36.6 38.2 C35 34.8 29 34.8 27.4 38.2 C25 38 21.5 36 20 31.5 Z" fill={hair} />
      )}
      <Path d={`M24.8 ${24.4 - lift} Q27 ${23.2 - lift} 29.2 ${24.2 - lift}`} fill="none" stroke={browColor} strokeWidth={1.4} strokeLinecap="round" />
      <Path d={`M34.8 ${24.2 - lift} Q37 ${23.2 - lift} 39.2 ${24.4 - lift}`} fill="none" stroke={browColor} strokeWidth={1.4} strokeLinecap="round" />
      {config.face === "soft" ? (
        <G stroke={INK} strokeWidth={1.4} fill="none" strokeLinecap="round">
          <Path d="M25.3 30.4 Q27 28.6 28.7 30.4" />
          <Path d="M35.3 30.4 Q37 28.6 38.7 30.4" />
        </G>
      ) : (
        <G>
          <Circle cx={27} cy={29.8} r={1.75} fill={INK} />
          <Circle cx={37} cy={29.8} r={1.75} fill={INK} />
          {rested && (
            <G fill="#FFFFFF">
              <Circle cx={27.6} cy={29.2} r={0.55} />
              <Circle cx={37.6} cy={29.2} r={0.55} />
            </G>
          )}
        </G>
      )}
      {config.face === "freckles" && (
        <G fill={shade(skin, -0.22)}>
          {[[24.5, 33.2], [26.3, 34.2], [23.6, 34.6], [39.5, 33.2], [37.7, 34.2], [40.4, 34.6]].map(([x, y], i) => (
            <Circle key={i} cx={x} cy={y} r={0.5} />
          ))}
        </G>
      )}
      {m !== "calm" && (
        <G fill="#D9746A" opacity={0.22}>
          <Circle cx={24.2} cy={34.4} r={2.4} />
          <Circle cx={39.8} cy={34.4} r={2.4} />
        </G>
      )}
      {config.face === "beard" ? <Path d="M29 37.4 Q32 39.4 35 37.4" fill="none" stroke={INK} strokeWidth={1.3} strokeLinecap="round" /> : mouth}
    </G>
  );
}

function Glasses({ style }: { style: string }) {
  if (style === "none") return null;
  const frame = { stroke: "#2B2F2E", strokeWidth: 1.2, fill: "#FFFFFF", fillOpacity: 0.12 };
  return (
    <G>
      {style === "round" ? (
        <>
          <Circle cx={27} cy={29.8} r={4.1} {...frame} />
          <Circle cx={37} cy={29.8} r={4.1} {...frame} />
        </>
      ) : (
        <>
          <Rect x={22.4} y={26.4} width={9.2} height={7} rx={1.6} {...frame} />
          <Rect x={32.4} y={26.4} width={9.2} height={7} rx={1.6} {...frame} />
        </>
      )}
      <Path d="M31.1 29.4 Q32 28.6 32.9 29.4" fill="none" stroke="#2B2F2E" strokeWidth={1.1} />
    </G>
  );
}

/** Small prop badges (salad bowl / sneakers) — today's logs, never a judgement. */
function PropBadge({ kind, size }: { kind: "salad" | "sneakers"; size: number }) {
  return (
    <View
      style={{
        width: size, height: size, borderRadius: size / 2, backgroundColor: colors.surfaceSecondary,
        borderWidth: 1, borderColor: colors.border, alignItems: "center", justifyContent: "center",
      }}
    >
      <Svg width={size * 0.72} height={size * 0.72} viewBox="0 0 20 20">
        {kind === "salad" ? (
          <G>
            <Circle cx={7} cy={9} r={3} fill="#5E9B5A" />
            <Circle cx={10.5} cy={7.5} r={3.2} fill="#4C8A4E" />
            <Circle cx={13.5} cy={9.3} r={2.6} fill="#79AE5E" />
            <Circle cx={9.8} cy={9.8} r={1.2} fill="#C8553D" />
            <Path d="M3 10.5 H17 C17 15 14 17 10 17 C6 17 3 15 3 10.5 Z" fill="#D9CDB6" />
          </G>
        ) : (
          <G>
            <Path d="M2.5 13.5 C2.5 9 4.5 7 6.5 7 L9 7 C10 9.5 12 10.5 15.5 11.2 C17 11.5 17.8 12.6 17.8 14 L17.8 14.5 L2.5 14.5 Z" fill={colors.brandSecondary} />
            <Rect x={2.5} y={14.5} width={15.3} height={2.3} rx={1} fill="#EDEAE4" />
            <Line x1={8.5} y1={9} x2={10.5} y2={8.2} stroke="#FFFFFF" strokeWidth={0.8} strokeLinecap="round" />
          </G>
        )}
      </Svg>
    </View>
  );
}

export function AvatarArt({
  config,
  mood,
  size = 44,
  ring = false,
  showProps = true,
}: {
  config: AvatarConfig;
  mood: AvatarMood | null;
  size?: number;
  ring?: boolean;
  showProps?: boolean;
}) {
  const raw = useId();
  const id = raw.replace(/[^a-zA-Z0-9]/g, "");
  const reduced = useReducedMotion();
  const c = avatarColors(config);
  const glow = !!mood?.glow;
  const pulse = useRef(new Animated.Value(1)).current;

  // A slow, fixed breathing glow on energised days; static with reduced motion.
  useEffect(() => {
    if (!glow || reduced) {
      pulse.setValue(1);
      return;
    }
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, { toValue: 0.55, duration: 1600, useNativeDriver: Platform.OS !== "web" }),
        Animated.timing(pulse, { toValue: 1, duration: 1600, useNativeDriver: Platform.OS !== "web" }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [glow, reduced, pulse]);

  const props = showProps && size >= 56 ? (mood?.props ?? []).filter((p): p is "salad" | "sneakers" => p !== "rested") : [];
  const badge = Math.max(16, Math.round(size * 0.34));
  const r = ring ? 30 : 32;
  const label = `Your avatar, ${MOOD_TEXT[mood?.mood ?? "calm"]} today`;

  return (
    <View style={{ width: size, height: size }} accessible accessibilityRole="image" accessibilityLabel={label}>
      {glow && (
        <Animated.View
          pointerEvents="none"
          style={{
            position: "absolute", left: -size * 0.08, top: -size * 0.08, width: size * 1.16, height: size * 1.16,
            borderRadius: size, backgroundColor: "rgba(184,134,43,0.20)", opacity: pulse,
          }}
        />
      )}
      <Svg width={size} height={size} viewBox="0 0 64 64">
        <Defs>
          <ClipPath id={`clip${id}`}>
            <Circle cx={32} cy={32} r={r} />
          </ClipPath>
          <RadialGradient id={`glow${id}`} cx="50%" cy="45%" r="55%">
            <Stop offset="0" stopColor="#FFF4D6" stopOpacity={0.95} />
            <Stop offset="1" stopColor="#FFF4D6" stopOpacity={0} />
          </RadialGradient>
        </Defs>
        <Circle cx={32} cy={32} r={r} fill={c.background} stroke={ring ? "#FFFFFF" : "none"} strokeWidth={ring ? 4 : 0} />
        <G clipPath={`url(#clip${id})`}>
          {glow && <Circle cx={32} cy={30} r={30} fill={`url(#glow${id})`} />}
          <HairBack style={config.hair} color={c.hair} />
          <Rect x={27} y={38} width={10} height={10} rx={3} fill={shade(c.skin, -0.06)} />
          <Path d={SHOULDERS} fill={c.outfit} />
          <Outfit style={config.outfit} color={c.outfit} skin={shade(c.skin, -0.06)} />
          {config.hair !== "covered" && (
            <G fill={c.skin}>
              <Circle cx={19.6} cy={31} r={3} />
              <Circle cx={44.4} cy={31} r={3} />
            </G>
          )}
          <Ellipse cx={32} cy={29} rx={12.5} ry={14} fill={c.skin} />
          <Face config={config} mood={mood} skin={c.skin} hair={c.hair} />
          <HairFront style={config.hair} color={c.hair} />
          <Glasses style={config.glasses} />
        </G>
      </Svg>
      {props.length > 0 && (
        <View style={{ position: "absolute", bottom: -badge * 0.15, right: -badge * 0.2, flexDirection: "row", gap: 2 }} pointerEvents="none">
          {props.map((p) => (
            <PropBadge key={p} kind={p} size={badge} />
          ))}
        </View>
      )}
    </View>
  );
}
