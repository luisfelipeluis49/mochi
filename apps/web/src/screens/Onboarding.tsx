// Onboarding (/welcome): a name only. The languages are pre-filled from the UI language and always differ.
import { type FormEvent, useState } from "react";
import type { Language } from "../contracts.ts";
import { Face } from "../ui/Face.tsx";
import { Banner } from "../ui/Banner.tsx";
import { faceOf, restingFace } from "../lib/face.ts";
import { type UiLang, languageName, t } from "../lib/i18n.ts";
import { problemBody, problemTitle } from "../ui/Problem.tsx";
import type { ProblemKind } from "../lib/httpProblem.ts";

export const NAME_MAX = 40;

/** The trimmed name is 1..40 characters with no control character (the server checks the same). */
export function validName(name: string): boolean {
  const n = name.trim();
  // eslint-disable-next-line no-control-regex
  return n.length >= 1 && Array.from(n).length <= NAME_MAX && !/[\u0000-\u001f\u007f]/.test(n);
}

export function defaultLanguages(ui: UiLang): { speak: Language; learn: Language } {
  return ui === "pt-BR" ? { speak: "pt-BR", learn: "en" } : { speak: "en", learn: "pt-BR" };
}

const other = (l: Language): Language => (l === "en" ? "pt-BR" : "en");

export interface OnboardingProps {
  lang: UiLang;
  note: "profile_lost" | null;
  busy: boolean;
  /** "invalid" = 422; a ProblemKind = network/5xx (the unreachable banner; the name is kept) */
  error: "invalid" | ProblemKind | null;
  onSubmit: (v: { display_name: string; comfortable_language: Language; target_language: Language }) => void;
}

export function Onboarding({ lang, note, busy, error, onSubmit }: OnboardingProps) {
  const [name, setName] = useState("");
  const [langs, setLangs] = useState(() => defaultLanguages(lang));
  const ok = validName(name);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (ok && !busy) onSubmit({ display_name: name.trim(), comfortable_language: langs.speak, target_language: langs.learn });
  };
  const options = (["pt-BR", "en"] as const).map((l) => <option key={l} value={l}>{languageName(lang, l)}</option>);
  return (
    <main className="welcome-screen">
      <form className="welcome-card" onSubmit={submit} noValidate>
        <div className="welcome-face"><Face lang={lang} view={faceOf({ ...restingFace(lang), capturing: true, startedAt: 1 }, 2)} /></div>
        <h1>{t(lang, "welcome_title")}</h1>
        {note === "profile_lost" && <Banner lang={lang} tone="notice">{t(lang, "problem_profile_lost_body")}</Banner>}
        {error && error !== "invalid" && (
          <Banner lang={lang} tone="problem" title={problemTitle(lang, { type: "http", kind: error })}>{problemBody(lang, { type: "http", kind: error })}</Banner>
        )}
        <label className="field-label" htmlFor="welcome-name">{t(lang, "welcome_question")}</label>
        <input
          id="welcome-name" className="field" name="name" type="text" autoComplete="given-name" maxLength={NAME_MAX}
          value={name} onChange={(e) => setName(e.target.value)} aria-invalid={error === "invalid" ? true : undefined}
          aria-describedby={error === "invalid" ? "welcome-name-error" : undefined} placeholder={t(lang, "welcome_name_label")} required
        />
        {error === "invalid" && <p id="welcome-name-error" className="field-error" role="alert">{t(lang, "welcome_name_error")}</p>}
        <p className="welcome-langs">
          <label>
            <span>{t(lang, "welcome_speak")}</span>{" "}
            <select value={langs.speak} onChange={(e) => { const v = e.target.value as Language; setLangs({ speak: v, learn: other(v) }); }}>{options}</select>
          </label>
          <span aria-hidden="true"> · </span>
          <label>
            <span>{t(lang, "welcome_learn")}</span>{" "}
            <select value={langs.learn} onChange={(e) => { const v = e.target.value as Language; setLangs({ learn: v, speak: other(v) }); }}>{options}</select>
          </label>
        </p>
        <button type="submit" className="btn btn-primary btn-block" disabled={!ok || busy}>
          {busy ? t(lang, "welcome_sending") : t(lang, "welcome_submit")}
        </button>
      </form>
    </main>
  );
}
