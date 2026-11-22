// The reachability probe (section 6.2): GET /healthz until it answers 200.
// Each try has a 10 s client timeout (in api.health). Retries after 2, 4 and 8 s, then every 15 s.
// "waking" shows while the first try is pending and for the first 90 s; "unreachable" after that.

import type { Api, Timers } from "./api.ts";
import { ApiError } from "./api.ts";
import { type ProblemKind, problemOfHttp } from "./httpProblem.ts";

export const PROBE_BACKOFF_MS = [2000, 4000, 8000] as const;
export const PROBE_MAX_MS = 15_000;

export function probeBackoffMs(attempt: number): number {
  return PROBE_BACKOFF_MS[attempt] ?? PROBE_MAX_MS;
}

export type ProbeState =
  /** a try is in flight; `problem` is what to keep showing meanwhile ("waking" on the first try) */
  | { status: "pending"; problem: ProblemKind }
  | { status: "ok" }
  | { status: "failing"; problem: ProblemKind; retryInMs: number };

export interface Probe {
  /** Try again now (the "Try again" button); the backoff keeps going. */
  retryNow(): void;
  stop(): void;
}

export function startProbe(api: Pick<Api, "health">, deps: { timers: Timers; now: () => number; online: () => boolean; onState: (s: ProbeState) => void }): Probe {
  const began = deps.now();
  let attempt = 0;
  let timer: unknown = null;
  let stopped = false;
  let inFlight = false;
  let shownProblem: ProblemKind = "waking";

  const run = async () => {
    if (stopped || inFlight) return;
    timer = null;
    inFlight = true;
    deps.onState({ status: "pending", problem: shownProblem });
    try {
      await api.health();
      inFlight = false;
      if (!stopped) deps.onState({ status: "ok" });
      stopped = true;
    } catch (e) {
      inFlight = false;
      if (stopped) return;
      const failure = e instanceof ApiError ? e.status : "network";
      const problem = problemOfHttp(failure, { op: "probe", online: deps.online(), probingForMs: deps.now() - began });
      const wait = probeBackoffMs(attempt++);
      // a non-gateway answer (e.g. 404 from a wrong proxy) still counts as not reachable
      const shown: ProblemKind = problem === "server" ? (deps.now() - began < 90_000 ? "waking" : "unreachable") : problem;
      shownProblem = shown;
      deps.onState({ status: "failing", problem: shown, retryInMs: wait });
      timer = deps.timers.setTimeout(run, wait);
    }
  };
  void run();

  return {
    retryNow() {
      if (stopped || inFlight) return;
      if (timer !== null) deps.timers.clearTimeout(timer);
      void run();
    },
    stop() {
      stopped = true;
      if (timer !== null) deps.timers.clearTimeout(timer);
    },
  };
}
