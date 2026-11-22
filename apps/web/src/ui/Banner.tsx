// A non-blocking banner at the top of a screen: a problem (role="alert") or a notice with actions.
import type { ReactNode } from "react";
import { type UiLang, t } from "../lib/i18n.ts";
import { Icon } from "./Icons.tsx";

export interface BannerProps {
  lang: UiLang;
  tone: "problem" | "notice";
  title?: string;
  children?: ReactNode;
  actions?: ReactNode;
  onDismiss?: () => void;
}

export function Banner({ lang, tone, title, children, actions, onDismiss }: BannerProps) {
  return (
    <div className={`banner banner-${tone}`} role={tone === "problem" ? "alert" : "status"}>
      <span className="banner-icon" aria-hidden="true"><Icon name={tone === "problem" ? "alert" : "mic"} size={20} /></span>
      <div className="banner-text">
        {title && <strong>{title}</strong>}
        {children && <span>{children}</span>}
        {actions && <div className="banner-actions">{actions}</div>}
      </div>
      {onDismiss && (
        <button type="button" className="banner-close" onClick={onDismiss} aria-label={t(lang, "dismiss")}>×</button>
      )}
    </div>
  );
}
