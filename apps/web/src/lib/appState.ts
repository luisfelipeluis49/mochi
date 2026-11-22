// The app's one store: a pure reducer over everything the screens show. The live backend state is
// lib/events.ts (nested as `live`); this file adds the mic gate, the probe, the identity, the
// session phase (idle -> starting -> capturing -> stopping) and the banners.

import type { LearningEvent, SessionRecord, User } from "../contracts.ts";
import { type LiveAction, type LiveState, initialLive, liveReducer } from "./events.ts";
import type { ProblemKind } from "./httpProblem.ts";
import type { UiLang } from "./i18n.ts";
import type { MicProblem } from "./mic.ts";
import type { ProbeState } from "./probe.ts";

export type GateView =
  | { status: "checking" }
  | { status: "prompt" }
  | { status: "slow" }
  | { status: "ok" }
  | { status: "failed"; problem: MicProblem }
  /** the person chose "Continue without microphone": Start is disabled with this reason */
  | { status: "skipped"; problem: MicProblem };

export type Banner = { type: "http"; kind: ProblemKind } | { type: "mic"; kind: MicProblem };

export type Phase = "idle" | "starting" | "capturing" | "stopping";

export interface SavedCard {
  minutes: number;
  hints: number;
}

export interface AppState {
  lang: UiLang;
  gate: GateView;
  probe: ProbeState;
  user: User | null;
  /** "checking" while GET /api/users/{id} runs for a stored user */
  identity: "none" | "checking" | "ok";
  note: "profile_lost" | null;
  live: LiveState;
  socket: "idle" | "open" | "retrying";
  online: boolean;
  phase: Phase;
  sessionId: string;
  startedAt: number;
  stoppedAt: number;
  /** this page asked for the Stop (so capturing=false is not "ended elsewhere") */
  stopRequested: boolean;
  banner: Banner | null;
  saved: SavedCard | null;
  /** a reload found this tab's session still capturing, and this page is not listening */
  rejoin: boolean;
  volume: number;
  volumePopAt: number;
  records: SessionRecord[];
}

export function initialApp(input: { lang: UiLang; user: User | null; sessionId: string; online?: boolean }): AppState {
  return {
    lang: input.lang,
    gate: { status: "checking" },
    probe: { status: "pending", problem: "waking" },
    user: input.user,
    identity: input.user ? "checking" : "none",
    note: null,
    live: initialLive(input.user?.user_id ?? null, input.sessionId),
    socket: "idle",
    online: input.online ?? true,
    phase: "idle",
    sessionId: input.sessionId,
    startedAt: 0,
    stoppedAt: 0,
    stopRequested: false,
    banner: null,
    saved: null,
    rejoin: false,
    volume: 80,
    volumePopAt: 0,
    records: [],
  };
}

export type AppAction =
  | { type: "lang"; lang: UiLang }
  | { type: "gate"; gate: GateView }
  | { type: "probe"; probe: ProbeState }
  | { type: "online"; online: boolean }
  | { type: "identity_ok"; user: User }
  /** the backend lost this user (404 or close 4400): forget it and show onboarding with a note */
  | { type: "lost_user" }
  | { type: "forget_user" }
  | { type: "user_created"; user: User }
  | { type: "live"; action: LiveAction }
  | { type: "socket"; status: AppState["socket"] }
  | { type: "words"; words: LearningEvent[] }
  | { type: "records"; records: SessionRecord[] }
  | { type: "start_begin"; sessionId: string }
  | { type: "start_ok"; now: number }
  | { type: "start_failed"; banner: Banner }
  | { type: "stop_begin" }
  | { type: "stop_done"; now: number; saved: SavedCard }
  /** the voice link dropped or failed after Start: back to idle with a banner */
  | { type: "voice_failed"; banner: Banner }
  | { type: "rejoin_ok"; now: number }
  | { type: "banner"; banner: Banner | null }
  | { type: "dismiss_saved" }
  | { type: "volume"; volume: number; now: number };

export function appReducer(s: AppState, a: AppAction): AppState {
  switch (a.type) {
    case "lang":
      return { ...s, lang: a.lang };
    case "gate":
      return { ...s, gate: a.gate };
    case "probe":
      return { ...s, probe: a.probe };
    case "online":
      return { ...s, online: a.online };
    case "identity_ok":
      return { ...s, user: a.user, identity: "ok", live: liveReducer(s.live, { type: "user", userId: a.user.user_id }) };
    case "lost_user":
      return { ...forgotten(s), note: "profile_lost" };
    case "forget_user":
      return { ...forgotten(s), note: null };
    case "user_created":
      return { ...s, user: a.user, identity: "ok", note: null, live: liveReducer(s.live, { type: "user", userId: a.user.user_id }) };
    case "socket":
      return { ...s, socket: a.status };
    case "words":
      return { ...s, live: liveReducer(s.live, { type: "words", words: a.words }) };
    case "records":
      return { ...s, records: a.records };
    case "live":
      return onLive(s, a.action);
    case "start_begin":
      return {
        ...s, phase: "starting", sessionId: a.sessionId, banner: null, saved: null, rejoin: false, stopRequested: false,
        startedAt: 0, stoppedAt: 0, live: liveReducer(s.live, { type: "follow", sessionId: a.sessionId }),
      };
    case "start_ok":
      return { ...s, phase: "capturing", startedAt: a.now };
    case "start_failed":
      return { ...s, phase: "idle", banner: a.banner };
    case "stop_begin":
      return { ...s, phase: "stopping", stopRequested: true, rejoin: false };
    case "stop_done":
      return { ...s, phase: "idle", stoppedAt: a.now, saved: a.saved };
    case "voice_failed":
      return { ...s, phase: "idle", banner: a.banner, rejoin: false };
    case "rejoin_ok":
      return { ...s, phase: "capturing", rejoin: false, startedAt: s.startedAt || a.now, banner: null };
    case "banner":
      return { ...s, banner: a.banner };
    case "dismiss_saved":
      return { ...s, saved: null };
    case "volume":
      return { ...s, volume: a.volume, volumePopAt: a.now };
  }
}

function forgotten(s: AppState): AppState {
  return {
    ...s, user: null, identity: "none", live: initialLive(null, s.sessionId), records: [],
    phase: "idle", rejoin: false, saved: null, banner: null,
  };
}

function onLive(s: AppState, action: LiveAction): AppState {
  const live = liveReducer(s.live, action);
  if (live === s.live) return s;
  let next: AppState = { ...s, live };
  if (action.type === "event" && action.event.type === "session.state.changed" && action.event.session_id === s.sessionId) {
    const capturing = action.event.payload.capturing;
    if (!capturing && s.phase === "capturing" && !s.stopRequested) {
      // The session ended without our Stop (an eviction, or Agora ended it): show it, go idle.
      next = { ...next, phase: "idle", banner: { type: "http", kind: "session_ended" }, stoppedAt: action.now };
    }
    if (capturing && s.phase === "idle" && !s.stopRequested) next = { ...next, rejoin: true };
    if (!capturing && s.rejoin) next = { ...next, rejoin: false };
  }
  return next;
}

/** May Start run now? (mic ready, backend reached, a user, not already running) */
export function canStart(s: AppState): boolean {
  return s.gate.status === "ok" && s.probe.status === "ok" && s.user !== null && s.phase === "idle" && !s.rejoin;
}

/** The reason Start is disabled because of the microphone, or null. */
export function micBlock(s: AppState): MicProblem | null {
  return s.gate.status === "skipped" || s.gate.status === "failed" ? s.gate.problem : null;
}
