// 本文件包含副本榜单分组数据，并支持中英双语展示。

import type { Locale } from "../../lib/i18n/types";

export type RankingGroupKey =
  | "crisis"
  | "crisisFragment"
  | "contingencyContract"
  | "warEcho"
  | "shadowPhase1"
  | "shadowPhase2"
  | "shadowPhase3"
  | "shadowPhase4";

export type RankingBossEntry = {
  slug: string;
  name: string;
  dungeonName: string;
};

export type RankingGroup = {
  key: RankingGroupKey;
  label: string;
  note: string;
  bosses: RankingBossEntry[];
};

export const rankingGroups: RankingGroup[] = [
  {
    key: "crisis",
    label: "危境再现",
    note: "收录 6 个危境再现首领",
    bosses: [
      { slug: "dung01_group_bossrush01", name: "危境再现·罗丹", dungeonName: "危境再现" },
      { slug: "dung01_group_bossrush02", name: "危境再现·三位一体", dungeonName: "危境再现" },
      { slug: "dung01_group_bossrush03", name: "危境再现·白垩界卫", dungeonName: "危境再现" },
      { slug: "dung02_group_bossrush01", name: "危境再现·阮一", dungeonName: "危境再现" },
      { slug: "dung02_group_bossrush02", name: "危境再现·聂菲斯", dungeonName: "危境再现" },
      { slug: "dung02_group_bossrush03", name: "危境再现·阿莱克琉斯", dungeonName: "危境再现" },
    ],
  },
  {
    key: "crisisFragment",
    label: "危境碎片",
    note: "巨山犼兽 / 蚀影噪雷",
    bosses: [
      { slug: "dung02_group_minibossrush01", name: "巨山犼兽", dungeonName: "危境碎片" },
      { slug: "dung02_group_minibossrush02", name: "蚀影噪雷", dungeonName: "危境碎片" },
    ],
  },
  {
    key: "contingencyContract",
    label: "危机合约",
    note: "活动榜单",
    bosses: [
      { slug: "indie_group_ccdg", name: "危机合约", dungeonName: "危机合约" },
    ],
  },
  {
    key: "warEcho",
    label: "战争回响",
    note: "收录全部 8 关最高难度（残酷）",
    bosses: [
      { slug: "indie_battletower001_ex", name: "白刃穿水·残酷", dungeonName: "战争回响" },
      { slug: "indie_battletower002_ex", name: "野性旧事·残酷", dungeonName: "战争回响" },
      { slug: "indie_battletower003_ex", name: "弓弩表象·残酷", dungeonName: "战争回响" },
      { slug: "indie_battletower004_ex", name: "斧柄纪年·残酷", dungeonName: "战争回响" },
      { slug: "indie_battletower005_ex", name: "铳弹砺石·残酷", dungeonName: "战争回响" },
      { slug: "indie_battletower006_ex", name: "裂地旧创·残酷", dungeonName: "战争回响" },
      { slug: "indie_battletower007_ex", name: "死兽鸣吼·残酷", dungeonName: "战争回响" },
      { slug: "indie_battletower008_ex", name: "战争简史·残酷", dungeonName: "战争回响" },
    ],
  },
  {
    key: "shadowPhase1",
    label: "影拓丰碑1期",
    note: "收录 9 个苦难副本",
    bosses: [
      { slug: "indie_hard008_s", name: "怨憎雾海·苦难", dungeonName: "影拓丰碑1期 · 灼痛疤痕" },
      { slug: "indie_hard009_s", name: "血肉熔点·苦难", dungeonName: "影拓丰碑1期 · 灼痛疤痕" },
      { slug: "indie_hard007_s", name: "呼吼炽焰·苦难", dungeonName: "影拓丰碑1期 · 灼痛疤痕" },
      { slug: "indie_hard002_s", name: "矢影环伺·苦难", dungeonName: "影拓丰碑1期 · 无机造物" },
      { slug: "indie_hard001_s", name: "狂冲盾止·苦难", dungeonName: "影拓丰碑1期 · 无机造物" },
      { slug: "indie_hard003_s", name: "安于磐石·苦难", dungeonName: "影拓丰碑1期 · 无机造物" },
      { slug: "indie_hard006_s", name: "毒雾求生·苦难", dungeonName: "影拓丰碑1期 · 大地的弃子" },
      { slug: "indie_hard005_s", name: "旁门外道·苦难", dungeonName: "影拓丰碑1期 · 大地的弃子" },
      { slug: "indie_hard004_s", name: "弩斧相应·苦难", dungeonName: "影拓丰碑1期 · 大地的弃子" },
    ],
  },
  {
    key: "shadowPhase2",
    label: "影拓丰碑2期",
    note: "浊流具现 · 6 个苦难副本",
    bosses: [
      { slug: "indie_hard013_s", name: "沉寂视界·苦难", dungeonName: "影拓丰碑2期 · 浊流具现" },
      { slug: "indie_hard014_s", name: "枯竭海退·苦难", dungeonName: "影拓丰碑2期 · 浊流具现" },
      { slug: "indie_hard010_s", name: "潮涌遗恨·苦难", dungeonName: "影拓丰碑2期 · 浊流具现" },
      { slug: "indie_hard012_s", name: "污浊血脉·苦难", dungeonName: "影拓丰碑2期 · 浊流具现" },
      { slug: "indie_hard015_s", name: "潜流绝窟·苦难", dungeonName: "影拓丰碑2期 · 浊流具现" },
      { slug: "indie_hard011_s", name: "霜冻联结·苦难", dungeonName: "影拓丰碑2期 · 浊流具现" },
    ],
  },
  {
    key: "shadowPhase3",
    label: "影拓丰碑3期",
    note: "死寂争鸣 · 6 个苦难副本",
    bosses: [
      { slug: "indie_hard016_s", name: "仪式旋流·苦难", dungeonName: "影拓丰碑3期 · 死寂争鸣" },
      { slug: "indie_hard017_s", name: "死寂表象·苦难", dungeonName: "影拓丰碑3期 · 死寂争鸣" },
      { slug: "indie_hard018_s", name: "忿鼓咆声·苦难", dungeonName: "影拓丰碑3期 · 死寂争鸣" },
      { slug: "indie_hard019_s", name: "刺痛盾阵·苦难", dungeonName: "影拓丰碑3期 · 死寂争鸣" },
      { slug: "indie_hard020_s", name: "溶解窥看·苦难", dungeonName: "影拓丰碑3期 · 死寂争鸣" },
      { slug: "indie_hard021_s", name: "冯河断水·苦难", dungeonName: "影拓丰碑3期 · 死寂争鸣" },
    ],
  },
  {
    key: "shadowPhase4",
    label: "影拓丰碑4期",
    note: "山中见犼 · 4 个苦难副本",
    bosses: [
      { slug: "indie_hard022_s", name: "撼山雾火·苦难", dungeonName: "影拓丰碑4期 · 山中见犼" },
      { slug: "indie_hard023_s", name: "兽群把戏·苦难", dungeonName: "影拓丰碑4期 · 山中见犼" },
      { slug: "indie_hard024_s", name: "山犼争王·苦难", dungeonName: "影拓丰碑4期 · 山中见犼" },
      { slug: "indie_hard025_s", name: "清波访客·苦难", dungeonName: "影拓丰碑4期 · 山中见犼" },
    ],
  },
];

