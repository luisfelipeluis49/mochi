import { test } from "node:test";
import assert from "node:assert/strict";
import { ApiError, PROBE_TIMEOUT_MS, beaconStop, createApi } from "./api.ts";
import { fakeFetch, fakeTimers, flush } from "./testkit.ts";
import type { LearningEvent, SessionRecord, SessionState, User } from "../contracts.ts";

const user: User = { user_id: "luis-felipe-3f9c1a", display_name: "Luís Felipe", comfortable_languages: ["pt-BR"], target_language: "en" };
const state: SessionState = { status: "active", mode: "together", focus: "en", capturing: true, participants: [user.user_id, "guest"] };
const word: LearningEvent = {
  learning_event_id: "learn_002", user_id: user.user_id, target_language: "en", expression: "umbrella", meaning: "guarda-chuva",
  detection_signal: "code_switch", hint_id: "hint_016", learning_state: "DISCOVERED",
  state_history: [{ learning_state: "DISCOVERED", at: "2026-11-21T10:01:00.000Z" }],
};
const record: SessionRecord = {
  record_id: "rec_1", session_id: "w-3f9c1a2b", user_id: user.user_id, started_at: "2026-11-21T10:00:00.000Z",
  ended_at: "2026-11-21T10:12:30.000Z", minutes: 12.5, hint_count: 3, learning_event_ids: ["learn_002"],
};

test("createUser posts the body to /api/users and returns the User (201)", async () => {
  const f = fakeFetch(() => ({ status: 201, json: user }));
  const api = createApi({ fetch: f.fn });
  const got = await api.createUser({ display_name: "Luís Felipe", comfortable_language: "pt-BR", target_language: "en" });
  assert.deepEqual(got, user);
  assert.equal(f.calls[0].method, "POST");
  assert.equal(f.calls[0].url, "/api/users");
  assert.deepEqual(f.calls[0].body, { display_name: "Luís Felipe", comfortable_language: "pt-BR", target_language: "en" });
  assert.equal(f.calls[0].headers["Content-Type"], "application/json");
});

test("GET user, words and sessions use the user path", async () => {
  const f = fakeFetch((c) => ({ status: 200, json: c.url.endsWith("/words") ? [word] : c.url.endsWith("/sessions") ? [record] : user }));
  const api = createApi({ fetch: f.fn });
  assert.deepEqual(await api.getUser(user.user_id), user);
  assert.deepEqual(await api.words(user.user_id), [word]);
  assert.deepEqual(await api.sessions(user.user_id), [record]);
  assert.deepEqual(f.calls.map((c) => `${c.method} ${c.url}`), [
    `GET /api/users/${user.user_id}`, `GET /api/users/${user.user_id}/words`, `GET /api/users/${user.user_id}/sessions`,
  ]);
});

test("start sends user_id and woken_by per UI language", async () => {
  const f = fakeFetch(() => ({ status: 200, json: state }));
  const api = createApi({ fetch: f.fn });
  assert.deepEqual(await api.start("w-3f9c1a2b", user.user_id, "pt-BR"), state);
  await api.start("w-3f9c1a2b", user.user_id, "en");
  assert.equal(f.calls[0].url, "/api/sessions/w-3f9c1a2b/start");
  assert.equal(f.calls[0].method, "POST");
  assert.deepEqual(f.calls[0].body, { user_id: user.user_id, woken_by: "oi mochi" });
  assert.deepEqual(f.calls[1].body, { user_id: user.user_id, woken_by: "hey mochi" });
});

test("stop and agora", async () => {
  const join = { app_id: "app", channel: "mochi-demo-w-3f9c1a2b", uid: 4242, token: "tok" };
  const f = fakeFetch((c) => ({ status: 200, json: c.url.endsWith("/agora") ? join : { ...state, capturing: false, status: "ended" } }));
  const api = createApi({ fetch: f.fn });
  const s = await api.stop("w-3f9c1a2b");
  assert.equal(s?.capturing, false);
  assert.deepEqual(await api.agora("w-3f9c1a2b"), join);
  assert.equal(f.calls[0].method, "POST");
  assert.equal(f.calls[0].url, "/api/sessions/w-3f9c1a2b/stop");
  assert.equal(f.calls[0].body, undefined);
  assert.equal(f.calls[1].method, "GET");
  assert.equal(f.calls[1].url, "/api/sessions/w-3f9c1a2b/agora");
});

