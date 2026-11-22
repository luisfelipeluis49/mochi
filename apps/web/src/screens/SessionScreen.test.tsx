import { test } from "node:test";
import assert from "node:assert/strict";
import { renderToString } from "react-dom/server";
import { SessionScreen, type SessionScreenProps } from "./SessionScreen.tsx";
import { faceOf, restingFace } from "../lib/face.ts";
import type { Hint } from "../contracts.ts";

const noop = () => {};
const user = { user_id: "luis", display_name: "Luís", comfortable_languages: ["pt-BR" as const], target_language: "en" as const };
const hint: Hint = { hint_id: "h1", target_user_id: "luis", target_language: "en", expression: "postpone", meaning: "adiar", example: "I need to postpone my meeting.", reason: "code_switch", expires_at: "2026-11-21T10:00:08.000Z" };

function props(over: Partial<SessionScreenProps> = {}): SessionScreenProps {
  return {
    lang: "en", user, face: faceOf(restingFace("en", "Luís"), 0), level: 0, hint: null, hintRemaining: 0, speak: null, speaking: false,
    sessionHints: [], phase: "idle", elapsedMs: 0, chip: "asleep", micBlocked: null, banner: null, saved: null, rejoin: false, volume: 80,
    activityInstruction: null, reachable: true, onStart: noop, onStop: noop, onRejoin: noop, onFixMic: noop, onVolume: noop,
    onDismissBanner: noop, onDismissSaved: noop, onGoDigest: noop, ...over,
  };
}

test("idle: the Start label and the Oi, Papear line", () => {
  const html = renderToString(<SessionScreen {...props()} />);
  assert.ok(html.includes("Start session"));
  assert.ok(html.includes("Papear listens through your microphone only while a session runs."));
  assert.ok(html.includes("Asleep"));
  assert.match(html, /mode-sleeping/);
  assert.ok(!html.includes("Stop session"));
  const pt = renderToString(<SessionScreen {...props({ lang: "pt-BR" })} />);
  assert.ok(pt.includes("Começar sessão") && pt.includes("O Papear só ouve pelo seu microfone enquanto uma sessão está ativa."));
});

test("capturing with a hint: the expression, the note, lang, aria-live, Stop and the timer", () => {
  const face = faceOf({ ...restingFace("en", "Luís"), capturing: true, startedAt: 1, hint }, 100_000);
  const html = renderToString(<SessionScreen {...props({ face, hint, hintRemaining: 0.4, phase: "capturing", chip: "listening", elapsedMs: 65_000, sessionHints: [hint] })} />);
  assert.match(html, /<p class="hint-word" lang="en">postpone<\/p>/);
  assert.ok(html.includes("English · adiar"));
  assert.match(html, /class="hint-region" aria-live="polite"/);
  assert.ok(html.includes("Stop session"));
  assert.ok(html.includes("Listening"));
  assert.ok(html.includes("01:05"));
  assert.match(html, /class="word-chip" lang="en">postpone/);
});

test("starting: Connecting with a spinner", () => {
  const html = renderToString(<SessionScreen {...props({ phase: "starting", face: faceOf({ ...restingFace("en"), starting: true }, 0) })} />);
  assert.ok(html.includes("Connecting…"));
  assert.match(html, /class="spinner"/);
  assert.match(html, /mode-waking/);
});

test("Start disabled with the mic reason and Fix microphone", () => {
  const html = renderToString(<SessionScreen {...props({ micBlocked: "denied" })} />);
  assert.match(html, /<button type="button" class="btn btn-primary btn-block btn-tall" disabled=""/);
  assert.ok(html.includes("Start needs the microphone: Microphone access is blocked"));
  assert.ok(html.includes("Fix microphone"));
});

test("saved card, reload banner, ended banner, game line", () => {
  const saved = renderToString(<SessionScreen {...props({ saved: { minutes: 12.5, hints: 3 } })} />);
  assert.ok(saved.includes("Session saved") && saved.includes("12.5 min") && saved.includes("3 hints") && saved.includes("See your digest"));
  const rejoin = renderToString(<SessionScreen {...props({ rejoin: true })} />);
  assert.ok(rejoin.includes("Your session is still running, but this page is not listening.") && rejoin.includes("Listen again"));
  const ended = renderToString(<SessionScreen {...props({ banner: { type: "http", kind: "session_ended" } })} />);
  assert.ok(ended.includes("The session ended"));
  assert.match(ended, /role="alert"/);
  const mic = renderToString(<SessionScreen {...props({ banner: { type: "mic", kind: "busy" } })} />);
  assert.ok(mic.includes("The microphone is being used by something else"));
  const game = renderToString(<SessionScreen {...props({ phase: "capturing", activityInstruction: "Ben describes. Ana guesses!" })} />);
  assert.ok(game.includes("Ben describes. Ana guesses!"));
});

test("speech bubble while capturing", () => {
  const html = renderToString(<SessionScreen {...props({ phase: "capturing", speak: { text: "You can say: queue.", language: "en", reason: "asks_mochi" }, speaking: true })} />);
  assert.ok(html.includes("You can say: queue."));
});
