from pydantic import BaseModel


class AdminOverviewResponse(BaseModel):
    totalUsers: int
    adminUsers: int
    totalBattles: int
    validBattles: int
    deletedBattles: int


class AdminUserSummaryResponse(BaseModel):
    id: str
    email: str | None = None
    nickname: str
    isAdmin: bool
    isDisabled: bool
    createdAt: str | None = None
    totalBattles: int
    validBattles: int
    deletedBattles: int
    lastBattleAt: str | None = None


class AdminBattleSummaryResponse(BaseModel):
    id: str
    uploaderUserId: str
    uploaderEmail: str | None = None
    uploaderNickname: str
    bossName: str
    dungeonName: str
    battleEndAt: str
    createdAt: str
    durationMs: int
    totalDamage: int
    totalDps: float
    status: str
    visibility: str
    parserVersion: str
    rulesVersion: str
    rosterSummary: list[str]


class AdminDashboardResponse(BaseModel):
    overview: AdminOverviewResponse
    users: list[AdminUserSummaryResponse]
    battles: list[AdminBattleSummaryResponse]


class AdminSetUserDisabledRequest(BaseModel):
    disabled: bool


class AdminSetUserAdminRequest(BaseModel):
    isAdmin: bool


class AdminResetPasswordRequest(BaseModel):
    newPassword: str


class AdminActionResponse(BaseModel):
    ok: bool
