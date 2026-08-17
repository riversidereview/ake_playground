"use client";

import type { ContractTag } from "../lib/api/types";
import { hasContractTagData } from "../lib/contract-tags";

import { resolveAssetUrl } from "../lib/i18n/terms";

type ContractTagSummaryProps = {
  score?: number | null;
  tags?: ContractTag[] | null;
  compact?: boolean;
};

function getTotalScore(score: number | null | undefined, tags: ContractTag[]) {
  return score ?? tags.reduce((sum, tag) => sum + tag.score, 0);
}

function getTagLabel(tag: ContractTag) {
  return tag.name?.trim() || tag.description?.trim() || tag.buffId?.trim() || `Tag ${tag.tagId}`;
}

function cleanDescription(value: string | null | undefined) {
  return (
    value
      ?.replace(/<color=[^>]+>/gi, "")
      .replace(/<\/color>/gi, "")
      .replace(/\s+/g, " ")
      .trim() || ""
  );
}

function getTagMeta(tag: ContractTag) {
  const description = cleanDescription(tag.description);
  if (description && !/[{}@]/.test(description)) {
    return description;
  }
  return `Tag ${tag.tagId}`;
}

function getTagTooltip(tag: ContractTag) {
  const parts = [`${getTagLabel(tag)} +${tag.score}`, `Tag ${tag.tagId}`];
  const meta = getTagMeta(tag);
  if (meta !== `Tag ${tag.tagId}`) {
    parts.push(meta);
  }
  if (tag.iconId) {
    parts.push(tag.iconId);
  }
  if (tag.buffId) {
    parts.push(tag.buffId);
  }
  return parts.join("\n");
}

export function ContractTagSummary({ score, tags, compact = false }: ContractTagSummaryProps) {
  const tagList = tags ?? [];
  if (!hasContractTagData(score, tagList)) {
    return null;
  }

  const visibleTags = compact ? tagList.slice(0, 3) : tagList;
  const hiddenCount = Math.max(tagList.length - visibleTags.length, 0);
  const totalScore = getTotalScore(score, tagList);

  return (
    <div className={`contract-tag-summary${compact ? " is-compact" : " is-full"}`}>
      <span aria-label={`合约评分 ${totalScore} 分`} className="contract-tag-score">
        <span className="contract-tag-score-label">合约评分</span>
        <strong>{totalScore}</strong>
        <span className="contract-tag-score-unit">分</span>
        {!compact ? <small>{tagList.length ? `${tagList.length} 个 tag` : "无明细"}</small> : null}
      </span>
      {visibleTags.length ? (
        <div className="contract-tag-list">
          {visibleTags.map((tag, index) => {
            const tooltip = getTagTooltip(tag);
            return (
              <span
                aria-label={tooltip}
                className="contract-tag-tile"
                data-tooltip={tooltip}
                key={`${tag.tagId}-${tag.buffId ?? "tag"}-${index}`}
                title={tooltip}
              >
                {tag.iconUrl ? (
                  <img
                    alt=""
                    aria-hidden="true"
                    className="contract-tag-icon"
                    loading="lazy"
                    onError={(event) => {
                      event.currentTarget.style.display = "none";
                    }}
                    src={resolveAssetUrl(tag.iconUrl) ?? undefined}
                  />
                ) : (
                  <span aria-hidden="true" className="contract-tag-icon-fallback">
                    #
                  </span>
                )}
                <span className="contract-tag-points">+{tag.score}</span>
              </span>
            );
          })}
          {hiddenCount > 0 ? <span className="contract-tag-chip is-more">+{hiddenCount}</span> : null}
        </div>
      ) : (
        <span className="contract-tag-empty">未记录 tag 明细</span>
      )}
    </div>
  );
}
