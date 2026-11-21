// =============================================================================
// insights.ts  —  LANGUAGE: TypeScript (no React, no screen)
// -----------------------------------------------------------------------------
// The numbers for the "Minhas conversas" page (/me?user=...): Mochi's reports of a
// person's real conversations (work meetings, calls, chats), added up over time.
// It only COUNTS and GROUPS what the backend already analysed (conversation.report.created,
// PROPOSED v0.5). Finding the mistakes is the backend's job, never the browser's.
// Tested in insights.test.ts.
// =============================================================================

import type { ConversationReport, Mistake, MistakeKind } from "../contracts.ts";
import type { ClientState } from "./store.ts";

/** Every conversation, oldest first. */
export function conversations(state: ClientState): ConversationReport[] {
  return Object.values(state.reports).sort((a, b) => Date.parse(a.started_at) - Date.parse(b.started_at));
}

/** How many mistakes in one conversation (each mistake counts as many times as it happened). */
export function mistakeCount(r: ConversationReport): number {
  return r.mistakes.reduce((sum, m) => sum + m.count, 0);
}

/** Mistakes per 10 minutes of speaking, so long and short conversations compare fairly. One decimal. */
export function mistakesPer10Min(r: ConversationReport): number {
  if (r.speaking_minutes <= 0) return 0;
  return Math.round((mistakeCount(r) / r.speaking_minutes) * 100) / 10;
}

export interface Totals {
  conversations: number;
  minutes: number;        // minutes the person spoke, all conversations
  unknownWords: number;   // different words they needed (each word once)
  mistakes: number;       // all mistakes, all conversations
}

export function totals(list: ConversationReport[]): Totals {
  return {
    conversations: list.length,
    minutes: list.reduce((s, r) => s + r.speaking_minutes, 0),
    unknownWords: new Set(list.flatMap((r) => r.unknown_words.map((w) => w.expression.toLowerCase()))).size,
    mistakes: list.reduce((s, r) => s + mistakeCount(r), 0),
  };
}

/** Change in mistakes per 10 minutes, first conversation vs last, in % (negative = fewer mistakes = better).
 *  null when there are fewer than 2 conversations or the first had none. */
export function improvementPercent(list: ConversationReport[]): number | null {
  if (list.length < 2) return null;
  const first = mistakesPer10Min(list[0]);
  const last = mistakesPer10Min(list[list.length - 1]);
  if (first === 0) return null;
  return Math.round(((last - first) / first) * 100);
}

export interface MistakeTopic {
  topic: string;
  kind: MistakeKind;
  count: number;           // all conversations together
  conversations: number;   // in how many conversations it happened
  example: Mistake;        // the most recent example (said → better)
}

/** The mistakes grouped by topic, most frequent first. */
export function topMistakes(list: ConversationReport[]): MistakeTopic[] {
  const byTopic = new Map<string, MistakeTopic>();
  for (const r of list) {             // oldest → newest, so the last example kept is the newest
    for (const m of r.mistakes) {
      const t = byTopic.get(m.topic);
      if (t) {
        t.count += m.count;
        t.conversations += 1;
        t.example = m;
      } else {
        byTopic.set(m.topic, { topic: m.topic, kind: m.kind, count: m.count, conversations: 1, example: m });
      }
    }
  }
  return [...byTopic.values()].sort((a, b) => b.count - a.count || a.topic.localeCompare(b.topic));
}

export interface WordNeeded {
  expression: string;
  meaning: string | null;
  saidInstead: string | null;
  times: number;            // all conversations together
  lastSeen: string;         // started_at of the last conversation where it was needed
}

/** The words the person didn't know, most needed first (a word needed again is a word to learn). */
export function wordsNeeded(list: ConversationReport[]): WordNeeded[] {
  const byWord = new Map<string, WordNeeded>();
  for (const r of list) {
    for (const w of r.unknown_words) {
      const key = w.expression.toLowerCase();
      const known = byWord.get(key);
      if (known) {
        known.times += w.times;
        known.lastSeen = r.started_at;
        known.saidInstead = w.said_instead ?? known.saidInstead;
      } else {
        byWord.set(key, { expression: w.expression, meaning: w.meaning, saidInstead: w.said_instead, times: w.times, lastSeen: r.started_at });
      }
    }
  }
  return [...byWord.values()].sort((a, b) => b.times - a.times || Date.parse(b.lastSeen) - Date.parse(a.lastSeen));
}

/** What to practice next: the newest report's own list if it has one, else the 3 most common mistake topics. */
export function practiceNext(list: ConversationReport[]): string[] {
  const latest = list.at(-1);
  if (latest && latest.focus_next.length > 0) return latest.focus_next.slice(0, 3);
  return topMistakes(list).slice(0, 3).map((t) => t.topic);
}

/** Bar width in % for the trend chart (the worst conversation = full bar). */
export function trendBarPercent(value: number, list: ConversationReport[]): number {
  const max = Math.max(0.1, ...list.map(mistakesPer10Min));
  return Math.round((value / max) * 100);
}
