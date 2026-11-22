// =============================================================================
// tabs.ts  —  LANGUAGE: TypeScript
// -----------------------------------------------------------------------------
// The two tabs at the bottom of a person's phone: Session (/m) and Analytics (/m/analytics).
// Switching tabs keeps the rest of the address (?user=ana&mock=1&lang=pt-BR ...).
// The old "/me" address opens Analytics, so old links still work.
// =============================================================================

export type Tab = "session" | "analytics";

/** The address of each tab. */
export const TAB_PATH: Record<Tab, string> = { session: "/m", analytics: "/m/analytics" };

/** Which tab an address belongs to: "/m/analytics" (or the old "/me") is Analytics, anything else is Session. */
export function tabFromPath(pathname: string): Tab {
  return pathname.startsWith("/m/analytics") || pathname.startsWith("/me") ? "analytics" : "session";
}

/** The address of a tab, keeping the options. Example: tabHref("analytics", "?user=ana&mock=1") → "/m/analytics?user=ana&mock=1" */
export function tabHref(tab: Tab, search: string): string {
  return `${TAB_PATH[tab]}${search}`;
}
