import { test } from "node:test";
import assert from "node:assert/strict";
import { SESSION_ID_RE, SESSION_KEY, forgetSession, newSessionId, rememberSession, rememberedSession } from "./sessionId.ts";
import { memoryStore, throwingStore } from "./storage.ts";

test("the format is w- and 8 lowercase hex", () => {
  for (let i = 0; i < 200; i++) assert.match(newSessionId(), SESSION_ID_RE);
  assert.equal(newSessionId(() => 0), "w-00000000");
  assert.equal(newSessionId(() => 0.999999), "w-ffffffff");
});

test("the reload slot keeps one id", () => {
  const s = memoryStore();
  assert.equal(rememberedSession(s), null);
  rememberSession("w-3f9c1a2b", s);
  assert.equal(rememberedSession(s), "w-3f9c1a2b");
  forgetSession(s);
  assert.equal(rememberedSession(s), null);
});

test("a malformed slot is ignored and blocked storage is safe", () => {
  const s = memoryStore();
  s.setItem(SESSION_KEY, "demo");
  assert.equal(rememberedSession(s), null);
  assert.equal(rememberedSession(throwingStore()), null);
  assert.doesNotThrow(() => rememberSession("w-00000000", throwingStore()));
});
