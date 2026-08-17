import assert from "node:assert/strict";
import { enDictionary } from "../lib/i18n/en";
import { zhDictionary } from "../lib/i18n/zh";
import {
  BOSS_NAME_EN,
  DUNGEON_NAME_EN,
  PROFESSION_NAMES,
  DAMAGE_ELEMENT_LABELS,
  SKILL_CATEGORY_LABELS,
  BUFF_ZONE_LABELS,
  TIMELINE_ZERO_SOURCE_LABELS,
  WEAPON_NAME_EN,
  WEAPON_NAME_ZH,
  EQUIP_SUIT_NAME_EN,
  EQUIP_SUIT_NAME_ZH,
  EQUIP_PIECE_NAME_EN,
  EQUIP_PIECE_NAME_ZH,
  getLocalizedWeaponName,
  getLocalizedEquipSuitName,
  getLocalizedEquipPieceName,
  getLocalizedEquipPartName,
} from "../lib/i18n/terms";
import {
  formatBossDisplayName,
  formatBossEyebrow,
} from "../lib/format/boss-display";
import {
  getBattleSkillCategoryLabel,
  getPreferredBattleSkillDisplayName,
} from "../lib/format/skill-display";
import {
  getRankingGroupLabel,
  getRankingGroupNote,
} from "../features/records/ranking-groups.generated";

function checkKeyParity(
  enObj: Record<string, any>,
  zhObj: Record<string, any>,
  path = "",
) {
  const enKeys = Object.keys(enObj);
  const zhKeys = Object.keys(zhObj);

  for (const key of enKeys) {
    const currentPath = path ? `${path}.${key}` : key;
    assert.ok(
      key in zhObj,
      `Missing key in zhDictionary: ${currentPath}`,
    );

    const enVal = enObj[key];
    const zhVal = zhObj[key];

    assert.equal(
      typeof enVal,
      typeof zhVal,
      `Type mismatch at ${currentPath}: en is ${typeof enVal}, zh is ${typeof zhVal}`,
    );

    if (typeof enVal === "object" && enVal !== null && !Array.isArray(enVal)) {
      checkKeyParity(enVal, zhVal, currentPath);
    }
  }

  for (const key of zhKeys) {
    const currentPath = path ? `${path}.${key}` : key;
    assert.ok(
      key in enObj,
      `Missing key in enDictionary: ${currentPath}`,
    );
  }
}

console.log("=== 1. Testing Dictionary Key Parity ===");
checkKeyParity(enDictionary, zhDictionary);
console.log("✔ Dictionary keys match 100% between EN and ZH!");

console.log("\n=== 2. Testing Arknights: Endfield Term Mappings ===");
// Boss names
assert.equal(BOSS_NAME_EN["dung01_group_bossrush01"], "Crisis Replay: Rhodagn");
assert.equal(BOSS_NAME_EN["indie_group_ccdg"], "Contingency Contract");
assert.equal(BOSS_NAME_EN["indie_hard022_s"], "Earthshaking Hazefyre: Agony");

// Dungeon names
assert.equal(DUNGEON_NAME_EN["危境再现"], "Crisis Replay");
assert.equal(DUNGEON_NAME_EN["危机合约"], "Contingency Contract");
assert.equal(DUNGEON_NAME_EN["斧柄纪年·残酷"], "Age of Axes: Brutal");

// Profession names
assert.equal(PROFESSION_NAMES.en["近卫"], "Guard");
assert.equal(PROFESSION_NAMES.zh["近卫"], "近卫");
assert.equal(PROFESSION_NAMES.en["术士"], "Caster");

// Elements
assert.equal(DAMAGE_ELEMENT_LABELS.en["fire"], "Heat");
assert.equal(DAMAGE_ELEMENT_LABELS.zh["fire"], "灼热");
assert.equal(DAMAGE_ELEMENT_LABELS.en["pulse"], "Pulse");
assert.equal(DAMAGE_ELEMENT_LABELS.zh["pulse"], "电磁");
assert.equal(DAMAGE_ELEMENT_LABELS.en["cryst"], "Cryo");
assert.equal(DAMAGE_ELEMENT_LABELS.zh["cryst"], "寒冷");

