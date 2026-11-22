// Typed client for every endpoint of THE SHARED CONTRACT the web uses. Same origin only (C0).
// fetch is injectable for tests. Every failure is an ApiError {status, kind}; the web never shows
// the backend's "detail".

import {
  type AgoraJoin, type LearningEvent, type NewUser, type SessionRecord, type SessionState, type User,
  isAgoraJoin, isLearningEvent, isSessionRecord, isSessionState, isUser,
} from "../contracts.ts";
import { type Failure, type Op, type ProblemKind, problemOfHttp } from "./httpProblem.ts";
import { type UiLang, wokenBy } from "./i18n.ts";

export type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

export class ApiError extends Error {
  readonly status: Failure;
  readonly kind: ProblemKind;
  constructor(status: Failure, kind: ProblemKind, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.kind = kind;
  }
}

export interface Timers {
  setTimeout: (fn: () => void, ms: number) => unknown;
  clearTimeout: (id: unknown) => void;
}

export const realTimers: Timers = {
  setTimeout: (fn, ms) => globalThis.setTimeout(fn, ms),
  clearTimeout: (id) => globalThis.clearTimeout(id as ReturnType<typeof setTimeout>),
};

export const PROBE_TIMEOUT_MS = 10_000;

export interface ApiOptions {
  fetch?: FetchLike;
  timers?: Timers;
  online?: () => boolean;
}

/** The API surface the app uses. The mock (?mock=1) implements the same interface. */
export interface Api {
  health(): Promise<{ status: string; version?: string }>;
  createUser(body: NewUser): Promise<User>;
  getUser(userId: string): Promise<User>;
  words(userId: string): Promise<LearningEvent[]>;
  sessions(userId: string): Promise<SessionRecord[]>;
  start(sessionId: string, userId: string, lang: UiLang): Promise<SessionState>;
  stop(sessionId: string): Promise<SessionState | null>;
  agora(sessionId: string): Promise<AgoraJoin>;
}

const enc = encodeURIComponent;

export function createApi(opts: ApiOptions = {}): Api {
  const doFetch: FetchLike = opts.fetch ?? ((i, init) => globalThis.fetch(i, init));
  const timers = opts.timers ?? realTimers;
  const online = opts.online ?? (() => globalThis.navigator?.onLine !== false);

  async function call<T>(op: Op, method: "GET" | "POST", path: string, body: unknown, check: (v: unknown) => v is T, timeoutMs?: number): Promise<T> {
    const ctrl = timeoutMs ? new AbortController() : null;
    let timedOut = false;
    const timer = ctrl ? timers.setTimeout(() => { timedOut = true; ctrl.abort(); }, timeoutMs!) : null;
    let res: Response;
    try {
      res = await doFetch(path, {
        method,
        headers: body === undefined ? { Accept: "application/json" } : { Accept: "application/json", "Content-Type": "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: ctrl?.signal,
      });
    } catch {
      const f: Failure = timedOut ? "timeout" : "network";
      throw new ApiError(f, problemOfHttp(f, { op, online: online() }), `${method} ${path}: ${f}`);
    } finally {
      if (timer !== null) timers.clearTimeout(timer);
    }
    if (!res.ok) {
      throw new ApiError(res.status, problemOfHttp(res.status, { op, online: online() }), `${method} ${path}: ${res.status}`);
    }
    let data: unknown;
    try {
      data = await res.json();
    } catch {
      throw new ApiError(res.status, "server", `${method} ${path}: not JSON`);
    }
    if (!check(data)) throw new ApiError(res.status, "server", `${method} ${path}: unexpected shape`);
    return data;
  }

  const anyObj = (v: unknown): v is { status: string; version?: string } => typeof v === "object" && v !== null;
  const arrayOf = <T>(g: (v: unknown) => v is T) => (v: unknown): v is T[] => Array.isArray(v) && v.every(g);

  return {
    health: () => call("probe", "GET", "/healthz", undefined, anyObj, PROBE_TIMEOUT_MS),
    createUser: (body) => call("other", "POST", "/api/users", body, isUser),
    getUser: (id) => call("user", "GET", `/api/users/${enc(id)}`, undefined, isUser),
    words: (id) => call("user", "GET", `/api/users/${enc(id)}/words`, undefined, arrayOf(isLearningEvent)),
    sessions: (id) => call("user", "GET", `/api/users/${enc(id)}/sessions`, undefined, arrayOf(isSessionRecord)),
    start: (sid, userId, lang) =>
      call("start", "POST", `/api/sessions/${enc(sid)}/start`, { user_id: userId, woken_by: wokenBy(lang) }, isSessionState),
    stop: async (sid) => {
      const v = await call("other", "POST", `/api/sessions/${enc(sid)}/stop`, undefined, (x: unknown): x is unknown => true);
      return isSessionState(v) ? v : null;
    },
    agora: (sid) => call("agora", "GET", `/api/sessions/${enc(sid)}/agora`, undefined, isAgoraJoin),
  };
}

/** The stop the browser sends while the tab closes (C6): a POST with an empty body. */
export function beaconStop(sessionId: string, nav: { sendBeacon?: (url: string, data?: BodyInit | null) => boolean } | undefined = globalThis.navigator): boolean {
  try {
    return nav?.sendBeacon?.(`/api/sessions/${enc(sessionId)}/stop`) ?? false;
  } catch {
    return false;
  }
}
