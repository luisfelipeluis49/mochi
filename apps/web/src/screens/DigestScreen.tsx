// Weekly digest (/digest): a wrap-up of everything the person did with Mochi in one week, across all
// of their sessions. The view model is lib/digest.ts.
import type { WeekView } from "../lib/digest.ts";
import { minutes } from "../lib/format.ts";
import { type UiLang, plural, t } from "../lib/i18n.ts";
import { Icon } from "../ui/Icons.tsx";

export interface DigestScreenProps {
  lang: UiLang;
  view: WeekView;
  onSelect: (offset: number) => void;
  onGoSession: () => void;
}

export function DigestScreen({ lang, view, onSelect, onGoSession }: DigestScreenProps) {
  const f = { lang };
  const max = Math.max(1, ...view.days.map((d) => d.minutes));
  const delta = view.deltaMinutes;
  const deltaText = view.previous.sessions === 0 && view.totals.sessions === 0 ? "" :
    delta === 0 ? t(lang, "digest_delta_same") :
    t(lang, delta > 0 ? "digest_delta_up" : "digest_delta_down", { n: minutes(Math.abs(delta), f) });
  return (
    <div className="screen digest-screen">
      <h1>{t(lang, "digest_title")}</h1>
      <p className="digest-pick">
        <label htmlFor="digest-week">{t(lang, "digest_pick")}</label>{" "}
        <select id="digest-week" value={view.offset} onChange={(e) => onSelect(Number(e.target.value))}>
          {view.options.map((o) => <option key={o.offset} value={o.offset}>{o.label}</option>)}
        </select>
      </p>
      <p className="digest-range muted">{view.range}</p>
      {view.empty ? (
        <section className="card empty-state">
          <p>{t(lang, "digest_empty")}</p>
          <a href="/session" className="btn btn-primary" onClick={(e) => { e.preventDefault(); onGoSession(); }}>{t(lang, "digest_go_session")}</a>
        </section>
      ) : (
        <>
          <section className="tiles" aria-label={t(lang, "digest_title")}>
            <div className="tile"><span className="tile-num">{view.totals.sessions}</span><span className="tile-label">{t(lang, "digest_sessions")}</span></div>
            <div className="tile"><span className="tile-num">{minutes(view.totals.minutes, f)}</span><span className="tile-label">{t(lang, "digest_minutes")}</span>{deltaText && <span className="tile-note">{deltaText}</span>}</div>
            <div className="tile"><span className="tile-num">{view.totals.activeDays}/7</span><span className="tile-label">{t(lang, "digest_active_days")}</span></div>
            <div className="tile"><span className="tile-num">{view.newWords}</span><span className="tile-label">{t(lang, "digest_new_words")}</span></div>
          </section>
          <section className="card">
            <h2>{t(lang, "digest_per_day")}</h2>
            <ol className="day-bars">
              {view.days.map((d) => (
                <li key={d.key} className="day-bar">
                  <span className="bar-track"><span className="bar-fill" style={{ height: `${Math.round((d.minutes / max) * 100)}%` }} /></span>
                  <span className="bar-value">{d.minutes > 0 ? minutes(d.minutes, f) : "–"}</span>
                  <span className="bar-label">{d.label}</span>
                </li>
              ))}
            </ol>
            <p className="muted small">{plural(lang, "hints", view.totals.hints)}</p>
          </section>
          <div className="digest-groups">
            {view.groups.length === 0 && <p className="muted">{t(lang, "digest_no_words")}</p>}
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
        </>
      )}
    </div>
  );
}
