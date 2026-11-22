// =============================================================================
// TabBar.tsx  —  LANGUAGE: TypeScript + JSX (React)
// -----------------------------------------------------------------------------
// The bar fixed at the bottom of a person's phone, with two buttons: Session · Analytics.
// The current tab is highlighted. Switching does NOT reload the page (PhoneApp.tsx), so a live
// session keeps its microphone and Mochi's voice while you look at the analytics.
// =============================================================================

import type { Language } from "../contracts.ts";
import { copyFor } from "../lib/i18n.ts";
import type { Tab } from "../lib/tabs.ts";

export function TabBar({ current, onSelect, lang }: { current: Tab; onSelect: (tab: Tab) => void; lang: Language }) {
  const t = copyFor(lang);
  const tabs: [Tab, string][] = [["session", t.tabSession], ["analytics", t.tabAnalytics]];
  return (
    <nav className="tabbar" aria-label={t.tabsLabel}>
      {tabs.map(([tab, label]) => (
        <button key={tab} type="button" className={`tab ${tab === current ? "on" : ""}`}
          aria-current={tab === current ? "page" : undefined} onClick={() => onSelect(tab)}>
          {label}
        </button>
      ))}
    </nav>
  );
}
