import type { BattleDetailResponse, TimelineEvent } from "./api/types";
import { endaxisGameData } from "./generated/endaxis-gamedata";
import { formatBossDisplayName } from "./format/boss-display";
import {
  getBattleSkillCategory,
  getBattleSkillCategoryLabel,
  getPreferredBattleSkillDisplayName,
} from "./format/skill-display";

const BASE_CHARACTER_ATTACK_RE = /^chr_\d{4}_[a-z0-9]+_attack_?\d+(?:$|_)/i;
const ATTACK_SHAPE_RE = /(?:^|_)(?:power_attack|heavy_attack|plunging_attack)(?:$|_)/i;
const ULTIMATE_ATTACK_SHAPE_RE = /(?:_ult_attack|_ultimate_attack|_ultimate_skill)/i;
const ACTIVE_SKILL_KEY_RE =
  /(?:^|_)(?:normal_skill|combo(?:_\d+)?_skill|ultimate_skill|ult_attack|power_attack|heavy_attack|plunging_attack)(?:$|_)|execute|execution/i;
const PASSIVE_OR_BUFF_KEY_RE = /^(?:buff_|status_)/i;
const DELAYED_HIT_CHILD_RE =
  /(?:^|[_/\s-])(?:projhit\d*|abilityrange|indicator|bomb|field|entity|range|实体|范围)(?:$|[_/\s-])/i;
const DISPLAY_NAME_SEGMENT_NOISE_RE = /^(?:派生|实体|范围|命中|indicator|water|projhit\d*|plus|bomb|\d+)$/i;
const SKILL_HIT_GROUP_GAP_MS = 1200;
const ULTIMATE_HIT_GROUP_GAP_MS = 5000;
const ENDAXIS_STORAGE_KEY = "endaxis_autosave";

type EndaxisActionType = "basicAttack" | "battleSkill" | "comboSkill" | "ultimate" | "finisher";

type EndaxisAction = {
  id: string;
  instanceId: string;
  type: EndaxisActionType;
  skillId: string;
  sourceSkillKey: string;
  name: string;
  librarySource: "character" | "endfield-logs";
  element: string;
  icon: string;
  duration: number;
  cooldown: number;
  spCost: number;
  gaugeCost: number;
  gaugeGain: number;
  teamGaugeGain: number;
  enhancementTime: number;
  animationTime: number;
  hits: unknown[];
  logicalStartTime: number;
  startTime: number;
  notes?: string;
};

type EndaxisTrack = {
  id: string | null;
  operatorInstanceId: string | null;
  actions: EndaxisAction[];
  initialGauge: number;
  maxGaugeOverride: number | null;
  gaugeEfficiency: number;
  originiumArtsPower: number;
  weaponId: string | null;
  weaponInstanceId: string | null;
  weaponCommon1Tier: number;
  weaponCommon2Tier: number;
  weaponBuffTier: number;
  weaponAppliedDeltas: Record<string, unknown>;
  equipmentAppliedDeltas: Record<string, unknown>;
  stats: Record<string, number>;
  equipArmorId: string | null;
  equipGlovesId: string | null;
  equipAccessory1Id: string | null;
  equipAccessory2Id: string | null;
  equipArmorInstanceId: string | null;
  equipGlovesInstanceId: string | null;
  equipAccessory1InstanceId: string | null;
  equipAccessory2InstanceId: string | null;
  equipArmorRefineTier: number;
  equipGlovesRefineTier: number;
  equipAccessory1RefineTier: number;
  equipAccessory2RefineTier: number;
  linkCdReduction: number;
  operatorStatus: null;
  enemyStatus: null;
  triggerEffects: unknown[];
};

export type EndaxisProject = {
  timestamp: number;
  version: "1.0.0";
  scenarioList: {
    id: string;
    name: string;
    data: {
      tracks: EndaxisTrack[];
      connections: unknown[];
      operators: EndaxisOperatorInstance[];
      weapons: EndaxisWeaponInstance[];
      gears: EndaxisGearInstance[];
      characterOverrides: Record<string, unknown>;
      weaponOverrides: Record<string, unknown>;
      equipmentCategoryOverrides: Record<string, unknown>;
      prepDuration: number;
      prepExpanded: boolean;
      systemConstants: Record<string, unknown>;
      activeEnemyId: string;
      activeEnemyLevel: number;
      customEnemyParams: Record<string, unknown>;
      cycleBoundaries: unknown[];
      switchEvents: unknown[];
      inheritedInitialEffects: unknown[];
      inheritedInitialEnemyState: null;
      contingencyContractTags: number[];
    };
  }[];
  activeScenarioId: string;
  systemConstants: Record<string, unknown>;
  activeEnemyId: string;
  activeEnemyLevel: number;
};

type EndaxisOperatorInstance = {
  id: string;
  operatorSlug: string;
  level: number;
  promoted: boolean;
  potential: number;
  skillLevels: Record<string, number>;
  talentStates: Record<string, number>;
  trustLevel: number;
};

type EndaxisWeaponInstance = {
  id: string;
  weaponSlug: string;
  level: number;
  tuned: boolean;
  potential: number;
  skill1Level: number;
  skill2Level: number;
  skill3Level: number;
};

type EndaxisGearInstance = {
  id: string;
  gearPieceId: string;
  artificingLevels: number[];
};

type EndaxisPackedCharacter = {
  id: string;
  name: string;
  element?: string | null;
  skill_duration?: number | null;
  skill_spCost?: number | null;
  skill_gaugeGain?: number | null;
  skill_teamGaugeGain?: number | null;
  skill_damage_ticks?: EndaxisPackedDamageTick[] | null;
  link_duration?: number | null;
  link_cooldown?: number | null;
  link_gaugeGain?: number | null;
  link_damage_ticks?: EndaxisPackedDamageTick[] | null;
  ultimate_duration?: number | null;
  ultimate_gaugeMax?: number | null;
  ultimate_gaugeReply?: number | null;
  ultimate_animationTime?: number | null;
  ultimate_enhancementTime?: number | null;
  ultimate_damage_ticks?: EndaxisPackedDamageTick[] | null;
  execution_duration?: number | null;
  execution_damage_ticks?: EndaxisPackedDamageTick[] | null;
  attack_segments?: EndaxisPackedAttackSegment[] | null;
};

