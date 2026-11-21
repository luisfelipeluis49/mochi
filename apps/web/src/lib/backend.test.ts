import assert from "node:assert/strict";
import { test } from "node:test";
import { shouldRetry } from "./backend.ts";

test("close code 4400 stops reconnecting; other codes retry", () => {
  assert.equal(shouldRetry(4400), false);
  assert.equal(shouldRetry(1006), true);
  assert.equal(shouldRetry(1000), true);
});
