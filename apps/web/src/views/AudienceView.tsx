// =============================================================================
// AudienceView.tsx  —  LANGUAGE: TypeScript + JSX (React)
// -----------------------------------------------------------------------------
// THE PROJECTOR (what the judges see).  URL: /audience
// Also shows the mode question after "Oi, Mochi!" and what Mochi says out loud.
// A big copy of Mochi's screen, with ONE important rule:
//   it NEVER shows the secret word while the game round is running.
// The backend never sends the secret word here anyway; this screen also only reads
// `revealed_word` once the round is over (ROUND_RESULT).
// =============================================================================

import type { Language } from "../contracts.ts";
import { copyFor, displayName, fitFontSize } from "../lib/i18n.ts";
import { type ClientState, hintOptions, isSpeaking, liveHint } from "../lib/store.ts";
import { resultVisible } from "../lib/home.ts";
import { Face } from "./HomeView.tsx";

export function AudienceView({ state, now, lang }: { state: ClientState; now: number; lang: Language }) {
  const t = copyFor(lang);      // texts in the chosen language
  const a = state.activity;     // the game (null if no game yet)
  const hint = liveHint(state, now); // current hint, or null

  // Pick what to draw, checking from most important to least important.
  let body;
  if (a && a.state === "ACTIVE_ROUND") {
    // A round is running: show WHO describes and WHO guesses. No word!
    body = (
      <>
        <p className="aud-roles">
          <b>{displayName(a.describer_user_id)}</b> {t.describes} · <b>{displayName(a.guesser_user_id)}</b> {t.guesses}
        </p>
        <p className="aud-instruction">{a.public_instruction}</p>
      </>
    );
  } else if (a && a.state === "ROUND_RESULT" && resultVisible(state, now)) {
    // Round finished: now the word can be shown, with "Ana got it!" or "Skipped".
    body = (
      <>
        <p className="aud-small">{t.word}</p>
        <p className="aud-big" style={{ fontSize: fitFontSize(a.revealed_word ?? "", 40, 80) }}>{a.revealed_word ?? ""}</p>
        <p className="aud-instruction">{a.result === "skipped" ? t.skipped : t.gotIt(displayName(a.guesser_user_id))}</p>
      </>
    );
  } else if (state.session?.capturing && state.session.mode === "choosing") {
    // "Oi, Mochi!": the mode question (wins over "speaking": Mochi asks it out loud at the same time).
    body = (
      <>
        <Face awake />
        <p className="aud-said">{t.choosing}</p>
        <p className="aud-modes">{t.modeName.practice} · {t.modeName.together} · {t.modeName.activity}</p>
      </>
    );
  } else if (isSpeaking(state, now) && state.speaking) {
    // Mochi is talking out loud: show what it says (the audience hears it too).
    body = (
      <>
        <Face awake small />
        <p className="aud-said">“{state.speaking.speak.text}”</p>
      </>
    );
  } else if (hint) {
    // A hint is live: who it is for, the options big, and the meaning smaller.
    const options = hintOptions(hint.expression);
    const longest = options.reduce((x, y) => (y.length > x.length ? y : x), "");
    body = (
      <>
        {hint.target_user_id && <p className="aud-small">{t.forName(displayName(hint.target_user_id))}</p>}
        {options.map((o) => <p key={o} className="aud-big" style={{ fontSize: fitFontSize(longest, options.length > 1 ? 18 : 40, 80, options.length > 1) }}>{o}</p>)}
        {hint.meaning && <p className="aud-small">{hint.meaning}</p>}
      </>
    );
  } else {
    // Nothing happening: Mochi's face, with the mode ("Ouvindo", "Praticando"...) or asleep.
    const session = state.session;
    const awake = session?.capturing ?? false;
    body = (
      <>
        <Face awake={awake} />
        <p className="aud-small">{!awake || !session ? t.sleeping : t.modeFace[session.mode]}</p>
      </>
    );
  }

  return <main className="audience">{body}</main>;
}
