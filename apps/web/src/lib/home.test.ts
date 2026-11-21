// =============================================================================
// home.test.ts  —  LANGUAGE: TypeScript (tests, run with `npm test`)
// -----------------------------------------------------------------------------
// Tests for home.ts: Mochi's screens and what tap / long press do in the game.
// Each test(...) block checks one rule. assert.equal(a, b) fails the test if a is not b.
// These run in Node.js without a browser or a backend.
// =============================================================================

import assert from "node:assert/strict";
import { test } from "node:test";
import type { Activity, EventType, MochiEvent, PayloadByType } from "../contracts.ts";
import { RESULT_SHOW_MS, applyAction, homeScreen, initialHomeLocal, onPress } from "./home.ts";
import { type ClientState, applyEvent, initialState } from "./store.ts";

const T0 = Date.parse("2026-11-19T16:01:00.000Z");
let n = 0;
const ev = <K extends EventType>(type: K, payload: PayloadByType[K]) =>
  ({ schema_version: "0.4", event_id: `e${++n}`, type, session_id: "demo",
     emitted_at: new Date(T0).toISOString(), sequence: n, payload }) as MochiEvent;

const activity: Activity = { activity_id: "describe_and_guess", round_id: "round_001", state: "ACTIVE_ROUND",
  describer_user_id: "ana", guesser_user_id: "sophie", public_instruction: "Ana describes. Sophie guesses!",
  result: null, revealed_word: null, word_source: "learning_event" };

function withRound(): ClientState {
  let s = applyEvent(initialState, ev("session.state.changed",
    { status: "active", mode: "activity", focus: "en", capturing: true, participants: ["ana", "sophie"] }), T0);
  s = applyEvent(s, ev("activity.state.changed", activity), T0);
  s = applyEvent(s, ev("activity.private_prompt",
    { round_id: "round_001", describer_user_id: "ana", secret_word: "umbrella", source_learning_event_id: "learn_002" }), T0);
  return s;
}

test("sleeping before Start, listening while capturing", () => {
  assert.equal(homeScreen(initialState, initialHomeLocal, T0).kind, "sleeping");
  const s = applyEvent(initialState, ev("session.state.changed",
    { status: "active", mode: "together", focus: "en", capturing: true, participants: ["ana", "sophie"] }), T0);
  assert.equal(homeScreen(s, initialHomeLocal, T0).kind, "listening");
});

test("hint shows its options, one per line, and who it is for", () => {
  const s = applyEvent(initialState, ev("hint.created", { hint_id: "h", target_user_id: "sophie", target_language: "pt-BR",
    expression: "me queimei · tomei muito sol", meaning: null, example: null, reason: "trails_off",
    expires_at: new Date(T0 + 8000).toISOString() }), T0);
  assert.deepEqual(homeScreen(s, initialHomeLocal, T0), { kind: "hint", options: ["me queimei", "tomei muito sol"], target: "sophie" });
});

test("after 'Oi, Mochi!' the screen asks which mode, then shows the mode", () => {
  const session = { status: "active" as const, focus: "en" as const, capturing: true, participants: ["ana", "sophie"] };
  let s = applyEvent(initialState, ev("session.state.changed", { ...session, mode: "choosing" }), T0);
  assert.equal(homeScreen(s, initialHomeLocal, T0).kind, "choosing");
  s = applyEvent(s, ev("session.state.changed", { ...session, mode: "practice" }), T0);
  assert.deepEqual(homeScreen(s, initialHomeLocal, T0), { kind: "listening", mode: "practice" });
});

test("the mode question wins over Mochi speaking it out loud", () => {
  let s = applyEvent(initialState, ev("session.state.changed",
    { status: "active", mode: "choosing", focus: "en", capturing: true, participants: ["ana", "sophie"] }), T0);
  s = applyEvent(s, ev("agent.speak.requested", { text: "Oi! O que vocês querem fazer hoje?", language: "pt-BR", reason: "asks_mochi" }), T0);
  assert.equal(homeScreen(s, initialHomeLocal, T0 + 100).kind, "choosing");
});

test("Mochi speaking shows what it says", () => {
  const s = applyEvent(initialState, ev("agent.speak.requested", { text: "Protetor solar.", language: "pt-BR", reason: "asks_mochi" }), T0);
  assert.deepEqual(homeScreen(s, initialHomeLocal, T0 + 500), { kind: "speaking", text: "Protetor solar." });
});

test("full round: hidden → tap reveals → tap sends guessed", () => {
  const s = withRound();
  let local = initialHomeLocal;

  const hidden = homeScreen(s, local, T0);
  assert.equal(hidden.kind, "game_hidden");
  assert.equal(onPress(hidden, "long"), null, "long press on hidden word does nothing");

  local = applyAction(local, onPress(hidden, "tap"));
  const revealed = homeScreen(s, local, T0);
  assert.deepEqual(revealed, { kind: "game_revealed", roundId: "round_001", word: "umbrella", guesser: "sophie" });

  const action = onPress(revealed, "tap");
  assert.deepEqual(action, { do: "send_result", roundId: "round_001", result: "guessed" });
  local = applyAction(local, action);
  const waiting = homeScreen(s, local, T0);
  assert.equal(waiting.kind, "game_waiting");
  assert.equal(onPress(waiting, "tap"), null, "no second send");
});

test("long press on revealed word sends skipped", () => {
  const s = withRound();
  const local = applyAction(initialHomeLocal, { do: "reveal", roundId: "round_001" });
  assert.deepEqual(onPress(homeScreen(s, local, T0), "long"), { do: "send_result", roundId: "round_001", result: "skipped" });
});

test("cannot reveal before the private prompt arrives", () => {
  let s = applyEvent(initialState, ev("activity.state.changed", activity), T0);
  const local = applyAction(initialHomeLocal, { do: "reveal", roundId: "round_001" });
  s = { ...s };
  assert.equal(homeScreen(s, local, T0).kind, "game_hidden");
});

test("result shows for a few seconds, then back to the face", () => {
  let s = withRound();
  s = applyEvent(s, ev("activity.state.changed", { ...activity, state: "ROUND_RESULT", result: "guessed", revealed_word: "umbrella" }), T0);
  assert.deepEqual(homeScreen(s, initialHomeLocal, T0 + 1000), { kind: "game_result", word: "umbrella", guesser: "sophie", result: "guessed" });
  assert.deepEqual(homeScreen(s, initialHomeLocal, T0 + RESULT_SHOW_MS + 1), { kind: "listening", mode: "activity" });
});

test("a new round starts hidden even if the last one was revealed", () => {
  let s = withRound();
  const local = applyAction(initialHomeLocal, { do: "reveal", roundId: "round_001" });
  s = applyEvent(s, ev("activity.state.changed", { ...activity, round_id: "round_002" }), T0);
  assert.equal(homeScreen(s, local, T0).kind, "game_hidden");
});

test("big words shrink to stay on one line", async () => {
  const { fitFontSize } = await import("./i18n.ts");
  assert.equal(fitFontSize("umbrella", 34), "min(34vh, 18.1vw)");
  assert.equal(fitFontSize("make it later", 34), "min(34vh, 29vw)");
});
