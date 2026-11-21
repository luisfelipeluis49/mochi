import assert from "node:assert/strict";
import { test } from "node:test";
import { joinFrom } from "./backend.ts";
import { AGORA_SDK_URL, markStartedHere, showLive, startedHere } from "./phoneMic.ts";

/** A tiny in-memory sessionStorage. */
function fakeStore() {
  const m = new Map<string, string>();
  return { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v), removeItem: (k: string) => void m.delete(k) };
}

test("a phone remembers it started the session, and forgets on Stop", () => {
  const s = fakeStore();
  assert.equal(startedHere(s), false);
  markStartedHere(true, s);
  assert.equal(startedHere(s), true);
  markStartedHere(false, s);
  assert.equal(startedHere(s), false);
});

test("no storage (private mode) behaves as 'not started here'", () => {
  assert.equal(startedHere(null), false);
  markStartedHere(true, null); // does not throw
});

test("live things hide only while a session started on the Pi runs", () => {
  assert.equal(showLive(true, true), true);   // phone session: hints here
  assert.equal(showLive(true, false), false); // Pi session: nothing live on the phone
  assert.equal(showLive(false, false), true); // after the session: analytics
});

test("the phone takes the device state's join block; none when no session runs", () => {
  const agora = { app_id: "a", channel: "mochi_demo", uid: 1001, token: "t" };
  assert.deepEqual(joinFrom({ agora }), agora);
  assert.equal(joinFrom({ agora: null }), null);
  assert.equal(joinFrom({}), null);
});

test("the Agora SDK is a pinned https URL", () => {
  assert.match(AGORA_SDK_URL, /^https:\/\/download\.agora\.io\/.+AgoraRTC_N-\d+\.\d+\.\d+\.js$/);
});