type EndaxisPackedDamageTick = {
  offset?: number | null;
  stagger?: number | null;
  sp?: number | null;
  spRecovery?: number | null;
  spReturn?: number | null;
  effects?: unknown[] | null;
  boundEffects?: unknown[] | null;
};

type EndaxisPackedAttackSegment = {
  duration?: number | null;
  gaugeGain?: number | null;
  damage_ticks?: EndaxisPackedDamageTick[] | null;
};

/** 排轴导出 API（/api/v1/battles/{id}/export）的施法序列条目。 */
export type BattleExportCast = {
  tsMsFromStart: number;
  endMsFromStart?: number | null;
  characterKey: string;
  skillKey: string;
  skillName?: string | null;
  skillSource?: string | null;
  /** v34+：该施放后短窗内回技力（主控重击）。老 battle 缺省 false。 */
  recoversEnergy?: boolean | null;
};

export type BattleExportRosterEntry = {
  slot?: number | null;
  characterKey?: string | null;
  characterName?: string | null;
  characterLevel?: number | null;
  characterPotential?: number | null;
  weapon?: {
    weaponTemplate?: string | null;
    weaponName?: string | null;
    weaponLevel?: number | null;
    weaponRefine?: number | null;
    iconUrl?: string | null;
    skills?: Array<{ skillKey: string; level?: number | null }> | null;
  } | null;
  equips?: unknown[] | null;
};

export type BattleExportData = {
  battleId?: string | null;
  parserVersion?: string | null;
  dungeon?: { bossKey?: string | null; bossName?: string | null; dungeonName?: string | null } | null;
  casts?: BattleExportCast[] | null;
  roster?: BattleExportRosterEntry[] | null;
};

/** 模拟器要求的最低解析器版本：v34 起带技力回复信号（主控重击精确过滤）。
 * 更早的战斗数据不全，排轴/模拟结果不准，禁止打开。 */
export const MIN_SIMULATOR_PARSER_VERSION = 34;

export function parserVersionNumber(parserVersion: string | null | undefined): number {
  const match = /v(\d+)\s*$/i.exec(String(parserVersion ?? ""));
  return match ? Number(match[1]) : 0;
}

const ENDAXIS_CAST_INPUT_KEY = "zmdlogs_axis_input";

export type EndaxisImportPayload = {
  storageKey: typeof ENDAXIS_STORAGE_KEY;
  project: EndaxisProject;
  /** 输入式施法意图：写入 localStorage[castInputKey]，由 Endaxis 引擎自建动作 */
  castInputKey: typeof ENDAXIS_CAST_INPUT_KEY;
  castInputs: EndaxisTrackCastInput[];
  /** 全战斗级：任一角色有回能重击 = 这场有技力信号，所有轨道按 recoversEnergy 门控
   * （AI 轨道整条无回能→过滤为 0）。false=老 battle，回退连招完整度。 */
  hasEnergySignal: boolean;
  summary: {
    battleId: string;
    battleTitle: string;
    rosterCount: number;
    actionCount: number;
    recognizedCharacterCount: number;
    /** casts=完整施法序列（v33+ 上传，含普攻）；timeline=旧 battle 伤害聚类近似 */
    sourceKind: "casts" | "timeline";
  };
};

const CHARACTER_SLUG_BY_KEY: Record<string, string> = {
  chr_0002_endminm: "endministrator",
  chr_0003_endminf: "endministrator",
  chr_0004_pelica: "perlica",
  chr_0005_chen: "chen-qianyu",
  chr_0006_wolfgd: "wulfgard",
  chr_0007_ikut: "arclight",
  chr_0009_azrila: "ember",
  chr_0011_seraph: "xaihi",
  chr_0012_avywen: "avywenna",
  chr_0013_aglina: "gilberta",
  chr_0014_aurora: "snowshine",
  chr_0015_lifeng: "lifeng",
  chr_0016_laevat: "laevatain",
  chr_0017_yvonne: "yvonne",
  chr_0018_dapan: "da-pan",
  chr_0019_karin: "akekuri",
  chr_0020_meurs: "catcher",
  chr_0021_whiten: "estella",
  chr_0022_bounda: "fluorite",
  chr_0023_antal: "antal",
  chr_0024_deepfin: "alesh",
  chr_0025_ardelia: "ardelia",
  chr_0026_lastrite: "last-rite",
  chr_0027_tangtang: "tangtang",
  chr_0028_wulfa: "rossi",
  chr_0029_pograni: "pogranichnik",
  chr_0030_zhuangfy: "zhuang-fangyi",
  chr_0031_mifu: "mifu",
  chr_0033_camille: "camille",
  chr_9000_endmin: "endministrator",
};

const CHARACTER_SLUG_BY_NAME: Record<string, string> = {
  管理员: "endministrator",
  佩丽卡: "perlica",
  陈千语: "chen-qianyu",
  狼卫: "wulfgard",
  弧光: "arclight",
  余烬: "ember",
  赛希: "xaihi",
  艾维文娜: "avywenna",
  洁尔佩塔: "gilberta",
  昼雪: "snowshine",
  黎风: "lifeng",
  莱万汀: "laevatain",
  伊冯: "yvonne",
  大潘: "da-pan",
  秋栗: "akekuri",
  卡契尔: "catcher",
  埃特拉: "estella",
  萤石: "fluorite",
  安塔尔: "antal",
  阿列什: "alesh",
  艾尔黛拉: "ardelia",
  别礼: "last-rite",
  汤汤: "tangtang",
  洛茜: "rossi",
  骏卫: "pogranichnik",
  庄方宜: "zhuang-fangyi",
  弭弗: "mifu",
  卡缪: "camille",
};

const ELEMENT_BY_DAMAGE_ELEMENT: Record<string, string> = {
  blaze: "heat",
  cold: "cryo",
  cryst: "cryo",
  crystal: "cryo",
  emag: "electric",
  fire: "heat",
  heat: "heat",
  ice: "cryo",
  natural: "nature",
  nature: "nature",
  physical: "physical",
  pulse: "electric",
  spell: "physical",
};

