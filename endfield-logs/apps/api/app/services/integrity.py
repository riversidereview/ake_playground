from __future__ import annotations

import hashlib
import hmac
import json
from datetime import date, datetime
from typing import Any

from app.core.config import get_settings

INTEGRITY_VERSION = "battle-struct-v1"


def _normalize(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return _normalize(value.model_dump(mode="json"))
    if isinstance(value, dict):
        return {str(k): _normalize(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _build_canonical_json(payload: Any) -> str:
    normalized = _normalize(payload)
    return json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _build_canonical_sha256(payload: Any) -> str:
    canonical_json = _build_canonical_json(payload)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def _build_server_seal(payload: Any, secret: str) -> str:
    canonical_json = _build_canonical_json(payload)
    return hmac.new(secret.encode("utf-8"), canonical_json.encode("utf-8"), hashlib.sha256).hexdigest()


def build_battle_integrity(payload: Any) -> dict[str, Any]:
    settings = get_settings()
    canonical_sha256 = _build_canonical_sha256(payload)
    server_seal = _build_server_seal(payload, settings.integrity_secret) if settings.integrity_secret else None
    verified = True
    if server_seal:
        expected = _build_server_seal(payload, settings.integrity_secret)
        verified = hmac.compare_digest(expected, server_seal)
    return {
        "version": INTEGRITY_VERSION,
        "canonicalSha256": canonical_sha256,
        "sealAlgorithm": "hmac-sha256" if server_seal else None,
        "serverSeal": server_seal,
        "verified": verified,
    }
