// =============================================================================
// people.ts  —  LANGUAGE: TypeScript
// -----------------------------------------------------------------------------
// Each phone belongs to ONE person. The first time a phone opens its owner's link
// (/m?user=tasnim), the phone remembers "this is Tasnim's phone". After that, opening
// the app's start address (/) on that phone goes straight to Tasnim's page.
// Nobody picks a person from a list: Tasnim's phone shows Tasnim, Matheus's shows Matheus.
// =============================================================================

const KEY = "mochi.user";

/** Minimal storage shape, so tests can pass a fake one (browsers pass window.localStorage). */
export interface SimpleStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

/** The browser's storage, or null where it is not available (private mode, some embedded views). */
export function browserStorage(): SimpleStorage | null {
  try {
    return typeof window !== "undefined" ? window.localStorage : null;
  } catch {
    return null;
  }
}

/** Remember whose phone this is. Never throws: if storage is blocked, the phone just doesn't remember. */
export function rememberUser(user: string, storage: SimpleStorage | null = browserStorage()): void {
  try {
    storage?.setItem(KEY, user.toLowerCase());
  } catch {
    /* storage full or blocked: nothing to do */
  }
}

/** Whose phone this is, if it was remembered; otherwise null. */
export function rememberedUser(storage: SimpleStorage | null = browserStorage()): string | null {
  try {
    const v = storage?.getItem(KEY);
    return v && /^[a-z0-9_-]{1,40}$/.test(v) ? v : null;
  } catch {
    return null;
  }
}

/** Read ?people=a,b from the URL (for the mock demo). Returns null when absent or not exactly two names. */
export function peopleFromUrl(search: string): [string, string] | null {
  const raw = new URLSearchParams(search).get("people");
  const names = (raw ?? "").split(",").map((x) => x.trim().toLowerCase()).filter(Boolean);
  return names.length === 2 ? [names[0], names[1]] : null;
}
