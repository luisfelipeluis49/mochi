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
import { askForMic, type MicProblem, markStartedHere, problemOf, startedHere, startPhoneMic } from "./phoneMic.ts";

export function usePhoneMic(capturing: boolean, onMicFailed: (problem: MicProblem) => void) {
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
    // 1. Ask for the mic on the tap itself (not in the mock). No mic = no session.
    if (b.usesMic) {
      try {
        await askForMic();
      } catch (err) {
        onMicFailed(problemOf(err));
        return;
      }
    }
    markStartedHere(true);
    setHere(true);
    await b.start();                   // 2. the usual Start
    if (!b.usesMic) return;            //    the mock stops here
    const join = await b.phoneAudio(); // 3. where to join
    if (!join) return onMicFailed("no-agora");
    try {
      micStop.current = await startPhoneMic(join); // 4. join Mochi's channel with this mic
    } catch {
      onMicFailed("agora");
    }
  };

  const stopHere = async (b: Backend) => {
    await endHere();
    await b.stop();
  };

  return { here, startHere, stopHere };
}
