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
import type { AgoraJoin } from "./phoneMic.ts";
import { parseEvent } from "./store.ts";
import { PI_SESSION, sessionFor } from "./phoneSession.ts";
import { type Who, wsQuery } from "./who.ts";

/** The commands a page can send. Same shape for the real backend and the mock. */
export interface Backend {
  start(): Promise<void>;                              // POST /api/sessions/<this phone's session>/start
  phoneAudio(): Promise<AgoraJoin | null>;             // GET /api/sessions/<session>/agora (null in the mock, and for the Pi's session: no mic)
  stop(): Promise<void>;                               // POST /api/sessions/<session>/stop
  activityStart(): Promise<void>;                      // POST /api/sessions/<session>/activity/start
  activityResult(result: RoundResult): Promise<void>;  // POST /api/sessions/<session>/activity/result
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

/** The session a page follows (D-37): a phone has its own; Mochi's screen and the projector the Pi's. */
export function sessionOf(who: Who): string {
  return who.kind === "user" ? sessionFor(who.session) : PI_SESSION;
}

/** Build the WebSocket address, e.g. ws://localhost:5173/ws?user=ana&session=p-3f9c1a2b */
function wsUrl(who: Who, session: string): string {
  const base = baseUrl() || window.location.origin;
  const follow = who.kind === "device" || session === PI_SESSION ? "" : `&session=${session}`;
  return `${base.replace(/^http/, "ws")}/ws?${wsQuery(who)}${follow}`; // http → ws, https → wss
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

/** Send one GET request and read the JSON answer. */
async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${baseUrl()}${path}`);
  if (!res.ok) throw new HttpError(path, res.status);
  return (await res.json()) as T;
}

/** The device state's join block, or null when no session runs (the same answer the Pi bridge polls). */
export function joinFrom(state: { agora?: AgoraJoin | null }): AgoraJoin | null {
  return state.agora ?? null;
}

/** Connect to the REAL backend. */
export function connectReal(who: Who, h: BackendHandlers): Backend {
  const session = sessionOf(who);
  let ws: WebSocket | null = null;
  let closed = false;                                  // true once the page closed it on purpose
  let retry: ReturnType<typeof setTimeout> | undefined;

  // Open the WebSocket. If it drops (e.g. Luís restarts the backend), try again after 2 seconds.
  // On every new connection the server re-sends the current state.
  const open = () => {
    ws = new WebSocket(wsUrl(who, session));
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
  const s = `/api/sessions/${session}`;
  return {
    start: () => post(`${s}/start`),
    // The phone's own channel (never the Pi's). In the Pi's session the Pi listens: no phone mic.
    phoneAudio: async () => (session === PI_SESSION ? null : await getJson<AgoraJoin>(`${s}/agora`)),
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
/** scenario "recording" (the /me page): nothing plays by itself; Record and Stop make a new conversation. */
export function connectMock(who: Who, h: BackendHandlers, speed: number, people?: [string, string],
  scenario: "demo" | "recording" = "demo"): Backend {
  const gw = new MockGateway(who, h.onEvent, speed, () => Date.now(), people, scenario);
  h.onConnected(true);
  gw.connect(scenario === "demo"); // the demo plays by itself; the /me page waits for "Record"
  return {
    start: async () => gw.start(),
    phoneAudio: async () => null, // the mock has no Agora: the phone just plays the fake demo
    stop: async () => gw.stop(),
    activityStart: async () => gw.activityStart(),
    activityResult: async (r) => gw.activityResult(r),
    close: () => gw.clear(),
  };
}
