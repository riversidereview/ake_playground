from fastapi import APIRouter, Response

from app.schemas.public import HotBossCard
from app.services.public_data import public_data_service

router = APIRouter(prefix="/api/home", tags=["home"])


@router.get("/hot-bosses", response_model=list[HotBossCard])
def get_hot_bosses(response: Response) -> list[HotBossCard]:
    response.headers["Cache-Control"] = "public, max-age=30, stale-while-revalidate=300"
    return public_data_service.list_hot_bosses()
