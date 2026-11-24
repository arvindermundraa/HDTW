import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  View, StyleSheet, Pressable, ScrollView, ActivityIndicator, TextInput,
  RefreshControl, AppState, Platform, Image, Alert,
} from "react-native";
import { useFocusEffect } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Feather } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import * as ImagePicker from "expo-image-picker";
import { AppText, Button, Card, ProgressBar } from "@/src/components/ui";
import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { colors, radius, spacing } from "@/src/theme";
import { FOCUS_AREA_LABEL } from "@/src/food";
import { AuthImage } from "@/src/components/AuthImage";

// Full image URL — points at our Wing-scoped proxy, never a raw Blob URL.
const apiOrigin = (process.env.EXPO_PUBLIC_BACKEND_URL || "").replace(/\/+$/, "");
const photoUrl = (path?: string) => (path ? `${apiOrigin}${path}` : "");

/**
 * Social Page — Wings.
 *
 * Group-aggregate only (every number here comes from a single sum/count
 * for the whole Wing, never a per-member stat). The backend contract
 * enforces this; this screen never ferrets a workaround.
 *
 * Phase 1 of the Oct-26 lab-test build:
 *   - Explicit loading / empty / retry states (no infinite spinner).
 *   - Visibility-gated 15 s polling + pull-to-refresh via `/wings/mine/summary`.
 *   - Preset cheers (shared counters, $inc server-side).
 *   - This week's Wing challenge (deterministic per week, same for every Wing).
 *   - "Send feedback" button for lab test accounts only.
 */

type CheerPreset = { key: string; label: string };
type ReactionPreset = { key: string; label: string };

type WingPost = {
  id: string; status: "pending" | "approved" | "rejected" | "removed" | "removed_by_poster";
  caption: string; steps: string[]; focus_tag?: string | null;
  image_url: string; image_width?: number; image_height?: number;
  reactions: Record<string, number>;
  created_at: string; mine?: boolean; reported?: boolean;
  reject_reason?: string;
};

type PhotosConfig = {
  mode: "off" | "test_only" | "on";
  can_post: boolean;
  max_posts_per_day: number;
  max_bytes: number;
  guide: string;
  reactions: ReactionPreset[];
  reject_reasons: Record<string, string>;
};

type Summary = {
  wing: null | {
    id: string; name: string; member_count: number;
    progress: { current: number; target: number; achieved: boolean };
    cheers: Record<string, number>;
    cheers_total: number;
    challenge: null | {
      id: string; title: string; description: string; unit: string;
      metric: string; week_start: string; week_end: string;
      current: number; target: number; achieved: boolean;
    };
  };
  cheer_presets?: CheerPreset[];
};

const POLL_MS = 15000;

