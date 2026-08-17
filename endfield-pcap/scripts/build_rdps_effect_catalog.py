#!/usr/bin/env python3
"""Build a review-only rDPS semantic catalogue from AKEData descriptions.

This script deliberately does not modify ``rdps_semantics_registry.json``.  It
combines the active registry, the manual-review overlay, and official display
text into a stable-ID catalogue that can be audited before any runtime change.
"""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = REPO_ROOT / "data" / "packet_semantics" / "rdps_semantics_registry.json"
DEFAULT_MANUAL_REVIEW = REPO_ROOT / "data" / "packet_semantics" / "rdps_semantics_registry_manual_review.json"
DEFAULT_SNAPSHOT = REPO_ROOT / "data" / "packet_semantics" / "akedata_rdps_text_snapshot.json"
DEFAULT_OUTPUT_JSON = REPO_ROOT / "data" / "packet_semantics" / "rdps_effect_catalog_review.json"
DEFAULT_OUTPUT_MD = REPO_ROOT / "docs" / "rdps_effect_catalog_review.md"
DEFAULT_AKEDATA_BASE = "https://data.akedata.wiki"

LIVE_TABLES = (
    "I18nTextTable_CN",
    "CharGrowthTable",
    "CharacterPotentialTable",
    "PotentialTalentEffectTable",
    "SkillPatchTable",
    "WeaponBasicTable",
    "ItemTable",
    "EquipSuitTable",
)

ZONE_LABELS = {
    "atk": "攻击力",
    "amp": "增幅",
    "combo": "连击",
    "dmg_inc": "伤害提升",
    "fragile": "脆弱",
    "arts_strength": "源石技艺强度",
    "res": "减抗",
    "vuln_taken": "承伤易伤",
}

ELEMENT_LABELS = {
    "all": "全部",
    "cryst": "寒冷",
    "fire": "灼热",
    "natural": "自然",
    "physical": "物理",
    "pulse": "电磁",
    "spell": "法术",
    "corresponding": "对应属性",
    "unknown": "待确认",
}

ELEMENT_TERMS = (
    ("physical", ("物理",)),
    ("fire", ("灼热", "火焰")),
    ("pulse", ("电磁",)),
    ("cryst", ("寒冷", "冰冷")),
    ("natural", ("自然",)),
    ("spell", ("法术",)),
)

ADMIN_IDS = {"chr_0002_endminm", "chr_0003_endminf", "chr_9000_endmin"}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def dump_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fetch_json(url: str, *, cache_bust: bool = False) -> Any:
    if cache_bust:
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}t={time.time_ns()}"
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "EndfieldLogs-rDPS-audit/1.0", "Cache-Control": "no-cache"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8-sig"))


def text_ref(value: Any, i18n: dict[str, str]) -> str:
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        return ""
    direct = value.get("text")
    if isinstance(direct, str) and direct:
        return direct
    ref_id = value.get("id")
    return str(i18n.get(str(ref_id), "")) if ref_id is not None else ""


def first_patch(skill_table: dict[str, Any], skill_id: str) -> dict[str, Any]:
    row = skill_table.get(skill_id)
    if not isinstance(row, dict):
        return {}
    bundle = row.get("SkillPatchDataBundle")
    if not isinstance(bundle, list) or not bundle or not isinstance(bundle[0], dict):
        return {}
    return bundle[0]


