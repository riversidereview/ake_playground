from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
from pathlib import Path
from typing import Any

from .game_path import ensure_configured_game_dir_interactive, is_valid_game_dir
from .logging_utils import configure_logging
from .rdps_audit import (
    audit_trace,
    audit_trace_batch,
    audit_truth_jsonl,
    format_audit_markdown,
    format_batch_audit_markdown,
    format_truth_audit_html,
    format_truth_audit_markdown,
)
from .packet_resolver import PacketResolver
from .runtime_paths import bundle_root
from .trace_bridge import default_trace_file, make_archive_trace_file
from .truth_context import default_truth_db_file, default_truth_jsonl_file, default_truth_log_file, export_truth_context


def _resolve_dll_dir(raw_dll_dir: Path | None) -> Path:
    dll_dir = raw_dll_dir
    if dll_dir is None:
        try:
            dll_dir = ensure_configured_game_dir_interactive()
        except Exception as exc:  # noqa: BLE001 - startup must explain the manual fallback.
            raise SystemExit(
                "未配置终末地游戏目录，也无法打开路径选择窗口。"
                '请使用 --dll-dir "D:\\Hypergryph Launcher\\games\\Endfield Game" 手动指定。'
            ) from exc
    if dll_dir is None:
        raise SystemExit(
            "未选择终末地游戏目录。"
            '如需命令行启动，请使用 --dll-dir "D:\\Hypergryph Launcher\\games\\Endfield Game" 手动指定。'
        )

    dll_dir = dll_dir.resolve()
    if not is_valid_game_dir(dll_dir):
        raise SystemExit(f"所选目录无效，未找到 Endfield.exe 或 GameAssembly.dll：{dll_dir}")
    return dll_dir


def _maybe_build_packet_resolver_bundle(packet_root: Path, bundle_path: Path) -> dict[str, Any]:
    script_path = bundle_root() / "infra" / "scripts" / "build_packet_resolver_bundle.py"
    if not script_path.exists():
        PacketResolver()
        return {}
    try:
        spec = importlib.util.spec_from_file_location("packet_bundle_builder", script_path)
        if spec is None or spec.loader is None:
            PacketResolver()
            return {}
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if hasattr(module, "build_best_available_bundle"):
            bundle = module.build_best_available_bundle(packet_root.resolve())
        else:
            bundle = module.build_bundle(packet_root.resolve())
        module._write_json(bundle_path, bundle)
        return bundle if isinstance(bundle, dict) else {}
    except Exception:
        PacketResolver()
        return {}


def _resolver_bundle_paths() -> tuple[Path, Path]:
    packet_root = bundle_root() / "data" / "packet_semantics"
    return packet_root, packet_root / "packet_resolver_bundle.json"


