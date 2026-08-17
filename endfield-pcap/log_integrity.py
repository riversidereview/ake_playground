from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime
from typing import Any


RAW_LOG_PROOF_VERSION = "raw-log-proof-v1"
RAW_LOG_PROOF_SOURCE = "endfield-dps-overlay"
RAW_LOG_SEAL_ALGORITHM = "hmac-sha256(local)"
RAW_LOG_LOADOUT_BEGIN_PREFIX = "## ENDFIELD_LOADOUT_SUMMARY_BEGIN sep="
RAW_LOG_LOADOUT_END = "## ENDFIELD_LOADOUT_SUMMARY_END"
RAW_LOG_PROOF_BEGIN_PREFIX = "## ENDFIELD_RAW_LOG_INTEGRITY_BEGIN sep="
RAW_LOG_PROOF_END = "## ENDFIELD_RAW_LOG_INTEGRITY_END"
_CHAIN_SEED = b"endfield-raw-log-chain-v1"
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


def _proof_json_text(proof: dict[str, Any]) -> str:
    return json.dumps(proof, ensure_ascii=False, indent=2, sort_keys=True)


def build_embedded_raw_log_text(
    text: str,
    *,
    file_name: str | None = None,
    exported_at: str | None = None,
    meta: dict[str, Any] | None = None,
    loadout_summary: str | None = None,
) -> tuple[str, dict[str, Any]]:
    data = text.encode("utf-8")
    proof = build_raw_log_proof(
        data,
        file_name=file_name,
        exported_at=exported_at,
        meta=meta,
    )
    body_text = text
    loadout_text = (loadout_summary or "").strip()
    if loadout_text:
        summary_separator_added = bool(body_text) and not body_text.endswith("\n")
        if summary_separator_added:
            body_text += "\n"
        body_text += (
            f"{RAW_LOG_LOADOUT_BEGIN_PREFIX}{1 if summary_separator_added else 0}\n"
            f"{loadout_text}\n"
            f"{RAW_LOG_LOADOUT_END}\n"
        )

    separator_added = bool(body_text) and not body_text.endswith("\n")
    proof_block = (
        f"{RAW_LOG_PROOF_BEGIN_PREFIX}{1 if separator_added else 0}\n"
        f"{_proof_json_text(proof)}\n"
        f"{RAW_LOG_PROOF_END}\n"
    )
    if separator_added:
        body_text += "\n"
    return body_text + proof_block, proof


def write_embedded_raw_log(
    log_path: str,
    *,
    text: str,
    meta: dict[str, Any] | None = None,
    loadout_summary: str | None = None,
) -> dict[str, Any]:
    embedded_text, proof = build_embedded_raw_log_text(
        text,
        file_name=os.path.basename(log_path),
        meta=meta,
        loadout_summary=loadout_summary,
    )
    with open(log_path, "w", encoding="utf-8", errors="replace", newline="") as handle:
        handle.write(embedded_text)
    return proof
