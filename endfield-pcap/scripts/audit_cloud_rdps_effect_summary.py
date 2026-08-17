from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CLOUD_DIR = ROOT.parent / "cloud_samples" / "20260530_220016"
DEFAULT_DATASETS = {
    "all_versions": "rdps_effect_summary.jsonl",
    "v24_v25": "rdps_effect_summary_v24_v25.jsonl",
}
DEFAULT_MANUAL_MAP = "rdps_effect_audit_v24_v25_手工映射.csv"
REPORT_STEM = "rdps_cloud_strict_registry_audit"

ZONE_CN = {
    "atk": "攻击",
    "dmg_inc": "增伤",
    "amp": "增幅",
    "fragile": "脆弱",
    "vuln_taken": "承伤易伤",
    "res": "减抗",
    "combo": "连击增伤",
    "crit": "暴击",
    "speedup": "加速",
    "slow": "减速",
}

STATUS_CN = {
    "verified": "已确认 rDPS",
    "verified_prefix": "已确认 rDPS 前缀",
    "guard_mismatch": "疑似 guard 不匹配",
    "known_non_rdps": "已确认不进 rDPS",
    "non_allocatable_zone": "非 rDPS 乘区",
    "unresolved_allocatable": "未覆盖 rDPS-like key",
}


@dataclass(frozen=True)
class RegistryMatch:
    status: str
    canonical_key: str
    cn_name: str
    reason: str


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def iter_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                rows.append(item)
    return rows


