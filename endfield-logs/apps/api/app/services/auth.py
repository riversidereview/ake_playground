from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from hashlib import pbkdf2_hmac, sha256
from hmac import compare_digest
from secrets import randbelow, token_bytes, token_urlsafe
from typing import Literal

from sqlalchemy import delete, func, select
from sqlalchemy.orm import load_only

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.models import (
    AuthPendingProfileRecord,
    AuthSessionRecord,
    AuthUserRecord,
    AuthVerificationCodeRecord,
    UploadedBattleRecord,
)
from app.db.session import SessionLocal
from app.schemas.auth import AuthUser
from app.services.email_delivery import EmailDeliveryError, email_delivery_service

SESSION_COOKIE_NAME = "endfield_logs_session"

ClientPurpose = Literal["web_login", "uploader_login"]
ClientType = Literal["web", "uploader"]


class DatabaseAuthService:
    code_ttl = timedelta(minutes=10)
    profile_setup_ttl = timedelta(hours=24)

    def send_code(self, email: str, purpose: ClientPurpose) -> str:
        normalized_email = self._normalize_email(email)
        code = f"{randbelow(1_000_000):06d}"
        now = datetime.now(UTC)

        with SessionLocal() as session:
            session.execute(
                delete(AuthVerificationCodeRecord).where(
                    AuthVerificationCodeRecord.email == normalized_email,
                    AuthVerificationCodeRecord.purpose == purpose,
                )
            )
            session.add(
                AuthVerificationCodeRecord(
                    email=normalized_email,
                    purpose=purpose,
                    code=self._hash_secret(code),
                    created_at=now,
                    expires_at=now + self.code_ttl,
                )
            )
            session.commit()

        try:
            email_delivery_service.send_verification_code(
                to_email=normalized_email,
                code=code,
                purpose=purpose,
            )
        except EmailDeliveryError as exc:
            raise AppError(status_code=502, code="email_send_failed", message="验证码邮件发送失败，请稍后再试。") from exc

        return code

    def verify_code(self, email: str, purpose: ClientPurpose, code: str) -> dict:
        normalized_email = self._normalize_email(email)
        now = datetime.now(UTC)

        with SessionLocal() as session:
            self._consume_verification_code(session, normalized_email, purpose, code, now=now)
            user = self._get_user_by_email(session, normalized_email)
            if user is None:
                profile_setup_token = token_urlsafe(24)
                session.execute(
                    delete(AuthPendingProfileRecord).where(
                        AuthPendingProfileRecord.email == normalized_email,
                        AuthPendingProfileRecord.purpose == purpose,
                    )
                )
                session.add(
                    AuthPendingProfileRecord(
                        token=self._hash_secret(profile_setup_token),
                        email=normalized_email,
                        purpose=purpose,
                        created_at=now,
                        expires_at=now + self.profile_setup_ttl,
                    )
                )
                session.commit()
                return {
                    "status": "needs_profile",
                    "profileSetupToken": profile_setup_token,
                }
            if user.is_disabled:
                raise AppError(status_code=403, code="account_disabled", message="这个账号已被禁用。")
            self._maybe_bootstrap_admin(session, user)

            auth_session, session_token = self._create_session_record(user, purpose, now=now)
            session.add(auth_session)
            session.commit()
            return self._build_authenticated_response(user, session_token, client_type=auth_session.client_type)

    def complete_profile(self, profile_setup_token: str, nickname: str) -> dict:
        normalized_nickname = self._normalize_nickname(nickname)
        now = datetime.now(UTC)

        with SessionLocal() as session:
            pending = self._get_pending_profile(session, profile_setup_token)
            if pending is None:
                raise AppError(status_code=400, code="profile_setup_invalid", message="资料补全凭证无效。")
            if self._as_utc(pending.expires_at) < now:
                session.delete(pending)
                session.commit()
                raise AppError(status_code=400, code="profile_setup_invalid", message="资料补全凭证无效。")
            if self._get_user_by_nickname(session, normalized_nickname) is not None:
                raise AppError(status_code=409, code="nickname_taken", message="昵称已被占用。")
            if self._get_user_by_email(session, pending.email) is not None:
                session.delete(pending)
                session.commit()
                raise AppError(status_code=409, code="email_taken", message="这个邮箱已经注册过了。")

            user = AuthUserRecord(
                id=self._build_user_id(pending.email),
                email=pending.email,
                nickname=normalized_nickname,
                created_at=now,
                password_hash=None,
                password_salt=None,
                is_admin=self._should_seed_admin_role(pending.email),
                is_disabled=False,
            )
            auth_session, session_token = self._create_session_record(user, pending.purpose, now=now)
            session.add(user)
            session.add(auth_session)
            session.delete(pending)
            session.commit()
            return self._build_authenticated_response(user, session_token, client_type=auth_session.client_type)

    def register_with_password(
        self,
        email: str | None,
        purpose: ClientPurpose,
        password: str,
        nickname: str,
        code: str | None = None,
    ) -> dict:
        normalized_nickname = self._normalize_nickname(nickname)
        if not normalized_nickname:
            raise AppError(status_code=422, code="nickname_invalid", message="用户名/昵称不能为空。")

        raw_email = (email or "").strip()
        if raw_email and "@" in raw_email:
            normalized_email = self._normalize_email(raw_email)
        else:
            normalized_email = f"{normalized_nickname.lower()}@local"

        settings = get_settings()
        now = datetime.now(UTC)

        with SessionLocal() as session:
            if self._get_user_by_nickname(session, normalized_nickname) is not None:
                raise AppError(status_code=409, code="nickname_taken", message="用户名/昵称已被占用。")
            if self._get_user_by_email(session, normalized_email) is not None:
                raise AppError(status_code=409, code="email_taken", message="该邮箱或用户名已经注册过了。")

            if settings.email_verification_required:
                if not code or not code.strip():
                    raise AppError(status_code=400, code="code_required", message="请先输入邮箱验证码。")
                self._consume_verification_code(session, normalized_email, purpose, code.strip(), now=now)

            password_salt = token_bytes(16).hex()
            user = AuthUserRecord(
                id=self._build_user_id(normalized_email),
                email=normalized_email,
                nickname=normalized_nickname,
                created_at=now,
                password_hash=self._hash_password(password, password_salt),
                password_salt=password_salt,
                is_admin=self._should_seed_admin_role(normalized_email),
                is_disabled=False,
            )
            auth_session, session_token = self._create_session_record(user, purpose, now=now)
            session.add(user)
            session.add(auth_session)
            session.commit()
            return self._build_authenticated_response(user, session_token, client_type=auth_session.client_type)

    def login_with_password(self, account: str, purpose: ClientPurpose, password: str) -> dict:
        identifier = (account or "").strip()
        if not identifier:
            raise AppError(status_code=401, code="login_failed", message="请输入用户名或邮箱。")

        normalized_email = self._normalize_email(identifier) if "@" in identifier else f"{identifier.lower()}@local"
        normalized_nickname = self._normalize_nickname(identifier)
        now = datetime.now(UTC)

        with SessionLocal() as session:
            user = (
                self._get_user_by_nickname(session, normalized_nickname)
                or self._get_user_by_email(session, normalized_email)
                or self._get_user_by_email(session, identifier.lower())
            )
            if user is None:
                raise AppError(status_code=401, code="login_failed", message="用户名/邮箱或密码不正确。")
            if user.is_disabled:
                raise AppError(status_code=403, code="account_disabled", message="这个账号已被禁用。")
            self._maybe_bootstrap_admin(session, user)
            if not user.password_hash or not user.password_salt:
                raise AppError(status_code=400, code="password_not_set", message="这个账号还没有设置密码。")
            if not compare_digest(user.password_hash, self._hash_password(password, user.password_salt)):
                raise AppError(status_code=401, code="login_failed", message="用户名/邮箱或密码不正确。")

            auth_session, session_token = self._create_session_record(user, purpose, now=now)
            session.add(auth_session)
            session.commit()
            return self._build_authenticated_response(user, session_token, client_type=auth_session.client_type)

    def check_nickname(self, nickname: str) -> bool:
        normalized_nickname = self._normalize_nickname(nickname)
        with SessionLocal() as session:
            return self._get_user_by_nickname(session, normalized_nickname) is None

    def check_email(self, email: str) -> bool:
        normalized_email = self._normalize_email(email)
        with SessionLocal() as session:
            return self._get_user_by_email(session, normalized_email) is None

    def update_nickname(self, session_token: str | None, nickname: str) -> AuthUser:
        if not session_token:
            raise AppError(status_code=401, code="session_invalid", message="请先登录。")

        normalized_nickname = self._normalize_nickname(nickname)
        if not normalized_nickname:
            raise AppError(status_code=422, code="nickname_invalid", message="昵称不能为空。")

        with SessionLocal() as session:
            auth_session = self._get_session_record(session, session_token)
            if auth_session is None or self._as_utc(auth_session.expires_at) < datetime.now(UTC):
                raise AppError(status_code=401, code="session_invalid", message="请先登录。")

            user = session.get(AuthUserRecord, auth_session.user_id)
            if user is None or user.is_disabled:
                raise AppError(status_code=401, code="session_invalid", message="请先登录。")

            existing_user = self._get_user_by_nickname(session, normalized_nickname)
            if existing_user is not None and existing_user.id != user.id:
                raise AppError(status_code=409, code="nickname_taken", message="昵称已被占用。")

            user.nickname = normalized_nickname
            for active_session in session.execute(
                select(AuthSessionRecord).where(AuthSessionRecord.user_id == user.id)
            ).scalars():
                active_session.nickname = normalized_nickname

            # load_only：只取要改写的列，别把该用户所有 battle 的时间轴 JSON 拉进内存
            #（2026-07-05 OOM 事故修正之一）。
            for row in session.execute(
                select(UploadedBattleRecord)
                .options(
                    load_only(
                        UploadedBattleRecord.id,
                        UploadedBattleRecord.uploader_nickname,
                        UploadedBattleRecord.roster_json,
                        UploadedBattleRecord.participants_json,
                    )
                )
                .where(UploadedBattleRecord.uploader_user_id == user.id)
            ).scalars():
                row.uploader_nickname = normalized_nickname
                row.roster_json = self._replace_account_display_names(row.roster_json, normalized_nickname)
                row.participants_json = self._replace_account_display_names(row.participants_json, normalized_nickname)

            session.commit()
            session.refresh(user)
            return self._to_auth_user(user)

    def get_user_from_session(self, session_token: str | None) -> AuthUser | None:
        if not session_token:
            return None

        now = datetime.now(UTC)
        with SessionLocal() as session:
            auth_session = self._get_session_record(session, session_token)
            if auth_session is None:
                return None
            if self._as_utc(auth_session.expires_at) < now:
                session.delete(auth_session)
                session.commit()
                return None

            user = session.get(AuthUserRecord, auth_session.user_id)
            if user is None:
                session.delete(auth_session)
                session.commit()
                return None
            if user.is_disabled:
                session.delete(auth_session)
                session.commit()
                return None
            bootstrap_changed = self._maybe_bootstrap_admin(session, user)
            if bootstrap_changed:
                session.commit()
            return self._to_auth_user(user)

    def logout(self, session_token: str | None) -> None:
        if not session_token:
            return
        with SessionLocal() as session:
            auth_session = self._get_session_record(session, session_token)
            if auth_session is None:
                return
            session.delete(auth_session)
            session.commit()

    def is_admin_user(self, user: AuthUser | None) -> bool:
        if user is None:
            return False
        return bool(user.isAdmin)

    @staticmethod
    def is_bootstrap_admin_email(email: str | None) -> bool:
        if not email:
            return False
        admin_emails = {
            item.strip().lower()
            for item in get_settings().admin_emails.split(",")
            if item.strip()
        }
        return email.strip().lower() in admin_emails

    @staticmethod
    def _get_user_by_email(session, normalized_email: str) -> AuthUserRecord | None:
        return session.execute(
            select(AuthUserRecord).where(AuthUserRecord.email == normalized_email)
        ).scalar_one_or_none()

    @staticmethod
    def _get_user_by_nickname(session, normalized_nickname: str) -> AuthUserRecord | None:
        return session.execute(
            select(AuthUserRecord).where(AuthUserRecord.nickname == normalized_nickname)
        ).scalar_one_or_none()

    @staticmethod
    def _build_user_id(email: str) -> str:
        return f"usr_{sha256(email.strip().lower().encode('utf-8')).hexdigest()[:32]}"

    @staticmethod
    def _normalize_email(email: str) -> str:
        return email.strip().lower()

    @staticmethod
    def _normalize_nickname(nickname: str) -> str:
        return nickname.strip()

    @staticmethod
    def _replace_account_display_names(raw_json: str, nickname: str) -> str:
        try:
            items = json.loads(raw_json)
        except json.JSONDecodeError:
            return raw_json
        if not isinstance(items, list):
            return raw_json
        for item in items:
            if isinstance(item, dict) and "accountDisplayName" in item:
                item["accountDisplayName"] = nickname
        return json.dumps(items, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _hash_password(password: str, salt_hex: str) -> str:
        return pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            120_000,
        ).hex()

    @staticmethod
    def _hash_secret(value: str) -> str:
        return sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _client_type_from_purpose(purpose: ClientPurpose) -> ClientType:
        return "web" if purpose == "web_login" else "uploader"

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def _create_session_record(
        self,
        user: AuthUserRecord,
        purpose: ClientPurpose,
        *,
        now: datetime,
    ) -> tuple[AuthSessionRecord, str]:
        client_type = self._client_type_from_purpose(purpose)
        expires_at = now + timedelta(days=7 if client_type == "web" else 30)
        session_token = f"ses_{token_urlsafe(24)}"
        return (
            AuthSessionRecord(
                token=self._hash_secret(session_token),
                user_id=user.id,
                email=user.email,
                nickname=user.nickname,
                client_type=client_type,
                created_at=now,
                expires_at=expires_at,
            ),
            session_token,
        )

    def _build_authenticated_response(self, user: AuthUserRecord, session_token: str, *, client_type: str) -> dict:
        return {
            "status": "authenticated",
            "user": self._to_auth_user(user),
            "sessionToken": session_token,
            "clientType": client_type,
        }

    @staticmethod
    def _to_auth_user(user: AuthUserRecord) -> AuthUser:
        return AuthUser(
            id=user.id,
            email=user.email,
            nickname=user.nickname,
            isAdmin=bool(user.is_admin),
        )

    def _should_seed_admin_role(self, email: str) -> bool:
        return self.is_bootstrap_admin_email(email)

    def _maybe_bootstrap_admin(self, session, user: AuthUserRecord) -> bool:
        if user.is_admin or user.is_disabled or not self.is_bootstrap_admin_email(user.email):
            return False
        user.is_admin = True
        session.add(user)
        session.flush()
        return True

    def _consume_verification_code(
        self,
        session,
        normalized_email: str,
        purpose: ClientPurpose,
        code: str,
        *,
        now: datetime,
    ) -> None:
        record = session.execute(
            select(AuthVerificationCodeRecord)
            .where(
                AuthVerificationCodeRecord.email == normalized_email,
                AuthVerificationCodeRecord.purpose == purpose,
            )
            .order_by(AuthVerificationCodeRecord.created_at.desc())
        ).scalars().first()
        if record is None:
            raise AppError(status_code=400, code="code_invalid", message="验证码无效。")
        if self._as_utc(record.expires_at) < now:
            session.delete(record)
            session.commit()
            raise AppError(status_code=400, code="code_expired", message="验证码已过期。")
        supplied_code_hash = self._hash_secret(code)
        if not compare_digest(record.code, supplied_code_hash) and not compare_digest(record.code, code):
            raise AppError(status_code=400, code="code_invalid", message="验证码无效。")
        session.delete(record)

    def _get_pending_profile(self, session, token: str) -> AuthPendingProfileRecord | None:
        token_hash = self._hash_secret(token)
        pending = session.get(AuthPendingProfileRecord, token_hash)
        if pending is not None:
            return pending
        return session.get(AuthPendingProfileRecord, token)

    def _get_session_record(self, session, session_token: str) -> AuthSessionRecord | None:
        token_hash = self._hash_secret(session_token)
        auth_session = session.get(AuthSessionRecord, token_hash)
        if auth_session is not None:
            return auth_session
        return session.get(AuthSessionRecord, session_token)

    @staticmethod
    def _count_active_admins(session) -> int:
        return int(
            session.execute(
                select(func.count())
                .select_from(AuthUserRecord)
                .where(
                    AuthUserRecord.is_admin.is_(True),
                    AuthUserRecord.is_disabled.is_(False),
                )
            ).scalar_one()
        )


auth_service = DatabaseAuthService()
