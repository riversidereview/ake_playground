"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useI18n } from "../lib/i18n/context";
import { AboutDialog } from "./about-dialog";

const CLIENT_DOWNLOAD_URL = "/downloads/EndfieldLogsClient_2.10.81_20260802.zip";

export function SiteNavLinks() {
  const pathname = usePathname();
  const { t, locale, setLocale } = useI18n();
  const [rankingMenuOpen, setRankingMenuOpen] = useState(false);
  const rankingMenuRef = useRef<HTMLDivElement | null>(null);

  const rankingMenuItems = [
    {
      href: "/statistics",
      label: t.nav.characterStatistics,
      match: (p: string) => p === "/statistics",
    },
    {
      href: "/boss/dung01_group_bossrush01",
      label: t.nav.crisisReplay,
      match: (p: string) => p.startsWith("/boss/dung01_group_bossrush") || p.startsWith("/boss/dung02_group_bossrush"),
    },
    {
      href: "/boss/dung02_group_minibossrush01",
      label: t.nav.crisisFragments,
      match: (p: string) => p.startsWith("/boss/dung02_group_minibossrush"),
    },
    {
      href: "/boss/indie_group_ccdg",
      label: t.nav.contingencyContract,
      match: (p: string) => p.startsWith("/boss/indie_group_ccdg"),
    },
    {
      href: "/boss/indie_battletower001_ex",
      label: t.nav.echoesOfWar,
      match: (p: string) => /^\/boss\/indie_battletower00[1-8]_ex$/.test(p),
    },
    {
      href: "/boss/indie_hard007_s",
      label: t.nav.shadowPhase1,
      match: (p: string) => /^\/boss\/indie_hard00[1-9]_s$/.test(p),
    },
    {
      href: "/boss/indie_hard013_s",
      label: t.nav.shadowPhase2,
      match: (p: string) => /^\/boss\/indie_hard01[0-5]_s$/.test(p),
    },
    {
      href: "/boss/indie_hard016_s",
      label: t.nav.shadowPhase3,
      match: (p: string) => /^\/boss\/indie_hard0(?:1[6-9]|2[0-1])_s$/.test(p),
    },
    {
      href: "/boss/indie_hard022_s",
      label: t.nav.shadowPhase4,
      match: (p: string) => /^\/boss\/indie_hard02[2-5]_s$/.test(p),
    },
  ];

  useEffect(() => {
    if (!rankingMenuOpen) {
      return;
    }

    function handlePointerDown(event: MouseEvent) {
      if (!rankingMenuRef.current?.contains(event.target as Node)) {
        setRankingMenuOpen(false);
      }
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setRankingMenuOpen(false);
      }
    }

    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [rankingMenuOpen]);

  const toggleLanguage = () => {
    setLocale(locale === "en" ? "zh" : "en");
  };

  return (
    <>
      {/* <AboutDialog /> */}
      <Link className={`nav-link${pathname === "/" ? " is-active" : ""}`} href="/">
        {t.common.home}
      </Link>
      {/* <a className="nav-link" href={CLIENT_DOWNLOAD_URL}>
        {t.common.downloadClient}
      </a> */}
      <div className="ranking-menu" ref={rankingMenuRef}>
        <button
          aria-expanded={rankingMenuOpen}
          aria-haspopup="menu"
          className={`nav-link ranking-menu-trigger${
            pathname.startsWith("/boss/") || pathname === "/statistics" ? " is-active" : ""
          }${rankingMenuOpen ? " is-open" : ""}`}
          onClick={() => setRankingMenuOpen((current) => !current)}
          type="button"
        >
          <span>{t.common.leaderboards}</span>
          <span className="ranking-menu-caret" aria-hidden="true">
            ▾
          </span>
        </button>
        {rankingMenuOpen ? (
          <div className="ranking-menu-panel">
            {rankingMenuItems.map((item) => (
              <Link
                className={`ranking-menu-item${item.match(pathname) ? " is-active" : ""}`}
                href={item.href}
                key={item.href}
                onClick={() => setRankingMenuOpen(false)}
              >
                {item.label}
              </Link>
            ))}
          </div>
        ) : null}
      </div>
      <button
        aria-label="Toggle language"
        className="nav-link language-toggle-btn"
        onClick={toggleLanguage}
        title={locale === "en" ? "切换为简体中文" : "Switch to English"}
        type="button"
      >
        <span style={{ fontWeight: 700, fontSize: "0.85rem", opacity: 0.9 }}>
          {locale === "en" ? "🌐 EN" : "🌐 中文"}
        </span>
      </button>
    </>
  );
}
