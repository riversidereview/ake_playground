from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AuthSession:
    session_token: str
    user_id: str
    email: str
    nickname: str


@dataclass
class BattleCandidate:
    candidate_id: str
    source_battle_index: int
    source_log_path: str
    file_name: str
    boss_name: str
    dungeon_name: str
    duration_ms: int
    roster_names: list[str]
    payload: dict
    selected: bool = False
    duplicate: bool = False
    duplicate_url: str | None = None
    upload_url: str | None = None
    upload_error: str | None = None


@dataclass
class UploaderStore:
    session: AuthSession | None = None
    current_trace_file_name: str | None = None
    current_trace_path: str | None = None
    current_integrity_label: str | None = None
    current_trace_integrity_verified: bool = False
    candidates: list[BattleCandidate] = field(default_factory=list)
    last_uploaded_battle_urls: list[str] = field(default_factory=list)
    upload_running: bool = False
