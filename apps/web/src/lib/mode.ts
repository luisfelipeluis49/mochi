// How a session listens (D-46), the same two ways the Pi works:
//   listen: a quiet listener. Mochi shows hints, speaks only when asked, or to explain an idiom
//           or a wrong expression. Start sends no wake phrase.
//   talk:   a conversation. Mochi talks with you (Praticar). Start sends the wake phrase.
// The choice is remembered on this device.

import { type KV, localStore, safeGet, safeSet } from "./storage.ts";

export type SessionMode = "listen" | "talk";
export const SESSION_MODES: readonly SessionMode[] = ["listen", "talk"];
export const MODE_KEY = "mochi.mode.v1";
export const DEFAULT_MODE: SessionMode = "listen";

export function readMode(s: KV | null = localStore()): SessionMode {
  const v = safeGet(s, MODE_KEY);
  return v === "talk" || v === "listen" ? v : DEFAULT_MODE;
}

export function writeMode(mode: SessionMode, s: KV | null = localStore()): boolean {
  return safeSet(s, MODE_KEY, mode);
}
