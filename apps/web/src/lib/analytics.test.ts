// =============================================================================
// analytics.test.ts  —  LANGUAGE: TypeScript (tests, run with `npm test`)
// -----------------------------------------------------------------------------
// Tests for analytics.ts: the progress numbers, the session order, the bar sizes.
// Each test(...) block checks one rule. assert.equal(a, b) fails the test if a is not b.
// These run in Node.js without a browser or a backend.
// =============================================================================

import assert from "node:assert/strict";
import { test } from "node:test";
import type { LearningEvent, LearningState, SessionSummary } from "../contracts.ts";
import { barPercent, lastSession, progress, sessionHistory } from "./analytics.ts";
import { type ClientState, initialState } from "./store.ts";

const word = (id: string, steps: LearningState[]): LearningEvent => ({
  learning_event_id: id, user_id: "ana", target_language: "en", expression: id, meaning: null,
  detection_signal: "code_switch", hint_id: null, learning_state: steps.at(-1)!,
  state_history: steps.map((s, i) => ({ learning_state: s, at: `2026-11-20T10:0${i}:00.000Z` })),
});
const summary = (id: string, minutes: number, at: string): SessionSummary => ({
  summary_id: id, user_id: "ana", target_language: "en", speaking_minutes: minutes,
  strengths: [], to_review: [], new_expressions: [], next_step: null, created_at: at,
});

const state: ClientState = {
  ...initialState,
  words: {
    postpone: word("postpone", ["DISCOVERED", "ASSISTED"]),
    umbrella: word("umbrella", ["DISCOVERED", "REINFORCED"]),   // recalled without the "with help" step
    receipt: word("receipt", ["DISCOVERED"]),
  },
  summaries: {
    today: summary("today", 24, "2026-11-21T10:00:00.000Z"),
    yesterday: summary("yesterday", 12, "2026-11-20T10:00:00.000Z"),
  },
};

test("progress counts words by the steps they reached, and adds up minutes", () => {
  assert.deepEqual(progress(state), { words: 3, usedWithHelp: 1, recalled: 1, onYourOwn: 0, minutes: 36, sessions: 2 });
  assert.deepEqual(progress(initialState), { words: 0, usedWithHelp: 0, recalled: 0, onYourOwn: 0, minutes: 0, sessions: 0 });
});

test("sessions are oldest first; the last session is the newest", () => {
  assert.deepEqual(sessionHistory(state).map((s) => s.summary_id), ["yesterday", "today"]);
  assert.equal(lastSession(state)?.summary_id, "today");
  assert.equal(lastSession(initialState), null);
});

test("the longest session gets the full bar", () => {
  const h = sessionHistory(state);
  assert.equal(barPercent(24, h), 100);
  assert.equal(barPercent(12, h), 50);
});