export default function Social() {
  const insets = useSafeAreaInsets();
  const { user } = useAuth();
  // `loading` is the FIRST-LOAD spinner. Once we have data (or a known
  // "no wing yet" state), it goes false forever on this mount; polls and
  // retries never re-enable the full-screen spinner.
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [wing, setWing] = useState<any>(null);
  const [summary, setSummary] = useState<Summary["wing"]>(null);
  const [cheerPresets, setCheerPresets] = useState<CheerPreset[]>([]);
  const [presets, setPresets] = useState<any[]>([]);

  const [mode, setMode] = useState<"none" | "create" | "join">("none");
  const [wingName, setWingName] = useState("");
  const [selectedMetric, setSelectedMetric] = useState<string>("");
  const [joinCode, setJoinCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [cheerBusy, setCheerBusy] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [showFeedback, setShowFeedback] = useState(false);

  // --- Phase 2: photo posts (behind WINGS_PHOTOS_MODE) ---------------------
  const [photosConfig, setPhotosConfig] = useState<PhotosConfig | null>(null);
  const [myPosts, setMyPosts] = useState<WingPost[]>([]);
  const [feed, setFeed] = useState<WingPost[]>([]);
  const [showPostSheet, setShowPostSheet] = useState(false);

  // Mount-stable "latest value seen" slot — polling callbacks read from it
  // instead of closing over stale state, which keeps re-renders cheap.
  const summaryRef = useRef<Summary["wing"]>(null);
  summaryRef.current = summary;

  const loadInitial = useCallback(async () => {
    setLoadError(null);
    try {
      const [sum, goalPresets] = await Promise.all([
        api.getMyWingSummary(),
        api.getWingGoalPresets(),
      ]);
      const typed = sum as Summary;
      setSummary(typed.wing);
      setCheerPresets(typed.cheer_presets || []);
      setPresets((goalPresets as any).presets);
      if ((goalPresets as any).presets.length && !selectedMetric) {
        setSelectedMetric((goalPresets as any).presets[0].metric);
      }
      // We also need the full wing object (members, join code) for the
      // card header. Only one extra request on first load.
      if (typed.wing) {
        const full = await api.getMyWing();
        setWing((full as any).wing);
      } else {
        setWing(null);
      }
      // Photos-phase additions — all fail soft so an older backend doesn't
      // break the Wings screen entirely.
      try {
        const cfg = (await api.getWingsPhotosConfig()) as PhotosConfig;
        setPhotosConfig(cfg);
      } catch { setPhotosConfig(null); }
      try {
        const mine = (await api.getMyWingPosts()) as any;
        setMyPosts(mine.posts || []);
      } catch { setMyPosts([]); }
      if (typed.wing) {
        try {
          const f = (await api.getWingFeed()) as any;
          setFeed(f.posts || []);
        } catch { setFeed([]); }
      } else {
        setFeed([]);
      }
    } catch (e: any) {
      setLoadError(e?.message || "Wings couldn't load.");
    } finally {
      setLoading(false);
    }
  }, [selectedMetric]);

  const refreshSummary = useCallback(async () => {
    try {
      const sum = (await api.getMyWingSummary()) as Summary;
      setSummary(sum.wing);
      if (sum.cheer_presets) setCheerPresets(sum.cheer_presets);
      setLoadError(null);
    } catch {
      // Polls fail quietly — the UI already shows the last-known values,
      // and the next poll will try again. We don't surface a transient
      // network blip as a scary banner mid-use.
    }
    // Also re-pull my-posts + feed on each poll so the student sees:
    //   * their own post flip from "Waiting for approval" to "Shared"
    //     within 15 s of a staff tap, and
    //   * new Wing-mate posts land in the feed without a manual refresh.
    try {
      const mine = (await api.getMyWingPosts()) as any;
      setMyPosts(mine.posts || []);
    } catch {}
    try {
      const f = (await api.getWingFeed()) as any;
      setFeed(f.posts || []);
    } catch {}
  }, []);

  useEffect(() => {
    loadInitial();
  }, [loadInitial]);

  // Visibility-gated polling: only runs while the Wings screen is focused
  // AND the app is in the foreground. Each poll fetches ~1 KB.
  useFocusEffect(
    useCallback(() => {
      let timer: ReturnType<typeof setInterval> | null = null;
      let appStateSub: { remove: () => void } | null = null;

      const start = () => {
        if (timer) return;
        timer = setInterval(refreshSummary, POLL_MS);
      };
      const stop = () => {
        if (timer) { clearInterval(timer); timer = null; }
      };
      // Honour the device's foreground/background state too (if the
      // student switches away from the app without leaving the tab).
      const onAppState = (next: string) => {
        if (next === "active") start();
        else stop();
      };
      appStateSub = AppState.addEventListener?.("change", onAppState) as any;
      start();
      // Also kick a fresh poll immediately on focus — don't wait 15 s.
      refreshSummary();
      return () => {
        stop();
        appStateSub?.remove?.();
      };
    }, [refreshSummary])
  );

  const onRefresh = async () => {
    setRefreshing(true);
    try {
      await refreshSummary();
    } finally {
      setRefreshing(false);
    }
  };

  const create = async () => {
    if (wingName.trim().length < 2 || !selectedMetric) return;
    setBusy(true); setError("");
    try {
      const res: any = await api.createWing(wingName.trim(), selectedMetric);
      setWing(res);
      // Refresh the summary so the challenge/cheers slots populate too.
      await refreshSummary();
      setMode("none"); setWingName("");
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
    } catch (e: any) {
      setError(e?.message || "Couldn't create that wing.");
    } finally { setBusy(false); }
  };

  const join = async () => {
    if (joinCode.trim().length < 6) return;
    setBusy(true); setError("");
    try {
      const res: any = await api.joinWing(joinCode.trim().toUpperCase());
      setWing(res);
      await refreshSummary();
      setMode("none"); setJoinCode("");
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
    } catch (e: any) {
      setError(e?.message || "Couldn't join that wing.");
    } finally { setBusy(false); }
  };

  const leave = async () => {
    setBusy(true);
    try {
      await api.leaveWing();
      setWing(null);
      setSummary(null);
    } finally { setBusy(false); }
  };

  const sendCheer = async (key: string) => {
    if (cheerBusy) return;
    setCheerBusy(key);
    // Optimistic bump — the server does the real $inc; this just keeps the
    // tap-to-render loop snappy during the lab test. If the request fails
    // the next poll corrects it.
    if (summary) {
      setSummary({
        ...summary,
        cheers: { ...summary.cheers, [key]: (summary.cheers?.[key] || 0) + 1 },
        cheers_total: (summary.cheers_total || 0) + 1,
      });
    }
    try {
      const res: any = await api.sendWingCheer(key);
      if (summary && res?.cheers) {
        setSummary({ ...summary, cheers: res.cheers, cheers_total: res.cheers_total });
      }
      Haptics.selectionAsync?.().catch(() => {});
    } catch {
      // Roll back the optimistic bump on failure.
      await refreshSummary();
    } finally {
      setCheerBusy(null);
    }
  };

  // ---- Render -----------------------------------------------------------
  if (loading) {
    return (
      <View style={[styles.c, styles.center]} testID="social-loading">
        <ActivityIndicator color={colors.brandPrimary} />
        <AppText variant="caption" style={{ marginTop: spacing.md }}>Loading Wings…</AppText>
      </View>
    );
  }

  if (loadError && !summary && !wing) {
    return (
      <View style={[styles.c, styles.center, { paddingHorizontal: spacing.xl }]} testID="social-error">
        <Feather name="cloud-off" size={28} color={colors.muted} />
        <AppText variant="subtitle" style={{ marginTop: spacing.md, textAlign: "center" }}>
          Wings didn&apos;t load this time
        </AppText>
        <AppText variant="caption" style={{ marginTop: spacing.sm, textAlign: "center" }}>
          Check your connection and try again. Nothing was lost.
        </AppText>
        <Button
          title="Try again"
          onPress={() => { setLoading(true); loadInitial(); }}
          style={{ marginTop: spacing.xl, paddingHorizontal: spacing["2xl"] }}
          testID="social-retry"
        />
      </View>
    );
  }

  const isTest = !!(user as any)?.is_test_account || (user?.email || "").toLowerCase().endsWith("@example.com");

  return (
    <View style={styles.c} testID="social-screen">
      <ScrollView
        contentContainerStyle={[styles.scroll, { paddingTop: insets.top + spacing.lg }]}
        showsVerticalScrollIndicator={false}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.brandPrimary} />}
      >
        <AppText variant="label" color={colors.brandPrimary}>SOCIAL</AppText>
        <AppText variant="display" style={{ marginTop: spacing.sm }}>Wings</AppText>
        <AppText variant="body" style={{ marginTop: spacing.sm }}>
          Move toward a shared goal together — never against each other.
        </AppText>

        {wing ? (
          <>
            <WingCard
              wing={wing}
              summary={summary}
              presets={cheerPresets}
              onCheer={sendCheer}
              cheerBusy={cheerBusy}
              onLeave={leave}
              busy={busy}
            />
            <ChallengeCard challenge={summary?.challenge ?? null} />

            {/* Share-a-meal: gated by WINGS_PHOTOS_MODE on the server, and
                re-gated here against photosConfig.can_post. "test_only" mode
                means only is_test_account students see this. */}
            {photosConfig?.can_post && (
              <Button
                title="Share a meal"
                onPress={() => setShowPostSheet(true)}
                style={{ marginTop: spacing.lg }}
                testID="social-share-meal"
              />
            )}

            {/* My recent posts strip: shows own posts with their moderation
                state. Only the poster sees pending / rejected; everyone
                else only ever sees approved posts, in the feed below. */}
            {myPosts.length > 0 && (
              <MyPostsStrip
                posts={myPosts.filter((p) => p.status !== "removed_by_poster")}
                onDelete={async (postId) => {
                  try {
                    await api.deleteWingPost(postId);
                    setMyPosts((xs) => xs.filter((p) => p.id !== postId));
                    setFeed((xs) => xs.filter((p) => p.id !== postId));
                  } catch {}
                }}
              />
            )}

            {/* Wing kitchen: approved posts in the student's own Wing. The
                backend filters by wing_id and status=="approved" and
                never surfaces reported posts, so this feed is already
                scoped — this view just renders what came back. */}
            <WingKitchen
              feed={feed}
              reactions={photosConfig?.reactions || []}
              onReact={async (postId, key) => {
                // Optimistic bump; server owns the truth via $inc, next
                // poll corrects any mismatch.
                setFeed((xs) => xs.map((p) => p.id === postId
                  ? { ...p, reactions: { ...p.reactions, [key]: (p.reactions?.[key] || 0) + 1 } }
                  : p));
                try { await api.reactToWingPost(postId, key); } catch {}
              }}
              onReport={async (postId) => {
                // Reporting hides the post for everyone until staff
                // re-review, so we drop it from this feed immediately.
                try {
                  await api.reportWingPost(postId);
                  setFeed((xs) => xs.filter((p) => p.id !== postId));
                } catch {}
              }}
            />

            {isTest && (
              <Button
                title="Send feedback"
                variant="secondary"
                onPress={() => setShowFeedback(true)}
                style={{ marginTop: spacing.lg }}
                testID="social-feedback-open"
              />
            )}
          </>
        ) : mode === "none" ? (
          <View style={{ marginTop: spacing.xl, gap: spacing.md }} testID="social-empty">
            <Card>
              <AppText variant="subtitle">You&apos;re not in a Wing yet</AppText>
              <AppText variant="caption" style={{ marginTop: spacing.sm }}>
                A Wing is a small group of students working toward one shared goal — no rankings, no stats about individual people.
              </AppText>
            </Card>
            <Button title="Create a wing" onPress={() => setMode("create")} testID="social-create-btn" />
            <Button title="Join a wing" variant="secondary" onPress={() => setMode("join")} testID="social-join-btn" />
          </View>
        ) : mode === "create" ? (
          <Card style={{ marginTop: spacing.xl }}>
            <AppText variant="label" style={{ marginBottom: spacing.sm }}>WING NAME</AppText>
            <TextInput
              value={wingName}
              onChangeText={setWingName}
              placeholder="e.g. Dunn Hall 3rd Floor"
              placeholderTextColor={colors.muted}
              maxLength={40}
              style={styles.input}
              testID="wing-name-input"
              accessibilityLabel="Wing name"
            />
            <AppText variant="label" style={{ marginTop: spacing.lg, marginBottom: spacing.sm }}>SHARED GOAL</AppText>
            <View style={{ gap: spacing.sm }}>
              {presets.map((p) => (
                <Pressable
                  key={p.metric}
                  onPress={() => setSelectedMetric(p.metric)}
                  style={[styles.goalOption, selectedMetric === p.metric && styles.goalOptionActive]}
                  testID={`goal-${p.metric}`}
                  accessibilityRole="radio"
                  accessibilityState={{ selected: selectedMetric === p.metric }}
                >
                  <AppText variant="body">{p.label}</AppText>
                  <AppText variant="caption" style={{ marginTop: 2 }}>
                    Wing target: {p.default_target} {p.unit}
                  </AppText>
                </Pressable>
              ))}
            </View>
            {!!error && (
              <AppText variant="caption" color={colors.warning} style={{ marginTop: spacing.md }}>{error}</AppText>
            )}
            <View style={{ flexDirection: "row", gap: spacing.sm, marginTop: spacing.xl }}>
              <Button title="Cancel" variant="secondary" onPress={() => setMode("none")} style={{ flex: 1 }} />
              <Button
                title={busy ? "Creating…" : "Create wing"}
                onPress={create}
                disabled={busy || wingName.trim().length < 2}
                style={{ flex: 1 }}
                testID="wing-create-submit"
              />
            </View>
          </Card>
        ) : (
          <Card style={{ marginTop: spacing.xl }}>
            <AppText variant="label" style={{ marginBottom: spacing.sm }}>JOIN CODE</AppText>
            <TextInput
              value={joinCode}
              onChangeText={(t) => setJoinCode(t.toUpperCase())}
              placeholder="ABC123"
              placeholderTextColor={colors.muted}
              autoCapitalize="characters"
              maxLength={8}
              style={styles.input}
              testID="wing-join-input"
              accessibilityLabel="Wing join code"
            />
            {!!error && (
              <AppText variant="caption" color={colors.warning} style={{ marginTop: spacing.md }}>{error}</AppText>
            )}
            <View style={{ flexDirection: "row", gap: spacing.sm, marginTop: spacing.xl }}>
              <Button title="Cancel" variant="secondary" onPress={() => setMode("none")} style={{ flex: 1 }} />
              <Button
                title={busy ? "Joining…" : "Join wing"}
                onPress={join}
                disabled={busy || joinCode.trim().length < 6}
                style={{ flex: 1 }}
                testID="wing-join-submit"
              />
            </View>
          </Card>
        )}

        <View style={{ height: spacing["3xl"] }} />
      </ScrollView>

      {showFeedback && (
        <FeedbackSheet onClose={() => setShowFeedback(false)} />
      )}
      {showPostSheet && photosConfig && (
        <PostSheet
          config={photosConfig}
          defaultFocus={(user as any)?.focus_area ?? null}
          onClose={() => setShowPostSheet(false)}
          onPosted={(created) => {
            setMyPosts((xs) => [created, ...xs]);
            setShowPostSheet(false);
          }}
        />
      )}
    </View>
  );
}

