// Mochi's face: an inline SVG modeled on hardware/pi-setup/face.html (the same eyes, mouths, blush and
// breathing). Which eyes and mouth show is decided only by the CSS classes mode-* and mood-*
// (styles/app.css); the mouth opens with Mochi's voice level while speaking.

import type { FaceView } from "../lib/face.ts";
import { type UiLang, t } from "../lib/i18n.ts";
import { Icon } from "./Icons.tsx";

export interface FaceProps {
  lang: UiLang;
  view: FaceView;
  /** Mochi's voice loudness 0..1 (opens the mouth while speaking) */
  level?: number;
}

export function faceLabel(lang: UiLang, view: FaceView): string {
  if (view.offline) return t(lang, "face_offline");
  if (view.mode === "hearing") return t(lang, "face_hearing", { name: view.who.replace(/\s…$/, "") || "…" });
  return t(lang, `face_${view.mode}`);
}

export function Face({ lang, view, level = 0 }: FaceProps) {
  const open = view.mode === "speaking" ? Math.min(1, Math.max(0.25, level * 1.8)) : 0;
  const cls = ["mochi-face", `mode-${view.mode}`, `mood-${view.mood}`, view.offline ? "is-offline" : ""].filter(Boolean).join(" ");
  return (
    <div className={cls} role="img" aria-label={faceLabel(lang, view)}>
      {view.who && <span className="face-who" aria-hidden="true">{view.who}</span>}
      {view.pop && (
        <span className="face-pop" aria-hidden="true"><Icon name="speaker" size={20} />{view.pop.value}</span>
      )}
      <svg viewBox="0 0 480 320" aria-hidden="true" focusable="false">
        <g className="face-body">
          <ellipse className="blush" cx="104" cy="196" rx="32" ry="19" />
          <ellipse className="blush" cx="376" cy="196" rx="32" ry="19" />
          <g className="eyes eyes-open">
            <g className="eye"><ellipse className="ink" cx="160" cy="140" rx="25" ry="33" /><circle className="shine" cx="169" cy="127" r="9" /><circle className="shine" cx="151" cy="152" r="4" opacity=".8" /></g>
            <g className="eye"><ellipse className="ink" cx="320" cy="140" rx="25" ry="33" /><circle className="shine" cx="329" cy="127" r="9" /><circle className="shine" cx="311" cy="152" r="4" opacity=".8" /></g>
          </g>
          <g className="eyes eyes-happy"><path className="line" d="M134 152 Q160 114 186 152" /><path className="line" d="M294 152 Q320 114 346 152" /></g>
          <g className="eyes eyes-closed"><path className="line" d="M134 140 Q160 164 186 140" /><path className="line" d="M294 140 Q320 164 346 140" /></g>
          <g className="eyes eyes-sleepy">
            <path className="ink" d="M135 148 a25 20 0 0 0 50 0 z" /><path className="ink" d="M295 148 a25 20 0 0 0 50 0 z" />
            <path className="line" d="M134 147 H186" /><path className="line" d="M294 147 H346" />
          </g>
          <g className="eyes eyes-laugh"><path className="line" d="M138 118 L182 140 L138 162" /><path className="line" d="M342 118 L298 140 L342 162" /></g>
          <g className="eyes eyes-love">
            <path className="heart" d="M0 9 C-22 -8 -9 -24 0 -11 C9 -24 22 -8 0 9 Z" transform="translate(160 146) scale(2.1)" />
            <path className="heart" d="M0 9 C-22 -8 -9 -24 0 -11 C9 -24 22 -8 0 9 Z" transform="translate(320 146) scale(2.1)" />
          </g>
          <g className="eyes eyes-star">
            <path className="star" d="M0 -17 L5 -5 L18 -5 L8 3 L12 16 L0 8 L-12 16 L-8 3 L-18 -5 L-5 -5 Z" transform="translate(160 140) scale(2)" />
            <path className="star" d="M0 -17 L5 -5 L18 -5 L8 3 L12 16 L0 8 L-12 16 L-8 3 L-18 -5 L-5 -5 Z" transform="translate(320 140) scale(2)" />
          </g>
          <g className="eyes eyes-cool">
            <path className="ink" d="M112 118 H228 Q230 172 190 172 H150 Q112 172 112 118 Z M252 118 H368 Q368 172 330 172 H290 Q250 172 252 118 Z" />
            <path className="line thin" d="M226 124 H254" />
          </g>
          <path className="mouth mouth-smile line" d="M214 200 Q240 224 266 200" />
          <path className="mouth mouth-rest line thin" d="M228 206 Q240 214 252 206" />
          <path className="mouth mouth-grin line" d="M206 196 Q240 236 274 196" />
          <path className="mouth mouth-hmm line" d="M224 210 L256 203" />
          <path className="mouth mouth-oops line" d="M216 212 Q228 200 240 210 Q252 220 264 208" />
          <ellipse className="mouth mouth-o fill-mouth" cx="240" cy="208" rx="10" ry="12" />
          <g className="mouth mouth-laugh"><path className="fill-mouth" d="M204 194 Q240 250 276 194 Z" /><path className="fill-tongue" d="M222 222 Q240 240 258 222 Q240 214 222 222 Z" /></g>
          <g className="mouth mouth-talk">
            <ellipse className="fill-mouth" cx="240" cy="208" rx={(20 - 5 * open).toFixed(1)} ry={(4 + 22 * open).toFixed(1)} />
            <ellipse className="fill-tongue" cx="240" cy="214" rx="10" ry={(7 * open).toFixed(1)} />
          </g>
          <g className="dots"><circle cx="372" cy="92" r="6" /><circle cx="392" cy="80" r="7" /><circle cx="415" cy="66" r="8" /></g>
          <g className="zzz"><text x="372" y="96">z</text><text x="400" y="70">z</text></g>
        </g>
      </svg>
      {view.offline && <span className="face-offline"><Icon name="wifiOff" size={18} />{t(lang, "face_offline")}</span>}
    </div>
  );
}
