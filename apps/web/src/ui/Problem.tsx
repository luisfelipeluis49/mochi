// A full-screen problem (role="alert"): a microphone problem (section 5) or a backend/session problem
// (section 6). Title and body come from i18n.ts; the backend's own text is never shown.

import type { ReactNode } from "react";
import type { Banner } from "../lib/appState.ts";
import { problemCopyKeys } from "../lib/httpProblem.ts";
import { type CopyKey, type UiLang, t } from "../lib/i18n.ts";
import { Face } from "./Face.tsx";
import type { FaceView } from "../lib/face.ts";

export function problemTitle(lang: UiLang, p: Banner): string {
  return t(lang, p.type === "mic" ? (`mic_${p.kind}_title` as CopyKey) : problemCopyKeys(p.kind).title);
}

export function problemBody(lang: UiLang, p: Banner): string {
  return t(lang, p.type === "mic" ? (`mic_${p.kind}_body` as CopyKey) : problemCopyKeys(p.kind).body);
}

export interface ProblemProps {
  lang: UiLang;
  problem: Banner;
  /** the main action ("Try again" or, for an insecure page, "Open the secure page") */
  onAction?: () => void;
  /** for problem "insecure": the https:// link */
  secureHref?: string;
  /** "Continue without microphone" (mic problems) */
  onContinue?: () => void;
  face?: FaceView;
  children?: ReactNode;
}

export function Problem({ lang, problem, onAction, secureHref, onContinue, face, children }: ProblemProps) {
  const insecure = problem.type === "mic" && problem.kind === "insecure";
  return (
    <main className="problem-screen" role="alert">
      <div className="problem-card">
        {face && <div className="problem-face"><Face lang={lang} view={face} /></div>}
        <h1>{problemTitle(lang, problem)}</h1>
        <p>{problemBody(lang, problem)}</p>
        <div className="problem-actions">
          {insecure && secureHref ? (
            <a className="btn btn-primary" href={secureHref}>{t(lang, "mic_open_secure")}</a>
          ) : onAction ? (
            <button type="button" className="btn btn-primary" onClick={onAction}>{t(lang, "try_again")}</button>
          ) : null}
          {onContinue && (
            <button type="button" className="btn-link" onClick={onContinue}>{t(lang, "mic_continue_without")}</button>
          )}
        </div>
        {children}
      </div>
    </main>
  );
}
