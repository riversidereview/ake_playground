from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ALLOCATABLE_ZONES = {"atk", "dmg_inc", "amp", "fragile", "vuln_taken", "res", "combo"}
ZONE_CN = {
    "atk": "攻击",
    "dmg_inc": "增伤",
    "amp": "增幅",
    "fragile": "脆弱",
    "vuln_taken": "承伤易伤",
    "res": "减抗",
    "combo": "连击增伤",
}
ELEMENT_CN = {
    "all": "全部",
    "spell": "法术",
    "physical": "物理",
    "fire": "灼热",
    "pulse": "电磁",
    "cryst": "寒冷/碎冰",
    "natural": "自然",
}
SOURCE_KIND_CN = {
    "character": "角色",
    "weapon": "武器",
    "suit": "装备套装",
    "common": "通用机制",
}


def load_json(rel: str) -> dict[str, Any]:
    path = ROOT / rel
    return json.loads(path.read_text(encoding="utf-8"))


def md_escape(value: Any) -> str:
    text = str(value if value is not None else "")
    return text.replace("|", "\\|").replace("\n", "<br>")


def normalize_effects(row: dict[str, Any]) -> list[dict[str, Any]]:
    effects: list[dict[str, Any]] = []
    for item in row.get("effects") or []:
        if not isinstance(item, dict):
            continue
        zone = str(item.get("zone") or "")
        if zone in ALLOCATABLE_ZONES:
            effects.append(
                {
                    "kind": "static",
                    "zone": zone,
                    "element": str(item.get("element") or "all"),
                    "bb_key": str(item.get("bb_key") or ""),
                    "rate": item.get("rate"),
                }
            )
    for item in row.get("dynamic_effects") or []:
        if not isinstance(item, dict):
            continue
        zone = str(item.get("zone") or "")
        if zone in ALLOCATABLE_ZONES:
            effects.append(
                {
                    "kind": "dynamic",
                    "zone": zone,
                    "element": str(item.get("element") or "all"),
                    "base_bb_key": str(item.get("base_bb_key") or item.get("bb_key") or ""),
                    "add_bb_key": str(item.get("add_bb_key") or ""),
                    "delay_bb_key": str(item.get("delay_bb_key") or ""),
                    "max_bb_key": str(item.get("max_bb_key") or ""),
                    "tick_bb_key": str(item.get("tick_bb_key") or ""),
                }
            )
    return effects


