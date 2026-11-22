import { test } from "node:test";
import assert from "node:assert/strict";
import { DEFAULT_MODE, MODE_KEY, readMode, writeMode } from "./mode.ts";
import type { KV } from "./storage.ts";

function memory(initial: Record<string, string> = {}): KV {
  const m = new Map(Object.entries(initial));
  return { getItem: (k) => m.get(k) ?? null, setItem: (k, v) => void m.set(k, v), removeItem: (k) => void m.delete(k) };
}

test("a new device listens quietly", () => {
  assert.equal(DEFAULT_MODE, "listen");
  assert.equal(readMode(memory()), "listen");
  assert.equal(readMode(null), "listen");
});

test("the choice is remembered; anything else falls back to listening", () => {
  const s = memory();
  assert.equal(writeMode("talk", s), true);
  assert.equal(readMode(s), "talk");
  assert.equal(readMode(memory({ [MODE_KEY]: "shout" })), "listen");
});
