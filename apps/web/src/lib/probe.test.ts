import { test } from "node:test";
import assert from "node:assert/strict";
import { probeBackoffMs, startProbe, type ProbeState } from "./probe.ts";
import { ApiError } from "./api.ts";
import { fakeTimers, flush } from "./testkit.ts";

test("the probe backoff is 2, 4, 8, then 15 s", () => {
  assert.deepEqual([0, 1, 2, 3, 4].map(probeBackoffMs), [2000, 4000, 8000, 15000, 15000]);
});

test("waking while pending and for 90 s, then unreachable; ok when /healthz answers", async () => {
  const timers = fakeTimers();
  const states: ProbeState[] = [];
  let ok = false;
  const api = { health: async () => { if (ok) return { status: "ok" }; throw new ApiError(502, "unreachable", "x"); } };
  startProbe(api, { timers, now: timers.now, online: () => true, onState: (s) => states.push(s) });
  assert.deepEqual(states[0], { status: "pending", problem: "waking" });
  await flush();
  assert.deepEqual(states[1], { status: "failing", problem: "waking", retryInMs: 2000 });
  const waits = [2000, 4000, 8000, 15000, 15000, 15000, 15000, 15000, 15000];
  for (const w of waits) {
    timers.tick(w);
    await flush();
  }
  const at89 = states[states.length - 3]; // the failure at 89 s
  assert.equal((at89 as { problem: string }).problem, "waking");
  const last = states[states.length - 1];
  assert.equal(last.status, "failing");
  assert.equal((last as { problem: string }).problem, "unreachable"); // the failure at 104 s
  ok = true;
  timers.tick(15000);
  await flush();
  assert.deepEqual(states[states.length - 1], { status: "ok" });
  assert.equal(timers.pending(), 0);
});

test("offline when the browser is offline", async () => {
  const timers = fakeTimers();
  const states: ProbeState[] = [];
  startProbe({ health: async () => { throw new ApiError("network", "offline", "x"); } }, { timers, now: timers.now, online: () => false, onState: (s) => states.push(s) });
  await flush();
  assert.equal((states[1] as { problem: string }).problem, "offline");
});

test("retryNow tries at once and stop ends it", async () => {
  const timers = fakeTimers();
  let calls = 0;
  const p = startProbe({ health: async () => { calls++; throw new ApiError("timeout", "unreachable", "x"); } }, { timers, now: timers.now, online: () => true, onState: () => {} });
  await flush();
  assert.equal(calls, 1);
  p.retryNow();
  await flush();
  assert.equal(calls, 2);
  p.stop();
  timers.tick(60_000);
  await flush();
  assert.equal(calls, 2);
});
