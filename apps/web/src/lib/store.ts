// =============================================================================
// store.ts  —  LANGUAGE: TypeScript (no React, no screen)
// -----------------------------------------------------------------------------
// The page's MEMORY. Every message (event) from the backend comes through here.
// applyEvent() takes "what we know so far" + "one new event" and returns
// "what we know now". It never changes the old data; it makes a new copy.
// Because these are plain functions, they are easy to test (see store.test.ts).
// Rule from AGENTS.md: the browser never decides who may see what. It only
// remembers and shows what the backend sent.
// =============================================================================

import type { Activity, ConversationReport, Hint, LearningEvent, MochiEvent, PrivatePrompt, Session, SessionSummary, Speak, SpeakerChanged } from "../contracts.ts";

// How many events the ?debug=1 list keeps.
export const DEBUG_LOG_SIZE = 10;

// Everything a page knows. One field per kind of event.
export interface ClientState {
  /** sequence numbers already applied on this connection (to ignore duplicates) */
  applied: number[];
  session: Session | null;          // is Mochi listening? which mode?
  activity: Activity | null;        // the game state (IDLE / ACTIVE_ROUND / ROUND_RESULT)
  /** the time (ms) when the current game state arrived, to show the result for a few seconds */
  activityReceivedAt: number;
  hint: Hint | null;                // the latest hint
  /** client clock (ms) until which the hint is shown. Worked out from the SERVER's own times
   *  (expires_at − emitted_at) counted from when it arrived, so a wrong device clock (a Pi has no
   *  clock battery) cannot hide or stretch hints. */
  hintShownUntil: number;
  privatePrompt: PrivatePrompt | null; // the SECRET word (only Mochi's screen receives this)
  words: Record<string, LearningEvent>; // saved words, by their id
  speaking: { speak: Speak; receivedAt: number } | null; // Mochi talking out loud
  summaries: Record<string, SessionSummary>; // every session summary received, by id (phone only; PROPOSED v0.5)
  reports: Record<string, ConversationReport>; // every conversation report, by id (the /me page; PROPOSED v0.5)
  speaker: SpeakerChanged | null;   // whose voice Mochi hears right now (PROPOSED v0.5)
  /** last events received, newest first, at most DEBUG_LOG_SIZE (for ?debug=1) */
  log: MochiEvent[];
}

// What a page knows before anything arrives: nothing.
export const initialState: ClientState = {
  applied: [],
  session: null,
  activity: null,
  activityReceivedAt: 0,
  hint: null,
  hintShownUntil: 0,
  privatePrompt: null,
  words: {},
  speaking: null,
  summaries: {},
  reports: {},
  speaker: null,
  log: [],
};

/** Called when a NEW connection opens. The server re-sends the current state, maybe
 *  with sequence numbers we have seen before, so we forget the old numbers. */
export function onNewConnection(state: ClientState): ClientState {
  return { ...state, applied: [] };
}

/** THE MAIN FUNCTION: apply one event and return the new state. */
export function applyEvent(state: ClientState, event: MochiEvent, now: number): ClientState {
  // Each event has a "sequence" number. If we already applied it, ignore it (AGENTS.md §6.1).
  if (state.applied.includes(event.sequence)) return state;

  // Start from a copy of the old state, remember this sequence number, and add the event to the debug list.
  const next: ClientState = {
    ...state,
    applied: [...state.applied, event.sequence].slice(-500), // keep only the last 500 numbers
    log: [event, ...state.log].slice(0, DEBUG_LOG_SIZE),
  };

  // Update the right field depending on the event type.
  switch (event.type) {
    case "session.state.changed":   // Start/Stop pressed, or mode changed
      next.session = event.payload;
      break;
    case "hint.created": {          // a new hint word
      next.hint = event.payload;
      next.hintShownUntil = now + hintLifetimeMs(event.payload.expires_at, event.emitted_at);
      break;
    }
    case "hint.cleared":            // backend says "remove this hint" (only if it is the one on screen)
      if (state.hint?.hint_id === event.payload.hint_id) next.hint = null;
      break;
    case "activity.state.changed":  // the game moved to a new state
      next.activity = event.payload;
      next.activityReceivedAt = now;
      break;
    case "activity.private_prompt": // the secret word (Mochi's screen only)
      next.privatePrompt = event.payload;
      break;
    case "learning_event.created":  // a new saved word
    case "learning_event.updated":  // a saved word moved to a new step (e.g. "Recalled in a game")
      next.words = { ...state.words, [event.payload.learning_event_id]: event.payload };
      break;
    case "agent.speak.requested":   // Mochi is about to talk
      next.speaking = { speak: event.payload, receivedAt: now };
      break;
    case "session.summary.created": // one session summary for this person (PROPOSED v0.5)
      next.summaries = { ...state.summaries, [event.payload.summary_id]: event.payload };
      break;
    case "conversation.report.created": // one analysed conversation for this person (PROPOSED v0.5)
      next.reports = { ...state.reports, [event.payload.report_id]: event.payload };
      break;
    case "speaker.changed":         // whose voice Mochi hears now (PROPOSED v0.5)
      next.speaker = event.payload;
      break;
  }
  return next;
}

