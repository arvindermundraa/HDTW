import React, { useState } from "react";
import { View, StyleSheet, TextInput, Pressable } from "react-native";
import { useRouter, useLocalSearchParams } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import { Feather } from "@expo/vector-icons";
import { AppText, Button } from "@/src/components/ui";
import { AuthScene } from "@/src/components/AuthScene";
import { useAuth } from "@/src/auth";
import { api } from "@/src/api";
import { colors, spacing, fonts, fontSize, radius } from "@/src/theme";
import { goBack } from "@/src/navigation";

// Sign in, create an account, and forgot password. Creating an account is
// for TAMU emails only and is confirmed with a 6-digit emailed code, as is
// "Forgot password?"; both end with the student signed in.
//
// Visuals (storybook-landscape wrapper, frosted card, floating veggies and
// drifting quotes) live in `src/components/AuthScene.tsx`. Everything the
// auth flow does — validation, requests, test IDs, error wording — is
// unchanged from before the redesign.
type Mode = "signin" | "signup" | "verify" | "forgot" | "reset";
const DOMAIN = "tamu.edu";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const MIN_PASSWORD = 6;

export default function AuthScreen() {
  const params = useLocalSearchParams<{ mode?: string }>();
  const [mode, setMode] = useState<Mode>(params.mode === "signup" ? "signup" : "signin");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(false);
  const { signIn, signUp } = useAuth();
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const go = (next: Mode) => {
    setMode(next);
    setError("");
    setShowPassword(false);
    if (next !== "reset" && next !== "verify") setNotice("");
  };

  const validEmail = () => {
    if (!EMAIL_RE.test(email.trim())) {
      setError("Please enter a valid email address.");
      return false;
    }
    return true;
  };

  const run = async (fn: () => Promise<void>) => {
    setLoading(true);
    try {
      await fn();
    } catch (e: any) {
      setError(e.message || "Something went wrong.");
    } finally {
      setLoading(false);
    }
  };

  const submitSignIn = () => {
    setError("");
    if (!email.trim() || !password) return setError("Please enter your email and password.");
    // Audit finding #22: only emptiness was checked client-side, so an
    // invalid address reached the server and surfaced a raw Pydantic
    // validation error instead of a friendly message.
    if (!validEmail()) return;
    run(async () => {
      await signIn(email.trim(), password);
      router.replace("/");
    });
  };

  const sendSignupCode = () => {
    setError("");
    if (!name.trim() || !email.trim() || !password) return setError("Please fill in your name, email and password.");
    if (!validEmail()) return;
    if (email.trim().toLowerCase().split("@")[1] !== DOMAIN) return setError(`Use your @${DOMAIN} email address.`);
    if (password.length < MIN_PASSWORD) return setError(`Choose a password with at least ${MIN_PASSWORD} characters.`);
    run(async () => {
      const res: any = await api.signupStart(email.trim());
      setNotice(res?.message || "We sent you a 6-digit code.");
      setCode("");
      go("verify");
    });
  };

  const createAccount = () => {
    setError("");
    if (code.length !== 6) return setError("Enter the 6-digit code from the email.");
    run(async () => {
      await signUp(email.trim(), password, name.trim(), code);
      router.replace("/");
    });
  };

  const sendCode = () => {
    setError("");
    if (!validEmail()) return;
    run(async () => {
      const res: any = await api.forgotPassword(email.trim());
      setNotice(res?.message || "If an account exists for that email, we sent a 6-digit code.");
      setCode("");
      setNewPassword("");
      go("reset");
    });
  };

  const submitReset = () => {
    setError("");
    if (code.length !== 6) return setError("Enter the 6-digit code from the email.");
    if (newPassword.length < MIN_PASSWORD) return setError(`Choose a password with at least ${MIN_PASSWORD} characters.`);
    run(async () => {
      await api.resetPassword(email.trim(), code, newPassword);
      // The reset signs out every other session; sign this device in.
      await signIn(email.trim(), newPassword);
      router.replace("/");
    });
  };

  const eye = (
    <Pressable
      onPress={() => setShowPassword((v) => !v)}
      hitSlop={10}
      accessibilityRole="button"
      accessibilityLabel={showPassword ? "Hide password" : "Show password"}
      testID="auth-password-toggle"
    >
      <Feather name={showPassword ? "eye-off" : "eye"} size={20} color={colors.muted} />
    </Pressable>
  );

  const link = (text: string, onPress: () => void, testID: string) => (
    <Pressable onPress={onPress} hitSlop={8} testID={testID}>
      <AppText variant="caption" color={colors.brandPrimary} style={{ fontFamily: fonts.semibold }}>
        {text}
      </AppText>
    </Pressable>
  );

  return (
    <AuthScene>
      <View style={[styles.c, { paddingTop: insets.top }]} testID="auth-screen">
        <Pressable
          onPress={() => (mode === "signin" || mode === "signup" ? goBack(router, "/welcome") : go(mode === "verify" ? "signup" : "signin"))}
          style={styles.back}
          testID="auth-back"
          accessibilityLabel="Back"
          accessibilityRole="button"
        >
          <Feather name="chevron-left" size={26} color={colors.onSurface} />
        </Pressable>
        <KeyboardAwareScrollView contentContainerStyle={styles.scroll} bottomOffset={20} showsVerticalScrollIndicator={false}>
          <View style={styles.card} testID="auth-card">
            <View style={styles.brand}>
              <AppText variant="label" color={colors.brandPrimary} style={styles.brandMark}>
                LLHS
              </AppText>
              <AppText variant="caption" style={styles.brandWelcome} testID="auth-welcome">
                Live Long, Heart Strong - Build habits your future self will thank you for.
              </AppText>
            </View>

            <AppText variant="display" style={styles.title}>
              {mode === "signin" ? "Welcome back" : mode === "signup" || mode === "verify" ? "Create your account" : "Reset your password"}
            </AppText>
            <AppText variant="body" style={styles.subtitle} testID="auth-subtitle">
              {mode === "signin"
                ? "Your future self has been waiting for you."
                : mode === "signup"
                  ? "Use your TAMU email. We'll email you a 6-digit code to confirm it."
                  : mode === "forgot"
                    ? "Enter the email you sign in with. We'll email you a 6-digit code."
                    : notice}
            </AppText>

            {mode === "signup" && (
              <Field label="Name" value={name} onChangeText={setName} placeholder="Your name" autoCapitalize="words" testID="auth-name" />
            )}

            {(mode === "signin" || mode === "signup" || mode === "forgot") && (
              <Field
                label={mode === "signup" ? "TAMU email" : "Email"}
                value={email}
                onChangeText={(v: string) => { setEmail(v); setError(""); }}
                placeholder="you@tamu.edu"
                keyboardType="email-address"
                autoCapitalize="none"
                testID="auth-email"
              />
            )}

            {mode === "signin" && (
              <>
                <Field
                  label="Password"
                  value={password}
                  onChangeText={setPassword}
                  placeholder="Your password"
                  secureTextEntry={!showPassword}
                  autoCapitalize="none"
                  autoCorrect={false}
                  testID="auth-password"
                  right={eye}
                />
                <View style={styles.forgotRow}>{link("Forgot password?", () => go("forgot"), "auth-forgot")}</View>
              </>
            )}

            {mode === "signup" && (
              <Field
                label="Password"
                value={password}
                onChangeText={(v: string) => { setPassword(v); setError(""); }}
                placeholder={`At least ${MIN_PASSWORD} characters`}
                secureTextEntry={!showPassword}
                autoCapitalize="none"
                autoCorrect={false}
                testID="auth-password"
                right={eye}
              />
            )}

            {mode === "verify" && (
              <>
                <Field
                  label="Code from the email"
                  value={code}
                  onChangeText={(v: string) => { setCode(v.replace(/\D/g, "").slice(0, 6)); setError(""); }}
                  placeholder="6 digits"
                  keyboardType="number-pad"
                  autoComplete="one-time-code"
                  testID="auth-signup-code"
                />
                <View style={styles.linkRow}>
                  {link("Send a new code", sendSignupCode, "auth-signup-resend")}
                  {link("Change email", () => go("signup"), "auth-signup-change")}
                </View>
              </>
            )}

            {mode === "reset" && (
              <>
                <Field
                  label="Code from the email"
                  value={code}
                  onChangeText={(v: string) => { setCode(v.replace(/\D/g, "").slice(0, 6)); setError(""); }}
                  placeholder="6 digits"
                  keyboardType="number-pad"
                  autoComplete="one-time-code"
                  testID="auth-reset-code"
                />
                <Field
                  label="New password"
                  value={newPassword}
                  onChangeText={(v: string) => { setNewPassword(v); setError(""); }}
                  placeholder={`At least ${MIN_PASSWORD} characters`}
                  secureTextEntry={!showPassword}
                  autoCapitalize="none"
                  autoCorrect={false}
                  testID="auth-new-password"
                  right={eye}
                />
                <View style={styles.linkRow}>
                  {link("Send a new code", sendCode, "auth-resend")}
                  {link("Use a different email", () => go("forgot"), "auth-change-email")}
                </View>
              </>
            )}

            {error ? (
              <AppText variant="caption" color={colors.error} style={{ marginTop: spacing.sm }} testID="auth-error">
                {error}
              </AppText>
            ) : null}

            <View style={{ height: spacing.lg }} />
            <Button
              title={
                mode === "signin" || mode === "signup"
                  ? "Sign in"
                  : mode === "verify"
                    ? "Verify and sign in"
                    : mode === "reset"
                      ? "Set new password"
                      : "Email me a code"
              }
              onPress={
                mode === "signin" ? submitSignIn : mode === "signup" ? sendSignupCode : mode === "verify" ? createAccount : mode === "forgot" ? sendCode : submitReset
              }
              loading={loading}
              testID="auth-submit"
            />

            {mode === "signin" ? (
              <View style={styles.backRow}>
                <AppText variant="body">
                  New here?{" "}
                  <AppText variant="body" color={colors.brandPrimary} style={{ fontFamily: fonts.semibold }} onPress={() => go("signup")} testID="auth-to-signup">
                    Create an account
                  </AppText>
                </AppText>
              </View>
            ) : mode === "signup" || mode === "verify" ? (
              <View style={styles.backRow}>
                <AppText variant="body">
                  Already have an account?{" "}
                  <AppText variant="body" color={colors.brandPrimary} style={{ fontFamily: fonts.semibold }} onPress={() => go("signin")} testID="auth-to-signin">
                    Sign in
                  </AppText>
                </AppText>
              </View>
            ) : (
              <View style={styles.backRow}>{link("Back to sign in", () => go("signin"), "auth-back-to-signin")}</View>
            )}
          </View>
        </KeyboardAwareScrollView>
      </View>
    </AuthScene>
  );
}

