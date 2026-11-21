// =============================================================================
// InsightsView.tsx  —  LANGUAGE: TypeScript + JSX (React)
// -----------------------------------------------------------------------------
// "MINHAS CONVERSAS": a person's own report of their real conversations
// (work meetings, calls, chats) that Mochi listened to.   URL: /me?user=tasnim
// Shows, from top to bottom:
//   1. Four totals: conversations, minutes speaking, words you needed, mistakes noticed
//   2. "Mistakes per 10 minutes": one bar per conversation, and the improvement in %
//   3. "Practice next": up to 3 things to work on
//   4. "Your most common mistakes": grouped by topic, with "You said → Better"
//   5. "Words you didn't know": what you needed, what it means, what you said instead
//   6. "Conversations": the list, newest first
// The numbers come from insights.ts; the analysis itself comes from the backend
// (conversation.report.created, PROPOSED v0.5). This page decides nothing.
// =============================================================================

import type { ConversationReport, Language } from "../contracts.ts";
import { copyFor, displayName } from "../lib/i18n.ts";
import {
  conversations, improvementPercent, mistakeCount, mistakesPer10Min, practiceNext, topMistakes, totals,
  trendBarPercent, wordsNeeded,
} from "../lib/insights.ts";
import type { ClientState } from "../lib/store.ts";

interface Props {
  user: string;          // whose page this is, e.g. "tasnim"
  state: ClientState;    // everything received (this page reads state.reports)
  lang: Language;        // "en" or "pt-BR"
  connected: boolean;    // is the connection to the backend open?
}

/** "18 nov" / "Nov 18" */
function shortDate(iso: string, lang: Language): string {
  return new Date(iso).toLocaleDateString(lang, { day: "numeric", month: "short" });
}

export function InsightsView({ user, state, lang, connected }: Props) {
  const t = copyFor(lang);
  const list = conversations(state);               // oldest first
  const sum = totals(list);
  const change = improvementPercent(list);         // negative = fewer mistakes = better
  const mistakes = topMistakes(list);
  const words = wordsNeeded(list);
  const practice = practiceNext(list);
  const latest: ConversationReport | undefined = list.at(-1);

  // The four numbers at the top: [number, label]
  const tiles: [number, string][] = [
    [sum.conversations, t.statConversations],
    [sum.minutes, t.statSpeaking],
    [sum.unknownWords, t.statUnknown],
    [sum.mistakes, t.statMistakes],
  ];

  return (
    <main className="mobile insights">
      <header>
        <div>
          <h1>{t.insightsTitle}</h1>
          <p className="subtitle">{displayName(user)} · {t.insightsSubtitle}</p>
        </div>
        <span className={`dot ${connected ? "on" : "off"}`}>{connected ? t.connected : t.disconnected}</span>
      </header>

      {list.length === 0 ? (
        <p className="empty">{t.noReports}</p>
      ) : (
        <>
          {/* 1. Totals */}
          <section className="stats">
            {tiles.map(([n, label]) => (
              <div key={label} className="stat">
                <div className="stat-n">{n}</div>
                <div className="stat-label">{label}</div>
              </div>
            ))}
          </section>

          {/* 2. Trend: mistakes per 10 minutes, one bar per conversation (oldest at the top) */}
          <section>
            <h2>{t.trendTitle}</h2>
            {change !== null && change !== 0 && (
              <p className={`trend-note ${change < 0 ? "good" : "bad"}`}>
                {change < 0 ? t.improved(-change) : t.worse(change)}
              </p>
            )}
            <ul className="bars">
              {list.map((r) => (
                <li key={r.report_id}>
                  <span className="bar-date">{shortDate(r.started_at, lang)}</span>
                  <span className="bar-track"><span className="bar-fill" style={{ width: `${trendBarPercent(mistakesPer10Min(r), list)}%` }} /></span>
                  <span className="bar-min">{mistakesPer10Min(r).toLocaleString(lang)}</span>
                </li>
              ))}
            </ul>
          </section>

          {/* 3. Practice next (and what is going well) */}
          {practice.length > 0 && (
            <section className="practice">
              <h2>{t.practiceTitle}</h2>
              <ol>{practice.map((p) => <li key={p}>{p}</li>)}</ol>
              {latest && latest.strengths.length > 0 && (
                <p className="going-well"><b>{t.strengthsTitle}:</b> {latest.strengths.join(" · ")}</p>
              )}
            </section>
          )}

          {/* 4. Most common mistakes, with one real example each */}
          <section>
            <h2>{t.commonMistakes}</h2>
            <ul className="cards">
              {mistakes.map((m) => (
                <li key={m.topic} className="card mistake">
                  <div className="card-top">
                    <span className="expr">{m.topic}</span>
                    <span className="label">{t.timesIn(m.count, m.conversations)}</span>
                  </div>
                  <span className="kind-pill">{t.kindName[m.kind]}</span>
                  <div className="said"><span>{t.youSaid}</span> <s>{m.example.said}</s></div>
                  <div className="better"><span>{t.better}</span> {m.example.better}</div>
                </li>
              ))}
            </ul>
          </section>

          {/* 5. Words you didn't know */}
          <section>
            <h2>{t.wordsTitle}</h2>
            <ul className="cards">
              {words.map((w) => (
                <li key={w.expression} className="card word-needed">
                  <div className="card-top">
                    <span className="expr">{w.expression}</span>
                    <span className="label">{t.timesNeeded(w.times)}</span>
                  </div>
                  {w.meaning && <div className="meaning">{w.meaning}</div>}
                  {w.saidInstead && w.saidInstead !== w.meaning && <div className="next">{t.saidInstead(w.saidInstead)}</div>}
                </li>
              ))}
            </ul>
          </section>

          {/* 6. The conversations, newest first */}
          <section>
            <h2>{t.conversationsTitle}</h2>
            <ul className="conv-list">
              {[...list].reverse().map((r) => (
                <li key={r.report_id}>
                  <div className="conv-top">
                    <span className="conv-title">{r.title}</span>
                    <span className="kind-pill">{t.contextName[r.context]}</span>
                  </div>
                  <div className="conv-meta">
                    {shortDate(r.started_at, lang)} · {t.convLine(r.speaking_minutes, mistakeCount(r), r.unknown_words.length)}
                  </div>
                </li>
              ))}
            </ul>
          </section>
        </>
      )}

      <p className="consent">{t.consentNote}</p>
    </main>
  );
}
