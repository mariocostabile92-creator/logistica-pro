from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.dependencies.planning_readiness import (
    get_planning_readiness_service,
)
from app.domain.core_language import OperationalUnit
from app.domain.planning_readiness import PlanningReadinessResult
from app.runtime.planning_readiness import PlanningReadinessService


router = APIRouter(prefix="/api/planning", tags=["planning"])


@router.get("/readiness", response_model=PlanningReadinessResult)
def readiness(
    organization_id: Annotated[
        str,
        Query(min_length=1, max_length=120),
    ] = "default",
    operational_unit_id: Annotated[
        str,
        Query(min_length=1, max_length=120),
    ] = "default",
    operation_date: date | None = Query(default=None),
    service: PlanningReadinessService = Depends(
        get_planning_readiness_service
    ),
) -> PlanningReadinessResult:
    evaluated_at = datetime.now(UTC)
    return service.evaluate(
        organization_id=organization_id,
        operational_unit=OperationalUnit(
            external_identifier=operational_unit_id
        ),
        operation_date=operation_date or evaluated_at.date(),
        evaluated_at=evaluated_at,
    )
