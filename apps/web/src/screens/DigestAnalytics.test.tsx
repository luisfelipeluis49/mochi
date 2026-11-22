import { test } from "node:test";
import assert from "node:assert/strict";
import { renderToString } from "react-dom/server";
import { DigestScreen } from "./DigestScreen.tsx";
import { AnalyticsScreen } from "./AnalyticsScreen.tsx";
import { buildDigest } from "../lib/digest.ts";
import { buildAnalytics } from "../lib/analytics.ts";
import { seedFor } from "../mock/backend.ts";

const noop = () => {};
const NOW = Date.parse("2026-11-21T13:00:00.000Z");
const user = { user_id: "luis", display_name: "Luís", comfortable_languages: ["pt-BR" as const], target_language: "en" as const };
const seed = seedFor(user, NOW);
const f = { lang: "en" as const, timeZone: "UTC" };

test("Digest filled", () => {
  const html = renderToString(<DigestScreen lang="en" view={buildDigest(seed.records, seed.words, {}, NOW, f)} onSelect={noop} onGoTraining={noop} onGoSession={noop} />);
  assert.ok(html.includes("Digest"));
  assert.ok(html.includes("11 min · 3 hints"));
  assert.ok(html.includes("New words") && html.includes("corkscrew"));
  assert.ok(html.includes("Practise next") && html.includes("Practise these now"));
  assert.ok(html.includes("A few words came up."));
  assert.match(html, /<select id="digest-session"/);
});

test("Digest empty", () => {
  const html = renderToString(<DigestScreen lang="pt-BR" view={null} onSelect={noop} onGoTraining={noop} onGoSession={noop} />);
  assert.ok(html.includes("Nenhuma sessão ainda. Comece uma e o resumo aparece aqui."));
  assert.ok(html.includes("Começar uma sessão"));
});

test("Analytics filled: tiles, chart with a hidden table, legend, state paths", () => {
  const html = renderToString(<AnalyticsScreen lang="en" view={buildAnalytics(seed.words, seed.records, {}, NOW, f)} f={f} />);
  for (const s of ["Words saved", "Used with help", "Recalled in a game", "Used on your own", "Comes in a later version", "Sessions", "Total minutes", "Day streak", "Training accuracy", "On this device"]) assert.ok(html.includes(s), s);
  assert.ok(html.includes("17.5"), "total minutes");
  assert.match(html, /<svg[^>]*role="img"/);
  assert.match(html, /<table class="visually-hidden">/);
  assert.match(html, /bar bar-newest/);
  assert.ok(html.includes("Where your words are"));
  assert.match(html, /<ol class="state-path"/);
  assert.match(html, /class="step reached"/);
  assert.ok(html.includes("Hint shown"));
});

test("Analytics empty", () => {
  const html = renderToString(<AnalyticsScreen lang="pt-BR" view={buildAnalytics([], [], {}, NOW, { lang: "pt-BR" })} f={{ lang: "pt-BR" }} />);
  assert.ok(html.includes("Seu progresso aparece depois da primeira sessão."));
});
