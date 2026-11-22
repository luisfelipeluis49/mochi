// =============================================================================
// StartPage.tsx  —  LANGUAGE: TypeScript + JSX (React)
// -----------------------------------------------------------------------------
// The page at "/". Each phone belongs to one person:
//   - if this phone already knows its owner (it opened /m?user=... before),
//     it goes straight to that person's "My conversations" page;
//   - otherwise it explains how to open your own link once.
// There is no list of people to choose from: Tasnim's phone shows Tasnim's page,
// Matheus's phone shows Matheus's. Links to Mochi's screen and the projector are
// here for whoever sets up the device.
// =============================================================================

import { useEffect } from "react";
import type { Language } from "../contracts.ts";
import { copyFor } from "../lib/i18n.ts";
import { rememberedUser } from "../lib/people.ts";
import { Face } from "./HomeView.tsx";

/** Add the current options (mock, lang, speed, debug, people) to a link, so the next page behaves the same. */
function withOptions(path: string): string {
  const now = new URLSearchParams(window.location.search);
  const [base, query] = path.split("?");
  const all = new URLSearchParams(query);
  for (const k of ["mock", "lang", "speed", "debug", "people"]) {
    const v = now.get(k);
    if (v) all.set(k, v);
  }
  const qs = all.toString();
  return qs ? `${base}?${qs}` : base;
}

export function StartPage({ lang }: { lang: Language }) {
  const t = copyFor(lang);
  const owner = rememberedUser();

  // This phone knows its owner: go to their page.
  useEffect(() => {
    if (owner) window.location.replace(withOptions(`/m?user=${owner}`));
  }, [owner]);
  if (owner) return null;

  return (
    <main className="mobile start">
      <div className="start-hero">
        <Face awake small />
        <h1>Mochi</h1>
        <p className="subtitle">{t.startSubtitle}</p>
      </div>

      {/* First time on this phone: open your own link once */}
      <section className="practice">
        <h2>{t.firstTimeTitle}</h2>
        <p className="first-time">{t.firstTimeText}</p>
        <code className="your-link">{window.location.origin}/m?user=<b>{t.yourName}</b></code>
      </section>

      {/* For whoever sets up the device and the projector */}
      <section>
        <h2>{t.screensTitle}</h2>
        <ul className="conv-list">
          <li><a href={withOptions("/home?device=home_pi_01")}>{t.screenDevice}</a></li>
          <li><a href={withOptions("/audience")}>{t.screenProjector}</a></li>
        </ul>
      </section>

      <p className="consent">{t.mockTip}</p>
    </main>
  );
}
