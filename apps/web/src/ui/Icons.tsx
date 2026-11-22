// Inline SVG icons (no icon set dependency). They take the text color (currentColor).
import type { ReactElement } from "react";

const base = { width: 24, height: 24, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 2, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true, focusable: false };

export type IconName = "session" | "training" | "digest" | "analytics" | "speaker" | "check" | "mic" | "wifiOff" | "alert" | "arrow";

const paths: Record<IconName, ReactElement> = {
  session: <><circle cx="12" cy="12" r="9" /><circle cx="9" cy="11" r="1" fill="currentColor" /><circle cx="15" cy="11" r="1" fill="currentColor" /><path d="M9.5 15q2.5 2 5 0" /></>,
  training: <><rect x="4" y="5" width="13" height="15" rx="2" /><path d="M8 3h10a2 2 0 0 1 2 2v12" /><path d="M8 11l2 2 4-4" /></>,
  digest: <><path d="M6 3h9l4 4v14H6z" /><path d="M14 3v5h5" /><path d="M9 13h7M9 17h5" /></>,
  analytics: <><path d="M4 20V10M10 20V4M16 20v-7M22 20H2" /></>,
  speaker: <><path d="M4 10h4l5-4v12l-5-4H4z" fill="currentColor" /><path d="M16 9a4 4 0 0 1 0 6M18.5 6.5a7.5 7.5 0 0 1 0 11" /></>,
  check: <><path d="M5 12.5l4.5 4.5L19 7.5" /></>,
  mic: <><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" /></>,
  wifiOff: <><path d="M2 8.5a15 15 0 0 1 20 0M5.5 12a10 10 0 0 1 13 0M9 15.5a5 5 0 0 1 6 0" /><circle cx="12" cy="19" r="1" fill="currentColor" /><path d="M3 3l18 18" /></>,
  alert: <><path d="M12 3l10 18H2z" /><path d="M12 10v5M12 18v.5" /></>,
  arrow: <><path d="M5 12h14M13 6l6 6-6 6" /></>,
};

export function Icon({ name, size = 24 }: { name: IconName; size?: number }) {
  return <svg {...base} width={size} height={size} className={`icon icon-${name}`}>{paths[name]}</svg>;
}
