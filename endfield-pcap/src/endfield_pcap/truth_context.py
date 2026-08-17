from __future__ import annotations

import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .runtime_paths import bundle_root


def default_truth_log_file() -> Path:
    return Path(os.environ.get("TEMP", ".")) / "endfield_truth_dump.log"


def default_truth_jsonl_file() -> Path:
    return Path(os.environ.get("TEMP", ".")) / "endfield_truth_dump.jsonl"


def default_truth_db_file() -> Path:
    return bundle_root().resolve().parent / "endfield-dump" / "database" / "runtime_truth_db.json"


_LOADOUT_LINE_RE = re.compile(
    r"\bLOADOUT\s+slot=(?P<slot>\d+)\s+char=(?P<char>\S+).*?"
    r"template=(?P<template>\S+)\s+potential=(?P<potential>-?\d+)\s+"
    r"weaponInstId=(?P<weapon_inst>-?\d+)\s+weaponTemplate=(?P<weapon_template>\S+)\s+"
    r"weaponLv=(?P<weapon_lv>-?\d+)\s+refine=(?P<refine>-?\d+)\s+break=(?P<breakthrough>-?\d+)\s+"
    r"attachedGem=(?P<attached_gem>-?\d+)"
)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _split_top_level(text: str, sep: str = " ") -> list[str]:
    parts: list[str] = []
    depth = 0
    start = 0
    for index, char in enumerate(text):
        if char == "{":
            depth += 1
        elif char == "}":
            depth = max(0, depth - 1)
        elif char == sep and depth == 0:
            chunk = text[start:index].strip()
            if chunk:
                parts.append(chunk)
            start = index + 1
    tail = text[start:].strip()
    if tail:
        parts.append(tail)
    return parts


