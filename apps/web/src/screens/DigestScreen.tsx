// Digest (/digest): a recap of the latest session (section 3.5). The view model is lib/digest.ts.
import type { DigestView } from "../lib/digest.ts";
import { type UiLang, t } from "../lib/i18n.ts";
import { Icon } from "../ui/Icons.tsx";

export interface DigestScreenProps {
  lang: UiLang;
  view: DigestView | null;
  onSelect: (recordId: string) => void;
  onGoTraining: () => void;
  onGoSession: () => void;
}

export function DigestScreen({ lang, view, onSelect, onGoTraining, onGoSession }: DigestScreenProps) {
  if (!view) {
    return (
      <div className="screen digest-screen">
        <h1>{t(lang, "digest_title")}</h1>
        <section className="card empty-state">
          <p>{t(lang, "digest_empty")}</p>
          <a href="/session" className="btn btn-primary" onClick={(e) => { e.preventDefault(); onGoSession(); }}>{t(lang, "digest_go_session")}</a>
        </section>
      </div>
    );
  }
  return (
    <div className="screen digest-screen">
      <h1>{t(lang, "digest_title")}</h1>
      {view.options.length > 1 && (
        <p className="digest-pick">
          <label htmlFor="digest-session">{t(lang, "digest_pick")}</label>{" "}
          <select id="digest-session" value={view.session.record_id} onChange={(e) => onSelect(e.target.value)}>
            {view.options.map((o) => <option key={o.record_id} value={o.record_id}>{o.label}</option>)}
          </select>
        </p>
      )}
      <section className="card digest-head">
        <h2>{view.header}</h2>
        <p className="closing">{t(lang, view.closingKey)}</p>
      </section>
      <div className="digest-groups">
        {view.noWords && <p className="muted">{t(lang, "digest_no_words")}</p>}
        {view.groups.map((g) => (
          <section key={g.state} className={`card digest-group group-${g.state.toLowerCase()}`}>
            <h3>{t(lang, g.titleKey)}</h3>
            <ul className="word-list">
              {g.words.map((w) => (
                <li key={w.id}><span className="word-expr">{w.expression}</span>{w.meaning && <span className="word-meaning"> · {w.meaning}</span>}</li>
              ))}
            </ul>
          </section>
        ))}
      </div>
      {view.practiseNext.length > 0 && (
        <section className="card practise-next">
          <h3>{t(lang, "digest_practise_next")}</h3>
          <ul className="word-chips">
            {view.practiseNext.map((w) => <li key={w.id} className="word-chip">{w.expression}</li>)}
          </ul>
          <a href="/training" className="btn btn-primary" onClick={(e) => { e.preventDefault(); onGoTraining(); }}>{t(lang, "digest_practise_now")} <Icon name="arrow" size={18} /></a>
        </section>
      )}
      <p className="today-line"><strong>{t(lang, "digest_today")}:</strong> {view.today.line}</p>
    </div>
  );
}