def effect_text(effects: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for effect in effects:
        zone = ZONE_CN.get(str(effect.get("zone") or ""), str(effect.get("zone") or ""))
        element = ELEMENT_CN.get(str(effect.get("element") or ""), str(effect.get("element") or ""))
        if effect.get("kind") == "dynamic":
            keys = [
                effect.get("base_bb_key"),
                effect.get("add_bb_key"),
                effect.get("tick_bb_key"),
                effect.get("max_bb_key"),
                effect.get("delay_bb_key"),
            ]
            key_text = "/".join(str(key) for key in keys if key)
            parts.append(f"{zone}({element}) dyn:{key_text or '-'}")
        else:
            suffix = str(effect.get("bb_key") or "-")
            if effect.get("rate") is not None:
                suffix += f"={effect.get('rate')}"
            parts.append(f"{zone}({element}) {suffix}")
    return "<br>".join(parts) if parts else "-"


def source_cn(row: dict[str, Any]) -> str:
    source_name = str(row.get("source_name") or "")
    source_id = str(row.get("source_id") or "")
    if source_name and source_name != source_id:
        return source_name
    return source_id or source_name or "-"


def merge_values(existing: list[Any], incoming: list[Any]) -> list[Any]:
    seen = {json.dumps(item, ensure_ascii=False, sort_keys=True) for item in existing}
    merged = list(existing)
    for item in incoming:
        key = json.dumps(item, ensure_ascii=False, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged


def infer_source_kind(canonical: str, row: dict[str, Any]) -> str:
    if row.get("source_kind"):
        return str(row.get("source_kind"))
    guard = row.get("guard") if isinstance(row.get("guard"), dict) else {}
    if guard.get("weapon_id") or canonical.startswith("buff_wpn_"):
        return "weapon"
    if guard.get("suit_id") or canonical.startswith("buff_equipsuit_"):
        return "suit"
    if canonical.startswith("buff_common_"):
        return "common"
    if canonical.startswith("buff_chr_"):
        return "character"
    return str(row.get("kind") or "unknown")


def infer_source_id(canonical: str, row: dict[str, Any]) -> str:
    guard = row.get("guard") if isinstance(row.get("guard"), dict) else {}
    for key in ("weapon_id", "suit_id", "character_id"):
        if guard.get(key):
            return str(guard[key])
    if row.get("source_id"):
        return str(row.get("source_id"))
    if canonical.startswith("buff_chr_"):
        parts = canonical.split("_")
        if len(parts) >= 3:
            return "_".join(parts[:3])
    if canonical.startswith("buff_wpn_"):
        parts = canonical.split("_")
        if len(parts) >= 3:
            return "_".join(parts[:3])
    if canonical.startswith("buff_equipsuit_"):
        return str(guard.get("suit_id") or "equip")
    if canonical.startswith("buff_common_"):
        return "common"
    return ""


def append_unique(values: list[str], value: str) -> None:
    if value and value not in values:
        values.append(value)


def main() -> None:
    numeric_map = load_json("data/packet_semantics/buff_numeric_map.json").get("mappings", {})
    mechanism_rows = load_json("data/packet_semantics/mechanism_registry.json").get("mechanisms", [])
    registry = load_json("data/packet_semantics/rdps_semantics_registry.json")
    verified = registry.get("verified_effects") if isinstance(registry.get("verified_effects"), dict) else {}

    rows_by_buff: dict[str, dict[str, Any]] = {}

    def upsert(canonical: str, row: dict[str, Any], *, source_table: str, numeric_id: str | None = None) -> None:
        if not canonical:
            return
        effects = normalize_effects(row)
        include_empty_review = str(row.get("role") or "") == "effect" and source_table == "buff_numeric_map"
        if not effects and not include_empty_review:
            return
        target = rows_by_buff.setdefault(
            canonical,
            {
                "canonical_buff_id": canonical,
                "cn_name": "",
                "source_kind": infer_source_kind(canonical, row),
                "source_id": str(row.get("source_id") or row.get("weapon_id") or row.get("suit_id") or row.get("character_id") or infer_source_id(canonical, row)),
                "source_name": source_cn(row),
                "role": str(row.get("role") or ""),
                "numeric_ids": [],
                "effects": [],
                "source_tables": [],
                "guards": {},
                "review_reasons": [],
                "description_sample": str(row.get("description_sample") or ""),
                "reason": str(row.get("reason") or ""),
            },
        )
        if source_table not in target["source_tables"]:
            target["source_tables"].append(source_table)
        ids = [str(value) for value in row.get("numeric_ids") or [] if str(value)]
        if numeric_id:
            ids.append(str(numeric_id))
        target["numeric_ids"] = sorted(set(target["numeric_ids"]) | set(ids), key=lambda value: (not value.isdigit(), int(value) if value.isdigit() else value))
        target["effects"] = merge_values(target["effects"], effects)
        if row.get("weapon_id"):
            target["guards"]["weapon_id"] = row.get("weapon_id")
        if row.get("suit_id"):
            target["guards"]["suit_id"] = row.get("suit_id")
        if row.get("character_id"):
            target["guards"]["character_id"] = row.get("character_id")
        if row.get("loadout_guard"):
            target["guards"]["loadout_guard"] = row.get("loadout_guard")
        guard = row.get("guard") if isinstance(row.get("guard"), dict) else {}
        for key, value in guard.items():
            target["guards"][str(key)] = value
        if not target.get("cn_name") and canonical in verified:
            target["cn_name"] = str(verified[canonical].get("cn_name") or "")
        if canonical in verified:
            target["status"] = "verified"
        else:
            target.setdefault("status", "candidate")
        if not target["effects"]:
            append_unique(target["review_reasons"], "role=effect 但没有可直接展开的乘区，需要确认 runtime 展开逻辑")
        if target["source_name"] == target["source_id"] or str(target["source_name"]).startswith(("chr_", "wpn_", "suit_")):
            append_unique(target["review_reasons"], "缺少稳定中文来源名")
        if any(effect.get("kind") == "dynamic" for effect in target["effects"]):
            append_unique(target["review_reasons"], "动态倍率/延迟生效，需要确认叠层和时间窗")

    for row in mechanism_rows:
        if not isinstance(row, dict):
            continue
        upsert(str(row.get("canonical_buff_id") or ""), row, source_table="mechanism_registry")

    for canonical, row in verified.items():
        if not isinstance(row, dict):
            continue
        verified_row = dict(row)
        verified_row.setdefault("canonical_buff_id", canonical)
        verified_row.setdefault("source_kind", infer_source_kind(canonical, verified_row))
        verified_row.setdefault("source_id", infer_source_id(canonical, verified_row))
        verified_row.setdefault("source_name", verified_row.get("source") or verified_row.get("cn_name") or verified_row.get("source_id"))
        verified_row.setdefault("role", "effect")
        upsert(str(canonical), verified_row, source_table="rdps_semantics_registry")

    for numeric_id, row in numeric_map.items():
        if not isinstance(row, dict):
            continue
        upsert(str(row.get("canonical_buff_id") or ""), row, source_table="buff_numeric_map", numeric_id=str(numeric_id))

    rows = sorted(
        rows_by_buff.values(),
        key=lambda item: (
            str(item.get("source_kind") or ""),
            str(item.get("source_id") or ""),
            str(item.get("canonical_buff_id") or ""),
        ),
    )
    for row in rows:
        row["review_required"] = bool(row.get("review_reasons")) and row.get("status") != "verified"

    summary = {
        "total_candidates": len(rows),
        "verified": sum(1 for row in rows if row.get("status") == "verified"),
        "needs_review": sum(1 for row in rows if row.get("review_required")),
        "by_source_kind": Counter(str(row.get("source_kind") or "unknown") for row in rows),
        "by_zone": Counter(effect.get("zone") for row in rows for effect in row.get("effects") or []),
    }
    out_json = {
        "version": 1,
        "updated": "2026-05-30",
        "summary": {
            "total_candidates": summary["total_candidates"],
            "verified": summary["verified"],
            "needs_review": summary["needs_review"],
            "by_source_kind": dict(summary["by_source_kind"]),
            "by_zone": dict(summary["by_zone"]),
        },
        "candidates": rows,
    }

    json_path = ROOT / "data" / "packet_semantics" / "rdps_whitelist_candidates.json"
    json_path.write_text(json.dumps(out_json, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines: list[str] = []
    lines.append("# rDPS 通用白名单候选表")
    lines.append("")
    lines.append("更新时间：2026-05-30")
    lines.append("")
    lines.append("这张表是从 `buff_numeric_map.json` 和 `mechanism_registry.json` 自动生成的全量候选。")
    lines.append("它不是直接放行表；只有进入 `rdps_semantics_registry.json` 的 verified / known_non_rdps 才会被 strict gate 作为已确认语义使用。")
    lines.append("")
    lines.append("## 汇总")
    lines.append("")
    lines.append(f"- 候选总数：{summary['total_candidates']}")
    lines.append(f"- 已验证：{summary['verified']}")
    lines.append(f"- 需人工确认：{summary['needs_review']}")
    lines.append("- 来源类型：" + "，".join(f"{SOURCE_KIND_CN.get(k, k)} {v}" for k, v in summary["by_source_kind"].most_common()))
    lines.append("- 乘区：" + "，".join(f"{ZONE_CN.get(k, k)} {v}" for k, v in summary["by_zone"].most_common()))
    lines.append("")

    review_rows = [row for row in rows if row.get("review_required")]
    if review_rows:
        lines.append("## 需你优先确认")
        lines.append("")
        lines.append("| 来源 | buff | 数字ID | 乘区 | 需要确认 |")
        lines.append("|---|---|---|---|---|")
        for row in review_rows:
            lines.append(
                "| "
                + " | ".join(
                    [
                        md_escape(row.get("source_name") or row.get("source_id")),
                        md_escape(row.get("canonical_buff_id")),
                        md_escape(", ".join(row.get("numeric_ids") or []) or "-"),
                        md_escape(effect_text(row.get("effects") or [])),
                        md_escape("；".join(dict.fromkeys(row.get("review_reasons") or []))),
                    ]
                )
                + " |"
            )
        lines.append("")

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("source_kind") or "unknown")].append(row)

    for kind in ["character", "weapon", "suit", "common", "common_mechanic", "equip", "unknown"]:
        group = grouped.get(kind)
        if not group:
            continue
        title = SOURCE_KIND_CN.get(kind, kind)
        lines.append(f"## {title}")
        lines.append("")
        lines.append("| 状态 | 来源 | buff | 数字ID | 乘区 | 保护条件 |")
        lines.append("|---|---|---|---|---|---|")
        for row in group:
            guards = row.get("guards") or {}
            guard_text = "；".join(f"{key}={value}" for key, value in guards.items()) or "-"
            status = "已验证" if row.get("status") == "verified" else ("需确认" if row.get("review_required") else "候选")
            cn_name = row.get("cn_name")
            source = row.get("source_name") or row.get("source_id")
            if cn_name:
                source = f"{cn_name}<br>{source}"
            lines.append(
                "| "
                + " | ".join(
                    [
                        md_escape(status),
                        md_escape(source),
                        md_escape(row.get("canonical_buff_id")),
                        md_escape(", ".join(row.get("numeric_ids") or []) or "-"),
                        md_escape(effect_text(row.get("effects") or [])),
                        md_escape(guard_text),
                    ]
                )
                + " |"
            )
        lines.append("")

    md_path = ROOT / "docs" / "rdps_whitelist_candidates.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {md_path}")
    print(f"wrote {json_path}")
    print(json.dumps(out_json["summary"], ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
