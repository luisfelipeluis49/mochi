// The voice link while a session runs: join/leave, Mochi's voice volume, and the two levels the face
// uses (this browser's microphone = "hearing", Mochi's voice = "speaking"), sampled every 100 ms.
import { useCallback, useEffect, useRef, useState } from "react";
import type { AgoraJoin } from "../contracts.ts";
import type { VoiceLink } from "../lib/agora.ts";
import { HEARING_LEVEL, QUIET_LEVEL } from "../lib/face.ts";

export type JoinVoice = (join: AgoraJoin, opts: { volume: number }) => Promise<VoiceLink>;

export interface AgoraMic {
  join(join: AgoraJoin, volume: number): Promise<void>;
  leave(): Promise<void>;
  setVolume(v: number): void;
  active: boolean;
  lastHearingAt: number;
  lastLoudAt: number;
  /** Mochi's voice level 0..1 (for the mouth) */
  level: number;
}

export function useAgoraMic(joinVoice: JoinVoice): AgoraMic {
  const link = useRef<VoiceLink | null>(null);
  const [active, setActive] = useState(false);
  const [levels, setLevels] = useState({ lastHearingAt: 0, lastLoudAt: 0, level: 0 });

  useEffect(() => {
    if (!active) return;
    const id = setInterval(() => {
      const l = link.current;
      if (!l) return;
      const now = Date.now();
      const mic = l.micLevel();
      const remote = l.remoteLevel() ?? 0;
      setLevels((prev) => {
        const hearing = mic > HEARING_LEVEL ? now : prev.lastHearingAt;
        const loud = remote > QUIET_LEVEL ? now : prev.lastLoudAt;
        const level = Math.round(remote * 20) / 20;
        if (hearing === prev.lastHearingAt && loud === prev.lastLoudAt && level === prev.level) return prev;
        return { lastHearingAt: hearing, lastLoudAt: loud, level };
      });
    }, 100);
    return () => clearInterval(id);
  }, [active]);

  const leave = useCallback(async () => {
    const l = link.current;
    link.current = null;
    setActive(false);
    setLevels((p) => ({ ...p, level: 0 }));
    await l?.leave();
  }, []);

  const join = useCallback(async (j: AgoraJoin, volume: number) => {
    await link.current?.leave();
    link.current = await joinVoice(j, { volume });
    setActive(true);
  }, [joinVoice]);

  const setVolume = useCallback((v: number) => link.current?.setVolume(v), []);

  useEffect(() => () => { void link.current?.leave(); }, []);

  return { join, leave, setVolume, active, ...levels };
}