def load_manual_map(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    try:
        handle = path.open("r", encoding="utf-8-sig", newline="")
    except OSError:
        return {}
    with handle:
        reader = csv.DictReader(handle)
        rows: dict[str, dict[str, str]] = {}
        for row in reader:
            event_key = str(row.get("event_key") or "")
            if event_key:
                rows[event_key] = dict(row)
        return rows


def md_escape(value: Any) -> str:
    text = str(value if value is not None else "")
    return text.replace("|", "\\|").replace("\n", "<br>")


def value_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def event_count(row: dict[str, Any]) -> int:
    try:
        return int(row.get("event_count") or 0)
    except (TypeError, ValueError):
        return 0


def battle_count(row: dict[str, Any]) -> int:
    try:
        return int(row.get("battle_count") or 0)
    except (TypeError, ValueError):
        return 0


def load_battle_metadata(cloud_dir: Path) -> dict[str, Any]:
    rows = iter_jsonl(cloud_dir / "battle_metadata.jsonl")
    versions = Counter(str(row.get("parser_version") or "") for row in rows)
    versions.pop("", None)
    return {
        "battle_rows": len(rows),
        "parser_versions": versions,
    }


def allowed_bb_keys(_entry: dict[str, Any]) -> bool:
    # The cloud summaries do not carry runtime BB key sets. Exact/prefix matching is
    # intentionally conservative about identity, while BB allow-list checks remain a
    # raw-trace preflight responsibility.
    return True


def guard_matches_summary(entry: dict[str, Any], row: dict[str, Any], event_key: str) -> bool:
    guard = entry.get("guard") if isinstance(entry.get("guard"), dict) else {}
    if not guard:
        return True

    source_guard = str(guard.get("source_character_key") or guard.get("source_character_id") or "")
    source_key = str(row.get("source_key") or "")
    if source_guard and source_key != source_guard:
        return False

    weapon_guard = str(guard.get("weapon_id") or "")
    if weapon_guard and not event_key.startswith(f"buff_{weapon_guard}"):
        return False

    suit_guard = str(guard.get("suit_id") or "")
    if suit_guard and not event_key.startswith("buff_equipsuit_"):
        return False

    # Source skill/family guards cannot be validated from aggregated cloud summary
    # rows. They are kept for raw-trace strict audit.
    return True


def build_registry_matcher(registry: dict[str, Any]):
    verified = registry.get("verified_effects") if isinstance(registry.get("verified_effects"), dict) else {}
    verified_by_key: dict[str, tuple[str, dict[str, Any]]] = {}
    for canonical, entry in verified.items():
        if not isinstance(entry, dict):
            continue
        canonical_text = str(canonical)
        verified_by_key.setdefault(canonical_text, (canonical_text, entry))
        for alias in entry.get("aliases") or []:
            if isinstance(alias, str) and alias:
                verified_by_key.setdefault(alias, (canonical_text, entry))
        for numeric_id in entry.get("numeric_ids") or []:
            if str(numeric_id):
                verified_by_key.setdefault(str(numeric_id), (canonical_text, entry))

    verified_prefixes = registry.get("verified_prefixes") if isinstance(registry.get("verified_prefixes"), list) else []
    known = registry.get("known_non_rdps") if isinstance(registry.get("known_non_rdps"), dict) else {}
    known_exact = known.get("exact_buff_ids") if isinstance(known.get("exact_buff_ids"), dict) else {}
    known_prefixes = known.get("prefixes") if isinstance(known.get("prefixes"), list) else []

    def match(row: dict[str, Any], allocatable_zones: set[str]) -> RegistryMatch:
        event_key = str(row.get("event_key") or "")
        zone = str(row.get("zone") or "")

        if event_key in verified_by_key:
            canonical, entry = verified_by_key[event_key]
            cn_name = str(entry.get("cn_name") or entry.get("source") or "")
            if not guard_matches_summary(entry, row, event_key):
                return RegistryMatch("guard_mismatch", canonical, cn_name, "summary source_key does not satisfy registry guard")
            return RegistryMatch("verified", canonical, cn_name, "")

        for entry in verified_prefixes:
            if not isinstance(entry, dict):
                continue
            prefix = str(entry.get("prefix") or "")
            if prefix and event_key.startswith(prefix) and allowed_bb_keys(entry):
                cn_name = str(entry.get("cn_name") or entry.get("source") or "")
                if not guard_matches_summary(entry, row, event_key):
                    return RegistryMatch("guard_mismatch", prefix, cn_name, "summary source_key does not satisfy registry prefix guard")
                return RegistryMatch("verified_prefix", prefix, cn_name, "")

        known_entry = known_exact.get(event_key)
        if isinstance(known_entry, dict) and allowed_bb_keys(known_entry):
            return RegistryMatch(
                "known_non_rdps",
                event_key,
                str(known_entry.get("cn_name") or known_entry.get("category") or ""),
                str(known_entry.get("reason") or known_entry.get("category") or ""),
            )

        for entry in known_prefixes:
            if not isinstance(entry, dict):
                continue
            prefix = str(entry.get("prefix") or "")
            if prefix and event_key.startswith(prefix) and allowed_bb_keys(entry):
                return RegistryMatch(
                    "known_non_rdps",
                    prefix,
                    str(entry.get("cn_name") or entry.get("category") or ""),
                    str(entry.get("reason") or entry.get("category") or ""),
                )

        if zone not in allocatable_zones:
            return RegistryMatch("non_allocatable_zone", "", ZONE_CN.get(zone, zone), "zone is outside registry allocatable_zones")

        return RegistryMatch("unresolved_allocatable", "", "", "not present in verified_effects/verified_prefixes/known_non_rdps")

    return match


def summarize_dataset(
    *,
    dataset: str,
    path: Path,
    matcher,
    allocatable_zones: set[str],
    manual_map: dict[str, dict[str, str]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = iter_jsonl(path)
    output_rows: list[dict[str, Any]] = []
    status_counts: Counter[str] = Counter()
    status_event_counts: Counter[str] = Counter()
    status_battle_counts: Counter[str] = Counter()
    zone_counts: Counter[str] = Counter()

    for row in rows:
        match = matcher(row, allocatable_zones)
        manual = manual_map.get(str(row.get("event_key") or ""), {})
        count = event_count(row)
        battles = battle_count(row)
        status_counts[match.status] += 1
        status_event_counts[match.status] += count
        status_battle_counts[match.status] += battles
        zone_counts[str(row.get("zone") or "")] += 1
        output_rows.append(
            {
                "dataset": dataset,
                "status": match.status,
                "status_cn": STATUS_CN.get(match.status, match.status),
                "event_key": str(row.get("event_key") or ""),
                "canonical_key": match.canonical_key,
                "cn_name": match.cn_name,
                "zone": str(row.get("zone") or ""),
                "zone_cn": ZONE_CN.get(str(row.get("zone") or ""), str(row.get("zone") or "")),
                "element": str(row.get("element") or ""),
                "rate": value_text(row.get("rate")),
                "base_rate": value_text(row.get("base_rate")),
                "tick_rate": value_text(row.get("tick_rate")),
                "max_rate": value_text(row.get("max_rate")),
                "source_key": str(row.get("source_key") or ""),
                "source_name": str(row.get("source_name") or ""),
                "effect_source": str(row.get("effect_source") or ""),
                "event_count": count,
                "battle_count": battles,
                "sample_battle_id": str(row.get("sample_battle_id") or ""),
                "first_created": str(row.get("first_created") or ""),
                "last_created": str(row.get("last_created") or ""),
                "parser_version": str(row.get("parser_version") or ""),
                "min_parser_version": str(row.get("min_parser_version") or ""),
                "max_parser_version": str(row.get("max_parser_version") or ""),
                "manual_mapping_entry": str(manual.get("手工表对应条目") or ""),
                "manual_conclusion": str(manual.get("映射结论") or ""),
                "manual_action": str(manual.get("处理建议") or ""),
                "manual_current_status": str(manual.get("当前状态") or ""),
                "reason": match.reason,
            }
        )

    summary = {
        "dataset": dataset,
        "path": path,
        "rows": len(rows),
        "status_counts": status_counts,
        "status_event_counts": status_event_counts,
        "status_battle_counts": status_battle_counts,
        "zone_counts": zone_counts,
    }
    return output_rows, summary


def aggregate_unresolved(rows: list[dict[str, Any]], dataset: str, limit: int = 40) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    for row in rows:
        if row["dataset"] != dataset or row["status"] != "unresolved_allocatable":
            continue
        key = (
            row["event_key"],
            row["zone"],
            row["element"],
            row["rate"],
            row["source_key"],
        )
        target = grouped.setdefault(
            key,
            {
                "event_key": row["event_key"],
                "zone": row["zone"],
                "element": row["element"],
                "rate": row["rate"],
                "source_key": row["source_key"],
                "source_name": row["source_name"],
                "event_count": 0,
                "battle_count": 0,
                "samples": [],
            },
        )
        target["event_count"] += int(row["event_count"])
        target["battle_count"] += int(row["battle_count"])
        if row["sample_battle_id"] and row["sample_battle_id"] not in target["samples"]:
            target["samples"].append(row["sample_battle_id"])

    values = sorted(grouped.values(), key=lambda item: (-int(item["battle_count"]), -int(item["event_count"]), item["event_key"]))
    return values[:limit]


def aggregate_guard_mismatch(rows: list[dict[str, Any]], dataset: str, limit: int = 25) -> list[dict[str, Any]]:
    selected = [row for row in rows if row["dataset"] == dataset and row["status"] == "guard_mismatch"]
    return sorted(selected, key=lambda item: (-int(item["battle_count"]), -int(item["event_count"]), item["event_key"]))[:limit]


def aggregate_unresolved_manual_hits(rows: list[dict[str, Any]], dataset: str, limit: int = 30) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row["dataset"] != dataset or row["status"] != "unresolved_allocatable":
            continue
        if not str(row.get("manual_conclusion") or "").startswith("命中"):
            continue
        target = grouped.setdefault(
            row["event_key"],
            {
                "event_key": row["event_key"],
                "manual_mapping_entry": row.get("manual_mapping_entry") or "",
                "manual_conclusion": row.get("manual_conclusion") or "",
                "manual_action": row.get("manual_action") or "",
                "zones": set(),
                "sources": Counter(),
                "event_count": 0,
                "battle_count": 0,
            },
        )
        target["zones"].add(f"{row['zone']}/{row['element']}@{row['rate']}")
        target["sources"][row["source_key"]] += int(row["battle_count"])
        target["event_count"] += int(row["event_count"])
        target["battle_count"] += int(row["battle_count"])
    values = sorted(grouped.values(), key=lambda item: (-int(item["battle_count"]), -int(item["event_count"]), item["event_key"]))
    return values[:limit]


def unresolved_manual_conclusions(rows: list[dict[str, Any]], dataset: str) -> Counter[str]:
    by_key: dict[str, str] = {}
    for row in rows:
        if row["dataset"] != dataset or row["status"] != "unresolved_allocatable":
            continue
        conclusion = str(row.get("manual_conclusion") or "<not_in_manual_csv>")
        by_key.setdefault(row["event_key"], conclusion)
    return Counter(by_key.values())


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def count_unique_status_keys(rows: list[dict[str, Any]], dataset: str, status: str) -> int:
    return len({row["event_key"] for row in rows if row["dataset"] == dataset and row["status"] == status})


def write_markdown(
    *,
    path: Path,
    summaries: list[dict[str, Any]],
    all_rows: list[dict[str, Any]],
    metadata: dict[str, Any],
    registry_path: Path,
    csv_path: Path,
) -> None:
    lines: list[str] = []
    lines.append("# 云端 rDPS registry 覆盖扫描")
    lines.append("")
    lines.append(f"- registry：`{registry_path}`")
    lines.append("- 说明：输入是云端旧 parser 产出的 timeline effect 聚合，不是原始 trace；本报告用于发现新 key/旧解析残留，raw strict preflight 仍以原始日志为准。")
    lines.append(f"- battle_metadata rows：{metadata.get('battle_rows', 0)}")
    versions = metadata.get("parser_versions") if isinstance(metadata.get("parser_versions"), Counter) else Counter()
    if versions:
        version_text = "；".join(f"{name}: {count}" for name, count in versions.most_common())
        lines.append(f"- parser versions：{version_text}")
    lines.append("")
    lines.append("## 总览")
    lines.append("")
    lines.append("| dataset | rows | verified | known_non_rdps | non_allocatable | unresolved keys | manual-hit unresolved | unresolved rows | unresolved events | guard mismatch |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for summary in summaries:
        dataset = str(summary["dataset"])
        status_counts: Counter[str] = summary["status_counts"]
        status_events: Counter[str] = summary["status_event_counts"]
        manual_hit_keys = sum(
            count
            for conclusion, count in unresolved_manual_conclusions(all_rows, dataset).items()
            if conclusion.startswith("命中")
        )
        lines.append(
            "| "
            + " | ".join(
                [
                    md_escape(dataset),
                    str(summary["rows"]),
                    str(status_counts.get("verified", 0) + status_counts.get("verified_prefix", 0)),
                    str(status_counts.get("known_non_rdps", 0)),
                    str(status_counts.get("non_allocatable_zone", 0)),
                    str(count_unique_status_keys(all_rows, dataset, "unresolved_allocatable")),
                    str(manual_hit_keys),
                    str(status_counts.get("unresolved_allocatable", 0)),
                    str(status_events.get("unresolved_allocatable", 0)),
                    str(status_counts.get("guard_mismatch", 0)),
                ]
            )
            + " |"
        )

    for summary in summaries:
        dataset = str(summary["dataset"])
        lines.append("")
        lines.append(f"## {dataset} 未覆盖 key")
        lines.append("")
        conclusions = unresolved_manual_conclusions(all_rows, dataset)
        if conclusions:
            text = "；".join(f"{name}: {count}" for name, count in conclusions.most_common())
            lines.append(f"- 按手工映射结论分组：{text}")
            lines.append("")

        manual_hits = aggregate_unresolved_manual_hits(all_rows, dataset)
        if manual_hits:
            lines.append("### 手工命中但 registry 未覆盖")
            lines.append("")
            lines.append("| event_key | 手工结论 | 手工条目 | zones | top source | battles | events | 建议 |")
            lines.append("|---|---|---|---|---|---:|---:|---|")
            for row in manual_hits:
                source = ""
                sources = row.get("sources")
                if isinstance(sources, Counter) and sources:
                    source = sources.most_common(1)[0][0]
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            md_escape(row["event_key"]),
                            md_escape(row["manual_conclusion"]),
                            md_escape(row["manual_mapping_entry"]),
                            md_escape("; ".join(sorted(row["zones"]))),
                            md_escape(source),
                            str(row["battle_count"]),
                            str(row["event_count"]),
                            md_escape(row["manual_action"]),
                        ]
                    )
                    + " |"
                )
            lines.append("")

        unresolved = aggregate_unresolved(all_rows, dataset)
        if not unresolved:
            lines.append("- 无未覆盖 allocatable key。")
        else:
            lines.append("| event_key | zone | element | rate | source | battles | events | 手工结论 | sample |")
            lines.append("|---|---|---|---:|---|---:|---:|---|---|")
            for row in unresolved:
                manual = next(
                    (
                        item
                        for item in all_rows
                        if item["dataset"] == dataset
                        and item["status"] == "unresolved_allocatable"
                        and item["event_key"] == row["event_key"]
                    ),
                    {},
                )
                source = row["source_key"]
                if row["source_name"]:
                    source += f" / {row['source_name']}"
                sample = "; ".join(row.get("samples") or [])[:160]
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            md_escape(row["event_key"]),
                            md_escape(f"{ZONE_CN.get(row['zone'], row['zone'])}({row['zone']})"),
                            md_escape(row["element"]),
                            md_escape(row["rate"]),
                            md_escape(source),
                            str(row["battle_count"]),
                            str(row["event_count"]),
                            md_escape(manual.get("manual_conclusion") or ""),
                            md_escape(sample),
                        ]
                    )
                    + " |"
                )

        guard_rows = aggregate_guard_mismatch(all_rows, dataset)
        if guard_rows:
            lines.append("")
            lines.append(f"## {dataset} guard mismatch")
            lines.append("")
            lines.append("| event_key | registry key | zone | source | battles | events | reason |")
            lines.append("|---|---|---|---|---:|---:|---|")
            for row in guard_rows:
                source = row["source_key"]
                if row["source_name"]:
                    source += f" / {row['source_name']}"
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            md_escape(row["event_key"]),
                            md_escape(row["canonical_key"]),
                            md_escape(row["zone"]),
                            md_escape(source),
                            str(row["battle_count"]),
                            str(row["event_count"]),
                            md_escape(row["reason"]),
                        ]
                    )
                    + " |"
                )

    lines.append("")
    lines.append("## 输出")
    lines.append("")
    lines.append(f"- CSV 全量：`{csv_path}`")
    lines.append(f"- Markdown 摘要：`{path}`")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scan cloud rDPS effect summaries against rdps_semantics_registry.")
    parser.add_argument("--cloud-dir", type=Path, default=DEFAULT_CLOUD_DIR)
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--dataset", action="append", default=[], help="Dataset mapping as name=filename. Defaults to all_versions and v24_v25.")
    parser.add_argument("--manual-map", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cloud_dir = args.cloud_dir.resolve()
    out_dir = (args.out_dir or cloud_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    datasets = dict(DEFAULT_DATASETS)
    for item in args.dataset:
        if "=" not in item:
            raise SystemExit(f"--dataset must be name=filename, got: {item}")
        name, filename = item.split("=", 1)
        datasets[name] = filename

    registry_path = ROOT / "data" / "packet_semantics" / "rdps_semantics_registry.json"
    registry = load_json(registry_path)
    allocatable_zones = set((registry.get("allocatable_zones") or {}).keys()) or {"atk", "dmg_inc", "amp", "fragile", "vuln_taken", "res", "combo"}
    matcher = build_registry_matcher(registry)
    manual_map = load_manual_map(args.manual_map or (cloud_dir / DEFAULT_MANUAL_MAP))

    all_rows: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    for dataset, filename in datasets.items():
        rows, summary = summarize_dataset(
            dataset=dataset,
            path=cloud_dir / filename,
            matcher=matcher,
            allocatable_zones=allocatable_zones,
            manual_map=manual_map,
        )
        all_rows.extend(rows)
        summaries.append(summary)

    csv_path = out_dir / f"{REPORT_STEM}.csv"
    md_path = out_dir / f"{REPORT_STEM}.md"
    write_csv(csv_path, all_rows)
    write_markdown(
        path=md_path,
        summaries=summaries,
        all_rows=all_rows,
        metadata=load_battle_metadata(cloud_dir),
        registry_path=registry_path,
        csv_path=csv_path,
    )

    for summary in summaries:
        status_counts: Counter[str] = summary["status_counts"]
        status_events: Counter[str] = summary["status_event_counts"]
        print(
            f"{summary['dataset']}: rows={summary['rows']} "
            f"verified={status_counts.get('verified', 0) + status_counts.get('verified_prefix', 0)} "
            f"known_non_rdps={status_counts.get('known_non_rdps', 0)} "
            f"non_allocatable={status_counts.get('non_allocatable_zone', 0)} "
            f"unresolved_keys={count_unique_status_keys(all_rows, str(summary['dataset']), 'unresolved_allocatable')} "
            f"unresolved_rows={status_counts.get('unresolved_allocatable', 0)} "
            f"unresolved_events={status_events.get('unresolved_allocatable', 0)} "
            f"guard_mismatch={status_counts.get('guard_mismatch', 0)}"
        )
    print(f"wrote {md_path}")
    print(f"wrote {csv_path}")


if __name__ == "__main__":
    main()