// Skill categories
assert.equal(SKILL_CATEGORY_LABELS.en["normal"], "Basic Attack");
assert.equal(SKILL_CATEGORY_LABELS.zh["normal"], "普攻");
assert.equal(SKILL_CATEGORY_LABELS.en["ultimate"], "Ultimate");
assert.equal(SKILL_CATEGORY_LABELS.zh["ultimate"], "终结技");

// Buff zones
assert.equal(BUFF_ZONE_LABELS.en["atk"], "ATK Boost");
assert.equal(BUFF_ZONE_LABELS.zh["atk"], "攻击");
assert.equal(BUFF_ZONE_LABELS.en["dmg_inc"], "DMG Boost");
assert.equal(BUFF_ZONE_LABELS.zh["dmg_inc"], "增伤");

// Zero anchors
assert.equal(TIMELINE_ZERO_SOURCE_LABELS.en["official_timer_start"], "Official Start");
assert.equal(TIMELINE_ZERO_SOURCE_LABELS.zh["official_timer_start"], "官方开始");

// Weapons
assert.equal(WEAPON_NAME_EN["wpn_sword_0013"], "Eminent Repute");
assert.equal(WEAPON_NAME_EN["显赫声名"], "Eminent Repute");
assert.equal(WEAPON_NAME_ZH["Eminent Repute"], "显赫声名");
assert.equal(getLocalizedWeaponName("落草", "en"), "Brigand's Calling");
assert.equal(getLocalizedWeaponName("Brigand's Calling", "zh"), "落草");
assert.equal(getLocalizedWeaponName("wpn_claym_0008", "en"), "Sundered Prince");

// Equipment Suits
assert.equal(EQUIP_SUIT_NAME_EN["suit_atk02"], "Type 50 Yinglung");
assert.equal(EQUIP_SUIT_NAME_EN["50式应龙"], "Type 50 Yinglung");
assert.equal(getLocalizedEquipSuitName("阿伯莉遗声", "en"), "Aburrey's Legacy");
assert.equal(getLocalizedEquipSuitName("Frontiers", "zh"), "拓荒");

// Equipment Pieces
assert.equal(getLocalizedEquipPieceName("50式应龙重甲", "en"), "Type 50 Yinglung Heavy Armor");
assert.equal(getLocalizedEquipPieceName("Type 50 Yinglung Heavy Armor", "zh"), "50式应龙重甲");
assert.equal(getLocalizedEquipPieceName("item_equip_t4_parts_wuling00_body_01", "en"), "AIC Fieldwork Armor");
assert.equal(getLocalizedEquipPieceName("简易护甲", "en"), "Basic Armor");
assert.equal(getLocalizedEquipPieceName("救赎者重甲", "en"), "Redeemer Heavy Armor");

// Equipment Parts
assert.equal(getLocalizedEquipPartName("护甲", "en"), "Armor");
assert.equal(getLocalizedEquipPartName("护手", "en"), "Gloves");
assert.equal(getLocalizedEquipPartName("配件", "en"), "Kit");
assert.equal(getLocalizedEquipPartName("Armor", "zh"), "护甲");
console.log("✔ Domain term dictionaries verified successfully!");

console.log("\n=== 3. Testing Boss & Skill Formatters ===");
// Boss Display Name
assert.equal(
  formatBossDisplayName({ bossName: "危境再现：罗丹", bossSlug: "dung01_group_bossrush01" }, "en"),
  "Crisis Replay: Rhodagn",
);
assert.equal(
  formatBossDisplayName({ bossName: "危境再现：罗丹", bossSlug: "dung01_group_bossrush01" }, "zh"),
  "危境再现：罗丹",
);
assert.equal(
  formatBossDisplayName({ bossName: "精锐行刑人" }, "en"),
  "Elite Executioner",
);
// Boss Eyebrow
assert.equal(formatBossEyebrow({ dungeonName: "危境再现" }, "en"), "Crisis Replay");
assert.equal(formatBossEyebrow({ dungeonName: "危境再现" }, "zh"), "危境再现");
assert.equal(formatBossEyebrow({ dungeonName: "斧柄纪年·残酷" }, "en"), "Age of Axes: Brutal");
assert.equal(formatBossEyebrow({ dungeonName: "斧柄纪年·残酷" }, "zh"), "斧柄纪年·残酷");

