// =============================================================================
// store.test.ts  —  LANGUAGE: TypeScript (tests, run with `npm test`)
// -----------------------------------------------------------------------------
// Tests for store.ts: duplicates ignored, hints expire, words sorted, debug list size.
// Each test(...) block checks one rule. assert.equal(a, b) fails the test if a is not b.
// These run in Node.js without a browser or a backend.
// =============================================================================

import assert from "node:assert/strict";
import { test } from "node:test";
import type { EventType, LearningEvent, MochiEvent, PayloadByType } from "../contracts.ts";
import { applyEvent, initialState, isSpeaking, liveHint, onNewConnection, parseEvent, wordsNewestFirst } from "./store.ts";

const T0 = Date.parse("2026-11-19T16:00:04.700Z");
let n = 0;
function ev<K extends EventType>(type: K, payload: PayloadByType[K], sequence = ++n): MochiEvent {
  return { schema_version: "0.4", event_id: `evt_${sequence}`, type, session_id: "demo",
    emitted_at: new Date(T0).toISOString(), sequence, payload } as MochiEvent;
}

// Example payloads from AGENTS.md §6.2
const hint = { hint_id: "hint_015", target_user_id: "ana", target_language: "en" as const,
  expression: "postpone", meaning: "adiar", example: "I need to postpone my meeting.",
  reason: "code_switch" as const, expires_at: "2026-11-19T16:00:12.700Z" };
const word = (id: string, expression: string, at: string): LearningEvent => ({
  learning_event_id: id, user_id: "ana", target_language: "en", expression, meaning: null,
  detection_signal: "code_switch", hint_id: null, learning_state: "DISCOVERED",
  state_history: [{ learning_state: "DISCOVERED", at }] });

test("ignores an event whose sequence was already applied", () => {
  const e = ev("hint.created", hint, 42);
  const s1 = applyEvent(initialState, e, T0);
  const s2 = applyEvent(s1, ev("hint.cleared", { hint_id: "hint_015" }, 42), T0);
  assert.equal(s2, s1);
  assert.equal(s2.hint?.expression, "postpone");
});

test("a new connection forgets applied sequences", () => {
  const s1 = applyEvent(initialState, ev("hint.created", hint, 7), T0);
  const s2 = applyEvent(onNewConnection(s1), ev("hint.cleared", { hint_id: "hint_015" }, 7), T0);
  assert.equal(s2.hint, null);
});

test("hint is live until expires_at, then gone", () => {
  const s = applyEvent(initialState, ev("hint.created", hint), T0);
  assert.equal(liveHint(s, T0 + 7_999)?.expression, "postpone");
  assert.equal(liveHint(s, T0 + 8_000), null);
});

test("hint.cleared removes only the matching hint", () => {
  let s = applyEvent(initialState, ev("hint.created", hint), T0);
  s = applyEvent(s, ev("hint.cleared", { hint_id: "other" }), T0);
  assert.ok(s.hint);
  s = applyEvent(s, ev("hint.cleared", { hint_id: "hint_015" }), T0);
  assert.equal(s.hint, null);
});

test("learning_event.updated replaces the card; words are newest first", () => {
  let s = applyEvent(initialState, ev("learning_event.created", word("learn_001", "postpone", "2026-11-19T16:00:05.000Z")), T0);
  s = applyEvent(s, ev("learning_event.created", word("learn_002", "umbrella", "2026-11-19T16:00:20.000Z")), T0);
  const updated = { ...word("learn_001", "postpone", "2026-11-19T16:00:05.000Z"), learning_state: "ASSISTED" as const };
  s = applyEvent(s, ev("learning_event.updated", updated), T0);
  const list = wordsNewestFirst(s);
  assert.deepEqual(list.map((w) => w.expression), ["umbrella", "postpone"]);
  assert.equal(list[1].learning_state, "ASSISTED");
});

test("speaking lasts a moment then ends", () => {
  const s = applyEvent(initialState, ev("agent.speak.requested", { text: "You can say: queue.", language: "en", reason: "asks_mochi" }), T0);
  assert.equal(isSpeaking(s, T0 + 1000), true);
  assert.equal(isSpeaking(s, T0 + 10_000), false);
});

test("debug log keeps the last ten events, newest first", () => {
  let s = initialState;
  for (let i = 1; i <= 12; i++) s = applyEvent(s, ev("hint.cleared", { hint_id: "x" }, 1000 + i), T0);
  assert.equal(s.log.length, 10);
  assert.equal(s.log[0].sequence, 1012);
});

test("the session summary is kept (PROPOSED v0.5); hint options split on ·", async () => {
  const { hintOptions } = await import("./store.ts");
  const s = applyEvent(initialState, ev("session.summary.created", {
    summary_id: "sum_001", user_id: "sophie", target_language: "pt-BR", speaking_minutes: 24,
    strengths: ["Descrever objetos"], to_review: ["Pretérito: fui, comprei"], new_expressions: ["apesar de", "na verdade"],
    next_step: "Descreva e Adivinhe: histórias", created_at: "2026-11-19T16:30:00.000Z" }), T0);
  assert.equal(s.summaries.sum_001.speaking_minutes, 24);
  assert.deepEqual(hintOptions("although · unfortunately · instead · extra"), ["although", "unfortunately", "instead"]);
});

test("parseEvent rejects junk", () => {
  assert.equal(parseEvent("not json"), null);
  assert.equal(parseEvent('{"type":"x"}'), null);
  assert.equal(parseEvent(JSON.stringify(ev("hint.created", hint)))?.type, "hint.created");
});
