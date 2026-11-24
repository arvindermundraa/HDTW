import "react-native-gesture-handler";
import { Stack } from "expo-router";
import * as SplashScreen from "expo-splash-screen";
import { useEffect } from "react";
import { LogBox } from "react-native";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { BottomSheetModalProvider } from "@gorhom/bottom-sheet";
import { KeyboardProvider } from "react-native-keyboard-controller";
import { useFonts } from "expo-font";

import { useIconFonts } from "@/src/hooks/use-icon-fonts";
import { AuthProvider } from "@/src/auth";
import { colors } from "@/src/theme";
import { PhoneFrame } from "@/src/components/PhoneFrame";

LogBox.ignoreAllLogs(true);

// Keep the native splash visible from cold start until icon fonts register.
// Required because @expo/vector-icons' componentDidMount fallback fires
// Font.loadAsync against a broken vendor path if any <Icon> mounts before
// the family is registered — which throws on Android Expo Go.
SplashScreen.preventAutoHideAsync();

export default function RootLayout() {
  const [iconsLoaded, iconsError] = useIconFonts();
  // Press Start 2P (SIL OFL) is only used inside the game screens — titles,
  // scores, round numbers and buttons. Bundled from the installed
  // @expo-google-fonts package, so it doesn't depend on a CDN at launch.
  const [fontsLoaded, fontsError] = useFonts({
    PlayfairDisplay_500Medium: require("@/assets/fonts/PlayfairDisplay-Medium.ttf"),
    PlayfairDisplay_600SemiBold: require("@/assets/fonts/PlayfairDisplay-SemiBold.ttf"),
    PlusJakartaSans_400Regular: require("@/assets/fonts/PlusJakartaSans-Regular.ttf"),
    PlusJakartaSans_500Medium: require("@/assets/fonts/PlusJakartaSans-Medium.ttf"),
    PlusJakartaSans_600SemiBold: require("@/assets/fonts/PlusJakartaSans-SemiBold.ttf"),
    PlusJakartaSans_700Bold: require("@/assets/fonts/PlusJakartaSans-Bold.ttf"),
    PressStart2P_400Regular: require("@expo-google-fonts/press-start-2p/400Regular/PressStart2P_400Regular.ttf"),
  });

  const ready = (iconsLoaded || iconsError) && (fontsLoaded || fontsError);

  useEffect(() => {
    if (ready) SplashScreen.hideAsync();
  }, [ready]);

  if (!ready) return null;

  return (
    <PhoneFrame>
    <GestureHandlerRootView style={{ flex: 1, backgroundColor: colors.surface }}>
      <SafeAreaProvider>
        <KeyboardProvider>
        <BottomSheetModalProvider>
          <AuthProvider>
            <Stack
              screenOptions={{
                headerShown: false,
                contentStyle: { backgroundColor: colors.surface },
                animation: "slide_from_right",
              }}
            >
              <Stack.Screen name="log-meal" options={{ presentation: "modal", animation: "slide_from_bottom" }} />
              <Stack.Screen name="focus-areas" options={{ presentation: "modal", animation: "slide_from_bottom" }} />
              <Stack.Screen name="goals" options={{ presentation: "modal", animation: "slide_from_bottom" }} />
              <Stack.Screen name="settings" options={{ presentation: "modal", animation: "slide_from_bottom" }} />
              <Stack.Screen name="weekly-story" options={{ presentation: "modal", animation: "slide_from_bottom" }} />
              <Stack.Screen name="build-meal" options={{ presentation: "modal", animation: "slide_from_bottom" }} />
              {/* Edit-my-profile (opened from the Settings modal) presents as a
                  modal too, so it stacks above Settings; first-time onboarding
                  stays a normal card. */}
              <Stack.Screen
                name="onboarding"
                options={({ route }) =>
                  (route.params as { mode?: string } | undefined)?.mode === "edit"
                    ? { presentation: "modal", animation: "slide_from_bottom" }
                    : {}
                }
              />
              {/* Avatar builder: a normal forward step after first-time
                  onboarding; a modal from Progress or Settings. */}
              <Stack.Screen
                name="avatar"
                options={({ route }) =>
                  (route.params as { mode?: string } | undefined)?.mode === "onboarding"
                    ? { gestureEnabled: false }
                    : { presentation: "modal", animation: "slide_from_bottom" }
                }
              />
            </Stack>
          </AuthProvider>
        </BottomSheetModalProvider>
        </KeyboardProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
    </PhoneFrame>
  );
}
