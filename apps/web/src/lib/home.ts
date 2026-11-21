// =============================================================================
// home.ts  —  LANGUAGE: TypeScript (no React, no screen)
// -----------------------------------------------------------------------------
// The RULES for Mochi's screen (AGENTS.md §7.5), kept apart from the drawing so
// they can be tested (see home.test.ts).
//   homeScreen() → "which screen should Mochi show now?"
//   onPress()    → "the user tapped / held: what should happen?"
//   applyAction()→ "remember what happened" (word revealed, result sent)
// New product vision: after "Oi, Mochi!" the screen asks which mode (choosing),
// a hint can show up to 3 options, and in the game Mochi itself judges the guess by
// voice (the backend sends ROUND_RESULT); the taps stay as a backup.
// =============================================================================

import type { RoundResult, SessionMode } from "../contracts.ts";
import { type ClientState, hintOptions, isSpeaking, liveHint } from "./store.ts";

export const LONG_PRESS_MS = 600;   // holding longer than this = long press (= "skip")
export const RESULT_SHOW_MS = 4000; // how long "Ana got it!" stays before going back to the face

/** Things only Mochi's screen knows. The server never sees "revealed". */
export interface HomeLocal {
  revealedRoundId: string | null; // the round where the describer already tapped to see the word
  sentRoundId: string | null;     // the round whose result we already sent (ignore more taps)
}
export const initialHomeLocal: HomeLocal = { revealedRoundId: null, sentRoundId: null };

/** Every possible screen on Mochi, with the data each one needs. */
export type HomeScreen =
  | { kind: "sleeping" }                                                  // not listening
  | { kind: "choosing" }                                                  // "Oi, Mochi!": what do you want to do today?
  | { kind: "listening"; mode: SessionMode }                              // listening, nothing to show
  | { kind: "hint"; options: string[]; target: string | null }            // 1 to 3 hint options, and who they are for
  | { kind: "speaking"; text: string }                                    // Mochi talking
  | { kind: "game_hidden"; roundId: string; describer: string }           // "Ana, turn me to you and tap"
  | { kind: "game_revealed"; roundId: string; word: string; guesser: string } // the secret word
  | { kind: "game_waiting"; roundId: string; describer: string; guesser: string } // result sent, waiting
  | { kind: "game_result"; word: string | null; guesser: string; result: RoundResult | null }; // "Ana got it!"

/** Decide the screen. Checked in order: game, choosing a mode, speaking, hint, then the face. */
export function homeScreen(state: ClientState, local: HomeLocal, now: number): HomeScreen {
  const a = state.activity;

  // 1) A game round is running.
  if (a?.state === "ACTIVE_ROUND") {
    // The secret word, but only if it belongs to THIS round.
    const secret = state.privatePrompt?.round_id === a.round_id ? state.privatePrompt.secret_word : null;
    if (local.revealedRoundId === a.round_id && secret) {
      return { kind: "game_revealed", roundId: a.round_id, word: secret, guesser: a.guesser_user_id };
    }
    if (local.sentRoundId === a.round_id) {
      return { kind: "game_waiting", roundId: a.round_id, describer: a.describer_user_id, guesser: a.guesser_user_id };
    }
    return { kind: "game_hidden", roundId: a.round_id, describer: a.describer_user_id };
  }

  // 2) The round just ended: show the result for RESULT_SHOW_MS, then fall through to the face.
  if (a?.state === "ROUND_RESULT" && now - state.activityReceivedAt < RESULT_SHOW_MS) {
    const word = a.revealed_word ?? (state.privatePrompt?.round_id === a.round_id ? state.privatePrompt.secret_word : null);
    return { kind: "game_result", word, guesser: a.guesser_user_id, result: a.result };
  }

  // 3) Someone said "Oi, Mochi!": ask which mode (PROPOSED v0.5). This wins over "speaking",
  //    because Mochi asks the same question out loud at that moment.
  const session = state.session;
  if (session?.capturing && session.mode === "choosing") return { kind: "choosing" };

  // 4) Mochi is talking.
  if (isSpeaking(state, now) && state.speaking) return { kind: "speaking", text: state.speaking.speak.text };

  // 5) A hint is live.
  const hint = liveHint(state, now);
  if (hint) return { kind: "hint", options: hintOptions(hint.expression), target: hint.target_user_id };

  // 6) Not listening: asleep.
  if (!session?.capturing) return { kind: "sleeping" };

  // 7) Otherwise: the face, awake, with the current mode.
  return { kind: "listening", mode: session.mode };
}

export type Press = "tap" | "long";

/** What a press can cause: reveal the word, send a result, or nothing (null). */
export type HomeAction =
  | { do: "reveal"; roundId: string }
  | { do: "send_result"; roundId: string; result: RoundResult }
  | null;

/** Tap on hidden word → reveal (only on this screen). Tap on revealed word → "guessed". Long press → "skipped". */
export function onPress(screen: HomeScreen, press: Press): HomeAction {
  if (screen.kind === "game_hidden" && press === "tap") return { do: "reveal", roundId: screen.roundId };
  if (screen.kind === "game_revealed") {
    return { do: "send_result", roundId: screen.roundId, result: press === "tap" ? "guessed" : "skipped" };
  }
  return null; // on every other screen, touches do nothing
}

/** Remember the action in the local state. */
export function applyAction(local: HomeLocal, action: HomeAction): HomeLocal {
  if (!action) return local;
  if (action.do === "reveal") return { ...local, revealedRoundId: action.roundId };
  return { revealedRoundId: null, sentRoundId: action.roundId };
}