const ENDAXIS_CHARACTER_ID_BY_SLUG: Record<string, string> = {
  akekuri: "AKEKURI",
  alesh: "ALESH",
  antal: "ANTAL",
  arclight: "ARCLIGHT",
  ardelia: "ARDELIA",
  avywenna: "AVYWENNA",
  camille: "CAMILLE",
  catcher: "CATCHER",
  "chen-qianyu": "CHENQIANYU",
  "da-pan": "DAPAN",
  ember: "EMBER",
  endministrator: "ENDMINISTRATOR",
  estella: "ESTELLA",
  fluorite: "FLUORITE",
  gilberta: "GILBERTA",
  laevatain: "LAEVATAIN",
  "last-rite": "LASTRITE",
  lifeng: "LIFENG",
  mifu: "MIFU",
  perlica: "PERLICA",
  pogranichnik: "POGRANICHNK",
  rossi: "ROSSI",
  snowshine: "SNOWSHINE",
  tangtang: "TANGTANG",
  wulfgard: "WULFGARD",
  xaihi: "XAIHI",
  yvonne: "YVONNE",
  "zhuang-fangyi": "ZHUANGFANGYI",
};

const ENDAXIS_CHARACTER_ROSTER = (endaxisGameData as { characterRoster?: EndaxisPackedCharacter[] }).characterRoster ?? [];
const ENDAXIS_CHARACTER_BY_ID = new Map(
  ENDAXIS_CHARACTER_ROSTER.map((character) => [character.id.trim().toUpperCase(), character]),
);
const ENDAXIS_CHARACTER_BY_NAME = new Map(
  ENDAXIS_CHARACTER_ROSTER.map((character) => [character.name.trim(), character]),
);

function safeIdPart(value: string) {
  return value.replace(/[^a-zA-Z0-9_-]+/g, "_").replace(/^_+|_+$/g, "") || "item";
}

function clampLevel(value: number | null | undefined) {
  const level = Number(value);
  if (!Number.isFinite(level) || level <= 0) {
    return 90;
  }
  if (level >= 90) {
    return 90;
  }
  if (level >= 80) {
    return 80;
  }
  if (level >= 60) {
    return 60;
  }
  if (level >= 40) {
    return 40;
  }
  if (level >= 20) {
    return 20;
  }
  return 1;
}

function clampPotential(value: number | null | undefined) {
  const potential = Number(value);
  if (!Number.isFinite(potential)) {
    return 0;
  }
  return Math.max(0, Math.min(Math.round(potential), 5));
}

function clampSkillLevel(value: number | null | undefined, fallback = 9) {
  const level = Number(value);
  if (!Number.isFinite(level) || level <= 0) {
    return fallback;
  }
  return Math.max(1, Math.min(Math.round(level), 12));
}

function clampWeaponSkillLevel(value: number | null | undefined) {
  const level = Number(value);
  if (!Number.isFinite(level) || level <= 0) {
    return 1;
  }
  return Math.max(1, Math.min(Math.round(level), 9));
}

function resolveCharacterSlug(characterKey: string | null | undefined, characterName: string | null | undefined) {
  const key = characterKey?.trim().toLowerCase() ?? "";
  if (key && CHARACTER_SLUG_BY_KEY[key]) {
    return CHARACTER_SLUG_BY_KEY[key];
  }
  const name = characterName?.trim() ?? "";
  return CHARACTER_SLUG_BY_NAME[name] ?? (key || name || null);
}

function normalizeResourceId(value: string | null | undefined) {
  const trimmed = value?.trim();
  if (!trimmed) {
    return null;
  }
  const filename = trimmed.split(/[\\/]/).pop() ?? trimmed;
  return filename.replace(/\.[^.]+$/, "");
}

function getEquipSlotKey(equip: BattleDetailResponse["battle"]["roster"][number]["equips"][number]) {
  const text = [equip.itemId, equip.partName, equip.iconUrl].filter(Boolean).join(" ").toLowerCase();
  if (/(?:^|_)body(?:_|$)|armor|armour|护甲|胸甲|轻甲|重甲|衣/.test(text)) {
    return "armor";
  }
  if (/(?:^|_)hand(?:_|$)|glove|gauntlet|手/.test(text)) {
    return "gloves";
  }
  if (/(?:^|_)edc(?:_|$)|kit|accessory|aux|lamp|chip|仪|器|芯片|饰/.test(text)) {
    return "accessory";
  }
  return null;
}

function assignGearSlots(
  equips: BattleDetailResponse["battle"]["roster"][number]["equips"],
  track: EndaxisTrack,
  gearInstances: EndaxisGearInstance[],
  idPrefix: string,
) {
  const accessoryKeys: Array<"equipAccessory1Id" | "equipAccessory2Id"> = ["equipAccessory1Id", "equipAccessory2Id"];
  const accessoryInstanceKeys: Array<"equipAccessory1InstanceId" | "equipAccessory2InstanceId"> = [
    "equipAccessory1InstanceId",
    "equipAccessory2InstanceId",
  ];
  let nextAccessoryIndex = 0;
  const fallbackSlots: Array<["equipArmorId" | "equipGlovesId" | "equipAccessory1Id" | "equipAccessory2Id", keyof EndaxisTrack]> = [
    ["equipArmorId", "equipArmorInstanceId"],
    ["equipGlovesId", "equipGlovesInstanceId"],
    ["equipAccessory1Id", "equipAccessory1InstanceId"],
    ["equipAccessory2Id", "equipAccessory2InstanceId"],
  ];

  for (const equip of [...equips].sort((left, right) => left.slot - right.slot)) {
    const gearPieceId = normalizeResourceId(equip.itemId ?? equip.iconUrl ?? equip.pieceName);
    if (!gearPieceId) {
      continue;
    }

    const instance: EndaxisGearInstance = {
      id: `${idPrefix}_gear_${safeIdPart(gearPieceId)}_${gearInstances.length + 1}`,
      gearPieceId,
      artificingLevels: [],
    };
    gearInstances.push(instance);

    const slotKey = getEquipSlotKey(equip);
    if (slotKey === "armor" && !track.equipArmorId) {
      track.equipArmorId = gearPieceId;
      track.equipArmorInstanceId = instance.id;
      continue;
    }
    if (slotKey === "gloves" && !track.equipGlovesId) {
      track.equipGlovesId = gearPieceId;
      track.equipGlovesInstanceId = instance.id;
      continue;
    }
    if (slotKey === "accessory" && nextAccessoryIndex < accessoryKeys.length) {
      track[accessoryKeys[nextAccessoryIndex]] = gearPieceId;
      track[accessoryInstanceKeys[nextAccessoryIndex]] = instance.id;
      nextAccessoryIndex += 1;
      continue;
    }

    const fallback = fallbackSlots.find(([idKey]) => !track[idKey]);
    if (fallback) {
      const [idKey, instanceKey] = fallback;
      track[idKey] = gearPieceId;
      (track[instanceKey] as string | null) = instance.id;
      if (idKey === "equipAccessory1Id") {
        nextAccessoryIndex = Math.max(nextAccessoryIndex, 1);
      }
      if (idKey === "equipAccessory2Id") {
        nextAccessoryIndex = Math.max(nextAccessoryIndex, 2);
      }
    }
  }
}

