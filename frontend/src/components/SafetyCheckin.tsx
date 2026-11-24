import React, { forwardRef, useCallback } from "react";
import { View, StyleSheet } from "react-native";
import { BottomSheetModal, BottomSheetView, BottomSheetBackdrop } from "@gorhom/bottom-sheet";
import { Feather } from "@expo/vector-icons";
import { AppText, Button } from "@/src/components/ui";
import { colors, spacing, radius } from "@/src/theme";

export type Checkin = { id: string; message: string; reason: string } | null;

export const SafetyCheckinSheet = forwardRef<BottomSheetModal, { checkin: Checkin; onAcknowledge: () => void }>(
  ({ checkin, onAcknowledge }, ref) => {
    const renderBackdrop = useCallback(
      (props: any) => <BottomSheetBackdrop {...props} appearsOnIndex={0} disappearsOnIndex={-1} opacity={0.4} />,
      []
    );
    return (
      <BottomSheetModal
        ref={ref}
        backdropComponent={renderBackdrop}
        enablePanDownToClose
        handleIndicatorStyle={{ backgroundColor: colors.borderStrong }}
        backgroundStyle={{ backgroundColor: colors.surface }}
      >
        <BottomSheetView style={styles.c}>
          <View style={styles.iconWrap}>
            <Feather name="heart" size={22} color={colors.onBrandSecondary} />
          </View>
          <AppText variant="title" style={{ marginTop: spacing.lg }}>
            A gentle check-in
          </AppText>
          <AppText variant="body" style={{ marginTop: spacing.md, marginBottom: spacing.xl, fontSize: 16, lineHeight: 24 }}>
            {checkin?.message}
          </AppText>
          <Button title="I'm okay, thank you" onPress={onAcknowledge} testID="safety-ack" />
          <AppText variant="caption" style={{ textAlign: "center", marginTop: spacing.lg }}>
            If food ever feels overwhelming, reaching out to someone you trust or a professional can help. This app never
            penalizes you.
          </AppText>
        </BottomSheetView>
      </BottomSheetModal>
    );
  }
);

SafetyCheckinSheet.displayName = "SafetyCheckinSheet";

const styles = StyleSheet.create({
  c: { paddingHorizontal: spacing.xl, paddingBottom: spacing["3xl"], paddingTop: spacing.sm },
  iconWrap: {
    width: 48,
    height: 48,
    borderRadius: radius.pill,
    backgroundColor: colors.brandSecondary,
    alignItems: "center",
    justifyContent: "center",
  },
});
