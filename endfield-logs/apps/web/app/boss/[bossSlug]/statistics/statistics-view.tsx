"use client";

import type { CSSProperties } from "react";
import Link from "next/link";

import { CharacterAvatar } from "../../../../components/character-avatar";
import type { BossCharacterStatisticsResponse } from "../../../../lib/api/types";
import { formatBossDisplayName, formatBossEyebrow } from "../../../../lib/format/boss-display";
import { useI18n } from "../../../../lib/i18n/context";
import { PROFESSION_NAMES, getLocalizedCharacterName } from "../../../../lib/i18n/terms";

type StatisticsRange = BossCharacterStatisticsResponse["range"];
type StatisticsMetric = BossCharacterStatisticsResponse["metric"];
type StatisticsPotential = BossCharacterStatisticsResponse["potential"];
type StatisticsRow = BossCharacterStatisticsResponse["rows"][number];

type StatisticsViewProps = {
  statistics: BossCharacterStatisticsResponse;
  bossSlug: string;
  metric: StatisticsMetric;
  timeRange: StatisticsRange;
  potentialRange: StatisticsPotential;
};

const chartColors = [
  "#b98cff",
  "#58c79a",
  "#f08aa9",
  "#70a8ff",
  "#f4bd62",
  "#60d4d0",
  "#ed8585",
  "#8bc66f",
  "#d997ff",
  "#ff986c",
  "#7cc4ff",
  "#e6d273",
  "#a7a1ff",
  "#66d097",
  "#ee9aca",
];

function formatMetricValue(value: number | null, locale: string): string {
  return value === null ? "—" : Math.round(value).toLocaleString(locale === "zh" ? "zh-CN" : "en-US");
}

function buildChartDomain(rows: StatisticsRow[]): { min: number; max: number } {
  const values = rows.flatMap((row) =>
    [row.lowerWhisker, row.upperWhisker].filter(
      (value): value is number => value !== null && Number.isFinite(value),
    ),
  );
  if (values.length === 0) {
    return { min: 0, max: 100 };
  }
  const observedMin = Math.min(...values);
  const observedMax = Math.max(...values);
  const observedSpan = Math.max(observedMax - observedMin, observedMax * 0.08, 1);
  return {
    min: Math.max(0, observedMin - observedSpan * 0.06),
    max: observedMax + observedSpan * 0.08,
  };
}

function chartPosition(
  value: number | null,
  domain: { min: number; max: number },
  scaleEnd = 100,
): number {
  if (value === null || domain.max <= domain.min) {
    return 0;
  }
  return Math.min(scaleEnd, Math.max(0, ((value - domain.min) / (domain.max - domain.min)) * scaleEnd));
}

function buildChartStyle(
  row: StatisticsRow,
  index: number,
  domain: { min: number; max: number },
  scaleEnd: number,
): CSSProperties {
  const rawP25 = chartPosition(row.p25, domain, scaleEnd);
  const rawP75 = chartPosition(row.p75, domain, scaleEnd);
  const boxCenter = (rawP25 + rawP75) / 2;
  const minimumBoxWidth = 1.4;
  const visibleP25 =
    rawP75 - rawP25 < minimumBoxWidth ? Math.max(0, boxCenter - minimumBoxWidth / 2) : rawP25;
  const visibleP75 =
    rawP75 - rawP25 < minimumBoxWidth ? Math.min(scaleEnd, boxCenter + minimumBoxWidth / 2) : rawP75;
  return {
    "--statistics-color": chartColors[index % chartColors.length],
    "--statistics-p10": `${chartPosition(row.p10, domain, scaleEnd)}%`,
    "--statistics-p25": `${visibleP25}%`,
    "--statistics-p50": `${chartPosition(row.median, domain, scaleEnd)}%`,
    "--statistics-p75": `${visibleP75}%`,
    "--statistics-p90": `${chartPosition(row.p90, domain, scaleEnd)}%`,
    "--statistics-max": `${chartPosition(row.upperWhisker, domain, scaleEnd)}%`,
  } as CSSProperties;
}

function outlierPosition(
  row: StatisticsRow,
  outlierIndex: number,
  domain: { min: number; max: number },
  scaleEnd: number,
): number {
  const outlier = row.outliers[outlierIndex];
  if (outlier.value >= domain.min && outlier.value <= domain.max) {
    return chartPosition(outlier.value, domain, scaleEnd);
  }
  const sameSide = row.outliers.filter((entry) =>
    outlier.value > domain.max ? entry.value > domain.max : entry.value < domain.min,
  );
  const sideIndex = sameSide.findIndex((entry) => entry.value === outlier.value);
  const progress = (sideIndex + 1) / (sameSide.length + 1);
  if (outlier.value > domain.max) {
    return scaleEnd + 1.5 + (100 - scaleEnd - 3) * progress;
  }
  return Math.max(0.8, 5.5 * progress);
}