function hasPoiseDamage(event: TimelineEvent) {
  return event.poiseDamage?.type === "PoiseDamage";
}

function isUltimateAttackShapeEvent(event: TimelineEvent) {
  const key = `${event.eventKey ?? ""} ${event.eventName ?? ""}`.toLowerCase();
  return ULTIMATE_ATTACK_SHAPE_RE.test(key);
}

function isBasicAttackShapeEvent(event: TimelineEvent) {
  const key = `${event.eventKey ?? ""}`.toLowerCase();
  return BASE_CHARACTER_ATTACK_RE.test(key) || ATTACK_SHAPE_RE.test(key);
}

function isPoiseHeavyBasicAttackEvent(event: TimelineEvent) {
  return hasPoiseDamage(event) && isBasicAttackShapeEvent(event) && !isUltimateAttackShapeEvent(event);
}

function hasExplicitActionStart(event: TimelineEvent) {
  return typeof event.actualStartMsFromStart === "number" && Number.isFinite(event.actualStartMsFromStart);
}

function looksLikeDelayedHitChild(event: TimelineEvent) {
  const key = event.eventKey ?? "";
  const name = event.eventName ?? "";
  return DELAYED_HIT_CHILD_RE.test(`${key} ${name}`);
}

function shouldImportSkillEvent(event: TimelineEvent) {
  if (event.laneType !== "skill") {
    return false;
  }
  const key = event.eventKey?.trim() ?? "";
  if (!key || PASSIVE_OR_BUFF_KEY_RE.test(key)) {
    return false;
  }
  if (!hasExplicitActionStart(event) && looksLikeDelayedHitChild(event)) {
    return false;
  }
  if (ACTIVE_SKILL_KEY_RE.test(key)) {
    return true;
  }
  if (isUltimateAttackShapeEvent(event)) {
    return true;
  }
  return ATTACK_SHAPE_RE.test(key) && hasPoiseDamage(event);
}

function normalizeActionDisplayName(name: string) {
  const segments = name
    .split("/")
    .map((segment) => segment.trim())
    .filter(Boolean);
  if (segments.length <= 1) {
    return name.trim();
  }
  const meaningfulSegments = segments.filter((segment, index) => index === 0 || !DISPLAY_NAME_SEGMENT_NOISE_RE.test(segment));
  return (meaningfulSegments[0] ?? segments[0] ?? name).trim();
}

function getTimelineSkillMergeKey(
  event: TimelineEvent,
  displayName: string,
  skillCategory: ReturnType<typeof getBattleSkillCategory>,
) {
  if (skillCategory === "ultimate") {
    return [
      event.sourceCharacterKey ?? event.sourceCharacterName ?? "",
      event.targetCharacterKey ?? event.targetCharacterName ?? "",
      skillCategory,
      displayName,
    ].join("::");
  }
  return event.eventGroupKey ?? `${event.eventKey ?? event.eventName}::${event.targetCharacterName ?? ""}`;
}

function canMergeSkillEvent(
  current: { lastHitMs: number } | undefined,
  event: TimelineEvent,
  skillCategory: ReturnType<typeof getBattleSkillCategory>,
) {
  if (!current) {
    return false;
  }
  const gapMs = event.tsMsFromStart - current.lastHitMs;
  if (skillCategory === "ultimate") {
    return gapMs <= ULTIMATE_HIT_GROUP_GAP_MS;
  }
  if (event.eventGroupKey !== undefined && event.eventGroupKey !== null) {
    return true;
  }
  return gapMs <= SKILL_HIT_GROUP_GAP_MS;
}

function getActionType(skillCategory: ReturnType<typeof getBattleSkillCategory>): EndaxisActionType {
  switch (skillCategory) {
    case "normal":
      return "basicAttack";
    case "combo":
      return "comboSkill";
    case "heavy":
      return "finisher";
    case "ultimate":
      return "ultimate";
    case "skill":
    case "other":
    default:
      return "battleSkill";
  }
}

function getEndaxisCharacterData(operatorSlug: string, characterName: string | null | undefined) {
  const byName = characterName ? ENDAXIS_CHARACTER_BY_NAME.get(characterName.trim()) : undefined;
  if (byName) {
    return byName;
  }
  const packedId = ENDAXIS_CHARACTER_ID_BY_SLUG[operatorSlug];
  return packedId ? ENDAXIS_CHARACTER_BY_ID.get(packedId) : undefined;
}

function getStandardActionName(actionType: EndaxisActionType) {
  switch (actionType) {
    case "battleSkill":
      return "战技";
    case "comboSkill":
      return "连携";
    case "ultimate":
      return "终结技";
    case "finisher":
      return "处决";
    default:
      return "普攻";
  }
}

function numberOrFallback(value: number | null | undefined, fallback: number) {
  const numeric = Number(value);
  return Number.isFinite(numeric) && numeric > 0 ? numeric : fallback;
}

function buildStandardHits(
  ticks: EndaxisPackedDamageTick[] | null | undefined,
  element: string,
) {
  return (ticks ?? [])
    .filter((tick) => Number.isFinite(Number(tick.offset)))
    .map((tick, index) => ({
      id: `hit_${index + 1}`,
      offset: Number(tick.offset) || 0,
      element,
      stagger: Number(tick.stagger) || 0,
      spRecovery: Number(tick.spRecovery ?? tick.sp) || 0,
      spReturn: Number(tick.spReturn) || 0,
      effects: tick.effects ?? tick.boundEffects ?? [],
    }));
}

