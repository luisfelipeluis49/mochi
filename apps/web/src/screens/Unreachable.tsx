// Shown at start while GET /healthz does not answer 200 (section 6.2): "waking" for the first 90 s
// (and while the first try is pending), then "unreachable" with Try again; "offline" without internet.
import { Problem } from "../ui/Problem.tsx";
import { faceOf, restingFace } from "../lib/face.ts";
import type { UiLang } from "../lib/i18n.ts";

export function Unreachable({ lang, problem, onRetry }: { lang: UiLang; problem: "waking" | "unreachable" | "offline" | string; onRetry: () => void }) {
  const kind = problem === "offline" ? "offline" : problem === "unreachable" ? "unreachable" : "waking";
  return (
    <Problem
      lang={lang}
      problem={{ type: "http", kind }}
      face={faceOf({ ...restingFace(lang), online: kind !== "offline" }, 0)}
      onAction={kind === "waking" ? undefined : onRetry}
    />
  );
}
