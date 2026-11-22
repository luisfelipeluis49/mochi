// Who uses this device: the User returned by POST /api/users, kept in localStorage "mochi.user.v1".
// Forgetting it deletes nothing on the server (THE SHARED CONTRACT, C6).

import { isUser, type User } from "../contracts.ts";
import { type KV, localStore, safeGet, safeRemove, safeSet } from "./storage.ts";

export const IDENTITY_KEY = "mochi.user.v1";

export function readUser(s: KV | null = localStore()): User | null {
  const raw = safeGet(s, IDENTITY_KEY);
  if (!raw) return null;
  try {
    const v: unknown = JSON.parse(raw);
    return isUser(v) ? v : null;
  } catch {
    return null;
  }
}

/** Store the user. Returns false when storage is unavailable (the app then keeps it in memory only). */
export function writeUser(user: User, s: KV | null = localStore()): boolean {
  return safeSet(s, IDENTITY_KEY, JSON.stringify(user));
}

export function forgetUser(s: KV | null = localStore()): void {
  safeRemove(s, IDENTITY_KEY);
}

/** Up to two initials for the avatar: "Luís Felipe" -> "LF", "ana" -> "A". */
export function initialsOf(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  const letters = parts.length > 1 ? [parts[0], parts[parts.length - 1]] : parts;
  return letters.map((p) => Array.from(p)[0] ?? "").join("").toLocaleUpperCase() || "?";
}
