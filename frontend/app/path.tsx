
import { Redirect } from "expo-router";

// My Path is now its own tab (app/(tabs)/my-path.tsx). This route stays so
// older links to "/path" keep working.
export default function PathRedirect() {
  return <Redirect href="/(tabs)/my-path" />;
}
