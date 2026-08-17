"use client";

import type { ReactNode } from "react";

import { AuthNav } from "../features/auth/auth-nav";
import { useI18n } from "../lib/i18n/context";
import { SiteNavLinks } from "./site-nav-links";

type AppShellProps = {
  children: ReactNode;
};

export function AppShell({ children }: AppShellProps) {
  const { t } = useI18n();

  return (
    <div>
      <header className="site-header">
        <div className="page-shell">
          <div className="site-header-inner">
            <div className="site-brand">
              <div className="site-brand-title">{t.common.siteTitle}</div>
              <div className="site-brand-subtitle">{t.common.siteSubtitle}</div>
            </div>
            <nav className="site-nav">
              <SiteNavLinks />
              <AuthNav />
            </nav>
          </div>
          <div className="site-status-row">
            <span className="pill pill-accent">{t.common.betaBadge}</span>
            <span>{t.common.betaNotice}</span>
          </div>
        </div>
      </header>
      <main className="page-shell page-content">{children}</main>
    </div>
  );
}
