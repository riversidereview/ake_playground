import logging

from fastapi import APIRouter, Request

from app.core.errors import AppError
from app.schemas.uploader import (
    CheckDuplicateBattleRequest,
    CheckDuplicateBattleResponse,
    UploadBattleRequest,
    UploadBattleResponse,
)
from app.services.auth import SESSION_COOKIE_NAME, auth_service
from app.services.public_data import public_data_service
from app.services.uploader_client_policy import require_supported_upload_semantics, require_supported_uploader_client

router = APIRouter(prefix="/api/uploader/battles", tags=["uploader-battles"])
logger = logging.getLogger(__name__)


def _resolve_session_token(request: Request) -> str | None:
    authorization = request.headers.get("authorization", "")
    if authorization.startswith("Bearer "):
        token = authorization[7:].strip()
        if token:
            return token
    return request.cookies.get(SESSION_COOKIE_NAME)


def _require_authenticated_user(request: Request):
    session_token = _resolve_session_token(request)
    user = auth_service.get_user_from_session(session_token)
    if user is None:
        raise AppError(status_code=401, code="session_invalid", message="请先登录上传器账号。")
    return user


@router.post("/check-duplicate", response_model=CheckDuplicateBattleResponse)
def check_duplicate(payload: CheckDuplicateBattleRequest, request: Request) -> CheckDuplicateBattleResponse:
    _ = _require_authenticated_user(request)
    require_supported_uploader_client(request)
    require_supported_upload_semantics(
        request,
        parser_version=payload.parserVersion,
        rules_version=payload.rulesVersion,
    )
    battle = public_data_service.find_duplicate_battle(payload.battleFingerprint)
    if battle is None:
        return CheckDuplicateBattleResponse(duplicate=False)
    return CheckDuplicateBattleResponse(
        duplicate=True,
        battleId=battle.battle_id,
        battleUrl=f"/battle/{battle.battle_id}",
    )


@router.post("", response_model=UploadBattleResponse)
def upload_battle(payload: UploadBattleRequest, request: Request) -> UploadBattleResponse:
    user = _require_authenticated_user(request)
    require_supported_uploader_client(request)
    require_supported_upload_semantics(
        request,
        parser_version=payload.battle.parserVersion,
        rules_version=payload.battle.rulesVersion,
    )
    logger.info(
        "uploader battle upload user=%s client=%s/%s builder=%s parser_header=%s rules_header=%s "
        "payload_parser=%s payload_rules=%s fingerprint=%s duration_ms=%s total_damage=%s",
        user.id,
        request.headers.get("x-endfield-uploader-name", ""),
        request.headers.get("x-endfield-uploader-version", ""),
        request.headers.get("x-endfield-payload-builder-version", ""),
        request.headers.get("x-endfield-parser-version", ""),
        request.headers.get("x-endfield-rules-version", ""),
        payload.battle.parserVersion,
        payload.battle.rulesVersion,
        payload.battle.battleFingerprint,
        payload.battle.durationMs,
        payload.battle.totalDamage,
    )
    created = public_data_service.create_uploaded_battle(payload, uploader_user_id=user.id, uploader_nickname=user.nickname)
    return UploadBattleResponse(
        battleId=created.battle_id,
        battleUrl=f"/battle/{created.battle_id}",
    )
