import { test } from "node:test";
import assert from "node:assert/strict";
import { renderToString } from "react-dom/server";
import { MicGate } from "./MicGate.tsx";
import { Unreachable } from "./Unreachable.tsx";
import { Onboarding, defaultLanguages, validName } from "./Onboarding.tsx";
import { ProfileScreen } from "./ProfileScreen.tsx";

const noop = () => {};

test("MicGate: the waiting screen, with the allow button only when slow", () => {
  const html = renderToString(<MicGate lang="en" slow={false} onAllow={noop} />);
  assert.ok(html.includes("Allow the microphone"));
  assert.ok(html.includes("Mochi only listens while a session is running."));
  assert.ok(!html.includes(">Allow microphone<"));
  assert.ok(renderToString(<MicGate lang="en" slow onAllow={noop} />).includes(">Allow microphone<"));
  assert.ok(renderToString(<MicGate lang="pt-BR" slow onAllow={noop} />).includes("Libere o microfone"));
});

test("Unreachable: waking copy, then unreachable copy with Try again", () => {
  const waking = renderToString(<Unreachable lang="en" problem="waking" onRetry={noop} />);
  assert.ok(waking.includes("Connecting to Mochi…"));
  assert.ok(!waking.includes("Try again"));
  const down = renderToString(<Unreachable lang="en" problem="unreachable" onRetry={noop} />);
  assert.ok(down.includes("Can&#x27;t reach Mochi"));
  assert.ok(down.includes("Try again"));
  assert.match(down, /role="alert"/);
  assert.ok(renderToString(<Unreachable lang="pt-BR" problem="offline" onRetry={noop} />).includes("Você está sem internet"));
});

test("Onboarding: submit disabled while the name is empty; languages pre-filled from the UI", () => {
  const en = renderToString(<Onboarding lang="en" note={null} busy={false} error={null} onSubmit={noop} />);
  assert.ok(en.includes("Welcome to Mochi"));
  assert.ok(en.includes("Enter your name to set up your workspace."));
  assert.match(en, /<button type="submit"[^>]*disabled=""/);
  assert.match(en, /autoComplete="given-name"|autocomplete="given-name"/);
  assert.match(en, /maxLength="40"|maxlength="40"/);
  // English UI: speaks English, learns Portuguese
  const selects = [...en.matchAll(/<select[^>]*>(.*?)<\/select>/g)].map((m) => m[1]);
  assert.match(selects[0], /<option value="en" selected="">English<\/option>/);
  assert.match(selects[1], /<option value="pt-BR" selected="">Portuguese<\/option>/);
  const pt = renderToString(<Onboarding lang="pt-BR" note={null} busy={false} error={null} onSubmit={noop} />);
  assert.ok(pt.includes("Bem-vindo ao Mochi"));
  assert.ok(pt.includes("Informe seu nome para configurar seu espaço."));
  const ptSelects = [...pt.matchAll(/<select[^>]*>(.*?)<\/select>/g)].map((m) => m[1]);
  assert.match(ptSelects[0], /<option value="pt-BR" selected="">Português<\/option>/);
  assert.match(ptSelects[1], /<option value="en" selected="">Inglês<\/option>/);
});

test("Onboarding: notes and errors", () => {
  assert.ok(renderToString(<Onboarding lang="en" note="profile_lost" busy={false} error={null} onSubmit={noop} />).includes("Tell it your name again."));
  assert.ok(renderToString(<Onboarding lang="en" note={null} busy={false} error="invalid" onSubmit={noop} />).includes("Use 1 to 40 letters."));
  assert.ok(renderToString(<Onboarding lang="pt-BR" note={null} busy={false} error="invalid" onSubmit={noop} />).includes("Use de 1 a 40 letras."));
  assert.ok(renderToString(<Onboarding lang="en" note={null} busy={false} error="unreachable" onSubmit={noop} />).includes("Can&#x27;t reach Mochi"));
});

test("name validation and default languages", () => {
  assert.equal(validName(""), false);
  assert.equal(validName("   "), false);
  assert.equal(validName(" Ana "), true);
  assert.equal(validName("x".repeat(40)), true);
  assert.equal(validName("x".repeat(41)), false);
  assert.equal(validName("A\u0007na"), false);
  assert.deepEqual(defaultLanguages("pt-BR"), { speak: "pt-BR", learn: "en" });
  assert.deepEqual(defaultLanguages("en"), { speak: "en", learn: "pt-BR" });
});

test("Profile: languages, switch and the forget note", () => {
  const html = renderToString(<ProfileScreen lang="en" user={{ user_id: "ana", display_name: "Ana", comfortable_languages: ["pt-BR"], target_language: "en" }} onLang={noop} onForget={noop} />);
  assert.ok(html.includes("Forget me on this device"));
  assert.ok(html.includes("Nothing is deleted on Mochi"));
  assert.match(html, /aria-pressed="true" lang="en"/);
  assert.ok(html.includes("Portuguese") && html.includes("English"));
});