function getFirstHitOffsetSeconds(action: { hits?: unknown[] }) {
  const offsets = (action.hits ?? [])
    .map((hit) => (hit && typeof hit === "object" && "offset" in hit ? Number((hit as { offset?: unknown }).offset) : NaN))
    .filter((offset) => Number.isFinite(offset) && offset > 0);
  return offsets.length > 0 ? Math.min(...offsets) : 0;
}

function getActionImportPriority(actionType: EndaxisActionType) {
  switch (actionType) {
    case "finisher":
      return 5;
    case "ultimate":
      return 4;
    case "comboSkill":
      return 3;
    case "battleSkill":
      return 2;
    case "basicAttack":
      return 1;
    default:
      return 0;
  }
}

function dedupeSameFrameActions(actions: EndaxisAction[]) {
  const actionByFrame = new Map<number, EndaxisAction>();

  for (const action of actions) {
    const frame = Math.round(action.startTime * 60);
    const current = actionByFrame.get(frame);
    if (!current) {
      actionByFrame.set(frame, action);
      continue;
    }

    const currentPriority = getActionImportPriority(current.type);
    const nextPriority = getActionImportPriority(action.type);
    if (
      nextPriority > currentPriority ||
      (nextPriority === currentPriority && Number(action.duration) > Number(current.duration))
    ) {
      actionByFrame.set(frame, action);
    }
  }

  return Array.from(actionByFrame.values()).sort((left, right) => left.startTime - right.startTime);
}

function getStandardActionTemplate(
  actionType: EndaxisActionType,
  operatorSlug: string,
  packedCharacter: EndaxisPackedCharacter | undefined,
  fallbackElement: string,
) {
  const element = ELEMENT_BY_DAMAGE_ELEMENT[(packedCharacter?.element ?? fallbackElement).toLowerCase()] ?? fallbackElement;
  const base = {
    id: `${operatorSlug}_${actionType}`,
    type: actionType,
    skillId: actionType,
    sourceSkillKey: actionType,
    name: getStandardActionName(actionType),
    librarySource: "character" as const,
    element,
    icon: "",
    duration: 1,
    cooldown: 0,
    spCost: 0,
    gaugeCost: 0,
    gaugeGain: 0,
    teamGaugeGain: 0,
    enhancementTime: 0,
    animationTime: 0,
    hits: [] as unknown[],
  };

  switch (actionType) {
    case "battleSkill":
      return {
        ...base,
        icon: `/operators/${operatorSlug}/battle.webp`,
        duration: numberOrFallback(packedCharacter?.skill_duration, 1),
        spCost: numberOrFallback(packedCharacter?.skill_spCost, 100),
        gaugeGain: Number(packedCharacter?.skill_gaugeGain) || 0,
        teamGaugeGain: Number(packedCharacter?.skill_teamGaugeGain ?? packedCharacter?.skill_gaugeGain) || 0,
        hits: buildStandardHits(packedCharacter?.skill_damage_ticks, element),
      };
    case "comboSkill":
      return {
        ...base,
        icon: `/operators/${operatorSlug}/combo.webp`,
        duration: numberOrFallback(packedCharacter?.link_duration, 1),
        cooldown: Number(packedCharacter?.link_cooldown) || 0,
        gaugeGain: Number(packedCharacter?.link_gaugeGain) || 0,
        hits: buildStandardHits(packedCharacter?.link_damage_ticks, element),
      };
    case "ultimate":
      return {
        ...base,
        icon: `/operators/${operatorSlug}/ultimate.webp`,
        duration: numberOrFallback(packedCharacter?.ultimate_duration, 1.5),
        gaugeCost: numberOrFallback(packedCharacter?.ultimate_gaugeMax, 100),
        gaugeGain: Number(packedCharacter?.ultimate_gaugeReply) || 0,
        enhancementTime: Number(packedCharacter?.ultimate_enhancementTime) || 0,
        animationTime: Number(packedCharacter?.ultimate_animationTime) || 0,
        hits: buildStandardHits(packedCharacter?.ultimate_damage_ticks, element),
      };
    case "finisher":
      return {
        ...base,
        duration: numberOrFallback(packedCharacter?.execution_duration, 1.5),
        hits: buildStandardHits(packedCharacter?.execution_damage_ticks, element),
      };
    default:
      return base;
  }
}

function getElement(event: TimelineEvent, fallback: string | null | undefined) {
  const raw = (event.damageElement ?? fallback ?? "physical").trim().toLowerCase();
  return ELEMENT_BY_DAMAGE_ELEMENT[raw] ?? raw;
}

function getActionTiming(event: TimelineEvent) {
  const startMsCandidates = [event.actualStartMsFromStart, event.tsMsFromStart].filter(
    (value): value is number => typeof value === "number" && Number.isFinite(value),
  );
  const startMs = Math.max(0, Math.min(...startMsCandidates));
  const endMsCandidates = [
    event.actualEndMsFromStart,
    typeof event.actualDurationMs === "number" ? startMs + event.actualDurationMs : null,
    typeof event.durationMs === "number" ? event.tsMsFromStart + event.durationMs : null,
    event.tsMsFromStart,
  ].filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  const endMs = Math.max(startMs, ...endMsCandidates);
  return { startMs, endMs };
}

function buildActionName(categoryLabel: string, preferredName: string) {
  const normalizedPreferred = preferredName.trim();
  if (!normalizedPreferred || normalizedPreferred === categoryLabel || normalizedPreferred === `${categoryLabel}技`) {
    return categoryLabel;
  }
  if (categoryLabel === "连携" && normalizedPreferred === "连携技") {
    return "连携";
  }
  return `${categoryLabel} · ${normalizedPreferred}`;
}

type CastClassification =
  | { kind: "skip" }
  | { kind: "action"; actionType: EndaxisActionType; segmentIndex?: number | "last" };

/** 施法意图（输入式）：交给 Endaxis 引擎自建动作，我们只给 type+段+时刻。 */
export type EndaxisCastIntent = {
  type: EndaxisActionType;
  segmentIndex?: number | "last";
  startTime: number;
  /** v34+ 普攻：该施放回技力（主控重击）；用于过滤非主控 AI 重击。 */
  recoversEnergy?: boolean;
};

