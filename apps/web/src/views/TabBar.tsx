// =============================================================================
// TabBar.tsx  —  LANGUAGE: TypeScript + JSX (React)
// -----------------------------------------------------------------------------
// The bar fixed at the bottom of a person's phone pages, with two buttons:
//   Analytics (/m)  ·  Conversations (/me)
// The current page's button is highlighted. Only on the phone pages, never on Mochi's screen or the projector.
// =============================================================================

import type { Language } from "../contracts.ts";
import { copyFor } from "../lib/i18n.ts";
import { type Tab, tabHref } from "../lib/tabs.ts";

export function TabBar({ current, search, lang }: { current: Tab; search: string; lang: Language }) {
  const t = copyFor(lang);
  const tabs: [Tab, string][] = [["analytics", t.tabAnalytics], ["conversations", t.tabConversations]];
  return (
    <nav className="tabbar" aria-label={t.tabsLabel}>
      {tabs.map(([tab, label]) => (
        <a key={tab} href={tabHref(tab, search)} className={`tab ${tab === current ? "on" : ""}`}
          aria-current={tab === current ? "page" : undefined}>
          {label}
        </a>
      ))}
    </nav>
  );
}
