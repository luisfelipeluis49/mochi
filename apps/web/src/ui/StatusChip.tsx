// The session status chip: Asleep / Waking up / Listening / No connection.
import { type UiLang, t } from "../lib/i18n.ts";

export type ChipState = "asleep" | "waking" | "listening" | "offline";

export function StatusChip({ lang, state }: { lang: UiLang; state: ChipState }) {
  const key = state === "asleep" ? "chip_asleep" : state === "waking" ? "chip_waking" : state === "listening" ? "chip_listening" : "chip_offline";
  return (
    <span className={`chip chip-${state}`} role="status">
      <span className="chip-dot" aria-hidden="true" />
      {t(lang, key)}
    </span>
  );
}
