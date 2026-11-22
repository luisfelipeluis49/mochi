import { test } from "node:test";
import assert from "node:assert/strict";
import { renderToString } from "react-dom/server";
import { Face } from "./Face.tsx";
import { FACE_MODES, faceOf, restingFace } from "../lib/face.ts";

const view = (mode: (typeof FACE_MODES)[number], over = {}) =>
  ({ mode, mood: "neutral" as const, word: "", note: "", who: "", badge: null, pop: null, offline: false, ...over });

test("the mode class, the state text and the aria-label", () => {
  const v = faceOf({ ...restingFace("en", "Ana"), capturing: true, startedAt: 1, lastHearingAt: 999 }, 1000);
  const html = renderToString(<Face lang="en" view={v} />);
  assert.match(html, /class="presence mode-hearing"/);
  assert.match(html, /role="img"/);
  assert.match(html, /aria-label="Hearing Ana"/);
  assert.ok(html.includes("monogram"));
});

test("each mode has a plain label in both languages and no cartoon parts", () => {
  const en: string[] = [];
  const pt: string[] = [];
  for (const mode of FACE_MODES) {
    const e = renderToString(<Face lang="en" view={view(mode)} />);
    const p = renderToString(<Face lang="pt-BR" view={view(mode)} />);
    assert.match(e, new RegExp(`mode-${mode}`));
    assert.ok(!/eyes|mouth|blush/.test(e));
    en.push(/aria-label="([^"]+)"/.exec(e)![1]);
    pt.push(/aria-label="([^"]+)"/.exec(p)![1]);
  }
  assert.deepEqual(en, ["Ready", "Connecting", "Listening", "Hearing …", "Processing", "Speaking", "Session ended"]);
  assert.deepEqual(pt, ["Pronto", "Conectando", "Ouvindo", "Ouvindo …", "Processando", "Falando", "Sessão encerrada"]);
});

test("the meter follows the voice while speaking and idles otherwise", () => {
  const loud = renderToString(<Face lang="en" view={view("speaking")} level={0.5} />);
  const idle = renderToString(<Face lang="en" view={view("awake")} />);
  const height = (html: string) => Number(/style="height:(\d+)%"/.exec(html)![1]);
  assert.ok(height(loud) > height(idle));
  assert.match(loud, /meter is-live/);
});

test("a problem mood marks the panel, offline greys it and says No connection", () => {
  assert.match(renderToString(<Face lang="en" view={view("awake", { mood: "oops" })} />), /has-problem/);
  const html = renderToString(<Face lang="en" view={faceOf({ ...restingFace("en"), online: false }, 0)} />);
  assert.match(html, /is-offline/);
  assert.ok(html.includes("No connection"));
});

test("the volume pop", () => {
  const v = faceOf({ ...restingFace("en"), capturing: true, startedAt: 1, volume: 40, volumePopAt: 999 }, 1000);
  assert.match(renderToString(<Face lang="en" view={v} />), /presence-pop/);
});
