// Training: spaced recall of the user's saved words (section 3.4). No new intelligence.
// Progress lives on this device only (localStorage "mochi.training.v1.<user_id>"); training never
// writes to the backend and never changes a word's learning_state.

import type { Language, LearningEvent } from "../contracts.ts";
import { type KV, localStore, safeGet, safeSet } from "./storage.ts";

export type Outcome = "correct" | "almost" | "wrong";

export interface ProgressEntry {
  box: number;
  due_at: number;
  correct: number;
  wrong: number;
  last_at: number;
}
export type Progress = Record<string, ProgressEntry>;

const MIN = 60_000;
const DAY = 24 * 60 * MIN;
/** Interval after a correct answer, by the box the card lands in. */
export const INTERVALS: Record<number, number> = { 1: 10 * MIN, 2: DAY, 3: 3 * DAY, 4: 7 * DAY, 5: 16 * DAY };
export const WRONG_DELAY = 10 * MIN;
export const ROUND_SIZE = 10;

// ---- answer check ----

const ARTICLES: Record<Language, RegExp> = {
  en: /^(the|a|an|to)\s+/,
  "pt-BR": /^(o|a|os|as|um|uma)\s+/,
};

export function normalise(s: string, language: Language): string {
  let out = s.normalize("NFC").toLowerCase().trim();
  out = out.replace(/[.,!?;:"'¿¡()]/g, "");
  out = out.replace(/\s+/g, " ").trim();
  out = out.replace(ARTICLES[language], "");
  return out;
}

export function stripAccents(s: string): string {
  return s.normalize("NFD").replace(/[̀-ͯ]/g, "").normalize("NFC");
}

export function levenshtein(a: string, b: string): number {
  const x = Array.from(a);
  const y = Array.from(b);
  let prev = Array.from({ length: y.length + 1 }, (_, i) => i);
  for (let i = 1; i <= x.length; i++) {
    const cur = [i];
    for (let j = 1; j <= y.length; j++) {
      cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x[i - 1] === y[j - 1] ? 0 : 1));
    }
    prev = cur;
  }
  return prev[y.length];
}

export function checkAnswer(expected: string, given: string, language: Language): Outcome {
  const e = normalise(expected, language);
  const g = normalise(given, language);
  if (!g) return "wrong";
  if (e === g) return "correct";
  if (stripAccents(e) === stripAccents(g)) return "almost";
  const letters = Array.from(e.replace(/\s/g, "")).length;
  const d = levenshtein(e, g);
  if (letters >= 9 && d <= 2) return "almost";
  if (letters >= 5 && d <= 1) return "almost";
  return "wrong";
}

// ---- schedule (Leitner, boxes 1-5) ----

export function newEntry(nowMs: number): ProgressEntry {
  return { box: 1, due_at: nowMs, correct: 0, wrong: 0, last_at: 0 };
}

export function schedule(entry: ProgressEntry | undefined, outcome: Outcome, nowMs: number): ProgressEntry {
  const e = entry ?? newEntry(nowMs);
  if (outcome === "wrong") {
    return { box: 1, due_at: nowMs + WRONG_DELAY, correct: e.correct, wrong: e.wrong + 1, last_at: nowMs };
  }
  const box = Math.min(e.box + 1, 5);
  return { box, due_at: nowMs + INTERVALS[box], correct: e.correct + 1, wrong: e.wrong, last_at: nowMs };
}

// ---- which words ----

export function isTrainable(w: LearningEvent, userId: string): boolean {
  return w.user_id === userId && typeof w.meaning === "string" && w.meaning.trim() !== "";
}

const firstAt = (w: LearningEvent) => Date.parse(w.state_history[0]?.at ?? "") || 0;

/** Due cards first (oldest due first), then never-trained words (newest first); at most `limit`. */
export function dueCards(words: LearningEvent[], progress: Progress, nowMs: number, limit = ROUND_SIZE): LearningEvent[] {
  const due = words.filter((w) => progress[w.learning_event_id] && progress[w.learning_event_id].due_at <= nowMs)
    .sort((a, b) => progress[a.learning_event_id].due_at - progress[b.learning_event_id].due_at);
  const fresh = words.filter((w) => !progress[w.learning_event_id]).sort((a, b) => firstAt(b) - firstAt(a));
  return [...due, ...fresh].slice(0, limit);
}

/** The earliest due time among trained words that are not due yet, or null. */
export function nextDue(words: LearningEvent[], progress: Progress, nowMs: number): number | null {
  let best: number | null = null;
  for (const w of words) {
    const p = progress[w.learning_event_id];
    if (p && p.due_at > nowMs && (best === null || p.due_at < best)) best = p.due_at;
  }
  return best;
}

// ---- storage ----

export const progressKey = (userId: string) => `mochi.training.v1.${userId}`;

/** Read and write progress; when storage is unavailable, it is kept in memory for this page. */
export class ProgressStore {
  private memory = new Map<string, Progress>();
  private readonly store: KV | null;
  constructor(store: KV | null = localStore()) {
    this.store = store;
  }
  read(userId: string): Progress {
    const raw = safeGet(this.store, progressKey(userId));
    if (raw) {
      try {
        const v: unknown = JSON.parse(raw);
        if (v && typeof v === "object" && !Array.isArray(v)) return sanitise(v as Record<string, unknown>);
      } catch {
        /* corrupt: fall through */
      }
    }
    return { ...(this.memory.get(userId) ?? {}) };
  }
  write(userId: string, p: Progress): void {
    this.memory.set(userId, p);
    safeSet(this.store, progressKey(userId), JSON.stringify(p));
  }
}

function sanitise(v: Record<string, unknown>): Progress {
  const out: Progress = {};
  for (const [id, e] of Object.entries(v)) {
    const x = e as Partial<ProgressEntry> | null;
    if (x && [x.box, x.due_at, x.correct, x.wrong, x.last_at].every((n) => typeof n === "number")) out[id] = x as ProgressEntry;
  }
  return out;
}

/** Totals for the analytics tile "Training accuracy". */
export function accuracy(progress: Progress): number | null {
  let c = 0;
  let w = 0;
  for (const e of Object.values(progress)) {
    c += e.correct;
    w += e.wrong;
  }
  return c + w === 0 ? null : c / (c + w);
}

/** BCP 47 tag for the speech recogniser. */
export function speechLang(l: Language): string {
  return l === "en" ? "en-US" : "pt-BR";
}
