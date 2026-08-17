from pydantic import BaseModel, Field

from upload_domain.enums import DuplicateStatus, UploadStatus, ValidationStatus


class ParsedBattleCandidate(BaseModel):
    local_id: str
    dungeon_name: str
    boss_name: str
    duration_ms: int | None = None
    roster_summary: list[str] = Field(default_factory=list)
    validation_status: ValidationStatus = ValidationStatus.UNKNOWN
    validation_reason_short: str | None = None
    duplicate_status: DuplicateStatus = DuplicateStatus.UNKNOWN
    duplicate_battle_id: str | None = None
    duplicate_battle_url: str | None = None
    selected: bool = False
    upload_status: UploadStatus = UploadStatus.IDLE
    uploaded_battle_id: str | None = None
    uploaded_battle_url: str | None = None
