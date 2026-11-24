import React, { useEffect, useState } from "react";
import { View, StyleSheet, Pressable, ScrollView, ActivityIndicator } from "react-native";
import { useVideoPlayer, VideoView } from "expo-video";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Feather } from "@expo/vector-icons";
import { AppText, Button, Card } from "@/src/components/ui";
import { api } from "@/src/api";
import { colors, spacing, radius } from "@/src/theme";
import { goBack } from "@/src/navigation";

export default function VideoScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [video, setVideo] = useState<any>(null);
  const [completed, setCompleted] = useState(false);
  const [awarded, setAwarded] = useState<number | null>(null);
  const [showingPeer, setShowingPeer] = useState(false);

  useEffect(() => {
    api.getCurriculum().then((list: any[]) => {
      const v = list.find((x) => x.id === id);
      setVideo(v);
      setCompleted(!!v?.completed);
    });
  }, [id]);

  const player = useVideoPlayer(video?.video_url || null, (p) => {
    p.loop = false;
  });

  const watchPeerVideo = () => {
    if (!video?.peer_video) return;
    setShowingPeer(true);
    player.replace(video.peer_video.video_url);
    player.play();
  };

  const markComplete = async () => {
    const res = await api.completeVideo(id!);
    setCompleted(true);
    if (!res.already) setAwarded(res.points_awarded);
  };

  if (!video) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color={colors.brandPrimary} />
      </View>
    );
  }

  return (
    <View style={styles.c} testID="video-screen">
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable onPress={() => goBack(router, "/learn")} hitSlop={10} testID="video-back">
          <Feather name="chevron-left" size={26} color={colors.onSurface} />
        </Pressable>
        <AppText variant="label">{video.duration}</AppText>
      </View>

      <VideoView player={player} style={styles.player} contentFit="cover" allowsFullscreen nativeControls testID="video-player" />

      <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
        <AppText variant="display">{video.title}</AppText>
        <AppText variant="body" style={{ marginTop: spacing.md }}>
          {video.summary}
        </AppText>

        <AppText variant="subtitle" style={{ marginTop: spacing.xl, marginBottom: spacing.md }}>
          Key takeaways
        </AppText>
        {video.key_points.map((k: string, i: number) => (
          <View key={i} style={styles.point}>
            <View style={styles.pointNum}>
              <AppText variant="caption" color={colors.onBrandTertiary}>
                {i + 1}
              </AppText>
            </View>
            <AppText variant="body" style={{ flex: 1 }}>
              {k}
            </AppText>
          </View>
        ))}

        {awarded ? (
          <Card style={{ marginTop: spacing.xl, backgroundColor: colors.brandTertiary, borderColor: colors.brandTertiary }}>
            <AppText variant="subtitle" color={colors.onBrandTertiary}>
              +{awarded} points earned 🌱
            </AppText>
          </Card>
        ) : null}

        {/* Youth Ambassador peer-modeling segment — placed underneath the
            baseline lesson per the review notes, shown once it's been
            watched so the transition line lands after the concept. */}
        {completed && video.peer_video && (
          <Pressable onPress={watchPeerVideo} testID="peer-video-card">
            <Card style={{ marginTop: spacing.xl }}>
              <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
                <Feather name="users" size={16} color={colors.brandPrimary} />
                <AppText variant="label">YOUTH AMBASSADOR</AppText>
              </View>
              <AppText variant="body" style={{ marginTop: spacing.sm }}>
                {video.peer_video.transition_line}
              </AppText>
              <View style={{ flexDirection: "row", alignItems: "center", gap: 6, marginTop: spacing.md }}>
                <Feather name="play-circle" size={16} color={colors.brandPrimary} />
                <AppText variant="label" color={colors.brandPrimary}>
                  {showingPeer ? "Now playing" : `Watch ${video.peer_video.ambassador_name}'s video`}
                </AppText>
              </View>
            </Card>
          </Pressable>
        )}

        <View style={{ height: spacing.xl }} />
        {completed ? (
          <Button title="Completed" variant="secondary" onPress={() => goBack(router, "/learn")} testID="video-done-btn" />
        ) : (
          <Button title="Mark as watched" onPress={markComplete} testID="video-complete" />
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  c: { flex: 1, backgroundColor: colors.surface },
  center: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.surface },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.sm,
  },
  player: { width: "100%", height: 220, backgroundColor: "#000" },
  scroll: { padding: spacing.xl, paddingBottom: spacing["3xl"] },
  point: { flexDirection: "row", gap: spacing.md, alignItems: "flex-start", marginBottom: spacing.md },
  pointNum: {
    width: 24,
    height: 24,
    borderRadius: 12,
    backgroundColor: colors.brandTertiary,
    alignItems: "center",
    justifyContent: "center",
  },
});
