import React from "react";
import { StyleProp, View, ViewStyle } from "react-native";
import Svg, { Circle, Ellipse, Path, G, Rect } from "react-native-svg";

/**
 * Simple, original SVG fruit and vegetable characters for the auth scene.
 * Each one is a plain geometric figure (circles, ellipses, a soft stem or
 * leaf) with a friendly dot-eye-plus-arc-smile face — nothing resembling
 * any known copyrighted character. Everything is pure vector so the whole
 * cast adds only a few KB to the bundle.
 *
 * Faces are drawn in the same style across the set so the characters feel
 * like a family. Keep that style unified: two black dots + one gentle arc
 * for the mouth, no eyebrows, no accessories.
 */

const SIZE = 72;
const EYE_FILL = "#2A2E33";
const SHADOW = "rgba(90, 71, 50, 0.14)"; // warm, soft shadow for the ground
const STROKE = "rgba(255, 255, 255, 0.4)";

function Face({ cx = SIZE / 2, cy = SIZE / 2 + 2, w = 20, smileWidth = 8 }: { cx?: number; cy?: number; w?: number; smileWidth?: number }) {
  // Two dot eyes above a small upturned smile.
  return (
    <G>
      <Circle cx={cx - w / 2} cy={cy - 3} r={2.1} fill={EYE_FILL} />
      <Circle cx={cx + w / 2} cy={cy - 3} r={2.1} fill={EYE_FILL} />
      <Path
        d={`M ${cx - smileWidth / 2} ${cy + 4} Q ${cx} ${cy + 7 + smileWidth / 4} ${cx + smileWidth / 2} ${cy + 4}`}
        stroke={EYE_FILL}
        strokeWidth={1.6}
        strokeLinecap="round"
        fill="none"
      />
    </G>
  );
}

type Props = { size?: number; style?: StyleProp<ViewStyle> };

export function AppleVeggie({ size = SIZE, style }: Props) {
  return (
    <View style={style} accessibilityLabel="apple" accessibilityRole="image">
      <Svg width={size} height={size} viewBox={`0 0 ${SIZE} ${SIZE}`}>
        <Ellipse cx={SIZE / 2 + 8} cy={SIZE / 2 + 60} rx={18} ry={3} fill={SHADOW} />
        {/* Body */}
        <Path
          d="M20 40 C20 24 28 18 36 20 C44 18 52 24 52 40 C52 54 44 60 36 60 C28 60 20 54 20 40 Z"
          fill="#E66A5A"
          stroke={STROKE}
          strokeWidth={1}
        />
        {/* Highlight */}
        <Ellipse cx={28} cy={30} rx={5} ry={3} fill="rgba(255,255,255,0.35)" />
        {/* Stem */}
        <Path d="M36 20 L36 14 Q36 11 39 11" stroke="#5A3C2A" strokeWidth={2} fill="none" strokeLinecap="round" />
        {/* Leaf */}
        <Path d="M38 14 C44 9 50 11 50 16 C46 20 40 19 38 15 Z" fill="#7CB06B" />
        <Face cx={36} cy={42} />
      </Svg>
    </View>
  );
}

export function StrawberryVeggie({ size = SIZE, style }: Props) {
  return (
    <View style={style} accessibilityLabel="strawberry" accessibilityRole="image">
      <Svg width={size} height={size} viewBox={`0 0 ${SIZE} ${SIZE}`}>
        <Ellipse cx={SIZE / 2} cy={SIZE / 2 + 60} rx={16} ry={3} fill={SHADOW} />
        <Path
          d="M20 32 Q36 24 52 32 Q50 48 36 60 Q22 48 20 32 Z"
          fill="#E85A6A"
          stroke={STROKE}
          strokeWidth={1}
        />
        {/* Seeds */}
        {[
          [28, 38], [36, 36], [44, 38], [32, 46], [40, 46], [36, 52],
        ].map(([x, y], i) => (
          <Ellipse key={i} cx={x} cy={y} rx={1} ry={1.6} fill="#FFF2B2" />
        ))}
        {/* Leaves (crown) */}
        <Path d="M22 32 L30 24 L36 30 L42 24 L50 32 L45 32 L38 28 L36 32 L34 28 L27 32 Z" fill="#5BA857" />
        <Face cx={36} cy={44} />
      </Svg>
    </View>
  );
}

