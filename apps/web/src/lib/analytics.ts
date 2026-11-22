// Analytics: numbers and progress from the saved words, the session records and this device's
// training progress (section 3.6). Pure.

import { LEARNING_STATES, type LearningEvent, type LearningState, type SessionRecord } from "../contracts.ts";
import { type Fmt, dayKey, previousDay, shortDay } from "./format.ts";
import { type Progress, accuracy } from "./training.ts";

export const BAR_COUNT = 10;

export interface Tiles {
  words: number;
  assisted: number;
  reinforced: number;
  independent: number;
  sessions: number;
  minutes: number;
  streak: number;
  /** correct / (correct + wrong) on this device, or null */
  accuracy: number | null;
}

export interface Bar {
  record_id: string;
  minutes: number;
  label: string;
  newest: boolean;
}

export interface PathStep {
  state: LearningState;
  reached: boolean;
  /** the first time it was reached (ISO), or null */
  at: string | null;
}

export interface AnalyticsView {
  empty: boolean;
  tiles: Tiles;
  bars: Bar[];
  states: { state: LearningState; count: number }[];
  /** newest first */
  words: LearningEvent[];
}

export function everReached(w: LearningEvent, s: LearningState): boolean {
  return w.learning_state === s || w.state_history.some((h) => h.learning_state === s);
}

/** The four steps DISCOVERED -> ASSISTED -> REINFORCED -> USED_INDEPENDENTLY, with the first date each was reached. */
export function statePath(w: LearningEvent): PathStep[] {
  return LEARNING_STATES.map((state) => {
    const times = w.state_history.filter((h) => h.learning_state === state).map((h) => h.at).sort((a, b) => Date.parse(a) - Date.parse(b));
    const reached = times.length > 0 || w.learning_state === state;
    return { state, reached, at: times[0] ?? null };
  });
}

/** Consecutive local days with at least one record, ending today or yesterday. */
export function dayStreak(records: SessionRecord[], nowMs: number, timeZone?: string): number {
  const days = new Set(records.map((r) => dayKey(Date.parse(r.ended_at), timeZone)));
  let day = dayKey(nowMs, timeZone);
  if (!days.has(day)) day = previousDay(day);
  let n = 0;
  while (days.has(day)) {
    n++;
    day = previousDay(day);
  }
  return n;
}

const firstAt = (w: LearningEvent) => Date.parse(w.state_history[0]?.at ?? "") || 0;

export function buildAnalytics(words: LearningEvent[], records: SessionRecord[], progress: Progress, nowMs: number, f: Fmt): AnalyticsView {
  const newestFirst = [...words].sort((a, b) => firstAt(b) - firstAt(a));
  const byEnd = [...records].sort((a, b) => Date.parse(a.ended_at) - Date.parse(b.ended_at));
  const last = byEnd.slice(-BAR_COUNT);
  return {
    empty: words.length === 0 && records.length === 0,
    tiles: {
      words: words.length,
      assisted: words.filter((w) => everReached(w, "ASSISTED")).length,
      reinforced: words.filter((w) => everReached(w, "REINFORCED")).length,
      independent: words.filter((w) => everReached(w, "USED_INDEPENDENTLY")).length,
      sessions: records.length,
      minutes: Math.round(records.reduce((s, r) => s + r.minutes, 0) * 10) / 10,
      streak: dayStreak(records, nowMs, f.timeZone),
      accuracy: accuracy(progress),
    },
    bars: last.map((r, i) => ({ record_id: r.record_id, minutes: r.minutes, label: shortDay(Date.parse(r.started_at), f), newest: i === last.length - 1 })),
    states: LEARNING_STATES.map((state) => ({ state, count: words.filter((w) => w.learning_state === state).length })),
    words: newestFirst,
  };
}