def _braced_field(raw_line: str, field_name: str) -> str | None:
    marker = f"{field_name}={{"
    start = raw_line.find(marker)
    if start < 0:
        return None
    index = start + len(marker)
    depth = 1
    result: list[str] = []
    while index < len(raw_line):
        char = raw_line[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return "".join(result)
        result.append(char)
        index += 1
    return None


def _parse_truth_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _parse_truth_loadout_lines(path: Path) -> dict[str, dict[str, Any]]:
    latest_by_char: dict[str, dict[str, Any]] = {}
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        match = _LOADOUT_LINE_RE.search(raw_line)
        if not match:
            continue
        char_key = match.group("char")
        latest_by_char[char_key] = {
            "slot": int(match.group("slot")),
            "character_key": char_key,
            "template": match.group("template"),
            "potential": int(match.group("potential")),
            "weapon_inst_id": int(match.group("weapon_inst")),
            "weapon_template": match.group("weapon_template"),
            "weapon_level": int(match.group("weapon_lv")),
            "weapon_refine": int(match.group("refine")),
            "weapon_break": int(match.group("breakthrough")),
            "attached_gem_inst_id": int(match.group("attached_gem")),
            "equip_insts_raw": _braced_field(raw_line, "equipInsts") or "",
            "equips_raw": _braced_field(raw_line, "equips") or "",
            "equip_suit_raw": _braced_field(raw_line, "equipSuit") or "",
        }
    return latest_by_char


def _parse_equip_inst_ids(raw: str) -> list[dict[str, Any]]:
    return [
        {"slot": int(slot), "inst_id": int(inst_id)}
        for slot, inst_id in re.findall(r"\[(\d+)\]=(\d+)", raw or "")
    ]


def _parse_equip_levels(raw: str | None) -> list[dict[str, int]]:
    levels: list[dict[str, int]] = []
    for index, level in re.findall(r"(\d+):(\d+)", raw or ""):
        levels.append({"index": int(index), "level": int(level)})
    return levels


def _parse_equip_templates(raw: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for token in _split_top_level(raw or "", " "):
        if "=" not in token:
            continue
        left, right = token.split("=", 1)
        slot_match = re.search(r"\[(\d+)\]", left)
        slot = int(slot_match.group(1)) if slot_match else 0
        item_id, _, suffix = right.partition("|")
        level_match = re.search(r"\|lv=([^|]+)", "|" + suffix if suffix else "")
        items.append(
            {
                "slot": slot,
                "item_id": item_id.strip(),
                "enhance_levels": _parse_equip_levels(level_match.group(1) if level_match else None),
                "raw_suffix": suffix,
            }
        )
    return items


def _parse_suit_counts(raw: str) -> list[dict[str, Any]]:
    return [
        {"suit_id": suit_id, "piece_count": int(count)}
        for suit_id, count in re.findall(r"\[([^\]]+)\]=(\d+)", raw or "")
    ]


def _load_character_catalog(root: Path) -> dict[str, dict[str, Any]]:
    manifest = _read_json(root / "data" / "akedata" / "character" / "manifest.json")
    return {
        str(entry.get("charId")): entry
        for entry in manifest
        if entry.get("charId")
    }


def _load_weapon_catalog(root: Path) -> dict[str, dict[str, Any]]:
    items_root = root / "data" / "akedata" / "weapon" / "items"
    catalog: dict[str, dict[str, Any]] = {}
    for path in items_root.glob("*.json"):
        payload = _read_json(path)
        weapon_id = str(payload.get("weaponId") or path.stem)
        catalog[weapon_id] = payload
    return catalog


def _load_equip_catalog(root: Path) -> dict[str, dict[str, Any]]:
    items_root = root / "data" / "akedata" / "equip" / "items"
    catalog: dict[str, dict[str, Any]] = {}
    for path in items_root.glob("*.json"):
        payload = _read_json(path)
        suit_id = str(payload.get("suitID") or path.stem)
        suit_name = str(payload.get("套组名称") or payload.get("name") or suit_id)
        suit_values = payload.get("value") if isinstance(payload.get("value"), dict) else {}
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
                "suit_values": suit_values,
                "part_name": str(item.get("部位") or ""),
                "rarity": item.get("rarity"),
                "main_attr": item.get("主词条") if isinstance(item.get("主词条"), dict) else None,
                "sub_attrs": item.get("副词条") if isinstance(item.get("副词条"), dict) else {},
            }
    return catalog


def _load_buff_manifest(root: Path) -> dict[str, dict[str, Any]]:
    manifest = _read_json(root / "data" / "akedata" / "buff" / "manifest.json")
    return {
        str(entry.get("id")): entry
        for entry in manifest
        if entry.get("id")
    }


def _load_buff_details(root: Path) -> dict[str, dict[str, Any]]:
    payload = _read_json(root / "data" / "local_semantics" / "buff" / "details.json")
    entries = payload.get("entries")
    return entries if isinstance(entries, dict) else {}


def _load_buff_hints(root: Path) -> dict[str, dict[str, Any]]:
    payload = _read_json(root / "data" / "local_semantics" / "classifier_hints.json")
    hints = payload.get("buffHints")
    return hints if isinstance(hints, dict) else {}


def _load_truth_db(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    payload = _read_json(path)
    return payload if isinstance(payload, dict) else {}


def _weapon_summary(weapon: dict[str, Any], weapon_level: int | None) -> dict[str, Any]:
    base_atk_curve = weapon.get("baseAtk") if isinstance(weapon.get("baseAtk"), list) else []
    current_base_atk = None
    if weapon_level is not None and 0 < weapon_level <= len(base_atk_curve):
        current_base_atk = base_atk_curve[weapon_level - 1]
    return {
        "weapon_id": weapon.get("weaponId"),
        "weapon_name": weapon.get("title") or weapon.get("name") or weapon.get("weaponId"),
        "weapon_type": weapon.get("weapontype"),
        "rarity": weapon.get("rarity"),
        "weapon_level": weapon_level,
        "current_base_atk": current_base_atk,
        "base_atk_curve": base_atk_curve,
        "skilllist": weapon.get("skilllist") if isinstance(weapon.get("skilllist"), list) else [],
    }


def _effect_summary_from_hints(hint: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for effect in hint.get("resolvedEffectHints") or []:
        if not isinstance(effect, dict):
            continue
        rows.append(
            {
                "zone": effect.get("zone"),
                "element": effect.get("element"),
                "source": effect.get("source"),
                "confidence": effect.get("confidence"),
                "reason": effect.get("reason"),
            }
        )
    return rows


def _effect_summary_from_detail(detail: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for effect in detail.get("attributeEffects") or []:
        if not isinstance(effect, dict):
            continue
        rows.append(
            {
                "zone": "ATTRIBUTE",
                "element": effect.get("attributeTypeSlug") or effect.get("attributeTypeName") or effect.get("attributeTypeId"),
                "source": "attribute_effect",
                "confidence": "detail_raw",
                "reason": effect.get("modifyAttributeType") or effect.get("formulaItem"),
            }
        )
    for effect in detail.get("damageEffects") or []:
        if not isinstance(effect, dict):
            continue
        addition = effect.get("addition") if isinstance(effect.get("addition"), dict) else {}
        rows.append(
            {
                "zone": effect.get("zoneName") or "DAMAGE",
                "element": addition.get("blackboardKey") or addition.get("value") or "all",
                "source": "damage_effect",
                "confidence": "detail_raw",
                "reason": effect.get("processorType") or effect.get("enableSide"),
            }
        )
    return rows


def _context_kind(owner: str, source: str) -> str:
    if owner.startswith("eny_") and source.startswith("chr_"):
        return "player_to_enemy_debuff"
    if owner.startswith("chr_") and source.startswith("chr_"):
        if owner == source:
            return "self_buff"
        return "player_to_player_buff"
    if owner.startswith("eny_") and source.startswith("eny_"):
        return "enemy_self_effect"
    if owner.startswith("chr_") and source.startswith("eny_"):
        return "enemy_to_player_effect"
    return "other"


def build_truth_context(
    *,
    truth_jsonl: Path | None = None,
    truth_log: Path | None = None,
    truth_db: Path | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    root = (root or bundle_root()).resolve()
    truth_jsonl = (truth_jsonl or default_truth_jsonl_file()).resolve()
    truth_log = (truth_log or default_truth_log_file()).resolve()
    truth_db = (truth_db or default_truth_db_file()).resolve()

    rows = _parse_truth_jsonl(truth_jsonl)
    loadout_lines = _parse_truth_loadout_lines(truth_log) if truth_log.exists() else {}
    persistent_db = _load_truth_db(truth_db)

    character_catalog = _load_character_catalog(root)
    weapon_catalog = _load_weapon_catalog(root)
    equip_catalog = _load_equip_catalog(root)
    buff_manifest = _load_buff_manifest(root)
    buff_details = _load_buff_details(root)
    buff_hints = _load_buff_hints(root)

    latest_loadout_by_actor: dict[str, dict[str, Any]] = {}
    squad_snapshots: list[dict[str, Any]] = []
    for row in rows:
        row_type = str(row.get("type") or "")
        if row_type == "TRUTH_SQUAD":
            squad_snapshots.append(row)
        elif row_type == "TRUTH_LOADOUT":
            canonical = str(row.get("canonical") or "")
            if canonical:
                latest_loadout_by_actor[canonical] = row

    current_loadout: list[dict[str, Any]] = []
    for canonical_actor_id, row in latest_loadout_by_actor.items():
        static_actor = character_catalog.get(canonical_actor_id, {})
        text_row = loadout_lines.get(canonical_actor_id, {})
        weapon_template = str(row.get("weaponTemplate") or text_row.get("weapon_template") or "")
        weapon = weapon_catalog.get(weapon_template, {})

        equip_items: list[dict[str, Any]] = []
        for item in _parse_equip_templates(str(row.get("equips") or text_row.get("equips_raw") or "")):
            meta = equip_catalog.get(item["item_id"], {})
            equip_items.append(
                {
                    **item,
                    "item_name": meta.get("item_name") or item["item_id"],
                    "suit_id": meta.get("suit_id") or "",
                    "suit_name": meta.get("suit_name") or "",
                    "part_name": meta.get("part_name") or "",
                    "rarity": meta.get("rarity"),
                    "main_attr": meta.get("main_attr"),
                    "sub_attrs": meta.get("sub_attrs") or {},
                    "suit_values": meta.get("suit_values") or {},
                }
            )

        current_loadout.append(
            {
                "character_key": canonical_actor_id,
                "character_name": static_actor.get("name") or canonical_actor_id,
                "character_type": static_actor.get("charType"),
                "profession": static_actor.get("profession"),
                "weapon_type": static_actor.get("weapontype"),
                "actor_inst_id": row.get("actorInstId"),
                "potential_level": int(text_row.get("potential", row.get("potential") or 0) or 0),
                "weapon_inst_id": int(text_row.get("weapon_inst_id", row.get("weaponInstId") or 0) or 0),
                "weapon_refine": int(text_row.get("weapon_refine", 0) or 0),
                "weapon_break": int(text_row.get("weapon_break", 0) or 0),
                "attached_gem_inst_id": int(text_row.get("attached_gem_inst_id", 0) or 0),
                "weapon": _weapon_summary(weapon, text_row.get("weapon_level")),
                "equip_inst_ids": _parse_equip_inst_ids(text_row.get("equip_insts_raw", row.get("equipInsts") or "")),
                "equips": equip_items,
                "equip_suits": _parse_suit_counts(str(row.get("equipSuit") or text_row.get("equip_suit_raw") or "")),
            }
        )
    current_loadout.sort(key=lambda item: str(item["character_key"]))

    buff_rows_by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    skill_counts: Counter[str] = Counter()
    actor_counts: Counter[str] = Counter()
    for row in rows:
        row_type = str(row.get("type") or "")
        if row_type == "TRUTH_BUFF":
            canonical = str(row.get("canonical") or "")
            if canonical:
                buff_rows_by_id[canonical].append(row)
        elif row_type == "TRUTH_SKILL":
            canonical = str(row.get("canonical") or "")
            if canonical:
                skill_counts[canonical] += 1
        elif row_type == "TRUTH_ACTOR":
            canonical = str(row.get("canonical") or "")
            if canonical:
                actor_counts[canonical] += 1

    buffs_seen: list[dict[str, Any]] = []
    for canonical_buff_id, seen_rows in sorted(buff_rows_by_id.items()):
        manifest_entry = buff_manifest.get(canonical_buff_id, {})
        detail_entry = buff_details.get(canonical_buff_id, {})
        hint_entry = buff_hints.get(canonical_buff_id, {})
        effect_summary = _effect_summary_from_hints(hint_entry)
        if not effect_summary:
            effect_summary = _effect_summary_from_detail(detail_entry)
        phase_counts = Counter(str(row.get("phase") or "") for row in seen_rows)
        context_counts = Counter(
            _context_kind(str(row.get("owner") or ""), str(row.get("src") or ""))
            for row in seen_rows
        )
        owner_counts = Counter(str(row.get("owner") or "") for row in seen_rows if row.get("owner"))
        source_counts = Counter(str(row.get("src") or "") for row in seen_rows if row.get("src"))
        buffs_seen.append(
            {
                "buff_id": canonical_buff_id,
                "buff_name": manifest_entry.get("name") or detail_entry.get("name") or canonical_buff_id,
                "manifest_content_file": manifest_entry.get("contentFile"),
                "classification": hint_entry.get("classification"),
                "rdps_relevant": bool(effect_summary),
                "effect_summary": effect_summary,
                "blackboard": detail_entry.get("blackboard") or [],
                "attribute_effects": detail_entry.get("attributeEffects") or [],
                "damage_effects": detail_entry.get("damageEffects") or [],
                "created_buff_ids": detail_entry.get("createdBuffIds") or [],
                "referenced_buff_ids": detail_entry.get("referencedBuffIds") or [],
                "phase_counts": dict(phase_counts),
                "context_counts": dict(context_counts),
                "owner_counts": dict(owner_counts),
                "source_counts": dict(source_counts),
                "seen_count": len(seen_rows),
            }
        )
    buffs_seen.sort(
        key=lambda item: (
            0 if item.get("rdps_relevant") else 1,
            -int(item.get("seen_count") or 0),
            str(item.get("buff_id") or ""),
        )
    )

    skills_seen = [
        {
            "skill_id": skill_id,
            "count": count,
        }
        for skill_id, count in skill_counts.most_common()
    ]
    actors_seen = [
        {
            "actor_id": actor_id,
            "count": count,
        }
        for actor_id, count in actor_counts.most_common()
    ]

    persistent_summary = {
        "actors": len(persistent_db.get("actors", {})) if isinstance(persistent_db.get("actors"), dict) else 0,
        "skills": len(persistent_db.get("skills", {})) if isinstance(persistent_db.get("skills"), dict) else 0,
        "buffs": len(persistent_db.get("buffs", {})) if isinstance(persistent_db.get("buffs"), dict) else 0,
        "registry_items": len(persistent_db.get("registry_items", {})) if isinstance(persistent_db.get("registry_items"), dict) else 0,
        "registry_strings": len(persistent_db.get("registry_strings", {})) if isinstance(persistent_db.get("registry_strings"), dict) else 0,
        "loadouts": len(persistent_db.get("loadouts", {})) if isinstance(persistent_db.get("loadouts"), dict) else 0,
    }
    if isinstance(persistent_db.get("registry_summary"), dict):
        persistent_summary["registry_summary"] = persistent_db["registry_summary"]
    persistent_registry_items = []
    if isinstance(persistent_db.get("registry_items"), dict):
        for value, item in persistent_db["registry_items"].items():
            if not isinstance(item, dict):
                continue
            persistent_registry_items.append(
                {
                    "value": value,
                    "namespace": item.get("namespace"),
                    "class": item.get("class"),
                    "field": item.get("field"),
                    "seen_count": item.get("seen_count"),
                    "last_seen_ts": item.get("last_seen_ts"),
                }
            )
    persistent_registry_items.sort(
        key=lambda row: (-int(row.get("seen_count") or 0), str(row.get("value") or ""))
    )
    persistent_registry_strings = []
    if isinstance(persistent_db.get("registry_strings"), dict):
        for _, item in persistent_db["registry_strings"].items():
            if not isinstance(item, dict):
                continue
            persistent_registry_strings.append(
                {
                    "value": item.get("value"),
                    "namespace": item.get("namespace"),
                    "class": item.get("class"),
                    "field": item.get("field"),
                    "seen_count": item.get("seen_count"),
                    "last_seen_ts": item.get("last_seen_ts"),
                }
            )
    persistent_registry_strings.sort(
        key=lambda row: (
            str(row.get("namespace") or ""),
            str(row.get("class") or ""),
            str(row.get("field") or ""),
            str(row.get("value") or ""),
        )
    )
    persistent_skills = []
    if isinstance(persistent_db.get("skills"), dict):
        for skill_id, item in persistent_db["skills"].items():
            if not isinstance(item, dict):
                continue
            persistent_skills.append(
                {
                    "skill_id": skill_id,
                    "seen_count": item.get("seen_count"),
                    "last_seen_ts": item.get("last_seen_ts"),
                }
            )
    persistent_skills.sort(key=lambda row: (-int(row.get("seen_count") or 0), str(row.get("skill_id") or "")))
    persistent_buffs = []
    if isinstance(persistent_db.get("buffs"), dict):
        for buff_id, item in persistent_db["buffs"].items():
            if not isinstance(item, dict):
                continue
            persistent_buffs.append(
                {
                    "buff_id": buff_id,
                    "seen_count": item.get("seen_count"),
                    "last_seen_ts": item.get("last_seen_ts"),
                    "last_owner": item.get("last_owner"),
                    "last_source": item.get("last_source"),
                }
            )
    persistent_buffs.sort(key=lambda row: (-int(row.get("seen_count") or 0), str(row.get("buff_id") or "")))

    return {
        "sources": {
            "truth_jsonl": str(truth_jsonl),
            "truth_log": str(truth_log),
            "truth_db": str(truth_db),
        },
        "summary": {
            "squad_snapshot_count": len(squad_snapshots),
            "current_loadout_size": len(current_loadout),
            "unique_buffs_seen": len(buffs_seen),
            "unique_skills_seen": len(skills_seen),
            "unique_actors_seen": len(actors_seen),
            "persistent_db": persistent_summary,
        },
        "current_loadout": current_loadout,
        "buffs_seen": buffs_seen,
        "skills_seen": skills_seen,
        "actors_seen": actors_seen,
        "persistent_registry_items": persistent_registry_items,
        "persistent_registry_strings": persistent_registry_strings,
        "persistent_skills": persistent_skills,
        "persistent_buffs": persistent_buffs,
    }


def render_truth_context_markdown(context: dict[str, Any]) -> str:
    lines = [
        "# rDPS Truth Context",
        "",
        "## Sources",
        f"- truth_jsonl: `{context['sources']['truth_jsonl']}`",
        f"- truth_log: `{context['sources']['truth_log']}`",
        f"- truth_db: `{context['sources']['truth_db']}`",
        "",
        "## Persistent DB",
        f"- actors: {context['summary']['persistent_db']['actors']}",
        f"- skills: {context['summary']['persistent_db']['skills']}",
        f"- buffs: {context['summary']['persistent_db']['buffs']}",
        f"- registry_items: {context['summary']['persistent_db']['registry_items']}",
        f"- registry_strings: {context['summary']['persistent_db']['registry_strings']}",
        f"- loadouts: {context['summary']['persistent_db']['loadouts']}",
    ]
    if context['summary']['persistent_db'].get('registry_summary'):
        lines.append(f"- registry_summary: {context['summary']['persistent_db']['registry_summary']}")
    lines.extend([
        "",
        "## Registry Items",
    ])
    if context.get("persistent_registry_items"):
        for item in context.get("persistent_registry_items")[:30]:
            lines.append(
                "- "
                f"`{item['value']}` "
                f"seen={item.get('seen_count')} "
                f"from={item.get('namespace')}::{item.get('class')}.{item.get('field')}"
            )
    else:
        lines.append("- No persistent registry items are stored yet.")
    lines.extend(["", "## Registry Strings"])
    if context.get("persistent_registry_strings"):
        for item in context.get("persistent_registry_strings")[:30]:
            lines.append(
                "- "
                f"`{item['value']}` "
                f"seen={item.get('seen_count')} "
                f"from={item.get('namespace')}::{item.get('class')}.{item.get('field')}"
            )
    else:
        lines.append("- No persistent registry strings are stored yet.")
    lines.extend([
        "",
        "## Current Loadout",
    ])
    if context.get("current_loadout"):
        for row in context.get("current_loadout") or []:
            weapon = row.get("weapon") or {}
            lines.append(
                "- "
                f"{row.get('character_name') or row['character_key']} "
                f"(`{row['character_key']}`) "
                f"potential={row.get('potential_level')} "
                f"weapon={weapon.get('weapon_name') or weapon.get('weapon_id')} "
                f"lv={weapon.get('weapon_level')} refine={row.get('weapon_refine')} break={row.get('weapon_break')} "
                f"baseAtk={weapon.get('current_base_atk')}"
            )
            for suit in row.get("equip_suits") or []:
                lines.append(
                    f"  suit: `{suit['suit_id']}` x{suit['piece_count']}"
                )
    else:
        lines.append("- No current battle/session loadout rows were found in the latest truth dump.")
        if context['summary']['persistent_db']['loadouts']:
            lines.append("- Persistent loadout entries exist in the runtime truth DB.")

    lines.extend(["", "## Buffs Seen"])
    if context.get("buffs_seen"):
        for entry in context.get("buffs_seen")[:30]:
            effect_text = ", ".join(
                f"{item.get('zone')}:{item.get('element')}"
                for item in entry.get("effect_summary") or []
            ) or f"attributeEffects={len(entry.get('attribute_effects') or [])}, damageEffects={len(entry.get('damage_effects') or [])}"
            lines.append(
                "- "
                f"`{entry['buff_id']}` "
                f"seen={entry.get('seen_count')} "
                f"class={entry.get('classification') or '-'} "
                f"context={entry.get('context_counts')} "
                f"effects={effect_text}"
            )
    else:
        lines.append("- No battle/session buff rows were found in the latest truth dump.")
    lines.extend(["", "## Persistent Skills"])
    if context.get("persistent_skills"):
        for item in context.get("persistent_skills")[:20]:
            lines.append(f"- `{item['skill_id']}` seen={item.get('seen_count')} last={item.get('last_seen_ts')}")
    else:
        lines.append("- No persistent skills are stored yet.")
    lines.extend(["", "## Persistent Buffs"])
    if context.get("persistent_buffs"):
        for item in context.get("persistent_buffs")[:20]:
            lines.append(
                f"- `{item['buff_id']}` seen={item.get('seen_count')} lastOwner={item.get('last_owner')} lastSource={item.get('last_source')}"
            )
    else:
        lines.append("- No persistent buffs are stored yet.")
    return "\n".join(lines) + "\n"


def export_truth_context(
    *,
    truth_jsonl: Path | None = None,
    truth_log: Path | None = None,
    truth_db: Path | None = None,
    root: Path | None = None,
    out_json: Path | None = None,
    out_md: Path | None = None,
) -> dict[str, Path]:
    context = build_truth_context(truth_jsonl=truth_jsonl, truth_log=truth_log, truth_db=truth_db, root=root)
    out_json = (out_json or Path("reports") / "rdps_truth_context.json").resolve()
    out_md = (out_md or Path("reports") / "rdps_truth_context.md").resolve()
    _write_json(out_json, context)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(render_truth_context_markdown(context), encoding="utf-8")
    return {"json": out_json, "markdown": out_md}
