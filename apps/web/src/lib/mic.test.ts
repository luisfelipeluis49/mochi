import { test } from "node:test";
import assert from "node:assert/strict";
import { MIC_PROBLEMS, SLOW_PROMPT_MS, micProblemOf, runMicGate, secureUrl, type MicEnv } from "./mic.ts";
import { fakeTimers, flush } from "./testkit.ts";
import { copy } from "./i18n.ts";

function env(over: Partial<MicEnv> & { gum?: () => Promise<{ getTracks(): { stop(): void }[] }> } = {}) {
  const calls = { gum: 0, prompt: 0, slow: 0 };
  const timers = fakeTimers();
  const e: MicEnv = {
    isSecureContext: true,
    mediaDevices: { getUserMedia: () => { calls.gum++; return over.gum ? over.gum() : Promise.resolve({ getTracks: () => [] }); } },
    permissions: null,
    timers,
    onPrompt: () => calls.prompt++,
    onSlow: () => calls.slow++,
    ...over,
  };
  return { e, calls, timers };
}

test("insecure: never calls getUserMedia", async () => {
  const { e, calls } = env({ isSecureContext: false });
  assert.deepEqual(await runMicGate(e), { ok: false, problem: "insecure" });
  assert.equal(calls.gum, 0);
});

test("no mediaDevices is unsupported", async () => {
  assert.deepEqual(await runMicGate(env({ mediaDevices: undefined }).e), { ok: false, problem: "unsupported" });
  assert.deepEqual(await runMicGate(env({ mediaDevices: {} }).e), { ok: false, problem: "unsupported" });
});

test("permission granted passes with no prompt", async () => {
  const { e, calls } = env({ permissions: { query: async () => ({ state: "granted" }) } });
  assert.deepEqual(await runMicGate(e), { ok: true });
  assert.equal(calls.gum, 0);
  assert.equal(calls.prompt, 0);
});

test("permission denied fails without getUserMedia", async () => {
  const { e, calls } = env({ permissions: { query: async () => ({ state: "denied" }) } });
  assert.deepEqual(await runMicGate(e), { ok: false, problem: "denied" });
  assert.equal(calls.gum, 0);
});

test("permission prompt asks getUserMedia and stops every track", async () => {
  let stopped = 0;
  const track = { stop: () => stopped++ };
  const { e, calls } = env({ permissions: { query: async () => ({ state: "prompt" }) }, gum: async () => ({ getTracks: () => [track, track] }) });
  assert.deepEqual(await runMicGate(e), { ok: true });
  assert.equal(calls.gum, 1);
  assert.equal(calls.prompt, 1);
  assert.equal(stopped, 2);
});

test("a query that throws falls through to getUserMedia", async () => {
  const { e, calls } = env({ permissions: { query: async () => { throw new TypeError("microphone is not a valid name"); } } });
  assert.deepEqual(await runMicGate(e), { ok: true });
  assert.equal(calls.gum, 1);
});

test("no answer after 8 s calls onSlow; the timer is cleared after", async () => {
  let answer!: (v: { getTracks(): { stop(): void }[] }) => void;
  const { e, calls, timers } = env({ gum: () => new Promise((r) => { answer = r; }) });
  const p = runMicGate(e);
  await flush();
  timers.tick(SLOW_PROMPT_MS - 1);
  assert.equal(calls.slow, 0);
  timers.tick(1);
  assert.equal(calls.slow, 1);
  answer({ getTracks: () => [] });
  assert.deepEqual(await p, { ok: true });
  assert.equal(timers.pending(), 0);
});

test("a getUserMedia error becomes its problem", async () => {
  const { e } = env({ gum: async () => { throw Object.assign(new Error("x"), { name: "NotAllowedError" }); } });
  assert.deepEqual(await runMicGate(e), { ok: false, problem: "denied" });
});

const named = (name: string) => Object.assign(new Error("x"), { name });
const coded = (code: string) => Object.assign(new Error("x"), { name: "AgoraRTCException", code });

test("micProblemOf: one row per problem", () => {
  assert.equal(micProblemOf(new TypeError("no mediaDevices")), "unsupported");
  for (const n of ["NotAllowedError", "PermissionDeniedError"]) assert.equal(micProblemOf(named(n)), "denied", n);
  assert.equal(micProblemOf(coded("PERMISSION_DENIED")), "denied");
  assert.equal(micProblemOf(named("SecurityError")), "policy");
  for (const n of ["NotFoundError", "DevicesNotFoundError", "OverconstrainedError"]) assert.equal(micProblemOf(named(n)), "no_device", n);
  assert.equal(micProblemOf(coded("DEVICE_NOT_FOUND")), "no_device");
  for (const n of ["NotReadableError", "TrackStartError", "AbortError"]) assert.equal(micProblemOf(named(n)), "busy", n);
  assert.equal(micProblemOf(coded("NOT_READABLE")), "busy");
  assert.equal(micProblemOf(named("SomethingElse")), "unknown");
  assert.equal(micProblemOf("boom"), "unknown");
  assert.equal(micProblemOf(null), "unknown");
});

test("an Agora error falls back to the DOM name in its message", () => {
  const e = Object.assign(new Error("NotAllowedError: Permission denied"), { name: "AgoraRTCException", code: "UNEXPECTED_ERROR" });
  assert.equal(micProblemOf(e), "denied");
});

test("every mic problem has copy in both languages", () => {
  for (const p of MIC_PROBLEMS) for (const lang of ["en", "pt-BR"] as const) {
    assert.ok(copy[lang][`mic_${p}_title`]);
    assert.ok(copy[lang][`mic_${p}_body`]);
  }
});

test("secureUrl swaps the scheme", () => {
  assert.equal(secureUrl("http://mochi.example/session?x=1"), "https://mochi.example/session?x=1");
});