export function CarrotVeggie({ size = SIZE, style }: Props) {
  return (
    <View style={style} accessibilityLabel="carrot" accessibilityRole="image">
      <Svg width={size} height={size} viewBox={`0 0 ${SIZE} ${SIZE}`}>
        <Ellipse cx={SIZE / 2} cy={SIZE / 2 + 60} rx={16} ry={3} fill={SHADOW} />
        {/* Fronds */}
        <Path d="M28 22 Q24 14 20 10 Q27 12 30 20 Z" fill="#6DAE63" />
        <Path d="M36 20 Q36 10 36 6 Q40 10 40 20 Z" fill="#7FBC72" />
        <Path d="M44 22 Q48 14 52 10 Q46 12 42 20 Z" fill="#6DAE63" />
        {/* Body */}
        <Path
          d="M26 24 Q36 22 46 24 L40 60 Q36 62 32 60 Z"
          fill="#E88A3A"
          stroke={STROKE}
          strokeWidth={1}
        />
        {/* Ridges */}
        <Path d="M30 32 L34 32 M38 36 L42 36 M30 42 L34 42 M38 48 L42 48" stroke="rgba(60,30,10,0.18)" strokeWidth={1.2} strokeLinecap="round" />
        <Face cx={36} cy={34} w={14} smileWidth={6} />
      </Svg>
    </View>
  );
}

export function AvocadoVeggie({ size = SIZE, style }: Props) {
  return (
    <View style={style} accessibilityLabel="avocado" accessibilityRole="image">
      <Svg width={size} height={size} viewBox={`0 0 ${SIZE} ${SIZE}`}>
        <Ellipse cx={SIZE / 2} cy={SIZE / 2 + 60} rx={16} ry={3} fill={SHADOW} />
        {/* Outer skin */}
        <Path
          d="M36 14 C48 14 54 26 54 40 C54 54 46 62 36 62 C26 62 18 54 18 40 C18 26 24 14 36 14 Z"
          fill="#4B6E3B"
          stroke={STROKE}
          strokeWidth={1}
        />
        {/* Flesh */}
        <Path
          d="M36 20 C45 20 50 30 50 40 C50 52 44 58 36 58 C28 58 22 52 22 40 C22 30 27 20 36 20 Z"
          fill="#C7DD8E"
        />
        {/* Pit */}
        <Circle cx={36} cy={44} r={9} fill="#6E4A2E" />
        <Face cx={36} cy={44} w={10} smileWidth={6} />
      </Svg>
    </View>
  );
}

export function BroccoliVeggie({ size = SIZE, style }: Props) {
  return (
    <View style={style} accessibilityLabel="broccoli" accessibilityRole="image">
      <Svg width={size} height={size} viewBox={`0 0 ${SIZE} ${SIZE}`}>
        <Ellipse cx={SIZE / 2} cy={SIZE / 2 + 60} rx={16} ry={3} fill={SHADOW} />
        {/* Stem */}
        <Rect x={30} y={40} width={12} height={20} rx={5} fill="#D5DFA6" stroke={STROKE} strokeWidth={1} />
        {/* Florets — four blobs forming a crown */}
        <Circle cx={22} cy={32} r={10} fill="#4B7F3F" />
        <Circle cx={34} cy={24} r={11} fill="#55924A" />
        <Circle cx={48} cy={30} r={10} fill="#4B7F3F" />
        <Circle cx={42} cy={38} r={8} fill="#55924A" />
        <Circle cx={28} cy={38} r={8} fill="#4B7F3F" />
        <Face cx={34} cy={30} />
      </Svg>
    </View>
  );
}

