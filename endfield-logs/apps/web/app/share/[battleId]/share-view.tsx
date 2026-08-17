"use client";

import Link from "next/link";

import { ContractTagSummary } from "../../../components/contract-tag-summary";
import type { ShareSummaryResponse } from "../../../lib/api/types";
import { hasContractTagData } from "../../../lib/contract-tags";
import { formatBossDisplayName, formatBossEyebrow } from "../../../lib/format/boss-display";
import { formatDurationMs } from "../../../lib/format/duration";
import { useI18n } from "../../../lib/i18n/context";

export function ShareView({ summary }: { summary: ShareSummaryResponse }) {
  const { t, locale } = useI18n();

  const hasContractTags = hasContractTagData(summary.contractTagScore, summary.contractTags);
  const displayTitle = formatBossDisplayName(summary, locale);
  const displayEyebrow = formatBossEyebrow(summary, locale);

  return (
    <div className="page-stack">
      <section className="panel panel-muted" style={{ display: "grid", gap: 16, maxWidth: 860 }}>
        <div className="breadcrumbs">
          {t.common.home} / {t.share.breadcrumbsShare} / {displayTitle}
        </div>
        <div className="eyebrow">{displayEyebrow}</div>
        <div>
          <h1 style={{ margin: "0 0 10px" }}>{displayTitle}</h1>
          <p className="muted" style={{ margin: 0 }}>
            {t.share.subtitle}
          </p>
        </div>
        <div className="summary-grid">
          <div className="summary-item">
            <span className="muted">{t.share.duration}</span>
            <strong>{formatDurationMs(summary.durationMs)}</strong>
          </div>
          <div className="summary-item">
            <span className="muted">{t.share.uploader}</span>
            <strong>{summary.uploaderNickname}</strong>
          </div>
          <div className="summary-item" style={{ gridColumn: "1 / -1" }}>
            <span className="muted">{t.share.roster}</span>
            <strong>{summary.rosterSummary.join(" / ")}</strong>
          </div>
          {hasContractTags ? (
            <div className="summary-item" style={{ gridColumn: "1 / -1" }}>
              <span className="muted">{t.share.selectedTags}</span>
              <ContractTagSummary score={summary.contractTagScore} tags={summary.contractTags} />
            </div>
          ) : null}
        </div>
        <div className="hero-actions">
          <Link className="button-primary" href={`/battle/${summary.battleId}`}>
            {t.share.viewFullReport}
          </Link>
          <Link className="button-secondary" href={`/boss/dung01_group_bossrush01`}>
            {t.share.backToLeaderboards}
          </Link>
        </div>
      </section>

      <section className="panel" style={{ maxWidth: 860 }}>
        <div className="table-toolbar">
          <div>
            <div className="eyebrow">{t.share.aboutThisPageTitle}</div>
            <h2 style={{ margin: "6px 0 0" }}>
              {locale === "en" ? "Summary Highlights" : "这页包含什么"}
            </h2>
          </div>
        </div>
        <div className="info-list">
          <span>{t.share.aboutThisPageText1}</span>
          <span>{t.share.aboutThisPageText2}</span>
        </div>
      </section>
    </div>
  );
}
