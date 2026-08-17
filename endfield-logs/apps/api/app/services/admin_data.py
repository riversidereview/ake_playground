from __future__ import annotations

import json
from dataclasses import dataclass

from secrets import token_bytes

from sqlalchemy import delete, select
from sqlalchemy.orm import load_only

from app.core.errors import AppError
from app.db.models import (
    AuthPendingProfileRecord,
    AuthSessionRecord,
    AuthUserRecord,
    AuthVerificationCodeRecord,
    UploadedBattleRecord,
)
from app.db.session import SessionLocal
from app.schemas.admin import (
    AdminActionResponse,
    AdminBattleSummaryResponse,
    AdminDashboardResponse,
    AdminOverviewResponse,
    AdminUserSummaryResponse,
)
from app.services.auth import DatabaseAuthService


@dataclass
class _AdminUserAggregate:
    id: str
    email: str | None
    nickname: str
    is_admin: bool
    is_disabled: bool
    created_at: str | None
    total_battles: int = 0
    valid_battles: int = 0
    deleted_battles: int = 0
    last_battle_at: str | None = None


class AdminDataService:
    def require_admin(self, viewer) -> None:
        if viewer is None:
            raise AppError(status_code=401, code="session_invalid", message="请先登录。")
        if not getattr(viewer, "isAdmin", False):
            raise AppError(status_code=403, code="forbidden", message="你没有后台管理权限。")

    def get_dashboard(self, viewer) -> AdminDashboardResponse:
        self.require_admin(viewer)

        with SessionLocal() as session:
            user_rows = session.execute(select(AuthUserRecord)).scalars().all()
            # load_only：管理面板是全表扫描，整行加载会把所有 battle 的时间轴 JSON
            # 一次性拉进内存（GB 级）——2026-07-05 OOM 事故修正之一。
            battle_rows = session.execute(
                select(UploadedBattleRecord)
                .options(
                    load_only(
                        UploadedBattleRecord.id,
                        UploadedBattleRecord.uploader_user_id,
                        UploadedBattleRecord.uploader_nickname,
                        UploadedBattleRecord.boss_name,
                        UploadedBattleRecord.dungeon_name,
                        UploadedBattleRecord.battle_end_at,
                        UploadedBattleRecord.created_at,
                        UploadedBattleRecord.duration_ms,
                        UploadedBattleRecord.total_damage,
                        UploadedBattleRecord.total_dps,
                        UploadedBattleRecord.status,
                        UploadedBattleRecord.visibility,
                        UploadedBattleRecord.parser_version,
                        UploadedBattleRecord.rules_version,
                        UploadedBattleRecord.roster_json,
                    )
                )
                .order_by(UploadedBattleRecord.created_at.desc())
            ).scalars().all()

        user_map: dict[str, _AdminUserAggregate] = {}
        for row in user_rows:
            user_map[row.id] = _AdminUserAggregate(
                id=row.id,
                email=row.email,
                nickname=row.nickname,
                is_admin=bool(row.is_admin),
                is_disabled=bool(row.is_disabled),
                created_at=row.created_at.isoformat(),
            )

        battle_summaries: list[AdminBattleSummaryResponse] = []
        for row in battle_rows:
            user_entry = user_map.get(row.uploader_user_id)
            if user_entry is not None:
                user_entry.total_battles += 1
                if row.status == "deleted":
                    user_entry.deleted_battles += 1
                else:
                    user_entry.valid_battles += 1
                if user_entry.last_battle_at is None or row.battle_end_at > user_entry.last_battle_at:
                    user_entry.last_battle_at = row.battle_end_at

            roster_summary = []
            try:
                roster_summary = [
                    str(item.get("characterName") or item.get("character_name") or "")
                    for item in json.loads(row.roster_json)
                    if isinstance(item, dict)
                ]
            except json.JSONDecodeError:
                roster_summary = []

            battle_summaries.append(
                AdminBattleSummaryResponse(
                    id=row.id,
                    uploaderUserId=row.uploader_user_id,
                    uploaderEmail=user_entry.email if user_entry is not None else None,
                    uploaderNickname=row.uploader_nickname,
                    bossName=row.boss_name,
                    dungeonName=row.dungeon_name,
                    battleEndAt=row.battle_end_at,
                    createdAt=row.created_at,
                    durationMs=row.duration_ms,
                    totalDamage=row.total_damage,
                    totalDps=row.total_dps,
                    status=row.status,
                    visibility=row.visibility,
                    parserVersion=row.parser_version,
                    rulesVersion=row.rules_version,
                    rosterSummary=[name for name in roster_summary if name],
                )
            )

        users = [
            AdminUserSummaryResponse(
                id=user.id,
                email=user.email,
                nickname=user.nickname,
                isAdmin=user.is_admin,
                isDisabled=user.is_disabled,
                createdAt=user.created_at,
                totalBattles=user.total_battles,
                validBattles=user.valid_battles,
                deletedBattles=user.deleted_battles,
                lastBattleAt=user.last_battle_at,
            )
            for user in user_map.values()
        ]
        users.sort(key=lambda item: item.nickname.lower())
        users.sort(key=lambda item: item.lastBattleAt or "", reverse=True)
        users.sort(key=lambda item: item.totalBattles, reverse=True)
        users.sort(key=lambda item: item.validBattles, reverse=True)

        total_battles = len(battle_summaries)
        valid_battles = sum(1 for battle in battle_summaries if battle.status == "valid")
        deleted_battles = total_battles - valid_battles
        admin_users = sum(1 for user in users if user.isAdmin)

        return AdminDashboardResponse(
            overview=AdminOverviewResponse(
                totalUsers=len(users),
                adminUsers=admin_users,
                totalBattles=total_battles,
                validBattles=valid_battles,
                deletedBattles=deleted_battles,
            ),
            users=users,
            battles=battle_summaries,
        )

    def set_user_disabled(self, viewer, user_id: str, *, disabled: bool) -> AdminActionResponse:
        self.require_admin(viewer)

        with SessionLocal() as session:
            target = session.get(AuthUserRecord, user_id)
            if target is None:
                raise AppError(status_code=404, code="user_not_found", message="未找到这个账号。")
            if disabled and target.is_admin:
                self._ensure_admin_survives(session, excluded_user_id=target.id)
            target.is_disabled = disabled
            self._delete_user_sessions(session, user_id)
            session.add(target)
            session.commit()

        return AdminActionResponse(ok=True)

    def set_user_admin(self, viewer, user_id: str, *, is_admin: bool) -> AdminActionResponse:
        self.require_admin(viewer)

        with SessionLocal() as session:
            target = session.get(AuthUserRecord, user_id)
            if target is None:
                raise AppError(status_code=404, code="user_not_found", message="未找到这个账号。")
            if not is_admin and target.is_admin and not target.is_disabled:
                self._ensure_admin_survives(session, excluded_user_id=target.id)
            target.is_admin = is_admin
            session.add(target)
            session.commit()

        return AdminActionResponse(ok=True)

    def reset_user_password(self, viewer, user_id: str, *, new_password: str) -> AdminActionResponse:
        self.require_admin(viewer)
        if len(new_password) < 8:
            raise AppError(status_code=422, code="password_too_short", message="新密码至少需要 8 位。")

        with SessionLocal() as session:
            target = session.get(AuthUserRecord, user_id)
            if target is None:
                raise AppError(status_code=404, code="user_not_found", message="未找到这个账号。")
            salt = token_bytes(16).hex()
            target.password_salt = salt
            target.password_hash = DatabaseAuthService._hash_password(new_password, salt)
            self._delete_user_sessions(session, user_id)
            session.add(target)
            session.commit()

        return AdminActionResponse(ok=True)

    def delete_user(self, viewer, user_id: str) -> AdminActionResponse:
        self.require_admin(viewer)

        with SessionLocal() as session:
            target = session.get(AuthUserRecord, user_id)
            if target is None:
                raise AppError(status_code=404, code="user_not_found", message="未找到这个账号。")
            if target.is_admin and not target.is_disabled:
                self._ensure_admin_survives(session, excluded_user_id=target.id)

            for battle in session.execute(
                select(UploadedBattleRecord)
                .options(load_only(UploadedBattleRecord.id, UploadedBattleRecord.status))
                .where(
                    UploadedBattleRecord.uploader_user_id == user_id,
                )
            ).scalars():
                battle.status = "deleted"
                session.add(battle)

            self._delete_user_sessions(session, user_id)
            session.execute(delete(AuthVerificationCodeRecord).where(AuthVerificationCodeRecord.email == target.email))
            session.execute(delete(AuthPendingProfileRecord).where(AuthPendingProfileRecord.email == target.email))
            session.delete(target)
            session.commit()

        from app.services.public_data import public_data_service

        public_data_service._invalidate_public_caches()
        return AdminActionResponse(ok=True)

    @staticmethod
    def _delete_user_sessions(session, user_id: str) -> None:
        session.execute(delete(AuthSessionRecord).where(AuthSessionRecord.user_id == user_id))

    @staticmethod
    def _ensure_admin_survives(session, *, excluded_user_id: str) -> None:
        remaining_admin = session.execute(
            select(AuthUserRecord.id).where(
                AuthUserRecord.id != excluded_user_id,
                AuthUserRecord.is_admin.is_(True),
                AuthUserRecord.is_disabled.is_(False),
            )
        ).scalars().first()
        if remaining_admin is None:
            raise AppError(
                status_code=409,
                code="last_admin_protected",
                message="至少要保留一个可用的管理员账号。",
            )


admin_data_service = AdminDataService()
