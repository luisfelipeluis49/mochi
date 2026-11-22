// Path <-> screen. A tiny router on the History API (no router dependency).

export type Screen = "welcome" | "session" | "training" | "digest" | "analytics" | "profile";

export const SCREENS: readonly Screen[] = ["welcome", "session", "training", "digest", "analytics", "profile"];

/** The four items of the navigation, in order (the profile is reached from the header avatar). */
export const NAV_SCREENS: readonly Screen[] = ["session", "training", "digest", "analytics"];

export const DEFAULT_SCREEN: Screen = "session";

export function pathOf(screen: Screen): string {
  return `/${screen}`;
}

export interface Route {
  screen: Screen;
  /** true when the path was not the screen's own path ("/" or unknown): the app replaces the URL. */
  redirected: boolean;
}

/** "/digest" -> digest. "/" and any unknown path go to the session screen. A trailing slash is fine. */
export function routeOf(pathname: string): Route {
  const clean = pathname.replace(/\/+$/, "") || "/";
  const name = clean.slice(1).toLowerCase();
  const hit = SCREENS.find((s) => s === name);
  if (hit && clean === pathOf(hit)) return { screen: hit, redirected: false };
  if (hit) return { screen: hit, redirected: true };
  return { screen: DEFAULT_SCREEN, redirected: true };
}