export type EndaxisTrackCastInput = {
  trackIndex: number;
  intents: EndaxisCastIntent[];
};

// ⚠️ 全部端锚定（$）白名单：casts 里混着机制子实体的施法
// （combo_skill_water/combo_skill_water_gene 这类涡流实体挂 7~42 秒），
// 允许尾缀的宽松匹配会把它们误判成玩家动作（2026-07-05 汤汤"连携×3"事故）。
const CAST_ATTACK_SEGMENT_END_RE = /_attack_?(\d+)$/i;
const CAST_HEAVY_END_RE = /(?:power|heavy)_attack$/i;
const CAST_PLUNGING_START_RE = /_plunging_attack(?:_start)?$/i;
const CAST_PLUNGING_END_RE = /_plunging_attack_end$/i;
const CAST_EXECUTION_RE = /execut/i;
const CAST_ULT_ATTACK_END_RE = /_ult(?:imate)?_attack_?(\d+)?$/i;
const CAST_ULTIMATE_END_RE = /_ultimate_skill$/i;
const CAST_COMBO_END_RE = /_combo(?:_\d+)?_skill$/i;
const CAST_NORMAL_SKILL_END_RE = /_normal_skill$/i;
const CAST_NOISE_RE = /(?:^|_)(?:dodge|dash|sprint|idle|born|die|hitstop|switch)(?:$|_)/i;

/** 施法序列（casts）里的 skillKey 是原样分段（attack1~5/重击/战技/终结…）。
 * 只认可精确收尾的玩家动作 key，其余（机制/实体/未知变体）一律跳过。 */
function classifyCastSkillKey(skillKey: string): CastClassification {
  const key = skillKey.toLowerCase();
  if (CAST_NOISE_RE.test(key) || CAST_PLUNGING_END_RE.test(key)) {
    // plunging_attack_end 是 start/end 成对包的收尾包，不是第二个动作
    return { kind: "skip" };
  }
  if (CAST_EXECUTION_RE.test(key)) {
    return { kind: "action", actionType: "finisher" };
  }
  if (CAST_ULTIMATE_END_RE.test(key)) {
    return { kind: "action", actionType: "ultimate" };
  }
  if (CAST_COMBO_END_RE.test(key)) {
    return { kind: "action", actionType: "comboSkill" };
  }
  if (CAST_NORMAL_SKILL_END_RE.test(key)) {
    return { kind: "action", actionType: "battleSkill" };
  }
  // 终结技期间的强化普攻（laevat ult_attack1 等）：时间轴上按普攻段占位
  const ultAttackMatch = key.match(CAST_ULT_ATTACK_END_RE);
  if (ultAttackMatch) {
    return {
      kind: "action",
      actionType: "basicAttack",
      segmentIndex: ultAttackMatch[1] ? Number(ultAttackMatch[1]) : undefined,
    };
  }
  if (CAST_HEAVY_END_RE.test(key)) {
    // 重击 = 连段末段（'last' 可 JSON 序列化，Infinity 会变 null）
    return { kind: "action", actionType: "basicAttack", segmentIndex: "last" };
  }
  if (CAST_PLUNGING_START_RE.test(key)) {
    return { kind: "action", actionType: "basicAttack", segmentIndex: 1 };
  }
  const attackMatch = key.match(CAST_ATTACK_SEGMENT_END_RE);
  if (attackMatch) {
    return { kind: "action", actionType: "basicAttack", segmentIndex: Number(attackMatch[1]) };
  }
  return { kind: "skip" };
}

/** 输入式：casts → 施法意图（type+段+时刻）。动作本体交给 Endaxis 引擎构造，
 * 这里只做「哪个技能」的分类，不碰时长/CD/伤害/连段——那些是引擎的事。 */
function buildCastIntents(casts: BattleExportCast[]): EndaxisCastIntent[] {
  const intents: EndaxisCastIntent[] = [];
  for (const cast of casts) {
    const classification = classifyCastSkillKey(cast.skillKey);
    if (classification.kind === "skip") {
      continue;
    }
    intents.push({
      type: classification.actionType,
      segmentIndex: classification.segmentIndex,
      startTime: Number((Math.max(0, cast.tsMsFromStart) / 1000).toFixed(3)),
      recoversEnergy: Boolean(cast.recoversEnergy),
    });
  }
  return intents.sort((left, right) => left.startTime - right.startTime);
}

function buildTrackActions(
  detail: BattleDetailResponse,
  rosterEntry: BattleDetailResponse["battle"]["roster"][number],
  trackId: string,
  idPrefix: string,
  packedCharacter: EndaxisPackedCharacter | undefined,
) {
  type GroupedSkill = {
    event: TimelineEvent;
    name: string;
    categoryLabel: string;
    skillCategory: ReturnType<typeof getBattleSkillCategory>;
    actionType: EndaxisActionType;
    startMs: number;
    endMs: number;
    lastHitMs: number;
    totalValue: number;
    hitCount: number;
    element: string;
  };

  const events = detail.timelineEvents
    .filter((event) => {
      const sourceMatches =
        (rosterEntry.characterKey && event.sourceCharacterKey === rosterEntry.characterKey) ||
        event.sourceCharacterName === rosterEntry.characterName;
      return sourceMatches && shouldImportSkillEvent(event);
    })
    .sort((left, right) => left.tsMsFromStart - right.tsMsFromStart);

  const groups: GroupedSkill[] = [];
  const latestIndexByMergeKey = new Map<string, number>();

  for (const event of events) {
    const preferredName = normalizeActionDisplayName(getPreferredBattleSkillDisplayName(event.eventName, event.eventKey));
    const isPoiseHeavy = isPoiseHeavyBasicAttackEvent(event);
    const skillCategory = isPoiseHeavy ? "heavy" : getBattleSkillCategory(preferredName, event.eventKey);
    const categoryLabel = isPoiseHeavy ? "重击" : getBattleSkillCategoryLabel(preferredName, event.eventKey);
    const name = buildActionName(categoryLabel, preferredName);
    const mergeKey = getTimelineSkillMergeKey(event, name, skillCategory);
    const currentIndex = latestIndexByMergeKey.get(mergeKey);
    const current = currentIndex !== undefined ? groups[currentIndex] : undefined;
    const timing = getActionTiming(event);

    if (!current || !canMergeSkillEvent(current, event, skillCategory)) {
      const group: GroupedSkill = {
        event,
        name,
        categoryLabel,
        skillCategory,
        actionType: getActionType(skillCategory),
        startMs: timing.startMs,
        endMs: timing.endMs,
        lastHitMs: event.tsMsFromStart,
        totalValue: event.value ?? 0,
        hitCount: 1,
        element: getElement(event, rosterEntry.characterElement),
      };
      groups.push(group);
      latestIndexByMergeKey.set(mergeKey, groups.length - 1);
      continue;
    }

    current.endMs = Math.max(current.endMs, timing.endMs);
    current.lastHitMs = event.tsMsFromStart;
    current.totalValue += event.value ?? 0;
    current.hitCount += 1;
    if (current.element === "physical") {
      current.element = getElement(event, rosterEntry.characterElement);
    }
    latestIndexByMergeKey.set(mergeKey, currentIndex!);
  }

  const actions = groups
    .sort((left, right) => left.startMs - right.startMs)
    .map((group, index): EndaxisAction => {
      const template = getStandardActionTemplate(group.actionType, trackId, packedCharacter, group.element);
      const hasExplicitStart =
        typeof group.event.actualStartMsFromStart === "number" && Number.isFinite(group.event.actualStartMsFromStart);
      const inferredStartMs = hasExplicitStart
        ? group.startMs
        : Math.max(0, group.startMs - getFirstHitOffsetSeconds(template) * 1000);
      const startTime = Number((inferredStartMs / 1000).toFixed(3));
      const instanceId = `${idPrefix}_act_${safeIdPart(trackId)}_${index + 1}`;
      return {
        ...template,
        instanceId,
        logicalStartTime: startTime,
        startTime,
        notes: `${group.name}，${group.hitCount} hit，总伤 ${Math.round(group.totalValue).toLocaleString("zh-CN")}`,
      };
    });

  return dedupeSameFrameActions(actions);
}

