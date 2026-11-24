import React from "react";
import { Redirect, useLocalSearchParams } from "expo-router";

// The Coach is now Future Me (study team feedback 5.2: one name for the
// conversational guide). Old links to /coach, including ?q=…, land there.
export default function Coach() {
  const { q } = useLocalSearchParams<{ q?: string }>();
  return <Redirect href={{ pathname: "/(tabs)/future-me", params: typeof q === "string" && q ? { q } : {} }} />;
}
