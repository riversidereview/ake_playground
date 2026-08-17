"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { buildApiUrl } from "../../lib/api/client";
import type { AdminDashboardResponse } from "../../lib/api/types";
import { formatBossDisplayName } from "../../lib/format/boss-display";
import { formatDurationMs } from "../../lib/format/duration";
import { useI18n } from "../../lib/i18n/context";

type AdminDashboardProps = {
  initialData: AdminDashboardResponse;
};

type AdminBattle = AdminDashboardResponse["battles"][number];

function formatDateTime(value: string | null, locale: string) {
  if (!value) {
    return "--";
  }
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

export function AdminDashboard({ initialData }: AdminDashboardProps) {
  const { t, locale } = useI18n();
  const [dashboard, setDashboard] = useState(initialData);
  const [selectedUserId, setSelectedUserId] = useState("all");
  const [statusFilter, setStatusFilter] = useState<"all" | "valid" | "deleted">("valid");
  const [query, setQuery] = useState("");
  const [pendingBattleId, setPendingBattleId] = useState<string | null>(null);
  const [pendingUserAction, setPendingUserAction] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const normalizedQuery = query.trim().toLowerCase();

  const selectedUser = useMemo(
    () => dashboard.users.find((user) => user.id === selectedUserId) ?? null,
    [dashboard.users, selectedUserId],
  );

  const filteredUsers = useMemo(() => {
    if (!normalizedQuery) {
      return dashboard.users;
    }
    return dashboard.users.filter((user) =>
      [user.nickname, user.email ?? ""].some((value) => value.toLowerCase().includes(normalizedQuery)),
    );
  }, [dashboard.users, normalizedQuery]);

  const filteredBattles = useMemo(() => {
    return dashboard.battles.filter((battle) => {
      if (selectedUserId !== "all" && battle.uploaderUserId !== selectedUserId) {
        return false;
      }
      if (statusFilter !== "all" && battle.status !== statusFilter) {
        return false;
      }
      if (!normalizedQuery) {
        return true;
      }

      return [
        battle.uploaderNickname,
        battle.uploaderEmail ?? "",
        battle.bossName,
        formatBossDisplayName(battle, locale),
        battle.dungeonName,
        battle.id,
        battle.rosterSummary.join(" "),
      ].some((value) => value.toLowerCase().includes(normalizedQuery));
    });
  }, [dashboard.battles, normalizedQuery, selectedUserId, statusFilter, locale]);

  async function handleDeleteBattle(battle: AdminBattle) {
    if (battle.status === "deleted" || pendingBattleId) {
      return;
    }
    const confirmed = window.confirm(
      locale === "en"
        ? `Are you sure you want to delete the battle record for ${battle.uploaderNickname}?`
        : `确定要删除 ${battle.uploaderNickname} 的这条战斗记录吗？`,
    );
    if (!confirmed) {
      return;
    }

    setPendingBattleId(battle.id);
    setMessage(null);
    try {
      const response = await fetch(buildApiUrl(`/api/admin/battles/${battle.id}`), {
        method: "DELETE",
        credentials: "include",
      });
      const data = (await response.json()) as { error?: { message?: string } };
      if (!response.ok) {
        throw new Error(data.error?.message ?? t.common.error);
      }

      setDashboard((current) => {
        const target = current.battles.find((item) => item.id === battle.id);
        if (!target || target.status === "deleted") {
          return current;
        }
        return {
          overview: {
            ...current.overview,
            validBattles: Math.max(0, current.overview.validBattles - 1),
            deletedBattles: current.overview.deletedBattles + 1,
          },
          users: current.users.map((user) =>
            user.id === target.uploaderUserId
              ? {
                  ...user,
                  validBattles: Math.max(0, user.validBattles - 1),
                  deletedBattles: user.deletedBattles + 1,
                }
              : user,
          ),
          battles: current.battles.map((item) =>
            item.id === battle.id
              ? {
                  ...item,
                  status: "deleted",
                }
              : item,
          ),
        };
      });
      setMessage(locale === "en" ? `Deleted record ${battle.id}.` : `已删除记录 ${battle.id}。`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : t.common.error);
    } finally {
      setPendingBattleId(null);
    }
  }

  async function handleToggleDisabled() {
    if (!selectedUser || pendingUserAction) {
      return;
    }
    const nextDisabled = !selectedUser.isDisabled;
    const confirmed = window.confirm(
      nextDisabled
        ? locale === "en"
          ? `Disable account ${selectedUser.nickname}?`
          : `确定要禁用账号 ${selectedUser.nickname} 吗？`
        : locale === "en"
          ? `Re-enable account ${selectedUser.nickname}?`
          : `确定要恢复账号 ${selectedUser.nickname} 吗？`,
    );
    if (!confirmed) {
      return;
    }

    setPendingUserAction(`disable:${selectedUser.id}`);
    setMessage(null);
    try {
      const response = await fetch(buildApiUrl(`/api/admin/users/${selectedUser.id}/disabled`), {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ disabled: nextDisabled }),
      });
      const data = (await response.json()) as { error?: { message?: string } };
      if (!response.ok) {
        throw new Error(data.error?.message ?? t.common.error);
      }
      setDashboard((current) => ({
        ...current,
        users: current.users.map((user) =>
          user.id === selectedUser.id ? { ...user, isDisabled: nextDisabled } : user,
        ),
      }));
      setMessage(
        nextDisabled
          ? locale === "en"
            ? "Account disabled."
            : "账号已禁用。"
          : locale === "en"
            ? "Account re-enabled."
            : "账号已恢复。",
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : t.common.error);
    } finally {
      setPendingUserAction(null);
    }
  }

  async function handleToggleAdmin() {
    if (!selectedUser || pendingUserAction) {
      return;
    }
    const nextIsAdmin = !selectedUser.isAdmin;
    const confirmed = window.confirm(
      nextIsAdmin
        ? locale === "en"
          ? `Promote ${selectedUser.nickname} to administrator?`
          : `确定要把 ${selectedUser.nickname} 提升为管理员吗？`
        : locale === "en"
          ? `Remove administrator permissions from ${selectedUser.nickname}?`
          : `确定要移除 ${selectedUser.nickname} 的管理员权限吗？`,
    );
    if (!confirmed) {
      return;
    }

    setPendingUserAction(`admin:${selectedUser.id}`);
    setMessage(null);
    try {
      const response = await fetch(buildApiUrl(`/api/admin/users/${selectedUser.id}/admin`), {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ isAdmin: nextIsAdmin }),
      });
      const data = (await response.json()) as { error?: { message?: string } };
      if (!response.ok) {
        throw new Error(data.error?.message ?? t.common.error);
      }
      setDashboard((current) => ({
        overview: {
          ...current.overview,
          adminUsers: current.overview.adminUsers + (nextIsAdmin ? 1 : -1),
        },
        users: current.users.map((user) =>
          user.id === selectedUser.id ? { ...user, isAdmin: nextIsAdmin } : user,
        ),
        battles: current.battles,
      }));
      setMessage(
        nextIsAdmin
          ? locale === "en"
            ? "Admin privileges granted."
            : "管理员权限已授予。"
          : locale === "en"
            ? "Admin privileges revoked."
            : "管理员权限已移除。",
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : t.common.error);
    } finally {
      setPendingUserAction(null);
    }
  }

  async function handleResetPassword() {
    if (!selectedUser || pendingUserAction) {
      return;
    }
    const newPassword = window.prompt(
      locale === "en"
        ? `Set a new password for ${selectedUser.nickname} (min 8 chars):`
        : `给 ${selectedUser.nickname} 设置一个新密码（至少 8 位）`,
      "",
    );
    if (!newPassword) {
      return;
    }

    setPendingUserAction(`password:${selectedUser.id}`);
    setMessage(null);
    try {
      const response = await fetch(buildApiUrl(`/api/admin/users/${selectedUser.id}/reset-password`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ newPassword }),
      });
      const data = (await response.json()) as { error?: { message?: string } };
      if (!response.ok) {
        throw new Error(data.error?.message ?? t.common.error);
      }
      setMessage(
        locale === "en"
          ? `Password updated for ${selectedUser.nickname}.`
          : `已为 ${selectedUser.nickname} 更新密码。`,
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : t.common.error);
    } finally {
      setPendingUserAction(null);
    }
  }

  async function handleDeleteUser() {
    if (!selectedUser || pendingUserAction) {
      return;
    }
    const confirmed = window.confirm(
      locale === "en"
        ? `Are you sure you want to delete account ${selectedUser.nickname}? This will revoke access and mark its battles as deleted.`
        : `确定要删除账号 ${selectedUser.nickname} 吗？这会同时清掉这个账号的登录能力，并把它的战斗记录标记为已删除。`,
    );
    if (!confirmed) {
      return;
    }

    setPendingUserAction(`delete:${selectedUser.id}`);
    setMessage(null);
    try {
      const response = await fetch(buildApiUrl(`/api/admin/users/${selectedUser.id}`), {
        method: "DELETE",
        credentials: "include",
      });
      const data = (await response.json()) as { error?: { message?: string } };
      if (!response.ok) {
        throw new Error(data.error?.message ?? t.common.error);
      }

      setDashboard((current) => ({
        overview: {
          ...current.overview,
          totalUsers: Math.max(0, current.overview.totalUsers - 1),
          adminUsers: current.overview.adminUsers - (selectedUser.isAdmin ? 1 : 0),
          validBattles:
            current.overview.validBattles -
            current.battles.filter(
              (battle) => battle.uploaderUserId === selectedUser.id && battle.status === "valid",
            ).length,
          deletedBattles:
            current.overview.deletedBattles +
            current.battles.filter(
              (battle) => battle.uploaderUserId === selectedUser.id && battle.status === "valid",
            ).length,
        },
        users: current.users.filter((user) => user.id !== selectedUser.id),
        battles: current.battles.map((battle) =>
          battle.uploaderUserId === selectedUser.id
            ? {
                ...battle,
                status: "deleted",
              }
            : battle,
        ),
      }));
      setSelectedUserId("all");
      setMessage(
        locale === "en" ? `Account ${selectedUser.nickname} deleted.` : `账号 ${selectedUser.nickname} 已删除。`,
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : t.common.error);
    } finally {
      setPendingUserAction(null);
    }
  }

  return (
    <div className="page-stack">
      <section className="panel panel-muted admin-hero">
        <div>
          <div className="eyebrow">{locale === "en" ? "ADMINISTRATION" : "后台管理"}</div>
          <h1 style={{ margin: "8px 0 10px" }}>{t.admin.title}</h1>
          <p className="muted" style={{ margin: 0, maxWidth: 880 }}>
            {t.admin.subtitle}
          </p>
        </div>
        <div className="stat-grid stat-grid-4">
          <div className="metric-card">
            <span className="metric-label">{locale === "en" ? "Total Users" : "账号总数"}</span>
            <strong>{dashboard.overview.totalUsers}</strong>
            <span className="metric-note">{locale === "en" ? "Including admins" : "含管理员账号"}</span>
          </div>
          <div className="metric-card">
            <span className="metric-label">{locale === "en" ? "Admins" : "管理员"}</span>
            <strong>{dashboard.overview.adminUsers}</strong>
            <span className="metric-note">{locale === "en" ? "Backend access" : "拥有后台权限"}</span>
          </div>
          <div className="metric-card">
            <span className="metric-label">{locale === "en" ? "Active Records" : "有效记录"}</span>
            <strong>{dashboard.overview.validBattles}</strong>
            <span className="metric-note">{locale === "en" ? "Publicly visible" : "当前仍对外可见"}</span>
          </div>
          <div className="metric-card">
            <span className="metric-label">{locale === "en" ? "Deleted" : "已删除"}</span>
            <strong>{dashboard.overview.deletedBattles}</strong>
            <span className="metric-note">{locale === "en" ? "Audit retained" : "后台保留审计状态"}</span>
          </div>
        </div>
      </section>

      <section className="admin-layout">
        <aside className="panel admin-sidebar">
          <div className="section-heading">
            <div>
              <div className="eyebrow">{locale === "en" ? "ACCOUNTS" : "账号列表"}</div>
              <h2>{locale === "en" ? "Upload Accounts" : "上传账号"}</h2>
            </div>
            <span className="muted">{t.admin.userCount(filteredUsers.length)}</span>
          </div>

          <button
            className={`admin-user-card${selectedUserId === "all" ? " is-active" : ""}`}
            onClick={() => setSelectedUserId("all")}
            type="button"
          >
            <div>
              <strong>{locale === "en" ? "All Accounts" : "全部账号"}</strong>
              <div className="admin-user-meta">{locale === "en" ? "View all battles" : "查看所有 battle"}</div>
            </div>
            <span>{dashboard.overview.totalBattles}</span>
          </button>

          <div className="admin-user-list">
            {filteredUsers.map((user) => (
              <button
                className={`admin-user-card${selectedUserId === user.id ? " is-active" : ""}`}
                key={user.id}
                onClick={() => setSelectedUserId(user.id)}
                type="button"
              >
                <div>
                  <div className="admin-user-title">
                    <strong>{user.nickname}</strong>
                    {user.isAdmin ? (
                      <span className="status-pill is-admin">{locale === "en" ? "Admin" : "管理员"}</span>
                    ) : null}
                    {user.isDisabled ? (
                      <span className="status-pill is-disabled">{locale === "en" ? "Disabled" : "已禁用"}</span>
                    ) : null}
                  </div>
                  <div className="admin-user-meta">{user.email ?? (locale === "en" ? "No email" : "未知邮箱")}</div>
                  <div className="admin-user-meta">
                    {locale === "en"
                      ? `Valid ${user.validBattles} / Del ${user.deletedBattles}`
                      : `有效 ${user.validBattles} / 删除 ${user.deletedBattles}`}
                  </div>
                </div>
                <span>{user.totalBattles}</span>
              </button>
            ))}
          </div>
        </aside>

        <div className="page-stack">
          {selectedUser ? (
            <section className="panel panel-muted">
              <div className="section-heading">
                <div>
                  <div className="eyebrow">{locale === "en" ? "ACCOUNT CONTROL" : "账号控制"}</div>
                  <h2>{selectedUser.nickname}</h2>
                </div>
                <div className="admin-chip-row">
                  {selectedUser.isAdmin ? (
                    <span className="status-pill is-admin">{locale === "en" ? "Admin" : "管理员"}</span>
                  ) : null}
                  {selectedUser.isDisabled ? (
                    <span className="status-pill is-disabled">{locale === "en" ? "Disabled" : "已禁用"}</span>
                  ) : null}
                </div>
              </div>

              <div className="stat-grid stat-grid-4">
                <div className="metric-card">
                  <span className="metric-label">{t.auth.emailLabel}</span>
                  <strong>{selectedUser.email ?? "--"}</strong>
                  <span className="metric-note">{locale === "en" ? "Primary login ID" : "登录主标识"}</span>
                </div>
                <div className="metric-card">
                  <span className="metric-label">{locale === "en" ? "Joined At" : "注册时间"}</span>
                  <strong>{formatDateTime(selectedUser.createdAt, locale)}</strong>
                  <span className="metric-note">{locale === "en" ? "Account creation" : "账号创建时间"}</span>
                </div>
                <div className="metric-card">
                  <span className="metric-label">{locale === "en" ? "Battles" : "记录数"}</span>
                  <strong>{selectedUser.totalBattles}</strong>
                  <span className="metric-note">
                    {locale === "en"
                      ? `Valid ${selectedUser.validBattles} / Deleted ${selectedUser.deletedBattles}`
                      : `有效 ${selectedUser.validBattles} / 删除 ${selectedUser.deletedBattles}`}
                  </span>
                </div>
                <div className="metric-card">
                  <span className="metric-label">{locale === "en" ? "Last Active" : "最近上传"}</span>
                  <strong>{formatDateTime(selectedUser.lastBattleAt, locale)}</strong>
                  <span className="metric-note">{locale === "en" ? "Last battle timestamp" : "最后一条 battle 时间"}</span>
                </div>
              </div>

              <div className="admin-actions" style={{ marginTop: 16 }}>
                <button
                  className="button-secondary"
                  disabled={Boolean(pendingUserAction)}
                  onClick={handleToggleDisabled}
                  type="button"
                >
                  {selectedUser.isDisabled
                    ? locale === "en"
                      ? "Restore Account"
                      : "恢复账号"
                    : locale === "en"
                      ? "Disable Account"
                      : "禁用账号"}
                </button>
                <button
                  className="button-secondary"
                  disabled={Boolean(pendingUserAction)}
                  onClick={handleResetPassword}
                  type="button"
                >
                  {locale === "en" ? "Reset Password" : "重置密码"}
                </button>
                <button
                  className="button-secondary"
                  disabled={Boolean(pendingUserAction)}
                  onClick={handleToggleAdmin}
                  type="button"
                >
                  {selectedUser.isAdmin
                    ? locale === "en"
                      ? "Revoke Admin"
                      : "移除管理员"
                    : locale === "en"
                      ? "Promote Admin"
                      : "提升为管理员"}
                </button>
                <button
                  className="button-danger"
                  disabled={Boolean(pendingUserAction)}
                  onClick={handleDeleteUser}
                  type="button"
                >
                  {locale === "en" ? "Delete Account" : "删除账号"}
                </button>
              </div>
            </section>
          ) : null}

          <section className="panel">
            <div className="section-heading">
              <div>
                <div className="eyebrow">{locale === "en" ? "FILTERED BATTLES" : "当前筛选"}</div>
                <h2>
                  {selectedUser
                    ? locale === "en"
                      ? `${selectedUser.nickname}'s Battles`
                      : `${selectedUser.nickname} 的战斗记录`
                    : locale === "en"
                      ? "All Site Battles"
                      : "全站战斗记录"}
                </h2>
              </div>
              <span className="muted">
                {selectedUser
                  ? `${locale === "en" ? "Last active: " : "最近战斗："}${formatDateTime(selectedUser.lastBattleAt, locale)}`
                  : t.admin.battleCount(dashboard.overview.totalBattles)}
              </span>
            </div>

            <div className="admin-toolbar">
              <label className="field-stack admin-search">
                <span>{locale === "en" ? "Search Account / Encounter / Operator" : "搜索账号 / 首领 / 角色"}</span>
                <input
                  className="field-input"
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder={locale === "en" ? "e.g. Rodan, Nephthys, email..." : "例如：洛茜、聂菲斯、某个邮箱"}
                  value={query}
                />
              </label>
              <div className="admin-chip-row">
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

            {message ? (
              <div className="panel-inset">
                <span className="muted">{message}</span>
              </div>
            ) : null}

            <div className="table-wrap">
              <table className="data-table admin-table">
                <thead>
                  <tr>
                    <th>{locale === "en" ? "Account" : "账号"}</th>
                    <th>{t.home.tableBoss}</th>
                    <th>{t.leaderboard.tableTeamComposition}</th>
                    <th>{t.userDashboard.tableUploadedAt}</th>
                    <th>DPS</th>
                    <th>{t.userDashboard.tableStatus}</th>
                    <th>{t.home.tableActions}</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredBattles.length ? (
                    filteredBattles.map((battle) => (
                      <tr
                        className={battle.status === "deleted" ? "admin-row-deleted" : undefined}
                        key={battle.id}
                      >
                        <td>
                          <div className="admin-cell-stack">
                            <strong>{battle.uploaderNickname}</strong>
                            <span>{battle.uploaderEmail ?? battle.uploaderUserId}</span>
                          </div>
                        </td>
                        <td>
                          <div className="admin-cell-stack">
                            <strong>{formatBossDisplayName(battle, locale)}</strong>
                            <span>{battle.dungeonName}</span>
                          </div>
                        </td>
                        <td>{battle.rosterSummary.join(" / ") || "-"}</td>
                        <td>
                          <div className="admin-cell-stack">
                            <strong>{formatDateTime(battle.battleEndAt, locale)}</strong>
                            <span>{formatDurationMs(battle.durationMs)}</span>
                          </div>
                        </td>
                        <td>{formatNumber(battle.totalDps, locale)}</td>
                        <td>
                          <span className={`status-pill ${battle.status === "deleted" ? "is-deleted" : "is-valid"}`}>
                            {battle.status === "deleted" ? t.userDashboard.statusDeleted : t.userDashboard.statusValid}
                          </span>
                        </td>
                        <td>
                          <div className="admin-actions">
                            {battle.status === "valid" ? (
                              <Link className="button-chip" href={`/battle/${battle.id}`}>
                                {locale === "en" ? "View" : "查看"}
                              </Link>
                            ) : null}
                            <button
                              className="button-danger"
                              disabled={battle.status === "deleted" || pendingBattleId === battle.id}
                              onClick={() => handleDeleteBattle(battle)}
                              type="button"
                            >
                              {pendingBattleId === battle.id
                                ? locale === "en"
                                  ? "Deleting..."
                                  : "删除中..."
                                : battle.status === "deleted"
                                  ? t.userDashboard.statusDeleted
                                  : locale === "en"
                                    ? "Delete"
                                    : "删除"}
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={7}>
                        <div className="panel-inset" style={{ margin: "8px 0" }}>
                          {locale === "en"
                            ? "No battle records match the current filter."
                            : "当前筛选下没有匹配的战斗记录。"}
                        </div>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      </section>
    </div>
  );
}