export function StatisticsView({
  statistics,
  bossSlug,
  metric,
  timeRange,
  potentialRange,
}: StatisticsViewProps) {
  const { t, locale } = useI18n();

  const isAllScope = bossSlug === "__all__";
  const displayTitle = isAllScope ? t.statistics.allBossesTitle : formatBossDisplayName(statistics, locale);
  const displayEyebrow = isAllScope
    ? locale === "en"
      ? "ALL ENCOUNTERS"
      : "全部副本"
    : formatBossEyebrow(statistics, locale);
  const metricLabel = metric === "rdps" ? "rDPS" : "DPS";

  const domain = buildChartDomain(statistics.rows);
  const hasOverflowOutliers = statistics.rows.some((row) =>
    row.outliers.some((outlier) => outlier.value < domain.min || outlier.value > domain.max),
  );
  const scaleEnd = hasOverflowOutliers ? 92 : 100;
  const axisTickCount = 9;
  const axisTicks = Array.from(
    { length: axisTickCount },
    (_, index) => domain.min + ((domain.max - domain.min) * index) / (axisTickCount - 1),
  );

  const rangeOptions: { key: StatisticsRange; label: string }[] = [
    { key: "7d", label: t.statistics.range7d },
    { key: "14d", label: t.statistics.range14d },
    { key: "30d", label: t.statistics.range30d },
    { key: "all", label: t.statistics.rangeAll },
  ];

  const potentialOptions: { key: StatisticsPotential; label: string }[] = [
    { key: "all", label: t.statistics.potentialAll },
    { key: "0", label: t.statistics.potentialP0 },
    { key: "1-5", label: t.statistics.potentialP1P5 },
  ];

  const statisticsHref = (
    nextMetric: StatisticsMetric,
    nextRange: StatisticsRange,
    nextPotential: StatisticsPotential,
  ) =>
    isAllScope
      ? `/statistics?metric=${nextMetric}&range=${nextRange}&potential=${nextPotential}`
      : `/boss/${bossSlug}/statistics?metric=${nextMetric}&range=${nextRange}&potential=${nextPotential}`;

  const nameMap = PROFESSION_NAMES[locale];

  return (
    <div className="page-stack">
      <section className="panel panel-muted boss-ranking-hero">
        <div className="breadcrumbs">
          {isAllScope
            ? `${t.leaderboard.breadcrumbsHome} / ${t.leaderboard.breadcrumbsLeaderboard} / ${t.statistics.allBossesTitle}`
            : `${t.leaderboard.breadcrumbsHome} / ${t.leaderboard.breadcrumbsLeaderboard} / ${displayTitle} / ${t.common.statistics}`}
        </div>
        <div className="section-heading boss-ranking-hero-heading">
          <div>
            <div className="eyebrow">{displayEyebrow}</div>
            <h1>{isAllScope ? displayTitle : `${displayTitle} · ${t.common.statistics}`}</h1>
            <p className="muted boss-ranking-copy">
              {t.statistics.sampleSummary(
                statistics.eligibleBattleCount,
                statistics.totalSampleCount,
                statistics.totalOutlierCount,
                isAllScope ? statistics.includedBossCount : undefined,
              )}
            </p>
          </div>
          <div className="boss-filter-row">
            {isAllScope ? (
              <Link className="button-secondary" href="/">
                {t.common.home}
              </Link>
            ) : (
              <>
                <Link className="button-secondary" href={`/boss/${bossSlug}?metric=${metric}`}>
                  {locale === "en" ? "Leaderboard" : "返回竞速榜"}
                </Link>
                <Link
                  className="button-secondary"
                  href={`/statistics?metric=${metric}&range=${timeRange}&potential=${potentialRange}`}
                >
                  {t.statistics.allBossesTitle}
                </Link>
              </>
            )}
            <Link
              className={metric === "dps" ? "button-primary" : "button-secondary"}
              href={statisticsHref("dps", timeRange, potentialRange)}
            >
              DPS
            </Link>
            <Link
              className={metric === "rdps" ? "button-primary" : "button-secondary"}
              href={statisticsHref("rdps", timeRange, potentialRange)}
            >
              rDPS
            </Link>
          </div>
        </div>
        <div className="boss-filter-row character-statistics-range-row" aria-label="Time range filter">
          {rangeOptions.map((option) => (
            <Link
              className={`button-chip${timeRange === option.key ? " is-active" : ""}`}
              href={statisticsHref(metric, option.key, potentialRange)}
              key={option.key}
            >
              {option.label}
            </Link>
          ))}
        </div>
        <div className="boss-filter-row character-statistics-range-row" aria-label="Potential filter">
          <span className="character-statistics-filter-label">{t.statistics.potentialFilter}</span>
          {potentialOptions.map((option) => (
            <Link
              className={`button-chip${potentialRange === option.key ? " is-active" : ""}`}
              href={statisticsHref(metric, timeRange, option.key)}
              key={option.key}
            >
              {option.label}
            </Link>
          ))}
        </div>
      </section>

      <section className="panel character-statistics-summary">
        <div className="table-toolbar">
          <div>
            <div className="eyebrow">{t.statistics.eyebrow}</div>
            <h2 style={{ margin: "6px 0 0" }}>
              {locale === "en" ? `Ranked by ${metricLabel}` : `按照 ${metricLabel} 排序`}
            </h2>
          </div>
          <div className="boss-filter-row">
            <span className="pill">
              {t.statistics.potentialFilter}:{" "}
              {potentialOptions.find((option) => option.key === statistics.potential)?.label}
            </span>
            {isAllScope ? (
              <span className="pill">
                {locale === "en" ? "Encounters: " : "覆盖副本："}
                {statistics.includedBossCount}
              </span>
            ) : null}
            <span className="pill">
              {locale === "en" ? "Eligible Battles: " : "有效战斗："}
              {statistics.eligibleBattleCount}
            </span>
            <span className="pill">
              {locale === "en" ? "Samples: " : "角色样本："}
              {statistics.totalSampleCount}
            </span>
            <span className="pill">
              {locale === "en" ? "Outliers: " : "离群样本："}
              {statistics.totalOutlierCount}
            </span>
            <span className="pill">
              {locale === "en" ? "Min Samples: " : "最低正式样本："}
              {statistics.minimumSampleCount}
            </span>
          </div>
        </div>
        <p className="muted character-statistics-note">{t.statistics.boxPlotHelp}</p>

        <div className="character-statistics-chart-scroll">
          <div className="character-statistics-chart">
            {statistics.rows.map((row, index) => {
              const profLabel = nameMap[row.characterProfession] || row.characterProfession;
              const charName = getLocalizedCharacterName(row.characterName, locale);
              return (
                <div
                  className={`character-statistics-chart-row${row.insufficientSamples ? " is-insufficient" : ""}`}
                  key={row.characterKey}
                  style={buildChartStyle(row, index, domain, scaleEnd)}
                >
                  <div className="character-statistics-character">
                    <CharacterAvatar avatarUrl={row.characterAvatarUrl} characterKey={row.characterKey} name={charName} size="sm" />
                    <div>
                      <strong>{charName}</strong>
                      <small>
                        {profLabel} · {row.normalSampleCount} {locale === "en" ? "samples" : "样本"}
                        {row.outlierCount > 0
                          ? ` · ${row.outlierCount} ${locale === "en" ? "outliers" : "离群"}`
                          : ""}
                      </small>
                    </div>
                  </div>
                  {row.sampleCount > 0 ? (
                    <div
                      aria-label={`${row.characterName} ${metricLabel}: P10 ${formatMetricValue(
                        row.p10,
                        locale,
                      )}, Median ${formatMetricValue(row.median, locale)}, P90 ${formatMetricValue(
                        row.p90,
                        locale,
                      )}, Outliers: ${row.outlierCount}`}
                      className="character-statistics-track"
                    >
                      {axisTicks.map((_, tickIndex) => (
                        <span
                          className="character-statistics-grid-line"
                          key={`${row.characterKey}-grid-${tickIndex}`}
                          style={{ left: `${(tickIndex * scaleEnd) / (axisTickCount - 1)}%` }}
                        />
                      ))}
                      <span className="character-statistics-whisker" />
                      <span className="character-statistics-whisker-cap is-start" />
                      <span className="character-statistics-whisker-cap is-end" />
                      <span className="character-statistics-box" />
                      <span className="character-statistics-median" />
                      <span
                        className="character-statistics-maximum"
                        title={
                          locale === "en"
                            ? `Max normal sample: ${formatMetricValue(row.upperWhisker, locale)}`
                            : `非离群样本最高 ${formatMetricValue(row.upperWhisker, locale)}`
                        }
                      />
                      {row.outliers.map((outlier, outlierIndex) => (
                        <span
                          className="character-statistics-outlier"
                          key={`${row.characterKey}-outlier-${outlier.value}`}
                          style={
                            {
                              "--statistics-outlier-size": "8px",
                              left: `${outlierPosition(row, outlierIndex, domain, scaleEnd)}%`,
                              top: "50%",
                            } as CSSProperties
                          }
                          title={
                            locale === "en"
                              ? `Outlier ${formatMetricValue(outlier.value, locale)}${
                                  outlier.count > 1 ? ` × ${outlier.count}` : ""
                                }`
                              : `离群值 ${formatMetricValue(outlier.value, locale)}${
                                  outlier.count > 1 ? ` × ${outlier.count}` : ""
                                }`
                          }
                        />
                      ))}
                    </div>
                  ) : (
                    <div className="character-statistics-track is-empty">
                      {locale === "en" ? "No valid samples" : "暂无有效样本"}
                    </div>
                  )}
                </div>
              );
            })}
            <div aria-hidden="true" className="character-statistics-axis">
              <span />
              <div className="character-statistics-axis-track">
                {axisTicks.map((tick, index) => (
                  <span
                    className={`character-statistics-axis-tick${index === 0 ? " is-first" : ""}${
                      index === axisTickCount - 1 ? " is-last" : ""
                    }`}
                    key={`axis-${index}`}
                    style={{ left: `${(index * scaleEnd) / (axisTickCount - 1)}%` }}
                  >
                    {formatMetricValue(tick, locale)}
                  </span>
                ))}
                <strong className="character-statistics-axis-title">
                  {metricLabel === "DPS" ? "DPS" : "rDPS"}
                </strong>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="panel">
        <div className="table-toolbar">
          <div>
            <div className="eyebrow">{t.common.statistics}</div>
            <h2 style={{ margin: "6px 0 0" }}>{metricLabel} {locale === "en" ? "Percentiles" : "分位数"}</h2>
          </div>
          <span className="muted">
            {locale === "en"
              ? `Operators with fewer than ${statistics.minimumSampleCount} samples are not formally ranked.`
              : `少于 ${statistics.minimumSampleCount} 个样本的角色不参与正式排名。`}
          </span>
        </div>
        <div className="table-wrap">
          <table className="data-table character-statistics-table">
            <thead>
              <tr>
                <th>{t.statistics.tableRank}</th>
                <th>{t.statistics.tableOperator}</th>
                <th>{t.statistics.tableSamples}</th>
                <th>P10</th>
                <th>P25</th>
                <th>{t.statistics.tableMedian}</th>
                <th>P75</th>
                <th>P90</th>
                <th>{locale === "en" ? "Max" : "最高"}</th>
              </tr>
            </thead>
            <tbody>
              {statistics.rows.map((row) => {
                const profLabel = nameMap[row.characterProfession] || row.characterProfession;
                const charName = getLocalizedCharacterName(row.characterName || row.characterKey, locale);
                return (
                  <tr
                    className={row.insufficientSamples ? "is-insufficient" : undefined}
                    key={`table-${row.characterKey}`}
                  >
                    <td>{row.rank ?? "—"}</td>
                    <td>
                      <div className="ranking-character-cell">
                        <CharacterAvatar avatarUrl={row.characterAvatarUrl} characterKey={row.characterKey} name={charName} size="sm" />
                        <div>
                          <strong>{charName}</strong>
                          <small>{profLabel}</small>
                        </div>
                      </div>
                    </td>
                    <td>
                      <strong>{row.sampleCount}</strong>
                      <small>
                        {locale === "en" ? "Normal: " : "正常 "}
                        {row.normalSampleCount}
                      </small>
                      {row.outlierCount > 0 ? (
                        <small className="character-statistics-outlier-count">
                          {locale === "en" ? "Outliers: " : "离群 "}
                          {row.outlierCount}
                        </small>
                      ) : null}
                      {row.insufficientSamples ? (
                        <small className="character-statistics-warning">{t.statistics.insufficientSamplesBadge}</small>
                      ) : null}
                    </td>
                    <td>{formatMetricValue(row.p10, locale)}</td>
                    <td>{formatMetricValue(row.p25, locale)}</td>
                    <td className="character-statistics-median-cell">{formatMetricValue(row.median, locale)}</td>
                    <td>{formatMetricValue(row.p75, locale)}</td>
                    <td>{formatMetricValue(row.p90, locale)}</td>
                    <td>{formatMetricValue(row.maximum, locale)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
