// =============================================================================
// backend.ts  —  LANGUAGE: TypeScript
// -----------------------------------------------------------------------------
// The ONLY file that talks to Luís's backend. Two directions:
//   RECEIVE: a WebSocket (/ws?...) that stays open; the backend pushes events through it.
//   SEND:    HTTP POST requests for commands (Start, Stop, start game, game result).
// It also has a MOCK version (?mock=1) that fakes the backend so you can work without it.
// When we connect to the real backend, this is the file to check first.
// =============================================================================

import type { MochiEvent, RoundResult } from "../contracts.ts";
import { MockGateway } from "../mock/demoScript.ts";
import { parseEvent } from "./store.ts";
import { type Who, wsQuery } from "./who.ts";

/** The commands a page can send. Same shape for the real backend and the mock. */
export interface Backend {
  start(): Promise<void>;                              // POST /api/sessions/demo/start
  stop(): Promise<void>;                               // POST /api/sessions/demo/stop
  activityStart(): Promise<void>;                      // POST /api/sessions/demo/activity/start
  activityResult(result: RoundResult): Promise<void>;  // POST /api/sessions/demo/activity/result
  close(): void;                                       // close the connection (when the page goes away)
}

/** What to do when something arrives. Given by useMochi.ts. */
export interface BackendHandlers {
  onEvent(e: MochiEvent): void;          // an event arrived
  onConnected(connected: boolean): void; // the connection opened (true) or closed (false)
  onRejected?(reason: string): void;     // the backend closed it with 4400: we stop retrying; this says why
}

/** The backend address. Empty = same address as the page (Vite forwards /api and /ws in development).
 *  To use a backend elsewhere, start with VITE_BACKEND_URL=https://... */
function baseUrl(): string {
  const env = (import.meta as unknown as { env?: Record<string, string | undefined> }).env ?? {};
  return (env.VITE_BACKEND_URL ?? "").replace(/\/$/, "");
}

/** Build the WebSocket address, e.g. ws://localhost:5173/ws?user=ana */
function wsUrl(who: Who): string {
  const base = baseUrl() || window.location.origin;
  return `${base.replace(/^http/, "ws")}/ws?${wsQuery(who)}`; // http → ws, https → wss
}

/** A failed POST, with the HTTP status (HomeView needs to tell 409 from the rest). */
export class HttpError extends Error {
  status: number;
  constructor(path: string, status: number) {
    super(`${path} → ${status}`);
    this.status = status;
  }
}

/** Should the page reconnect after the socket closed with this code? 4400 = the backend rejected
 *  this connection (bad ?user= ...): retrying can never work. */
export function shouldRetry(code: number): boolean {
  return code !== 4400;
}

/** Send one POST request. Throws an error if the backend answers with a failure. */
async function post(path: string, body?: unknown): Promise<void> {
  const res = await fetch(`${baseUrl()}${path}`, {
    method: "POST",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new HttpError(path, res.status);
}

/** Connect to the REAL backend. */
export function connectReal(who: Who, h: BackendHandlers): Backend {
  let ws: WebSocket | null = null;
  let closed = false;                                  // true once the page closed it on purpose
  let retry: ReturnType<typeof setTimeout> | undefined;

  // Open the WebSocket. If it drops (e.g. Luís restarts the backend), try again after 2 seconds.
  // On every new connection the server re-sends the current state.
  const open = () => {
    ws = new WebSocket(wsUrl(who));
    ws.onopen = () => h.onConnected(true);
    ws.onmessage = (m) => {                            // a message arrived
      const e = parseEvent(String(m.data));            // text → event (or null if broken)
      if (e) h.onEvent(e);
    };
    ws.onclose = (ev) => {
      h.onConnected(false);
      if (!shouldRetry(ev.code)) {
        closed = true; // no retry loop
        h.onRejected?.(ev.reason || `closed (${ev.code})`);
        return;
      }
      if (!closed) retry = setTimeout(open, 2000);
    };
  };
  open();

  // The commands: each one is a POST to the address from AGENTS.md §6.4.
  const s = "/api/sessions/demo";
  return {
    start: () => post(`${s}/start`),
    stop: () => post(`${s}/stop`),
    activityStart: () => post(`${s}/activity/start`),
    activityResult: (result) => post(`${s}/activity/result`, { result }), // body: { "result": "guessed" }
    close() {
      closed = true;
      clearTimeout(retry);
      ws?.close();
    },
  };
}

/** Connect to the FAKE backend (?mock=1). It replays the demo by itself. */
export function connectMock(who: Who, h: BackendHandlers, speed: number): Backend {
  const gw = new MockGateway(who, h.onEvent, speed);
  h.onConnected(true);
  gw.connect(true); // true = play the demo automatically
  return {
    start: async () => gw.start(),
    stop: async () => gw.stop(),
    activityStart: async () => gw.activityStart(),
    activityResult: async (r) => gw.activityResult(r),
    close: () => gw.clear(),
  };
}
