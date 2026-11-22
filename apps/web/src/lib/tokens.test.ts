// No color values outside styles/tokens.css: every other file uses the tokens.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { join, relative } from "node:path";

const src = fileURLToPath(new URL("..", import.meta.url));

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((n) => {
    const p = join(dir, n);
    return statSync(p).isDirectory() ? files(p) : [p];
  });
}

test("no hex colors outside tokens.css", () => {
  const offenders: string[] = [];
  for (const f of files(src)) {
    const rel = relative(src, f);
    if (rel === join("styles", "tokens.css") || rel.endsWith(".test.ts") || rel.endsWith(".test.tsx")) continue;
    if (!/\.(tsx?|css)$/.test(f)) continue;
    const text = readFileSync(f, "utf8");
    for (const m of text.matchAll(/#[0-9a-fA-F]{3,8}\b/g)) {
      const line = text.slice(0, m.index).split("\n").length;
      offenders.push(`${rel}:${line} ${m[0]}`);
    }
  }
  assert.deepEqual(offenders, []);
});
