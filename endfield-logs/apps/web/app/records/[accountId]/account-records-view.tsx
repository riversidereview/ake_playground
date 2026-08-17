"use client";

import Link from "next/link";
import { AccountRankingsPanel } from "../../../features/records/user-battles-dashboard";
import type { PublicUserRankingsResponse } from "../../../lib/api/types";
import { useI18n } from "../../../lib/i18n/context";

export function AccountRecordsView({ response }: { response: PublicUserRankingsResponse }) {
  const { t, locale } = useI18n();

  return (
    <div className="page-stack">
      <section className="panel panel-muted">
        <div className="section-heading">
          <div>
            <div className="breadcrumbs">
              {t.common.home} / {locale === "en" ? "Account Rankings" : "账号排名"} / {response.accountDisplayName}
            </div>
            <div className="eyebrow" style={{ marginTop: 14 }}>
              {locale === "en" ? "PUBLIC PROFILE" : "公开账号"}
            </div>
            <h1 style={{ margin: "6px 0 0" }}>{response.accountDisplayName}</h1>
            <p className="muted" style={{ margin: "8px 0 0" }}>
              {locale === "en"
                ? "Displays this account's best valid speedrun ranking across all public leaderboards."
                : "这里展示该账号在公开竞速榜单中的当前最好通关排名。"}
            </p>
          </div>
          <Link className="button-chip" href="/">
            {t.common.home}
          </Link>
        </div>
      </section>

      <AccountRankingsPanel
        rankings={response.rankings}
        title={
          locale === "en"
            ? `${response.accountDisplayName}'s Rankings Across Encounters`
            : `${response.accountDisplayName}在各首领中的排名`
        }
      />
    </div>
  );
}
