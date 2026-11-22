import { test } from "node:test";
import assert from "node:assert/strict";
import { PROBLEM_KINDS, WAKING_WINDOW_MS, problemCopyKeys, problemOfHttp } from "./httpProblem.ts";
import { copy } from "./i18n.ts";

test("offline when the browser says so and the call could not go out", () => {
  assert.equal(problemOfHttp("network", { op: "probe", online: false, probingForMs: 0 }), "offline");
  assert.equal(problemOfHttp("timeout", { op: "other", online: false }), "offline");
});

test("waking: 502/503/504, network error or timeout during the first 90 s of probing", () => {
  for (const f of [502, 503, 504, "network", "timeout"] as const) {
    assert.equal(problemOfHttp(f, { op: "probe", online: true, probingForMs: 0 }), "waking", String(f));
    assert.equal(problemOfHttp(f, { op: "probe", online: true, probingForMs: WAKING_WINDOW_MS - 1 }), "waking", String(f));
  }
});

test("unreachable: still failing after 90 s", () => {
  assert.equal(problemOfHttp("timeout", { op: "probe", online: true, probingForMs: WAKING_WINDOW_MS }), "unreachable");
  assert.equal(problemOfHttp(503, { op: "probe", probingForMs: 120_000 }), "unreachable");
  assert.equal(problemOfHttp("network", { op: "other", online: true }), "unreachable");
});

test("start 409 is session_full, start 502 is agora_start", () => {
  assert.equal(problemOfHttp(409, { op: "start" }), "session_full");
  assert.equal(problemOfHttp(502, { op: "start" }), "agora_start");
});

test("404 on the user is profile_lost (start too: unknown user)", () => {
  assert.equal(problemOfHttp(404, { op: "user" }), "profile_lost");
  assert.equal(problemOfHttp(404, { op: "start" }), "profile_lost");
});

test("the join block of a session that is not capturing means the session ended", () => {
  assert.equal(problemOfHttp(409, { op: "agora" }), "session_ended");
  assert.equal(problemOfHttp(404, { op: "agora" }), "session_ended");
});

test("anything else is a server problem", () => {
  assert.equal(problemOfHttp(500, { op: "other" }), "server");
  assert.equal(problemOfHttp(422, { op: "start" }), "server");
  assert.equal(problemOfHttp(404, { op: "other" }), "server");
});

test("every problem kind except profile_lost has a title and a body in both languages", () => {
  for (const kind of PROBLEM_KINDS) {
    const k = problemCopyKeys(kind);
    for (const lang of ["en", "pt-BR"] as const) {
      assert.ok(copy[lang][k.title].length > 0);
      assert.ok(copy[lang][k.body].length > 0);
    }
  }
});
