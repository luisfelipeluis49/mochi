import assert from "node:assert/strict";
import { test } from "node:test";
import type { EventType, MochiEvent, PayloadByType } from "../contracts.ts";
import { REDACTED, redactPayload } from "./debug.ts";

const ev = <K extends EventType>(type: K, payload: PayloadByType[K]) =>
  ({ schema_version: "0.4", event_id: "e", type, session_id: "demo", emitted_at: "2026-11-19T16:00:00.000Z", sequence: 1, payload }) as MochiEvent;

const act = (state: "ACTIVE_ROUND" | "ROUND_RESULT", revealed_word: string | null) => ({
  activity_id: "describe_and_guess", round_id: "r1", state, describer_user_id: "ben", guesser_user_id: "ana",
  public_instruction: null, result: null, revealed_word, word_source: "stock" as const });

test("secret_word in the private prompt is hidden", () => {
  const out = JSON.stringify(redactPayload(ev("activity.private_prompt",
    { round_id: "r1", describer_user_id: "ben", secret_word: "umbrella", source_learning_event_id: null })));
  assert.ok(!out.includes("umbrella"));
  assert.ok(out.includes(REDACTED));
});

test("revealed_word is hidden during ACTIVE_ROUND but shown in ROUND_RESULT", () => {
  assert.ok(!JSON.stringify(redactPayload(ev("activity.state.changed", act("ACTIVE_ROUND", "umbrella")))).includes("umbrella"));
  assert.ok(JSON.stringify(redactPayload(ev("activity.state.changed", act("ROUND_RESULT", "umbrella")))).includes("umbrella"));
});

test("other payloads are untouched", () => {
  const p = { text: "hi", language: "en" as const, reason: "asks_mochi" as const };
  assert.deepEqual(redactPayload(ev("agent.speak.requested", p)), p);
});
