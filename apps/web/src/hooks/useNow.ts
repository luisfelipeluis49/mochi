// The clock, re-read every `intervalMs` (1 s by default) so time-based views (the hint countdown,
// the elapsed timer, the face) move on their own.
import { useEffect, useState } from "react";

export function useNow(intervalMs = 1000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);
  return now;
}
