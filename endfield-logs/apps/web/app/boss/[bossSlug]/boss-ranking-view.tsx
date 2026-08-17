"use client";

import Link from "next/link";

import { CharacterAvatar } from "../../../components/character-avatar";
import { ContractTagSummary } from "../../../components/contract-tag-summary";
import type { BossRankingResponse } from "../../../lib/api/types";
import { hasContractTagData } from "../../../lib/contract-tags";
import { formatBossDisplayName, formatBossEyebrow } from "../../../lib/format/boss-display";
import { formatDurationMs } from "../../../lib/format/duration";
import { useI18n } from "../../../lib/i18n/context";
import { PROFESSION_ABBREVIATION_MAP, PROFESSION_NAMES, getLocalizedCharacterName } from "../../../lib/i18n/terms";

type BossRankingViewProps = {
  ranking: BossRankingResponse;
  hotBosses: {
    bossSlug: string;
    bossName: string;
    dungeonName: string;
  }[];
  metric: "dps" | "rdps";
};

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

function formatBattleTime(isoString: string, locale: string): string {
  return new Intl.DateTimeFormat(locale === "zh" ? "zh-CN" : "en-US", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(isoString));
}

function getBossDirectoryGroup(dungeonName: string): string {
  const shadowMonumentMatch = dungeonName.match(/^影拓丰碑\d+期/);
  if (shadowMonumentMatch) {
    return shadowMonumentMatch[0];
  }
  return dungeonName;
}

