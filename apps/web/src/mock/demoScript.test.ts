// =============================================================================
// demoScript.test.ts  —  LANGUAGE: TypeScript (tests, run with `npm test`)
// -----------------------------------------------------------------------------
// Tests for the mock: it plays the product-vision story and gives each page only
// what the real backend would give it (secret word → Mochi only; words and
// summary → their owner only).
// Each test(...) block checks one rule. assert.equal(a, b) fails the test if a is not b.
// These run in Node.js without a browser or a backend.
// =============================================================================

import assert from "node:assert/strict";
import { test } from "node:test";
import type { MochiEvent } from "../contracts.ts";
import type { Who } from "../lib/who.ts";
import { MockGateway } from "./demoScript.ts";

// Run the whole scripted demo very fast (x500) and collect what one page receives.
async function run(who: Who): Promise<MochiEvent[]> {
  const got: MochiEvent[] = [];
  const gw = new MockGateway(who, (e) => got.push(e), 500);
  gw.connect(true);
  await new Promise((r) => setTimeout(r, 70));                 // reaches the game (~57 ms)
  if (who.kind === "device") gw.activityResult("guessed");    // on Mochi's screen, the "tap"
  await new Promise((r) => setTimeout(r, 60));                 // result, Mochi speaks, stop, summaries
  gw.clear();
  return got;
}

const ana: Who = { kind: "user", user: "ana" };
const sophie: Who = { kind: "user", user: "sophie" };
const home: Who = { kind: "device", device: "home_pi_01" };
const audience: Who = { kind: "audience" };

test("the secret word goes only to Mochi's screen", async () => {
  for (const who of [ana, sophie, audience]) {
    const events = await run(who);
    assert.ok(!events.some((e) => e.type === "activity.private_prompt"), JSON.stringify(who));
    for (const e of events) {
      if (e.type === "activity.state.changed" && e.payload.state === "ACTIVE_ROUND") assert.equal(e.payload.revealed_word, null);
    }
  }
  assert.ok((await run(home)).some((e) => e.type === "activity.private_prompt"));
});

test("each person gets only their own words and summary", async () => {
  const words = (events: MochiEvent[]) => events.flatMap((e) =>
    e.type === "learning_event.created" ? [e.payload.expression] : []);
  const summaries = (events: MochiEvent[]) => events.flatMap((e) =>
    e.type === "session.summary.created" ? [e.payload.user_id] : []);

  const a = await run(ana);
  const s = await run(sophie);
  assert.deepEqual(words(a), ["postpone", "umbrella"]);
  assert.deepEqual(words(s), ["me queimei", "protetor solar"]);
  assert.deepEqual(summaries(a), ["ana", "ana"]);       // yesterday + today
  assert.deepEqual(summaries(s), ["sophie", "sophie"]);
  assert.equal(summaries(await run(audience)).length, 0);
});

test("the story: Oi Mochi → Companhia → game → Mochi congratulates → stop", async () => {
  const events = await run(audience);
  const modes = events.flatMap((e) => (e.type === "session.state.changed" ? [e.payload.mode] : []));
  assert.ok(modes.includes("choosing") && modes.includes("together") && modes.includes("activity"));
  const said = events.flatMap((e) => (e.type === "agent.speak.requested" ? [e.payload.text] : []));
  assert.ok(said.includes("Protetor solar."));
  assert.ok(said.includes("Correct! Sophie, your turn to describe."));
  const last = events.filter((e) => e.type === "session.state.changed").at(-1);
  assert.equal(last?.type === "session.state.changed" && last.payload.capturing, false);
});

test("umbrella ends as 'Recalled in a game' on Ana's phone", async () => {
  const last = (await run(ana)).filter((e) => e.type === "learning_event.updated").at(-1);
  assert.equal(last?.type === "learning_event.updated" && last.payload.learning_state, "REINFORCED");
});

test("sequence numbers only go up", async () => {
  const events = await run(home);
  events.forEach((e, i) => i > 0 && assert.ok(e.sequence > events[i - 1].sequence));
});
