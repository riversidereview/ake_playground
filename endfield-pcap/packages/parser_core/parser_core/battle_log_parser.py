from __future__ import annotations

import bisect
import copy
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta
from functools import lru_cache
from math import isclose, log
from pathlib import Path
from typing import Any

from parser_core.integrity import build_canonical_sha256

PARSER_VERSION = "raw-log-parser-v43"
RULES_VERSION = "raw-log-parser-v37"
UNKNOWN_DUNGEON_KEY = "unknown_dungeon"
UNKNOWN_DUNGEON_NAME = "未知副本"
UNKNOWN_ENEMY_KEY = "eny_0000_unknown"

_TIMESTAMP_RE = re.compile(r"^\[(\d{2}):(\d{2}):(\d{2})\.(\d{3})\]\s+")
_GAME_TIMER_START_RE = re.compile(r"\bGAME_TIMER_START\b")
_GAME_TIMER_END_RE = re.compile(r"\bGAME_TIMER_END\b")
_OFFICIAL_TIMER_START_RE = re.compile(r"\bOFFICIAL_TIMER_START\b")
_OFFICIAL_TIMER_END_RE = re.compile(r"\bOFFICIAL_TIMER_END\b")
_LIVE_TIMER_TICK_RE = re.compile(r"\bLIVE_TIMER_TICK\b")
_KV_RE = re.compile(r'(\w+)=(".*?"|\S+)')
_CHAR_KEY_RE = re.compile(r"(chr_\d{4}_[a-z0-9]+)")
_SQUAD_MEMBER_RE = re.compile(r"(chr_\d{4}_[a-z0-9]+)_(\d+)")
_ENEMY_KEY_RE = re.compile(r"(eny_\d{4}_[a-z0-9]+)")
_FULL_ENEMY_KEY_RE = re.compile(r"^(eny_\d{4}_[a-z0-9]+(?:(?:_hard)|(?:_hdg\d*)|(?:_assult))?(?:_assult)?)$")
_HIT_SEQ_RE = re.compile(r"\bHP_V2\s+#(\d+)\b")
_POISE_RE = re.compile(r"\bPOISE_V1\b")
_SHORT_ID_RE = re.compile(r"^id_(\d+)$")
_RUNTIME_SKILL_ID_RE = re.compile(r"^(?:skill_)?(\d+)$")
_COMPOSITE_RUNTIME_SKILL_RE = re.compile(r"^(chr_\d{4}_[a-z0-9]+)_skill_(\d+)$")
_ENDMIN_VARIANTS = {"chr_0002_endminm", "chr_0003_endminf"}
_STATIC_TRIGGER_DAMAGE_BUFF_RE = re.compile(r"^buff_[a-z0-9_]+(?:triggered|damage)[a-z0-9_]*$", re.IGNORECASE)
_DPD_RAW_RE = re.compile(
    r'DPD_RAW\s+#(?P<seq>\d+).*?\bcalc=(?P<calc>[-\d.eE+]+)\s+'
    r'atkScale=(?P<atk_scale>[-\d.eE+]+)\s+blocked=(?P<blocked>\d+)\s+'
    r'damageType=(?P<damage_type>0x[0-9A-Fa-f]+|\S+)\s+'
    r'decorateMask=(?P<decorate_mask>0x[0-9A-Fa-f]+|\S+)\s+'
    r'collider="(?P<collider>[^"]*)"\s+'
    r'atkZones=\[(?P<atk_zones>[^\]]*)\]\s+defZones=\[(?P<def_zones>[^\]]*)\]'
)
_BASELINE_RE = re.compile(r"\bBASELINE\s+#(?P<seq>\d+)\s+(?P<body>.*)")
_PKT_MOD_RE = re.compile(r"\bPKT_MOD\s+#(?P<seq>\d+)\s+atk=\[(?P<atk>[^\]]*)\]\s+def=\[(?P<def>[^\]]*)\]")
_PKT_ATTR_RE = re.compile(r"\bPKT_ATTR\s+#(?P<seq>\d+)\s+atk=\[(?P<atk>[^\]]*)\]\s+def=\[(?P<def>[^\]]*)\]")
_BASELINE_KV_RE = re.compile(r"(-?\d+)=([-\d.eE+]+)")
_LOADOUT_SLOT_RE = re.compile(
    r"\bLOADOUT\s+slot=(?P<slot>\d+)\s+char=(?P<char>\S+).*?"
    r"weaponTemplate=(?P<weapon>\S+).*?"
    r"equipSuit=(?P<equip_suit>\{.*\})"
)
_LOADOUT_FIELD_RE_TEMPLATE = r"\b{key}=([^\s]+)"

_BUFF_LABEL_PRIORITY = {
    "攻击提升": 0,
    "增伤": 1,
    "增幅": 2,
    "导电": 2,
    "腐蚀": 2,
    "燃烧": 2,
    "冻结": 2,
    "碎冰": 2,
    "法术爆发": 2,
    "破防": 2,
    "倒地": 2,
    "击飞": 2,
    "猛击": 2,
    "脆弱": 2,
    "物理脆弱": 2,
    "物理脆弱 / 碎甲": 2,
    "碎甲": 2,
    "易伤": 3,
    "承伤易伤": 3,
    "减抗": 4,
    "连击增伤": 5,
    "暴击": 6,
    "暴击伤害": 7,
}
_BUFF_NOISE_PREFIXES = (
    "buff_common_vfx_",
    "buff_common_normal_skill_fx_",
    "buff_common_combo_attack_fx",
    "buff_common_dash",
    "buff_common_dash_",
    "buff_common_full_immune_weak",
)
_BUFF_NOISE_IDS = {
    "buff_chr_0011_seraph_mainchr_heal",
    "buff_chr_0023_antal_ultimate_icon",
    "buff_chr_0023_antal_ultimate_icon_2",
    "buff_common_obtain_ultimate_sp",
    "buff_common_dash_behit_listener",
    "buff_common_poise_break_damage_taken_scale",
}
_BUFF_NOISE_BB_KEYS = {
    "atb",
    "atk_duration",
    "cd",
    "comboskill_cooldown",
    "common_character_perfect_dodge",
    "count",
    "damage_interval",
    "def_decrease_tick",
    "def_decrease_tick_final",
    "duration",
    "dodgeSkillId",
    "end_early",
    "heal_value",
    "healvalue",
    "hit_spellduration",
    "hp_up",
    "imbue_scale",
    "infliction_num",
    "max_stack",
    "max_def_decrease",
    "max_def_decrease_final",
    "phy_spell_up",
    "poise",
    "posie",
    "potential_1",
    "potential_3",
    "potential_3_atb",
    "rate_add",
    "shatter_dmg",
    "skill_bg_type",
    "speed",
    "stack_cond",
    "start_def_decrease",
    "time_warning",
    "usp_everyone",
    "usp_self",
    "vfx_buff_name",
}
_BUFF_EFFECT_BB_KEY_IGNORE_BY_ID = {
    # Seraph's ultimate uses atk_up as an internal base for elemental EnhancedAction.
    # The actual buffs are emitted separately as common_affixes_enhance_* children.
    "buff_chr_0011_seraph_atk_buff": {"atk_up"},
    # Seraph's heal-side potential wrapper passes atk_up into a child action. The
    # actual attack buff is emitted separately by the weapon buff.
    "buff_chr_0011_seraph_potential_1_atkup": {"atk_up"},
    # suit_atk02 stores child trigger parameters on the persistent wearer buff.
    # Only atk_up is a direct stat effect here; dmg_up belongs to the later
    # add-combo-damage child.
    "buff_equipsuit_atk_02": {"dmg_up", "max_stack"},
    # Fracture carries trigger damage parameters next to the actual debuff.
    # The rDPS effect is physical_res_down; atk_scale belongs to the triggered hit.
    "buff_physical_do_fracture": {"atk_scale"},
    # Mixed weapon buffs carry owner-side parameters next to external rDPS keys.
    "buff_wpn_funnel_0006_valid": {"atk_up"},
    "buff_wpn_funnel_0011_valid": {"nature_dmg_up"},
    "buff_wpn_sword_0012_atk_up": {"atk_up"},
    "buff_wpn_sword_0013_atk_up": {"atk_up", "atk_up_add", "atk_up_mult"},
    "buff_wpn_sword_0016_team": {"phy_dmg_up", "phy_dmg_up2"},
    "buff_wpn_sword_0016_valid": {"phy_dmg_up", "phy_dmg_up2"},
    "buff_wpn_sword_0020_cryst": {"atk_up"},
}
_ATTR_TYPE_BUFF_LABELS = {
    2: "攻击提升",
    9: "暴击",
    10: "暴击伤害",
    17: "增伤",
    28: "增伤",
    32: "增伤",
    33: "增伤",
    50: "增伤",
    51: "增伤",
    53: "增伤",
    65: "增幅",
    66: "增幅",
    67: "增幅",
    68: "增幅",
    70: "易伤",
}
_FRAGILE_ATTR_TYPES = set(range(70, 86))
_BUFF_MERGE_GAP_MS = 250
_BUFF_MIRROR_DEDUPE_WINDOW_MS = 500
_TIMELINE_SKILL_GROUP_GAP_MS = 1200
_TIMELINE_ULTIMATE_GROUP_GAP_MS = 5000
_ZONE_BY_LABEL = {
    "攻击提升": "atk",
    "增伤": "dmg_inc",
    "增幅": "amp",
    "脆弱": "fragile",
    "物理脆弱": "fragile",
    "物理脆弱 / 碎甲": "vuln_taken",
    "碎甲": "vuln_taken",
    "易伤": "vuln_taken",
    "承伤易伤": "vuln_taken",
    "减抗": "res",
    "连击增伤": "combo",
    "源石技艺强度": "arts_strength",
    "加速": "speedup",
    "缓速": "slow",
}
_EFFECT_ZONE_LABELS = {
    "atk": "攻击提升",
    "dmg_inc": "增伤",
    "amp": "增幅",
    "fragile": "脆弱",
    "vuln_taken": "易伤",
    "res": "减抗",
    "combo": "连击增伤",
    "arts_strength": "源石技艺强度",
    "crit": "暴击",
    "speedup": "加速",
    "slow": "缓速",
}
_RDPS_DEBUG_ZONE_LABELS = {
    "atk": "攻击",
    "dmg_inc": "增伤",
    "fragile": "脆弱",
    "vuln_taken": "易伤",
    "amp": "增幅",
    "res": "减抗",
    "combo": "连击",
    "crit": "暴击",
    "arts_strength": "源石技艺强度",
}
_RDPS_DEBUG_ZONE_ORDER = {
    "atk": 0,
    "dmg_inc": 1,
    "fragile": 2,
    "vuln_taken": 3,
    "amp": 4,
    "res": 5,
    "combo": 6,
    "crit": 7,
    "arts_strength": 8,
}
_RDPS_ALLOCATABLE_ZONES = {"atk", "dmg_inc", "amp", "fragile", "vuln_taken", "res", "combo", "arts_strength"}
_DPD_ZONE_BUCKETS = {
    "dmg_inc": ("atk", 1),
    "amp": ("atk", 3),
    "combo": ("atk", 4),
    "vuln_taken": ("def", 1),
    "fragile": ("def", 5),
}
_ELEMENTAL_ELEMENTS = {"fire", "pulse", "cryst", "natural"}
_ARTS_STRENGTH_EFFECT_BUFF_IDS = {
    "buff_physical_do_fracture",
    "buff_common_pulse_pulse_conduct_triggered_do",
    "buff_common_pulse_cryst_triggered",
    "buff_common_natural_cryst_triggered",
    "buff_common_natural_pulse_triggered",
}
_ARTS_STRENGTH_PHYSICAL_ANOMALY_DAMAGE_IDS = {
    "buff_physical_airborne",
    "buff_physical_crushed",
    "buff_physical_knockdown",
    "buff_physical_do_fracture",
}
_ARTS_STRENGTH_BB_KEYS = {
    "phy_spell_up",
    "physpell_up",
    "physpell",
    "physicalandspellinflictionenhance",
}
_ACTION_DAMAGE_TYPE_TO_ELEMENT = {
    "physical": "physical",
    "fire": "fire",
    "pulse": "pulse",
    "cryst": "cryst",
    "crystal": "cryst",
    "natural": "natural",
}
_CHAR_TYPE_TO_ELEMENT = {
    "物理": "physical",
    "灼热": "fire",
    "寒冷": "cryst",
    "电磁": "pulse",
    "自然": "natural",
}
_ENHANCED_ACTION_SUBTYPE_TO_ELEMENT = {
    "crystal": "cryst",
    "cryst": "cryst",
    "natural": "natural",
    "fire": "fire",
    "pulse": "pulse",
    "physical": "physical",
    "spell": "spell",
    "all": "all",
}
_ATTR_TYPE_TO_LABEL = {
    39: "力量",
    40: "敏捷",
    41: "智识",
    42: "意志",
}
_ATTR_LABEL_TO_TYPE = {value: key for key, value in _ATTR_TYPE_TO_LABEL.items()}
_DAMAGE_SCHOOL_BY_SPEC = {
    "CharacterNormalAttack": "physical",
    "CharacterPlungingAttack": "physical",
    "CharacterPowerAttack": "physical",
    "CharacterDashAttack": "physical",
    "CharacterNormalSkill": "spell",
    "CharacterUltimateSkill": "spell",
    "CharacterComboSkill": "spell",
}
_RATE_IGNORE_BUFF_PATTERNS = (
    re.compile(r"^buff_equipsuit_(?:usp_02|combo_cd01)$", re.IGNORECASE),
    re.compile(r"buff_common_affixes_slow", re.IGNORECASE),
    re.compile(r"^buff_chr_0023_antal_(?:normal_skill|tageffect|utimate_skill)$", re.IGNORECASE),
    re.compile(r"^buff_common_affixes_shelter_default_child$", re.IGNORECASE),
    re.compile(r"buff_common_affixes_vulnerable_spell", re.IGNORECASE),
    re.compile(
        r"^buff_common_(?:physical|fire|pulse|cryst|natural|spell)_"
        r"(?:physical|fire|pulse|cryst|natural|spell)_corrupt_triggered$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^buff_common_(?:try_)?(?:physical|fire|pulse|cryst|natural|spell)_triggered(?:_wrapper)?$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^buff_common_try_(?:physical|fire|pulse|cryst|natural|spell)"
        r"_(?:physical|fire|pulse|cryst|natural|spell)_triggered$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^buff_common_(?:physical|fire|pulse|cryst|natural|spell)"
        r"_(?:physical|fire|pulse|cryst|natural|spell)_triggered_wrapper$",
        re.IGNORECASE,
    ),
)
_BB_KEY_ELEMENT_RE = re.compile(r"(fire|pulse|crystal|cryst|natural|physical|physic|spell)")
_ATTR_TYPE_TO_EFFECT = {
    2: ("atk", "all"),
    9: ("crit", "all"),
    10: ("crit", "all"),
    17: ("dmg_inc", "all"),
    28: ("dmg_inc", "all"),
    32: ("dmg_inc", "spell"),
    33: ("dmg_inc", "spell"),
    50: ("dmg_inc", "physical"),
    51: ("dmg_inc", "fire"),
    # 52/54 依据 AttributeMetaTable 官方语义补齐（icon_pulse/natural_damage_increase），
    # 此前缺失导致电磁/自然系角色的属性快照增伤丢失。
    52: ("dmg_inc", "pulse"),
    53: ("dmg_inc", "cryst"),
    54: ("dmg_inc", "natural"),
    65: ("amp", "fire"),
    66: ("amp", "pulse"),
    67: ("amp", "cryst"),
    68: ("amp", "natural"),
    70: ("fragile", "physical"),
    71: ("fragile", "fire"),
    72: ("fragile", "pulse"),
    73: ("fragile", "cryst"),
    74: ("fragile", "natural"),
    80: ("fragile", "physical"),
    81: ("fragile", "natural"),
    82: ("fragile", "cryst"),
    83: ("fragile", "pulse"),
    84: ("fragile", "fire"),
    85: ("fragile", "spell"),
}
_DEF_DECREASE_ATTR_TYPE_TO_EFFECT = {
    80: ("res", "physical"),
    81: ("res", "natural"),
    82: ("res", "cryst"),
    83: ("res", "pulse"),
    84: ("res", "fire"),
    85: ("res", "spell"),
}
_DAMAGE_TAG_TO_ELEMENT = {
    "pd": "physical",
    "fire": "fire",
    "cryst": "cryst",
    "pulse": "pulse",
    "natur": "natural",
    "natural": "natural",
}
_DPD_DAMAGE_TYPE_TO_ELEMENT = {
    0: "physical",
    2: "fire",
    3: "pulse",
    4: "cryst",
    6: "natural",
}
_ELEMENT_LABELS = {
    "physical": "物理",
    "fire": "灼热",
    "pulse": "电磁",
    "cryst": "寒冷",
    "natural": "自然",
    "spell": "法术",
}
_BUFF_SKILL_FILTER = {
    "buff_wpn_sword_0006_valid": re.compile(r"normal_skill|ult_attack"),
    "buff_equipsuit_combo_cd01_spellup": re.compile(r"normal_skill|combo|ultimate"),
}
_BUFF_EFFECT_SKILL_FILTER = {
    ("576", "dmg_inc"): re.compile(r"normal_skill"),
    ("buff_equipsuit_attrisuit_01", "dmg_inc"): re.compile(r"normal_skill.*_1"),
    ("buff_equipsuit_attrisuitup_01", "dmg_inc"): re.compile(r"normal_skill.*_1"),
    # suit_atk02: the persistent atk_up remains on the wearer; the child
    # dmg_up is consumed by the wearer's next combo skill.
    ("buff_equipsuit_atk_02_addcombodamage", "dmg_inc"): re.compile(r"combo"),
    ("buff_equipsuit_atk_02_addcombodamage_buff", "dmg_inc"): re.compile(r"combo"),
}
_ATTR_TYPE_SKILL_FILTER = {
    28: re.compile(r"ultimate"),
    32: re.compile(r"normal_skill"),
    33: re.compile(r"combo"),
}
_SINGLETON_REFRESH_EVENT_PATTERNS = (
    re.compile(r"^buff_equipsuit_", re.IGNORECASE),
    re.compile(r"^buff_chr_\d{4}_[a-z0-9]+_potential_\d+(?:_|$)", re.IGNORECASE),
)
_STACKABLE_EVENT_NAME_RE = re.compile(r"(?:^|_)(?:layer|stack)(?:_|$)", re.IGNORECASE)
_WEAPON_BUFF_RE = re.compile(r"^buff_wpn_[a-z]+_\d+_")
_WEAPON_ID_FROM_BUFF_RE = re.compile(r"^buff_(wpn_[a-z]+_\d+)_")
_FOOD_POTION_BUFF_RE = re.compile(r"^buff_common_.*_potion(?:_\d+)?$", re.IGNORECASE)
_GENERIC_BUFF_PREFIXES = (
    "buff_common_affixes_enhance_",
    "buff_common_affixes_vulnerable_",
    "buff_common_pulse_",
    "buff_common_fire_",
    "buff_common_cryst_",
    "buff_common_natural_",
)
_PLAYER_TARGET_GENERIC_BUFF_PREFIXES = (
    "buff_common_affixes_enhance_",
)
_CHR_BORROW_WINDOW_MS = 1000
_DEF_DECREASE_BASE_KEYS = {"def_decrease", "additional_def_decrease"}
_DEF_DECREASE_TICKS_PER_SEC = 3.5


def _attr_type_applies_to_skill(attr_type: int | None, skill_key: str | None) -> bool:
    if attr_type is None:
        return True
    skill_filter = _ATTR_TYPE_SKILL_FILTER.get(attr_type)
    if skill_filter is None:
        return True
    return bool(skill_filter.search(str(skill_key or "")))
_HIDDEN_COMBO_RULES = (
    {
        "rule_key": "karin_hidden_combo",
        "buff_patterns": (
            re.compile(r"buff_chr_0019_karin_talent_2_combo", re.IGNORECASE),
            re.compile(r"buff_chr_0019_karin_potential_5_combo", re.IGNORECASE),
        ),
        "skill_group_rates": {
            1: 0.30,
            2: 0.20,
        },
        "cast_window_ms": 5000,
    },
)
_GENERIC_COMBO_TRIGGER_BUFF_ID = "buff_common_affixes_combo_trigger"
_GENERIC_COMBO_IMBUE_BUFF_IDS = {
    "buff_common_affixes_skillimbue",
    "buff_common_affixes_skillimbue_atk",
}
_COMBO_TOTAL_RATES_BY_GROUP_TYPE = {
    1: (0.30, 0.45, 0.60, 0.75),
    2: (0.20, 0.30, 0.40, 0.50),
}
_COMBO_TRIGGER_GROUP_WINDOW_MS = 20
_COMBO_CONSUME_MAX_WINDOW_MS = 5000
_COMBO_CONSUME_SKILL_ALIASES: dict[str, dict[str, Any]] = {
    "sk_wpn_lance_0010": {
        "family_skill_key": "chr_0015_lifeng_ultimate_skill",
        "group_type": 2,
    },
}
_DUNGEON_CONTEXT_ALIASES: dict[str, tuple[str, str]] = {
    "indie_contract001": ("indie_group_ccdg", "危机合约"),
    "indie_group_ccdg": ("indie_group_ccdg", "危机合约"),
    "indie_ccdg001": ("indie_group_ccdg", "危机合约"),
    "indie_hard016": ("indie_hard016", "仪式旋流"),
    "indie_hard016_s": ("indie_hard016_s", "仪式旋流·苦难"),
    "indie_hard017": ("indie_hard017", "死寂表象"),
    "indie_hard017_s": ("indie_hard017_s", "死寂表象·苦难"),
    "indie_hard018": ("indie_hard018", "忿鼓咆声"),
    "indie_hard018_s": ("indie_hard018_s", "忿鼓咆声·苦难"),
    "indie_hard019": ("indie_hard019", "刺痛盾阵"),
    "indie_hard019_s": ("indie_hard019_s", "刺痛盾阵·苦难"),
    "indie_hard020": ("indie_hard020", "溶解窥看"),
    "indie_hard020_s": ("indie_hard020_s", "溶解窥看·苦难"),
    "indie_hard021": ("indie_hard021", "冯河断水"),
    "indie_hard021_s": ("indie_hard021_s", "冯河断水·苦难"),
}
_DUNGEON_ENEMY_HINT_ALIASES: dict[str, str] = {
    "indie_hard011_s": "eny_0090_wgabyss",
    "indie_hard016": "eny_0046_lbshamman",
    "indie_hard016_s": "eny_0046_lbshamman",
    "indie_hard017": "eny_0095_ethillu",
    "indie_hard017_s": "eny_0095_ethillu",
    "indie_hard018": "eny_0082_hsbear",
    "indie_hard018_s": "eny_0082_hsbear",
    "indie_hard019": "eny_0088_wgthorns",
    "indie_hard019_s": "eny_0088_wgthorns",
    "indie_hard020": "eny_0107_wgshoal2",
    "indie_hard020_s": "eny_0107_wgshoal2",
    "indie_hard021": "eny_0102_hstiger2",
    "indie_hard021_s": "eny_0102_hstiger2",
    "dung01_bossrush01_01": "eny_0051_rodin",
    "dung01_bossrush01_02": "eny_0051_rodin",
    "dung01_bossrush01_03": "eny_0051_rodin",
    "dung01_bossrush01_04": "eny_0051_rodin",
    "dung01_bossrush03_01": "eny_0052_palesent",
    "dung01_bossrush03_02": "eny_0052_palesent",
    "dung01_bossrush03_03": "eny_0052_palesent",
    "dung02_bossrush02_01": "eny_0079_nefarp2",
    "dung02_bossrush02_02": "eny_0079_nefarp2",
    "dung02_bossrush02_03": "eny_0079_nefarp2",
}
_VISUAL_HIT_GROUP_WINDOW_MS = 120


def _timer_is_authoritative(fields: dict[str, Any]) -> bool:
    if _coerce_int(fields.get("fallback"), default=0) != 0:
        return False
    if str(fields.get("source") or "").endswith("Fallback"):
        return False
    if "official" in fields:
        return _coerce_int(fields.get("official"), default=1) != 0
    return str(fields.get("source") or "") != "BattleOpModifyBattleState"


def _is_generic_runtime_skill_id(skill_key: str | None) -> bool:
    return bool(re.fullmatch(r"skill_\d+", str(skill_key or "")))


@lru_cache(maxsize=1)
def _load_classifier_hints() -> dict[str, Any]:
    candidates = [
        _repo_root() / "data" / "local_semantics" / "classifier_hints.json",
    ]
    for path in candidates:
        try:
            if not path.is_file():
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            return data
    return {}


def _buff_classifier_hint(buff_id: str) -> dict[str, Any] | None:
    hints = _load_classifier_hints().get("buffHints")
    if not isinstance(hints, dict):
        return None
    hint = hints.get(buff_id)
    return hint if isinstance(hint, dict) else None


def _positive_int(value: Any) -> int | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    rounded = round(number)
    if abs(number - rounded) > 0.0001:
        return None
    return int(rounded)


def _iter_json_entries(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    entries = payload.get("entries") if isinstance(payload, dict) else payload
    if not isinstance(entries, list):
        return []
    return [entry for entry in entries if isinstance(entry, dict)]


@lru_cache(maxsize=1)
def _load_nonstacking_weapon_ids() -> set[str]:
    roots = [
        _repo_root() / "data" / "akedata" / "weapon" / "items",
    ]
    markers = ("无法叠加", "不能叠加", "不可叠加")
    weapon_ids: set[str] = set()
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            weapon_id = str(payload.get("weaponId") or path.stem)
            text_parts: list[str] = []
            for skill in payload.get("skilllist") or []:
                if isinstance(skill, dict):
                    text_parts.append(str(skill.get("description") or ""))
            text_parts.append(str(payload.get("description") or ""))
            if any(marker in "\n".join(text_parts) for marker in markers):
                weapon_ids.add(weapon_id)
        if weapon_ids:
            break
    return weapon_ids


def _is_nonstacking_refresh_event(event_key: str | None) -> bool:
    event_key = str(event_key or "")
    if _is_food_potion_buff(event_key):
        return True
    match = _WEAPON_ID_FROM_BUFF_RE.match(event_key)
    if match and match.group(1) in _load_nonstacking_weapon_ids():
        return True
    if _STACKABLE_EVENT_NAME_RE.search(event_key):
        return False
    return any(pattern.search(event_key) for pattern in _SINGLETON_REFRESH_EVENT_PATTERNS)


def _is_food_potion_buff(event_key: str | None) -> bool:
    return bool(_FOOD_POTION_BUFF_RE.match(str(event_key or "")))


def _blackboard_max_stack_from_weapon_skill(skill: dict[str, Any]) -> int | None:
    description = str(skill.get("description") or "")
    if "叠加" not in description and "max_stack" not in description:
        return None
    for item in skill.get("blackboard") or []:
        if not isinstance(item, dict) or item.get("key") != "max_stack":
            continue
        raw_value = item.get("value")
        values = raw_value if isinstance(raw_value, list) else [raw_value]
        stack_values = [value for value in (_positive_int(value) for value in values) if value is not None]
        if stack_values:
            return min(stack_values)
    return None


@lru_cache(maxsize=1)
def _load_weapon_id_stack_limits() -> dict[str, int]:
    roots = [
        _repo_root() / "data" / "akedata" / "weapon" / "items",
    ]
    limits: dict[str, int] = {}
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            weapon_id = str(payload.get("weaponId") or path.stem)
            for skill in payload.get("skilllist") or []:
                if not isinstance(skill, dict):
                    continue
                max_stack = _blackboard_max_stack_from_weapon_skill(skill)
                if max_stack is not None:
                    limits[weapon_id] = max_stack
                    break
        if limits:
            break
    return limits


@lru_cache(maxsize=1)
def _load_weapon_buff_stack_limits() -> dict[str, int]:
    paths = [
        _repo_root() / "data" / "local_static" / "skill" / "manifest.json",
    ]
    limits: dict[str, int] = {}
    for path in paths:
        if not path.is_file():
            continue
        for entry in _iter_json_entries(path):
            skill_id = str(entry.get("id") or "")
            if not skill_id.startswith("sk_wpn_"):
                continue
            binary_probe = entry.get("binaryProbe")
            if not isinstance(binary_probe, dict):
                continue
            max_stack = None
            for hint in binary_probe.get("blackboardDoubleHints") or []:
                if not isinstance(hint, dict) or hint.get("key") != "max_stack":
                    continue
                max_stack = _positive_int(hint.get("value"))
                if max_stack is not None:
                    break
            if max_stack is None:
                continue
            created_buff_ids = binary_probe.get("highConfidenceCreatedBuffIds") or binary_probe.get("createdBuffIds") or []
            if not isinstance(created_buff_ids, list):
                continue
            for buff_id in created_buff_ids:
                buff_key = str(buff_id or "")
                if buff_key.startswith("buff_wpn_"):
                    limits[buff_key] = max_stack
        if limits:
            break
    return limits


def _buff_stack_limit(event_key: str | None) -> int | None:
    event_key = str(event_key or "")
    if not event_key:
        return None
    if _is_food_potion_buff(event_key):
        return 1
    semantic_entry = _load_local_buff_semantic_entries().get(event_key)
    if isinstance(semantic_entry, dict):
        stacking = semantic_entry.get("stacking")
        if isinstance(stacking, dict):
            semantic_limit = _positive_int(stacking.get("maxStackCnt"))
            if semantic_limit is not None:
                return semantic_limit
    exact_limit = _load_weapon_buff_stack_limits().get(event_key)
    if exact_limit is not None:
        return exact_limit
    match = _WEAPON_ID_FROM_BUFF_RE.match(event_key)
    if match:
        weapon_id = match.group(1)
        if event_key == f"buff_{weapon_id}_atk_up" or event_key.startswith(f"buff_{weapon_id}_atk_up_"):
            return _load_weapon_id_stack_limits().get(weapon_id)
    return None


def _buff_effect_hint_candidates(buff_id: str) -> list[Any]:
    hint = _buff_classifier_hint(buff_id)
    if not hint:
        return []
    resolved = hint.get("resolvedEffectHints")
    if isinstance(resolved, list) and resolved:
        return resolved
    direct = hint.get("effectHints")
    return direct if isinstance(direct, list) else []


_BUFF_DAMAGE_NAME_OVERRIDES = {
    "buff_physical_airborne": "物理浮空伤害",
    "buff_physical_crushed": "猛击",
    "buff_physical_knockdown": "倒地",
    "buff_physical_no_guard": "破防",
    "buff_chr_0028_wulfa_normal_bleed": "爪印斫痕",
    "buff_chr_0028_wulfa_normal_bleed_effect": "爪印斫痕",
    "buff_chr_0028_wulfa_normal_bleed_crit_extra_damage": "沸血",
    "buff_chr_0028_wulfa_combo_2_damage": "燎影时刻",
    "buff_common_cryst_triggered_physical_break": "猛击",
    "buff_common_heal_moss_1": "治疗苔藓",
    "buff_common_heal_moss_2": "治疗苔藓",
    "buff_common_originum_frozen": "源石冻结",
}
_RUNTIME_SKILL_NAME_OVERRIDES = {
    "chr_0017_yvonne_skill_162": "伊冯连携 / 机器人持续伤害",
    "chr_0017_yvonne_skill_163": "伊冯连携 / 机器人终结爆炸",
}
_ELEMENT_TOKEN_TO_NAME = {
    "physical": "物理",
    "fire": "灼热",
    "pulse": "电磁",
    "cryst": "寒冷",
    "crystal": "寒冷",
    "natural": "自然",
    "spell": "法术",
}
_ATTACK_INDEX_RE = re.compile(r"_attack(\d+)")
_ATTACK_VARIANT_RE = re.compile(
    r"^chr_\d{4}_[a-z0-9]+_attack_?(\d+)(?:_(\d+))?(?:_projhit)?(?:_blocked)?$",
    re.IGNORECASE,
)
_DASH_ATTACK_RE = re.compile(r"^chr_\d{4}_[a-z0-9]+_dash_attack(?:_projhit(?:\d+)?)?$", re.IGNORECASE)
_PLUNGING_ATTACK_RE = re.compile(
    r"^chr_\d{4}_[a-z0-9]+_plunging_attack(?:_(start|end|projhit))?$",
    re.IGNORECASE,
)
_TALENT_RE = re.compile(r"^chr_\d{4}_[a-z0-9]+_talent_?(\d+)(?:_(\d+))?$", re.IGNORECASE)
_POTENTIAL_RE = re.compile(r"^chr_\d{4}_[a-z0-9]+_potential_?(\d+)(?:_(\d+))?$", re.IGNORECASE)
_PASSIVE_RE = re.compile(r"^chr_\d{4}_[a-z0-9]+_passive(?:_(.+))?$", re.IGNORECASE)
_COMBO_SKILL_RE = re.compile(r"_combo(?:_\d+)?_skill(?:$|_)")
_COMBO_DAMAGE_SKILL_KEY_RE = re.compile(
    r"^buff_(chr_\d{4}_[a-z0-9]+_combo(?:_\d+)?_)damage(?:wait)?$",
    re.IGNORECASE,
)


def _repo_root() -> Path:
    override = os.environ.get("ENDFIELD_LOGS_DATA_ROOT")
    if override:
        return Path(override)
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        frozen_path = Path(frozen_root)
        if (frozen_path / "data").exists():
            return frozen_path
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        for parent in (exe_dir, *exe_dir.parents):
            if (parent / "data" / "local_tables").exists() or (parent / "data" / "akedata").exists():
                return parent
    for parent in Path(__file__).resolve().parents:
        if (parent / "data").exists() and ((parent / "packages").exists() or (parent / "data" / "local_tables").exists()):
            return parent
    return Path(__file__).resolve().parents[3]


def _apply_dungeon_catalog_overrides() -> None:
    """Merge dungeon alias tables from data/local_tables/dungeon_catalog.json.

    The catalog file is the single maintained source for dungeon aliases shared
    by parser_core, the API service, and the web frontend. Entries in the file
    win over the built-in tables above; the built-ins remain as a fallback for
    environments where the data directory is absent.
    """
    catalog_path = _repo_root() / "data" / "local_tables" / "dungeon_catalog.json"
    if not catalog_path.exists():
        return
    try:
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    parser_tables = catalog.get("parser") or {}
    for key, value in (parser_tables.get("dungeon_context_aliases") or {}).items():
        if isinstance(value, list) and len(value) == 2:
            _DUNGEON_CONTEXT_ALIASES[str(key)] = (str(value[0]), str(value[1]))
    for key, value in (parser_tables.get("dungeon_enemy_hints") or {}).items():
        _DUNGEON_ENEMY_HINT_ALIASES[str(key)] = str(value)


_apply_dungeon_catalog_overrides()


def _token_field(line: str, key: str) -> str | None:
    match = re.search(_LOADOUT_FIELD_RE_TEMPLATE.format(key=re.escape(key)), line)
    return match.group(1) if match else None


def _braced_field(line: str, key: str) -> str | None:
    marker = f"{key}="
    start = line.find(marker)
    if start < 0:
        return None
    brace_start = line.find("{", start + len(marker))
    if brace_start < 0:
        return None
    depth = 0
    for index in range(brace_start, len(line)):
        char = line[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return line[brace_start + 1:index]
    return None


def _split_top_level(text: str, sep: str) -> list[str]:
    parts: list[str] = []
    start = 0
    depth = 0
    for index, char in enumerate(text):
        if char == "{":
            depth += 1
        elif char == "}":
            depth = max(0, depth - 1)
        elif char == sep and depth == 0:
            parts.append(text[start:index])
            start = index + 1
    parts.append(text[start:])
    return [part.strip() for part in parts if part.strip()]


def _parse_bb_assignments(blob: str | None) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for item in _split_top_level(str(blob or ""), ","):
        if "=" not in item:
            continue
        key, raw_value = item.split("=", 1)
        value = raw_value.strip()
        rate = _safe_positive_rate(value)
        values[key.strip()] = rate if rate is not None else value
    return values


def _ms_time_text(timestamp_ms: int | None) -> str | None:
    if timestamp_ms is None:
        return None
    value = int(timestamp_ms) % (24 * 60 * 60 * 1000)
    hours, rem = divmod(value, 60 * 60 * 1000)
    minutes, rem = divmod(rem, 60 * 1000)
    seconds, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"


@lru_cache(maxsize=1)
def _load_packet_numeric_buff_map() -> dict[str, dict[str, Any]]:
    map_path = _repo_root() / "data" / "packet_semantics" / "buff_numeric_map.json"
    if not map_path.exists():
        return {}
    try:
        payload = json.loads(map_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    mappings = payload.get("mappings")
    if not isinstance(mappings, dict):
        return {}
    return {
        str(buff_id): mapping
        for buff_id, mapping in mappings.items()
        if isinstance(mapping, dict)
    }


def _merge_packet_buff_mapping_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {}
    base = dict(rows[0])
    effect_keys: set[str] = set()
    merged_effects: list[dict[str, Any]] = []
    for field in ("effects", "dynamic_effects"):
        merged: list[dict[str, Any]] = []
        for row in rows:
            values = row.get(field)
            if not isinstance(values, list):
                continue
            for item in values:
                if not isinstance(item, dict):
                    continue
                marker = json.dumps(item, ensure_ascii=False, sort_keys=True)
                unique_key = f"{field}:{marker}"
                if unique_key in effect_keys:
                    continue
                effect_keys.add(unique_key)
                merged.append(item)
        if merged:
            merged_effects.extend(merged)
            base[field] = merged
    if "effects" not in base:
        base["effects"] = []
    if "dynamic_effects" not in base:
        base["dynamic_effects"] = []
    for row in rows[1:]:
        if not base.get("reason") and row.get("reason"):
            base["reason"] = row.get("reason")
        if not base.get("confidence") and row.get("confidence"):
            base["confidence"] = row.get("confidence")
        if base.get("stack_limit") in (None, "", 0) and row.get("stack_limit") not in (None, "", 0):
            base["stack_limit"] = row.get("stack_limit")
    return base


@lru_cache(maxsize=1)
def _load_packet_canonical_buff_map() -> dict[str, dict[str, Any]]:
    by_canonical: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in _load_packet_numeric_buff_map().values():
        canonical_buff_id = str(row.get("canonical_buff_id") or "")
        if not canonical_buff_id:
            continue
        by_canonical[canonical_buff_id].append(row)
    return {
        canonical_buff_id: _merge_packet_buff_mapping_rows(rows)
        for canonical_buff_id, rows in by_canonical.items()
        if rows
    }


@lru_cache(maxsize=1)
def _load_mechanism_registry_by_buff_id() -> dict[str, list[dict[str, Any]]]:
    path = _repo_root() / "data" / "packet_semantics" / "mechanism_registry.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    rows_by_buff = payload.get("by_buff_id")
    if not isinstance(rows_by_buff, dict):
        return {}
    out: dict[str, list[dict[str, Any]]] = {}
    for buff_id, rows in rows_by_buff.items():
        if not isinstance(rows, list):
            continue
        normalized_rows = [row for row in rows if isinstance(row, dict)]
        if normalized_rows:
            out[str(buff_id)] = normalized_rows
    return out


def _mechanism_registry_buff_hint(buff_id: str | None) -> dict[str, Any]:
    key = str(buff_id or "")
    if not key:
        return {}
    canonical_key = _load_num_id_str_buff_map().get(key, key) if key.isdigit() else key
    rows = _load_mechanism_registry_by_buff_id().get(canonical_key) or []
    if len(rows) != 1:
        return {}
    row = dict(rows[0])
    row["canonical_buff_id"] = str(row.get("canonical_buff_id") or canonical_key)
    if row.get("source_kind") == "weapon" and row.get("source_id") and not row.get("weapon_id"):
        row["weapon_id"] = row.get("source_id")
    if row.get("source_kind") == "suit" and row.get("source_id") and not row.get("suit_id"):
        row["suit_id"] = row.get("source_id")
    row.setdefault("scope", "loadout_guarded")
    row.setdefault("confidence", "compiled_from_unpack")
    return row


def _packet_numeric_buff_hint(buff_id: str | None) -> dict[str, Any]:
    key = str(buff_id or "")
    direct = _load_packet_numeric_buff_map().get(key)
    if isinstance(direct, dict):
        return direct
    canonical = _load_packet_canonical_buff_map().get(key)
    if isinstance(canonical, dict):
        return canonical
    return _mechanism_registry_buff_hint(key)


@lru_cache(maxsize=1)
def _load_rdps_semantics_registry() -> dict[str, Any]:
    path = _repo_root() / "data" / "packet_semantics" / "rdps_semantics_registry.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _record_bb_key_set(record: dict[str, Any]) -> set[str]:
    keys = {str(key) for key in record.get("bb_keys") or [] if str(key)}
    keys.update(str(key) for key in (record.get("bb_values") or {}).keys() if str(key))
    return keys


def _rdps_registry_bb_keys_allowed(entry: dict[str, Any], record: dict[str, Any]) -> bool:
    allowed_values = entry.get("allowed_bb_keys")
    if not isinstance(allowed_values, list):
        return True
    allowed = {str(key).lower() for key in allowed_values}
    if "*" in allowed:
        return True
    observed = {key.lower() for key in _record_bb_key_set(record)}
    return observed.issubset(allowed)


_RDPS_REGISTRY_CONTROL_BB_KEYS = {
    "",
    "=",
    "duration",
    "duration2",
    "duration_spellvulnerable",
    "life_time",
    "lifetime",
    "max_stack",
    "max_stack_count",
    "maxstack",
    "stack_limit",
    "stacklimit",
    "cntmax",
    "count",
    "max_count",
}


def _rdps_registry_entry_matches_guard(entry: dict[str, Any], record: dict[str, Any]) -> bool:
    guard = entry.get("guard")
    if not isinstance(guard, dict):
        return True

    source_key = str(record.get("source_character_key") or "")
    target_key = str(record.get("target_character_key") or "")
    packet_mapping = record.get("packet_mapping") if isinstance(record.get("packet_mapping"), dict) else {}

    source_guard = str(guard.get("source_character_key") or guard.get("source_character_id") or "")
    if source_guard and source_key != source_guard:
        return False

    character_guard = str(guard.get("character_id") or "")
    if character_guard and character_guard not in {source_key, target_key}:
        return False

    source_skill = str(record.get("source_skill_key") or "")
    source_skill_family = str(record.get("source_skill_family_key") or source_skill)
    skill_guard = str(guard.get("source_skill_key") or "")
    if skill_guard and source_skill != skill_guard:
        return False
    family_guard = str(guard.get("source_skill_family_key") or "")
    if family_guard and source_skill_family != family_guard:
        return False

    weapon_guard = str(guard.get("weapon_id") or "")
    if weapon_guard:
        mapping_weapon = str(packet_mapping.get("weapon_id") or "")
        event_key = _normalize_buff_id(record.get("event_key"))
        raw_event_key = _normalize_buff_id(record.get("raw_event_key"))
        event_matches_weapon = event_key.startswith(f"buff_{weapon_guard}") or raw_event_key.startswith(f"buff_{weapon_guard}")
        if mapping_weapon and mapping_weapon != weapon_guard:
            return False
        if not mapping_weapon and not event_matches_weapon:
            return False

    suit_guard = str(guard.get("suit_id") or "")
    if suit_guard:
        mapping_suit = str(packet_mapping.get("suit_id") or "")
        if mapping_suit and mapping_suit != suit_guard:
            return False

    return True


def _rdps_registry_matching_effect_entry(record: dict[str, Any], *, require_guard: bool) -> dict[str, Any] | None:
    registry = _load_rdps_semantics_registry()
    verified = registry.get("verified_effects") if isinstance(registry.get("verified_effects"), dict) else {}
    candidates = {
        _normalize_buff_id(record.get("event_key")),
        _normalize_buff_id(record.get("raw_event_key")),
    }
    candidates.discard("")
    raw_numeric = _normalize_buff_id(record.get("raw_event_key"))

    for canonical_buff_id, entry in verified.items():
        if not isinstance(entry, dict):
            continue
        aliases = {str(value) for value in entry.get("aliases") or [] if str(value)}
        numeric_ids = {str(value) for value in entry.get("numeric_ids") or [] if str(value)}
        if not (
            str(canonical_buff_id) in candidates
            or bool(candidates & aliases)
            or (raw_numeric and raw_numeric in numeric_ids)
        ):
            continue
        if require_guard and not _rdps_registry_entry_matches_guard(entry, record):
            continue
        return entry

    prefixes = registry.get("verified_prefixes") if isinstance(registry.get("verified_prefixes"), list) else []
    for key in candidates:
        if not key:
            continue
        for entry in prefixes:
            if not isinstance(entry, dict):
                continue
            prefix = str(entry.get("prefix") or "")
            if not prefix or not key.startswith(prefix):
                continue
            if require_guard and not _rdps_registry_entry_matches_guard(entry, record):
                continue
            if _rdps_registry_bb_keys_allowed(entry, record):
                return entry
    return None


def _rdps_registry_known_non_rdps_entry(record: dict[str, Any]) -> dict[str, Any] | None:
    registry = _load_rdps_semantics_registry()
    known = registry.get("known_non_rdps") if isinstance(registry.get("known_non_rdps"), dict) else {}
    exact = known.get("exact_buff_ids") if isinstance(known.get("exact_buff_ids"), dict) else {}
    candidates = [
        _normalize_buff_id(record.get("event_key")),
        _normalize_buff_id(record.get("raw_event_key")),
    ]
    for key in candidates:
        entry = exact.get(key)
        if isinstance(entry, dict) and _rdps_registry_bb_keys_allowed(entry, record):
            return entry

    prefixes = known.get("prefixes") if isinstance(known.get("prefixes"), list) else []
    for key in candidates:
        if not key:
            continue
        for entry in prefixes:
            if not isinstance(entry, dict):
                continue
            prefix = str(entry.get("prefix") or "")
            if prefix and key.startswith(prefix) and _rdps_registry_bb_keys_allowed(entry, record):
                return entry
    return None


def _rdps_registry_suppresses_zone_effects(record: dict[str, Any]) -> bool:
    entry = _rdps_registry_known_non_rdps_entry(record)
    return bool(entry and entry.get("suppress_zone_effects"))


def _rdps_registry_verified_effect_entry(record: dict[str, Any]) -> dict[str, Any] | None:
    return _rdps_registry_matching_effect_entry(record, require_guard=True)


def _rdps_registry_candidate_effect_entry(record: dict[str, Any]) -> dict[str, Any] | None:
    return _rdps_registry_matching_effect_entry(record, require_guard=False)


def _rdps_registry_effect_bb_keys(entry: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for effect in entry.get("effects") or []:
        if not isinstance(effect, dict):
            continue
        for field in ("bb_key", "add_bb_key", "delay_bb_key", "max_bb_key"):
            value = str(effect.get(field) or "")
            if value:
                keys.add(value)
        keys.update(str(value) for value in effect.get("bb_keys") or [] if str(value))
        keys.update(str(value) for value in effect.get("required_bb_keys") or [] if str(value))
    return keys


def _rdps_registry_ignored_bb_keys(entry: dict[str, Any]) -> set[str]:
    ignored = {key.lower() for key in _RDPS_REGISTRY_CONTROL_BB_KEYS}
    ignored.update(str(key).lower() for key in _rdps_registry_effect_bb_keys(entry))
    ignored.update(str(key).lower() for key in entry.get("ignored_bb_keys") or [] if str(key))
    ignored.update(str(key).lower() for key in entry.get("self_bb_keys") or [] if str(key))
    return ignored


def _rdps_registry_effect_like_bb_key(record: dict[str, Any], bb_key: str) -> bool:
    lowered = str(bb_key or "").lower()
    if lowered in _RDPS_REGISTRY_CONTROL_BB_KEYS:
        return False
    if _is_damage_increase_bb_key(lowered):
        return True
    if any(token in lowered for token in ("atk", "attack", "dmg", "damage", "vulnerable", "fragile", "res", "def_decrease", "crit")):
        return True
    label = _label_from_bb_key(
        lowered,
        buff_id=_normalize_buff_id(record.get("event_key")),
        target_is_enemy=bool(record.get("target_enemy_key")),
    )
    return _zone_from_label(label or "") is not None


def _rdps_registry_unrecognized_effect_bb_keys(entry: dict[str, Any], record: dict[str, Any]) -> list[str]:
    ignored = _rdps_registry_ignored_bb_keys(entry)
    keys: set[str] = set()
    keys.update(str(key) for key in (record.get("bb_values") or {}).keys() if str(key))
    keys.update(str(mod.get("bb_key") or "") for mod in record.get("attr_mods") or [] if str(mod.get("bb_key") or ""))
    return sorted(
        key
        for key in keys
        if key.lower() not in ignored and _rdps_registry_effect_like_bb_key(record, key)
    )


def _rdps_registry_effect_runtime_rate(
    spec: dict[str, Any],
    record: dict[str, Any],
) -> tuple[float | None, str | None]:
    bb_values = {str(key): value for key, value in (record.get("bb_values") or {}).items()}
    candidate_keys = [str(key) for key in spec.get("bb_keys") or [] if str(key)]
    primary_key = str(spec.get("bb_key") or "")
    if primary_key and primary_key not in candidate_keys:
        candidate_keys.insert(0, primary_key)
    for bb_key in candidate_keys:
        rate = _safe_positive_rate(bb_values.get(bb_key))
        if rate is not None:
            return rate, bb_key

    formula = str(spec.get("formula") or "")
    if formula == "atk_add_plus_mult_consume_half_for_other_targets":
        add = _coerce_optional_float(bb_values.get(str(spec.get("add_bb_key") or "atk_up_add")))
        mult = _coerce_optional_float(bb_values.get(str(spec.get("mult_bb_key") or "atk_up_mult")))
        consumed = _coerce_optional_float(bb_values.get(str(spec.get("consume_bb_key") or "consume_layer")))
        if add is None or mult is None or consumed is None:
            return None, None
        rate = add + mult * consumed
        source_key = str(record.get("source_character_key") or "")
        target_key = str(record.get("target_character_key") or "")
        if target_key and source_key and target_key != source_key:
            rate *= float(spec.get("other_target_multiplier") or 0.5)
        return rate if rate > 0 else None, primary_key or str(spec.get("add_bb_key") or "atk_up_add")

    static_rate = _safe_positive_rate(spec.get("rate"))
    if static_rate is not None and str(spec.get("value_source") or "").lower() in {"constant", "static_literal"}:
        return static_rate, primary_key or None
    return None, None


def _rdps_registry_zone_effects(record: dict[str, Any], entry: dict[str, Any]) -> list[dict[str, Any]]:
    if entry.get("dynamic"):
        return []
    effects: list[dict[str, Any]] = []
    for spec in entry.get("effects") or []:
        if not isinstance(spec, dict):
            continue
        zone = str(spec.get("zone") or "")
        if zone not in _RDPS_ALLOCATABLE_ZONES and zone != "crit":
            continue
        rate, used_bb_key = _rdps_registry_effect_runtime_rate(spec, record)
        if rate is None:
            continue
        effect = {
            "zone": zone,
            "element": _normalize_effect_element(str(spec.get("element") or "all")),
            "rate": rate,
        }
        if used_bb_key:
            effect["_registry_bb_key"] = used_bb_key
            _attach_bb_key_damage_type_condition(effect, used_bb_key)
            if spec.get("expose_bb_key"):
                effect["bb_key"] = used_bb_key
        if isinstance(spec.get("condition"), dict):
            effect["condition"] = dict(spec["condition"])
        effects.append(effect)
    return effects


def _rdps_registry_validation_error(entry: dict[str, Any], record: dict[str, Any]) -> dict[str, Any] | None:
    if not _rdps_registry_bb_keys_allowed(entry, record):
        return {"reason": "registry allowed_bb_keys check failed"}
    unknown_bb_keys = _rdps_registry_unrecognized_effect_bb_keys(entry, record)
    if unknown_bb_keys:
        return {
            "reason": "verified rDPS buff carried effect-like BB keys not declared by rdps_semantics_registry",
            "unknown_bb_keys": unknown_bb_keys,
        }
    if entry.get("dynamic"):
        return None
    if entry.get("effects") and not _rdps_registry_zone_effects(record, entry):
        return {
            "reason": "verified rDPS buff did not expose required runtime BB value declared by rdps_semantics_registry",
            "required_bb_keys": sorted(_rdps_registry_effect_bb_keys(entry)),
        }
    return None



def _parse_loadout_suits(raw: str) -> set[str]:
    return {
        suit_id
        for suit_id, count in re.findall(r"\[([^\]]+)\]=(\d+)", raw or "")
        if int(count) >= 3
    }


@lru_cache(maxsize=1)
def _load_weapon_catalog() -> dict[str, dict[str, Any]]:
    root = _repo_root() / "data" / "akedata" / "weapon" / "items"
    catalog: dict[str, dict[str, Any]] = {}
    if not root.is_dir():
        return catalog
    for path in root.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        weapon_id = str(payload.get("weaponId") or path.stem)
        catalog[weapon_id] = {
            "weapon_template": weapon_id,
            "weapon_name": str(payload.get("title") or payload.get("name") or weapon_id),
            "weapon_type": payload.get("weapontype"),
            "rarity": payload.get("rarity"),
            "base_atk_values": payload.get("baseAtk") if isinstance(payload.get("baseAtk"), list) else [],
            "skilllist": payload.get("skilllist") if isinstance(payload.get("skilllist"), list) else [],
        }
    return catalog


@lru_cache(maxsize=1)
def _load_character_base_stat_catalog() -> dict[str, dict[int, dict[str, Any]]]:
    root = _repo_root() / "data" / "local_tables" / "character" / "items"
    catalog: dict[str, dict[int, dict[str, Any]]] = {}
    if not root.is_dir():
        return catalog
    for path in root.glob("chr_*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        raw = payload.get("raw") if isinstance(payload.get("raw"), dict) else {}
        attributes = raw.get("attributes") if isinstance(raw, dict) else []
        if not isinstance(attributes, list):
            continue
        level_rows: dict[int, dict[str, Any]] = {}
        for row in attributes:
            if not isinstance(row, dict):
                continue
            attr_blob = row.get("Attribute") if isinstance(row.get("Attribute"), dict) else {}
            attrs = attr_blob.get("attrs") if isinstance(attr_blob, dict) else []
            if not isinstance(attrs, list):
                continue
            values: dict[int, float] = {}
            level = None
            for item in attrs:
                if not isinstance(item, dict):
                    continue
                try:
                    attr_type = int(item.get("attrType"))
                    attr_value = float(item.get("attrValue"))
                except (TypeError, ValueError):
                    continue
                values[attr_type] = attr_value
                if attr_type == 0:
                    level = int(round(attr_value))
            if level is None:
                continue
            break_stage = int(row.get("breakStage") or 0)
            previous = level_rows.get(level)
            if previous is not None and int(previous.get("break_stage") or 0) > break_stage:
                continue
            level_rows[level] = {
                "level": level,
                "break_stage": break_stage,
                "hp": values.get(1),
                "atk": values.get(2),
                "def": values.get(3),
                "attr_39": values.get(39),
                "attr_40": values.get(40),
                "attr_41": values.get(41),
                "attr_42": values.get(42),
            }
        if level_rows:
            catalog[path.stem] = level_rows
    return catalog


def _character_base_stats(character_key: str | None, level: int | None) -> dict[str, Any] | None:
    key = str(character_key or "")
    if not key:
        return None
    rows = _load_character_base_stat_catalog().get(key)
    if not rows:
        return None
    if level is None or level <= 0:
        max_level = max(rows)
        return {
            **rows[max_level],
            "level_source": "assumed_max_level",
        }
    exact = rows.get(int(level))
    if exact is not None:
        return {
            **exact,
            "level_source": "loadout",
        }
    lower_levels = [value for value in rows if value <= int(level)]
    if lower_levels:
        nearest = max(lower_levels)
        return {
            **rows[nearest],
            "level_source": "nearest_lower_level",
        }
    nearest = min(rows)
    return {
        **rows[nearest],
        "level_source": "nearest_level",
    }


@lru_cache(maxsize=1)
def _load_suit_catalog() -> dict[str, dict[str, Any]]:
    root = _repo_root() / "data" / "akedata" / "equip" / "items"
    catalog: dict[str, dict[str, Any]] = {}
    if not root.is_dir():
        return catalog
    for path in root.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        suit_id = str(payload.get("suitID") or path.stem)
        catalog[suit_id] = {
            "suit_id": suit_id,
            "suit_name": str(payload.get("套组名称") or payload.get("name") or suit_id),
            "description": str(payload.get("技能描述") or ""),
            "value": payload.get("value") if isinstance(payload.get("value"), dict) else {},
        }
    return catalog


@lru_cache(maxsize=1)
def _load_equip_item_catalog() -> dict[str, dict[str, Any]]:
    root = _repo_root() / "data" / "akedata" / "equip" / "items"
    catalog: dict[str, dict[str, Any]] = {}
    if not root.is_dir():
        return catalog
    for path in root.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        suit_id = str(payload.get("suitID") or path.stem)
        suit_name = str(payload.get("套组名称") or suit_id)
        equip_items = payload.get("equip")
        if not isinstance(equip_items, dict):
            continue
        for item_id, item in equip_items.items():
            if not isinstance(item, dict):
                continue
            key = str(item.get("itemId") or item_id)
            catalog[key] = {
                "item_id": key,
                "item_name": str(item.get("name") or key),
                "suit_id": suit_id,
                "suit_name": suit_name,
                "part_name": str(item.get("部位") or ""),
                "rarity": item.get("rarity"),
                "main_attr": item.get("主词条") if isinstance(item.get("主词条"), dict) else None,
                "sub_attrs": item.get("副词条") if isinstance(item.get("副词条"), dict) else {},
            }
    return catalog


def _parse_skill_int_ids(raw_line: str) -> list[str]:
    match = re.search(r"skillIntIds=\[([^\]]*)\]", raw_line)
    if not match:
        return []
    return re.findall(r"\d+", match.group(1))


def _parse_equip_levels(raw: str | None) -> list[dict[str, int]]:
    levels: list[dict[str, int]] = []
    for index, level in re.findall(r"(\d+):(\d+)", str(raw or "")):
        levels.append({"index": int(index), "level": int(level)})
    return levels


def _parse_inline_equip_stats(raw: str | None) -> list[dict[str, Any]]:
    stats: list[dict[str, Any]] = []
    for item in str(raw or "").split(";"):
        if ":" not in item or "=" not in item:
            continue
        slot, rest = item.split(":", 1)
        name, raw_value = rest.split("=", 1)
        level = None
        value_text = raw_value
        if "@" in raw_value:
            value_text, raw_level = raw_value.rsplit("@", 1)
            try:
                level = int(raw_level)
            except ValueError:
                level = None
        number = _safe_positive_rate(value_text)
        stats.append(
            {
                "slot": slot,
                "name": name,
                "value": number if number is not None else value_text,
                "level": level,
            }
        )
    return stats


def _parse_inline_equips(raw_line: str) -> list[dict[str, Any]]:
    equips_blob = _braced_field(raw_line, "equips")
    if not equips_blob:
        return []
    matches = list(re.finditer(r"\[(\d+)\]=", equips_blob))
    equips: list[dict[str, Any]] = []
    catalog = _load_equip_item_catalog()
    for index, match in enumerate(matches):
        slot = int(match.group(1))
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(equips_blob)
        entry = equips_blob[start:end].strip()
        item_id = entry.split("|", 1)[0].strip()
        meta = catalog.get(item_id, {})
        level_match = re.search(r"\|lv=([^|]+)", entry)
        stats_match = re.search(r"\|stats=(.*)$", entry)
        equips.append(
            {
                "slot": slot,
                "item_id": item_id,
                "item_name": meta.get("item_name") or item_id,
                "suit_id": meta.get("suit_id") or "",
                "suit_name": meta.get("suit_name") or "",
                "part_name": meta.get("part_name") or "",
                "rarity": meta.get("rarity"),
                "enhance_levels": _parse_equip_levels(level_match.group(1) if level_match else None),
                "stats": _parse_inline_equip_stats(stats_match.group(1) if stats_match else None),
                "catalog_main_attr": meta.get("main_attr"),
                "catalog_sub_attrs": meta.get("sub_attrs") or {},
            }
        )
    return equips


def _parse_suit_counts(raw: str | None) -> list[dict[str, Any]]:
    suits: list[dict[str, Any]] = []
    catalog = _load_suit_catalog()
    for suit_id, count_text in re.findall(r"\[([^\]]+)\]=(\d+)", str(raw or "")):
        count = int(count_text)
        meta = catalog.get(suit_id, {})
        suits.append(
            {
                "suit_id": suit_id,
                "suit_name": meta.get("suit_name") or suit_id,
                "piece_count": count,
                "active": count >= 3,
                "description": meta.get("description") or "",
                "value": meta.get("value") or {},
            }
        )
    return suits


def _parse_weapon_source_skills(blob: str | None) -> list[dict[str, Any]]:
    if not blob:
        return []
    skills: list[dict[str, Any]] = []
    for entry in _split_top_level(blob, ";"):
        if ":" not in entry:
            continue
        skill_id, rest = entry.split(":", 1)
        level_match = re.search(r"(?:^|:)level=([^:]+)", rest)
        potential_match = re.search(r"(?:^|:)potentialLv=([^:]+)", rest)
        bb_blob = _braced_field(f"bb={{{rest.split('bb={', 1)[1]}" if "bb={" in rest else "", "bb")
        skills.append(
            {
                "skill_id": skill_id.strip(),
                "level": _coerce_int(level_match.group(1), default=0) if level_match else None,
                "potential_level": _coerce_int(potential_match.group(1), default=0) if potential_match else None,
                "bb": _parse_bb_assignments(bb_blob),
            }
        )
    return skills


def _weapon_value_options(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def _select_weapon_option(options: list[Any], level: Any) -> Any:
    if not options or level is None:
        return None
    try:
        level_int = int(level)
    except (TypeError, ValueError):
        return None
    if 0 <= level_int < len(options):
        return options[level_int]
    if 1 <= level_int <= len(options):
        return options[level_int - 1]
    return None


def _weapon_values_match(expected: Any, observed: Any) -> bool:
    if isinstance(expected, (int, float)) and isinstance(observed, (int, float)):
        return isclose(float(expected), float(observed), rel_tol=1e-6, abs_tol=1e-6)
    return str(expected) == str(observed)


def _normalize_weapon_refine_index(index: int, option_count: int) -> int:
    if option_count <= 0:
        return index
    display_tier_count = 6
    offset = max(0, option_count - display_tier_count)
    normalized = index - offset
    if normalized < 0:
        return 0
    max_normalized = max(0, min(option_count, display_tier_count) - 1)
    return min(normalized, max_normalized)


def _weapon_skill_blackboard_rows(weapon_template: str) -> list[dict[str, Any]]:
    meta = _load_weapon_catalog().get(weapon_template, {})
    rows: list[dict[str, Any]] = []
    for index, skill in enumerate(meta.get("skilllist") or []):
        if not isinstance(skill, dict):
            continue
        blackboard_rows = [
            raw
            for raw in skill.get("blackboard") or []
            if isinstance(raw, dict) and str(raw.get("key") or "").strip()
        ]
        if not blackboard_rows:
            continue
        rows.append(
            {
                "index": index,
                "keys": {str(raw.get("key") or "").strip() for raw in blackboard_rows},
                "blackboard": blackboard_rows,
            }
        )
    return rows


def _infer_weapon_refine_from_source_skills(
    weapon_template: str,
    source_skills: list[dict[str, Any]] | None,
) -> int | None:
    skill_rows = _weapon_skill_blackboard_rows(weapon_template)
    if not skill_rows:
        return None

    source_rows: list[dict[str, Any]] = []
    for skill in source_skills or []:
        if not isinstance(skill, dict):
            continue
        blackboard = skill.get("bb") if isinstance(skill.get("bb"), dict) else skill.get("blackboard")
        if not isinstance(blackboard, dict) or not blackboard:
            continue
        keys = {str(key or "").strip() for key in blackboard.keys() if str(key or "").strip()}
        if not keys:
            continue
        source_rows.append(
            {
                "keys": keys,
                "blackboard": blackboard,
                "level": _coerce_int(skill.get("level"), default=0),
            }
        )
    if not source_rows:
        return None

    passive_row = max(skill_rows, key=lambda row: (len(row["keys"]), int(row["index"])))
    passive_keys = set(passive_row["keys"])
    best_source = max(
        source_rows,
        key=lambda row: (
            len(passive_keys & set(row["keys"])),
            len(set(row["keys"])),
            int(row["level"] or 0),
        ),
    )
    if not (passive_keys & set(best_source["keys"])):
        return None

    max_option_count = max(
        len(_weapon_value_options(raw.get("value")))
        for raw in passive_row["blackboard"]
        if _weapon_value_options(raw.get("value"))
    )
    candidates: list[int] = []
    for refine in range(max_option_count):
        compared = 0
        mismatch = False
        for raw in passive_row["blackboard"]:
            key = str(raw.get("key") or "").strip()
            if not key or key not in best_source["blackboard"]:
                continue
            expected = _select_weapon_option(_weapon_value_options(raw.get("value")), refine)
            observed = best_source["blackboard"].get(key)
            compared += 1
            if expected is None or not _weapon_values_match(expected, observed):
                mismatch = True
                break
        if compared and not mismatch:
            candidates.append(refine)

    hinted_refine = int(best_source["level"] - 1) if int(best_source["level"] or 0) > 0 else None
    if len(candidates) == 1:
        return _normalize_weapon_refine_index(candidates[0], max_option_count)
    if hinted_refine is not None and hinted_refine in candidates:
        return _normalize_weapon_refine_index(hinted_refine, max_option_count)
    if hinted_refine is not None and 0 <= hinted_refine < max_option_count:
        return _normalize_weapon_refine_index(hinted_refine, max_option_count)
    if candidates:
        return _normalize_weapon_refine_index(candidates[0], max_option_count)
    return None


def _selected_weapon_base_atk(weapon_template: str, weapon_level: int | None) -> Any:
    values = _load_weapon_catalog().get(weapon_template, {}).get("base_atk_values")
    if not isinstance(values, list) or weapon_level is None:
        return None
    if 0 < weapon_level <= len(values):
        return values[weapon_level - 1]
    return None


def _parse_loadout_slot_snapshot(raw_line: str) -> dict[str, Any] | None:
    char_key = _token_field(raw_line, "char")
    if not char_key or not char_key.startswith("chr_"):
        return None
    weapon_template = _token_field(raw_line, "weaponTemplate") or ""
    weapon_level = _coerce_int(_token_field(raw_line, "weaponLv"), default=0)
    weapon_meta = _load_weapon_catalog().get(weapon_template, {})
    equip_suit_blob = _braced_field(raw_line, "equipSuit") or ""
    row = {
        "slot": _coerce_int(_token_field(raw_line, "slot"), default=0),
        "character_key": char_key,
        "character_name": _resolve_character_name(char_key) or char_key,
        "character_level": _coerce_int(_token_field(raw_line, "charLv"), default=0) or None,
        "potential": _coerce_int(_token_field(raw_line, "potential"), default=0),
        "weapon_inst_id": _token_field(raw_line, "weaponInstId"),
        "weapon_template": weapon_template,
        "weapon_name": weapon_meta.get("weapon_name") or weapon_template,
        "weapon_level": weapon_level,
        "weapon_refine": _coerce_int(_token_field(raw_line, "refine"), default=0),
        "weapon_refine_source": "loadout",
        "weapon_break": _coerce_int(_token_field(raw_line, "break"), default=0),
        "weapon_base_atk": _selected_weapon_base_atk(weapon_template, weapon_level),
        "weapon_catalog_skilllist": weapon_meta.get("skilllist") or [],
        "equip_suit_raw": "{" + equip_suit_blob + "}" if equip_suit_blob else "{}",
        "suit_effects": _parse_suit_counts(equip_suit_blob),
        "equips": _parse_inline_equips(raw_line),
        "skill_int_ids": _parse_skill_int_ids(raw_line),
        "weapon_source_skills": [],
        "weapon_refine_stats": [],
        "gem_template": None,
        "gem_terms": {},
    }
    return row


def _parse_loadout_stats_snapshot(raw_line: str) -> dict[str, Any] | None:
    char_key = _token_field(raw_line, "char")
    if not char_key or not char_key.startswith("chr_"):
        return None
    weapon_template = _token_field(raw_line, "weaponTemplate") or ""
    weapon_level = _coerce_int(_token_field(raw_line, "weaponLv"), default=0)
    weapon_refine_stats = _parse_weapon_source_skills(_braced_field(raw_line, "weaponRefineStats"))
    weapon_source_skills = _parse_weapon_source_skills(_braced_field(raw_line, "weaponSourceSkills"))
    inferred_refine = _infer_weapon_refine_from_source_skills(
        weapon_template,
        weapon_source_skills or weapon_refine_stats,
    )
    return {
        "character_key": char_key,
        "weapon_template": weapon_template,
        "weapon_refine": inferred_refine,
        "weapon_refine_source": "source_skill" if inferred_refine is not None else None,
        "weapon_base_atk": _coerce_int(_token_field(raw_line, "weaponBaseAtk"), default=0)
        or _selected_weapon_base_atk(weapon_template, weapon_level),
        "weapon_base_atk_lv1": _coerce_int(_token_field(raw_line, "weaponBaseAtkLv1"), default=0),
        "weapon_base_atk_max": _coerce_int(_token_field(raw_line, "weaponBaseAtkMax"), default=0),
        "weapon_refine_stats": weapon_refine_stats,
        "weapon_source_skills": weapon_source_skills,
        "gem_template": _token_field(raw_line, "gemTemplate"),
        "gem_terms": _parse_bb_assignments((_braced_field(raw_line, "gemTerms") or "").replace(":", "=")),
    }


def _merge_loadout_snapshot(base: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    current_refine_source = merged.get("weapon_refine_source")
    update_refine_source = update.get("weapon_refine_source")
    for key, value in update.items():
        if value in (None, "", [], {}):
            continue
        if key == "equips" and isinstance(value, list):
            current = merged.get("equips")
            if isinstance(current, list) and current:
                merged["equips"] = _merge_loadout_equips_by_slot(
                    current,
                    value,
                    suit_counts=_suit_effect_count_map(update.get("suit_effects")),
                )
            else:
                merged["equips"] = value
            continue
        if key == "weapon_refine" and current_refine_source == "source_skill" and update_refine_source != "source_skill":
            continue
        if (
            key == "weapon_refine_source"
            and current_refine_source == "source_skill"
            and value != "source_skill"
        ):
            continue
        merged[key] = value
    return merged


def _select_loadout_snapshot_for_battle(
    loadout_groups: list[dict[str, Any]],
    fallback_by_char: dict[str, dict[str, Any]],
    *,
    anchor_ms: int | None,
) -> dict[str, dict[str, Any]]:
    """Pick the loadout group that belongs to the current battle window.

    Live overlay context can contain stale bag/loadout snapshots from before a
    timer reset. Use the most recent complete group before the first relevant
    hit instead of merging every character ever seen in the retained context.
    """
    groups = [group for group in loadout_groups if group.get("rows")]
    if anchor_ms is not None:
        eligible = [
            group
            for group in groups
            if int(group.get("ts_ms") or 0) <= anchor_ms + 1000
        ]
    else:
        eligible = groups
    if not eligible:
        eligible = groups
    if not eligible:
        return {key: dict(value) for key, value in fallback_by_char.items()}

    reason_rank = {
        "BATTLE_START": 4,
        "SC_SELF_SCENE_INFO": 3,
        "SC_SYNC_CHAR_BAG_INFO": 2,
        "SC_ITEM_BAG_SCOPE_MODIFY": 1,
    }
    selected = max(
        eligible,
        key=lambda group: (
            int(group.get("ts_ms") or 0),
            reason_rank.get(str(group.get("reason") or ""), 0),
            int(group.get("index") or 0),
        ),
    )
    rows = selected.get("rows")
    if not isinstance(rows, dict):
        return {}
    merged_rows: dict[str, dict[str, Any]] = {}
    for key, value in rows.items():
        if not isinstance(value, dict):
            continue
        character_key = str(key)
        fallback = fallback_by_char.get(character_key)
        if isinstance(fallback, dict):
            merged_rows[character_key] = _merge_loadout_snapshot(fallback, value)
        else:
            merged_rows[character_key] = dict(value)
    return merged_rows


_WEAPON_LOADOUT_STATE_FIELDS = {
    "weapon_inst_id",
    "weapon_template",
    "weapon_name",
    "weapon_level",
    "weapon_refine",
    "weapon_refine_source",
    "weapon_break",
    "weapon_base_atk",
    "weapon_base_atk_lv1",
    "weapon_base_atk_max",
    "weapon_catalog_skilllist",
    "weapon_source_skills",
    "weapon_refine_stats",
    "gem_template",
    "gem_terms",
}


def _loadout_weapon_source_skill_ids(row: dict[str, Any] | None) -> set[int]:
    if not isinstance(row, dict):
        return set()
    result: set[int] = set()
    for item in row.get("weapon_source_skills") or row.get("weapon_refine_stats") or []:
        if not isinstance(item, dict):
            continue
        skill_int_id = _coerce_int(item.get("skill_id"), default=0)
        if skill_int_id:
            result.add(skill_int_id)
    return result


def _loadout_with_weapon_state(
    destination: dict[str, Any],
    source: dict[str, Any],
) -> dict[str, Any]:
    merged = copy.deepcopy(destination)
    previous_source_ids = _loadout_weapon_source_skill_ids(destination)
    for key in _WEAPON_LOADOUT_STATE_FIELDS:
        if key in source:
            merged[key] = copy.deepcopy(source[key])
        else:
            merged.pop(key, None)

    destination_potential = int(destination.get("potential") or 0)
    for field in ("weapon_source_skills", "weapon_refine_stats"):
        for item in merged.get(field) or []:
            if isinstance(item, dict):
                item["potential_level"] = destination_potential

    next_source_ids = _loadout_weapon_source_skill_ids(merged)
    skill_int_ids = [
        int(skill_int_id)
        for skill_int_id in destination.get("skill_int_ids") or []
        if int(skill_int_id) and int(skill_int_id) not in previous_source_ids
    ]
    for skill_int_id in next_source_ids:
        if skill_int_id not in skill_int_ids:
            skill_int_ids.append(skill_int_id)
    merged["skill_int_ids"] = skill_int_ids
    return merged


def _loadout_without_mismatched_weapon_skills(row: dict[str, Any]) -> dict[str, Any]:
    weapon_template = str(row.get("weapon_template") or "")
    if not weapon_template.startswith("wpn_"):
        return row
    expected_main_skill = f"sk_{weapon_template}"
    skill_id_map = _load_num_id_str_skill_map()
    main_skills = {
        skill_id_map.get(str(item.get("skill_id") or ""), str(item.get("skill_id") or ""))
        for item in row.get("weapon_source_skills") or row.get("weapon_refine_stats") or []
        if isinstance(item, dict)
    }
    main_skills = {skill_id for skill_id in main_skills if skill_id.startswith("sk_wpn_")}
    if not main_skills or expected_main_skill in main_skills:
        return row

    sanitized = copy.deepcopy(row)
    stale_source_ids = _loadout_weapon_source_skill_ids(sanitized)
    sanitized["weapon_source_skills"] = []
    sanitized["weapon_refine_stats"] = []
    if sanitized.get("weapon_refine_source") == "source_skill":
        sanitized["weapon_refine"] = None
        sanitized["weapon_refine_source"] = None
    sanitized["skill_int_ids"] = [
        int(skill_int_id)
        for skill_int_id in sanitized.get("skill_int_ids") or []
        if int(skill_int_id) and int(skill_int_id) not in stale_source_ids
    ]
    return sanitized


def _merge_tracked_loadout_state(
    previous: dict[str, Any] | None,
    row: dict[str, Any],
) -> dict[str, Any]:
    """Merge adjacent partial snapshots without retaining the old weapon.

    `_merge_loadout_snapshot` intentionally protects a source-skill-derived
    refine from weaker updates.  That protection must not cross a weapon
    instance change, where the new weapon's whole state is authoritative.
    """

    previous = previous or {}
    merged = _merge_loadout_snapshot(previous, row)
    previous_inst_id = str(previous.get("weapon_inst_id") or "")
    next_inst_id = str(row.get("weapon_inst_id") or "")
    if previous_inst_id and next_inst_id and previous_inst_id != next_inst_id:
        merged = _loadout_with_weapon_state(merged, row)
    return merged


def _repair_weapon_puton_loadout_groups(
    loadout_groups: list[dict[str, Any]],
    fallback_by_char: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Repair the partial state emitted by the old SC_WEAPON_PUTON handler.

    The legacy client updated only the receiver's weapon instance.  When a
    weapon was moved from another character, the previous owner retained the
    same instance and both characters retained their pre-swap weapon skills.
    The surrounding loadout groups contain enough information to reconstruct
    the atomic swap deterministically.
    """

    raw_state_by_char: dict[str, dict[str, Any]] = {}
    corrected_state_by_char: dict[str, dict[str, Any]] = {}

    for group in loadout_groups:
        rows = group.get("rows")
        if not isinstance(rows, dict):
            continue
        raw_rows = {
            str(char_key): copy.deepcopy(row)
            for char_key, row in rows.items()
            if isinstance(row, dict)
        }
        corrected_rows = copy.deepcopy(raw_rows)
        reason = str(group.get("reason") or "")

        if reason != "SC_SYNC_CHAR_BAG_INFO":
            # Equipment/scene/battle snapshots repeat the cached weapon state.
            # Carry an earlier correction forward while the raw instance for
            # that character has not changed.
            for char_key, raw_row in raw_rows.items():
                previous_raw = raw_state_by_char.get(char_key)
                previous_corrected = corrected_state_by_char.get(char_key)
                if not previous_raw or not previous_corrected:
                    continue
                if all(
                    previous_raw.get(field) == previous_corrected.get(field)
                    for field in _WEAPON_LOADOUT_STATE_FIELDS
                ):
                    continue
                if str(raw_row.get("weapon_inst_id") or "") == str(
                    previous_raw.get("weapon_inst_id") or ""
                ):
                    corrected_rows[char_key] = _loadout_with_weapon_state(
                        raw_row,
                        previous_corrected,
                    )

        state_updates: dict[str, dict[str, Any]] = {}
        if reason == "SC_WEAPON_PUTON":
            for receiver_key, raw_receiver in raw_rows.items():
                previous_raw_receiver = raw_state_by_char.get(receiver_key)
                previous_corrected_receiver = corrected_state_by_char.get(receiver_key)
                if not previous_raw_receiver or not previous_corrected_receiver:
                    continue
                new_weapon_inst_id = str(raw_receiver.get("weapon_inst_id") or "")
                if not new_weapon_inst_id or new_weapon_inst_id == str(
                    previous_raw_receiver.get("weapon_inst_id") or ""
                ):
                    continue

                previous_owner_key = next(
                    (
                        char_key
                        for char_key, previous_row in corrected_state_by_char.items()
                        if char_key != receiver_key
                        and str(previous_row.get("weapon_inst_id") or "") == new_weapon_inst_id
                    ),
                    None,
                )
                if previous_owner_key is None:
                    corrected_rows[receiver_key] = _loadout_without_mismatched_weapon_skills(
                        corrected_rows[receiver_key]
                    )
                    continue

                previous_owner_state = corrected_state_by_char[previous_owner_key]
                corrected_receiver = _loadout_with_weapon_state(
                    raw_receiver,
                    previous_owner_state,
                )
                owner_destination = corrected_rows.get(
                    previous_owner_key,
                    corrected_state_by_char[previous_owner_key],
                )
                corrected_previous_owner = _loadout_with_weapon_state(
                    owner_destination,
                    previous_corrected_receiver,
                )
                corrected_rows[receiver_key] = corrected_receiver
                if previous_owner_key in corrected_rows:
                    corrected_rows[previous_owner_key] = corrected_previous_owner
                else:
                    state_updates[previous_owner_key] = corrected_previous_owner

        for char_key, row in list(corrected_rows.items()):
            corrected_rows[char_key] = _loadout_without_mismatched_weapon_skills(row)
        group["rows"] = corrected_rows
        # A logical snapshot can arrive as adjacent LOADOUT / LOADOUT_STATS
        # records (and therefore as separate groups).  Preserve the fields
        # from both halves while advancing the raw/corrected state machines.
        for char_key, row in raw_rows.items():
            raw_state_by_char[char_key] = _merge_tracked_loadout_state(
                raw_state_by_char.get(char_key), row
            )
        for char_key, row in corrected_rows.items():
            corrected_state_by_char[char_key] = _merge_tracked_loadout_state(
                corrected_state_by_char.get(char_key), row
            )
        for char_key, row in state_updates.items():
            corrected_state_by_char[char_key] = _merge_tracked_loadout_state(
                corrected_state_by_char.get(char_key), row
            )

    repaired_fallback = {
        str(char_key): copy.deepcopy(row)
        for char_key, row in fallback_by_char.items()
        if isinstance(row, dict)
    }
    for char_key, row in corrected_state_by_char.items():
        repaired_fallback[char_key] = _merge_tracked_loadout_state(
            repaired_fallback.get(char_key), row
        )
    return repaired_fallback


def _equip_is_edc(equip: dict[str, Any]) -> bool:
    item_id = str(equip.get("item_id") or "")
    part_name = str(equip.get("part_name") or "")
    return "_edc_" in item_id or "饰品" in part_name or "终端" in part_name


def _alternate_edc_slot(slot: int | None) -> int | None:
    if slot == 2:
        return 3
    if slot == 3:
        return 2
    return None


def _suit_effect_count_map(value: object) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in value or []:
        if not isinstance(item, dict):
            continue
        suit_id = str(item.get("suit_id") or "")
        if not suit_id:
            continue
        counts[suit_id] = int(item.get("piece_count") or 0)
    return counts


def _equip_suit_counts(equips: list[dict[str, Any]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for equip in equips:
        if not isinstance(equip, dict):
            continue
        suit_id = str(equip.get("suit_id") or "")
        if suit_id:
            counts[suit_id] += 1
    return counts


def _merge_loadout_equips_by_slot(
    base: list[dict[str, Any]],
    update: list[dict[str, Any]],
    *,
    suit_counts: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = [dict(equip) for equip in base if isinstance(equip, dict)]
    slot_index: dict[int, int] = {}
    for index, equip in enumerate(merged):
        try:
            slot_index[int(equip.get("slot"))] = index
        except (TypeError, ValueError):
            continue

    for equip in update:
        if not isinstance(equip, dict):
            continue
        try:
            slot = int(equip.get("slot"))
        except (TypeError, ValueError):
            slot = None
        if slot is not None and slot in slot_index:
            existing = merged[slot_index[slot]]
            alternate_slot = _alternate_edc_slot(slot)
            existing_suit = str(existing.get("suit_id") or "")
            update_suit = str(equip.get("suit_id") or "")
            if (
                alternate_slot is not None
                and alternate_slot not in slot_index
                and existing_suit
                and _equip_is_edc(existing)
                and _equip_is_edc(equip)
                and suit_counts
            ):
                current_counts = _equip_suit_counts(merged)
                after_replace = current_counts.get(existing_suit, 0) - 1
                if update_suit == existing_suit:
                    after_replace += 1
                if int(suit_counts.get(existing_suit, 0) or 0) > after_replace:
                    moved = dict(existing)
                    moved["slot"] = alternate_slot
                    merged.append(moved)
                    slot_index[alternate_slot] = len(merged) - 1
            merged[slot_index[slot]] = {
                **existing,
                **{key: value for key, value in equip.items() if value not in (None, "", [], {})},
            }
        else:
            merged.append(dict(equip))
            if slot is not None:
                slot_index[slot] = len(merged) - 1

    return sorted(
        merged,
        key=lambda equip: int(equip.get("slot")) if str(equip.get("slot", "")).lstrip("-").isdigit() else 99,
    )


def _packet_mapping_applies(
    mapping: dict[str, Any],
    *,
    owner_key: str | None,
    source_key: str | None,
    active_suits_by_char: dict[str, set[str]] | None = None,
    active_weapons_by_char: dict[str, str] | None = None,
) -> bool:
    character_id = str(mapping.get("character_id") or "")
    if character_id and character_id not in {owner_key, source_key}:
        return False

    suit_id = str(mapping.get("suit_id") or "")
    if suit_id and active_suits_by_char:
        guard_key = str(source_key or owner_key or "")
        has_actor_loadout = bool(guard_key and guard_key in active_suits_by_char)
        active_suits = active_suits_by_char.get(guard_key, set()) if has_actor_loadout else set()
        if has_actor_loadout and suit_id not in active_suits:
            return False

    weapon_id = str(mapping.get("weapon_id") or "")
    if weapon_id and active_weapons_by_char:
        guard_key = str(source_key or owner_key or "")
        active_weapon = active_weapons_by_char.get(guard_key) if guard_key else None
        if active_weapon and weapon_id != active_weapon:
            return False

    return True


_STATIC_PACKET_BUFF_ALIASES = {
    # Early packet traces used this synthetic alias for suit_usp02's actual
    # damage-up child. Normalize it to the static buff id so suit gating and
    # semantic lookup see the real equipment buff.
    "buff_equipsuit_usp_02_dmgup": "buff_equipsuit_usp_02_AddAttack",
}


def _canonical_packet_buff_id(
    buff_id: str | None,
    *,
    owner_key: str | None = None,
    source_key: str | None = None,
    active_suits_by_char: dict[str, set[str]] | None = None,
    active_weapons_by_char: dict[str, str] | None = None,
) -> str:
    raw_buff_id = _normalize_buff_id(buff_id)
    if raw_buff_id in _STATIC_PACKET_BUFF_ALIASES:
        return _STATIC_PACKET_BUFF_ALIASES[raw_buff_id]
    hint = _packet_numeric_buff_hint(raw_buff_id)
    if hint and not _packet_mapping_applies(
        hint,
        owner_key=owner_key,
        source_key=source_key,
        active_suits_by_char=active_suits_by_char,
        active_weapons_by_char=active_weapons_by_char,
    ):
        return raw_buff_id
    canonical = hint.get("canonical_buff_id")
    if canonical:
        return str(canonical)
    for candidate_key in (source_key, owner_key, None):
        fallback = _canonical_num_table_buff_number(raw_buff_id, candidate_key)
        if fallback:
            return fallback
    return raw_buff_id


def _preserve_raw_numeric_internal_trigger_buff_id(record: dict[str, Any]) -> None:
    raw_buff_id = _normalize_buff_id(record.get("raw_event_key") or record.get("event_key"))
    if not raw_buff_id.isdigit():
        return
    if isinstance(record.get("packet_mapping"), dict):
        return
    if _is_internal_trigger_damage_record(record):
        record["event_key"] = raw_buff_id


def _is_packet_effectless_wrapper(record_or_buff_id: dict[str, Any] | str | None) -> bool:
    if isinstance(record_or_buff_id, dict):
        hint = record_or_buff_id.get("packet_mapping")
        if not isinstance(hint, dict):
            raw_buff_id = _normalize_buff_id(record_or_buff_id.get("raw_event_key") or record_or_buff_id.get("event_key"))
            hint = _packet_numeric_buff_hint(raw_buff_id)
    else:
        hint = _packet_numeric_buff_hint(record_or_buff_id)
    role = str(hint.get("role") or "").lower()
    has_effect_specs = bool(hint.get("effects") or hint.get("dynamic_effects"))
    return role in {"wrapper", "marker", "utility"} and not has_effect_specs


def _packet_mapping_allows_static_rate(hint: dict[str, Any]) -> bool:
    return bool(
        hint.get("allow_static_rate")
        or hint.get("allow_static_rates")
        or str(hint.get("value_source") or "").lower() in {"static_literal", "constant"}
    )


def _packet_numeric_effects(record: dict[str, Any]) -> list[dict[str, Any]]:
    raw_buff_id = _normalize_buff_id(record.get("raw_event_key") or record.get("event_key"))
    hint = record.get("packet_mapping")
    if not isinstance(hint, dict):
        hint = _packet_numeric_buff_hint(raw_buff_id)
    specs = hint.get("effects")
    bb_values = {str(key): value for key, value in (record.get("bb_values") or {}).items()}
    if not isinstance(specs, list):
        specs = _enhanced_action_child_effect_specs(str(record.get("event_key") or ""))
        if not specs:
            return []
    allow_static_rate = _packet_mapping_allows_static_rate(hint)
    effects: list[dict[str, Any]] = []
    for spec in specs:
        if not isinstance(spec, dict):
            continue
        zone = str(spec.get("zone") or "")
        if zone not in _DPD_ZONE_BUCKETS and zone != "crit":
            continue
        element = _normalize_effect_element(str(spec.get("element") or "all"))
        bb_key = str(spec.get("bb_key") or "")
        rate = _safe_positive_rate(bb_values.get(bb_key)) if bb_key else None
        if rate is None and str(spec.get("prefer_runtime_rate_key") or ""):
            rate = _safe_positive_rate(bb_values.get(str(spec.get("prefer_runtime_rate_key") or "")))
        if rate is None and allow_static_rate:
            rate = _safe_positive_rate(spec.get("rate"))
        if rate is None:
            continue
        effect = {"zone": zone, "element": element, "rate": rate}
        if bb_key:
            effect["bb_key"] = bb_key
            _attach_bb_key_damage_type_condition(effect, bb_key)
        effects.append(effect)
    return effects


def _packet_numeric_dynamic_effects(record: dict[str, Any]) -> list[dict[str, Any]]:
    raw_buff_id = _normalize_buff_id(record.get("raw_event_key") or record.get("event_key"))
    hint = record.get("packet_mapping")
    if not isinstance(hint, dict):
        hint = _packet_numeric_buff_hint(raw_buff_id)
    specs = hint.get("dynamic_effects")
    if not isinstance(specs, list):
        return []
    bb_values = {str(key): value for key, value in (record.get("bb_values") or {}).items()}
    allow_static_rate = _packet_mapping_allows_static_rate(hint)
    effects: list[dict[str, Any]] = []
    for spec in specs:
        if not isinstance(spec, dict):
            continue
        zone = str(spec.get("zone") or "")
        if zone not in _DPD_ZONE_BUCKETS and zone != "crit":
            continue
        element = _normalize_effect_element(str(spec.get("element") or "all"))
        base_bb_keys = [str(key) for key in spec.get("base_bb_keys") or [] if str(key)]
        base_bb_key = str(spec.get("base_bb_key") or spec.get("bb_key") or "")
        if not base_bb_keys and base_bb_key:
            base_bb_keys = [base_bb_key]
        base_rate = None
        for candidate_key in base_bb_keys:
            base_rate = _safe_positive_rate(bb_values.get(candidate_key))
            if base_rate is not None:
                base_bb_key = candidate_key
                break
        if base_rate is None:
            base_rate = _safe_positive_rate(spec.get("base_rate")) if allow_static_rate else None
        if base_rate is None:
            base_rate = 0.0
        add_bb_key = str(spec.get("add_bb_key") or "")
        delayed_add_rate = _safe_positive_rate(bb_values.get(add_bb_key)) if add_bb_key else None
        if delayed_add_rate is None:
            delayed_add_rate = _safe_positive_rate(spec.get("delayed_add_rate")) if allow_static_rate else None
        if delayed_add_rate is None:
            delayed_add_rate = 0.0
        delay_bb_key = str(spec.get("delay_bb_key") or "")
        delay_sec = _safe_positive_rate(bb_values.get(delay_bb_key)) if delay_bb_key else None
        if delay_sec is None and allow_static_rate:
            delay_sec = _safe_positive_rate(spec.get("delay_sec")) or 0.0
        if delay_sec is None:
            delay_sec = 0.0
        tick_rate = (_safe_positive_rate(spec.get("tick_rate")) or 0.0) if allow_static_rate else 0.0
        tick_bb_key = ""
        for candidate_key in [str(key) for key in spec.get("tick_bb_keys") or [] if str(key)]:
            runtime_tick_rate = _safe_positive_rate(bb_values.get(candidate_key))
            if runtime_tick_rate is not None:
                tick_bb_key = candidate_key
                tick_rate = runtime_tick_rate * (float(spec.get("tick_multiplier") or 1.0))
                break
        max_bb_key = str(spec.get("max_bb_key") or "")
        max_rate = _safe_positive_rate(bb_values.get(max_bb_key)) if max_bb_key else None
        if max_rate is None:
            max_rate = (_safe_positive_rate(spec.get("max_rate")) or 0.0) if allow_static_rate else 0.0
        if base_rate <= 0 and delayed_add_rate <= 0 and tick_rate <= 0:
            continue
        effect = {
            "zone": zone,
            "element": element,
            "base_rate": base_rate,
            "tick_rate": tick_rate,
            "max_rate": max_rate,
            "delayed_add_rate": delayed_add_rate,
            "delay_sec": delay_sec,
        }
        if base_bb_key:
            effect["bb_key"] = base_bb_key
        if add_bb_key:
            effect["add_bb_key"] = add_bb_key
        if delay_bb_key:
            effect["delay_bb_key"] = delay_bb_key
        if tick_bb_key:
            effect["tick_bb_key"] = tick_bb_key
        if max_bb_key:
            effect["max_bb_key"] = max_bb_key
        if spec.get("dynamic_key"):
            effect["dynamic_key"] = spec.get("dynamic_key")
        effects.append(effect)
    return effects


def _packet_mapping_stack_limit(record: dict[str, Any]) -> int | None:
    bb_values = record.get("bb_values") if isinstance(record.get("bb_values"), dict) else {}
    for key in ("max_stack", "stack_limit", "maxStack", "stackLimit"):
        limit = _positive_int(bb_values.get(key))
        if limit is not None:
            return limit
    hint = record.get("packet_mapping")
    if not isinstance(hint, dict):
        raw_buff_id = _normalize_buff_id(record.get("raw_event_key") or record.get("event_key"))
        hint = _packet_numeric_buff_hint(raw_buff_id)
    return _positive_int(hint.get("stack_limit"))


@lru_cache(maxsize=1)
def _load_packet_numeric_skill_map() -> dict[str, dict[str, Any]]:
    map_path = _repo_root() / "data" / "packet_semantics" / "skill_numeric_map.json"
    if not map_path.exists():
        return {}
    try:
        payload = json.loads(map_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    mappings = payload.get("mappings")
    if not isinstance(mappings, dict):
        return {}
    return {
        str(skill_id): mapping
        for skill_id, mapping in mappings.items()
        if isinstance(mapping, dict)
    }


def _packet_numeric_skill_hint(skill_key: str | None) -> dict[str, Any]:
    return _load_packet_numeric_skill_map().get(str(skill_key or ""), {})


@lru_cache(maxsize=1)
def _load_num_id_str_skill_map() -> dict[str, str]:
    candidate_paths = (
        _repo_root().parent / "endfield_tables" / "Data" / "TableCfg" / "NumIdStrTable.json",
        _repo_root() / "data" / "local_tables" / "NumIdStrTable.json",
    )
    for path in candidate_paths:
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        skill_section = payload.get("skill_id") if isinstance(payload, dict) else None
        if not isinstance(skill_section, dict):
            continue
        mapping = skill_section.get("dic")
        if not isinstance(mapping, dict):
            continue
        return {
            str(skill_id): str(static_id)
            for skill_id, static_id in mapping.items()
            if static_id is not None
        }
    return {}


@lru_cache(maxsize=1)
def _load_num_id_str_buff_map() -> dict[str, str]:
    candidate_paths = (
        _repo_root().parent / "endfield_tables" / "Data" / "TableCfg" / "NumIdStrTable.json",
        _repo_root() / "data" / "local_tables" / "NumIdStrTable.json",
    )
    for path in candidate_paths:
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        buff_section = payload.get("buff_id") if isinstance(payload, dict) else None
        if not isinstance(buff_section, dict):
            continue
        mapping = buff_section.get("dic")
        if not isinstance(mapping, dict):
            continue
        return {
            str(buff_id): str(static_id)
            for buff_id, static_id in mapping.items()
            if static_id is not None
        }
    return {}


def _canonical_num_table_skill_number(skill_number: str | None, character_key: str | None) -> str | None:
    if not skill_number:
        return None
    static_id = _load_num_id_str_skill_map().get(str(skill_number))
    if not static_id:
        return None
    if not _runtime_owner_matches_static_domain(character_key, static_id):
        return None
    if not character_key:
        return static_id
    match = _CHAR_KEY_RE.search(static_id)
    if match and not _character_key_matches_static_family(str(character_key), match.group(1)):
        return None
    return static_id


def _canonical_num_table_skill_id(skill_key: str | None, character_key: str | None) -> str | None:
    skill_number = _runtime_skill_number(skill_key)
    return _canonical_num_table_skill_number(skill_number, character_key)


def _parse_char_skills_line(raw_line: str) -> tuple[str, dict[str, int]] | None:
    """解析 bridge 的 CHAR_SKILLS 行 → (角色key, {技能key: 等级})。
    运行时兜底 id（纯数字 / chr_xxx_skill_766）经 num 表解析，失败自弃。"""
    fields = _extract_fields(raw_line)
    owner_key = str(fields.get("owner") or "")
    tokens_match = re.search(r"skills=\[([^\]]*)\]", raw_line)
    if not owner_key or not tokens_match:
        return None
    levels: dict[str, int] = {}
    for token in tokens_match.group(1).split():
        skill_id, _, level_text = token.rpartition(":")
        level = _coerce_int(level_text, default=0)
        if not skill_id or level <= 0:
            continue
        if _is_generic_runtime_skill_id(skill_id) or re.fullmatch(r".*_skill_\d+", skill_id) or skill_id.isdigit():
            resolved = _canonical_num_table_skill_id(skill_id, owner_key)
            if not resolved:
                continue
            skill_id = resolved
        levels[skill_id] = level
    if not levels:
        return None
    return owner_key, levels


def extract_char_skill_levels_from_text(text: str) -> dict[str, dict[str, int]]:
    """全文提取 CHAR_SKILLS（bridge 在战前落盘，可能在 battle 分段之外——
    与 _raw_text_loadout_entries 同理由 uploader 对整个 trace 调用）。同角色取最后一次。"""
    result: dict[str, dict[str, int]] = {}
    for raw_line in text.splitlines():
        if " CHAR_SKILLS " not in raw_line:
            continue
        parsed = _parse_char_skills_line(raw_line)
        if parsed is not None:
            result[parsed[0]] = parsed[1]
    return result


def _canonical_num_table_buff_number(buff_number: str | None, character_key: str | None) -> str | None:
    if not buff_number:
        return None
    static_id = _load_num_id_str_buff_map().get(str(buff_number))
    if not static_id:
        return None
    if not _runtime_owner_matches_static_domain(character_key, static_id):
        return None
    if not character_key:
        return static_id
    match = _CHAR_KEY_RE.search(static_id)
    if match and not _character_key_matches_static_family(str(character_key), match.group(1)):
        return None
    return static_id


def _character_key_matches_static_family(character_key: str | None, static_character_key: str | None) -> bool:
    character = str(character_key or "")
    static_character = str(static_character_key or "")
    if not character or not static_character:
        return True
    if character == static_character:
        return True
    if character == "chr_9000_endmin" and static_character in _ENDMIN_VARIANTS:
        return True
    return False


def _runtime_owner_matches_static_domain(character_key: str | None, static_id: str | None) -> bool:
    owner = str(character_key or "")
    static = str(static_id or "")
    if not owner or not static:
        return True
    if owner.startswith("chr_") and _ENEMY_KEY_RE.search(static):
        return False
    if owner.startswith("eny_") and _CHAR_KEY_RE.search(static):
        return False
    return True


@lru_cache(maxsize=1)
def _load_canonical_skill_display_names() -> dict[str, str]:
    display_names: dict[str, str] = {}
    skill_map = _load_packet_numeric_skill_map()
    map_path = _repo_root() / "data" / "packet_semantics" / "skill_numeric_map.json"
    if map_path.exists():
        try:
            payload = json.loads(map_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        preserved = payload.get("canonical_display_names") if isinstance(payload, dict) else {}
        if isinstance(preserved, dict):
            for canonical_skill_id, display_name in preserved.items():
                canonical_text = str(canonical_skill_id or "").strip()
                display_text = str(display_name or "").strip()
                if not canonical_text or not display_text:
                    continue
                existing = display_names.get(canonical_text, "")
                if not existing or len(display_text) > len(existing):
                    display_names[canonical_text] = display_text
    for mapping in skill_map.values():
        canonical_skill_id = str(mapping.get("canonical_skill_id") or "")
        display_name = str(mapping.get("display_name") or "").strip()
        if not canonical_skill_id or not display_name:
            continue
        existing = display_names.get(canonical_skill_id, "")
        if not existing or len(display_name) > len(existing):
            display_names[canonical_skill_id] = display_name
    return display_names


def _runtime_skill_number(skill_key: str | None) -> str | None:
    raw_skill_key = str(skill_key or "")
    match = _RUNTIME_SKILL_ID_RE.match(raw_skill_key)
    if match:
        return match.group(1)
    match = _COMPOSITE_RUNTIME_SKILL_RE.match(raw_skill_key)
    if match:
        return match.group(2)
    return None


def _is_runtime_numeric_skill_id(skill_key: str | None) -> bool:
    text = str(skill_key or "")
    return bool(re.fullmatch(r"skill_\d+", text) or re.search(r"_skill_\d+$", text))


def _canonical_packet_skill_id(skill_key: str | None) -> str:
    raw_skill_key = str(skill_key or "")
    hint = _packet_numeric_skill_hint(raw_skill_key)
    canonical = hint.get("canonical_skill_id")
    return str(canonical or raw_skill_key)


def _canonical_hit_skill_id(skill_key: str | None, character_key: str | None) -> str:
    raw_skill_key = str(skill_key or "")
    direct = _canonical_packet_skill_id(raw_skill_key)
    if direct != raw_skill_key:
        return direct
    skill_number = _runtime_skill_number(raw_skill_key)
    if skill_number and character_key:
        composite_key = f"{character_key}_skill_{skill_number}"
        composite = _canonical_packet_skill_id(composite_key)
        if composite != composite_key:
            return composite
    num_table_skill = _canonical_num_table_skill_id(raw_skill_key, character_key)
    if num_table_skill:
        return num_table_skill
    return raw_skill_key


def _canonical_runtime_buff_skill_id(skill_key: str | None, character_key: str | None) -> str | None:
    skill_number = _runtime_skill_number(skill_key)
    canonical_buff_id = _canonical_num_table_buff_number(skill_number, character_key)
    if not canonical_buff_id:
        return None
    if canonical_buff_id.startswith(f"buff_{character_key}_"):
        if any(token in canonical_buff_id for token in ("damage", "bleed", "effect", "trigger", "airborne", "break")):
            return canonical_buff_id
    if canonical_buff_id.startswith(("buff_common_", "buff_physical_", "buff_fire_", "buff_pulse_", "buff_cryst_", "buff_natural_")):
        if any(token in canonical_buff_id for token in ("trigger", "airborne", "break", "damage")):
            return canonical_buff_id
    return None


@lru_cache(maxsize=1)
def _load_local_skill_semantic_entries() -> dict[str, dict[str, Any]]:
    details_path = _repo_root() / "data" / "local_semantics" / "skill" / "details.json"
    if not details_path.exists():
        return {}
    try:
        payload = json.loads(details_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    entries = payload.get("entries")
    if not isinstance(entries, dict):
        return {}
    return {
        str(skill_id): entry
        for skill_id, entry in entries.items()
        if isinstance(entry, dict)
    }


@lru_cache(maxsize=4096)
def _related_child_buff_ids(buff_id: str) -> set[str]:
    ids: set[str] = set()
    entry = _load_local_buff_semantic_entries().get(str(buff_id or ""))
    if isinstance(entry, dict):
        ids.update(str(value) for value in entry.get("createdBuffIds") or [] if str(value or ""))
        ids.update(str(value) for value in entry.get("referencedBuffIds") or [] if str(value or ""))
    hint = _buff_classifier_hint(str(buff_id or "")) or {}
    ids.update(str(value) for value in hint.get("createdBuffIds") or [] if str(value or ""))
    ids.update(str(value) for value in hint.get("referencedBuffIds") or [] if str(value or ""))
    return ids


@lru_cache(maxsize=4096)
def _skill_related_buff_ids(skill_id: str) -> set[str]:
    ids: set[str] = set()
    entry = _load_local_skill_semantic_entries().get(str(skill_id or ""))
    if isinstance(entry, dict):
        ids.update(str(value) for value in entry.get("createdBuffIds") or [] if str(value or ""))
        ids.update(str(value) for value in entry.get("referencedBuffIds") or [] if str(value or ""))
    return ids


@lru_cache(maxsize=16384)
def _buff_semantically_reaches_buff(source_buff_id: str, target_buff_id: str, max_depth: int = 3) -> bool:
    source = str(source_buff_id or "")
    target = str(target_buff_id or "")
    if not source or not target:
        return False
    if source == target:
        return True
    frontier = set(_related_child_buff_ids(source))
    seen = set(frontier)
    depth = 0
    while frontier and depth < max_depth:
        if target in frontier:
            return True
        next_frontier: set[str] = set()
        for buff_id in frontier:
            next_frontier.update(_related_child_buff_ids(buff_id))
        next_frontier -= seen
        seen.update(next_frontier)
        frontier = next_frontier
        depth += 1
    return False


@lru_cache(maxsize=16384)
def _skill_semantically_reaches_buff(skill_id: str, target_buff_id: str, max_depth: int = 4) -> bool:
    skill = str(skill_id or "")
    target = str(target_buff_id or "")
    if not skill or not target:
        return False
    frontier = set(_skill_related_buff_ids(skill))
    seen = set(frontier)
    depth = 0
    while frontier and depth < max_depth:
        if target in frontier:
            return True
        next_frontier: set[str] = set()
        for buff_id in frontier:
            next_frontier.update(_related_child_buff_ids(buff_id))
        next_frontier -= seen
        seen.update(next_frontier)
        frontier = next_frontier
        depth += 1
    return False


def _derived_skill_id_from_origin_skill(origin_skill_id: str | None) -> str | None:
    origin = str(origin_skill_id or "")
    if not origin:
        return None
    if origin.endswith("_projhit"):
        return origin
    return f"{origin}_projhit"


def _runtime_skill_trigger_chain_mapping(
    skill_key: str | None,
    character_key: str | None,
    *,
    original_template_int_id: int | None,
    target_enemy_key: str | None,
    ts_ms: int,
    recent_numeric_buffs_by_source: dict[str, list[dict[str, Any]]],
    max_delta_ms: int = 1000,
) -> dict[str, Any] | None:
    skill_number = _runtime_skill_number(skill_key)
    if not skill_number or not character_key or original_template_int_id is None:
        return None
    trigger_buff_id = _canonical_num_table_buff_number(skill_number, character_key)
    if not trigger_buff_id or not trigger_buff_id.startswith(f"buff_{character_key}_"):
        return None
    if not any(token in trigger_buff_id for token in ("damage", "trigger")):
        return None
    origin_skill_id = _canonical_num_table_skill_number(str(original_template_int_id), character_key)
    if not origin_skill_id or not origin_skill_id.startswith(f"{character_key}_"):
        return None
    if not _skill_semantically_reaches_buff(origin_skill_id, trigger_buff_id):
        return None

    trigger_buff_evidence: dict[str, Any] | None = None
    for buff in reversed(recent_numeric_buffs_by_source.get(str(character_key), [])):
        delta_ms = ts_ms - int(buff.get("ts_ms") or 0)
        if delta_ms < -50:
            continue
        if delta_ms > max_delta_ms:
            break
        buff_target_enemy = str(buff.get("target_enemy_key") or "")
        if target_enemy_key and buff_target_enemy and buff_target_enemy != str(target_enemy_key):
            continue
        raw_event_key = str(buff.get("raw_event_key") or "")
        if not raw_event_key.isdigit():
            continue
        candidate_buff_id = _canonical_num_table_buff_number(raw_event_key, character_key)
        if not candidate_buff_id:
            continue
        if candidate_buff_id != trigger_buff_id and not _buff_semantically_reaches_buff(candidate_buff_id, trigger_buff_id):
            continue
        trigger_buff_evidence = {
            "raw_event_key": raw_event_key,
            "event_key": buff.get("event_key"),
            "line_no": buff.get("line_no"),
            "start_time": buff.get("time"),
            "delta_ms": delta_ms,
            "source_character_key": buff.get("source_character_key"),
            "target_enemy_key": buff.get("target_enemy_key"),
            "canonical_buff_id": candidate_buff_id,
        }
        break
    if trigger_buff_evidence is None:
        return None

    canonical_skill_id = _derived_skill_id_from_origin_skill(origin_skill_id)
    if not canonical_skill_id:
        return None
    return {
        "canonical_skill_id": canonical_skill_id,
        "origin_skill_id": origin_skill_id,
        "trigger_buff_id": trigger_buff_id,
        "trigger_buff_evidence": trigger_buff_evidence,
    }


def _same_frame_trigger_buff_for_runtime_skill(
    skill_key: str | None,
    character_key: str | None,
    ts_ms: int,
    *,
    target_enemy_key: str | None,
    recent_numeric_buffs_by_source: dict[str, list[dict[str, Any]]],
    max_delta_ms: int = 10,
) -> dict[str, Any] | None:
    skill_number = _runtime_skill_number(skill_key)
    if not skill_number or not character_key:
        return None
    for buff in reversed(recent_numeric_buffs_by_source.get(str(character_key), [])):
        delta_ms = ts_ms - int(buff.get("ts_ms") or 0)
        if delta_ms < -50:
            continue
        if delta_ms > 250:
            break
        raw_event_key = str(buff.get("raw_event_key") or "")
        if not raw_event_key.isdigit() or raw_event_key == skill_number:
            continue
        buff_target_enemy = str(buff.get("target_enemy_key") or "")
        if target_enemy_key and buff_target_enemy != str(target_enemy_key):
            continue
        if str(buff.get("event_key") or "") == "buff_common_vfx_char_atk_up":
            continue
        if str(buff.get("event_key") or "") == "buff_physical_handle_cryst_break":
            continue
        if delta_ms > max_delta_ms:
            continue
        if buff.get("bb_values") or buff.get("attr_mods"):
            continue
        return {
            "buff": buff,
            "delta_ms": delta_ms,
        }
    return None


def _same_frame_trigger_buff_from_buff_starts(
    skill_key: str | None,
    character_key: str | None,
    ts_ms: int,
    *,
    target_enemy_key: str | None,
    buff_starts: list[dict[str, Any]],
    max_delta_ms: int = 10,
) -> dict[str, Any] | None:
    skill_number = _runtime_skill_number(skill_key)
    if not skill_number or not character_key:
        return None
    candidates: list[dict[str, Any]] = []
    for buff in buff_starts:
        buff_ts_ms = int(buff.get("ts_ms") or -1)
        delta_ms = buff_ts_ms - ts_ms
        if delta_ms < 0 or delta_ms > max_delta_ms:
            continue
        raw_event_key = str(buff.get("raw_event_key") or buff.get("event_key") or "")
        is_numeric = raw_event_key.isdigit()
        event_key = str(buff.get("event_key") or "")
        is_static_trigger = bool(_STATIC_TRIGGER_DAMAGE_BUFF_RE.match(event_key))
        if is_numeric and raw_event_key == skill_number:
            continue
        if not is_numeric and not is_static_trigger:
            continue
        if str(buff.get("source_character_key") or "") != str(character_key):
            continue
        buff_target_enemy = str(buff.get("target_enemy_key") or "")
        if target_enemy_key and buff_target_enemy != str(target_enemy_key):
            continue
        if str(buff.get("event_key") or "") == "buff_common_vfx_char_atk_up":
            continue
        if buff.get("bb_values") or buff.get("attr_mods"):
            continue
        candidates.append(
            {
                "buff": buff,
                "delta_ms": delta_ms,
            }
        )
    if not candidates:
        return None
    candidates.sort(
        key=lambda item: (
            0
            if str((item.get("buff") or {}).get("event_key") or "") == "buff_common_cryst_triggered_physical_break"
            else 1,
            int(item.get("delta_ms") or 0),
        )
    )
    return candidates[0]


def _same_frame_damage_buff_from_buff_starts(
    hit: dict[str, Any],
    buff_starts: list[dict[str, Any]],
    *,
    max_delta_ms: int = 250,
) -> dict[str, Any] | None:
    raw_skill_key = str(hit.get("raw_skill_key") or hit.get("skill_key") or "")
    if not _runtime_skill_number(raw_skill_key):
        return None
    character_key = str(hit.get("character_key") or "")
    target_enemy_key = str(hit.get("target_enemy_key") or "")
    ts_ms = int(hit.get("ts_ms") or 0)
    hit_line_no = int(hit.get("line_no") or 0)
    action_id = hit.get("action_id")
    damage_unit_index = hit.get("damage_unit_index")
    candidates: list[dict[str, Any]] = []
    for buff in buff_starts:
        if str(buff.get("source_character_key") or "") != character_key:
            continue
        buff_target_enemy = str(buff.get("target_enemy_key") or "")
        if target_enemy_key and buff_target_enemy != target_enemy_key:
            continue
        buff_line_no = int(buff.get("line_no") or 0)
        if hit_line_no and buff_line_no and buff_line_no > hit_line_no:
            continue
        buff_ts_ms = int(buff.get("ts_ms") or 0)
        delta_ms = ts_ms - buff_ts_ms
        if delta_ms < 0 or delta_ms > max_delta_ms:
            continue
        event_key = str(buff.get("event_key") or "")
        if not event_key.startswith("buff_"):
            continue
        action_element = _infer_skill_action_damage_element(event_key, action_id, damage_unit_index)
        if action_element is None:
            continue
        candidates.append(
            {
                "buff": buff,
                "delta_ms": delta_ms,
                "action_element": action_element,
            }
        )
    if not candidates:
        return None
    candidates.sort(
        key=lambda item: (
            int(item.get("delta_ms") or 0),
            -int((item.get("buff") or {}).get("line_no") or 0),
        )
    )
    return candidates[0]


def _trigger_damage_identity_from_buff(
    buff: dict[str, Any],
    *,
    damage_element: str | None,
    target_enemy_key: str | None,
    nearby_buffs: list[dict[str, Any]] | None = None,
) -> tuple[str, str]:
    event_key = str(buff.get("event_key") or "")
    raw_event_key = str(buff.get("raw_event_key") or event_key or "unknown")
    source_key = str(buff.get("source_character_key") or "")
    element_label = _ELEMENT_LABELS.get(str(damage_element or ""), str(damage_element or "元素"))
    bb_values = {str(key).lower(): value for key, value in (buff.get("bb_values") or {}).items()}

    if event_key == "buff_physical_no_guard":
        return event_key, "破防"
    if event_key == "buff_physical_knockdown":
        return event_key, "倒地"
    if event_key == "buff_physical_crushed":
        return event_key, "猛击"
    if event_key == "buff_physical_airborne":
        return event_key, "击飞"
    if event_key == "buff_common_cryst_triggered_physical_break":
        return event_key, "猛击"
    if event_key == "buff_common_originum_frozen":
        return event_key, "源石冻结"
    if event_key == "buff_common_enemy_spell_status_do_frozen":
        if "physical_res_down" in bb_values or "phy_resist_down" in bb_values:
            return event_key, "碎甲" if source_key == "chr_0029_pograni" else "物理脆弱"
        if "spell_resistance_decrease" in bb_values or "final_spell_resistance_decrease" in bb_values:
            return event_key, "导电"
        if (
            "def_decrease" in bb_values
            or "max_def_decrease" in bb_values
            or "additional_def_decrease" in bb_values
            or "all_resistance_decrease" in bb_values
        ):
            return event_key, "腐蚀"
        return event_key, "冻结"
    if event_key == "buff_physical_handle_cryst_break":
        for other in nearby_buffs or []:
            if other is buff:
                continue
            if str(other.get("source_character_key") or "") != source_key:
                continue
            if str(other.get("target_enemy_key") or "") != str(target_enemy_key or ""):
                continue
            other_key = str(other.get("event_key") or "")
            other_bb_values = {str(key).lower(): value for key, value in (other.get("bb_values") or {}).items()}
            if other_key == "buff_common_enemy_spell_status_do_frozen" and (
                "physical_res_down" in other_bb_values or "phy_resist_down" in other_bb_values
            ):
                return other_key, "碎甲" if source_key == "chr_0029_pograni" else "物理脆弱"
        return event_key, f"{element_label}触发伤害"

    resolved_name = _resolve_skill_name(event_key) if event_key.startswith("buff_") else None
    if resolved_name and resolved_name != "触发伤害":
        return event_key, resolved_name
    return f"numeric_buff_trigger_{raw_event_key}", f"{element_label}触发伤害"


def _apply_same_frame_trigger_skill_mappings(
    hits: list[dict[str, Any]],
    buff_starts: list[dict[str, Any]],
) -> None:
    confirmed_trigger_by_runtime_number: dict[str, tuple[str, str]] = {}
    for hit in hits:
        current_skill_key = str(hit.get("skill_key") or "")
        raw_skill_key = str(hit.get("raw_skill_key") or current_skill_key)
        if not re.search(r"_skill_\d+$", raw_skill_key):
            continue
        damage_buff_evidence = _same_frame_damage_buff_from_buff_starts(hit, buff_starts)
        if damage_buff_evidence is not None:
            buff = damage_buff_evidence["buff"]
            delta_ms = int(damage_buff_evidence["delta_ms"])
            action_element = str(damage_buff_evidence.get("action_element") or "")
            canonical_skill_id, display_name = _trigger_damage_identity_from_buff(
                buff,
                damage_element=action_element,
                target_enemy_key=str(hit.get("target_enemy_key") or ""),
                nearby_buffs=buff_starts,
            )
            raw_skill_number = _runtime_skill_number(raw_skill_key)
            hit["raw_skill_key"] = raw_skill_key
            hit["skill_key"] = canonical_skill_id
            hit["skill_name"] = display_name
            hit["skill_group_type"] = None
            hit["skill_family_key"] = canonical_skill_id
            hit["damage_element"] = action_element or hit.get("damage_element")
            hit["damage_school"] = _damage_school_from_element(action_element) or hit.get("damage_school")
            if raw_skill_number:
                confirmed_trigger_by_runtime_number[raw_skill_number] = (canonical_skill_id, display_name)
            mapping = hit.get("skill_mapping")
            if isinstance(mapping, dict):
                mapping.update(
                    {
                        "status": "mapped",
                        "status_label": "已映射",
                        "canonical_skill_id": canonical_skill_id,
                        "display_name": display_name,
                        "confidence": "same_frame_damage_buff_action",
                        "reason": "runtime hit shares the same timestamp with a same-source same-target damage BUFF_START whose static action damage unit matches this HP_V2 actionId/damageUnitIndex",
                        "trigger_buff": {
                            "raw_event_key": buff.get("raw_event_key"),
                            "event_key": buff.get("event_key"),
                            "line_no": buff.get("line_no"),
                            "start_time": buff.get("time"),
                            "delta_ms": delta_ms,
                            "source_character_key": buff.get("source_character_key"),
                            "target_enemy_key": buff.get("target_enemy_key"),
                        },
                    }
                )
            continue
        if not re.search(r"_skill_\d+$", current_skill_key):
            continue
        mapping = hit.get("skill_mapping")
        if isinstance(mapping, dict) and str(mapping.get("status") or "") not in {"unmapped", "candidate"}:
            continue
        evidence = _same_frame_trigger_buff_from_buff_starts(
            raw_skill_key,
            str(hit.get("character_key") or ""),
            int(hit.get("ts_ms") or 0),
            target_enemy_key=str(hit.get("target_enemy_key") or ""),
            buff_starts=buff_starts,
        )
        if evidence is None:
            continue
        buff = evidence["buff"]
        delta_ms = int(evidence["delta_ms"])
        buff_number = str(buff.get("raw_event_key") or buff.get("event_key") or "")
        canonical_skill_id, display_name = _trigger_damage_identity_from_buff(
            buff,
            damage_element=str(hit.get("damage_element") or ""),
            target_enemy_key=str(hit.get("target_enemy_key") or ""),
            nearby_buffs=buff_starts,
        )
        raw_skill_number = _runtime_skill_number(raw_skill_key)
        hit["raw_skill_key"] = raw_skill_key
        hit["skill_key"] = canonical_skill_id
        hit["skill_name"] = display_name
        hit["skill_group_type"] = None
        hit["skill_family_key"] = canonical_skill_id
        if raw_skill_number:
            confirmed_trigger_by_runtime_number[raw_skill_number] = (canonical_skill_id, display_name)
        if isinstance(mapping, dict):
            mapping.update(
                {
                    "status": "mapped",
                    "status_label": "已映射",
                    "canonical_skill_id": canonical_skill_id,
                    "display_name": display_name,
                    "confidence": "same_frame_trigger_buff",
                    "reason": "runtime hit shares the same timestamp with a same-source same-target trigger BUFF_START that has no blackboard or attr evidence; treated as triggered/status damage",
                    "trigger_buff": {
                        "raw_event_key": buff.get("raw_event_key"),
                        "event_key": buff.get("event_key"),
                        "line_no": buff.get("line_no"),
                        "start_time": buff.get("time"),
                        "delta_ms": delta_ms,
                        "source_character_key": buff.get("source_character_key"),
                        "target_enemy_key": buff.get("target_enemy_key"),
                    },
                }
            )
    for hit in hits:
        current_skill_key = str(hit.get("skill_key") or "")
        if not re.search(r"_skill_\d+$", current_skill_key):
            continue
        mapping = hit.get("skill_mapping")
        if not isinstance(mapping, dict) or str(mapping.get("status") or "") not in {"unmapped", "candidate"}:
            continue
        raw_skill_key = str(hit.get("raw_skill_key") or current_skill_key)
        runtime_number = _runtime_skill_number(raw_skill_key)
        if not runtime_number:
            continue
        shared = confirmed_trigger_by_runtime_number.get(runtime_number)
        if shared is None:
            continue
        synthetic_skill_key, display_name = shared
        hit["raw_skill_key"] = raw_skill_key
        hit["skill_key"] = synthetic_skill_key
        hit["skill_name"] = display_name
        hit["skill_group_type"] = None
        hit["skill_family_key"] = synthetic_skill_key
        action_element = _infer_skill_action_damage_element(
            synthetic_skill_key,
            hit.get("action_id"),
            hit.get("damage_unit_index"),
        )
        if action_element:
            hit["damage_element"] = action_element
            hit["damage_school"] = _damage_school_from_element(action_element) or hit.get("damage_school")
        mapping.update(
            {
                "status": "mapped",
                "status_label": "已映射",
                "canonical_skill_id": synthetic_skill_key,
                "display_name": display_name,
                "confidence": "shared_runtime_trigger_number",
                "reason": "same runtime skill number was already confirmed elsewhere in this battle as triggered/status damage",
            }
        )


def _canonical_hit_skill_id_from_cast_context(
    skill_key: str | None,
    character_key: str | None,
    ts_ms: int,
    *,
    original_template_int_id: int | None = None,
    target_enemy_key: str | None,
    recent_skill_casts_by_char: dict[str, list[dict[str, Any]]],
    recent_numeric_buffs_by_source: dict[str, list[dict[str, Any]]],
) -> str | None:
    raw_skill_key = str(skill_key or "")
    skill_number = _runtime_skill_number(raw_skill_key)
    if not skill_number or not character_key:
        return None
    same_number_buff_delta_ms: int | None = None
    for buff in reversed(recent_numeric_buffs_by_source.get(str(character_key), [])):
        delta_ms = ts_ms - int(buff.get("ts_ms") or 0)
        if delta_ms < -50:
            continue
        if delta_ms > 20000:
            break
        if str(buff.get("raw_event_key") or "") != skill_number:
            continue
        buff_target_enemy = str(buff.get("target_enemy_key") or "")
        if target_enemy_key and buff_target_enemy != str(target_enemy_key):
            continue
        same_number_buff_delta_ms = delta_ms
        break
    trigger_chain = _runtime_skill_trigger_chain_mapping(
        raw_skill_key,
        character_key,
        original_template_int_id=original_template_int_id,
        target_enemy_key=target_enemy_key,
        ts_ms=ts_ms,
        recent_numeric_buffs_by_source=recent_numeric_buffs_by_source,
    )
    if trigger_chain is not None:
        return str(trigger_chain.get("canonical_skill_id") or "")
    runtime_buff_skill = _canonical_runtime_buff_skill_id(raw_skill_key, character_key)
    if runtime_buff_skill:
        return runtime_buff_skill
    trigger_buff = _same_frame_trigger_buff_for_runtime_skill(
        raw_skill_key,
        character_key,
        ts_ms,
        target_enemy_key=target_enemy_key,
        recent_numeric_buffs_by_source=recent_numeric_buffs_by_source,
    )
    if trigger_buff is not None:
        buff = trigger_buff["buff"]
        canonical_skill_id, _ = _trigger_damage_identity_from_buff(
            buff,
            damage_element=None,
            target_enemy_key=target_enemy_key,
        )
        return canonical_skill_id
    for cast in reversed(recent_skill_casts_by_char.get(str(character_key), [])):
        delta_ms = ts_ms - int(cast.get("ts_ms") or 0)
        if delta_ms < -50:
            continue
        if delta_ms > 12000:
            break
        cast_skill = str(cast.get("skill") or "")
        if not cast_skill or _is_runtime_numeric_skill_id(cast_skill):
            continue
        if same_number_buff_delta_ms is None or same_number_buff_delta_ms <= 150:
            return cast_skill
    trigger_chain = _runtime_skill_trigger_chain_mapping(
        raw_skill_key,
        character_key,
        original_template_int_id=original_template_int_id,
        target_enemy_key=target_enemy_key,
        ts_ms=ts_ms,
        recent_numeric_buffs_by_source=recent_numeric_buffs_by_source,
    )
    if trigger_chain is not None:
        return str(trigger_chain.get("canonical_skill_id") or "")
    runtime_buff_skill = _canonical_runtime_buff_skill_id(raw_skill_key, character_key)
    if runtime_buff_skill:
        return runtime_buff_skill
    trigger_buff = _same_frame_trigger_buff_for_runtime_skill(
        raw_skill_key,
        character_key,
        ts_ms,
        target_enemy_key=target_enemy_key,
        recent_numeric_buffs_by_source=recent_numeric_buffs_by_source,
    )
    if trigger_buff is not None:
        buff = trigger_buff["buff"]
        canonical_skill_id, _ = _trigger_damage_identity_from_buff(
            buff,
            damage_element=None,
            target_enemy_key=target_enemy_key,
        )
        return canonical_skill_id
    return None


def _recent_source_skill_context_for_buff(
    source_key: str | None,
    ts_ms: int,
    recent_skill_casts_by_char: dict[str, list[dict[str, Any]]],
) -> dict[str, str] | None:
    if not source_key:
        return None
    for cast in reversed(recent_skill_casts_by_char.get(str(source_key), [])):
        delta_ms = ts_ms - int(cast.get("ts_ms") or 0)
        if delta_ms < -50:
            continue
        if delta_ms > 12000:
            break
        skill_key = str(cast.get("skill") or "")
        if not skill_key:
            continue
        canonical_skill = _canonical_packet_skill_id(skill_key)
        skill_profile = _resolve_skill_profile(canonical_skill)
        return {
            "source_skill_key": canonical_skill,
            "source_skill_family_key": _resolve_skill_family_key(canonical_skill, skill_profile),
        }
    return None


@lru_cache(maxsize=1)
def _load_local_buff_semantic_entries() -> dict[str, dict[str, Any]]:
    details_path = _repo_root() / "data" / "local_semantics" / "buff" / "details.json"
    if not details_path.exists():
        return {}
    try:
        payload = json.loads(details_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    entries = payload.get("entries")
    if not isinstance(entries, dict):
        return {}
    return {
        str(buff_id): entry
        for buff_id, entry in entries.items()
        if isinstance(entry, dict)
    }


@lru_cache(maxsize=16384)
def _buff_child_family_ids(buff_id: str) -> set[str]:
    seen: set[str] = set()
    frontier = [str(buff_id or "")]
    entries = _load_local_buff_semantic_entries()
    while frontier:
        current = frontier.pop()
        if not current or current in seen:
            continue
        seen.add(current)
        entry = entries.get(current)
        if not isinstance(entry, dict):
            continue
        for field in ("createdBuffIds", "referencedBuffIds", "binaryCreatedBuffIds", "binaryReferencedBuffIds"):
            for child in entry.get(field) or []:
                child_id = str(child or "")
                if child_id and child_id not in seen:
                    frontier.append(child_id)
    return seen


@lru_cache(maxsize=1)
def _load_equip_suit_allowed_buffs() -> dict[str, set[str]]:
    skill_entries = _load_local_skill_semantic_entries()
    equip_root = _repo_root() / "data" / "local_tables" / "equip" / "items"
    result: dict[str, set[str]] = {}
    if not equip_root.is_dir():
        return result
    for path in sorted(equip_root.glob("suit_*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        suit_id = str(payload.get("suitID") or "")
        passive_skill_id = str(payload.get("passiveSkillId") or "")
        if not suit_id or not passive_skill_id:
            continue
        entry = skill_entries.get(passive_skill_id)
        if not isinstance(entry, dict):
            continue
        root_buffs = {
            str(buff_id or "")
            for field in ("createdBuffIds", "referencedBuffIds", "binaryCreatedBuffIds", "binaryReferencedBuffIds")
            for buff_id in (entry.get(field) or [])
            if str(buff_id or "").startswith("buff_equipsuit_")
        }
        allowed: set[str] = set()
        for buff_id in root_buffs:
            allowed.update(_buff_child_family_ids(buff_id))
        if allowed:
            result[suit_id] = allowed
    return result


def _equip_buff_matches_active_suits(
    event_key: str | None,
    source_key: str | None,
    active_suits_by_char: dict[str, set[str]] | None,
) -> bool:
    buff_id = str(event_key or "")
    if not buff_id.startswith("buff_equipsuit_"):
        return True
    source = str(source_key or "")
    if not source or not isinstance(active_suits_by_char, dict):
        return True
    if not active_suits_by_char:
        return True
    if source not in active_suits_by_char:
        # Character trials and squad swaps can emit equipment buff packets
        # without a matching LOADOUT row for the replacement character.
        return True
    active_suits = set(active_suits_by_char.get(source) or set())
    if not active_suits:
        return False
    allowed_by_suit = _load_equip_suit_allowed_buffs()
    for suit_id in active_suits:
        if buff_id in allowed_by_suit.get(str(suit_id), set()):
            return True
    return False


def _weapon_buff_matches_active_weapon(
    event_key: str | None,
    source_key: str | None,
    active_weapons_by_char: dict[str, str] | None,
) -> bool:
    buff_id = str(event_key or "")
    if not _WEAPON_BUFF_RE.match(buff_id):
        return True
    source = str(source_key or "")
    if not source or not isinstance(active_weapons_by_char, dict):
        return True
    if not active_weapons_by_char:
        return True
    active_weapon = active_weapons_by_char.get(source)
    if not active_weapon:
        # Character trials and squad swaps can emit weapon buff packets before a
        # matching LOADOUT_STATS row exists for the new source character.
        return True
    hint = _packet_numeric_buff_hint(buff_id)
    weapon_id = str(hint.get("weapon_id") or "")
    if not weapon_id:
        match = _WEAPON_ID_FROM_BUFF_RE.match(buff_id)
        weapon_id = match.group(1) if match else ""
    return not weapon_id or weapon_id == active_weapon


def _buff_decoded_detail_path(buff_id: str) -> Path | None:
    entry = _load_local_buff_semantic_entries().get(str(buff_id or ""))
    if not isinstance(entry, dict):
        return None
    source = entry.get("source") if isinstance(entry.get("source"), dict) else {}
    path_text = str(source.get("decodedDetailPath") or "")
    if path_text:
        path = _repo_root() / path_text
        if path.is_file():
            return path
    fallback = _repo_root() / "data" / "akedata" / "buff" / "items" / f"{buff_id}.json"
    return fallback if fallback.is_file() else None


def _normalize_condition_damage_type(value: Any) -> str | None:
    lowered = str(value or "").strip().lower()
    if lowered in {"physical", "physic"}:
        return "physical"
    if lowered in {"fire", "pulse", "cryst", "crystal", "natural"}:
        return "cryst" if lowered == "crystal" else lowered
    return None


@lru_cache(maxsize=4096)
def _decoded_damage_modifier_condition_rows(buff_id: str) -> dict[int, dict[str, Any]]:
    path = _buff_decoded_detail_path(buff_id)
    if path is None:
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    modifiers = payload.get("damageModifier")
    if not isinstance(modifiers, list):
        return {}

    rows: dict[int, dict[str, Any]] = {}
    for index, modifier in enumerate(modifiers):
        if not isinstance(modifier, dict):
            continue
        condition = modifier.get("condition") if isinstance(modifier.get("condition"), dict) else {}
        action_data = condition.get("actionData") if isinstance(condition, dict) else []
        damage_types: set[str] = set()
        condition_buff_ids: set[str] = set()
        for action in action_data or []:
            if not isinstance(action, dict):
                continue
            action_type = str(action.get("$type") or "")
            if "CheckDamageType" in action_type:
                damage_type = _normalize_condition_damage_type(action.get("damageType"))
                if damage_type:
                    damage_types.add(damage_type)
            if "CheckBuffStackNumAdvanced" in action_type:
                buff_settings = action.get("buffSettings") if isinstance(action.get("buffSettings"), dict) else {}
                for buff_id_value in buff_settings.get("buffIdList") or []:
                    normalized = _normalize_buff_id(buff_id_value)
                    if normalized:
                        condition_buff_ids.add(normalized)
        if damage_types or condition_buff_ids:
            rows[index] = {
                "damage_types": tuple(sorted(damage_types)),
                "condition_buff_ids": tuple(sorted(condition_buff_ids)),
            }
    return rows


def _walk_enhanced_action_child_specs(payload: Any, *, target_child_buff_id: str) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            type_name = str(node.get("$type") or "")
            if "EnhancedAction+Data" in type_name:
                child_buff = node.get("childBuffId") if isinstance(node.get("childBuffId"), dict) else {}
                child_buff_id = str(child_buff.get("value") or "")
                subtype = str(node.get("subType") or "").lower()
                element = _ENHANCED_ACTION_SUBTYPE_TO_ELEMENT.get(subtype)
                if (
                    node.get("asChildBuff")
                    and child_buff_id == target_child_buff_id
                    and element
                ):
                    rate_cfg = node.get("rate") if isinstance(node.get("rate"), dict) else {}
                    specs.append(
                        {
                            "zone": "amp",
                            "element": element,
                            "bb_key": str(rate_cfg.get("blackboardKey") or ""),
                            # Child buff instances often carry the copied rate under a plain runtime `rate` key.
                            "prefer_runtime_rate_key": "rate",
                        }
                    )
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(payload)
    return specs


@lru_cache(maxsize=4096)
def _enhanced_action_child_effect_specs(buff_id: str) -> list[dict[str, Any]]:
    target_child_buff_id = str(buff_id or "")
    if not target_child_buff_id:
        return []
    reverse_parents: set[str] = set()
    for parent_buff_id, entry in _load_local_buff_semantic_entries().items():
        if not isinstance(entry, dict):
            continue
        referenced = {
            str(value)
            for value in entry.get("referencedBuffIds") or []
            if str(value or "")
        }
        if target_child_buff_id in referenced:
            reverse_parents.add(str(parent_buff_id))
    specs: list[dict[str, Any]] = []
    for parent_buff_id in sorted(reverse_parents):
        path = _buff_decoded_detail_path(parent_buff_id)
        if path is None:
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        specs.extend(_walk_enhanced_action_child_specs(payload, target_child_buff_id=target_child_buff_id))
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for spec in specs:
        key = (
            str(spec.get("zone") or ""),
            str(spec.get("element") or ""),
            str(spec.get("bb_key") or ""),
            str(spec.get("prefer_runtime_rate_key") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(spec)
    return deduped


def _semantic_entry_bb_keys(entry: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for item in entry.get("blackboard") or []:
        if not isinstance(item, dict):
            continue
        key = item.get("key")
        if isinstance(key, str) and key:
            keys.add(key)
    return keys


def _semantic_entry_has_rdps(entry: dict[str, Any]) -> bool:
    flags = entry.get("semanticFlags") if isinstance(entry.get("semanticFlags"), dict) else {}
    counts = entry.get("modifierCounts") if isinstance(entry.get("modifierCounts"), dict) else {}
    probe = entry.get("binaryProbe") if isinstance(entry.get("binaryProbe"), dict) else {}
    return bool(
        flags.get("hasTemplateModifiers")
        or flags.get("hasAttributeModifier")
        or flags.get("hasDamageModifier")
        or counts.get("attribute")
        or counts.get("damage")
        or probe.get("rdpsCandidate")
    )


def _char_prefix(value: Any) -> str | None:
    match = re.match(r"^(chr_\d{4})_", str(value or ""))
    return match.group(1) if match else None


_PACKET_RDPS_BB_KEY_HINTS = {
    "atk_up",
    "atk_up2",
    "crit_up",
    "crit_up2",
    "crit_dmg_up",
    "def_decrease",
    "def_decrease_tick",
    "def_decrease_tick_final",
    "dmg_up",
    "fire_dmg_up",
    "ignore_fire_resist",
    "max_def_decrease",
    "max_def_decrease_final",
    "normal_atk_up_valid",
    "pd_up",
    "phy_dmg_up",
    "phy_dmg_up2",
    "spell_damage_taken_up",
    "spell_dmg_up",
    "spell_taken_up",
    "spell_up",
    "start_def_decrease",
}
_PACKET_UTILITY_BB_KEY_HINTS = {
    "atb",
    "atk_duration",
    "cd",
    "comboskill_cooldown",
    "common_character_perfect_dodge",
    "count",
    "damage_interval",
    "duration",
    "dodgeSkillId",
    "heal_value",
    "healvalue",
    "hp_up",
    "lv",
    "max_stack",
    "poise",
    "posie",
    "probability",
    "ratio",
    "shelter",
    "skill_bg_type",
    "speed",
    "vfx_buff_name",
}


def _packet_bb_key_has_rdps_shape(key: str) -> bool:
    lowered = key.lower()
    if lowered in _PACKET_RDPS_BB_KEY_HINTS:
        return True
    if any(token in lowered for token in ("def_decrease", "resist", "taken_up", "vulnerable", "fragile")):
        return True
    if any(token in lowered for token in ("dmg_up", "damage_up", "spell_up", "atk_up", "crit")):
        return True
    return lowered.startswith("ignore_") and ("res" in lowered or "def" in lowered)


def _is_internal_trigger_damage_record(record: dict[str, Any]) -> bool:
    raw_buff_id = _normalize_buff_id(record.get("raw_event_key") or record.get("event_key"))
    if not raw_buff_id.isdigit():
        return False
    bb_keys = {str(key).lower() for key in record.get("bb_keys") or []}
    bb_keys.update(str(key).lower() for key in (record.get("bb_values") or {}).keys())
    trigger_keys = {"phy_dmg_up", "final_phy_dmg_up", "shatter_dmg", "consumed_layer"}
    if not trigger_keys.issubset(bb_keys):
        return False
    owner = str(record.get("owner_raw") or record.get("target_character_key") or record.get("target_enemy_key") or "")
    source = str(record.get("raw_source") or record.get("source_character_key") or "")
    return owner.startswith("eny_") and source.startswith("chr_")


def _classify_packet_buff_record(record: dict[str, Any]) -> dict[str, Any]:
    raw_buff_id = _normalize_buff_id(record.get("raw_event_key") or record.get("event_key"))
    mapping = record.get("packet_mapping")
    if isinstance(mapping, dict):
        return {
            "status": "mapped",
            "class": str(mapping.get("role") or "mapped"),
            "label": "已接受映射",
            "reason": str(mapping.get("reason") or ""),
        }
    if not raw_buff_id.isdigit():
        return {
            "status": "static_id",
            "class": "static",
            "label": "静态 ID",
            "reason": "buff id is already a static string id",
        }
    owner = str(record.get("owner_raw") or record.get("target_character_key") or record.get("target_enemy_key") or "")
    source = str(record.get("raw_source") or record.get("source_character_key") or "")
    if not any(value.startswith(("chr_", "eny_")) for value in (owner, source)):
        return {
            "status": "unmapped",
            "class": "orphan_actor",
            "label": "孤立 actor",
            "reason": "numeric buff has no character/enemy owner or source context",
        }
    bb_keys = {str(key) for key in record.get("bb_keys") or []}
    bb_keys.update(str(key) for key in (record.get("bb_values") or {}).keys())
    if _is_internal_trigger_damage_record(record):
        return {
            "status": "unmapped",
            "class": "utility_or_marker",
            "label": "内部触发窗",
            "reason": "numeric buff matches common cryst-triggered helper keys and should not be treated as an external damage buff",
        }
    rdps_keys = sorted(key for key in bb_keys if _packet_bb_key_has_rdps_shape(key))
    if rdps_keys:
        return {
            "status": "unmapped",
            "class": "rdps_effect",
            "label": "疑似 rDPS 效果",
            "reason": "numeric buff has rDPS-shaped blackboard keys: " + ", ".join(rdps_keys),
        }
    if bb_keys:
        utility_keys = {key for key in bb_keys if key.lower() in _PACKET_UTILITY_BB_KEY_HINTS}
        if utility_keys == bb_keys:
            return {
                "status": "unmapped",
                "class": "utility_or_marker",
                "label": "工具/标记",
                "reason": "only utility blackboard keys were observed",
            }
        return {
            "status": "unmapped",
            "class": "unknown_blackboard",
            "label": "未知黑板",
            "reason": "blackboard keys exist but do not match accepted rDPS patterns",
        }
    return {
        "status": "unmapped",
        "class": "no_blackboard",
        "label": "无黑板",
        "reason": "numeric buff carried no blackboard values in this trace",
    }


_CLASSIFIER_ZONE_TO_INTERNAL = {
    "ATK": "atk",
    "CRIT": "crit",
    "CRIT_RATE": "crit",
    "DMG_INC": "dmg_inc",
    "AMP": "amp",
    "FRAGILE": "fragile",
    "VULN_TAKEN": "vuln_taken",
    "RES": "res",
    "COMBO": "combo",
    "UTILITY": "utility",
}


def _classifier_zone_to_internal(zone: Any) -> str | None:
    return _CLASSIFIER_ZONE_TO_INTERNAL.get(str(zone or "").strip().upper())


def _packet_record_effect_pairs(record: dict[str, Any]) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for effect in (record.get("zone_effects") or []):
        if not isinstance(effect, dict):
            continue
        zone = str(effect.get("zone") or "").strip()
        if not zone:
            continue
        pairs.add((zone, _normalize_effect_element(effect.get("element"))))
    for effect in (record.get("dynamic_effects") or []):
        if not isinstance(effect, dict):
            continue
        zone = str(effect.get("zone") or "").strip()
        if not zone:
            continue
        pairs.add((zone, _normalize_effect_element(effect.get("element"))))
    return pairs


def _classifier_hint_effect_pairs(hint: dict[str, Any]) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for effect in hint.get("resolvedEffectHints") or hint.get("effectHints") or []:
        if not isinstance(effect, dict):
            continue
        zone = _classifier_zone_to_internal(effect.get("zone"))
        if zone in (None, "utility"):
            continue
        pairs.add((zone, _normalize_effect_element(effect.get("element"))))
    return pairs


def _packet_buff_semantic_candidates(record: dict[str, Any], *, limit: int = 5) -> list[dict[str, Any]]:
    raw_buff_id = _normalize_buff_id(record.get("raw_event_key") or record.get("event_key"))
    if not raw_buff_id.isdigit():
        return []
    bb_keys = {str(key) for key in record.get("bb_keys") or []}
    bb_keys.update(str(key) for key in (record.get("bb_values") or {}).keys())
    if not bb_keys:
        return []
    observed_effect_pairs = _packet_record_effect_pairs(record)
    prefixes = {
        _char_prefix(record.get("owner_raw")),
        _char_prefix(record.get("raw_source")),
        _char_prefix(record.get("target_character_key")),
        _char_prefix(record.get("source_character_key")),
    }
    prefixes.discard(None)
    precise_character_keys = {
        str(value)
        for value in (
            record.get("owner_raw"),
            record.get("raw_source"),
            record.get("target_character_key"),
            record.get("source_character_key"),
        )
        if str(value or "").startswith("chr_")
    }
    target_is_enemy = bool(record.get("target_enemy_key"))
    candidates: list[tuple[int, str, dict[str, Any], set[str], set[str], dict[str, Any], set[tuple[str, str]]]] = []
    for buff_id, entry in _load_local_buff_semantic_entries().items():
        semantic_keys = _semantic_entry_bb_keys(entry)
        if not semantic_keys:
            continue
        overlap = bb_keys & semantic_keys
        if not overlap:
            continue
        missing_packet_keys = bb_keys - semantic_keys
        score = len(overlap) * 10 - len(missing_packet_keys) * 2
        hint = _buff_classifier_hint(buff_id) or {}
        classification = str(hint.get("classification") or "")
        hint_effect_pairs = _classifier_hint_effect_pairs(hint)
        effect_pair_overlap = observed_effect_pairs & hint_effect_pairs

        if any(buff_id.startswith(prefix or "") for prefix in prefixes):
            score += 8
        if any(buff_id.startswith(f"buff_{char_key}") for char_key in precise_character_keys):
            score += 12
        if _semantic_entry_has_rdps(entry):
            score += 4
        if classification == "effect_buff":
            score += 8
        elif classification == "indirect_buff":
            score += 3
        elif classification == "wrapper":
            score += 2 if not observed_effect_pairs else -6
        elif classification == "marker_or_utility":
            score += 1 if not observed_effect_pairs else -12

        if observed_effect_pairs and hint_effect_pairs:
            if effect_pair_overlap:
                score += len(effect_pair_overlap) * 18
            else:
                score -= min(12, len(observed_effect_pairs) * 4)

            damage_side_pairs = {
                pair for pair in hint_effect_pairs
                if pair[0] in ({"fragile", "vuln_taken", "res"} if target_is_enemy else {"atk", "dmg_inc", "amp", "crit", "combo"})
            }
            if damage_side_pairs:
                score += 4
            else:
                score -= 3
        if score <= 0:
            continue
        candidates.append((score, buff_id, entry, overlap, missing_packet_keys, hint, effect_pair_overlap))
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return [
        {
            "candidate_buff_id": buff_id,
            "score": score,
            "confidence": (
                "static_bb_character_effect_match"
                if effect_pair_overlap and any(buff_id.startswith(f"buff_{char_key}") for char_key in precise_character_keys)
                else "static_bb_effect_match"
                if effect_pair_overlap
                else "static_bb_owner_match"
                if any(buff_id.startswith(prefix or "") for prefix in prefixes)
                else "static_bb_match"
            ),
            "overlap_keys": sorted(overlap),
            "unknown_packet_keys": sorted(missing_packet_keys),
            "rdps_semantics": _semantic_entry_has_rdps(entry),
            "classification": hint.get("classification"),
            "effect_overlap": [
                {"zone": zone, "element": element}
                for zone, element in sorted(effect_pair_overlap)
            ],
            "resolved_effect_hints": [
                effect_hint
                for effect_hint in (hint.get("resolvedEffectHints") or [])
                if isinstance(effect_hint, dict)
            ],
        }
        for score, buff_id, entry, overlap, missing_packet_keys, hint, effect_pair_overlap in candidates[:limit]
    ]


@lru_cache(maxsize=1)
def _load_character_names() -> dict[str, str]:
    manifest_path = _repo_root() / "data" / "akedata" / "character" / "manifest.json"
    if not manifest_path.exists():
        return {}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {
        str(entry.get("charId")): str(entry.get("name"))
        for entry in manifest
        if entry.get("charId") and entry.get("name")
    }


@lru_cache(maxsize=1)
def _load_enemy_names() -> dict[str, str]:
    manifest_path = _repo_root() / "data" / "akedata" / "enemy" / "manifest.json"
    if not manifest_path.exists():
        return {}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {
        str(entry.get("templateId")): str(entry.get("name"))
        for entry in manifest
        if entry.get("templateId") and entry.get("name")
    }


def _high_difficulty_stage_key(dungeon_id: str) -> str:
    return dungeon_id.removesuffix("_s")


def _dungeon_table_sources() -> list[tuple[Path, Path]]:
    root = _repo_root()
    return [
        (root / "data" / "akedata" / "dungeon" / "manifest.json", root / "data" / "akedata" / "dungeon" / "items"),
        (root / "data" / "local_tables" / "dungeon" / "manifest.json", root / "data" / "local_tables" / "dungeon" / "items"),
    ]


def _iter_dungeon_manifest_entries(manifest: Any) -> list[dict[str, Any]]:
    if isinstance(manifest, list):
        return [entry for entry in manifest if isinstance(entry, dict)]
    if isinstance(manifest, dict):
        entries = manifest.get("entries")
        if isinstance(entries, list):
            return [entry for entry in entries if isinstance(entry, dict)]
    return []


def _dungeon_item_path(entry: dict[str, Any], dungeon_root: Path) -> Path | None:
    content_file = str(entry.get("contentFile") or "")
    detail_path = str(entry.get("detailPath") or "")
    if detail_path:
        candidate = _repo_root() / detail_path
        if candidate.exists():
            return candidate
    if content_file:
        return dungeon_root / Path(content_file).name
    if detail_path:
        return dungeon_root / Path(detail_path).name
    return None


def _iter_dungeon_table_payloads() -> list[tuple[dict[str, Any], dict[str, Any]]]:
    payloads: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for manifest_path, dungeon_root in _dungeon_table_sources():
        if not manifest_path.exists() or not dungeon_root.exists():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for entry in _iter_dungeon_manifest_entries(manifest):
            item_path = _dungeon_item_path(entry, dungeon_root)
            if item_path is None or not item_path.exists():
                continue
            try:
                data = json.loads(item_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(data, dict):
                payloads.append((entry, data))
    return payloads


@lru_cache(maxsize=1)
def _load_dungeon_by_id() -> dict[str, tuple[str, str]]:
    mapping: dict[str, tuple[str, str]] = {}
    for entry, data in _iter_dungeon_table_payloads():
        template_id = str(entry.get("templateId") or "")
        if not template_id:
            continue
        series_key = str(data.get("dungeonSeriesId") or template_id)
        series_name = str(data.get("dungeonSeriesname") or entry.get("name") or UNKNOWN_DUNGEON_NAME)
        mapping.setdefault(series_key, (series_key, series_name))
        for dungeon_id, dungeon in (data.get("dungeons") or {}).items():
            dungeon_key = str(dungeon_id)
            dungeon_name = str(dungeon.get("name") or series_name)
            if dungeon_key.startswith("indie_hard"):
                mapping[dungeon_key] = (dungeon_key, dungeon_name)
            else:
                mapping[dungeon_key] = (series_key, series_name)
        for dungeon_id in data.get("includeDungeonIds") or []:
            dungeon_key = str(dungeon_id or "")
            if not dungeon_key:
                continue
            if dungeon_key.startswith("indie_hard"):
                mapping.setdefault(dungeon_key, (dungeon_key, series_name))
            else:
                mapping.setdefault(dungeon_key, (series_key, series_name))
    return mapping


@lru_cache(maxsize=1)
def _load_dungeon_enemy_hints() -> dict[str, str]:
    mapping = dict(_DUNGEON_ENEMY_HINT_ALIASES)
    root = _repo_root()
    item_root = root / "data" / "local_tables" / "dungeon" / "items"
    if item_root.exists():
        for item_path in item_root.glob("*.json"):
            try:
                item_payload = json.loads(item_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            pending = [item_payload]
            while pending:
                node = pending.pop()
                if isinstance(node, dict):
                    dungeon_id = str(node.get("dungeonId") or "").strip()
                    enemy_ids = node.get("enemyIds")
                    if dungeon_id and isinstance(enemy_ids, list):
                        enemy_keys = {
                            enemy_key
                            for raw_enemy_id in enemy_ids
                            if (enemy_key := _extract_enemy_key(str(raw_enemy_id)))
                            and enemy_key != UNKNOWN_ENEMY_KEY
                        }
                        if len(enemy_keys) == 1:
                            mapping.setdefault(dungeon_id, next(iter(enemy_keys)))
                    pending.extend(node.values())
                elif isinstance(node, list):
                    pending.extend(node)
    path = root / "jsondata" / "Dungeon.json"
    if not path.exists():
        return mapping
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return mapping
    if not isinstance(payload, dict):
        return mapping
    for dungeon_id, raw_enemy_key in payload.items():
        enemy_key = _extract_enemy_key(str(raw_enemy_key))
        if enemy_key and enemy_key != UNKNOWN_ENEMY_KEY:
            mapping[str(dungeon_id)] = enemy_key
    return mapping


@lru_cache(maxsize=1)
def _load_skill_name_prefixes() -> list[tuple[str, str]]:
    character_root = _repo_root() / "data" / "akedata" / "character" / "items"
    if not character_root.exists():
        return []

    prefixes: list[tuple[str, str]] = []
    for path in character_root.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        for skill in data.get("skills") or []:
            skill_name = str(skill.get("name") or "")
            skill_ids = skill.get("skillIds") or []
            if not skill_name:
                continue
            for skill_id in skill_ids:
                skill_key = str(skill_id or "")
                if skill_key:
                    prefixes.append((skill_key, skill_name))
    prefixes.sort(key=lambda item: len(item[0]), reverse=True)
    return prefixes


@lru_cache(maxsize=1)
def _load_skill_exact_names() -> dict[str, str]:
    return {
        skill_key: skill_name
        for skill_key, skill_name in _load_skill_name_prefixes()
    }


@lru_cache(maxsize=1)
def _load_character_profiles() -> dict[str, dict[str, str]]:
    manifest_path = _repo_root() / "data" / "akedata" / "character" / "manifest.json"
    if not manifest_path.exists():
        return {}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {
        str(entry.get("charId")): {
            "name": str(entry.get("name") or ""),
            "char_type": str(entry.get("charType") or ""),
            "profession": str(entry.get("profession") or ""),
            "weapon_type": str(entry.get("weapontype") or ""),
        }
        for entry in manifest
        if entry.get("charId")
    }


@lru_cache(maxsize=1)
def _load_skill_profiles() -> dict[str, dict[str, Any]]:
    character_root = _repo_root() / "data" / "akedata" / "character" / "items"
    skill_item_root = _repo_root() / "data" / "akedata" / "skill" / "items"
    if not character_root.exists():
        return {}

    profiles = _load_character_profiles()
    mapping: dict[str, dict[str, Any]] = {}
    damage_tag_re = re.compile(r"<@ba\.([a-z_]+)>")
    for path in character_root.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        char_key = str(data.get("charId") or "")
        if not char_key:
            continue
        char_profile = profiles.get(char_key, {})
        char_type = char_profile.get("char_type") or str(data.get("charType") or "")
        profession = char_profile.get("profession") or str(data.get("profession") or "")
        weapon_type = char_profile.get("weapon_type") or str(data.get("weapontype") or "")
        for skill in data.get("skills") or []:
            try:
                group_type = int(skill.get("groupType") or 0)
            except (TypeError, ValueError):
                group_type = 0
            skill_ids = [str(skill_id or "") for skill_id in (skill.get("skillIds") or []) if skill_id]
            description = str(skill.get("description") or "")
            tags = {match.group(1) for match in damage_tag_re.finditer(description)}
            elements = {
                _DAMAGE_TAG_TO_ELEMENT[tag]
                for tag in tags
                if tag in _DAMAGE_TAG_TO_ELEMENT
            }
            family_skill_key = skill_ids[0] if group_type == 3 and skill_ids else ""
            for skill_key in skill_ids:
                skill_item_spec = ""
                skill_item_path = skill_item_root / f"{skill_key}.json"
                if skill_item_path.exists():
                    try:
                        skill_item = json.loads(skill_item_path.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError):
                        skill_item = {}
                    skill_item_spec = str(skill_item.get("skillSpecification") or "")
                mapping[skill_key] = {
                    "char_key": char_key,
                    "char_type": char_type,
                    "profession": profession,
                    "weapon_type": weapon_type,
                    "group_type": group_type,
                    "skill_specification": skill_item_spec,
                    "elements": sorted(elements),
                    # combo => 连携，同一条连携的多个分段应共享展示家族
                    "family_skill_key": family_skill_key or skill_key,
                }
    return mapping


@lru_cache(maxsize=4096)
def _load_skill_item_metadata(skill_key: str) -> dict[str, Any]:
    if not skill_key:
        return {}
    path = _repo_root() / "data" / "akedata" / "skill" / "items" / f"{skill_key}.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {
        "skill_specification": str(payload.get("skillSpecification") or ""),
        "cast_type": str(payload.get("castType") or ""),
        "attack_range_type": str(payload.get("attackRangeType") or ""),
    }


def _damage_school_from_element(element: str | None) -> str | None:
    if element == "physical":
        return "physical"
    if element in _ELEMENTAL_ELEMENTS:
        return "spell"
    return None


def _normalize_action_damage_type(value: Any) -> str | None:
    return _ACTION_DAMAGE_TYPE_TO_ELEMENT.get(str(value or "").strip().lower())


@lru_cache(maxsize=4096)
def _load_skill_action_damage_units(skill_key: str) -> dict[int, list[dict[str, Any]]]:
    if not skill_key:
        return {}
    canonical = _canonical_packet_skill_id(skill_key)
    path = _repo_root() / "data" / "akedata" / "skill" / "items" / f"{canonical}.json"
    if not path.exists():
        path = _repo_root() / "data" / "akedata" / "buff" / "items" / f"{canonical}.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    actions: dict[int, list[dict[str, Any]]] = {}

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            raw_action_id = node.get("serverActionIndex")
            raw_units = node.get("damageUnits")
            if raw_action_id is not None and isinstance(raw_units, list):
                try:
                    action_id = int(raw_action_id)
                except (TypeError, ValueError):
                    action_id = -1
                if action_id >= 0:
                    units: list[dict[str, Any]] = []
                    for index, unit in enumerate(raw_units):
                        if not isinstance(unit, dict):
                            continue
                        element = _normalize_action_damage_type(unit.get("damageType"))
                        if element is None:
                            continue
                        units.append(
                            {
                                "index": index,
                                "damage_type": str(unit.get("damageType") or ""),
                                "damage_attribute_type": str(unit.get("damageAttributeType") or ""),
                                "element": element,
                            }
                        )
                    if units:
                        actions.setdefault(action_id, units)
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(payload)
    return actions


def _infer_skill_action_damage_element(
    skill_key: str | None,
    action_id: int | str | None,
    damage_unit_index: int | str | None = None,
) -> str | None:
    try:
        action_id_int = int(action_id) if action_id is not None else None
    except (TypeError, ValueError):
        action_id_int = None
    if not skill_key or action_id_int is None:
        return None
    units = _load_skill_action_damage_units(str(skill_key)).get(action_id_int)
    if not units:
        return None

    try:
        unit_index = int(damage_unit_index) if damage_unit_index is not None else None
    except (TypeError, ValueError):
        unit_index = None
    if unit_index is not None:
        for unit in units:
            if unit.get("index") == unit_index:
                return str(unit.get("element") or "") or None

    for unit in units:
        if str(unit.get("damage_attribute_type") or "").lower() == "hp":
            return str(unit.get("element") or "") or None
    return str(units[0].get("element") or "") or None


@lru_cache(maxsize=1)
def _load_skill_profile_prefixes() -> list[tuple[str, dict[str, Any]]]:
    return sorted(_load_skill_profiles().items(), key=lambda item: len(item[0]), reverse=True)


def _resolve_skill_profile(skill_key: str | None) -> dict[str, Any] | None:
    if not skill_key:
        return None
    skill_key = _canonical_packet_skill_id(skill_key)
    mapping = _load_skill_profiles()
    exact = mapping.get(skill_key)
    if exact is not None:
        return exact
    for prefix, profile in _load_skill_profile_prefixes():
        if skill_key.startswith(prefix):
            return profile
    return None


def _resolve_combo_consume_context(hit: dict[str, Any]) -> tuple[int, str] | None:
    skill_key = str(hit.get("skill_key") or "")
    alias = _COMBO_CONSUME_SKILL_ALIASES.get(skill_key)
    if alias is not None:
        return int(alias["group_type"]), str(alias["family_skill_key"])

    try:
        group_type = int(hit.get("skill_group_type"))
    except (TypeError, ValueError):
        group_type = None
    family_key = str(hit.get("skill_family_key") or skill_key)
    if group_type in {1, 2} and family_key:
        return group_type, family_key

    if "_normal_skill" in skill_key:
        return 1, re.sub(r"(_normal_skill).*", r"\1", skill_key)
    if "_ultimate_skill" in skill_key:
        match = re.search(r"(chr_\d{4}_[a-z0-9]+_ultimate_skill)", skill_key)
        if match:
            return 2, match.group(1)

    return None


def _combo_marginal_layer_rates(group_type: int, stack_count: int) -> list[float]:
    total_rates = _COMBO_TOTAL_RATES_BY_GROUP_TYPE.get(group_type)
    if not total_rates or stack_count <= 0:
        return []
    capped_count = min(int(stack_count), len(total_rates))
    marginal_rates: list[float] = []
    previous_total = 0.0
    for total_rate in total_rates[:capped_count]:
        marginal_rates.append(max(0.0, float(total_rate) - previous_total))
        previous_total = float(total_rate)
    return marginal_rates


def _resolve_skill_family_key(skill_key: str | None, skill_profile: dict[str, Any] | None = None) -> str:
    if not skill_key:
        return ""
    skill_key = _canonical_packet_skill_id(skill_key)
    ultimate_match = re.match(r"^(chr_\d{4}_[a-z0-9]+)_ult_attack", skill_key.lower())
    if ultimate_match:
        return f"{ultimate_match.group(1)}_ultimate_skill"

    if skill_profile is not None:
        family_skill_key = str(skill_profile.get("family_skill_key") or skill_key)
        if family_skill_key:
            return family_skill_key

    combo_damage_match = _COMBO_DAMAGE_SKILL_KEY_RE.match(skill_key.lower())
    if combo_damage_match:
        combo_skill_key = f"{combo_damage_match.group(1)}skill"
        combo_profile = _resolve_skill_profile(combo_skill_key)
        if combo_profile is not None:
            return str(combo_profile.get("family_skill_key") or combo_skill_key)
        return combo_skill_key

    return skill_key


_CAST_CHILD_ENTITY_RE = re.compile(
    r"(?:projhit|abilityrange|indicator|blocked|_bomb|_field|_sheep)",
    re.IGNORECASE,
)


def _cast_skill_family_key(cast: dict[str, Any]) -> str:
    cast_skill = str(cast.get("skill") or "")
    if not cast_skill:
        return ""
    if str(cast.get("skill_source") or "").lower() == "summon":
        return ""
    if _CAST_CHILD_ENTITY_RE.search(cast_skill):
        return ""

    cast_character_key = str(cast.get("source_character_key") or "")
    canonical_skill = _canonical_packet_skill_id(cast_skill)
    if _is_generic_runtime_skill_id(canonical_skill) or re.fullmatch(r".*_skill_\d+", canonical_skill):
        canonical_skill = _canonical_num_table_skill_id(canonical_skill, cast_character_key) or canonical_skill

    skill_profile = _resolve_skill_profile(canonical_skill)
    family_key = _resolve_skill_family_key(canonical_skill, skill_profile)
    family_match = re.match(
        r"^(.*?_(?:ultimate_skill|normal_skill|combo(?:_\d+)?_skill))",
        family_key.lower(),
    )
    return family_match.group(1) if family_match else family_key


def _build_cast_start_index(skill_casts: list[dict[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    index: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for cast in sorted(skill_casts, key=lambda item: int(item.get("ts_ms") or 0)):
        character_key = str(cast.get("source_character_key") or "")
        family_key = _cast_skill_family_key(cast)
        if not character_key or not family_key:
            continue
        index[(character_key, family_key)].append(cast)
    return index


def _matching_cast_for_hit(
    hit: dict[str, Any],
    cast_start_index: dict[tuple[str, str], list[dict[str, Any]]],
) -> dict[str, Any] | None:
    character_key = str(hit.get("character_key") or "")
    family_key = str(hit.get("skill_family_key") or hit.get("skill_key") or "").lower()
    if not character_key or not family_key:
        return None

    hit_ts = int(hit.get("ts_ms") or 0)
    for cast in reversed(cast_start_index.get((character_key, family_key), [])):
        cast_ts = int(cast.get("ts_ms") or 0)
        delta_ms = hit_ts - cast_ts
        if delta_ms < -50:
            continue
        if delta_ms > 12000:
            break
        return cast
    return None


def _timeline_skill_group_gap_ms(hit: dict[str, Any]) -> int:
    skill_key = str(hit.get("skill_key") or "").lower()
    family_key = str(hit.get("skill_family_key") or "").lower()
    if "_ultimate_skill" in family_key or "_ultimate_skill" in skill_key or "_ult_attack" in skill_key:
        return _TIMELINE_ULTIMATE_GROUP_GAP_MS
    return _TIMELINE_SKILL_GROUP_GAP_MS


def _resolve_character_name(character_key: str | None) -> str | None:
    if not character_key:
        return None
    return _load_character_names().get(character_key, character_key)


def _resolve_enemy_name(enemy_key: str | None) -> str | None:
    if not enemy_key:
        return None
    return _load_enemy_names().get(enemy_key, enemy_key)


def _resolve_dungeon_context(dungeon_id: str | None) -> tuple[str, str] | None:
    if not dungeon_id:
        return None
    return _DUNGEON_CONTEXT_ALIASES.get(dungeon_id) or _load_dungeon_by_id().get(dungeon_id)


@lru_cache(maxsize=1)
def _load_buff_manifest_names() -> dict[str, str]:
    manifest_path = _repo_root() / "data" / "akedata" / "buff" / "manifest.json"
    if not manifest_path.exists():
        return {}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {
        str(entry.get("id")): str(entry.get("name"))
        for entry in manifest
        if entry.get("id") and entry.get("name")
    }


def _humanize_buff_damage_name(skill_key: str) -> str | None:
    override = _BUFF_DAMAGE_NAME_OVERRIDES.get(skill_key)
    if override is not None:
        return override

    manifest_name = _load_buff_manifest_names().get(skill_key, skill_key.removeprefix("buff_"))
    normalized = manifest_name.removeprefix("buff_")

    anomaly_do_match = re.match(
        r"^common_(fire|pulse|cryst|natural)_(?:fire|pulse|cryst|natural)_(conduct_triggered_do|corrupt_do)$",
        normalized,
    )
    if anomaly_do_match:
        action = anomaly_do_match.group(2)
        if action == "conduct_triggered_do":
            return "导电"
        if action == "corrupt_do":
            return "腐蚀"

    same_element_burst_match = re.match(
        r"^common_(fire|pulse|cryst|natural|spell)_\1_triggered$",
        normalized,
    )
    if same_element_burst_match:
        element = _ELEMENT_TOKEN_TO_NAME.get(same_element_burst_match.group(1), same_element_burst_match.group(1))
        return f"{element}爆发"

    cross_element_trigger_match = re.match(
        r"^common_(fire|pulse|cryst|natural)_(fire|pulse|cryst|natural)_triggered$",
        normalized,
    )
    if cross_element_trigger_match:
        applied = cross_element_trigger_match.group(1)
        anomaly_name = {
            "fire": "燃烧",
            "pulse": "导电",
            "cryst": "冻结",
            "natural": "腐蚀",
        }.get(applied)
        if anomaly_name:
            return anomaly_name

    if normalized.startswith("common_") and normalized.endswith("_triggered"):
        parts = normalized.split("_")
        if len(parts) >= 4:
            left = _ELEMENT_TOKEN_TO_NAME.get(parts[1], parts[1])
            right = _ELEMENT_TOKEN_TO_NAME.get(parts[2], parts[2])
            return f"{left}·{right}触发"

    if normalized.startswith("enemy_spell_") and "_triggered_" in normalized:
        parts = normalized.split("_")
        if len(parts) >= 5:
            element = _ELEMENT_TOKEN_TO_NAME.get(parts[2], parts[2])
            return f"敌方法术{element}触发"

    if normalized.endswith("_airborne"):
        prefix = normalized.removesuffix("_airborne")
        prefix_name = _ELEMENT_TOKEN_TO_NAME.get(prefix, prefix)
        return f"{prefix_name}浮空伤害"

    if normalized.startswith("common_heal_moss_"):
        return "治疗苔藓"

    if normalized.startswith("chr_"):
        character_skill_name = _humanize_character_skill_name(normalized)
        if character_skill_name is not None:
            return character_skill_name

    if normalized.startswith("common_"):
        readable = normalized.removeprefix("common_").replace("_", " ")
        return readable

    return None


def _humanize_skill_suffix_text(suffix: str) -> str | None:
    text = suffix.strip("_").lower()
    if not text:
        return None
    explicit = {
        "abilityentity": "实体",
        "abilityentitymove": "实体移动",
        "abilityrange": "范围",
        "air_attack_abilityrange": "空中攻击范围",
        "air_attack_projhit": "空中攻击派生",
        "air_attack_sheep": "空中攻击 / 绵羊",
        "blocked": "格挡",
        "during_ult": "终结技期间",
        "gene_sheep": "召唤绵羊",
        "hit": "命中",
        "hit_self": "自身命中",
        "indicator": "指示器",
        "listen_combo": "连携监听",
        "projhit": "派生",
        "remain_loop_sheep": "绵羊持续伤害",
        "sheep": "绵羊派生",
        "shockwave": "冲击波",
        "start": "起手",
    }
    if text in explicit:
        return explicit[text]

    absorb_match = re.match(r"absorb(?:_(\d+))?_projhit$", text)
    if absorb_match:
        slot = absorb_match.group(1)
        return f"吸收{slot}派生" if slot else "吸收派生"

    attack_match = re.match(r"attack_?(\d+)(?:_(\d+))?_projhit(?:_blocked)?$", text)
    if attack_match:
        attack_index = attack_match.group(1)
        sub_index = attack_match.group(2)
        base = f"A{attack_index}"
        if sub_index:
            base += f"-{sub_index}"
        if text.endswith("_blocked"):
            return f"{base} 派生（格挡）"
        return f"{base} 派生"

    tokens = [token for token in text.split("_") if token]
    if not tokens:
        return None
    token_map = {
        "absorb": "吸收",
        "air": "空中",
        "airborne": "浮空",
        "attack": "攻击",
        "blocked": "格挡",
        "bleed": "流血",
        "break": "击破",
        "combo": "连携",
        "damage": "伤害",
        "drone": "无人机",
        "effect": "效果",
        "entity": "实体",
        "extra": "额外",
        "fx": "特效",
        "loop": "循环",
        "move": "移动",
        "normal": "普攻",
        "projhit": "派生",
        "range": "范围",
        "remain": "持续",
        "self": "自身",
        "sheep": "绵羊",
        "shockwave": "冲击波",
        "spawn": "召唤",
        "talent": "天赋",
    }
    pretty = [token_map.get(token, token.upper() if token.isdigit() else token) for token in tokens]
    return " / ".join(pretty)


def _humanize_character_skill_name(skill_key: str) -> str | None:
    exact_name = _load_skill_exact_names().get(skill_key)
    if exact_name:
        return exact_name

    lowered = skill_key.lower()

    if lowered.endswith("_dodge"):
        return "闪避"

    if _DASH_ATTACK_RE.match(lowered):
        return "闪避攻击 派生" if "projhit" in lowered else "闪避攻击"

    if lowered.endswith("_power_attack"):
        return "重击"

    plunging_match = _PLUNGING_ATTACK_RE.match(lowered)
    if plunging_match:
        phase = plunging_match.group(1)
        if phase == "projhit":
            return "下落攻击 派生"
        if phase == "start":
            return "下落攻击 起手"
        return "下落攻击"

    attack_match = _ATTACK_VARIANT_RE.match(lowered)
    if attack_match:
        attack_index = attack_match.group(1)
        sub_index = attack_match.group(2)
        base = f"A{attack_index}"
        if sub_index:
            base += f"-{sub_index}"
        if "projhit" in lowered and "blocked" in lowered:
            return f"{base} 派生（格挡）"
        if "projhit" in lowered:
            return f"{base} 派生"
        return base

    talent_match = _TALENT_RE.match(lowered)
    if talent_match:
        tier = talent_match.group(1)
        branch = talent_match.group(2)
        return f"天赋{tier}-{branch}" if branch else f"天赋{tier}"

    potential_match = _POTENTIAL_RE.match(lowered)
    if potential_match:
        tier = potential_match.group(1)
        branch = potential_match.group(2)
        return f"潜能{tier}-{branch}" if branch else f"潜能{tier}"

    passive_match = _PASSIVE_RE.match(lowered)
    if passive_match:
        suffix = _humanize_skill_suffix_text(passive_match.group(1) or "")
        return f"被动 / {suffix}" if suffix else "被动"
    if lowered.endswith("_passive"):
        suffix_name = _humanize_skill_suffix_text(lowered.split("_", 3)[-1].removesuffix("_passive"))
        return f"被动 / {suffix_name}" if suffix_name else "被动"

    talent_suffix_index = lowered.find("_talent_")
    if talent_suffix_index >= 0:
        suffix_name = _humanize_skill_suffix_text(lowered[talent_suffix_index + len("_talent_"):])
        return f"天赋 / {suffix_name}" if suffix_name else "天赋"

    if lowered.endswith("_tactic_skill"):
        return "战术技"

    if lowered.endswith("_extra_attack_projhit"):
        return "追加攻击 派生"
    if lowered.endswith("_extra_attack"):
        return "追加攻击"

    for base_suffix in ("_normal_skill", "_combo_skill", "_ultimate_skill"):
        if base_suffix not in lowered:
            continue
        base_index = lowered.index(base_suffix) + len(base_suffix)
        base_key = skill_key[:base_index]
        suffix = skill_key[base_index:]
        base_name = _load_skill_exact_names().get(base_key)
        suffix_name = _humanize_skill_suffix_text(suffix)
        if base_name and suffix_name:
            return f"{base_name} / {suffix_name}"
        if base_name:
            return base_name
        break

    for base_key, base_name in _load_skill_name_prefixes():
        prefix = f"{base_key}_"
        if not skill_key.startswith(prefix):
            continue
        suffix_name = _humanize_skill_suffix_text(skill_key[len(base_key):])
        if suffix_name:
            return f"{base_name} / {suffix_name}"
        break

    suffix_patterns = (
        "remain_loop",
        "air_attack",
        "absorb",
        "abilityentity",
        "airborne",
        "bleed",
        "break",
        "damage",
        "effect",
        "projhit",
        "blocked",
        "sheep",
    )
    if any(pattern in lowered for pattern in suffix_patterns):
        if "_remain_loop_" in lowered:
            suffix_name = _humanize_skill_suffix_text(lowered.split("_", 3)[-1])
            if suffix_name:
                return suffix_name
        tail = lowered.split("_", 3)[-1]
        suffix_name = _humanize_skill_suffix_text(tail)
        if suffix_name:
            return suffix_name

    return None


def _humanize_generic_skill_tokens(text: str) -> str | None:
    value = text.strip("_").lower()
    if not value:
        return None
    explicit = {
        "abilityrange": "范围",
        "activityspecial": "活动特化",
        "battleact": "战斗动作",
        "bornexit": "出场结束",
        "bornstart": "出场开始",
        "death": "死亡",
        "doodad": "装置",
        "dungeon": "副本",
        "endinggame": "终局",
        "explosion": "爆炸",
        "ex": "EX",
        "hard": "高难",
        "interact": "交互",
        "passive": "被动",
        "projhit": "派生",
        "settlement": "结算",
        "store": "存储",
    }
    if value in explicit:
        return explicit[value]

    skill_match = re.fullmatch(r"skill0?(\d+)", value)
    if skill_match:
        return f"技能{int(skill_match.group(1))}"

    dash_match = re.fullmatch(r"dash_([bflr])", value)
    if dash_match:
        direction = {"b": "后", "f": "前", "l": "左", "r": "右"}.get(dash_match.group(1), dash_match.group(1))
        return f"冲刺（{direction}）"

    tokens = [token for token in value.split("_") if token]
    token_map = {
        "abilityentity": "实体",
        "activityspecial": "活动特化",
        "anchor": "锚点",
        "attack": "攻击",
        "attackcore": "核心攻击",
        "attackplayer": "玩家攻击",
        "battleact": "战斗动作",
        "boom": "爆破",
        "bomb": "炸弹",
        "carpet": "地毯",
        "container": "容器",
        "core": "核心",
        "dash": "冲刺",
        "death": "死亡",
        "doodad": "装置",
        "endinggame": "终局",
        "entity": "实体",
        "explosion": "爆炸",
        "fire": "火焰",
        "flammable": "可燃",
        "interact": "交互",
        "matrix": "矩阵",
        "mud": "泥沼",
        "oil": "油桶",
        "passive": "被动",
        "plus": "强化",
        "projhit": "派生",
        "range": "范围",
        "settlement": "结算",
        "special": "特殊",
        "store": "存储",
        "wall": "墙",
        "wave": "波动",
        "weekraid": "周常",
    }
    pretty: list[str] = []
    for token in tokens:
        skill_match = re.fullmatch(r"skill0?(\d+)", token)
        if skill_match:
            pretty.append(f"技能{int(skill_match.group(1))}")
            continue
        dash_match = re.fullmatch(r"dash_([bflr])", token)
        if dash_match:
            direction = {"b": "后", "f": "前", "l": "左", "r": "右"}.get(dash_match.group(1), dash_match.group(1))
            pretty.append(f"冲刺（{direction}）")
            continue
        pretty.append(token_map.get(token, token.upper() if token.isdigit() else token))
    return " / ".join(pretty) if pretty else None


def _humanize_generic_skill_name(skill_key: str) -> str | None:
    lowered = skill_key.lower()
    if lowered.startswith("eny_"):
        parts = lowered.split("_", 3)
        suffix = parts[3] if len(parts) >= 4 else ""
        suffix_name = _humanize_generic_skill_tokens(suffix)
        return f"敌方 / {suffix_name}" if suffix_name else "敌方技能"
    if lowered.startswith("abilityentity_"):
        suffix_name = _humanize_generic_skill_tokens(lowered.removeprefix("abilityentity_"))
        return f"实体 / {suffix_name}" if suffix_name else "实体技能"
    if lowered.startswith("common_"):
        suffix_name = _humanize_generic_skill_tokens(lowered.removeprefix("common_"))
        return f"通用 / {suffix_name}" if suffix_name else "通用技能"
    return None


def _resolve_skill_name(skill_key: str | None) -> str | None:
    if not skill_key:
        return None
    runtime_override = _RUNTIME_SKILL_NAME_OVERRIDES.get(str(skill_key))
    if runtime_override:
        return runtime_override
    skill_hint = _packet_numeric_skill_hint(skill_key)
    display_name = skill_hint.get("display_name")
    if display_name:
        return str(display_name)
    skill_key = _canonical_packet_skill_id(skill_key)
    canonical_display_name = _load_canonical_skill_display_names().get(skill_key)
    if canonical_display_name:
        return canonical_display_name
    lowered = skill_key.lower()
    if skill_key.startswith("buff_"):
        humanized_buff_name = _humanize_buff_damage_name(skill_key)
        if humanized_buff_name is not None:
            return humanized_buff_name
    if skill_key.startswith("chr_"):
        character_skill_name = _humanize_character_skill_name(skill_key)
        if character_skill_name is not None:
            return character_skill_name
    generic_skill_name = _humanize_generic_skill_name(skill_key)
    if generic_skill_name is not None:
        return generic_skill_name
    if lowered.startswith("numeric_buff_trigger_"):
        return "触发伤害"

    if any(token in lowered for token in ("execute", "execution")):
        return "处决"
    if "_ult_attack" in lowered or "_ultimate_skill" in lowered:
        return "终结技"
    if _COMBO_SKILL_RE.search(lowered):
        for prefix, skill_name in _load_skill_name_prefixes():
            if skill_key.startswith(prefix):
                return skill_name
        return "连携技"
    if "_normal_skill" in lowered:
        return "战技"
    if "power_attack" in lowered or "plunging_attack" in lowered or "heavy_attack" in lowered:
        return "重击"

    attack_match = _ATTACK_INDEX_RE.search(lowered)
    if attack_match:
        attack_index = int(attack_match.group(1))
        if 1 <= attack_index <= 4:
            return f"A{attack_index}"
        return "重击"

    for prefix, skill_name in _load_skill_name_prefixes():
        if skill_key.startswith(prefix):
            return skill_name
    return skill_key


def _element_from_text(value: str | None) -> str | None:
    if not value:
        return None
    match = _BB_KEY_ELEMENT_RE.search(value.lower())
    if not match:
        return None
    token = match.group(1)
    if token == "crystal":
        return "cryst"
    if token == "physic":
        return "physical"
    return token


def _damage_increase_element_from_bb_key(bb_key: str | None) -> str | None:
    lowered = (bb_key or "").lower()
    if lowered == "pd_up":
        return "physical"
    return _element_from_text(lowered)


def _is_damage_increase_bb_key(bb_key: str | None) -> bool:
    lowered = (bb_key or "").lower()
    return lowered in {"dmg_up", "pd_up", "spell_up"} or lowered.endswith("_dmg_up") or lowered.endswith("_dmg_up2")


def _normalize_effect_element(element: str | None) -> str:
    return element or "all"


def _effect_applies_to_damage_element(
    effect_element: str,
    damage_element: str | None,
    damage_school: str | None = None,
) -> bool:
    normalized = _normalize_effect_element(effect_element)
    if normalized == "all":
        return True
    if normalized in {"physical", "spell"}:
        if damage_school is not None:
            return normalized == damage_school
        if damage_element is None:
            return False
        if normalized == "physical":
            return damage_element == "physical"
        return damage_element in _ELEMENTAL_ELEMENTS
    if damage_element is None:
        return False
    return normalized == damage_element


def _effect_damage_type_condition_elements(effect: dict[str, Any]) -> set[str]:
    condition = effect.get("condition")
    return _condition_damage_type_elements(condition if isinstance(condition, dict) else None)


def _condition_damage_type_elements(condition: dict[str, Any] | None) -> set[str]:
    if not isinstance(condition, dict):
        return set()
    if str(condition.get("type") or "") == "all":
        elements: set[str] = set()
        for child in condition.get("conditions") or []:
            if isinstance(child, dict):
                elements.update(_condition_damage_type_elements(child))
        return elements
    if str(condition.get("type") or "") != "damage_type_in":
        return set()
    return {
        str(element)
        for element in condition.get("elements") or []
        if str(element or "")
    }


def _effect_element_applies_to_hit(
    effect: dict[str, Any],
    damage_element: str | None,
    damage_school: str | None = None,
) -> bool:
    effect_element = _normalize_effect_element(effect.get("element"))
    condition_elements = _effect_damage_type_condition_elements(effect)
    if condition_elements and (effect_element == "all" or effect_element in condition_elements):
        return True
    return _effect_applies_to_damage_element(effect_element, damage_element, damage_school)


def _element_filter_debug_fields(
    effect_element: str,
    damage_element: str | None,
    damage_school: str | None = None,
) -> dict[str, Any]:
    normalized = _normalize_effect_element(effect_element)
    reason = "damage_school_filtered" if normalized in {"physical", "spell"} else "damage_element_filtered"
    return {
        "reason": reason,
        "reason_group": "element_mismatch",
        "filter_kind": reason,
        "effect_element": normalized,
        "hit_damage_element": damage_element,
        "hit_damage_school": damage_school,
    }


def _description_line_for_bb_key(description: str, key: str) -> str:
    lines = [part.strip() for part in str(description or "").replace("\r", "\n").split("\n") if part.strip()]
    placeholder = "{" + key
    for line in lines:
        if placeholder in line:
            return line
    return lines[0] if lines else ""


def _condition_text_for_line(line: str) -> str:
    text = str(line or "").strip()
    if not text:
        return ""
    condition_markers = (
        "施放",
        "释放",
        "造成",
        "命中",
        "触发",
        "获得",
        "时，",
        "时 ",
        "后，",
        "期间",
    )
    if any(marker in text for marker in condition_markers):
        return text
    return ""


def _skill_groups_from_text(text: str) -> list[str]:
    groups: list[str] = []
    value = str(text or "")
    if "普通攻击" in value:
        groups.append("normal")
    if "战技" in value:
        groups.append("skill")
    if "连携技" in value:
        groups.append("combo")
    if "终结技" in value:
        groups.append("ultimate")
    if "所有技能" in value or "全技能" in value:
        groups.extend(["skill", "combo", "ultimate"])
    return list(dict.fromkeys(groups))


def _elements_from_text(text: str) -> list[str]:
    elements: list[str] = []
    mapping = (
        ("物理", "physical"),
        ("灼热", "fire"),
        ("电磁", "pulse"),
        ("寒冷", "cryst"),
        ("自然", "natural"),
        ("法术", "spell"),
    )
    for token, normalized in mapping:
        if token in str(text or ""):
            elements.append(normalized)
    return list(dict.fromkeys(elements))


def _static_multiplier_entry(
    *,
    source_type: str,
    source_name: str,
    label: str,
    zone: str,
    element: str,
    rate: float,
    note: str = "",
    skill_groups: list[str] | None = None,
    condition_text: str = "",
) -> dict[str, Any] | None:
    if zone not in _RDPS_ALLOCATABLE_ZONES or abs(rate) <= 1e-9:
        return None
    return {
        "source_type": source_type,
        "source_name": source_name,
        "label": label,
        "zone": zone,
        "zone_label": _RDPS_DEBUG_ZONE_LABELS.get(zone, zone),
        "element": element,
        "rate": rate,
        "note": note,
        "skill_groups": skill_groups or [],
        "condition_text": condition_text,
    }


def _derive_static_entries_from_desc(
    *,
    source_type: str,
    source_name: str,
    desc: str,
    value: Any,
    note: str = "",
) -> list[dict[str, Any]]:
    text = str(desc or "").strip()
    rate = _safe_positive_rate(value)
    if not text or rate is None:
        return []
    if any(token in text for token in ("终结技充能效率", "治疗", "力量", "敏捷", "智识", "意志", "防御力", "生命值", "主能力", "副能力", "源石技艺强度")):
        return []
    if "连携技冷却缩减" in text:
        return []

    if "承伤易伤" in text or "受到的法术伤害" in text or "受到的物理伤害" in text or "受到伤害提高" in text:
        zone = "vuln_taken"
    elif "减抗" in text or "抗性降低" in text:
        zone = "res"
    elif "连击增伤" in text:
        zone = "combo"
    elif "脆弱" in text or ("易伤" in text and "受到" not in text):
        zone = "fragile"
    elif "攻击提升" in text or "攻击力提升" in text:
        zone = "atk"
    elif "伤害提升" in text or "伤害加成" in text or "所有技能伤害" in text or "全技能伤害" in text:
        zone = "dmg_inc"
    else:
        return []

    condition_text = _condition_text_for_line(text)
    skill_groups = _skill_groups_from_text(text)
    entries: list[dict[str, Any]] = []
    for element in _elements_from_text(text) or ["all"]:
        entry = _static_multiplier_entry(
            source_type=source_type,
            source_name=source_name,
            label=text,
            zone=zone,
            element=element,
            rate=rate,
            note=note,
            skill_groups=skill_groups,
            condition_text=condition_text,
        )
        if entry is not None:
            entries.append(entry)
    return entries


def _derive_static_entries_from_weapon_bb(
    *,
    source_name: str,
    skill_id: str,
    bb: dict[str, Any],
    description_by_key: dict[str, str],
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for raw_key, raw_value in (bb or {}).items():
        key = str(raw_key or "").lower()
        rate = _safe_positive_rate(raw_value)
        if rate is None:
            continue
        zone = ""
        element = "all"
        skill_groups: list[str] = []
        if key in {"spell_damage_taken_up", "spell_dmg_taken_up"}:
            zone = "vuln_taken"
            element = "spell"
        elif key == "dmg_taken_up":
            zone = "vuln_taken"
        elif key in {"spell_dmg_up", "spelldam"}:
            zone = "dmg_inc"
            element = "spell"
        elif key == "spell_up":
            zone = "dmg_inc"
            skill_groups = ["skill", "combo", "ultimate"]
        elif key == "normal_atk_up":
            zone = "dmg_inc"
            skill_groups = ["normal"]
        elif key.endswith("_dmg_up"):
            zone = "dmg_inc"
            prefix = key.removesuffix("_dmg_up")
            element = {
                "fire": "fire",
                "pulse": "pulse",
                "cryst": "cryst",
                "natural": "natural",
                "physical": "physical",
                "spell": "spell",
            }.get(prefix, "all")
        elif key.startswith("damage_taken_up_"):
            zone = "vuln_taken"
            suffix = key.removeprefix("damage_taken_up_")
            element = {
                "fire": "fire",
                "pulse": "pulse",
                "cryst": "cryst",
                "natural": "natural",
                "physical": "physical",
                "spell": "spell",
            }.get(suffix, "all")
        else:
            continue

        description_line = str(description_by_key.get(key) or "")
        entry = _static_multiplier_entry(
            source_type="weapon",
            source_name=source_name,
            label=f"武器效果 {skill_id} / {raw_key}",
            zone=zone,
            element=element,
            rate=rate,
            note=f"blackboard: {raw_key}={raw_value}",
            skill_groups=skill_groups,
            condition_text=_condition_text_for_line(description_line),
        )
        if entry is not None:
            entries.append(entry)
    return entries


def _derive_static_self_multiplier_entries(row: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []

    for equip in row.get("equips") or []:
        if not isinstance(equip, dict):
            continue
        equip_name = str(equip.get("piece_name") or equip.get("item_name") or equip.get("item_id") or "装备")
        for stat in equip.get("stats") or []:
            if not isinstance(stat, dict):
                continue
            entries.extend(
                _derive_static_entries_from_desc(
                    source_type="equip",
                    source_name=equip_name,
                    desc=str(stat.get("name") or ""),
                    value=stat.get("value"),
                    note=f"{equip.get('part_name') or ''} / {stat.get('slot') or ''}",
                )
            )

    for suit in row.get("suit_effects") or []:
        if not isinstance(suit, dict) or not suit.get("active"):
            continue
        suit_name = str(suit.get("suit_name") or suit.get("suit_id") or "套装")
        description = str(suit.get("description") or "")
        for key, value in (suit.get("value") or {}).items():
            line = _description_line_for_bb_key(description, str(key))
            entries.extend(
                _derive_static_entries_from_desc(
                    source_type="suit",
                    source_name=suit_name,
                    desc=line or description,
                    value=value,
                    note=f"{key}={value}",
                )
            )

    weapon_name = str(row.get("weapon_name") or row.get("weapon_template") or "武器")
    description_by_key: dict[str, str] = {}
    for skill in row.get("weapon_catalog_skilllist") or []:
        if not isinstance(skill, dict):
            continue
        description = str(skill.get("description") or "")
        for bb in skill.get("blackboard") or []:
            if not isinstance(bb, dict):
                continue
            key = str(bb.get("key") or "").lower()
            if key:
                description_by_key[key] = _description_line_for_bb_key(description, key)
    for skill in row.get("weapon_source_skills") or row.get("weapon_refine_stats") or []:
        if not isinstance(skill, dict):
            continue
        entries.extend(
            _derive_static_entries_from_weapon_bb(
                source_name=weapon_name,
                skill_id=str(skill.get("skill_id") or ""),
                bb=dict(skill.get("bb") or {}),
                description_by_key=description_by_key,
            )
        )

    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str, float, str]] = set()
    for entry in entries:
        # Conditional entries should be represented by live packet buff windows;
        # adding them here would double count transient weapon/suit effects.
        if entry.get("condition_text"):
            continue
        key = (
            str(entry.get("source_type") or ""),
            str(entry.get("source_name") or ""),
            str(entry.get("label") or ""),
            str(entry.get("element") or ""),
            round(float(entry.get("rate") or 0.0), 6),
            ",".join(entry.get("skill_groups") or []),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(entry)
    return deduped


@lru_cache(maxsize=None)
def _load_character_potential_rows(character_key: str) -> list[dict[str, Any]]:
    path = _repo_root() / "data" / "akedata" / "character" / "items" / f"{character_key}.json"
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [row for row in payload.get("potentials") or [] if isinstance(row, dict)]


def _arts_strength_entry(
    *,
    source_type: str,
    source_name: str,
    label: str,
    value: Any,
    note: str = "",
) -> dict[str, Any] | None:
    points = _safe_positive_rate(value)
    if points is None:
        return None
    return {
        "source_type": source_type,
        "source_name": source_name,
        "label": label,
        "zone": "arts_strength",
        "zone_label": _RDPS_DEBUG_ZONE_LABELS["arts_strength"],
        "element": "all",
        "rate": points,
        "note": note,
    }


def _derive_static_arts_strength_entries(row: dict[str, Any]) -> list[dict[str, Any]]:
    """Collect always-on source-strength points from the selected battle loadout.

    Transient effects stay packet-window driven.  This baseline is only the
    denominator for the dedicated anomaly formula; it is never converted into
    an ordinary damage-increase percentage.
    """

    entries: list[dict[str, Any]] = []
    for equip in row.get("equips") or []:
        if not isinstance(equip, dict):
            continue
        equip_name = str(equip.get("piece_name") or equip.get("item_name") or equip.get("item_id") or "装备")
        for stat in equip.get("stats") or []:
            if not isinstance(stat, dict) or "源石技艺强度" not in str(stat.get("name") or ""):
                continue
            entry = _arts_strength_entry(
                source_type="equip",
                source_name=equip_name,
                label=str(stat.get("name") or "源石技艺强度"),
                value=stat.get("value"),
                note=f"{equip.get('part_name') or ''} / {stat.get('slot') or ''}",
            )
            if entry is not None:
                entries.append(entry)

    for suit in row.get("suit_effects") or []:
        if not isinstance(suit, dict) or not suit.get("active"):
            continue
        description = str(suit.get("description") or "")
        for key, value in (suit.get("value") or {}).items():
            line = _description_line_for_bb_key(description, str(key))
            if "源石技艺强度" not in line or _condition_text_for_line(line):
                continue
            entry = _arts_strength_entry(
                source_type="suit",
                source_name=str(suit.get("suit_name") or suit.get("suit_id") or "套装"),
                label=line,
                value=value,
                note=f"{key}={value}",
            )
            if entry is not None:
                entries.append(entry)

    weapon_name = str(row.get("weapon_name") or row.get("weapon_template") or "武器")
    description_by_key: dict[str, str] = {}
    for skill in row.get("weapon_catalog_skilllist") or []:
        if not isinstance(skill, dict):
            continue
        description = str(skill.get("description") or "")
        for bb in skill.get("blackboard") or []:
            if not isinstance(bb, dict):
                continue
            key = str(bb.get("key") or "").lower()
            if key:
                description_by_key[key] = _description_line_for_bb_key(description, key)
    for skill in row.get("weapon_source_skills") or row.get("weapon_refine_stats") or []:
        if not isinstance(skill, dict):
            continue
        for raw_key, value in (skill.get("bb") or {}).items():
            key = str(raw_key or "").lower()
            line = description_by_key.get(key, "")
            if key not in _ARTS_STRENGTH_BB_KEYS and "源石技艺强度" not in line:
                continue
            if line and _condition_text_for_line(line):
                continue
            entry = _arts_strength_entry(
                source_type="weapon",
                source_name=weapon_name,
                label=line or f"武器效果 {skill.get('skill_id') or ''} / {raw_key}",
                value=value,
                note=f"blackboard: {raw_key}={value}",
            )
            if entry is not None:
                entries.append(entry)

    character_key = str(row.get("character_key") or "")
    potential = max(int(row.get("potential") or 0), 0)
    for index, potential_row in enumerate(_load_character_potential_rows(character_key), start=1):
        if index > potential:
            break
        description = str(potential_row.get("description") or "")
        for raw_key, value in (potential_row.get("values") or {}).items():
            key = str(raw_key or "").lower()
            line = _description_line_for_bb_key(description, str(raw_key))
            if key not in _ARTS_STRENGTH_BB_KEYS and "源石技艺强度" not in line:
                continue
            entry = _arts_strength_entry(
                source_type="potential",
                source_name=str(potential_row.get("name") or f"潜能 {index}"),
                label=line or "源石技艺强度",
                value=value,
                note=f"potential={index}; {raw_key}={value}",
            )
            if entry is not None:
                entries.append(entry)

    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, float]] = set()
    for entry in entries:
        signature = (
            str(entry.get("source_type") or ""),
            str(entry.get("source_name") or ""),
            str(entry.get("label") or ""),
            round(float(entry.get("rate") or 0.0), 6),
        )
        if signature in seen:
            continue
        seen.add(signature)
        deduped.append(entry)
    return deduped


def _is_arts_strength_damage_hit(hit: dict[str, Any]) -> bool:
    skill_key = str(hit.get("skill_key") or "").lower()
    skill_name = str(hit.get("skill_name") or "")
    if re.match(r"^buff_common_(?:fire|pulse|cryst|natural)_[a-z0-9_]*triggered", skill_key):
        return True
    if skill_key in _ARTS_STRENGTH_PHYSICAL_ANOMALY_DAMAGE_IDS:
        return True
    return skill_key.startswith("buff_common_") and any(
        token in skill_name
        for token in ("物理异常", "法术异常", "法术爆发", "燃烧", "导电", "腐蚀", "冻结", "碎甲", "猛击", "击倒", "击飞")
    )


def _arts_strength_damage_multiplier(points: float) -> float:
    return 1.0 + max(float(points), 0.0) / 100.0


def _arts_strength_effect_multiplier(points: float) -> float:
    normalized = max(float(points), 0.0)
    return 1.0 + (2.0 * normalized / (normalized + 300.0))


def _infer_skill_damage_element(skill_key: str | None, character_key: str | None) -> str | None:
    if not skill_key:
        return None
    skill_key = _canonical_packet_skill_id(skill_key)

    if skill_key == "buff_common_cryst_triggered_physical_break":
        return "physical"

    direct = _element_from_text(skill_key)
    if direct:
        return direct
    if "burning_status" in skill_key:
        return "fire"

    profile = _resolve_skill_profile(skill_key)
    if profile is None and character_key:
        char_type = _load_character_profiles().get(character_key, {}).get("char_type")
        return _CHAR_TYPE_TO_ELEMENT.get(char_type)
    if profile is None:
        return None

    elements = list(profile.get("elements") or [])
    if len(elements) == 1:
        return elements[0]

    char_type = str(profile.get("char_type") or "")
    default_element = _CHAR_TYPE_TO_ELEMENT.get(char_type)
    group_type = int(profile.get("group_type") or 0)
    skill_lower = skill_key.lower()

    if len(elements) > 1:
        if "attack" in skill_lower or "power_attack" in skill_lower or "plunging" in skill_lower:
            return "physical" if "physical" in elements else default_element
        if "combo" in skill_lower and "physical" in elements:
            return "physical"
        if group_type in {1, 2} and default_element in elements:
            return default_element

    return default_element or (elements[0] if elements else None)


def _infer_skill_damage_school(
    skill_key: str | None,
    character_key: str | None,
    *,
    raw_skill_key: str | None = None,
) -> str | None:
    candidate_keys = [str(skill_key or "")]
    raw_key = str(raw_skill_key or "")
    if raw_key and raw_key not in candidate_keys:
        candidate_keys.append(raw_key)

    for candidate in candidate_keys:
        if not candidate:
            continue
        canonical = _canonical_packet_skill_id(candidate)
        profile = _resolve_skill_profile(canonical)
        spec = str(profile.get("skill_specification") or "") if profile is not None else ""
        if not spec:
            item_meta = _load_skill_item_metadata(canonical)
            spec = str(item_meta.get("skill_specification") or "")
        school = _DAMAGE_SCHOOL_BY_SPEC.get(spec)
        inferred_element = _infer_skill_damage_element(canonical, character_key)
        lowered = canonical.lower()
        if school == "physical" and inferred_element in _ELEMENTAL_ELEMENTS and any(
            token in lowered for token in ("_ultimate_skill", "_ult_attack", "_normal_skill", "_combo_skill")
        ):
            return "spell"
        if school:
            return school
        if inferred_element in _ELEMENTAL_ELEMENTS and any(
            token in lowered for token in ("_attack", "_projhit", "_power_attack", "_dash_attack", "_plunging_attack")
        ):
            return "spell"
        if any(token in lowered for token in ("_ultimate_skill", "_ult_attack", "_normal_skill", "_combo_skill")):
            return "spell"
        if "remain_loop_sheep" in lowered:
            return "physical"
        if any(token in lowered for token in ("_attack", "_projhit", "_power_attack", "_dash_attack", "_plunging_attack")):
            return "physical"

    damage_element = _infer_skill_damage_element(skill_key or raw_skill_key, character_key)
    if damage_element == "physical":
        return "physical"
    return None


def _parse_prefixed_timestamp_ms(line: str) -> int | None:
    match = _TIMESTAMP_RE.match(line)
    if not match:
        return None
    hours, minutes, seconds, millis = (int(part) for part in match.groups())
    return (((hours * 60) + minutes) * 60 + seconds) * 1000 + millis


def _parse_hint_timestamp_ms(text: str | None) -> int | None:
    if not text:
        return None
    parts = text.split("-")
    if len(parts) != 4:
        return None
    hours, minutes, seconds, millis = (int(part) for part in parts)
    return (((hours * 60) + minutes) * 60 + seconds) * 1000 + millis


def _extract_fields(line: str) -> dict[str, str]:
    return {
        key: value[1:-1] if value.startswith('"') and value.endswith('"') else value
        for key, value in _KV_RE.findall(line)
    }


def _parse_poise_damage_event(raw_line: str, ts_ms: int, line_no: int) -> dict[str, Any] | None:
    if not _POISE_RE.search(raw_line):
        return None
    fields = _extract_fields(raw_line)
    if str(fields.get("type") or "") != "PoiseDamage":
        return None
    source = str(fields.get("source") or "").strip()
    orig_source = str(fields.get("origSource") or "").strip()
    if source in {"", "unknown"}:
        source = orig_source
    if source in {"", "unknown"}:
        return None
    return {
        "line_no": line_no,
        "ts_ms": ts_ms,
        "type": "PoiseDamage",
        "value": _coerce_optional_float(fields.get("value")),
        "current_value": _coerce_optional_float(fields.get("cur")),
        "source": source,
        "source_int": _coerce_int(fields.get("sourceInt"), default=0) or None,
        "orig_source": orig_source if orig_source not in {"", "unknown"} else None,
        "orig_source_int": _coerce_int(fields.get("origSourceInt"), default=0) or None,
    }


def _apply_poise_damage_events_to_hits(
    hits: list[dict[str, Any]],
    poise_damage_events: list[dict[str, Any]],
) -> None:
    if not hits or not poise_damage_events:
        return

    for event in poise_damage_events:
        source = str(event.get("source") or "")
        source_int = event.get("source_int")
        orig_source_int = event.get("orig_source_int")
        event_ts_ms = int(event.get("ts_ms") or 0)
        matches = [
            hit
            for hit in hits
            if int(hit.get("ts_ms") or 0) == event_ts_ms
            and (
                source in {str(hit.get("skill_key") or ""), str(hit.get("skill_family_key") or "")}
                or (source_int is not None and source_int == hit.get("template_int_id"))
                or (orig_source_int is not None and orig_source_int == hit.get("original_template_int_id"))
            )
        ]
        if not matches:
            continue
        for hit in matches:
            hit["poise_damage"] = {
                "type": event.get("type") or "PoiseDamage",
                "value": event.get("value"),
                "current_value": event.get("current_value"),
                "source": source,
                "source_int": source_int,
                "orig_source": event.get("orig_source"),
                "orig_source_int": orig_source_int,
            }


@lru_cache(maxsize=1)
def _load_contract_tag_texts() -> dict[str, str]:
    candidates = [
        _repo_root().parent / "endfield_tables" / "Data" / "TableCfg" / "I18nTextTable_CN.json",
        _repo_root() / "data" / "local_tables" / "I18nTextTable_CN.json",
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            result: dict[str, str] = {}
            for key, value in payload.items():
                if isinstance(value, str):
                    result[str(key)] = value
                elif isinstance(value, dict):
                    text = value.get("text") or value.get("value")
                    if isinstance(text, str):
                        result[str(key)] = text
            return result
    return {}


def _contract_tag_text(value: Any, texts: dict[str, str]) -> str | None:
    if isinstance(value, dict):
        text = value.get("text")
        if isinstance(text, str) and text:
            return text
        value = value.get("id")
    if value is None:
        return None
    return texts.get(str(value))


@lru_cache(maxsize=1)
def _load_contract_tag_catalog() -> dict[int, dict[str, Any]]:
    catalog: dict[int, dict[str, Any]] = {}
    public_path = _repo_root() / "data" / "public" / "contract_tags.json"
    if public_path.exists():
        try:
            payload = json.loads(public_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = None
        tags = payload.get("tags") if isinstance(payload, dict) else payload
        entries = tags.values() if isinstance(tags, dict) else tags if isinstance(tags, list) else []
        for item in entries:
            if not isinstance(item, dict):
                continue
            tag_id = _coerce_int(str(item.get("tagId") or item.get("tag_id") or ""), default=0)
            if tag_id > 0:
                catalog[tag_id] = dict(item)

    table_candidates = [
        _repo_root().parent / "endfield_tables" / "Data" / "TableCfg" / "CcTagTable.json",
        _repo_root() / "data" / "local_tables" / "CcTagTable.json",
    ]
    for path in table_candidates:
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        entries = payload.values() if isinstance(payload, dict) else payload if isinstance(payload, list) else []
        for item in entries:
            if not isinstance(item, dict):
                continue
            tag_id = _coerce_int(str(item.get("tagId") or item.get("tag_id") or ""), default=0)
            if tag_id <= 0:
                continue
            merged = dict(catalog.get(tag_id) or {})
            merged.update(item)
            catalog[tag_id] = merged
        break

    texts = _load_contract_tag_texts()
    for tag_id, item in list(catalog.items()):
        enriched = dict(item)
        name = enriched.get("name")
        desc = enriched.get("desc") if "desc" in enriched else enriched.get("description")
        name_text = _contract_tag_text(name, texts) or _contract_tag_text(enriched.get("nameTextId"), texts)
        desc_text = _contract_tag_text(desc, texts) or _contract_tag_text(enriched.get("descTextId"), texts)
        if name_text:
            enriched["name"] = name_text
        if desc_text:
            enriched["description"] = desc_text
        catalog[tag_id] = enriched
    return catalog


def _parse_contract_tag_ids(value: str | None) -> list[int]:
    if not value:
        return []
    return [int(item) for item in re.findall(r"\d+", value)]


def _contract_tag_payload(tag_id: int) -> dict[str, Any]:
    catalog_entry = _load_contract_tag_catalog().get(tag_id, {})
    tag_terms = catalog_entry.get("tagTerms") if isinstance(catalog_entry.get("tagTerms"), list) else []
    values: dict[str, Any] = {}
    for term in tag_terms:
        if not isinstance(term, dict):
            continue
        for row in term.get("blackboard") or []:
            if isinstance(row, dict) and row.get("key") is not None:
                values[str(row.get("key"))] = row.get("value")
    icon_id = catalog_entry.get("iconId") or catalog_entry.get("icon")
    payload: dict[str, Any] = {
        "tag_id": tag_id,
        "score": _coerce_int(str(catalog_entry.get("score") or ""), default=0),
    }
    if catalog_entry.get("name"):
        payload["name"] = catalog_entry.get("name")
    if catalog_entry.get("description"):
        payload["description"] = catalog_entry.get("description")
    if icon_id:
        payload["icon"] = icon_id
    icon_url = catalog_entry.get("iconUrl") or catalog_entry.get("icon_url")
    if icon_url:
        payload["icon_url"] = icon_url
    if catalog_entry.get("buffId"):
        payload["buff_id"] = catalog_entry.get("buffId")
    if catalog_entry.get("groupId") is not None:
        payload["group_id"] = catalog_entry.get("groupId")
    if catalog_entry.get("conflictId") is not None:
        payload["conflict_id"] = catalog_entry.get("conflictId")
    if tag_terms:
        payload["terms"] = tag_terms
    if values:
        payload["values"] = values
    return payload


def _short_actor_number(value: str | None) -> str | None:
    if not value:
        return None
    match = _SHORT_ID_RE.match(value)
    return match.group(1) if match else None


@lru_cache(maxsize=1)
def _load_actor_fingerprint_map() -> dict[str, dict[str, Any]]:
    map_path = _repo_root() / "data" / "packet_semantics" / "actor_fingerprint_map.json"
    if not map_path.exists():
        return {}
    try:
        payload = json.loads(map_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    characters = payload.get("characters")
    if not isinstance(characters, dict):
        return {}
    return {
        str(character_key): fingerprint
        for character_key, fingerprint in characters.items()
        if isinstance(fingerprint, dict)
    }


def _parse_loadout_skill_ids(raw: str) -> set[str]:
    match = re.search(r"skillIntIds=\[([^\]]*)\]", raw)
    if not match:
        return set()
    return set(re.findall(r"\d+", match.group(1)))


def _collect_loadout_skill_fingerprints(text: str) -> tuple[set[str], dict[str, set[str]]]:
    roster: set[str] = set()
    skill_ids_by_char: dict[str, set[str]] = {}
    for raw_line in text.splitlines():
        if "LOADOUT slot=" not in raw_line:
            continue
        char_match = re.search(r"\bchar=(chr_\d{4}_[a-z0-9]+)\b", raw_line)
        if not char_match:
            continue
        char_key = char_match.group(1)
        roster.add(char_key)
        skill_ids_by_char.setdefault(char_key, set()).update(_parse_loadout_skill_ids(raw_line))
    return roster, skill_ids_by_char


def _collect_short_actor_observations(text: str) -> dict[str, dict[str, Counter[str]]]:
    observations: dict[str, dict[str, Counter[str]]] = defaultdict(
        lambda: {"skills": Counter(), "self_buffs": Counter()}
    )
    for raw_line in text.splitlines():
        if " HP_V2 " in raw_line:
            fields = _extract_fields(raw_line)
            actor_id = fields.get("src") or fields.get("atk")
            if not _short_actor_number(actor_id):
                continue
            skill_number = _runtime_skill_number(fields.get("skill"))
            if skill_number:
                observations[actor_id]["skills"][skill_number] += 1
            continue

        if " BUFF_START " in raw_line:
            fields = _extract_fields(raw_line)
            owner = fields.get("owner")
            src = fields.get("src")
            if not owner or owner != src or not _short_actor_number(owner):
                continue
            buff_number = _runtime_skill_number(_normalize_buff_id(fields.get("id")))
            if buff_number:
                observations[owner]["self_buffs"][buff_number] += 1
    return observations


def _score_actor_fingerprint(
    *,
    actor_observation: dict[str, Counter[str]],
    character_key: str,
    loadout_skill_ids: set[str],
    fingerprint: dict[str, Any],
) -> int:
    skills = set(actor_observation.get("skills") or {})
    self_buffs = set(actor_observation.get("self_buffs") or {})
    if not skills and not self_buffs:
        return 0

    score = 0
    score += 5 * len(skills & loadout_skill_ids)
    score += 4 * len(skills & {str(value) for value in fingerprint.get("strong_skill_ids") or []})
    score += 1 * len(skills & {str(value) for value in fingerprint.get("weak_skill_ids") or []})
    score += 2 * len(self_buffs & {str(value) for value in fingerprint.get("self_buff_ids") or []})
    return score


def _infer_short_actor_aliases_from_fingerprints(text: str) -> dict[str, str]:
    roster, loadout_skill_ids_by_char = _collect_loadout_skill_fingerprints(text)
    configured_fingerprints = _load_actor_fingerprint_map()
    observations = _collect_short_actor_observations(text)
    if not observations:
        return {}

    candidate_chars = set(configured_fingerprints)
    candidate_chars.update(loadout_skill_ids_by_char)
    if roster:
        candidate_chars &= roster
    if not candidate_chars:
        return {}

    scored: list[tuple[str, str, int, int]] = []
    for actor_id, observation in observations.items():
        actor_scores: list[tuple[str, int]] = []
        for char_key in candidate_chars:
            score = _score_actor_fingerprint(
                actor_observation=observation,
                character_key=char_key,
                loadout_skill_ids=loadout_skill_ids_by_char.get(char_key, set()),
                fingerprint=configured_fingerprints.get(char_key, {}),
            )
            if score > 0:
                actor_scores.append((char_key, score))
        if not actor_scores:
            continue
        actor_scores.sort(key=lambda item: item[1], reverse=True)
        top_char, top_score = actor_scores[0]
        runner_up = actor_scores[1][1] if len(actor_scores) > 1 else 0
        scored.append((actor_id, top_char, top_score, runner_up))

    aliases: dict[str, str] = {}
    claimed_chars: set[str] = set()
    min_score = 4 if roster else 8
    deferred: list[tuple[str, str, int, int]] = []
    for actor_id, char_key, top_score, runner_up in sorted(scored, key=lambda item: item[2], reverse=True):
        if char_key in claimed_chars:
            continue
        if top_score < min_score or top_score - runner_up < 2:
            deferred.append((actor_id, char_key, top_score, runner_up))
            continue
        aliases[actor_id] = char_key
        claimed_chars.add(char_key)

    remaining_chars = roster - claimed_chars
    if len(remaining_chars) == 1:
        remaining_char = next(iter(remaining_chars))
        weak_matches = [
            (actor_id, top_score)
            for actor_id, char_key, top_score, runner_up in deferred
            if char_key == remaining_char and top_score > runner_up and top_score > 0 and actor_id not in aliases
        ]
        if len(weak_matches) == 1:
            aliases[weak_matches[0][0]] = remaining_char
    return aliases


def _infer_short_actor_aliases_from_loadout(text: str) -> dict[str, str]:
    """Recover packet runtime actor ids when ACTOR_MAP was not emitted."""
    if "LOADOUT reason=SC_SELF_SCENE_INFO" not in text:
        return {}
    roster: list[str] = []
    roster_seen: set[str] = set()
    for raw_line in text.splitlines():
        if "LOADOUT slot=" not in raw_line:
            continue
        match = _LOADOUT_SLOT_RE.search(raw_line)
        if not match:
            continue
        char_key = match.group("char")
        if char_key and char_key not in roster_seen:
            roster_seen.add(char_key)
            roster.append(char_key)

    if len(roster) < 2:
        return {}

    groups: list[list[str]] = []
    group: list[str] = []
    group_seen: set[str] = set()
    group_ts_ms: int | None = None
    for raw_line in text.splitlines():
        if _GAME_TIMER_START_RE.search(raw_line):
            break
        if " BUFF_START " not in raw_line:
            continue
        ts_ms = _parse_prefixed_timestamp_ms(raw_line)
        fields = _extract_fields(raw_line)
        owner_id = _short_actor_number(fields.get("owner"))
        src_id = _short_actor_number(fields.get("src"))
        if not owner_id or owner_id != src_id:
            continue
        if group and ts_ms is not None and group_ts_ms is not None and ts_ms - group_ts_ms > 1000:
            groups.append(group)
            group = []
            group_seen = set()
        if not group:
            group_ts_ms = ts_ms
        if owner_id in group_seen:
            continue
        group_seen.add(owner_id)
        group.append(owner_id)
    if group:
        groups.append(group)

    player_ids = next((candidate for candidate in reversed(groups) if len(candidate) >= len(roster)), [])
    if len(player_ids) < len(roster):
        return {}
    return {f"id_{actor_id}": roster[index] for index, actor_id in enumerate(player_ids[: len(roster)])}


def _infer_context_enemy_hint(text: str) -> str | None:
    dungeon_enemy_hints = _load_dungeon_enemy_hints()
    if dungeon_enemy_hints:
        for raw_line in text.splitlines():
            if (
                " DUNGEON_CONTEXT " not in raw_line
                and not _OFFICIAL_TIMER_START_RE.search(raw_line)
                and not _OFFICIAL_TIMER_END_RE.search(raw_line)
            ):
                continue
            fields = _extract_fields(raw_line)
            for field_name in ("dungeonId", "dungeon_id", "gameId", "game_id"):
                enemy_key = dungeon_enemy_hints.get(str(fields.get(field_name) or ""))
                if enemy_key:
                    return enemy_key

    enemy_hints: set[str] = set()
    for raw_line in text.splitlines():
        if " HP_V2 " in raw_line:
            continue
        for enemy_key in _ENEMY_KEY_RE.findall(raw_line):
            if enemy_key != UNKNOWN_ENEMY_KEY:
                enemy_hints.add(enemy_key)
                if len(enemy_hints) > 1:
                    return None
    return next(iter(enemy_hints)) if len(enemy_hints) == 1 else None


def _infer_short_enemy_aliases(text: str, player_aliases: dict[str, str]) -> dict[str, str]:
    if not player_aliases:
        return {}
    player_ids = set(player_aliases)
    counts: Counter[str] = Counter()
    for raw_line in text.splitlines():
        if " HP_V2 " not in raw_line:
            continue
        fields = _extract_fields(raw_line)
        src = fields.get("src") or fields.get("atk")
        target = fields.get("tgt")
        if src in player_ids and target and _short_actor_number(target) and target not in player_ids:
            counts[target] += 1
    enemy_alias = _infer_context_enemy_hint(text) or UNKNOWN_ENEMY_KEY
    return {actor_id: enemy_alias for actor_id, _count in counts.most_common()}


def _apply_short_actor_aliases(text: str) -> str:
    player_aliases = _infer_short_actor_aliases_from_loadout(text)
    if not player_aliases:
        player_aliases = _infer_short_actor_aliases_from_fingerprints(text)
    if not player_aliases:
        return text
    aliases = {**player_aliases, **_infer_short_enemy_aliases(text, player_aliases)}
    if not aliases:
        return text
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line
        for short_id, alias in aliases.items():
            line = line.replace(short_id, alias)
        lines.append(line)
    return "\n".join(lines)


def _extract_character_key(*values: str | None) -> str | None:
    for value in values:
        if not value:
            continue
        match = _CHAR_KEY_RE.search(value)
        if match:
            return match.group(1)
    return None


def _extract_enemy_key(*values: str | None) -> str | None:
    for value in values:
        if not value:
            continue
        full_match = _FULL_ENEMY_KEY_RE.match(value)
        if full_match:
            return full_match.group(1)
        match = _ENEMY_KEY_RE.search(value)
        if match:
            return match.group(1)
    return None


def _collect_party_actor_ids(raw_line: str) -> set[str]:
    actor_ids: set[str] = set()
    if " SQUAD " in raw_line:
        actor_ids.update(match.group(2) for match in _SQUAD_MEMBER_RE.finditer(raw_line))
    if " ENTITY_STATS " in raw_line:
        fields = _extract_fields(raw_line)
        if fields.get("kind") == "character" and _extract_character_key(fields.get("template")):
            actor_id = fields.get("id")
            if actor_id:
                actor_ids.add(actor_id)
    return actor_ids


def _recover_enemy_target_from_mislabeled_actor(
    fields: dict[str, str],
    *,
    context_enemy_hint: str | None,
    party_actor_ids: set[str],
) -> str | None:
    if not party_actor_ids:
        return None
    target_id = fields.get("tgtId") or fields.get("targetId")
    if not target_id or target_id in party_actor_ids:
        return None
    if fields.get("eHP") is None:
        return None
    if not _extract_character_key(fields.get("tgt")):
        return None
    return context_enemy_hint or UNKNOWN_ENEMY_KEY


_ENEMY_DEFENSE_EFFECT_BB_KEYS = {
    "additional_def_decrease",
    "all_resistance_decrease",
    "def_decrease",
    "def_decrease_tick",
    "def_decrease_tick_final",
    "final_spell_resistance_decrease",
    "max_def_decrease",
    "physical_res_down",
    "physical_vulnerable_dmg_increase",
    "phy_resist_down",
    "spell_damage_taken_up",
    "spell_resistance_decrease",
    "spell_taken_up",
    "start_def_decrease",
}

_PHYSICAL_DAMAGE_ELEMENT_BB_KEYS = {
    "physical_res_down",
    "physical_vulnerable_dmg_increase",
    "phy_resist_down",
}

_FINAL_BB_KEY_OVERRIDES = {
    "spell_resistance_decrease": "final_spell_resistance_decrease",
}


def _bb_key_damage_type_condition(bb_key: str | None) -> dict[str, Any] | None:
    if str(bb_key or "").lower() not in _PHYSICAL_DAMAGE_ELEMENT_BB_KEYS:
        return None
    return {
        "type": "damage_type_in",
        "source": "blackboard_key",
        "elements": ["physical"],
    }


def _attach_bb_key_damage_type_condition(effect: dict[str, Any], bb_key: str | None) -> None:
    if effect.get("condition"):
        return
    condition = _bb_key_damage_type_condition(bb_key)
    if condition is not None:
        effect["condition"] = condition


def _record_has_enemy_defense_effect(record: dict[str, Any], bb_values: dict[str, Any]) -> bool:
    bb_keys = {str(key).lower() for key in bb_values}
    if bb_keys & _ENEMY_DEFENSE_EFFECT_BB_KEYS:
        return True

    event_key = _normalize_buff_id(record.get("event_key")).lower()
    if "conduct_triggered" in event_key:
        return True
    if "corrupt_triggered" in event_key or "corrupt_do" in event_key:
        return True
    if re.match(r"^buff_common_(?:try_)?natural_(?:fire|pulse|cryst|natural)_triggered(?:_wrapper)?$", event_key):
        return True
    return False


def _bb_duration_ms_for_enemy_defense_effect(bb_values: dict[str, Any]) -> int | None:
    for key in ("duration", "corrupt_duration", "duration_corrupt", "duration_corrupt_final"):
        duration = _safe_positive_rate(bb_values.get(key))
        if duration is not None:
            return int(duration * 1000)
    return None


def _apply_enemy_status_bb_overrides(
    record: dict[str, Any],
    *,
    context_enemy_hint: str | None,
) -> None:
    bb_values = {str(key).lower(): value for key, value in (record.get("bb_values") or {}).items()}
    if not _record_has_enemy_defense_effect(record, bb_values):
        return

    if record.get("target_character_key") and not record.get("target_enemy_key"):
        enemy_key = context_enemy_hint or UNKNOWN_ENEMY_KEY
        record["target_enemy_key"] = enemy_key
        record["target_enemy_name"] = _resolve_enemy_name(enemy_key) or enemy_key
        record["target_character_key"] = None
        record["target_character_name"] = None

    duration_ms = _bb_duration_ms_for_enemy_defense_effect(bb_values)
    if duration_ms is not None:
        raw_duration_ms = record.get("raw_duration_ms")
        if raw_duration_ms is None or duration_ms < int(raw_duration_ms or 0):
            record["raw_duration_ms"] = duration_ms
            record["raw_duration_source"] = "bb"


def _coerce_int(value: str | None, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(float(value))
    except ValueError:
        return default


def _cap_enemy_overkill_damage(
    hit_value: int,
    *,
    enemy_hp_after: int | None,
    previous_enemy_hp: int | None,
) -> int:
    if hit_value <= 0 or enemy_hp_after is None or previous_enemy_hp is None:
        return hit_value
    if previous_enemy_hp <= 0 and enemy_hp_after <= 0:
        return 0
    if enemy_hp_after <= 0 and previous_enemy_hp > 0:
        return min(hit_value, previous_enemy_hp)
    return hit_value


def _coerce_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _annotate_hit_enemy_hp_state(hits: list[dict[str, Any]]) -> None:
    previous_enemy_hp_by_target: dict[str, int] = {}
    observed_max_hp_by_target: dict[str, int] = {}

    for hit in hits:
        target_enemy_key = str(hit.get("target_enemy_key") or "")
        enemy_hp_after = _coerce_optional_int(hit.get("enemy_hp_after"))
        if not target_enemy_key or enemy_hp_after is None:
            continue

        previous_enemy_hp = previous_enemy_hp_by_target.get(target_enemy_key)
        hit_value = max(0, _coerce_optional_int(hit.get("hit_value")) or 0)
        if previous_enemy_hp is not None and previous_enemy_hp >= enemy_hp_after:
            enemy_hp_before = previous_enemy_hp
            source = "previous_enemy_hp"
        else:
            enemy_hp_before = enemy_hp_after + hit_value
            source = "enemy_hp_after_plus_hit"

        hit["enemy_hp_before"] = enemy_hp_before
        hit["enemy_hp_before_source"] = source
        observed_max_hp_by_target[target_enemy_key] = max(
            observed_max_hp_by_target.get(target_enemy_key, 0),
            enemy_hp_before,
            enemy_hp_after,
        )
        previous_enemy_hp_by_target[target_enemy_key] = enemy_hp_after

    for hit in hits:
        target_enemy_key = str(hit.get("target_enemy_key") or "")
        observed_max_hp = observed_max_hp_by_target.get(target_enemy_key)
        enemy_hp_before = _coerce_optional_int(hit.get("enemy_hp_before"))
        if observed_max_hp is None or observed_max_hp <= 0:
            continue
        hit["target_enemy_observed_max_hp"] = observed_max_hp
        if enemy_hp_before is not None:
            hit["target_enemy_hp_ratio_before"] = enemy_hp_before / observed_max_hp


def _new_participant_totals() -> defaultdict[str, dict[str, Any]]:
    return defaultdict(
        lambda: {
            "character_key": None,
            "character_name": None,
            "total_damage": 0,
            "max_hit": 0,
            "crit_hits": 0,
            "hit_count": 0,
        }
    )


def _recompute_participant_visual_max_hits(
    hits: list[dict[str, Any]],
    participant_totals: defaultdict[str, dict[str, Any]],
) -> None:
    grouped_max: dict[str, int] = defaultdict(int)
    last_group: dict[tuple[str, str, str], dict[str, int]] = {}

    ordered_hits = sorted(
        hits,
        key=lambda item: (
            int(item.get("ts_ms") or 0),
            str(item.get("character_key") or ""),
            str(item.get("skill_key") or ""),
        ),
    )
    for hit in ordered_hits:
        character_key = str(hit.get("character_key") or "")
        if not character_key:
            continue
        target_key = str(hit.get("target_enemy_key") or "")
        skill_key = str(hit.get("skill_key") or "")
        ts_ms = int(hit.get("ts_ms") or 0)
        hit_value = int(hit.get("hit_value") or 0)
        group_key = (character_key, target_key, skill_key)
        current = last_group.get(group_key)
        if current is None or ts_ms - current["last_ts_ms"] > _VISUAL_HIT_GROUP_WINDOW_MS:
            current = {"sum": hit_value, "last_ts_ms": ts_ms}
            last_group[group_key] = current
        else:
            current["sum"] += hit_value
            current["last_ts_ms"] = ts_ms
        grouped_max[character_key] = max(grouped_max[character_key], current["sum"])

    for character_key, participant in participant_totals.items():
        participant["max_hit"] = max(int(participant.get("max_hit") or 0), int(grouped_max.get(character_key) or 0))


def _new_skill_totals() -> defaultdict[tuple[str, str], dict[str, Any]]:
    return defaultdict(
        lambda: {
            "character_key": None,
            "character_name": None,
            "skill_key": None,
            "skill_name": None,
            "total_damage": 0,
            "max_damage": 0,
            "hit_count": 0,
            "cast_count": 0,
        }
    )


def _rebuild_hit_totals(
    hits: list[dict[str, Any]],
    buff_starts: list[dict[str, Any]],
) -> tuple[
    defaultdict[str, dict[str, Any]],
    defaultdict[tuple[str, str], dict[str, Any]],
    list[str],
    set[str],
    Counter[str],
]:
    participant_totals = _new_participant_totals()
    skill_totals = _new_skill_totals()
    roster_seen: set[str] = set()
    roster_order: list[str] = []
    enemy_counter: Counter[str] = Counter()

    for hit in hits:
        character_key = str(hit.get("character_key") or "")
        if not character_key:
            continue
        if character_key not in roster_seen:
            roster_seen.add(character_key)
            roster_order.append(character_key)
        enemy_key = str(hit.get("target_enemy_key") or "")
        if enemy_key:
            enemy_counter[enemy_key] += 1

        hit_value = int(hit.get("hit_value") or 0)
        crit_flag = int(hit.get("crit_flag") or 0)
        participant = participant_totals[character_key]
        participant["character_key"] = character_key
        participant["character_name"] = hit.get("character_name") or _resolve_character_name(character_key) or character_key
        participant["total_damage"] += hit_value
        participant["max_hit"] = max(participant["max_hit"], hit_value)
        participant["crit_hits"] += 1 if crit_flag else 0
        participant["hit_count"] += 1

        skill_key = str(hit.get("skill_key") or "unknown_skill")
        skill_entry = skill_totals[(character_key, skill_key)]
        skill_entry["character_key"] = character_key
        skill_entry["character_name"] = participant["character_name"]
        skill_entry["skill_key"] = skill_key
        skill_entry["skill_name"] = hit.get("skill_name") or _resolve_skill_name(skill_key) or skill_key
        skill_entry["total_damage"] += hit_value
        skill_entry["max_damage"] = max(skill_entry["max_damage"], hit_value)
        skill_entry["hit_count"] += 1
        if int(hit.get("hit_index") or 1) == 1:
            skill_entry["cast_count"] += 1

    for buff_record in buff_starts:
        for character_key in (buff_record.get("source_character_key"), buff_record.get("target_character_key")):
            if not character_key:
                continue
            character_key = str(character_key)
            if character_key not in roster_seen:
                roster_seen.add(character_key)
                roster_order.append(character_key)
            participant = participant_totals[character_key]
            participant["character_key"] = character_key
            participant["character_name"] = _resolve_character_name(character_key) or character_key

    _recompute_participant_visual_max_hits(hits, participant_totals)

    return participant_totals, skill_totals, roster_order, roster_seen, enemy_counter


def _retarget_unknown_enemy_hits(
    hits: list[dict[str, Any]],
    buff_starts: list[dict[str, Any]],
    enemy_key: str | None,
) -> bool:
    if not enemy_key or enemy_key == UNKNOWN_ENEMY_KEY:
        return False
    changed = False
    enemy_name = _resolve_enemy_name(enemy_key) or enemy_key
    for hit in hits:
        if hit.get("target_enemy_key") != UNKNOWN_ENEMY_KEY:
            continue
        hit["target_enemy_key"] = enemy_key
        hit["target_enemy_name"] = enemy_name
        changed = True
    for buff_record in buff_starts:
        if buff_record.get("target_enemy_key") != UNKNOWN_ENEMY_KEY:
            continue
        buff_record["target_enemy_key"] = enemy_key
        buff_record["target_enemy_name"] = enemy_name
    return changed


def _filter_buff_starts_for_timer_window(
    buff_starts: list[dict[str, Any]],
    *,
    battle_start_ms: int,
) -> list[dict[str, Any]]:
    def overlaps_start(buff_record: dict[str, Any]) -> bool:
        start_ts_ms = int(buff_record.get("ts_ms") or 0)
        if start_ts_ms >= battle_start_ms:
            return True
        end_ts_ms = buff_record.get("end_ts_ms")
        if end_ts_ms is not None:
            return int(end_ts_ms) >= battle_start_ms
        raw_duration_ms = buff_record.get("raw_duration_ms")
        if raw_duration_ms is not None and int(raw_duration_ms or 0) > 0:
            return start_ts_ms + int(raw_duration_ms) >= battle_start_ms
        packet_seen_ts_ms = buff_record.get("packet_modifier_last_seen_ts_ms")
        if packet_seen_ts_ms is not None:
            return int(packet_seen_ts_ms) >= battle_start_ms
        return False

    return [
        buff_record
        for buff_record in buff_starts
        if not (
            buff_record.get("target_enemy_key")
            and int(buff_record.get("ts_ms") or 0) < battle_start_ms
            and not overlaps_start(buff_record)
        )
    ]


def _coerce_float(value: str | None, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _coerce_optional_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _parse_zone_values(blob: str | None) -> list[float]:
    values: list[float] = []
    for part in (blob or "").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            values.append(float(part))
        except ValueError:
            values.append(1.0)
    return values


def _parse_dpd_raw_line(line: str) -> dict[str, Any] | None:
    match = _DPD_RAW_RE.search(line)
    if not match:
        return None
    return {
        "seq": int(match.group("seq")),
        "calc": _coerce_float(match.group("calc")),
        "atk_scale": _coerce_float(match.group("atk_scale")),
        "blocked": _coerce_int(match.group("blocked")),
        "damage_type_raw": match.group("damage_type"),
        "decorate_mask_raw": match.group("decorate_mask"),
        "collider": match.group("collider"),
        "atk_zones": _parse_zone_values(match.group("atk_zones")),
        "def_zones": _parse_zone_values(match.group("def_zones")),
    }


def _damage_element_from_dpd_raw(dpd_raw: dict[str, Any] | None) -> str | None:
    if not isinstance(dpd_raw, dict):
        return None
    raw_value = dpd_raw.get("damage_type", dpd_raw.get("damageType"))
    if raw_value is None:
        raw_value = dpd_raw.get("damage_type_raw", dpd_raw.get("damageTypeRaw"))
    if raw_value is None:
        return None
    try:
        damage_type = int(str(raw_value), 16) if str(raw_value).lower().startswith("0x") else int(raw_value)
    except (TypeError, ValueError):
        return None
    return _DPD_DAMAGE_TYPE_TO_ELEMENT.get(damage_type)


def _parse_baseline_line(line: str) -> tuple[int, dict[int, float]] | None:
    match = _BASELINE_RE.search(line)
    if not match:
        return None
    return (
        int(match.group("seq")),
        {
            int(key): _coerce_float(value)
            for key, value in _BASELINE_KV_RE.findall(match.group("body"))
        },
    )


def _parse_packet_modifier_line(line: str) -> tuple[int, list[str], list[str]] | None:
    match = _PKT_MOD_RE.search(line)
    if not match:
        return None
    attacker = [item for item in match.group("atk").split() if item]
    defender = [item for item in match.group("def").split() if item]
    return int(match.group("seq")), attacker, defender


def _parse_packet_attr_line(line: str) -> tuple[int, list[str], list[str]] | None:
    match = _PKT_ATTR_RE.search(line)
    if not match:
        return None
    attacker = [item for item in match.group("atk").split() if item]
    defender = [item for item in match.group("def").split() if item]
    return int(match.group("seq")), attacker, defender


def _packet_attr_allowed_effects(tokens: list[str] | None) -> set[tuple[str, str]]:
    allowed: set[tuple[str, str]] = set()
    for token in tokens or []:
        head = str(token).split(":", 1)[0]
        try:
            attr_type = int(head)
        except (TypeError, ValueError):
            continue
        mapping = _ATTR_TYPE_TO_EFFECT.get(attr_type)
        if mapping is None:
            continue
        zone, element = mapping
        allowed.add((str(zone), str(element or "all")))
    return allowed


def _dpd_bucket_value_for_zone(zone: str, dpd_raw: dict[str, Any] | None) -> float | None:
    if not dpd_raw:
        return None
    bucket = _DPD_ZONE_BUCKETS.get(zone)
    if bucket is None:
        return None
    side, index = bucket
    values = dpd_raw.get("atk_zones") if side == "atk" else dpd_raw.get("def_zones")
    if not values or index >= len(values):
        return None
    try:
        return float(values[index])
    except (TypeError, ValueError):
        return None


def _round4(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        return None


def _sort_rdps_debug_zones(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        items,
        key=lambda item: (
            _RDPS_DEBUG_ZONE_ORDER.get(str(item.get("zone") or ""), 99),
            str(item.get("zone") or ""),
        ),
    )


def _rdps_debug_record_applicable_effect(
    *,
    window: dict[str, Any],
    effect: dict[str, Any],
    scope: str,
    rdps_credit: float | None = None,
) -> dict[str, Any]:
    source_key = window.get("source_character_key")
    raw_source_key = window.get("raw_source_character_key")
    zone = str(effect.get("zone") or "")
    row = {
        "scope": scope,
        "source_character_key": source_key,
        "source_character_name": window.get("source_character_name")
        or _resolve_character_name(source_key)
        or source_key,
        "raw_source_character_key": raw_source_key,
        "raw_source_character_name": window.get("raw_source_character_name")
        or _resolve_character_name(raw_source_key)
        or raw_source_key,
        "raw_source": window.get("raw_source"),
        "target_character_key": window.get("target_character_key"),
        "target_character_name": window.get("target_character_name"),
        "owner_raw": window.get("owner_raw"),
        "event_key": window.get("event_key"),
        "event_name": window.get("event_name"),
        "uid": window.get("uid"),
        "uid_aliases": list(window.get("uid_aliases") or []),
        "start_ts_ms": window.get("start_ts_ms"),
        "start_time": window.get("start_time"),
        "end_ts_ms": window.get("end_ts_ms"),
        "end_time": window.get("end_time"),
        "zone": zone,
        "zone_label": _RDPS_DEBUG_ZONE_LABELS.get(zone, zone),
        "element": str(effect.get("element") or "all"),
        "rate": _round4(effect.get("rate") or 0.0),
        "rdps_credit": _round4(rdps_credit),
    }
    condition = effect.get("condition")
    if isinstance(condition, dict):
        row["condition"] = dict(condition)
    return row


def _rdps_debug_record_dpd_self_residual(
    *,
    hit: dict[str, Any],
    zone: str,
    rate: float,
) -> dict[str, Any]:
    attacker_key = str(hit.get("character_key") or "")
    attacker_name = str(hit.get("character_name") or _resolve_character_name(attacker_key) or attacker_key)
    return {
        "scope": "self",
        "source_character_key": attacker_key,
        "source_character_name": attacker_name,
        "raw_source_character_key": attacker_key,
        "raw_source_character_name": attacker_name,
        "raw_source": "DPD_RAW",
        "target_character_key": attacker_key,
        "target_character_name": attacker_name,
        "owner_raw": "DPD_RAW",
        "event_key": "__dpd_self_residual__",
        "event_name": "自身基线/未归因（DPD残差）",
        "uid": None,
        "start_ts_ms": None,
        "start_time": None,
        "end_ts_ms": None,
        "end_time": None,
        "zone": zone,
        "zone_label": _RDPS_DEBUG_ZONE_LABELS.get(zone, zone),
        "element": str(hit.get("damage_element") or "all"),
        "rate": _round4(rate),
        "rdps_credit": None,
    }


def _rdps_debug_record_baseline_self(
    *,
    hit: dict[str, Any],
    attr_type: int,
    zone: str,
    element: str,
    rate: float,
    final_value: float,
    captured: float,
) -> dict[str, Any]:
    attacker_key = str(hit.get("character_key") or "")
    attacker_name = str(hit.get("character_name") or _resolve_character_name(attacker_key) or attacker_key)
    label = _ATTR_TYPE_BUFF_LABELS.get(attr_type) or _RDPS_DEBUG_ZONE_LABELS.get(zone, zone)
    return {
        "scope": "self",
        "source_character_key": attacker_key,
        "source_character_name": attacker_name,
        "raw_source_character_key": attacker_key,
        "raw_source_character_name": attacker_name,
        "raw_source": "BASELINE",
        "target_character_key": attacker_key,
        "target_character_name": attacker_name,
        "owner_raw": "BASELINE",
        "event_key": f"__baseline_attr_{attr_type}__",
        "event_name": f"自身属性基线（{label} / attrType={attr_type}）",
        "uid": None,
        "start_ts_ms": None,
        "start_time": None,
        "end_ts_ms": None,
        "end_time": None,
        "zone": zone,
        "zone_label": _RDPS_DEBUG_ZONE_LABELS.get(zone, zone),
        "element": element,
        "rate": _round4(rate),
        "rdps_credit": None,
        "baseline_final": _round4(final_value),
        "baseline_captured": _round4(captured),
    }


def _rdps_debug_record_static_self(
    *,
    hit: dict[str, Any],
    entry: dict[str, Any],
) -> dict[str, Any]:
    attacker_key = str(hit.get("character_key") or "")
    attacker_name = str(hit.get("character_name") or _resolve_character_name(attacker_key) or attacker_key)
    zone = str(entry.get("zone") or "")
    source_type = str(entry.get("source_type") or "static")
    source_name = str(entry.get("source_name") or "静态来源")
    return {
        "scope": "self",
        "source_character_key": attacker_key,
        "source_character_name": attacker_name,
        "raw_source_character_key": attacker_key,
        "raw_source_character_name": attacker_name,
        "raw_source": source_type,
        "target_character_key": attacker_key,
        "target_character_name": attacker_name,
        "owner_raw": source_type,
        "event_key": f"__static_self_{source_type}__",
        "event_name": f"自身静态基线（{source_name} / {entry.get('label') or zone}）",
        "uid": None,
        "start_ts_ms": None,
        "start_time": None,
        "end_ts_ms": None,
        "end_time": None,
        "zone": zone,
        "zone_label": _RDPS_DEBUG_ZONE_LABELS.get(zone, zone),
        "element": str(entry.get("element") or "all"),
        "rate": _round4(entry.get("rate") or 0.0),
        "rdps_credit": None,
        "note": entry.get("note"),
    }


def _effect_condition_failure(effect: dict[str, Any], hit: dict[str, Any]) -> dict[str, Any] | None:
    condition = effect.get("condition")
    if not isinstance(condition, dict):
        return None

    condition_type = str(condition.get("type") or "")
    if condition_type == "all":
        for child in condition.get("conditions") or []:
            if not isinstance(child, dict):
                continue
            failure = _effect_condition_failure({"condition": child}, hit)
            if failure:
                return {
                    **failure,
                    "compound_condition_type": condition_type,
                    "compound_condition_source": condition.get("source"),
                }
        return None

    if condition_type == "target_hp_ratio_lte":
        threshold = _safe_positive_rate(condition.get("threshold"))
        hp_before = _coerce_optional_int(hit.get("enemy_hp_before"))
        observed_max_hp = _coerce_optional_int(hit.get("target_enemy_observed_max_hp"))
        ratio = None
        try:
            if hit.get("target_enemy_hp_ratio_before") is not None:
                ratio = float(hit.get("target_enemy_hp_ratio_before"))
        except (TypeError, ValueError):
            ratio = None
        if ratio is None and hp_before is not None and observed_max_hp and observed_max_hp > 0:
            ratio = hp_before / observed_max_hp
        if threshold is None or ratio is None or hp_before is None or not observed_max_hp or observed_max_hp <= 0:
            return {
                "reason": "condition_state_missing",
                "reason_group": "condition_unobservable",
                "condition_type": condition_type,
                "condition_source": condition.get("source"),
                "condition_threshold": _round4(threshold),
                "target_hp_before": hp_before,
                "target_observed_max_hp": observed_max_hp,
                "target_hp_ratio_before": _round4(ratio),
            }
        if ratio > threshold + 0.000001:
            return {
                "reason": "target_hp_above_threshold",
                "reason_group": "condition_unsatisfied",
                "condition_type": condition_type,
                "condition_source": condition.get("source"),
                "condition_threshold": _round4(threshold),
                "target_hp_before": hp_before,
                "target_observed_max_hp": observed_max_hp,
                "target_hp_ratio_before": _round4(ratio),
            }
        return None

    if condition_type == "target_has_buff":
        required = {
            _normalize_buff_id(buff_id)
            for buff_id in condition.get("buff_ids") or []
            if _normalize_buff_id(buff_id)
        }
        active = {
            _normalize_buff_id(buff_id)
            for buff_id in hit.get("_active_target_buff_ids") or []
            if _normalize_buff_id(buff_id)
        }
        if not required:
            return {
                "reason": "condition_state_missing",
                "reason_group": "condition_unobservable",
                "condition_type": condition_type,
                "condition_source": condition.get("source"),
            }
        if not active or not (required & active):
            return {
                "reason": "target_buff_missing",
                "reason_group": "condition_unsatisfied",
                "condition_type": condition_type,
                "condition_source": condition.get("source"),
                "condition_buff_ids": sorted(required),
                "active_target_buff_ids": sorted(active),
            }
        return None

    if condition_type == "damage_type_in":
        elements = [
            str(element)
            for element in condition.get("elements") or []
            if str(element or "")
        ]
        damage_element = str(hit.get("damage_element") or "")
        damage_school = str(hit.get("damage_school") or "")
        if not elements or (not damage_element and not damage_school):
            return {
                "reason": "condition_state_missing",
                "reason_group": "condition_unobservable",
                "condition_type": condition_type,
                "condition_source": condition.get("source"),
                "condition_elements": elements,
                "damage_element": damage_element or None,
                "damage_school": damage_school or None,
            }

        def matches(required: str) -> bool:
            if required == "physical":
                return damage_element == "physical" or (not damage_element and damage_school == "physical")
            return damage_element == required

        if not any(matches(element) for element in elements):
            return {
                "reason": "damage_type_filtered",
                "reason_group": "condition_unsatisfied",
                "condition_type": condition_type,
                "condition_source": condition.get("source"),
                "condition_elements": elements,
                "damage_element": damage_element or None,
                "damage_school": damage_school or None,
            }
        return None

    return {
        "reason": "condition_type_unsupported",
        "reason_group": "condition_unobservable",
        "condition_type": condition_type,
        "condition_source": condition.get("source"),
    }


def _rdps_contribution_rows(
    contributions_map: dict[str, float],
    *,
    sort_by_value: bool,
) -> list[dict[str, Any]]:
    items = sorted(
        contributions_map.items(),
        key=(lambda item: (-item[1], item[0])) if sort_by_value else (lambda item: item[0]),
    )
    return [
        {
            "character_key": character_key,
            "character_name": _resolve_character_name(character_key) or character_key,
            "value": _round4(value),
        }
        for character_key, value in items
        if value > 0.0001
    ]


def _duration_ms_from_seconds(value: str | None) -> int | None:
    seconds = _coerce_float(value, default=-1.0)
    if seconds < 0:
        return None
    if seconds > 1_000_000:
        return None
    return int(round(seconds * 1000))


def _build_iso_datetime(reference_date: date, timestamp_ms: int, rollover_days: int = 0) -> str:
    midnight = datetime.combine(reference_date, time.min)
    result = midnight + timedelta(days=rollover_days, milliseconds=timestamp_ms)
    return result.astimezone().isoformat(timespec="seconds")


def _normalize_buff_id(buff_id: str | None) -> str:
    return str(buff_id or "unknown_buff")


def _is_canonical_packet_buff_key(buff_id: str | None) -> bool:
    text = _normalize_buff_id(buff_id)
    return bool(text) and text != "unknown_buff" and not text.isdigit()


def _prefer_packet_buff_record(previous: dict[str, Any], current: dict[str, Any]) -> bool:
    previous_key = _normalize_buff_id(previous.get("event_key"))
    current_key = _normalize_buff_id(current.get("event_key"))
    if previous_key == current_key:
        return False
    previous_canonical = _is_canonical_packet_buff_key(previous_key)
    current_canonical = _is_canonical_packet_buff_key(current_key)
    if current_canonical and not previous_canonical:
        return True
    if previous_canonical and not current_canonical:
        return False
    if current_key == "unknown_buff" and previous_key != "unknown_buff":
        return False
    if previous_key == "unknown_buff" and current_key != "unknown_buff":
        return True
    return False


def _is_noise_buff(buff_id: str) -> bool:
    return buff_id in _BUFF_NOISE_IDS or buff_id.startswith(_BUFF_NOISE_PREFIXES)


def _should_ignore_rate_buff(buff_id: str) -> bool:
    return any(pattern.search(buff_id) for pattern in _RATE_IGNORE_BUFF_PATTERNS)


def _should_ignore_record_rate_effects(record: dict[str, Any]) -> bool:
    buff_id = _normalize_buff_id(record.get("event_key"))
    if buff_id == "buff_equipsuit_atk_02_aruadetect":
        return True
    return False


def _is_effectless_wrapper_record(record: dict[str, Any]) -> bool:
    buff_id = _normalize_buff_id(record.get("event_key"))
    packet_mapping = record.get("packet_mapping")
    if isinstance(packet_mapping, dict) and str(packet_mapping.get("role") or "").lower() == "effect":
        return False
    entry = _load_local_buff_semantic_entries().get(buff_id)
    if isinstance(entry, dict):
        action_types = {str(item or "") for item in entry.get("actionTypes") or []}
        if "VulnerableAction" in action_types:
            return False
    if _is_internal_trigger_damage_record(record):
        return True
    if record.get("attr_mods"):
        return False
    if _is_packet_effectless_wrapper(record):
        return True
    hint = _buff_classifier_hint(buff_id) or {}
    classification = str(hint.get("classification") or "")
    if classification not in {"wrapper", "marker_or_utility"}:
        return False
    if hint.get("resolvedEffectHints") or int(hint.get("resolvedEffectCount") or 0) > 0:
        return False
    semantic_flags = hint.get("semanticFlags") if isinstance(hint.get("semanticFlags"), dict) else {}
    created_or_referenced_buff_ids = [
        str(child_id)
        for field in ("createdBuffIds", "referencedBuffIds", "binaryCreatedBuffIds", "binaryReferencedBuffIds")
        for child_id in hint.get(field) or []
        if str(child_id or "")
    ]
    if semantic_flags.get("hasDynamicBlackboard"):
        entry = _load_local_buff_semantic_entries().get(buff_id)
        if isinstance(entry, dict):
            action_types = {str(item or "") for item in entry.get("actionTypes") or []}
            created_or_referenced = {
                str(child_id)
                for field in ("createdBuffIds", "referencedBuffIds", "binaryCreatedBuffIds", "binaryReferencedBuffIds")
                for child_id in entry.get(field) or []
                if str(child_id or "")
            }
            if "OnSpellAbnormalStartFinish" in action_types and created_or_referenced:
                return True
        return False
    if classification == "wrapper" and created_or_referenced_buff_ids:
        return True
    created_buff_ids = [
        str(buff_id)
        for buff_id in hint.get("createdBuffIds") or []
        if str(buff_id or "")
    ]
    return bool(created_buff_ids) and all(_is_noise_buff(created_buff_id) for created_buff_id in created_buff_ids)


def _add_label(labels: set[str], label: str | None) -> None:
    if label:
        labels.add(label)


def _anomaly_status_labels(
    buff_id: str,
    *,
    source_key: str,
    target_is_enemy: bool,
    bb_values: dict[str, Any],
) -> set[str]:
    labels: set[str] = set()
    lowered = buff_id.lower()

    if lowered == "buff_physical_no_guard":
        labels.add("破防")
    elif lowered == "buff_physical_knockdown":
        labels.add("倒地")
    elif lowered == "buff_physical_airborne":
        labels.add("击飞")
    elif lowered == "buff_physical_crushed":
        labels.add("猛击")
    elif lowered == "buff_common_cryst_triggered_physical_break":
        labels.add("猛击")

    if "conduct_triggered" in lowered:
        labels.add("导电")
    if (
        "corrupt_triggered" in lowered
        or "corrupt_do" in lowered
        or re.match(r"^buff_common_(?:try_)?natural_(?:fire|pulse|cryst|natural)_triggered(?:_wrapper)?$", lowered)
    ):
        labels.add("腐蚀")
    if "fire_fire_triggered" in lowered or "burn" in lowered:
        labels.add("燃烧")

    same_element_burst = re.match(
        r"^buff_common_(fire|pulse|cryst|natural|spell)_\1_triggered(?:_wrapper|_do)?$",
        lowered,
    )
    if same_element_burst:
        labels.add("法术爆发")

    if (
        "frozen" in lowered
        and "physical_res_down" not in bb_values
        and "phy_resist_down" not in bb_values
    ):
        labels.add("冻结")

    if target_is_enemy and source_key == "chr_0029_pograni" and "physical_res_down" in bb_values:
        labels.add("碎甲")

    return labels


def _label_from_bb_key(
    bb_key: str,
    *,
    buff_id: str,
    target_is_enemy: bool,
) -> str | None:
    lowered = bb_key.lower()
    if not lowered or lowered in _BUFF_NOISE_BB_KEYS:
        return None
    if _buff_effect_bb_key_ignored(buff_id, lowered):
        return None
    if lowered in {"atk", "atk_up", "atk_up2"}:
        return "攻击提升"
    if lowered in {"phy_resist_down", "physical_res_down", "physical_vulnerable_dmg_increase"}:
        return "物理脆弱 / 碎甲"
    if lowered == "ratio_speed":
        return "加速"
    if lowered == "ratio_speedreduction":
        return "缓速"
    if lowered in {"crit_up", "crit_up2", "critical_rate"}:
        return "暴击"
    if lowered in {"crit_dmg", "critical_damage_inc"}:
        return "暴击伤害"
    if lowered in {"fire_up", "pulse_up", "cryst_up", "crystal_up", "natural_up", "physical_up", "physic_up"}:
        return "脆弱" if target_is_enemy else "增幅"
    if _is_damage_increase_bb_key(lowered) or lowered.endswith("_up_valid"):
        return "增伤"
    if lowered.endswith("_taken_up"):
        return "承伤易伤"
    if lowered == "def_down_damage":
        return "脆弱"
    if lowered in {"def_decrease", "additional_def_decrease"}:
        return "减抗"
    if lowered.endswith("_vul"):
        return "脆弱"
    if lowered.startswith("rate_") and "vulnerable" in lowered:
        return "脆弱"
    if lowered.startswith("enhance_"):
        return "增幅"
    if re.match(r"^(?:.+_)?taken_up_(?:physical|physic|fire|pulse|cryst|crystal|natural|spell)$", lowered):
        return "承伤易伤"
    if re.match(r"^damage_taken_up_(?:physical|physic|fire|pulse|cryst|crystal|natural|spell)$", lowered):
        return "承伤易伤"
    if lowered.endswith("_resistance_decrease") or lowered.endswith("_resistance_down"):
        return "承伤易伤"
    if lowered.endswith("_res_down") or (lowered.startswith("ignore_") and lowered.endswith("_resist")):
        return "减抗"
    if lowered == "combo_damageup":
        return "连击增伤"
    if lowered in {"atk_scale", "extra_atk_scale", "burning_atk_scale"} and target_is_enemy:
        buff_lower = buff_id.lower()
        if any(token in buff_lower for token in ("vulnerable", "fragile", "fracture")):
            return "脆弱"
        return None
    if lowered == "rate":
        buff_lower = buff_id.lower()
        if buff_lower in {
            "buff_chr_0015_lifeng_purify",
            "buff_chr_0015_lifeng_normal_skill_debuff",
            "buff_chr_0015_lifeng_normal_skill_debuff_icon",
        }:
            return "物理脆弱"
        if any(token in buff_lower for token in ("vulnerable", "fragile", "waterdebuff")):
            return "脆弱"
        if "enhance_" in buff_lower:
            return "增幅"
        if any(token in buff_lower for token in ("spellup", "dmg", "damage_increase")):
            return "增伤"
        if "criticalrate" in buff_lower:
            return "暴击"
        if "combo_damage" in buff_lower:
            return "连击增伤"
    return None


def _buff_effect_bb_key_ignored(buff_id: str, bb_key: str) -> bool:
    ignored_keys = _BUFF_EFFECT_BB_KEY_IGNORE_BY_ID.get(str(buff_id or "").lower())
    return ignored_keys is not None and str(bb_key or "").lower() in ignored_keys


def _collect_buff_labels(record: dict[str, Any]) -> list[str]:
    buff_id = _normalize_buff_id(record.get("event_key"))
    target_is_enemy = bool(record.get("target_enemy_key"))
    source_key = str(record.get("source_character_key") or "")
    bb_values = {str(key).lower(): value for key, value in (record.get("bb_values") or {}).items()}
    semantic_condition_effects = _collect_semantic_condition_zone_effects(record)
    anomaly_labels = _anomaly_status_labels(
        buff_id,
        source_key=source_key,
        target_is_enemy=target_is_enemy,
        bb_values=bb_values,
    )
    if _should_ignore_record_rate_effects(record):
        return sorted(anomaly_labels, key=lambda item: (_BUFF_LABEL_PRIORITY.get(item, 99), item))
    if _is_noise_buff(buff_id) or _should_ignore_rate_buff(buff_id):
        return sorted(anomaly_labels, key=lambda item: (_BUFF_LABEL_PRIORITY.get(item, 99), item))
    if _is_effectless_wrapper_record(record) and anomaly_labels and not semantic_condition_effects:
        return sorted(anomaly_labels, key=lambda item: (_BUFF_LABEL_PRIORITY.get(item, 99), item))
    if _is_effectless_wrapper_record(record) and not semantic_condition_effects:
        return []

    labels: set[str] = set(anomaly_labels)
    special_bb_labels: dict[str, str] = {}

    if buff_id == _GENERIC_COMBO_TRIGGER_BUFF_ID:
        labels.add("连击增伤")
    if buff_id in {
        "buff_chr_0015_lifeng_purify",
        "buff_chr_0015_lifeng_normal_skill_debuff",
        "buff_chr_0015_lifeng_normal_skill_debuff_icon",
    }:
        labels.add("物理脆弱")
    if buff_id == "buff_chr_0029_pograni_talent2":
        labels.add("铁卫标记")
    if "physical_res_down" in bb_values:
        if source_key == "chr_0029_pograni":
            special_bb_labels["physical_res_down"] = "碎甲"
            labels.add("碎甲")
        else:
            special_bb_labels["physical_res_down"] = "物理脆弱"
            labels.add("物理脆弱")
    if "phy_resist_down" in bb_values:
        special_bb_labels["phy_resist_down"] = "物理脆弱"

    semantic_bb_keys = {
        str(effect.get("bb_key") or "")
        for effect in semantic_condition_effects
        if str(effect.get("bb_key") or "")
    }
    semantic_bb_keys_lower = {key.lower() for key in semantic_bb_keys}
    packet_label_effects = [
        effect
        for effect in _packet_numeric_effects(record)
        if not (str(effect.get("bb_key") or "") and str(effect.get("bb_key") or "") in semantic_bb_keys)
    ]
    for effect in packet_label_effects + _packet_numeric_dynamic_effects(record):
        zone = str(effect.get("zone") or "")
        label = _EFFECT_ZONE_LABELS.get(zone)
        if label:
            labels.add(label)
    for effect in semantic_condition_effects:
        zone = str(effect.get("zone") or "")
        label = _EFFECT_ZONE_LABELS.get(zone)
        if label:
            labels.add(label)
    for bb_key in record.get("bb_keys") or []:
        lowered = str(bb_key).lower()
        if lowered in semantic_bb_keys_lower:
            continue
        if lowered in special_bb_labels:
            labels.add(special_bb_labels[lowered])
            continue
        _add_label(
            labels,
            _label_from_bb_key(
                str(bb_key),
                buff_id=buff_id,
                target_is_enemy=target_is_enemy,
            ),
        )

    attr_label_rows = record.get("attr_mods") or [
        {"attr_type": attr_type, "bb_key": ""}
        for attr_type in record.get("attr_types") or []
    ]
    for attr_mod in attr_label_rows:
        try:
            attr_type_int = int(attr_mod.get("attr_type"))
        except (TypeError, ValueError):
            continue
        bb_key = str(attr_mod.get("bb_key") or "").lower()
        if _buff_effect_bb_key_ignored(buff_id, bb_key):
            continue
        if bb_key in special_bb_labels:
            labels.add(special_bb_labels[bb_key])
            continue
        attr_effect = _ATTR_TYPE_TO_EFFECT.get(attr_type_int)
        if (
            attr_effect is not None
            and attr_effect[0] == "amp"
            and _is_damage_increase_bb_key(str(attr_mod.get("bb_key") or ""))
        ):
            continue
        if str(attr_mod.get("bb_key") or "") in _DEF_DECREASE_BASE_KEYS:
            labels.add("减抗")
            continue
        if attr_type_int in _FRAGILE_ATTR_TYPES:
            labels.add("脆弱")
            continue
        _add_label(labels, _ATTR_TYPE_BUFF_LABELS.get(attr_type_int))

    return sorted(labels, key=lambda item: (_BUFF_LABEL_PRIORITY.get(item, 99), item))


def _normalize_buff_duration_ms(
    start_ts_ms: int,
    *,
    event_key: str | None = None,
    end_ts_ms: int | None,
    raw_duration_ms: int | None,
    battle_end_ms: int,
) -> int:
    remaining_ms = max(battle_end_ms - start_ts_ms, 1)
    if _is_food_potion_buff(event_key) and raw_duration_ms is not None and raw_duration_ms > 0:
        return max(min(raw_duration_ms, remaining_ms), 1)

    candidates: list[int] = []
    if end_ts_ms is not None and end_ts_ms >= start_ts_ms:
        candidates.append(max(end_ts_ms - start_ts_ms, 1))
    if raw_duration_ms is not None and raw_duration_ms > 0:
        candidates.append(raw_duration_ms)
    if candidates:
        return max(min(min(candidates), remaining_ms), 1)

    if raw_duration_ms is None:
        return remaining_ms
    if raw_duration_ms <= 0:
        return min(remaining_ms, 1000)
    if raw_duration_ms > remaining_ms:
        return remaining_ms
    return raw_duration_ms


def _extend_buff_records_from_packet_modifiers(
    buff_starts: list[dict[str, Any]],
    packet_modifier_last_seen_by_uid: dict[str, int],
) -> None:
    for record in buff_starts:
        uid = str(record.get("uid") or "")
        if not uid:
            continue
        last_seen_ts_ms = packet_modifier_last_seen_by_uid.get(uid)
        if last_seen_ts_ms is None:
            continue
        start_ts_ms = int(record.get("ts_ms") or 0)
        if last_seen_ts_ms < start_ts_ms:
            continue

        seen_duration_ms = max(last_seen_ts_ms - start_ts_ms, 1)
        record["packet_modifier_last_seen_ts_ms"] = last_seen_ts_ms

        raw_duration_ms = record.get("raw_duration_ms")
        if raw_duration_ms is None or int(raw_duration_ms or 0) < seen_duration_ms:
            record["raw_duration_ms"] = seen_duration_ms
            record["raw_duration_source"] = "packet_modifier"
            if record.get("end_ts_ms") is None or int(record.get("end_ts_ms") or 0) < last_seen_ts_ms:
                record["end_ts_ms"] = last_seen_ts_ms
                record["inferred_end_source_type"] = "packet_modifier"
                record["inferred_end_source_key"] = uid
        elif record.get("end_ts_ms") is not None and int(record.get("end_ts_ms") or 0) < last_seen_ts_ms:
            record["end_ts_ms"] = last_seen_ts_ms
            record["inferred_end_source_type"] = "packet_modifier"
            record["inferred_end_source_key"] = uid


_RELATED_BUFF_LIFECYCLE_START_TOLERANCE_MS = 250


def _buff_record_lifecycle_target_key(record: dict[str, Any]) -> str:
    return str(
        record.get("target_character_key")
        or record.get("target_enemy_key")
        or record.get("owner_raw")
        or ""
    )


def _buff_record_lifecycle_lane_matches(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if str(left.get("source_character_key") or "") != str(right.get("source_character_key") or ""):
        return False
    if _buff_record_lifecycle_target_key(left) != _buff_record_lifecycle_target_key(right):
        return False
    return (
        abs(int(left.get("ts_ms") or 0) - int(right.get("ts_ms") or 0))
        <= _RELATED_BUFF_LIFECYCLE_START_TOLERANCE_MS
    )


def _buff_record_static_effect_pairs(record: dict[str, Any]) -> set[tuple[str, str, float]]:
    pairs: set[tuple[str, str, float]] = set()
    for effect in _collect_zone_effects(record):
        try:
            rate = round(float(effect.get("rate") or 0.0), 6)
        except (TypeError, ValueError):
            continue
        if rate <= 0:
            continue
        pairs.add(
            (
                str(effect.get("zone") or ""),
                _normalize_effect_element(effect.get("element")),
                rate,
            )
        )
    return pairs


def _buff_records_have_matching_lifecycle_effects(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_key = str(left.get("event_key") or "")
    right_key = str(right.get("event_key") or "")
    if not (left_key.endswith("_default_child") or right_key.endswith("_default_child")):
        return False
    left_pairs = _buff_record_static_effect_pairs(left)
    right_pairs = _buff_record_static_effect_pairs(right)
    if left_pairs & right_pairs:
        return True
    child_key = left_key if left_key.endswith("_default_child") else right_key
    parent_pairs = right_pairs if left_key.endswith("_default_child") else left_pairs
    if child_key.startswith("buff_common_affixes_vulnerable"):
        return any(zone in {"fragile", "vuln_taken", "res"} for zone, _element, _rate in parent_pairs)
    return False


def _buff_records_lifecycle_related(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_key = str(left.get("event_key") or "")
    right_key = str(right.get("event_key") or "")
    if not left_key or not right_key or left_key == right_key:
        return False
    return (
        _buff_semantically_reaches_buff(left_key, right_key)
        or _buff_semantically_reaches_buff(right_key, left_key)
        or _buff_records_have_matching_lifecycle_effects(left, right)
    )


def _record_has_authoritative_bb_duration(record: dict[str, Any]) -> bool:
    return str(record.get("raw_duration_source") or "") == "bb"


def _infer_related_buff_end_times(
    buff_starts: list[dict[str, Any]],
    skill_casts: list[dict[str, Any]],
) -> None:
    ended_buff_records = [
        record
        for record in buff_starts
        if record.get("end_ts_ms") is not None
        and int(record.get("end_ts_ms") or 0) >= int(record.get("ts_ms") or 0)
    ]
    ended_skill_casts = [
        cast
        for cast in skill_casts
        if cast.get("end_ts_ms") is not None
        and int(cast.get("end_ts_ms") or 0) >= int(cast.get("ts_ms") or 0)
    ]
    if not ended_buff_records and not ended_skill_casts:
        return

    for record in buff_starts:
        if record.get("end_ts_ms") is not None:
            continue
        if _record_has_authoritative_bb_duration(record):
            continue
        event_key = str(record.get("event_key") or "")
        source_key = str(record.get("source_character_key") or "")
        start_ts_ms = int(record.get("ts_ms") or 0)
        if not event_key or not source_key:
            continue
        inferred_ends: list[tuple[int, str, str]] = []
        for sibling in ended_buff_records:
            if sibling is record or not _buff_record_lifecycle_lane_matches(record, sibling):
                continue
            if _buff_records_lifecycle_related(record, sibling):
                inferred_ends.append(
                    (
                        int(sibling.get("end_ts_ms") or 0),
                        "related_buff",
                        str(sibling.get("event_key") or ""),
                    )
                )
        for cast in ended_skill_casts:
            if str(cast.get("source_character_key") or "") != source_key:
                continue
            if (
                abs(start_ts_ms - int(cast.get("ts_ms") or 0))
                > _RELATED_BUFF_LIFECYCLE_START_TOLERANCE_MS
            ):
                continue
            cast_skill = str(cast.get("skill") or "")
            if _skill_semantically_reaches_buff(cast_skill, event_key):
                inferred_ends.append((int(cast.get("end_ts_ms") or 0), "related_skill", cast_skill))
        valid_ends = [
            (end_ts_ms, source_type, source_key)
            for end_ts_ms, source_type, source_key in inferred_ends
            if end_ts_ms >= start_ts_ms
        ]
        if not valid_ends:
            continue
        packet_last_seen_ts_ms = record.get("packet_modifier_last_seen_ts_ms")
        if packet_last_seen_ts_ms is not None:
            try:
                packet_last_seen_int = int(packet_last_seen_ts_ms)
            except (TypeError, ValueError):
                packet_last_seen_int = 0
            if packet_last_seen_int >= start_ts_ms:
                ends_after_packet_evidence = [
                    (end_ts_ms, source_type, source_key)
                    for end_ts_ms, source_type, source_key in valid_ends
                    if end_ts_ms >= packet_last_seen_int
                ]
                if ends_after_packet_evidence:
                    valid_ends = ends_after_packet_evidence
                else:
                    record["end_ts_ms"] = packet_last_seen_int
                    record["inferred_end_source_type"] = "packet_modifier"
                    record["inferred_end_source_key"] = str(record.get("uid") or "")
                    continue
        end_ts_ms, source_type, inferred_from = min(valid_ends, key=lambda item: item[0])
        record["end_ts_ms"] = end_ts_ms
        record["inferred_end_source_type"] = source_type
        record["inferred_end_source_key"] = inferred_from


def _merge_buff_windows(buff_windows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not buff_windows:
        return []

    buff_windows.sort(
        key=lambda item: (
            item["source_character_key"] or "",
            item["target_character_key"] or "",
            item["event_key"],
            item["start_ts_ms"],
        )
    )
    merged: list[dict[str, Any]] = []
    for window in buff_windows:
        if not merged:
            merged.append(window)
            continue
        previous = merged[-1]
        same_lane = (
            previous["source_character_key"] == window["source_character_key"]
            and previous["target_character_key"] == window["target_character_key"]
            and previous["event_key"] == window["event_key"]
            and previous.get("skill_family_key") == window.get("skill_family_key")
        )
        if (
            same_lane
            and not _window_allows_stacking(previous)
            and not _window_allows_stacking(window)
            and int(window.get("start_ts_ms") or 0) <= int(previous.get("end_ts_ms") or 0) + _BUFF_MERGE_GAP_MS
            and _same_event_window_signature_matches(previous, window)
        ):
            _merge_window_content(previous, window)
            continue
        if (
            same_lane
            and _is_nonstacking_refresh_event(str(window.get("event_key") or ""))
            and previous["start_ts_ms"] <= window["start_ts_ms"] <= previous["end_ts_ms"] + _BUFF_MERGE_GAP_MS
        ):
            _merge_window_content(previous, window)
            continue
        if (
            same_lane
            and previous["end_ts_ms"] <= window["start_ts_ms"] <= previous["end_ts_ms"] + _BUFF_MERGE_GAP_MS
        ):
            _merge_window_content(previous, window)
            continue
        merged.append(window)
    return merged


def _window_uid_aliases(window: dict[str, Any]) -> set[str]:
    aliases: set[str] = set()
    uid = str(window.get("uid") or "")
    if uid:
        aliases.add(uid)
    for alias in window.get("uid_aliases") or []:
        text = str(alias or "")
        if text:
            aliases.add(text)
    return aliases


def _merge_window_uid_aliases(target: dict[str, Any], other: dict[str, Any]) -> None:
    aliases = _window_uid_aliases(target) | _window_uid_aliases(other)
    primary_uid = str(target.get("uid") or "")
    if primary_uid:
        aliases.discard(primary_uid)
    target["uid_aliases"] = sorted(aliases)


def _effect_condition_signature(effect: dict[str, Any]) -> str:
    condition = effect.get("condition")
    if not isinstance(condition, dict):
        return ""
    return json.dumps(condition, ensure_ascii=False, sort_keys=True)


def _effect_row_signature(effect: dict[str, Any]) -> tuple[Any, ...]:
    if "rate" in effect:
        return (
            "static",
            str(effect.get("zone") or ""),
            _normalize_effect_element(effect.get("element")),
            round(float(effect.get("rate") or 0.0), 6),
            str(effect.get("bb_key") or ""),
            int(effect.get("attr_type")) if effect.get("attr_type") is not None else None,
            _effect_condition_signature(effect),
        )
    return (
        "dynamic",
        str(effect.get("zone") or ""),
        _normalize_effect_element(effect.get("element")),
        round(float(effect.get("base_rate") or 0.0), 6),
        round(float(effect.get("tick_rate") or 0.0), 6),
        round(float(effect.get("max_rate") or 0.0), 6),
        round(float(effect.get("delayed_add_rate") or 0.0), 6),
        round(float(effect.get("delay_sec") or 0.0), 6),
        str(effect.get("bb_key") or ""),
        str(effect.get("add_bb_key") or ""),
        str(effect.get("delay_bb_key") or ""),
        _effect_condition_signature(effect),
    )


def _merge_effect_lists(primary: list[dict[str, Any]] | None, secondary: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for effect in [*(primary or []), *(secondary or [])]:
        if not isinstance(effect, dict):
            continue
        signature = _effect_row_signature(effect)
        if signature in seen:
            continue
        seen.add(signature)
        merged.append(dict(effect))
    return merged


def _prefer_window_event_name(primary: dict[str, Any], secondary: dict[str, Any]) -> str:
    primary_name = str(primary.get("event_name") or "")
    secondary_name = str(secondary.get("event_name") or "")
    event_key = str(primary.get("event_key") or secondary.get("event_key") or "")
    if primary_name and primary_name != event_key and secondary_name == event_key:
        return primary_name
    if secondary_name and secondary_name != event_key and primary_name == event_key:
        return secondary_name
    if len(secondary_name) > len(primary_name):
        return secondary_name
    return primary_name or secondary_name or event_key


def _merge_window_content(target: dict[str, Any], other: dict[str, Any]) -> None:
    target_start = int(target.get("start_ts_ms") or 0)
    other_start = int(other.get("start_ts_ms") or 0)
    target_line = int(target.get("start_line_no") or target.get("line_no") or 0)
    other_line = int(other.get("start_line_no") or other.get("line_no") or 0)
    if other_start < target_start or (other_start == target_start and other_line and (not target_line or other_line < target_line)):
        target["start_line_no"] = other_line
    _merge_window_uid_aliases(target, other)
    target["end_ts_ms"] = max(int(target.get("end_ts_ms") or 0), int(other.get("end_ts_ms") or 0))
    target["duration_ms"] = max(int(target["end_ts_ms"]) - int(target.get("start_ts_ms") or 0), 1)
    target["zone_effects"] = _merge_effect_lists(target.get("zone_effects"), other.get("zone_effects"))
    target["dynamic_effects"] = _merge_effect_lists(target.get("dynamic_effects"), other.get("dynamic_effects"))
    target["event_name"] = _prefer_window_event_name(target, other)
    if not target.get("stack_limit") and other.get("stack_limit"):
        target["stack_limit"] = other.get("stack_limit")


def _window_matches_packet_uids(window: dict[str, Any], packet_uids: set[str]) -> bool:
    if not packet_uids:
        return True
    aliases = _window_uid_aliases(window)
    if not aliases:
        return True
    return bool(aliases & packet_uids)


def _buff_window_stack_sort_key(window: dict[str, Any]) -> tuple[int, int, str]:
    uid = str(window.get("uid") or "")
    return (
        int(window.get("start_ts_ms") or 0),
        int(uid) if uid.isdigit() else 0,
        uid,
    )


def _buff_window_stack_group_key(window: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(window.get("event_key") or ""),
        str(window.get("source_character_key") or ""),
        str(window.get("target_character_key") or ""),
        str(window.get("skill_family_key") or ""),
    )


def _window_allows_stacking(window: dict[str, Any]) -> bool:
    stack_limit = _positive_int(window.get("stack_limit"))
    if stack_limit is not None and stack_limit > 1:
        return True
    return bool(_STACKABLE_EVENT_NAME_RE.search(str(window.get("event_key") or "")))


def _apply_buff_stack_limits(buff_windows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not buff_windows:
        return []

    uncapped: list[dict[str, Any]] = []
    grouped: defaultdict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for window in buff_windows:
        limit = _positive_int(window.get("stack_limit"))
        if limit is None:
            limit = _buff_stack_limit(str(window.get("event_key") or ""))
        if limit is None:
            uncapped.append(window)
            continue
        capped_window = dict(window)
        capped_window["stack_limit"] = limit
        grouped[_buff_window_stack_group_key(capped_window)].append(capped_window)

    capped: list[dict[str, Any]] = []
    for windows in grouped.values():
        active: list[dict[str, Any]] = []
        for window in sorted(windows, key=_buff_window_stack_sort_key):
            start_ts_ms = int(window.get("start_ts_ms") or 0)
            active = [item for item in active if int(item.get("end_ts_ms") or 0) >= start_ts_ms]
            active.append(window)
            active.sort(key=_buff_window_stack_sort_key)
            limit = int(window["stack_limit"])
            while len(active) > limit:
                expired = active.pop(0)
                old_end_ts_ms = int(expired.get("end_ts_ms") or 0)
                expired["end_ts_ms"] = min(old_end_ts_ms, start_ts_ms - 1)
        capped.extend(windows)

    limited = [
        window
        for window in [*uncapped, *capped]
        if int(window.get("end_ts_ms") or 0) >= int(window.get("start_ts_ms") or 0)
    ]
    for window in limited:
        window["duration_ms"] = max(int(window["end_ts_ms"]) - int(window["start_ts_ms"]), 1)
    return sorted(limited, key=lambda item: (int(item.get("start_ts_ms") or 0), str(item.get("event_key") or "")))


def _static_effect_signature(window: dict[str, Any]) -> tuple[tuple[Any, ...], ...] | None:
    if window.get("dynamic_effects"):
        return None
    effects = window.get("zone_effects") or []
    if not effects:
        return None
    signature: list[tuple[Any, ...]] = []
    for effect in effects:
        try:
            rate = round(float(effect.get("rate") or 0.0), 4)
        except (TypeError, ValueError):
            return None
        if rate <= 0:
            return None
        signature.append(
            (
                str(effect.get("zone") or ""),
                _normalize_effect_element(effect.get("element")),
                rate,
                _effect_condition_signature(effect),
            )
        )
    return tuple(sorted(signature))


def _dynamic_effect_signature(window: dict[str, Any]) -> tuple[tuple[str, str, float, float, float, float, float], ...] | None:
    effects = window.get("dynamic_effects") or []
    if not effects:
        return None
    signature: list[tuple[str, str, float, float, float, float, float]] = []
    for effect in effects:
        try:
            signature.append(
                (
                    str(effect.get("zone") or ""),
                    _normalize_effect_element(effect.get("element")),
                    round(float(effect.get("base_rate") or 0.0), 6),
                    round(float(effect.get("tick_rate") or 0.0), 6),
                    round(float(effect.get("max_rate") or 0.0), 6),
                    round(float(effect.get("delayed_add_rate") or 0.0), 6),
                    round(float(effect.get("delay_sec") or 0.0), 6),
                )
            )
        except (TypeError, ValueError):
            return None
    return tuple(sorted(signature))


def _window_detail_count(window: dict[str, Any]) -> int:
    return len(window.get("zone_effects") or []) + len(window.get("dynamic_effects") or [])


def _same_event_window_signature_matches(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_static = set(_static_effect_signature(left) or [])
    right_static = set(_static_effect_signature(right) or [])
    left_dynamic = _dynamic_effect_signature(left)
    right_dynamic = _dynamic_effect_signature(right)
    if left_dynamic != right_dynamic:
        return False
    if left_static == right_static:
        return True
    if not left_static or not right_static:
        return True
    return left_static.issuperset(right_static) or right_static.issuperset(left_static)


def _mirror_preference_score(window: dict[str, Any]) -> int:
    event_key = str(window.get("event_key") or "")
    hint = _buff_classifier_hint(event_key) or {}
    classification = hint.get("classification")
    score = 0
    if int(window.get("modifier_count") or 0) > 0:
        score += 4
    if classification == "effect_buff":
        score += 3
    elif classification == "wrapper":
        score -= 2
    elif classification == "marker_or_utility":
        score -= 3
    lowered = event_key.lower()
    if "icon" in lowered or "vfx" in lowered:
        score -= 1
    return score


def _event_key_parent_of_default_child(event_key: str | None) -> str | None:
    text = str(event_key or "")
    suffix = "_default_child"
    if not text.endswith(suffix):
        return None
    return text[: -len(suffix)]


def _effect_elements_compatible(parent_element: str, child_element: str) -> bool:
    if parent_element == child_element:
        return True
    if child_element == "all":
        return True
    if child_element == "spell":
        return parent_element in _ELEMENTAL_ELEMENTS or parent_element == "spell"
    return False


def _parent_window_covers_default_child(parent: dict[str, Any], child: dict[str, Any]) -> bool:
    parent_effects = parent.get("zone_effects") or []
    child_effects = child.get("zone_effects") or []
    if not parent_effects or not child_effects:
        return False

    parent_elements_by_lane: defaultdict[tuple[str, float], set[str]] = defaultdict(set)
    for effect in parent_effects:
        try:
            rate = round(float(effect.get("rate") or 0.0), 6)
        except (TypeError, ValueError):
            continue
        if rate <= 0:
            continue
        lane = (str(effect.get("zone") or ""), rate)
        parent_elements_by_lane[lane].add(_normalize_effect_element(effect.get("element")))

    for child_effect in child_effects:
        try:
            child_rate = round(float(child_effect.get("rate") or 0.0), 6)
        except (TypeError, ValueError):
            return False
        child_lane = (str(child_effect.get("zone") or ""), child_rate)
        parent_elements = parent_elements_by_lane.get(child_lane)
        if not parent_elements:
            return False
        child_element = _normalize_effect_element(child_effect.get("element"))
        if child_element in {"spell", "all"} and len(parent_elements & _ELEMENTAL_ELEMENTS) < 2:
            if child_element not in parent_elements and "all" not in parent_elements:
                return False
        elif not any(_effect_elements_compatible(parent_element, child_element) for parent_element in parent_elements):
            return False
    return True


@lru_cache(maxsize=4096)
def _created_child_buff_ids(buff_id: str) -> set[str]:
    ids: set[str] = set()
    entry = _load_local_buff_semantic_entries().get(str(buff_id or ""))
    if isinstance(entry, dict):
        ids.update(str(value) for value in entry.get("createdBuffIds") or [] if str(value or ""))
    hint = _buff_classifier_hint(str(buff_id or "")) or {}
    ids.update(str(value) for value in hint.get("createdBuffIds") or [] if str(value or ""))
    return ids


def _window_static_effect_pairs(window: dict[str, Any]) -> set[tuple[str, str, float]]:
    pairs: set[tuple[str, str, float]] = set()
    for effect in window.get("zone_effects") or []:
        try:
            rate = round(float(effect.get("rate") or 0.0), 6)
        except (TypeError, ValueError):
            continue
        if rate <= 0:
            continue
        pairs.add(
            (
                str(effect.get("zone") or ""),
                _normalize_effect_element(effect.get("element")),
                rate,
            )
        )
    return pairs


def _window_matches_same_lane(parent: dict[str, Any], child: dict[str, Any]) -> bool:
    return (
        parent.get("source_character_key") == child.get("source_character_key")
        and parent.get("target_character_key") == child.get("target_character_key")
        and abs(int(parent.get("start_ts_ms") or 0) - int(child.get("start_ts_ms") or 0)) <= _BUFF_MIRROR_DEDUPE_WINDOW_MS
    )


def _parent_window_covers_created_children(parent: dict[str, Any], siblings: list[dict[str, Any]]) -> bool:
    child_ids = _created_child_buff_ids(str(parent.get("event_key") or ""))
    if not child_ids:
        return False
    parent_pairs = _window_static_effect_pairs(parent)
    if not parent_pairs:
        return False
    child_pairs: set[tuple[str, str, float]] = set()
    for other in siblings:
        if other is parent:
            continue
        if str(other.get("event_key") or "") not in child_ids:
            continue
        if not _window_matches_same_lane(parent, other):
            continue
        child_pairs.update(_window_static_effect_pairs(other))
    if not child_pairs:
        return False
    for zone, element, rate in parent_pairs:
        if (zone, element, rate) in child_pairs:
            continue
        if element == "spell":
            spell_children = {
                child_element
                for child_zone, child_element, child_rate in child_pairs
                if child_zone == zone and child_rate == rate and child_element in _ELEMENTAL_ELEMENTS
            }
            if spell_children:
                continue
        if element == "all":
            matching_children = [
                child_element
                for child_zone, child_element, child_rate in child_pairs
                if child_zone == zone and child_rate == rate
            ]
            if matching_children:
                continue
        return False
    return True


def _parent_window_covers_specific_siblings(parent: dict[str, Any], siblings: list[dict[str, Any]]) -> bool:
    parent_pairs = _window_static_effect_pairs(parent)
    if not parent_pairs:
        return False
    child_pairs: set[tuple[str, str, float]] = set()
    child_event_keys: set[str] = set()
    for other in siblings:
        if other is parent:
            continue
        if str(other.get("event_key") or "") == str(parent.get("event_key") or ""):
            continue
        if not _window_matches_same_lane(parent, other):
            continue
        pairs = _window_static_effect_pairs(other)
        if not pairs:
            continue
        child_pairs.update(pairs)
        child_event_keys.add(str(other.get("event_key") or ""))
    if not child_pairs or not child_event_keys:
        return False
    for zone, element, rate in parent_pairs:
        if (zone, element, rate) in child_pairs:
            continue
        if element == "spell":
            spell_children = {
                child_element
                for child_zone, child_element, child_rate in child_pairs
                if child_zone == zone and child_rate == rate and child_element in _ELEMENTAL_ELEMENTS
            }
            if spell_children:
                continue
        if element == "all":
            matching_children = [
                child_element
                for child_zone, child_element, child_rate in child_pairs
                if child_zone == zone and child_rate == rate
            ]
            if matching_children:
                continue
        return False
    return True


def _dedupe_mirrored_buff_windows(buff_windows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    for window in buff_windows:
        if _parent_window_covers_created_children(window, deduped) or _parent_window_covers_specific_siblings(window, deduped):
            continue
        parent_event_key = _event_key_parent_of_default_child(window.get("event_key"))
        if parent_event_key is not None:
            parent_index = None
            for index, other in enumerate(deduped):
                if other.get("event_key") != parent_event_key:
                    continue
                if other.get("source_character_key") != window.get("source_character_key"):
                    continue
                if other.get("target_character_key") != window.get("target_character_key"):
                    continue
                if abs(int(other.get("start_ts_ms") or 0) - int(window.get("start_ts_ms") or 0)) > _BUFF_MIRROR_DEDUPE_WINDOW_MS:
                    continue
                if _parent_window_covers_default_child(other, window):
                    parent_index = index
                    break
            if parent_index is not None:
                _merge_window_uid_aliases(deduped[parent_index], window)
                continue

        signature = _static_effect_signature(window)
        if signature is None:
            deduped.append(window)
            continue

        mirror_index = None
        for index, other in enumerate(deduped):
            if other.get("event_key") == window.get("event_key"):
                if _window_allows_stacking(other) or _window_allows_stacking(window):
                    continue
                if _window_matches_same_lane(other, window) and _same_event_window_signature_matches(other, window):
                    mirror_index = index
                    break
                continue
            if other.get("source_character_key") != window.get("source_character_key"):
                continue
            if other.get("target_character_key") != window.get("target_character_key"):
                continue
            if _static_effect_signature(other) != signature:
                continue
            if abs(int(other.get("start_ts_ms") or 0) - int(window.get("start_ts_ms") or 0)) > _BUFF_MIRROR_DEDUPE_WINDOW_MS:
                continue
            mirror_index = index
            break

        if mirror_index is None:
            deduped.append(window)
            continue

        other = deduped[mirror_index]
        same_event_duplicate = other.get("event_key") == window.get("event_key")
        current_score = _mirror_preference_score(window)
        other_score = _mirror_preference_score(other)
        if same_event_duplicate:
            current_score += _window_detail_count(window)
            other_score += _window_detail_count(other)
        if current_score > other_score:
            _merge_window_uid_aliases(window, other)
            deduped[mirror_index] = window
        elif current_score == other_score and not same_event_duplicate:
            deduped.append(window)
        else:
            _merge_window_uid_aliases(other, window)
    return deduped


def _assign_skill_timeline_group_keys(hits: list[dict[str, Any]]) -> None:
    latest_group_state: dict[tuple[str, str, str], dict[str, int]] = {}
    next_group_index: defaultdict[tuple[str, str, str], int] = defaultdict(int)

    for order_index, hit in sorted(
        enumerate(hits),
        key=lambda item: (int(item[1].get("ts_ms") or 0), item[0]),
    ):
        _ = order_index
        base_event_key = str(hit.get("skill_family_key") or hit.get("skill_key") or "")
        if not base_event_key:
            hit["timeline_group_key"] = None
            continue

        state_key = (
            str(hit.get("character_key") or ""),
            base_event_key,
            str(hit.get("target_enemy_key") or ""),
        )
        hit_ts_ms = int(hit.get("ts_ms") or 0)
        state = latest_group_state.get(state_key)
        if state is None or hit_ts_ms - state["last_ts_ms"] > _timeline_skill_group_gap_ms(hit):
            next_group_index[state_key] += 1

        group_index = next_group_index[state_key]
        latest_group_state[state_key] = {"last_ts_ms": hit_ts_ms}
        hit["timeline_group_key"] = f"{base_event_key}::{state_key[2] or 'unknown-target'}::{group_index}"


def _infer_missing_hit_damage_schools(
    hits: list[dict[str, Any]],
    buff_windows: list[dict[str, Any]],
) -> None:
    for hit in hits:
        if hit.get("damage_school"):
            continue
        packet_modifier_uids = hit.get("packet_modifier_uids") if isinstance(hit.get("packet_modifier_uids"), dict) else {}
        attacker_modifier_uids = {str(item) for item in packet_modifier_uids.get("attacker") or [] if str(item)}
        defender_modifier_uids = {str(item) for item in packet_modifier_uids.get("defender") or [] if str(item)}
        attacker_key = str(hit.get("character_key") or "")
        target_enemy_key = str(hit.get("target_enemy_key") or "")
        hit_ts_ms = int(hit.get("ts_ms") or 0)
        skill_key = str(hit.get("skill_key") or "")
        skill_family_key = str(hit.get("skill_family_key") or "")

        packet_candidates: set[str] = set()
        generic_candidates: set[str] = set()
        for window in buff_windows:
            if not (int(window.get("start_ts_ms") or 0) <= hit_ts_ms <= int(window.get("end_ts_ms") or 0)):
                continue
            window_skill_family_key = str(window.get("skill_family_key") or "")
            if window_skill_family_key and skill_family_key != window_skill_family_key:
                continue
            skill_filter = _BUFF_SKILL_FILTER.get(str(window.get("event_key") or ""))
            if skill_filter and not skill_filter.search(skill_key):
                continue

            applies_to_attacker = str(window.get("target_character_key") or "") == attacker_key
            applies_to_enemy = bool(target_enemy_key) and str(window.get("target_character_key") or "") == target_enemy_key
            if not applies_to_attacker and not applies_to_enemy:
                continue

            packet_match = False
            if applies_to_attacker and attacker_modifier_uids and _window_matches_packet_uids(window, attacker_modifier_uids):
                packet_match = True
            if applies_to_enemy and defender_modifier_uids and _window_matches_packet_uids(window, defender_modifier_uids):
                packet_match = True

            for effect in _window_effects_at_ts(window, hit_ts_ms):
                effect_skill_filter = _BUFF_EFFECT_SKILL_FILTER.get((str(window.get("event_key") or ""), str(effect.get("zone") or "")))
                if effect_skill_filter and not effect_skill_filter.search(skill_key):
                    continue
                attr_type = effect.get("attr_type")
                if isinstance(attr_type, int) and not _attr_type_applies_to_skill(attr_type, skill_key):
                    continue
                try:
                    rate = float(effect.get("rate") or 0.0)
                except (TypeError, ValueError):
                    continue
                if rate <= 0:
                    continue
                school = _normalize_effect_element(effect.get("element"))
                if school not in {"physical", "spell"}:
                    continue
                generic_candidates.add(school)
                if packet_match:
                    packet_candidates.add(school)

        if len(packet_candidates) == 1:
            hit["damage_school"] = next(iter(packet_candidates))
        elif len(generic_candidates) == 1:
            hit["damage_school"] = next(iter(generic_candidates))


def _build_role_skill_stats_from_timeline_groups(
    hits: list[dict[str, Any]],
    roster_order: list[str],
) -> list[dict[str, Any]]:
    cast_totals: defaultdict[tuple[str, str, str], dict[str, Any]] = defaultdict(
        lambda: {
            "character_key": None,
            "character_name": None,
            "skill_key": None,
            "skill_name": None,
            "total_damage": 0,
        }
    )

    for index, hit in enumerate(hits):
        character_key = str(hit.get("character_key") or "")
        if not character_key:
            continue
        skill_key = str(hit.get("skill_family_key") or hit.get("skill_key") or "unknown_skill")
        cast_key = str(hit.get("timeline_group_key") or f"{skill_key}::hit-{index}")
        cast_entry = cast_totals[(character_key, skill_key, cast_key)]
        cast_entry["character_key"] = character_key
        cast_entry["character_name"] = hit.get("character_name") or _resolve_character_name(character_key) or character_key
        cast_entry["skill_key"] = skill_key
        cast_entry["skill_name"] = hit.get("skill_name") or _resolve_skill_name(skill_key) or skill_key
        cast_entry["total_damage"] += int(hit.get("hit_value") or 0)

    skill_totals: defaultdict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {
            "character_key": None,
            "character_name": None,
            "skill_key": None,
            "skill_name": None,
            "total_damage": 0,
            "max_damage": 0,
            "cast_count": 0,
        }
    )

    for (character_key, skill_key, _), cast_entry in cast_totals.items():
        cast_damage = int(cast_entry["total_damage"] or 0)
        skill_entry = skill_totals[(character_key, skill_key)]
        skill_entry["character_key"] = character_key
        skill_entry["character_name"] = cast_entry["character_name"]
        skill_entry["skill_key"] = skill_key
        skill_entry["skill_name"] = cast_entry["skill_name"]
        skill_entry["total_damage"] += cast_damage
        skill_entry["max_damage"] = max(int(skill_entry["max_damage"] or 0), cast_damage)
        skill_entry["cast_count"] += 1

    role_skill_stats = []
    for character_key in roster_order:
        character_skills = [
            entry
            for (entry_character_key, _), entry in skill_totals.items()
            if entry_character_key == character_key
        ]
        character_skills.sort(key=lambda item: (-item["total_damage"], item["skill_key"]))
        for entry in character_skills:
            cast_count = max(int(entry["cast_count"] or 0), 1)
            role_skill_stats.append(
                {
                    "character_key": character_key,
                    "character_name": entry["character_name"],
                    "skill_key": entry["skill_key"],
                    "skill_name": entry["skill_name"],
                    "cast_count": cast_count,
                    "total_damage": entry["total_damage"],
                    "avg_damage": round(entry["total_damage"] / cast_count, 2),
                    "max_damage": entry["max_damage"],
                }
            )

    return role_skill_stats


def _zone_from_label(label: str) -> str | None:
    return _ZONE_BY_LABEL.get(label)


def _safe_positive_rate(value: Any) -> float | None:
    try:
        rate = float(value)
    except (TypeError, ValueError):
        return None
    if rate <= 0:
        return None
    return rate


def _semantic_blackboard_defaults(entry: dict[str, Any]) -> dict[str, Any]:
    defaults: dict[str, Any] = {}
    for row in entry.get("blackboard") or []:
        if not isinstance(row, dict):
            continue
        key = str(row.get("key") or "")
        if not key:
            continue
        if row.get("defaultDouble") is not None:
            defaults[key] = row.get("defaultDouble")
        elif row.get("defaultString") not in (None, ""):
            defaults[key] = row.get("defaultString")
    return defaults


def _semantic_damage_effect_zone(effect: dict[str, Any]) -> tuple[str, str] | None:
    if str(effect.get("processorType") or "") != "DamageScaleProcessor":
        return None
    if str(effect.get("zoneName") or "") != "NormalCalcZone":
        return None
    side = str(effect.get("side") or effect.get("enableSide") or "")
    if side == "Attacker":
        return "dmg_inc", "all"
    if side == "Defender":
        return "vuln_taken", "all"
    return None


def _semantic_damage_effect_condition(
    buff_id: str,
    effect: dict[str, Any],
    *,
    defaults: dict[str, Any],
    bb_values: dict[str, Any],
) -> dict[str, Any] | None:
    condition_actions = {
        str(action)
        for action in effect.get("conditionActionTypes") or []
        if str(action or "")
    }
    if not condition_actions:
        return None
    conditions: list[dict[str, Any]] = []
    if "CheckHp" in condition_actions:
        threshold = _safe_positive_rate(bb_values.get("hp_remain"))
        if threshold is None:
            threshold = _safe_positive_rate(defaults.get("hp_remain"))
        if threshold is None:
            return None
        conditions.append({
            "type": "target_hp_ratio_lte",
            "source": "CheckHp",
            "threshold": threshold,
            "threshold_key": "hp_remain",
        })
    if "CheckDamageType" in condition_actions or "CheckBuffStackNumAdvanced" in condition_actions:
        try:
            group_index = int(effect.get("groupIndex"))
        except (TypeError, ValueError):
            return None
        decoded_conditions = _decoded_damage_modifier_condition_rows(buff_id).get(group_index) or {}
        damage_types = [
            str(element)
            for element in decoded_conditions.get("damage_types") or []
            if str(element or "")
        ]
        if damage_types:
            conditions.append({
                "type": "damage_type_in",
                "source": "CheckDamageType",
                "elements": damage_types,
            })
        condition_buff_ids = [
            _normalize_buff_id(buff_id_value)
            for buff_id_value in decoded_conditions.get("condition_buff_ids") or effect.get("conditionBuffIds") or []
            if _normalize_buff_id(buff_id_value)
        ]
        if "CheckBuffStackNumAdvanced" in condition_actions and condition_buff_ids:
            conditions.append({
                "type": "target_has_buff",
                "source": "CheckBuffStackNumAdvanced",
                "buff_ids": sorted(set(condition_buff_ids)),
            })
    unsupported = condition_actions - {"CheckHp", "CheckDamageType", "CheckBuffStackNumAdvanced"}
    if unsupported or not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {
        "type": "all",
        "source": "+".join(sorted(condition_actions)),
        "conditions": conditions,
    }


def _collect_semantic_condition_zone_effects(record: dict[str, Any]) -> list[dict[str, Any]]:
    buff_id = _normalize_buff_id(record.get("event_key"))
    entry = _load_local_buff_semantic_entries().get(buff_id)
    if not isinstance(entry, dict):
        return []

    bb_values = {str(key): value for key, value in (record.get("bb_values") or {}).items()}
    defaults = _semantic_blackboard_defaults(entry)
    effects: list[dict[str, Any]] = []
    for damage_effect in entry.get("damageEffects") or []:
        if not isinstance(damage_effect, dict):
            continue
        condition = _semantic_damage_effect_condition(
            buff_id,
            damage_effect,
            defaults=defaults,
            bb_values=bb_values,
        )
        if condition is None:
            continue
        zone_element = _semantic_damage_effect_zone(damage_effect)
        if zone_element is None:
            continue
        zone, element = zone_element
        addition = damage_effect.get("addition") if isinstance(damage_effect.get("addition"), dict) else {}
        bb_key = str(addition.get("blackboardKey") or "")
        rate = _safe_positive_rate(bb_values.get(bb_key)) if bb_key else None
        if rate is None:
            rate = _safe_positive_rate(addition.get("value"))
        if rate is None and bb_key:
            rate = _safe_positive_rate(defaults.get(bb_key))
        if rate is None:
            continue
        if zone == "dmg_inc" and bb_key:
            element = _damage_increase_element_from_bb_key(bb_key) or element
        elif bb_key:
            element = _element_from_text(bb_key) or element
        condition_elements = _condition_damage_type_elements(condition)
        if element == "all" and len(condition_elements) == 1:
            element = next(iter(condition_elements))
        effect = {
            "zone": zone,
            "element": _normalize_effect_element(element),
            "rate": rate,
            "condition": condition,
            "semantic_source": "damageEffects",
        }
        if bb_key:
            effect["bb_key"] = bb_key
            _attach_bb_key_damage_type_condition(effect, bb_key)
        effects.append(effect)
    return effects


def _collect_zone_effects(record: dict[str, Any]) -> list[dict[str, Any]]:
    buff_id = _normalize_buff_id(record.get("event_key"))
    if _rdps_registry_suppresses_zone_effects(record):
        return []
    semantic_condition_effects = _collect_semantic_condition_zone_effects(record)
    if (
        _is_noise_buff(buff_id)
        or _should_ignore_rate_buff(buff_id)
        or _should_ignore_record_rate_effects(record)
        or record.get("packet_mapping_rejected")
    ):
        return []
    registry_candidate = _rdps_registry_candidate_effect_entry(record)
    if _is_effectless_wrapper_record(record) and not semantic_condition_effects and registry_candidate is None:
        return []
    if registry_candidate is not None:
        registry_entry = _rdps_registry_verified_effect_entry(record)
        if registry_entry is None:
            return []
        registry_effects = _rdps_registry_zone_effects(record, registry_entry)
        for registry_effect in registry_effects:
            registry_bb_key = str(registry_effect.get("bb_key") or registry_effect.get("_registry_bb_key") or "")
            for semantic_effect in semantic_condition_effects:
                if (
                    registry_bb_key
                    and registry_bb_key == str(semantic_effect.get("bb_key") or "")
                    and str(registry_effect.get("zone") or "") == str(semantic_effect.get("zone") or "")
                    and _normalize_effect_element(registry_effect.get("element"))
                    == _normalize_effect_element(semantic_effect.get("element"))
                    and isinstance(semantic_effect.get("condition"), dict)
                ):
                    registry_effect["bb_key"] = registry_bb_key
                    registry_effect["condition"] = dict(semantic_effect["condition"])
                    if semantic_effect.get("semantic_source"):
                        registry_effect["semantic_source"] = semantic_effect.get("semantic_source")
        for registry_effect in registry_effects:
            registry_effect.pop("_registry_bb_key", None)
        if registry_entry.get("dynamic"):
            return []
        return registry_effects

    semantic_bb_keys = {
        str(effect.get("bb_key") or "")
        for effect in semantic_condition_effects
        if str(effect.get("bb_key") or "")
    }
    packet_effects = [
        effect
        for effect in _packet_numeric_effects(record)
        if not (str(effect.get("bb_key") or "") and str(effect.get("bb_key") or "") in semantic_bb_keys)
    ]
    target_is_enemy = bool(record.get("target_enemy_key"))
    bb_values = {str(key): value for key, value in (record.get("bb_values") or {}).items()}
    effects: list[dict[str, Any]] = list(packet_effects)
    effects.extend(semantic_condition_effects)
    covered_bb_keys: set[str] = set()
    for effect in packet_effects:
        bb_key = str(effect.get("bb_key") or "")
        if bb_key:
            covered_bb_keys.add(bb_key)
    for effect in effects:
        if effect.get("condition"):
            bb_key = str(effect.get("bb_key") or "")
            if bb_key:
                covered_bb_keys.add(bb_key)
    for effect in _packet_numeric_dynamic_effects(record):
        for key_name in ("bb_key", "add_bb_key", "delay_bb_key"):
            bb_key = str(effect.get(key_name) or "")
            if bb_key:
                covered_bb_keys.add(bb_key)

    for attr_mod in record.get("attr_mods") or []:
        bb_key = str(attr_mod.get("bb_key") or "")
        if bb_key and bb_key in semantic_bb_keys:
            covered_bb_keys.add(bb_key)
            continue
        if _buff_effect_bb_key_ignored(buff_id, bb_key):
            continue
        if bb_key:
            covered_bb_keys.add(bb_key)
        try:
            attr_type_int = int(attr_mod.get("attr_type"))
        except (TypeError, ValueError):
            attr_type_int = None
        attr_zone = None
        attr_element = None
        if bb_key in _DEF_DECREASE_BASE_KEYS and attr_type_int is not None:
            attr_zone, attr_element = _DEF_DECREASE_ATTR_TYPE_TO_EFFECT.get(attr_type_int, (None, None))
        elif attr_type_int is not None and attr_type_int in _ATTR_TYPE_TO_EFFECT:
            attr_zone, attr_element = _ATTR_TYPE_TO_EFFECT[attr_type_int]
        elif attr_type_int in _FRAGILE_ATTR_TYPES:
            attr_zone, attr_element = "fragile", "all"
        zone = None
        element = None
        if _is_damage_increase_bb_key(bb_key):
            zone = "dmg_inc"
            element = _damage_increase_element_from_bb_key(bb_key) or attr_element
        elif attr_zone is not None:
            zone, element = attr_zone, attr_element
        elif attr_type_int is not None:
            continue
        elif bb_key:
            label = _label_from_bb_key(bb_key, buff_id=buff_id, target_is_enemy=target_is_enemy)
            zone = _zone_from_label(label or "")
            element = _element_from_text(bb_key)
            if element is None and label:
                label_elements = _elements_from_text(label)
                if label_elements:
                    element = label_elements[0]
            if (
                element is None
                and bb_key.lower() == "rate"
                and (
                    "enhance_" in buff_id.lower()
                    or "vulnerable" in buff_id.lower()
                    or "fragile" in buff_id.lower()
                )
            ):
                element = _element_from_text(buff_id)
        if zone is None:
            continue

        rate = None
        uses_runtime_bb_key = bb_key and str(attr_mod.get("use_key") or "0") == "1"
        if uses_runtime_bb_key:
            rate = _safe_positive_rate(bb_values.get(bb_key))
            if rate is None and bb_values:
                # This instance carried runtime BB data, but not for the key the modifier says to use.
                # Treat that as a non-effect wrapper/refresh row instead of falling back to the template rate.
                continue
        if rate is None:
            rate = _safe_positive_rate(attr_mod.get("value"))
        if rate is None and bb_key:
            rate = _safe_positive_rate(bb_values.get(bb_key))
        if rate is None:
            continue
        if bb_key.startswith("final_"):
            covered_bb_keys.add(bb_key.removeprefix("final_"))
        effect = {"zone": zone, "element": _normalize_effect_element(element), "rate": rate}
        if attr_type_int is not None:
            effect["attr_type"] = attr_type_int
        if bb_key:
            effect["bb_key"] = bb_key
            _attach_bb_key_damage_type_condition(effect, bb_key)
        effects.append(effect)

    bb_value_keys = {str(key).lower() for key in bb_values}
    for bb_key, raw_value in bb_values.items():
        if bb_key in covered_bb_keys:
            continue
        final_override_key = _FINAL_BB_KEY_OVERRIDES.get(bb_key.lower())
        if final_override_key and final_override_key in bb_value_keys:
            continue
        if _buff_effect_bb_key_ignored(buff_id, bb_key):
            continue
        label = _label_from_bb_key(bb_key, buff_id=buff_id, target_is_enemy=target_is_enemy)
        zone = _zone_from_label(label or "")
        element = _damage_increase_element_from_bb_key(bb_key) if zone == "dmg_inc" else _element_from_text(bb_key)
        if element is None and label:
            label_elements = _elements_from_text(label)
            if label_elements:
                element = label_elements[0]
        if (
            element is None
            and bb_key.lower() == "rate"
            and (
                "enhance_" in buff_id.lower()
                or "vulnerable" in buff_id.lower()
                or "fragile" in buff_id.lower()
            )
        ):
            element = _element_from_text(buff_id)
        element = _normalize_effect_element(element)
        rate = _safe_positive_rate(raw_value)
        if zone is None or rate is None:
            continue
        effect = {"zone": zone, "element": element, "rate": rate}
        _attach_bb_key_damage_type_condition(effect, bb_key)
        effects.append(effect)

    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, float, str]] = set()
    for effect in effects:
        condition_marker = ""
        if isinstance(effect.get("condition"), dict):
            condition_marker = json.dumps(effect["condition"], ensure_ascii=False, sort_keys=True)
        key = (
            str(effect["zone"]),
            str(effect["element"]),
            round(float(effect["rate"]), 6),
            condition_marker,
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(effect)
    return deduped


def _extract_dynamic_effect_specs(record: dict[str, Any]) -> list[dict[str, Any]]:
    buff_id = _normalize_buff_id(record.get("event_key"))
    if (
        _rdps_registry_suppresses_zone_effects(record)
        or _is_noise_buff(buff_id)
        or _should_ignore_rate_buff(buff_id)
        or _should_ignore_record_rate_effects(record)
        or _is_effectless_wrapper_record(record)
        or record.get("packet_mapping_rejected")
    ):
        return []

    packet_dynamic_effects = _packet_numeric_dynamic_effects(record)
    if any(effect.get("dynamic_key") == "def_decrease" for effect in packet_dynamic_effects):
        return packet_dynamic_effects
    bb_values = {str(key): value for key, value in (record.get("bb_values") or {}).items()}
    tick_rate = _safe_positive_rate(bb_values.get("def_decrease_tick_final"))
    if tick_rate is None:
        tick_rate = _safe_positive_rate(bb_values.get("def_decrease_tick"))
    max_rate = _safe_positive_rate(bb_values.get("max_def_decrease")) or 0.0
    if tick_rate is None and max_rate <= 0:
        return packet_dynamic_effects

    dynamic_specs: dict[tuple[str, str], dict[str, Any]] = {}
    for attr_mod in record.get("attr_mods") or []:
        bb_key = str(attr_mod.get("bb_key") or "")
        if bb_key not in _DEF_DECREASE_BASE_KEYS:
            continue
        try:
            attr_type_int = int(attr_mod.get("attr_type"))
        except (TypeError, ValueError):
            continue
        mapping = _DEF_DECREASE_ATTR_TYPE_TO_EFFECT.get(attr_type_int)
        if mapping is None:
            continue
        zone, element = mapping
        base_rate = _safe_positive_rate(bb_values.get(bb_key))
        if base_rate is None:
            base_rate = _safe_positive_rate(attr_mod.get("value")) or 0.0
        spec = dynamic_specs.setdefault(
            (zone, element),
            {
                "zone": zone,
                "element": element,
                "base_rate": 0.0,
                "tick_rate": (tick_rate or 0.0) * _DEF_DECREASE_TICKS_PER_SEC,
                "max_rate": max_rate,
            },
        )
        spec["base_rate"] += base_rate

    if not dynamic_specs and record.get("target_enemy_key"):
        base_rate = _safe_positive_rate(bb_values.get("def_decrease"))
        if base_rate is None:
            base_rate = _safe_positive_rate(bb_values.get("start_def_decrease")) or 0.0
        if base_rate > 0 or tick_rate is not None:
            dynamic_specs[("res", "all")] = {
                "zone": "res",
                "element": "all",
                "base_rate": base_rate,
                "tick_rate": (tick_rate or 0.0) * _DEF_DECREASE_TICKS_PER_SEC,
                "max_rate": max_rate,
            }

    return packet_dynamic_effects + list(dynamic_specs.values())


def _window_effects_at_ts(window: dict[str, Any], hit_ts_ms: int) -> list[dict[str, Any]]:
    dynamic_specs = list(window.get("dynamic_effects") or [])
    if not dynamic_specs:
        return list(window.get("zone_effects") or [])

    elapsed_sec = max(0.0, (hit_ts_ms - int(window["start_ts_ms"])) / 1000.0)
    effects: list[dict[str, Any]] = []
    for spec in dynamic_specs:
        rate = max(0.0, float(spec.get("base_rate") or 0.0))
        rate += elapsed_sec * max(0.0, float(spec.get("tick_rate") or 0.0))
        if elapsed_sec >= max(0.0, float(spec.get("delay_sec") or 0.0)):
            rate += max(0.0, float(spec.get("delayed_add_rate") or 0.0))
        max_rate = max(0.0, float(spec.get("max_rate") or 0.0))
        if max_rate > 0:
            rate = min(rate, max_rate)
        if rate <= 0.001:
            continue
        effects.append(
            {
                "zone": str(spec["zone"]),
                "element": _normalize_effect_element(spec.get("element")),
                "rate": rate,
            }
        )
    return effects


def _effect_summary_rows(effects: list[dict[str, Any]]) -> list[str]:
    rows: list[str] = []
    seen: set[str] = set()
    for effect in effects:
        zone = str(effect.get("zone") or "")
        element = _normalize_effect_element(effect.get("element"))
        rate = effect.get("rate")
        if rate is None:
            rate = effect.get("base_rate")
        try:
            base_rate = float(rate)
        except (TypeError, ValueError):
            base_rate = None
        label = _EFFECT_ZONE_LABELS.get(zone, zone)
        if base_rate is None:
            row_text = f"{label}/{element} -"
        else:
            delayed_add_rate = _safe_positive_rate(effect.get("delayed_add_rate")) or 0.0
            delay_sec = float(effect.get("delay_sec") or 0.0)
            tick_rate = float(effect.get("tick_rate") or 0.0)
            max_rate = float(effect.get("max_rate") or 0.0)
            if delayed_add_rate > 0 and delay_sec > 0:
                row_text = (
                    f"{label}/{element} {base_rate * 100:.2f}%"
                    f" -> {(base_rate + delayed_add_rate) * 100:.2f}% @ {delay_sec:g}s"
                )
            elif tick_rate > 0 and max_rate > base_rate:
                row_text = (
                    f"{label}/{element} {base_rate * 100:.2f}%"
                    f" -> {max_rate * 100:.2f}% over time"
                )
            else:
                row_text = f"{label}/{element} {base_rate * 100:.2f}%"
        condition = effect.get("condition")
        if isinstance(condition, dict) and str(condition.get("type") or "") == "target_hp_ratio_lte":
            threshold = _safe_positive_rate(condition.get("threshold"))
            if threshold is not None:
                row_text = f"{row_text} (target HP <= {threshold * 100:.2f}%)"
        elif isinstance(condition, dict) and str(condition.get("type") or "") == "damage_type_in":
            elements = [str(item) for item in condition.get("elements") or [] if str(item or "")]
            if elements:
                row_text = f"{row_text} (damage type: {', '.join(elements)})"
        if row_text in seen:
            continue
        seen.add(row_text)
        rows.append(row_text)
    return rows


def _effect_segments_for_event(
    *,
    start_ts_ms: int,
    end_ts_ms: int,
    zone_effects: list[dict[str, Any]],
    dynamic_effects: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    for effect in zone_effects:
        segments.append(
            {
                "start_ts_ms": start_ts_ms,
                "start_time": _ms_time_text(start_ts_ms),
                "end_ts_ms": end_ts_ms,
                "end_time": _ms_time_text(end_ts_ms),
                "zone": str(effect.get("zone") or ""),
                "element": _normalize_effect_element(effect.get("element")),
                "rate": effect.get("rate"),
                "mode": "static",
            }
        )
    for effect in dynamic_effects:
        base_rate = float(effect.get("base_rate") or 0.0)
        delayed_add_rate = float(effect.get("delayed_add_rate") or 0.0)
        delay_ms = int(max(0.0, float(effect.get("delay_sec") or 0.0)) * 1000)
        tick_rate = float(effect.get("tick_rate") or 0.0)
        max_rate = float(effect.get("max_rate") or 0.0)
        zone = str(effect.get("zone") or "")
        element = _normalize_effect_element(effect.get("element"))
        if delayed_add_rate > 0 and delay_ms > 0 and start_ts_ms + delay_ms < end_ts_ms:
            segments.append(
                {
                    "start_ts_ms": start_ts_ms,
                    "start_time": _ms_time_text(start_ts_ms),
                    "end_ts_ms": start_ts_ms + delay_ms,
                    "end_time": _ms_time_text(start_ts_ms + delay_ms),
                    "zone": zone,
                    "element": element,
                    "rate": base_rate,
                    "mode": "dynamic_before_delay",
                }
            )
            segments.append(
                {
                    "start_ts_ms": start_ts_ms + delay_ms,
                    "start_time": _ms_time_text(start_ts_ms + delay_ms),
                    "end_ts_ms": end_ts_ms,
                    "end_time": _ms_time_text(end_ts_ms),
                    "zone": zone,
                    "element": element,
                    "rate": base_rate + delayed_add_rate,
                    "mode": "dynamic_after_delay",
                }
            )
            continue
        segments.append(
            {
                "start_ts_ms": start_ts_ms,
                "start_time": _ms_time_text(start_ts_ms),
                "end_ts_ms": end_ts_ms,
                "end_time": _ms_time_text(end_ts_ms),
                "zone": zone,
                "element": element,
                "rate": base_rate,
                "tick_rate_per_sec": tick_rate,
                "max_rate": max_rate,
                "mode": "dynamic",
            }
        )
    return segments


def _buff_window_identity(window: dict[str, Any]) -> tuple[Any, ...]:
    uid = str(window.get("uid") or "")
    if uid:
        return ("uid", uid)
    return (
        "tuple",
        window.get("event_key"),
        window.get("source_character_key"),
        window.get("target_character_key"),
        int(window.get("start_ts_ms") or 0),
    )


def _build_buff_events(
    buff_starts: list[dict[str, Any]],
    buff_windows: list[dict[str, Any]],
    *,
    battle_start_ms: int,
    battle_end_ms: int,
) -> list[dict[str, Any]]:
    included_identities = {_buff_window_identity(window) for window in buff_windows}
    events: list[dict[str, Any]] = []
    for record in buff_starts:
        start_ts_ms = int(record.get("ts_ms") or 0)
        duration_ms = _normalize_buff_duration_ms(
            start_ts_ms,
            event_key=record.get("event_key"),
            end_ts_ms=record.get("end_ts_ms"),
            raw_duration_ms=record.get("raw_duration_ms"),
            battle_end_ms=battle_end_ms,
        )
        end_ts_ms = start_ts_ms + duration_ms
        labels = _collect_buff_labels(record)
        zone_effects = _collect_zone_effects(record)
        dynamic_effects = _extract_dynamic_effect_specs(record)
        has_effects = bool(zone_effects or dynamic_effects)
        identity = _buff_window_identity(
            {
                "uid": record.get("uid"),
                "event_key": record.get("event_key"),
                "source_character_key": record.get("source_character_key"),
                "target_character_key": record.get("target_character_key") or record.get("target_enemy_key"),
                "start_ts_ms": start_ts_ms,
            }
        )
        included = has_effects and identity in included_identities
        status = "included" if included else "merged" if has_effects else "filtered"
        packet_classification = _classify_packet_buff_record(record)
        events.append(
            {
                "status": status,
                "status_label": "纳入" if included else "合并/未参与窗口" if has_effects else "过滤",
                "line_no": record.get("line_no"),
                "uid": record.get("uid"),
                "event_key": record.get("event_key"),
                "raw_event_key": record.get("raw_event_key"),
                "event_name": " / ".join(labels) if labels else record.get("event_key"),
                "packet_mapping": record.get("packet_mapping"),
                "packet_classification": packet_classification,
                "semantic_candidates": _packet_buff_semantic_candidates(record),
                "source_character_key": record.get("source_character_key"),
                "source_character_name": record.get("source_character_name"),
                "source_skill_key": record.get("source_skill_key"),
                "source_skill_family_key": record.get("source_skill_family_key"),
                "raw_source": record.get("raw_source"),
                "target_character_key": record.get("target_character_key") or record.get("target_enemy_key"),
                "target_character_name": record.get("target_character_name") or record.get("target_enemy_name"),
                "target_player_key": record.get("target_character_key"),
                "target_enemy_key": record.get("target_enemy_key"),
                "owner_raw": record.get("owner_raw"),
                "start_ts_ms": start_ts_ms,
                "start_time": _ms_time_text(start_ts_ms),
                "end_ts_ms": end_ts_ms,
                "end_time": _ms_time_text(end_ts_ms),
                "start_ms_from_battle": start_ts_ms - battle_start_ms,
                "end_ms_from_battle": end_ts_ms - battle_start_ms,
                "duration_ms": duration_ms,
                "raw_end_ts_ms": record.get("end_ts_ms"),
                "raw_end_time": _ms_time_text(record.get("end_ts_ms")) if record.get("end_ts_ms") is not None else None,
                "raw_duration_ms": record.get("raw_duration_ms"),
                "overlaps_battle": end_ts_ms >= battle_start_ms and start_ts_ms <= battle_end_ms,
                "bb_keys": sorted(set(str(key) for key in record.get("bb_keys") or [])),
                "bb_values": dict(record.get("bb_values") or {}),
                "attr_types": list(record.get("attr_types") or []),
                "attr_mods": list(record.get("attr_mods") or []),
                "zone_effects": zone_effects,
                "dynamic_effects": dynamic_effects,
                "effect_segments": _effect_segments_for_event(
                    start_ts_ms=start_ts_ms,
                    end_ts_ms=end_ts_ms,
                    zone_effects=zone_effects,
                    dynamic_effects=dynamic_effects,
                ),
                "effect_summary": _effect_summary_rows(zone_effects + dynamic_effects),
                "is_weapon_buff": bool(record.get("is_weapon_buff")),
            }
        )
    return sorted(events, key=lambda item: (int(item.get("start_ts_ms") or 0), int(item.get("line_no") or 0)))


def _build_buff_record_index(buff_starts: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for record in buff_starts:
        uid = str(record.get("uid") or "")
        if uid:
            index[uid] = record
    return index


def _record_could_affect_external_rdps(record: dict[str, Any]) -> bool:
    source_key = str(record.get("source_character_key") or "")
    if not source_key.startswith("chr_"):
        return False
    target_enemy_key = str(record.get("target_enemy_key") or "")
    if target_enemy_key.startswith("eny_"):
        return True
    target_character_key = str(record.get("target_character_key") or "")
    return bool(target_character_key.startswith("chr_") and target_character_key != source_key)


def _record_overlaps_window(record: dict[str, Any], *, battle_start_ms: int, battle_end_ms: int) -> bool:
    start_ts_ms = int(record.get("ts_ms") or 0)
    duration_ms = _normalize_buff_duration_ms(
        start_ts_ms,
        event_key=record.get("event_key"),
        end_ts_ms=record.get("end_ts_ms"),
        raw_duration_ms=record.get("raw_duration_ms"),
        battle_end_ms=battle_end_ms,
    )
    end_ts_ms = start_ts_ms + duration_ms
    return end_ts_ms >= battle_start_ms and start_ts_ms <= battle_end_ms


def _known_non_rdps_buff_record(record: dict[str, Any]) -> bool:
    event_key = _normalize_buff_id(record.get("event_key"))
    if _rdps_registry_known_non_rdps_entry(record) is not None:
        return True
    if _rdps_registry_verified_effect_entry(record) is not None:
        return False
    if _is_noise_buff(event_key) or _should_ignore_rate_buff(event_key):
        return True
    if _is_internal_trigger_damage_record(record):
        return True
    if _is_effectless_wrapper_record(record):
        return True
    classification = _classify_packet_buff_record(record)
    return classification.get("class") in {"utility", "utility_or_marker", "marker", "wrapper"}


def _build_rdps_preflight(
    buff_starts: list[dict[str, Any]],
    buff_windows: list[dict[str, Any]],
    *,
    battle_start_ms: int,
    battle_end_ms: int,
    active_character_keys: set[str] | None = None,
) -> dict[str, Any]:
    included_uids: set[str] = set()
    for window in buff_windows:
        included_uids.update(_window_uid_aliases(window))
    blockers: list[dict[str, Any]] = []
    checked_external = 0
    accepted_effects = 0
    accepted_non_rdps = 0
    for record in buff_starts:
        if not _record_overlaps_window(record, battle_start_ms=battle_start_ms, battle_end_ms=battle_end_ms):
            continue
        if not _record_could_affect_external_rdps(record):
            continue
        source_key = str(record.get("source_character_key") or "")
        if active_character_keys and source_key.startswith("chr_") and source_key not in active_character_keys:
            continue
        checked_external += 1
        uid = str(record.get("uid") or "")
        zone_effects = _collect_zone_effects(record)
        dynamic_effects = _extract_dynamic_effect_specs(record)
        has_effect = bool(zone_effects or dynamic_effects)
        included = bool(uid and uid in included_uids)
        classification = _classify_packet_buff_record(record)
        verified_entry = _rdps_registry_verified_effect_entry(record)
        if verified_entry is not None:
            if not has_effect and not _record_bb_key_set(record):
                continue
            validation_error = _rdps_registry_validation_error(verified_entry, record)
            if validation_error is not None:
                blockers.append(
                    {
                        "uid": uid,
                        "event_key": record.get("event_key"),
                        "raw_event_key": record.get("raw_event_key"),
                        "source_character_key": record.get("source_character_key"),
                        "source_skill_key": record.get("source_skill_key"),
                        "source_skill_family_key": record.get("source_skill_family_key"),
                        "target_character_key": record.get("target_character_key"),
                        "target_enemy_key": record.get("target_enemy_key"),
                        "class": classification.get("class"),
                        "reason": validation_error.get("reason"),
                        "bb_keys": sorted(set(str(key) for key in record.get("bb_keys") or [])),
                        "unknown_bb_keys": validation_error.get("unknown_bb_keys"),
                        "required_bb_keys": validation_error.get("required_bb_keys"),
                        "has_effect": has_effect,
                        "included_effect_window": included,
                        "packet_mapping_rejected": bool(record.get("packet_mapping_rejected")),
                    }
                )
                continue
            accepted_effects += 1
            continue
        if _known_non_rdps_buff_record(record):
            accepted_non_rdps += 1
            continue
        if included and has_effect:
            if verified_entry is None:
                blockers.append(
                    {
                        "uid": uid,
                        "event_key": record.get("event_key"),
                        "raw_event_key": record.get("raw_event_key"),
                        "source_character_key": record.get("source_character_key"),
                        "source_skill_key": record.get("source_skill_key"),
                        "source_skill_family_key": record.get("source_skill_family_key"),
                        "target_character_key": record.get("target_character_key"),
                        "target_enemy_key": record.get("target_enemy_key"),
                        "class": classification.get("class"),
                        "reason": "included external rDPS effect is not in rdps_semantics_registry.verified_effects",
                        "bb_keys": sorted(set(str(key) for key in record.get("bb_keys") or [])),
                        "has_effect": has_effect,
                        "included_effect_window": included,
                        "packet_mapping_rejected": bool(record.get("packet_mapping_rejected")),
                    }
                )
                continue
            accepted_effects += 1
            continue
        if included and classification.get("class") == "effect":
            if verified_entry is None:
                blockers.append(
                    {
                        "uid": uid,
                        "event_key": record.get("event_key"),
                        "raw_event_key": record.get("raw_event_key"),
                        "source_character_key": record.get("source_character_key"),
                        "source_skill_key": record.get("source_skill_key"),
                        "source_skill_family_key": record.get("source_skill_family_key"),
                        "target_character_key": record.get("target_character_key"),
                        "target_enemy_key": record.get("target_enemy_key"),
                        "class": classification.get("class"),
                        "reason": "included external rDPS effect is not in rdps_semantics_registry.verified_effects",
                        "bb_keys": sorted(set(str(key) for key in record.get("bb_keys") or [])),
                        "has_effect": has_effect,
                        "included_effect_window": included,
                        "packet_mapping_rejected": bool(record.get("packet_mapping_rejected")),
                    }
                )
                continue
            accepted_effects += 1
            continue
        blockers.append(
            {
                "uid": uid,
                "event_key": record.get("event_key"),
                "raw_event_key": record.get("raw_event_key"),
                "source_character_key": record.get("source_character_key"),
                "source_skill_key": record.get("source_skill_key"),
                "source_skill_family_key": record.get("source_skill_family_key"),
                "target_character_key": record.get("target_character_key"),
                "target_enemy_key": record.get("target_enemy_key"),
                "class": classification.get("class"),
                "reason": classification.get("reason"),
                "bb_keys": sorted(set(str(key) for key in record.get("bb_keys") or [])),
                "has_effect": has_effect,
                "included_effect_window": included,
                "packet_mapping_rejected": bool(record.get("packet_mapping_rejected")),
            }
        )

    return {
        "mode": "pre_allocation_semantic_gate",
        "ok": not blockers,
        "checked_external_buff_count": checked_external,
        "accepted_effect_buff_count": accepted_effects,
        "accepted_non_rdps_buff_count": accepted_non_rdps,
        "blocker_count": len(blockers),
        "blockers": blockers[:100],
    }


def _static_entry_applies_to_hit(entry: dict[str, Any], hit: dict[str, Any]) -> bool:
    zone = str(entry.get("zone") or "")
    if zone not in _RDPS_ALLOCATABLE_ZONES:
        return False
    rate = _safe_positive_rate(entry.get("rate"))
    if rate is None:
        return False
    if not _effect_applies_to_damage_element(
        str(entry.get("element") or "all"),
        hit.get("damage_element"),
        hit.get("damage_school"),
    ):
        return False

    skill_groups = {str(group or "") for group in entry.get("skill_groups") or [] if str(group or "")}
    if not skill_groups:
        return True
    skill_key = str(hit.get("skill_key") or "").lower()
    try:
        group_type = int(hit.get("skill_group_type"))
    except (TypeError, ValueError):
        group_type = None
    if "normal" in skill_groups and ("attack" in skill_key or "normal_attack" in skill_key):
        return True
    if "skill" in skill_groups and ("normal_skill" in skill_key or group_type == 1):
        return True
    if "combo" in skill_groups and ("combo" in skill_key or group_type == 3):
        return True
    if "ultimate" in skill_groups and ("ult" in skill_key or "ultimate" in skill_key or group_type == 2):
        return True
    return False


def _packet_modifier_guard_signature(effect: dict[str, Any]) -> tuple[Any, ...]:
    zone = str(effect.get("zone") or "")
    element = _normalize_effect_element(effect.get("element"))
    bb_keys = tuple(
        str(effect.get(key_name) or "")
        for key_name in ("bb_key", "add_bb_key", "delay_bb_key", "tick_bb_key", "max_bb_key")
    )
    try:
        attr_type = int(effect.get("attr_type")) if effect.get("attr_type") is not None else None
    except (TypeError, ValueError):
        attr_type = None
    condition_signature = _effect_condition_signature(effect)
    if any(bb_keys) or attr_type is not None or condition_signature:
        return ("keyed", zone, element, bb_keys, attr_type, condition_signature)
    return _effect_row_signature(effect)


def _matched_packet_defender_effect_signatures(
    *,
    hit: dict[str, Any],
    buff_windows: list[dict[str, Any]],
    defender_modifier_uids: set[str],
) -> set[tuple[Any, ...]]:
    if not defender_modifier_uids:
        return set()

    target_enemy_key = str(hit.get("target_enemy_key") or "")
    hit_ts_ms = int(hit.get("ts_ms") or 0)
    hit_line_no = int(hit.get("line_no") or 0)
    skill_key = str(hit.get("skill_key") or "")
    signatures: set[tuple[Any, ...]] = set()
    for window in buff_windows:
        if not target_enemy_key or str(window.get("target_character_key") or "") != target_enemy_key:
            continue
        if not (_window_uid_aliases(window) & defender_modifier_uids):
            continue
        window_effects = _window_effects_at_ts(window, hit_ts_ms)
        if not window_effects:
            continue
        window_start_ts_ms = int(window.get("start_ts_ms") or 0)
        if not (window_start_ts_ms <= hit_ts_ms <= int(window.get("end_ts_ms") or 0)):
            continue
        window_line_no = int(window.get("start_line_no") or window.get("line_no") or 0)
        if window_start_ts_ms == hit_ts_ms and hit_line_no and window_line_no and window_line_no > hit_line_no:
            continue
        if window_start_ts_ms == hit_ts_ms and str(window.get("event_key") or "") == skill_key:
            continue
        skill_family_key = window.get("skill_family_key")
        if skill_family_key and hit.get("skill_family_key") != skill_family_key:
            continue
        skill_filter = _BUFF_SKILL_FILTER.get(str(window.get("event_key") or ""))
        if skill_filter and not skill_filter.search(skill_key):
            continue

        for effect in window_effects:
            if str(effect.get("zone") or "") == "vuln_taken":
                signatures.add(_packet_modifier_guard_signature(effect))
    return signatures


def _active_target_buff_ids_for_hit(
    hit: dict[str, Any],
    condition_buff_records: list[dict[str, Any]] | None,
) -> set[str]:
    target_key = str(hit.get("target_enemy_key") or "")
    if not target_key or not condition_buff_records:
        return set()
    hit_ts_ms = int(hit.get("ts_ms") or 0)
    hit_line_no = int(hit.get("line_no") or 0)
    active: set[str] = set()
    for record in condition_buff_records:
        if str(record.get("target_enemy_key") or record.get("target_character_key") or "") != target_key:
            continue
        try:
            start_ts_ms = int(record.get("ts_ms") or 0)
        except (TypeError, ValueError):
            start_ts_ms = 0
        if start_ts_ms > hit_ts_ms:
            continue
        try:
            end_ts_ms = int(record.get("end_ts_ms")) if record.get("end_ts_ms") is not None else None
        except (TypeError, ValueError):
            end_ts_ms = None
        if end_ts_ms is not None and hit_ts_ms > end_ts_ms:
            continue
        try:
            start_line_no = int(record.get("line_no") or 0)
        except (TypeError, ValueError):
            start_line_no = 0
        if start_ts_ms == hit_ts_ms and hit_line_no and start_line_no and start_line_no > hit_line_no:
            continue
        for key in (record.get("event_key"), record.get("raw_event_key")):
            normalized = _normalize_buff_id(key)
            if normalized:
                active.add(normalized)
    return active


def _arts_strength_effect_contributors(
    *,
    effect_window: dict[str, Any],
    effect: dict[str, Any],
    buff_windows: list[dict[str, Any]],
) -> list[tuple[str, float, dict[str, Any] | None]]:
    """Split a fracture/conduct/corrosion rate by its source-strength provenance."""

    event_key = _normalize_buff_id(effect_window.get("event_key"))
    source_key = str(effect_window.get("source_character_key") or "")
    final_rate = float(effect.get("rate") or 0.0)
    if event_key not in _ARTS_STRENGTH_EFFECT_BUFF_IDS or not source_key or final_rate <= 0:
        return [(source_key, final_rate, None)]

    applied_at_ms = int(effect_window.get("start_ts_ms") or 0)
    applied_line_no = int(effect_window.get("start_line_no") or effect_window.get("line_no") or 0)
    self_points = max(float(effect_window.get("source_static_arts_strength") or 0.0), 0.0)
    external_points: dict[str, float] = defaultdict(float)

    for candidate in buff_windows:
        if str(candidate.get("target_character_key") or "") != source_key:
            continue
        start_ms = int(candidate.get("start_ts_ms") or 0)
        end_ms = int(candidate.get("end_ts_ms") or 0)
        if not (start_ms <= applied_at_ms <= end_ms):
            continue
        start_line_no = int(candidate.get("start_line_no") or candidate.get("line_no") or 0)
        if start_ms == applied_at_ms and applied_line_no and start_line_no and start_line_no > applied_line_no:
            continue
        provider_key = str(candidate.get("source_character_key") or "")
        if not provider_key:
            continue
        for candidate_effect in _window_effects_at_ts(candidate, applied_at_ms):
            if str(candidate_effect.get("zone") or "") != "arts_strength":
                continue
            points = float(candidate_effect.get("rate") or 0.0)
            if points <= 0:
                continue
            if provider_key == source_key:
                self_points += points
            else:
                external_points[provider_key] += points

    external_total = sum(external_points.values())
    if external_total <= 0:
        return [(source_key, final_rate, None)]

    without_external = final_rate * (
        _arts_strength_effect_multiplier(self_points)
        / _arts_strength_effect_multiplier(self_points + external_total)
    )
    external_rate = max(final_rate - without_external, 0.0)
    contributors: list[tuple[str, float, dict[str, Any] | None]] = [(source_key, without_external, None)]
    for provider_key, points in external_points.items():
        provider_rate = external_rate * (points / external_total)
        provenance = {
            "derived_from_zone": "arts_strength",
            "effect_event_key": effect_window.get("event_key"),
            "effect_source_character_key": source_key,
            "arts_strength_points": points,
            "arts_strength_self_points": self_points,
            "arts_strength_external_points": external_total,
        }
        contributors.append((provider_key, provider_rate, provenance))
    return contributors


def _rdps_debug_record_arts_effect_provenance(
    *,
    effect_window: dict[str, Any],
    effect: dict[str, Any],
    source_key: str,
    rate: float,
    provenance: dict[str, Any] | None,
    scope: str,
) -> dict[str, Any]:
    debug_effect = dict(effect)
    debug_effect["rate"] = rate
    debug_window = dict(effect_window)
    debug_window["source_character_key"] = source_key
    debug_window["source_character_name"] = _resolve_character_name(source_key) or source_key
    record = _rdps_debug_record_applicable_effect(window=debug_window, effect=debug_effect, scope=scope)
    if provenance:
        record.update(
            {
                "derived_from_zone": "arts_strength",
                "effect_source_character_key": provenance.get("effect_source_character_key"),
                "arts_strength_points": _round4(provenance.get("arts_strength_points") or 0.0),
                "arts_strength_self_points": _round4(provenance.get("arts_strength_self_points") or 0.0),
                "arts_strength_external_points": _round4(provenance.get("arts_strength_external_points") or 0.0),
            }
        )
    return record


def _allocate_rdps_for_hit(
    hit: dict[str, Any],
    buff_windows: list[dict[str, Any]],
    *,
    include_debug: bool = False,
    buff_records_by_uid: dict[str, dict[str, Any]] | None = None,
    condition_buff_records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    attacker_key = hit["character_key"]
    target_enemy_key = hit["target_enemy_key"]
    hit_value = float(hit["hit_value"])
    hit_ts_ms = hit["ts_ms"]
    damage_element = hit.get("damage_element")
    damage_school = hit.get("damage_school")
    arts_strength_damage_hit = _is_arts_strength_damage_hit(hit)
    packet_modifier_uids = hit.get("packet_modifier_uids") if isinstance(hit.get("packet_modifier_uids"), dict) else {}
    attacker_modifier_uids = {str(item) for item in packet_modifier_uids.get("attacker") or [] if str(item)}
    defender_modifier_uids = {str(item) for item in packet_modifier_uids.get("defender") or [] if str(item)}
    packet_attr_details = hit.get("packet_attr_details") if isinstance(hit.get("packet_attr_details"), dict) else {}
    defender_allowed_effects = _packet_attr_allowed_effects(packet_attr_details.get("defender") if isinstance(packet_attr_details, dict) else [])
    hit_line_no = int(hit.get("line_no") or 0)

    external_by_zone: dict[str, list[tuple[str, float, dict[str, Any] | None]]] = defaultdict(list)
    self_by_zone: dict[str, float] = defaultdict(float)
    captured_by_attr_type: dict[int, float] = defaultdict(float)
    contributors_by_zone: dict[str, list[dict[str, Any]]] = defaultdict(list) if include_debug else {}
    ignored_effects: list[dict[str, Any]] = []
    matched_packet_defender_effect_signatures = _matched_packet_defender_effect_signatures(
        hit=hit,
        buff_windows=buff_windows,
        defender_modifier_uids=defender_modifier_uids,
    ) if bool(hit.get("packet_modifier_seen")) else set()
    active_target_buff_ids = _active_target_buff_ids_for_hit(hit, condition_buff_records)
    hit["_active_target_buff_ids"] = sorted(active_target_buff_ids)

    for window in buff_windows:
        window_effects = _window_effects_at_ts(window, hit_ts_ms)
        if not window_effects:
            continue
        window_start_ts_ms = int(window.get("start_ts_ms") or 0)
        if not (window_start_ts_ms <= hit_ts_ms <= int(window.get("end_ts_ms") or 0)):
            continue
        window_line_no = int(window.get("start_line_no") or window.get("line_no") or 0)
        if window_start_ts_ms == hit_ts_ms and hit_line_no and window_line_no and window_line_no > hit_line_no:
            continue
        if window_start_ts_ms == hit_ts_ms and str(window.get("event_key") or "") == str(hit.get("skill_key") or ""):
            continue
        skill_family_key = window.get("skill_family_key")
        if skill_family_key and hit.get("skill_family_key") != skill_family_key:
            continue
        skill_filter = _BUFF_SKILL_FILTER.get(window["event_key"])
        if skill_filter and not skill_filter.search(str(hit.get("skill_key") or "")):
            continue

        applies_to_attacker = window["target_character_key"] == attacker_key
        applies_to_enemy = bool(target_enemy_key) and window["target_character_key"] == target_enemy_key
        if not applies_to_attacker and not applies_to_enemy:
            continue

        window_uid_aliases = _window_uid_aliases(window)
        packet_uid_match = bool(window_uid_aliases & defender_modifier_uids)

        source_key = window["source_character_key"]
        if not source_key:
            continue

        for effect in window_effects:
            zone = effect["zone"]
            rate = effect["rate"]
            element = effect.get("element")
            packet_uid_restricted = (
                bool(hit.get("packet_modifier_seen"))
                and applies_to_enemy
                and bool(window_uid_aliases)
                and zone == "vuln_taken"
                and _packet_modifier_guard_signature(effect) in matched_packet_defender_effect_signatures
            )
            if packet_uid_restricted and not packet_uid_match:
                if include_debug:
                    ignored_effects.append(
                        {
                            **_rdps_debug_record_applicable_effect(window=window, effect=effect, scope="ignored"),
                            "reason": "packet_defender_uid_suppressed",
                            "reason_group": "packet_modifier_uid_mismatch",
                            "packet_modifier_guard": "defender_uid_selection",
                            "packet_modifier_seen": True,
                            "packet_modifier_uids": {
                                "attacker": sorted(attacker_modifier_uids),
                                "defender": sorted(defender_modifier_uids),
                            },
                            "candidate_uids": sorted(window_uid_aliases),
                        }
                    )
                continue
            effect_skill_filter = _BUFF_EFFECT_SKILL_FILTER.get((window["event_key"], zone))
            if effect_skill_filter and not effect_skill_filter.search(str(hit.get("skill_key") or "")):
                continue
            attr_type = effect.get("attr_type")
            if isinstance(attr_type, int) and not _attr_type_applies_to_skill(
                attr_type,
                str(hit.get("skill_key") or ""),
            ):
                continue
            if zone == "crit":
                if include_debug:
                    ignored_effects.append(
                        {
                            **_rdps_debug_record_applicable_effect(window=window, effect=effect, scope="ignored"),
                            "reason": "crit_not_allocated",
                        }
                    )
                continue
            if zone not in _RDPS_ALLOCATABLE_ZONES:
                if include_debug:
                    ignored_effects.append(
                        {
                            **_rdps_debug_record_applicable_effect(window=window, effect=effect, scope="ignored"),
                            "reason": "utility_not_allocated",
                        }
                    )
                continue
            if zone == "arts_strength" and not arts_strength_damage_hit:
                if include_debug:
                    ignored_effects.append(
                        {
                            **_rdps_debug_record_applicable_effect(window=window, effect=effect, scope="ignored"),
                            "reason": "arts_strength_only_affects_anomaly_damage",
                        }
                    )
                continue
            if rate <= 0:
                continue
            if not _effect_element_applies_to_hit(effect, damage_element, damage_school):
                if include_debug:
                    ignored_effects.append(
                        {
                            **_rdps_debug_record_applicable_effect(window=window, effect=effect, scope="ignored"),
                            **_element_filter_debug_fields(effect["element"], damage_element, damage_school),
                        }
                    )
                continue
            condition_failure = _effect_condition_failure(effect, hit)
            if condition_failure:
                if include_debug:
                    ignored_effects.append(
                        {
                            **_rdps_debug_record_applicable_effect(window=window, effect=effect, scope="ignored"),
                            **condition_failure,
                        }
                    )
                continue
            if (
                source_key != attacker_key
                and applies_to_enemy
                and defender_allowed_effects
                and not defender_modifier_uids
                and (zone, _normalize_effect_element(effect["element"])) not in defender_allowed_effects
            ):
                if include_debug:
                    ignored_effects.append(
                        {
                            **_rdps_debug_record_applicable_effect(window=window, effect=effect, scope="ignored"),
                            "reason": "packet_attr_mismatch",
                        }
                    )
                continue
            if applies_to_attacker and isinstance(attr_type, int):
                captured_by_attr_type[attr_type] += rate
            effect_contributors = (
                _arts_strength_effect_contributors(
                    effect_window=window,
                    effect=effect,
                    buff_windows=buff_windows,
                )
                if applies_to_enemy
                else [(source_key, rate, None)]
            )
            for contributor_key, contributor_rate, provenance in effect_contributors:
                if contributor_rate <= 0:
                    continue
                scope = "self" if contributor_key == attacker_key else "external"
                record = (
                    _rdps_debug_record_arts_effect_provenance(
                        effect_window=window,
                        effect=effect,
                        source_key=contributor_key,
                        rate=contributor_rate,
                        provenance=provenance,
                        scope=scope,
                    )
                    if include_debug
                    else None
                )
                if contributor_key == attacker_key:
                    self_by_zone[zone] += contributor_rate
                else:
                    external_by_zone[zone].append((contributor_key, contributor_rate, record))
                if include_debug and record is not None:
                    contributors_by_zone[zone].append(record)

    for raw_attr_type, final_value in (hit.get("baseline") or {}).items():
        try:
            attr_type = int(raw_attr_type)
            final_rate = float(final_value)
        except (TypeError, ValueError):
            continue
        if attr_type == 2:
            continue
        mapping = _ATTR_TYPE_TO_EFFECT.get(attr_type)
        if mapping is None:
            continue
        zone, element = mapping
        if zone == "crit":
            continue
        if not _attr_type_applies_to_skill(attr_type, str(hit.get("skill_key") or "")):
            continue
        if not _effect_applies_to_damage_element(element, damage_element, damage_school):
            continue
        baseline_rate = final_rate - captured_by_attr_type.get(attr_type, 0.0)
        if baseline_rate <= 0.001:
            continue
        self_by_zone[zone] += baseline_rate
        if include_debug:
            contributors_by_zone[zone].append(
                _rdps_debug_record_baseline_self(
                    hit=hit,
                    attr_type=attr_type,
                    zone=zone,
                    element=str(element or "all"),
                    rate=baseline_rate,
                    final_value=final_rate,
                    captured=captured_by_attr_type.get(attr_type, 0.0),
                )
            )

    for entry in hit.get("static_multiplier_entries") or []:
        if not isinstance(entry, dict) or not _static_entry_applies_to_hit(entry, hit):
            continue
        zone = str(entry.get("zone") or "")
        rate = float(entry.get("rate") or 0.0)
        self_by_zone[zone] += rate
        if include_debug:
            contributors_by_zone[zone].append(_rdps_debug_record_static_self(hit=hit, entry=entry))

    if arts_strength_damage_hit:
        for entry in hit.get("static_arts_strength_entries") or []:
            if not isinstance(entry, dict):
                continue
            points = float(entry.get("rate") or 0.0)
            if points <= 0:
                continue
            self_by_zone["arts_strength"] += points
            if include_debug:
                contributors_by_zone["arts_strength"].append(
                    _rdps_debug_record_static_self(hit=hit, entry=entry)
                )

    for zone in _DPD_ZONE_BUCKETS:
        bucket_value = _dpd_bucket_value_for_zone(zone, hit.get("dpd_raw"))
        if bucket_value is None:
            continue
        recognized_total = self_by_zone.get(zone, 0.0) + sum(
            rate for _, rate, _ in external_by_zone.get(zone, [])
        )
        residual = (bucket_value - 1.0) - recognized_total
        if abs(residual) > 0.003:
            self_by_zone[zone] += residual
            if include_debug:
                contributors_by_zone[zone].append(
                    _rdps_debug_record_dpd_self_residual(hit=hit, zone=zone, rate=residual)
                )

    m_values: dict[str, float] = {}
    external_sum_by_zone: dict[str, float] = {}
    for zone, contributors in external_by_zone.items():
        external_sum = sum(rate for _, rate, _ in contributors)
        if external_sum <= 0:
            continue
        self_sum = self_by_zone.get(zone, 0.0)
        if zone == "arts_strength":
            m_z = (
                _arts_strength_damage_multiplier(self_sum + external_sum)
                / _arts_strength_damage_multiplier(self_sum)
            )
        else:
            m_z = (1.0 + self_sum + external_sum) / (1.0 + self_sum)
        bucket_value = _dpd_bucket_value_for_zone(zone, hit.get("dpd_raw"))
        if bucket_value is not None and bucket_value > 1.0001:
            calibrated_m_z = bucket_value / max(1.0, bucket_value - external_sum)
            if calibrated_m_z > 1.0001:
                m_z = calibrated_m_z
        if m_z <= 1.0:
            continue
        external_sum_by_zone[zone] = external_sum
        m_values[zone] = m_z

    hit_rdps_contributions: dict[str, float] = defaultdict(float)
    if not m_values:
        product_external = 1.0
        attacker_share = hit_value
        external_pool = 0.0
        hit_rdps_contributions[attacker_key] += hit_value
    else:
        product_external = 1.0
        for value in m_values.values():
            product_external *= value

        if product_external <= 1.0:
            attacker_share = hit_value
            external_pool = 0.0
            hit_rdps_contributions[attacker_key] += hit_value
        else:
            attacker_share = hit_value / product_external
            external_pool = hit_value - attacker_share
            hit_rdps_contributions[attacker_key] += attacker_share
            log_total = sum(log(value) for value in m_values.values())
            if log_total <= 0:
                hit_rdps_contributions[attacker_key] += external_pool
            else:
                for zone, contributors in external_by_zone.items():
                    if zone not in m_values:
                        continue
                    zone_share = external_pool * (log(m_values[zone]) / log_total)
                    zone_external_sum = external_sum_by_zone[zone]
                    if zone_external_sum <= 0:
                        hit_rdps_contributions[attacker_key] += zone_share
                        continue
                    for source_key, rate, record in contributors:
                        credit = zone_share * (rate / zone_external_sum)
                        if include_debug and record is not None:
                            record["rdps_credit"] = _round4(credit)
                        hit_rdps_contributions[source_key] += credit

    normalized_contributions = {
        character_key: value
        for character_key, value in hit_rdps_contributions.items()
        if value > 0.0001
    }
    result: dict[str, Any] = {
        "contributions_map": normalized_contributions,
        "contributions_list": _rdps_contribution_rows(normalized_contributions, sort_by_value=True),
    }

    if not include_debug:
        return result

    zone_external_share: dict[str, float] = defaultdict(float)
    log_total = sum(log(value) for value in m_values.values()) if product_external > 1.0 else 0.0
    if log_total > 0 and external_pool > 0:
        for zone in external_by_zone:
            if zone not in m_values:
                continue
            zone_external_share[zone] = external_pool * (log(m_values[zone]) / log_total)

    zones: list[dict[str, Any]] = []
    for zone in sorted(
        set(self_by_zone) | set(external_by_zone),
        key=lambda key: (_RDPS_DEBUG_ZONE_ORDER.get(key, 99), key),
    ):
        self_rate = self_by_zone.get(zone, 0.0)
        external_rate = external_sum_by_zone.get(
            zone,
            sum(rate for _, rate, _ in external_by_zone.get(zone, [])),
        )
        total_rate = self_rate + external_rate
        total_multiplier = (
            _arts_strength_damage_multiplier(total_rate)
            if zone == "arts_strength"
            else 1.0 + total_rate
        )
        bucket_value = _dpd_bucket_value_for_zone(zone, hit.get("dpd_raw"))
        zones.append(
            {
                "zone": zone,
                "zone_label": _RDPS_DEBUG_ZONE_LABELS.get(zone, zone),
                "self_rate": _round4(self_rate),
                "external_rate": _round4(external_rate),
                "total_rate": _round4(total_rate),
                "total_multiplier": _round4(total_multiplier),
                "external_multiplier": _round4(m_values.get(zone, 1.0)),
                "zone_external_share": _round4(zone_external_share.get(zone, 0.0)),
                "dpd_bucket": (
                    {
                        "side": _DPD_ZONE_BUCKETS[zone][0],
                        "index": _DPD_ZONE_BUCKETS[zone][1],
                        "value": _round4(bucket_value),
                    }
                    if zone in _DPD_ZONE_BUCKETS and bucket_value is not None
                    else None
                ),
                "contributors": sorted(
                    contributors_by_zone.get(zone, []),
                    key=lambda item: (
                        0 if item.get("scope") == "external" else 1,
                        -float(item.get("rate") or 0.0),
                        str(item.get("source_character_name") or ""),
                        str(item.get("event_key") or ""),
                    ),
                ),
            }
        )

    external_sources: dict[str, dict[str, Any]] = {}
    for contributors in external_by_zone.values():
        for source_key, _rate, record in contributors:
            current = external_sources.setdefault(
                source_key,
                {
                    "character_key": source_key,
                    "character_name": (record or {}).get("source_character_name") or _resolve_character_name(source_key) or source_key,
                    "effect_count": 0,
                    "rdps_credit": 0.0,
                },
            )
            current["effect_count"] += 1
            if record is not None:
                current["rdps_credit"] += float(record.get("rdps_credit") or 0.0)

    modifier_details: list[dict[str, Any]] = []
    record_index = buff_records_by_uid if isinstance(buff_records_by_uid, dict) else {}
    for side, uids in (("attacker", sorted(attacker_modifier_uids)), ("defender", sorted(defender_modifier_uids))):
        for uid in uids:
            record = record_index.get(uid)
            if not isinstance(record, dict):
                modifier_details.append(
                    {
                        "side": side,
                        "uid": uid,
                        "event_key": "",
                        "event_name": "",
                        "source_character_name": "",
                        "target_name": "",
                        "bb_values": {},
                    }
                )
                continue
            target_name = (
                record.get("target_character_name")
                or record.get("target_enemy_name")
                or record.get("owner_raw")
                or ""
            )
            modifier_details.append(
                {
                    "side": side,
                    "uid": uid,
                    "event_key": record.get("event_key"),
                    "event_name": " / ".join(_collect_buff_labels(record)) or record.get("event_key") or "",
                    "source_character_key": record.get("source_character_key"),
                    "source_character_name": record.get("source_character_name"),
                    "target_key": record.get("target_character_key") or record.get("target_enemy_key"),
                    "target_name": target_name,
                    "bb_values": dict(record.get("bb_values") or {}),
                    "bb_keys": sorted(set(str(key) for key in record.get("bb_keys") or [])),
                }
            )

    result.update(
        {
            "zones": _sort_rdps_debug_zones(zones),
            "ignored_effects": ignored_effects,
            "product_external_multiplier": _round4(product_external),
            "attacker_share": _round4(attacker_share),
            "external_pool": _round4(external_pool),
            "external_sources": sorted(
                (
                    {
                        **value,
                        "rdps_credit": _round4(value["rdps_credit"]),
                    }
                    for value in external_sources.values()
                ),
                key=lambda item: (-float(item.get("rdps_credit") or 0.0), str(item.get("character_name") or "")),
            ),
            "zone_summary": " / ".join(
                f"{zone['zone_label']} x{float(zone['external_multiplier']):.4f}"
                for zone in _sort_rdps_debug_zones(zones)
                if float(zone.get("external_multiplier") or 1.0) > 1.0001
            ),
            "buff_source_summary": " / ".join(
                f"{source['character_name']} +{float(source['rdps_credit']):.1f}"
                for source in sorted(
                    (
                        {
                            **value,
                            "rdps_credit": _round4(value["rdps_credit"]),
                        }
                        for value in external_sources.values()
                    ),
                    key=lambda item: (-float(item.get("rdps_credit") or 0.0), str(item.get("character_name") or "")),
                )
                if float(source.get("rdps_credit") or 0.0) > 0.0001
            ),
            "packet_modifier_uids": {
                "attacker": sorted(attacker_modifier_uids),
                "defender": sorted(defender_modifier_uids),
            },
            "packet_modifier_details": modifier_details,
        }
    )
    return result


def _compute_rdps_damage_shares(
    hits: list[dict[str, Any]],
    buff_windows: list[dict[str, Any]],
    condition_buff_records: list[dict[str, Any]] | None = None,
) -> dict[str, float]:
    rdps_damage: dict[str, float] = defaultdict(float)

    for hit in hits:
        allocation = _allocate_rdps_for_hit(
            hit,
            buff_windows,
            include_debug=False,
            condition_buff_records=condition_buff_records,
        )
        normalized_contributions = dict(allocation.get("contributions_map") or {})
        hit["rdps_contributions"] = normalized_contributions
        for character_key, value in normalized_contributions.items():
            rdps_damage[character_key] += value

    return dict(rdps_damage)


def _build_rdps_damage_basis(
    hits: list[dict[str, Any]],
    rdps_damage: dict[str, float],
    total_damage: int,
) -> dict[str, Any]:
    total_rdps_contribution = sum(float(value or 0.0) for value in rdps_damage.values())
    hit_conservation_deltas: list[float] = []
    for hit in hits:
        contribution_total = sum(
            float(value or 0.0)
            for value in (hit.get("rdps_contributions") or {}).values()
        )
        hit_conservation_deltas.append(contribution_total - float(hit.get("hit_value") or 0.0))

    packet_final_values = [
        float(hit["packet_final_value"])
        for hit in hits
        if hit.get("packet_final_value") is not None
    ]
    packet_raw_values = [
        float(hit["packet_raw_value"])
        for hit in hits
        if hit.get("packet_raw_value") is not None
    ]
    conservation_delta = total_rdps_contribution - float(total_damage)
    max_hit_delta = max((abs(delta) for delta in hit_conservation_deltas), default=0.0)
    hit_mismatch_count = sum(1 for delta in hit_conservation_deltas if abs(delta) > 0.01)
    return {
        "mode": "packet_hp_loss",
        "rdps_mode": "packet_hp_loss",
        "source": "HP_V2.hit with packet eHP overkill cap",
        "hit_count": len(hits),
        "packet_grounded_hit_count": sum(1 for hit in hits if hit.get("packet_hit_value") is not None),
        "packet_hit_count": sum(1 for hit in hits if hit.get("packet_hit_value") is not None),
        "packet_final_value_count": len(packet_final_values),
        "packet_raw_value_count": len(packet_raw_values),
        "formula_grounded_hit_count": 0,
        "missing_packet_hit_count": sum(1 for hit in hits if hit.get("packet_hit_value") is None),
        "overkill_capped_hit_count": sum(1 for hit in hits if int(hit.get("overkill_damage") or 0) > 0),
        "total_damage": total_damage,
        "total_packet_final_value": _round4(sum(packet_final_values)) if packet_final_values else None,
        "total_packet_raw_value": _round4(sum(packet_raw_values)) if packet_raw_values else None,
        "total_rdps_contribution": _round4(total_rdps_contribution),
        "rdps_conservation_delta": _round4(conservation_delta),
        "rdps_conservation_ok": abs(conservation_delta) <= 0.01 and hit_mismatch_count == 0,
        "hit_conservation_mismatch_count": hit_mismatch_count,
        "max_hit_conservation_delta": _round4(max_hit_delta),
    }


def _resolve_weapon_buff_sources(buff_records: list[dict[str, Any]]) -> None:
    weapon_records = [record for record in buff_records if record.get("is_weapon_buff")]
    for record in weapon_records:
        raw_source_key = record.get("raw_source_character_key")
        target_key = record.get("target_character_key")
        if not raw_source_key or not target_key or raw_source_key == target_key:
            continue

        peer_targets = {
            peer.get("target_character_key")
            for peer in weapon_records
            if peer.get("event_key") == record.get("event_key")
            and peer.get("raw_source_character_key") == raw_source_key
            and peer.get("target_character_key")
            and abs(int(peer.get("ts_ms") or 0) - int(record.get("ts_ms") or 0)) <= 20
        }
        if len(peer_targets) < 2:
            continue

        record["source_character_key"] = raw_source_key
        record["source_character_name"] = _resolve_character_name(raw_source_key) or raw_source_key


def _buff_record_end_ts_ms(record: dict[str, Any], battle_end_ms: int) -> int:
    start_ts_ms = int(record["ts_ms"])
    duration_ms = _normalize_buff_duration_ms(
        start_ts_ms,
        event_key=record.get("event_key"),
        end_ts_ms=record.get("end_ts_ms"),
        raw_duration_ms=record.get("raw_duration_ms"),
        battle_end_ms=battle_end_ms,
    )
    return start_ts_ms + duration_ms


def _matches_hidden_combo_rule(buff_id: str) -> dict[str, Any] | None:
    for rule in _HIDDEN_COMBO_RULES:
        if any(pattern.search(buff_id) for pattern in rule["buff_patterns"]):
            return rule
    return None


def _build_hidden_combo_windows(
    hits: list[dict[str, Any]],
    buff_starts: list[dict[str, Any]],
    *,
    battle_end_ms: int,
) -> list[dict[str, Any]]:
    combo_windows: list[dict[str, Any]] = []
    ordered_hits = sorted(hits, key=lambda item: item["ts_ms"])

    for buff_record in buff_starts:
        source_key = buff_record.get("source_character_key")
        target_key = buff_record.get("target_character_key")
        buff_id = _normalize_buff_id(buff_record.get("event_key"))
        rule = _matches_hidden_combo_rule(buff_id)
        if not source_key or not target_key or rule is None:
            continue

        buff_start_ms = int(buff_record["ts_ms"])
        buff_end_ms = _buff_record_end_ts_ms(buff_record, battle_end_ms)

        for hit in ordered_hits:
            if hit["character_key"] != target_key:
                continue
            if not (buff_start_ms <= hit["ts_ms"] <= buff_end_ms):
                continue

            combo_context = _resolve_combo_consume_context(hit)
            if combo_context is None:
                continue
            combo_group_type, skill_family_key = combo_context
            rate = rule["skill_group_rates"].get(combo_group_type)
            if rate is None or rate <= 0:
                continue

            combo_windows.append(
                {
                    "start_ts_ms": hit["ts_ms"],
                    "end_ts_ms": min(hit["ts_ms"] + int(rule["cast_window_ms"]), battle_end_ms),
                    "duration_ms": min(int(rule["cast_window_ms"]), max(battle_end_ms - hit["ts_ms"], 1)),
                    "source_character_key": source_key,
                    "source_character_name": buff_record.get("source_character_name"),
                    "target_character_key": target_key,
                    "target_character_name": buff_record.get("target_character_name"),
                    "target_player_key": target_key,
                    "target_enemy_key": None,
                    "event_key": f"{buff_id}::{skill_family_key}",
                    "event_name": "连击增伤",
                    "zone_effects": [{"zone": "combo", "element": "all", "rate": rate}],
                    "skill_family_key": skill_family_key,
                }
            )
            break

    return combo_windows


def _build_combo_consume_windows(
    hits: list[dict[str, Any]],
    buff_starts: list[dict[str, Any]],
    *,
    battle_end_ms: int,
) -> list[dict[str, Any]]:
    combo_windows: list[dict[str, Any]] = []
    ordered_hits = sorted(hits, key=lambda item: item["ts_ms"])
    trigger_records: list[dict[str, Any]] = []
    consume_records: list[dict[str, Any]] = []

    for buff_record in buff_starts:
        buff_id = _normalize_buff_id(buff_record.get("event_key"))
        source_key = buff_record.get("source_character_key")
        target_key = buff_record.get("target_character_key")
        if not source_key or not target_key:
            continue

        if buff_id in _GENERIC_COMBO_IMBUE_BUFF_IDS:
            consume_records.append(
                {
                    "buff_record": buff_record,
                    "source_key": source_key,
                    "target_key": target_key,
                    "start_ms": int(buff_record["ts_ms"]),
                }
            )
            continue

        if buff_id != _GENERIC_COMBO_TRIGGER_BUFF_ID:
            continue

        buff_start_ms = int(buff_record["ts_ms"])
        buff_end_ms = _buff_record_end_ts_ms(buff_record, battle_end_ms)
        trigger_records.append(
            {
                "buff_record": buff_record,
                "source_key": source_key,
                "target_key": target_key,
                "start_ms": buff_start_ms,
                "end_ms": buff_end_ms,
            }
        )

    trigger_records.sort(
        key=lambda record: (
            int(record["start_ms"]),
            str(record["source_key"] or ""),
            str(record["target_key"] or ""),
        )
    )
    trigger_groups: list[dict[str, Any]] = []
    for record in trigger_records:
        group = next(
            (
                candidate
                for candidate in reversed(trigger_groups)
                if candidate["source_key"] == record["source_key"]
                and abs(int(record["start_ms"]) - int(candidate["start_ms"])) <= _COMBO_TRIGGER_GROUP_WINDOW_MS
            ),
            None,
        )
        if group is None:
            group = {
                "source_key": record["source_key"],
                "start_ms": record["start_ms"],
                "records": [],
            }
            trigger_groups.append(group)
        group["records"].append(record)

    indexed_hits = list(enumerate(ordered_hits))
    matched_layers: list[dict[str, Any]] = []
    for group in trigger_groups:
        group_start_ms = min(int(record["start_ms"]) for record in group["records"])
        group_end_ms = max(int(record["end_ms"]) for record in group["records"])
        group_source_key = group["source_key"]

        consume_candidates = [
            record
            for record in consume_records
            if record["source_key"] == group_source_key
            and group_start_ms < int(record["start_ms"]) <= group_end_ms + _COMBO_TRIGGER_GROUP_WINDOW_MS
        ]
        if not consume_candidates:
            continue

        consume_record = min(
            consume_candidates,
            key=lambda record: (int(record["start_ms"]), str(record["target_key"] or "")),
        )
        consume_ts_ms = int(consume_record["start_ms"])
        target_key = consume_record["target_key"]
        source_key = consume_record["source_key"]

        hit_candidate: tuple[int, dict[str, Any], tuple[int, str]] | None = None
        for hit_index, hit in indexed_hits:
            if hit["character_key"] != target_key:
                continue
            if not (consume_ts_ms <= hit["ts_ms"] <= consume_ts_ms + _COMBO_CONSUME_MAX_WINDOW_MS):
                continue
            combo_context = _resolve_combo_consume_context(hit)
            if combo_context is None:
                continue
            hit_candidate = (hit_index, hit, combo_context)
            break

        if hit_candidate is None:
            continue

        hit_index, _hit, combo_context = hit_candidate
        combo_group_type, skill_family_key = combo_context
        matched_layers.append(
            {
                "consume_record": consume_record,
                "consume_ts_ms": consume_ts_ms,
                "target_key": target_key,
                "source_key": source_key,
                "source_record": group["records"][0]["buff_record"],
                "group_start_ms": group_start_ms,
                "hit_index": hit_index,
                "combo_group_type": combo_group_type,
                "skill_family_key": skill_family_key,
            }
        )

    consume_groups: dict[tuple[int, str, int, int, str], list[dict[str, Any]]] = {}
    for layer in matched_layers:
        group_key = (
            int(layer["consume_ts_ms"]),
            str(layer["target_key"] or ""),
            int(layer["hit_index"]),
            int(layer["combo_group_type"]),
            str(layer["skill_family_key"] or ""),
        )
        consume_groups.setdefault(group_key, []).append(layer)

    for layers in consume_groups.values():
        layers.sort(key=lambda layer: (int(layer["group_start_ms"]), str(layer["source_key"] or "")))
        marginal_rates = _combo_marginal_layer_rates(int(layers[0]["combo_group_type"]), len(layers))
        if not marginal_rates:
            continue

        capped_layers = layers[: len(marginal_rates)]
        total_rate = round(sum(marginal_rates), 6)
        rates_by_source: dict[str, dict[str, Any]] = {}
        for layer, rate in zip(capped_layers, marginal_rates):
            if rate <= 0:
                continue
            source_key = str(layer["source_key"] or "")
            if not source_key:
                continue
            bucket = rates_by_source.setdefault(
                source_key,
                {
                    "rate": 0.0,
                    "layers": [],
                    "first_layer": layer,
                },
            )
            bucket["rate"] = float(bucket["rate"]) + float(rate)
            bucket["layers"].append(layer)

        for source_key, bucket in rates_by_source.items():
            rate = round(float(bucket["rate"]), 6)
            if rate <= 0:
                continue
            first_layer = bucket["first_layer"]
            consume_record = first_layer["consume_record"]
            consume_buff_record = consume_record["buff_record"]
            source_buff_record = first_layer["source_record"]
            consume_ts_ms = int(first_layer["consume_ts_ms"])
            target_key = str(first_layer["target_key"] or "")
            skill_family_key = str(first_layer["skill_family_key"] or "")
            window_end_ms = min(consume_ts_ms + _COMBO_CONSUME_MAX_WINDOW_MS, battle_end_ms)
            combo_windows.append(
                {
                    "start_ts_ms": consume_ts_ms,
                    "end_ts_ms": window_end_ms,
                    "duration_ms": max(window_end_ms - consume_ts_ms, 1),
                    "source_character_key": source_key,
                    "source_character_name": source_buff_record.get("source_character_name"),
                    "target_character_key": target_key,
                    "target_character_name": consume_buff_record.get("target_character_name"),
                    "target_player_key": target_key,
                    "target_enemy_key": None,
                    "event_key": f"{_GENERIC_COMBO_TRIGGER_BUFF_ID}::{skill_family_key}",
                    "event_name": "连击增伤",
                    "zone_effects": [{"zone": "combo", "element": "all", "rate": rate}],
                    "skill_family_key": skill_family_key,
                    "combo_stack_count": len(capped_layers),
                    "combo_layer_count": len(bucket["layers"]),
                    "combo_total_rate": total_rate,
                    "combo_rate_model": "ordered_marginal_stack",
                }
            )

    return combo_windows


def _build_special_combo_windows(
    hits: list[dict[str, Any]],
    buff_starts: list[dict[str, Any]],
    *,
    battle_end_ms: int,
) -> list[dict[str, Any]]:
    combo_windows = _build_hidden_combo_windows(hits, buff_starts, battle_end_ms=battle_end_ms)
    combo_windows.extend(_build_combo_consume_windows(hits, buff_starts, battle_end_ms=battle_end_ms))
    return _merge_buff_windows(combo_windows)


def parse_raw_battle_log_text(
    text: str,
    *,
    file_name: str | None = None,
    first_hit_hint: str | None = None,
    last_hit_hint: str | None = None,
    reference_date: date | None = None,
    include_rdps_debug: bool = False,
    loadout_override_by_char: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    reference_date = reference_date or datetime.now().astimezone().date()
    text = _apply_short_actor_aliases(text)
    context_enemy_hint = _infer_context_enemy_hint(text)
    trace_identity_inference_seen = " IDENTITY_INFERENCE " in text
    first_hit_hint_ms = _parse_hint_timestamp_ms(first_hit_hint)
    last_hit_hint_ms = _parse_hint_timestamp_ms(last_hit_hint)

    hits: list[dict[str, Any]] = []
    hits_by_seq: dict[int, dict[str, Any]] = {}
    baseline_by_character: dict[str, dict[int, float]] = {}
    buff_starts: list[dict[str, Any]] = []
    roster_order: list[str] = []
    roster_seen: set[str] = set()
    participant_totals = _new_participant_totals()
    skill_totals = _new_skill_totals()
    enemy_counter: Counter[str] = Counter()
    last_enemy_hp_by_target: dict[str, int] = {}
    active_buff_starts_by_uid: dict[str, dict[str, Any]] = {}
    buff_start_index_by_uid_ts: dict[tuple[str, int], int] = {}
    packet_modifier_last_seen_by_uid: dict[str, int] = {}
    pending_attr_mods: dict[str, list[dict[str, str]]] = defaultdict(list)
    pending_buff_record: dict[str, Any] | None = None
    last_chr_src_on_owner: dict[str, tuple[str, int]] = {}
    recent_skill_casts_by_char: dict[str, list[dict[str, Any]]] = defaultdict(list)
    skill_casts: list[dict[str, Any]] = []
    active_skill_casts_by_inst: dict[str, dict[str, Any]] = {}
    # ATB_UPDATE（技力更新，v34+ 客户端 BattleOpUpdateAtbInfo）：主控角色重击回技力
    # = reason=AddValue 正 delta。排轴导出据此标记「回能量重击」区分主控 vs AI。
    # 按角色收集技力增加时刻。
    atb_gain_ms_by_char: dict[str, list[int]] = defaultdict(list)
    # CHAR_SKILLS（bridge 自 SC_SELF_SCENE_INFO_SKILLS 落盘）：角色技能等级清单，
    # 供排轴导出 API 消费；同角色多次同步取最后一次。
    char_skill_levels: dict[str, dict[str, int]] = {}
    first_party_action_ms: int | None = None
    recent_numeric_buffs_by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    dungeon_context: tuple[str, str] | None = None
    dungeon_context_id: str | None = None
    party_actor_ids: set[str] = set()
    game_timer_start_ms: int | None = None
    game_timer_end_ms: int | None = None
    game_timer_elapsed_ms: int | None = None
    game_timer_window_elapsed_ms: int | None = None
    official_timer_start_ms: int | None = None
    official_timer_elapsed_ms: int | None = None
    official_timer_end_ms: int | None = None
    timer_start_seen = False
    timer_end_seen = False
    timer_window_valid = True
    challenge_pass_confirmed = False
    official_pass_confirmed = False
    completion_source = ""
    active_suits_by_char: dict[str, set[str]] = {}
    weapon_override_by_char = {
        str(char_key): copy.deepcopy(row)
        for char_key, row in (loadout_override_by_char or {}).items()
        if isinstance(row, dict)
    }
    active_weapons_by_char: dict[str, str] = {
        char_key: str(row.get("weapon_template") or "")
        for char_key, row in weapon_override_by_char.items()
        if str(row.get("weapon_template") or "")
    }
    loadout_by_char: dict[str, dict[str, Any]] = copy.deepcopy(weapon_override_by_char)
    loadout_groups: list[dict[str, Any]] = []
    current_loadout_group: dict[str, Any] | None = None
    first_context_ms: int | None = None
    last_context_ms: int | None = None
    contract_tag_ids: list[int] = []
    contract_tag_score: int | None = None
    poise_damage_events: list[dict[str, Any]] = []

    def set_dungeon_context(raw_dungeon_id: str | None) -> None:
        nonlocal dungeon_context, dungeon_context_id
        context_id = str(raw_dungeon_id or "").strip()
        if not context_id:
            return
        dungeon_context_id = context_id
        # The official stage id is authoritative. If the newest official id
        # is not mapped, clear any older resolved context instead of silently
        # keeping or guessing a leaderboard from an enemy target.
        dungeon_context = _resolve_dungeon_context(context_id)

    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        ts_ms = _parse_prefixed_timestamp_ms(raw_line)
        if ts_ms is None:
            continue
        if first_context_ms is None:
            first_context_ms = ts_ms
        last_context_ms = ts_ms
        party_actor_ids.update(_collect_party_actor_ids(raw_line))

        if " LOADOUT reason=" in raw_line or "LOADOUT reason=" in raw_line:
            fields = _extract_fields(raw_line)
            current_loadout_group = {
                "ts_ms": ts_ms,
                "reason": str(fields.get("reason") or ""),
                "index": len(loadout_groups),
                "rows": {},
            }
            loadout_groups.append(current_loadout_group)
            continue

        if " DUNGEON_CONTEXT " in raw_line:
            fields = _extract_fields(raw_line)
            set_dungeon_context(fields.get("dungeonId") or fields.get("dungeon_id"))
            continue

        if " BATTLE_RESULT " in raw_line:
            fields = _extract_fields(raw_line)
            set_dungeon_context(fields.get("dungeonId") or fields.get("dungeon_id"))
            if _coerce_int(fields.get("isPass"), default=0) == 1:
                challenge_pass_confirmed = True
                completion_source = str(fields.get("source") or "battle_result")
            continue

        if " CONTRACT_TAGS " in raw_line:
            fields = _extract_fields(raw_line)
            set_dungeon_context(fields.get("dungeonId") or fields.get("dungeon_id"))
            parsed_tag_ids = _parse_contract_tag_ids(fields.get("tagIds") or fields.get("tag_ids"))
            if parsed_tag_ids:
                contract_tag_ids = parsed_tag_ids
            if fields.get("score") is not None:
                contract_tag_score = _coerce_int(fields.get("score"), default=0)
            continue

        if " LOADOUT_STATS " in raw_line or "LOADOUT_STATS " in raw_line:
            stats_snapshot = _parse_loadout_stats_snapshot(raw_line)
            if stats_snapshot is not None:
                char_key = str(stats_snapshot["character_key"])
                loadout_by_char[char_key] = _merge_loadout_snapshot(
                    loadout_by_char.get(char_key, {"character_key": char_key}),
                    stats_snapshot,
                )
                if char_key in weapon_override_by_char:
                    loadout_by_char[char_key] = _loadout_with_weapon_state(
                        loadout_by_char[char_key],
                        weapon_override_by_char[char_key],
                    )
                if current_loadout_group is None or current_loadout_group.get("ts_ms") != ts_ms:
                    current_loadout_group = {
                        "ts_ms": ts_ms,
                        "reason": "",
                        "index": len(loadout_groups),
                        "rows": {},
                    }
                    loadout_groups.append(current_loadout_group)
                group_rows = current_loadout_group["rows"]
                group_rows[char_key] = _merge_loadout_snapshot(
                    group_rows.get(char_key, {"character_key": char_key}),
                    stats_snapshot,
                )
                if char_key in weapon_override_by_char:
                    group_rows[char_key] = _loadout_with_weapon_state(
                        group_rows[char_key],
                        weapon_override_by_char[char_key],
                    )
            continue

        if " LOADOUT slot=" in raw_line or "LOADOUT slot=" in raw_line:
            loadout_snapshot = _parse_loadout_slot_snapshot(raw_line)
            if loadout_snapshot is not None:
                char_key = str(loadout_snapshot["character_key"])
                loadout_by_char[char_key] = _merge_loadout_snapshot(
                    loadout_by_char.get(char_key, {}),
                    loadout_snapshot,
                )
                if char_key in weapon_override_by_char:
                    loadout_by_char[char_key] = _loadout_with_weapon_state(
                        loadout_by_char[char_key],
                        weapon_override_by_char[char_key],
                    )
                if current_loadout_group is None or current_loadout_group.get("ts_ms") != ts_ms:
                    current_loadout_group = {
                        "ts_ms": ts_ms,
                        "reason": "",
                        "index": len(loadout_groups),
                        "rows": {},
                    }
                    loadout_groups.append(current_loadout_group)
                group_rows = current_loadout_group["rows"]
                group_rows[char_key] = _merge_loadout_snapshot(
                    group_rows.get(char_key, {}),
                    loadout_snapshot,
                )
                if char_key in weapon_override_by_char:
                    group_rows[char_key] = _loadout_with_weapon_state(
                        group_rows[char_key],
                        weapon_override_by_char[char_key],
                    )
            loadout_match = _LOADOUT_SLOT_RE.search(raw_line)
            if loadout_match:
                char_key = loadout_match.group("char")
                active_weapons_by_char[char_key] = str(
                    loadout_by_char.get(char_key, {}).get("weapon_template")
                    or loadout_match.group("weapon")
                )
                active_suits_by_char[char_key] = _parse_loadout_suits(
                    loadout_match.group("equip_suit")
                )
            continue

        if _OFFICIAL_TIMER_START_RE.search(raw_line):
            fields = _extract_fields(raw_line)
            set_dungeon_context(fields.get("gameId") or fields.get("game_id"))
            official_timer_start_ms = ts_ms
            game_timer_start_ms = ts_ms
            timer_start_seen = True
            continue

        if _LIVE_TIMER_TICK_RE.search(raw_line):
            fields = _extract_fields(raw_line)
            elapsed_ms = _coerce_int(fields.get("elapsedMs"), default=0)
            if elapsed_ms > 0:
                game_timer_end_ms = ts_ms
                game_timer_elapsed_ms = elapsed_ms
                game_timer_window_elapsed_ms = elapsed_ms
            continue

        if _OFFICIAL_TIMER_END_RE.search(raw_line):
            fields = _extract_fields(raw_line)
            set_dungeon_context(fields.get("gameId") or fields.get("game_id"))
            official_timer_end_ms = ts_ms
            if _coerce_int(fields.get("isPass"), default=0) == 1:
                challenge_pass_confirmed = True
                official_pass_confirmed = True
                completion_source = "official_timer_end"
            pass_time_ms = _coerce_int(fields.get("passTime"), default=0)
            if pass_time_ms > 0:
                game_timer_end_ms = ts_ms
                game_timer_elapsed_ms = pass_time_ms
                game_timer_window_elapsed_ms = pass_time_ms
                official_timer_elapsed_ms = pass_time_ms
                timer_end_seen = True
            continue

        if _GAME_TIMER_START_RE.search(raw_line):
            fields = _extract_fields(raw_line)
            start_ms = _coerce_int(fields.get("startMs"), default=0)
            if official_timer_start_ms is None and _timer_is_authoritative(fields) and start_ms >= 0:
                game_timer_start_ms = ts_ms
                timer_start_seen = True
            continue

        if _GAME_TIMER_END_RE.search(raw_line):
            fields = _extract_fields(raw_line)
            timer_is_authoritative = _timer_is_authoritative(fields)
            if timer_is_authoritative and _coerce_int(fields.get("isPass"), default=0) == 1:
                challenge_pass_confirmed = True
                completion_source = str(fields.get("source") or "game_timer_end")
            elapsed_ms = _coerce_int(fields.get("elapsedMs"), default=0)
            wall_elapsed_ms = _coerce_int(fields.get("wallElapsedMs"), default=0)
            sane = _coerce_int(fields.get("sane"), default=1)
            if (
                official_timer_elapsed_ms is None
                and timer_is_authoritative
                and sane
                and elapsed_ms > 0
            ):
                game_timer_end_ms = ts_ms
                game_timer_elapsed_ms = wall_elapsed_ms if wall_elapsed_ms > 0 else elapsed_ms
                game_timer_window_elapsed_ms = game_timer_elapsed_ms
                timer_end_seen = True
            continue

        if " ATB_UPDATE " in raw_line:
            fields = _extract_fields(raw_line)
            if str(fields.get("reason") or "") == "AddValue" and _safe_positive_rate(fields.get("delta")) is not None:
                atb_char = _extract_character_key(fields.get("owner"), "")
                if atb_char:
                    atb_gain_ms_by_char[atb_char].append(ts_ms)
            continue

        if " SKILL_CAST_START " in raw_line:
            fields = _extract_fields(raw_line)
            cast_skill = str(fields.get("skill") or "")
            cast_character_key = _extract_character_key(fields.get("owner"), cast_skill)
            cast_record = {
                "ts_ms": ts_ms,
                "line_no": line_no,
                "skill": cast_skill,
                "owner": fields.get("owner"),
                "skill_inst_id": fields.get("inst"),
                "skill_source": fields.get("skillSource") or fields.get("skill_source"),
                "source_character_key": cast_character_key,
                "end_ts_ms": None,
            }
            skill_casts.append(cast_record)
            inst_key = str(cast_record.get("skill_inst_id") or "")
            if inst_key:
                active_skill_casts_by_inst[inst_key] = cast_record
            if cast_character_key:
                if first_party_action_ms is None and not _is_generic_runtime_skill_id(cast_skill):
                    first_party_action_ms = ts_ms
                rows = recent_skill_casts_by_char[cast_character_key]
                rows.append(
                    {
                        "ts_ms": ts_ms,
                        "skill": cast_skill,
                        "owner": fields.get("owner"),
                        "skill_inst_id": fields.get("inst"),
                        "skill_source": fields.get("skillSource") or fields.get("skill_source"),
                    }
                )
                del rows[:-16]
            continue

        if " SKILL_CAST_END " in raw_line:
            fields = _extract_fields(raw_line)
            inst_key = str(fields.get("inst") or "")
            cast_record = active_skill_casts_by_inst.pop(inst_key, None) if inst_key else None
            if cast_record is not None:
                cast_record["end_ts_ms"] = ts_ms
                cast_record["end_line_no"] = line_no
            continue

        if " CHAR_SKILLS " in raw_line:
            parsed_char_skills = _parse_char_skills_line(raw_line)
            if parsed_char_skills is not None:
                char_skill_levels[parsed_char_skills[0]] = parsed_char_skills[1]
            continue

        if " BB[" in raw_line:
            if pending_buff_record is not None:
                parsed_bb_fields = _extract_fields(raw_line)
                pending_buff_record["bb_keys"].extend(parsed_bb_fields.keys())
                for key, raw_value in parsed_bb_fields.items():
                    rate = _safe_positive_rate(raw_value)
                    if rate is not None:
                        pending_buff_record["bb_values"][key] = rate
                _apply_enemy_status_bb_overrides(
                    pending_buff_record,
                    context_enemy_hint=context_enemy_hint,
                )
                _preserve_raw_numeric_internal_trigger_buff_id(pending_buff_record)
            continue

        dpd_raw = _parse_dpd_raw_line(raw_line)
        if dpd_raw is not None:
            hit = hits_by_seq.get(int(dpd_raw["seq"]))
            if hit is not None:
                hit["dpd_raw"] = {key: value for key, value in dpd_raw.items() if key != "seq"}
            continue

        baseline = _parse_baseline_line(raw_line)
        if baseline is not None:
            seq, values = baseline
            hit = hits_by_seq.get(seq)
            if hit is not None:
                hit["baseline"] = values
                baseline_by_character[str(hit.get("character_key") or "")] = values
            continue

        packet_modifiers = _parse_packet_modifier_line(raw_line)
        if packet_modifiers is not None:
            seq, attacker_modifier_uids, defender_modifier_uids = packet_modifiers
            for uid in attacker_modifier_uids + defender_modifier_uids:
                if uid:
                    packet_modifier_last_seen_by_uid[str(uid)] = max(
                        packet_modifier_last_seen_by_uid.get(str(uid), ts_ms),
                        ts_ms,
                    )
            hit = hits_by_seq.get(seq)
            if hit is not None:
                hit["packet_modifier_seen"] = True
                hit["packet_modifier_uids"] = {
                    "attacker": attacker_modifier_uids,
                    "defender": defender_modifier_uids,
                }
            continue

        packet_attrs = _parse_packet_attr_line(raw_line)
        if packet_attrs is not None:
            seq, attacker_attr_rows, defender_attr_rows = packet_attrs
            hit = hits_by_seq.get(seq)
            if hit is not None:
                hit["packet_attr_details"] = {
                    "attacker": attacker_attr_rows,
                    "defender": defender_attr_rows,
                }
            continue

        poise_damage_event = _parse_poise_damage_event(raw_line, ts_ms, line_no)
        if poise_damage_event is not None:
            poise_damage_events.append(poise_damage_event)
            continue

        current_buff_record: dict[str, Any] | None = None

        if " ATTR_MOD " in raw_line or " DMG_MOD " in raw_line:
            fields = _extract_fields(raw_line)
            buff_key = _normalize_buff_id(fields.get("buff"))
            pending_attr_mods[buff_key].append(
                {
                    "attr_type": str(fields.get("attrType") or ""),
                    "bb_key": str(fields.get("bbKey") or ""),
                    "use_key": str(fields.get("useKey") or "0"),
                    "value": _safe_positive_rate(fields.get("val")),
                }
            )

        if " HP_V2 " in raw_line:
            fields = _extract_fields(raw_line)
            character_key = _extract_character_key(fields.get("src"), fields.get("atk"), fields.get("skill"))
            if character_key is None:
                continue
            target_enemy_key = _extract_enemy_key(fields.get("tgt"), fields.get("skill"))
            if target_enemy_key is None:
                target_enemy_key = _recover_enemy_target_from_mislabeled_actor(
                    fields,
                    context_enemy_hint=context_enemy_hint,
                    party_actor_ids=party_actor_ids,
                )
            if target_enemy_key is None:
                continue
            enemy_counter[target_enemy_key] += 1

            character_name = _resolve_character_name(character_key) or character_key
            raw_hit_value = _coerce_int(fields.get("hit"))
            packet_hit_value = raw_hit_value if fields.get("hit") is not None else None
            packet_raw_value = _coerce_optional_float(fields.get("raw"))
            packet_final_value = _coerce_optional_float(fields.get("packetFinalValue"))
            has_enemy_hp_after = "eHP" in fields
            enemy_hp_after = _coerce_int(fields.get("eHP"))
            hit_value = _cap_enemy_overkill_damage(
                raw_hit_value,
                enemy_hp_after=enemy_hp_after if has_enemy_hp_after else None,
                previous_enemy_hp=last_enemy_hp_by_target.get(target_enemy_key),
            )
            damage_value_source = "packet_hit"
            if packet_hit_value is None:
                damage_value_source = "missing_packet_hit"
            elif hit_value != raw_hit_value:
                damage_value_source = "packet_hit_overkill_capped"
            if has_enemy_hp_after:
                last_enemy_hp_by_target[target_enemy_key] = enemy_hp_after
            crit_flag = _coerce_int(fields.get("critFlag"))
            raw_skill_key = fields.get("skill") or "unknown_skill"
            original_template_int_id = _coerce_int(fields.get("origTemplateIntId"), default=0) or None
            skill_key = (
                _canonical_hit_skill_id_from_cast_context(
                    raw_skill_key,
                    character_key,
                    ts_ms,
                    original_template_int_id=original_template_int_id,
                    target_enemy_key=target_enemy_key,
                    recent_skill_casts_by_char=recent_skill_casts_by_char,
                    recent_numeric_buffs_by_source=recent_numeric_buffs_by_source,
                )
                or _canonical_hit_skill_id(raw_skill_key, character_key)
            )
            skill_name = _resolve_skill_name(skill_key) or skill_key
            hit_index = _coerce_int(fields.get("hits"), default=1)
            skill_profile = _resolve_skill_profile(skill_key)
            skill_group_type = None
            skill_family_key = _resolve_skill_family_key(skill_key, skill_profile)
            if skill_profile is not None:
                try:
                    skill_group_type = int(skill_profile.get("group_type"))
                except (TypeError, ValueError):
                    skill_group_type = None
            alias_combo_consume = _COMBO_CONSUME_SKILL_ALIASES.get(skill_key)
            if alias_combo_consume is not None:
                skill_group_type = int(alias_combo_consume["group_type"])
                skill_family_key = str(alias_combo_consume["family_skill_key"])

            seq_match = _HIT_SEQ_RE.search(raw_line)
            seq = int(seq_match.group(1)) if seq_match else len(hits) + 1
            action_id = _coerce_int(fields.get("actionId"), default=0) or None
            damage_unit_index = _coerce_int(fields.get("damageUnitIndex"), default=0)
            action_damage_element = _infer_skill_action_damage_element(
                skill_key,
                action_id,
                damage_unit_index,
            )
            damage_element = action_damage_element or _infer_skill_damage_element(skill_key, character_key)
            if action_damage_element:
                damage_school = _damage_school_from_element(action_damage_element) or _infer_skill_damage_school(
                    skill_key,
                    character_key,
                    raw_skill_key=raw_skill_key,
                )
            else:
                damage_school = _infer_skill_damage_school(
                    skill_key,
                    character_key,
                    raw_skill_key=raw_skill_key,
                ) or _damage_school_from_element(damage_element)
            hit = {
                "seq": seq,
                "line_no": line_no,
                "ts_ms": ts_ms,
                "character_key": character_key,
                "character_name": character_name,
                "target_enemy_key": target_enemy_key,
                "target_enemy_name": _resolve_enemy_name(target_enemy_key) or target_enemy_key,
                "raw_skill_key": raw_skill_key,
                "skill_key": skill_key,
                "skill_name": skill_name,
                "skill_level": _coerce_int(fields.get("skillLv"), default=0) or None,
                "template_int_id": _coerce_int(fields.get("templateIntId"), default=0) or None,
                "action_id": action_id,
                "damage_unit_index": damage_unit_index,
                "original_template_int_id": original_template_int_id,
                "dynamic_bb_signature": fields.get("dynBB"),
                "damage_element": damage_element,
                "damage_school": damage_school,
                "skill_group_type": skill_group_type,
                "skill_family_key": skill_family_key,
                "hit_value": hit_value,
                "raw_hit_value": raw_hit_value,
                "packet_hit_value": packet_hit_value,
                "packet_raw_value": packet_raw_value,
                "packet_final_value": packet_final_value,
                "damage_value_source": damage_value_source,
                "rdps_basis_value": hit_value,
                "rdps_basis_source": damage_value_source,
                "overkill_damage": max(0, raw_hit_value - hit_value),
                "enemy_hp_after": enemy_hp_after,
                "crit_flag": crit_flag,
                "hit_index": hit_index,
                "dpd_raw": None,
                "baseline": baseline_by_character.get(character_key),
                "packet_modifier_seen": False,
                "packet_modifier_uids": {"attacker": [], "defender": []},
                "packet_attr_details": {"attacker": [], "defender": []},
            }
            hits.append(hit)
            hits_by_seq[seq] = hit
            if loadout_by_char and character_key not in loadout_by_char:
                # A battle actor outside the frozen loadout proves that the
                # client carried an old bag team across an empty dungeon-team
                # packet. Stop using that loadout for subsequent inference.
                loadout_by_char.clear()
                active_suits_by_char.clear()
                active_weapons_by_char.clear()
            if character_key not in roster_seen:
                roster_seen.add(character_key)
                roster_order.append(character_key)

            participant = participant_totals[character_key]
            participant["character_key"] = character_key
            participant["character_name"] = character_name
            participant["total_damage"] += hit_value
            participant["max_hit"] = max(participant["max_hit"], hit_value)
            participant["crit_hits"] += 1 if crit_flag else 0
            participant["hit_count"] += 1

            skill_entry = skill_totals[(character_key, skill_key)]
            skill_entry["character_key"] = character_key
            skill_entry["character_name"] = character_name
            skill_entry["skill_key"] = skill_key
            skill_entry["skill_name"] = skill_name
            skill_entry["total_damage"] += hit_value
            skill_entry["max_damage"] = max(skill_entry["max_damage"], hit_value)
            skill_entry["hit_count"] += 1
            if hit_index == 1:
                skill_entry["cast_count"] += 1

        elif " BUFF_START " in raw_line:
            fields = _extract_fields(raw_line)
            owner_value = str(fields.get("owner") or "")
            owner_key = _extract_character_key(owner_value)
            target_enemy_key = _extract_enemy_key(fields.get("owner"))
            raw_buff_key = _normalize_buff_id(fields.get("id"))
            raw_source_key = _extract_character_key(fields.get("src"))
            source_key = raw_source_key
            mapping_hint = _packet_numeric_buff_hint(raw_buff_key)
            mapping_rejected = False
            if mapping_hint and not _packet_mapping_applies(
                mapping_hint,
                owner_key=owner_key,
                source_key=source_key,
                active_suits_by_char=active_suits_by_char,
                active_weapons_by_char=active_weapons_by_char,
            ):
                mapping_rejected = True
                mapping_hint = {}
            buff_key = _canonical_packet_buff_id(
                raw_buff_key,
                owner_key=owner_key,
                source_key=source_key,
                active_suits_by_char=active_suits_by_char,
                active_weapons_by_char=active_weapons_by_char,
            )
            if source_key is None:
                source_key = _extract_character_key(fields.get("src"), buff_key)
            if (
                source_key
                and raw_source_key is None
                and owner_key is None
                and target_enemy_key is not None
                and (
                    _extract_enemy_key(fields.get("src")) is not None
                    or (loadout_by_char and source_key not in loadout_by_char)
                )
            ):
                # Do not let enemy-owned debuffs promote an off-roster player
                # solely because the buff id text happens to contain a
                # character prefix. This was pulling e.g. `chr_0021_whiten`
                # into party rDPS even when src/owner were both enemy-side.
                source_key = None
            is_weapon_buff = bool(_WEAPON_BUFF_RE.match(buff_key))
            chr_key_from_buff = _extract_character_key(buff_key)
            if chr_key_from_buff and owner_value:
                last_chr_src_on_owner[owner_value] = (chr_key_from_buff, ts_ms)
            if owner_key and is_weapon_buff and (raw_source_key is None or raw_source_key == owner_key):
                source_key = owner_key
            elif (
                owner_key
                and (source_key is None or source_key == owner_key)
                and any(buff_key.startswith(prefix) for prefix in _GENERIC_BUFF_PREFIXES)
            ):
                borrowed = last_chr_src_on_owner.get(owner_value)
                if borrowed is not None and ts_ms - borrowed[1] <= _CHR_BORROW_WINDOW_MS:
                    source_key = borrowed[0]
            if (
                owner_key
                and source_key
                and source_key != owner_key
                and loadout_by_char
                and owner_key in loadout_by_char
                and source_key not in loadout_by_char
                and any(buff_key.startswith(prefix) for prefix in _PLAYER_TARGET_GENERIC_BUFF_PREFIXES)
            ):
                source_key = owner_key
            player_keys = [key for key in (source_key, owner_key) if key]
            if not player_keys:
                pending_buff_record = None
                continue
            for player_key in player_keys:
                if player_key not in roster_seen:
                    roster_seen.add(player_key)
                    roster_order.append(player_key)
            if source_key:
                source_participant = participant_totals[source_key]
                source_participant["character_key"] = source_key
                source_participant["character_name"] = _resolve_character_name(source_key) or source_key
            if owner_key:
                owner_participant = participant_totals[owner_key]
                owner_participant["character_key"] = owner_key
                owner_participant["character_name"] = _resolve_character_name(owner_key) or owner_key
            attr_mods = pending_attr_mods.pop(buff_key, [])
            if not attr_mods and raw_buff_key != buff_key:
                attr_mods = pending_attr_mods.pop(raw_buff_key, [])
            source_skill_context = _recent_source_skill_context_for_buff(
                source_key,
                ts_ms,
                recent_skill_casts_by_char,
            ) or {}
            buff_record = {
                "uid": str(fields.get("uid") or ""),
                "line_no": line_no,
                "ts_ms": ts_ms,
                "source_character_key": source_key,
                "source_character_name": _resolve_character_name(source_key) or source_key,
                "source_skill_key": source_skill_context.get("source_skill_key"),
                "source_skill_family_key": source_skill_context.get("source_skill_family_key"),
                "raw_source_character_key": raw_source_key,
                "raw_source_character_name": _resolve_character_name(raw_source_key) or raw_source_key,
                "raw_source": fields.get("src"),
                "target_character_key": owner_key,
                "target_character_name": _resolve_character_name(owner_key) or owner_key,
                "target_enemy_key": target_enemy_key,
                "target_enemy_name": _resolve_enemy_name(target_enemy_key) or target_enemy_key,
                "owner_raw": owner_value,
                "event_key": buff_key,
                "raw_event_key": raw_buff_key,
                "packet_mapping": mapping_hint if mapping_hint else None,
                "packet_mapping_rejected": mapping_rejected,
                "raw_duration_ms": _duration_ms_from_seconds(fields.get("dur")),
                "end_ts_ms": None,
                "bb_keys": [row["bb_key"] for row in attr_mods if row["bb_key"]],
                "bb_values": {},
                "attr_types": [row["attr_type"] for row in attr_mods if row["attr_type"]],
                "attr_mods": attr_mods,
                "is_weapon_buff": is_weapon_buff,
            }
            uid_key = str(buff_record.get("uid") or "")
            replaced_existing = False
            if uid_key:
                existing = active_buff_starts_by_uid.get(uid_key)
                if existing is not None and int(existing.get("ts_ms") or -1) == ts_ms:
                    index_key = (uid_key, ts_ms)
                    if _prefer_packet_buff_record(existing, buff_record):
                        replace_index = buff_start_index_by_uid_ts.get(index_key)
                        if replace_index is not None:
                            buff_starts[replace_index] = buff_record
                        active_buff_starts_by_uid[uid_key] = buff_record
                    current_buff_record = active_buff_starts_by_uid.get(uid_key)
                    replaced_existing = True
            if not replaced_existing:
                buff_starts.append(buff_record)
                if raw_buff_key.isdigit() and source_key:
                    rows = recent_numeric_buffs_by_source[str(source_key)]
                    rows.append(buff_record)
                    del rows[:-128]
                if uid_key:
                    active_buff_starts_by_uid[uid_key] = buff_record
                    buff_start_index_by_uid_ts[(uid_key, ts_ms)] = len(buff_starts) - 1
                current_buff_record = buff_record

        elif " BUFF_END " in raw_line:
            fields = _extract_fields(raw_line)
            uid = str(fields.get("uid") or "")
            if uid:
                buff_record = active_buff_starts_by_uid.pop(uid, None)
                if buff_record is not None:
                    buff_record["end_ts_ms"] = ts_ms
                    current_buff_record = buff_record

        pending_buff_record = current_buff_record

    loadout_by_char = _repair_weapon_puton_loadout_groups(loadout_groups, loadout_by_char)
    _apply_poise_damage_events_to_hits(hits, poise_damage_events)

    if not hits and (loadout_by_char or dungeon_context_id):
        anchor_ms = (
            first_party_action_ms
            if first_party_action_ms is not None
            else game_timer_start_ms
            if game_timer_start_ms is not None
            else official_timer_start_ms
            if official_timer_start_ms is not None
            else first_context_ms
            if first_context_ms is not None
            else 0
        )
        battle_loadout_by_char = _select_loadout_snapshot_for_battle(
            loadout_groups,
            loadout_by_char,
            anchor_ms=anchor_ms,
        )
        loadout = sorted(
            battle_loadout_by_char.values(),
            key=lambda item: (int(item.get("slot") or 0), str(item.get("character_key") or "")),
        )
        roster = [
            {
                "slot": int(row.get("slot") or index),
                "character_key": str(row.get("character_key") or ""),
                "character_name": str(row.get("character_name") or row.get("character_key") or ""),
            }
            for index, row in enumerate(loadout, start=1)
            if row.get("character_key")
        ]
        end_ms = last_context_ms if last_context_ms is not None else anchor_ms
        dungeon_key, dungeon_name = dungeon_context or (UNKNOWN_DUNGEON_KEY, UNKNOWN_DUNGEON_NAME)
        time_source = "party_action_window" if first_party_action_ms is not None else "battle_ready"
        fingerprint_payload = {
            "rules_version": RULES_VERSION,
            "time_source": time_source,
            "loadout": [row["character_key"] for row in roster],
            "anchor_ms": anchor_ms,
        }
        return {
            "battle": {
                "dungeon_key": dungeon_key,
                "dungeon_name": dungeon_name,
                "boss_key": "unknown_boss",
                "boss_name": "未知对象",
                "boss_identity_source": "missing_damage_target",
                "dungeon_context_id": dungeon_context_id,
                "dungeon_identity_source": (
                    "dungeon_context"
                    if dungeon_context is not None
                    else "unmapped_dungeon_context"
                    if dungeon_context_id
                    else "missing_dungeon_context"
                ),
                "battle_start_at": _build_iso_datetime(reference_date, anchor_ms),
                "battle_end_at": _build_iso_datetime(reference_date, end_ms),
                "duration_ms": 0,
                "time_source": time_source,
                "timeline_zero_source": time_source,
                "timer_start_seen": timer_start_seen,
                "timer_end_seen": timer_end_seen,
                "official_timer_start_seen": official_timer_start_ms is not None,
                "official_timer_end_seen": official_timer_end_ms is not None,
                "timer_start_inferred": False,
                "clear_flag": False,
                "total_damage": 0,
                "total_dps": 0.0,
                "roster": roster,
                "battle_fingerprint": build_canonical_sha256(fingerprint_payload),
                "parser_version": PARSER_VERSION,
                "rules_version": RULES_VERSION,
                "source_file_name": file_name,
            },
            "participants": [],
            "loadout": loadout,
            "buff_events": [],
            "timeline_events": [],
            "role_skill_stats": [],
            "debug_hits": [],
            "casts": [],
            "char_skills": {},
        }

    if not hits:
        raise ValueError("未在日志中解析到任何 HP_V2 伤害事件。")

    _extend_buff_records_from_packet_modifiers(buff_starts, packet_modifier_last_seen_by_uid)
    _infer_related_buff_end_times(buff_starts, skill_casts)
    _apply_same_frame_trigger_skill_mappings(hits, buff_starts)
    _resolve_weapon_buff_sources(buff_starts)
    for buff_record in buff_starts:
        source_key = buff_record.get("source_character_key")
        if not source_key:
            continue
        if source_key not in roster_seen:
            roster_seen.add(source_key)
            roster_order.append(source_key)
        source_participant = participant_totals[source_key]
        source_participant["character_key"] = source_key
        source_participant["character_name"] = _resolve_character_name(source_key) or source_key

    known_enemy_keys = {
        enemy_key
        for enemy_key in enemy_counter
        if enemy_key and enemy_key != UNKNOWN_ENEMY_KEY
    }
    should_retarget_unknown = (
        bool(context_enemy_hint)
        and UNKNOWN_ENEMY_KEY in enemy_counter
        and (not known_enemy_keys or known_enemy_keys == {context_enemy_hint})
    )
    identity_retargeted = bool(
        should_retarget_unknown
        and _retarget_unknown_enemy_hits(hits, buff_starts, context_enemy_hint)
    )
    if identity_retargeted:
        (
            participant_totals,
            skill_totals,
            roster_order,
            roster_seen,
            enemy_counter,
        ) = _rebuild_hit_totals(hits, buff_starts)

    initial_boss_key = enemy_counter.most_common(1)[0][0] if enemy_counter else "unknown_boss"
    first_party_hit_ms = next(
        (
            int(hit["ts_ms"])
            for hit in hits
            if str(hit.get("character_key") or "").startswith("chr_")
            and str(hit.get("target_enemy_key") or "").startswith("eny_")
        ),
        None,
    )
    first_party_boss_hit_ms = next(
        (
            int(hit["ts_ms"])
            for hit in hits
            if str(hit.get("character_key") or "").startswith("chr_")
            and str(hit.get("target_enemy_key") or "") == initial_boss_key
        ),
        None,
    )

    def _fallback_hit_window() -> tuple[int, int, str]:
        if first_hit_hint_ms is not None:
            return (
                first_hit_hint_ms,
                last_hit_hint_ms if last_hit_hint_ms is not None else hits[-1]["ts_ms"],
                "hit_hint_window",
            )
        if first_party_action_ms is not None:
            return first_party_action_ms, last_hit_hint_ms if last_hit_hint_ms is not None else hits[-1]["ts_ms"], "party_action_window"
        if first_party_boss_hit_ms is not None:
            return first_party_boss_hit_ms, last_hit_hint_ms if last_hit_hint_ms is not None else hits[-1]["ts_ms"], "party_boss_hit_window"
        if first_party_hit_ms is not None:
            return first_party_hit_ms, last_hit_hint_ms if last_hit_hint_ms is not None else hits[-1]["ts_ms"], "party_hit_window"
        return (
            first_hit_hint_ms if first_hit_hint_ms is not None else hits[0]["ts_ms"],
            last_hit_hint_ms if last_hit_hint_ms is not None else hits[-1]["ts_ms"],
            "hit_window",
        )

    time_source = "game_timer"
    timeline_zero_source = "game_timer"
    if game_timer_elapsed_ms is not None:
        timer_window_elapsed_ms = game_timer_window_elapsed_ms or game_timer_elapsed_ms
        if (
            official_timer_elapsed_ms is not None
            and game_timer_start_ms is not None
            and game_timer_end_ms is not None
            and game_timer_end_ms >= game_timer_start_ms
        ):
            first_hit_ms = game_timer_start_ms
            last_hit_ms = game_timer_end_ms
            timeline_zero_source = (
                "official_timer_start"
                if official_timer_start_ms is not None and official_timer_start_ms == game_timer_start_ms
                else "game_timer_start"
            )
        elif game_timer_start_ms is not None:
            first_hit_ms = game_timer_start_ms
            last_hit_ms = first_hit_ms + timer_window_elapsed_ms
            timeline_zero_source = (
                "official_timer_start"
                if official_timer_start_ms is not None and official_timer_start_ms == game_timer_start_ms
                else "game_timer_start"
            )
        elif game_timer_end_ms is not None:
            last_hit_ms = game_timer_end_ms
            first_hit_ms = last_hit_ms - timer_window_elapsed_ms
            timeline_zero_source = "timer_end_inferred"
        else:
            first_hit_ms = first_hit_hint_ms if first_hit_hint_ms is not None else hits[0]["ts_ms"]
            last_hit_ms = first_hit_ms + timer_window_elapsed_ms
            timeline_zero_source = "timer_elapsed_first_hit_inferred"
    elif game_timer_start_ms is not None:
        _, fallback_last_hit_ms, _ = _fallback_hit_window()
        first_hit_ms = game_timer_start_ms
        last_hit_ms = max(fallback_last_hit_ms, hits[-1]["ts_ms"])
        timeline_zero_source = (
            "official_timer_start"
            if official_timer_start_ms is not None and official_timer_start_ms == game_timer_start_ms
            else "game_timer_start"
        )
    else:
        first_hit_ms, last_hit_ms, time_source = _fallback_hit_window()
        timeline_zero_source = time_source
    if last_hit_ms < first_hit_ms:
        last_hit_ms += 24 * 60 * 60 * 1000

    has_game_timer_window = game_timer_start_ms is not None or game_timer_elapsed_ms is not None
    if has_game_timer_window:
        windowed_hits = [hit for hit in hits if first_hit_ms <= int(hit["ts_ms"]) <= last_hit_ms]
        if windowed_hits:
            buff_starts = _filter_buff_starts_for_timer_window(
                buff_starts,
                battle_start_ms=first_hit_ms,
            )
            hits = windowed_hits
            (
                participant_totals,
                skill_totals,
                roster_order,
                roster_seen,
                enemy_counter,
            ) = _rebuild_hit_totals(hits, buff_starts)
        else:
            timer_window_valid = False
            game_timer_start_ms = None
            game_timer_end_ms = None
            game_timer_elapsed_ms = None
            game_timer_window_elapsed_ms = None
            has_game_timer_window = False
            first_hit_ms, last_hit_ms, time_source = _fallback_hit_window()
            time_source = "invalid_timer_window"
            timeline_zero_source = "invalid_timer_window"
            if last_hit_ms < first_hit_ms:
                last_hit_ms += 24 * 60 * 60 * 1000
            if time_source in {"party_boss_hit_window", "party_hit_window"}:
                buff_starts = _filter_buff_starts_for_timer_window(
                    buff_starts,
                    battle_start_ms=first_hit_ms,
                )
                windowed_hits = [hit for hit in hits if int(hit["ts_ms"]) >= first_hit_ms]
                if windowed_hits:
                    hits = windowed_hits
                    (
                        participant_totals,
                        skill_totals,
                        roster_order,
                        roster_seen,
                        enemy_counter,
                    ) = _rebuild_hit_totals(hits, buff_starts)
    elif time_source in {"party_boss_hit_window", "party_hit_window"}:
        buff_starts = _filter_buff_starts_for_timer_window(
            buff_starts,
            battle_start_ms=first_hit_ms,
        )
        windowed_hits = [hit for hit in hits if int(hit["ts_ms"]) >= first_hit_ms]
        if windowed_hits:
            hits = windowed_hits
            (
                participant_totals,
                skill_totals,
                roster_order,
                roster_seen,
                enemy_counter,
            ) = _rebuild_hit_totals(hits, buff_starts)

    boss_key = enemy_counter.most_common(1)[0][0] if enemy_counter else "unknown_boss"
    boss_name = _resolve_enemy_name(boss_key) or boss_key
    dungeon_key, dungeon_name = dungeon_context or (UNKNOWN_DUNGEON_KEY, UNKNOWN_DUNGEON_NAME)
    if dungeon_key.startswith("indie_battletower"):
        # War Echo records are leaderboard data. Only the server's official
        # challenge-complete message may mark them cleared; HP zero, scene
        # exits and late dungeon status are retained as diagnostics only.
        clear_flag = official_pass_confirmed
    else:
        clear_flag = challenge_pass_confirmed or any(
            hit["target_enemy_key"] == boss_key and hit.get("enemy_hp_after", 1) <= 0
            for hit in hits
        )
    if not timer_window_valid:
        clear_flag = False
    duration_ms = max(
        game_timer_elapsed_ms if game_timer_elapsed_ms is not None else last_hit_ms - first_hit_ms,
        1,
    )
    wall_window_ms = max(last_hit_ms - first_hit_ms, 1)
    timeline_scale = duration_ms / wall_window_ms if has_game_timer_window else 1.0
    timer_start_inferred = timeline_zero_source in {
        "timer_end_inferred",
        "timer_elapsed_first_hit_inferred",
    }

    def battle_offset_ms(ts_ms: int) -> int:
        return max(int(round((int(ts_ms) - first_hit_ms) * timeline_scale)), 0)

    def battle_offset_ms_unclamped(ts_ms: int) -> int:
        return int(round((int(ts_ms) - first_hit_ms) * timeline_scale))

    total_damage = sum(hit["hit_value"] for hit in hits)
    total_dps = round(total_damage / (duration_ms / 1000), 2)
    battle_loadout_by_char = _select_loadout_snapshot_for_battle(
        loadout_groups,
        loadout_by_char,
        anchor_ms=int(hits[0]["ts_ms"]) if hits else first_hit_ms,
    )
    observed_damage_characters = {
        str(hit.get("character_key") or "")
        for hit in hits
        if str(hit.get("character_key") or "").startswith("chr_")
    }
    selected_loadout_characters = set(battle_loadout_by_char)
    loadout_stale = bool(
        selected_loadout_characters
        and observed_damage_characters - selected_loadout_characters
    )
    if loadout_stale:
        battle_loadout_by_char = {}
        active_suits_by_char.clear()
    active_weapons_by_char = {
        str(character_key): str(row.get("weapon_template") or "")
        for character_key, row in battle_loadout_by_char.items()
        if isinstance(row, dict) and row.get("weapon_template")
    }
    for loadout_row in battle_loadout_by_char.values():
        if isinstance(loadout_row, dict):
            loadout_row["static_multiplier_entries"] = _derive_static_self_multiplier_entries(loadout_row)
            loadout_row["static_arts_strength_entries"] = _derive_static_arts_strength_entries(loadout_row)
    static_entries_by_char = {
        str(character_key): list(row.get("static_multiplier_entries") or [])
        for character_key, row in battle_loadout_by_char.items()
        if isinstance(row, dict)
    }
    static_arts_strength_entries_by_char = {
        str(character_key): list(row.get("static_arts_strength_entries") or [])
        for character_key, row in battle_loadout_by_char.items()
        if isinstance(row, dict)
    }
    static_arts_strength_by_char = {
        character_key: sum(float(entry.get("rate") or 0.0) for entry in entries)
        for character_key, entries in static_arts_strength_entries_by_char.items()
    }
    for hit in hits:
        character_key = str(hit.get("character_key") or "")
        hit["static_multiplier_entries"] = static_entries_by_char.get(character_key, [])
        hit["static_arts_strength_entries"] = static_arts_strength_entries_by_char.get(character_key, [])
        if not hit.get("damage_element"):
            hit["damage_element"] = _damage_element_from_dpd_raw(hit.get("dpd_raw"))
    _annotate_hit_enemy_hp_state(hits)

    roster = []

    buff_windows = []
    for buff_record in buff_starts:
        labels = _collect_buff_labels(buff_record)
        zone_effects = _collect_zone_effects(buff_record)
        dynamic_effects = _extract_dynamic_effect_specs(buff_record)
        if not zone_effects and not dynamic_effects:
            continue
        if not _equip_buff_matches_active_suits(
            buff_record.get("event_key"),
            buff_record.get("source_character_key"),
            active_suits_by_char,
        ):
            continue
        if not _weapon_buff_matches_active_weapon(
            buff_record.get("event_key"),
            buff_record.get("source_character_key"),
            active_weapons_by_char,
        ):
            continue
        start_ts_ms = buff_record["ts_ms"]
        buff_duration_ms = _normalize_buff_duration_ms(
            start_ts_ms,
            event_key=buff_record.get("event_key"),
            end_ts_ms=buff_record.get("end_ts_ms"),
            raw_duration_ms=buff_record.get("raw_duration_ms"),
            battle_end_ms=last_hit_ms,
        )
        buff_windows.append(
            {
                "start_ts_ms": start_ts_ms,
                "start_line_no": buff_record.get("line_no"),
                "end_ts_ms": start_ts_ms + buff_duration_ms,
                "duration_ms": buff_duration_ms,
                "uid": buff_record.get("uid"),
                "uid_aliases": [],
                "source_character_key": buff_record["source_character_key"],
                "source_character_name": buff_record["source_character_name"],
                "source_static_arts_strength": static_arts_strength_by_char.get(
                    str(buff_record.get("source_character_key") or ""),
                    0.0,
                ),
                "source_skill_key": buff_record.get("source_skill_key"),
                "source_skill_family_key": buff_record.get("source_skill_family_key"),
                "raw_source_character_key": buff_record.get("raw_source_character_key"),
                "raw_source_character_name": buff_record.get("raw_source_character_name"),
                "raw_source": buff_record.get("raw_source"),
                "target_character_key": buff_record["target_character_key"] or buff_record["target_enemy_key"],
                "target_character_name": buff_record["target_character_name"] or buff_record["target_enemy_name"],
                "target_player_key": buff_record["target_character_key"],
                "target_enemy_key": buff_record["target_enemy_key"],
                "owner_raw": buff_record.get("owner_raw"),
                "event_key": buff_record["event_key"],
                "event_name": " / ".join(labels) if labels else buff_record["event_key"],
                "zone_effects": zone_effects,
                "dynamic_effects": dynamic_effects,
                "modifier_count": len(buff_record.get("attr_mods") or []),
                "skill_family_key": None,
                "stack_limit": _packet_mapping_stack_limit(buff_record) or _buff_stack_limit(buff_record["event_key"]),
            }
        )
    buff_windows = _dedupe_mirrored_buff_windows(_merge_buff_windows(buff_windows))
    buff_windows.extend(_build_special_combo_windows(hits, buff_starts, battle_end_ms=last_hit_ms))
    buff_windows = _dedupe_mirrored_buff_windows(_merge_buff_windows(buff_windows))
    buff_windows = _apply_buff_stack_limits(buff_windows)
    _infer_missing_hit_damage_schools(hits, buff_windows)
    rdps_preflight = _build_rdps_preflight(
        buff_starts,
        buff_windows,
        battle_start_ms=first_hit_ms,
        battle_end_ms=last_hit_ms,
        active_character_keys=set(battle_loadout_by_char),
    )
    buff_events = _build_buff_events(
        buff_starts,
        buff_windows,
        battle_start_ms=first_hit_ms,
        battle_end_ms=last_hit_ms,
    )
    rdps_damage = _compute_rdps_damage_shares(hits, buff_windows, condition_buff_records=buff_starts)
    rdps_damage_basis = _build_rdps_damage_basis(hits, rdps_damage, int(total_damage))
    rdps_damage_basis["rdps_preflight_ok"] = bool(rdps_preflight.get("ok"))
    rdps_damage_basis["rdps_strict_ok"] = bool(rdps_preflight.get("ok")) and bool(rdps_damage_basis.get("rdps_conservation_ok"))
    rdps_damage_basis["preflight_blocker_count"] = int(rdps_preflight.get("blocker_count") or 0)
    _assign_skill_timeline_group_keys(hits)

    participants = []
    for character_key in roster_order:
        participant = participant_totals.get(character_key)
        if participant is None or not participant["character_name"]:
            continue
        if battle_loadout_by_char and character_key not in battle_loadout_by_char and participant["total_damage"] <= 0:
            continue
        total_rd = rdps_damage.get(character_key, float(participant["total_damage"]))
        if participant["total_damage"] <= 0 and total_rd <= 0:
            continue
        dps = round(participant["total_damage"] / (duration_ms / 1000), 2)
        rdps = round(total_rd / (duration_ms / 1000), 2)
        hit_count = participant["hit_count"]
        participants.append(
            {
                "character_key": character_key,
                "character_name": participant["character_name"],
                "total_damage": participant["total_damage"],
                "total_rd": total_rd,
                "dps": dps,
                "rdps": rdps,
                "max_hit": participant["max_hit"] or None,
                "hit_count": hit_count or None,
                "crit_hits": participant["crit_hits"] or None,
                "crit_rate": round(participant["crit_hits"] / hit_count, 4) if hit_count else None,
            }
        )
    participants.sort(key=lambda item: (-item["dps"], -item["rdps"], item["character_name"]))
    roster = [
        {
            "slot": index,
            "character_key": participant["character_key"],
            "character_name": participant["character_name"],
        }
        for index, participant in enumerate(participants, start=1)
    ]

    cast_start_index = _build_cast_start_index(skill_casts)

    timeline_events = []
    for hit in hits:
        matching_cast = _matching_cast_for_hit(hit, cast_start_index)
        actual_start_ms = int(matching_cast["ts_ms"]) if matching_cast is not None else None
        actual_end_ms = (
            int(matching_cast["end_ts_ms"])
            if matching_cast is not None and matching_cast.get("end_ts_ms") is not None
            else None
        )
        timeline_events.append(
            {
                "ts_ms_from_start": battle_offset_ms(hit["ts_ms"]),
                "lane_type": "skill",
                "source_character_key": hit["character_key"],
                "source_character_name": hit["character_name"],
                "target_character_key": hit["target_enemy_key"],
                "target_character_name": hit["target_enemy_name"],
                "event_type": "damage",
                "event_key": hit.get("skill_family_key") or hit["skill_key"],
                "event_group_key": hit.get("timeline_group_key"),
                "event_name": hit["skill_name"],
                "value": hit["hit_value"],
                "damage_element": hit.get("damage_element"),
                "damage_school": hit.get("damage_school"),
                "value_source": hit.get("damage_value_source"),
                "packet_hit_value": hit.get("packet_hit_value"),
                "packet_raw_value": hit.get("packet_raw_value"),
                "packet_final_value": hit.get("packet_final_value"),
                "overkill_damage": hit.get("overkill_damage"),
                "rdps_basis_value": hit.get("rdps_basis_value"),
                "rdps_basis_source": hit.get("rdps_basis_source"),
                "rdps_contributions": [
                    {
                        "character_key": character_key,
                        "character_name": _resolve_character_name(character_key) or character_key,
                        "value": round(value, 4),
                    }
                    for character_key, value in sorted((hit.get("rdps_contributions") or {}).items())
                ],
                "packet_modifier_uids": hit.get("packet_modifier_uids") or {"attacker": [], "defender": []},
                "packet_attr_details": hit.get("packet_attr_details") or {"attacker": [], "defender": []},
                "poise_damage": hit.get("poise_damage"),
                "duration_ms": None,
                "actual_start_ms_from_start": (
                    battle_offset_ms_unclamped(actual_start_ms) if actual_start_ms is not None else None
                ),
                "actual_end_ms_from_start": (
                    battle_offset_ms_unclamped(actual_end_ms) if actual_end_ms is not None else None
                ),
                "actual_duration_ms": (
                    max(actual_end_ms - actual_start_ms, 1)
                    if actual_start_ms is not None and actual_end_ms is not None
                    else None
                ),
                "important": True,
            }
        )

    # 零伤害施放补录（例如辅助干员的终结技）：这些施放没有任何伤害命中，
    # 时间轴上会完全缺失。仅当施放技能名可解析为真实模板（非运行时兜底 id）、
    # 属于战技/连携/终结技形态、且该角色同技能在本场没有伤害命中时补一个 cast 事件；
    # 解析不出真名的老日志自动不生效，不会产生歧义数据。
    damaging_skill_keys = {
        (hit["character_key"], str(key))
        for hit in hits
        for key in (hit.get("skill_family_key"), hit.get("skill_key"))
        if key
    }
    participant_keys = {participant["character_key"] for participant in participants}
    last_cast_emit_ms: dict[tuple[str, str], int] = {}
    for cast in sorted(skill_casts, key=lambda item: int(item["ts_ms"])):
        cast_skill = str(cast.get("skill") or "")
        cast_character_key = cast.get("source_character_key")
        if not cast_character_key or cast_character_key not in participant_keys or not cast_skill:
            continue
        if _is_generic_runtime_skill_id(cast_skill) or re.fullmatch(r".*_skill_\d+", cast_skill):
            # 运行时兜底 id（chr_xxx_skill_100901）：尝试 num 表反解析成真实技能，失败则放弃。
            canonical_skill = _canonical_num_table_skill_id(cast_skill, cast_character_key)
            if not canonical_skill:
                continue
            cast_skill = canonical_skill
        # 归一到技能族：施放会连带范围/位移/派生等子实体（xxx_ultimate_skill_abilityrange），
        # 统一收敛为族名后再判定，避免子实体刷屏、也保证与伤害命中的 family key 对得上。
        family_match = re.match(r"^(.*?_(?:ultimate_skill|normal_skill|combo_skill))", cast_skill)
        if not family_match:
            continue
        cast_skill = family_match.group(1)
        if (cast_character_key, cast_skill) in damaging_skill_keys:
            continue
        cast_ts_ms = int(cast["ts_ms"])
        if cast_ts_ms < first_hit_ms or cast_ts_ms > last_hit_ms:
            continue
        emit_key = (str(cast_character_key), cast_skill)
        last_emit_ms = last_cast_emit_ms.get(emit_key)
        if last_emit_ms is not None and cast_ts_ms - last_emit_ms < 3000:
            continue
        last_cast_emit_ms[emit_key] = cast_ts_ms
        timeline_events.append(
            {
                "ts_ms_from_start": battle_offset_ms(cast_ts_ms),
                "lane_type": "skill",
                "source_character_key": cast_character_key,
                "source_character_name": _resolve_character_name(cast_character_key) or cast_character_key,
                "target_character_key": None,
                "target_character_name": None,
                "event_type": "cast",
                "event_key": cast_skill,
                "event_group_key": None,
                "event_name": _resolve_skill_name(cast_skill) or cast_skill,
                "value": None,
                "damage_element": None,
                "damage_school": None,
                "value_source": None,
                "packet_hit_value": None,
                "packet_raw_value": None,
                "packet_final_value": None,
                "overkill_damage": None,
                "rdps_basis_value": None,
                "rdps_basis_source": None,
                "rdps_contributions": [],
                "packet_modifier_uids": {"attacker": [], "defender": []},
                "packet_attr_details": {"attacker": [], "defender": []},
                "poise_damage": None,
                "duration_ms": None,
                "important": True,
            }
        )

    # 完整施法序列（v33，排轴导出 API 专用通道，不进 timeline_events 不影响展示）：
    # 参与者的每一次 SKILL_CAST_START 原样保留分段（attack1~5/重击/战技/终结…），
    # 运行时 id 经 num 表解析、失败自弃；子实体派生施放（projhit/abilityrange 等）
    # 不是玩家操作，过滤掉。窗口放宽到战斗零点前 10s（开怪第一个施放先于首刀落地）。
    casts_export: list[dict[str, Any]] = []
    _CAST_EXPORT_NOISE_RE = re.compile(
        r"(_projhit|_abilityrange|_abilityentity|_absorb|_indicator|_blocked|_listener|_aura|_marker)"
    )
    # 技力归属（v34+）：一次技力增加(ATB_UPDATE AddValue)归属到它「之前最近」的同角色施放
    # = 真正触发回技力的那一次(主控重击=连招末段)。若用前向窗口从每个施放往后看，连招
    # 前几段(A1~A4)会把末段(A5)的回技力抢标。先收集(施放起点ms, casts_export下标)，全部
    # 建完后按「gain 归最近前驱 cast」一次性回填 recovers_energy。
    _ATB_RECOVER_WINDOW_MS = 1500
    cast_starts_by_char: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for cast in sorted(skill_casts, key=lambda item: int(item["ts_ms"])):
        cast_skill = str(cast.get("skill") or "")
        cast_character_key = cast.get("source_character_key")
        if not cast_character_key or cast_character_key not in participant_keys or not cast_skill:
            continue
        if _is_generic_runtime_skill_id(cast_skill) or re.fullmatch(r".*_skill_\d+", cast_skill):
            canonical_skill = _canonical_num_table_skill_id(cast_skill, cast_character_key)
            if not canonical_skill:
                continue
            cast_skill = canonical_skill
        if _CAST_EXPORT_NOISE_RE.search(cast_skill):
            continue
        cast_ts_ms = int(cast["ts_ms"])
        if cast_ts_ms < first_hit_ms - 10_000 or cast_ts_ms > last_hit_ms:
            continue
        cast_end_ts_ms = cast.get("end_ts_ms")
        casts_export.append(
            {
                "ts_ms_from_start": battle_offset_ms_unclamped(cast_ts_ms),
                "end_ms_from_start": (
                    battle_offset_ms_unclamped(int(cast_end_ts_ms)) if cast_end_ts_ms is not None else None
                ),
                "character_key": cast_character_key,
                "skill_key": cast_skill,
                "skill_name": _resolve_skill_name(cast_skill) or cast_skill,
                "skill_source": str(cast.get("skill_source") or "") or None,
                # 技力增加归属回填（下方），默认 False；老客户端无 ATB_UPDATE 恒 False。
                "recovers_energy": False,
            }
        )
        cast_starts_by_char[cast_character_key].append((cast_ts_ms, len(casts_export) - 1))

    # 回填：每次技力增加 → 归属到 (gain-窗口, gain] 内最近的前驱同角色施放。
    for atb_char, gains in atb_gain_ms_by_char.items():
        starts = cast_starts_by_char.get(atb_char)
        if not starts:
            continue
        start_ms_list = [s for s, _ in starts]
        for gain_ms in gains:
            pos = bisect.bisect_right(start_ms_list, gain_ms) - 1
            if pos < 0:
                continue
            cast_start_ms, cast_idx = starts[pos]
            if 0 <= gain_ms - cast_start_ms <= _ATB_RECOVER_WINDOW_MS:
                casts_export[cast_idx]["recovers_energy"] = True

    for event in buff_windows:
        actual_start_ms = int(event["start_ts_ms"])
        actual_end_ms = int(event["end_ts_ms"])
        visible_start_ms = max(int(event["start_ts_ms"]), first_hit_ms)
        visible_end_ms = min(int(event["end_ts_ms"]), last_hit_ms)
        if visible_end_ms < visible_start_ms:
            continue
        visible_duration_ms = max(
            battle_offset_ms_unclamped(visible_end_ms) - battle_offset_ms_unclamped(visible_start_ms),
            1,
        )
        timeline_events.append(
            {
                "ts_ms_from_start": battle_offset_ms(visible_start_ms),
                "lane_type": "buff",
                "source_character_key": event["source_character_key"],
                "source_character_name": event["source_character_name"],
                "target_character_key": event["target_character_key"],
                "target_character_name": event["target_character_name"],
                "target_player_key": event.get("target_player_key"),
                "target_enemy_key": event.get("target_enemy_key"),
                "event_type": "buff",
                "event_key": event["event_key"],
                "event_name": event["event_name"],
                "value": None,
                "rdps_contributions": [],
                "duration_ms": visible_duration_ms,
                "actual_start_ms_from_start": battle_offset_ms_unclamped(actual_start_ms),
                "actual_end_ms_from_start": battle_offset_ms_unclamped(actual_end_ms),
                "actual_duration_ms": max(
                    battle_offset_ms_unclamped(actual_end_ms) - battle_offset_ms_unclamped(actual_start_ms),
                    1,
                ),
                "effects": _window_effects_at_ts(event, visible_start_ms),
                "dynamic_effects": list(event.get("dynamic_effects") or []),
                "important": True,
            }
        )
    timeline_events.sort(key=lambda item: (item["ts_ms_from_start"], item["lane_type"], item["event_name"]))

    role_skill_stats = _build_role_skill_stats_from_timeline_groups(hits, roster_order)
    loadout = sorted(
        battle_loadout_by_char.values(),
        key=lambda item: (int(item.get("slot") or 0), str(item.get("character_key") or "")),
    )
    debug_hits: list[dict[str, Any]] = []
    if include_rdps_debug:
        buff_records_by_uid = _build_buff_record_index(buff_starts)
        for hit in hits:
            allocation = _allocate_rdps_for_hit(
                hit,
                buff_windows,
                include_debug=True,
                buff_records_by_uid=buff_records_by_uid,
                condition_buff_records=buff_starts,
            )
            debug_hit = dict(hit)
            debug_hit["rdps_contributions"] = allocation.get("contributions_list") or []
            for key in (
                "zones",
                "ignored_effects",
                "product_external_multiplier",
                "attacker_share",
                "external_pool",
                "external_sources",
                "zone_summary",
                "buff_source_summary",
                "packet_modifier_uids",
                "packet_modifier_details",
            ):
                debug_hit[key] = allocation.get(key)
            debug_hits.append(debug_hit)

    fingerprint_payload = {
        "rules_version": RULES_VERSION,
        "boss_key": boss_key,
        "first_hit_ms": first_hit_ms,
        "last_hit_ms": last_hit_ms,
        "hits": [
            {
                "ts_ms": hit["ts_ms"],
                "character_key": hit["character_key"],
                "skill_key": hit["skill_key"],
                "hit_value": hit["hit_value"],
                "crit_flag": hit["crit_flag"],
                "target_enemy_key": hit["target_enemy_key"],
            }
            for hit in hits
        ],
    }
    contract_tags = [_contract_tag_payload(tag_id) for tag_id in contract_tag_ids]
    if contract_tags:
        tag_scores = [_coerce_int(str(tag.get("score") or ""), default=0) for tag in contract_tags]
        computed_contract_tag_score = sum(tag_scores)
        if computed_contract_tag_score > 0:
            contract_tag_score = computed_contract_tag_score
        elif contract_tag_score is None:
            contract_tag_score = computed_contract_tag_score

    return {
        "battle": {
            "dungeon_key": dungeon_key,
            "dungeon_name": dungeon_name,
            "boss_key": boss_key,
            "boss_name": boss_name,
            "battle_start_at": _build_iso_datetime(reference_date, first_hit_ms),
            "battle_end_at": _build_iso_datetime(reference_date, last_hit_ms),
            "duration_ms": duration_ms,
            "time_source": "game_timer" if has_game_timer_window else time_source,
            "timeline_zero_source": timeline_zero_source,
            "timer_start_seen": timer_start_seen,
            "timer_end_seen": timer_end_seen,
            "official_timer_start_seen": official_timer_start_ms is not None,
            "official_timer_end_seen": official_timer_end_ms is not None,
            "timer_start_inferred": timer_start_inferred,
            "timer_window_valid": timer_window_valid,
            "clear_flag": clear_flag,
            "challenge_pass_confirmed": challenge_pass_confirmed,
            "official_pass_confirmed": official_pass_confirmed,
            "completion_source": completion_source,
            "boss_identity_source": (
                "trace_inference"
                if trace_identity_inference_seen
                else "inferred_dungeon_context"
                if identity_retargeted
                else "damage_target"
            ),
            "dungeon_context_id": dungeon_context_id,
            "dungeon_identity_source": (
                "dungeon_context"
                if dungeon_context is not None
                else "unmapped_dungeon_context"
                if dungeon_context_id
                else "missing_dungeon_context"
            ),
            "total_damage": total_damage,
            "total_dps": total_dps,
            "roster": roster,
            "battle_fingerprint": build_canonical_sha256(fingerprint_payload),
            "parser_version": PARSER_VERSION,
            "rules_version": RULES_VERSION,
            "source_file_name": file_name,
            "loadout_stale": loadout_stale,
            "rdps_damage_basis": rdps_damage_basis,
            "contract_tag_score": contract_tag_score,
            "contract_tags": contract_tags,
        },
        "participants": participants,
        "loadout": loadout,
        "buff_events": buff_events,
        "timeline_events": timeline_events,
        "role_skill_stats": role_skill_stats,
        "debug_hits": debug_hits,
        "rdps_damage_basis": rdps_damage_basis,
        "rdps_preflight": rdps_preflight,
        "casts": casts_export,
        "char_skills": {
            character_key: [
                {"skill_key": skill_key, "level": level}
                for skill_key, level in sorted(levels.items())
            ]
            for character_key, levels in char_skill_levels.items()
        },
    }
