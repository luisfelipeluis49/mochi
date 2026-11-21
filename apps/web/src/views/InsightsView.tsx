// =============================================================================
// InsightsView.tsx  —  LANGUAGE: TypeScript + JSX (React)
// -----------------------------------------------------------------------------
// "MINHAS CONVERSAS": ONE person's own page, on their own phone.   URL: /me?user=tasnim
//
// How it is used:
//   1. Press "Record a conversation" when a conversation starts (with Matheus, a client, anyone).
//      It records with THIS phone's microphone (usePhoneMic.ts); the Pi must be off.
//   2. Press "Stop and save" when it ends. That recording becomes ONE entry in the history.
//      An hour later, another recording with someone else becomes ANOTHER entry.
//   3. Tap an entry to see ONLY WHAT YOU SAID: your sentences, the better version when there was
//      a mistake, and the words you needed. What the other person said is never shown or saved.
//
// Main view, from top to bottom:
//   recording card · totals · mistakes per 10 minutes · practice next · most common mistakes ·
//   words you didn't know · conversation history
// The numbers come from insights.ts; the analysis comes from the backend
// (conversation.report.created, PROPOSED v0.5). This page decides nothing.
// =============================================================================

import { type RefObject, useEffect, useState } from "react";
import type { ConversationReport, Language } from "../contracts.ts";
import type { Backend } from "../lib/backend.ts";
import { copyFor, displayName } from "../lib/i18n.ts";
import { usePhoneMic } from "../lib/usePhoneMic.ts";
import {
  conversations, improvementPercent, mistakeCount, mistakesPer10Min, practiceNext, topMistakes, totals,
  trendBarPercent, wordsNeeded,
} from "../lib/insights.ts";
import type { ClientState } from "../lib/store.ts";

interface Props {
  user: string;                        // whose page this is, e.g. "tasnim"
  state: ClientState;                  // everything received (this page reads state.reports and state.session)
  now: number;                         // current time, for the recording timer
  lang: Language;                      // "en" or "pt-BR"
  connected: boolean;                  // is the connection to the backend open?
  backend: RefObject<Backend | null>;  // used to send Record (start) and Stop
}

/** "18 nov" / "Nov 18" */
function shortDate(iso: string, lang: Language): string {
  return new Date(iso).toLocaleDateString(lang, { day: "numeric", month: "short" });
}

/** "14:05" */
function clockTime(iso: string, lang: Language): string {
  return new Date(iso).toLocaleTimeString(lang, { hour: "2-digit", minute: "2-digit" });
}

