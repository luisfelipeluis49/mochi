import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { contrastRatio, hexTokens } from "./contrast.ts";

const tokens = hexTokens(readFileSync(new URL("../styles/tokens.css", import.meta.url), "utf8"));
const c = (name: string) => {
  const v = tokens[name];
  assert.ok(v, `token --${name}`);
  return v;
};

test("the WCAG formula", () => {
  assert.equal(contrastRatio("#000000", "#FFFFFF"), 21);
  assert.equal(contrastRatio("#FFFFFF", "#FFFFFF"), 1);
  assert.equal(contrastRatio("#777777", "#FFFFFF").toFixed(2), "4.48");
});

// [text, background, the ratio section 4 states, the WCAG floor for this use]
const PAIRS: [string, string, number | null, number][] = [
  ["color-text", "color-bg", 16.3, 4.5],
  ["color-text", "color-surface", null, 4.5],
  ["color-text", "color-surface-2", null, 4.5],
  ["color-text-muted", "color-bg", 6.6, 4.5],
  ["color-text-muted", "color-surface-2", 6.1, 4.5],
  ["color-text-muted", "color-surface", null, 4.5],
  ["color-border", "color-bg", 3.4, 3],
  ["color-primary", "color-bg", 5.0, 4.5],
  ["color-on-primary", "color-primary", 5.3, 4.5],
  ["color-on-primary", "color-primary-strong", 7.6, 4.5],
  ["color-primary-strong", "color-primary-soft", 6.5, 4.5],
  ["color-text", "color-accent", 7.0, 4.5],
  ["color-accent-text", "color-bg", 5.2, 4.5],
  ["color-accent-text", "color-accent-soft", 4.8, 4.5],
  ["color-danger", "color-bg", 6.1, 4.5],
  ["color-danger", "color-surface", null, 4.5],
  ["color-danger", "color-surface-2", null, 4.5],
  ["color-accent-text", "color-surface", null, 4.5],
  ["color-accent-text", "color-surface-2", null, 4.5],
  ["color-primary-strong", "color-surface", null, 4.5],
  ["color-text-muted", "color-primary-soft", null, 4.5],
  ["color-focus", "color-bg", null, 3],
  ["color-text", "color-primary-soft", null, 4.5],
  ["color-text", "color-accent-soft", null, 4.5],
  ["color-primary", "color-surface", null, 4.5],
];

for (const [fg, bg, stated, floor] of PAIRS) {
  test(`${fg} on ${bg}`, () => {
    const r = contrastRatio(c(fg), c(bg));
    assert.ok(r >= floor, `${r.toFixed(2)} < ${floor}`);
    if (stated !== null) assert.ok(r >= stated - 0.05, `${r.toFixed(2)} below the stated ${stated}`);
  });
}

test("white text on orange is NOT allowed (the reason for the rule)", () => {
  assert.ok(contrastRatio(c("color-on-primary"), c("color-accent")) < 4.5);
});