export function BananaVeggie({ size = SIZE, style }: Props) {
  return (
    <View style={style} accessibilityLabel="banana" accessibilityRole="image">
      <Svg width={size} height={size} viewBox={`0 0 ${SIZE} ${SIZE}`}>
        <Ellipse cx={SIZE / 2} cy={SIZE / 2 + 60} rx={16} ry={3} fill={SHADOW} />
        {/* Crescent body */}
        <Path
          d="M14 46 C18 24 46 14 58 18 C56 26 60 36 54 44 C44 58 24 62 14 46 Z"
          fill="#F2CB4C"
          stroke={STROKE}
          strokeWidth={1}
        />
        <Path d="M20 46 C24 32 44 24 54 24" stroke="rgba(130, 90, 10, 0.18)" strokeWidth={1.5} fill="none" strokeLinecap="round" />
        {/* Stem */}
        <Path d="M58 18 L62 14" stroke="#6B4A20" strokeWidth={2} strokeLinecap="round" />
        <Face cx={34} cy={38} w={12} smileWidth={7} />
      </Svg>
    </View>
  );
}

export function BlueberriesVeggie({ size = SIZE, style }: Props) {
  return (
    <View style={style} accessibilityLabel="blueberries" accessibilityRole="image">
      <Svg width={size} height={size} viewBox={`0 0 ${SIZE} ${SIZE}`}>
        <Ellipse cx={SIZE / 2} cy={SIZE / 2 + 60} rx={16} ry={3} fill={SHADOW} />
        {/* Three berries in a cluster */}
        <Circle cx={22} cy={44} r={12} fill="#4A5EB6" stroke={STROKE} strokeWidth={1} />
        <Circle cx={48} cy={42} r={12} fill="#4A5EB6" stroke={STROKE} strokeWidth={1} />
        <Circle cx={34} cy={52} r={13} fill="#5569C6" stroke={STROKE} strokeWidth={1} />
        {/* Highlights */}
        <Ellipse cx={18} cy={40} rx={3} ry={2} fill="rgba(255,255,255,0.25)" />
        <Ellipse cx={44} cy={38} rx={3} ry={2} fill="rgba(255,255,255,0.25)" />
        {/* Little tops */}
        <Path d="M22 32 L22 36 M20 34 L24 34" stroke="#2E3A6D" strokeWidth={1.2} strokeLinecap="round" />
        <Path d="M48 30 L48 34 M46 32 L50 32" stroke="#2E3A6D" strokeWidth={1.2} strokeLinecap="round" />
        <Face cx={34} cy={52} w={12} smileWidth={6} />
      </Svg>
    </View>
  );
}

export function OatsVeggie({ size = SIZE, style }: Props) {
  return (
    <View style={style} accessibilityLabel="oats" accessibilityRole="image">
      <Svg width={size} height={size} viewBox={`0 0 ${SIZE} ${SIZE}`}>
        <Ellipse cx={SIZE / 2} cy={SIZE / 2 + 60} rx={16} ry={3} fill={SHADOW} />
        {/* Bowl */}
        <Path
          d="M14 42 Q36 32 58 42 L54 58 Q36 64 18 58 Z"
          fill="#E7D1A4"
          stroke={STROKE}
          strokeWidth={1}
        />
        {/* Oats surface */}
        <Ellipse cx={36} cy={42} rx={22} ry={5} fill="#F3E2BC" />
        {/* Oat grains */}
        {[
          [26, 40], [30, 42], [34, 40], [40, 42], [44, 40], [48, 42], [32, 44], [40, 44],
        ].map(([x, y], i) => (
          <Ellipse key={i} cx={x} cy={y} rx={1.6} ry={1} fill="#B98F4A" />
        ))}
        <Face cx={36} cy={52} w={12} smileWidth={6} />
      </Svg>
    </View>
  );
}

export type VeggieKey =
  | "apple" | "strawberry" | "carrot" | "avocado" | "broccoli"
  | "banana" | "blueberries" | "oats";

export const VEGGIE_COMPONENTS: Record<VeggieKey, React.ComponentType<Props>> = {
  apple: AppleVeggie,
  strawberry: StrawberryVeggie,
  carrot: CarrotVeggie,
  avocado: AvocadoVeggie,
  broccoli: BroccoliVeggie,
  banana: BananaVeggie,
  blueberries: BlueberriesVeggie,
  oats: OatsVeggie,
};
