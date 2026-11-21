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
import { SECOND_USER, type Who } from "../lib/who.ts";
import { displayName } from "../lib/i18n.ts";
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
const sophie: Who = { kind: "user", user: SECOND_USER }; // the second demo person (ben in the backend roster today)
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
  assert.deepEqual(summaries(s), [SECOND_USER, SECOND_USER]);
  assert.equal(summaries(await run(audience)).length, 0);
});

test("the story: Oi Mochi → Companhia → game → Mochi congratulates → stop", async () => {
  const events = await run(audience);
  const modes = events.flatMap((e) => (e.type === "session.state.changed" ? [e.payload.mode] : []));
  assert.ok(modes.includes("choosing") && modes.includes("together") && modes.includes("activity"));
  const said = events.flatMap((e) => (e.type === "agent.speak.requested" ? [e.payload.text] : []));
  assert.ok(said.includes("Protetor solar."));
  assert.ok(said.includes(`Correct! ${displayName(SECOND_USER)}, your turn to describe.`));
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

test("conversation reports go only to their owner's page", async () => {
  const reports = (events: MochiEvent[]) => events.flatMap((e) =>
    e.type === "conversation.report.created" ? [e.payload.user_id] : []);
  assert.deepEqual(reports(await run({ kind: "user", user: "tasnim" })), ["tasnim", "tasnim", "tasnim", "tasnim"]);
  assert.equal(reports(await run(audience)).length, 0);
  assert.equal(reports(await run(home)).length, 0);
});

test("with ?people=tasnim,matheus the demo uses your names, and Mochi shows who is talking", async () => {
  const got: MochiEvent[] = [];
  const gw = new MockGateway({ kind: "device", device: "home_pi_01" }, (e) => got.push(e), 500, () => Date.now(), ["tasnim", "matheus"]);
  gw.connect(true);
  await new Promise((r) => setTimeout(r, 75));
  gw.activityResult("guessed");
  await new Promise((r) => setTimeout(r, 40));
  gw.clear();
  const speakers = got.flatMap((e) => (e.type === "speaker.changed" ? [e.payload.name] : []));
  assert.ok(speakers.includes("Tasnim") && speakers.includes("Matheus"));
  assert.equal(speakers.at(-1), null); // nobody after Stop
  const hintsFor = got.flatMap((e) => (e.type === "hint.created" ? [e.payload.target_user_id] : []));
  assert.deepEqual([...new Set(hintsFor)].sort(), ["matheus", "tasnim"]);
  const said = got.flatMap((e) => (e.type === "agent.speak.requested" ? [e.payload.text] : []));
  assert.ok(said.includes("Correct! Matheus, your turn to describe."));
});

test("Matheus gets his own past conversations", async () => {
  const titles = (await run({ kind: "user", user: "matheus" })).flatMap((e) =>
    e.type === "conversation.report.created" ? [e.payload.title] : []);
  assert.deepEqual(titles, ["Weekly sync with the team", "Demo rehearsal", "Weekly sync with the team"]);
});

test("on the /me page: Record → Stop saves ONE new conversation; a second recording is a separate one", async () => {
  const got: MochiEvent[] = [];
  const gw = new MockGateway({ kind: "user", user: "tasnim" }, (e) => got.push(e), 1, () => Date.now(), undefined, "recording");
  gw.connect(false);
  const before = got.filter((e) => e.type === "conversation.report.created").length; // the 4 past ones
  assert.equal(before, 4);
  assert.ok(!got.some((e) => e.type === "hint.created"), "nothing plays by itself on /me");

  gw.start(); await new Promise((r) => setTimeout(r, 20)); gw.stop();
  gw.start(); await new Promise((r) => setTimeout(r, 20)); gw.stop();
  gw.clear();

  const reports = got.flatMap((e) => (e.type === "conversation.report.created" ? [e.payload] : []));
  const fresh = reports.slice(before);
  assert.equal(fresh.length, 2);
  assert.notEqual(fresh[0].report_id, fresh[1].report_id);
  assert.notEqual(fresh[0].my_sentences[1].text, fresh[1].my_sentences[1].text); // different conversations
  for (const r of fresh) {
    assert.equal(r.user_id, "tasnim");
    assert.ok(r.my_sentences.length > 0);
    assert.ok(Date.parse(r.ended_at) >= Date.parse(r.started_at));
    // every mistake listed comes from one of HER sentences
    for (const m of r.mistakes) assert.ok(r.my_sentences.some((s) => s.text === m.said && s.better === m.better));
  }
  const recording = got.flatMap((e) => (e.type === "session.state.changed" ? [e.payload.capturing] : []));
  assert.deepEqual(recording.slice(-4), [true, false, true, false]);
});

test("past conversations carry only the owner's sentences, in order", async () => {
  const r = (await run({ kind: "user", user: "tasnim" })).flatMap((e) =>
    e.type === "conversation.report.created" ? [e.payload] : [])[0];
  const times = r.my_sentences.map((s) => Date.parse(s.at));
  assert.deepEqual(times, [...times].sort((a, b) => a - b));
  assert.equal(r.my_sentences[1].better, "Yesterday I sent the report to the client.");
});
