from fastapi import APIRouter

from app.core.errors import AppError
from app.schemas.integrity import (
    PreflightRawLogUploadRequest,
    PreflightRawLogUploadResponse,
    VerifyRawLogIntegrityRequest,
    VerifyRawLogIntegrityResponse,
)
from app.services.raw_log_integrity import verify_raw_log_proof

router = APIRouter(prefix="/api/integrity", tags=["integrity"])


@router.post("/verify-raw-log", response_model=VerifyRawLogIntegrityResponse)
def verify_raw_log(payload: VerifyRawLogIntegrityRequest) -> VerifyRawLogIntegrityResponse:
    result = verify_raw_log_proof(payload.content.encode("utf-8"), payload.proof.model_dump())
    computed = result["computed"]
    return VerifyRawLogIntegrityResponse(
        verified=result["verified"],
        issues=result["issues"],
        computed_byte_size=computed["byte_size"],
        computed_line_count=computed["line_count"],
        computed_sha256=computed["sha256"],
        computed_chain_sha256=computed["chain_sha256"],
    )


@router.post("/preflight-raw-log-upload", response_model=PreflightRawLogUploadResponse)
def preflight_raw_log_upload(payload: PreflightRawLogUploadRequest) -> PreflightRawLogUploadResponse:
    if payload.integrity_gate.tamper_suspected:
        raise AppError(status_code=422, code="raw_log_rejected", message="原始日志完整性校验未通过，站点已拒收。")
    if payload.proof is None or not payload.integrity_gate.integrity_proof_present:
        raise AppError(status_code=422, code="raw_log_rejected", message="缺少原始日志完整性说明，站点已拒收。")

    result = verify_raw_log_proof(payload.content.encode("utf-8"), payload.proof.model_dump())
    if not result["verified"]:
        raise AppError(status_code=422, code="raw_log_rejected", message="原始日志完整性校验未通过，站点已拒收。")

    return PreflightRawLogUploadResponse(
        accepted=True,
        canonical_reason="raw_log_integrity_verified",
    )