function createOperatorInstance(
  rosterEntry: BattleDetailResponse["battle"]["roster"][number],
  operatorSlug: string,
  idPrefix: string,
) {
  const id = `${idPrefix}_op_${safeIdPart(operatorSlug)}`;
  const skillLevel = clampSkillLevel(null, 12);
  const talentStates: Record<string, number> = {};
  for (let index = 0; index < 3; index += 1) {
    talentStates[String(index)] = 0;
  }
  return {
    id,
    instance: {
      id,
      operatorSlug,
      level: clampLevel(rosterEntry.characterLevel),
      promoted: clampLevel(rosterEntry.characterLevel) >= 80,
      potential: clampPotential(rosterEntry.characterPotential),
      skillLevels: {
        basicAttack: skillLevel,
        battleSkill: skillLevel,
        comboSkill: skillLevel,
        ultimate: skillLevel,
      },
      talentStates,
      trustLevel: 4,
    } satisfies EndaxisOperatorInstance,
  };
}

function createWeaponInstance(
  rosterEntry: BattleDetailResponse["battle"]["roster"][number],
  idPrefix: string,
  exportRosterEntry?: BattleExportRosterEntry,
) {
  const weaponSlug = normalizeResourceId(rosterEntry.weapon?.weaponTemplate ?? rosterEntry.weapon?.iconUrl ?? null);
  if (!weaponSlug) {
    return null;
  }
  const id = `${idPrefix}_weapon_${safeIdPart(weaponSlug)}`;
  const skillLevel = clampWeaponSkillLevel(rosterEntry.weapon?.weaponRefine);
  // 2.10.55+ 上传：武器三词条各自等级（wpn_attr_*=词条1 / wpn_sp_attr_*=词条2 / sk_wpn_*=主词条），
  // 同一把武器三词条可不同级，单一 refine 表达不了；老 battle 缺省时退回统一 refine。
  let skill1Level = skillLevel;
  let skill2Level = skillLevel;
  let skill3Level = skillLevel;
  for (const wordSkill of exportRosterEntry?.weapon?.skills ?? []) {
    const key = (wordSkill.skillKey ?? "").toLowerCase();
    const level = clampWeaponSkillLevel(wordSkill.level);
    if (key.startsWith("sk_wpn_")) {
      skill3Level = level;
    } else if (key.startsWith("wpn_sp_attr_")) {
      skill2Level = level;
    } else if (key.startsWith("wpn_attr_")) {
      skill1Level = level;
    }
  }
  return {
    id,
    weaponSlug,
    instance: {
      id,
      weaponSlug,
      level: clampLevel(rosterEntry.weapon?.weaponLevel),
      tuned: clampLevel(rosterEntry.weapon?.weaponLevel) >= 80,
      potential: Math.max(0, Math.min(skill3Level - 1, 5)),
      skill1Level,
      skill2Level,
      skill3Level,
    } satisfies EndaxisWeaponInstance,
  };
}

function createEmptyTrack(): EndaxisTrack {
  return {
    id: null,
    operatorInstanceId: null,
    actions: [],
    initialGauge: 0,
    maxGaugeOverride: null,
    gaugeEfficiency: 100,
    originiumArtsPower: 0,
    weaponId: null,
    weaponInstanceId: null,
    weaponCommon1Tier: 1,
    weaponCommon2Tier: 1,
    weaponBuffTier: 1,
    weaponAppliedDeltas: {},
    equipmentAppliedDeltas: {},
    stats: {
      ult_charge_eff: 100,
      link_cd_reduction: 0,
      originium_arts_power: 0,
    },
    equipArmorId: null,
    equipGlovesId: null,
    equipAccessory1Id: null,
    equipAccessory2Id: null,
    equipArmorInstanceId: null,
    equipGlovesInstanceId: null,
    equipAccessory1InstanceId: null,
    equipAccessory2InstanceId: null,
    equipArmorRefineTier: 0,
    equipGlovesRefineTier: 0,
    equipAccessory1RefineTier: 0,
    equipAccessory2RefineTier: 0,
    linkCdReduction: 0,
    operatorStatus: null,
    enemyStatus: null,
    triggerEffects: [],
  };
}

function isEnemyKey(value: string | null | undefined) {
  return Boolean(value?.trim().startsWith("eny_"));
}

