// =============================================================================
// who.ts  —  LANGUAGE: TypeScript
// -----------------------------------------------------------------------------
// Reads the page address (URL) and answers: "which of the 3 screens am I?"
// The answer is also used to build the WebSocket address (AGENTS.md §6.4),
// so the backend knows what to send to this page.
// =============================================================================

/** The three kinds of connection. */
export type Who =
  | { kind: "user"; user: string }        // a phone:         /m?user=ana
  | { kind: "device"; device: string }    // Mochi's screen:  /home?device=home_pi_01
  | { kind: "audience" };                 // the projector:   /audience

/** URL → Who. Returns null for any other address (then main.tsx shows the link list). */
export function whoFromUrl(pathname: string, search: string): Who | null {
  const q = new URLSearchParams(search);
  if (pathname.startsWith("/home")) return { kind: "device", device: q.get("device") ?? "home_pi_01" };
  if (pathname.startsWith("/audience")) return { kind: "audience" };
  if (pathname.startsWith("/m")) {
    const user = q.get("user");
    return user ? { kind: "user", user } : null; // a phone page needs ?user=
  }
  return null;
}

/** Who → the part after "?" in the WebSocket address, e.g. "user=ana". */
export function wsQuery(who: Who): string {
  if (who.kind === "user") return `user=${encodeURIComponent(who.user)}`;
  if (who.kind === "device") return `device=${encodeURIComponent(who.device)}`;
  return "view=audience";
}
