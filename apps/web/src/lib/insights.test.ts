// =============================================================================
// insights.test.ts  —  LANGUAGE: TypeScript (tests, run with `npm test`)
// -----------------------------------------------------------------------------
// Tests for insights.ts: totals, mistakes per 10 minutes, improvement, grouping of
// mistakes and unknown words, and what to practice next.
// Each test(...) block checks one rule. assert.equal(a, b) fails the test if a is not b.
// These run in Node.js without a browser or a backend.
// =============================================================================

import assert from "node:assert/strict";
import { test } from "node:test";
import type { ConversationReport } from "../contracts.ts";
import {
  conversations, improvementPercent, mistakesPer10Min, practiceNext, topMistakes, totals, trendBarPercent, wordsNeeded,
} from "./insights.ts";
import { initialState } from "./store.ts";

const report = (id: string, at: string, minutes: number, extra: Partial<ConversationReport> = {}): ConversationReport => ({
  report_id: id, user_id: "tasnim", target_language: "en", title: id, context: "meeting", started_at: at,
  speaking_minutes: minutes, mistakes: [], unknown_words: [], strengths: [], focus_next: [], ...extra,
});

const first = report("first", "2026-11-16T10:00:00.000Z", 20, {
  mistakes: [
    { kind: "grammar", topic: "Past tense", said: "Yesterday I send it", better: "Yesterday I sent it", count: 4 },
    { kind: "grammar", topic: "Prepositions", said: "good in Excel", better: "good at Excel", count: 2 },
  ],
  unknown_words: [{ expression: "postpone", meaning: "adiar", said_instead: "adiar", times: 2 }],
});
const second = report("second", "2026-11-20T10:00:00.000Z", 20, {
  mistakes: [{ kind: "grammar", topic: "Past tense", said: "I go there last week", better: "I went there last week", count: 2 }],
  unknown_words: [
    { expression: "Postpone", meaning: "adiar", said_instead: "make it later", times: 1 },
    { expression: "deadline", meaning: "prazo", said_instead: null, times: 1 },
  ],
  focus_next: ["Past tense: sent, went"],
});
const state = { ...initialState, reports: { second, first } };

test("conversations are oldest first; totals add up (words counted once)", () => {
  assert.deepEqual(conversations(state).map((r) => r.report_id), ["first", "second"]);
  assert.deepEqual(totals(conversations(state)), { conversations: 2, minutes: 40, unknownWords: 2, mistakes: 8 });
});

test("mistakes per 10 minutes, and the improvement between first and last", () => {
  assert.equal(mistakesPer10Min(first), 3);
  assert.equal(mistakesPer10Min(second), 1);
  assert.equal(improvementPercent(conversations(state)), -67);
  assert.equal(improvementPercent([first]), null);
  assert.equal(mistakesPer10Min(report("empty", "2026-11-20T10:00:00.000Z", 0)), 0);
});

test("mistakes grouped by topic, most frequent first, with the newest example", () => {
  const top = topMistakes(conversations(state));
  assert.deepEqual(top.map((t) => [t.topic, t.count, t.conversations]), [["Past tense", 6, 2], ["Prepositions", 2, 1]]);
  assert.equal(top[0].example.better, "I went there last week");
});

test("unknown words grouped (case ignored), most needed first", () => {
  const words = wordsNeeded(conversations(state));
  assert.deepEqual(words.map((w) => [w.expression, w.times]), [["postpone", 3], ["deadline", 1]]);
  assert.equal(words[0].saidInstead, "make it later");
});

test("practice next: the newest report's list, else the top mistake topics", () => {
  assert.deepEqual(practiceNext(conversations(state)), ["Past tense: sent, went"]);
  assert.deepEqual(practiceNext([first]), ["Past tense", "Prepositions"]);
  assert.deepEqual(practiceNext([]), []);
});

test("the worst conversation gets the full trend bar", () => {
  const list = conversations(state);
  assert.equal(trendBarPercent(mistakesPer10Min(first), list), 100);
  assert.equal(trendBarPercent(mistakesPer10Min(second), list), 33);
});
