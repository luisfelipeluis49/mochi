import { test } from "node:test";
import assert from "node:assert/strict";
import { renderToString } from "react-dom/server";
import { TRAINING_MS, TrainingClock, TrainingDone, TrainingScreen, type TrainingScreenProps } from "./TrainingScreen.tsx";

const noop = () => {};
const base: TrainingScreenProps = {
  lang: "en", phase: "idle", training: false, elapsedMs: 0, micBlocked: null, banner: null, reachable: true, hasWords: true,
  onStart: noop, onStop: noop, onFixMic: noop, onDismissBanner: noop, onGoAnalytics: noop, onGoSession: noop,
};

test("idle: what a training is, and Start", () => {
  const html = renderToString(<TrainingScreen {...base} />);
  assert.ok(html.includes("Start training") && html.includes("About 5 minutes") && html.includes("No hints and no second tries"));
  assert.ok(!html.includes("<progress") && !html.includes("Finish now"));
});

test("no saved words: said so, Start still works", () => {
  const html = renderToString(<TrainingScreen {...base} hasWords={false} />);
  assert.ok(html.includes("No saved words yet"));
  assert.ok(!/disabled=""[^>]*>[^<]*Start training/.test(html));
});

test("running: the clock, the progress bar and Finish; no Start", () => {
  const html = renderToString(<TrainingScreen {...base} phase="capturing" training elapsedMs={90_000} />);
  assert.ok(html.includes("01:30 / 05:00") && html.includes("<progress") && html.includes("Finish now"));
  assert.ok(!html.includes("Start training") && !html.includes("wrapping up"));
});

test("from minute four Mochi is wrapping up; the clock never passes five minutes", () => {
  assert.ok(renderToString(<TrainingClock lang="en" elapsedMs={4 * 60_000} />).includes("wrapping up"));
  assert.ok(renderToString(<TrainingClock lang="en" elapsedMs={TRAINING_MS + 60_000} />).includes("05:00 / 05:00"));
});

test("another kind of session is running: Start is off and the way back is offered", () => {
  const html = renderToString(<TrainingScreen {...base} phase="capturing" training={false} />);
  assert.ok(html.includes("A session is running.") && html.includes("Go to the session"));
  assert.match(html, /disabled=""[^>]*>Start training/);
});

test("a missing microphone or an unreachable backend turns Start off", () => {
  assert.match(renderToString(<TrainingScreen {...base} micBlocked="denied" />), /disabled=""[^>]*>Start training/);
  assert.match(renderToString(<TrainingScreen {...base} reachable={false} />), /disabled=""[^>]*>Start training/);
});

test("portuguese", () => {
  const html = renderToString(<TrainingScreen {...base} lang="pt-BR" />);
  assert.ok(html.includes("Começar o treino") && html.includes("Sem dicas"));
});

test("the done card is kind and points to progress", () => {
  const html = renderToString(<TrainingDone lang="en" onGoAnalytics={noop} />);
  assert.ok(html.includes("Nice work!") && html.includes("See your progress"));
});