// -------- Wing card: progress + cheers --------------------------------------
function WingCard({
  wing, summary, presets, onCheer, cheerBusy, onLeave, busy,
}: {
  wing: any;
  summary: Summary["wing"];
  presets: CheerPreset[];
  onCheer: (key: string) => void;
  cheerBusy: string | null;
  onLeave: () => void;
  busy: boolean;
}) {
  const progress = summary?.progress ?? wing.progress;
  const memberCount = summary?.member_count ?? wing.members?.length ?? 1;
  const cheers = summary?.cheers ?? {};
  const cheersTotal = summary?.cheers_total ?? 0;

  return (
    <Card style={{ marginTop: spacing.xl }} testID="wing-card">
      <View style={styles.rowBetween}>
        <View style={{ flex: 1 }}>
          <AppText variant="subtitle">{wing.name}</AppText>
          <AppText variant="caption" style={{ marginTop: 2 }}>
            {memberCount} member{memberCount === 1 ? "" : "s"} · code {wing.join_code}
          </AppText>
        </View>
        {progress.achieved && (
          <View style={styles.achievedBadge}>
            <Feather name="check" size={14} color={colors.onBrandPrimary} />
          </View>
        )}
      </View>

      <View style={{ marginTop: spacing.lg }}>
        <View style={styles.rowBetween}>
          <AppText variant="caption">{wing.goal_label}</AppText>
          <AppText variant="caption">
            Our Wing: {progress.current} / {progress.target} {wing.goal_unit}
          </AppText>
        </View>
        <View style={{ marginTop: spacing.sm }}>
          <ProgressBar value={progress.current} max={progress.target} height={10} />
        </View>
      </View>

      {presets.length > 0 && (
        <View style={{ marginTop: spacing.xl }}>
          <AppText variant="label" style={{ marginBottom: spacing.sm }}>
            CHEERS · {cheersTotal} total
          </AppText>
          <View style={styles.cheerRow} testID="cheers-row">
            {presets.map((p) => (
              <Pressable
                key={p.key}
                onPress={() => onCheer(p.key)}
                disabled={cheerBusy !== null}
                style={[styles.cheerBtn, cheerBusy === p.key && styles.cheerBtnBusy]}
                testID={`cheer-${p.key}`}
                accessibilityRole="button"
                accessibilityLabel={`${p.label}, ${cheers[p.key] || 0}`}
              >
                <AppText variant="label" color={colors.onSurface}>{p.label}</AppText>
                <AppText variant="caption" style={{ marginTop: 2 }}>{cheers[p.key] || 0}</AppText>
              </Pressable>
            ))}
          </View>
          <AppText variant="caption" style={{ marginTop: spacing.sm, color: colors.onSurfaceSecondary }}>
            Cheers are counted for the whole Wing — never shown as who tapped.
          </AppText>
        </View>
      )}

      <Button title="Leave wing" variant="secondary" onPress={onLeave} disabled={busy}
              style={{ marginTop: spacing.xl }} testID="wing-leave" />
    </Card>
  );
}

