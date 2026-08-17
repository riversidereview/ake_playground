from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.errors import AppError


REPO_ROOT = Path(__file__).resolve().parents[4]
HINTS_PATH = REPO_ROOT / "data" / "local_semantics" / "classifier_hints.json"
SUPPORTED_HINT_KINDS = {"attribute_type", "buff", "skill"}
HINT_MAP_BY_KIND = {
    "attribute_type": "attributeTypeHints",
    "buff": "buffHints",
    "skill": "skillHints",
}


@lru_cache(maxsize=4)
def _load_hints() -> dict[str, Any]:
    if not HINTS_PATH.exists():
        raise AppError(status_code=503, code="semantic_hints_missing", message="本地分类提示不存在，请先运行构建脚本。")
    return json.loads(HINTS_PATH.read_text(encoding="utf-8"))


class LocalGameSemanticHintsService:
    def get_catalog_summary(self) -> dict[str, Any]:
        payload = _load_hints()
        modules = {}
        for kind in SUPPORTED_HINT_KINDS:
            bucket = payload.get(HINT_MAP_BY_KIND[kind], {})
            modules[kind] = {
                "kind": kind,
                "count": len(bucket),
                "source": {"primary": "local_semantic_hints"},
            }
        return {
            "source": payload.get("source", {}),
            "summary": payload.get("summary", {}),
            "modules": modules,
            "sourceStrategy": {kind: "local_semantic_hints" for kind in SUPPORTED_HINT_KINDS},
        }

    def list_entries(self, kind: str) -> dict[str, Any]:
        normalized_kind = self._normalize_kind(kind)
        payload = _load_hints()
        bucket = payload.get(HINT_MAP_BY_KIND[normalized_kind], {})
        entries = list(bucket.values())
        return {
            "kind": normalized_kind,
            "count": len(entries),
            "entries": entries,
            "source": {"primary": "local_semantic_hints"},
        }

    def get_entry_detail(self, kind: str, entry_id: str) -> dict[str, Any]:
        normalized_kind = self._normalize_kind(kind)
        payload = _load_hints()
        bucket = payload.get(HINT_MAP_BY_KIND[normalized_kind], {})
        detail = bucket.get(entry_id)
        if detail is None:
            raise AppError(status_code=404, code="semantic_hint_not_found", message="未找到对应分类提示。")
        return {
            "kind": normalized_kind,
            "id": entry_id,
            "detail": detail,
            "source": {"primary": "local_semantic_hints"},
        }

    def _normalize_kind(self, kind: str) -> str:
        if kind not in SUPPORTED_HINT_KINDS:
            raise AppError(status_code=404, code="semantic_hint_kind_not_found", message="未找到对应分类提示类型。")
        return kind


local_game_semantic_hints_service = LocalGameSemanticHintsService()