def blackboard_keys(patch: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    for row in patch.get("blackboard") or []:
        if isinstance(row, dict) and row.get("key"):
            keys.append(str(row["key"]))
    return sorted(set(keys))


def make_record(
    kind: str,
    source_id: str,
    source_name: str,
    section: str,
    title: str,
    description: str,
    *,
    runtime_ids: Iterable[str] = (),
    bb_keys: Iterable[str] = (),
) -> dict[str, Any] | None:
    description = str(description or "").strip()
    if not description:
        return None
    return {
        "kind": kind,
        "source_id": source_id,
        "source_name": source_name or source_id,
        "section": section,
        "title": title or section,
        "description": description,
        "runtime_ids": sorted({str(x) for x in runtime_ids if x}),
        "bb_keys": sorted({str(x) for x in bb_keys if x}),
    }


def dedupe_records(records: Iterable[dict[str, Any] | None]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    for record in records:
        if not record:
            continue
        key = (
            str(record["kind"]),
            str(record["source_id"]),
            str(record["section"]),
            str(record["title"]),
            str(record["description"]),
        )
        if key in seen:
            continue
        seen.add(key)
        output.append(record)
    return sorted(output, key=lambda row: (row["kind"], row["source_id"], row["section"], row["title"]))


def build_live_snapshot(base_url: str) -> dict[str, Any]:
    base_url = base_url.rstrip("/")
    manifest = fetch_json(f"{base_url}/manifest.json", cache_bust=True)
    latest_id = str(manifest["latest"])
    latest = next(row for row in manifest["versions"] if str(row.get("id")) == latest_id)
    table_root = f"{base_url}/{str(latest['tableCfgPath']).strip('/')}"
    tables = {name: fetch_json(f"{table_root}/{name}.json") for name in LIVE_TABLES}
    i18n = tables["I18nTextTable_CN"]
    skill_table = tables["SkillPatchTable"]
    records: list[dict[str, Any] | None] = []

    growth_table = tables["CharGrowthTable"]
    potential_table = tables["CharacterPotentialTable"]
    effect_table = tables["PotentialTalentEffectTable"]
    for char_id, growth in growth_table.items():
        if not isinstance(growth, dict):
            continue
        char_name = text_ref(growth.get("name"), i18n) or char_id
        for node in (growth.get("talentNodeMap") or {}).values():
            if not isinstance(node, dict) or node.get("nodeType") != 4:
                continue
            info = node.get("passiveSkillNodeInfo") or {}
            effect_id = str(info.get("talentEffectId") or "")
            effect = effect_table.get(effect_id) or {}
            records.append(
                make_record(
                    "character",
                    char_id,
                    char_name,
                    "talent",
                    text_ref(info.get("name"), i18n) or text_ref(effect.get("name"), i18n),
                    text_ref(effect.get("desc"), i18n),
                    runtime_ids=(effect_id,),
                )
            )

        potential = potential_table.get(char_id) or {}
        for row in potential.get("potentialUnlockBundle") or []:
            if not isinstance(row, dict):
                continue
            effect_id = str(row.get("potentialEffectId") or "")
            effect = effect_table.get(effect_id) or {}
            description = text_ref(effect.get("desc"), i18n)
            patch = first_patch(skill_table, effect_id)
            if not description:
                description = text_ref(patch.get("description"), i18n)
            records.append(
                make_record(
                    "character",
                    char_id,
                    char_name,
                    "potential",
                    text_ref(row.get("name"), i18n),
                    description,
                    runtime_ids=(effect_id,),
                    bb_keys=blackboard_keys(patch),
                )
            )

        for group in (growth.get("skillGroupMap") or {}).values():
            if not isinstance(group, dict):
                continue
            skill_ids = [str(x) for x in group.get("skillIdList") or [] if x]
            group_id = str(group.get("skillGroupId") or "")
            patch_ids = skill_ids or ([group_id] if group_id else [])
            keys: set[str] = set()
            for skill_id in patch_ids:
                keys.update(blackboard_keys(first_patch(skill_table, skill_id)))
            records.append(
                make_record(
                    "character",
                    char_id,
                    char_name,
                    "skill",
                    text_ref(group.get("name"), i18n),
                    text_ref(group.get("desc"), i18n),
                    runtime_ids=skill_ids + ([group_id] if group_id else []),
                    bb_keys=keys,
                )
            )

    weapon_table = tables["WeaponBasicTable"]
    item_table = tables["ItemTable"]
    for weapon_id, weapon in weapon_table.items():
        if not isinstance(weapon, dict):
            continue
        item = item_table.get(weapon_id) or {}
        weapon_name = text_ref(item.get("name"), i18n) or weapon_id
        for skill_id in weapon.get("weaponSkillList") or []:
            skill_id = str(skill_id)
            patch = first_patch(skill_table, skill_id)
            records.append(
                make_record(
                    "weapon",
                    weapon_id,
                    weapon_name,
                    "skill",
                    text_ref(patch.get("skillName"), i18n) or skill_id,
                    text_ref(patch.get("description"), i18n),
                    runtime_ids=(skill_id,),
                    bb_keys=blackboard_keys(patch),
                )
            )

    for suit_id, suit in tables["EquipSuitTable"].items():
        if not isinstance(suit, dict):
            continue
        for row in suit.get("list") or []:
            if not isinstance(row, dict):
                continue
            skill_id = str(row.get("skillID") or "")
            patch = first_patch(skill_table, skill_id)
            suit_name = text_ref(row.get("suitName"), i18n) or suit_id
            records.append(
                make_record(
                    "equip",
                    suit_id,
                    suit_name,
                    "set",
                    f"{row.get('equipCnt') or '?'}件套",
                    text_ref(patch.get("description"), i18n),
                    runtime_ids=(skill_id,),
                    bb_keys=blackboard_keys(patch),
                )
            )

    records_out = dedupe_records(records)
    return {
        "source": {
            "provider": "AKEData Wiki",
            "base_url": base_url,
            "manifest_url": f"{base_url}/manifest.json",
            "version_id": latest_id,
            "game_version": latest.get("gameVersion"),
            "hotfix_version": latest.get("hotfixVersion"),
            "published_at": latest.get("publishedAt"),
            "manifest_updated_at": manifest.get("updatedAt"),
            "table_cfg_path": latest.get("tableCfgPath"),
        },
        "counts": count_records(records_out),
        "records": records_out,
    }


def build_local_snapshot() -> dict[str, Any]:
    records: list[dict[str, Any] | None] = []
    char_dir = REPO_ROOT / "data" / "akedata" / "character" / "items"
    for path in sorted(char_dir.glob("*.json")):
        data = load_json(path)
        char_id = str(data.get("charId") or path.stem)
        char_name = str(data.get("name") or char_id)
        for section in ("talents", "potentials", "skills"):
            for row in data.get(section) or []:
                if not isinstance(row, dict):
                    continue
                records.append(
                    make_record(
                        "character",
                        char_id,
                        char_name,
                        section.rstrip("s"),
                        str(row.get("name") or section),
                        str(row.get("description") or ""),
                        runtime_ids=row.get("skillIds") or (),
                        bb_keys=(row.get("values") or {}).keys(),
                    )
                )

    weapon_dir = REPO_ROOT / "data" / "akedata" / "weapon" / "items"
    for path in sorted(weapon_dir.glob("*.json")):
        data = load_json(path)
        weapon_id = str(data.get("weaponId") or path.stem)
        weapon_name = str(data.get("title") or weapon_id)
        for row in data.get("skilllist") or []:
            if not isinstance(row, dict):
                continue
            records.append(
                make_record(
                    "weapon",
                    weapon_id,
                    weapon_name,
                    "skill",
                    str(row.get("skillName") or "skill"),
                    str(row.get("description") or ""),
                    bb_keys=(bb.get("key") for bb in row.get("blackboard") or [] if isinstance(bb, dict)),
                )
            )

    equip_dir = REPO_ROOT / "data" / "local_tables" / "equip" / "items"
    for path in sorted(equip_dir.glob("*.json")):
        data = load_json(path)
        records.append(
            make_record(
                "equip",
                str(data.get("suitID") or path.stem),
                str(data.get("name") or path.stem),
                "set",
                "3件套",
                str(data.get("skillDescription") or ""),
                bb_keys=(data.get("value") or {}).keys(),
            )
        )

    records_out = dedupe_records(records)
    local_char_ids = {path.stem for path in char_dir.glob("*.json")}
    local_weapon_ids = {path.stem for path in weapon_dir.glob("*.json")}
    table_char_ids = {path.stem for path in (REPO_ROOT / "data" / "local_tables" / "character" / "items").glob("*.json")}
    table_weapon_ids = {path.stem for path in (REPO_ROOT / "data" / "local_tables" / "weapon" / "items").glob("*.json")}
    return {
        "source": {
            "provider": "local AKEData mirror",
            "base_url": None,
            "version_id": "local-mirror",
            "source_gaps": {
                "characters": sorted(table_char_ids - local_char_ids),
                "weapons": sorted(table_weapon_ids - local_weapon_ids),
            },
        },
        "counts": count_records(records_out),
        "records": records_out,
    }


def count_records(records: Iterable[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    total = 0
    for record in records:
        counts[str(record.get("kind") or "unknown")] += 1
        total += 1
    return {"total": total, **dict(sorted(counts.items()))}


def strip_markup(value: str) -> str:
    text = re.sub(r"<[^>]*>", "", str(value or ""))
    text = text.replace("\r", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return text.strip()


def split_fragments(description: str) -> list[str]:
    clean = strip_markup(description)
    fragments = [part.strip(" /\n") for part in re.split(r"(?<=[。；;])|\n+", clean)]
    return [part for part in fragments if part]


def external_reasons(fragment: str) -> list[str]:
    reasons: list[str] = []
    team_target = bool(
        re.search(
            r"(?:全队|小队内其他干员|其他友方干员|其他队友|小队内所有友方|和自身属性不同的干员|任意干员)[^。；]*"
            r"(?:获得|施加|攻击力|造成的?[^。；]*伤害|伤害|增幅)",
            fragment,
        )
        or re.search(r"使主控干员[^。；]*(?:获得|施加|攻击力|增幅)", fragment)
        or re.search(r"为主控干员[^。；]*(?:施加|提供)[^。；]*(?:攻击力|增幅)", fragment)
        or re.search(r"主控干员(?:获得|受到)[^。；]*(?:攻击力|增幅)", fragment)
        or re.search(r"对其施加[^。；]*增幅", fragment)
    )
    relevant = bool(re.search(r"攻击力|伤害|增幅|脆弱|抗性|导电|腐蚀|碎甲|源石技艺强度", fragment))
    if team_target and relevant:
        reasons.append("external_ally_effect")

    fragile_is_trigger = bool(re.search(r"装备者[^。；]{0,50}施加[^，。；]{0,30}脆弱(?:时|后)[，,]", fragment))
    if re.search(r"施加[^。；]{0,60}脆弱", fragment) and not fragile_is_trigger:
        reasons.append("enemy_fragile")
    if re.search(r"(?:目标|敌人)[^。；]{0,50}受到[^。；]{0,30}伤害[^。；]{0,20}(?:\+|提高|提升)", fragment):
        reasons.append("enemy_damage_taken")
    if re.search(r"使[^。；]{0,30}(?:目标|敌人)[^。；]{0,30}受到[^。；]{0,30}伤害", fragment):
        reasons.append("enemy_damage_taken")
    if re.search(r"(?:降低|减少)[^。；]{0,24}(?:抗性|防御)|(?:抗性|防御)[^。；]{0,18}(?:降低|减少|下降)", fragment):
        reasons.append("enemy_resistance_down")
    if re.search(r"(?:施加的)?[^。；]{0,30}脆弱效果[^。；]{0,24}(?:额外|提升|提高|加倍|加强)", fragment):
        reasons.append("fragile_modifier")
    if re.search(r"(?:施加|强制)[^。；]{0,24}(?:导电|腐蚀|碎甲)", fragment):
        reasons.append("common_mechanism")
    return sorted(set(reasons))


def infer_elements(fragment: str, zone: str) -> list[str]:
    if zone in {"atk", "combo", "arts_strength"}:
        return ["all"]
    if zone == "res" and "腐蚀" in fragment:
        return ["all"]
    if zone == "vuln_taken" and "导电" in fragment and "法术" not in fragment:
        return ["spell"]
    if zone == "vuln_taken" and "碎甲" in fragment and "物理" not in fragment:
        return ["physical"]

    if "对应属性" in fragment:
        return ["corresponding"]

    focus = fragment
    if zone == "fragile" and "脆弱" in fragment:
        windows = []
        for match in re.finditer("脆弱", fragment):
            windows.append(fragment[max(0, match.start() - 10) : match.end() + 2])
        focus = " ".join(windows)
    elif zone == "vuln_taken":
        matches = re.findall(r"受到(?:的)?([^。；]{0,60}?)(?:\+|提高|提升)", fragment)
        if matches:
            focus = " ".join(matches)
    elif zone == "amp" and "增幅" in fragment:
        windows = []
        for match in re.finditer("增幅", fragment):
            windows.append(fragment[max(0, match.start() - 10) : match.end() + 2])
        focus = " ".join(windows)

    elements = [key for key, terms in ELEMENT_TERMS if any(term in focus for term in terms)]
    if elements:
        return elements
    if re.search(r"所有类型|全队[^。；]{0,24}造成的伤害|其他队友造成的伤害|其他干员造成的伤害", fragment):
        return ["all"]
    return ["unknown"]


def infer_effects(fragment: str, reasons: Iterable[str]) -> list[dict[str, str]]:
    zones: list[str] = []
    if ("enemy_fragile" in reasons or "fragile_modifier" in reasons) and "脆弱" in fragment:
        zones.append("fragile")
    if re.search(r"受到[^。；]{0,30}伤害[^。；]{0,20}(?:\+|提高|提升)", fragment):
        zones.append("vuln_taken")
    if re.search(r"(?:降低|减少)[^。；]{0,24}(?:抗性|防御)|(?:抗性|防御)[^。；]{0,18}(?:降低|减少|下降)", fragment) or "腐蚀" in fragment:
        zones.append("res")
    if "增幅" in fragment:
        zones.append("amp")
    if re.search(r"连携技伤害[^。；]{0,18}(?:\+|提升|提高)", fragment) and "external_ally_effect" in reasons:
        zones.append("combo")
    if re.search(r"攻击力[^。；]{0,18}(?:\+|提升|提高)|攻击力提升", fragment) and "external_ally_effect" in reasons:
        zones.append("atk")
    if re.search(r"源石技艺强度[^。；]{0,18}(?:\+|提升|提高)", fragment) and "external_ally_effect" in reasons:
        zones.append("arts_strength")
    if re.search(r"(?:造成的?[^。；]{0,16}伤害|(?:物理|灼热|电磁|寒冷|自然|法术)伤害)[^。；]{0,18}(?:\+|提升|提高)", fragment) and "external_ally_effect" in reasons and "连携技伤害" not in fragment:
        zones.append("dmg_inc")
    if "导电" in fragment and "common_mechanism" in reasons:
        zones.append("vuln_taken")
    if "碎甲" in fragment and "common_mechanism" in reasons:
        zones.append("vuln_taken")

    effects: list[dict[str, str]] = []
    for zone in dict.fromkeys(zones):
        for element in infer_elements(fragment, zone):
            effects.append({"zone": zone, "element": element})
    return effects


def source_group_id(source_id: str) -> str:
    return "chr_admin" if source_id in ADMIN_IDS else source_id


def extract_text_candidates(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    named_effects: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    record_key_terms: dict[tuple[str, str, str, str], list[str]] = {}
    for record in records:
        source_key = source_group_id(str(record["source_id"]))
        raw_description = str(record.get("description") or "")
        terms = sorted(set(re.findall(r"<@ba\.key>([^<]{2,20})</>", raw_description)))
        record_key = (
            str(record["kind"]),
            str(record["source_id"]),
            str(record["section"]),
            str(record["title"]),
        )
        record_key_terms[record_key] = terms
        definition_text = strip_markup(raw_description)
        definition_effects = infer_effects(definition_text, ["external_ally_effect"])
        for term in terms:
            if term in definition_text and definition_effects:
                named_effects[(source_key, term)].extend(definition_effects)

    candidates: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for record in records:
        for fragment in split_fragments(str(record.get("description") or "")):
            record_key = (
                str(record["kind"]),
                str(record["source_id"]),
                str(record["section"]),
                str(record["title"]),
            )
            terms = record_key_terms.get(record_key, [])
            reasons = external_reasons(fragment)
            if not reasons and "获得" in fragment:
                receives_named_effect = bool(
                    re.search(
                        r"(?:全队|小队内其他干员|其他友方干员|其他队友|任意干员|和自身属性不同的干员)[^。；]*获得",
                        fragment,
                    )
                )
                if receives_named_effect and any(term in fragment and named_effects.get((source_group_id(str(record["source_id"])), term)) for term in terms):
                    reasons = ["external_ally_effect"]
            if not reasons:
                continue
            effects = infer_effects(fragment, reasons)
            linked_terms: list[str] = []
            if not effects and "external_ally_effect" in reasons and "获得" in fragment:
                for term in terms:
                    if term not in fragment:
                        continue
                    linked = named_effects.get((source_group_id(str(record["source_id"])), term), [])
                    if linked:
                        linked_terms.append(term)
                        effects.extend(linked)
                effects = [dict(pair) for pair in {tuple(sorted(effect.items())) for effect in effects}]
                if effects:
                    reasons = sorted(set(reasons + ["linked_named_effect"]))
            if not effects:
                continue
            key = (
                source_group_id(str(record["source_id"])),
                str(record["section"]),
                str(record["title"]),
                fragment,
                tuple((effect["zone"], effect["element"]) for effect in effects),
            )
            if key in seen:
                continue
            seen.add(key)
            candidates.append(
                {
                    "candidate_id": "",
                    "kind": record["kind"],
                    "source_id": str(record["source_id"]),
                    "source_group_id": source_group_id(str(record["source_id"])),
                    "source_name": record["source_name"],
                    "section": record["section"],
                    "title": record["title"],
                    "text": fragment,
                    "reasons": reasons,
                    "inferred_effects": effects,
                    "runtime_ids": record.get("runtime_ids") or [],
                    "bb_keys": record.get("bb_keys") or [],
                    "linked_terms": linked_terms,
                }
            )
    candidates.sort(key=lambda row: (row["kind"], row["source_group_id"], row["section"], row["title"], row["text"]))
    for index, candidate in enumerate(candidates, start=1):
        candidate["candidate_id"] = f"TXT-{index:04d}"
    return candidates


def char_name_map(records: Iterable[dict[str, Any]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for row in records:
        if row.get("kind") != "character":
            continue
        name = str(row.get("source_name") or "")
        source_id = source_group_id(str(row.get("source_id") or ""))
        if name:
            result[name] = source_id
    result["管理员"] = "chr_admin"
    return result


def registry_source_key(entry: dict[str, Any], names: dict[str, str], canonical: str = "") -> str:
    guard = entry.get("guard") or {}
    if guard.get("source_character_key"):
        return source_group_id(str(guard["source_character_key"]))
    if guard.get("weapon_id"):
        return str(guard["weapon_id"])
    if guard.get("suit_id"):
        return str(guard["suit_id"])
    char_match = re.match(r"buff_(chr_\d{4}_[a-z0-9]+)(?:_|$)", canonical)
    if char_match:
        return source_group_id(char_match.group(1))
    source = str(entry.get("source") or "")
    match = re.search(r"(wpn_[a-z0-9_]+)", source)
    if match:
        return match.group(1)
    match = re.search(r"(suit_[a-z0-9_]+)", source)
    if match:
        return match.group(1)
    if source in names:
        return names[source]
    if "通用" in source:
        return "common"
    if "连击" in source:
        return "combo_projection"
    return f"unmapped:{source or 'unknown'}"


def status_rank(status: str) -> int:
    return {
        "proposed_removal": 5,
        "proposed_replacement_removal": 5,
        "verified_existing_with_member_removal": 3,
        "proposed_addition": 4,
        "proposed_update_addition": 3,
        "verified_existing_update_review": 2,
        "verified_existing": 1,
    }.get(status, 0)


def collect_catalog_components(
    registry: dict[str, Any], manual: dict[str, Any], records: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    names = char_name_map(records)
    updates = manual.get("proposed_verified_updates") or {}
    additions = manual.get("proposed_verified_additions") or {}
    removals = manual.get("proposed_verified_removals") or {}
    decisions = manual.get("review_decisions") or {}
    decisions_by_target: dict[str, list[dict[str, str]]] = defaultdict(list)
    for decision_id, decision in decisions.items():
        if not isinstance(decision, dict):
            continue
        for target in decision.get("targets") or []:
            decisions_by_target[str(target)].append(
                {
                    "decision_id": str(decision_id),
                    "status": str(decision.get("status") or "pending"),
                    "decision": str(decision.get("decision") or ""),
                }
            )
    raw_components: list[dict[str, Any]] = []

    def append_entry(canonical: str, entry: dict[str, Any], kind: str, base_status: str, old_effects: list[dict[str, Any]] | None = None) -> None:
        source_key = registry_source_key(entry, names, canonical)
        old_pairs = {(str(row.get("zone")), str(row.get("element"))) for row in (old_effects or [])}
        for effect in entry.get("effects") or []:
            if not isinstance(effect, dict) or not effect.get("zone") or not effect.get("element"):
                continue
            pair = (str(effect["zone"]), str(effect["element"]))
            status = base_status
            if base_status == "verified_existing_update_review" and pair not in old_pairs:
                status = "proposed_update_addition"
            member_key = f"{kind}:{canonical}:{pair[0]}:{pair[1]}:{effect.get('bb_key') or ''}"
            raw_components.append(
                {
                    "canonical": canonical,
                    "kind": kind,
                    "member_key": member_key,
                    "cn_name": str(entry.get("cn_name") or canonical),
                    "source": str(entry.get("source") or ""),
                    "source_key": source_key,
                    "zone": pair[0],
                    "element": pair[1],
                    "bb_key": str(effect.get("bb_key") or ""),
                    "numeric_ids": [str(x) for x in entry.get("numeric_ids") or []],
                    "aliases": [str(x) for x in entry.get("aliases") or []],
                    "guard": entry.get("guard") or {},
                    "status": status,
                    "note": str(entry.get("note") or ""),
                }
            )

    for canonical, original in (registry.get("verified_effects") or {}).items():
        original = dict(original)
        if canonical in updates:
            merged = {**original, **dict(updates[canonical])}
            append_entry(canonical, merged, "exact", "verified_existing_update_review", original.get("effects") or [])
            new_pairs = {
                (str(row.get("zone")), str(row.get("element")))
                for row in merged.get("effects") or []
                if isinstance(row, dict)
            }
            removed_effects = [
                row
                for row in original.get("effects") or []
                if isinstance(row, dict) and (str(row.get("zone")), str(row.get("element"))) not in new_pairs
            ]
            if removed_effects:
                removed_entry = dict(original)
                removed_entry["effects"] = removed_effects
                removed_entry["note"] = (
                    str(removed_entry.get("note") or "")
                    + " 本乘区/元素将被本轮 proposed_verified_updates 替换。"
                ).strip()
                append_entry(canonical, removed_entry, "exact", "proposed_replacement_removal")
        else:
            status = "proposed_removal" if canonical in removals else "verified_existing"
            if canonical in removals:
                original["note"] = str(removals[canonical].get("reason") or original.get("note") or "")
            append_entry(canonical, original, "exact", status)

    for canonical, addition in additions.items():
        append_entry(canonical, dict(addition), "exact", "proposed_addition")

    for prefix in registry.get("verified_prefixes") or []:
        if isinstance(prefix, dict):
            append_entry(str(prefix.get("prefix") or ""), dict(prefix), "prefix", "verified_existing")

    groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for component in raw_components:
        groups[(component["source_key"], component["cn_name"], component["zone"], component["element"])].append(component)

    catalog: list[dict[str, Any]] = []
    for (source_key, cn_name, zone, element), members in groups.items():
        statuses = sorted({row["status"] for row in members}, key=status_rank, reverse=True)
        runtime_members = [
            {
                "kind": row["kind"],
                "canonical": row["canonical"],
                "bb_key": row["bb_key"],
                "member_key": row["member_key"],
                "status": row["status"],
            }
            for row in sorted(members, key=lambda item: item["member_key"])
        ]
        status_set = set(statuses)
        if "proposed_removal" in status_set and "verified_existing" in status_set:
            group_status = "verified_existing_with_member_removal"
        else:
            group_status = statuses[0] if statuses else "verified_existing"
        catalog.append(
            {
                "rdps_effect_id": "",
                "cn_name": cn_name,
                "source": next((row["source"] for row in members if row["source"]), ""),
                "source_key": source_key,
                "zone": zone,
                "zone_name": ZONE_LABELS.get(zone, zone),
                "element": element,
                "element_name": ELEMENT_LABELS.get(element, element),
                "status": group_status,
                "all_statuses": statuses,
                "numeric_ids": sorted({value for row in members for value in row["numeric_ids"]}),
                "aliases": sorted({value for row in members for value in row["aliases"]}),
                "guards": [row["guard"] for row in members if row["guard"]],
                "runtime_members": runtime_members,
                "notes": sorted({row["note"] for row in members if row["note"]}),
                "review_decisions": [
                    decision
                    for canonical in sorted({row["canonical"] for row in members})
                    for decision in decisions_by_target.get(canonical, [])
                ],
                "text_evidence": [],
            }
        )
    return catalog


def catalog_sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
    source = str(row["source_key"])
    if source == "common":
        category = 0
    elif source.startswith("chr_"):
        category = 1
    elif source.startswith("wpn_"):
        category = 2
    elif source.startswith("suit_"):
        category = 3
    else:
        category = 4
    return (category, source, str(row["cn_name"]), str(row["zone"]), str(row["element"]))


def assign_stable_ids(catalog: list[dict[str, Any]], previous_path: Path) -> None:
    previous: list[dict[str, Any]] = []
    if previous_path.exists():
        try:
            previous = load_json(previous_path).get("effect_catalog") or []
        except (OSError, ValueError, AttributeError):
            previous = []
    by_member: dict[str, str] = {}
    by_semantic: dict[tuple[str, str, str, str], str] = {}
    max_id = 0
    for row in previous:
        effect_id = str(row.get("rdps_effect_id") or "")
        match = re.fullmatch(r"RDPS-(\d{4,})", effect_id)
        if not match:
            continue
        max_id = max(max_id, int(match.group(1)))
        for member in row.get("runtime_members") or []:
            if member.get("member_key"):
                by_member[str(member["member_key"])] = effect_id
        by_semantic[(str(row.get("source_key")), str(row.get("cn_name")), str(row.get("zone")), str(row.get("element")))] = effect_id

    used: set[str] = set()
    for row in sorted(catalog, key=catalog_sort_key):
        candidates = {
            by_member.get(str(member.get("member_key")))
            for member in row.get("runtime_members") or []
            if member.get("member_key")
        }
        candidates.discard(None)
        effect_id = sorted(candidates)[0] if candidates else by_semantic.get(
            (str(row["source_key"]), str(row["cn_name"]), str(row["zone"]), str(row["element"]))
        )
        if effect_id and effect_id not in used:
            row["rdps_effect_id"] = effect_id
            used.add(effect_id)
            continue
        max_id += 1
        effect_id = f"RDPS-{max_id:04d}"
        row["rdps_effect_id"] = effect_id
        used.add(effect_id)
    catalog.sort(key=lambda row: int(str(row["rdps_effect_id"]).split("-")[-1]))


def annotate_registry_conflicts(catalog: list[dict[str, Any]], registry: dict[str, Any]) -> None:
    known = (registry.get("known_non_rdps") or {}).get("exact_buff_ids") or {}
    known_ids = set(known)
    for row in catalog:
        overlaps = sorted(
            {
                str(member.get("canonical"))
                for member in row.get("runtime_members") or []
                if str(member.get("canonical")) in known_ids
            }
        )
        row["known_non_rdps_overlap"] = overlaps


def component_index(catalog: list[dict[str, Any]]) -> dict[tuple[str, str, str], list[dict[str, Any]]]:
    result: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in catalog:
        result[(str(row["source_key"]), str(row["zone"]), str(row["element"]))].append(row)
    return result


def common_mechanism_matches(fragment: str, catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
    wanted: list[tuple[str, str, str]] = []
    if "导电" in fragment:
        wanted.append(("common", "vuln_taken", "spell"))
    if "腐蚀" in fragment:
        wanted.append(("common", "res", "all"))
    if "碎甲" in fragment:
        wanted.append(("common", "vuln_taken", "physical"))
    return [row for row in catalog if (row["source_key"], row["zone"], row["element"]) in wanted]


def match_candidates(
    candidates: list[dict[str, Any]], catalog: list[dict[str, Any]], manual: dict[str, Any] | None = None
) -> None:
    index = component_index(catalog)
    by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_id = {row["rdps_effect_id"]: row for row in catalog}
    for row in catalog:
        by_source[str(row["source_key"])].append(row)

    rejected_shapes: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    for decision_id, decision in ((manual or {}).get("review_decisions") or {}).items():
        if not isinstance(decision, dict) or decision.get("status") != "rejected":
            continue
        for source_key in decision.get("source_keys") or []:
            for shape in decision.get("effect_shapes") or []:
                if isinstance(shape, dict) and shape.get("zone") and shape.get("element"):
                    rejected_shapes[(str(source_key), str(shape["zone"]), str(shape["element"]))].append(str(decision_id))

    for candidate in candidates:
        matches: list[dict[str, Any]] = []
        per_effect: list[dict[str, Any]] = []
        source_key = str(candidate["source_group_id"])
        for effect in candidate["inferred_effects"]:
            element = str(effect["element"])
            if element == "corresponding":
                exact = [
                    row
                    for row in by_source.get(source_key, [])
                    if row["zone"] == effect["zone"] and row["element"] in {"cryst", "fire", "natural", "physical", "pulse", "spell"}
                ]
            else:
                exact = index.get((source_key, str(effect["zone"]), element), [])
            if not exact and "common_mechanism" in candidate["reasons"]:
                exact = [
                    row
                    for row in common_mechanism_matches(candidate["text"], catalog)
                    if row["zone"] == effect["zone"] and row["element"] == effect["element"]
                ]
            matches.extend(exact)
            per_effect.append(
                {
                    **effect,
                    "matched_rdps_effect_ids": sorted({row["rdps_effect_id"] for row in exact}),
                }
            )

        unique = {row["rdps_effect_id"]: row for row in matches}
        matched_ids = sorted(unique)
        statuses = {row["status"] for row in unique.values()}
        rejected_decisions = sorted(
            {
                decision_id
                for effect in candidate["inferred_effects"]
                for decision_id in rejected_shapes.get(
                    (source_key, str(effect["zone"]), str(effect["element"])), []
                )
            }
        )
        if matched_ids:
            if statuses <= {"proposed_addition", "proposed_update_addition"}:
                match_status = "covered_by_proposal"
            elif statuses <= {"proposed_removal", "proposed_replacement_removal"}:
                match_status = "matched_entry_proposed_for_removal"
            else:
                match_status = "covered_verified"
        elif rejected_decisions:
            match_status = "excluded_by_review"
        elif not candidate["inferred_effects"]:
            match_status = "review_required_no_effect_shape"
        elif by_source.get(source_key):
            match_status = "source_covered_effect_mismatch"
        else:
            match_status = "missing_candidate"
        candidate["effect_matches"] = per_effect
        candidate["matched_rdps_effect_ids"] = matched_ids
        candidate["review_decision_ids"] = rejected_decisions
        candidate["match_status"] = match_status
        for effect_id in matched_ids:
            by_id[effect_id]["text_evidence"].append(candidate["candidate_id"])

    for row in catalog:
        row["text_evidence"] = sorted(set(row["text_evidence"]))
        if row["text_evidence"]:
            row["text_audit_status"] = "official_text_matched"
        elif row["source_key"] in {"common", "combo_projection"}:
            row["text_audit_status"] = "no_direct_source_text_expected"
        else:
            row["text_audit_status"] = "no_external_text_evidence"


def summarize(catalog: list[dict[str, Any]], candidates: list[dict[str, Any]], snapshot: dict[str, Any]) -> dict[str, Any]:
    status_counts: dict[str, int] = defaultdict(int)
    for row in catalog:
        status_counts[str(row["status"])] += 1
    match_counts: dict[str, int] = defaultdict(int)
    for row in candidates:
        match_counts[str(row["match_status"])] += 1
    return {
        "text_records": snapshot.get("counts") or {},
        "rdps_effects": len(catalog),
        "effect_statuses": dict(sorted(status_counts.items())),
        "text_candidates": len(candidates),
        "candidate_matches": dict(sorted(match_counts.items())),
        "effects_without_text_evidence": sum(1 for row in catalog if not row["text_evidence"]),
        "effects_overlapping_known_non_rdps": sum(1 for row in catalog if row.get("known_non_rdps_overlap")),
    }


def md_escape(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", "<br>")


def short_text(value: str, limit: int = 130) -> str:
    value = re.sub(r"\s+", " ", str(value or "")).strip()
    return value if len(value) <= limit else value[: limit - 1] + "…"


def render_markdown(payload: dict[str, Any]) -> str:
    source = payload["text_source"]
    summary = payload["summary"]
    catalog = payload["effect_catalog"]
    candidates = payload["text_candidates"]
    lines = [
        "# rDPS 效果编号与官表文本审核",
        "",
        "> 本文件仅供审核。解析器不会加载本文件，现有线上白名单没有被自动修改。",
        "",
        "## 数据口径",
        "",
        f"- 文本来源：{md_escape(source.get('provider'))}",
        f"- 官网版本：`{md_escape(source.get('version_id'))}`（游戏 {md_escape(source.get('game_version'))}，热更 {md_escape(source.get('hotfix_version'))}）",
        f"- 官表发布时间：{md_escape(source.get('published_at'))}",
        f"- 官表文本记录：{summary['text_records'].get('total', 0)} 条；识别出外部 rDPS 相关文本 {summary['text_candidates']} 条",
        f"- 编号后的语义效果：{summary['rdps_effects']} 项；没有直接文本证据的现有项 {summary['effects_without_text_evidence']} 项",
        f"- 同时存在于 verified/proposal 与 known_non_rdps 的冲突效果：{summary['effects_overlapping_known_non_rdps']} 项",
        "",
        "编号按语义效果分配：同一个运行时 buff 的不同乘区/元素分别编号；同语义的 runtime 别名共享编号。编号一经写入目录，后续重建会优先复用，不回收旧号。",
        "",
        "## 待审核改动",
        "",
        "| 编号 | 审核 | 状态 | 效果 | 来源 | 乘区 / 元素 | runtime key |",
        "|---|---|---|---|---|---|---|",
    ]
    review_rows = [row for row in catalog if row["status"] != "verified_existing"]
    for row in review_rows:
        runtime = "<br>".join(
            md_escape(member["canonical"])
            + (f" [{md_escape(member.get('status'))}]" if member.get("status") != "verified_existing" else "")
            for member in row["runtime_members"]
        )
        review = ", ".join(sorted({decision["status"] for decision in row.get("review_decisions") or []})) or "pending"
        lines.append(
            f"| `{row['rdps_effect_id']}` | {md_escape(review)} | {md_escape(row['status'])} | {md_escape(row['cn_name'])} | "
            f"{md_escape(row['source'])} | {md_escape(row['zone_name'])} / {md_escape(row['element_name'])} | {runtime} |"
        )
    if not review_rows:
        lines.append("| - | - | - | 无 | - | - | - |")

    conflicts = [row for row in catalog if row.get("known_non_rdps_overlap")]
    lines += [
        "",
        "## Registry 自相矛盾项",
        "",
        "| 编号 | 效果 | 同时命中的 known_non_rdps key |",
        "|---|---|---|",
    ]
    for row in conflicts:
        lines.append(
            f"| `{row['rdps_effect_id']}` | {md_escape(row['cn_name'])}（{md_escape(row['zone_name'])}/{md_escape(row['element_name'])}） | "
            f"{md_escape(', '.join(row['known_non_rdps_overlap']))} |"
        )
    if not conflicts:
        lines.append("| - | 无 | - |")

    lines += [
        "",
        "## 当前效果编号总表",
        "",
        "| 编号 | 效果 | 来源 | 乘区 / 元素 | numeric ID | runtime key | 文本证据 |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in catalog:
        runtime = "<br>".join(
            md_escape(member["canonical"])
            + (f" [{md_escape(member.get('status'))}]" if member.get("status") != "verified_existing" else "")
            for member in row["runtime_members"]
        )
        numeric = ", ".join(row["numeric_ids"]) or "-"
        evidence = ", ".join(row["text_evidence"]) or "-"
        lines.append(
            f"| `{row['rdps_effect_id']}` | {md_escape(row['cn_name'])} | {md_escape(row['source'])} | "
            f"{md_escape(row['zone_name'])} / {md_escape(row['element_name'])} | {md_escape(numeric)} | {runtime} | {md_escape(evidence)} |"
        )

    unresolved = [row for row in candidates if row["match_status"] not in {"covered_verified"}]
    lines += [
        "",
        "## 官表文本发现的缺项 / 疑项",
        "",
        "| 文本号 | 结论 | 来源 | 条目 | 推断乘区 | 匹配编号 | 官表原文摘录 |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in unresolved:
        shape = ", ".join(
            f"{ZONE_LABELS.get(effect['zone'], effect['zone'])}/{ELEMENT_LABELS.get(effect['element'], effect['element'])}"
            for effect in row["inferred_effects"]
        ) or "待人工确认"
        matches = ", ".join(row["matched_rdps_effect_ids"]) or "-"
        lines.append(
            f"| `{row['candidate_id']}` | {md_escape(row['match_status'])} | {md_escape(row['source_name'])} | "
            f"{md_escape(row['section'])} · {md_escape(row['title'])} | {md_escape(shape)} | {md_escape(matches)} | "
            f"{md_escape(short_text(row['text']))} |"
        )
    if not unresolved:
        lines.append("| - | - | - | - | - | - | 无 |")

    lines += [
        "",
        "## 审核规则",
        "",
        "- `covered_verified`：官表文本的来源、乘区和元素能命中现有 verified 效果。",
        "- `covered_by_proposal`：只能由本轮人工草案补齐，尚未进入线上白名单。",
        "- `source_covered_effect_mismatch`：来源已有白名单，但官表文字推断出的乘区或元素对不上，需要核对 registry。",
        "- `missing_candidate`：官表显示存在外部增益/减益，但该来源没有对应 verified 效果。",
        "- `review_required_no_effect_shape`：文本明确影响队友或敌人，但自动规则无法安全判断乘区，必须人工读原文。",
        "- `excluded_by_review`：自动文本扫描命中候选，但已由人工审核确认为不进入外部 rDPS。",
        "",
    ]
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--manual-review", type=Path, default=DEFAULT_MANUAL_REVIEW)
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    parser.add_argument("--akedata-base", default=DEFAULT_AKEDATA_BASE)
    parser.add_argument("--refresh-live", action="store_true", help="download the latest official AKEData TableCfg and refresh the compact snapshot")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.refresh_live:
        snapshot = build_live_snapshot(args.akedata_base)
        dump_json(args.snapshot, snapshot)
    elif args.snapshot.exists():
        snapshot = load_json(args.snapshot)
    else:
        snapshot = build_local_snapshot()
        dump_json(args.snapshot, snapshot)

    registry = load_json(args.registry)
    manual = load_json(args.manual_review) if args.manual_review.exists() else {}
    records = snapshot.get("records") or []
    candidates = extract_text_candidates(records)
    catalog = collect_catalog_components(registry, manual, records)
    assign_stable_ids(catalog, args.output_json)
    annotate_registry_conflicts(catalog, registry)
    match_candidates(candidates, catalog, manual)
    payload = {
        "purpose": "review_only_not_loaded_by_parser",
        "text_source": snapshot.get("source") or {},
        "active_registry": str(args.registry),
        "manual_review_overlay": str(args.manual_review),
        "review_decisions": manual.get("review_decisions") or {},
        "id_policy": {
            "format": "RDPS-xxxx",
            "unit": "one semantic zone/element effect",
            "alias_policy": "runtime aliases with the same source, display name, zone and element share an ID",
            "reuse_policy": "existing IDs are reused by runtime member key; old IDs are never intentionally recycled",
        },
        "summary": summarize(catalog, candidates, snapshot),
        "effect_catalog": catalog,
        "text_candidates": candidates,
    }
    dump_json(args.output_json, payload)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.write_text(render_markdown(payload), encoding="utf-8")
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    print(f"snapshot={args.snapshot}")
    print(f"catalog={args.output_json}")
    print(f"review={args.output_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