// -------- Weekly challenge card --------------------------------------------
type ChallengeShape = NonNullable<NonNullable<Summary["wing"]>["challenge"]>;
function ChallengeCard({ challenge }: { challenge: ChallengeShape | null }) {
  if (!challenge) return null;
  return (
    <Card style={{ marginTop: spacing.lg }} testID="challenge-card">
      <AppText variant="label" color={colors.brandPrimary}>THIS WEEK&apos;S CHALLENGE</AppText>
      <AppText variant="subtitle" style={{ marginTop: spacing.sm }}>{challenge.title}</AppText>
      <AppText variant="caption" style={{ marginTop: spacing.sm }}>{challenge.description}</AppText>
      <View style={{ marginTop: spacing.md }}>
        <View style={styles.rowBetween}>
          <AppText variant="caption">Our Wing</AppText>
          <AppText variant="caption">
            {challenge.current} / {challenge.target} {challenge.unit}
          </AppText>
        </View>
        <View style={{ marginTop: spacing.sm }}>
          <ProgressBar value={challenge.current} max={challenge.target} height={8} />
        </View>
      </View>
      {challenge.achieved && (
        <AppText variant="body" color={colors.brandPrimary} style={{ marginTop: spacing.md }}>
          Done together — nice.
        </AppText>
      )}
    </Card>
  );
}

