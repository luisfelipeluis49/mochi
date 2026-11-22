// =============================================================================
// sessionStage.ts  —  LANGUAGE: TypeScript
// -----------------------------------------------------------------------------
// What the Session tab shows while Mochi is in the meeting: the SAME choice Mochi's own screen
// makes (home.ts → homeScreen), so the phone behaves like the Pi. Only differences:
//   - no game on the phone: game screens show the listening face instead
//   - a hint also carries its meaning and example (a phone has room for them)
// =============================================================================

import type { SessionMode } from "../contracts.ts";
import { homeScreen, initialHomeLocal } from "./home.ts";
import { type ClientState, liveHint } from "./store.ts";

export type Stage =
  | { kind: "idle" }                                                       // no session: ready to start
  | { kind: "listening"; mode: SessionMode }                               // Mochi's face, awake
  | { kind: "choosing" }                                                   // "Hi Mochi": which mode?
  | { kind: "speaking"; text: string }                                     // what Mochi says out loud
  | { kind: "hint"; options: string[]; target: string | null; meaning: string | null; example: string | null };

/** The stage for this moment. `live` is false while a session that this phone did not start runs
 *  (it then shows the face only: no words from another session on this phone). */
export function sessionStage(state: ClientState, now: number, live: boolean): Stage {
  const s = homeScreen(state, initialHomeLocal, now);
  const mode = state.session?.mode ?? "together";
  if (s.kind === "sleeping") return { kind: "idle" };
  if (!live) return { kind: "listening", mode };
  switch (s.kind) {
    case "choosing":
      return { kind: "choosing" };
    case "speaking":
      return { kind: "speaking", text: s.text };
    case "hint": {
      const h = liveHint(state, now);
      return { kind: "hint", options: s.options, target: s.target, meaning: h?.meaning ?? null, example: h?.example ?? null };
    }
    case "listening":
      return { kind: "listening", mode: s.mode };
    default:
      return { kind: "listening", mode }; // a game round: no game on the phone
  }
}
