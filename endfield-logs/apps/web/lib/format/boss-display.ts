import type { Locale } from "../i18n/types";
import { getLocalizedBossName, getLocalizedDungeonName } from "../i18n/terms";

export const CRISIS_CONTRACT_BOSS_SLUG = "indie_group_ccdg";
export const CRISIS_CONTRACT_DUNGEON_NAME = "危机合约";
export const CRISIS_CONTRACT_DUNGEON_NAME_EN = "Contingency Contract";

type BossDisplayInput = {
  bossSlug?: string | null;
  bossName?: string | null;
  dungeonName?: string | null;
};

export function isCrisisContractDisplay({ bossSlug, dungeonName }: BossDisplayInput) {
  return (
    bossSlug === CRISIS_CONTRACT_BOSS_SLUG ||
    dungeonName === CRISIS_CONTRACT_DUNGEON_NAME ||
    dungeonName === CRISIS_CONTRACT_DUNGEON_NAME_EN
  );
}

export function formatBossDisplayName(input: BossDisplayInput, locale: Locale = "en") {
  if (isCrisisContractDisplay(input)) {
    return locale === "en" ? CRISIS_CONTRACT_DUNGEON_NAME_EN : CRISIS_CONTRACT_DUNGEON_NAME;
  }
  const rawBossName = input.bossName?.trim() || input.dungeonName?.trim() || (locale === "en" ? "Unknown Encounter" : "未知首领");
  if (input.bossSlug) {
    return getLocalizedBossName(input.bossSlug, rawBossName, locale);
  }
  return getLocalizedBossName(rawBossName, getLocalizedDungeonName(rawBossName, locale), locale);
}

export function formatBossEyebrow(input: BossDisplayInput, locale: Locale = "en") {
  if (isCrisisContractDisplay(input)) {
    return locale === "en" ? "EVENT SPEEDRUN" : "活动竞速";
  }
  const rawDungeonName = input.dungeonName?.trim() || (locale === "en" ? "Speedrun Leaderboard" : "竞速榜单");
  return getLocalizedDungeonName(rawDungeonName, locale);
}

