from pydantic import BaseModel, Field


class BattleRosterEntry(BaseModel):
    slot: int
    character_key: str
    character_name: str
    account_display_name: str


class BattleIntegrityProof(BaseModel):
    version: str
    canonical_sha256: str
    seal_algorithm: str | None = None
    server_seal: str | None = None


class RawLogIntegrityProof(BaseModel):
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
    meta: dict = Field(default_factory=dict)


class RawLogUploadIntegrityGate(BaseModel):
    tamper_suspected: bool = False
    integrity_proof_present: bool = True
    reasons: list[str] = Field(default_factory=list)


class RawLogUploadDocument(BaseModel):
    file_name: str
    content: str
    proof: RawLogIntegrityProof | None = None
    integrity_gate: RawLogUploadIntegrityGate


class UploadBattleRequest(BaseModel):
    battle_fingerprint: str
    dungeon_key: str
    dungeon_name: str
    boss_key: str
    boss_name: str
    duration_ms: int
    clear_flag: bool
    roster: list[BattleRosterEntry]
    integrity: BattleIntegrityProof | None = None