// -------- Feedback sheet (is_test only) ------------------------------------
function FeedbackSheet({ onClose }: { onClose: () => void }) {
  const [doing, setDoing] = useState("");
  const [happened, setHappened] = useState("");
  const [rating, setRating] = useState<number | null>(null);
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const [err, setErr] = useState("");

  const device = Platform.OS === "web"
    ? `web (${typeof navigator !== "undefined" ? navigator.userAgent.slice(0, 60) : "unknown"})`
    : Platform.OS;

  const send = async () => {
    setErr(""); setSending(true);
    try {
      await api.sendLabFeedback({
        screen: "wings", device,
        what_doing: doing.trim(), what_happened: happened.trim(),
        rating,
      });
      setSent(true);
    } catch (e: any) {
      setErr(e?.message || "Couldn't send that just now.");
    } finally {
      setSending(false);
    }
  };

  return (
    <View style={styles.sheetBackdrop} testID="feedback-sheet">
      <View style={styles.sheet}>
        {sent ? (
          <>
            <AppText variant="subtitle">Thanks for the note.</AppText>
            <AppText variant="caption" style={{ marginTop: spacing.sm }}>
              Your feedback was saved for the test session.
            </AppText>
            <Button title="Close" onPress={onClose} style={{ marginTop: spacing.lg }} />
          </>
        ) : (
          <>
            <AppText variant="subtitle">Lab test feedback</AppText>
            <AppText variant="caption" style={{ marginTop: spacing.xs }}>
              Only used during the test. Not research data.
            </AppText>
            <AppText variant="label" style={{ marginTop: spacing.md, marginBottom: spacing.xs }}>
              What were you doing?
            </AppText>
            <TextInput
              value={doing} onChangeText={setDoing}
              placeholder="e.g. tapped Cheer three times in a row"
              placeholderTextColor={colors.muted}
              style={styles.input}
              multiline
              testID="feedback-doing"
              accessibilityLabel="What were you doing?"
            />
            <AppText variant="label" style={{ marginTop: spacing.md, marginBottom: spacing.xs }}>
              What happened?
            </AppText>
            <TextInput
              value={happened} onChangeText={setHappened}
              placeholder="e.g. the counter didn't update until I pulled to refresh"
              placeholderTextColor={colors.muted}
              style={[styles.input, { minHeight: 80 }]}
              multiline
              testID="feedback-happened"
              accessibilityLabel="What happened?"
            />
            <AppText variant="label" style={{ marginTop: spacing.md, marginBottom: spacing.xs }}>
              Rating (optional)
            </AppText>
            <View style={{ flexDirection: "row", gap: spacing.sm }}>
              {[1, 2, 3, 4, 5].map((n) => (
                <Pressable
                  key={n}
                  onPress={() => setRating(rating === n ? null : n)}
                  style={[styles.ratingBtn, rating === n && styles.ratingBtnActive]}
                  accessibilityRole="button"
                  accessibilityLabel={`${n} out of 5`}
                  testID={`feedback-rating-${n}`}
                >
                  <AppText variant="label" color={rating === n ? colors.onBrandPrimary : colors.onSurface}>
                    {n}
                  </AppText>
                </Pressable>
              ))}
            </View>
            {!!err && (
              <AppText variant="caption" color={colors.error} style={{ marginTop: spacing.sm }}>{err}</AppText>
            )}
            <View style={{ flexDirection: "row", gap: spacing.sm, marginTop: spacing.lg }}>
              <Button title="Close" variant="secondary" onPress={onClose} style={{ flex: 1 }} />
              <Button
                title={sending ? "Sending…" : "Send"}
                onPress={send}
                disabled={sending || !doing.trim() || !happened.trim()}
                style={{ flex: 1 }}
                testID="feedback-submit"
              />
            </View>
          </>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  c: { flex: 1, backgroundColor: colors.surface },
  center: { alignItems: "center", justifyContent: "center" },
  scroll: { paddingHorizontal: spacing.xl, paddingBottom: spacing["3xl"] },
  rowBetween: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  input: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md,
    color: colors.onSurface,
    backgroundColor: colors.surface,
  },
  goalOption: {
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.md,
    padding: spacing.md, backgroundColor: colors.surfaceSecondary,
  },
  goalOptionActive: { borderColor: colors.brandPrimary, backgroundColor: colors.surface },
  achievedBadge: {
    width: 28, height: 28, borderRadius: 14,
    backgroundColor: colors.brandPrimary,
    alignItems: "center", justifyContent: "center",
  },
  cheerRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  cheerBtn: {
    flexGrow: 1, minWidth: 100, alignItems: "center",
    paddingVertical: spacing.md, paddingHorizontal: spacing.md,
    borderRadius: radius.md,
    backgroundColor: colors.surfaceSecondary,
    borderWidth: 1, borderColor: colors.border,
  },
  cheerBtnBusy: { opacity: 0.6 },
  sheetBackdrop: {
    position: "absolute", left: 0, right: 0, top: 0, bottom: 0,
    backgroundColor: "rgba(0,0,0,0.4)", justifyContent: "flex-end",
  },
  sheet: {
    backgroundColor: colors.surface,
    borderTopLeftRadius: 20, borderTopRightRadius: 20,
    padding: spacing.xl, gap: 2,
  },
  ratingBtn: {
    width: 44, height: 44, borderRadius: 22,
    borderWidth: 1, borderColor: colors.border,
    backgroundColor: colors.surfaceSecondary,
    alignItems: "center", justifyContent: "center",
  },
  ratingBtnActive: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  // --- Photo post UI (Phase 2) --------------------------------------------
  postThumb: {
    width: 100, height: 100, borderRadius: radius.md,
    backgroundColor: colors.surfaceTertiary,
  },
  statusChip: {
    alignSelf: "flex-start", borderRadius: radius.pill,
    paddingHorizontal: 10, paddingVertical: 2,
    borderWidth: 1, borderColor: colors.border,
  },
  feedCard: {
    marginTop: spacing.md, padding: spacing.lg,
    backgroundColor: colors.surfaceSecondary,
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.md,
    gap: spacing.sm,
  },
  feedImage: {
    width: "100%", aspectRatio: 1, borderRadius: radius.md,
    backgroundColor: colors.surfaceTertiary,
  },
  reactionBtn: {
    flexGrow: 1, minWidth: 110, alignItems: "center",
    paddingVertical: spacing.sm, paddingHorizontal: spacing.sm,
    borderRadius: radius.md,
    backgroundColor: colors.surface,
    borderWidth: 1, borderColor: colors.border,
  },
  previewBox: {
    width: "100%", aspectRatio: 1, borderRadius: radius.md,
    backgroundColor: colors.surfaceTertiary,
    alignItems: "center", justifyContent: "center",
  },
});

// -------- My recent posts: status chips + delete ---------------------------
function statusLabel(status: WingPost["status"], reported?: boolean): { label: string; color: string } {
  if (reported && status !== "rejected") return { label: "Hidden while we re-check", color: colors.warning };
  switch (status) {
    case "pending":  return { label: "Waiting for approval", color: colors.warning };
    case "approved": return { label: "Shared with your Wing", color: colors.brandPrimary };
    case "rejected": return { label: "Not shared", color: colors.error };
    case "removed":  return { label: "Taken down by staff", color: colors.muted };
    default:         return { label: "", color: colors.muted };
  }
}

function MyPostsStrip({ posts, onDelete }: { posts: WingPost[]; onDelete: (postId: string) => void }) {
  if (!posts.length) return null;
  return (
    <View style={{ marginTop: spacing.lg }} testID="my-posts-strip">
      <AppText variant="label" style={{ marginBottom: spacing.sm }}>MY RECENT POSTS</AppText>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.sm }}>
        {posts.map((p) => {
          const s = statusLabel(p.status, p.reported);
          return (
            <View key={p.id} style={{ width: 120 }} testID={`my-post-${p.id}`}>
              {p.image_url ? (
                <AuthImage uri={photoUrl(p.image_url)} style={styles.postThumb} />
              ) : (
                <View style={styles.postThumb} />
              )}
              <View style={[styles.statusChip, { marginTop: 6, borderColor: s.color }]}>
                <AppText variant="label" color={s.color} style={{ fontSize: 11 }}>
                  {s.label}
                </AppText>
              </View>
              {p.status === "rejected" && p.reject_reason && (
                <AppText variant="caption" style={{ fontSize: 11, marginTop: 4 }}>{p.reject_reason}</AppText>
              )}
              <Pressable onPress={() => onDelete(p.id)} hitSlop={8} style={{ marginTop: 4 }} testID={`delete-post-${p.id}`}>
                <AppText variant="label" color={colors.muted} style={{ fontSize: 11 }}>Delete</AppText>
              </Pressable>
            </View>
          );
        })}
      </ScrollView>
    </View>
  );
}

