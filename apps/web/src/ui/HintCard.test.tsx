import { test } from "node:test";
import assert from "node:assert/strict";
import { renderToString } from "react-dom/server";
import { HintCard } from "./HintCard.tsx";
import type { Hint } from "../contracts.ts";

const hint: Hint = { hint_id: "h", target_user_id: null, target_language: "en", expression: "postpone", meaning: "adiar", example: "I need to postpone my meeting.", reason: "code_switch", expires_at: "2026-11-21T10:00:08.000Z" };

test("a hint with no target is For everyone", () => {
  const html = renderToString(<HintCard lang="en" hint={hint} note="English · adiar" remaining={0.5} used={null} />);
  assert.ok(html.includes("For everyone"));
  assert.ok(html.includes('lang="en"'));
  assert.match(html, /aria-live="polite"/);
  assert.ok(html.includes("<i>I need to postpone my meeting.</i>"));
  assert.ok(html.includes("scaleX(0.500)"));
});

test("a targeted hint does not say For everyone; pt-BR copy", () => {
  const html = renderToString(<HintCard lang="pt-BR" hint={{ ...hint, target_user_id: "ana" }} note="Inglês · adiar" remaining={1} used={null} />);
  assert.ok(!html.includes("Para todos"));
  assert.ok(html.includes("Inglês · adiar"));
});

test("the used badge", () => {
  const html = renderToString(<HintCard lang="en" hint={null} note="" remaining={0} used={{ word: "umbrella" }} />);
  assert.ok(html.includes("Word used"));
  assert.ok(html.includes("umbrella"));
});
