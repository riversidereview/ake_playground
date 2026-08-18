from __future__ import annotations

import json
from pathlib import Path


def build_name_index(character_table_path: Path, i18n_path: Path) -> dict[str, str]:
    character_table = json.loads(character_table_path.read_text(encoding="utf-8-sig"))
    i18n_table = json.loads(i18n_path.read_text(encoding="utf-8-sig"))

    name_index: dict[str, str] = {}
    for templateid, payload in character_table.items():
        name_payload = payload.get("name") or {}
        name_id = name_payload.get("id")
        if name_id is None:
            continue
        text = i18n_table.get(str(name_id))
        if isinstance(text, str) and text:
            name_index[templateid] = text
    return name_index


def load_name_index(name_index_path: Path) -> dict[str, str]:
    if not name_index_path.exists():
        manifest_candidates = [
            name_index_path.resolve().parents[1] / "data" / "akedata" / "character" / "manifest.json",
            name_index_path.resolve().parent / "data" / "akedata" / "character" / "manifest.json",
            Path(__file__).resolve().parents[3] / "endfield-logs" / "data" / "akedata" / "character" / "manifest.json",
        ]
        for manifest_path in manifest_candidates:
            if manifest_path.exists():
                try:
                    items = json.loads(manifest_path.read_text(encoding="utf-8"))
                    if isinstance(items, list):
                        return {
                            str(item["charId"]): str(item["name"])
                            for item in items
                            if isinstance(item, dict) and "charId" in item and "name" in item
                        }
                except Exception:
                    pass
        return {}
    payload = json.loads(name_index_path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid name index payload: {name_index_path}")
    return {str(templateid): str(name) for templateid, name in payload.items() if isinstance(name, str) and name}

