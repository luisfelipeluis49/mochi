import { test } from "node:test";
import assert from "node:assert/strict";
import { appReducer, canStart, initialApp, micBlock, type AppAction, type AppState } from "./appState.ts";
import type { MochiEvent, SessionState, User } from "../contracts.ts";

const user: User = { user_id: "luis-felipe-3f9c1a", display_name: "Luís Felipe", comfortable_languages: ["pt-BR"], target_language: "en" };
let seq = 100;
function stateEvent(sessionId: string, capturing: boolean): MochiEvent {
  const payload: SessionState = { status: capturing ? "active" : "created", mode: "together", focus: "en", capturing, participants: capturing ? [user.user_id, "guest"] : [] };
  return { schema_version: "0.4", event_id: `evt_${seq}`, type: "session.state.changed", session_id: sessionId, emitted_at: "2026-11-21T10:00:00.000Z", sequence: seq++, payload };
}
const run = (s: AppState, ...as: AppAction[]) => as.reduce(appReducer, s);
const ready = () => run(initialApp({ lang: "en", user, sessionId: "w-00000000" }),
  { type: "gate", gate: { status: "ok" } }, { type: "probe", probe: { status: "ok" } }, { type: "identity_ok", user });

test("a stored user starts in identity checking; no user is none", () => {
  assert.equal(initialApp({ lang: "en", user, sessionId: "w-00000000" }).identity, "checking");
  assert.equal(initialApp({ lang: "en", user: null, sessionId: "w-00000000" }).identity, "none");
});

test("canStart needs the gate, the probe, a user and an idle phase", () => {
  const s = ready();
  assert.equal(canStart(s), true);
  assert.equal(canStart(run(s, { type: "gate", gate: { status: "skipped", problem: "denied" } })), false);
  assert.equal(micBlock(run(s, { type: "gate", gate: { status: "skipped", problem: "denied" } })), "denied");
  assert.equal(canStart(run(s, { type: "start_begin", sessionId: "w-11111111" })), false);
});

test("start: begin follows the new session id; ok captures", () => {
  let s = run(ready(), { type: "start_begin", sessionId: "w-11111111" });
  assert.equal(s.phase, "starting");
  assert.equal(s.live.sessionId, "w-11111111");
  // the idle snapshot of the new session during Start is not "ended elsewhere"
  s = run(s, { type: "live", action: { type: "event", event: stateEvent("w-11111111", false), now: 1 } });
  assert.equal(s.banner, null);
  s = run(s, { type: "live", action: { type: "event", event: stateEvent("w-11111111", true), now: 2 } }, { type: "start_ok", now: 5 });
  assert.equal(s.phase, "capturing");
  assert.equal(s.startedAt, 5);
});

test("capturing false without our Stop ends the session with a banner", () => {
  let s = run(ready(), { type: "start_begin", sessionId: "w-11111111" }, { type: "start_ok", now: 5 });
  s = run(s, { type: "live", action: { type: "event", event: stateEvent("w-11111111", false), now: 9 } });
  assert.equal(s.phase, "idle");
  assert.deepEqual(s.banner, { type: "http", kind: "session_ended" });
});

test("capturing false after our Stop is not an error", () => {
  let s = run(ready(), { type: "start_begin", sessionId: "w-11111111" }, { type: "start_ok", now: 5 }, { type: "stop_begin" });
  s = run(s, { type: "live", action: { type: "event", event: stateEvent("w-11111111", false), now: 9 } });
  assert.equal(s.banner, null);
  s = run(s, { type: "stop_done", now: 10, saved: { minutes: 12.5, hints: 3 } });
  assert.equal(s.phase, "idle");
  assert.deepEqual(s.saved, { minutes: 12.5, hints: 3 });
  assert.equal(s.stoppedAt, 10);
});

test("a reload that finds the session capturing asks to listen again", () => {
  let s = ready();
  s = run(s, { type: "live", action: { type: "event", event: stateEvent("w-00000000", true), now: 1 } });
  assert.equal(s.rejoin, true);
  assert.equal(canStart(s), false);
  const back = run(s, { type: "rejoin_ok", now: 3 });
  assert.equal(back.phase, "capturing");
  assert.equal(back.rejoin, false);
  const gone = run(s, { type: "live", action: { type: "event", event: stateEvent("w-00000000", false), now: 4 } });
  assert.equal(gone.rejoin, false);
});

test("a failed start goes back to idle with its banner", () => {
  const s = run(ready(), { type: "start_begin", sessionId: "w-11111111" }, { type: "start_failed", banner: { type: "http", kind: "session_full" } });
  assert.equal(s.phase, "idle");
  assert.deepEqual(s.banner, { type: "http", kind: "session_full" });
});

test("lost user forgets everything and notes profile_lost; forget has no note", () => {
  const lost = run(ready(), { type: "lost_user" });
  assert.equal(lost.user, null);
  assert.equal(lost.identity, "none");
  assert.equal(lost.note, "profile_lost");
  assert.equal(run(ready(), { type: "forget_user" }).note, null);
});

test("volume sets the pop time", () => {
  const s = run(ready(), { type: "volume", volume: 40, now: 77 });
  assert.equal(s.volume, 40);
  assert.equal(s.volumePopAt, 77);
});
