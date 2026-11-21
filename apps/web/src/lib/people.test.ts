// =============================================================================
// people.test.ts  —  LANGUAGE: TypeScript (tests, run with `npm test`)
// -----------------------------------------------------------------------------
// Tests for people.ts: a phone remembers its owner; reading ?people=a,b for the demo.
// =============================================================================

import assert from "node:assert/strict";
import { test } from "node:test";
import { type SimpleStorage, peopleFromUrl, rememberUser, rememberedUser } from "./people.ts";

function fakeStorage(): SimpleStorage {
  const data = new Map<string, string>();
  return { getItem: (k) => data.get(k) ?? null, setItem: (k, v) => void data.set(k, v) };
}

test("a phone remembers its owner", () => {
  const phone = fakeStorage();
  assert.equal(rememberedUser(phone), null);
  rememberUser("Tasnim", phone);
  assert.equal(rememberedUser(phone), "tasnim");
});

test("each phone keeps its own owner", () => {
  const tasnimPhone = fakeStorage();
  const matheusPhone = fakeStorage();
  rememberUser("tasnim", tasnimPhone);
  rememberUser("matheus", matheusPhone);
  assert.equal(rememberedUser(tasnimPhone), "tasnim");
  assert.equal(rememberedUser(matheusPhone), "matheus");
});

test("blocked or missing storage never breaks the page", () => {
  const broken: SimpleStorage = { getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("blocked"); } };
  assert.doesNotThrow(() => rememberUser("tasnim", broken));
  assert.equal(rememberedUser(broken), null);
  assert.equal(rememberedUser(null), null);
});

test("?people= needs exactly two names", () => {
  assert.deepEqual(peopleFromUrl("?people=Tasnim, Matheus&mock=1"), ["tasnim", "matheus"]);
  assert.equal(peopleFromUrl("?people=tasnim"), null);
  assert.equal(peopleFromUrl("?mock=1"), null);
});
