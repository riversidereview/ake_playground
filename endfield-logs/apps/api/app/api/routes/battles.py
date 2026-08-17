from fastapi import APIRouter, Request

from app.schemas.public import (
    BattleDetailResponse,
    DeleteBattleResponse,
    PublicUserRankingsResponse,
    ShareSummaryResponse,
    UserBattlesResponse,
)
from app.services.auth import SESSION_COOKIE_NAME, auth_service
from app.services.public_data import public_data_service

router = APIRouter(prefix="/api/battles", tags=["battles"])


def _resolve_session_token(request: Request) -> str | None:
    authorization = request.headers.get("authorization", "")
    if authorization.startswith("Bearer "):
        token = authorization[7:].strip()
        if token:
            return token
    return request.cookies.get(SESSION_COOKIE_NAME)


@router.get("/mine", response_model=UserBattlesResponse)
def get_my_battles(request: Request) -> UserBattlesResponse:
    session_token = _resolve_session_token(request)
    viewer = auth_service.get_user_from_session(session_token)
    viewer_user_id = viewer.id if viewer else None
    return public_data_service.list_user_battles(viewer_user_id)


@router.get("/users/{account_id}/rankings", response_model=PublicUserRankingsResponse)
def get_user_rankings(account_id: str) -> PublicUserRankingsResponse:
    return public_data_service.get_public_user_rankings(account_id)


@router.get("/{battle_id}", response_model=BattleDetailResponse)
def get_battle_detail(battle_id: str, request: Request) -> BattleDetailResponse:
    session_token = _resolve_session_token(request)
    viewer = auth_service.get_user_from_session(session_token)
    viewer_user_id = viewer.id if viewer else None
    return public_data_service.get_battle_detail(
        battle_id,
        viewer_user_id,
        viewer_is_admin=auth_service.is_admin_user(viewer),
    )


@router.get("/{battle_id}/share-summary", response_model=ShareSummaryResponse)
def get_share_summary(battle_id: str) -> ShareSummaryResponse:
    return public_data_service.get_share_summary(battle_id)


@router.delete("/{battle_id}", response_model=DeleteBattleResponse)
def delete_battle(battle_id: str, request: Request) -> DeleteBattleResponse:
    session_token = _resolve_session_token(request)
    viewer = auth_service.get_user_from_session(session_token)
    viewer_user_id = viewer.id if viewer else None
    public_data_service.delete_battle(
        battle_id,
        viewer_user_id,
        viewer_is_admin=auth_service.is_admin_user(viewer),
    )
    return DeleteBattleResponse(ok=True)
