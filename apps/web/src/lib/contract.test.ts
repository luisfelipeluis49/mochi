// =============================================================================
// contract.test.ts  —  LANGUAGE: TypeScript (tests, run with `npm test`)
// -----------------------------------------------------------------------------
// Checks the web app against the OFFICIAL contract in packages/contracts (owner: Matheus),
// so a renamed field or a new value in the backend breaks THIS test in CI, not the screens
// on demo day. src/contracts.ts is a hand-written copy; this keeps it honest.
//   1. Every official example event is read and stored the way the screens expect.
//   2. Every field the screens read exists in the official JSON Schema.
//   3. The learning states the cards show are exactly the official ones.
// =============================================================================

import assert from "node:assert/strict";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { LEARNING_STATE_ORDER } from "../contracts.ts";
import { applyEvent, initialState, liveHint, parseEvent } from "./store.ts";

// apps/web/src/lib → repo root
const CONTRACTS = fileURLToPath(new URL("../../../../packages/contracts/", import.meta.url));
const here = existsSync(CONTRACTS);
const skip = here ? false : "packages/contracts not found (run inside the repository)";

const json = (path: string) => JSON.parse(readFileSync(CONTRACTS + path, "utf8"));

test("every official example event is read and stored as the screens expect", { skip }, () => {
  const dir = "examples/events/";
  const files = readdirSync(CONTRACTS + dir).filter((f) => f.endsWith(".json")).sort();
  assert.ok(files.length >= 8, "expected the 8 event examples");
  let s = initialState;
  const now = Date.parse("2026-11-19T16:00:05.000Z");
  for (const f of files) {
    const e = parseEvent(readFileSync(CONTRACTS + dir + f, "utf8"));
    assert.ok(e, `${f} was not recognised as an event`);
    s = applyEvent(s, e, now);
  }
  assert.equal(typeof s.session?.capturing, "boolean", "session.state.changed → session");
  assert.ok(s.activity?.state, "activity.state.changed → activity");
  assert.ok(s.privatePrompt?.secret_word, "activity.private_prompt → secret word");
  assert.ok(Object.values(s.words).every((w) => w.expression && w.state_history.length > 0), "learning events → word cards");
  assert.ok(s.speaking?.speak.text, "agent.speak.requested → speaking");
  // hint.created is applied before hint.cleared in file order; check it on its own:
  const hint = parseEvent(readFileSync(CONTRACTS + dir + "hint.created.json", "utf8"));
  assert.ok(hint);
  assert.ok(liveHint(applyEvent(initialState, hint, now), now)?.expression, "hint.created → a visible hint");
});

/** The fields the screens read, per official schema file. If one is renamed in the backend, this fails. */
const FIELDS_THE_SCREENS_READ: Record<string, string[]> = {
  "Envelope.json": ["schema_version", "event_id", "type", "emitted_at", "sequence", "payload"],
  "SessionState.json": ["status", "mode", "capturing", "participants"],
  "Hint.json": ["hint_id", "target_user_id", "expression", "meaning", "example", "expires_at"],
  "HintCleared.json": ["hint_id"],
  "Activity.json": ["round_id", "state", "describer_user_id", "guesser_user_id", "public_instruction", "result", "revealed_word"],
  "PrivatePrompt.json": ["round_id", "secret_word"],
  "LearningEvent.json": ["learning_event_id", "user_id", "target_language", "expression", "meaning", "learning_state", "state_history"],
  "Speak.json": ["text", "language", "reason"],
};

test("every field the screens read exists in the official schema", { skip }, () => {
  for (const [file, fields] of Object.entries(FIELDS_THE_SCREENS_READ)) {
    const props = Object.keys(json("schema/" + file).properties ?? {});
    for (const f of fields) assert.ok(props.includes(f), `${file}: the screens read "${f}", the schema has ${props.join(", ")}`);
  }
});

test("the learning states on the word cards are exactly the official ones", { skip }, () => {
  const schema = json("schema/LearningEvent.json");
  const def = Object.entries(schema.$defs ?? {}).find(([name]) => name === "LearningState")?.[1] as { enum?: string[] } | undefined;
  assert.ok(def?.enum, "LearningState enum not found in LearningEvent.json");
  assert.deepEqual([...def.enum].sort(), [...LEARNING_STATE_ORDER].sort());
});
