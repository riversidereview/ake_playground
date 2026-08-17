from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.errors import AppError


REPO_ROOT = Path(__file__).resolve().parents[4]
AKEDATA_ROOT = REPO_ROOT / "data" / "akedata"
LOCAL_STATIC_ROOT = REPO_ROOT / "data" / "local_static"
LOCAL_TABLE_ROOT = REPO_ROOT / "data" / "local_tables"
SUPPORTED_KINDS = {"character", "weapon", "enemy", "equip", "dungeon", "buff", "skill", "attribute_type"}
LOCAL_STATIC_KINDS = {"buff", "skill", "attribute_type"}
LOCAL_TABLE_KINDS = {"character", "weapon", "enemy", "equip", "dungeon"}

AKEDATA_ID_FIELDS = {
    "character": "charId",
    "weapon": "weaponId",
    "enemy": "templateId",
    "equip": "suitID",
    "dungeon": "templateId",
    "buff": "id",
    "skill": "id",
    "attribute_type": "id",
}


class LocalGameCatalogService:
    def get_catalog_summary(self) -> dict[str, Any]:
        summary = self._load_json(AKEDATA_ROOT / "catalog.json")
        local_summary = self._load_json(LOCAL_STATIC_ROOT / "catalog.json", required=False)
        local_table_summary = self._load_json(LOCAL_TABLE_ROOT / "catalog.json", required=False)

        modules = dict(summary.get("modules", {}))
        for kind in LOCAL_TABLE_KINDS:
            local_module = self._safe_local_module(local_table_summary, kind)
            if not local_module:
                modules[kind] = {
                    **modules.get(kind, {}),
                    "source": {"primary": "akedata_mirror"},
                }
                continue
            local_module = self._with_merged_count(kind, local_module, primary="local_table")
            modules[kind] = {
                **local_module,
                "source": self._build_source_info(kind, primary="local_table"),
            }

        for kind in LOCAL_STATIC_KINDS:
            local_module = self._safe_local_module(local_summary, kind)
            if not local_module:
                modules[kind] = {
                    **modules.get(kind, {}),
                    "source": {"primary": "akedata_mirror"},
                }
                continue
            local_module = self._with_merged_count(kind, local_module, primary="local_static")
            modules[kind] = {
                **local_module,
                "source": self._build_source_info(kind, primary="local_static"),
            }

        for kind in SUPPORTED_KINDS - LOCAL_STATIC_KINDS - LOCAL_TABLE_KINDS:
            modules[kind] = {
                **modules.get(kind, {}),
                "source": {"primary": "akedata_mirror"},
            }

        return {
            **summary,
            "modules": modules,
            "sourceStrategy": {
                "character": "local_table_preferred",
                "weapon": "local_table_preferred",
                "enemy": "local_table_preferred",
                "equip": "local_table_preferred",
                "dungeon": "local_table_preferred",
                "buff": "local_static_preferred",
                "skill": "local_static_preferred",
                "attribute_type": "local_static_preferred",
            },
        }

    def list_entries(self, kind: str) -> dict[str, Any]:
        normalized_kind = self._normalize_kind(kind)
        if self._use_local_table(normalized_kind):
            local_manifest = self._load_json(LOCAL_TABLE_ROOT / normalized_kind / "manifest.json")
            entries = self._merge_generated_entries(normalized_kind, local_manifest.get("entries", []), primary="local_table")
            return {
                "kind": normalized_kind,
                "count": len(entries),
                "entries": entries,
                "source": self._build_source_info(normalized_kind, primary="local_table"),
            }
        if self._use_local_static(normalized_kind):
            local_manifest = self._load_json(LOCAL_STATIC_ROOT / normalized_kind / "manifest.json")
            entries = self._merge_local_static_entries(normalized_kind, local_manifest.get("entries", []))
            return {
                "kind": normalized_kind,
                "count": len(entries),
                "entries": entries,
                "source": self._build_source_info(normalized_kind, primary="local_static"),
            }

        manifest = self._load_json(AKEDATA_ROOT / normalized_kind / "manifest.json")
        return {
            "kind": normalized_kind,
            "count": len(manifest),
            "entries": manifest,
            "source": {"primary": "akedata_mirror"},
        }

    def get_entry_detail(self, kind: str, entry_id: str) -> dict[str, Any]:
        normalized_kind = self._normalize_kind(kind)
        if self._use_local_table(normalized_kind):
            local_manifest = self._load_json(LOCAL_TABLE_ROOT / normalized_kind / "manifest.json")
            merged_entries = self._merge_generated_entries(normalized_kind, local_manifest.get("entries", []), primary="local_table")
            manifest_entry = self._find_local_entry(merged_entries, entry_id)
            detail = self._load_generated_detail(normalized_kind, manifest_entry)
            return {
                "kind": normalized_kind,
                "id": entry_id,
                "manifestEntry": manifest_entry,
                "detail": detail,
                "source": manifest_entry.get("source") or self._build_source_info(normalized_kind, primary="local_table"),
            }
        if self._use_local_static(normalized_kind):
            local_manifest = self._load_json(LOCAL_STATIC_ROOT / normalized_kind / "manifest.json")
            merged_entries = self._merge_local_static_entries(normalized_kind, local_manifest.get("entries", []))
            manifest_entry = self._find_local_entry(merged_entries, entry_id)
            detail = self._load_local_static_detail(normalized_kind, manifest_entry)
            payload: dict[str, Any] = {
                "kind": normalized_kind,
                "id": entry_id,
                "manifestEntry": manifest_entry,
                "detail": detail,
                "source": manifest_entry.get("source") or self._build_source_info(normalized_kind, primary="local_static"),
            }
            if "localBinaryPath" in manifest_entry:
                payload["localBinary"] = {
                    "path": manifest_entry.get("localBinaryPath"),
                    "projectPath": manifest_entry.get("localBinaryProjectPath"),
                    "size": manifest_entry.get("localBinarySize"),
                }
            if "binaryProbe" in manifest_entry:
                payload["binaryProbe"] = manifest_entry.get("binaryProbe")
            return payload

        manifest_entries = self._load_json(AKEDATA_ROOT / normalized_kind / "manifest.json")
        manifest_entry = self._find_manifest_entry(normalized_kind, manifest_entries, entry_id)
        detail = self._load_json(AKEDATA_ROOT / normalized_kind / "items" / f"{entry_id}.json")
        return {
            "kind": normalized_kind,
            "id": entry_id,
            "manifestEntry": manifest_entry,
            "detail": detail,
            "source": {"primary": "akedata_mirror"},
        }

    def _safe_local_module(self, summary: dict[str, Any] | None, kind: str) -> dict[str, Any] | None:
        if not summary:
            return None
        modules = summary.get("modules")
        if not isinstance(modules, dict):
            return None
        module = modules.get(kind)
        return module if isinstance(module, dict) else None

    def _with_merged_count(self, kind: str, module: dict[str, Any], primary: str) -> dict[str, Any]:
        manifest_path = LOCAL_STATIC_ROOT / kind / "manifest.json" if primary == "local_static" else LOCAL_TABLE_ROOT / kind / "manifest.json"
        if not manifest_path.exists():
            return module
        local_manifest = self._load_json(manifest_path)
        local_entries = local_manifest.get("entries", [])
        merged_count = len(self._merge_generated_entries(kind, local_entries, primary=primary))
        local_count = int(module.get("count") or len(local_entries))
        return {
            **module,
            "count": merged_count,
            "localCount": local_count,
            "akedataSupplementCount": max(0, merged_count - local_count),
        }

    def _use_local_static(self, kind: str) -> bool:
        return kind in LOCAL_STATIC_KINDS and (LOCAL_STATIC_ROOT / kind / "manifest.json").exists()

    def _use_local_table(self, kind: str) -> bool:
        return kind in LOCAL_TABLE_KINDS and (LOCAL_TABLE_ROOT / kind / "manifest.json").exists()

    def _merge_local_static_entries(self, kind: str, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return self._merge_generated_entries(kind, entries, primary="local_static")

    def _merge_generated_entries(self, kind: str, entries: list[dict[str, Any]], primary: str) -> list[dict[str, Any]]:
        akedata_entries = self._load_akedata_manifest_map(kind)
        merged: list[dict[str, Any]] = []
        local_ids: set[str] = set()
        for entry in entries:
            entry_id = str(entry.get("id"))
            local_ids.add(entry_id)
            akedata_entry = akedata_entries.get(entry_id, {})
            merged.append({**akedata_entry, **entry, "source": self._build_source_info(kind, primary=primary)})
        for entry_id in sorted(set(akedata_entries) - local_ids):
            akedata_entry = akedata_entries[entry_id]
            merged.append(
                {
                    "id": entry_id,
                    **akedata_entry,
                    "source": {
                        "primary": "akedata_mirror",
                        "includedBy": f"{primary}_preferred_union",
                    },
                }
            )
        return merged

    def _load_akedata_manifest_map(self, kind: str) -> dict[str, dict[str, Any]]:
        manifest_path = AKEDATA_ROOT / kind / "manifest.json"
        if not manifest_path.exists():
            return {}
        manifest = self._load_json(manifest_path)
        id_field = AKEDATA_ID_FIELDS[kind]
        entries: dict[str, dict[str, Any]] = {}
        for item in manifest:
            entry_id = str(item.get(id_field))
            if entry_id:
                entries[entry_id] = item
        return entries

    def _load_local_static_detail(self, kind: str, manifest_entry: dict[str, Any]) -> dict[str, Any]:
        detail_path_str = manifest_entry.get("decodedDetailPath") or manifest_entry.get("detailPath")
        if detail_path_str:
            detail_path = REPO_ROOT / Path(detail_path_str.replace("/", "\\"))
            if detail_path.exists():
                return self._load_json(detail_path)

        entry_id = str(manifest_entry.get("id"))
        fallback_path = AKEDATA_ROOT / kind / "items" / f"{entry_id}.json"
        if fallback_path.exists():
            return self._normalize_akedata_detail(kind, entry_id, self._load_json(fallback_path))

        return {
            "id": entry_id,
            "decodedAvailable": False,
            "localBinaryProjectPath": manifest_entry.get("localBinaryProjectPath"),
            "localBinarySize": manifest_entry.get("localBinarySize"),
        }

    def _load_generated_detail(self, kind: str, manifest_entry: dict[str, Any]) -> dict[str, Any]:
        detail_path_str = manifest_entry.get("detailPath")
        if detail_path_str:
            detail_path = REPO_ROOT / Path(detail_path_str.replace("/", "\\"))
            if detail_path.exists():
                return self._load_json(detail_path)
        entry_id = str(manifest_entry.get("id"))
        fallback_path = AKEDATA_ROOT / kind / "items" / f"{entry_id}.json"
        if fallback_path.exists():
            return self._normalize_akedata_detail(kind, entry_id, self._load_json(fallback_path))
        raise AppError(status_code=503, code="catalog_data_missing", message="本地生成的静态详情不存在，请先运行构建脚本。")

    def _normalize_akedata_detail(self, kind: str, entry_id: str, detail: Any) -> Any:
        if not isinstance(detail, dict):
            return detail
        normalized = dict(detail)
        normalized.setdefault("id", entry_id)
        id_field = AKEDATA_ID_FIELDS.get(kind)
        if id_field:
            normalized.setdefault(id_field, entry_id)
        if kind == "dungeon":
            normalized.setdefault("templateId", normalized.get("dungeonSeriesId", entry_id))
        return normalized

    def _find_local_entry(self, entries: list[dict[str, Any]], entry_id: str) -> dict[str, Any]:
        for entry in entries:
            if str(entry.get("id")) == entry_id:
                return entry
        raise AppError(status_code=404, code="catalog_entry_not_found", message="未找到对应静态数据条目。")

    def _find_manifest_entry(
        self,
        kind: str,
        manifest_entries: list[dict[str, Any]],
        entry_id: str,
    ) -> dict[str, Any]:
        id_field = AKEDATA_ID_FIELDS[kind]
        for entry in manifest_entries:
            if str(entry.get(id_field)) == entry_id:
                return entry
        raise AppError(status_code=404, code="catalog_entry_not_found", message="未找到对应静态数据条目。")

    def _build_source_info(self, kind: str, primary: str) -> dict[str, Any]:
        payload: dict[str, Any] = {"primary": primary}
        if kind in {"buff", "skill"}:
            payload["decodedSupplement"] = "akedata_mirror"
        if kind == "attribute_type":
            payload["decodedSupplement"] = "local_attribute_table"
        if kind in {"character", "weapon", "enemy", "dungeon"} and primary == "local_table":
            payload["decodedSupplement"] = "i18n_text_table_cn"
        if kind == "equip" and primary == "local_table":
            payload["decodedSupplement"] = "skill_patch_table_cn"
        return payload

    def _normalize_kind(self, kind: str) -> str:
        if kind not in SUPPORTED_KINDS:
            raise AppError(status_code=404, code="catalog_kind_not_found", message="未找到对应静态数据分类。")
        return kind

    def _load_json(self, path: Path, required: bool = True) -> Any:
        if not path.exists():
            if required:
                raise AppError(
                    status_code=503,
                    code="catalog_data_missing",
                    message="本地静态数据尚未同步，请先运行同步脚本。",
                )
            return None
        return json.loads(path.read_text(encoding="utf-8"))


local_game_catalog_service = LocalGameCatalogService()
