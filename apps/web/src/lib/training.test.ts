import { test } from "node:test";
import assert from "node:assert/strict";
import { INTERVALS, ProgressStore, WRONG_DELAY, accuracy, checkAnswer, dueCards, isTrainable, levenshtein, nextDue, progressKey, schedule, speechLang, type Progress } from "./training.ts";
import { memoryStore, throwingStore } from "./storage.ts";
import type { LearningEvent } from "../contracts.ts";

const NOW = Date.parse("2026-11-21T10:00:00.000Z");
const DAY = 86_400_000;
function word(id: string, at: string, over: Partial<LearningEvent> = {}): LearningEvent {
  return {
    learning_event_id: id, user_id: "luis", target_language: "en", expression: id, meaning: "m", detection_signal: "code_switch",
    hint_id: null, learning_state: "DISCOVERED", state_history: [{ learning_state: "DISCOVERED", at }], ...over,
  };
}

test("checkAnswer: exact, case, punctuation and spaces", () => {
  assert.equal(checkAnswer("umbrella", "umbrella", "en"), "correct");
  assert.equal(checkAnswer("umbrella", "  Umbrella! ", "en"), "correct");
  assert.equal(checkAnswer("put off", "put   off", "en"), "correct");
});

test("checkAnswer: one leading article is dropped (en and pt)", () => {
  assert.equal(checkAnswer("umbrella", "an umbrella", "en"), "correct");
  assert.equal(checkAnswer("to postpone", "postpone", "en"), "correct");
  assert.equal(checkAnswer("the receipt", "a receipt", "en"), "correct");
  assert.equal(checkAnswer("guarda-chuva", "o guarda-chuva", "pt-BR"), "correct");
  assert.equal(checkAnswer("fila", "uma fila", "pt-BR"), "correct");
  assert.equal(checkAnswer("recibo", "os recibo", "pt-BR"), "correct");
});

test("checkAnswer: accents only is almost", () => {
  assert.equal(checkAnswer("pão", "pao", "pt-BR"), "almost");
  assert.equal(checkAnswer("café", "cafe", "pt-BR"), "almost");
});

test("checkAnswer: typos by word length", () => {
  assert.equal(checkAnswer("queue", "queu", "en"), "almost");      // 5 letters, distance 1
  assert.equal(checkAnswer("tree", "tre", "en"), "wrong");         // 4 letters: exact only
  assert.equal(checkAnswer("umbrella", "umbrela", "en"), "almost");
  assert.equal(checkAnswer("umbrella", "unbrela", "en"), "wrong"); // 8 letters, distance 2
  assert.equal(checkAnswer("corkscrew", "corkscru", "en"), "almost"); // 9 letters, distance 2
  assert.equal(checkAnswer("corkscrew", "korkscru", "en"), "wrong"); // distance 3
});

test("checkAnswer: wrong and empty", () => {
  assert.equal(checkAnswer("umbrella", "raincoat", "en"), "wrong");
  assert.equal(checkAnswer("umbrella", "   ", "en"), "wrong");
});

test("levenshtein", () => {
  assert.equal(levenshtein("kitten", "sitting"), 3);
  assert.equal(levenshtein("", "abc"), 3);
});

test("schedule: a new card is box 1; correct climbs every box with its interval", () => {
  let e = schedule(undefined, "correct", NOW);
  assert.deepEqual(e, { box: 2, due_at: NOW + INTERVALS[2], correct: 1, wrong: 0, last_at: NOW });
  e = schedule(e, "almost", NOW);
  assert.equal(e.box, 3);
  assert.equal(e.due_at, NOW + 3 * DAY);
  e = schedule(e, "correct", NOW);
  assert.equal(e.box, 4);
  assert.equal(e.due_at, NOW + 7 * DAY);
  e = schedule(e, "correct", NOW);
  assert.equal(e.box, 5);
  assert.equal(e.due_at, NOW + 16 * DAY);
  e = schedule(e, "correct", NOW);
  assert.equal(e.box, 5, "box 5 is the top");
  assert.equal(e.correct, 5);
});

test("schedule: box 1 interval is 10 min; wrong goes back to box 1 in 10 min", () => {
  assert.equal(INTERVALS[1], 10 * 60_000);
  const e = schedule({ box: 4, due_at: 0, correct: 3, wrong: 0, last_at: 0 }, "wrong", NOW);
  assert.deepEqual(e, { box: 1, due_at: NOW + WRONG_DELAY, correct: 3, wrong: 1, last_at: NOW });
  assert.equal(schedule({ box: 1, due_at: 0, correct: 0, wrong: 1, last_at: 0 }, "correct", NOW).box, 2);
});

test("dueCards: due first (oldest due first), then never trained (newest first), with a limit", () => {
  const words = [
    word("a", "2026-11-20T10:00:00.000Z"), word("b", "2026-11-21T09:00:00.000Z"), word("c", "2026-11-19T10:00:00.000Z"),
    word("d", "2026-11-18T10:00:00.000Z"), word("e", "2026-11-17T10:00:00.000Z"),
  ];
  const progress: Progress = {
    d: { box: 2, due_at: NOW - 1000, correct: 1, wrong: 0, last_at: 0 },
    e: { box: 2, due_at: NOW - 5000, correct: 1, wrong: 0, last_at: 0 },
    c: { box: 3, due_at: NOW + DAY, correct: 2, wrong: 0, last_at: 0 },
  };
  assert.deepEqual(dueCards(words, progress, NOW).map((w) => w.learning_event_id), ["e", "d", "b", "a"]);
  assert.deepEqual(dueCards(words, progress, NOW, 3).map((w) => w.learning_event_id), ["e", "d", "b"]);
  assert.equal(nextDue(words, progress, NOW), NOW + DAY);
  assert.equal(nextDue(words, {}, NOW), null);
});

test("untrainable words are left out: no meaning, or someone else's", () => {
  assert.equal(isTrainable(word("a", "2026-11-20T10:00:00.000Z"), "luis"), true);
  assert.equal(isTrainable(word("a", "2026-11-20T10:00:00.000Z", { meaning: null }), "luis"), false);
  assert.equal(isTrainable(word("a", "2026-11-20T10:00:00.000Z", { meaning: "  " }), "luis"), false);
  assert.equal(isTrainable(word("a", "2026-11-20T10:00:00.000Z", { user_id: "guest" }), "luis"), false);
});

test("progress storage round-trips and survives a store that throws", () => {
  const s = memoryStore();
  const ps = new ProgressStore(s);
  assert.deepEqual(ps.read("luis"), {});
  const p: Progress = { a: { box: 2, due_at: 1, correct: 1, wrong: 0, last_at: 1 } };
  ps.write("luis", p);
  assert.deepEqual(new ProgressStore(s).read("luis"), p);
  assert.ok(s.data.has(progressKey("luis")));

  const broken = new ProgressStore(throwingStore());
  assert.deepEqual(broken.read("luis"), {});
  broken.write("luis", p);
  assert.deepEqual(broken.read("luis"), p, "kept in memory");

  s.setItem(progressKey("x"), "{bad");
  assert.deepEqual(new ProgressStore(s).read("x"), {});
});

test("accuracy and speech language", () => {
  assert.equal(accuracy({}), null);
  assert.equal(accuracy({ a: { box: 1, due_at: 0, correct: 7, wrong: 3, last_at: 0 } }), 0.7);
  assert.equal(speechLang("en"), "en-US");
  assert.equal(speechLang("pt-BR"), "pt-BR");
});
