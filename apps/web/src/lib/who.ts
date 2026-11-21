// =============================================================================
// who.ts  —  LANGUAGE: TypeScript
// -----------------------------------------------------------------------------
// Reads the page address (URL) and answers: "which of the 3 screens am I?"
// The answer is also used to build the WebSocket address (AGENTS.md §6.4),
// so the backend knows what to send to this page.
// =============================================================================

/** The three kinds of connection. */
export type Who =
  | { kind: "user"; user: string; session?: string } // a phone: /m?user=ana  (also /me?user=ana, "My conversations");
                                                     // session: ?session=demo follows the Pi's session
  | { kind: "device"; device: string }    // Mochi's screen:  /home?device=home_pi_01
  | { kind: "audience" };                 // the projector:   /audience

/** URL → Who. Returns null for any other address (then main.tsx shows the link list). */
export function whoFromUrl(pathname: string, search: string): Who | null {
  const q = new URLSearchParams(search);
  if (pathname.startsWith("/home")) return { kind: "device", device: q.get("device") ?? "home_pi_01" };
  if (pathname.startsWith("/audience")) return { kind: "audience" };
  if (pathname.startsWith("/m")) {
    const user = q.get("user");
    const session = q.get("session") ?? undefined;
    return user ? { kind: "user", user, ...(session ? { session } : {}) } : null; // a phone page needs ?user=
  }
  return null;
}

/** Who → the part after "?" in the WebSocket address, e.g. "user=ana". */
export function wsQuery(who: Who): string {
  if (who.kind === "user") return `user=${encodeURIComponent(who.user)}`;
  if (who.kind === "device") return `device=${encodeURIComponent(who.device)}`;
  return "view=audience";
}

/** The second demo person. It must be in the backend roster (services/backend/.../gateway/roster.py),
 *  which today is ana + ben; any other name is refused with close code 4400. The product deck calls
 *  her Sophie: if the team renames ben → sophie in the backend, change this ONE line too.
 *  The mock demo, the start-page links and the tests all follow this constant. */
export const SECOND_USER = "ben";

/** The links shown on the Index page. */
export function indexLinks(): { href: string; label: string }[] {
  return [
    { href: "/home?device=home_pi_01", label: "Home view (Mochi's screen)" },
    { href: "/m?user=ana", label: "Mobile view: Ana" },
    { href: `/m?user=${SECOND_USER}`, label: `Mobile view: ${SECOND_USER[0].toUpperCase()}${SECOND_USER.slice(1)}` },
    { href: "/m?user=ben", label: "Mobile view: Ben (backend roster)" },
    { href: "/me?user=tasnim&mock=1", label: "My conversations (analytics of real conversations)" },
    { href: "/audience", label: "Audience view (projector)" },
  ];
}
