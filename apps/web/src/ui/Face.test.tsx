import { test } from "node:test";
import assert from "node:assert/strict";
import { renderToString } from "react-dom/server";
import { Face } from "./Face.tsx";
import { FACE_MODES, faceOf, restingFace } from "../lib/face.ts";

test("the mode and mood classes and the aria-label", () => {
  const view = faceOf({ ...restingFace("en", "Ana"), capturing: true, startedAt: 1, lastHearingAt: 999 }, 1000);
  const html = renderToString(<Face lang="en" view={view} />);
  assert.match(html, /class="mochi-face mode-hearing mood-happy"/);
  assert.match(html, /role="img"/);
  assert.match(html, /aria-label="Mochi hears Ana"/);
  assert.ok(html.includes("Ana …"));
});

test("each mode has a label in both languages", () => {
  for (const mode of FACE_MODES) {
    const view = { mode, mood: "neutral" as const, word: "", note: "", who: "", badge: null, pop: null, offline: false };
    assert.match(renderToString(<Face lang="en" view={view} />), new RegExp(`mode-${mode}`));
    assert.match(renderToString(<Face lang="pt-BR" view={view} />), /aria-label="O Mochi/);
  }
  const listening = renderToString(<Face lang="pt-BR" view={{ mode: "awake", mood: "curious", word: "", note: "", who: "", badge: null, pop: null, offline: false }} />);
  assert.match(listening, /aria-label="O Mochi está ouvindo"/);
  assert.match(listening, /mood-curious/);
});

test("offline greys the face and says No connection", () => {
  const html = renderToString(<Face lang="en" view={faceOf({ ...restingFace("en"), online: false }, 0)} />);
  assert.match(html, /is-offline/);
  assert.ok(html.includes("No connection"));
});

test("the volume pop", () => {
  const view = faceOf({ ...restingFace("en"), capturing: true, startedAt: 1, volume: 40, volumePopAt: 999 }, 1000);
  assert.match(renderToString(<Face lang="en" view={view} />), /face-pop/);
});