async function failure(status: number, op: "start" | "user" | "create" | "agora") {
  const f = fakeFetch(() => ({ status, json: { detail: "nope" } }));
  const api = createApi({ fetch: f.fn, online: () => true });
  const run = op === "start" ? api.start("w-00000000", "x", "en") : op === "user" ? api.getUser("x")
    : op === "agora" ? api.agora("w-00000000") : api.createUser({ display_name: "", comfortable_language: "en", target_language: "pt-BR" });
  try {
    await run;
  } catch (e) {
    assert.ok(e instanceof ApiError);
    return e;
  }
  throw new Error("did not throw");
}

test("status codes map to ApiError kinds", async () => {
  assert.equal((await failure(404, "user")).kind, "profile_lost");
  assert.equal((await failure(409, "start")).kind, "session_full");
  assert.equal((await failure(502, "start")).kind, "agora_start");
  assert.equal((await failure(404, "start")).kind, "profile_lost");
  const v = await failure(422, "create");
  assert.equal(v.status, 422);
  assert.equal(v.kind, "server");
  assert.equal((await failure(409, "agora")).kind, "session_ended");
  assert.equal((await failure(503, "user")).kind, "unreachable");
});

test("a network error is an ApiError, offline when the browser is offline", async () => {
  const f = fakeFetch(() => "throw");
  const off = createApi({ fetch: f.fn, online: () => false });
  await assert.rejects(off.getUser("x"), (e: unknown) => e instanceof ApiError && e.status === "network" && e.kind === "offline");
  const on = createApi({ fetch: f.fn, online: () => true });
  await assert.rejects(on.getUser("x"), (e: unknown) => e instanceof ApiError && e.kind === "unreachable");
});

test("a wrong shape is a server problem", async () => {
  const f = fakeFetch(() => ({ status: 200, json: { user_id: 1 } }));
  await assert.rejects(createApi({ fetch: f.fn }).getUser("x"), (e: unknown) => e instanceof ApiError && e.kind === "server");
});

test("the /healthz probe aborts after 10 s", async () => {
  const timers = fakeTimers();
  const f = fakeFetch(() => "hang");
  const api = createApi({ fetch: f.fn, timers, online: () => true });
  let err: unknown = null;
  const p = api.health().catch((e) => { err = e; });
  await flush();
  assert.equal(f.calls[0].url, "/healthz");
  timers.tick(PROBE_TIMEOUT_MS - 1);
  await flush();
  assert.equal(err, null);
  timers.tick(1);
  await p;
  assert.ok((err as unknown) instanceof ApiError);
  assert.equal((err as unknown as ApiError).status, "timeout");
  assert.equal(timers.pending(), 0);
});

test("the probe clears its timer when it answers", async () => {
  const timers = fakeTimers();
  const f = fakeFetch(() => ({ status: 200, json: { status: "ok", version: "dev" } }));
  const api = createApi({ fetch: f.fn, timers });
  assert.deepEqual(await api.health(), { status: "ok", version: "dev" });
  assert.equal(timers.pending(), 0);
});

test("beaconStop posts an empty body to the stop path", () => {
  const sent: unknown[][] = [];
  assert.equal(beaconStop("w-3f9c1a2b", { sendBeacon: (...a) => { sent.push(a); return true; } }), true);
  assert.deepEqual(sent, [["/api/sessions/w-3f9c1a2b/stop"]]);
  assert.equal(beaconStop("w-3f9c1a2b", {}), false);
  assert.equal(beaconStop("w-3f9c1a2b", undefined), false);
});

test("one word the client does not understand does not hide the others", async () => {
  const bad = { ...word, learning_event_id: "bad", learning_state: "FROM_A_NEWER_BACKEND" };
  const f = fakeFetch(() => ({ status: 200, json: [bad, word] }));
  const api = createApi({ fetch: f.fn });
  assert.deepEqual(await api.words(user.user_id), [word]);
});
