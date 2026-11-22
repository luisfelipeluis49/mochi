// The hint under the face: the word, its language and meaning, an example, and a countdown bar.
// The region is aria-live so a screen reader hears each new word.

import type { Hint } from "../contracts.ts";
import { type UiLang, t } from "../lib/i18n.ts";

export interface HintCardProps {
  lang: UiLang;
  hint: Hint | null;
  /** "English · adiar" */
  note: string;
  /** fraction of time left, 1 -> 0 */
  remaining: number;
  /** "Word used" badge with the word, or null */
  used: { word: string } | null;
}

export function HintCard({ lang, hint, note, remaining, used }: HintCardProps) {
  return (
    <section className="hint-region" aria-live="polite" aria-label={t(lang, "hint_region")}>
      {used && (
        <p className="used-badge">{t(lang, "hint_used")} <span lang={hint?.target_language}>{used.word}</span></p>
      )}
      {hint && (
        <div className="hint-card">
          {hint.target_user_id === null && <p className="hint-everyone">{t(lang, "hint_for_everyone")}</p>}
          <p className="hint-word" lang={hint.target_language}>{hint.expression}</p>
          {note && <p className="hint-note">{note}</p>}
          {hint.example && <p className="hint-example" lang={hint.target_language}><i>{hint.example}</i></p>}
          <div className="hint-timer" role="progressbar" aria-label={t(lang, "hint_time_left")} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(remaining * 100)}>
            <span style={{ transform: `scaleX(${remaining.toFixed(3)})` }} />
          </div>
        </div>
      )}
    </section>
  );
}
