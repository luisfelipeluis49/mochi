import assert from "node:assert/strict";
import { test } from "node:test";
import type { Activity, EventType, MochiEvent, PayloadByType } from "../contracts.ts";
import { sessionStage } from "./sessionStage.ts";
import { type ClientState, applyEvent, initialState } from "./store.ts";

const T0 = Date.parse("2026-11-21T22:00:00.000Z");
let n = 0;
const ev = <K extends EventType>(type: K, payload: PayloadByType[K]) =>
  ({ schema_version: "0.4", event_id: `e${++n}`, type, session_id: "p-1", emitted_at: new Date(T0).toISOString(),
     sequence: n, payload }) as MochiEvent;

const live = (s: ClientState = initialState) => applyEvent(s, ev("session.state.changed",
  { status: "active", mode: "together", focus: "en", capturing: true, participants: ["ana", "ben"] }), T0);

const hint = (s: ClientState) => applyEvent(s, ev("hint.created", { hint_id: "h1", target_user_id: "ana", target_language: "en",
  expression: "postpone", meaning: "adiar", example: "I need to postpone my meeting.", reason: "code_switch",
  expires_at: new Date(T0 + 8000).toISOString() }), T0);

test("no session: ready to start", () => {
  assert.deepEqual(sessionStage(initialState, T0, true), { kind: "idle" });
});

test("in a session: Mochi's face, listening", () => {
  assert.deepEqual(sessionStage(live(), T0, true), { kind: "listening", mode: "together" });
});

test("a hint shows the word with its meaning and example, like Mochi's screen plus the details", () => {
  assert.deepEqual(sessionStage(hint(live()), T0 + 1000, true), { kind: "hint", options: ["postpone"], target: "ana",
    meaning: "adiar", example: "I need to postpone my meeting." });
});

test("Mochi answering out loud shows what it says", () => {
  const s = applyEvent(live(), ev("agent.speak.requested", { text: "You can say: queue.", language: "en", reason: "asks_mochi" }), T0);
  assert.deepEqual(sessionStage(s, T0 + 500, true), { kind: "speaking", text: "You can say: queue." });
});

test("no game on the phone: a round shows the listening face", () => {
  const round: Activity = { activity_id: "describe_and_guess", round_id: "r1", state: "ACTIVE_ROUND", describer_user_id: "ben",
    guesser_user_id: "ana", public_instruction: "", result: null, revealed_word: null, word_source: "stock" };
  const s = applyEvent(live(), ev("activity.state.changed", round), T0);
  assert.equal(sessionStage(s, T0, true).kind, "listening");
});

test("a session this phone did not start shows no words", () => {
  assert.equal(sessionStage(hint(live()), T0 + 1000, false).kind, "listening");
});
