import React, { useState } from "react";
import { View, StyleSheet, Linking, Pressable } from "react-native";
import { useRouter } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { AppText, Button } from "@/src/components/ui";
import { IconCircle, cardStyle } from "@/src/components/llhs";
import { api, RecallInfo } from "@/src/api";
import { colors, domain, spacing, fonts, radius } from "@/src/theme";

// The ASA24 food recall, brought into Today. The recall itself happens on
// NCI's ASA24 site (no API), so this card links out, records "I finished"
// so the study team knows when to download results, and says when new
// results are in. Never shows a score, and a missed window is never shown
// as a failure: the card simply moves on to the next recall.

const shortDate = (iso?: string) => {
  if (!iso) return "";
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("en-US", { month: "short", day: "numeric" });
};

export function RecallCard({ info, onChange }: { info: RecallInfo | null; onChange: () => void }) {
  const router = useRouter();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  if (!info) return null;
  const { recall } = info;
  const done = recall.recalls_done ?? 0;
  const needed = recall.recalls_needed ?? 2;

  const reviewResults = async () => {
    await api.recallResultsSeen().catch(() => {});
    onChange();
    router.push("/focus-areas");
  };

  const finish = async () => {
    if (!recall.assessment_type) return;
    setSaving(true);
    setError("");
    try {
      await api.recallFinished(recall.assessment_type);
      onChange();
    } catch (e: any) {
      setError(e?.message || "Couldn't save that. Try again.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <View style={{ gap: spacing.md }}>
      {info.new_results && (
        <Pressable onPress={reviewResults} style={[cardStyle, styles.results]} testID="recall-new-results">
          <IconCircle icon="bar-chart-2" color={domain.food.main} tint={domain.food.tint} size={40} />
          <View style={{ flex: 1 }}>
            <AppText variant="subtitle">Your new results are in</AppText>
            <AppText variant="caption">See your strengths and choose your focus area.</AppText>
          </View>
          <Feather name="chevron-right" size={20} color={colors.muted} />
        </Pressable>
      )}

      {recall.state !== "complete" && (
        <View style={cardStyle} testID={`recall-card-${recall.state}`}>
          <View style={styles.head}>
            <IconCircle icon="clipboard" color={domain.food.main} tint={domain.food.tint} size={40} />
            <View style={{ flex: 1 }}>
              <AppText variant="label" color={colors.muted}>
                {(recall.label || "").toUpperCase()} FOOD RECALLS
                {recall.state === "open" ? ` · ${Math.min(done + 1, needed)} OF ${needed}` : ""}
              </AppText>
              <AppText variant="subtitle">
                {recall.state === "open"
                  ? `Open until ${shortDate(recall.due_by)}`
                  : recall.state === "upcoming"
                    ? `Opens ${shortDate(recall.opens_on)}`
                    : "Done. Thank you!"}
              </AppText>
            </View>
          </View>

          <AppText variant="body" style={{ marginTop: spacing.md }}>
            {recall.state === "open"
              ? done === 0
                ? `Do ${needed} recalls on the ASA24 website: one in the evening of a weekday, and one in the evening of a Saturday or Sunday. Either order. Each covers the last 24 hours and takes about 30 minutes.`
                : "One more to go: do it in the evening of the other kind of day (a weekday or a Saturday or Sunday). It covers the last 24 hours."
              : recall.state === "upcoming"
                ? `${needed} recalls, a weekday and a weekend day. In ${recall.days_until_open} ${recall.days_until_open === 1 ? "day" : "days"}. Nothing to prepare.`
                : "Your results will appear here after the study team reviews them."}
          </AppText>
          {recall.state === "open" && done > 0 ? (
            <AppText variant="caption" color={colors.muted} style={{ marginTop: spacing.xs }} testID="recall-progress">
              {done} of {needed} done
            </AppText>
          ) : null}

          {recall.state === "open" && (
            <>
              <View style={styles.username}>
                <AppText variant="caption">Your ASA24 login</AppText>
                {info.asa24_username ? (
                  <>
                    <View style={styles.loginRow}>
                      <AppText variant="caption" style={styles.loginKey}>Username</AppText>
                      <AppText variant="body" style={styles.loginValue} selectable testID="recall-username">
                        {info.asa24_username}
                      </AppText>
                    </View>
                    {info.asa24_password ? (
                      <View style={styles.loginRow}>
                        <AppText variant="caption" style={styles.loginKey}>Password</AppText>
                        <AppText variant="body" style={[styles.loginValue, { flex: 1 }]} selectable testID="recall-password">
                          {showPassword ? info.asa24_password : "••••••••"}
                        </AppText>
                        <Pressable onPress={() => setShowPassword((v) => !v)} hitSlop={8} testID="recall-password-toggle">
                          <AppText variant="caption" color={colors.brandPrimary} style={{ fontFamily: fonts.semibold }}>
                            {showPassword ? "Hide" : "Show"}
                          </AppText>
                        </Pressable>
                      </View>
                    ) : (
                      <AppText variant="caption" style={{ marginTop: spacing.xs }}>
                        Use the password the study team gave you.
                      </AppText>
                    )}
                  </>
                ) : (
                  <AppText variant="body" testID="recall-username">
                    Your ASA24 login is being set up. Check back soon, or ask the study team.
                  </AppText>
                )}
              </View>
              <View style={styles.actions}>
                <Button
                  title="Start recall"
                  onPress={() => Linking.openURL(info.link)}
                  style={{ flex: 1 }}
                  testID="recall-start"
                />
                <Button
                  title="I finished"
                  variant="secondary"
                  onPress={finish}
                  loading={saving}
                  style={{ flex: 1 }}
                  testID="recall-finished"
                />
              </View>
              {error ? (
                <AppText variant="caption" color={colors.error} style={{ marginTop: spacing.sm }}>
                  {error}
                </AppText>
              ) : null}
            </>
          )}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  head: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  results: { flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.lg },
  username: {
    marginTop: spacing.md,
    padding: spacing.md,
    borderRadius: radius.md,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
  },
  actions: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.md },
  loginRow: { flexDirection: "row", alignItems: "center", gap: spacing.md, marginTop: spacing.xs },
  loginKey: { width: 72 },
  loginValue: { fontFamily: fonts.semibold },
});
