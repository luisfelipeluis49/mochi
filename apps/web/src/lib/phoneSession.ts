// =============================================================================
// phoneSession.ts  —  LANGUAGE: TypeScript
// -----------------------------------------------------------------------------
// Each phone has its OWN session on the backend (DECISIONS D-37): its own Agora channel, its own
// hints and cooldown. Starting or stopping it never touches the Pi's session ("demo") or another
// phone's. The id is random, kept in sessionStorage so a reload of this tab finds the same session.
// `?session=demo` on /m makes the phone follow and control the Pi's session instead (the Operator's
// remote Start/Stop; no microphone then, the Pi listens).
// =============================================================================

export const PI_SESSION = "demo";
const KEY = "mochi.sessionId";
const ID_PATTERN = /^[A-Za-z0-9_-]{1,40}$/;

type Store = Pick<Storage, "getItem" | "setItem">;

function storage(): Store | null {
  try {
    return globalThis.sessionStorage ?? null;
  } catch {
    return null; // some private modes throw on access
  }
}

/** A new session id, e.g. "p-3f9c1a2b". */
export function newSessionId(random: () => number = Math.random): string {
  return `p-${Math.floor(random() * 0xffffffff).toString(16).padStart(8, "0")}`;
}

/** Is this a session id the backend accepts? */
export function isSessionId(id: string): boolean {
  return ID_PATTERN.test(id);
}

/** This tab's own session id: the stored one, else a new one (stored when storage works). */
export function ownSessionId(s: Store | null = storage(), random: () => number = Math.random): string {
  try {
    const kept = s?.getItem(KEY);
    if (kept && isSessionId(kept)) return kept;
    const id = newSessionId(random);
    s?.setItem(KEY, id);
    return id;
  } catch {
    return newSessionId(random);
  }
}

/** The session a page follows: the one named in the address (valid ids only), else its own. */
export function sessionFor(named: string | null | undefined, own: () => string = ownSessionId): string {
  return named && isSessionId(named) ? named : own();
}
