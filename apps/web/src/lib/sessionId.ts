// A new session id for every Start: "w-" + 8 random lowercase hex characters (THE SHARED CONTRACT, C6).
// The id of the running session is kept in sessionStorage "mochi.session.v1" so a reload can find it.

import { type KV, safeGet, safeRemove, safeSet, sessionStore } from "./storage.ts";

export const SESSION_KEY = "mochi.session.v1";
export const SESSION_ID_RE = /^w-[0-9a-f]{8}$/;

/** random() returns a number in [0, 1), like Math.random. */
export function newSessionId(random: () => number = defaultRandom): string {
  let hex = "";
  for (let i = 0; i < 8; i++) hex += Math.floor(random() * 16).toString(16);
  return `w-${hex}`;
}

function defaultRandom(): number {
  const c = globalThis.crypto;
  if (c?.getRandomValues) return c.getRandomValues(new Uint32Array(1))[0] / 2 ** 32;
  return Math.random();
}

export function rememberSession(id: string, s: KV | null = sessionStore()): void {
  safeSet(s, SESSION_KEY, id);
}

export function rememberedSession(s: KV | null = sessionStore()): string | null {
  const id = safeGet(s, SESSION_KEY);
  return id && SESSION_ID_RE.test(id) ? id : null;
}

export function forgetSession(s: KV | null = sessionStore()): void {
  safeRemove(s, SESSION_KEY);
}
