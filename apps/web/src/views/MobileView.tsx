// =============================================================================
// MobileView.tsx  —  LANGUAGE: TypeScript + JSX (React)
// -----------------------------------------------------------------------------
// A PERSON'S PHONE.  URL: /m?user=ana  (or /m?user=ben)
// "Mochi Mobile": the ANALYTICS page — a place to reflect after talking, not during.
// (The vision slides: "Sem celular. Só conversa." Hints and the game live on Mochi itself.)
// Shows, from top to bottom:
//   1. Start / Stop (the Operator uses these) + the current mode + "Start a game"
//   1b. The LIVE HINT, when this person gets stuck (word, meaning, example). The backend sends it only
//       to the phone of the person it is for (AGENTS.md 6.2 / 9.4); it goes away with the hint on Mochi.
//   2. "Your progress": new words, used with help, recalled in a game, minutes practiced
//   3. "Your last session": the summary card (PROPOSED v0.5)
//   4. "Sessions": minutes per session, as bars
//   5. "My words": one card per saved word, with its path (Hint shown → Used with help → ...)
// It does NOT filter anything: the backend only sends Ana's words and summaries to Ana's phone.
// =============================================================================

import { type RefObject, useState } from "react";
import { LEARNING_STATE_ORDER, type Language, type LearningEvent, type SessionSummary } from "../contracts.ts";
import { barPercent, lastSession, progress, sessionHistory } from "../lib/analytics.ts";
import type { Backend } from "../lib/backend.ts";
import { copyFor, displayName } from "../lib/i18n.ts";
import { type ClientState, hintOptions, liveHint, wordsNewestFirst } from "../lib/store.ts";

// The inputs this screen receives from main.tsx.
interface Props {
  user: string;                        // "ana" or "ben" (the backend roster)
  state: ClientState;                  // all data received from the backend
  now: number;                         // current time (the live hint disappears on time)
  lang: Language;                      // "en" or "pt-BR"
  connected: boolean;                  // is the connection to the backend open?
  backend: RefObject<Backend | null>;  // used to send Start / Stop
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

// --- The whole phone page ------------------------------------------------------
export function MobileView({ user, state, now, lang, connected, backend }: Props) {
  const t = copyFor(lang);
  const [busy, setBusy] = useState(false);              // true while a button request is on its way (buttons are disabled)
  const [error, setError] = useState<string | null>(null); // error message if the backend could not be reached
  const capturing = state.session?.capturing ?? false;  // is Mochi listening right now?
  const hint = liveHint(state, now);                    // the hint for this person, while it is on screen
  const words = wordsNewestFirst(state);                // saved words, newest first
  const p = progress(state);                            // the numbers for "Your progress"
  const last = lastSession(state);                      // the newest session summary, or null
  const history = sessionHistory(state);                // all sessions, oldest first

  // Helper for the buttons: disable them, send the command, show an error if it fails.
  const run = async (fn: (b: Backend) => Promise<void>) => {
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

  // The four numbers at the top. Each: [number, label].
  const tiles: [number, string][] = [
    [p.words, t.statWords],
    [p.usedWithHelp, t.statAssisted],
    [p.recalled, t.statRecalled],
    [p.minutes, t.statMinutes],
  ];

  return (
    <main className="mobile">
      {/* Top bar: name + connection status */}
      <header>
        <h1>Mochi · {displayName(user)}</h1>
        <span className={`dot ${connected ? "on" : "off"}`}>{connected ? t.connected : t.disconnected}</span>
      </header>

      {/* 1. Start / Stop (only one shows at a time) + the current mode */}
      <section className="controls">
        <p className="status">
          {capturing ? t.sessionOn : t.sessionOff}
          {capturing && state.session && <span className="mode-pill">{t.mode}: {t.modeName[state.session.mode]}</span>}
        </p>
        {capturing ? (
          <button className="btn stop" disabled={busy} onClick={() => run((b) => b.stop())}>{t.stop}</button>
        ) : (
          <button className="btn start" disabled={busy} onClick={() => run((b) => b.start())}>{t.start}</button>
        )}
        {/* Start a Describe & Guess round (the Operator's phone). Shown while Mochi listens and no round is
            running. Until the backend can start a round by voice ("Bora jogar!"), this is the only way in the UI. */}
        {capturing && state.activity?.state !== "ACTIVE_ROUND" && (
          <button className="btn secondary" disabled={busy} onClick={() => run((b) => b.activityStart())}>{t.startGame}</button>
        )}
        {error && <p className="error">{error}</p>}
      </section>

      {/* 1b. Live hint: only while there is one (the backend sends this phone only its owner's hints) */}
      {hint && (
        <section className="live-hint" aria-live="polite">
          <div className="tag">{t.liveHint}</div>
          {hintOptions(hint.expression).map((o) => <div key={o} className="expr">{o}</div>)}
          {hint.meaning && <div className="meaning">{hint.meaning}</div>}
          {hint.example && <div className="example">“{hint.example}”</div>}
        </section>
      )}

      {/* 2. Your progress: four numbers */}
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

      {/* 3. Your last session: the summary, or a short message until a session ends */}
      <section>
        <h2>{t.lastSessionTitle}</h2>
        {last ? <SummaryCard s={last} lang={lang} /> : <p className="empty">{t.noSummary}</p>}
      </section>

      {/* 4. Sessions: one bar per session, longest = full width */}
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

      {/* 5. My words: a message if empty, otherwise one card per word */}
      <section>
        <h2>{t.myWords}</h2>
        {words.length === 0 ? <p className="empty">{t.noWords}</p> : (
          <ul className="cards">{words.map((w) => <WordCard key={w.learning_event_id} w={w} lang={lang} />)}</ul>
        )}
      </section>
    </main>
  );
}
