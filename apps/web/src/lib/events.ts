// What the page knows from the backend's events. A pure reducer: (state, action) -> new state.
// The browser never decides who may see what: it shows what the gateway sent to this connection.

import type { Activity, Hint, LearningEvent, MochiEvent, SessionState, Speak } from "../contracts.ts";

/** How many applied sequence numbers are remembered (enough to drop any duplicate of a snapshot). */
export const APPLIED_LIMIT = 500;
export const HINT_DEFAULT_MS = 8000;
export const HINT_MAX_MS = 60_000;
/** How many hints of this session the Session screen lists. */
export const SESSION_HINTS_LIMIT = 20;

export interface LiveState {
  /** This page's user (to tell "this user's" learning events). */
  userId: string | null;
  /** The session this page follows; session-scoped events for another session are ignored. */
  sessionId: string | null;
  applied: number[];
  session: SessionState | null;
  /** client clock (ms) when `session` last changed */
  sessionChangedAt: number;
  activity: Activity | null;
  hint: Hint | null;
  /** client clock (ms) when the hint arrived and when it goes away */
  hintShownAt: number;
  hintShownUntil: number;
  /** Hints shown in this session, newest first. */
  sessionHints: Hint[];
  speak: Speak | null;
  speakAt: number;
  words: Record<string, LearningEvent>;
  /** The last of this user's words that reached ASSISTED live, for the "★ You used it!" badge. */
  used: { expression: string; at: number } | null;
  /** client clock (ms) when one of this user's words reached ASSISTED / REINFORCED live */
  proudAt: number;
  excitedAt: number;
}

export function initialLive(userId: string | null = null, sessionId: string | null = null): LiveState {
  return {
    userId, sessionId, applied: [], session: null, sessionChangedAt: 0, activity: null, hint: null,
    hintShownAt: 0, hintShownUntil: 0, sessionHints: [], speak: null, speakAt: 0, words: {},
    used: null, proudAt: 0, excitedAt: 0,
  };
}

export type LiveAction =
  | { type: "event"; event: MochiEvent; now: number }
  /** a new socket opened: the server re-sends its snapshot, maybe with numbers already applied */
  | { type: "connected" }
  /** the page follows another session (a new Start): forget what belonged to the old one */
  | { type: "follow"; sessionId: string }
  | { type: "user"; userId: string | null }
  | { type: "words"; words: LearningEvent[] };

/** How long a hint stays, from the server's own two times (both on the server clock), so a wrong
 *  device clock never hides or stretches it. 8 s when a time is missing; never more than 60 s. */
export function hintLifetimeMs(expiresAt: string, emittedAt: string): number {
  const ms = Date.parse(expiresAt) - Date.parse(emittedAt);
  if (!Number.isFinite(ms) || ms <= 0) return HINT_DEFAULT_MS;
  return Math.min(ms, HINT_MAX_MS);
}

const SESSION_SCOPED = new Set(["session.state.changed", "hint.created", "hint.cleared", "activity.state.changed", "agent.speak.requested", "activity.private_prompt"]);

function reached(e: LearningEvent, state: LearningEvent["learning_state"]): boolean {
  return e.learning_state === state || e.state_history.some((h) => h.learning_state === state);
}

/** Keep whichever copy of a word knows more history (a live update can be newer than a GET). */
function newer(a: LearningEvent | undefined, b: LearningEvent): LearningEvent {
  if (!a) return b;
  return b.state_history.length >= a.state_history.length ? b : a;
}

export function liveReducer(state: LiveState, action: LiveAction): LiveState {
  switch (action.type) {
    case "connected":
      return { ...state, applied: [] };
    case "user":
      return action.userId === state.userId ? state : { ...initialLive(action.userId, state.sessionId) };
    case "follow":
      if (action.sessionId === state.sessionId) return state;
      return {
        ...state, sessionId: action.sessionId, applied: [], session: null, sessionChangedAt: 0, activity: null,
        hint: null, hintShownAt: 0, hintShownUntil: 0, sessionHints: [], speak: null, speakAt: 0,
      };
    case "words": {
      const words = { ...state.words };
      for (const w of action.words) words[w.learning_event_id] = newer(words[w.learning_event_id], w);
      return { ...state, words };
    }
    case "event":
      return applyEvent(state, action.event, action.now);
  }
}

function applyEvent(state: LiveState, event: MochiEvent, now: number): LiveState {
  if (state.applied.includes(event.sequence)) return state; // a duplicate; a gap is fine
  if (SESSION_SCOPED.has(event.type) && state.sessionId !== null && event.session_id !== state.sessionId) return state;
  const next: LiveState = { ...state, applied: [...state.applied, event.sequence].slice(-APPLIED_LIMIT) };

  switch (event.type) {
    case "session.state.changed":
      next.session = event.payload;
      next.sessionChangedAt = now;
      break;
    case "hint.created": {
      const h = event.payload;
      next.hint = h;
      next.hintShownAt = now;
      next.hintShownUntil = now + hintLifetimeMs(h.expires_at, event.emitted_at);
      next.sessionHints = [h, ...state.sessionHints.filter((x) => x.hint_id !== h.hint_id)].slice(0, SESSION_HINTS_LIMIT);
      break;
    }
    case "hint.cleared":
      if (state.hint?.hint_id === event.payload.hint_id) next.hint = null;
      break;
    case "activity.state.changed":
      next.activity = event.payload;
      break;
    case "activity.private_prompt":
      // Never sent to a user connection; ignored if it ever arrives (the web shows no secret word).
      break;
    case "agent.speak.requested":
      next.speak = event.payload;
      next.speakAt = now;
      break;
    case "learning_event.created":
    case "learning_event.updated": {
      const w = event.payload;
      const before = state.words[w.learning_event_id];
      next.words = { ...state.words, [w.learning_event_id]: newer(before, w) };
      const mine = state.userId !== null && w.user_id === state.userId;
      if (mine && event.type === "learning_event.updated") {
        if (w.learning_state === "ASSISTED" && !(before && reached(before, "ASSISTED"))) {
          next.used = { expression: w.expression, at: now };
          next.proudAt = now;
        }
        if (w.learning_state === "REINFORCED" && !(before && reached(before, "REINFORCED"))) next.excitedAt = now;
      }
      break;
    }
  }
  return next;
}

/** The hint to show now, or null when there is none or its time ran out. */
export function liveHint(state: LiveState, now: number): Hint | null {
  return state.hint && now < state.hintShownUntil ? state.hint : null;
}

/** Fraction of the hint's time left, 1 -> 0 (for the countdown bar). */
export function hintRemaining(state: LiveState, now: number): number {
  const total = state.hintShownUntil - state.hintShownAt;
  if (!state.hint || total <= 0) return 0;
  return Math.max(0, Math.min(1, (state.hintShownUntil - now) / total));
}

/** This user's words, newest first (by the first time each was saved). */
export function myWords(state: LiveState): LearningEvent[] {
  return Object.values(state.words)
    .filter((w) => state.userId !== null && w.user_id === state.userId)
    .sort((a, b) => firstAt(b) - firstAt(a));
}

export function firstAt(e: LearningEvent): number {
  return Date.parse(e.state_history[0]?.at ?? "") || 0;
}

export function isCapturing(state: LiveState): boolean {
  return state.session?.capturing === true;
}
