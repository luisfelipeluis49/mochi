import { test } from "node:test";
import assert from "node:assert/strict";
import { clock, dayKey, elapsed, longDay, minutes, percent, previousDay, relative, shortDay } from "./format.ts";

const at = Date.parse("2026-11-21T10:00:00.000Z");

test("dayKey follows the time zone", () => {
  assert.equal(dayKey(at, "UTC"), "2026-11-21");
  assert.equal(dayKey(Date.parse("2026-11-21T02:00:00.000Z"), "America/Sao_Paulo"), "2026-11-20");
});

test("previousDay crosses months and years", () => {
  assert.equal(previousDay("2026-11-21"), "2026-11-20");
  assert.equal(previousDay("2026-12-01"), "2026-11-30");
  assert.equal(previousDay("2027-01-01"), "2026-12-31");
});

test("dates and times per locale", () => {
  assert.equal(longDay(at, { lang: "en", timeZone: "UTC" }), "Saturday, 21 Nov");
  assert.match(longDay(at, { lang: "pt-BR", timeZone: "UTC" }), /sábado, 21 de nov/);
  assert.equal(shortDay(at, { lang: "en", timeZone: "UTC" }), "21 Nov");
  assert.equal(clock(at, { lang: "en", timeZone: "UTC" }), "10:00");
  assert.equal(clock(at, { lang: "pt-BR", timeZone: "UTC" }), "10:00");
});

test("minutes keep one decimal in the locale", () => {
  assert.equal(minutes(12.5, { lang: "en" }), "12.5");
  assert.equal(minutes(12.5, { lang: "pt-BR" }), "12,5");
  assert.equal(minutes(3, { lang: "en" }), "3");
  assert.equal(minutes(2.04, { lang: "en" }), "2");
});

test("elapsed is mm:ss", () => {
  assert.equal(elapsed(0), "00:00");
  assert.equal(elapsed(65_000), "01:05");
  assert.equal(elapsed(3_725_000), "1:02:05");
  assert.equal(elapsed(-5), "00:00");
});

test("relative times", () => {
  assert.equal(relative(at + 10 * 60_000, at, { lang: "en" }), "in 10 minutes");
  assert.equal(relative(at + 86_400_000, at, { lang: "en" }), "tomorrow");
  assert.equal(relative(at + 86_400_000, at, { lang: "pt-BR" }), "amanhã");
  assert.equal(relative(at, at, { lang: "en" }), "now");
  assert.equal(relative(at + 3 * 3_600_000, at, { lang: "en" }), "in 3 hours");
});

test("percent", () => {
  assert.equal(percent(0.7, { lang: "en" }), "70%");
});
