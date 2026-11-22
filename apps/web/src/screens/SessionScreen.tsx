// Session (/session): Mochi Home in the browser (section 3.2). Start runs the C6 order; Mochi hears
// through this browser's microphone, shows hints under its face and speaks through the Agora audio.
// No game (the secret word goes to the device only) and no transcript.

import type { Hint, Speak, User } from "../contracts.ts";
import type { Banner as BannerT, Phase, SavedCard } from "../lib/appState.ts";
import type { FaceView } from "../lib/face.ts";
import { elapsed, minutes } from "../lib/format.ts";
import { type UiLang, plural, t } from "../lib/i18n.ts";
import type { MicProblem } from "../lib/mic.ts";
import { SESSION_MODES, type SessionMode } from "../lib/mode.ts";
import { Banner } from "../ui/Banner.tsx";
import { Face } from "../ui/Face.tsx";
import { HintCard } from "../ui/HintCard.tsx";
import { problemBody, problemTitle } from "../ui/Problem.tsx";
import { SpeechBubble } from "../ui/SpeechBubble.tsx";
import { type ChipState, StatusChip } from "../ui/StatusChip.tsx";
import { Icon } from "../ui/Icons.tsx";

export interface SessionScreenProps {
  lang: UiLang;
  user: User;
  face: FaceView;
  level: number;
  hint: Hint | null;
  hintRemaining: number;
  speak: Speak | null;
  speaking: boolean;
  sessionHints: Hint[];
  phase: Phase;
  elapsedMs: number;
  chip: ChipState;
  micBlocked: MicProblem | null;
  banner: BannerT | null;
  saved: SavedCard | null;
  rejoin: boolean;
  volume: number;
  /** the public line of a game round, if one is running (never a word) */
  activityInstruction: string | null;
  /** the backend can be reached (Start needs it) */
  reachable: boolean;
  onStart: () => void;
  onStop: () => void;
  onRejoin: () => void;
  onFixMic: () => void;
  onVolume: (v: number) => void;
  onDismissBanner: () => void;
  onDismissSaved: () => void;
  onGoDigest: () => void;
  /** how this session listens (D-46): chosen before Start */
  mode: SessionMode;
  onMode: (m: SessionMode) => void;
}

export function SessionScreen(p: SessionScreenProps) {
  const { lang } = p;
  const capturing = p.phase === "capturing" || p.phase === "stopping";
  const starting = p.phase === "starting";
  const startDisabled = p.micBlocked !== null || starting || p.rejoin || !p.reachable;
  return (
    <div className="screen session-screen">
      <h1 className="visually-hidden">{t(lang, "session_title")}</h1>
      {p.banner && (
        <Banner lang={lang} tone="problem" title={problemTitle(lang, p.banner)} onDismiss={p.onDismissBanner}>{problemBody(lang, p.banner)}</Banner>
      )}
      {p.rejoin && (
        <Banner lang={lang} tone="notice" actions={<>
          <button type="button" className="btn btn-primary btn-small" onClick={p.onRejoin}>{t(lang, "session_listen_again")}</button>
          <button type="button" className="btn btn-secondary btn-small" onClick={p.onStop}>{t(lang, "session_stop_short")}</button>
        </>}>{t(lang, "session_reload_banner")}</Banner>
      )}
      <div className="session-grid">
        <div className="session-main">
          <div className="status-row">
            <StatusChip lang={lang} state={p.chip} />
            {capturing && <span className="elapsed" aria-label={t(lang, "session_elapsed")}>{elapsed(p.elapsedMs)}</span>}
          </div>
          <div className="face-wrap"><Face lang={lang} view={p.face} level={p.level} /></div>
          <HintCard lang={lang} hint={p.hint} note={p.face.note} remaining={p.hintRemaining} used={p.face.badge ? { word: p.face.badge.word } : null} />
          {p.activityInstruction && <p className="activity-line"><strong>{t(lang, "session_game")}:</strong> {p.activityInstruction}</p>}
          <SpeechBubble lang={lang} speak={capturing ? p.speak : null} speaking={p.speaking} />
        </div>
        <aside className="session-side">
          <div className="controls">
            {capturing ? (
              <button type="button" className="btn btn-secondary btn-block btn-tall" onClick={p.onStop} disabled={p.phase === "stopping"}>
                {p.phase === "stopping" ? t(lang, "session_stopping") : t(lang, "session_stop")}
              </button>
            ) : (
              <>
                <fieldset className="mode-choice" disabled={starting}>
                  <legend>{t(lang, "session_mode_label")}</legend>
                  {SESSION_MODES.map((m) => (
                    <label key={m} className={`mode-option${p.mode === m ? " is-selected" : ""}`}>
                      <input type="radio" name="session-mode" value={m} checked={p.mode === m} onChange={() => p.onMode(m)} />
                      <span className="mode-name">{t(lang, `session_mode_${m}`)}</span>
                      <span className="mode-note muted small">{t(lang, `session_mode_${m}_note`)}</span>
                    </label>
                  ))}
                </fieldset>
                <button type="button" className="btn btn-primary btn-block btn-tall" onClick={p.onStart} disabled={startDisabled} aria-describedby="start-line">
                  {starting ? <><span className="spinner" aria-hidden="true" />{t(lang, "session_waking")}</> : t(lang, "session_start")}
                </button>
                <p id="start-line" className="muted small center">
                  {p.micBlocked ? t(lang, "session_mic_needed", { reason: t(lang, `mic_${p.micBlocked}_title`) }) : t(lang, "session_start_line")}
                </p>
                {p.micBlocked && (
                  <button type="button" className="btn btn-secondary btn-block" onClick={p.onFixMic}><Icon name="mic" size={20} />{t(lang, "mic_fix")}</button>
                )}
              </>
            )}
          </div>
          {p.saved && !capturing && (
            <section className="card saved-card" aria-live="polite">
              <p><Icon name="check" size={20} /> <strong>{t(lang, "session_saved")}</strong> · {t(lang, "min_short", { n: minutes(p.saved.minutes, { lang }) })} · {plural(lang, "hints", p.saved.hints)}</p>
              <a href="/digest" className="link-arrow" onClick={(e) => { e.preventDefault(); p.onGoDigest(); }}>{t(lang, "session_see_digest")} <Icon name="arrow" size={18} /></a>
            </section>
          )}
          <section className="card this-session">
            <h2>{t(lang, "session_this_session")}</h2>
            {p.sessionHints.length === 0 ? (
              <p className="muted small">{t(lang, "session_no_hints")}</p>
            ) : (
              <ul className="word-chips">
                {p.sessionHints.map((h) => <li key={h.hint_id} className="word-chip" lang={h.target_language}>{h.expression}</li>)}
              </ul>
            )}
          </section>
          <section className="card volume">
            <label htmlFor="voice-volume">{t(lang, "session_volume")}</label>
            <div className="volume-row">
              <Icon name="speaker" size={20} />
              <input id="voice-volume" type="range" min={0} max={100} step={5} value={p.volume} onChange={(e) => p.onVolume(Number(e.target.value))} />
              <output htmlFor="voice-volume">{p.volume}</output>
            </div>
          </section>
        </aside>
      </div>
    </div>
  );
}
