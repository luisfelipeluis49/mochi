import { test } from "node:test";
import assert from "node:assert/strict";
import { buildDigest, nextDay, weekKeys } from "./digest.ts";
import type { LearningEvent, SessionRecord } from "../contracts.ts";

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

// 2026-11-21 is a Saturday: its week is Mon 16 Nov .. Sun 22 Nov.
const NOW = Date.parse("2026-11-21T15:00:00.000Z");
const monday = rec("1", "2026-11-16T13:00:00.000Z", "2026-11-16T13:10:00.000Z", { hint_count: 2 });
const saturday = rec("2", "2026-11-21T13:00:00.000Z", "2026-11-21T13:12:30.000Z", { hint_count: 3 });
const saturday2 = rec("3", "2026-11-21T14:00:00.000Z", "2026-11-21T14:05:00.000Z", { hint_count: 0 });
const lastWeek = rec("0", "2026-11-12T13:00:00.000Z", "2026-11-12T13:20:00.000Z", { hint_count: 5 });
const all = [lastWeek, monday, saturday, saturday2];
const words = [
  word("postpone", [["DISCOVERED", "2026-11-16T13:01:00.000Z"], ["ASSISTED", "2026-11-21T13:03:00.000Z"]]),
  word("umbrella", [["DISCOVERED", "2026-11-21T13:05:00.000Z"]]),
  word("queue", [["DISCOVERED", "2026-11-12T10:00:00.000Z"], ["REINFORCED", "2026-11-21T13:10:00.000Z"]]),
  word("receipt", [["DISCOVERED", "2026-11-19T10:00:00.000Z"]], { meaning: null }),
];

test("a week runs Monday to Sunday and weeks go back", () => {
  assert.deepEqual(weekKeys(NOW, 0, TZ), ["2026-11-16", "2026-11-17", "2026-11-18", "2026-11-19", "2026-11-20", "2026-11-21", "2026-11-22"]);
  assert.equal(weekKeys(NOW, 1, TZ)[0], "2026-11-09");
  assert.equal(weekKeys(Date.parse("2026-11-22T20:00:00.000Z"), 0, TZ)[0], "2026-11-16"); // a Sunday still belongs to its Monday
  assert.equal(nextDay("2026-11-30"), "2026-12-01");
});

test("totals add up every session of the week, not one", () => {
  const d = buildDigest(all, words, NOW, en);
  assert.deepEqual(d.totals, { sessions: 3, minutes: 27.5, hints: 5, activeDays: 2 });
  assert.equal(d.empty, false);
  assert.deepEqual(d.days.map((x) => x.minutes), [10, 0, 0, 0, 0, 17.5, 0]);
  assert.deepEqual(d.days.map((x) => x.sessions), [1, 0, 0, 0, 0, 2, 0]);
});

test("the week before gives the comparison, and offset 1 is that week", () => {
  const d = buildDigest(all, words, NOW, en);
  assert.equal(d.previous.minutes, 20);
  assert.equal(d.deltaMinutes, 7.5);
  const prev = buildDigest(all, words, NOW, en, 1);
  assert.equal(prev.totals.sessions, 1);
  assert.equal(prev.offset, 1);
});

test("words are grouped by what happened during the week", () => {
  const d = buildDigest(all, words, NOW, en);
  const g = Object.fromEntries(d.groups.map((x) => [x.state, x.words.map((w) => w.expression)]));
  assert.deepEqual(g, { DISCOVERED: ["postpone", "umbrella", "receipt"], ASSISTED: ["postpone"], REINFORCED: ["queue"] });
  assert.equal(d.newWords, 3);
});

test("a week with no session is empty but still has seven days", () => {
  const d = buildDigest(all, words, NOW, en, 3);
  assert.equal(d.empty, true);
  assert.equal(d.days.length, 7);
  assert.equal(d.options.length, 8);
  assert.equal(d.options[0].label, "This week");
});

test("the range reads in the language", () => {
  assert.equal(buildDigest(all, words, NOW, en).range, "16 Nov – 22 Nov");
  assert.match(buildDigest(all, words, NOW, { lang: "pt-BR", timeZone: TZ }).range, /^16 de nov\.? – 22 de nov\.?$/);
});
