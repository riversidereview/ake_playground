"use client";

import Link from "next/link";
import type { CSSProperties } from "react";

import { CharacterAvatar } from "../components/character-avatar";
import { ContractTagSummary } from "../components/contract-tag-summary";
import type { HotBossCard } from "../lib/api/types";
import { hasContractTagData } from "../lib/contract-tags";
import { formatBossDisplayName, formatBossEyebrow } from "../lib/format/boss-display";
import { formatDurationMs } from "../lib/format/duration";
import { useI18n } from "../lib/i18n/context";
import { getLocalizedCharacterName, resolveAssetUrl } from "../lib/i18n/terms";

function getRankTone(scorePercent: number): string {
  if (scorePercent >= 100) {
    return "is-gold";
  }
  if (scorePercent >= 95) {
    return "is-orange";
  }
  if (scorePercent >= 75) {
    return "is-purple";
  }
  if (scorePercent >= 50) {
    return "is-blue";
  }
  if (scorePercent >= 25) {
    return "is-green";
  }
  return "is-gray";
}

const bossCardBackgrounds: Record<string, string> = {
  dung01_group_bossrush01: "/images/boss-bg/dung01_group_bossrush01.webp",
  dung01_group_bossrush02: "/images/boss-bg/dung01_group_bossrush02.webp",
  dung01_group_bossrush03: "/images/boss-bg/dung01_group_bossrush03.webp",
  dung02_group_bossrush01: "/images/boss-bg/dung02_group_bossrush01.webp",
  dung02_group_bossrush02: "/images/boss-bg/dung02_group_bossrush02.webp",
  dung02_group_bossrush03: "/images/boss-bg/dung02_group_bossrush03.webp",
  dung02_group_minibossrush01: "/images/boss-bg/dung02_group_minibossrush01.webp",
  dung02_group_minibossrush02: "/images/boss-bg/dung02_group_minibossrush02.webp",
  indie_group_ccdg: "/images/boss-bg/indie_group_ccdg.webp",
  indie_battletower001_ex: "/images/boss-bg/indie_group_twdg.svg",
  indie_battletower002_ex: "/images/boss-bg/indie_group_twdg.svg",
  indie_battletower003_ex: "/images/boss-bg/indie_group_twdg.svg",
  indie_battletower004_ex: "/images/boss-bg/indie_group_twdg.svg",
  indie_battletower005_ex: "/images/boss-bg/indie_group_twdg.svg",
  indie_battletower006_ex: "/images/boss-bg/indie_group_twdg.svg",
  indie_battletower007_ex: "/images/boss-bg/indie_group_twdg.svg",
  indie_battletower008_ex: "/images/boss-bg/indie_group_twdg.svg",
  indie_hard001: "/images/boss-bg/indie_hard001_s.webp",
  indie_hard001_s: "/images/boss-bg/indie_hard001_s.webp",
  indie_hard002: "/images/boss-bg/indie_hard002_s.webp",
  indie_hard002_s: "/images/boss-bg/indie_hard002_s.webp",
  indie_hard003: "/images/boss-bg/indie_hard003_s.webp",
  indie_hard003_s: "/images/boss-bg/indie_hard003_s.webp",
  indie_hard004: "/images/boss-bg/indie_hard004_s.webp",
  indie_hard004_s: "/images/boss-bg/indie_hard004_s.webp",
  indie_hard005: "/images/boss-bg/indie_hard005_s.webp",
  indie_hard005_s: "/images/boss-bg/indie_hard005_s.webp",
  indie_hard006: "/images/boss-bg/indie_hard006_s.webp",
  indie_hard006_s: "/images/boss-bg/indie_hard006_s.webp",
  indie_hard007: "/images/boss-bg/indie_hard007_s.webp",
  indie_hard007_s: "/images/boss-bg/indie_hard007_s.webp",
  indie_hard008: "/images/boss-bg/indie_hard008_s.webp",
  indie_hard008_s: "/images/boss-bg/indie_hard008_s.webp",
  indie_hard009: "/images/boss-bg/indie_hard009_s.webp",
  indie_hard009_s: "/images/boss-bg/indie_hard009_s.webp",
  indie_hard010: "/images/boss-bg/indie_hard010_s.webp",
  indie_hard010_s: "/images/boss-bg/indie_hard010_s.webp",
  indie_hard011: "/images/boss-bg/indie_hard011_s.webp",
  indie_hard011_s: "/images/boss-bg/indie_hard011_s.webp",
  indie_hard012: "/images/boss-bg/indie_hard012_s.webp",
  indie_hard012_s: "/images/boss-bg/indie_hard012_s.webp",
  indie_hard013: "/images/boss-bg/indie_hard013_s.webp",
  indie_hard013_s: "/images/boss-bg/indie_hard013_s.webp",
  indie_hard014: "/images/boss-bg/indie_hard014_s.webp",
  indie_hard014_s: "/images/boss-bg/indie_hard014_s.webp",
  indie_hard015: "/images/boss-bg/indie_hard015_s.webp",
  indie_hard015_s: "/images/boss-bg/indie_hard015_s.webp",
  indie_hard016: "/images/boss-bg/indie_hard016_s.webp",
  indie_hard016_s: "/images/boss-bg/indie_hard016_s.webp",
  indie_hard017: "/images/boss-bg/indie_hard017_s.webp",
  indie_hard017_s: "/images/boss-bg/indie_hard017_s.webp",
  indie_hard018: "/images/boss-bg/indie_hard018_s.webp",
  indie_hard018_s: "/images/boss-bg/indie_hard018_s.webp",
  indie_hard019: "/images/boss-bg/indie_hard019_s.webp",
  indie_hard019_s: "/images/boss-bg/indie_hard019_s.webp",
  indie_hard020: "/images/boss-bg/indie_hard020_s.webp",
  indie_hard020_s: "/images/boss-bg/indie_hard020_s.webp",
  indie_hard021: "/images/boss-bg/indie_hard021_s.webp",
  indie_hard021_s: "/images/boss-bg/indie_hard021_s.webp",
  indie_hard022: "/images/boss-bg/indie_hard022_s.webp",
  indie_hard022_s: "/images/boss-bg/indie_hard022_s.webp",
  indie_hard023: "/images/boss-bg/indie_hard023_s.webp",
  indie_hard023_s: "/images/boss-bg/indie_hard023_s.webp",
  indie_hard024: "/images/boss-bg/indie_hard024_s.webp",
  indie_hard024_s: "/images/boss-bg/indie_hard024_s.webp",
  indie_hard025: "/images/boss-bg/indie_hard025_s.webp",
  indie_hard025_s: "/images/boss-bg/indie_hard025_s.webp",
};

