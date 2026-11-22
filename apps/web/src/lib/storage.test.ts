import { test } from "node:test";
import assert from "node:assert/strict";
import { memoryStore, safeGet, safeRemove, safeSet, throwingStore } from "./storage.ts";

test("safe access works and never throws", () => {
  const s = memoryStore();
  assert.equal(safeSet(s, "k", "v"), true);
  assert.equal(safeGet(s, "k"), "v");
  safeRemove(s, "k");
  assert.equal(safeGet(s, "k"), null);
  assert.equal(safeSet(throwingStore(), "k", "v"), false);
  assert.equal(safeGet(throwingStore(), "k"), null);
  assert.doesNotThrow(() => safeRemove(throwingStore(), "k"));
  assert.equal(safeSet(null, "k", "v"), false);
});
