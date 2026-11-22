// The microphone gate (section 5). It runs first on every load, so the browser asks for the
// microphone on the first visit. Every browser API comes in through `env`, so it is testable.
// On success every track is stopped at once: Agora opens its own track at Start.

import type { Timers } from "./api.ts";

export type MicProblem = "insecure" | "unsupported" | "denied" | "policy" | "no_device" | "busy" | "unknown";
export const MIC_PROBLEMS: readonly MicProblem[] = ["insecure", "unsupported", "denied", "policy", "no_device", "busy", "unknown"];

export type GateResult = { ok: true } | { ok: false; problem: MicProblem };

interface TrackLike { stop(): void }
interface StreamLike { getTracks(): TrackLike[] }

export interface MicEnv {
  isSecureContext: boolean;
  mediaDevices?: { getUserMedia?: (c: { audio: boolean }) => Promise<StreamLike> } | null;
  permissions?: { query?: (d: { name: string }) => Promise<{ state: string }> } | null;
  timers: Timers;
  /** The browser's question is about to open (show "Allow the microphone"). */
  onPrompt?: () => void;
  /** No answer after SLOW_PROMPT_MS (show the "Allow microphone" button; iOS may need a tap). */
  onSlow?: () => void;
}

export const SLOW_PROMPT_MS = 8000;

/** DOM error names and Agora error codes -> MicProblem.
 *  UNVERIFIED: the Agora codes (PERMISSION_DENIED, DEVICE_NOT_FOUND, NOT_READABLE) come from the
 *  Agora Web SDK docs and were not seen on a device here; the DOM `name` an Agora error carries is
 *  checked as a fallback. */
const BY_NAME: Record<string, MicProblem> = {
  NotAllowedError: "denied",
  PermissionDeniedError: "denied",
  PERMISSION_DENIED: "denied",
  SecurityError: "policy",
  NotFoundError: "no_device",
  DevicesNotFoundError: "no_device",
  OverconstrainedError: "no_device",
  DEVICE_NOT_FOUND: "no_device",
  NotReadableError: "busy",
  TrackStartError: "busy",
  AbortError: "busy",
  NOT_READABLE: "busy",
  TypeError: "unsupported",
  NOT_SUPPORTED: "unsupported",
};

export function micProblemOf(err: unknown): MicProblem {
  if (typeof err !== "object" || err === null) return "unknown";
  const e = err as { name?: unknown; code?: unknown; message?: unknown };
  const code = typeof e.code === "string" ? e.code : "";
  if (code && BY_NAME[code] && code !== "TypeError") return BY_NAME[code];
  const name = typeof e.name === "string" ? e.name : "";
  if (name && BY_NAME[name]) return BY_NAME[name];
  // Agora wraps the browser error; its message often names it ("NotAllowedError: Permission denied").
  const msg = typeof e.message === "string" ? e.message : "";
  for (const key of Object.keys(BY_NAME)) if (key.endsWith("Error") && key !== "TypeError" && msg.includes(key)) return BY_NAME[key];
  return "unknown";
}

export async function runMicGate(env: MicEnv): Promise<GateResult> {
  if (!env.isSecureContext) return { ok: false, problem: "insecure" };
  const gum = env.mediaDevices?.getUserMedia;
  if (!gum) return { ok: false, problem: "unsupported" };

  if (env.permissions?.query) {
    try {
      const st = await env.permissions.query({ name: "microphone" });
      if (st.state === "granted") return { ok: true };
      if (st.state === "denied") return { ok: false, problem: "denied" };
    } catch {
      /* Firefox and Safari may not know "microphone": ask getUserMedia */
    }
  }

  env.onPrompt?.();
  const slow = env.timers.setTimeout(() => env.onSlow?.(), SLOW_PROMPT_MS);
  try {
    const stream = await gum.call(env.mediaDevices, { audio: true });
    for (const t of stream.getTracks()) t.stop();
    return { ok: true };
  } catch (err) {
    return { ok: false, problem: micProblemOf(err) };
  } finally {
    env.timers.clearTimeout(slow);
  }
}

/** The browser's own env (only called in the browser). */
export function browserMicEnv(timers: Timers, hooks: Pick<MicEnv, "onPrompt" | "onSlow"> = {}): MicEnv {
  const nav = globalThis.navigator as Navigator | undefined;
  return {
    isSecureContext: globalThis.isSecureContext !== false,
    mediaDevices: nav?.mediaDevices as MicEnv["mediaDevices"],
    permissions: nav?.permissions as unknown as MicEnv["permissions"],
    timers,
    ...hooks,
  };
}

/** The same URL on https: (the action of the "insecure" problem). */
export function secureUrl(href: string): string {
  return href.replace(/^http:/, "https:");
}
