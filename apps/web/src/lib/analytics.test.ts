import { test } from "node:test";
import assert from "node:assert/strict";
import { buildAnalytics, dayStreak, statePath } from "./analytics.ts";
import type { LearningEvent, SessionRecord } from "../contracts.ts";

const TZ = "UTC";
const f = { lang: "en" as const, timeZone: TZ };
const NOW = Date.parse("2026-11-21T15:00:00.000Z");

function rec(id: string, day: string, minutes = 10, over: Partial<SessionRecord> = {}): SessionRecord {
  return { record_id: id, session_id: "w-00000000", user_id: "luis", started_at: `${day}T10:00:00.000Z`, ended_at: `${day}T10:10:00.000Z`, minutes, hint_count: 1, learning_event_ids: [], ...over };
}
function word(id: string, history: [LearningEvent["learning_state"], string][]): LearningEvent {
  return {
    learning_event_id: id, user_id: "luis", target_language: "en", expression: id, meaning: "m", detection_signal: "code_switch",
    hint_id: null, learning_state: history[history.length - 1][0], state_history: history.map(([s, at]) => ({ learning_state: s, at })),
  };
}
const words = [
  word("a", [["DISCOVERED", "2026-11-19T10:00:00.000Z"]]),
  word("b", [["DISCOVERED", "2026-11-20T10:00:00.000Z"], ["ASSISTED", "2026-11-20T10:02:00.000Z"]]),
  word("c", [["DISCOVERED", "2026-11-21T10:00:00.000Z"], ["ASSISTED", "2026-11-21T10:01:00.000Z"], ["REINFORCED", "2026-11-21T10:05:00.000Z"]]),
];

test("tiles", () => {
  const v = buildAnalytics(words, [rec("1", "2026-11-20", 12.5), rec("2", "2026-11-21", 3.04)], { a: { box: 1, due_at: 0, correct: 3, wrong: 1, last_at: 0 } }, NOW, f);
  assert.deepEqual(v.tiles, { words: 3, assisted: 2, reinforced: 1, independent: 0, sessions: 2, minutes: 15.5, streak: 2, accuracy: 0.75 });
  assert.equal(v.empty, false);
  assert.deepEqual(v.words.map((w) => w.learning_event_id), ["c", "b", "a"]);
  assert.deepEqual(v.states, [
    { state: "DISCOVERED", count: 1 }, { state: "ASSISTED", count: 1 }, { state: "REINFORCED", count: 1 }, { state: "USED_INDEPENDENTLY", count: 0 },
  ]);
});

test("accuracy is null with no training", () => {
  assert.equal(buildAnalytics(words, [], {}, NOW, f).tiles.accuracy, null);
});

test("streak: ending today, ending yesterday, broken", () => {
  assert.equal(dayStreak([rec("1", "2026-11-21"), rec("2", "2026-11-20"), rec("3", "2026-11-19")], NOW, TZ), 3);
  assert.equal(dayStreak([rec("2", "2026-11-20"), rec("3", "2026-11-19")], NOW, TZ), 2);
  assert.equal(dayStreak([rec("1", "2026-11-21"), rec("3", "2026-11-19")], NOW, TZ), 1);
  assert.equal(dayStreak([rec("3", "2026-11-19")], NOW, TZ), 0);
  assert.equal(dayStreak([], NOW, TZ), 0);
  assert.equal(dayStreak([rec("1", "2026-11-21"), rec("1b", "2026-11-21")], NOW, TZ), 1);
});

test("statePath: four steps with the first date reached", () => {
  const p = statePath(words[2]);
  assert.deepEqual(p.map((s) => [s.state, s.reached, s.at]), [
    ["DISCOVERED", true, "2026-11-21T10:00:00.000Z"],
    ["ASSISTED", true, "2026-11-21T10:01:00.000Z"],
    ["REINFORCED", true, "2026-11-21T10:05:00.000Z"],
    ["USED_INDEPENDENTLY", false, null],
  ]);
  const twice = word("d", [["DISCOVERED", "2026-11-21T10:00:00.000Z"], ["ASSISTED", "2026-11-21T11:00:00.000Z"], ["ASSISTED", "2026-11-21T10:30:00.000Z"]]);
  assert.equal(statePath(twice)[1].at, "2026-11-21T10:30:00.000Z");
});

test("bars: the last 10 records, oldest on the left, newest marked", () => {
  const records = Array.from({ length: 12 }, (_, i) => rec(`r${i}`, `2026-11-${String(i + 1).padStart(2, "0")}`, i + 1));
  const v = buildAnalytics([], records.reverse(), {}, NOW, f);
  assert.equal(v.bars.length, 10);
  assert.equal(v.bars[0].record_id, "r2");
  assert.equal(v.bars[9].record_id, "r11");
  assert.equal(v.bars[9].newest, true);
  assert.equal(v.bars.filter((b) => b.newest).length, 1);
  assert.equal(v.bars[0].label, "3 Nov");
  assert.equal(v.bars[0].minutes, 3);
});

test("empty with no words and no records", () => {
  assert.equal(buildAnalytics([], [], {}, NOW, f).empty, true);
});