export function BossRankingView({ ranking, hotBosses, metric }: BossRankingViewProps) {
  const { t, locale } = useI18n();

  const currentDirectoryGroup = getBossDirectoryGroup(ranking.dungeonName);
  const relatedBosses = hotBosses.filter((boss) => getBossDirectoryGroup(boss.dungeonName) === currentDirectoryGroup);
  const bossChips = relatedBosses.length > 0 ? relatedBosses : hotBosses;
  const showContractTags = ranking.rows.some((row) => hasContractTagData(row.contractTagScore, row.contractTags));
  const displayTitle = formatBossDisplayName(ranking, locale);
  const displayEyebrow = formatBossEyebrow(ranking, locale);
  const showCharacterStatistics = ranking.bossSlug !== "indie_group_ccdg";
  const rankingRuleCopy = showContractTags ? t.leaderboard.ruleContract : t.leaderboard.ruleSpeed;

  const abbrevMap = PROFESSION_ABBREVIATION_MAP[locale];
  const nameMap = PROFESSION_NAMES[locale];

  return (
    <div className="page-stack">
      <section className="panel panel-muted boss-ranking-hero">
        <div className="breadcrumbs">
          {t.leaderboard.breadcrumbsHome} / {t.leaderboard.breadcrumbsLeaderboard} / {displayTitle}
        </div>
        <div className="section-heading boss-ranking-hero-heading">
          <div>
            <div className="eyebrow">{displayEyebrow}</div>
            <h1>{displayTitle}</h1>
            <p className="muted boss-ranking-copy">{rankingRuleCopy}</p>
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <Link
              className={metric === "dps" ? "button-primary" : "button-secondary"}
              href={`/boss/${ranking.bossSlug}?metric=dps`}
            >
              DPS
            </Link>
            <Link
              className={metric === "rdps" ? "button-primary" : "button-secondary"}
              href={`/boss/${ranking.bossSlug}?metric=rdps`}
            >
              rDPS
            </Link>
            {showCharacterStatistics ? (
              <Link
                className="button-secondary"
                href={`/boss/${ranking.bossSlug}/statistics?metric=${metric}&range=all`}
              >
                {t.leaderboard.characterStatsLink}
              </Link>
            ) : null}
          </div>
        </div>
        <div className="boss-chip-row">
          {bossChips.map((boss) => (
            <Link
              className={`button-chip${boss.bossSlug === ranking.bossSlug ? " is-active" : ""}`}
              href={`/boss/${boss.bossSlug}?metric=${metric}`}
              key={`chip-${boss.bossSlug}`}
            >
              {formatBossDisplayName(boss, locale)}
            </Link>
          ))}
        </div>
      </section>

      <section className="panel profession-summary-panel">
        <div className="table-toolbar profession-summary-toolbar">
          <div>
            <div className="eyebrow">{t.leaderboard.professionUsageTitle}</div>
            <h2 style={{ margin: "6px 0 0" }}>{t.leaderboard.professionUsageSubtitle}</h2>
          </div>
          <div className="boss-filter-row">
            <span className="pill">
              {locale === "en" ? "Metric: " : "当前口径："}
              {metric === "dps" ? "DPS" : "rDPS"}
            </span>
            <span className="pill">
              {locale === "en" ? "Entries: " : "上榜记录："}
              {ranking.rows.length}
            </span>
          </div>
        </div>
        <div className="profession-summary-grid">
          {ranking.professionGroups.map((group) => {
            const profLabel = nameMap[group.profession] || group.profession;
            const profAbbrev = abbrevMap[group.profession] || group.profession.slice(0, 3).toUpperCase();
            return (
              <section className="profession-group-card" key={group.profession}>
                <header className="profession-group-header">
                  <span className="profession-badge" data-profession={group.profession} title={profLabel}>
                    {profAbbrev}
                  </span>
                  <strong>{profLabel}</strong>
                </header>
                {group.entries.length > 0 ? (
                  <div className="profession-entry-list">
                    {group.entries.map((entry) => {
                      const entryCharName = getLocalizedCharacterName(entry.characterName, locale);
                      return (
                        <div className="profession-entry" key={`${group.profession}-${entry.characterName}`}>
                          <span className="profession-entry-name character-inline">
                            <CharacterAvatar avatarUrl={entry.avatarUrl} name={entryCharName} size="sm" />
                            <span>{entryCharName}</span>
                          </span>
                          <span className="profession-entry-percent">{entry.usagePercent.toFixed(1)}%</span>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div className="profession-empty">
                    {locale === "en" ? "No operators in this class yet." : "当前榜单里还没有这个职业的上榜角色。"}
                  </div>
                )}
              </section>
            );
          })}
        </div>
      </section>

      <section className="panel">
        <div className="table-toolbar">
          <div>
            <div className="eyebrow">{t.common.leaderboards}</div>
            <h2 style={{ margin: "6px 0 0" }}>{displayTitle}</h2>
          </div>
          <span className="muted">
            {locale === "en"
              ? "Each account retains only its best valid clear under current leaderboard rules."
              : "每个账号仅保留当前榜单规则下最好的一条有效通关记录。"}
          </span>
        </div>
        <div className="table-wrap">
          <table className="data-table ranking-report-table">
            <thead>
              <tr>
                <th>{t.leaderboard.tableRank}</th>
                <th>{t.leaderboard.tableOperator}</th>
                <th>{t.leaderboard.tableUploader}</th>
                <th>{t.leaderboard.tableClearTime}</th>
                {showContractTags ? <th>{t.leaderboard.tableTags}</th> : null}
                <th>{metric === "dps" ? "Total DPS" : "Total rDPS"}</th>
                <th>{t.leaderboard.tableTeamComposition}</th>
                <th>{t.leaderboard.tableBattleDate}</th>
                <th>{t.home.tableActions}</th>
              </tr>
            </thead>
            <tbody>
              {ranking.rows.length === 0 ? (
                <tr>
                  <td colSpan={showContractTags ? 9 : 8} style={{ textAlign: "center", padding: 32 }}>
                    <span className="muted">{t.leaderboard.noData}</span>
                  </td>
                </tr>
              ) : (
                ranking.rows.map((row) => {
                  const rankTone = getRankTone(row.scorePercent);
                  const charProfLabel = nameMap[row.characterProfession] || row.characterProfession;
                  const charProfAbbrev =
                    abbrevMap[row.characterProfession] || row.characterProfession.slice(0, 3).toUpperCase();
                  return (
                    <tr className={row.rank === 1 ? "is-featured" : undefined} key={row.battleId}>
                      <td className="ranking-rank-cell">
                        <div className={`ranking-rank-value ${rankTone}`}>{row.rank}</div>
                        <small className={`ranking-rank-percent ${rankTone}`}>{row.scorePercent}%</small>
                      </td>
                      <td>
                        <div className="ranking-character-cell">
                          <CharacterAvatar
                            avatarUrl={row.characterAvatarUrl}
                            characterKey={row.characterKey}
                            name={getLocalizedCharacterName(row.characterName || row.characterKey, locale)}
                          />
                          <div>
                            <strong className="character-inline">
                              <span>{getLocalizedCharacterName(row.characterName || row.characterKey, locale)}</span>
                              <span
                                className="profession-badge"
                                data-profession={row.characterProfession}
                                title={charProfLabel}
                              >
                                {charProfAbbrev}
                              </span>
                            </strong>
                            <small>{charProfLabel}</small>
                          </div>
                        </div>
                      </td>
                      <td>
                        <Link
                          className="ranking-account-link"
                          href={`/records/${encodeURIComponent(row.accountId)}`}
                          title={`View ${row.accountDisplayName}'s records`}
                        >
                          {row.accountDisplayName}
                        </Link>
                      </td>
                      <td>{formatDurationMs(row.durationMs)}</td>
                      {showContractTags ? (
                        <td>
                          {hasContractTagData(row.contractTagScore, row.contractTags) ? (
                            <ContractTagSummary compact score={row.contractTagScore} tags={row.contractTags} />
                          ) : (
                            <span className="muted">-</span>
                          )}
                        </td>
                      ) : null}
                      <td>
                        <div className="ranking-metric-cell">
                          <strong>{Math.round(metric === "dps" ? row.dps : row.rdps).toLocaleString()}</strong>
                        </div>
                      </td>
                      <td>
                        <div className="ranking-roster-grid">
                          {row.rosterEntries.map((entry) => {
                            const entryProfAbbrev =
                              abbrevMap[entry.profession] || entry.profession.slice(0, 3).toUpperCase();
                            const entryProfLabel = nameMap[entry.profession] || entry.profession;
                            const entryCharName = getLocalizedCharacterName(entry.characterName, locale);
                            return (
                              <span className="ranking-roster-chip" key={`${row.battleId}-${entry.characterName}`}>
                                <CharacterAvatar avatarUrl={entry.avatarUrl} name={entryCharName} size="sm" />
                                <span>{entryCharName}</span>
                                <span
                                  className="profession-badge"
                                  data-profession={entry.profession}
                                  title={entryProfLabel}
                                >
                                  {entryProfAbbrev}
                                </span>
                              </span>
                            );
                          })}
                        </div>
                      </td>
                      <td>{formatBattleTime(row.battleEndAt, locale)}</td>
                      <td>
                        <Link className="button-chip" href={`/battle/${row.battleId}?metric=${metric}`}>
                          {locale === "en" ? "Report" : "查看"}
                        </Link>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
