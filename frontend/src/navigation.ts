import type { Href, useRouter } from "expo-router";

type Router = ReturnType<typeof useRouter>;

// router.back() is a silent no-op when there's no history to pop — e.g. on
// web after a refresh or when a screen was opened from a deep link — which
// leaves the participant stranded (or staring at a stuck spinner after a
// save). Every "close"/"done" in the app goes through this instead, falling
// back to a sensible screen when there's nothing to go back to.
export function goBack(router: Router, fallback: Href = "/") {
  if (router.canGoBack()) router.back();
  else router.replace(fallback);
}
