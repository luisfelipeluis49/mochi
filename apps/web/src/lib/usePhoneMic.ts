// =============================================================================
// usePhoneMic.ts  —  LANGUAGE: TypeScript (a React hook)
// -----------------------------------------------------------------------------
// Start/Stop with THIS phone's microphone, shared by the phone page (/m: Iniciar/Parar) and
// "My conversations" (/me: Record/Stop and save). See phoneMic.ts and PROPOSAL_phone_microphone.md.
//   startHere: the usual POST /start, then this phone's mic joins Mochi's channel (the Pi is not used)
//   stopHere:  mic off, then the usual POST /stop
//   here:      did THIS phone start the running session? (false while a session started on the Pi runs)
// =============================================================================

import { useEffect, useRef, useState } from "react";
import type { Backend } from "./backend.ts";
import { markStartedHere, startedHere, startPhoneMic } from "./phoneMic.ts";

export function usePhoneMic(capturing: boolean, onMicFailed: () => void) {
  const [here, setHere] = useState(() => startedHere());
  const micStop = useRef<(() => Promise<void>) | null>(null); // stops this phone's mic, when it is on
  const wasCapturing = useRef(capturing);

  // Turn the mic off and forget "started here".
  const endHere = async () => {
    const stop = micStop.current;
    micStop.current = null;
    markStartedHere(false);
    setHere(false);
    await stop?.().catch(() => undefined);
  };

  // The session ended (Stop here, on another phone, or a reset): turn the mic off too.
  useEffect(() => {
    if (wasCapturing.current && !capturing) void endHere();
    wasCapturing.current = capturing;
  }, [capturing]);

  // Leaving the page: turn the mic off (the session itself keeps running until Stop).
  useEffect(() => () => { void micStop.current?.(); }, []);

  const startHere = async (b: Backend) => {
    markStartedHere(true);
    setHere(true);
    await b.start();
    const join = await b.phoneAudio(); // null in the mock: no mic
    if (!join) return;
    try {
      micStop.current = await startPhoneMic(join);
    } catch {
      onMicFailed(); // no permission, no HTTPS, or the SDK did not load
    }
  };

  const stopHere = async (b: Backend) => {
    await endHere();
    await b.stop();
  };

  return { here, startHere, stopHere };
}
