import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { hintLifetimeMs, hintRemaining, initialLive, liveHint, liveReducer, myWords, type LiveState } from "./events.ts";
import { EVENT_TYPES, isMochiEvent, type LearningEvent, type MochiEvent } from "../contracts.ts";

const examplesDir = fileURLToPath(new URL("../../../../packages/contracts/examples/events/", import.meta.url));
const examples: Record<string, MochiEvent> = {};
for (const f of readdirSync(examplesDir).filter((n) => n.endsWith(".json"))) {
  examples[f.replace(/\.json$/, "")] = JSON.parse(readFileSync(examplesDir + f, "utf8"));
}

function ev<T extends MochiEvent>(base: T, over: Partial<MochiEvent>): T {
  return { ...base, ...over } as T;
}
const run = (s: LiveState, e: MochiEvent, now = 1000) => liveReducer(s, { type: "event", event: e, now });

// The examples follow the backend's contracts (v0.7, docs/DECISIONS.md D-58): the game's two events are
// gone from them, and three events this app does not show yet were added. The ones it knows must pass the
// guards; the others must be dropped by them, as they are on the socket.
test("every contracts example event the app knows passes the type guards, the others are dropped", () => {
  const known = (name: string) => (EVENT_TYPES as readonly string[]).includes(name);
  assert.equal(Object.keys(examples).filter(known).length, 6);
  for (const [name, e] of Object.entries(examples)) assert.equal(isMochiEvent(e), known(name), name);
});

test("a duplicate sequence is ignored, a gap is fine", () => {
  let s = initialLive("ana", "demo");
  s = run(s, examples["session.state.changed"]);
  const again = run(s, ev(examples["session.state.changed"], { payload: { ...examples["session.state.changed"].payload, capturing: false } } as Partial<MochiEvent>));
  assert.equal(again, s);
  const gap = run(s, ev(examples["agent.speak.requested"], { sequence: 99 }));
  assert.equal(gap.speak?.text, "You can say: queue.");
});

test("a new connection forgets the applied numbers", () => {
  let s = run(initialLive("ana", "demo"), examples["session.state.changed"]);
  s = liveReducer(s, { type: "connected" });
  assert.deepEqual(s.applied, []);
  const re = run(s, examples["session.state.changed"]);
  assert.notEqual(re, s);
});

test("a hint shows until its server lifetime ends", () => {
  const s = run(initialLive("ana", "demo"), examples["hint.created"], 1000);
  assert.equal(hintLifetimeMs("2026-11-19T16:00:12.700Z", "2026-11-19T16:00:04.700Z"), 8000);
  assert.equal(liveHint(s, 1000)?.expression, "postpone");
  assert.equal(liveHint(s, 8999)?.expression, "postpone");
  assert.equal(liveHint(s, 9000), null);
  assert.equal(hintRemaining(s, 5000), 0.5);
  assert.deepEqual(s.sessionHints.map((h) => h.expression), ["postpone"]);
});

test("odd hint times fall back to 8 s and cap at 60 s", () => {
  assert.equal(hintLifetimeMs("nope", "2026-11-19T16:00:04.700Z"), 8000);
  assert.equal(hintLifetimeMs("2026-11-19T16:00:00.000Z", "2026-11-19T16:00:04.700Z"), 8000);
  assert.equal(hintLifetimeMs("2026-11-19T17:00:00.000Z", "2026-11-19T16:00:00.000Z"), 60_000);
});

test("hint.cleared removes the hint", () => {
  let s = run(initialLive("ana", "demo"), examples["hint.created"]);
  s = run(s, examples["hint.cleared"]);
  assert.equal(liveHint(s, 1001), null);
});

test("learning_event.updated replaces by id; ASSISTED raises the used badge", () => {
  let s = run(initialLive("ana", "demo"), examples["learning_event.created"], 1000);
  const created = examples["learning_event.created"].payload as LearningEvent;
  const assisted: LearningEvent = {
    ...created, learning_state: "ASSISTED",
    state_history: [...created.state_history, { learning_state: "ASSISTED", at: "2026-11-19T16:00:30.000Z" }],
  };
  s = run(s, ev(examples["learning_event.updated"], { sequence: 50, payload: assisted }), 2000);
  assert.equal(Object.keys(s.words).length, 1);
  assert.equal(s.words[created.learning_event_id].learning_state, "ASSISTED");
  assert.deepEqual(s.used, { expression: created.expression, at: 2000 });
  assert.equal(s.proudAt, 2000);
  const reinforced: LearningEvent = { ...assisted, learning_state: "REINFORCED", state_history: [...assisted.state_history, { learning_state: "REINFORCED", at: "2026-11-19T16:01:00.000Z" }] };
  s = run(s, ev(examples["learning_event.updated"], { sequence: 51, payload: reinforced }), 3000);
  assert.equal(s.excitedAt, 3000);
});

test("someone else's word update raises no badge", () => {
  const w = { ...(examples["learning_event.updated"].payload as LearningEvent), user_id: "ben", learning_state: "ASSISTED" as const };
  const s = run(initialLive("ana", "demo"), ev(examples["learning_event.updated"], { payload: w }));
  assert.equal(s.used, null);
  assert.deepEqual(myWords(s), []);
});

test("events of another session are ignored, learning events are not", () => {
  let s = initialLive("ana", "w-3f9c1a2b");
  s = run(s, examples["hint.created"]); // session_id "demo"
  assert.equal(s.hint, null);
  s = run(s, examples["learning_event.created"]);
  assert.equal(myWords(s).length, 1);
});

test("following a new session forgets the old live state but keeps the words", () => {
  let s = run(initialLive("ana", "demo"), examples["hint.created"]);
  s = run(s, examples["learning_event.created"]);
  s = liveReducer(s, { type: "follow", sessionId: "w-00000000" });
  assert.equal(s.hint, null);
  assert.deepEqual(s.sessionHints, []);
  assert.equal(myWords(s).length, 1);
});

test("loaded words merge, keeping the copy with more history", () => {
  const live = examples["learning_event.created"].payload as LearningEvent;
  const longer: LearningEvent = { ...live, learning_state: "ASSISTED", state_history: [...live.state_history, { learning_state: "ASSISTED", at: "2026-11-19T16:01:00.000Z" }] };
  let s = liveReducer(initialLive("ana"), { type: "words", words: [longer] });
  s = liveReducer(s, { type: "words", words: [live] });
  assert.equal(s.words[live.learning_event_id].learning_state, "ASSISTED");
});

test("the private prompt never lands in state", () => {
  const prompt = {
    ...examples["hint.created"], type: "activity.private_prompt",
    payload: { round_id: "round_1", describer_user_id: "ana", secret_word: "umbrella", source_learning_event_id: null },
  } as unknown as MochiEvent; // the backend no longer sends one, so there is no example file to read
  const s = run(initialLive("ana", "demo"), prompt);
  assert.equal(JSON.stringify(s).includes("umbrella"), false);
});
