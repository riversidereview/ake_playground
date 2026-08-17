from __future__ import annotations

import json
import re
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from functools import lru_cache
from math import log
from pathlib import Path
from statistics import median
from typing import Any

from parser_core.battle_log_parser import (
    UNKNOWN_DUNGEON_KEY,
    UNKNOWN_DUNGEON_NAME,
    _BUFF_EFFECT_SKILL_FILTER,
    _BUFF_SKILL_FILTER,
    _CHR_BORROW_WINDOW_MS,
    _GENERIC_BUFF_PREFIXES,
    _ATTR_TYPE_BUFF_LABELS,
    _ATTR_TYPE_TO_EFFECT,
    _WEAPON_BUFF_RE,
    _apply_buff_stack_limits,
    _annotate_hit_enemy_hp_state,
    _attr_type_applies_to_skill,
    _bb_duration_ms_for_enemy_defense_effect,
    _buff_stack_limit,
    _equip_buff_matches_active_suits,
    _build_special_combo_windows,
    _cap_enemy_overkill_damage,
    _allocate_rdps_for_hit,
    _coerce_float,
    _coerce_int,
    _coerce_optional_float,
    _collect_buff_labels,
    _collect_zone_effects,
    _canonical_num_table_skill_id,
    _character_base_stats,
    _dedupe_mirrored_buff_windows,
    _derive_static_self_multiplier_entries,
    _damage_school_from_element,
    _damage_element_from_dpd_raw,
    _duration_ms_from_seconds,
    _effect_applies_to_damage_element,
    _extract_character_key,
    _extract_dynamic_effect_specs,
    _extract_enemy_key,
    _extract_fields,
    _extend_buff_records_from_packet_modifiers,
    _infer_skill_damage_element,
    _infer_skill_action_damage_element,
    _infer_related_buff_end_times,
    _is_noise_buff,
    _merge_buff_windows,
    _normalize_buff_duration_ms,
    _normalize_buff_id,
    _normalize_effect_element,
    _packet_mapping_applies,
    _packet_mapping_stack_limit,
    _packet_buff_semantic_candidates,
    _packet_numeric_skill_hint,
    _packet_numeric_buff_hint,
    _canonical_packet_buff_id,
    _preserve_raw_numeric_internal_trigger_buff_id,
    _classify_packet_buff_record,
    _parse_loadout_suits,
    _merge_loadout_snapshot,
    _parse_hint_timestamp_ms,
    _parse_loadout_slot_snapshot,
    _parse_loadout_stats_snapshot,
    _parse_prefixed_timestamp_ms,
    _prefer_packet_buff_record,
    _resolve_character_name,
    _resolve_dungeon_context,
    _resolve_enemy_name,
    _resolve_skill_family_key,
    _resolve_skill_name,
    _resolve_skill_profile,
    _infer_skill_damage_school,
    _is_runtime_numeric_skill_id,
    _apply_same_frame_trigger_skill_mappings,
    _infer_missing_hit_damage_schools,
    _RDPS_ALLOCATABLE_ZONES,
    _canonical_runtime_buff_skill_id,
    _same_frame_trigger_buff_for_runtime_skill,
    _runtime_skill_number,
    _runtime_skill_trigger_chain_mapping,
    _trigger_damage_identity_from_buff,
    _collect_party_actor_ids,
    _infer_context_enemy_hint,
    _recover_enemy_target_from_mislabeled_actor,
    _record_has_enemy_defense_effect,
    _resolve_weapon_buff_sources,
    _safe_positive_rate,
    _should_ignore_rate_buff,
    _weapon_buff_matches_active_weapon,
    _window_matches_packet_uids,
    _window_effects_at_ts,
)


ZONE_LABELS = {
    "atk": "攻击",
    "dmg_inc": "增伤",
    "fragile": "脆弱",
    "vuln_taken": "易伤",
    "amp": "增幅",
    "res": "减抗",
    "combo": "连击",
    "crit": "暴击",
}
ZONE_ORDER = {
    "atk": 0,
    "dmg_inc": 1,
    "fragile": 2,
    "vuln_taken": 3,
    "amp": 4,
    "res": 5,
    "combo": 6,
    "crit": 7,
}
ELEMENT_LABELS = {
    "physical": "物理",
    "fire": "灼热",
    "pulse": "电磁",
    "cryst": "寒冷",
    "natural": "自然",
    "spell": "法术",
}
DPD_ZONE_BUCKETS = {
    "dmg_inc": ("atk", 1),
    "amp": ("atk", 3),
    "combo": ("atk", 4),
    "vuln_taken": ("def", 1),
    "fragile": ("def", 5),
}