function Field({ label, testID, right, ...props }: any) {
  return (
    <View style={{ marginBottom: spacing.lg }}>
      <AppText variant="label" style={{ marginBottom: spacing.sm }}>
        {label}
      </AppText>
      <View style={styles.inputWrap}>
        <TextInput
          {...props}
          testID={testID}
          placeholderTextColor={colors.muted}
          style={[styles.input, right ? { paddingRight: 48 } : null]}
          accessibilityLabel={label}
        />
        {right ? <View style={styles.inputRight}>{right}</View> : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  c: { flex: 1 }, // sits on top of the AuthScene's gradient sky
  back: {
    width: 40, height: 40, borderRadius: 20,
    alignItems: "center", justifyContent: "center",
    marginLeft: spacing.md, marginTop: spacing.sm,
    backgroundColor: "rgba(255, 255, 255, 0.65)",
  },
  scroll: {
    paddingHorizontal: spacing.lg,
    // Leave a sky strip at the top so the drifting quote has room to
    // breathe above the frosted card at 390 px wide. On wider screens the
    // card centres vertically and this just becomes extra sky.
    paddingTop: spacing["2xl"],
    paddingBottom: spacing["3xl"],
    alignItems: "center",
  },
  card: {
    // Frosted, semi-transparent card centred over the storybook landscape.
    // Keeps the form at 390px (the brief's minimum) and never wider than
    // 460px so it stays legible on desktop too.
    width: "100%",
    maxWidth: 460,
    backgroundColor: "rgba(255, 255, 255, 0.88)",
    borderRadius: 20,
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing["2xl"],
    marginTop: spacing.lg,
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.6)",
    // Soft, warm shadow — stays painterly rather than UI-sharp.
    shadowColor: "#5A3C2A",
    shadowOpacity: 0.12,
    shadowRadius: 24,
    shadowOffset: { width: 0, height: 10 },
    elevation: 6,
  },
  brand: { alignItems: "center", marginBottom: spacing.lg, gap: 4 },
  brandMark: { letterSpacing: 2, fontSize: 12, fontFamily: fonts.semibold },
  brandWelcome: {
    textAlign: "center", fontSize: 13, lineHeight: 18,
    color: colors.onSurfaceSecondary,
  },
  title: { fontSize: 26, lineHeight: 32, textAlign: "center" },
  subtitle: { marginTop: spacing.sm, marginBottom: spacing.xl, textAlign: "center" },
  input: {
    backgroundColor: "rgba(255, 255, 255, 0.95)",
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    paddingHorizontal: spacing.lg,
    paddingVertical: 14,
    fontFamily: fonts.medium,
    fontSize: fontSize.lg,
    color: colors.onSurface,
  },
  inputWrap: { position: "relative", justifyContent: "center" },
  inputRight: { position: "absolute", right: spacing.lg, top: 0, bottom: 0, justifyContent: "center" },
  forgotRow: { alignItems: "flex-end", marginTop: -spacing.sm },
  linkRow: { flexDirection: "row", justifyContent: "space-between", marginTop: -spacing.sm },
  backRow: { alignItems: "center", paddingVertical: spacing.lg },
});
