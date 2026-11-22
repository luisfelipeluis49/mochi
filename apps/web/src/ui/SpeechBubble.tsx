// What Mochi said aloud (agent.speak.requested). aria-live so it is read out.
import type { Speak } from "../contracts.ts";
import { type UiLang, t } from "../lib/i18n.ts";

export function SpeechBubble({ lang, speak, speaking }: { lang: UiLang; speak: Speak | null; speaking: boolean }) {
  return (
    <div className="speech-region" aria-live="polite">
      {speak && (
        <figure className={`speech ${speaking ? "is-speaking" : ""}`}>
          <figcaption className="visually-hidden">{t(lang, "session_said")}</figcaption>
          <blockquote lang={speak.language}>{speak.text}</blockquote>
        </figure>
      )}
    </div>
  );
}
