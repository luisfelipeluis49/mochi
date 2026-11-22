// Papear's presence panel: a sober status card with the monogram, a plain-words state and a live
// audio meter. It replaces the cartoon face of the Pi's screen on the web. The state still comes from
// lib/face.ts (the same modes as the device); the meter follows Papear's voice while it speaks and
// shows a low idle line otherwise. No animation runs under prefers-reduced-motion (styles/app.css).

import type { FaceView } from "../lib/face.ts";
import { type UiLang, t } from "../lib/i18n.ts";
import { Icon } from "./Icons.tsx";

export interface FaceProps {
  lang: UiLang;
  view: FaceView;
  /** Papear's voice loudness 0..1 (the meter moves while speaking) */
  level?: number;
}

const BARS = [0.45, 0.7, 1, 0.7, 0.45];

export function faceLabel(lang: UiLang, view: FaceView): string {
  if (view.offline) return t(lang, "face_offline");
  if (view.mode === "hearing") return t(lang, "face_hearing", { name: view.who.replace(/\s…$/, "") || "…" });
  return t(lang, `face_${view.mode}`);
}

export function Face({ lang, view, level = 0 }: FaceProps) {
  const speaking = view.mode === "speaking";
  const live = view.mode === "hearing" || view.mode === "awake" || view.mode === "thinking" || speaking;
  const amplitude = speaking ? Math.min(1, Math.max(0.2, level * 1.8)) : 0;
  const cls = ["presence", `mode-${view.mode}`, view.mood === "oops" ? "has-problem" : "", view.offline ? "is-offline" : ""].filter(Boolean).join(" ");
  const label = faceLabel(lang, view);
  return (
    <div className={cls} role="img" aria-label={label}>
      <div className="presence-head" aria-hidden="true">
        <span className="monogram">P</span>
        <span className="presence-state">{label}</span>
        {view.pop && <span className="presence-pop"><Icon name="speaker" size={16} />{view.pop.value}</span>}
      </div>
      <div className={`meter${live ? " is-live" : ""}`} aria-hidden="true">
        {BARS.map((h, i) => (
          <span key={i} className="meter-bar" style={{ height: `${Math.round(12 + (speaking ? amplitude * h * 88 : h * 10))}%` }} />
        ))}
      </div>
      {view.offline && <span className="presence-offline" aria-hidden="true"><Icon name="wifiOff" size={16} />{t(lang, "face_offline")}</span>}
    </div>
  );
}