// Skill category formatting
assert.equal(getBattleSkillCategoryLabel("A1", null, "en"), "Basic Attack");
assert.equal(getBattleSkillCategoryLabel("A1", null, "zh"), "普攻");
assert.equal(getBattleSkillCategoryLabel("战技", "chr_001_normal_skill", "en"), "Battle Skill");
assert.equal(getBattleSkillCategoryLabel("战技", "chr_001_normal_skill", "zh"), "战技");
assert.equal(getBattleSkillCategoryLabel("终结技", "chr_001_ult_attack", "en"), "Ultimate");
assert.equal(getBattleSkillCategoryLabel("终结技", "chr_001_ult_attack", "zh"), "终结技");

// Skill display name
assert.equal(
  getPreferredBattleSkillDisplayName("连携技", "chr_001_combo_skill", "en"),
  "Combo Skill",
);
assert.equal(
  getPreferredBattleSkillDisplayName("连携技", "chr_001_combo_skill", "zh"),
  "连携技",
);
assert.equal(
  getPreferredBattleSkillDisplayName("寒冷击破触发", "buff_common_cryst_triggered_physical_break", "en"),
  "Cryo Break Trigger",
);
assert.equal(
  getPreferredBattleSkillDisplayName("寒冷击破触发", "buff_common_cryst_triggered_physical_break", "zh"),
  "寒冷击破触发",
);

// Damage type localization (specifically requested by user)
assert.equal(
  getPreferredBattleSkillDisplayName("物理浮空伤害", "buff_physical_airborne", "en"),
  "Physical Airborne DMG",
);
assert.equal(
  getPreferredBattleSkillDisplayName("物理浮空伤害", "buff_physical_airborne", "zh"),
  "物理浮空伤害",
);
assert.equal(
  getPreferredBattleSkillDisplayName("物理浮空伤害", null, "en"),
  "Physical Airborne DMG",
);
assert.equal(
  getPreferredBattleSkillDisplayName("猛击", "buff_physical_crushed", "en"),
  "Crush",
);
assert.equal(
  getPreferredBattleSkillDisplayName("破防", "buff_physical_no_guard", "en"),
  "Breach",
);
assert.equal(
  getPreferredBattleSkillDisplayName("倒地", "buff_physical_knockdown", "en"),
  "Knock Down",
);
assert.equal(
  getPreferredBattleSkillDisplayName("爪印斫痕", "buff_chr_0028_wulfa_normal_bleed", "en"),
  "Claw Slash",
);
assert.equal(
  getPreferredBattleSkillDisplayName("沸血", "buff_chr_0028_wulfa_normal_bleed_crit_extra_damage", "en"),
  "Boiling Blood",
);
assert.equal(
  getPreferredBattleSkillDisplayName("灼热爆发", null, "en"),
  "Heat Burst",
);
assert.equal(
  getPreferredBattleSkillDisplayName("伊冯连携 / 机器人持续伤害", "chr_0017_yvonne_skill_162", "en"),
  "Yvonne Combo / Drone DoT",
);
console.log("✔ Boss & skill formatting helpers verified successfully!");

console.log("\n=== 4. Testing Ranking Groups Metadata ===");
assert.equal(getRankingGroupLabel("crisis", "zh"), "危境再现");
assert.equal(getRankingGroupLabel("crisis", "en"), "Crisis Replay");
assert.equal(getRankingGroupNote("crisis", "zh"), "收录 6 个危境再现首领");
assert.equal(getRankingGroupNote("crisis", "en"), "Includes 6 Crisis Replay Bosses");
console.log("✔ Ranking groups metadata bilingual helpers verified successfully!");

console.log("\n=== ALL INTERNATIONALIZATION TESTS PASSED! ===");