const bossCardPositions: Record<string, string> = {
  dung01_group_bossrush01: "center center",
  dung01_group_bossrush02: "center center",
  dung01_group_bossrush03: "center center",
  dung02_group_bossrush01: "center center",
  dung02_group_bossrush02: "center center",
  dung02_group_minibossrush01: "center center",
  indie_group_ccdg: "center center",
  indie_battletower001_ex: "center center",
  indie_battletower002_ex: "center center",
  indie_battletower003_ex: "center center",
  indie_battletower004_ex: "center center",
  indie_battletower005_ex: "center center",
  indie_battletower006_ex: "center center",
  indie_battletower007_ex: "center center",
  indie_battletower008_ex: "center center",
};

function getBossCardStyle(bossSlug: string): CSSProperties {
  const bg = resolveAssetUrl(bossCardBackgrounds[bossSlug] ?? bossCardBackgrounds.dung01_group_bossrush01);
  return {
    "--boss-card-bg": bg ? `url(${bg})` : undefined,
    "--boss-card-position": bossCardPositions[bossSlug] ?? "center center",
  } as CSSProperties;
}

export function HomeView({ hotBosses }: { hotBosses: HotBossCard[] }) {
  const { t, locale } = useI18n();

  const bossOverviewRows = hotBosses
    .map((boss) => ({
      bossSlug: boss.bossSlug,
      bossName: boss.bossName,
      bossDisplayName: formatBossDisplayName(boss, locale),
      dungeonName: formatBossEyebrow(boss, locale),
      bestRun: boss.topSpeedRuns[0] ?? null,
    }))
    .sort((left, right) => {
      if (!left.bestRun && !right.bestRun) {
        return 0;
      }
      if (!left.bestRun) {
        return 1;
      }
      if (!right.bestRun) {
        return -1;
      }
      return left.bestRun.durationMs - right.bestRun.durationMs;
    });

  return (
    <div className="page-stack">
      <section className="hero-grid">
        <article className="panel panel-muted" style={{ display: "grid", gap: 16 }}>
          <div className="eyebrow">{t.home.eyebrow}</div>
          <div>
            <h1 className="hero-title">{t.home.heroTitle}</h1>
            <p className="hero-copy">{t.home.heroCopy}</p>
          </div>
        </article>
      </section>

      <section className="home-grid">
        <div className="panel" id="crisis-replay-overview" style={{ display: "grid", gap: 14 }}>
          <div className="section-heading">
            <div>
              <div className="eyebrow">{t.home.hotBossesEyebrow}</div>
              <h2>{t.home.hotBossesTitle}</h2>
            </div>
            <span className="muted">{t.home.hotBossesCount(hotBosses.length)}</span>
          </div>

          <div className="grid-cards">
            {hotBosses.map((boss) => (
              <article className="panel-inset boss-card" key={boss.bossSlug} style={getBossCardStyle(boss.bossSlug)}>
                <div className="boss-card-info">
                  <div className="boss-card-head">
                    <div>
                      <div className="eyebrow">{t.home.hotBossesEyebrow}</div>
                      <h3 style={{ margin: "6px 0 0" }}>{t.home.hotBossesTitle}</h3>
                      <div className="eyebrow boss-card-dungeon">{formatBossEyebrow(boss, locale)}</div>
                      <strong className="boss-card-name">{formatBossDisplayName(boss, locale)}</strong>
                    </div>
                  </div>

                  <Link className="button-chip boss-card-link" href={`/boss/${boss.bossSlug}`}>
                    {t.home.enterLeaderboard}
                  </Link>
                </div>

                <div className="boss-card-table-wrap">
                  <table className="mini-table">
                    <thead>
                      <tr>
                        <th>{t.home.tableRank}</th>
                        <th>{t.home.tableMainDps}</th>
                        <th>{t.home.tableUploader}</th>
                        <th>{t.home.tableDuration}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {boss.topSpeedRuns.map((run, index) => (
                        <tr key={run.battleId}>
                          <td>
                            <span className={`mini-rank-badge ${getRankTone(run.scorePercent ?? 0)}`}>
                              #{index + 1}
                            </span>
                          </td>
                          <td>
                            <Link className="character-link" href={`/battle/${run.battleId}`}>
                              <CharacterAvatar
                                avatarUrl={run.characterAvatarUrl}
                                characterKey={run.characterKey}
                                name={getLocalizedCharacterName(run.characterName || run.characterKey, locale)}
                                size="sm"
                              />
                              <span>{getLocalizedCharacterName(run.characterName || run.characterKey, locale)}</span>
                            </Link>
                          </td>
                          <td>{run.uploaderNickname}</td>
                          <td>
                            <div style={{ display: "grid", gap: 4, justifyItems: "center" }}>
                              <span>{formatDurationMs(run.durationMs)}</span>
                              {hasContractTagData(run.contractTagScore, run.contractTags) ? (
                                <ContractTagSummary compact score={run.contractTagScore} tags={run.contractTags} />
                              ) : null}
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </article>
            ))}
          </div>
        </div>

        <aside className="panel panel-muted" style={{ alignContent: "start", display: "grid", gap: 14 }}>
          <div>
            <div className="eyebrow">{t.home.quickDirectory}</div>
            <h2 style={{ margin: "6px 0 0" }}>{t.home.startHere}</h2>
          </div>
          <div className="directory-list">
            <Link className="directory-button" href="/boss/dung01_group_bossrush01">
              <strong>{t.nav.crisisReplay}</strong>
              <small>{locale === "en" ? "6 Featured Encounters" : "固定收录 6 个首领"}</small>
            </Link>
            <Link className="directory-button" href="/boss/dung02_group_minibossrush01">
              <strong>{t.nav.crisisFragments}</strong>
              <small>{locale === "en" ? "Colossal Hou / Shadow Thunder" : "巨山犼兽 / 蚀影噪雷"}</small>
            </Link>
            <Link className="directory-button" href="/boss/indie_group_ccdg">
              <strong>{t.nav.contingencyContract}</strong>
              <small>{locale === "en" ? "Event Speedrun Leaderboard" : "活动榜单"}</small>
            </Link>
            <Link className="directory-button" href="/boss/indie_battletower001_ex">
              <strong>{t.nav.echoesOfWar}</strong>
              <small>{locale === "en" ? "All 8 Cruel Encounters" : "全部 8 个残酷关卡"}</small>
            </Link>
            <Link className="directory-button" href="/boss/indie_hard007_s">
              <strong>{t.nav.shadowPhase1}</strong>
              <small>{locale === "en" ? "9 Torment Instances" : "收录 9 个苦难副本"}</small>
            </Link>
            <Link className="directory-button" href="/boss/indie_hard013_s">
              <strong>{t.nav.shadowPhase2}</strong>
              <small>{locale === "en" ? "Turbid Manifestation · 6 Instances" : "浊流具现 · 6 个苦难副本"}</small>
            </Link>
            <Link className="directory-button" href="/boss/indie_hard016_s">
              <strong>{t.nav.shadowPhase3}</strong>
              <small>{locale === "en" ? "Clamor of Silence · 6 Instances" : "死寂争鸣 · 6 个苦难副本"}</small>
            </Link>
            <Link className="directory-button" href="/boss/indie_hard022_s">
              <strong>{t.nav.shadowPhase4}</strong>
              <small>{locale === "en" ? "Hou in Mountains · 4 Instances" : "山中见犼 · 4 个苦难副本"}</small>
            </Link>
          </div>
        </aside>
      </section>

      <section className="panel">
        <div className="table-toolbar">
          <div>
            <div className="eyebrow">{t.home.bossOverview}</div>
            <h2 style={{ margin: "6px 0 0" }}>{t.home.fastestTableTitle}</h2>
          </div>
          <span className="muted">{t.home.fastestTableSubtitle}</span>
        </div>
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>{t.home.tableBoss}</th>
                <th>{t.home.tableDungeon}</th>
                <th>{t.home.tableFastestRecord}</th>
                <th>{t.home.tableMainDps}</th>
                <th>{t.home.tableUploader}</th>
                <th>{t.home.tableActions}</th>
              </tr>
            </thead>
            <tbody>
              {bossOverviewRows.map((row, index) => (
                <tr className={index === 0 ? "is-featured" : undefined} key={row.bossSlug}>
                  <td>{row.bossDisplayName}</td>
                  <td>{row.dungeonName}</td>
                  <td>
                    {row.bestRun ? (
                      <div style={{ display: "grid", gap: 4 }}>
                        <span>{formatDurationMs(row.bestRun.durationMs)}</span>
                        {hasContractTagData(row.bestRun.contractTagScore, row.bestRun.contractTags) ? (
                          <ContractTagSummary
                            compact
                            score={row.bestRun.contractTagScore}
                            tags={row.bestRun.contractTags}
                          />
                        ) : null}
                      </div>
                    ) : (
                      "--:--"
                    )}
                  </td>
                  <td>
                    {row.bestRun ? (
                      <span className="character-inline">
                        <CharacterAvatar
                          avatarUrl={row.bestRun.characterAvatarUrl}
                          characterKey={row.bestRun.characterKey}
                          name={getLocalizedCharacterName(row.bestRun.characterName || row.bestRun.characterKey, locale)}
                          size="sm"
                        />
                        <span>{getLocalizedCharacterName(row.bestRun.characterName || row.bestRun.characterKey, locale)}</span>
                      </span>
                    ) : (
                      "-"
                    )}
                  </td>
                  <td>{row.bestRun?.uploaderNickname ?? "-"}</td>
                  <td>
                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                      <Link className="button-chip" href={`/boss/${row.bossSlug}`}>
                        {t.common.leaderboards}
                      </Link>
                      {row.bestRun ? (
                        <Link className="button-chip" href={`/battle/${row.bestRun.battleId}`}>
                          {t.common.viewFullReport}
                        </Link>
                      ) : null}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <footer className="site-filing-footer">
        <a href="https://beian.miit.gov.cn/" rel="noopener noreferrer nofollow" target="_blank">
          渝ICP备2025075658号
        </a>
      </footer>
    </div>
  );
}