def _collect_audit_batch_trace_files(args: argparse.Namespace) -> list[Path]:
    files: list[Path] = [path for path in args.trace_file if path is not None]
    patterns = args.glob or ["*.log", "*.dat"]
    for trace_dir in args.trace_dir:
        if trace_dir is None or not trace_dir.exists():
            continue
        for pattern in patterns:
            iterator = trace_dir.rglob(pattern) if args.recursive else trace_dir.glob(pattern)
            files.extend(path for path in iterator if path.is_file())
    unique: dict[str, Path] = {}
    for path in files:
        resolved = path.resolve()
        unique.setdefault(str(resolved).lower(), resolved)
    ordered = sorted(unique.values(), key=lambda item: str(item).lower())
    if args.limit and args.limit > 0:
        ordered = ordered[: args.limit]
    return ordered


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Endfield packet capture DPS overlay")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve = subparsers.add_parser("serve", help="Run the packet capture service and DPS overlay")
    serve.add_argument("--ws-port", type=int, default=29325)
    serve.add_argument("--log-dir", type=Path, default=Path("logs"))
    serve.add_argument("--log-level", default="INFO")
    serve.add_argument("--game-exe", default="Endfield.exe")
    serve.add_argument("--npcap-device", default="auto")
    serve.add_argument(
        "--dll-dir",
        type=Path,
        default=None,
        help="Directory containing Endfield.exe and GameAssembly.dll",
    )
    serve.add_argument("--no-overlay", action="store_true", help="Run the service without opening the tkinter DPS overlay")
    serve.add_argument("--no-trace", action="store_true", help="Do not write legacy dxg_trace.dat-compatible lines")
    serve.add_argument("--trace-file", type=Path, default=None, help="Trace file consumed by overlay.py")
    serve.add_argument("--status-file", type=Path, default=None, help="Status JSON file consumed by overlay.py")
    serve.add_argument("--debug", action="store_true", help="Write parsed debug messages to local JSON files")
    serve.add_argument("--debug-dir", type=Path, default=Path("debug"))
    serve.add_argument(
        "--merge-multi-phase-enemy-battles",
        action="store_true",
        help="Merge configured multi-phase boss fights into a single battle until the tracked enemy dies",
    )
    root = bundle_root()
    configured_key = os.environ.get("ENDFIELD_RSA_KEY_FILE", "").strip()
    default_key = Path(configured_key).expanduser() if configured_key else root / "secrets" / "client_privkey.pem"
    serve.add_argument(
        "--rsa-key-txt",
        type=Path,
        default=default_key,
        help="Path to a user-supplied PEM key (or set ENDFIELD_RSA_KEY_FILE)",
    )
    serve.add_argument("--name-index", type=Path, default=root / "jsondata" / "CharacterNameIndex.json")

    diag = subparsers.add_parser("diag", help="Print game connection and Npcap diagnostics")
    diag.add_argument("--watch-seconds", type=int, default=0)
    diag.add_argument("--out", type=Path, default=None)

    audit = subparsers.add_parser("audit", help="Audit rDPS packet evidence from a trace file")
    audit.add_argument("--trace-file", type=Path, default=default_trace_file())
    audit.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    audit.add_argument("--out", type=Path, default=None, help="Write the audit report to this path")

    audit_batch = subparsers.add_parser("audit-batch", help="Audit rDPS evidence from multiple trace files")
    audit_batch.add_argument("--trace-file", type=Path, action="append", default=[])
    audit_batch.add_argument("--trace-dir", type=Path, action="append", default=[])
    audit_batch.add_argument("--glob", action="append", default=None, help="File glob under each trace dir, e.g. *.log")
    audit_batch.add_argument("--recursive", action="store_true", help="Search trace dirs recursively")
    audit_batch.add_argument("--limit", type=int, default=0, help="Limit number of files after sorting")
    audit_batch.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    audit_batch.add_argument("--out", type=Path, default=None, help="Write the batch audit report to this path")

    audit_truth = subparsers.add_parser("audit-truth", help="Audit rDPS runtime truth directly from truth jsonl")
    audit_truth.add_argument("--truth-jsonl", type=Path, default=default_truth_jsonl_file())
    audit_truth.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    audit_truth.add_argument("--out", type=Path, default=None, help="Write the audit report to this path")

    audit_truth_viewer = subparsers.add_parser("audit-truth-viewer", help="Generate HTML viewer directly from truth jsonl")
    audit_truth_viewer.add_argument("--truth-jsonl", type=Path, default=default_truth_jsonl_file())
    audit_truth_viewer.add_argument("--out", type=Path, default=Path("reports") / "latest_truth_audit_viewer.html")

    audit_viewer = subparsers.add_parser("audit-viewer", help="Generate loadout and buff event audit HTML")
    audit_viewer.add_argument("--trace-file", type=Path, default=default_trace_file())
    audit_viewer.add_argument("--out", type=Path, default=Path("reports") / "latest_battle_audit_viewer.html")

    truth_context = subparsers.add_parser("truth-context", help="Export runtime truth + static rdps analysis context")
    truth_context.add_argument("--truth-jsonl", type=Path, default=default_truth_jsonl_file())
    truth_context.add_argument("--truth-log", type=Path, default=default_truth_log_file())
    truth_context.add_argument("--truth-db", type=Path, default=default_truth_db_file())
    truth_context.add_argument("--out-json", type=Path, default=Path("reports") / "rdps_truth_context.json")
    truth_context.add_argument("--out-md", type=Path, default=Path("reports") / "rdps_truth_context.md")

    truth_report = subparsers.add_parser("truth-report", help="Generate the full runtime truth report bundle")
    truth_report.add_argument("--truth-jsonl", type=Path, default=default_truth_jsonl_file())
    truth_report.add_argument("--truth-log", type=Path, default=default_truth_log_file())
    truth_report.add_argument("--truth-db", type=Path, default=default_truth_db_file())
    truth_report.add_argument("--out-dir", type=Path, default=Path("reports"))

    build_packet_bundle = subparsers.add_parser(
        "build-packet-resolver-bundle",
        help="Compile the packet resolver bundle from canonical export/direct semantics when available",
    )
    packet_root, bundle_path = _resolver_bundle_paths()
    build_packet_bundle.add_argument("--packet-root", type=Path, default=packet_root)
    build_packet_bundle.add_argument("--out", type=Path, default=bundle_path)

    return parser


