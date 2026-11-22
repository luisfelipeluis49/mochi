import assert from "node:assert/strict";
import { test } from "node:test";
import { tabFromPath, tabHref } from "./tabs.ts";

test("each phone address belongs to one tab", () => {
  assert.equal(tabFromPath("/m"), "session");
  assert.equal(tabFromPath("/m/analytics"), "analytics");
  assert.equal(tabFromPath("/me"), "analytics"); // old "My conversations" links open Analytics
});

test("switching tabs keeps the person and the options", () => {
  assert.equal(tabHref("analytics", "?user=ana&mock=1&lang=pt-BR"), "/m/analytics?user=ana&mock=1&lang=pt-BR");
  assert.equal(tabHref("session", "?user=ana"), "/m?user=ana");
  assert.equal(tabHref("session", ""), "/m");
});