export function buildEndaxisImportPayload(
  detail: BattleDetailResponse,
  battleExport?: BattleExportData | null,
): EndaxisImportPayload {
  const idPrefix = `efl_${safeIdPart(detail.battle.id)}`;
  const battleTitle = formatBossDisplayName(detail.battle);
  const scenarioId = `${idPrefix}_scenario`;
  const operators: EndaxisOperatorInstance[] = [];
  const weapons: EndaxisWeaponInstance[] = [];
  const gears: EndaxisGearInstance[] = [];
  let actionCount = 0;
  let recognizedCharacterCount = 0;
  let usedCastSource = false;
  const castInputs: EndaxisTrackCastInput[] = [];
  const allCasts = battleExport?.casts ?? [];
  const hasEnergySignal = allCasts.some((cast) => cast.recoversEnergy === true);
  const exportRosterByKey = new Map(
    (battleExport?.roster ?? [])
      .filter((entry) => entry?.characterKey)
      .map((entry) => [String(entry.characterKey), entry]),
  );

  const tracks = detail.battle.roster.slice(0, 4).map((rosterEntry, index) => {
    const characterSlug = resolveCharacterSlug(rosterEntry.characterKey, rosterEntry.characterName);
    const operatorSlug = characterSlug ?? rosterEntry.characterKey ?? rosterEntry.characterName;
    const packedCharacter = getEndaxisCharacterData(operatorSlug, rosterEntry.characterName);
    const operator = createOperatorInstance(rosterEntry, operatorSlug, `${idPrefix}_${index + 1}`);
    const weapon = createWeaponInstance(
      rosterEntry,
      `${idPrefix}_${index + 1}`,
      exportRosterByKey.get(rosterEntry.characterKey ?? ""),
    );
    const track = createEmptyTrack();

    track.id = operatorSlug;
    track.operatorInstanceId = operator.id;
    const characterCasts = allCasts.filter((cast) => cast.characterKey === rosterEntry.characterKey);
    if (characterCasts.length > 0) {
      // v33+ battle：输出施法意图，动作由 Endaxis 引擎在浏览器端自建（输入式）。
      // 工程本身留空动作，避免与引擎构造的动作重复。
      track.actions = [];
      const intents = buildCastIntents(characterCasts);
      if (intents.length > 0) {
        castInputs.push({ trackIndex: index, intents });
        actionCount += intents.length;
        usedCastSource = true;
      }
    } else {
      // 老 battle 回退：无施法序列，按展示 timeline 的伤害聚类自建近似动作
      track.actions = buildTrackActions(detail, rosterEntry, operatorSlug, `${idPrefix}_${index + 1}`, packedCharacter);
      actionCount += track.actions.length;
    }
    operators.push(operator.instance);

    if (CHARACTER_SLUG_BY_KEY[(rosterEntry.characterKey ?? "").toLowerCase()] || CHARACTER_SLUG_BY_NAME[rosterEntry.characterName]) {
      recognizedCharacterCount += 1;
    }

    if (weapon) {
      track.weaponId = weapon.weaponSlug;
      track.weaponInstanceId = weapon.id;
      track.weaponCommon1Tier = weapon.instance.skill1Level;
      track.weaponCommon2Tier = weapon.instance.skill2Level;
      track.weaponBuffTier = weapon.instance.skill3Level;
      weapons.push(weapon.instance);
    }

    assignGearSlots(rosterEntry.equips, track, gears, `${idPrefix}_${index + 1}`);

    return track;
  });

  while (tracks.length < 4) {
    tracks.push(createEmptyTrack());
  }

  const battleBossKey = detail.battle.bossKey?.trim();
  const battleBossName = detail.battle.bossName.trim();
  const activeEnemyId =
    battleBossKey && isEnemyKey(battleBossKey)
      ? battleBossKey
      : isEnemyKey(battleBossName)
        ? battleBossName
        : "custom";
  const contingencyContractTags =
    detail.battle.contractTags
      ?.map((tag) => Number(tag.tagId))
      .filter((tagId) => Number.isFinite(tagId)) ?? [];

  const scenarioData = {
    tracks,
    connections: [],
    operators,
    weapons,
    gears,
    characterOverrides: {},
    weaponOverrides: {},
    equipmentCategoryOverrides: {},
    prepDuration: 5,
    prepExpanded: true,
    systemConstants: {},
    activeEnemyId,
    activeEnemyLevel: 90,
    customEnemyParams: {},
    cycleBoundaries: [],
    switchEvents: [],
    inheritedInitialEffects: [],
    inheritedInitialEnemyState: null,
    contingencyContractTags,
  };

  const project: EndaxisProject = {
    timestamp: Date.now(),
    version: "1.0.0",
    scenarioList: [
      {
        id: scenarioId,
        name: `${battleTitle} · ${detail.battle.id}`,
        data: scenarioData,
      },
    ],
    activeScenarioId: scenarioId,
    systemConstants: {},
    activeEnemyId,
    activeEnemyLevel: 90,
  };

  return {
    storageKey: ENDAXIS_STORAGE_KEY,
    project,
    castInputKey: ENDAXIS_CAST_INPUT_KEY,
    castInputs,
    hasEnergySignal,
    summary: {
      battleId: detail.battle.id,
      battleTitle,
      rosterCount: detail.battle.roster.length,
      actionCount,
      recognizedCharacterCount,
      sourceKind: usedCastSource ? "casts" : "timeline",
    },
  };
}

/** 只从导出数据构建（editor 专用）。导出门禁 = valid+public（不要求上榜），
 * 比 detail 端点的排名门禁宽，玩家自己的非最佳战斗也能开模拟器。导出 roster
 * 是 detail roster 的超集（多 skills/enhanceLevels/stats），字段兼容；缺的
 * characterElement 由 Endaxis 干员数据兜底、contractTags 置空。 */
export function buildEndaxisImportPayloadFromExport(battleExport: BattleExportData): EndaxisImportPayload {
  const syntheticDetail = {
    battle: {
      id: String(battleExport.battleId ?? ""),
      bossKey: battleExport.dungeon?.bossKey ?? "",
      bossName: battleExport.dungeon?.bossName ?? "",
      contractTags: [],
      roster: battleExport.roster ?? [],
    },
    timelineEvents: [],
  } as unknown as BattleDetailResponse;
  return buildEndaxisImportPayload(syntheticDetail, battleExport);
}
