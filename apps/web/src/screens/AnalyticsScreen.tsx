// Analytics (/analytics): tiles, minutes per session, where the words are, and the word list with
// each word's state path (section 3.6). The view model is lib/analytics.ts.
import { useState } from "react";
import { LEARNING_STATES, type LearningState } from "../contracts.ts";
import { type AnalyticsView, statePath } from "../lib/analytics.ts";
import { type Fmt, minutes, percent, shortDay } from "../lib/format.ts";
import { type UiLang, languageName, t } from "../lib/i18n.ts";

const STATE_KEY = {
  DISCOVERED: "state_DISCOVERED", ASSISTED: "state_ASSISTED", REINFORCED: "state_REINFORCED", USED_INDEPENDENTLY: "state_USED_INDEPENDENTLY",
} as const;

function Tile({ label, value, note, accent }: { label: string; value: string; note?: string; accent?: boolean }) {
  return (
    <div className={`tile ${accent ? "tile-accent" : ""}`}>
      <span className="tile-value">{value}</span>
      <span className="tile-label">{label}</span>
      {note && <span className="tile-note">{note}</span>}
    </div>
  );
}

function MinutesChart({ lang, view, f }: { lang: UiLang; view: AnalyticsView; f: Fmt }) {
  const max = Math.max(1, ...view.bars.map((b) => b.minutes));
  const W = 320, H = 160, top = 18, bottom = 22, gap = 6;
  const bw = view.bars.length ? (W - gap * (view.bars.length - 1)) / view.bars.length : 0;
  return (
    <section className="card chart">
      <h2 id="chart-minutes">{t(lang, "chart_minutes")}</h2>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-labelledby="chart-minutes" className="bars">
        <line x1="0" x2={W} y1={H - bottom} y2={H - bottom} className="axis" />
        {view.bars.map((b, i) => {
          const h = ((H - top - bottom) * b.minutes) / max;
          const x = i * (bw + gap);
          const y = H - bottom - h;
          return (
            <g key={b.record_id}>
              <rect x={x} y={y} width={bw} height={Math.max(h, 1)} rx="3" className={b.newest ? "bar bar-newest" : "bar"} />
              <text x={x + bw / 2} y={y - 4} textAnchor="middle" className="bar-value">{minutes(b.minutes, f)}</text>
              <text x={x + bw / 2} y={H - 6} textAnchor="middle" className="bar-label">{b.label}</text>
            </g>
          );
        })}
      </svg>
      <table className="visually-hidden">
        <caption>{t(lang, "chart_minutes")}</caption>
        <thead><tr><th scope="col">{t(lang, "chart_date")}</th><th scope="col">{t(lang, "chart_minutes_col")}</th></tr></thead>
        <tbody>{view.bars.map((b) => <tr key={b.record_id}><td>{b.label}</td><td>{minutes(b.minutes, f)}</td></tr>)}</tbody>
      </table>
    </section>
  );
}

function StatesBar({ lang, view }: { lang: UiLang; view: AnalyticsView }) {
  const total = view.states.reduce((s, x) => s + x.count, 0);
  return (
    <section className="card states">
      <h2>{t(lang, "chart_states")}</h2>
      <div className="stack" aria-hidden="true">
        {view.states.filter((s) => s.count > 0).map((s) => (
          <span key={s.state} className={`stack-part st-${s.state.toLowerCase()}`} style={{ flexGrow: s.count }} />
        ))}
        {total === 0 && <span className="stack-part st-empty" style={{ flexGrow: 1 }} />}
      </div>
      <ul className="legend">
        {view.states.map((s) => (
          <li key={s.state}><span className={`swatch st-${s.state.toLowerCase()}`} aria-hidden="true" /><strong>{s.count}</strong> {t(lang, STATE_KEY[s.state])}</li>
        ))}
      </ul>
    </section>
  );
}

export interface AnalyticsScreenProps {
  lang: UiLang;
  view: AnalyticsView;
  f: Fmt;
}

export function AnalyticsScreen({ lang, view, f }: AnalyticsScreenProps) {
  const [filter, setFilter] = useState<LearningState | "all">("all");
  if (view.empty) {
    return (
      <div className="screen analytics-screen">
        <h1>{t(lang, "analytics_title")}</h1>
        <section className="card empty-state"><p>{t(lang, "analytics_empty")}</p></section>
      </div>
    );
  }
  const { tiles } = view;
  const words = filter === "all" ? view.words : view.words.filter((w) => w.learning_state === filter);
  return (
    <div className="screen analytics-screen">
      <h1>{t(lang, "analytics_title")}</h1>
      <div className="tiles">
        <Tile label={t(lang, "tile_words")} value={String(tiles.words)} />
        <Tile label={t(lang, "tile_assisted")} value={String(tiles.assisted)} />
        <Tile label={t(lang, "tile_reinforced")} value={String(tiles.reinforced)} />
        <Tile label={t(lang, "tile_independent")} value={tiles.independent ? String(tiles.independent) : "—"} note={tiles.independent ? undefined : t(lang, "tile_independent_note")} />
        <Tile label={t(lang, "tile_sessions")} value={String(tiles.sessions)} />
        <Tile label={t(lang, "tile_minutes")} value={minutes(tiles.minutes, f)} />
        <Tile label={t(lang, "tile_streak")} value={String(tiles.streak)} accent />
        <Tile label={t(lang, "tile_accuracy")} value={tiles.accuracy === null ? "—" : percent(tiles.accuracy, f)} note={t(lang, "tile_accuracy_note")} />
      </div>
      <div className="charts">
        <MinutesChart lang={lang} view={view} f={f} />
        <StatesBar lang={lang} view={view} />
      </div>
      <section className="card words">
        <h2>{t(lang, "words_list")}</h2>
        <div className="filters" role="group" aria-label={t(lang, "words_list")}>
          {(["all", ...LEARNING_STATES] as const).map((s) => (
            <button key={s} type="button" className="filter-chip" aria-pressed={filter === s} onClick={() => setFilter(s)}>
              {s === "all" ? t(lang, "filter_all") : t(lang, STATE_KEY[s])}
            </button>
          ))}
        </div>
        <ul className="word-rows">
          {words.map((w) => (
            <li key={w.learning_event_id} className="word-row">
              <div className="word-head">
                <span className="word-expr" lang={w.target_language}>{w.expression}</span>
                {w.meaning && <span className="word-meaning">{w.meaning}</span>}
                <span className="word-lang">{languageName(lang, w.target_language)}</span>
              </div>
              <ol className="state-path" aria-label={t(lang, "state_path")}>
                {statePath(w).map((step) => (
                  <li key={step.state} className={step.reached ? "step reached" : "step"}>
                    <span className="step-dot" aria-hidden="true" />
                    <span className="step-label">{t(lang, STATE_KEY[step.state])}</span>
                    <span className="step-date">{step.reached && step.at ? shortDay(Date.parse(step.at), f) : <span className="visually-hidden">{t(lang, "state_not_reached")}</span>}</span>
                  </li>
                ))}
              </ol>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