const GROUP_LABELS_EN: Record<RankingGroupKey, { label: string; note: string }> = {
  crisis: { label: "Crisis Replay", note: "Includes 6 Crisis Replay Bosses" },
  crisisFragment: { label: "Crisis Fragments", note: "Craghowler / Blitzcrash Blightshade" },
  contingencyContract: { label: "Contingency Contract", note: "Event Speedrun" },
  warEcho: { label: "Echoes of War", note: "All 8 Brutal Difficulty Encounters" },
  shadowPhase1: { label: "Umbral Monument: Phase 1", note: "9 Agony Instances" },
  shadowPhase2: { label: "Umbral Monument: Phase 2", note: "Turbid Manifestation · 6 Agony Instances" },
  shadowPhase3: { label: "Umbral Monument: Phase 3", note: "Clamor of Silence · 6 Agony Instances" },
  shadowPhase4: { label: "Umbral Monument: Phase 4", note: "Hou in the Mountains · 4 Agony Instances" },
};

export function getRankingGroupLabel(groupKey: RankingGroupKey, locale: Locale = "en"): string {
  if (locale === "en" && GROUP_LABELS_EN[groupKey]) {
    return GROUP_LABELS_EN[groupKey].label;
  }
  return rankingGroups.find((g) => g.key === groupKey)?.label ?? groupKey;
}

export function getRankingGroupNote(groupKey: RankingGroupKey, locale: Locale = "en"): string {
  if (locale === "en" && GROUP_LABELS_EN[groupKey]) {
    return GROUP_LABELS_EN[groupKey].note;
  }
  return rankingGroups.find((g) => g.key === groupKey)?.note ?? "";
}
