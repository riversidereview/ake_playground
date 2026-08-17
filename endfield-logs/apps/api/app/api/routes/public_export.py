"""对外只读导出 API（排轴器等外部工具消费）。

契约要点（2026-07-05 用户定稿）：
- 只读、仅公开排名 battle、免 token；per-IP 限流兜底。
- 自有版本化 schema（schemaVersion 字段），老 payload（无 casts）返回 422 明确拒绝。
- battle 数据不可变 → 强缓存（ETag + Cache-Control）。
- 匿名跨域可读：手动 Access-Control-Allow-Origin: *（全局 CORSMiddleware
  是带凭据的站点白名单，不覆盖外部工具的域）。
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import defaultdict, deque

from fastapi import APIRouter, Request, Response

from app.core.errors import AppError
from app.services.public_data import public_data_service

router = APIRouter(prefix="/api/v1", tags=["public-export"])

_RATE_LIMIT_MAX_REQUESTS = 60
_RATE_LIMIT_WINDOW_SECONDS = 60.0
_rate_lock = threading.Lock()
_rate_buckets: dict[str, deque[float]] = defaultdict(deque)


def _enforce_rate_limit(request: Request) -> None:
    client_ip = request.client.host if request.client else "unknown"
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip() or client_ip
    now = time.monotonic()
    with _rate_lock:
        bucket = _rate_buckets[client_ip]
        while bucket and now - bucket[0] > _RATE_LIMIT_WINDOW_SECONDS:
            bucket.popleft()
        if len(bucket) >= _RATE_LIMIT_MAX_REQUESTS:
            raise AppError(
                status_code=429,
                code="rate_limited",
                message="请求过于频繁，请稍后再试。",
            )
        bucket.append(now)
        # 防泄漏：空桶顺手清理（低频路径，代价可忽略）
        if len(_rate_buckets) > 10_000:
            for key in [k for k, v in _rate_buckets.items() if not v][:5_000]:
                _rate_buckets.pop(key, None)


@router.get("/battles/{battle_id}/export")
def get_battle_export(battle_id: str, request: Request, response: Response) -> dict:
    _enforce_rate_limit(request)
    payload = public_data_service.get_battle_export(battle_id)
    # ETag = 内容哈希：battle 可被同用户重传覆盖（补全字段），
    # 固定 ETag + 长缓存会让 CDN 永远供旧数据（2026-07-05 排轴器开发者踩中）。
    # max-age 收敛到 60s，重传后一分钟内全网生效。
    content_hash = hashlib.md5(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    etag = f'W/"{content_hash}"'
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "public, max-age=60"
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=dict(response.headers))  # type: ignore[return-value]
    return payload
