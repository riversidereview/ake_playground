from enum import StrEnum


class ValidationStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"


class DuplicateStatus(StrEnum):
    UNKNOWN = "unknown"
    DUPLICATE = "duplicate"
    UNIQUE = "unique"


class UploadStatus(StrEnum):
    IDLE = "idle"
    UPLOADING = "uploading"
    SUCCESS = "success"
    FAILED = "failed"
    BLOCKED_DUPLICATE = "blocked_duplicate"

