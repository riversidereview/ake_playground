from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.services.game_semantic_hints import local_game_semantic_hints_service


router = APIRouter(prefix="/api/game-semantics/hints", tags=["game-semantics"])


@router.get("/catalog")
def get_semantic_hint_catalog() -> dict[str, Any]:
    return local_game_semantic_hints_service.get_catalog_summary()


@router.get("/{kind}")
def list_semantic_hints(kind: str) -> dict[str, Any]:
    return local_game_semantic_hints_service.list_entries(kind)


@router.get("/{kind}/{entry_id}")
def get_semantic_hint_detail(kind: str, entry_id: str) -> dict[str, Any]:
    return local_game_semantic_hints_service.get_entry_detail(kind, entry_id)