_HIT_SEQ_RE = re.compile(r"\bHP_V2\s+#(\d+)\b")
_ACTOR_MAP_RE = re.compile(r"\bACTOR_MAP\b")
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
_RAW_LOG_PROOF_BEGIN_PREFIX = "## ENDFIELD_RAW_LOG_INTEGRITY_BEGIN sep="
_RAW_LOG_PROOF_END = "## ENDFIELD_RAW_LOG_INTEGRITY_END"
_REPO_ROOT = Path(__file__).resolve().parents[3]
_XLSX_NS = {
    "a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


def _read_json_file(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _normalize_value_options(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def _selected_option_for_level(options: list[Any], level: Any) -> Any:
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


def _sub_affix_key_order(raw_key: Any) -> tuple[int, str]:
    match = re.search(r"(\d+)", str(raw_key))
    return (int(match.group(1)) if match else 99, str(raw_key))


def _build_affix_rows(item: dict[str, Any], levels: list[int] | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    levels = levels or []
    main_attr = item.get("主词条")
    if isinstance(main_attr, dict):
        rows.append(
            {
                "kind": "main",
                "index": 0,
                "desc": _clean_text(main_attr.get("desc")),
                "value": main_attr.get("value"),
                "value_options": _normalize_value_options(main_attr.get("value")),
                "level": None,
                "selected_value": main_attr.get("value"),
            }
        )
    sub_attrs = item.get("副词条")
    if isinstance(sub_attrs, dict):
        for index, key in enumerate(sorted(sub_attrs.keys(), key=_sub_affix_key_order)):
            attr = sub_attrs.get(key)
            if not isinstance(attr, dict):
                continue
            options = _normalize_value_options(attr.get("value"))
            level = levels[index] if index < len(levels) else None
            selected = _selected_option_for_level(options, level)
            rows.append(
                {
                    "kind": "sub",
                    "index": index,
                    "desc": _clean_text(attr.get("desc")),
                    "value": selected if selected is not None else attr.get("value"),
                    "value_options": options,
                    "level": level,
                    "selected_value": selected,
                }
            )
    return rows


@lru_cache(maxsize=1)
def _load_equip_affix_catalog() -> dict[str, dict[str, Any]]:
    catalog: dict[str, dict[str, Any]] = {}
    equip_root = _REPO_ROOT / "data" / "akedata" / "equip" / "items"
    if not equip_root.exists():
        return catalog
    for path in sorted(equip_root.glob("*.json")):
        payload = _read_json_file(path)
        if not isinstance(payload, dict):
            continue
        suit_id = str(payload.get("suitID") or path.stem)
        suit_name = _clean_text(payload.get("套组名称") or payload.get("displayName") or payload.get("name"))
        equip_items = payload.get("equip")
        if not isinstance(equip_items, dict):
            continue
        for item_id, item in equip_items.items():
            if not isinstance(item, dict):
                continue
            item_key = str(item.get("itemId") or item_id)
            catalog[item_key] = {
                "item_id": item_key,
                "piece_name": _clean_text(item.get("name")),
                "suit_id": suit_id,
                "suit_name": suit_name,
                "part_name": _clean_text(item.get("部位")),
                "affixes": _build_affix_rows(item),
            }
    return catalog


@lru_cache(maxsize=1)
def _load_weapon_affix_catalog() -> dict[str, dict[str, Any]]:
    catalog: dict[str, dict[str, Any]] = {}
    weapon_root = _REPO_ROOT / "data" / "akedata" / "weapon" / "items"
    if not weapon_root.exists():
        return catalog
    for path in sorted(weapon_root.glob("*.json")):
        payload = _read_json_file(path)
        if not isinstance(payload, dict):
            continue
        weapon_id = str(payload.get("weaponId") or path.stem)
        catalog[weapon_id] = {
            "weapon_template": weapon_id,
            "weapon_name": _clean_text(payload.get("title") or payload.get("name") or weapon_id),
            "weapon_base_atk_values": payload.get("baseAtk") if isinstance(payload.get("baseAtk"), list) else [],
            "weapon_skilllist": payload.get("skilllist") if isinstance(payload.get("skilllist"), list) else [],
        }
    return catalog


def _extract_embedded_raw_log_proof(text: str) -> dict[str, Any] | None:
    begin_idx = text.rfind(_RAW_LOG_PROOF_BEGIN_PREFIX)
    if begin_idx < 0:
        return None
    begin_line_end = text.find("\n", begin_idx)
    if begin_line_end < 0:
        return None
    end_marker = "\n" + _RAW_LOG_PROOF_END
    end_idx = text.find(end_marker, begin_line_end + 1)
    if end_idx < 0:
        return None
    try:
        proof = json.loads(text[begin_line_end + 1:end_idx])
    except json.JSONDecodeError:
        return None
    return proof if isinstance(proof, dict) else None


def _enrich_equip_row(equip: dict[str, Any]) -> dict[str, Any]:
    item_id = str(equip.get("item_id") or equip.get("itemId") or "")
    meta = _load_equip_affix_catalog().get(item_id, {})
    row = dict(equip)
    row.setdefault("item_id", item_id)
    row.setdefault("piece_name", meta.get("piece_name") or item_id)
    row.setdefault("suit_id", meta.get("suit_id") or "")
    row.setdefault("suit_name", meta.get("suit_name") or "")
    row.setdefault("part_name", meta.get("part_name") or "")
    levels = row.get("enhance_levels")
    if not isinstance(levels, list):
        levels = []
    levels = [int(value) for value in levels if isinstance(value, int) or str(value).lstrip("-").isdigit()]
    raw_affixes = row.get("affixes") if isinstance(row.get("affixes"), list) else meta.get("affixes") or []
    affixes: list[dict[str, Any]] = []
    main_attr: dict[str, Any] | None = None
    sub_attrs: list[dict[str, Any]] = []
    for raw_attr in raw_affixes:
        if not isinstance(raw_attr, dict):
            continue
        attr = dict(raw_attr)
        if attr.get("kind") == "sub":
            index = int(attr.get("index") or 0)
            level = levels[index] if index < len(levels) else attr.get("level")
            options = attr.get("value_options") if isinstance(attr.get("value_options"), list) else []
            selected = _selected_option_for_level(options, level)
            attr["level"] = level
            attr["selected_value"] = selected
            if selected is not None:
                attr["value"] = selected
            sub_attrs.append(attr)
        elif main_attr is None:
            main_attr = attr
        affixes.append(attr)
    row["enhance_levels"] = levels
    row["affixes"] = affixes
    row["main_attr"] = row.get("main_attr") or main_attr
    row["sub_attrs"] = row.get("sub_attrs") if isinstance(row.get("sub_attrs"), list) and row.get("sub_attrs") else sub_attrs
    try:
        failed_times = int(row.get("enhance_failed_times"))
    except (TypeError, ValueError):
        failed_times = None
    row["enhance_failed_times"] = failed_times if failed_times and 0 < failed_times <= 10000 else None
    return row


def _is_valid_equip_row(equip: dict[str, Any]) -> bool:
    item_id = str(equip.get("item_id") or equip.get("itemId") or "")
    return item_id.startswith("item_")


_ATTR_NAME_TO_TYPE = {
    "力量": 39,
    "敏捷": 40,
    "智识": 41,
    "意志": 42,
}


@lru_cache(maxsize=1)
def _load_character_attr_type_catalog() -> dict[str, dict[str, int | None]]:
    root = _REPO_ROOT / "data" / "local_tables" / "character" / "items"
    catalog: dict[str, dict[str, int | None]] = {}
    if not root.is_dir():
        return catalog
    for path in root.glob("chr_*.json"):
        payload = _read_json_file(path)
        raw = payload.get("raw") if isinstance(payload, dict) and isinstance(payload.get("raw"), dict) else {}
        main_attr_type = raw.get("mainAttrType")
        sub_attr_type = raw.get("subAttrType")
        try:
            main_attr_int = int(main_attr_type) if main_attr_type is not None else None
        except (TypeError, ValueError):
            main_attr_int = None
        try:
            sub_attr_int = int(sub_attr_type) if sub_attr_type is not None else None
        except (TypeError, ValueError):
            sub_attr_int = None
        catalog[path.stem] = {
            "main_attr_type": main_attr_int,
            "sub_attr_type": sub_attr_int,
        }
    return catalog


def _estimate_visible_panel_attack(
    character_key: str,
    loadout_row: dict[str, Any],
    base_stats: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(base_stats, dict):
        return None
    attr_types = _load_character_attr_type_catalog().get(character_key, {})
    main_attr_type = attr_types.get("main_attr_type")
    sub_attr_type = attr_types.get("sub_attr_type")
    if main_attr_type is None or sub_attr_type is None:
        return None

    ability_totals = {
        39: float(base_stats.get("attr_39") or 0.0),
        40: float(base_stats.get("attr_40") or 0.0),
        41: float(base_stats.get("attr_41") or 0.0),
        42: float(base_stats.get("attr_42") or 0.0),
    }
    atk_pct_bonus = 0.0
    flat_atk_bonus = 0.0
    sub_attr_pct_bonus = 0.0

    for skill in loadout_row.get("weapon_source_skills") or []:
        if not isinstance(skill, dict):
            continue
        bb = skill.get("bb") if isinstance(skill.get("bb"), dict) else {}
        for key, raw_value in bb.items():
            try:
                value = float(raw_value)
            except (TypeError, ValueError):
                continue
            lowered = str(key).lower()
            if lowered == "atk":
                atk_pct_bonus += value
            elif lowered == "mainattr":
                ability_totals[main_attr_type] = ability_totals.get(main_attr_type, 0.0) + value
            elif lowered == "second_attr_up":
                sub_attr_pct_bonus += value
            elif lowered in {"str", "agi", "wisd", "will"}:
                attr_type = _ATTR_NAME_TO_TYPE.get({"str": "力量", "agi": "敏捷", "wisd": "智识", "will": "意志"}[lowered])
                if attr_type is not None:
                    ability_totals[attr_type] = ability_totals.get(attr_type, 0.0) + value

    for equip in loadout_row.get("equips") or []:
        if not isinstance(equip, dict):
            continue
        for stat in equip.get("stats") or []:
            if not isinstance(stat, dict):
                continue
            name = str(stat.get("name") or "")
            try:
                value = float(stat.get("value") or 0.0)
            except (TypeError, ValueError):
                continue
            attr_type = _ATTR_NAME_TO_TYPE.get(name)
            if attr_type is not None:
                ability_totals[attr_type] = ability_totals.get(attr_type, 0.0) + value
            elif name == "攻击力":
                flat_atk_bonus += value

    if sub_attr_pct_bonus:
        ability_totals[sub_attr_type] = ability_totals.get(sub_attr_type, 0.0) * (1.0 + sub_attr_pct_bonus)

    try:
        character_base_atk = float(base_stats.get("atk") or 0.0)
    except (TypeError, ValueError):
        character_base_atk = 0.0
    try:
        weapon_base_atk = float(loadout_row.get("weapon_base_atk") or 0.0)
    except (TypeError, ValueError):
        weapon_base_atk = 0.0
    if character_base_atk <= 0 or weapon_base_atk <= 0:
        return None

    main_attr_total = ability_totals.get(main_attr_type, 0.0)
    sub_attr_total = ability_totals.get(sub_attr_type, 0.0)
    ability_bonus_multiplier = 1.0 + int(main_attr_total) * 0.005 + int(sub_attr_total) * 0.002
    panel_attack_estimate = ((character_base_atk + weapon_base_atk) * (1.0 + atk_pct_bonus) + flat_atk_bonus) * ability_bonus_multiplier
    return {
        "main_attr_type": main_attr_type,
        "sub_attr_type": sub_attr_type,
        "main_attr_total": main_attr_total,
        "sub_attr_total": sub_attr_total,
        "atk_pct_bonus": atk_pct_bonus,
        "flat_atk_bonus": flat_atk_bonus,
        "sub_attr_pct_bonus": sub_attr_pct_bonus,
        "ability_bonus_multiplier": ability_bonus_multiplier,
        "panel_attack_estimate": panel_attack_estimate,
    }


def _damage_doc_workbook_path() -> Path:
    return _REPO_ROOT.parent / "endfield_docs" / "干员属性.xlsx"


@lru_cache(maxsize=1)
def _load_damage_doc_sheet_rows() -> dict[str, list[list[str | None]]]:
    path = _damage_doc_workbook_path()
    if not path.exists():
        return {}
    sheets: dict[str, list[list[str | None]]] = {}
    try:
        with zipfile.ZipFile(path) as zf:
            shared_strings: list[str] = []
            if "xl/sharedStrings.xml" in zf.namelist():
                root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
                for si in root.findall("a:si", _XLSX_NS):
                    texts = [node.text or "" for node in si.iterfind(".//a:t", _XLSX_NS)]
                    shared_strings.append("".join(texts))

            workbook = ET.fromstring(zf.read("xl/workbook.xml"))
            rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
            rel_map: dict[str, str] = {}
            for rel in rels:
                rid = rel.attrib.get("Id")
                target = rel.attrib.get("Target")
                if rid and target:
                    rel_map[rid] = target

            def cell_value(cell: ET.Element) -> str | None:
                cell_type = cell.attrib.get("t")
                if cell_type == "inlineStr":
                    texts = [node.text or "" for node in cell.iterfind(".//a:t", _XLSX_NS)]
                    return "".join(texts)
                value = cell.find("a:v", _XLSX_NS)
                if value is None:
                    return None
                raw = value.text
                if cell_type == "s":
                    try:
                        return shared_strings[int(raw)]
                    except Exception:
                        return raw
                return raw

            sheet_root = workbook.find("a:sheets", _XLSX_NS)
            if sheet_root is None:
                return {}
            for sheet in sheet_root:
                name = sheet.attrib.get("name")
                rid = sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
                target = rel_map.get(rid or "")
                if not name or not target:
                    continue
                sheet_path = "xl/" + target if not target.startswith("xl/") else target
                if sheet_path not in zf.namelist():
                    continue
                xml_root = ET.fromstring(zf.read(sheet_path))
                rows: list[list[str | None]] = []
                for row in xml_root.findall(".//a:sheetData/a:row", _XLSX_NS):
                    values = [cell_value(cell) for cell in row.findall("a:c", _XLSX_NS)]
                    rows.append(values)
                sheets[name] = rows
    except Exception:
        return {}
    return sheets


def _parse_doc_scalar(value: str | None) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("%"):
        text = text[:-1]
        try:
            return float(text) / 100.0
        except ValueError:
            return None
    try:
        return float(text)
    except ValueError:
        return None


@lru_cache(maxsize=1)
def _load_damage_doc_skill_scalar_catalog() -> dict[str, dict[str, dict[int, float]]]:
    rows = _load_damage_doc_sheet_rows().get("干员技能属性") or []
    catalog: dict[str, dict[str, dict[int, float]]] = defaultdict(lambda: defaultdict(dict))
    if not rows:
        return {}
    for row in rows[1:]:
        if len(row) < 5:
            continue
        skill_id = str(row[2] or "").strip()
        key = str(row[3] or "").strip()
        if not skill_id or not key:
            continue
        for index, raw_value in enumerate(row[4:16], start=1):
            scalar = _parse_doc_scalar(raw_value)
            if scalar is None:
                continue
            catalog[skill_id][key][index] = scalar
    return {
        skill_id: {key: dict(levels) for key, levels in values.items()}
        for skill_id, values in catalog.items()
    }


def _skill_doc_scalar(skill_key: str | None, skill_level: int | None) -> float | None:
    if not skill_key or not skill_level or skill_level <= 0:
        return None
    catalog = _load_damage_doc_skill_scalar_catalog()
    candidate_keys = [str(skill_key)]
    text = str(skill_key)
    for candidate in (
        text.removesuffix("_blocked"),
        text.removesuffix("_projhit"),
        text.removesuffix("_projhit_blocked"),
    ):
        if candidate and candidate not in candidate_keys:
            candidate_keys.append(candidate)
    if text.endswith("_projhit"):
        base = text.removesuffix("_projhit")
        if base and base not in candidate_keys:
            candidate_keys.append(base)
    for candidate_key in candidate_keys:
        rows = catalog.get(candidate_key, {})
        if not rows:
            continue
        for key_name in ("atk_scale", "display_atk_scale"):
            values = rows.get(key_name)
            if isinstance(values, dict) and skill_level in values:
                return values[skill_level]
    return None


def _extract_loadout_from_text(text: str) -> list[dict[str, Any]]:
    def _loadout_from_raw_lines() -> list[dict[str, Any]]:
        self_scene_loadout_by_char: dict[str, dict[str, Any]] = {}
        sync_char_bag_loadout_by_char: dict[str, dict[str, Any]] = {}
        orphan_loadout_by_char: dict[str, dict[str, Any]] = {}
        current_reason: str | None = None
        for raw_line in text.splitlines():
            reason_match = re.search(r"\bLOADOUT\s+reason=([^\s]+)", raw_line)
            if reason_match:
                current_reason = reason_match.group(1)
                if current_reason == "SC_SELF_SCENE_INFO":
                    self_scene_loadout_by_char = {}
                elif current_reason == "SC_SYNC_CHAR_BAG_INFO":
                    sync_char_bag_loadout_by_char = {}
                elif current_reason == "BATTLE_START":
                    orphan_loadout_by_char = {}
                continue
            snapshot: dict[str, Any] | None = None
            if " LOADOUT_STATS " in raw_line or "LOADOUT_STATS " in raw_line:
                snapshot = _parse_loadout_stats_snapshot(raw_line)
            elif " LOADOUT slot=" in raw_line or "LOADOUT slot=" in raw_line:
                snapshot = _parse_loadout_slot_snapshot(raw_line)
            if snapshot is None:
                continue
            char_key = str(snapshot.get("character_key") or "")
            if not char_key:
                continue
            if current_reason == "SC_SELF_SCENE_INFO":
                self_scene_loadout_by_char[char_key] = _merge_loadout_snapshot(
                    self_scene_loadout_by_char.get(char_key, {}),
                    snapshot,
                )
            elif current_reason == "SC_SYNC_CHAR_BAG_INFO":
                sync_char_bag_loadout_by_char[char_key] = _merge_loadout_snapshot(
                    sync_char_bag_loadout_by_char.get(char_key, {}),
                    snapshot,
                )
            elif current_reason is None:
                orphan_loadout_by_char[char_key] = _merge_loadout_snapshot(
                    orphan_loadout_by_char.get(char_key, {}),
                    snapshot,
                )
            else:
                orphan_loadout_by_char[char_key] = _merge_loadout_snapshot(
                    orphan_loadout_by_char.get(char_key, {}),
                    snapshot,
                )
        loadout_by_char = self_scene_loadout_by_char or sync_char_bag_loadout_by_char or orphan_loadout_by_char
        return sorted(loadout_by_char.values(), key=lambda row: int(row.get("slot") or 0))

    proof = _extract_embedded_raw_log_proof(text)
    meta = proof.get("meta") if isinstance(proof, dict) else None
    loadout = meta.get("loadout") if isinstance(meta, dict) else None
    line_loadout = _loadout_from_raw_lines()
    if isinstance(loadout, list):
        line_by_char = {
            str(row.get("character_key") or row.get("char_key") or row.get("char") or ""): row
            for row in line_loadout
            if str(row.get("character_key") or row.get("char_key") or row.get("char") or "")
        }
        merged_loadout: list[dict[str, Any]] = []
        for entry in loadout:
            if not isinstance(entry, dict):
                continue
            char_key = str(entry.get("character_key") or entry.get("char_key") or entry.get("char") or "")
            base = line_by_char.get(char_key, {})
            merged_loadout.append(_merge_loadout_snapshot(base, entry))
        loadout = merged_loadout
    else:
        loadout = line_loadout
    weapon_catalog = _load_weapon_affix_catalog()
    enriched: list[dict[str, Any]] = []
    for entry in loadout:
        if not isinstance(entry, dict):
            continue
        row = dict(entry)
        row["character_key"] = str(row.get("character_key") or row.get("char_key") or row.get("char") or "")
        row["char_key"] = str(row.get("char_key") or row["character_key"])
        row["character_name"] = str(row.get("character_name") or row.get("char_name") or row["character_key"])
        row["char_name"] = str(row.get("char_name") or row["character_name"])
        weapon_template = str(row.get("weapon_template") or "")
        weapon_meta = weapon_catalog.get(weapon_template, {})
        row.setdefault("weapon_name", weapon_meta.get("weapon_name") or weapon_template)
        base_values = weapon_meta.get("weapon_base_atk_values") if isinstance(weapon_meta, dict) else []
        weapon_level = row.get("weapon_level")
        if row.get("weapon_base_atk") is None and isinstance(base_values, list):
            try:
                level_int = int(weapon_level)
            except (TypeError, ValueError):
                level_int = 0
            if 0 < level_int <= len(base_values):
                row["weapon_base_atk"] = base_values[level_int - 1]
        row.setdefault("weapon_skilllist", weapon_meta.get("weapon_skilllist") or [])
        row["equips"] = [
            _enrich_equip_row(equip)
            for equip in row.get("equips") or []
            if isinstance(equip, dict) and _is_valid_equip_row(equip)
        ]
        enriched.append(row)
    return enriched


def _loadout_skill_ids_by_char(loadout: list[dict[str, Any]]) -> dict[str, set[str]]:
    ids_by_char: dict[str, set[str]] = {}
    for row in loadout:
        char_key = str(row.get("character_key") or row.get("char_key") or row.get("char") or "")
        if not char_key:
            continue
        ids_by_char[char_key] = {
            str(skill_id)
            for skill_id in row.get("skill_int_ids") or []
            if str(skill_id)
        }
    return ids_by_char


@lru_cache(maxsize=None)
def _load_exported_character_skill_groups(character_key: str) -> list[dict[str, Any]]:
    path = _REPO_ROOT / "data" / "akedata" / "character" / "items" / f"{character_key}.json"
    payload = _read_json_file(path)
    if not isinstance(payload, dict):
        return []
    labels = {0: "普攻", 1: "战技", 2: "终结", 3: "连携"}
    groups: list[dict[str, Any]] = []
    for skill in payload.get("skills") or []:
        if not isinstance(skill, dict):
            continue
        try:
            group_type = int(skill.get("groupType") or 0)
        except (TypeError, ValueError):
            group_type = 0
        skill_ids = [str(skill_id) for skill_id in skill.get("skillIds") or [] if skill_id]
        if not skill_ids:
            continue
        groups.append(
            {
                "group_type": group_type,
                "group_label": labels.get(group_type, str(group_type)),
                "name": _clean_text(skill.get("name")) or labels.get(group_type, ""),
                "skill_ids": skill_ids,
            }
        )
    return groups


def _active_loadout_maps_from_rows(
    loadout: list[dict[str, Any]],
) -> tuple[dict[str, set[str]], dict[str, str]]:
    active_suits_by_char: dict[str, set[str]] = {}
    active_weapons_by_char: dict[str, str] = {}
    for row in loadout:
        if not isinstance(row, dict):
            continue
        char_key = str(row.get("character_key") or row.get("char_key") or row.get("char") or "")
        if not char_key:
            continue
        weapon_template = str(row.get("weapon_template") or "")
        if weapon_template:
            active_weapons_by_char[char_key] = weapon_template
        suit_counter: dict[str, int] = defaultdict(int)
        for equip in row.get("equips") or []:
            if not isinstance(equip, dict):
                continue
            suit_id = str(equip.get("suit_id") or equip.get("suitID") or "")
            if suit_id:
                suit_counter[suit_id] += 1
        for suit_effect in row.get("suit_effects") or []:
            if not isinstance(suit_effect, dict):
                continue
            suit_id = str(suit_effect.get("suit_id") or "")
            if suit_id and suit_effect.get("active", True):
                suit_counter[suit_id] = max(suit_counter.get(suit_id, 0), int(suit_effect.get("piece_count") or 3))
        suit_blob = str(row.get("equip_suit") or row.get("equipSuit") or row.get("equip_suit_raw") or "")
        for suit_id in _parse_loadout_suits(suit_blob):
            suit_counter[suit_id] = max(suit_counter.get(suit_id, 0), 3)
        active_suits_by_char[char_key] = {
            suit_id for suit_id, count in suit_counter.items() if count >= 3
        }
    return active_suits_by_char, active_weapons_by_char


@lru_cache(maxsize=1)
def _load_skill_action_graph_candidate_map() -> dict[str, list[dict[str, Any]]]:
    path = _REPO_ROOT / "data" / "packet_semantics" / "skill_action_graph_candidates.json"
    payload = _read_json_file(path)
    if not isinstance(payload, dict):
        return {}
    candidates = payload.get("candidates")
    if not isinstance(candidates, dict):
        return {}
    result: dict[str, list[dict[str, Any]]] = {}
    for skill_key, rows in candidates.items():
        if not isinstance(rows, list):
            continue
        normalized_rows: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            candidate_skill_id = str(row.get("candidate_skill_id") or "")
            if not candidate_skill_id:
                continue
            normalized_rows.append(
                {
                    "candidate_skill_id": candidate_skill_id,
                    "display_name": str(row.get("display_name") or candidate_skill_id),
                    "confidence": str(row.get("confidence") or "action_graph_candidate"),
                    "source": str(row.get("source") or "akedata_action_graph"),
                    "reason": str(row.get("reason") or ""),
                    "evidence": [str(item) for item in row.get("evidence") or []],
                }
            )
        if normalized_rows:
            result[str(skill_key)] = normalized_rows
    return result


def _action_graph_skill_candidates(
    skill_key: str,
    *,
    character_key: str | None,
) -> list[dict[str, Any]]:
    rows = _load_skill_action_graph_candidate_map().get(str(skill_key or ""), [])
    if not rows:
        return []
    if not character_key:
        return rows
    character_prefix = f"{character_key}_"
    return [
        row
        for row in rows
        if str(row.get("candidate_skill_id") or "").startswith(character_prefix)
    ]


def _skill_mapping_info(
    skill_key: str,
    *,
    character_key: str | None,
    target_enemy_key: str | None,
    damage_element: str | None,
    original_template_int_id: int | None,
    ts_ms: int,
    recent_actor_maps_by_char: dict[str, list[dict[str, Any]]],
    recent_skill_casts_by_char: dict[str, list[dict[str, Any]]],
    recent_numeric_buffs_by_source: dict[str, list[dict[str, Any]]],
    loadout_skill_ids_by_char: dict[str, set[str]],
) -> dict[str, Any]:
    skill_number = _runtime_skill_number(skill_key)
    loadout_skill_ids = loadout_skill_ids_by_char.get(str(character_key or ""), set())
    in_loadout = bool(skill_number and skill_number in loadout_skill_ids)
    exported_groups = _load_exported_character_skill_groups(str(character_key or "")) if character_key else []
    same_number_buff: dict[str, Any] | None = None
    same_number_buff_delta_ms: int | None = None
    if skill_number:
        for buff in reversed(recent_numeric_buffs_by_source.get(str(character_key or ""), [])):
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
            same_number_buff = buff
            same_number_buff_delta_ms = delta_ms
            break

    trigger_chain = _runtime_skill_trigger_chain_mapping(
        skill_key,
        character_key,
        original_template_int_id=original_template_int_id,
        target_enemy_key=target_enemy_key,
        ts_ms=ts_ms,
        recent_numeric_buffs_by_source=recent_numeric_buffs_by_source,
    )
    if trigger_chain is not None:
        canonical_skill_id = str(trigger_chain.get("canonical_skill_id") or "")
        display_name = _resolve_skill_name(canonical_skill_id) or canonical_skill_id
        return {
            "status": "mapped",
            "status_label": "已映射",
            "raw_skill_key": skill_key,
            "canonical_skill_id": canonical_skill_id,
            "display_name": display_name,
            "confidence": "orig_template_trigger_buff_chain",
            "reason": "runtime hit maps to a same-character damage buff id, and origTemplateIntId resolves to a static skill whose semantic chain creates that buff",
            "origin_skill_id": trigger_chain.get("origin_skill_id"),
            "trigger_buff_id": trigger_chain.get("trigger_buff_id"),
            "trigger_buff": trigger_chain.get("trigger_buff_evidence"),
            "candidates": [],
            "action_graph_candidates": [],
        }
    runtime_buff_skill = _canonical_runtime_buff_skill_id(skill_key, character_key)
    if runtime_buff_skill:
        display_name = _resolve_skill_name(runtime_buff_skill) or runtime_buff_skill
        return {
            "status": "mapped",
            "status_label": "已映射",
            "raw_skill_key": skill_key,
            "canonical_skill_id": runtime_buff_skill,
            "display_name": display_name,
            "confidence": "num_id_str_buff_id",
            "reason": "runtime numeric skill id matched NumIdStrTable.buff_id and the canonical buff id looks like trigger or damage-side hit content",
            "candidates": [],
            "action_graph_candidates": [],
        }

    if skill_number and character_key:
        for cast in reversed(recent_skill_casts_by_char.get(str(character_key or ""), [])):
            delta_ms = ts_ms - int(cast.get("ts_ms") or 0)
            if delta_ms < -50:
                continue
            if delta_ms > 12000:
                break
            cast_skill = str(cast.get("skill") or "")
            if not cast_skill or _is_runtime_numeric_skill_id(cast_skill):
                continue
            if same_number_buff_delta_ms is None or same_number_buff_delta_ms <= 150:
                return {
                    "status": "mapped",
                    "status_label": "已映射",
                    "raw_skill_key": skill_key,
                    "canonical_skill_id": cast_skill,
                    "confidence": "skill_start_cast_packet",
                    "reason": "runtime hit was matched to a recent BattleOpSkillStartCast packet; this packet evidence has priority over manual numeric maps",
                    "cast_evidence": {
                        "skill": cast_skill,
                        "line_no": cast.get("line_no"),
                        "start_time": cast.get("time"),
                        "delta_ms": delta_ms,
                        "owner": cast.get("owner"),
                        "skill_inst_id": cast.get("skill_inst_id"),
                    },
                    "trigger_buff": {
                        "raw_event_key": same_number_buff.get("raw_event_key"),
                        "event_key": same_number_buff.get("event_key"),
                        "line_no": same_number_buff.get("line_no"),
                        "start_time": same_number_buff.get("time"),
                        "delta_ms": same_number_buff_delta_ms,
                        "source_character_key": same_number_buff.get("source_character_key"),
                        "target_enemy_key": same_number_buff.get("target_enemy_key"),
                    }
                    if same_number_buff is not None
                    else None,
                    "candidates": [],
                    "action_graph_candidates": [],
                }

    hint = _packet_numeric_skill_hint(skill_key)
    if hint:
        return {
            "status": "mapped",
            "status_label": "已映射",
            "raw_skill_key": skill_key,
            "canonical_skill_id": str(hint.get("canonical_skill_id") or skill_key),
            "confidence": str(hint.get("confidence") or "manual_runtime_map"),
            "reason": str(hint.get("reason") or ""),
            "candidates": [],
            "action_graph_candidates": [],
        }
    num_table_skill = _canonical_num_table_skill_id(skill_key, character_key)
    if num_table_skill:
        return {
            "status": "mapped",
            "status_label": "已映射",
            "raw_skill_key": skill_key,
            "canonical_skill_id": num_table_skill,
            "confidence": "num_id_str_skill_id",
            "reason": "runtime numeric skill id matched NumIdStrTable.skill_id and the static id matches the current character family",
            "candidates": [],
            "action_graph_candidates": [],
        }
    if not re.search(r"_skill_\d+$", skill_key or ""):
        return {
            "status": "static",
            "status_label": "静态 ID",
            "raw_skill_key": skill_key,
            "canonical_skill_id": skill_key,
            "confidence": "static_id",
            "reason": "skill id is already a static-style id",
            "candidates": [],
            "action_graph_candidates": [],
        }

    candidates: list[dict[str, Any]] = []
    for actor_map in reversed(recent_actor_maps_by_char.get(str(character_key or ""), [])):
        delta_ms = ts_ms - int(actor_map.get("ts_ms") or 0)
        if delta_ms < -50:
            continue
        if delta_ms > 2500:
            break
        actor_skill = str(actor_map.get("skill") or "")
        if not actor_skill:
            continue
        candidates.append(
            {
                "candidate_skill_id": actor_skill,
                "delta_ms": delta_ms,
                "source": actor_map.get("source"),
                "actor_id": actor_map.get("actor_id"),
                "confidence": "actor_map_same_runtime"
                if actor_skill == skill_key
                else "actor_map_time_nearby",
                "reason": "same runtime skill id was observed in ACTOR_MAP shortly before this HP_V2 hit"
                if actor_skill == skill_key
                else "same-character ACTOR_MAP was observed shortly before this HP_V2 hit",
            }
        )
        if len(candidates) >= 4:
            break

    action_graph_candidates = _action_graph_skill_candidates(
        skill_key,
        character_key=character_key,
    )
    strong_actor_candidates = [
        candidate
        for candidate in candidates
        if not re.search(r"_skill_\d+$", str(candidate.get("candidate_skill_id") or ""))
        and 0 <= int(candidate.get("delta_ms") or 999999) <= 250
    ]
    if len(strong_actor_candidates) == 1:
        actor_candidate = strong_actor_candidates[0]
        canonical_skill_id = str(actor_candidate.get("candidate_skill_id") or "")
        if canonical_skill_id:
            return {
                "status": "mapped",
                "status_label": "已映射",
                "raw_skill_key": skill_key,
                "canonical_skill_id": canonical_skill_id,
                "confidence": "actor_map_single_candidate_strong",
                "reason": "a single nearby non-runtime ACTOR_MAP candidate was observed shortly before this HP_V2 hit",
                "cast_evidence": None,
                "trigger_buff": None,
                "candidates": candidates,
                "action_graph_candidates": action_graph_candidates,
            }
    trigger_chain = _runtime_skill_trigger_chain_mapping(
        skill_key,
        character_key,
        original_template_int_id=original_template_int_id,
        target_enemy_key=target_enemy_key,
        ts_ms=ts_ms,
        recent_numeric_buffs_by_source=recent_numeric_buffs_by_source,
    )
    if trigger_chain is not None:
        canonical_skill_id = str(trigger_chain.get("canonical_skill_id") or "")
        display_name = _resolve_skill_name(canonical_skill_id) or canonical_skill_id
        return {
            "status": "mapped",
            "status_label": "已映射",
            "raw_skill_key": skill_key,
            "canonical_skill_id": canonical_skill_id,
            "display_name": display_name,
            "confidence": "orig_template_trigger_buff_chain",
            "reason": "runtime hit maps to a same-character damage buff id, and origTemplateIntId resolves to a static skill whose semantic chain creates that buff",
            "origin_skill_id": trigger_chain.get("origin_skill_id"),
            "trigger_buff_id": trigger_chain.get("trigger_buff_id"),
            "trigger_buff": trigger_chain.get("trigger_buff_evidence"),
            "candidates": candidates,
            "action_graph_candidates": action_graph_candidates,
        }
    runtime_buff_skill = _canonical_runtime_buff_skill_id(skill_key, character_key)
    if runtime_buff_skill:
        display_name = _resolve_skill_name(runtime_buff_skill) or runtime_buff_skill
        return {
            "status": "mapped",
            "status_label": "已映射",
            "raw_skill_key": skill_key,
            "canonical_skill_id": runtime_buff_skill,
            "display_name": display_name,
            "confidence": "num_id_str_buff_id",
            "reason": "runtime numeric skill id matched NumIdStrTable.buff_id and the canonical buff id looks like trigger or damage-side hit content",
            "candidates": candidates,
            "action_graph_candidates": action_graph_candidates,
        }
    trigger_buff = _same_frame_trigger_buff_for_runtime_skill(
        skill_key,
        character_key,
        ts_ms,
        target_enemy_key=target_enemy_key,
        recent_numeric_buffs_by_source=recent_numeric_buffs_by_source,
    )
    if trigger_buff is not None and not in_loadout:
        buff = trigger_buff["buff"]
        delta_ms = int(trigger_buff["delta_ms"])
        canonical_skill_id, display_name = _trigger_damage_identity_from_buff(
            buff,
            damage_element=damage_element,
            target_enemy_key=target_enemy_key,
        )
        return {
            "status": "mapped",
            "status_label": "已映射",
            "raw_skill_key": skill_key,
            "canonical_skill_id": canonical_skill_id,
            "display_name": display_name,
            "confidence": "same_frame_trigger_buff",
            "reason": "runtime hit shares the same timestamp with a same-source same-target numeric BUFF_START that has no blackboard or attr evidence; treated as triggered/status damage",
            "cast_evidence": None,
            "trigger_buff": {
                "raw_event_key": buff.get("raw_event_key"),
                "event_key": buff.get("event_key"),
                "line_no": buff.get("line_no"),
                "start_time": buff.get("time"),
                "delta_ms": delta_ms,
                "source_character_key": buff.get("source_character_key"),
                "target_enemy_key": buff.get("target_enemy_key"),
            },
            "candidates": candidates,
            "action_graph_candidates": action_graph_candidates,
        }
    if skill_number and not in_loadout and same_number_buff is not None:
        buff = same_number_buff
        delta_ms = int(same_number_buff_delta_ms or 0)
        canonical_skill_id, display_name = _trigger_damage_identity_from_buff(
            buff,
            damage_element=damage_element,
            target_enemy_key=target_enemy_key,
        )
        return {
            "status": "mapped",
            "status_label": "已映射",
            "raw_skill_key": skill_key,
            "canonical_skill_id": canonical_skill_id,
            "display_name": display_name,
            "confidence": "buff_start_same_numeric",
            "reason": "runtime HP_V2 skill number matches a recent same-source same-target numeric BUFF_START; treated as triggered/status damage, not a character skill",
            "trigger_buff": {
                "raw_event_key": buff.get("raw_event_key"),
                "event_key": buff.get("event_key"),
                "line_no": buff.get("line_no"),
                "start_time": buff.get("time"),
                "delta_ms": delta_ms,
                "source_character_key": buff.get("source_character_key"),
                "target_enemy_key": buff.get("target_enemy_key"),
            },
            "candidates": [],
            "action_graph_candidates": [],
        }
    candidate_display_name = (
        str(action_graph_candidates[0].get("display_name") or "")
        if action_graph_candidates
        else ""
    )
    confidence = "none"
    if candidates:
        confidence = "actor_map_time_nearby"
    elif action_graph_candidates:
        confidence = str(action_graph_candidates[0].get("confidence") or "action_graph_candidate")
    elif in_loadout:
        confidence = "loadout_skill_int_id"

    return {
        "status": "candidate" if candidates or in_loadout or action_graph_candidates else "unmapped",
        "status_label": "候选" if candidates or in_loadout or action_graph_candidates else "未映射",
        "raw_skill_key": skill_key,
        "canonical_skill_id": None,
        "confidence": confidence,
        "reason": "runtime numeric skill id has no accepted canonical mapping",
        "loadout_skill_id": in_loadout,
        "loadout_skill_number": skill_number,
        "exported_skill_groups": exported_groups,
        "candidate_display_name": candidate_display_name,
        "candidates": candidates,
        "action_graph_candidates": action_graph_candidates,
    }


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


def _parse_hex_int(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(value, 16) if value.lower().startswith("0x") else int(value)
    except ValueError:
        return None


def _parse_dpd_raw_line(line: str) -> dict[str, Any] | None:
    match = _DPD_RAW_RE.search(line)
    if not match:
        return None
    return {
        "seq": int(match.group("seq")),
        "calc": _coerce_float(match.group("calc")),
        "atk_scale": _coerce_float(match.group("atk_scale")),
        "blocked": _coerce_int(match.group("blocked")),
        "damage_type": _parse_hex_int(match.group("damage_type")),
        "damage_type_raw": match.group("damage_type"),
        "decorate_mask": _parse_hex_int(match.group("decorate_mask")),
        "decorate_mask_raw": match.group("decorate_mask"),
        "collider": match.group("collider"),
        "atk_zones": _parse_zone_values(match.group("atk_zones")),
        "def_zones": _parse_zone_values(match.group("def_zones")),
    }


def _parse_baseline_line(line: str) -> tuple[int, dict[int, float]] | None:
    match = _BASELINE_RE.search(line)
    if not match:
        return None
    values = {
        int(key): _coerce_float(value)
        for key, value in _BASELINE_KV_RE.findall(match.group("body"))
    }
    return int(match.group("seq")), values


def _parse_packet_modifier_line(line: str) -> tuple[int, list[str], list[str]] | None:
    match = _PKT_MOD_RE.search(line)
    if not match:
        return None
    atk = [item for item in match.group("atk").split() if item]
    defender = [item for item in match.group("def").split() if item]
    return int(match.group("seq")), atk, defender


def _parse_packet_attr_line(line: str) -> tuple[int, list[str], list[str]] | None:
    match = _PKT_ATTR_RE.search(line)
    if not match:
        return None
    atk = [item for item in match.group("atk").split() if item]
    defender = [item for item in match.group("def").split() if item]
    return int(match.group("seq")), atk, defender


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


def _format_ts_ms(ts_ms: int) -> str:
    millis = ts_ms % 1000
    total_seconds = ts_ms // 1000
    seconds = total_seconds % 60
    total_minutes = total_seconds // 60
    minutes = total_minutes % 60
    hours = total_minutes // 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"


def _round4(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 4)


def _dpd_bucket_for_zone(zone: str, dpd_raw: dict[str, Any] | None) -> dict[str, Any] | None:
    if not dpd_raw:
        return None
    bucket = DPD_ZONE_BUCKETS.get(zone)
    if bucket is None:
        return None
    side, index = bucket
    values = dpd_raw.get("atk_zones") if side == "atk" else dpd_raw.get("def_zones")
    values = values or []
    if len(values) > index:
        return {"side": side, "index": index, "value": values[index]}
    return None


def _sort_zones(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(items, key=lambda item: (ZONE_ORDER.get(str(item.get("zone")), 99), str(item.get("zone"))))


def _apply_enemy_target_bb_duration_override(record: dict[str, Any]) -> None:
    if not record.get("target_enemy_key"):
        return
    bb_values = {str(key).lower(): value for key, value in (record.get("bb_values") or {}).items()}
    if not _record_has_enemy_defense_effect(record, bb_values):
        return
    duration_ms = _bb_duration_ms_for_enemy_defense_effect(bb_values)
    if duration_ms is None:
        return
    raw_duration_ms = record.get("raw_duration_ms")
    if raw_duration_ms is None or duration_ms < int(raw_duration_ms or 0):
        record["raw_duration_ms"] = duration_ms
        record["raw_duration_source"] = "bb"


def _build_buff_windows(
    hits: list[dict[str, Any]],
    buff_starts: list[dict[str, Any]],
    *,
    battle_end_ms: int,
    active_suits_by_char: dict[str, set[str]] | None = None,
    active_weapons_by_char: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    _resolve_weapon_buff_sources(buff_starts)

    buff_windows: list[dict[str, Any]] = []
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

        start_ts_ms = int(buff_record["ts_ms"])
        buff_duration_ms = _normalize_buff_duration_ms(
            start_ts_ms,
            event_key=buff_record.get("event_key"),
            end_ts_ms=buff_record.get("end_ts_ms"),
            raw_duration_ms=buff_record.get("raw_duration_ms"),
            battle_end_ms=battle_end_ms,
        )
        buff_windows.append(
            {
                "start_ts_ms": start_ts_ms,
                "start_line_no": buff_record.get("line_no"),
                "start_time": _format_ts_ms(start_ts_ms),
                "end_ts_ms": start_ts_ms + buff_duration_ms,
                "end_time": _format_ts_ms(start_ts_ms + buff_duration_ms),
                "duration_ms": buff_duration_ms,
                "uid": buff_record.get("uid"),
                "source_character_key": buff_record.get("source_character_key"),
                "source_character_name": buff_record.get("source_character_name"),
                "raw_source_character_key": buff_record.get("raw_source_character_key"),
                "raw_source_character_name": buff_record.get("raw_source_character_name"),
                "raw_source": buff_record.get("raw_source"),
                "target_character_key": buff_record.get("target_character_key")
                or buff_record.get("target_enemy_key"),
                "target_character_name": buff_record.get("target_character_name")
                or buff_record.get("target_enemy_name"),
                "target_player_key": buff_record.get("target_character_key"),
                "target_enemy_key": buff_record.get("target_enemy_key"),
                "owner_raw": buff_record.get("owner_raw"),
                "event_key": buff_record.get("event_key"),
                "event_name": " / ".join(labels) if labels else str(buff_record.get("event_key") or ""),
                "zone_effects": zone_effects,
                "dynamic_effects": dynamic_effects,
                "modifier_count": len(buff_record.get("attr_mods") or []),
                "skill_family_key": None,
                "stack_limit": _packet_mapping_stack_limit(buff_record) or _buff_stack_limit(buff_record.get("event_key")),
            }
        )

    buff_windows = _dedupe_mirrored_buff_windows(_merge_buff_windows(buff_windows))
    buff_windows.extend(_build_special_combo_windows(hits, buff_starts, battle_end_ms=battle_end_ms))
    merged = _apply_buff_stack_limits(_dedupe_mirrored_buff_windows(_merge_buff_windows(buff_windows)))
    for window in merged:
        window["start_time"] = _format_ts_ms(int(window["start_ts_ms"]))
        window["end_time"] = _format_ts_ms(int(window["end_ts_ms"]))
    return merged


def _build_buff_record_index(buff_starts: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for record in buff_starts:
        uid = str(record.get("uid") or "")
        if uid:
            index[uid] = record
    return index


def _format_effect_summary(effects: list[dict[str, Any]]) -> list[str]:
    rows: list[str] = []
    seen: set[str] = set()
    for effect in effects:
        zone = str(effect.get("zone") or "")
        zone_label = ZONE_LABELS.get(zone, zone)
        element = str(effect.get("element") or "all")
        rate = effect.get("rate")
        if rate is None and effect.get("base_rate") is not None:
            rate = effect.get("base_rate")
        try:
            base_rate = float(rate)
        except (TypeError, ValueError):
            base_rate = None
        element_text = "" if element == "all" else f"/{element}"
        if base_rate is None:
            row_text = f"{zone_label}{element_text} -"
        else:
            delayed_add_rate = float(effect.get("delayed_add_rate") or 0.0)
            delay_sec = float(effect.get("delay_sec") or 0.0)
            tick_rate = float(effect.get("tick_rate") or 0.0)
            max_rate = float(effect.get("max_rate") or 0.0)
            if delayed_add_rate > 0 and delay_sec > 0:
                row_text = (
                    f"{zone_label}{element_text} {base_rate * 100:.2f}%"
                    f" -> {(base_rate + delayed_add_rate) * 100:.2f}% @ {delay_sec:g}s"
                )
            elif tick_rate > 0 and max_rate > base_rate:
                row_text = (
                    f"{zone_label}{element_text} {base_rate * 100:.2f}%"
                    f" -> {max_rate * 100:.2f}% over time"
                )
            else:
                row_text = f"{zone_label}{element_text} {base_rate * 100:.2f}%"
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


def _build_buff_audit_rows(
    buff_starts: list[dict[str, Any]],
    *,
    battle_end_ms: int,
    included_windows: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    _resolve_weapon_buff_sources(buff_starts)
    included_uids = {
        str(window.get("uid") or "")
        for window in included_windows or []
        if window.get("uid")
    }
    for record in buff_starts:
        buff_id = _normalize_buff_id(record.get("event_key"))
        raw_buff_id = _normalize_buff_id(record.get("raw_event_key") or buff_id)
        packet_classification = _classify_packet_buff_record(record)
        semantic_candidates = _packet_buff_semantic_candidates(record)
        packet_mapping = record.get("packet_mapping") if isinstance(record.get("packet_mapping"), dict) else None
        labels = _collect_buff_labels(record)
        zone_effects = _collect_zone_effects(record)
        dynamic_effects = _extract_dynamic_effect_specs(record)
        effective_duration_ms = _normalize_buff_duration_ms(
            int(record.get("ts_ms") or 0),
            event_key=record.get("event_key"),
            end_ts_ms=record.get("end_ts_ms"),
            raw_duration_ms=record.get("raw_duration_ms"),
            battle_end_ms=battle_end_ms,
        )
        reasons: list[str] = []
        has_effects = bool(zone_effects or dynamic_effects)
        included = has_effects and (not included_uids or str(record.get("uid") or "") in included_uids)
        merged = has_effects and not included
        if _is_noise_buff(buff_id):
            reasons.append("配置为噪声/载体 buff")
        if _should_ignore_rate_buff(buff_id):
            reasons.append("规则忽略此类 rate wrapper")
        if not zone_effects and not dynamic_effects:
            reasons.append("无可识别正数效果")
        if not labels and (zone_effects or dynamic_effects):
            reasons.append("有效果但缺少展示标签")
        if merged:
            reasons.append("已被同一来源/目标/buff 的刷新链合并，不单独生效")
        if raw_buff_id.isdigit():
            if packet_mapping:
                reasons.append("numeric packet id 已通过上下文守卫映射")
            else:
                reasons.append(f"numeric packet id 未采纳：{packet_classification.get('label')}")
        status = "included" if included else "merged" if merged else "filtered"
        rows.append(
            {
                "status": status,
                "status_label": "纳入" if included else "合并" if merged else "过滤",
                "reasons": reasons,
                "line_no": record.get("line_no"),
                "uid": record.get("uid"),
                "event_key": buff_id,
                "raw_event_key": raw_buff_id,
                "event_name": " / ".join(labels) if labels else buff_id,
                "packet_mapping": packet_mapping,
                "packet_classification": packet_classification,
                "semantic_candidates": semantic_candidates,
                "source_character_key": record.get("source_character_key"),
                "source_character_name": record.get("source_character_name"),
                "raw_source": record.get("raw_source"),
                "target_character_key": record.get("target_character_key") or record.get("target_enemy_key"),
                "target_character_name": record.get("target_character_name") or record.get("target_enemy_name"),
                "owner_raw": record.get("owner_raw"),
                "start_ts_ms": record.get("ts_ms"),
                "start_time": record.get("time") or _format_ts_ms(int(record.get("ts_ms") or 0)),
                "end_ts_ms": int(record.get("ts_ms") or 0) + effective_duration_ms,
                "end_time": _format_ts_ms(int(record.get("ts_ms") or 0) + effective_duration_ms),
                "raw_end_time": _format_ts_ms(int(record["end_ts_ms"])) if record.get("end_ts_ms") is not None else None,
                "raw_duration_ms": record.get("raw_duration_ms"),
                "effective_duration_ms": effective_duration_ms,
                "bb_keys": sorted(set(str(key) for key in record.get("bb_keys") or [])),
                "bb_raw": dict(record.get("bb_raw") or {}),
                "attr_mods": list(record.get("attr_mods") or []),
                "zone_effects": zone_effects,
                "dynamic_effects": dynamic_effects,
                "effect_summary": _format_effect_summary(zone_effects + dynamic_effects),
            }
        )
    return sorted(rows, key=lambda item: (int(item.get("start_ts_ms") or 0), int(item.get("line_no") or 0)))


def _record_applicable_effect(
    *,
    window: dict[str, Any],
    effect: dict[str, Any],
    scope: str,
    rdps_credit: float | None = None,
) -> dict[str, Any]:
    source_key = window.get("source_character_key")
    raw_source_key = window.get("raw_source_character_key")
    return {
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
        "zone": str(effect.get("zone") or ""),
        "zone_label": ZONE_LABELS.get(str(effect.get("zone") or ""), str(effect.get("zone") or "")),
        "element": str(effect.get("element") or "all"),
        "rate": _round4(float(effect.get("rate") or 0.0)),
        "rdps_credit": _round4(rdps_credit),
    }


def _record_dpd_self_residual(
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
        "zone_label": ZONE_LABELS.get(zone, zone),
        "element": str(hit.get("damage_element") or "all"),
        "rate": _round4(rate),
        "rdps_credit": None,
    }


def _record_baseline_self(
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
    label = _ATTR_TYPE_BUFF_LABELS.get(attr_type) or ZONE_LABELS.get(zone, zone)
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
        "zone_label": ZONE_LABELS.get(zone, zone),
        "element": element,
        "rate": _round4(rate),
        "rdps_credit": None,
        "baseline_final": _round4(final_value),
        "baseline_captured": _round4(captured),
    }


def _attach_hit_reconstruction(
    hits: list[dict[str, Any]],
    loadout: list[dict[str, Any]],
    history_phase_scalars: dict[tuple[str, str, int | None, int | None, int | None, str, int], list[float]] | None = None,
) -> None:
    loadout_by_char = {
        str(row.get("character_key") or row.get("char_key") or row.get("char") or ""): row
        for row in loadout
        if str(row.get("character_key") or row.get("char_key") or row.get("char") or "")
    }

    scalar_rows: defaultdict[tuple[str, str, int | None, int | None, str | None, str, str, str, int], list[float]] = defaultdict(list)
    phase_scalar_rows: defaultdict[tuple[str, str, int | None, int | None, int | None, str, str, str, int], list[float]] = defaultdict(list)
    phase_signature_order: defaultdict[tuple[str, str], list[tuple[int | None, int | None, int | None]]] = defaultdict(list)

    def _stable_scalar(values: list[float]) -> tuple[float | None, float | None]:
        if not values:
            return None, None
        med = median(values)
        if med <= 0:
            return None, None
        spread = (max(values) - min(values)) / med if len(values) > 1 else 0.0
        if spread > 0.15:
            return None, spread
        return med, spread

    for hit in hits:
        character_key = str(hit.get("character_key") or "")
        loadout_row = loadout_by_char.get(character_key)
        if not isinstance(loadout_row, dict):
            hit["reconstruction"] = None
            continue

        try:
            character_level = int(loadout_row.get("character_level") or 0)
        except (TypeError, ValueError):
            character_level = 0

        base_stats = _character_base_stats(character_key, character_level)
        character_base_atk = None
        character_level_source = None
        if isinstance(base_stats, dict):
            try:
                character_base_atk = float(base_stats.get("atk")) if base_stats.get("atk") is not None else None
            except (TypeError, ValueError):
                character_base_atk = None
            character_level_source = base_stats.get("level_source")
            if not character_level and base_stats.get("level") is not None:
                try:
                    character_level = int(base_stats.get("level"))
                except (TypeError, ValueError):
                    pass

        weapon_base_atk = None
        try:
            if loadout_row.get("weapon_base_atk") is not None:
                weapon_base_atk = float(loadout_row.get("weapon_base_atk"))
        except (TypeError, ValueError):
            weapon_base_atk = None

        known_base_atk = None
        if character_base_atk is not None and weapon_base_atk is not None:
            known_base_atk = character_base_atk + weapon_base_atk

        panel_estimate = _estimate_visible_panel_attack(character_key, loadout_row, base_stats)
        attack_input = None
        if isinstance(panel_estimate, dict):
            try:
                attack_input = float(panel_estimate.get("panel_attack_estimate") or 0.0)
            except (TypeError, ValueError):
                attack_input = None
        if not attack_input and known_base_atk:
            attack_input = known_base_atk

        total_multiplier = 1.0
        zone_signature_parts: list[str] = []
        for zone in hit.get("zones") or []:
            try:
                zone_multiplier = float(zone.get("total_multiplier") or 1.0)
            except (TypeError, ValueError):
                zone_multiplier = 1.0
            if zone_multiplier > 0:
                total_multiplier *= zone_multiplier
            zone_signature_parts.append(
                f"{zone.get('zone')}:{zone.get('self_rate')}:{zone.get('external_rate')}"
            )
        zone_signature = "|".join(sorted(zone_signature_parts))

        crit_multiplier = 1.0
        if int(hit.get("crit_flag") or 0):
            crit_value = hit.get("crit_dmg")
            try:
                crit_float = float(crit_value)
            except (TypeError, ValueError):
                crit_float = -1.0
            if crit_float >= 0:
                crit_multiplier = 1.0 + crit_float
            else:
                crit_multiplier = 1.5

        implied_scalar = None
        packet_modifier_uids = hit.get("packet_modifier_uids") if isinstance(hit.get("packet_modifier_uids"), dict) else {}
        attacker_uid_signature = ",".join(sorted(str(item) for item in packet_modifier_uids.get("attacker") or [] if str(item)))
        packet_attr_details = hit.get("packet_attr_details") if isinstance(hit.get("packet_attr_details"), dict) else {}
        defender_attr_signature = ",".join(str(item) for item in packet_attr_details.get("defender") or [] if str(item))
        packet_modifier_details = hit.get("packet_modifier_details") if isinstance(hit.get("packet_modifier_details"), list) else []
        attacker_modifier_event_signature = ",".join(
            sorted(
                {
                    str(row.get("event_key") or "")
                    for row in packet_modifier_details
                    if isinstance(row, dict) and str(row.get("side") or "") == "attacker" and str(row.get("event_key") or "")
                }
            )
        )
        defender_modifier_event_signature = ",".join(
            sorted(
                {
                    str(row.get("event_key") or "")
                    for row in packet_modifier_details
                    if isinstance(row, dict) and str(row.get("side") or "") == "defender" and str(row.get("event_key") or "")
                }
            )
        )
        phase_signature = (
            int(hit.get("template_int_id") or 0) or None,
            int(hit.get("action_id") or 0) or None,
            int(hit.get("original_template_int_id") or 0) or None,
        )
        phase_order_key = (character_key, str(hit.get("skill_key") or ""))
        if phase_signature not in phase_signature_order[phase_order_key]:
            phase_signature_order[phase_order_key].append(phase_signature)
        if attack_input and attack_input > 0 and total_multiplier > 0 and crit_multiplier:
            implied_scalar = float(hit.get("hit_value") or 0.0) / (attack_input * total_multiplier * crit_multiplier)
            group_key = (
                character_key,
                str(hit.get("skill_key") or ""),
                int(hit.get("skill_level") or 0) or None,
                int(hit.get("action_id") or 0) or None,
                str(hit.get("dynamic_bb_signature") or "") or None,
                attacker_uid_signature,
                defender_attr_signature,
                zone_signature,
                1 if int(hit.get("crit_flag") or 0) else 0,
            )
            if implied_scalar > 0:
                scalar_rows[group_key].append(implied_scalar)
                phase_group_key = (
                    character_key,
                    str(hit.get("skill_key") or ""),
                    int(hit.get("skill_level") or 0) or None,
                    phase_signature[0],
                    phase_signature[1],
                    attacker_modifier_event_signature,
                    defender_modifier_event_signature,
                    zone_signature,
                    1 if int(hit.get("crit_flag") or 0) else 0,
                )
                phase_scalar_rows[phase_group_key].append(implied_scalar)

        hit["reconstruction"] = {
            "character_level": character_level or None,
            "character_level_source": character_level_source,
            "character_base_atk": _round4(character_base_atk),
            "weapon_base_atk": _round4(weapon_base_atk),
            "known_base_atk": _round4(known_base_atk),
            "panel_attack_estimate": _round4(panel_estimate.get("panel_attack_estimate")) if isinstance(panel_estimate, dict) else None,
            "attack_input": _round4(attack_input),
            "atk_pct_bonus": _round4(panel_estimate.get("atk_pct_bonus")) if isinstance(panel_estimate, dict) else None,
            "flat_atk_bonus": _round4(panel_estimate.get("flat_atk_bonus")) if isinstance(panel_estimate, dict) else None,
            "main_attr_total": _round4(panel_estimate.get("main_attr_total")) if isinstance(panel_estimate, dict) else None,
            "sub_attr_total": _round4(panel_estimate.get("sub_attr_total")) if isinstance(panel_estimate, dict) else None,
            "ability_bonus_multiplier": _round4(panel_estimate.get("ability_bonus_multiplier")) if isinstance(panel_estimate, dict) else None,
            "visible_total_multiplier": _round4(total_multiplier),
            "crit_multiplier": _round4(crit_multiplier) if crit_multiplier is not None else None,
            "implied_scalar": _round4(implied_scalar),
            "predicted_hit": None,
            "predicted_error": None,
            "predicted_error_pct": None,
            "learned_scalar": None,
            "learned_scalar_group_size": 0,
            "learned_scalar_source": None,
            "attacker_uid_signature": attacker_uid_signature or None,
            "defender_attr_signature": defender_attr_signature or None,
            "attacker_modifier_event_signature": attacker_modifier_event_signature or None,
            "defender_modifier_event_signature": defender_modifier_event_signature or None,
            "zone_signature": zone_signature or None,
            "runtime_phase_signature": {
                "template_int_id": phase_signature[0],
                "action_id": phase_signature[1],
                "original_template_int_id": phase_signature[2],
            },
            "runtime_phase_label": None,
            "phase_predicted_hit": None,
            "phase_predicted_error": None,
            "phase_predicted_error_pct": None,
            "phase_learned_scalar": None,
            "phase_learned_scalar_group_size": 0,
        }

    for hit in hits:
        reconstruction = hit.get("reconstruction")
        if not isinstance(reconstruction, dict):
            continue
        phase_signature = reconstruction.get("runtime_phase_signature") if isinstance(reconstruction.get("runtime_phase_signature"), dict) else {}
        phase_order_key = (str(hit.get("character_key") or ""), str(hit.get("skill_key") or ""))
        phase_tuple = (
            phase_signature.get("template_int_id"),
            phase_signature.get("action_id"),
            phase_signature.get("original_template_int_id"),
        )
        if phase_tuple in phase_signature_order.get(phase_order_key, []):
            reconstruction["runtime_phase_label"] = f"P{phase_signature_order[phase_order_key].index(phase_tuple) + 1}"
        group_key = (
            str(hit.get("character_key") or ""),
            str(hit.get("skill_key") or ""),
            int(hit.get("skill_level") or 0) or None,
            int(hit.get("action_id") or 0) or None,
            str(hit.get("dynamic_bb_signature") or "") or None,
            str(reconstruction.get("attacker_uid_signature") or ""),
            str(reconstruction.get("defender_attr_signature") or ""),
            str(reconstruction.get("zone_signature") or ""),
            1 if int(hit.get("crit_flag") or 0) else 0,
        )
        original_values = list(scalar_rows.get(group_key) or [])
        values = list(original_values)
        implied_scalar = reconstruction.get("implied_scalar")
        if implied_scalar not in (None, 0) and len(values) > 1:
            try:
                current_value = float(implied_scalar)
                remove_index = min(range(len(values)), key=lambda index: abs(values[index] - current_value))
                values.pop(remove_index)
            except (TypeError, ValueError):
                pass
        learned_scalar = median(values) if len(values) >= 1 and len(original_values) > 1 else None
        reconstruction["learned_scalar"] = _round4(learned_scalar)
        reconstruction["learned_scalar_group_size"] = len(values)
        reconstruction["learned_scalar_source"] = "same_skill_leave_one_out" if learned_scalar is not None else None
        phase_group_key = (
            str(hit.get("character_key") or ""),
            str(hit.get("skill_key") or ""),
            int(hit.get("skill_level") or 0) or None,
            phase_signature.get("template_int_id"),
            phase_signature.get("action_id"),
            str(reconstruction.get("attacker_modifier_event_signature") or ""),
            str(reconstruction.get("defender_modifier_event_signature") or ""),
            str(reconstruction.get("zone_signature") or ""),
            1 if int(hit.get("crit_flag") or 0) else 0,
        )
        phase_original_values = list(phase_scalar_rows.get(phase_group_key) or [])
        phase_values = list(phase_original_values)
        if implied_scalar not in (None, 0) and len(phase_values) > 1:
            try:
                current_value = float(implied_scalar)
                remove_index = min(range(len(phase_values)), key=lambda index: abs(phase_values[index] - current_value))
                phase_values.pop(remove_index)
            except (TypeError, ValueError):
                pass
        phase_learned_scalar, phase_spread = _stable_scalar(phase_values) if len(phase_original_values) > 1 else (None, None)
        if phase_learned_scalar is None and history_phase_scalars:
            history_values = list(history_phase_scalars.get(phase_group_key) or [])
            phase_learned_scalar, phase_spread = _stable_scalar(history_values)
            if phase_learned_scalar is not None:
                reconstruction["phase_learned_scalar_group_size"] = len(history_values)
                reconstruction["phase_learned_scalar_source"] = "historical_phase"
            else:
                reconstruction["phase_learned_scalar_group_size"] = len(phase_values)
                reconstruction["phase_learned_scalar_source"] = None
        else:
            reconstruction["phase_learned_scalar_group_size"] = len(phase_values)
            reconstruction["phase_learned_scalar_source"] = "same_file_phase_leave_one_out" if phase_learned_scalar is not None else None
        reconstruction["phase_learned_scalar"] = _round4(phase_learned_scalar)
        reconstruction["phase_learned_scalar_spread"] = _round4(phase_spread)
        attack_input = reconstruction.get("attack_input")
        visible_total_multiplier = reconstruction.get("visible_total_multiplier")
        crit_multiplier = reconstruction.get("crit_multiplier")
        actual_hit = float(hit.get("hit_value") or 0.0)
        prediction_source = None
        predicted_hit = None
        error = None
        if (
            attack_input not in (None, 0)
            and visible_total_multiplier not in (None, 0)
            and crit_multiplier not in (None, 0)
        ):
            if learned_scalar is not None:
                predicted_hit = float(attack_input) * float(visible_total_multiplier) * float(crit_multiplier) * float(learned_scalar)
                prediction_source = "exact_leave_one_out"
            elif phase_learned_scalar is not None:
                predicted_hit = float(attack_input) * float(visible_total_multiplier) * float(crit_multiplier) * float(phase_learned_scalar)
                prediction_source = "phase_leave_one_out"
            if predicted_hit is not None:
                error = predicted_hit - actual_hit
        reconstruction["predicted_hit"] = _round4(predicted_hit)
        reconstruction["predicted_error"] = _round4(error)
        reconstruction["predicted_error_pct"] = _round4((error / actual_hit) if actual_hit and error is not None else None)
        reconstruction["predicted_source"] = prediction_source
        if (
            phase_learned_scalar is not None
            and attack_input not in (None, 0)
            and visible_total_multiplier not in (None, 0)
            and crit_multiplier not in (None, 0)
        ):
            phase_predicted_hit = float(attack_input) * float(visible_total_multiplier) * float(crit_multiplier) * float(phase_learned_scalar)
            phase_error = phase_predicted_hit - actual_hit
            reconstruction["phase_predicted_hit"] = _round4(phase_predicted_hit)
            reconstruction["phase_predicted_error"] = _round4(phase_error)
            reconstruction["phase_predicted_error_pct"] = _round4((phase_error / actual_hit) if actual_hit else None)


def _reports_dir() -> Path:
    return _REPO_ROOT / "reports"


@lru_cache(maxsize=1)
def _historical_trace_files_signature() -> tuple[tuple[str, int], ...]:
    reports = _reports_dir()
    if not reports.is_dir():
        return ()
    rows: list[tuple[str, int]] = []
    for path in sorted(reports.glob("*trace*.dat")):
        try:
            rows.append((path.name, path.stat().st_mtime_ns))
        except OSError:
            continue
    return tuple(rows)


@lru_cache(maxsize=8)
def _load_historical_phase_scalars(
    exclude_file_name: str | None,
    files_signature: tuple[tuple[str, int], ...],
) -> dict[tuple[str, str, int | None, int | None, int | None, str, str, str, int], list[float]]:
    _ = files_signature
    reports = _reports_dir()
    history: defaultdict[tuple[str, str, int | None, int | None, int | None, str, str, str, int], list[float]] = defaultdict(list)
    if not reports.is_dir():
        return {}
    for path in sorted(reports.glob("*trace*.dat")):
        if exclude_file_name and path.name == exclude_file_name:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        try:
            report = parse_hit_debug_log_text(text, file_name=path.name, _allow_history=False)
        except Exception:
            continue
        for hit in report.get("hits") or []:
            reconstruction = hit.get("reconstruction")
            if not isinstance(reconstruction, dict):
                continue
            implied_scalar = reconstruction.get("implied_scalar")
            if implied_scalar in (None, 0):
                continue
            try:
                scalar = float(implied_scalar)
            except (TypeError, ValueError):
                continue
            key = (
                str(hit.get("character_key") or ""),
                str(hit.get("skill_key") or ""),
                int(hit.get("skill_level") or 0) or None,
                int(hit.get("template_int_id") or 0) or None,
                int(hit.get("action_id") or 0) or None,
                str(reconstruction.get("attacker_modifier_event_signature") or ""),
                str(reconstruction.get("defender_modifier_event_signature") or ""),
                str(reconstruction.get("zone_signature") or ""),
                1 if int(hit.get("crit_flag") or 0) else 0,
            )
            history[key].append(scalar)
    return {key: list(values) for key, values in history.items()}


def _explain_hit(
    hit: dict[str, Any],
    buff_windows: list[dict[str, Any]],
    buff_records_by_uid: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    allocation = _allocate_rdps_for_hit(
        hit,
        buff_windows,
        include_debug=True,
        buff_records_by_uid=buff_records_by_uid,
    )
    hit["zones"] = allocation.get("zones") or []
    hit["ignored_effects"] = allocation.get("ignored_effects") or []
    hit["product_external_multiplier"] = allocation.get("product_external_multiplier")
    hit["attacker_share"] = allocation.get("attacker_share")
    hit["external_pool"] = allocation.get("external_pool")
    hit["rdps_contributions"] = allocation.get("contributions_list") or []
    hit["external_sources"] = allocation.get("external_sources") or []
    hit["zone_summary"] = str(allocation.get("zone_summary") or "")
    hit["buff_source_summary"] = str(allocation.get("buff_source_summary") or "")
    hit["packet_modifier_uids"] = allocation.get("packet_modifier_uids") or {"attacker": [], "defender": []}
    hit["packet_modifier_details"] = allocation.get("packet_modifier_details") or []
    return hit


def parse_hit_debug_log_text(
    text: str,
    *,
    file_name: str | None = None,
    first_hit_hint: str | None = None,
    last_hit_hint: str | None = None,
    _allow_history: bool = True,
) -> dict[str, Any]:
    """Parse a raw battle log into per-hit multiplier and buff-source details."""

    loadout = _extract_loadout_from_text(text)
    context_enemy_hint = _infer_context_enemy_hint(text)
    active_suits_by_char, active_weapons_by_char = _active_loadout_maps_from_rows(loadout)
    loadout_skill_ids_by_char = _loadout_skill_ids_by_char(loadout)
    first_hit_hint_ms = _parse_hint_timestamp_ms(first_hit_hint)
    last_hit_hint_ms = _parse_hint_timestamp_ms(last_hit_hint)

    hits: list[dict[str, Any]] = []
    hits_by_seq: dict[int, dict[str, Any]] = {}
    baseline_by_character: dict[str, dict[int, float]] = {}
    buff_starts: list[dict[str, Any]] = []
    enemy_counter: Counter[str] = Counter()
    last_enemy_hp_by_target: dict[str, int] = {}
    participant_totals: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "character_key": None,
            "character_name": None,
            "total_damage": 0,
            "hit_count": 0,
        }
    )
    active_buff_starts_by_uid: dict[str, dict[str, Any]] = {}
    buff_start_index_by_uid_ts: dict[tuple[str, int], int] = {}
    packet_modifier_last_seen_by_uid: dict[str, int] = {}
    pending_attr_mods: dict[str, list[dict[str, Any]]] = defaultdict(list)
    pending_buff_record: dict[str, Any] | None = None
    last_chr_src_on_owner: dict[str, tuple[str, int]] = {}
    recent_actor_maps_by_char: dict[str, list[dict[str, Any]]] = defaultdict(list)
    recent_skill_casts_by_char: dict[str, list[dict[str, Any]]] = defaultdict(list)
    skill_casts: list[dict[str, Any]] = []
    active_skill_casts_by_inst: dict[str, dict[str, Any]] = {}
    recent_numeric_buffs_by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    party_actor_ids: set[str] = set()
    dungeon_context: tuple[str, str] | None = None
    dungeon_context_id: str | None = None

    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        ts_ms = _parse_prefixed_timestamp_ms(raw_line)
        if ts_ms is None:
            continue
        party_actor_ids.update(_collect_party_actor_ids(raw_line))

        if any(
            marker in raw_line
            for marker in (
                " DUNGEON_CONTEXT ",
                " BATTLE_RESULT ",
                " CONTRACT_TAGS ",
                " OFFICIAL_TIMER_START ",
                " OFFICIAL_TIMER_END ",
            )
        ):
            fields = _extract_fields(raw_line)
            raw_dungeon_id = (
                fields.get("dungeonId")
                or fields.get("dungeon_id")
                or fields.get("gameId")
                or fields.get("game_id")
            )
            if raw_dungeon_id:
                dungeon_context_id = str(raw_dungeon_id).strip()
                dungeon_context = _resolve_dungeon_context(dungeon_context_id)

        if _ACTOR_MAP_RE.search(raw_line):
            fields = _extract_fields(raw_line)
            actor_skill = str(fields.get("skill") or "")
            actor_character_key = _extract_character_key(fields.get("template"), actor_skill)
            if actor_character_key:
                rows = recent_actor_maps_by_char[actor_character_key]
                rows.append(
                    {
                        "line_no": line_no,
                        "ts_ms": ts_ms,
                        "time": _format_ts_ms(ts_ms),
                        "actor_id": fields.get("id"),
                        "template": fields.get("template"),
                        "source": fields.get("source"),
                        "skill": actor_skill,
                    }
                )
                del rows[:-16]
            continue

        if " SKILL_CAST_START " in raw_line:
            fields = _extract_fields(raw_line)
            cast_skill = str(fields.get("skill") or "")
            cast_character_key = _extract_character_key(fields.get("owner"), cast_skill)
            cast_record = {
                "line_no": line_no,
                "ts_ms": ts_ms,
                "time": _format_ts_ms(ts_ms),
                "owner": fields.get("owner"),
                "skill_inst_id": fields.get("inst"),
                "skill": cast_skill,
                "source_character_key": cast_character_key,
                "end_ts_ms": None,
            }
            skill_casts.append(cast_record)
            inst_key = str(cast_record.get("skill_inst_id") or "")
            if inst_key:
                active_skill_casts_by_inst[inst_key] = cast_record
            if cast_character_key:
                rows = recent_skill_casts_by_char[cast_character_key]
                rows.append(
                    {
                        "line_no": line_no,
                        "ts_ms": ts_ms,
                        "time": _format_ts_ms(ts_ms),
                        "owner": fields.get("owner"),
                        "skill_inst_id": fields.get("inst"),
                        "skill": cast_skill,
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

        if " BB[" in raw_line:
            if pending_buff_record is not None:
                parsed_bb_fields = _extract_fields(raw_line)
                pending_buff_record["bb_keys"].extend(parsed_bb_fields.keys())
                pending_buff_record["bb_raw"].update(parsed_bb_fields)
                for key, raw_value in parsed_bb_fields.items():
                    rate = _safe_positive_rate(raw_value)
                    if rate is not None:
                        pending_buff_record["bb_values"][key] = rate
                _apply_enemy_target_bb_duration_override(pending_buff_record)
                _preserve_raw_numeric_internal_trigger_buff_id(pending_buff_record)
            continue

        dpd_raw = _parse_dpd_raw_line(raw_line)
        if dpd_raw is not None:
            hit = hits_by_seq.get(int(dpd_raw["seq"]))
            if hit is not None:
                dpd_payload = {key: value for key, value in dpd_raw.items() if key != "seq"}
                dpd_payload["line_no"] = line_no
                hit["dpd_raw"] = dpd_payload
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
                    "raw_fields": dict(fields),
                    "line_no": line_no,
                }
            )

        if " HP_V2 " in raw_line:
            fields = _extract_fields(raw_line)
            character_key = _extract_character_key(fields.get("src"), fields.get("atk"), fields.get("skill"))
            target_enemy_key = _extract_enemy_key(fields.get("tgt"), fields.get("skill"))
            if target_enemy_key is None:
                target_enemy_key = _recover_enemy_target_from_mislabeled_actor(
                    fields,
                    context_enemy_hint=context_enemy_hint,
                    party_actor_ids=party_actor_ids,
                )
            if character_key is None or target_enemy_key is None:
                continue

            seq_match = _HIT_SEQ_RE.search(raw_line)
            seq = int(seq_match.group(1)) if seq_match else len(hits) + 1
            enemy_counter[target_enemy_key] += 1

            character_name = _resolve_character_name(character_key) or character_key
            skill_key = fields.get("skill") or "unknown_skill"
            damage_element = _infer_skill_damage_element(skill_key, character_key)

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

            raw_skill_key = skill_key
            skill_mapping = _skill_mapping_info(
                raw_skill_key,
                character_key=character_key,
                target_enemy_key=target_enemy_key,
                damage_element=damage_element,
                original_template_int_id=_coerce_int(fields.get("origTemplateIntId"), default=0) or None,
                ts_ms=ts_ms,
                recent_actor_maps_by_char=recent_actor_maps_by_char,
                recent_skill_casts_by_char=recent_skill_casts_by_char,
                recent_numeric_buffs_by_source=recent_numeric_buffs_by_source,
                loadout_skill_ids_by_char=loadout_skill_ids_by_char,
            )
            effective_skill_key = str(skill_mapping.get("canonical_skill_id") or raw_skill_key)
            skill_profile = _resolve_skill_profile(effective_skill_key)
            skill_group_type = None
            skill_family_key = _resolve_skill_family_key(effective_skill_key, skill_profile)
            if skill_profile is not None:
                try:
                    skill_group_type = int(skill_profile.get("group_type"))
                except (TypeError, ValueError):
                    skill_group_type = None
            action_id = _coerce_int(fields.get("actionId"), default=0) or None
            damage_unit_index = _coerce_int(fields.get("damageUnitIndex"), default=0)
            action_damage_element = _infer_skill_action_damage_element(
                effective_skill_key,
                action_id,
                damage_unit_index,
            )
            damage_element = action_damage_element or _infer_skill_damage_element(effective_skill_key, character_key) or damage_element
            if action_damage_element:
                damage_school = _damage_school_from_element(action_damage_element) or _infer_skill_damage_school(
                    effective_skill_key,
                    character_key,
                    raw_skill_key=raw_skill_key,
                )
            else:
                damage_school = _infer_skill_damage_school(
                    effective_skill_key,
                    character_key,
                    raw_skill_key=raw_skill_key,
                ) or _damage_school_from_element(damage_element)
            hit = {
                "seq": seq,
                "line_no": line_no,
                "ts_ms": ts_ms,
                "time": _format_ts_ms(ts_ms),
                "character_key": character_key,
                "character_name": character_name,
                "target_enemy_key": target_enemy_key,
                "target_enemy_name": _resolve_enemy_name(target_enemy_key) or target_enemy_key,
                "raw_skill_key": raw_skill_key,
                "skill_key": effective_skill_key,
                "skill_name": str(
                    skill_mapping.get("display_name")
                    or skill_mapping.get("candidate_display_name")
                    or _resolve_skill_name(effective_skill_key)
                    or _resolve_skill_name(raw_skill_key)
                    or raw_skill_key
                ),
                "skill_mapping": skill_mapping,
                "skill_level": _coerce_int(fields.get("skillLv"), default=0) or None,
                "template_int_id": _coerce_int(fields.get("templateIntId"), default=0) or None,
                "action_id": action_id,
                "damage_unit_index": damage_unit_index,
                "original_template_int_id": _coerce_int(fields.get("origTemplateIntId"), default=0) or None,
                "dynamic_bb_signature": fields.get("dynBB"),
                "skill_group_type": skill_group_type,
                "skill_family_key": skill_family_key,
                "damage_element": damage_element,
                "damage_school": damage_school,
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
                "raw_damage": _coerce_float(fields.get("raw")),
                "cum_damage": _coerce_int(fields.get("cum")),
                "hit_index": _coerce_int(fields.get("hits"), default=1),
                "crit_flag": _coerce_int(fields.get("critFlag")),
                "crit_dmg": _coerce_float(fields.get("critDmg")),
                "src_raw": fields.get("src"),
                "tgt_raw": fields.get("tgt"),
                "atk_raw": fields.get("atk"),
                "shared": _coerce_int(fields.get("shared")),
                "raw_line": raw_line,
                "dpd_raw": None,
                "baseline": baseline_by_character.get(character_key),
                "packet_modifier_seen": False,
                "packet_modifier_uids": {"attacker": [], "defender": []},
                "packet_attr_details": {"attacker": [], "defender": []},
            }
            hits.append(hit)
            hits_by_seq[seq] = hit

            participant = participant_totals[character_key]
            participant["character_key"] = character_key
            participant["character_name"] = character_name
            participant["total_damage"] += hit["hit_value"]
            participant["hit_count"] += 1

        elif " BUFF_START " in raw_line:
            fields = _extract_fields(raw_line)
            owner_value = str(fields.get("owner") or "")
            src_value = str(fields.get("src") or "")
            owner_key = _extract_character_key(owner_value)
            target_enemy_key = _extract_enemy_key(owner_value)
            raw_buff_key = _normalize_buff_id(fields.get("id"))
            raw_source_key = _extract_character_key(src_value, raw_buff_key)
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
                source_key = _extract_character_key(src_value, buff_key)
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

            if not source_key and not owner_key:
                pending_buff_record = None
                continue

            attr_mods = pending_attr_mods.pop(buff_key, [])
            if not attr_mods and raw_buff_key != buff_key:
                attr_mods = pending_attr_mods.pop(raw_buff_key, [])
            buff_record = {
                "uid": str(fields.get("uid") or ""),
                "line_no": line_no,
                "ts_ms": ts_ms,
                "time": _format_ts_ms(ts_ms),
                "source_character_key": source_key,
                "source_character_name": _resolve_character_name(source_key) or source_key,
                "raw_source_character_key": raw_source_key,
                "raw_source_character_name": _resolve_character_name(raw_source_key) or raw_source_key,
                "raw_source": src_value,
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
                "bb_raw": {},
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

    if not hits:
        raise ValueError("未在日志中解析到任何 HP_V2 伤害事件。")

    _extend_buff_records_from_packet_modifiers(buff_starts, packet_modifier_last_seen_by_uid)
    _infer_related_buff_end_times(buff_starts, skill_casts)
    _apply_same_frame_trigger_skill_mappings(hits, buff_starts)
    first_hit_ms = first_hit_hint_ms if first_hit_hint_ms is not None else int(hits[0]["ts_ms"])
    last_hit_ms = last_hit_hint_ms if last_hit_hint_ms is not None else int(hits[-1]["ts_ms"])
    if last_hit_ms < first_hit_ms:
        last_hit_ms += 24 * 60 * 60 * 1000

    buff_windows = _build_buff_windows(
        hits,
        buff_starts,
        battle_end_ms=last_hit_ms,
        active_suits_by_char=active_suits_by_char,
        active_weapons_by_char=active_weapons_by_char,
    )
    _infer_missing_hit_damage_schools(hits, buff_windows)
    static_entries_by_char: dict[str, list[dict[str, Any]]] = {}
    for row in loadout:
        if not isinstance(row, dict):
            continue
        entries = _derive_static_self_multiplier_entries(row)
        row["static_multiplier_entries"] = entries
        static_entries_by_char[str(row.get("character_key") or "")] = entries
    for hit in hits:
        hit["static_multiplier_entries"] = static_entries_by_char.get(str(hit.get("character_key") or ""), [])
        if not hit.get("damage_element"):
            hit["damage_element"] = _damage_element_from_dpd_raw(hit.get("dpd_raw"))
    _annotate_hit_enemy_hp_state(hits)
    buff_records_by_uid = _build_buff_record_index(buff_starts)
    buff_audit = _build_buff_audit_rows(buff_starts, battle_end_ms=last_hit_ms, included_windows=buff_windows)
    explained_hits = [_explain_hit(hit, buff_windows, buff_records_by_uid) for hit in hits]
    history_phase_scalars = (
        _load_historical_phase_scalars(file_name, _historical_trace_files_signature())
        if _allow_history
        else {}
    )
    _attach_hit_reconstruction(explained_hits, loadout, history_phase_scalars)

    boss_key = enemy_counter.most_common(1)[0][0] if enemy_counter else "unknown_boss"
    boss_name = _resolve_enemy_name(boss_key) or boss_key
    dungeon_key, dungeon_name = dungeon_context or (UNKNOWN_DUNGEON_KEY, UNKNOWN_DUNGEON_NAME)
    duration_ms = max(last_hit_ms - first_hit_ms, 1)
    total_damage = sum(int(hit["hit_value"]) for hit in hits)

    participants = [
        {
            "character_key": key,
            "character_name": value.get("character_name") or key,
            "total_damage": value.get("total_damage") or 0,
            "hit_count": value.get("hit_count") or 0,
        }
        for key, value in participant_totals.items()
    ]
    participants.sort(key=lambda item: (-int(item["total_damage"]), str(item["character_name"])))

    return {
        "summary": {
            "file_name": file_name,
            "hit_count": len(explained_hits),
            "buff_window_count": len(buff_windows),
            "buff_audit_count": len(buff_audit),
            "buff_audit_included_count": sum(1 for row in buff_audit if row.get("status") == "included"),
            "buff_audit_filtered_count": sum(1 for row in buff_audit if row.get("status") == "filtered"),
            "buff_audit_merged_count": sum(1 for row in buff_audit if row.get("status") == "merged"),
            "dpd_count": sum(1 for hit in explained_hits if hit.get("dpd_raw")),
            "baseline_count": sum(1 for hit in explained_hits if hit.get("baseline")),
            "external_buff_hit_count": sum(1 for hit in explained_hits if hit.get("external_sources")),
            "first_hit_ms": first_hit_ms,
            "first_hit_time": _format_ts_ms(first_hit_ms),
            "last_hit_ms": last_hit_ms,
            "last_hit_time": _format_ts_ms(last_hit_ms),
            "duration_ms": duration_ms,
            "total_damage": total_damage,
            "total_dps": round(total_damage / (duration_ms / 1000), 2),
            "boss_key": boss_key,
            "boss_name": boss_name,
            "dungeon_key": dungeon_key,
            "dungeon_name": dungeon_name,
            "dungeon_context_id": dungeon_context_id,
            "dungeon_identity_source": (
                "dungeon_context"
                if dungeon_context is not None
                else "unmapped_dungeon_context"
                if dungeon_context_id
                else "missing_dungeon_context"
            ),
        },
        "participants": participants,
        "loadout": loadout,
        "hits": explained_hits,
        "buff_windows": buff_windows,
        "buff_audit": buff_audit,
    }
