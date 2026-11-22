import { test } from "node:test";
import assert from "node:assert/strict";
import { SLEEPY_MS, faceOf, restingFace, speakingUntil, type FaceInput } from "./face.ts";
import type { Hint } from "../contracts.ts";

const NOW = 1_000_000;
const hint: Hint = {
  hint_id: "hint_015", target_user_id: "luis", target_language: "en", expression: "postpone", meaning: "adiar",
  example: "I need to postpone my meeting.", reason: "code_switch", expires_at: "2026-11-21T10:00:12.700Z",
};
const base = (over: Partial<FaceInput> = {}): FaceInput => ({ ...restingFace("en", "Luís"), ...over });
// capturing for a while, quiet: plain awake/neutral
const live = (over: Partial<FaceInput> = {}) => base({ capturing: true, startedAt: NOW - 60_000, ...over });

test("sleeping: no live session", () => {
  const f = faceOf(base(), NOW);
  assert.equal(f.mode, "sleeping");
  assert.equal(f.mood, "neutral");
});

test("waking: from the Start tap until the mic is published", () => {
  assert.equal(faceOf(base({ starting: true }), NOW).mode, "waking");
});

test("awake: capturing with a quiet mic", () => {
  const f = faceOf(live(), NOW);
  assert.equal(f.mode, "awake");
  assert.equal(f.who, "");
});

test("hearing + who: mic level within the last 500 ms", () => {
  const f = faceOf(live({ lastHearingAt: NOW - 200 }), NOW);
  assert.equal(f.mode, "hearing");
  assert.equal(f.who, "Luís …");
  assert.equal(faceOf(live({ lastHearingAt: NOW - 600, lastResponseAt: NOW - 550 }), NOW).mode, "awake");
});

test("thinking: up to 1.5 s after hearing ends, until a hint or a speak arrives", () => {
  assert.equal(faceOf(live({ lastHearingAt: NOW - 1000 }), NOW).mode, "thinking");
  assert.equal(faceOf(live({ lastHearingAt: NOW - 1999 }), NOW).mode, "thinking");
  assert.equal(faceOf(live({ lastHearingAt: NOW - 2000 }), NOW).mode, "awake");
  assert.equal(faceOf(live({ lastHearingAt: NOW - 1000, lastResponseAt: NOW - 100 }), NOW).mode, "awake");
});

test("speaking: until the remote voice is quiet for 700 ms, or the word-count fallback", () => {
  assert.equal(faceOf(live({ speakingUntil: NOW + 1 }), NOW).mode, "speaking");
  assert.equal(speakingUntil(NOW, "You can say: queue.", NOW + 3000), NOW + 3700);
  assert.equal(speakingUntil(NOW, "You can say: queue.", 0), NOW + 1200 + 4 * 350);
  assert.equal(speakingUntil(0, "x", 0), 0);
});

test("bye: 2 s after Stop, then sleeping", () => {
  assert.equal(faceOf(base({ stoppedAt: NOW - 1000 }), NOW).mode, "bye");
  assert.equal(faceOf(base({ stoppedAt: NOW - 2000 }), NOW).mode, "sleeping");
});

test("moods: happy after Start, curious with a hint, proud, excited, oops, sleepy", () => {
  assert.equal(faceOf(live({ startedAt: NOW - 1000 }), NOW).mood, "happy");
  assert.equal(faceOf(live({ startedAt: NOW - 4000 }), NOW).mood, "neutral");
  assert.equal(faceOf(live({ hint }), NOW).mood, "curious");
  assert.equal(faceOf(live({ proudAt: NOW - 100 }), NOW).mood, "proud");
  assert.equal(faceOf(live({ proudAt: NOW - 5000 }), NOW).mood, "neutral");
  assert.equal(faceOf(live({ excitedAt: NOW - 100 }), NOW).mood, "excited");
  assert.equal(faceOf(live({ problem: true }), NOW).mood, "oops");
  assert.equal(faceOf(base({ problem: true }), NOW).mood, "oops");
  assert.equal(faceOf(live({ startedAt: NOW - SLEEPY_MS }), NOW).mood, "sleepy");
  assert.equal(faceOf(live({ startedAt: NOW - SLEEPY_MS, lastHearingAt: NOW - 10_000 }), NOW).mood, "neutral");
});

test("mood priorities: oops > excited > proud > curious > happy", () => {
  const all = { startedAt: NOW - 100, hint, proudAt: NOW - 100, excitedAt: NOW - 100 };
  assert.equal(faceOf(live({ ...all, problem: true }), NOW).mood, "oops");
  assert.equal(faceOf(live(all), NOW).mood, "excited");
  assert.equal(faceOf(live({ ...all, excitedAt: 0 }), NOW).mood, "proud");
  assert.equal(faceOf(live({ ...all, excitedAt: 0, proudAt: 0 }), NOW).mood, "curious");
  assert.equal(faceOf(live({ startedAt: NOW - 100 }), NOW).mood, "happy");
});

test("the reload fallback: lastStateChange stands in for startedAt", () => {
  assert.equal(faceOf(live({ startedAt: 0, lastStateChange: NOW - 100 }), NOW).mood, "happy");
});

test("word and note from the hint, in the UI language", () => {
  const f = faceOf(live({ hint }), NOW);
  assert.equal(f.word, "postpone");
  assert.equal(f.note, "English · adiar");
  assert.equal(faceOf(live({ hint, lang: "pt-BR" }), NOW).note, "Inglês · adiar");
  assert.equal(faceOf(live({ hint: { ...hint, meaning: null } }), NOW).note, "English");
  assert.equal(faceOf(base({ hint }), NOW).word, "", "no hint while not capturing");
});

test("used badge for 5 s after a word reaches ASSISTED", () => {
  assert.deepEqual(faceOf(live({ used: { expression: "umbrella", at: NOW - 100 } }), NOW).badge, { kind: "used", word: "umbrella" });
  assert.equal(faceOf(live({ used: { expression: "umbrella", at: NOW - 5000 } }), NOW).badge, null);
});

test("volume pop for 2 s", () => {
  assert.deepEqual(faceOf(live({ volume: 40, volumePopAt: NOW - 500 }), NOW).pop, { kind: "volume", value: 40 });
  assert.equal(faceOf(live({ volume: 40, volumePopAt: NOW - 2000 }), NOW).pop, null);
});

test("offline", () => {
  assert.equal(faceOf(base({ online: false }), NOW).offline, true);
  assert.equal(faceOf(base(), NOW).offline, false);
});