// -------- Wing kitchen feed: approved posts + reactions + report -----------
function WingKitchen({
  feed, reactions, onReact, onReport,
}: {
  feed: WingPost[]; reactions: ReactionPreset[];
  onReact: (postId: string, key: string) => void;
  onReport: (postId: string) => void;
}) {
  if (!feed.length) return null;
  return (
    <View style={{ marginTop: spacing.lg }} testID="wing-kitchen">
      <AppText variant="label" style={{ marginBottom: spacing.xs }}>WING KITCHEN</AppText>
      <AppText variant="caption" style={{ marginBottom: spacing.sm }}>
        What your Wing is cooking. Only approved posts from your Wing — reactions are counted, never named.
      </AppText>
      {feed.map((p) => (
        <View key={p.id} style={styles.feedCard} testID={`feed-post-${p.id}`}>
          {p.image_url ? (
            <AuthImage
              uri={photoUrl(p.image_url)}
              style={styles.feedImage}
              accessibilityLabel="A food photo shared by a wing member"
              resizeMode="cover"
            />
          ) : null}
          {!!p.focus_tag && (
            <View style={[styles.statusChip, { borderColor: colors.brandPrimary }]}>
              <AppText variant="label" color={colors.brandPrimary} style={{ fontSize: 11 }}>
                Focus: {FOCUS_AREA_LABEL[p.focus_tag] ?? p.focus_tag}
              </AppText>
            </View>
          )}
          {!!p.caption && <AppText variant="body">{p.caption}</AppText>}
          {p.steps && p.steps.length > 0 && (
            <View style={{ gap: 2 }}>
              <AppText variant="label" style={{ fontSize: 11 }}>HOW I MADE IT</AppText>
              {p.steps.map((s, i) => (
                <AppText key={i} variant="caption" style={{ fontSize: 12 }}>
                  {i + 1}. {s}
                </AppText>
              ))}
            </View>
          )}
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginTop: 4 }} testID={`reactions-${p.id}`}>
            {reactions.map((r) => (
              <Pressable
                key={r.key}
                onPress={() => onReact(p.id, r.key)}
                style={styles.reactionBtn}
                accessibilityRole="button"
                accessibilityLabel={`${r.label}, ${p.reactions?.[r.key] || 0} so far`}
                testID={`react-${p.id}-${r.key}`}
              >
                <AppText variant="label" color={colors.onSurface} style={{ fontSize: 12 }}>{r.label}</AppText>
                <AppText variant="caption" style={{ marginTop: 2 }}>{p.reactions?.[r.key] || 0}</AppText>
              </Pressable>
            ))}
          </View>
          <Pressable onPress={() => onReport(p.id)} hitSlop={8} style={{ alignSelf: "flex-end" }} testID={`report-${p.id}`}>
            <AppText variant="label" color={colors.muted} style={{ fontSize: 12 }}>Report</AppText>
          </Pressable>
        </View>
      ))}
    </View>
  );
}

