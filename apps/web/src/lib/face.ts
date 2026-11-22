// Mochi's face on the web, derived from state and time (section 3.3). Pure.
// It mirrors hardware/pi-bridge/mochi_device/face.py: the same modes and moods, but every value is
// worked out here in the browser from the session, the hint, the voice levels and the clock.

import type { Hint } from "../contracts.ts";
import { type UiLang, languageName } from "./i18n.ts";

export type FaceMode = "sleeping" | "waking" | "awake" | "hearing" | "thinking" | "speaking" | "bye";
export type FaceMood = "neutral" | "happy" | "excited" | "love" | "laughing" | "surprised" | "curious" | "proud" | "oops" | "cool" | "sleepy";

export const FACE_MODES: readonly FaceMode[] = ["sleeping", "waking", "awake", "hearing", "thinking", "speaking", "bye"];
export const FACE_MOODS: readonly FaceMood[] = ["neutral", "happy", "excited", "love", "laughing", "surprised", "curious", "proud", "oops", "cool", "sleepy"];

export const BYE_MS = 2000;
export const HEARING_MS = 500;
export const THINKING_MS = 1500;
export const HAPPY_MS = 4000;
export const PROUD_MS = 5000;
export const EXCITED_MS = 5000;
export const USED_BADGE_MS = 5000;
export const VOLUME_POP_MS = 2000;
export const SLEEPY_MS = 5 * 60_000;
/** Mic loudness (0..1) above which this browser counts as "hearing". */
export const HEARING_LEVEL = 0.06;
/** Mochi's voice counts as quiet this long after its level last went over QUIET_LEVEL. */
export const SPEAK_QUIET_MS = 700;
export const QUIET_LEVEL = 0.05;

export interface FaceInput {
  lang: UiLang;
  displayName: string;
  capturing: boolean;
  /** the Start tap happened and the microphone is not published yet */
  starting: boolean;
  /** client clock of this page's Stop (0 = none) */
  stoppedAt: number;
  /** client clock of the last microphone level over HEARING_LEVEL (0 = none) */
  lastHearingAt: number;
  /** client clock of the last hint or spoken line (ends "thinking") */
  lastResponseAt: number;
  /** client clock until which Mochi is speaking (see speakingUntil) */
  speakingUntil: number;
  /** the live hint, or null */
  hint: Hint | null;
  /** client clock of the last session state change (a fallback for startedAt after a reload) */
  lastStateChange: number;
  /** an error banner is showing */
  problem: boolean;
  /** client clock when capturing began (0 = unknown) */
  startedAt: number;
  online: boolean;
  proudAt: number;
  excitedAt: number;
  used: { expression: string; at: number } | null;
  volume: number;
  volumePopAt: number;
}

export interface FaceView {
  mode: FaceMode;
  mood: FaceMood;
  /** the big word under the face ("" = none) */
  word: string;
  /** "English · adiar" ("" = none) */
  note: string;
  /** "<name> …" while hearing ("" = nobody) */
  who: string;
  /** "★ You used it!" for a few seconds, or null */
  badge: { kind: "used"; word: string } | null;
  /** the volume pop above the face, or null */
  pop: { kind: "volume"; value: number } | null;
  offline: boolean;
}

const within = (at: number, ms: number, now: number) => at > 0 && now >= at && now - at < ms;

function modeOf(i: FaceInput, now: number): FaceMode {
  if (i.starting) return "waking";
  if (!i.capturing) return within(i.stoppedAt, BYE_MS, now) ? "bye" : "sleeping";
  if (i.speakingUntil > now) return "speaking";
  if (within(i.lastHearingAt, HEARING_MS, now)) return "hearing";
  if (within(i.lastHearingAt, HEARING_MS + THINKING_MS, now) && i.lastResponseAt < i.lastHearingAt) return "thinking";
  return "awake";
}

function moodOf(i: FaceInput, mode: FaceMode, hint: Hint | null, now: number): FaceMood {
  if (i.problem) return "oops";
  if (mode === "sleeping" || mode === "waking" || mode === "bye") return "neutral";
  if (within(i.excitedAt, EXCITED_MS, now)) return "excited";
  if (within(i.proudAt, PROUD_MS, now)) return "proud";
  if (hint) return "curious";
  const started = i.startedAt || i.lastStateChange;
  if (within(started, HAPPY_MS, now)) return "happy";
  const lastActive = Math.max(started, i.lastHearingAt);
  if (lastActive > 0 && now - lastActive >= SLEEPY_MS) return "sleepy";
  return "neutral";
}

export function faceOf(i: FaceInput, now: number): FaceView {
  const mode = modeOf(i, now);
  const hint = i.capturing ? i.hint : null;
  const mood = moodOf(i, mode, hint, now);
  const word = hint?.expression ?? "";
  const note = hint ? [languageName(i.lang, hint.target_language), hint.meaning].filter(Boolean).join(" · ") : "";
  const who = mode === "hearing" && i.displayName ? `${i.displayName} …` : "";
  const badge = i.used && within(i.used.at, USED_BADGE_MS, now) ? { kind: "used" as const, word: i.used.expression } : null;
  const pop = within(i.volumePopAt, VOLUME_POP_MS, now) ? { kind: "volume" as const, value: i.volume } : null;
  return { mode, mood, word, note, who, badge, pop, offline: !i.online };
}

/** Until when Mochi is speaking: while its voice is loud, plus SPEAK_QUIET_MS; without any level
 *  reading, 1.2 s + 0.35 s per word from when the line arrived. */
export function speakingUntil(speakAt: number, text: string, lastLoudAt: number): number {
  if (speakAt <= 0) return 0;
  if (lastLoudAt >= speakAt) return lastLoudAt + SPEAK_QUIET_MS;
  const words = text.trim().split(/\s+/).filter(Boolean).length;
  return speakAt + 1200 + 350 * words;
}

/** An input with nothing going on (for tests and the first render). */
export function restingFace(lang: UiLang = "en", displayName = ""): FaceInput {
  return {
    lang, displayName, capturing: false, starting: false, stoppedAt: 0, lastHearingAt: 0, lastResponseAt: 0,
    speakingUntil: 0, hint: null, lastStateChange: 0, problem: false, startedAt: 0, online: true,
    proudAt: 0, excitedAt: 0, used: null, volume: 80, volumePopAt: 0,
  };
}
