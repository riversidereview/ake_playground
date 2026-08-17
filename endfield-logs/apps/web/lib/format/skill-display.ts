import type { Locale } from "../i18n/types";
import { SKILL_CATEGORY_LABELS } from "../i18n/terms";

const ATTACK_INDEX_RE = /_attack(\d+)(?:$|_)/i;
const COMBO_SKILL_KEY_RE = /(?:^|_)combo(?:_\d+)?_skill(?:$|_)/i;

const ELEMENT_ZH_TO_EN: Record<string, string> = {
  物理: "Physical",
  灼热: "Heat",
  电磁: "Pulse",
  寒冷: "Cryo",
  自然: "Nature",
  法术: "Arts",
  火: "Heat",
  雷: "Pulse",
  冰: "Cryo",
};

const ELEMENT_EN_TO_ZH: Record<string, string> = {
  Physical: "物理",
  Heat: "灼热",
  Pulse: "电磁",
  Cryo: "寒冷",
  Nature: "自然",
  Arts: "法术",
};

const SKILL_KEY_OVERRIDES: Record<string, { zh: string; en: string }> = {
  buff_physical_airborne: {
    zh: "物理浮空伤害",
    en: "Physical Airborne DMG",
  },
  buff_physical_crushed: {
    zh: "猛击",
    en: "Crush",
  },
  buff_physical_knockdown: {
    zh: "倒地",
    en: "Knock Down",
  },
  buff_physical_no_guard: {
    zh: "破防",
    en: "Breach",
  },
  buff_chr_0028_wulfa_normal_bleed: {
    zh: "爪印斫痕",
    en: "Claw Slash",
  },
  buff_chr_0028_wulfa_normal_bleed_effect: {
    zh: "爪印斫痕",
    en: "Claw Slash",
  },
  buff_chr_0028_wulfa_normal_bleed_crit_extra_damage: {
    zh: "沸血",
    en: "Boiling Blood",
  },
  buff_chr_0028_wulfa_combo_2_damage: {
    zh: "燎影时刻",
    en: "Blazing Shadow Moment",
  },
  buff_common_cryst_triggered_physical_break: {
    zh: "寒冷击破触发",
    en: "Cryo Break Trigger",
  },
  buff_common_heal_moss_1: {
    zh: "治疗苔藓",
    en: "Healing Moss",
  },
  buff_common_heal_moss_2: {
    zh: "治疗苔藓",
    en: "Healing Moss",
  },
  buff_common_originum_frozen: {
    zh: "源石冻结",
    en: "Originium Freeze",
  },
  chr_0017_yvonne_skill_162: {
    zh: "伊冯连携 / 机器人持续伤害",
    en: "Yvonne Combo / Drone DoT",
  },
  chr_0017_yvonne_skill_163: {
    zh: "伊冯连携 / 机器人终结爆炸",
    en: "Yvonne Combo / Drone Final Explosion",
  },
};

