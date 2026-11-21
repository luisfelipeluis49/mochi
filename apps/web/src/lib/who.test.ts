import assert from "node:assert/strict";
import { test } from "node:test";
import { SECOND_USER, indexLinks, whoFromUrl, wsQuery } from "./who.ts";

test("whoFromUrl reads the three kinds of page", () => {
  assert.deepEqual(whoFromUrl("/m", "?user=ana"), { kind: "user", user: "ana" });
  assert.equal(whoFromUrl("/m", ""), null);
  assert.deepEqual(whoFromUrl("/home", "?device=home_pi_01"), { kind: "device", device: "home_pi_01" });
  assert.deepEqual(whoFromUrl("/home", ""), { kind: "device", device: "home_pi_01" });
  assert.deepEqual(whoFromUrl("/audience", ""), { kind: "audience" });
  assert.equal(whoFromUrl("/", ""), null);
});

test("wsQuery builds the WebSocket query (and encodes it)", () => {
  assert.equal(wsQuery({ kind: "user", user: "ana" }), "user=ana");
  assert.equal(wsQuery({ kind: "user", user: "a b&c" }), "user=a%20b%26c");
  assert.equal(wsQuery({ kind: "device", device: "home_pi_01" }), "device=home_pi_01");
  assert.equal(wsQuery({ kind: "audience" }), "view=audience");
});

test("Index links include ana, ben and the one-constant second person", () => {
  const hrefs = indexLinks().map((l) => l.href);
  assert.ok(hrefs.includes("/m?user=ana"));
  assert.ok(hrefs.includes("/m?user=ben"));
  assert.ok(hrefs.includes(`/m?user=${SECOND_USER}`));
});
