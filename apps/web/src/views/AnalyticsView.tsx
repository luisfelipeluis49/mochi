// =============================================================================
// AnalyticsView.tsx  —  LANGUAGE: TypeScript + JSX (React)
// -----------------------------------------------------------------------------
// THE ANALYTICS TAB (company version).  /m/analytics?user=ana
// How the sessions went and which words to learn. No Start/Stop here (that is the Session tab).
// Shows, from top to bottom:
//   0. while this phone's session runs: a note that its analytics come when it ends + a button back
//   1. "Your progress": new words, used with help, recalled in a game, minutes practiced
//   2. "Your last session": the summary card (strengths, to review, new expressions, next step)
//   3. "Sessions": minutes per session, as bars
//   4. "Words to learn": one card per saved word, with its path (Hint shown → Used with help → ...)
// It does NOT filter anything: the backend only sends Ana's words and summaries to Ana's phone.
// =============================================================================

import { LEARNING_STATE_ORDER, type Language, type LearningEvent, type SessionSummary } from "../contracts.ts";
import { barPercent, lastSession, progress, sessionHistory } from "../lib/analytics.ts";
import { copyFor, displayName } from "../lib/i18n.ts";
import { type ClientState, wordsNewestFirst } from "../lib/store.ts";

// The inputs this screen receives from PhoneApp.tsx.
interface Props {
  user: string;                  // "ana" or "ben" (the backend roster)
  state: ClientState;            // all data received from the backend
  lang: Language;                // "en" or "pt-BR"
  connected: boolean;            // is the connection to the backend open?
  live: boolean;                 // is THIS phone's session running right now?
  onBackToSession: () => void;   // the button in the "session in progress" note
}

/** A date as short text in the page's language, e.g. "21 nov" or "Nov 21". */
function shortDate(iso: string, lang: Language): string {
  return new Date(iso).toLocaleDateString(lang, { day: "numeric", month: "short" });
}

// --- One word card in "My words" ---------------------------------------------
function WordCard({ w, lang }: { w: LearningEvent; lang: Language }) {
  const t = copyFor(lang);
  // Which steps has this word already reached? (taken from its history)
  const reached = new Set(w.state_history.map((h) => h.learning_state));
  return (
    // data-state lets the CSS color the label (pink for "Hint shown" / "Used with help")
    <li className="card" data-word={w.expression} data-state={w.learning_state}>
      <div className="card-top">
        <span className="expr">{w.expression}</span>                     {/* e.g. "umbrella" */}
        <span className="label">{t.stateLabel[w.learning_state]}</span> {/* e.g. "Recalled in a game" */}
      </div>
      {w.meaning && <div className="meaning">{w.meaning}</div>}         {/* e.g. "guarda-chuva" */}
      {/* The path: the 4 steps as little pills; reached steps are pink, the current one is dark */}
      <ol className="path" aria-label="state path">
        {LEARNING_STATE_ORDER.map((s) => (
          <li key={s} className={`${reached.has(s) ? "done" : ""} ${s === w.learning_state ? "current" : ""}`}>
            {t.stateLabel[s]}
          </li>
        ))}
      </ol>
      <div className="next">{t.nextStep[w.learning_state]}</div>         {/* a fixed tip for the next step */}
    </li>
  );
}

// --- "Your last session": the summary card from the Mochi Mobile slide (PROPOSED v0.5) ---
function SummaryCard({ s, lang }: { s: SessionSummary; lang: Language }) {
  const t = copyFor(lang);
  // One box per part of the summary; a part with nothing in it is not drawn.
  const parts: [string, string[]][] = [
    [t.strengths, s.strengths],
    [t.toReview, s.to_review],
    [t.newExpressions, s.new_expressions],
    [t.nextStepTitle, s.next_step ? [s.next_step] : []],
  ];
  return (
    <div className="summary">
      <div className="summary-meta">{displayName(s.user_id)} · {t.languageName[s.target_language]} · {shortDate(s.created_at, lang)}</div>
      <div className="summary-minutes">{s.speaking_minutes} min</div>
      <div className="summary-minutes-label">{t.minutesLabel}</div>
      {parts.filter(([, items]) => items.length > 0).map(([title, items]) => (
        <div key={title} className="summary-box">
          <div className="summary-box-title">{title}</div>
          <div>{items.join(" · ")}</div>
        </div>
      ))}
    </div>
  );
}

// --- The whole Analytics tab ---------------------------------------------------
export function AnalyticsView({ user, state, lang, connected, live, onBackToSession }: Props) {
  const t = copyFor(lang);
  const words = wordsNewestFirst(state);                // saved words, newest first
  const p = progress(state);                            // the numbers for "Your progress"
  const last = lastSession(state);                      // the newest session summary, or null
  const history = sessionHistory(state);                // all sessions, oldest first

  // The four numbers at the top. Each: [number, label].
  const tiles: [number, string][] = [
    [p.words, t.statWords],
    [p.usedWithHelp, t.statAssisted],
    [p.recalled, t.statRecalled],
    [p.minutes, t.statMinutes],
  ];

  return (
    <main className="mobile analytics">
      {/* Top bar: name + connection status */}
      <header>
        <h1>{t.analyticsTitle} · {displayName(user)}</h1>
        <span className={`dot ${connected ? "on" : "off"}`}>{connected ? t.connected : t.disconnected}</span>
      </header>

      {/* 0. A session is running on this phone: its analytics come when it ends */}
      {live && (
        <section className="record-notice">
          <p>{t.analyticsNotice}</p>
          <button type="button" className="btn secondary" onClick={onBackToSession}>{t.backToSession}</button>
        </section>
      )}

      {/* 1. Your progress: four numbers */}
      <section>
        <h2>{t.progressTitle}</h2>
        <div className="stats">
          {tiles.map(([n, label]) => (
            <div key={label} className="stat">
              <div className="stat-n">{n}</div>
              <div className="stat-label">{label}</div>
            </div>
          ))}
        </div>
      </section>

      {/* 2. Your last session: the summary, or a short message until a session ends */}
      <section>
        <h2>{t.lastSessionTitle}</h2>
        {last ? <SummaryCard s={last} lang={lang} /> : <p className="empty">{t.noSummary}</p>}
      </section>

      {/* 3. Sessions: one bar per session, longest = full width */}
      {history.length > 0 && (
        <section>
          <h2>{t.sessionsTitle}</h2>
          <ul className="bars">
            {history.map((s) => (
              <li key={s.summary_id}>
                <span className="bar-date">{shortDate(s.created_at, lang)}</span>
                <span className="bar-track"><span className="bar-fill" style={{ width: `${barPercent(s.speaking_minutes, history)}%` }} /></span>
                <span className="bar-min">{s.speaking_minutes} min</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* 4. Words to learn: a message if empty, otherwise one card per word */}
      <section>
        <h2>{t.wordsToLearn}</h2>
        {words.length === 0 ? <p className="empty">{t.noWords}</p> : (
          <ul className="cards">{words.map((w) => <WordCard key={w.learning_event_id} w={w} lang={lang} />)}</ul>
        )}
      </section>
    </main>
  );
}
