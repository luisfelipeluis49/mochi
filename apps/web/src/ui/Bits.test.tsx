import { test } from "node:test";
import assert from "node:assert/strict";
import { renderToString } from "react-dom/server";
import { Banner } from "./Banner.tsx";
import { SpeechBubble } from "./SpeechBubble.tsx";
import { StatusChip } from "./StatusChip.tsx";

test("StatusChip states", () => {
  assert.ok(renderToString(<StatusChip lang="en" state="listening" />).includes("Listening"));
  assert.ok(renderToString(<StatusChip lang="pt-BR" state="listening" />).includes("Ouvindo"));
  assert.ok(renderToString(<StatusChip lang="en" state="asleep" />).includes("Asleep"));
  assert.ok(renderToString(<StatusChip lang="en" state="offline" />).includes("No connection"));
});

test("SpeechBubble is aria-live and carries the language", () => {
  const html = renderToString(<SpeechBubble lang="en" speak={{ text: "You can say: queue.", language: "en", reason: "asks_mochi" }} speaking />);
  assert.match(html, /aria-live="polite"/);
  assert.ok(html.includes('lang="en"'));
  assert.ok(html.includes("You can say: queue."));
  assert.match(renderToString(<SpeechBubble lang="en" speak={null} speaking={false} />), /aria-live="polite"/);
});

test("Banner roles", () => {
  assert.match(renderToString(<Banner lang="en" tone="problem" title="t">b</Banner>), /role="alert"/);
  assert.match(renderToString(<Banner lang="en" tone="notice">b</Banner>), /role="status"/);
  assert.match(renderToString(<Banner lang="en" tone="notice" onDismiss={() => {}}>b</Banner>), /aria-label="Dismiss"/);
});
