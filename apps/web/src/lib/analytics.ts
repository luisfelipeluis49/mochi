// =============================================================================
// analytics.ts  —  LANGUAGE: TypeScript (no React, no screen)
// -----------------------------------------------------------------------------
// The numbers on the phone's analytics page ("Mochi Mobile"). It only COUNTS what
// the backend already sent to this phone (its words and its session summaries);
// it never decides anything about learning. Tested in analytics.test.ts.
// =============================================================================

import type { LearningEvent, LearningState, SessionSummary } from "../contracts.ts";
import type { ClientState } from "./store.ts";

/** Did this word ever reach this step? (looks at its whole history, not just where it is now) */
function reached(w: LearningEvent, step: LearningState): boolean {
  return w.state_history.some((h) => h.learning_state === step);
}

export interface Progress {
  words: number;          // new words learnt (every saved word)
  usedWithHelp: number;   // words that reached "Used with help"
  recalled: number;       // words that reached "Recalled in a game"
  onYourOwn: number;      // words that reached "Used on your own"
  minutes: number;        // minutes of speaking practice, all sessions added up
  sessions: number;       // how many session summaries we have
}

/** The "Your progress" numbers. */
export function progress(state: ClientState): Progress {
  const words = Object.values(state.words);
  const sessions = Object.values(state.summaries);
  return {
    words: words.length,
    usedWithHelp: words.filter((w) => reached(w, "ASSISTED")).length,
    recalled: words.filter((w) => reached(w, "REINFORCED")).length,
    onYourOwn: words.filter((w) => reached(w, "USED_INDEPENDENTLY")).length,
    minutes: sessions.reduce((sum, s) => sum + s.speaking_minutes, 0),
    sessions: sessions.length,
  };
}

/** Every session, oldest first (for the "minutes per session" bars). */
export function sessionHistory(state: ClientState): SessionSummary[] {
  return Object.values(state.summaries).sort((a, b) => Date.parse(a.created_at) - Date.parse(b.created_at));
}

/** The most recent session, or null if there is none yet. */
export function lastSession(state: ClientState): SessionSummary | null {
  return sessionHistory(state).at(-1) ?? null;
}

/** Bar width in % for one session, compared to the longest session. */
export function barPercent(minutes: number, history: SessionSummary[]): number {
  const max = Math.max(1, ...history.map((s) => s.speaking_minutes));
  return Math.round((minutes / max) * 100);
}
