from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.errors import AppError


REPO_ROOT = Path(__file__).resolve().parents[4]
LOCAL_SEMANTICS_ROOT = REPO_ROOT / "data" / "local_semantics"
SUPPORTED_SEMANTIC_KINDS = {"buff", "skill", "attribute_type"}


@lru_cache(maxsize=16)
def _load_json_cached(path_str: str) -> Any:
    path = Path(path_str)
    if not path.exists():
        raise AppError(status_code=503, code="semantic_index_missing", message="本地语义索引不存在，请先运行构建脚本。")
    return json.loads(path.read_text(encoding="utf-8"))


class LocalGameSemanticsService:
    def get_catalog_summary(self) -> dict[str, Any]:
        catalog = _load_json_cached(str(LOCAL_SEMANTICS_ROOT / "catalog.json"))
        modules = {}
        for kind, module in (catalog.get("modules") or {}).items():
            modules[kind] = {
                **module,
                "source": {"primary": "local_semantics"},
            }
        return {
            **catalog,
            "modules": modules,
            "sourceStrategy": {kind: "local_semantics" for kind in SUPPORTED_SEMANTIC_KINDS},
        }

    def list_entries(self, kind: str) -> dict[str, Any]:
        normalized_kind = self._normalize_kind(kind)
        manifest = _load_json_cached(str(LOCAL_SEMANTICS_ROOT / normalized_kind / "manifest.json"))
        return {
            "kind": normalized_kind,
            "count": manifest.get("count", 0),
            "entries": manifest.get("entries", []),
            "source": {"primary": "local_semantics"},
        }

    def get_entry_detail(self, kind: str, entry_id: str) -> dict[str, Any]:
        normalized_kind = self._normalize_kind(kind)
        manifest = _load_json_cached(str(LOCAL_SEMANTICS_ROOT / normalized_kind / "manifest.json"))
        entries = manifest.get("entries", [])
        manifest_entry = next((entry for entry in entries if str(entry.get("id")) == entry_id), None)
        if manifest_entry is None:
            raise AppError(status_code=404, code="semantic_entry_not_found", message="未找到对应语义条目。")

        details = _load_json_cached(str(LOCAL_SEMANTICS_ROOT / normalized_kind / "details.json"))
        detail = (details.get("entries") or {}).get(entry_id)
        if detail is None:
            raise AppError(status_code=404, code="semantic_detail_not_found", message="未找到对应语义详情。")

        return {
            "kind": normalized_kind,
            "id": entry_id,
            "manifestEntry": manifest_entry,
            "detail": detail,
            "source": {"primary": "local_semantics"},
        }

    def _normalize_kind(self, kind: str) -> str:
        if kind not in SUPPORTED_SEMANTIC_KINDS:
            raise AppError(status_code=404, code="semantic_kind_not_found", message="未找到对应语义分类。")
        return kind


local_game_semantics_service = LocalGameSemanticsService()
