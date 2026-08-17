from typing import Literal

from fastapi import APIRouter, Query

from app.schemas.public import BossCharacterStatisticsResponse, BossRankingResponse
from app.services.public_data import public_data_service

router = APIRouter(prefix="/api/bosses", tags=["bosses"])


@router.get("/character-statistics", response_model=BossCharacterStatisticsResponse)
def get_all_character_statistics(
    metric: Literal["dps", "rdps"] = Query(default="dps"),
    time_range: Literal["7d", "14d", "30d", "all"] = Query(default="all", alias="range"),
    potential: Literal["0", "1-5", "all"] = Query(default="all"),
) -> BossCharacterStatisticsResponse:
    return public_data_service.get_all_character_statistics(metric, time_range, potential)


@router.get("/{boss_slug}/rankings", response_model=BossRankingResponse)
def get_boss_rankings(
    boss_slug: str,
    metric: Literal["dps", "rdps"] = Query(default="dps"),
) -> BossRankingResponse:
    return public_data_service.get_boss_rankings(boss_slug, metric)


@router.get("/{boss_slug}/character-statistics", response_model=BossCharacterStatisticsResponse)
def get_boss_character_statistics(
    boss_slug: str,
    metric: Literal["dps", "rdps"] = Query(default="dps"),
    time_range: Literal["7d", "14d", "30d", "all"] = Query(default="all", alias="range"),
    potential: Literal["0", "1-5", "all"] = Query(default="all"),
) -> BossCharacterStatisticsResponse:
    return public_data_service.get_boss_character_statistics(boss_slug, metric, time_range, potential)
