from __future__ import annotations

from collections.abc import Iterable
from urllib.parse import urlsplit

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp

API_SECURITY_HEADERS = {
    "Content-Security-Policy": "base-uri 'self'; form-action 'self'; frame-ancestors 'none'; object-src 'none'",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Origin-Agent-Cluster": "?1",
    "Permissions-Policy": "camera=(), geolocation=(), microphone=()",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}

_UNSAFE_METHODS = {"DELETE", "PATCH", "POST", "PUT"}


def normalize_origin(value: str | None) -> str | None:
    if value is None:
        return None
    candidate = value.strip()
    if not candidate or candidate == "null":
        return None
    parsed = urlsplit(candidate)
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        for key, value in API_SECURITY_HEADERS.items():
            response.headers.setdefault(key, value)
        return response


class CookieCsrfMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: ASGIApp,
        *,
        session_cookie_name: str,
        trusted_origins: Iterable[str],
        allow_missing_origin: bool,
    ) -> None:
        super().__init__(app)
        self._session_cookie_name = session_cookie_name
        self._trusted_origins = {
            normalized
            for normalized in (normalize_origin(origin) for origin in trusted_origins)
            if normalized is not None
        }
        self._allow_missing_origin = allow_missing_origin

    async def dispatch(self, request: Request, call_next):
        if request.method.upper() not in _UNSAFE_METHODS:
            return await call_next(request)

        if request.headers.get("authorization", "").startswith("Bearer "):
            return await call_next(request)
        if self._session_cookie_name not in request.cookies:
            return await call_next(request)

        origin = normalize_origin(request.headers.get("origin"))
        referer_origin = normalize_origin(request.headers.get("referer"))
        source_origin = origin or referer_origin

        if source_origin is None:
            if self._allow_missing_origin:
                return await call_next(request)
            return JSONResponse(
                status_code=403,
                content={
                    "error": {
                        "code": "csrf_origin_required",
                        "message": "缺少可信的请求来源。",
                    }
                },
            )

        if source_origin not in self._trusted_origins:
            return JSONResponse(
                status_code=403,
                content={
                    "error": {
                        "code": "csrf_origin_forbidden",
                        "message": "请求来源未被允许。",
                    }
                },
            )
        return await call_next(request)
