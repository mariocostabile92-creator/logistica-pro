from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.dependencies.planning_timeline import (
    get_planning_timeline_service,
)
from app.domain.core_language import OperationalUnit
from app.domain.planning_timeline import PlanningTimelineResult
from app.runtime.planning_timeline import PlanningTimelineRuntimeService


router = APIRouter(prefix="/api/planning", tags=["planning"])


@router.get("/timeline", response_model=PlanningTimelineResult)
def timeline(
    organization_id: Annotated[
        str,
        Query(min_length=1, max_length=120),
    ] = "default",
    operational_unit_id: Annotated[
        str,
        Query(min_length=1, max_length=120),
    ] = "default",
    operation_date: date | None = Query(default=None),
    service: PlanningTimelineRuntimeService = Depends(
        get_planning_timeline_service
    ),
) -> PlanningTimelineResult:
    evaluated_at = datetime.now(UTC)
    return service.timeline(
        organization_id=organization_id,
        operational_unit=OperationalUnit(
            external_identifier=operational_unit_id
        ),
        operation_date=operation_date or evaluated_at.date(),
        evaluated_at=evaluated_at,
    )