/** "03:27" from milliseconds */
function stopwatch(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

/** The name shown for a conversation: its title, or "Conversation at 14:05" when it has none. */
function conversationName(r: ConversationReport, lang: Language): string {
  return r.title || copyFor(lang).untitled(clockTime(r.started_at, lang));
}

// --- The recording card: "Record a conversation" / "Recording 03:27 · Stop and save" -----------
function RecordCard({ state, now, lang, backend }: Pick<Props, "state" | "now" | "lang" | "backend">) {
  const t = copyFor(lang);
  const recording = state.session?.capturing ?? false;
  const [startedAt, setStartedAt] = useState<number | null>(null); // when this phone saw the recording start
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Record uses THIS phone's microphone, not the Pi's (see usePhoneMic.ts).
  const { startHere, stopHere } = usePhoneMic(recording, (problem) => setError(t.micProblem[problem]));

  // Start the timer when the recording starts (from this phone or from the device), clear it when it stops.
  useEffect(() => {
    setStartedAt(recording ? Date.now() : null);
  }, [recording]);

  const send = async (fn: (b: Backend) => Promise<void>) => {
    if (!backend.current) return;
    setBusy(true);
    setError(null);
    try {
      await fn(backend.current);
    } catch {
      setError(t.requestFailed);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className={`record ${recording ? "on" : ""}`}>
      {recording ? (
        <>
          <div className="record-status"><span className="rec-dot" /> {t.recording} · {stopwatch(startedAt ? now - startedAt : 0)}</div>
          <p className="record-hint">{t.onlyYou}</p>
          {/* Notice: the numbers of this session show on the analytics page (/m), same person and options */}
          <p className="record-notice">
            {t.analyticsNotice} <a href={`/m${window.location.search}`}>{t.openAnalytics}</a>
          </p>
          <button className="btn stop" disabled={busy} onClick={() => send(stopHere)}>{t.stopRecording}</button>
        </>
      ) : (
        <>
          <button className="btn record-btn" disabled={busy} onClick={() => send(startHere)}>● {t.recordTitle}</button>
          <p className="record-hint">{t.recordHint}</p>
        </>
      )}
      {error && <p className="error">{error}</p>}
    </section>
  );
}

// --- One conversation, opened: only what YOU said ----------------------------------------------
function ConversationDetail({ r, lang, onBack }: { r: ConversationReport; lang: Language; onBack: () => void }) {
  const t = copyFor(lang);
  return (
    <>
      <button className="back" onClick={onBack}>{t.backToAll}</button>
      <section>
        <h1>{conversationName(r, lang)}</h1>
        <p className="subtitle">
          {shortDate(r.started_at, lang)} · {clockTime(r.started_at, lang)}–{clockTime(r.ended_at, lang)} · {t.contextName[r.context]}
        </p>
        <p className="conv-meta">{t.convLine(r.speaking_minutes, mistakeCount(r), r.unknown_words.length)}</p>
      </section>

      {/* What you said, in order. A sentence with a mistake shows the better version under it. */}
      <section>
        <h2>{t.whatYouSaid}</h2>
        <p className="only-you">{t.onlyYou}</p>
        <ol className="sentences">
          {r.my_sentences.map((m, i) => (
            <li key={i} className={m.better ? "has-fix" : ""}>
              <span className="at">{clockTime(m.at, lang)}</span>
              <div>
                <div className="said-line">{m.better ? <s>{m.text}</s> : m.text}</div>
                {m.better && (
                  <div className="better-line">
                    {m.topic && <span className="kind-pill">{m.topic}</span>} {m.better}
                  </div>
                )}
              </div>
            </li>
          ))}
        </ol>
      </section>

      {r.unknown_words.length > 0 && (
        <section>
          <h2>{t.wordsThisConv}</h2>
          <ul className="cards">
            {r.unknown_words.map((w) => (
              <li key={w.expression} className="card word-needed">
                <div className="card-top">
                  <span className="expr">{w.expression}</span>
                  <span className="label">{t.timesNeeded(w.times)}</span>
                </div>
                {w.meaning && <div className="meaning">{w.meaning}</div>}
                {w.said_instead && w.said_instead !== w.meaning && <div className="next">{t.saidInstead(w.said_instead)}</div>}
              </li>
            ))}
          </ul>
        </section>
      )}

      {(r.strengths.length > 0 || r.focus_next.length > 0) && (
        <section className="practice">
          {r.focus_next.length > 0 && (<><h2>{t.practiceTitle}</h2><ol>{r.focus_next.map((p) => <li key={p}>{p}</li>)}</ol></>)}
          {r.strengths.length > 0 && <p className="going-well"><b>{t.strengthsTitle}:</b> {r.strengths.join(" · ")}</p>}
        </section>
      )}
    </>
  );
}

// --- The whole page -----------------------------------------------------------------------------
export function InsightsView({ user, state, now, lang, connected, backend }: Props) {
  const t = copyFor(lang);
  const [openId, setOpenId] = useState<string | null>(null); // the conversation being read, or null
  const list = conversations(state);                          // oldest first
  const open = openId ? state.reports[openId] : undefined;

  // Opening a conversation (or going back) starts at the top of the page.
  useEffect(() => { window.scrollTo(0, 0); }, [openId]);

  const header = (
    <header>
      <div>
        <h1>{t.insightsTitle}</h1>
        <p className="subtitle">{displayName(user)} · {t.insightsSubtitle}</p>
      </div>
      <span className={`dot ${connected ? "on" : "off"}`}>{connected ? t.connected : t.disconnected}</span>
    </header>
  );

  if (open) {
    return (
      <main className="mobile insights">
        <ConversationDetail r={open} lang={lang} onBack={() => setOpenId(null)} />
      </main>
    );
  }

  const sum = totals(list);
  const change = improvementPercent(list);   // negative = fewer mistakes = better
  const mistakes = topMistakes(list);
  const words = wordsNeeded(list);
  const practice = practiceNext(list);
  const latest = list.at(-1);
  const tiles: [number, string][] = [
    [sum.conversations, t.statConversations],
    [sum.minutes, t.statSpeaking],
    [sum.unknownWords, t.statUnknown],
    [sum.mistakes, t.statMistakes],
  ];

  return (
    <main className="mobile insights">
      {header}

      {/* Record → Stop = one conversation in the history */}
      <RecordCard state={state} now={now} lang={lang} backend={backend} />

      {list.length === 0 ? (
        <p className="empty">{t.noReports}</p>
      ) : (
        <>
          {/* Conversation history, newest first: tap one to see what you said */}
          <section>
            <h2>{t.historyTitle}</h2>
            <ul className="conv-list">
              {[...list].reverse().map((r) => (
                <li key={r.report_id}>
                  <button className="conv-open" onClick={() => setOpenId(r.report_id)}>
                    <div className="conv-top">
                      <span className="conv-title">{conversationName(r, lang)}</span>
                      <span className="kind-pill">{t.contextName[r.context]}</span>
                    </div>
                    <div className="conv-meta">
                      {shortDate(r.started_at, lang)} · {clockTime(r.started_at, lang)} · {t.convLine(r.speaking_minutes, mistakeCount(r), r.unknown_words.length)}
                    </div>
                    {r.my_sentences[0] && <div className="conv-preview">“{r.my_sentences[0].text}”</div>}
                  </button>
                </li>
              ))}
            </ul>
          </section>

          {/* All conversations together */}
          <section className="stats">
            {tiles.map(([n, label]) => (
              <div key={label} className="stat">
                <div className="stat-n">{n}</div>
                <div className="stat-label">{label}</div>
              </div>
            ))}
          </section>

          <section>
            <h2>{t.trendTitle}</h2>
            {change !== null && change !== 0 && (
              <p className={`trend-note ${change < 0 ? "good" : "bad"}`}>{change < 0 ? t.improved(-change) : t.worse(change)}</p>
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

          {practice.length > 0 && (
            <section className="practice">
              <h2>{t.practiceTitle}</h2>
              <ol>{practice.map((p) => <li key={p}>{p}</li>)}</ol>
              {latest && latest.strengths.length > 0 && <p className="going-well"><b>{t.strengthsTitle}:</b> {latest.strengths.join(" · ")}</p>}
            </section>
          )}

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
        </>
      )}

      <p className="consent">{t.consentNote}</p>
    </main>
  );
}
