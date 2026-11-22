import { test } from "node:test";
import assert from "node:assert/strict";
import { copy, detectLang, fill, languageName, plural, storeLang, storedLang, t, wokenBy, LANG_KEY } from "./i18n.ts";
import { memoryStore, throwingStore } from "./storage.ts";

test("both languages have exactly the same keys", () => {
  assert.deepEqual(Object.keys(copy.en).sort(), Object.keys(copy["pt-BR"]).sort());
});

test("no string is empty", () => {
  for (const lang of ["en", "pt-BR"] as const) for (const [k, v] of Object.entries(copy[lang])) assert.ok(v.trim().length > 0, `${lang}.${k}`);
});

test("placeholders match between languages", () => {
  const ph = (s: string) => (s.match(/\{\w+\}/g) ?? []).sort().join();
  for (const k of Object.keys(copy.en) as (keyof typeof copy.en)[]) assert.equal(ph(copy.en[k]), ph(copy["pt-BR"][k]), k);
});

test("detection order: ?lang=, then storage, then the browser", () => {
  assert.equal(detectLang({ search: "?lang=pt-BR", stored: "en", navigatorLanguage: "en-US" }), "pt-BR");
  assert.equal(detectLang({ search: "?lang=en", stored: "pt-BR", navigatorLanguage: "pt-PT" }), "en");
  assert.equal(detectLang({ search: "", stored: "pt-BR", navigatorLanguage: "en-US" }), "pt-BR");
  assert.equal(detectLang({ search: "?lang=xx", stored: null, navigatorLanguage: "pt-PT" }), "pt-BR");
  assert.equal(detectLang({ navigatorLanguage: "de-DE" }), "en");
  assert.equal(detectLang({}), "en");
});

test("the stored language survives blocked storage", () => {
  const s = memoryStore();
  storeLang("pt-BR", s);
  assert.equal(storedLang(s), "pt-BR");
  assert.equal(s.data.get(LANG_KEY), "pt-BR");
  assert.equal(storedLang(throwingStore()), null);
  assert.doesNotThrow(() => storeLang("en", throwingStore()));
});

test("helpers", () => {
  assert.equal(fill("{a} and {b}", { a: 1 }), "1 and {b}");
  assert.equal(t("en", "training_start"), "Start training");
  assert.equal(plural("en", "hints", 1), "1 hint");
  assert.equal(plural("pt-BR", "hints", 3), "3 dicas");
  assert.equal(languageName("en", "en"), "English");
  assert.equal(languageName("pt-BR", "en"), "Inglês");
  assert.equal(languageName("en", "pt-BR"), "Portuguese");
  assert.equal(languageName("pt-BR", "pt-BR"), "Português");
  assert.equal(wokenBy("pt-BR"), "oi mochi");
  assert.equal(wokenBy("en"), "hey mochi");
});

test("state labels are the AGENTS 6.3 UI labels", () => {
  assert.equal(copy.en.state_DISCOVERED, "Hint shown");
  assert.equal(copy.en.state_ASSISTED, "Used with help");
  assert.equal(copy.en.state_REINFORCED, "Recalled in a game");
  assert.equal(copy.en.state_USED_INDEPENDENTLY, "Used on your own");
  assert.equal(copy["pt-BR"].state_DISCOVERED, "Dica mostrada");
  assert.equal(copy["pt-BR"].state_USED_INDEPENDENTLY, "Usada sem ajuda");
});
