// The microphone gate while the browser's question is open (section 5).
import { Face } from "../ui/Face.tsx";
import { faceOf, restingFace } from "../lib/face.ts";
import { type UiLang, t } from "../lib/i18n.ts";
import { Icon } from "../ui/Icons.tsx";

export function MicGate({ lang, slow, onAllow }: { lang: UiLang; slow: boolean; onAllow: () => void }) {
  const face = faceOf({ ...restingFace(lang), starting: true }, 0);
  return (
    <main className="gate-screen">
      <div className="gate-card">
        <div className="gate-face"><Face lang={lang} view={face} /></div>
        <h1><Icon name="mic" /> {t(lang, "mic_wait_title")}</h1>
        <p>{t(lang, "mic_wait_body")}</p>
        {slow && <button type="button" className="btn btn-primary" onClick={onAllow}>{t(lang, "mic_allow")}</button>}
      </div>
    </main>
  );
}

/** A plain loading screen (while the permission query or the identity check runs). */
export function Loading({ lang }: { lang: UiLang }) {
  return (
    <main className="gate-screen" aria-busy="true">
      <div className="gate-card">
        <div className="gate-face"><Face lang={lang} view={faceOf(restingFace(lang), 0)} /></div>
        <p className="muted">{t(lang, "loading")}</p>
      </div>
    </main>
  );
}