const SKILL_NAME_OVERRIDES: Record<string, { zh: string; en: string }> = {
  "cryst triggered physical break": {
    zh: "寒冷击破触发",
    en: "Cryo Break Trigger",
  },
  "物理浮空伤害": {
    zh: "物理浮空伤害",
    en: "Physical Airborne DMG",
  },
  "physical airborne dmg": {
    zh: "物理浮空伤害",
    en: "Physical Airborne DMG",
  },
  "浮空伤害": {
    zh: "浮空伤害",
    en: "Airborne DMG",
  },
  "airborne dmg": {
    zh: "浮空伤害",
    en: "Airborne DMG",
  },
  "猛击": {
    zh: "猛击",
    en: "Crush",
  },
  "crush": {
    zh: "猛击",
    en: "Crush",
  },
  "倒地": {
    zh: "倒地",
    en: "Knock Down",
  },
  "knock down": {
    zh: "倒地",
    en: "Knock Down",
  },
  "knockdown": {
    zh: "倒地",
    en: "Knock Down",
  },
  "破防": {
    zh: "破防",
    en: "Breach",
  },
  "breach": {
    zh: "破防",
    en: "Breach",
  },
  "爪印斫痕": {
    zh: "爪印斫痕",
    en: "Claw Slash",
  },
  "claw slash": {
    zh: "爪印斫痕",
    en: "Claw Slash",
  },
  "沸血": {
    zh: "沸血",
    en: "Boiling Blood",
  },
  "boiling blood": {
    zh: "沸血",
    en: "Boiling Blood",
  },
  "燎影时刻": {
    zh: "燎影时刻",
    en: "Blazing Shadow Moment",
  },
  "blazing shadow moment": {
    zh: "燎影时刻",
    en: "Blazing Shadow Moment",
  },
  "治疗苔藓": {
    zh: "治疗苔藓",
    en: "Healing Moss",
  },
  "healing moss": {
    zh: "治疗苔藓",
    en: "Healing Moss",
  },
  "源石冻结": {
    zh: "源石冻结",
    en: "Originium Freeze",
  },
  "originium freeze": {
    zh: "源石冻结",
    en: "Originium Freeze",
  },
  "寒冷击破触发": {
    zh: "寒冷击破触发",
    en: "Cryo Break Trigger",
  },
  "cryo break trigger": {
    zh: "寒冷击破触发",
    en: "Cryo Break Trigger",
  },
  "热能击破触发": {
    zh: "热能击破触发",
    en: "Heat Break Trigger",
  },
  "heat break trigger": {
    zh: "热能击破触发",
    en: "Heat Break Trigger",
  },
  "电磁击破触发": {
    zh: "电磁击破触发",
    en: "Pulse Break Trigger",
  },
  "pulse break trigger": {
    zh: "电磁击破触发",
    en: "Pulse Break Trigger",
  },
  "物理击破触发": {
    zh: "物理击破触发",
    en: "Phys Break Trigger",
  },
  "phys break trigger": {
    zh: "物理击破触发",
    en: "Phys Break Trigger",
  },
  "自然击破触发": {
    zh: "自然击破触发",
    en: "Nature Break Trigger",
  },
  "nature break trigger": {
    zh: "自然击破触发",
    en: "Nature Break Trigger",
  },
  "灼热爆发": {
    zh: "灼热爆发",
    en: "Heat Burst",
  },
  "heat burst": {
    zh: "灼热爆发",
    en: "Heat Burst",
  },
  "电磁爆发": {
    zh: "电磁爆发",
    en: "Pulse Burst",
  },
  "pulse burst": {
    zh: "电磁爆发",
    en: "Pulse Burst",
  },
  "寒冷爆发": {
    zh: "寒冷爆发",
    en: "Cryo Burst",
  },
  "cryo burst": {
    zh: "寒冷爆发",
    en: "Cryo Burst",
  },
  "自然爆发": {
    zh: "自然爆发",
    en: "Nature Burst",
  },
  "nature burst": {
    zh: "自然爆发",
    en: "Nature Burst",
  },
  "法术爆发": {
    zh: "法术爆发",
    en: "Arts Burst",
  },
  "arts burst": {
    zh: "法术爆发",
    en: "Arts Burst",
  },
  "导电": {
    zh: "导电",
    en: "Electrification",
  },
  "electrification": {
    zh: "导电",
    en: "Electrification",
  },
  "腐蚀": {
    zh: "腐蚀",
    en: "Corrosion",
  },
  "corrosion": {
    zh: "腐蚀",
    en: "Corrosion",
  },
  "燃烧": {
    zh: "燃烧",
    en: "Combustion",
  },
  "combustion": {
    zh: "燃烧",
    en: "Combustion",
  },
  "冻结": {
    zh: "冻结",
    en: "Solidification",
  },
  "solidification": {
    zh: "冻结",
    en: "Solidification",
  },
  "伊冯连携 / 机器人持续伤害": {
    zh: "伊冯连携 / 机器人持续伤害",
    en: "Yvonne Combo / Drone DoT",
  },
  "伊冯连携 / 机器人终结爆炸": {
    zh: "伊冯连携 / 机器人终结爆炸",
    en: "Yvonne Combo / Drone Final Explosion",
  },
};

export type BattleSkillCategory = "normal" | "skill" | "combo" | "heavy" | "ultimate" | "other";

