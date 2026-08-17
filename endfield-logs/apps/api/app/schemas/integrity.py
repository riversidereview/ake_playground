from typing import Any

from pydantic import BaseModel, Field


class RawLogIntegrityProofResponse(BaseModel):
    version: str
    source: str
    file_name: str | None = None
    exported_at: str | None = None
    byte_size: int
    line_count: int
    sha256: str
    chain_sha256: str
    seal_algorithm: str | None = None
    local_seal: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class VerifyRawLogIntegrityRequest(BaseModel):
    content: str
    proof: RawLogIntegrityProofResponse


class VerifyRawLogIntegrityResponse(BaseModel):
    verified: bool
    issues: list[str]
    computed_byte_size: int
    computed_line_count: int
    computed_sha256: str
    computed_chain_sha256: str


class RawLogUploadIntegrityGateRequest(BaseModel):
    tamper_suspected: bool = False
    integrity_proof_present: bool = True
    reasons: list[str] = Field(default_factory=list)


class PreflightRawLogUploadRequest(BaseModel):
    file_name: str
    content: str
    proof: RawLogIntegrityProofResponse | None = None
    integrity_gate: RawLogUploadIntegrityGateRequest


class PreflightRawLogUploadResponse(BaseModel):
    accepted: bool
    canonical_reason: str
