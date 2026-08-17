from fastapi import APIRouter, Request

from app.schemas.admin import (
    AdminActionResponse,
    AdminDashboardResponse,
    AdminResetPasswordRequest,
    AdminSetUserAdminRequest,
    AdminSetUserDisabledRequest,
)
from app.schemas.public import DeleteBattleResponse
from app.services.auth import SESSION_COOKIE_NAME, auth_service
from app.services.admin_data import admin_data_service
from app.services.public_data import public_data_service

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _resolve_session_token(request: Request) -> str | None:
    authorization = request.headers.get("authorization", "")
    if authorization.startswith("Bearer "):
        token = authorization[7:].strip()
        if token:
            return token
    return request.cookies.get(SESSION_COOKIE_NAME)


@router.get("/dashboard", response_model=AdminDashboardResponse)
def get_admin_dashboard(request: Request) -> AdminDashboardResponse:
    session_token = _resolve_session_token(request)
    viewer = auth_service.get_user_from_session(session_token)
    return admin_data_service.get_dashboard(viewer)


@router.delete("/battles/{battle_id}", response_model=DeleteBattleResponse)
def admin_delete_battle(battle_id: str, request: Request) -> DeleteBattleResponse:
    session_token = _resolve_session_token(request)
    viewer = auth_service.get_user_from_session(session_token)
    admin_data_service.require_admin(viewer)
    public_data_service.delete_battle(
        battle_id,
        viewer.id if viewer else None,
        viewer_is_admin=True,
    )
    return DeleteBattleResponse(ok=True)


@router.patch("/users/{user_id}/disabled", response_model=AdminActionResponse)
def admin_set_user_disabled(
    user_id: str,
    payload: AdminSetUserDisabledRequest,
    request: Request,
) -> AdminActionResponse:
    session_token = _resolve_session_token(request)
    viewer = auth_service.get_user_from_session(session_token)
    return admin_data_service.set_user_disabled(viewer, user_id, disabled=payload.disabled)


@router.patch("/users/{user_id}/admin", response_model=AdminActionResponse)
def admin_set_user_admin(
    user_id: str,
    payload: AdminSetUserAdminRequest,
    request: Request,
) -> AdminActionResponse:
    session_token = _resolve_session_token(request)
    viewer = auth_service.get_user_from_session(session_token)
    return admin_data_service.set_user_admin(viewer, user_id, is_admin=payload.isAdmin)


@router.post("/users/{user_id}/reset-password", response_model=AdminActionResponse)
def admin_reset_user_password(
    user_id: str,
    payload: AdminResetPasswordRequest,
    request: Request,
) -> AdminActionResponse:
    session_token = _resolve_session_token(request)
    viewer = auth_service.get_user_from_session(session_token)
    return admin_data_service.reset_user_password(viewer, user_id, new_password=payload.newPassword)


@router.delete("/users/{user_id}", response_model=AdminActionResponse)
def admin_delete_user(user_id: str, request: Request) -> AdminActionResponse:
    session_token = _resolve_session_token(request)
    viewer = auth_service.get_user_from_session(session_token)
    return admin_data_service.delete_user(viewer, user_id)
