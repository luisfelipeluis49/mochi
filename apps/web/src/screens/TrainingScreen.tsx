// Training (/training): a five-minute role-play. Mochi plays a colleague in a new situation like the
// ones where you needed a word or made a mistake in your meetings (D-68). No hints, no second tries;
// at the end Mochi gives kind feedback by voice. The backend builds the scene from your history;
// this screen only starts and stops the session and shows the clock.

import { useEffect, useRef, useState } from "react";
import type { Banner as BannerT, Phase } from "../lib/appState.ts";
import { elapsed } from "../lib/format.ts";
import { type UiLang, t } from "../lib/i18n.ts";
import type { MicProblem } from "../lib/mic.ts";
import { Banner } from "../ui/Banner.tsx";
import { Icon } from "../ui/Icons.tsx";
import { problemBody, problemTitle } from "../ui/Problem.tsx";

/** A training lasts about this long; Mochi starts wrapping up a minute before (backend: 4:00). */
export const TRAINING_MS = 5 * 60_000;
export const WRAP_UP_MS = 4 * 60_000;

export interface TrainingScreenProps {
  lang: UiLang;
  phase: Phase;
  /** the running session is this screen's training */
  training: boolean;
  elapsedMs: number;
  micBlocked: MicProblem | null;
  banner: BannerT | null;
  reachable: boolean;
  hasWords: boolean;
  onStart: () => void;
  onStop: () => void;
  onFixMic: () => void;
  onDismissBanner: () => void;
  onGoAnalytics: () => void;
  onGoSession: () => void;
}

export function TrainingClock({ lang, elapsedMs }: { lang: UiLang; elapsedMs: number }) {
  const wrapping = elapsedMs >= WRAP_UP_MS;
  const shown = Math.min(elapsedMs, TRAINING_MS);
  return (
    <div className="training-clock" aria-live="off">
      <p className="training-time">{`${elapsed(shown)} / ${elapsed(TRAINING_MS)}`}</p>
      <progress max={TRAINING_MS} value={shown} aria-label={t(lang, "training_clock")} />
      {wrapping && <p className="muted small" aria-live="polite">{t(lang, "training_wrapping")}</p>}
    </div>
  );
}

export function TrainingDone({ lang, onGoAnalytics }: { lang: UiLang; onGoAnalytics: () => void }) {
  return (
    <section className="card training-done" aria-live="polite">
      <p className="big-line"><Icon name="check" size={20} /> {t(lang, "training_done_title")}</p>
      <p>{t(lang, "training_done_body")}</p>
      <a href="/analytics" className="link-arrow" onClick={(e) => { e.preventDefault(); onGoAnalytics(); }}>
        {t(lang, "training_see_progress")} <Icon name="arrow" size={18} />
      </a>
    </section>
  );
}

/** True once a running training has ended, until the next one starts. */
function useFinished(running: boolean): boolean {
  const was = useRef(false);
  const [finished, setFinished] = useState(false);
  useEffect(() => {
    if (running) setFinished(false);
    else if (was.current) setFinished(true);
    was.current = running;
  }, [running]);
  return finished;
}

export function TrainingScreen(p: TrainingScreenProps) {
  const { lang } = p;
  const running = p.training && (p.phase === "capturing" || p.phase === "stopping");
  const busyElsewhere = !p.training && (p.phase === "capturing" || p.phase === "stopping");
  const starting = p.phase === "starting";
  const finished = useFinished(running);
  const startDisabled = p.micBlocked !== null || starting || busyElsewhere || !p.reachable;
  return (
    <div className="screen training-screen">
      <h1>{t(lang, "training_title")}</h1>
      {p.banner && (
        <Banner lang={lang} tone="problem" title={problemTitle(lang, p.banner)} onDismiss={p.onDismissBanner}>{problemBody(lang, p.banner)}</Banner>
      )}
      <section className="card training-intro">
        <p>{t(lang, "training_intro")}</p>
        <ul className="training-rules">
          <li>{t(lang, "training_rule_scene")}</li>
          <li>{t(lang, "training_rule_alone")}</li>
          <li>{t(lang, "training_rule_feedback")}</li>
        </ul>
        {!p.hasWords && <p className="muted small">{t(lang, "training_no_words")}</p>}
      </section>
      {running ? (
        <section className="card training-live">
          <TrainingClock lang={lang} elapsedMs={p.elapsedMs} />
          <button type="button" className="btn btn-secondary btn-block btn-tall" onClick={p.onStop} disabled={p.phase === "stopping"}>
            {p.phase === "stopping" ? t(lang, "session_stopping") : t(lang, "training_finish")}
          </button>
        </section>
      ) : (
        <section className="controls">
          <button type="button" className="btn btn-primary btn-block btn-tall" onClick={p.onStart} disabled={startDisabled}>
            {starting ? <><span className="spinner" aria-hidden="true" />{t(lang, "session_waking")}</> : t(lang, "training_start")}
          </button>
          {busyElsewhere && (
            <p className="muted small center">
              {t(lang, "training_busy")}{" "}
              <a href="/session" onClick={(e) => { e.preventDefault(); p.onGoSession(); }}>{t(lang, "training_go_session")}</a>
            </p>
          )}
          {p.micBlocked && (
            <button type="button" className="btn btn-secondary btn-block" onClick={p.onFixMic}><Icon name="mic" size={20} />{t(lang, "mic_fix")}</button>
          )}
        </section>
      )}
      {finished && !running && <TrainingDone lang={lang} onGoAnalytics={p.onGoAnalytics} />}
    </div>
  );
}
