import { test } from "node:test";
import assert from "node:assert/strict";
import { IDENTITY_KEY, forgetUser, initialsOf, readUser, writeUser } from "./identity.ts";
import { memoryStore, throwingStore } from "./storage.ts";
import type { User } from "../contracts.ts";

const luis: User = { user_id: "luis-felipe-3f9c1a", display_name: "Luís Felipe", comfortable_languages: ["pt-BR"], target_language: "en" };

test("write, read and forget", () => {
  const s = memoryStore();
  assert.equal(readUser(s), null);
  assert.equal(writeUser(luis, s), true);
  assert.deepEqual(readUser(s), luis);
  forgetUser(s);
  assert.equal(readUser(s), null);
  assert.equal(s.data.has(IDENTITY_KEY), false);
});

test("a corrupt value reads as no user", () => {
  const s = memoryStore();
  s.setItem(IDENTITY_KEY, "{not json");
  assert.equal(readUser(s), null);
  s.setItem(IDENTITY_KEY, JSON.stringify({ user_id: "x" }));
  assert.equal(readUser(s), null);
});

test("storage that throws or is missing never crashes", () => {
  assert.equal(readUser(throwingStore()), null);
  assert.equal(writeUser(luis, throwingStore()), false);
  assert.doesNotThrow(() => forgetUser(throwingStore()));
  assert.equal(readUser(null), null);
  assert.equal(writeUser(luis, null), false);
});

test("initials", () => {
  assert.equal(initialsOf("Luís Felipe"), "LF");
  assert.equal(initialsOf("ana"), "A");
  assert.equal(initialsOf("Maria da Silva"), "MS");
  assert.equal(initialsOf("   "), "?");
});
