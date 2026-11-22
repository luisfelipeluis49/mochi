// Dates, minutes and relative times, per UI language. The time zone is injectable for tests.

import { type UiLang, intlLocale } from "./i18n.ts";

export interface Fmt {
  lang: UiLang;
  /** IANA zone; undefined = the browser's own. */
  timeZone?: string;
}

/** "2026-11-21" for an instant, in the given time zone (a local calendar day). */
export function dayKey(ms: number, timeZone?: string): string {
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone, year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(new Date(ms));
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? "00";
  return `${get("year")}-${get("month")}-${get("day")}`;
}

/** The day before a dayKey: "2026-11-21" -> "2026-11-20". Pure calendar arithmetic, no time zone. */
export function previousDay(key: string): string {
  const [y, m, d] = key.split("-").map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d - 1));
  return dt.toISOString().slice(0, 10);
}

/** "Friday, 21 Nov" / "sexta-feira, 21 de nov." */
export function longDay(ms: number, f: Fmt): string {
  const weekday = new Intl.DateTimeFormat(intlLocale(f.lang), { timeZone: f.timeZone, weekday: "long" }).format(new Date(ms));
  return `${weekday}, ${shortDay(ms, f)}`;
}

/** "21 Nov" / "21 de nov." */
export function shortDay(ms: number, f: Fmt): string {
  return new Intl.DateTimeFormat(intlLocale(f.lang), { timeZone: f.timeZone, day: "numeric", month: "short" }).format(new Date(ms));
}

/** "10:00" (24 h in both UIs). */
export function clock(ms: number, f: Fmt): string {
  return new Intl.DateTimeFormat(intlLocale(f.lang), { timeZone: f.timeZone, hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(ms));
}

/** 12.5 -> "12.5" (en) / "12,5" (pt-BR); always one decimal place at most. */
export function minutes(n: number, f: Fmt): string {
  return new Intl.NumberFormat(intlLocale(f.lang), { maximumFractionDigits: 1, minimumFractionDigits: 0 }).format(Math.round(n * 10) / 10);
}

/** Elapsed time as mm:ss (or h:mm:ss past an hour). */
export function elapsed(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const mm = String(m).padStart(2, "0");
  const ss = String(s).padStart(2, "0");
  return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}

/** "in 10 minutes", "tomorrow", "now" / "em 10 minutos", "amanhã", "agora". */
export function relative(targetMs: number, nowMs: number, f: Fmt): string {
  const diff = targetMs - nowMs;
  const rtf = new Intl.RelativeTimeFormat(intlLocale(f.lang), { numeric: "auto" });
  const abs = Math.abs(diff);
  if (abs < 45_000) return rtf.format(0, "second");
  if (abs < 45 * 60_000) return rtf.format(Math.round(diff / 60_000), "minute");
  if (abs < 22 * 3_600_000) return rtf.format(Math.round(diff / 3_600_000), "hour");
  return rtf.format(Math.round(diff / 86_400_000), "day");
}

/** Percent with no decimals: 0.7 -> "70%". */
export function percent(ratio: number, f: Fmt): string {
  return new Intl.NumberFormat(intlLocale(f.lang), { style: "percent", maximumFractionDigits: 0 }).format(ratio);
}
