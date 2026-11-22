// HTTP status / network failure -> the problem the app shows (section 6.1). Pure.
// The web never shows the backend's "detail": it shows its own copy, chosen here.

export type ProblemKind =
  | "offline" | "waking" | "unreachable" | "session_full" | "agora_start" | "agora_sdk"
  | "agora_join" | "session_ended" | "profile_lost" | "server";

export const PROBLEM_KINDS: readonly ProblemKind[] = [
  "offline", "waking", "unreachable", "session_full", "agora_start", "agora_sdk",
  "agora_join", "session_ended", "profile_lost", "server",
];

/** A failed call: an HTTP status, a network error (fetch threw / socket could not open) or a client timeout. */
export type Failure = number | "network" | "timeout";

/** Which call failed. "probe" = GET /healthz; "user" = GET /api/users/{id}; "start" = POST .../start;
 *  "agora" = GET .../agora; "other" = anything else. */
export type Op = "probe" | "user" | "start" | "agora" | "other";

export interface ProblemContext {
  op: Op;
  /** navigator.onLine; false always means offline. */
  online?: boolean;
  /** How long the app has been probing the backend without success (ms). Undefined outside the probe. */
  probingForMs?: number;
}

/** Waking turns into unreachable after this long without an answer. */
export const WAKING_WINDOW_MS = 90_000;

const isGateway = (f: Failure) => f === "network" || f === "timeout" || f === 502 || f === 503 || f === 504;

export function problemOfHttp(failure: Failure, ctx: ProblemContext): ProblemKind {
  if (ctx.online === false && (failure === "network" || failure === "timeout")) return "offline";
  if (ctx.op === "user" && failure === 404) return "profile_lost";
  if (ctx.op === "start") {
    if (failure === 409) return "session_full";
    if (failure === 502) return "agora_start";
    if (failure === 404) return "profile_lost";
  }
  if (ctx.op === "agora" && (failure === 404 || failure === 409)) return "session_ended";
  if (isGateway(failure)) {
    if (ctx.probingForMs !== undefined) return ctx.probingForMs < WAKING_WINDOW_MS ? "waking" : "unreachable";
    return "unreachable";
  }
  return "server";
}

/** The i18n keys of a problem's title and body. */
export function problemCopyKeys(kind: ProblemKind): { title: `problem_${ProblemKind}_title`; body: `problem_${ProblemKind}_body` } {
  return { title: `problem_${kind}_title`, body: `problem_${kind}_body` };
}
