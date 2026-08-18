from fastapi import APIRouter, Query, Request, Response
from pydantic import EmailStr

from app.core.config import get_settings
from app.schemas.auth import (
    AuthSessionResponse,
    AuthMeResponse,
    CheckEmailResponse,
    CheckNicknameResponse,
    CompleteProfileRequest,
    LogoutResponse,
    PasswordLoginRequest,
    PasswordRegisterRequest,
    SendCodeRequest,
    SendCodeResponse,
    UpdateNicknameRequest,
    VerifyCodeRequest,
    VerifyCodeResponse,
)
from app.services.auth import SESSION_COOKIE_NAME, auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _resolve_session_token(request: Request) -> str | None:
    authorization = request.headers.get("authorization", "")
    if authorization.startswith("Bearer "):
        token = authorization[7:].strip()
        if token:
            return token
    return request.cookies.get(SESSION_COOKIE_NAME)


def _build_web_cookie_options() -> dict:
    settings = get_settings()
    options = {
        "httponly": True,
        "max_age": 7 * 24 * 60 * 60,
        "path": "/",
        "samesite": "lax",
        "secure": settings.session_cookie_secure_enabled,
    }
    if settings.session_cookie_domain:
        options["domain"] = settings.session_cookie_domain
    return options


def _apply_auth_response_headers(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


def _apply_web_cookie(result: dict, response: Response, *, purpose: str) -> dict:
    session_token = result.get("sessionToken")
    if purpose == "web_login" and session_token:
        response.set_cookie(key=SESSION_COOKIE_NAME, value=session_token, **_build_web_cookie_options())
        result["sessionToken"] = None
    return result


@router.post("/send-code", response_model=SendCodeResponse)
def send_code(payload: SendCodeRequest, response: Response) -> SendCodeResponse:
    _apply_auth_response_headers(response)
    debug_code = auth_service.send_code(payload.email, payload.purpose)
    settings = get_settings()
    return SendCodeResponse(
        ok=True,
        cooldownSeconds=60,
        purpose=payload.purpose,
        debugCode=debug_code if settings.auth_debug_code_exposed else None,
    )


@router.post("/verify-code", response_model=VerifyCodeResponse)
def verify_code(payload: VerifyCodeRequest, response: Response) -> VerifyCodeResponse:
    _apply_auth_response_headers(response)
    result = auth_service.verify_code(payload.email, payload.purpose, payload.code)
    return VerifyCodeResponse(**_apply_web_cookie(result, response, purpose=payload.purpose))


@router.post("/complete-profile", response_model=VerifyCodeResponse)
def complete_profile(payload: CompleteProfileRequest, response: Response) -> VerifyCodeResponse:
    _apply_auth_response_headers(response)
    result = auth_service.complete_profile(payload.profileSetupToken, payload.nickname)
    purpose = "web_login" if result.get("clientType") == "web" else "uploader_login"
    return VerifyCodeResponse(**_apply_web_cookie(result, response, purpose=purpose))


@router.post("/register", response_model=AuthSessionResponse)
def register_password(payload: PasswordRegisterRequest, response: Response) -> AuthSessionResponse:
    _apply_auth_response_headers(response)
    result = auth_service.register_with_password(
        payload.email,
        payload.purpose,
        payload.password,
        payload.nickname,
        payload.code,
    )
    return AuthSessionResponse(**_apply_web_cookie(result, response, purpose=payload.purpose))


@router.post("/login", response_model=AuthSessionResponse)
def login_password(payload: PasswordLoginRequest, response: Response) -> AuthSessionResponse:
    _apply_auth_response_headers(response)
    result = auth_service.login_with_password(payload.account_identifier, payload.purpose, payload.password)
    return AuthSessionResponse(**_apply_web_cookie(result, response, purpose=payload.purpose))


@router.get("/check-nickname", response_model=CheckNicknameResponse)
def check_nickname(nickname: str = Query(min_length=2, max_length=32)) -> CheckNicknameResponse:
    return CheckNicknameResponse(available=auth_service.check_nickname(nickname))


@router.get("/check-email", response_model=CheckEmailResponse)
def check_email(email: str = Query(min_length=1, max_length=320)) -> CheckEmailResponse:
    return CheckEmailResponse(available=auth_service.check_email(str(email).strip()))


@router.get("/me", response_model=AuthMeResponse)
def auth_me(request: Request, response: Response) -> AuthMeResponse:
    _apply_auth_response_headers(response)
    session_token = _resolve_session_token(request)
    user = auth_service.get_user_from_session(session_token)
    return AuthMeResponse(authenticated=user is not None, user=user)


@router.patch("/me/nickname", response_model=AuthMeResponse)
def update_nickname(payload: UpdateNicknameRequest, request: Request, response: Response) -> AuthMeResponse:
    _apply_auth_response_headers(response)
    session_token = _resolve_session_token(request)
    user = auth_service.update_nickname(session_token, payload.nickname)
    return AuthMeResponse(authenticated=True, user=user)


@router.post("/logout", response_model=LogoutResponse)
def logout(request: Request, response: Response) -> LogoutResponse:
    _apply_auth_response_headers(response)
    session_token = _resolve_session_token(request)
    auth_service.logout(session_token)
    response.delete_cookie(SESSION_COOKIE_NAME, path="/", domain=get_settings().session_cookie_domain)
    return LogoutResponse(ok=True)
