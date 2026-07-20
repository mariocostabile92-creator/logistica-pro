from fastapi import APIRouter, HTTPException

from app.briefing.briefing_service import (
    generate_daily_briefing,
    get_latest_daily_briefing,
)
from app.briefing.models import DailyOperationsBriefing
from app.briefing.schemas import GenerateDailyBriefingRequest
from app.services.planning_generation_service import PlanningNotFoundError


router = APIRouter(
    prefix="/api/briefing/v1",
    tags=["daily-operations-briefing-v1"],
)


@router.get(
    "/daily/latest",
    response_model=DailyOperationsBriefing,
)
def latest() -> DailyOperationsBriefing:
    return get_latest_daily_briefing()


@router.post(
    "/daily/generate",
    response_model=DailyOperationsBriefing,
)
def generate(
    request: GenerateDailyBriefingRequest | None = None,
) -> DailyOperationsBriefing:
    try:
        return generate_daily_briefing(
            request.planning_id if request else None
        )
    except PlanningNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

