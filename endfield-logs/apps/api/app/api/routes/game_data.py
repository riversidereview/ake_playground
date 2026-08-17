from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.services.game_catalog import local_game_catalog_service


router = APIRouter(prefix="/api/game-data", tags=["game-data"])


@router.get("/catalog")
def get_catalog_summary() -> dict[str, Any]:
    return local_game_catalog_service.get_catalog_summary()


@router.get("/{kind}")
def list_catalog_entries(kind: str) -> dict[str, Any]:
    return local_game_catalog_service.list_entries(kind)


@router.get("/{kind}/{entry_id}")
def get_catalog_entry_detail(kind: str, entry_id: str) -> dict[str, Any]:
    return local_game_catalog_service.get_entry_detail(kind, entry_id)