export function getPreferredBattleSkillDisplayName(
  skillName: string,
  skillKey?: string | null,
  locale: Locale = "en",
): string {
  if (skillKey) {
    const skillKeyOverride = SKILL_KEY_OVERRIDES[skillKey.toLowerCase()];
    if (skillKeyOverride) {
      return locale === "zh" ? skillKeyOverride.zh : skillKeyOverride.en;
    }
  }
  const trimmed = skillName.trim();
  const skillNameOverride = SKILL_NAME_OVERRIDES[trimmed.toLowerCase()];
  if (skillNameOverride) {
    return locale === "zh" ? skillNameOverride.zh : skillNameOverride.en;
  }
  if (skillKey && COMBO_SKILL_KEY_RE.test(skillKey)) {
    return locale === "zh" ? "连携技" : "Combo Skill";
  }

  // Pattern-based translations
  if (locale === "en") {
    // e.g. "物理浮空伤害" -> "Physical Airborne DMG"
    const airborneMatch = trimmed.match(/^(.+?)浮空伤害$/);
    if (airborneMatch) {
      const elem = ELEMENT_ZH_TO_EN[airborneMatch[1]] || airborneMatch[1];
      return `${elem} Airborne DMG`;
    }

    // e.g. "灼热爆发" -> "Heat Burst"
    const burstMatch = trimmed.match(/^(.+?)爆发$/);
    if (burstMatch) {
      const elem = ELEMENT_ZH_TO_EN[burstMatch[1]] || burstMatch[1];
      return `${elem} Burst`;
    }

    // e.g. "灼热·电磁触发" -> "Heat · Pulse Trigger"
    const triggerMatch = trimmed.match(/^(.+?)[·・](.+?)触发$/);
    if (triggerMatch) {
      const elem1 = ELEMENT_ZH_TO_EN[triggerMatch[1]] || triggerMatch[1];
      const elem2 = ELEMENT_ZH_TO_EN[triggerMatch[2]] || triggerMatch[2];
      return `${elem1} · ${elem2} Trigger`;
    }

    // e.g. "敌方法术灼热触发" -> "Enemy Arts Heat Trigger"
    const enemyArtsMatch = trimmed.match(/^敌方法术(.+?)触发$/);
    if (enemyArtsMatch) {
      const elem = ELEMENT_ZH_TO_EN[enemyArtsMatch[1]] || enemyArtsMatch[1];
      return `Enemy Arts ${elem} Trigger`;
    }

    if (trimmed === "战技") return "Battle Skill";
    if (trimmed === "连携" || trimmed === "连携技") return "Combo";
    if (trimmed === "终结技" || trimmed === "大招") return "Ultimate";
    if (trimmed === "普攻") return "Basic Attack";
    if (trimmed === "重击" || trimmed === "处决") return "Heavy Attack";
  } else {
    // locale === "zh"
    const airborneEnMatch = trimmed.match(/^(.+?)\s+Airborne\s+DMG$/i);
    if (airborneEnMatch) {
      const elem = ELEMENT_EN_TO_ZH[airborneEnMatch[1]] || airborneEnMatch[1];
      return `${elem}浮空伤害`;
    }

    const burstEnMatch = trimmed.match(/^(.+?)\s+Burst$/i);
    if (burstEnMatch) {
      const elem = ELEMENT_EN_TO_ZH[burstEnMatch[1]] || burstEnMatch[1];
      return `${elem}爆发`;
    }

    if (trimmed === "Battle Skill" || trimmed === "BS") return "战技";
    if (trimmed === "Combo" || trimmed === "Combo Skill") return "连携";
    if (trimmed === "Ultimate" || trimmed === "ULT") return "大招";
    if (trimmed === "Basic Attack" || trimmed === "Normal Attack" || trimmed === "BA") return "普攻";
    if (trimmed === "Heavy Attack" || trimmed === "Finisher" || trimmed === "Execution") return "重击";
  }

  return trimmed;
}

export function getBattleSkillCategory(skillName: string, skillKey?: string | null): BattleSkillCategory {
  const displayName = getPreferredBattleSkillDisplayName(skillName, skillKey, "zh").trim();
  if (/^A[1-4]$/i.test(displayName) || /^(Basic Attack|Normal Attack|普攻|BA)/i.test(displayName)) {
    return "normal";
  }
  if (displayName === "战技" || displayName === "Battle Skill" || displayName === "BS") {
    return "skill";
  }
  if (displayName === "连携技" || displayName === "连携" || displayName === "Combo Skill" || displayName === "Combo") {
    return "combo";
  }
  if (
    displayName === "重击" ||
    displayName === "处决" ||
    displayName === "Heavy Attack" ||
    displayName === "Finisher" ||
    displayName === "Execution" ||
    displayName === "Hvy"
  ) {
    return "heavy";
  }
  if (displayName === "终结技" || displayName === "大招" || displayName === "Ultimate" || displayName === "ULT") {
    return "ultimate";
  }
  if (!skillKey) {
    return "other";
  }

  const lowered = skillKey.toLowerCase();
  if (lowered.includes("_ult_attack") || lowered.includes("_ultimate_skill")) {
    return "ultimate";
  }
  if (COMBO_SKILL_KEY_RE.test(lowered)) {
    return "combo";
  }
  if (lowered.includes("_normal_skill")) {
    return "skill";
  }
  if (lowered.includes("execute") || lowered.includes("execution")) {
    return "heavy";
  }
  if (lowered.includes("power_attack") || lowered.includes("plunging_attack") || lowered.includes("heavy_attack")) {
    return "heavy";
  }

  const attackMatch = ATTACK_INDEX_RE.exec(lowered);
  if (attackMatch) {
    return "normal";
  }

  return "other";
}

export function getBattleSkillCategoryLabel(
  skillName: string,
  skillKey?: string | null,
  locale: Locale = "en",
): string {
  const category = getBattleSkillCategory(skillName, skillKey);
  return SKILL_CATEGORY_LABELS[locale][category] || SKILL_CATEGORY_LABELS[locale].other;
}

