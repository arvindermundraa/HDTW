import React from "react";
import { View, StyleSheet, Pressable } from "react-native";
import Animated, {
  useAnimatedRef,
  useAnimatedStyle,
  useSharedValue,
  withTiming,
  measure,
  runOnJS,
} from "react-native-reanimated";
import { Gesture, GestureDetector } from "react-native-gesture-handler";
import { Feather } from "@expo/vector-icons";
import { AppText } from "@/src/components/ui";
import { colors, spacing, radius } from "@/src/theme";

export type Ingredient = { id: string; name: string; icon?: string };

/**
 * Draggable ingredient chip. Two ways to add an item to the plate, by
 * design, not by accident:
 *   1. Drag it onto the plate zone (the "fun," tactile interaction the
 *      source deck's mockup depicts: "Drag and drop to build your plate!").
 *   2. Tap it (Gesture.Exclusive below lets a stationary tap win when the
 *      pan gesture never crosses its minDistance threshold).
 * Tap-to-add is the accessible path — drag-and-drop alone has no equivalent
 * for screen-reader or switch-control users, so it is never the *only* way
 * to play. This mirrors the same cosmetic-vs-functional split used
 * elsewhere in the app (LLM word reveal, RewardBurst): the drag animation
 * is progressive enhancement, tap-to-add is the functional guarantee.
 */
export function DraggableChip({
  ingredient,
  plateRef,
  onAdd,
  disabled,
  reducedMotion,
  testID,
}: {
  ingredient: Ingredient;
  plateRef: React.RefObject<any>;
  onAdd: (id: string) => void;
  disabled?: boolean;
  reducedMotion?: boolean;
  testID?: string;
}) {
  const translateX = useSharedValue(0);
  const translateY = useSharedValue(0);
  const scale = useSharedValue(1);

  const handleAdd = (id: string) => onAdd(id);

  const pan = Gesture.Pan()
    .minDistance(10)
    .enabled(!disabled)
    .onUpdate((e) => {
      translateX.value = e.translationX;
      translateY.value = e.translationY;
      scale.value = 1.06;
    })
    .onEnd((e) => {
      const plate = measure(plateRef);
      let dropped = false;
      if (plate) {
        dropped =
          e.absoluteX >= plate.pageX &&
          e.absoluteX <= plate.pageX + plate.width &&
          e.absoluteY >= plate.pageY &&
          e.absoluteY <= plate.pageY + plate.height;
      }
      const dur = reducedMotion ? 0 : 180;
      translateX.value = withTiming(0, { duration: dur });
      translateY.value = withTiming(0, { duration: dur });
      scale.value = withTiming(1, { duration: dur });
      if (dropped) runOnJS(handleAdd)(ingredient.id);
    });

  const tap = Gesture.Tap()
    .enabled(!disabled)
    .onEnd(() => {
      runOnJS(handleAdd)(ingredient.id);
    });

  const composed = Gesture.Exclusive(pan, tap);

  const style = useAnimatedStyle(() => ({
    transform: [
      { translateX: translateX.value },
      { translateY: translateY.value },
      { scale: scale.value },
    ],
    zIndex: translateX.value !== 0 || translateY.value !== 0 ? 10 : 1,
  }));

  return (
    <GestureDetector gesture={composed}>
      <Animated.View
        style={[styles.chip, disabled && styles.chipDisabled, style]}
        testID={testID}
        accessibilityRole="button"
        accessibilityLabel={`Add ${ingredient.name} to plate`}
        accessibilityHint="Double tap to add, or drag onto the plate"
      >
        <AppText style={{ fontSize: 22 }}>{ingredient.icon || "🍽️"}</AppText>
        <AppText variant="caption" style={{ textAlign: "center", marginTop: 4 }} numberOfLines={2}>
          {ingredient.name}
        </AppText>
      </Animated.View>
    </GestureDetector>
  );
}

export function PlateZone({
  plateRef,
  items,
  onRemove,
  emptyLabel,
}: {
  plateRef: React.RefObject<any>;
  items: Ingredient[];
  onRemove: (id: string) => void;
  emptyLabel: string;
}) {
  return (
    <Animated.View ref={plateRef} style={styles.plate} testID="plate-zone">
      {items.length === 0 ? (
        <AppText variant="caption" style={{ textAlign: "center", paddingHorizontal: spacing.xl }}>
          {emptyLabel}
        </AppText>
      ) : (
        <View style={styles.plateItemsWrap}>
          {items.map((it) => (
            <Pressable
              key={it.id}
              style={styles.plateItem}
              onPress={() => onRemove(it.id)}
              testID={`plate-item-${it.id}`}
              accessibilityRole="button"
              accessibilityLabel={`Remove ${it.name} from plate`}
            >
              <AppText style={{ fontSize: 18 }}>{it.icon || "🍽️"}</AppText>
              <AppText variant="caption" style={{ marginLeft: 6 }}>
                {it.name}
              </AppText>
              <Feather name="x" size={13} color={colors.muted} style={{ marginLeft: 6 }} />
            </Pressable>
          ))}
        </View>
      )}
    </Animated.View>
  );
}

export function useMeasuredPlateRef() {
  return useAnimatedRef<any>();
}

const styles = StyleSheet.create({
  chip: {
    width: 84,
    height: 84,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surfaceSecondary,
    alignItems: "center",
    justifyContent: "center",
    padding: spacing.xs,
  },
  chipDisabled: { opacity: 0.35 },
  plate: {
    minHeight: 160,
    borderRadius: radius.pill,
    borderWidth: 2,
    borderColor: colors.border,
    borderStyle: "dashed",
    backgroundColor: colors.surfaceSecondary,
    alignItems: "center",
    justifyContent: "center",
    padding: spacing.lg,
  },
  plateItemsWrap: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, justifyContent: "center" },
  plateItem: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
});
