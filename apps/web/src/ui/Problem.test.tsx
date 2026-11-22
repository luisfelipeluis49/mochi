import { test } from "node:test";
import assert from "node:assert/strict";
import { renderToString } from "react-dom/server";
import { Problem } from "./Problem.tsx";
import { MIC_PROBLEMS } from "../lib/mic.ts";
import { PROBLEM_KINDS, problemCopyKeys } from "../lib/httpProblem.ts";
import { copy } from "../lib/i18n.ts";

const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/'/g, "&#x27;").replace(/</g, "&lt;");

for (const lang of ["en", "pt-BR"] as const) {
  test(`every MicProblem renders its own title (${lang}), role=alert`, () => {
    for (const kind of MIC_PROBLEMS) {
      const html = renderToString(<Problem lang={lang} problem={{ type: "mic", kind }} onAction={() => {}} onContinue={() => {}} secureHref="https://x/" />);
      assert.match(html, /role="alert"/);
      assert.ok(html.includes(esc(copy[lang][`mic_${kind}_title`])), `${kind} title`);
      assert.ok(html.includes(esc(copy[lang][`mic_${kind}_body`])), `${kind} body`);
      assert.ok(html.includes(esc(copy[lang].mic_continue_without)));
    }
  });
  test(`every ProblemKind renders its own title (${lang})`, () => {
    for (const kind of PROBLEM_KINDS) {
      const html = renderToString(<Problem lang={lang} problem={{ type: "http", kind }} onAction={() => {}} />);
      assert.match(html, /role="alert"/);
      assert.ok(html.includes(esc(copy[lang][problemCopyKeys(kind).title])), kind);
    }
  });
}

test("insecure offers the https link", () => {
  const html = renderToString(<Problem lang="en" problem={{ type: "mic", kind: "insecure" }} secureHref="https://mochi.example/session" onAction={() => {}} />);
  assert.match(html, /href="https:\/\/mochi.example\/session"/);
  assert.ok(html.includes("Open the secure page"));
});
