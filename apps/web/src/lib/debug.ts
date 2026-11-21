// =============================================================================
// debug.ts  —  LANGUAGE: TypeScript (no React)
// -----------------------------------------------------------------------------
// What the ?debug=1 panel may print. It must never show a secret word:
// the Home view receives it before the describer taps (AGENTS.md 6.2, 7.5).
// =============================================================================

import type { MochiEvent } from "../contracts.ts";

export const REDACTED = "[hidden]";

/** The payload of an event with secret words replaced by "[hidden]":
 *  secret_word in activity.private_prompt, revealed_word while the round is ACTIVE_ROUND. */
export function redactPayload(e: MochiEvent): unknown {
  if (e.type === "activity.private_prompt") return { ...e.payload, secret_word: REDACTED };
  if (e.type === "activity.state.changed" && e.payload.state === "ACTIVE_ROUND" && e.payload.revealed_word != null) {
    return { ...e.payload, revealed_word: REDACTED };
  }
  return e.payload;
}
