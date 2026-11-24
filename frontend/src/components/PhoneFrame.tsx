import { createContext, useContext, useEffect, useState, type PropsWithChildren } from "react";
import { Platform, StyleSheet, Text, View, useWindowDimensions } from "react-native";

import { colors, fonts } from "@/src/theme";

// On a desktop browser the app is shown inside a phone-sized frame, so the
// web build looks the way participants see it in the mobile app. Real
// phones (and narrow browser windows) stay full screen. `?fullscreen=1`
// in the URL turns the frame off, e.g. for staff screenshots.
const FRAME_BREAKPOINT = 700; // window width at which the frame appears
const PHONE_W = 390; // iPhone 14/15 logical size
const PHONE_H = 844;
const BEZEL = 12;
const STATUS_H = 30;
const HOME_H = 22;
const MARGIN = 24; // space above and below the frame

type Size = { width: number; height: number };
const ScreenSize = createContext<Size | null>(null);

/** Width and height of the app's screen: the phone frame's on desktop web,
 *  the window's everywhere else. Use instead of useWindowDimensions for
 *  layout. */
export function useScreenSize(): Size {
  const win = useWindowDimensions();
  const framed = useContext(ScreenSize);
  return framed ?? { width: win.width, height: win.height };
}

function fullscreenRequested(): boolean {
  if (Platform.OS !== "web" || typeof window === "undefined") return false;
  try {
    return new URLSearchParams(window.location.search).get("fullscreen") === "1";
  } catch {
    return false;
  }
}

function useClock(): string {
  const fmt = () => new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }).replace(/\s?[AP]M$/i, "");
  const [now, setNow] = useState(fmt);
  useEffect(() => {
    const id = setInterval(() => setNow(fmt()), 30_000);
    return () => clearInterval(id);
  }, []);
  return now;
}

export function PhoneFrame({ children }: PropsWithChildren) {
  const win = useWindowDimensions();
  const [fullscreen] = useState(fullscreenRequested);
  const clock = useClock();
  const framed = Platform.OS === "web" && !fullscreen && win.width >= FRAME_BREAKPOINT;
  if (!framed) return <>{children}</>;

  // Shrink the phone to fit short windows, never above its real size.
  const outerH = Math.min(PHONE_H + BEZEL * 2, win.height - MARGIN * 2);
  const screenH = outerH - BEZEL * 2;
  const screenW = PHONE_W;
  const appH = screenH - STATUS_H - HOME_H;

  return (
    <View style={styles.backdrop} testID="phone-frame">
      <View style={[styles.device, { height: outerH, width: screenW + BEZEL * 2 }]}>
        <View style={[styles.screen, { width: screenW, height: screenH }]}>
          <View style={styles.statusBar} accessibilityElementsHidden importantForAccessibility="no-hide-descendants">
            <Text style={styles.clock}>{clock}</Text>
            <View style={styles.island} />
            <View style={styles.statusIcons}>
              <View style={[styles.bar, { height: 5 }]} />
              <View style={[styles.bar, { height: 7 }]} />
              <View style={[styles.bar, { height: 9 }]} />
              <View style={styles.battery}><View style={styles.batteryFill} /></View>
            </View>
          </View>
          <ScreenSize.Provider value={{ width: screenW, height: appH }}>
            <View style={{ width: screenW, height: appH, overflow: "hidden" }}>{children}</View>
          </ScreenSize.Provider>
          <View style={styles.homeArea}>
            <View style={styles.homeIndicator} />
          </View>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#DDE3DF",
  },
  device: {
    padding: BEZEL,
    borderRadius: 56,
    backgroundColor: "#101A16",
    boxShadow: "0 24px 60px rgba(16, 26, 22, 0.28), 0 4px 14px rgba(16, 26, 22, 0.18)",
  },
  screen: {
    borderRadius: 44,
    overflow: "hidden",
    backgroundColor: colors.surface,
  },
  statusBar: {
    height: STATUS_H,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 28,
    backgroundColor: colors.surface,
  },
  clock: { fontFamily: fonts.semibold, fontSize: 14, color: colors.onSurface, width: 56 },
  island: { width: 96, height: 24, borderRadius: 12, backgroundColor: "#101A16", marginTop: 6 },
  statusIcons: { flexDirection: "row", alignItems: "flex-end", gap: 2, width: 56, justifyContent: "flex-end" },
  bar: { width: 3, borderRadius: 1, backgroundColor: colors.onSurface },
  battery: {
    marginLeft: 5, width: 22, height: 11, borderRadius: 3, borderWidth: 1, borderColor: colors.onSurface, padding: 1,
  },
  batteryFill: { flex: 1, borderRadius: 1, backgroundColor: colors.onSurface },
  homeArea: { height: HOME_H, alignItems: "center", justifyContent: "center", backgroundColor: colors.surface },
  homeIndicator: { width: 120, height: 5, borderRadius: 3, backgroundColor: colors.onSurface, opacity: 0.85 },
});
