// =============================================================================
// tabs.ts  —  LANGUAGE: TypeScript
// -----------------------------------------------------------------------------
// The two tabs at the bottom of a person's phone pages: Analytics (/m) and Conversations (/me).
// Switching tabs keeps the rest of the address (?user=ana&mock=1&lang=pt-BR ...).
// =============================================================================

export type Tab = "analytics" | "conversations";

/** The page of each tab. */
export const TAB_PATH: Record<Tab, string> = { analytics: "/m", conversations: "/me" };

/** Which tab a path belongs to: "/me..." is Conversations, anything else is Analytics. */
export function tabFromPath(pathname: string): Tab {
  return pathname.startsWith("/me") ? "conversations" : "analytics";
}

/** The link of a tab, keeping the options. Example: tabHref("conversations", "?user=ana&mock=1") → "/me?user=ana&mock=1" */
export function tabHref(tab: Tab, search: string): string {
  return `${TAB_PATH[tab]}${search}`;
}
