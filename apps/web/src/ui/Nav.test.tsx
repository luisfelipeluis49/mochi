import { test } from "node:test";
import assert from "node:assert/strict";
import { renderToString } from "react-dom/server";
import { Nav } from "./Nav.tsx";

const user = { user_id: "ana", display_name: "Ana Souza", comfortable_languages: ["pt-BR" as const], target_language: "en" as const };

test("four items, in order, with aria-current on the active one", () => {
  const html = renderToString(<Nav lang="en" screen="digest" user={user} onNavigate={() => {}} />);
  const items = [...html.matchAll(/class="nav-item"[^>]*>/g)].map((m) => m[0]);
  assert.equal(items.length, 4);
  assert.deepEqual([...html.matchAll(/href="(\/[a-z]+)" class="nav-item"/g)].map((m) => m[1]), ["/session", "/training", "/digest", "/analytics"]);
  assert.equal((html.match(/aria-current="page"/g) ?? []).length, 1);
  assert.match(html, /href="\/digest" class="nav-item" aria-current="page"/);
  assert.match(html, /<nav[^>]*aria-label="Main navigation"/);
  assert.ok(html.includes(">AS<"), "avatar initials");
});

test("Portuguese labels", () => {
  const html = renderToString(<Nav lang="pt-BR" screen="session" user={user} onNavigate={() => {}} />);
  for (const l of ["Sessão", "Treino", "Resumo", "Análises"]) assert.ok(html.includes(l), l);
});
