// The digest: a recap of one session (section 3.5). Pure: records, words, training progress and the
// clock in, a view model out. The time zone is injectable so tests are stable.

import type { LearningEvent, LearningState, SessionRecord } from "../contracts.ts";
import { type CopyKey, plural, t } from "./i18n.ts";
import { type Fmt, clock, dayKey, longDay, minutes } from "./format.ts";
import type { Progress } from "./training.ts";

export const DIGEST_OPTIONS = 10;
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

export interface DigestView {
  options: { record_id: string; label: string }[];
  session: SessionRecord;
  header: string;
  groups: DigestGroup[];
  /** true when the session saved no word we can find */
  noWords: boolean;
  today: { sessions: number; minutes: number; hints: number; line: string };
  practiseNext: DigestWord[];
  closingKey: CopyKey;
}

const GROUPS: { state: LearningState; titleKey: CopyKey }[] = [
  { state: "DISCOVERED", titleKey: "digest_new" },
  { state: "ASSISTED", titleKey: "digest_assisted" },
  { state: "REINFORCED", titleKey: "digest_reinforced" },
];

const byEndDesc = (a: SessionRecord, b: SessionRecord) => Date.parse(b.ended_at) - Date.parse(a.ended_at);
const firstAt = (w: LearningEvent) => Date.parse(w.state_history[0]?.at ?? "") || 0;
const toWord = (w: LearningEvent): DigestWord => ({ id: w.learning_event_id, expression: w.expression, meaning: w.meaning });

export function closingKey(hintCount: number): CopyKey {
  if (hintCount <= 0) return "digest_close_none";
  if (hintCount <= 3) return "digest_close_few";
  return "digest_close_many";
}

export function recordLabel(r: SessionRecord, f: Fmt): string {
  const at = Date.parse(r.started_at);
  return `${longDay(at, f)} · ${clock(at, f)}`;
}

/** Returns null when there is no session yet (the empty state). */
export function buildDigest(
  records: SessionRecord[], words: LearningEvent[], progress: Progress, nowMs: number, f: Fmt, selectedId?: string | null,
): DigestView | null {
  const sorted = [...records].sort(byEndDesc);
  if (sorted.length === 0) return null;
  const session = sorted.find((r) => r.record_id === selectedId) ?? sorted[0];
  const byId = new Map(words.map((w) => [w.learning_event_id, w]));

  const start = Date.parse(session.started_at);
  const end = Date.parse(session.ended_at);
  const inWindow = (at: string) => {
    const ms = Date.parse(at);
    return ms >= start && ms <= end;
  };
  const found = session.learning_event_ids.map((id) => byId.get(id)).filter((w): w is LearningEvent => !!w);
  const groups = GROUPS.map((g) => ({
    ...g,
    words: found.filter((w) => w.state_history.some((h) => h.learning_state === g.state && inWindow(h.at))).map(toWord),
  })).filter((g) => g.words.length > 0);

  const today = dayKey(nowMs, f.timeZone);
  const todays = sorted.filter((r) => dayKey(Date.parse(r.ended_at), f.timeZone) === today);
  const tSessions = todays.length;
  const tMinutes = Math.round(todays.reduce((s, r) => s + r.minutes, 0) * 10) / 10;
  const tHints = todays.reduce((s, r) => s + r.hint_count, 0);

  const due = words.filter((w) => progress[w.learning_event_id] && progress[w.learning_event_id].due_at <= nowMs)
    .sort((a, b) => progress[a.learning_event_id].due_at - progress[b.learning_event_id].due_at);
  const discovered = words.filter((w) => w.learning_state === "DISCOVERED").sort((a, b) => firstAt(a) - firstAt(b));
  const next: LearningEvent[] = [];
  for (const w of [...due, ...discovered]) {
    if (next.length >= PRACTISE_NEXT) break;
    if (!next.includes(w)) next.push(w);
  }

  const at = Date.parse(session.started_at);
  const header = [longDay(at, f), clock(at, f), t(f.lang, "min_short", { n: minutes(session.minutes, f) }), plural(f.lang, "hints", session.hint_count)].join(" · ");

  return {
    options: sorted.slice(0, DIGEST_OPTIONS).map((r) => ({ record_id: r.record_id, label: recordLabel(r, f) })),
    session,
    header,
    groups,
    noWords: groups.length === 0,
    today: {
      sessions: tSessions, minutes: tMinutes, hints: tHints,
      line: [plural(f.lang, "sessions", tSessions), t(f.lang, "min_short", { n: minutes(tMinutes, f) }), plural(f.lang, "hints", tHints)].join(" · "),
    },
    practiseNext: next.map(toWord),
    closingKey: closingKey(session.hint_count),
  };
}