// -------- Posting sheet: pick photo, caption, steps, focus tag -------------
const FOCUS_PICK_ORDER = [
  "total_fruits", "total_vegetables", "whole_grains", "dairy",
  "total_protein_foods", "seafood_plant_proteins", "fatty_acids",
  "added_sugars", "sodium", "refined_grains", "saturated_fats",
];

function PostSheet({
  config, defaultFocus, onClose, onPosted,
}: {
  config: PhotosConfig;
  defaultFocus: string | null;
  onClose: () => void;
  onPosted: (post: WingPost) => void;
}) {
  const [guideOpen, setGuideOpen] = useState(true);
  const [asset, setAsset] = useState<null | { uri: string; name: string; type: string; file?: File }>(null);
  const [caption, setCaption] = useState("");
  const [steps, setSteps] = useState<string[]>([""]);
  const [focusTag, setFocusTag] = useState<string | null>(defaultFocus);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const pickPhoto = async () => {
    setError("");
    try {
      const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (perm.status !== "granted" && Platform.OS !== "web") {
        setError("We need photo-library access to pick an image.");
        return;
      }
      const res = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ["images"],
        quality: 0.9,
        base64: false,
        exif: false, // we strip server-side too, but ask the picker not to attach it
      });
      if (res.canceled || !res.assets?.length) return;
      const a = res.assets[0];
      const name = a.fileName || "photo.jpg";
      const type = a.mimeType || "image/jpeg";
      if (Platform.OS === "web") {
        // On web the picker gives a blob: URL; fetch bytes into a File so
        // the multipart upload carries real content, not a URL ref.
        const resp = await fetch(a.uri);
        const blob = await resp.blob();
        const file = new File([blob], name, { type: blob.type || type });
        setAsset({ uri: a.uri, name, type: file.type, file });
      } else {
        setAsset({ uri: a.uri, name, type });
      }
    } catch (e: any) {
      setError(e?.message || "Couldn't open the photo picker.");
    }
  };

  const setStep = (i: number, v: string) => setSteps((xs) => xs.map((s, j) => (j === i ? v : s)));
  const addStep = () => setSteps((xs) => (xs.length >= 5 ? xs : [...xs, ""]));
  const dropStep = (i: number) => setSteps((xs) => (xs.length === 1 ? [""] : xs.filter((_, j) => j !== i)));

  const submit = async () => {
    setError("");
    if (!asset) { setError("Pick a photo first."); return; }
    if (!caption.trim()) { setError("Add a short caption."); return; }
    setBusy(true);
    try {
      const cleanedSteps = steps.map((s) => s.trim()).filter(Boolean).slice(0, 5);
      const file = asset.file ? asset.file : { uri: asset.uri, name: asset.name, type: asset.type };
      const created = (await api.uploadWingPost({ file, caption: caption.trim(), steps: cleanedSteps, focusTag })) as WingPost;
      Haptics.notificationAsync?.(Haptics.NotificationFeedbackType.Success).catch(() => {});
      onPosted(created);
    } catch (e: any) {
      setError(e?.message || "Couldn't share that just now.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={styles.sheetBackdrop} testID="post-sheet">
      <ScrollView
        style={{ maxHeight: "92%" }}
        contentContainerStyle={styles.sheet}
        keyboardShouldPersistTaps="handled"
      >
        <AppText variant="subtitle">Share a meal</AppText>
        <AppText variant="caption" style={{ marginTop: 2 }}>
          Only approved posts appear in your Wing. Review usually takes a few minutes during the lab test.
        </AppText>

        <Pressable
          onPress={() => setGuideOpen((v) => !v)}
          style={{ marginTop: spacing.md, flexDirection: "row", alignItems: "center", gap: 6 }}
          testID="post-guide-toggle"
        >
          <Feather name={guideOpen ? "chevron-down" : "chevron-right"} size={16} color={colors.brandPrimary} />
          <AppText variant="label" color={colors.brandPrimary} style={{ fontSize: 13 }}>
            Posting guide
          </AppText>
        </Pressable>
        {guideOpen && (
          <AppText variant="caption" style={{ marginTop: 4, lineHeight: 18 }} testID="post-guide-text">
            {config.guide}
          </AppText>
        )}

        <View style={{ marginTop: spacing.md }}>
          <Pressable onPress={pickPhoto} style={styles.previewBox} testID="post-pick-photo" accessibilityLabel="Pick a photo">
            {asset ? (
              <Image source={{ uri: asset.uri }} style={styles.feedImage} resizeMode="cover" />
            ) : (
              <View style={{ alignItems: "center", gap: 6 }}>
                <Feather name="camera" size={24} color={colors.muted} />
                <AppText variant="label" color={colors.muted}>Tap to pick a food photo</AppText>
                <AppText variant="caption" style={{ fontSize: 11 }}>JPG, PNG or HEIC · max 5 MB</AppText>
              </View>
            )}
          </Pressable>
        </View>

        <AppText variant="label" style={{ marginTop: spacing.md, marginBottom: spacing.xs }}>Caption</AppText>
        <TextInput
          value={caption} onChangeText={setCaption}
          placeholder="What's on the plate?"
          placeholderTextColor={colors.muted}
          maxLength={200}
          multiline
          style={styles.input}
          testID="post-caption"
          accessibilityLabel="Caption"
        />
        <AppText variant="caption" style={{ fontSize: 11, textAlign: "right" }}>{caption.length}/200</AppText>

        <AppText variant="label" style={{ marginTop: spacing.sm, marginBottom: spacing.xs }}>
          How I made it (optional)
        </AppText>
        {steps.map((s, i) => (
          <View key={i} style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm, marginBottom: 6 }}>
            <TextInput
              value={s} onChangeText={(v) => setStep(i, v)}
              placeholder={`Step ${i + 1}`}
              placeholderTextColor={colors.muted}
              maxLength={80}
              style={[styles.input, { flex: 1 }]}
              testID={`post-step-${i}`}
            />
            {(steps.length > 1 || s) && (
              <Pressable onPress={() => dropStep(i)} hitSlop={8} testID={`post-step-remove-${i}`}>
                <Feather name="x" size={18} color={colors.muted} />
              </Pressable>
            )}
          </View>
        ))}
        {steps.length < 5 && (
          <Pressable onPress={addStep} hitSlop={6} testID="post-add-step">
            <AppText variant="label" color={colors.brandPrimary} style={{ fontSize: 13 }}>+ Add step</AppText>
          </Pressable>
        )}

        <AppText variant="label" style={{ marginTop: spacing.md, marginBottom: spacing.xs }}>Focus area (optional)</AppText>
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm }}>
          <Pressable
            onPress={() => setFocusTag(null)}
            style={[styles.goalOption, focusTag === null && styles.goalOptionActive, { paddingVertical: 8, paddingHorizontal: 12 }]}
            testID="post-focus-none"
          >
            <AppText variant="label" style={{ fontSize: 12 }}>No tag</AppText>
          </Pressable>
          {FOCUS_PICK_ORDER.map((id) => (
            <Pressable
              key={id}
              onPress={() => setFocusTag(id)}
              style={[styles.goalOption, focusTag === id && styles.goalOptionActive, { paddingVertical: 8, paddingHorizontal: 12 }]}
              testID={`post-focus-${id}`}
            >
              <AppText variant="label" style={{ fontSize: 12 }}>{FOCUS_AREA_LABEL[id] ?? id}</AppText>
            </Pressable>
          ))}
        </View>

        {!!error && (
          <AppText variant="caption" color={colors.error} style={{ marginTop: spacing.md }} testID="post-error">
            {error}
          </AppText>
        )}

        <View style={{ flexDirection: "row", gap: spacing.sm, marginTop: spacing.lg }}>
          <Button title="Cancel" variant="secondary" onPress={onClose} style={{ flex: 1 }} testID="post-cancel" />
          <Button
            title={busy ? "Sharing…" : "Share"}
            onPress={submit}
            disabled={busy || !asset || !caption.trim()}
            style={{ flex: 1 }}
            testID="post-submit"
          />
        </View>
      </ScrollView>
    </View>
  );
}
