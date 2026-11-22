// The navigation: a bottom tab bar on phones, a left rail on tablets, a side nav on desktops
// (the same markup; styles/app.css lays it out per width). Four items: Session, Training, Digest, Analytics.

import type { MouseEvent } from "react";
import type { User } from "../contracts.ts";
import { initialsOf } from "../lib/identity.ts";
import { type UiLang, t } from "../lib/i18n.ts";
import { NAV_SCREENS, type Screen, pathOf } from "../lib/routes.ts";
import { Icon, type IconName } from "./Icons.tsx";

const ICON: Record<string, IconName> = { session: "session", training: "training", digest: "digest", analytics: "analytics" };
const LABEL = { session: "nav_session", training: "nav_training", digest: "nav_digest", analytics: "nav_analytics" } as const;

export interface NavProps {
  lang: UiLang;
  screen: Screen;
  user: User | null;
  onNavigate: (s: Screen) => void;
}

/** A plain link that navigates in-app on a normal click (a modified click opens a new tab). */
export function linkClick(onNavigate: (s: Screen) => void, s: Screen) {
  return (e: MouseEvent<HTMLAnchorElement>) => {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    e.preventDefault();
    onNavigate(s);
  };
}

export function Avatar({ name, size = "m" }: { name: string; size?: "m" | "l" }) {
  return <span className={`avatar avatar-${size}`} aria-hidden="true">{initialsOf(name)}</span>;
}

export function Nav({ lang, screen, user, onNavigate }: NavProps) {
  return (
    <nav className="nav" aria-label={t(lang, "nav_label")}>
      <span className="nav-wordmark" aria-hidden="true">{t(lang, "app_name")}</span>
      <ul className="nav-list">
        {NAV_SCREENS.map((s) => (
          <li key={s}>
            <a href={pathOf(s)} className="nav-item" aria-current={s === screen ? "page" : undefined} onClick={linkClick(onNavigate, s)}>
              <Icon name={ICON[s]} />
              <span className="nav-label">{t(lang, LABEL[s as keyof typeof LABEL])}</span>
            </a>
          </li>
        ))}
      </ul>
      {user && (
        <a href={pathOf("profile")} className="nav-user" aria-current={screen === "profile" ? "page" : undefined} onClick={linkClick(onNavigate, "profile")} aria-label={t(lang, "profile_open", { name: user.display_name })}>
          <Avatar name={user.display_name} />
          <span className="nav-user-name">{user.display_name}</span>
        </a>
      )}
    </nav>
  );
}
