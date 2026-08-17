"use client";

import { useEffect, useMemo, useState } from "react";

import type { EndaxisImportPayload } from "../../../../lib/endaxis-project";
import { useI18n } from "../../../../lib/i18n/context";

type EndaxisPreloadProps = {
  payload: EndaxisImportPayload;
};

const ENDAXIS_EDITOR_URL = "/endaxis/timeline";

export function EndaxisPreload({ payload }: EndaxisPreloadProps) {
  const { t, locale } = useI18n();
  const [message, setMessage] = useState(
    locale === "en" ? "Writing timeline project..." : "正在写入排轴工程...",
  );

  const projectJson = useMemo(() => JSON.stringify(payload.project, null, 2), [payload.project]);

  useEffect(() => {
    try {
      window.localStorage.setItem(payload.storageKey, JSON.stringify(payload.project));
      if (payload.castInputs.length > 0) {
        window.localStorage.setItem(
          payload.castInputKey,
          JSON.stringify({ tracks: payload.castInputs, hasEnergySignal: payload.hasEnergySignal }),
        );
      } else {
        window.localStorage.removeItem(payload.castInputKey);
      }
      setMessage(
        locale === "en"
          ? "Project written. Opening Endaxis editor..."
          : "工程已写入，正在打开 Endaxis 编辑器...",
      );
      window.setTimeout(() => {
        window.location.replace(ENDAXIS_EDITOR_URL);
      }, 250);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Failed to write project locally.");
    }
  }, [
    payload.project,
    payload.storageKey,
    payload.castInputKey,
    payload.castInputs,
    payload.hasEnergySignal,
    locale,
  ]);

  function handleDownloadProject() {
    const blob = new Blob([projectJson], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `endaxis_${payload.summary.battleId}.json`;
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="page-stack">
      <section className="panel panel-muted" style={{ display: "grid", gap: 16 }}>
        <div className="breadcrumbs">
          {t.common.home} / {t.common.myBattles} / {locale === "en" ? "Timeline Editor" : "排轴编辑器"}
        </div>
        <div className="section-heading">
          <div>
            <div className="eyebrow">ENDAXIS</div>
            <h1>{locale === "en" ? "Opening Timeline Editor" : "正在打开排轴编辑器"}</h1>
            <p className="muted" style={{ margin: "8px 0 0" }}>
              {message}
            </p>
          </div>
          <a className="button-secondary" href={`/axis/${payload.summary.battleId}`}>
            {locale === "en" ? "Back to Axis View" : "返回排轴视图"}
          </a>
        </div>
        <div className="stat-grid stat-grid-4">
          <div className="metric-card">
            <span className="metric-label">{locale === "en" ? "Battle" : "战斗"}</span>
            <strong>{payload.summary.battleTitle}</strong>
            <span className="metric-note">{payload.summary.battleId}</span>
          </div>
          <div className="metric-card">
            <span className="metric-label">{locale === "en" ? "Operators" : "角色"}</span>
            <strong>{payload.summary.rosterCount}</strong>
            <span className="metric-note">
              {payload.summary.recognizedCharacterCount}{" "}
              {locale === "en" ? "matched to Endaxis" : "个已匹配 Endaxis"}
            </span>
          </div>
          <div className="metric-card">
            <span className="metric-label">{locale === "en" ? "Action Blocks" : "动作块"}</span>
            <strong>{payload.summary.actionCount}</strong>
            <span className="metric-note">
              {payload.summary.sourceKind === "casts"
                ? locale === "en"
                  ? "Full cast sequence"
                  : "完整施法序列（含普攻）"
                : locale === "en"
                  ? "Approximated damage hits"
                  : "旧版战斗：按伤害命中近似分组"}
            </span>
          </div>
          <div className="metric-card">
            <span className="metric-label">{locale === "en" ? "Fallback Export" : "备用导入"}</span>
            <button className="button-secondary" onClick={handleDownloadProject} type="button">
              {t.common.exportJson}
            </button>
            <span className="metric-note">
              {locale === "en" ? "Manual import in Endaxis" : "可在 Endaxis 中手动导入"}
            </span>
          </div>
        </div>
        <div className="panel-inset">
          <span className="muted">
            {locale === "en" ? "If redirect does not trigger automatically, open " : "如果没有自动跳转，可以直接打开 "}
            <a className="text-link" href={ENDAXIS_EDITOR_URL}>
              Endaxis Editor
            </a>
            .
          </span>
        </div>
      </section>
    </div>
  );
}
