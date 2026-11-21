// =============================================================================
// HomeView.tsx  —  LANGUAGE: TypeScript + JSX (React)
// -----------------------------------------------------------------------------
// MOCHI'S OWN SCREEN (the 3.5-inch touch screen on the Raspberry Pi).
// URL: /home?device=home_pi_01
//
// What it shows (one at a time, full screen, big text, no animation):
//   sleeping face → "What do you want to do today?" → listening face → a hint (1-3 options)
//   → "speaking" (with what Mochi says) → the game screens
// Face screens are cream, like Mochi's body; word screens are dark, like the vision slides.
// The ONLY input: tap anywhere on the screen, or hold (long press).
// The decision "which screen to show" is made in lib/home.ts; this file only draws it
// and turns finger touches into "tap" or "long".
// =============================================================================

import { type PointerEvent, type RefObject, useRef, useState } from "react";
import { type Backend, HttpError } from "../lib/backend.ts";
import { type HomeLocal, LONG_PRESS_MS, type Press, afterResultFailure, applyAction, homeScreen, initialHomeLocal, onPress } from "../lib/home.ts";
import { copyFor, displayName, fitFontSize } from "../lib/i18n.ts";
import type { ClientState } from "../lib/store.ts";
import type { Language } from "../contracts.ts";

// "Props" = the inputs this component receives from main.tsx.
interface Props {
  state: ClientState;                  // all data received from the backend
  now: number;                         // current time in milliseconds
  lang: Language;                      // "en" or "pt-BR"
  backend: RefObject<Backend | null>;  // used to send the game result to the backend
}

// The face from the vision slides: two black eyes with a white shine, pink cheeks, a small smile.
// All the shapes are drawn in styles.css. awake=false → closed eyes (Mochi is resting).
export function Face({ awake, small = false }: { awake: boolean; small?: boolean }) {
  return (
    <div className={`face ${awake ? "awake" : "asleep"} ${small ? "small-face" : ""}`} aria-hidden="true">
      <span className="eye" />
      <span className="eye" />
      <span className="cheek left" />
      <span className="cheek right" />
      <span className="mouth" />
    </div>
  );
}

export function HomeView({ state, now, lang, backend }: Props) {
  const t = copyFor(lang); // t = all the texts in the chosen language (t.listening, t.gotIt(...), ...)

  // "local" = things only THIS screen knows: has the describer (Ana) revealed the word? did we already send the result?
  // The server never hears about "revealed"; only the final result is sent.
  const [local, setLocal] = useState<HomeLocal>(initialHomeLocal);

  // Timer used to detect a long press (finger held down for 600 ms).
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Ask lib/home.ts: "with this data, which screen should Mochi show right now?"
  const screen = homeScreen(state, local, now);

  // Called after we know if it was a "tap" or a "long" press.
  const press = (p: Press) => {
    const action = onPress(screen, p);   // what should this press do on this screen? (maybe nothing)
    if (!action) return;
    setLocal((l) => applyAction(l, action)); // remember it locally (e.g. "word revealed")
    if (action.do === "send_result") {
      // Second tap = "guessed", long press = "skipped" → tell the backend.
      backend.current?.activityResult(action.result).catch((err) => {
        // 409 = the round already ended: follow the server. Other failures: show the word again to tap again.
        const status = err instanceof HttpError ? err.status : null;
        setLocal((l) => afterResultFailure(l, action.roundId, status));
      });
    }
  };

  // --- Turning finger touches into "tap" or "long" ------------------------------
  // Finger goes DOWN: start a 600 ms timer. If it runs out, it's a long press.
  const down = (e: PointerEvent) => {
    e.preventDefault(); // stop the browser from selecting text or zooming
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      timer.current = null;
      press("long");
    }, LONG_PRESS_MS);
  };
  // Finger goes UP before 600 ms: cancel the timer, it's a normal tap.
  const up = () => {
    if (timer.current) {
      clearTimeout(timer.current);
      timer.current = null;
      press("tap");
    }
  };
  // Touch was interrupted (finger slid off the screen): do nothing.
  const cancel = () => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
  };

  // --- Choose what to draw for each screen ------------------------------------
  // fitFontSize(...) makes long words smaller so they always fit on one line.
  let body;
  switch (screen.kind) {
    case "sleeping":      // before Start: closed eyes
      body = (<><Face awake={false} /><p className="small">{t.sleeping}</p></>);
      break;
    case "choosing":      // "Oi, Mochi!" → which mode? (the choice is said out loud, not tapped)
      body = (
        <>
          <Face awake small />
          <p className="medium">{t.choosing}</p>
          <p className="modes">{t.modeName.practice} · {t.modeName.together} · {t.modeName.activity}</p>
        </>
      );
      break;
    case "listening":     // open eyes + the mode: "Ouvindo" (Companhia), "Praticando", "Hora do jogo"
      body = (<><Face awake /><p className="small">{t.modeFace[screen.mode]}</p></>);
      break;
    case "hint": {        // someone got stuck: who it is for, then 1 to 3 options, one per line
      const longest = screen.options.reduce((a, b) => (b.length > a.length ? b : a), "");
      const many = screen.options.length > 1;
      // several options: each must fit on one line; one option: it may wrap between words
      const size = fitFontSize(longest, many ? 22 : 34, 90, many);
      body = (
        <>
          {screen.target && <p className="for">{t.forName(displayName(screen.target))}</p>}
          {screen.options.map((o) => <p key={o} className="big" style={{ fontSize: size }}>{o}</p>)}
        </>
      );
      break;
    }
    case "speaking":      // Mochi talks out loud: small face + what it says
      body = (<><Face awake small /><p className="said">“{screen.text}”</p></>);
      break;
    case "game_hidden":   // game started: "Ana, turn me to you and tap"
      body = <p className="medium">{t.turnAndTap(displayName(screen.describer))}</p>;
      break;
    case "game_revealed": // the describer tapped: show the secret word + instructions
      body = (<><p className="big" style={{ fontSize: fitFontSize(screen.word, 30, 70) }}>{screen.word}</p><p className="small">{t.tapWhenGets(displayName(screen.guesser))}</p><p className="tiny">{t.longPressSkip}</p></>);
      break;
    case "game_waiting":  // result sent, waiting for the backend to confirm
      body = <p className="medium">{t.waiting}</p>;
      break;
    case "game_result":   // "umbrella — Ana got it!" for a few seconds
      body = (<><p className="big" style={{ fontSize: fitFontSize(screen.word ?? "", 30) }}>{screen.word ?? ""}</p><p className="medium">{screen.result === "skipped" ? t.skipped : t.gotIt(displayName(screen.guesser))}</p></>);
      break;
  }

  // The whole screen is ONE big touch area (the guide: "a tela inteira é o botão").
  // data-screen="..." helps testing: you can see which screen is showing.
  return (
    <main
      className={`home home-${screen.kind}`}
      data-screen={screen.kind}
      onPointerDown={down}
      onPointerUp={up}
      onPointerCancel={cancel}
      onPointerLeave={cancel}
      onContextMenu={(e) => e.preventDefault()} // a long press must not open the right-click menu
    >
      {body}
    </main>
  );
}
