from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime
from typing import Any


RAW_LOG_PROOF_VERSION = "raw-log-proof-v1"
RAW_LOG_PROOF_SOURCE = "endfield-dps-overlay"
RAW_LOG_SEAL_ALGORITHM = "hmac-sha256(local)"
_CHAIN_SEED = b"endfield-raw-log-chain-v1"
# Keep the original seal seed stable for backward compatibility with
# already-exported sidecar proofs. Embedded proofs reuse the same seal scheme.
_LOCAL_SEAL_KEY = hashlib.sha256(
    b"endfield|meter|raw-log-proof|2026-04|sidecar"
).digest()


def _normalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _normalize(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    return value


def _canonical_json(payload: dict[str, Any]) -> str:
    normalized = _normalize(payload)
    return json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def build_raw_log_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_raw_log_chain_sha256(data: bytes) -> str:
    acc = _CHAIN_SEED
    for idx, line in enumerate(data.splitlines(keepends=True)):
        hasher = hashlib.sha256()
        hasher.update(acc)
        hasher.update(idx.to_bytes(4, "big", signed=False))
        hasher.update(line)
        acc = hasher.digest()
    return hashlib.sha256(acc).hexdigest()


def build_raw_log_proof(
    data: bytes,
    *,
    file_name: str | None = None,
    exported_at: str | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "version": RAW_LOG_PROOF_VERSION,
        "source": RAW_LOG_PROOF_SOURCE,
        "file_name": file_name,
        "exported_at": exported_at or datetime.now().astimezone().isoformat(timespec="seconds"),
        "byte_size": len(data),
        "line_count": len(data.splitlines(keepends=True)),
        "sha256": build_raw_log_sha256(data),
        "chain_sha256": build_raw_log_chain_sha256(data),
        "meta": meta or {},
    }
    local_seal = hmac.new(
        _LOCAL_SEAL_KEY,
        _canonical_json(payload).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    payload["seal_algorithm"] = RAW_LOG_SEAL_ALGORITHM
    payload["local_seal"] = local_seal
    return payload


def verify_raw_log_proof(data: bytes, proof: dict[str, Any]) -> dict[str, Any]:
    issues: list[str] = []
    computed = {
        "byte_size": len(data),
        "line_count": len(data.splitlines(keepends=True)),
        "sha256": build_raw_log_sha256(data),
        "chain_sha256": build_raw_log_chain_sha256(data),
    }
    if proof.get("version") != RAW_LOG_PROOF_VERSION:
        issues.append("proof.version mismatch")
    if proof.get("source") != RAW_LOG_PROOF_SOURCE:
        issues.append("proof.source mismatch")
    if proof.get("byte_size") != computed["byte_size"]:
        issues.append("proof.byte_size mismatch")
    if proof.get("line_count") != computed["line_count"]:
        issues.append("proof.line_count mismatch")
    if proof.get("sha256") != computed["sha256"]:
        issues.append("proof.sha256 mismatch")
    if proof.get("chain_sha256") != computed["chain_sha256"]:
        issues.append("proof.chain_sha256 mismatch")
    expected_payload = {
        "version": proof.get("version"),
        "source": proof.get("source"),
        "file_name": proof.get("file_name"),
        "exported_at": proof.get("exported_at"),
        "byte_size": proof.get("byte_size"),
        "line_count": proof.get("line_count"),
        "sha256": proof.get("sha256"),
        "chain_sha256": proof.get("chain_sha256"),
        "meta": proof.get("meta") or {},
    }
    expected_seal = hmac.new(
        _LOCAL_SEAL_KEY,
        _canonical_json(expected_payload).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if proof.get("seal_algorithm") != RAW_LOG_SEAL_ALGORITHM:
        issues.append("proof.seal_algorithm mismatch")
    if not hmac.compare_digest(str(proof.get("local_seal") or ""), expected_seal):
        issues.append("proof.local_seal mismatch")
    return {
        "verified": not issues,
        "issues": issues,
        "computed": computed,
    }