/** The hint to show right now, or null if there is none or its time ran out. */
export function liveHint(state: ClientState, now: number): Hint | null {
  if (!state.hint) return null;
  return now < state.hintShownUntil ? state.hint : null;
}

/** Default and maximum time a hint stays, if the server's times are missing or odd. */
export const HINT_DEFAULT_MS = 8000;
export const HINT_MAX_MS = 60000;

/** How long a hint should stay, from the SERVER's own two times (both on the server's clock),
 *  so the device's clock never matters. Falls back to 8 s if a time is missing; never over 60 s. */
export function hintLifetimeMs(expiresAt: string, emittedAt: string): number {
  const ms = Date.parse(expiresAt) - Date.parse(emittedAt);
  if (!Number.isFinite(ms) || ms <= 0) return HINT_DEFAULT_MS;
  return Math.min(ms, HINT_MAX_MS);
}

/** A hint can hold up to 3 options separated by " · " ("me queimei · tomei muito sol").
 *  Returns them as a list, one per line on screen. */
export function hintOptions(expression: string): string[] {
  return expression.split("·").map((x) => x.trim()).filter(Boolean).slice(0, 3);
}

/** The name to show for whoever is talking, or null. Not shown when Mochi is not listening. */
export function speakerName(state: ClientState): string | null {
  if (!state.session?.capturing) return null;
  return state.speaker?.name ?? null;
}

/** How long to show "speaking". The backend doesn't say, so we guess from the text length
 *  (at least 2.5 seconds, about 85 ms per letter). */
export function speakingDurationMs(text: string): number {
  return Math.max(2500, text.length * 85);
}

/** Is Mochi (probably) still talking? */
export function isSpeaking(state: ClientState, now: number): boolean {
  if (!state.speaking) return false;
  return now - state.speaking.receivedAt < speakingDurationMs(state.speaking.speak.text);
}

// When was this word first saved? (the first entry of its history)
function createdAt(e: LearningEvent): number {
  return Date.parse(e.state_history[0]?.at ?? "") || 0;
}

/** "My words" list: newest word first. */
export function wordsNewestFirst(state: ClientState): LearningEvent[] {
  return Object.values(state.words).sort((a, b) => createdAt(b) - createdAt(a));
}

const SUPPORTED_SCHEMA = "0.4";
let warnedSchema = false; // warn only once per page

/** Turn the raw text from the WebSocket into an event object.
 *  Returns null for anything broken or unknown, so bad messages can't crash the page. */
export function parseEvent(raw: string): MochiEvent | null {
  try {
    const e = JSON.parse(raw);
    if (e && typeof e.type === "string" && typeof e.sequence === "number" && "payload" in e) {
      // A different schema_version is not a reason to drop the event: apply it, but say so once.
      if (e.schema_version !== SUPPORTED_SCHEMA && !warnedSchema) {
        warnedSchema = true;
        console.warn(`mochi: event schema_version ${String(e.schema_version)}, this app knows ${SUPPORTED_SCHEMA}; applying it anyway`);
      }
      return e as MochiEvent;
    }
  } catch {
    /* not valid JSON: ignore it */
  }
  return null;
}
