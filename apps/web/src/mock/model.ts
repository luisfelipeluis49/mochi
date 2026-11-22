// A ready AppModel built from the mock backend, synchronously: used by the App render test and
// handy for looking at screens without a browser.
import type { AppActions, AppModel } from "../hooks/useApp.ts";
import { appReducer, initialApp, type AppAction } from "../lib/appState.ts";
import type { UiLang } from "../lib/i18n.ts";
import type { Screen } from "../lib/routes.ts";
import type { Hint, MochiEvent, User } from "../contracts.ts";
import { demoWords, seedFor } from "./backend.ts";

export const MOCK_NOW = Date.parse("2026-11-21T13:00:30.000Z");

export function mockUser(lang: UiLang = "en"): User {
  return lang === "pt-BR"
    ? { user_id: "luis-felipe-3f9c1a", display_name: "Luís Felipe", comfortable_languages: ["pt-BR"], target_language: "en" }
    : { user_id: "ben-1a2b3c", display_name: "Ben", comfortable_languages: ["en"], target_language: "pt-BR" };
}

/** A capturing session with a live hint, saved words and two past records. */
export function mockModel(opts: { lang?: UiLang; screen?: Screen; capturing?: boolean } = {}): AppModel {
  const lang = opts.lang ?? "en";
  const user = mockUser(lang);
  const now = MOCK_NOW;
  const seed = seedFor(user, now);
  const sid = "w-3f9c1a2b";
  const w = demoWords(user.target_language)[0];
  const hint: Hint = {
    hint_id: "hint_m1", target_user_id: user.user_id, target_language: user.target_language, expression: w.expression,
    meaning: w.meaning, example: w.example, reason: "code_switch", expires_at: new Date(now + 6000).toISOString(),
  };
  const ev = (seq: number, e: Omit<MochiEvent, "schema_version" | "event_id" | "session_id" | "emitted_at" | "sequence">): MochiEvent =>
    ({ schema_version: "0.4", event_id: `evt_${seq}`, session_id: sid, emitted_at: new Date(now - 2000).toISOString(), sequence: seq, ...e }) as MochiEvent;
  const capturing = opts.capturing ?? true;
  const actions: AppAction[] = [
    { type: "gate", gate: { status: "ok" } },
    { type: "probe", probe: { status: "ok" } },
    { type: "identity_ok", user },
    { type: "words", words: seed.words },
    { type: "records", records: seed.records },
  ];
  if (capturing) {
    actions.push(
      { type: "start_begin", sessionId: sid },
      { type: "live", action: { type: "event", now: now - 60_000, event: ev(1, { type: "session.state.changed", payload: { status: "active", mode: "together", focus: user.target_language, capturing: true, participants: [user.user_id, "guest"] } }) } },
      { type: "start_ok", now: now - 60_000 },
      { type: "live", action: { type: "event", now: now - 2000, event: ev(2, { type: "hint.created", payload: hint }) } },
    );
  }
  const state = actions.reduce(appReducer, initialApp({ lang, user, sessionId: sid }));
  return {
    state, screen: opts.screen ?? "session", now, hasSpeech: false, onboarding: { busy: false, error: null }, digestWeek: 0, mode: "listen", training: false,
    voice: { lastHearingAt: 0, lastLoudAt: 0, level: 0 }, timeZone: "UTC",
  };
}

export const noopActions: AppActions = {
  navigate() {}, start() {}, stop() {}, rejoin() {}, retryGate() {}, continueWithoutMic() {}, retryProbe() {}, setVolume() {},
  dismissBanner() {}, dismissSaved() {}, submitName() {}, setLang() {}, forget() {}, selectWeek() {}, setMode() {},
};
