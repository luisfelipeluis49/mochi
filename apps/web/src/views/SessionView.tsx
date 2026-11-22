// =============================================================================
// SessionView.tsx  —  LANGUAGE: TypeScript + JSX (React)
// -----------------------------------------------------------------------------
// THE SESSION TAB (company version).  /m?user=ana
// "Start session" (on the Pi you say "Hi Mochi"; here you tap) and Mochi joins the meeting LIVE
// through this phone: it listens with the phone's mic, speaks through the phone, and the stage in
// the middle behaves like Mochi's own screen (sessionStage.ts ← home.ts):
//   idle → Mochi resting + "Start session"
//   listening → Mochi's face, awake     hint → the word (and its meaning and example)
//   speaking → what Mochi says           choosing → "what do you want to do today?"
// No recording and no game here. The words and the summary go to the Analytics tab.
// =============================================================================

import { type RefObject, useState } from "react";
import type { Language } from "../contracts.ts";
import type { Backend } from "../lib/backend.ts";
import { copyFor, displayName, fitFontSize } from "../lib/i18n.ts";
import { showLive } from "../lib/phoneMic.ts";
import { type Stage, sessionStage } from "../lib/sessionStage.ts";
import { type ClientState, speakerName } from "../lib/store.ts";
import type { PhoneMic } from "../lib/usePhoneMic.ts";
import { Face } from "./HomeView.tsx";

interface Props {
  user: string;
  state: ClientState;
  now: number;
  lang: Language;
  connected: boolean;
  backend: RefObject<Backend | null>;
  mic: PhoneMic;                 // Start session / Stop session with this phone's mic (PhoneApp.tsx)
  micError: string | null;       // what went wrong with the mic, in words
  clearMicError: () => void;
}

/** The middle of the screen: the same states as Mochi's own screen. */
function StageView({ stage, lang, speaker }: { stage: Stage; lang: Language; speaker: string | null }) {
  const t = copyFor(lang);
  switch (stage.kind) {
    case "idle":
      return (
        <div className="stage stage-light">
          <Face awake={false} />
          <p className="stage-title">{t.readyTitle}</p>
          <p className="stage-text">{t.readyText}</p>
        </div>
      );
    case "listening":
      return (
        <div className="stage stage-light">
          {speaker && <span className="speaker-badge">{speaker}</span>}
          <Face awake />
          <p className="stage-label">{t.modeFace[stage.mode]}</p>
        </div>
      );
    case "choosing":
      return (
        <div className="stage stage-light">
          <Face awake small />
          <p className="stage-title">{t.choosing}</p>
          <p className="stage-label">{t.modeName.practice} · {t.modeName.together} · {t.modeName.activity}</p>
        </div>
      );
    case "speaking":
      return (
        <div className="stage stage-light">
          <Face awake small />
          <p className="stage-said">“{stage.text}”</p>
        </div>
      );
    case "hint": {
      const longest = stage.options.reduce((a, b) => (b.length > a.length ? b : a), "");
      const size = fitFontSize(longest, stage.options.length > 1 ? 22 : 34, 64, stage.options.length > 1);
      return (
        <div className="stage stage-dark" aria-live="polite">
          {stage.target && <p className="stage-for">{t.forName(displayName(stage.target))}</p>}
          {stage.options.map((o) => <p key={o} className="stage-word" style={{ fontSize: size }}>{o}</p>)}
          {stage.meaning && <p className="stage-meaning">{stage.meaning}</p>}
          {stage.example && <p className="stage-example">“{stage.example}”</p>}
        </div>
      );
    }
  }
}

export function SessionView({ user, state, now, lang, connected, backend, mic, micError, clearMicError }: Props) {
  const t = copyFor(lang);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const capturing = state.session?.capturing ?? false;
  const stage = sessionStage(state, now, showLive(capturing, mic.here));

  // A button: disable it, send the command, show an error if it fails.
  const run = async (fn: (b: Backend) => Promise<void>) => {
    if (!backend.current) return;
    setBusy(true);
    setError(null);
    clearMicError();
    try {
      await fn(backend.current);
    } catch {
      setError(t.requestFailed);
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="mobile session">
      <header>
        <h1>Mochi · {displayName(user)}</h1>
        <span className={`dot ${connected ? "on" : "off"}`}>{connected ? t.connected : t.disconnected}</span>
      </header>

      {capturing && <p className="session-live"><span className="rec-dot" /> {t.sessionLive}</p>}

      <StageView stage={stage} lang={lang} speaker={speakerName(state)} />

      <section className="controls">
        {capturing ? (
          <button className="btn stop" disabled={busy} onClick={() => run(mic.stopHere)}>{t.stopSession}</button>
        ) : (
          <button className="btn start" disabled={busy} onClick={() => run(mic.startHere)}>{t.startSession}</button>
        )}
        {(error ?? micError) && <p className="error">{error ?? micError}</p>}
        <p className="consent">{t.consentNote}</p>
      </section>
    </main>
  );
}
