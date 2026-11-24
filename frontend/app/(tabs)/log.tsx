import { Redirect } from "expo-router";

// The centre "+" in the tab bar opens the Log modal directly; this route only
// exists so the tab has a screen. A deep link here goes to the same place.
export default function LogTab() {
  return <Redirect href="/log-meal" />;
}
