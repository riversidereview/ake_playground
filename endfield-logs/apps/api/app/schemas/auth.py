from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class SendCodeRequest(BaseModel):
    email: EmailStr
    purpose: Literal["web_login", "uploader_login"]


class SendCodeResponse(BaseModel):
    ok: bool
    cooldownSeconds: int
    purpose: str
    debugCode: str | None = None


class VerifyCodeRequest(BaseModel):
    email: EmailStr
    purpose: Literal["web_login", "uploader_login"]
    code: str


class CompleteProfileRequest(BaseModel):
    profileSetupToken: str
    nickname: str


class PasswordRegisterRequest(BaseModel):
    nickname: str = Field(min_length=2, max_length=32)
    password: str = Field(min_length=6, max_length=128)
    email: str | None = Field(default=None, max_length=320)
    purpose: Literal["web_login", "uploader_login"] = "web_login"
    code: str | None = Field(default=None, max_length=16)


class PasswordLoginRequest(BaseModel):
    password: str = Field(min_length=1, max_length=128)
    email: str | None = Field(default=None, max_length=320)
    account: str | None = Field(default=None, max_length=320)
    purpose: Literal["web_login", "uploader_login"] = "web_login"

    @property
    def account_identifier(self) -> str:
        return (self.account or self.email or "").strip()


class UpdateNicknameRequest(BaseModel):
    nickname: str = Field(min_length=2, max_length=32)


class CheckNicknameResponse(BaseModel):
    available: bool


class CheckEmailResponse(BaseModel):
    available: bool


class AuthUser(BaseModel):
    id: str
    email: str
    nickname: str
    isAdmin: bool = False


class VerifyCodeResponse(BaseModel):
    status: Literal["authenticated", "needs_profile"]
    user: AuthUser | None = None
    profileSetupToken: str | None = None
    sessionToken: str | None = None
    clientType: Literal["web", "uploader"] | None = None


class AuthSessionResponse(BaseModel):
    status: Literal["authenticated"]
    user: AuthUser
    sessionToken: str | None = None
    clientType: Literal["web", "uploader"]


class AuthMeResponse(BaseModel):
    authenticated: bool
    user: AuthUser | None = None


class LogoutResponse(BaseModel):
    ok: bool
