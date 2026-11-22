import { test } from "node:test";
import assert from "node:assert/strict";
import { renderToString } from "react-dom/server";
import { TrainingCard, TrainingDone, TrainingEmpty, TrainingScreen, speechCtor } from "./TrainingScreen.tsx";
import type { LearningEvent } from "../contracts.ts";

const noop = () => {};
const NOW = Date.parse("2026-11-21T10:00:00.000Z");
const word = (id: string, over: Partial<LearningEvent> = {}): LearningEvent => ({
  learning_event_id: id, user_id: "luis", target_language: "en", expression: "umbrella", meaning: "guarda-chuva", detection_signal: "code_switch",
  hint_id: null, learning_state: "DISCOVERED", state_history: [{ learning_state: "DISCOVERED", at: "2026-11-21T09:00:00.000Z" }], ...over,
});
const cardProps = { lang: "en" as const, word: word("a"), index: 2, total: 10, hasSpeech: false, listening: false, onAnswer: noop, onDontKnow: noop, onNext: noop, onSay: noop };

test("a card: the meaning, the question, progress and the input attributes", () => {
  const html = renderToString(<TrainingCard {...cardProps} feedback={null} />);
  assert.ok(html.includes("guarda-chuva"));
  assert.ok(html.includes("How do you say this in English?"));
  assert.ok(html.includes("3 / 10"));
  assert.match(html, /lang="en"/);
  assert.match(html, /autoCapitalize="off"|autocapitalize="off"/);
  assert.match(html, /autoCorrect="off"|autocorrect="off"/);
  assert.match(html, /spellCheck="false"|spellcheck="false"/);
  assert.ok(html.includes("Check") && html.includes("I don&#x27;t know"));
  assert.ok(renderToString(<TrainingCard {...cardProps} lang="pt-BR" word={word("b", { target_language: "pt-BR", meaning: "umbrella" })} feedback={null} />).includes("Como se diz isso em português?"));
});

test("result states", () => {
  assert.ok(renderToString(<TrainingCard {...cardProps} feedback={{ outcome: "correct", expected: "umbrella" }} />).includes("Right!"));
  assert.ok(renderToString(<TrainingCard {...cardProps} feedback={{ outcome: "almost", expected: "umbrella" }} />).includes("Almost! It&#x27;s spelled “umbrella”."));
  assert.ok(renderToString(<TrainingCard {...cardProps} feedback={{ outcome: "wrong", expected: "umbrella" }} />).includes("The word is “umbrella”."));
  assert.ok(renderToString(<TrainingCard {...cardProps} lang="pt-BR" feedback={{ outcome: "wrong", expected: "umbrella" }} />).includes("A palavra é “umbrella”."));
  const done = renderToString(<TrainingDone lang="en" right={7} review={3} nextAt={NOW + 600_000} now={NOW} onAgain={noop} />);
  assert.ok(done.includes("7 right · 3 to review") && done.includes("Train again") && done.includes("in 10 minutes"));
});

test("the Say it button only with SpeechRecognition", () => {
  assert.ok(!renderToString(<TrainingCard {...cardProps} feedback={null} />).includes("Say it"));
  const html = renderToString(<TrainingCard {...cardProps} hasSpeech feedback={null} />);
  assert.ok(html.includes("Say it") && html.includes("Uses your browser&#x27;s speech service"));
  assert.equal(speechCtor({}), null);
  class R {}
  assert.equal(speechCtor({ webkitSpeechRecognition: R }), R);
});

test("empty states", () => {
  const none = renderToString(<TrainingEmpty lang="en" hasWords={false} nextAt={null} now={NOW} onGoSession={noop} />);
  assert.ok(none.includes("Training is made of the words Papear showed you when you got stuck.") && none.includes('href="/session"'));
  const caught = renderToString(<TrainingEmpty lang="pt-BR" hasWords nextAt={NOW + 86_400_000} now={NOW} onGoSession={noop} />);
  assert.ok(caught.includes("Tudo em dia! Próxima palavra amanhã."));
});

test("the screen: a round from the words, untrainable ones counted", () => {
  const words = [word("a"), word("b", { expression: "queue", meaning: "fila" }), word("c", { meaning: null }), word("d", { user_id: "guest" })];
  const html = renderToString(<TrainingScreen lang="en" userId="luis" words={words} progress={{}} now={NOW} hasSpeech={false} onResult={noop} onGoSession={noop} />);
  assert.ok(html.includes("1 / 2"));
  assert.ok(html.includes("1 word has no meaning yet and is not in training."));
  const empty = renderToString(<TrainingScreen lang="en" userId="luis" words={[]} progress={{}} now={NOW} hasSpeech={false} onResult={noop} onGoSession={noop} />);
  assert.ok(empty.includes("Training is made of the words Papear showed you when you got stuck."));
  const later = renderToString(<TrainingScreen lang="en" userId="luis" words={[word("a")]} progress={{ a: { box: 2, due_at: NOW + 86_400_000, correct: 1, wrong: 0, last_at: NOW } }} now={NOW} hasSpeech={false} onResult={noop} onGoSession={noop} />);
  assert.ok(later.includes("All caught up! Next word due tomorrow."));
});