def run_diag() -> int:
    from .diagnostic import collect_diagnostic_report

    print(collect_diagnostic_report(watch_seconds=0), end="")
    return 0


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "diag":
        configure_logging("INFO")
        from .diagnostic import collect_diagnostic_report

        text = collect_diagnostic_report(watch_seconds=max(0, int(args.watch_seconds)))
        if args.out is not None:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(text, encoding="utf-8-sig")
        else:
            print(text, end="")
        return 0
    if args.command == "audit":
        configure_logging("INFO")
        result = audit_trace(args.trace_file.resolve())
        text = (
            json.dumps(result, ensure_ascii=False, indent=2)
            if args.json
            else format_audit_markdown(result)
        )
        if args.out is not None:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(text, encoding="utf-8")
        else:
            print(text)
        return 0 if result.get("ok") else 2
    if args.command == "audit-batch":
        configure_logging("INFO")
        trace_files = _collect_audit_batch_trace_files(args)
        result = audit_trace_batch(trace_files)
        text = (
            json.dumps(result, ensure_ascii=False, indent=2)
            if args.json
            else format_batch_audit_markdown(result)
        )
        if args.out is not None:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(text, encoding="utf-8")
        else:
            print(text)
        return 0 if result.get("ok") else 2
    if args.command == "audit-truth":
        configure_logging("INFO")
        result = audit_truth_jsonl(args.truth_jsonl.resolve())
        text = (
            json.dumps(result, ensure_ascii=False, indent=2)
            if args.json
            else format_truth_audit_markdown(result)
        )
        if args.out is not None:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(text, encoding="utf-8")
        else:
            print(text)
        return 0 if result.get("ok") else 2
    if args.command == "audit-truth-viewer":
        configure_logging("INFO")
        result = audit_truth_jsonl(args.truth_jsonl.resolve())
        html = format_truth_audit_html(result)
        out_path = args.out.resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(html, encoding="utf-8")
        print(f"wrote {out_path}")
        print(
            f"loadout={result.get('coverage', {}).get('loadout_rows', 0)} "
            f"buff_ids={result.get('coverage', {}).get('unique_buff_ids', 0)} "
            f"damage={result.get('coverage', {}).get('damage_events', 0)}"
        )
        return 0 if result.get("ok") else 2
    if args.command == "audit-viewer":
        configure_logging("INFO")
        from parser_core.audit_viewer import write_audit_viewer_html
        from parser_core.unified import parse_overlay_battle_snapshot_text

        trace_path = args.trace_file.resolve()
        text = trace_path.read_text(encoding="utf-8", errors="ignore")
        snapshot = parse_overlay_battle_snapshot_text(text, file_name=str(trace_path))
        out_path = write_audit_viewer_html(snapshot, args.out)
        print(f"wrote {out_path.resolve()}")
        print(f"loadout={len(snapshot.get('loadout') or [])} buff_events={len(snapshot.get('buff_events') or [])}")
        return 0
    if args.command == "truth-context":
        configure_logging("INFO")
        outputs = export_truth_context(
            truth_jsonl=args.truth_jsonl.resolve(),
            truth_log=args.truth_log.resolve(),
            truth_db=args.truth_db.resolve(),
            out_json=args.out_json.resolve(),
            out_md=args.out_md.resolve(),
        )
        for key, path in outputs.items():
            print(f"{key}={path}")
        return 0
    if args.command == "truth-report":
        configure_logging("INFO")
        out_dir = args.out_dir.resolve()
        out_dir.mkdir(parents=True, exist_ok=True)

        truth_jsonl = args.truth_jsonl.resolve()
        truth_log = args.truth_log.resolve()
        truth_db = args.truth_db.resolve()

        packet_root, bundle_path = _resolver_bundle_paths()
        _maybe_build_packet_resolver_bundle(packet_root, bundle_path)

        context_outputs = export_truth_context(
            truth_jsonl=truth_jsonl,
            truth_log=truth_log,
            truth_db=truth_db,
            out_json=out_dir / "rdps_truth_context.json",
            out_md=out_dir / "rdps_truth_context.md",
        )
        truth_audit = audit_truth_jsonl(truth_jsonl)
        truth_audit_json = out_dir / "rdps_truth_audit.json"
        truth_audit_md = out_dir / "rdps_truth_audit.md"
        truth_audit_viewer = out_dir / "latest_truth_audit_viewer.html"
        truth_audit_json.write_text(json.dumps(truth_audit, ensure_ascii=False, indent=2), encoding="utf-8")
        truth_audit_md.write_text(format_truth_audit_markdown(truth_audit), encoding="utf-8")
        truth_audit_viewer.write_text(format_truth_audit_html(truth_audit), encoding="utf-8")

        index_path = out_dir / "truth_report_index.md"
        index_lines = [
            "# Truth Report",
            "",
            f"- truth_jsonl: `{truth_jsonl}`",
            f"- truth_log: `{truth_log}`",
            f"- truth_db: `{truth_db}`",
            "",
            "## Outputs",
            f"- packet_resolver_bundle: `{bundle_path}`",
            f"- context_json: `{context_outputs['json']}`",
            f"- context_md: `{context_outputs['markdown']}`",
            f"- truth_audit_json: `{truth_audit_json}`",
            f"- truth_audit_md: `{truth_audit_md}`",
            f"- truth_audit_viewer: `{truth_audit_viewer}`",
        ]
        index_path.write_text("\n".join(index_lines) + "\n", encoding="utf-8")

        print(f"context_json={context_outputs['json']}")
        print(f"context_md={context_outputs['markdown']}")
        print(f"packet_resolver_bundle={bundle_path}")
        print(f"truth_audit_json={truth_audit_json}")
        print(f"truth_audit_md={truth_audit_md}")
        print(f"truth_audit_viewer={truth_audit_viewer}")
        print(f"index_md={index_path}")
        return 0 if truth_audit.get("ok") else 2
    if args.command == "build-packet-resolver-bundle":
        configure_logging("INFO")
        bundle = _maybe_build_packet_resolver_bundle(args.packet_root.resolve(), args.out.resolve())
        content_summary = bundle.get("content_summary") if isinstance(bundle.get("content_summary"), dict) else {}
        buffs_summary = content_summary.get("buffs") if isinstance(content_summary.get("buffs"), dict) else {}
        skills_summary = content_summary.get("skills") if isinstance(content_summary.get("skills"), dict) else {}
        attrs_summary = content_summary.get("attribute_types") if isinstance(content_summary.get("attribute_types"), dict) else {}
        index_summary = ((bundle.get("indexes") or {}).get("summary") or {}) if isinstance(bundle.get("indexes"), dict) else {}
        print(f"packet_resolver_bundle={args.out.resolve()}")
        print(
            "content="
            f"buffs:{int(buffs_summary.get('count') or 0)} "
            f"skills:{int(skills_summary.get('count') or 0)} "
            f"attribute_types:{int(attrs_summary.get('count') or 0)} "
            f"assign_patterns:{int(buffs_summary.get('assignment_pattern_count') or 0) + int(skills_summary.get('assignment_pattern_count') or 0)}"
        )
        print(
            "indexes="
            f"parent_rules:{int(((index_summary.get('parent_rules') or {}).get('buffs') or 0)) + int(((index_summary.get('parent_rules') or {}).get('skills') or 0))} "
            f"created_parents:{int(index_summary.get('created_buff_parent_keys') or 0)} "
            f"referenced_buffs:{int(index_summary.get('referenced_buff_parent_keys') or 0)} "
            f"referenced_skills:{int(index_summary.get('referenced_skill_parent_keys') or 0)}"
        )
        return 0

    configure_logging(args.log_level)
    from .service import DamageLogService, ServiceConfig

    dll_dir = _resolve_dll_dir(args.dll_dir)
    packet_root, bundle_path = _resolver_bundle_paths()
    _maybe_build_packet_resolver_bundle(packet_root, bundle_path)
    log_dir = args.log_dir.resolve()
    trace_file = (
        args.trace_file.resolve()
        if args.trace_file is not None
        else make_archive_trace_file(log_dir)
    ) if not bool(args.no_trace) else None
    config = ServiceConfig(
        ws_port=args.ws_port,
        log_dir=log_dir,
        log_level=args.log_level,
        game_exe=args.game_exe,
        npcap_device=args.npcap_device,
        dll_dir=dll_dir,
        debug_enabled=bool(args.debug),
        debug_dir=args.debug_dir.resolve(),
        rsa_key_txt=args.rsa_key_txt.resolve(),
        name_index_path=args.name_index.resolve(),
        trace_file=trace_file,
        status_file=args.status_file.resolve() if args.status_file is not None else None,
        trace_enabled=not bool(args.no_trace),
        merge_multi_phase_enemy_battles=bool(args.merge_multi_phase_enemy_battles),
    )
    if args.no_overlay:
        service = DamageLogService(config)
        asyncio.run(service.run())
    else:
        from .runner import run_with_overlay

        return run_with_overlay(config)
    return 0

