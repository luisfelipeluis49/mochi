import { test } from "node:test";
import assert from "node:assert/strict";
import { buildDigest, closingKey } from "./digest.ts";
import type { LearningEvent, SessionRecord } from "../contracts.ts";
import type { Progress } from "./training.ts";

const TZ = "America/Sao_Paulo"; // UTC-3, no daylight saving in 2026
const en = { lang: "en" as const, timeZone: TZ };

function rec(id: string, start: string, end: string, over: Partial<SessionRecord> = {}): SessionRecord {
  const minutes = Math.round((Date.parse(end) - Date.parse(start)) / 6000) / 10;
  return { record_id: id, session_id: `w-${id.padStart(8, "0")}`, user_id: "luis", started_at: start, ended_at: end, minutes, hint_count: 3, learning_event_ids: [], ...over };
}
function word(id: string, history: [LearningEvent["learning_state"], string][], over: Partial<LearningEvent> = {}): LearningEvent {
  return {
    learning_event_id: id, user_id: "luis", target_language: "en", expression: id, meaning: `m-${id}`, detection_signal: "code_switch",
    hint_id: null, learning_state: history[history.length - 1][0], state_history: history.map(([s, at]) => ({ learning_state: s, at })), ...over,
  };
}

const r1 = rec("1", "2026-11-21T13:00:00.000Z", "2026-11-21T13:12:30.000Z", {
  learning_event_ids: ["postpone", "umbrella", "gone", "queue"], hint_count: 3,
});
const words = [
  word("postpone", [["DISCOVERED", "2026-11-21T13:01:00.000Z"], ["ASSISTED", "2026-11-21T13:03:00.000Z"]]),
  word("umbrella", [["DISCOVERED", "2026-11-21T13:05:00.000Z"]]),
  word("queue", [["DISCOVERED", "2026-11-20T10:00:00.000Z"], ["REINFORCED", "2026-11-21T13:10:00.000Z"]]),
  word("receipt", [["DISCOVERED", "2026-11-19T10:00:00.000Z"]]),
];
const NOW = Date.parse("2026-11-21T15:00:00.000Z");

test("the newest record is selected; header in the locale", () => {
  const old = rec("0", "2026-11-20T13:00:00.000Z", "2026-11-20T13:05:00.000Z");
  const d = buildDigest([old, r1], words, {}, NOW, en)!;
  assert.equal(d.session.record_id, "1");
  assert.equal(d.header, "Saturday, 21 Nov · 10:00 · 12.5 min · 3 hints");
  assert.deepEqual(d.options.map((o) => o.record_id), ["1", "0"]);
  assert.equal(buildDigest([old, r1], words, {}, NOW, en, "0")!.session.record_id, "0");
  const pt = buildDigest([r1], words, {}, NOW, { lang: "pt-BR", timeZone: TZ })!;
  assert.match(pt.header, /^sábado, 21 de nov\.? · 10:00 · 12,5 min · 3 dicas$/);
});

test("words are grouped by what happened in the window; unknown ids are skipped", () => {
  const d = buildDigest([r1], words, {}, NOW, en)!;
  const g = Object.fromEntries(d.groups.map((x) => [x.state, x.words.map((w) => w.expression)]));
  assert.deepEqual(g, { DISCOVERED: ["postpone", "umbrella"], ASSISTED: ["postpone"], REINFORCED: ["queue"] });
  assert.equal(d.noWords, false);
  assert.equal(d.groups[0].titleKey, "digest_new");
});

test("a session whose words are all gone has no words", () => {
  const d = buildDigest([rec("2", "2026-11-21T13:00:00.000Z", "2026-11-21T13:10:00.000Z", { learning_event_ids: ["gone"] })], words, {}, NOW, en)!;
  assert.deepEqual(d.groups, []);
  assert.equal(d.noWords, true);
});

test("practise next: training-due first, then DISCOVERED oldest first, at most 3", () => {
  const progress: Progress = { queue: { box: 2, due_at: NOW - 1000, correct: 1, wrong: 0, last_at: 0 } };
  const d = buildDigest([r1], words, progress, NOW, en)!;
  assert.deepEqual(d.practiseNext.map((w) => w.expression), ["queue", "receipt", "umbrella"]);
});

test("the closing line follows the hint count", () => {
  assert.equal(closingKey(0), "digest_close_none");
  assert.equal(closingKey(1), "digest_close_few");
  assert.equal(closingKey(3), "digest_close_few");
  assert.equal(closingKey(4), "digest_close_many");
  assert.equal(buildDigest([{ ...r1, hint_count: 0 }], words, {}, NOW, en)!.closingKey, "digest_close_none");
});

test("no records is the empty state", () => {
  assert.equal(buildDigest([], words, {}, NOW, en), null);
});

test("today's totals use local days, across midnight", () => {
  // 02:30Z on the 22nd is 23:30 on the 21st in São Paulo; 03:30Z is 00:30 on the 22nd.
  const late = rec("a", "2026-11-22T02:20:00.000Z", "2026-11-22T02:30:00.000Z", { hint_count: 2 }); // 10 min, the 21st
  const after = rec("b", "2026-11-22T03:00:00.000Z", "2026-11-22T03:30:00.000Z", { hint_count: 1 }); // 30 min, the 22nd
  const now21 = Date.parse("2026-11-22T02:50:00.000Z"); // 23:50 on the 21st
  const d21 = buildDigest([late, r1], [], {}, now21, en)!;
  assert.deepEqual({ s: d21.today.sessions, m: d21.today.minutes, h: d21.today.hints }, { s: 2, m: 22.5, h: 5 });
  assert.equal(d21.today.line, "2 sessions · 22.5 min · 5 hints");
  const now22 = Date.parse("2026-11-22T04:00:00.000Z"); // 01:00 on the 22nd
  const d22 = buildDigest([after, late, r1], [], {}, now22, en)!;
  assert.deepEqual({ s: d22.today.sessions, m: d22.today.minutes, h: d22.today.hints }, { s: 1, m: 30, h: 1 });
  assert.equal(d22.today.line, "1 session · 30 min · 1 hint");
});
