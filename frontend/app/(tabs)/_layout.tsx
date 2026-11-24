import React from "react";
import { Tabs, useRouter } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { Platform, Pressable, View } from "react-native";
import { colors, fonts, shadow } from "@/src/theme";

// Bottom bar: Today · Path · (+ log) · Learn · Future Me (the digital twin
// and the app's one conversational guide; the old Coach route redirects
// there). "Ask Future Me" buttons open it with a question filled in.
// Progress (the old "Me" tab) opens from the points chip / avatar on Today,
// and Wings (Social) opens from Progress → Challenges. Both keep their
// routes; they are just not in the bar.
function LogButton() {
  const router = useRouter();
  return (
    <View style={{ flex: 1, alignItems: "center" }}>
      <Pressable
        onPress={() => router.push("/log-meal")}
        accessibilityRole="button"
        accessibilityLabel="Log a meal, movement or sleep"
        testID="tab-log"
        style={{
          width: 58,
          height: 58,
          borderRadius: 29,
          marginTop: -22,
          backgroundColor: colors.brandPrimary,
          alignItems: "center",
          justifyContent: "center",
          ...shadow.lifted,
        }}
      >
        <Feather name="plus" size={28} color={colors.onBrandPrimary} />
      </Pressable>
    </View>
  );
}

export default function TabsLayout() {
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.brandPrimary,
        tabBarInactiveTintColor: "#6B7A75",
        tabBarStyle: {
          backgroundColor: colors.surfaceSecondary,
          borderTopColor: colors.border,
          borderTopWidth: 1,
          height: Platform.OS === "ios" ? 90 : 76,
          paddingTop: 8,
          paddingBottom: Platform.OS === "ios" ? 30 : 16,
        },
        tabBarLabelStyle: { fontFamily: fonts.bold, fontSize: 11, lineHeight: 15 },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: "Today",
          tabBarIcon: ({ color, size }) => <Feather name="home" size={size - 2} color={color} />,
        }}
      />
      <Tabs.Screen
        name="my-path"
        options={{
          title: "Path",
          tabBarIcon: ({ color, size }) => <Feather name="map" size={size - 2} color={color} />,
        }}
      />
      <Tabs.Screen
        name="log"
        options={{
          title: "Log",
          tabBarButton: () => <LogButton />,
        }}
      />
      <Tabs.Screen
        name="learn"
        options={{
          title: "Learn",
          tabBarIcon: ({ color, size }) => <Feather name="book-open" size={size - 2} color={color} />,
        }}
      />
      <Tabs.Screen
        name="future-me"
        options={{
          title: "Future Me",
          tabBarIcon: ({ color, size }) => <Feather name="user" size={size - 2} color={color} />,
        }}
      />
      <Tabs.Screen name="profile" options={{ href: null, title: "Progress" }} />
      <Tabs.Screen name="eat" options={{ href: null, title: "Eat" }} />
      <Tabs.Screen name="social" options={{ href: null, title: "Wings" }} />
    </Tabs>
  );
}
