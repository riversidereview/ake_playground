"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { ContractTagSummary } from "../../components/contract-tag-summary";
import { buildApiUrl } from "../../lib/api/client";
import type { AuthUser, UserBattlesResponse } from "../../lib/api/types";
import { hasContractTagData } from "../../lib/contract-tags";
import { formatBossDisplayName } from "../../lib/format/boss-display";
import { formatDurationMs } from "../../lib/format/duration";
import { useI18n } from "../../lib/i18n/context";
import { getLocalizedCharacterName, getLocalizedDungeonName } from "../../lib/i18n/terms";
import { getRankingGroupLabel, getRankingGroupNote, rankingGroups } from "./ranking-groups.generated";
import type { RankingBossEntry, RankingGroupKey } from "./ranking-groups.generated";

type UserBattlesDashboardProps = {
  battles: UserBattlesResponse["battles"];
  currentUser: AuthUser;
  rankings: UserBattlesResponse["rankings"];
};

type RankingRow = UserBattlesResponse["rankings"][number];

function formatDateTime(value: string, locale: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat(locale === "zh" ? "zh-CN" : "en-US", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

function formatNumber(value: number, locale: string) {
  return new Intl.NumberFormat(locale === "zh" ? "zh-CN" : "en-US").format(Math.round(value));
}

function formatBossShortName(value: string) {
  return value.replace(/^(危境再现|危境碎片|危机合约|影拓丰碑\d期|Crisis Replay|Crisis Fragments|Contingency Contract|Echoes of War|Umbral Monument: Phase \d|Monument of Shadows: Phase \d)[·・\s:]*/, "");
}

function getRankingGroupKey(row: Pick<RankingRow, "bossSlug" | "dungeonName">): RankingGroupKey | null {
  return rankingGroups.find((group) => group.bosses.some((boss) => boss.slug === row.bossSlug))?.key ?? null;
}

function getInitialRankingGroup(rankings: RankingRow[]): RankingGroupKey {
  return rankingGroups.find((group) => rankings.some((row) => getRankingGroupKey(row) === group.key))?.key ?? "crisis";
}

function getScoreTone(scorePercent: number) {
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

function formatRankingSubtitle(boss: RankingBossEntry, ranking: RankingRow | null, locale: "en" | "zh") {
  if (ranking) {
    const displayName = formatBossDisplayName(ranking, locale);
    const dungeonName = getLocalizedDungeonName(ranking.dungeonName, locale);
    return displayName === dungeonName ? dungeonName : `${dungeonName} · ${formatBossShortName(displayName)}`;
  }
  const bossDisplayName = formatBossDisplayName({ bossSlug: boss.slug, bossName: boss.name, dungeonName: boss.dungeonName }, locale);
  const dungeonName = getLocalizedDungeonName(boss.dungeonName, locale);
  if (boss.slug.startsWith("indie_hard")) {
    return `${formatBossShortName(bossDisplayName)} · ${formatBossShortName(bossDisplayName)}`;
  }
  return bossDisplayName === dungeonName ? dungeonName : `${dungeonName} · ${formatBossShortName(bossDisplayName)}`;
}

type AccountRankingsPanelProps = {
  rankings: UserBattlesResponse["rankings"];
  title: string;
  note?: string;
};

export function AccountRankingsPanel({
  rankings,
  title,
  note,
}: AccountRankingsPanelProps) {
  const { t, locale } = useI18n();
  const [rankingGroup, setRankingGroup] = useState<RankingGroupKey>(() => getInitialRankingGroup(rankings));
  const rankingCounts = useMemo(() => {
    return rankingGroups.reduce<Record<RankingGroupKey, number>>(
      (counts, group) => {
        counts[group.key] = rankings.filter((row) => getRankingGroupKey(row) === group.key).length;
        return counts;
      },
      {} as Record<RankingGroupKey, number>,
    );
  }, [rankings]);
  const filteredRankings = useMemo(() => {
    return rankings.filter((row) => getRankingGroupKey(row) === rankingGroup);
  }, [rankingGroup, rankings]);
  const activeRankingGroup = rankingGroups.find((group) => group.key === rankingGroup) ?? rankingGroups[0];
  const rankingTableRows = useMemo(() => {
    const rankingsByBossSlug = new Map(filteredRankings.map((row) => [row.bossSlug, row]));
    return activeRankingGroup.bosses.map((boss) => ({
      boss,
      ranking: rankingsByBossSlug.get(boss.slug) ?? null,
    }));
  }, [activeRankingGroup, filteredRankings]);
  const showContractTags = rankingTableRows.some(
    ({ ranking }) => ranking && hasContractTagData(ranking.contractTagScore, ranking.contractTags),
  );
  const rankingStats = useMemo(() => {
    if (!filteredRankings.length) {
      return {
        averagePercent: 0,
        bestPercent: 0,
        bestRank: 0,
        bestBossName: "",
      };
    }
    const bestByPercent = [...filteredRankings].sort((left, right) => {
      if (right.scorePercent !== left.scorePercent) {
        return right.scorePercent - left.scorePercent;
      }
      return left.rank - right.rank;
    })[0];
    const averagePercent = Math.round(
      filteredRankings.reduce((sum, row) => sum + row.scorePercent, 0) / filteredRankings.length,
    );
    return {
      averagePercent,
      bestPercent: bestByPercent.scorePercent,
      bestRank: bestByPercent.rank,
      bestBossName: formatBossDisplayName(bestByPercent, locale),
    };
  }, [filteredRankings, locale]);

  return (
    <section className="panel">
      <div className="table-toolbar">
        <div>
          <div className="eyebrow">{locale === "en" ? "ACCOUNT RANKINGS" : "账号排名"}</div>
          <h2 style={{ margin: "6px 0 0" }}>{title}</h2>
        </div>
        <span className="muted">
          {note ?? (locale === "en" ? "Rankings calculated per current public rules." : "按公开榜单当前规则排名统计。")}
        </span>
      </div>

      <div className="account-ranking-stack">
        <div className="account-ranking-filter-grid" role="group" aria-label="Ranking group filter">
          {rankingGroups.map((group) => (
            <button
              aria-pressed={rankingGroup === group.key}
              className={`account-ranking-filter-button${rankingGroup === group.key ? " is-active" : ""}`}
              key={group.key}
              onClick={() => setRankingGroup(group.key)}
              type="button"
            >
              <strong>{getRankingGroupLabel(group.key, locale)}</strong>
              <span>{getRankingGroupNote(group.key, locale)}</span>
              <small>
                {rankingCounts[group.key]} {locale === "en" ? "ranked" : "个上榜"}
              </small>
            </button>
          ))}
        </div>

        <div className="account-ranking-overview">
          <div className="account-ranking-chart">
            <div className="account-ranking-axis-label">{locale === "en" ? "Percentile" : "百分比"}</div>
            <div className="account-ranking-bars">
              {filteredRankings.map((row) => {
                const scoreTone = getScoreTone(row.scorePercent);
                return (
                  <div className="account-ranking-bar-column" key={`chart-${row.bossSlug}-${row.battleId}`}>
                    <div className="account-ranking-bar-track">
                      <div
                        className={`account-ranking-bar ${scoreTone}`}
                        style={{ height: `${Math.max(row.scorePercent, 4)}%` }}
                      >
                        <span className={`account-score ${scoreTone}`}>{row.scorePercent}</span>
                      </div>
                    </div>
                    <span className="account-ranking-bar-label">
                      {formatBossShortName(formatBossDisplayName(row, locale))}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>

          <aside className="account-ranking-summary">
            <span className="muted">{locale === "en" ? "Account Performance" : "账号表现"}</span>
            <strong className={`account-score ${getScoreTone(rankingStats.averagePercent)}`}>
              {filteredRankings.length ? `${rankingStats.averagePercent}%` : "-"}
            </strong>
            <span>{locale === "en" ? "Average Score %" : "平均百分比"}</span>
            <dl>
              <div>
                <dt>{locale === "en" ? "Best Score" : "最佳"}</dt>
                <dd className={`account-score ${getScoreTone(rankingStats.bestPercent)}`}>
                  {filteredRankings.length ? `${rankingStats.bestPercent}%` : "-"}
                </dd>
              </div>
              <div>
                <dt>{locale === "en" ? "Best Rank" : "最佳排名"}</dt>
                <dd className={`account-score ${getScoreTone(rankingStats.bestPercent)}`}>
                  {filteredRankings.length ? `#${rankingStats.bestRank}` : "-"}
                </dd>
              </div>
              <div>
                <dt>{locale === "en" ? "Ranked Encounters" : "上榜首领"}</dt>
                <dd>{filteredRankings.length}</dd>
              </div>
            </dl>
            <span className="muted">{rankingStats.bestBossName ? formatBossShortName(rankingStats.bestBossName) : "-"}</span>
          </aside>
        </div>

        <div className="table-wrap">
          <table className="data-table account-ranking-table">
            <thead>
              <tr>
                <th>{t.home.tableBoss}</th>
                <th>{t.leaderboard.tableRank}</th>
                <th>{t.leaderboard.tableScorePercent}</th>
                {showContractTags ? <th>{t.leaderboard.tableTags}</th> : null}
                <th>{t.leaderboard.tableTeamComposition}</th>
                <th>{t.home.tableActions}</th>
              </tr>
            </thead>
            <tbody>
              {rankingTableRows.map(({ boss, ranking }) => {
                const scoreTone = getScoreTone(ranking?.scorePercent ?? 0);
                return (
                  <tr key={boss.slug}>
                    <td>
                      <div style={{ display: "grid", gap: 4 }}>
                        <strong>
                          {formatBossShortName(
                            ranking
                              ? formatBossDisplayName(ranking, locale)
                              : formatBossDisplayName({
                                  bossSlug: boss.slug,
                                  bossName: boss.name,
                                  dungeonName: boss.dungeonName,
                                }, locale),
                          )}
                        </strong>
                        <span className="muted">{formatRankingSubtitle(boss, ranking, locale)}</span>
                      </div>
                    </td>
                    <td>
                      {ranking ? <strong className={`account-score ${scoreTone}`}>#{ranking.rank}</strong> : <span className="muted">-</span>}
                    </td>
                    <td>
                      {ranking ? (
                        <div style={{ display: "grid", gap: 4 }}>
                          <strong className={`account-score ${scoreTone}`}>{ranking.scorePercent}%</strong>
                          <span className="muted">{formatDurationMs(ranking.durationMs)}</span>
                        </div>
                      ) : (
                        <span className="muted">-</span>
                      )}
                    </td>
                    {showContractTags ? (
                      <td>
                        {ranking && hasContractTagData(ranking.contractTagScore, ranking.contractTags) ? (
                          <ContractTagSummary compact score={ranking.contractTagScore} tags={ranking.contractTags} />
                        ) : (
                          <span className="muted">-</span>
                        )}
                      </td>
                    ) : null}
                    <td>{ranking?.rosterSummary.map((name) => getLocalizedCharacterName(name, locale)).join(" / ") || <span className="muted">-</span>}</td>
                    <td>
                      {ranking ? (
                        <Link className="button-secondary" href={`/battle/${ranking.battleId}`}>
                          {locale === "en" ? "Report" : "查看"}
                        </Link>
                      ) : (
                        <span className="muted">-</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}

export function UserBattlesDashboard({
  battles: initialBattles,
  currentUser,
  rankings: initialRankings,
}: UserBattlesDashboardProps) {
  const { t, locale } = useI18n();
  const [battles, setBattles] = useState(initialBattles);
  const [rankings, setRankings] = useState(initialRankings);
  const [statusFilter, setStatusFilter] = useState<"all" | "valid" | "deleted">("valid");
  const [query, setQuery] = useState("");
  const [nickname, setNickname] = useState(currentUser.nickname);
  const [nicknameDraft, setNicknameDraft] = useState(currentUser.nickname);
  const [nicknamePending, setNicknamePending] = useState(false);
  const [pendingBattleId, setPendingBattleId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const normalizedQuery = query.trim().toLowerCase();
  const filteredBattles = useMemo(() => {
    return battles.filter((battle) => {
      if (statusFilter !== "all" && battle.status !== statusFilter) {
        return false;
      }
      if (!normalizedQuery) {
        return true;
      }
      return [
        battle.id,
        battle.bossName,
        formatBossDisplayName(battle, locale),
        battle.dungeonName,
        battle.rosterSummary.join(" "),
        battle.parserVersion,
        battle.rulesVersion,
      ].some((value) => value.toLowerCase().includes(normalizedQuery));
    });
  }, [battles, normalizedQuery, statusFilter, locale]);

  const validBattles = battles.filter((battle) => battle.status === "valid").length;
  const deletedBattles = battles.length - validBattles;
  const latestBattle = battles[0] ?? null;
  const showBattleContractTags = filteredBattles.some(
    (battle) => hasContractTagData(battle.contractTagScore, battle.contractTags),
  );

  async function handleDeleteBattle(battleId: string) {
    if (pendingBattleId) {
      return;
    }
    const target = battles.find((battle) => battle.id === battleId);
    if (!target || target.status === "deleted") {
      return;
    }
    if (
      !window.confirm(
        locale === "en"
          ? `Are you sure you want to delete the record for ${formatBossDisplayName(target, locale)}?`
          : `确定要删除 ${formatBossDisplayName(target, locale)} 这条战斗记录吗？`,
      )
    ) {
      return;
    }

    setPendingBattleId(battleId);
    setMessage(null);
    try {
      const response = await fetch(buildApiUrl(`/api/battles/${battleId}`), {
        method: "DELETE",
        credentials: "include",
      });
      const data = (await response.json()) as { error?: { message?: string } };
      if (!response.ok) {
        throw new Error(data.error?.message ?? t.common.error);
      }
      setBattles((current) =>
        current.map((battle) => (battle.id === battleId ? { ...battle, status: "deleted" } : battle)),
      );
      setRankings((current) => current.filter((row) => row.battleId !== battleId));
      setMessage(t.userDashboard.deleteSuccess);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : t.common.error);
    } finally {
      setPendingBattleId(null);
    }
  }

  async function handleUpdateNickname() {
    const nextNickname = nicknameDraft.trim();
    if (!nextNickname || nicknamePending || nextNickname === nickname) {
      return;
    }

    setNicknamePending(true);
    setMessage(null);
    try {
      const response = await fetch(buildApiUrl("/api/auth/me/nickname"), {
        method: "PATCH",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ nickname: nextNickname }),
      });
      const data = (await response.json()) as {
        user?: AuthUser | null;
        error?: { message?: string };
      };
      if (!response.ok || !data.user) {
        throw new Error(data.error?.message ?? t.common.error);
      }
      setNickname(data.user.nickname);
      setNicknameDraft(data.user.nickname);
      setMessage(
        locale === "en"
          ? "Nickname updated! Leaderboards and battle reports will reflect your new display name."
          : "昵称已更新，榜单和战斗详情会显示新的昵称。",
      );
      window.dispatchEvent(new CustomEvent("auth-nickname-updated", { detail: data.user.nickname }));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : t.common.error);
    } finally {
      setNicknamePending(false);
    }
  }

  return (
    <div className="page-stack">
      <section className="panel panel-muted">
        <div className="section-heading">
          <div>
            <div className="eyebrow">{locale === "en" ? "PERSONAL DASHBOARD" : "个人管理"}</div>
            <h1>{t.userDashboard.title}</h1>
            <p className="muted" style={{ margin: "8px 0 0" }}>
              {t.userDashboard.subtitle}
            </p>
          </div>
          <Link className="button-chip" href="/">
            {t.common.home}
          </Link>
        </div>

        <div className="stat-grid stat-grid-4" style={{ marginTop: 16 }}>
          <div className="metric-card">
            <span className="metric-label">{locale === "en" ? "Total Records" : "总记录"}</span>
            <strong>{battles.length}</strong>
            <span className="metric-note">{locale === "en" ? "All battles under this account" : "当前账号下全部 battle"}</span>
          </div>
          <div className="metric-card">
            <span className="metric-label">{locale === "en" ? "Active Records" : "有效记录"}</span>
            <strong>{validBattles}</strong>
            <span className="metric-note">{locale === "en" ? "Accessible in reports" : "仍可进入详情页"}</span>
          </div>
          <div className="metric-card">
            <span className="metric-label">{locale === "en" ? "Deleted" : "已删除"}</span>
            <strong>{deletedBattles}</strong>
            <span className="metric-note">{locale === "en" ? "Removed from leaderboards" : "已从公开页面移除"}</span>
          </div>
          <div className="metric-card">
            <span className="metric-label">{locale === "en" ? "Latest Upload" : "最近上传"}</span>
            <strong>{latestBattle ? formatDateTime(latestBattle.battleEndAt, locale) : "--"}</strong>
            <span className="metric-note">
              {latestBattle ? formatBossDisplayName(latestBattle, locale) : t.home.noRecord}
            </span>
          </div>
        </div>
      </section>

      <section className="panel">
        <div className="table-toolbar">
          <div>
            <div className="eyebrow">{locale === "en" ? "ACCOUNT SETTINGS" : "账号设置"}</div>
            <h2 style={{ margin: "6px 0 0" }}>{locale === "en" ? "Change Display Nickname" : "修改公开昵称"}</h2>
          </div>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
            <input
              className="field-input"
              maxLength={32}
              minLength={2}
              onChange={(event) => setNicknameDraft(event.target.value)}
              style={{ width: 240 }}
              value={nicknameDraft}
            />
            <button
              className="button-primary"
              disabled={nicknamePending || nicknameDraft.trim().length < 2 || nicknameDraft.trim() === nickname}
              onClick={handleUpdateNickname}
              type="button"
            >
              {nicknamePending ? `${t.common.save}...` : t.common.save}
            </button>
          </div>
        </div>
      </section>

      <AccountRankingsPanel
        rankings={rankings}
        title={locale === "en" ? "My Rankings Across Encounters" : "我在各首领中的排名"}
      />

      <section className="panel">
        <div className="table-toolbar">
          <div>
            <div className="eyebrow">{locale === "en" ? "BATTLE LOGS" : "记录列表"}</div>
            <h2 style={{ margin: "6px 0 0" }}>{locale === "en" ? "Browse & Manage Battles" : "查看、筛选或删除自己的 battle"}</h2>
          </div>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
            <input
              className="field-input"
              onChange={(event) => setQuery(event.target.value)}
              placeholder={locale === "en" ? "Search boss / dungeon / battle ID" : "搜索首领 / 副本 / battleId"}
              style={{ width: 260 }}
              value={query}
            />
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <button
                className={`button-chip${statusFilter === "valid" ? " is-active" : ""}`}
                onClick={() => setStatusFilter("valid")}
                type="button"
              >
                {t.userDashboard.filterValid}
              </button>
              <button
                className={`button-chip${statusFilter === "deleted" ? " is-active" : ""}`}
                onClick={() => setStatusFilter("deleted")}
                type="button"
              >
                {t.userDashboard.filterDeleted}
              </button>
              <button
                className={`button-chip${statusFilter === "all" ? " is-active" : ""}`}
                onClick={() => setStatusFilter("all")}
                type="button"
              >
                {t.userDashboard.filterAll}
              </button>
            </div>
          </div>
        </div>

        {message ? (
          <div className="panel-inset" style={{ marginBottom: 12 }}>
            <span className="muted">{message}</span>
          </div>
        ) : null}

        {filteredBattles.length ? (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>{t.userDashboard.tableStatus}</th>
                  <th>{t.userDashboard.tableBoss}</th>
                  <th>{t.leaderboard.tableTeamComposition}</th>
                  {showBattleContractTags ? <th>{t.leaderboard.tableTags}</th> : null}
                  <th>{t.userDashboard.tableUploadedAt}</th>
                  <th>DPS</th>
                  <th>{locale === "en" ? "Version" : "版本"}</th>
                  <th>{t.userDashboard.tableActions}</th>
                </tr>
              </thead>
              <tbody>
                {filteredBattles.map((battle) => (
                  <tr className={battle.status === "deleted" ? "admin-row-deleted" : undefined} key={battle.id}>
                    <td>
                      <span className={`status-pill ${battle.status === "valid" ? "is-valid" : "is-deleted"}`}>
                        {battle.status === "valid" ? t.userDashboard.statusValid : t.userDashboard.statusDeleted}
                      </span>
                    </td>
                    <td>
                      <div style={{ display: "grid", gap: 4 }}>
                        <strong>{formatBossDisplayName(battle, locale)}</strong>
                        <span className="muted">{getLocalizedDungeonName(battle.dungeonName, locale)}</span>
                        <span className="muted">{battle.id}</span>
                      </div>
                    </td>
                    <td>{battle.rosterSummary.map((name) => getLocalizedCharacterName(name, locale)).join(" / ") || "--"}</td>
                    {showBattleContractTags ? (
                      <td>
                        {hasContractTagData(battle.contractTagScore, battle.contractTags) ? (
                          <ContractTagSummary compact score={battle.contractTagScore} tags={battle.contractTags} />
                        ) : (
                          <span className="muted">-</span>
                        )}
                      </td>
                    ) : null}
                    <td>
                      <div style={{ display: "grid", gap: 4 }}>
                        <span>{formatDateTime(battle.battleEndAt, locale)}</span>
                        <span className="muted">{formatDurationMs(battle.durationMs)}</span>
                      </div>
                    </td>
                    <td>{formatNumber(battle.totalDps, locale)}</td>
                    <td>
                      <div style={{ display: "grid", gap: 4 }}>
                        <span>{battle.parserVersion}</span>
                        <span className="muted">{battle.rulesVersion}</span>
                      </div>
                    </td>
                    <td>
                      <div className="admin-actions">
                        {battle.status === "valid" ? (
                          <>
                            <Link className="button-secondary" href={`/battle/${battle.id}`}>
                              {locale === "en" ? "Report" : "查看"}
                            </Link>
                            <Link className="button-secondary" href={`/axis/${battle.id}/editor`}>
                              {locale === "en" ? "Simulator" : "排轴"}
                            </Link>
                          </>
                        ) : null}
                        <button
                          className="button-danger"
                          disabled={battle.status === "deleted" || pendingBattleId === battle.id}
                          onClick={() => handleDeleteBattle(battle.id)}
                          type="button"
                        >
                          {pendingBattleId === battle.id
                            ? `${locale === "en" ? "Deleting..." : "删除中..."}`
                            : `${locale === "en" ? "Delete" : "删除"}`}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty-state">
            {battles.length
              ? locale === "en"
                ? "No battle records match the current filter."
                : "当前筛选条件下没有符合的记录。"
              : locale === "en"
                ? "No battles uploaded under this account yet. Upload a battle via the desktop client to view it here."
                : "这个账号还没有上传过 battle，先用上传器传一条记录就会出现在这里。"}
          </div>
        )}
      </section>
    </div>
  );
}
