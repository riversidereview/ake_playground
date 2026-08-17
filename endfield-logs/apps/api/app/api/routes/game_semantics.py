from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.services.game_semantics import local_game_semantics_service


router = APIRouter(prefix="/api/game-semantics", tags=["game-semantics"])


@router.get("/catalog")
def get_semantic_catalog_summary() -> dict[str, Any]:
    return local_game_semantics_service.get_catalog_summary()


@router.get("/{kind}")
def list_semantic_entries(kind: str) -> dict[str, Any]:
    return local_game_semantics_service.list_entries(kind)


@router.get("/{kind}/{entry_id}")
def get_semantic_entry_detail(kind: str, entry_id: str) -> dict[str, Any]:
    return local_game_semantics_service.get_entry_detail(kind, entry_id)
