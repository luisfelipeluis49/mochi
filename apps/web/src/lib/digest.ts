// The weekly digest: a wrap-up of ALL of a person's sessions in one calendar week (Monday to Sunday),
// not of a single session. Pure: records, words, training progress and the clock in, a view model out.
// The time zone is injectable so tests are stable.

import type { LearningEvent, LearningState, SessionRecord } from "../contracts.ts";
import { type CopyKey, t } from "./i18n.ts";
import { type Fmt, dayKey, previousDay, shortDay } from "./format.ts";
import { type Progress, isTrainable } from "./training.ts";

/** How many weeks back the week picker offers (this week = 0). */
export const WEEKS_BACK = 8;
export const PRACTISE_NEXT = 3;

export interface DigestWord {
  id: string;
  expression: string;
  meaning: string | null;
}

export interface DigestGroup {
  state: LearningState;
  titleKey: CopyKey;
  words: DigestWord[];
}

export interface DigestDay {
  key: string;
  /** "Mon" / "seg." */
  label: string;
  minutes: number;
  sessions: number;
}

export interface Totals {
  sessions: number;
  minutes: number;
  hints: number;
  activeDays: number;
}

export interface WeekView {
  offset: number;
  /** "17 Nov – 23 Nov" */
  range: string;
  options: { offset: number; label: string }[];
  totals: Totals;
  previous: Totals;
  /** minutes this week minus minutes the week before (one decimal) */
  deltaMinutes: number;
  days: DigestDay[];
  newWords: number;
  groups: DigestGroup[];
  practiseNext: DigestWord[];
  /** true when no session ended in this week */
  empty: boolean;
}

const GROUPS: { state: LearningState; titleKey: CopyKey }[] = [
  { state: "DISCOVERED", titleKey: "digest_new" },
  { state: "ASSISTED", titleKey: "digest_assisted" },
  { state: "REINFORCED", titleKey: "digest_reinforced" },
];

const round1 = (n: number) => Math.round(n * 10) / 10;
const toWord = (w: LearningEvent): DigestWord => ({ id: w.learning_event_id, expression: w.expression, meaning: w.meaning });
const firstAt = (w: LearningEvent) => Date.parse(w.state_history[0]?.at ?? "") || 0;

/** The day after a dayKey: "2026-11-21" -> "2026-11-22". Pure calendar arithmetic. */
export function nextDay(key: string): string {
  const [y, m, d] = key.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d + 1)).toISOString().slice(0, 10);
}

/** 0 = Monday ... 6 = Sunday, for a dayKey. */
function weekdayIndex(key: string): number {
  const [y, m, d] = key.split("-").map(Number);
  return (new Date(Date.UTC(y, m - 1, d)).getUTCDay() + 6) % 7;
}

/** The seven dayKeys (Monday first) of the week that is `offset` weeks before the one holding `nowMs`. */
export function weekKeys(nowMs: number, offset: number, timeZone?: string): string[] {
  let monday = dayKey(nowMs, timeZone);
  for (let i = weekdayIndex(monday); i > 0; i--) monday = previousDay(monday);
  for (let i = 0; i < offset * 7; i++) monday = previousDay(monday);
  const keys = [monday];
  while (keys.length < 7) keys.push(nextDay(keys[keys.length - 1]));
  return keys;
}

const asNoon = (key: string) => Date.parse(`${key}T12:00:00.000Z`);
const dayLabel = (key: string, f: Fmt) =>
  new Intl.DateTimeFormat(f.lang === "pt-BR" ? "pt-BR" : "en-GB", { timeZone: "UTC", weekday: "short" }).format(new Date(asNoon(key)));
const keyLabel = (key: string, f: Fmt) => shortDay(asNoon(key), { lang: f.lang, timeZone: "UTC" });
const rangeOf = (keys: string[], f: Fmt) => `${keyLabel(keys[0], f)} – ${keyLabel(keys[6], f)}`;

function totalsOf(records: SessionRecord[], keysSet: Set<string>, timeZone?: string): { totals: Totals; perDay: Map<string, { minutes: number; sessions: number }> } {
  const perDay = new Map<string, { minutes: number; sessions: number }>();
  let minutes = 0, hints = 0, sessions = 0;
  for (const r of records) {
    const key = dayKey(Date.parse(r.ended_at), timeZone);
    if (!keysSet.has(key)) continue;
    const d = perDay.get(key) ?? { minutes: 0, sessions: 0 };
    d.minutes += r.minutes;
    d.sessions += 1;
    perDay.set(key, d);
    minutes += r.minutes;
    hints += r.hint_count;
    sessions += 1;
  }
  return { totals: { sessions, minutes: round1(minutes), hints, activeDays: perDay.size }, perDay };
}

/** The wrap-up of one week. Always returns a view; `empty` says the week had no session. */
export function buildDigest(
  records: SessionRecord[], words: LearningEvent[], progress: Progress, nowMs: number, f: Fmt, offset = 0,
): WeekView {
  const keys = weekKeys(nowMs, offset, f.timeZone);
  const keySet = new Set(keys);
  const { totals, perDay } = totalsOf(records, keySet, f.timeZone);
  const before = weekKeys(nowMs, offset + 1, f.timeZone);
  const previous = totalsOf(records, new Set(before), f.timeZone).totals;

  const days = keys.map((key) => ({
    key, label: dayLabel(key, f), minutes: round1(perDay.get(key)?.minutes ?? 0), sessions: perDay.get(key)?.sessions ?? 0,
  }));

  // what happened to each word during the week: any step of its history that falls on one of the seven days
  const inWeek = (at: string) => keySet.has(dayKey(Date.parse(at), f.timeZone));
  const groups = GROUPS.map((g) => ({
    ...g,
    words: words.filter((w) => w.state_history.some((h) => h.learning_state === g.state && inWeek(h.at))).map(toWord),
  })).filter((g) => g.words.length > 0);
  const newWords = groups.find((g) => g.state === "DISCOVERED")?.words.length ?? 0;

  // Practise next: training-due words first, then the oldest still only "DISCOVERED". Only words Training can use.
  const usable = words.filter((w) => isTrainable(w, w.user_id ?? ""));
  const due = usable.filter((w) => progress[w.learning_event_id] && progress[w.learning_event_id].due_at <= nowMs)
    .sort((a, b) => progress[a.learning_event_id].due_at - progress[b.learning_event_id].due_at);
  const discovered = usable.filter((w) => w.learning_state === "DISCOVERED").sort((a, b) => firstAt(a) - firstAt(b));
  const next: LearningEvent[] = [];
  for (const w of [...due, ...discovered]) {
    if (next.length >= PRACTISE_NEXT) break;
    if (!next.includes(w)) next.push(w);
  }

  const options = Array.from({ length: WEEKS_BACK }, (_, i) => ({ offset: i, label: i === 0 ? t(f.lang, "digest_this_week") : rangeOf(weekKeys(nowMs, i, f.timeZone), f) }));

  return {
    offset, range: rangeOf(keys, f), options, totals, previous, deltaMinutes: round1(totals.minutes - previous.minutes),
    days, newWords, groups, practiseNext: next.map(toWord), empty: totals.sessions === 0,
  };
}
