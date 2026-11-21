import assert from "node:assert/strict";
import { test } from "node:test";
import { tabFromPath, tabHref } from "./tabs.ts";

test("each phone page belongs to one tab", () => {
  assert.equal(tabFromPath("/m"), "analytics");
  assert.equal(tabFromPath("/me"), "conversations");
});

test("switching tabs keeps the person and the options", () => {
  assert.equal(tabHref("conversations", "?user=ana&mock=1&lang=pt-BR"), "/me?user=ana&mock=1&lang=pt-BR");
  assert.equal(tabHref("analytics", "?user=ana"), "/m?user=ana");
  assert.equal(tabHref("analytics", ""), "/m");
});
