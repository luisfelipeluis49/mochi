import { test } from "node:test";
import assert from "node:assert/strict";
import { renderToString } from "react-dom/server";
import { App } from "./App.tsx";
import { mockModel, noopActions } from "./mock/model.ts";
import { SCREENS } from "./lib/routes.ts";
import { appReducer } from "./lib/appState.ts";

test("App renders the session with ?mock=1 data: landmarks, nav, a live hint", () => {
  const html = renderToString(<App model={mockModel({ lang: "pt-BR" })} actions={noopActions} />);
  assert.match(html, /<nav /);
  assert.match(html, /<header /);
  assert.match(html, /<main /);
  assert.match(html, /aria-current="page"/);
  assert.match(html, /class="hint-word" lang="en">postpone/);
  assert.ok(html.includes("Encerrar sessão"));
  assert.ok(html.includes("Ouvindo"));
});

test("App renders every screen", () => {
  for (const screen of SCREENS) {
    const html = renderToString(<App model={mockModel({ screen, capturing: false })} actions={noopActions} />);
    assert.match(html, /<main /, screen);
  }
  assert.ok(renderToString(<App model={mockModel({ screen: "analytics", capturing: false })} actions={noopActions} />).includes("Words saved"));
  assert.ok(renderToString(<App model={mockModel({ screen: "digest", capturing: false })} actions={noopActions} />).includes("Practise next"));
  assert.ok(renderToString(<App model={mockModel({ screen: "training", capturing: false })} actions={noopActions} />).includes("1 / "));
});

test("App flow: gate, probe, onboarding, identity", () => {
  const m = mockModel({ capturing: false });
  const withGate = (gate: Parameters<typeof appReducer>[1]) => ({ ...m, state: appReducer(m.state, gate) });
  assert.ok(renderToString(<App model={withGate({ type: "gate", gate: { status: "prompt" } })} actions={noopActions} />).includes("Allow the microphone"));
  assert.ok(renderToString(<App model={withGate({ type: "gate", gate: { status: "failed", problem: "denied" } })} actions={noopActions} href="http://x/" />).includes("Microphone access is blocked"));
  assert.ok(renderToString(<App model={withGate({ type: "probe", probe: { status: "pending", problem: "waking" } })} actions={noopActions} />).includes("Connecting to Mochi…"));
  assert.ok(renderToString(<App model={withGate({ type: "lost_user" })} actions={noopActions} />).includes("Tell it your name again."));
  const skipped = renderToString(<App model={withGate({ type: "gate", gate: { status: "skipped", problem: "no_device" } })} actions={noopActions} />);
  assert.ok(skipped.includes("Start needs the microphone: No microphone found"));
});

test("a lost socket shows a non-blocking banner, never the full screen", () => {
  const m = mockModel({ capturing: false });
  const html = renderToString(<App model={{ ...m, state: appReducer(m.state, { type: "socket", status: "retrying" }) }} actions={noopActions} />);
  assert.ok(html.includes("Can&#x27;t reach Mochi"));
  assert.match(html, /<nav /);
  assert.match(html, /No connection/);
});
