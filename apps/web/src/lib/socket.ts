// The WebSocket to the backend (THE SHARED CONTRACT, C5): /ws?user=<id>&session=<id>, same origin.
// The server never pings; the client reconnects after 1, 2, 4 and 8 s, then every 15 s, and never
// after close code 4400 (an unknown user: the "lost user" rule, C6).

import { isMochiEvent, type MochiEvent } from "../contracts.ts";
import type { Timers } from "./api.ts";

export const LOST_USER_CODE = 4400;
export const BACKOFF_MS = [1000, 2000, 4000, 8000] as const;
export const BACKOFF_MAX_MS = 15_000;

/** Delay before reconnect attempt number `attempt` (0-based): 1, 2, 4, 8, 15, 15, ... seconds. */
export function backoffMs(attempt: number): number {
  return BACKOFF_MS[attempt] ?? BACKOFF_MAX_MS;
}

/** ws: or wss: to match the page, on the page's own host. */
export function socketUrl(loc: { protocol: string; host: string }, userId: string, sessionId: string): string {
  const proto = loc.protocol === "https:" ? "wss:" : "ws:";
  const q = new URLSearchParams({ user: userId, session: sessionId });
  return `${proto}//${loc.host}/ws?${q.toString()}`;
}

/** Text from the socket -> a known, well-formed event, or null (ignored). */
export function parseEvent(raw: unknown): MochiEvent | null {
  if (typeof raw !== "string") return null;
  try {
    const v: unknown = JSON.parse(raw);
    return isMochiEvent(v) ? v : null;
  } catch {
    return null;
  }
}

/** The part of the browser WebSocket we use. */
export interface SocketLike {
  onopen: ((ev: unknown) => void) | null;
  onmessage: ((ev: { data: unknown }) => void) | null;
  onclose: ((ev: { code: number; reason: string }) => void) | null;
  onerror: ((ev: unknown) => void) | null;
  close(code?: number, reason?: string): void;
}
export type SocketCtor = new (url: string) => SocketLike;

export interface SocketHandlers {
  onOpen(): void;
  onEvent(e: MochiEvent): void;
  /** The socket closed; `retryInMs` is null when it will not reconnect. */
  onClose(info: { code: number; retryInMs: number | null }): void;
  /** Close code 4400: the backend does not know this user. */
  onLostUser(): void;
}

export interface Connection {
  close(): void;
  readonly url: string;
}

export function connectSocket(url: string, h: SocketHandlers, deps: { WebSocket: SocketCtor; timers: Timers }): Connection {
  let ws: SocketLike | null = null;
  let attempt = 0;
  let closedByUs = false;
  let retry: unknown = null;

  const open = () => {
    retry = null;
    const sock = new deps.WebSocket(url);
    ws = sock;
    sock.onopen = () => {
      if (ws !== sock) return;
      attempt = 0; // a good connection resets the backoff
      h.onOpen();
    };
    sock.onmessage = (m) => {
      if (ws !== sock) return;
      const e = parseEvent(m.data);
      if (e) h.onEvent(e);
    };
    sock.onerror = () => { /* a close always follows */ };
    sock.onclose = (ev) => {
      if (ws !== sock) return;
      ws = null;
      if (closedByUs) return;
      if (ev.code === LOST_USER_CODE) {
        h.onClose({ code: ev.code, retryInMs: null });
        h.onLostUser();
        return;
      }
      const wait = backoffMs(attempt++);
      h.onClose({ code: ev.code, retryInMs: wait });
      retry = deps.timers.setTimeout(open, wait);
    };
  };
  open();

  return {
    url,
    close() {
      closedByUs = true;
      if (retry !== null) deps.timers.clearTimeout(retry);
      const s = ws;
      ws = null;
      try {
        s?.close(1000, "bye");
      } catch {
        /* already closed */
      }
    },
  };
}
